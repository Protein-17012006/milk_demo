"""Review frames on the Model page for the cans the auto-labeller left to people (auto-label design 5.5), and people's
decisions back as the review file that `auto_label_run labels --review` reads.

A segment the queue (`queue.json`) lists gets one review frame: the frame of the segment that shows most of its cans
to review. Its boxes are the cans a person must decide (needs_flavour: no flavour shown, no Right offered) and the cans
already accepted, by the machine or by reuse (their flavour shown and pre-filled Right, so a person corrects only what
is wrong). Cans waiting on another segment's frame and cans already masked get no box.

    python -m training.store_view.auto_label_review push --proposals P --frames F --truth T --segments S [--trn TRN] ^
        --camera CAM-S01-A --analytics-bucket B --table milk-backend-development-audits --model-version V
    python -m training.store_view.auto_label_review export --table milk-backend-development-audits --out review.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from training.store_view.auto_label import Decision

STORE_ID = "DEMO-S01"
REGION_NAME = "ap-southeast-1"
ICT = timezone(timedelta(hours=7))


def audit_id(camera: str, segment: str) -> str:
    return f"REV-{camera}-{segment}"


def pick_frame(proposal: dict, track_ids: list[str]) -> str:
    """The frame of the segment that shows the most of these cans; on a tie the one nearest the segment's middle."""
    frames = proposal["frames"]
    wanted = [t for t in proposal["tracks"] if t.id in set(track_ids)]
    middle = (len(frames) - 1) / 2

    def rank(i: int) -> tuple[int, float, int]:
        return -sum(1 for t in wanted if frames[i] in t.seen), abs(i - middle), i

    return frames[min(range(len(frames)), key=rank)]


def review_boxes(
    proposal: dict, decisions: dict[str, Decision], track_ids: list[str], frame: str
) -> tuple[list[dict], list[dict]]:
    """The boxes of the review frame and the pre-filled verdicts (Right on each accepted can)."""
    boxes: list[dict] = []
    verdicts: list[dict] = []
    for t in proposal["tracks"]:
        own = t.box_in(frame)
        if own is None:
            continue
        box = [int(round(v)) for v in own]
        d = decisions.get(t.id)
        if t.id in track_ids:
            boxes.append(
                {
                    "box_id": len(boxes) + 1,
                    "track_id": t.id,
                    "sku_id": None,
                    "conf": 0.0,
                    "box": box,
                    "needs_flavour": True,
                }
            )
        elif d is not None and d.status == "accept":
            boxes.append({"box_id": len(boxes) + 1, "track_id": t.id, "sku_id": d.sku, "conf": 1.0, "box": box})
            verdicts.append({"box_id": len(boxes), "verdict": "correct"})
    return boxes, verdicts


def review_item(
    proposal: dict,
    decisions: dict[str, Decision],
    track_ids: list[str],
    camera: str,
    manifest_row: dict,
    image_key: str,
    model_version: str,
) -> dict:
    """The pending audit row of one segment's review frame, shaped like the ingest's sampled frames."""
    boxes, verdicts = review_boxes(proposal, decisions, track_ids, manifest_row["capture_id"])
    return {
        "store_id": STORE_ID,
        "audit_id": audit_id(camera, proposal["segment"]),
        "purpose": "review",
        "segment_id": proposal["segment"],
        "camera_id": camera,
        "capture_id": manifest_row["capture_id"],
        "capture_timestamp": manifest_row["capture_timestamp"],
        "image_key": image_key,
        "model_version": model_version,
        "pipeline": "auto-label",
        "display_visible": True,
        "status": "pending",
        "sampled_at": datetime.now(ICT).isoformat(timespec="seconds"),
        "ai_boxes_json": json.dumps(boxes, separators=(",", ":")),
        "verdicts_json": json.dumps(verdicts, separators=(",", ":")),
        "missed_json": "[]",
    }


def review_file(audits: list[dict]) -> dict:
    """People's decisions on the done review frames, by segment and can (auto_label_labels' review file):
    Right keeps the box's flavour, Wrong SKU names the chosen one, Not our SKU and Out of scope stay as they are;
    missed points become [x, y]. Other audits, and review frames not done, are left out."""
    out: dict = {}
    for a in audits:
        if not str(a.get("audit_id", "")).startswith("REV-") or a.get("status") != "done":
            continue
        boxes = {b["box_id"]: b for b in json.loads(a.get("ai_boxes_json") or "[]")}
        tracks = {}
        for v in json.loads(a.get("verdicts_json") or "[]"):
            b = boxes.get(v.get("box_id"))
            if b is None or not b.get("track_id"):
                continue
            verdict = v.get("verdict")
            if verdict == "correct" and b.get("sku_id"):
                tracks[b["track_id"]] = {"verdict": "sku", "sku": b["sku_id"]}
            elif verdict == "wrong_sku" and v.get("true_sku_id"):
                tracks[b["track_id"]] = {"verdict": "sku", "sku": v["true_sku_id"]}
            elif verdict in ("not_product", "out_of_scope"):
                tracks[b["track_id"]] = {"verdict": verdict}
        missed = [[m["x"], m["y"]] for m in json.loads(a.get("missed_json") or "[]")]
        out[a["segment_id"]] = {"tracks": tracks, "missed": missed}
    return out


