# Auto-label phần 2b: hàng chờ Review trên trang Model — kế hoạch triển khai

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Các lon mà máy chưa quyết được đến tay người trên trang Model, dưới dạng "Review frame", tối đa một frame mỗi đoạn. Box cần xem không có vị gợi ý. Quyết định của người quay về pipeline nhãn và về kho ảnh màu.

**Architecture:**
- **Laptop** (có quyền AWS) chạy lệnh `push`: đọc `queue.json` và file đề xuất, chọn frame, chép ảnh vào bucket analytics, ghi dòng audit `REV-<camera>-<segment>` (`purpose` là `review`).
- **Backend:**
  - chặn verdict `correct` trên box `needs_flavour`;
  - frame `REV-` không mang mã `AUD-` nên tự đứng ngoài mọi số đo.
- **Frontend:**
  - box `needs_flavour` hiện "?" và bỏ "Right" khỏi vòng bấm;
  - hàng chờ xếp scoring → training → review.
- **Lệnh `export`** đọc các frame review đã xong thành file review (định dạng của `auto_label_labels`). `labels --review` và kho ảnh dùng file này.

**Tech Stack:**
- Python 3.12, boto3, moto (test), pytest.
- Next.js/TypeScript, test bằng `node --test --experimental-strip-types`.

**Spec:** `docs/superpowers/specs/2026-11-25-auto-label-design.md`, mục 5.4b, 5.5 và 5.9 (hoang duyệt ngày 25/11 và 26/11).

**Nối tiếp:** `docs/superpowers/plans/2026-11-26-auto-label-reuse.md` (phần 2a, cổng 1 đã đạt). Hàng chờ thật hiện có 4 frame, 15 lon (`store_eval\autolabel_train\queue.json` trên HUYHOANG).

## Global Constraints

**Frame review:**
- Không bao giờ tính vào số đo của trang Model. Chỉ frame `AUD-` được tính (`_is_scoring`). Frame review không mang `AUD-`.
- Box cần xem (`needs_flavour: true`) không có vị gợi ý (`sku_id` null). Người phải chọn vị (`wrong_sku` + `true_sku_id`), Not our SKU hoặc Out of scope.
- **"Right" không dùng cho box `needs_flavour`.** Frontend bỏ nó khỏi vòng bấm, backend trả 400 nếu nhận được.
- Box đã chấp nhận (máy hoặc dùng lại) hiện vị, và được điền sẵn verdict `correct`. Người sửa được.
- Lon "chờ cùng" (`waits:`) và lon đã che (`masked`) không có box trên frame. Nếu người chấm lon đó là lon sót thì vùng ấy bị che khi train; như vậy vô hại.
- Không bao giờ chọn frame AUD làm frame review. `propose` đã loại frame AUD khỏi `frames`; `push` kiểm lại bằng manifest.

**Định danh và lưu trữ:**
- `audit_id` = `REV-<camera_id>-<segment id>`, ví dụ `REV-CAM-S01-A-seg-0090`.
- `store_id` = `DEMO-S01`.
- Ảnh vào `audits/frames/<camera>/<YYYY-MM-DD>/<filename>` của bucket analytics, giống `_write_frame_audit`.
- Ghi có điều kiện `attribute_not_exists(audit_id)`, nên chạy lại `push` không ghi đè frame người đã gắn.

**Quyết định trả về:**
- File review: `{"<segment>": {"tracks": {"<track id>": {"verdict": "sku"|"not_product"|"out_of_scope", "sku"?: ...}}, "missed": [[x, y]]}}`.
- Đổi verdict của box thành quyết định: `correct` → `sku` (vị của box), `wrong_sku` → `sku` (`true_sku_id`), `not_product` và `out_of_scope` giữ nguyên.

**Kho ảnh:** chỉ nhận nhãn của người. Verdict của frame `REV-` đã xong là nhãn người, giống TRN. Không bao giờ nhận frame AUD.

