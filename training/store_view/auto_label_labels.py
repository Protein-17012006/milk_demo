"""People's decisions on the auto-labeller's cans, and the labels written from them (auto-label design 5.5-5.6).

The review file (written by the Model page's Review frames, part 2) holds, per segment, a verdict for each track a
person looked at, and the points of cans the machine missed:

    {"<segment id>": {"tracks": {"<track id>": {"verdict": "sku", "sku": "original145"}}, "missed": [[x, y]]}}

verdict "sku" names the flavour, "not_product" drops the box, "out_of_scope" leaves the can unlabelled (status
"masked"). A can the labels do not name must never look like background to the detector, so it is painted grey (127)
on the copy of the frame: cans still under review, out of scope, hidden in that very frame, and the missed points.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from training.store_view.auto_label import Decision, Track
from training.store_view.labels import to_yolo

FRAME_SIZE = (2560, 1440)
GREY = 127


def apply_review(decisions: dict[str, Decision], review: dict) -> dict[str, Decision]:
    out = dict(decisions)
    for tid, v in (review or {}).get("tracks", {}).items():
        verdict = v.get("verdict")
        if verdict == "sku":
            out[tid] = Decision("accept", v["sku"], "human")
        elif verdict == "not_product":
            out[tid] = Decision("drop", None, "human_not_product")
        elif verdict == "out_of_scope":
            out[tid] = Decision("masked", None, "out_of_scope")
    return out


def _int_box(box) -> tuple[int, int, int, int]:
    return tuple(int(round(v)) for v in box)


def frame_labels(
    capture_id: str,
    tracks: list[Track],
    decisions: dict[str, Decision],
    classes: list[str],
    missed: list[list[float]],
    mask_radius: int = 40,
    size: tuple[int, int] = FRAME_SIZE,
) -> tuple[list[str], list[tuple[int, int, int, int]]]:
    """YOLO lines and grey areas (x, y, w, h) of one frame."""
    lines, masks = [], []
    for t in tracks:
        d = decisions.get(t.id)
        if d is None or d.status == "drop":
            continue
        own = t.box_in(capture_id)
        if d.status == "accept":
            if d.sku not in classes:
                raise ValueError(f"{t.id}: flavour {d.sku!r} is not one of the classes {classes}")
            if own is not None:
                lines += to_yolo([list(own)], *size, cls=classes.index(d.sku))
                continue
        masks.append(_int_box(own if own is not None else t.box))
    for x, y in missed:
        masks.append((int(round(x)) - mask_radius, int(round(y)) - mask_radius, 2 * mask_radius, 2 * mask_radius))
    return lines, masks


def write_segment(
    segment: dict,
    frames: list[str],
    paths: dict[str, Path],
    tracks: list[Track],
    decisions: dict[str, Decision],
    classes: list[str],
    missed: list[list[float]],
    out: Path,
    never: set[str] = frozenset(),
    mask_radius: int = 40,
) -> Counter:
    """A grey-masked copy and a YOLO label file for each frame of a training segment; never a scoring frame, nothing
    from a held-out segment, nothing from a segment too short to decide."""
    import cv2

    counts: Counter = Counter()
    if segment.get("split") != "train":
        counts["skipped_holdout"] += len(frames)
        return counts
    if any(d.status == "too_short" for d in decisions.values()):
        counts["skipped_too_short"] += len(frames)
        return counts
    for cid in frames:
        if cid in never:
            counts["skipped_scoring"] += 1
            continue
        if cid not in paths:
            counts["skipped_missing"] += 1
            continue
        image = cv2.imread(str(paths[cid]))
        if image is None:
            counts["skipped_unreadable"] += 1
            continue
        lines, masks = frame_labels(
            cid, tracks, decisions, classes, missed, mask_radius, (image.shape[1], image.shape[0])
        )
        for x, y, w, h in masks:
            image[max(y, 0) : max(y + h, 0), max(x, 0) : max(x + w, 0)] = GREY
        (out / "images").mkdir(parents=True, exist_ok=True)
        (out / "labels").mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out / "images" / f"{cid}.jpg"), image, [cv2.IMWRITE_JPEG_QUALITY, 95])
        (out / "labels" / f"{cid}.txt").write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
        counts["written"] += 1
    return counts
