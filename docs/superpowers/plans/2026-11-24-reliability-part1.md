# Độ tin cậy của số đếm, phần 1 — kế hoạch làm

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Làm phần chung của spec (mục 1):
- lúc không thấy tủ thì ghi "không đo được", không tính là 0;
- đo đúng: luật chấm A, khung chấm điểm và khung dạy, chỉ số hai chiều có khoảng tin cậy, xác nhận sự kiện kệ;
- web nói rõ mức tin cậy của từng SKU.

Phần 2 (kho ảnh lon thật) có kế hoạch riêng: `2026-11-24-reliability-part2-gallery.md`.

**Architecture:**
- **Worker:** thêm module `server/milk/display.py`. Mỗi capture được so vùng tủ với bộ ảnh mẫu tự học, rồi ghi
  `display_score` và `display_visible` vào record.
- **Lambda ingest:**
  - lưu hai trường này;
  - capture không thấy tủ thì không cập nhật `latest_stock`;
  - `shelf.py` bỏ các lần kiểm không đo được, đánh dấu sự kiện sau khoảng trống, và chép ảnh sự kiện;
  - mỗi giờ chọn 1 khung chấm điểm (`AUD-`) và 1 khung dạy (`TRN-`).
- **Lambda API:** thêm chỉ số hai chiều, chỉ số có/không, khoảng tin cậy (bootstrap theo khung), xác nhận sự kiện và
  nhãn tin cậy.
- **Website:** cập nhật màn hình chấm, trang Model, Dashboard và Products.

**Tech Stack:**
- Python 3.12. Lambda không dùng thư viện ngoài. Worker dùng numpy và opencv-python-headless.
- pytest + moto.
- CloudFormation (`infra/backend.yaml`).
- Next.js 16 static export, React, recharts, `node --test`.

**Spec:** `docs/superpowers/specs/2026-11-24-reliability-design.md`

## Global Constraints

- **Không có số giả.** Chưa đủ mẫu thì API trả `null` hoặc `"insufficient"` kèm n, và giao diện hiện "Not enough
  samples (n = …)". Không bao giờ hiện 0% thay cho "không có dữ liệu".
- **Phạm vi A:** chỉ đếm lon ở khay trên thấy được mặt hoặc nắp, đủ để nhận ra vị.
- **Verdict:** `correct`, `wrong_sku`, `not_product`, `out_of_scope`. Hộp `out_of_scope` bị bỏ khỏi mọi chỉ số và
  không xuất sang kho ảnh. Công thức 12 KPI không đổi.
- **Lý do bỏ qua khung:** `blurry`, `blocked`, `camera_moved`, `display_away`, `other`. Khung bỏ qua không vào chỉ số
  nào.
- **Mã khung:**
  - `AUD-<camera>-<YYYYMMDD>-<HH>`, `purpose = "scoring"`: khung duy nhất được dùng để tính chỉ số.
  - `TRN-<camera>-<YYYYMMDD>-<HH>`, `purpose = "training"`: không bao giờ vào chỉ số.
- **Hằng số:**

  | Tên | Giá trị | Ở đâu |
  |---|---|---|
  | `GAP_MINUTES` | 30 | `backend/shelf.py` |
  | `MIN_FRAMES`, `MIN_TRUE_UNITS`, `MIN_DAYS` | 10, 20, 2 | `backend/audit_scoring.py` |
  | `BADGE_HIGH`, `BADGE_MEDIUM` | 0.90, 0.70 | `backend/audit_scoring.py` |
  | `BOOTSTRAP_SAMPLES`, `BOOTSTRAP_SEED` | 400, 20261124 | `backend/audit_scoring.py` |
  | `ALERT_MIN_VERIFIED` | 10 | `backend/api/handler.py` |
  | `REF_MIN_BOXES`, `REF_MIN_CONF`, `REF_EVERY_S`, `MAX_REFS` | 3, 0.8, 600, 50 | `server/milk/display.py` |
  | `MILK_DISPLAY_MIN` (mặc định) | 0.5 | `server/milk/config.py` |

- **Buổi trong ngày** (giờ ICT của khung): sáng trước 12:00, chiều 12:00–17:00, tối từ 17:00.
- **Giờ và ngày theo ICT (UTC+7).** Lần kiểm là khoảng 5 phút, mã `YYYYMMDD-HHMM`.
- **Bản ghi cũ:**
  - capture không có `display_visible` thì coi là thấy tủ;
  - item `check#` không có `measurable` thì coi là đo được;
  - audit không có `purpose` thì xét theo tiền tố mã khung.
- **Nhãn trên website bằng tiếng Anh**, như các trang hiện có.
- **Repo là public:** không commit ảnh tiệm, kể cả trong test. Test worker dùng ảnh tổng hợp.
- **Tài khoản commit:** `Nguyen Huy Hoang <193206418+Protein-17012006@users.noreply.github.com>`.
- **Change set của `milk-backend-development` không bao giờ dùng `--tags`.**
- **Giới hạn 10 Lambda chạy cùng lúc:** không thêm lời gọi song song mới trên Dashboard. Số mới phải đi kèm các lời
  gọi đang có (`/kpi`, `/shelf-events`, `/products`).
- **Lệnh test:**
  - Python: chạy trong venv Python 3.12 cài `requirements-dev.txt`, như CI. Lệnh `python -m pytest <file> -q`.
  - Frontend: `cd frontend && npm test`.
  - Trước mỗi lần push: `ruff check .` và `ruff format --check .`.

## Review Focus

1. **Dữ liệu cũ và dữ liệu thiếu:** capture, check hay audit tạo trước khi có các trường mới vẫn được tính như cũ,
   không lỗi 500.
   - Test ở Task 5: ingest một record không có trường thấy tủ thì vẫn cập nhật `latest_stock`.
   - Test ở Task 2: audit không có `purpose` nhưng mã `AUD-` vẫn vào chỉ số.
2. **Kiểm thấy tủ chưa sẵn sàng:**
   - chưa có ảnh mẫu thì coi là thấy tủ, `display_score` là `null`;
   - vùng tủ nằm một phần ngoài khung thì cắt vào trong khung;
   - không đặt `MILK_DISPLAY_ZONE` thì không kiểm gì.

   Test ở Task 4.
3. **Chỉ số khi gần như không có gì để tính:** audit chỉ có hộp `out_of_scope`, chỉ có khung bỏ qua, hay SKU chỉ có
   số model mà không có số thật. Phải trả `null` hoặc `"insufficient"`, không chia cho 0. Test ở Task 1 và Task 8.
4. **Sự kiện không có ảnh, và ảnh đã hết hạn:** capture không có ảnh thì sự kiện vẫn được ghi, chỉ không có ảnh. API ảnh
   trả `null` và giao diện ghi "Photo no longer kept". Test ở Task 9.
5. **`event_key` có `#`, `&`, dấu cách hoặc tiếng Việt, và sự kiện đã bị tính lại xoá:**
   - xác nhận gửi trong body, không đặt `event_key` vào URL;
   - kết quả xác nhận vẫn còn sau khi tính lại, và vẫn tính vào tỉ lệ cảnh báo đúng nếu sự kiện còn;
   - danh sách sự kiện không bao giờ lẫn item `verdict#`.

   Test ở Task 9.

---

### Task 0: Đưa kế hoạch vào repo

- [ ] **Step 1:** Commit hai file kế hoạch, với message `Docs: plans for counting reliability (part 1 and the gallery)`.

### Task 1: Luật chấm A trên màn hình chấm

