# Runbook: the milk hub pipeline

One Docker image per commit, promoted through four environments on Amazon ECS Fargate in
**ap-southeast-1 (Singapore)**, the same region as the EC2 hub. A merge to `main` deploys to development, test and staging by itself;
production deploys after a reviewer approves it in GitHub. Nobody deploys by hand: every
AWS change goes through GitHub Actions, which signs in with the IAM user key stored as the
repo secrets `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`.

What the pipeline deploys is the **hub**: the dashboard and API (`server/milk/web`), with
its S3 bucket and DynamoDB table. MediaMTX (stream ingest) and the counting worker (GPU)
are not part of it; the EC2 hub (`milk-demo-*` stacks, `infra/deploy.ps1`) is separate and
unchanged. The pipeline's IAM user cannot touch it: its policy names only the pipeline's own
stacks, roles, buckets and tables.

| Environment | Port | Task | Cluster | Starts when | Checks | After |
|---|---|---|---|---|---|---|
| development | 8082 | 0.25 vCPU / 1 GB, Spot | milk-nonprod | every merge to main; manual CD run from any branch | smoke test | - |
| test | 8081 | 0.25 vCPU / 1 GB, Spot | milk-nonprod | development succeeded (main only) | smoke test | end-to-end check, waited for (15 min max) |
| staging | 8080 | 0.5 vCPU / 1 GB | milk-nonprod | test succeeded | load test (20 users), smoke test | - |
| production | 80 | 0.5 vCPU / 1 GB | milk-prod (Container Insights) | staging succeeded **and** a reviewer approves | load test (at least 5 min), smoke test | parity table |

Each environment has its own stack `milk-<env>`: ECS service `milk-<env>`, bucket
`milk-<env>-<account>`, table `milk-<env>-captures`, secret `milk/<env>/app`, task role,
log group `/milk/<env>`, dashboard `milk-<env>` (and, in production, alarms). All four
share one load balancer, one ECR repository (`milk`) and the stack `milk-platform`.

| File | What |
|---|---|
| `.github/workflows/ci.yml` | Four required checks on every pull request: `lint`, `test`, `cfn-lint`, `image` |
| `.github/workflows/cd.yml` | Build once, promote development → test → staging → production |
| `.github/workflows/deploy.yml` | Reusable: one environment, one tag (runs `scripts/ci/deploy_env.sh`) |
| `.github/workflows/rollback.yml` | Manual: an earlier tag to one environment |
| `.github/workflows/reingest.yml` | Manual: rebuild a captures table from the S3 result files |
| `.github/workflows/infra.yml` | `infra/platform.yml`: change-set preview on PRs, deploy after approval |
| `.github/workflows/power.yml` | Stops development/test/staging every night at 23:00 (Vietnam); start/stop by hand |
| `infra/platform.yml`, `infra/app.yml`, `infra/params/*.json` | CloudFormation: shared platform, one stack per environment, per-environment values |
| `infra/deployer-policy.json` | IAM policy for the pipeline's IAM user |
| `scripts/ci/*.sh` | Deployment, one-off tasks, smoke test, load test, parity table, GitHub setup |

## 1. One-time setup

Needs: AWS CLI v2, the GitHub CLI (`winget install GitHub.cli`, then `gh auth login` as the
person who will approve production), and Git Bash on Windows.

1. **IAM user for the pipeline** (done once by an account admin): IAM user `milk-github` with
   no console access, the customer-managed policy `milk-github-deployer` made from
   `infra/deployer-policy.json`, and one access key. The pipeline can create IAM roles named
   `milk-<env>-*` for its tasks, so treat the key as sensitive.
