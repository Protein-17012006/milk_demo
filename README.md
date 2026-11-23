# milk-camera

Live shelf-stock counting for 12 milk SKUs from a grocery-store CCTV camera, built for
the COS40005 demo with Datagent. The camera's stream goes to a small hub in AWS Singapore;
the counting runs on a GPU machine of the team, and the counts appear on a web dashboard a
few seconds later. Results are kept in the CV Output format of Datagent's Data Dictionary.

Plan and decisions: Confluence page **HOANG-P08** (team space). Earlier design for the
four-store phase: **HOANG-P07**.

## How it works (hybrid)

```
STORE                      AWS ap-southeast-1: the hub (t3.small)                 TEAM GPU MACHINE
CCTV 4K --RTSP/LAN--> relay --RTSPS/SRT--> MediaMTX :8322 / :8890 --RTSPS (read)--> counter (milk.counter)
                                             |                                     |  model on the GPU
                                             | (fallback: counter on the hub CPU)  |  blur faces, smooth
                                             v                                     |
          browser --HTTPS--> CloudFront --> dashboard + API (FastAPI) <--HTTPS + token-+  results, blurred frames
                                             |
                                             v
                               S3 (blurred frames, JSON) + DynamoDB (captures), written by the hub
```

- **Ingest (hub):** MediaMTX accepts RTSPS (TLS) and SRT (AES passphrase). The store relay
  may only publish and the GPU worker may only read `cam-*` paths, each with its own
  password. Plain RTSP listens on localhost only.
- **Counter (worker):** one program, `python -m milk.counter --env worker.env`, runs on the
  GPU machine (or on the hub's CPU as a fallback). It decodes with the system ffmpeg, always
  counts the newest frame, blurs faces, and posts results to the hub through CloudFront with
  the internal token. It holds no AWS keys and stores nothing locally. See `worker/README.md`.
- **Model:** pluggable. `null` finds nothing and is used until the team's pipeline
  (YOLO26s + DINOv2-S + LanceDB) is installed as `long`.
- **Dashboard:** latest frame with boxes, counts per SKU, latency, where the model runs, a
  10-minute chart, count changes, and CSV export of CV Output and Capture Log in
  Datagent's format.
- **Cost:** the hub is a t3.small. The stream from the hub to the GPU machine is AWS
  internet egress, about 2 GB per hour of 4K video; the first 100 GB a month are free.

## Repository layout

| Path | What |
|---|---|
| `server/milk/` | Counter, stream reader, face blur, CV Output, web app |
| `server/milk/web/static/` | Dashboard (plain HTML, CSS, JavaScript) |
| `server/mediamtx.yml.tpl` | MediaMTX v1.21.3 config template |
| `server/systemd/` | Services: `mediamtx`, `milk-counter`, `milk-web`, `milk-replay` |
| `infra/base.yaml` | CloudFormation: S3 bucket, DynamoDB table (kept on delete) |
| `infra/server.yaml` | CloudFormation: EC2, Elastic IP, CloudFront, nightly stop |
| `infra/*.ps1` | Deploy, release, start/stop and budget scripts (Windows PowerShell + AWS CLI) |
| `infra/remote/` | Scripts that run on the server |
| `edge/RELAY.md` | How the store relay pushes the camera stream (Vietnamese) |
| `worker/` | Running the counter on a GPU machine: guide (Vietnamese) and systemd user unit |
| `tests/` | Unit tests; `pytest` (`tests/load/` = Locust load test) |
| `Dockerfile`, `docker-compose.yml` | The hub as one image (also runs `milk.selfcheck` and `milk.reindex`) |
| `infra/platform.yml`, `infra/app.yml`, `infra/params/` | CloudFormation for the CI/CD pipeline on ECS Fargate (ap-southeast-1) |
| `.github/workflows/`, `scripts/ci/` | CI checks and the dev → test → staging → production pipeline |

## Deploy

Needs AWS CLI v2 with a profile (default `milk`) and PowerShell. Nothing else on the laptop.

```powershell
.\infra\deploy.ps1                      # secrets in SSM, both stacks, first release (t3.small hub)
.\infra\release.ps1                     # after a code change: upload and apply on the server
.\infra\remote-run.ps1 "journalctl -u milk-web -n 50 --no-pager"   # run a command on the hub (SSM)
.\infra\server-power.ps1 -Start         # the server also stops itself at 23:00 every night
.\infra\worker-env.ps1 -OutFile <path>  # settings for a GPU worker; contains secrets, send privately
.\infra\switch-source.ps1 -Source camera   # count the store camera; -Source replay = recorded video (demo fallback)
.\infra\budget.ps1 -Email you@example.com -LimitUsd 100   # alerts on real usage, credits excluded
```

Count on AWS instead of the team GPU (bigger CPU hub, then `counter/local=on`), or on an AWS
GPU once the quota allows it (the Elastic IP, URL and data stay the same):

```powershell
.\infra\deploy.ps1 -InstanceType g4dn.xlarge -RootVolumeGiB 100 `
  -ImageParam /aws/service/deeplearning/ami/x86_64/base-oss-nvidia-driver-gpu-ubuntu-24.04/latest/ami-id
```

## CI/CD pipeline (ECS Fargate)

Separately from the EC2 hub above, every merge to `main` builds one image and deploys the hub
to development, test and staging on ECS Fargate in ap-southeast-1; production deploys after a
reviewer approves it in GitHub. One-time setup, releasing, rollback and re-ingest:
[docs/runbook.md](docs/runbook.md). Run the hub locally with `docker compose up --build`.

## Settings

Everything that differs per deployment lives in SSM Parameter Store under `/milk-demo/`.
Secrets are created by `deploy.ps1` and never written to this repository. Change a setting,
then run `.\infra\release.ps1` to apply it.

| Parameter | Default | Meaning |
|---|---|---|
| `stream/publish_user`, `stream/publish_pass` | random | Login for the store relay |
| `stream/srt_passphrase` | random | SRT encryption passphrase |
| `web/password` | random | Dashboard password |
| `camera/store_id`, `camera/store_code`, `camera/id` | `DEMO-S01`, `S01`, `CAM-S01-A` | IDs written into CV Output |
| `counter/source_path` | `cam-s01-a` | Stream path to count; `cam-replay` counts the test video |
| `counter/pipeline` | `null` | `null` or `long` |
| `counter/roi` | empty | Shelf area as fractions `x,y,w,h`, e.g. `0.1,0.2,0.8,0.6` |
| `counter/decode` | `keyframes` | `all` decodes every frame (for a GPU server) |
| `counter/replay` | `off` | `on` plays `s3://<bucket>/samples/replay.mp4` as stream `cam-replay` |
| `counter/local` | `off` | `on` counts on the hub's own CPU; keep `off` while a GPU worker runs |
| `counter/max_fps` | `2` | Frames per second the hub's own counter processes |
| `stream/worker_user`, `stream/worker_pass` | random | Read-only login for a GPU worker |

## Data and privacy

- No video is recorded. Only frames with faces blurred are stored, in a private, encrypted
  bucket, and deleted after 30 days.
- The stream leaves the store, so the store owner's written consent and a notice in the
  store come before installation.
- Never commit keys, passwords, IP addresses, model weights, or store images to this
  public repository. `iam.md` and similar files are in `.gitignore`.

## Tests

```powershell
python -m pytest
```

`tests/test_cvoutput.py` rebuilds the 12 rows of image `PHONE-S02-A_20261012_083216-2.jpg`
from the CV Output report of 17/10/2026 and checks the CSV matches it byte for byte.
