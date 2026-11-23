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


def status_of(level: int) -> str:
    """OOS at 0, LOW at 1..LOW_MAX, IN_STOCK above."""
    if level <= 0:
        return "OOS"
    return "LOW" if level <= LOW_MAX else "IN_STOCK"


def _event(kind: str, at: str, before: int, after: int, duration_min: int | None = None) -> dict[str, Any]:
    return {
        "type": kind,
        "at": at,
        "delta": after - before,
        "level_before": before,
        "level_after": after,
        "duration_min": duration_min,
    }


def step_state(state: dict | None, units: int, bucket: str) -> tuple[dict, dict | None]:
    """Apply one counted check of one SKU to its shelf state.

    A change needs two checks in a row: x1 is the previous check, x2 this one. A check makes at most one event,
    tried in the order OOS, LOW_STOCK, DEPLETED, RESTOCKED, and the event is timed at x1. With no event and
    x1 == x2, the level follows x2 (shoppers taking single units). oos_checks counts checks spent out of stock,
    so a RESTOCKED that ends one carries its minutes."""
    s = (
        dict(state)
        if state
        else {"L": None, "status": None, "since": None, "prev": None, "prev_bucket": None, "oos_checks": 0}
    )
    x1, x2, at, level = s["prev"], int(units), s["prev_bucket"], s["L"]
    event = None
    new_level = level
    if x1 is not None and level is None:
        if x1 == x2:
            new_level = x2  # first two equal checks set the level, without an event
    elif x1 is not None:
        if x1 == 0 and x2 == 0 and level > 0:
            event = _event("OOS", at, level, 0)
        elif 1 <= x1 <= LOW_MAX and 1 <= x2 <= LOW_MAX and level > LOW_MAX:
            event = _event("LOW_STOCK", at, level, max(x1, x2))
        elif x1 <= level - DEPLETED_DROP and x2 <= level - DEPLETED_DROP and min(x1, x2) > LOW_MAX:
            event = _event("DEPLETED", at, level, max(x1, x2))
        elif x1 >= level + RESTOCK_RISE and x2 >= level + RESTOCK_RISE:
            ended_oos = s["status"] == "OOS"
            event = _event(
                "RESTOCKED", at, level, min(x1, x2), BUCKET_MINUTES * (s["oos_checks"] - 1) if ended_oos else None
            )
        elif x1 == x2:
            new_level = x2
        if event is not None:
            new_level = event["level_after"]
    if new_level is not None and status_of(new_level) != s["status"]:
        s["status"], s["since"] = status_of(new_level), at
        s["oos_checks"] = 2 if s["status"] == "OOS" else 0
    elif event is None and s["status"] == "OOS":
        s["oos_checks"] += 1
    s["L"], s["prev"], s["prev_bucket"] = new_level, x2, bucket
    return s, event
