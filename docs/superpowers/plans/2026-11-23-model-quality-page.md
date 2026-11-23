# Trang Model (chấm và theo dõi model) — kế hoạch làm

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Website có trang `/model`. Ở đó team chấm từng khung ảnh thật, rồi thấy 12 chỉ số của Datagent, bảng
theo SKU, ma trận nhầm lẫn, xu hướng theo ngày, và theo dõi tự động 7 ngày.

**Architecture:**
- Worker ghi thêm `model_version` và `detections` (từng hộp) vào mỗi kết quả.
- Lịch hằng giờ của Lambda ingest chọn ngẫu nhiên 1 khung mỗi camera-giờ vào bảng `audits` (ảnh chép sang
  bucket analytics), và ghi thống kê giờ vào bảng `model-health`.
- Lambda API có 6 route `/model/*`. Các phép tính nằm trong module thuần `backend/audit_scoring.py` và
  `backend/model_health.py`.
- Trang Next.js (static export) gọi các route đó.

**Tech Stack:**
- Python 3.12 (Lambda, boto3), pytest + moto.
- CloudFormation (`infra/backend.yaml`).
- Next.js 16 static export, React, recharts, lucide-react, `node --test`.

**Spec:** `docs/superpowers/specs/2026-11-23-model-quality-page-design.md`

## Global Constraints

- **Không có số liệu giả.** Chỉ số không có mẫu thì API trả `value: null` và `n: 0`, giao diện hiện "—". Không bao giờ hiện 0 thay cho "không có dữ liệu".
- **Phân quyền:** mọi route `/model/*` chỉ cho `team_admin` và `field_team`; `datagent` nhận 403 `FORBIDDEN`.
- **Verdict:** `correct`, `wrong_sku` hoặc `not_product`. **Lý do bỏ qua:** `blurry`, `blocked`, `camera_moved` hoặc `other`.
- **`audit_id`:** `AUD-<camera_id>-<YYYYMMDD>-<HH>`, theo giờ ICT của khung.
- **Ảnh:** `audits/frames/<camera_id>/<YYYY-MM-DD>/<image_filename>` trong bucket analytics, không lifecycle.
- **`model-health`:** khoá `camera_id` + `hour` (`YYYYMMDD-HH`), TTL `expires_at` = lúc ghi + 90 ngày.
- **Khung trùng:** IoU ≥ 0.5, như `DUPLICATE` trong `server/milk/pipeline.py`.
- **Mục tiêu KPI:**

  | Chỉ số | Mục tiêu |
  |---|---|
  | #1 | ≥ 0.80 |
  | #2 | ≥ 0.60 |
  | #3 | ≤ 2 |
  | #4 | ≥ 0.75 |
  | #5 | ≥ 0.40 |
  | #6 | Exact + Minor ≥ 0.75 |
  | #7 | ≤ 0.20 |
  | #8 | ≤ 0.10 |
  | #9 | > 0.8 |
  | #10 | < 0.5 |
  | #11 | ≤ 30000 ms |
  | #12 | ≤ 0.20 |

- **Giờ và ngày** tính theo ICT (UTC+7). Lambda chạy theo UTC.
- **`MILK_MODEL_VERSION`:**
  - Bản đang chạy dùng `long-2026-10-13+slide-v3`.
  - Mặc định khi không đặt: `<MILK_PIPELINE>`, cộng `:<tên thư mục chứa MILK_SLIDE_WEIGHTS>` khi pipeline có `slide`.
- **Gói Lambda** để file ở gốc zip:
  - API: `handler.py` (từ `backend/api/`), `common.py`, `audit_scoring.py`.
  - Ingest: `handler.py` (từ `backend/ingest/`), `common.py`, `model_health.py`.
- **Next.js:** đọc tài liệu trong `frontend/node_modules/next/dist/docs/` trước khi viết code frontend
  (`frontend/AGENTS.md`). Static export nên không có route động; màn hình đếm dùng `?audit=<id>`.
- **Chạy test:** `"$VENV/Scripts/python.exe" -m pytest -q` từ gốc repo. `VENV` là venv scratchpad có moto; nếu
  mất thì dựng lại bằng `py -3.10 -m venv --system-site-packages` rồi `pip install "moto[dynamodb,s3]"`.
  Frontend chạy `cd frontend && npm test`.
