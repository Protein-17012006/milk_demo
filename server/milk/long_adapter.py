"""Adapter for the team's carton pipeline (carton_recognition/cv_output.py on Long's machine).

It calls that pipeline's own read_units(), so detection, database lookup and per-carton
scores are exactly those behind the CV Output report of 17/10/2026. It needs the
pipeline's environment (torch, ultralytics, lancedb) and its files:

    MILK_LONG_DIR    folder with cv_output.py, recognize.py, embedder_types.pt and db_types/
                     (default ~/Desktop/Datagent/carton_recognition)
    MILK_LONG_YOLO   type detector weights (default <MILK_LONG_DIR>/../yolo/best_types.pt)
    MILK_LONG_CONF   YOLO confidence threshold (default 0.25, as in the report)
    MILK_LONG_IMGSZ  YOLO input size (default 1280, as in the report)
    MILK_DEVICE      "cuda" or "cpu"; give "cuda", not "cuda:0": the pipeline turns on
                     half precision only for the exact string "cuda"
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

from .cvoutput import Detection


class LongPipeline:
    name = "long"

    def __init__(self, models_dir: str = "") -> None:
        root = Path(os.environ.get("MILK_LONG_DIR") or Path.home() / "Desktop/Datagent/carton_recognition").expanduser()
        if not (root / "cv_output.py").is_file():
            raise FileNotFoundError(f"cv_output.py not found in {root}; set MILK_LONG_DIR")
        sys.path.insert(0, str(root))
        import cv_output  # the team's pipeline; it puts its own folder on sys.path
        from recognize import Recognizer
        from ultralytics import YOLO

        yolo_path = Path(os.environ.get("MILK_LONG_YOLO") or root.parent / "yolo" / "best_types.pt").expanduser()
        self._cvo = cv_output
        self._rec = Recognizer(device=os.environ.get("MILK_DEVICE") or None, types=True)
        self._yolo = YOLO(str(yolo_path))
        self._conf = float(os.environ.get("MILK_LONG_CONF", "0.25"))
        self._imgsz = int(os.environ.get("MILK_LONG_IMGSZ", "1280"))
        self.device = str(self._rec.embedder.device)
        self._warm_up()

    def _warm_up(self) -> None:
        """The first call loads everything onto the GPU; do it now rather than on the first live frame."""
        blank = np.full((720, 1280, 3), 128, np.uint8)
        self._yolo.predict(blank, imgsz=self._imgsz, verbose=False, device=self._rec.embedder.device)
        self._rec.embedder.embed([self._cvo.crop_box(blank, [100, 100, 160, 220])])

    def read_units(self, image: np.ndarray) -> list[dict]:
        """The pipeline's own per-carton reading (box, detector and database SKU, unit_score)."""
        return self._cvo.read_units(image, self._yolo, self._rec, self._conf, self._imgsz)

    def to_detections(self, units: list[dict]) -> list[Detection]:
        return [
            Detection(u["sku_id"], self._cvo.NAME_OF.get(u["sku_id"]), float(u["unit_score"]), tuple(u["box"]))
            for u in units
        ]

    def detect(self, image: np.ndarray) -> list[Detection]:
        return self.to_detections(self.read_units(image))
