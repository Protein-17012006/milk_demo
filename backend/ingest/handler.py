"""Ingestion / Result Writer Lambda (Platform B — NHAT-P01).

Receives captures from:
1. SQS queue subscribed to S3 Event notifications for results/<camera>/<date>/<capture_id>.json
2. Direct invocation:
   - {"action": "ingest_record", "record": {...}, "source_bucket": "..."}
   - {"action": "backfill_from_table", "source_table": "...", "source_bucket": "...", "limit": 50}
   - {"action": "select_hourly_official", "hour_prefix": "YYYY-MM-DDTHH"} (EventBridge hourly)
"""
from __future__ import annotations

import json
import os
import random
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from common import (
    DEFAULT_ALIAS_MAP,
    UNRECOGNIZED,
    floor_two_decimals,
    from_dynamodb,
    lower_median,
    resolve_sku_alias,
    to_dynamodb_safe,
    validate_capture_payload,
)
from model_health import capture_boxes, hour_stats

ICT = timezone(timedelta(hours=7))

REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
CAPTURES_TABLE = os.environ.get("CAPTURES_TABLE", "")
LATEST_STOCK_TABLE = os.environ.get("LATEST_STOCK_TABLE", "")
REVIEW_QUEUE_TABLE = os.environ.get("REVIEW_QUEUE_TABLE", "")
ANALYTICS_BUCKET = os.environ.get("ANALYTICS_BUCKET", "")
CAPTURE_TTL_DAYS = int(os.environ.get("CAPTURE_TTL_DAYS", "7"))
AUDITS_TABLE = os.environ.get("AUDITS_TABLE", "")
MODEL_HEALTH_TABLE = os.environ.get("MODEL_HEALTH_TABLE", "")
HEALTH_TTL_DAYS = 90


def _aws_clients():
    s3 = boto3.client("s3", region_name=REGION)
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
        detections = json.loads(raw["detections_json"]) if isinstance(raw["detections_json"], str) else raw["detections_json"]

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
        "detections": from_dynamodb(detections) if detections is not None else None,
        "counts": from_dynamodb(raw.get("counts") or {}),
        "rows": from_dynamodb(rows or []),
        "log": from_dynamodb(log or {}),
    }
    return record


