#!/usr/bin/env bash
# Smoke test after a deployment: the service is stable, every running task runs the new tag,
# and /healthz behind the load balancer answers ok with that tag.
#
#   scripts/ci/smoke_test.sh <cluster> <service> <tag> <url>
set -euo pipefail
cd "$(dirname "$0")/../.."
# shellcheck source=scripts/ci/lib.sh
source scripts/ci/lib.sh

CLUSTER="$1" SERVICE="$2" TAG="$3" URL="$4"

log "waiting for $SERVICE to be stable"
aws ecs wait services-stable --cluster "$CLUSTER" --services "$SERVICE" || fail "$SERVICE did not become stable"

mapfile -t tasks < <(aws ecs list-tasks --cluster "$CLUSTER" --service-name "$SERVICE" --desired-status RUNNING \
  --query 'taskArns[]' --output text | tr '\t' '\n' | sed '/^$/d')
[ "${#tasks[@]}" -gt 0 ] || fail "$SERVICE has no running task"
mapfile -t images < <(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "${tasks[@]}" \
  --query "tasks[].containers[?name=='app'].image[]" --output text | tr '\t' '\n' | sed '/^$/d')
for image in "${images[@]}"; do
  [ "${image##*:}" = "$TAG" ] || fail "a running task uses $image, not $TAG"
done
log "${#tasks[@]} running task(s), all on $TAG"

for attempt in $(seq 1 12); do
  body=$(curl -fsS --max-time 5 "$URL/healthz" 2>/dev/null || true)
  if [ "$(jq -r '.ok // false' <<<"$body" 2>/dev/null)" = true ]; then
    served=$(jq -r .version <<<"$body")
    if [ "$served" = "$TAG" ]; then
      log "$URL/healthz answers ok, version $served"
      exit 0
    fi
    log "attempt $attempt: load balancer still reaches version $served"
  else
    log "attempt $attempt: no healthy answer yet"
  fi
  sleep 5
done
fail "$URL/healthz did not answer ok with version $TAG within 60 s"
