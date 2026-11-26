"""Gate 1 (auto-label design 5.7): how good the auto-labeller's own decisions are, on the held-out segments whose
keyframe has a hand-drawn truth. The gallery and the prompts must not have seen those segments.

At the keyframe a can's box is its own box there, else its median box; it matches the first truth row not yet taken
whose box holds its centre (cans the machine accepted are matched before the others).

    real          cans the machine accepted on its own (reason "agree") that match a truth row of any kind (ignore and
                  lower tier included); reused and human decisions are scored by reuse_right instead
    flavour       those machine-accepted cans matching a row with a known flavour that have that flavour
    coverage      truth rows (not ignore) matched by a can that is accepted, masked or sent to review
    review_share  segments that need a new review frame (after reusing decisions, design 5.4b), among segments not too
                  short to decide; without that list, segments with any can sent to review
    reuse_right   reused decisions whose label is the truth's at that can, over reused cans in segments with a truth;
                  counts.reuse_kinds splits the wrong ones (flavour_swap, flavour_where_unknown,
                  flavour_where_no_can, no_flavour_where_flavour, out_of_scope_vs_not_product)

simulate() plays the person with the truth: a can on a new review frame of a segment whose keyframe has a truth gets
the truth's label at once, and later segments may reuse it; segments without a truth leave their cans waiting.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from training.store_view.auto_label import Decision, Track
from training.store_view.auto_label_reuse import NOT_PRODUCT, OUT_OF_SCOPE, Precedent, queue

GATE1 = {
    "real": (">=", 0.99),
    "flavour": (">=", 0.98),
    "coverage": (">=", 0.95),
    "review_share": ("<=", 0.40),
    "reuse_right": (">=", 0.99),
}
COVERED = ("accept", "review", "masked")


def _ratio(a: int, b: int) -> float | None:
    return a / b if b else None


def score(
    segments: dict[str, tuple[list[Track], dict[str, Decision]]],
    truth: dict[str, list[dict]],
    keyframe_of: dict[str, str],
    new_frames: set[str] | None = None,
) -> dict:
    n = {
        "accepted": 0,
        "real": 0,
        "flavour_rows": 0,
        "flavour_right": 0,
        "rows": 0,
        "covered": 0,
        "segments": 0,
        "review_segments": 0,
    }
    for sid, (tracks, decisions) in segments.items():
        if any(d.status == "too_short" for d in decisions.values()):
            continue
        n["segments"] += 1
        if new_frames is None:
            n["review_segments"] += any(d.status == "review" for d in decisions.values())
        else:
            n["review_segments"] += sid in new_frames
        key = keyframe_of.get(sid)
        if key not in truth:
            continue
        rows = truth[key]
        taken = [False] * len(rows)
        order = sorted(
            (t for t in tracks if decisions.get(t.id) and decisions[t.id].status in COVERED),
            key=lambda t: decisions[t.id].reason != "agree",
        )
        for t in order:
            d = decisions[t.id]
            x, y, w, h = t.box_in(key) or t.box
            cx, cy = x + w / 2, y + h / 2
            hit = next(
                (
                    i
                    for i, r in enumerate(rows)
                    if not taken[i]
                    and r["box"][0] <= cx <= r["box"][0] + r["box"][2]
                    and r["box"][1] <= cy <= r["box"][1] + r["box"][3]
                ),
                None,
            )
            if hit is not None:
                taken[hit] = True
            if d.status != "accept" or d.reason != "agree":
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


def truth_label(rows: list[dict], box) -> str:
    """The truth's label at a box: the first row holding its centre gives its flavour, or out of scope when the row's
    flavour is unknown or the row is ignore; no row there means not a product."""
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2
    for r in rows:
        rx, ry, rw, rh = r["box"]
        if rx <= cx <= rx + rw and ry <= cy <= ry + rh:
            return OUT_OF_SCOPE if r.get("kind") == "ignore" or r.get("sku") in (None, "unknown") else r["sku"]
    return NOT_PRODUCT


def reuse_kind(got: str, want: str) -> str:
    """How a reused label stands against the truth's at that can."""
    none = (NOT_PRODUCT, OUT_OF_SCOPE)
    if got == want:
        return "right"
    if got in none and want in none:
        return "out_of_scope_vs_not_product"
    if got in none:
        return "no_flavour_where_flavour"
    if want == OUT_OF_SCOPE:
        return "flavour_where_unknown"
    if want == NOT_PRODUCT:
        return "flavour_where_no_can"
    return "flavour_swap"


def simulate(
    proposals: list[dict], truth: dict[str, list[dict]], precedents: Sequence[Precedent], min_sim: float
) -> dict:
    """Gate 1 with decisions reused (see the module text)."""

    def box_at(p: dict, t: Track):
        key = p.get("keyframe")
        return t.box_in(key) or t.box

    def human(p: dict, t: Track) -> str | None:
        key = p.get("keyframe")
        return truth_label(truth[key], box_at(p, t)) if key in truth else None

    r = queue(proposals, precedents, min_sim, human)
    summary = score(
        {p["segment"]: (p["tracks"], r.decisions[p["segment"]]) for p in proposals},
        truth,
        {p["segment"]: p["keyframe"] for p in proposals},
        set(r.new_frames),
    )
    by_seg = {p["segment"]: p for p in proposals}
    kinds: Counter = Counter()
    for seg, tid, _, label in r.links:
        p = by_seg[seg]
        if p.get("keyframe") not in truth:
            continue
        t = next(t for t in p["tracks"] if t.id == tid)
        kinds[reuse_kind(label, truth_label(truth[p["keyframe"]], box_at(p, t)))] += 1
    checked, right = sum(kinds.values()), kinds["right"]
    summary["reuse_right"] = _ratio(right, checked)
    summary["counts"].update(
        new_frames=len(r.new_frames),
        reused=len(r.links),
        waiting=sum(d.reason.startswith("waits:") for ds in r.decisions.values() for d in ds.values()),
        conflict=sum(d.reason == "reuse_conflict" for ds in r.decisions.values() for d in ds.values()),
        reuse_checked=checked,
        reuse_right=right,
        reuse_kinds={k: v for k, v in sorted(kinds.items()) if k != "right"},
    )
    return summary


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
