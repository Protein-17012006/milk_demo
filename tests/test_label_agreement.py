"""A labeller's answers on a check sheet against the answer key (operations-loop design 5.4).

Every expected number is counted by hand from the answers below: a unit is a box of the frame, a missed mark of the
key, or a mark of the labeller that matches none of the key's."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from label_agreement import MATCH_PX, compare, week_of, weekly  # noqa: E402

KEY_V = [{"box_id": 1, "verdict": "correct"}, {"box_id": 2, "verdict": "wrong_sku", "true_sku_id": "original145"}]
KEY_M = [{"sku_id": "hot160", "x": 900, "y": 500}]


def test_the_same_answers_agree_on_every_unit():
    assert compare(KEY_V, KEY_M, KEY_V, KEY_M) == {
        "units": 3,
        "agree": 3,
        "boxes": 2,
        "boxes_agree": 2,
        "marks_key": 1,
        "marks_matched": 1,
        "marks_extra": 0,
    }


def test_calling_the_models_wrong_name_right_is_a_disagreement():
    mine = [{"box_id": 1, "verdict": "correct"}, {"box_id": 2, "verdict": "correct"}]
    out = compare(KEY_V, KEY_M, mine, KEY_M)
    assert (out["boxes_agree"], out["agree"], out["units"]) == (1, 2, 3)


def test_another_right_name_is_a_disagreement():
    mine = [KEY_V[0], {"box_id": 2, "verdict": "wrong_sku", "true_sku_id": "hot160"}]
    assert compare(KEY_V, KEY_M, mine, KEY_M)["boxes_agree"] == 1


def test_a_box_left_without_a_verdict_is_a_disagreement():
    out = compare(KEY_V, KEY_M, [KEY_V[0]], KEY_M)
    assert (out["boxes"], out["boxes_agree"]) == (2, 1)


def test_a_mark_within_forty_pixels_and_of_the_same_product_matches():
    assert MATCH_PX == 40
    assert compare(KEY_V, KEY_M, KEY_V, [{"sku_id": "hot160", "x": 925, "y": 520}])["marks_matched"] == 1  # 32 px away
    assert compare(KEY_V, KEY_M, KEY_V, [{"sku_id": "hot160", "x": 940, "y": 500}])["marks_matched"] == 1  # 40 px
    assert compare(KEY_V, KEY_M, KEY_V, [{"sku_id": "hot160", "x": 941, "y": 500}])["marks_matched"] == 0  # 41 px


def test_a_mark_of_another_product_at_the_same_place_does_not_match():
    out = compare(KEY_V, KEY_M, KEY_V, [{"sku_id": "original145", "x": 900, "y": 500}])
    assert (out["marks_matched"], out["marks_extra"], out["units"], out["agree"]) == (0, 1, 4, 2)


def test_two_marks_on_one_can_match_once():
    mine = [{"sku_id": "hot160", "x": 900, "y": 500}, {"sku_id": "hot160", "x": 910, "y": 505}]
    out = compare(KEY_V, KEY_M, KEY_V, mine)
    assert (out["marks_matched"], out["marks_extra"], out["units"], out["agree"]) == (1, 1, 4, 3)


def test_each_mark_takes_the_nearest_free_mark_of_the_key():
    key_marks = [{"sku_id": "hot160", "x": 900, "y": 500}, {"sku_id": "hot160", "x": 930, "y": 500}]
    mine = [{"sku_id": "hot160", "x": 928, "y": 500}, {"sku_id": "hot160", "x": 902, "y": 500}]
    out = compare(KEY_V, key_marks, KEY_V, mine)
    assert (out["marks_key"], out["marks_matched"], out["marks_extra"]) == (2, 2, 0)


def test_a_mark_the_labeller_did_not_make_is_a_disagreement():
    out = compare(KEY_V, KEY_M, KEY_V, [])
    assert (out["marks_matched"], out["units"], out["agree"]) == (0, 3, 2)


def test_a_frame_without_boxes_or_marks_has_no_unit():
    assert compare([], [], [], []) == {
        "units": 0,
        "agree": 0,
        "boxes": 0,
        "boxes_agree": 0,
        "marks_key": 0,
        "marks_matched": 0,
        "marks_extra": 0,
    }


def test_the_week_follows_the_store_clock():
    assert week_of("2026-11-29T23:30:00+07:00") == "2026-W48"  # a Sunday
    assert week_of("2026-11-29T17:30:00+00:00") == "2026-W49"  # Monday 00:30 in Vietnam
    assert week_of("2027-01-01T08:00:00+07:00") == "2026-W53"  # the ISO week keeps its own year


def _pair(by: str, at: str, verdicts: list[dict], missed: list[dict]) -> tuple[dict, dict]:
    key = {"audit_id": "TRN-CAM-S01-A-20261121-08", "key_verdicts": KEY_V, "key_missed": KEY_M}
    sheet = {"audit_id": "CHK-0a1b2c3d", "labeled_by": by, "labeled_at": at, "verdicts": verdicts, "missed": missed}
    return key, sheet


def test_weekly_sums_units_per_labeller_and_week():
    both_right = [{"box_id": 1, "verdict": "correct"}, {"box_id": 2, "verdict": "correct"}]
    pairs = [
        _pair("ann@team.vn", "2026-11-24T09:00:00+07:00", KEY_V, KEY_M),  # 3 of 3
        _pair("ann@team.vn", "2026-11-27T09:00:00+07:00", both_right, []),  # 1 of 3
        _pair("ann@team.vn", "2026-11-30T09:00:00+07:00", KEY_V, KEY_M),  # the next week: 3 of 3
        _pair("binh@client.vn", "2026-11-25T09:00:00+07:00", both_right, KEY_M),  # 2 of 3
    ]
    assert weekly(pairs) == [
        {"labeller": "ann@team.vn", "week": "2026-W49", "frames": 1, "units": 3, "agree": 3, "agreement": 1.0},
        {
            "labeller": "ann@team.vn",
            "week": "2026-W48",
            "frames": 2,
            "units": 6,
            "agree": 4,
            "agreement": pytest.approx(4 / 6),
        },
        {
            "labeller": "binh@client.vn",
            "week": "2026-W48",
            "frames": 1,
            "units": 3,
            "agree": 2,
            "agreement": pytest.approx(2 / 3),
        },
    ]


def test_a_week_of_frames_without_units_has_no_agreement():
    key = {"audit_id": "k", "key_verdicts": [], "key_missed": []}
    sheet = {"audit_id": "CHK-1", "labeled_by": "ann@team.vn", "labeled_at": "2026-11-24T09:00:00+07:00"}
    (row,) = weekly([(key, {**sheet, "verdicts": [], "missed": []})])
    assert (row["frames"], row["units"], row["agreement"]) == (1, 0, None)
