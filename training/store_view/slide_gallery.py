"""The colour gallery: Slide can crops labelled by people, and how it reads a can's flavour (auto-label design 5.4,
slide-fusion design 5.1).

A crop is described by its colour: the middle 70% of its height and 60% of its width, grey-world balanced, a hue x
saturation histogram (18 x 8) of it, square-rooted and of unit length. A can is read by its 10 nearest crops (cosine):
a flavour is named only when it holds at least 60% of their weight, at least 3 of the 10, and the gallery has at
least 20 crops of it; otherwise the read is unsure. Only people's labels enter: the hand-drawn truth and the training
frames (TRN) labelled on the Model page, never automatic labels, never a scoring frame (AUD), and, for a gallery used
to measure, never a held-out frame.

    python -m training.store_view.slide_gallery export-trn --out trn_done.json            (laptop: TRN- and REV- audits)
    python -m training.store_view.slide_gallery build --truth T --segments S --frames F --trn trn_done.json ^
        [--exclude-holdout] --out slide_gallery_CAM-S01-A_<YYYYMMDD>.npz
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))

from milk.gallery import (  # noqa: E402,F401  the read rule lives in the worker's code; re-exported for the tools
    MIN_IMAGES,
    MIN_SHARE,
    MIN_VOTES,
    Gallery,
    GalleryVote,
    K,
    _grey_world,
    colour,
    crop_of,
    mean_colour,
    read,
)

AUDITS_TABLE = "milk-backend-development-audits"
REGION_NAME = "ap-southeast-1"


def trn_rows(audits: list[dict]) -> list[tuple[str, list[int], str]]:
    """(capture_id, box x y w h, label) of each judged box of the done training (TRN-) and review (REV-) audits, both
    people's labels: correct -> the box's label, wrong_sku -> the true one, not_product -> "none"; out of scope and
    anything not judged are left out. Scoring audits (AUD-) never enter."""
    out = []
    for a in audits:
        if not str(a.get("audit_id", "")).startswith(("TRN-", "REV-")) or a.get("status") != "done":
            continue
        boxes = {b["box_id"]: b for b in json.loads(a.get("ai_boxes_json") or "[]")}
        for v in json.loads(a.get("verdicts_json") or "[]"):
            b = boxes.get(v.get("box_id"))
            if b is None:
                continue
            label = {"correct": b.get("sku_id"), "wrong_sku": v.get("true_sku_id"), "not_product": "none"}.get(
                v.get("verdict")
            )
            if label:
                out.append((a["capture_id"], [int(x) for x in b["box"]], label))
    return out


def build(
    truth: dict[str, list[dict]],
    segments: list[dict],
    frames_dir: Path,
    trn: list[dict],
    exclude_holdout: bool,
    per_keyframe: int = 30,
    min_sim: float = 0.85,
) -> Gallery:
    """The gallery from the hand-drawn truth (each box cut from up to per_keyframe frames of its segment whose box area
    still looks like the keyframe's) and from the done TRN and REV audits. Scoring frames never enter; with exclude_holdout,
    held-out keyframes and held-out TRN frames do not either."""
    import cv2

    from training.store_view.dataset import read_scoring_frames, spread
    from training.store_view.segments import holdout, signature, similarity

    scoring = read_scoring_frames(frames_dir)
    paths = {p.stem: p for p in frames_dir.glob("*/*.jpg")}
    feats, labels, sources, objects = [], [], [], []

    def add(image, box, label, source, obj):
        crop = crop_of(image, box)
        if crop is not None:
            feats.append(colour(crop))
            labels.append(label)
            sources.append(source)
            objects.append(obj)

    seg_of = {s["keyframe"]: s for s in segments if s.get("kind") == "day"}
    for key, rows in truth.items():
        seg = seg_of.get(key)
        if seg is None or key not in paths or (exclude_holdout and seg.get("split") == "holdout"):
            continue
        key_grey = cv2.imread(str(paths[key]), cv2.IMREAD_GRAYSCALE)
        usable = [
            (i, r) for i, r in enumerate(rows) if r.get("kind") != "ignore" and r.get("sku") not in (None, "unknown")
        ]
        for cid in spread([c for c in seg["members"] if c not in scoring and c in paths], per_keyframe):
            image = cv2.imread(str(paths[cid]))
            grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            for i, r in usable:
                x, y, w, h = r["box"]
                area = (max(0, x - 8), max(0, y - 8), x + w + 8, y + h + 8)
                if cid != key and similarity(signature(grey, area), signature(key_grey, area)) < min_sim:
                    continue
                add(image, r["box"], r["sku"], cid, f"truth:{key}#{i}")
    stamp = {a["capture_id"]: a.get("capture_timestamp", "") for a in trn}
    cache: dict[str, np.ndarray] = {}
    for cid, box, label in trn_rows(trn):
        if cid in scoring or cid not in paths or (exclude_holdout and stamp.get(cid) and holdout(stamp[cid])):
            continue
        if cid not in cache:
            cache.clear()
            cache[cid] = cv2.imread(str(paths[cid]))
        add(cache[cid], box, label, cid, f"trn:{cid}@{box[0]},{box[1]}")
    return Gallery(
        np.stack(feats) if feats else np.zeros((0, 144)),
        np.array(labels, dtype=str),
        np.array(sources, dtype=str),
        datetime.now().isoformat(timespec="seconds"),
        None,
        np.array(objects, dtype=str),
    )


def _export_trn(out: Path) -> int:
    import boto3
    from boto3.dynamodb.conditions import Attr

    table = boto3.resource("dynamodb", region_name=REGION_NAME).Table(AUDITS_TABLE)
    kw = {
        "FilterExpression": Attr("status").eq("done")
        & (Attr("audit_id").begins_with("TRN-") | Attr("audit_id").begins_with("REV-"))
    }
    items, resp = [], table.scan(**kw)
    items += resp["Items"]
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **kw)
        items += resp["Items"]
    keep = ("audit_id", "status", "capture_id", "capture_timestamp", "ai_boxes_json", "verdicts_json")
    out.write_text(json.dumps([{k: str(i.get(k, "")) for k in keep} for i in items], indent=1), encoding="utf-8")
    return len(items)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    e = sub.add_parser("export-trn")
    e.add_argument("--out", type=Path, required=True)
    b = sub.add_parser("build")
    b.add_argument("--truth", type=Path, required=True)
    b.add_argument("--segments", type=Path, required=True)
    b.add_argument("--frames", type=Path, required=True)
    b.add_argument("--trn", type=Path, required=True)
    b.add_argument("--exclude-holdout", action="store_true")
    b.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    if args.command == "export-trn":
        print(f"{_export_trn(args.out)} done TRN and REV audits -> {args.out}")
        return
    g = build(
        json.loads(args.truth.read_text(encoding="utf-8")),
        json.loads(args.segments.read_text(encoding="utf-8")),
        args.frames,
        json.loads(args.trn.read_text(encoding="utf-8")),
        args.exclude_holdout,
    )
    g.save(args.out)
    print(f"{len(g.labels)} crops -> {args.out}: {dict(sorted(g.counts().items()))}")


if __name__ == "__main__":
    main()
