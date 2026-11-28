"""Ingestion / Result Writer Lambda (Platform B — NHAT-P01).

Receives captures from:
1. SQS queue subscribed to S3 Event notifications for results/<camera>/<date>/<capture_id>.json
2. Direct invocation:
   - {"action": "ingest_record", "record": {...}, "source_bucket": "..."}
   - {"action": "backfill_from_table", "source_table": "...", "source_bucket": "...", "limit": 50}
   - {"action": "select_hourly_official", "hour_prefix": "YYYY-MM-DDTHH"} (EventBridge hourly)
   - {"action": "shelf_tick", "now": <ISO, optional>} (EventBridge every 5 minutes: Dashboard shelf metrics)
   - {"action": "shelf_recompute", "store_id": "...", "days": 15, "now": <ISO, optional>}
"""

from __future__ import annotations

import hashlib
import heapq
import json
import os
import random
import re
import time
from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import boto3
import compare
import label_signals
import shelf
from boto3.dynamodb.conditions import Attr, Key
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from common import (
    UNRECOGNIZED,
    floor_two_decimals,
    from_dynamodb,
    lower_median,
    resolve_sku_alias,
    to_dynamodb_safe,
    validate_capture_payload,
)
from model_health import capture_boxes, hour_stats
from model_versions import STATE_ID

ICT = timezone(timedelta(hours=7))

REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
CAPTURES_TABLE = os.environ.get("CAPTURES_TABLE", "")
LATEST_STOCK_TABLE = os.environ.get("LATEST_STOCK_TABLE", "")
REVIEW_QUEUE_TABLE = os.environ.get("REVIEW_QUEUE_TABLE", "")
ANALYTICS_BUCKET = os.environ.get("ANALYTICS_BUCKET", "")
CAPTURE_TTL_DAYS = int(os.environ.get("CAPTURE_TTL_DAYS", "7"))
AUDITS_TABLE = os.environ.get("AUDITS_TABLE", "")
# Corrections that ask for the frame of their reading; unset, the hourly rule serves no request
CORRECTIONS_TABLE = os.environ.get("CORRECTIONS_TABLE", "")
MODEL_HEALTH_TABLE = os.environ.get("MODEL_HEALTH_TABLE", "")
HEALTH_TTL_DAYS = 90
SHELF_TABLE = os.environ.get("SHELF_TABLE", "")
SHELF_EVENTS_TABLE = os.environ.get("SHELF_EVENTS_TABLE", "")
STORE_LIST_TABLE = os.environ.get("STORE_LIST_TABLE", "")
MODEL_VERSIONS_TABLE = os.environ.get("MODEL_VERSIONS_TABLE", "")
# The shelf tick and the recompute copy event photos inside this Lambda's 60 s: a hung S3 call gives up fast
PHOTO_S3_CONFIG = Config(connect_timeout=3, read_timeout=10, retries={"max_attempts": 2})


def _aws_clients(s3_config: Config | None = None):
    s3 = boto3.client("s3", region_name=REGION, config=s3_config)
    ddb = boto3.resource("dynamodb", region_name=REGION)
    return s3, ddb


def _normalize_record(raw: dict[str, Any], source_bucket: str = "") -> dict[str, Any]:
    rows = raw.get("rows")
    if rows is None and "rows_json" in raw:
        rows = json.loads(raw["rows_json"]) if isinstance(raw["rows_json"], str) else raw["rows_json"]
    log = raw.get("log")
    if log is None and "log_json" in raw:
        log = json.loads(raw["log_json"]) if isinstance(raw["log_json"], str) else raw["log_json"]
    detections = raw.get("detections")
    if detections is None and raw.get("detections_json"):
        detections = (
            json.loads(raw["detections_json"]) if isinstance(raw["detections_json"], str) else raw["detections_json"]
        )

    display_score = raw.get("display_score")
    record = {
        "capture_id": raw.get("capture_id") or (log or {}).get("capture_id", ""),
        "store_id": raw.get("store_id") or (log or {}).get("store_id", ""),
        "camera_id": raw.get("camera_id") or (log or {}).get("camera_id", ""),
        "capture_timestamp": raw.get("capture_timestamp") or (log or {}).get("capture_timestamp", ""),
        "capture_source": raw.get("capture_source") or (log or {}).get("capture_source", "CCTV"),
        "image_filename": raw.get("image_filename") or (log or {}).get("image_filename", ""),
        "image_key": raw.get("image_key", ""),
        "source_bucket": raw.get("source_bucket") or source_bucket,
        "processing_time_ms": int(raw.get("processing_time_ms") or (log or {}).get("processing_time_ms") or 0),
        "latency_ms": int(raw.get("latency_ms") or 0),
        "units_found": int(raw.get("units_found") or (log or {}).get("units_found") or 0),
        "flagged_rows": int(raw.get("flagged_rows") or (log or {}).get("flagged_rows") or 0),
        "faces_blurred": int(raw.get("faces_blurred") or 0),
        "pipeline": raw.get("pipeline", "long"),
        "model_version": raw.get("model_version") or "unknown",
        # what the worker saw of the display: old workers send neither, which means "visible"
        "display_score": float(display_score) if display_score is not None else None,
        "display_visible": bool(raw.get("display_visible", True)),
        "detections": from_dynamodb(detections) if detections is not None else None,
        "counts": from_dynamodb(raw.get("counts") or {}),
        "rows": from_dynamodb(rows or []),
        "log": from_dynamodb(log or {}),
    }
    return record


