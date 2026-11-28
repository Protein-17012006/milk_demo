"""The data export of the gallery (ops/gallery_data.py): done audits and their frames, against moto's DynamoDB and S3."""

from __future__ import annotations

import json

import boto3
import pytest
from moto import mock_aws

from ops.gallery_data import export
from training.store_view.dataset import read_scoring_frames

REGION = "ap-southeast-1"
BUCKET = "test-analytics-bucket"
CAMERA = "CAM-S01-A"
CID1 = "CAP-S01-20261127-235959-3"
CID2 = "CAP-S01-20261128-000100"


@pytest.fixture
def aws(monkeypatch):
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(key, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name=REGION)
        table = ddb.create_table(
            TableName="test-audits",
            KeySchema=[
                {"AttributeName": "store_id", "KeyType": "HASH"},
                {"AttributeName": "audit_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "store_id", "AttributeType": "S"},
                {"AttributeName": "audit_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        s3 = boto3.client("s3", region_name=REGION)
        s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})
        yield table, s3


def put(table, s3, audit_id, cid, status="done", camera=CAMERA, with_frame=True):
    key = f"audits/frames/{camera}/{cid[8:12]}-{cid[12:14]}-{cid[14:16]}/{cid}.jpg"
    if with_frame:
        s3.put_object(Bucket=BUCKET, Key=key, Body=b"jpeg " + cid.encode())
    table.put_item(
        Item={
            "store_id": "S01",
            "audit_id": audit_id,
            "camera_id": camera,
            "status": status,
            "capture_id": cid,
            "capture_timestamp": "2026-11-27T16:59:59+00:00",  # UTC; the store day comes from the id
            "ai_boxes_json": "[]",
            "verdicts_json": "[]",
            "image_key": key,
            "model_version": "ignored",
        }
    )


def test_export_writes_audits_frames_and_a_manifest_that_marks_scoring_frames(aws, tmp_path):
    table, s3 = aws
    put(table, s3, "TRN-CAM-S01-A-20261127-01", CID1)
    put(table, s3, "AUD-CAM-S01-A-20261127-01", CID1)
    put(table, s3, "CMP-CAM-S01-A-20261128-01", CID2)
    put(table, s3, "REV-CAM-S01-A-seg-0001", "CAP-S01-20261128-000200")
    put(table, s3, "TRN-CAM-S01-A-20261127-02", "CAP-S01-20261127-120000", status="pending")
    put(table, s3, "TRN-CAM-S01-B-20261127-01", "CAP-S01-20261127-130000", camera="CAM-S01-B")
    put(table, s3, "XYZ-CAM-S01-A-1", "CAP-S01-20261127-140000")

    counts = export(table, s3, BUCKET, CAMERA, tmp_path)

    assert counts == {
        "audits": {"TRN-": 1, "REV-": 1, "CMP-": 1, "AUD-": 1},
        "frames_new": 3,
        "frames_kept": 0,
        "frames_missing": 0,
    }
    audits = json.loads((tmp_path / "audits.json").read_text(encoding="utf-8"))
    assert sorted(a["audit_id"] for a in audits) == [
        "AUD-CAM-S01-A-20261127-01",
        "CMP-CAM-S01-A-20261128-01",
        "REV-CAM-S01-A-seg-0001",
        "TRN-CAM-S01-A-20261127-01",
    ]
    assert set(audits[0]) == {
        "audit_id", "status", "capture_id", "capture_timestamp", "ai_boxes_json", "verdicts_json", "image_key",
        "candidate_version",
    }  # fmt: skip
    folder = tmp_path / "frames" / CAMERA
    assert (folder / "2026-11-27" / f"{CID1}.jpg").read_bytes() == b"jpeg " + CID1.encode()
    assert (folder / "2026-11-28" / f"{CID2}.jpg").is_file()
    rows = [json.loads(line) for line in (folder / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    by_id = {r["capture_id"]: r for r in rows}
    assert set(by_id[CID1]) == {"capture_id", "capture_timestamp", "audit_ids"}
    assert sorted(by_id[CID1]["audit_ids"]) == ["AUD-CAM-S01-A-20261127-01", "TRN-CAM-S01-A-20261127-01"]
    assert len(rows) == 3
    assert read_scoring_frames(folder) == {CID1}


def test_a_second_export_fetches_only_what_is_missing_and_rewrites_the_manifest(aws, tmp_path):
    table, s3 = aws
    put(table, s3, "TRN-CAM-S01-A-20261127-01", CID1)
    export(table, s3, BUCKET, CAMERA, tmp_path)
    put(table, s3, "AUD-CAM-S01-A-20261127-01", CID1)  # the capture became a scoring frame since
    put(table, s3, "CMP-CAM-S01-A-20261128-01", CID2)
    counts = export(table, s3, BUCKET, CAMERA, tmp_path)
    assert counts["frames_new"] == 1 and counts["frames_kept"] == 1
    assert read_scoring_frames(tmp_path / "frames" / CAMERA) == {CID1}


def test_a_pending_scoring_audit_still_marks_its_capture_as_a_scoring_frame(aws, tmp_path):
    table, s3 = aws
    put(table, s3, "TRN-CAM-S01-A-20261127-01", CID1)
    put(table, s3, "AUD-CAM-S01-A-20261127-01", CID1, status="pending")
    export(table, s3, BUCKET, CAMERA, tmp_path)
    assert read_scoring_frames(tmp_path / "frames" / CAMERA) == {CID1}
    audits = json.loads((tmp_path / "audits.json").read_text(encoding="utf-8"))
    assert [a["audit_id"] for a in audits] == ["TRN-CAM-S01-A-20261127-01"]


def test_a_frame_that_is_not_in_the_bucket_is_counted_not_fatal(aws, tmp_path):
    table, s3 = aws
    put(table, s3, "TRN-CAM-S01-A-20261127-01", CID1, with_frame=False)
    counts = export(table, s3, BUCKET, CAMERA, tmp_path)
    assert counts["frames_new"] == 0 and counts["frames_missing"] == 1
