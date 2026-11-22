# NHAT-P01 — Thiết kế Backend Website Đếm Hàng Trên Kệ (Nền B, Serverless)

| Thuộc tính | Giá trị |
| :--- | :--- |
| **Mã plan** | `NHAT-P01` |
| **Folder Confluence** | `Nhật` |
| **Type** | `design-plan` |
| **Status** | `draft` *(chờ `hoang` duyệt chuyển `approved` trước khi mở rộng lên `staging`/`production`)* |
| **Reviewer** | `hoang` |
| **Region đã chốt** | `ap-southeast-1` (Singapore) — *(nguồn: `hoang, 21/11`)* |
| **Ngày lập** | `2026-11-21 22:06 +07:00` |
| **Bảng chỉ mục plan** | `NHAT-P01 \| design-plan \| draft \| Nhật \| hoang \| Backend serverless nền B cho website Next.js` |

> [!IMPORTANT]
> **Ràng buộc an toàn public repo (`Protein-17012006/milk_demo`)**: Không có AWS key, mật khẩu, Cognito token, địa chỉ IP hay ảnh/video cửa hàng nào trong tài liệu này hoặc trong repo *(nguồn: `HOANG-P08 quyết định 7; Claude rule mục 9`)*.
> Mọi đề xuất không có trong tài liệu gốc được gắn nhãn **`(đề xuất)`**; mọi con số chưa có hoá đơn hoặc số đo thực tế được gắn nhãn **`(chưa kiểm chứng)`** *(nguồn: `Claude rule mục 6`)*.

---

## Mục tiêu

Chứng minh (hoặc bác bỏ) rằng backend serverless theo **nền B của `HOANG-P07`** (Amplify Hosting + AWS WAF + API Gateway REST API + Lambda + Cognito MFA + DynamoDB + S3 / Glue / S3 Tables / Athena) đặt tại **Singapore (`ap-southeast-1`)** phục vụ đầy đủ 5 khu vực của website `frontend/` (`/login` & `/register`, `Home`, `Reports`, `Products` + `Validation Card`, `Settings`) bằng dữ liệu thật từ bộ đếm `HOANG-P08`, tuân thủ đúng tên bảng/cột của **Data Dictionary** và khớp từng byte với chuẩn xuất CSV 16 cột (`tests/test_cvoutput.py`), kịp mốc **Alpha `06/12`**.

**Điều kiện `done`**:
1. Một capture thật từ camera cửa hàng đi hết đường từ hub `HOANG-P08` → bộ ghi kết quả (`IngestLambda`) → bảng `cv_output` (S3/Glue) và `latest_stock` (DynamoDB) → trả về qua API `GET /v1/products`.
2. File `GET /v1/exports/cv-output.csv` xuất ra đúng **16 cột** theo thứ tự Data Dictionary kèm UTF-8 BOM (mở trực tiếp trong Excel tiếng Việt không lỗi font).
3. Người dùng Cognito có cấu hình TOTP MFA đăng nhập được; API Gateway chặn request không có token (`401`); người tự đăng ký qua `/register` chưa có nhóm quyền bị chặn (`403 PENDING_ROLE_ASSIGNMENT`).
4. Hạ tầng dựng bằng code (CloudFormation), chạy được unit test + integration test với `moto` (`KHANG-T001`) + kiểm chứng live trên môi trường `development`.

---

## Reason

1. **Quyết định nền B đã chốt (`hoang, 21/11`; `Architecture design mục 4`)**: Không thêm API mới lên hub FastAPI của `HOANG-P08` (vốn dùng mật khẩu chung, 1 EC2 demo). Hệ thống hướng tới sản phẩm dùng thật cho **1 client là Datagent** (mô hình blackbox: Datagent và đội đếm chỉ dùng website và file xuất; team vận hành toàn bộ AWS — *nguồn: `Quyết định Datagent 02/11`*).
2. **Tách biệt đường nhận kết quả & đường đọc web**: Kiến trúc tổng đang được `hoang` vẽ lại từ `21/11` (cách lấy luồng từ cửa hàng và nơi chạy model đếm có thể thay đổi giữa worker máy `long` và SageMaker mỗi đêm). Đưa toàn bộ dữ liệu đi qua một **bộ ghi kết quả duy nhất (`IngestLambda`)** giúp API website độc lập hoàn toàn với nơi chạy model *(nguồn: `Hướng dẫn thiết kế p.1, p.9`)*.
3. **Đồng bộ region Singapore (`ap-southeast-1`)**: Hub `HOANG-P08`, bucket `milk-demo-base-databucket-xh85udq9bhrr`, DynamoDB `milk-demo-base-CapturesTable-*`, Amplify Hosting (`milk-demo-frontend`) và pipeline 4 môi trường `KHANG-T001` đều đang chạy tại `ap-southeast-1`, tránh phí truyền dữ liệu cross-region và giảm độ trễ *(nguồn: `hoang, 21/11`)*.

---

## 1. Sơ đồ kiến trúc Backend (Nền B)

> Nguồn: `Architecture design mục 4, 6, 7`; `HOANG-P08`; `Hướng dẫn thiết kế p.4–5`. Các đường nét đứt/nhãn `(đề xuất)` là phần chọn trong `NHAT-P01`.

```mermaid
flowchart LR
    subgraph Client["Trình duyệt người dùng (Blackbox)"]
        Browser["Datagent / Field Team / Team Admin"]
    end

    subgraph Edge["Frontend & Xác thực (ap-southeast-1)"]
        Amplify["AWS Amplify Hosting\nNext.js 16 Static Export\n(main.d2k8euxy0yoiv8.amplifyapp.com)"]
        Cognito["Amazon Cognito User Pool\nTOTP MFA + 3 Groups:\ndatagent / field_team / team_admin"]
        WAF["AWS WAFv2 Regional WebACL\nRateLimit 2000/5m + AWSManagedRulesCommonRuleSet"]
        APIGW["API Gateway REST API (/v1)\nCognito JWT Authorizer"]
    end

    subgraph Compute["Tầng Xử lý Serverless (Python 3.12)"]
        ApiLambda["Lambda API\nmilk-backend-<env>-api\nRBAC 2 lớp + Presigned URL"]
        IngestLambda["Lambda Bộ ghi kết quả\nmilk-backend-<env>-ingest\nKiểm 16/10 cột + Chống trùng + Alias"]
        Scheduler["EventBridge Rule (Mỗi giờ)\nChọn 1 Capture Chính Thức / cam / giờ"]
    end

    subgraph Data["Tầng Lưu trữ & Phân tích (ap-southeast-1)"]
        DDB["7 Bảng DynamoDB (PITR + SSE)\ncaptures (TTL 7d), latest_stock, review_queue,\nsku_master, store_list, corrections, user_prefs"]
        S3Analytics["Private S3 Analytics Bucket\nKMS/SSE + TLS-only + Versioning\nframes/official (90d), warehouse/ (permanent)"]
        GlueAthena["Glue Data Catalog / S3 Tables\n+ Amazon Athena\n12 KPI (chu kỳ 2 tuần) & Xuất CSV"]
    end

    subgraph ExistingP08["Đang chạy — Giữ nguyên (HOANG-P08)"]
        Worker["GPU Worker (máy long)\nĐếm + Che mặt\nKhông giữ AWS key / Không mở cổng"]
        Hub["Hub EC2 (HOANG-P08)\nGhi frames/ & results/ JSON lên S3"]
        HubS3["Hub S3 Bucket\nmilk-demo-base-databucket-*"]
    end

    subgraph Queue["Hàng đợi & Cảnh báo"]
        SQS["SQS IngestQueue\n+ IngestDLQ (14d) + SNS Alarm"]
    end

    Browser -->|Tải web| Amplify
    Browser -->|Đăng nhập + MFA| Cognito
    Browser -->|Bearer JWT| WAF --> APIGW
    APIGW -.->|Xác thực JWT| Cognito
    APIGW --> ApiLambda

    ApiLambda -->|Đọc/ghi nóng| DDB
    ApiLambda -->|Presigned URL 15m| S3Analytics
    ApiLambda -.->|Đọc ảnh che mặt (RO)| HubS3
    ApiLambda -->|Truy vấn KPI / Export| GlueAthena

    Worker --> Hub --> HubS3
    HubS3 -.->|"S3 Event results/*.json (NHAT-T001)"| SQS
    SQS --> IngestLambda
    Scheduler -->|Hourly trigger| IngestLambda
    IngestLambda --> DDB
    IngestLambda --> S3Analytics --> GlueAthena
```

