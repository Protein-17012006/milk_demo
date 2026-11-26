# Tối ưu website, đợt 3: công cụ của team — kế hoạch làm

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Team gán nhãn một khung hình bằng vài lần bấm thay vì mười bảy; mở trang Model là biết camera và worker có
chạy không; thẻ sản phẩm mở ra là thấy ảnh có khoanh hộp; Settings đưa Shelf plan lên đầu; các việc đang chờ team
hiện ở một chỗ.

**Architecture:**
- Gần như chỉ là giao diện. Quy tắc thuần nằm trong `frontend/lib` có test: phím tắt và "đánh dấu phần còn lại đúng"
  (`audit-labeling.ts`), dòng trạng thái chạy (`model-status.ts`), các việc đang chờ (`waiting-work.ts`).
- Một thay đổi backend nhỏ: `/model/summary` trả thêm tên sản phẩm theo nhãn model, để trang Model không còn hiện mã
  `TMP-MLK-TH-01` thay cho tên.

**Tech Stack:** Next.js 16.4.6 static export, React 19, `node --test`; Python 3.12 (Lambda API), pytest + moto.

**Spec:** `docs/reviews/2026-11-26-website-feature-review.md`: thay đổi 8, phần thẻ sản phẩm của thay đổi 7, ba dòng
cuối của mục "Còn thiếu", và các dòng Model / Settings / Category liên quan trong bảng từng trang. Toàn cảnh ba đợt:
`docs/superpowers/plans/2026-11-26-website-optimization-batch1.md`.

Nhánh: `feat/website-optimization-3`, cắt từ `feat/website-optimization-2` (4efe77f, đang chạy thật từ 27/11 00:48).

## Những điều Claude tự quyết (báo cáo để ngỏ, hoang chưa nói)

1. **Ô "I checked for cans the model missed" vẫn phải tự tích**, không có phím tắt: đó là lời xác nhận của người
   gán nhãn. Khung 15 hộp đều đúng còn ba thao tác: một nút, một ô tích, Enter.
2. **"Camera và worker đang chạy"** tính từ giờ ảnh mới nhất của tiệm: trong 15 phút gần đây là đang chạy; ngoài giờ
   mở cửa thì ghi là tiệm đang đóng, không báo động; trong giờ mở cửa mà quá 15 phút không có ảnh thì ghi có thể
   camera, hub hoặc worker đã dừng.
3. **"Các việc đang chờ" nằm trên Dashboard, chỉ team thấy** (team cũng vào Dashboard sau khi đăng nhập): số lần đọc
   chờ duyệt, số khung chờ gán nhãn, số sự kiện chưa xác nhận trong 20 sự kiện mới nhất, mỗi mục là một liên kết. Hai
   lệnh gọi thêm chỉ chạy sau khi các số chính đã về, lần lượt từng lệnh, và chỉ với tài khoản team.
4. **Không gom ba chỗ kiểm tay thành một màn hình** (báo cáo gợi ý "gom về một nơi"): đợt này chỉ đưa số việc và
   đường dẫn về một chỗ; ba công cụ vẫn ở trang của chúng.
5. **Thẻ sản phẩm:** người thường thấy tên "Product details", hai ô số (số hộp, giờ đọc) và ảnh; phần kỹ thuật gập
   lại cho mọi người, team mở ra khi cần.
6. **Ngưỡng 0.70** rời Settings, thành một câu trên trang Model. **Timezone** thành một dòng chú thích cuối Settings.
7. **Tên sản phẩm trên trang Model** lấy từ backend (`sku_names`), không ghi cứng trong giao diện.

## Global Constraints

- Mọi ràng buộc của đợt 1 và 2 vẫn giữ (chữ tiếng Anh lời thường; team = `field_team` hoặc `team_admin`; không số
  liệu giả; test thuần trong `frontend/lib`; commit noreply kèm Co-Authored-By; không push, không deploy khi hoang chưa
  duyệt; change set không `--tags`).
