"""A person's decision reused for the same can, and the review queue (training/store_view/auto_label_reuse.py)."""

import copy

import numpy as np
import pytest

from training.store_view.auto_label import Decision, Track
from training.store_view.auto_label_reuse import (
    Precedent,
    decision_for,
    label_of,
    pair_stats,
    queue,
    reuse,
    review_precedents,
    suggest_min_sim,
    trn_precedents,
    truth_precedents,
)
from training.store_view.slide_gallery import colour

BOX = (100.0, 500.0, 70.0, 160.0)


def axis(i):
    v = np.zeros(144)
    v[i] = 1.0
    return v


YELLOW, GREEN = axis(0), axis(1)  # two colours the gallery feature tells apart


def can(tid, box=BOX, colour=YELLOW):
    t = Track(tid, box)
    t.colour = None if colour is None else colour.copy()
    return t


def precedent(label, colour=YELLOW, box=BOX, key="K", source="truth:K#0"):
    return Precedent(key, box, colour, label, source)


def prop(seg, first, tracks, decisions):
    return {"segment": seg, "keyframe": first, "split": "train", "frames": [first, first + "-b"],
            "tracks": tracks, "decisions": decisions}


def waiting(seg, first):
    """A segment with one can at BOX, sent to review, yellow."""
    return prop(seg, first, [can(f"{seg}-t0")], {f"{seg}-t0": Decision("review", None, "disagree")})


def test_a_can_at_the_same_place_with_the_same_colour_takes_the_human_flavour():
    assert reuse(can("t"), [precedent("original145")], 0.95) == Decision("accept", "original145", "reused:truth:K#0")


def test_a_swapped_can_same_place_other_colour_is_not_reused():
    assert reuse(can("t", colour=YELLOW), [precedent("sourcream150", colour=GREEN)], 0.95) is None


def test_iou_below_half_is_another_place():
    shifted = (100.0 + 70.0 * 3 / 7, 500.0, 70.0, 160.0)  # overlap 40 of 70 wide: IoU = 40 / 100 = 0.4
    assert reuse(can("t", box=shifted), [precedent("cheese145")], 0.95) is None


def test_matching_precedents_that_disagree_send_the_can_to_a_person():
    ps = [precedent("cheese145", key="K1", source="truth:K1#0"), precedent("original145", key="K2", source="trn:K2@1,1")]
    assert reuse(can("t"), ps, 0.95) == Decision("review", None, "reuse_conflict")


def test_agreeing_precedents_name_the_latest_as_the_source():
    ps = [precedent("cheese145", key="CAP-2", source="b"), precedent("cheese145", key="CAP-1", source="a")]
    assert reuse(can("t"), ps, 0.95) == Decision("accept", "cheese145", "reused:b")


def test_not_product_drops_and_out_of_scope_masks():
    assert decision_for("not_product", "r") == Decision("drop", None, "r")
    assert decision_for("out_of_scope", "r") == Decision("masked", None, "r")
    assert decision_for("hot160", "r") == Decision("accept", "hot160", "r")
    assert label_of(Decision("masked", None, "x")) == "out_of_scope"
    assert label_of(Decision("drop", None, "x")) == "not_product"
    assert label_of(Decision("accept", "hot160", "x")) == "hot160"
    assert label_of(Decision("review", None, "disagree")) is None


def test_a_can_without_colour_never_matches():
    assert reuse(can("t", colour=None), [precedent("cheese145")], 0.0) is None


def test_queue_opens_one_frame_then_later_segments_wait_on_it():
    r = queue([waiting("s1", "CAP-1"), waiting("s2", "CAP-2"), waiting("s3", "CAP-3")], [], 0.95)
    assert r.new_frames == {"s1": ["s1-t0"]}
    assert r.decisions["s2"]["s2-t0"] == Decision("review", None, "waits:s1-t0")
    assert r.decisions["s3"]["s3-t0"] == Decision("review", None, "waits:s1-t0")


def test_a_can_of_another_colour_at_a_waiting_place_needs_its_own_frame():
    s2 = prop("s2", "CAP-2", [can("s2-t0", colour=GREEN)], {"s2-t0": Decision("review", None, "disagree")})
    assert queue([waiting("s1", "CAP-1"), s2], [], 0.95).new_frames == {"s1": ["s1-t0"], "s2": ["s2-t0"]}


def test_queue_orders_segments_by_first_frame_not_by_name():
    r = queue([waiting("s1", "CAP-9"), waiting("s9", "CAP-1")], [], 0.95)
    assert r.new_frames == {"s9": ["s9-t0"]}
    assert r.decisions["s1"]["s1-t0"] == Decision("review", None, "waits:s9-t0")


def test_a_decided_precedent_resolves_the_can_without_a_frame():
    r = queue([waiting("s1", "CAP-1")], [precedent("cheese145")], 0.95)
    assert r.new_frames == {}
    assert r.decisions["s1"]["s1-t0"] == Decision("accept", "cheese145", "reused:truth:K#0")
    assert r.links == [("s1", "s1-t0", "truth:K#0")]


def test_a_conflict_opens_a_frame():
    ps = [precedent("cheese145", key="K1"), precedent("original145", key="K2")]
    r = queue([waiting("s1", "CAP-1")], ps, 0.95)
    assert r.new_frames == {"s1": ["s1-t0"]}
    assert r.decisions["s1"]["s1-t0"] == Decision("review", None, "reuse_conflict")


