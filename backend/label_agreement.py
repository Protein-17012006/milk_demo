"""How far a labeller's answers on a check sheet agree with the answer key (operations-loop design 5.4).

The units compared are every box of the frame, every missed mark of the key, and every mark of the labeller that
matches none of the key's. A box agrees when both gave it the same verdict and, for "wrong SKU", the same right
product. A mark agrees when it names the key's product and lies within MATCH_PX of the key's mark; each mark of the
key is matched once.

Agreement over several frames is the sum of agreeing units over the sum of units, not a mean of per-frame shares:
a frame with twenty cans weighs more than one with two.

Only team admins are shown these numbers (the API route checks). Nothing here touches AWS.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

MATCH_PX = 40  # a lid on CAM-S01-A is 60 to 80 px wide on the 2560 x 1440 frame
ICT = timezone(timedelta(hours=7))


def compare(key_verdicts: list[dict], key_missed: list[dict], verdicts: list[dict], missed: list[dict]) -> dict:
    """One check sheet against its key: units, agree, and what they are made of (boxes, boxes_agree, marks_key,
    marks_matched, marks_extra); units = boxes + marks_key + marks_extra, agree = boxes_agree + marks_matched."""
    mine = {v.get("box_id"): v for v in verdicts}
    boxes_agree = 0
    for key in key_verdicts:
        own = mine.get(key.get("box_id"))
        if own is None or own.get("verdict") != key.get("verdict"):
            continue
        if key.get("verdict") == "wrong_sku" and own.get("true_sku_id") != key.get("true_sku_id"):
            continue
        boxes_agree += 1

    free = list(range(len(key_missed)))
    matched = 0
    for mark in missed:
        near = [
            (math.dist((mark["x"], mark["y"]), (key_missed[i]["x"], key_missed[i]["y"])), i)
            for i in free
            if key_missed[i].get("sku_id") == mark.get("sku_id")
        ]
        near = [(d, i) for d, i in near if d <= MATCH_PX]
        if near:
            free.remove(min(near)[1])
            matched += 1
    extra = len(missed) - matched
    return {
        "units": len(key_verdicts) + len(key_missed) + extra,
        "agree": boxes_agree + matched,
        "boxes": len(key_verdicts),
        "boxes_agree": boxes_agree,
        "marks_key": len(key_missed),
        "marks_matched": matched,
        "marks_extra": extra,
    }


def week_of(iso: str) -> str:
    """The ISO week of that moment on the store's clock (UTC+7), as 2026-W48."""
    year, week, _ = datetime.fromisoformat(iso).astimezone(ICT).isocalendar()
    return f"{year}-W{week:02d}"


def weekly(pairs: list[tuple[dict, dict]]) -> list[dict]:
    """Agreement per labeller and week from (answer key, answered check sheet) pairs. The key carries key_verdicts
    and key_missed, the sheet labeled_by, labeled_at, verdicts and missed. Rows are labeller, week, frames, units,
    agree and agreement (None without a unit), newest week first, then by labeller."""
    totals: dict[tuple[str, str], dict[str, int]] = {}
    for key, sheet in pairs:
        result = compare(key["key_verdicts"], key["key_missed"], sheet["verdicts"], sheet["missed"])
        row = totals.setdefault(
            (week_of(sheet["labeled_at"]), sheet["labeled_by"]), {"frames": 0, "units": 0, "agree": 0}
        )
        row["frames"] += 1
        row["units"] += result["units"]
        row["agree"] += result["agree"]
    weeks = sorted({week for week, _ in totals}, reverse=True)
    return [
        {
            "labeller": labeller,
            "week": week,
            **row,
            "agreement": row["agree"] / row["units"] if row["units"] else None,
        }
        for week in weeks
        for (w, labeller), row in sorted(totals.items())
        if w == week
    ]