- **Commit:** dùng `-c user.name="Nguyen Huy Hoang" -c user.email=193206418+Protein-17012006@users.noreply.github.com`,
  và kết thúc bằng dòng `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Khung mà model không vẽ hộp nào (kệ trống, hoặc sót hết) vẫn phải đếm và lưu được, chỉ với điểm sót. Test ở Task 2, 6, 8.
2. Bộ lọc không khớp audit nào (phiên bản chưa có dữ liệu): mọi chỉ số `null`, `n = 0`, không ra 0. Test ở Task 7.
3. Hộp UNRECOGNIZED chấm `correct` (hàng ngoài danh mục) không được cộng vào số thật của SKU nào, và không vào mẫu số của #1–2. Test ở Task 2.
4. Capture có đuôi `-2`, `-3` (nhiều capture trong một giây), và giờ có capture nhưng không có ảnh: chọn khung không sót, cũng không lỗi. Test ở Task 5.
5. Bản ghi cũ không có `detections` hay `model_version`: hộp dựng lại từ `rows`, phiên bản là `"unknown"`. Test ở Task 3 và 5.

---

### Task 1: Worker ghi `model_version` và `detections`

**Files:**
- Modify: `server/milk/config.py` (thêm `Settings.model_version`, hàm `default_model_version`, dòng trong `load`)
- Modify: `server/milk/cvoutput.py` (thêm `persist_record`)
- Modify: `server/milk/counter.py:210` (dùng `persist_record`)
- Test: `tests/test_config.py`, `tests/test_cvoutput.py`

**Interfaces:**
- Produces:
  - `default_model_version(pipeline: str, slide_weights: str) -> str`.
  - `Settings.model_version: str`.
  - `persist_record(log_line: dict, rows: list[dict], counts: dict, latency_ms: int, detections: list[Detection], model_version: str) -> dict`.
    Trả về `{**log_line, "rows", "log", "counts", "latency_ms", "model_version", "detections": [{"sku_id", "conf", "box"}]}`.
    `conf` làm tròn 3 chữ số; `box` là 4 số nguyên `round()`.

- [ ] **Step 1: Viết test hỏng**

```python
# tests/test_config.py
def test_model_version_comes_from_the_env(monkeypatch):
    monkeypatch.setenv("MILK_MODEL_VERSION", "long-2026-10-13+slide-v3")
    assert config.load().model_version == "long-2026-10-13+slide-v3"

def test_model_version_defaults_to_pipeline_and_slide_run(monkeypatch):
    monkeypatch.delenv("MILK_MODEL_VERSION", raising=False)
    assert config.default_model_version("long+slide", "~/Desktop/Datagent/slide_pilot/runs_v3/best.pt") == "long+slide:runs_v3"
    assert config.default_model_version("long", "") == "long"

# tests/test_cvoutput.py
def test_persist_record_keeps_every_box_with_its_own_score():
    dets = [Detection("hot160", "Slide Hot & Spicy 160g", 0.8744, (947.4, 326.0, 74.0, 165.6))]
    rec = persist_record({"capture_id": "CAP-S01-20261123-125654-2"}, [], {"hot160": 1}, 104, dets, "v3")
    assert rec["model_version"] == "v3"
    assert rec["detections"] == [{"sku_id": "hot160", "conf": 0.874, "box": [947, 326, 74, 166]}]
    assert rec["capture_id"] == "CAP-S01-20261123-125654-2" and rec["latency_ms"] == 104
```

Dùng cùng cách import và `monkeypatch` như các test đã có trong hai file đó.

- [ ] **Step 2:** Chạy `pytest -q tests/test_config.py tests/test_cvoutput.py`. Mong đợi: FAIL vì chưa có `model_version`, `default_model_version`, `persist_record`.
- [ ] **Step 3:** Viết code: `config.py`, `persist_record` trong `cvoutput.py`, và sửa `counter.py:210` thành `record = persist_record(log_line, rows, counts, latency_ms, detections, s.model_version)`.
- [ ] **Step 4:** Chạy cả bộ `pytest -q`. Mong đợi: tất cả PASS.
- [ ] **Step 5:** Commit `Worker: record the model version and every box with its own score`.

### Task 2: Module chấm điểm `backend/audit_scoring.py`

**Files:**
- Create: `backend/audit_scoring.py`
- Test: `tests/test_audit_scoring.py` (đặt `sys.path.insert(0, ROOT / "backend")` như file test moto)

**Interfaces:**
- Produces:
  - `VERDICTS = ("correct", "wrong_sku", "not_product")`
  - `SKIP_REASONS = ("blurry", "blocked", "camera_moved", "other")`
  - `KPI_TARGETS: dict[str, tuple[str, float]]` — tên chỉ số → (`">="`, `"<="`, `">"`, `"<"`), ngưỡng. Lấy theo Global Constraints.
    Ngưỡng #6 áp lên Exact + Minor.
  - `validate_labels(ai_boxes: list[dict], verdicts: list[dict], missed: list[dict], catalog: set[str]) -> list[str]`
    trả về các lỗi, ví dụ `"box 3 has no verdict"` hoặc `"unknown sku 'xyz'"`.
  - `comparison_rows(audit: dict) -> list[dict]`. Audit có `ai_boxes`, `verdicts`, `missed`, `capture_timestamp`.
    Mỗi dòng: `{sku_id, ai_unit_count, human_unit_count, count_difference, count_accuracy_pct, discrepancy_category}`.
    Chỉ cho SKU của danh mục; UNRECOGNIZED không có dòng (spec mục 5).
  - `summarize(audits: list[dict], processing_ms: list[int]) -> dict`. Trả về:
    `{"n_audits": int, "kpis": {name: {"value": float|None, "target": [op, threshold], "met": bool|None, "n": int}}, "per_sku": [...], "confusion": {"rows": [...], "cols": [...], "cells": {"<row>|<col>": int}}, "by_day": [{"day", "audits", "overall_identification_accuracy", "unit_count_mae", "exact_or_minor_rate"}]}`.
    Mỗi dòng `per_sku`: `{sku_id, model_units, true_units, id_accuracy, missed_units, confused_as, confused_count}`.
    Ma trận: hàng là nhãn model cộng `"UNRECOGNIZED"` và `"MISSED"`; cột là nhãn thật cộng `"NOT_PRODUCT"`.

- [ ] **Step 1: Viết test hỏng** với số tính tay, lấy từ ca 23/11.

```python
AUDIT_2311 = {  # 2 Original read as Hot, 1 Original right, cheese: 1 right + 1 candy, missed: 2 Hot, 1 cheese
    "capture_timestamp": "2026-11-23T12:56:54+07:00",
    "ai_boxes": [
        {"box_id": 1, "sku_id": "hot160", "conf": 0.87, "box": [948, 326, 72, 167]},
        {"box_id": 2, "sku_id": "hot160", "conf": 0.94, "box": [1190, 288, 74, 150]},
        {"box_id": 3, "sku_id": "original145", "conf": 0.67, "box": [1063, 336, 75, 117]},
        {"box_id": 4, "sku_id": "cheese145", "conf": 0.85, "box": [1121, 310, 73, 129]},
        {"box_id": 5, "sku_id": "cheese145", "conf": 0.85, "box": [700, 900, 60, 60]},
    ],
    "verdicts": [
        {"box_id": 1, "verdict": "wrong_sku", "true_sku_id": "original145"},
        {"box_id": 2, "verdict": "wrong_sku", "true_sku_id": "original145"},
        {"box_id": 3, "verdict": "correct"}, {"box_id": 4, "verdict": "correct"},
        {"box_id": 5, "verdict": "not_product"},
    ],
    "missed": [{"sku_id": "hot160", "x": 940, "y": 400}, {"sku_id": "hot160", "x": 1030, "y": 330},
               {"sku_id": "cheese145", "x": 1010, "y": 290}],
}

