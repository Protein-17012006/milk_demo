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
    capture_position,
    change_pct,
    expected_at,
    far_apart,
    gap_between,
    in_view,
    is_open,
    merge,
    move_skus,
    open_buckets,
    products_position,
    rollup,
    see_skus,
    sees_shelf,
    step_arrangements,
    step_state,
    totals,
    valid_hours,
    view_of,
)

TS = "2026-11-21T14:00:10+07:00"
PHANTOM = {"sku_id": "cheese145", "conf": 0.5, "box": [0, 0, 8, 8]}  # a night phantom: low confidence


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


def _sku(checks=0, available=0, units_sum=0, oos_started=0, restock_units=0, restock_events=0, unseen_checks=0) -> dict:
    return {
        "checks": checks,
        "available": available,
        "units_sum": units_sum,
        "oos_started": oos_started,
        "restock_units": restock_units,
        "restock_events": restock_events,
        "unseen_checks": unseen_checks,
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
        cap("CAM-A", "2026-11-23T14:06:10+07:00", {}, boxes=[PHANTOM], visible=False),
        cap("CAM-A", "2026-11-23T14:07:10+07:00", {"X": 4}),
    ]
    c = build_check("20261123-1405", caps)
    assert (c["counts"], c["captures_visible"], c["measurable"]) == ({"X": 4}, 2, True)


def test_a_check_mostly_without_the_display_is_not_measurable():
    caps = [cap("CAM-A", f"2026-11-23T14:0{m}:10+07:00", {}, boxes=[PHANTOM], visible=m == 5) for m in (5, 6, 7)]
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
    hidden = build_check(
        "20261123-1405", [cap("CAM-A", "2026-11-23T14:05:10+07:00", {"X": 3}, boxes=[PHANTOM], visible=False)]
    )
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


def test_open_buckets_counts_five_minute_checks_inside_the_hours():
    assert open_buckets("08:00", "20:30", "20261123-0000", "20261123-2355") == 150
    assert open_buckets("08:00", "20:30", "20261123-0800", "20261123-0810") == 3
    assert open_buckets(None, None, "20261123-0000", "20261123-2355") == 0
    assert open_buckets("08:00", "20:30", "20261123-0000", "20261124-2355") == 300  # two days
    assert open_buckets("08:00", "20:30", "20261124-0000", "20261123-2355") == 0  # last before first


# --- 2026-11-26: a SKU counts as expected only once the system knows of it ---

TH = "TH true MILK 180ml"


def seen(bucket: str, counts: dict | None = None, sure: tuple = (), measurable: bool = True) -> dict:
    return {"bucket": bucket, "counts": counts or {}, "confident_skus": list(sure), "measurable": measurable}


def test_a_sku_is_not_expected_before_its_first_sure_count():
    since: dict[str, str] = {}
    assert expected_at(seen("20261126-1525"), [TH], since, {}) == []
    assert expected_at(seen("20261126-1530", {TH: 7}, (TH,)), [TH], since, {}) == [TH]
    assert since == {TH: "20261126-1530"}


def test_a_started_sku_stays_expected_when_the_shelf_is_empty():
    since = {TH: "20261126-1530"}
    assert expected_at(seen("20261126-1545"), [TH], since, {}) == [TH]
    assert since == {TH: "20261126-1530"}


def test_a_sku_is_expected_from_the_check_where_it_joined_the_plan():
    since: dict[str, str] = {}
    joined = {TH: "20261126-1530"}
    assert expected_at(seen("20261126-1525"), [TH], since, joined) == []
    assert expected_at(seen("20261126-1530"), [TH], since, joined) == [TH]
    assert since == {TH: "20261126-1530"}


def test_a_first_count_before_joining_the_plan_starts_the_sku_earlier():
    since: dict[str, str] = {}
    assert expected_at(seen("20261122-2150", {TH: 2}, (TH,)), [TH], since, {TH: "20261124-0900"}) == [TH]
    assert since == {TH: "20261122-2150"}


def test_an_unsure_reading_does_not_start_a_sku():
    since: dict[str, str] = {}
    assert expected_at(seen("20261123-1315", {TH: 1}), [TH], since, {}) == []
    assert since == {}


def test_a_check_without_the_display_does_not_start_a_sku_by_its_counts():
    since: dict[str, str] = {}
    assert expected_at(seen("20261126-1530", {TH: 7}, (TH,), measurable=False), [TH], since, {}) == []


