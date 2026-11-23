"""Checks the worker's CV Output against the team's own cv_output.py on the report's sample images.

For every image both sides get the same cartons from cv_output.read_units(); the rows built by
milk.cvoutput.build_capture must equal those of cv_output.readings(), field by field (processing
time aside). The totals are printed next to the CV Output report of 17/10/2026 for reference:
the saved sample images were re-encoded and had faces blurred, so a fresh reading may differ
slightly from the report even when the code is identical.

    <carton_recognition>/.venv/bin/python worker/regression.py ~/Desktop/Datagent/cv_output_sample
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import pathlib
import statistics
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "server"))

from milk.cvoutput import CaptureStem, build_capture  # noqa: E402
from milk.long_adapter import LongPipeline  # noqa: E402

FIELDS = [
    "reading_id",
    "capture_id",
    "store_id",
    "camera_id",
    "capture_timestamp",
    "capture_source",
    "image_filename",
    "sku_id",
    "sku_name",
    "unit_count",
    "confidence_score",
    "detection_method",
    "bounding_box",
    "is_flagged",
    "flag_reason",
]


def theirs_row(row: dict) -> dict:
    return {f: ("" if row[f] is None and f == "flag_reason" else row[f]) for f in FIELDS}


def ours_row(row: dict) -> dict:
    out = {f: row[f] for f in FIELDS}
    out["bounding_box"] = json.dumps(row["bounding_box"], separators=(",", ":"))
    return out


def report_totals(csv_path: pathlib.Path) -> tuple[int, int, int]:
    with open(csv_path, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    return len(rows), sum(int(r["unit_count"]) for r in rows), sum(r["is_flagged"] in ("True", "TRUE") for r in rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sample", type=pathlib.Path, help="folder with images/ and cv_output.csv from the 17/10 report")
    args = ap.parse_args()

    import cv2

    pipe = LongPipeline()
    cvo = pipe._cvo
    images = sorted((args.sample / "images").glob("*.jpg"))
    mismatches, n_rows, n_units, n_flagged, times = 0, 0, 0, 0, []
    for path in images:
        camera, date, rest = path.stem.split("_", 2)  # PHONE-S02-A, 20261012, 083216 or 083216-2
        store_code = camera.split("-")[1]
        when = datetime.datetime.strptime(date + rest.split("-")[0], "%Y%m%d%H%M%S").replace(tzinfo=cvo.VN)
        image = cv2.imread(str(path))
        started = time.perf_counter()
        units = pipe.read_units(image)
        times.append((time.perf_counter() - started) * 1000)

        capture = dict(
            store_id=f"TEST-{store_code}",
            camera_id=camera,
            capture_source="Phone",
            time=when,
            stamp=f"{date}-{rest}",
            image_filename=path.name,
        )
        theirs, _ = cvo.readings(units, capture, 0)
        ours, log = build_capture(
            pipe.to_detections(units),
            stem=CaptureStem(store_code, date, rest),
            store_id=f"TEST-{store_code}",
            camera_id=camera,
            capture_source="Phone",
            ts=when,
            processing_time_ms=0,
        )
        a, b = [theirs_row(r) for r in theirs], [ours_row(r) for r in ours]
        if a != b:
            mismatches += 1
            print(f"MISMATCH {path.name}")
            for x, y in zip(a, b, strict=False):
                for f in FIELDS:
                    if x[f] != y[f]:
                        print(f"   {x['reading_id']} {f}: pipeline={x[f]!r} worker={y[f]!r}")
            if len(a) != len(b):
                print(f"   rows: pipeline={len(a)} worker={len(b)}")
        n_rows += len(ours)
        n_units += log["units_found"]
        n_flagged += log["flagged_rows"]

    r_rows, r_units, r_flagged = report_totals(args.sample / "cv_output.csv")
    print(f"images: {len(images)}; device: {pipe.device}")
    print(f"rows built by the worker equal the pipeline's on {len(images) - mismatches}/{len(images)} images")
    print(f"this run:      {n_rows} rows, {n_units} cartons, {n_flagged} flagged rows")
    print(f"report 17/10:  {r_rows} rows, {r_units} cartons, {r_flagged} flagged rows")
    print(f"reading time per image: median {statistics.median(times):.0f} ms, max {max(times):.0f} ms")
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
