"""The live release against a candidate, on the same frames (operations-loop design 5.2).

While a candidate runs in parallel, a frame for people to label shows the boxes of both releases as one set, and
nothing on it says which release drew which box:
  - both drew a box at the same place with the same name: one box with that name, labelled as any box is;
  - they drew it with different names, or only one of them drew it: one box with no name (needs_flavour), so the
    person says what is there without a suggestion to follow.
From one labelled frame, split_audit gives back two frames in the shape audit_scoring reads, one per release, so
the live release's numbers are computed as before and the candidate's can be set beside them.

The three keys that say who drew a box (src, live_sku, cand_sku) stay in the backend: public_boxes drops them.
Nothing here touches AWS.
"""

from __future__ import annotations

import json
from typing import Any

from model_health import capture_boxes

SAME_PLACE = 0.5  # two boxes are one object when they share this much of the smaller one (as MILK_LONG_TH_OVERLAP)
PRIVATE_KEYS = ("src", "live_sku", "cand_sku")
CMP_PER_DAY = 8  # comparison frames per camera per day, at most


def _shared(a, b) -> float:
    """Share of the smaller of two x, y, w, h boxes that the other covers."""
    ix = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    smaller = min(a[2] * a[3], b[2] * b[3])
    return ix * iy / smaller if smaller > 0 else 0.0


def _by_confidence(boxes: list[dict]) -> list[dict]:
    return sorted(boxes, key=lambda b: (-float(b.get("conf", 0.0)), list(b["box"]), str(b.get("sku_id"))))


def merge_boxes(live: list[dict], cand: list[dict]) -> list[dict]:
    """The boxes of both releases as one set, one to one: each live box, surest first, takes the candidate box not
    yet taken that shares most with it (at least SAME_PLACE of the smaller box). The same input in any order gives
    the same output. Boxes are numbered from 1, top to bottom, then left to right."""
    free = _by_confidence(cand)
    out: list[dict] = []
    for box in _by_confidence(live):
        best, best_share = None, SAME_PLACE
        for other in free:
            share = _shared(box["box"], other["box"])
            if share > best_share or (share == best_share and best is None):
                best, best_share = other, share
        if best is None:
            out.append(_merged(box, None))
            continue
        free.remove(best)
        out.append(_merged(box, best))
    out.extend(_merged(None, other) for other in free)
    out.sort(key=lambda b: (b["box"][1], b["box"][0], b["src"]))
    for i, b in enumerate(out, start=1):
        b["box_id"] = i
    return out


def _merged(live: dict | None, cand: dict | None) -> dict:
    shown = live or cand
    same = live is not None and cand is not None and live.get("sku_id") == cand.get("sku_id")
    return {
        "box_id": 0,
        "sku_id": shown.get("sku_id") if same else None,
        "conf": float(shown.get("conf", 0.0)),
        "box": [int(v) for v in shown["box"]],
        "needs_flavour": not same,
        "src": "both" if live is not None and cand is not None else ("live" if live is not None else "cand"),
        "live_sku": live.get("sku_id") if live is not None else None,
        "cand_sku": cand.get("sku_id") if cand is not None else None,
    }


def differs(boxes: list[dict]) -> bool:
    """Whether the two releases read the frame differently anywhere."""
    return any(b.get("needs_flavour") and b.get("src") for b in boxes)


def public_boxes(boxes: list[dict]) -> list[dict]:
    """The boxes as the browser may have them: without who drew them."""
    return [{k: v for k, v in b.items() if k not in PRIVATE_KEYS} for b in boxes]


def frame_boxes(item: dict, candidate: str | None) -> list[dict]:
    """The boxes of a frame for people to label, from its capture row: both releases' boxes merged when the capture
    carries a result of `candidate` (the release now running in parallel); otherwise the live boxes as always. A
    result of some other candidate, or a capture the candidate never read, gives the live boxes."""
    live = capture_boxes(item)
    raw = item.get("candidate_detections_json")
    if not candidate or item.get("candidate_version") != candidate or raw is None:
        return live
    found = json.loads(raw) if isinstance(raw, str) else list(raw)
    cand = [
        {"sku_id": d.get("sku_id"), "conf": float(d.get("conf", 0.0)), "box": [int(v) for v in d["box"]]} for d in found
    ]
    return merge_boxes(live, cand)


def _side(audit: dict, own: str, version: Any) -> dict:
    """One release's frame out of a merged one: its boxes under its own names, the person's answers as they apply to
    it, and as misses the real units it drew no box for. `own` is "live_sku" or "cand_sku"."""
    mine = "live" if own == "live_sku" else "cand"
    answers = {v["box_id"]: v for v in audit.get("verdicts", [])}
    boxes, verdicts, missed = [], [], list(audit.get("missed", []))
    for b in audit.get("ai_boxes", []):
        drew = b.get("src") in ("both", mine)
        answer = answers.get(b["box_id"])
        if drew:
            name = b.get(own) if b.get("needs_flavour") else b.get("sku_id")
            boxes.append({"box_id": b["box_id"], "sku_id": name, "conf": b.get("conf", 0.0), "box": b["box"]})
            if answer:
                verdicts.append(_own_answer(b, answer, name))
        elif answer and answer.get("verdict") == "wrong_sku" and answer.get("true_sku_id"):
            x, y, w, h = b["box"]
            missed.append({"sku_id": answer["true_sku_id"], "x": x + w // 2, "y": y + h // 2})
    return {**audit, "model_version": version, "ai_boxes": boxes, "verdicts": verdicts, "missed": missed}


def _own_answer(box: dict, answer: dict, name: str | None) -> dict:
    """On a box with no name shown, the person named the SKU that is there (wrong_sku + true_sku_id): the release
    that had called it that was right."""
    if box.get("needs_flavour") and answer.get("verdict") == "wrong_sku" and answer.get("true_sku_id") == name:
        return {"box_id": box["box_id"], "verdict": "correct"}
    return dict(answer)


def split_audit(audit: dict) -> tuple[dict, dict | None]:
    """(the live release's frame, the candidate's frame) from a frame that shows both; a frame without a candidate
    is the live release's frame as it stands, and there is no second one."""
    if not audit.get("candidate_version"):
        return audit, None
    return (
        _side(audit, "live_sku", audit.get("model_version")),
        _side(audit, "cand_sku", audit["candidate_version"]),
    )