def ingest_capture(record: dict[str, Any], s3_client=None, ddb_resource=None, write_analytics: bool = False) -> dict[str, Any]:
    """Validate, deduplicate, map alias, write captures/latest_stock/review_queue."""
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
    capture_item = to_dynamodb_safe({
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
        "detections_json": (json.dumps(record["detections"], separators=(",", ":"))
                            if record.get("detections") is not None else None),
        "rows_json": json.dumps(mapped_rows, ensure_ascii=False),
        "log_json": json.dumps(record["log"], ensure_ascii=False),
        "expires_at": now_epoch + CAPTURE_TTL_DAYS * 86400,
    })

    try:
        captures_tbl.put_item(
            Item=capture_item,
            ConditionExpression="attribute_not_exists(capture_id)",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return {"status": "duplicate_skipped", "capture_id": capture_id}
        raise

    # Step 4: Update latest_stock (per store_id + sku_id) with lower-median smoothing of last 3 captures
    seen_skus: set[str] = set()
    for row in mapped_rows:
        sku_key = row["sku_id"] or UNRECOGNIZED
        seen_skus.add(sku_key)

        prev_item = stock_tbl.get_item(Key={"store_id": store_id, "sku_id": sku_key}).get("Item") or {}
        prev_recent = [int(x) for x in from_dynamodb(prev_item.get("recent_counts", []))]
        recent_counts = (prev_recent + [row["unit_count"]])[-3:]
        smoothed = lower_median(recent_counts)

        stock_tbl.put_item(
            Item=to_dynamodb_safe({
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
            })
        )

        # Step 5: Deduplicated review_queue per (camera_id, sku_id, flag_reason)
        if row["is_flagged"]:
            flag_reason = row.get("flag_reason") or ("Unrecognized" if row["sku_id"] is None else "Low Confidence")
            queue_key = f"{camera_id}#{sku_key}#{flag_reason}"
            queue_tbl.put_item(
                Item=to_dynamodb_safe({
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
                })
            )

    _count_down_missing(stock_tbl, store_id, camera_id, capture_ts, seen_skus)

    if write_analytics and ANALYTICS_BUCKET:
        _write_official_to_s3(s3_client, record, mapped_rows)

    return {
        "status": "ingested",
        "capture_id": capture_id,
        "skus_updated": len(seen_skus),
        "flagged_rows": record["flagged_rows"],
    }


def _count_down_missing(stock_tbl, store_id: str, camera_id: str, capture_ts: str, seen_skus: set[str]) -> None:
    """A SKU that this camera showed before but this capture does not is counted as 0 in the smoothing window,
    so it leaves latest_stock after the usual smoothing instead of staying "on shelf" for good.

    Only rows last written by this camera from an older capture change: another camera of the store may watch
    other shelves, and SQS can deliver an older result after a newer one. The other fields keep the last
    reading that saw the SKU (when, which frame, which boxes)."""
    resp = stock_tbl.query(KeyConditionExpression=Key("store_id").eq(store_id))
    items = resp.get("Items", [])
    while "LastEvaluatedKey" in resp:
        resp = stock_tbl.query(KeyConditionExpression=Key("store_id").eq(store_id),
                               ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp.get("Items", []))

    for item in from_dynamodb(items):
        if item["sku_id"] in seen_skus or item.get("camera_id") != camera_id:
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


def sample_audit(s3_client, ddb_resource, camera_id: str, items: list[dict[str, Any]], hour: str,
                 rng: random.Random) -> str | None:
    """Picks one capture with a frame at random, copies the frame to the analytics bucket and writes a
    pending audit. Returns the audit id, or None when the hour has no frame or already has its audit."""
    with_frame = sorted((it for it in items if it.get("image_key")), key=lambda it: it["capture_id"])
    if not with_frame:
        return None
    table = ddb_resource.Table(AUDITS_TABLE)
    store_id = with_frame[0]["store_id"]
    audit_id = f"AUD-{camera_id}-{hour}"
    if table.get_item(Key={"store_id": store_id, "audit_id": audit_id}).get("Item"):
        return None
    pick = rng.choice(with_frame)
    filename = pick.get("image_filename") or pick["image_key"].rsplit("/", 1)[-1]
    image_key = f"audits/frames/{camera_id}/{pick['capture_timestamp'][:10]}/{filename}"
    s3_client.copy_object(Bucket=ANALYTICS_BUCKET, Key=image_key,
                          CopySource={"Bucket": pick["source_bucket"], "Key": pick["image_key"]})
    try:
        table.put_item(
            Item=to_dynamodb_safe({
                "store_id": store_id,
                "audit_id": audit_id,
                "camera_id": camera_id,
                "capture_id": pick["capture_id"],
                "capture_timestamp": pick["capture_timestamp"],
                "image_key": image_key,
                "model_version": pick.get("model_version") or "unknown",
                "pipeline": pick.get("pipeline", ""),
                "status": "pending",
                "sampled_at": datetime.now(ICT).isoformat(timespec="seconds"),
                "ai_boxes_json": json.dumps(capture_boxes(pick), separators=(",", ":")),
                "verdicts_json": "[]",
                "missed_json": "[]",
            }),
            ConditionExpression="attribute_not_exists(audit_id)",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return None
        raise
    return audit_id


def record_health(ddb_resource, camera_id: str, hour: str, items: list[dict[str, Any]]) -> None:
    stats = hour_stats(items)
    if not stats["captures"]:
        return
    ddb_resource.Table(MODEL_HEALTH_TABLE).put_item(Item=to_dynamodb_safe({
        "camera_id": camera_id,
        "hour": hour,
        **stats,
        "expires_at": int(time.time()) + HEALTH_TTL_DAYS * 86400,
    }))


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
                audit_id = sample_audit(s3_client, ddb_resource, camera_id, items, hour, rng)
                if audit_id:
                    audits.append(audit_id)
        except Exception as exc:  # noqa: BLE001 - one camera failing must not stop the others
            print(json.dumps({"model_page_hour_failed": camera_id, "hour": hour, "error": repr(exc)}))
    return {"hour": hour, "audits": audits, "health_items": health}


def _handle_backfill_health(event: dict[str, Any], s3_client, ddb_resource) -> dict[str, Any]:
    """Health for the `days` x 24 hours ending at `until` (default: the previous hour); no sampling."""
    until = event.get("until") or previous_hour(datetime.now(timezone.utc))
    end = datetime.strptime(until, "%Y%m%d-%H")
    hours = [(end - timedelta(hours=h)).strftime("%Y%m%d-%H") for h in range(int(event.get("days", 7)) * 24)]
    written = sum(_run_hour(s3_client, ddb_resource, h, random.Random(), sample=False)["health_items"] for h in hours)
    return {"action": "backfill_model_health", "hours": len(hours), "health_items": written}


def lambda_handler(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    s3_client, ddb_resource = _aws_clients()

    # 1. EventBridge scheduled hourly selection, then the Model page's frame to label and hourly health
    if event.get("source") == "aws.events" or event.get("action") == "select_hourly_official":
        result = _handle_hourly_official(s3_client, ddb_resource)
        result["model_page"] = _run_hour(s3_client, ddb_resource, previous_hour(datetime.now(timezone.utc)),
                                         random.Random())
        return result

    if event.get("action") == "sample_audits":
        hour = event.get("hour") or previous_hour(datetime.now(timezone.utc))
        return {"action": "sample_audits", **_run_hour(s3_client, ddb_resource, hour, random.Random())}

    if event.get("action") == "backfill_model_health":
        return _handle_backfill_health(event, s3_client, ddb_resource)

    # 2. Direct backfill invocation
    if event.get("action") == "backfill_from_table":
        return _handle_backfill(event, s3_client, ddb_resource)

    # 3. Direct single record invocation
    if event.get("action") == "ingest_record":
        rec = _normalize_record(event["record"], source_bucket=event.get("source_bucket", ""))
        return ingest_capture(rec, s3_client=s3_client, ddb_resource=ddb_resource, write_analytics=bool(event.get("official")))

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
            rec = _normalize_record(raw, source_bucket=bucket)
            processed.append(ingest_capture(rec, s3_client=s3_client, ddb_resource=ddb_resource))

    return {"processed": len(processed), "results": processed}
