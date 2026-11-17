#!/usr/bin/env python3
"""End-to-end check of the observability pipeline (stdlib only).

Runs the key user journey against the running stack (sign up, create a draft, autosave,
publish, read via share link), then asks Tempo, Loki and Prometheus what they stored:

1. every step produced a trace, a metric series and structured logs;
2. the logs carry the same trace ids as the traces, and latency exemplars point at them;
3. none of the stored signals contain the user's password, email, username, tokens or the
   journal's title and text.

Usage: make obs-verify   (or: python3 observability/verify_journey.py)
Needs: make obs-up, with RATE_LIMIT_ENABLED=false if you run it many times in an hour.
"""

import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from typing import Any

API = os.getenv("API_URL", "http://localhost:8000") + "/api/v1"
TEMPO = os.getenv("TEMPO_URL", "http://127.0.0.1:3200")
LOKI = os.getenv("LOKI_URL", "http://127.0.0.1:3100")
PROM = os.getenv("PROMETHEUS_URL", "http://127.0.0.1:9090")
STEPS = ("create_draft", "autosave", "publish", "read")
SERVICE = "globetrekker-backend"

failures: list[str] = []


def check(ok: bool, what: str) -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {what}")
    if not ok:
        failures.append(what)


def call(
    opener: urllib.request.OpenerDirector,
    method: str,
    url: str,
    body: Any = None,
    headers: dict[str, str] | None = None,
) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)  # noqa: S310 (local URLs)
    req.add_header("X-Requested-With", "XMLHttpRequest")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with opener.open(req, timeout=10) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None


def get_json(url: str, **params: str) -> Any:
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310 (local URLs)
        return json.loads(resp.read())


def run_journey() -> dict[str, str]:
    suffix = secrets.token_hex(4)
    user = {
        "username": f"otel_{suffix}",
        "email": f"otel_{suffix}@example.com",
        "password": f"pw-{secrets.token_urlsafe(12)}",
        "display_name": f"Otel Tester {suffix}",
    }
    title = f"Hidden waterfall {suffix}"
    text = f"The gate code is {secrets.token_hex(3)} and the key is under the stone"

    author = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    reader = urllib.request.build_opener()
    access = call(author, "POST", f"{API}/auth/signup", user)["access_token"]
    auth = {"Authorization": f"Bearer {access}"}
    created = call(author, "POST", f"{API}/journals", headers=auth)
    doc = {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }
    call(
        author,
        "PATCH",
        f"{API}/journals/{created['id']}",
        {
            "version": created["version"],
            "title": title,
            "content_json": doc,
            "visibility": "unlisted",
        },
        auth,
    )
    published = call(author, "POST", f"{API}/journals/{created['id']}/publish", headers=auth)
    token = published["share_token"]
    call(reader, "GET", f"{API}/journals/{published['slug']}?t={urllib.parse.quote(token)}")
    print(f"Journey done: journal {created['id']} published as unlisted, read via share link.")
    return {
        "journal_id": created["id"],
        "password": user["password"],
        "email": user["email"],
        "username": user["username"],
        "display name": user["display_name"],
        "access token": access,
        "share token": token,
        "journal title": title,
        "journal text": text,
        "journal slug": published["slug"],
    }


def wait_for(fetch: Any, ready: Any, what: str, timeout: float = 60) -> Any:
    deadline = time.monotonic() + timeout
    while True:
        try:
            result = fetch()
            if ready(result):
                return result
        except (urllib.error.URLError, json.JSONDecodeError, KeyError):
            result = None
        if time.monotonic() > deadline:
            print(f"  (timed out waiting for {what})")
            return result
        time.sleep(2)


