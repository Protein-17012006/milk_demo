"""Shelf metrics for the Dashboard: 5-minute checks, opening hours, shelf state and events, hour and day rollups.

Spec: docs/superpowers/specs/2026-11-24-dashboard-shelf-metrics-design.md, and 2026-11-24-reliability-design.md 1.1c
(checks without the display are not measured, gaps). Nothing here touches AWS.
A bucket is a 5-minute slot in ICT (UTC+7), named by its first minute: YYYYMMDD-HHMM.
"""

from __future__ import annotations

import json
import math
import re
import statistics
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
PRODUCTS_MIN_BOXES = 3  # this many sure named boxes anywhere in the frame show the shelf is in view
PRODUCTS_MIN_CONF = 0.8  # a box this sure counts toward PRODUCTS_MIN_BOXES
ARRANGEMENT_JUMP_PX = 500  # the cans' position moving further than this (pixels of the 2560x1440 frame) is a move
GAP_MINUTES = 30  # two measured checks further apart than this have a gap between them: the shelf was not seen

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


def open_buckets(open_time: str | None, close_time: str | None, first: str, last: str) -> int:
    """How many 5-minute checks fall inside the opening hours, from bucket first to bucket last, both included.
    A store without hours has none."""
    if not open_time or not close_time:
        return 0
    open_min = int(open_time[:2]) * 60 + int(open_time[3:5])
    close_min = int(close_time[:2]) * 60 + int(close_time[3:5])
    first_day, last_day = bucket_time(first).date(), bucket_time(last).date()
    first_min = int(first[9:11]) * 60 + int(first[11:13])
    last_min = int(last[9:11]) * 60 + int(last[11:13])
    total, day = 0, first_day
    while day <= last_day:
        lo = max(open_min, first_min if day == first_day else 0)
        hi = min(close_min - 1, last_min if day == last_day else 24 * 60 - 1)
        if hi >= lo:
            total += hi // BUCKET_MINUTES - -(-lo // BUCKET_MINUTES) + 1  # multiples of 5 in [lo, hi]
        day += timedelta(days=1)
    return total


def _rows(item: dict) -> list[dict]:
    raw = item.get("rows_json")
    if not raw:
        return []
    return json.loads(raw) if isinstance(raw, str) else list(raw)


def sees_display(capture: dict) -> bool:
    """Whether the worker saw the display in this capture; captures from before the display check carry no
    display_visible and saw it."""
    return capture.get("display_visible", True) is not False


def sure_boxes(capture: dict) -> list[dict]:
    """The named boxes of a capture that are at least PRODUCTS_MIN_CONF sure."""
    return [b for b in capture_boxes(capture) if b["sku_id"] and b["conf"] >= PRODUCTS_MIN_CONF]


def sees_products(capture: dict) -> bool:
    """Whether the capture holds PRODUCTS_MIN_BOXES sure named boxes, wherever they are in the frame."""
    return len(sure_boxes(capture)) >= PRODUCTS_MIN_BOXES


def sees_shelf(capture: dict) -> bool:
    """Whether the capture sees the shelf: the zone check passes, or the model sees the cans elsewhere."""
    return sees_display(capture) or sees_products(capture)


def _median_point(points: list[tuple[float, float]]) -> list[int]:
    return [round(statistics.median(p[0] for p in points)), round(statistics.median(p[1] for p in points))]


def capture_position(capture: dict) -> list[int] | None:
    """Where the cans are in one capture: the median centre [x, y] of its sure boxes; None when it sees no products."""
    if not sees_products(capture):
        return None
    return _median_point([(b["box"][0] + b["box"][2] / 2, b["box"][1] + b["box"][3] / 2) for b in sure_boxes(capture)])


def products_position(captures: list[dict]) -> list[int] | None:
    """Where the cans are over several captures: the median of their positions; None when none has one."""
    points = [p for p in (capture_position(c) for c in captures) if p is not None]
    return _median_point([(p[0], p[1]) for p in points]) if points else None


def far_apart(a: list[float], b: list[float]) -> bool:
    """Whether two [x, y] points are more than ARRANGEMENT_JUMP_PX apart (exactly that far is not)."""
    return math.hypot(a[0] - b[0], a[1] - b[1]) > ARRANGEMENT_JUMP_PX


def _frame_boxes(capture: dict) -> dict[str, list]:
    """Per product, its boxes ([x, y, width, height]) in one capture's frame, from the capture's rows."""
    boxes: dict[str, list] = {}
    for row in _rows(capture):
        if row.get("sku_id") and row.get("bounding_box"):
            boxes.setdefault(row["sku_id"], []).extend(row["bounding_box"])
    return boxes


