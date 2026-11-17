"""OpenTelemetry: traces, metrics and logs for the Globetrekker API.

When ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set (see docker-compose.observability.yml) all three
signals are sent over OTLP/HTTP to the OpenTelemetry Collector, which forwards them to
Tempo (traces), Prometheus (metrics) and Loki (logs). Without it, spans still get real trace
ids (so stdout logs stay correlated) but nothing is exported. ``OTEL_CONSOLE_EXPORT=true``
also prints every signal to stdout for debugging.

Privacy rules (enforced here, and again in the Collector):
- HTTP spans and metrics carry the *route template* (``/api/v1/journals/{journal_id}``),
  never the raw path, query string, headers, cookies, client IP or request/response bodies.
- No user identifiers (id, username, email) and no journal text (title, content) are recorded.
- Exceptions are recorded by type only; messages can quote user input.
- Every log event and custom span attribute passes through :func:`scrub`, which drops
  sensitive keys and masks values that look like emails or tokens.
"""

import os
import re
import time
import traceback
import uuid
from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from typing import Any

import structlog
from fastapi import Request, Response
from opentelemetry import metrics, trace
from opentelemetry._logs import SeverityNumber, get_logger, get_logger_provider, set_logger_provider
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, ConsoleLogRecordExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import SpanKind, StatusCode
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import get_settings

SCOPE = "globetrekker"
SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "globetrekker-backend")

tracer = trace.get_tracer(SCOPE)
meter = metrics.get_meter(SCOPE)

# ---------- key user journey: write and publish a journal ----------
# Each step of the journey is one API call. Requests to these routes are tagged with
# `journey` / `journey.step` on their span and metrics so the whole flow can be followed in
# Grafana: create a draft -> autosave edits -> publish -> someone reads it.
JOURNEY = "publish_journal"
JOURNEY_STEPS: dict[tuple[str, str], str] = {
    ("POST", "/api/v1/journals"): "create_draft",
    ("PATCH", "/api/v1/journals/{journal_id}"): "autosave",
    ("POST", "/api/v1/journals/{journal_id}/publish"): "publish",
    ("GET", "/api/v1/journals/{slug}"): "read",
}

# Seconds-scale buckets (the SDK defaults assume milliseconds).
_SECONDS_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1, 2.5, 5, 10]

http_duration = meter.create_histogram(
    "http.server.request.duration",
    unit="s",
    description="API request duration by route template and status code",
    explicit_bucket_boundaries_advisory=_SECONDS_BUCKETS,
)
journey_requests = meter.create_counter(
    "journey.step.requests",
    unit="{request}",
    description="Requests per step of the publish-a-journal journey, by outcome",
)
journey_duration = meter.create_histogram(
    "journey.step.duration",
    unit="s",
    description="Duration of each step of the publish-a-journal journey",
    explicit_bucket_boundaries_advisory=_SECONDS_BUCKETS,
)
journals_published = meter.create_counter(
    "journals.published",
    unit="{journal}",
    description="Journals that went from draft to published, by visibility",
)


# ---------- scrubbing ----------
# Keys whose values must never leave the process, wherever they appear in a key name.
_SENSITIVE_KEY = re.compile(
    r"pass(word|wd)?|secret|token|authorization|auth_header|cookie|session|credential|"
    r"api[_.-]?key|jwt|e[_.-]?mail|username|display_name|bio|title|subtitle|content|body|"
    r"comment|place_name|client\.address|user_agent|url\.query|url\.full|(^|[._])(ip|lat|lng)($|[._])",
    re.IGNORECASE,
)
# Values that look like credentials or contact details, wherever they appear.
_SENSITIVE_VALUE = re.compile(
    r"[\w.+-]+@[\w-]+\.[\w.-]+"  # email address
    r"|eyJ[\w-]+\.[\w-]+\.[\w-]+"  # JWT
    r"|(?i:bearer)\s+[\w.~+/=-]+",  # Authorization header value
)
REDACTED = "[REDACTED]"
_KEEP_KEYS = frozenset({"event", "level", "timestamp", "trace_id", "span_id", "request_id"})


def scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        return _SENSITIVE_VALUE.sub(REDACTED, value)
    return value


