"""The worker's main loop with a candidate release beside the live one, run for a few seconds on a stand-in camera
and a stand-in hub. Real clock, short sampling windows (0.8 s every 2 s)."""

from __future__ import annotations

import json
import time

import numpy as np
import pytest
from test_release import write_release

from milk import candidate, counter, release
from milk.cvoutput import Detection
from milk.stream import Frame


class Finished(Exception):
    """Raised by the stand-ins when the test's time is up: it ends counter.main()."""


class Clock:
    def __init__(self):
        now = time.time()
        # stop half a second before a window opens, at least one whole window from now
        self.stop_at = (now // 2 + 2) * 2 - 0.5

    def over(self) -> bool:
        return time.time() >= self.stop_at


class Camera:
    """Stands in for the stream reader: a new grey frame every 50 ms, each of its own shade."""

    connected, last_error, stream_info = True, None, {}

    def __init__(self, clock):
        self._clock, self._seq = clock, 0

    def start(self):
        pass

    def stop(self):
        pass

    def newer_than(self, seq, timeout):
        if self._clock.over():
            raise Finished
        time.sleep(0.05)
        self._seq += 1
        image = np.full((120, 160, 3), self._seq % 250, np.uint8)
        return Frame(image=image, received_at=time.time(), seq=self._seq)


class Hub:
    def __init__(self, clock):
        self._clock = clock
        self.posts: list[tuple[str, dict]] = []

    def post(self, path, payload):
        if self._clock.over():
            raise Finished
        self.posts.append((path, payload))
        return True

    def of(self, path):
        return [payload for p, payload in self.posts if p == path]


class ShadePipeline:
    """Draws one box whose x is the shade of the frame it was given: two pipelines that saw the same pixels draw the
    same box."""

    def __init__(self, name, fail=False):
        self.name, self.fail, self.device = name, fail, "cpu"

    def detect(self, image):
        if self.fail:
            raise RuntimeError("the candidate broke")
        return [Detection("original145", "Slide Original 145g", 0.9, (int(image[0, 0, 0]), 10, 20, 30))]


def run_worker(tmp_path, monkeypatch, candidate_pipeline):
    write_release(tmp_path, "v1", env={"MILK_PIPELINE": "null"}, kind="baseline")
    write_release(tmp_path, "v2", env={"MILK_PIPELINE": "null"}, kind="rules", parent="v1")
    release.write_pointer(tmp_path, release.Pointer(live="v1", candidate="v2"))
    settings = {
        "MILK_RELEASES_DIR": str(tmp_path),
        "MILK_PIPELINE": "null",
        "MILK_MODEL_VERSION": "set-by-hand",
        "MILK_SAMPLE_EVERY_S": "2",
        "MILK_SAMPLE_FOR_S": "0.8",
        "MILK_PERSIST_EVERY_S": "0.2",
        "MILK_SMOOTH_WINDOW": "1",
        "MILK_YUNET": str(tmp_path / "no-face-model.onnx"),
        "MILK_PERSON_MODEL": "",
        "MILK_HUB_URL": "http://hub.invalid",
        "MILK_INTERNAL_TOKEN": "token",
    }
    for key, value in settings.items():
        monkeypatch.setenv(key, value)
    for key in ("MILK_ENV_FILE", "MILK_ROI", "MILK_DISPLAY_ZONE", "MILK_MAX_FPS"):
        monkeypatch.delenv(key, raising=False)
    clock = Clock()
    hub = Hub(clock)
    monkeypatch.setattr(counter, "LatestFrameReader", lambda *args, **kwargs: Camera(clock))
    monkeypatch.setattr(counter, "HubClient", lambda *args, **kwargs: hub)
    monkeypatch.setattr(counter, "load_pipeline", lambda kind, models_dir, env=None: ShadePipeline("live"))
    monkeypatch.setattr(candidate, "load_pipeline", lambda kind, models_dir, env=None: candidate_pipeline)
    monkeypatch.setattr(counter, "CANDIDATE_MARGIN_S", 0.2)
    with pytest.raises(Finished):
        counter.main([])
    return hub


def test_the_candidate_reads_the_frames_the_live_release_stored_and_never_the_other_way(tmp_path, monkeypatch):
    hub = run_worker(tmp_path, monkeypatch, ShadePipeline("candidate"))
    stored = [p["record"] for p in hub.of("/internal/persist")]
    read_again = hub.of("/internal/candidate")
    assert len(stored) >= 2
    assert {r["model_version"] for r in stored} == {"v1"}
    assert [c["capture_id"] for c in read_again] == [r["capture_id"] for r in stored]
    assert {c["candidate_version"] for c in read_again} == {"v2"}
    for record, again in zip(stored, read_again, strict=True):
        assert again["detections"][0]["box"] == record["detections"][0]["box"]  # the same pixels
        assert again["capture_timestamp"] == record["capture_timestamp"]
        assert "candidate" not in json.dumps(record)  # nothing of the candidate rides on the live record
    order = [(path, p.get("capture_id") or p.get("record", {}).get("capture_id")) for path, p in hub.posts]
    for again in read_again:
        cid = again["capture_id"]
        assert order.index(("/internal/persist", cid)) < order.index(("/internal/candidate", cid))
    status = json.loads((tmp_path / release.CANDIDATE_STATUS_FILE).read_text(encoding="utf-8"))
    assert (status["candidate"], status["late"], status["errors"], status["stopped"]) == ("v2", 0, 0, None)
    assert status["windows"] >= 1
    started = release.read_worker_status(tmp_path)
    assert (started["live"], started["candidate"]) == ("v1", "v2")


def test_a_candidate_that_breaks_stops_itself_and_the_live_release_goes_on(tmp_path, monkeypatch):
    hub = run_worker(tmp_path, monkeypatch, ShadePipeline("candidate", fail=True))
    stored = [p["record"] for p in hub.of("/internal/persist")]
    assert len(stored) >= 2 and all(r["detections"] for r in stored)
    assert hub.of("/internal/candidate") == []
    status = json.loads((tmp_path / release.CANDIDATE_STATUS_FILE).read_text(encoding="utf-8"))
    assert status["stopped"] == "error: RuntimeError"
    windows = {r["capture_id"][:-2] for r in stored}  # captures of more than one moment: counting went on
    assert len(windows) >= 1
