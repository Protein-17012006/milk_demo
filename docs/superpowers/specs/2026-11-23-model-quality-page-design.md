# Trang Model: chấm và theo dõi chất lượng model đếm

Ngày 2026-11-23 · hoang duyệt hướng trong chat ("ok chốt") · nối tiếp HOANG-P10 (website dùng số thật)

## Vì sao

- **hoang, chat 23/11:** *"thêm 1 trang để maintainance model performance và observe (trang này mục đích để
  đánh giá tổng quát model)"*.
- Kiểm 23/11 trên 199 lần đọc thật (12:42–12:58), cả 4 vị Slide đã bày trong tủ kính:
  - Model nhầm vị mà rất tự tin: 2 lon Nguyên bản bị gọi là Hot & Spicy trong 186 và 196/199 lần, độ tin
    cậy trung vị 0.92, nên không bị gắn cờ.
  - 81% lần đọc có khung trùng. Lỗi này đã sửa ở `a619a7b`, nhưng trước khi sửa không có chỗ nào cho thấy nó.
  - Sót lon bị che hoặc nằm trong tối.
  - Website chỉ cho thấy số đếm, không cho thấy số đó đúng hay sai.
- Datagent chấm Tech Partner (team mình) bằng **12 chỉ số ở sheet "Validation - Accuracy Report"** của Data
  Dictionary. Chỉ số nào cũng cần số đếm thật của người; hiện bảng corrections có 0 dòng.
- **hoang chọn (23/11):** số thật do team đếm trên ảnh, ngay trong website. Human Audit tại tiệm của field
  team Datagent để sau, dùng chung cách tính.

## Mục tiêu

- Thấy 12 chỉ số của Datagent cạnh mục tiêu pilot, tính từ các khung team đã đếm.
- Thấy model sai ở đâu: theo SKU, theo cặp nhầm lẫn (model nói X, thật là Y), theo ngày, theo phiên bản model.
- Theo dõi tự động 7 ngày gần nhất, không cần người đếm.
- Đếm một khung mất 1–2 phút.
- Bộ khung đã đếm được giữ lâu dài, để dùng lại khi fine-tune (phần Feedback Loop của Datagent).

## Không làm (bản này)

- Không nhập Human Audit của Datagent. Cách tính dưới đây dùng lại được khi làm việc đó.
- Không xuất dữ liệu huấn luyện (ví dụ định dạng YOLO) từ các khung đã đếm.
- Datagent không thấy trang này.
- Không đổi số trên Products, Reports hay CSV; ô "Top 50 SKU accuracy" trên Reports vẫn để "—".
- Không đổi cách worker đếm. Worker chỉ ghi thêm 2 trường (mục 1).
- Không đổi thời gian giữ capture (7 ngày) và ảnh liên tục trên hub (7 ngày).

## Không được xảy ra

- Không có số liệu giả. Chưa có khung đã đếm thì ô chỉ số hiện "—" kèm số khung (n = 0), không hiện 0% hay số mẫu.
- Không chọn khung theo kiểu "dễ". Khung chính thức mỗi giờ được chọn theo ít cờ nhất, nên sẽ làm chỉ số đẹp giả.
- Không đưa ảnh chưa làm mờ mặt vào bộ đếm. Chỉ chép ảnh hub đã lưu, mà hub chỉ lưu ảnh đã làm mờ.

## Phương án

**Nơi làm** (agent đề xuất; hoang "ok chốt"):
- **A. Trong website và backend B. Chọn phương án này.** Trang Next.js mới, thêm route vào Lambda API, thêm
  bảng DynamoDB, và gắn việc chọn khung vào lịch hằng giờ mà Lambda ingest đã có.
- B. CVAT hoặc Label Studio để đếm, website chỉ hiện chỉ số. Loại vì phải dựng và bảo vệ thêm máy chủ, người
  đếm đăng nhập riêng, và phải đồng bộ kết quả về.
- C. Dashboard hub trên EC2. Loại vì hub tắt lúc 23:00, không có nhóm Cognito, và P10 đã chốt phần cho client
  nằm ở backend B.

