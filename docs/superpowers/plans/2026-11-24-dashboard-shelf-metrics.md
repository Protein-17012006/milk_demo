# Dashboard: OSA, hết hàng, bổ sung hàng — kế hoạch làm

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mọi ô trống trên Dashboard có số thật (OSA, Top 50 SKU Accuracy, Restock Rate, 4 tab xu hướng, Recent Shelf
Activities), hoặc nói rõ còn thiếu gì; team_admin đặt giờ mở cửa và danh sách SKU của tiệm trong Settings.

**Architecture:**
- Module thuần `backend/shelf.py`: dựng lần kiểm 5 phút, chạy trạng thái kệ, gộp theo giờ và ngày.
- Lambda ingest: job `shelf_tick` chạy mỗi 5 phút, ghi vào 2 bảng mới `shelf` và `shelf-events`. `shelf_recompute`
  tính lại 15 ngày.
- Lambda API:
  - route mới `/stores/{id}/shelf-plan`, `/reports/trends`, `/shelf-events`;
  - `/kpi` thêm trường mới;
  - `/reports/series` đọc dữ liệu đã gộp theo ngày.
- Trang Dashboard và khối "Shelf plan" trong Settings gọi các route đó.

**Tech Stack:**
- Python 3.12 (Lambda, boto3), pytest + moto.
- CloudFormation (`infra/backend.yaml`).
- Next.js 16 static export, React, recharts, `node --test`.

**Spec:** `docs/superpowers/specs/2026-11-24-dashboard-shelf-metrics-design.md`

## Global Constraints

- **Không có số liệu giả.** Ô nào thiếu số thì API trả `null` kèm `blocked_reason`, giao diện hiện "—" và câu chỉ việc
  cần làm. Không bao giờ hiện 0% thay cho "không có dữ liệu".
- **Giờ và ngày theo ICT (UTC+7).** Lambda chạy theo UTC.
- **Lần kiểm:** khoảng 5 phút theo ICT, bắt đầu ở :00, :05, :10…, mã `YYYYMMDD-HHMM` (phút đầu khoảng).
- **Hằng số trong `backend/shelf.py`:**

  | Tên | Giá trị |
  |---|---|
  | `BUCKET_MINUTES` | 5 |
  | `CONFIDENT` | 0.70 |
  | `LOW_MAX` | 2 |
  | `DEPLETED_DROP` | 3 |
  | `RESTOCK_RISE` | 2 |
  | `SETTLE_MINUTES` | 2 |
  | `MAX_BUCKETS_PER_TICK` | 36 |
  | `RECOMPUTE_DAYS` | 15 |
  | `SUGGEST_DAYS` | 7 |
  | `CHECK_TTL_DAYS` | 15 |
  | `ROLLUP_TTL_DAYS` | 90 |
- **Bảng mới:**

  | Bảng | Khoá |
  |---|---|
  | `milk-backend-<env>-shelf` | `store_id` (HASH) + `key` (RANGE) |
  | `milk-backend-<env>-shelf-events` | `store_id` (HASH) + `event_key` (RANGE) |

  - TTL dùng thuộc tính `expires_at`.
  - Trong bảng `shelf`, `key` có 4 dạng: `state`, `check#<bucket>`, `hour#YYYYMMDD-HH`, `day#YYYYMMDD`.
  - `event_key` có dạng `<bucket>#<sku_id>#<type>`.
- **Loại sự kiện:**

  | Lưu trong dữ liệu | Hiện trên giao diện |
  |---|---|
  | `OOS` | "OOS" |
  | `LOW_STOCK` | "LOW STOCK" |
  | `DEPLETED` | "DEPLETED" |
  | `RESTOCKED` | "RESTOCKED" |
- **Trường mới trong `store_list`:** `open_time`, `close_time` ("HH:MM"), `expected_skus` (list), `shelf_plan_updated_by`,
  `shelf_plan_updated_at`, `shelf_recompute_requested_at`.
- **Lý do chặn** (`blocked_reason`): `no_hours`, `no_expected`, `no_checks`, `no_previous`, `no_labels`.
- **Phân quyền:** `PUT /stores/{id}/shelf-plan` chỉ cho `team_admin`; các route mới khác cho mọi nhóm đã duyệt.
- **Mặc định khoảng thời gian:** 14 ngày, trên API và trên trang.
- **Dấu trừ hiển thị** là "−" (U+2212).
- **Gói Lambda** để file ở gốc zip:
  - API: `handler.py` (từ `backend/api/`), `common.py`, `audit_scoring.py`, `model_health.py`, `shelf.py`.
  - Ingest: `handler.py` (từ `backend/ingest/`), `common.py`, `model_health.py`, `shelf.py`.
- **Next.js:** đọc tài liệu trong `frontend/node_modules/next/dist/docs/` trước khi viết code frontend
  (`frontend/AGENTS.md`).
- **Chạy test:** từ gốc repo chạy `"$VENV/Scripts/python.exe" -m pytest -q`. `VENV` là venv py3.12 ở scratchpad, dựng
  từ `requirements-dev.txt`. Frontend chạy `cd frontend && npm test`.
