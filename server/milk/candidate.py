"""The candidate release, run beside the live one (operations-loop design 5.2).

The live release always comes first. During a sampling window the worker only hands the candidate a copy of each
frame it has just stored; once the window is over and the stream is closed, the candidate reads those copies and its
boxes go to the hub as a message of their own. Nothing of the candidate reaches the live record, and whatever goes
wrong with it (it cannot load, it raises, it is too slow) stops the candidate, never the worker.

What happened is written to candidate-status.json beside live.json; the job runner on this machine copies it to the
website's backend and takes a stopped candidate out of the pointer.
"""

from __future__ import annotations

import json
import logging
import time
from collections import deque
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path

import numpy as np

from . import release
from .pipeline import Pipeline, load_pipeline

log = logging.getLogger(__name__)

STATUS_FILE = release.CANDIDATE_STATUS_FILE
MAX_HELD = 12  # frames of one window kept in memory for the candidate
LATE_LIMIT = 3  # windows in a row the candidate could not finish before it is stopped
LOAD_TIMES_KEPT = 5
DIED_LOADING_LIMIT = 2  # starts in a row that ended while this candidate was loading: it is not loaded again


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _write_status(path: Path, status: dict) -> None:
    try:
        path.write_text(json.dumps({**status, "updated_at": _now()}), encoding="utf-8")
    except OSError:  # the status file is a report; failing to write it must not touch the counting
        log.exception("could not write %s", path)


class CandidateRunner:
    def __init__(
        self,
        pipeline: Pipeline,
        version: str,
        status_path: Path,
        clock: Callable[[], float] = time.time,
        load_times: list[str] | None = None,
    ) -> None:
        self.version = version
        self.stopped: str | None = None
        self._pipeline = pipeline
        self._status_path = Path(status_path)
        self._clock = clock
        self._held: deque[tuple[str, str, str, np.ndarray, tuple[int, int]]] = deque()
        self._windows = self._late = self._errors = self._late_run = 0
        self._load_times = list(load_times or [])

    def status(self) -> dict:
        return {
            "candidate": self.version,
            "windows": self._windows,
            "late": self._late,
            "errors": self._errors,
            "load_times": self._load_times,
            "loads_unfinished": 0,
            "stopped": self.stopped,
        }

    def write_status(self) -> None:
        _write_status(self._status_path, self.status())

    def hold(
        self, capture_id: str, capture_timestamp: str, camera_id: str, crop: np.ndarray, offset: tuple[int, int]
    ) -> None:
        """Keeps a copy of a frame the live release has just stored, for flush() to read once the window is over."""
        if self.stopped or len(self._held) >= MAX_HELD:
            return
        self._held.append((capture_id, capture_timestamp, camera_id, crop.copy(), offset))

    def flush(self, deadline: float, limit: int | None = None) -> list[dict]:
        """Reads held frames, oldest first, until none is left, `limit` have been read in this call, or the clock
        reaches `deadline`. Returns one hub payload per frame read. A window whose frames were all read counts as
        done; frames still held at the deadline are dropped and the window counts as late."""
        if self.stopped or not self._held:
            return []
        out: list[dict] = []
        finished = False
        while self._held and (limit is None or len(out) < limit):
            if self._clock() >= deadline:
                self._held.clear()
                self._late += 1
                self._late_run += 1
                finished = True
                if self._late_run >= LATE_LIMIT:
                    self.stopped = "too_slow"
                break
            capture_id, capture_timestamp, camera_id, crop, (dx, dy) = self._held.popleft()
            started = time.perf_counter()
            try:
                detections = self._pipeline.detect(crop)
            except Exception as exc:  # noqa: BLE001 - a candidate's failure must never reach the live counting
                log.exception("candidate %s failed on %s", self.version, capture_id)
                self._held.clear()
                self._errors += 1
                self.stopped = f"error: {type(exc).__name__}"
                self.write_status()
                return []
            boxes = []
            for d in detections:
                x, y, w, h = (int(round(float(v))) for v in d.box)
                boxes.append({"sku_id": d.sku_id, "conf": round(float(d.confidence), 3), "box": [x + dx, y + dy, w, h]})
            out.append(
                {
                    "camera_id": camera_id,
                    "capture_id": capture_id,
                    "capture_timestamp": capture_timestamp,
                    "candidate_version": self.version,
                    "processing_time_ms": round((time.perf_counter() - started) * 1000),
                    "detections": boxes,
                }
            )
        if not self._held and not finished:
            self._late_run = 0
            finished = True
        if finished:
            self._windows += 1
            self.write_status()
        return out


def load_candidate(root: Path, base_env: Mapping[str, str], models_dir: str, sampled: bool) -> CandidateRunner | None:
    """The runner of the candidate that live.json names, or None: no candidate, a worker that reads the stream all
    the time (there is no idle time to run it in), or a candidate that cannot be loaded. Never raises.

    The attempt is written to candidate-status.json before the load begins, so a worker that dies while loading the
    candidate (a native crash takes the whole process) leaves a trace: after DIED_LOADING_LIMIT such starts in a row
    the candidate is left out and the live release comes up alone. The job runner then takes it out of live.json."""
    root = Path(root)
    status_path = root / STATUS_FILE
    try:
        version = release.read_pointer(root).candidate
    except ValueError:
        log.exception("candidate: cannot read the pointer")
        return None
    if not version:
        return None
    load_times: list[str] = []
    unfinished = 0
    try:
        old = json.loads(status_path.read_text(encoding="utf-8"))
        if old.get("candidate") == version:
            load_times = [str(t) for t in old.get("load_times") or []]
            unfinished = int(old.get("loads_unfinished") or 0)
    except (OSError, ValueError, TypeError):
        pass

    def status(stopped: str | None, times: list[str], still_loading: int = 0, errors: int = 0) -> dict:
        return {
            "candidate": version,
            "windows": 0,
            "late": 0,
            "errors": errors,
            "load_times": times,
            "loads_unfinished": still_loading,
            "stopped": stopped,
        }

    if not sampled:
        log.warning("candidate %s is not run: the worker reads the stream continuously", version)
        _write_status(status_path, status("not run: the worker reads the stream continuously", load_times))
        return None
    if unfinished >= DIED_LOADING_LIMIT:
        log.error("candidate %s is left out: the worker died %d times while loading it", version, unfinished)
        _write_status(status_path, status("error: the worker died twice while loading it", load_times, unfinished, 1))
        return None
    load_times = (load_times + [_now()])[-LOAD_TIMES_KEPT:]
    _write_status(status_path, status(None, load_times, unfinished + 1))
    try:
        candidate = release.load_release(root, version)
        pipeline = load_pipeline(
            candidate.env.get("MILK_PIPELINE", "null"), models_dir, release.model_env(base_env, candidate)
        )
    except Exception as exc:  # noqa: BLE001 - the live release must start whatever the candidate does
        log.exception("candidate %s could not be loaded", version)
        _write_status(status_path, status(f"error: {type(exc).__name__}", load_times, 0, 1))
        return None
    runner = CandidateRunner(pipeline, version, status_path, load_times=load_times)
    runner.write_status()
    log.info("candidate %s loaded (%s)", version, pipeline.name)
    return runner
