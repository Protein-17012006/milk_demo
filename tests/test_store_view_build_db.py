"""Crops for the milk database and its similarity threshold (training/store_view/build_db.py)."""

import pytest

from training.store_view.build_db import crop_jobs, is_negative, pick_threshold

SEGMENTS = [
    {"id": "seg-0001", "kind": "day", "split": "train", "members": ["A1", "A2", "A3"]},
    {"id": "seg-0002", "kind": "day", "split": "holdout", "members": ["H1"]},
    {"id": "seg-0003", "kind": "negative", "split": "train", "members": ["N1"]},
]


def labels(tmp_path):
    for cid in ("A1", "A2", "A3", "H1"):
        (tmp_path / f"{cid}.txt").write_text("0 0.318359 0.090278 0.011719 0.041667\n")
    (tmp_path / "N1.txt").write_text("")
    return tmp_path


def test_crop_jobs_list_each_labelled_carton_of_the_part(tmp_path):
    jobs = crop_jobs(SEGMENTS, labels(tmp_path), "train", share=0.0, per_segment=2)
    assert jobs == [("A1", [800, 100, 30, 60]), ("A3", [800, 100, 30, 60])]


def test_crop_jobs_never_touch_held_out_frames(tmp_path):
    folder = labels(tmp_path)
    for part in ("train", "val"):
        assert all(cid != "H1" for cid, _ in crop_jobs(SEGMENTS, folder, part, share=0.5))
    with pytest.raises(ValueError):
        crop_jobs(SEGMENTS, folder, "holdout")


def test_pick_threshold_keeps_98_percent_of_positives():
    pos = [0.90 + k / 100 for k in range(10)]
    neg = [0.50 + k / 100 for k in range(36)]  # up to 0.85
    t = pick_threshold(pos)
    assert 0.85 < t <= 0.90
    assert all(n < t for n in neg)


def test_pick_threshold_rejects_at_most_2_percent_of_positives():
    pos = [0.80 + k * 0.19 / 49 for k in range(50)]
    t = pick_threshold(pos)
    assert sum(p >= t for p in pos) == 49  # 1 of 50 may go: the highest threshold that still keeps 98%


def test_a_detection_on_a_labelled_carton_is_not_a_negative():
    labelled = [[800, 100, 30, 60]]  # x, y, w, h
    assert not is_negative([802, 105, 828, 150], labelled)  # x0, y0, x1, y1: its centre lies in the carton
    assert is_negative([900, 100, 930, 160], labelled)
    assert is_negative([802, 105, 828, 150], [])  # a negative frame: every detection is a mistake


def test_pick_threshold_needs_positives():
    with pytest.raises(ValueError):
        pick_threshold([])