2. **cicd.env.** `cp cicd.env.example cicd.env` in the repository root and fill in
   `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `GITHUB_REPO_URL`. `cicd.env` is
   ignored by git; never commit it, never paste the key anywhere else.
3. **GitHub.** `bash scripts/ci/setup_github.sh`. It checks the key with AWS, then sets the
   repo secrets and variables (`AWS_ACCOUNT_ID`, `ALERT_EMAIL` from `git config user.email`),
   protects `main` with the four required checks, and creates the environments, with you as
   the required reviewer of `production` and `platform`. Run it again whenever the key changes.
   Required reviewers and branch protection are free only on public repositories.
4. **Platform.** GitHub → Actions → *Infrastructure* → *Run workflow* on `main`, then
   approve the `platform` environment. This creates the network, load balancer, ECR
   repository, clusters and alarm topic. Cost alerts come from the account's existing budgets
   (`milk-demo-gross`, `budget_do_not_exceed`). If an alert email is set, **confirm the
   subscription email from AWS SNS**.
5. **First release.** Merge any pull request to `main` (or run *CD* by hand on `main`). The
   first deployment of each environment creates its stack; this takes a few minutes longer.
6. **Dashboard password.** Each environment has its own, generated in Secrets Manager.
   Someone with AWS access reads it:
   `aws secretsmanager get-secret-value --region ap-southeast-1 --secret-id milk/production/app --query SecretString --output text`
   (`web_password`). The session secret and worker token in the same secret are created by
   the first deployment.

## 2. Releasing a change

1. Branch `feat/<topic>` or `fix/<topic>`, open a pull request to `main`, fill in the checklist.
2. CI runs `lint` (ruff, ruff format, actionlint, shellcheck), `test` (pytest, at least 80%
   line coverage on the hub modules), `cfn-lint` and `image` (Docker build, the container
   answers `/healthz`, Trivy finds no fixable CRITICAL/HIGH). All four must be green and the
   branch up to date with `main`; no approving review is needed.
3. Merge. *CD* builds the image once, tagged with the first 7 characters of the commit
   (e.g. `1d58130`), pushes it to ECR (tags are immutable; a re-run for the same commit skips
   the build), and deploys development → test → staging.
4. Production waits. Open the run, *Review deployments*, approve `production`.
5. Each job links to its environment's URL; the job summary has the load-test table and, in
   production, the parity table (all four environments should run the same tag). Changes to
   `docs/` or Markdown files alone do not start a release.

What every deployment does (`scripts/ci/deploy_env.sh`, the same in every environment):

1. Preflight: the image exists in ECR, read the platform's outputs.
2. Update stack `milk-<env>` with the current template; the running hub keeps its image.
   (First deployment: create the stack with no task running.)
3. Add the session secret and worker token to `milk/<env>/app` if missing (values masked).
4. Start the service (0 → 1 task) if it was stopped to save money.
5. Staging and production: start 20 Locust users on the runner.
6. Update the stack with the new image. ECS starts the new task beside the old one and stops
   the old one only after the new one passes its health checks; if it never does, the
   circuit breaker rolls the service back and the step fails.
7. Smoke test: service stable, every task runs the new tag, `/healthz` answers `ok` with
   that tag through the load balancer.
8. Staging and production: load-test verdict. Any failed request or no request fails the job;
   p95 above 2 s only warns. Production keeps the load on for at least 5 minutes, so every
   release leaves evidence on the CloudWatch dashboard. Artifact: `locust-<env>-<tag>`.
9. Test: the end-to-end check, `python -m milk.selfcheck` as a one-off ECS task. It plays the
   worker and a browser against the deployed hub (camera `CAM-E2E`): health and version,
   login and token enforcement, a capture through live/frame/history/flags, persistence to S3
   and DynamoDB, both CSV exports byte for byte, every page; it cleans up after itself. Its
   log (`e2e_check` lines, then `e2e_summary`) is printed into the job log when the task ends.
10. Report: the URL; production writes the parity table.

Try a branch on real AWS: Actions → *CD* → *Run workflow* → choose the branch. It deploys to
development only.

## 3. When a release fails

A failed step fails its job and later environments do not run; earlier environments keep the
new version. Read the job log: every step is time-stamped, a failed stack update prints the
newest failed CloudFormation events, and one-off task logs are printed in full.

| Symptom | Likely cause | What to do |
|---|---|---|
| `image milk:<tag> is not in ECR` | build job failed, or the tag expired (30 newest kept) | re-run the build / use a newer tag |
| stack update fails, service rolled back | new task never became healthy | `/milk/<env>` log group, stream `app/app/<task-id>`; fix forward |
| `<stack> is in UPDATE_ROLLBACK_FAILED` | CloudFormation could not roll back | console: *Continue update rollback*, then re-run the job |
| smoke test: load balancer still reaches the old version | draining took longer than 60 s | re-run the job |
| load test failed | a request failed during the update: 5xx, refused or reset | see the table in the job summary and the artifact |
| end-to-end check failed | a `e2e_check ... result=fail` line says which | fix forward; the test environment keeps the new version |

Fix forward with a new pull request; its image takes the whole path again. In production a
failed load-test verdict arrives after the new version already serves users: decide whether
to roll back.

## 4. Rolling back

Actions → *Rollback* → *Run workflow*: environment and an earlier tag. Run it once with an
empty tag to see the 10 newest tags in the summary. The rollback reuses `deploy.yml` with
`rollback: true`: no end-to-end test; staging and production still run the load test, and
production still needs approval. A CD run waiting at the production gate holds the
production lock, so reject that run first. Target: production restored within 10 minutes of
approval.

The current template is used with the old image, so a rollback never undoes an
infrastructure change; revert that in a pull request.

## 5. Re-ingesting captures

Every capture is a JSON result file in S3 and a row in DynamoDB (what the CSV exports read).
If a table is emptied or recreated, Actions → *Re-ingest* rebuilds it from the bucket with
`python -m milk.reindex` as a one-off task: choose the environment, optionally a prefix
(`CAM-S01-A/2026-11-18`) and *dry run* to only count. Rows keep their keys, so running it
twice changes nothing; files past their 30-day retention are skipped. Production needs approval.

## 6. Saving money

Rough monthly cost at list prices (Singapore is ~10-20% above us-east-1) with everything running: load balancer ~USD 17,
production ~18, staging ~18, development and test on Spot ~3 each, public IPv4 addresses
~3.6 each (load balancer 2 + one per task), secrets ~1.6, Container Insights and alarms a few
dollars. The account's budgets email before the USD 100 limit.

- *Power* stops development, test and staging every night at 23:00 Vietnam time. Start them
  by hand from the same workflow, or just release: a deployment starts a stopped service.
- Production is never stopped by a workflow (availability is a success metric).
- ECR keeps the 30 newest images; logs are kept 14 days; frames and results 30 days.

## 7. Changing the platform

Edit `infra/platform.yml` in a pull request: the *Infrastructure* run on it shows the
change set (look for `Replacement: True`). After the merge the platform deploys when a
reviewer approves the `platform` environment. `infra/app.yml` and `infra/params/*.json`
need nothing special: every release updates each environment's stack with the current template.

## 8. Pointing a counting worker at an environment

The worker posts to the hub: set `MILK_HUB_URL` to the environment's URL (e.g.
`http://<alb-dns>` for production, `:8080` for staging) and `MILK_INTERNAL_TOKEN` to
`internal_token` from `milk/<env>/app`. The load balancer serves plain HTTP (HTTPS and a
domain are out of scope), so the token and the dashboard password cross the internet
unencrypted. Use it for the demo only, and keep the CloudFront hub for the store camera.

## 9. Tearing down after grading

1. Empty and delete each environment: `aws s3 rm s3://milk-<env>-<account> --recursive`, then
   `aws cloudformation delete-stack --stack-name milk-<env>` (all four).
2. `aws cloudformation delete-stack --stack-name milk-platform` (the ECR repository is
   emptied automatically).
3. Delete the IAM user's access key, then the repo secrets.

## 10. How this differs from the CIC-NIDS brief it follows

| Brief | Here | Why |
|---|---|---|
| Streamlit dashboard, `/_stcore/health` | FastAPI hub, `/healthz` (reports environment and version) | the application being deployed |
| RDS PostgreSQL, db-bootstrap and Alembic migrate tasks | DynamoDB table + S3 bucket per environment; no migrations | the hub stores captures in DynamoDB/S3; nothing to migrate, and no RDS cost |
| S3 upload → EventBridge → ingestion task; reconcile | none; re-ingest = rebuild the table from S3 result files | the hub receives results over HTTP from the worker, not files |
| E2E: sample files per data contract | `milk.selfcheck`: worker + browser path against the deployed hub | tests what this application actually does |
| private subnets | public subnets, tasks reachable only from the load balancer | no RDS to hide; no NAT gateway (~USD 32/month) |
| OIDC role per environment | one IAM user key in repo secrets | as specified for this project |
| `databases.yml` stack | not needed | tables and buckets live in each environment's stack |
| session cookie always `Secure` | `MILK_COOKIE_SECURE=false` in the pipeline's environments | the load balancer is plain HTTP; browsers drop Secure cookies over HTTP |
