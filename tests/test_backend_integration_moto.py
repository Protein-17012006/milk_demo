"""Integration tests with mocked AWS (moto) matching KHANG-T001 CI conventions."""
from __future__ import annotations

import importlib.util
import json
import sys
import urllib.parse
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import common  # noqa: E402


def _load_module(name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(name, str(file_path))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _auth_event(method: str, path: str, groups: str = "datagent", body: dict | None = None, query: dict | None = None):
    return {
        "httpMethod": method,
        "path": path,
        "queryStringParameters": query or {},
        "headers": {"origin": "https://main.d2k8euxy0yoiv8.amplifyapp.com"},
        "requestContext": {
            "authorizer": {
                "claims": {
                    "sub": "user-sub-001",
                    "email": "tester@datagent.io",
                    "cognito:groups": groups,
                }
            }
        },
        "body": json.dumps(body) if body is not None else None,
    }


def _create_mock_infra(region: str = "ap-southeast-1"):
    ddb = boto3.client("dynamodb", region_name=region)
    tables = [
        ("test-captures", "camera_id", "capture_id"),
        ("test-latest-stock", "store_id", "sku_id"),
        ("test-review-queue", "store_id", "queue_key"),
        ("test-sku-master", "sku_id", None),
        ("test-store-list", "store_id", None),
        ("test-corrections", "store_id", "correction_id"),
        ("test-user-prefs", "user_sub", None),
    ]
    for name, pk, sk in tables:
        key_schema = [{"AttributeName": pk, "KeyType": "HASH"}]
        attr_defs = [{"AttributeName": pk, "AttributeType": "S"}]
        if sk:
            key_schema.append({"AttributeName": sk, "KeyType": "RANGE"})
            attr_defs.append({"AttributeName": sk, "AttributeType": "S"})
        ddb.create_table(
            TableName=name,
            KeySchema=key_schema,
            AttributeDefinitions=attr_defs,
            BillingMode="PAY_PER_REQUEST",
        )

    s3 = boto3.client("s3", region_name=region)
    s3.create_bucket(
        Bucket="test-analytics-bucket",
        CreateBucketConfiguration={"LocationConstraint": region},
    )


TH_SWEET = "TH true MILK Sữa Tươi Tiệt Trùng Có Đường 180ml"  # official name of TMP-MLK-TH-01
TH_LOW = "TH true MILK Sữa Tươi Tiệt Trùng Ít Đường 180ml"  # official name of TMP-MLK-TH-02


def _backend(monkeypatch: pytest.MonkeyPatch):
    """Both Lambdas on moto tables with the SKU master seeded. Call inside mock_aws."""
    region = "ap-southeast-1"
    env = {
        "AWS_REGION": region,
        "AWS_DEFAULT_REGION": region,
        "CAPTURES_TABLE": "test-captures",
        "LATEST_STOCK_TABLE": "test-latest-stock",
        "REVIEW_QUEUE_TABLE": "test-review-queue",
        "SKU_MASTER_TABLE": "test-sku-master",
        "STORE_LIST_TABLE": "test-store-list",
        "CORRECTIONS_TABLE": "test-corrections",
        "USER_PREFS_TABLE": "test-user-prefs",
        "ANALYTICS_BUCKET": "test-analytics-bucket",
        "HUB_BUCKET": "test-analytics-bucket",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    _create_mock_infra(region)
    api = _load_module("moto_api_handler", ROOT / "backend" / "api" / "handler.py")
    ingest = _load_module("moto_ingest_handler", ROOT / "backend" / "ingest" / "handler.py")
    assert api.lambda_handler(_auth_event("POST", "/v1/admin/seed", groups="team_admin"))["statusCode"] == 200
    return api, ingest


def _ingest(ingest, camera_id: str, hhmmss: str, counts: list[tuple[str, int]]) -> None:
    """Ingest one hub result of store DEMO-S01 taken on 21/11 at hhmmss; counts are (model label, units)."""
    capture_id = f"CAP-S01-20261121-{hhmmss}"
    ts = f"2026-11-21T{hhmmss[:2]}:{hhmmss[2:4]}:{hhmmss[4:]}+07:00"
    image = f"{camera_id}_20261121_{hhmmss}.jpg"
    head = {"capture_id": capture_id, "store_id": "DEMO-S01", "camera_id": camera_id, "capture_timestamp": ts,
            "capture_source": "CCTV", "image_filename": image}
    rows = [
        {**head, "reading_id": f"RD-S01-20261121-{hhmmss}-{i:03d}", "sku_id": label, "sku_name": label,
         "unit_count": units, "confidence_score": 0.9, "detection_method": "Visual",
         "bounding_box": [[10 + 60 * k, 20, 50, 80] for k in range(units)], "is_flagged": False, "flag_reason": "",
         "processing_time_ms": 20}
        for i, (label, units) in enumerate(counts, start=1)
    ]
    total = sum(units for _, units in counts)
    record = {**head, "image_key": f"frames/{camera_id}/2026-11-21/{image}", "processing_time_ms": 20,
              "units_found": total, "flagged_rows": 0, "rows": rows,
              "log": {**head, "units_found": total, "rows_written": len(rows), "flagged_rows": 0,
                      "processing_time_ms": 20}}
    assert ingest.ingest_capture(ingest._normalize_record(record))["status"] == "ingested"


def _units(api) -> dict[str, int]:
    resp = api.lambda_handler(_auth_event("GET", "/v1/products"))
    assert resp["statusCode"] == 200
    return {p["sku_id"]: p["unit_count"] for p in json.loads(resp["body"])["items"]}


@mock_aws
def test_a_sku_missing_from_the_next_capture_drops_to_zero(monkeypatch: pytest.MonkeyPatch):
    # 22/11 night: false Vinamilk readings stayed "on shelf" because later captures never mentioned them
    api, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "140700", [("TMP-MLK-TH-02", 3), ("TMP-MLK-TH-01", 1)])
    _ingest(ingest, "CAM-S01-A", "140710", [("TMP-MLK-TH-02", 3)])

    units = _units(api)
    assert (units[TH_SWEET], units[TH_LOW]) == (0, 3)
    kpi = json.loads(api.lambda_handler(_auth_event("GET", "/v1/kpi"))["body"])
    assert kpi["total_on_shelf_units"] == 3


@mock_aws
def test_a_capture_from_another_camera_leaves_the_first_cameras_skus(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "140700", [("TMP-MLK-TH-01", 2)])
    _ingest(ingest, "CAM-S01-B", "140710", [("TMP-MLK-TH-02", 3)])

    units = _units(api)
    assert (units[TH_SWEET], units[TH_LOW]) == (2, 3)


@mock_aws
def test_an_older_capture_arriving_late_leaves_a_newer_reading(monkeypatch: pytest.MonkeyPatch):
    # SQS does not keep order: the 14:07:00 result can be ingested after the 14:07:10 one
    api, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "140710", [("TMP-MLK-TH-01", 2)])
    _ingest(ingest, "CAM-S01-A", "140700", [("TMP-MLK-TH-02", 3)])

    assert _units(api)[TH_SWEET] == 2


