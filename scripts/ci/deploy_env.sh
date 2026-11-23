#!/usr/bin/env bash
# Deploys ONE environment with ONE image tag. Run by .github/workflows/deploy.yml, never by hand.
#
#   scripts/ci/deploy_env.sh <development|test|staging|production> <image_tag>
#   ROLLBACK=true  redeploys an earlier tag: skips the end-to-end test
#
# Order (the same in every environment):
#    1. preflight       the image exists in ECR; read the platform's outputs
#    2. infrastructure  update stack milk-<env> with the current template; the running hub
#                       keeps its image (first deployment: create it with no task running)
#    3. secret          add the session secret and worker token to milk/<env>/app if missing
#    4. start service   desired count 0 -> 1 if it was stopped to save money
#    5. load test       start 20 Locust users in the background (staging, production)
#    6. application     update the stack with the new image: ECS rolling update, circuit
#                       breaker rolls back and fails the step if the new task never gets healthy
#    7. smoke test      service stable, every task runs the new tag, /healthz answers ok + tag
#    8. load verdict    any failed request or no requests fails; p95 > 2 s warns (staging,
#                       production; production keeps the load on for at least 5 minutes)
#    9. follow-up       test: end-to-end check as a one-off task, waited for (<= 15 min)
#   10. report          environment URL; production also writes the parity table
set -euo pipefail
cd "$(dirname "$0")/../.."
# shellcheck source=scripts/ci/lib.sh
source scripts/ci/lib.sh

ENV_NAME="${1:?usage: deploy_env.sh <environment> <image_tag>}"
TAG="${2:?usage: deploy_env.sh <environment> <image_tag>}"
ROLLBACK="${ROLLBACK:-false}"
case "$ENV_NAME" in development | test | staging | production) ;; *) fail "unknown environment $ENV_NAME" ;; esac
[[ "$TAG" =~ ^[0-9a-f]{7,40}$ ]] || fail "image tag must be a commit hash, got '$TAG'"

STACK="milk-$ENV_NAME"
PARAMS_FILE="infra/params/$ENV_NAME.json"
LOAD_TEST=false
case "$ENV_NAME" in staging | production) LOAD_TEST=true ;; esac
MIN_LOAD_SECONDS=0
[ "$ENV_NAME" = production ] && MIN_LOAD_SECONDS=300
mapfile -t BASE_PARAMS < <(jq -r 'to_entries[] | "\(.key)=\(.value)"' "$PARAMS_FILE")

cleanup() {
  local code=$?
  if [ "$code" -ne 0 ] && [ "$LOAD_TEST" = true ]; then scripts/ci/load_test.sh abort || true; fi
  exit "$code"
}
trap cleanup EXIT

deploy_stack() { # deploy_stack KEY=VALUE...
  if ! aws cloudformation deploy \
    --stack-name "$STACK" \
    --template-file infra/app.yml \
    --capabilities CAPABILITY_IAM \
    --no-fail-on-empty-changeset \
    --tags project=milk "environment=$ENV_NAME" \
    --parameter-overrides "${BASE_PARAMS[@]}" "$@"; then
    log "stack $STACK failed; newest failed events:"
    stack_failures "$STACK"
    fail "CloudFormation could not update $STACK"
  fi
}

log "deploying $TAG to $ENV_NAME (rollback=$ROLLBACK)"

# 1 ---------------------------------------------------------------------------------------------
step 1 "preflight"
aws ecr describe-images --repository-name "$ECR_REPOSITORY" --image-ids "imageTag=$TAG" >/dev/null 2>&1 ||
  fail "image $ECR_REPOSITORY:$TAG is not in ECR"
[ "$(stack_status "$PLATFORM_STACK")" != NONE ] ||
  fail "stack $PLATFORM_STACK does not exist; run the Infrastructure workflow first (docs/runbook.md)"
ALB_DNS=$(stack_output "$PLATFORM_STACK" AlbDns)
SUBNETS=$(stack_output "$PLATFORM_STACK" Subnets)
TASK_SG=$(stack_output "$PLATFORM_STACK" TaskSecurityGroup)
URL=$(env_url "$ENV_NAME" "$ALB_DNS")
output url "$URL"
log "image found; environment URL $URL"

# 2 ---------------------------------------------------------------------------------------------
step 2 "infrastructure (current template, running image kept)"
FIRST=false
status=$(stack_status "$STACK")
case "$status" in
  ROLLBACK_COMPLETE)
    log "$STACK is left over from a failed first deployment; deleting it"
    aws cloudformation delete-stack --stack-name "$STACK"
    aws cloudformation wait stack-delete-complete --stack-name "$STACK"
    status=NONE
    ;;
  *_IN_PROGRESS) fail "$STACK is busy ($status); wait for it to finish and run the job again" ;;
  UPDATE_ROLLBACK_FAILED | DELETE_FAILED) fail "$STACK is in $status and needs a person (docs/runbook.md)" ;;
esac
if [ "$status" = NONE ]; then
  FIRST=true
  log "creating $STACK with $TAG and no running task"
  deploy_stack "ImageTag=$TAG" DesiredCount=0
