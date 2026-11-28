"""What the job runner does next, from what it has just read. Nothing here touches AWS, the disk or the worker.

The runner reads four things each turn: live.json (the pointer: what the worker loads at its next start), the
camera's rows of the model-versions table (the state row and one row per release), the release folders on disk, and
candidate-status.json (what the worker says about the candidate it runs). next_steps turns them into an ordered list
of steps; the runner carries them out one by one and reads everything again on its next turn. Every step is safe to
do twice, so a runner that died half-way is finished, not repeated, by the next turn.

Steps:
    ("init_state", pointer)          first run: write the state row from the pointer
    ("register", id)                 a release folder without a row: write its row
    ("adopt", pointer)               live.json was changed by hand: the table follows the disk
    ("start_parallel", id)           put a waiting release beside the live one
    ("stop", id, reason)             take a candidate out: it stopped itself, restarts the worker, or draws at night
                                     more than the live release does
    ("fail", request_id, message)    answer a request "no"
    ("mark_discarded", request_id, id) discard a release that is not running: only its row changes
    ("point", pointer)               write live.json for the request in hand
    ("restart_worker",)              for a request; or alone, when the worker runs something else than live.json names
    ("confirm", request_id, version) wait for the worker to say it runs `version`, then answer the request
    ("sync_status", id, numbers)     copy the worker's numbers about the candidate to its row
"""

from __future__ import annotations

import json
from datetime import datetime

from model_versions import request_running

from milk.release import Pointer

NIGHT_FRAMES = 100  # frames without the display a candidate must have read before the night rule speaks
NIGHT_LIMIT = 1.0  # named boxes per 100 such frames beyond the live release's; more stops the candidate
RESTARTS = 3
RESTART_WINDOW_S = 15 * 60
REQUEST_TTL_S = 30 * 60  # a request nobody began within this time is answered no, not carried out late
EXPIRED = (
    "The counting machine did not get to this request within 30 minutes, so nothing was changed. "
    "Ask again if it is still wanted."
)
NUMBERS = ("windows", "late", "errors")


def _named(raw) -> int:
    found = json.loads(raw) if isinstance(raw, str) else (raw or [])
    return sum(1 for d in found if d.get("sku_id"))


def night_rate(captures: list[dict], version: str) -> float | None:
    """Named boxes per 100 frames that `version` draws beyond the live release on the same frame, over the captures
    taken with the display away that `version` has read; None until there are NIGHT_FRAMES of them. The live release
    draws boxes there too (on 27/11 21:05, seven on the bare floor in a motorbike's light), so a candidate is held to
    the live release, not to zero."""
    frames = [
        c
        for c in captures
        if c.get("display_visible") is False
        and c.get("candidate_version") == version
        and c.get("candidate_detections_json") is not None
    ]
    if len(frames) < NIGHT_FRAMES:
        return None
    more = sum(max(0, _named(c["candidate_detections_json"]) - _named(c.get("detections_json"))) for c in frames)
    return 100.0 * more / len(frames)


def _of_state(state: dict) -> Pointer:
    return Pointer(
        live=state.get("live") or "", previous=state.get("previous") or None, candidate=state.get("candidate") or None
    )


def target(state: dict, request: dict) -> Pointer:
    """Where live.json must point once the request is done, worked out from the table's state (which changes only
    when the request has been answered), never from the pointer itself."""
    action = request.get("action")
    if action == "put_live":
        return Pointer(live=request["version_id"], previous=state.get("live") or None)
    if action == "rollback":
        return Pointer(live=state["previous"], previous=state.get("live") or None)
    return Pointer(live=state["live"], previous=state.get("previous") or None)  # discard


def _restarting(status: dict) -> bool:
    times = [datetime.fromisoformat(t) for t in (status.get("load_times") or [])[-RESTARTS:]]
    return len(times) == RESTARTS and (max(times) - min(times)).total_seconds() <= RESTART_WINDOW_S


def _why_stop(candidate: str, status: dict | None, night: float | None) -> str | None:
    if status and status.get("candidate") == candidate:
        if status.get("stopped"):
            return str(status["stopped"])
        if _restarting(status):
            return "worker restarts"
    if night is not None and night > NIGHT_LIMIT:
        return f"night boxes: {night:g} more per 100 frames than the live version"
    return None


def _expired(request: dict, now: datetime | None) -> bool:
    if now is None or not request.get("at"):
        return False
    try:
        return (now - datetime.fromisoformat(request["at"])).total_seconds() > REQUEST_TTL_S
    except (TypeError, ValueError):
        return False


def _runs_what_is_named(worker_started: dict | None, pointer: Pointer) -> bool:
    """Whether the worker's start record names the releases live.json names; no record means nothing is known."""
    if not worker_started:
        return True
    return (worker_started.get("live"), worker_started.get("candidate") or None) == (pointer.live, pointer.candidate)


def next_steps(
    pointer: Pointer,
    state: dict,
    versions: dict[str, dict],
    on_disk: list[str],
    worker_status: dict | None,
    night: float | None,
    *,
    now: datetime | None = None,
    worker_started: dict | None = None,
) -> list[tuple]:
    registers = [("register", release_id) for release_id in sorted(on_disk) if release_id not in versions]
    if not state:
        return [("init_state", pointer), *registers]
    steps: list[tuple] = list(registers)
    candidate = state.get("candidate") or None
    why_stop = _why_stop(candidate, worker_status, night) if candidate else None

    if request_running(state):
        request = state["request"]
        if why_stop and request.get("version_id") == candidate:
            failed = ("fail", request["id"], f"The candidate was stopped: {why_stop}.")
            return [*steps, ("stop", candidate, why_stop), failed]
        if request.get("action") == "discard" and request.get("version_id") != candidate:
            return [*steps, ("mark_discarded", request["id"], request["version_id"])]
        goal = target(state, request)
        if pointer != goal:
            if _expired(request, now):  # not begun in time: the situation it was asked in may be gone
                return [*steps, ("fail", request["id"], EXPIRED)]
            steps.append(("point", goal))
        return [*steps, ("restart_worker",), ("confirm", request["id"], goal.live)]

    if pointer != _of_state(state):
        return [*steps, ("adopt", pointer)]

    if candidate:
        row = versions.get(candidate) or {}
        if row.get("status") == "candidate" and candidate in on_disk:
            return [*steps, ("start_parallel", candidate)]
        if why_stop:
            return [*steps, ("stop", candidate, why_stop)]
        if not _runs_what_is_named(worker_started, pointer):
            return [*steps, ("restart_worker",)]
        if worker_status and worker_status.get("candidate") == candidate:
            numbers = {k: int(worker_status.get(k) or 0) for k in NUMBERS}
            if numbers != {k: int((row.get("worker") or {}).get(k) or 0) for k in NUMBERS}:
                steps.append(("sync_status", candidate, numbers))
        return steps

    waiting = sorted(
        (str(row.get("created_at", "")), release_id)
        for release_id, row in versions.items()
        if row.get("status") == "candidate" and release_id in on_disk
    )
    if waiting:
        steps.append(("start_parallel", waiting[0][1]))
    elif not _runs_what_is_named(worker_started, pointer):
        steps.append(("restart_worker",))
    return steps
