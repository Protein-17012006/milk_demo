"""Score the counting path (milk + Slide, merged as the worker merges them) on held-out frames, and the gate a
store-view model must pass before it goes live (spec 5.4).

A model box matches a labelled carton when its centre lies inside it, one to one, the surer box first. Only boxes
named TH count towards TH; every other milk name (Vinamilk at a store that sells none) is a false box, and so is a
TH box on a frame without TH. Unrecognised boxes and Slide boxes are not milk. Numbers come per frame and per segment
(each segment one vote), so one long run of near-identical frames cannot carry the score.

    python -m training.store_view.evaluate run --frames F --segments S --labels L --env-file worker.env ^
        --new "MILK_LONG_DIR=...;MILK_LONG_YOLO=...;MILK_LONG_TILE=1280" --current "MILK_LONG_TILE=0" --out R.json
        [--since 2026-11-25T13:00:00+07:00]   only segments that start at or after this moment
    python -m training.store_view.evaluate synthetic --old best_types.pt --old-data D12 --new best_store_v1.pt --new-data D11
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

GATE = {
    "recall": (">=", 0.85),
    "precision": (">=", 0.90),
    "count_within_1": (">=", 0.80),
    "negatives_per_100": ("<=", 1.0),
}
VINAMILK_DROP = 0.02  # most a Vinamilk class may lose in mAP50 on the synthetic val images
# The milk pipeline's settings: cleared before each pipeline is loaded, so the second one never inherits the first's.
LONG_KEYS = (
    "MILK_LONG_DIR",
    "MILK_LONG_YOLO",
    "MILK_LONG_TILE",
    "MILK_LONG_VARIANTS",
    "MILK_LONG_TH_CONFIRM",
    "MILK_LONG_TH_OVERLAP",
)


def match(model: list[tuple[list[int], float]], truth: list[list[int]]) -> tuple[int, int, int]:
    """(true, false, missed): a model box (x, y, w, h) with its confidence takes the first free labelled carton its
    centre lies in, surer boxes first."""
    taken = [False] * len(truth)
    tp = 0
    for box, _ in sorted(model, key=lambda m: -m[1]):
        cx, cy = box[0] + box[2] / 2, box[1] + box[3] / 2
        for k, (x, y, w, h) in enumerate(truth):
            if not taken[k] and x <= cx <= x + w and y <= cy <= y + h:
                taken[k] = True
                tp += 1
                break
    return tp, len(model) - tp, len(truth) - tp


def frame_result(capture_id: str, segment: str, detections: list, truth: list[list[int]]) -> dict:
    """One frame scored: detections are the counting path's (sku_id, confidence, box), truth the labelled cartons."""
    milk = [d for d in detections if d.sku_id and str(d.sku_id).startswith("TMP-MLK")]
    th = [d for d in milk if str(d.sku_id).startswith("TMP-MLK-TH")]
    tp, fp, fn = match([(list(d.box), d.confidence) for d in th], truth)
    return {
        "capture_id": capture_id,
        "segment": segment,
        "truth": len(truth),
        "th": len(th),
        "milk": len(milk),
        "tp": tp,
        "fp": fp + len(milk) - len(th),
        "fn": fn,
        "count_error": len(th) - len(truth),
    }


def _rates(results: list[dict]) -> dict:
    tp, fp, fn = (sum(r[k] for r in results) for k in ("tp", "fp", "fn"))
    with_th = [r for r in results if r["truth"] > 0]
    negative = [r for r in results if r["truth"] == 0]
    return {
        "recall": tp / (tp + fn) if tp + fn else None,
        "precision": tp / (tp + fp) if tp + fp else None,
        "count_within_1": sum(abs(r["count_error"]) <= 1 for r in with_th) / len(with_th) if with_th else None,
        "negatives_per_100": 100 * sum(r["milk"] for r in negative) / len(negative) if negative else None,
        "frames": len(results),
        "frames_with_th": len(with_th),
        "negative_frames": len(negative),
    }


def summarize(results: list[dict]) -> dict:
    """{"frames": rates over all frames, "segments": the mean of each segment's rates}."""
    by_segment: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_segment[r["segment"]].append(r)
    per = [_rates(rs) for rs in by_segment.values()]
    segments: dict = {"segments": len(per)}
    for key in GATE:
        values = [p[key] for p in per if p[key] is not None]
        segments[key] = sum(values) / len(values) if values else None
    return {"frames": _rates(results), "segments": segments}


def gate(summary: dict) -> list[str]:
    """What fails the gate, in both views; empty when the model may go live."""
    failures = []
    for view in ("frames", "segments"):
        for key, (op, limit) in GATE.items():
            value = summary[view].get(key)
            if value is None:
                failures.append(f"{view}: {key} not measured")
            elif op == ">=" and value < limit:
                failures.append(f"{view}: {key} {value:.3f} < {limit}")
            elif op == "<=" and value > limit:
                failures.append(f"{view}: {key} {value:.3f} > {limit}")
    return failures


def _env(text: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in text.split(";") if part.strip())


