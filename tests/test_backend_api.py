"""Unit tests for the Platform B Serverless Backend (NHAT-P01)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import common  # noqa: E402


def _load_module(name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(name, str(file_path))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


api_handler = _load_module("milk_api_handler", ROOT / "backend" / "api" / "handler.py")
ingest_handler = _load_module("milk_ingest_handler", ROOT / "backend" / "ingest" / "handler.py")


def test_alias_resolution_maps_model_label_to_packaging_name():
    sku_id, sku_name = common.resolve_sku_alias("TMP-MLK-TH-02")
    assert sku_id == "TH true MILK Sữa Tươi Tiệt Trùng Ít Đường 180ml"
    assert sku_name == sku_id

    snack_id, _ = common.resolve_sku_alias("original145")
    assert snack_id == "Slide Original 145g"

    # Unknown new SKU not in SKU Master must still be accepted
    new_id, new_name = common.resolve_sku_alias("NEW-SKU-999", "Sữa Mới 180ml")
    assert new_id == "Sữa Mới 180ml"
    assert new_name == "Sữa Mới 180ml"

    # Unrecognized carton stays None
    assert common.resolve_sku_alias(None) == (None, None)


def test_lower_median_smoothing():
    assert common.lower_median([4, 2, 5]) == 4
    assert common.lower_median([1, 4]) == 1
    assert common.lower_median([3]) == 3
    assert common.lower_median([]) == 0


def test_validation_card_result_rule():
    assert common.compute_validation_result(True, "Exact Match") == "Đạt"
    assert common.compute_validation_result(True, "Minor") == "Đạt"
    assert common.compute_validation_result(True, "Major") == "Không đạt"
    assert common.compute_validation_result(False, "Wrong SKU") == "Không đạt"
    assert common.compute_validation_result(None, None) == "Pending"


def test_validate_capture_payload_checks_16_and_10_columns():
    valid_row = {col: "x" for col in common.CV_OUTPUT_COLUMNS}
    valid_log = {col: "x" for col in common.CAPTURE_LOG_COLUMNS}
    assert common.validate_capture_payload({"rows": [valid_row], "log": valid_log}) == []

    bad_row = {col: "x" for col in common.CV_OUTPUT_COLUMNS[:-1]}
    errors = common.validate_capture_payload({"rows": [bad_row], "log": valid_log})
    assert any("processing_time_ms" in e for e in errors)


def test_csv_export_has_utf8_bom_and_16_columns():
    row = {
        "reading_id": "RD-S01-20261121-140654-002",
        "capture_id": "CAP-S01-20261121-140654",
        "store_id": "DEMO-S01",
        "camera_id": "CAM-S01-A",
        "capture_timestamp": "2026-11-21T14:06:54+07:00",
        "capture_source": "CCTV",
        "image_filename": "CAM-S01-A_20261121_140654.jpg",
        "sku_id": "TH true MILK Sữa Tươi Tiệt Trùng Ít Đường 180ml",
        "sku_name": "TH true MILK Sữa Tươi Tiệt Trùng Ít Đường 180ml",
        "unit_count": 2,
        "confidence_score": 0.87,
        "detection_method": "Visual",
        "bounding_box": [[1036, 244, 62, 103], [991, 235, 53, 102]],
        "is_flagged": False,
        "flag_reason": "",
        "processing_time_ms": 167,
    }
    csv_out = common.to_csv([row], common.CV_OUTPUT_COLUMNS, bom=True)
    assert csv_out.startswith("\ufeffreading_id,")
    lines = csv_out.lstrip("\ufeff").strip().splitlines()
    assert len(lines) == 2
    assert len(lines[0].split(",")) == 16
    assert '"[[1036,244,62,103],[991,235,53,102]]",FALSE,,167' in lines[1]


def test_rbac_blocks_unassigned_self_registered_user():
    event = {
        "httpMethod": "GET",
        "path": "/v1/products",
        "requestContext": {"authorizer": {"claims": {"sub": "u-1", "email": "new@datagent.io"}}},
    }
    resp = api_handler.lambda_handler(event)
    assert resp["statusCode"] == 403
    body = json.loads(resp["body"])
    assert body["error"] == "PENDING_ROLE_ASSIGNMENT"


def test_rbac_blocks_datagent_from_admin_import():
    event = {
        "httpMethod": "POST",
        "path": "/v1/imports/sku-master",
        "requestContext": {
            "authorizer": {
                "claims": {
                    "sub": "u-2",
                    "email": "viewer@datagent.io",
                    "cognito:groups": "datagent",
                }
            }
        },
        "body": json.dumps({"items": []}),
    }
    resp = api_handler.lambda_handler(event)
    assert resp["statusCode"] == 403
    assert json.loads(resp["body"])["error"] == "FORBIDDEN"


def test_health_endpoint_is_public():
    resp = api_handler.lambda_handler({"httpMethod": "GET", "path": "/v1/health"})
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["status"] == "ok"
    assert body["flag_threshold"] == 0.70


def test_select_best_capture_hourly_tiebreak():
    candidates = [
        {"capture_id": "C1", "flagged_rows": 2, "units_found": 20, "capture_timestamp": "2026-11-21T10:05:00+07:00"},
        {"capture_id": "C2", "flagged_rows": 0, "units_found": 12, "capture_timestamp": "2026-11-21T10:15:00+07:00"},
        {"capture_id": "C3", "flagged_rows": 0, "units_found": 18, "capture_timestamp": "2026-11-21T10:35:00+07:00"},
        {"capture_id": "C4", "flagged_rows": 0, "units_found": 18, "capture_timestamp": "2026-11-21T10:25:00+07:00"},
    ]
    best = ingest_handler.select_best_capture(candidates)
    assert best is not None
    assert best["capture_id"] == "C4"


def test_options_preflight_returns_cors_headers():
    resp = api_handler.lambda_handler(
        {
            "httpMethod": "OPTIONS",
            "path": "/v1/products",
            "headers": {"origin": "https://main.d2k8euxy0yoiv8.amplifyapp.com"},
        }
    )
    assert resp["statusCode"] == 204
    assert resp["headers"]["Access-Control-Allow-Origin"] == "https://main.d2k8euxy0yoiv8.amplifyapp.com"
    assert "Authorization" in resp["headers"]["Access-Control-Allow-Headers"]
