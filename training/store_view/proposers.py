"""The two box sources of the auto-labeller (auto-label design 5.2), run on one store frame.

A: the Slide detector the worker runs (milk.slide_adapter.SlidePipeline), at confidence 0.05 and imgsz 2560: boxes
   with a flavour.
B: YOLOE with visual prompts, the boxes people drew on the camera's prompt keyframes, run on the crop of the product
   region at imgsz 640 and confidence 0.3: boxes without a flavour. One run per prompt keyframe; the union is thinned
   by non-maximum suppression.

Only boxes whose centre lies in the region are kept. Boxes are x, y, width, height in frame pixels. Runs in a venv of
its own (.venv-label on the counting machine), never in the worker's.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np

SLIDE_CONF = "0.05"
SLIDE_IMGSZ = "2560"
YOLOE_IMGSZ = 640
YOLOE_CONF = 0.3


@dataclass(frozen=True)
class Proposal:
    source: str  # "A" (Slide detector) or "B" (YOLOE)
    box: tuple[float, float, float, float]  # x, y, w, h in frame pixels
    conf: float
    sku: str | None  # the detector's flavour (A only)


def region_prompts(rows: list[dict], region: tuple[int, int, int, int]) -> np.ndarray:
    """Truth rows (box x y w h in frame pixels) as x0 y0 x1 y1 in the region crop; ignore rows are left out."""
    rx, ry = region[0], region[1]
    boxes = [
        [r["box"][0] - rx, r["box"][1] - ry, r["box"][0] - rx + r["box"][2], r["box"][1] - ry + r["box"][3]]
        for r in rows
        if r.get("kind") != "ignore"
    ]
    return np.array(boxes, dtype=np.float32).reshape(-1, 4)


def in_region(box, region: tuple[int, int, int, int]) -> bool:
    cx, cy = box[0] + box[2] / 2, box[1] + box[3] / 2
    return bool(region[0] <= cx <= region[2] and region[1] <= cy <= region[3])


def _iou(a, b) -> float:
    ix = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    inter = ix * iy
    return inter / max(a[2] * a[3] + b[2] * b[3] - inter, 1e-9)


def union_nms(props: list[Proposal], iou: float = 0.5) -> list[Proposal]:
    """The surer box of any overlapping pair (IoU >= iou), in the order the kept boxes came."""
    keep: list[Proposal] = []
    for p in sorted(props, key=lambda p: -p.conf):
        if all(_iou(p.box, k.box) < iou for k in keep):
            keep.append(p)
    return [p for p in props if p in keep]


class Sources:
    """Both sources, loaded once; frame(image) gives the proposals of one frame."""

    def __init__(
        self,
        slide_weights: str | None,
        yoloe_weights: str,
        prompt_images: list[np.ndarray],
        prompt_boxes: list[np.ndarray],
        region: tuple[int, int, int, int],
    ) -> None:
        self._slide = None  # without Slide weights, YOLOE alone (draft boxes for any product group)
        if slide_weights:
            os.environ["MILK_SLIDE_WEIGHTS"] = slide_weights
            os.environ["MILK_SLIDE_CONF"] = SLIDE_CONF
            os.environ["MILK_SLIDE_IMGSZ"] = SLIDE_IMGSZ
            from milk.slide_adapter import SlidePipeline

            self._slide = SlidePipeline()
        self._yoloe_weights = yoloe_weights
        x0, y0, x1, y1 = region
        self._prompts = [(img[y0:y1, x0:x1].copy(), boxes) for img, boxes in zip(prompt_images, prompt_boxes, strict=True)]
        self._region = region

    def _yoloe(self, image: np.ndarray) -> list[Proposal]:
        from ultralytics import YOLOE
        from ultralytics.models.yolo.yoloe import YOLOEVPSegPredictor

        x0, y0, x1, y1 = self._region
        crop = image[y0:y1, x0:x1]
        out: list[Proposal] = []
        for ref, boxes in self._prompts:
            model = YOLOE(self._yoloe_weights)  # fresh per prompt: the visual prompt sets the model's classes
            r = model.predict(
                crop,
                refer_image=ref,
                visual_prompts=dict(bboxes=boxes, cls=np.zeros(len(boxes), dtype=int)),
                predictor=YOLOEVPSegPredictor,
                imgsz=YOLOE_IMGSZ,
                conf=YOLOE_CONF,
                verbose=False,
            )[0]
            for (bx0, by0, bx1, by1), c in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), strict=True):
                out.append(Proposal("B", (bx0 + x0, by0 + y0, bx1 - bx0, by1 - by0), float(c), None))
        return union_nms(out)

    def frame(self, image: np.ndarray) -> list[Proposal]:
        detections = self._slide.detect(image) if self._slide else []
        a = [Proposal("A", tuple(float(v) for v in d.box), float(d.confidence), d.sku_id) for d in detections]
        return [p for p in a + self._yoloe(image) if in_region(p.box, self._region)]
