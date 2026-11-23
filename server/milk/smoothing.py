"""Steadier counts for the dashboard: the lower median of the last few frames per SKU.

A hand reaching for a carton hides others for a frame or two; the median keeps the
number on screen from jumping. Raw per-frame counts are still stored unchanged.
"""

from __future__ import annotations

from collections import deque
from statistics import median_low


class CountSmoother:
    def __init__(self, window: int = 3) -> None:
        if window < 1:
            raise ValueError("window must be at least 1")
        self._history: deque[dict[str, int]] = deque(maxlen=window)

    def update(self, counts: dict[str, int]) -> dict[str, int]:
        self._history.append(dict(counts))
        keys = set().union(*self._history)
        smoothed = {k: median_low([h.get(k, 0) for h in self._history]) for k in keys}
        return {k: v for k, v in sorted(smoothed.items()) if v > 0}

    def reset(self) -> None:
        self._history.clear()
