#!/usr/bin/env bash
# Runs a one-off ECS task from an environment's job task definition and waits for it.
#
#   scripts/ci/run_task.sh <env> <cluster> <family> <subnets,csv> <security_group> <timeout_s> [command...]
#
# Polls every 10 s. Once the task stops, prints its whole CloudWatch log stream
# (/milk/<env>, stream job/job/<task-id>) into the job log and exits with the container's
# exit code. A task still running after <timeout_s> (at most 30 min) is stopped and fails.
set -euo pipefail
cd "$(dirname "$0")/../.."
# shellcheck source=scripts/ci/lib.sh
source scripts/ci/lib.sh

ENV_NAME="$1" CLUSTER="$2" FAMILY="$3" SUBNETS="$4" SECURITY_GROUP="$5" TIMEOUT="$6"
shift 6
[ "$TIMEOUT" -le 1800 ] || TIMEOUT=1800
CONTAINER=job
LOG_GROUP="/milk/$ENV_NAME"

overrides='{}'
if [ "$#" -gt 0 ]; then
  # Arguments go in on stdin: jq would read one like "-m" as its own option.
  overrides=$(printf '%s\n' "$@" | jq -R . | jq -cs --arg name "$CONTAINER" '{containerOverrides: [{name: $name, command: .}]}')
fi

log "starting $FAMILY on $CLUSTER: ${*:-default command}"
result=$(aws ecs run-task \
  --cluster "$CLUSTER" \
  --task-definition "$FAMILY" \
  --launch-type FARGATE \
  --count 1 \
  --started-by github-actions \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SECURITY_GROUP],assignPublicIp=ENABLED}" \
  --overrides "$overrides" \
  --output json)
TASK_ARN=$(jq -r '.tasks[0].taskArn // empty' <<<"$result")
[ -n "$TASK_ARN" ] || fail "ECS did not start the task: $(jq -c .failures <<<"$result")"
TASK_ID="${TASK_ARN##*/}"
STREAM="$CONTAINER/$CONTAINER/$TASK_ID"
log "task $TASK_ID started; log stream $LOG_GROUP $STREAM"

print_log() {
  local token="" previous="" page
  log "----- log of task $TASK_ID -----"
  while :; do
    if [ -n "$token" ]; then
      page=$(aws logs get-log-events --log-group-name "$LOG_GROUP" --log-stream-name "$STREAM" \
        --start-from-head --next-token "$token" --output json 2>/dev/null) || break
    else
      page=$(aws logs get-log-events --log-group-name "$LOG_GROUP" --log-stream-name "$STREAM" \
        --start-from-head --output json 2>/dev/null) || {
        log "(no log stream: the container may not have started)"
        break
      }
    fi
    jq -r '.events[].message' <<<"$page"
    previous="$token"
    token=$(jq -r .nextForwardToken <<<"$page")
    [ "$token" != "$previous" ] || break
  done
  log "----- end of log -----"
}

started=$(date +%s)
status=PROVISIONING
while [ "$status" != STOPPED ]; do
  sleep 10
  status=$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$TASK_ARN" --query 'tasks[0].lastStatus' --output text)
  elapsed=$(($(date +%s) - started))
  if [ "$status" != STOPPED ] && [ "$elapsed" -ge "$TIMEOUT" ]; then
    log "task still $status after ${elapsed}s; stopping it"
    aws ecs stop-task --cluster "$CLUSTER" --task "$TASK_ARN" --reason "timeout in GitHub Actions" >/dev/null
    aws ecs wait tasks-stopped --cluster "$CLUSTER" --tasks "$TASK_ARN" || true
    print_log
    fail "task $TASK_ID ran longer than ${TIMEOUT}s"
  fi
done
sleep 5 # the last log lines reach CloudWatch a moment after the container stops
print_log

details=$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$TASK_ARN" --output json)
exit_code=$(jq -r --arg c "$CONTAINER" '.tasks[0].containers[] | select(.name == $c) | .exitCode // empty' <<<"$details")
if [ -z "$exit_code" ]; then
  fail "task $TASK_ID stopped without an exit code: $(jq -r '.tasks[0].stoppedReason' <<<"$details")"
fi
log "task $TASK_ID exited with $exit_code after $(($(date +%s) - started))s"
exit "$exit_code"