- **Commit:** dùng `-c user.name="Nguyen Huy Hoang" -c user.email=193206418+Protein-17012006@users.noreply.github.com`,
  và kết thúc bằng dòng `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Tiệm mới:** chưa đặt giờ, chưa có danh sách, chưa có capture nào. API trả `null` cùng lý do chặn, không lỗi 500,
   không ra 0%. Test ở Task 6.
2. **Capture đến trễ, `shelf_tick` chạy 2 lần hoặc chồng nhau:** không đếm trùng, không sinh sự kiện trùng. Test ở
   Task 4.
3. **Dòng không nhận ra (`sku_id` rỗng), hoặc SKU không có trong SKU master:** bị bỏ qua khi đếm, không gây lỗi. Test ở
   Task 1.
4. **Giờ nhập sai:** "25:00", "6:00", giờ đóng không sau giờ mở, hoặc SKU lạ → `PUT` trả 400 và không lưu gì. Tiệm mở
   tới "23:59" vẫn hợp lệ. Test ở Task 1 và 5.
5. **SKU trong danh sách mà chưa từng thấy (luôn 0):**
   - lần đầu: L = 0, trạng thái OOS, không sinh sự kiện;
   - OSA tính nó là không có hàng;
   - `oos_now` đếm nó.

   Test ở Task 2 và 6.

---

### Task 0: Đưa spec và kế hoạch vào repo

- [ ] **Step 1:** Commit `docs/superpowers/specs/2026-11-24-dashboard-shelf-metrics-design.md` và file kế hoạch này, với
  message `Docs: design and plan for the Dashboard shelf metrics (hoang approved)`.

### Task 1: Lần kiểm và giờ mở cửa (`backend/shelf.py`)

**Files:**
- Create: `backend/shelf.py`
- Test: `tests/test_shelf.py`

**Interfaces:**
- Consumes:
  - `common.lower_median(values: list[int]) -> int`
  - `common.resolve_sku_alias(raw_sku_id, raw_sku_name=None) -> (sku_id | None, name | None)`
  - `model_health.capture_boxes(item) -> list[{box_id, sku_id (model label), conf, box}]`
- Produces:
  - các hằng số ở Global Constraints;
  - `bucket_of(capture_ts: str) -> str`
  - `bucket_time(bucket: str) -> datetime`: đầu khoảng, có múi ICT
  - `add_buckets(bucket: str, n: int) -> str`
  - `is_open(bucket: str, open_time: str | None, close_time: str | None) -> bool`
  - `valid_hours(open_time: str, close_time: str) -> bool`
  - `build_check(bucket: str, captures: list[dict]) -> dict`, trả về
    `{"bucket", "counts": {sku_id: int}, "captures": int, "cameras": [sorted], "confident_skus": [sorted]}`

- [ ] **Step 1: Viết test.** Trong file test, helper `cap(camera, ts, counts: dict[str, int], boxes=None)` dựng một
  capture giống item thật của bảng `captures`:
  - `rows_json`: mỗi SKU một dòng `{"sku_id": <tên>, "model_alias": <nhãn>, "unit_count": n, "confidence_score": 0.9,
    "bounding_box": [...]}`;
  - `detections_json` lấy từ `boxes`.

```python
def test_bucket_is_the_five_minutes_the_capture_falls_in():
    assert bucket_of("2026-11-23T14:07:31+07:00") == "20261123-1405"
    assert bucket_of("2026-11-23T14:10:00+07:00") == "20261123-1410"
    assert bucket_of("2026-11-23T07:02:00+00:00") == "20261123-1400"  # UTC in, ICT out

def test_add_buckets_crosses_midnight():
    assert add_buckets("20261123-2355", 1) == "20261124-0000"

def test_open_hours_include_open_and_exclude_close():
    assert is_open("20261123-0600", "06:00", "22:00") and is_open("20261123-2155", "06:00", "22:00")
    assert not is_open("20261123-0555", "06:00", "22:00") and not is_open("20261123-2200", "06:00", "22:00")
    assert not is_open("20261123-1200", None, None)

def test_valid_hours():
    assert valid_hours("06:00", "22:00") and valid_hours("00:00", "23:59")
    for bad in [("22:00", "06:00"), ("06:00", "06:00"), ("25:00", "26:00"), ("6:00", "22:00"), ("06:00", "")]:
        assert not valid_hours(*bad)

def test_check_counts_are_the_median_per_camera_summed_over_cameras():
    caps = [cap("CAM-A", "2026-11-23T14:05:10+07:00", {"Slide Cheese 145g": 3}),
            cap("CAM-A", "2026-11-23T14:06:10+07:00", {"Slide Cheese 145g": 5}),
            cap("CAM-A", "2026-11-23T14:07:10+07:00", {"Slide Cheese 145g": 4}),
            cap("CAM-B", "2026-11-23T14:06:30+07:00", {"Slide Cheese 145g": 2})]
    check = build_check("20261123-1405", caps)
    assert check["counts"] == {"Slide Cheese 145g": 6} and check["captures"] == 4
    assert check["cameras"] == ["CAM-A", "CAM-B"]

def test_a_sku_missing_from_a_capture_counts_zero_there():
    caps = [cap("CAM-A", t, c) for t, c in [("2026-11-23T14:05:10+07:00", {"X": 4}),
            ("2026-11-23T14:06:10+07:00", {}), ("2026-11-23T14:07:10+07:00", {})]]
    assert build_check("20261123-1405", caps)["counts"] == {"X": 0}

def test_unrecognized_rows_are_left_out():
    # a row with sku_id None (UNRECOGNIZED) adds nothing
    ...  # build one capture with rows_json [{"sku_id": None, "unit_count": 3, ...}]
    assert build_check("20261123-1405", caps)["counts"] == {}

def test_confident_skus_need_one_box_at_070():
    boxes = [{"sku_id": "hot160", "conf": 0.69, "box": [0, 0, 5, 5]}, {"sku_id": "cheese145", "conf": 0.70, "box": [9, 0, 5, 5]}]
    caps = [cap("CAM-A", "2026-11-23T14:05:10+07:00", {"Slide Hot & Spicy 160g": 1, "Slide Cheese 145g": 1}, boxes)]
    assert build_check("20261123-1405", caps)["confident_skus"] == ["Slide Cheese 145g"]
