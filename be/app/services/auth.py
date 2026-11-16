import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ProblemError, unauthorized
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    generate_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models import RefreshToken, User, UserStatus
from app.schemas import SignupIn

MAX_FAILED_LOGINS = 10
LOCKOUT = timedelta(minutes=15)
# A refresh token reused within this window after rotation is treated as a benign
# race (e.g. two tabs refreshing at once), not as theft.
ROTATION_GRACE = timedelta(seconds=30)


def _now() -> datetime:
    return datetime.now(UTC)


async def signup(session: AsyncSession, data: SignupIn) -> User:
    taken = await session.execute(
        select(User.email, User.username).where(
            (User.email == data.email) | (User.username == data.username)
        )
    )
    errors = []
    for email, username in taken:
        if email.lower() == data.email.lower():
            errors.append(
                {"field": "email", "message": "An account with this email already exists"}
            )
        if username.lower() == data.username:
            errors.append({"field": "username", "message": "This username is taken"})
    if errors:
        raise ProblemError(409, "Conflict", "Account already exists", errors=errors)

    user = User(
        email=data.email,
        username=data.username,
        display_name=data.display_name,
        password_hash=hash_password(data.password),
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise ProblemError(409, "Conflict", "Account already exists") from None
    return user


async def authenticate(session: AsyncSession, email: str, password: str) -> User:
    user = await session.scalar(select(User).where(User.email == email).with_for_update())
    invalid = unauthorized("Incorrect email or password")
    if user is None or user.deleted_at is not None:
        verify_password(password, DUMMY_PASSWORD_HASH)  # keep timing uniform
        raise invalid
    now = _now()
    if user.locked_until and user.locked_until > now:
        raise ProblemError(
            429, "Too Many Requests", "Too many failed attempts. Try again in a few minutes."
        )
    if not verify_password(password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_FAILED_LOGINS:
            user.locked_until = now + LOCKOUT
            user.failed_login_count = 0
        await session.commit()
        raise invalid
    if user.status != UserStatus.active:
        raise ProblemError(403, "Forbidden", "This account is suspended")
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    return user


async def issue_refresh_token(
    session: AsyncSession,
    user: User,
    *,
    family_id: uuid.UUID | None = None,
    user_agent: str | None = None,
    ip: str | None = None,
) -> tuple[str, RefreshToken]:
    raw, token_hash = generate_token()
    token = RefreshToken(
        user_id=user.id,
        family_id=family_id or uuid.uuid4(),
        token_hash=token_hash,
        expires_at=_now() + timedelta(days=get_settings().refresh_token_ttl_days),
        user_agent=(user_agent or "")[:500] or None,
        ip=ip,
    )
    session.add(token)
    await session.flush()
    return raw, token


async def revoke_family(session: AsyncSession, family_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


async def rotate_refresh_token(
    session: AsyncSession, raw: str, *, user_agent: str | None, ip: str | None
) -> tuple[User, str]:
    token = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw)).with_for_update()
    )
    invalid = unauthorized("Session expired, please log in again")
    if token is None:
        raise invalid
    now = _now()
    if token.revoked_at is not None:
        if token.replaced_by_id is not None and now - token.revoked_at <= ROTATION_GRACE:
            pass  # concurrent refresh: branch a new token in the same family below
        else:
            # Reuse of an old token: assume it was stolen and end the whole session.
            await revoke_family(session, token.family_id)
            await session.commit()
            raise invalid
    if token.expires_at <= now:
        raise invalid

    user = await session.get(User, token.user_id)
    if user is None or user.deleted_at is not None or user.status != UserStatus.active:
        raise invalid

    new_raw, new_token = await issue_refresh_token(
        session, user, family_id=token.family_id, user_agent=user_agent, ip=ip
    )
    if token.revoked_at is None:
        token.revoked_at = now
        token.replaced_by_id = new_token.id
    return user, new_raw


async def logout(session: AsyncSession, raw: str) -> None:
    token = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw))
    )
    if token is not None:
        await revoke_family(session, token.family_id)


async def revoke_all_sessions(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
