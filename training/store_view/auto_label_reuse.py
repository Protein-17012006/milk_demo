"""A person's decision reused for the same can (auto-label design 5.4b), and the review queue built from it.

A can waiting for review takes the decision a person already made for a can at the same place (median boxes overlap,
IoU >= 0.5) with the same colour (the gallery's colour features, dot product >= the reuse threshold). Position alone
is not enough: on 23/11 a Sour Cream can at (943, 247) had become a Cheese can 43 minutes later. When the matching
decisions disagree, nothing is reused and a person looks again.

The queue takes the segments in time order. A can no decision covers either waits on a can already waiting at the
same place with the same colour in an earlier segment, or needs a new review frame for its segment.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np

from training.store_view.auto_label import Decision, Track, _overlap

REUSE_MIN_SIM = 0.95  # placeholder until measured on the train-side truth (plan 2026-11-26 Task 6)
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


def reuse(track: Track, precedents: Sequence[Precedent], min_sim: float) -> Decision | None:
    found = matching(track, precedents, min_sim)
    if not found:
        return None
    if len({p.label for p in found}) > 1:
        return Decision("review", None, "reuse_conflict")
    latest = max(found, key=lambda p: p.key)
    return decision_for(latest.label, f"reused:{latest.source}")


@dataclass
class QueueResult:
    decisions: dict[str, dict[str, Decision]] = field(default_factory=dict)
    new_frames: dict[str, list[str]] = field(default_factory=dict)
    links: list[tuple[str, str, str]] = field(default_factory=list)


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
    pending: list[Track] = []
    out = QueueResult()
    for p in sorted(proposals, key=lambda p: p["frames"][0] if p["frames"] else ""):
        seg = p["segment"]
        decisions = dict(p["decisions"])
        for t in p["tracks"]:
            d = decisions.get(t.id)
            if d is None or d.status != "review":
                continue
            again = reuse(t, decided, min_sim)
            if again is not None and again.status != "review":
                decisions[t.id] = again
                out.links.append((seg, t.id, again.reason.removeprefix("reused:")))
                continue
            if again is None:
                waits_on = next(
                    (w for w in pending if same_place(t.box, w.box) and _same_colour(t.colour, w.colour, min_sim)), None
                )
                if waits_on is not None:
                    decisions[t.id] = Decision("review", None, f"waits:{waits_on.id}")
                    continue
            else:
                decisions[t.id] = again
            out.new_frames.setdefault(seg, []).append(t.id)
            label = human(p, t) if human else None
            if label is None:
                pending.append(t)
            elif t.colour is not None:
                decided.append(Precedent(p["frames"][0], t.box, t.colour, label, f"sim:{t.id}"))
                decisions[t.id] = decision_for(label, "human")
            else:
                decisions[t.id] = decision_for(label, "human")
        out.decisions[seg] = decisions
    return out