```

- [ ] **Step 2: Chạy test, phải FAIL.** Lệnh: `pytest tests/test_shelf.py -q`. Mong đợi: `ModuleNotFoundError: shelf`.
- [ ] **Step 3: Viết `backend/shelf.py`.**
  - Số đếm mỗi SKU lấy từ `rows_json`: `row["sku_id"]` (tên sản phẩm). Bỏ dòng có `sku_id` rỗng.
  - Mỗi camera lấy `lower_median` qua các capture của camera đó trong khoảng, SKU vắng trong capture nào thì tính 0
    ở capture đó. Rồi cộng các camera lại.
  - `confident_skus`: các hộp từ `capture_boxes` có `conf ≥ CONFIDENT`. Nhãn của hộp đổi ra tên bằng
    `resolve_sku_alias(label)[0]`.
- [ ] **Step 4:** Chạy lại test. Mong đợi: PASS.
- [ ] **Step 5:** Commit `Shelf metrics: 5-minute checks and opening hours (pure module)`.

### Task 2: Trạng thái kệ (`backend/shelf.py`)

**Files:**
- Modify: `backend/shelf.py`
- Test: `tests/test_shelf.py`

**Interfaces:**
- Produces:
  - `status_of(level: int) -> str`: 0 → `"OOS"`; 1–2 → `"LOW"`; ≥ 3 → `"IN_STOCK"`.
  - `step_state(state: dict | None, units: int, bucket: str) -> tuple[dict, dict | None]`:
    - `state` có các khoá `{"L", "status", "since", "prev", "prev_bucket", "oos_checks"}`;
    - sự kiện trả về có dạng `{"type", "at", "delta", "level_before", "level_after", "duration_min"}`. `sku_id` do
      bên gọi thêm vào.

- [ ] **Step 1: Viết test.** Helper `walk(levels, state=None)` trong file test: cho `step_state` đi qua các lần kiểm
  liền nhau, bắt đầu từ `20261123-1400`, rồi trả về danh sách sự kiện khác `None` và trạng thái cuối.

```python
def test_first_two_equal_checks_set_the_level_without_an_event():
    events, st = walk([3, 3]); assert events == [] and (st["L"], st["status"]) == (3, "IN_STOCK")
    events, st = walk([0, 0]); assert events == [] and (st["L"], st["status"]) == (0, "OOS")

def test_two_zero_checks_make_an_out_of_stock():
    events, _ = walk([5, 5, 0, 0])
    assert events == [{"type": "OOS", "at": "20261123-1410", "delta": -5, "level_before": 5, "level_after": 0, "duration_min": None}]

def test_one_hidden_check_is_not_an_event():
    assert walk([5, 5, 0, 5, 5])[0] == []

def test_low_stock_wins_over_depleted():
    assert [(e["type"], e["delta"], e["level_after"]) for e in walk([8, 8, 2, 2])[0]] == [("LOW_STOCK", -6, 2)]

def test_depleted_needs_a_drop_of_three():
    events, st = walk([8, 8, 6, 6]); assert events == [] and st["L"] == 6
    assert [(e["type"], e["delta"], e["level_after"]) for e in walk([12, 12, 8, 8])[0]] == [("DEPLETED", -4, 8)]

def test_restocked_needs_a_rise_of_two():
    events, st = walk([8, 8, 9, 9]); assert events == [] and st["L"] == 9
    assert [(e["type"], e["delta"], e["level_after"]) for e in walk([8, 8, 24, 24])[0]] == [("RESTOCKED", 16, 24)]

def test_restock_after_out_of_stock_carries_its_open_minutes():
    events, _ = walk([5, 5, 0, 0, 0, 0, 6, 6])
    assert [(e["type"], e["at"], e["duration_min"]) for e in events] == [("OOS", "20261123-1410", None), ("RESTOCKED", "20261123-1430", 20)]
```

- [ ] **Step 2:** Chạy test. Mong đợi: FAIL vì `step_state` chưa có.
- [ ] **Step 3: Viết `status_of` và `step_state`.**
  - Bảng luật và các quy tắc kèm theo lấy đúng mục 1 của spec.
  - x1 = `state["prev"]`, x2 = `units`. Thời điểm sự kiện là `prev_bucket`.
  - `oos_checks` đếm các lần kiểm mang trạng thái OOS: đặt bằng 2 khi sự kiện OOS xảy ra, và cộng 1 mỗi lần kiểm sau đó
    khi trạng thái vẫn là OOS.
  - Ở sự kiện RESTOCKED kết thúc một lần OOS: `duration_min = 5 × (oos_checks − 1)`. Phải trừ 1 vì lần kiểm x1 đã có
    hàng.
- [ ] **Step 4:** Chạy lại test. Mong đợi: PASS.
- [ ] **Step 5:** Commit `Shelf metrics: shelf state and events (OOS, low stock, depleted, restocked)`.

### Task 3: Gộp theo giờ, ngày và tổng của một khoảng (`backend/shelf.py`)

**Files:**
- Modify: `backend/shelf.py`
- Test: `tests/test_shelf.py`

**Interfaces:**
- Produces:
  - `rollup(checks: list[dict], events: list[dict]) -> dict`.
    - Mỗi check có `bucket`, `counts`, `open`, `expected` và `confident_skus`.
    - Kết quả:
      `{"checks": int, "max_total": int, "confident_skus": [sorted], "skus": {sku: {"checks", "available", "units_sum", "oos_started", "restock_units", "restock_events"}}}`.
    - `checks` ở cấp trên đếm số lần kiểm được tính, tức `open` và `expected` không rỗng.
  - `merge(rollups: list[dict]) -> dict`: cộng các số đếm, lấy max của `max_total`, hợp các `confident_skus`.
  - `totals(rollups: list[dict], skus: set[str] | None = None) -> dict`: trả
    `{"checks", "available", "osa", "restock_units", "restock_events", "oos_started", "store_checks", "avg_total_units"}`.
    - `osa` = `available / checks`.
    - `avg_total_units` = Σ `units_sum` / `store_checks`.
    - Cả hai là `None` khi mẫu số bằng 0.
  - `change_pct(current: float | None, previous: float | None) -> float | None`: làm tròn 1 chữ số thập phân; trả
    `None` khi `previous` là `None` hoặc 0.

- [ ] **Step 1: Viết test.**

```python
def test_only_open_checks_of_expected_skus_count():
    open_c = {"bucket": "20261123-1400", "counts": {"A": 3, "C": 9}, "open": True, "expected": ["A", "B"], "confident_skus": []}  # B not seen
    shut_c = {"bucket": "20261123-1405", "counts": {"A": 5}, "open": False, "expected": ["A", "B"], "confident_skus": ["C"]}
    r = rollup([open_c, shut_c], [])
    assert r["checks"] == 1 and r["max_total"] == 3 and r["confident_skus"] == ["C"]
    assert r["skus"]["A"] == {"checks": 1, "available": 1, "units_sum": 3, "oos_started": 0, "restock_units": 0, "restock_events": 0}
    assert r["skus"]["B"]["available"] == 0 and "C" not in r["skus"]

