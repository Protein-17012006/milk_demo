"""Which requests the Model page may make about model versions (operations-loop design 5.2)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from model_versions import STATE_ID, STATUSES, can  # noqa: E402


def test_put_live_needs_a_parallel_run_and_a_verdict():
    state = {"live": "v1", "previous": None, "candidate": "v2", "request": None}
    assert can("put_live", state, {"status": "parallel"}, "better") is None
    assert can("put_live", state, {"status": "parallel"}, "no_difference") is None
    assert can("put_live", state, {"status": "parallel"}, "waiting") is not None
    assert can("put_live", state, {"status": "parallel"}, "worse") is not None
    assert can("put_live", state, {"status": "candidate"}, "better") is not None
    assert can("put_live", state, None, "better") is not None
    assert can("rollback", state, None, None) is not None
    assert can("rollback", {**state, "previous": "v0"}, None, None) is None


def test_discard_only_a_waiting_or_running_candidate():
    state = {"live": "v1", "previous": None, "candidate": "v2", "request": None}
    assert can("discard", state, {"status": "candidate"}, None) is None
    assert can("discard", state, {"status": "parallel"}, "worse") is None
    assert can("discard", state, {"status": "live"}, None) is not None
    assert can("discard", state, None, None) is not None


def test_one_request_at_a_time():
    state = {"live": "v1", "previous": "v0", "candidate": None, "request": {"id": "r1"}, "last_result": None}
    assert can("rollback", state, None, None) == "Another request is still running."
    done = {**state, "last_result": {"request_id": "r1", "ok": True}}
    assert can("rollback", done, None, None) is None
    earlier = {**state, "last_result": {"request_id": "r0", "ok": True}}
    assert can("rollback", earlier, None, None) == "Another request is still running."


def test_an_unknown_action_is_refused():
    assert can("retrain", {"live": "v1"}, None, None) is not None


def test_names_the_runner_and_the_website_share():
    assert STATE_ID == "#state"
    assert STATUSES == ("candidate", "parallel", "live", "replaced", "discarded", "stopped")
