"""Storage of captures (S3 + DynamoDB) and the re-index job that rebuilds the table from S3."""

import json
from datetime import datetime, timedelta, timezone

from conftest import BUCKET, REGION, TABLE

from milk import reindex as reindex_module
from milk.cvoutput import CaptureIdAllocator, Detection, build_capture, counts_of
from milk.store import Persistence, candidate_key

ICT = timezone(timedelta(hours=7))
JPEG = b"\xff\xd8\xff\xe0fake"


def capture(ts: datetime, camera: str = "CAM-T-A") -> dict:
    dets = [
        Detection("TMP-MLK-VNM-01", "Vinamilk Không Đường 180ml", 0.9, (1, 2, 3, 4)),
        Detection(None, None, 0.1, (5, 6, 7, 8)),
    ]
    rows, log = build_capture(
        dets,
        stem=CaptureIdAllocator().stem("S01", ts),
        store_id="DEMO-S01",
        camera_id=camera,
        capture_source="CCTV",
        ts=ts,
        processing_time_ms=420,
    )
    return {**log, "rows": rows, "log": log, "counts": counts_of(rows), "latency_ms": 900}


def test_save_writes_the_frame_the_result_file_and_the_row(aws):
    s3, table = aws
    store = Persistence(REGION, BUCKET, TABLE)
    record = capture(datetime(2026, 11, 18, 18, 0, 0, tzinfo=ICT))
    store._save(record, JPEG)

    prefix = "CAM-T-A/2026-11-18"
    frame = s3.get_object(Bucket=BUCKET, Key=f"frames/{prefix}/{record['image_filename']}")["Body"].read()
    assert frame == JPEG
    result = json.loads(
        s3.get_object(Bucket=BUCKET, Key=f"results/{prefix}/{record['capture_id']}.json")["Body"].read()
    )
    assert result["image_key"] == f"frames/{prefix}/{record['image_filename']}"
    item = table.get_item(Key={"camera_id": "CAM-T-A", "capture_id": record["capture_id"]})["Item"]
    assert item["units_found"] == 2 and item["flagged_rows"] == 1
    assert json.loads(item["rows_json"]) == record["rows"]


def test_save_without_a_frame_stores_no_image(aws):
    s3, table = aws
    record = capture(datetime(2026, 11, 18, 18, 0, 1, tzinfo=ICT))
    Persistence(REGION, BUCKET, TABLE)._save(record, None)
    item = table.get_item(Key={"camera_id": "CAM-T-A", "capture_id": record["capture_id"]})["Item"]
    assert item["image_key"] == ""
    assert "Contents" not in s3.list_objects_v2(Bucket=BUCKET, Prefix="frames/")


def test_reindex_rebuilds_the_table_from_result_files(aws):
    s3, table = aws
    store = Persistence(REGION, BUCKET, TABLE)
    now = datetime.now(ICT).replace(microsecond=0)
    fresh = capture(now)
    old = capture(now - timedelta(days=40))
    store._save(fresh, JPEG)
    store._save(old, None)
    s3.put_object(Bucket=BUCKET, Key="results/CAM-T-A/notes.txt", Body=b"not a capture")
    s3.put_object(Bucket=BUCKET, Key="results/CAM-T-A/broken.json", Body=b'{"capture_id": "x"}')
    for record in (fresh, old):  # the table is lost; the files remain
        table.delete_item(Key={"camera_id": "CAM-T-A", "capture_id": record["capture_id"]})

    dry = reindex_module.reindex(s3, table, BUCKET, dry_run=True)
    assert dry == {"loaded": 1, "expired": 1, "skipped": 2}
    assert table.scan()["Count"] == 0

    stats = reindex_module.reindex(s3, table, BUCKET)
    assert stats == {"loaded": 1, "expired": 1, "skipped": 2}
    item = table.get_item(Key={"camera_id": "CAM-T-A", "capture_id": fresh["capture_id"]})["Item"]
    assert item["image_key"].startswith("frames/CAM-T-A/")
    assert item["expires_at"] == reindex_module.expires_at(fresh)
    # Running it again changes nothing.
    assert reindex_module.reindex(s3, table, BUCKET)["loaded"] == 1
    assert table.scan()["Count"] == 1


