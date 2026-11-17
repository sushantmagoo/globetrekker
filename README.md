# Globetrekker

A journaling app and social network for travellers: https://globetrekker.me

- **Spec:** [`_docs/spec.md`](_docs/spec.md), including what's built so far (§9)
- **Frontend:** `fe/`, with React, TypeScript, Vite, Ant Design and TipTap
- **Backend:** `be/`, with FastAPI, async SQLAlchemy, Alembic and uv
- **Database:** PostgreSQL 18
- **Monitoring:** OpenTelemetry → Prometheus, Loki, Tempo → Grafana, plus an on-call agent

## Prerequisites

| For | You need |
| --- | --- |
| Running the app | Docker with Compose |
| Backend dev, tests, on-call agent | [uv](https://docs.astral.sh/uv/) (Python 3.13 is installed by uv) |
| Frontend dev, e2e tests | Node.js 22 and npm |
| On-call agent fixing issues | The `claude` CLI (Claude Code), logged in |
| Infra and deploy linters (`make lint`) | `actionlint` and `shellcheck` (cfn-lint runs via `uvx`) |

## Run locally

```bash
cp .env.example .env
docker compose up --build        # or: make up
```

| What        | URL                              |
| ----------- | -------------------------------- |
| App         | http://localhost:5173            |
| API docs    | http://localhost:8000/api/docs   |

Source folders are mounted into the containers, so backend and frontend changes hot-reload.

### With monitoring

```bash
make obs-up        # the app + OTel Collector, Prometheus, Loki, Tempo, Grafana
make obs-verify    # run the publish journey and check every signal arrived, linked and scrubbed
make obs-down      # stop (keeps data)
```

| What | URL |
| --- | --- |
| Grafana (opens on the "Publish a journal" dashboard; no login locally) | http://127.0.0.1:3000 |
| Prometheus / Loki / Tempo | http://127.0.0.1:9090, :3100, :3200 |

### Which compose files are used where

| Where | Files |
| --- | --- |
| Local (`docker compose up`, `make up`, CI e2e) | `docker-compose.yml` + `docker-compose.override.yml` (auto-loaded) |
| Local with monitoring (`make obs-up`) | the two above + `docker-compose.observability.yml` |
| Production (EC2, via `deploy/remote-deploy.sh`) | `docker-compose.yml` + `docker-compose.prod.yml` + `docker-compose.observability.yml` |

`docker-compose.override.yml` is dev-only and never used in production. `make check-compose` validates all three combinations.

## Develop without Docker

```bash
# backend (needs Postgres; `docker compose up -d db` is enough)
cd be && uv sync && uv run alembic upgrade head && uv run uvicorn app.main:app --reload

# frontend
cd fe && npm install && npm run dev
```

New migration: `cd be && uv run alembic revision --autogenerate -m "describe change"`

## Tests and checks

```bash
make test               # fast, no Docker: frontend (Vitest), backend unit, on-call agent
make test-integration   # API + real Postgres 18 (throwaway container), incl. telemetry/privacy tests
make e2e-install        # once: Playwright + Chromium
make e2e                # start the stack (rate limits off) and run Playwright
make lint               # ruff, mypy, oxlint, tsc, cfn-lint, actionlint, shellcheck
make test-all           # everything CI runs
make help               # every target
```

| Suite | Tests |
| --- | --- |
| Frontend unit (Vitest) | 29 |
| Backend unit (pytest) | 38 |
| Backend integration (pytest + Postgres 18) | 32 |
| End-to-end (Playwright) | 14 |
| On-call agent (pytest) | 12 |

CI (`.github/workflows/ci-cd.yml`) runs all of them on every pull request. Strategy and coverage are in [`_docs/testing.md`](_docs/testing.md).

## Observability

The key user journey, **write and publish a journal** (create draft → autosave → publish → read), emits metrics, traces and structured logs that share a trace id. They pass through the OpenTelemetry Collector into Prometheus, Loki and Tempo, and are shown on a Grafana dashboard. **No customer data or credentials** reach telemetry:
- route templates instead of URLs;
- no user identifiers or journal text;
- no exception messages;
- scrubbing in the app, and again in the Collector.

Tests enforce this, and `make obs-verify` checks it against the stored data. See [`_docs/observability.md`](_docs/observability.md).

## Alerting and the on-call agent

**The alert.** One user-impact alert, "Users failing to write or publish journals", fires when more than 5% of a journey step's requests fail with a server error over 5 minutes, with at least 3 failed requests (SLO: 99% success).

**The agent.** Grafana sends the alert to the **on-call agent** (`oncall-agent/`). The agent:
1. collects the metrics, logs and traces;
2. runs Claude Code headless with locked-down tools to find the root cause, fix it and add a regression test;
3. runs the backend checks and writes `REPORT.md`.

It never commits or deploys; a person reviews the change.

```bash
make obs-up
make oncall-agent                     # on the host, port 8001
open http://localhost:8001/incidents  # incidents and agent status
```

The agent runs on a developer or operator machine, not on EC2. See [`_docs/on-call-agent.md`](_docs/on-call-agent.md) for the spec and an end-to-end drill: alert fired → fix and test written in about 100 s → alert resolved.

## Deployment (AWS)

- **Infrastructure** is created and updated by GitHub Actions (`.github/workflows/infra.yml`) from `infra/cloudformation/app.yaml`:
  - VPC, EC2 with an encrypted data volume, an Elastic IP, ECR, a release bucket and IAM;
  - secrets generated into SSM Parameter Store: `POSTGRES_PASSWORD`, `JWT_SECRET`, `GRAFANA_ADMIN_PASSWORD`.
- **Releases** go out from `.github/workflows/ci-cd.yml`:
  - every merge to `main` that passes lint, unit, integration and e2e tests is built, pushed to ECR and deployed to EC2 over SSM;
  - if the new release isn't healthy, the previous one is restored automatically;
  - to roll back by hand, run the workflow with `release_sha`.
- **Monitoring ships with every release.** It is reachable only through an SSM tunnel and Grafana requires a login. Use a **`t3.medium`** instance (repo variable `INSTANCE_TYPE`) when running monitoring.
- **AWS login** uses OIDC, so no AWS keys are stored in GitHub, and there's no SSH.

Details:
- [`_docs/deployment.md`](_docs/deployment.md): architecture, security model, one-time setup, operating the server, Grafana access.
- [`_docs/release-process.md`](_docs/release-process.md): shipping, migrations, failures, rollbacks.

`make build-prod` builds the production images locally.

## Repository layout

| Path | What |
| --- | --- |
| `fe/` | React frontend |
| `be/` | FastAPI backend, Alembic migrations, unit and integration tests |
| `e2e/` | Playwright end-to-end tests |
| `observability/` | Collector, Prometheus, Loki and Tempo configs; Grafana datasources, dashboard and alert; `verify_journey.py` |
| `oncall-agent/` | Alert webhook → evidence → headless coding agent |
| `infra/cloudformation/` | AWS templates (bootstrap and app stack) |
| `deploy/` | `remote-deploy.sh`, run on EC2 by CI |
| `.github/workflows/` | `ci-cd.yml` (test, build, deploy), `infra.yml` (infrastructure) |
| `docker-compose*.yml`, `Caddyfile` | Local and production stacks |
| `_docs/` | Specs and process docs (below) |

## Docs

| Doc | What |
| --- | --- |
| [`_docs/spec.md`](_docs/spec.md) | Product and technical spec |
| [`_docs/tasks.md`](_docs/tasks.md) | Improvement backlog (mirrored as GitHub issues) |
| [`_docs/testing.md`](_docs/testing.md) | Test strategy: unit, integration, e2e, on-call agent |
| [`_docs/observability.md`](_docs/observability.md) | Metrics, traces and logs; dashboard; privacy rules; production monitoring |
| [`_docs/on-call-agent.md`](_docs/on-call-agent.md) | User-impact alert and the agent that fixes issues |
| [`_docs/deployment.md`](_docs/deployment.md) | AWS deployment and infrastructure |
| [`_docs/release-process.md`](_docs/release-process.md) | How changes ship and roll back |
| [`_docs/pm.md`](_docs/pm.md), [`se.md`](_docs/se.md), [`qa.md`](_docs/qa.md) | Team roles |
