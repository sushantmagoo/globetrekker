# Globetrekker

A journaling app and social network for travellers: https://globetrekker.me

- **Spec:** [`_docs/spec.md`](_docs/spec.md), including what's built so far (§9)
- **Frontend:** `fe/`, with React, TypeScript, Vite, Ant Design and TipTap
- **Backend:** `be/`, with FastAPI, async SQLAlchemy, Alembic and uv
- **Database:** PostgreSQL 18

## Run locally

```bash
cp .env.example .env
docker compose up --build
```

| What        | URL                              |
| ----------- | -------------------------------- |
| App         | http://localhost:5173            |
| API docs    | http://localhost:8000/api/docs   |

Source folders are mounted into the containers, so backend and frontend changes hot-reload.

## Develop without Docker

```bash
# backend (needs Postgres; `docker compose up -d db` is enough)
cd be && uv sync && uv run alembic upgrade head && uv run uvicorn app.main:app --reload

# frontend
cd fe && npm install && npm run dev
```

## Tests and checks

```bash
make test               # frontend + backend unit tests (no Docker)
make test-integration   # API + real Postgres 18 (throwaway container)
make e2e-install        # once: Playwright + Chromium
make e2e                # start the stack (rate limits off) and run Playwright
make lint               # ruff, mypy, oxlint, tsc, cfn-lint, actionlint, shellcheck
make help               # everything else
```

Strategy and coverage: [`_docs/testing.md`](_docs/testing.md).

New migration: `cd be && uv run alembic revision --autogenerate -m "describe change"`

## Deployment (AWS)

- **Infrastructure** (VPC, EC2, ECR, IAM) is created and updated by GitHub Actions (`.github/workflows/infra.yml`) from `infra/cloudformation/app.yaml`.
- **Releases** go out from `.github/workflows/ci-cd.yml`: every merge to `main` that passes all tests is built, pushed to ECR and deployed to EC2 over SSM, with an automatic rollback if the new release isn't healthy.
- **AWS login** uses OIDC, so no AWS keys are stored in GitHub.

- [`_docs/deployment.md`](_docs/deployment.md): architecture, security model, one-time setup.
- [`_docs/release-process.md`](_docs/release-process.md): shipping, migrations, failures, rollbacks.

## Docs

| Doc | What |
| --- | --- |
| [`_docs/spec.md`](_docs/spec.md) | Product and technical spec |
| [`_docs/tasks.md`](_docs/tasks.md) | Improvement backlog (mirrored as GitHub issues) |
| [`_docs/testing.md`](_docs/testing.md) | Test strategy: unit, integration, e2e |
| [`_docs/deployment.md`](_docs/deployment.md) | AWS deployment and infrastructure |
| [`_docs/release-process.md`](_docs/release-process.md) | How changes ship and roll back |
| [`_docs/pm.md`](_docs/pm.md), [`se.md`](_docs/se.md), [`qa.md`](_docs/qa.md) | Team roles |
