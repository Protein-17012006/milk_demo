#!/bin/bash
# Installs or updates everything on the demo server. Safe to run again.
# Run as root: by the EC2 bootstrap on first boot, then by update.sh on every release.
# Secrets and per-camera settings come from SSM Parameter Store under $MILK_SSM_PREFIX.
set -euo pipefail
export PATH="$PATH:/snap/bin"
# shellcheck disable=SC1091
source /etc/milk/deploy.env # MILK_REGION MILK_BUCKET MILK_TABLE MILK_RELEASE_KEY MILK_SSM_PREFIX

APP=/opt/milk/app
VENV=/opt/milk/venv
MODELS=/opt/milk/models
DATA=/opt/milk/data
MTX_VERSION=v1.21.3
YUNET_FILE=face_detection_yunet_2023mar.onnx
YUNET_URL="https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/$YUNET_FILE"

log() { echo "[install $(date -Is)] $*"; }
param() { # param NAME [DEFAULT]
  aws ssm get-parameter --region "$MILK_REGION" --with-decryption --name "$MILK_SSM_PREFIX/$1" \
    --query Parameter.Value --output text 2>/dev/null || echo "${2:-}"
}

log "user and folders"
id milk >/dev/null 2>&1 || useradd --system --home-dir /opt/milk --shell /usr/sbin/nologin milk
install -d -o milk -g milk /opt/milk "$MODELS" "$DATA"
install -d -m 0750 -o root -g milk /etc/milk /etc/mediamtx

log "settings from SSM"
PUBLISH_USER=$(param stream/publish_user)
PUBLISH_PASS=$(param stream/publish_pass)
WORKER_USER=$(param stream/worker_user)
WORKER_PASS=$(param stream/worker_pass)
SRT_PASSPHRASE=$(param stream/srt_passphrase)
WEB_PASSWORD=$(param web/password)
WEB_SECRET=$(param web/secret)
INTERNAL_TOKEN=$(param web/internal_token)
ORIGIN_SECRET=$(param web/origin_secret)
for name in PUBLISH_USER PUBLISH_PASS WORKER_USER WORKER_PASS SRT_PASSPHRASE WEB_PASSWORD WEB_SECRET INTERNAL_TOKEN ORIGIN_SECRET; do
  [ -n "${!name}" ] || { echo "missing $name in SSM under $MILK_SSM_PREFIX"; exit 1; }
done
STORE_ID=$(param camera/store_id DEMO-S01)
STORE_CODE=$(param camera/store_code S01)
CAMERA_ID=$(param camera/id CAM-S01-A)
SOURCE_PATH=$(param counter/source_path cam-s01-a) # cam-replay to count the recorded test video
PIPELINE=$(param counter/pipeline null)
DECODE=$(param counter/decode keyframes)
ROI=$(param counter/roi "")
REPLAY=$(param counter/replay off)
LOCAL_COUNTER=$(param counter/local off) # on = count on this server's CPU (fallback when no GPU worker)
MAX_FPS=$(param counter/max_fps 2) # frames counted per second by the local counter; keeps t3 CPU credits
# Store camera reachable from the internet (HOANG-P10 decision 1): MediaMTX pulls it on demand instead
# of a relay pushing it. Unset camera/url = no pulled path; a relay can still publish to cam-* paths.
CAMERA_URL=$(param camera/url "")   # SecureString, rtsp://user:pass@host:port/...; never logged
CAMERA_PATH=$(param camera/path cam-s01-a)

log "MediaMTX $MTX_VERSION"
if [ "$(cat /usr/local/lib/mediamtx.version 2>/dev/null || true)" != "$MTX_VERSION" ]; then
  tmp=$(mktemp -d)
  base="https://github.com/bluenviron/mediamtx/releases/download/$MTX_VERSION"
  file="mediamtx_${MTX_VERSION}_linux_amd64.tar.gz"
  curl -fsSL -o "$tmp/$file" "$base/$file"
  curl -fsSL -o "$tmp/checksums.sha256" "$base/checksums.sha256"
  # Lines look like "<sha256> *<file>"; keep only ours and let sha256sum verify it.
  line=$(awk -v f="$file" '$2 == f || $2 == "*" f' "$tmp/checksums.sha256")
  [ -n "$line" ] || { echo "no checksum published for $file"; exit 1; }
  (cd "$tmp" && echo "$line" | sha256sum -c -)
  tar -xzf "$tmp/$file" -C "$tmp" mediamtx
  install -m 0755 "$tmp/mediamtx" /usr/local/bin/mediamtx
  install -d /usr/local/lib && echo "$MTX_VERSION" > /usr/local/lib/mediamtx.version
  rm -rf "$tmp"
fi
if [ ! -s /etc/mediamtx/server.crt ]; then
  openssl req -x509 -newkey rsa:2048 -nodes -days 825 -subj "/CN=milk-demo-ingest" \
    -keyout /etc/mediamtx/server.key -out /etc/mediamtx/server.crt 2>/dev/null
fi
chown root:milk /etc/mediamtx/server.key /etc/mediamtx/server.crt
chmod 0640 /etc/mediamtx/server.key

PUBLISH_USER="$PUBLISH_USER" PUBLISH_PASS="$PUBLISH_PASS" WORKER_USER="$WORKER_USER" \
WORKER_PASS="$WORKER_PASS" SRT_PASSPHRASE="$SRT_PASSPHRASE" \
CAMERA_URL="$CAMERA_URL" CAMERA_PATH="$CAMERA_PATH" \
python3 - "$APP/server/mediamtx.yml.tpl" /etc/mediamtx/mediamtx.yml.new <<'PY'
import os, re, sys
text = open(sys.argv[1], encoding="utf-8").read()
def fill(match):
    value = os.environ.get(match.group(1))
    if not value:
        raise SystemExit(f"missing value for {match.group(1)}")
    return value
