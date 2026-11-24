"""Is the glass display cabinet in view? The store packs it away at night, and counting an empty frame as
"out of stock" would be wrong. The cabinet zone of each capture is compared, by an H x S colour histogram, with
references the worker learns by itself: a capture with enough confident cans inside the zone becomes a reference."""

from __future__ import annotations

import logging
import os

import numpy as np

from .cvoutput import Detection

REF_MIN_BOXES = 3  # confident cans inside the zone before a capture may become a reference
REF_MIN_CONF = 0.8
REF_EVERY_S = 600  # at most one new reference per 10 minutes
MAX_REFS = 50  # the newest references are kept

H_BINS, S_BINS = 30, 16

log = logging.getLogger("milk.display")


def zone_crop(image: np.ndarray, zone: tuple[float, float, float, float]) -> np.ndarray:
    """The cabinet zone (x, y, w, h as fractions of the frame); the part outside the frame is dropped."""
    height, width = image.shape[:2]
    x, y, w, h = zone
    x0, y0 = int(x * width), int(y * height)
    x1, y1 = min(width, int((x + w) * width)), min(height, int((y + h) * height))
    return image[y0:y1, x0:x1]


def hs_histogram(image: np.ndarray) -> np.ndarray:
    """Normalised hue x saturation histogram (30 x 16 bins) as a flat float32 array."""
    import cv2

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [H_BINS, S_BINS], [0, 180, 0, 256])
    cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
    return hist.flatten().astype(np.float32)


class DisplayCheck:
    """Scores each capture's cabinet zone against the learnt references (best correlation, 1 = the same look)."""

    def __init__(self, zone: tuple[float, float, float, float], min_score: float = 0.5, refs_path: str | None = None):
        self._zone = zone
        self._min_score = min_score
        self._path = refs_path
        self._hists: list[np.ndarray] = []
        self._times: list[float] = []
        if refs_path and os.path.exists(refs_path):
            self._load(refs_path)

    def _load(self, path: str) -> None:
        """Reads saved references; a corrupt or incomplete file starts the worker with none (and is overwritten
        by the next reference it learns) instead of stopping it."""
        try:
            with np.load(path) as saved:
                hists = list(saved["hists"])
                times = [float(t) for t in saved["times"]]
            if len(hists) != len(times):
                raise ValueError(f"{len(hists)} histograms but {len(times)} times")
        except Exception as exc:  # noqa: BLE001 - OSError, ValueError, KeyError, BadZipFile and more
            log.warning("ignoring display references in %s: %s: %s", path, type(exc).__name__, exc)
            return
        self._hists, self._times = hists, times

    @property
    def n_refs(self) -> int:
        return len(self._hists)

    def check(self, image: np.ndarray, detections: list[Detection], now: float) -> tuple[float | None, bool]:
        """(score, seen): the score is None until a reference exists, and then the display counts as seen."""
        import cv2

        hist = hs_histogram(zone_crop(image, self._zone))
        score: float | None = None
        seen = True
        if self._hists:
            best = max(float(cv2.compareHist(hist, ref, cv2.HISTCMP_CORREL)) for ref in self._hists)
            seen = best >= self._min_score
            score = round(best, 3)
        if self._worth_learning(image, detections, now):
            self._learn(hist, now)
        return score, seen

    def _worth_learning(self, image: np.ndarray, detections: list[Detection], now: float) -> bool:
        if self._times and now - self._times[-1] < REF_EVERY_S:
            return False
        height, width = image.shape[:2]
        x, y, w, h = self._zone
        left, top, right, bottom = x * width, y * height, (x + w) * width, (y + h) * height
        inside = 0
        for d in detections:
            bx, by, bw, bh = d.box
            cx, cy = bx + bw / 2, by + bh / 2
            if d.confidence >= REF_MIN_CONF and left <= cx < right and top <= cy < bottom:
                inside += 1
        return inside >= REF_MIN_BOXES

    def _learn(self, hist: np.ndarray, now: float) -> None:
        self._hists = (self._hists + [hist])[-MAX_REFS:]
        self._times = (self._times + [now])[-MAX_REFS:]
        if self._path:
            tmp = self._path + ".tmp"
            with open(tmp, "wb") as handle:
                np.savez(handle, hists=np.array(self._hists), times=np.array(self._times))
            os.replace(tmp, self._path)
