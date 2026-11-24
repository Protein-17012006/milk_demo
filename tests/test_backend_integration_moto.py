"""Integration tests with mocked AWS (moto) matching KHANG-T001 CI conventions."""

from __future__ import annotations

import importlib.util
import json
import random
import sys
import urllib.parse
from decimal import Decimal
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from datetime import UTC

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
        ("test-audits", "store_id", "audit_id"),
        ("test-model-health", "camera_id", "hour"),
        ("test-shelf", "store_id", "key"),
        ("test-shelf-events", "store_id", "event_key"),
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
    for bucket in ("test-analytics-bucket", "test-hub-bucket"):
        s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": region})


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
        "AUDITS_TABLE": "test-audits",
        "MODEL_HEALTH_TABLE": "test-model-health",
        "SHELF_TABLE": "test-shelf",
        "SHELF_EVENTS_TABLE": "test-shelf-events",
        "ANALYTICS_BUCKET": "test-analytics-bucket",
        "HUB_BUCKET": "test-hub-bucket",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    _create_mock_infra(region)
    api = _load_module("moto_api_handler", ROOT / "backend" / "api" / "handler.py")
    ingest = _load_module("moto_ingest_handler", ROOT / "backend" / "ingest" / "handler.py")
    assert api.lambda_handler(_auth_event("POST", "/v1/admin/seed", groups="team_admin"))["statusCode"] == 200
    return api, ingest


def _ingest(
    ingest,
    camera_id: str,
    hhmmss: str,
    counts: list[tuple[str, int]],
    *,
    detections=None,
    model_version=None,
    with_frame: bool = False,
    display_visible: bool | None = None,
    display_score: float | None = None,
) -> None:
    """Ingest one hub result of store DEMO-S01 taken on 21/11 at hhmmss (may carry a -2 suffix); counts are
    (model label, units). with_frame puts a fake frame in the hub bucket, as the hub does. display_visible sets
    the worker's field (False also sets a low display_score); None leaves it out, as old workers did. display_score
    sets the worker's score, as a worker that has learnt the display sends it."""
    capture_id = f"CAP-S01-20261121-{hhmmss}"
    ts = f"2026-11-21T{hhmmss[:2]}:{hhmmss[2:4]}:{hhmmss[4:6]}+07:00"
    image = f"{camera_id}_20261121_{hhmmss}.jpg"
    image_key = f"frames/{camera_id}/2026-11-21/{image}" if with_frame else ""
    if with_frame:
        boto3.client("s3", region_name="ap-southeast-1").put_object(
            Bucket="test-hub-bucket", Key=image_key, Body=f"jpeg {hhmmss}".encode()
        )
    head = {
        "capture_id": capture_id,
        "store_id": "DEMO-S01",
        "camera_id": camera_id,
        "capture_timestamp": ts,
        "capture_source": "CCTV",
        "image_filename": image,
    }
    rows = [
        {
            **head,
            "reading_id": f"RD-S01-20261121-{hhmmss}-{i:03d}",
            "sku_id": label,
            "sku_name": label,
            "unit_count": units,
            "confidence_score": 0.9,
            "detection_method": "Visual",
            "bounding_box": [[10 + 60 * k, 20, 50, 80] for k in range(units)],
            "is_flagged": False,
            "flag_reason": "",
            "processing_time_ms": 20,
        }
        for i, (label, units) in enumerate(counts, start=1)
    ]
    total = sum(units for _, units in counts)
    record = {
        **head,
        "image_key": image_key,
        "processing_time_ms": 20,
        "units_found": total,
        "flagged_rows": 0,
        "rows": rows,
        "log": {**head, "units_found": total, "rows_written": len(rows), "flagged_rows": 0, "processing_time_ms": 20},
    }
    if detections is not None:
        record["detections"] = detections
    if model_version is not None:
        record["model_version"] = model_version
    if display_visible is not None:
        record["display_visible"] = display_visible
        if not display_visible:
            record["display_score"] = 0.2
    if display_score is not None:
        record["display_score"] = display_score
    normalized = ingest._normalize_record(record, source_bucket="test-hub-bucket")
    assert ingest.ingest_capture(normalized)["status"] == "ingested"


def _table(name: str):
    return boto3.resource("dynamodb", region_name="ap-southeast-1").Table(name)


