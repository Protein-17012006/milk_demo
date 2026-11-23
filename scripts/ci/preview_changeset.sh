#!/usr/bin/env bash
# Shows what a template change would do to a stack, without changing anything: creates a
# change set, writes its changes to the job summary, then deletes it.
#
#   scripts/ci/preview_changeset.sh <stack> <template> [KEY=VALUE...]
set -euo pipefail
cd "$(dirname "$0")/../.."
# shellcheck source=scripts/ci/lib.sh
source scripts/ci/lib.sh

STACK="$1" TEMPLATE="$2"
shift 2
params=$(printf '%s\n' "$@" | jq -R 'capture("^(?<ParameterKey>[^=]+)=(?<ParameterValue>.*)$")' | jq -cs .)

status=$(stack_status "$STACK")
type=UPDATE
if [ "$status" = NONE ] || [ "$status" = REVIEW_IN_PROGRESS ]; then type=CREATE; fi
name="preview-$(date +%s)"
log "change set $name ($type) for $STACK from $TEMPLATE"
aws cloudformation create-change-set --stack-name "$STACK" --change-set-name "$name" --change-set-type "$type" \
  --template-body "file://$TEMPLATE" --parameters "$params" --capabilities CAPABILITY_IAM >/dev/null

cleanup() {
  aws cloudformation delete-change-set --stack-name "$STACK" --change-set-name "$name" >/dev/null 2>&1 || true
  # A CREATE change set leaves an empty stack in REVIEW_IN_PROGRESS; remove it again.
  if [ "$type" = CREATE ]; then aws cloudformation delete-stack --stack-name "$STACK" >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT

if ! aws cloudformation wait change-set-create-complete --stack-name "$STACK" --change-set-name "$name" 2>/dev/null; then
  reason=$(aws cloudformation describe-change-set --stack-name "$STACK" --change-set-name "$name" --query StatusReason --output text)
  if [[ "$reason" == *"didn't contain changes"* || "$reason" == *"No updates"* ]]; then
    summary "### Change set for \`$STACK\`: no changes"
    log "no changes"
    exit 0
  fi
  fail "change set failed: $reason"
fi

summary "### Change set for \`$STACK\` ($type)"
summary ""
summary "| Action | Resource | Type | Replacement |"
summary "|---|---|---|---|"
aws cloudformation describe-change-set --stack-name "$STACK" --change-set-name "$name" \
  --query 'Changes[].ResourceChange.[Action, LogicalResourceId, ResourceType, Replacement]' --output text |
  while read -r action resource rtype replacement; do
    log "$action $resource $rtype replacement=$replacement"
    summary "| $action | $resource | $rtype | $replacement |"
  done
