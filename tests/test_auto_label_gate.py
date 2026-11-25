"""Gate 1: the auto-labeller's decisions against the hand-drawn truth (training/store_view/auto_label_gate.py)."""

from training.store_view.auto_label import Decision, Track
from training.store_view.auto_label_gate import GATE1, failures, score
from training.store_view.proposers import Proposal

KEY = "K1"


def can(tid, box):
    t = Track(tid, box)
    t.seen[KEY] = {"B": Proposal("B", box, 0.8, None)}
    return t


def one(tracks, decisions, rows):
    return score({"s1": (tracks, decisions)}, {KEY: rows}, {"s1": KEY})


def test_an_accepted_can_on_a_lower_tier_truth_row_counts_as_real():
    s = one([can("t0", (100, 500, 70, 160))], {"t0": Decision("accept", "cheese145", "agree")},
            [{"box": [95, 495, 80, 170], "sku": "unknown", "kind": "lower"}])
    assert s["real"] == 1.0 and s["flavour"] is None


def test_an_accepted_box_where_no_truth_row_is_is_not_real():
    s = one([can("t0", (900, 900, 50, 50))], {"t0": Decision("accept", "cheese145", "agree")},
            [{"box": [95, 495, 80, 170], "sku": "cheese145", "kind": "face"}])
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
    assert set(GATE1) == {"real", "flavour", "coverage", "review_share"}
    got = failures({"real": 0.95, "flavour": 0.99, "coverage": 0.90, "review_share": 0.5})
    assert len(got) == 3 and any("real" in f for f in got) and any("review_share" in f for f in got)
    assert failures({"real": None, "flavour": 1.0, "coverage": 1.0, "review_share": 0.0}) == ["real not measured"]