def build_check(bucket: str, captures: list[dict]) -> dict[str, Any]:
    """One check of a store, from the captures that see the shelf: per SKU, the lower median of each camera's
    captures (a SKU missing from a capture counts 0 there), summed over cameras. Unrecognized rows are left out.
    confident_skus: SKUs with one box at CONFIDENT or more; confident_by_camera has them per camera.
    positions: per camera, where the cans stood (products_position of its captures that see the shelf).
    captures_zone: captures that pass the zone check alone.

    A capture sees the shelf when the zone check passes or sure boxes show the cans elsewhere (sees_shelf).
    The check is measurable when at least half of its captures see the shelf; otherwise it says why. image_key
    and source_bucket are the frame of the first capture (by capture_id) that sees the shelf and has one, for
    event photos; frame_boxes are each product's boxes in that very frame ({} without a frame), so a photo of an
    event can show where its product stood. They change no count."""
    seeing = [item for item in captures if sees_shelf(item)]
    per_camera: dict[str, list[dict[str, int]]] = defaultdict(list)
    confident: dict[str, set[str]] = defaultdict(set)
    seen_by_camera: dict[str, list[dict]] = defaultdict(list)
    for item in seeing:
        units: dict[str, int] = defaultdict(int)
        for row in _rows(item):
            if row.get("sku_id"):
                units[row["sku_id"]] += int(row.get("unit_count", 0))
        camera = str(item.get("camera_id", ""))
        per_camera[camera].append(units)
        seen_by_camera[camera].append(item)
        confident.setdefault(camera, set())  # a camera that sees the shelf is listed, even with no sure product
        for box in capture_boxes(item):
            name = resolve_sku_alias(box["sku_id"])[0] if box["sku_id"] else None
            if name and box["conf"] >= CONFIDENT:
                confident[camera].add(name)
    counts: dict[str, int] = defaultdict(int)
    for caps in per_camera.values():
        for sku in {s for c in caps for s in c}:
            counts[sku] += lower_median([c.get(sku, 0) for c in caps])
    framed = sorted((item for item in seeing if item.get("image_key")), key=lambda item: str(item["capture_id"]))
    positions = {cam: pos for cam, caps in seen_by_camera.items() if (pos := products_position(caps)) is not None}
    measurable = bool(seeing) and 2 * len(seeing) >= len(captures)
    check = {
        "bucket": bucket,
        "counts": dict(counts),
        "captures": len(captures),
        "captures_visible": len(seeing),
        "measurable": measurable,
        "cameras": sorted({str(item.get("camera_id", "")) for item in captures}),
        "confident_skus": sorted(set().union(*confident.values())),
        "confident_by_camera": {cam: sorted(names) for cam, names in sorted(confident.items())},
        "positions": positions,
        "captures_zone": sum(1 for item in captures if sees_display(item)),
        "image_key": framed[0]["image_key"] if framed else None,
        "source_bucket": (framed[0].get("source_bucket") or None) if framed else None,
        "frame_boxes": _frame_boxes(framed[0]) if framed else {},
    }
    if not measurable:
        check["unmeasured_reason"] = "display_not_visible"
    return check


def expected_at(check: dict, plan: list[str], since: dict[str, str], joined: dict[str, str]) -> list[str]:
    """The plan's SKUs that count at this check, in name order.

    A SKU starts at the first measurable check that counted it with a sure box, or at the check where it joined the
    plan (joined: SKU -> bucket), whichever comes first. Before that the system knew nothing of it, so its empty
    space is not out of stock. since (SKU -> the bucket it started at) is read and updated."""
    counts = check.get("counts") or {}
    sure = set(check.get("confident_skus") or []) if check.get("measurable", True) else set()
    bucket = check["bucket"]
    out = []
    for sku in sorted(plan):
        if sku not in since:
            counted = sku in sure and int(counts.get(sku, 0)) > 0
            if not counted and not (sku in joined and bucket >= joined[sku]):
                continue
            since[sku] = bucket
        if bucket >= since[sku]:
            out.append(sku)
    return out


def gap_between(last_measured: str | None, bucket: str) -> tuple[str, str] | None:
    """(last_measured, bucket) when these two measured checks are more than GAP_MINUTES apart, else None."""
    if last_measured is None or bucket_time(bucket) - bucket_time(last_measured) <= timedelta(minutes=GAP_MINUTES):
        return None
    return last_measured, bucket


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


_NEW_STATE = {
    "L": None,
    "status": None,
    "since": None,
    "prev": None,
    "prev_bucket": None,
    "oos_checks": 0,
    "prev_gap": None,
}


