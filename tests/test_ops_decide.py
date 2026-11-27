"""What the job runner on the counting machine does next (operations-loop design 5.2). Nothing here touches AWS, the
disk or the worker: next_steps only reads what it is given."""

from __future__ import annotations

import json
from datetime import datetime

from milk.release import Pointer as P
from ops.decide import NIGHT_FRAMES, NIGHT_LIMIT, next_steps, night_rate


def state(live="v1", previous=None, candidate=None, request=None, last_result=None):
    return {"live": live, "previous": previous, "candidate": candidate, "request": request, "last_result": last_result}


def row(status, created_at="2026-11-27T10:00:00+07:00", worker=None):
    return {"status": status, "created_at": created_at, "worker": worker or {"windows": 0, "late": 0, "errors": 0}}


def rows(**statuses):
    return {version: row(status) for version, status in statuses.items()}


def status(candidate, stopped=None, windows=0, late=0, errors=0, load_times=()):
    return {
        "candidate": candidate,
        "stopped": stopped,
        "windows": windows,
        "late": late,
        "errors": errors,
        "load_times": list(load_times),
    }


def night_captures(frames, boxes, version):
    """`frames` captures taken with the display away that `version` has read; `boxes` named boxes among them."""
    out = []
    for n in range(frames):
        found = [{"sku_id": "hot160", "conf": 0.9, "box": [1, 2, 3, 4]}] if n < boxes else []
        out.append(
            {"display_visible": False, "candidate_version": version, "candidate_detections_json": json.dumps(found)}
        )
    return out


def test_the_first_run_writes_the_state_and_registers_what_is_on_disk():
    steps = next_steps(P(live="v1"), {}, {}, ["v1"], None, None)
    assert steps == [("init_state", P(live="v1")), ("register", "v1")]


def test_a_new_release_on_disk_is_registered_then_started():
    steps = next_steps(P(live="v1"), state(live="v1"), {"v1": row("live")}, ["v1", "v2"], None, None)
    assert steps == [("register", "v2")]
    steps = next_steps(
        P(live="v1"), state(live="v1"), {"v1": row("live"), "v2": row("candidate")}, ["v1", "v2"], None, None
    )
    assert steps == [("start_parallel", "v2")]


def test_the_oldest_waiting_release_starts_first_and_only_one_runs():
    versions = {
        "v1": row("live"),
        "v3": row("candidate", created_at="2026-11-27T12:00:00+07:00"),
        "v2": row("candidate", created_at="2026-11-27T11:00:00+07:00"),
    }
    assert next_steps(P(live="v1"), state(), versions, ["v1", "v2", "v3"], None, None) == [("start_parallel", "v2")]
    running = {**versions, "v2": row("parallel")}
    args = (P(live="v1", candidate="v2"), state(candidate="v2"), running, ["v1", "v2", "v3"])
    assert next_steps(*args, None, None) == []


def test_a_waiting_release_whose_folder_is_gone_is_not_started():
    versions = {"v1": row("live"), "v2": row("candidate")}
    assert next_steps(P(live="v1"), state(), versions, ["v1"], None, None) == []


def test_a_start_that_was_cut_short_is_finished():
    # the pointer and the state already name the candidate, but its row never became "parallel"
    args = (P(live="v1", candidate="v2"), state(candidate="v2"), rows(v1="live", v2="candidate"), ["v1", "v2"])
    assert next_steps(*args, None, None) == [("start_parallel", "v2")]


def test_put_live_points_restarts_and_confirms():
    st = state(live="v1", candidate="v2", request={"id": "r1", "action": "put_live", "version_id": "v2"})
    steps = next_steps(P(live="v1", candidate="v2"), st, rows(v1="live", v2="parallel"), ["v1", "v2"], None, None)
    assert steps == [("point", P(live="v2", previous="v1")), ("restart_worker",), ("confirm", "r1", "v2")]


def test_a_request_half_done_is_finished_not_repeated():
    st = state(live="v1", candidate="v2", request={"id": "r1", "action": "put_live", "version_id": "v2"})
    steps = next_steps(P(live="v2", previous="v1"), st, rows(v1="live", v2="parallel"), ["v1", "v2"], None, None)
    assert steps == [("restart_worker",), ("confirm", "r1", "v2")]


