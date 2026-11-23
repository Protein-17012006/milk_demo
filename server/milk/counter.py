"""Counting worker: newest frame -> model -> CV Output rows -> results to the hub.

The same program runs on the hub itself (CPU fallback) or on a GPU machine elsewhere,
such as Long's RTX 5090. It needs only the stream URL, the hub URL and the internal token;
it never holds AWS keys, because the hub stores frames and results.

    python -m milk.counter --env worker.env
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import socket
import time
import urllib.request
from collections import deque
from datetime import datetime, timedelta, timezone

import numpy as np

from . import config
from .cvoutput import CaptureIdAllocator, Detection, build_capture, counts_of
from .pipeline import load_pipeline
from .privacy import load_blurrer
from .smoothing import CountSmoother
from .stream import LatestFrameReader

log = logging.getLogger("milk.counter")


def roi_pixels(roi, width: int, height: int) -> tuple[int, int, int, int]:
    if roi is None:
        return 0, 0, width, height
    x, y, w, h = roi
    x0, y0 = int(x * width), int(y * height)
    x1, y1 = min(width, int((x + w) * width)), min(height, int((y + h) * height))
    return x0, y0, x1 - x0, y1 - y0


def normalise(dets: list[Detection], dx: int = 0, dy: int = 0) -> list[Detection]:
    """Plain Python numbers (models often return numpy types) and frame coordinates."""
    out = []
    for d in dets:
        x, y, w, h = (int(round(float(v))) for v in d.box)
        out.append(Detection(d.sku_id, d.sku_name, float(d.confidence), (x + dx, y + dy, w, h), d.method))
    return out


def encode_jpeg(image: np.ndarray, quality: int, max_width: int | None = None) -> tuple[bytes, int, int]:
    import cv2

    h, w = image.shape[:2]
    if max_width and w > max_width:
        image = cv2.resize(image, (max_width, round(h * max_width / w)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    return buf.tobytes(), image.shape[1], image.shape[0]


class HubClient:
    """Posts JSON to the hub's /internal endpoints with the shared token."""

    def __init__(self, base_url: str, token: str, timeout: float = 10.0) -> None:
        self._base = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._last_error: str | None = None

    def post(self, path: str, payload: dict) -> bool:
        request = urllib.request.Request(
            self._base + path,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "X-Internal-Token": self._token, "User-Agent": "milk-counter"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                response.read()
            if self._last_error:
                log.info("hub reachable again")
            self._last_error = None
            return True
        except Exception as exc:  # noqa: BLE001 - the hub may be restarting or stopped
            message = f"{type(exc).__name__}: {exc}"
            if message != self._last_error:
                log.warning("could not reach the hub at %s: %s", self._base, message)
            self._last_error = message
            return False


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Count milk cartons on a live stream and send results to the hub.")
    parser.add_argument("--env", help="file with MILK_* settings (KEY=VALUE lines)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    s = config.load(args.env)
    tz = timezone(timedelta(hours=s.utc_offset_hours))
    pipeline = load_pipeline(s.pipeline, s.models_dir)
    blurrer = load_blurrer(s.yunet_path, s.person_model, s.device, s.person_blur)
    reader = LatestFrameReader(s.stream_url, keyframes_only=(s.decode != "all"))
    reader.start()
    hub = HubClient(s.hub_url, s.internal_token)
    smoother = CountSmoother(s.smooth_window)
    ids = CaptureIdAllocator()
    worker_name = os.environ.get("MILK_WORKER_NAME") or socket.gethostname()
    device = getattr(pipeline, "device", "cpu")
    min_gap = 1.0 / s.max_fps if s.max_fps > 0 else 0.0
    publish_gap = 1.0 / s.publish_fps if s.publish_fps > 0 else 0.0
    log.info(
        "camera %s, pipeline %s on %s, blur %s, hub %s",
        s.camera_id,
        pipeline.name,
        device,
        "on" if blurrer else "OFF",
        s.hub_url,
    )

    last_seq = 0
    last_start = last_status = last_publish = last_persist = 0.0
    last_smoothed: dict | None = None
    done_at: deque[float] = deque(maxlen=1200)

    while True:
        if min_gap:
            wait = last_start + min_gap - time.time()
            if wait > 0:
                time.sleep(wait)
        frame = reader.newer_than(last_seq, timeout=2.0)
        now = time.time()
        if now - last_status >= 2.0:
            hub.post(
                "/internal/status",
                {
                    "camera_id": s.camera_id,
                    "connected": reader.connected,
                    "last_error": reader.last_error,
                    "stream": reader.stream_info,
                    "pipeline": pipeline.name,
                    "device": device,
                    "worker": worker_name,
                    "blur": blurrer is not None,
                    "frames_last_minute": sum(1 for t in done_at if now - t <= 60),
                },
            )
            last_status = now
        if frame is None:
            continue
        last_seq, last_start = frame.seq, time.time()
        try:
            image = frame.image
            height, width = image.shape[:2]
            x0, y0, cw, ch = roi_pixels(s.roi, width, height)
            crop = image if (cw, ch) == (width, height) else image[y0 : y0 + ch, x0 : x0 + cw]

            started = time.perf_counter()
            detections = normalise(pipeline.detect(crop), x0, y0)
            processing_ms = round((time.perf_counter() - started) * 1000)
            done_at.append(time.time())

            ts = datetime.fromtimestamp(frame.received_at, tz)
            rows, log_line = build_capture(
                detections,
                stem=ids.stem(s.store_code, ts),
                store_id=s.store_id,
                camera_id=s.camera_id,
                capture_source=s.capture_source,
                ts=ts,
                processing_time_ms=processing_ms,
                flag_threshold=s.flag_threshold,
            )
            counts = counts_of(rows)
            smoothed = smoother.update(counts)
            changed = smoothed != last_smoothed
            last_smoothed = smoothed

            since_publish = time.time() - last_publish
            since_persist = time.time() - last_persist
            publish = changed or since_publish >= publish_gap
            persist = since_persist >= s.persist_every_s or (changed and since_persist >= 2.0)
            if not (publish or persist):
                continue

            shown, faces = blurrer.blur(image) if blurrer else (image, 0)
            latency_ms = round((time.time() - frame.received_at) * 1000)
            if publish:
                jpeg, display_w, display_h = encode_jpeg(shown, 80, s.display_max_w)
                meta = {
                    "camera_id": s.camera_id,
                    "store_id": s.store_id,
                    "capture_id": log_line["capture_id"],
                    "capture_timestamp": log_line["capture_timestamp"],
                    "received_at": frame.received_at,
                    "processing_time_ms": processing_ms,
                    "latency_ms": latency_ms,
                    "frame_w": width,
                    "frame_h": height,
                    "display_w": display_w,
                    "display_h": display_h,
                    "roi": None if s.roi is None else [x0, y0, cw, ch],
                    "detections": [
                        {
                            "sku_id": d.sku_id,
                            "conf": round(d.confidence, 3),
                            "box": list(d.box),
                            "flagged": d.sku_id is None or d.confidence < s.flag_threshold,
                        }
                        for d in detections
                    ],
                    "counts": counts,
                    "smoothed": smoothed,
                    "units": log_line["units_found"],
                    "flagged_rows": log_line["flagged_rows"],
                    "flagged": [
                        {k: r[k] for k in ("sku_id", "sku_name", "unit_count", "confidence_score", "flag_reason")}
                        for r in rows
                        if r["is_flagged"]
                    ],
                    "faces_blurred": faces,
                    "pipeline": pipeline.name,
                }
                if hub.post("/internal/result", {"meta": meta, "jpeg_b64": base64.b64encode(jpeg).decode("ascii")}):
                    last_publish = time.time()
            if persist:
                full = encode_jpeg(shown, 85)[0] if blurrer else None  # never store unblurred frames
                record = {**log_line, "rows": rows, "log": log_line, "counts": counts, "latency_ms": latency_ms}
                payload = {"record": record, "jpeg_b64": base64.b64encode(full).decode("ascii") if full else None}
                if hub.post("/internal/persist", payload):
                    last_persist = time.time()
        except Exception:  # noqa: BLE001 - keep counting the next frame
            log.exception("frame %s failed", frame.seq)


if __name__ == "__main__":
    main()