def span_attrs(span: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for a in span.get("attributes", []):
        v = a["value"]
        out[a["key"]] = next(iter(v.values())) if v else None
    return out


def main() -> int:
    secrets_ = run_journey()
    journal_id = secrets_.pop("journal_id")
    start = int(time.time()) - 600

    print("\nTraces (Tempo)")
    q = f'{{ span.journal.id = "{journal_id}" }}'
    found = wait_for(
        lambda: get_json(
            f"{TEMPO}/api/search", q=q, start=str(start), end=str(int(time.time()) + 60), limit="50"
        ),
        lambda r: r and len(r.get("traces", [])) >= len(STEPS),
        "traces",
    )
    trace_ids = {t["traceID"].rjust(32, "0") for t in (found or {}).get("traces", [])}
    traces = {tid: get_json(f"{TEMPO}/api/traces/{tid}") for tid in trace_ids}
    steps_seen: dict[str, str] = {}
    db_spans = render_spans = 0
    for tid, trace in traces.items():
        for batch in trace.get("batches", []):
            for scope in batch.get("scopeSpans", []):
                for span in scope.get("spans", []):
                    attrs = span_attrs(span)
                    if "journey.step" in attrs:
                        steps_seen[attrs["journey.step"]] = tid
                    db_spans += "db.statement" in attrs
                    render_spans += span["name"] == "journal.render"
    check(set(steps_seen) == set(STEPS), f"one trace per journey step: {sorted(steps_seen)}")
    check(db_spans > 0, f"traces include SQL spans ({db_spans} found)")
    check(render_spans == 1, "autosave trace includes the journal.render span")

    print("\nLogs (Loki)")
    logql = f'{{service_name="{SERVICE}"}} | journal_id="{journal_id}"'
    logs = wait_for(
        lambda: get_json(
            f"{LOKI}/loki/api/v1/query_range", query=logql, start=str(start * 10**9), limit="200"
        ),
        lambda r: r and sum(len(s["values"]) for s in r["data"]["result"]) >= 3,
        "logs",
    )
    events: dict[str, set[str]] = {}
    for stream in (logs or {}).get("data", {}).get("result", []):
        for _, line, *meta in stream["values"]:
            tid = (meta[0] if meta else {}).get("trace_id", stream["stream"].get("trace_id", ""))
            events.setdefault(line, set()).add(tid)
    for event, step in [
        ("journal draft created", "create_draft"),
        ("journal autosaved", "autosave"),
        ("journal published", "publish"),
    ]:
        tids = events.get(event, set())
        check(
            bool(tids) and tids == {steps_seen.get(step)},
            f'"{event}" log has the {step} trace id ({next(iter(tids), "missing")[:12]}…)',
        )

    print("\nMetrics (Prometheus)")
    result = wait_for(
        lambda: get_json(
            f"{PROM}/api/v1/query",
            query=f'sum by (journey_step) (journey_step_requests_total{{job="{SERVICE}", outcome="success"}})',
        ),
        lambda r: r and {s["metric"]["journey_step"] for s in r["data"]["result"]} >= set(STEPS),
        "metrics",
    )
    series = {
        s["metric"]["journey_step"]: s["value"][1]
        for s in (result or {}).get("data", {}).get("result", [])
    }
    check(set(series) >= set(STEPS), f"journey_step_requests_total per step: {series}")
    published = get_json(
        f"{PROM}/api/v1/query", query=f'sum(journals_published_total{{job="{SERVICE}"}})'
    )
    check(bool(published["data"]["result"]), "journals_published_total is recorded")
    exemplars = get_json(
        f"{PROM}/api/v1/query_exemplars",
        query=f'journey_step_duration_seconds_bucket{{job="{SERVICE}"}}',
        start=str(start),
        end=str(int(time.time()) + 60),
    )
    ex_tids = {
        e["labels"].get("trace_id")
        for s in exemplars.get("data", [])
        for e in s.get("exemplars", [])
    }
    check(
        bool(ex_tids & set(steps_seen.values())), "latency exemplars link to this journey's traces"
    )

    print("\nPrivacy (nothing sensitive stored)")
    stored = json.dumps(traces) + json.dumps(logs)
    all_logs = get_json(
        f"{LOKI}/loki/api/v1/query_range",
        query=f'{{service_name="{SERVICE}"}}',
        start=str(start * 10**9),
        limit="5000",
    )
    stored += json.dumps(all_logs)
    labels = get_json(
        f"{PROM}/api/v1/series", **{"match[]": f'{{job="{SERVICE}"}}', "start": str(start)}
    )
    stored += json.dumps(labels)
    for what, value in secrets_.items():
        check(value not in stored, f"no {what} in traces, logs or metric labels")

    print()
    if failures:
        print(f"{len(failures)} check(s) failed.")
        return 1
    print(f"All checks passed. Open Grafana: http://127.0.0.1:3000 (trace {steps_seen['publish']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
