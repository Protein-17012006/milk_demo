"""Access control and the result -> live -> frame path of the web app."""

import base64
import dataclasses
import importlib
import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.update(
    {
        "MILK_WEB_PASSWORD": "pw-test",
        "MILK_WEB_SECRET": "s" * 64,
        "MILK_INTERNAL_TOKEN": "token-test",
        "MILK_ORIGIN_SECRET": "origin-test",
        "MILK_CAMERA_ID": "CAM-T-A",
    }
)

from fastapi.testclient import TestClient  # noqa: E402

web = importlib.import_module("milk.web.app")
ORIGIN = {"X-Origin-Verify": "origin-test"}
TOKEN = {"X-Internal-Token": "token-test"}

META = {
    "camera_id": "CAM-T-A",
    "store_id": "DEMO-S01",
    "capture_id": "CAP-S01-20261118-180000",
    "capture_timestamp": "2026-11-18T18:00:00+07:00",
    "received_at": 1795000000.0,
    "processing_time_ms": 420,
    "latency_ms": 900,
    "frame_w": 3840,
    "frame_h": 2160,
    "display_w": 1920,
    "display_h": 1080,
    "roi": None,
    "detections": [{"sku_id": "TMP-MLK-VNM-01", "conf": 0.9, "box": [10, 20, 30, 60], "flagged": False}],
    "counts": {"TMP-MLK-VNM-01": 2, "UNRECOGNIZED": 1},
    "smoothed": {"TMP-MLK-VNM-01": 2, "UNRECOGNIZED": 1},
    "units": 3,
    "flagged_rows": 1,
    "flagged": [
        {"sku_id": None, "sku_name": None, "unit_count": 1, "confidence_score": 0.0, "flag_reason": "Unrecognized"}
    ],
    "faces_blurred": 0,
    "pipeline": "null",
}
JPEG = b"\xff\xd8\xff\xe0fake-jpeg-bytes"


@pytest.fixture(scope="module")
def local():
    # One client for everything that touches the live state, so it all runs on one event loop.
    with TestClient(web.app, base_url="https://testserver", client=("127.0.0.1", 40000)) as client:
        yield client


def remote(headers=ORIGIN):
    return TestClient(web.app, base_url="https://testserver", headers=headers)


def test_requests_without_the_cloudfront_secret_are_refused():
    assert remote(headers={}).get("/healthz").status_code == 403
    assert remote().get("/healthz").status_code == 200


def test_dashboard_and_api_need_a_login():
    client = remote()
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/login"
    assert client.get("/api/live").status_code == 401
    assert client.get("/api/frame").status_code == 401


def test_wrong_password_is_refused():
    assert remote().post("/api/login", json={"password": "nope"}).status_code == 401


def test_internal_endpoints_need_the_token(local):
    # A GPU worker elsewhere reaches the hub through CloudFront, with the token.
    assert remote().post("/internal/status", json={"camera_id": "CAM-T-A"}).status_code == 403
    assert (
        remote().post("/internal/status", json={"camera_id": "CAM-T-A"}, headers={**ORIGIN, **TOKEN}).status_code == 200
    )
    # Without CloudFront's secret header the request never gets as far as the token.
    assert remote(headers=TOKEN).post("/internal/status", json={"camera_id": "CAM-T-A"}).status_code == 403
    assert local.post("/internal/status", json={"camera_id": "CAM-T-A"}).status_code == 403
    assert local.post("/internal/status", json={"camera_id": "CAM-T-A"}, headers=TOKEN).status_code == 200


class FakePersistence:
    saved, dropped, last_error = 0, 0, None

    def __init__(self):
        self.items = []

    def submit(self, record, jpeg):
        self.items.append((record, jpeg))


def test_persist_hands_the_capture_to_storage(local, monkeypatch):
    fake = FakePersistence()
    monkeypatch.setattr(web, "PERSIST", fake)
    payload = {"record": {"capture_id": "CAP-S01-20261118-180000"}, "jpeg_b64": base64.b64encode(JPEG).decode()}
    assert local.post("/internal/persist", json=payload, headers=TOKEN).status_code == 202
    assert fake.items == [({"capture_id": "CAP-S01-20261118-180000"}, JPEG)]


def test_persist_without_storage_configured_is_503(local, monkeypatch):
    monkeypatch.setattr(web, "PERSIST", None)
    payload = {"record": {"capture_id": "x"}, "jpeg_b64": None}
    assert local.post("/internal/persist", json=payload, headers=TOKEN).status_code == 503


