#!/usr/bin/env bash
# Shared helpers for the scripts in scripts/ci. Source it; do not run it.
# shellcheck disable=SC2034 # variables here are used by the scripts that source this file

export AWS_REGION="${AWS_REGION:-ap-southeast-1}"
export AWS_DEFAULT_REGION="$AWS_REGION"
export AWS_PAGER=""
PLATFORM_STACK="milk-platform"
ECR_REPOSITORY="milk"
ENVIRONMENTS=(development test staging production)

log() { printf '[%s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
step() { log "== step $1: $2"; }
warn() { echo "::warning::$*"; }
fail() {
  echo "::error::$*"
  exit 1
}

# Hide a value in every later log line of the job (no-op outside GitHub Actions).
mask() { if [ -n "${GITHUB_ACTIONS:-}" ] && [ -n "$1" ]; then echo "::add-mask::$1"; fi; }

summary() { if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then printf '%s\n' "$*" >>"$GITHUB_STEP_SUMMARY"; fi; }
output() { if [ -n "${GITHUB_OUTPUT:-}" ]; then printf '%s=%s\n' "$1" "$2" >>"$GITHUB_OUTPUT"; fi; }

stack_status() {
  aws cloudformation describe-stacks --stack-name "$1" --query 'Stacks[0].StackStatus' --output text 2>/dev/null ||
    echo NONE
}

stack_output() { # stack_output STACK KEY
  aws cloudformation describe-stacks --stack-name "$1" \
    --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue" --output text
}

stack_parameter() { # stack_parameter STACK KEY
  aws cloudformation describe-stacks --stack-name "$1" \
    --query "Stacks[0].Parameters[?ParameterKey=='$2'].ParameterValue" --output text
}

# The newest failed events of a stack, so a failed deployment says why in the job log.
stack_failures() {
  aws cloudformation describe-stack-events --stack-name "$1" --max-items 40 \
    --query "StackEvents[?contains(ResourceStatus, 'FAILED')].[Timestamp, LogicalResourceId, ResourceStatus, ResourceStatusReason]" \
    --output text 2>/dev/null | head -15 || true
}

env_port() { jq -r .Port "infra/params/$1.json"; }
env_cluster() { echo "milk-$(jq -r .ClusterKind "infra/params/$1.json")"; }

env_url() { # env_url ENV ALB_DNS
  local port
  port=$(env_port "$1")
  if [ "$port" = "80" ]; then echo "http://$2"; else echo "http://$2:$port"; fi
}

# The image tag a service's current task definition runs, or "-" if it does not exist.
service_tag() { # service_tag CLUSTER SERVICE
  local taskdef image
  taskdef=$(aws ecs describe-services --cluster "$1" --services "$2" \
    --query "services[?status=='ACTIVE'].taskDefinition | [0]" --output text 2>/dev/null || true)
  if [ -z "$taskdef" ] || [ "$taskdef" = "None" ]; then
    echo "-"
    return
  fi
  image=$(aws ecs describe-task-definition --task-definition "$taskdef" \
    --query 'taskDefinition.containerDefinitions[0].image' --output text)
  echo "${image##*:}"
}