def test_events_feed_out_of_stock_and_restock_numbers():
    ev = [{"sku_id": "A", "type": "OOS", "delta": -5}, {"sku_id": "A", "type": "RESTOCKED", "delta": 6},
          {"sku_id": "B", "type": "RESTOCKED", "delta": 2}]
    r = rollup([], ev)
    assert (r["skus"]["A"]["oos_started"], r["skus"]["A"]["restock_units"], r["skus"]["B"]["restock_events"]) == (1, 6, 1)

def test_merge_adds_hours_into_a_day():
    ...  # two hour rollups: checks 12 and 10, max_total 9 and 14 → checks 22, max_total 14

def test_osa_is_available_over_counted_checks_and_filters_by_sku():
    r = {"checks": 2, "max_total": 7, "confident_skus": [], "skus": {
        "A": {"checks": 2, "available": 2, "units_sum": 7, "oos_started": 0, "restock_units": 0, "restock_events": 0},
        "B": {"checks": 2, "available": 1, "units_sum": 1, "oos_started": 1, "restock_units": 0, "restock_events": 0}}}
    t = totals([r]); assert (t["osa"], t["avg_total_units"]) == (0.75, 4.0)
    assert totals([r], {"B"})["osa"] == 0.5
    assert totals([])["osa"] is None

def test_change_pct():
    assert change_pct(13.4, 10.0) == 34.0
    assert change_pct(5, 0) is None and change_pct(5, None) is None
```

- [ ] **Step 2:** Chạy test. Mong đợi: FAIL.
- [ ] **Step 3:** Viết `rollup`, `merge`, `totals`, `change_pct`. SKU có trong `expected` mà không có trong `counts`
  thì tính 0 đơn vị: vẫn tính là một lần kiểm, nhưng không có hàng.
- [ ] **Step 4:** Chạy lại test. Mong đợi: PASS.
- [ ] **Step 5:** Commit `Shelf metrics: hour and day rollups, period totals`.

### Task 4: `shelf_tick` và `shelf_recompute` (Lambda ingest)

**Files:**
- Modify: `backend/ingest/handler.py`
- Test: `tests/test_backend_integration_moto.py`
  - thêm `("test-shelf", "store_id", "key")` và `("test-shelf-events", "store_id", "event_key")` vào
    `_create_mock_infra`;
  - thêm `SHELF_TABLE` và `SHELF_EVENTS_TABLE` vào biến môi trường của `_backend`.

**Interfaces:**
- Consumes: mọi hàm của Task 1–3.
- Produces:
  - biến môi trường mới cho ingest: `SHELF_TABLE`, `SHELF_EVENTS_TABLE`, `STORE_LIST_TABLE`.
  - `shelf_tick(ddb_resource, now_utc: datetime) -> dict`, trả `{"action": "shelf_tick", "stores": {store_id: processed}}`
  - `shelf_recompute(ddb_resource, store_id: str, days: int, now_utc: datetime) -> dict`
  - `lambda_handler` nhận thêm 2 action:
    - `{"action": "shelf_tick", "now": <ISO, tùy chọn>}`
    - `{"action": "shelf_recompute", "store_id": ..., "days": 15, "now": <ISO, tùy chọn>}`
  - Item `check#` lưu thêm `open`, `expected`, `expires_at`.
  - Item `hour#`, `day#` và sự kiện có `expires_at`.