**Lên live:** backend và frontend đi qua PR, CI và deploy tay. Chỉ lên live và chỉ `push` frame lên bảng thật khi hoang OK.

**Test:**
- Python: `PYTEST` như kế hoạch 2a (venv py3.12 có `requirements-dev.txt` và `opencv-python`). Cả bộ test phải xanh; `ruff check .` và `ruff format --check .` sạch, vì CI chạy cả hai.
- Frontend: `cd frontend && npm test` và `npm run build`.

**Nhánh:** `feat/auto-label-part2` (tách từ `main`).

## Review Focus

1. **Một frame review được `push` hai lần:** dòng audit cũ, kể cả khi đã `done`, phải giữ nguyên. Test nằm ở Task 4.
2. **Người lưu frame review mà không bấm gì trên box đã chấp nhận:** verdict `correct` điền sẵn phải đủ để Save. Khi export, các box đó thành quyết định của người, cùng vị. Test nằm ở Task 3 và Task 2.
3. **Gửi `correct` cho box `needs_flavour` qua API** (không qua UI): backend trả 400. Test nằm ở Task 1.
4. **Một frame `REV-` lọt vào số đo của trang Model**, qua summary, top 50 hoặc display check: số không đổi. Test nằm ở Task 1.
5. **Frame review của đoạn không còn trong `queue.json`** (đã được dùng lại ở vòng sau): `export` vẫn đọc quyết định của nó, vì người đã quyết. Test nằm ở Task 3.

---

### Task 1: Backend nhận frame review

**Files:**
- Modify: `backend/audit_scoring.py` (`validate_labels`)
- Modify: `backend/api/handler.py` (docstring của `_purpose` và `_is_scoring` nhắc `REV-`, không đổi logic)
- Test: `tests/test_audit_scoring.py`, `tests/test_backend_integration_moto.py`

**Interfaces:**
- Produces: `validate_labels(ai_boxes, verdicts, missed, catalog)` báo lỗi `"box {id} needs a flavour: Right is not offered"` khi box có `needs_flavour` truthy mà verdict là `correct`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_audit_scoring.py
def test_a_box_that_needs_a_flavour_cannot_be_right():
    boxes = [{"box_id": 1, "sku_id": None, "needs_flavour": True}, {"box_id": 2, "sku_id": "hot160"}]
    errs = validate_labels(boxes, [{"box_id": 1, "verdict": "correct"}, {"box_id": 2, "verdict": "correct"}], [], {"hot160"})
    assert errs == ["box 1 needs a flavour: Right is not offered"]
    ok = [{"box_id": 1, "verdict": "wrong_sku", "true_sku_id": "hot160"}, {"box_id": 2, "verdict": "correct"}]
    assert validate_labels(boxes, ok, [], {"hot160"}) == []

# tests/test_backend_integration_moto.py
@mock_aws
def test_a_review_frame_is_labelled_but_never_scored(monkeypatch):
    # put_item a REV- audit (purpose review, 2 boxes: one needs_flavour, one hot160 with verdict correct pre-filled)
    # GET list → purpose "review"; PUT with correct on the needs_flavour box → 400;
    # PUT with wrong_sku + true_sku_id → 200 status done; GET /v1/model/summary days=0 → n_audits == 0