def test_rows_of_the_2311_frame():
    rows = {r["sku_id"]: r for r in comparison_rows(AUDIT_2311)}
    assert (rows["original145"]["ai_unit_count"], rows["original145"]["human_unit_count"]) == (1, 3)
    assert rows["original145"]["discrepancy_category"] == "Minor"
    assert round(rows["original145"]["count_accuracy_pct"], 4) == 0.3333
    assert (rows["hot160"]["ai_unit_count"], rows["hot160"]["human_unit_count"]) == (2, 2)
    assert rows["hot160"]["discrepancy_category"] == "Wrong SKU"          # counts match, cans are wrong
    assert rows["cheese145"]["discrepancy_category"] == "Exact Match"

def test_kpis_of_the_2311_frame():
    k = summarize([AUDIT_2311], [20, 30])["kpis"]
    assert k["overall_identification_accuracy"]["value"] == 0.5          # 2 of 4 catalog boxes named right
    assert k["overall_identification_accuracy"]["met"] is False
    assert round(k["unit_count_mae"]["value"], 4) == 0.6667
    assert round(k["unit_count_accuracy_avg"]["value"], 4) == 0.7778
    assert round(k["exact_match_rate"]["value"], 4) == 0.3333
    assert k["missed_sku_rate"]["value"] == 0.0
    assert k["false_detection_rate"]["value"] == 0.2
    assert round(k["avg_confidence_correct"]["value"], 4) == 0.76
    assert round(k["avg_confidence_incorrect"]["value"], 4) == 0.8867
    assert k["avg_processing_time_ms"]["value"] == 25
    assert k["unrecognized_product_rate"]["value"] == 0.0

def test_per_sku_and_confusion_of_the_2311_frame():
    s = summarize([AUDIT_2311], [])
    hot = next(r for r in s["per_sku"] if r["sku_id"] == "hot160")
    assert (hot["model_units"], hot["true_units"], hot["id_accuracy"], hot["missed_units"]) == (2, 2, 0.0, 2)
    assert (hot["confused_as"], hot["confused_count"]) == ("original145", 2)
    assert s["confusion"]["cells"]["hot160|original145"] == 2
    assert s["confusion"]["cells"]["cheese145|NOT_PRODUCT"] == 1
    assert s["confusion"]["cells"]["MISSED|hot160"] == 2

def test_unrecognized_box_on_other_goods_counts_for_no_sku():
    audit = {"capture_timestamp": "2026-11-23T13:00:00+07:00",
             "ai_boxes": [{"box_id": 1, "sku_id": None, "conf": 0.45, "box": [0, 0, 10, 10]},
                          {"box_id": 2, "sku_id": None, "conf": 0.30, "box": [20, 0, 10, 10]}],
             "verdicts": [{"box_id": 1, "verdict": "correct"},
                          {"box_id": 2, "verdict": "wrong_sku", "true_sku_id": "cheese145"}],
             "missed": []}
    assert comparison_rows(audit) == [{"sku_id": "cheese145", "ai_unit_count": 0, "human_unit_count": 1,
                                       "count_difference": -1, "count_accuracy_pct": 0.0,
                                       "discrepancy_category": "Missed SKU"}]
    k = summarize([audit], [])["kpis"]
    assert k["overall_identification_accuracy"]["value"] == 0.0           # box 2: catalog can, not named
    assert k["unrecognized_product_rate"]["value"] == 1.0

