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

import json
from datetime import datetime, timedelta, timezone

from training.store_view.auto_label import Decision

STORE_ID = "DEMO-S01"
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
