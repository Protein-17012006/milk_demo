"""Shelf metrics (backend/shelf.py): 5-minute checks, opening hours, shelf state and rollups. Values worked out by hand."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from shelf import (  # noqa: E402
    add_buckets,
    bucket_of,
    build_check,
    change_pct,
    gap_between,
    is_open,
    merge,
    rollup,
    step_state,
    totals,
    valid_hours,
)


def cap(
    camera: str,
    ts: str,
    counts: dict[str, int],
    boxes: list[dict] | None = None,
    visible: bool | None = None,
    image_key: str = "",
) -> dict:
    """One item of the captures table: rows_json as ingest writes it (sku_id = product name), detections_json if boxes.
    visible sets display_visible (None leaves it out, as for captures from before the display check); image_key is
    "" for a capture without a frame, as ingest writes it."""
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
    item = {
        "camera_id": camera,
        "capture_id": f"CAP-S01-{ts[:4]}{ts[5:7]}{ts[8:10]}-{ts[11:13]}{ts[14:16]}{ts[17:19]}",
        "capture_timestamp": ts,
        "image_key": image_key,
        "rows_json": json.dumps(rows),
        "detections_json": json.dumps(boxes) if boxes is not None else None,
    }
    if visible is not None:
        item["display_visible"] = visible
    return item


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


# --- Task 3: rollups and period totals ---


def _sku(checks=0, available=0, units_sum=0, oos_started=0, restock_units=0, restock_events=0) -> dict:
    return {
        "checks": checks,
        "available": available,
        "units_sum": units_sum,
        "oos_started": oos_started,
        "restock_units": restock_units,
        "restock_events": restock_events,
    }


def test_only_open_checks_of_expected_skus_count():
    open_c = {
        "bucket": "20261123-1400",
        "counts": {"A": 3, "C": 9},
        "open": True,
        "expected": ["A", "B"],
        "confident_skus": [],
    }
    shut_c = {
        "bucket": "20261123-1405",
        "counts": {"A": 5},
        "open": False,
        "expected": ["A", "B"],
        "confident_skus": ["C"],
    }
    r = rollup([open_c, shut_c], [])
    assert r["checks"] == 1 and r["max_total"] == 3 and r["confident_skus"] == ["C"]
    assert r["skus"]["A"] == _sku(checks=1, available=1, units_sum=3)
    assert r["skus"]["B"] == _sku(checks=1)  # in the list but not seen: a check without stock
    assert "C" not in r["skus"]


def test_events_feed_out_of_stock_and_restock_numbers():
    ev = [
        {"sku_id": "A", "type": "OOS", "delta": -5},
        {"sku_id": "A", "type": "RESTOCKED", "delta": 6},
        {"sku_id": "B", "type": "RESTOCKED", "delta": 2},
    ]
    r = rollup([], ev)
    assert r["skus"]["A"] == _sku(oos_started=1, restock_units=6, restock_events=1)
    assert r["skus"]["B"] == _sku(restock_units=2, restock_events=1)


def test_merge_adds_hours_into_a_day():
    h1 = {"checks": 12, "max_total": 9, "confident_skus": ["A"], "skus": {"A": _sku(12, 10, 40)}}
    h2 = {"checks": 10, "max_total": 14, "confident_skus": ["B"], "skus": {"A": _sku(10, 10, 50, 0, 6, 1)}}
    day = merge([h1, h2])
    assert (day["checks"], day["max_total"], day["confident_skus"]) == (22, 14, ["A", "B"])
    assert day["skus"]["A"] == _sku(22, 20, 90, 0, 6, 1)


def test_osa_is_available_over_counted_checks_and_filters_by_sku():
    r = {"checks": 2, "max_total": 7, "confident_skus": [], "skus": {"A": _sku(2, 2, 7), "B": _sku(2, 1, 1, 1)}}
    t = totals([r])
    assert (t["osa"], t["avg_total_units"], t["store_checks"], t["oos_started"]) == (0.75, 4.0, 2, 1)
    assert totals([r], {"B"})["osa"] == 0.5
    assert totals([])["osa"] is None and totals([])["avg_total_units"] is None


def test_change_pct():
    assert change_pct(13.4, 10.0) == 34.0
    assert change_pct(5, 0) is None and change_pct(5, None) is None and change_pct(None, 5) is None


# --- Reliability: checks without the display are not measured, gaps between measured checks ---


def test_a_check_counts_only_captures_that_see_the_display():
    caps = [
        cap("CAM-A", "2026-11-23T14:05:10+07:00", {"X": 4}),
        cap("CAM-A", "2026-11-23T14:06:10+07:00", {}, visible=False),
        cap("CAM-A", "2026-11-23T14:07:10+07:00", {"X": 4}),
    ]
    c = build_check("20261123-1405", caps)
    assert (c["counts"], c["captures_visible"], c["measurable"]) == ({"X": 4}, 2, True)


def test_a_check_mostly_without_the_display_is_not_measurable():
    caps = [cap("CAM-A", f"2026-11-23T14:0{m}:10+07:00", {}, visible=m == 5) for m in (5, 6, 7)]
    assert build_check("20261123-1405", caps)["measurable"] is False


def test_old_captures_without_the_field_see_the_display():
    assert build_check("20261123-1405", [cap("CAM-A", "2026-11-23T14:05:10+07:00", {"X": 1})])["measurable"]


def test_a_check_keeps_one_frame_for_event_photos():
    caps = [
        cap("CAM-A", "2026-11-23T14:06:10+07:00", {"X": 1}, image_key="frames/b.jpg"),
        cap("CAM-A", "2026-11-23T14:05:10+07:00", {"X": 1}, visible=False, image_key="frames/a.jpg"),
    ]
    assert build_check("20261123-1405", caps)["image_key"] == "frames/b.jpg"


def test_a_check_without_the_display_says_why():
    hidden = build_check("20261123-1405", [cap("CAM-A", "2026-11-23T14:05:10+07:00", {"X": 3}, visible=False)])
    assert (hidden["counts"], hidden["unmeasured_reason"]) == ({}, "display_not_visible")
    assert "unmeasured_reason" not in build_check("20261123-1405", [cap("CAM-A", "2026-11-23T14:05:10+07:00", {})])


def test_gap_between():
    assert gap_between("20261123-1400", "20261123-1430") is None
    assert gap_between("20261123-1400", "20261123-1435") == ("20261123-1400", "20261123-1435")
    assert gap_between(None, "20261123-1435") is None


def test_an_event_right_after_a_gap_says_so():
    st, events = None, []
    for bucket, units, gap in [
        ("20261123-2020", 5, None),
        ("20261123-2025", 5, None),
        ("20261124-0845", 0, ("20261123-2025", "20261124-0845")),
        ("20261124-0850", 0, None),
    ]:
        st, e = step_state(st, units, bucket, gap)
        events += [e] if e else []
    assert events == [
        {
            "type": "OOS",
            "at": "20261124-0845",
            "delta": -5,
            "level_before": 5,
            "level_after": 0,
            "duration_min": None,
            "after_gap": True,
            "gap_from": "20261123-2025",
            "gap_to": "20261124-0845",
        }
    ]


def test_a_state_stored_without_its_empty_fields_still_steps():
    # DynamoDB keeps no None: a state read back has no L, status, since or prev_gap until they are set
    st, event = step_state({"prev": 5, "prev_bucket": "20261123-1400", "oos_checks": 0}, 5, "20261123-1405")
    assert event is None and (st["L"], st["status"], st["since"]) == (5, "IN_STOCK", "20261123-1400")


def test_unmeasured_open_checks_are_counted_apart():
    c = {
        "bucket": "20261123-1400",
        "counts": {"A": 0},
        "open": True,
        "measurable": False,
        "expected": ["A"],
        "confident_skus": [],
    }
    r = rollup([c], [])
    assert (r["checks"], r["unmeasured_checks"], "A" in r["skus"]) == (0, 1, False)
    assert totals([r])["unmeasured_checks"] == 1