def test_a_frame_with_no_boxes_scores_only_its_misses():
    audit = {"capture_timestamp": "2026-11-23T14:00:00+07:00", "ai_boxes": [], "verdicts": [],
             "missed": [{"sku_id": "hot160", "x": 1, "y": 1}]}
    k = summarize([audit], [])["kpis"]
    assert k["missed_sku_rate"]["value"] == 1.0
    assert k["overall_identification_accuracy"] == {"value": None, "target": [">=", 0.6], "met": None, "n": 0}

def test_no_audits_means_no_numbers():
    k = summarize([], [])["kpis"]
    assert all(v["value"] is None and v["n"] == 0 for v in k.values())

def test_validate_labels():
    boxes = AUDIT_2311["ai_boxes"]
    assert validate_labels(boxes, AUDIT_2311["verdicts"], AUDIT_2311["missed"], CATALOG) == []
    assert validate_labels(boxes, AUDIT_2311["verdicts"][:4], [], CATALOG) == ["box 5 has no verdict"]
    bad = AUDIT_2311["verdicts"][:4] + [{"box_id": 5, "verdict": "wrong_sku", "true_sku_id": "xyz"}]
    assert validate_labels(boxes, bad, [], CATALOG) == ["unknown sku 'xyz'"]
    assert validate_labels([], [], [{"sku_id": "hot160", "x": 1, "y": 1}], CATALOG) == []
```

`CATALOG = {"original145", "sourcream150", "cheese145", "hot160", "TMP-MLK-TH-01"}`. Ghi chú: test #1 ở hàng cheese
cho Exact Match dù có một hộp `not_product`; spec chỉ coi là False Detection khi số thật = 0.

- [ ] **Step 2:** Chạy `pytest -q tests/test_audit_scoring.py`. Mong đợi: FAIL vì chưa có module.
- [ ] **Step 3:** Viết `backend/audit_scoring.py` theo spec mục 5.
  - Dòng so sánh chỉ cho nhãn khác `None`.
  - Mẫu số #1–2: hộp có tên mà `correct`, cộng mọi hộp `wrong_sku`.
  - #1 lọc theo top 50 SKU theo tổng số thật.
  - Chỉ số có mẫu số 0 thì trả `value: None`, `met: None`, `n: 0`.
  - #11 dùng danh sách `processing_ms`.
  - `by_day` gom theo `capture_timestamp[:10]`.
- [ ] **Step 4:** Chạy `pytest -q`. Mong đợi: tất cả PASS.
- [ ] **Step 5:** Commit `Backend: score labelled frames the way Datagent's Accuracy Report reads`.

### Task 3: Module thống kê giờ `backend/model_health.py`

**Files:**
- Create: `backend/model_health.py`
- Test: `tests/test_model_health.py`

**Interfaces:**
- Produces:
  - `iou(a: list|tuple, b: list|tuple) -> float` (hộp x, y, w, h).
  - `capture_boxes(item: dict) -> list[dict]`. Item là một capture của bảng captures (có `rows_json`, có thể có
    `detections_json`). Trả về `[{"box_id": i, "sku_id", "conf", "box"}]`, `box_id` từ 1.
    Không có `detections_json` thì mỗi `bounding_box` của `rows` là một hộp, `conf` lấy `confidence_score` của dòng.
    Nhãn lấy `model_alias` của dòng nếu có (ingest đã đổi `sku_id` sang tên chính thức), không thì `sku_id`.
  - `hour_stats(items: list[dict]) -> dict`. Trả về:
    `{"captures", "model_versions": [..], "conf_median", "conf_mean", "flagged_row_pct", "unrecognized_box_pct", "units_median", "units_min", "units_max", "jitter", "duplicate_pairs", "processing_ms_median", "processing_ms_p90", "latency_ms_median"}`.
    Items xếp theo `capture_timestamp`. `jitter` = trung bình qua các cặp capture liền nhau của Σ_SKU |Δ số
    đơn vị|. Số đơn vị theo SKU lấy từ `rows`. Không có item thì trả `{"captures": 0}`.

- [ ] **Step 1: Viết test hỏng**

```python
NEW = {"capture_timestamp": "2026-11-23T13:30:00+07:00", "units_found": 3, "processing_time_ms": 20,
       "latency_ms": 100, "model_version": "v3", "flagged_rows": 1,
       "rows_json": '[{"sku_id": "Slide Cheese 145g", "model_alias": "cheese145", "unit_count": 2, "confidence_score": 0.8, "bounding_box": [[0,0,10,10],[0,0,10,10]], "is_flagged": false}, {"sku_id": null, "model_alias": "", "unit_count": 1, "confidence_score": 0.3, "bounding_box": [[50,0,10,10]], "is_flagged": true}]',
       "detections_json": '[{"sku_id": "cheese145", "conf": 0.9, "box": [0,0,10,10]}, {"sku_id": "cheese145", "conf": 0.7, "box": [0,0,10,10]}, {"sku_id": null, "conf": 0.3, "box": [50,0,10,10]}]'}
OLD = {"capture_timestamp": "2026-11-23T13:30:10+07:00", "units_found": 1, "processing_time_ms": 40,
       "latency_ms": 200, "flagged_rows": 0,
       "rows_json": '[{"sku_id": "Slide Cheese 145g", "model_alias": "cheese145", "unit_count": 1, "confidence_score": 0.6, "bounding_box": [[0,0,10,10]], "is_flagged": false}]'}

def test_old_record_boxes_come_from_rows():
    assert capture_boxes(OLD) == [{"box_id": 1, "sku_id": "cheese145", "conf": 0.6, "box": [0, 0, 10, 10]}]

def test_hour_stats():
    s = hour_stats([OLD, NEW])                       # out of order on purpose
    assert s["captures"] == 2 and s["model_versions"] == ["unknown", "v3"]
    assert s["duplicate_pairs"] == 1                 # the two cheese boxes of NEW
    assert s["unrecognized_box_pct"] == 0.25         # 1 of 4 boxes
    assert s["flagged_row_pct"] == 1 / 3             # 1 of 3 rows
    assert s["jitter"] == 2                          # cheese 2 -> 1 (|1|) + unrecognized 1 -> 0 (|1|)
    assert (s["units_min"], s["units_max"]) == (1, 3)
    assert round(s["conf_median"], 4) == 0.65        # boxes 0.9, 0.7, 0.3, 0.6
    assert s["processing_ms_median"] == 30
```