- **Người thường không bị thêm lệnh gọi API nào.** Dashboard của team thêm đúng hai lệnh, chạy sau và lần lượt.
- **Luật gán nhãn không đổi:** mọi hộp phải có kết luận, hộp "Wrong SKU" phải có SKU đúng, ô kiểm phải được tích
  (`canSave`). Nút mới và phím tắt chỉ điền kết luận nhanh hơn.
- Phím tắt không chạy khi con trỏ đang ở ô nhập, ô chọn hoặc vùng văn bản.
- Giờ theo ICT (UTC+7).

## Review Focus

1. Hộp "?" (khung review, không có gợi ý): nút "đánh dấu phần còn lại đúng" và phím 1 không được gán "Right" cho nó.
   Test: Task 2.
2. Nhấn Enter khi chưa đủ điều kiện lưu: không được lưu. Test: Task 2 (`canSave` giữ nguyên), Task 3 (kiểm trình
   duyệt: Enter khi nút Save đang khoá không gửi gì).
3. Tiệm chưa có giờ mở cửa, hoặc chưa có ảnh nào: dòng trạng thái phải nói đúng điều biết được, không báo "đã dừng".
   Test: Task 4 `runStatus`.
4. Giờ mở cửa qua nửa đêm không có ở tiệm hiện tại, nhưng `runStatus` không được coi "22:00 đến 06:00" là mở cả
   ngày. Test: Task 4.
5. Không có việc nào đang chờ: dải việc phải biến mất, không hiện ba số 0. Test: Task 7 `waitingWork`.

## File Structure

| File | Việc | Trách nhiệm |
| --- | --- | --- |
| `backend/api/handler.py`, `tests/test_backend_integration_moto.py` | sửa | `/model/summary` thêm `sku_names` |
| `frontend/lib/audit-labeling.ts` (+ test) | sửa | phím tắt, đánh dấu phần còn lại đúng, hộp kế tiếp |
| `frontend/components/model/AuditLabeler.tsx` | sửa | hộp đang chọn, phím, nút mới |
| `frontend/lib/model-status.ts` (+ test) | tạo | dòng "camera và worker đang chạy" |
| `frontend/components/model/ModelQualityView.tsx` | sửa | dòng trạng thái, chú giải By day, tên phiên bản, tên sản phẩm, câu về ngưỡng |
| `frontend/components/category/ProductDetailsModal.tsx` | sửa | ảnh lên đầu, phần kỹ thuật gập lại |
| `frontend/components/settings/SettingsView.tsx` | sửa | thứ tự khối, chú thích timezone, giờ ảnh gần nhất |
| `frontend/lib/waiting-work.ts` (+ test) | tạo | các việc đang chờ team |
| `frontend/components/reports/{ReportsDashboard,RecentActivitiesCard}.tsx` | sửa | dải việc đang chờ |
| `frontend/lib/api.ts` | sửa | kiểu `sku_names`, giờ mở cửa của tiệm |

---

### Task 1: Backend: `/model/summary` trả tên sản phẩm theo nhãn model

**Files:** Modify `backend/api/handler.py` (`_handle_model_summary`); Test `tests/test_backend_integration_moto.py`

**Interfaces:** Produces `sku_names: {<nhãn model>: <tên sản phẩm>}` ở gốc câu trả lời, lấy từ `_sku_choices(ddb)` (SKU
Master trước, bảng alias có sẵn cho phần còn lại). Các trường khác không đổi.

- [ ] **Step 1: Test (phải fail)**

```python
@mock_aws
def test_model_summary_names_every_model_label(monkeypatch: pytest.MonkeyPatch):
    api, _ = _backend(monkeypatch)
    names = _call(api, "GET", "/v1/model/summary", query={"days": "0"})[1]["sku_names"]
    assert names["TMP-MLK-TH-01"] == TH_OLD  # a label whose own row no longer shows in /products
    assert names["cheese145"] == CHEESE
```

- [ ] **Step 2: Chạy, phải fail (`KeyError: 'sku_names'`); thêm trường; chạy cả file, phải pass; lint; commit**

