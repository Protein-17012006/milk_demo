"""Scoring of frames the team labelled on the Model page, against Datagent's Accuracy Report (spec section 5).

Every expected value below was worked out by hand from the boxes and verdicts in the fixture."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from audit_scoring import comparison_rows, summarize, validate_labels  # noqa: E402

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
    assert k["overall_identification_accuracy"] == {"value": None, "target": [">=", 0.6], "met": None, "n": 0}


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
