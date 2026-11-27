"""The live release against a candidate on the same frames (operations-loop design 5.2).

Boxes are x, y, w, h in frame pixels. Every expected value was worked out by hand from the boxes below."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import compare  # noqa: E402
import model_health  # noqa: E402
from audit_scoring import comparison_rows, frame_tallies  # noqa: E402


def box(box_id, sku, conf, xywh):
    return {"box_id": box_id, "sku_id": sku, "conf": conf, "box": xywh}


LIVE = [box(1, "original145", 0.9, [100, 100, 60, 120]), box(2, "cheese145", 0.8, [300, 100, 60, 120])]
CAND = [
    box(1, "original145", 0.7, [104, 102, 60, 120]),
    box(2, "hot160", 0.9, [302, 98, 60, 120]),
    box(3, "cheese145", 0.6, [500, 100, 60, 120]),
]


def merged_audit(live, cand, verdicts, missed=()):
    return {
        "audit_id": "AUD-CAM-S01-A-20261127-10",
        "capture_timestamp": "2026-11-27T10:05:00+07:00",
        "model_version": "v1",
        "candidate_version": "v2",
        "status": "done",
        "ai_boxes": compare.merge_boxes(live, cand),
        "verdicts": [
            {"box_id": box_id, "verdict": verdict, **({"true_sku_id": true} if true else {})}
            for box_id, (verdict, true) in verdicts.items()
        ],
        "missed": list(missed),
    }


def verdicts_of(audit):
    return {v["box_id"]: v["verdict"] for v in audit["verdicts"]}


def test_merge_pairs_one_to_one_and_hides_disputed_names():
    merged = compare.merge_boxes(LIVE, CAND)
    assert [(b["src"], b["sku_id"], b["needs_flavour"]) for b in merged] == [
        ("both", "original145", False),
        ("both", None, True),
        ("cand", None, True),
    ]
    assert [b["box"] for b in merged][:2] == [[100, 100, 60, 120], [300, 100, 60, 120]]
    assert (merged[1]["live_sku"], merged[1]["cand_sku"]) == ("cheese145", "hot160")
    assert [b["box_id"] for b in merged] == [1, 2, 3]


def test_two_candidate_boxes_on_one_can_leave_one_unpaired():
    cand = [box(1, "original145", 0.9, [100, 100, 60, 120]), box(2, "original145", 0.5, [110, 104, 60, 120])]
    merged = compare.merge_boxes(LIVE[:1], cand)
    assert [b["src"] for b in merged] == ["both", "cand"]
    assert merged == compare.merge_boxes(LIVE[:1], list(reversed(cand)))


def test_a_candidate_box_across_two_live_boxes_pairs_with_one_only():
    live = [box(1, "hot160", 0.9, [100, 100, 60, 120]), box(2, "hot160", 0.8, [160, 100, 60, 120])]
    cand = [box(1, "hot160", 0.9, [125, 100, 70, 120])]  # covers 35 px of the first, 35 px of the second
    merged = compare.merge_boxes(live, cand)
    assert sorted(b["src"] for b in merged) == ["both", "live"]


def test_boxes_that_barely_touch_are_two_objects():
    live = [box(1, "hot160", 0.9, [100, 100, 60, 120])]
    cand = [box(1, "hot160", 0.9, [140, 100, 60, 120])]  # shares 20 of 60 px: a third, under SAME_PLACE
    assert [b["src"] for b in compare.merge_boxes(live, cand)] == ["live", "cand"]


def test_merged_boxes_are_numbered_top_to_bottom_then_left_to_right():
    live = [box(1, "hot160", 0.9, [400, 300, 60, 120]), box(2, "hot160", 0.8, [100, 300, 60, 120])]
    cand = [box(1, "hot160", 0.9, [250, 50, 60, 120])]
    merged = compare.merge_boxes(live, cand)
    assert [(b["box_id"], b["box"][0]) for b in merged] == [(1, 250), (2, 100), (3, 400)]


def test_differs_only_when_a_box_is_disputed():
    assert compare.differs(compare.merge_boxes(LIVE, CAND))
    assert not compare.differs(compare.merge_boxes(LIVE, LIVE))
    assert not compare.differs(LIVE)


def test_capture_boxes_know_only_the_live_release():
    item = {
        "detections_json": json.dumps([{"sku_id": "original145", "conf": 0.9, "box": [1, 2, 3, 4]}]),
        "candidate_version": "v2",
        "candidate_detections_json": json.dumps([{"sku_id": "hot160", "conf": 0.9, "box": [50, 60, 30, 40]}]),
    }
    assert model_health.capture_boxes(item) == [
        {"box_id": 1, "sku_id": "original145", "conf": 0.9, "box": [1, 2, 3, 4]}
    ]


def test_frame_boxes_merge_only_for_the_candidate_running_in_parallel():
    item = {
        "detections_json": json.dumps([{"sku_id": "original145", "conf": 0.9, "box": [100, 100, 60, 120]}]),
        "candidate_version": "v2",
        "candidate_detections_json": json.dumps([{"sku_id": "hot160", "conf": 0.9, "box": [100, 100, 60, 120]}]),
    }
    assert [b["src"] for b in compare.frame_boxes(item, "v2")] == ["both"]
    assert compare.frame_boxes(item, "v3") == model_health.capture_boxes(item)
    assert compare.frame_boxes(item, None) == model_health.capture_boxes(item)


def test_a_capture_the_candidate_never_read_gives_the_live_boxes():
    item = {"detections_json": json.dumps([{"sku_id": "original145", "conf": 0.9, "box": [1, 2, 3, 4]}])}
    assert compare.frame_boxes(item, "v2") == [{"box_id": 1, "sku_id": "original145", "conf": 0.9, "box": [1, 2, 3, 4]}]


def test_a_candidate_that_saw_nothing_disputes_every_live_box():
    item = {
        "detections_json": json.dumps([{"sku_id": "original145", "conf": 0.9, "box": [100, 100, 60, 120]}]),
        "candidate_version": "v2",
        "candidate_detections_json": "[]",
    }
    assert [(b["src"], b["needs_flavour"]) for b in compare.frame_boxes(item, "v2")] == [("live", True)]


def test_public_boxes_carry_nothing_about_who_drew_them():
    public = compare.public_boxes(compare.merge_boxes(LIVE, CAND))
    assert [sorted(b) for b in public] == [["box", "box_id", "conf", "needs_flavour", "sku_id"]] * 3
    assert [b["sku_id"] for b in public] == ["original145", None, None]


def test_split_audit_gives_each_side_its_own_verdicts():
    audit = merged_audit(
        LIVE, CAND, verdicts={1: ("correct", None), 2: ("wrong_sku", "hot160"), 3: ("wrong_sku", "cheese145")}
    )
    live, cand = compare.split_audit(audit)
    assert verdicts_of(live) == {1: "correct", 2: "wrong_sku"}
    assert [m["sku_id"] for m in live["missed"]] == ["cheese145"]
    assert (live["missed"][0]["x"], live["missed"][0]["y"]) == (530, 160)
    assert verdicts_of(cand) == {1: "correct", 2: "correct", 3: "correct"}
    assert cand["missed"] == []
    assert [b["sku_id"] for b in live["ai_boxes"]] == ["original145", "cheese145"]
    assert [b["sku_id"] for b in cand["ai_boxes"]] == ["original145", "hot160", "cheese145"]
    assert (live["model_version"], cand["model_version"]) == ("v1", "v2")


def test_split_audit_keeps_not_product_and_out_of_scope_for_the_side_that_drew_the_box():
    audit = merged_audit(
        LIVE, CAND, verdicts={1: ("correct", None), 2: ("not_product", None), 3: ("out_of_scope", None)}
    )
    live, cand = compare.split_audit(audit)
    assert verdicts_of(live) == {1: "correct", 2: "not_product"}
    assert verdicts_of(cand) == {1: "correct", 2: "not_product", 3: "out_of_scope"}
    assert live["missed"] == [] and cand["missed"] == []


def test_split_audit_keeps_the_misses_a_person_marked_for_both_sides():
    missed = [{"sku_id": "hot160", "x": 900, "y": 400}]
    audit = merged_audit(LIVE, LIVE, verdicts={1: ("correct", None), 2: ("correct", None)}, missed=missed)
    live, cand = compare.split_audit(audit)
    assert live["missed"] == missed and cand["missed"] == missed


def test_split_audit_of_a_frame_without_a_candidate_is_the_frame_itself():
    audit = {"audit_id": "AUD-x", "ai_boxes": LIVE, "verdicts": [{"box_id": 1, "verdict": "correct"}], "missed": []}
    live, cand = compare.split_audit(audit)
    assert live is audit and cand is None


def test_an_unlabelled_merged_frame_splits_into_boxes_without_verdicts():
    audit = {**merged_audit(LIVE, CAND, verdicts={}), "status": "pending"}
    live, cand = compare.split_audit(audit)
    assert (live["verdicts"], cand["verdicts"]) == ([], [])
    assert (len(live["ai_boxes"]), len(cand["ai_boxes"])) == (2, 3)


def test_the_live_side_of_an_undisputed_frame_scores_like_the_frame_did_before():
    verdicts = [
        {"box_id": 1, "verdict": "correct"},
        {"box_id": 2, "verdict": "wrong_sku", "true_sku_id": "original145"},
    ]
    missed = [{"sku_id": "hot160", "x": 900, "y": 400}]
    classic = {
        "audit_id": "AUD-CAM-S01-A-20261127-10",
        "capture_timestamp": "2026-11-27T10:05:00+07:00",
        "ai_boxes": LIVE,
        "verdicts": verdicts,
        "missed": missed,
    }
    merged = {**classic, "candidate_version": "v2", "ai_boxes": compare.merge_boxes(LIVE, LIVE)}
    live, _cand = compare.split_audit(merged)
    assert comparison_rows(live) == comparison_rows(classic)
    assert frame_tallies(live) == frame_tallies(classic)
