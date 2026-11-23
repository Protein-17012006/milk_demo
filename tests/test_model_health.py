"""Hourly model health computed from the captures the backend keeps (spec section 6)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from model_health import capture_boxes, hour_stats  # noqa: E402

NEW = {"capture_timestamp": "2026-11-23T13:30:00+07:00", "units_found": 3, "processing_time_ms": 20,
       "latency_ms": 100, "model_version": "v3", "flagged_rows": 1,
       "rows_json": '[{"sku_id": "Slide Cheese 145g", "model_alias": "cheese145", "unit_count": 2, "confidence_score": 0.8, "bounding_box": [[0,0,10,10],[0,0,10,10]], "is_flagged": false}, {"sku_id": null, "model_alias": "", "unit_count": 1, "confidence_score": 0.3, "bounding_box": [[50,0,10,10]], "is_flagged": true}]',
       "detections_json": '[{"sku_id": "cheese145", "conf": 0.9, "box": [0,0,10,10]}, {"sku_id": "cheese145", "conf": 0.7, "box": [0,0,10,10]}, {"sku_id": null, "conf": 0.3, "box": [50,0,10,10]}]'}
OLD = {"capture_timestamp": "2026-11-23T13:30:10+07:00", "units_found": 1, "processing_time_ms": 40,
       "latency_ms": 200, "flagged_rows": 0,
       "rows_json": '[{"sku_id": "Slide Cheese 145g", "model_alias": "cheese145", "unit_count": 1, "confidence_score": 0.6, "bounding_box": [[0,0,10,10]], "is_flagged": false}]'}


def test_old_record_boxes_come_from_rows():
    assert capture_boxes(OLD) == [{"box_id": 1, "sku_id": "cheese145", "conf": 0.6, "box": [0, 0, 10, 10]}]


def test_new_record_boxes_keep_their_own_scores():
    assert [b["conf"] for b in capture_boxes(NEW)] == [0.9, 0.7, 0.3]
    assert [b["box_id"] for b in capture_boxes(NEW)] == [1, 2, 3]


def test_hour_stats():
    s = hour_stats([OLD, NEW])  # out of order on purpose
    assert s["captures"] == 2 and s["model_versions"] == ["unknown", "v3"]
    assert s["duplicate_pairs"] == 1  # the two cheese boxes of NEW
    assert s["unrecognized_box_pct"] == 0.25  # 1 of 4 boxes
    assert s["flagged_row_pct"] == 1 / 3  # 1 of 3 rows
    assert s["jitter"] == 2  # cheese 2 -> 1 (|1|) + unrecognized 1 -> 0 (|1|)
    assert (s["units_min"], s["units_max"]) == (1, 3)
    assert round(s["conf_median"], 4) == 0.65  # boxes 0.9, 0.7, 0.3, 0.6
    assert s["processing_ms_median"] == 30


def test_an_hour_without_captures():
    assert hour_stats([]) == {"captures": 0}