---

## 2. Danh sách API (`/v1/*`) & OpenAPI Contract

Tài liệu hợp đồng API chuẩn OpenAPI 3.1 nằm tại repo: [backend/openapi.yaml](file:///F:/milk_demo/backend/openapi.yaml) `(đề xuất)`.

| Method | Path | Trang Frontend | Bảng đọc / ghi | Nhóm Cognito |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/v1/health` | Ops / Smoke test | *(không)* | Public (`NONE`) |
| `GET` | `/v1/me` | Login / Register / Guard | JWT claims | Đã đăng nhập (kể cả chưa có nhóm) |
| `GET` | `/v1/products` | `Products`, `Home` | Đọc `sku_master`, `latest_stock`, `store_list`, `review_queue` | `datagent`, `field_team`, `team_admin` |
| `GET` | `/v1/products/{sku_id}` | `Products` (nút `View`) | Đọc `sku_master`, `latest_stock`, `review_queue`, `corrections`, `captures` + ký URL S3 | `datagent`, `field_team`, `team_admin` |
| `GET` | `/v1/stores` | Bộ lọc Store, `Settings`, `Reports` | Đọc `store_list`, `captures` | `datagent`, `field_team`, `team_admin` |
| `GET` | `/v1/search` | `Home` (Quick search) | Đọc `sku_master`, `latest_stock` | `datagent`, `field_team`, `team_admin` |
| `GET` | `/v1/review-queue` | `Products` (Open review queue) | Đọc `review_queue` + ký URL ảnh 15 phút | `datagent`, `field_team`, `team_admin` |
| `POST` | `/v1/corrections` | `Products` / `Validation Card` | Ghi `corrections`, cập nhật trạng thái `review_queue` (`Đã sửa` / `Đã xác nhận`) | `field_team`, `team_admin` |
| `GET` | `/v1/validation/{comparison_id}` | `Validation Card` | Đọc `review_queue`, `corrections`, `sku_master` (tính `Result` & `Status`) | `datagent`, `field_team`, `team_admin` |
| `POST` | `/v1/uploads` | Trang tải lên (SD, điện thoại, Human Audit) | Trả Presigned PUT URL lên `S3Analytics/uploads/` (15 phút) | `field_team`, `team_admin` |
| `POST` | `/v1/imports/sku-master` | `Products` (Import SKU Master) | Ghi `sku_master` | `team_admin` |
| `POST` | `/v1/imports/store-list` | `Settings` (Import Store List) | Ghi `store_list` | `team_admin` |
| `POST` | `/v1/admin/seed` | Bootstrap dữ liệu tạm khi chờ Datagent | Ghi `DEMO-S01` + 16 SKU tạm (`12 sữa + 4 Slide`) | `team_admin` |
| `GET` | `/v1/exports/cv-output.csv` | `Products` (Export CV Output) | Đọc `captures` / Athena `cv_output` → CSV UTF-8 BOM **16 cột** | `datagent`, `field_team`, `team_admin` |
| `GET` | `/v1/exports/capture-log.csv` | Báo cáo vận hành | Đọc `captures` / Athena `capture_log` → CSV UTF-8 BOM **10 cột** | `datagent`, `field_team`, `team_admin` |
| `GET` | `/v1/kpi` | `Reports` (KPI cards) | Đọc `captures`, `latest_stock`, `store_list`, `accuracy_kpi` | `datagent`, `field_team`, `team_admin` |
| `GET` | `/v1/reports/series` | `Reports` (biểu đồ) | Tổng hợp từ `captures` / Athena `cv_output` *(mở rộng sau khi chốt OSA/Restock)* | `datagent`, `field_team`, `team_admin` |
| `GET` / `PUT` | `/v1/settings` | `Settings` (5 mục đợt 1) | Đọc/ghi `user_prefs` + đọc `store_list` + JWT claims | `datagent`, `field_team`, `team_admin` |

> [!NOTE]
> **Mã hoá URL cho `sku_id` tiếng Việt**: Theo quyết định `hoang, 21/11`, `sku_id` là tên sản phẩm in trên bao bì (có dấu cách và dấu tiếng Việt). Mọi lời gọi `GET /v1/products/{sku_id}` phải dùng `encodeURIComponent(sku_id)` ở frontend và `urllib.parse.unquote()` ở Lambda.

**Ví dụ Request & Response (từ dữ liệu thật trên `milk-backend-development`)**:

```http
GET /v1/products?store_id=DEMO-S01 HTTP/1.1
Authorization: Bearer <Cognito-IdToken-JWT>
```

```json
{
  "items": [
    {
      "sku_id": "TH true MILK Sữa Tươi Tiệt Trùng Ít Đường 180ml",
      "sku_name": "TH true MILK Sữa Tươi Tiệt Trùng Ít Đường 180ml",
      "model_alias": "TMP-MLK-TH-02",
      "brand": "TH true MILK",
      "category": "Milk",
      "pack_type": "Carton",
      "pack_size": "180ml",
      "barcode": null,
      "unit_count": 3,
      "smoothed_unit_count": 3,
      "confidence_score": 0.87,
      "stores_available": 1,
      "stores_total": 1,
      "capture_id": "CAP-S01-20261118-174608",
      "capture_timestamp": "2026-11-18T17:46:08+07:00",
      "unregistered_in_master": false
    }
  ],
  "stores_total": 1,
  "unrecognized_units": 1,
  "flag_threshold": 0.7
}
```

```http
POST /v1/corrections HTTP/1.1
Authorization: Bearer <Cognito-IdToken-JWT (group: field_team)>
Content-Type: application/json

{
  "store_id": "DEMO-S01",
  "queue_key": "CAM-S01-A#TH true MILK Sữa Tươi Tiệt Trùng Có Đường 180ml#Low Confidence",
  "reading_id": "RD-S01-20261121-140700-002",
  "original_sku_id": "TH true MILK Sữa Tươi Tiệt Trùng Có Đường 180ml",
  "corrected_sku_id": "TH true MILK Sữa Tươi Tiệt Trùng Ít Đường 180ml",
  "original_count": 1,
  "corrected_count": 2,
  "correction_type": "SKU Fix",
  "notes": "Verified against shelf photo"
}
```

```json
{
  "correction_id": "CORR-20261121-a1b2c3d4",
  "status": "Đã sửa",
  "fed_back_to_model": false,
  "correction_date": "2026-11-21T22:00:00+07:00"
}
```

---

## 3. Mô hình Dữ liệu (S3 Tables / Glue, DynamoDB, S3 & Thời gian giữ)

Mọi mốc giờ lưu chuẩn **ISO 8601 UTC+7** *(nguồn: `Data Dictionary; README`)*. **Tuyệt đối không cộng `unit_count` qua nhiều capture** — tồn kho hiện tại luôn lấy từ capture mới nhất của mỗi camera *(nguồn: `Hướng dẫn thiết kế p.7`)*.

### 3.1. 9 bảng phân tích (S3 Tables / Glue Data Catalog + Athena)

> 5 bảng đầu theo `Architecture design mục 4`; 4 bảng sau đặt tên `(đề xuất)` theo `doc backend 21/11`.

| Bảng | Nguồn định nghĩa | Số cột | Ai ghi | Ghi chú triển khai |
| :--- | :--- | :---: | :--- | :--- |
| `store_list` | Data Dictionary — `Reference - Store List` | 13 | Team (`POST /v1/imports/store-list`) | Trước khi Datagent gửi, seed tạm `DEMO-S01` (`CAM-S01-A`) |
| `sku_master` | Data Dictionary — `Reference - SKU Master` | 14 | Team (`POST /v1/imports/sku-master`) | Seed tạm 12 SKU sữa (`server/milk/skus.json`) + 4 vị Slide (`HOANG-P09`); ô chưa có để `null` |
| `cv_output` | Data Dictionary — `CV Output - AI Reading` | 16 | `IngestLambda` (chỉ capture chính thức) | Khớp từng byte `tests/test_cvoutput.py`; partition `year/month/day` |
| `human_audit` | Data Dictionary — `Validation - Human Audit` | 11 | Đội thực địa Datagent / Team nhập | `unit_count_shelf` là ground truth (chờ chốt điểm A1) |
| `corrections` | Data Dictionary — `Accuracy Report, phần C` | 11 | `ApiLambda` (`field_team` sửa trên web) | Tách riêng khỏi `human_audit` (`HOANG-P07`); có cờ `fed_back_to_model` |
| `accuracy_comparison` `(đề xuất)` | Data Dictionary — `Accuracy Report, phần A` | 12 | Athena (chu kỳ 2 tuần) | 1 dòng cho mỗi `(store_id, sku_id, capture_id)` |
| `accuracy_kpi` `(đề xuất)` | Data Dictionary — `Accuracy Report, phần B` | 12 KPI | Athena (chu kỳ 2 tuần) | Website chỉ đọc kết quả đã tính sẵn |
| `capture_log` `(đề xuất)` | Báo cáo 17/10 — điểm A5 | 10 | `IngestLambda` | 1 dòng mỗi ảnh kể cả ảnh 0 hộp; dùng tính `avg_processing_time_ms` (A7) |
| `unit_detail` `(đề xuất)` | File mẫu 17/10 — sheet `Unit Detail` | Theo mẫu | `IngestLambda` | **Đang chờ worker gửi chi tiết từng hộp** → cần ticket `NHAT-T003` cho `hoang` |

### 3.2. 7 bảng DynamoDB nóng cho Website (`PAY_PER_REQUEST`, PITR + SSE)

| Bảng DynamoDB | Partition Key (PK) | Sort Key (SK) | TTL | Trang đọc / ghi |
| :--- | :--- | :--- | :--- | :--- |
| `milk-backend-<env>-captures` | `camera_id` | `capture_id` | **7 ngày** (`expires_at`) | `IngestLambda` ghi; `ApiLambda` đọc lịch sử gần đây & chọn capture chính thức mỗi giờ |
| `milk-backend-<env>-latest-stock` | `store_id` | `sku_id` | Không | `Products`, `Home`, `Reports` (lưu `unit_count` mới nhất + `smoothed_unit_count` trung vị dưới 3 khung + giữ dòng `__UNRECOGNIZED__`) |
| `milk-backend-<env>-review-queue` | `store_id` | `queue_key` (`camera_id#sku_id#flag_reason`) | Không | `Products` (Open review queue), `Validation Card`; tối đa 1 mục đang mở cho mỗi bộ `(camera, sku, flag_reason)` |
| `milk-backend-<env>-sku-master` | `sku_id` | *(không)* | Không | `Products`, `Home`, `Validation Card`, `POST /v1/imports/sku-master` |
| `milk-backend-<env>-store-list` | `store_id` | *(không)* | Không | Bộ lọc Store, `Reports`, `Settings`, `POST /v1/imports/store-list` |
| `milk-backend-<env>-corrections` | `store_id` | `correction_id` | Không | `POST /v1/corrections`, `Validation Card` |
| `milk-backend-<env>-user-prefs` `(đề xuất)` | `user_sub` | *(không)* | Không | `GET/PUT /v1/settings` (lưu `date_format`, `default_landing_page` theo user) |

### 3.3. Cấu trúc S3 & Chính sách lưu giữ (đã chốt `21/11` theo mốc `HOANG-P07`)

Bucket phân tích private: `milk-backend-<env>-<account_id>` (Block Public Access ON, Versioning ON, SSE-S3/KMS, Bucket Policy từ chối mọi request không dùng TLS `aws:SecureTransport=false`).

| Prefix / Loại dữ liệu | Thời gian giữ | Cơ chế & Nguồn |
| :--- | :---: | :--- |
| `frames/official/<camera>/<date>/` (1 ảnh chính thức/cam/giờ) | **90 ngày** | S3 Lifecycle Expiration 90d *(P07: giữ 3 tháng cho nhiều chu kỳ 2 tuần & train lại)* |
| Ảnh capture liên tục (mỗi 10 giây trên bucket hub `HOANG-P08`) | **7 ngày** | Bucket hub hiện giữ 30d (`infra/base.yaml`) → mở ticket **`NHAT-T001`** nhờ `hoang` hạ xuống 7d & bật S3 Event |
| `frames/corrections/` (ảnh có dòng sửa trong `corrections`) | **Tới khi `fed_back_to_model = TRUE`** | Không áp rule xoá tự động; job dọn sau khi model retrain xong |
| `warehouse/cv_output/`, `warehouse/capture_log/`, S3 Tables | **Không tự xoá** | Dung lượng nhỏ, cần đối chiếu KPI qua các chu kỳ |
| `uploads/` (ảnh thẻ SD, điện thoại, Human Audit tải lên) | **7 ngày** | S3 Lifecycle Expiration sau khi đã ingest vào warehouse |
| `athena-results/` | **14 ngày** | S3 Lifecycle Expiration cho kết quả query tạm |
| DynamoDB `captures` | **7 ngày** | DynamoDB TTL trên cột `expires_at` |

---

## 4. Đường nhận kết quả, Chống trùng & Báo lỗi

1. **Đường vào đã chọn `(đề xuất)`**: **`Hub S3 Event (results/<camera>/<date>/<capture_id>.json) → SQS IngestQueue → IngestLambda`** *(nguồn: `Architecture design mục 3; Hướng dẫn thiết kế p.9`)*.
   - **Ưu điểm**: Không phải sửa code worker trên máy `long` hay hub `store.py`; giữ tuyệt đối ràng buộc *worker không giữ AWS key, không mở cổng* (`HOANG-P08 quyết định 2`); có SQS buffer chống mất bản ghi khi traffic tăng.
   - **Phụ thuộc chéo**: Cần mở ticket **`NHAT-T001`** (reviewer `hoang`) để thêm S3 Event Notification prefix `results/` trên bucket `milk-demo-base-databucket-xh85udq9bhrr` trỏ tới ARN của `IngestQueue` (và hạ `RetentionDays` của hub từ 30 xuống 7 ngày). Trong lúc chờ `NHAT-T001`, `IngestLambda` hỗ trợ chế độ `backfill_from_table` đọc read-only từ `milk-demo-base-CapturesTable-1623FFBNLNMQO` để nạp dữ liệu thật.
2. **Thứ tự xử lý trong `IngestLambda`** ([backend/ingest/handler.py](file:///F:/milk_demo/backend/ingest/handler.py)):
   - **Bước 1 — Validate schema**: Kiểm tra đủ **16 cột** `CV Output` và **10 cột** `Capture Log`. Bản ghi sai schema ném `ValueError` → SQS retry 3 lần (`maxReceiveCount: 3`) → đẩy sang **`IngestDLQ`** (giữ 14 ngày) và kích hoạt CloudWatch Alarm → **SNS Alert** để xử lý & replay *(nguồn: `Architecture design mục 5`)*.
   - **Bước 2 — Chống trùng (Idempotency)**: Ghi vào `captures` bằng `ConditionExpression="attribute_not_exists(capture_id)"`. Nếu `ConditionalCheckFailedException`, trả `duplicate_skipped` — đảm bảo chạy lại cùng một ảnh không bao giờ sinh dòng trùng.
   - **Bước 3 — Đổi nhãn qua bảng Alias**: Chuyển nhãn model (`TMP-MLK-TH-01..12`, `original145`, …) sang `sku_id` = tên sản phẩm chính thức in trên bao bì (`hoang, 21/11`). SKU lạ chưa có trong `sku_master` vẫn được chấp nhận & hiển thị; dòng `sku_id = null` (Unrecognized) vẫn được giữ nguyên.
   - **Bước 4 — Cập nhật bảng nóng**: Ghi `captures` (TTL 7 ngày) và cập nhật `latest_stock` kèm số đếm đã làm mượt bằng trung vị dưới (`lower_median`) 3 khung gần nhất.
   - **Bước 5 — Capture chính thức mỗi giờ & Hàng đợi duyệt (đã chốt `21/11`)**:
     - EventBridge Rule kích hoạt mỗi giờ 1 lần (`select_hourly_official`) chọn đúng **1 capture / camera / giờ** theo thứ tự ưu tiên: **(1) ít `flagged_rows` nhất → (2) nhiều `units_found` nhất → (3) `capture_timestamp` sớm nhất**.
     - Chỉ capture chính thức đi vào `cv_output`, `capture_log`, sao chép ảnh sang `frames/official/` (giữ 90 ngày) và sinh/cập nhật mục trong `review_queue` (gộp theo bộ `camera_id#sku_id#flag_reason`, tối đa 1 mục đang mở mỗi bộ để tránh spam hàng đợi duyệt khi `TMP-MLK-TH-01` có điểm `0.0`).
     - *Lưu ý*: Giả định "chọn capture ít dòng bị cờ nhất giúp tránh ảnh bị người che" hiện là **`(chưa kiểm chứng)`** — sẽ đo lại sau 1 tuần chạy thực tế tại cửa hàng.

---

## 5. Đăng nhập & Phân quyền (Cognito + MFA + RBAC 2 lớp)

1. **Kiến trúc xác thực (`Architecture design mục 6`; `hoang, 21/11`)**:
   - **Đội ngũ phát triển (Team)**: Vào AWS Console/CLI qua IAM Identity Center + MFA.
   - **Datagent & Đội đếm**: Đăng nhập website bằng **Amazon Cognito User Pool** + **TOTP Software Token MFA** (`MfaConfiguration=OPTIONAL` trên `development` để tiện kiểm thử, bắt buộc `ON` trên `staging`/`production`). Không dùng mật khẩu chung của hub `HOANG-P08`.
   - **Một workspace duy nhất**: 1 client là Datagent, không tách `tenant_id` (`hoang, 21/11`).
2. **3 Nhóm quyền Cognito `(đề xuất)` & Kiểm quyền 2 lớp**:
   - **Lớp 1 (API Gateway)**: `CognitoUserPoolsAuthorizer` xác thực chữ ký RS256, `iss`, `aud`, `exp` của JWT trên mọi route trừ `GET /v1/health` và `OPTIONS`. Request không có JWT hợp lệ bị chặn ngay tại edge (`HTTP 401`).
   - **Lớp 2 (Lambda `ApiLambda`)**: Đọc `cognito:groups` trong JWT claims:
     - `datagent` (Precedence 30): Xem tồn kho, báo cáo, 12 KPI, hàng đợi duyệt, xuất CSV (`GET`).
     - `field_team` (Precedence 20): Toàn bộ quyền `datagent` + gửi bản sửa `POST /v1/corrections` + xin Presigned URL tải ảnh/Human Audit `POST /v1/uploads`.
     - `team_admin` (Precedence 10): Toàn bộ quyền trên + `POST /v1/imports/sku-master`, `POST /v1/imports/store-list`, `POST /v1/admin/seed`, quản lý gán nhóm người dùng.
     - **Không thuộc nhóm nào (User tự đăng ký qua `/register`)**: Giữ nguyên trang `/register` theo chốt `hoang, 21/11`, nhưng mọi API dữ liệu trả về **`HTTP 403 {"error": "PENDING_ROLE_ASSIGNMENT"}`** cho tới khi `team_admin` gán họ vào nhóm phù hợp (và vẫn bật MFA).
3. **Vòng đời Token trên Frontend `(đề xuất)`**:
   - **Lấy token**: Sử dụng AWS Amplify Auth (`aws-amplify/auth` hoặc `amazon-cognito-identity-js`) qua flow `ALLOW_USER_SRP_AUTH` (SRP không gửi mật khẩu thô qua mạng), kèm challenge `SOFTWARE_TOKEN_MFA`.
   - **Nơi giữ token**: `IdToken` và `AccessToken` (hạn 1 giờ) giữ **trong bộ nhớ React state / memory** (hạn chế XSS đánh cắp từ `localStorage`), hoặc nếu cần giữ phiên qua reload thì dùng Cognito `RefreshToken` (hạn 7 ngày) với chính sách CSP chặt trên Amplify Hosting (vì frontend hiện chạy static export không có BFF cookie server).
   - **Khi hết hạn**: API trả `401` → interceptor frontend tự động gọi `fetchAuthSession({ forceRefresh: true })` bằng `RefreshToken` và retry 1 lần; nếu refresh thất bại thì điều hướng về `/login`.
4. **Bootstrap tài khoản `team_admin` đầu tiên**:
   - Người vận hành (đăng nhập AWS bằng IAM Identity Center + MFA) chạy 2 lệnh AWS CLI một lần sau khi deploy stack:
     1. `aws cognito-idp admin-create-user --user-pool-id <PoolId> --username <admin-email> --user-attributes Name=email,Value=<admin-email> Name=email_verified,Value=true`
     2. `aws cognito-idp admin-add-user-to-group --user-pool-id <PoolId> --username <admin-email> --group-name team_admin`
   - Lần đăng nhập đầu tiên Cognito bắt buộc đổi mật khẩu tạm và quét QR thiết lập TOTP Authenticator.

---

## 6. Tính toán 12 KPI, Validation Card & Xuất file CSV

### 6.1. 12 KPI chuẩn Data Dictionary (Athena chạy theo chu kỳ 2 tuần)

> Nguồn: `Data Dictionary — Accuracy Report phần B`; `Báo cáo CV Output 17/10`; `Thiết kế backend p.6–7`.

| # | Tên KPI | Mục tiêu Data Dictionary | Nguồn tính & Lưu ý |
| :-: | :--- | :--- | :--- |
| 1 | `sku_identification_accuracy` | $\ge 80\%$ (Top 50 SKU theo sản lượng) | Athena ghép `cv_output` × `human_audit`. **Khi chưa có danh sách Top 50 từ Datagent**: tính trên toàn bộ SKU hiện có và hiện ghi chú rõ trên trang `Reports` *(chốt `21/11`)* |
| 2 | `overall_identification_accuracy` | $\ge 60\%$ (mọi SKU) | Tỷ lệ SKU khớp đúng trên tất cả SKU có trong `human_audit` |
| 3 | `unit_count_mae` | $\le 2$ hộp / SKU / kệ | $\text{MAE} = \text{AVG}(\lvert \text{unit\_count} - \text{unit\_count\_shelf} \rvert)$ *(phụ thuộc điểm A1)* |
| 4 | `unit_count_accuracy_avg` | $\ge 75\%$ | Trung bình `count_accuracy_pct` trong `accuracy_comparison` |
| 5 | `exact_match_rate` | $\ge 40\%$ | Tỷ lệ dòng có $\text{unit\_count} = \text{unit\_count\_shelf}$ |
| 6 | `minor_error_rate` | Khớp chính xác + lệch 1–2 hộp $\ge 75\%$ | Tỷ lệ dòng `discrepancy_category IN ('Exact Match', 'Minor')` |
| 7 | `missed_sku_rate` | $\le 20\%$ | Tỷ lệ SKU có trong `human_audit` nhưng không xuất hiện trong `cv_output` |
| 8 | `false_detection_rate` | $\le 10\%$ | Tỷ lệ SKU có trong `cv_output` nhưng không có trong `human_audit` |
| 9 | `avg_confidence_correct` | $> 0.8$ | Trung bình `confidence_score` của các dòng đoán đúng SKU |
| 10 | `avg_confidence_incorrect` | $< 0.5$ | Trung bình `confidence_score` của các dòng đoán sai SKU |
| 11 | `avg_processing_time_ms` | $\le 30\text{s}$ / ảnh | **1 giá trị mỗi ảnh từ `capture_log`** (không tính trung bình theo từng dòng `cv_output` — *điểm A7*) |
| 12 | `unrecognized_product_rate` | $\le 20\%$ | Tỷ lệ dòng `sku_id IS NULL` trên tổng số dòng `cv_output` (*điểm A3*) |

**Lịch chạy Athena `(đề xuất)`**: Sau khi kết thúc mỗi đợt **Human Audit (chu kỳ 2 tuần)** và `field_team` tải file `human_audit` lên, EventBridge / admin trigger chạy truy vấn Athena cập nhật bảng `accuracy_comparison` và `accuracy_kpi`. Website đọc trực tiếp kết quả tính sẵn để tránh độ trễ 3–8 giây của Athena ở mỗi lượt mở trang `Reports`.

### 6.2. Quy tắc Validation Card & Settings Đợt 1 (đã chốt `21/11`)

- **Validation Card**:
  - `Result`: **`"Đạt"`** khi `sku_match_correct = TRUE` và `discrepancy_category IN ("Exact Match", "Minor")`; ngược lại **`"Không đạt"`**.
  - `Status`: `"Chờ duyệt"` (còn trong `review_queue`), `"Đã sửa"` (có bản ghi trong `corrections`), `"Đã xác nhận"` (`field_team` xác nhận AI đếm đúng — lưu ở `review_queue`).
  - **Đã bỏ** ô `OCR Extracted Text` (model chỉ dùng `Visual`, không đọc chữ trên bao bì).
- **Settings đợt 1 (giữ đúng 5 phần)**: (1) Email & nhóm Cognito (chỉ đọc), (2) Định dạng ngày & trang mở đầu (lưu DynamoDB `user_prefs`), (3) Múi giờ `UTC+7` (chỉ đọc), (4) Ngưỡng cờ `0.70` (chỉ đọc), (5) Danh sách tiệm (`store_list`, `team_admin` nhập file). Ẩn các ô chưa có nguồn/phân hệ: auto-validate, OCR cross-check, model version, giờ quét đêm, cảnh báo out-of-stock/carton, email digest, webhook, API key.

### 6.3. Xuất file CSV đúng chuẩn mẫu 17/10

- Endpoint `GET /v1/exports/cv-output.csv` xuất UTF-8 BOM (`\ufeff`) với đúng **16 cột**: `reading_id, capture_id, store_id, camera_id, capture_timestamp, capture_source, image_filename, sku_id, sku_name, unit_count, confidence_score, detection_method, bounding_box, is_flagged, flag_reason, processing_time_ms` — đảm bảo pass 100% `tests/test_cvoutput.py`.
- Endpoint `GET /v1/exports/capture-log.csv` xuất UTF-8 BOM với đúng **10 cột**: `capture_id, store_id, camera_id, capture_timestamp, capture_source, image_filename, units_found, rows_written, flagged_rows, processing_time_ms`.
- Khi sản lượng vượt ~50.000 dòng, nâng cấp sang Athena async job lưu file ra `S3/athena-results/` và trả Presigned GET URL `(đề xuất)`.

---

## 7. Triển khai IaC, CI/CD 4 môi trường & Quản lý Secret

1. **Hạ tầng bằng code (IaC)**: Sử dụng **AWS CloudFormation** ([infra/backend.yaml](file:///F:/milk_demo/infra/backend.yaml)) để đồng bộ hoàn toàn với stack hiện có của team (`infra/base.yaml`, `milk-platform`, `milk-{development,test,staging,production}` trong `KHANG-T001`).
2. **4 Môi trường theo `KHANG-T001`**:
   - `milk-backend-development` (nhánh `develop` / `Frontend`, `MfaConfiguration=OPTIONAL`, deploy tự động sau khi pass pytest).
   - `milk-backend-test` (nhánh `test`, chạy smoke test + moto integration test).
   - `milk-backend-staging` (nhánh `staging`, `MfaConfiguration=ON`, chạy E2E test).
   - `milk-backend-production` (nhánh `main`, `MfaConfiguration=ON`, **bắt buộc manual approval trên GitHub Environment** trước khi deploy).
3. **Tích hợp pipeline của Khang (Ticket `NHAT-T002`)**:
   - Không tự sửa workflow trong folder/code của Khang (`Claude rule mục 8`). Mở ticket **`NHAT-T002`** (reviewer: `Khang`) để thêm job `deploy-backend` vào GitHub Actions: chạy `pytest tests/test_backend_api.py tests/test_backend_integration_moto.py tests/test_cvoutput.py`, đóng gói `api_lambda.zip` & `ingest_lambda.zip` lên `s3://milk-<env>-754361433393/releases/backend/<sha>/`, và gọi `aws cloudformation deploy --stack-name milk-backend-<env> --template-file infra/backend.yaml --capabilities CAPABILITY_NAMED_IAM`.
4. **Nơi giữ Secret**:
   - CI/CD xác thực vào AWS qua **GitHub OIDC IAM Role** (không lưu static `AWS_ACCESS_KEY_ID` lâu dài trong repo).
   - Tham số công khai của frontend (`NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_COGNITO_USER_POOL_ID`, `NEXT_PUBLIC_COGNITO_CLIENT_ID`) đặt trong **Amplify Hosting Environment Variables** theo từng nhánh — không chứa secret.
   - Secret nội bộ (nếu có webhook/key tương lai) đặt trong **AWS Secrets Manager / SSM Parameter Store SecureString** mã hoá KMS.

---

## 8. Bảo mật, Riêng tư & Pháp lý

| Lớp | Triển khai thực tế & Kế hoạch | Nguồn |
| :--- | :--- | :--- |
| **WAF & Chống lạm dụng** | AWS WAFv2 Regional WebACL gắn trực tiếp vào REST API Gateway stage `/v1`: `RateLimit2000Per5Min` (theo IP) + `AWSManagedRulesCommonRuleSet`; API Gateway throttling `100 req/s`, burst `200`. | `HOANG-P07 mục 6` |
| **Mã hoá & Truyền tải** | S3 `SSE-S3` (nâng lên `KMS CMK` ở production), DynamoDB SSE + PITR, ép buộc HTTPS/TLS (`aws:SecureTransport=true`), S3 `BlockPublicAcls/Policy` bật toàn phần. | `HOANG-P07 mục 6` |
| **Ảnh đã che mặt** | Worker che mặt trước khi rời máy `long`; website chỉ xem ảnh qua **Presigned GET URL hết hạn sau 15 phút** do `ApiLambda` ký sau khi xác thực JWT. | `HOANG-P07 QĐ6; HOANG-P08 QĐ3` |
| **Giám sát & Kiểm toán** | CloudWatch Logs cho `ApiLambda` & `IngestLambda` (retention 30 ngày), Alarm trên `IngestDLQ` + 5XX API → SNS; CloudTrail toàn tài khoản + AWS Budgets cảnh báo chi phí (`\$100` ngưỡng tài khoản hiện tại). | `HOANG-P07 mục 6, 7` |
| **Tuân thủ pháp lý** | Xử lý ảnh tại Singapore là chuyển dữ liệu xuyên biên giới theo **Luật 91/2025** (Điều 20, 21 — yêu cầu hồ sơ đánh giá tác động trong **60 ngày** từ lần chuyển dữ liệu đầu tiên từ cửa hàng). **Chưa có tư vấn pháp lý** → ghi rõ rủi ro để `hoang` & Datagent xử lý trước khi chạy rộng. | `Thiết kế backend p.11, 14` |

---

## 9. Ước tính Chi phí theo tháng tại Singapore (`ap-southeast-1`)

> [!WARNING]
> Toàn bộ bảng chi phí dưới đây là **`(chưa kiểm chứng)`** cho tới khi có hoá đơn thực tế trên AWS Cost Explorer / Billing *(quy định `Hướng dẫn thiết kế p.15`)*. Giả định theo `HOANG-P07`: **4 tiệm × 1 camera**, ~**10 người dùng**, ~**20.000 API request/tháng**, 14 capture chính thức/tiệm/ngày (~1.680 ảnh/tháng).

| Dịch vụ AWS (`ap-southeast-1`) | Khối lượng ước tính / tháng | Chi phí ước tính (USD/tháng) | Ghi chú |
| :--- | :--- | :---: | :--- |
| **AWS WAFv2 Regional WebACL** | 1 WebACL ($\$5.00$) + 2 rules ($\$2.00$) + 20K req ($\approx \$0.01$) | **\$7.01 – \$10.01** *(chưa kiểm chứng)* | Chiếm tỷ trọng lớn nhất phần website (tương đồng P07 \$10.01 giá Tokyo) |
| **Amplify Hosting (Static Export)** | 1 app, build ~20 phút, <1 GB traffic | **\$0.00 – \$0.50** *(chưa kiểm chứng)* | Nằm gọn trong Free Tier / giá cực thấp nhờ static export |
| **Amazon Cognito User Pool** | ~10 MAU (dưới mốc 10.000 MAU Free Tier) | **\$0.00** *(chưa kiểm chứng)* | TOTP MFA miễn phí (không dùng SMS MFA) |
| **API Gateway REST API** | 20.000 requests (\$4.25 / 1M req tại Singapore) | **\$0.09** *(chưa kiểm chứng)* | Giá REST API Singapore nhỉnh hơn us-east-1 nhưng ở mức 20K req gần như bằng 0 |
| **AWS Lambda (API + Ingest)** | ~100.000 invocations × 256 MB × 150 ms | **\$0.00 – \$0.10** *(chưa kiểm chứng)* | Trong Free Tier (1M req + 400.000 GB-s/tháng) |
| **Amazon DynamoDB (7 bảng On-Demand + PITR)** | ~200K WCU / 100K RCU, <100 MB lưu trữ | **\$0.35 – \$0.60** *(chưa kiểm chứng)* | TTL 7 ngày giữ dung lượng bảng `captures` nhỏ |
| **Amazon S3 + S3 Tables / Glue + Athena** | ~5 GB ảnh 90 ngày + JSONL, ~20 truy vấn Athena (<1 GB scan) | **\$0.20 – \$0.40** *(chưa kiểm chứng)* | Athena \$5/TB dữ liệu quét; partition `year/month/day` giảm scan xuống vài MB |
| **SQS + EventBridge + CloudWatch Logs** | ~150K messages, 720 hourly triggers, <1 GB logs | **\$0.10 – \$0.50** *(chưa kiểm chứng)* | 1M SQS request đầu tiên miễn phí |
| **Tổng riêng phần Website Backend (nền B)** | — | **~ \$8 – \$12 / tháng** *(chưa kiểm chứng)* | Rất dư dả so với \$200 AWS credit hiện có & \$800 credit Datagent (`02/11`) |

---

## 10. Đánh đổi các điểm còn phải chọn (Mục *Nền backend* p.5)

| # | Điểm cần chọn | Các phương án & Đánh đổi | Đề xuất của `NHAT-P01` |
| :-: | :--- | :--- | :--- |
| 1 | **REST API hay HTTP API** | AWS chỉ hỗ trợ gắn **WAFv2 trực tiếp vào REST API** (`HTTP API: No`). Dùng HTTP API phải dựng thêm CloudFront + WAF phía trước, phức tạp hoá routing và chi phí tương đương. | **Chọn REST API Gateway** + WAFv2 trực tiếp (đã triển khai & verify thành công trên `milk-backend-development`). |
| 2 | **Nơi chạy Frontend (Next.js 16.4.6)** | Amplify Hosting chỉ ghi hỗ trợ SSR chính thức tới Next.js 15; thử deploy SSR Next.js 16 có rủi ro lỗi adapter. Ngược lại, **Next.js Static Export (`output: "export"`)** trên Amplify Hosting `WEB` chạy ổn định 100% vì toàn bộ frontend là client dashboard gọi REST API. | **Chọn Amplify Hosting với `output: "export"`** (đã deploy live thành công tại `https://main.d2k8euxy0yoiv8.amplifyapp.com`, 0 lỗi console). |
| 3 | **Ngôn ngữ Lambda** | **Python 3.12** tái sử dụng trực tiếp chuẩn xuất `milk.cvoutput` và khớp hệ sinh thái test `pytest` + `moto` của `KHANG-T001`. TypeScript cùng ngôn ngữ frontend nhưng phải viết lại toàn bộ logic 16-col CSV & làm tròn confidence. | **Chọn Python 3.12** cho cả `ApiLambda` và `IngestLambda`. |
| 4 | **Hạ tầng bằng code (IaC)** | P07 đề xuất CDK/Terraform; nhưng repo `milk_demo` (`infra/base.yaml`) và pipeline 4 môi trường của Khang (`KHANG-T001`) đều đang dùng **CloudFormation**. Dùng Terraform sẽ tách đôi state quản lý. | **Chọn CloudFormation (`infra/backend.yaml`)** để nối trực tiếp vào pipeline của Khang mà không thêm công cụ mới. |
| 5 | **Đường nhận kết quả** | (a) S3 Event → SQS → Lambda; (b) Hub gọi API bằng IAM Role (phải sửa `store.py`); (c) Worker gửi thẳng (phải sửa worker + thêm auth máy). | **Chọn (a) S3 Event → SQS → `IngestLambda`** `(đề xuất)` + mở ticket `NHAT-T001` cho `hoang`. |
| 6 | **Athena chậm vài giây mỗi query** | Query Athena trực tiếp mỗi lần tải `Reports` gây trễ 3–8 giây và tốn tiền scan lặp. | **Tính sẵn KPI theo chu kỳ 2 tuần** vào `accuracy_kpi`, đọc nhanh từ DynamoDB cho màn hình realtime; xuất file lớn chạy nền trả Presigned URL `(đề xuất)`. |
| 7 | **Region sao lưu (DR)** | Region chính đã chốt **`ap-southeast-1` (Singapore)**. P07 từng chọn Osaka vì đi cùng Tokyo. Với Singapore, cần 1 region backup gần và tuân thủ quy định lưu trữ. | **Đề xuất backup sang `ap-southeast-2` (Sydney) hoặc `ap-northeast-1` (Tokyo)** qua S3 Cross-Region Replication + AWS Backup ở giai đoạn mở rộng production *(chờ `hoang` chốt; ưu tiên sau mốc Alpha `06/12`)*. |

---

## 11. Bảng Mâu thuẫn, Lệch nguồn & Câu hỏi mở cho `hoang`

### 11.1. Các điểm đã xử lý / chờ xác nhận từ `hoang`

| # | Nội dung mâu thuẫn / Chỗ mở | Nguồn A vs Nguồn B | Trạng thái & Đề xuất xử lý |
| :-: | :--- | :--- | :--- |
| 1 | **Định nghĩa số liệu ngoài Data Dictionary** (`OSA`, `Restock Rate`, `Out-of-Stock`, `Restock Volume`, `Avg. Stock / Store`, `Recent activities`, `Detection Accuracy`) | Figma Project A có các ô này **vs** Data Dictionary & `MeetingNote 02/11` chưa định nghĩa và Datagent chưa yêu cầu | **Còn mở (`hoang` → Datagent)**. Làm sau cùng; giữ API `/v1/reports/series` trả dữ liệu đếm theo thời gian cơ bản trước, không tự bịa công thức OSA/Restock. |
| 2 | **9 điểm A1–A9 (báo cáo 17/10)** | A1 (`unit_count` nhìn thấy vs `unit_count_shelf` cả kệ), A5 (`capture_log`), A7 (`avg_processing_time_ms`), A9 (`Anomalous Count`) đang chờ Datagent xác nhận | **Còn mở (Datagent qua `long`)**. A1 bắt buộc chốt trước đợt Human Audit đầu tiên; tạm áp dụng A3, A5, A7 đúng báo cáo 17/10; chưa bật cờ A9 trong 2 tuần đầu. |
| 3 | **Đơn vị đếm lẻ hay lốc/thùng** | Frontend có cảnh báo "carton" **vs** `hoang`: *"chưa rõ, có thể cả 2"* | **Còn mở (Datagent qua `long`)**. Ẩn cảnh báo carton ở đợt 1; đề xuất mỗi quy cách đóng gói là 1 SKU riêng trong `sku_master`, không thêm cột mới vào `CV Output` `(đề xuất)`. |
| 4 | **`sku_id` khi Datagent gửi SKU Master** | Data Dictionary: `sku_id` dạng mã (`SKU-MLK-VNM-001`) **vs** `hoang, 21/11`: *"sku tôi đã chốt với họ là tên sản phẩm"* | Đã tuân thủ quyết định mới nhất `21/11`: dùng **tên sản phẩm in trên bao bì** làm `sku_id`, map nhãn model qua bảng alias. Nếu sau này Datagent vẫn yêu cầu mã nội bộ, chỉ cần cập nhật bảng alias không phải sửa lịch sử. |
| 5 | **4 vị snack Slide** (`original145`, `sourcream150`, `cheese145`, `hot160`) | Đã train `20/11` (`HOANG-P09`) **vs** Data Dictionary chỉ ghi `Milk` & `Instant Noodles` | Đã đưa 4 vị Slide vào bảng alias & seed tạm; chờ Datagent xác nhận phạm vi snack và tên chính xác trên bao bì. |
| 6 | **Chi tiết từng hộp (`unit_detail`)** | Validation Card cần điểm từng hộp **vs** bản ghi `/internal/persist` hiện tại của worker chưa gửi `unit_detail` | Mở ticket **`NHAT-T003`** (reviewer `hoang`) bổ sung `unit_detail` vào payload persist của worker. |
| 7 | **`.gitignore` của repo `milk_demo`** | Dòng 24 (`data/`) và dòng 31 (`*.png`) đang chặn `frontend/data/` và `frontend/public/images/` khiến build CI lỗi nếu clone mới | Bổ sung ngoại lệ `!frontend/data/` và `!frontend/public/images/` (vẫn tuyệt đối giữ chặn ảnh cửa hàng/chụp thật ở mọi thư mục khác) trước khi nối API thật thay dữ liệu mock. |
| 8 | **Màn hình chưa có trên Figma** | Trang tải ảnh thẻ SD/điện thoại, nhập Human Audit, quản lý Store List chưa có thiết kế Figma | Backend đã có sẵn endpoint (`POST /v1/uploads`, `POST /v1/imports/store-list`). Hỏi `hoang` ai phụ trách vẽ UI cho 3 màn này sau Alpha. |
| 9 | **Vận hành sau môn học & License YOLO (AGPL-3.0)** | `HOANG-P07 quyết định 7` & `Thiết kế backend p.13` | Ghi nhận để `hoang` chốt với Datagent trước khi bàn giao thương mại. |

---

## 12. Phân mốc: Demo `02/12` vs Alpha `06/12`

| Mốc | Phạm vi bàn giao | Ghi chú |
| :--- | :--- | :--- |
| **Demo tại cửa hàng (`02/12`)** | • Dashboard hub `HOANG-P08` vẫn là phương án dự phòng chạy trực tiếp trên cửa hàng `(đề xuất)`.<br>• Hạ tầng backend `milk-backend-development` đã dựng xong trên Singapore, đã backfill 281 capture thật, hoạt động live: `/v1/health`, `/v1/products`, `/v1/stores`, `/v1/review-queue`, `/v1/kpi`, `/v1/exports/cv-output.csv` (16 cột), Cognito + MFA + WAFv2.<br>• Nối frontend Amplify (`Login/Register`, `Products`, `Home`, `Settings` 5 mục) gọi API thật trên môi trường `development`. | Kịp trình diễn song song giao diện mới + dữ liệu thật từ `DEMO-S01`. |
| **Alpha (`06/12`)** | • Hoàn tất ticket **`NHAT-T001`** (`hoang` bật S3 Event `results/` trên hub bucket → `IngestQueue` realtime + hạ retention hub xuống 7 ngày).<br>• Hoàn tất ticket **`NHAT-T002`** (`Khang` nối `infra/backend.yaml` vào GitHub Actions cho 4 môi trường `development`/`test`/`staging`/`production`).<br>• Nối hoàn chỉnh `Validation Card`, luồng `field_team` sửa dòng bị cờ (`POST /v1/corrections`), tải Human Audit (`POST /v1/uploads`), và Athena query tính 12 KPI chu kỳ đầu tiên khi có Human Audit. | Đạt đủ điều kiện `done` cho toàn bộ 5 khu frontend trên môi trường `staging`/`production`. |

---

## 13. Chiến lược Test & Bằng chứng Chạy thật

### 13.1. Bộ kiểm thử tự động (Unit Test + Integration Test `moto` + Contract Test `cvoutput`)

- **Unit tests** ([tests/test_backend_api.py](file:///F:/milk_demo/tests/test_backend_api.py)): kiểm tra ánh xạ alias `TMP-MLK-*` → tên sản phẩm, làm mượt `lower_median`, quy tắc `Validation Card Result`, kiểm đủ 16/10 cột, UTF-8 BOM CSV, RBAC chặn user chưa có nhóm (`403 PENDING_ROLE_ASSIGNMENT`), RBAC chặn `datagent` gọi import (`403`), CORS allowlist, và luật chọn 1 capture chính thức mỗi giờ.
- **Integration tests với AWS giả (`moto`)** ([tests/test_backend_integration_moto.py](file:///F:/milk_demo/tests/test_backend_integration_moto.py)): khớp cách làm của `KHANG-T001` — dựng 7 bảng DynamoDB + S3 bucket giả, chạy trọn vòng đời `seed → ingest → dedupe → GET /v1/products (tiếng Việt URL-encoded) → GET /v1/review-queue → POST /v1/corrections → GET /v1/exports/cv-output.csv (16 cột)`.
- **Contract tests** ([tests/test_cvoutput.py](file:///F:/milk_demo/tests/test_cvoutput.py)): xác minh định dạng xuất khớp từng byte với file mẫu `17/10`.

**Bằng chứng chạy `pytest` (nguyên văn, `2026-11-21 22:00 +07:00`)**:

```text
2026-11-21 22:00 +07:00
============================= test session starts =============================
platform win32 -- Python 3.13.13, pytest-9.2.0, pluggy-1.7.0
rootdir: F:\milk_demo
configfile: pytest.ini
collecting ... collected 21 items

tests/test_backend_api.py::test_alias_resolution_maps_model_label_to_packaging_name PASSED [  4%]
tests/test_backend_api.py::test_lower_median_smoothing PASSED            [  9%]
tests/test_backend_api.py::test_validation_card_result_rule PASSED       [ 14%]
tests/test_backend_api.py::test_validate_capture_payload_checks_16_and_10_columns PASSED [ 19%]
tests/test_backend_api.py::test_csv_export_has_utf8_bom_and_16_columns PASSED [ 23%]
tests/test_backend_api.py::test_rbac_blocks_unassigned_self_registered_user PASSED [ 28%]
tests/test_backend_api.py::test_rbac_blocks_datagent_from_admin_import PASSED [ 33%]
tests/test_backend_api.py::test_health_endpoint_is_public PASSED         [ 38%]
tests/test_backend_api.py::test_select_best_capture_hourly_tiebreak PASSED [ 42%]
tests/test_backend_api.py::test_options_preflight_returns_cors_headers PASSED [ 47%]
tests/test_backend_integration_moto.py::test_end_to_end_ingest_review_and_export_with_moto PASSED [ 52%]
tests/test_cvoutput.py::test_rows_match_the_17_10_sample_exactly PASSED  [ 57%]
tests/test_cvoutput.py::test_output_does_not_depend_on_the_order_the_model_lists_skus PASSED [ 61%]
tests/test_cvoutput.py::test_capture_log_matches_the_17_10_sample PASSED [ 66%]
tests/test_cvoutput.py::test_csv_starts_with_bom_for_excel PASSED        [ 71%]
tests/test_cvoutput.py::test_empty_frame_gives_no_rows_but_a_log_line PASSED [ 76%]
tests/test_cvoutput.py::test_allocator_suffixes_reset_each_second PASSED [ 80%]
tests/test_cvoutput.py::test_score_is_rounded_down_and_the_flag_uses_the_raw_mean PASSED [ 85%]
tests/test_cvoutput.py::test_a_mean_of_exactly_0_70_is_accepted PASSED   [ 90%]
tests/test_cvoutput.py::test_three_cartons_at_0_70_fall_just_below_in_floating_point_and_are_flagged PASSED [ 95%]
tests/test_cvoutput.py::test_counts_use_unrecognized_key PASSED          [100%]

============================= 21 passed in 5.76s ==============================
```

### 13.2. Bằng chứng triển khai Live trên AWS Singapore (`milk-backend-development`)

- **CloudFormation Stack (`2026-11-21 22:00 +07:00`)**: `milk-backend-development` → **`CREATE_COMPLETE`** (`ap-southeast-1`):
  - `ApiBaseUrl`: `https://qq20q6drmi.execute-api.ap-southeast-1.amazonaws.com/v1`
  - `CognitoUserPoolId`: `ap-southeast-1_6MvmrWNmd` (3 groups: `team_admin`, `field_team`, `datagent`; `SoftwareTokenMfaConfiguration.Enabled = true`)
  - `CognitoClientId`: `60l85r4c624741f2mr9hecr81d`
  - `AnalyticsBucketName`: `milk-backend-development-754361433393`
  - `GlueDatabaseName`: `milk_backend_development` (tables: `cv_output`, `capture_log`)
  - `AthenaWorkGroupName`: `milk-backend-development`
  - `WAFv2 WebACL`: `milk-backend-development-waf` gắn trực tiếp vào `arn:aws:apigateway:ap-southeast-1::/restapis/qq20q6drmi/stages/v1`

- **Kiểm chứng HTTP qua WAF + REST API Gateway (`2026-11-21 22:02 +07:00`)**:
```text
2026-11-21 22:02 +07:00
--- Public GET /v1/health ---
{"status":"ok","service":"milk-backend-api","region":"ap-southeast-1","flag_threshold":0.7}
--- Unauthenticated GET /v1/products (expect 401) ---
HTTP Status: 401
```

- **Kiểm chứng Backfill dữ liệu thật từ hub `milk-demo-base-CapturesTable-1623FFBNLNMQO` (read-only) & Chống trùng (`2026-11-21 22:02 +07:00`)**:
```json
{"action": "backfill_from_table", "scanned": 281, "ingested": 231, "skipped_duplicates": 50, "official_hourly_written": 2}
```

- **Kiểm chứng dữ liệu thật qua các route API (`2026-11-21 22:04 +07:00`)**:
```text
2026-11-21 22:04 +07:00
GET /v1/products -> HTTP 200, items=16
GET /v1/stores -> HTTP 200, stores=1, first_store=DEMO-S01
GET /v1/review-queue -> HTTP 200, open_items=8, first_reason=Low Confidence, has_frame_presigned_url=True
GET /v1/kpi -> HTTP 200, body={"active_stores_monitored": 1, "total_stores": 1, "total_on_shelf_units": 14, "unrecognized_units": 1, "avg_processing_time_ms": 118, "top_50_sku_accuracy": null, "top_50_scope_note": "Pending first Human Audit cycle; currently tracking all available SKUs.", "captures_count": 281, "flag_threshold": 0.7}
GET /v1/exports/cv-output.csv -> HTTP 200, has_bom=True, col_count=16, total_rows=483
CSV Header: reading_id,capture_id,store_id,camera_id,capture_timestamp,capture_source,image_filename,sku_id,sku_name,unit_count,confidence_score,detection_method,bounding_box,is_flagged,flag_reason,processing_time_ms
```

---

## Nextstep

1. Nộp bản draft `NHAT-P01` lên Confluence folder `Nhật` (reviewer `hoang`) để duyệt sang `approved` và chốt các điểm mở ở Mục 11.
2. Mở 3 ticket liên nhóm trong `Nhật_Ticket`:
   - **`NHAT-T001`** (reviewer `hoang`): Bật S3 Event Notification (`results/`) trên bucket hub `milk-demo-base-databucket-xh85udq9bhrr` trỏ vào `IngestQueue` và hạ `RetentionDays` của hub từ 30 xuống 7 ngày.
   - **`NHAT-T002`** (reviewer `Khang`): Tích hợp `infra/backend.yaml` và bộ test `pytest` + `moto` vào pipeline CI/CD 4 môi trường (`KHANG-T001`).
   - **`NHAT-T003`** (reviewer `hoang`): Bổ sung `unit_detail` (điểm từng hộp) vào payload `/internal/persist` của worker để phục vụ chi tiết Validation Card.
3. Kết nối `frontend/` (Next.js trên Amplify Hosting) với Cognito User Pool (`ap-southeast-1_6MvmrWNmd`) và REST API Gateway (`https://qq20q6drmi.execute-api.ap-southeast-1.amazonaws.com/v1`), thay thế dần dữ liệu giả bằng API thật trên môi trường `development` trước mốc demo `02/12`.

---

## Nhật ký

- **`2026-11-21 21:40 +07:00`**: Khảo sát đầy đủ AWS account `754361433393` (`ap-southeast-1`), đọc toàn bộ tài liệu đầu vào (`Data Dictionary`, `Định dạng output model`, `Thiết kế backend 21/11`, `Hướng dẫn thiết kế cho Nhật`) và mã nguồn `server/milk/*`, `infra/base.yaml`, `tests/test_cvoutput.py`.
- **`2026-11-21 21:53 +07:00`**: Hoàn thiện `backend/common.py`, `backend/api/handler.py`, `backend/ingest/handler.py`, `backend/openapi.yaml`, `infra/backend.yaml`; vượt qua `aws cloudformation validate-template` HTTP 200.
- **`2026-11-21 21:54 +07:00`**: Lần deploy đầu gặp rollback do `ApiWafAssociation` thiếu `DependsOn: ApiStage`; đã bổ sung `DependsOn: ApiStage` và tham chiếu `${ApiStage}` trong `infra/backend.yaml`.
- **`2026-11-21 22:00 +07:00`**: `pytest` pass **21/21** (10 unit tests + 1 `moto` integration test + 10 `cvoutput` contract tests). CloudFormation stack **`milk-backend-development`** đạt **`CREATE_COMPLETE`** tại `ap-southeast-1`.
- **`2026-11-21 22:04 +07:00`**: Seed 1 cửa hàng (`DEMO-S01`) + 16 SKU; backfill 281 capture thật từ hub (chứng minh chống trùng 50 bản ghi); xác minh live HTTP 200 `/v1/health`, HTTP 401 khi thiếu JWT, WAFv2 gắn trên stage `/v1`, và file `cv-output.csv` xuất đủ 16 cột (483 dòng thật). Hoàn thiện bản draft `NHAT-P01`.
