"""A person's decision reused for the same can (auto-label design 5.4b), and the review queue built from it.

A can waiting for review takes the decision a person already made for a can at the same place (median boxes overlap,
IoU >= 0.5) with the same colour (the gallery's colour features, dot product >= the reuse threshold). Position alone
is not enough: on 23/11 a Sour Cream can at (943, 247) had become a Cheese can 43 minutes later. When the matching
decisions disagree, nothing is reused and a person looks again.

Reuse stays within a day: the shop rearranges between days, and decisions from other days at the same place
disagreed 20 times on the held-out segments (26/11). A decision "not a product" is reused as a grey mask, never as
background, so a can that stands there now is not taught as background.

The queue takes the segments in time order. A can no decision covers either waits on a can already waiting at the
same place with the same colour in an earlier segment of the same day, or needs a new review frame for its segment.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

import numpy as np

from training.store_view.auto_label import Decision, Track, _overlap
from training.store_view.slide_gallery import colour, crop_of

# Measured 26/11 with reuse-pairs on the train-side truth of CAM-S01-A: 134 same-place same-label pairs (5th percentile
# 0.6905, median 0.8743) and 76 same-place pairs with different labels, the most alike 0.7498; suggest_min_sim 0.7548.
REUSE_MIN_SIM = 0.755
NOT_PRODUCT, OUT_OF_SCOPE = "not_product", "out_of_scope"


@dataclass(frozen=True)
class Precedent:
    key: str  # the capture a person decided on; capture ids sort by time
    box: tuple[float, float, float, float]
    colour: np.ndarray
    label: str  # a flavour, NOT_PRODUCT or OUT_OF_SCOPE
    source: str  # "review:<track id>", "truth:<key>#<i>", "trn:<capture>@x,y" or "sim:<track id>"


def same_place(a, b) -> bool:
    return _overlap(a, b)[0] >= 0.5


def _same_colour(a: np.ndarray | None, b: np.ndarray | None, min_sim: float) -> bool:
    return a is not None and b is not None and float(np.dot(a, b)) >= min_sim


def matching(track: Track, precedents: Sequence[Precedent], min_sim: float) -> list[Precedent]:
    return [p for p in precedents if same_place(track.box, p.box) and _same_colour(track.colour, p.colour, min_sim)]


def decision_for(label: str, reason: str) -> Decision:
    if label == NOT_PRODUCT:
        return Decision("drop", None, reason)
    if label == OUT_OF_SCOPE:
        return Decision("masked", None, reason)
    return Decision("accept", label, reason)


def label_of(d: Decision) -> str | None:
    return {"accept": d.sku, "drop": NOT_PRODUCT, "masked": OUT_OF_SCOPE}.get(d.status)


def day_of(capture_id: str) -> str:
    """The YYYYMMDD of a capture id (CAP-S01-20261125-064004-3); "" when it has none."""
    m = re.search(r"\d{8}", capture_id)
    return m.group(0) if m else ""


def _reused(track: Track, precedents: Sequence[Precedent], min_sim: float) -> Precedent | str | None:
    """The latest matching decision, "conflict" when the matching decisions disagree, None when none matches."""
    found = matching(track, precedents, min_sim)
    if not found:
        return None
    if len({p.label for p in found}) > 1:
        return "conflict"
    return max(found, key=lambda p: p.key)


def _apply(p: Precedent) -> Decision:
    return decision_for(OUT_OF_SCOPE if p.label == NOT_PRODUCT else p.label, f"reused:{p.source}")


def reuse(track: Track, precedents: Sequence[Precedent], min_sim: float) -> Decision | None:
    found = _reused(track, precedents, min_sim)
    if found is None:
        return None
    if found == "conflict":
        return Decision("review", None, "reuse_conflict")
    return _apply(found)


def _truth_label(row: dict) -> str:
    if row.get("kind") == "ignore" or row.get("sku") in (None, "unknown"):
        return OUT_OF_SCOPE
    return row["sku"]


def truth_precedents(
    truth: dict[str, list[dict]], keys: Iterable[str], load: Callable[[str], np.ndarray | None]
) -> list[Precedent]:
    """Each hand-drawn row of the given keyframes, with the colour of its crop in the keyframe. The caller picks the
    keys: never a held-out keyframe outside gate 1's simulation."""
    out = []
    for key in keys:
        image = load(key)
        if image is None:
            continue
        for i, row in enumerate(truth.get(key, [])):
            crop = crop_of(image, row["box"])
            if crop is not None:
                out.append(
                    Precedent(
                        key, tuple(float(v) for v in row["box"]), colour(crop), _truth_label(row), f"truth:{key}#{i}"
                    )
                )
    return out


