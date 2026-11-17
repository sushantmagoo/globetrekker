# Globetrekker — On-call agent

A small service that **wakes up when a user-impact alert fires and fixes the issue**. It does four things:
1. Receives the Grafana alert.
2. Collects the evidence from Prometheus, Loki and Tempo.
3. Starts a coding agent (Claude Code, headless) on this repository to find the root cause, fix it, add a regression test and run the checks.
4. Writes everything to an incident folder.

A person reviews the change and ships it. The agent never commits, pushes or deploys.

Code: [`oncall-agent/`](../oncall-agent/). Run it with `make oncall-agent`. It is also the runbook linked from the alert.

## 1. Goals and non-goals

**Goals**
- Shorten the time from "users are hurting" to "a tested fix is ready for review".
- Act only on **user impact**, not on noise (see §3).
- Give the person reviewing the fix one folder with everything: the alert, the evidence, the agent's full transcript and a report.

**Non-goals (for now)**
- Deploying, rolling back or restarting anything. Those stay human decisions; see [`release-process.md`](release-process.md).
- Infrastructure incidents (disk full, instance down). The agent only changes application code.
- Paging people. The alert has no human contact point yet.

## 2. Flow

```
 users ──> backend ──OTLP──> Collector ──> Prometheus / Loki / Tempo
                                              │
                         Grafana alert rule ──┘ (every 30 s)
                                │ firing for 1 min
                                ▼  webhook POST /alerts
                         on-call agent (host, :8001)
                                │ 1. open incident folder (dedup by fingerprint)
                                │ 2. collect evidence (best effort)
                                │ 3. write CONTEXT.md
                                ▼
                         claude -p (headless, locked-down tools, cwd = repo)
                                │ read evidence → find code → fix → regression test
                                │ → pytest + ruff + mypy → REPORT.md
                                ▼
                         person reviews `git diff` + REPORT.md → PR → CI → deploy
                                │
                         Grafana sends "resolved" ──> incident marked resolved
```

## 3. The alert: user impact

**Rule:** `Users failing to write or publish journals`
(`observability/grafana/provisioning/alerting/user-impact-alerts.yaml`).

| | |
| --- | --- |
| **Journey** | Write and publish a journal: `create_draft` → `autosave` → `publish` → `read` |
| **SLI** (per step) | Requests that did **not** fail with a 5xx, divided by all requests. A 4xx (validation, a version conflict, not found) is the user's own mistake, not a failure. |
| **SLO** | 99% of journey requests succeed |
| **Fires when** | Over the last 5 minutes, for any one step: failure ratio **> 5%** *and* at least **3** failed requests. It must stay that way for **1 minute**. |
| **Normal when** | Below either threshold. No traffic at all also counts as Normal. |
| **Labels** | `journey_step`, `severity=critical`, `slo=publish-journal-availability` |
| **Annotations** | `summary` ("34% of "publish" requests are failing"), `impact` (failed requests and %), `description`, `dashboard_url` (filtered to the step), `runbook_url` (this file) |

Why this shape:
- **It measures what users feel.** The rule watches the share of users' attempts that fail, not causes like CPU, a single exception, or a count of errors with no denominator.
- **5% over 5 minutes** is five times the error budget, so users are clearly affected. A short window keeps detection fast.
- **The minimum of 3 failures** means one unlucky request on a quiet site never wakes anyone.
- **One alert per step** (`group_by journey_step`): the agent and the human see straight away which part of the journey broke.

It replaces the earlier "any 5xx in the publish journey" rule. That rule fired on a single error regardless of how many users were affected.

Routing: every Grafana alert goes to the contact point `on-call-agent` (`on-call-agent.yaml`), a webhook to `ONCALL_WEBHOOK_URL` (default `http://host.docker.internal:8001/alerts`). Policy settings:
- `group_wait` 10 s;
- `group_interval` 1 min;
- `repeat_interval` 4 h;
- resolve messages are enabled.

## 4. API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/alerts` | Grafana webhook. Returns 202 with one result per alert: `incident_created`, `duplicate` or `resolved`. Returns 422 for anything that isn't a webhook payload with a non-empty `alerts` list. |
| `GET` | `/incidents` | Incidents, newest first, with their state |
| `GET` | `/healthz` | Liveness |

## 5. Incident lifecycle

1. **Firing, new fingerprint:** the agent creates `incidents/<UTC time>-<alertname>-<fingerprint>/` and saves `alert.json`. It then collects context in a background task and queues the coding agent.
2. **Firing again within `ONCALL_DEDUP_SECONDS`** (default 1 h): the notification is appended to `events.jsonl`. No new run starts, because Grafana re-sends firing alerts.
3. **Resolved:** the notification is appended to `events.jsonl` and `status.json` gets `alert_status=resolved`. The next firing opens a new incident.
4. **Agent states** (`status.json` → `agent`): `queued` → `running` → `completed` | `failed` | `timed_out` | `failed_to_start` | `error`. If `ONCALL_AGENT_ENABLED=false` the state is `disabled`.
5. **One coding agent at a time.** Runs are queued so two agents never edit the working tree at once.