**Cách đếm** (hoang "ok chốt"):
- **Chấm từng khung model vẽ, rồi thêm điểm cho hàng bị sót. Chọn cách này.**
- Đã loại: chỉ nhập tổng theo vị. Cách đó không bắt được nhầm vị khi tổng trùng. Ví dụ ngày 23/11, model báo
  Hot = 2 và thật cũng có 2 lon Hot, nhưng 2 khung model gọi Hot thật ra là lon Nguyên bản.

**Chọn khung** (hoang "ok chốt"):
- **Mỗi giờ có capture, chọn ngẫu nhiên 1 khung cho mỗi camera. Chọn cách này.**
- Đã loại: dùng khung chính thức của giờ, vì nó thiên về khung ít cờ.

**Lưu ảnh** (hoang "ok chốt"):
- **Chép ảnh sang bucket analytics, không tự xoá. Chọn cách này.**
- Lưu ý: điều này khác quy tắc 90 ngày cho ảnh chính thức ngày 21/11. Quyết định mới hơn áp dụng cho ảnh đã đếm.

## Thiết kế

### 1. Worker ghi thêm 2 trường vào mỗi kết quả lưu

Code ở `server/milk/counter.py`, chỗ dựng `record` cho `/internal/persist`:

- **`model_version`** (chuỗi):
  - Lấy từ biến mới `MILK_MODEL_VERSION` trong `worker.env`.
  - Không đặt thì ghép `MILK_PIPELINE` với tên thư mục chứa trọng số Slide, ví dụ `long+slide:runs_v3`.
  - Bản đang chạy đặt `MILK_MODEL_VERSION=long-2026-10-13+slide-v3` (trọng số sữa ngày 13/10, Slide v3).
- **`detections`**: danh sách từng hộp `{sku_id, conf, box}`.
  - Giống mục `detections` trong `meta` mà worker đã gửi dashboard: `conf` là độ tin cậy của riêng hộp đó,
    `box` là x, y, w, h trên khung gốc.
  - Đây là một phần của NHAT-T003 (`unit_detail`). Validation Card chưa đọc trường này.
- Hub không cần sửa: `store.py` ghi nguyên `record` ra `results/*.json`.
- Ingest (`_normalize_record` và bảng captures):
  - Đọc thêm 2 trường. Bảng captures lưu `model_version` và `detections_json`.
  - Bản ghi cũ không có 2 trường: `model_version = "unknown"`, còn `detections` dựng lại từ `rows`
    (mỗi `bounding_box` là một hộp, `conf` lấy độ tin cậy của dòng).

### 2. Bảng mới

Cả hai bảng đều PAY_PER_REQUEST, có PITR và SSE như các bảng hiện có. Thêm ARN của cả hai vào statement
DynamoDB của `LambdaExecutionRole`. Thêm `AUDITS_TABLE` và `MODEL_HEALTH_TABLE` vào biến môi trường của cả hai Lambda.

**`milk-backend-<env>-audits`**: khoá `store_id` (HASH), `audit_id` (RANGE). Không TTL.

| Trường | Nội dung |
|---|---|
| `audit_id` | `AUD-<camera_id>-<YYYYMMDD>-<HH>` (giờ ICT của khung) |
| `camera_id`, `capture_id`, `capture_timestamp` | capture được chọn |
| `image_key` | `audits/frames/<camera_id>/<YYYY-MM-DD>/<image_filename>` trong bucket analytics |
| `model_version`, `pipeline` | từ capture |
| `status` | `pending`, `done` hoặc `skipped` |
| `sampled_at` | lúc chọn khung |
| `ai_boxes_json` | `[{box_id, sku_id, conf, box}]`. `box_id` đánh số 1..n. `sku_id` là nhãn model (`hot160`, `TMP-MLK-TH-01`), `null` nếu UNRECOGNIZED |
| `verdicts_json` | `[{box_id, verdict, true_sku_id}]`. `verdict` là `correct`, `wrong_sku` hoặc `not_product`. `true_sku_id` (nhãn model) chỉ có khi `wrong_sku` |
| `missed_json` | `[{sku_id, x, y}]`: mỗi điểm là 1 đơn vị hàng mà model không vẽ khung |
| `labeled_by`, `labeled_at` | email trong token và thời điểm lưu |
| `skip_reason` | khi `skipped`: `blurry`, `blocked`, `camera_moved` hoặc `other` kèm ghi chú |