- [ ] **Step 1: Viết test.** Mỗi test làm như sau:
  - ghi vào `test-store-list` mục `DEMO-S01` có `open_time "06:00"`, `close_time "22:00"`,
    `expected_skus ["Slide Cheese 145g"]`;
  - tạo capture bằng `_ingest(ingest, "CAM-S01-A", hhmmss, [("cheese145", n)])`. Danh sách rỗng nghĩa là không thấy
    lon nào;
  - gọi tick bằng `ingest.lambda_handler({"action": "shelf_tick", "now": "2026-11-21T14:22:00+07:00"})`.

  Các test:
  - `test_shelf_tick_finds_an_out_of_stock`: capture lúc 140010 và 140510 có 5 lon, lúc 141010 và 141510 không có
    lon nào. Mong đợi: đúng 1 sự kiện `20261121-1410#Slide Cheese 145g#OOS`.
  - `test_shelf_tick_twice_counts_once`: chạy tick 2 lần với cùng `now`. Mong đợi: `hour#20261121-14` có
    `skus["Slide Cheese 145g"]["checks"] == 4`, và vẫn chỉ có 1 sự kiện.
  - `test_a_bucket_closed_under_two_minutes_waits`: `now` = 14:21:30. Mong đợi: `state.last_bucket == "20261121-1410"`.
  - `test_closed_hours_do_not_count`: `close_time "14:10"`. Mong đợi: không có sự kiện nào, và
    `hour#20261121-14.checks == 2`.
  - `test_a_saved_plan_is_recomputed_on_the_next_tick`:
    - sau lần tick đầu, đổi `expected_skus` thành `["Slide Cheese 145g", "Slide Hot & Spicy 160g"]` và đặt
      `shelf_recompute_requested_at`;
    - tick lại. Mong đợi: cờ đã bị xoá, và `hour#…14` có `skus["Slide Hot & Spicy 160g"] == {"checks": 4, "available": 0, ...}`.
- [ ] **Step 2:** Chạy `pytest tests/test_backend_integration_moto.py -q -k shelf`. Mong đợi: FAIL.
- [ ] **Step 3: Viết code trong `backend/ingest/handler.py`.**
  - **Tiệm và camera:** lấy tiệm từ `store_list`. Camera của tiệm là các `camera_id` trong `latest_stock` có
    `store_id` đó; mã tiệm lấy từ `capture_id`, như `cameras()`.
  - **Capture của khoảng:** `captures_between(...)` Query `capture_id` between `CAP-<mã>-YYYYMMDD-HHMM00` và
    `CAP-<mã>-YYYYMMDD-HHMM59~`, với HHMM là phút cuối khoảng.
  - **Danh sách SKU:** dùng `expected_skus` đã lưu. Nếu chưa lưu, lấy hợp các `confident_skus` của các `day#` trong
    `SUGGEST_DAYS` ngày. SKU trong danh sách mà không có trong `counts` của lần kiểm thì đưa 0 vào `step_state`.
  - **Đi qua các khoảng:** bắt đầu ở `add_buckets(last_bucket, 1)`. Nếu chưa có `state`, bắt đầu từ khoảng đầu tiên có
    capture trong 7 ngày. Dừng khi khoảng chưa đóng đủ `SETTLE_MINUTES`, hoặc đã xử lý `MAX_BUCKETS_PER_TICK` khoảng.
  - **Ghi `state`:** điều kiện `last_bucket` vẫn bằng giá trị cũ. Nếu `ConditionalCheckFailedException` thì dừng tiệm
    đó trong lượt này.
  - **Ghi `hour#` và `day#`:** dùng SET, tính lại từ `check#` của giờ đó, rồi từ các `hour#` của ngày.
  - **Tính lại:** nếu tiệm có `shelf_recompute_requested_at` thì gọi `shelf_recompute` trước, rồi REMOVE cờ với điều
    kiện giá trị cờ không đổi. `shelf_recompute` làm theo mục 4 của spec:
    1. dựng lại `check#` từ `captures` cho phần còn trong 7 ngày;
    2. xoá `state`, `hour#`, `day#` và sự kiện trong khoảng tính lại (dùng BatchWrite);
    3. chạy lại các `check#` theo thứ tự thời gian. `open` và `expected` tính lại theo kế hoạch kệ hiện tại;
       `expected` mặc định lấy từ `confident_skus` của các `check#`.
- [ ] **Step 4:** Chạy lại test, rồi chạy cả bộ `pytest -q`. Mong đợi: PASS hết.
- [ ] **Step 5:** Commit `Ingest: shelf_tick every 5 minutes and shelf_recompute`.

### Task 5: Kế hoạch kệ qua API (`/stores/{store_id}/shelf-plan`)

**Files:**
- Modify: `backend/api/handler.py`
- Test: `tests/test_backend_integration_moto.py`

**Interfaces:**
- Consumes: `shelf.valid_hours`, các `day#` của Task 4.
- Produces:
  - biến môi trường mới cho API: `SHELF_TABLE`, `SHELF_EVENTS_TABLE`.
  - `_now() -> datetime`: trả giờ hiện tại có múi ICT. Test thay bằng monkeypatch.
  - `GET /stores/{id}/shelf-plan` trả
    `{"store_id", "open_time", "close_time", "expected_skus", "source": "saved"|"suggested", "suggested": [{"sku_id", "last_seen": "YYYY-MM-DD"}], "updated_by", "updated_at"}`.
  - `PUT /stores/{id}/shelf-plan`: body `{"open_time", "close_time", "expected_skus"}`.
    - Lỗi: 400 `INVALID_HOURS`; 400 `UNKNOWN_SKU` kèm `"skus": [...]`; 403 khi không phải `team_admin`; 404
      `STORE_NOT_FOUND`.
    - Lưu thành công: ghi thêm `shelf_recompute_requested_at = _now()`.