**Files:**
- Modify: `backend/audit_scoring.py`
- Modify: `backend/api/handler.py` (`_handle_model_audit_put`)
- Modify: `frontend/lib/audit-labeling.ts`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/components/model/AuditLabeler.tsx`
- Test: `tests/test_audit_scoring.py`, `tests/test_backend_integration_moto.py`, `frontend/lib/audit-labeling.test.ts`

**Interfaces:**
- Produces (backend):
  - `audit_scoring.VERDICTS = ("correct", "wrong_sku", "not_product", "out_of_scope")`
  - `audit_scoring.SKIP_REASONS = ("blurry", "blocked", "camera_moved", "display_away", "other")`
  - `audit_scoring.scoped(audit: dict) -> dict`: bản sao của audit, đã bỏ các hộp `out_of_scope` cùng verdict của
    chúng. Task 8 và Task 10 dùng lại.
  - Audit `done` có thêm `label_rule = "A"` và `misses_checked = True`.
  - `GET /model/summary` có thêm `old_rule_frames`: số khung chấm điểm `done` chưa có `label_rule = "A"`.
- Produces (frontend):
  - `Verdict = "correct" | "wrong_sku" | "not_product" | "out_of_scope"`
  - `canSave(aiBoxes, labels, missesChecked: boolean): boolean`
  - `toPayload(labels, missed)` trả `{verdicts, missed, misses_checked: true}`.

- [ ] **Step 1: Viết test Python.** Thêm vào `tests/test_audit_scoring.py`:

```python
AUDIT_SCOPE = {  # 2 Cheese named right, 1 real Cheese can on the lower tier (out of scope under rule A)
    "capture_timestamp": "2026-11-24T09:35:04+07:00",
    "ai_boxes": [
        {"box_id": 1, "sku_id": "cheese145", "conf": 0.96, "box": [907, 227, 69, 180]},
        {"box_id": 2, "sku_id": "cheese145", "conf": 0.95, "box": [944, 259, 70, 46]},
        {"box_id": 3, "sku_id": "cheese145", "conf": 0.41, "box": [950, 560, 60, 70]},
    ],
    "verdicts": [
        {"box_id": 1, "verdict": "correct"},
        {"box_id": 2, "verdict": "correct"},
        {"box_id": 3, "verdict": "out_of_scope"},
    ],
    "missed": [],
}


def test_out_of_scope_boxes_count_nowhere():
    rows = comparison_rows(AUDIT_SCOPE)
    assert [(r["sku_id"], r["ai_unit_count"], r["human_unit_count"], r["discrepancy_category"]) for r in rows] == [
        ("cheese145", 2, 2, "Exact Match")
    ]
    s = summarize([AUDIT_SCOPE], [])
    assert (s["kpis"]["false_detection_rate"]["value"], s["kpis"]["false_detection_rate"]["n"]) == (0.0, 2)
    assert s["kpis"]["avg_confidence_correct"]["n"] == 2
    assert next(r for r in s["per_sku"] if r["sku_id"] == "cheese145")["model_units"] == 2
    assert s["confusion"]["cells"] == {"cheese145|cheese145": 2}


def test_a_frame_of_only_out_of_scope_boxes_has_no_numbers():
    only = {**AUDIT_SCOPE, "ai_boxes": AUDIT_SCOPE["ai_boxes"][2:], "verdicts": AUDIT_SCOPE["verdicts"][2:]}
    k = summarize([only], [])["kpis"]
    assert k["false_detection_rate"]["value"] is None and k["unit_count_mae"]["value"] is None


def test_validate_labels_accepts_out_of_scope():
    assert validate_labels(AUDIT_SCOPE["ai_boxes"], AUDIT_SCOPE["verdicts"], [], CATALOG) == []
```

- [ ] **Step 2: Viết test moto.**
  - Sửa các lời gọi `PUT /v1/model/audits/...` đang có trong `tests/test_backend_integration_moto.py` để gửi thêm
    `"misses_checked": True`.
  - Thêm 2 test:

```python
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
        ExpressionAttributeValues={":done": "done", ":v": '[{"box_id":1,"verdict":"correct"},{"box_id":2,"verdict":"correct"}]'},
    )
    assert _call(api, "GET", "/v1/model/summary", query={"days": "0"})[1]["old_rule_frames"] == 1
```

- [ ] **Step 3: Viết test frontend.** Thêm vào `frontend/lib/audit-labeling.test.ts`:

```ts
test("a click goes from not our SKU to out of scope, then back to unlabelled", () => {
  assert.equal(nextVerdict("not_product"), "out_of_scope");
  assert.equal(nextVerdict("out_of_scope"), null);
});

test("save needs every box labelled and the missed-cans check", () => {
  const boxes = [{ box_id: 1, sku_id: "hot160" }];
  const labels = { 1: { verdict: "out_of_scope" as const, trueSku: null } };
  assert.equal(canSave(boxes, labels, false), false);
  assert.equal(canSave(boxes, labels, true), true);
});

test("an out-of-scope box counts neither for the model nor for the truth", () => {
  assert.deepEqual(totalsBySku([{ box_id: 1, sku_id: "cheese145" }], { 1: { verdict: "out_of_scope", trueSku: null } }, []), {});
});

test("the payload says the missed cans were checked", () => {
  assert.deepEqual(toPayload({ 1: { verdict: "out_of_scope", trueSku: null } }, []), {
    verdicts: [{ box_id: 1, verdict: "out_of_scope" }],
    missed: [],
    misses_checked: true,
  });
});
```

- [ ] **Step 4: Chạy test, phải FAIL.**
  - `python -m pytest tests/test_audit_scoring.py tests/test_backend_integration_moto.py -q`
  - `cd frontend && npm test`

  Mong đợi: các test mới FAIL. Các test cũ vẫn PASS, riêng các lời gọi PUT đã sửa ở Step 2 thì FAIL vì API chưa đổi.
- [ ] **Step 5: Sửa backend.**
  - `scoped()` được gọi ở đầu `comparison_rows`, `_kpis`, `_per_sku` và `_confusion`.
  - `validate_labels` nhận `out_of_scope` cho mọi hộp.
  - `_handle_model_audit_put`:
    - `misses_checked` khác `True` thì trả 400, message `"misses_checked must be true: check for cans the model missed"`;
    - khi lưu, ghi thêm `label_rule="A"` và `misses_checked=True`.
  - `_handle_model_summary` trả thêm `old_rule_frames`.
- [ ] **Step 6: Sửa frontend.**
  - `CYCLE = [null, "correct", "wrong_sku", "not_product", "out_of_scope"]`.
  - `totalsBySku` bỏ qua hẳn hộp `out_of_scope`.
  - `ApiAuditVerdict.verdict` thêm `"out_of_scope"`. `api.saveAudit` gửi thêm `misses_checked`.
  - `AuditLabeler.tsx`:
    - `VERDICT_STYLE.out_of_scope = { color: "#6B7280", label: "Out of scope" }`;
    - `SKIP_REASONS` thêm `{ value: "display_away", label: "Display not in view" }`;
    - một khung luật đặt trên ảnh, nội dung đúng như sau: "Rule A — count catalogue cans on the display's top tray
      whose face or lid shows enough to tell the flavour. Mark Out of scope: cans on the lower tier, cans almost fully
      hidden, cans whose flavour you can't tell.";
    - một ô tích "I checked for cans the model missed (click the shelf to add them)". Ô này phải được tích thì Save
      mới bật. Ô bỏ tích sau mỗi lần sang khung mới.
  - `ModelQualityView.tsx`: khi `old_rule_frames > 0` thì hiện một dòng "{n} frames were labelled before rule A —
    relabel them so the numbers follow one rule".
- [ ] **Step 7: Chạy lại cả hai bộ test.** Mong đợi: PASS hết. Chạy thêm `cd frontend && npm run build`, phải build
  được.
- [ ] **Step 8:** Commit `Model page: rule A labelling (out of scope, display not in view, missed-cans check)`.

### Task 2: Khung chấm điểm, khung dạy, và lưu trường thấy tủ

**Files:**
- Modify: `backend/ingest/handler.py` (`_normalize_record`, `ingest_capture`, `sample_audit` → `sample_frames`,
  `_run_hour`)
- Modify: `backend/api/handler.py` (`_done_audits`, `_handle_model_summary`, `_handle_model_audits`)
- Modify: `frontend/lib/api.ts`, `frontend/components/model/ModelQualityView.tsx`,
  `frontend/components/model/AuditLabeler.tsx`
- Test: `tests/test_backend_integration_moto.py`

**Interfaces:**
- Produces:
  - Record sau `_normalize_record`, và item bảng captures, có thêm:
    - `display_score: float | None`, chỉ ghi vào item khi khác `None`;
    - `display_visible: bool`, mặc định `True`.
  - `sample_frames(s3_client, ddb_resource, camera_id: str, items: list[dict], hour: str, rng: random.Random,
    store: dict | None) -> list[str]`: trả các audit id vừa tạo (0, 1 hoặc 2 id).
  - Audit item có thêm `purpose` (`"scoring"` | `"training"`) và `display_visible` (lấy từ capture được chọn).
  - API: `_is_scoring(audit: dict) -> bool` (mã bắt đầu bằng `AUD-`). Mỗi item của `GET /model/audits` có thêm
    `purpose`.
- Test helper: `_ingest(..., display_visible: bool | None = None)` đặt `record["display_visible"]`. Nếu giá trị là
  `False` thì đặt thêm `record["display_score"] = 0.2`.

- [ ] **Step 1: Viết test moto.**

```python
AUD_14, TRN_14 = "AUD-CAM-S01-A-20261121-14", "TRN-CAM-S01-A-20261121-14"