text = re.sub(r"\{\{([A-Z_]+)\}\}", fill, text)
url, path = os.environ.get("CAMERA_URL", ""), os.environ.get("CAMERA_PATH", "")
if url:
    if not re.fullmatch(r"cam-[a-z0-9-]+", path):
        raise SystemExit("camera/path must look like cam-<name> so the worker account may read it")
    if not url.startswith(("rtsp://", "rtsps://")):
        raise SystemExit("camera/url must be an rtsp:// or rtsps:// URL")
    quoted = "'" + url.replace("'", "''") + "'"  # YAML single-quoted scalar
    text = text.rstrip("\n") + (
        f"\n  {path}:\n"
        f"    source: {quoted}\n"
        "    sourceOnDemand: yes\n"
        "    rtspTransport: tcp\n"
    )
open(sys.argv[2], "w", encoding="utf-8").write(text)
PY
MTX_CHANGED=0
if ! cmp -s /etc/mediamtx/mediamtx.yml.new /etc/mediamtx/mediamtx.yml; then
  mv /etc/mediamtx/mediamtx.yml.new /etc/mediamtx/mediamtx.yml
  MTX_CHANGED=1
else
  rm -f /etc/mediamtx/mediamtx.yml.new
fi
chown root:milk /etc/mediamtx/mediamtx.yml
chmod 0640 /etc/mediamtx/mediamtx.yml

log "environment for the counter and the web"
umask 027
cat > /etc/milk/milk.env <<EOF
MILK_REGION=$MILK_REGION
MILK_BUCKET=$MILK_BUCKET
MILK_TABLE=$MILK_TABLE
MILK_STORE_ID=$STORE_ID
MILK_STORE_CODE=$STORE_CODE
MILK_CAMERA_ID=$CAMERA_ID
MILK_CAMERA_PATH=$SOURCE_PATH
MILK_CAPTURE_SOURCE=CCTV
MILK_STREAM_URL=rtsp://127.0.0.1:8554/$SOURCE_PATH
MILK_DECODE=$DECODE
MILK_PIPELINE=$PIPELINE
MILK_ROI=$ROI
MILK_MODELS_DIR=$MODELS
MILK_YUNET=$MODELS/$YUNET_FILE
MILK_WEB_PASSWORD=$WEB_PASSWORD
MILK_WEB_SECRET=$WEB_SECRET
MILK_INTERNAL_TOKEN=$INTERNAL_TOKEN
MILK_ORIGIN_SECRET=$ORIGIN_SECRET
MILK_HUB_URL=http://127.0.0.1:80
MILK_WORKER_NAME=hub-cpu
MILK_MAX_FPS=$MAX_FPS
EOF
umask 022
chown root:milk /etc/milk/milk.env
chmod 0640 /etc/milk/milk.env

log "python environment"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --disable-pip-version-check --upgrade pip wheel
"$VENV/bin/pip" install --quiet --disable-pip-version-check -r "$APP/server/requirements.txt"
if [ "$PIPELINE" != "null" ] && [ -f "$APP/server/requirements-model.txt" ]; then
  if command -v nvidia-smi >/dev/null 2>&1; then torch_index=https://download.pytorch.org/whl/cu126
  else torch_index=https://download.pytorch.org/whl/cpu; fi
  "$VENV/bin/pip" install --quiet --disable-pip-version-check --extra-index-url "$torch_index" \
    -r "$APP/server/requirements-model.txt"
fi

log "models and test video"
aws s3 sync "s3://$MILK_BUCKET/models/" "$MODELS/" --region "$MILK_REGION" --only-show-errors || log "no models in S3 yet"
if [ ! -s "$MODELS/$YUNET_FILE" ]; then
  curl -fsSL -o "$MODELS/$YUNET_FILE" "$YUNET_URL"
fi
if aws s3 ls "s3://$MILK_BUCKET/samples/replay.mp4" --region "$MILK_REGION" >/dev/null 2>&1; then
  aws s3 cp "s3://$MILK_BUCKET/samples/replay.mp4" "$DATA/replay.mp4" --region "$MILK_REGION" --only-show-errors
fi
chown -R milk:milk "$MODELS" "$DATA"

log "services"
install -m 0644 "$APP"/server/systemd/*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable mediamtx milk-web >/dev/null 2>&1
if [ "$MTX_CHANGED" = 1 ] || ! systemctl is-active --quiet mediamtx; then
  systemctl restart mediamtx
fi
systemctl restart milk-web
if [ "$LOCAL_COUNTER" = "on" ]; then
  systemctl enable milk-counter >/dev/null 2>&1
  systemctl restart milk-counter
else
  systemctl disable --now milk-counter >/dev/null 2>&1 || true # counting happens on a GPU worker
fi
if [ "$REPLAY" = "on" ] && [ -s "$DATA/replay.mp4" ]; then
  systemctl restart milk-replay
else
  systemctl stop milk-replay >/dev/null 2>&1 || true
fi
sleep 3
for unit in mediamtx milk-web milk-counter milk-replay; do
  echo "  $unit: $(systemctl is-active "$unit" 2>/dev/null || true)"
done
log "done"
