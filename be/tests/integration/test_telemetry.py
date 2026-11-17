"""The publish-a-journal journey emits traces, metrics and logs that share a trace id,
and none of the signals contain customer data or credentials."""

import json
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from opentelemetry.trace import SpanKind, StatusCode

from app.main import app
from app.services import journals as journal_service
from tests.conftest import Telemetry
from tests.integration.conftest import PASSWORD, UserFactory, doc

TITLE = "Secret sunrise over Bagan"
BODY = "We hid the spare key under the blue flowerpot"
JOURNEY_ROUTES = {
    "create_draft": "/api/v1/journals",
    "autosave": "/api/v1/journals/{journal_id}",
    "publish": "/api/v1/journals/{journal_id}/publish",
    "read": "/api/v1/journals/{slug}",
}


async def run_journey(
    c: AsyncClient, reader: AsyncClient, visibility: str = "public"
) -> dict[str, Any]:
    created = (await c.post("/api/v1/journals")).json()
    r = await c.patch(
        f"/api/v1/journals/{created['id']}",
        json={
            "version": created["version"],
            "title": TITLE,
            "content_json": doc(BODY),
            "visibility": visibility,
        },
    )
    assert r.status_code == 200, r.text
    r = await c.post(f"/api/v1/journals/{created['id']}/publish")
    assert r.status_code == 200, r.text
    published: dict[str, Any] = r.json()
    r = await reader.get(
        f"/api/v1/journals/{published['slug']}", params={"t": published["share_token"]}
    )
    assert r.status_code == 200, r.text
    return published


def server_spans(telemetry: Telemetry) -> dict[str, Any]:
    return {
        s.attributes["journey.step"]: s
        for s in telemetry.spans()
        if s.kind == SpanKind.SERVER and s.attributes and "journey.step" in s.attributes
    }


async def test_journey_signals_share_a_trace_id(
    make_user: UserFactory, client: AsyncClient, telemetry: Telemetry
) -> None:
    author = await make_user("ana")
    published = await run_journey(author, client)

    # --- traces: one server span per step, named by route template, with DB child spans
    steps = server_spans(telemetry)
    assert set(steps) == set(JOURNEY_ROUTES)
    for step, route in JOURNEY_ROUTES.items():
        span = steps[step]
        assert span.attributes["http.route"] == route
        assert span.attributes["journey"] == "publish_journal"
        assert span.name.endswith(route)
        assert span.status.status_code != StatusCode.ERROR
    assert steps["publish"].attributes["journal.id"] == published["id"]
    assert steps["publish"].attributes["journal.visibility"] == "public"
    assert steps["read"].attributes["journal.access"] == "share_link"

    autosave_trace = steps["autosave"].context.trace_id
    children = [s for s in telemetry.spans() if s.context.trace_id == autosave_trace]
    names = {s.name for s in children}
    assert "journal.render" in names
    assert any(s.attributes and s.attributes.get("db.system") == "postgresql" for s in children)

    # --- logs: the step's own event and the request log both carry the span's trace id
    logs = telemetry.logs()
    for step, event in [
        ("create_draft", "journal draft created"),
        ("autosave", "journal autosaved"),
        ("publish", "journal published"),
    ]:
        trace_id = steps[step].context.trace_id
        [record] = [r for r in logs if r.body == event]
        assert record.trace_id == trace_id
        assert record.attributes["journey"] == "publish_journal"
        [request_log] = [
            r for r in logs if r.body == "request" and r.attributes.get("journey_step") == step
        ]
        assert request_log.trace_id == trace_id
        assert request_log.attributes["route"] == JOURNEY_ROUTES[step]

    # --- metrics: per-step counters, latency and the business outcome
    points = telemetry.metrics()
    counts = {
        (p.attributes["journey.step"], p.attributes["outcome"]): p.value
        for p in points["journey.step.requests"]
    }
    assert counts == {(step, "success"): 1 for step in JOURNEY_ROUTES}
    assert {p.attributes["journey.step"] for p in points["journey.step.duration"]} == set(
        JOURNEY_ROUTES
    )
    [published_point] = points["journals.published"]
    assert published_point.value == 1
    assert published_point.attributes == {"journal.visibility": "public"}
    # Latency exemplars link the metric to the trace too.
    [publish_latency] = [
        p for p in points["journey.step.duration"] if p.attributes["journey.step"] == "publish"
    ]
    assert any(e.trace_id == steps["publish"].context.trace_id for e in publish_latency.exemplars)


