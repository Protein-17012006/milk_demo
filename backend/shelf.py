"""Shelf metrics for the Dashboard: 5-minute checks, opening hours, shelf state and events, hour and day rollups.

Spec: docs/superpowers/specs/2026-11-24-dashboard-shelf-metrics-design.md. Nothing here touches AWS.
A bucket is a 5-minute slot in ICT (UTC+7), named by its first minute: YYYYMMDD-HHMM.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from common import lower_median, resolve_sku_alias
from model_health import capture_boxes

ICT = timezone(timedelta(hours=7))
BUCKET_MINUTES = 5
CONFIDENT = 0.70  # a box this sure makes its SKU "seen" for the suggested shelf plan
LOW_MAX = 2  # LOW STOCK: 1..2 units left
DEPLETED_DROP = 3  # DEPLETED: fell by at least 3 and still 3 or more
RESTOCK_RISE = 2  # RESTOCKED: rose by at least 2
SETTLE_MINUTES = 2  # a bucket is worked on once it closed this long ago, so late captures make it
MAX_BUCKETS_PER_TICK = 36
RECOMPUTE_DAYS = 15
SUGGEST_DAYS = 7
CHECK_TTL_DAYS = 15
ROLLUP_TTL_DAYS = 90

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def bucket_of(capture_ts: str) -> str:
    """The bucket an ISO timestamp falls in, in ICT."""
    t = datetime.fromisoformat(capture_ts).astimezone(ICT)
    return t.replace(minute=t.minute - t.minute % BUCKET_MINUTES, second=0, microsecond=0).strftime("%Y%m%d-%H%M")


def bucket_time(bucket: str) -> datetime:
    """Start of a bucket, ICT-aware."""
    return datetime.strptime(bucket, "%Y%m%d-%H%M").replace(tzinfo=ICT)


def add_buckets(bucket: str, n: int) -> str:
    return (bucket_time(bucket) + timedelta(minutes=BUCKET_MINUTES * n)).strftime("%Y%m%d-%H%M")


def valid_hours(open_time: str, close_time: str) -> bool:
    """Opening hours as "HH:MM" (ICT), one range for every day, closing after opening."""
    return bool(_HHMM.match(open_time or "")) and bool(_HHMM.match(close_time or "")) and close_time > open_time


def is_open(bucket: str, open_time: str | None, close_time: str | None) -> bool:
    """True when the bucket starts inside [open, close); a store without hours is never open."""
    if not open_time or not close_time:
        return False
    return open_time <= f"{bucket[9:11]}:{bucket[11:13]}" < close_time


def _rows(item: dict) -> list[dict]:
    raw = item.get("rows_json")
    if not raw:
        return []
    return json.loads(raw) if isinstance(raw, str) else list(raw)


def build_check(bucket: str, captures: list[dict]) -> dict[str, Any]:
    """One check of a store: per SKU, the lower median of each camera's captures (a SKU missing from a capture
    counts 0 there), summed over cameras. Unrecognized rows are left out. confident_skus: SKUs with one box at
    CONFIDENT or more."""
    per_camera: dict[str, list[dict[str, int]]] = defaultdict(list)
    confident: set[str] = set()
    for item in captures:
        units: dict[str, int] = defaultdict(int)
        for row in _rows(item):
            if row.get("sku_id"):
                units[row["sku_id"]] += int(row.get("unit_count", 0))
        per_camera[str(item.get("camera_id", ""))].append(units)
        for box in capture_boxes(item):
            name = resolve_sku_alias(box["sku_id"])[0] if box["sku_id"] else None
            if name and box["conf"] >= CONFIDENT:
                confident.add(name)
    counts: dict[str, int] = defaultdict(int)
    for caps in per_camera.values():
        for sku in {s for c in caps for s in c}:
            counts[sku] += lower_median([c.get(sku, 0) for c in caps])
    return {
        "bucket": bucket,
        "counts": dict(counts),
        "captures": len(captures),
        "cameras": sorted(per_camera),
        "confident_skus": sorted(confident),
    }
