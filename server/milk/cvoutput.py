"""CV Output rows and Capture Log lines in the format of Datagent's Data Dictionary.

The column order and value formats follow the sample files sent with the CV Output
report v1.0 of 17/10/2026: one row per SKU per image, 16 columns, `is_flagged` as
TRUE/FALSE, `bounding_box` as a JSON list of [x, y, width, height] in pixels.
"""

from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import dataclass
from datetime import datetime

import numpy as np

CV_OUTPUT_COLUMNS = [
    "reading_id",
    "capture_id",
    "store_id",
    "camera_id",
    "capture_timestamp",
    "capture_source",
    "image_filename",
    "sku_id",
    "sku_name",
    "unit_count",
    "confidence_score",
    "detection_method",
    "bounding_box",
    "is_flagged",
    "flag_reason",
    "processing_time_ms",
]

CAPTURE_LOG_COLUMNS = [
    "capture_id",
    "store_id",
    "camera_id",
    "capture_timestamp",
    "capture_source",
    "image_filename",
    "rows_written",
    "units_found",
    "flagged_rows",
    "processing_time_ms",
]

UNRECOGNIZED = "UNRECOGNIZED"


@dataclass(frozen=True)
class Detection:
    """One carton found in a frame. `sku_id` is None when no known SKU matched."""

    sku_id: str | None
    sku_name: str | None
    confidence: float
    box: tuple[int, int, int, int]  # x, y, width, height in source pixels
    method: str = "Visual"


@dataclass(frozen=True)
class CaptureStem:
    """Shared part of capture_id, reading_id and image_filename for one capture."""

    store_code: str
    date: str  # YYYYMMDD
    time: str  # HHMMSS, plus -2, -3 ... when several captures fall in the same second

    @property
    def text(self) -> str:
        return f"{self.store_code}-{self.date}-{self.time}"


class CaptureIdAllocator:
    """Gives each capture a unique stem; several captures in one second get -2, -3, ..."""

    def __init__(self) -> None:
        self._last: tuple[str, str, str] | None = None
        self._count = 0

    def stem(self, store_code: str, ts: datetime) -> CaptureStem:
        key = (store_code, f"{ts:%Y%m%d}", f"{ts:%H%M%S}")
        if key == self._last:
            self._count += 1
            return CaptureStem(key[0], key[1], f"{key[2]}-{self._count}")
        self._last, self._count = key, 1
        return CaptureStem(*key)


def _row_confidence(detections: list[Detection]) -> tuple[float, float]:
    """(raw mean, stored score) as in carton_recognition/cv_output.py: the stored score is rounded
    down to 2 decimals and the flag uses the raw mean, so a stored 0.70 is never a flagged 0.6987."""
    raw = float(np.mean([d.confidence for d in detections]))
    return raw, math.floor(raw * 100 + 1e-9) / 100


def build_capture(
    detections: list[Detection],
    *,
    stem: CaptureStem,
    store_id: str,
    camera_id: str,
    capture_source: str,
    ts: datetime,
    processing_time_ms: int,
    flag_threshold: float = 0.70,
) -> tuple[list[dict], dict]:
    """Group detections into CV Output rows and one Capture Log line.

    `stem` comes from CaptureIdAllocator, for example S01-20261118-170900 or
    S01-20261118-170900-2. Rows are ordered by unit count, highest first, with the
    unrecognised row last, as in the 17/10 sample.
    """
    capture_id = f"CAP-{stem.text}"
    image_filename = f"{camera_id}_{stem.date}_{stem.time}.jpg"
    timestamp = ts.isoformat(timespec="seconds")

    groups: dict[str | None, list[Detection]] = {}
    for det in detections:
        groups.setdefault(det.sku_id, []).append(det)

    recognised = sorted(
        ((sku, dets) for sku, dets in groups.items() if sku is not None),
        key=lambda item: (-len(item[1]), item[0]),
    )
    ordered = recognised + ([(None, groups[None])] if None in groups else [])

    rows: list[dict] = []
    for seq, (sku_id, dets) in enumerate(ordered, start=1):
        if sku_id is None:
            confidence, flagged, reason, name = 0.0, True, "Unrecognized", None
        else:
            raw, confidence = _row_confidence(dets)
            flagged = raw < flag_threshold
            reason = "Low Confidence" if flagged else ""
            name = dets[0].sku_name
        methods = sorted({d.method for d in dets})
        rows.append(
            {
                "reading_id": f"RD-{stem.text}-{seq:03d}",
                "capture_id": capture_id,
                "store_id": store_id,
                "camera_id": camera_id,
                "capture_timestamp": timestamp,
                "capture_source": capture_source,
                "image_filename": image_filename,
                "sku_id": sku_id,
                "sku_name": name,
                "unit_count": len(dets),
                "confidence_score": confidence,
                "detection_method": methods[0] if len(methods) == 1 else " + ".join(methods),
                "bounding_box": [list(d.box) for d in dets],
                "is_flagged": flagged,
                "flag_reason": reason,
                "processing_time_ms": processing_time_ms,
            }
        )

    log = {
        "capture_id": capture_id,
        "store_id": store_id,
        "camera_id": camera_id,
        "capture_timestamp": timestamp,
        "capture_source": capture_source,
        "image_filename": image_filename,
        "rows_written": len(rows),
        "units_found": sum(r["unit_count"] for r in rows),
        "flagged_rows": sum(1 for r in rows if r["is_flagged"]),
        "processing_time_ms": processing_time_ms,
    }
    return rows, log


def counts_of(rows: list[dict]) -> dict[str, int]:
    """Units per SKU for the dashboard; unrecognised cartons are counted under UNRECOGNIZED."""
    return {(r["sku_id"] or UNRECOGNIZED): r["unit_count"] for r in rows}


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, list):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


def to_csv(records: list[dict], columns: list[str], bom: bool = True) -> str:
    """CSV text with a UTF-8 BOM so Excel shows Vietnamese names correctly."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(columns)
    for record in records:
        writer.writerow([_cell(record.get(col)) for col in columns])
    return ("﻿" if bom else "") + out.getvalue()
