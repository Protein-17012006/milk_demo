# Tối ưu website, đợt 2: Dashboard cho người thường — kế hoạch làm

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mở Dashboard là thấy ngay từng sản phẩm còn bao nhiêu, món nào hết hoặc sắp hết, số mới tới lúc nào, và
xem được ảnh kệ có khoanh hộp; các thẻ số và danh sách sự kiện gọn lại cho người thường.

**Architecture:**
- Backend: `/products` cho biết sản phẩm nào thuộc shelf plan, trạng thái hàng của nó, và khung hình mới nhất kèm
  hộp của từng sản phẩm (đọc từ chính các dòng `latest_stock` nó đã đọc). Check và sự kiện giữ thêm toạ độ hộp của
  sản phẩm trong hai ảnh sự kiện.
- Frontend: Dashboard gọi `/products` thay cho `/reports/series`; quy tắc thuần nằm trong `frontend/lib/shelf-now.ts`
  và `shelf-ui.ts` có test; các component mới chỉ vẽ.
- Số trên bảng Dashboard lấy cùng nguồn với trang Category (lần đọc mới nhất), nên hai trang không lệch nhau.

**Tech Stack:** Python 3.12 (Lambda, boto3), pytest + moto; Next.js 16.4.6 static export, React 19, `node --test`.

**Spec:** `docs/reviews/2026-11-26-website-feature-review.md`: thay đổi 3, 4, phần Dashboard của thay đổi 7, mục "Còn
thiếu" (bốn dòng đầu), và các dòng Dashboard / Category liên quan trong bảng từng trang. Toàn cảnh ba đợt:
`docs/superpowers/plans/2026-11-26-website-optimization-batch1.md`. hoang 26/11: giữ tiếng Anh; "cứ build đi".

Nhánh: `feat/website-optimization-2`, cắt từ `feat/website-optimization-1` (042f510, đang chạy thật từ 27/11 00:08).

## Những điều Claude tự quyết (báo cáo để ngỏ, hoang chưa nói)

1. **Số của bảng lấy từ lần đọc mới nhất** (như Category), không lấy mức đã "chốt qua hai lần kiểm" của phần sự
   kiện. Ngày 26/11 hai nguồn này lệch nhau (Slide Cheese: 3 so với 1); người xem sẽ thấy hai trang khác số nếu
   dùng nguồn kia.
2. **Trạng thái hàng tính trên chính con số đó** theo luật sẵn có của backend: 0 là hết, 1 đến 2 là sắp hết.
   **Thẻ "Out of stock now" đếm trên bảng**, không dùng `oos_now` của `/kpi` (số đó chờ hai lần kiểm liên tiếp), nên
   thẻ và bảng không bao giờ lệch nhau. Danh sách sự kiện vẫn theo luật hai lần kiểm.
3. **Ba thẻ của team rời Dashboard** (Active Stores Monitored, Avg. Inference Time, Top 50 SKU Accuracy) mà chưa
   thêm gì vào trang Model trong đợt này: Model đã có "Processing time" và "SKU identification"; dòng "camera và
   worker đang chạy" thuộc đợt 3.
4. **Ảnh kệ mở bằng một nút trên thẻ bảng**, không đặt ảnh thu nhỏ trên trang; đường dẫn ảnh đi kèm danh sách sản
   phẩm nên không thêm lệnh gọi nào.
5. **Hộp trong ảnh sự kiện chỉ có ở sự kiện sinh sau lần deploy này.** Sự kiện cũ hiện ảnh như hiện nay.
6. **Sản phẩm ngoài shelf plan ở Category** gom vào một khối đóng sẵn ở cuối, không ẩn hẳn.
7. **Sự kiện lặp được gộp** khi cùng tiệm, cùng sản phẩm, cùng loại và không có sự kiện loại khác của sản phẩm đó
   xen giữa.
8. **"One cycle"** được giải thích là hai tuần, chu kỳ đo của Datagent (theo thiết kế 24/11).

## Global Constraints

- Mọi ràng buộc của đợt 1 vẫn giữ: chữ tiếng Anh lời thường; team = `hasGroup("field_team", "team_admin")`; không
  số liệu giả; test thuần trong `frontend/lib`; commit bằng danh tính noreply kèm dòng Co-Authored-By; không push,
  không deploy khi hoang chưa duyệt; change set không `--tags`.
- **Không thêm lệnh gọi API lúc mở Dashboard:** `/products` thay `/reports/series`, và lệnh gọi trend `accuracy` bị
  bỏ. Dashboard còn 8 lệnh gọi (trước là 9).
- **`/products` được Category gọi mỗi 15 giây:** phần mới không được thêm lệnh đọc DynamoDB nào khi tiệm đã lưu
  shelf plan.