- [ ] **Step 2:** Chạy test. Mong đợi: FAIL vì chưa có module.
- [ ] **Step 3:** Viết `backend/model_health.py`.
- [ ] **Step 4:** Chạy `pytest -q`. Mong đợi: tất cả PASS.
- [ ] **Step 5:** Commit `Backend: hourly model health from saved captures`.

### Task 4: Hạ tầng (2 bảng, quyền, biến môi trường)

**Files:**
- Modify: `infra/backend.yaml`
  - Thêm `AuditsTable` và `ModelHealthTable` sau `UserPrefsTable`, cùng kiểu với các bảng khác. `ModelHealthTable`
    có `TimeToLiveSpecification` theo `expires_at`.
  - Thêm 2 ARN vào statement DynamoDB đầu tiên của `LambdaExecutionRole`.
  - Thêm `AUDITS_TABLE` và `MODEL_HEALTH_TABLE` vào cả `ApiLambda` và `IngestLambda`.
  - Thêm `SKU_MASTER_TABLE` vào `IngestLambda`. Không bắt buộc; bỏ qua nếu không dùng.
- Modify: `tests/test_backend_integration_moto.py`
  - `_create_mock_infra` tạo thêm `test-audits` (`store_id`/`audit_id`) và `test-model-health` (`camera_id`/`hour`).
  - Tạo thêm bucket `test-hub-bucket`.
  - `_backend` đặt `AUDITS_TABLE`, `MODEL_HEALTH_TABLE`.

- [ ] **Step 1:** Sửa template. Chạy `aws cloudformation validate-template --template-body file://infra/backend.yaml --region ap-southeast-1`
  (đặt `MSYS_NO_PATHCONV=1`). Mong đợi: in ra Parameters, không lỗi.
- [ ] **Step 2:** Sửa phần dựng bảng giả lập. Chạy `pytest -q`. Mong đợi: tất cả PASS (chưa test mới).
- [ ] **Step 3:** Commit `Infra: audits and model-health tables for the Model page`.

### Task 5: Ingest — lưu 2 trường mới, chọn khung và thống kê giờ

**Files:**
- Modify: `backend/ingest/handler.py`
- Test: `tests/test_backend_integration_moto.py`
  - `_ingest` nhận thêm `detections` và `model_version`.
  - `_ingest` ghi ảnh giả vào `test-hub-bucket` khi có `with_frame=True`, và đặt `source_bucket` cho capture.

**Interfaces:**
- Consumes: `model_health.capture_boxes`, `model_health.hour_stats` (Task 3).
- Produces:
  - `previous_hour(now_utc: datetime) -> str` (`YYYYMMDD-HH` theo ICT).
  - `cameras(ddb) -> list[tuple[str, str]]`: các cặp (`camera_id`, `store_code`) lấy từ `latest_stock`.
    `store_code` tách từ `capture_id` dạng `CAP-<code>-...`.
  - `captures_in_hour(ddb, camera_id: str, store_code: str, hour: str) -> list[dict]`: Query với
    `begins_with(capture_id, "CAP-<code>-<YYYYMMDD>-<HH>")`.
  - `sample_audit(s3, ddb, camera_id: str, items: list[dict], hour: str, rng: random.Random) -> str | None`:
    trả `audit_id`, hoặc `None` khi không có capture có ảnh.
  - `record_health(ddb, camera_id: str, hour: str, items: list[dict]) -> None`.
  - Action mới của `lambda_handler`:
    - `{"action": "sample_audits", "hour": "YYYYMMDD-HH"}`: chạy cả chọn khung lẫn thống kê cho giờ đó.
    - `{"action": "backfill_model_health", "days": 7}`.
  - `select_hourly_official` gọi thêm hai việc trên cho giờ trước.
  - Bảng captures lưu thêm `model_version` (mặc định `"unknown"`) và `detections_json` (chỉ khi record có `detections`).