**`milk-backend-<env>-model-health`**: khoá `camera_id` (HASH), `hour` (RANGE, `YYYYMMDD-HH`). TTL 90 ngày
(`expires_at`). Mỗi item là thống kê một giờ của một camera (mục 6).

Ảnh của bộ đếm: bucket analytics, prefix `audits/`. Bucket này không có lifecycle cho prefix đó, nên ảnh được
giữ mãi. Quyền Get/Put đã có trong role.

### 3. Chọn khung để đếm (Lambda ingest, lịch hằng giờ)

Việc này gắn vào lần chạy `select_hourly_official` sẵn có (EventBridge `rate(1 hour)`). Chạy riêng được bằng
`{"action": "sample_audits", "hour": "YYYYMMDD-HH"}` để thử và chạy bù.

0. **"Giờ trước"** là giờ tròn gần nhất đã trôi qua, tính theo giờ ICT. Lý do: `rate(1 hour)` không chạy đúng
   đầu giờ. Ví dụ lần chạy lúc 13:24 thì xét 12:00–12:59.
1. **Danh sách camera** lấy từ các giá trị `camera_id` khác nhau trong `latest_stock` (bảng nhỏ). Không quét bảng captures.
2. **Capture của giờ trước:** với mỗi camera, Query bảng captures theo `camera_id`, lọc `capture_id` bắt đầu
   bằng tiền tố của giờ đó, ví dụ `CAP-S01-20261123-13`. Lấy mã tiệm (`S01`) từ các `capture_id` đã có của camera.
3. **Chọn ngẫu nhiên** 1 capture trong những capture có `image_key`, theo phân phối đều. Giờ không có capture
   nào có ảnh thì bỏ qua.
4. **Chép ảnh** bằng `copy_object` từ bucket hub sang `audits/frames/...` trong bucket analytics.
5. **Ghi audit** `pending` bằng `put_item` có điều kiện `attribute_not_exists(audit_id)`. Chạy lại cùng giờ
   không tạo thêm audit.
6. **Lỗi** ở một camera thì ghi log và chạy tiếp camera khác. Lần chạy sau không tự chạy bù giờ bị lỡ, vì
   `sample_audits` chạy bù bằng tay được.

### 4. API mới (Lambda API)

Mọi route mới chỉ cho `team_admin` và `field_team`; `datagent` nhận 403. Dùng `_require_groups` như các route hiện có.
API Gateway không cần sửa: resource `{proxy+}` đã nhận mọi phương thức (ANY) qua bộ xác thực Cognito.

| Route | Việc |
|---|---|
| `GET /model/audits?status=pending&days=7` | Danh sách audit mới nhất trước, kèm số `pending`, `done`, `skipped` trong khoảng |
| `GET /model/audits/{audit_id}` | Chi tiết audit, link ảnh ký 15 phút (bucket analytics), `ai_boxes`, verdict và điểm sót nếu đã có, danh sách SKU để chọn vị |
| `PUT /model/audits/{audit_id}` | Lưu `verdicts` và `missed`, chuyển sang `done` (xem kiểm tra bên dưới) |
| `POST /model/audits/{audit_id}/skip` | `{reason, note}`, chuyển sang `skipped` |
| `GET /model/summary?days=7&model_version=` | Chỉ số, bảng theo SKU, ma trận nhầm lẫn, chuỗi theo ngày (mục 5) |
| `GET /model/health?days=7` | Thống kê theo giờ từ `model-health` (mục 6) |

Kiểm tra của `PUT`:
- Mọi `box_id` của model phải có đúng 1 verdict.
- `true_sku_id` và `sku_id` của điểm sót phải là nhãn model có trong `DEFAULT_ALIAS_MAP` (`backend/common.py`)
  hoặc trong cột `model_alias` của SKU Master. Sai thì trả 400.
