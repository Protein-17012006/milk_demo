"""The training set of the store-view milk detector: real frames cut into native-size windows, plus Long's synthetic
set with the two TH classes merged into one.

Real frames: each train or val segment gives up to `per_segment` frames spread over its time. A frame with cartons
gives every window holding one whole (at least 60% of it), plus one window touching none. A negative frame (the
cabinet packed away) gives windows without cartons, always the one showing the gap under the freezer, where a white
bottle was read as TH at night. Held-out segments never enter; val is chosen by segment, never by frame.

    python -m training.store_view.dataset --segments S.json --frames DIR --labels DIR --synthetic DIR --out DIR
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import zlib
from collections import Counter
from pathlib import Path

import numpy as np

from training.store_view.labels import from_yolo, to_yolo

NAMES = [
    "th_true_milk",
    "vinamilk_banana",
    "vinamilk_soy",
    "vinamilk_fresh_less_sugar",
    "vinamilk_chocolate",
    "vinamilk_fresh_no_sugar",
    "vinamilk_fresh_sweetened",
    "vinamilk_soy_black_sesame",
    "vinamilk_soy_almond",
    "vinamilk_melon",
    "vinamilk_9_seeds",
]
GHOST = [850, 40, 200, 180]  # x, y, w, h: the gap under the freezer, seen when the cabinet is packed away
WINDOW = 1280
KEYFRAME_SIZE = (2560, 1440)  # label files are written for this size (labels.write_labels)


def remap_synthetic(old: int) -> int:
    """Long's 12 type classes to the 11 classes here: both TH types become th_true_milk, the rest move down one."""
    if old in (0, 1):
        return 0
    if 2 <= old <= 11:
        return old - 1
    raise ValueError(f"unknown synthetic class {old}")


def windows(w: int, h: int, size: int = WINDOW, overlap: float = 0.3) -> list[tuple[int, int, int, int]]:
    """Overlapping size x size windows covering a w x h frame: the rule of recognize.tiles() that the worker uses."""
    step = max(int(size * (1 - overlap)), 1)
    xs = sorted({min(x, max(w - size, 0)) for x in range(0, max(w - size, 0) + step, step)})
    ys = sorted({min(y, max(h - size, 0)) for y in range(0, max(h - size, 0) + step, step)})
    return [(x, y, min(x + size, w), min(y + size, h)) for y in ys for x in xs]


def clip_to_window(
    boxes: list[list[int]], window: tuple[int, int, int, int], min_inside: float = 0.6
) -> list[list[int]]:
    """Boxes in window coordinates; a box with less than min_inside of its area in the window is left out."""
    x0, y0, x1, y1 = window
    out = []
    for x, y, bw, bh in boxes:
        ix0, iy0, ix1, iy1 = max(x, x0), max(y, y0), min(x + bw, x1), min(y + bh, y1)
        if ix1 <= ix0 or iy1 <= iy0 or (ix1 - ix0) * (iy1 - iy0) < min_inside * bw * bh:
            continue
        out.append([ix0 - x0, iy0 - y0, ix1 - ix0, iy1 - iy0])
    return out


def _touches(box: list[int], window: tuple[int, int, int, int]) -> bool:
    x, y, bw, bh = box
    return x < window[2] and window[0] < x + bw and y < window[3] and window[1] < y + bh


def _covers(window: tuple[int, int, int, int], box: list[int]) -> bool:
    x, y, bw, bh = box
    return window[0] <= x and window[1] <= y and window[2] >= x + bw and window[3] >= y + bh


def val_segments(segment_ids: list[str], share: float = 0.1) -> set[str]:
    """A stable choice of about `share` of the segments: the same ids give the same choice on any machine."""
    return {i for i in segment_ids if zlib.crc32(i.encode()) % 10000 < share * 10000}


def assign(segments: list[dict], share: float = 0.1) -> dict[str, str]:
    """capture_id -> "train" or "val" for the members of the training day and negative segments; held-out and
    transient segments get nothing."""
    usable = [s for s in segments if s["split"] == "train" and s["kind"] in ("day", "negative")]
    val = val_segments([s["id"] for s in usable], share)
    return {cid: ("val" if s["id"] in val else "train") for s in usable for cid in s["members"]}


def frame_samples(
    size: tuple[int, int],
    keyframe_size: tuple[int, int],
    boxes: list[list[int]],
    negatives: int,
    rng: random.Random,
) -> list[tuple[tuple[int, int, int, int], list[list[int]]]]:
    """(window, boxes in window coordinates) to cut from one frame. A frame of another size than its keyframe gives
    none: its labels would not fit."""
    if size != keyframe_size:
        return []
    wins = windows(*size)
    if boxes:
        samples = [(win, inside) for win in wins if (inside := clip_to_window(boxes, win))]
        empty = [win for win in wins if not any(_touches(b, win) for b in boxes)]
        rng.shuffle(empty)
        return samples + [(win, []) for win in empty[:negatives]]
    ghost = [win for win in wins if _covers(win, GHOST)][:1]
    others = [win for win in wins if win not in ghost]
    rng.shuffle(others)
    return [(win, []) for win in ghost + others[: max(negatives - len(ghost), 0)]]