- [ ] **Step 1: Viết test hỏng**
  - `test_previous_hour_is_in_ict`: `previous_hour(datetime(2026, 11, 23, 6, 24, tzinfo=timezone.utc)) == "20261123-12"`.
  - `test_capture_keeps_model_version_and_boxes`: ingest với `model_version="v3"` và 2 detections, rồi đọc lại item
    trong `test-captures`. `model_version == "v3"` và `json.loads(detections_json)` bằng đúng 2 hộp đã gửi. Ingest
    không có 2 trường thì `model_version == "unknown"` và không có `detections_json`.
  - `test_hourly_sampling_picks_one_frame_and_copies_it`:
    - Ingest 3 capture ở giờ 14 (`140700`, `140710`, `140710-2`) có ảnh, và 1 capture ở giờ 15.
    - Gọi `lambda_handler({"action": "sample_audits", "hour": "20261121-14"})`.
    - Bảng `test-audits` có đúng 1 item `AUD-CAM-S01-A-20261121-14`, `status == "pending"`, `capture_id` thuộc 3
      capture giờ 14.
    - `ai_boxes_json` khớp các hộp của capture đó.
    - Bucket analytics có object `audits/frames/CAM-S01-A/2026-11-21/<image_filename>`.
  - `test_sampling_the_same_hour_twice_keeps_one_audit`.
  - `test_an_hour_whose_captures_have_no_frame_gets_no_audit`: các capture có `image_key == ""`, không lỗi, 0 audit.
  - `test_health_item_for_the_hour`: sau `sample_audits`, `test-model-health` có item `CAM-S01-A` / `20261121-14`,
    `captures == 3`, có `expires_at`.
- [ ] **Step 2:** Chạy các test mới. Mong đợi: FAIL.
- [ ] **Step 3:** Viết code. Dùng `copy_object(CopySource={"Bucket": item["source_bucket"], "Key": item["image_key"]})`.
  Ghi có điều kiện `attribute_not_exists(audit_id)`; gặp `ConditionalCheckFailedException` thì bỏ qua. Lỗi ở một
  camera thì ghi log rồi chạy tiếp camera khác.
- [ ] **Step 4:** Chạy `pytest -q`. Mong đợi: tất cả PASS.
- [ ] **Step 5:** Commit `Ingest: keep model version and boxes, sample one frame per camera-hour, hourly health`.

### Task 6: API — danh sách, chi tiết, lưu và bỏ qua audit

**Files:**
- Modify: `backend/api/handler.py`. Thêm route trong khối đã qua `_require_groups(user, VALID_GROUPS)`. Mỗi route
  gọi thêm `_require_groups(user, WRITE_CORRECTION_GROUPS, event)`.
- Test: `tests/test_backend_integration_moto.py`

**Interfaces:**
- Consumes: `audit_scoring.validate_labels`, `VERDICTS`, `SKIP_REASONS` (Task 2); bảng `audits` (Task 5).
- Produces (JSON):
  - `GET /model/audits?status=pending|done|skipped&days=N` →
    `{"items": [{audit_id, camera_id, capture_id, capture_timestamp, model_version, status, n_boxes, labeled_by}], "counts": {"pending", "done", "skipped"}}`.
    Xếp mới nhất trước; `days` mặc định 7.
  - `GET /model/audits/{audit_id}` → `{audit fields..., "ai_boxes", "verdicts", "missed", "frame_url", "sku_choices": [{"label", "name"}]}`.
    `frame_url` ký 900 s trên `ANALYTICS_BUCKET`. `sku_choices` lấy từ SKU Master (`model_alias` khác rỗng), xếp theo `name`.
  - `PUT /model/audits/{audit_id}` body `{"verdicts", "missed"}` → 200 kèm audit đã lưu; 400 `{"error": "INVALID_LABELS", "message": "; ".join(errors)}`.
  - `POST /model/audits/{audit_id}/skip` body `{"reason", "note"}` → 200; lý do lạ thì 400.
  - Không thấy audit thì 404 `NOT_FOUND`.

- [ ] **Step 1: Viết test hỏng** (moto). Tạo audit bằng `sample_audits` như Task 5.
  - `test_datagent_cannot_open_model_routes`: `GET /v1/model/audits` với groups `datagent` → 403.
  - `test_list_and_detail_for_field_team`:
    - list có 1 item `pending`, `counts == {"pending": 1, "done": 0, "skipped": 0}`.
    - detail có `frame_url` khác rỗng, `ai_boxes` đúng số hộp, và trong `sku_choices` có `{"label": "hot160", "name": "Slide Hot & Spicy 160g"}`.
  - `test_saving_labels_marks_the_audit_done`: PUT verdict đủ → 200, `status == "done"`, `labeled_by == "tester@datagent.io"`.
  - `test_saving_without_a_verdict_for_every_box_is_refused`: thiếu 1 hộp → 400 `INVALID_LABELS`, audit vẫn `pending`.
  - `test_skip_needs_a_known_reason`: `{"reason": "rain"}` → 400; `{"reason": "blocked"}` → 200 và `status == "skipped"`.
  - `test_a_frame_without_boxes_is_saved_with_misses_only`: capture có ảnh nhưng 0 dòng, nên audit có `ai_boxes == []`.
    PUT `{"verdicts": [], "missed": [{"sku_id": "hot160", "x": 1, "y": 1}]}` → 200, `status == "done"`.