**Test alerts:** alerts labelled `test="true"` go through the same pipeline, but the agent is told not to change code. It only confirms the pipeline works:

```bash
curl -X POST localhost:8001/alerts -H 'Content-Type: application/json' -d \
  '{"alerts":[{"status":"firing","labels":{"alertname":"PipelineTest","test":"true"}}]}'
```

### Incident folder

```
incidents/<time>-<alertname>-<fingerprint>/
  alert.json        alert + webhook group fields
  context.json      affected step, time window, metrics, logs, trace search
  traces/<id>.json  full traces from Tempo
  CONTEXT.md        readable summary; the coding agent starts here
  events.jsonl      repeats and the resolved notification
  status.json       incident and agent state, timings, exit code
  agent/            prompt.md, output.jsonl (Claude Code stream-json transcript), stderr.log
  REPORT.md         written by the coding agent
```

`incidents/` is git-ignored.

## 6. Evidence collection

All evidence comes from the window between `startsAt` − 15 min and now. Each source is **best effort**: if a backend is down, the error is recorded and the coding agent still starts with whatever was collected.

| Source | What | Query |
| --- | --- | --- |
| Alert | Affected step → method and route (`journey_step` label); impact numbers | n/a |
| Prometheus | Requests by step, status and `error_type`; failure ratio; p95 latency | `journey_step_requests_total`, `journey_step_duration_seconds` |
| Loki | Up to 50 WARN/ERROR logs, including `error_type` and **`exception_frames`** | `{service_name="globetrekker-backend"} \| severity_text=~"WARN.*\|ERROR\|CRITICAL"` |
| Tempo | Up to 5 error traces: trace ids from error logs of the affected step first, then a TraceQL search | `{resource.service.name="globetrekker-backend" && status=error && span.journey.step="<step>"}` |

**`exception_frames`** is what lets the agent find the bug without seeing user data:
- The backend records where an unhandled exception was raised as `file:line in function: source line` (the innermost 12 frames).
- It never records the exception message or local variables.
- Values that look like emails or tokens are masked even inside source lines.

This is set in `be/app/core/telemetry.py` and tested in `be/tests/integration/test_telemetry.py`. Example from the drill:

```
be/app/api/v1/journals.py:109 in publish_journal: await journal_service.publish(session, journal, user)
be/app/services/journals.py:338 in publish: trip_days = (journal.travel_end - journal.travel_start).days + 1
```

## 7. The coding agent

```
claude -p --output-format stream-json --verbose --permission-mode acceptEdits
       --allowedTools    Read Grep Glob Edit Write
                         Bash(uv run --directory be pytest|ruff|mypy:*) Bash(git status|diff|log:*)
       --disallowedTools Bash(git commit|push|reset|checkout|restore|stash|clean:*)
                         Bash(docker|aws|gh|curl:*) WebFetch WebSearch
```

- **Where it runs:** the working directory is the repository (`ONCALL_REPO_DIR`). The prompt is passed on stdin.
- **Approvals:** in headless mode nobody can approve anything, so every action outside the allowlist is denied. File edits are auto-accepted only inside the working directory.
- **What it's asked to do** (`oncall_agent/agent.py`):
  1. Work out which step fails and how many users are affected.
  2. Find the failing code from `exception_frames`.
  3. Find the root cause.
  4. Make the smallest safe fix.
  5. Add a regression test that fails without the fix.
  6. Run `pytest`, `ruff` and `mypy` in `be/`.
  7. Write `REPORT.md`: summary, user impact, evidence, root cause, changes, test results, follow-ups.
- **What it must not do:** commit or ship anything; weaken or delete tests; remove telemetry or privacy scrubbing to silence an error.
- **Timeout:** `ONCALL_AGENT_TIMEOUT_SECONDS` (30 min); after that it is killed (`timed_out`).

### Safety