```bash
git add backend/api/handler.py tests/test_backend_integration_moto.py
git commit -m "Model summary: the product name of every model label comes with the numbers"
```

---

### Task 2: Quy tắc gán nhãn nhanh

**Files:** Modify `frontend/lib/audit-labeling.ts`, `frontend/lib/audit-labeling.test.ts`

**Interfaces:** Produces

```ts
/** A box as the labeller lists it: a ? box (needs_flavour) has no suggestion to call right. */
export interface LabelBox extends AuditBox { needs_flavour?: boolean }
/** The verdict a key gives the highlighted box: 1 Right, 2 Wrong SKU, 3 Not our SKU, 4 Out of scope; null for any
 * other key, and for 1 on a ? box. */
export function verdictForKey(key: string, needsFlavour?: boolean): Verdict | null;
/** How many boxes "mark the rest right" would mark: unjudged boxes that have a suggestion. */
export function restCount(aiBoxes: LabelBox[], labels: Record<number, BoxLabel>): number;
/** The labels with those boxes marked right; judged boxes and ? boxes are left as they are. */
export function markRestCorrect(aiBoxes: LabelBox[], labels: Record<number, BoxLabel>): Record<number, BoxLabel>;
/** The next box without a verdict after box `after` in list order, wrapping round; null when all are judged. */
export function nextUnjudged(aiBoxes: AuditBox[], labels: Record<number, BoxLabel>, after: number | null): number | null;
```

- [ ] **Step 1: Thêm test**

```ts
test("keys 1 to 4 give the four verdicts; a ? box has no Right", () => {
  assert.equal(verdictForKey("1"), "correct");
  assert.equal(verdictForKey("2"), "wrong_sku");
  assert.equal(verdictForKey("3"), "not_product");
  assert.equal(verdictForKey("4"), "out_of_scope");
  assert.equal(verdictForKey("5"), null);
  assert.equal(verdictForKey("Enter"), null);
  assert.equal(verdictForKey("1", true), null);
  assert.equal(verdictForKey("2", true), "wrong_sku");
});

test("marking the rest right leaves judged boxes and ? boxes alone", () => {
  const boxes = [
    { box_id: 1, sku_id: "a" },
    { box_id: 2, sku_id: "a" },
    { box_id: 3, sku_id: null, needs_flavour: true },
    { box_id: 4, sku_id: "b" },
  ];
  const labels = { 2: { verdict: "wrong_sku" as const, trueSku: "b" } };
  assert.equal(restCount(boxes, labels), 2);
  const marked = markRestCorrect(boxes, labels);
  assert.deepEqual(marked, {
    1: { verdict: "correct", trueSku: null },
    2: { verdict: "wrong_sku", trueSku: "b" },
    4: { verdict: "correct", trueSku: null },
  });
  assert.equal(restCount(boxes, marked), 0);
  assert.equal(canSave(boxes, marked, true), false); // the ? box still needs its flavour
});

test("the next box to judge follows the list and wraps round", () => {
  const boxes = [{ box_id: 1, sku_id: "a" }, { box_id: 2, sku_id: "a" }, { box_id: 3, sku_id: "b" }];
  const labels = { 2: { verdict: "correct" as const, trueSku: null } };
  assert.equal(nextUnjudged(boxes, labels, null), 1);
  assert.equal(nextUnjudged(boxes, labels, 1), 3);
  assert.equal(nextUnjudged(boxes, labels, 3), 1);
  assert.equal(nextUnjudged(boxes, { ...labels, 1: { verdict: "correct", trueSku: null }, 3: { verdict: "not_product", trueSku: null } }, 1), null);
});
```

- [ ] **Step 2: Chạy, phải fail; viết bốn hàm; chạy lại, phải pass; commit**

```bash
git add frontend/lib/audit-labeling.ts frontend/lib/audit-labeling.test.ts
git commit -m "Labelling: the rules for the number keys, marking the rest right and moving to the next box"
```

---

### Task 3: Màn hình gán nhãn: hộp đang chọn, phím tắt, nút "đánh dấu phần còn lại đúng"

