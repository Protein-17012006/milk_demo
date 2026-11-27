"""Model adapters. Each returns cvoutput.Detection objects in the coordinates of the image given.

`null` finds nothing; it lets the stream, dashboard and storage run before the model is installed.
`long` wraps the team's milk-carton pipeline (YOLO26s + DINOv2-S + LanceDB) from Long's GPU machine.
`slide` is the Slide snack-can detector of HOANG-P09. Several can run on the same frame, joined with "+":
`long+slide` counts the milk cartons and the Slide cans in one picture.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

import numpy as np

from .cvoutput import Detection

OVERLAP = 0.5  # a box of an earlier model that covers this much of a later model's box is the same object
DUPLICATE = 0.5  # two boxes of one model with this IoU or more are one object: on the store frames of 23/11
#                  repeated boxes had IoU 0.6-1.0 and neighbouring cans 0.25 or less


class Pipeline(Protocol):
    name: str

    def detect(self, image: np.ndarray) -> list[Detection]: ...


class NullPipeline:
    name = "null"

    def detect(self, image: np.ndarray) -> list[Detection]:
        return []


def _shared(a: tuple, b: tuple) -> float:
    """Share of the smaller of two x, y, w, h boxes that the other covers."""
    ix = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    smaller = min(a[2] * a[3], b[2] * b[3])
    return ix * iy / smaller if smaller > 0 else 0.0


def _iou(a: tuple, b: tuple) -> float:
    """Intersection over union of two x, y, w, h boxes."""
    ix = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def dedupe(dets: list[Detection]) -> list[Detection]:
    """One detection per object from one model: where boxes overlap by DUPLICATE or more, the most confident
    one stays, whatever its class. The Slide model can return one can twice, as one flavour or as two."""
    kept: list[Detection] = []
    for d in sorted(dets, key=lambda d: d.confidence, reverse=True):
        if all(_iou(d.box, k.box) < DUPLICATE for k in kept):
            kept.append(d)
    return [d for d in dets if any(d is k for k in kept)]


def merge(first: list[Detection], later: list[Detection]) -> list[Detection]:
    """Detections of two models on one frame. Where a box of `first` lies on a box of `later` (most of the
    smaller one shared), the object is the later model's: the milk pipeline sees a Slide can as an
    unrecognised carton, so without this one can would be counted twice."""
    kept = [d for d in first if all(_shared(d.box, e.box) < OVERLAP for e in later)]
    return kept + list(later)


class CombinedPipeline:
    """Runs its pipelines in order on the same frame; later ones win where boxes overlap."""

    def __init__(self, parts: list[Pipeline]) -> None:
        self.parts = parts
        self.name = "+".join(p.name for p in parts)
        devices = {getattr(p, "device", "cpu") for p in parts}
        self.device = devices.pop() if len(devices) == 1 else "+".join(sorted(devices))

    def detect(self, image: np.ndarray) -> list[Detection]:
        out: list[Detection] = []
        for p in self.parts:
            out = merge(out, p.detect(image))
        return out


def _one(kind: str, models_dir: str, env: Mapping[str, str] | None = None) -> Pipeline:
    if kind == "null":
        return NullPipeline()
    if kind == "long":
        from .long_adapter import LongPipeline  # imported lazily: needs torch and the model files

        return LongPipeline(models_dir, env)
    if kind == "slide":
        from .slide_adapter import SlidePipeline  # imported lazily: needs torch and the weights

        return SlidePipeline(models_dir, env)
    raise ValueError(f"unknown MILK_PIPELINE part {kind!r}; expected 'null', 'long' or 'slide'")


def load_pipeline(kind: str, models_dir: str, env: Mapping[str, str] | None = None) -> Pipeline:
    """The pipeline named by `kind` ("long", "slide", "long+slide", "null"). `env` holds the model settings of one
    release; None means the process environment, which is where the live release's settings are."""
    parts = [k.strip() for k in kind.split("+") if k.strip()]
    if len(parts) == 1:
        return _one(parts[0], models_dir, env)
    if not parts:
        raise ValueError("MILK_PIPELINE is empty")
    return CombinedPipeline([_one(k, models_dir, env) for k in parts])
