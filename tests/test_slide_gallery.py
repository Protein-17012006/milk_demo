"""The colour gallery of human-labelled Slide crops (training/store_view/slide_gallery.py)."""

import json

import cv2
import numpy as np

from training.store_view.slide_gallery import (
    LABEL_PREFIXES,
    MIN_IMAGES,
    Gallery,
    build,
    colour,
    day_of,
    mean_colour,
    read,
    trn_rows,
)

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
    g = gallery(
        [(a, "cheese145"), (b, "original145"), (near(axis(60), 25), "cheese145"), (near(axis(90), 25), "original145")]
    )
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
    assert rows == [
        ("C2", [10, 0, 8, 8], "original145"),
        ("C2", [20, 0, 8, 8], "hot160"),
        ("C2", [30, 0, 8, 8], "none"),
    ]


def test_trn_rows_read_done_review_audits_as_people_labels():
    boxes = [
        {"box_id": 1, "track_id": "s-t0", "sku_id": "cheese145", "conf": 1.0, "box": [10, 0, 8, 8]},
        {"box_id": 2, "track_id": "s-t1", "sku_id": None, "conf": 0.0, "box": [20, 0, 8, 8], "needs_flavour": True},
    ]
    verdicts = [{"box_id": 1, "verdict": "correct"}, {"box_id": 2, "verdict": "wrong_sku", "true_sku_id": "hot160"}]
    rows = trn_rows([audit("REV-CAM-S01-A-seg-0090", "done", boxes, verdicts)])
    assert rows == [("C2", [10, 0, 8, 8], "cheese145"), ("C2", [20, 0, 8, 8], "hot160")]


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


def test_twenty_crops_of_one_can_are_not_twenty_cans():
    # a truth box is cut from up to 30 frames: those crops are one can, and MIN_IMAGES counts cans
    hot = near(axis(0), 25, spread=0.01)
    rest = near(axis(40), 30)
    feats = np.concatenate([hot, rest])
    labels = np.array(["hot160"] * 25 + ["original145"] * 30)
    objects = np.array(["truth:K1#3"] * 25 + [f"trn:C{i}@1,1" for i in range(30)])
    g = Gallery(feats, labels, np.array(["K1"] * 55), "x", None, objects)
    assert g.counts() == {"hot160": 1, "original145": 30}
    assert read(g, axis(0)).sku is None


def test_build_names_each_can_once(tmp_path):
    # one truth box cut from three look-alike frames of its segment is one can
    frames = tmp_path / "frames"
    (frames / "2026-11-24").mkdir(parents=True)
    img = RNG.integers(30, 220, size=(120, 200, 3)).astype(np.uint8)
    for cid in ("K", "M1", "M2"):
        cv2.imwrite(str(frames / "2026-11-24" / f"{cid}.jpg"), img)
    rows = [{"capture_id": c, "audit_ids": []} for c in ("K", "M1", "M2")]
    (frames / "manifest.jsonl").write_text("".join(json.dumps(r) + chr(10) for r in rows))
    truth = {"K": [{"box": [20, 20, 30, 60], "sku": "cheese145", "kind": "face"}]}
    segments = [{"id": "s", "kind": "day", "split": "train", "keyframe": "K", "members": ["K", "M1", "M2"]}]
    g = build(truth, segments, frames, [], exclude_holdout=True)
    assert len(g.labels) == 3 and g.counts() == {"cheese145": 1}


def test_mean_colour_is_a_unit_vector_and_none_for_nothing():
    m = mean_colour([axis(0), axis(0), axis(1)])
    assert abs(float(np.linalg.norm(m)) - 1.0) < 1e-6
    assert float(m @ axis(0)) > float(m @ axis(1)) > 0
    assert mean_colour([]) is None


def test_cmp_frames_are_people_labels_and_a_disputed_box_takes_the_name_people_chose():
    boxes = [
        {"box_id": 1, "sku_id": "cheese145", "conf": 0.9, "box": [10, 0, 8, 8]},
        {"box_id": 2, "sku_id": None, "conf": 0.0, "box": [20, 0, 8, 8], "needs_flavour": True},
        {"box_id": 3, "sku_id": None, "conf": 0.0, "box": [30, 0, 8, 8], "needs_flavour": True},
        {"box_id": 4, "sku_id": None, "conf": 0.0, "box": [40, 0, 8, 8], "needs_flavour": True},
    ]
    verdicts = [
        {"box_id": 1, "verdict": "correct"},
        {"box_id": 2, "verdict": "wrong_sku", "true_sku_id": "hot160"},
        {"box_id": 3, "verdict": "not_product"},
        {"box_id": 4, "verdict": "correct"},  # no usable label: skipped
    ]
    cmp_audit = audit("CMP-CAM-S01-A-20261127-01", "done", boxes, verdicts)
    assert LABEL_PREFIXES == ("TRN-", "REV-", "CMP-")
    assert trn_rows([cmp_audit]) == []  # the auto-label default is unchanged
    assert trn_rows([cmp_audit], LABEL_PREFIXES) == [
        ("C2", [10, 0, 8, 8], "cheese145"),
        ("C2", [20, 0, 8, 8], "hot160"),
        ("C2", [30, 0, 8, 8], "none"),
    ]


