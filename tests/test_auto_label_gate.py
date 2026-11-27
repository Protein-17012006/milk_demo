"""Gate 1: the auto-labeller's decisions against the hand-drawn truth (training/store_view/auto_label_gate.py)."""

import numpy as np

from training.store_view.auto_label import Decision, Track
from training.store_view.auto_label_gate import GATE1, failures, score, simulate, truth_label
from training.store_view.proposers import Proposal

KEY = "K1"


def can(tid, box):
    t = Track(tid, box)
    t.seen[KEY] = {"B": Proposal("B", box, 0.8, None)}
    return t


def one(tracks, decisions, rows):
    return score({"s1": (tracks, decisions)}, {KEY: rows}, {"s1": KEY})


def test_an_accepted_can_on_a_lower_tier_truth_row_counts_as_real():
    s = one(
        [can("t0", (100, 500, 70, 160))],
        {"t0": Decision("accept", "cheese145", "agree")},
        [{"box": [95, 495, 80, 170], "sku": "unknown", "kind": "lower"}],
    )
    assert s["real"] == 1.0 and s["flavour"] is None


def test_an_accepted_box_where_no_truth_row_is_is_not_real():
    s = one(
        [can("t0", (900, 900, 50, 50))],
        {"t0": Decision("accept", "cheese145", "agree")},
        [{"box": [95, 495, 80, 170], "sku": "cheese145", "kind": "face"}],
    )
    assert s["real"] == 0.0 and s["coverage"] == 0.0


def test_flavour_ignores_rows_whose_flavour_is_unknown():
    rows = [
        {"box": [95, 495, 80, 170], "sku": "cheese145", "kind": "face"},
        {"box": [300, 100, 70, 40], "sku": "unknown", "kind": "ignore"},
    ]
    tracks = [can("t0", (100, 500, 70, 160)), can("t1", (305, 105, 60, 30))]
    decisions = {"t0": Decision("accept", "cheese145", "agree"), "t1": Decision("accept", "original145", "agree")}
    s = one(tracks, decisions, rows)
    assert s["real"] == 1.0 and s["flavour"] == 1.0


def test_coverage_counts_review_as_covered():
    rows = [
        {"box": [95, 495, 80, 170], "sku": "cheese145", "kind": "face"},
        {"box": [195, 495, 80, 170], "sku": "original145", "kind": "face"},
        {"box": [300, 100, 70, 40], "sku": "unknown", "kind": "ignore"},
    ]
    tracks = [can("t0", (100, 500, 70, 160)), can("t1", (200, 500, 70, 160))]
    decisions = {"t0": Decision("accept", "cheese145", "agree"), "t1": Decision("review", None, "disagree")}
    assert one(tracks, decisions, rows)["coverage"] == 1.0


def test_review_share_is_per_segment():
    t = can("t0", (100, 500, 70, 160))
    s = score(
        {
            "s1": ([t], {"t0": Decision("review", None, "disagree")}),
            "s2": ([t], {"t0": Decision("accept", "cheese145", "agree")}),
            "s3": ([t], {"t0": Decision("too_short", None, "too_short")}),
        },
        {},
        {},
    )
    assert s["review_share"] == 0.5


def test_failures_lists_each_metric_off_its_limit():
    assert set(GATE1) == {"real", "flavour", "coverage", "review_share", "reuse_right"}
    got = failures({"real": 0.95, "flavour": 0.99, "coverage": 0.90, "review_share": 0.5, "reuse_right": 0.9})
    assert len(got) == 4 and any("real" in f for f in got) and any("review_share" in f for f in got)
    assert any(f.startswith("reuse_right") for f in got)
    ok = {"real": None, "flavour": 1.0, "coverage": 1.0, "review_share": 0.0, "reuse_right": 1.0}
    assert failures(ok) == ["real not measured"]


ROW = {"box": [95, 495, 80, 170], "sku": "cheese145", "kind": "face"}
CAN = (100, 500, 70, 160)


def test_reused_and_human_accepts_are_not_counted_as_machine_accepts():
    for reason in ("reused:truth:K#0", "human"):
        s = one([can("t0", CAN)], {"t0": Decision("accept", "cheese145", reason)}, [ROW])
        assert s["real"] is None and s["coverage"] == 1.0


def test_masked_counts_as_covered():
    assert one([can("t0", CAN)], {"t0": Decision("masked", None, "out_of_scope")}, [ROW])["coverage"] == 1.0