- Hộp UNRECOGNIZED chỉ nhận verdict theo bảng ở mục 5.
- Lưu lại một audit `done` thì ghi đè, cập nhật `labeled_by` và `labeled_at`. Hai người lưu cùng lúc thì bản lưu sau thắng.

Danh sách SKU để chọn vị là các SKU trong SKU Master có `model_alias`. Mỗi SKU hiện tên chính thức, còn giá trị
gửi lên là nhãn model, để tính trùng với `ai_boxes`.

### 5. Cách tính

Đây là đề xuất của agent, dựa theo mô tả cột trong Data Dictionary. Ô công thức trong sheet hiện `#ERROR!` nên
không đọc được công thức gốc. Mọi phép tính làm trong Lambda API, chỉ trên các audit `done` trong khoảng ngày và
phiên bản model đã chọn.

**Nghĩa của verdict.** "SKU của danh mục" là một nhãn trong bảng alias. Hàng khác của tiệm (kẹo, nước...) không
phải SKU của danh mục.

| Verdict | Hộp model gọi tên một SKU | Hộp UNRECOGNIZED |
|---|---|---|
| `correct` | đúng một đơn vị của SKU đó | một món hàng không có trong danh mục, nên model không gọi tên là đúng |
| `wrong_sku` + `true_sku_id` | một đơn vị của SKU khác trong danh mục | một đơn vị của SKU trong danh mục mà model không gọi được tên |
| `not_product` | không phải SKU nào của danh mục (hàng khác, nền, kệ, tay, bảng giá) | không phải món hàng nào cả |

**Mỗi audit (một khung):**
- Một hộp của model là một lần phát hiện.
- **Số thật của vị s:** số hộp `correct` có nhãn s, cộng số hộp `wrong_sku` có `true_sku_id` = s, cộng số điểm
  sót của s. Hộp UNRECOGNIZED `correct` không tính vào vị nào.
- **Số model của vị s:** số hộp có nhãn s.
- **Hộp UNRECOGNIZED không có dòng so sánh**, vì hàng ngoài danh mục không có số thật. Nó vẫn được tính ở ma trận
  nhầm lẫn, ở chỉ số #12 và ở chỉ số #1–2 (khi thật là một SKU). Đây là quyết định lúc lập kế hoạch ngày 23/11.
- **Dòng so sánh** (một dòng cho mỗi cặp khung × SKU của danh mục, với mọi SKU có số model > 0 hoặc số thật > 0), theo phần A của Accuracy Report:
  - `count_difference` = số model − số thật.
  - `count_accuracy_pct` = max(0, 1 − |chênh| / số thật) khi số thật > 0; bằng 0 khi số thật = 0.
- **Loại lỗi `discrepancy_category`**, xét theo thứ tự, gặp điều kiện nào trước thì lấy loại đó:
  1. Missed SKU: số model = 0, số thật > 0.
  2. False Detection: số thật = 0 và mọi hộp model của vị này là `not_product`.
  3. Wrong SKU: có ít nhất một hộp model của vị này là `wrong_sku`.
  4. Theo |chênh|: 0 là Exact Match, 1–2 là Minor, từ 3 trở lên là Major.
  - Với trường hợp ngày 23/11: dòng Hot có số model 2, số thật 2 nhưng cả 2 hộp sai vị, nên ra **Wrong SKU**, không ra Exact Match.

**12 chỉ số**, theo phần B của Accuracy Report. Mỗi ô hiện giá trị, mục tiêu, đạt hay không, và n.