**Files:** Modify `frontend/components/model/AuditLabeler.tsx`

**Interfaces:** Consumes Task 2.

Hành vi:
- Có một **hộp đang chọn** (`data-active-box` trên dòng của nó; viền nét đứt đậm trên ảnh). Mở khung hình thì đó là
  hộp chưa có kết luận đầu tiên. Bấm một hộp trên ảnh hoặc một dòng trong danh sách thì hộp đó thành hộp đang chọn.
- Phím **1, 2, 3, 4** gán kết luận cho hộp đang chọn (`verdictForKey`) rồi chuyển sang hộp chưa có kết luận kế tiếp
  (`nextUnjudged`); kết luận "Wrong SKU" thì ở lại hộp đó để chọn SKU đúng. Phím **Enter** lưu khi nút Save đang bật.
  Phím không chạy khi con trỏ ở `input`, `select`, `textarea`, và khi đang mở phần Skip.
- Nút **`Mark the other N right`** (`data-mark-rest`) đầu danh sách "Model boxes", hiện khi `restCount > 0`; N là
  `restCount`. Bấm thì `markRestCorrect`.
- Đoạn hướng dẫn thêm một dòng: `Keys: 1 Right · 2 Wrong SKU · 3 Not our SKU · 4 Out of scope for the highlighted box · Enter saves.`
- Bấm vào hộp trên ảnh vẫn xoay vòng kết luận như cũ.

- [ ] **Step 1: Sửa `AuditLabeler.tsx`; `npm test`; build; lint; commit**

```bash
git add frontend/components/model/AuditLabeler.tsx
git commit -m "Label frames: number keys, Enter to save, and one button for the boxes that are right"
```

---

### Task 4: Trang Model: camera và worker có chạy không, và các chỗ khó đọc

**Files:**
- Create: `frontend/lib/model-status.ts`, `frontend/lib/model-status.test.ts`
- Modify: `frontend/components/model/ModelQualityView.tsx`, `frontend/lib/api.ts` (`ApiStore.open_time`,
  `close_time`; `ApiModelSummary.sku_names`)

**Interfaces:** Produces

```ts
export type RunTone = "running" | "quiet" | "stopped" | "none";
export interface RunStatus { tone: RunTone; text: string }
export const RUNNING_WITHIN_MIN = 15;
/** What the latest image of a store says about its camera, hub and worker. now and the times are read in UTC+7. */
export function runStatus(
  store: { last_capture_timestamp: string | null; open_time?: string | null; close_time?: string | null },
  now: Date
): RunStatus;
/** "15:45" for an image of today (UTC+7), "15:45 on 26/11" for an older one. */
export function imageTimeText(timestamp: string, now: Date): string;
```

Câu chữ (ví dụ với `now` = 20:40 ngày 26/11):

| Trường hợp | tone | text |
| --- | --- | --- |
| ảnh mới nhất 20:37 | running | `Running: latest image at 20:37 (3 min ago).` |
| ảnh 15:45, tiệm mở 06:00–22:00 | stopped | `No new image for 4 h (latest at 15:45). The store is open until 22:00, so the camera, the hub or the worker may have stopped.` |
| ảnh 21:58 hôm trước, `now` 05:10, mở 06:00–22:00 | quiet | `Latest image at 21:58 on 26/11 (7 h ago). The store is closed now and opens at 06:00.` |
| ảnh 15:45, tiệm không có giờ mở cửa | quiet | `Latest image at 15:45 (4 h ago).` |
| không có ảnh | none | `No image in the last 7 days.` |

Tuổi ảnh: dưới 60 phút ghi `N min ago`; dưới 48 giờ ghi `N h ago` (làm tròn xuống); còn lại `N days ago`.

- [ ] **Step 1: Test `frontend/lib/model-status.test.ts`**

```ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { imageTimeText, runStatus } from "./model-status.ts";

const NOW = new Date("2026-11-26T13:40:00Z"); // 20:40 on 26/11 in UTC+7
const HOURS = { open_time: "06:00", close_time: "22:00" };

test("an image of the last 15 minutes means it is running", () => {
  assert.deepEqual(runStatus({ last_capture_timestamp: "2026-11-26T20:37:10+07:00", ...HOURS }, NOW), {
    tone: "running",
    text: "Running: latest image at 20:37 (3 min ago).",
  });
});

test("no new image while the store is open is flagged", () => {
  assert.deepEqual(runStatus({ last_capture_timestamp: "2026-11-26T15:45:23+07:00", ...HOURS }, NOW), {
    tone: "stopped",
    text: "No new image for 4 h (latest at 15:45). The store is open until 22:00, so the camera, the hub or the worker may have stopped.",
  });
});

test("a closed store is quiet, not stopped", () => {
  const early = new Date("2026-11-26T22:10:00Z"); // 05:10 on 27/11 in UTC+7
  assert.deepEqual(runStatus({ last_capture_timestamp: "2026-11-26T21:58:02+07:00", ...HOURS }, early), {
    tone: "quiet",
    text: "Latest image at 21:58 on 26/11 (7 h ago). The store is closed now and opens at 06:00.",
  });
});

test("without opening hours it only says what it knows", () => {
  assert.deepEqual(runStatus({ last_capture_timestamp: "2026-11-26T15:45:23+07:00" }, NOW), {
    tone: "quiet",
    text: "Latest image at 15:45 (4 h ago).",
  });
  assert.deepEqual(runStatus({ last_capture_timestamp: null, ...HOURS }, NOW), { tone: "none", text: "No image in the last 7 days." });
  // hours written the wrong way round are not "open all day"
  assert.equal(runStatus({ last_capture_timestamp: "2026-11-26T15:45:23+07:00", open_time: "22:00", close_time: "06:00" }, NOW).tone, "quiet");
});

test("the time of an image", () => {
  assert.equal(imageTimeText("2026-11-26T15:45:23+07:00", NOW), "15:45");
  assert.equal(imageTimeText("2026-11-24T09:05:00+07:00", NOW), "09:05 on 24/11");
});
```

- [ ] **Step 2: Chạy, phải fail; viết `model-status.ts`; chạy lại, phải pass**

- [ ] **Step 3: `ModelQualityView.tsx`**

- Gọi thêm `api.getStores()` (cùng chỗ gọi `getProducts`); mỗi tiệm một dòng ngay dưới tiêu đề
  (`data-run-status`, `data-tone`): chấm màu (xanh, xám, cam) + `Camera and worker, <store_id>: ` + `runStatus().text`.
- Câu về ngưỡng dưới dòng đó: `Readings under <flag_threshold> confidence, or with no SKU matched, are flagged for
  review.` (`flag_threshold` từ câu trả lời `/products` đang gọi sẵn).
- `nameOf`: ưu tiên `summary.sku_names`, rồi tới tên từ `/products`, rồi mới tới nhãn.
- Ô chọn phiên bản: `unknown` hiện là `Before versions were recorded`.
- Biểu đồ "By day": thêm `<Legend />`.

- [ ] **Step 4: Build, lint, commit**

```bash
git add frontend/lib/model-status.ts frontend/lib/model-status.test.ts frontend/lib/api.ts frontend/components/model/ModelQualityView.tsx
git commit -m "Model page: whether the camera and worker are running, on top; names, a legend and a plain version label"
```

---

### Task 5: Thẻ sản phẩm: ảnh có khoanh hộp lên đầu, phần kỹ thuật gập lại

**Files:** Modify `frontend/components/category/ProductDetailsModal.tsx`

Hành vi:
- Tiêu đề: team `Validation Card Details`; người thường `Product details`.
- Ô số: team giữ bốn ô; người thường còn hai ô: `Units` và `Read at` (`HH:MM on DD/MM` của lần đọc).
- Ngay dưới các ô số (và hai dòng ghi chú sẵn có): khối ảnh (`data-card-frame`). Có ảnh và có hộp: SVG phóng vào các
  hộp (`focusRegion`), hộp khoanh số như `FrameViewer`, cao tối đa 300 px; bấm vào thì mở `FrameViewer` như nút "View
  frame" hiện nay (kể cả việc tải lại đường dẫn quá 10 phút). Dòng dưới: `N boxes in the frame of HH:MM on DD/MM`.
  Chưa có đường dẫn: `Loading the frame…`; không có ảnh: `No frame stored for this reading`.
