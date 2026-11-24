"""Settings read from the environment (systemd loads /etc/milk/milk.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import PurePath


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def load_env_file(path: str) -> None:
    """Reads KEY=VALUE lines into the environment; variables already set take precedence."""
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _roi(raw: str | None, name: str = "MILK_ROI") -> tuple[float, float, float, float] | None:
    """Region as normalised x,y,w,h in 0..1, for example "0.1,0.2,0.8,0.6" (MILK_ROI, MILK_DISPLAY_ZONE)."""
    if not raw:
        return None
    parts = [float(p) for p in raw.split(",")]
    if len(parts) != 4:
        raise ValueError(f"{name} needs four numbers x,y,w,h, got {raw!r}")
    x, y, w, h = parts
    if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 and 0 < h <= 1):
        raise ValueError(f"{name} values must be fractions of the frame, got {raw!r}")
    return x, y, w, h


def default_model_version(pipeline: str, slide_weights: str) -> str:
    """Model version when MILK_MODEL_VERSION is not set: the pipeline, plus the Slide training run when the
    pipeline counts Slide cans (runs_v3/best.pt -> "long+slide:runs_v3")."""
    if "slide" in pipeline and slide_weights:
        return f"{pipeline}:{PurePath(slide_weights).parent.name}"
    return pipeline


@dataclass(frozen=True)
class Settings:
    region: str
    bucket: str | None
    table: str | None
    store_id: str
    store_code: str
    camera_id: str
    camera_path: str
    capture_source: str
    stream_url: str
    decode: str
    web_password: str
    web_secret: str
    internal_token: str
    hub_url: str
    pipeline: str
    models_dir: str
    yunet_path: str
    person_model: str
    person_blur: str
    device: str
    persist_every_s: float
    publish_fps: float
    max_fps: float
    roi: tuple[float, float, float, float] | None
    display_max_w: int
    display_zone: tuple[float, float, float, float] | None
    display_min: float
    display_refs: str | None
    smooth_window: int
    flag_threshold: float
    mediamtx_api: str
    utc_offset_hours: int
    model_version: str
    cookie_secure: bool = True
    environment: str = "local"
    version: str = "dev"
    stream_ca_file: str | None = None
    stream_tls_name: str | None = None
    sample_every_s: float = 0.0
    sample_for_s: float = 30.0


def _sampling() -> tuple[float, float]:
    """MILK_SAMPLE_EVERY_S and MILK_SAMPLE_FOR_S: read the stream for FOR seconds every EVERY seconds.
    EVERY = 0 counts continuously."""
    every = float(_env("MILK_SAMPLE_EVERY_S", "0"))
    window = float(_env("MILK_SAMPLE_FOR_S", "30"))
    if every > 0 and not 0 < window < every:
        raise ValueError(
            f"MILK_SAMPLE_FOR_S ({window:g}) must be more than 0 and less than MILK_SAMPLE_EVERY_S ({every:g})"
        )
    return every, window


def _flag(name: str, default: bool) -> bool:
    value = _env(name)
    return default if value is None else value.strip().lower() not in ("0", "false", "no", "off")


def load(env_file: str | None = None) -> Settings:
    env_file = env_file or _env("MILK_ENV_FILE")
    if env_file:
        load_env_file(env_file)
    camera_path = _env("MILK_CAMERA_PATH", "cam-s01-a")
    sample_every_s, sample_for_s = _sampling()
    return Settings(
        region=_env("MILK_REGION", "ap-southeast-1"),
        bucket=_env("MILK_BUCKET"),
        table=_env("MILK_TABLE"),
        store_id=_env("MILK_STORE_ID", "DEMO-S01"),
        store_code=_env("MILK_STORE_CODE", "S01"),
        camera_id=_env("MILK_CAMERA_ID", "CAM-S01-A"),
        camera_path=camera_path,
        capture_source=_env("MILK_CAPTURE_SOURCE", "CCTV"),
        stream_url=_env("MILK_STREAM_URL", f"rtsp://127.0.0.1:8554/{camera_path}"),
        decode=_env("MILK_DECODE", "keyframes"),
        web_password=_env("MILK_WEB_PASSWORD", ""),
        web_secret=_env("MILK_WEB_SECRET", ""),
        internal_token=_env("MILK_INTERNAL_TOKEN", ""),
        # Where the counter sends results: the web on the same server, or the hub's
        # CloudFront address when the counter runs on a GPU machine elsewhere.
        hub_url=_env("MILK_HUB_URL", _env("MILK_WEB_INTERNAL_URL", "http://127.0.0.1:80")),
        pipeline=_env("MILK_PIPELINE", "null"),
        models_dir=_env("MILK_MODELS_DIR", "/opt/milk/models"),
        yunet_path=_env("MILK_YUNET", "/opt/milk/models/face_detection_yunet_2023mar.onnx"),
        person_model=_env("MILK_PERSON_MODEL", ""),  # COCO weights, e.g. yolo26s.pt; empty = faces only
        person_blur=_env("MILK_PERSON_BLUR", "head"),  # head: head and shoulders; body: the whole person
        device=_env("MILK_DEVICE", ""),  # cuda:0, cpu, or empty for automatic
        persist_every_s=float(_env("MILK_PERSIST_EVERY_S", "10")),
        publish_fps=float(_env("MILK_PUBLISH_FPS", "3")),  # dashboard updates per second, at most
        max_fps=float(_env("MILK_MAX_FPS", "0")),  # frames counted per second, 0 = as fast as possible
        roi=_roi(_env("MILK_ROI")),
        display_max_w=int(_env("MILK_DISPLAY_MAX_W", "1920")),
        # The glass cabinet, as fractions of the frame; unset = the worker does not check whether it is in view
        display_zone=_roi(_env("MILK_DISPLAY_ZONE"), "MILK_DISPLAY_ZONE"),
        display_min=float(_env("MILK_DISPLAY_MIN", "0.5")),  # histogram correlation below this = cabinet not in view
        display_refs=_env("MILK_DISPLAY_REFS"),  # .npz where the learnt references are kept across restarts
        smooth_window=int(_env("MILK_SMOOTH_WINDOW", "3")),
        flag_threshold=float(_env("MILK_FLAG_THRESHOLD", "0.70")),
        mediamtx_api=_env("MILK_MEDIAMTX_API", "http://127.0.0.1:9997"),
        utc_offset_hours=int(_env("MILK_UTC_OFFSET_HOURS", "7")),
        model_version=_env("MILK_MODEL_VERSION")
        or default_model_version(_env("MILK_PIPELINE", "null"), _env("MILK_SLIDE_WEIGHTS", "")),
        # The session cookie is Secure by default (CloudFront serves HTTPS). The pipeline's
        # environments are plain HTTP behind the load balancer, so they set this to false.
        cookie_secure=_flag("MILK_COOKIE_SECURE", True),
        environment=_env("MILK_ENVIRONMENT", "local"),
        version=_env("MILK_VERSION", "dev"),  # image tag, set by the pipeline
        # The hub's RTSPS certificate (self-signed) and the name in it, for workers whose ffmpeg checks it
        stream_ca_file=_env("MILK_STREAM_CA_FILE"),
        stream_tls_name=_env("MILK_STREAM_TLS_NAME"),
        sample_every_s=sample_every_s,
        sample_for_s=sample_for_s,
    )