- **Luật trạng thái hàng** là `shelf.status_of` (0 hết; 1 đến `LOW_MAX` = 2 sắp hết). Frontend không tự tính lại.
- **Toạ độ hộp** là `[x, y, width, height]` theo pixel của khung hình gốc.
- **Ảnh** là khung hình đã che mặt người; đường dẫn ký sẵn sống 15 phút và không được ghi log.
- Phần ingest (tick 5 phút) chỉ được **thêm** trường; không đổi cách tính số đếm, trạng thái hay sự kiện.

## Review Focus

1. Tiệm chưa có shelf plan và chưa có gợi ý: Dashboard phải nói rõ điều đó, không hiện bảng rỗng hay số 0. Test:
   Task 2 `shelfNowRows([])`, `shelfNowSummary`.
2. Sản phẩm trong plan mà chưa từng được thấy (không có dòng tồn): phải hiện 0 hộp, "Out of stock". Test: Task 1
   `test_products_mark_the_shelf_plan_and_stock_status`.
3. Lần đọc mới nhất không có khung hình, hoặc đường dẫn đã hết hạn: nút "Shelf photo" phải khoá kèm lý do, hoặc tải
   lại danh sách trước khi mở. Test: Task 1 (frame không có ảnh), Task 2 `frameLegend`.
4. Sự kiện cũ không có hộp, hoặc ảnh đã hết hạn: hộp thoại ảnh vẫn hiện như hiện nay. Test: Task 8
   `test_photos_route_gives_null_for_a_missing_photo` (sửa), Task 6.
5. Gộp sự kiện không được nuốt mất sự kiện loại khác nằm giữa hai sự kiện cùng loại (LOW → RESTOCKED → LOW vẫn là ba
   dòng). Test: Task 6 `foldEvents`.

## File Structure

| File | Việc | Trách nhiệm |
| --- | --- | --- |
| `backend/api/handler.py` | sửa | `/products`: `in_shelf_plan`, `stock_status`, `as_of`, `frames`; `/shelf-events/photos`: hộp |
| `backend/shelf.py` | sửa | `build_check` giữ hộp của khung hình nó chọn |
| `backend/ingest/handler.py` | sửa | sự kiện giữ hộp của sản phẩm trong hai ảnh |
| `backend/openapi.yaml` | sửa | các trường mới |
| `tests/test_backend_integration_moto.py`, `tests/test_shelf.py` | sửa | test |
| `frontend/lib/shelf-now.ts` (+ test) | tạo | dòng của bảng, tổng, nhãn trạng thái, giờ cập nhật, chú giải ảnh kệ, tách theo plan |
| `frontend/lib/shelf-ui.ts` (+ test) | sửa | gộp sự kiện lặp |
| `frontend/lib/api.ts`, `reports-ui.ts` | sửa | kiểu mới; bỏ phần của biểu đồ cột |
| `frontend/components/reports/ShelfNowTable.tsx` | tạo | bảng "On the shelf now" |
| `frontend/components/common/ShelfFrameViewer.tsx` | tạo | ảnh kệ với hộp của nhiều sản phẩm |
| `frontend/components/reports/{ReportsDashboard,KpiGrid,FilterBar,TrendsInsightsChart,RecentActivitiesCard}.tsx` | sửa | bố cục mới, bốn thẻ, dòng cycle, bỏ tab accuracy, gộp sự kiện, ảnh |
| `frontend/components/reports/MonthlyStockChart.tsx` | xoá | biểu đồ trùng số với Trends |
| `frontend/components/category/CategoryProductsView.tsx`, `frontend/lib/products-ui.ts` | sửa | khối sản phẩm ngoài plan |

---

### Task 1: Backend: `/products` biết shelf plan, trạng thái hàng và khung hình mới nhất

**Files:**
- Modify: `backend/api/handler.py` (`_load_products_catalog`, `_handle_get_products` và dòng route của nó),
  `backend/openapi.yaml`
- Test: `tests/test_backend_integration_moto.py`

**Interfaces:**
- Produces, mỗi phần tử của `items`: `in_shelf_plan: bool`; `stock_status: "OOS" | "LOW" | "IN_STOCK" | null`
  (`shelf.status_of(unit_count)` khi thuộc plan, ngoài plan là `null`).
- Plan của một tiệm là `expected_skus` đã lưu; chưa lưu thì là danh sách gợi ý (`_suggested_skus`). Nhiều tiệm thì
  lấy hợp. Tiệm đã lưu plan không gây thêm lệnh đọc nào.
- Produces, ở gốc câu trả lời: `as_of: str | null` (giờ chụp mới nhất trong các dòng tồn); `frames: list`, mỗi
  camera có dòng tồn một phần tử:
  `{store_id, camera_id, capture_id, capture_timestamp, frame_presigned_url, faces_blurred, products: [{sku_id,
  sku_name, boxes: [[x, y, w, h], …]}]}`. `products` gồm các dòng tồn của đúng lần chụp mới nhất của camera đó, có ít
  nhất một hộp, bỏ dòng Unrecognized, xếp theo `sku_name`. `frame_presigned_url` là `null` khi lần chụp không có ảnh.