def scrub(attributes: Mapping[str, Any]) -> dict[str, Any]:
    """Drop sensitive keys and mask sensitive-looking values."""
    return {
        key: scrub_value(value)
        for key, value in attributes.items()
        if key in _KEEP_KEYS or not _SENSITIVE_KEY.search(key)
    }


def set_span_attributes(attributes: Mapping[str, Any]) -> None:
    """Set scrubbed attributes on the current span."""
    trace.get_current_span().set_attributes(
        scrub({k: v for k, v in attributes.items() if v is not None})
    )


# ---------- structlog processors ----------
def add_trace_context(
    _: Any, __: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Stamp every log line with the current trace and span id."""
    ctx = trace.get_current_span().get_span_context()
    if ctx.is_valid:
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict


def scrub_event(_: Any, __: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    return scrub(event_dict)


_SEVERITY = {
    "debug": SeverityNumber.DEBUG,
    "info": SeverityNumber.INFO,
    "warning": SeverityNumber.WARN,
    "warn": SeverityNumber.WARN,
    "error": SeverityNumber.ERROR,
    "critical": SeverityNumber.FATAL,
}
_otel_logger = get_logger(SCOPE)
_NOT_ATTRIBUTES = frozenset({"event", "level", "timestamp", "trace_id", "span_id"})


def export_to_otel(
    _: Any, method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Send the (already scrubbed) event as an OTel log record, in the current span's context
    so Loki stores the same trace id as Tempo. Returns the event unchanged for stdout."""
    level = str(event_dict.get("level", method)).lower()
    attributes = {
        key: value if isinstance(value, str | bool | int | float) else str(value)
        for key, value in event_dict.items()
        if key not in _NOT_ATTRIBUTES and value is not None
    }
    _otel_logger.emit(
        severity_number=_SEVERITY.get(level, SeverityNumber.INFO),
        severity_text=level.upper(),
        body=str(event_dict.get("event", "")),
        attributes=attributes,
    )
    return event_dict


def code_frames(exc: BaseException, limit: int = 12) -> str:
    """Where an exception was raised, as code locations only: ``file:line in function: source``.

    Deliberately leaves out the exception message and local variables (they can contain
    user input), so it is safe to export. The on-call agent uses it to find the failing code.
    """
    lines = []
    for frame in traceback.extract_tb(exc.__traceback__)[-limit:]:
        path = frame.filename.replace("\\", "/")
        if "/app/" in path:
            path = "be/app/" + path.rsplit("/app/", 1)[1]
        elif "site-packages/" in path:
            path = path.rsplit("site-packages/", 1)[1]
        lines.append(f"{path}:{frame.lineno} in {frame.name}: {(frame.line or '').strip()}")
    # Source lines are code, but a literal in them could still look like an email or token.
    return str(scrub_value("\n".join(lines)))


# ---------- setup ----------
def _exporters() -> tuple[list[Any], list[Any], list[Any]]:
    spans: list[Any] = []
    metric_exporters: list[Any] = []
    logs: list[Any] = []
    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        # Endpoint, headers and timeouts come from the standard OTEL_EXPORTER_OTLP_* variables.
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        spans.append(OTLPSpanExporter())
        metric_exporters.append(OTLPMetricExporter())
        logs.append(OTLPLogExporter())
    if os.getenv("OTEL_CONSOLE_EXPORT", "").lower() == "true":
        spans.append(ConsoleSpanExporter())
        metric_exporters.append(ConsoleMetricExporter())
        logs.append(ConsoleLogRecordExporter())
    return spans, metric_exporters, logs


def setup_telemetry(engine: AsyncEngine) -> None:
    """Install SDK providers (unless already installed, e.g. by tests) and instrument SQL.

    Safe to call more than once.
    """
    settings = get_settings()
    resource = Resource.create(
        {
            "service.name": SERVICE_NAME,
            "service.version": "0.1.0",
            # One per process: prod runs several uvicorn workers, each exporting its own
            # cumulative counters, which must not overwrite each other in Prometheus.
            "service.instance.id": f"{os.uname().nodename}-{os.getpid()}-{uuid.uuid4().hex[:6]}",
            "deployment.environment.name": settings.app_env,
        }
    )
    span_exporters, metric_exporters, log_exporters = _exporters()

    if not isinstance(trace.get_tracer_provider(), TracerProvider):
        tracer_provider = TracerProvider(resource=resource)
        for exporter in span_exporters:
            tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(tracer_provider)

    if not isinstance(metrics.get_meter_provider(), MeterProvider):
        # Export interval honours OTEL_METRIC_EXPORT_INTERVAL (ms, default 60000).
        readers = [PeriodicExportingMetricReader(e) for e in metric_exporters]
        metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=readers))

    if not isinstance(get_logger_provider(), LoggerProvider):
        logger_provider = LoggerProvider(resource=resource)
        for exporter in log_exporters:
            logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
        set_logger_provider(logger_provider)

    instrumentor = SQLAlchemyInstrumentor()
    if not instrumentor.is_instrumented_by_opentelemetry:
        # Spans carry the parameterised SQL text only; bound values are never recorded.
        # skip_dep_check: the instrumentor's declared range stops below SQLAlchemy 2.1, but
        # the engine events it hooks are unchanged (covered by tests/integration/test_telemetry).
        instrumentor.instrument(
            engine=engine.sync_engine, enable_commenter=False, skip_dep_check=True
        )


