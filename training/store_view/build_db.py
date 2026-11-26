"""The milk database v2: real TH carton crops from the store's frames, the detector's mistakes as "none", and a
similarity threshold set on validation crops.

The worker looks boxes up in the type database (Recognizer(types=True): embedder_types.pt and db_types/ of its
MILK_LONG_DIR), so crops go there, cut exactly as the worker cuts them (embedder.crop_box, margin 0.06). Long's
enroll.py writes to the brand database instead (db/, embedder.pt) and is not used. Run on the counting machine, in a
copy of carton_recognition (TRAINING.md section 3), never in the folder the worker reads:

    python -m training.store_view.build_db enrol     --long-dir ...\\carton_recognition_v2 --segments S --labels L --frames F
    python -m training.store_view.build_db negatives --long-dir ... --segments S --labels L --frames F --yolo W --tile 1280
    python -m training.store_view.build_db threshold --long-dir ... --segments S --labels L --frames F --yolo W --tile 1280
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from training.store_view.dataset import KEYFRAME_SIZE, assign, read_scoring_frames, spread
from training.store_view.labels import from_yolo


def crop_jobs(
    segments: list[dict],
    labels_dir: Path,
    part: str,
    share: float = 0.1,
    per_segment: int = 40,
    never: set[str] = frozenset(),
) -> list[tuple[str, list[int]]]:
    """(capture_id, box x, y, w, h) of every labelled carton in up to per_segment frames of each day segment of the
    training days' `part` (train or val). Held-out frames and the frames in `never` (scoring frames) are never
    cropped."""
    if part not in ("train", "val"):
        raise ValueError(f"crops come from the training days only (train or val), not {part!r}")
    parts = assign(segments, share, never)
    jobs = []
    for seg in segments:
        if seg["kind"] != "day":
            continue
        for cid in spread([c for c in seg["members"] if parts.get(c) == part], per_segment):
            label = labels_dir / f"{cid}.txt"
            if label.is_file():
                jobs += [(cid, box) for _, box in from_yolo(label.read_text().splitlines(), *KEYFRAME_SIZE)]
    return jobs


def is_negative(det: list[float], labelled: list[list[int]]) -> bool:
    """A detection (x0, y0, x1, y1) is a mistake unless its centre lies in a labelled carton (x, y, w, h)."""
    cx, cy = (det[0] + det[2]) / 2, (det[1] + det[3]) / 2
    return not any(x <= cx <= x + w and y <= cy <= y + h for x, y, w, h in labelled)


def pick_threshold(pos: list[float], keep: float = 0.98) -> float:
    """The highest similarity threshold that still accepts `keep` of the positive crops."""
    if not pos:
        raise ValueError("no positive crops")
    ordered = sorted(pos)
    return float(ordered[int(math.floor((1 - keep) * len(ordered) + 1e-9))])


def _long(long_dir: Path):
    import torch  # noqa: F401  first on Windows, before cv2 and lancedb (server/milk/torch_first.py)

    sys.path.insert(0, str(long_dir))
    import build_db as long_db  # Long's build_db.py: to_table, TABLE
    import embedder
    import recognize

    return long_db, embedder, recognize


def _frames_index(frames: Path) -> dict[str, Path]:
    return {p.stem: p for p in frames.glob("*/*.jpg")}


def _crops(jobs, paths, crop_box):
    import cv2

    crops, meta, cache = [], [], {}
    for cid, (x, y, w, h) in jobs:
        if cid not in cache:
            cache.clear()
            cache[cid] = cv2.imread(str(paths[cid]))
        crops.append(crop_box(cache[cid], [x, y, x + w, y + h]))
        meta.append({"image": cid, "box": f"{x},{y},{x + w},{y + h}"})
    return crops, meta


def _mistakes(segments, labels_dir, frames, part, yolo_path, tile, recognize, per_segment, share, never):
    """(capture_id, box) of detector boxes that are not labelled cartons, on the part's day and negative frames;
    never on the frames in `never` (scoring frames)."""
    import cv2
    from ultralytics import YOLO

    yolo = YOLO(str(yolo_path))
    parts = assign(segments, share, never)
    jobs = []
    for seg in segments:
        if seg["kind"] not in ("day", "negative"):
            continue
        for cid in spread([c for c in seg["members"] if parts.get(c) == part], per_segment):
            label = labels_dir / f"{cid}.txt"
            if cid not in frames or not label.is_file():
                continue
            labelled = [box for _, box in from_yolo(label.read_text().splitlines(), *KEYFRAME_SIZE)]
            image = cv2.imread(str(frames[cid]))
            for row in recognize.detect(image, yolo, "cuda", 0.25, 1280, tile=tile):
                if is_negative(list(row[:4]), labelled):
                    x0, y0, x1, y1 = (int(round(v)) for v in row[:4])
                    jobs.append((cid, [x0, y0, x1 - x0, y1 - y0]))
    return jobs


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["enrol", "negatives", "threshold"])
    ap.add_argument("--long-dir", type=Path, required=True, help="the copy of carton_recognition to build")
    ap.add_argument("--segments", type=Path, required=True)
    ap.add_argument("--labels", type=Path, required=True)
    ap.add_argument("--frames", type=Path, required=True)
    ap.add_argument("--yolo", type=Path)
    ap.add_argument("--tile", type=int, default=1280)
    ap.add_argument("--per-segment", type=int, default=40)
    ap.add_argument("--share", type=float, default=0.1)
    ap.add_argument("--keep", type=float, default=0.98)
    args = ap.parse_args(argv)
    if (args.long_dir / "db_types").resolve() == Path("C:/Users/huyho/Datagent/carton_recognition/db_types").resolve():
        raise SystemExit("refusing to write to the database the worker reads: use a copy (carton_recognition_v2)")
    long_db, embedder, recognize = _long(args.long_dir)
    segments = json.loads(args.segments.read_text(encoding="utf-8"))
    scoring = read_scoring_frames(args.frames)
    frames = _frames_index(args.frames)
    emb = embedder.Embedder(device="cuda", types=True)

    if args.command in ("enrol", "negatives"):
        if args.command == "enrol":
            jobs = crop_jobs(segments, args.labels, "train", args.share, args.per_segment, scoring)
            brand = kind = "th_true_milk"
        else:
            jobs = _mistakes(
                segments, args.labels, frames, "train", args.yolo, args.tile, recognize, 20, args.share, scoring
            )
            brand = kind = "none"
        crops, meta = _crops(jobs, frames, embedder.crop_box)
        if not crops:
            raise SystemExit("nothing to enrol")
        for m in meta:
            m.update(brand=brand, kind=kind, source="store_view", note="CAM-S01-A, store-view design 2026-11-25")
        import lancedb

        table = lancedb.connect(str(embedder.named("db", True))).open_table(long_db.TABLE)
        table.add(long_db.to_table(emb.embed(crops), meta))
        print(f"enrolled {len(crops)} crops as {brand}; db_types now holds {table.count_rows()} vectors")
        return

    rec = recognize.Recognizer(device="cuda", types=True, strict=False)
    pos_crops, _ = _crops(
        crop_jobs(segments, args.labels, "val", args.share, args.per_segment, scoring), frames, embedder.crop_box
    )
    neg_jobs = _mistakes(segments, args.labels, frames, "val", args.yolo, args.tile, recognize, 20, args.share, scoring)
    neg_crops, _ = _crops(neg_jobs, frames, embedder.crop_box)
    pos = rec.lookup(emb.embed(pos_crops)) if pos_crops else []
    neg = rec.lookup(emb.embed(neg_crops)) if neg_crops else []
    threshold = pick_threshold([p["similarity"] for p in pos if p["guess"] == "th_true_milk"], args.keep)
    config = embedder.named("config.json", True)
    old = json.loads(config.read_text()) if config.exists() else {}
    config.write_text(json.dumps({"min_margin": old.get("min_margin", 0.0), "min_similarity": threshold}, indent=1))
    th_ok = sum(p["guess"] == "th_true_milk" and p["similarity"] >= threshold for p in pos)
    neg_in = sum(n["guess"] != "none" and n["similarity"] >= threshold for n in neg)
    print(f"min_similarity {threshold:.4f} -> {config}")
    print(f"val TH crops accepted as TH: {th_ok}/{len(pos)}; val mistakes still accepted: {neg_in}/{len(neg)}")


if __name__ == "__main__":
    main()