- `_handle_get_products(event, s3, ddb)`: thêm `s3` để ký đường dẫn.

- [ ] **Step 1: Viết test (phải fail)**

```python
@mock_aws
def test_products_mark_the_shelf_plan_and_stock_status(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _shelf_plan(expected=(CHEESE, HOT, TH_MERGED))
    _ingest(ingest, "CAM-S01-A", "140010", [("cheese145", 5), ("hot160", 2), ("original145", 4)])
    items = {p["sku_id"]: p for p in _call(api, "GET", "/v1/products", groups="datagent")[1]["items"]}
    assert (items[CHEESE]["in_shelf_plan"], items[CHEESE]["stock_status"]) == (True, "IN_STOCK")
    assert (items[HOT]["in_shelf_plan"], items[HOT]["stock_status"]) == (True, "LOW")
    assert (items[TH_MERGED]["in_shelf_plan"], items[TH_MERGED]["stock_status"]) == (True, "OOS")  # never seen
    assert (items["Slide Original 145g"]["in_shelf_plan"], items["Slide Original 145g"]["stock_status"]) == (
        False,
        None,
    )


@mock_aws
def test_products_carry_the_newest_frame_with_each_products_boxes(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "140010", [("original145", 1)], with_frame=True)
    _ingest(ingest, "CAM-S01-A", "140510", [("cheese145", 2), ("hot160", 1)], with_frame=True)
    body = _call(api, "GET", "/v1/products", groups="datagent")[1]
    assert body["as_of"] == "2026-11-21T14:05:10+07:00"
    (frame,) = body["frames"]
    assert (frame["camera_id"], frame["capture_id"]) == ("CAM-S01-A", "CAP-S01-20261121-140510")
    assert "CAM-S01-A_20261121_140510.jpg" in frame["frame_presigned_url"]
    assert [(p["sku_id"], p["boxes"]) for p in frame["products"]] == [
        (CHEESE, [[10, 20, 50, 80], [70, 20, 50, 80]]),
        (HOT, [[10, 20, 50, 80]]),
    ]


@mock_aws
def test_products_frame_without_a_stored_image_has_no_link(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    assert _call(api, "GET", "/v1/products", groups="datagent")[1]["frames"] == []
    _ingest(ingest, "CAM-S01-A", "140510", [("cheese145", 2)])
    (frame,) = _call(api, "GET", "/v1/products", groups="datagent")[1]["frames"]
    assert frame["frame_presigned_url"] is None and len(frame["products"]) == 1


@mock_aws
def test_products_read_nothing_extra_for_a_saved_plan(monkeypatch: pytest.MonkeyPatch):
    api, _ = _backend(monkeypatch)
    _shelf_plan(expected=(CHEESE,))
    monkeypatch.setattr(api, "_suggested_skus", lambda *a, **k: pytest.fail("a saved plan needs no suggestion"))
    assert _call(api, "GET", "/v1/products", groups="datagent")[0] == 200
```

Nhãn model trong `_ingest` (`cheese145`, `hot160`, `original145`) phải là nhãn mà `DEFAULT_ALIAS_MAP` đổi ra đúng
tên sản phẩm; xem `backend/common.py` và sửa nhãn trong test nếu khác.

- [ ] **Step 2: Chạy, phải fail**

Run: `python -m pytest tests/test_backend_integration_moto.py -q -k "shelf_plan_and_stock or newest_frame or stored_image or nothing_extra"`
Expected: 4 FAIL (`KeyError: 'in_shelf_plan'`, `KeyError: 'frames'`).

- [ ] **Step 3: Viết mã trong `backend/api/handler.py` theo khối Interfaces; cập nhật `backend/openapi.yaml`**

- [ ] **Step 4: Chạy cả file test, rồi lint và commit**

Run: `python -m pytest tests/test_backend_integration_moto.py -q` và `ruff check . && ruff format --check .`
Expected: tất cả PASS, lint sạch.

```bash
git add backend/api/handler.py backend/openapi.yaml tests/test_backend_integration_moto.py
git commit -m "Products: each row says whether it is on the shelf plan and how its stock stands; the newest frame comes with its boxes"
```

---

### Task 2: Frontend: quy tắc của bảng "On the shelf now"

**Files:**
- Create: `frontend/lib/shelf-now.ts`, `frontend/lib/shelf-now.test.ts`
- Modify: `frontend/lib/api.ts` (kiểu `ApiProduct`, `ApiProductsResponse`, `ApiShelfFrame`)

**Interfaces:**
- Consumes: các trường mới của Task 1.
- Produces (`frontend/lib/shelf-now.ts`):

