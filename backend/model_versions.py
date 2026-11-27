"""Model versions on the website (operations-loop design 5.2): the names the job runner on the counting machine and
the website share, and which requests the Model page may make.

The model-versions table has, per camera, one row per release (version_id = the release's id, with kind, parent,
status, criteria, when its parallel run started, who decided) and one state row (version_id "#state": the live
release, the one before it, the candidate, the request the website made and what the runner answered).

A release goes live through one door only: it runs in parallel with the live one, people's answers on sampled frames
give a verdict, and a team admin asks for it. The runner does the switch; this module only says what may be asked.
"""

from __future__ import annotations

STATE_ID = "#state"
STATUSES = ("candidate", "parallel", "live", "replaced", "discarded", "stopped")
ACTIONS = ("put_live", "discard", "rollback")
# Verdicts of a parallel run that let a team admin put the candidate live
MAY_GO_LIVE = ("better", "no_difference")


def request_running(state: dict) -> bool:
    """A request the website wrote that the runner has not answered yet."""
    request = state.get("request")
    return bool(request) and (state.get("last_result") or {}).get("request_id") != request.get("id")


def can(action: str, state: dict, version: dict | None, verdict_state: str | None) -> str | None:
    """Why `action` may not be asked now, in words for the Model page, or None when it may."""
    if action not in ACTIONS:
        return f"Unknown action: {action}."
    if request_running(state):
        return "Another request is still running."
    if action == "rollback":
        return None if state.get("previous") else "There is no earlier version to roll back to."
    status = (version or {}).get("status")
    if action == "discard":
        return None if status in ("candidate", "parallel") else "Only a waiting or running candidate can be discarded."
    if (version or {}).get("version_id") != state.get("candidate"):
        return "Only the candidate that is running now can be put live."
    if status != "parallel":
        return "Only a version that is running in parallel with the live one can be put live."
    if verdict_state not in MAY_GO_LIVE:
        return "The parallel run has not reached a result that allows this yet."
    return None
