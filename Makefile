# Globetrekker developer commands. See _docs/testing.md and _docs/deployment.md.
.DEFAULT_GOAL := help
.PHONY: help up down logs test test-frontend test-backend test-integration test-all \
        e2e-install e2e e2e-run lint lint-backend lint-frontend lint-infra build-prod

COMPOSE_PROD = docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.prod.yml

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------- local stack ----------
up: ## Start the local dev stack (http://localhost:5173)
	docker compose up -d --build

down: ## Stop the local dev stack (keeps data)
	docker compose down

logs: ## Follow backend + frontend logs
	docker compose logs -f backend frontend

# ---------- tests ----------
test: test-frontend test-backend ## Fast unit suites (frontend + backend), no Docker needed

test-frontend: ## Frontend unit tests (Vitest)
	cd fe && npm test

test-backend: ## Backend unit tests (pytest, no database)
	cd be && uv run pytest tests/unit -q

test-integration: ## Backend integration tests (API + real Postgres via testcontainers; needs Docker)
	cd be && uv run pytest tests/integration -q

e2e-install: ## One-time: install Playwright and Chromium
	cd e2e && npm ci && npx playwright install chromium

e2e: ## Start the stack with rate limits off, run Playwright, leave the stack running
	RATE_LIMIT_ENABLED=false docker compose up -d --build
	cd e2e && npx playwright test

e2e-run: ## Run Playwright against an already running stack
	cd e2e && npx playwright test

test-all: lint test test-integration e2e ## Everything CI runs

# ---------- lint ----------
lint: lint-backend lint-frontend lint-infra ## All linters and type checks

lint-backend:
	cd be && uv run ruff check . && uv run ruff format --check . && uv run mypy

lint-frontend:
	cd fe && npm run lint && npm run typecheck
	cd e2e && npm run typecheck

lint-infra: ## CloudFormation, GitHub Actions and deploy script linters
	uvx cfn-lint infra/cloudformation/*.yaml
	actionlint .github/workflows/*.yml
	shellcheck deploy/remote-deploy.sh

# ---------- production images ----------
build-prod: ## Build the production images locally (globetrekker-*:prod)
	$(COMPOSE_PROD) build backend frontend
