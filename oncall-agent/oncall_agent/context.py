"""Collect the evidence for an alert: affected journey step, metrics, logs and traces.

Every backend call is best effort: a failing backend is recorded in the context as an error
instead of stopping the incident. Telemetry is already scrubbed by the backend and the
Collector, so it holds no customer data; error logs and spans carry the exception type and
code locations (file:line in function), never the exception message.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from oncall_agent.config import Settings

# Mirrors JOURNEY_STEPS in be/app/core/telemetry.py.
STEP_ROUTES = {
    "create_draft": ("POST", "/api/v1/journals"),
    "autosave": ("PATCH", "/api/v1/journals/{journal_id}"),
    "publish": ("POST", "/api/v1/journals/{journal_id}/publish"),
    "read": ("GET", "/api/v1/journals/{slug}"),
}
ERROR_LOG_QUERY = '{{service_name="{service}"}} | severity_text=~"WARN.*|ERROR|CRITICAL"'


def parse_time(value: str | None) -> datetime | None:
    """Parse a Grafana timestamp; Go's zero time means 'unset'."""
    if not value or value.startswith("0001-"):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def affected_step(alert: dict) -> dict[str, str | None]:
    labels = alert.get("labels") or {}
    annotations = alert.get("annotations") or {}
    step = labels.get("journey_step") or annotations.get("journey_step") or None
    method, route = STEP_ROUTES.get(step or "", (None, None))
    return {
        "journey_step": step,
        "method": method,
        "route": route,
        "description": f"{method} {route} ({step})" if route else None,
    }


def time_window(alert: dict, settings: Settings, now: datetime | None = None) -> dict[str, str]:
    now = now or datetime.now(UTC)
    started = parse_time(alert.get("startsAt")) or now
    ended = parse_time(alert.get("endsAt"))
    start = started - timedelta(minutes=settings.lookback_minutes)
    end = min(ended, now) if ended and ended > start else now
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "alert_started": started.isoformat(),
    }


def normalize_trace_id(trace_id: str) -> str:
    """Tempo search drops leading zeros from trace ids; restore the 32-hex-digit form."""
    return trace_id.lower().zfill(32)


def _ns(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp() * 1e9)


def _best_effort(fn: Callable[..., Any], *args: Any) -> dict[str, Any]:
    try:
        return {"ok": True, "data": fn(*args)}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