def test_only_plan_skus_are_expected_and_in_name_order():
    since = {"B": "20261122-0600", "A": "20261122-0600", "C": "20261122-0600"}
    assert expected_at(seen("20261126-1530"), ["B", "A"], since, {}) == ["A", "B"]


def test_a_check_keeps_the_boxes_of_the_frame_it_shows():
    cheese = "Slide Cheese 145g"
    framed = cap(
        "CAM-A", "2026-11-21T14:00:10+07:00", {cheese: 2, "Slide Hot & Spicy 160g": 1}, image_key="frames/a.jpg"
    )
    later = cap("CAM-A", "2026-11-21T14:01:30+07:00", {cheese: 3})
    check = build_check("20261121-1400", [later, framed])
    assert check["image_key"] == "frames/a.jpg"
    assert check["frame_boxes"] == {cheese: [[0, 0, 8, 8], [10, 0, 8, 8]], "Slide Hot & Spicy 160g": [[0, 0, 8, 8]]}
    assert build_check("20261121-1400", [later])["frame_boxes"] == {}  # no frame, so no boxes of it


# --- Shelf not in view: seeing the shelf ---


def _sure(k: int, cx: int, cy: int, sku: str = "cheese145") -> list[dict]:
    """k sure boxes (conf 0.9) all centred on (cx, cy)."""
    return [{"sku_id": sku, "conf": 0.9, "box": [cx - 5, cy - 5, 10, 10]} for _ in range(k)]


def test_a_capture_away_from_the_zone_sees_the_shelf_by_three_sure_boxes():
    sure = [{"sku_id": "cheese145", "conf": 0.9, "box": [100 * k, 0, 10, 10]} for k in range(3)]
    assert sees_shelf(cap("CAM-S01-A", TS, {}, boxes=sure, visible=False))
    assert not sees_shelf(cap("CAM-S01-A", TS, {}, boxes=sure[:2], visible=False))
    assert not sees_shelf(cap("CAM-S01-A", TS, {}, boxes=[{**b, "conf": 0.79} for b in sure], visible=False))
    assert not sees_shelf(cap("CAM-S01-A", TS, {}, boxes=[{**b, "sku_id": None} for b in sure], visible=False))


def test_a_capture_the_zone_check_passes_sees_the_shelf_without_boxes():
    assert sees_shelf(cap("CAM-S01-A", TS, {}, boxes=[], visible=True))
    assert sees_shelf(cap("CAM-S01-A", TS, {}))  # older than the display check


def test_capture_position_is_the_median_centre_of_its_sure_boxes():
    boxes = [
        {"sku_id": "cheese145", "conf": 0.9, "box": [0, 0, 10, 10]},
        {"sku_id": "hot160", "conf": 0.9, "box": [100, 0, 10, 10]},
        {"sku_id": "hot160", "conf": 0.95, "box": [200, 40, 10, 10]},
        {"sku_id": "hot160", "conf": 0.5, "box": [2000, 2000, 10, 10]},  # not sure: left out
    ]
    assert capture_position(cap("CAM-S01-A", TS, {}, boxes=boxes, visible=False)) == [105, 5]
    assert capture_position(cap("CAM-S01-A", TS, {}, boxes=boxes[:2], visible=False)) is None


def test_products_position_is_the_median_of_the_captures_positions():
    # three captures centred near (100, 10), (110, 12) and (400, 50), and one without a position
    caps = [
        cap("CAM-S01-A", TS, {}, boxes=_sure(3, 100, 10), visible=False),
        cap("CAM-S01-A", TS, {}, boxes=_sure(3, 110, 12), visible=False),
        cap("CAM-S01-A", TS, {}, boxes=_sure(3, 400, 50), visible=False),
        cap("CAM-S01-A", TS, {}, boxes=[PHANTOM], visible=False),
    ]
    assert products_position(caps) == [110, 12]
    assert products_position([cap("CAM-S01-A", TS, {}, visible=False)]) is None


def test_far_apart_means_more_than_500_px():
    assert not far_apart([0, 0], [300, 400])  # exactly 500
    assert far_apart([0, 0], [300, 401])
    assert far_apart([1068, 246], [290, 412])  # 28/11 12:10 -> 12:15
    assert not far_apart([820, 148], [934, 527])  # 27/11 12:05, 399 px


