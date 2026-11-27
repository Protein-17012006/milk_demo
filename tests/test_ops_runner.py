"""The job runner against a test table (moto) and a temp releases folder. The worker is a stand-in: `restart`
writes the start record a real worker writes once it has loaded what live.json names."""

from __future__ import annotations

import json

import boto3
import pytest
from moto import mock_aws
from test_release import write_release

from milk import release
from ops.runner import Runner

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
    assert runner.tick()[0] == ("stop", "v2", "night boxes: 100 per 100 frames")


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