def test_an_answered_request_is_not_done_again():
    request = {"id": "r1", "action": "put_live", "version_id": "v2"}
    st = state(live="v2", previous="v1", request=request, last_result={"request_id": "r1", "ok": True})
    assert next_steps(P(live="v2", previous="v1"), st, rows(v1="replaced", v2="live"), ["v1", "v2"], None, None) == []


def test_rollback_swaps_live_and_previous():
    st = state(live="v2", previous="v1", request={"id": "r2", "action": "rollback"})
    steps = next_steps(P(live="v2", previous="v1"), st, rows(v1="replaced", v2="live"), ["v1", "v2"], None, None)
    assert steps == [("point", P(live="v1", previous="v2")), ("restart_worker",), ("confirm", "r2", "v1")]


def test_discard_takes_the_candidate_out_and_keeps_the_live_release():
    st = state(live="v1", previous="v0", candidate="v2", request={"id": "r3", "action": "discard", "version_id": "v2"})
    pointer = P(live="v1", previous="v0", candidate="v2")
    steps = next_steps(pointer, st, rows(v0="replaced", v1="live", v2="parallel"), ["v0", "v1", "v2"], None, None)
    assert steps == [("point", P(live="v1", previous="v0")), ("restart_worker",), ("confirm", "r3", "v1")]


def test_a_stopped_or_night_drawing_candidate_is_stopped():
    st = state(live="v1", candidate="v2")
    args = (P(live="v1", candidate="v2"), st, rows(v1="live", v2="parallel"), ["v1", "v2"])
    assert next_steps(*args, status("v2", stopped="too_slow"), None)[0] == ("stop", "v2", "too_slow")
    assert next_steps(*args, None, 1.4)[0] == ("stop", "v2", "night boxes: 1.4 per 100 frames")
    assert next_steps(*args, None, 0.8) == []
    assert next_steps(*args, None, NIGHT_LIMIT) == []


def test_the_status_of_another_candidate_stops_nothing():
    st = state(live="v1", candidate="v2")
    args = (P(live="v1", candidate="v2"), st, rows(v1="live", v2="parallel"), ["v1", "v2"])
    assert next_steps(*args, status("v9", stopped="too_slow"), None) == []


def test_three_loads_within_fifteen_minutes_stop_the_candidate():
    st = state(live="v1", candidate="v2")
    args = (P(live="v1", candidate="v2"), st, rows(v1="live", v2="parallel"), ["v1", "v2"])
    quick = status(
        "v2", load_times=["2026-11-28T09:00:00+07:00", "2026-11-28T09:04:00+07:00", "2026-11-28T09:09:00+07:00"]
    )
    slow = status(
        "v2", load_times=["2026-11-27T09:00:00+07:00", "2026-11-28T05:50:00+07:00", "2026-11-28T09:09:00+07:00"]
    )
    assert next_steps(*args, quick, None)[0] == ("stop", "v2", "worker restarts")
    assert next_steps(*args, slow, None) == []


def test_a_request_about_a_candidate_that_was_stopped_is_answered_no():
    request = {"id": "r1", "action": "put_live", "version_id": "v2"}
    st = state(live="v1", candidate="v2", request=request)
    args = (P(live="v1", candidate="v2"), st, rows(v1="live", v2="parallel"), ["v1", "v2"])
    assert next_steps(*args, status("v2", stopped="error: RuntimeError"), None) == [
        ("stop", "v2", "error: RuntimeError"),
        ("fail", "r1", "The candidate was stopped: error: RuntimeError."),
    ]


def test_the_workers_numbers_are_copied_when_they_change():
    st = state(live="v1", candidate="v2")
    args = (P(live="v1", candidate="v2"), st, rows(v1="live", v2="parallel"), ["v1", "v2"])
    seen = status("v2", windows=12, late=1)
    assert next_steps(*args, seen, None) == [("sync_status", "v2", {"windows": 12, "late": 1, "errors": 0})]


def test_a_pointer_changed_by_hand_is_taken_as_the_truth():
    # live.json edited by hand (worker/README.md, "when milk-ops is down"): no request, and the table says otherwise
    steps = next_steps(
        P(live="v2", previous="v1"), state(live="v1"), rows(v1="live", v2="candidate"), ["v1", "v2"], None, None
    )
    assert steps == [("adopt", P(live="v2", previous="v1"))]


