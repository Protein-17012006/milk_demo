"""Split a camera's frames into runs of one arrangement, so one labelled keyframe can stand for the whole run.

The camera is fixed and the packs move seldom: as long as the region where they stand looks the same, the boxes of
one keyframe are right for every frame of the run. A frame unlike the run's first frame either ends the run, or,
when the run's look comes back within `patience` frames, is a passing occlusion (a hand, a customer) and belongs
to no run. Frames whose worker did not see the display (the cabinet packed away at night) are negatives: no TH.
A run never spans a time gap or the edge of the held-out window, so held-out frames never share a run with
training frames.

    python -m training.store_view.segments --frames C:\\Users\\huyho\\Datagent\\store_frames\\CAM-S01-A ^
        --region 760,0,1200,320 --out C:\\Users\\huyho\\Datagent\\store_labels\\segments.json
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np

SIG_W, SIG_H = 64, 48
# Held out from training, database and threshold tuning (spec 5.2e): 23/11 from 18:00 until the cabinet was packed
# away (standing packs at dusk), and everything from 25/11 on. End None = no end.
HOLDOUT = (
    ("2026-11-23T18:00:00+07:00", "2026-11-23T21:00:00+07:00"),
    ("2026-11-25T00:00:00+07:00", None),
)


def holdout(capture_timestamp: str) -> bool:
    t = datetime.fromisoformat(capture_timestamp)
    return any(
        datetime.fromisoformat(start) <= t and (end is None or t < datetime.fromisoformat(end))
        for start, end in HOLDOUT
    )


def signature(image: np.ndarray, region: tuple[int, int, int, int]) -> np.ndarray:
    """What the region (x0, y0, x1, y1 in the image's pixels) looks like, independent of overall brightness: grey,
    64x48, mean removed, unit standard deviation, flattened."""
    import cv2

    x0, y0, x1, y1 = region
    crop = image[y0:y1, x0:x1]
    if crop.ndim == 3 and crop.shape[2] == 1:  # ultralytics' patched cv2.imread keeps a channel axis on grey images
        crop = crop[..., 0]
    elif crop.ndim == 3:
        crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(crop, (SIG_W, SIG_H), interpolation=cv2.INTER_AREA).astype(np.float32).ravel()
    small -= small.mean()
    return small / max(float(small.std()), 1e-6)


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Pearson correlation of two signatures, -1..1."""
    a = a - a.mean()
    b = b - b.mean()
    return float(a @ b / max(float(np.linalg.norm(a) * np.linalg.norm(b)), 1e-12))


def _close(group: dict, rows: list[dict], sigs: list[np.ndarray], min_sim: float, min_len: int) -> dict:
    members = group["members"]
    if group["kind"] == "negative":
        keyframe = members[len(members) // 2]
        kept = members
    else:
        stack = np.stack([sigs[i] - sigs[i].mean() for i in members])
        stack /= np.maximum(np.linalg.norm(stack, axis=1, keepdims=True), 1e-12)
        sims = stack @ stack.T
        best = int(np.argmax(sims.mean(axis=1)))
        keyframe = members[best]
        kept = [i for i, s in zip(members, sims[best], strict=True) if s >= min_sim]
    kind = group["kind"] if len(kept) >= min_len else "transient"
    return {
        "kind": kind,
        "split": "holdout" if group["holdout"] else "train",
        "keyframe": rows[keyframe]["capture_id"],
        "members": [rows[i]["capture_id"] for i in kept],
        "first_ts": rows[kept[0]]["capture_timestamp"],
        "last_ts": rows[kept[-1]]["capture_timestamp"],
        "dropped": len(members) - len(kept),
    }


def split(
    rows: list[dict],
    sigs: list[np.ndarray],
    min_sim: float = 0.8,
    max_gap_s: float = 900,
    patience: int = 3,
    min_len: int = 3,
) -> list[dict]:
    """Runs of one arrangement in time order, each {id, kind (day | negative | transient), split (train | holdout),
    keyframe, members, first_ts, last_ts, dropped}. rows carry capture_id, capture_timestamp, display_visible;
    sigs[i] is the signature of rows[i]."""
    order = sorted(range(len(rows)), key=lambda i: (rows[i]["capture_timestamp"], rows[i]["capture_id"]))
    groups: list[dict] = []
    current: dict | None = None
    for pos, i in enumerate(order):
        row = rows[i]
        t = datetime.fromisoformat(row["capture_timestamp"])
        kind = "negative" if row.get("display_visible") is False else "day"
        held = holdout(row["capture_timestamp"])
        if (
            current is not None
            and (current["kind"], current["holdout"]) == (kind, held)
            and (t - current["last_t"]).total_seconds() <= max_gap_s
        ):
            anchor = sigs[current["anchor"]]
            if kind == "negative" or similarity(sigs[i], anchor) >= min_sim:
                current["members"].append(i)
                current["last_t"] = t
                continue
            ahead = order[pos + 1 : pos + 1 + patience]
            if any(
                rows[j].get("display_visible") is not False and similarity(sigs[j], anchor) >= min_sim for j in ahead
            ):
                continue  # a passing occlusion: the arrangement comes back
        current = {"kind": kind, "holdout": held, "anchor": i, "members": [i], "last_t": t}
        groups.append(current)
    segments = [_close(g, rows, sigs, min_sim, min_len) for g in groups]
    for n, seg in enumerate(segments, start=1):
        seg["id"] = f"seg-{n:04d}"
    return segments


def main(argv: list[str] | None = None) -> None:
    import cv2

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames", type=Path, required=True, help="a camera folder with manifest.jsonl (harvest.py)")
    ap.add_argument("--region", required=True, help="x0,y0,x1,y1 in full-frame pixels")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--min-sim", type=float, default=0.8)
    ap.add_argument("--max-gap-s", type=float, default=900)
    args = ap.parse_args(argv)
    x0, y0, x1, y1 = (int(v) for v in args.region.split(","))
    half = (x0 // 2, y0 // 2, x1 // 2, y1 // 2)  # frames are read at half size: faster, the same look
    rows, sigs = [], []
    with open(args.frames / "manifest.jsonl", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            image = cv2.imread(str(args.frames / row["path"]), cv2.IMREAD_REDUCED_GRAYSCALE_2)
            if image is None:
                continue
            rows.append(row)
            sigs.append(signature(image, half))
    segments = split(rows, sigs, min_sim=args.min_sim, max_gap_s=args.max_gap_s)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(segments, indent=1), encoding="utf-8")
    tally = Counter((s["split"], s["kind"]) for s in segments)
    frames = Counter((s["split"], s["kind"]) for s in segments for _ in s["members"])
    print(f"{len(rows)} frames -> {len(segments)} segments")
    for key in sorted(tally):
        print(f"  {key[0]:<8} {key[1]:<10} segments {tally[key]:>4}  frames {frames[key]:>6}")
    days = Counter((s["first_ts"][:10], s["kind"]) for s in segments if s["kind"] != "transient")
    print("per day:", dict(sorted(days.items())))


if __name__ == "__main__":
    main()