def test_a_check_counts_captures_that_see_products_away_from_the_zone():
    cheese = "Slide Cheese 145g"
    caps = [
        cap("CAM-S01-A", TS, {cheese: 5}, visible=False),
        cap("CAM-S01-A", "2026-11-21T14:01:10+07:00", {cheese: 5}, visible=False),
    ]
    check = build_check("20261121-1400", caps)
    assert (check["counts"], check["captures_visible"], check["measurable"]) == ({cheese: 5}, 2, True)


def test_a_check_keeps_positions_confident_products_by_camera_and_zone_captures():
    cheese = "Slide Cheese 145g"
    in_zone = cap("CAM-S01-A", TS, {}, boxes=_sure(3, 1000, 300), visible=True)
    away = cap("CAM-S01-A", "2026-11-21T14:01:10+07:00", {}, boxes=_sure(3, 1000, 300), visible=False)
    other = cap("CAM-S01-B", "2026-11-21T14:02:10+07:00", {}, boxes=[PHANTOM], visible=True)
    check = build_check("20261121-1400", [in_zone, away, other])
    assert check["positions"] == {"CAM-S01-A": [1000, 300]}
    assert "CAM-S01-B" not in check["positions"]
    assert check["confident_by_camera"]["CAM-S01-A"] == [cheese]
    assert check["confident_by_camera"].get("CAM-S01-B", []) == []
    assert check["confident_skus"] == [cheese]
    assert check["captures_zone"] == 2  # the in-zone capture and camera B's (visible=True)


# --- Shelf not in view: arrangements and products not in view ---

CAM_A, CAM_B = "CAM-S01-A", "CAM-S01-B"


def _moved_check(counts: dict, sure_a: list[str], sure_b: list[str] | None = None) -> dict:
    by_camera = {CAM_A: sorted(sure_a)}
    if sure_b is not None:
        by_camera[CAM_B] = sorted(sure_b)
    return {"bucket": "20261128-1215", "counts": counts, "confident_by_camera": by_camera}


def test_the_first_position_of_a_camera_starts_its_arrangement():
    arrangements = {}
    check = {"bucket": "20261128-1000", "positions": {CAM_A: [1000, 250]}}
    assert step_arrangements(arrangements, check) == []
    assert arrangements == {CAM_A: {"position": [1000, 250], "since": "20261128-1000"}}


def test_a_jump_of_more_than_500_px_is_a_new_arrangement():
    arrangements = {CAM_A: {"position": [1068, 246], "since": "20261128-0625"}}
    check = {"bucket": "20261128-1215", "positions": {CAM_A: [290, 412]}}
    assert step_arrangements(arrangements, check) == [CAM_A]
    assert arrangements[CAM_A] == {"position": [290, 412], "since": "20261128-1215"}


def test_a_person_in_front_or_a_slow_drift_is_the_same_arrangement():
    arrangements = {CAM_A: {"position": [1000, 250], "since": "20261128-0625"}}
    for pos in ([1180, 250], [820, 148], [934, 527], [1150, 283]):  # up to 399 px from the previous position
        assert step_arrangements(arrangements, {"bucket": "20261128-1300", "positions": {CAM_A: pos}}) == []
    assert arrangements[CAM_A] == {"position": [1150, 283], "since": "20261128-0625"}


def test_a_check_without_a_position_changes_no_arrangement():
    arrangements = {CAM_A: {"position": [1000, 250], "since": "20261128-0625"}}
    assert step_arrangements(arrangements, {"bucket": "20261128-1300", "positions": {}}) == []
    assert arrangements == {CAM_A: {"position": [1000, 250], "since": "20261128-0625"}}


def test_a_move_puts_products_not_seen_out_of_view_with_what_was_seen_last():
    state = {
        "TH": {"L": 6, "status": "IN_STOCK", "prev": 6, "prev_bucket": "20261128-1210", "camera": CAM_A},
        "Cheese": {"L": 4, "status": "IN_STOCK", "prev": 4, "prev_bucket": "20261128-1210", "camera": CAM_A},
        "Hot": {"L": 3, "status": "LOW", "prev": 3, "prev_bucket": "20261128-1210", "camera": CAM_B},
    }
    hot_before = dict(state["Hot"])
    move_skus(state, [CAM_A], _moved_check({"Cheese": 5}, ["Cheese"], ["Hot"]))
    assert state["TH"] == {
        "in_view": False,
        "not_in_view_since": "20261128-1215",
        "last_seen_units": 6,
        "last_seen_at": "20261128-1210",
        "camera": CAM_A,
    }
    assert state["Cheese"] == {"in_view": True, "camera": CAM_A}  # its level is gone: it starts again
    assert state["Hot"] == hot_before


