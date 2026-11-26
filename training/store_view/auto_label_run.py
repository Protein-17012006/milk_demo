"""The auto-labeller's commands (auto-label design 5.1). Runs on the counting machine in .venv-label.

    propose          each day segment of a split: both sources on up to --per-segment of its frames (never a scoring
                     frame), gallery reads, cans, decisions -> <out>/<segment>.json, and <out>/review.json listing the
                     cans a person has to look at
    labels           the training segments' proposals plus the people's review file -> grey-masked frames and YOLO labels
    gate1            the held-out proposals against the hand-drawn truth (design 5.7)
    draft-keyframes  YOLOE alone on some frames, to draw a new keyframe faster (any product group); with
                     --check-labels, the share of already labelled boxes the draft covers

    python -m training.store_view.auto_label_run propose --config cameras\\CAM-S01-A.json --group slide ^
        --segments S --frames F --prompts-from truth.json --gallery G.npz --slide-weights W --yoloe Y ^
        --split holdout --out DIR
    python -m training.store_view.auto_label_run gate1 --proposals DIR --truth truth.json
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import numpy as np

from training.store_view.auto_label import Decision, Track, cluster, decide
from training.store_view.auto_label_gate import failures, score
from training.store_view.auto_label_labels import apply_review, write_segment
from training.store_view.proposers import Proposal, region_prompts
from training.store_view.slide_gallery import Gallery, GalleryVote, colour, crop_of, mean_colour, read

FRAME_SIZE = (2560, 1440)


def load_group(path: Path, name: str) -> dict:
    """One product group of a camera's config: region (x0, y0, x1, y1), classes, prompts {source, keyframes}."""
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    g = cfg["groups"][name]
    return {"camera": cfg["camera"], "region": tuple(g["region"]), "classes": list(g["classes"]), "prompts": g["prompts"]}


def run_segment(
    segment_id: str,
    frame_ids: list[str],
    load: Callable[[str], np.ndarray | None],
    sources,
    gallery: Gallery,
) -> tuple[list[Track], dict[str, Decision], list[str]]:
    """The cans of one segment and their decisions; also the frames that could be read."""
    props: dict[str, list[Proposal]] = {}
    feats: dict[tuple[str, Proposal], np.ndarray] = {}
    used = []
    for cid in frame_ids:
        image = load(cid)
        if image is None:
            continue
        used.append(cid)
        props[cid] = sources.frame(image)
        for p in props[cid]:
            crop = crop_of(image, p.box)
            if crop is not None:
                feats[(cid, p)] = colour(crop)
    tracks = cluster(props, segment_id)
    counts = gallery.counts()
    for t in tracks:
        own = []
        for cid, slot in t.seen.items():
            p = slot.get("A") or slot.get("B")
            if (cid, p) in feats:
                t.votes[cid] = read(gallery, feats[(cid, p)])
                own.append(feats[(cid, p)])
        t.colour = mean_colour(own)
    return tracks, {t.id: decide(t, used, counts) for t in tracks}, used


def _track_json(t: Track) -> dict:
    return {
        "id": t.id,
        "box": list(t.box),
        "seen": {c: {s: [list(p.box), p.conf, p.sku] for s, p in slot.items()} for c, slot in t.seen.items()},
        "votes": {c: [v.sku, v.share, v.votes, v.none_hit] for c, v in t.votes.items()},
        "colour": None if t.colour is None else [round(float(v), 5) for v in t.colour],
    }


def _track_from(d: dict) -> Track:
    t = Track(d["id"], tuple(d["box"]))
    t.seen = {c: {s: Proposal(s, tuple(b), conf, sku) for s, (b, conf, sku) in slot.items()} for c, slot in d["seen"].items()}
    t.votes = {c: GalleryVote(*v) for c, v in d["votes"].items()}
    t.colour = None if d.get("colour") is None else np.array(d["colour"], dtype=float)
    return t


