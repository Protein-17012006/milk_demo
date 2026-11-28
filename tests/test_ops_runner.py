"""The job runner against a test table (moto) and a temp releases folder. The worker is a stand-in: `restart`
writes the start record a real worker writes once it has loaded what live.json names."""

from __future__ import annotations

import json

import boto3
import pytest
from moto import mock_aws
from test_release import write_release

from milk import release
from ops.decide import night_rate
from ops.runner import Runner, night_reader_for

REGION = "ap-southeast-1"
CAMERA = "CAM-S01-A"
STATE = "#state"


@pytest.fixture
def table(monkeypatch):
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(key, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    with mock_aws():
        yield boto3.resource("dynamodb", region_name=REGION).create_table(
            TableName="test-model-versions",
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[
                {"AttributeName": "camera_id", "KeyType": "HASH"},
                {"AttributeName": "version_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "camera_id", "AttributeType": "S"},
                {"AttributeName": "version_id", "AttributeType": "S"},
            ],
        )


class Worker:
    """Stands in for the counting worker: a restart loads what live.json names and says so."""

    def __init__(self, root, loads=True):
        self.root, self.loads, self.restarts = root, loads, 0

    def restart(self):
        self.restarts += 1
        if self.loads:
            pointer = release.read_pointer(self.root)
            release.write_worker_status(self.root, live=pointer.live, candidate=pointer.candidate)


@pytest.fixture
def root(tmp_path):
    write_release(tmp_path, "v1", env={"MILK_PIPELINE": "null"}, kind="baseline")
    release.write_pointer(tmp_path, release.Pointer(live="v1"))
    return tmp_path


def runner_for(root, table, worker, **kwargs):
    kwargs.setdefault("confirm_timeout_s", 5.0)
    kwargs.setdefault("poll_s", 0.01)
    return Runner(root, CAMERA, table, restart=worker.restart, **kwargs)


def row(table, version_id):
    return table.get_item(Key={"camera_id": CAMERA, "version_id": version_id}).get("Item")


def ask(table, action, version_id=None, request_id="r1"):
    request = {"id": request_id, "action": action, "by": "admin@example.com", "at": "2026-11-28T09:00:00+07:00"}
    if version_id:
        request["version_id"] = version_id
    table.update_item(
        Key={"camera_id": CAMERA, "version_id": STATE},
        UpdateExpression="SET #r = :r",
        ExpressionAttributeNames={"#r": "request"},
        ExpressionAttributeValues={":r": request},
    )


def running_in_parallel(root, table, worker):
    """v1 live and v2 running beside it, the way the runner itself gets there."""
    runner = runner_for(root, table, worker)
    runner.tick()
    write_release(root, "v2", env={"MILK_PIPELINE": "null"}, kind="rules", parent="v1")
    runner.tick()  # registers v2
    runner.tick()  # starts it
    return runner


def test_the_first_turn_writes_the_state_and_the_live_release(root, table):
    worker = Worker(root)
    steps = runner_for(root, table, worker).tick()
    assert [s[0] for s in steps] == ["init_state", "register"]
    assert (row(table, STATE)["live"], row(table, "v1")["status"], row(table, "v1")["kind"]) == (
        "v1",
        "live",
        "baseline",
    )
    assert worker.restarts == 0


def test_a_new_release_is_registered_with_its_criteria_then_runs_beside_the_live_one(root, table):
    worker = Worker(root)
    runner = running_in_parallel(root, table, worker)
    v2 = row(table, "v2")
    assert (v2["status"], v2["kind"], v2["parent"]) == ("parallel", "rules", "v1")
    assert (int(v2["criteria"]["min_days"]), int(v2["criteria"]["min_frames"])) == (3, 30)
    assert v2["parallel_started_at"] and v2["created_at"]
    assert row(table, STATE)["candidate"] == "v2"
    assert release.read_pointer(root) == release.Pointer(live="v1", candidate="v2")
    assert worker.restarts == 1
    assert runner.tick() == []  # nothing more to do, and no second restart
    assert worker.restarts == 1


def test_put_live_switches_the_worker_and_answers_the_request(root, table):
    worker = Worker(root)
    runner = running_in_parallel(root, table, worker)
    ask(table, "put_live", "v2")
    steps = runner.tick()
    assert [s[0] for s in steps] == ["point", "restart_worker", "confirm"]
    assert release.read_pointer(root) == release.Pointer(live="v2", previous="v1")
    state = row(table, STATE)
    assert (state["live"], state["previous"], state.get("candidate")) == ("v2", "v1", None)
    assert (state["last_result"]["request_id"], state["last_result"]["ok"]) == ("r1", True)
    v2 = row(table, "v2")
    assert (v2["status"], v2["decided_by"], v2["decided_at"]) == (
        "live",
        "admin@example.com",
        "2026-11-28T09:00:00+07:00",
    )
    assert row(table, "v1")["status"] == "replaced"
    assert worker.restarts == 2
    assert runner.tick() == []


def test_roll_back_returns_to_the_release_before(root, table):
    worker = Worker(root)
    runner = running_in_parallel(root, table, worker)
    ask(table, "put_live", "v2")
    runner.tick()
    ask(table, "rollback", request_id="r2")
    runner.tick()
    assert release.read_pointer(root) == release.Pointer(live="v1", previous="v2")
    state = row(table, STATE)
    assert (state["live"], state["previous"], state["last_result"]["request_id"]) == ("v1", "v2", "r2")
    assert (row(table, "v1")["status"], row(table, "v2")["status"]) == ("live", "replaced")


def test_discard_takes_the_candidate_out(root, table):
    worker = Worker(root)
    runner = running_in_parallel(root, table, worker)
    ask(table, "discard", "v2")
    runner.tick()
    assert release.read_pointer(root) == release.Pointer(live="v1")
    assert row(table, "v2")["status"] == "discarded" and "candidate" not in row(table, STATE)
    assert row(table, STATE)["last_result"]["ok"] is True


def test_a_worker_that_does_not_come_up_with_the_release_is_reported_not_rolled_back(root, table):
    worker = Worker(root)
    runner = running_in_parallel(root, table, worker)
    worker.loads = False  # from now on the worker never says it started
    ask(table, "put_live", "v2")
    runner_for(root, table, worker, confirm_timeout_s=0.05).tick()
    result = row(table, STATE)["last_result"]
    assert (result["request_id"], result["ok"]) == ("r1", False)
    assert "v2" in result["message"]
    assert release.read_pointer(root) == release.Pointer(live="v2", previous="v1")  # left for a person to decide
    assert (row(table, STATE)["live"], row(table, "v2")["status"]) == ("v1", "parallel")
    del runner


def test_a_candidate_the_worker_stopped_is_taken_out_with_the_reason(root, table):
    worker = Worker(root)
    runner = running_in_parallel(root, table, worker)
    status = {"candidate": "v2", "windows": 4, "late": 3, "errors": 0, "load_times": [], "stopped": "too_slow"}
    (root / "candidate-status.json").write_text(json.dumps(status), encoding="utf-8")
    steps = runner.tick()
    assert steps[0] == ("stop", "v2", "too_slow")
    v2 = row(table, "v2")
    assert (v2["status"], v2["stopped_reason"]) == ("stopped", "too_slow")
    assert "candidate" not in row(table, STATE)
    assert release.read_pointer(root) == release.Pointer(live="v1")
    assert worker.restarts == 2


def test_the_workers_numbers_reach_the_candidates_row(root, table):
    worker = Worker(root)
    runner = running_in_parallel(root, table, worker)
    status = {"candidate": "v2", "windows": 12, "late": 1, "errors": 0, "load_times": [], "stopped": None}
    (root / "candidate-status.json").write_text(json.dumps(status), encoding="utf-8")
    runner.tick()
    assert {k: int(v) for k, v in row(table, "v2")["worker"].items()} == {"windows": 12, "late": 1, "errors": 0}


def test_a_candidate_that_draws_at_night_is_stopped(root, table):
    worker = Worker(root)
    running_in_parallel(root, table, worker)
    night = [
        {"display_visible": False, "candidate_version": "v2", "candidate_detections_json": '[{"sku_id": "hot160"}]'}
    ] * 100
    runner = runner_for(root, table, worker, night_reader=lambda version, since: night)
    assert runner.tick()[0] == ("stop", "v2", "night boxes: 100 more per 100 frames than the live version")


def test_the_night_reader_brings_the_live_boxes_of_the_frames_the_candidate_read(table):
    captures = boto3.resource("dynamodb", region_name=REGION).create_table(
        TableName="test-captures",
        BillingMode="PAY_PER_REQUEST",
        KeySchema=[
            {"AttributeName": "camera_id", "KeyType": "HASH"},
            {"AttributeName": "capture_id", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "camera_id", "AttributeType": "S"},
            {"AttributeName": "capture_id", "AttributeType": "S"},
        ],
    )
    boxes = json.dumps([{"sku_id": "hot160", "conf": 0.5, "box": [1, 2, 3, 4]}])

    def put(capture_id, visible, version):
        item = {"camera_id": CAMERA, "capture_id": capture_id, "display_visible": visible, "candidate_version": version}
        captures.put_item(Item={**item, "candidate_detections_json": boxes, "detections_json": boxes})

    put("CAP-S01-20261128-210504", False, "v2")
    put("CAP-S01-20261128-140504", True, "v2")  # the display was there
    put("CAP-S01-20261128-210509", False, "v3")  # another candidate's
    put("CAP-S01-20261127-210504", False, "v2")  # before the day the run started
    frames = night_reader_for(captures, CAMERA, "S01")("v2", "2026-11-28T09:00:00+07:00")
    assert [f.get("detections_json") for f in frames] == [boxes]
    assert night_rate(frames * 100, "v2") == 0.0  # the same boxes as the live release: nothing more at night


def test_a_release_folder_that_cannot_be_read_is_shown_as_stopped_not_retried(root, table):
    worker = Worker(root)
    runner = runner_for(root, table, worker)
    runner.tick()
    (root / "broken").mkdir()
    (root / "broken" / "release.json").write_text("{", encoding="utf-8")
    runner.tick()
    broken = row(table, "broken")
    assert broken["status"] == "stopped" and "release.json" in broken["stopped_reason"]
    assert runner.tick() == []


def test_every_turn_leaves_a_sign_of_life(root, table):
    runner = runner_for(root, table, Worker(root))
    runner.tick()
    runner.tick()
    assert row(table, STATE)["runner_seen_at"]


def test_no_pointer_means_nothing_is_done(tmp_path, table):
    assert runner_for(tmp_path, table, Worker(tmp_path)).tick() == []
    assert row(table, STATE) is None


# --- after the whole-branch review -----------------------------------------------------------------------------


def fail_once(runner, when):
    """Makes the runner's next table write for which `when(version_id, values)` is true fail, once."""
    real, state = runner._set, {"failed": False}

    def flaky(version_id, values, *args, **kwargs):
        if not state["failed"] and when(version_id, values):
            state["failed"] = True
            raise RuntimeError("the table was away for a moment")
        return real(version_id, values, *args, **kwargs)

    runner._set = flaky
    return state


def test_a_roll_back_cut_short_before_its_last_write_is_finished_not_undone(root, table):
    worker = Worker(root)
    runner = running_in_parallel(root, table, worker)
    ask(table, "put_live", "v2")
    runner.tick()
    ask(table, "rollback", request_id="r2")
    cut = fail_once(runner, lambda version_id, values: version_id == STATE and "last_result" in values)
    runner.tick()  # the worker is back on v1, but the answer could not be written
    assert cut["failed"]
    runner.tick()
    assert release.read_pointer(root) == release.Pointer(live="v1", previous="v2")
    state = row(table, STATE)
    assert (state["live"], state["previous"]) == ("v1", "v2")
    assert (state["last_result"]["request_id"], state["last_result"]["ok"]) == ("r2", True)
    assert (row(table, "v1")["status"], row(table, "v2")["status"]) == ("live", "replaced")


def test_put_live_cut_short_before_its_last_write_keeps_the_way_back(root, table):
    worker = Worker(root)
    runner = running_in_parallel(root, table, worker)
    ask(table, "put_live", "v2")
    fail_once(runner, lambda version_id, values: version_id == STATE and "last_result" in values)
    runner.tick()
    runner.tick()
    state = row(table, STATE)
    assert (state["live"], state["previous"], state["last_result"]["ok"]) == ("v2", "v1", True)


def test_a_roll_back_takes_a_running_candidate_out_and_says_why(root, table):
    worker = Worker(root)
    runner = running_in_parallel(root, table, worker)
    ask(table, "put_live", "v2")
    runner.tick()
    write_release(root, "v3", env={"MILK_PIPELINE": "null"}, kind="rules", parent="v2")
    runner.tick()
    runner.tick()
    assert row(table, "v3")["status"] == "parallel"
    ask(table, "rollback", request_id="r2")
    runner.tick()
    assert release.read_pointer(root) == release.Pointer(live="v1", previous="v2")
    v3 = row(table, "v3")
    assert (v3["status"], v3["stopped_reason"]) == ("stopped", "taken out when v1 went live")
    assert "candidate" not in row(table, STATE)


def test_discarding_a_waiting_release_leaves_the_running_one_alone(root, table):
    worker = Worker(root)
    runner = running_in_parallel(root, table, worker)
    write_release(root, "v3", env={"MILK_PIPELINE": "null"}, kind="rules", parent="v1")
    runner.tick()  # v3 is registered and waits: v2 is running
    restarts = worker.restarts
    ask(table, "discard", "v3")
    assert runner.tick() == [("mark_discarded", "r1", "v3")]
    assert (row(table, "v3")["status"], row(table, "v2")["status"]) == ("discarded", "parallel")
    assert release.read_pointer(root) == release.Pointer(live="v1", candidate="v2")
    assert row(table, STATE)["last_result"]["ok"] is True and worker.restarts == restarts


def test_a_candidate_the_worker_does_not_come_up_with_is_taken_out_again(root, table):
    worker = Worker(root)
    runner = runner_for(root, table, worker, confirm_timeout_s=0.05)
    runner.tick()
    write_release(root, "v2", env={"MILK_PIPELINE": "null"}, kind="rules", parent="v1")
    runner.tick()
    worker.loads = False  # the worker never says it started with the candidate
    runner.tick()
    v2 = row(table, "v2")
    assert (v2["status"], v2["stopped_reason"]) == ("stopped", "the worker did not start with it")
    assert release.read_pointer(root) == release.Pointer(live="v1")
    assert "candidate" not in row(table, STATE)
    assert worker.restarts == 2  # once with the candidate, once more without it


def test_a_restart_that_fails_leaves_the_release_waiting_and_is_tried_again(root, table):
    worker = Worker(root)
    runner = runner_for(root, table, worker)
    runner.tick()
    write_release(root, "v2", env={"MILK_PIPELINE": "null"}, kind="rules", parent="v1")
    runner.tick()
    real_restart, calls = worker.restart, {"n": 0}

    def breaks_once():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("Start-ScheduledTask failed")
        real_restart()

    runner._restart_worker_now = breaks_once
    runner.tick()
    assert row(table, "v2")["status"] == "candidate"
    assert release.read_pointer(root) == release.Pointer(live="v1")
    runner.tick()
    assert row(table, "v2")["status"] == "parallel"
    assert release.read_pointer(root) == release.Pointer(live="v1", candidate="v2")


def test_a_worker_found_running_without_the_candidate_is_restarted_once(root, table):
    worker = Worker(root)
    runner = running_in_parallel(root, table, worker)
    release.write_worker_status(root, live="v1", candidate=None)  # as if a later restart had not taken the candidate
    restarts = worker.restarts
    assert runner.tick() == [("restart_worker",)]
    assert worker.restarts == restarts + 1
    assert runner.tick() == []


def test_a_restart_that_changes_nothing_is_not_repeated_every_minute(root, table):
    worker = Worker(root)
    runner = running_in_parallel(root, table, worker)
    worker.loads = False
    release.write_worker_status(root, live="v1", candidate=None)
    assert runner.tick() == [("restart_worker",)]
    assert runner.tick() == []  # asked a moment ago: wait before asking again
