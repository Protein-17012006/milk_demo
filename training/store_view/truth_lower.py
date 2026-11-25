"""Lower-tier Slide cans added to the hand-drawn truth (auto-label design 5.7): the training labels name every visible
can, so gate 1 must count a lower-tier can as a real one. Rule A never counts kind "lower".

    sheets: draft boxes no truth row holds -> numbered zoom sheets <out>/<keyframe>.jpg and <out>/candidates.json
    apply:  a person's decisions {keyframe: {"<n>": "<sku>" | "unknown" | "no"}} -> the truth with "lower" rows

    python -m training.store_view.truth_lower sheets --truth T --drafts DIR --frames F --out DIR
    python -m training.store_view.truth_lower apply --truth T --candidates DIR\\candidates.json --decisions D --out T2
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

REGION = (860, 100, 1560, 900)  # the Slide display with its lower tier, CAM-S01-A


def _holds(row: dict, box) -> bool:
    x, y, w, h = row["box"]
    cx, cy = box[0] + box[2] / 2, box[1] + box[3] / 2
    return x <= cx <= x + w and y <= cy <= y + h


def candidates(truth_rows: list[dict], proposals: list[list[float]]) -> list[list[int]]:
    """Draft boxes (x, y, w, h) whose centre no truth row of any kind holds."""
    return [[int(round(v)) for v in b[:4]] for b in proposals if not any(_holds(r, b) for r in truth_rows)]


def add_lower(truth: dict, keyframe: str, boxes_with_sku: list[tuple[list[int], str]]) -> dict:
    out = copy.deepcopy(truth)
    out[keyframe] = out.get(keyframe, []) + [{"box": list(b), "sku": sku, "kind": "lower"} for b, sku in boxes_with_sku]
    return out


def _sheets(args) -> None:
    import cv2

    truth = json.loads(args.truth.read_text(encoding="utf-8"))
    paths = {p.stem: p for p in args.frames.glob("*/*.jpg")}
    args.out.mkdir(parents=True, exist_ok=True)
    found = {}
    for key, rows in truth.items():
        draft = args.drafts / f"{key}.json"
        if not draft.is_file():
            continue
        cands = candidates(rows, json.loads(draft.read_text(encoding="utf-8")))
        found[key] = cands
        img = cv2.imread(str(paths[key]))
        for r in rows:
            x, y, w, h = r["box"]
            cv2.rectangle(img, (x, y), (x + w, y + h), (255, 255, 255), 1)
        for i, (x, y, w, h) in enumerate(cands):
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 0, 255), 2)
            cv2.putText(img, str(i), (x + 2, y + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        x0, y0, x1, y1 = REGION
        cv2.imwrite(str(args.out / f"{key}.jpg"), cv2.resize(img[y0:y1, x0:x1], None, fx=1.6, fy=1.6))
        print(key, len(cands), "candidates")
    (args.out / "candidates.json").write_text(json.dumps(found, indent=1), encoding="utf-8")


def _apply(args) -> None:
    truth = json.loads(args.truth.read_text(encoding="utf-8"))
    cands = json.loads(args.candidates.read_text(encoding="utf-8"))
    decisions = json.loads(args.decisions.read_text(encoding="utf-8"))
    for key, picks in decisions.items():
        chosen = [(cands[key][int(i)], sku) for i, sku in picks.items() if sku != "no"]
        truth = add_lower(truth, key, chosen)
        print(key, len(chosen), "lower rows")
    args.out.write_text(json.dumps(truth, indent=1), encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    s = sub.add_parser("sheets")
    for name in ("--truth", "--drafts", "--frames", "--out"):
        s.add_argument(name, type=Path, required=True)
    a = sub.add_parser("apply")
    for name in ("--truth", "--candidates", "--decisions", "--out"):
        a.add_argument(name, type=Path, required=True)
    args = ap.parse_args(argv)
    _sheets(args) if args.command == "sheets" else _apply(args)


if __name__ == "__main__":
    main()
