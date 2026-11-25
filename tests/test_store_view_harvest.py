"""Gathering store frames for training (training/store_view/harvest.py): one manifest row per capture."""

from decimal import Decimal

from training.store_view.harvest import capture_prefix, frame_relpath, merge_rows, rows_from_audits, rows_from_captures

HUB = "milk-demo-base-databucket-test"
ANALYTICS = "milk-backend-development-test"


def capture(capture_id, ts, **extra):
    item = {
        "camera_id": "CAM-S01-A",
        "capture_id": capture_id,
        "capture_timestamp": ts,
        "image_key": f"frames/CAM-S01-A/{ts[:10]}/{capture_id}.jpg",
        "source_bucket": HUB,
        "detections_json": '[{"sku_id": "cheese145", "conf": 0.9, "box": [10, 20, 30, 40]}]',
    }
    item.update(extra)
    return item


def audit(audit_id, capture_id, ts):
    return {
        "audit_id": audit_id,
        "camera_id": "CAM-S01-A",
        "capture_id": capture_id,
        "capture_timestamp": ts,
        "image_key": f"audits/frames/CAM-S01-A/{ts[:10]}/{capture_id}.jpg",
        "display_visible": True,
        "ai_boxes_json": '[{"box_id": 1, "sku_id": "hot160", "conf": 0.5, "box": [1, 2, 3, 4]}]',
    }


def test_frame_relpath_uses_the_ict_day():
    # 05:00 in Vietnam is still the day before in UTC: the folder must follow the store's own day
    assert frame_relpath("CAP-S01-20261125-050000", "2026-11-25T05:00:00+07:00") == (
        "2026-11-25/CAP-S01-20261125-050000.jpg"
    )


def test_capture_prefix_follows_the_store_of_the_camera():
    assert capture_prefix("CAM-S01-A") == "CAP-S01-"
    assert capture_prefix("CAM-S02-B") == "CAP-S02-"


def test_captures_without_a_frame_are_left_out():
    rows = rows_from_captures([capture("CAP-S01-20261124-120000", "2026-11-24T12:00:00+07:00", image_key="")])
    assert rows == []


def test_capture_rows_carry_what_training_needs():
    item = capture(
        "CAP-S01-20261124-120000", "2026-11-24T12:00:00+07:00", display_visible=False, display_score=Decimal("0.42")
    )
    (row,) = rows_from_captures([item])
    assert row["capture_id"] == "CAP-S01-20261124-120000"
    assert (row["bucket"], row["image_key"]) == (HUB, "frames/CAM-S01-A/2026-11-24/CAP-S01-20261124-120000.jpg")
    assert row["display_visible"] is False and row["display_score"] == 0.42
    assert row["boxes"] == [{"sku_id": "cheese145", "conf": 0.9, "box": [10, 20, 30, 40]}]
    assert row["audit_ids"] == [] and row["path"] == "2026-11-24/CAP-S01-20261124-120000.jpg"


def test_missing_display_fields_mean_the_display_was_seen():
    # captures from before the display check (24/11 19:03) carry no display_visible: they saw the display
    (row,) = rows_from_captures([capture("CAP-S01-20261123-120000", "2026-11-23T12:00:00+07:00")])
    assert row["display_visible"] is True and row["display_score"] is None


def test_merge_keeps_one_row_per_capture_and_lists_its_audits():
    ts = "2026-11-24T12:00:13+07:00"
    hub = rows_from_captures([capture("CAP-S01-20261124-120013-4", ts)])
    audits = rows_from_audits(
        [
            audit("AUD-CAM-S01-A-20261124-12", "CAP-S01-20261124-120013-4", ts),
            audit("TRN-CAM-S01-A-20261124-12", "CAP-S01-20261124-120013-4", ts),
        ],
        ANALYTICS,
    )
    (row,) = merge_rows(hub, audits)
    assert row["bucket"] == HUB
    assert row["audit_ids"] == ["AUD-CAM-S01-A-20261124-12", "TRN-CAM-S01-A-20261124-12"]


def test_an_audit_frame_whose_hub_copy_expired_is_kept():
    ts = "2026-11-23T12:49:00+07:00"
    audits = rows_from_audits([audit("AUD-CAM-S01-A-20261123-12", "CAP-S01-20261123-124900", ts)], ANALYTICS)
    (row,) = merge_rows([], audits)
    assert (row["bucket"], row["image_key"]) == (
        ANALYTICS,
        "audits/frames/CAM-S01-A/2026-11-23/CAP-S01-20261123-124900.jpg",
    )
    assert row["audit_ids"] == ["AUD-CAM-S01-A-20261123-12"]
    assert row["boxes"] == [{"box_id": 1, "sku_id": "hot160", "conf": 0.5, "box": [1, 2, 3, 4]}]


def test_merged_rows_come_out_in_time_order():
    later = capture("CAP-S01-20261124-130000", "2026-11-24T13:00:00+07:00")
    earlier = capture("CAP-S01-20261124-120000", "2026-11-24T12:00:00+07:00")
    rows = merge_rows(rows_from_captures([later, earlier]), [])
    assert [r["capture_id"] for r in rows] == ["CAP-S01-20261124-120000", "CAP-S01-20261124-130000"]
