"""People's decisions, YOLO labels and grey masks of the auto-labeller (training/store_view/auto_label_labels.py)."""

import cv2
import numpy as np
import pytest

from training.store_view.auto_label import Decision, Track
from training.store_view.auto_label_labels import apply_review, frame_labels, write_segment
from training.store_view.proposers import Proposal

CLASSES = ["cheese145", "hot160", "original145", "sourcream150"]


def can(tid, frames, box=(1000, 300, 70, 160), median=(990, 300, 70, 160)):
    t = Track(tid, median)
    for cid in frames:
        t.seen[cid] = {"A": Proposal("A", box, 0.9, "cheese145")}
    return t


def test_an_accepted_can_is_written_with_its_own_box_in_that_frame():
    t = can("s-t0", ["C1"])
    lines, masks = frame_labels("C1", [t], {"s-t0": Decision("accept", "cheese145", "agree")}, CLASSES, [])
    assert lines == ["0 0.404297 0.263889 0.027344 0.111111"] and masks == []


def test_a_frame_where_the_can_is_hidden_masks_it_instead_of_labelling():
    t = can("s-t0", ["C1"])
    lines, masks = frame_labels("C2", [t], {"s-t0": Decision("accept", "cheese145", "agree")}, CLASSES, [])
    assert lines == [] and masks == [(990, 300, 70, 160)]


def test_review_and_out_of_scope_are_masked_never_labelled():
    a, b, c = can("s-t0", ["C1"]), can("s-t1", ["C1"], box=(1200, 300, 70, 160)), can("s-t2", ["C1"], box=(1300, 1, 9, 9))
    decisions = {
        "s-t0": Decision("review", None, "disagree"),
        "s-t1": Decision("masked", None, "out_of_scope"),
        "s-t2": Decision("drop", None, "ghost"),
    }
    lines, masks = frame_labels("C1", [a, b, c], decisions, CLASSES, [])
    assert lines == [] and masks == [(1000, 300, 70, 160), (1200, 300, 70, 160)]


def test_review_file_turns_a_track_into_the_chosen_flavour():
    decisions = {
        "s-t0": Decision("review", None, "disagree"),
        "s-t1": Decision("review", None, "only_A"),
        "s-t2": Decision("review", None, "no_A_flavour"),
        "s-t3": Decision("accept", "cheese145", "agree"),
    }
    review = {
        "tracks": {
            "s-t0": {"verdict": "sku", "sku": "original145"},
            "s-t1": {"verdict": "not_product"},
            "s-t2": {"verdict": "out_of_scope"},
        },
        "missed": [],
    }
    out = apply_review(decisions, review)
    assert out["s-t0"] == Decision("accept", "original145", "human")
    assert out["s-t1"].status == "drop"
    assert out["s-t2"] == Decision("masked", None, "out_of_scope")
    assert out["s-t3"] == decisions["s-t3"]


def test_missed_points_are_masked():
    _, masks = frame_labels("C1", [], {}, CLASSES, [[1200, 400]], mask_radius=40)
    assert masks == [(1160, 360, 80, 80)]


def test_a_flavour_outside_the_classes_is_an_error():
    with pytest.raises(ValueError):
        frame_labels("C1", [can("s-t0", ["C1"])], {"s-t0": Decision("accept", "pepsi", "human")}, CLASSES, [])


def test_write_segment_skips_scoring_and_holdout_frames(tmp_path):
    paths = {}
    for cid in ("C1", "C2"):
        p = tmp_path / f"{cid}.jpg"
        cv2.imwrite(str(p), np.full((1440, 2560, 3), 200, np.uint8))
        paths[cid] = p
    tracks = [can("s-t0", ["C1", "C2"]), can("s-t1", ["C2"], box=(1200, 300, 70, 160), median=(1200, 300, 70, 160))]
    decisions = {"s-t0": Decision("accept", "cheese145", "agree"), "s-t1": Decision("review", None, "disagree")}
    train = {"id": "s", "split": "train"}
    counts = write_segment(train, ["C1", "C2"], paths, tracks, decisions, CLASSES, [], tmp_path / "out", never={"C1"})
    assert counts["written"] == 1 and counts["skipped_scoring"] == 1
    assert not (tmp_path / "out" / "labels" / "C1.txt").exists()
    assert (tmp_path / "out" / "labels" / "C2.txt").read_text().startswith("0 ")
    img = cv2.imread(str(tmp_path / "out" / "images" / "C2.jpg"))
    assert abs(int(img[380, 1235, 0]) - 127) <= 3 and abs(int(img[380, 1035, 0]) - 200) <= 3  # masked vs labelled
    held = write_segment({"id": "h", "split": "holdout"}, ["C2"], paths, tracks, decisions, CLASSES, [], tmp_path / "o2")
    assert held["skipped_holdout"] == 1 and not (tmp_path / "o2").exists()