@mock_aws
def test_previous_hour_is_in_ict(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    from datetime import datetime

    assert ingest.previous_hour(datetime(2026, 11, 23, 6, 24, tzinfo=UTC)) == "20261123-12"


@mock_aws
def test_capture_keeps_model_version_and_boxes(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    dets = [
        {"sku_id": "hot160", "conf": 0.87, "box": [948, 326, 72, 167]},
        {"sku_id": "hot160", "conf": 0.94, "box": [1190, 288, 74, 150]},
    ]
    _ingest(ingest, "CAM-S01-A", "140700", [("hot160", 2)], detections=dets, model_version="v3")
    _ingest(ingest, "CAM-S01-A", "140710", [("hot160", 2)])
    new = _table("test-captures").get_item(Key={"camera_id": "CAM-S01-A", "capture_id": "CAP-S01-20261121-140700"})[
        "Item"
    ]
    old = _table("test-captures").get_item(Key={"camera_id": "CAM-S01-A", "capture_id": "CAP-S01-20261121-140710"})[
        "Item"
    ]
    assert new["model_version"] == "v3" and json.loads(new["detections_json"]) == dets
    assert old["model_version"] == "unknown" and "detections_json" not in old


@mock_aws
def test_hourly_sampling_picks_one_frame_and_copies_it(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    for t in ("140700", "140710", "140710-2"):
        _ingest(ingest, "CAM-S01-A", t, [("hot160", 2)], with_frame=True)
    _ingest(ingest, "CAM-S01-A", "150000", [("hot160", 1)], with_frame=True)

    ingest.lambda_handler({"action": "sample_audits", "hour": "20261121-14"})

    audits = _table("test-audits").scan()["Items"]
    assert sorted(a["audit_id"] for a in audits) == ["AUD-CAM-S01-A-20261121-14", "TRN-CAM-S01-A-20261121-14"]
    audit = next(a for a in audits if a["audit_id"].startswith("AUD-"))
    assert audit["status"] == "pending"
    assert audit["capture_id"] in {"CAP-S01-20261121-140700", "CAP-S01-20261121-140710", "CAP-S01-20261121-140710-2"}
    assert [b["box"] for b in json.loads(audit["ai_boxes_json"])] == [[10, 20, 50, 80], [70, 20, 50, 80]]
    assert audit["image_key"].startswith("audits/frames/CAM-S01-A/2026-11-21/CAM-S01-A_20261121_14")
    copied = (
        boto3.client("s3", region_name="ap-southeast-1")
        .get_object(Bucket="test-analytics-bucket", Key=audit["image_key"])["Body"]
        .read()
    )
    assert copied == f"jpeg {audit['capture_id'].rsplit('20261121-', 1)[1]}".encode()


@mock_aws
def test_sampling_the_same_hour_twice_keeps_one_audit(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    for t in ("140700", "140710"):
        _ingest(ingest, "CAM-S01-A", t, [("hot160", 2)], with_frame=True)
    ingest.lambda_handler({"action": "sample_audits", "hour": "20261121-14"})
    first = _table("test-audits").get_item(Key={"store_id": "DEMO-S01", "audit_id": AUDIT_14})["Item"]["capture_id"]
    ingest.lambda_handler({"action": "sample_audits", "hour": "20261121-14"})
    audits = _table("test-audits").scan()["Items"]
    assert len(audits) == 2 and {a["audit_id"]: a["capture_id"] for a in audits}[AUDIT_14] == first


@mock_aws
def test_an_hour_whose_captures_have_no_frame_gets_no_audit(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    for t in ("140700", "140710"):
        _ingest(ingest, "CAM-S01-A", t, [("hot160", 2)])
    ingest.lambda_handler({"action": "sample_audits", "hour": "20261121-14"})
    assert _table("test-audits").scan()["Items"] == []


@mock_aws
def test_health_item_for_the_hour(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    for t in ("140700", "140710", "140710-2"):
        _ingest(ingest, "CAM-S01-A", t, [("hot160", 2)], with_frame=True)
    ingest.lambda_handler({"action": "sample_audits", "hour": "20261121-14"})
    item = _table("test-model-health").get_item(Key={"camera_id": "CAM-S01-A", "hour": "20261121-14"})["Item"]
    assert item["captures"] == 3 and item["expires_at"] > 0


@mock_aws
def test_the_hourly_run_samples_before_the_official_pick(monkeypatch: pytest.MonkeyPatch):
    # the official pick scans the whole captures table; if it fails as the table grows, the hour must
    # already have its frame to label
    _, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "140700", [("hot160", 2)], with_frame=True)
    monkeypatch.setattr(ingest, "previous_hour", lambda now: "20261121-14")

    def broken(*_args):
        raise MemoryError("captures table too large")

    monkeypatch.setattr(ingest, "_handle_hourly_official", broken)
    with pytest.raises(MemoryError):
        ingest.lambda_handler({"source": "aws.events"})
    assert [a["audit_id"] for a in _table("test-audits").scan()["Items"]] == ["AUD-CAM-S01-A-20261121-14"]


@mock_aws
def test_backfill_writes_health_for_past_hours(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "140700", [("hot160", 2)])
    _ingest(ingest, "CAM-S01-A", "150000", [("hot160", 1)])
    ingest.lambda_handler({"action": "backfill_model_health", "days": 1, "until": "20261121-16"})
    hours = sorted(i["hour"] for i in _table("test-model-health").scan()["Items"])
    assert hours == ["20261121-14", "20261121-15"]


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
def test_seeded_skus_reach_the_website_with_their_own_photo(monkeypatch: pytest.MonkeyPatch):
    api, _ = _backend(monkeypatch)
    resp = api.lambda_handler(_auth_event("GET", "/v1/products"))
    images = {p["sku_id"]: p["image_url"] for p in json.loads(resp["body"])["items"]}

    assert images[TH_SWEET] == "/images/products/th-true-milk-fresh-milk-sweetened-180ml.png"
    assert images[TH_LOW] == "/images/products/th-true-milk-fresh-milk-low-sugar-180ml.png"
    assert images["Slide Cheese 145g"] == "/images/products/slide-cheese-145g.png"


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


AUDIT_14 = "AUD-CAM-S01-A-20261121-14"


def _one_pending_audit(ingest, counts=(("hot160", 2),)) -> None:
    """A stock row for the camera at 13:00, then one capture with a frame at 14:07, sampled into an audit."""
    _ingest(ingest, "CAM-S01-A", "130000", [("hot160", 1)])
    _ingest(ingest, "CAM-S01-A", "140700", list(counts), with_frame=True)
    ingest.lambda_handler({"action": "sample_audits", "hour": "20261121-14"})


def _call(api, method: str, path: str, groups: str = "field_team", body=None, query=None) -> tuple[int, dict]:
    resp = api.lambda_handler(_auth_event(method, path, groups=groups, body=body, query=query))
    return resp["statusCode"], json.loads(resp["body"])


TRN_14 = "TRN-CAM-S01-A-20261121-14"


def _audits() -> dict[str, dict]:
    return {i["audit_id"]: i for i in _table("test-audits").scan()["Items"]}


@mock_aws
def test_an_hour_gives_a_scoring_frame_and_a_training_frame(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "140700", [("hot160", 2)], with_frame=True)
    _ingest(ingest, "CAM-S01-A", "141200", [("hot160", 2)], with_frame=True)
    ingest.lambda_handler({"action": "sample_audits", "hour": "20261121-14"})
    a = _audits()
    assert set(a) == {AUDIT_14, TRN_14}
    assert a[AUDIT_14]["capture_id"] != a[TRN_14]["capture_id"]
    assert (a[AUDIT_14]["purpose"], a[TRN_14]["purpose"]) == ("scoring", "training")


@mock_aws
def test_sampling_an_hour_again_creates_nothing_and_keeps_the_scoring_frame(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "140700", [("hot160", 2)], with_frame=True)
    _ingest(ingest, "CAM-S01-A", "141200", [("hot160", 2)], with_frame=True)
    ingest.lambda_handler({"action": "sample_audits", "hour": "20261121-14"})
    first = _audits()
    again = ingest.lambda_handler({"action": "sample_audits", "hour": "20261121-14"})
    second = _audits()
    assert again["audits"] == []
    assert set(second) == {AUDIT_14, TRN_14}
    assert second[AUDIT_14]["capture_id"] != second[TRN_14]["capture_id"]
    assert second[AUDIT_14]["capture_id"] == first[AUDIT_14]["capture_id"]


@mock_aws
def test_training_frames_only_come_from_captures_that_see_the_display(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "130000", [("hot160", 1)])  # a stock row, so the camera is known
    _ingest(ingest, "CAM-S01-A", "140700", [], with_frame=True, display_visible=False)
    ingest.lambda_handler({"action": "sample_audits", "hour": "20261121-14"})
    a = _audits()
    assert set(a) == {AUDIT_14} and a[AUDIT_14]["display_visible"] is False  # scored frames are not filtered


@mock_aws
def test_the_training_frame_is_never_a_capture_that_hides_the_display(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    visible = "CAP-S01-20261121-140700"
    _ingest(ingest, "CAM-S01-A", "140700", [("hot160", 2)], with_frame=True, display_visible=True)
    _ingest(ingest, "CAM-S01-A", "141200", [("hot160", 2)], with_frame=True, display_visible=False)
    _ingest(ingest, "CAM-S01-A", "141700", [("hot160", 2)], with_frame=True, display_visible=False)
    s3, ddb = ingest._aws_clients()
    items = ingest.captures_in_hour(ddb, "CAM-S01-A", "S01", "20261121-14")
    outcomes = set()
    for seed in range(20):
        for audit_id in _audits():
            _table("test-audits").delete_item(Key={"store_id": "DEMO-S01", "audit_id": audit_id})
        ingest.sample_frames(s3, ddb, "CAM-S01-A", items, "20261121-14", random.Random(seed), None)
        a = _audits()
        if a[AUDIT_14]["capture_id"] == visible:
            assert set(a) == {AUDIT_14}  # the scoring frame took the only visible capture: no training frame
            outcomes.add("no training frame")
        else:
            assert a[TRN_14]["capture_id"] == visible
            outcomes.add("training frame")
    assert outcomes == {"no training frame", "training frame"}


@mock_aws
def test_frames_outside_opening_hours_are_not_sampled(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    _shelf_plan(open_time="06:00", close_time="14:00")
    _ingest(ingest, "CAM-S01-A", "140700", [("hot160", 2)], with_frame=True)
    ingest.lambda_handler({"action": "sample_audits", "hour": "20261121-14"})
    assert _audits() == {}


@mock_aws
def test_a_frame_to_label_keeps_the_display_score_of_its_capture(monkeypatch: pytest.MonkeyPatch):
    # the Model page's display check counts only frames the worker's check judged, so the score goes on the audit
    _, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "140700", [("hot160", 2)], with_frame=True, display_visible=True, display_score=0.91)
    ingest.lambda_handler({"action": "sample_audits", "hour": "20261121-14"})
    audit = _audits()[AUDIT_14]
    assert (audit["display_visible"], audit["display_score"]) == (True, Decimal("0.91"))
    # no score on the capture (an older worker, or none learnt yet): none on the audit either
    _ingest(ingest, "CAM-S01-A", "150700", [("hot160", 2)], with_frame=True)
    ingest.lambda_handler({"action": "sample_audits", "hour": "20261121-15"})
    audit = _audits()["AUD-CAM-S01-A-20261121-15"]
    assert audit["display_visible"] is True and "display_score" not in audit


@mock_aws
def test_ingest_keeps_the_display_fields_and_old_records_mean_visible(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "140700", [], display_visible=False)
    _ingest(ingest, "CAM-S01-A", "141200", [])
    items = {i["capture_id"]: i for i in _table("test-captures").scan()["Items"]}
    hidden, old = items["CAP-S01-20261121-140700"], items["CAP-S01-20261121-141200"]
    assert hidden["display_visible"] is False and float(hidden["display_score"]) == 0.2
    assert old["display_visible"] is True and "display_score" not in old


@mock_aws
def test_summary_and_top_50_ignore_training_frames(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "140700", [("hot160", 2)], with_frame=True)
    _ingest(ingest, "CAM-S01-A", "141200", [("hot160", 2)], with_frame=True)
    ingest.lambda_handler({"action": "sample_audits", "hour": "20261121-14"})
    body = {
        "verdicts": [{"box_id": 1, "verdict": "correct"}, {"box_id": 2, "verdict": "correct"}],
        "missed": [],
        "misses_checked": True,
    }
    assert _call(api, "PUT", f"/v1/model/audits/{TRN_14}", body=body)[0] == 200
    _, summary = _call(api, "GET", "/v1/model/summary", query={"days": "0"})
    assert summary["n_audits"] == 0
    _, items = _call(api, "GET", "/v1/model/audits", query={"days": "0"})
    assert {i["audit_id"]: i["purpose"] for i in items["items"]} == {AUDIT_14: "scoring", TRN_14: "training"}


@mock_aws
def test_an_old_audit_without_purpose_counts_by_its_id(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _one_pending_audit(ingest)
    _table("test-audits").update_item(
        Key={"store_id": "DEMO-S01", "audit_id": AUDIT_14}, UpdateExpression="REMOVE purpose"
    )
    body = {
        "verdicts": [{"box_id": 1, "verdict": "correct"}, {"box_id": 2, "verdict": "correct"}],
        "missed": [],
        "misses_checked": True,
    }
    assert _call(api, "PUT", f"/v1/model/audits/{AUDIT_14}", body=body)[0] == 200
    assert _call(api, "GET", "/v1/model/summary", query={"days": "0"})[1]["n_audits"] == 1
    items = _call(api, "GET", "/v1/model/audits", query={"days": "0"})[1]["items"]
    assert [i["purpose"] for i in items] == ["scoring"]


@mock_aws
def test_datagent_cannot_open_model_routes(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _one_pending_audit(ingest)
    for method, path in (
        ("GET", "/v1/model/audits"),
        ("GET", f"/v1/model/audits/{AUDIT_14}"),
        ("PUT", f"/v1/model/audits/{AUDIT_14}"),
        ("POST", f"/v1/model/audits/{AUDIT_14}/skip"),
        ("GET", "/v1/model/summary"),
        ("GET", "/v1/model/health"),
    ):
        assert _call(api, method, path, groups="datagent", body={})[0] == 403


@mock_aws
def test_list_and_detail_for_field_team(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _one_pending_audit(ingest)
    status, listing = _call(api, "GET", "/v1/model/audits", query={"status": "pending", "days": "0"})
    assert status == 200
    assert [i["audit_id"] for i in listing["items"]] == [AUDIT_14]
    assert listing["counts"] == {"pending": 1, "done": 0, "skipped": 0}
    status, detail = _call(api, "GET", f"/v1/model/audits/{AUDIT_14}")
    assert status == 200 and detail["frame_url"]
    assert len(detail["ai_boxes"]) == 2
    assert {"label": "hot160", "name": "Slide Hot & Spicy 160g"} in detail["sku_choices"]


@mock_aws
def test_saving_labels_marks_the_audit_done(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _one_pending_audit(ingest)
    body = {
        "verdicts": [
            {"box_id": 1, "verdict": "correct"},
            {"box_id": 2, "verdict": "wrong_sku", "true_sku_id": "original145"},
        ],
        "missed": [{"sku_id": "hot160", "x": 5, "y": 5}],
        "misses_checked": True,
    }
    status, saved = _call(api, "PUT", f"/v1/model/audits/{AUDIT_14}", body=body)
    assert status == 200
    assert saved["status"] == "done" and saved["labeled_by"] == "tester@datagent.io"
    assert saved["verdicts"] == body["verdicts"] and saved["missed"] == body["missed"]


@mock_aws
def test_saving_without_a_verdict_for_every_box_is_refused(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _one_pending_audit(ingest)
    status, err = _call(
        api,
        "PUT",
        f"/v1/model/audits/{AUDIT_14}",
        body={"verdicts": [{"box_id": 1, "verdict": "correct"}], "missed": [], "misses_checked": True},
    )
    assert status == 400 and err["error"] == "INVALID_LABELS" and "box 2 has no verdict" in err["message"]
    assert _call(api, "GET", f"/v1/model/audits/{AUDIT_14}")[1]["status"] == "pending"


@mock_aws
def test_skip_needs_a_known_reason(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _one_pending_audit(ingest)
    assert _call(api, "POST", f"/v1/model/audits/{AUDIT_14}/skip", body={"reason": "rain"})[0] == 400
    status, skipped = _call(api, "POST", f"/v1/model/audits/{AUDIT_14}/skip", body={"reason": "blocked"})
    assert status == 200 and skipped["status"] == "skipped" and skipped["skip_reason"] == "blocked"


@mock_aws
def test_a_frame_without_boxes_is_saved_with_misses_only(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _one_pending_audit(ingest, counts=())
    assert _call(api, "GET", f"/v1/model/audits/{AUDIT_14}")[1]["ai_boxes"] == []
    status, saved = _call(
        api,
        "PUT",
        f"/v1/model/audits/{AUDIT_14}",
        body={"verdicts": [], "missed": [{"sku_id": "hot160", "x": 1, "y": 1}], "misses_checked": True},
    )
    assert status == 200 and saved["status"] == "done"


@mock_aws
def test_saving_needs_the_missed_cans_check(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _one_pending_audit(ingest)  # two hot160 boxes
    labels = {"verdicts": [{"box_id": 1, "verdict": "correct"}, {"box_id": 2, "verdict": "out_of_scope"}], "missed": []}
    status, body = _call(api, "PUT", f"/v1/model/audits/{AUDIT_14}", body=labels)
    assert status == 400 and "misses_checked" in body["message"]
    status, body = _call(api, "PUT", f"/v1/model/audits/{AUDIT_14}", body={**labels, "misses_checked": True})
    assert status == 200 and (body["label_rule"], body["misses_checked"]) == ("A", True)


@mock_aws
def test_a_frame_without_the_display_is_skipped_as_display_away(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _one_pending_audit(ingest)
    status, body = _call(api, "POST", f"/v1/model/audits/{AUDIT_14}/skip", body={"reason": "display_away"})
    assert status == 200 and body["skip_reason"] == "display_away"


@mock_aws
def test_summary_counts_frames_labelled_before_rule_a(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _one_pending_audit(ingest)
    _table("test-audits").update_item(  # labelled on 24/11 before rule A existed: done, no label_rule
        Key={"store_id": "DEMO-S01", "audit_id": AUDIT_14},
        UpdateExpression="SET #s = :done, verdicts_json = :v",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":done": "done",
            ":v": '[{"box_id":1,"verdict":"correct"},{"box_id":2,"verdict":"correct"}]',
        },
    )
    assert _call(api, "GET", "/v1/model/summary", query={"days": "0"})[1]["old_rule_frames"] == 1


@mock_aws
def test_an_unknown_audit_is_not_found(monkeypatch: pytest.MonkeyPatch):
    api, _ = _backend(monkeypatch)
    assert _call(api, "GET", "/v1/model/audits/AUD-NOPE")[0] == 404


@mock_aws
def test_summary_without_labelled_frames_has_no_numbers(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _one_pending_audit(ingest)
    status, summary = _call(api, "GET", "/v1/model/summary", query={"days": "0"})
    assert status == 200 and summary["n_audits"] == 0
    assert all(
        k["value"] is None and k["n"] == 0 for name, k in summary["kpis"].items() if name != "avg_processing_time_ms"
    )  # speed comes from hourly health, not from labels


@mock_aws
def test_summary_after_labelling_one_frame(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "130000", [("hot160", 1)])
    _ingest(ingest, "CAM-S01-A", "140700", [("hot160", 2)], model_version="v3", with_frame=True)
    ingest.lambda_handler({"action": "sample_audits", "hour": "20261121-14"})
    _call(
        api,
        "PUT",
        f"/v1/model/audits/{AUDIT_14}",
        body={
            "verdicts": [
                {"box_id": 1, "verdict": "correct"},
                {"box_id": 2, "verdict": "wrong_sku", "true_sku_id": "original145"},
            ],
            "missed": [],
            "misses_checked": True,
        },
    )
    status, summary = _call(api, "GET", "/v1/model/summary", query={"days": "0"})
    assert status == 200 and summary["n_audits"] == 1
    assert summary["kpis"]["overall_identification_accuracy"]["value"] == 0.5
    assert summary["model_versions"] == ["v3"]
    assert summary["kpis"]["avg_processing_time_ms"]["value"] == 20  # every capture of hour 14 took 20 ms


@mock_aws
def test_summary_for_a_version_without_frames(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _one_pending_audit(ingest)
    _call(
        api,
        "PUT",
        f"/v1/model/audits/{AUDIT_14}",
        body={
            "verdicts": [{"box_id": 1, "verdict": "correct"}, {"box_id": 2, "verdict": "correct"}],
            "missed": [],
            "misses_checked": True,
        },
    )
    status, summary = _call(api, "GET", "/v1/model/summary", query={"days": "0", "model_version": "v9"})
    assert status == 200 and summary["n_audits"] == 0
    assert summary["kpis"]["overall_identification_accuracy"]["value"] is None


@mock_aws
def test_health_lists_hours_in_order(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "150000", [("hot160", 1)])
    _ingest(ingest, "CAM-S01-A", "140700", [("hot160", 2)])
    ingest.lambda_handler({"action": "backfill_model_health", "days": 1, "until": "20261121-16"})
    status, health = _call(api, "GET", "/v1/model/health", query={"days": "0"})
    assert status == 200
    assert [(h["camera_id"], h["hour"], h["captures"]) for h in health["items"]] == [
        ("CAM-S01-A", "20261121-14", 1),
        ("CAM-S01-A", "20261121-15", 1),
    ]


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


# --- Dashboard shelf metrics (spec docs/superpowers/specs/2026-11-24-dashboard-shelf-metrics-design.md) ---

CHEESE = "Slide Cheese 145g"
HOT = "Slide Hot & Spicy 160g"


def _shelf_plan(open_time="06:00", close_time="22:00", expected=(CHEESE,), **extra) -> None:
    """Give DEMO-S01 opening hours and expected SKUs, as the Settings page will."""
    fields = {"open_time": open_time, "close_time": close_time, "expected_skus": list(expected), **extra}
    _table("test-store-list").update_item(
        Key={"store_id": "DEMO-S01"},
        UpdateExpression="SET " + ", ".join(f"#{k} = :{k}" for k in fields),
        ExpressionAttributeNames={f"#{k}": k for k in fields},
        ExpressionAttributeValues={f":{k}": v for k, v in fields.items()},
    )


def _cheese_then_empty(ingest) -> None:
    """5 cans at 14:00 and 14:05, none at 14:10 and 14:15 (21/11)."""
    for hhmmss, units in [("140010", 5), ("140510", 5), ("141010", 0), ("141510", 0)]:
        _ingest(ingest, "CAM-S01-A", hhmmss, [("cheese145", units)] if units else [])


def _tick(ingest, now="2026-11-21T14:22:00+07:00") -> dict:
    return ingest.lambda_handler({"action": "shelf_tick", "now": now})


def _shelf(key: str) -> dict | None:
    return _table("test-shelf").get_item(Key={"store_id": "DEMO-S01", "key": key}).get("Item")


def _event_keys() -> list[str]:
    return sorted(i["event_key"] for i in _table("test-shelf-events").scan()["Items"])


@mock_aws
def test_shelf_tick_finds_an_out_of_stock(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    _shelf_plan()
    _cheese_then_empty(ingest)
    _tick(ingest)
    assert _event_keys() == [f"20261121-1410#{CHEESE}#OOS"]


@mock_aws
def test_shelf_tick_twice_counts_once(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    _shelf_plan()
    _cheese_then_empty(ingest)
    _tick(ingest)
    _tick(ingest)
    assert _shelf("hour#20261121-14")["skus"][CHEESE]["checks"] == 4
    assert _event_keys() == [f"20261121-1410#{CHEESE}#OOS"]


@mock_aws
def test_a_bucket_closed_under_two_minutes_waits(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    _shelf_plan()
    _cheese_then_empty(ingest)
    _tick(ingest, now="2026-11-21T14:21:30+07:00")
    assert _shelf("state")["last_bucket"] == "20261121-1410"


@mock_aws
def test_closed_hours_do_not_count(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    _shelf_plan(close_time="14:10")
    _cheese_then_empty(ingest)
    _tick(ingest)
    assert _event_keys() == []
    assert _shelf("hour#20261121-14")["checks"] == 2


@mock_aws
def test_a_saved_plan_is_recomputed_on_the_next_tick(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    _shelf_plan()
    _cheese_then_empty(ingest)
    _tick(ingest)
    _shelf_plan(expected=(CHEESE, HOT), shelf_recompute_requested_at="2026-11-21T14:22:30+07:00")
    _tick(ingest)
    store = _table("test-store-list").get_item(Key={"store_id": "DEMO-S01"})["Item"]
    assert "shelf_recompute_requested_at" not in store
    hot = _shelf("hour#20261121-14")["skus"][HOT]
    assert (hot["checks"], hot["available"]) == (4, 0)
    assert _event_keys() == [f"20261121-1410#{CHEESE}#OOS"]


PLAN_PATH = "/v1/stores/DEMO-S01/shelf-plan"


def _at(api, monkeypatch: pytest.MonkeyPatch, iso: str) -> None:
    from datetime import datetime

    monkeypatch.setattr(api, "_now", lambda: datetime.fromisoformat(iso))


@mock_aws
def test_shelf_plan_starts_as_the_suggestion(monkeypatch: pytest.MonkeyPatch):
    api, _ = _backend(monkeypatch)
    _at(api, monkeypatch, "2026-11-21T15:00:00+07:00")
    _table("test-shelf").put_item(Item={"store_id": "DEMO-S01", "key": "day#20261121", "confident_skus": [CHEESE]})
    status, body = _call(api, "GET", PLAN_PATH)
    assert status == 200 and body["source"] == "suggested"
    assert body["expected_skus"] == [CHEESE] == [s["sku_id"] for s in body["suggested"]]
    assert body["suggested"][0]["last_seen"] == "2026-11-21"


@mock_aws
def test_only_team_admin_saves_a_shelf_plan(monkeypatch: pytest.MonkeyPatch):
    api, _ = _backend(monkeypatch)
    plan = {"open_time": "06:00", "close_time": "22:00", "expected_skus": [CHEESE]}
    assert _call(api, "PUT", PLAN_PATH, groups="datagent", body=plan)[0] == 403
    status, body = _call(api, "PUT", PLAN_PATH, groups="team_admin", body=plan)
    assert status == 200 and body["source"] == "saved" and body["expected_skus"] == [CHEESE]
    assert (body["open_time"], body["close_time"]) == ("06:00", "22:00")


@mock_aws
def test_shelf_plan_rejects_bad_hours_and_unknown_skus(monkeypatch: pytest.MonkeyPatch):
    api, _ = _backend(monkeypatch)
    for open_time, close_time in [("22:00", "06:00"), ("6:00", "22:00")]:
        body = {"open_time": open_time, "close_time": close_time, "expected_skus": [CHEESE]}
        status, out = _call(api, "PUT", PLAN_PATH, groups="team_admin", body=body)
        assert (status, out["error"]) == (400, "INVALID_HOURS")
    body = {"open_time": "06:00", "close_time": "22:00", "expected_skus": [CHEESE, "No Such Milk"]}
    status, out = _call(api, "PUT", PLAN_PATH, groups="team_admin", body=body)
    assert (status, out["error"], out["skus"]) == (400, "UNKNOWN_SKU", ["No Such Milk"])
    store = _table("test-store-list").get_item(Key={"store_id": "DEMO-S01"})["Item"]
    assert "open_time" not in store and "expected_skus" not in store


@mock_aws
def test_saving_a_plan_asks_for_a_recompute(monkeypatch: pytest.MonkeyPatch):
    api, _ = _backend(monkeypatch)
    _at(api, monkeypatch, "2026-11-21T15:00:00+07:00")
    body = {"open_time": "06:00", "close_time": "22:00", "expected_skus": [CHEESE]}
    assert _call(api, "PUT", PLAN_PATH, groups="team_admin", body=body)[0] == 200
    store = _table("test-store-list").get_item(Key={"store_id": "DEMO-S01"})["Item"]
    assert store["shelf_recompute_requested_at"] == "2026-11-21T15:00:00+07:00"
    assert store["shelf_plan_updated_by"] == "tester@datagent.io"


@mock_aws
def test_shelf_plan_of_an_unknown_store_is_not_found(monkeypatch: pytest.MonkeyPatch):
    api, _ = _backend(monkeypatch)
    status, body = _call(api, "GET", "/v1/stores/NOPE/shelf-plan")
    assert (status, body["error"]) == (404, "STORE_NOT_FOUND")


NOW = "2026-11-28T12:00:00+07:00"


def _put_shelf(key: str, **fields) -> None:
    _table("test-shelf").put_item(Item={"store_id": "DEMO-S01", "key": key, **fields})


def _rollup_item(checks: int, available: int, restock_units: int, units_sum: int = 0, max_total: int = 0) -> dict:
    """An hour# or day# rollup in which only Slide Cheese was expected."""
    sku = {
        "checks": checks,
        "available": available,
        "units_sum": units_sum,
        "oos_started": 0,
        "restock_units": restock_units,
        "restock_events": 1 if restock_units else 0,
    }
    return {"checks": checks, "max_total": max_total, "confident_skus": [CHEESE], "skus": {CHEESE: sku}}


def _kpi(api, **query) -> dict:
    status, body = _call(api, "GET", "/v1/kpi", groups="datagent", query=query)
    assert status == 200
    return body


@mock_aws
def test_kpi_osa_and_restock_rate_against_the_previous_period(monkeypatch: pytest.MonkeyPatch):
    api, _ = _backend(monkeypatch)
    _at(api, monkeypatch, NOW)
    _shelf_plan()
    _put_shelf("day#20261127", **_rollup_item(100, 64, 201))  # inside the last 14 days (15/11-28/11)
    _put_shelf("day#20261110", **_rollup_item(100, 60, 150))  # inside the 14 days before (01/11-14/11)
    kpi = _kpi(api, days="14")
    assert (kpi["osa"]["value"], kpi["osa"]["previous"], kpi["osa"]["blocked_reason"]) == (0.64, 0.6, None)
    r = kpi["restock_rate"]
    assert (r["units_per_day"], r["previous_units_per_day"], r["change_pct"], r["blocked_reason"]) == (
        14.4,
        10.7,
        34.0,
        None,
    )


@mock_aws
def test_a_store_without_hours_is_blocked_not_zero(monkeypatch: pytest.MonkeyPatch):
    api, _ = _backend(monkeypatch)
    _at(api, monkeypatch, NOW)
    _put_shelf("day#20261127", **_rollup_item(100, 64, 201))
    kpi = _kpi(api)
    assert (kpi["osa"]["value"], kpi["osa"]["blocked_reason"]) == (None, "no_hours")
    assert kpi["restock_rate"]["blocked_reason"] == "no_hours" and kpi["oos_now"]["blocked_reason"] == "no_hours"
    assert "total_on_shelf_units" in kpi and "captures_count" in kpi


@mock_aws
def test_kpi_capture_numbers_read_only_store_and_processing_time(monkeypatch: pytest.MonkeyPatch):
    """/kpi scans captures for two fields only (ProjectionExpression); the numbers must not change."""
    api, _ = _backend(monkeypatch)
    _at(api, monkeypatch, NOW)
    captures = _table("test-captures")
    for i, ms in enumerate((20, 40, 0)):  # 0 = unknown time, left out of the mean
        captures.put_item(
            Item={
                "camera_id": "CAM-S01-A",
                "capture_id": f"CAP-S01-20261128-11{i}000",
                "store_id": "DEMO-S01",
                "processing_time_ms": ms,
                "rows_json": "[]",
            }
        )
    kpi = _kpi(api)
    assert (kpi["captures_count"], kpi["active_stores_monitored"], kpi["avg_processing_time_ms"]) == (3, 1, 30)


@mock_aws
def test_stores_last_capture_reads_only_store_and_timestamp(monkeypatch: pytest.MonkeyPatch):
    """/stores scans captures for two fields only (ProjectionExpression); the latest capture must not change."""
    api, _ = _backend(monkeypatch)
    _table("test-store-list").put_item(Item={"store_id": "DEMO-S01", "store_name": "Demo Store S01"})
    _table("test-store-list").put_item(Item={"store_id": "DEMO-S02", "store_name": "Demo Store S02"})
    for ts in ("2026-11-24T08:45:10+07:00", "2026-11-24T09:05:40+07:00", "2026-11-23T22:00:28+07:00"):
        _table("test-captures").put_item(
            Item={
                "camera_id": "CAM-S01-A",
                "capture_id": f"CAP-S01-{ts[:10].replace('-', '')}-{ts[11:19].replace(':', '')}",
                "store_id": "DEMO-S01",
                "capture_timestamp": ts,
                "rows_json": "[]",
            }
        )
    status, body = _call(api, "GET", "/v1/stores", groups="datagent")
    by_id = {s["store_id"]: s for s in body["items"]}
    assert status == 200
    assert (by_id["DEMO-S01"]["last_capture_timestamp"], by_id["DEMO-S01"]["has_recent_capture"]) == (
        "2026-11-24T09:05:40+07:00",
        True,
    )
    assert (by_id["DEMO-S02"]["last_capture_timestamp"], by_id["DEMO-S02"]["has_recent_capture"]) == (None, False)


@mock_aws
def test_oos_now_counts_expected_skus_out_of_stock(monkeypatch: pytest.MonkeyPatch):
    api, _ = _backend(monkeypatch)
    _at(api, monkeypatch, NOW)
    _shelf_plan(expected=(CHEESE, HOT))
    skus = {CHEESE: {"status": "OOS"}, HOT: {"status": "IN_STOCK"}, TH_SWEET: {"status": "OOS"}}  # TH not expected
    _put_shelf("state", last_bucket="20261128-1150", skus=skus)
    oos = _kpi(api)["oos_now"]
    assert (oos["count"], oos["as_of"], oos["blocked_reason"]) == (1, "20261128-1150", None)


@mock_aws
def test_top_50_accuracy_needs_labelled_frames(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _at(api, monkeypatch, NOW)
    top = _kpi(api)["top_50_sku_accuracy"]
    assert (top["value"], top["n_frames"], top["blocked_reason"]) == (None, 0, "no_labels")
    _one_pending_audit(ingest)
    verdicts = [{"box_id": 1, "verdict": "correct"}, {"box_id": 2, "verdict": "correct"}]
    body = {"verdicts": verdicts, "missed": [], "misses_checked": True}
    assert _call(api, "PUT", f"/v1/model/audits/{AUDIT_14}", body=body)[0] == 200
    top = _kpi(api)["top_50_sku_accuracy"]
    assert (top["value"], top["n_frames"], top["blocked_reason"]) == (1.0, 1, None)
    assert top["scope_note"] == "All SKUs: Datagent has not sent a top-50 list yet"


@mock_aws
def test_trends_per_day_and_per_hour(monkeypatch: pytest.MonkeyPatch):
    api, _ = _backend(monkeypatch)
    _at(api, monkeypatch, NOW)
    _shelf_plan()
    _put_shelf("day#20261127", **_rollup_item(10, 8, 6, units_sum=40))
    _put_shelf("hour#20261128-09", **_rollup_item(4, 4, 2, units_sum=12))
    status, body = _call(
        api, "GET", "/v1/reports/trends", groups="datagent", query={"metric": "restock_volume", "days": "7"}
    )
    assert status == 200 and [p["t"] for p in body["points"]] == [f"2026-11-{d}" for d in range(22, 29)]
    assert {p["t"]: p["value"] for p in body["points"]} == {
        **{f"2026-11-{d}": None for d in range(22, 29)},
        "2026-11-27": 6,
    }
    body = _call(api, "GET", "/v1/reports/trends", groups="datagent", query={"metric": "total_stock", "days": "1"})[1]
    assert [p["t"] for p in body["points"]] == [f"20261128-{h:02d}" for h in range(13)]
    assert {p["t"]: p["value"] for p in body["points"]}["20261128-09"] == 3.0


@mock_aws
def test_shelf_events_filter_by_kind_and_category(monkeypatch: pytest.MonkeyPatch):
    api, _ = _backend(monkeypatch)
    _at(api, monkeypatch, NOW)
    for at, sku, kind, delta in [
        ("20261128-1000", CHEESE, "OOS", -5),
        ("20261128-1100", CHEESE, "RESTOCKED", 6),
        ("20261128-1105", TH_SWEET, "LOW_STOCK", -3),
    ]:
        item = {"type": kind, "sku_id": sku, "at": at, "delta": delta, "level_before": 5, "level_after": 5 + delta}
        _table("test-shelf-events").put_item(Item={"store_id": "DEMO-S01", "event_key": f"{at}#{sku}#{kind}", **item})

    def kinds(**query):
        return [
            (i["sku_id"], i["type"]) for i in _call(api, "GET", "/v1/shelf-events", "datagent", query=query)[1]["items"]
        ]

    assert kinds() == [(TH_SWEET, "LOW_STOCK"), (CHEESE, "RESTOCKED"), (CHEESE, "OOS")]
    assert kinds(kind="alerts") == [(TH_SWEET, "LOW_STOCK"), (CHEESE, "OOS")]
    assert kinds(kind="restocked") == [(CHEESE, "RESTOCKED")]
    assert kinds(category="Milk") == [(TH_SWEET, "LOW_STOCK")]
    first = _call(api, "GET", "/v1/shelf-events", "datagent", query={"limit": "2"})[1]
    assert len(first["items"]) == 2 and first["next_cursor"]
    assert (first["items"][0]["store_name"], first["items"][0]["sku_name"]) == ("Demo Store S01", TH_SWEET)
    rest = _call(api, "GET", "/v1/shelf-events", "datagent", query={"limit": "2", "cursor": first["next_cursor"]})[1]
    assert [i["type"] for i in rest["items"]] == ["OOS"] and rest["next_cursor"] is None


@mock_aws
def test_series_reads_day_rollups(monkeypatch: pytest.MonkeyPatch):
    api, _ = _backend(monkeypatch)
    _at(api, monkeypatch, NOW)
    _put_shelf("day#20261127", **_rollup_item(2, 2, 0, units_sum=8, max_total=7))
    status, body = _call(api, "GET", "/v1/reports/series", groups="datagent")
    assert status == 200
    assert body["series"] == [
        {"date": "2026-11-27", "avg_units": 4.0, "max_units": 7, "checks": 2, "unmeasured_hours": 0.0}
    ]


# --- Reliability: checks without the display are not measured, gaps (spec 2026-11-24-reliability 1.1c) ---


@mock_aws
def test_a_capture_without_the_display_leaves_the_shelf_numbers(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "140000", [("cheese145", 5)])
    _ingest(ingest, "CAM-S01-A", "140500", [], display_visible=False)
    assert _units(api)[CHEESE] == 5
    status = _shelf("display#CAM-S01-A")
    assert (status["visible"], status["since"]) == (False, "2026-11-21T14:05:00+07:00")


@mock_aws
def test_a_record_without_display_fields_still_updates_the_shelf_numbers(monkeypatch: pytest.MonkeyPatch):
    # workers older than the display check send neither field: their captures see the display, as before
    api, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "140000", [("cheese145", 5), ("hot160", 2)])
    _ingest(ingest, "CAM-S01-A", "140500", [("cheese145", 4)])
    units = _units(api)
    assert (units[CHEESE], units[HOT]) == (4, 0)  # updated, and a SKU the capture no longer shows counts down
    status = _shelf("display#CAM-S01-A")
    assert (status["visible"], status["since"], status["last_visible_at"]) == (
        True,
        "2026-11-21T14:00:00+07:00",
        "2026-11-21T14:05:00+07:00",
    )


@mock_aws
def test_a_late_older_capture_does_not_turn_the_display_status_back(monkeypatch: pytest.MonkeyPatch):
    # SQS and hub re-sends do not keep order: the status follows the newest capture applied
    _, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "140500", [("cheese145", 5)], display_visible=True)
    _ingest(ingest, "CAM-S01-A", "140000", [], display_visible=False)
    status = _shelf("display#CAM-S01-A")
    assert (status["visible"], status["since"], status["updated_at"]) == (
        True,
        "2026-11-21T14:05:00+07:00",
        "2026-11-21T14:05:00+07:00",
    )
    _ingest(ingest, "CAM-S01-A", "141000", [], display_visible=False)
    _ingest(ingest, "CAM-S01-A", "140700", [("cheese145", 5)], display_visible=True)  # late, but it saw the display
    status = _shelf("display#CAM-S01-A")
    assert (status["visible"], status["since"], status["last_visible_at"], status["updated_at"]) == (
        False,
        "2026-11-21T14:10:00+07:00",
        "2026-11-21T14:07:00+07:00",
        "2026-11-21T14:10:00+07:00",
    )


@mock_aws
def test_checks_without_the_display_make_no_out_of_stock(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    _shelf_plan()
    for hhmmss, units, seen in [("140010", 5, True), ("140510", 5, True), ("141010", 0, False), ("141510", 0, False)]:
        _ingest(ingest, "CAM-S01-A", hhmmss, [("cheese145", units)] if units else [], display_visible=seen)
    _tick(ingest)
    assert _event_keys() == [] and _shelf("hour#20261121-14")["unmeasured_checks"] == 2
    assert _shelf("check#20261121-1410")["unmeasured_reason"] == "display_not_visible"
    assert "unmeasured_reason" not in _shelf("check#20261121-1405")


@mock_aws
def test_events_after_a_gap_are_marked(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    _shelf_plan()
    for hhmmss, units in [("140010", 5), ("140510", 5), ("150010", 0), ("150510", 0)]:
        _ingest(ingest, "CAM-S01-A", hhmmss, [("cheese145", units)] if units else [])
    _tick(ingest, now="2026-11-21T15:12:00+07:00")
    event = _table("test-shelf-events").get_item(
        Key={"store_id": "DEMO-S01", "event_key": f"20261121-1500#{CHEESE}#OOS"}
    )["Item"]
    assert (event["after_gap"], event["gap_from"], event["gap_to"]) == (True, "20261121-1405", "20261121-1500")


@mock_aws
def test_shelf_state_and_gaps_carry_over_between_ticks(monkeypatch: pytest.MonkeyPatch):
    # one check per tick: the level not set yet, the last measured check and the gap all go through the state item
    _, ingest = _backend(monkeypatch)
    _shelf_plan()
    for hhmmss, units in [("140010", 5), ("140510", 5), ("150010", 0), ("150510", 0)]:
        _ingest(ingest, "CAM-S01-A", hhmmss, [("cheese145", units)] if units else [])
    for hhmmss in ("140730", "141230", "150730", "151230"):
        _tick(ingest, now=f"2026-11-21T{hhmmss[:2]}:{hhmmss[2:4]}:{hhmmss[4:]}+07:00")
    assert _event_keys() == [f"20261121-1500#{CHEESE}#OOS"]
    event = _table("test-shelf-events").get_item(
        Key={"store_id": "DEMO-S01", "event_key": f"20261121-1500#{CHEESE}#OOS"}
    )["Item"]
    assert (event["after_gap"], event["gap_from"], event["gap_to"]) == (True, "20261121-1405", "20261121-1500")


@mock_aws
def test_a_recompute_replays_measured_checks_and_gaps_from_stored_checks(monkeypatch: pytest.MonkeyPatch):
    # days whose captures have expired are replayed from their check# items; items stored before this change have
    # no measurable field and count as measured
    _, ingest = _backend(monkeypatch)
    _shelf_plan()
    for minute, units, measurable in [
        ("1400", 5, None),
        ("1405", 5, None),
        ("1410", 0, False),
        ("1415", 0, False),
        ("1500", 0, True),
        ("1505", 0, True),
    ]:
        fields = {"bucket": f"20261121-{minute}", "counts": {CHEESE: units}, "captures": 1, "cameras": ["CAM-S01-A"]}
        if measurable is not None:
            fields["measurable"] = measurable
        if measurable is False:
            fields["unmeasured_reason"] = "display_not_visible"
        _put_shelf(f"check#20261121-{minute}", **fields, confident_skus=[])
    ingest.lambda_handler({"action": "shelf_recompute", "store_id": "DEMO-S01", "now": "2026-11-21T15:12:00+07:00"})
    assert _event_keys() == [f"20261121-1500#{CHEESE}#OOS"]
    event = _table("test-shelf-events").get_item(
        Key={"store_id": "DEMO-S01", "event_key": f"20261121-1500#{CHEESE}#OOS"}
    )["Item"]
    assert (event["after_gap"], event["gap_from"], event["gap_to"]) == (True, "20261121-1405", "20261121-1500")
    hour = _shelf("hour#20261121-14")
    assert (hour["checks"], hour["unmeasured_checks"]) == (2, 2)
    assert (_shelf("check#20261121-1410")["measurable"], _shelf("state")["last_measured_bucket"]) == (
        False,
        "20261121-1505",
    )


@mock_aws
def test_kpi_says_how_many_hours_were_measured(monkeypatch: pytest.MonkeyPatch):
    api, _ = _backend(monkeypatch)
    _at(api, monkeypatch, NOW)  # 28/11 12:00, open 06:00-22:00: checks 06:00..11:55 are closed = 72 checks
    _shelf_plan()
    _put_shelf("hour#20261128-09", **_rollup_item(6, 6, 0), unmeasured_checks=2)
    coverage = _kpi(api, days="1")["coverage"]
    assert coverage == {"measured_hours": 0.5, "open_hours": 6.0, "display_away_hours": 0.2}
    # an old rollup without unmeasured_checks counts none
    _put_shelf("day#20261127", **_rollup_item(12, 12, 0))
    coverage = _kpi(api, days="2")["coverage"]
    assert coverage["measured_hours"] == 1.0 and coverage["display_away_hours"] == 0.0
    assert coverage["open_hours"] == 22.0  # all of 27/11 (192 checks) plus 72 today


@mock_aws
def test_kpi_coverage_is_null_when_the_store_has_no_hours(monkeypatch: pytest.MonkeyPatch):
    api, _ = _backend(monkeypatch)
    _at(api, monkeypatch, NOW)
    assert _kpi(api)["coverage"] is None


@mock_aws
def test_trends_and_series_say_how_many_hours_were_not_measured(monkeypatch: pytest.MonkeyPatch):
    api, _ = _backend(monkeypatch)
    _at(api, monkeypatch, NOW)
    _shelf_plan()
    _put_shelf("day#20261127", **_rollup_item(10, 8, 6, units_sum=40), unmeasured_checks=4)
    _put_shelf("hour#20261128-09", **_rollup_item(4, 4, 2, units_sum=12), unmeasured_checks=6)
    query = {"metric": "osa", "days": "7"}
    points = _call(api, "GET", "/v1/reports/trends", groups="datagent", query=query)[1]["points"]
    assert {p["t"]: p["unmeasured_hours"] for p in points}["2026-11-27"] == 0.3  # 4 x 5 min = 0.33 h
    query = {"metric": "osa", "days": "1"}
    points = _call(api, "GET", "/v1/reports/trends", groups="datagent", query=query)[1]["points"]
    assert {p["t"]: p["unmeasured_hours"] for p in points}["20261128-09"] == 0.5
    series = _call(api, "GET", "/v1/reports/series", groups="datagent")[1]["series"]
    assert series[0]["unmeasured_hours"] == 0.3


@mock_aws
def test_products_list_cameras_that_cannot_see_the_display(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "140000", [("cheese145", 5)])
    _ingest(ingest, "CAM-S01-A", "140500", [], display_visible=False)
    status, body = _call(api, "GET", "/v1/products", groups="datagent")
    assert status == 200
    assert body["displays"] == [
        {
            "camera_id": "CAM-S01-A",
            "store_id": "DEMO-S01",
            "visible": False,
            "since": "2026-11-21T14:05:00+07:00",
            "last_visible_at": "2026-11-21T14:00:00+07:00",
        }
    ]


@mock_aws
def test_products_still_answer_when_the_display_status_cannot_be_read(monkeypatch: pytest.MonkeyPatch):
    api, _ = _backend(monkeypatch)
    status, body = _call(api, "GET", "/v1/products", groups="datagent")
    assert status == 200 and body["items"]
    for shelf_table in ("", "no-such-table"):  # unset, and a table that does not exist
        monkeypatch.setattr(api, "SHELF_TABLE", shelf_table)
        status, body = _call(api, "GET", "/v1/products", groups="datagent")
        assert status == 200 and body["items"] and body["displays"] == []


# --- Model page: present or absent, by time of day, check level, display check (reliability spec 1.2c) ---

SOUR = "Slide Sour Cream & Onion 150g"
AUDIT_15 = "AUD-CAM-S01-A-20261121-15"


def _labelled_frame_with_its_check(api, ingest) -> None:
    """DEMO-S01 must carry Cheese, Hot and Sour Cream. The 14:07 scoring frame shows 2 Hot and 1 Cheese; the
    labeller finds 1 Hot right, 1 "Hot" that is an Original, the Cheese right and 1 Cheese the model missed. Two
    captures at 14:06 and 14:08 see 3 Hot and 3 Cheese, so check 14:05 (lower median of the three) says 3 and 3."""
    _shelf_plan(expected=(CHEESE, HOT, SOUR))
    _one_pending_audit(ingest, counts=(("hot160", 2), ("cheese145", 1)))
    for hhmmss in ("140600", "140800"):
        _ingest(ingest, "CAM-S01-A", hhmmss, [("hot160", 3), ("cheese145", 3)])
    _tick(ingest)
    body = {
        "verdicts": [
            {"box_id": 1, "verdict": "correct"},
            {"box_id": 2, "verdict": "wrong_sku", "true_sku_id": "original145"},
            {"box_id": 3, "verdict": "correct"},
        ],
        "missed": [{"sku_id": "cheese145", "x": 5, "y": 5}],
        "misses_checked": True,
    }
    assert _call(api, "PUT", f"/v1/model/audits/{AUDIT_14}", body=body)[0] == 200


@mock_aws
def test_summary_has_presence_periods_check_level_and_display_check(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _labelled_frame_with_its_check(api, ingest)
    check = _shelf("check#20261121-1405")
    assert (check["counts"], check["measurable"], check["cameras"]) == ({HOT: 3, CHEESE: 3}, True, ["CAM-S01-A"])
    # a second scoring frame, 15:07: the worker said the display was in view, the labeller skipped it as away
    _ingest(ingest, "CAM-S01-A", "150700", [("hot160", 2)], with_frame=True, display_visible=True, display_score=0.88)
    ingest.lambda_handler({"action": "sample_audits", "hour": "20261121-15"})
    assert _call(api, "POST", f"/v1/model/audits/{AUDIT_15}/skip", body={"reason": "display_away"})[0] == 200

    status, s = _call(api, "GET", "/v1/model/summary", query={"days": "0"})
    assert status == 200 and s["n_audits"] == 1
    # truth: Hot 1, Original 1, Cheese 2; the frame: Hot 2, Cheese 1; expected: Cheese, Hot, Sour Cream
    assert s["presence"] == {
        "agree": {"value": 0.75, "ci": None, "n": 4},  # Original: model 0, truth 1
        "false_empty": {"value": 0.5, "ci": None, "n": 2},  # model 0 for Original and Sour Cream
        "missed_empty": {"value": 0.0, "ci": None, "n": 1},  # truth 0 for Sour Cream only
    }
    afternoon = s["by_period"]["afternoon"]
    assert afternoon["frames"] == 1 and afternoon["presence_agree"] == {"value": 0.75, "ci": None, "n": 4}
    assert afternoon["overall_identification_accuracy"]["value"] == pytest.approx(2 / 3)
    assert afternoon["per_sku"]["hot160"] == {
        "named_right": 0.5,
        "found_right": 1.0,
        "model_units": 2,
        "true_units": 1,
        "frames": 1,
        "days": 1,
        "enough": False,
    }
    assert s["by_period"]["morning"]["frames"] == 0 and s["by_period"]["evening"]["per_sku"] == {}
    hot = next(r for r in s["per_sku"] if r["sku_id"] == "hot160")
    assert (hot["found_right"], hot["bias_per_frame"], hot["enough"], hot["id_accuracy_ci"]) == (1.0, 1.0, False, None)
    assert s["kpis"]["overall_identification_accuracy"]["ci"] is None  # one frame
    # check 14:05 (Hot 3, Cheese 3) against the truth: off by +2 Hot, +1 Cheese, -1 Original; Sour Cream 0 on both
    c = s["check_level"]
    assert c["frames"] == 1
    assert (c["count_mae"]["value"], c["count_mae"]["n"]) == (pytest.approx(4 / 3), 3)
    assert (c["count_bias"]["value"], c["count_bias"]["n"]) == (pytest.approx(2 / 3), 3)
    assert c["presence_agree"] == {"value": 0.75, "ci": None, "n": 4}
    # only 15:07 was judged by the check (14:07's capture has no display fields): 1 frame, under 10, no share
    assert s["display_check"] == {
        "agree": {"value": None, "ci": None, "n": 1},
        "false_not_visible": 0,
        "false_visible": 1,
    }


@mock_aws
def test_check_level_leaves_out_checks_it_cannot_compare(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _labelled_frame_with_its_check(api, ingest)
    key = {"store_id": "DEMO-S01", "key": "check#20261121-1405"}
    for update, values in [
        ("SET measurable = :v", {":v": False}),  # the display was not in view in that check
        ("SET measurable = :v, cameras = :c", {":v": True, ":c": ["CAM-S01-A", "CAM-S01-B"]}),  # store-wide sum
    ]:
        _table("test-shelf").update_item(Key=key, UpdateExpression=update, ExpressionAttributeValues=values)
        c = _call(api, "GET", "/v1/model/summary", query={"days": "0"})[1]["check_level"]
        assert (c["frames"], c["count_mae"]) == (0, {"value": None, "ci": None, "n": 0})
    _table("test-shelf").delete_item(Key=key)
    assert _call(api, "GET", "/v1/model/summary", query={"days": "0"})[1]["check_level"]["frames"] == 0
    _table("test-shelf").put_item(Item={**key, "bucket": "20261121-1405", "counts": {HOT: 1}, "cameras": ["CAM-S01-A"]})
    c = _call(api, "GET", "/v1/model/summary", query={"days": "0"})[1]["check_level"]
    assert (c["frames"], c["count_bias"]["value"]) == (1, -1.0)  # an old item without measurable was measured


@mock_aws
def test_presence_uses_the_suggested_plan_when_none_is_saved(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _labelled_frame_with_its_check(api, ingest)
    _table("test-store-list").update_item(Key={"store_id": "DEMO-S01"}, UpdateExpression="REMOVE expected_skus")
    _at(api, monkeypatch, "2026-11-21T15:00:00+07:00")
    _put_shelf("day#20261121", confident_skus=[SOUR])  # the suggestion: only Sour Cream was seen surely
    agree = _call(api, "GET", "/v1/model/summary", query={"days": "0"})[1]["presence"]["agree"]
    assert (agree["value"], agree["n"]) == (0.75, 4)  # Sour Cream, 0 on both sides, agrees
    monkeypatch.setattr(api, "SHELF_TABLE", "no-such-table")  # no suggestion: only the SKUs either side counted
    agree = _call(api, "GET", "/v1/model/summary", query={"days": "0"})[1]["presence"]["agree"]
    assert (agree["value"], agree["n"]) == (pytest.approx(2 / 3), 3)


@mock_aws
def test_presence_holds_each_frame_to_its_own_stores_plan(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _labelled_frame_with_its_check(api, ingest)  # DEMO-S01 must carry Cheese, Hot and Sour Cream
    _table("test-store-list").put_item(Item={"store_id": "DEMO-S02", "store_name": "S02", "expected_skus": [TH_SWEET]})
    _table("test-audits").put_item(  # a labelled S02 frame: one TH Sweet box, right
        Item={
            "store_id": "DEMO-S02",
            "audit_id": "AUD-CAM-S02-A-20261121-14",
            "purpose": "scoring",
            "camera_id": "CAM-S02-A",
            "capture_id": "CAP-S02-20261121-140700",
            "capture_timestamp": "2026-11-21T14:07:00+07:00",
            "model_version": "unknown",
            "status": "done",
            "label_rule": "A",
            "ai_boxes_json": json.dumps([{"box_id": 1, "sku_id": "TMP-MLK-TH-01", "conf": 0.9, "box": [1, 2, 3, 4]}]),
            "verdicts_json": json.dumps([{"box_id": 1, "verdict": "correct"}]),
            "missed_json": "[]",
        }
    )
    s = _call(api, "GET", "/v1/model/summary", query={"days": "0"})[1]
    # S01's frame: 3 of 4 as before; S02's frame: TH only, 1 of 1. One merged plan would add 0/0 rows to both
    # frames: 8 of 9, false empty 1 of 6, missed empty 0 of 5, and 4 of 5 at the check.
    p = s["presence"]
    assert [(p[k]["value"], p[k]["n"]) for k in ("agree", "false_empty", "missed_empty")] == [
        (0.8, 5),
        (0.5, 2),
        (0.0, 1),
    ]
    assert s["check_level"]["presence_agree"] == {"value": 0.75, "ci": None, "n": 4}  # S01's check only


@mock_aws
def test_summary_still_answers_when_the_checks_cannot_be_read(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _labelled_frame_with_its_check(api, ingest)
    for shelf_table in ("", "no-such-table"):
        monkeypatch.setattr(api, "SHELF_TABLE", shelf_table)
        status, s = _call(api, "GET", "/v1/model/summary", query={"days": "0"})
        assert status == 200 and s["n_audits"] == 1 and s["check_level"]["frames"] == 0


# --- Confirming shelf events, with their photos ---

OOS_KEY = f"20261121-1410#{CHEESE}#OOS"
VERDICT_PATH = "/v1/shelf-events/verdict"
SOUR = "Slide Sour Cream & Onion 150g"


def _framed_cheese_then_empty(ingest) -> None:
    for hhmmss, units in [("140010", 5), ("140510", 5), ("141010", 0), ("141510", 0)]:
        _ingest(ingest, "CAM-S01-A", hhmmss, [("cheese145", units)] if units else [], with_frame=True)


def _oos_event() -> dict:
    return _table("test-shelf-events").get_item(Key={"store_id": "DEMO-S01", "event_key": OOS_KEY})["Item"]


def _verify(api, verdict="right", event_key=OOS_KEY, groups="field_team") -> tuple[int, dict]:
    body = {"store_id": "DEMO-S01", "event_key": event_key, "verdict": verdict}
    return _call(api, "PUT", VERDICT_PATH, groups=groups, body=body)


def _bucket_keys() -> set[str]:
    s3 = boto3.client("s3", region_name="ap-southeast-1")
    listing = s3.list_objects_v2(Bucket="test-analytics-bucket", Prefix="shelf-events/")
    return {o["Key"] for o in listing.get("Contents", [])}


def _put_event(key: str, kind: str = "OOS", sku: str = CHEESE) -> None:
    _table("test-shelf-events").put_item(
        Item={"store_id": "DEMO-S01", "event_key": key, "type": kind, "sku_id": sku, "at": key.split("#")[0]}
    )


def _put_verdict(key: str, verdict: str, kind: str = "OOS") -> None:
    _table("test-shelf-events").put_item(
        Item={"store_id": "DEMO-S01", "event_key": f"verdict#{key}", "verdict": verdict, "type": kind}
    )


@mock_aws
def test_an_event_copies_its_two_photos(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    _shelf_plan()
    _framed_cheese_then_empty(ingest)
    _tick(ingest)
    event = _oos_event()
    assert event["photo_before_key"].startswith("shelf-events/frames/DEMO-S01/")
    assert event["photo_before_key"].endswith("-before.jpg") and event["photo_after_key"].endswith("-after.jpg")
    s3 = boto3.client("s3", region_name="ap-southeast-1")
    before = s3.get_object(Bucket="test-analytics-bucket", Key=event["photo_before_key"])["Body"].read()
    after = s3.get_object(Bucket="test-analytics-bucket", Key=event["photo_after_key"])["Body"].read()
    assert (before, after) == (b"jpeg 140510", b"jpeg 141010")


@mock_aws
def test_an_event_without_photos_is_still_written(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    _shelf_plan()
    _cheese_then_empty(ingest)
    _tick(ingest)
    event = _oos_event()
    assert "photo_before_key" not in event and "photo_after_key" not in event
    assert _bucket_keys() == set()


@mock_aws
def test_an_expired_frame_does_not_stop_the_event(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    _shelf_plan()
    _framed_cheese_then_empty(ingest)
    boto3.client("s3", region_name="ap-southeast-1").delete_object(
        Bucket="test-hub-bucket", Key="frames/CAM-S01-A/2026-11-21/CAM-S01-A_20261121_140510.jpg"
    )
    _tick(ingest)
    event = _oos_event()
    assert "photo_before_key" not in event and event["photo_after_key"].endswith("-after.jpg")


@mock_aws
def test_recompute_keeps_photos_and_verdicts(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _at(api, monkeypatch, "2026-11-21T14:30:00+07:00")
    _shelf_plan()
    _framed_cheese_then_empty(ingest)
    _tick(ingest)
    photos = {k: _oos_event()[k] for k in ("photo_before_key", "photo_after_key")}
    assert _verify(api, "wrong")[0] == 200
    _shelf_plan(expected=(CHEESE, HOT), shelf_recompute_requested_at="2026-11-21T14:22:30+07:00")
    _tick(ingest)
    assert {k: _oos_event()[k] for k in photos} == photos
    items = _call(api, "GET", "/v1/shelf-events", groups="datagent")[1]["items"]
    assert [(i["event_key"], i["verdict"]) for i in items] == [(OOS_KEY, "wrong")]
    assert f"verdict#{OOS_KEY}" in {i["event_key"] for i in _table("test-shelf-events").scan()["Items"]}
    assert len(_bucket_keys()) == 2


@mock_aws
def test_events_list_never_shows_verdict_items(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _at(api, monkeypatch, "2026-11-21T14:30:00+07:00")
    _shelf_plan()
    _cheese_then_empty(ingest)
    _tick(ingest)
    items = _call(api, "GET", "/v1/shelf-events", groups="datagent")[1]["items"]
    assert [i["event_key"] for i in items] == [OOS_KEY] and "verdict" not in items[0]
    status, body = _verify(api, "unsure")
    assert (status, body["verdict"]) == (200, "unsure")
    items = _call(api, "GET", "/v1/shelf-events", groups="datagent")[1]["items"]
    assert [(i["event_key"], i["verdict"]) for i in items] == [(OOS_KEY, "unsure")]
    key = {"store_id": "DEMO-S01", "event_key": f"verdict#{OOS_KEY}"}
    saved = _table("test-shelf-events").get_item(Key=key)["Item"]
    assert (saved["type"], saved["sku_id"], saved["at"]) == ("OOS", CHEESE, "20261121-1410")
    assert saved["verified_by"] == "tester@datagent.io" and saved["verified_at"]


@mock_aws
def test_only_the_team_verifies_events(monkeypatch: pytest.MonkeyPatch):
    api, _ = _backend(monkeypatch)
    amp = f"20261121-1410#{SOUR}#OOS"
    _table("test-shelf-events").put_item(
        Item={"store_id": "DEMO-S01", "event_key": amp, "type": "OOS", "sku_id": SOUR, "at": "20261121-1410"}
    )
    assert _verify(api, "right", amp, groups="datagent")[0] == 403
    assert _verify(api, "right", "20261121-1410#Nothing#OOS")[0] == 404
    assert _verify(api, "right", f"verdict#{amp}")[0] == 404
    assert _verify(api, "maybe", amp)[0] == 400
    assert _call(api, "PUT", VERDICT_PATH, body={"store_id": "DEMO-S01", "verdict": "right"})[0] == 400
    for group in ("field_team", "team_admin"):
        assert _verify(api, "right", amp, groups=group)[0] == 200
    saved = _table("test-shelf-events").get_item(Key={"store_id": "DEMO-S01", "event_key": f"verdict#{amp}"})["Item"]
    assert saved["verdict"] == "right"


@mock_aws
def test_alert_accuracy_ignores_unsure_and_needs_ten(monkeypatch: pytest.MonkeyPatch):
    api, _ = _backend(monkeypatch)
    _at(api, monkeypatch, "2026-11-21T22:30:00+07:00")
    for i, verdict in enumerate(["right"] * 6 + ["wrong"] * 3 + ["unsure"]):
        key = f"20261121-{10 + i:02d}00#{CHEESE}#OOS"
        _put_event(key)
        _put_verdict(key, verdict)
    acc = _kpi(api)["alert_accuracy"]
    assert (acc["value"], acc["n"], acc["unsure"], acc["blocked_reason"]) == (None, 9, 1, "few_verified")
    # a verdict whose event is gone counts for nothing
    _put_verdict(f"20261121-0900#{CHEESE}#OOS", "right")
    assert _kpi(api)["alert_accuracy"]["n"] == 9
    last = f"20261121-2000#{CHEESE}#DEPLETED"
    _put_event(last, "DEPLETED")
    _put_verdict(last, "right", "DEPLETED")
    acc = _kpi(api)["alert_accuracy"]
    assert (acc["value"], acc["n"], acc["unsure"], acc["blocked_reason"]) == (0.7, 10, 1, None)
    assert acc["by_type"] == {
        "OOS": {"right": 6, "wrong": 3, "unsure": 1},
        "DEPLETED": {"right": 1, "wrong": 0, "unsure": 0},
    }


@mock_aws
def test_alert_accuracy_follows_the_category(monkeypatch: pytest.MonkeyPatch):
    # the list under the number applies the Category filter; the number must count the same events
    api, _ = _backend(monkeypatch)
    _at(api, monkeypatch, "2026-11-21T22:30:00+07:00")
    snack, milk = f"20261121-1000#{CHEESE}#OOS", f"20261121-1100#{TH_SWEET}#OOS"
    _put_event(snack)
    _put_verdict(snack, "right")
    _put_event(milk, sku=TH_SWEET)
    _put_verdict(milk, "wrong")
    assert _kpi(api)["alert_accuracy"]["n"] == 2
    acc = _kpi(api, category="Milk")["alert_accuracy"]
    assert (acc["n"], acc["unsure"], acc["by_type"]) == (1, 0, {"OOS": {"right": 0, "wrong": 1, "unsure": 0}})
    acc = _kpi(api, category="Snacks")["alert_accuracy"]
    assert (acc["n"], acc["by_type"]) == (1, {"OOS": {"right": 1, "wrong": 0, "unsure": 0}})


@mock_aws
def test_photos_route_gives_null_for_a_missing_photo(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _shelf_plan()
    _framed_cheese_then_empty(ingest)
    _tick(ingest)
    query = {"store_id": "DEMO-S01", "event_key": OOS_KEY}
    status, body = _call(api, "GET", "/v1/shelf-events/photos", groups="datagent", query=query)
    assert status == 200 and "shelf-events/frames/DEMO-S01/" in body["before_url"] and body["after_url"]
    boto3.client("s3", region_name="ap-southeast-1").delete_object(
        Bucket="test-analytics-bucket", Key=_oos_event()["photo_before_key"]
    )
    status, body = _call(api, "GET", "/v1/shelf-events/photos", groups="datagent", query=query)
    assert (status, body["before_url"]) == (200, None) and body["after_url"]
    no_photo = f"20261121-1500#{CHEESE}#OOS"
    _put_event(no_photo)
    query = {"store_id": "DEMO-S01", "event_key": no_photo}
    body = _call(api, "GET", "/v1/shelf-events/photos", groups="datagent", query=query)[1]
    assert body == {"before_url": None, "after_url": None}
    query = {"store_id": "DEMO-S01", "event_key": "20261121-1500#nothing#OOS"}
    assert _call(api, "GET", "/v1/shelf-events/photos", groups="datagent", query=query)[0] == 404


@mock_aws
def test_after_a_long_gap_the_before_photo_is_the_check_before_the_gap(monkeypatch: pytest.MonkeyPatch):
    # 44 checks (3.5 hours) in which the camera could not see the display, each with a frame of the wrong shelf
    # state; the event right after the gap must show the last measured check, not "no photo" or a stray frame
    _, ingest = _backend(monkeypatch)
    _shelf_plan()
    s3 = boto3.client("s3", region_name="ap-southeast-1")

    def frame(bucket: str, body: str) -> dict:
        key = f"frames/CAM-S01-A/2026-11-21/{bucket}.jpg"
        s3.put_object(Bucket="test-hub-bucket", Key=key, Body=body.encode())
        return {"image_key": key, "source_bucket": "test-hub-bucket"}

    base = {"captures": 1, "cameras": ["CAM-S01-A"], "confident_skus": []}
    for bucket, units in [("1400", 5), ("1405", 5)]:
        _put_shelf(
            f"check#20261121-{bucket}",
            bucket=f"20261121-{bucket}",
            counts={CHEESE: units},
            **base,
            **frame(bucket, f"measured {bucket}"),
        )
    for i in range(44):
        minute = 14 * 60 + 10 + 5 * i
        bucket = f"{minute // 60:02d}{minute % 60:02d}"
        _put_shelf(
            f"check#20261121-{bucket}",
            bucket=f"20261121-{bucket}",
            counts={CHEESE: 5},
            measurable=False,
            unmeasured_reason="display_not_visible",
            **base,
            **frame(bucket, f"away {bucket}"),
        )
    for bucket in ("1750", "1755"):
        _put_shelf(
            f"check#20261121-{bucket}",
            bucket=f"20261121-{bucket}",
            counts={CHEESE: 0},
            **base,
            **frame(bucket, f"measured {bucket}"),
        )
    ingest.lambda_handler({"action": "shelf_recompute", "store_id": "DEMO-S01", "now": "2026-11-21T18:10:00+07:00"})
    key = f"20261121-1750#{CHEESE}#OOS"
    event = _table("test-shelf-events").get_item(Key={"store_id": "DEMO-S01", "event_key": key})["Item"]
    assert event["after_gap"] and event["gap_from"] == "20261121-1405"
    read = lambda k: s3.get_object(Bucket="test-analytics-bucket", Key=event[k])["Body"].read()  # noqa: E731
    assert (read("photo_before_key"), read("photo_after_key")) == (b"measured 1405", b"measured 1750")


@mock_aws
def test_a_network_failure_while_copying_a_photo_does_not_stop_the_tick(monkeypatch: pytest.MonkeyPatch):
    from botocore.exceptions import ReadTimeoutError

    _, ingest = _backend(monkeypatch)
    _shelf_plan()
    _framed_cheese_then_empty(ingest)
    real = boto3.client("s3", region_name="ap-southeast-1")

    class Flaky:
        def __getattr__(self, name):
            return getattr(real, name)

        def copy_object(self, **kwargs):
            raise ReadTimeoutError(endpoint_url="https://s3.test")

    monkeypatch.setattr(
        ingest, "_aws_clients", lambda: (Flaky(), boto3.resource("dynamodb", region_name="ap-southeast-1"))
    )
    _tick(ingest)
    event = _oos_event()
    assert "photo_before_key" not in event and "photo_after_key" not in event
    assert _shelf("state")["last_bucket"] == "20261121-1415"


# --- reliability badge per SKU (reliability spec 1.3) ---


def _put_cheese_frames(days: tuple[str, ...], per_day: int) -> None:
    """Scoring frames, done: of 2 boxes named Cheese 1 is right and 1 is not a product; 2 boxes named Hot are really
    Cheese. So Cheese is named right 1 of 2 and found right 1 of 3."""
    boxes = [
        {"box_id": i, "sku_id": sku, "conf": 0.9, "box": [i * 9, 0, 5, 5]}
        for i, sku in ((1, "cheese145"), (2, "cheese145"), (3, "hot160"), (4, "hot160"))
    ]
    verdicts = [
        {"box_id": 1, "verdict": "correct"},
        {"box_id": 2, "verdict": "not_product"},
        {"box_id": 3, "verdict": "wrong_sku", "true_sku_id": "cheese145"},
        {"box_id": 4, "verdict": "wrong_sku", "true_sku_id": "cheese145"},
    ]
    _put_scoring_frames(days, per_day, boxes, verdicts)


def _put_scoring_frames(days: tuple[str, ...], per_day: int, boxes: list[dict], verdicts: list[dict]) -> None:
    """Done scoring frames of DEMO-S01's camera A, per_day of them on each day of November (hours 10, 11, ...)."""
    for day in days:
        for i in range(per_day):
            _table("test-audits").put_item(
                Item={
                    "store_id": "DEMO-S01",
                    "audit_id": f"AUD-CAM-S01-A-202611{day}-{10 + i:02d}",
                    "status": "done",
                    "purpose": "scoring",
                    "capture_timestamp": f"2026-11-{day}T{10 + i:02d}:10:00+07:00",
                    "ai_boxes_json": json.dumps(boxes),
                    "verdicts_json": json.dumps(verdicts),
                    "missed_json": "[]",
                }
            )


@mock_aws
def test_products_carry_reliability(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "140000", [("cheese145", 5)])
    body = _call(api, "GET", "/v1/products", groups="datagent")[1]
    assert body["items"]
    for p in body["items"]:  # no scoring frame yet
        assert p["reliability"] == {
            "badge": "insufficient",
            "named_right": None,
            "found_right": None,
            "true_units": 0,
            "frames": 0,
            "confused_as": None,
        }


@mock_aws
def test_products_and_events_carry_the_badge_from_14_days_of_scoring_frames(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "140000", [("cheese145", 5)])
    _at(api, monkeypatch, NOW)  # 2026-11-28
    _put_cheese_frames(("20", "21"), 6)  # 12 frames, 36 true Cheese cans, two days: enough
    _put_cheese_frames(("01",), 12)  # older than 14 days: left out
    items = {p["sku_id"]: p for p in _call(api, "GET", "/v1/products", groups="datagent")[1]["items"]}
    r = items[CHEESE]["reliability"]
    assert (r["badge"], r["true_units"], r["frames"]) == ("low", 36, 12)
    assert (r["named_right"], r["found_right"]) == (0.5, pytest.approx(1 / 3))
    assert r["confused_as"] == HOT
    for at, sku, kind in [("20261128-1000", CHEESE, "OOS"), ("20261128-1100", HOT, "OOS")]:
        item = {"type": kind, "sku_id": sku, "at": at, "delta": -5, "level_before": 5, "level_after": 0}
        _table("test-shelf-events").put_item(Item={"store_id": "DEMO-S01", "event_key": f"{at}#{sku}#{kind}", **item})
    events = {e["sku_id"]: e for e in _call(api, "GET", "/v1/shelf-events", "datagent")[1]["items"]}
    assert (events[CHEESE]["badge"], events[CHEESE]["uncertain"]) == ("low", True)
    assert events[HOT]["badge"] == "insufficient" and "uncertain" not in events[HOT]


ORIGINAL = "Slide Original 145g"


@mock_aws
def test_a_sku_the_model_never_names_reads_low_and_its_events_uncertain(monkeypatch: pytest.MonkeyPatch):
    # 23/11 evening: every real Original can was called Cheese, so the model never said Original at all
    api, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "140000", [("cheese145", 5)])  # gives the store its camera
    _at(api, monkeypatch, NOW)  # 2026-11-28
    boxes = [{"box_id": i, "sku_id": "cheese145", "conf": 0.93, "box": [i * 9, 0, 5, 5]} for i in (1, 2, 3)]
    verdicts = [{"box_id": i, "verdict": "wrong_sku", "true_sku_id": "original145"} for i in (1, 2, 3)]
    _put_scoring_frames(("20", "21"), 6, boxes, verdicts)  # 12 frames on 2 days, 36 real Original cans
    items = {p["sku_id"]: p for p in _call(api, "GET", "/v1/products", groups="datagent")[1]["items"]}
    r = items[ORIGINAL]["reliability"]
    assert (r["badge"], r["found_right"], r["named_right"], r["true_units"], r["frames"]) == ("low", 0.0, None, 36, 12)
    assert r["confused_as"] == CHEESE
    at = "20261128-1000"
    item = {"type": "OOS", "sku_id": ORIGINAL, "at": at, "delta": -3, "level_before": 3, "level_after": 0}
    _table("test-shelf-events").put_item(Item={"store_id": "DEMO-S01", "event_key": f"{at}#{ORIGINAL}#OOS", **item})
    event = _call(api, "GET", "/v1/shelf-events", "datagent")[1]["items"][0]
    assert (event["sku_id"], event["badge"], event["uncertain"]) == (ORIGINAL, "low", True)


@mock_aws
def test_lists_still_answer_when_the_scoring_frames_cannot_be_read(monkeypatch: pytest.MonkeyPatch):
    api, _ = _backend(monkeypatch)
    for audits_table in ("", "no-such-table"):  # unset, and a table that does not exist
        monkeypatch.setattr(api, "AUDITS_TABLE", audits_table)
        body = _call(api, "GET", "/v1/products", groups="datagent")[1]
        assert body["items"] and {p["reliability"]["badge"] for p in body["items"]} == {"insufficient"}
        assert _call(api, "GET", "/v1/shelf-events", groups="datagent")[0] == 200


@mock_aws
def test_scoring_frames_are_read_by_key_for_the_window_only(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "140000", [("cheese145", 5)])  # gives the store its camera
    _at(api, monkeypatch, NOW)  # 2026-11-28
    _put_cheese_frames(("20", "21"), 6)  # in the window
    _put_cheese_frames(("01",), 3)  # before the 14 days
    _table("test-audits").put_item(  # a training frame of the store, a frame of another store: never read
        Item={"store_id": "DEMO-S01", "audit_id": "TRN-CAM-S01-A-20261121-10", "status": "done", "purpose": "training"}
    )
    _table("test-audits").put_item(
        Item={"store_id": "OTHER", "audit_id": "AUD-CAM-X-20261121-10", "status": "done", "purpose": "scoring"}
    )
    read: list[str] = []
    real_query = api._query_all

    def spy(table, **kwargs):
        items = real_query(table, **kwargs)
        if table.name == "test-audits":
            read.extend(i["audit_id"] for i in items)
        return items

    def no_scan(table, **kwargs):
        assert table.name != "test-audits", "the audits table must not be scanned"
        return real_scan(table, **kwargs)

    real_scan = api._scan_all
    monkeypatch.setattr(api, "_query_all", spy)
    monkeypatch.setattr(api, "_scan_all", no_scan)
    items = {p["sku_id"]: p for p in _call(api, "GET", "/v1/products", groups="datagent")[1]["items"]}
    assert items[CHEESE]["reliability"]["frames"] == 12
    assert len(read) == 12 and all(a.startswith("AUD-CAM-S01-A-202611") and "-20261101-" not in a for a in read)