def test_night_rate_waits_for_a_hundred_frames():
    assert NIGHT_FRAMES == 100
    assert night_rate(night_captures(99, boxes=5, version="v2"), "v2") is None
    assert night_rate(night_captures(200, boxes=3, version="v2"), "v2") == 1.5


def test_night_rate_counts_only_frames_without_the_display_that_this_candidate_read():
    captures = night_captures(100, boxes=2, version="v2")
    captures += [{**c, "display_visible": True} for c in night_captures(50, boxes=50, version="v2")]
    captures += night_captures(50, boxes=50, version="v3")
    captures += [{"display_visible": False}] * 30  # the candidate never read these
    assert night_rate(captures, "v2") == 2.0


# --- after the whole-branch review -----------------------------------------------------------------------------

NOW = datetime.fromisoformat("2026-11-28T09:40:00+07:00")
EXPIRED = (
    "The counting machine did not get to this request within 30 minutes, so nothing was changed. "
    "Ask again if it is still wanted."
)


def test_a_request_left_for_more_than_half_an_hour_is_answered_no_not_carried_out():
    request = {"id": "r1", "action": "rollback", "at": "2026-11-28T09:00:00+07:00"}
    st = state(live="v2", previous="v1", request=request)
    args = (P(live="v2", previous="v1"), st, rows(v1="replaced", v2="live"), ["v1", "v2"], None, None)
    assert next_steps(*args, now=NOW) == [("fail", "r1", EXPIRED)]


def test_a_request_asked_a_few_minutes_ago_is_carried_out():
    request = {"id": "r1", "action": "rollback", "at": "2026-11-28T09:30:00+07:00"}
    st = state(live="v2", previous="v1", request=request)
    args = (P(live="v2", previous="v1"), st, rows(v1="replaced", v2="live"), ["v1", "v2"], None, None)
    assert next_steps(*args, now=NOW)[0] == ("point", P(live="v1", previous="v2"))


def test_an_old_request_that_was_already_begun_is_finished():
    # live.json already points where the request wanted: the switch has happened, only the answer is missing
    request = {"id": "r1", "action": "rollback", "at": "2026-11-28T09:00:00+07:00"}
    st = state(live="v2", previous="v1", request=request)
    args = (P(live="v1", previous="v2"), st, rows(v1="replaced", v2="live"), ["v1", "v2"], None, None)
    assert next_steps(*args, now=NOW) == [("restart_worker",), ("confirm", "r1", "v1")]


def test_discarding_a_release_that_is_not_running_only_marks_it():
    request = {"id": "r1", "action": "discard", "version_id": "v3"}
    st = state(live="v1", candidate="v2", request=request)
    args = (P(live="v1", candidate="v2"), st, rows(v1="live", v2="parallel", v3="candidate"), ["v1", "v2", "v3"])
    assert next_steps(*args, None, None) == [("mark_discarded", "r1", "v3")]


def test_a_worker_that_runs_something_other_than_live_json_names_is_restarted():
    st = state(live="v1", candidate="v2")
    args = (P(live="v1", candidate="v2"), st, rows(v1="live", v2="parallel"), ["v1", "v2"], None, None)
    without = {"live": "v1", "candidate": None, "started_at": "2026-11-28T02:00:00+00:00"}
    assert next_steps(*args, worker_started=without) == [("restart_worker",)]
    as_named = {"live": "v1", "candidate": "v2", "started_at": "2026-11-28T02:00:00+00:00"}
    assert next_steps(*args, worker_started=as_named) == []
    assert next_steps(*args, worker_started=None) == []  # no start record yet: nothing is known


def test_a_candidate_that_must_stop_is_stopped_rather_than_restarted_into():
    st = state(live="v1", candidate="v2")
    args = (P(live="v1", candidate="v2"), st, rows(v1="live", v2="parallel"), ["v1", "v2"])
    without = {"live": "v1", "candidate": None, "started_at": "2026-11-28T02:00:00+00:00"}
    steps = next_steps(*args, status("v2", stopped="error: FileNotFoundError"), None, worker_started=without)
    assert steps == [("stop", "v2", "error: FileNotFoundError")]
