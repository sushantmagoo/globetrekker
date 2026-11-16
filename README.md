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

## Checks

```bash
cd be && uv run pytest && uv run ruff check . && uv run mypy      # tests start a throwaway Postgres via Docker
cd fe && npm test && npm run lint && npm run typecheck && npm run build
```

New migration: `cd be && uv run alembic revision --autogenerate -m "describe change"`

## Production

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

This needs `POSTGRES_PASSWORD`, `JWT_SECRET` and `ACME_EMAIL` set in `.env`, plus DNS for `globetrekker.me` and `www.globetrekker.me`. Caddy obtains the TLS certificates.
