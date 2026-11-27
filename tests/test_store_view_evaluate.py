"""Scoring the counting path on held-out frames, and the gate before going live (training/store_view/evaluate.py)."""

import os

from milk.cvoutput import Detection
from training.store_view.evaluate import apply_env, frame_result, gate, in_window, match, night, summarize


def test_centre_inside_matches():
    assert match([([10, 10, 20, 20], 0.9)], [[5, 5, 30, 30]]) == (1, 0, 0)
    assert match([([40, 40, 20, 20], 0.9)], [[5, 5, 30, 30]]) == (0, 1, 1)


def test_one_truth_box_matches_one_model_box():
    assert match([([10, 10, 20, 20], 0.9), ([12, 12, 20, 20], 0.8)], [[5, 5, 30, 30]]) == (1, 1, 0)


def test_the_more_confident_box_takes_a_shared_carton():
    # both boxes sit in carton A; only the sure one may take it, the other stays unmatched even though B is near
    truth = [[0, 0, 30, 30], [30, 0, 30, 30]]
    assert match([([5, 5, 20, 20], 0.6), ([8, 5, 20, 20], 0.95)], truth) == (1, 1, 1)


def th(box, conf=0.9):
    return Detection("TMP-MLK-TH-00", "TH", conf, tuple(box))


def test_precision_counts_every_milk_label_but_unrecognized():
    detections = [
        th([10, 10, 20, 20]),
        Detection("TMP-MLK-VNM-03", "VNM", 0.8, (100, 100, 20, 20)),
        Detection(None, None, 0.0, (200, 200, 20, 20)),  # unrecognised: not counted as milk
        Detection("cheese145", "Slide", 0.9, (300, 300, 20, 20)),  # Slide: not milk
    ]
    result = frame_result("CAP-1", "seg-0001", detections, [[5, 5, 30, 30]])
    assert (result["tp"], result["fp"], result["fn"]) == (1, 1, 0)
    assert result["count_error"] == 0
    assert summarize([result])["frames"]["precision"] == 0.5


def test_a_vinamilk_name_on_a_th_carton_is_a_miss_and_a_false_box():
    result = frame_result(
        "CAP-1", "seg-0001", [Detection("TMP-MLK-VNM-03", "VNM", 0.8, (10, 10, 20, 20))], [[5, 5, 30, 30]]
    )
    assert (result["tp"], result["fp"], result["fn"], result["count_error"]) == (0, 1, 1, -1)


def test_boxes_on_negative_frames_are_counted_per_100():
    quiet = [frame_result(f"N{k}", "seg-0009", [], []) for k in range(99)]
    noisy = frame_result("N99", "seg-0009", [th([0, 0, 10, 10]), th([50, 50, 10, 10])], [])
    assert summarize(quiet + [noisy])["frames"]["negatives_per_100"] == 2.0


def test_count_within_1_looks_only_at_frames_with_th():
    good = frame_result("A", "seg-0001", [th([0, 0, 10, 10])], [[0, 0, 10, 10], [20, 0, 10, 10]])  # off by 1
    bad = frame_result("B", "seg-0001", [], [[0, 0, 10, 10], [20, 0, 10, 10]])  # off by 2
    empty = frame_result("C", "seg-0002", [], [])
    assert summarize([good, bad, empty])["frames"]["count_within_1"] == 0.5


def test_segment_view_gives_each_segment_one_vote():
    long_run = [frame_result(f"A{k}", "seg-0001", [th([0, 0, 10, 10])], [[0, 0, 10, 10]]) for k in range(9)]
    short_run = [frame_result("B0", "seg-0002", [], [[0, 0, 10, 10]])]
    summary = summarize(long_run + short_run)
    assert summary["frames"]["recall"] == 0.9
    assert summary["segments"]["recall"] == 0.5


def test_gate_lists_failures():
    ok = {"recall": 0.9, "precision": 0.95, "count_within_1": 0.85, "negatives_per_100": 0.5}
    assert gate({"frames": ok, "segments": ok}) == []
    weak = dict(ok, recall=0.8, negatives_per_100=3.0)
    assert gate({"frames": weak, "segments": ok}) == [
        "frames: recall 0.800 < 0.85",
        "frames: negatives_per_100 3.000 > 1.0",
    ]


def test_gate_fails_a_number_that_could_not_be_measured():
    missing = {"recall": None, "precision": 0.95, "count_within_1": 0.85, "negatives_per_100": 0.5}
    assert gate({"frames": missing, "segments": missing}) == [
        "frames: recall not measured",
        "segments: recall not measured",
    ]


def test_the_current_pipeline_does_not_inherit_the_new_ones_settings(monkeypatch):
    # every variable is set through monkeypatch first, so pytest restores it after apply_env changed it
    monkeypatch.setenv("MILK_LONG_TH_CONFIRM", "detector")
    monkeypatch.setenv("MILK_LONG_TILE", "1280")
    monkeypatch.setenv("MILK_SLIDE_CONF", "0.9")
    monkeypatch.delenv("NOT_A_MILK_SETTING", raising=False)
    apply_env({"MILK_SLIDE_CONF": "0.25", "NOT_A_MILK_SETTING": "x"}, {"MILK_LONG_TILE": "0"})
    assert "MILK_LONG_TH_CONFIRM" not in os.environ
    assert os.environ["MILK_LONG_TILE"] == "0" and os.environ["MILK_SLIDE_CONF"] == "0.25"
    assert "NOT_A_MILK_SETTING" not in os.environ


def test_since_keeps_segments_that_start_at_or_after_it():
    since = "2026-11-25T13:00:00+07:00"
    assert in_window("2026-11-25T13:00:00+07:00", since) and in_window("2026-11-26T06:00:00+07:00", since)
    assert not in_window("2026-11-25T12:59:59+07:00", since)
    assert in_window("2026-11-23T18:00:00+07:00", None)


def test_night_counts_milk_boxes_on_frames_without_the_display():
    rows = [{"kind": "negative", "milk": 0}] * 199 + [{"kind": "negative", "milk": 2}, {"kind": "day", "milk": 5}]
    assert night(rows) == {"frames": 200, "milk_boxes": 2, "per_100": 1.0}


def test_night_without_frames_is_not_measured():
    assert night([{"kind": "day", "milk": 1}]) == {"frames": 0, "milk_boxes": 0, "per_100": None}


def test_the_overlap_setting_is_cleared_between_pipelines(monkeypatch):
    monkeypatch.setenv("MILK_LONG_TH_OVERLAP", "0.5")
    apply_env({}, {})
    assert "MILK_LONG_TH_OVERLAP" not in os.environ


def test_a_box_whose_centre_lies_in_two_cartons_takes_the_nearer_one():
    # 26/11 14:10, arrangement F0: seven boxes on seven cartons. Boxes around slanted neighbours overlap, and the centre
    # of the box on the 4th carton also lies in the 3rd carton's box, which comes first in the list
    truth = [
        [832, 97, 34, 23],
        [853, 90, 35, 22],
        [846, 112, 34, 23],
        [866, 104, 35, 23],
        [859, 127, 35, 23],
        [880, 119, 25, 23],
        [872, 142, 35, 24],
    ]
    model = [
        ([832, 96, 32, 26], 0.94),
        ([857, 129, 30, 27], 0.94),
        ([851, 88, 32, 24], 0.93),
        ([863, 104, 30, 26], 0.93),
        ([845, 113, 29, 26], 0.93),
        ([870, 146, 30, 28], 0.91),
        ([874, 118, 33, 27], 0.91),
    ]
    assert match(model, truth) == (7, 0, 0)
