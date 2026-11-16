"""RFC 9457 problem+json error responses."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_JSON = "application/problem+json"


class ProblemError(Exception):
    def __init__(
        self,
        status: int,
        title: str,
        detail: str | None = None,
        *,
        errors: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self.title = title
        self.detail = detail
        self.errors = errors
        self.headers = headers


def not_found(what: str = "Resource") -> ProblemError:
    return ProblemError(404, "Not Found", f"{what} not found")


def forbidden(detail: str = "You are not allowed to do this") -> ProblemError:
    return ProblemError(403, "Forbidden", detail)


def conflict(detail: str) -> ProblemError:
    return ProblemError(409, "Conflict", detail)


def bad_request(detail: str, errors: list[dict[str, Any]] | None = None) -> ProblemError:
    return ProblemError(400, "Bad Request", detail, errors=errors)


def unauthorized(detail: str = "Authentication required") -> ProblemError:
    return ProblemError(401, "Unauthorized", detail, headers={"WWW-Authenticate": "Bearer"})


def _problem(
    request: Request,
    status: int,
    title: str,
    detail: str | None,
    errors: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "instance": request.url.path,
    }
    if detail:
        body["detail"] = detail
    if errors:
        body["errors"] = errors
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemError)
    async def _problem_handler(request: Request, exc: ProblemError) -> JSONResponse:
        return _problem(request, exc.status, exc.title, exc.detail, exc.errors, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                # drop the leading "body"/"query" segment so fields map onto form names
                "field": ".".join(str(p) for p in err["loc"][1:]) or str(err["loc"][0]),
                "message": err["msg"],
            }
            for err in exc.errors()
        ]
        return _problem(request, 422, "Validation Error", "Some fields are invalid", errors)

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _problem(
            request,
            exc.status_code,
            str(exc.detail) if exc.status_code < 500 else "Internal Server Error",
            None,
            headers=getattr(exc, "headers", None),
        )
