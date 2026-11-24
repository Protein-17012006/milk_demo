"""Replay the worker's display check over a real capture series and say whether it gets the known
"display packed away" window right.

Reads the captures of one camera from DynamoDB and each frame from S3 (into memory only, nothing is written to
disk), takes one capture with a frame per --every-min slot, and runs them in time order through one DisplayCheck
exactly as the worker does: references are learnt from the stored detections_json, `now` is the capture's time.
The stored frame is the blurred JPEG at full resolution, not the frame the worker checked: the worker runs the check
on the frame before people are blurred. It has the same size, so its boxes need no scaling.

Times are ICT (+07:00) without an offset. A window is START/END, inclusive of START and exclusive of END.
Frames inside --hidden must come out "NOT in view", every other frame "in view" unless it is inside --skip
(transition windows: printed, not judged). Exit 0 when nothing judged is wrong, 1 otherwise, 2 on a usage or AWS error.

usage: python scripts/check_display_series.py --camera CAM-S01-A --from 2026-11-23T12:40 --to 2026-11-24T10:00 \
           --every-min 10 --zone 0.336,0.083,0.242,0.361 --hidden 2026-11-23T20:50/2026-11-23T22:00
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

from milk.config import _roi  # noqa: E402 - the parser of MILK_DISPLAY_ZONE
from milk.cvoutput import Detection  # noqa: E402
from milk.display import DisplayCheck  # noqa: E402

ICT = timezone(timedelta(hours=7))
EXPECT_TEXT = {"hidden": "expect not in view", "visible": "expect in view", "skip": "skip"}


def parse_local(text: str) -> datetime:
    """An ICT local time such as 2026-11-23T12:40 (an offset in the text is honoured)."""
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=ICT)


def parse_window(text: str) -> tuple[datetime, datetime]:
    start_text, sep, end_text = text.partition("/")
    if not sep:
        raise ValueError(f"window needs START/END, got {text!r}")
    start, end = parse_local(start_text), parse_local(end_text)
    if end <= start:
        raise ValueError(f"window end must be after its start, got {text!r}")
    return start, end


def _inside(when: datetime, windows: list[tuple[datetime, datetime]]) -> bool:
    return any(start <= when < end for start, end in windows)


def expectation(when: datetime, hidden: list, skip: list) -> str:
    """ "skip", "hidden" or "visible" for a frame taken at `when`; a skip window wins over a hidden one."""
    if _inside(when, skip):
        return "skip"
    return "hidden" if _inside(when, hidden) else "visible"


def pick_slots(items: list[dict], start: datetime, end: datetime, every_min: int) -> list[dict]:
    """The first capture (by capture_id) with a frame in each `every_min` slot of [start, end), in time order."""
    picked: dict[int, dict] = {}
    for it in sorted(items, key=lambda i: i["capture_id"]):
        if not it.get("image_key"):
            continue
        when = datetime.fromisoformat(it["capture_timestamp"])
        if not start <= when < end:
            continue
        slot = int((when - start).total_seconds() // (every_min * 60))
        picked.setdefault(slot, it)
    return [picked[slot] for slot in sorted(picked)]


def verdict(expect: str, visible: bool) -> str:
    if expect == "skip":
        return ""
    return "OK" if visible == (expect == "visible") else "WRONG"


def exit_code(verdicts: list[str]) -> int:
    return 1 if "WRONG" in verdicts else 0


def detections_from_json(value) -> list[Detection]:
    """Detections as the worker passed them to DisplayCheck, from the stored detections_json (str or list)."""
    if not value:
        return []
    raw = json.loads(value) if isinstance(value, str) else value
    return [
        Detection(
            sku_id=d.get("sku_id"),
            sku_name=None,
            confidence=float(d.get("conf", 0.0)),
            box=tuple(int(v) for v in d["box"]),
        )
        for d in raw
    ]


def format_line(when: datetime, capture_id: str, score: float | None, visible: bool, expect: str) -> str:
    shown = "-" if score is None else f"{score:.3f}"
    state = "in view" if visible else "NOT in view"
    line = f"{when.astimezone(ICT):%Y-%m-%d %H:%M}  {capture_id:<28} {shown:>6}  {state:<11}  "
    return f"{line}{EXPECT_TEXT[expect]:<18}  {verdict(expect, visible)}".rstrip()


def fetch_items(table, camera: str, start: datetime, end: datetime) -> list[dict]:
    from boto3.dynamodb.conditions import Attr, Key

    kwargs = {
        "KeyConditionExpression": Key("camera_id").eq(camera),
        "FilterExpression": Attr("capture_timestamp").between(start.isoformat(), end.isoformat()),
    }
    items: list[dict] = []
    while True:
        page = table.query(**kwargs)
        items += page["Items"]
        if "LastEvaluatedKey" not in page:
            return items
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--camera", required=True)
    ap.add_argument("--from", dest="start", required=True, help="ICT, e.g. 2026-11-23T12:40")
    ap.add_argument("--to", dest="end", required=True)
    ap.add_argument("--every-min", type=int, default=10)
    ap.add_argument("--zone", required=True, help="x,y,w,h as fractions, like MILK_DISPLAY_ZONE")
    ap.add_argument("--min", dest="min_score", type=float, default=0.6, help="like MILK_DISPLAY_MIN")
    ap.add_argument("--hidden", action="append", default=[], metavar="START/END")
    ap.add_argument("--skip", action="append", default=[], metavar="START/END")
    ap.add_argument("--table", default="milk-backend-development-captures")
    ap.add_argument("--profile", default="default")
    ap.add_argument("--region", default="ap-southeast-1")
    args = ap.parse_args(argv)

    try:
        start, end = parse_local(args.start), parse_local(args.end)
        zone = _roi(args.zone, "--zone")
        hidden = [parse_window(w) for w in args.hidden]
        skip = [parse_window(w) for w in args.skip]
        if zone is None:
            raise ValueError("--zone is empty")
        if end <= start or args.every_min < 1:
            raise ValueError("--to must be after --from and --every-min at least 1")
    except ValueError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return 2

    import cv2
    import numpy as np

    check = DisplayCheck(zone, min_score=args.min_score)  # no refs file: learn from this series only
    verdicts: list[str] = []
    try:
        import boto3

        session = boto3.Session(profile_name=args.profile, region_name=args.region)
        table = session.resource("dynamodb").Table(args.table)
        s3 = session.client("s3")
        picked = pick_slots(fetch_items(table, args.camera, start, end), start, end, args.every_min)
        for it in picked:
            body = s3.get_object(Bucket=it["source_bucket"], Key=it["image_key"])["Body"].read()
            image = cv2.imdecode(np.frombuffer(body, np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                print(f"{it['capture_id']}: frame is not a readable image", file=sys.stderr)
                return 2
            when = datetime.fromisoformat(it["capture_timestamp"])
            score, visible = check.check(image, detections_from_json(it.get("detections_json")), when.timestamp())
            expect = expectation(when, hidden, skip)
            verdicts.append(verdict(expect, visible))
            print(format_line(when, it["capture_id"], score, visible, expect))
    except Exception as exc:  # noqa: BLE001 - credentials, network, missing table or object
        print(f"AWS error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    judged = [v for v in verdicts if v]
    print(
        f"\nframes {len(verdicts)}, judged {len(judged)}, wrong {judged.count('WRONG')}, "
        f"references learnt {check.n_refs}"
    )
    return exit_code(verdicts)


if __name__ == "__main__":
    sys.exit(main())