else
  RUNNING_TAG=$(stack_parameter "$STACK" ImageTag)
  log "updating $STACK infrastructure; the hub stays on $RUNNING_TAG"
  deploy_stack "ImageTag=$RUNNING_TAG" DesiredCount=1
fi
CLUSTER=$(stack_output "$STACK" Cluster)
SERVICE=$(stack_output "$STACK" ServiceName)
SECRET_ARN=$(stack_output "$STACK" SecretArn)

# 3 ---------------------------------------------------------------------------------------------
step 3 "secret milk/$ENV_NAME/app"
secret_json=$(aws secretsmanager get-secret-value --secret-id "$SECRET_ARN" --query SecretString --output text)
for key in web_password web_secret internal_token; do mask "$(jq -r --arg k "$key" '.[$k] // empty' <<<"$secret_json")"; done
added=()
for key in web_secret internal_token; do
  if [ -z "$(jq -r --arg k "$key" '.[$k] // empty' <<<"$secret_json")" ]; then
    value=$(openssl rand -hex 32)
    mask "$value"
    secret_json=$(jq --arg k "$key" --arg v "$value" '.[$k] = $v' <<<"$secret_json")
    added+=("$key")
  fi
done
if [ "${#added[@]}" -gt 0 ]; then
  tmp=$(mktemp)
  chmod 600 "$tmp"
  printf '%s' "$secret_json" >"$tmp"
  aws secretsmanager put-secret-value --secret-id "$SECRET_ARN" --secret-string "file://$tmp" >/dev/null
  rm -f "$tmp"
  log "added ${added[*]} to the secret"
else
  log "secret complete"
fi
WEB_PASSWORD=$(jq -r .web_password <<<"$secret_json")
unset secret_json

# 4 ---------------------------------------------------------------------------------------------
step 4 "start the service if it was stopped"
desired=$(aws ecs describe-services --cluster "$CLUSTER" --services "$SERVICE" --query 'services[0].desiredCount' --output text)
if [ "$FIRST" = true ]; then
  log "first deployment: step 6 starts the first task"
elif [ "$desired" = 0 ]; then
  log "service was stopped; starting one task on the current image"
  aws ecs update-service --cluster "$CLUSTER" --service "$SERVICE" --desired-count 1 >/dev/null
  aws ecs wait services-stable --cluster "$CLUSTER" --services "$SERVICE"
else
  log "service running ($desired task)"
fi

# 5 ---------------------------------------------------------------------------------------------
if [ "$LOAD_TEST" = true ] && [ "$FIRST" = false ]; then
  step 5 "start the load test"
  LOCUST_WEB_PASSWORD="$WEB_PASSWORD" scripts/ci/load_test.sh start "$ENV_NAME" "$URL"
else
  step 5 "load test: not in $ENV_NAME$([ "$FIRST" = true ] && echo ' before the first task exists')"
fi

# 6 ---------------------------------------------------------------------------------------------
step 6 "application: rolling update to $TAG"
deploy_stack "ImageTag=$TAG" DesiredCount=1
log "stack updated; ECS reports the service stable on $TAG"
if [ "$LOAD_TEST" = true ] && [ "$FIRST" = true ]; then
  log "first deployment: starting the load test now that a task answers"
  LOCUST_WEB_PASSWORD="$WEB_PASSWORD" scripts/ci/load_test.sh start "$ENV_NAME" "$URL"
fi
unset WEB_PASSWORD

# 7 ---------------------------------------------------------------------------------------------
step 7 "smoke test"
scripts/ci/smoke_test.sh "$CLUSTER" "$SERVICE" "$TAG" "$URL"

# 8 ---------------------------------------------------------------------------------------------
if [ "$LOAD_TEST" = true ]; then
  step 8 "load-test verdict"
  scripts/ci/load_test.sh stop "$ENV_NAME" "$TAG" "$MIN_LOAD_SECONDS"
else
  step 8 "load-test verdict: not in $ENV_NAME"
fi

# 9 ---------------------------------------------------------------------------------------------
if [ "$ENV_NAME" = test ] && [ "$ROLLBACK" != true ]; then
  step 9 "end-to-end check (one-off task, waited for)"
  scripts/ci/run_task.sh "$ENV_NAME" "$CLUSTER" "milk-$ENV_NAME-job" "$SUBNETS" "$TASK_SG" 900 python -m milk.selfcheck
else
  step 9 "follow-up task: none in $ENV_NAME$([ "$ROLLBACK" = true ] && echo ' (rollback)')"
fi

# 10 --------------------------------------------------------------------------------------------
step 10 "report"
summary "### ${ENV_NAME}: \`$TAG\`$([ "$ROLLBACK" = true ] && echo ' (rollback)')"
summary ""
summary "- URL: $URL"
summary "- Service: \`$CLUSTER/$SERVICE\`"
if [ "$ENV_NAME" = production ]; then scripts/ci/parity_table.sh "$TAG"; fi
log "$ENV_NAME runs $TAG at $URL"
