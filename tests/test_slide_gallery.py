"""The colour gallery of human-labelled Slide crops (training/store_view/slide_gallery.py)."""

import json

import cv2
import numpy as np

from training.store_view.slide_gallery import MIN_IMAGES, Gallery, build, colour, read, trn_rows

RNG = np.random.default_rng(7)


def unit(v):
    return v / np.linalg.norm(v)


def axis(i):
    v = np.zeros(144)
    v[i] = 1.0
    return v


def near(v, n, spread=0.05):
    return np.stack([unit(v + RNG.normal(0, spread, 144) * (v == 0)) for _ in range(n)])


def gallery(groups, none_threshold=None):
    feats = np.concatenate([f for f, _ in groups])
    labels = np.concatenate([[lab] * len(f) for f, lab in groups])
    return Gallery(feats, labels, np.array([f"C{i}" for i in range(len(labels))]), "2026-11-25", none_threshold)


def test_colour_is_a_unit_144_vector_and_ignores_overall_brightness():
    crop = RNG.integers(30, 220, size=(160, 70, 3)).astype(np.uint8)
    a, b = colour(crop), colour((crop * 0.6).astype(np.uint8))
    assert a.shape == (144,) and abs(np.linalg.norm(a) - 1) < 1e-6
    assert float(a @ b) > 0.98


def test_read_names_the_flavour_with_most_weight():
    g = gallery([(near(axis(0), 25), "cheese145"), (near(axis(50), 25), "original145")])
    vote = read(g, axis(0))
    assert vote.sku == "cheese145" and vote.votes >= 3 and vote.share >= 0.6 and not vote.none_hit


def test_read_never_votes_for_a_flavour_with_fewer_than_20_images():
    hot = near(axis(0), 12, spread=0.01)
    far = near(unit(axis(0) * 0.5 + axis(9)), 30)
    g = gallery([(hot, "hot160"), (far, "original145")])
    assert MIN_IMAGES == 20
    assert read(g, axis(0)).sku is None


def test_read_is_unsure_below_60_percent_weight():
    q = unit(axis(0) + axis(1))
    a = np.stack([unit(axis(0) + axis(1) + 0.001 * axis(2 + i)) for i in range(5)])
    b = np.stack([unit(axis(0) + axis(1) + 0.001 * axis(20 + i)) for i in range(5)])
    g = gallery([(a, "cheese145"), (b, "original145"), (near(axis(60), 25), "cheese145"), (near(axis(90), 25), "original145")])
    assert read(g, q).sku is None


def test_none_hit_only_when_the_gallery_has_a_none_threshold():
    none = np.stack([unit(axis(0) + 0.33 * axis(1))])  # cosine 0.95 with axis(0)
    rest = near(axis(70), 25)
    assert not read(gallery([(none, "none"), (rest, "cheese145")]), axis(0)).none_hit
    assert read(gallery([(none, "none"), (rest, "cheese145")], none_threshold=0.9), axis(0)).none_hit


def audit(aid, status, boxes, verdicts, cid="C2", ts="2026-11-24T12:00:13+07:00"):
    return {
        "audit_id": aid,
        "status": status,
        "capture_id": cid,
        "capture_timestamp": ts,
        "ai_boxes_json": json.dumps(boxes),
        "verdicts_json": json.dumps(verdicts),
    }


def test_trn_rows_follow_the_verdicts():
    boxes = [{"box_id": i, "sku_id": "original145", "conf": 0.9, "box": [10 * i, 0, 8, 8]} for i in range(1, 5)]
    verdicts = [
        {"box_id": 1, "verdict": "correct"},
        {"box_id": 2, "verdict": "wrong_sku", "true_sku_id": "hot160"},
        {"box_id": 3, "verdict": "not_product"},
        {"box_id": 4, "verdict": "out_of_scope"},
    ]
    rows = trn_rows(
        [
            audit("TRN-CAM-S01-A-20261124-12", "done", boxes, verdicts),
            audit("TRN-CAM-S01-A-20261124-13", "pending", boxes, []),
            audit("AUD-CAM-S01-A-20261124-12", "done", boxes, verdicts),
        ]
    )
    assert rows == [("C2", [10, 0, 8, 8], "original145"), ("C2", [20, 0, 8, 8], "hot160"), ("C2", [30, 0, 8, 8], "none")]


def frame(folder, day, cid):
    (folder / day).mkdir(parents=True, exist_ok=True)
    img = RNG.integers(30, 220, size=(120, 200, 3)).astype(np.uint8)
    cv2.imwrite(str(folder / day / f"{cid}.jpg"), img)


def test_build_skips_scoring_frames_and_holdout_trn_when_asked(tmp_path):
    frames = tmp_path / "frames"
    frame(frames, "2026-11-24", "C1")
    frame(frames, "2026-11-24", "C2")
    frame(frames, "2026-11-25", "C3")
    rows = [
        {"capture_id": "C1", "audit_ids": ["AUD-CAM-S01-A-20261124-11", "TRN-CAM-S01-A-20261124-11"]},
        {"capture_id": "C2", "audit_ids": ["TRN-CAM-S01-A-20261124-12"]},
        {"capture_id": "C3", "audit_ids": ["TRN-CAM-S01-A-20261125-08"]},
    ]
    (frames / "manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    box = [{"box_id": 1, "sku_id": "cheese145", "conf": 0.9, "box": [20, 20, 30, 60]}]
    ok = [{"box_id": 1, "verdict": "correct"}]
    trn = [
        audit("TRN-CAM-S01-A-20261124-11", "done", box, ok, cid="C1", ts="2026-11-24T11:00:00+07:00"),
        audit("TRN-CAM-S01-A-20261124-12", "done", box, ok, cid="C2", ts="2026-11-24T12:00:00+07:00"),
        audit("TRN-CAM-S01-A-20261125-08", "done", box, ok, cid="C3", ts="2026-11-25T08:00:00+07:00"),
    ]
    g = build({}, [], frames, trn, exclude_holdout=True)
    assert sorted(set(g.sources.tolist())) == ["C2"]
    assert sorted(set(build({}, [], frames, trn, exclude_holdout=False).sources.tolist())) == ["C2", "C3"]


def test_save_and_load_round_trip(tmp_path):
    g = gallery([(near(axis(0), 3), "cheese145")], none_threshold=0.91)
    g.save(tmp_path / "g.npz")
    back = Gallery.load(tmp_path / "g.npz")
    assert np.allclose(back.features, g.features) and back.labels.tolist() == g.labels.tolist()
    assert back.sources.tolist() == g.sources.tolist() and back.built_at == "2026-11-25" and back.none_threshold == 0.91
    assert back.counts() == {"cheese145": 3}