def test_result_reaches_live_frame_and_history(local):
    payload = {"meta": dict(META), "jpeg_b64": base64.b64encode(JPEG).decode()}
    assert local.post("/internal/result", json=payload, headers=TOKEN).status_code == 200

    assert local.post("/api/login", json={"password": "pw-test"}).status_code == 200
    live = local.get("/api/live", params={"after": 0}).json()
    assert live["meta"]["capture_id"] == META["capture_id"]
    assert live["status"]["worker_ok"] is True
    assert local.get("/api/frame").content == JPEG
    history = local.get("/api/history", params={"minutes": 10**9}).json()
    assert history[-1]["total"] == 3
    flags = local.get("/api/flags").json()
    assert flags[0]["flag_reason"] == "Unrecognized"


def test_live_after_a_server_restart_returns_at_once(local):
    # A browser that saw seq 500 before a restart must not wait for seq 501.
    response = local.get("/api/live", params={"after": 500})
    assert response.status_code == 200
    assert response.json()["seq"] < 500


def test_export_rejects_a_bad_date(local):
    response = local.get("/api/export/cv-output.csv", params={"date": "18-11-2026"})
    assert response.status_code in (400, 503)


def test_healthz_reports_the_environment_and_version():
    body = remote().get("/healthz").json()
    assert body["ok"] is True and body["environment"] == "local" and body["version"] == "dev"


def test_session_cookie_is_secure_unless_turned_off(monkeypatch):
    secure = remote().post("/api/login", json={"password": "pw-test"})
    assert "secure" in secure.headers["set-cookie"].lower()
    # Environments behind the plain-HTTP load balancer set MILK_COOKIE_SECURE=false.
    monkeypatch.setattr(web, "settings", dataclasses.replace(web.settings, cookie_secure=False))
    plain = remote().post("/api/login", json={"password": "pw-test"})
    assert plain.status_code == 200 and "secure" not in plain.headers["set-cookie"].lower()


def test_exports_read_the_day_from_dynamodb(local, aws, monkeypatch):
    from conftest import BUCKET, REGION, TABLE

    from milk.cvoutput import CaptureIdAllocator, Detection, build_capture, counts_of, to_csv
    from milk.store import Persistence

    monkeypatch.setattr(web, "settings", dataclasses.replace(web.settings, table=TABLE, region=REGION))
    ts = datetime(2026, 11, 18, 18, 0, 0, tzinfo=timezone(timedelta(hours=7)))
    rows, log = build_capture(
        [Detection("TMP-MLK-VNM-01", "Vinamilk 180ml", 0.9, (1, 2, 3, 4))],
        stem=CaptureIdAllocator().stem("S01", ts),
        store_id="DEMO-S01",
        camera_id="CAM-T-A",
        capture_source="CCTV",
        ts=ts,
        processing_time_ms=420,
    )
    record = {**log, "rows": rows, "log": log, "counts": counts_of(rows), "latency_ms": 900}
    Persistence(REGION, BUCKET, TABLE)._save(record, None)

    assert local.post("/api/login", json={"password": "pw-test"}).status_code == 200
    cv = local.get("/api/export/cv-output.csv", params={"camera": "CAM-T-A", "date": "2026-11-18"})
    assert cv.status_code == 200
    assert cv.content == to_csv(rows, web.CV_OUTPUT_COLUMNS).encode("utf-8")
    assert 'filename="CV_Output_CAM-T-A_2026-11-18.csv"' in cv.headers["content-disposition"]
    capture_log = local.get("/api/export/capture-log.csv", params={"camera": "CAM-T-A", "date": "2026-11-18"})
    assert capture_log.content == to_csv([log], web.CAPTURE_LOG_COLUMNS).encode("utf-8")
    empty = local.get("/api/export/cv-output.csv", params={"camera": "CAM-T-A", "date": "2026-11-17"})
    assert empty.content == to_csv([], web.CV_OUTPUT_COLUMNS).encode("utf-8")


def test_status_reports_the_ingest_server_as_down_when_absent(local):
    assert local.post("/api/login", json={"password": "pw-test"}).status_code == 200
    body = local.get("/api/status").json()
    assert body["ingest"]["ready"] is False and body["camera_id"] == "CAM-T-A"


def test_logout_clears_the_session():
    response = remote().post("/api/logout")
    assert response.status_code == 200 and "milk_session=" in response.headers["set-cookie"]
