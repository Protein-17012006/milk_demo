"""Which capture of a camera-hour becomes the training frame (operations-loop design 5.4).

The hourly rule serves a correction's request first (ingest handler). Without one it looks for a count that jumps
between the frames of one sampling window: the worker reads a window of a few frames in half a minute, the shelf does
not change in that time, so a frame whose count strays from its window's is a frame the model read badly. Without
that signal either, the frame is drawn at random as before.

Nothing here touches AWS.
"""

from __future__ import annotations

import math
import random
import statistics
from collections import Counter
from collections.abc import Callable
from datetime import datetime

WINDOW_GAP_S = 60  # two captures further apart than this belong to two sampling windows
JUMP_MIN = 2  # units a count must stray from its window's median to be a signal


def _when(item: dict) -> datetime:
    return datetime.fromisoformat(item["capture_timestamp"])


def windows(items: list[dict]) -> list[list[dict]]:
    """The captures in time order, cut wherever two neighbours are more than WINDOW_GAP_S apart."""
    out: list[list[dict]] = []
    for item in sorted(items, key=lambda it: (_when(it), it["capture_id"])):
        if out and (_when(item) - _when(out[-1][-1])).total_seconds() <= WINDOW_GAP_S:
            out[-1].append(item)
        else:
            out.append([item])
    return out


def count_jumps(items: list[dict], boxes_of: Callable[[dict], list[dict]]) -> dict[str, int]:
    """capture_id -> how far the capture's count strays from its window: the largest gap, over the products any
    frame of the window names, between this capture's units and the window's median (a product a frame does not
    show counts as zero there). Boxes without a name are left out."""
    jumps: dict[str, int] = {}
    for window in windows(items):
        counts = [Counter(b["sku_id"] for b in boxes_of(it) if b.get("sku_id")) for it in window]
        skus = set().union(*counts)
        medians = {sku: statistics.median(c[sku] for c in counts) for sku in skus}
        for item, own in zip(window, counts, strict=True):
            jumps[item["capture_id"]] = max((math.ceil(abs(own[sku] - medians[sku])) for sku in skus), default=0)
    return jumps


def pick_training(seeing: list[dict], jumps: dict[str, int], rng: random.Random) -> tuple[dict, str]:
    """The training frame among `seeing` and why: the capture with the largest jump when that reaches JUMP_MIN
    (the earliest of equals, no draw), else one draw of rng.choice, exactly as the rule drew before signals."""
    top = max((jumps.get(it["capture_id"], 0) for it in seeing), default=0)
    if top >= JUMP_MIN:
        strayed = [it for it in seeing if jumps.get(it["capture_id"], 0) == top]
        return min(strayed, key=lambda it: it["capture_id"]), "count_jump"
    return rng.choice(seeing), "random"
