"""Is the glass display cabinet in view? The store packs it away at night, and counting an empty frame as
"out of stock" would be wrong. The cabinet zone of each capture is compared with references the worker learns by
itself: a capture with enough confident cans inside the zone becomes a reference.

The zone is compared quarter by quarter, on colour and on shape, and the score is the mean of the two, so neither
reaches MILK_DISPLAY_MIN (0.6) alone. Colour alone was not enough: on 23/11 the cabinet's place held fruit, sweets
and red snack packets for half an hour after it was packed away, and their colours matched the cabinet as well as
the cabinet itself did the next morning, put back a little to the side."""

from __future__ import annotations

import logging
import os
from itertools import pairwise

import numpy as np

from .cvoutput import Detection

REF_MIN_BOXES = 3  # confident cans inside the zone before a capture may become a reference
REF_MIN_CONF = 0.8
REF_EVERY_S = 600  # at most one new reference per 10 minutes
MAX_REFS = 50  # the newest references are kept

WORK_W = 192  # px: the zone is shrunk to this width first (fast, and the same detail at any camera resolution)
CELLS = 2  # compared quarter by quarter (2 x 2): the same colours or edges in other places do not match
H_BINS, S_BINS = 30, 16  # colour: hue x saturation histogram of each quarter
EDGE_BINS = 18  # shape: edge-direction histogram of each quarter, 10 degrees per bin
COLOUR_LEN = H_BINS * S_BINS
CELL_LEN = COLOUR_LEN + EDGE_BINS
DESC_LEN = CELLS * CELLS * CELL_LEN  # one reference, as kept in the refs file

log = logging.getLogger("milk.display")


def zone_crop(image: np.ndarray, zone: tuple[float, float, float, float]) -> np.ndarray:
    """The cabinet zone (x, y, w, h as fractions of the frame); the part outside the frame is dropped."""
    height, width = image.shape[:2]
    x, y, w, h = zone
    x0, y0 = int(x * width), int(y * height)
    x1, y1 = min(width, int((x + w) * width)), min(height, int((y + h) * height))
    return image[y0:y1, x0:x1]


def describe(zone: np.ndarray) -> np.ndarray:
    """What a zone crop (BGR) looks like, quarter by quarter, as a flat float32 array of DESC_LEN:
    - colour: the hue x saturation histogram after a gray-world white balance (so a warmer or cooler light changes
      little), as square roots of its shares: the dot product of two is their Bhattacharyya coefficient;
    - shape: the edge-direction histogram (gradient directions weighted by strength), mean removed and of unit
      length: the dot product of two is their correlation. A quarter without edges is all zeros."""
    import cv2

    height, width = zone.shape[:2]
    small = cv2.resize(zone, (WORK_W, max(CELLS, round(height * WORK_W / width))), interpolation=cv2.INTER_AREA)
    means = small.reshape(-1, 3).mean(axis=0)
    gains = np.clip(means.mean() / np.maximum(means, 1.0), 0.5, 2.0)
    hsv = cv2.cvtColor(np.clip(small * gains, 0, 255).astype(np.uint8), cv2.COLOR_BGR2HSV)
    grey = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gx, gy = cv2.Sobel(grey, cv2.CV_32F, 1, 0), cv2.Sobel(grey, cv2.CV_32F, 0, 1)
    strength, angle = cv2.cartToPolar(gx, gy, angleInDegrees=True)
    direction = np.minimum((angle % 180) * (EDGE_BINS / 180), EDGE_BINS - 1).astype(np.int32)
    rows = np.linspace(0, small.shape[0], CELLS + 1).astype(int)
    cols = np.linspace(0, small.shape[1], CELLS + 1).astype(int)
    parts = []
    for r0, r1 in pairwise(rows):
        for c0, c1 in pairwise(cols):
            colour = cv2.calcHist([hsv[r0:r1, c0:c1]], [0, 1], None, [H_BINS, S_BINS], [0, 180, 0, 256]).ravel()
            parts.append(np.sqrt(colour / max(float(colour.sum()), 1.0)))
            cell_dir, cell_strength = direction[r0:r1, c0:c1].ravel(), strength[r0:r1, c0:c1].ravel()
            edges = np.bincount(cell_dir, weights=cell_strength, minlength=EDGE_BINS)
            edges = edges - edges.mean()
            norm = float(np.linalg.norm(edges))
            parts.append(edges / norm if norm > 1e-6 else np.zeros(EDGE_BINS))
    return np.concatenate(parts).astype(np.float32)


