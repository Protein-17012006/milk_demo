"""The auto-labeller's commands and camera config (training/store_view/auto_label_run.py)."""

import json

import cv2
import numpy as np

from training.store_view.auto_label import Track
from training.store_view.auto_label_run import (
    _track_from,
    _track_json,
    human_precedents,
    load_group,
    main,
    propose,
    run_segment,
)
from training.store_view.proposers import Proposal
from training.store_view.slide_gallery import Gallery, colour

YELLOW, GREEN, BLUE = (40, 200, 230), (60, 190, 60), (200, 90, 40)  # BGR
CAN1, CAN2 = (10, 10, 20, 40), (40, 10, 20, 40)


def scene():
    img = np.full((64, 80, 3), 128, np.uint8)
    img[10:50, 10:30] = YELLOW
    img[10:50, 40:60] = GREEN
    return img


def patch(bgr):
    p = np.zeros((40, 20, 3), np.uint8)
    p[:] = bgr
    return colour(p)


def gallery():
    feats = [patch(YELLOW)] * 25 + [patch(GREEN)] * 25 + [patch(BLUE)] * 25
    labels = ["cheese145"] * 50 + ["original145"] * 25
    return Gallery(np.stack(feats), np.array(labels), np.array(["S"] * 75), "x", None)


class FakeSources:
    """Both sources agree there are two cans; the detector calls the green one original145."""

    def frame(self, image):
        return [
            Proposal("A", CAN1, 0.9, "cheese145"),
            Proposal("B", CAN1, 0.8, None),
            Proposal("A", CAN2, 0.9, "original145"),
            Proposal("B", CAN2, 0.8, None),
        ]


def test_run_segment_with_fake_sources_accepts_an_agreed_can_and_reviews_a_disputed_one():
    frames = [f"F{i}" for i in range(6)]
    tracks, decisions, used = run_segment("s1", frames, lambda cid: scene(), FakeSources(), gallery())
    assert used == frames and len(tracks) == 2
    by_box = {t.box: decisions[t.id] for t in tracks}
    assert by_box[CAN1].status == "accept" and by_box[CAN1].sku == "cheese145"
    assert by_box[CAN2].status == "review" and by_box[CAN2].reason == "disagree"


def two_tone_scene():
    """Grey-world turns a one-colour crop grey, so each can here has two colours: yellow over blue, green over red."""
    img = scene()
    img[30:50, 10:30] = BLUE
    img[30:50, 40:60] = (40, 40, 200)
    return img


def test_run_segment_gives_each_can_the_colour_of_its_boxes():
    img = two_tone_scene()
    own1, own2 = colour(img[10:50, 10:30]), colour(img[10:50, 40:60])
    assert float(own1 @ own2) < 0.9
    tracks, _, _ = run_segment("seg-1", ["C1", "C2"], lambda c: two_tone_scene(), FakeSources(), gallery())
    by_box = {tuple(t.box): t for t in tracks}
    assert float(by_box[CAN1].colour @ own1) > 0.99
    assert float(by_box[CAN2].colour @ own2) > 0.99


def test_a_track_round_trips_with_and_without_colour():
    t = Track("s-t0", (1.0, 2.0, 3.0, 4.0))
    t.colour = patch(YELLOW)
    back = _track_from(json.loads(json.dumps(_track_json(t))))
    assert np.allclose(back.colour, t.colour, atol=1e-4)
    old = _track_json(t)
    del old["colour"]
    assert _track_from(old).colour is None


def test_propose_skips_scoring_frames_and_writes_one_file_per_segment(tmp_path):
    frames = tmp_path / "frames" / "2026-11-24"
    frames.mkdir(parents=True)
    members = {"seg-1": [f"A{i}" for i in range(6)], "seg-2": [f"B{i}" for i in range(6)]}
    for cid in members["seg-1"] + members["seg-2"]:
        cv2.imwrite(str(frames / f"{cid}.jpg"), scene())
    rows = [{"capture_id": c, "audit_ids": ["AUD-CAM-S01-A-20261124-08"] if c == "A3" else []} for c in members["seg-1"]]
    (tmp_path / "frames" / "manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    segments = [
        {"id": sid, "kind": "day", "split": "train", "keyframe": m[0], "members": m} for sid, m in members.items()
    ] + [{"id": "seg-3", "kind": "day", "split": "holdout", "keyframe": "H0", "members": ["H0"]}]
    out = tmp_path / "out"
    summary = propose(segments, tmp_path / "frames", FakeSources(), gallery(), "train", 30, out)
    assert sorted(p.name for p in out.glob("seg-*.json")) == ["seg-1.json", "seg-2.json"]
    seg1 = json.loads((out / "seg-1.json").read_text())
    assert "A3" not in seg1["frames"] and len(seg1["frames"]) == 5
    assert not (out / "review.json").exists()  # the queue command builds the review list (plan 2026-11-26)
    assert summary["accept"] == 2 and summary["review"] == 2


def test_config_classes_come_from_the_file_not_the_code(tmp_path):
    cfg = {"camera": "CAM-X", "groups": {"slide": {"region": [1, 2, 3, 4], "classes": ["x", "y"],
                                                   "prompts": {"source": "truth", "keyframes": ["K"]}}}}
    (tmp_path / "c.json").write_text(json.dumps(cfg))
    g = load_group(tmp_path / "c.json", "slide")
    assert g["classes"] == ["x", "y"] and g["region"] == (1, 2, 3, 4) and g["prompts"]["keyframes"] == ["K"]