def test_a_simulated_human_decision_is_reused_by_later_segments():
    r = queue([waiting("s1", "CAP-1"), waiting("s2", "CAP-2")], [], 0.95,
              human=lambda p, t: "cheese145" if p["segment"] == "s1" else None)
    assert r.new_frames == {"s1": ["s1-t0"]}
    assert r.decisions["s1"]["s1-t0"] == Decision("accept", "cheese145", "human")
    assert r.decisions["s2"]["s2-t0"] == Decision("accept", "cheese145", "reused:sim:s1-t0")
    assert r.links == [("s2", "s2-t0", "sim:s1-t0")]


def test_accepted_cans_and_out_of_scope_are_left_alone():
    s1 = prop("s1", "CAP-1", [can("s1-t0"), can("s1-t1", box=(300.0, 500.0, 70.0, 160.0))],
              {"s1-t0": Decision("accept", "hot160", "agree"), "s1-t1": Decision("masked", None, "out_of_scope")})
    r = queue([s1], [precedent("cheese145"), precedent("cheese145", box=(300.0, 500.0, 70.0, 160.0))], 0.95)
    assert r.decisions["s1"] == s1["decisions"] and r.new_frames == {} and r.links == []


def test_queue_does_not_change_its_input():
    s1 = waiting("s1", "CAP-1")
    before = copy.deepcopy(s1["decisions"])
    queue([s1], [precedent("cheese145")], 0.95)
    assert s1["decisions"] == before


def two_cans():
    """A 64 x 80 frame with two two-tone cans (grey-world would turn a one-colour crop grey)."""
    img = np.full((64, 80, 3), 128, np.uint8)
    img[10:30, 10:30], img[30:50, 10:30] = (40, 200, 230), (200, 90, 40)
    img[10:30, 40:60], img[30:50, 40:60] = (60, 190, 60), (40, 40, 200)
    return img


ROWS = [{"box": [10, 10, 20, 40], "sku": "cheese145", "kind": "face"},
        {"box": [40, 10, 20, 40], "sku": "unknown", "kind": "lid"}]


def test_truth_rows_become_precedents_with_their_crop_colour_and_unknown_as_out_of_scope():
    ps = truth_precedents({"K": ROWS, "OTHER": ROWS}, ["K"], lambda c: two_cans())
    assert [p.label for p in ps] == ["cheese145", "out_of_scope"]
    assert float(ps[0].colour @ colour(two_cans()[10:50, 10:30])) > 0.99
    assert float(ps[0].colour @ ps[1].colour) < 0.9
    assert [p.source for p in ps] == ["truth:K#0", "truth:K#1"] and ps[0].key == "K"


def test_an_ignore_row_is_out_of_scope_even_with_a_flavour():
    ps = truth_precedents({"K": [{"box": [10, 10, 20, 40], "sku": "hot160", "kind": "ignore"}]}, ["K"],
                          lambda c: two_cans())
    assert ps[0].label == "out_of_scope"


def test_trn_none_is_not_product():
    ps = trn_precedents([("C1", [10, 10, 20, 40], "none"), ("C1", [40, 10, 20, 40], "sourcream150")],
                        lambda c: two_cans())
    assert [(p.label, p.source, p.key) for p in ps] == [("not_product", "trn:C1@10,10", "C1"),
                                                        ("sourcream150", "trn:C1@40,10", "C1")]


def test_review_decisions_become_precedents_keyed_by_the_segment_first_frame():
    s1 = prop("s1", "C1", [can("s1-t0"), can("s1-t1", colour=GREEN), can("s1-t2", colour=None), can("s1-t3")],
              {})
    review = {"s1": {"tracks": {"s1-t0": {"verdict": "sku", "sku": "hot160"}, "s1-t1": {"verdict": "out_of_scope"},
                                "s1-t2": {"verdict": "not_product"}}, "missed": []}}
    ps = review_precedents([s1], review)
    assert {(p.source, p.label, p.key) for p in ps} == {("review:s1-t0", "hot160", "C1"),
                                                        ("review:s1-t1", "out_of_scope", "C1")}


def test_unreadable_images_give_no_precedent():
    assert truth_precedents({"K": ROWS}, ["K"], lambda c: None) == []
    assert trn_precedents([("C1", [10, 10, 20, 40], "none")], lambda c: None) == []


def test_suggest_min_sim_is_the_5th_percentile_of_same_label_pairs():
    pairs = [(0.90 + i / 1000, True) for i in range(100)]
    assert abs(suggest_min_sim(pairs) - 0.905) < 0.002


def test_suggest_min_sim_rises_above_the_closest_different_label_pair():
    assert suggest_min_sim([(0.95, True)] * 20 + [(0.97, False)]) == pytest.approx(0.975)


def test_suggest_min_sim_without_same_label_pairs_reuses_nothing():
    assert suggest_min_sim([(0.97, False)]) == 1.0


def test_pair_stats_pairs_only_different_keys_at_the_same_place():
    far = (600.0, 100.0, 70.0, 160.0)
    ps = [precedent("cheese145", key="K1"), precedent("cheese145", key="K1", box=far),
          precedent("cheese145", key="K2"), precedent("original145", colour=GREEN, key="K3")]
    pairs = pair_stats(ps)
    assert sorted(pairs) == [(0.0, False), (0.0, False), (1.0, True)]
