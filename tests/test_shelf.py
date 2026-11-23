"""Shelf metrics (backend/shelf.py): 5-minute checks, opening hours, shelf state and rollups. Values worked out by hand."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from shelf import add_buckets, bucket_of, build_check, is_open, step_state, valid_hours  # noqa: E402


def cap(camera: str, ts: str, counts: dict[str, int], boxes: list[dict] | None = None) -> dict:
    """One item of the captures table: rows_json as ingest writes it (sku_id = product name), detections_json if boxes."""
    rows = [
        {
            "sku_id": name,
            "model_alias": "",
            "unit_count": n,
            "confidence_score": 0.9,
            "bounding_box": [[10 * k, 0, 8, 8] for k in range(n)],
        }
        for name, n in counts.items()
    ]
    return {
        "camera_id": camera,
        "capture_id": f"CAP-S01-{ts[:4]}{ts[5:7]}{ts[8:10]}-{ts[11:13]}{ts[14:16]}{ts[17:19]}",
        "capture_timestamp": ts,
        "rows_json": json.dumps(rows),
        "detections_json": json.dumps(boxes) if boxes is not None else None,
    }


# --- Task 1: checks and opening hours ---


def test_bucket_is_the_five_minutes_the_capture_falls_in():
    assert bucket_of("2026-11-23T14:07:31+07:00") == "20261123-1405"
    assert bucket_of("2026-11-23T14:10:00+07:00") == "20261123-1410"
    assert bucket_of("2026-11-23T07:02:00+00:00") == "20261123-1400"  # UTC in, ICT out


def test_add_buckets_crosses_midnight():
    assert add_buckets("20261123-2355", 1) == "20261124-0000"


def test_open_hours_include_open_and_exclude_close():
    assert is_open("20261123-0600", "06:00", "22:00") and is_open("20261123-2155", "06:00", "22:00")
    assert not is_open("20261123-0555", "06:00", "22:00") and not is_open("20261123-2200", "06:00", "22:00")
    assert not is_open("20261123-1200", None, None)


def test_valid_hours():
    assert valid_hours("06:00", "22:00") and valid_hours("00:00", "23:59")
    for bad in [("22:00", "06:00"), ("06:00", "06:00"), ("25:00", "26:00"), ("6:00", "22:00"), ("06:00", "")]:
        assert not valid_hours(*bad), bad


def test_check_counts_are_the_median_per_camera_summed_over_cameras():
    caps = [
        cap("CAM-A", "2026-11-23T14:05:10+07:00", {"Slide Cheese 145g": 3}),
        cap("CAM-A", "2026-11-23T14:06:10+07:00", {"Slide Cheese 145g": 5}),
        cap("CAM-A", "2026-11-23T14:07:10+07:00", {"Slide Cheese 145g": 4}),
        cap("CAM-B", "2026-11-23T14:06:30+07:00", {"Slide Cheese 145g": 2}),
    ]
    check = build_check("20261123-1405", caps)
    assert check["bucket"] == "20261123-1405"
    assert check["counts"] == {"Slide Cheese 145g": 6} and check["captures"] == 4
    assert check["cameras"] == ["CAM-A", "CAM-B"]


def test_a_sku_missing_from_a_capture_counts_zero_there():
    caps = [
        cap("CAM-A", "2026-11-23T14:05:10+07:00", {"X": 4}),
        cap("CAM-A", "2026-11-23T14:06:10+07:00", {}),
        cap("CAM-A", "2026-11-23T14:07:10+07:00", {}),
    ]
    assert build_check("20261123-1405", caps)["counts"] == {"X": 0}


def test_unrecognized_rows_are_left_out():
    item = cap("CAM-A", "2026-11-23T14:05:10+07:00", {})
    item["rows_json"] = json.dumps([{"sku_id": None, "unit_count": 3, "confidence_score": 0.1, "bounding_box": []}])
    assert build_check("20261123-1405", [item])["counts"] == {}


def test_confident_skus_need_one_box_at_070():
    boxes = [
        {"sku_id": "hot160", "conf": 0.69, "box": [0, 0, 5, 5]},
        {"sku_id": "cheese145", "conf": 0.70, "box": [9, 0, 5, 5]},
    ]
    caps = [cap("CAM-A", "2026-11-23T14:05:10+07:00", {"Slide Hot & Spicy 160g": 1, "Slide Cheese 145g": 1}, boxes)]
    assert build_check("20261123-1405", caps)["confident_skus"] == ["Slide Cheese 145g"]


# --- Task 2: shelf state ---


def walk(levels: list[int], state: dict | None = None) -> tuple[list[dict], dict]:
    """Step the shelf state through checks in a row from 20261123-1400; returns the events and the last state."""
    events = []
    bucket = "20261123-1400"
    for units in levels:
        state, event = step_state(state, units, bucket)
        if event is not None:
            events.append(event)
        bucket = add_buckets(bucket, 1)
    return events, state


def test_first_two_equal_checks_set_the_level_without_an_event():
    events, st = walk([3, 3])
    assert events == [] and (st["L"], st["status"]) == (3, "IN_STOCK")
    events, st = walk([0, 0])
    assert events == [] and (st["L"], st["status"]) == (0, "OOS")


def test_two_zero_checks_make_an_out_of_stock():
    events, _ = walk([5, 5, 0, 0])
    assert events == [
        {"type": "OOS", "at": "20261123-1410", "delta": -5, "level_before": 5, "level_after": 0, "duration_min": None}
    ]


def test_one_hidden_check_is_not_an_event():
    assert walk([5, 5, 0, 5, 5])[0] == []


def test_low_stock_wins_over_depleted():
    assert [(e["type"], e["delta"], e["level_after"]) for e in walk([8, 8, 2, 2])[0]] == [("LOW_STOCK", -6, 2)]


def test_depleted_needs_a_drop_of_three():
    events, st = walk([8, 8, 6, 6])
    assert events == [] and st["L"] == 6
    assert [(e["type"], e["delta"], e["level_after"]) for e in walk([12, 12, 8, 8])[0]] == [("DEPLETED", -4, 8)]


def test_restocked_needs_a_rise_of_two():
    events, st = walk([8, 8, 9, 9])
    assert events == [] and st["L"] == 9
    assert [(e["type"], e["delta"], e["level_after"]) for e in walk([8, 8, 24, 24])[0]] == [("RESTOCKED", 16, 24)]


def test_restock_after_out_of_stock_carries_its_open_minutes():
    events, _ = walk([5, 5, 0, 0, 0, 0, 6, 6])
    assert [(e["type"], e["at"], e["duration_min"]) for e in events] == [
        ("OOS", "20261123-1410", None),
        ("RESTOCKED", "20261123-1430", 20),
    ]