# ---------- HTTP middleware ----------
log = structlog.get_logger()
_UNLOGGED_PATHS = frozenset({"/api/health", "/api/ready"})


def _route_template(request: Request) -> str | None:
    """The matched route's template with router prefixes, e.g. ``/api/v1/journals/{slug}``."""
    fastapi_scope = request.scope.get("fastapi")
    if isinstance(fastapi_scope, dict):
        # FastAPI >= 0.16x keeps the fully-prefixed template on the effective route context.
        path = getattr(fastapi_scope.get("effective_route_context"), "path_format", None)
        if isinstance(path, str):
            return path
    path = getattr(request.scope.get("route"), "path", None)
    return path if isinstance(path, str) else None


async def telemetry_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """One server span, request metrics and a request log line per API call.

    Runs outside FastAPI's exception handlers, so it sees the final status code, including
    500 for unhandled errors (which are re-raised for Starlette to answer).
    """
    if request.url.path in _UNLOGGED_PATHS or not request.url.path.startswith("/api"):
        return await call_next(request)

    method = request.method
    status_code = 500
    error_type: str | None = None
    frames: str | None = None
    start = time.perf_counter()
    with tracer.start_as_current_span(
        method,
        kind=SpanKind.SERVER,
        attributes={"http.request.method": method, "url.scheme": request.url.scheme},
        record_exception=False,  # exception messages may quote user input
        set_status_on_exception=False,
    ) as span:
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception as exc:
            error_type = type(exc).__qualname__
            frames = code_frames(exc)
            raise
        finally:
            elapsed = time.perf_counter() - start
            route = _route_template(request) or "unmatched"
            attributes: dict[str, Any] = {
                "http.request.method": method,
                "http.route": route,
                "http.response.status_code": status_code,
            }
            if status_code >= 500:
                attributes["error.type"] = error_type or str(status_code)
                span.set_status(StatusCode.ERROR)
                if error_type:
                    event = {"exception.type": error_type}
                    if frames:
                        event["exception.frames"] = frames
                    span.add_event("exception", event)
            span.update_name(f"{method} {route}")
            span.set_attributes(attributes)
            http_duration.record(elapsed, attributes)

            step = JOURNEY_STEPS.get((method, route))
            if step:
                outcome = (
                    "success"
                    if status_code < 400
                    else "client_error"
                    if status_code < 500
                    else "server_error"
                )
                journey_attrs = {**attributes, "journey": JOURNEY, "journey.step": step}
                span.set_attributes({"journey": JOURNEY, "journey.step": step})
                journey_requests.add(1, {**journey_attrs, "outcome": outcome})
                journey_duration.record(elapsed, {**journey_attrs, "outcome": outcome})

            log_kwargs: dict[str, Any] = {
                "method": method,
                "route": route,
                "status": status_code,
                "duration_ms": round(elapsed * 1000, 1),
            }
            if step:
                log_kwargs |= {"journey": JOURNEY, "journey_step": step}
            if status_code >= 500:
                log.error(
                    "request failed", error_type=error_type, exception_frames=frames, **log_kwargs
                )
            else:
                log.info("request", **log_kwargs)