- [ ] **Step 2:** Chạy. Mong đợi: FAIL (404 hoặc thiếu route).
- [ ] **Step 3:** Viết code. `_parse_body` đã có.
- [ ] **Step 4:** Chạy `pytest -q`. Mong đợi: tất cả PASS.
- [ ] **Step 5:** Commit `API: list, open, label and skip frames for the Model page`.

### Task 7: API — tổng hợp và theo dõi tự động

**Files:**
- Modify: `backend/api/handler.py`
- Test: `tests/test_backend_integration_moto.py`

**Interfaces:**
- Consumes: `audit_scoring.summarize` (Task 2); bảng `model-health` (Task 5).
- Produces:
  - `GET /model/summary?days=N&model_version=V` →
    `{**summarize(...), "model_versions": [các phiên bản có audit done, mới nhất trước], "range": {"days": N}}`.
    `days=0` nghĩa là tất cả. Không truyền `model_version` hoặc truyền `all` thì lấy mọi phiên bản.
    `processing_ms` lấy từ `processing_ms_median` của các item `model-health` trong khoảng, mỗi item nhân `captures` lần.
  - `GET /model/health?days=N` → `{"items": [{camera_id, hour, ...hour_stats}]}`, xếp theo giờ tăng dần.

- [ ] **Step 1: Viết test hỏng**
  - `test_summary_without_labelled_frames_has_no_numbers`: mọi `kpis[*].value is None`, `n_audits == 0`.
  - `test_summary_after_labelling_one_frame`: dựng một audit có 2 hộp `hot160` bằng `_ingest`, rồi PUT với 1 hộp
    `correct` và 1 hộp `wrong_sku → original145`. Mong đợi `overall_identification_accuracy.value == 0.5`,
    `n_audits == 1`, `model_versions == ["v3"]`.
  - `test_summary_for_a_version_without_frames`: `model_version=v9` → `n_audits == 0`, mọi value `None`.
  - `test_health_lists_hours_in_order`.
- [ ] **Step 2:** Chạy. Mong đợi: FAIL.
- [ ] **Step 3:** Viết code.
- [ ] **Step 4:** Chạy `pytest -q`. Mong đợi: tất cả PASS.
- [ ] **Step 5:** Commit `API: Datagent KPIs, per-SKU errors, confusion and hourly health for the Model page`.

### Task 8: Frontend — client API, logic đếm, định dạng chỉ số

**Files:**
- Modify: `frontend/lib/api.ts`. Thêm type `ApiAuditListResponse`, `ApiAuditDetail`, `ApiModelSummary`,
  `ApiModelHealth`, và 6 method: `listAudits(status?, days?)`, `getAudit(id)`, `saveAudit(id, body)`,
  `skipAudit(id, reason, note?)`, `getModelSummary(days, modelVersion?)`, `getModelHealth(days)`.
- Create: `frontend/lib/audit-labeling.ts`, `frontend/lib/audit-labeling.test.ts`
- Create: `frontend/lib/model-ui.ts`, `frontend/lib/model-ui.test.ts`

**Interfaces:**
- Produces:
  - `type Verdict = "correct" | "wrong_sku" | "not_product"`
  - `type BoxLabel = { verdict: Verdict | null; trueSku: string | null }`
  - `nextVerdict(v: Verdict | null): Verdict | null`. Thứ tự: `null` → `correct` → `wrong_sku` → `not_product` → `null`.
  - `totalsBySku(aiBoxes: {box_id: number; sku_id: string | null}[], labels: Record<number, BoxLabel>, missed: {sku_id: string}[]): Record<string, {model: number; truth: number}>`
  - `canSave(aiBoxes, labels): boolean`: mọi hộp có verdict, và hộp `wrong_sku` có `trueSku`.
  - `toPayload(labels, missed): {verdicts: {box_id: number; verdict: Verdict; true_sku_id?: string}[]; missed: {sku_id: string; x: number; y: number}[]}`
  - `kpiDisplay(name: string, kpi: {value: number | null; target: [string, number]; met: boolean | null; n: number}): {text: string; targetText: string; tone: "met" | "missed" | "none"}`.
    `value === null` thì `text === "—"`, `tone === "none"`. Chỉ số tỷ lệ hiện `%` (1 chữ số thập phân), MAE hiện 2 chữ số, ms hiện số nguyên.

- [ ] **Step 1: Viết test hỏng** (`node:test`, `assert`).
  - `nextVerdict` đi đủ vòng.
  - `totalsBySku` với 2 hộp `hot160` (1 `correct`, 1 `wrong_sku → original145`) và 1 điểm sót `hot160` →
    `{hot160: {model: 2, truth: 2}, original145: {model: 0, truth: 1}}`.
  - `canSave`: một hộp chưa chấm → `false`; hộp `wrong_sku` chưa chọn vị → `false`; không có hộp nào → `true`.
  - `kpiDisplay("overall_identification_accuracy", {value: 0.5, target: [">=", 0.6], met: false, n: 4})` →
    `{text: "50.0%", targetText: "≥ 60%", tone: "missed"}`; khi `value: null` → `text: "—"`.
- [ ] **Step 2:** `cd frontend && npm test`. Mong đợi: FAIL vì chưa có module.
- [ ] **Step 3:** Viết code. Thêm method vào `createApiClient`, theo kiểu `requestWithAuth` đang dùng.
- [ ] **Step 4:** `npm test`. Mong đợi: tất cả PASS (cả test cũ).
- [ ] **Step 5:** Commit `Website: API client and labelling logic for the Model page`.

