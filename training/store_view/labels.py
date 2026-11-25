"""Keyframe boxes and the YOLO label files made from them.

A keyframe's entry in keyframes.json holds boxes [x, y, w, h] in frame pixels, and packs: a pack seen as a grid of
cartons is given by its four corners (top-left, top-right, bottom-right, bottom-left) and its rows and columns, and
each cell becomes one carton box. An entry with no boxes and no packs means: no TH carton shows in that segment.
Rule (spec 5.1): one box per TH 180ml carton whose front face or top shows enough to tell it is a TH carton; the box
covers what is visible of it.

    python -m training.store_view.labels zoom   --frames DIR --segments FILE --out DIR [--split train|holdout|all]
    python -m training.store_view.labels review --frames DIR --segments FILE --keyframes FILE --out DIR
    python -m training.store_view.labels write  --segments FILE --keyframes FILE --out DIR
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

REGION = (760, 0, 1200, 320)  # where the TH packs stand on CAM-S01-A (2560x1440)


def grid_boxes(quad: list[tuple[float, float]], rows: int, cols: int) -> list[list[int]]:
    """The box around each cell of a quad (top-left, top-right, bottom-right, bottom-left), row by row, cells found
    by bilinear interpolation of the corners."""
    tl, tr, br, bl = (np.asarray(p, dtype=float) for p in quad)

    def at(u: float, v: float) -> np.ndarray:
        top, bottom = tl + (tr - tl) * u, bl + (br - bl) * u
        return top + (bottom - top) * v

    boxes = []
    for r in range(rows):
        for c in range(cols):
            corners = [at((c + du) / cols, (r + dv) / rows) for du in (0, 1) for dv in (0, 1)]
            x0, y0 = round(min(p[0] for p in corners)), round(min(p[1] for p in corners))
            x1, y1 = round(max(p[0] for p in corners)), round(max(p[1] for p in corners))
            boxes.append([int(x0), int(y0), int(x1 - x0), int(y1 - y0)])
    return boxes


def clip_box(box: list[int], w: int, h: int) -> list[int] | None:
    """The part of a box inside a w x h frame, None when nothing is left."""
    x0, y0 = max(0, box[0]), max(0, box[1])
    x1, y1 = min(w, box[0] + box[2]), min(h, box[1] + box[3])
    if x1 <= x0 or y1 <= y0:
        return None
    return [x0, y0, x1 - x0, y1 - y0]


def boxes_of(entry: dict, w: int, h: int) -> list[list[int]]:
    """Every carton box of a keyframe entry, its own boxes first, then the cells of its packs, clipped to the frame."""
    raw = [list(b) for b in entry.get("boxes", [])]
    for pack in entry.get("packs", []):
        raw += grid_boxes(pack["quad"], pack["rows"], pack["cols"])
    return [b for b in (clip_box(box, w, h) for box in raw) if b is not None]


def to_yolo(boxes: list[list[int]], w: int, h: int, cls: int = 0) -> list[str]:
    return [f"{cls} {(x + bw / 2) / w:.6f} {(y + bh / 2) / h:.6f} {bw / w:.6f} {bh / h:.6f}" for x, y, bw, bh in boxes]


def from_yolo(lines: list[str], w: int, h: int) -> list[tuple[int, list[int]]]:
    out = []
    for line in lines:
        if not line.strip():
            continue
        cls, cx, cy, bw, bh = line.split()
        cx, cy, bw, bh = float(cx) * w, float(cy) * h, float(bw) * w, float(bh) * h
        out.append((int(cls), [round(cx - bw / 2), round(cy - bh / 2), round(bw), round(bh)]))
    return out


def write_labels(segments: list[dict], keyframes: dict, out_dir: Path, size: tuple[int, int]) -> dict[str, int]:
    """One label file per member: a day segment's members take its keyframe's boxes, negative segments' members an
    empty file. Transient segments, and day segments whose keyframe has no entry yet, get no files."""
    w, h = size
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {"labelled": 0, "negative": 0, "unlabelled_segments": 0}
    for seg in segments:
        if seg["kind"] == "negative":
            lines, key = [], "negative"
        elif seg["kind"] == "day":
            entry = keyframes.get(seg["keyframe"])
            if entry is None:
                counts["unlabelled_segments"] += 1
                continue
            lines, key = to_yolo(boxes_of(entry, w, h), w, h), "labelled"
        else:
            continue
        text = "".join(f"{line}\n" for line in lines)
        for capture_id in seg["members"]:
            (out_dir / f"{capture_id}.txt").write_text(text, encoding="utf-8")
            counts[key] += 1
    return counts


def zoom_view(image: np.ndarray, region: tuple[int, int, int, int], scale: int = 4, grid: int = 20) -> np.ndarray:
    """The region enlarged `scale` times, with a line every `grid` frame pixels and the frame coordinates written
    every 2 lines, to read box corners from."""
    import cv2

    x0, y0, x1, y1 = region
    crop = image[y0:y1, x0:x1]
    if crop.ndim == 2:
        crop = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
    big = cv2.resize(crop, (crop.shape[1] * scale, crop.shape[0] * scale), interpolation=cv2.INTER_CUBIC)
    for x in range(x0 - x0 % grid + grid, x1, grid):
        major = (x // grid) % 2 == 0
        cv2.line(
            big, ((x - x0) * scale, 0), ((x - x0) * scale, big.shape[0]), (0, 255, 255) if major else (0, 160, 160), 1
        )
        if major:
            cv2.putText(big, str(x), ((x - x0) * scale + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
    for y in range(y0 - y0 % grid + grid, y1, grid):
        major = (y // grid) % 2 == 0
        cv2.line(
            big, (0, (y - y0) * scale), (big.shape[1], (y - y0) * scale), (255, 255, 0) if major else (160, 160, 0), 1
        )
        if major:
            cv2.putText(big, str(y), (2, (y - y0) * scale - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
    return big


def draw(image: np.ndarray, boxes: list[list[int]], color: tuple[int, int, int] = (0, 0, 255)) -> np.ndarray:
    """A copy of the image with each box outlined and numbered."""
    import cv2

    out = image.copy()
    for n, (x, y, w, h) in enumerate(boxes, start=1):
        cv2.rectangle(out, (x, y), (x + w, y + h), color, 1)
        cv2.putText(out, str(n), (x + 1, y + 9), cv2.FONT_HERSHEY_SIMPLEX, 0.3, color, 1)
    return out


def _region(text: str | None) -> tuple[int, int, int, int]:
    return tuple(int(v) for v in text.split(",")) if text else REGION  # type: ignore[return-value]


def _keyframes(segments: list[dict], split: str) -> list[dict]:
    return [s for s in segments if s["kind"] == "day" and (split == "all" or s["split"] == split)]


def _frame_path(frames: Path, capture_id: str) -> Path:
    found = list(frames.glob(f"*/{capture_id}.jpg"))
    if not found:
        raise FileNotFoundError(capture_id)
    return found[0]


def main(argv: list[str] | None = None) -> None:
    import cv2

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["zoom", "review", "write"])
    ap.add_argument("--frames", type=Path)
    ap.add_argument("--segments", type=Path, required=True)
    ap.add_argument("--keyframes", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--region")
    ap.add_argument("--split", default="all", choices=["train", "holdout", "all"])
    ap.add_argument("--scale", type=int, default=4)
    args = ap.parse_args(argv)
    segments = json.loads(args.segments.read_text(encoding="utf-8"))
    args.out.mkdir(parents=True, exist_ok=True)
    region = _region(args.region)

    if args.command == "write":
        keyframes = json.loads(args.keyframes.read_text(encoding="utf-8"))
        print(write_labels(segments, keyframes, args.out, (2560, 1440)))
        return

    if args.command == "zoom":
        for seg in _keyframes(segments, args.split):
            image = cv2.imread(str(_frame_path(args.frames, seg["keyframe"])))
            name = f"{seg['id']}_{seg['split']}_{seg['keyframe']}.jpg"
            cv2.imwrite(str(args.out / name), zoom_view(image, region, args.scale), [cv2.IMWRITE_JPEG_QUALITY, 92])
        print("zoom views:", len(_keyframes(segments, args.split)))
        return

    keyframes = json.loads(args.keyframes.read_text(encoding="utf-8"))
    tiles = []
    for seg in _keyframes(segments, args.split):
        entry = keyframes.get(seg["keyframe"])
        if entry is None:
            continue
        image = cv2.imread(str(_frame_path(args.frames, seg["keyframe"])))
        boxed = draw(image, boxes_of(entry, image.shape[1], image.shape[0]))
        x0, y0, x1, y1 = region
        tile = cv2.resize(boxed[y0:y1, x0:x1], ((x1 - x0) * 2, (y1 - y0) * 2), interpolation=cv2.INTER_CUBIC)
        cv2.putText(
            tile,
            f"{seg['id']} {seg['first_ts'][5:16]} n={len(boxes_of(entry, 2560, 1440))}",
            (6, 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 0, 255),
            2,
        )
        tiles.append(tile)
    for sheet in range(0, len(tiles), 6):
        part = tiles[sheet : sheet + 6]
        while len(part) % 2:
            part.append(np.zeros_like(part[0]))
        rows = [np.hstack(part[i : i + 2]) for i in range(0, len(part), 2)]
        cv2.imwrite(str(args.out / f"review_{sheet // 6 + 1:02d}.jpg"), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])
    print("reviewed keyframes:", len(tiles))


if __name__ == "__main__":
    main()