def step_state(
    state: dict | None, units: int, bucket: str, gap: tuple[str, str] | None = None
) -> tuple[dict, dict | None]:
    """Apply one measured check of one SKU to its shelf state.

    A change needs two checks in a row: x1 is the previous check, x2 this one. A check makes at most one event,
    tried in the order OOS, LOW_STOCK, DEPLETED, RESTOCKED, and the event is timed at x1. With no event and
    x1 == x2, the level follows x2 (shoppers taking single units). oos_checks counts checks spent out of stock,
    so a RESTOCKED that ends one carries its minutes.

    gap is the gap right before this check (gap_between), if any; the state keeps it as prev_gap. An event timed at
    a check right after a gap carries after_gap, gap_from and gap_to: the change happened somewhere in that gap.
    A state read back from DynamoDB lacks the fields that were None."""
    s = {**_NEW_STATE, **(state or {})}
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
            if s["prev_gap"]:
                gap_from, gap_to = s["prev_gap"]
                event.update(after_gap=True, gap_from=gap_from, gap_to=gap_to)
    if new_level is not None and status_of(new_level) != s["status"]:
        s["status"], s["since"] = status_of(new_level), at
        s["oos_checks"] = 2 if s["status"] == "OOS" else 0
    elif event is None and s["status"] == "OOS":
        s["oos_checks"] += 1
    s["L"], s["prev"], s["prev_bucket"], s["prev_gap"] = new_level, x2, bucket, list(gap) if gap else None
    return s, event


def in_view(state: dict | None) -> bool:
    """False only for a product marked not in view (its place is outside the frame since a move)."""
    return (state or {}).get("in_view") is not False


def view_of(state: dict | None) -> dict | None:
    """When a product is not in view: since when, and the level and check it was last seen at. Else None."""
    if in_view(state):
        return None
    s = state or {}
    return {
        "since": s.get("not_in_view_since"),
        "last_units": s.get("last_seen_units"),
        "last_at": s.get("last_seen_at"),
    }


def step_arrangements(arrangements: dict[str, dict], check: dict) -> list[str]:
    """Follow where each camera's cans stand. A jump of more than ARRANGEMENT_JUMP_PX from the last position is a new
    arrangement (since = this check); smaller moves (a person in front, a slow drift) only update the position.
    arrangements is changed in place; returns the cameras whose arrangement changed, in name order."""
    changed = []
    for camera, pos in sorted((check.get("positions") or {}).items()):
        current = arrangements.get(camera)
        if current is None:
            arrangements[camera] = {"position": pos, "since": check["bucket"]}
        elif far_apart(current["position"], pos):
            arrangements[camera] = {"position": pos, "since": check["bucket"]}
            changed.append(camera)
        else:
            current["position"] = pos
    return changed


def _seen_by(check: dict, camera: str, sku: str) -> bool:
    return (
        sku in (check.get("confident_by_camera") or {}).get(camera, [])
        and int((check.get("counts") or {}).get(sku, 0)) > 0
    )


def move_skus(skus_state: dict[str, dict], cameras: list[str], check: dict) -> None:
    """A move on these cameras: the level of their products no longer means anything, so their state starts again.
    A product seen surely in this check starts fresh and in view; one already not in view keeps what was last seen;
    any other is marked not in view, with the level (or the last check's units) it had. skus_state is changed in place."""
    for sku, state in list(skus_state.items()):
        if state.get("camera") is not None and state["camera"] not in cameras:
            continue
        seen_on = next((c for c in sorted(cameras) if _seen_by(check, c, sku)), None)
        if seen_on is not None:
            skus_state[sku] = {"in_view": True, "camera": seen_on}
        elif not in_view(state):
            skus_state[sku] = {
                "in_view": False,
                "not_in_view_since": state.get("not_in_view_since"),
                "last_seen_units": state.get("last_seen_units"),
                "last_seen_at": state.get("last_seen_at"),
                "camera": state.get("camera"),
            }
        else:
            level = state.get("L")
            skus_state[sku] = {
                "in_view": False,
                "not_in_view_since": check["bucket"],
                "last_seen_units": level if level is not None else state.get("prev"),
                "last_seen_at": state.get("prev_bucket"),
                "camera": state.get("camera"),
            }


