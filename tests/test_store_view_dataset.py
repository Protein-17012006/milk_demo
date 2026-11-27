"""The training set: real frames cut into native-size windows plus Long's synthetic set (training/store_view/dataset.py)."""

import json
import random

import cv2
import numpy as np
import pytest

from training.store_view.dataset import (
    GHOST,
    NAMES,
    assign,
    build,
    clip_to_window,
    frame_samples,
    remap_synthetic,
    scoring_frames,
    val_segments,
    windows,
)


def _manifest(frames, rows):
    (frames / "manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_eleven_classes_th_first():
    assert len(NAMES) == 11 and NAMES[0] == "th_true_milk" and NAMES[-1] == "vinamilk_9_seeds"


def test_remap_merges_the_two_th_classes():
    assert remap_synthetic(0) == remap_synthetic(1) == 0
    assert remap_synthetic(2) == 1  # vinamilk_banana
    assert remap_synthetic(11) == 10  # vinamilk_9_seeds


def test_windows_cover_a_2560x1440_frame_at_native_size():
    wins = windows(2560, 1440)
    assert all((x1 - x0, y1 - y0) == (1280, 1280) for x0, y0, x1, y1 in wins)
    for px in range(0, 2560, 37):
        for py in range(0, 1440, 41):
            assert any(x0 <= px < x1 and y0 <= py < y1 for x0, y0, x1, y1 in wins)


def test_clip_keeps_70_percent_inside_and_drops_50():
    window = (0, 0, 100, 100)
    assert clip_to_window([[80, 10, 20, 10]], window) == [[80, 10, 20, 10]]
    assert clip_to_window([[86, 10, 20, 10]], window) == [[86, 10, 14, 10]]
    assert clip_to_window([[90, 10, 20, 10]], window) == []


def test_clip_gives_window_coordinates():
    assert clip_to_window([[120, 60, 10, 10]], (100, 50, 200, 150)) == [[20, 10, 10, 10]]


def test_val_is_stable_and_about_the_share():
    ids = [f"seg-{n:04d}" for n in range(1000)]
    chosen = val_segments(ids, share=0.1)
    assert chosen == val_segments(ids, share=0.1)
    assert 50 <= len(chosen) <= 150


def test_holdout_segments_never_reach_train_or_val():
    segments = [
        {"id": "seg-0001", "kind": "day", "split": "train", "members": ["A1", "A2"]},
        {"id": "seg-0002", "kind": "day", "split": "holdout", "members": ["H1", "H2"]},
        {"id": "seg-0003", "kind": "negative", "split": "holdout", "members": ["H3"]},
        {"id": "seg-0004", "kind": "transient", "split": "train", "members": ["T1"]},
        {"id": "seg-0005", "kind": "negative", "split": "train", "members": ["N1"]},
    ]
    parts = assign(segments, share=0.0)
    assert parts == {"A1": "train", "A2": "train", "N1": "train"}


def test_frames_never_to_train_on_get_no_part_even_in_a_training_segment():
    segments = [{"id": "seg-0001", "kind": "day", "split": "train", "members": ["A1", "A2", "A3"]}]
    parts = assign(segments, share=0.0, never={"A2"})
    assert parts == {"A1": "train", "A3": "train"}


def test_scoring_frames_are_those_with_an_aud_audit():
    rows = [
        {"capture_id": "C1", "audit_ids": ["AUD-CAM-S01-A-20261124-08"]},
        {"capture_id": "C2", "audit_ids": ["TRN-CAM-S01-A-20261124-12"]},
        {"capture_id": "C3", "audit_ids": []},
        {"capture_id": "C4"},
        {"capture_id": "C5", "audit_ids": ["TRN-CAM-S01-A-20261124-13", "AUD-CAM-S01-A-20261124-13"]},
    ]
    assert scoring_frames(rows) == {"C1", "C5"}


def test_val_is_chosen_by_segment():
    segments = [
        {"id": f"seg-{n:04d}", "kind": "day", "split": "train", "members": [f"F{n}a", f"F{n}b"]} for n in range(200)
    ]
    parts = assign(segments, share=0.2)
    assert any(p == "val" for p in parts.values())
    for n in range(200):
        assert parts[f"F{n}a"] == parts[f"F{n}b"]


def test_frames_of_another_size_than_their_keyframe_are_skipped():
    samples = frame_samples((1920, 1080), (2560, 1440), [[800, 100, 30, 60]], 1, random.Random(0))
    assert samples == []


def test_a_labelled_frame_gives_every_window_with_a_carton_plus_one_without():
    samples = frame_samples((2560, 1440), (2560, 1440), [[800, 200, 30, 60]], 1, random.Random(0))
    with_th = [s for s in samples if s[1]]
    without = [s for s in samples if not s[1]]
    assert sorted(w[:2] for w, _ in with_th) == [(0, 0), (0, 160)]  # (896, ...) do not reach x = 800
    assert len(without) == 1
    ((window, _),) = without
    assert window[0] > 830 or window[2] < 800  # a negative window shows no part of the carton


def test_a_negative_frame_always_shows_the_freezer_gap():
    samples = frame_samples((2560, 1440), (2560, 1440), [], 2, random.Random(0))
    assert len(samples) == 2 and all(not boxes for _, boxes in samples)
    gx, gy, gw, gh = GHOST
    assert any(x0 <= gx and y0 <= gy and x1 >= gx + gw and y1 >= gy + gh for (x0, y0, x1, y1), _ in samples)


def test_build_writes_a_yolo_dataset(tmp_path):
    frames, labels, synth, out = tmp_path / "frames", tmp_path / "labels", tmp_path / "synth", tmp_path / "out"
    (frames / "2026-11-24").mkdir(parents=True)
    cv2.imwrite(str(frames / "2026-11-24" / "K.jpg"), np.zeros((1440, 2560, 3), np.uint8))
    labels.mkdir()
    (labels / "K.txt").write_text("0 0.318359 0.090278 0.011719 0.041667\n")
    for part in ("train", "val"):
        (synth / "images" / part).mkdir(parents=True)
        (synth / "labels" / part).mkdir(parents=True)
        cv2.imwrite(str(synth / "images" / part / f"s_{part}.jpg"), np.zeros((108, 192, 3), np.uint8))
        (synth / "labels" / part / f"s_{part}.txt").write_text("1 0.5 0.5 0.1 0.2\n7 0.2 0.2 0.1 0.1\n")
    _manifest(frames, [{"capture_id": "K", "audit_ids": []}])
    segments = [
        {"id": "seg-0001", "kind": "day", "split": "train", "keyframe": "K", "members": ["K"], "first_ts": "x"},
    ]
    build(segments, frames, labels, synth, out, share=0.0, per_segment=60, seed=0)
    assert (out / "data.yaml").read_text().split("names:\n")[1].splitlines()[0] == "  0: th_true_milk"
    real = sorted(p.name for p in (out / "labels" / "train").glob("real_*.txt"))
    assert real and all((out / "images" / "train" / name.replace(".txt", ".jpg")).is_file() for name in real)
    assert (out / "labels" / "train" / "synth_s_train.txt").read_text().splitlines() == [
        "0 0.5 0.5 0.1 0.2",
        "6 0.2 0.2 0.1 0.1",
    ]
    assert (out / "labels" / "val" / "synth_s_val.txt").is_file()
    assert all((out / f"val_L{k}.txt").is_file() for k in range(1, 6))


def _real_frame_and_synth(tmp_path, names):
    frames, labels, synth = tmp_path / "frames", tmp_path / "labels", tmp_path / "synth"
    (frames / "2026-11-24").mkdir(parents=True)
    labels.mkdir()
    for name in names:
        cv2.imwrite(str(frames / "2026-11-24" / f"{name}.jpg"), np.zeros((1440, 2560, 3), np.uint8))
        (labels / f"{name}.txt").write_text("0 0.318359 0.090278 0.011719 0.041667\n")
    for part in ("train", "val"):
        (synth / "images" / part).mkdir(parents=True)
        (synth / "labels" / part).mkdir(parents=True)
    return frames, labels, synth


def test_build_never_cuts_a_scoring_frame_but_keeps_a_training_frame(tmp_path):
    frames, labels, synth = _real_frame_and_synth(tmp_path, ["S", "T"])
    _manifest(
        frames,
        [
            {"capture_id": "S", "audit_ids": ["AUD-CAM-S01-A-20261124-08"]},
            {"capture_id": "T", "audit_ids": ["TRN-CAM-S01-A-20261124-12"]},
        ],
    )
    segments = [{"id": "seg-0001", "kind": "day", "split": "train", "keyframe": "S", "members": ["S", "T"]}]
    counts = build(segments, frames, labels, synth, tmp_path / "out", share=0.0, per_segment=60, seed=0)
    cut = {p.name.split("_")[1] for p in (tmp_path / "out" / "images" / "train").glob("real_*.jpg")}
    assert cut == {"T"}
    assert counts["skipped_scoring"] == 1


def test_build_refuses_to_run_without_the_manifest(tmp_path):
    frames, labels, synth = _real_frame_and_synth(tmp_path, ["T"])
    segments = [{"id": "seg-0001", "kind": "day", "split": "train", "keyframe": "T", "members": ["T"]}]
    with pytest.raises(FileNotFoundError, match="manifest"):
        build(segments, frames, labels, synth, tmp_path / "out", share=0.0, per_segment=60, seed=0)
