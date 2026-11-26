# Tối ưu website, đợt 1: sửa cái hỏng, dọn cái thừa — kế hoạch làm

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nút Export chạy lại; đăng nhập xong vào thẳng Dashboard; trên điện thoại thanh bên tự thu gọn; việc của
team chỉ hiện cho team; các nút không có tác dụng bị gỡ; chữ kỹ thuật được viết lại bằng tiếng Anh dễ hiểu.

**Architecture:**
- Backend: `_handle_export_csv` đọc theo khoảng ngày (lọc ngay trong lệnh scan, chỉ lấy cột cần), dựng CSV từng
  capture một, ghi file vào `exports/` của bucket analytics và trả đường dẫn tải có hạn 10 phút. Template thêm một
  luật xoá `exports/` sau 1 ngày.
- Frontend: một component `ExportCsvButton` dùng chung cho Category và Dashboard. Các quy tắc thuần (khoảng ngày,
  thu gọn thanh bên, trạng thái khung trang, cột của Category, đọc file import) nằm trong `frontend/lib/*.ts` có
  test; component chỉ nối dây.
- Không đổi API nào khác, không đổi dữ liệu, không đổi quyền ở backend.

**Tech Stack:** Python 3.12 (Lambda, boto3), pytest + moto; CloudFormation (`infra/backend.yaml`); Next.js 16.4.6
static export, React 19, `node --test`.

**Spec:** `docs/reviews/2026-11-26-website-feature-review.md`: thay đổi 1, 2, 5, 6, 9, 10 và các dòng liên quan
trong bảng từng trang. hoang 26/11: giữ tiếng Anh; chia ba đợt, mỗi đợt deploy và kiểm riêng; "cứ build đi".

## Toàn cảnh ba đợt

| Đợt | Làm gì | Thay đổi trong báo cáo | Backend | Kế hoạch |
| --- | --- | --- | --- | --- |
| 1 | Sửa Export; vào thẳng Dashboard; thanh bên trên điện thoại; việc của team chỉ hiện cho team; gỡ nút giả; viết lại chữ | 1, 2, 5, 6, 9, 10 | Có (Export) | file này |
| 2 | Dashboard cho người thường: bảng từng sản phẩm, thẻ "hết hàng lúc này", dọn sáu thẻ số, giờ cập nhật, ảnh kệ mới nhất có khoanh hộp, gộp sự kiện lặp, sản phẩm ngoài shelf plan gom xuống cuối | 3, 4, một phần 7 | Có (toạ độ hộp cho ảnh sự kiện) | viết khi đợt 1 đã chạy thật |
| 3 | Công cụ của team: thẻ sản phẩm có ảnh lên đầu, gán nhãn nhanh hơn, dòng "camera và worker đang chạy", Settings xếp lại, số việc đang chờ ở một chỗ | 8, phần còn lại của 7 | Không | viết khi đợt 2 đã chạy thật |

Nhánh: `feat/website-optimization-1`, cắt từ `docs/website-feature-review` (9f0bb86 = mã đang chạy 3508cc3 + tài
liệu đánh giá). Đợt sau cắt từ nhánh đợt trước.

## Những điều Claude tự quyết (báo cáo để ngỏ, hoang chưa nói)

1. **Mọi tài khoản đăng nhập xong đều vào Dashboard**, và ô "Default Landing Page" trong Settings bị gỡ (báo cáo
   cho hai lựa chọn: nối cho có tác dụng, hoặc gỡ). Lý do: một luật duy nhất, không thêm lệnh gọi API lúc đăng
   nhập.
2. **Trang Home bị gỡ hẳn.** Địa chỉ `/` hiện Dashboard; `/dashboard` vẫn chạy. Ô tìm của Home không chuyển đi đâu
   vì Category đã có ô tìm theo tên.
3. **Chưa đăng nhập thì mọi trang chuyển về `/login`.** Liên kết "Back to Workspace" ở trang đăng nhập bị gỡ.
4. **Export:** chọn ngày đầu và ngày cuối, tối đa 7 ngày (capture chỉ được giữ 7 ngày), mặc định là hôm nay. Người
   thường vẫn thấy hai nút xuất vì backend cho nhóm `datagent` xuất CSV và Datagent là bên nhận file này.
5. **Bốn liên kết chân trang gỡ hết** (chưa có địa chỉ liên hệ thật để giữ lại một cái).
6. **Menu "..." của từng dòng ở Category gỡ hết**, kể cả "Export Row CSV".
7. **Người thường ở Category** không thấy cột SKU CODE, cột CONFIDENCE, bộ lọc Status và lựa chọn sắp xếp theo
   confidence; họ còn một nhãn Reliability dưới tên sản phẩm. Website cũng không gọi `/review-queue` cho họ.
8. **Tiệm chỉ có một** thì ẩn bộ lọc Store (Dashboard, Category) và cột AVAIL IN STORES.
9. **Nhóm sản phẩm ở Category mở sẵn.**
10. **Nút "Import SKU Master" sang Settings** là một nút chọn file như "Import Store List", không còn hộp thoại
    riêng (hộp thoại cũ ghi nhận `.xlsx` trong khi chỉ đọc được `.csv` và `.json`).

## Global Constraints

- **Chữ trên màn hình bằng tiếng Anh, lời thường.** Không còn `AWS`, `Cognito`, `DynamoDB`, tên bảng, tên biến môi
  trường, mã HTTP hay tên nhóm trong câu chữ dành cho người dùng. Tên nhóm chỉ còn ở menu tài khoản và khối Account.
- **Ba mức quyền ở giao diện:** team = `hasGroup("field_team", "team_admin")`; admin = `hasGroup("team_admin")`;
  người thường = mọi tài khoản còn lại (kể cả `datagent`).
- **Không số liệu giả, không đo lượt dùng, không số bán.**
- **Không thêm lệnh gọi API lúc mở trang:** tài khoản AWS chỉ chạy 10 Lambda cùng lúc.
- **Captures được giữ 7 ngày** (`CAPTURE_TTL_DAYS`), nên `EXPORT_MAX_DAYS = 7`. Ngày tính theo ICT (UTC+7).
- **Next.js 16:** đọc phần liên quan trong `frontend/node_modules/next/dist/docs/` trước khi viết mã dùng API của
  Next (`frontend/AGENTS.md`). Website là static export (`output: "export"`, `trailingSlash: true`).
- **Test frontend:** logic thuần nằm trong `frontend/lib/<tên>.ts`, test ở `frontend/lib/<tên>.test.ts`, import
  bằng `./<tên>.ts`, chỉ import kiểu (type-only) từ module khác. Chạy: `cd frontend && npm test`. Build:
  `cd frontend && npm run build`.
- **Test backend:** `python -m pytest tests/test_backend_integration_moto.py -q` trong một venv đã cài
  `requirements-dev.txt`.
- **Lint:** không thêm lỗi mới ở file đã sửa (`cd frontend && npx eslint <file>`). Repo có sẵn 5 lỗi
  `react-hooks/set-state-in-effect`; `next build` không chạy lint.
- **Commit:** danh tính noreply qua `-c user.name="Nguyen Huy Hoang" -c
  user.email="Protein-17012006@users.noreply.github.com"`; câu tiếng Anh dạng "Area: what changed"; kết thúc bằng
  dòng `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>`.
