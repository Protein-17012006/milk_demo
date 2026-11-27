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
from pathlib import Path

import numpy as np

from . import config, release
from .candidate import load_candidate
from .cvoutput import CaptureIdAllocator, Detection, build_capture, counts_of, persist_record
from .display import DisplayCheck
from .pipeline import load_pipeline
from .privacy import load_blurrer
from .sampling import Sampler
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


def status_payload(
    camera_id: str,
    reader,
    pipeline_name: str,
    device: str,
    worker: str,
    blur: bool,
    frames_last_minute: int,
    sampling: dict | None,
) -> dict:
    """What the worker posts to /internal/status every 2 s. Between sampling windows there is no reader: the
    stream is closed on purpose, and `sampling` tells the hub when it opens again."""
    payload = {
        "camera_id": camera_id,
        "connected": bool(reader is not None and reader.connected),
        "last_error": reader.last_error if reader is not None else None,
        "stream": reader.stream_info if reader is not None else {},
        "pipeline": pipeline_name,
        "device": device,
        "worker": worker,
        "blur": blur,
        "frames_last_minute": frames_last_minute,
    }
    if sampling is not None:
        payload["sampling"] = sampling
    return payload


CANDIDATE_MARGIN_S = 5.0


def candidate_deadline(next_start: float) -> float:
    """When the candidate must have stopped reading: a little before the next window opens, so that the live
    release never waits for it."""
    return next_start - CANDIDATE_MARGIN_S


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
    sampler = Sampler(
        s.sample_every_s,
        s.sample_for_s,
        lambda: LatestFrameReader(
            s.stream_url, keyframes_only=(s.decode != "all"), ca_file=s.stream_ca_file, tls_name=s.stream_tls_name
        ),
    )
    display = DisplayCheck(s.display_zone, s.display_min, s.display_refs) if s.display_zone else None
    # A candidate release, if live.json names one: it reads each window's stored frames once the window is over
    releases_dir = os.environ.get("MILK_RELEASES_DIR")
    candidate = (
        load_candidate(Path(releases_dir), dict(os.environ), s.models_dir, sampled=not sampler.continuous)
        if releases_dir
        else None
    )
    if releases_dir:  # the models are loaded: say so, for the job runner that asked for this start
        release.write_worker_status(Path(releases_dir), s.model_version, candidate.version if candidate else None)
    hub = HubClient(s.hub_url, s.internal_token)
    smoother = CountSmoother(s.smooth_window)
    ids = CaptureIdAllocator()
    worker_name = os.environ.get("MILK_WORKER_NAME") or socket.gethostname()
    device = getattr(pipeline, "device", "cpu")
    min_gap = 1.0 / s.max_fps if s.max_fps > 0 else 0.0
    publish_gap = 1.0 / s.publish_fps if s.publish_fps > 0 else 0.0
    log.info(
        "camera %s, pipeline %s on %s, blur %s, hub %s, %s",
        s.camera_id,
        pipeline.name,
        device,
        "on" if blurrer else "OFF",
        s.hub_url,
        "stream read continuously"
        if sampler.continuous
        else f"stream read for {s.sample_for_s:g} s every {s.sample_every_s:g} s",
    )

    last_seq = 0
    last_start = last_status = last_publish = last_persist = 0.0
    last_smoothed: dict | None = None
    done_at: deque[float] = deque(maxlen=1200)

    def post_status(reader, now: float) -> None:
        nonlocal last_status
        if now - last_status < 2.0:
            return
        hub.post(
            "/internal/status",
            status_payload(
                s.camera_id,
                reader,
                pipeline.name,
                device,
                worker_name,
                blurrer is not None,
                sum(1 for t in done_at if now - t <= 60),
                sampler.describe(now),
            ),
        )
        last_status = now

    while True:
        now = time.time()
        reader, opened = sampler.reader_at(now)
        if opened:  # a new window: counts from the last one must not leak into this one
            smoother.reset()
            last_seq, last_smoothed = 0, None
            if candidate:  # frames of the last window it never got to: dropped, and that window counts as late
                candidate.flush(0.0)
        if reader is None:  # between windows: the stream stays closed
            post_status(None, now)
            if candidate:  # one frame per turn, so the status above keeps going out while it reads
                sent = candidate.flush(candidate_deadline(sampler.next_start(now)), limit=1)
                for payload in sent:
                    hub.post("/internal/candidate", payload)
                if sent:
                    continue
            time.sleep(max(0.05, min(1.0, sampler.next_start(now) - now)))
            continue
        if min_gap:
            wait = last_start + min_gap - time.time()
            if wait > 0:
                time.sleep(wait)
        frame = reader.newer_than(last_seq, timeout=2.0)
        post_status(reader, time.time())
        if frame is None:
            continue
        last_seq, last_start = frame.seq, time.time()
        sampler.note_frame()
        try:
            image = frame.image
            height, width = image.shape[:2]
            x0, y0, cw, ch = roi_pixels(s.roi, width, height)
            crop = image if (cw, ch) == (width, height) else image[y0 : y0 + ch, x0 : x0 + cw]

            started = time.perf_counter()
            detections = normalise(pipeline.detect(crop), x0, y0)
            processing_ms = round((time.perf_counter() - started) * 1000)
            done_at.append(time.time())
            # On the original frame, before any blur; no zone set means the cabinet is taken as in view
            display_score, display_visible = display.check(image, detections, time.time()) if display else (None, True)

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
            if not sampler.continuous and sampler.frames_in_window < s.smooth_window:
                # Sampled counting stores nothing from a window's first smooth_window - 1 frames: the dashboard's
                # smoothed count is still filling. Records hold raw per-frame counts either way.
                persist = False
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
                    "display_score": display_score,
                    "display_visible": display_visible,
                    "faces_blurred": faces,
                    "pipeline": pipeline.name,
                }
                if hub.post("/internal/result", {"meta": meta, "jpeg_b64": base64.b64encode(jpeg).decode("ascii")}):
                    last_publish = time.time()
            if persist:
                full = encode_jpeg(shown, 85)[0] if blurrer else None  # never store unblurred frames
                record = persist_record(log_line, rows, counts, latency_ms, detections, s.model_version)
                record["display_score"] = display_score
                record["display_visible"] = display_visible
                payload = {"record": record, "jpeg_b64": base64.b64encode(full).decode("ascii") if full else None}
                if hub.post("/internal/persist", payload):
                    last_persist = time.time()
                    if candidate:  # the frame as the live release saw it: before any blur, kept in memory only
                        candidate.hold(
                            log_line["capture_id"], log_line["capture_timestamp"], s.camera_id, crop, (x0, y0)
                        )
        except Exception:  # noqa: BLE001 - keep counting the next frame
            log.exception("frame %s failed", frame.seq)


if __name__ == "__main__":
    main()