def _manifest(frames_dir: Path) -> dict[str, dict]:
    path = frames_dir / "manifest.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {r["capture_id"]: r for r in rows}


def push(
    proposals_dir: Path,
    queue_json: Path,
    frames_dir: Path,
    truth: Path,
    segments: Path,
    trn: Path | None,
    camera: str,
    analytics_bucket: str,
    table_name: str,
    model_version: str,
    s3,
    ddb,
) -> list[str]:
    """One pending review frame per segment of queue.json: the decisions are those the queue command computes (people's
    decisions reused); the frame is copied from the hub bucket to the analytics bucket like a sampled frame. An audit
    that already exists, pending or done, is left alone. Returns the audit ids created now."""
    from botocore.exceptions import ClientError

    from training.store_view.auto_label_reuse import REUSE_MIN_SIM, queue
    from training.store_view.auto_label_run import human_precedents, load_proposals
    from training.store_view.dataset import read_scoring_frames

    props = {p["segment"]: p for p in load_proposals(proposals_dir)}
    segs = json.loads(Path(segments).read_text(encoding="utf-8"))
    decided = queue(list(props.values()), human_precedents(truth, segs, frames_dir, trn), REUSE_MIN_SIM)
    rows, scoring = _manifest(frames_dir), read_scoring_frames(frames_dir)
    table = ddb.Table(table_name)
    created = []
    for seg, track_ids in json.loads(Path(queue_json).read_text(encoding="utf-8")).items():
        frame = pick_frame(props[seg], track_ids)
        if frame in scoring:
            raise ValueError(f"{seg}: {frame} is a scoring frame (AUD) and can never be a review frame")
        row = rows[frame]
        key = f"audits/frames/{camera}/{row['capture_timestamp'][:10]}/{row['image_key'].rsplit('/', 1)[-1]}"
        s3.copy_object(Bucket=analytics_bucket, Key=key, CopySource={"Bucket": row["bucket"], "Key": row["image_key"]})
        item = review_item(props[seg], decided.decisions[seg], track_ids, camera, row, key, model_version)
        try:
            table.put_item(Item=item, ConditionExpression="attribute_not_exists(audit_id)")
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                continue
            raise
        created.append(item["audit_id"])
    return created


def export(table_name: str, ddb) -> dict:
    """The review file from every review frame of the audits table (only done ones give decisions)."""
    from boto3.dynamodb.conditions import Attr

    table = ddb.Table(table_name)
    kw = {"FilterExpression": Attr("audit_id").begins_with("REV-")}
    resp = table.scan(**kw)
    items = list(resp["Items"])
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **kw)
        items += resp["Items"]
    return review_file(items)


def main(argv: list[str] | None = None) -> None:
    import boto3

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("push")
    for name in ("--proposals", "--frames", "--truth", "--segments"):
        p.add_argument(name, type=Path, required=True)
    p.add_argument("--queue", type=Path, help="default: <proposals>/queue.json")
    p.add_argument("--trn", type=Path)
    for name in ("--camera", "--analytics-bucket", "--table", "--model-version"):
        p.add_argument(name, required=True)
    e = sub.add_parser("export")
    e.add_argument("--table", required=True)
    e.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    ddb = boto3.resource("dynamodb", region_name=REGION_NAME)
    if args.command == "export":
        decisions = export(args.table, ddb)
        args.out.write_text(json.dumps(decisions, indent=1), encoding="utf-8")
        print(f"{len(decisions)} done review frames -> {args.out}")
        return
    created = push(
        args.proposals,
        args.queue or args.proposals / "queue.json",
        args.frames,
        args.truth,
        args.segments,
        args.trn,
        args.camera,
        args.analytics_bucket,
        args.table,
        args.model_version,
        boto3.client("s3", region_name=REGION_NAME),
        ddb,
    )
    print(json.dumps({"created": created}))


if __name__ == "__main__":
    main()
