"""Export what the gallery is built from: the labelled frames of one camera and the audits that label them.

Reads the audits table and the analytics bucket (where the backend keeps a copy of every labelled frame, for good)
and writes, under one folder:

    audits.json                                     every done audit of the camera made by people or for scoring:
                                                    training (TRN-), review (REV-), comparison (CMP-), scoring (AUD-)
    frames/<camera>/<YYYY-MM-DD>/<capture_id>.jpg   the frames, the day read from the capture id (local time)
    frames/<camera>/manifest.jsonl                  one row per capture: capture_id, capture_timestamp, audit_ids

The manifest is written from scratch each run. Besides the done audits it lists scoring audits of any status, so a
capture whose scoring audit still waits for its verdicts is already known as a scoring frame, and the gallery never
takes it.
Frames already on disk are not fetched again. Standard library only at module level: it runs in a venv with just boto3.

    python -m ops.gallery_data --root <out_dir> --camera CAM-S01-A
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

AUDITS_TABLE = "milk-backend-development-audits"
ANALYTICS_BUCKET = "milk-backend-development-754361433393"
PREFIXES = ("TRN-", "REV-", "CMP-", "AUD-")
FIELDS = (
    "audit_id",
    "status",
    "capture_id",
    "capture_timestamp",
    "ai_boxes_json",
    "verdicts_json",
    "image_key",
    "candidate_version",
)


def _day(capture_id: str) -> str:
    stamp = capture_id.split("-")[2]
    return f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}"


def _scan(table, camera: str) -> list[dict]:
    from boto3.dynamodb.conditions import Attr

    kw = {"FilterExpression": Attr("camera_id").eq(camera)}
    items = []
    while True:
        page = table.scan(**kw)
        items += page["Items"]
        if "LastEvaluatedKey" not in page:
            return items
        kw["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def export(table, s3, bucket: str, camera: str, out_dir: Path) -> dict:
    """Write audits.json, the missing frames and the manifest under out_dir; return the counts:
    {"audits": {prefix: done audits}, "frames_new", "frames_kept", "frames_missing"}."""
    items = [i for i in _scan(table, camera) if str(i.get("audit_id", "")).startswith(PREFIXES)]
    done = [i for i in items if i.get("status") == "done"]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [{k: str(i.get(k, "")) for k in FIELDS} for i in sorted(done, key=lambda i: i["audit_id"])]
    (out_dir / "audits.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")

    folder = out_dir / "frames" / camera
    new = kept = missing = 0
    for row in {r["capture_id"]: r for r in rows}.values():  # a capture with two audits is fetched once
        dest = folder / _day(row["capture_id"]) / f"{row['capture_id']}.jpg"
        if dest.is_file() and dest.stat().st_size > 0:
            kept += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_suffix(".part")
        try:
            s3.download_file(bucket, row["image_key"], str(part))
        except Exception as exc:  # botocore's ClientError, imported lazily; anything but a missing key is a real fault
            if getattr(exc, "response", {}).get("Error", {}).get("Code") not in ("404", "NoSuchKey"):
                raise
            missing += 1
            continue
        part.replace(dest)
        new += 1

    captures: dict[str, dict] = {}
    listed = [i for i in items if i.get("status") == "done" or i["audit_id"].startswith("AUD-")]
    for i in sorted(listed, key=lambda i: (str(i.get("capture_timestamp", "")), i["audit_id"])):
        row = captures.setdefault(
            i["capture_id"],
            {"capture_id": i["capture_id"], "capture_timestamp": str(i.get("capture_timestamp", "")), "audit_ids": []},
        )
        row["audit_ids"].append(i["audit_id"])
    ordered = sorted(captures.values(), key=lambda r: (r["capture_timestamp"], r["capture_id"]))
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "manifest.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in ordered), encoding="utf-8"
    )
    by_prefix = {p: sum(1 for i in done if i["audit_id"].startswith(p)) for p in PREFIXES}
    return {"audits": by_prefix, "frames_new": new, "frames_kept": kept, "frames_missing": missing}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, required=True, help="the folder to write into")
    ap.add_argument("--camera", required=True)
    ap.add_argument("--region", default="ap-southeast-1")
    ap.add_argument("--table", default=AUDITS_TABLE)
    ap.add_argument("--bucket", default=ANALYTICS_BUCKET)
    args = ap.parse_args(argv)

    import boto3

    table = boto3.resource("dynamodb", region_name=args.region).Table(args.table)
    s3 = boto3.client("s3", region_name=args.region)
    print(json.dumps(export(table, s3, args.bucket, args.camera, args.root)))


if __name__ == "__main__":
    main()