```ts
export type StockStatus = "OOS" | "LOW" | "IN_STOCK";
export interface ShelfNowRow { skuId: string; name: string; imageUrl: string | null; units: number; status: StockStatus; badge: ReliabilityBadge | null }
/** Products of the shelf plan: out of stock first, then low, then in stock; fewer units first; then by name. */
export function shelfNowRows(products: ShelfNowInput[]): ShelfNowRow[];
export interface ShelfNowSummary { products: number; units: number; out: number; low: number }
export function shelfNowSummary(rows: ShelfNowRow[]): ShelfNowSummary;
export function stockStatusLabel(status: StockStatus): "Out of stock" | "Low" | "In stock";
/** "Updated at 15:45" for a reading of the same UTC+7 day as now, "Updated at 15:45 on 26/11" for an older one. */
export function updatedText(asOf: string | null, now: Date): string | null;
/** "Slide Cheese 145g", "A and B", "A, B and 2 more"; "" for none. */
export function namesText(names: string[]): string;
export function splitByPlan<T extends { inShelfPlan: boolean }>(items: T[]): { onPlan: T[]; offPlan: T[] };
export interface FrameLegendItem { name: string; count: number; color: string; boxes: Box[] }
/** One legend entry per product that has boxes, coloured in order from FRAME_COLORS (cycling). */
export function frameLegend(products: { sku_name: string; boxes: Box[] }[]): FrameLegendItem[];
```

`ShelfNowInput` = `Pick<ApiProduct, "sku_id" | "sku_name" | "image_url" | "unit_count" | "in_shelf_plan" |
"stock_status" | "reliability">`. `api.ts`: `in_shelf_plan?: boolean`, `stock_status?: StockStatus | null` trên
`ApiProduct`; `as_of?: string | null`, `frames?: ApiShelfFrame[]` trên `ApiProductsResponse`.

- [ ] **Step 1: Viết test `frontend/lib/shelf-now.test.ts`**

```ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { frameLegend, namesText, shelfNowRows, shelfNowSummary, splitByPlan, stockStatusLabel, updatedText } from "./shelf-now.ts";

const p = (sku_id: string, unit_count: number, stock_status: "OOS" | "LOW" | "IN_STOCK" | null, in_shelf_plan = true) => ({
  sku_id, sku_name: sku_id, image_url: null, unit_count, in_shelf_plan, stock_status,
});

test("the table lists the plan's products, the ones that need attention first", () => {
  const rows = shelfNowRows([p("Sour", 6, "IN_STOCK"), p("Hot", 2, "LOW"), p("Vinamilk", 0, null, false), p("TH", 0, "OOS"), p("Cheese", 3, "IN_STOCK"), p("Original", 1, "LOW")]);
  assert.deepEqual(rows.map((r) => [r.name, r.units, r.status]), [
    ["TH", 0, "OOS"], ["Original", 1, "LOW"], ["Hot", 2, "LOW"], ["Cheese", 3, "IN_STOCK"], ["Sour", 6, "IN_STOCK"],
  ]);
  assert.deepEqual(shelfNowSummary(rows), { products: 5, units: 12, out: 1, low: 2 });
});

test("no plan, or an older backend without the fields, gives no rows", () => {
  assert.deepEqual(shelfNowRows([]), []);
  assert.deepEqual(shelfNowRows([{ sku_id: "A", sku_name: "A", image_url: null, unit_count: 4 }]), []);
  assert.deepEqual(shelfNowSummary([]), { products: 0, units: 0, out: 0, low: 0 });
});

test("labels and the update line", () => {
  assert.equal(stockStatusLabel("OOS"), "Out of stock");
  assert.equal(stockStatusLabel("LOW"), "Low");
  assert.equal(stockStatusLabel("IN_STOCK"), "In stock");
  const now = new Date("2026-11-26T13:40:00Z"); // 20:40 on 26/11 in UTC+7
  assert.equal(updatedText("2026-11-26T15:45:23+07:00", now), "Updated at 15:45");
  assert.equal(updatedText("2026-11-25T21:58:02+07:00", now), "Updated at 21:58 on 25/11");
  assert.equal(updatedText(null, now), null);
  assert.equal(namesText([]), "");
  assert.equal(namesText(["A"]), "A");
  assert.equal(namesText(["A", "B"]), "A and B");
  assert.equal(namesText(["A", "B", "C", "D"]), "A, B and 2 more");
});

test("products off the plan are set apart", () => {
  const items = [{ id: 1, inShelfPlan: true }, { id: 2, inShelfPlan: false }, { id: 3, inShelfPlan: true }];
  assert.deepEqual(splitByPlan(items), { onPlan: [items[0], items[2]], offPlan: [items[1]] });
});

test("the shelf photo's legend: one colour per product that has boxes", () => {
  const legend = frameLegend([
    { sku_name: "Cheese", boxes: [[1, 2, 3, 4], [5, 6, 7, 8]] },
    { sku_name: "Gone", boxes: [] },
    { sku_name: "Hot", boxes: [[9, 9, 9, 9]] },
  ]);
  assert.deepEqual(legend.map((l) => [l.name, l.count]), [["Cheese", 2], ["Hot", 1]]);
  assert.notEqual(legend[0].color, legend[1].color);
});
```