def test_the_detector_window_is_native_size_and_holds_the_region():
    from training.store_view.auto_label_run import window_around

    assert window_around((760, 0, 1200, 320)) == (760, 0, 2040, 1280)
    assert window_around((880, 120, 1520, 720)) == (880, 120, 2160, 1400)
    assert window_around((2400, 1300, 2500, 1400)) == (1280, 160, 2560, 1440)  # pushed back inside the frame


def write_frames(root, ids, aud=()):
    day = root / "2026-11-24"
    day.mkdir(parents=True, exist_ok=True)
    for cid in ids:
        cv2.imwrite(str(day / f"{cid}.jpg"), two_tone_scene())
    rows = [{"capture_id": c, "audit_ids": ["AUD-CAM-S01-A-20261124-08"] if c in aud else ["TRN-X"]} for c in ids]
    (root / "manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def trn_audit(cid, stamp):
    return {"audit_id": f"TRN-{cid}", "status": "done", "capture_id": cid, "capture_timestamp": stamp,
            "ai_boxes_json": json.dumps([{"box_id": "b1", "box": list(CAN1), "sku_id": "cheese145"}]),
            "verdicts_json": json.dumps([{"box_id": "b1", "verdict": "correct"}])}


def test_human_precedents_never_use_held_out_truth_or_scoring_frames(tmp_path):
    frames = tmp_path / "frames"
    write_frames(frames, ["K_train", "K_hold", "C_aud", "C_hold", "C_ok"], aud={"C_aud"})
    rows = [{"box": list(CAN1), "sku": "cheese145", "kind": "face"}]
    truth = tmp_path / "truth.json"
    truth.write_text(json.dumps({"K_train": rows, "K_hold": rows, "C_aud": rows}))
    segments = [
        {"id": "s1", "kind": "day", "split": "train", "keyframe": "K_train", "members": ["K_train"]},
        {"id": "s2", "kind": "day", "split": "holdout", "keyframe": "K_hold", "members": ["K_hold"]},
        {"id": "s3", "kind": "day", "split": "train", "keyframe": "C_aud", "members": ["C_aud"]},
    ]
    trn = tmp_path / "trn.json"
    trn.write_text(json.dumps([trn_audit("C_aud", "2026-11-24T10:00:00+07:00"),
                               trn_audit("C_hold", "2026-11-25T10:00:00+07:00"),
                               trn_audit("C_ok", "2026-11-24T11:00:00+07:00")]))
    ps = human_precedents(truth, segments, frames, trn)
    assert sorted(p.source for p in ps) == ["trn:C_ok@10,10", "truth:K_train#0"]


def seg_file(folder, seg, first, colour_of):
    t = Track(f"{seg}-t0", tuple(float(v) for v in CAN1))
    t.seen = {first: {"B": Proposal("B", CAN1, 0.8, None)}}
    t.colour = colour_of
    body = {"segment": seg, "keyframe": first, "split": "train", "frames": [first], "tracks": [_track_json(t)],
            "decisions": {t.id: ["review", None, "disagree"]}}
    (folder / f"{seg}.json").write_text(json.dumps(body))


def test_queue_command_writes_only_new_frames(tmp_path):
    frames, props = tmp_path / "frames", tmp_path / "props"
    write_frames(frames, ["A1", "B1"])
    props.mkdir()
    yellow = colour(two_tone_scene()[10:50, 10:30])
    seg_file(props, "seg-1", "A1", yellow)
    seg_file(props, "seg-2", "B1", yellow)
    (tmp_path / "truth.json").write_text("{}")
    (tmp_path / "segments.json").write_text("[]")
    main(["queue", "--proposals", str(props), "--truth", str(tmp_path / "truth.json"),
          "--segments", str(tmp_path / "segments.json"), "--frames", str(frames)])
    assert json.loads((props / "queue.json").read_text()) == {"seg-1": ["seg-1-t0"]}


def test_labels_command_labels_a_can_a_human_decided_on_a_train_keyframe(tmp_path):
    frames, props, out = tmp_path / "frames", tmp_path / "props", tmp_path / "out"
    write_frames(frames, ["K1", "A1"])
    props.mkdir()
    seg_file(props, "seg-1", "A1", colour(two_tone_scene()[10:50, 10:30]))
    (tmp_path / "truth.json").write_text(json.dumps({"K1": [{"box": list(CAN1), "sku": "original145", "kind": "face"}]}))
    segments = [{"id": "seg-0", "kind": "day", "split": "train", "keyframe": "K1", "members": ["K1"]},
                {"id": "seg-1", "kind": "day", "split": "train", "keyframe": "A1", "members": ["A1"]}]
    (tmp_path / "segments.json").write_text(json.dumps(segments))
    cfg = {"camera": "CAM-X", "groups": {"slide": {"region": [0, 0, 80, 64], "classes": ["cheese145", "original145"],
                                                   "prompts": {"source": "truth", "keyframes": ["K1"]}}}}
    (tmp_path / "c.json").write_text(json.dumps(cfg))
    main(["labels", "--proposals", str(props), "--frames", str(frames), "--config", str(tmp_path / "c.json"),
          "--segments", str(tmp_path / "segments.json"), "--truth", str(tmp_path / "truth.json"), "--out", str(out)])
    assert (out / "labels" / "A1.txt").read_text().startswith("1 ")
