from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Header, Request, Response, status

from app.api.deps import SessionDep
from app.core.config import get_settings
from app.core.errors import ProblemError, unauthorized
from app.core.ratelimit import limiter
from app.core.security import create_access_token
from app.models import User
from app.schemas import LoginIn, SignupIn, TokenOut
from app.services import auth as auth_service

REFRESH_COOKIE = "gt_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"


async def require_xhr(x_requested_with: Annotated[str | None, Header()] = None) -> None:
    """CSRF defence for cookie-authenticated endpoints: browsers won't send custom
    headers cross-site without a CORS preflight, which we never allow."""
    if x_requested_with != "XMLHttpRequest":
        raise ProblemError(403, "Forbidden", "Missing X-Requested-With header")


router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(require_xhr)])


def _client(request: Request) -> tuple[str | None, str | None]:
    return request.headers.get("user-agent"), request.client.host if request.client else None


def _set_refresh_cookie(response: Response, raw: str) -> None:
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        raw,
        max_age=settings.refresh_token_ttl_days * 86400,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)


def _token_out(user: User) -> TokenOut:
    return TokenOut(
        access_token=create_access_token(user.id, user.role.value),
        expires_in=get_settings().access_token_ttl_min * 60,
    )


async def _start_session(
    session: SessionDep, request: Request, response: Response, user: User
) -> TokenOut:
    ua, ip = _client(request)
    raw, _ = await auth_service.issue_refresh_token(session, user, user_agent=ua, ip=ip)
    await session.commit()
    _set_refresh_cookie(response, raw)
    return _token_out(user)


@router.post("/signup", status_code=status.HTTP_201_CREATED)
@limiter.limit("3/hour")
async def signup(
    request: Request, response: Response, data: SignupIn, session: SessionDep
) -> TokenOut:
    user = await auth_service.signup(session, data)
    return await _start_session(session, request, response, user)


@router.post("/login")
@limiter.limit("10/minute")
async def login(
    request: Request, response: Response, data: LoginIn, session: SessionDep
) -> TokenOut:
    user = await auth_service.authenticate(session, data.email, data.password)
    return await _start_session(session, request, response, user)


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    session: SessionDep,
    gt_refresh: Annotated[str | None, Cookie()] = None,
) -> TokenOut:
    if not gt_refresh:
        raise unauthorized("No active session")
    ua, ip = _client(request)
    try:
        user, new_raw = await auth_service.rotate_refresh_token(
            session, gt_refresh, user_agent=ua, ip=ip
        )
    except ProblemError:
        _clear_refresh_cookie(response)
        raise
    await session.commit()
    _set_refresh_cookie(response, new_raw)
    return _token_out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    session: SessionDep,
    gt_refresh: Annotated[str | None, Cookie()] = None,
) -> None:
    if gt_refresh:
        await auth_service.logout(session, gt_refresh)
        await session.commit()
    _clear_refresh_cookie(response)