- **Không push, không deploy khi hoang chưa duyệt.** Deploy backend bằng change set, không `--tags`. Không xoá bucket
  `milk-development-754361433393`.

## Review Focus

1. Xuất một ngày không có capture nào: người dùng mong nhận file chỉ có dòng tiêu đề và một câu nói rõ, không phải
   lỗi. Test: Task 1 `test_export_empty_day_gives_header_only`, Task 2 `exportDoneText(0, …)`.
2. Khoảng ngày gõ tay sai (ngày tương lai, cũ hơn 7 ngày, đầu sau cuối): mong có câu báo trước khi gửi yêu cầu, và
   backend cũng từ chối. Test: Task 2 `exportRangeError`, Task 1 `test_export_rejects_bad_ranges`.
3. Tài khoản vừa đăng ký, chưa có nhóm: mong thấy dòng "chờ duyệt", không bị đẩy về trang đăng nhập và không thấy
   công cụ của team. Test: Task 3 `shellState` ("waiting"), Task 5 `categoryColumns(false, …)`.
4. Người dùng điện thoại tự mở thanh bên, hoặc xoay ngang máy: mong lựa chọn của họ được giữ. Test: Task 4
   `isCollapsed`.
5. File import rỗng, chỉ có dòng tiêu đề, hoặc không phải danh sách: mong không có yêu cầu nào gửi đi và có câu báo.
   Test: Task 5 `parseImportFile`.

## File Structure

| File | Việc | Trách nhiệm |
| --- | --- | --- |
| `backend/common.py` | sửa | thêm `csv_rows` (các dòng dữ liệu, không tiêu đề) |
| `backend/api/handler.py` | sửa | `_handle_export_csv`: khoảng ngày, đọc gọn, ghi S3, trả đường dẫn |
| `backend/openapi.yaml` | sửa | tham số và câu trả lời mới của hai route export |
| `infra/backend.yaml` | sửa | luật `expire-exports-1d` cho `exports/` |
| `tests/test_backend_integration_moto.py` | sửa | test export |
| `frontend/lib/export-ui.ts` (+ test) | tạo | khoảng ngày xuất file và câu chữ của nó |
| `frontend/components/common/ExportCsvButton.tsx` | tạo | nút xuất file dùng chung |
| `frontend/lib/shell-ui.ts` (+ test) | tạo | trang đến sau đăng nhập, trạng thái khung trang |
| `frontend/lib/sidebar-ui.ts` (+ test) | tạo | mục đang chọn, thu gọn thanh bên |
| `frontend/lib/import-parse.ts` (+ test) | tạo | đọc file import `.json` / `.csv` thành danh sách dòng |
| `frontend/lib/products-ui.ts` (+ test) | sửa | "Not flagged", cột theo quyền, lựa chọn sắp xếp theo quyền |
| `frontend/lib/product-groups.ts` (+ test) | sửa | bỏ `groupSelection` |
| `frontend/lib/reliability-ui.ts`, `shelf-ui.ts`, `health-ui.ts` (+ test) | sửa | câu chữ |
| `frontend/lib/api.ts` | sửa | `exportCsvLink`; bỏ `exportCvOutputCsv`, `exportCaptureLogCsv`, `searchCatalog`, `updateSettings` |
| `frontend/lib/home-ui.ts`, `frontend/components/home/HomePageView.tsx` | xoá | trang Home |
| `frontend/components/layout/SidebarContext.tsx` | xoá | ô Quick search |
| `frontend/app/(dashboard)/page.tsx` | sửa | `/` hiện Dashboard |
| `frontend/components/layout/{DashboardShell,Sidebar}.tsx` | sửa | chuyển về login, dòng chờ duyệt, thanh bên |
| `frontend/components/auth/{LoginView,RegisterView,AuthShell}.tsx` | sửa | trang đến, gỡ nút giả, câu chữ |
| `frontend/components/category/{CategoryProductsView,ProductRow,ProductGroupRow,ProductDetailsModal,ReviewQueue}.tsx` | sửa | quyền, cột, gỡ ô chọn và menu, export |
| `frontend/components/reports/{ReportsDashboard,FilterBar}.tsx` | sửa | export, câu chữ, ẩn Store khi một tiệm |
| `frontend/components/settings/SettingsView.tsx` | sửa | gỡ preferences, thêm Import SKU Master, câu chữ |

---

### Task 1: Backend: export theo khoảng ngày, trả đường dẫn tải

**Files:**
- Modify: `backend/common.py` (cạnh `to_csv`), `backend/api/handler.py` (`_handle_export_csv` và hai dòng route
  `/exports/*.csv`), `backend/openapi.yaml` (`/exports/cv-output.csv`, `/exports/capture-log.csv`),
  `infra/backend.yaml` (`AnalyticsBucket.LifecycleConfiguration.Rules`)
- Test: `tests/test_backend_integration_moto.py`

**Interfaces:**
- Produces: `common.csv_rows(records: list[dict[str, Any]], columns: list[str]) -> str`: chỉ các dòng dữ liệu, mỗi
  dòng kết thúc bằng `\n`, không tiêu đề, không BOM. Kết quả của `to_csv` giữ nguyên từng byte.
- Produces: `GET /exports/{cv-output|capture-log}.csv` với query:
  - `from`, `to`: `YYYY-MM-DD` theo ICT, tính cả hai đầu. Chỉ có một trong hai thì cái kia bằng nó. `date` = `from`
    = `to` (giữ cho tương thích). Không có tham số ngày nào: lấy mọi capture như cũ.
  - `camera`: như cũ.
  - `link=1`: trả JSON `{"url", "filename", "rows", "bytes", "from", "to", "expires_in": 600}`. Không có `link`: trả
    chữ CSV như cũ.
  - Lỗi 400: `{"error": "INVALID_DATE"}` (không phải ngày thật dạng `YYYY-MM-DD`), `{"error": "INVALID_RANGE"}`
    (`from` sau `to`), `{"error": "RANGE_TOO_LONG", "max_days": 7}` (quá 7 ngày).
  - `filename`: `<kind>_<from>_<to>.csv`; một ngày thì `<kind>_<ngày>.csv`; không có ngày thì `<kind>_all.csv`.
  - File nằm ở `exports/<kind>/<uuid4 hex>/<filename>` trong `ANALYTICS_BUCKET`. Đường dẫn ký sẵn `get_object`,
    `ExpiresIn=600`, kèm `ResponseContentDisposition: attachment; filename="<filename>"` và
    `ResponseContentType: text/csv; charset=utf-8`.
  - `rows` là số dòng dữ liệu (không tính tiêu đề); `bytes` là cỡ file UTF-8.
- Đọc bảng: `_scan_all` với `ProjectionExpression` là `camera_id, capture_timestamp, rows_json` (cv-output) hoặc
  `camera_id, capture_timestamp, log_json` (capture-log); có khoảng ngày thì thêm `FilterExpression`
  `capture_timestamp >= from` và `< ngày sau to`. CSV dựng từng capture một bằng `csv_rows`, không gom mọi dòng vào
  một danh sách.

- [ ] **Step 1: Viết test (chưa có mã nên phải fail)**

Thêm cuối `tests/test_backend_integration_moto.py`. Capture được đặt thẳng vào bảng để chọn được ngày:

