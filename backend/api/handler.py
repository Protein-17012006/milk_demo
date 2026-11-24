"""Serverless REST API Lambda for Project A Shelf Analytics (Platform B — NHAT-P01).

Serves all /v1/* endpoints behind AWS WAF + API Gateway REST API + Cognito Authorizer.
Enforces Cognito group RBAC:
  - datagent:   read products/stores/reports/KPI/review-queue + export CSV
  - field_team: datagent permissions + submit corrections + presigned uploads
  - team_admin: all permissions + import SKU Master / Store List + admin seed
  - no group:   403 PENDING_ROLE_ASSIGNMENT (for self-registered /register users)
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
import shelf
from audit_scoring import SKIP_REASONS, summarize, validate_labels
from boto3.dynamodb.conditions import Key
from common import (
    CAPTURE_LOG_COLUMNS,
    CV_OUTPUT_COLUMNS,
    DEFAULT_ALIAS_MAP,
    MILK_FLAG_THRESHOLD,
    UNRECOGNIZED,
    compute_validation_result,
    from_dynamodb,
    to_csv,
    to_dynamodb_safe,
)

ICT = timezone(timedelta(hours=7))

REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
CAPTURES_TABLE = os.environ.get("CAPTURES_TABLE", "")
LATEST_STOCK_TABLE = os.environ.get("LATEST_STOCK_TABLE", "")
REVIEW_QUEUE_TABLE = os.environ.get("REVIEW_QUEUE_TABLE", "")
SKU_MASTER_TABLE = os.environ.get("SKU_MASTER_TABLE", "")
STORE_LIST_TABLE = os.environ.get("STORE_LIST_TABLE", "")
CORRECTIONS_TABLE = os.environ.get("CORRECTIONS_TABLE", "")
USER_PREFS_TABLE = os.environ.get("USER_PREFS_TABLE", "")
ANALYTICS_BUCKET = os.environ.get("ANALYTICS_BUCKET", "")
HUB_BUCKET = os.environ.get("HUB_BUCKET", "")
AUDITS_TABLE = os.environ.get("AUDITS_TABLE", "")
MODEL_HEALTH_TABLE = os.environ.get("MODEL_HEALTH_TABLE", "")
SHELF_TABLE = os.environ.get("SHELF_TABLE", "")
SHELF_EVENTS_TABLE = os.environ.get("SHELF_EVENTS_TABLE", "")
ALLOWED_ORIGINS = {
    o.strip()
    for o in os.environ.get(
        "ALLOWED_ORIGINS",
        "https://main.d2k8euxy0yoiv8.amplifyapp.com,http://localhost:3000",
    ).split(",")
    if o.strip()
}

VALID_GROUPS = {"datagent", "field_team", "team_admin"}
WRITE_CORRECTION_GROUPS = {"field_team", "team_admin"}
ADMIN_GROUPS = {"team_admin"}


def _clients():
    s3 = boto3.client("s3", region_name=REGION)
    ddb = boto3.resource("dynamodb", region_name=REGION)
    return s3, ddb


def _cors_headers(event: dict[str, Any]) -> dict[str, str]:
    headers = event.get("headers") or {}
    origin = headers.get("origin") or headers.get("Origin") or ""
    allow_origin = origin if origin in ALLOWED_ORIGINS else next(iter(ALLOWED_ORIGINS), "*")
    return {
        "Access-Control-Allow-Origin": allow_origin,
        "Access-Control-Allow-Headers": "Authorization,Content-Type",
        "Access-Control-Allow-Methods": "GET,POST,PUT,OPTIONS",
        "Vary": "Origin",
    }


def _json_response(
    status_code: int,
    payload: Any,
    event: dict[str, Any],
    content_type: str = "application/json; charset=utf-8",
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    hdrs = {"Content-Type": content_type, **_cors_headers(event)}
    if extra_headers:
        hdrs.update(extra_headers)
    body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return {"statusCode": status_code, "headers": hdrs, "body": body}


def _extract_user(event: dict[str, Any]) -> dict[str, Any]:
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    raw_groups = claims.get("cognito:groups", "")
    if isinstance(raw_groups, list):
        groups = [g for g in raw_groups if g]
    elif isinstance(raw_groups, str) and raw_groups.strip():
        # API Gateway REST Cognito authorizer passes comma-separated string
        cleaned = raw_groups.strip().strip("[]")
        groups = [g.strip().strip('"').strip("'") for g in cleaned.split(",") if g.strip()]
    else:
        groups = []
    return {
        "sub": claims.get("sub", ""),
        "email": claims.get("email", claims.get("cognito:username", "")),
        "groups": groups,
    }


def _require_groups(user: dict[str, Any], allowed: set[str], event: dict[str, Any]) -> dict[str, Any] | None:
    if not user["groups"]:
        return _json_response(
            403,
            {
                "error": "PENDING_ROLE_ASSIGNMENT",
                "message": "Your account has been created and is waiting for team_admin to assign a Cognito group.",
            },
            event,
        )
    if not set(user["groups"]).intersection(allowed):
        return _json_response(
            403,
            {
                "error": "FORBIDDEN",
                "message": f"Required role: one of {sorted(allowed)}",
            },
            event,
        )
    return None


def _presign_frame(s3_client, image_key: str, source_bucket: str = "") -> str | None:
    if not image_key:
        return None
    bucket = source_bucket or HUB_BUCKET or ANALYTICS_BUCKET
    if not bucket:
        return None
    try:
        return s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": image_key},
            ExpiresIn=900,
        )
    except Exception:
        return None


def _parse_body(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("body") or "{}"
    if isinstance(raw, dict):
        return raw
    return json.loads(raw)


def _scan_all(table, **kwargs) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    resp = table.scan(**kwargs)
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **kwargs)
        items.extend(resp.get("Items", []))
    return from_dynamodb(items)


def _query_all(table, **kwargs) -> list[dict[str, Any]]:
    resp = table.query(**kwargs)
    items = resp.get("Items", [])
    while "LastEvaluatedKey" in resp:
        resp = table.query(ExclusiveStartKey=resp["LastEvaluatedKey"], **kwargs)
        items.extend(resp.get("Items", []))
    return from_dynamodb(items)


def _now() -> datetime:
    """Current time in ICT; tests replace it."""
    return datetime.now(ICT)


def _load_products_catalog(ddb) -> tuple[list[dict[str, Any]], int, int]:
    """Aggregate latest_stock across stores, enriched with sku_master & store_list."""
    stock_items = _scan_all(ddb.Table(LATEST_STOCK_TABLE))
    sku_items = _scan_all(ddb.Table(SKU_MASTER_TABLE))
    store_items = _scan_all(ddb.Table(STORE_LIST_TABLE))

    sku_map = {s["sku_id"]: s for s in sku_items}
    total_stores = max(len(store_items), len({x["store_id"] for x in stock_items}) or 1)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unrecognized_max = 0
    for item in stock_items:
        if item["sku_id"] == UNRECOGNIZED:
            unrecognized_max += int(item.get("smoothed_count", item.get("unit_count", 0)))
            continue
        grouped[item["sku_id"]].append(item)

    all_sku_ids = sorted(set(sku_map.keys()) | set(grouped.keys()))
    products: list[dict[str, Any]] = []

    for sku_id in all_sku_ids:
        master = sku_map.get(sku_id)
        rows = grouped.get(sku_id, [])
        total_units = sum(int(r.get("smoothed_count", r.get("unit_count", 0))) for r in rows)
        stores_avail = sum(1 for r in rows if int(r.get("smoothed_count", r.get("unit_count", 0))) > 0)

        # Unit-weighted average confidence across stores (per doc p.11)
        weight_sum = sum(int(r.get("unit_count", 0)) for r in rows)
        if weight_sum > 0:
            weighted_conf = (
                sum(float(r.get("confidence_score", 0.0)) * int(r.get("unit_count", 0)) for r in rows) / weight_sum
            )
        elif rows:
            weighted_conf = sum(float(r.get("confidence_score", 0.0)) for r in rows) / len(rows)
        else:
            weighted_conf = 0.0

        latest_row = max(rows, key=lambda r: str(r.get("capture_timestamp", ""))) if rows else None
        is_flagged = bool(latest_row.get("is_flagged")) if latest_row else False

        products.append(
            {
                "sku_id": sku_id,
                "sku_name": (master or {}).get("sku_name_vi") or (latest_row or {}).get("sku_name") or sku_id,
                "sku_name_en": (master or {}).get("sku_name_en"),
                "model_alias": (master or {}).get("model_alias") or (latest_row or {}).get("model_alias") or "",
                "brand": (master or {}).get("brand"),
                "manufacturer": (master or {}).get("manufacturer"),
                "category": (master or {}).get("category"),
                "subcategory": (master or {}).get("subcategory"),
                "pack_type": (master or {}).get("pack_type"),
                "pack_size": (master or {}).get("pack_size"),
                "barcode": (master or {}).get("barcode"),
                "image_url": (master or {}).get("image_url"),
                "in_sku_master": master is not None,
                "unit_count": total_units,
                "confidence_score": round(weighted_conf, 2),
                "is_flagged": is_flagged,
                "flag_reason": (latest_row or {}).get("flag_reason", ""),
                "stores_available": stores_avail,
                "stores_total": total_stores,
                "capture_id": (latest_row or {}).get("capture_id"),
                "capture_timestamp": (latest_row or {}).get("capture_timestamp"),
                "processing_time_ms": (latest_row or {}).get("processing_time_ms", 0),
            }
        )

    return products, unrecognized_max, total_stores


def _handle_get_products(event: dict[str, Any], ddb) -> dict[str, Any]:
    params = event.get("queryStringParameters") or {}
    q = (params.get("q") or "").strip().lower()
    category = params.get("category") or ""
    status_filter = params.get("status") or ""
    sort_by = params.get("sort") or "stock_desc"

    products, unrecognized_units, total_stores = _load_products_catalog(ddb)

    filtered = []
    for p in products:
        if category and category.lower() != "all" and (p.get("category") or "").lower() != category.lower():
            continue
        if status_filter and status_filter.lower() != "all":
            if status_filter.lower() == "flagged" and not p["is_flagged"]:
                continue
            if status_filter.lower() == "validated" and p["is_flagged"]:
                continue
        if q:
            haystack = " ".join(
                str(x or "") for x in (p["sku_id"], p["sku_name"], p["model_alias"], p["barcode"], p["brand"])
            ).lower()
            if q not in haystack:
                continue
        filtered.append(p)

    if sort_by == "stock_asc":
        filtered.sort(key=lambda x: x["unit_count"])
    elif sort_by == "confidence_desc":
        filtered.sort(key=lambda x: x["confidence_score"], reverse=True)
    elif sort_by == "name_asc":
        filtered.sort(key=lambda x: x["sku_name"].lower())
    else:
        filtered.sort(key=lambda x: x["unit_count"], reverse=True)

    return _json_response(
        200,
        {
            "items": filtered,
            "total": len(filtered),
            "unrecognized_units": unrecognized_units,
            "stores_total": total_stores,
            "flag_threshold": MILK_FLAG_THRESHOLD,
        },
        event,
    )


def _handle_get_product_detail(sku_id_raw: str, event: dict[str, Any], s3, ddb) -> dict[str, Any]:
    # Decision 21/11: sku_id can contain spaces & Vietnamese accents -> URL decode
    sku_id = urllib.parse.unquote(sku_id_raw)
    master = from_dynamodb(ddb.Table(SKU_MASTER_TABLE).get_item(Key={"sku_id": sku_id}).get("Item"))
    stock_items = [item for item in _scan_all(ddb.Table(LATEST_STOCK_TABLE)) if item.get("sku_id") == sku_id]
    corrections = [c for c in _scan_all(ddb.Table(CORRECTIONS_TABLE)) if c.get("sku_id") == sku_id]
    queue_items = [q for q in _scan_all(ddb.Table(REVIEW_QUEUE_TABLE)) if q.get("sku_id") == sku_id]

    if not master and not stock_items:
        return _json_response(404, {"error": "NOT_FOUND", "sku_id": sku_id}, event)

    latest = max(stock_items, key=lambda r: str(r.get("capture_timestamp", ""))) if stock_items else None
    latest_correction = max(corrections, key=lambda c: str(c.get("correction_date", ""))) if corrections else None
    latest_queue = queue_items[0] if queue_items else None

    if latest_correction:
        status_label = "Đã sửa"
    elif latest_queue:
        status_label = latest_queue.get("status", "Chờ duyệt")
    else:
        status_label = "Đã xác nhận"

    discrepancy = (latest_correction or {}).get("discrepancy_category")
    sku_match_ok = (latest_correction or {}).get("sku_match_correct")
    result_label = compute_validation_result(sku_match_ok, discrepancy)

    bboxes = []
    if latest and latest.get("bounding_box_json"):
        bboxes = json.loads(latest["bounding_box_json"])

    frame_url = _presign_frame(
        s3,
        (latest or {}).get("image_key", ""),
        (latest or {}).get("source_bucket", ""),
    )

    return _json_response(
        200,
        {
            "sku_id": sku_id,
            "in_sku_master": master is not None,
            "product_information": master
            or {
                "sku_id": sku_id,
                "sku_name_vi": (latest or {}).get("sku_name", sku_id),
                "brand": None,
                "manufacturer": None,
                "category": None,
                "pack_type": None,
                "pack_size": None,
                "barcode": None,
            },
            "cv_output": {
                "reading_id": (latest or {}).get("reading_id"),
                "capture_id": (latest or {}).get("capture_id"),
                "store_id": (latest or {}).get("store_id"),
                "camera_id": (latest or {}).get("camera_id"),
                "capture_timestamp": (latest or {}).get("capture_timestamp"),
                "capture_source": (latest or {}).get("capture_source", "CCTV"),
                "image_filename": (latest or {}).get("image_filename"),
                "image_key": (latest or {}).get("image_key"),
                "frame_presigned_url": frame_url,
                "unit_count": (latest or {}).get("unit_count", 0),
                "smoothed_count": (latest or {}).get("smoothed_count", 0),
                "confidence_score": (latest or {}).get("confidence_score", 0.0),
                "detection_method": "Visual",
                "bounding_box": bboxes,
                "is_flagged": (latest or {}).get("is_flagged", False),
                "flag_reason": (latest or {}).get("flag_reason", ""),
                "processing_time_ms": (latest or {}).get("processing_time_ms", 0),
                "faces_blurred": (latest or {}).get("faces_blurred", 0),
            },
            "validation": {
                "result": result_label,
                "status": status_label,
                "expected_label": (latest_correction or {}).get("corrected_sku_id") or sku_id,
                "mismatch_type": discrepancy or "None",
                "reviewed_at": (latest_correction or {}).get("correction_date"),
                "accuracy": None,  # populated once human_audit runs
            },
            "stores": stock_items,
            "corrections": corrections,
        },
        event,
    )


def _handle_get_stores(event: dict[str, Any], ddb) -> dict[str, Any]:
    stores = _scan_all(ddb.Table(STORE_LIST_TABLE))
    captures = _scan_all(ddb.Table(CAPTURES_TABLE))
    last_by_store: dict[str, str] = {}
    for c in captures:
        sid = c.get("store_id", "")
        ts = str(c.get("capture_timestamp", ""))
        if ts > last_by_store.get(sid, ""):
            last_by_store[sid] = ts

    enriched = []
    for st in stores:
        sid = st["store_id"]
        enriched.append(
            {
                **st,
                "last_capture_timestamp": last_by_store.get(sid),
                "has_recent_capture": sid in last_by_store,
            }
        )

    return _json_response(
        200,
        {
            "items": enriched,
            "total": len(enriched),
            "active_monitored": sum(1 for s in enriched if s["has_recent_capture"]),
        },
        event,
    )


def _handle_search(event: dict[str, Any], ddb) -> dict[str, Any]:
    q = ((event.get("queryStringParameters") or {}).get("q") or "").strip().lower()
    products, _, _ = _load_products_catalog(ddb)
    if q:
        products = [
            p
            for p in products
            if q
            in f"{p['sku_id']} {p['sku_name']} {p.get('model_alias', '')} {p.get('barcode', '')} {p.get('brand', '')}".lower()
        ]
    products.sort(key=lambda x: x["unit_count"], reverse=True)
    return _json_response(200, {"products": products[:10], "total": len(products)}, event)


def _handle_review_queue(event: dict[str, Any], s3, ddb) -> dict[str, Any]:
    status_filter = (event.get("queryStringParameters") or {}).get("status") or ""
    items = _scan_all(ddb.Table(REVIEW_QUEUE_TABLE))
    if status_filter and status_filter.lower() != "all":
        items = [i for i in items if (i.get("status") or "").lower() == status_filter.lower()]
    items.sort(key=lambda x: str(x.get("capture_timestamp", "")), reverse=True)

    for item in items:
        item["bounding_box"] = json.loads(item.get("bounding_box_json") or "[]")
        item["frame_presigned_url"] = _presign_frame(s3, item.get("image_key", ""), item.get("source_bucket", ""))

    return _json_response(200, {"items": items, "total": len(items)}, event)


def _handle_post_correction(event: dict[str, Any], user: dict[str, Any], ddb) -> dict[str, Any]:
    body = _parse_body(event)
    store_id = body.get("store_id") or "DEMO-S01"
    queue_key = body.get("queue_key", "")
    sku_id = body.get("sku_id", "")
    action = body.get("action", "correct")  # "correct" or "confirm"
    now_iso = datetime.now(ICT).isoformat(timespec="seconds")

    if action == "confirm":
        if queue_key:
            ddb.Table(REVIEW_QUEUE_TABLE).update_item(
                Key={"store_id": store_id, "queue_key": queue_key},
                UpdateExpression="SET #s = :st, reviewed_by = :u, reviewed_at = :t",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":st": "Đã xác nhận", ":u": user["email"], ":t": now_iso},
            )
        return _json_response(200, {"status": "Đã xác nhận", "reviewed_at": now_iso}, event)

    correction_id = f"COR-{datetime.now(ICT).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
    corr_item = to_dynamodb_safe(
        {
            "store_id": store_id,
            "correction_id": correction_id,
            "reading_id": body.get("reading_id", ""),
            "capture_id": body.get("capture_id", ""),
            "sku_id": sku_id,
            "corrected_sku_id": body.get("corrected_sku_id") or sku_id,
            "corrected_unit_count": body.get("corrected_unit_count"),
            "discrepancy_category": body.get("discrepancy_category") or "Wrong SKU",
            "sku_match_correct": bool(body.get("sku_match_correct", False)),
            "notes": body.get("notes", ""),
            "reviewer_email": user["email"],
            "correction_date": now_iso,
            "fed_back_to_model": False,
        }
    )
    ddb.Table(CORRECTIONS_TABLE).put_item(Item=corr_item)

    if queue_key:
        ddb.Table(REVIEW_QUEUE_TABLE).update_item(
            Key={"store_id": store_id, "queue_key": queue_key},
            UpdateExpression="SET #s = :st, reviewed_by = :u, reviewed_at = :t, correction_id = :cid",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":st": "Đã sửa",
                ":u": user["email"],
                ":t": now_iso,
                ":cid": correction_id,
            },
        )

    return _json_response(201, {"correction_id": correction_id, "status": "Đã sửa", "correction_date": now_iso}, event)


def _handle_import_sku_master(event: dict[str, Any], ddb) -> dict[str, Any]:
    body = _parse_body(event)
    items = body.get("items", [])
    if not isinstance(items, list):
        return _json_response(400, {"error": "items must be a list"}, event)

    tbl = ddb.Table(SKU_MASTER_TABLE)
    written = 0
    for row in items:
        sku_id = row.get("sku_id") or row.get("sku_name_vi")
        if not sku_id:
            continue
        tbl.put_item(
            Item=to_dynamodb_safe(
                {
                    "sku_id": sku_id,
                    "sku_name_vi": row.get("sku_name_vi") or sku_id,
                    "sku_name_en": row.get("sku_name_en"),
                    "model_alias": row.get("model_alias", ""),
                    "brand": row.get("brand"),
                    "manufacturer": row.get("manufacturer"),
                    "category": row.get("category"),
                    "subcategory": row.get("subcategory"),
                    "pack_type": row.get("pack_type"),
                    "pack_size": row.get("pack_size"),
                    "barcode": row.get("barcode"),
                    "image_url": row.get("image_url"),
                    "is_active": bool(row.get("is_active", True)),
                    "updated_at": datetime.now(ICT).isoformat(timespec="seconds"),
                }
            )
        )
        written += 1

    return _json_response(200, {"imported": written}, event)


def _handle_import_store_list(event: dict[str, Any], ddb) -> dict[str, Any]:
    body = _parse_body(event)
    items = body.get("items", [])
    if not isinstance(items, list):
        return _json_response(400, {"error": "items must be a list"}, event)

    tbl = ddb.Table(STORE_LIST_TABLE)
    written = 0
    for row in items:
        store_id = row.get("store_id")
        if not store_id:
            continue
        tbl.put_item(
            Item=to_dynamodb_safe(
                {
                    "store_id": store_id,
                    "store_name": row.get("store_name") or store_id,
                    "district": row.get("district", ""),
                    "camera_id": row.get("camera_id", ""),
                    "categories_in_view": row.get("categories_in_view", ["Milk"]),
                    "wifi_available": bool(row.get("wifi_available", True)),
                    "status": row.get("status", "active"),
                    "updated_at": datetime.now(ICT).isoformat(timespec="seconds"),
                }
            )
        )
        written += 1

    return _json_response(200, {"imported": written}, event)


def _handle_presigned_upload(event: dict[str, Any], user: dict[str, Any], s3) -> dict[str, Any]:
    body = _parse_body(event)
    upload_type = body.get("type", "human_audit")  # human_audit | phone_capture | sd_card
    filename = os.path.basename(body.get("filename") or f"upload-{int(time.time())}.csv")
    content_type = body.get("content_type") or "application/octet-stream"
    date_part = datetime.now(ICT).strftime("%Y-%m-%d")
    key = f"uploads/{upload_type}/{date_part}/{uuid.uuid4().hex[:8]}_{filename}"

    url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": ANALYTICS_BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=600,
    )
    return _json_response(
        200,
        {"upload_url": url, "s3_key": key, "expires_in": 600, "requested_by": user["email"]},
        event,
    )


def _handle_export_csv(kind: str, event: dict[str, Any], ddb) -> dict[str, Any]:
    params = event.get("queryStringParameters") or {}
    camera = params.get("camera") or ""
    date_prefix = params.get("date") or ""  # YYYY-MM-DD

    captures = _scan_all(ddb.Table(CAPTURES_TABLE))
    if camera:
        captures = [c for c in captures if c.get("camera_id") == camera]
    if date_prefix:
        captures = [c for c in captures if str(c.get("capture_timestamp", "")).startswith(date_prefix)]
    captures.sort(key=lambda c: str(c.get("capture_timestamp", "")))

    if kind == "capture-log":
        logs = [json.loads(c["log_json"]) for c in captures if c.get("log_json")]
        csv_text = to_csv(logs, CAPTURE_LOG_COLUMNS, bom=True)
        return _json_response(
            200,
            csv_text,
            event,
            content_type="text/csv; charset=utf-8",
            extra_headers={"Content-Disposition": 'attachment; filename="capture-log.csv"'},
        )

    all_rows: list[dict[str, Any]] = []
    for c in captures:
        if c.get("rows_json"):
            all_rows.extend(json.loads(c["rows_json"]))
    csv_text = to_csv(all_rows, CV_OUTPUT_COLUMNS, bom=True)
    return _json_response(
        200,
        csv_text,
        event,
        content_type="text/csv; charset=utf-8",
        extra_headers={"Content-Disposition": 'attachment; filename="cv-output.csv"'},
    )


def _handle_kpi(event: dict[str, Any], ddb) -> dict[str, Any]:
    products, unrecognized_units, total_stores = _load_products_catalog(ddb)
    # only the two fields used: the full items (rows, boxes) are ~18 MB and took ~9 s per call to read
    captures = _scan_all(ddb.Table(CAPTURES_TABLE), ProjectionExpression="store_id, processing_time_ms")
    active_stores = len({c.get("store_id") for c in captures if c.get("store_id")})

    # Per A7 (doc p.7): avg_processing_time_ms = mean of one value per capture from capture_log
    proc_times = [int(c.get("processing_time_ms", 0)) for c in captures if int(c.get("processing_time_ms", 0)) > 0]
    avg_proc_ms = round(sum(proc_times) / len(proc_times)) if proc_times else 0
    total_units = sum(p["unit_count"] for p in products)

    return _json_response(
        200,
        {
            "active_stores_monitored": active_stores,
            "total_stores": total_stores,
            "total_on_shelf_units": total_units,
            "unrecognized_units": unrecognized_units,
            "avg_processing_time_ms": avg_proc_ms,
            "top_50_scope_note": TOP_50_NOTE,
            "captures_count": len(captures),
            "flag_threshold": MILK_FLAG_THRESHOLD,
            **_shelf_kpis(ddb, event.get("queryStringParameters") or {}),
        },
        event,
    )


# --- Dashboard shelf numbers (spec docs/superpowers/specs/2026-11-24-dashboard-shelf-metrics-design.md) -------

TOP_50_NOTE = "All SKUs: Datagent has not sent a top-50 list yet"
ALERT_TYPES = {"OOS", "LOW_STOCK", "DEPLETED"}
TREND_METRICS = {"total_stock", "oos", "accuracy", "restock_volume", "osa"}


def _r(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


def _days_param(params: dict[str, Any], default: int = 14) -> int:
    try:
        days = int(params.get("days") or default)
    except ValueError:
        days = default
    return max(1, min(days, shelf.ROLLUP_TTL_DAYS))


def _stores_for(ddb, params: dict[str, Any]) -> list[dict[str, Any]]:
    wanted = params.get("store_id")
    return [s for s in _scan_all(ddb.Table(STORE_LIST_TABLE)) if not wanted or s["store_id"] == wanted]


def _category_skus(ddb, category: str | None) -> set[str] | None:
    """SKUs of one SKU master category; None means every SKU."""
    if not category or category.lower() == "all":
        return None
    return {s["sku_id"] for s in _scan_all(ddb.Table(SKU_MASTER_TABLE)) if (s.get("category") or "") == category}


def _windows(days: int) -> tuple[list[str], list[str]]:
    """Rollup keys of the current period and of the previous one of the same length: hour# keys of today and of
    yesterday up to this hour for 1 day, else day# keys ending today."""
    now = _now()
    if days == 1:
        yesterday = now - timedelta(days=1)
        hours = range(now.hour + 1)
        return [f"hour#{now:%Y%m%d}-{h:02d}" for h in hours], [f"hour#{yesterday:%Y%m%d}-{h:02d}" for h in hours]
    current = [f"day#{now - timedelta(days=i):%Y%m%d}" for i in range(days - 1, -1, -1)]
    previous = [f"day#{now - timedelta(days=i):%Y%m%d}" for i in range(2 * days - 1, days - 1, -1)]
    return current, previous