async def test_failed_steps_are_counted_and_logged(
    make_user: UserFactory, telemetry: Telemetry
) -> None:
    author = await make_user("ana")
    created = (await author.post("/api/v1/journals")).json()
    assert (await author.post(f"/api/v1/journals/{created['id']}/publish")).status_code == 422
    stale = await author.patch(
        f"/api/v1/journals/{created['id']}", json={"version": created["version"] + 5}
    )
    assert stale.status_code == 409

    counts = {
        (p.attributes["journey.step"], p.attributes["http.response.status_code"]): p.value
        for p in telemetry.metrics()["journey.step.requests"]
    }
    assert counts[("publish", 422)] == 1
    assert counts[("autosave", 409)] == 1
    events = {r.body: r for r in telemetry.logs()}
    assert events["journal publish rejected"].attributes["missing"] == "title,content_json"
    assert events["journal publish rejected"].severity_text == "WARNING"
    assert (
        events["journal autosave conflict"].trace_id
        == server_spans(telemetry)["autosave"].context.trace_id
    )
    assert "journals.published" not in telemetry.metrics()


async def test_unhandled_error_records_type_but_not_message(
    make_user: UserFactory, telemetry: Telemetry, monkeypatch: pytest.MonkeyPatch
) -> None:
    author = await make_user("ana")
    created = (await author.post("/api/v1/journals")).json()

    async def broken(*_: Any) -> None:
        raise RuntimeError("could not publish for ana@example.com: " + BODY)

    monkeypatch.setattr(journal_service, "publish", broken)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
        headers=dict(author.headers),
    ) as c:
        r = await c.post(f"/api/v1/journals/{created['id']}/publish")
    assert r.status_code == 500

    span = server_spans(telemetry)["publish"]
    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes["error.type"] == "RuntimeError"
    [event] = span.events
    assert event.attributes["exception.type"] == "RuntimeError"
    # Code locations (for the on-call agent), but never the message.
    assert "test_telemetry.py" in event.attributes["exception.frames"]
    assert "in broken: raise RuntimeError" in event.attributes["exception.frames"]
    assert set(event.attributes) == {"exception.type", "exception.frames"}
    [failed] = [r for r in telemetry.logs() if r.body == "request failed"]
    assert failed.severity_text == "ERROR"
    assert failed.attributes["error_type"] == "RuntimeError"
    assert failed.attributes["exception_frames"] == event.attributes["exception.frames"]
    assert failed.trace_id == span.context.trace_id
    [point] = [
        p
        for p in telemetry.metrics()["journey.step.requests"]
        if p.attributes["outcome"] == "server_error"
    ]
    assert point.attributes["error.type"] == "RuntimeError"
    assert "ana@example.com" not in dump_all(telemetry)


def dump_all(telemetry: Telemetry) -> str:
    """Every exported span, log and metric data point as one string."""
    parts: list[Any] = []
    for s in telemetry.spans():
        parts.append([s.name, dict(s.attributes or {}), dict(s.resource.attributes)])
        parts.extend([e.name, dict(e.attributes or {})] for e in s.events)
    for r in telemetry.logs():
        parts.append([r.body, dict(r.attributes or {})])
    for name, points in telemetry.metrics().items():
        parts.extend([name, dict(p.attributes)] for p in points)
    return json.dumps(parts, default=str)


async def test_no_customer_data_or_credentials_in_telemetry(
    make_user: UserFactory, client: AsyncClient, telemetry: Telemetry
) -> None:
    author = await make_user("ana_traveller")
    published = await run_journey(author, client, visibility="unlisted")
    # Also exercise login, a token refresh and a password change.
    login = await client.post(
        "/api/v1/auth/login", json={"email": "ana_traveller@example.com", "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    refreshed = await client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200, refreshed.text

    secrets = {
        "password": PASSWORD,
        "email": "ana_traveller@example.com",
        "username": "ana_traveller",
        "display name": "Ana_Traveller",
        "access token": author.headers["Authorization"].removeprefix("Bearer "),
        "login access token": login.json()["access_token"],
        "refresh cookie": client.cookies["gt_refresh"],
        "share token": published["share_token"],
        "journal title": TITLE,
        "journal text": BODY,
        "journal slug": published["slug"],
    }
    dump = dump_all(telemetry)
    assert len(telemetry.spans()) > 10  # sanity: there was plenty to leak into
    leaked = [what for what, value in secrets.items() if value and value in dump]
    assert leaked == []
