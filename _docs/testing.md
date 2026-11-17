# Globetrekker — Testing

Four layers, each catching a different class of bug. None replaces another; see
[Why four layers](#why-four-layers).

| Layer | Tool | Runs against | Count | Time |
| --- | --- | --- | --- | --- |
| Frontend unit | Vitest + React Testing Library | jsdom, `fetch` mocked | 29 | ~2 s |
| Backend unit | pytest | Pure Python: no database, no HTTP | 38 | <1 s |
| Integration | pytest + httpx `ASGITransport` | FastAPI in-process + a real, throwaway Postgres 18 | 32 | ~5 s |
| End-to-end | Playwright (Chromium, plus a Pixel 7 smoke test) | Real browser → Vite → FastAPI → Postgres, all in Docker | 14 | ~15 s |

```bash
make test             # frontend + backend unit suites (no Docker)
make test-integration # backend + throwaway Postgres (needs Docker)
make e2e-install      # one-time: Playwright + Chromium
make e2e              # start the stack with rate limits off, run Playwright
make lint             # ruff, mypy, oxlint, tsc, cfn-lint, actionlint, shellcheck
make test-all         # everything CI runs
```

CI runs all four layers on every pull request (see [`release-process.md`](release-process.md)).

---

## Frontend unit tests

`fe/src/**/*.test.ts(x)`, run with `make test-frontend` (or `cd fe && npm test`).

They cover UI logic in isolation. The API is mocked, so nothing talks to a backend.

| File | What it proves |
| --- | --- |
| `api/client.test.ts` | Request plumbing: the CSRF header, bearer token and query strings are sent; problem+json responses become `ApiError` with field errors; 204 responses and network errors are handled. On a 401 the client refreshes the token **once** and retries, concurrent refreshes share one request, and a failed refresh clears the session. |
| `features/editor/useAutosave.test.ts` | The autosave state machine with fake timers: edits are debounced into one request, the server's version is used for the next save, changes are kept and retried while offline, and a 409 stops saving while keeping the local copy. |
| `features/editor/videoEmbed.test.ts` | YouTube/Vimeo URL normalisation (must match the backend), including look-alike domains and `javascript:` URLs. |
| `utils/sanitize.test.ts` | Defence-in-depth HTML sanitising: only allow-listed iframes, no scripts, images or event handlers, and links get safe `rel`/`target`. Also covers share-link building (tokens only for unlisted journals) and avatar initials and colours. |
| `utils/format.test.ts` | Travel date ranges and country flags. |

## Backend unit tests

`be/tests/unit/`, run with `make test-backend` (or `cd be && uv run pytest tests/unit`).

These are pure functions with no database, network or app startup, so the whole suite runs in under a second.

| File | What it proves |
| --- | --- |
| `test_content.py` | The editor JSON → HTML pipeline, the most security-sensitive code. It covers marks and headings, escaping, link schemes and `rel`, rejection of images and unknown nodes/marks, the video allow-list, excerpts and reading time. |
| `test_telemetry.py` | Scrubbing (sensitive keys dropped; emails, JWTs and bearer tokens masked) and logs carrying the current trace and span id. |
| `test_helpers.py` | Slugs (unicode, emoji, length), keyset cursors (round trip, garbage gives 400), Argon2 hashing, JWTs (expired, wrong type and forged tokens are rejected), opaque-token hashing, and request validation (usernames, weak passwords, tag normalisation, date order, coordinates, blank comments). |

## Integration tests

`be/tests/integration/`, run with `make test-integration`.

Real HTTP requests go through the full FastAPI app (routers, dependencies, services and SQLAlchemy) into a **real Postgres 18**, the same engine production uses:
- **Locally:** testcontainers starts a throwaway `postgres:18-alpine` container.
- **In CI:** a GitHub Actions service container, passed in via `TEST_DATABASE_URL`.

The schema is created by running the real Alembic migrations, not `create_all`. Every test starts with empty tables, because `conftest.py` truncates them afterwards.

| File | What it proves |
| --- | --- |
| `test_auth.py` | Sign-up and duplicate detection, the CSRF header requirement, wrong passwords and the 10-attempt lockout, refresh-token rotation with its reuse grace window, logout revoking the session, profile and password changes, account deletion. |
| `test_journals.py` | Draft lifecycle and slugs, optimistic concurrency (409), rejected images, publish validation, slugs frozen after publish, ownership checks, **the full visibility matrix** (public, followers, unlisted with and without token, private) for visitors, followers, strangers and owners, share-token rotation, unpublish and delete, and Open Graph HTML escaping. |
| `test_social.py` | Follows and counters, notifications (incl. like coalescing), likes and bookmarks, comments with replies and cascading deletes, the home feed, Explore pagination and filters, and deleted authors disappearing. |
| `test_telemetry.py` | The publish journey's spans (route templates, journey tags, SQL and render children), metrics (per-step counts, latency exemplars, published-by-visibility) and logs all share each request's trace id. Failed steps (409, 422, 500) are counted and logged; a 500 records the exception type but not its message. **Privacy:** after the whole journey, login and refresh, no password, email, username, token, cookie, title, text or slug appears in any exported signal. |
| `test_migrations.py` | Migrations run upgrade → downgrade → upgrade on an **empty** database, and `alembic check` finds no drift between the migrations and the models. |

This layer catches what unit tests can't, because only Postgres behaves like Postgres:
- constraints and generated columns (`search_vector`);
- `citext` case-insensitivity;
- `ON CONFLICT` upserts;
- row locks (`FOR UPDATE`) in token rotation and autosave;
- migration mistakes.

## End-to-end tests

`e2e/` (a separate npm project), run with `make e2e`, or `make e2e-run` against a stack you already started with `RATE_LIMIT_ENABLED=false docker compose up -d`.

These are the only tests that exercise the **real, containerised stack**: a browser talking to the Vite dev server, which proxies `/api` to the FastAPI container, which uses the Postgres container. They catch wiring problems none of the other layers can see:
- a broken proxy;
- a missing environment variable;
- cookies not surviving a reload;
- CORS or CSRF behaving differently over real HTTP;
- a migration that doesn't run in the container.

| Spec | Scenario |
| --- | --- |
| `smoke.spec.ts` | API health and readiness through the proxy, home page (also on a Pixel 7 viewport), 404 page, problem+json errors, link-preview HTML. |
| `auth.spec.ts` | Sign up in the UI → land in the editor → session survives a reload → log out → members-only route redirects → wrong password error → log in. Duplicate username shows a field error. |
| `journal.spec.ts` | Type in the TipTap editor with formatting → autosave → reload keeps the content → publish → a **logged-out** visitor reads it and finds it on Explore. Publishing an empty draft explains what's missing. |
| `sharing.spec.ts` | Unlisted: hidden without the token, readable with the share-modal link, never on Explore. Private: other users get 404 even with the token. Link previews show the title. |
| `social.spec.ts` | Followers-only journal hidden until the reader follows, then it appears in their home feed. Like and comment persist across a reload, and the author gets follow, like and comment notifications. |

Design notes:
- **Isolation without resets.** Every test signs up its own uniquely named users (`uniqueName()`), so the suite runs in parallel (4 workers) against a shared, never-reset database, including your local one.
- **Fast setup, real UI where it matters.** Tests that aren't about sign-up create users and journals through the API (`signUpViaApi`, `publishJournal`) using the page's own request context, so the refresh cookie lands in the browser and the page is logged in.
- **Rate limits.** Sign-up is limited to 3 per hour per IP in production, so the e2e stack runs with `RATE_LIMIT_ENABLED=false`. That setting is never used in production.
- **Stability check.** The suite passed 42 of 42 runs with `--repeat-each=3` before it was committed. CI retries a failed test once and uploads the HTML report and traces.
- **It already found a bug.** Under parallel load, the profile's Follow button sometimes kept its loading spinner after the follow had succeeded (4 of 12 runs). Follow and Following were the same antd button with changing props, so the old spinner's exit animation lingered. Giving each state its own `key` fixed it (12 of 12 runs).

## On-call agent

`oncall-agent/tests`, run with `make test-oncall-agent` (12 tests, also a CI job). They use fake Prometheus, Loki and Tempo and a stand-in for the coding agent, and cover incident creation, evidence collection, deduplication and resolution, test alerts, backends being down, and the locked-down agent command. The end-to-end drill with real Claude Code is described in [`on-call-agent.md`](on-call-agent.md#10-testing).

## Observability check

`make obs-verify` (after `make obs-up`) runs the journey against the real stack. It then queries Tempo, Loki and Prometheus to check that each step stored a trace, logs and metrics with matching trace ids, and that none of the user's secrets reached storage. See [`observability.md`](observability.md).

## Why four layers

- **The unit suites** are fast and precise, but each only proves its own half works in isolation. A mocked API can drift from what the backend really returns, and pure functions never touch a database.
- **Integration** closes the database gap cheaply. It uses real Postgres, migrations, locking and constraints, without paying for a browser or containers.
- **End-to-end** is slower and coarser, but it's the only layer that runs the actual containers, proxy, cookies and browser.

Rule of thumb: test at the **lowest** layer that can prove the behaviour.
- Pure logic → unit.
- Anything depending on the database or on HTTP semantics (permissions, status codes) → integration.
- Full user journeys and wiring → e2e.

## What CI runs

```
backend (lint + unit) ──┬──> integration (Postgres service)
                        └──┐
frontend (lint + unit + build) ──> e2e (docker compose + Playwright)
                                       │
             integration + e2e pass ───┴──> build images ──> deploy (main only)
```

## Not covered yet (future work)

- **Production smoke tests:** e2e runs against the dev stack, not the deployed site. The deploy job only checks `/api/ready` on the live URL.
- **Visual regression and cross-browser testing:** e2e uses Chromium only.
- **Automated accessibility checks** (e.g. axe).
- **Load and performance testing.**
- **Concurrency under real load:** the code uses row locks for token rotation and autosave, but nothing stress-tests them.
- **Upgrading a populated database:** the migration test runs on an empty database only.