- [ ] **Step 1: Viết test.**
  - `test_shelf_plan_starts_as_the_suggestion`: ghi sẵn `day#20261121` có `confident_skus ["Slide Cheese 145g"]`.
    Mong đợi: `source == "suggested"` và
    `expected_skus == ["Slide Cheese 145g"] == [s["sku_id"] for s in body["suggested"]]`.
  - `test_only_team_admin_saves_a_shelf_plan`: `datagent` nhận 403; `team_admin` nhận 200 và `source == "saved"`.
  - `test_shelf_plan_rejects_bad_hours_and_unknown_skus`: các cặp giờ ("22:00", "06:00") và ("6:00", "22:00") trả 400
    `INVALID_HOURS`; SKU "No Such Milk" trả 400 `UNKNOWN_SKU`. Sau đó mục `store_list` không đổi.
  - `test_saving_a_plan_asks_for_a_recompute`: sau `PUT`, mục `store_list` có `shelf_recompute_requested_at`.
- [ ] **Step 2:** Chạy test. Mong đợi: FAIL, vì route chưa có nên trả 404.
- [ ] **Step 3:** Viết 2 route. Route `PUT` dùng `_require_groups(user, ADMIN_GROUPS, event)`.
- [ ] **Step 4:** Chạy lại test. Mong đợi: PASS.
- [ ] **Step 5:** Commit `API: shelf plan per store (opening hours and expected SKUs)`.

### Task 6: Số cho Dashboard (`/kpi`, `/reports/trends`, `/shelf-events`, `/reports/series`)

**Files:**
- Modify: `backend/api/handler.py`
- Test: `tests/test_backend_integration_moto.py`

**Interfaces:**
- Consumes: `shelf.totals`, `shelf.merge`, `shelf.change_pct`, `audit_scoring.summarize`.
- Produces:
  - **`GET /kpi?days=14&store_id=&category=`.** Các trường cũ giữ nguyên nghĩa. Thêm:
    - `osa {value, previous, blocked_reason}`
    - `restock_rate {units_per_day, previous_units_per_day, change_pct, blocked_reason}`
    - `oos_now {count, as_of, blocked_reason}`
    - `top_50_sku_accuracy {value, n_frames, scope_note, blocked_reason}`
  - **`GET /reports/trends?metric=total_stock|oos|accuracy|restock_volume|osa&days=&store_id=&category=`** trả
    `{"metric", "points": [{"t": "YYYY-MM-DD" | "YYYYMMDD-HH", "value": float | null}]}`. Với `days=1` thì theo giờ.
  - **`GET /shelf-events?days=&store_id=&category=&kind=all|alerts|restocked&limit=20&cursor=`** trả
    `{"items": [{..., "store_id", "store_name", "sku_name"}], "next_cursor"}`, mới nhất trước.
  - **`GET /reports/series`** trả mỗi ngày `{date, avg_units, max_units, checks}`, đọc từ `day#`.
- **Khoảng thời gian:**
  - khoảng hiện tại là `days` ngày, tính tới `_now()`;
  - khoảng trước liền kề có cùng độ dài;
  - với `days=1`, dùng các `hour#` của hôm nay và của hôm qua, tính tới cùng giờ.
- **Category:** lọc theo `category` của SKU master.

- [ ] **Step 1: Viết test.** Ghi thẳng các item `shelf` vào bảng, rồi monkeypatch `_now` về `2026-11-28T12:00+07:00`.
  - `test_kpi_osa_and_restock_rate_against_the_previous_period`:
    - 14 `day#` trong khoảng hiện tại cộng lại được checks 100, available 64, restock_units 201;
    - 14 `day#` của khoảng trước cộng lại được checks 100, available 60, restock_units 150.
    - Mong đợi: `osa == {"value": 0.64, "previous": 0.6, ...}`, `restock_rate.units_per_day == 14.4`,
      `previous_units_per_day == 10.7`, `change_pct == 34.0`. Số mỗi ngày làm tròn 1 chữ số thập phân; `change_pct`
      tính từ số chưa làm tròn.
  - `test_a_store_without_hours_is_blocked_not_zero`: Mong đợi: `osa.value is None` và
    `osa.blocked_reason == "no_hours"`. Các trường cũ vẫn có số.
  - `test_oos_now_counts_expected_skus_out_of_stock`: `state` có A OOS, B IN_STOCK, C OOS, trong đó C không thuộc danh
    sách. Mong đợi: `oos_now.count == 1`.
  - `test_top_50_accuracy_needs_labelled_frames`: không có audit `done` thì `value is None` và
    `blocked_reason == "no_labels"`. Có 1 audit `done` thì `n_frames == 1`.
  - `test_trends_per_day_and_per_hour`: `metric=restock_volume&days=7` trả 7 điểm. `days=1` trả các giờ tới 12h.
  - `test_shelf_events_filter_by_kind_and_category`:
    - `kind=alerts` chỉ có OOS, LOW_STOCK, DEPLETED;
    - `kind=restocked` chỉ có RESTOCKED;
    - `category=Milk` bỏ các SKU Slide.
  - `test_series_reads_day_rollups`: Mong đợi:
    `{"date": "2026-11-27", "avg_units": 4.0, "max_units": 7, "checks": 2}`.
- [ ] **Step 2:** Chạy test. Mong đợi: FAIL.
- [ ] **Step 3:** Viết code.
  - Tìm `day#` và `hour#` bằng Query `begins_with` hoặc `between` trên `key`.
  - Với "All stores", gộp các tiệm lại.
  - Top 50 SKU Accuracy:
    - lấy các audit `done` trong khoảng, của các camera thuộc tiệm;
    - `scope_note = "All SKUs: Datagent has not sent a top-50 list yet"`.
- [ ] **Step 4:** Chạy lại test, rồi chạy cả bộ `pytest -q`. Mong đợi: PASS hết.
- [ ] **Step 5:** Commit `API: OSA, restock rate, out-of-stock and accuracy for the Dashboard; shelf events and trends`.

### Task 7: Hạ tầng (`infra/backend.yaml`)