def _rollups_by_key(ddb, stores: list[dict[str, Any]], keys: list[str]) -> dict[str, list[dict[str, Any]]]:
    """The stores' rollup items for the given keys (all hour# or all day#), grouped by key."""
    wanted, found = set(keys), defaultdict(list)
    if not keys:
        return found
    for store in stores:
        cond = Key("store_id").eq(store["store_id"]) & Key("key").between(min(keys), max(keys))
        for item in _query_all(ddb.Table(SHELF_TABLE), KeyConditionExpression=cond):
            if item["key"] in wanted:
                found[item["key"]].append(item)
    return found


def _point_label(key: str) -> str:
    """day#20261127 → 2026-11-27; hour#20261128-09 → 20261128-09."""
    kind, value = key.split("#", 1)
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}" if kind == "day" else value


def _with_hours(stores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [s for s in stores if s.get("open_time") and s.get("close_time")]


def _done_audits(ddb, stores: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    since = (_now() - timedelta(days=days)).isoformat(timespec="seconds")
    store_ids = {s["store_id"] for s in stores}
    return [
        _audit_view(a)
        for a in _scan_all(ddb.Table(AUDITS_TABLE))
        if a.get("status") == "done" and a.get("store_id") in store_ids and str(a.get("capture_timestamp", "")) >= since
    ]


def _oos_now(ddb, stores: list[dict[str, Any]], skus: set[str] | None) -> dict[str, Any]:
    """Expected SKUs whose shelf state is OOS at the last check."""
    count, as_of = 0, None
    for store in stores:
        state = from_dynamodb(
            ddb.Table(SHELF_TABLE).get_item(Key={"store_id": store["store_id"], "key": "state"}).get("Item")
        )
        if not state:
            continue
        expected = set(_shelf_plan_view(ddb, store)["expected_skus"])
        for sku, st in (state.get("skus") or {}).items():
            if sku in expected and (skus is None or sku in skus) and (st or {}).get("status") == "OOS":
                count += 1
        as_of = max(as_of or "", state.get("last_bucket") or "") or None
    if as_of is None:
        return {"count": None, "as_of": None, "blocked_reason": "no_checks"}
    return {"count": count, "as_of": as_of, "blocked_reason": None}


def _shelf_kpis(ddb, params: dict[str, Any]) -> dict[str, Any]:
    """OSA, restock rate, out-of-stock now and top-50 accuracy for the Dashboard filters (days, store_id,
    category). A number the data cannot give is None with a blocked_reason."""
    days = _days_param(params)
    stores = _stores_for(ddb, params)
    skus = _category_skus(ddb, params.get("category"))
    open_stores = _with_hours(stores)
    out: dict[str, Any] = {"days": days}
    if not open_stores:
        blocked = {"blocked_reason": "no_hours"}
        out["osa"] = {"value": None, "previous": None, **blocked}
        out["restock_rate"] = {"units_per_day": None, "previous_units_per_day": None, "change_pct": None, **blocked}
        out["oos_now"] = {"count": None, "as_of": None, **blocked}
    else:
        current_keys, previous_keys = _windows(days)
        current = shelf.totals([i for v in _rollups_by_key(ddb, open_stores, current_keys).values() for i in v], skus)
        previous = shelf.totals([i for v in _rollups_by_key(ddb, open_stores, previous_keys).values() for i in v], skus)
        out["osa"] = {
            "value": _r(current["osa"], 4),
            "previous": _r(previous["osa"], 4),
            "blocked_reason": None if current["osa"] is not None else "no_checks",
        }
        rate = current["restock_units"] / days if current["store_checks"] else None
        previous_rate = previous["restock_units"] / days if previous["store_checks"] else None
        change = shelf.change_pct(rate, previous_rate)
        reason = "no_checks" if rate is None else ("no_previous" if change is None else None)
        out["restock_rate"] = {
            "units_per_day": _r(rate, 1),
            "previous_units_per_day": _r(previous_rate, 1),
            "change_pct": change,
            "blocked_reason": reason,
        }
        out["oos_now"] = _oos_now(ddb, open_stores, skus)
    audits = _done_audits(ddb, stores, days)
    value = summarize(audits, [])["kpis"]["sku_identification_accuracy"]["value"] if audits else None
    out["top_50_sku_accuracy"] = {
        "value": value,
        "n_frames": len(audits),
        "scope_note": TOP_50_NOTE,
        "blocked_reason": None if value is not None else "no_labels",
    }
    return out


def _handle_reports_trends(event: dict[str, Any], ddb) -> dict[str, Any]:
    """One point per day (per hour for days=1) of the chosen metric; None where nothing was counted."""
    params = event.get("queryStringParameters") or {}
    metric = params.get("metric") or "total_stock"
    if metric not in TREND_METRICS:
        return _json_response(400, {"error": "INVALID_METRIC", "allowed": sorted(TREND_METRICS)}, event)
    days = _days_param(params)
    stores = _stores_for(ddb, params)
    keys, _ = _windows(days)
    if metric == "accuracy":
        dates = sorted({_point_label(k)[:10] if k.startswith("day#") else _now().strftime("%Y-%m-%d") for k in keys})
        by_day = {
            d["day"]: d["overall_identification_accuracy"]
            for d in summarize(_done_audits(ddb, stores, days), [])["by_day"]
        }
        points = [{"t": date, "value": by_day.get(date)} for date in dates]
    else:
        skus = _category_skus(ddb, params.get("category"))
        by_key = _rollups_by_key(ddb, _with_hours(stores), keys)
        points = []
        for key in keys:
            t = shelf.totals(by_key.get(key, []), skus)
            value = None
            if t["store_checks"]:
                value = {
                    "total_stock": _r(t["avg_total_units"], 1),
                    "osa": _r(t["osa"], 4),
                    "oos": t["oos_started"],
                    "restock_volume": t["restock_units"],
                }[metric]
            points.append({"t": _point_label(key), "value": value})
    return _json_response(200, {"metric": metric, "days": days, "points": points}, event)


def _handle_shelf_events(event: dict[str, Any], ddb) -> dict[str, Any]:
    """Shelf events newest first, filtered by kind (all, alerts, restocked), store and category, a page at a time."""
    params = event.get("queryStringParameters") or {}
    days = _days_param(params)
    kind = params.get("kind") or "all"
    try:
        limit = max(1, min(int(params.get("limit") or 20), 200))
    except ValueError:
        limit = 20
    stores = _stores_for(ddb, params)
    master = {s["sku_id"]: s for s in _scan_all(ddb.Table(SKU_MASTER_TABLE))}
    skus = _category_skus(ddb, params.get("category"))
    first = (_now() - timedelta(days=days - 1)).strftime("%Y%m%d") + "-0000"
    items = []
    for store in stores:
        cond = Key("store_id").eq(store["store_id"]) & Key("event_key").gte(first)
        for item in _query_all(ddb.Table(SHELF_EVENTS_TABLE), KeyConditionExpression=cond):
            if kind == "alerts" and item["type"] not in ALERT_TYPES:
                continue
            if kind == "restocked" and item["type"] != "RESTOCKED":
                continue
            if skus is not None and item["sku_id"] not in skus:
                continue
            item.pop("expires_at", None)
            item["store_name"] = store.get("store_name") or store["store_id"]
            item["sku_name"] = (master.get(item["sku_id"]) or {}).get("sku_name_vi") or item["sku_id"]
            items.append(item)
    items.sort(key=lambda e: (e["event_key"], e["store_id"]), reverse=True)
    cursor = params.get("cursor") or ""
    if cursor:
        items = [e for e in items if f"{e['event_key']}|{e['store_id']}" < cursor]
    page = items[:limit]
    next_cursor = f"{page[-1]['event_key']}|{page[-1]['store_id']}" if len(items) > limit else None
    return _json_response(200, {"items": page, "next_cursor": next_cursor}, event)


def _handle_reports_series(event: dict[str, Any], ddb) -> dict[str, Any]:
    """Per day: average units of the expected SKUs per counted check, the largest check total, and the checks."""
    params = event.get("queryStringParameters") or {}
    days = max(2, _days_param(params, default=shelf.ROLLUP_TTL_DAYS))
    skus = _category_skus(ddb, params.get("category"))
    keys, _ = _windows(days)
    by_key = _rollups_by_key(ddb, _stores_for(ddb, params), keys)
    series = []
    for key in keys:
        items = by_key.get(key, [])
        t = shelf.totals(items, skus)
        if t["store_checks"]:
            series.append(
                {
                    "date": _point_label(key),
                    "avg_units": _r(t["avg_total_units"], 1),
                    "max_units": max(int(i.get("max_total", 0)) for i in items),
                    "checks": t["store_checks"],
                }
            )
    return _json_response(200, {"series": series}, event)


def _handle_get_settings(event: dict[str, Any], user: dict[str, Any], ddb) -> dict[str, Any]:
    """Phase-1 Settings (5 approved sections per NHAT-P01 / doc p.14-15)."""
    prefs = from_dynamodb(ddb.Table(USER_PREFS_TABLE).get_item(Key={"user_sub": user["sub"]}).get("Item") or {})
    stores = _scan_all(ddb.Table(STORE_LIST_TABLE))
    return _json_response(
        200,
        {
            "account": {
                "email": user["email"],
                "groups": user["groups"],
                "readonly": True,
            },
            "preferences": {
                "date_format": prefs.get("date_format", "DD MMM YYYY, HH:mm"),
                "default_landing": prefs.get("default_landing", "Home"),
            },
            "timezone": {"value": "Asia/Ho_Chi_Minh (UTC+7)", "readonly": True},
            "flag_threshold": {"value": MILK_FLAG_THRESHOLD, "readonly": True},
            "stores": stores,
        },
        event,
    )


def _handle_put_settings(event: dict[str, Any], user: dict[str, Any], ddb) -> dict[str, Any]:
    body = _parse_body(event)
    date_format = body.get("date_format", "DD MMM YYYY, HH:mm")
    default_landing = body.get("default_landing", "Home")
    now_iso = datetime.now(ICT).isoformat(timespec="seconds")

    ddb.Table(USER_PREFS_TABLE).put_item(
        Item={
            "user_sub": user["sub"],
            "email": user["email"],
            "date_format": date_format,
            "default_landing": default_landing,
            "updated_at": now_iso,
        }
    )
    return _json_response(
        200,
        {"date_format": date_format, "default_landing": default_landing, "updated_at": now_iso},
        event,
    )


def _handle_seed_initial_data(event: dict[str, Any], ddb) -> dict[str, Any]:
    """Seed initial DEMO-S01 store and 16 SKUs (12 milk + 4 Slide snacks per doc p.8)."""
    now_iso = datetime.now(ICT).isoformat(timespec="seconds")
    ddb.Table(STORE_LIST_TABLE).put_item(
        Item=to_dynamodb_safe(
            {
                "store_id": "DEMO-S01",
                "store_name": "Demo Store S01",
                "district": "Ho Chi Minh City",
                "camera_id": "CAM-S01-A",
                "categories_in_view": ["Milk", "Snacks"],
                "wifi_available": True,
                "status": "active",
                "updated_at": now_iso,
            }
        )
    )
    sku_tbl = ddb.Table(SKU_MASTER_TABLE)
    for alias, meta in DEFAULT_ALIAS_MAP.items():
        sku_tbl.put_item(
            Item=to_dynamodb_safe(
                {
                    "sku_id": meta["sku_id"],
                    "sku_name_vi": meta["sku_name_vi"],
                    "sku_name_en": meta["sku_name_en"],
                    "model_alias": alias,
                    "brand": meta["brand"],
                    "manufacturer": meta["manufacturer"],
                    "category": meta["category"],
                    "subcategory": meta["subcategory"],
                    "pack_type": meta["pack_type"],
                    "pack_size": meta["pack_size"],
                    "barcode": None,
                    "image_url": meta.get("image_url"),
                    "is_active": True,
                    "updated_at": now_iso,
                }
            )
        )
    return _json_response(200, {"seeded_stores": 1, "seeded_skus": len(DEFAULT_ALIAS_MAP)}, event)


# --- Shelf plan per store (spec docs/superpowers/specs/2026-11-24-dashboard-shelf-metrics-design.md) ----------


def _store_item(ddb, store_id: str) -> dict[str, Any] | None:
    return from_dynamodb(ddb.Table(STORE_LIST_TABLE).get_item(Key={"store_id": store_id}).get("Item"))


def _shelf_days(ddb, store_id: str, first_day: str, last_day: str) -> list[dict[str, Any]]:
    """day# rollups of a store from first_day through last_day (YYYYMMDD), oldest first."""
    cond = Key("store_id").eq(store_id) & Key("key").between(f"day#{first_day}", f"day#{last_day}")
    return _query_all(ddb.Table(SHELF_TABLE), KeyConditionExpression=cond)


def _suggested_skus(ddb, store_id: str) -> list[dict[str, str]]:
    """SKUs seen with a box at 0.70 or more in the last SUGGEST_DAYS days, with the last day each was seen."""
    today = _now()
    first = (today - timedelta(days=shelf.SUGGEST_DAYS - 1)).strftime("%Y%m%d")
    last_seen: dict[str, str] = {}
    for day in _shelf_days(ddb, store_id, first, today.strftime("%Y%m%d")):
        date = day["key"][4:]
        for sku in day.get("confident_skus") or []:
            last_seen[sku] = max(last_seen.get(sku, ""), f"{date[:4]}-{date[4:6]}-{date[6:]}")
    return [{"sku_id": sku, "last_seen": last_seen[sku]} for sku in sorted(last_seen)]


def _shelf_plan_view(ddb, store: dict[str, Any]) -> dict[str, Any]:
    suggested = _suggested_skus(ddb, store["store_id"])
    saved = sorted(store.get("expected_skus") or [])
    return {
        "store_id": store["store_id"],
        "open_time": store.get("open_time"),
        "close_time": store.get("close_time"),
        "expected_skus": saved or [s["sku_id"] for s in suggested],
        "source": "saved" if saved else "suggested",
        "suggested": suggested,
        "updated_by": store.get("shelf_plan_updated_by"),
        "updated_at": store.get("shelf_plan_updated_at"),
    }


def _handle_get_shelf_plan(store_id: str, event: dict[str, Any], ddb) -> dict[str, Any]:
    store = _store_item(ddb, store_id)
    if not store:
        return _json_response(404, {"error": "STORE_NOT_FOUND"}, event)
    return _json_response(200, _shelf_plan_view(ddb, store), event)


def _handle_put_shelf_plan(store_id: str, event: dict[str, Any], user: dict[str, Any], ddb) -> dict[str, Any]:
    """team_admin saves opening hours and expected SKUs; the next shelf_tick recomputes the last 15 days."""
    if not _store_item(ddb, store_id):
        return _json_response(404, {"error": "STORE_NOT_FOUND"}, event)
    body = _parse_body(event)
    open_time, close_time = str(body.get("open_time") or ""), str(body.get("close_time") or "")
    if not shelf.valid_hours(open_time, close_time):
        return _json_response(400, {"error": "INVALID_HOURS"}, event)
    skus = body.get("expected_skus") or []
    if not isinstance(skus, list) or not all(isinstance(s, str) for s in skus):
        return _json_response(400, {"error": "INVALID_SKUS"}, event)
    known = {s["sku_id"] for s in _scan_all(ddb.Table(SKU_MASTER_TABLE))}
    unknown = sorted({s for s in skus if s not in known})
    if unknown:
        return _json_response(400, {"error": "UNKNOWN_SKU", "skus": unknown}, event)
    now_iso = _now().isoformat(timespec="seconds")
    values = {
        ":o": open_time,
        ":c": close_time,
        ":by": user["email"],
        ":at": now_iso,
    }
    update = "SET open_time = :o, close_time = :c, shelf_plan_updated_by = :by, shelf_plan_updated_at = :at, "
    update += "shelf_recompute_requested_at = :at"
    if skus:
        update += ", expected_skus = :skus"
        values[":skus"] = sorted(set(skus))
    else:  # an empty list means: use the suggestion again
        update += " REMOVE expected_skus"
    ddb.Table(STORE_LIST_TABLE).update_item(
        Key={"store_id": store_id}, UpdateExpression=update, ExpressionAttributeValues=values
    )
    return _json_response(200, _shelf_plan_view(ddb, _store_item(ddb, store_id)), event)


# --- Model page (spec docs/superpowers/specs/2026-11-23-model-quality-page-design.md) -------------------------


def _audit_view(item: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in item.items() if not k.endswith("_json")}
    out["ai_boxes"] = json.loads(item.get("ai_boxes_json") or "[]")
    out["verdicts"] = json.loads(item.get("verdicts_json") or "[]")
    out["missed"] = json.loads(item.get("missed_json") or "[]")
    return out


def _find_audit(ddb, audit_id: str) -> dict[str, Any] | None:
    found = [a for a in _scan_all(ddb.Table(AUDITS_TABLE)) if a.get("audit_id") == audit_id]
    return found[0] if found else None


def _within_days(ts: str, days: int) -> bool:
    if days <= 0:
        return True
    try:
        return datetime.fromisoformat(ts) >= datetime.now(ICT) - timedelta(days=days)
    except ValueError:
        return False


def _sku_choices(ddb) -> dict[str, str]:
    """Model label -> official product name: SKU Master first, the built-in alias table for the rest."""
    choices = {s["model_alias"]: s["sku_id"] for s in _scan_all(ddb.Table(SKU_MASTER_TABLE)) if s.get("model_alias")}
    for label, entry in DEFAULT_ALIAS_MAP.items():
        choices.setdefault(label, entry["sku_id"])
    return choices


def _handle_model_audits(event: dict[str, Any], ddb) -> dict[str, Any]:
    params = event.get("queryStringParameters") or {}
    status = params.get("status") or ""
    days = int(params.get("days") or 7)
    audits = [a for a in _scan_all(ddb.Table(AUDITS_TABLE)) if _within_days(str(a.get("capture_timestamp", "")), days)]
    counts = {s: sum(1 for a in audits if a.get("status") == s) for s in ("pending", "done", "skipped")}
    chosen = sorted(
        (a for a in audits if not status or a.get("status") == status),
        key=lambda a: str(a.get("capture_timestamp", "")),
        reverse=True,
    )
    items = [
        {
            "audit_id": a["audit_id"],
            "camera_id": a.get("camera_id"),
            "capture_id": a.get("capture_id"),
            "capture_timestamp": a.get("capture_timestamp"),
            "model_version": a.get("model_version"),
            "status": a.get("status"),
            "n_boxes": len(json.loads(a.get("ai_boxes_json") or "[]")),
            "labeled_by": a.get("labeled_by"),
        }
        for a in chosen
    ]
    return _json_response(200, {"items": items, "counts": counts}, event)


def _handle_model_audit_get(audit_id: str, event: dict[str, Any], s3, ddb) -> dict[str, Any]:
    audit = _find_audit(ddb, audit_id)
    if not audit:
        return _json_response(404, {"error": "NOT_FOUND", "audit_id": audit_id}, event)
    view = _audit_view(audit)
    view["frame_url"] = _presign_frame(s3, audit.get("image_key", ""), ANALYTICS_BUCKET)
    view["sku_choices"] = sorted(
        ({"label": label, "name": name} for label, name in _sku_choices(ddb).items()), key=lambda c: c["name"]
    )
    return _json_response(200, view, event)


def _set_audit(ddb, audit: dict[str, Any], values: dict[str, Any], remove: tuple[str, ...] = ()) -> dict[str, Any]:
    names = {f"#{k}": k for k in values}
    expr = "SET " + ", ".join(f"#{k} = :{k}" for k in values)
    if remove:
        expr += " REMOVE " + ", ".join(remove)
    table = ddb.Table(AUDITS_TABLE)
    key = {"store_id": audit["store_id"], "audit_id": audit["audit_id"]}
    table.update_item(
        Key=key,
        UpdateExpression=expr,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues={f":{k}": v for k, v in values.items()},
    )
    return from_dynamodb(table.get_item(Key=key)["Item"])


def _handle_model_audit_put(audit_id: str, event: dict[str, Any], user: dict[str, Any], ddb) -> dict[str, Any]:
    audit = _find_audit(ddb, audit_id)
    if not audit:
        return _json_response(404, {"error": "NOT_FOUND", "audit_id": audit_id}, event)
    body = _parse_body(event)
    verdicts, missed = body.get("verdicts"), body.get("missed")
    if not isinstance(verdicts, list) or not isinstance(missed, list):
        return _json_response(400, {"error": "INVALID_LABELS", "message": "verdicts and missed must be lists"}, event)
    errors = validate_labels(json.loads(audit.get("ai_boxes_json") or "[]"), verdicts, missed, set(_sku_choices(ddb)))
    if any(not isinstance(m.get("x"), (int, float)) or not isinstance(m.get("y"), (int, float)) for m in missed):
        errors.append("every missed point needs numbers x and y")
    if errors:
        return _json_response(400, {"error": "INVALID_LABELS", "message": "; ".join(errors)}, event)
    clean_verdicts = [
        {
            "box_id": v["box_id"],
            "verdict": v["verdict"],
            **({"true_sku_id": v["true_sku_id"]} if v["verdict"] == "wrong_sku" else {}),
        }
        for v in verdicts
    ]
    clean_missed = [{"sku_id": m["sku_id"], "x": m["x"], "y": m["y"]} for m in missed]
    saved = _set_audit(
        ddb,
        audit,
        {
            "verdicts_json": json.dumps(clean_verdicts, separators=(",", ":")),
            "missed_json": json.dumps(clean_missed, separators=(",", ":")),
            "status": "done",
            "labeled_by": user["email"],
            "labeled_at": datetime.now(ICT).isoformat(timespec="seconds"),
        },
        remove=("skip_reason", "skip_note"),
    )
    return _json_response(200, _audit_view(saved), event)


def _handle_model_audit_skip(audit_id: str, event: dict[str, Any], user: dict[str, Any], ddb) -> dict[str, Any]:
    audit = _find_audit(ddb, audit_id)
    if not audit:
        return _json_response(404, {"error": "NOT_FOUND", "audit_id": audit_id}, event)
    body = _parse_body(event)
    if body.get("reason") not in SKIP_REASONS:
        return _json_response(
            400, {"error": "INVALID_REASON", "message": f"reason must be one of {list(SKIP_REASONS)}"}, event
        )
    saved = _set_audit(
        ddb,
        audit,
        {
            "status": "skipped",
            "skip_reason": body["reason"],
            "skip_note": str(body.get("note") or "")[:500],
            "labeled_by": user["email"],
            "labeled_at": datetime.now(ICT).isoformat(timespec="seconds"),
        },
    )
    return _json_response(200, _audit_view(saved), event)


def _hour_within_days(hour: str, days: int) -> bool:
    if days <= 0:
        return True
    try:
        start = datetime.strptime(hour, "%Y%m%d-%H").replace(tzinfo=ICT)
    except ValueError:
        return False
    return start >= datetime.now(ICT) - timedelta(days=days)


def _handle_model_summary(event: dict[str, Any], ddb) -> dict[str, Any]:
    params = event.get("queryStringParameters") or {}
    days = int(params.get("days") or 7)
    version = params.get("model_version") or "all"
    done = [
        a
        for a in _scan_all(ddb.Table(AUDITS_TABLE))
        if a.get("status") == "done" and _within_days(str(a.get("capture_timestamp", "")), days)
    ]
    latest: dict[str, str] = {}
    for a in done:
        v = a.get("model_version") or "unknown"
        latest[v] = max(latest.get(v, ""), str(a.get("capture_timestamp", "")))
    chosen = [a for a in done if version == "all" or (a.get("model_version") or "unknown") == version]
    health = [h for h in _scan_all(ddb.Table(MODEL_HEALTH_TABLE)) if _hour_within_days(str(h.get("hour", "")), days)]
    processing = [
        float(h["processing_ms_median"])
        for h in health
        if "processing_ms_median" in h
        for _ in range(int(h.get("captures", 0)))
    ]
    return _json_response(
        200,
        {
            **summarize([_audit_view(a) for a in chosen], processing),
            "model_versions": sorted(latest, key=lambda v: latest[v], reverse=True),
            "range": {"days": days, "model_version": version},
        },
        event,
    )


def _handle_model_health(event: dict[str, Any], ddb) -> dict[str, Any]:
    params = event.get("queryStringParameters") or {}
    days = int(params.get("days") or 7)
    items = sorted(
        (h for h in _scan_all(ddb.Table(MODEL_HEALTH_TABLE)) if _hour_within_days(str(h.get("hour", "")), days)),
        key=lambda h: (str(h.get("hour", "")), str(h.get("camera_id", ""))),
    )
    return _json_response(200, {"items": items}, event)


def _route_model(method: str, route_path: str, event: dict[str, Any], user: dict[str, Any], s3, ddb):
    if method == "GET" and route_path == "/model/summary":
        return _handle_model_summary(event, ddb)
    if method == "GET" and route_path == "/model/health":
        return _handle_model_health(event, ddb)
    parts = route_path.strip("/").split("/")  # model, audits, <id>, skip
    if parts[:2] == ["model", "audits"]:
        if len(parts) == 2 and method == "GET":
            return _handle_model_audits(event, ddb)
        if len(parts) == 3 and method == "GET":
            return _handle_model_audit_get(parts[2], event, s3, ddb)
        if len(parts) == 3 and method == "PUT":
            return _handle_model_audit_put(parts[2], event, user, ddb)
        if len(parts) == 4 and parts[3] == "skip" and method == "POST":
            return _handle_model_audit_skip(parts[2], event, user, ddb)
    return _json_response(404, {"error": "ROUTE_NOT_FOUND", "method": method, "path": route_path}, event)


def lambda_handler(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    method = (event.get("httpMethod") or "GET").upper()
    path = event.get("path") or "/"
    # Strip optional stage prefix (/v1) if present
    if path.startswith("/v1/"):
        route_path = path[3:]
    elif path == "/v1":
        route_path = "/"
    else:
        route_path = path

    if method == "OPTIONS":
        return _json_response(204, "", event)

    # Public health endpoint
    if method == "GET" and route_path == "/health":
        return _json_response(
            200,
            {
                "status": "ok",
                "service": "milk-backend-api",
                "region": REGION,
                "flag_threshold": MILK_FLAG_THRESHOLD,
            },
            event,
        )

    user = _extract_user(event)

    # /me allows checking current Cognito group status (even if pending assignment)
    if method == "GET" and route_path == "/me":
        return _json_response(
            200,
            {
                "sub": user["sub"],
                "email": user["email"],
                "groups": user["groups"],
                "approved": bool(user["groups"]),
            },
            event,
        )

    # All other endpoints require an assigned Cognito group
    denied = _require_groups(user, VALID_GROUPS, event)
    if denied:
        return denied

    s3, ddb = _clients()

    try:
        if route_path.startswith("/model/"):
            err = _require_groups(user, WRITE_CORRECTION_GROUPS, event)
            if err:
                return err
            return _route_model(method, route_path, event, user, s3, ddb)

        if method == "GET" and route_path == "/products":
            return _handle_get_products(event, ddb)

        if method == "GET" and route_path.startswith("/products/"):
            sku_param = route_path[len("/products/") :]
            return _handle_get_product_detail(sku_param, event, s3, ddb)

        if method == "GET" and route_path == "/stores":
            return _handle_get_stores(event, ddb)

        if route_path.startswith("/stores/") and route_path.endswith("/shelf-plan"):
            store_id = urllib.parse.unquote(route_path[len("/stores/") : -len("/shelf-plan")])
            if method == "GET":
                return _handle_get_shelf_plan(store_id, event, ddb)
            if method == "PUT":
                err = _require_groups(user, ADMIN_GROUPS, event)
                if err:
                    return err
                return _handle_put_shelf_plan(store_id, event, user, ddb)

        if method == "GET" and route_path == "/search":
            return _handle_search(event, ddb)

        if method == "GET" and route_path == "/review-queue":
            return _handle_review_queue(event, s3, ddb)

        if method == "POST" and route_path == "/corrections":
            err = _require_groups(user, WRITE_CORRECTION_GROUPS, event)
            if err:
                return err
            return _handle_post_correction(event, user, ddb)

        if method == "POST" and route_path == "/uploads":
            err = _require_groups(user, WRITE_CORRECTION_GROUPS, event)
            if err:
                return err
            return _handle_presigned_upload(event, user, s3)

        if method == "POST" and route_path == "/imports/sku-master":
            err = _require_groups(user, ADMIN_GROUPS, event)
            if err:
                return err
            return _handle_import_sku_master(event, ddb)

        if method == "POST" and route_path == "/imports/store-list":
            err = _require_groups(user, ADMIN_GROUPS, event)
            if err:
                return err
            return _handle_import_store_list(event, ddb)

        if method == "POST" and route_path == "/admin/seed":
            err = _require_groups(user, ADMIN_GROUPS, event)
            if err:
                return err
            return _handle_seed_initial_data(event, ddb)

        if method == "GET" and route_path == "/exports/cv-output.csv":
            return _handle_export_csv("cv-output", event, ddb)

        if method == "GET" and route_path == "/exports/capture-log.csv":
            return _handle_export_csv("capture-log", event, ddb)

        if method == "GET" and route_path == "/kpi":
            return _handle_kpi(event, ddb)

        if method == "GET" and route_path == "/reports/series":
            return _handle_reports_series(event, ddb)

        if method == "GET" and route_path == "/reports/trends":
            return _handle_reports_trends(event, ddb)

        if method == "GET" and route_path == "/shelf-events":
            return _handle_shelf_events(event, ddb)

        if method == "GET" and route_path == "/settings":
            return _handle_get_settings(event, user, ddb)

        if method == "PUT" and route_path == "/settings":
            return _handle_put_settings(event, user, ddb)

        return _json_response(404, {"error": "ROUTE_NOT_FOUND", "method": method, "path": route_path}, event)

    except json.JSONDecodeError:
        return _json_response(400, {"error": "INVALID_JSON"}, event)
    except Exception as exc:  # noqa: BLE001
        return _json_response(500, {"error": "INTERNAL_ERROR", "detail": str(exc)}, event)
