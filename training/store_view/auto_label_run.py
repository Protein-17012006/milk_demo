"""The auto-labeller's commands (auto-label design 5.1, 5.4b). Runs on the counting machine in .venv-label.

propose          each day segment of a split: both sources on up to --per-segment of its frames (never a scoring
                 frame), gallery reads, colours, cans, decisions -> <out>/<segment>.json
queue            the proposals of a split after reusing people's decisions (train-side truth, TRN verdicts, the
                 review file): <proposals>/queue.json lists the segments that need a new review frame and the cans
                 a person decides there
labels           the training segments' proposals, people's decisions reused -> grey-masked frames and YOLO labels
gate1            the held-out proposals against the hand-drawn truth, people simulated by the truth (design 5.7)
reuse-pairs      how alike the colours of the train-side truth's same-place cans are: the reuse threshold
draft-keyframes  YOLOE alone on some frames, to draw a new keyframe faster (any product group); with
                 --check-labels, the share of already labelled boxes the draft covers

python -m training.store_view.auto_label_run propose --config cameras\\CAM-S01-A.json --group slide ^
    --segments S --frames F --prompts-from truth.json --gallery G.npz --slide-weights W --yoloe Y ^
    --split holdout --out DIR
python -m training.store_view.auto_label_run queue --proposals DIR --truth truth.json --segments S --frames F ^
    [--trn trn_done.json] [--review review.json]
python -m training.store_view.auto_label_run gate1 --proposals DIR --truth truth.json --segments S --frames F ^
    [--trn trn_done.json]
python -m training.store_view.auto_label_run reuse-pairs --truth truth.json --segments S --frames F
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import numpy as np

from training.store_view.auto_label import Decision, Track, cluster, decide
from training.store_view.auto_label_gate import failures, simulate
from training.store_view.auto_label_labels import apply_review, write_segment
from training.store_view.auto_label_reuse import (
    REUSE_MIN_SIM,
    Precedent,
    pair_stats,
    queue,
    review_precedents,
    suggest_min_sim,
    trn_precedents,
    truth_precedents,
)
from training.store_view.proposers import Proposal, region_prompts
from training.store_view.slide_gallery import (
    Gallery,
    GalleryVote,
    colour,
    crop_of,
    mean_colour,
    read,
    trn_rows,
)

FRAME_SIZE = (2560, 1440)


def load_group(path: Path, name: str) -> dict:
    """One product group of a camera's config: region (x0, y0, x1, y1), classes, prompts {source, keyframes}."""
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    g = cfg["groups"][name]
    return {
        "camera": cfg["camera"],
        "region": tuple(g["region"]),
        "classes": list(g["classes"]),
        "prompts": g["prompts"],
    }


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
    t.seen = {
        c: {s: Proposal(s, tuple(b), conf, sku) for s, (b, conf, sku) in slot.items()} for c, slot in d["seen"].items()
    }
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
    summary: Counter = Counter()
    for seg in segments:
        if seg.get("kind") != "day" or seg.get("split") != split:
            continue
        frame_ids = spread([c for c in seg["members"] if c not in scoring and c in paths], per_segment)
        tracks, decisions, used = run_segment(
            seg["id"], frame_ids, lambda c: cv2.imread(str(paths[c])), sources, gallery
        )
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
    return summary


def _loader(frames_dir: Path) -> Callable[[str], np.ndarray | None]:
    import cv2

    paths = _paths(frames_dir)
    return lambda cid: cv2.imread(str(paths[cid])) if cid in paths else None


def human_precedents(
    truth_path: Path, segments: list[dict], frames_dir: Path, trn_path: Path | None
) -> list[Precedent]:
    """People's decisions a can may reuse (design 5.4b): the truth of train-side keyframes and the done TRN verdicts.
    Never a scoring frame (AUD), never a held-out keyframe or TRN frame."""
    from training.store_view.dataset import read_scoring_frames
    from training.store_view.segments import holdout

    scoring = read_scoring_frames(frames_dir)
    load = _loader(frames_dir)
    truth = json.loads(Path(truth_path).read_text(encoding="utf-8"))
    keys = sorted(
        s["keyframe"]
        for s in segments
        if s.get("kind") == "day"
        and s.get("split") == "train"
        and s.get("keyframe") in truth
        and s["keyframe"] not in scoring
    )
    out = truth_precedents(truth, keys, load)
    if trn_path:
        audits = json.loads(Path(trn_path).read_text(encoding="utf-8"))
        stamp = {a["capture_id"]: a.get("capture_timestamp", "") for a in audits}
        rows = [r for r in trn_rows(audits) if r[0] not in scoring and not (stamp.get(r[0]) and holdout(stamp[r[0]]))]
        out += trn_precedents(rows, load)
    return out


