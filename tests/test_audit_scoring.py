"""Scoring of frames the team labelled on the Model page, against Datagent's Accuracy Report (spec section 5).

Every expected value below was worked out by hand from the boxes and verdicts in the fixture."""

from __future__ import annotations

import random
import statistics
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from audit_scoring import (  # noqa: E402
    BOOTSTRAP_SAMPLES,
    BOOTSTRAP_SEED,
    MIN_DAYS,
    MIN_FRAMES,
    MIN_TRUE_UNITS,
    _resamples,
    badge,
    check_level,
    comparison_rows,
    display_agreement,
    enough,
    frame_tallies,
    period_of,
    ratio_ci,
    sku_reliability,
    summarize,
    validate_labels,
)

CATALOG = {"original145", "sourcream150", "cheese145", "hot160", "TMP-MLK-TH-01"}

AUDIT_2311 = {  # 2 Original read as Hot, 1 Original right, cheese: 1 right + 1 candy, missed: 2 Hot, 1 cheese
    "capture_timestamp": "2026-11-23T12:56:54+07:00",
    "ai_boxes": [
        {"box_id": 1, "sku_id": "hot160", "conf": 0.87, "box": [948, 326, 72, 167]},
        {"box_id": 2, "sku_id": "hot160", "conf": 0.94, "box": [1190, 288, 74, 150]},
        {"box_id": 3, "sku_id": "original145", "conf": 0.67, "box": [1063, 336, 75, 117]},
        {"box_id": 4, "sku_id": "cheese145", "conf": 0.85, "box": [1121, 310, 73, 129]},
        {"box_id": 5, "sku_id": "cheese145", "conf": 0.85, "box": [700, 900, 60, 60]},
    ],
    "verdicts": [
        {"box_id": 1, "verdict": "wrong_sku", "true_sku_id": "original145"},
        {"box_id": 2, "verdict": "wrong_sku", "true_sku_id": "original145"},
        {"box_id": 3, "verdict": "correct"},
        {"box_id": 4, "verdict": "correct"},
        {"box_id": 5, "verdict": "not_product"},
    ],
    "missed": [
        {"sku_id": "hot160", "x": 940, "y": 400},
        {"sku_id": "hot160", "x": 1030, "y": 330},
        {"sku_id": "cheese145", "x": 1010, "y": 290},
    ],
}


def test_rows_of_the_2311_frame():
    rows = {r["sku_id"]: r for r in comparison_rows(AUDIT_2311)}
    assert (rows["original145"]["ai_unit_count"], rows["original145"]["human_unit_count"]) == (1, 3)
    assert rows["original145"]["discrepancy_category"] == "Minor"
    assert round(rows["original145"]["count_accuracy_pct"], 4) == 0.3333
    assert (rows["hot160"]["ai_unit_count"], rows["hot160"]["human_unit_count"]) == (2, 2)
    assert rows["hot160"]["discrepancy_category"] == "Wrong SKU"  # counts match, cans are wrong
    assert rows["cheese145"]["discrepancy_category"] == "Exact Match"


def test_kpis_of_the_2311_frame():
    k = summarize([AUDIT_2311], [20, 30])["kpis"]
    assert k["overall_identification_accuracy"]["value"] == 0.5  # 2 of 4 catalog boxes named right
    assert k["overall_identification_accuracy"]["met"] is False
    assert round(k["unit_count_mae"]["value"], 4) == 0.6667
    assert round(k["unit_count_accuracy_avg"]["value"], 4) == 0.7778
    assert round(k["exact_match_rate"]["value"], 4) == 0.3333
    assert k["missed_sku_rate"]["value"] == 0.0
    assert k["false_detection_rate"]["value"] == 0.2
    assert round(k["avg_confidence_correct"]["value"], 4) == 0.76
    assert round(k["avg_confidence_incorrect"]["value"], 4) == 0.8867
    assert k["avg_processing_time_ms"]["value"] == 25
    assert k["unrecognized_product_rate"]["value"] == 0.0


def test_per_sku_and_confusion_of_the_2311_frame():
    s = summarize([AUDIT_2311], [])
    hot = next(r for r in s["per_sku"] if r["sku_id"] == "hot160")
    assert (hot["model_units"], hot["true_units"], hot["id_accuracy"], hot["missed_units"]) == (2, 2, 0.0, 2)
    assert (hot["confused_as"], hot["confused_count"]) == ("original145", 2)
    assert s["confusion"]["cells"]["hot160|original145"] == 2
    assert s["confusion"]["cells"]["cheese145|NOT_PRODUCT"] == 1
    assert s["confusion"]["cells"]["MISSED|hot160"] == 2