| Risk | Mitigation |
| --- | --- |
| Prompt injection via telemetry (someone puts instructions in a field that ends up in logs) | The backend and Collector already drop user content. The context and prompt label all collected data as evidence, never instructions. Tools are allowlisted: no network, no shell beyond the test and lint commands, no git writes. |
| Customer data reaching the model | The evidence only contains scrubbed telemetry (route templates, error types, code locations, opaque journal ids); see [`observability.md`](observability.md#privacy-what-is-never-sent). |
| A bad fix reaching users | Nothing is committed or deployed. A person reviews `git diff` and `REPORT.md`, then opens a PR, which runs the full CI. |
| Two agents editing at once | Single worker queue |
| Webhook spoofing | The service binds to `127.0.0.1`. If it's ever exposed beyond the host, add a shared token (Grafana webhook `authorization_credentials`). |
| Clobbering a developer's uncommitted work | Known limitation: the agent edits the checkout it runs in. Run it on a dedicated checkout (`ONCALL_REPO_DIR`), or see §10 for git worktrees. |

## 8. Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `ONCALL_AGENT_ENABLED` | `true` | `false` = only collect context |
| `ONCALL_AGENT_CMD` | the locked-down `claude -p …` above | Coding agent command (the prompt goes on stdin) |
| `ONCALL_AGENT_TIMEOUT_SECONDS` | `1800` | Kill the agent after this long |
| `ONCALL_REPO_DIR` | the repository root | Where the agent works |
| `ONCALL_INCIDENTS_DIR` | `oncall-agent/incidents/` | Incident folders |
| `ONCALL_DEDUP_SECONDS` | `3600` | Duplicate window per alert fingerprint |
| `ONCALL_LOOKBACK_MINUTES` | `15` | Evidence window before the alert started |
| `ONCALL_MAX_LOGS`, `ONCALL_MAX_TRACES` | `50`, `5` | Evidence limits |
| `PROMETHEUS_URL`, `LOKI_URL`, `TEMPO_URL` | `http://127.0.0.1:9090`, `:3100`, `:3200` | Backends |
| `ONCALL_WEBHOOK_URL` (Grafana side) | `http://host.docker.internal:8001/alerts` | Where Grafana sends alerts |

## 9. Running it

```bash
make obs-up          # app + monitoring
make oncall-agent    # on the host: needs uv, the `claude` CLI (logged in) and this checkout
open http://localhost:8001/incidents
```

**Why the host and not Docker:** the coding agent needs the `claude` CLI, its login, and a writable checkout of the repository.

**Production:** the alert rule and contact point ship with every release. The agent does not run on EC2: there is no `claude` login or writable checkout there, and the instance must not change its own code. On EC2, Grafana's deliveries to `ONCALL_WEBHOOK_URL` fail and are logged, and the alert is still visible in Grafana. To use the agent for production alerts:
1. Run it on an operator machine or a small dedicated host that can reach the production Prometheus, Loki and Tempo (for example through SSM port forwarding).
2. Point `ONCALL_WEBHOOK_URL` at it, with a shared token.

## 10. Testing

**Unit tests:** `make test-oncall-agent`, 12 tests, also in CI as the `oncall-agent` job. They use fake Prometheus, Loki and Tempo and a stand-in for `claude`, and cover:
- a firing alert creates an incident, collects context and runs the agent with the right prompt and working directory;
- duplicates are appended, resolved alerts close the incident, and a new firing opens a new one;
- the test-alert prompt;
- backends down → context errors are recorded and the agent still runs;
- an agent that fails to start;
- payload validation;
- the default command is locked down.

**End-to-end drill (17 Nov 2026, real stack, real Claude Code):**
1. **Planted bug:** publishing a journal with a start date but no end date raised `TypeError`. It was disguised as a "trip length on the publish span" feature.
2. **Traffic:** simulated users (one in three with only a start date) made 31% of publishes fail. Other steps stayed healthy.
3. **Alert:** fired only for `publish` ("34.14% of publish requests are failing", 31 failed in 5 min).
4. **Agent wakes up:** the webhook reached the agent 10 s later. The evidence pointed at `be/app/services/journals.py:338`.
5. **Diagnosis and fix** (102 s, 21 turns): Claude Code changed the guard to `if journal.travel_start and journal.travel_end:` and added `test_publish_with_only_travel_start`. It reported that the test fails without the fix (`1 failed, 70 passed`) and passes with it (`71 passed`, ruff and mypy clean). It also wrote a thorough REPORT.md.
6. **Lockdown held:** 5 tool calls outside the allowlist (`sed -i`, `git -C`, absolute-path `uv run`) were denied, and the agent used its permitted tools instead.
7. **Resolution:** the fix was live through dev hot reload. Publish success went back to 100% and Grafana sent "resolved" 5 minutes later (03:46:50 fired → 03:53:00 resolved).

The planted bug and its fix were then removed; neither was ever committed.

## 11. Future work

- **Isolated workspace:** run each incident in its own `git worktree` branch (`oncall/<incident>`) and open a draft PR automatically, so the agent never touches a developer's checkout.
- **Human notification:** add a second contact point (Slack or email) with the incident folder and report link.
- **More journeys:** add more user-impact alerts, each with its own SLO, plus a latency SLO (p95 per step) and burn-rate windows (1 h / 6 h) once there's real traffic.
- **Webhook auth:** a shared token on the webhook, required before the agent runs anywhere but localhost.
- **Browser errors:** with browser tracing, include frontend failures in the evidence.