def see_skus(skus_state: dict[str, dict], check: dict, expected: list[str]) -> None:
    """Name the camera that counted each expected product surely (first camera in name order). A product that was not
    in view comes back fresh and in view; one with a state keeps it and gets its camera; a new one gets {"camera"}."""
    claimed: set[str] = set()
    for camera in sorted(check.get("confident_by_camera") or {}):
        for sku in expected:
            if sku in claimed or not _seen_by(check, camera, sku):
                continue
            claimed.add(sku)
            state = skus_state.get(sku)
            if state is None:
                skus_state[sku] = {"camera": camera}
            elif not in_view(state):
                skus_state[sku] = {"in_view": True, "camera": camera}
            else:
                state["camera"] = camera


SKU_FIELDS = ("checks", "available", "units_sum", "oos_started", "restock_units", "restock_events", "unseen_checks")


def _blank() -> dict[str, int]:
    return dict.fromkeys(SKU_FIELDS, 0)


def _result(
    checks: int, unmeasured: int, max_total: int, confident: set[str], skus: dict[str, dict[str, int]]
) -> dict[str, Any]:
    return {
        "checks": checks,
        "unmeasured_checks": unmeasured,
        "max_total": max_total,
        "confident_skus": sorted(confident),
        "skus": {sku: dict(row) for sku, row in skus.items()},
    }


def rollup(checks: list[dict], events: list[dict]) -> dict[str, Any]:
    """Sum of one hour: counted checks (open, measurable, with expected SKUs) per SKU (a SKU in the check's
    not_in_view only adds unseen_checks, and is left out of the check's total), the store's largest total in one check, SKUs seen confidently in any check, and the hour's OOS and RESTOCKED events. An expected SKU missing
    from a check's counts is a check without stock. unmeasured_checks: open checks with expected SKUs that could not
    be measured; checks stored before measurable existed were measured."""
    skus: dict[str, dict[str, int]] = defaultdict(_blank)
    counted, unmeasured, max_total, confident = 0, 0, 0, set()
    for check in checks:
        confident.update(check.get("confident_skus") or [])
        expected = check.get("expected") or []
        if not check.get("open") or not expected:
            continue
        if not check.get("measurable", True):
            unmeasured += 1
            continue
        counted += 1
        total = 0
        not_in_view = set(check.get("not_in_view") or [])
        for sku in expected:
            if sku in not_in_view:
                skus[sku]["unseen_checks"] += 1
                continue
            units = int((check.get("counts") or {}).get(sku, 0))
            row = skus[sku]
            row["checks"] += 1
            row["available"] += 1 if units > 0 else 0
            row["units_sum"] += units
            total += units
        max_total = max(max_total, total)
    for event in events:
        row = skus[event["sku_id"]]
        if event["type"] == "OOS":
            row["oos_started"] += 1
        elif event["type"] == "RESTOCKED":
            row["restock_units"] += int(event["delta"])
            row["restock_events"] += 1
    return _result(counted, unmeasured, max_total, confident, skus)


def merge(rollups: list[dict]) -> dict[str, Any]:
    """Hours into a day (or days into a period): counts add, max_total is the largest, confident SKUs unite."""
    skus: dict[str, dict[str, int]] = defaultdict(_blank)
    counted, unmeasured, max_total, confident = 0, 0, 0, set()
    for r in rollups:
        counted += int(r.get("checks", 0))
        unmeasured += int(r.get("unmeasured_checks", 0))
        max_total = max(max_total, int(r.get("max_total", 0)))
        confident.update(r.get("confident_skus") or [])
        for sku, row in (r.get("skus") or {}).items():
            for field in SKU_FIELDS:
                skus[sku][field] += int(row.get(field, 0))
    return _result(counted, unmeasured, max_total, confident, skus)


def totals(rollups: list[dict], skus: set[str] | None = None) -> dict[str, Any]:
    """Numbers of a period, optionally for some SKUs only (a category). osa and avg_total_units are None when
    nothing was counted. store_checks and unmeasured_checks are the store's checks, whatever the SKUs."""
    merged = merge(rollups)
    rows = [row for sku, row in merged["skus"].items() if skus is None or sku in skus]
    sums = {field: sum(row[field] for row in rows) for field in SKU_FIELDS}
    store_checks = merged["checks"]
    return {
        "checks": sums["checks"],
        "available": sums["available"],
        "osa": sums["available"] / sums["checks"] if sums["checks"] else None,
        "restock_units": sums["restock_units"],
        "restock_events": sums["restock_events"],
        "oos_started": sums["oos_started"],
        "store_checks": store_checks,
        "unmeasured_checks": merged["unmeasured_checks"],
        "avg_total_units": sums["units_sum"] / store_checks if store_checks else None,
    }


def change_pct(current: float | None, previous: float | None) -> float | None:
    """Percent change against the previous period, rounded to 1 decimal; None without a previous value."""
    if current is None or not previous:
        return None
    return round((current - previous) / previous * 100, 1)
