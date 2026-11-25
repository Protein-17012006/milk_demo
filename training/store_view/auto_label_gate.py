"""Gate 1 (auto-label design 5.7): how good the auto-labeller's own decisions are, on the held-out segments whose
keyframe has a hand-drawn truth. The gallery and the prompts must not have seen those segments.

At the keyframe a can's box is its own box there, else its median box; it matches the first truth row not yet taken
whose box holds its centre (accepted cans are matched before cans sent to review).

    real          accepted cans that match a truth row of any kind (ignore and lower tier included)
    flavour       accepted cans matching a row with a known flavour that have that flavour
    coverage      truth rows (not ignore) matched by an accepted can or one sent to review
    review_share  segments with a can sent to review, among segments not too short to decide
"""

from __future__ import annotations

from training.store_view.auto_label import Decision, Track

GATE1 = {"real": (">=", 0.99), "flavour": (">=", 0.98), "coverage": (">=", 0.95), "review_share": ("<=", 0.40)}


def _ratio(a: int, b: int) -> float | None:
    return a / b if b else None


def score(
    segments: dict[str, tuple[list[Track], dict[str, Decision]]],
    truth: dict[str, list[dict]],
    keyframe_of: dict[str, str],
) -> dict:
    n = {"accepted": 0, "real": 0, "flavour_rows": 0, "flavour_right": 0, "rows": 0, "covered": 0, "segments": 0,
         "review_segments": 0}
    for sid, (tracks, decisions) in segments.items():
        if any(d.status == "too_short" for d in decisions.values()):
            continue
        n["segments"] += 1
        n["review_segments"] += any(d.status == "review" for d in decisions.values())
        key = keyframe_of.get(sid)
        if key not in truth:
            continue
        rows = truth[key]
        taken = [False] * len(rows)
        order = sorted(
            (t for t in tracks if decisions.get(t.id) and decisions[t.id].status in ("accept", "review")),
            key=lambda t: decisions[t.id].status != "accept",
        )
        for t in order:
            d = decisions[t.id]
            x, y, w, h = t.box_in(key) or t.box
            cx, cy = x + w / 2, y + h / 2
            hit = next(
                (i for i, r in enumerate(rows) if not taken[i] and r["box"][0] <= cx <= r["box"][0] + r["box"][2]
                 and r["box"][1] <= cy <= r["box"][1] + r["box"][3]),
                None,
            )
            if hit is not None:
                taken[hit] = True
            if d.status != "accept":
                continue
            n["accepted"] += 1
            if hit is None:
                continue
            n["real"] += 1
            row = rows[hit]
            if row.get("kind") != "ignore" and row.get("sku") not in (None, "unknown"):
                n["flavour_rows"] += 1
                n["flavour_right"] += d.sku == row["sku"]
        for i, r in enumerate(rows):
            if r.get("kind") != "ignore":
                n["rows"] += 1
                n["covered"] += taken[i]
    return {
        "real": _ratio(n["real"], n["accepted"]),
        "flavour": _ratio(n["flavour_right"], n["flavour_rows"]),
        "coverage": _ratio(n["covered"], n["rows"]),
        "review_share": _ratio(n["review_segments"], n["segments"]),
        "counts": n,
    }


def failures(summary: dict) -> list[str]:
    out = []
    for key, (op, limit) in GATE1.items():
        value = summary.get(key)
        if value is None:
            out.append(f"{key} not measured")
        elif op == ">=" and value < limit:
            out.append(f"{key} {value:.3f} < {limit}")
        elif op == "<=" and value > limit:
            out.append(f"{key} {value:.3f} > {limit}")
    return out
