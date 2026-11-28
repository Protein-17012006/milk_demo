"""The gallery's read rule, shared by the worker and the training tools: how a Slide can's flavour is read from
people's labelled crops, and the namer that applies it to the detector's boxes.

A crop is described by its colour: the middle 70% of its height and 60% of its width, grey-world balanced, a hue x
saturation histogram (18 x 8) of it, square-rooted and of unit length. A can is read by its 10 nearest crops (cosine):
a flavour is named only when it holds at least 60% of their weight, at least 3 of the 10, and the gallery has at
least 20 cans of it; otherwise the read is unsure. GalleryNamer renames the detector's boxes by this rule and never
drops, adds or reorders one: a box it cannot read keeps the detector's name and is marked unsure.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from milk.catalog import product_names
from milk.cvoutput import Detection

GALLERY_KEY = "MILK_SLIDE_GALLERY"

MIN_IMAGES = 20
K = 10
MIN_SHARE = 0.6
MIN_VOTES = 3


def _grey_world(img: np.ndarray) -> np.ndarray:
    m = img.reshape(-1, 3).mean(axis=0)
    return np.clip(img * (m.mean() / np.maximum(m, 1)), 0, 255).astype(np.uint8)


def colour(crop: np.ndarray) -> np.ndarray:
    """Unit 144-vector of the crop's middle colours."""
    import cv2

    h, w = crop.shape[:2]
    mid = _grey_world(crop[int(h * 0.15) : int(h * 0.85), int(w * 0.2) : int(w * 0.8)])
    hsv = cv2.cvtColor(mid, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [18, 8], [0, 180, 0, 256]).ravel()
    hist = np.sqrt(hist / max(float(hist.sum()), 1.0))
    return hist / max(float(np.linalg.norm(hist)), 1e-9)


def mean_colour(feats: list[np.ndarray]) -> np.ndarray | None:
    """The colour of a can seen in several crops: their mean, of unit length again; None when there is no crop."""
    if not feats:
        return None
    m = np.mean(np.stack(feats), axis=0)
    return m / max(float(np.linalg.norm(m)), 1e-9)


@dataclass
class Gallery:
    features: np.ndarray
    labels: np.ndarray
    sources: np.ndarray
    built_at: str
    none_threshold: float | None = None
    objects: np.ndarray | None = None  # the can each crop shows: one truth box cut from many frames is one can

    def save(self, path: Path) -> None:
        np.savez(
            path,
            features=self.features,
            labels=self.labels.astype(str),
            sources=self.sources.astype(str),
            built_at=np.array(self.built_at),
            none_threshold=np.array(np.nan if self.none_threshold is None else self.none_threshold),
            objects=(self.objects if self.objects is not None else self.sources).astype(str),
        )

    @classmethod
    def load(cls, path: Path) -> Gallery:
        d = np.load(path, allow_pickle=False)
        nt = float(d["none_threshold"])
        objects = d["objects"] if "objects" in d.files else None
        return cls(d["features"], d["labels"], d["sources"], str(d["built_at"]), None if np.isnan(nt) else nt, objects)

    def counts(self) -> dict[str, int]:
        """Cans per label (MIN_IMAGES counts cans, not crops); crops when the gallery does not know its cans."""
        if self.objects is None:
            return dict(Counter(self.labels.tolist()))
        return dict(Counter(label for label, _ in set(zip(self.labels.tolist(), self.objects.tolist(), strict=True))))


@dataclass(frozen=True)
class GalleryVote:
    sku: str | None
    share: float
    votes: int
    none_hit: bool


def read(gallery: Gallery, feature: np.ndarray, k: int = K) -> GalleryVote:
    """The flavour the k nearest crops name, or sku None when they are not sure enough (see the module text)."""
    if not len(gallery.labels):
        return GalleryVote(None, 0.0, 0, False)
    sims = gallery.features @ feature
    idx = np.argsort(-sims)[:k]
    weight: Counter = Counter()
    count: Counter = Counter()
    for i in idx:
        weight[gallery.labels[i]] += max(float(sims[i]), 0.0)
        count[gallery.labels[i]] += 1
    top, top_weight = weight.most_common(1)[0]
    share = top_weight / max(sum(weight.values()), 1e-9)
    counts = gallery.counts()
    sure = top != "none" and share >= MIN_SHARE and count[top] >= MIN_VOTES and counts.get(top, 0) >= MIN_IMAGES
    first = idx[0]
    none_hit = (
        gallery.none_threshold is not None
        and gallery.labels[first] == "none"
        and float(sims[first]) >= gallery.none_threshold
    )
    return GalleryVote(top if sure else None, share, count[top], bool(none_hit))


def crop_of(image: np.ndarray, box) -> np.ndarray | None:
    x, y, w, h = (int(round(v)) for v in box)
    crop = image[max(y, 0) : y + h, max(x, 0) : x + w]
    return crop if crop.size and crop.shape[0] >= 4 and crop.shape[1] >= 4 else None


class GalleryNamer:
    """Names Slide boxes from the gallery. Boxes are x, y, width, height in the coordinates of the image given to name()."""

    def __init__(
        self,
        gallery: Gallery,
        product: Mapping[str, str],
        feature: Callable[[np.ndarray], np.ndarray] = colour,
    ) -> None:
        self.gallery = gallery
        self.product = product
        self.feature = feature
        self.counts = gallery.counts()

    def name(self, image: np.ndarray, detections: list[Detection]) -> list[Detection]:
        return [self._one(image, d) for d in detections]

    def _one(self, image: np.ndarray, det: Detection) -> Detection:
        if self.counts.get(det.sku_id, 0) < MIN_IMAGES:
            return det  # the gallery has no grounds to read this name (milk boxes included)
        crop = crop_of(image, det.box)
        if crop is None:
            return replace(det, unsure=True)
        vote = read(self.gallery, self.feature(crop))
        if vote.sku is None:
            return replace(det, unsure=True)
        return replace(det, sku_id=str(vote.sku), sku_name=self.product.get(str(vote.sku), str(vote.sku)), unsure=False)


def load_namer(env: Mapping[str, str]) -> GalleryNamer | None:
    """The namer of the gallery file MILK_SLIDE_GALLERY points at; None when the variable is unset or empty."""
    path = env.get(GALLERY_KEY, "")
    if not path:
        return None
    if not Path(path).is_file():
        raise FileNotFoundError(f"{GALLERY_KEY} points at a file that is not there: {path}")
    return GalleryNamer(Gallery.load(Path(path)), product_names())
