"""Hourly health of the counting model, from the captures the backend keeps (no person needed).

`capture_boxes` reads the boxes of one capture: from `detections_json` (one score per box, written by the
worker since 23/11) or, for older captures, from the CV Output rows (one score per SKU). `hour_stats` sums up
one camera-hour for the Model page. Nothing here touches AWS.
"""

from __future__ import annotations

import json
import math
import statistics
from collections import Counter
from typing import Any

DUPLICATE_IOU = 0.5  # as DUPLICATE in server/milk/pipeline.py: two boxes this close are one object
UNRECOGNIZED = "UNRECOGNIZED"


def iou(a, b) -> float:
    """Intersection over union of two x, y, w, h boxes."""
    ix = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def _json_list(value: Any) -> list:
    if not value:
        return []
    return json.loads(value) if isinstance(value, str) else list(value)


def _label(row: dict) -> str | None:
    """Model label of a row: ingest keeps it in model_alias (sku_id became the product name)."""
    return row.get("model_alias") or row.get("sku_id") or None


def capture_boxes(item: dict) -> list[dict]:
    """Every box of one capture as {box_id, sku_id (model label or None), conf, box}, box_id from 1."""
    detections = _json_list(item.get("detections_json"))
    if detections:
        return [
            {
                "box_id": i,
                "sku_id": d.get("sku_id"),
                "conf": float(d.get("conf", 0.0)),
                "box": [int(v) for v in d["box"]],
            }
            for i, d in enumerate(detections, start=1)
        ]
    boxes = []
    for row in _json_list(item.get("rows_json")):
        for box in row.get("bounding_box") or []:
            boxes.append(
                {
                    "box_id": len(boxes) + 1,
                    "sku_id": _label(row),
                    "conf": float(row.get("confidence_score", 0.0)),
                    "box": [int(v) for v in box],
                }
            )
    return boxes


def _counts(item: dict) -> Counter:
    counts: Counter = Counter()
    for row in _json_list(item.get("rows_json")):
        counts[_label(row) or UNRECOGNIZED] += int(row.get("unit_count", 0))
    return counts


def _p90(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.9 * len(ordered)) - 1)]


def hour_stats(items: list[dict]) -> dict:
    """Health of one camera-hour. Shares are None when there is nothing to divide by."""
    if not items:
        return {"captures": 0}
    items = sorted(items, key=lambda it: str(it.get("capture_timestamp", "")))
    boxes = [capture_boxes(it) for it in items]
    all_boxes = [b for bs in boxes for b in bs]
    rows = [r for it in items for r in _json_list(it.get("rows_json"))]
    confs = [b["conf"] for b in all_boxes]
    units = [int(it.get("units_found", 0)) for it in items]
    counts = [_counts(it) for it in items]
    jumps = [
        sum(abs(a[k] - b[k]) for k in set(a) | set(b)) for a, b in zip(counts, counts[1:], strict=False)
    ]  # consecutive pairs
    duplicates = sum(
        1
        for bs in boxes
        for i in range(len(bs))
        for j in range(i + 1, len(bs))
        if iou(bs[i]["box"], bs[j]["box"]) >= DUPLICATE_IOU
    )
    processing = [float(it.get("processing_time_ms", 0)) for it in items]
    latency = [float(it.get("latency_ms", 0)) for it in items]
    return {
        "captures": len(items),
        "model_versions": sorted({it.get("model_version") or "unknown" for it in items}),
        "conf_median": statistics.median(confs) if confs else None,
        "conf_mean": statistics.fmean(confs) if confs else None,
        "flagged_row_pct": sum(bool(r.get("is_flagged")) for r in rows) / len(rows) if rows else None,
        "unrecognized_box_pct": sum(b["sku_id"] is None for b in all_boxes) / len(all_boxes) if all_boxes else None,
        "units_median": statistics.median(units),
        "units_min": min(units),
        "units_max": max(units),
        "jitter": statistics.fmean(jumps) if jumps else None,
        "duplicate_pairs": duplicates,
        "processing_ms_median": statistics.median(processing),
        "processing_ms_p90": _p90(processing),
        "latency_ms_median": statistics.median(latency),
    }
