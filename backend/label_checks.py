"""Frames with a known answer, served to each labeller without telling them (operations-loop design 5.4).

An answer key is a labelled frame that a team admin vouches for: the audit carries answer_key, who marked it and
when, and a copy of its answers at that moment (key_verdicts_json, key_missed_json), so relabelling the frame later
does not move the key.

A check sheet is a row of its own in the audits table (CHK-<token>): the key's picture and boxes, blank answers,
assigned to one labeller. It looks like any pending frame in that labeller's queue. Its answers stay on the sheet and
never touch the key. Nothing that scores the model reads a CHK- row (only AUD- rows count), and nothing that builds
training data does (TRN-, REV- and CMP- rows only).

One frame in CHECK_EVERY is a check: after CHECK_EVERY - 1 frames a labeller saved, the next one is a sheet.

Nothing here touches AWS.
"""

from __future__ import annotations

CHECK_EVERY = 10
SHEET_PREFIX = "CHK-"
# what a sheet takes from its key: the frame and the model's boxes, never an answer
_COPIED = (
    "store_id",
    "purpose",
    "camera_id",
    "capture_id",
    "capture_timestamp",
    "image_key",
    "model_version",
    "pipeline",
    "display_visible",
    "display_score",
    "ai_boxes_json",
)


def is_sheet(audit: dict) -> bool:
    return str(audit.get("audit_id", "")).startswith(SHEET_PREFIX)


def can_be_key(audit: dict) -> str | None:
    """Why this frame cannot be an answer key, in words for the Model page, or None when it can. The words for a
    check sheet do not say what it is."""
    if is_sheet(audit):
        return "This frame cannot be an answer key."
    if audit.get("status") != "done":
        return "Only a labelled frame can be an answer key."
    if audit.get("candidate_version"):
        return "A frame that shows two versions cannot be an answer key."
    return None


def _sheets_of(audits: list[dict], email: str) -> list[dict]:
    return [a for a in audits if is_sheet(a) and a.get("assigned_to") == email]


def due(audits: list[dict], email: str) -> bool:
    """Whether the labeller's next frame is a check: they saved CHECK_EVERY - 1 frames since their newest sheet was
    made (ever, without one), and none of their sheets still waits. Sheets are not counted as frames."""
    sheets = _sheets_of(audits, email)
    if any(s.get("status") == "pending" for s in sheets):
        return False
    since = max((str(s.get("sampled_at", "")) for s in sheets), default="")
    saved = sum(
        1
        for a in audits
        if not is_sheet(a)
        and a.get("status") == "done"
        and a.get("labeled_by") == email
        and str(a.get("labeled_at", "")) > since
    )
    return saved >= CHECK_EVERY - 1


def eligible_keys(audits: list[dict], email: str) -> list[dict]:
    """The answer keys this labeller can be checked on: not one they labelled, not one they marked, not one they
    already got a sheet for."""
    seen = {s.get("check_of") for s in _sheets_of(audits, email)}
    return [
        a
        for a in audits
        if a.get("answer_key") is True
        and not is_sheet(a)
        and a.get("labeled_by") != email
        and a.get("answer_key_by") != email
        and a["audit_id"] not in seen
    ]


def newest_key(keys: list[dict]) -> dict:
    """The key whose frame was taken last. A check is made from it, not from one drawn at random: the picture
    carries the camera's date, and a frame of last week among today's would give the check away."""
    return max(keys, key=lambda k: (str(k.get("capture_timestamp", "")), k["audit_id"]))


def labellers(audits: list[dict]) -> list[str]:
    """Everyone who labelled a frame (check sheets aside), in name order."""
    return sorted(
        {a["labeled_by"] for a in audits if a.get("status") == "done" and a.get("labeled_by") and not is_sheet(a)}
    )


def without_key(audits: list[dict]) -> list[str]:
    """The labellers no answer key is left for: their checks have stopped until a team admin marks a new key."""
    return [who for who in labellers(audits) if not eligible_keys(audits, who)]


def sheet_for(key: dict, email: str, now_iso: str, token: str) -> dict:
    """The check sheet of `key` for one labeller: the key's frame and boxes, no answers yet. It carries the purpose
    the labeller would see on the key itself (an old frame without a stored one is judged by its id, as the API
    does), so its banner reads the same."""
    purpose = key.get("purpose") or ("scoring" if str(key["audit_id"]).startswith("AUD-") else "training")
    return {
        **{name: key[name] for name in _COPIED if name in key},
        "purpose": purpose,
        "audit_id": f"{SHEET_PREFIX}{token}",
        "check_of": key["audit_id"],
        "assigned_to": email,
        "status": "pending",
        "sampled_at": now_iso,
        "verdicts_json": "[]",
        "missed_json": "[]",
    }