| # | Chỉ số | Cách tính | Mục tiêu |
|---|---|---|---|
| 1 | `sku_identification_accuracy` (top 50 SKU) | trong các hộp mà thật là một SKU của danh mục (hộp có tên mà `correct`, cộng mọi hộp `wrong_sku`, kể cả hộp UNRECOGNIZED), tỷ lệ hộp có tên mà `correct`. Chỉ xét SKU thật thuộc top 50 theo tổng số thật trong khoảng. Ít hơn 50 SKU thì ghi "top 50 = cả N SKU" | ≥ 80% |
| 2 | `overall_identification_accuracy` | như #1, mọi SKU | ≥ 60% |
| 3 | `unit_count_mae` | trung bình \|chênh\| trên các dòng so sánh | ≤ 2 |
| 4 | `unit_count_accuracy_avg` | trung bình `count_accuracy_pct` trên dòng có số thật > 0 | ≥ 75% |
| 5 | `exact_match_rate` | dòng Exact Match ÷ mọi dòng | ≥ 40% |
| 6 | `minor_error_rate` | dòng Minor ÷ mọi dòng; hiện thêm Exact + Minor | Exact + Minor ≥ 75% |
| 7 | `missed_sku_rate` | dòng Missed SKU ÷ dòng có số thật > 0 | ≤ 20% |
| 8 | `false_detection_rate` | hộp `not_product` ÷ mọi hộp | ≤ 10% |
| 9 | `avg_confidence_correct` | trung bình `conf` của hộp `correct` | > 0.8 |
| 10 | `avg_confidence_incorrect` | trung bình `conf` của hộp `wrong_sku` hoặc `not_product` | < 0.5 |
| 11 | `avg_processing_time_ms` | trung bình `processing_time_ms` của mọi capture trong khoảng (từ `model-health`) | ≤ 30 000 ms |
| 12 | `unrecognized_product_rate` | hộp UNRECOGNIZED ÷ mọi hộp | ≤ 20% |

**Bảng theo SKU**, mỗi SKU có trong số thật hoặc số model là một dòng:
- Tổng số model và tổng số thật.
- Tỷ lệ nhận đúng của các hộp model mang nhãn đó.
- Số đơn vị bị sót.
- "Hay bị nhầm thành": `true_sku_id` gặp nhiều nhất trong các hộp `wrong_sku` của nó, kèm số lần.

**Ma trận nhầm lẫn:**
- Hàng là nhãn model, có thêm UNRECOGNIZED.
- Cột là vị thật, có thêm "không phải hàng".
- Thêm một hàng "bỏ sót" cho điểm sót theo vị thật.

**Theo ngày** (ngày ICT của khung): số audit `done`, chỉ số #2, #3 và Exact + Minor.

### 6. Theo dõi tự động

Cùng lịch hằng giờ, Lambda ingest tính thống kê của giờ trước cho mỗi camera, lấy từ capture của giờ đó (cùng
Query với mục 3), rồi ghi 1 item vào `model-health`:
- Số capture, và các `model_version` gặp trong giờ.
- Độ tin cậy: trung vị và trung bình độ tin cậy từng hộp. Bản ghi cũ dùng độ tin cậy của dòng.
- Tỷ lệ dòng bị gắn cờ, và tỷ lệ hộp UNRECOGNIZED.
- Số đơn vị mỗi capture: trung vị, nhỏ nhất, lớn nhất.
- Mức số nhảy: trung bình \|Δ\| số đơn vị giữa hai capture liền nhau, cộng qua các vị.
- Số cặp khung trùng (IoU ≥ 0.5 trong một capture). Sau `a619a7b` phải bằng 0.
- `processing_time_ms` trung vị và p90; `latency_ms` trung vị.
- Ngay sau khi triển khai, chạy bù 7 ngày gần nhất bằng `{"action": "backfill_model_health"}` (capture chỉ giữ 7 ngày).

### 7. Trang web `/model`

Nhãn tiếng Anh như phần còn lại của website.

- **Thanh bên:** mục "Model" chỉ hiện với `team_admin` và `field_team`. Nhóm khác vào thẳng `/model` thì thấy
  báo không có quyền.
- **Đầu trang:** chọn phiên bản model (mặc định là bản mới nhất có dữ liệu, có "All versions"), khoảng ngày
  (7 ngày, 30 ngày, tất cả), và nút "Label frames (n pending)".
- **Khối Datagent KPIs:** 12 ô. Chưa có audit `done` thì mọi ô là "—" và có dòng "No labelled frames yet".
- **Khối Per SKU:** bảng ở mục 5.
- **Khối Confusion:** ma trận, ô đậm theo số lần.
- **Khối By day:** biểu đồ đường bằng recharts (đã có trong dependencies).
- **Khối Live health (7 days):**
  - Biểu đồ theo giờ: độ tin cậy, % gắn cờ, mức số nhảy, ms/khung, số capture.
  - Thêm dòng "duplicate boxes" (phải bằng 0).