def test_unrecognized_box_on_other_goods_counts_for_no_sku():
    audit = {
        "capture_timestamp": "2026-11-23T13:00:00+07:00",
        "ai_boxes": [
            {"box_id": 1, "sku_id": None, "conf": 0.45, "box": [0, 0, 10, 10]},
            {"box_id": 2, "sku_id": None, "conf": 0.30, "box": [20, 0, 10, 10]},
        ],
        "verdicts": [
            {"box_id": 1, "verdict": "correct"},
            {"box_id": 2, "verdict": "wrong_sku", "true_sku_id": "cheese145"},
        ],
        "missed": [],
    }
    assert comparison_rows(audit) == [
        {
            "sku_id": "cheese145",
            "ai_unit_count": 0,
            "human_unit_count": 1,
            "count_difference": -1,
            "count_accuracy_pct": 0.0,
            "discrepancy_category": "Missed SKU",
        }
    ]
    k = summarize([audit], [])["kpis"]
    assert k["overall_identification_accuracy"]["value"] == 0.0  # box 2: catalog can, not named
    assert k["unrecognized_product_rate"]["value"] == 1.0


def test_a_frame_with_no_boxes_scores_only_its_misses():
    audit = {
        "capture_timestamp": "2026-11-23T14:00:00+07:00",
        "ai_boxes": [],
        "verdicts": [],
        "missed": [{"sku_id": "hot160", "x": 1, "y": 1}],
    }
    k = summarize([audit], [])["kpis"]
    assert k["missed_sku_rate"]["value"] == 1.0
    assert k["overall_identification_accuracy"] == {
        "value": None,
        "target": [">=", 0.6],
        "met": None,
        "n": 0,
        "ci": None,
    }


def test_no_audits_means_no_numbers():
    k = summarize([], [])["kpis"]
    assert all(v["value"] is None and v["n"] == 0 for v in k.values())


def test_validate_labels():
    boxes = AUDIT_2311["ai_boxes"]
    assert validate_labels(boxes, AUDIT_2311["verdicts"], AUDIT_2311["missed"], CATALOG) == []
    assert validate_labels(boxes, AUDIT_2311["verdicts"][:4], [], CATALOG) == ["box 5 has no verdict"]
    bad = AUDIT_2311["verdicts"][:4] + [{"box_id": 5, "verdict": "wrong_sku", "true_sku_id": "xyz"}]
    assert validate_labels(boxes, bad, [], CATALOG) == ["unknown sku 'xyz'"]
    assert validate_labels([], [], [{"sku_id": "hot160", "x": 1, "y": 1}], CATALOG) == []


AUDIT_SCOPE = {  # 2 Cheese named right, 1 real Cheese can on the lower tier (out of scope under rule A)
    "capture_timestamp": "2026-11-24T09:35:04+07:00",
    "ai_boxes": [
        {"box_id": 1, "sku_id": "cheese145", "conf": 0.96, "box": [907, 227, 69, 180]},
        {"box_id": 2, "sku_id": "cheese145", "conf": 0.95, "box": [944, 259, 70, 46]},
        {"box_id": 3, "sku_id": "cheese145", "conf": 0.41, "box": [950, 560, 60, 70]},
    ],
    "verdicts": [
        {"box_id": 1, "verdict": "correct"},
        {"box_id": 2, "verdict": "correct"},
        {"box_id": 3, "verdict": "out_of_scope"},
    ],
    "missed": [],
}


def test_out_of_scope_boxes_count_nowhere():
    rows = comparison_rows(AUDIT_SCOPE)
    assert [(r["sku_id"], r["ai_unit_count"], r["human_unit_count"], r["discrepancy_category"]) for r in rows] == [
        ("cheese145", 2, 2, "Exact Match")
    ]
    s = summarize([AUDIT_SCOPE], [])
    assert (s["kpis"]["false_detection_rate"]["value"], s["kpis"]["false_detection_rate"]["n"]) == (0.0, 2)
    assert s["kpis"]["avg_confidence_correct"]["n"] == 2
    assert next(r for r in s["per_sku"] if r["sku_id"] == "cheese145")["model_units"] == 2
    assert s["confusion"]["cells"] == {"cheese145|cheese145": 2}


