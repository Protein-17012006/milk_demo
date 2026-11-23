#!/usr/bin/env bash
# One-time setup of the GitHub side of the pipeline. Run it from Git Bash or any bash, with
# the GitHub CLI logged in (gh auth login) as the person who will approve production.
#
#   scripts/ci/setup_github.sh            # reads ./cicd.env
#   CICD_ENV=../cicd.env scripts/ci/setup_github.sh
#
# cicd.env holds only what a person must supply (never commit it; see cicd.env.example):
#   AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY  access key of the IAM user the pipeline uses
#   GITHUB_REPO_URL                           https://github.com/<owner>/<repo> or git@github.com:<owner>/<repo>.git
# Everything else is derived:
#   AWS_ACCOUNT_ID  <- aws sts get-caller-identity (with the key above)
#   owner/repo      <- GITHUB_REPO_URL
#   PROD_REVIEWER   <- the logged-in GitHub user
#   ALERT_EMAIL     <- $ALERT_EMAIL, else git config user.email unless it is a GitHub noreply
#                      address (empty: a warning; set repo variable ALERT_EMAIL later)
#
# It sets:
#   repo secrets    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY (sent on stdin, never printed)
#   repo variables  AWS_ACCOUNT_ID, ALERT_EMAIL (if found)
#   branch main     protected: checks lint, test, cfn-lint, image required, branch up to date,
#                   no approving review required
#   environments    development, test, staging; production and platform with PROD_REVIEWER as
#                   required reviewer; test/staging/production/platform deploy only from main
# Safe to run again.
set -euo pipefail
cd "$(dirname "$0")/../.."

log() { printf '[setup] %s\n' "$*"; }
warn() { printf '[setup] WARNING: %s\n' "$*" >&2; }
fail() {
  printf '[setup] ERROR: %s\n' "$*" >&2
  exit 1
}

ENV_FILE="${CICD_ENV:-cicd.env}"
[ -f "$ENV_FILE" ] || fail "$ENV_FILE not found: copy cicd.env.example to cicd.env and fill in the three values"

read_value() { # the value of KEY in ENV_FILE, spaces and quotes trimmed; never sourced as code
  local line value
  line=$(grep -E "^[[:space:]]*$1[[:space:]]*=" "$ENV_FILE" | tail -n 1 || true)
  value="${line#*=}"
  value="${value%$'\r'}"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  value="${value#[\"\']}"
  value="${value%[\"\']}"
  printf '%s' "$value"
}

AWS_KEY_ID=$(read_value AWS_ACCESS_KEY_ID)
AWS_SECRET=$(read_value AWS_SECRET_ACCESS_KEY)
REPO_URL=$(read_value GITHUB_REPO_URL)
for name in AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY GITHUB_REPO_URL; do
  case "$name" in
    AWS_ACCESS_KEY_ID) value="$AWS_KEY_ID" ;;
    AWS_SECRET_ACCESS_KEY) value="$AWS_SECRET" ;;
    GITHUB_REPO_URL) value="$REPO_URL" ;;
  esac
  [ -n "$value" ] || fail "$name is empty in $ENV_FILE"
done
[[ "$AWS_KEY_ID" =~ ^(AKIA|ASIA)[A-Z0-9]{16}$ ]] ||
  fail "AWS_ACCESS_KEY_ID in $ENV_FILE does not look like an access key id (AKIA + 16 characters)"
[ "${#AWS_SECRET}" -eq 40 ] || fail "AWS_SECRET_ACCESS_KEY in $ENV_FILE is not 40 characters long"

if [[ "$REPO_URL" =~ ^https://github\.com/([^/]+)/([^/]+)/?$ ]] || [[ "$REPO_URL" =~ ^git@github\.com:([^/]+)/([^/]+)$ ]]; then
  REPO="${BASH_REMATCH[1]}/${BASH_REMATCH[2]%.git}"
else
  fail "GITHUB_REPO_URL must look like https://github.com/<owner>/<repo> or git@github.com:<owner>/<repo>.git"
fi

for tool in gh aws git; do command -v "$tool" >/dev/null || fail "$tool is not installed"; done
gh auth status >/dev/null 2>&1 || fail "the GitHub CLI is not logged in: run gh auth login"
gh repo view "$REPO" >/dev/null || fail "cannot open $REPO with the GitHub CLI"

log "checking the AWS key"
AWS_ACCOUNT_ID=$(env -u AWS_PROFILE -u AWS_SESSION_TOKEN AWS_ACCESS_KEY_ID="$AWS_KEY_ID" \
  AWS_SECRET_ACCESS_KEY="$AWS_SECRET" aws sts get-caller-identity --region ap-southeast-1 \
  --query Account --output text) || fail "AWS rejected the access key in $ENV_FILE"
PROD_REVIEWER=$(gh api user -q .login)
REVIEWER_ID=$(gh api user -q .id)
# ALERT_EMAIL in the environment wins; a GitHub noreply address cannot receive mail, so skip it.
ALERT_EMAIL="${ALERT_EMAIL-$(git config user.email || true)}"
case "$ALERT_EMAIL" in *@users.noreply.github.com) ALERT_EMAIL="" ;; esac
log "repository $REPO, AWS account $AWS_ACCOUNT_ID, production reviewer $PROD_REVIEWER"

log "repo secrets"
printf '%s' "$AWS_KEY_ID" | gh secret set AWS_ACCESS_KEY_ID --repo "$REPO"
printf '%s' "$AWS_SECRET" | gh secret set AWS_SECRET_ACCESS_KEY --repo "$REPO"
unset AWS_SECRET AWS_KEY_ID

log "repo variables"
gh variable set AWS_ACCOUNT_ID --repo "$REPO" --body "$AWS_ACCOUNT_ID"
if [ -n "$ALERT_EMAIL" ]; then
  gh variable set ALERT_EMAIL --repo "$REPO" --body "$ALERT_EMAIL"
else
  warn "git config user.email is empty: the platform deploys without an email subscription."
  warn "add one later with: gh variable set ALERT_EMAIL --repo $REPO --body you@example.com"
fi

log "protecting main (required checks: lint, test, cfn-lint, image)"
gh api -X PUT "repos/$REPO/branches/main/protection" --input - >/dev/null <<'JSON' ||
{
  "required_status_checks": { "strict": true, "contexts": ["lint", "test", "cfn-lint", "image"] },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
  fail "could not protect main (the branch must exist on GitHub; private repos need a paid plan for this)"

log "environments"
# development accepts any branch: a manual CD run from a branch deploys there.
gh api -X PUT "repos/$REPO/environments/development" >/dev/null
for env in test staging; do
  gh api -X PUT "repos/$REPO/environments/$env" --input - >/dev/null <<'JSON'
{ "deployment_branch_policy": { "protected_branches": true, "custom_branch_policies": false } }
JSON
done
for env in production platform; do
  gh api -X PUT "repos/$REPO/environments/$env" --input - >/dev/null <<JSON ||
{
  "reviewers": [ { "type": "User", "id": $REVIEWER_ID } ],
  "deployment_branch_policy": { "protected_branches": true, "custom_branch_policies": false }
}
JSON
    fail "could not set a required reviewer on $env (private repos need a paid plan for this)"
done

log "done"
cat <<EOF

  Repository      $REPO
  AWS account     $AWS_ACCOUNT_ID (region ap-southeast-1)
  Approver        $PROD_REVIEWER (production and platform)
  Alert email     ${ALERT_EMAIL:-none}

  Next: Actions -> Infrastructure -> Run workflow (approve "platform"), then merge to main.
  See docs/runbook.md.
EOF