def test_reindex_prefix_limits_the_files(aws):
    s3, table = aws
    store = Persistence(REGION, BUCKET, TABLE)
    now = datetime.now(ICT).replace(microsecond=0)
    store._save(capture(now, "CAM-A"), None)
    store._save(capture(now, "CAM-B"), None)
    stats = reindex_module.reindex(s3, table, BUCKET, prefix="CAM-B/")
    assert stats["loaded"] == 1


def test_reindex_main_needs_storage_settings(monkeypatch, capsys):
    monkeypatch.delenv("MILK_BUCKET", raising=False)
    monkeypatch.delenv("MILK_TABLE", raising=False)
    assert reindex_module.main([]) == 2


def test_reindex_main_prints_a_summary(aws, monkeypatch, capsys):
    monkeypatch.setenv("MILK_BUCKET", BUCKET)
    monkeypatch.setenv("MILK_TABLE", TABLE)
    monkeypatch.setenv("MILK_REGION", REGION)
    Persistence(REGION, BUCKET, TABLE)._save(capture(datetime.now(ICT).replace(microsecond=0)), None)
    assert reindex_module.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "reindex_summary" in out and "loaded=1" in out and "dry_run=true" in out


CANDIDATE = {
    "camera_id": "CAM-T-A",
    "capture_id": "CAP-S01-20261127-100005",
    "capture_timestamp": "2026-11-27T10:00:05+07:00",
    "candidate_version": "v2",
    "processing_time_ms": 310,
    "detections": [{"sku_id": "original145", "conf": 0.9, "box": [15, 25, 30, 40]}],
}


def test_candidate_key_sits_beside_the_capture_result():
    payload = {
        "camera_id": "CAM-S01-A",
        "capture_id": "CAP-S01-20261127-100005",
        "capture_timestamp": "2026-11-27T10:00:05+07:00",
    }
    assert candidate_key(payload) == "results/CAM-S01-A/2026-11-27/CAP-S01-20261127-100005.candidate.json"


def test_a_candidate_result_is_one_file_and_no_row(aws):
    s3, table = aws
    store = Persistence(REGION, BUCKET, TABLE)
    store._handle("candidate", CANDIDATE, None)
    stored = json.loads(s3.get_object(Bucket=BUCKET, Key=candidate_key(CANDIDATE))["Body"].read())
    assert stored == CANDIDATE
    assert table.scan()["Items"] == []
    assert "Contents" not in s3.list_objects_v2(Bucket=BUCKET, Prefix="frames/")


def test_a_candidate_result_waits_in_the_same_queue_and_is_dropped_when_it_is_full(aws):
    store = Persistence(REGION, BUCKET, TABLE, maxsize=1)
    store.submit_candidate(CANDIDATE)
    store.submit_candidate({**CANDIDATE, "capture_id": "CAP-S01-20261127-100015"})
    assert store.dropped == 1
    assert store._queue.get_nowait() == ("candidate", CANDIDATE, None)


def test_reindex_leaves_candidate_files_alone(aws):
    s3, table = aws
    store = Persistence(REGION, BUCKET, TABLE)
    record = capture(datetime.now(ICT))
    store._save(record, JPEG)
    store._handle("candidate", {**CANDIDATE, "capture_id": record["capture_id"]}, None)
    table.delete_item(Key={"camera_id": "CAM-T-A", "capture_id": record["capture_id"]})
    stats = reindex_module.reindex(s3, table, BUCKET)
    assert stats == {"loaded": 1, "expired": 0, "skipped": 0}
