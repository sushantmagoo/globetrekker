# Globetrekker — Release process

How a change ships, day to day. For how the pipeline is built and why, see
[`deployment.md`](deployment.md). For the test layers, see [`testing.md`](testing.md).

## The short version

- `main` is always deployable. Work happens on short-lived branches (`<issue>-short-name`) and lands through pull requests.
- Every merge to `main` that passes all tests is released automatically to production.
- A release **is** a commit SHA. The same SHA tags both images in ECR and the release bundle in S3, and names the release folder on the server.
- Rolling back means redeploying an earlier SHA. No rebuild is needed, and it takes about a minute.

There's no staging environment and no version numbers yet. That's the right amount of process for one instance and one team. A staging stack is the natural next step once there are real users.

## What runs when

**`ci-cd.yml`**

| Trigger | Jobs |
| --- | --- |
| Pull request to `main` | `backend` and `frontend` (in parallel) → `integration` and `e2e`. **No images, no deploy.** |
| Push to `main` (a merge) | All of the above → `images` (push to ECR) → `deploy` (SSM to EC2) |
| Manual run on `main`, no input | Same as a push: re-test, rebuild and redeploy the current commit |
| Manual run on `main` with `release_sha` | **Rollback:** skips tests and builds, redeploys that earlier release |

**`infra.yml`**

| Trigger | Jobs |
| --- | --- |
| Pull request touching `infra/` | `validate` (cfn-lint) |
| Push to `main` touching `infra/`, or a manual run | `validate` → `deploy` (CloudFormation + Parameter Store) in the `infrastructure` environment |

Ordering:
- The cheap jobs gate the expensive ones: integration waits for backend lint and unit tests, and e2e waits for both unit suites.
- Nothing is built or deployed unless **every** test layer passed.
- A new push to a PR cancels that PR's older run. Runs on `main` are never cancelled midway.

## Shipping a change

1. **Branch from `main`.** Write code and tests. Locally: `make lint test test-integration`, plus `make e2e` for user-facing flows.
2. **Open a PR** that references the issue (`Closes #12`). CI runs all four test layers.
3. **Review.** QA verifies the acceptance criteria (see [`qa.md`](qa.md)).
4. **Merge.** The push to `main` builds the images and deploys. Watch it in **Actions → CI/CD**. The deploy job prints the instance's own deploy log and a summary with the released SHA.

**Recommended GitHub settings** (Settings → Branches → `main`):
- Require a pull request before merging.
- Require these status checks: `Backend lint + unit tests`, `Frontend lint + unit tests + build`, `Backend integration tests (Postgres)` and `End-to-end tests (Playwright)`.
- Optional: add required reviewers to the `production` environment if you want to press "Approve" before each release goes out.

## Database migrations

Migrations ship with the code. The `migrate` service runs `alembic upgrade head` before the new
backend starts, and the deploy fails (then rolls back) if it errors. Because rollbacks don't undo
migrations, every migration must be **backward compatible with the previous release**:
- **Adding** tables, columns with defaults, or indexes: fine in one release.
- **Renaming or removing** something takes two releases. First ship code that stops using it, then ship the migration that drops it.
- **Long-running migrations** (big backfills or index builds on large tables) should be run deliberately, not inside a routine deploy.

The `test_migrations.py` integration test checks that every migration upgrades, downgrades and matches the models.

## When a deploy fails

The `deploy` job fails loudly. The server side restores the previous release by itself before reporting failure, so a failed deploy normally leaves the site running the last good version.

| Failing step | Meaning | What to do |
| --- | --- | --- |
| **Read stack outputs** | The `globetrekker-app` stack doesn't exist yet, or the role can't read it | Run the Infrastructure workflow first (`deployment.md`, one-time setup) |
| **Build and push images** | Docker build failed, or ECR login failed | Read the build log. Check `AWS_DEPLOY_ROLE_ARN` is set |
| **Deploy via SSM Run Command** | The script failed on the instance: image pull, migration or health check. The job prints the instance's log, including the backend and migrate logs | Fix forward (below). The previous release is already running again |
| **Public health check** | The instance is healthy but `APP_URL` isn't reachable | Usually DNS or the certificate (Caddy logs), or a security group change |

## Rolling back

1. **Instant rollback (default for incidents).** Go to **Actions → CI/CD → Run workflow**, branch `main`, and set `release_sha` to the last good commit. That's the SHA in `/opt/globetrekker/CURRENT_RELEASE` before the bad deploy, or in the summary of the last green deploy run. This redeploys the exact images and bundle of that release, without rebuilding or re-testing.
2. **Then fix forward.** `git revert` the bad commit (or fix it) in a PR and merge. The next normal deploy makes `main` and production agree again. Until then, the next merge to `main` will redeploy whatever `main` contains.

Releases older than 180 days (bundles) or beyond the newest 30 images can no longer be rolled back to.

## Infrastructure changes

1. Edit `infra/cloudformation/app.yaml` in a PR. CI runs cfn-lint. Say in the PR description which resources change, and whether any of them is **replaced** (instance, volume, Elastic IP).
2. Merge. `infra.yml` deploys the change in the `infrastructure` environment, after approval if reviewers are configured.
3. **Watch out for replacements.**
   - Changing `InstanceType` stops and starts the instance (a short outage).
   - Changing the AMI parameter or `UserData` **replaces** the instance. The data volume is kept and re-attached, so Postgres data survives, but run the CI/CD workflow afterwards to put the app back on the new instance.
   - Never change `DataVolume` properties that force a replacement without a backup.

`bootstrap.yaml` is changed rarely and only by hand with admin credentials (`deployment.md`, step 1).

## Rotating secrets

- **`JWT_SECRET`:**
  1. `aws ssm put-parameter --name /globetrekker/prod/JWT_SECRET --type SecureString --overwrite --value "$(openssl rand -hex 32)"`
  2. Redeploy the current release (CI/CD → Run workflow with its SHA).

  All users are logged out.
- **`POSTGRES_PASSWORD`:**
  1. Change the password inside Postgres first: `ALTER USER globetrekker PASSWORD '…'` on the instance.
  2. Update the parameter with the same value.
  3. Redeploy.

  Doing it in the other order locks the app out of its database.

## Versioning

There are no semantic versions. The commit SHA is the release identifier everywhere: ECR tags, the S3 bundle, the release folder on the server, and the deploy summary. If the project later needs human-friendly versions (a changelog, app-store builds), add a tagging step to the deploy job that tags the deployed SHA, rather than inventing a separate version scheme.