- Khối "Product Information (SKU Master)" đổi tên `Product`; hai dòng `SKU Code / Alias` và `Barcode` chỉ team thấy.
- Khối "Human Audit & Correction" (team) giữ nguyên chỗ, ngay dưới khối Product.
- Hai khối "CV Detection Output" và "Capture & S3 Traceability" vào trong một `<details data-technical>` tên
  `Technical details`, mặc định đóng. Nút "View frame" cũ bị gỡ (khối ảnh đã làm việc đó).

- [ ] **Step 1: Sửa file; `npm test`; build; lint; commit**

```bash
git add frontend/components/category/ProductDetailsModal.tsx
git commit -m "Product card: the frame with its boxes comes first; the technical fields fold away"
```

---

### Task 6: Settings: Shelf plan lên đầu, bớt khối chỉ để đọc

**Files:** Modify `frontend/components/settings/SettingsView.tsx`

Hành vi: thứ tự khối là Account, Shelf plan, Monitored Stores. Khối Timezone và khối Low-Confidence Flag Threshold bị
gỡ; cuối trang có một dòng (`data-timezone-note`): `Every time on this site and in the CSV files is in UTC+7
(<timezoneLabel>).` Mỗi tiệm: `Last capture: <ISO>` thành `Latest image at <imageTimeText>` (Task 4), lấy "bây giờ"
lúc danh sách về, không đọc đồng hồ khi vẽ.

- [ ] **Step 1: Sửa file; build; lint; commit**

```bash
git add frontend/components/settings/SettingsView.tsx
git commit -m "Settings: the shelf plan comes first; the read-only timezone and threshold blocks shrink to a line"
```

---

### Task 7: Các việc đang chờ team, ở một chỗ

**Files:**
- Create: `frontend/lib/waiting-work.ts`, `frontend/lib/waiting-work.test.ts`
- Modify: `frontend/components/reports/ReportsDashboard.tsx`, `RecentActivitiesCard.tsx`

**Interfaces:** Produces

```ts
export interface WaitingItem { key: "readings" | "frames" | "events"; text: string; href: string }
/** The team's waiting work as links, in this order; a count of 0 or null (not loaded) gives no item. */
export function waitingWork(counts: { readings: number | null; frames: number | null; events: number | null; moreEvents?: boolean }): WaitingItem[];
/** Events without a verdict among those given (the latest page of Recent Shelf Activities). */
export function unconfirmedEvents(items: { verdict?: string }[]): number;
```

Câu chữ: `9 readings to review` → `/category`; `13 frames to label` → `/model`; `4 shelf events to confirm` →
`#recent-shelf-activities` (có `moreEvents` thì `20+ shelf events to confirm`). Số 1 dùng danh từ số ít.

- [ ] **Step 1: Test `frontend/lib/waiting-work.test.ts`**

```ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { unconfirmedEvents, waitingWork } from "./waiting-work.ts";

test("waiting work is listed as links, and nothing waiting lists nothing", () => {
  assert.deepEqual(waitingWork({ readings: 9, frames: 13, events: 4 }), [
    { key: "readings", text: "9 readings to review", href: "/category" },
    { key: "frames", text: "13 frames to label", href: "/model" },
    { key: "events", text: "4 shelf events to confirm", href: "#recent-shelf-activities" },
  ]);
  assert.deepEqual(waitingWork({ readings: 1, frames: 0, events: null }), [
    { key: "readings", text: "1 reading to review", href: "/category" },
  ]);
  assert.deepEqual(waitingWork({ readings: 0, frames: 0, events: 0 }), []);
  assert.deepEqual(waitingWork({ readings: null, frames: null, events: null }), []);
  assert.equal(waitingWork({ readings: 0, frames: 0, events: 20, moreEvents: true })[0].text, "20+ shelf events to confirm");
});

test("an event waits until someone gives a verdict", () => {
  assert.equal(unconfirmedEvents([{ verdict: "right" }, {}, { verdict: undefined }, { verdict: "unsure" }]), 2);
  assert.equal(unconfirmedEvents([]), 0);
});
```