- [ ] **Step 2: Chạy, phải fail; viết `shelf-now.ts` và các kiểu trong `api.ts`; chạy lại, phải pass**

Run: `cd frontend && npm test`

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/shelf-now.ts frontend/lib/shelf-now.test.ts frontend/lib/api.ts
git commit -m "Website: the rules of the Dashboard's per-product table (rows, totals, labels, update time)"
```

---

### Task 3: Dashboard: bảng từng sản phẩm, bốn thẻ số, giờ cập nhật

**Files:**
- Create: `frontend/components/reports/ShelfNowTable.tsx`
- Modify: `frontend/components/reports/ReportsDashboard.tsx`, `KpiGrid.tsx`, `frontend/lib/reports-ui.ts`,
  `frontend/lib/api.ts` (`getReportsSeries` và kiểu của nó, nếu không còn ai dùng)
- Delete: `frontend/components/reports/MonthlyStockChart.tsx`

**Interfaces:**
- Consumes: `shelfNowRows`, `shelfNowSummary`, `stockStatusLabel`, `updatedText`, `namesText` (Task 2).
- `ShelfNowTable` props: `{ rows: ShelfNowRow[] | null; loaded: boolean; onOpenPhoto?: () => void; photoReason:
  string | null }` (`rows === null`: chưa tải; `photoReason` khác null thì nút ảnh bị khoá và ghi lý do).
- `KpiGrid` props: `{ summary: ShelfNowSummary | null; outNames: string[]; kpi; sparklines; days; storeName }`.

Hành vi:
- `ReportsDashboard`: gọi `api.getProducts({ category })` ở chỗ đang gọi `getReportsSeries`; lỗi thì bảng ghi
  "The product list could not be loaded." còn các phần khác vẫn hiện.
- Dòng dưới tiêu đề (`data-updated`): `updatedText(as_of)` + ` · Shelf numbers are worked out every 5 minutes in
  opening hours.`; chưa có `as_of` thì chỉ còn câu sau.
- Bốn thẻ, lưới 2 × 2 (`data-kpi` lần lượt `on-shelf`, `oos-now`, `osa`, `restock`):

| Thẻ | Số chính | Dòng dưới |
| --- | --- | --- |
| On the shelf now | `summary.units` + `units` | `N products on the shelf plan` |
| Out of stock now | `summary.out` | có món hết: `namesText(outNames)`; không: `Every product on the plan has stock.`; có món sắp hết thì thêm dòng `Low: N` |
| On-Shelf Availability | `76.9%` | một dòng: `+2.1 pts vs the previous 14 days`, hoặc lý do bị chặn, hoặc `Share of opening-hours checks where a product had stock.` |
| Restock rate | `5.6 units/day` | `vs 4.1 units/day before`, hoặc `No earlier period to compare`, hoặc lý do bị chặn |

  Không có dòng nào trong plan (`summary.products === 0` sau khi đã tải): hai thẻ đầu ghi `—` và dòng
  `No shelf plan yet. An administrator sets it in Settings.` Hai thẻ sau giữ biểu đồ nhỏ như hiện nay.
- `ShelfNowTable` (`data-shelf-now`), tiêu đề "On the shelf now", dòng phụ "Each product on the shelf plan, at the
  latest reading." Mỗi dòng (`data-shelf-now-row`, `data-status`): ảnh nhỏ, tên, nhãn Reliability (như Category),
  số hộp, nhãn trạng thái (đỏ / vàng / xanh). Nút "Shelf photo" ở góc phải tiêu đề (`data-shelf-photo`); Task 4 nối.
- Bố cục: trên màn hình rộng, bốn thẻ chiếm 5 cột, bảng 7 cột; hẹp thì xếp dọc, bảng trước.
- Gỡ: thẻ Active Stores Monitored, Avg. Inference Time, Top 50 SKU Accuracy; `MonthlyStockChart`; trong
  `reports-ui.ts` các phần chỉ biểu đồ cột dùng (`ChartGranularity`, `GRANULARITY_OPTIONS`, `StockPoint`,
  `bucketStockSeries`, `SparklinePoint`) và các trường `KpiMetrics` không còn dùng.

- [ ] **Step 1: Viết `ShelfNowTable.tsx`, sửa `KpiGrid.tsx`, `ReportsDashboard.tsx`, `reports-ui.ts`; xoá `MonthlyStockChart.tsx`**
- [ ] **Step 2: Build, test, lint**

Run: `cd frontend && npm test && npm run build && npx eslint components/reports lib/reports-ui.ts`
Expected: PASS, build xong, không thêm lỗi lint.

- [ ] **Step 3: Commit**

```bash
git add -A frontend/components/reports frontend/lib/reports-ui.ts frontend/lib/api.ts
git commit -m "Dashboard: a table of what is on the shelf now, four cards a viewer can read, and when the numbers were updated"
```

---

### Task 4: Ảnh kệ có khoanh hộp trên Dashboard

**Files:**
- Create: `frontend/components/common/ShelfFrameViewer.tsx`
- Modify: `frontend/components/reports/ReportsDashboard.tsx`

**Interfaces:**
- Consumes: `frames` của `/products` (Task 1), `frameLegend` (Task 2), `focusRegion` (`lib/frame-geometry.ts`).
- `ShelfFrameViewer` props: `{ frame: ApiShelfFrame; onClose: () => void; onImageError: () => void }`.

Hành vi: toàn màn hình như `FrameViewer`. Thanh trên: giờ chụp (`HH:MM on DD/MM`), tổng số hộp, chú giải (một ô màu
và `tên × số hộp` cho mỗi sản phẩm), nút "Full frame / Zoom to boxes", nút đóng; Esc đóng. Hộp vẽ bằng màu của sản
phẩm đó. Mở ra ở mức phóng vào vùng có hộp.
Nút "Shelf photo" trên bảng: khoá với lý do "No photo was stored for the latest reading." khi không có khung hình
hoặc khung không có đường dẫn. Khi danh sách đã tải quá 10 phút thì tải lại `/products` rồi mới mở (đường dẫn sống
15 phút). Ảnh lỗi: đóng khung xem và ghi "The photo could not be loaded." cạnh nút.

- [ ] **Step 1: Viết `ShelfFrameViewer.tsx`, nối nút trong `ReportsDashboard.tsx`**
- [ ] **Step 2: Build, lint, commit**

Run: `cd frontend && npm test && npm run build && npx eslint components/common components/reports`

```bash
git add frontend/components/common/ShelfFrameViewer.tsx frontend/components/reports/ReportsDashboard.tsx
git commit -m "Dashboard: the latest shelf photo opens with every product's boxes drawn on it"
```

---

### Task 5: Trends bỏ tab của team; giải thích "cycle"

**Files:**
- Modify: `frontend/components/reports/TrendsInsightsChart.tsx`, `ReportsDashboard.tsx`, `FilterBar.tsx`

Hành vi: gỡ tab "Detection Accuracy" và lệnh gọi trend `accuracy` (Model đã có "By day"); `TrendTab` còn
`total_stock | oos | restock_volume`. Khi Timeframe đang chọn có chữ "cycle", dưới hàng bộ lọc hiện một dòng nhỏ
(`data-cycle-note`): `One cycle is two weeks, the period Datagent measures over.` Câu "Sign in with an approved
account to see trends." thành "Trends appear once your account is approved."

- [ ] **Step 1: Sửa ba file; build; lint; commit**

```bash
git add frontend/components/reports
git commit -m "Dashboard: the team's accuracy tab leaves Trends; the timeframe says what a cycle is"
```

---

### Task 6: Recent Shelf Activities: gộp sự kiện lặp, một nhãn độ tin cậy, ảnh mở to

**Files:**
- Modify: `frontend/lib/shelf-ui.ts`, `frontend/lib/shelf-ui.test.ts`,
  `frontend/components/reports/RecentActivitiesCard.tsx`

**Interfaces:**
- Produces (`shelf-ui.ts`):

```ts
export interface EventFold<T> { head: T; earlier: T[] }
/** items newest first. An event joins the fold of the same store, product and type unless an event of another type
 * for that store and product lies between them. Folds keep the order of their newest event. */
