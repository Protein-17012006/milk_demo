"""Replay the shelf checks of real captures with the old and the new shelf rules. Read-only: it only reads the
store list, the latest-stock rows and the captures from DynamoDB, and writes nothing.

    python scripts/shelf_replay.py --profile default --region ap-southeast-1 --store DEMO-S01 \
        --from 2026-11-21 --to 2026-11-28

Both passes run the same captures through shelf.build_check and ingest.handler._apply_check, in bucket order, with
the store's saved shelf plan. The old rule is emulated in process: shelf.sees_shelf is replaced by shelf.sees_display
and shelf.ARRANGEMENT_JUMP_PX by infinity for the whole old pass, then both are put back. An arrangement change is
a check _apply_check marked arrangement_changed (open and measured), as the tick records it.
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

STACK = "milk-backend-development"
NIGHT_FROM, NIGHT_TO = "2100", "0630"  # a new event between these hours of the day is a defect


def load_handler(region: str):
    """Load backend/ingest/handler.py the way the tests do; its table names come from the environment."""
    env = {"AWS_REGION": region, "AWS_DEFAULT_REGION": region}
    for var, table in (
        ("CAPTURES_TABLE", "captures"),
        ("LATEST_STOCK_TABLE", "latest-stock"),
        ("STORE_LIST_TABLE", "store-list"),
        ("SHELF_TABLE", "shelf"),
        ("SHELF_EVENTS_TABLE", "shelf-events"),
        ("REVIEW_QUEUE_TABLE", "review-queue"),
        ("AUDITS_TABLE", "audits"),
        ("CORRECTIONS_TABLE", "corrections"),
        ("MODEL_HEALTH_TABLE", "model-health"),
        ("MODEL_VERSIONS_TABLE", "model-versions"),
    ):
        env[var] = f"{STACK}-{table}"
    for key, value in env.items():
        os.environ.setdefault(key, value)
    spec = importlib.util.spec_from_file_location("replay_ingest_handler", str(ROOT / "backend/ingest/handler.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def is_night(bucket: str) -> bool:
    hhmm = bucket[9:13]
    return hhmm >= NIGHT_FROM or hhmm < NIGHT_TO


def fetch(handler, ddb, store_id: str, first_day: str, last_day: str):
    """The store record, its cameras and their captures from first_day through last_day (YYYYMMDD), by bucket."""
    store = handler.from_dynamodb(ddb.Table(handler.STORE_LIST_TABLE).get_item(Key={"store_id": store_id}).get("Item"))
    cameras = handler._store_cameras(ddb, store_id)
    by_bucket = handler._captures_by_bucket(ddb, cameras, f"{first_day}-0000", f"{last_day}-2355")
    return store or {"store_id": store_id}, cameras, by_bucket


def run_pass(handler, shelf, store: dict, by_bucket: dict, plan_of, rule: str) -> dict:
    """Build every check and apply it in bucket order. rule is "new" (the code as it is) or "old"."""
    saved = shelf.sees_shelf, shelf.ARRANGEMENT_JUMP_PX
    if rule == "old":  # both patches stay on for the whole pass: checks are built and applied under the old rule
        shelf.sees_shelf, shelf.ARRANGEMENT_JUMP_PX = shelf.sees_display, float("inf")
    try:
        checks = {b: shelf.build_check(b, caps) for b, caps in sorted(by_bucket.items()) if caps}
        plan = plan_of(checks)
        skus_state, since, arrangements, last_measured = {}, {}, {}, None
        events, moves, views = [], [], []
        for bucket in sorted(checks):
            check = checks[bucket]
            before = {cam: list(a["position"]) for cam, a in arrangements.items()}
            got, last_measured = handler._apply_check(
                check, store, plan, skus_state, last_measured, since, arrangements
            )
            events += [{**e, "bucket": bucket} for e in got]
            if check.get("arrangement_changed"):  # the cameras _apply_check gave a new arrangement at this check
                for cam, now in sorted(arrangements.items()):
                    if cam in before and now["since"] == bucket:
                        a, pos = before[cam], now["position"]
                        moves.append((bucket, cam, math.hypot(a[0] - pos[0], a[1] - pos[1]), a, pos))
            if "not_in_view" in check:  # only an open, measured check says who is in view
                views.append((bucket, set(check["not_in_view"])))
    finally:
        shelf.sees_shelf, shelf.ARRANGEMENT_JUMP_PX = saved
    return {"checks": checks, "events": events, "moves": moves, "views": views, "plan": plan}


def hourly_totals(shelf, run: dict, day: str) -> dict:
    by_hour_checks, by_hour_events = defaultdict(list), defaultdict(list)
    for bucket, check in run["checks"].items():
        if bucket.startswith(day):
            by_hour_checks[bucket[:11]].append(check)
    for event in run["events"]:
        if event["bucket"].startswith(day):
            by_hour_events[event["at"][:11]].append(event)
    hours = sorted(set(by_hour_checks) | set(by_hour_events))
    return shelf.totals([shelf.rollup(by_hour_checks[h], by_hour_events[h]) for h in hours])


def intervals(run: dict) -> list[tuple[str, str, str | None]]:
    """(sku, first check not in view, first check back in view or None) over the whole run."""
    out, open_at = [], {}
    for bucket, missing in run["views"]:
        for sku in sorted(missing - open_at.keys()):
            open_at[sku] = bucket
        for sku in sorted(open_at.keys() - missing):
            out.append((sku, open_at.pop(sku), bucket))
    out += [(sku, start, None) for sku, start in sorted(open_at.items())]
    return sorted(out, key=lambda x: (x[1], x[0]))


def fmt_osa(t: dict) -> str:
    return "n/a" if t["osa"] is None else f"{t['osa'] * 100:.1f}% ({t['available']}/{t['checks']})"


def describe(run: dict, event: dict) -> str:
    """One event with the counts of its product in the check before and in the check that made it."""
    buckets = sorted(run["checks"])
    i = buckets.index(event["bucket"])
    sku = event["sku_id"]
    prev = run["checks"][buckets[i - 1]] if i else {}
    cur = run["checks"][event["bucket"]]
    return (
        f"{event['bucket']} {sku[:24]} {event['type']} level {event['level_before']}->{event['level_after']}; "
        f"counts at {buckets[i - 1] if i else '-'}: {(prev.get('counts') or {}).get(sku, 0)}, "
        f"at {event['bucket']}: {(cur.get('counts') or {}).get(sku, 0)}"
    )


def count_events(run: dict, day: str, kind: str) -> int:
    return Counter(e["type"] for e in run["events"] if e["bucket"].startswith(day))[kind]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--profile", default="default")
    ap.add_argument("--region", default="ap-southeast-1")
    ap.add_argument("--store", required=True)
    ap.add_argument("--from", dest="first", required=True, help="first day, YYYY-MM-DD")
    ap.add_argument("--to", dest="last", required=True, help="last day, YYYY-MM-DD")
    args = ap.parse_args()

    import boto3
    import shelf

    handler = load_handler(args.region)
    ddb = boto3.Session(profile_name=args.profile, region_name=args.region).resource("dynamodb")
    first_day, last_day = args.first.replace("-", ""), args.last.replace("-", "")
    store, cameras, by_bucket = fetch(handler, ddb, args.store, first_day, last_day)
    print(f"store {args.store}  cameras {cameras}  saved plan {sorted(store.get('expected_skus') or [])}")
    print(f"open {store.get('open_time')}-{store.get('close_time')}  plan saved {store.get('shelf_plan_updated_at')}")

    def plan_of(checks: dict) -> list[str]:
        if store.get("expected_skus"):
            return sorted(store["expected_skus"])
        return sorted({s for c in checks.values() for s in c.get("confident_skus") or []})  # the suggestion

    old = run_pass(handler, shelf, store, by_bucket, plan_of, "old")
    new = run_pass(handler, shelf, store, by_bucket, plan_of, "new")

    days = sorted({b[:8] for b in by_bucket})
    start = datetime.strptime(first_day, "%Y%m%d")
    span = (datetime.strptime(last_day, "%Y%m%d") - start).days + 1
    counts = ", ".join(f"{x} ({sum(len(v) for b, v in by_bucket.items() if b.startswith(x))})" for x in days)
    print("days with captures:", counts)
    missing = [x for i in range(span) if (x := (start + timedelta(days=i)).strftime("%Y%m%d")) not in days]
    print("days without captures:", missing or "none")
    print("plan used:", new["plan"])
    gone = intervals(new)
    for day in days:
        measured = [sum(1 for b, c in r["checks"].items() if b.startswith(day) and c["measurable"]) for r in (old, new)]
        print(f"\n=== {day} ===")
        print(
            f"checks {sum(1 for b in new['checks'] if b.startswith(day))}  measured old {measured[0]} -> new {measured[1]}"
        )
        for bucket, cam, dist, a, b in new["moves"]:
            if bucket.startswith(day):
                print(f"  arrangement change at {bucket} camera {cam}: {dist:.0f} px  {a} -> {b}")
        n_old = sum(1 for c in old["checks"].values() if c.get("arrangement_changed") and c["bucket"].startswith(day))
        print(f"  arrangement changes under the old rule: {n_old}")
        for sku, begin, back in gone:
            if begin.startswith(day):
                print(f"  not in view: {sku} from {begin} until {back or 'the end of the data'}")
        types = sorted({e["type"] for e in old["events"] + new["events"] if e["bucket"].startswith(day)})
        for t in types:
            print(f"  events {t}: old {count_events(old, day, t)} -> new {count_events(new, day, t)}")
        if not types:
            print("  events: none (old or new)")
        old_keys = {e["event_key"]: e for e in old["events"]}
        new_keys = {e["event_key"]: e for e in new["events"]}
        for tag, left, right, run in (("only new", new_keys, old_keys, new), ("only old", old_keys, new_keys, old)):
            for key in sorted(left.keys() - right.keys()):
                if left[key]["bucket"].startswith(day):
                    print(
                        f"  event {tag}: {describe(run, left[key])}"
                        + ("  [NIGHT]" if is_night(left[key]["bucket"]) else "")
                    )
        for r, name in ((old, "old"), (new, "new")):
            at_1215 = [e["event_key"] for e in r["events"] if e["bucket"] == f"{day}-1215"]
            if at_1215:
                print(f"  events at 12:15 {name}: {at_1215}")
        print(f"  OSA old {fmt_osa(hourly_totals(shelf, old, day))} -> new {fmt_osa(hourly_totals(shelf, new, day))}")
    nights = [sum(1 for e in r["events"] if is_night(e["bucket"])) for r in (old, new)]
    print(f"\nevents between 21:00 and 06:30: old {nights[0]}, new {nights[1]}")
    print("arrangement changes (new rule):", [(b, c, round(x)) for b, c, x, _, _ in new["moves"]] or "none")
    print("arrangement changes (old rule):", sum(1 for c in old["checks"].values() if c.get("arrangement_changed")))


if __name__ == "__main__":
    main()