def test_a_capture_with_an_aud_audit_never_enters_even_with_a_trn_audit(tmp_path):
    frames = tmp_path / "frames"
    frame(frames, "2026-11-27", "C1")
    frame(frames, "2026-11-27", "C2")
    rows = [
        {"capture_id": "C1", "audit_ids": ["TRN-CAM-S01-A-20261127-01", "AUD-CAM-S01-A-20261127-01"]},
        {"capture_id": "C2", "audit_ids": ["CMP-CAM-S01-A-20261127-02"]},
    ]
    (frames / "manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    box = [{"box_id": 1, "sku_id": "cheese145", "conf": 0.9, "box": [20, 20, 30, 60]}]
    ok = [{"box_id": 1, "verdict": "correct"}]
    done = [
        audit("TRN-CAM-S01-A-20261127-01", "done", box, ok, cid="C1"),
        audit("CMP-CAM-S01-A-20261127-02", "done", box, ok, cid="C2"),
    ]
    g = build({}, [], frames, done, exclude_holdout=False)
    assert sorted(set(g.sources.tolist())) == ["C2"]
    assert g.built_from == ("CMP-CAM-S01-A-20261127-02",)


def test_day_of_reads_the_store_day_from_the_capture_id():
    assert day_of("CAP-S01-20261127-235959-3") == "2026-11-27"
    assert day_of("CAP-S01-20261128-000001") == "2026-11-28"


def test_build_leaves_out_the_excluded_days_and_records_what_it_was_built_from(tmp_path):
    frames = tmp_path / "frames"
    for day, cid in (
        ("2026-11-26", "CAP-S01-20261126-100000"),
        ("2026-11-27", "CAP-S01-20261127-100000"),
        ("2026-11-26", "CAP-S01-20261126-090000"),
        ("2026-11-27", "CAP-S01-20261127-090000"),
    ):
        frame(frames, day, cid)
    k1, k2 = "CAP-S01-20261126-090000", "CAP-S01-20261127-090000"
    cids = [k1, k2, "CAP-S01-20261126-100000", "CAP-S01-20261127-100000"]
    (frames / "manifest.jsonl").write_text("".join(json.dumps({"capture_id": c, "audit_ids": []}) + "\n" for c in cids))
    truth = {k: [{"box": [20, 20, 30, 60], "sku": "cheese145", "kind": "face"}] for k in (k1, k2)}
    segments = [
        {"id": f"s{i}", "kind": "day", "split": "train", "keyframe": k, "members": [k]} for i, k in enumerate((k1, k2))
    ]
    box = [{"box_id": 1, "sku_id": "hot160", "conf": 0.9, "box": [20, 20, 30, 60]}]
    ok = [{"box_id": 1, "verdict": "correct"}]
    trn = [
        audit("TRN-A-1", "done", box, ok, cid="CAP-S01-20261126-100000"),
        audit("REV-A-2", "done", box, ok, cid="CAP-S01-20261127-100000"),
    ]
    full = build(truth, segments, frames, trn, exclude_holdout=False)
    assert full.built_from == tuple(sorted(["REV-A-2", "TRN-A-1", f"truth:{k1}", f"truth:{k2}"]))
    g = build(truth, segments, frames, trn, exclude_holdout=False, exclude_days=frozenset({"2026-11-27"}))
    assert g.built_from == tuple(sorted(["TRN-A-1", f"truth:{k1}"]))
    assert sorted(set(g.sources.tolist())) == sorted([k1, "CAP-S01-20261126-100000"])
    g.save(tmp_path / "g.npz")
    assert Gallery.load(tmp_path / "g.npz").built_from == g.built_from


def test_an_old_gallery_file_without_built_from_loads_as_empty(tmp_path):
    np.savez(
        tmp_path / "old.npz",
        features=np.zeros((1, 144)),
        labels=np.array(["cheese145"]),
        sources=np.array(["C1"]),
        built_at=np.array("x"),
        none_threshold=np.array(np.nan),
    )
    assert Gallery.load(tmp_path / "old.npz").built_from == ()


def test_a_group_gallery_keeps_its_own_names_and_only_the_none_crops_inside_its_region(tmp_path):
    frames = tmp_path / "frames"
    frame(frames, "2026-11-27", "CAP-S01-20261127-100000")
    cid = "CAP-S01-20261127-100000"
    (frames / "manifest.jsonl").write_text(json.dumps({"capture_id": cid, "audit_ids": []}) + "\n")
    boxes = [
        {"box_id": 1, "sku_id": "cheese145", "conf": 0.9, "box": [20, 20, 30, 60]},
        {"box_id": 2, "sku_id": "TMP-MLK-TH-00", "conf": 0.9, "box": [60, 20, 30, 60]},
        {"box_id": 3, "sku_id": "x", "conf": 0.9, "box": [100, 20, 30, 60]},  # centre (115, 50): in the region
        {"box_id": 4, "sku_id": "x", "conf": 0.9, "box": [160, 20, 30, 60]},  # centre (175, 50): outside
    ]
    verdicts = [
        {"box_id": 1, "verdict": "correct"},
        {"box_id": 2, "verdict": "correct"},
        {"box_id": 3, "verdict": "not_product"},
        {"box_id": 4, "verdict": "not_product"},
    ]
    trn = [audit("TRN-A-1", "done", boxes, verdicts, cid=cid)]
    g = build(
        {}, [], frames, trn, exclude_holdout=False, skus=frozenset({"cheese145", "hot160"}), region=(0, 0, 150, 100)
    )
    assert sorted(g.labels.tolist()) == ["cheese145", "none"]
    assert sorted(g.objects.tolist()) == [f"trn:{cid}@100,20", f"trn:{cid}@20,20"]
    everything = build({}, [], frames, trn, exclude_holdout=False)
    assert len(everything.labels) == 4


def test_build_takes_several_frame_folders_and_their_scoring_frames_are_the_union(tmp_path):
    harvest, export = tmp_path / "harvest", tmp_path / "export"
    key, labelled, scoring = "CAP-S01-20261126-090000", "CAP-S01-20261126-100000", "CAP-S01-20261126-110000"
    frame(harvest, "2026-11-26", key)
    frame(export, "2026-11-26", labelled)
    frame(export, "2026-11-26", scoring)
    other = "CAP-S01-20261126-120000"
    frame(harvest, "2026-11-26", other)
    rows = [{"capture_id": key, "audit_ids": []}, {"capture_id": other, "audit_ids": ["AUD-H-1", "TRN-H-1"]}]
    (harvest / "manifest.jsonl").write_text("".join(json.dumps(r) + chr(10) for r in rows))
    (export / "manifest.jsonl").write_text(json.dumps({"capture_id": scoring, "audit_ids": ["AUD-X-1"]}) + "\n")
    truth = {key: [{"box": [20, 20, 30, 60], "sku": "cheese145", "kind": "face"}]}
    segments = [{"id": "s0", "kind": "day", "split": "train", "keyframe": key, "members": [key]}]
    box = [{"box_id": 1, "sku_id": "hot160", "conf": 0.9, "box": [20, 20, 30, 60]}]
    ok = [{"box_id": 1, "verdict": "correct"}]
    trn = [
        audit("TRN-A-1", "done", box, ok, cid=labelled),
        audit("TRN-A-2", "done", box, ok, cid=scoring),
        audit("TRN-H-1", "done", box, ok, cid=other),
    ]
    g = build(truth, segments, [harvest, export], trn, exclude_holdout=False)
    assert g.built_from == tuple(sorted(["TRN-A-1", f"truth:{key}"]))  # the scoring frame of the other folder is out
    assert build(truth, segments, harvest, trn[:1], exclude_holdout=False).built_from == (f"truth:{key}",)


def test_a_day_held_out_also_drops_the_members_of_a_kept_truth_segment_that_fall_on_that_day(tmp_path):
    frames = tmp_path / "frames"
    key, member = "CAP-S01-20261127-235000", "CAP-S01-20261128-001000"
    frame(frames, "2026-11-27", key)
    frame(frames, "2026-11-28", member)
    (frames / "manifest.jsonl").write_text(
        "".join(json.dumps({"capture_id": c, "audit_ids": []}) + "\n" for c in (key, member))
    )
    truth = {key: [{"box": [20, 20, 30, 60], "sku": "cheese145", "kind": "face"}]}
    segments = [{"id": "s0", "kind": "day", "split": "train", "keyframe": key, "members": [key, member]}]
    full = build(truth, segments, frames, [], exclude_holdout=False, min_sim=-1.0)
    assert member in set(full.sources.tolist())
    g = build(truth, segments, frames, [], exclude_holdout=False, exclude_days=frozenset({"2026-11-28"}), min_sim=-1.0)
    assert set(g.sources.tolist()) == {key}