class Collector:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self.client = client or httpx.Client(timeout=10)

    # --- Prometheus -------------------------------------------------------
    def metrics(self, window: dict[str, str], step: str | None) -> dict[str, Any]:
        start = datetime.fromisoformat(window["start"])
        end = datetime.fromisoformat(window["end"])
        rng = f"{max(int((end - start).total_seconds()), 60)}s"
        sel = f'job="{self.settings.service_name}"' + (f', journey_step="{step}"' if step else "")
        total = f"sum by (journey_step) (increase(journey_step_requests_total{{{sel}}}[{rng}]))"
        failed = (
            f"sum by (journey_step) (increase(journey_step_requests_total"
            f'{{{sel}, outcome="server_error"}}[{rng}]))'
        )
        queries = {
            "requests_by_status": (
                "sum by (journey_step, http_response_status_code, error_type) "
                f"(increase(journey_step_requests_total{{{sel}}}[{rng}]))"
            ),
            "failure_ratio": f"({failed} or {total} * 0) / {total}",
            "latency_p95_seconds": (
                "histogram_quantile(0.95, sum by (le, journey_step) "
                f"(rate(journey_step_duration_seconds_bucket{{{sel}}}[{rng}])))"
            ),
        }
        results = {}
        for name, query in queries.items():
            response = self.client.get(
                f"{self.settings.prometheus_url}/api/v1/query",
                params={"query": query, "time": end.timestamp()},
            )
            response.raise_for_status()
            results[name] = {
                "query": query,
                "result": [
                    {"labels": item["metric"], "value": item["value"][1]}
                    for item in response.json()["data"]["result"]
                ],
            }
        return results

    # --- Loki -------------------------------------------------------------
    def logs(self, window: dict[str, str]) -> dict[str, Any]:
        query = ERROR_LOG_QUERY.format(service=self.settings.service_name)
        response = self.client.get(
            f"{self.settings.loki_url}/loki/api/v1/query_range",
            params={
                "query": query,
                "start": _ns(window["start"]),
                "end": _ns(window["end"]),
                "limit": self.settings.max_logs,
                "direction": "backward",
            },
        )
        response.raise_for_status()
        entries = []
        for stream in response.json()["data"]["result"]:
            labels = stream["stream"]
            for timestamp, line, *_ in stream["values"]:
                entries.append(
                    {
                        "time": datetime.fromtimestamp(int(timestamp) / 1e9, UTC).isoformat(),
                        "message": line,
                        "severity": labels.get("severity_text"),
                        "trace_id": labels.get("trace_id"),
                        "attributes": {
                            k: v
                            for k, v in labels.items()
                            if k not in {"severity_text", "trace_id", "span_id"}
                        },
                    }
                )
        entries.sort(key=lambda e: e["time"], reverse=True)
        return {"query": query, "entries": entries[: self.settings.max_logs]}

    # --- Tempo ------------------------------------------------------------
    def search_error_traces(self, window: dict[str, str], step: str | None) -> list[str]:
        conditions = [f'resource.service.name="{self.settings.service_name}"', "status=error"]
        if step:
            conditions.append(f'span.journey.step="{step}"')
        response = self.client.get(
            f"{self.settings.tempo_url}/api/search",
            params={
                "q": "{" + " && ".join(conditions) + "}",
                "start": int(datetime.fromisoformat(window["start"]).timestamp()),
                "end": int(datetime.fromisoformat(window["end"]).timestamp()) + 1,
                "limit": self.settings.max_traces,
            },
        )
        response.raise_for_status()
        return [normalize_trace_id(t["traceID"]) for t in response.json().get("traces", [])]

    def trace(self, trace_id: str) -> dict[str, Any]:
        response = self.client.get(f"{self.settings.tempo_url}/api/v2/traces/{trace_id}")
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data

    # --- All together -----------------------------------------------------
    def collect(self, alert: dict) -> dict[str, Any]:
        step = affected_step(alert)
        window = time_window(alert, self.settings)
        metrics = _best_effort(self.metrics, window, step["journey_step"])
        logs = _best_effort(self.logs, window)

        # Traces referenced by error logs of the affected step first, then Tempo's search.
        trace_ids: list[str] = []
        for entry in (logs.get("data") or {}).get("entries", []):
            same_step = not step["journey_step"] or (
                entry["attributes"].get("journey_step") in (None, step["journey_step"])
            )
            if entry.get("trace_id") and entry["severity"] in {"ERROR", "CRITICAL"} and same_step:
                trace_ids.append(normalize_trace_id(entry["trace_id"]))
        search = _best_effort(self.search_error_traces, window, step["journey_step"])
        trace_ids.extend(search.get("data") or [])
        trace_ids = list(dict.fromkeys(trace_ids))[: self.settings.max_traces]

        traces = {}
        for trace_id in trace_ids:
            result = _best_effort(self.trace, trace_id)
            traces[trace_id] = result["data"] if result["ok"] else {"error": result["error"]}

        return {
            "collected_at": datetime.now(UTC).isoformat(),
            "affected": step,
            "window": window,
            "metrics": metrics,
            "logs": logs,
            "trace_search": search,
            "traces": traces,
        }


def _otlp_value(value: dict) -> Any:
    for key in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if key in value:
            return value[key]
    return value


def summarize_trace(trace: dict) -> list[dict[str, Any]]:
    """Flatten a Tempo trace into spans with key attributes and exception events."""
    root = trace.get("trace") or trace
    spans = []
    for batch in root.get("resourceSpans") or root.get("batches") or []:
        for scope in batch.get("scopeSpans", []):
            for span in scope.get("spans", []):
                attrs = {
                    a["key"]: _otlp_value(a.get("value", {})) for a in span.get("attributes", [])
                }
                exceptions = []
                for event in span.get("events", []):
                    if event.get("name") == "exception":
                        ev = {
                            a["key"]: _otlp_value(a.get("value", {}))
                            for a in event.get("attributes", [])
                        }
                        exceptions.append(
                            {"type": ev.get("exception.type"), "frames": ev.get("exception.frames")}
                        )
                start = int(span.get("startTimeUnixNano", 0))
                end = int(span.get("endTimeUnixNano", 0))
                spans.append(
                    {
                        "name": span.get("name"),
                        "span_id": span.get("spanId"),
                        "parent_span_id": span.get("parentSpanId"),
                        "status": (span.get("status") or {}).get("code"),
                        "duration_ms": round((end - start) / 1e6, 3) if end else None,
                        "attributes": attrs,
                        "exceptions": exceptions,
                    }
                )
    return spans