def test_a_frame_of_only_out_of_scope_boxes_has_no_numbers():
    only = {**AUDIT_SCOPE, "ai_boxes": AUDIT_SCOPE["ai_boxes"][2:], "verdicts": AUDIT_SCOPE["verdicts"][2:]}
    k = summarize([only], [])["kpis"]
    assert k["false_detection_rate"]["value"] is None and k["unit_count_mae"]["value"] is None


def test_validate_labels_accepts_out_of_scope():
    assert validate_labels(AUDIT_SCOPE["ai_boxes"], AUDIT_SCOPE["verdicts"], [], CATALOG) == []


def test_share_of_out_of_scope_boxes_is_counted_before_they_are_dropped():
    share = summarize([AUDIT_SCOPE], [])["out_of_scope_share"]
    assert share["n"] == 3 and share["value"] == pytest.approx(1 / 3)
    assert summarize([], [])["out_of_scope_share"] == {"value": None, "n": 0}


# --- Two-way accuracy, present or absent, check level, by time of day, intervals (reliability spec 1.2c) ---

EXPECTED = {"original145", "hot160", "cheese145", "sourcream150"}

AUDIT_1744 = {  # the real 23/11 17:44 frame: 3 Original read as Cheese, 2 Cheese right, 3 Sour Cream right, no misses
    "capture_timestamp": "2026-11-23T17:44:38+07:00",
    "ai_boxes": [
        {"box_id": 1, "sku_id": "cheese145", "conf": 0.81, "box": [905, 300, 70, 160]},
        {"box_id": 2, "sku_id": "cheese145", "conf": 0.77, "box": [980, 302, 70, 158]},
        {"box_id": 3, "sku_id": "cheese145", "conf": 0.74, "box": [1055, 298, 71, 161]},
        {"box_id": 4, "sku_id": "cheese145", "conf": 0.93, "box": [1130, 300, 70, 160]},
        {"box_id": 5, "sku_id": "cheese145", "conf": 0.95, "box": [1205, 301, 69, 159]},
        {"box_id": 6, "sku_id": "sourcream150", "conf": 0.92, "box": [1280, 296, 72, 166]},
        {"box_id": 7, "sku_id": "sourcream150", "conf": 0.90, "box": [1356, 297, 72, 165]},
        {"box_id": 8, "sku_id": "sourcream150", "conf": 0.88, "box": [1432, 298, 72, 164]},
    ],
    "verdicts": [
        {"box_id": 1, "verdict": "wrong_sku", "true_sku_id": "original145"},
        {"box_id": 2, "verdict": "wrong_sku", "true_sku_id": "original145"},
        {"box_id": 3, "verdict": "wrong_sku", "true_sku_id": "original145"},
        {"box_id": 4, "verdict": "correct"},
        {"box_id": 5, "verdict": "correct"},
        {"box_id": 6, "verdict": "correct"},
        {"box_id": 7, "verdict": "correct"},
        {"box_id": 8, "verdict": "correct"},
    ],
    "missed": [],
}


def test_found_right_is_named_right_over_true_units():
    s = summarize([AUDIT_2311], [])
    rows = {r["sku_id"]: r for r in s["per_sku"]}
    assert (rows["original145"]["found_right"], rows["hot160"]["found_right"]) == (1 / 3, 0.0)
    assert rows["original145"]["bias_per_frame"] == -2.0  # model 1, truth 3


def test_presence_counts_false_empties():
    p = summarize([AUDIT_1744], [], expected=EXPECTED)["presence"]
    # original: model 0, truth 3 -> false empty; hot: 0/0 agree; cheese and sour cream present on both sides
    assert (p["agree"]["value"], p["agree"]["n"]) == (0.75, 4)
    assert (p["false_empty"]["value"], p["false_empty"]["n"]) == (0.5, 2)
    assert (p["missed_empty"]["value"], p["missed_empty"]["n"]) == (0.0, 1)


def test_periods_follow_the_frame_hour():
    assert [
        period_of(t) for t in ("2026-11-24T09:35:04+07:00", "2026-11-23T14:18:11+07:00", "2026-11-23T17:44:38+07:00")
    ] == ["morning", "afternoon", "evening"]


def test_bootstrap_is_repeatable_and_brackets_the_value():
    tallies = [(9, 11), (8, 10), (10, 12), (7, 11), (11, 13)]
    ci = ratio_ci(tallies)
    assert ci == ratio_ci(tallies) and ci[0] <= sum(t[0] for t in tallies) / sum(t[1] for t in tallies) <= ci[1]
    assert ratio_ci([(1, 2)]) is None  # one frame gives no interval