export function foldEvents<T extends { store_id: string; sku_id: string; type: string }>(items: T[]): EventFold<T>[];
/** "+3 earlier" for the toggle; null when there is nothing to unfold. */
export function earlierText(count: number): string | null;
```

- [ ] **Step 1: Thêm test vào `frontend/lib/shelf-ui.test.ts`**

```ts
test("repeated events of one product fold into the newest; another type in between keeps them apart", () => {
  const e = (sku_id: string, type: string, at: string) => ({ store_id: "S1", sku_id, type, at });
  const items = [
    e("Cheese", "LOW_STOCK", "5"), e("Original", "LOW_STOCK", "4"), e("Cheese", "LOW_STOCK", "3"),
    e("Cheese", "RESTOCKED", "2"), e("Cheese", "LOW_STOCK", "1"),
  ];
  const folds = foldEvents(items);
  assert.deepEqual(folds.map((f) => [f.head.sku_id, f.head.at, f.earlier.map((x) => x.at)]), [
    ["Cheese", "5", ["3"]], ["Original", "4", []], ["Cheese", "2", []], ["Cheese", "1", []],
  ]);
  assert.deepEqual(foldEvents([]), []);
  assert.equal(foldEvents([e("A", "OOS", "2"), { ...e("A", "OOS", "1"), store_id: "S2" }]).length, 2); // another store
  assert.equal(earlierText(0), null);
  assert.equal(earlierText(3), "+3 earlier");
});
```

- [ ] **Step 2: Chạy, phải fail; viết `foldEvents`, `earlierText`; chạy lại, phải pass**

- [ ] **Step 3: `RecentActivitiesCard.tsx`**

- Danh sách 20 sự kiện đầu và hộp "View all activity" đều vẽ theo `foldEvents`: dòng đầu là sự kiện mới nhất của
  nhóm; có sự kiện cũ hơn thì thêm nút `earlierText(n)` (`data-event-earlier`), bấm thì hiện các sự kiện đó thụt vào
  bên dưới, bấm lần nữa thì thu lại.
- Gỡ chữ đỏ "uncertain" (nhãn Reliability đã nói điều đó).
- Hộp ảnh: mỗi ảnh bấm vào thì mở to toàn màn hình (Esc hoặc bấm ra ngoài để đóng); ảnh không còn thì giữ ô "Photo
  no longer kept".

- [ ] **Step 4: Build, lint, commit**

```bash
git add frontend/lib/shelf-ui.ts frontend/lib/shelf-ui.test.ts frontend/components/reports/RecentActivitiesCard.tsx
git commit -m "Recent Shelf Activities: repeats of one product fold into one row, and each photo opens large"
```

---

### Task 7: Category: sản phẩm ngoài shelf plan xuống cuối

**Files:**
- Modify: `frontend/lib/products-ui.ts` (`SkuProduct.inShelfPlan`), `frontend/lib/review-queue.ts` (giá trị mặc
  định), `frontend/components/category/CategoryProductsView.tsx`, các test có dựng `SkuProduct`

**Interfaces:**
- Consumes: `in_shelf_plan` (Task 1), `splitByPlan` (Task 2).
- `SkuProduct.inShelfPlan: boolean` (dòng dựng từ hàng chờ duyệt: `false`).

Hành vi: khi có ít nhất một sản phẩm thuộc plan, bảng vẽ các nhóm của sản phẩm trong plan trước, rồi một dòng tiêu
đề (`data-off-plan`, `aria-expanded`) `Not on this store's shelf plan (N)`; bấm thì mở ra các nhóm của sản phẩm
ngoài plan. Mặc định đóng; đang tìm kiếm thì mở sẵn. Không sản phẩm nào thuộc plan (tiệm chưa có plan) thì bảng như
hiện nay.