@mock_aws
def test_end_to_end_ingest_review_and_export_with_moto(monkeypatch: pytest.MonkeyPatch):
    region = "ap-southeast-1"
    monkeypatch.setenv("AWS_REGION", region)
    monkeypatch.setenv("AWS_DEFAULT_REGION", region)
    monkeypatch.setenv("CAPTURES_TABLE", "test-captures")
    monkeypatch.setenv("LATEST_STOCK_TABLE", "test-latest-stock")
    monkeypatch.setenv("REVIEW_QUEUE_TABLE", "test-review-queue")
    monkeypatch.setenv("SKU_MASTER_TABLE", "test-sku-master")
    monkeypatch.setenv("STORE_LIST_TABLE", "test-store-list")
    monkeypatch.setenv("CORRECTIONS_TABLE", "test-corrections")
    monkeypatch.setenv("USER_PREFS_TABLE", "test-user-prefs")
    monkeypatch.setenv("ANALYTICS_BUCKET", "test-analytics-bucket")
    monkeypatch.setenv("HUB_BUCKET", "test-analytics-bucket")

    _create_mock_infra(region)

    api = _load_module("moto_api_handler", ROOT / "backend" / "api" / "handler.py")
    ingest = _load_module("moto_ingest_handler", ROOT / "backend" / "ingest" / "handler.py")

    # 1. Seed store_list & sku_master as team_admin
    seed_resp = api.lambda_handler(_auth_event("POST", "/v1/admin/seed", groups="team_admin"))
    assert seed_resp["statusCode"] == 200
    seed_body = json.loads(seed_resp["body"])
    assert seed_body["seeded_stores"] >= 1
    assert seed_body["seeded_skus"] >= 12

    # 2. Ingest a real-shaped 16-col capture payload (including flagged & unrecognized rows)
    capture_record = {
        "capture_id": "CAP-S01-20261121-140700",
        "store_id": "DEMO-S01",
        "camera_id": "CAM-S01-A",
        "capture_timestamp": "2026-11-21T14:07:00+07:00",
        "capture_source": "CCTV",
        "image_filename": "CAM-S01-A_20261121_140700.jpg",
        "image_key": "frames/CAM-S01-A/2026-11-21/CAM-S01-A_20261121_140700.jpg",
        "processing_time_ms": 142,
        "units_found": 5,
        "flagged_rows": 2,
        "rows": [
            {
                "reading_id": "RD-S01-20261121-140700-001",
                "capture_id": "CAP-S01-20261121-140700",
                "store_id": "DEMO-S01",
                "camera_id": "CAM-S01-A",
                "capture_timestamp": "2026-11-21T14:07:00+07:00",
                "capture_source": "CCTV",
                "image_filename": "CAM-S01-A_20261121_140700.jpg",
                "sku_id": "TMP-MLK-TH-02",
                "sku_name": "TH true MILK Sữa Tươi Tiệt Trùng Ít Đường 180ml",
                "unit_count": 3,
                "confidence_score": 0.87,
                "detection_method": "Visual",
                "bounding_box": [[10, 20, 50, 80]],
                "is_flagged": False,
                "flag_reason": "",
                "processing_time_ms": 142,
            },
            {
                "reading_id": "RD-S01-20261121-140700-002",
                "capture_id": "CAP-S01-20261121-140700",
                "store_id": "DEMO-S01",
                "camera_id": "CAM-S01-A",
                "capture_timestamp": "2026-11-21T14:07:00+07:00",
                "capture_source": "CCTV",
                "image_filename": "CAM-S01-A_20261121_140700.jpg",
                "sku_id": "TMP-MLK-TH-01",
                "sku_name": "TH true MILK Sữa Tươi Tiệt Trùng Có Đường 180ml",
                "unit_count": 1,
                "confidence_score": 0.0,
                "detection_method": "Visual",
                "bounding_box": [[60, 20, 50, 80]],
                "is_flagged": True,
                "flag_reason": "Low Confidence",
                "processing_time_ms": 142,
            },
            {
                "reading_id": "RD-S01-20261121-140700-003",
                "capture_id": "CAP-S01-20261121-140700",
                "store_id": "DEMO-S01",
                "camera_id": "CAM-S01-A",
                "capture_timestamp": "2026-11-21T14:07:00+07:00",
                "capture_source": "CCTV",
                "image_filename": "CAM-S01-A_20261121_140700.jpg",
                "sku_id": None,
                "sku_name": None,
                "unit_count": 1,
                "confidence_score": 0.45,
                "detection_method": "Visual",
                "bounding_box": [[110, 20, 50, 80]],
                "is_flagged": True,
                "flag_reason": "Unrecognized Product",
                "processing_time_ms": 142,
            },
        ],
        "log": {
            "capture_id": "CAP-S01-20261121-140700",
            "store_id": "DEMO-S01",
            "camera_id": "CAM-S01-A",
            "capture_timestamp": "2026-11-21T14:07:00+07:00",
            "capture_source": "CCTV",
            "image_filename": "CAM-S01-A_20261121_140700.jpg",
            "units_found": 5,
            "rows_written": 3,
            "flagged_rows": 2,
            "processing_time_ms": 142,
        },
    }

    normalized = ingest._normalize_record(capture_record, source_bucket="test-analytics-bucket")
    res1 = ingest.ingest_capture(normalized, write_analytics=True)
    assert res1["status"] == "ingested"
    assert res1["skus_updated"] == 3  # 2 recognized SKUs + 1 UNRECOGNIZED retained

    # 3. Idempotent deduplication check
    res2 = ingest.ingest_capture(normalized, write_analytics=True)
    assert res2["status"] == "duplicate_skipped"

    # 4. Products API returns aliased official packaging name + URL-encoded Vietnamese lookup works
    prod_resp = api.lambda_handler(_auth_event("GET", "/v1/products", groups="datagent"))
    assert prod_resp["statusCode"] == 200
    prod_body = json.loads(prod_resp["body"])
    target_sku = "TH true MILK Sữa Tươi Tiệt Trùng Ít Đường 180ml"
    matched = [p for p in prod_body["items"] if p["sku_id"] == target_sku]
    assert len(matched) == 1
    assert matched[0]["unit_count"] == 3

    encoded_path = "/v1/products/" + urllib.parse.quote(target_sku, safe="")
    detail_resp = api.lambda_handler(_auth_event("GET", encoded_path, groups="datagent"))
    assert detail_resp["statusCode"] == 200
    detail_body = json.loads(detail_resp["body"])
    assert detail_body["sku_id"] == target_sku

    # 5. Review queue contains flagged items & field_team can submit a correction
    q_resp = api.lambda_handler(_auth_event("GET", "/v1/review-queue", groups="field_team"))
    assert q_resp["statusCode"] == 200
    q_items = json.loads(q_resp["body"])["items"]
    assert len(q_items) == 2

    corr_resp = api.lambda_handler(
        _auth_event(
            "POST",
            "/v1/corrections",
            groups="field_team",
            body={
                "store_id": "DEMO-S01",
                "queue_key": q_items[0]["queue_key"],
                "reading_id": q_items[0]["reading_id"],
                "original_sku_id": q_items[0]["sku_id"],
                "corrected_sku_id": target_sku,
                "original_count": 1,
                "corrected_count": 2,
                "correction_type": "SKU Fix",
                "notes": "Verified against packaging",
            },
        )
    )
    assert corr_resp["statusCode"] == 201

    # 6. Export CV Output CSV returns exact 16 Data Dictionary columns with UTF-8 BOM
    csv_resp = api.lambda_handler(_auth_event("GET", "/v1/exports/cv-output.csv", groups="datagent"))
    assert csv_resp["statusCode"] == 200
    assert csv_resp["body"].startswith("\ufeffreading_id,")
    header = csv_resp["body"].lstrip("\ufeff").splitlines()[0].split(",")
    assert header == common.CV_OUTPUT_COLUMNS
    assert len(header) == 16