**Files:**
- Modify: `infra/backend.yaml`

- [ ] **Step 1:** Thêm `ShelfTable` và `ShelfEventsTable`. Cách làm giống `ModelHealthTable`: PAY_PER_REQUEST, PITR,
  SSE, TTL `expires_at`; khoá như Global Constraints.
- [ ] **Step 2:** Sửa `LambdaExecutionRole`:
  - thêm 2 ARN mới vào câu lệnh Get/Put/Update/Query/Scan đang có;
  - thêm một câu lệnh mới cho `dynamodb:DeleteItem` và `dynamodb:BatchWriteItem` trên 2 bảng mới.
- [ ] **Step 3:** Thêm biến môi trường:
  - API: `SHELF_TABLE`, `SHELF_EVENTS_TABLE`.
  - Ingest: `SHELF_TABLE`, `SHELF_EVENTS_TABLE`, `STORE_LIST_TABLE`.
- [ ] **Step 4:** Thêm `ShelfTickRule`:
  - `rate(5 minutes)`;
  - Input `'{"action": "shelf_tick"}'`;
  - kèm `ShelfTickPermission`, giống `HourlyOfficialRule`.
- [ ] **Step 5:** Chạy `cfn-lint infra/backend.yaml`. Nếu venv chưa có thì cài vào venv. Mong đợi: không lỗi.
- [ ] **Step 6:** Commit `Infra: shelf tables, 5-minute shelf tick, permissions`.

### Task 8: Lớp dữ liệu frontend (`lib/api.ts`, `lib/shelf-ui.ts`)

**Files:**
- Modify: `frontend/lib/api.ts`
- Create: `frontend/lib/shelf-ui.ts`
- Test: `frontend/lib/shelf-ui.test.ts`

**Interfaces:**
- Produces:
  - **Type mới:** `ApiShelfPlan`, `ApiShelfEvent`, `ApiTrendPoint`. `ApiKpiResponse` thêm các trường của Task 6.
  - **Hàm client:**
    - `getKpi(p?: {days?, storeId?, category?})`
    - `getTrends(metric, p?)`
    - `getShelfEvents(p?: {days?, storeId?, category?, kind?, limit?, cursor?})`
    - `getShelfPlan(storeId)`
    - `saveShelfPlan(storeId, body)`
    - `getReportsSeries(p?)`
  - **`shelf-ui.ts`:**
    - `TIMEFRAMES: {label: string; days: number}[]` gồm "Today"/1, "Last 7 days"/7, "Last 14 days (one cycle)"/14,
      "Last 90 days"/90;
    - `eventText(e: ApiShelfEvent): string`
    - `eventLabel(type): string`
    - `timeAgo(at: string, now: Date): string`
    - `ptsChange(cur: number | null, prev: number | null): string | null`
    - `pctChange(pct: number | null): string | null`
    - `blockedText(reason: string, storeName?: string): string`

- [ ] **Step 1: Viết test** (giá trị lấy theo Figma).

```ts
test("events read as on the Figma card", () => {
  assert.equal(eventText(ev("OOS", -6, 0)), "0 units (−6)");
  assert.equal(eventText(ev("RESTOCKED", 16, 24)), "+16 units (24 total)");
  assert.equal(eventText(ev("DEPLETED", -4, 8)), "−4 units (8 left)");
  assert.equal(eventText(ev("LOW_STOCK", -6, 2)), "2 left (−6)");
});
test("time ago from a 5-minute bucket", () => {
  const now = new Date("2026-11-24T10:00:00+07:00");
  assert.equal(timeAgo("20261124-0950", now), "10 min ago");
  assert.equal(timeAgo("20261124-0900", now), "1 hr ago");
  assert.equal(timeAgo("20261122-1000", now), "2 days ago");
});
test("changes against the previous period", () => {
  assert.equal(ptsChange(0.66, 0.62), "+4.0 pts");
  assert.equal(ptsChange(0.62, 0.66), "−4.0 pts");
  assert.equal(ptsChange(0.6, null), null);
  assert.equal(pctChange(34), "+34%");
  assert.equal(pctChange(-12.5), "−12.5%");
  assert.equal(pctChange(null), null);
});
test("a blocked card says what to do", () => {
  assert.equal(blockedText("no_hours", "DEMO-S01"), "Set opening hours for DEMO-S01 in Settings");
  assert.equal(blockedText("no_labels"), "Label frames on the Model page");
});
```

- [ ] **Step 2:** Chạy `npm test`. Mong đợi: FAIL vì module chưa có.
- [ ] **Step 3:** Viết `shelf-ui.ts` và các hàm client.
  - Chữ cho các lý do chặn khác: `no_expected` → "Choose this store's SKUs in Settings"; `no_checks` → "No checks in
    this period"; `no_previous` → "Needs the previous period's data to compare".
- [ ] **Step 4:** Chạy `npm test`. Mong đợi: PASS hết.
- [ ] **Step 5:** Commit `Website: shelf metric types, client calls and text helpers`.

### Task 9: Trang Dashboard

**Files:**
- Modify:
  - `frontend/components/reports/ReportsDashboard.tsx`
  - `frontend/components/reports/FilterBar.tsx`
  - `frontend/components/reports/KpiGrid.tsx`
  - `frontend/components/reports/TrendsInsightsChart.tsx`
  - `frontend/components/reports/RecentActivitiesCard.tsx`
  - `frontend/components/reports/MonthlyStockChart.tsx`
  - `frontend/lib/reports-ui.ts`

**Interfaces:**
- Consumes: Task 8.