```python
def _put_capture(day: str, hhmmss: str, units: int, camera_id: str = "CAM-S01-A") -> str:
    capture_id = f"CAP-S01-{day.replace('-', '')}-{hhmmss.replace(':', '')}"
    ts = f"{day}T{hhmmss}+07:00"
    row = {col: "" for col in common.CV_OUTPUT_COLUMNS} | {
        "reading_id": f"RD-{capture_id}",
        "capture_id": capture_id,
        "store_id": "DEMO-S01",
        "camera_id": camera_id,
        "capture_timestamp": ts,
        "sku_id": CHEESE,
        "sku_name": "Sữa, có dấu phẩy",
        "unit_count": units,
    }
    log = {col: "" for col in common.CAPTURE_LOG_COLUMNS} | {"capture_id": capture_id, "capture_timestamp": ts}
    _table("test-captures").put_item(
        Item={
            "camera_id": camera_id,
            "capture_id": capture_id,
            "capture_timestamp": ts,
            "rows_json": json.dumps([row], ensure_ascii=False),
            "log_json": json.dumps(log, ensure_ascii=False),
            "detections_json": "x" * 1000,
        }
    )
    return capture_id


def _export(api, kind="cv-output", **query):
    return api.lambda_handler(_auth_event("GET", f"/v1/exports/{kind}.csv", groups="datagent", query=query))


def test_csv_rows_matches_to_csv():
    cols = ["a", "b"]
    recs = [{"a": "Sữa, tươi", "b": None}, {"a": 1, "b": True}]
    assert "﻿" + "a,b\n" + common.csv_rows(recs, cols) == common.to_csv(recs, cols)
    assert common.csv_rows([], cols) == ""


@mock_aws
def test_export_date_range_keeps_only_those_days(monkeypatch):
    api, _ = _backend(monkeypatch)
    for day in ("2026-11-23", "2026-11-24", "2026-11-25"):
        _put_capture(day, "10:00:00", 2)
    body = _export(api, **{"from": "2026-11-24", "to": "2026-11-25"})["body"]
    lines = body.lstrip("﻿").splitlines()
    assert lines[0].split(",") == common.CV_OUTPUT_COLUMNS
    assert len(lines) == 3 and "20261123" not in body
    assert len(_export(api)["body"].splitlines()) == 4  # no dates: everything, as before
    assert len(_export(api, date="2026-11-23")["body"].splitlines()) == 2  # old single-day parameter
    assert len(_export(api, to="2026-11-25")["body"].splitlines()) == 2  # one end given: that day only


@mock_aws
def test_export_link_writes_file_and_returns_link(monkeypatch):
    api, _ = _backend(monkeypatch)
    _put_capture("2026-11-24", "10:00:00", 2)
    _put_capture("2026-11-25", "10:00:00", 3)
    query = {"from": "2026-11-24", "to": "2026-11-25"}
    resp = _export(api, link="1", **query)
    assert resp["statusCode"] == 200
    out = json.loads(resp["body"])
    assert out["filename"] == "cv-output_2026-11-24_2026-11-25.csv"
    assert (out["rows"], out["from"], out["to"], out["expires_in"]) == (2, "2026-11-24", "2026-11-25", 600)
    assert "exports/cv-output/" in out["url"] and "response-content-disposition" in out["url"].lower()
    s3 = boto3.client("s3", region_name="ap-southeast-1")
    keys = [
        o["Key"] for o in s3.list_objects_v2(Bucket="test-analytics-bucket", Prefix="exports/cv-output/")["Contents"]
    ]
    assert len(keys) == 1 and keys[0].endswith("/" + out["filename"])
    stored = s3.get_object(Bucket="test-analytics-bucket", Key=keys[0])["Body"].read()
    assert stored.decode("utf-8") == _export(api, **query)["body"]
    assert out["bytes"] == len(stored)


@mock_aws
def test_export_empty_day_gives_header_only(monkeypatch):
    api, _ = _backend(monkeypatch)
    _put_capture("2026-11-24", "10:00:00", 2)
    out = json.loads(_export(api, link="1", date="2026-11-20")["body"])
    assert out["rows"] == 0 and out["filename"] == "cv-output_2026-11-20.csv"
    assert _export(api, date="2026-11-20")["body"] == "﻿" + ",".join(common.CV_OUTPUT_COLUMNS) + "\n"


@mock_aws
def test_export_rejects_bad_ranges(monkeypatch):
    api, _ = _backend(monkeypatch)

    def error(**query):
        resp = _export(api, **query)
        return resp["statusCode"], json.loads(resp["body"])["error"]

    assert error(**{"from": "2026-11-25", "to": "2026-11-24"}) == (400, "INVALID_RANGE")
    assert error(**{"from": "2026-11-01", "to": "2026-11-26"}) == (400, "RANGE_TOO_LONG")
    assert error(**{"from": "26/11/2026"}) == (400, "INVALID_DATE")
    assert error(date="2026-02-30") == (400, "INVALID_DATE")
    assert _export(api, **{"from": "2026-11-20", "to": "2026-11-26"})["statusCode"] == 200  # exactly 7 days


@mock_aws
def test_export_capture_log_link(monkeypatch):
    api, _ = _backend(monkeypatch)
    _put_capture("2026-11-24", "10:00:00", 2)
    out = json.loads(_export(api, kind="capture-log", link="1", date="2026-11-24")["body"])
    assert (out["filename"], out["rows"]) == ("capture-log_2026-11-24.csv", 1)
    header = _export(api, kind="capture-log", date="2026-11-24")["body"].lstrip("﻿").splitlines()[0]
    assert header.split(",") == common.CAPTURE_LOG_COLUMNS


@mock_aws
def test_export_scan_is_filtered_and_projected(monkeypatch):
    api, _ = _backend(monkeypatch)
    seen = {}
    real = api._scan_all
    monkeypatch.setattr(api, "_scan_all", lambda table, **kw: seen.update(kw) or real(table, **kw))
    _export(api, date="2026-11-24")
    assert seen["ProjectionExpression"] == "camera_id, capture_timestamp, rows_json" and "FilterExpression" in seen
    seen.clear()
    _export(api, kind="capture-log")
    assert seen["ProjectionExpression"] == "camera_id, capture_timestamp, log_json" and "FilterExpression" not in seen
```

- [ ] **Step 2: Chạy test, phải fail**

Run: `python -m pytest tests/test_backend_integration_moto.py -q -k "export or csv_rows"`
Expected: các test mới FAIL (`AttributeError: csv_rows`, `KeyError`/`JSONDecodeError` ở các test còn lại); test cũ
`test_end_to_end…` phần export vẫn PASS.

- [ ] **Step 3: Thêm `csv_rows` vào `backend/common.py`; `to_csv` gọi nó**

- [ ] **Step 4: Viết lại `_handle_export_csv(kind: str, event, s3, ddb)` theo khối Interfaces; hai dòng route truyền thêm `s3`**

Hằng số cạnh hàm: `EXPORT_MAX_DAYS = 7`, `EXPORT_LINK_SECONDS = 600`. Ngày được kiểm bằng
`datetime.strptime(value, "%Y-%m-%d")` và phải khớp lại đúng chuỗi đã nhận.

- [ ] **Step 5: Chạy test, phải pass**

Run: `python -m pytest tests/test_backend_integration_moto.py -q`
Expected: tất cả PASS.

- [ ] **Step 6: Thêm luật vòng đời vào `infra/backend.yaml`, cập nhật `backend/openapi.yaml`**

