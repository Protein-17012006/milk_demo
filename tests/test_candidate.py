import json

import numpy as np
import pytest
from test_release import write_release

from milk import candidate, release
from milk.candidate import LATE_LIMIT, MAX_HELD, CandidateRunner, load_candidate
from milk.cvoutput import Detection

TS = "2026-11-27T10:00:05+07:00"


class FakePipeline:
    name = "fake"

    def __init__(self):
        self.seen = 0

    def detect(self, image):
        self.seen += 1
        return [Detection("original145", "Slide Original 145g", 0.9, (5, 5, 30, 40))]


class RaisingPipeline:
    name = "raising"

    def __init__(self, error):
        self.error = error

    def detect(self, image):
        raise self.error


class FakeClock:
    """Every reading is `step` seconds after the one before."""

    def __init__(self, step):
        self.now, self.step = 0.0, step

    def __call__(self):
        self.now += self.step
        return self.now


@pytest.fixture
def status_path(tmp_path):
    return tmp_path / candidate.STATUS_FILE


@pytest.fixture
def crop():
    return np.zeros((40, 60, 3), np.uint8)


def test_flush_returns_one_payload_per_held_frame(status_path, crop):
    runner = CandidateRunner(FakePipeline(), "v2", status_path, clock=FakeClock(step=1.0))
    runner.hold("CAP-1", "2026-11-27T10:00:05+07:00", "CAM-S01-A", crop, (10, 20))
    runner.hold("CAP-2", "2026-11-27T10:00:15+07:00", "CAM-S01-A", crop, (10, 20))
    payloads = runner.flush(deadline=100.0)
    assert [p["capture_id"] for p in payloads] == ["CAP-1", "CAP-2"]
    assert payloads[0]["candidate_version"] == "v2"
    assert payloads[0]["camera_id"] == "CAM-S01-A"
    assert payloads[0]["capture_timestamp"] == "2026-11-27T10:00:05+07:00"
    assert payloads[0]["detections"] == [{"sku_id": "original145", "conf": 0.9, "box": [15, 25, 30, 40]}]
    assert isinstance(payloads[0]["processing_time_ms"], int)
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert (status["candidate"], status["windows"], status["late"], status["stopped"]) == ("v2", 1, 0, None)


def test_the_candidate_reads_a_copy_not_the_live_frame(status_path, crop):
    seen = []

    class Remembering(FakePipeline):
        def detect(self, image):
            seen.append(image.copy())
            return []

    runner = CandidateRunner(Remembering(), "v2", status_path)
    runner.hold("CAP-1", TS, "CAM-S01-A", crop, (0, 0))
    crop[:] = 255  # the worker goes on to blur and reuse its own buffer
    runner.flush(deadline=1e12)
    assert int(seen[0].max()) == 0


def test_three_late_windows_in_a_row_stop_the_candidate(status_path, crop):
    clock = FakeClock(step=10.0)  # every reading of the clock is 10 s later
    runner = CandidateRunner(FakePipeline(), "v2", status_path, clock=clock)
    for n in range(LATE_LIMIT):
        runner.hold(f"CAP-{n}a", TS, "CAM-S01-A", crop, (0, 0))
        runner.hold(f"CAP-{n}b", TS, "CAM-S01-A", crop, (0, 0))
        runner.flush(deadline=clock.now + 5.0)
    assert runner.stopped == "too_slow"
    assert json.loads(status_path.read_text(encoding="utf-8"))["late"] == 3
    runner.hold("CAP-x", TS, "CAM-S01-A", crop, (0, 0))
    assert runner.flush(deadline=1e9) == []


def test_a_window_read_in_time_clears_the_late_count(status_path, crop):
    clock = FakeClock(step=10.0)
    runner = CandidateRunner(FakePipeline(), "v2", status_path, clock=clock)
    for _ in range(LATE_LIMIT - 1):
        runner.hold("CAP-late", TS, "CAM-S01-A", crop, (0, 0))
        runner.flush(deadline=clock.now + 5.0)
    runner.hold("CAP-ok", TS, "CAM-S01-A", crop, (0, 0))
    assert len(runner.flush(deadline=clock.now + 1000.0)) == 1
    runner.hold("CAP-late", TS, "CAM-S01-A", crop, (0, 0))
    runner.flush(deadline=clock.now + 5.0)
    assert runner.stopped is None


