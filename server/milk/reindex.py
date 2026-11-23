"""Rebuilds the captures table from the result files in S3: the pipeline's re-ingest job.

Every capture is stored twice: a JSON result file in S3 and a row in DynamoDB that the CSV
exports read. The file is the source of truth, so an emptied or recreated table can be
filled again from the bucket. Rows are written with their original keys, so running the
job twice changes nothing. Files whose 30-day retention has already passed are skipped.

    python -m milk.reindex                              # every result file
    python -m milk.reindex --prefix CAM-S01-A/2026-11-18  # one camera, one day
    python -m milk.reindex --dry-run                    # count only, write nothing
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime

from . import config
from .store import RETENTION_DAYS, table_item

log = logging.getLogger("milk.reindex")


def expires_at(record: dict) -> int:
    """Retention counts from the capture, not from the re-index."""
    captured = datetime.fromisoformat(record["capture_timestamp"]).timestamp()
    return int(captured) + RETENTION_DAYS * 86400


def reindex(s3, table, bucket: str, prefix: str = "", dry_run: bool = False, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    stats = {"loaded": 0, "expired": 0, "skipped": 0}
    pages = s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=f"results/{prefix}")
    with table.batch_writer(overwrite_by_pkeys=["camera_id", "capture_id"]) as batch:
        for page in pages:
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if not key.endswith(".json"):
                    stats["skipped"] += 1
                    continue
                try:
                    record = json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
                    item = table_item(record, record.get("image_key", ""), expires_at(record))
                except (KeyError, ValueError, TypeError) as exc:
                    log.warning("skipped %s: %s: %s", key, type(exc).__name__, exc)
                    stats["skipped"] += 1
                    continue
                if item["expires_at"] <= now:
                    stats["expired"] += 1
                    continue
                if not dry_run:
                    batch.put_item(Item=item)
                stats["loaded"] += 1
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild the captures table from the result files in S3.")
    parser.add_argument("--prefix", default="", help="under results/, for example CAM-S01-A/2026-11-18")
    parser.add_argument("--dry-run", action="store_true", help="count the files, write nothing")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    s = config.load()
    if not (s.bucket and s.table):
        log.error("MILK_BUCKET and MILK_TABLE must be set")
        return 2
    import boto3

    s3 = boto3.client("s3", region_name=s.region)
    table = boto3.resource("dynamodb", region_name=s.region).Table(s.table)
    stats = reindex(s3, table, s.bucket, args.prefix.strip("/"), args.dry_run)
    print(
        f"reindex_summary bucket={s.bucket} table={s.table} prefix={args.prefix or '-'} "
        f"dry_run={str(args.dry_run).lower()} loaded={stats['loaded']} expired={stats['expired']} "
        f"skipped={stats['skipped']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