def test_enough_needs_ten_frames_twenty_cans_and_two_days():
    assert enough(10, 20, 2) and not enough(9, 20, 2) and not enough(10, 19, 2) and not enough(10, 20, 1)


def test_display_agreement():
    seen = {"status": "done", "display_visible": True, "display_score": 0.91}
    away = {"status": "skipped", "skip_reason": "display_away", "display_visible": False, "display_score": 0.21}
    judged = [
        *[seen] * 7,
        {**seen, "display_score": 1},  # a score of exactly 1 reads back from DynamoDB as an int
        {"status": "done", "display_visible": False, "display_score": 0.42},  # the labeller saw it, the check said no
        *[away] * 2,
        {"status": "skipped", "skip_reason": "display_away", "display_visible": True, "display_score": 0.77},
        {"status": "skipped", "skip_reason": "display_away", "display_visible": False},  # only a check says False
    ]
    unjudged = [
        {"status": "done"},  # before the display check existed
        {"status": "done", "display_visible": True},  # 24/11 13:50-19:03: True copied from an old worker's capture
        {"status": "skipped", "skip_reason": "display_away", "display_visible": True},  # no reference learnt yet
        {"status": "skipped", "skip_reason": "blurry", "display_visible": False, "display_score": 0.3},  # not about it
        {"status": "pending", "display_visible": True, "display_score": 0.9},  # not labelled yet
    ]
    d = display_agreement(judged + unjudged)
    # 13 judged frames: 8 + 2 + 1 agree; 1 wrongly "not in view" (0.42), 1 wrongly "in view" (0.77)
    assert (d["agree"]["value"], d["agree"]["n"], d["false_not_visible"], d["false_visible"]) == (11 / 13, 13, 1, 1)
    assert d["agree"]["ci"][0] <= 11 / 13 <= d["agree"]["ci"][1]


def test_display_agreement_needs_ten_judged_frames():
    seen = {"status": "done", "display_visible": True, "display_score": 0.91}
    d = display_agreement([seen] * (MIN_FRAMES - 1) + [{"status": "done"}] * 5)
    assert d == {"agree": {"value": None, "ci": None, "n": 9}, "false_not_visible": 0, "false_visible": 0}
    assert display_agreement([seen] * MIN_FRAMES)["agree"]["value"] == 1.0


def test_summary_of_300_frames_takes_under_three_seconds():
    started = time.perf_counter()
    summarize([AUDIT_1744, AUDIT_2311] * 150, [], expected=EXPECTED)
    assert time.perf_counter() - started < 3.0


def test_tallies_of_the_1744_frame():
    t = frame_tallies(AUDIT_1744, EXPECTED)
    assert (t["named_right:cheese145"], t["named_right:sourcream150"]) == ((2, 5), (3, 3))
    assert (t["found_right:original145"], t["found_right:cheese145"]) == ((0, 3), (2, 2))
    assert (t["bias:original145"], t["bias:cheese145"], t["bias:sourcream150"]) == ((-3, 1), (3, 1), (0, 1))
    assert "named_right:hot160" not in t  # neither side counted Hot: no pair, it only counts in present or absent
    assert (t["presence_agree"], t["false_empty"], t["missed_empty"]) == ((3, 4), (1, 2), (0, 1))
    assert t["kpi:overall_identification_accuracy"] == (5, 8)  # 3 Original boxes named Cheese
    assert t["kpi:unit_count_mae"] == (6, 3)  # cheese +3, original -3, sour cream 0


def test_kpis_of_the_1744_frame():
    k = summarize([AUDIT_1744], [])["kpis"]
    assert k["overall_identification_accuracy"]["value"] == 0.625
    assert k["unit_count_mae"]["value"] == 2.0
    assert round(k["unit_count_accuracy_avg"]["value"], 4) == 0.3333  # cheese 0 (5 for 2), original 0, sour cream 1
    assert round(k["exact_match_rate"]["value"], 4) == 0.3333
    assert k["minor_error_rate"]["value"] == 0.0 and round(k["minor_error_rate"]["exact_or_minor"], 4) == 0.3333
    assert round(k["missed_sku_rate"]["value"], 4) == 0.3333
    assert k["false_detection_rate"]["value"] == 0.0
    assert round(k["avg_confidence_correct"]["value"], 4) == 0.916
    assert round(k["avg_confidence_incorrect"]["value"], 4) == 0.7733


