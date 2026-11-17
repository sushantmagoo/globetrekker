"""Structured logging (structlog).

Every event is scrubbed (see app.core.telemetry.scrub), stamped with the current trace and
span id, sent to OpenTelemetry (-> Collector -> Loki) and printed to stdout: JSON in
production, coloured key=value locally.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response

from app.core import telemetry
from app.core.config import get_settings


def configure_logging(level: int | None = None) -> None:
    settings = get_settings()
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if settings.is_production
        else structlog.dev.ConsoleRenderer()
    )
    if level is None:
        level = logging.WARNING if settings.app_env == "test" else logging.INFO
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            telemetry.scrub_event,
            telemetry.add_trace_context,
            telemetry.export_to_otel,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
    )


async def request_context_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Bind a request id to every log line of the request and echo it in the response."""
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    if len(request_id) > 64 or not request_id.isascii():
        request_id = uuid.uuid4().hex
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
