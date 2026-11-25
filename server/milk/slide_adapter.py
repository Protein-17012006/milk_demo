"""Adapter for the Slide snack-can detector of HOANG-P09 (YOLO26s, four flavours, trained on renders).

The model returns one box per can with its flavour, so there is no database look-up as in the milk
pipeline: the box class is the SKU and the YOLO score is the confidence. Settings:

    MILK_SLIDE_WEIGHTS  detector weights (default ~/Desktop/Datagent/slide_pilot/runs_v3/best.pt, the model
                        chosen for the demo on 2026-11-22)
    MILK_SLIDE_IMGSZ    input size of the longer side (default 2560: a 2560x1440 store frame keeps its own
                        pixels, so cans are as large as in the training pictures)
    MILK_SLIDE_CONF     YOLO confidence threshold (default 0.25, as in the evaluation on the store frames)
    MILK_DEVICE         "cuda" or "cpu"

The class names of the model (original145, sourcream150, cheese145, hot160) are written as sku_id, as the
milk pipeline writes its TMP-MLK-* labels; product names come from skus.json. Mapping them to Datagent's
SKU (the product name) is the backend's alias table.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from .catalog import SKUS, product_names  # noqa: F401 - both stay importable from here
from .cvoutput import Detection
from .pipeline import dedupe

DEFAULT_WEIGHTS = "~/Desktop/Datagent/slide_pilot/runs_v3/best.pt"


def to_detections(classes, scores, boxes_xyxy, names: dict[int, str], product: dict[str, str]) -> list[Detection]:
    """YOLO output (class index, score, x0 y0 x1 y1) as Detections with x, y, width, height boxes, one per can:
    the model's repeated boxes for one can are dropped (pipeline.dedupe)."""
    out = []
    for c, s, b in zip(classes, scores, boxes_xyxy, strict=False):
        label = names[int(c)]
        x0, y0, x1, y1 = (float(v) for v in b)
        out.append(Detection(label, product.get(label, label), float(s), (x0, y0, x1 - x0, y1 - y0)))
    return dedupe(out)


class SlidePipeline:
    name = "slide"

    def __init__(self, models_dir: str = "") -> None:
        from ultralytics import YOLO  # imported lazily: needs torch

        weights = Path(os.environ.get("MILK_SLIDE_WEIGHTS") or DEFAULT_WEIGHTS).expanduser()
        if not weights.is_file():
            raise FileNotFoundError(f"Slide weights not found: {weights}; set MILK_SLIDE_WEIGHTS")
        self._model = YOLO(str(weights))
        self._imgsz = int(os.environ.get("MILK_SLIDE_IMGSZ", "2560"))
        self._conf = float(os.environ.get("MILK_SLIDE_CONF", "0.25"))
        self.device = os.environ.get("MILK_DEVICE") or ("cuda" if _cuda() else "cpu")
        self._product = product_names()
        self._model.predict(
            np.full((720, 1280, 3), 128, np.uint8),
            imgsz=self._imgsz,
            conf=self._conf,
            device=self.device,
            verbose=False,
        )  # load onto the GPU now, not on the first frame

    def detect(self, image: np.ndarray) -> list[Detection]:
        res = self._model.predict(
            image, imgsz=self._imgsz, conf=self._conf, max_det=500, device=self.device, verbose=False
        )[0]
        return to_detections(
            res.boxes.cls.tolist(), res.boxes.conf.tolist(), res.boxes.xyxy.tolist(), self._model.names, self._product
        )


def _cuda() -> bool:
    try:
        import torch

        return torch.cuda.is_available()
    except Exception:  # noqa: BLE001
        return False