def test_kpis_over_frames_are_sums_over_sums_with_an_interval():
    k = summarize([AUDIT_2311, AUDIT_1744], [20])["kpis"]
    assert (k["overall_identification_accuracy"]["value"], k["overall_identification_accuracy"]["n"]) == (7 / 12, 12)
    assert round(k["unit_count_mae"]["value"], 4) == 1.3333  # (2 + 6) units off over 6 rows, not a mean of means
    for name, kpi in k.items():
        if name == "avg_processing_time_ms":
            assert "ci" not in kpi  # KPI 11 comes from the hourly health, not from frames
        elif kpi["value"] is not None:  # bounds have 4 decimals: exact match is 1/3 in both frames, [0.3333, 0.3333]
            assert kpi["ci"][0] <= round(kpi["value"], 4) <= kpi["ci"][1], name
    assert summarize([AUDIT_2311], [])["kpis"]["unit_count_mae"]["ci"] is None  # one frame: no interval


def test_per_sku_rows_carry_both_ways_with_intervals():
    rows = {r["sku_id"]: r for r in summarize([AUDIT_2311, AUDIT_1744], [])["per_sku"]}
    cheese = rows["cheese145"]  # 2311: 1 right of 2 named, 2 true; 1744: 2 right of 5 named, 2 true
    assert (cheese["id_accuracy"], cheese["found_right"]) == (3 / 7, 3 / 4)
    assert cheese["bias_per_frame"] == 1.5  # (2 - 2 + 5 - 2) / 2 frames
    assert cheese["id_accuracy_ci"][0] <= 3 / 7 <= cheese["id_accuracy_ci"][1]
    assert cheese["found_right_ci"][0] <= 3 / 4 <= cheese["found_right_ci"][1]
    assert cheese["bias_per_frame_ci"][0] <= 1.5 <= cheese["bias_per_frame_ci"][1]
    assert (cheese["frames"], cheese["days"], cheese["enough"]) == (2, 1, False)
    hot = rows["hot160"]  # only in 2311: both boxes wrong, 2 true cans missed
    assert (hot["found_right"], hot["found_right_ci"], hot["frames"]) == (0.0, None, 1)


def test_a_sku_never_really_there_has_no_found_right():
    audit = {
        "capture_timestamp": "2026-11-23T13:00:00+07:00",
        "ai_boxes": [{"box_id": 1, "sku_id": "hot160", "conf": 0.6, "box": [0, 0, 10, 10]}],
        "verdicts": [{"box_id": 1, "verdict": "not_product"}],
        "missed": [],
    }
    row = summarize([audit], [])["per_sku"][0]
    assert (row["sku_id"], row["id_accuracy"], row["found_right"], row["bias_per_frame"]) == ("hot160", 0.0, None, 1.0)
    assert (row["true_units"], row["frames"], row["days"], row["enough"]) == (0, 0, 0, False)


def test_enough_samples_need_true_cans_on_two_ict_days():
    def on(day: str) -> dict:
        return {**AUDIT_1744, "capture_timestamp": f"{day}T17:44:38+07:00"}

    two_days = [on("2026-11-23")] * 5 + [on("2026-11-24")] * 5
    rows = {r["sku_id"]: r for r in summarize(two_days, [])["per_sku"]}
    assert (rows["cheese145"]["frames"], rows["cheese145"]["true_units"], rows["cheese145"]["days"]) == (10, 20, 2)
    assert rows["cheese145"]["enough"] and rows["original145"]["enough"]
    one_day = [on("2026-11-23")] * 10
    assert not any(r["enough"] for r in summarize(one_day, [])["per_sku"])
    # 23/11 23:30 UTC is 24/11 06:30 in ICT: two days, and a morning frame
    late = {**AUDIT_1744, "capture_timestamp": "2026-11-23T23:30:00+00:00"}
    s = summarize([AUDIT_1744, late], [])
    assert next(r for r in s["per_sku"] if r["sku_id"] == "cheese145")["days"] == 2
    assert (s["by_period"]["morning"]["frames"], s["by_period"]["evening"]["frames"]) == (1, 1)


def test_periods_are_in_ict():
    assert [period_of(t) for t in ("2026-11-23T04:59:59+00:00", "2026-11-23T05:00:00Z", "2026-11-23T10:00:00Z")] == [
        "morning",
        "afternoon",
        "evening",
    ]