- [ ] **Step 2: Chạy, phải fail; viết `waiting-work.ts`; chạy lại, phải pass**

- [ ] **Step 3: Nối vào Dashboard**

- `RecentActivitiesCard`: thêm prop `onFirstPage?: (items, hasMore) => void`, gọi khi trang đầu của bộ lọc "All" về;
  thẻ có `id="recent-shelf-activities"`.
- `ReportsDashboard` (chỉ khi là team): sau khi các số chính đã về, gọi lần lượt `api.getReviewQueue()` rồi
  `api.listAudits("pending", 0)`; đếm lần đọc đang chờ bằng `reviewSummary` sẵn có. Dải (`data-waiting-work`) nằm
  dưới bộ lọc: `Waiting for the team:` rồi các liên kết của `waitingWork`. Không có mục nào thì không vẽ dải.

- [ ] **Step 4: Build, lint, commit**

```bash
git add frontend/lib/waiting-work.ts frontend/lib/waiting-work.test.ts frontend/components/reports
git commit -m "Dashboard: the team's waiting work in one line, with links to where it is done"
```

---

### Task 8: Kiểm bản build trên máy, rồi deploy khi hoang duyệt

- [ ] **Step 1:** `python -m pytest -q`, `ruff check . && ruff format --check .`, `cd frontend && npm test && npm run build`

- [ ] **Step 2: Kiểm bằng trình duyệt trên bản build ở máy** (API thật, chặn mọi lệnh ghi; `sku_names` chưa có trên
  backend đang chạy nên điểm 4 chỉ kiểm sau khi deploy backend):

| # | Tài khoản | Điều phải đúng |
| --- | --- | --- |
| 1 | team | Model có `[data-run-status]` với câu bắt đầu bằng "Camera and worker"; biểu đồ By day có chú giải; không còn lựa chọn phiên bản tên `unknown` |
| 2 | team | mở "Label frames": có `[data-active-box]`; nhấn `1` thì hộp đó thành "Right" và hộp đang chọn chuyển đi; `[data-mark-rest]` bấm xong thì số hộp chưa có kết luận (không tính hộp "?") về 0; Enter khi Save còn khoá không gửi lệnh ghi nào; đóng mà không lưu |
| 3 | team | Dashboard có `[data-waiting-work]` với liên kết tới `/category` và `/model`; các số khớp số trên hai trang đó |
| 4 | team (sau deploy backend) | bảng Per SKU không còn ô nào bắt đầu bằng `TMP-MLK-` |
| 5 | team | thẻ sản phẩm: `[data-card-frame]` có `rect[data-box]`; `details[data-technical]` đóng; có "Human Audit & Correction" |
| 6 | người thường | thẻ sản phẩm tên "Product details", có `[data-card-frame]`, không có "SKU Code", không có form sửa |
| 7 | team (admin) | Settings: "Shelf plan" đứng trước "Monitored Stores"; không còn khối "Timezone" và "Low-Confidence Flag Threshold"; có `[data-timezone-note]` |
| 8 | người thường | Dashboard không có `[data-waiting-work]`; số lệnh gọi lúc mở vẫn là 8 |
| 9 | cả hai | không lệnh ghi nào bị chặn ngoài dự kiến; console không lỗi |

- [ ] **Step 3: DỪNG. Báo hoang và xin duyệt deploy**
- [ ] **Step 4 (sau khi duyệt):** backend (`backend_changeset.sh <sha> create`, xem, `execute`; chỉ mã), rồi Amplify,
  rồi chạy lại bảng kiểm trên bản thật kể cả điểm 4.
- [ ] **Step 5:** ghi memory; push và PR khi hoang bảo.
