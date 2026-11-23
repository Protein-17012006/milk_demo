"""End-to-end check of a deployed hub: the pipeline runs it in the test environment.

It runs as a one-off ECS task from the same image as the hub and plays both the counting
worker and a browser against the real service behind the load balancer, then checks
storage in S3 and DynamoDB. It uses its own camera, CAM-E2E, so it never touches real
captures:

1. reset: delete earlier CAM-E2E captures from the table and the bucket
2. health (and that the service runs this build), access control
3. a capture posted as the worker reaches live, frame, history and flags
4. the same capture, persisted, lands in S3 and DynamoDB and comes back in both CSV
   exports byte for byte as cvoutput writes them
5. every page and static file of the dashboard loads
6. reset again, so the test environment holds only what this check loads

Prints one `e2e_check` line per check and one `e2e_summary` line; exits 1 if any failed.

    python -m milk.selfcheck
"""

from __future__ import annotations

import base64
import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from . import config
from .cvoutput import (
    CAPTURE_LOG_COLUMNS,
    CV_OUTPUT_COLUMNS,
    CaptureIdAllocator,
    Detection,
    build_capture,
    counts_of,
    to_csv,
)

CAMERA = "CAM-E2E"
# Smallest valid JPEG header plus filler; the hub stores and returns the bytes as they are.
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00e2e-frame\xff\xd9"
SKU_NAME = "Vinamilk 100% Sữa Tươi Tiệt Trùng Không Đường 180ml"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return None


OPENER = urllib.request.build_opener(_NoRedirect)


class Response:
    def __init__(self, status: int, headers, body: bytes) -> None:
        self.status, self.headers, self.body = status, headers, body

    def json(self):
        return json.loads(self.body)


class Hub:
    def __init__(self, base_url: str, token: str) -> None:
        self.base = base_url.rstrip("/")
        self.token = token
        self.cookie = ""

    def request(
        self, method: str, path: str, body: dict | None = None, *, auth: bool = True, token: bool = False
    ) -> Response:
        headers = {"User-Agent": "milk-selfcheck"}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if auth and self.cookie:
            headers["Cookie"] = self.cookie
        if token:
            headers["X-Internal-Token"] = self.token
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with OPENER.open(request, timeout=30) as response:
                return Response(response.status, response.headers, response.read())
        except urllib.error.HTTPError as exc:
            return Response(exc.code, exc.headers, exc.read())


class Checks:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def run(self, name: str, check: Callable[[], str | None]) -> None:
        try:
            detail = check() or ""
        except Exception as exc:  # noqa: BLE001 - every failure is reported, then the next check runs
            self.failed += 1
            print(f"e2e_check name={name} result=fail error={type(exc).__name__}: {exc}", flush=True)
            return
        self.passed += 1
        print(f"e2e_check name={name} result=pass {detail}".rstrip(), flush=True)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def reset(s3, table, bucket: str) -> str:
    """Deletes every CAM-E2E capture from the table and the bucket."""
    from boto3.dynamodb.conditions import Key

    rows = 0
    kwargs = {"KeyConditionExpression": Key("camera_id").eq(CAMERA), "ProjectionExpression": "capture_id"}
    with table.batch_writer() as batch:
        while True:
            page = table.query(**kwargs)
            for item in page["Items"]:
                batch.delete_item(Key={"camera_id": CAMERA, "capture_id": item["capture_id"]})
                rows += 1
            if "LastEvaluatedKey" not in page:
                break
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    objects = 0
    for prefix in (f"frames/{CAMERA}/", f"results/{CAMERA}/"):
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
            keys = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
            if keys:
                s3.delete_objects(Bucket=bucket, Delete={"Objects": keys, "Quiet": True})
                objects += len(keys)
    return f"rows={rows} objects={objects}"


