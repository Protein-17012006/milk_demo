"""Adapter for the team's carton pipeline (carton_recognition, Long's code, on the counting machine).

It runs that pipeline's detector (recognize.detect) and database look-up (Recognizer and cv_output.type_support), and
decides here, in readings() and decide(), which SKU each box is and how sure: with best_types.pt (12 classes) and
MILK_LONG_TILE=0 that is exactly cv_output.read_units, the reading behind the CV Output report of 17/10/2026.
Settings:

    MILK_LONG_DIR       folder with cv_output.py, recognize.py, embedder_types.pt and db_types/
                        (default ~/Desktop/Datagent/carton_recognition)
    MILK_LONG_YOLO      detector weights (default <MILK_LONG_DIR>/../yolo/best_types.pt)
    MILK_LONG_CONF      YOLO confidence threshold (default 0.25, as in the report)
    MILK_LONG_IMGSZ     YOLO input size (default 1280, as in the report)
    MILK_LONG_TILE      0 (default): the whole frame only. 1280: also windows of 1280 px at the frame's own size,
                        merged by NMS: a store camera's cartons of 25-45 px are only seen at full size
    MILK_LONG_VARIANTS  0 (default): every TH carton of the store-view model is the merged row TMP-MLK-TH-00.
                        1: name Có đường / Ít đường when the database clearly leans to one, for cameras close enough
                        to read the label
    MILK_LONG_TH_CONFIRM  database (default): the database may reject any box, as before. detector: a box of the
                        merged TH class is kept without asking the database and scored by the detector alone; on a
                        store camera the database rejects real cartons of an arrangement it has not stored
                        (design 2026-11-26). Every other class still goes through the database
    MILK_DEVICE        "cuda" or "cpu"; give "cuda", not "cuda:0": the pipeline turns on
                        half precision only for the exact string "cuda"
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

import numpy as np

from .catalog import product_names
from .cvoutput import Detection

TH_BRAND = "th_true_milk"  # the store-view model's one TH class; Long's type classes start with it too
VARIANT_SHARE = 0.7  # share of the TH backing one type must hold before a TH carton is named by type
TH_CONFIRMS = ("database", "detector")  # who may reject a box of the merged TH class (MILK_LONG_TH_CONFIRM)

# Detector class -> model label (the backend maps labels to product names). The 12 type classes are Long's SKUS.
LABEL_OF_CLASS = {
    TH_BRAND: "TMP-MLK-TH-00",
    "th_true_milk_sweetened": "TMP-MLK-TH-01",
    "th_true_milk_less_sugar": "TMP-MLK-TH-02",
    "vinamilk_fresh_no_sugar": "TMP-MLK-VNM-01",
    "vinamilk_fresh_less_sugar": "TMP-MLK-VNM-02",
    "vinamilk_fresh_sweetened": "TMP-MLK-VNM-03",
    "vinamilk_chocolate": "TMP-MLK-VNM-04",
    "vinamilk_banana": "TMP-MLK-VNM-05",
    "vinamilk_melon": "TMP-MLK-VNM-06",
    "vinamilk_soy": "TMP-MLK-VNM-07",
    "vinamilk_soy_almond": "TMP-MLK-VNM-08",
    "vinamilk_soy_black_sesame": "TMP-MLK-VNM-09",
    "vinamilk_9_seeds": "TMP-MLK-VNM-10",
}


def _settings() -> tuple[int, bool]:
    """(MILK_LONG_TILE, MILK_LONG_VARIANTS) from the environment."""
    return int(os.environ.get("MILK_LONG_TILE") or 0), os.environ.get("MILK_LONG_VARIANTS", "0") == "1"


def _th_confirm() -> str:
    """MILK_LONG_TH_CONFIRM from the environment: "database" (also when unset or empty) or "detector". Any other
    value stops the worker: a misspelt setting must not quietly count as the default."""
    value = (os.environ.get("MILK_LONG_TH_CONFIRM") or "").strip().lower() or "database"
    if value not in TH_CONFIRMS:
        raise ValueError(f"MILK_LONG_TH_CONFIRM must be one of {TH_CONFIRMS}, not {value!r}")
    return value


def needs_lookup(cls_name: str, variants: bool, th_confirm: str) -> bool:
    """Whether a box of this detector class is sent to the database. Only a merged-TH box in detector mode is not,
    unless the database is still wanted to name its type."""
    return not (cls_name == TH_BRAND and th_confirm == "detector" and not variants)


def decide(
    cls_name: str,
    yolo_conf: float,
    brand: str,
    kind_share: Mapping[str, float],
    variants: bool,
    th_confirm: str = "database",
) -> tuple[str | None, float]:
    """(model label, unit score) of one box. brand is the database's answer ("unknown": not one of our cartons);
    kind_share the share of the box's nearest stored cartons of each kind.

    - unknown to the database: (None, 0.0), an unrecognised box;
    - the merged TH class: backed by every TH kind; named by type only with `variants` and one type leading;
    - the merged TH class with th_confirm "detector": never rejected, scored by the detector alone;
    - a type class: named by the detector, backed by the share of that type, as cv_output.read_units does."""
    by_detector = cls_name == TH_BRAND and th_confirm == "detector"
    if brand == "unknown" and not by_detector:
        return None, 0.0
    if cls_name == TH_BRAND:
        th = {kind: share for kind, share in kind_share.items() if kind.startswith(TH_BRAND)}
        support = sum(th.values())
        label = LABEL_OF_CLASS[TH_BRAND]
        typed = [(share, kind) for kind, share in th.items() if kind != TH_BRAND and kind in LABEL_OF_CLASS]
        if variants and brand != "unknown" and typed and support > 0:
            share, kind = max(typed)
            if share / support >= VARIANT_SHARE:
                label = LABEL_OF_CLASS[kind]
        return label, round(yolo_conf if by_detector else yolo_conf * support, 3)
    return LABEL_OF_CLASS.get(cls_name, cls_name), round(yolo_conf * kind_share.get(cls_name, 0.0), 3)


def readings(
    rows: np.ndarray,
    names: Mapping[int, str],
    lookups: list[dict],
    shares: list[Mapping[str, float]],
    product: Mapping[str, str],
    variants: bool,
    th_confirm: str = "database",
) -> list[Detection]:
    """Detections of one frame from the detector's rows (x0, y0, x1, y1, confidence, class, ...), the database's
    answer for each box and its kind shares."""
    out = []
    for row, found, share in zip(rows, lookups, shares, strict=True):
        x0, y0, x1, y1, conf, cls = (float(v) for v in row[:6])
        label, score = decide(names[int(cls)], conf, found["brand"], share, variants, th_confirm)
        box = (int(round(x0)), int(round(y0)), int(round(x1 - x0)), int(round(y1 - y0)))
        out.append(Detection(label, product.get(label) if label else None, score, box))
    return out


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
        self._tile, self._variants = _settings()
        self._th_confirm = _th_confirm()
        self._product = product_names()
        self.device = str(self._rec.embedder.device)
        self._warm_up()

    def _warm_up(self) -> None:
        """The first call loads everything onto the GPU; do it now rather than on the first live frame."""
        blank = np.full((720, 1280, 3), 128, np.uint8)
        self._yolo.predict(blank, imgsz=self._imgsz, verbose=False, device=self._rec.embedder.device)
        self._rec.embedder.embed([self._cvo.crop_box(blank, [100, 100, 160, 220])])

    def read_units(self, image: np.ndarray) -> list[dict]:
        """The pipeline's own per-carton reading (box, detector and database SKU, unit_score): worker/regression.py
        compares the worker with it."""
        return self._cvo.read_units(image, self._yolo, self._rec, self._conf, self._imgsz)

    def to_detections(self, units: list[dict]) -> list[Detection]:
        return [
            Detection(u["sku_id"], self._cvo.NAME_OF.get(u["sku_id"]), float(u["unit_score"]), tuple(u["box"]))
            for u in units
        ]

    def detect(self, image: np.ndarray) -> list[Detection]:
        device = self._rec.embedder.device
        det = self._cvo.detect(image, self._yolo, device, self._conf, self._imgsz, tile=self._tile)
        det = self._cvo.one_box_per_unit(det)
        if not len(det):
            return []
        names = self._yolo.names
        ask = [i for i, row in enumerate(det) if needs_lookup(names[int(row[5])], self._variants, self._th_confirm)]
        lookups: list[dict] = [{"brand": "unknown"} for _ in det]  # the answer decide() ignores for a box not asked
        shares: list[Mapping[str, float]] = [{} for _ in det]
        if ask:
            vectors = self._rec.embedder.embed([self._cvo.crop_box(image, det[i, :4]) for i in ask])
            found, support = self._rec.lookup(vectors), self._cvo.type_support(self._rec, vectors)
            for i, lookup, share in zip(ask, found, support, strict=True):
                lookups[i], shares[i] = lookup, share
        return readings(det, names, lookups, shares, self._product, self._variants, self._th_confirm)
