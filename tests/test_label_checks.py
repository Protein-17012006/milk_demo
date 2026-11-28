"""Answer keys and check sheets (operations-loop design 5.4): when a labeller is due a check, which key suits whom."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from label_checks import (  # noqa: E402
    CHECK_EVERY,
    can_be_key,
    due,
    eligible_keys,
    is_sheet,
    newest_key,
    sheet_for,
    without_key,
)

A, B, ADMIN = "a@team.vn", "b@client.vn", "admin@team.vn"


def frame(hour: int, by: str, **extra) -> dict:
    return {
        "store_id": "DEMO-S01",
        "audit_id": f"TRN-CAM-S01-A-20261128-{hour:02d}",
        "status": "done",
        "purpose": "training",
        "labeled_by": by,
        "labeled_at": f"2026-11-28T{hour:02d}:30:00+07:00",
        **extra,
    }


def sheet(token: str, of: str, to: str, status: str, sampled_hour: int) -> dict:
    return {
        "store_id": "DEMO-S01",
        "audit_id": f"CHK-{token}",
        "check_of": of,
        "assigned_to": to,
        "status": status,
        "sampled_at": f"2026-11-28T{sampled_hour:02d}:45:00+07:00",
        **({"labeled_by": to, "labeled_at": f"2026-11-28T{sampled_hour:02d}:50:00+07:00"} if status == "done" else {}),
    }


def key(hour: int, by: str = ADMIN, marked_by: str = ADMIN) -> dict:
    return frame(hour, by, answer_key=True, answer_key_by=marked_by)


def test_one_frame_in_ten_is_a_check():
    assert CHECK_EVERY == 10


def test_a_check_is_due_after_nine_frames():
    assert not due([frame(h, A) for h in range(8)], A)
    assert due([frame(h, A) for h in range(9)], A)


def test_other_peoples_frames_and_unfinished_frames_do_not_count():
    audits = [frame(h, B) for h in range(9)] + [frame(h, A, status="pending") for h in range(9, 18)]
    assert not due(audits, A)


def test_no_second_check_while_one_waits():
    audits = [frame(h, A) for h in range(9)] + [sheet("11111111", "TRN-CAM-S01-A-20261127-10", A, "pending", 0)]
    assert not due(audits, A)
    assert due(audits, B) is False  # and someone else's waiting sheet is not mine either way


def test_the_count_starts_again_after_a_sheet():
    done_sheet = sheet("11111111", "TRN-CAM-S01-A-20261127-10", A, "done", 8)
    before = [frame(h, A) for h in range(9)]
    assert not due(before + [done_sheet] + [frame(h, A) for h in range(10, 13)], A)
    assert due(before + [done_sheet] + [frame(h, A) for h in range(10, 19)], A)


def test_a_sheet_i_answered_is_not_one_of_my_nine_frames():
    audits = [frame(h, A) for h in range(8)] + [sheet("11111111", "TRN-CAM-S01-A-20261127-10", A, "done", 0)]
    assert not due(audits, A)


def test_a_key_i_labelled_or_marked_is_not_for_me():
    audits = [key(1, by=A), key(2, marked_by=A), key(3)]
    assert [k["audit_id"] for k in eligible_keys(audits, A)] == ["TRN-CAM-S01-A-20261128-03"]


def test_a_key_i_was_checked_on_is_not_given_again():
    audits = [key(3), key(4), sheet("11111111", "TRN-CAM-S01-A-20261128-03", A, "done", 5)]
    assert [k["audit_id"] for k in eligible_keys(audits, A)] == ["TRN-CAM-S01-A-20261128-04"]
    assert len(eligible_keys(audits, B)) == 2


def test_a_frame_that_is_not_marked_is_no_key():
    assert eligible_keys([frame(1, ADMIN)], A) == []


def test_what_can_be_an_answer_key():
    assert can_be_key(frame(1, ADMIN)) is None
    assert can_be_key(frame(1, ADMIN, status="pending")) == "Only a labelled frame can be an answer key."
    assert (
        can_be_key(frame(1, ADMIN, candidate_version="v-next"))
        == "A frame that shows two versions cannot be an answer key."
    )
    assert can_be_key(sheet("11111111", "x", A, "done", 1)) == "This frame cannot be an answer key."


def test_a_sheet_copies_the_frame_and_starts_blank():
    source = {
        **key(3),
        "camera_id": "CAM-S01-A",
        "capture_id": "CAP-S01-20261128-030010",
        "capture_timestamp": "2026-11-28T03:00:10+07:00",
        "image_key": "audits/frames/CAM-S01-A/2026-11-28/f.jpg",
        "model_version": "v3",
        "pipeline": "long",
        "display_visible": True,
        "ai_boxes_json": '[{"box_id":1,"sku_id":"hot160","box":[1,2,3,4]}]',
        "verdicts_json": '[{"box_id":1,"verdict":"correct"}]',
        "missed_json": '[{"sku_id":"hot160","x":9,"y":9}]',
        "key_verdicts_json": '[{"box_id":1,"verdict":"correct"}]',
        "key_missed_json": "[]",
    }
    made = sheet_for(source, A, "2026-11-28T12:00:00+07:00", "0a1b2c3d")
    assert made == {
        "store_id": "DEMO-S01",
        "audit_id": "CHK-0a1b2c3d",
        "check_of": "TRN-CAM-S01-A-20261128-03",
        "assigned_to": A,
        "status": "pending",
        "sampled_at": "2026-11-28T12:00:00+07:00",
        "purpose": "training",
        "camera_id": "CAM-S01-A",
        "capture_id": "CAP-S01-20261128-030010",
        "capture_timestamp": "2026-11-28T03:00:10+07:00",
        "image_key": "audits/frames/CAM-S01-A/2026-11-28/f.jpg",
        "model_version": "v3",
        "pipeline": "long",
        "display_visible": True,
        "ai_boxes_json": '[{"box_id":1,"sku_id":"hot160","box":[1,2,3,4]}]',
        "verdicts_json": "[]",
        "missed_json": "[]",
    }
    assert is_sheet(made) and not is_sheet(source)


def test_a_sheet_of_an_old_frame_shows_the_purpose_its_id_stands_for():
    old_scoring = {"store_id": "DEMO-S01", "audit_id": "AUD-CAM-S01-A-20261123-10", "status": "done"}
    old_training = {"store_id": "DEMO-S01", "audit_id": "TRN-CAM-S01-A-20261124-10", "status": "done"}
    assert sheet_for(old_scoring, A, "2026-11-28T12:00:00+07:00", "0a1b2c3d")["purpose"] == "scoring"
    assert sheet_for(old_training, A, "2026-11-28T12:00:00+07:00", "0a1b2c3e")["purpose"] == "training"


def test_a_sheet_keeps_the_display_score_of_its_frame():
    assert (
        sheet_for({**key(3), "display_score": 0.91}, A, "2026-11-28T12:00:00+07:00", "0a1b2c3d")["display_score"]
        == 0.91
    )
    assert "display_score" not in sheet_for(key(3), A, "2026-11-28T12:00:00+07:00", "0a1b2c3d")


def test_the_check_is_made_from_the_newest_key():
    keys = [
        {**key(3), "capture_timestamp": "2026-11-26T09:00:00+07:00"},
        {**key(4), "capture_timestamp": "2026-11-28T07:20:00+07:00"},
        {**key(5), "capture_timestamp": "2026-11-27T12:30:00+07:00"},
    ]
    assert newest_key(keys)["audit_id"] == "TRN-CAM-S01-A-20261128-04"


def test_who_has_no_answer_key_left():
    audits = [key(3), frame(10, A), frame(11, B), sheet("11111111", "TRN-CAM-S01-A-20261128-03", A, "done", 12)]
    # the admin labelled and marked the only key; A was checked on it already; B can still get it
    assert without_key(audits) == [A, ADMIN]
    assert without_key([frame(10, A)]) == [A]  # no key at all
    assert without_key([]) == []