def _audits() -> dict[str, dict]:
    return {i["audit_id"]: i for i in _table("test-audits").scan()["Items"]}


@mock_aws
def test_an_hour_gives_a_scoring_frame_and_a_training_frame(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "140700", [("hot160", 2)], with_frame=True)
    _ingest(ingest, "CAM-S01-A", "141200", [("hot160", 2)], with_frame=True)
    ingest.lambda_handler({"action": "sample_audits", "hour": "20261121-14"})
    a = _audits()
    assert set(a) == {AUD_14, TRN_14}
    assert a[AUD_14]["capture_id"] != a[TRN_14]["capture_id"]
    assert (a[AUD_14]["purpose"], a[TRN_14]["purpose"]) == ("scoring", "training")


@mock_aws
def test_training_frames_only_come_from_captures_that_see_the_display(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "140700", [], with_frame=True, display_visible=False)
    ingest.lambda_handler({"action": "sample_audits", "hour": "20261121-14"})
    a = _audits()
    assert set(a) == {AUD_14} and a[AUD_14]["display_visible"] is False  # scored frames are not filtered


@mock_aws
def test_frames_outside_opening_hours_are_not_sampled(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    _shelf_plan(open_time="06:00", close_time="14:00")
    _ingest(ingest, "CAM-S01-A", "140700", [("hot160", 2)], with_frame=True)
    ingest.lambda_handler({"action": "sample_audits", "hour": "20261121-14"})
    assert _audits() == {}


@mock_aws
def test_summary_and_top_50_ignore_training_frames(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "140700", [("hot160", 2)], with_frame=True)
    _ingest(ingest, "CAM-S01-A", "141200", [("hot160", 2)], with_frame=True)
    ingest.lambda_handler({"action": "sample_audits", "hour": "20261121-14"})
    body = {"verdicts": [{"box_id": 1, "verdict": "correct"}, {"box_id": 2, "verdict": "correct"}], "missed": [],
            "misses_checked": True}
    assert _call(api, "PUT", f"/v1/model/audits/{TRN_14}", body=body)[0] == 200
    _, summary = _call(api, "GET", "/v1/model/summary", query={"days": "0"})
    assert summary["n_audits"] == 0
    _, items = _call(api, "GET", "/v1/model/audits", query={"days": "0"})
    assert {i["audit_id"]: i["purpose"] for i in items["items"]} == {AUD_14: "scoring", TRN_14: "training"}
```

```python
@mock_aws
def test_an_old_audit_without_purpose_counts_by_its_id(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _one_pending_audit(ingest)
    _table("test-audits").update_item(
        Key={"store_id": "DEMO-S01", "audit_id": AUD_14}, UpdateExpression="REMOVE purpose"
    )
    body = {"verdicts": [{"box_id": 1, "verdict": "correct"}, {"box_id": 2, "verdict": "correct"}], "missed": [],
            "misses_checked": True}
    assert _call(api, "PUT", f"/v1/model/audits/{AUD_14}", body=body)[0] == 200
    assert _call(api, "GET", "/v1/model/summary", query={"days": "0"})[1]["n_audits"] == 1
```

  Các test cũ về chọn khung phải giữ nguyên. Lý do: giờ chỉ có 1 capture có ảnh thì chỉ có khung chấm điểm, nên
  `_one_pending_audit` vẫn ra đúng 1 audit.
- [ ] **Step 2: Chạy test, phải FAIL.** Lệnh: `python -m pytest tests/test_backend_integration_moto.py -q`. Mong
  đợi: các test mới FAIL.
- [ ] **Step 3: Sửa ingest.**
  - `_normalize_record` và item captures mang 2 trường thấy tủ.
  - `sample_frames`:
    - chỉ lấy các capture có `image_key`;
    - tiệm có giờ mở cửa thì lọc bằng `shelf.is_open(shelf.bucket_of(ts), open_time, close_time)`;
    - **AUD:** `rng.choice` trong mọi capture còn lại;
    - **TRN:** `rng.choice` trong các capture có `display_visible` khác `False`, trừ capture của AUD. Nếu AUD đã có
      từ lần chạy trước thì đọc `capture_id` của nó để loại ra;
    - mỗi loại ghi bằng `put_item` có điều kiện `attribute_not_exists(audit_id)`, chép ảnh như hiện nay.
  - `_run_hour` lấy `store_id` từ capture, đọc item `store_list`, rồi truyền `store` vào `sample_frames`.
- [ ] **Step 4: Sửa API.**
  - `_done_audits` và `_handle_model_summary` chỉ lấy audit thoả `_is_scoring`.
  - `_handle_model_audits` trả `purpose`. Audit cũ không có trường này thì suy từ tiền tố mã.
- [ ] **Step 5: Sửa frontend.**
  - `ApiAuditListItem.purpose` và `ApiAuditDetail.purpose`, kiểu `"scoring" | "training"`.
  - Trong `ModelQualityView.tsx`, hàng chờ xếp khung chấm điểm trước khung dạy, mỗi nhóm cũ nhất trước.
  - Tiêu đề màn hình chấm ghi "Scoring frame — counts in the accuracy numbers" hoặc "Training frame — teaches the
    flavour gallery, never scored".
- [ ] **Step 6: Chạy lại test Python, `npm test`, `npm run build`.** Mong đợi: PASS hết.
- [ ] **Step 7:** Commit `Model page: a scoring frame and a training frame per camera-hour; ingest keeps display fields`.

### Task 3: Triển khai đợt 1 (chấm theo luật A, khung dạy)

Đợt này để team bắt đầu chấm sớm nhất. Mọi bước đụng tới hệ thống thật cần hoang đồng ý trong chat trước.

- [ ] **Step 1:** Chạy đủ bộ kiểm như CI: `ruff check .`, `ruff format --check .`, `python -m pytest -q`,
  `cd frontend && npm test && npm run build`. Mong đợi: tất cả xanh.
- [ ] **Step 2:** Push nhánh `feat/reliability`, mở PR vào `main`, chờ CI xanh.
- [ ] **Step 3 (cần hoang đồng ý):** Deploy backend theo `docs/runbook.md`.
  - Đóng gói 2 Lambda, đưa lên `releases/backend/<sha>/`.
  - Change set cho `milk-backend-development`, chỉ đổi code và tham số; **không** dùng `--tags`.
  - Rồi deploy Amplify (job mới).
- [ ] **Step 4 (cần hoang đồng ý):** Trên HUYHOANG, sao lưu `C:\Users\huyho\Datagent\TRAINING.md`. Rồi thay dòng
  "Không bao giờ train trên ảnh test (`slide_pilot\test_frames`, ảnh audit của cửa hàng)" bằng: *"Không bao giờ train
  hay đưa vào kho ảnh: `slide_pilot\test_frames` và khung chấm điểm `AUD-…`. Khung dạy `TRN-…` thì được (hoang
  đồng ý 24/11)."*
- [ ] **Step 5:** Kiểm trên hệ thống thật.
  - Sau lần chạy hằng giờ kế tiếp, giờ đó có 1 `AUD-` và 1 `TRN-`.
  - Màn hình chấm có khung luật, ô tích lon sót, verdict "Out of scope" và lý do bỏ qua "Display not in view". Kiểm
    bằng tài khoản `model-check` (team_admin); xem cách đăng nhập ở memory `frontend-deploy`.
  - Chấm thử một khung rồi đặt lại `pending`, để bộ chấm không giữ nhãn do máy tạo.
- [ ] **Step 6:** Báo hoang:
  - có thể bắt đầu chấm;
  - nên chấm lại 11 khung cũ theo luật A;
  - nhịp đề xuất: 3 ngày đầu chấm hết khung trong giờ bày hàng.

  Ghi Nhật ký HOANG-P10.

### Task 4: Worker kiểm thấy tủ

**Files:**
- Create: `server/milk/display.py`, `tests/test_display.py`
- Modify: `server/milk/config.py`, `tests/test_config.py`, `server/milk/counter.py`, `worker/README.md`

**Interfaces:**
- Consumes: `cvoutput.Detection` (box là x, y, w, h theo pixel khung).
- Produces:
  - `display.REF_MIN_BOXES = 3`, `REF_MIN_CONF = 0.8`, `REF_EVERY_S = 600`, `MAX_REFS = 50`
  - `display.zone_crop(image: np.ndarray, zone: tuple[float, float, float, float]) -> np.ndarray`: cắt vùng tủ, phần
    nằm ngoài khung thì bỏ.
  - `display.hs_histogram(image: np.ndarray) -> np.ndarray`: histogram H×S (30×16 ô) qua `cv2.calcHist`, chuẩn hoá
    bằng `cv2.normalize`, trả mảng float32 phẳng.
  - `class DisplayCheck(zone, min_score: float = 0.5, refs_path: str | None = None)`:
    - `check(image: np.ndarray, detections: list[Detection], now: float) -> tuple[float | None, bool]`;
    - property `n_refs: int`.
  - `Settings` có thêm `display_zone: tuple[float, float, float, float] | None` (từ `MILK_DISPLAY_ZONE`),
    `display_min: float` (từ `MILK_DISPLAY_MIN`, mặc định 0.5) và `display_refs: str | None` (từ `MILK_DISPLAY_REFS`,
    mặc định `None`).
  - `meta` và `record` của worker có thêm `display_score` (số làm tròn 3 chữ số, hoặc `None`) và `display_visible`
    (`bool`).

- [ ] **Step 1: Viết test.**
  - Ảnh tổng hợp 2560×1440, vùng tủ là `ZONE = (0.336, 0.083, 0.242, 0.361)`.
  - `display_img()`: trong vùng tủ là các sọc dọc màu cam, vàng và xanh lá, ngoài vùng là nền xám.
  - `floor_img()`: toàn khung là nhiễu xám.
  - `cans(n, conf=0.9, inside=True)`: n hộp `Detection("cheese145", "x", conf, (x, y, 60, 150))`. Tâm hộp nằm trong
    vùng tủ khi `inside=True`, và ngoài vùng khi `inside=False`.

```python
def test_no_references_means_seen_without_a_score():
    assert DisplayCheck(ZONE).check(display_img(), [], now=0.0) == (None, True)


def test_confident_cans_inside_the_zone_teach_a_reference():
    d = DisplayCheck(ZONE)
    d.check(display_img(), cans(3), now=0.0)
    score, seen = d.check(display_img(), [], now=1.0)
    assert d.n_refs == 1 and score > 0.99 and seen


def test_the_display_gone_scores_low():
    d = DisplayCheck(ZONE)
    d.check(display_img(), cans(3), now=0.0)
    score, seen = d.check(floor_img(), [], now=1.0)
    assert score < 0.5 and not seen


def test_unsure_or_outside_cans_teach_nothing():
    d = DisplayCheck(ZONE)
    for dets in (cans(2), cans(3, conf=0.79), cans(3, inside=False)):
        d.check(display_img(), dets, now=0.0)
    assert d.n_refs == 0


def test_one_reference_per_ten_minutes_and_at_most_fifty():
    d = DisplayCheck(ZONE)
    d.check(display_img(), cans(3), now=0.0)
    d.check(display_img(), cans(3), now=599.0)
    assert d.n_refs == 1
    for k in range(1, 60):
        d.check(display_img(), cans(3), now=600.0 * k)
    assert d.n_refs == 50


def test_references_survive_a_restart(tmp_path):
    path = str(tmp_path / "refs.npz")
    DisplayCheck(ZONE, refs_path=path).check(display_img(), cans(3), now=0.0)
    assert DisplayCheck(ZONE, refs_path=path).n_refs == 1


def test_a_zone_partly_outside_the_frame_is_cut_to_the_frame():
    assert zone_crop(np.zeros((100, 200, 3), np.uint8), (0.9, 0.9, 0.5, 0.5)).shape == (10, 20, 3)
```

  Thêm vào `tests/test_config.py`:
  - `test_display_settings_default_off`: không đặt biến nào thì zone là `None`, min là 0.5, refs là `None`.
  - `test_display_settings_from_env`.
  - `test_bad_display_zone_is_rejected`: message phải có `MILK_DISPLAY_ZONE`.
- [ ] **Step 2: Chạy test, phải FAIL.** Lệnh: `python -m pytest tests/test_display.py tests/test_config.py -q`.
- [ ] **Step 3: Viết `display.py`.**
  - `check`:
    1. Tính histogram của vùng tủ.
    2. Có mẫu thì `score` là giá trị lớn nhất của `cv2.compareHist(h, ref, cv2.HISTCMP_CORREL)` qua các mẫu. Chưa có
       mẫu thì `score = None` và coi là thấy tủ.
    3. Sau đó mới xét học mẫu. Học khi có ít nhất `REF_MIN_BOXES` hộp với `conf ≥ REF_MIN_CONF` có tâm trong vùng tủ,
       và mẫu gần nhất đã cách ít nhất `REF_EVERY_S` giây. Giữ `MAX_REFS` mẫu mới nhất. Có `refs_path` thì ghi bằng
       `np.savez` (gồm mẫu và thời điểm học).
  - `__init__` đọc file mẫu nếu file có sẵn.
- [ ] **Step 4: Sửa `config.py`.** `_roi(raw, name="MILK_ROI")` dùng chung cho `MILK_DISPLAY_ZONE`, message lỗi theo
  `name`.
- [ ] **Step 5: Sửa `counter.py`.**
  - Có `s.display_zone` thì tạo `DisplayCheck(s.display_zone, s.display_min, s.display_refs)`.
  - Mỗi khung gọi `check(image, detections, time.time())` trên ảnh gốc, trước khi làm mờ.
  - Ghi `display_score` và `display_visible` vào `meta` và `record`.
  - Không có vùng tủ thì ghi `(None, True)`.
- [ ] **Step 6: Ghi tài liệu.** Thêm 3 biến vào `worker/README.md`. Ghi giá trị cho CAM-S01-A:
  `MILK_DISPLAY_ZONE=0.336,0.083,0.242,0.361` và `MILK_DISPLAY_REFS=C:/Users/huyho/Datagent/display_refs_CAM-S01-A.npz`.
- [ ] **Step 7:** Chạy `python -m pytest tests/test_display.py tests/test_config.py tests/test_counter_helpers.py -q`.
  Mong đợi: PASS.
- [ ] **Step 8:** Commit `Worker: say whether the display is in view (zone histogram against learnt references)`.

### Task 5: Lần kiểm đo được, khoảng trống, trạng thái thấy tủ

**Files:**
- Modify: `backend/shelf.py`
- Modify: `backend/ingest/handler.py` (`ingest_capture`, `_apply_check`, `_check_item`, `_event_item`,
  `_shelf_store_tick`, `shelf_recompute`)
- Test: `tests/test_shelf.py`, `tests/test_backend_integration_moto.py`

**Interfaces:**
- Consumes: các trường thấy tủ trong captures (Task 2).
- Produces:
  - `shelf.GAP_MINUTES = 30`
  - `shelf.gap_between(last_measured: str | None, bucket: str) -> tuple[str, str] | None`: trả `(last_measured,
    bucket)` khi hai lần kiểm cách nhau hơn 30 phút.
  - `build_check(...)` trả thêm:
    - `captures_visible: int`;
    - `measurable: bool`: đúng khi `captures_visible > 0` và `2 * captures_visible >= captures`;
    - `image_key: str | None` và `source_bucket: str | None`: lấy từ capture thấy tủ đầu tiên có ảnh, xếp theo
      `capture_id`.

    Số đếm chỉ lấy từ các capture thấy tủ.
  - `step_state(state, units, bucket, gap: tuple[str, str] | None = None)`:
    - state có thêm `prev_gap`: khoảng trống ngay trước lần kiểm `prev`.
    - Sự kiện (tính thời điểm ở x1, tức `prev`) có `after_gap: True`, `gap_from` và `gap_to` khi `prev_gap` khác
      `None`. Ngược lại, sự kiện không có 3 trường này, nên các test cũ giữ nguyên.
  - `rollup(...)` chỉ đếm lần kiểm `open` và `measurable`. Item cũ không có `measurable` thì coi là `True`. Kết quả có
    thêm `unmeasured_checks`, là số lần kiểm mở cửa, có danh sách, mà không đo được. `merge` cộng dồn trường này,
    `totals` trả ra trường này.
  - Ingest:
    - `_apply_check(check, store, expected, skus_state, last_measured: str | None) -> tuple[list[dict], str | None]`.
    - Item `state` có thêm `last_measured_bucket`.
    - Item bảng `shelf` `display#<camera_id>`: `{store_id, key, camera_id, visible, since, last_visible_at,
      updated_at}`. `since` là lúc trạng thái `visible` hiện tại bắt đầu.
    - Item `check#` có thêm `measurable`, `captures_visible`, `image_key`, `source_bucket`.

- [ ] **Step 1: Viết test logic thuần.** Trong `tests/test_shelf.py`, helper `cap()` nhận thêm `visible: bool | None
  = None` và `image_key: str = ""`.

```python
def test_a_check_counts_only_captures_that_see_the_display():
    caps = [
        cap("CAM-A", "2026-11-23T14:05:10+07:00", {"X": 4}),
        cap("CAM-A", "2026-11-23T14:06:10+07:00", {}, visible=False),
        cap("CAM-A", "2026-11-23T14:07:10+07:00", {"X": 4}),
    ]
    c = build_check("20261123-1405", caps)
    assert (c["counts"], c["captures_visible"], c["measurable"]) == ({"X": 4}, 2, True)


def test_a_check_mostly_without_the_display_is_not_measurable():
    caps = [cap("CAM-A", f"2026-11-23T14:0{m}:10+07:00", {}, visible=m == 5) for m in (5, 6, 7)]
    assert build_check("20261123-1405", caps)["measurable"] is False


def test_old_captures_without_the_field_see_the_display():
    assert build_check("20261123-1405", [cap("CAM-A", "2026-11-23T14:05:10+07:00", {"X": 1})])["measurable"]


def test_a_check_keeps_one_frame_for_event_photos():
    caps = [
        cap("CAM-A", "2026-11-23T14:06:10+07:00", {"X": 1}, image_key="frames/b.jpg"),
        cap("CAM-A", "2026-11-23T14:05:10+07:00", {"X": 1}, visible=False, image_key="frames/a.jpg"),
    ]
    assert build_check("20261123-1405", caps)["image_key"] == "frames/b.jpg"


def test_gap_between():
    assert gap_between("20261123-1400", "20261123-1430") is None
    assert gap_between("20261123-1400", "20261123-1435") == ("20261123-1400", "20261123-1435")
    assert gap_between(None, "20261123-1435") is None


def test_an_event_right_after_a_gap_says_so():
    st, events = None, []
    for bucket, units, gap in [
        ("20261123-2020", 5, None),
        ("20261123-2025", 5, None),
        ("20261124-0845", 0, ("20261123-2025", "20261124-0845")),
        ("20261124-0850", 0, None),
    ]:
        st, e = step_state(st, units, bucket, gap)
        events += [e] if e else []
    assert events == [
        {"type": "OOS", "at": "20261124-0845", "delta": -5, "level_before": 5, "level_after": 0,
         "duration_min": None, "after_gap": True, "gap_from": "20261123-2025", "gap_to": "20261124-0845"}
    ]


def test_unmeasured_open_checks_are_counted_apart():
    c = {"bucket": "20261123-1400", "counts": {"A": 0}, "open": True, "measurable": False,
         "expected": ["A"], "confident_skus": []}
    r = rollup([c], [])
    assert (r["checks"], r["unmeasured_checks"], "A" in r["skus"]) == (0, 1, False)
    assert totals([r])["unmeasured_checks"] == 1
```

- [ ] **Step 2: Viết test moto.**

```python
@mock_aws
def test_a_capture_without_the_display_leaves_the_shelf_numbers(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "140000", [("cheese145", 5)])
    _ingest(ingest, "CAM-S01-A", "140500", [], display_visible=False)
    assert _units(api)[CHEESE] == 5
    status = _shelf("display#CAM-S01-A")
    assert (status["visible"], status["since"]) == (False, "2026-11-21T14:05:00+07:00")


@mock_aws
def test_checks_without_the_display_make_no_out_of_stock(monkeypatch: pytest.MonkeyPatch):
    _, ingest = _backend(monkeypatch)
    _shelf_plan()
    for hhmmss, units, seen in [("140010", 5, True), ("140510", 5, True), ("141010", 0, False), ("141510", 0, False)]:
        _ingest(ingest, "CAM-S01-A", hhmmss, [("cheese145", units)] if units else [], display_visible=seen)
    _tick(ingest)
    assert _event_keys() == [] and _shelf("hour#20261121-14")["unmeasured_checks"] == 2


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
```

- [ ] **Step 3: Chạy test, phải FAIL.** Lệnh: `python -m pytest tests/test_shelf.py tests/test_backend_integration_moto.py -q`.
- [ ] **Step 4: Sửa `shelf.py`** theo Interfaces.
- [ ] **Step 5: Sửa ingest.**
  - `ingest_capture`:
    - mỗi capture ghi lại item `display#<camera_id>`;
    - capture có `display_visible is False` thì không cập nhật `latest_stock`, không đụng hàng chờ duyệt, không gọi
      `_count_down_missing`. Vẫn lưu capture như thường.
  - `_apply_check`:
    - chỉ chạy trạng thái khi lần kiểm `open`, `measurable` và có danh sách SKU;
    - `gap = shelf.gap_between(last_measured, bucket)`;
    - trả `last_measured` mới.
  - `_shelf_store_tick` và `shelf_recompute`:
    - đọc và ghi `last_measured_bucket` trong `state`. Khi tính lại, bắt đầu từ `None`;
    - truyền các trường sự kiện mới vào `_event_item`, và các trường lần kiểm mới vào `_check_item`.
- [ ] **Step 6: Chạy lại test.** Mong đợi: PASS hết, kể cả mọi test cũ của shelf và moto.
- [ ] **Step 7:** Commit `Shelf: checks without the display are not measured; events after a gap say so`.

### Task 6: Web — số giờ đo được, sự kiện sau khoảng trống, dòng "không thấy tủ"

**Files:**
- Modify: `backend/shelf.py`, thêm `open_buckets`
- Modify: `backend/api/handler.py` (`_shelf_kpis`, `_handle_get_products`)
- Modify: `frontend/lib/api.ts`, `frontend/lib/shelf-ui.ts`, `frontend/components/reports/KpiGrid.tsx`,
  `frontend/components/reports/RecentActivitiesCard.tsx`, `frontend/components/category/CategoryProductsView.tsx`
- Test: `tests/test_shelf.py`, `tests/test_backend_integration_moto.py`, `frontend/lib/shelf-ui.test.ts`

**Interfaces:**
- Produces:
  - `shelf.open_buckets(open_time: str | None, close_time: str | None, first: str, last: str) -> int`: số lần kiểm
    5 phút trong giờ mở cửa, từ bucket `first` đến bucket `last`, tính cả hai đầu.
  - `/kpi` có thêm `coverage: {"measured_hours": float, "open_hours": float, "display_away_hours": float}`, làm tròn 1
    chữ số. Ô bị chặn thì `coverage` là `null`.
    - `measured_hours = store_checks × 5 / 60`.
    - `display_away_hours = unmeasured_checks × 5 / 60`.
    - `open_hours`: cộng `open_buckets` của các tiệm trong khoảng chọn, tính tới lần kiểm đã đóng gần nhất, × 5 / 60.
  - `/products` có thêm `displays: [{camera_id, store_id, visible, since, last_visible_at}]`.
  - Frontend:
    - `gapText(e: { after_gap?: boolean; gap_from?: string; gap_to?: string }): string | null`
    - `coverageText(c: { measured_hours: number; open_hours: number; display_away_hours: number }): string`
    - `displayBanner(displays: ApiDisplayStatus[]): string | null`

- [ ] **Step 1: Viết test.**

```python
def test_open_buckets_counts_five_minute_checks_inside_the_hours():
    assert open_buckets("08:00", "20:30", "20261123-0000", "20261123-2355") == 150
    assert open_buckets("08:00", "20:30", "20261123-0800", "20261123-0810") == 3
    assert open_buckets(None, None, "20261123-0000", "20261123-2355") == 0
```

  Test moto `test_kpi_says_how_many_hours_were_measured`:
  - đặt rollup `hour#` có `checks = 6` và `unmeasured_checks = 2`;
  - mong đợi `coverage.measured_hours == 0.5` và `coverage.display_away_hours == 0.2`;
  - mong đợi `open_hours` đúng như tính tay từ giờ mở cửa.

  Test moto `test_products_list_cameras_that_cannot_see_the_display`: sau một capture `display_visible=False`, mục
  `displays` có camera đó với `visible: false`.

  Thêm vào `frontend/lib/shelf-ui.test.ts`:

```ts
test("an event after a gap says when the shelf was not seen", () => {
  assert.equal(
    gapText({ after_gap: true, gap_from: "20261123-2025", gap_to: "20261124-0845" }),
    "between 20:30 and 08:45 (not measured)"
  );
  assert.equal(gapText({}), null);
});

test("coverage text", () => {
  assert.equal(
    coverageText({ measured_hours: 9.5, open_hours: 12.5, display_away_hours: 1 }),
    "Measured 9.5 h of 12.5 h open · display not in view 1 h"
  );
});

test("a banner for each camera that cannot see the display", () => {
  assert.equal(
    displayBanner([{ camera_id: "CAM-S01-A", store_id: "DEMO-S01", visible: false, since: "2026-11-23T20:45:10+07:00", last_visible_at: "2026-11-23T20:40:05+07:00" }]),
    "CAM-S01-A cannot see the display since 20:45 — numbers below are from the last check at 20:40"
  );
  assert.equal(displayBanner([]), null);
});
```

- [ ] **Step 2: Chạy test, phải FAIL.**
- [ ] **Step 3: Sửa code.**
  - API như Interfaces.
  - Ô OSA trong `KpiGrid.tsx` hiện `coverageText` ngay dưới dòng so sánh.
  - Mỗi dòng sự kiện có `gapText` thì hiện thêm dòng đó.
  - Trang Products hiện `displayBanner` phía trên danh sách.
  - Biểu đồ xu hướng đã dùng `connectNulls={false}`, nên những giờ không đo được tự thành khoảng trống. Không cần sửa
    biểu đồ.
- [ ] **Step 4: Chạy lại test, `npm run build`.** Mong đợi: PASS.
- [ ] **Step 5:** Commit `Dashboard and Products: hours measured, events after a gap, cameras that cannot see the display`.

### Task 7: Triển khai đợt 2 (kiểm thấy tủ chạy thật)

Mọi bước đụng tới hệ thống thật cần hoang đồng ý trước.

**Files:**
- Create: `scripts/check_display_series.py`. Script đọc capture và ảnh từ AWS lúc chạy, không lưu ảnh vào repo.

- [ ] **Step 1: Viết `scripts/check_display_series.py`.**
  - Tham số `--camera CAM-S01-A --from 2026-11-23T12:40 --to 2026-11-24T10:00 --every-min 10 --zone ... --hidden
    2026-11-23T20:50/2026-11-23T22:00`.
  - Script lấy 1 capture có ảnh mỗi `--every-min` phút, rồi cho chạy qua `DisplayCheck` theo thứ tự thời gian. Mẫu
    được học từ `detections_json` đã lưu, đúng như worker làm.
  - In bảng thời điểm / điểm / thấy hay không.
  - Kết thúc: mọi khung trong `--hidden` phải ra "không thấy", mọi khung khác phải ra "thấy". Sai thì thoát với mã 1.
- [ ] **Step 2:** Chạy script trên chuỗi 23–24/11. Mong đợi: thoát 0. Không đạt thì đổi cách so hoặc ngưỡng trong
  `display.py` (spec cho phép), rồi chạy lại Task 4.
- [ ] **Step 3:** Chạy đủ bộ kiểm như Task 3 Step 1. Push lên PR.
- [ ] **Step 4 (cần hoang đồng ý):** Deploy backend và Amplify như đợt 1.
- [ ] **Step 5 (cần hoang đồng ý):** Đổi worker trên HUYHOANG.
  1. Sao lưu `worker.env` và repo clone.
  2. Lấy nhánh mới bằng git bundle (HUYHOANG không kéo từ GitHub).
  3. Thêm vào `worker.env` 3 biến của Task 4, Step 6.
  4. `Stop-ScheduledTask` rồi `Start-ScheduledTask milk-worker`.
  5. Kiểm `results/*.json` mới trên hub có `display_score` và `display_visible`.
- [ ] **Step 6 (cần hoang cho giờ):** team_admin lưu giờ bày hàng thật của DEMO-S01 trong Settings. Lưu xong, hệ thống
  tự tính lại 15 ngày.
- [ ] **Step 7:** Kiểm sau khi tính lại ngày 22–24/11.
  - Các sự kiện lúc 20:40 (cất tủ), 12:40 (hub mới bật) và đêm 22/11 không còn.
  - Các sự kiện lúc 08:45 ngày 24/11 còn, kèm `after_gap`.

  Kiểm thêm buổi tối hôm triển khai:
  - lúc tiệm cất tủ, item `display#CAM-S01-A` chuyển sang `visible: false`;
  - Products hiện dòng báo, và không có sự kiện OOS nào.
- [ ] **Step 8:** Ghi Nhật ký HOANG-P10.

### Task 8: Chỉ số hai chiều, có/không, mức lần kiểm, theo buổi, khoảng tin cậy

**Files:**
- Modify: `backend/audit_scoring.py`, `backend/api/handler.py` (`_handle_model_summary`)
- Modify: `frontend/lib/api.ts`, `frontend/lib/model-ui.ts`, `frontend/lib/health-ui.ts`,
  `frontend/components/model/ModelQualityView.tsx`, `frontend/components/model/LiveHealth.tsx`
- Test: `tests/test_audit_scoring.py`, `tests/test_backend_integration_moto.py`, `frontend/lib/model-ui.test.ts`

**Interfaces:**
- Consumes: `scoped(audit)` (Task 1), audit có `display_visible` (Task 2), item `check#` (Task 5).
- Produces trong `audit_scoring.py`:
  - Hằng số `MIN_FRAMES`, `MIN_TRUE_UNITS`, `MIN_DAYS`, `BOOTSTRAP_SAMPLES`, `BOOTSTRAP_SEED`, giá trị như ở Global
    Constraints.
  - `period_of(capture_ts: str) -> str`: trả `"morning"`, `"afternoon"` hoặc `"evening"`.
  - `frame_tallies(audit: dict, expected: set[str] | None = None) -> dict[str, tuple[float, float]]`: các cặp (tử, mẫu)
    của một khung, định nghĩa ở Step 3.
  - `ratio_ci(tallies: list[tuple[float, float]], samples: int = BOOTSTRAP_SAMPLES, seed: int = BOOTSTRAP_SEED) ->
    list[float] | None`
  - `enough(frames: int, true_units: int, days: int) -> bool`
  - `summarize(audits, processing_ms, expected: set[str] | None = None)`:
    - mỗi KPI (trừ #11) có thêm `ci`;
    - mỗi dòng `per_sku` có thêm `found_right`, `found_right_ci`, `id_accuracy_ci`, `bias_per_frame`, `frames`, `days`,
      `enough`;
    - thêm `presence: {"agree", "false_empty", "missed_empty"}`, mỗi mục là `{value, ci, n}`;
    - thêm `by_period: {"morning" | "afternoon" | "evening": {"frames", "overall_identification_accuracy",
      "presence_agree"}}`.
  - `check_level(pairs: list[tuple[dict, dict[str, int]]]) -> dict`: mỗi cặp là (audit, số của lần kiểm theo nhãn
    model). Trả `{"count_mae": {value, ci, n}, "presence_agree": {value, ci, n}}`.
  - `display_agreement(audits: list[dict]) -> dict`: trả `{"agree": {value, ci, n}, "false_not_visible": int,
    "false_visible": int}`.
- Produces trong API: `GET /model/summary` có thêm `presence`, `by_period`, `check_level`, `display_check`.

- [ ] **Step 1: Viết test.** Dùng `AUDIT_2311` có sẵn, cộng thêm `AUDIT_1744`. `AUDIT_1744` dựng theo khung thật
  17:44 ngày 23/11: 3 hộp `cheese145` mà thật là `original145`, 2 hộp `cheese145` đúng, 3 hộp `sourcream150` đúng,
  không có điểm sót.

```python
EXPECTED = {"original145", "hot160", "cheese145", "sourcream150"}


def test_found_right_is_named_right_over_true_units():
    s = summarize([AUDIT_2311], [])
    rows = {r["sku_id"]: r for r in s["per_sku"]}
    assert (rows["original145"]["found_right"], rows["hot160"]["found_right"]) == (1 / 3, 0.0)
    assert rows["original145"]["bias_per_frame"] == -2.0  # model 1, truth 3


def test_presence_counts_false_empties():
    p = summarize([AUDIT_1744], [], expected=EXPECTED)["presence"]
    # original: model 0, truth 3 -> false empty; hot: 0/0 agree; cheese and sour cream present on both sides
    assert (p["agree"]["value"], p["agree"]["n"]) == (0.75, 4)
    assert (p["false_empty"]["value"], p["false_empty"]["n"]) == (0.5, 2)
    assert (p["missed_empty"]["value"], p["missed_empty"]["n"]) == (0.0, 1)


def test_periods_follow_the_frame_hour():
    assert [period_of(t) for t in ("2026-11-24T09:35:04+07:00", "2026-11-23T14:18:11+07:00",
                                   "2026-11-23T17:44:38+07:00")] == ["morning", "afternoon", "evening"]


def test_bootstrap_is_repeatable_and_brackets_the_value():
    tallies = [(9, 11), (8, 10), (10, 12), (7, 11), (11, 13)]
    ci = ratio_ci(tallies)
    assert ci == ratio_ci(tallies) and ci[0] <= sum(t[0] for t in tallies) / sum(t[1] for t in tallies) <= ci[1]
    assert ratio_ci([(1, 2)]) is None  # one frame gives no interval


def test_enough_needs_ten_frames_twenty_cans_and_two_days():
    assert enough(10, 20, 2) and not enough(9, 20, 2) and not enough(10, 19, 2) and not enough(10, 20, 1)


def test_display_agreement():
    audits = [
        {"status": "done", "display_visible": True},
        {"status": "done", "display_visible": False},  # labeller saw the display, the check said no
        {"status": "skipped", "skip_reason": "display_away", "display_visible": False},
        {"status": "skipped", "skip_reason": "blurry", "display_visible": True},  # not about the display: left out
    ]
    d = display_agreement(audits)
    assert (d["agree"]["value"], d["agree"]["n"], d["false_not_visible"], d["false_visible"]) == (2 / 3, 3, 1, 0)


def test_summary_of_300_frames_takes_under_three_seconds():
    started = time.perf_counter()
    summarize([AUDIT_1744, AUDIT_2311] * 150, [], expected=EXPECTED)
    assert time.perf_counter() - started < 3.0
```

  Test moto `test_summary_has_presence_periods_check_level_and_display_check`:
  - chấm 1 khung chấm điểm, có item `check#` cùng bucket;
  - các khối mới có mặt, giá trị đúng như tính tay.
- [ ] **Step 2: Chạy test, phải FAIL.**
- [ ] **Step 3: Viết code. Cách tính không suy ra được từ test, nên ghi rõ ở đây.**
  - **Tử và mẫu của một khung** (`frame_tallies`, tính trên `scoped(audit)`):

    | Khoá | Tử | Mẫu |
    |---|---|---|
    | `named_right:<sku>` | số hộp model gọi `<sku>` mà `correct` | số hộp model gọi `<sku>` |
    | `found_right:<sku>` | số hộp model gọi `<sku>` mà `correct` | số lon thật của `<sku>` (cách tính như `_truth_counts`) |
    | `bias:<sku>` | số model − số thật | 1, nếu số model hoặc số thật > 0 |
    | `presence_agree` | số SKU mà model và người cùng nói có, hoặc cùng nói không | số SKU được xét |
    | `false_empty` | số SKU model nói 0 mà thật > 0 | số SKU model nói 0 |
    | `missed_empty` | số SKU model nói > 0 mà thật = 0 | số SKU thật = 0 |
    | `kpi:<tên>` | tử của KPI trong khung đó | mẫu của KPI trong khung đó |

    - "SKU được xét" là `expected`, cộng các SKU có số model hoặc số thật > 0.
    - Mỗi KPI #1–#10 và #12 là tỉ lệ của tổng tử trên tổng mẫu qua các khung. Đúng như cách `_kpis` đang tính.
  - **`ratio_ci`:**
    1. Chỉ giữ các khung có mẫu > 0. Còn dưới 2 khung thì trả `None`.
    2. Lấy mẫu lại có hoàn lại với `random.Random(seed)`, `samples` lần, mỗi lần đúng số khung.
    3. Giá trị mỗi lần = tổng tử ÷ tổng mẫu (bỏ lần nào có mẫu bằng 0).
    4. Trả `[phân vị 2.5, phân vị 97.5]`, làm tròn 4 chữ số.

    Bootstrap chỉ cộng các cặp đã tính sẵn, không chấm lại khung, nhờ vậy 300 khung chạy dưới 3 giây.
  - **`frames`** của một SKU là số khung có số thật > 0. **`days`** là số ngày khác nhau của các khung đó.
    **`enough(frames, true_units, days)`** dùng 3 số này.
  - **Mức lần kiểm (API):**
    - với mỗi khung chấm điểm `done`, đọc item `check#<bucket của capture_timestamp>` của tiệm;
    - bỏ qua khi không có item, hoặc `measurable` là `False`;
    - đổi số lần kiểm (theo tên sản phẩm) sang nhãn model bằng bảng ngược của `_sku_choices`.
  - `display_agreement` chỉ xét khung `done` và khung bỏ qua với lý do `display_away`.
- [ ] **Step 4: Sửa giao diện.**
  - **Bảng Per SKU:** thêm cột "Found right" và "Bias / frame". Hiện khoảng tin cậy nhỏ dưới mỗi %, theo dạng
    `ciText(ci)`, ví dụ "(75–83%)". Dòng `enough: false` ghi "Not enough samples".
  - **Khối mới "Present or absent":** 3 số `presence`, kèm câu giải thích ngắn như Live health.
  - **Khối mới "By time of day":** 3 cột sáng / chiều / tối.
  - **Một dòng "Dashboard checks":** lấy từ `check_level`.
  - **Live health:** thêm dòng "Display check" lấy từ `display_check`.
  - Thêm test node cho `ciText`.
- [ ] **Step 5: Chạy lại test, `npm run build`.** Mong đợi: PASS.
- [ ] **Step 6:** Commit `Model page: two-way accuracy per SKU, present or absent, by time of day, confidence intervals`.

### Task 9: Xác nhận sự kiện kệ và ảnh sự kiện

**Files:**
- Modify: `backend/ingest/handler.py`, thêm `_event_photos` và gọi nó trong `_shelf_store_tick` và `shelf_recompute`
- Modify: `backend/api/handler.py`: `_handle_shelf_events`, route mới, thêm `alert_accuracy` vào `_shelf_kpis`
- Modify: `infra/backend.yaml`, thêm lifecycle
- Modify: `frontend/lib/api.ts`, `frontend/lib/shelf-ui.ts`, `frontend/components/reports/RecentActivitiesCard.tsx`
- Test: `tests/test_backend_integration_moto.py`, `frontend/lib/shelf-ui.test.ts`

**Interfaces:**
- Consumes: item `check#` có `image_key`, `source_bucket`, `measurable` (Task 5).
- Produces:
  - Ingest `_event_photos(s3_client, ddb_resource, store_id: str, event: dict) -> dict`:
    - trả `{"photo_before_key": ..., "photo_after_key": ...}`, bỏ khoá nào không có ảnh;
    - **ảnh "after"** lấy từ item `check#<event.at>`;
    - **ảnh "before"** lấy từ lần kiểm đo được có ảnh gần nhất trước `at`. Tìm bằng Query `check#` có `key <
      check#<at>`, `ScanIndexForward=False`, `Limit=24`;
    - đích là `shelf-events/frames/<store_id>/<sha1(event_key)[:16]>-before.jpg` và `…-after.jpg` trong
      `ANALYTICS_BUCKET`;
    - file đã có (`head_object`) thì không chép lại.
  - API:
    - `GET /v1/shelf-events/photos?store_id=&event_key=` trả `{before_url, after_url}`: link ký 15 phút, hoặc `null`.
    - `PUT /v1/shelf-events/verdict`, body `{store_id, event_key, verdict}`:
      - `verdict` là `"right"`, `"wrong"` hoặc `"unsure"`;
      - chỉ `team_admin` và `field_team`;
      - sự kiện không tồn tại thì 404;
      - ghi item `event_key = "verdict#<event_key>"` gồm `{verdict, verified_by, verified_at, type, sku_id, at}`.
    - Mỗi item của `GET /v1/shelf-events` có thêm `verdict`, nếu đã có xác nhận.
    - `/kpi` có thêm `alert_accuracy: {"value", "n", "unsure", "by_type": {type: {"right", "wrong", "unsure"}},
      "blocked_reason"}`:
      - tính trên các sự kiện còn tồn tại trong khoảng chọn;
      - `value = right / (right + wrong)`;
      - `blocked_reason = "few_verified"` khi `right + wrong < ALERT_MIN_VERIFIED`.
  - Lifecycle `expire-shelf-event-frames-90d`: `Prefix: shelf-events/frames/`, `ExpirationInDays: 90`,
    `NoncurrentVersionExpiration: {NoncurrentDays: 1}`. Bucket có bật versioning, nên cần dòng này để xoá thật.

- [ ] **Step 1: Viết test moto.**
  - `test_an_event_copies_its_two_photos`: các capture `with_frame=True` lúc 14:00, 14:05, 14:10 và 14:15. Sau `_tick`,
    sự kiện OOS lúc 14:10 có đủ 2 khoá, và cả 2 object có trong `test-analytics-bucket`.
  - `test_an_event_without_photos_is_still_written`: capture không có ảnh. Sự kiện vẫn có, không có khoá ảnh nào.
  - `test_recompute_keeps_photos_and_verdicts`:
    1. xác nhận `"wrong"` cho sự kiện;
    2. lưu kế hoạch kệ, đặt cờ tính lại, rồi `_tick`;
    3. sự kiện vẫn có `verdict == "wrong"` và vẫn giữ 2 khoá ảnh.
  - `test_events_list_never_shows_verdict_items`: sau khi xác nhận, `GET /v1/shelf-events` chỉ trả sự kiện, và sự
    kiện đó có `verdict`.
  - `test_only_the_team_verifies_events`: `datagent` nhận 403. `event_key` không tồn tại thì 404. `event_key` có
    `&` và dấu cách vẫn đi qua được trong body.
  - `test_alert_accuracy_ignores_unsure_and_needs_ten`:
    - 9 lần right / wrong cộng 1 unsure thì `blocked_reason == "few_verified"`;
    - thêm 1 lần right thì có `value`, `n == 10`, `unsure == 1`.
  - `test_photos_route_gives_null_for_a_missing_photo`.
- [ ] **Step 2: Viết test node.**
  - `alertAccuracyText({value: 0.7, n: 10, unsure: 1})` phải bằng `"Alerts confirmed right: 7 of 10 (1 unsure)"`.
  - `alertAccuracyText({blocked_reason: "few_verified", n: 3})` phải bằng `"Confirm 7 more alerts to see how often
    they are right"`.
- [ ] **Step 3: Chạy test, phải FAIL.**
- [ ] **Step 4: Sửa code.**
  - `_handle_shelf_events` Query theo `Key("event_key").between(first, "9")`, chỉ khoá bắt đầu bằng số. Sau đó đọc
    các item `begins_with("verdict#")` của tiệm để gắn `verdict` vào sự kiện.
  - Thêm lifecycle vào `infra/backend.yaml`. Chạy `cfn-lint infra/backend.yaml`.
  - Trong `RecentActivitiesCard.tsx`:
    - mỗi dòng có nút "Photos", mở hộp thoại 2 ảnh "Before" và "At the event". Ảnh `null` thì ghi "Photo no longer
      kept";
    - người dùng thuộc `team_admin` hoặc `field_team` (xem `useAuth().user.groups`) thấy 3 nút "Right / Wrong /
      Unsure". Nút đang chọn được tô màu;
    - đầu thẻ hiện `alertAccuracyText(kpi.alert_accuracy)`. Số này lấy từ lời gọi `/kpi` mà Dashboard đang có, không
      thêm lời gọi mới.
- [ ] **Step 5: Chạy lại test, `npm run build`.** Mong đợi: PASS.
- [ ] **Step 6:** Commit `Dashboard: confirm shelf events with before and after photos; alert accuracy`.

### Task 10: Nhãn tin cậy của từng SKU

**Files:**
- Modify: `backend/audit_scoring.py`, thêm `badge`
- Modify: `backend/api/handler.py`: `_handle_get_products` và `_handle_shelf_events`
- Modify: `frontend/lib/api.ts`, thêm `frontend/lib/reliability-ui.ts` và `frontend/lib/reliability-ui.test.ts`
- Modify: `frontend/components/category/ProductRow.tsx`, `frontend/components/reports/RecentActivitiesCard.tsx`,
  `frontend/components/model/ModelQualityView.tsx`
- Test: `tests/test_audit_scoring.py`, `tests/test_backend_integration_moto.py`

**Interfaces:**
- Consumes: các dòng `per_sku` có `enough`, `id_accuracy_ci`, `found_right_ci` (Task 8).
- Produces:
  - `audit_scoring.BADGE_HIGH = 0.90`, `BADGE_MEDIUM = 0.70`.
  - `audit_scoring.badge(row: dict) -> str`: trả `"insufficient"` khi `enough` là `False`. Ngược lại so cận dưới của
    `id_accuracy_ci` và `found_right_ci`:
    - cả hai ≥ 0.90 thì `"high"`;
    - cả hai ≥ 0.70 thì `"medium"`;
    - còn lại `"low"`.
  - Mỗi dòng `per_sku` có thêm `badge`.
  - Mỗi item của `/products` có thêm `reliability: {badge, named_right, found_right, true_units, frames, confused_as}`.
    - Tính trên các khung chấm điểm `done` của 14 ngày gần nhất, đối chiếu bằng `model_alias` của sản phẩm.
    - Sản phẩm không có dòng nào thì `badge` là `"insufficient"`.
  - Mỗi item của `/shelf-events` có thêm `uncertain: true` khi nhãn của SKU là `"low"`.
  - Frontend:
    - `badgeLabel(badge) -> "High" | "Medium" | "Low" | "Not enough samples"`
    - `reliabilityText(r) -> string`, ví dụ `"found right 24% · 21 cans · 9 frames · often read as Slide Cheese 145g"`.

- [ ] **Step 1: Viết test.**

```python
def _row(enough=True, named=(0.92, 0.97), found=(0.91, 0.99)):
    return {"enough": enough, "id_accuracy_ci": list(named), "found_right_ci": list(found)}


def test_badges():
    assert badge(_row(enough=False)) == "insufficient"
    assert badge(_row()) == "high"
    assert badge(_row(found=(0.72, 0.9))) == "medium"
    assert badge(_row(named=(0.55, 0.8))) == "low"
    assert badge({"enough": True, "id_accuracy_ci": None, "found_right_ci": [0.9, 1.0]}) == "insufficient"
```

  - Test moto `test_products_carry_reliability`: chưa có khung chấm nào thì mọi sản phẩm có `badge ==
    "insufficient"`.
  - Test node cho `badgeLabel` và `reliabilityText`.
- [ ] **Step 2: Chạy test, phải FAIL.**
- [ ] **Step 3: Sửa code.**
  - `ProductRow` có một nhãn nhỏ cạnh tên SKU, màu theo nhãn. Rê chuột thì hiện `reliabilityText`.
  - Dòng sự kiện có `uncertain` thì hiện thêm chữ "uncertain".
  - Bảng Per SKU của trang Model có thêm cột "Reliability".
- [ ] **Step 4: Chạy lại test, `npm run build`.** Mong đợi: PASS.
- [ ] **Step 5:** Commit `Products, Dashboard, Model page: a reliability badge per SKU from the scoring frames`.

### Task 11: Triển khai đợt 3 và ghi lại

- [ ] **Step 1:** Chạy đủ bộ kiểm như Task 3 Step 1. Push lên PR, chờ CI xanh.
- [ ] **Step 2 (cần hoang đồng ý):** Deploy backend.
  - Change set phải có lifecycle mới, và **không** dùng `--tags`.
  - Chỉ được có các thay đổi: lifecycle của bucket analytics, code 2 Lambda, và các mục "Dynamic" đi kèm. Thấy mục
    "Replacement" nào thì dừng lại và báo hoang.
- [ ] **Step 3 (cần hoang đồng ý):** Deploy Amplify.
- [ ] **Step 4:** Kiểm trên trình duyệt, như các lần trước.
  - **Trang Model:** cột "Found right", "Present or absent", "By time of day", dòng "Display check".
  - **Dashboard:**
    - nút Photos ở một sự kiện thật;
    - xác nhận một sự kiện bằng `model-check`, rồi xoá item `verdict#` đó, để không để lại nhãn do máy tạo;
    - dòng "Alerts confirmed right".
  - **Products:** nhãn tin cậy.
- [ ] **Step 5:** Ghi Nhật ký HOANG-P10 và cập nhật memory `reliability-analysis-2026-11-24`. Báo hoang:
  - các số đầu tiên;
  - khi nào đủ khung dạy để bắt đầu phần 2 (spec mục 2.1: ít nhất 30 khung dạy `done`, đủ 3 buổi).