def load_proposals(folder: Path) -> list[dict]:
    """Each segment file: {segment, keyframe, split, frames, tracks: [Track], decisions: {id: Decision}}."""
    out = []
    for p in sorted(folder.glob("seg-*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        d["tracks"] = [_track_from(t) for t in d["tracks"]]
        d["decisions"] = {k: Decision(*v) for k, v in d["decisions"].items()}
        out.append(d)
    return out


def _paths(frames_dir: Path) -> dict[str, Path]:
    return {p.stem: p for p in frames_dir.glob("*/*.jpg")}


def propose(
    segments: list[dict],
    frames_dir: Path,
    sources,
    gallery: Gallery,
    split: str,
    per_segment: int,
    out: Path,
) -> Counter:
    import cv2

    from training.store_view.dataset import read_scoring_frames, spread

    scoring = read_scoring_frames(frames_dir)
    paths = _paths(frames_dir)
    out.mkdir(parents=True, exist_ok=True)
    review: dict[str, list[str]] = {}
    summary: Counter = Counter()
    for seg in segments:
        if seg.get("kind") != "day" or seg.get("split") != split:
            continue
        frame_ids = spread([c for c in seg["members"] if c not in scoring and c in paths], per_segment)
        tracks, decisions, used = run_segment(seg["id"], frame_ids, lambda c: cv2.imread(str(paths[c])), sources, gallery)
        (out / f"{seg['id']}.json").write_text(
            json.dumps(
                {
                    "segment": seg["id"],
                    "keyframe": seg.get("keyframe"),
                    "split": seg["split"],
                    "frames": used,
                    "tracks": [_track_json(t) for t in tracks],
                    "decisions": {k: [d.status, d.sku, d.reason] for k, d in decisions.items()},
                }
            ),
            encoding="utf-8",
        )
        summary.update(d.status for d in decisions.values())
        wanted = [k for k, d in decisions.items() if d.status == "review"]
        if wanted:
            review[seg["id"]] = wanted
    (out / "review.json").write_text(json.dumps(review, indent=1), encoding="utf-8")
    return summary


def _prompts(group: dict, prompts_from: Path, paths: dict[str, Path]):
    import cv2

    from training.store_view.labels import boxes_of

    data = json.loads(prompts_from.read_text(encoding="utf-8"))
    images, boxes = [], []
    for key in group["prompts"]["keyframes"]:
        if group["prompts"]["source"] == "truth":
            rows = data[key]
        else:  # TH keyframes.json: own boxes plus pack cells
            rows = [{"box": b, "kind": "face"} for b in boxes_of(data[key], *FRAME_SIZE)]
        images.append(cv2.imread(str(paths[key])))
        boxes.append(region_prompts(rows, group["region"]))
    return images, boxes


def window_around(region: tuple[int, int, int, int], size: tuple[int, int] = FRAME_SIZE, side: int = 1280):
    """A side x side window of the frame, at native size, starting at the region's corner and pushed back inside."""
    x0 = max(0, min(region[0], size[0] - side))
    y0 = max(0, min(region[1], size[1] - side))
    return (x0, y0, x0 + side, y0 + side)


def _detector_boxes(model, image, group: dict, conf: float = 0.1) -> list[Proposal]:
    """The group's classes found by a store-view detector on a native-size window around the region."""
    from training.store_view.proposers import in_region

    wx0, wy0, wx1, wy1 = window_around(group["region"], (image.shape[1], image.shape[0]))
    r = model.predict(image[wy0:wy1, wx0:wx1], imgsz=wx1 - wx0, conf=conf, verbose=False)[0]
    out = []
    for (bx0, by0, bx1, by1), c, k in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist(), strict=True):
        p = Proposal("B", (bx0 + wx0, by0 + wy0, bx1 - bx0, by1 - by0), float(c), None)
        if model.names[int(k)] in group["classes"] and in_region(p.box, group["region"]):
            out.append(p)
    return out


def _draft(args) -> None:
    import cv2

    from training.store_view.labels import from_yolo
    from training.store_view.proposers import Sources

    group = load_group(args.config, args.group)
    paths = _paths(args.frames)
    if args.detector:  # a group that has a detector of its own (TH): its boxes beat YOLOE's visual prompts
        from ultralytics import YOLO

        model = YOLO(str(args.detector))

        def find(image):
            return _detector_boxes(model, image, group)
    else:
        images, boxes = _prompts(group, args.prompts_from, paths)
        find = Sources(None, str(args.yoloe), images, boxes, group["region"]).frame
    args.out.mkdir(parents=True, exist_ok=True)
    x0, y0, x1, y1 = group["region"]
    for cid in args.keyframes:
        image = cv2.imread(str(paths[cid]))
        found = find(image)
        (args.out / f"{cid}.json").write_text(json.dumps([[*p.box, p.conf] for p in found]), encoding="utf-8")
        sheet = image.copy()
        for p in found:
            bx, by, bw, bh = (int(round(v)) for v in p.box)
            cv2.rectangle(sheet, (bx, by), (bx + bw, by + bh), (0, 220, 0), 1)
        cv2.imwrite(str(args.out / f"{cid}.jpg"), cv2.resize(sheet[y0:y1, x0:x1], None, fx=3, fy=3))
        line = f"{cid}: {len(found)} draft boxes"
        if args.check_labels and (args.check_labels / f"{cid}.txt").is_file():
            truth = [b for _, b in from_yolo((args.check_labels / f"{cid}.txt").read_text().splitlines(), *FRAME_SIZE)]
            hit = sum(
                any(x <= p.box[0] + p.box[2] / 2 <= x + w and y <= p.box[1] + p.box[3] / 2 <= y + h for p in found)
                for x, y, w, h in truth
            )
            line += f"; covers {hit}/{len(truth)} labelled boxes"
        print(line)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("propose")
    for name in ("--config", "--segments", "--frames", "--prompts-from", "--gallery", "--slide-weights", "--yoloe", "--out"):
        p.add_argument(name, type=Path, required=True)
    p.add_argument("--group", default="slide")
    p.add_argument("--split", choices=["train", "holdout"], required=True)
    p.add_argument("--per-segment", type=int, default=30)
    lab = sub.add_parser("labels")
    for name in ("--proposals", "--frames", "--config", "--segments", "--out"):
        lab.add_argument(name, type=Path, required=True)
    lab.add_argument("--review", type=Path)
    lab.add_argument("--group", default="slide")
    g = sub.add_parser("gate1")
    g.add_argument("--proposals", type=Path, required=True)
    g.add_argument("--truth", type=Path, required=True)
    d = sub.add_parser("draft-keyframes")
    for name in ("--config", "--frames", "--out"):
        d.add_argument(name, type=Path, required=True)
    d.add_argument("--prompts-from", type=Path, help="truth.json or keyframes.json (YOLOE drafts)")
    d.add_argument("--yoloe", type=Path)
    d.add_argument("--detector", type=Path, help="the group's own detector (TH: best_store_v1.pt) instead of YOLOE")
    d.add_argument("--group", required=True)
    d.add_argument("--keyframes", nargs="+", required=True)
    d.add_argument("--check-labels", type=Path)
    args = ap.parse_args(argv)

    if args.command == "draft-keyframes":
        _draft(args)
        return
    if args.command == "gate1":
        props = load_proposals(args.proposals)
        truth = json.loads(args.truth.read_text(encoding="utf-8"))
        summary = score(
            {p["segment"]: (p["tracks"], p["decisions"]) for p in props}, truth, {p["segment"]: p["keyframe"] for p in props}
        )
        print("  ".join(f"{k} {summary[k]:.3f}" if summary[k] is not None else f"{k} -" for k in
                        ("real", "flavour", "coverage", "review_share")), json.dumps(summary["counts"]))
        fails = failures(summary)
        print("gate 1 passed" if not fails else "gate 1 FAILED: " + "; ".join(fails))
        return
    if args.command == "labels":
        from training.store_view.dataset import read_scoring_frames

        group = load_group(args.config, args.group)
        segs = {s["id"]: s for s in json.loads(args.segments.read_text(encoding="utf-8"))}
        review = json.loads(args.review.read_text(encoding="utf-8")) if args.review else {}
        scoring, paths, total = read_scoring_frames(args.frames), _paths(args.frames), Counter()
        for p in load_proposals(args.proposals):
            entry = review.get(p["segment"], {})
            decisions = apply_review(p["decisions"], entry)
            total += write_segment(segs[p["segment"]], p["frames"], paths, p["tracks"], decisions, group["classes"],
                                   entry.get("missed", []), args.out, never=scoring)
        print(json.dumps(dict(total)))
        return

    import cv2  # noqa: F401  (frames are read inside propose)

    from training.store_view.proposers import Sources

    group = load_group(args.config, args.group)
    paths = _paths(args.frames)
    images, boxes = _prompts(group, args.prompts_from, paths)
    sources = Sources(str(args.slide_weights), str(args.yoloe), images, boxes, group["region"])
    gallery = Gallery.load(args.gallery)
    segments = json.loads(args.segments.read_text(encoding="utf-8"))
    summary = propose(segments, args.frames, sources, gallery, args.split, args.per_segment, args.out)
    print(json.dumps(dict(summary)), "->", args.out)


if __name__ == "__main__":
    main()
