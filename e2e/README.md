# End-to-end tests (Playwright)

Real browser → Vite dev server → FastAPI → Postgres, all running in Docker. The scenarios and design notes are in
[`_docs/testing.md`](../_docs/testing.md#end-to-end-tests).

```bash
make e2e-install                                   # once: npm ci + Chromium
RATE_LIMIT_ENABLED=false docker compose up -d --build
cd e2e && npx playwright test                      # or: make e2e
npx playwright test --headed tests/journal.spec.ts # watch one spec
npx playwright show-report                         # after a failure in CI (download the artifact)
```

`BASE_URL` overrides the target (default `http://localhost:5173`). Tests create their own uniquely
named users, so they can run in parallel against a database that isn't reset between runs.