### Task 9: Frontend — trang `/model`, màn hình đếm, mục trên thanh bên

**Files:**
- Create: `frontend/app/(dashboard)/model/page.tsx`. Chỉ render `<ModelQualityView />`, giống `category/page.tsx`.
- Create: `frontend/components/model/ModelQualityView.tsx`. Gồm bộ lọc, 12 ô chỉ số, bảng theo SKU, ma trận,
  biểu đồ theo ngày, và theo dõi tự động.
- Create: `frontend/components/model/AuditLabeler.tsx`. Ảnh và hộp SVG (dùng `lib/frame-geometry.ts` như
  `FrameViewer`), xoay vòng verdict, chọn vị, điểm sót, bảng tổng, và các nút Save, Skip, Next.
- Modify: `frontend/components/layout/Sidebar.tsx`. Thêm mục `{ id: "model", label: "Model", href: "/model", icon: Gauge }`.
  Chỉ hiện khi `hasGroup("team_admin", "field_team")`. Thêm `"model"` vào `NavItemId`.

- [ ] **Step 1:** Đọc `frontend/node_modules/next/dist/docs/` phần App Router (pages, `useSearchParams`, static
  export) trước khi viết.
- [ ] **Step 2:** Viết trang và các component. Màn hình đếm mở bằng `?audit=<id>`, hoặc audit `pending` cũ nhất
  khi bấm "Label frames". Chưa đăng nhập, hoặc không thuộc 2 nhóm trên, thì hiện thông báo không có quyền và không
  gọi API.
- [ ] **Step 3:** `cd frontend && npm run build`. Mong đợi: biên dịch xong, có trang `/model` tĩnh, TypeScript qua.
  Chạy thêm `npx eslint components/model app/(dashboard)/model lib/audit-labeling.ts lib/model-ui.ts`. Mong đợi:
  không có lỗi mới.
- [ ] **Step 4:** Chạy bản build ở `http://localhost:3000` (`python -m http.server 3000 --bind 127.0.0.1 --directory frontend/out`).
  Mở `/model` bằng Edge chạy ngầm (cách đăng nhập ở Task 10, bước 4). Mong đợi: trang hiện "—" khi chưa có audit `done`.
- [ ] **Step 5:** Commit `Website: Model page with frame labelling, Datagent KPIs and live health`.

### Task 10: Triển khai và kiểm trên hệ thống thật

- [ ] **Step 1 — Backend:**
  - Đóng gói 2 zip theo commit (Global Constraints) và đưa lên `s3://milk-development-754361433393/releases/backend/<sha>/`.
  - Tạo change set từ `infra/backend.yaml` của repo:
    - `ApiCodeKey` và `IngestCodeKey` mới; các tham số khác dùng `UsePreviousValue=true`; `CAPABILITY_NAMED_IAM`.
  - Change set chỉ được có: Add `AuditsTable` và `ModelHealthTable`; Modify `LambdaExecutionRole`, `ApiLambda`,
    `IngestLambda`; cộng các mục "Dynamic" đi kèm.
  - Chạy change set. Kiểm `CodeSha256` của 2 Lambda khớp 2 zip.
- [ ] **Step 2 — Dữ liệu đầu:**
  - Gọi ingest `{"action": "backfill_model_health", "days": 7}`.
  - Gọi `sample_audits` cho các giờ có capture của hôm nay, để có audit `pending`.
  - Kiểm: số item `model-health` lớn hơn 0; có audit `pending`; ảnh có trong `audits/frames/`.
- [ ] **Step 3 — Worker** (hoang đã cho phép ngày 23/11):
  - Sao lưu `config.py`, `cvoutput.py`, `counter.py` và `worker.env` thành `*.bak-20261123b`.
  - Chép 3 file; thêm dòng `MILK_MODEL_VERSION=long-2026-10-13+slide-v3` vào `worker.env`.
  - Kiểm import bằng `.venv` của worker, rồi khởi động lại `milk-worker`.
  - Kiểm: `results/*.json` mới có `model_version` và `detections`; không còn cặp khung trùng.
- [ ] **Step 4 — Tài khoản kiểm:**
  - Tạo `model-check@example.com` thuộc nhóm `team_admin`, có TOTP. Mật khẩu và khoá lưu ở SSM SecureString
    `/milk-demo/web/model-check-account`, cách làm như `api-check`.
- [ ] **Step 5 — Frontend:**
  - Build rồi deploy tay lên Amplify (`milk-demo-frontend`, `d2k8euxy0yoiv8`).
  - Quét bundle không có chuỗi mẫu.
  - Chạy bài kiểm đầu cuối trên trang thật:
    - `model-check` thấy mục Model; mở `/model`, các ô chỉ số là "—".
    - Chấm và lưu 1 khung thật; các ô chuyển sang số, `n_audits` = 1.
    - Tài khoản `api-check` (`datagent`) không thấy mục Model; gọi API `/model/audits` nhận 403.
- [ ] **Step 6 — Push và ghi lại:**
  - `git push origin main`.
  - Ghi một mục Nhật ký vào HOANG-P10 trên Confluence: việc đã làm, số đo, link spec và plan.