```yaml
          - Id: expire-exports-1d
            Status: Enabled
            Prefix: exports/
            ExpirationInDays: 1
            NoncurrentVersionExpiration:
              NoncurrentDays: 1
```

Run: `python -c "import yaml,sys; yaml.safe_load(open('backend/openapi.yaml', encoding='utf-8')); print('ok')"` và
`aws cloudformation validate-template --template-body file://infra/backend.yaml --region ap-southeast-1` (lệnh chỉ
đọc; template lớn hơn 51.200 byte thì bỏ qua lệnh này và để bước change set ở Task 8 kiểm).
Expected: `ok`; validate không báo lỗi.

- [ ] **Step 7: Chạy cả bộ test backend rồi commit**

Run: `python -m pytest -q`
Expected: không có test nào fail.

```bash
git add backend/common.py backend/api/handler.py backend/openapi.yaml infra/backend.yaml tests/test_backend_integration_moto.py
git commit -m "Export: a date range, a lean read and a download link instead of a 6 MB answer"
```

---

### Task 2: Frontend: nút xuất file dùng chung

**Files:**
- Create: `frontend/lib/export-ui.ts`, `frontend/lib/export-ui.test.ts`,
  `frontend/components/common/ExportCsvButton.tsx`
- Modify: `frontend/lib/api.ts` (hai hàm export), `frontend/components/category/CategoryProductsView.tsx` (nút
  "Export CV Output", xoá `handleExportCsv`), `frontend/components/reports/ReportsDashboard.tsx` (nút "Download",
  xoá `handleDownloadCsv`)

**Interfaces:**
- Consumes: route export của Task 1 với `link=1`.
- Produces (`frontend/lib/export-ui.ts`):

```ts
export type ExportKind = "cv-output" | "capture-log";
export interface ExportRange { from: string; to: string } // YYYY-MM-DD in UTC+7, both ends included
export const EXPORT_MAX_DAYS = 7;
export function ictDay(now: Date): string;
export function defaultExportRange(now: Date): ExportRange;   // today to today
export function earliestExportDay(now: Date): string;          // today minus 6 days
export function exportRangeError(range: ExportRange, now: Date): string | null;
export function exportDoneText(rows: number, range: ExportRange): string;
```

- Produces (`frontend/lib/api.ts`): `interface ApiExportLink { url: string; filename: string; rows: number; bytes:
  number; from: string; to: string; expires_in: number }` và
  `exportCsvLink(kind: ExportKind, range: ExportRange): Promise<ApiExportLink>` (GET
  `/exports/<kind>.csv?from=…&to=…&link=1`). `exportCvOutputCsv` và `exportCaptureLogCsv` bị xoá.
- Produces: `<ExportCsvButton kind label className? request />` với
  `request: (kind: ExportKind, range: ExportRange) => Promise<ApiExportLink>`.

- [ ] **Step 1: Viết test `frontend/lib/export-ui.test.ts`**

```ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { defaultExportRange, earliestExportDay, exportDoneText, exportRangeError, ictDay } from "./export-ui.ts";

const NOW = new Date("2026-11-26T13:40:00Z"); // 20:40 on 26/11 in UTC+7

test("the day is the UTC+7 day", () => {
  assert.equal(ictDay(NOW), "2026-11-26");
  assert.equal(ictDay(new Date("2026-11-26T17:30:00Z")), "2026-11-27"); // 00:30 the next day in UTC+7
  assert.deepEqual(defaultExportRange(NOW), { from: "2026-11-26", to: "2026-11-26" });
  assert.equal(earliestExportDay(NOW), "2026-11-20");
});

test("a range is checked before anything is sent", () => {
  assert.equal(exportRangeError({ from: "2026-11-20", to: "2026-11-26" }, NOW), null);
  assert.equal(exportRangeError({ from: "2026-11-26", to: "2026-11-26" }, NOW), null);
  assert.equal(exportRangeError({ from: "", to: "2026-11-26" }, NOW), "Choose the first and the last day.");
  assert.equal(exportRangeError({ from: "2026-11-26", to: "2026-11-25" }, NOW), "The first day is after the last day.");
  assert.equal(exportRangeError({ from: "2026-11-26", to: "2026-11-27" }, NOW), "The last day is in the future.");
  assert.equal(
    exportRangeError({ from: "2026-11-19", to: "2026-11-26" }, NOW),
    "Captures are kept for 7 days. Choose days from 20/11 on."
  );
});

test("the closing line says what was downloaded", () => {
  assert.equal(exportDoneText(9819, { from: "2026-11-24", to: "2026-11-26" }), "Downloaded 9,819 rows for 24/11 to 26/11.");
  assert.equal(exportDoneText(1, { from: "2026-11-26", to: "2026-11-26" }), "Downloaded 1 row for 26/11.");
  assert.equal(
    exportDoneText(0, { from: "2026-11-26", to: "2026-11-26" }),
    "No captures on 26/11: the file has only the header row."
  );
  assert.equal(
    exportDoneText(0, { from: "2026-11-24", to: "2026-11-26" }),
    "No captures from 24/11 to 26/11: the file has only the header row."
  );
});
```

- [ ] **Step 2: Chạy, phải fail**

Run: `cd frontend && npm test`
Expected: FAIL, không tìm thấy `./export-ui.ts`.

- [ ] **Step 3: Viết `frontend/lib/export-ui.ts` cho test pass**

- [ ] **Step 4: Chạy, phải pass**

Run: `cd frontend && npm test`
Expected: PASS.

- [ ] **Step 5: `frontend/lib/api.ts`: thêm `ApiExportLink` và `exportCsvLink`, xoá hai hàm export cũ**

- [ ] **Step 6: Viết `frontend/components/common/ExportCsvButton.tsx`**

Hành vi:
- Bấm nút mở một hộp nhỏ ngay dưới nút: hai ô `<input type="date">` nhãn "From" và "To" (`min` =
  `earliestExportDay`, `max` = `ictDay`, giá trị đầu = `defaultExportRange`), dòng chú thích "Times are in UTC+7.
  Captures are kept for 7 days.", nút "Download". Bấm ra ngoài hoặc nhấn Esc thì đóng.
- `exportRangeError` khác null: hiện câu đó (`role="alert"`), nút "Download" bị khoá.
- Đang chờ: nút "Download" bị khoá, ghi "Preparing the file…" kèm vòng xoay.
- Xong: tải file bằng một thẻ `<a href={url}>` tạm rồi `.click()`; hiện `exportDoneText` (`role="status"`).
- Lỗi: hiện "The file could not be prepared. Try again, or choose fewer days." (`role="alert"`).
- Thuộc tính để kiểm bằng trình duyệt: nút mở `data-export-open={kind}`, hộp `data-export-panel`, nút tải
  `data-export-download`, dòng kết quả `data-export-result="done" | "error"`.

- [ ] **Step 7: Dùng nút mới ở hai trang**

- `CategoryProductsView.tsx`: nút "Export CV Output" thành `<ExportCsvButton kind="cv-output" label="Export CV
  Output" … />` giữ kiểu viền hiện có; xoá `handleExportCsv` và import `Download` nếu không còn dùng. (Lời gọi
  `handleExportCsv([item])` của menu dòng được gỡ ở Task 5; trong task này thay tạm bằng hàm rỗng để build qua.)
