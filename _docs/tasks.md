# Globetrekker — Tasks

A running TODO list of improvements beyond the current MVP. See `spec.md` for the design and §9 for what's built.
Check items off as they land.

## Infrastructure

- [ ] **Email service.** Add an SMTP provider (e.g. Postmark, SES, Resend) and set up SPF, DKIM and DMARC for `globetrekker.me`. This unlocks:
  - [ ] Email verification on sign-up
  - [ ] "Forgot password" / reset by email
  - [ ] Notification digests (opt-in)
- [ ] **Object storage (S3 / R2 / MinIO).** Needed before any uploads:
  - [ ] Photo uploads in journals (presigned uploads, resized WebP variants, EXIF GPS stripping)
  - [ ] Cover images for journals and trips
  - [ ] Profile avatars (replace initials)
  - [ ] Per-journal Open Graph images for link previews
- [ ] **Caching (Redis).**
  - [ ] Shared rate limiting across workers (limits are currently per process)
  - [ ] Cache Explore/trending and popular tags
  - [ ] Background job queue (e.g. `arq`) instead of in-process tasks
- [ ] **Backups.** Nightly `pg_dump` to off-site storage, plus a monthly restore test.
- [ ] **Monitoring.** Error tracking (Sentry), uptime checks, and basic metrics and dashboards. *Partly done:* OpenTelemetry metrics, traces and logs with a local Grafana stack for the publish journey (`observability.md`). A user-impact alert and an on-call agent are done (`on-call-agent.md`). Still needed: human paging, browser tracing and uptime checks.
- [x] **CI/CD.** GitHub Actions to lint, test and build images, then deploy to the server. (#6, done: `ci-cd.yml`, `infra.yml`, see `deployment.md`; first real AWS run still pending)
- [ ] **Connection pooling.** Add PgBouncer once traffic grows.

## Features

- [ ] **Trips.** Group journals into a trip, with ordering and a trip page (the table already exists).
- [ ] **Search.** Full-text search for journals, and search for users and tags (`/search`).
- [ ] **Popular tags** endpoint and a tag cloud on Explore.
- [ ] **"Places visited" world map** on profiles.
- [ ] **Sitemap** (`sitemap.xml`) for SEO.
- [ ] **Reports and moderation.** Report journals, comments or users, plus admin tools to review reports and hide content or suspend users.
- [ ] **Social login** (Google, Apple).
- [ ] **Real-time notifications** (server-sent events instead of polling every 60 s).
- [ ] **Journal revision history.**
- [ ] **i18n.** Move UI strings to `react-i18next`.
- [ ] **PWA and offline drafts**, then native apps.

## Maintenance and housekeeping

- [ ] **Nightly job.** Recompute counters, permanently delete accounts that were deleted more than 30 days ago, and clean up expired refresh tokens.
- [x] **End-to-end tests** (Playwright) for the main path: sign up → write → publish → share → like and comment. (#20, done: `e2e/`, see `testing.md`)
- [ ] **Generated API types.** Switch from hand-written `fe/src/api/types.ts` to `openapi-typescript` once it supports TypeScript 7.
- [ ] **Reliable logout.** Use `fetch(..., { keepalive: true })` so logout still completes if the tab closes right after clicking.
- [x] **Separate image names for dev and prod Docker builds**, so the two don't overwrite each other on the same machine. (#23, done: `:dev` / `:prod` tags)
