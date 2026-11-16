#!/usr/bin/env bash
# Runs ON the EC2 instance (via SSM Run Command from .github/workflows/ci-cd.yml).
#
# The release bundle (docker-compose files, Caddyfile, this script) has already been
# extracted to /opt/globetrekker/releases/<sha>. This script:
#   1. writes the release's .env from SSM Parameter Store (secrets never touch GitHub logs),
#   2. pulls the backend/frontend images CI built and tested for <sha> from ECR,
#   3. starts the stack (migrations run first, via the `migrate` service),
#   4. waits for the backend to report healthy,
#   5. on success points /opt/globetrekker/current at this release;
#      on failure restarts the previous release and exits non-zero.
#
# Usage: remote-deploy.sh <release-sha>
# Env:   AWS_REGION, ECR_REGISTRY (required), SSM_PREFIX (default /globetrekker/prod)
set -euo pipefail

SHA="${1:?usage: remote-deploy.sh <release-sha>}"
: "${AWS_REGION:?AWS_REGION is required}"
: "${ECR_REGISTRY:?ECR_REGISTRY is required}"
SSM_PREFIX="${SSM_PREFIX:-/globetrekker/prod}"

APP_DIR="${APP_DIR:-/opt/globetrekker}"
RELEASE_DIR="$APP_DIR/releases/$SHA"
CURRENT_LINK="$APP_DIR/current"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-300}"

log() { printf '[deploy %s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }

compose() {
  docker compose --env-file "$1/.env" -f "$1/docker-compose.yml" -f "$1/docker-compose.prod.yml" "${@:2}"
}

write_env() {
  local dir="$1" sha="$2"
  log "Writing $dir/.env from SSM ($SSM_PREFIX)"
  umask 077
  {
    aws ssm get-parameters-by-path --region "$AWS_REGION" --path "$SSM_PREFIX" \
      --with-decryption --query 'Parameters[*].[Name,Value]' --output text |
      while IFS=$'\t' read -r name value; do
        printf '%s=%s\n' "${name##*/}" "$value"
      done
    printf 'BACKEND_IMAGE=%s/globetrekker-backend:%s\n' "$ECR_REGISTRY" "$sha"
    printf 'FRONTEND_IMAGE=%s/globetrekker-frontend:%s\n' "$ECR_REGISTRY" "$sha"
  } >"$dir/.env"
  for required in POSTGRES_PASSWORD JWT_SECRET ACME_EMAIL; do
    grep -q "^${required}=" "$dir/.env" || { log "Missing SSM parameter $SSM_PREFIX/$required"; exit 1; }
  done
}

wait_healthy() {
  local dir="$1" deadline=$((SECONDS + HEALTH_TIMEOUT)) id status
  while ((SECONDS < deadline)); do
    id="$(compose "$dir" ps -q backend || true)"
    status="$( [ -n "$id" ] && docker inspect --format '{{.State.Health.Status}}' "$id" 2>/dev/null || echo starting)"
    if [ "$status" = "healthy" ]; then
      # Migrations must have finished cleanly too.
      local migrate_id
      migrate_id="$(compose "$dir" ps -a -q migrate || true)"
      if [ -n "$migrate_id" ] && [ "$(docker inspect --format '{{.State.ExitCode}}' "$migrate_id")" != "0" ]; then
        log "Migrations failed"
        return 1
      fi
      return 0
    fi
    sleep 5
  done
  log "Backend not healthy after ${HEALTH_TIMEOUT}s (last status: $status)"
  return 1
}

[ -d "$RELEASE_DIR" ] || { log "Release dir $RELEASE_DIR not found"; exit 1; }
PREVIOUS_DIR="$(readlink -f "$CURRENT_LINK" 2>/dev/null || true)"

write_env "$RELEASE_DIR" "$SHA"

log "Logging in to ECR $ECR_REGISTRY"
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY" >/dev/null

log "Pulling images for $SHA"
compose "$RELEASE_DIR" pull --quiet

log "Starting release $SHA"
if compose "$RELEASE_DIR" up -d --no-build --remove-orphans && wait_healthy "$RELEASE_DIR"; then
  ln -sfn "$RELEASE_DIR" "$CURRENT_LINK"
  echo "$SHA" >"$APP_DIR/CURRENT_RELEASE"
  log "Release $SHA is live"
  # Keep the 5 newest releases on disk for quick manual rollbacks; drop unused image layers.
  # shellcheck disable=SC2012  # release dirs are commit SHAs, so plain `ls` is safe here
  ls -1dt "$APP_DIR"/releases/*/ | tail -n +6 | xargs rm -rf
  docker image prune -f >/dev/null
  exit 0
fi

log "Release $SHA FAILED. Recent logs:"
compose "$RELEASE_DIR" logs --no-color --tail 80 migrate backend || true

if [ -n "$PREVIOUS_DIR" ] && [ "$PREVIOUS_DIR" != "$RELEASE_DIR" ] && [ -d "$PREVIOUS_DIR" ]; then
  log "Rolling back to $(basename "$PREVIOUS_DIR")"
  compose "$PREVIOUS_DIR" up -d --no-build --remove-orphans && wait_healthy "$PREVIOUS_DIR" &&
    log "Previous release restored"
fi
exit 1