def test_an_error_stops_the_candidate_and_never_escapes(status_path, crop):
    runner = CandidateRunner(RaisingPipeline(RuntimeError("boom")), "v2", status_path)
    runner.hold("CAP-1", TS, "CAM-S01-A", crop, (0, 0))
    assert runner.flush(deadline=1e12) == []
    assert runner.stopped == "error: RuntimeError"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert (status["errors"], status["stopped"]) == (1, "error: RuntimeError")


def test_a_thirteenth_frame_is_not_held(status_path, crop):
    runner = CandidateRunner(FakePipeline(), "v2", status_path)
    for n in range(MAX_HELD + 1):
        runner.hold(f"CAP-{n}", TS, "CAM-S01-A", crop, (0, 0))
    assert len(runner.flush(deadline=1e12)) == 12


def test_flush_in_steps_finishes_the_window_once(status_path, crop):
    pipe = FakePipeline()
    runner = CandidateRunner(pipe, "v2", status_path, clock=FakeClock(step=1.0))
    for n in range(3):
        runner.hold(f"CAP-{n}", TS, "CAM-S01-A", crop, (0, 0))
    got = [runner.flush(deadline=100.0, limit=1) for _ in range(4)]
    assert [len(g) for g in got] == [1, 1, 1, 0]
    assert json.loads(status_path.read_text(encoding="utf-8"))["windows"] == 1


def test_flush_with_nothing_held_writes_nothing(status_path):
    runner = CandidateRunner(FakePipeline(), "v2", status_path)
    assert runner.flush(deadline=1e12) == []
    assert not status_path.exists()


def write_pointer_with_candidate(root, live, candidate_id, env=None):
    write_release(root, live, env={"MILK_PIPELINE": "null"})
    if candidate_id:
        write_release(root, candidate_id, env=env or {"MILK_PIPELINE": "null"})
    release.write_pointer(root, release.Pointer(live=live, previous=None, candidate=candidate_id))


def test_load_candidate_is_none_when_reading_continuously(tmp_path):
    write_pointer_with_candidate(tmp_path, "v1", "v2")
    assert load_candidate(tmp_path, {}, "", sampled=False) is None


def test_load_candidate_is_none_without_a_candidate(tmp_path):
    write_pointer_with_candidate(tmp_path, "v1", None)
    assert load_candidate(tmp_path, {}, "", sampled=True) is None
    assert not (tmp_path / candidate.STATUS_FILE).exists()


def test_load_candidate_gives_the_candidate_its_own_settings(tmp_path, monkeypatch):
    write_pointer_with_candidate(tmp_path, "v1", "v2", env={"MILK_PIPELINE": "null", "MILK_SLIDE_CONF": "0.35"})
    seen = {}

    def fake_load(kind, models_dir, env=None):
        seen.update(kind=kind, env=dict(env))
        return FakePipeline()

    monkeypatch.setattr(candidate, "load_pipeline", fake_load)
    base = {
        "MILK_HUB_URL": "https://hub",
        "MILK_PIPELINE": "long+slide",
        "MILK_SLIDE_CONF": "0.25",
        "MILK_LONG_TILE": "1280",
    }
    runner = load_candidate(tmp_path, base, "", sampled=True)
    assert runner is not None and runner.version == "v2"
    assert seen["kind"] == "null"
    assert seen["env"] == {
        "MILK_HUB_URL": "https://hub",
        "MILK_PIPELINE": "null",
        "MILK_SLIDE_CONF": "0.35",
        "MILK_MODEL_VERSION": "v2",
    }


def test_a_candidate_that_cannot_load_is_reported_and_live_goes_on(tmp_path, monkeypatch):
    write_pointer_with_candidate(tmp_path, "v1", "v2")

    def broken(kind, models_dir, env=None):
        raise FileNotFoundError("weights not found")

    monkeypatch.setattr(candidate, "load_pipeline", broken)
    assert load_candidate(tmp_path, {}, "", sampled=True) is None
    status = json.loads((tmp_path / candidate.STATUS_FILE).read_text(encoding="utf-8"))
    assert (status["candidate"], status["stopped"]) == ("v2", "error: FileNotFoundError")


def test_a_candidate_whose_release_is_missing_is_reported(tmp_path):
    write_release(tmp_path, "v1", env={"MILK_PIPELINE": "null"})
    release.write_pointer(tmp_path, release.Pointer(live="v1", previous=None, candidate="gone"))
    assert load_candidate(tmp_path, {}, "", sampled=True) is None
    status = json.loads((tmp_path / candidate.STATUS_FILE).read_text(encoding="utf-8"))
    assert (status["candidate"], status["stopped"]) == ("gone", "error: ValueError")