def _env_file(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def apply_env(base: dict[str, str], overrides: dict[str, str]) -> None:
    """The environment one pipeline is loaded with: the milk settings cleared, then the MILK_ settings of `base`
    (worker.env), then `overrides`."""
    for key in LONG_KEYS:
        os.environ.pop(key, None)
    os.environ.update({k: v for k, v in base.items() if k.startswith("MILK_")})
    os.environ.update(overrides)


def in_window(first_ts: str, since: str | None) -> bool:
    """Whether a segment that starts at first_ts is scored: always without `since`, else from that moment on."""
    return since is None or datetime.fromisoformat(first_ts) >= datetime.fromisoformat(since)


def night(results: list[dict]) -> dict:
    """Milk boxes on the frames of negative segments (the display is not in view: the cabinet is packed away)."""
    rows = [r for r in results if r.get("kind") == "negative"]
    boxes = sum(r["milk"] for r in rows)
    return {"frames": len(rows), "milk_boxes": boxes, "per_100": 100 * boxes / len(rows) if rows else None}


def _pipeline(base: dict[str, str], overrides: dict[str, str]):
    from milk.pipeline import load_pipeline

    apply_env(base, overrides)
    return load_pipeline("long+slide", "")


def run(args: argparse.Namespace) -> None:
    import torch  # noqa: F401  first on Windows

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
    import cv2

    from training.store_view.dataset import KEYFRAME_SIZE, spread
    from training.store_view.labels import from_yolo

    base = _env_file(args.env_file) if args.env_file else {}
    pipes = {"new": _pipeline(base, _env(args.new)), "current": _pipeline(base, _env(args.current))}
    segments = json.loads(args.segments.read_text(encoding="utf-8"))
    paths = {p.stem: p for p in args.frames.glob("*/*.jpg")}
    results: dict[str, list[dict]] = {"new": [], "current": []}
    slide_differs = 0
    for seg in segments:
        if seg["split"] != "holdout" or seg["kind"] not in ("day", "negative"):
            continue
        if not in_window(seg["first_ts"], args.since):
            continue
        for cid in spread(seg["members"], args.per_segment):
            label = args.labels / f"{cid}.txt"
            if cid not in paths or not label.is_file():
                continue
            truth = [box for _, box in from_yolo(label.read_text().splitlines(), *KEYFRAME_SIZE)]
            image = cv2.imread(str(paths[cid]))
            found = {name: pipe.detect(image) for name, pipe in pipes.items()}
            for name, dets in found.items():
                results[name].append({**frame_result(cid, seg["id"], dets, truth), "kind": seg["kind"]})
            slides = [
                sorted((d.sku_id, d.box) for d in dets if not str(d.sku_id or "").startswith("TMP-MLK") and d.sku_id)
                for dets in found.values()
            ]
            slide_differs += slides[0] != slides[1]
    report = {name: summarize(rs) for name, rs in results.items()}
    report["gate_failures"] = gate(report["new"])
    report["slide_frames_that_differ"] = slide_differs
    report["since"] = args.since
    report["settings"] = {"new": args.new, "current": args.current}  # the override strings only, never worker.env
    report["night"] = night(results["new"])
    report["frames"] = results["new"]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    for name in ("current", "new"):
        for view in ("frames", "segments"):
            s = report[name][view]
            cells = "  ".join(f"{k} {s[k]:.3f}" if s[k] is not None else f"{k} -" for k in GATE)
            print(f"{name:<8} {view:<9} {cells}")
    print(f"held-out frames {len(results['new'])}; Slide differs on {slide_differs}")
    n = report["night"]
    per_100 = "-" if n["per_100"] is None else f"{n['per_100']:.1f}"
    print(f"night frames {n['frames']}  milk boxes {n['milk_boxes']}  per 100 {per_100}")
    print("gate passed" if not report["gate_failures"] else "gate FAILED: " + "; ".join(report["gate_failures"]))


def synthetic(args: argparse.Namespace) -> None:
    """Vinamilk mAP50 per class on the same synthetic val images: old 12-class model vs the new 11-class one."""
    from ultralytics import YOLO

    def ap50(weights: Path, data: Path) -> dict[str, float]:
        metrics = YOLO(str(weights)).val(data=str(data), imgsz=1280, batch=16, workers=8, verbose=False, plots=False)
        names = metrics.names
        return {names[int(c)]: float(v) for c, v in zip(metrics.box.ap_class_index, metrics.box.ap50, strict=True)}

    old, new = ap50(args.old, args.old_data), ap50(args.new, args.new_data)
    failures = []
    for name in sorted(k for k in old if k.startswith("vinamilk")):
        drop = old[name] - new.get(name, 0.0)
        print(f"{name:<28} old {old[name]:.3f}  new {new.get(name, 0.0):.3f}  drop {drop:+.3f}")
        if drop > VINAMILK_DROP:
            failures.append(name)
    print("vinamilk check passed" if not failures else "vinamilk check FAILED: " + ", ".join(failures))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--frames", type=Path, required=True)
    r.add_argument("--segments", type=Path, required=True)
    r.add_argument("--labels", type=Path, required=True)
    r.add_argument("--env-file", type=Path, help="worker.env: the Slide and device settings (never printed)")
    r.add_argument("--new", required=True, help='overrides for the new model, "KEY=value;KEY=value"')
    r.add_argument("--current", required=True, help="overrides for the running model")
    r.add_argument("--per-segment", type=int, default=30)
    r.add_argument("--since", help="only segments that start at or after this moment, ISO with offset")
    r.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("synthetic")
    s.add_argument("--old", type=Path, required=True)
    s.add_argument("--old-data", type=Path, required=True, help="data yaml with Long's 12 classes")
    s.add_argument("--new", type=Path, required=True)
    s.add_argument("--new-data", type=Path, required=True, help="data yaml with the 11 classes, same val images")
    args = ap.parse_args(argv)
    run(args) if args.command == "run" else synthetic(args)


if __name__ == "__main__":
    main()
