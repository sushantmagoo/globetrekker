"""Telemetry helpers: scrubbing and log/trace correlation (no database)."""

import structlog
from opentelemetry import trace

from app.core import telemetry as t
from tests.conftest import Telemetry


def test_scrub_drops_sensitive_keys() -> None:
    clean = t.scrub(
        {
            "password": "hunter2",
            "new_password": "x",
            "access_token": "abc",
            "share_token": "abc",
            "Authorization": "Bearer abc",
            "cookie": "gt_refresh=abc",
            "email": "a@b.co",
            "username": "ana",
            "display_name": "Ana",
            "title": "My trip",
            "content_json": {},
            "url.query": "t=abc",
            "client_ip": "1.2.3.4",
            "lat": 1.0,
            # kept
            "event": "journal published",
            "journal_id": "0190-abc",
            "visibility": "public",
            "status": 200,
            "relationship": "kept",  # contains "ip" but isn't an IP
            "trace_id": "0af7651916cd43dd8448eb211c80319c",
        }
    )
    assert clean == {
        "event": "journal published",
        "journal_id": "0190-abc",
        "visibility": "public",
        "status": 200,
        "relationship": "kept",
        "trace_id": "0af7651916cd43dd8448eb211c80319c",
    }


def test_scrub_masks_sensitive_looking_values() -> None:
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"
    clean = t.scrub(
        {
            "event": "lookup failed for ana@example.com",
            "detail": f"got {jwt}",
            "header": "Bearer abc.def-123",
            "count": 3,
        }
    )
    assert clean == {
        "event": f"lookup failed for {t.REDACTED}",
        "detail": f"got {t.REDACTED}",
        "header": t.REDACTED,
        "count": 3,
    }


def test_logs_carry_the_current_trace_id(telemetry: Telemetry) -> None:
    log = structlog.get_logger()
    with t.tracer.start_as_current_span("work") as span:
        log.info("journal autosaved", journal_id="j1", password="nope", note="mail me@x.io")
    ctx = span.get_span_context()

    [record] = [r for r in telemetry.logs() if r.body == "journal autosaved"]
    assert record.trace_id == ctx.trace_id
    assert record.span_id == ctx.span_id
    assert record.severity_text == "INFO"
    assert record.attributes["journal_id"] == "j1"
    assert "password" not in record.attributes
    assert record.attributes["note"] == f"mail {t.REDACTED}"


def test_logs_outside_a_span_are_still_exported(telemetry: Telemetry) -> None:
    assert not trace.get_current_span().get_span_context().is_valid
    structlog.get_logger().warning("startup check", ok=True)
    [record] = [r for r in telemetry.logs() if r.body == "startup check"]
    assert record.severity_text == "WARNING"
    assert record.attributes["ok"] is True