- [ ] **Step 1: Sửa các file; `npm test`; build; lint; commit**

```bash
git add frontend/lib frontend/components/category/CategoryProductsView.tsx
git commit -m "Category: products that are not on the store's shelf plan sit in a closed section at the bottom"
```

---

### Task 8: Ảnh sự kiện phóng vào sản phẩm và khoanh hộp

**Files:**
- Modify: `backend/shelf.py` (`build_check`), `backend/ingest/handler.py` (`_event_photos`, `PHOTO_KEYS`,
  `display_fields`), `backend/api/handler.py` (`_handle_shelf_event_photos`), `backend/openapi.yaml`,
  `frontend/lib/api.ts` (`ApiEventPhotos`), `frontend/components/reports/RecentActivitiesCard.tsx`
- Test: `tests/test_shelf.py`, `tests/test_backend_integration_moto.py`

**Interfaces:**
- `shelf.build_check` thêm `"frame_boxes": {sku_id: [[x, y, w, h], …]}`: hộp của từng sản phẩm trong đúng lần chụp
  mà `image_key` lấy; `{}` khi check không có khung hình. Số đếm, `measurable` và các trường khác không đổi.
- Sự kiện thêm `boxes_before`, `boxes_after`: hộp của sản phẩm của sự kiện trong check mà ảnh tương ứng lấy từ đó
  (`[]` khi không có hộp). Chỉ được ghi cùng lúc ảnh được chép hoặc được tìm thấy; một lần tính lại giữ nguyên các
  trường này như đang giữ khoá ảnh.
- `GET /shelf-events/photos` thêm `before_boxes`, `after_boxes` (luôn là danh sách).
- `ApiEventPhotos`: `before_boxes?: Box[]`, `after_boxes?: Box[]`.

- [ ] **Step 1: Viết test (phải fail)**

`tests/test_shelf.py`:

```python
def test_a_check_keeps_the_boxes_of_the_frame_it_shows():
    with_frame = {**_capture("CAM-A", "140010", {CHEESE: 2}), "image_key": "frames/a.jpg", "source_bucket": "hub"}
    check = shelf.build_check("20261121-1400", [with_frame, _capture("CAM-A", "140130", {CHEESE: 3})])
    assert check["image_key"] == "frames/a.jpg"
    assert check["frame_boxes"] == {CHEESE: _boxes_of(with_frame, CHEESE)} and len(check["frame_boxes"][CHEESE]) == 2
    assert shelf.build_check("20261121-1400", [_capture("CAM-A", "140010", {CHEESE: 2})])["frame_boxes"] == {}
```

(`_capture` là hàm dựng capture sẵn có của file test; `_boxes_of` đọc `bounding_box` của dòng sản phẩm đó trong
`rows_json`. Tên và tham số theo đúng hàm đang có trong `tests/test_shelf.py`.)