```

Dùng helper sẵn có của file moto: `_backend`, `_call`, `_table("test-audits")` và hằng `store_id` `"DEMO-S01"`. Ảnh lấy từ bucket test như `_one_pending_audit`.

- [ ] **Step 2: Run to verify they fail** — `PYTEST tests/test_audit_scoring.py tests/test_backend_integration_moto.py -k "flavour or review_frame"`. Expected: FAIL; validate chưa biết `needs_flavour`.

- [ ] **Step 3: Implement** the `needs_flavour` check in `validate_labels`. Module text: thêm một dòng về box `needs_flavour` vào bảng verdict.

- [ ] **Step 4: Run to verify they pass, then the whole suite.**

- [ ] **Step 5: Commit** — `git commit -m "Model page backend: review frames, no Right on a box that needs a flavour"`

### Task 2: Frontend hiện frame review

**Files:**
- Modify: `frontend/lib/api.ts`:
  - `AuditPurpose` thêm `"review"`;
  - `ApiAuditBox` thêm `needs_flavour?: boolean` và `track_id?: string`.
- Modify: `frontend/lib/audit-labeling.ts`:
  - `nextVerdict(verdict, needsFlavour = false)`;
  - thêm `labelQueueOrder`.
- Modify: `frontend/components/model/AuditLabeler.tsx`:
  - dòng đầu theo `purpose`;
  - box `needs_flavour` hiện "?";
  - vòng bấm gọi `nextVerdict(v, b.needs_flavour)`;
  - danh sách chọn vị ghi "Flavour" thay vì "Right SKU";
  - đoạn hướng dẫn có câu cho box "?".
- Modify: `frontend/components/model/ModelQualityView.tsx` — dùng `labelQueueOrder` thay cho sort tại chỗ (dòng ~141); nhãn purpose "Review".
- Test: `frontend/lib/audit-labeling.test.ts`

**Interfaces:**
- Produces:
  - `nextVerdict(verdict: Verdict | null, needsFlavour?: boolean): Verdict | null`. Với `needsFlavour`, vòng bấm là null → wrong_sku → not_product → out_of_scope → null.
  - `labelQueueOrder(items: Pick<ApiAuditListItem, "audit_id" | "purpose" | "capture_timestamp">[]): string[]` xếp scoring → training → review, mỗi nhóm cũ trước.

- [ ] **Step 1: Write the failing tests** (`audit-labeling.test.ts`)

```ts
test("a box that needs a flavour never offers Right", () => {
  assert.equal(nextVerdict(null, true), "wrong_sku");
  assert.equal(nextVerdict("out_of_scope", true), null);
  assert.equal(nextVerdict(null), "correct");
});

test("the queue opens scoring, then training, then review frames, each oldest first", () => {
  const it = (audit_id: string, purpose: string, capture_timestamp: string) => ({ audit_id, purpose, capture_timestamp });
  assert.deepEqual(
    labelQueueOrder([it("R1", "review", "2026-11-24T10:00"), it("T1", "training", "2026-11-25T10:00"),
                     it("A2", "scoring", "2026-11-25T09:00"), it("A1", "scoring", "2026-11-24T09:00")] as never),
    ["A1", "A2", "T1", "R1"]);
});

test("a review frame saved with its pre-filled Right boxes and every ? box decided can be saved", () => {
  // canSave with a needs_flavour box labelled wrong_sku + trueSku and an accepted box labelled correct → true
});
```

- [ ] **Step 2: Run to verify they fail** — `cd frontend && npm test`. Expected: FAIL, vì chưa có `labelQueueOrder` và `nextVerdict` bỏ qua tham số thứ hai.

- [ ] **Step 3: Implement** lib changes, then the two components.
  - Dòng đầu cho frame review: `"Review frame — machine-unsure cans; your choice teaches the auto-labeller, never scored"`.
  - Hướng dẫn cho box "?": `"A ? box has no suggestion: click to pick its flavour, Not our SKU or Out of scope."`

- [ ] **Step 4: Run** `npm test` (PASS) and `npm run build` (build xong, không lỗi TypeScript).

- [ ] **Step 5: Commit** — `git commit -m "Model page: review frames, a ? box offers no Right; queue scoring, training, review"`

### Task 3: Frame review từ hàng chờ, và quyết định trả về (hàm thuần)

**Files:**
- Create: `training/store_view/auto_label_review.py`
- Test: `tests/test_auto_label_review.py`

**Interfaces:**
- Consumes: `load_proposals` (dict đề xuất có `tracks: [Track]`, `decisions`); `queue()` (`QueueResult.decisions`); `Track.box_in`.
- Produces:

```python
STORE_ID = "DEMO-S01"