def test_by_period_gives_each_sku_both_ways():
    p = summarize([AUDIT_2311, AUDIT_1744], [], expected=EXPECTED)["by_period"]
    assert p["morning"] == {
        "frames": 0,
        "overall_identification_accuracy": {"value": None, "ci": None, "n": 0},
        "presence_agree": {"value": None, "ci": None, "n": 0},
        "per_sku": {},
    }
    afternoon, evening = p["afternoon"], p["evening"]  # 2311 at 12:56, 1744 at 17:44
    assert (afternoon["frames"], afternoon["overall_identification_accuracy"]["value"]) == (1, 0.5)
    assert (afternoon["presence_agree"]["value"], afternoon["presence_agree"]["n"]) == (1.0, 4)
    assert afternoon["per_sku"]["hot160"] == {
        "named_right": 0.0,
        "found_right": 0.0,
        "model_units": 2,
        "true_units": 2,
        "frames": 1,
        "days": 1,
        "enough": False,
    }
    assert (evening["frames"], evening["overall_identification_accuracy"]["value"]) == (1, 0.625)
    original = evening["per_sku"]["original145"]  # three cans, all read as Cheese
    assert (original["named_right"], original["found_right"], original["true_units"]) == (None, 0.0, 3)
    assert "hot160" not in evening["per_sku"]


def test_check_level_compares_the_dashboard_counts_with_the_frame_truth():
    pairs = [
        (AUDIT_1744, {"cheese145": 4, "sourcream150": 3}),  # off: original -3, cheese +2, sour cream 0
        (AUDIT_2311, {"hot160": 2, "original145": 1, "cheese145": 1, "sourcream150": 0}),  # original -2, cheese -1
    ]
    c = check_level(pairs, EXPECTED)
    assert c["frames"] == 2
    assert (round(c["count_mae"]["value"], 4), c["count_mae"]["n"]) == (1.3333, 6)  # (5 + 3) / 6 SKU pairs
    assert (round(c["count_bias"]["value"], 4), c["count_bias"]["n"]) == (-0.6667, 6)  # (-1 - 3) / 6, signed
    assert (c["presence_agree"]["value"], c["presence_agree"]["n"]) == (7 / 8, 8)  # only 1744's Original disagrees
    assert c["count_bias"]["ci"][0] <= c["count_bias"]["value"] <= c["count_bias"]["ci"][1]


def test_each_frame_is_held_to_its_own_stores_plan():
    a = {**AUDIT_1744, "store_id": "S-A"}  # model Cheese 5, Sour Cream 3; truth Original 3, Cheese 2, Sour Cream 3
    b = {**AUDIT_2311, "store_id": "S-B"}  # model Hot 2, Original 1, Cheese 2; truth Original 3, Hot 2, Cheese 2
    plans = {"S-A": {"cheese145", "sourcream150"}, "S-B": {"hot160", "TMP-MLK-TH-01"}}
    # S-A: Cheese, Sour Cream, Original (counted): 2 agree of 3, Original a false empty; Hot and TH are not S-A's
    # S-B: Hot, TH, Original, Cheese: 4 of 4, TH 0/0 is the only empty row. One merged plan would give 9/10, 1/5, 0/4.
    p = summarize([a, b], [], expected=plans)["presence"]
    assert (p["agree"]["value"], p["agree"]["n"]) == (6 / 7, 7)
    assert (p["false_empty"]["value"], p["false_empty"]["n"]) == (0.5, 2)
    assert (p["missed_empty"]["value"], p["missed_empty"]["n"]) == (0.0, 1)
    pairs = [(a, {"cheese145": 5, "sourcream150": 3}), (b, {"hot160": 2, "original145": 1, "cheese145": 2})]
    agree = check_level(pairs, plans)["presence_agree"]
    assert (agree["value"], agree["n"]) == (6 / 7, 7)
    alone = summarize([{**a, "store_id": "S-C"}], [], expected=plans)["presence"]["agree"]  # a store without a plan
    assert (alone["value"], alone["n"]) == (2 / 3, 3)


def test_check_level_without_checks_has_no_numbers():
    assert check_level([]) == {
        "frames": 0,
        "count_mae": {"value": None, "ci": None, "n": 0},
        "count_bias": {"value": None, "ci": None, "n": 0},
        "presence_agree": {"value": None, "ci": None, "n": 0},
    }