def test_review_share_counts_only_segments_that_need_a_new_frame():
    t = can("t0", CAN)
    review = {"t0": Decision("review", None, "disagree")}
    s = score({"s1": ([t], review), "s2": ([t], review), "s3": ([t], review)}, {}, {}, new_frames={"s1"})
    assert s["review_share"] == 1 / 3


def test_truth_label_reads_flavour_unknown_and_nothing():
    rows = [ROW, {"box": [300, 100, 70, 40], "sku": "unknown", "kind": "ignore"}]
    assert truth_label(rows, CAN) == "cheese145"
    assert truth_label(rows, (305, 105, 60, 30)) == "out_of_scope"
    assert truth_label(rows, (900, 900, 50, 50)) == "not_product"


def tracked(seg, key, colour):
    t = Track(f"{seg}-t0", CAN)
    t.seen[key] = {"B": Proposal("B", CAN, 0.8, None)}
    t.colour = colour
    return {
        "segment": seg,
        "keyframe": key,
        "split": "holdout",
        "frames": [key],
        "tracks": [t],
        "decisions": {t.id: Decision("review", None, "disagree")},
    }


YELLOW = np.eye(144)[0]


def test_simulate_scores_a_wrong_reuse_as_wrong():
    rows_sour = [{**ROW, "sku": "sourcream150"}]
    s = simulate([tracked("s1", "K1", YELLOW), tracked("s2", "K2", YELLOW)], {"K1": rows_sour, "K2": [ROW]}, [], 0.95)
    assert s["reuse_right"] == 0.0 and s["counts"]["new_frames"] == 1 and s["counts"]["reused"] == 1


def test_simulate_scores_a_right_reuse_and_counts_it_covered():
    s = simulate([tracked("s1", "K1", YELLOW), tracked("s2", "K2", YELLOW)], {"K1": [ROW], "K2": [ROW]}, [], 0.95)
    assert s["reuse_right"] == 1.0 and s["coverage"] == 1.0 and s["review_share"] == 0.5


def test_simulate_leaves_segments_without_truth_waiting():
    s = simulate([tracked("s1", "K1", YELLOW), tracked("s2", "K2", YELLOW)], {}, [], 0.95)
    assert s["counts"]["waiting"] == 1 and s["reuse_right"] is None and s["counts"]["new_frames"] == 1


def test_simulate_splits_reuse_by_kind():
    rows_sour = [{**ROW, "sku": "sourcream150"}]
    s = simulate([tracked("s1", "K1", YELLOW), tracked("s2", "K2", YELLOW)], {"K1": rows_sour, "K2": [ROW]}, [], 0.95)
    assert s["counts"]["reuse_kinds"] == {"flavour_swap": 1}
    unknown = [{**ROW, "sku": "unknown"}]
    s = simulate([tracked("s1", "K1", YELLOW), tracked("s2", "K2", YELLOW)], {"K1": [ROW], "K2": unknown}, [], 0.95)
    assert s["counts"]["reuse_kinds"] == {"flavour_where_unknown": 1}


def test_reuse_right_counts_only_a_flavour_the_truth_contradicts():
    # hoang 26/11: a reused flavour where the truth says unknown (a half-hidden lid) is reported, not counted wrong
    unknown = [{**ROW, "sku": "unknown"}]
    s = simulate([tracked("s1", "K1", YELLOW), tracked("s2", "K2", YELLOW)], {"K1": [ROW], "K2": unknown}, [], 0.95)
    assert s["reuse_right"] == 1.0 and s["counts"]["reuse_kinds"] == {"flavour_where_unknown": 1}


def test_a_reused_flavour_where_the_truth_has_no_can_is_wrong():
    s = simulate([tracked("s1", "K1", YELLOW), tracked("s2", "K2", YELLOW)], {"K1": [ROW], "K2": []}, [], 0.95)
    assert s["reuse_right"] == 0.0 and s["counts"]["reuse_kinds"] == {"flavour_where_no_can": 1}


def test_no_label_against_no_label_is_not_wrong():
    ignore = [{**ROW, "sku": "unknown", "kind": "ignore"}]
    s = simulate([tracked("s1", "K1", YELLOW), tracked("s2", "K2", YELLOW)], {"K1": [], "K2": ignore}, [], 0.95)
    assert s["reuse_right"] == 1.0 and s["counts"]["reuse_kinds"] == {"out_of_scope_vs_not_product": 1}