- [ ] **Step 1: Bộ lọc.** Timeframe lấy từ `TIMEFRAMES`, mặc định 14 ngày. Store lấy từ `/stores`. Category gồm All,
  Milk, Snacks. Mọi lời gọi API đều gửi `days`, `storeId` và `category`.
- [ ] **Step 2: Ô KPI.**
  - OSA: % kèm `ptsChange` và sparkline `osa` theo ngày.
  - Top 50: % kèm "from n frames the team labelled" và `scope_note`.
  - Restock Rate: `pctChange` kèm "x units/day vs y" và sparkline `restock_volume`.
  - Ô bị chặn hiện "—" và `blockedText`.
  - "Total On-Shelf Units" có nhãn "now".
  - Mỗi ô có một dòng định nghĩa lấy từ mục 1 của spec, viết bằng tiếng Anh, ngắn gọn.
- [ ] **Step 3: Trends & Insights.**
  - Mỗi tab một chuỗi số thật, kèm một dòng nói tab đo gì.
  - Detection Accuracy ghi n khung.
  - Chuỗi rỗng hiện câu nói rõ lý do, không vẽ đường.
- [ ] **Step 4: Recent Shelf Activities.**
  - Hiện 20 sự kiện mới nhất. Bộ lọc All / Alerts only / Restocked đổi `kind` của lời gọi API.
  - Mỗi dòng: nhãn loại sự kiện, tên sản phẩm, `timeAgo`, tên tiệm, `eventText`.
  - Nút "View all activity" mở hộp thoại có nút "Load more", gọi tiếp bằng `cursor`.
- [ ] **Step 5: Shelf Stock Count.** Tooltip ghi "checks" thay cho "captures". Thêm phụ đề "Average units of the
  store's expected SKUs per check, opening hours only".
- [ ] **Step 6: Kiểm.**
  - `npm test` và `npm run build`: không lỗi.
  - `npx eslint components/reports lib/shelf-ui.ts lib/reports-ui.ts`: không có lỗi mới.
- [ ] **Step 7:** Commit `Website: Dashboard shows OSA, restock rate, trends and shelf activity from the shelf rollups`.

### Task 10: Khối "Shelf plan" trong Settings

**Files:**
- Create: `frontend/components/settings/ShelfPlanSection.tsx`
- Modify: `frontend/components/settings/SettingsView.tsx`, thêm khối này dưới mục "Monitored Stores".

- [ ] **Step 1: Viết khối.** Mỗi tiệm một khối, gồm:
  - 2 ô giờ (`<input type="time">`);
  - danh sách SKU lấy từ `getProducts()`, nhóm theo `brand · subcategory`, mỗi SKU có ô chọn;
  - nhãn "Seen in the last 7 days" cho các SKU có trong `suggested`;
  - nút "Use suggestion";
  - dòng "Automatic until a team_admin saves this list" khi `source` là "suggested".

  Chỉ `team_admin` mới có nút "Save shelf plan". Lưu xong hiện toast "Saved. The last 15 days are recomputed within 5
  minutes."; lỗi 400 thì hiện thông báo lỗi từ API.
- [ ] **Step 2: Kiểm.** `npm run build` và `npm test` qua; eslint không có lỗi mới.
- [ ] **Step 3:** Commit `Website: Settings lets team_admin set opening hours and expected SKUs per store`.

### Task 11: Triển khai và kiểm trên hệ thống thật

Phần này đụng tới hệ thống thật, nên phải hỏi hoang trước, như các đợt trước.

- [ ] **Step 1 — Backend:**
  - Đóng gói 2 zip theo Global Constraints và đưa lên `s3://milk-development-754361433393/releases/backend/<sha>/`.
  - Tạo change set từ `infra/backend.yaml`, với `ApiCodeKey` và `IngestCodeKey` mới; các tham số khác dùng
    `UsePreviousValue=true`, thêm `--tags project=milk-demo`.
  - Change set chỉ được có các thay đổi sau, cộng các mục "Dynamic" đi kèm:
    - Add: `ShelfTable`, `ShelfEventsTable`, `ShelfTickRule`, `ShelfTickPermission`;
    - Modify: `LambdaExecutionRole`, `ApiLambda`, `IngestLambda`.
  - Chạy change set. Kiểm `CodeSha256` của 2 Lambda khớp với 2 zip.
- [ ] **Step 2 — Dữ liệu đầu:**
  - Chờ 1 lượt tick. Kiểm: có item `check#` cho DEMO-S01, và Dashboard báo `no_hours`.
  - Hỏi hoang giờ mở cửa thật của DEMO-S01, rồi lưu kế hoạch kệ trong Settings bằng tài khoản team_admin
    (`model-check`). Danh sách SKU lấy theo gợi ý, hoặc theo lựa chọn của hoang.
  - Chờ lượt tick kế tiếp. Kiểm:
    - cờ `shelf_recompute_requested_at` đã bị xoá;
    - có các item `hour#` và `day#`;
    - nếu có hết hàng hay bổ sung thật thì có sự kiện.
- [ ] **Step 3 — Frontend:**
  - Build rồi deploy tay lên Amplify.
  - Kiểm bằng trình duyệt qua đăng nhập thật:
    - Dashboard ở từng mốc thời gian và từng tiệm;
    - các ô hiện số hoặc lý do chặn đúng;
    - Recent Shelf Activities có lọc được;
    - Settings lưu được (team_admin) và chỉ xem được (datagent).
  - Quét bundle: không còn chuỗi "the API does not serve".
- [ ] **Step 4:** Push nhánh, mở PR có Why / What changes / Testing / Already live, và chờ CI.
- [ ] **Step 5:** Ghi vào trang HOANG-P10 (Nhật ký) và cập nhật memory.
