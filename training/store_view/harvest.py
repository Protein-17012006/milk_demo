"""Gather every stored frame of one camera for training, with one manifest row per capture.

Sources: the hub's frames (kept RetentionDays days, prefix frames/) and the copies of the labelled frames
(AUD-/TRN-, kept for good in the analytics bucket). A capture found in both is one row; its audit ids are listed.
Runs on the laptop, which has the AWS access. The frames go to a folder outside OneDrive, then to HUYHOANG:

    python -m training.store_view.harvest --camera CAM-S01-A --first 2026-11-22 --last 2026-11-25 ^
        --out C:\\Users\\huyho\\milk_store_frames

Writes <out>/<camera>/<YYYY-MM-DD>/<capture_id>.jpg (store days, ICT) and <out>/<camera>/manifest.jsonl. Frames
already on disk are not fetched again.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

CAPTURES_TABLE = "milk-backend-development-captures"
AUDITS_TABLE = "milk-backend-development-audits"
ANALYTICS_BUCKET = "milk-backend-development-754361433393"
ICT = timezone(timedelta(hours=7))
CAPTURE_FIELDS = (
    "capture_id, capture_timestamp, image_key, source_bucket, display_visible, display_score, detections_json"
)


def capture_prefix(camera_id: str) -> str:
    """Capture ids of the camera's store: CAM-S01-A -> CAP-S01-."""
    return f"CAP-{camera_id.split('-')[1]}-"


def frame_relpath(capture_id: str, capture_timestamp: str) -> str:
    """Where one frame is kept: a folder per store day (ICT, whatever offset the timestamp carries)."""
    day = datetime.fromisoformat(capture_timestamp).astimezone(ICT).strftime("%Y-%m-%d")
    return f"{day}/{capture_id}.jpg"


def _json_list(value) -> list:
    if not value:
        return []
    return json.loads(value) if isinstance(value, str) else list(value)


def _row(item: dict, bucket: str | None, boxes, audit_ids: list[str]) -> dict:
    score = item.get("display_score")
    return {
        "capture_id": item["capture_id"],
        "capture_timestamp": item["capture_timestamp"],
        # captures from before the display check carry no display_visible: they saw the display (backend/shelf.py)
        "display_visible": item.get("display_visible", True) is not False,
        "display_score": float(score) if score is not None else None,
        "bucket": bucket,
        "image_key": item["image_key"],
        "boxes": _json_list(boxes),
        "audit_ids": audit_ids,
        "path": frame_relpath(item["capture_id"], item["capture_timestamp"]),
    }


def rows_from_captures(items: list[dict]) -> list[dict]:
    """Manifest rows of the hub's captures that kept a frame; the boxes are the live model's."""
    return [_row(it, it.get("source_bucket"), it.get("detections_json"), []) for it in items if it.get("image_key")]


def rows_from_audits(items: list[dict], bucket: str) -> list[dict]:
    """Manifest rows of the labelled frames' copies in the analytics bucket."""
    return [_row(it, bucket, it.get("ai_boxes_json"), [it["audit_id"]]) for it in items if it.get("image_key")]


def merge_rows(hub: list[dict], audits: list[dict]) -> list[dict]:
    """One row per capture, in time order: the hub's frame where it still exists, else the labelled copy; every
    audit id of the capture is listed."""
    by_id: dict[str, dict] = {r["capture_id"]: {**r, "audit_ids": list(r["audit_ids"])} for r in hub}
    for a in audits:
        row = by_id.get(a["capture_id"])
        if row is None:
            by_id[a["capture_id"]] = {**a, "audit_ids": list(a["audit_ids"])}
        else:
            row["audit_ids"].extend(x for x in a["audit_ids"] if x not in row["audit_ids"])
    return sorted(by_id.values(), key=lambda r: (r["capture_timestamp"], r["capture_id"]))


def _all(call, **kw) -> list[dict]:
    items = []
    while True:
        page = call(**kw)
        items += page["Items"]
        if "LastEvaluatedKey" not in page:
            return items
        kw["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camera", default="CAM-S01-A")
    ap.add_argument("--first", required=True, help="first store day, YYYY-MM-DD")
    ap.add_argument("--last", required=True, help="last store day, YYYY-MM-DD")
    ap.add_argument("--out", type=Path, required=True, help="a folder outside OneDrive")
    ap.add_argument("--profile", default="default")
    ap.add_argument("--region", default="ap-southeast-1")
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args(argv)

    import boto3
    from boto3.dynamodb.conditions import Attr, Key
    from botocore.exceptions import ClientError

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    ddb = session.resource("dynamodb")
    prefix = capture_prefix(args.camera)
    first, last = args.first.replace("-", ""), args.last.replace("-", "")
    captures = _all(
        ddb.Table(CAPTURES_TABLE).query,
        KeyConditionExpression=Key("camera_id").eq(args.camera)
        & Key("capture_id").between(f"{prefix}{first}", f"{prefix}{last}-999999"),
        ProjectionExpression=CAPTURE_FIELDS,
    )
    audits = [
        a
        for a in _all(ddb.Table(AUDITS_TABLE).scan, FilterExpression=Attr("camera_id").eq(args.camera))
        if args.first <= frame_relpath(a["capture_id"], a["capture_timestamp"])[:10] <= args.last
    ]
    rows = merge_rows(rows_from_captures(captures), rows_from_audits(audits, ANALYTICS_BUCKET))
    out = args.out / args.camera
    s3 = session.client("s3")

    def fetch(row: dict) -> str:
        dest = out / row["path"]
        if dest.is_file() and dest.stat().st_size > 0:
            return "kept"
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_suffix(".part")
        try:
            s3.download_file(row["bucket"], row["image_key"], str(part))
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
                return "missing"
            raise
        part.replace(dest)
        return "new"

    with ThreadPoolExecutor(args.workers) as pool:
        results = list(pool.map(fetch, rows))
    present = [row for row, result in zip(rows, results, strict=True) if result != "missing"]
    with open(out / "manifest.jsonl", "w", encoding="utf-8") as handle:
        for row in present:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("frames:", dict(Counter(results)), "| manifest rows:", len(present))
    print("per day:", dict(sorted(Counter(r["path"][:10] for r in present).items())))


if __name__ == "__main__":
    main()
