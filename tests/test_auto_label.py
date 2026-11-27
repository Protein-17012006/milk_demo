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


import pytest  # noqa: E402

from training.store_view.auto_label import Decision, Track, decide  # noqa: E402
from training.store_view.slide_gallery import GalleryVote  # noqa: E402

COUNTS = {"cheese145": 30, "original145": 30, "sourcream150": 30}  # no hot160 crops yet


def track(n, a_seen, b_seen, a_skus=(), gallery=(), none_hits=0):
    """n frames F0..; the detector sees the first a_seen with a_skus[i], YOLOE the first b_seen; gallery[i] is the
    gallery's flavour in frame i (None = unsure); the first none_hits frames of YOLOE's are read as not a product."""
    t = Track("seg-1-t0", (100, 200, 70, 160))
    for i in range(n):
        cid = f"F{i:02d}"
        slot = {}
        if i < a_seen:
            slot["A"] = Proposal("A", (100, 200, 70, 160), 0.9, a_skus[i] if a_skus else "cheese145")
        if i < b_seen:
            slot["B"] = Proposal("B", (98, 170, 74, 192), 0.8, None)
        if slot:
            t.seen[cid] = slot
            sku = gallery[i] if i < len(gallery) else None
            t.votes[cid] = GalleryVote(sku, 1.0 if sku else 0.4, 10 if sku else 4, i < none_hits)
    return t, [f"F{i:02d}" for i in range(n)]


CASES = [
    ("both agree", (10, 10, 10, ["cheese145"] * 10, ["cheese145"] * 10), ("accept", "cheese145", "agree")),
    ("ghost", (10, 2, 2, ["cheese145"] * 2, ["cheese145"] * 2), ("drop", None, "ghost")),
    ("only YOLOE", (10, 0, 8, (), ["original145"] * 8), ("review", None, "no_A_flavour")),
    ("gallery says none", (10, 0, 8, (), [None] * 8, 6), ("drop", None, "gallery_none")),
    ("only the detector", (10, 10, 0, ["cheese145"] * 10, ["cheese145"] * 10), ("review", None, "only_A")),
    ("thin gallery", (10, 10, 10, ["hot160"] * 10, [None] * 10), ("review", None, "thin_gallery")),
    ("disagree", (10, 10, 10, ["original145"] * 10, ["cheese145"] * 10), ("review", None, "disagree")),
    (
        "unstable",
        (10, 10, 10, ["original145"] * 7 + ["cheese145"] * 3, ["original145"] * 10),
        ("review", None, "unstable"),
    ),
    ("too short", (3, 3, 3, ["cheese145"] * 3, ["cheese145"] * 3), ("too_short", None, "too_short")),
]


@pytest.mark.parametrize("name,args,want", CASES, ids=[c[0] for c in CASES])
def test_decide(name, args, want):
    t, frames = track(*args)
    assert decide(t, frames, COUNTS) == Decision(*want)
