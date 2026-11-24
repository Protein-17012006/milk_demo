"""The pure parts of scripts/check_display_series.py (synthetic data only; no AWS)."""

import importlib.util
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_display_series.py"
spec = importlib.util.spec_from_file_location("check_display_series", SCRIPT)
cds = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cds)

ICT = timezone(timedelta(hours=7))


def at(text):
    return cds.parse_local(text)


def item(cid, ts, key="k.jpg"):
    return {"capture_id": cid, "capture_timestamp": ts, "image_key": key}


def test_parse_local_reads_ict():
    assert at("2026-11-23T12:40") == datetime(2026, 11, 23, 12, 40, tzinfo=ICT)
    assert at("2026-11-23T12:40").timestamp() == datetime(2026, 11, 23, 5, 40, tzinfo=UTC).timestamp()


def test_parse_window():
    start, end = cds.parse_window("2026-11-23T20:50/2026-11-23T22:00")
    assert (start, end) == (at("2026-11-23T20:50"), at("2026-11-23T22:00"))


@pytest.mark.parametrize("bad", ["2026-11-23T20:50", "a/b", "2026-11-23T22:00/2026-11-23T20:50"])
def test_parse_window_rejects(bad):
    with pytest.raises(ValueError):
        cds.parse_window(bad)


def test_expectation_inclusive_start_exclusive_end():
    hidden = [cds.parse_window("2026-11-23T20:50/2026-11-23T22:00")]
    skip = [cds.parse_window("2026-11-23T20:40/2026-11-23T20:50")]
    assert cds.expectation(at("2026-11-23T20:50"), hidden, skip) == "hidden"
    assert cds.expectation(at("2026-11-23T21:59"), hidden, skip) == "hidden"
    assert cds.expectation(at("2026-11-23T22:00"), hidden, skip) == "visible"
    assert cds.expectation(at("2026-11-23T20:40"), hidden, skip) == "skip"
    assert cds.expectation(at("2026-11-23T20:49"), hidden, skip) == "skip"
    assert cds.expectation(at("2026-11-23T12:40"), hidden, skip) == "visible"


def test_pick_slots_first_with_image_per_slot_in_time_order():
    items = [
        item("C-3", "2026-11-23T12:12:00+07:00"),
        item("C-1", "2026-11-23T12:41:00+07:00", key=""),  # no frame: not a candidate
        item("C-2", "2026-11-23T12:43:00+07:00"),
        item("C-4", "2026-11-23T12:52:00+07:00"),
        item("C-5", "2026-11-23T12:55:00+07:00"),
        item("C-0", "2026-11-23T12:30:00+07:00"),  # before --from
        item("C-6", "2026-11-23T14:00:00+07:00"),  # at --to: excluded
    ]
    picked = cds.pick_slots(items, at("2026-11-23T12:40"), at("2026-11-23T14:00"), 10)
    assert [i["capture_id"] for i in picked] == ["C-2", "C-4"]


def test_pick_slots_orders_by_capture_id_within_slot():
    items = [item("C-b", "2026-11-23T12:48:00+07:00"), item("C-a", "2026-11-23T12:42:00+07:00")]
    picked = cds.pick_slots(items, at("2026-11-23T12:40"), at("2026-11-23T13:00"), 10)
    assert [i["capture_id"] for i in picked] == ["C-a"]


def test_verdict():
    assert cds.verdict("hidden", False) == "OK"
    assert cds.verdict("hidden", True) == "WRONG"
    assert cds.verdict("visible", True) == "OK"
    assert cds.verdict("visible", False) == "WRONG"
    assert cds.verdict("skip", True) == ""


def test_exit_code():
    assert cds.exit_code(["OK", "", "OK"]) == 0
    assert cds.exit_code(["OK", "WRONG"]) == 1
    assert cds.exit_code([]) == 0


def test_detections_from_json_string_and_list():
    raw = [{"sku_id": "a", "conf": 0.91, "box": [10, 20, 30, 40], "flagged": False}, {"conf": 0.5, "box": [1, 2, 3, 4]}]
    for value in (json.dumps(raw), raw):
        dets = cds.detections_from_json(value)
        assert len(dets) == 2
        assert dets[0].sku_id == "a" and dets[0].confidence == 0.91 and dets[0].box == (10, 20, 30, 40)
        assert dets[1].sku_id is None


def test_detections_from_json_missing():
    assert cds.detections_from_json(None) == []
    assert cds.detections_from_json("") == []


def test_format_line():
    line = cds.format_line(at("2026-11-23T20:50"), "CAP-1", 0.1234, False, "hidden")
    assert "2026-11-23 20:50" in line and "CAP-1" in line and "0.123" in line
    assert "NOT in view" in line and "expect not in view" in line and line.rstrip().endswith("OK")
    none = cds.format_line(at("2026-11-23T12:40"), "CAP-2", None, True, "skip")
    assert " - " in none and "in view" in none and "skip" in none and "WRONG" not in none