def test_a_product_with_no_camera_yet_moves_with_the_cameras():
    state = {"TH": {"L": None, "prev": 2, "prev_bucket": "20261128-1210"}}
    move_skus(state, [CAM_A], _moved_check({}, []))
    assert state["TH"]["in_view"] is False and state["TH"]["last_seen_units"] == 2  # no level yet: the last units


def test_a_product_already_out_of_view_keeps_when_it_was_last_seen():
    state = {"TH": {"L": 6, "prev": 6, "prev_bucket": "20261128-1210", "camera": CAM_A}}
    move_skus(state, [CAM_A], _moved_check({}, []))
    first = dict(state["TH"])
    second = _moved_check({}, [])
    second["bucket"] = "20261128-1500"
    move_skus(state, [CAM_A], second)
    assert state["TH"] == first
    assert (first["not_in_view_since"], first["last_seen_units"], first["last_seen_at"]) == (
        "20261128-1215",
        6,
        "20261128-1210",
    )


def test_a_product_out_of_stock_before_a_move_keeps_zero_as_last_seen():
    state = {
        "TH": {
            "L": 0,
            "status": "OOS",
            "since": "20261128-1100",
            "prev": 0,
            "prev_bucket": "20261128-1210",
            "camera": CAM_A,
        }
    }
    move_skus(state, [CAM_A], _moved_check({}, []))
    assert state["TH"]["last_seen_units"] == 0 and state["TH"]["in_view"] is False
    assert "status" not in state["TH"]


def test_a_product_seen_again_starts_fresh_and_in_view():
    state = {
        "TH": {
            "in_view": False,
            "not_in_view_since": "20261128-1215",
            "last_seen_units": 6,
            "last_seen_at": "20261128-1210",
            "camera": CAM_A,
        }
    }
    check = {"bucket": "20261128-1230", "counts": {"TH": 4}, "confident_by_camera": {CAM_A: ["TH"]}}
    see_skus(state, check, ["TH"])
    assert state["TH"] == {"in_view": True, "camera": CAM_A}
    s, event = step_state(state["TH"], 4, "20261128-1230")
    s, event2 = step_state(s, 4, "20261128-1235")
    assert s["L"] == 4 and event is None and event2 is None


def test_see_skus_names_the_camera_that_counted_a_product_surely():
    state = {"Cheese": {"L": 4, "camera": CAM_B}, "Hot": {"in_view": False, "camera": CAM_B}}
    check = {
        "bucket": "20261128-1230",
        "counts": {"Cheese": 5, "Hot": 2, "Plain": 3, "Other": 1},
        "confident_by_camera": {CAM_B: ["Cheese", "Hot", "Plain"], CAM_A: ["Cheese", "Other"]},
    }
    see_skus(state, check, ["Cheese", "Hot", "Plain"])  # Other is not expected
    assert state["Cheese"] == {"L": 4, "camera": CAM_A}  # the first camera in name order that saw it surely
    assert state["Hot"] == {"in_view": True, "camera": CAM_B}
    assert state["Plain"] == {"camera": CAM_B}
    assert "Other" not in state


def test_see_skus_ignores_a_product_counted_zero():
    state = {}
    check = {"bucket": "20261128-1230", "counts": {"Cheese": 0}, "confident_by_camera": {CAM_A: ["Cheese"]}}
    see_skus(state, check, ["Cheese"])
    assert state == {}


def test_in_view_and_view_of():
    assert in_view(None) and in_view({}) and in_view({"in_view": True})
    assert not in_view({"in_view": False})
    off = {
        "in_view": False,
        "not_in_view_since": "20261128-1215",
        "last_seen_units": 6,
        "last_seen_at": "20261128-1210",
    }
    assert view_of(off) == {"since": "20261128-1215", "last_units": 6, "last_at": "20261128-1210"}
    assert view_of({"in_view": True}) is None


def test_a_product_not_in_view_is_left_out_of_the_hours_numbers():
    check = {
        "bucket": "20261128-1300",
        "counts": {"Cheese": 5},
        "open": True,
        "expected": ["Cheese", "TH"],
        "not_in_view": ["TH"],
        "confident_skus": [],
    }
    r = rollup([check], [])
    assert r["skus"]["Cheese"] == _sku(checks=1, available=1, units_sum=5)
    assert r["skus"]["TH"] == _sku(unseen_checks=1)
    assert r["max_total"] == 5 and r["checks"] == 1
    assert merge([r, r])["skus"]["TH"]["unseen_checks"] == 2