def test_each_load_is_remembered_up_to_five(tmp_path):
    write_pointer_with_candidate(tmp_path, "v1", "v2")
    for _ in range(7):
        assert load_candidate(tmp_path, {}, "", sampled=True) is not None
    status = json.loads((tmp_path / candidate.STATUS_FILE).read_text(encoding="utf-8"))
    assert len(status["load_times"]) == 5


def test_load_times_start_again_for_another_candidate(tmp_path):
    write_pointer_with_candidate(tmp_path, "v1", "v2")
    load_candidate(tmp_path, {}, "", sampled=True)
    load_candidate(tmp_path, {}, "", sampled=True)
    write_release(tmp_path, "v3", env={"MILK_PIPELINE": "null"})
    release.write_pointer(tmp_path, release.Pointer(live="v1", previous=None, candidate="v3"))
    load_candidate(tmp_path, {}, "", sampled=True)
    status = json.loads((tmp_path / candidate.STATUS_FILE).read_text(encoding="utf-8"))
    assert (status["candidate"], len(status["load_times"])) == ("v3", 1)


def read_status(root):
    return json.loads((root / candidate.STATUS_FILE).read_text(encoding="utf-8"))


def test_the_attempt_to_load_is_written_down_before_the_load_begins(tmp_path, monkeypatch):
    write_pointer_with_candidate(tmp_path, "v1", "v2")
    during = {}

    def loading(kind, models_dir, env=None):
        during.update(read_status(tmp_path))  # what a worker that died right here would leave behind
        return FakePipeline()

    monkeypatch.setattr(candidate, "load_pipeline", loading)
    assert load_candidate(tmp_path, {}, "", sampled=True) is not None
    assert (during["candidate"], during["loads_unfinished"], len(during["load_times"])) == ("v2", 1, 1)
    assert read_status(tmp_path)["loads_unfinished"] == 0


def test_a_candidate_the_worker_died_loading_twice_is_not_loaded_a_third_time(tmp_path, monkeypatch):
    write_pointer_with_candidate(tmp_path, "v1", "v2")
    left = {
        "candidate": "v2",
        "windows": 0,
        "late": 0,
        "errors": 0,
        "load_times": [],
        "loads_unfinished": 2,
        "stopped": None,
    }
    (tmp_path / candidate.STATUS_FILE).write_text(json.dumps(left), encoding="utf-8")
    loads = []
    monkeypatch.setattr(candidate, "load_pipeline", lambda *args, **kwargs: loads.append(1) or FakePipeline())
    assert load_candidate(tmp_path, {}, "", sampled=True) is None
    assert loads == []
    assert read_status(tmp_path)["stopped"] == "error: the worker died twice while loading it"


def test_unfinished_loads_of_another_candidate_do_not_count(tmp_path):
    write_pointer_with_candidate(tmp_path, "v1", "v2")
    left = {
        "candidate": "v9",
        "windows": 0,
        "late": 0,
        "errors": 0,
        "load_times": [],
        "loads_unfinished": 2,
        "stopped": None,
    }
    (tmp_path / candidate.STATUS_FILE).write_text(json.dumps(left), encoding="utf-8")
    assert load_candidate(tmp_path, {}, "", sampled=True) is not None
    assert read_status(tmp_path)["loads_unfinished"] == 0


def test_a_candidate_that_failed_to_load_did_not_die_loading(tmp_path, monkeypatch):
    write_pointer_with_candidate(tmp_path, "v1", "v2")

    def broken(kind, models_dir, env=None):
        raise FileNotFoundError("weights not found")

    monkeypatch.setattr(candidate, "load_pipeline", broken)
    for _ in range(3):
        assert load_candidate(tmp_path, {}, "", sampled=True) is None
    status = read_status(tmp_path)
    assert (status["stopped"], status["loads_unfinished"]) == ("error: FileNotFoundError", 0)


def test_a_candidate_not_run_because_the_stream_is_read_all_the_time_says_so(tmp_path):
    write_pointer_with_candidate(tmp_path, "v1", "v2")
    assert load_candidate(tmp_path, {}, "", sampled=False) is None
    status = read_status(tmp_path)
    assert (status["candidate"], status["stopped"]) == ("v2", "not run: the worker reads the stream continuously")
