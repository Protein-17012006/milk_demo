"""Review frames on the Model page for the cans the auto-labeller left to people, and their decisions back
(training/store_view/auto_label_review.py)."""

import json

from training.store_view.auto_label import Decision, Track
from training.store_view.auto_label_review import audit_id, pick_frame, review_boxes, review_file, review_item
from training.store_view.proposers import Proposal

FRAMES = ["F1", "F2", "F3"]


def track(tid, box, frames, sku=None):
    t = Track(tid, box)
    for f in frames:
        t.seen[f] = {"A": Proposal("A", box, 0.9, sku)} if sku else {"B": Proposal("B", box, 0.8, None)}
    return t


def proposal():
    tracks = [
        track("s-t0", (10.0, 10.0, 20.0, 40.0), FRAMES, "cheese145"),
        track("s-t1", (40.0, 10.0, 20.0, 40.0), ["F2", "F3"]),
        track("s-t2", (70.0, 10.0, 20.0, 40.0), FRAMES),
    ]
    return {"segment": "s", "keyframe": "F1", "split": "train", "frames": FRAMES, "tracks": tracks}


DECISIONS = {
    "s-t0": Decision("accept", "cheese145", "agree"),
    "s-t1": Decision("review", None, "no_A_flavour"),
    "s-t2": Decision("review", None, "waits:r-t9"),
}


def test_audit_id_names_the_camera_and_segment():
    assert audit_id("CAM-S01-A", "seg-0090") == "REV-CAM-S01-A-seg-0090"


def test_pick_frame_prefers_the_frame_showing_the_most_cans_to_review():
    assert pick_frame(proposal(), ["s-t1"]) == "F2"


def test_pick_frame_takes_the_frame_nearest_the_middle_on_a_tie():
    assert pick_frame(proposal(), ["s-t0"]) == "F2"


def test_review_boxes_show_accepted_cans_with_their_flavour_and_review_cans_without():
    boxes, verdicts = review_boxes(proposal(), DECISIONS, ["s-t1"], "F2")
    assert boxes == [
        {"box_id": 1, "track_id": "s-t0", "sku_id": "cheese145", "conf": 1.0, "box": [10, 10, 20, 40]},
        {"box_id": 2, "track_id": "s-t1", "sku_id": None, "conf": 0.0, "box": [40, 10, 20, 40], "needs_flavour": True},
    ]
    assert verdicts == [{"box_id": 1, "verdict": "correct"}]


def test_a_can_not_seen_in_the_chosen_frame_gets_no_box():
    boxes, _ = review_boxes(proposal(), DECISIONS, ["s-t1"], "F1")
    assert [b["track_id"] for b in boxes] == ["s-t0"]


def test_review_item_is_a_pending_review_audit_of_that_segment():
    row = {"capture_id": "F2", "capture_timestamp": "2026-11-24T10:00:00+07:00"}
    item = review_item(proposal(), DECISIONS, ["s-t1"], "CAM-S01-A", row, "audits/frames/x.jpg", "auto-label v")
    assert item["audit_id"] == "REV-CAM-S01-A-s" and item["store_id"] == "DEMO-S01"
    assert item["purpose"] == "review" and item["status"] == "pending" and item["segment_id"] == "s"
    assert item["capture_id"] == "F2" and item["image_key"] == "audits/frames/x.jpg"
    assert [b["track_id"] for b in json.loads(item["ai_boxes_json"])] == ["s-t0", "s-t1"]
    assert json.loads(item["verdicts_json"]) == [{"box_id": 1, "verdict": "correct"}]
    assert item["missed_json"] == "[]"


def done(aid, verdicts, missed=(), status="done"):
    boxes = [
        {"box_id": 1, "track_id": "s-t0", "sku_id": "cheese145", "conf": 1.0, "box": [10, 10, 20, 40]},
        {"box_id": 2, "track_id": "s-t1", "sku_id": None, "conf": 0.0, "box": [40, 10, 20, 40], "needs_flavour": True},
        {"box_id": 3, "track_id": "s-t3", "sku_id": None, "conf": 0.0, "box": [70, 10, 20, 40], "needs_flavour": True},
    ]
    return {
        "audit_id": aid,
        "segment_id": aid.removeprefix("REV-CAM-S01-A-"),
        "status": status,
        "ai_boxes_json": json.dumps(boxes),
        "verdicts_json": json.dumps(verdicts),
        "missed_json": json.dumps(list(missed)),
    }


def test_review_file_turns_verdicts_into_track_decisions():
    audits = [
        done(
            "REV-CAM-S01-A-s",
            [
                {"box_id": 1, "verdict": "correct"},
                {"box_id": 2, "verdict": "wrong_sku", "true_sku_id": "hot160"},
                {"box_id": 3, "verdict": "out_of_scope"},
            ],
            [{"sku_id": "hot160", "x": 5, "y": 6}],
        )
    ]
    assert review_file(audits) == {
        "s": {
            "tracks": {
                "s-t0": {"verdict": "sku", "sku": "cheese145"},
                "s-t1": {"verdict": "sku", "sku": "hot160"},
                "s-t3": {"verdict": "out_of_scope"},
            },
            "missed": [[5, 6]],
        }
    }


def test_review_file_skips_pending_and_non_review_audits():
    audits = [
        done("REV-CAM-S01-A-s", [{"box_id": 2, "verdict": "not_product"}], status="pending"),
        {**done("TRN-CAM-S01-A-20261124-10", [{"box_id": 1, "verdict": "correct"}]), "segment_id": "x"},
    ]
    assert review_file(audits) == {}


def test_review_file_keeps_a_segment_no_longer_in_the_queue():
    # it reads only the audits: a segment the queue would now resolve still gives the decision a person made
    got = review_file([done("REV-CAM-S01-A-old", [{"box_id": 2, "verdict": "not_product"}])])
    assert got == {"old": {"tracks": {"s-t1": {"verdict": "not_product"}}, "missed": []}}