- **Màn hình đếm**, mở từ nút Label, hiện từng audit `pending` cũ nhất trước:
  - Ảnh và các hộp vẽ bằng SVG phủ lên ảnh, như `FrameViewer.tsx`. Dùng lại `lib/frame-geometry.ts`; có
    phóng to và kéo.
  - **Bấm vào hộp** để xoay vòng trạng thái: chưa chấm (xám) → `correct` (xanh) → `wrong_sku` (đỏ, mở danh sách
    chọn vị đúng) → `not_product` (tím) → chưa chấm.
  - **Bấm chỗ trống:** thêm một điểm sót và chọn vị. Bấm vào điểm sót để xoá.
  - **Bảng bên cạnh:** theo từng vị, số model và số thật cập nhật ngay khi chấm.
  - **Nút:** Save (chỉ bật khi mọi hộp đã chấm), Skip (chọn lý do), Next.
- **Trang tĩnh** (`output: "export"`): không dùng route động. Dùng query param `?audit=<id>` hoặc modal.

### 8. Kiểm thử

- **Worker** (pytest): `record` lưu có `model_version`; `detections` có đủ `sku_id`, `conf` và `box`.
- **Backend** (pytest + moto, cùng file test integration):
  - Chọn khung: mỗi camera-giờ có capture tạo đúng 1 audit `pending` và ảnh được chép; chạy lại không tạo thêm;
    giờ không có ảnh thì bỏ qua.
  - `PUT`: thiếu verdict hoặc nhãn lạ trả 400.
  - Phân quyền: `datagent` nhận 403 ở mọi route `/model/*`.
  - `summary`: tính trên audit dựng tay, so với số tính tay. Có ca ngày 23/11 (2 hộp Hot thật là Nguyên bản,
    2 lon Hot bị sót), ca toàn đúng, và ca chưa có audit (trả `null`, không trả 0).
  - `health`: trên một giờ dựng tay, có một cặp khung trùng.
- **Frontend** (`npm test`, `lib/*.test.ts`): logic xoay vòng trạng thái hộp, điểm sót, tổng theo vị, và điều
  kiện bật Save.
- **Đầu cuối** (Edge chạy ngầm như 22/11):
  - Đăng nhập bằng một tài khoản máy nhóm `team_admin`. Tài khoản `api-check` thuộc `datagent` nên chỉ dùng để
    kiểm 403.
  - Kiểm: chấm một khung thật rồi lưu, các ô chỉ số đổi từ "—" sang số.
- Đọc `frontend/AGENTS.md`: bản Next.js này có thay đổi lớn. Phải đọc tài liệu trong `node_modules/next/dist/docs/` trước khi viết code.

### 9. Triển khai

1. **Backend và hạ tầng:**
   - Đóng gói 2 Lambda theo commit, đưa lên `releases/backend/<sha>/`.
   - Change set từ `infra/backend.yaml` của repo. Template đang chạy chỉ khác repo ở 2 dòng chú thích có dấu gạch
     dài, và ở dòng trống cuối file.
   - Change set chỉ được có: thêm 2 bảng, sửa role, sửa 2 Lambda (code và biến môi trường), và các mục "Dynamic"
     đi kèm.
   - Sau đó chạy bù `model-health`.
2. **Worker:** sao lưu rồi chép `counter.py` lên máy long, thêm `MILK_MODEL_VERSION` vào `worker.env`, khởi động lại.
   Cần hoang đồng ý như ngày 23/11.
3. **Frontend:** deploy tay lên Amplify theo cách đang dùng, rồi chạy bài kiểm đầu cuối trên trang thật.

## Để người làm tự quyết

- Icon của mục "Model", màu, và chi tiết giao diện, theo các trang hiện có.
- Phím tắt khi đếm.
- Cách gom và vẽ biểu đồ.
- Chia code Lambda API thành module, hay giữ trong `handler.py`.
- Tạo tài khoản máy `team_admin` cho bài kiểm đầu cuối: mật khẩu và khoá TOTP để trong SSM, như `api-check`.