def test_display_agreement_leaves_out_frames_from_before_the_check():
    d = display_agreement([{"status": "done"}, {"status": "skipped", "skip_reason": "display_away"}])
    assert d == {"agree": {"value": None, "ci": None, "n": 0}, "false_not_visible": 0, "false_visible": 0}
    assert display_agreement([{"status": "pending"}])["agree"] == {"value": None, "ci": None, "n": 0}


def test_bootstrap_resamples_whole_frames_with_the_fixed_seed():
    # the brief's steps done plainly: keep frames with a denominator, draw that many with replacement by
    # random.Random(seed) BOOTSTRAP_SAMPLES times, sum over sum each time, 2.5th and 97.5th percentiles, 4 decimals
    assert (BOOTSTRAP_SAMPLES, BOOTSTRAP_SEED, MIN_FRAMES, MIN_TRUE_UNITS, MIN_DAYS) == (400, 20261124, 10, 20, 2)
    tallies = [(9, 11), (8, 10), (0, 0), (10, 12), (7, 11), (11, 13), (2, 5)]
    kept = [t for t in tallies if t[1] > 0]
    rng = random.Random(BOOTSTRAP_SEED)
    draws = [rng.choices(kept, k=len(kept)) for _ in range(BOOTSTRAP_SAMPLES)]
    values = [sum(num for num, _ in draw) / sum(den for _, den in draw) for draw in draws]
    cuts = statistics.quantiles(values, n=40, method="inclusive")
    assert ratio_ci(tallies) == [round(cuts[0], 4), round(cuts[-1], 4)]


def test_the_bootstrap_draws_are_not_kept_after_a_call():
    # the API Lambda has 256 MB and stays warm: draws of 1,440 frames held ~99 MB after the call
    frames = [AUDIT_1744, AUDIT_2311] * 6
    summarize(frames, [], expected=EXPECTED)
    assert _resamples.cache_info().currsize == 0
    sku_reliability(_frames_of_cheese(("22", "23"), 6))
    assert _resamples.cache_info().currsize == 0
    check_level([(a, {"cheese145": 4}) for a in frames], EXPECTED)
    assert _resamples.cache_info().currsize == 0
    display_agreement([{"status": "done", "display_visible": True, "display_score": 0.9}] * 12)
    assert _resamples.cache_info().currsize == 0
    # ratio_ci itself keeps its draws, so that the ratios inside one of those calls share them
    assert ratio_ci([(1, 2), (2, 3)]) and _resamples.cache_info().currsize == 1
    _resamples.cache_clear()


def test_frames_without_a_denominator_give_no_interval():
    assert ratio_ci([(1, 2), (0, 0), (0, 0)]) is None  # one frame counted
    assert ratio_ci([]) is None


def test_no_frames_give_no_new_numbers():
    s = summarize([], [], expected=EXPECTED)
    assert s["presence"]["agree"] == {"value": None, "ci": None, "n": 0}
    assert all(p["frames"] == 0 and p["per_sku"] == {} for p in s["by_period"].values())
    assert s["kpis"]["unit_count_mae"]["ci"] is None


def _row(enough=True, named=(0.92, 0.97), found=(0.91, 0.99)):
    return {"enough": enough, "id_accuracy_ci": list(named), "found_right_ci": list(found)}


def test_badges():
    assert badge(_row(enough=False)) == "insufficient"
    assert badge(_row()) == "high"
    assert badge(_row(found=(0.72, 0.9))) == "medium"
    assert badge(_row(named=(0.55, 0.8))) == "low"
    # never named by the model: no interval of named right, which counts as a lower bound of 0 (spec 1.3)
    assert badge({"enough": True, "id_accuracy_ci": None, "found_right_ci": [0.9, 1.0]}) == "low"
    assert badge({"enough": False, "id_accuracy_ci": None, "found_right_ci": [0.9, 1.0]}) == "insufficient"
    # nothing to be found: no interval of found right
    assert badge({"enough": True, "id_accuracy_ci": [0.95, 1.0], "found_right_ci": None}) == "insufficient"


