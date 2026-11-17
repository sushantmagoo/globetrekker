"""On-call agent: receives Grafana alert webhooks on POST /alerts.

For each new firing alert: open an incident folder, collect the evidence (affected journey
step, metrics, logs, traces) and start the coding agent headlessly to fix the issue.
Run: uv run uvicorn oncall_agent.app:app --host 127.0.0.1 --port 8001
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from oncall_agent.agent import AgentRunner
from oncall_agent.config import Settings
from oncall_agent.context import Collector
from oncall_agent.incidents import IncidentStore, is_test_alert, save_context

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("oncall_agent")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    settings.incidents_dir.mkdir(parents=True, exist_ok=True)
    store = IncidentStore(settings.incidents_dir, settings.dedup_seconds)
    app.state.settings = settings
    app.state.store = store
    app.state.collector = Collector(settings)
    app.state.runner = AgentRunner(settings, store)
    log.info(
        "Incidents: %s | repo: %s | agent: %s",
        settings.incidents_dir,
        settings.repo_dir,
        settings.agent_command[0] if settings.agent_enabled else "disabled",
    )
    yield


app = FastAPI(title="Globetrekker on-call agent", lifespan=lifespan)


def handle_incident(incident: Path, alert: dict) -> None:
    """Collect the evidence, then hand the incident to the coding agent."""
    state = app.state
    try:
        save_context(incident, state.collector.collect(alert))
        state.store.set_status(incident, state="context_collected")
    except Exception as exc:  # still start the agent with whatever was collected
        log.exception("Context collection failed for %s", incident.name)
        state.store.set_status(incident, state="context_failed", context_error=str(exc))
    state.runner.submit(incident, test=is_test_alert(alert))


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/alerts", status_code=202)
async def receive_alerts(request: Request, background: BackgroundTasks) -> JSONResponse:
    try:
        payload = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "Body must be JSON") from exc
    alerts = payload.get("alerts") if isinstance(payload, dict) else None
    if not isinstance(alerts, list) or not alerts:
        raise HTTPException(
            422, "Expected a Grafana webhook payload with a non-empty 'alerts' list"
        )

    store: IncidentStore = app.state.store
    results: list[dict[str, Any]] = []
    for alert in alerts:
        if not isinstance(alert, dict):
            raise HTTPException(422, "Each alert must be an object")
        alertname = (alert.get("labels") or {}).get("alertname", "alert")
        status = alert.get("status") or payload.get("status") or "firing"
        alert = {**alert, "status": status}
        if status == "resolved":
            closed = store.close(alert)
            results.append(
                {
                    "alertname": alertname,
                    "status": status,
                    "action": "resolved",
                    "incident": closed.name if closed else None,
                }
            )
            continue
        incident, created = store.open_or_append(alert, payload)
        if created:
            background.add_task(handle_incident, incident, alert)
        log.info("Alert %s (%s): %s", alertname, status, "new incident" if created else "duplicate")
        results.append(
            {
                "alertname": alertname,
                "status": status,
                "action": "incident_created" if created else "duplicate",
                "incident": incident.name,
            }
        )
    return JSONResponse({"received": len(alerts), "results": results}, status_code=202)


@app.get("/incidents")
def list_incidents() -> list[dict[str, Any]]:
    root: Path = app.state.settings.incidents_dir
    incidents = []
    for path in sorted(root.iterdir(), reverse=True):
        status_file = path / "status.json"
        if path.is_dir() and status_file.exists():
            incidents.append({"incident": path.name, **json.loads(status_file.read_text())})
    return incidents