def main() -> int:
    s = config.load()
    expect(bool(s.bucket and s.table and s.internal_token and s.web_password), "storage and secrets must be set")
    import boto3

    s3 = boto3.client("s3", region_name=s.region)
    table = boto3.resource("dynamodb", region_name=s.region).Table(s.table)
    hub = Hub(s.hub_url, s.internal_token)
    checks = Checks()
    print(f"e2e_start hub={hub.base} environment={s.environment} version={s.version}", flush=True)

    tz = timezone(timedelta(hours=s.utc_offset_hours))
    ts = datetime.now(tz).replace(microsecond=0)
    detections = [
        Detection("TMP-MLK-VNM-01", SKU_NAME, 0.93, (10, 20, 30, 60)),
        Detection("TMP-MLK-VNM-01", SKU_NAME, 0.91, (50, 20, 30, 60)),
        Detection(None, None, 0.20, (90, 20, 30, 60)),
    ]
    rows, log_line = build_capture(
        detections,
        stem=CaptureIdAllocator().stem(s.store_code, ts),
        store_id=s.store_id,
        camera_id=CAMERA,
        capture_source="E2E",
        ts=ts,
        processing_time_ms=123,
        flag_threshold=s.flag_threshold,
    )
    capture_id = log_line["capture_id"]
    counts = counts_of(rows)
    day = ts.strftime("%Y-%m-%d")
    jpeg_b64 = base64.b64encode(JPEG).decode("ascii")

    checks.run("reset_before", lambda: reset(s3, table, s.bucket))

    def health() -> str:
        r = hub.request("GET", "/healthz", auth=False)
        expect(r.status == 200 and r.json().get("ok") is True, f"healthz answered {r.status}")
        served = r.json().get("version")
        expect(served == s.version, f"service runs {served}, this check is {s.version}")
        return f"version={served}"

    def access_control() -> str:
        expect(hub.request("GET", "/", auth=False).status == 303, "dashboard without login is not a redirect")
        expect(hub.request("GET", "/api/live", auth=False).status == 401, "API without login is not 401")
        status = hub.request("POST", "/internal/status", {"camera_id": CAMERA}).status
        expect(status == 403, f"internal endpoint without token answered {status}")
        wrong = hub.request("POST", "/api/login", {"password": "not-the-password"}, auth=False).status
        expect(wrong == 401, f"wrong password answered {wrong}")
        return "login and token enforced"

    def login() -> str:
        r = hub.request("POST", "/api/login", {"password": s.web_password}, auth=False)
        expect(r.status == 200, f"login answered {r.status}")
        cookie = r.headers.get("Set-Cookie", "")
        expect(cookie.startswith("milk_session="), "no session cookie")
        hub.cookie = cookie.split(";", 1)[0]
        return ""

    def worker_result() -> str:
        status = hub.request("POST", "/internal/status", {"camera_id": CAMERA, "worker": "selfcheck"}, token=True)
        expect(status.status == 200, f"status answered {status.status}")
        meta = {
            "camera_id": CAMERA,
            "store_id": s.store_id,
            "capture_id": capture_id,
            "capture_timestamp": log_line["capture_timestamp"],
            "received_at": time.time(),
            "processing_time_ms": 123,
            "latency_ms": 0,
            "frame_w": 128,
            "frame_h": 72,
            "display_w": 128,
            "display_h": 72,
            "roi": None,
            "detections": [
                {"sku_id": d.sku_id, "conf": d.confidence, "box": list(d.box), "flagged": d.sku_id is None}
                for d in detections
            ],
            "counts": counts,
            "smoothed": counts,
            "units": log_line["units_found"],
            "flagged_rows": log_line["flagged_rows"],
            "flagged": [
                {k: r[k] for k in ("sku_id", "sku_name", "unit_count", "confidence_score", "flag_reason")}
                for r in rows
                if r["is_flagged"]
            ],
            "faces_blurred": 0,
            "pipeline": "selfcheck",
        }
        r = hub.request("POST", "/internal/result", {"meta": meta, "jpeg_b64": jpeg_b64}, token=True)
        expect(r.status == 200, f"result answered {r.status}")
        return f"capture_id={capture_id}"

    def live_view() -> str:
        live = hub.request("GET", f"/api/live?camera={CAMERA}&after=0").json()
        expect(live["meta"]["capture_id"] == capture_id, "live shows another capture")
        expect(live["status"]["worker_ok"] is True, "worker not shown as connected")
        expect(hub.request("GET", f"/api/frame?camera={CAMERA}").body == JPEG, "frame differs")
        history = hub.request("GET", f"/api/history?camera={CAMERA}&minutes=5").json()
        expect(bool(history) and history[-1]["total"] == log_line["units_found"], "history total differs")
        flags = hub.request("GET", f"/api/flags?camera={CAMERA}").json()
        expect(bool(flags) and flags[0]["flag_reason"] == "Unrecognized", "flag missing")
        return f"units={log_line['units_found']}"

    def persisted() -> str:
        record = {**log_line, "rows": rows, "log": log_line, "counts": counts, "latency_ms": 0}
        r = hub.request("POST", "/internal/persist", {"record": record, "jpeg_b64": jpeg_b64}, token=True)
        expect(r.status == 202, f"persist answered {r.status}")
        deadline = time.time() + 60
        item = None
        while time.time() < deadline and item is None:
            item = table.get_item(Key={"camera_id": CAMERA, "capture_id": capture_id}).get("Item")
            if item is None:
                time.sleep(2)
        expect(item is not None, "capture not in DynamoDB after 60 s")
        prefix = f"{CAMERA}/{log_line['capture_timestamp'][:10]}"
        s3.head_object(Bucket=s.bucket, Key=f"results/{prefix}/{capture_id}.json")
        s3.head_object(Bucket=s.bucket, Key=f"frames/{prefix}/{log_line['image_filename']}")
        return "s3 and dynamodb"

    def export(path: str, records: list[dict], columns: list[str]) -> Callable[[], str]:
        def check() -> str:
            r = hub.request("GET", f"{path}?camera={CAMERA}&date={day}")
            expect(r.status == 200, f"export answered {r.status}")
            expect(r.body == to_csv(records, columns).encode("utf-8"), "CSV differs from cvoutput")
            return f"bytes={len(r.body)}"

        return check

    def pages() -> str:
        for path in ("/", "/login", "/static/app.js", "/static/style.css", "/api/skus"):
            r = hub.request("GET", path)
            expect(r.status == 200, f"{path} answered {r.status}")
        return "5 pages"

    checks.run("health", health)
    checks.run("access_control", access_control)
    checks.run("login", login)
    checks.run("worker_result", worker_result)
    checks.run("live_frame_history_flags", live_view)
    checks.run("persist_s3_dynamodb", persisted)
    checks.run("export_cv_output", export("/api/export/cv-output.csv", rows, CV_OUTPUT_COLUMNS))
    checks.run("export_capture_log", export("/api/export/capture-log.csv", [log_line], CAPTURE_LOG_COLUMNS))
    checks.run("pages", pages)
    checks.run("reset_after", lambda: reset(s3, table, s.bucket))

    print(f"e2e_summary passed={checks.passed} failed={checks.failed}", flush=True)
    return 1 if checks.failed else 0


if __name__ == "__main__":
    sys.exit(main())