def _precedents(args, proposals: list[dict], review: dict) -> list[Precedent]:
    segments = json.loads(args.segments.read_text(encoding="utf-8"))
    return human_precedents(args.truth, segments, args.frames, args.trn) + review_precedents(proposals, review)


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
    for (bx0, by0, bx1, by1), c, k in zip(
        r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist(), strict=True
    ):
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
    for name in (
        "--config",
        "--segments",
        "--frames",
        "--prompts-from",
        "--gallery",
        "--slide-weights",
        "--yoloe",
        "--out",
    ):
        p.add_argument(name, type=Path, required=True)
    p.add_argument("--group", default="slide")
    p.add_argument("--split", choices=["train", "holdout"], required=True)
    p.add_argument("--per-segment", type=int, default=30)
    q = sub.add_parser("queue")
    for name in ("--proposals", "--truth", "--segments", "--frames"):
        q.add_argument(name, type=Path, required=True)
    q.add_argument("--trn", type=Path)
    q.add_argument("--review", type=Path)
    lab = sub.add_parser("labels")
    for name in ("--proposals", "--frames", "--config", "--segments", "--truth", "--out"):
        lab.add_argument(name, type=Path, required=True)
    lab.add_argument("--trn", type=Path)
    lab.add_argument("--review", type=Path)
    lab.add_argument("--group", default="slide")
    g = sub.add_parser("gate1")
    for name in ("--proposals", "--truth", "--segments", "--frames"):
        g.add_argument(name, type=Path, required=True)
    g.add_argument("--trn", type=Path)
    rp = sub.add_parser("reuse-pairs")
    for name in ("--truth", "--segments", "--frames"):
        rp.add_argument(name, type=Path, required=True)
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
    if args.command == "reuse-pairs":
        segments = json.loads(args.segments.read_text(encoding="utf-8"))
        pairs = pair_stats(human_precedents(args.truth, segments, args.frames, None))
        same = sorted(sim for sim, equal in pairs if equal)
        different = sorted(sim for sim, equal in pairs if not equal)
        if same:
            print(
                f"same label: {len(same)} pairs, percentiles 1/5/50 = "
                + " / ".join(f"{np.percentile(same, q):.4f}" for q in (1, 5, 50))
            )
        print(f"different label: {len(different)} pairs" + (f", most alike {different[-1]:.4f}" if different else ""))
        print(f"suggested REUSE_MIN_SIM {suggest_min_sim(pairs):.4f}")
        return
    if args.command == "gate1":
        props = load_proposals(args.proposals)
        truth = json.loads(args.truth.read_text(encoding="utf-8"))
        summary = simulate(props, truth, _precedents(args, props, {}), REUSE_MIN_SIM)
        print(
            "  ".join(
                f"{k} {summary[k]:.3f}" if summary[k] is not None else f"{k} -"
                for k in ("real", "flavour", "coverage", "review_share", "reuse_right")
            ),
            json.dumps(summary["counts"]),
        )
        fails = failures(summary)
        print("gate 1 passed" if not fails else "gate 1 FAILED: " + "; ".join(fails))
        return
    review = json.loads(args.review.read_text(encoding="utf-8")) if getattr(args, "review", None) else {}
    if args.command == "queue":
        props = load_proposals(args.proposals)
        r = queue(props, _precedents(args, props, review), REUSE_MIN_SIM)
        (args.proposals / "queue.json").write_text(json.dumps(r.new_frames, indent=1), encoding="utf-8")
        reasons = Counter(d.reason.split(":")[0] for ds in r.decisions.values() for d in ds.values())
        print(
            json.dumps(
                {
                    "segments": len(props),
                    "new_frames": len(r.new_frames),
                    "reused": len(r.links),
                    "waiting": reasons["waits"],
                    "conflict": reasons["reuse_conflict"],
                }
            )
        )
        return
    if args.command == "labels":
        from training.store_view.dataset import read_scoring_frames

        group = load_group(args.config, args.group)
        segs = {s["id"]: s for s in json.loads(args.segments.read_text(encoding="utf-8"))}
        props = load_proposals(args.proposals)
        for p in props:
            p["decisions"] = apply_review(p["decisions"], review.get(p["segment"], {}))
        r = queue(props, _precedents(args, props, review), REUSE_MIN_SIM)
        scoring, paths, total = read_scoring_frames(args.frames), _paths(args.frames), Counter()
        for p in props:
            total += write_segment(
                segs[p["segment"]],
                p["frames"],
                paths,
                p["tracks"],
                r.decisions[p["segment"]],
                group["classes"],
                review.get(p["segment"], {}).get("missed", []),
                args.out,
                never=scoring,
            )
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