def similarity(desc: np.ndarray, refs: np.ndarray) -> np.ndarray:
    """Likeness, 0..1, of one description to each row of refs: the mean of colour (1 - Bhattacharyya distance) and
    shape (correlation, below 0 counted as 0), each averaged over the quarters."""
    own = desc.reshape(CELLS * CELLS, CELL_LEN)
    other = refs.reshape(len(refs), CELLS * CELLS, CELL_LEN)
    overlap = np.einsum("qk,rqk->rq", own[:, :COLOUR_LEN], other[:, :, :COLOUR_LEN])
    colour = 1.0 - np.sqrt(np.clip(1.0 - overlap, 0.0, 1.0))
    shape = np.clip(np.einsum("qk,rqk->rq", own[:, COLOUR_LEN:], other[:, :, COLOUR_LEN:]), 0.0, 1.0)
    return (colour.mean(axis=1) + shape.mean(axis=1)) / 2


class DisplayCheck:
    """Scores each capture's cabinet zone against the learnt references (the best likeness, 1 = the same look)."""

    def __init__(self, zone: tuple[float, float, float, float], min_score: float = 0.6, refs_path: str | None = None):
        self._zone = zone
        self._min_score = min_score
        self._path = refs_path
        self._refs = np.empty((0, DESC_LEN), np.float32)
        self._times: list[float] = []
        if refs_path and os.path.exists(refs_path):
            self._load(refs_path)

    def _load(self, path: str) -> None:
        """Reads saved references; a corrupt or incomplete file starts the worker with none (and is overwritten
        by the next reference it learns) instead of stopping it."""
        try:
            with np.load(path) as saved:
                refs = np.asarray(saved["refs"], np.float32)
                times = [float(t) for t in saved["times"]]
            if refs.ndim != 2 or refs.shape[1] != DESC_LEN:  # described another way: cannot be compared
                raise ValueError(f"references of shape {refs.shape}, expected (n, {DESC_LEN})")
            if len(refs) != len(times):
                raise ValueError(f"{len(refs)} references but {len(times)} times")
        except Exception as exc:  # noqa: BLE001 - OSError, ValueError, KeyError, BadZipFile and more
            log.warning("ignoring display references in %s: %s: %s", path, type(exc).__name__, exc)
            return
        self._refs, self._times = refs, times

    @property
    def n_refs(self) -> int:
        return len(self._refs)

    def check(self, image: np.ndarray, detections: list[Detection], now: float) -> tuple[float | None, bool]:
        """(score, seen): the score is None until a reference exists, and then the display counts as seen."""
        desc = describe(zone_crop(image, self._zone))
        score: float | None = None
        seen = True
        if len(self._refs):
            score = round(float(similarity(desc, self._refs).max()), 3)
            seen = score >= self._min_score
        if self._worth_learning(image, detections, now):
            self._learn(desc, now)
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

    def _learn(self, desc: np.ndarray, now: float) -> None:
        self._refs = np.vstack([self._refs, desc])[-MAX_REFS:]
        self._times = (self._times + [now])[-MAX_REFS:]
        if self._path:
            tmp = self._path + ".tmp"
            with open(tmp, "wb") as handle:
                np.savez(handle, refs=self._refs, times=np.array(self._times))
            os.replace(tmp, self._path)