`tests/test_backend_integration_moto.py`:

```python
@mock_aws
def test_an_event_keeps_the_products_boxes_in_its_two_photos(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _shelf_plan()
    _framed_cheese_then_empty(ingest)
    _tick(ingest)
    event = _oos_event()
    assert len(event["boxes_before"]) >= 1 and event["boxes_after"] == []  # the cheese was there, then it was not
    query = {"store_id": "DEMO-S01", "event_key": OOS_KEY}
    body = _call(api, "GET", "/v1/shelf-events/photos", groups="datagent", query=query)[1]
    assert body["before_boxes"] == event["boxes_before"] and body["after_boxes"] == []
    ingest.shelf_recompute("DEMO-S01")
    assert _oos_event()["boxes_before"] == event["boxes_before"]  # a recompute keeps them
```

Trong `test_photos_route_gives_null_for_a_missing_photo`, câu trả lời của sự kiện không có ảnh thành
`{"before_url": None, "after_url": None, "before_boxes": [], "after_boxes": []}`.

- [ ] **Step 2: Chạy, phải fail; viết mã backend; chạy cả hai file test, phải pass**

Run: `python -m pytest tests/test_shelf.py tests/test_backend_integration_moto.py -q`

- [ ] **Step 3: Frontend: hộp ảnh của sự kiện**

Có ít nhất một hộp ở một trong hai ảnh: cả hai ảnh vẽ bằng SVG, phóng vào `focusRegion([...before, ...after])`, mỗi
ảnh khoanh các hộp của riêng nó; dòng dưới mỗi ảnh ghi `N boxes of this product` (0 thì `None of this product in
view`). Không có hộp nào: ảnh hiện như hiện nay. Bấm vào ảnh vẫn mở to (Task 6).

- [ ] **Step 4: Chạy toàn bộ test, lint, commit**

Run: `python -m pytest -q` và `cd frontend && npm test && npm run build`

```bash
git add backend tests frontend/lib/api.ts frontend/components/reports/RecentActivitiesCard.tsx
git commit -m "Shelf events: the two photos zoom on the product and outline its boxes"
```

---

### Task 9: Kiểm bản build trên máy, rồi deploy khi hoang duyệt

- [ ] **Step 1: Toàn bộ test và build**

Run: `python -m pytest -q`, `ruff check . && ruff format --check .`, `cd frontend && npm test && npm run build`

- [ ] **Step 2: Kiểm bằng trình duyệt trên bản build ở máy**

Backend mới chưa chạy thật, nên script tự trả lời `GET /products` bằng câu trả lời thật của API cộng các trường mới
(tính theo đúng luật của Task 1 từ chính câu trả lời đó), và chặn mọi lệnh ghi như đợt 1. Điều phải đúng:

| # | Tài khoản | Điều phải đúng |
| --- | --- | --- |
| 1 | người thường | Dashboard có `[data-shelf-now]` với đúng số dòng bằng số sản phẩm trong plan; dòng hết hàng đứng trước |
| 2 | người thường | tổng ở thẻ `on-shelf` bằng tổng số hộp các dòng; thẻ `oos-now` bằng số dòng `data-status="OOS"` |
| 3 | người thường | có `[data-updated]` bắt đầu bằng "Updated at"; không còn "Active Stores Monitored", "Avg. Inference Time", "Top 50 SKU Accuracy", "Shelf Stock Count", "Detection Accuracy" |
| 4 | người thường | bấm `[data-shelf-photo]` mở khung xem có ít nhất một `rect[data-box]` và chú giải; Esc đóng |
| 5 | người thường | Recent Shelf Activities không có chữ "uncertain"; nếu có `[data-event-earlier]` thì bấm vào hiện thêm dòng |
| 6 | người thường | Category có `[data-off-plan]` đóng sẵn; bấm thì số `[data-sku-row]` tăng lên |
| 7 | người thường | số lệnh gọi API lúc mở Dashboard không quá 8 |
| 8 | team | Dashboard như trên và vẫn có nút Right / Wrong / Unsure ở sự kiện |
| 9 | cả hai | bề ngang 390 px: bảng nằm trọn trong màn hình, không cuộn ngang cả trang |
| 10 | cả hai | không lệnh ghi nào bị chặn; console không có lỗi ngoài 404 của file prefetch |

- [ ] **Step 3: DỪNG. Báo hoang và xin duyệt deploy**

- [ ] **Step 4 (sau khi duyệt): backend trước** (`backend_changeset.sh <sha> create`, xem, `execute`: chỉ mã của hai
  Lambda, template không đổi), kiểm `/products` thật có các trường mới và tick 5 phút không lỗi; **rồi website**
  (Amplify), chạy lại bảng kiểm trên bản thật không dùng câu trả lời giả.
- [ ] **Step 5:** ghi memory; push và PR khi hoang bảo.
