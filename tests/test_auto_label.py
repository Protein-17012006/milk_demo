"""Clusters of a segment and the decision for each can (training/store_view/auto_label.py)."""

from training.store_view.auto_label import cluster, same_can
from training.store_view.proposers import Proposal


def A(box, conf=0.9, sku="cheese145"):
    return Proposal("A", box, conf, sku)


def B(box, conf=0.8):
    return Proposal("B", box, conf, None)


def test_a_body_box_and_a_lid_plus_body_box_of_one_can_are_one_track():
    body, whole = (100, 280, 70, 80), (98, 170, 74, 192)  # IoU 0.39, but the body lies inside the whole can
    assert same_can(body, whole)
    tracks = cluster({"C1": [A(body), B(whole)]}, "seg-1")
    assert len(tracks) == 1 and set(tracks[0].seen["C1"]) == {"A", "B"}


def test_two_cans_side_by_side_stay_two_tracks():
    assert not same_can((100, 200, 70, 160), (160, 200, 70, 160))  # touching, 10 px overlap
    tracks = cluster({"C1": [A((100, 200, 70, 160)), A((172, 200, 70, 160), sku="original145")]}, "seg-1")
    assert len(tracks) == 2


def test_a_can_seen_in_several_frames_is_one_track_with_a_median_box():
    frames = {
        "C1": [A((100, 200, 70, 160))],
        "C2": [A((104, 202, 70, 160))],
        "C3": [B((102, 198, 72, 162))],
    }
    (track,) = cluster(frames, "seg-7")
    assert track.id == "seg-7-t0"
    assert set(track.seen) == {"C1", "C2", "C3"}
    assert track.box == (102, 200, 70, 160)


def test_one_source_keeps_its_surer_box_when_it_gives_two_in_a_frame():
    (track,) = cluster({"C1": [A((100, 200, 70, 160), conf=0.5), A((102, 201, 70, 160), conf=0.9)]}, "seg-1")
    assert track.seen["C1"]["A"].conf == 0.9