def _link_or_copy(src: Path, dst: Path) -> None:
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _spread(members: list[str], n: int) -> list[str]:
    if len(members) <= n:
        return members
    return [members[i] for i in sorted({int(round(v)) for v in np.linspace(0, len(members) - 1, n)})]


def build(
    segments: list[dict],
    frames_dir: Path,
    labels_dir: Path,
    synth_dir: Path,
    out: Path,
    share: float = 0.1,
    per_segment: int = 60,
    seed: int = 0,
    negatives_per_frame: int = 1,
) -> dict[str, int]:
    import cv2

    rng = random.Random(seed)
    parts = assign(segments, share)
    for part in ("train", "val"):
        (out / "images" / part).mkdir(parents=True, exist_ok=True)
        (out / "labels" / part).mkdir(parents=True, exist_ok=True)
    paths = {p.stem: p for p in frames_dir.glob("*/*.jpg")}
    counts: Counter = Counter()
    kw, kh = KEYFRAME_SIZE
    for seg in segments:
        chosen = [cid for cid in seg["members"] if cid in parts]
        for cid in _spread(chosen, per_segment):
            label_file = labels_dir / f"{cid}.txt"
            if cid not in paths or not label_file.is_file():
                counts["skipped_no_file"] += 1
                continue
            image = cv2.imread(str(paths[cid]))
            if image is None:
                counts["skipped_unreadable"] += 1
                continue
            boxes = [box for _, box in from_yolo(label_file.read_text().splitlines(), kw, kh)]
            samples = frame_samples((image.shape[1], image.shape[0]), KEYFRAME_SIZE, boxes, negatives_per_frame, rng)
            if not samples:
                counts["skipped_size"] += 1
            for (x0, y0, x1, y1), inside in samples:
                name = f"real_{cid}_{x0}_{y0}"
                part = parts[cid]
                cv2.imwrite(
                    str(out / "images" / part / f"{name}.jpg"), image[y0:y1, x0:x1], [cv2.IMWRITE_JPEG_QUALITY, 95]
                )
                lines = to_yolo(inside, x1 - x0, y1 - y0)
                (out / "labels" / part / f"{name}.txt").write_text("".join(f"{line}\n" for line in lines))
                counts[f"real_{part}_{'th' if inside else 'empty'}"] += 1
    for part in ("train", "val"):
        for image in sorted((synth_dir / "images" / part).glob("*.jpg")):
            label = synth_dir / "labels" / part / f"{image.stem}.txt"
            _link_or_copy(image, out / "images" / part / f"synth_{image.name}")
            lines = []
            for line in label.read_text().splitlines() if label.is_file() else []:
                cls, rest = line.split(maxsplit=1)
                lines.append(f"{remap_synthetic(int(cls))} {rest}")
            (out / "labels" / part / f"synth_{image.stem}.txt").write_text("".join(f"{line}\n" for line in lines))
            counts[f"synthetic_{part}"] += 1
    every_val = [f"./images/val/synth_{p.name}" for p in sorted((synth_dir / "images" / "val").glob("*.jpg"))]
    for k in range(1, 6):
        own = synth_dir / f"val_L{k}.txt"
        listed = (
            [f"./images/val/synth_{Path(line.strip()).name}" for line in own.read_text().splitlines() if line.strip()]
            if own.is_file()
            else every_val
        )
        (out / f"val_L{k}.txt").write_text("".join(f"{line}\n" for line in listed))
    names = "".join(f"  {i}: {n}\n" for i, n in enumerate(NAMES))
    (out / "data.yaml").write_text(f"path: {out.resolve()}\ntrain: images/train\nval: images/val\nnames:\n{names}")
    (out / "README.txt").write_text(json.dumps(dict(sorted(counts.items())), indent=1) + "\n")
    return dict(counts)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--segments", type=Path, required=True)
    ap.add_argument("--frames", type=Path, required=True, help="camera folder: <day>/<capture_id>.jpg")
    ap.add_argument("--labels", type=Path, required=True, help="store_labels\\yolo")
    ap.add_argument("--synthetic", type=Path, required=True, help="Long's dataset with type labels (12 classes)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--share", type=float, default=0.1)
    ap.add_argument("--per-segment", type=int, default=60)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)
    segments = json.loads(args.segments.read_text(encoding="utf-8"))
    counts = build(
        segments, args.frames, args.labels, args.synthetic, args.out, args.share, args.per_segment, args.seed
    )
    print(json.dumps(counts, indent=1))


if __name__ == "__main__":
    main()