def audit_id(camera: str, segment: str) -> str                      # "REV-<camera>-<segment>"
def pick_frame(proposal: dict, track_ids: list[str]) -> str
    # frame có nhiều track trong track_ids được thấy nhất; hoà thì frame gần giữa đoạn nhất
def review_boxes(proposal: dict, decisions: dict[str, Decision], track_ids: list[str], frame: str
                 ) -> tuple[list[dict], list[dict]]
    # (ai_boxes, pre-filled verdicts). ai_boxes: mỗi track thấy ở frame (box_in) mà là
    #   - track trong track_ids → {"box_id", "track_id", "sku_id": None, "conf": 0.0, "box", "needs_flavour": True}
    #   - quyết định accept → {"box_id", "track_id", "sku_id": d.sku, "conf": 1.0, "box"} + verdict {"box_id", "verdict": "correct"}
    # box_id từ 1 theo thứ tự track; box là list int [x, y, w, h]
def review_item(proposal: dict, decisions: dict[str, Decision], track_ids: list[str], camera: str,
                manifest_row: dict, image_key: str, model_version: str) -> dict
    # dòng audit đầy đủ, như _write_frame_audit:
    #   store_id, audit_id, purpose "review", camera_id, capture_id, capture_timestamp, image_key, model_version,
    #   pipeline "auto-label", display_visible True, status "pending", sampled_at,
    #   ai_boxes_json, verdicts_json (điền sẵn), missed_json "[]", segment_id
def review_file(audits: list[dict]) -> dict
    # các audit REV- có status "done" → file review (Global Constraints); box không có track_id thì bỏ;
    # missed → [x, y] của từng điểm; audit khác REV- hoặc chưa done thì bỏ qua
```

- [ ] **Step 1: Write the failing tests** (`tests/test_auto_label_review.py`)

Dựng 1 đề xuất có 3 track: t0 accept cheese145, t1 review, t2 waits. Track thấy ở các frame `F1..F3`; t1 chỉ thấy ở F2 và F3.

```python
def test_pick_frame_prefers_the_frame_showing_the_most_cans_to_review():
    assert pick_frame(p, ["s-t1"]) == "F2"


def test_review_boxes_show_accepted_cans_with_their_flavour_and_review_cans_without():
    ...
    # 2 box: t0 sku cheese145 + verdict correct điền sẵn; t1 sku None needs_flavour; t2 (waits) không có box


def test_review_item_is_a_pending_review_audit_of_that_segment():
    ...
    # audit_id "REV-CAM-S01-A-s", purpose "review", status "pending", json fields parse back


def test_review_file_turns_verdicts_into_track_decisions():
    ...
    # correct trên box cheese145 → {"verdict":"sku","sku":"cheese145"}; wrong_sku → sku true; out_of_scope giữ;
    # missed [{"sku_id":..,"x":5,"y":6}] → [[5,6]]


def test_review_file_skips_pending_and_non_review_audits(): ...
def test_review_file_keeps_a_segment_no_longer_in_the_queue(): ...  # Review Focus 5: chỉ đọc audit, không đọc queue.json
```

- [ ] **Step 2: Run to verify they fail** — `PYTEST tests/test_auto_label_review.py`. Expected: FAIL với lỗi `ModuleNotFoundError`.

- [ ] **Step 3: Implement** `auto_label_review.py`.

- [ ] **Step 4: Run to verify they pass, then the whole suite.**

- [ ] **Step 5: Commit** — `git commit -m "Auto-label: review frames from the queue, and people's decisions back as a review file"`

### Task 4: Lệnh `push` và `export`; kho ảnh nhận nhãn review

**Files:**
- Modify: `training/store_view/auto_label_review.py` (`push`, `main`)
- Modify: `training/store_view/slide_gallery.py`:
  - `trn_rows` nhận cả audit `REV-` đã xong;
  - `_export_trn` xuất cả `REV-`; đổi tên mô tả trong docstring.
- Test: `tests/test_auto_label_review.py` (moto), `tests/test_slide_gallery.py`

**Interfaces:**
- Consumes: Task 3; `load_proposals`, `human_precedents`, `queue`, `REUSE_MIN_SIM` (2a).
- Produces:

```python
def push(proposals_dir: Path, queue_json: Path, frames_dir: Path, truth: Path, segments: Path, trn: Path | None,
         camera: str, analytics_bucket: str, table_name: str, model_version: str, s3, ddb) -> list[str]
    # quyết định của mỗi đoạn = queue(load_proposals(...), human_precedents(...)) như lệnh queue;
    # với mỗi đoạn trong queue.json: pick_frame, đọc dòng manifest của frame (bucket, image_key, capture_timestamp),
    # copy_object sang analytics bucket, put_item có điều kiện; trả các audit id vừa tạo (bỏ qua audit đã có)
