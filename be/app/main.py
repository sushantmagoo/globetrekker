from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from app.api.v1 import auth, feed, journals, notifications, og, social, users
from app.core.config import get_settings
from app.core.errors import PROBLEM_JSON, install_error_handlers
from app.core.logging import configure_logging, request_context_middleware
from app.core.ratelimit import limiter
from app.db.session import engine


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()

    app = FastAPI(
        title="Globetrekker API",
        version="0.1.0",
        openapi_url="/api/openapi.json",
        docs_url=None if settings.is_production else "/api/docs",
        redoc_url=None,
    )

    app.state.limiter = limiter

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limited(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(
            {
                "type": "about:blank",
                "title": "Too Many Requests",
                "status": 429,
                "detail": "Slow down a little and try again shortly.",
                "instance": request.url.path,
            },
            status_code=429,
            media_type=PROBLEM_JSON,
        )

    install_error_handlers(app)
    app.middleware("http")(request_context_middleware)
    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    v1 = APIRouter(prefix="/api/v1")
    for module in (auth, users, journals, social, feed, notifications, og):
        v1.include_router(module.router)
    app.include_router(v1)

    if not settings.is_production:

        @app.get("/docs", include_in_schema=False)
        async def docs_redirect() -> RedirectResponse:
            return RedirectResponse("/api/docs")

    @app.get("/api/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/ready", include_in_schema=False)
    async def ready() -> JSONResponse:
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return JSONResponse({"status": "ok"})

    return app


app = create_app()