def trn_precedents(rows: list[tuple[str, list[int], str]], load: Callable[[str], np.ndarray | None]) -> list[Precedent]:
    """The judged boxes of done training frames (slide_gallery.trn_rows); "none" is not a product. The caller leaves
    out scoring and held-out frames."""
    out, cache = [], {}
    for cid, box, label in rows:
        if cid not in cache:
            cache = {cid: load(cid)}
        if cache[cid] is None:
            continue
        crop = crop_of(cache[cid], box)
        if crop is not None:
            out.append(
                Precedent(
                    cid,
                    tuple(float(v) for v in box),
                    colour(crop),
                    NOT_PRODUCT if label == "none" else label,
                    f"trn:{cid}@{box[0]},{box[1]}",
                )
            )
    return out


def review_precedents(proposals: list[dict], review: dict) -> list[Precedent]:
    """The cans people decided on review frames (the review file of auto_label_labels); a can without a colour cannot
    be matched, so it gives none."""
    labels = {"not_product": NOT_PRODUCT, "out_of_scope": OUT_OF_SCOPE}
    out = []
    for p in proposals:
        verdicts = (review.get(p["segment"]) or {}).get("tracks", {})
        for t in p["tracks"]:
            v = verdicts.get(t.id)
            if not v or t.colour is None or not p["frames"]:
                continue
            label = v.get("sku") if v.get("verdict") == "sku" else labels.get(v.get("verdict"))
            if label:
                out.append(Precedent(p["frames"][0], t.box, t.colour, label, f"review:{t.id}"))
    return out


def pair_stats(precedents: Sequence[Precedent]) -> list[tuple[float, bool]]:
    """Every two decisions on different captures at the same place: (how alike their colours are, same label?)."""
    out = []
    for i, a in enumerate(precedents):
        for b in precedents[i + 1 :]:
            if a.key != b.key and same_place(a.box, b.box):
                out.append((float(np.dot(a.colour, b.colour)), a.label == b.label))
    return out


def suggest_min_sim(pairs: list[tuple[float, bool]]) -> float:
    """The reuse threshold: the 5th percentile of the same-label pairs, raised just above the most alike pair with
    different labels; with no same-label pair, 1.0 (reuse nothing)."""
    same = [sim for sim, equal in pairs if equal]
    if not same:
        return 1.0
    threshold = float(np.percentile(same, 5))
    different = [sim for sim, equal in pairs if not equal]
    if different and threshold <= max(different):
        threshold = max(different) + 0.005
    return threshold


@dataclass
class QueueResult:
    decisions: dict[str, dict[str, Decision]] = field(default_factory=dict)
    new_frames: dict[str, list[str]] = field(default_factory=dict)
    links: list[tuple[str, str, str, str]] = field(default_factory=list)  # (segment, track, source, label)


def queue(
    proposals: list[dict],
    precedents: Sequence[Precedent],
    min_sim: float = REUSE_MIN_SIM,
    human: Callable[[dict, Track], str | None] | None = None,
) -> QueueResult:
    """Each can sent to review: reused when a decision covers it, waiting when a can at the same place with the same
    colour already waits in an earlier segment, else on its segment's new review frame. human, when given, decides the
    cans on a new frame at once (gate 1 simulates people with the truth); its decisions are then reused like any other.
    Neither the proposals nor their decisions are changed."""
    decided = list(precedents)
    pending: list[tuple[str, Track]] = []
    out = QueueResult()
    for p in sorted(proposals, key=lambda p: p["frames"][0] if p["frames"] else ""):
        seg = p["segment"]
        day = day_of(p["frames"][0]) if p["frames"] else ""
        decisions = dict(p["decisions"])
        for t in p["tracks"]:
            d = decisions.get(t.id)
            if d is None or d.status != "review":
                continue
            found = _reused(t, [x for x in decided if day_of(x.key) == day], min_sim)
            if isinstance(found, Precedent):
                decisions[t.id] = _apply(found)
                out.links.append((seg, t.id, found.source, found.label))
                continue
            if found is None:
                waits_on = next(
                    (
                        w
                        for wday, w in pending
                        if wday == day and same_place(t.box, w.box) and _same_colour(t.colour, w.colour, min_sim)
                    ),
                    None,
                )
                if waits_on is not None:
                    decisions[t.id] = Decision("review", None, f"waits:{waits_on.id}")
                    continue
            else:
                decisions[t.id] = Decision("review", None, "reuse_conflict")
            out.new_frames.setdefault(seg, []).append(t.id)
            label = human(p, t) if human else None
            if label is None:
                pending.append((day, t))
            elif t.colour is not None:
                decided.append(Precedent(p["frames"][0], t.box, t.colour, label, f"sim:{t.id}"))
                decisions[t.id] = decision_for(label, "human")
            else:
                decisions[t.id] = decision_for(label, "human")
        out.decisions[seg] = decisions
    return out
