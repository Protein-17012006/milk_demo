"""Scoring the counting path on held-out frames, and the gate before going live (training/store_view/evaluate.py)."""

from milk.cvoutput import Detection
from training.store_view.evaluate import frame_result, gate, match, summarize


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