def ingest_capture(
    record: dict[str, Any], s3_client=None, ddb_resource=None, write_analytics: bool = False
) -> dict[str, Any]:
    """Validate, deduplicate, map alias, write captures/latest_stock/review_queue and the camera's display status."""
    errors = validate_capture_payload(record)
    if errors:
        raise ValueError(f"Invalid capture payload: {'; '.join(errors)}")

    if s3_client is None or ddb_resource is None:
        s3_client, ddb_resource = _aws_clients()

    captures_tbl = ddb_resource.Table(CAPTURES_TABLE)
    stock_tbl = ddb_resource.Table(LATEST_STOCK_TABLE)
    queue_tbl = ddb_resource.Table(REVIEW_QUEUE_TABLE)

    camera_id = record["camera_id"]
    capture_id = record["capture_id"]
    store_id = record["store_id"]
    capture_ts = record["capture_timestamp"]

    # Map model labels to official packaging product names (hoang 21/11 decision)
    mapped_rows: list[dict[str, Any]] = []
    unrecognized_units = 0
    for r in record["rows"]:
        raw_sku = r.get("sku_id")
        official_sku_id, official_sku_name = resolve_sku_alias(raw_sku, r.get("sku_name"))
        mapped = dict(r)
        mapped["model_alias"] = raw_sku or ""
        mapped["sku_id"] = official_sku_id
        mapped["sku_name"] = official_sku_name
        mapped["confidence_score"] = floor_two_decimals(float(r.get("confidence_score", 0.0)))
        mapped["unit_count"] = int(r.get("unit_count", 0))
        mapped["is_flagged"] = bool(r.get("is_flagged", False))
        mapped_rows.append(mapped)
        if official_sku_id is None:
            unrecognized_units += mapped["unit_count"]

    # Step 2: Deduplicate by (camera_id, capture_id)
    now_epoch = int(time.time())
    capture_item = to_dynamodb_safe(
        {
            "camera_id": camera_id,
            "capture_id": capture_id,
            "store_id": store_id,
            "capture_timestamp": capture_ts,
            "capture_source": record["capture_source"],
            "image_filename": record["image_filename"],
            "image_key": record["image_key"],
            "source_bucket": record.get("source_bucket", ""),
            "processing_time_ms": record["processing_time_ms"],
            "latency_ms": record["latency_ms"],
            "units_found": record["units_found"],
            "flagged_rows": record["flagged_rows"],
            "unrecognized_units": unrecognized_units,
            "faces_blurred": record["faces_blurred"],
            "pipeline": record["pipeline"],
            "model_version": record.get("model_version") or "unknown",
            "display_visible": record.get("display_visible", True),
            **({"display_score": record["display_score"]} if record.get("display_score") is not None else {}),
            "detections_json": (
                json.dumps(record["detections"], separators=(",", ":"))
                if record.get("detections") is not None
                else None
            ),
            "rows_json": json.dumps(mapped_rows, ensure_ascii=False),
            "log_json": json.dumps(record["log"], ensure_ascii=False),
            "expires_at": now_epoch + CAPTURE_TTL_DAYS * 86400,
        }
    )

    try:
        captures_tbl.put_item(
            Item=capture_item,
            ConditionExpression="attribute_not_exists(capture_id)",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return {"status": "duplicate_skipped", "capture_id": capture_id}
        raise

    # Step 4: Update latest_stock (per store_id + sku_id) with lower-median smoothing of last 3 captures. A capture
    # that cannot see the display is kept above but says nothing about the shelf: latest_stock and the review queue
    # stay as the last capture that saw the display left them.
    sees_display = shelf.sees_shelf(capture_item)
    seen_skus: set[str] = set()
    for row in mapped_rows if sees_display else []:
        sku_key = row["sku_id"] or UNRECOGNIZED
        seen_skus.add(sku_key)

        prev_item = stock_tbl.get_item(Key={"store_id": store_id, "sku_id": sku_key}).get("Item") or {}
        prev_recent = [int(x) for x in from_dynamodb(prev_item.get("recent_counts", []))]
        recent_counts = (prev_recent + [row["unit_count"]])[-3:]
        smoothed = lower_median(recent_counts)

        stock_tbl.put_item(
            Item=to_dynamodb_safe(
                {
                    "store_id": store_id,
                    "sku_id": sku_key,
                    "sku_name": row["sku_name"] or "Unrecognized",
                    "model_alias": row.get("model_alias", ""),
                    "camera_id": camera_id,
                    "reading_id": row["reading_id"],
                    "capture_id": capture_id,
                    "capture_timestamp": capture_ts,
                    "capture_source": row["capture_source"],
                    "image_filename": row["image_filename"],
                    "image_key": record["image_key"],
                    "source_bucket": record.get("source_bucket", ""),
                    "unit_count": row["unit_count"],
                    "smoothed_count": smoothed,
                    "recent_counts": recent_counts,
                    "confidence_score": row["confidence_score"],
                    "detection_method": row["detection_method"],
                    "bounding_box_json": json.dumps(row["bounding_box"], separators=(",", ":")),
                    "is_flagged": row["is_flagged"],
                    "flag_reason": row.get("flag_reason", ""),
                    "processing_time_ms": row["processing_time_ms"],
                    "faces_blurred": record["faces_blurred"],
                    "pipeline": record["pipeline"],
                }
            )
        )

        # Step 5: Deduplicated review_queue per (camera_id, sku_id, flag_reason)
        if row["is_flagged"]:
            flag_reason = row.get("flag_reason") or ("Unrecognized" if row["sku_id"] is None else "Low Confidence")
            queue_key = f"{camera_id}#{sku_key}#{flag_reason}"
            queue_tbl.put_item(
                Item=to_dynamodb_safe(
                    {
                        "store_id": store_id,
                        "queue_key": queue_key,
                        "camera_id": camera_id,
                        "reading_id": row["reading_id"],
                        "capture_id": capture_id,
                        "capture_timestamp": capture_ts,
                        "sku_id": sku_key,
                        "sku_name": row["sku_name"] or "Unrecognized",
                        "model_alias": row.get("model_alias", ""),
                        "unit_count": row["unit_count"],
                        "confidence_score": row["confidence_score"],
                        "flag_reason": flag_reason,
                        "bounding_box_json": json.dumps(row["bounding_box"], separators=(",", ":")),
                        "image_key": record["image_key"],
                        "source_bucket": record.get("source_bucket", ""),
                        "status": "Chờ duyệt",
                        "updated_at": capture_ts,
                    }
                )
            )

    if sees_display:
        # Nothing is counted down right after a move (this capture's place is far from the arrangement the tick
        # last saw) or for a product the tick marked not in view: its place is outside the frame, not empty.
        state = _shelf_state(ddb_resource, store_id)
        position = shelf.capture_position(capture_item)
        arranged = ((state.get("arrangements") or {}).get(camera_id) or {}).get("position")
        if not (position and arranged and shelf.far_apart(position, arranged)):
            away = frozenset(sku for sku, s in (state.get("skus") or {}).items() if not shelf.in_view(s))
            _count_down_missing(stock_tbl, store_id, camera_id, capture_ts, seen_skus, away)

    # Step 6: Whether the camera sees the display, for the website (after the shelf numbers: a retry of this
    # message is skipped as a duplicate, so a failure here must not cost the capture its stock update)
    if SHELF_TABLE:
        _record_display(ddb_resource.Table(SHELF_TABLE), store_id, camera_id, capture_ts, sees_display)

    if write_analytics and ANALYTICS_BUCKET:
        _write_official_to_s3(s3_client, record, mapped_rows)

    return {
        "status": "ingested",
        "capture_id": capture_id,
        "skus_updated": len(seen_skus),
        "flagged_rows": record["flagged_rows"],
    }


CANDIDATE_FIELDS = ("camera_id", "capture_id", "candidate_version", "detections")


def ingest_candidate(raw: dict[str, Any], ddb_resource=None) -> dict[str, Any]:
    """A candidate release's boxes for a capture the live release has already read (operations-loop design 5.2):
    kept on that capture's row and nowhere else. Stock, the review queue, the shelf numbers and CV Output
    know only the live release. A result whose capture is not there, or that lacks a field, is skipped and
    logged, never raised: nobody sees a candidate's result, so it must not fill the dead-letter queue."""
    capture_id = raw.get("capture_id") if isinstance(raw, dict) else None
    missing = [f for f in CANDIDATE_FIELDS if not isinstance(raw, dict) or raw.get(f) is None]
    if missing:
        print(json.dumps({"candidate_skipped": capture_id, "reason": f"missing {missing}"}))
        return {"status": "skipped", "reason": f"missing {missing}", "capture_id": capture_id}
    if ddb_resource is None:
        _, ddb_resource = _aws_clients()
    try:
        ddb_resource.Table(CAPTURES_TABLE).update_item(
            Key={"camera_id": raw["camera_id"], "capture_id": capture_id},
            UpdateExpression="SET candidate_version = :v, candidate_detections_json = :d",
            ConditionExpression="attribute_exists(capture_id)",
            ExpressionAttributeValues={
                ":v": str(raw["candidate_version"]),
                ":d": json.dumps(raw["detections"], separators=(",", ":")),
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
            raise
        print(json.dumps({"candidate_skipped": capture_id, "reason": "no capture"}))
        return {"status": "skipped", "reason": "no capture", "capture_id": capture_id}
    return {"status": "stored", "capture_id": capture_id}


def _record_display(table, store_id: str, camera_id: str, capture_ts: str, visible: bool) -> None:
    """Item display#<camera_id> of the shelf table: whether the camera sees the display (visible), since when
    (since), the newest capture that saw it (last_visible_at) and the newest capture applied (updated_at).

    SQS and hub re-sends can deliver an older capture after a newer one, so every update is conditional on
    updated_at: an older capture never moves the status back, it can only move last_visible_at on."""
    key = {"store_id": store_id, "key": f"display#{camera_id}"}
    seen = ", last_visible_at = :ts" if visible else ""
    newer = {":ts": capture_ts, ":v": visible}
    updates = [
        # the same status as now: only the times move on
        ("SET updated_at = :ts" + seen, "visible = :v AND updated_at < :ts", newer),
        # the camera's first capture, or the status flips: since starts here
        (
            "SET camera_id = :camera, visible = :v, since = :ts, updated_at = :ts" + seen,
            "attribute_not_exists(updated_at) OR (visible <> :v AND updated_at < :ts)",
            {**newer, ":camera": camera_id},
        ),
    ]
    if visible:  # older than the status, it can still be the newest capture that saw the display
        newest_seen = (
            "attribute_exists(updated_at) AND (attribute_not_exists(last_visible_at) OR last_visible_at < :ts)"
        )
        updates.append(("SET last_visible_at = :ts", newest_seen, {":ts": capture_ts}))
    for update, condition, values in updates:
        try:
            table.update_item(
                Key=key, UpdateExpression=update, ConditionExpression=condition, ExpressionAttributeValues=values
            )
            return
        except ClientError as exc:  # not this case (or a newer capture is in): try the next one
            if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise


def _shelf_state(ddb_resource, store_id: str) -> dict[str, Any]:
    """The shelf table's state item of the store (the tick's per-product status and the camera arrangements);
    {} when there is no shelf table or no item yet. A failed read costs the capture nothing but this check."""
    if not SHELF_TABLE:
        return {}
    try:
        item = ddb_resource.Table(SHELF_TABLE).get_item(Key={"store_id": store_id, "key": "state"}).get("Item")
    except ClientError as exc:
        print(json.dumps({"shelf_state_unreadable": store_id, "error": repr(exc)}))
        return {}
    return from_dynamodb(item) if item else {}


def _count_down_missing(
    stock_tbl,
    store_id: str,
    camera_id: str,
    capture_ts: str,
    seen_skus: set[str],
    skip: frozenset[str] = frozenset(),
) -> None:
    """A SKU that this camera showed before but this capture does not is counted as 0 in the smoothing window,
    so it leaves latest_stock after the usual smoothing instead of staying "on shelf" for good.

    Only rows last written by this camera from an older capture change: another camera of the store may watch
    other shelves, and SQS can deliver an older result after a newer one. The other fields keep the last
    reading that saw the SKU (when, which frame, which boxes). A SKU in `skip` (not in view) is left alone."""
    resp = stock_tbl.query(KeyConditionExpression=Key("store_id").eq(store_id))
    items = resp.get("Items", [])
    while "LastEvaluatedKey" in resp:
        resp = stock_tbl.query(
            KeyConditionExpression=Key("store_id").eq(store_id), ExclusiveStartKey=resp["LastEvaluatedKey"]
        )
        items.extend(resp.get("Items", []))

    for item in from_dynamodb(items):
        if item["sku_id"] in seen_skus or item["sku_id"] in skip or item.get("camera_id") != camera_id:
            continue
        if str(item.get("capture_timestamp", "")) >= capture_ts:
            continue
        prev = [int(x) for x in item.get("recent_counts", [])]
        recent = (prev + [0])[-3:]
        if recent == prev:  # already three zeros
            continue
        stock_tbl.update_item(
            Key={"store_id": store_id, "sku_id": item["sku_id"]},
            UpdateExpression="SET unit_count = :zero, recent_counts = :recent, smoothed_count = :smoothed",
            ExpressionAttributeValues={":zero": 0, ":recent": recent, ":smoothed": lower_median(recent)},
        )


def _write_official_to_s3(s3_client, record: dict[str, Any], mapped_rows: list[dict[str, Any]]) -> None:
    """Write partitioned JSONL records for Glue / Athena & S3 Tables."""
    ts_str = record["capture_timestamp"][:10]  # YYYY-MM-DD
    parts = ts_str.split("-")
    year, month, day = (parts + ["2026", "11", "21"])[:3]
    cap_id = record["capture_id"]

    if mapped_rows:
        cv_body = "\n".join(json.dumps(r, ensure_ascii=False) for r in mapped_rows) + "\n"
        s3_client.put_object(
            Bucket=ANALYTICS_BUCKET,
            Key=f"warehouse/cv_output/year={year}/month={month}/day={day}/{cap_id}.jsonl",
            Body=cv_body.encode("utf-8"),
            ContentType="application/x-ndjson",
        )

    log_body = json.dumps(record["log"], ensure_ascii=False) + "\n"
    s3_client.put_object(
        Bucket=ANALYTICS_BUCKET,
        Key=f"warehouse/capture_log/year={year}/month={month}/day={day}/{cap_id}.jsonl",
        Body=log_body.encode("utf-8"),
        ContentType="application/x-ndjson",
    )


def select_best_capture(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Official hourly capture rule (NHAT-P01 / doc p.9):
    1. Fewest flagged_rows
    2. Highest units_found
    3. Earliest capture_timestamp
    """
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda c: (
            int(c.get("flagged_rows", 0)),
            -int(c.get("units_found", 0)),
            str(c.get("capture_timestamp", "")),
        ),
    )


def _handle_backfill(event: dict[str, Any], s3_client, ddb_resource) -> dict[str, Any]:
    """Backfill latest captures from an existing hub DynamoDB table (read-only)."""
    source_table = event["source_table"]
    source_bucket = event.get("source_bucket", "")
    limit = int(event.get("limit", 30))

    src_tbl = ddb_resource.Table(source_table)
    resp = src_tbl.scan(Limit=limit)
    items = from_dynamodb(resp.get("Items", []))
    # Sort chronologically so latest_stock smoothing ends on the newest capture
    items.sort(key=lambda x: str(x.get("capture_timestamp", "")))

    ingested = 0
    skipped = 0
    # Group by (camera_id, hour) to pick official hourly snapshots for analytics
    by_hour: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for raw in items:
        rec = _normalize_record(raw, source_bucket=source_bucket)
        res = ingest_capture(rec, s3_client=s3_client, ddb_resource=ddb_resource, write_analytics=False)
        if res["status"] == "ingested":
            ingested += 1
        else:
            skipped += 1
        hour_key = rec["capture_timestamp"][:13]
        by_hour[(rec["camera_id"], hour_key)].append(rec)

    official_written = 0
    for group in by_hour.values():
        best = select_best_capture(group)
        if best and ANALYTICS_BUCKET:
            mapped_rows = []
            for r in best["rows"]:
                off_id, off_name = resolve_sku_alias(r.get("sku_id"), r.get("sku_name"))
                mapped_rows.append({**r, "sku_id": off_id, "sku_name": off_name})
            _write_official_to_s3(s3_client, best, mapped_rows)
            official_written += 1

    return {
        "action": "backfill_from_table",
        "scanned": len(items),
        "ingested": ingested,
        "skipped_duplicates": skipped,
        "official_hourly_written": official_written,
    }


def _handle_hourly_official(s3_client, ddb_resource) -> dict[str, Any]:
    """Select one official capture per camera for the previous hour and archive to S3."""
    now_ict = datetime.now(ICT)
    prev_hour = (now_ict - timedelta(hours=1)).strftime("%Y-%m-%dT%H")
    captures_tbl = ddb_resource.Table(CAPTURES_TABLE)
    items = from_dynamodb(captures_tbl.scan().get("Items", []))

    by_cam: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in items:
        if str(raw.get("capture_timestamp", "")).startswith(prev_hour):
            by_cam[raw["camera_id"]].append(_normalize_record(raw))

    written = 0
    for group in by_cam.values():
        best = select_best_capture(group)
        if best and ANALYTICS_BUCKET:
            _write_official_to_s3(s3_client, best, best["rows"])
            written += 1

    return {"action": "select_hourly_official", "hour": prev_hour, "official_written": written}


# --- Model page: one random frame per camera-hour to label, and hourly health (spec 2026-11-23) ---------------


def previous_hour(now_utc: datetime) -> str:
    """The last full clock hour in ICT before `now_utc`, as YYYYMMDD-HH (the schedule is not on the hour)."""
    return (now_utc.astimezone(ICT) - timedelta(hours=1)).strftime("%Y%m%d-%H")


def _scan_all(table, **kwargs) -> list[dict[str, Any]]:
    resp = table.scan(**kwargs)
    items = resp.get("Items", [])
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **kwargs)
        items.extend(resp.get("Items", []))
    return from_dynamodb(items)


def cameras(ddb_resource) -> list[tuple[str, str]]:
    """(camera_id, store code) of every camera that has stock rows; the code comes from CAP-<code>-... ids."""
    found: dict[str, str] = {}
    for item in _scan_all(ddb_resource.Table(LATEST_STOCK_TABLE), ProjectionExpression="camera_id, capture_id"):
        parts = str(item.get("capture_id", "")).split("-")
        if item.get("camera_id") and len(parts) > 2 and parts[0] == "CAP":
            found.setdefault(item["camera_id"], parts[1])
    return sorted(found.items())


def captures_in_hour(ddb_resource, camera_id: str, store_code: str, hour: str) -> list[dict[str, Any]]:
    """Captures of one camera in one ICT hour, found by their id (CAP-S01-20261123-13...), not by a scan."""
    table = ddb_resource.Table(CAPTURES_TABLE)
    cond = Key("camera_id").eq(camera_id) & Key("capture_id").begins_with(f"CAP-{store_code}-{hour}")
    resp = table.query(KeyConditionExpression=cond)
    items = resp.get("Items", [])
    while "LastEvaluatedKey" in resp:
        resp = table.query(KeyConditionExpression=cond, ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp.get("Items", []))
    return from_dynamodb(items)


def parallel_candidate(ddb_resource, camera_id: str) -> str | None:
    """The release that runs in parallel with the live one on this camera, by the model-versions table: the
    candidate of the state row, when its own row says its parallel run has started. None otherwise."""
    if not MODEL_VERSIONS_TABLE:
        return None
    table = ddb_resource.Table(MODEL_VERSIONS_TABLE)
    state = table.get_item(Key={"camera_id": camera_id, "version_id": STATE_ID}).get("Item") or {}
    version = state.get("candidate")
    if not version:
        return None
    row = table.get_item(Key={"camera_id": camera_id, "version_id": version}).get("Item") or {}
    return str(version) if row.get("status") == "parallel" else None


def _write_frame_audit(
    s3_client,
    table,
    audit_id: str,
    purpose: str,
    pick: dict[str, Any],
    camera_id: str,
    candidate: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str | None:
    """Copies the picked capture's frame to the analytics bucket and writes a pending audit of that purpose, with
    what the worker's display check said of the capture: display_visible, and display_score when the check had one
    (the Model page's display check counts only the frames it judged). Returns the audit id, or None when the audit
    already exists.

    A scoring or comparison frame of a capture that `candidate` (the release running in parallel) has also read
    shows the boxes of both releases as one set (compare.merge_boxes) and keeps the candidate's id; a training
    frame, and any frame the candidate has not read, shows the live release's boxes as always. `extra` is written
    onto the audit as it is (why a training frame was picked)."""
    both = (
        purpose in ("scoring", "compare")
        and bool(candidate)
        and pick.get("candidate_version") == candidate
        and pick.get("candidate_detections_json") is not None
    )
    boxes = compare.frame_boxes(pick, candidate) if both else capture_boxes(pick)
    filename = pick.get("image_filename") or pick["image_key"].rsplit("/", 1)[-1]
    image_key = f"audits/frames/{camera_id}/{pick['capture_timestamp'][:10]}/{filename}"
    s3_client.copy_object(
        Bucket=ANALYTICS_BUCKET, Key=image_key, CopySource={"Bucket": pick["source_bucket"], "Key": pick["image_key"]}
    )
    try:
        table.put_item(
            Item=to_dynamodb_safe(
                {
                    "store_id": pick["store_id"],
                    "audit_id": audit_id,
                    "purpose": purpose,
                    "camera_id": camera_id,
                    "capture_id": pick["capture_id"],
                    "capture_timestamp": pick["capture_timestamp"],
                    "image_key": image_key,
                    "model_version": pick.get("model_version") or "unknown",
                    **({"candidate_version": candidate} if both else {}),
                    "pipeline": pick.get("pipeline", ""),
                    "display_visible": pick.get("display_visible", True) is not False,
                    **({"display_score": pick["display_score"]} if pick.get("display_score") is not None else {}),
                    "status": "pending",
                    "sampled_at": datetime.now(ICT).isoformat(timespec="seconds"),
                    "ai_boxes_json": json.dumps(boxes, separators=(",", ":")),
                    "verdicts_json": "[]",
                    "missed_json": "[]",
                    **(extra or {}),
                }
            ),
            ConditionExpression="attribute_not_exists(audit_id)",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return None
        raise
    return audit_id


def _frames_in_opening_hours(items: list[dict[str, Any]], store: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The captures that have a frame, in id order; with the store's hours known, only those taken while it is open."""
    with_frame = sorted((it for it in items if it.get("image_key")), key=lambda it: it["capture_id"])
    if store and store.get("open_time") and store.get("close_time"):
        with_frame = [
            it
            for it in with_frame
            if shelf.is_open(shelf.bucket_of(it["capture_timestamp"]), store["open_time"], store["close_time"])
        ]
    return with_frame


def sample_compare(
    s3_client,
    ddb_resource,
    camera_id: str,
    items: list[dict[str, Any]],
    hour: str,
    rng: random.Random,
    store: dict[str, Any] | None,
    candidate: str | None,
) -> list[str]:
    """A comparison frame (CMP-<camera>-<YYYYMMDD>-<n>) for one camera-hour, while `candidate` runs in parallel:
    one capture, picked at random among those of the hour that both releases read differently and that is not
    the hour's scoring or training frame. At most compare.CMP_PER_DAY a day, and one an hour however often the
    hour is sampled. Comparison frames are never scored. Returns the audit id created now, if any."""
    if not candidate:
        return []
    differing = [
        it
        for it in _frames_in_opening_hours(items, store)
        if it.get("candidate_version") == candidate and compare.differs(compare.frame_boxes(it, candidate))
    ]
    if not differing:
        return []
    table = ddb_resource.Table(AUDITS_TABLE)
    store_id = differing[0]["store_id"]
    prefix = f"CMP-{camera_id}-{hour[:8]}-"
    today = _query_all(table, KeyConditionExpression=Key("store_id").eq(store_id) & Key("audit_id").begins_with(prefix))
    of_this_hour = {it["capture_id"] for it in items}
    if len(today) >= compare.CMP_PER_DAY or any(a.get("capture_id") in of_this_hour for a in today):
        return []
    taken = set()
    for audit_id in (f"AUD-{camera_id}-{hour}", f"TRN-{camera_id}-{hour}"):
        other = table.get_item(Key={"store_id": store_id, "audit_id": audit_id}).get("Item")
        if other:
            taken.add(other.get("capture_id"))
    free = [it for it in differing if it["capture_id"] not in taken]
    if not free:
        return []
    audit_id = f"{prefix}{len(today) + 1}"
    written = _write_frame_audit(s3_client, table, audit_id, "compare", rng.choice(free), camera_id, candidate)
    return [audit_id] if written else []


def pending_requests(ddb_resource, store_id: str) -> list[dict[str, Any]]:
    """Corrections of the store that still ask for the frame of their reading (label_request "pending"), oldest
    first. None when this Lambda is not told the corrections table."""
    if not CORRECTIONS_TABLE:
        return []
    rows = _query_all(
        ddb_resource.Table(CORRECTIONS_TABLE),
        KeyConditionExpression=Key("store_id").eq(store_id),
        FilterExpression=Attr("label_request").eq("pending"),
    )
    return sorted((r for r in rows if r.get("capture_id")), key=lambda r: r["correction_id"])


def _close_requests(ddb_resource, rows: list[dict[str, Any]], status: str, **fields: str) -> None:
    """Answers these corrections' requests: "queued" with label_audit_id, or "dropped" with label_request_note."""
    table = ddb_resource.Table(CORRECTIONS_TABLE)
    values = {"label_request": status, **fields}
    for row in rows:
        table.update_item(
            Key={"store_id": row["store_id"], "correction_id": row["correction_id"]},
            UpdateExpression="SET " + ", ".join(f"#{k} = :{k}" for k in values),
            ExpressionAttributeNames={f"#{k}": k for k in values},
            ExpressionAttributeValues={f":{k}": v for k, v in values.items()},
        )
        row["label_request"] = status


_CAPTURE_ID = re.compile(r"CAP-[A-Za-z0-9]+-(?P<day>\d{8})-(?P<time>\d{6})(?:-\d+)?")


def _capture_hour(capture_id: Any) -> str | None:
    """YYYYMMDD-HH of a capture id (CAP-<code>-<YYYYMMDD>-<HHMMSS>[-n]); None when the value is not one."""
    found = _CAPTURE_ID.fullmatch(capture_id) if isinstance(capture_id, str) else None
    return f"{found['day']}-{found['time'][:2]}" if found else None


def _rows_expired(capture_hour: str, hour: str) -> bool:
    """Whether a capture of that hour is older than capture rows are kept, seen from the hour being sampled."""
    taken = datetime.strptime(capture_hour[:8], "%Y%m%d")
    return taken + timedelta(days=CAPTURE_TTL_DAYS) < datetime.strptime(hour[:8], "%Y%m%d")


def _serve_one(
    s3_client,
    ddb_resource,
    camera_id: str,
    store_id: str,
    training_id: str,
    hour: str,
    request: dict[str, Any],
    requests: list[dict[str, Any]],
) -> bool | None:
    """One request against this camera-hour's training slot. None: go on to the next request (this one was
    answered, dropped or left waiting). True: its frame is now the hour's training frame. False: the slot was
    taken meanwhile, so no request is served this hour."""
    capture_id = request["capture_id"]
    same = [r for r in requests if r["capture_id"] == capture_id and r["label_request"] == "pending"]
    capture_hour = _capture_hour(capture_id)
    if capture_hour is None:
        _close_requests(ddb_resource, same, "dropped", label_request_note="the reading has no usable frame")
        return None
    if capture_hour > hour:
        # A reading of a later hour than the one being sampled (the run for hour h happens during h+1): that
        # hour's own run serves it, after its scoring frame is drawn. Served now, the capture could be drawn again
        # as that hour's scoring frame, and one picture would be both a training and a scoring frame.
        return None
    captures = ddb_resource.Table(CAPTURES_TABLE)
    pick = from_dynamodb(captures.get_item(Key={"camera_id": camera_id, "capture_id": capture_id}).get("Item"))
    if not pick:
        # another camera's capture, or a row that has expired (rows live CAPTURE_TTL_DAYS, less than the frames)
        if _rows_expired(capture_hour, hour):
            note = "the reading is older than the captures kept"
            _close_requests(ddb_resource, same, "dropped", label_request_note=note)
        return None
    if not pick.get("image_key") or not shelf.sees_shelf(pick):
        _close_requests(ddb_resource, same, "dropped", label_request_note="the reading has no usable frame")
        return None
    audits = ddb_resource.Table(AUDITS_TABLE)
    existing = _query_all(
        audits,
        KeyConditionExpression=Key("store_id").eq(store_id),
        FilterExpression=Attr("capture_id").eq(capture_id),
    )
    if existing:
        _close_requests(ddb_resource, same, "queued", label_audit_id=min(a["audit_id"] for a in existing))
        return None
    why = {"picked_by": "correction", "correction_id": request["correction_id"]}
    try:
        written = _write_frame_audit(s3_client, audits, training_id, "training", pick, camera_id, extra=why)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in ("NoSuchKey", "404"):
            raise
        _close_requests(ddb_resource, same, "dropped", label_request_note="the frame is no longer kept")
        return None
    if written:
        _close_requests(ddb_resource, same, "queued", label_audit_id=training_id)
    return bool(written)


def serve_label_request(s3_client, ddb_resource, camera_id: str, store_id: str, training_id: str, hour: str) -> bool:
    """Gives this camera-hour's training frame to the oldest correction that asks for the frame of its reading
    (operations-loop design 5.4): one request an hour, so the day's number of frames does not grow. True when the
    training audit `training_id` was written from a corrected reading's capture.

    A request is left waiting when its capture is another camera's, or was taken in a later hour than `hour`. It
    is dropped, with the reason on the correction, when its reading has no frame a labeller could use, when its
    capture id is not one, or when its capture row has expired. One whose frame is already an audit is answered
    with that audit. Corrections of the same capture are answered together. A request that raises is logged and
    left waiting; the next one is tried."""
    requests = pending_requests(ddb_resource, store_id)
    for request in requests:
        if request["label_request"] != "pending":  # answered with an earlier request of the same capture
            continue
        try:
            served = _serve_one(s3_client, ddb_resource, camera_id, store_id, training_id, hour, request, requests)
        except Exception as exc:  # noqa: BLE001 - one request that cannot be handled must not block the others
            failed = {"label_request_failed": request.get("correction_id"), "camera_id": camera_id, "hour": hour}
            print(json.dumps({**failed, "error": repr(exc)}))
            continue
        if served is not None:
            return served
    return False


def sample_frames(
    s3_client,
    ddb_resource,
    camera_id: str,
    items: list[dict[str, Any]],
    hour: str,
    rng: random.Random,
    store: dict[str, Any] | None,
    candidate: str | None = None,
) -> list[str]:
    """Picks, for one camera-hour, a scoring frame (AUD-, any capture with a frame, at random) and a training frame
    (TRN-, a different capture that sees the shelf: the zone check passed or sure boxes are anywhere in the frame). The training frame follows signals (operations-loop
    design 5.4): the frame of a reading someone corrected, else the frame whose count strays from its sampling
    window, else a random one; the audit says which in picked_by. A capture that is already a frame to label (a
    correction's request can make it one in another hour's run) is drawn for neither: one picture is never both a
    scoring and a training frame. Frames outside the store's opening hours are not sampled. Returns the audit ids
    created now (0, 1 or 2); an existing audit is left alone."""
    with_frame = _frames_in_opening_hours(items, store)
    if not with_frame:
        return []
    table = ddb_resource.Table(AUDITS_TABLE)
    store_id = with_frame[0]["store_id"]
    scoring_id, training_id = f"AUD-{camera_id}-{hour}", f"TRN-{camera_id}-{hour}"
    created: list[str] = []
    audited = {
        a.get("capture_id")
        for a in _query_all(
            table,
            KeyConditionExpression=Key("store_id").eq(store_id),
            FilterExpression=Attr("capture_id").begins_with(
                os.path.commonprefix([it["capture_id"] for it in with_frame])
            ),
            ProjectionExpression="capture_id",
        )
    }

    scoring = table.get_item(Key={"store_id": store_id, "audit_id": scoring_id}).get("Item")
    if scoring:
        scoring_capture = scoring.get("capture_id")
    else:
        scoring_capture = None
        free = [it for it in with_frame if it["capture_id"] not in audited]
        if free:
            pick = rng.choice(free)
            scoring_capture = pick["capture_id"]
            if _write_frame_audit(s3_client, table, scoring_id, "scoring", pick, camera_id, candidate):
                created.append(scoring_id)

    if not table.get_item(Key={"store_id": store_id, "audit_id": training_id}).get("Item"):
        try:
            requested = serve_label_request(s3_client, ddb_resource, camera_id, store_id, training_id, hour)
        except Exception as exc:  # noqa: BLE001 - a request that cannot be served must not cost the hour its frame
            print(json.dumps({"label_request_failed": camera_id, "hour": hour, "error": repr(exc)}))
            requested = False
        if requested:
            return [*created, training_id]
        seeing = [
            it
            for it in with_frame
            if shelf.sees_shelf(it) and it["capture_id"] != scoring_capture and it["capture_id"] not in audited
        ]
        if seeing:
            # a window's median is taken over all its frames, the scoring frame included
            jumps = label_signals.count_jumps(with_frame, capture_boxes)
            pick, picked_by = label_signals.pick_training(seeing, jumps, rng)
            if _write_frame_audit(
                s3_client, table, training_id, "training", pick, camera_id, extra={"picked_by": picked_by}
            ):
                created.append(training_id)
    return created


def record_health(ddb_resource, camera_id: str, hour: str, items: list[dict[str, Any]]) -> None:
    stats = hour_stats(items)
    if not stats["captures"]:
        return
    ddb_resource.Table(MODEL_HEALTH_TABLE).put_item(
        Item=to_dynamodb_safe(
            {
                "camera_id": camera_id,
                "hour": hour,
                **stats,
                "expires_at": int(time.time()) + HEALTH_TTL_DAYS * 86400,
            }
        )
    )


def _run_hour(s3_client, ddb_resource, hour: str, rng: random.Random, sample: bool = True) -> dict[str, Any]:
    audits, health = [], 0
    for camera_id, store_code in cameras(ddb_resource):
        try:
            items = captures_in_hour(ddb_resource, camera_id, store_code, hour)
            if not items:
                continue
            record_health(ddb_resource, camera_id, hour, items)
            health += 1
            if sample:
                store = from_dynamodb(
                    ddb_resource.Table(STORE_LIST_TABLE).get_item(Key={"store_id": items[0]["store_id"]}).get("Item")
                )
                candidate = parallel_candidate(ddb_resource, camera_id)
                audits.extend(sample_frames(s3_client, ddb_resource, camera_id, items, hour, rng, store, candidate))
                audits.extend(sample_compare(s3_client, ddb_resource, camera_id, items, hour, rng, store, candidate))
        except Exception as exc:  # noqa: BLE001 - one camera failing must not stop the others
            print(json.dumps({"model_page_hour_failed": camera_id, "hour": hour, "error": repr(exc)}))
    return {"hour": hour, "audits": audits, "health_items": health}


def _handle_backfill_health(event: dict[str, Any], s3_client, ddb_resource) -> dict[str, Any]:
    """Health for the `days` x 24 hours ending at `until` (default: the previous hour); no sampling."""
    until = event.get("until") or previous_hour(datetime.now(UTC))
    end = datetime.strptime(until, "%Y%m%d-%H")
    hours = [(end - timedelta(hours=h)).strftime("%Y%m%d-%H") for h in range(int(event.get("days", 7)) * 24)]
    written = sum(_run_hour(s3_client, ddb_resource, h, random.Random(), sample=False)["health_items"] for h in hours)
    return {"action": "backfill_model_health", "hours": len(hours), "health_items": written}


# --- Dashboard shelf metrics (spec docs/superpowers/specs/2026-11-24-dashboard-shelf-metrics-design.md) ---


def _now_of(event: dict[str, Any]) -> datetime:
    raw = event.get("now")
    return datetime.fromisoformat(raw).astimezone(UTC) if raw else datetime.now(UTC)


def _query_all(table, **kwargs) -> list[dict[str, Any]]:
    resp = table.query(**kwargs)
    items = resp.get("Items", [])
    while "LastEvaluatedKey" in resp:
        resp = table.query(ExclusiveStartKey=resp["LastEvaluatedKey"], **kwargs)
        items.extend(resp.get("Items", []))
    return from_dynamodb(items)


def _shelf_range(store_id: str, first: str, last: str):
    return Key("store_id").eq(store_id) & Key("key").between(first, last)


def _store_cameras(ddb_resource, store_id: str) -> list[tuple[str, str]]:
    """(camera_id, store code) of one store's cameras, from its latest_stock rows, as cameras() does."""
    found: dict[str, str] = {}
    rows = _query_all(ddb_resource.Table(LATEST_STOCK_TABLE), KeyConditionExpression=Key("store_id").eq(store_id))
    for item in rows:
        parts = str(item.get("capture_id", "")).split("-")
        if item.get("camera_id") and len(parts) > 2 and parts[0] == "CAP":
            found.setdefault(item["camera_id"], parts[1])
    return sorted(found.items())


def _last_closed_bucket(now_utc: datetime) -> str:
    """The latest bucket that closed at least SETTLE_MINUTES ago, so captures arriving late are in it."""
    return shelf.bucket_of((now_utc - timedelta(minutes=shelf.BUCKET_MINUTES + shelf.SETTLE_MINUTES)).isoformat())


def _captures_by_bucket(ddb_resource, cameras: list[tuple[str, str]], first: str, last: str) -> dict[str, list]:
    """Captures of the store's cameras from bucket `first` through bucket `last`, by bucket (ids CAP-<code>-...)."""
    table = ddb_resource.Table(CAPTURES_TABLE)
    end = (shelf.bucket_time(last) + timedelta(minutes=shelf.BUCKET_MINUTES - 1)).strftime("%Y%m%d-%H%M")
    by_bucket: dict[str, list] = defaultdict(list)
    for camera_id, code in cameras:
        cond = Key("camera_id").eq(camera_id) & Key("capture_id").between(
            f"CAP-{code}-{first}00", f"CAP-{code}-{end}59~"
        )
        for item in _query_all(table, KeyConditionExpression=cond):
            by_bucket[shelf.bucket_of(item["capture_timestamp"])].append(item)
    return by_bucket


def _first_capture_bucket(ddb_resource, cameras: list[tuple[str, str]], since: str) -> str | None:
    table = ddb_resource.Table(CAPTURES_TABLE)
    firsts = []
    for camera_id, code in cameras:
        cond = Key("camera_id").eq(camera_id) & Key("capture_id").between(f"CAP-{code}-{since}00", f"CAP-{code}-~")
        items = from_dynamodb(table.query(KeyConditionExpression=cond, Limit=1).get("Items", []))
        if items:
            firsts.append(shelf.bucket_of(items[0]["capture_timestamp"]))
    return min(firsts) if firsts else None


def _expected_skus(ddb_resource, store: dict[str, Any], now_utc: datetime) -> list[str]:
    """The saved list, else the suggestion: SKUs seen confidently in the last SUGGEST_DAYS days (day rollups)."""
    if store.get("expected_skus"):
        return sorted(store["expected_skus"])
    today = now_utc.astimezone(ICT)
    first = (today - timedelta(days=shelf.SUGGEST_DAYS - 1)).strftime("%Y%m%d")
    days = _query_all(
        ddb_resource.Table(SHELF_TABLE),
        KeyConditionExpression=_shelf_range(store["store_id"], f"day#{first}", f"day#{today.strftime('%Y%m%d')}"),
    )
    return sorted({sku for day in days for sku in day.get("confident_skus") or []})


def _plan_joined(store: dict[str, Any]) -> dict[str, str]:
    """SKU -> the bucket where it joined the saved plan. A plan saved before join times were kept gives each of its
    SKUs the time of its last save; a suggested plan has no join times."""
    joined = store.get("expected_since") or {}
    last_save = store.get("shelf_plan_updated_at")
    out = {}
    for sku in store.get("expected_skus") or []:
        at = joined.get(sku) or last_save
        if at:
            out[sku] = shelf.bucket_of(at)
    return out


def _apply_check(
    check: dict,
    store: dict,
    plan: list[str],
    skus_state: dict,
    last_measured: str | None,
    since: dict[str, str],
    arrangements: dict[str, dict],
) -> tuple[list[dict[str, Any]], str | None]:
    """Mark the check open or not and record the SKUs it was counted against: the plan's SKUs that have started
    (shelf.expected_at; since is updated). An open, measured check follows where each camera's cans stand
    (arrangements, changed in place): a move marks the products not seen at the new place as not in view
    (check["arrangement_changed"]), and check["not_in_view"] lists the expected products that are not in view.
    Each expected product that is in view steps its state, with the gap since the last measured check if there is
    one; any other check leaves the state and the arrangements alone. Returns the events and the last measured
    bucket. Checks stored before measurable existed were measured."""
    check["open"] = shelf.is_open(check["bucket"], store.get("open_time"), store.get("close_time"))
    expected = check["expected"] = shelf.expected_at(check, plan, since, _plan_joined(store))
    if not (check["open"] and check.get("measurable", True)):
        return [], last_measured
    moved = shelf.step_arrangements(arrangements, check)
    if moved:
        shelf.move_skus(skus_state, moved, check)
        check["arrangement_changed"] = True
    shelf.see_skus(skus_state, check, expected)
    check["not_in_view"] = [sku for sku in expected if not shelf.in_view(skus_state.get(sku))]
    if not expected:
        return [], last_measured
    gap = shelf.gap_between(last_measured, check["bucket"])
    events = []
    for sku in expected:
        if sku in check["not_in_view"]:
            continue
        state, event = shelf.step_state(skus_state.get(sku), int(check["counts"].get(sku, 0)), check["bucket"], gap)
        skus_state[sku] = state
        if event is not None:
            events.append({**event, "sku_id": sku, "event_key": f"{event['at']}#{sku}#{event['type']}"})
    return events, check["bucket"]


def _expires(start: datetime, days: int) -> int:
    return int((start + timedelta(days=days)).timestamp())


def _check_item(store_id: str, check: dict) -> dict:
    expires = _expires(shelf.bucket_time(check["bucket"]), shelf.CHECK_TTL_DAYS)
    return to_dynamodb_safe({**check, "store_id": store_id, "key": f"check#{check['bucket']}", "expires_at": expires})


def _event_item(store_id: str, event: dict) -> dict:
    return to_dynamodb_safe(
        {**event, "store_id": store_id, "expires_at": _expires(shelf.bucket_time(event["at"]), shelf.ROLLUP_TTL_DAYS)}
    )


def _head_exists(s3_client, bucket: str, key: str) -> bool:
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return False
        raise
    return True


def _copy_photo(s3_client, source: dict, dest_key: str) -> str | None:
    """Copy one check's frame next to the event; the key when the photo is there, None when it cannot be kept
    (the frame expired, no frame was saved, or S3 refused): the event is still written without that photo."""
    try:
        if _head_exists(s3_client, ANALYTICS_BUCKET, dest_key):
            return dest_key
        if not (source.get("image_key") and source.get("source_bucket")):
            return None
        s3_client.copy_object(
            Bucket=ANALYTICS_BUCKET,
            Key=dest_key,
            CopySource={"Bucket": source["source_bucket"], "Key": source["image_key"]},
        )
        return dest_key
    except (ClientError, BotoCoreError) as exc:  # a timeout or a dropped connection too: no photo, the tick goes on
        print(json.dumps({"event_photo_failed": dest_key, "error": repr(exc)}))
        return None


BEFORE_LOOKBACK = 24  # checks looked through for a "before" photo: two hours of 5-minute checks
PHOTO_KEYS = ("photo_before_key", "photo_after_key")
# the event's product in each photo: its boxes in the frame the photo was copied from ([] when it is not in view)
BOX_KEYS = ("boxes_before", "boxes_after")

Checks = Mapping[str, dict[str, Any]]  # a recompute's checks by bucket, as it replays them


def _gives_before_photo(check: dict[str, Any]) -> bool:
    """An open, measured check with a frame (old items without the open or measurable field were both)."""
    return bool(check.get("measurable", True) and check.get("open", True) and check.get("image_key"))


def _before_check(table, store_id: str, event: dict[str, Any], checks: Checks | None = None) -> dict[str, Any] | None:
    """The check the event's "before" photo comes from. After a gap that is the last measured check before it
    (gap_from, where level_before was read), when it kept a frame; otherwise the newest open, measured check with a
    frame among the BEFORE_LOOKBACK checks before that point. checks: the recompute's checks, read instead of the
    stored items; None reads the stored items (the tick)."""
    bound = event["at"]
    if event.get("after_gap") and event.get("gap_from"):
        bound = event["gap_from"]
        if checks is not None:
            exact = checks.get(bound)
        else:
            exact = from_dynamodb(table.get_item(Key={"store_id": store_id, "key": f"check#{bound}"}).get("Item"))
        if exact and exact.get("image_key"):
            return exact
    if checks is not None:
        earlier = [checks[b] for b in heapq.nlargest(BEFORE_LOOKBACK, (b for b in checks if b < bound))]
    else:
        resp = table.query(
            KeyConditionExpression=Key("store_id").eq(store_id) & Key("key").lt(f"check#{bound}"),
            ScanIndexForward=False,
            Limit=BEFORE_LOOKBACK,
        )
        earlier = [c for c in from_dynamodb(resp.get("Items", [])) if str(c["key"]).startswith("check#")]
    return next((c for c in earlier if _gives_before_photo(c)), None)


def _event_photos(
    s3_client, ddb_resource, store_id: str, event: dict[str, Any], checks: Checks | None = None
) -> dict[str, str]:
    """Copy the photos a shelf event does not have yet (hub frames expire after 7 days): the check of the event
    (after) and the last measured check with a frame before it (before). Returns photo_before_key and
    photo_after_key of the photos copied now, or found already copied, each left out when there is no photo; and
    with each photo boxes_before / boxes_after, the event's product in that frame (from the check's frame_boxes).

    checks: the recompute's checks by bucket. It writes its check items in a batch, so until the batch is sent the
    table holds the old items (or none) and the photos must come from the checks it is replaying. None reads the
    stored items, which the tick has just written."""
    wanted = [name for name in ("before", "after") if not event.get(f"photo_{name}_key")]
    if not ANALYTICS_BUCKET or not wanted:
        return {}
    table = ddb_resource.Table(SHELF_TABLE)
    digest = hashlib.sha1(event["event_key"].encode("utf-8")).hexdigest()[:16]
    prefix = f"shelf-events/frames/{store_id}/{digest}"
    sources: dict[str, dict[str, Any] | None] = {}
    try:
        if "after" in wanted:
            if checks is not None:
                sources["after"] = checks.get(event["at"])
            else:
                item = table.get_item(Key={"store_id": store_id, "key": f"check#{event['at']}"}).get("Item")
                sources["after"] = from_dynamodb(item)
        if "before" in wanted:
            sources["before"] = _before_check(table, store_id, event, checks)
    except (ClientError, BotoCoreError) as exc:
        print(json.dumps({"event_photo_failed": event["event_key"], "error": repr(exc)}))
        return {}
    out: dict[str, str] = {}
    for name in wanted:
        source = sources[name] or {}
        key = _copy_photo(s3_client, source, f"{prefix}-{name}.jpg")
        if key:
            out[f"photo_{name}_key"] = key
            out[f"boxes_{name}"] = (source.get("frame_boxes") or {}).get(event["sku_id"]) or []
    return out


def _write_rollups(ddb_resource, store_id: str, hours: set[str]) -> None:
    """Rebuild hour# from the hour's checks and events, then day# from the day's hours. SET, so reruns agree."""
    table = ddb_resource.Table(SHELF_TABLE)
    events_table = ddb_resource.Table(SHELF_EVENTS_TABLE)
    for hour in sorted(hours):
        checks = _query_all(table, KeyConditionExpression=_shelf_range(store_id, f"check#{hour}00", f"check#{hour}59"))
        cond = Key("store_id").eq(store_id) & Key("event_key").between(f"{hour}00", f"{hour}59~")
        events = _query_all(events_table, KeyConditionExpression=cond)
        start = datetime.strptime(hour, "%Y%m%d-%H").replace(tzinfo=ICT)
        item = {**shelf.rollup(checks, events), "store_id": store_id, "key": f"hour#{hour}"}
        table.put_item(Item=to_dynamodb_safe({**item, "expires_at": _expires(start, shelf.ROLLUP_TTL_DAYS)}))
    for day in sorted({hour[:8] for hour in hours}):
        hour_items = _query_all(
            table, KeyConditionExpression=_shelf_range(store_id, f"hour#{day}-00", f"hour#{day}-23")
        )
        start = datetime.strptime(day, "%Y%m%d").replace(tzinfo=ICT)
        item = {**shelf.merge(hour_items), "store_id": store_id, "key": f"day#{day}"}
        table.put_item(Item=to_dynamodb_safe({**item, "expires_at": _expires(start, shelf.ROLLUP_TTL_DAYS)}))


def _shelf_store_tick(s3_client, ddb_resource, store: dict[str, Any], now_utc: datetime) -> int:
    """Work the store's closed buckets after the last one done (at most MAX_BUCKETS_PER_TICK); returns checks made."""
    store_id = store["store_id"]
    flag = store.get("shelf_recompute_requested_at")
    if flag:
        done = shelf_recompute(s3_client, ddb_resource, store_id, shelf.RECOMPUTE_DAYS, now_utc)
        try:
            ddb_resource.Table(STORE_LIST_TABLE).update_item(
                Key={"store_id": store_id},
                UpdateExpression="REMOVE shelf_recompute_requested_at",
                ConditionExpression="shelf_recompute_requested_at = :flag",
                ExpressionAttributeValues={":flag": flag},
            )
        except ClientError as exc:  # saved again meanwhile: the next tick recomputes once more
            if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
        return done["checks"]

    cameras = _store_cameras(ddb_resource, store_id)
    if not cameras:
        return 0
    table = ddb_resource.Table(SHELF_TABLE)
    state_item = from_dynamodb(table.get_item(Key={"store_id": store_id, "key": "state"}).get("Item"))
    if state_item:
        first = shelf.add_buckets(state_item["last_bucket"], 1)
    else:
        since = shelf.bucket_of((now_utc - timedelta(days=CAPTURE_TTL_DAYS)).isoformat())
        first = _first_capture_bucket(ddb_resource, cameras, since)
        if first is None:
            return 0
    last = min(_last_closed_bucket(now_utc), shelf.add_buckets(first, shelf.MAX_BUCKETS_PER_TICK - 1))
    if first > last:
        return 0

    by_bucket = _captures_by_bucket(ddb_resource, cameras, first, last)
    expected = _expected_skus(ddb_resource, store, now_utc)
    skus_state = dict((state_item or {}).get("skus") or {})
    since = dict((state_item or {}).get("since") or {})
    arrangements = dict((state_item or {}).get("arrangements") or {})
    last_measured = (state_item or {}).get("last_measured_bucket")
    events_table = ddb_resource.Table(SHELF_EVENTS_TABLE)
    hours: set[str] = set()
    made = 0
    bucket = first
    while bucket <= last:
        if by_bucket.get(bucket):
            check = shelf.build_check(bucket, by_bucket[bucket])
            events, last_measured = _apply_check(check, store, expected, skus_state, last_measured, since, arrangements)
            table.put_item(Item=_check_item(store_id, check))
            for event in events:
                event.update(_event_photos(s3_client, ddb_resource, store_id, event))
                events_table.put_item(Item=_event_item(store_id, event))
                hours.add(event["at"][:11])
            hours.add(bucket[:11])
            made += 1
        bucket = shelf.add_buckets(bucket, 1)

    state = to_dynamodb_safe(
        {
            "store_id": store_id,
            "key": "state",
            "last_bucket": last,
            "last_measured_bucket": last_measured,
            "skus": skus_state,
            "since": since,
            "arrangements": arrangements,
        }
    )
    try:  # only one run moves a store's state on; an overlapping run stops here
        if state_item:
            table.put_item(
                Item=state,
                ConditionExpression="last_bucket = :old",
                ExpressionAttributeValues={":old": state_item["last_bucket"]},
            )
        else:
            table.put_item(
                Item=state, ConditionExpression="attribute_not_exists(#k)", ExpressionAttributeNames={"#k": "key"}
            )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return 0
        raise
    _write_rollups(ddb_resource, store_id, hours)
    return made


def shelf_tick(s3_client, ddb_resource, now_utc: datetime) -> dict[str, Any]:
    """Every 5 minutes: each store's new checks, shelf state, events and rollups."""
    stores = _scan_all(ddb_resource.Table(STORE_LIST_TABLE))
    return {
        "action": "shelf_tick",
        "stores": {s["store_id"]: _shelf_store_tick(s3_client, ddb_resource, s, now_utc) for s in stores},
    }


def shelf_recompute(s3_client, ddb_resource, store_id: str, days: int, now_utc: datetime) -> dict[str, Any]:
    """Rebuild a store's last `days` days with its current shelf plan: checks from captures still kept, older
    checks as stored, then state, events and rollups replayed from scratch.

    An event that comes back with the same key keeps the photo keys it had, with no S3 call. A missing photo is
    copied from the checks being replayed, and only for events newer than the hub keeps frames (CAPTURE_TTL_DAYS):
    older frames are gone, and the 60 s Lambda must not spend its time on them."""
    store = from_dynamodb(ddb_resource.Table(STORE_LIST_TABLE).get_item(Key={"store_id": store_id}).get("Item"))
    store = store or {"store_id": store_id}
    table = ddb_resource.Table(SHELF_TABLE)
    events_table = ddb_resource.Table(SHELF_EVENTS_TABLE)
    now_ict = now_utc.astimezone(ICT)
    first = (now_ict - timedelta(days=days)).strftime("%Y%m%d") + "-0000"
    last = _last_closed_bucket(now_utc)

    checks = {
        c["bucket"]: c
        for c in _query_all(table, KeyConditionExpression=_shelf_range(store_id, f"check#{first}", f"check#{last}"))
    }
    cameras = _store_cameras(ddb_resource, store_id)
    if cameras:
        kept_from = max(first, shelf.bucket_of((now_utc - timedelta(days=CAPTURE_TTL_DAYS)).isoformat()))
        for bucket, caps in _captures_by_bucket(ddb_resource, cameras, kept_from, last).items():
            if first <= bucket <= last:
                checks[bucket] = shelf.build_check(bucket, caps)

    stale = _query_all(table, KeyConditionExpression=_shelf_range(store_id, f"day#{first[:8]}", f"day#{last[:8]}"))
    stale += _query_all(table, KeyConditionExpression=_shelf_range(store_id, f"hour#{first[:11]}", f"hour#{last[:11]}"))
    old_events = _query_all(
        events_table, KeyConditionExpression=Key("store_id").eq(store_id) & Key("event_key").between(first, f"{last}~")
    )
    kept_photos = {
        e["event_key"]: {**{k: e[k] for k in PHOTO_KEYS if e.get(k)}, **{k: e[k] for k in BOX_KEYS if k in e}}
        for e in old_events
    }
    # SKUs that started before these days stay started; the others start again from the checks replayed
    old_state = from_dynamodb(table.get_item(Key={"store_id": store_id, "key": "state"}).get("Item")) or {}
    since = {sku: bucket for sku, bucket in (old_state.get("since") or {}).items() if bucket < first}
    frames_from = shelf.bucket_of((now_utc - timedelta(days=CAPTURE_TTL_DAYS)).isoformat())
    with table.batch_writer() as writer:
        for item in [*stale, {"key": "state"}]:
            writer.delete_item(Key={"store_id": store_id, "key": item["key"]})
    with events_table.batch_writer() as writer:
        for item in old_events:
            writer.delete_item(Key={"store_id": store_id, "event_key": item["event_key"]})

    if store.get("expected_skus"):
        expected = sorted(store["expected_skus"])
    else:
        suggest_from = shelf.bucket_of((now_utc - timedelta(days=shelf.SUGGEST_DAYS)).isoformat())
        expected = sorted({s for b, c in checks.items() if b >= suggest_from for s in c.get("confident_skus") or []})

    skus_state: dict[str, Any] = {}
    arrangements: dict[str, dict] = {}
    last_measured: str | None = None
    hours: set[str] = set()
    replayed: dict[str, dict[str, Any]] = {}  # the checks as this run writes them, for the event photos
    # what a check knew of the display; checks stored before the display check have none of these
    display_fields = (
        "captures_visible",
        "measurable",
        "unmeasured_reason",
        "image_key",
        "source_bucket",
        "frame_boxes",
        "positions",
        "confident_by_camera",
        "captures_zone",
    )
    with table.batch_writer() as writer, events_table.batch_writer() as event_writer:
        for bucket in sorted(checks):
            stored = checks[bucket]
            check = {k: stored[k] for k in ("bucket", "counts", "captures", "cameras", "confident_skus")}
            check.update({k: stored[k] for k in display_fields if k in stored})
            events, last_measured = _apply_check(check, store, expected, skus_state, last_measured, since, arrangements)
            replayed[bucket] = check
            for event in events:
                event.update(kept_photos.get(event["event_key"], {}))
                if event["at"] >= frames_from:
                    event.update(_event_photos(s3_client, ddb_resource, store_id, event, replayed))
                event_writer.put_item(Item=_event_item(store_id, event))
                hours.add(event["at"][:11])
            writer.put_item(Item=_check_item(store_id, check))
            hours.add(bucket[:11])
    state = {"store_id": store_id, "key": "state", "last_bucket": last, "last_measured_bucket": last_measured}
    table.put_item(Item=to_dynamodb_safe({**state, "skus": skus_state, "since": since, "arrangements": arrangements}))
    _write_rollups(ddb_resource, store_id, hours)
    return {"action": "shelf_recompute", "store_id": store_id, "checks": len(checks), "hours": len(hours)}


def lambda_handler(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    shelf_run = event.get("action") in ("shelf_tick", "shelf_recompute")  # these copy event photos
    s3_client, ddb_resource = _aws_clients(PHOTO_S3_CONFIG if shelf_run else None)

    # 0. Dashboard shelf metrics: EventBridge every 5 minutes, or a recompute run by hand
    if event.get("action") == "shelf_tick":
        return shelf_tick(s3_client, ddb_resource, _now_of(event))
    if event.get("action") == "shelf_recompute":
        days = int(event.get("days") or shelf.RECOMPUTE_DAYS)
        return shelf_recompute(s3_client, ddb_resource, event["store_id"], days, _now_of(event))

    # 1. EventBridge hourly run: first the Model page's frame to label and hourly health (light queries), then
    #    the official capture of the hour, which scans the whole captures table and may fail as it grows
    if event.get("source") == "aws.events" or event.get("action") == "select_hourly_official":
        model_page = _run_hour(s3_client, ddb_resource, previous_hour(datetime.now(UTC)), random.Random())
        return {**_handle_hourly_official(s3_client, ddb_resource), "model_page": model_page}

    if event.get("action") == "sample_audits":
        hour = event.get("hour") or previous_hour(datetime.now(UTC))
        return {"action": "sample_audits", **_run_hour(s3_client, ddb_resource, hour, random.Random())}

    if event.get("action") == "backfill_model_health":
        return _handle_backfill_health(event, s3_client, ddb_resource)

    # 2. Direct backfill invocation
    if event.get("action") == "backfill_from_table":
        return _handle_backfill(event, s3_client, ddb_resource)

    # 3. Direct single record invocation
    if event.get("action") == "ingest_record":
        rec = _normalize_record(event["record"], source_bucket=event.get("source_bucket", ""))
        return ingest_capture(
            rec, s3_client=s3_client, ddb_resource=ddb_resource, write_analytics=bool(event.get("official"))
        )

    # 4. SQS batch wrapping S3 Event notifications
    processed = []
    for sqs_record in event.get("Records", []):
        body = json.loads(sqs_record["body"])
        s3_events = body.get("Records", [])
        for s3_ev in s3_events:
            bucket = s3_ev["s3"]["bucket"]["name"]
            key = s3_ev["s3"]["object"]["key"]
            if not key.startswith("results/") or not key.endswith(".json"):
                continue
            obj = s3_client.get_object(Bucket=bucket, Key=key)
            raw = json.loads(obj["Body"].read().decode("utf-8"))
            if key.endswith(".candidate.json"):  # a candidate release's boxes for a capture, not a capture
                processed.append(ingest_candidate(raw, ddb_resource))
                continue
            rec = _normalize_record(raw, source_bucket=bucket)
            processed.append(ingest_capture(rec, s3_client=s3_client, ddb_resource=ddb_resource))

    return {"processed": len(processed), "results": processed}