```

```text
python -m training.store_view.auto_label_review push --proposals P --frames F --truth T --segments S [--trn TRN] ^
    --camera CAM-S01-A --analytics-bucket B --table milk-backend-development-audits --model-version V
python -m training.store_view.auto_label_review export --table milk-backend-development-audits --out review.json
```

- [ ] **Step 1: Write the failing tests**

```python
@mock_aws
def test_push_writes_one_pending_review_audit_per_queued_segment_and_never_twice(tmp_path):
    # bucket nguồn có ảnh frame; manifest có bucket/image_key/capture_timestamp; table audits (store_id, audit_id)
    # push hai lần → lần 1 trả ["REV-CAM-S01-A-seg-1"], lần 2 trả []; ảnh có ở analytics bucket;
    # sửa status thành "done" rồi push lại → item vẫn "done"                     (Review Focus 1)

def test_trn_rows_read_done_review_audits_as_people_labels():           # tests/test_slide_gallery.py
    # một audit REV- done với verdict correct trên box cheese145 → ("CAP..", box, "cheese145")
```

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Implement** `push`, `main` (argparse, boto3 `ap-southeast-1`) and the gallery change. `export` gọi scan bảng audits (lọc `begins_with(audit_id, "REV-")`), rồi `review_file`, rồi ghi JSON.

- [ ] **Step 4: Run to verify they pass, then the whole suite; `ruff check .`, `ruff format --check .`.**

- [ ] **Step 5: Commit** — `git commit -m "Auto-label: push review frames to the Model page and export people's decisions"`

### Task 5: PR, deploy và đưa 4 frame lên (chỉ khi hoang OK)

Chạy thật, không viết test.

- [ ] **Step 1: Push nhánh, mở PR vào `main`, chờ CI xanh** (lint, test, cfn-lint, image). Báo hoang link PR.
- [ ] **Step 2 (sau khi hoang OK): deploy backend.**
  - Đóng gói Lambda API như các lần trước: zip lên `milk-development-754361433393/releases/backend/<sha>/`, cập nhật mã hàm.
  - **Không** `--tags` trên stack backend.
  - Expected: `GET /v1/model/audits` vẫn 200.
- [ ] **Step 3 (sau khi hoang OK): deploy frontend.**
  - Amplify deploy tay, theo memory `frontend-deploy`.
  - Expected: job SUCCEED; trang Model mở được (headless Edge, `shelf_run.py`).
- [ ] **Step 4: Đưa frame lên.**
  - Lấy tên bucket analytics từ biến môi trường `ANALYTICS_BUCKET` của Lambda API.
  - Chép `store_eval\autolabel_train` từ HUYHOANG về laptop.
  - Chạy `push`.
  - Expected: 4 audit `REV-…` pending; trang Model hiện chúng sau scoring và training; box "?" không có Right.
- [ ] **Step 5: Báo hoang gắn nhãn 4 frame** (khoảng 15 lon). Sau đó chạy:
  - `export` ra `review.json`, rồi chép sang HUYHOANG;
  - `labels --review review.json` trên các đoạn train.
  - Expected: in số frame đã ghi nhãn. Đây là đầu vào của phần 3 (train Slide v4).