- `ReportsDashboard.tsx`: nút "Download" thành `<ExportCsvButton kind="capture-log" label="Download capture log" …
  />` giữ kiểu chữ hiện có; xoá `handleDownloadCsv` (kể cả đoạn lặng lẽ tải file tóm tắt khi lỗi).

- [ ] **Step 8: Build, lint file đã sửa, commit**

Run: `cd frontend && npm test && npm run build && npx eslint lib/export-ui.ts components/common/ExportCsvButton.tsx`
Expected: test PASS, build xong, eslint không báo lỗi.

```bash
git add frontend/lib/export-ui.ts frontend/lib/export-ui.test.ts frontend/lib/api.ts frontend/components/common/ExportCsvButton.tsx frontend/components/category/CategoryProductsView.tsx frontend/components/reports/ReportsDashboard.tsx
git commit -m "Website: one export button with a date range and a visible wait, on Category and Dashboard"
```

---

### Task 3: Vào thẳng Dashboard; gỡ Home; chưa đăng nhập thì về trang đăng nhập

**Files:**
- Create: `frontend/lib/shell-ui.ts`, `frontend/lib/shell-ui.test.ts`
- Modify: `frontend/components/auth/LoginView.tsx` (bốn chỗ `router.push("/category")`, liên kết "Back to
  Workspace"), `frontend/app/(dashboard)/page.tsx`, `frontend/components/layout/DashboardShell.tsx`,
  `frontend/components/layout/Sidebar.tsx` (mục "Home"), `frontend/lib/api.ts` (`searchCatalog`)
- Delete: `frontend/components/home/HomePageView.tsx`, `frontend/lib/home-ui.ts`

**Interfaces:**
- Produces (`frontend/lib/shell-ui.ts`):

```ts
export const AFTER_SIGN_IN = "/dashboard";
export type ShellState = "loading" | "to-login" | "waiting" | "ready";
export function shellState(a: { isLoading: boolean; isAuthenticated: boolean; isApproved: boolean }): ShellState;
export const WAITING_TEXT = "Your account is waiting for approval. An administrator has to approve it before shelf data appears.";
```

- [ ] **Step 1: Viết test `frontend/lib/shell-ui.test.ts`**

```ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { AFTER_SIGN_IN, shellState } from "./shell-ui.ts";

test("what the page frame shows", () => {
  assert.equal(AFTER_SIGN_IN, "/dashboard");
  assert.equal(shellState({ isLoading: true, isAuthenticated: false, isApproved: false }), "loading"); // never redirect while the session is still being read
  assert.equal(shellState({ isLoading: false, isAuthenticated: false, isApproved: false }), "to-login");
  assert.equal(shellState({ isLoading: false, isAuthenticated: true, isApproved: false }), "waiting"); // just registered: no group yet
  assert.equal(shellState({ isLoading: false, isAuthenticated: true, isApproved: true }), "ready");
});
```

- [ ] **Step 2: Chạy, phải fail** (`cd frontend && npm test`: không tìm thấy `./shell-ui.ts`)

- [ ] **Step 3: Viết `frontend/lib/shell-ui.ts`; chạy lại, phải pass**

- [ ] **Step 4: Nối vào giao diện**

- `LoginView.tsx`: bốn chỗ thành `router.push(AFTER_SIGN_IN)`; gỡ khối liên kết "Back to Workspace".
- `app/(dashboard)/page.tsx`: trả `<ReportsDashboard />`.
- `DashboardShell.tsx`: `to-login` thì `router.replace("/login")` trong một effect và không vẽ trang con; dải xám
  "Not signed in…" bị gỡ. `waiting` thì dải cam ghi `Signed in as <email>. ` + `WAITING_TEXT`. `loading` và `ready`
  vẽ như hiện nay.
- `Sidebar.tsx`: gỡ mục `home` khỏi `NavItemId` và `PRIMARY_NAV_ITEMS`.
- Xoá hai file Home; gỡ `searchCatalog` khỏi `api.ts`.

- [ ] **Step 5: Build, commit**

Run: `cd frontend && npm test && npm run build`
Expected: PASS; build liệt kê `/`, `/dashboard`, `/category`, `/model`, `/settings`, `/login`, `/register`.

```bash
git add -A frontend/lib/shell-ui.ts frontend/lib/shell-ui.test.ts frontend/lib/home-ui.ts frontend/lib/api.ts frontend/components/home frontend/components/auth/LoginView.tsx "frontend/app/(dashboard)/page.tsx" frontend/components/layout/DashboardShell.tsx frontend/components/layout/Sidebar.tsx
git commit -m "Website: sign-in lands on the Dashboard, the Home page is gone, signed-out pages go to the login page"
```

---

### Task 4: Thanh bên: tự thu gọn trên màn hình hẹp, gỡ Quick search

**Files:**
- Create: `frontend/lib/sidebar-ui.ts`, `frontend/lib/sidebar-ui.test.ts`
- Modify: `frontend/components/layout/Sidebar.tsx`, `frontend/components/layout/DashboardShell.tsx`
  (`SidebarSearchProvider`), `frontend/components/category/CategoryProductsView.tsx` (`sidebarSearch`)
- Delete: `frontend/components/layout/SidebarContext.tsx`

**Interfaces:**
- Produces (`frontend/lib/sidebar-ui.ts`):

```ts
export const NARROW_QUERY = "(max-width: 767px)";
/** choice: what the user last pressed (true = collapsed), null until they press. */
export function isCollapsed(choice: boolean | null, narrow: boolean): boolean;
/** The Dashboard item is also the current page on "/". */
export function isNavActive(href: string, pathname: string): boolean;
```

- [ ] **Step 1: Viết test `frontend/lib/sidebar-ui.test.ts`**

```ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { isCollapsed, isNavActive } from "./sidebar-ui.ts";

test("a narrow screen starts collapsed, and the user's own choice wins", () => {
  assert.equal(isCollapsed(null, true), true);
  assert.equal(isCollapsed(null, false), false);
  assert.equal(isCollapsed(false, true), false); // opened by hand on a phone
  assert.equal(isCollapsed(false, false), false); // then turned to landscape: still open
  assert.equal(isCollapsed(true, false), true); // collapsed by hand on a desktop
});

test("the current page", () => {
  assert.equal(isNavActive("/dashboard", "/"), true);
  assert.equal(isNavActive("/dashboard", "/dashboard/"), true);
  assert.equal(isNavActive("/category", "/"), false);
  assert.equal(isNavActive("/settings", "/settings/"), true);
  assert.equal(isNavActive("/model", "/model"), true);
  assert.equal(isNavActive("/model", "/models/"), false);
});
```

- [ ] **Step 2: Chạy, phải fail; viết `frontend/lib/sidebar-ui.ts`; chạy lại, phải pass**

- [ ] **Step 3: `Sidebar.tsx`**

- `narrow` đọc từ `window.matchMedia(NARROW_QUERY)` bằng `useSyncExternalStore` (ảnh chụp phía server: `false`);
  `choice` là `useState<boolean | null>(null)`; `collapsed = isCollapsed(choice, narrow)`; nút thu gọn đặt
  `choice = !collapsed`.
- Gỡ cả khối "Quick Search Bar", `handleSearchBoxClick`, `searchInputRef`, `useSidebarSearch`, import `Search`.
- Mục đang chọn dùng `isNavActive`.
- Dòng "Pending role" trong menu tài khoản thành "Waiting for approval".

- [ ] **Step 4: Gỡ `SidebarContext.tsx`, `SidebarSearchProvider` trong `DashboardShell.tsx`, và `sidebarSearch`
  trong `CategoryProductsView.tsx` (ô tìm của trang chỉ còn `localSearch`)**

- [ ] **Step 5: Build, commit**

Run: `cd frontend && npm test && npm run build && npx eslint components/layout/Sidebar.tsx lib/sidebar-ui.ts`
Expected: PASS, build xong, không lỗi lint.

```bash
git add -A frontend/lib/sidebar-ui.ts frontend/lib/sidebar-ui.test.ts frontend/components/layout frontend/components/category/CategoryProductsView.tsx
git commit -m "Sidebar: starts collapsed on a narrow screen; the Quick search box is gone"
```

---

### Task 5: Category: việc của team chỉ hiện cho team, gỡ ô chọn và menu dòng

**Files:**
- Create: `frontend/lib/import-parse.ts`, `frontend/lib/import-parse.test.ts`
- Modify: `frontend/lib/products-ui.ts`, `frontend/lib/products-ui.test.ts`, `frontend/lib/product-groups.ts`,
  `frontend/lib/product-groups.test.ts`, `frontend/lib/review-queue.test.ts` (giá trị `status`),
  `frontend/components/category/CategoryProductsView.tsx`, `ProductRow.tsx`, `ProductGroupRow.tsx`,
  `ProductDetailsModal.tsx`, `ReviewQueue.tsx`, `frontend/components/settings/SettingsView.tsx`

**Interfaces:**
- Produces (`frontend/lib/products-ui.ts`):

```ts
export type ProductStatus = "Not flagged" | "Needs Review" | "Low Confidence";   // was "Validated" | …
export const STATUS_FILTER_OPTIONS: StatusFilterOption[];                         // "All", "Not flagged", "Needs Review", "Low Confidence"
export const NO_BARCODE = "No barcode yet";
export interface CategoryColumns { skuCode: boolean; confidence: boolean; stores: boolean }
export function categoryColumns(canReview: boolean, storeCount: number): CategoryColumns;
export function showStoreFilter(storeCount: number): boolean;
export function sortOptions(canReview: boolean): SortOption[];                    // viewers: no "Confidence (high → low)"
```

- Produces (`frontend/lib/import-parse.ts`):
  `parseImportFile(fileName: string, text: string): Record<string, unknown>[]`. `.json`: một mảng, hoặc một object
  có `items` là mảng; thứ khác thì `[]`. File khác: CSV, dòng đầu là tiêu đề, bỏ BOM, bỏ dấu `"` bao quanh, ô rỗng
  không thành khoá, dòng trống bị bỏ.
- `ProductRow` props: `{ item, nested?, columns: CategoryColumns, onOpenDetails }`. `ProductGroupRow` props:
  `{ group, expanded, columns: CategoryColumns, onToggleExpand }`. `ProductDetailsModal` thêm `canReview: boolean`.
- `groupSelection` bị xoá khỏi `product-groups.ts`.

- [ ] **Step 1: Viết test**

`frontend/lib/import-parse.test.ts`:

```ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { parseImportFile } from "./import-parse.ts";

test("JSON: a list, or an object with items", () => {
  assert.deepEqual(parseImportFile("a.json", '[{"sku_id":"A"}]'), [{ sku_id: "A" }]);
  assert.deepEqual(parseImportFile("A.JSON", '{"items":[{"sku_id":"A"}]}'), [{ sku_id: "A" }]);
  assert.deepEqual(parseImportFile("a.json", '{"sku_id":"A"}'), []);
});

test("CSV: header row, BOM, quotes, CRLF, empty cells", () => {
  const text = '﻿"sku_id","brand","barcode"\r\n"A","TH",""\r\n\r\nB,Slide,893\r\n';
  assert.deepEqual(parseImportFile("skus.csv", text), [
    { sku_id: "A", brand: "TH" },
    { sku_id: "B", brand: "Slide", barcode: "893" },
  ]);
});

test("nothing to import", () => {
  assert.deepEqual(parseImportFile("skus.csv", ""), []);
  assert.deepEqual(parseImportFile("skus.csv", "sku_id,brand\n"), []);
});
```

Trong `frontend/lib/products-ui.test.ts`, đổi hai dòng `auditStatusText("Validated", …)` thành `"Not flagged"` và
thêm:

```ts
test("what each account sees on Category", () => {
  assert.deepEqual(categoryColumns(false, 1), { skuCode: false, confidence: false, stores: false });
  assert.deepEqual(categoryColumns(true, 1), { skuCode: true, confidence: true, stores: false });
  assert.deepEqual(categoryColumns(false, 3), { skuCode: false, confidence: false, stores: true });
  assert.equal(showStoreFilter(0), false);
  assert.equal(showStoreFilter(1), false);
  assert.equal(showStoreFilter(2), true);
  assert.deepEqual(sortOptions(false), ["On-shelf stock (high → low)", "On-shelf stock (low → high)", "Name (A → Z)"]);
  assert.equal(sortOptions(true).includes("Confidence (high → low)"), true);
  assert.deepEqual(STATUS_FILTER_OPTIONS, ["All", "Not flagged", "Needs Review", "Low Confidence"]);
});
```

Trong `frontend/lib/product-groups.test.ts`: xoá test của `groupSelection` và import của nó; `status: "Validated"`
thành `"Not flagged"` (cả ở `review-queue.test.ts`).

- [ ] **Step 2: Chạy, phải fail; sửa `products-ui.ts`, `product-groups.ts`, viết `import-parse.ts`; chạy lại, phải
  pass**

- [ ] **Step 3: `CategoryProductsView.tsx`**

- `canReview = hasGroup("field_team", "team_admin")`; `columns = categoryColumns(canReview, liveStores?.length ?? 0)`.
- `loadLiveData`: chỉ gọi `api.getReviewQueue()` khi `canReview`; người thường thì `liveQueue` giữ `null`.
- `ReviewBanner` và `ReviewQueueDialog` chỉ vẽ khi `canReview`.
- Thanh công cụ: gỡ nút "Import SKU Master" và cả hộp thoại import; bộ lọc "Store:" chỉ khi
  `showStoreFilter(…)`; "Status:" chỉ khi `canReview`; "Sort:" dùng `sortOptions(canReview)`. Ô tìm ghi "Search by
  name" cho người thường, "Search name, SKU code or barcode" cho team.
- Bảng: gỡ cột ô chọn (tiêu đề, `selectedIds`, `toggleSelectAll`, `toggleSelectRow`, `toggleGroupSelection`); gỡ
  menu dòng (`openRowMenuId`, `rowMenuRef`, effect của nó); tiêu đề SKU CODE, CONFIDENCE, AVAIL IN STORES theo
  `columns`; `min-w` của bảng là tổng các cột cố định đang hiện cộng 240.
- Nhóm mở sẵn: đổi `expandedKeys` thành `collapsedKeys` (rỗng lúc đầu); "Collapse all / Expand all" giữ nguyên chữ.
- `statusOf` trả "Not flagged"; `barcode: p.barcode || NO_BARCODE`; `reviewed()` đặt `status: "Not flagged"`.
- `ProductDetailsModal` nhận `canReview`.

- [ ] **Step 4: `ProductRow.tsx`, `ProductGroupRow.tsx`, `ProductDetailsModal.tsx`, `ReviewQueue.tsx`**

- `ProductRow`, `ProductGroupRow`: gỡ ô chọn và menu "..."; các ô SKU CODE, CONFIDENCE, AVAIL IN STORES theo
  `columns`. Cột ACTIONS còn nút "View" (rộng 64 px).
- `ProductDetailsModal`: khối "Human Audit & Correction" và nút "Save Correction" chỉ khi `canReview`; gỡ dòng chân
  "Mapped 1:1 to Datagent 16-column CV Output & corrections schema."
- `ReviewQueue`: nhãn trạng thái chỉ còn tiếng Anh ("Waiting", "Confirmed", "Corrected").

- [ ] **Step 5: `SettingsView.tsx`: nút "Import SKU Master" cạnh "Import Store List"**

Chỉ admin thấy. Chọn file (`accept=".json,.csv"`) → `parseImportFile`. Danh sách rỗng: thông báo "The file has no
rows." và không gọi API. Có dòng: `api.importSkuMaster(items)` rồi thông báo `Imported N products into the SKU
master.` "Import Store List" cũng đọc file bằng `parseImportFile` và báo `Imported N stores.`

- [ ] **Step 6: Build, lint, commit**

Run: `cd frontend && npm test && npm run build && npx eslint components/category components/settings/SettingsView.tsx lib/import-parse.ts lib/products-ui.ts`
Expected: PASS, build xong, không thêm lỗi lint.

```bash
git add -A frontend/lib frontend/components/category frontend/components/settings/SettingsView.tsx
git commit -m "Category: team tools show only to the team; the unused checkboxes and row menu are gone"
```

---

### Task 6: Gỡ những thứ không có tác dụng ở đăng nhập, đăng ký và Settings

**Files:**
- Modify: `frontend/components/auth/LoginView.tsx`, `RegisterView.tsx`, `AuthShell.tsx`,
  `frontend/components/settings/SettingsView.tsx`, `frontend/lib/api.ts` (`updateSettings`)

Task này không có logic thuần mới nên không có test đơn vị; việc kiểm là build và bước trình duyệt ở Task 8.

- [ ] **Step 1: `LoginView.tsx`**

Gỡ hai nút "Continue with Google", "Continue with SSO", dòng "or", `GoogleIcon`, import `KeyRound`; gỡ ô "Remember
this device" và state `rememberDevice` ("Forgot your password?" nằm sát phải). Bước nhập mã: giữ một dòng "Enter the
6-digit code from your authenticator app." trong form và không đặt `infoMsg` cùng ý nữa (hai chỗ). Câu ở bước quên
mật khẩu: "We'll email you a code to reset your password."

- [ ] **Step 2: `RegisterView.tsx`**

Gỡ hai nút "Sign up with Google", "Sign up with SSO", dòng "or" nếu có, `GoogleIcon`, import `KeyRound`. Ba câu:

| Chỗ | Chữ mới |
| --- | --- |
| dòng dưới tiêu đề khi `step === "DONE"` | `Your email is verified. An administrator has to approve the account before it can see shelf data.` |
| đoạn trên nút "Sign up" | `A new account needs an administrator's approval before it can see shelf data.` |
| hộp xanh ở bước DONE | `Email verified for <email>. You can sign in now; shelf data appears once an administrator approves the account.` |

- [ ] **Step 3: `AuthShell.tsx`**

Gỡ nút chọn ngôn ngữ (state, effect, `LANGUAGES`, import `Check`, `ChevronDown`, `Globe`) và bốn liên kết chân
trang; chân trang còn dòng bản quyền.

- [ ] **Step 4: `SettingsView.tsx` và `api.ts`**

Gỡ khối "Personal Display Preferences", nút "Save Preferences", `DATE_FORMATS`, `LANDING_PAGES`, `UserPreferences`,
`DEFAULT_PREFS`, `savedPrefs`, `draftPrefs`, `hasUnsavedChanges`, `handleSave`, `saving`; gỡ `updateSettings` khỏi
`api.ts`.

- [ ] **Step 5: Build, commit**

Run: `cd frontend && npm test && npm run build`
Expected: PASS, build xong.

```bash
git add frontend/components/auth frontend/components/settings/SettingsView.tsx frontend/lib/api.ts
git commit -m "Website: controls that did nothing are gone (Google and SSO buttons, language, footer links, two preferences)"
```

---

### Task 7: Chữ dễ hiểu, và ẩn bộ lọc Store khi chỉ có một tiệm

**Files:**
- Modify: `frontend/lib/reliability-ui.ts` (+ test), `frontend/lib/shelf-ui.ts` (+ test), `frontend/lib/health-ui.ts`
  (+ test nếu có dòng khẳng định câu này), `frontend/components/reports/ReportsDashboard.tsx`, `FilterBar.tsx`,
  `frontend/components/category/CategoryProductsView.tsx`, `frontend/components/settings/SettingsView.tsx`

**Interfaces:**
- Consumes: `showStoreFilter` (Task 5).
- `FilterBar` thêm prop `showStore: boolean`; khi `false` lưới còn hai cột.

- [ ] **Step 1: Đổi các khẳng định trong test trước**

| Test | Giá trị mới |
| --- | --- |
| `reliability-ui.test.ts`: `badgeLabel("insufficient")` | `"Not rated"` |
| `reliability-ui.test.ts`: `reliabilityText` khi `insufficient` | `"Not rated yet: too few checked frames (8 cans, 3 frames)"`, `"Not rated yet: too few checked frames (0 cans, 0 frames)"` |
| `shelf-ui.test.ts`: `alertAccuracyText(blocked, true)` | `"Too few confirmed alerts to rate them (3 so far) · confirm 7 more alerts to see how often they are right"` |
| `shelf-ui.test.ts`: `alertAccuracyText(blocked, false)` và không tham số | `"Too few confirmed alerts to rate them (3 so far)"` |
| `shelf-ui.test.ts`: trường hợp `n = 9`, 2 unsure | `"Too few confirmed alerts to rate them (9 so far) · confirm 1 more alert to see how often they are right (2 unsure)"` |

- [ ] **Step 2: Chạy, phải fail; sửa `reliability-ui.ts`, `shelf-ui.ts`; trong `health-ui.ts` đổi "review queue on
  Products" thành "review queue on Category"; chạy lại, phải pass**

- [ ] **Step 3: Câu chữ trong component**

| File | Chữ cũ | Chữ mới |
| --- | --- | --- |
| `ReportsDashboard.tsx` | `Live AWS data, N captures synced. Shelf numbers are worked out every 5 minutes from the store's checks in opening hours.` | `Shelf numbers are worked out every 5 minutes from the store's checks in opening hours.` |
| `CategoryProductsView.tsx` | `Live AWS Singapore backend · N SKUs synced (UTC+7)` | `N products · times are in UTC+7` |
| `CategoryProductsView.tsx` | `Sign in with an approved account to load live products (UTC+7)` và câu tương tự trong bảng | `Products appear once your account is approved.` |
| `CategoryProductsView.tsx` | `Saved correction to AWS DynamoDB (corrections)` | `Saved the correction.` |
| `CategoryProductsView.tsx` | `Only field_team or team_admin can submit corrections.` / `…can confirm review items.` | `Your account cannot save corrections.` / `Your account cannot confirm readings.` |
| `SettingsView.tsx` | dòng dưới tiêu đề (cả hai nhánh) | `Your account, the stores and the shelf plan.` |
| `SettingsView.tsx` | `Loading settings from AWS...` | `Loading settings…` |
| `SettingsView.tsx` | `Account & Cognito Role` + dòng mô tả `Managed centrally via Amazon Cognito…` | `Account`, bỏ dòng mô tả |
| `SettingsView.tsx` | `Cognito Email`, `Assigned Cognito Groups`, `Pending team_admin assignment` | `Email`, `Groups`, `Waiting for approval` |
| `SettingsView.tsx` | `0.70 (MILK_FLAG_THRESHOLD)` và đoạn `Rows below 0.70 raw average confidence or with sku_id = NULL…` | `0.70` và `A reading with confidence under 0.70, or one that matched no SKU, is flagged for review.` |
| `SettingsView.tsx` | `Standard ISO 8601 UTC+7 across all captures and CSV exports (Data Dictionary).` | `Every time on this site and in the CSV files is in UTC+7.` |
| `SettingsView.tsx` | `Loaded from store_list; team_admin can import updated store JSON files.` | `The stores this site monitors.` |
| `SettingsView.tsx` | `Only team_admin can import Store List.` | `Your account cannot import the store list.` |

- [ ] **Step 4: `FilterBar.tsx` nhận `showStore`; `ReportsDashboard.tsx` truyền `showStoreFilter(stores?.length ?? 0)`**

- [ ] **Step 5: Quét chữ kỹ thuật còn sót, build, commit**

Run: `cd frontend && npm test && npm run build`
Expected: PASS, build xong.

Run (từ gốc repo): `grep -rnE "AWS|Cognito|DynamoDB|MILK_FLAG_THRESHOLD|PENDING_ROLE|Chờ duyệt|Pending SKU|sku_id = NULL" frontend/components --include=*.tsx | grep -vE "^\S+:\s*[0-9]+:\s*(//|/\*|\*|import )|CognitoGroup|\{/\*"`
Expected: không còn dòng nào là chữ hiện lên màn hình (còn lại chỉ là tên kiểu, chú thích mã và khoá trạng thái
`"Chờ duyệt"` trong bảng `STATUS` của `ReviewQueue.tsx`).

```bash
git add frontend/lib frontend/components
git commit -m "Website: plain wording in place of infrastructure names; the Store filter hides when there is one store"
```

---

### Task 8: Kiểm bản build trên máy, rồi deploy khi hoang duyệt

**Files:**
- Create (scratchpad, không vào repo): `opt1_run.py`, `browser/opt1_check.cjs`

- [ ] **Step 1: Chạy toàn bộ test và build**

Run: `python -m pytest -q` rồi `cd frontend && npm test && npm run build`
Expected: không test nào fail; `frontend/out/` có `index.html`, `dashboard/`, `category/`, `model/`, `settings/`,
`login/`, `register/` và không có trang Home riêng.

- [ ] **Step 2: Kiểm bằng trình duyệt trên bản build, đọc API thật**

Phục vụ `frontend/out` ở `http://localhost:3000` (CORS của API cho phép origin này). Script điều khiển Edge bằng
`puppeteer-core@23.11.1`, đăng nhập bằng tài khoản thử lấy từ SSM (`/milk-demo/web/api-check-account` cho người
thường, `/milk-demo/web/model-check-account` cho team), **huỷ mọi request tới API có method khác `GET` và
`OPTIONS`**, và tự trả lời request `GET /exports/*.csv?…link=1` bằng một JSON mẫu (backend đang chạy chưa biết
`link`). Danh sách kiểm:

| # | Tài khoản | Điều phải đúng |
| --- | --- | --- |
| 1 | người thường | sau khi đăng nhập, đường dẫn là `/dashboard/` |
| 2 | người thường | thanh bên không có "Home", không có ô "Quick search" |
| 3 | người thường | Category: không có `[data-review-banner]`, "Import SKU Master", "Status:", tiêu đề SKU CODE / CONFIDENCE / AVAIL IN STORES, không có `[role=checkbox]`; có ít nhất một `[data-sku-row]` mà không phải bấm gì |
| 4 | người thường | thẻ sản phẩm: không có "Human Audit & Correction", không có "Save Correction" |
| 5 | người thường | Dashboard: bấm `[data-export-open="capture-log"]` hiện hai ô ngày; bấm tải hiện `[data-export-result="done"]`; đổi "To" thành ngày mai thì nút tải bị khoá và có câu "The last day is in the future." |
| 6 | người thường | bề ngang 390 px: thanh bên rộng 56 px lúc mở trang; nút `[data-export-open]` nằm trọn trong màn hình |
| 7 | chưa đăng nhập | mở `/category/` thì kết thúc ở `/login/`; trang đăng nhập không có "Google", "SSO", "Remember this device", "English", "Terms of Use" |
| 8 | team | Category: có `[data-review-banner]`, bộ lọc "Status:" có "Not flagged", có tiêu đề SKU CODE và CONFIDENCE |
| 9 | team | thẻ sản phẩm: có "Human Audit & Correction" và "Save Correction" (không bấm lưu) |
| 10 | team | Settings: có "Import SKU Master" và "Import Store List"; không có "Date Format", "Default Landing Page" |
| 11 | cả hai | chữ trên Dashboard, Category, Settings, login, register không khớp `/AWS|Cognito|DynamoDB|MILK_FLAG_THRESHOLD|PENDING_ROLE|Chờ duyệt/` |
| 12 | cả hai | `blocked` (các lệnh ghi bị huỷ) rỗng |

Expected: 12/12.

- [ ] **Step 3: DỪNG. Báo hoang kết quả và xin duyệt deploy**

- [ ] **Step 4 (sau khi hoang duyệt): deploy backend trước**

Đóng gói hai Lambda, đưa lên `s3://milk-development-754361433393/releases/backend/<sha>/`, tạo change set cho stack
`milk-backend-development` với template mới (`infra/backend.yaml`) và hai khoá mã mới, **không `--tags`**. Xem change
set: chỉ được có `Modify` cho hai Lambda, các tài nguyên đi theo mã như lần trước, và `AnalyticsBucket` (luật vòng
đời, không thay thế). Có dòng `Replacement: True` nào thì không chạy. Rồi execute.

Kiểm trên API thật bằng tài khoản người thường: `GET /exports/cv-output.csv?from=<hôm nay>&to=<hôm nay>&link=1` và
cùng lệnh với 7 ngày, cho cả `capture-log`: trả 200, ghi lại thời gian chạy và bộ nhớ từ log Lambda (phải dưới 20
giây và dưới 200 MB), tải thử đường dẫn và đếm dòng.

- [ ] **Step 5 (sau khi hoang duyệt): deploy website**

Nén nội dung `frontend/out/`, `aws amplify create-deployment --app-id d2k8euxy0yoiv8 --branch-name main`, đưa file
lên, `start-deployment` (chạy thành lệnh riêng), chờ `SUCCEED`. Chạy lại bảng kiểm ở Step 2 trên
`https://main.d2k8euxy0yoiv8.amplifyapp.com`, lần này không tự trả lời request export.

- [ ] **Step 6: Ghi lại**

Cập nhật memory (đợt 1 đã chạy thật, cách lùi: change set về `releases/backend/3978796/`, Amplify về bản build của
3508cc3). Push nhánh và mở PR khi hoang bảo.