def _frames_of_cheese(days: tuple[str, ...], per_day: int) -> list[dict]:
    """Frames of one Cheese story: of 2 boxes named Cheese 1 is right and 1 is not a product; 2 boxes named Hot
    are really Cheese. True Cheese cans per frame: 3."""
    out = []
    for day in days:
        for i in range(per_day):
            out.append(
                {
                    "store_id": "S1",
                    "capture_timestamp": f"2026-11-{day}T1{i % 10}:10:00+07:00",
                    "ai_boxes": [
                        {"box_id": 1, "sku_id": "cheese145", "conf": 0.9, "box": [0, 0, 5, 5]},
                        {"box_id": 2, "sku_id": "cheese145", "conf": 0.9, "box": [9, 0, 5, 5]},
                        {"box_id": 3, "sku_id": "hot160", "conf": 0.9, "box": [18, 0, 5, 5]},
                        {"box_id": 4, "sku_id": "hot160", "conf": 0.9, "box": [27, 0, 5, 5]},
                    ],
                    "verdicts": [
                        {"box_id": 1, "verdict": "correct"},
                        {"box_id": 2, "verdict": "not_product"},
                        {"box_id": 3, "verdict": "wrong_sku", "true_sku_id": "cheese145"},
                        {"box_id": 4, "verdict": "wrong_sku", "true_sku_id": "cheese145"},
                    ],
                    "missed": [],
                }
            )
    return out


def test_sku_reliability_counts_and_what_a_sku_is_read_as():
    audits = _frames_of_cheese(("22", "23"), 6)  # 12 frames, 3 true Cheese cans each = 36
    rel = sku_reliability(audits)
    cheese = rel["cheese145"]
    assert cheese["badge"] == "low"  # found right 1 of 3, named right 1 of 2
    assert (cheese["true_units"], cheese["frames"]) == (36, 12)
    assert cheese["found_right"] == pytest.approx(1 / 3) and cheese["named_right"] == 0.5
    assert cheese["confused_as"] == "hot160"  # its true cans were most often called Hot
    hot = rel["hot160"]  # never really on the shelf: nothing to be found, so not enough samples
    assert (hot["badge"], hot["true_units"], hot["frames"], hot["confused_as"]) == ("insufficient", 0, 0, None)


def _frames_of_original_read_as_cheese(days: tuple[str, ...], per_day: int) -> list[dict]:
    """Frames of the 23/11 evening story: 3 real Original cans, all called Cheese; the model never says Original."""
    boxes = [{"box_id": b, "sku_id": "cheese145", "conf": 0.93, "box": [b * 9, 0, 5, 5]} for b in (1, 2, 3)]
    verdicts = [{"box_id": b, "verdict": "wrong_sku", "true_sku_id": "original145"} for b in (1, 2, 3)]
    return [
        {
            "store_id": "S1",
            "capture_timestamp": f"2026-11-{day}T1{i % 10}:10:00+07:00",
            "ai_boxes": boxes,
            "verdicts": verdicts,
            "missed": [],
        }
        for day in days
        for i in range(per_day)
    ]


def test_a_sku_the_model_never_names_is_low_not_insufficient():
    audits = _frames_of_original_read_as_cheese(("23", "24"), 6)  # 12 frames on 2 days, 36 real Original cans
    original = sku_reliability(audits)["original145"]
    # found right 0 of 36: enough samples, and named right has no interval (no box was ever named Original)
    assert (original["badge"], original["found_right"], original["named_right"]) == ("low", 0.0, None)
    assert (original["true_units"], original["frames"], original["confused_as"]) == (36, 12, "cheese145")
    row = next(r for r in summarize(audits, [])["per_sku"] if r["sku_id"] == "original145")
    assert (row["badge"], row["enough"]) == ("low", True)
    assert (row["id_accuracy_ci"], row["found_right_ci"]) == (None, [0.0, 0.0])
    # Cheese was called 36 times but never really there: nothing to be found, so not enough samples
    assert sku_reliability(audits)["cheese145"]["badge"] == "insufficient"


def test_sku_reliability_is_insufficient_on_one_day_and_without_audits():
    one_day = sku_reliability(_frames_of_cheese(("22",), 12))["cheese145"]
    assert one_day["badge"] == "insufficient" and one_day["true_units"] == 36  # n is still given
    assert sku_reliability([]) == {}


def test_per_sku_rows_carry_a_badge():
    rows = {r["sku_id"]: r for r in summarize(_frames_of_cheese(("22", "23"), 6), [])["per_sku"]}
    assert rows["cheese145"]["badge"] == sku_reliability(_frames_of_cheese(("22", "23"), 6))["cheese145"]["badge"]


def test_sku_reliability_of_14_days_is_quick():
    audits = _frames_of_cheese(tuple(f"{d:02d}" for d in range(10, 24)), 16)  # 14 days x 16 frames
    start = time.perf_counter()
    sku_reliability(audits)
    assert time.perf_counter() - start < 1.0
