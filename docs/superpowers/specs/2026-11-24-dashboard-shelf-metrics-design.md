# Dashboard: OSA, hết hàng, bổ sung hàng và hoạt động trên kệ

Ngày 2026-11-24 · hoang chọn hướng và duyệt thiết kế trong chat ("duyệt thiết kế") · nối tiếp HOANG-P10 (website
dùng số thật)

## Vì sao

- **hoang, chat 24/11:** *"trang dashboard chưa biết có 1 số dashboard trống sẽ hiển thị như thế nào"*. Các ô đang
  trống: On-Shelf Availability (OSA), Top 50 SKU Accuracy, Restock Rate (vs Last Cycle), cả 4 tab Trends & Insights,
  và Recent Shelf Activities.
- **Vì sao trống:** câu mở #1 của `docs/NHAT-P01.md` ghi rằng các số này có trong Figma, nhưng Data Dictionary và
  Datagent chưa định nghĩa. Team đã chốt không tự đặt công thức. **Ngày 24/11 hoang báo:** *"datagent bảo chúng tôi tự
  định nghĩa cho phù hợp"*.
- **Data Dictionary (bản tải 24/11):**
  - Store List và SKU Master không có cột giờ mở cửa hay danh sách hàng của tiệm.
  - Không sheet nào định nghĩa OSA, hết hàng hay bổ sung.
  - Chu kỳ đo là 2 tuần: README ghi *"Measurement cycle: Bi-weekly"*, Accuracy Report ghi *"retrain the model at least
    once per bi-weekly cycle"*.
- **Figma Project A, khung Dashboard `2:1031`** cho thấy mỗi ô trông thế nào khi có số:
  - OSA "64%".
  - Restock Rate (vs Last Cycle) "+34%", kèm sparkline.
  - 4 tab xu hướng theo tuần.
  - Danh sách sự kiện: OOS "0 cartons (−6)", RESTOCKED "+16 cartons (24 total)", DEPLETED "−4 cartons (8 left)",
    LOW STOCK. Lọc theo All / Alerts Only / Restocked.
- **Dữ liệu thật 23/11:**
  - Từ 21h ảnh tối. Model chỉ thấy 0–2 hộp, độ tin cậy trung vị 0.17–0.33, nên mọi SKU bị đếm về 0.
  - Sau 22:00 không còn capture nào; hub tắt lúc 23:00 (spec 2026-11-23).
  - 12 SKU sữa mà tiệm không bán thỉnh thoảng vẫn bị "thấy", với độ tin cậy gần 0.

## hoang đã chọn (24/11)

- **SKU "phải có trên kệ" của mỗi tiệm:** danh sách theo tiệm do team_admin đặt. Mặc định là các SKU thấy rõ (độ tin
  cậy ≥ 0.70) trong 7 ngày gần nhất, sửa được trong Settings.
- **Cách xây:** B, tính sẵn giống model-health. Sự kiện và số tổng hợp được tính trước, Dashboard chỉ đọc.
- **Top 50 SKU Accuracy tính từ khung team tự chấm:** mọi nhóm đều thấy, kể cả Datagent. hoang: *"ai cũng có thể thấy
  nên không phải lo"*. Điều này thay cho ghi chú trong spec 2026-11-23 rằng ô này trên Reports giữ "—".

## Mục tiêu

- Mỗi ô trên Dashboard hiện số thật. Nếu chưa có số, ô nói rõ còn thiếu gì và ai làm. Không còn dòng "the API does
  not serve this".
- Mỗi số có định nghĩa viết ở một chỗ, và trang hiện dòng giải thích ngắn như Live health.
- Giờ đóng cửa, ảnh tối và lúc camera tắt không làm sai số.
- Datagent mở trang là trả lời được:
  - tiệm nào đang thiếu SKU nào, từ lúc nào;
  - tỉ lệ có hàng trên kệ;
  - tiệm bổ sung hàng nhiều hay ít hơn chu kỳ trước.

## Không làm (bản này)

- Không đổi cách worker đếm. Không đổi CV Output, CSV hay Capture Log.
- Không đọc độ sáng khung hình. Để sau: worker báo độ sáng để bỏ các khung quá tối.
- Không nhập Human Audit của Datagent.
- Không gửi cảnh báo qua email, Slack hay SNS.
- Giờ mở cửa chỉ có một khoảng dùng chung cho mọi ngày, không chia theo thứ.

## Không được xảy ra

- Không có số giả. Chưa đủ dữ liệu thì ô hiện "—" kèm lý do, không hiện 0%.
- Giờ đóng cửa, hoặc lúc không có capture, không được tính là hết hàng.
- SKU không thuộc danh sách của tiệm không sinh sự kiện và không kéo OSA xuống.
- Job chạy lại, hay hai lượt chạy chồng nhau, không được đếm trùng.

## Phương án

hoang chọn B.

- A. Tính lại mỗi lần mở trang, từ `captures`. Loại vì chỉ có 7 ngày lịch sử (capture hết hạn sau 7 ngày), và mỗi lần
  mở trang lại quét lại.
- **B. Tính sẵn, giống model-health. Chọn.**
- C. Athena trên `cv_output` ở S3. Loại vì `cv_output` chỉ có 1 capture chính thức mỗi giờ, nên không thấy các lần
  hết hàng hay bổ sung ngắn hơn 1 giờ. Mỗi truy vấn cũng mất 3–8 giây.

## Thiết kế

### 1. Định nghĩa *(đề xuất; Datagent giao team tự định nghĩa)*

**Lần kiểm.**
- Mỗi khoảng 5 phút của một tiệm (giờ UTC+7, bắt đầu ở :00, :05, :10…) là một lần kiểm, nếu trong khoảng đó có ít nhất
  1 capture.
- Số đơn vị của một SKU trong lần kiểm là trung vị số đơn vị của SKU đó qua các capture trong 5 phút. Capture không có
  SKU thì tính là 0. Tiệm có nhiều camera thì cộng các camera lại.
- Số đơn vị lấy đúng số model ghi trong capture, như trang Products, ở mọi độ tin cậy.
- Vì sao chọn 5 phút: worker đếm 30 giây mỗi 5 phút (`MILK_SAMPLE_EVERY_S=300`), nên mỗi lần kiểm đúng bằng một nhịp
  đếm. Khi worker đếm liên tục, khoảng 5 phút gom các capture lại.

**Lần kiểm được tính** là lần kiểm thoả cả hai điều kiện:
- SKU thuộc danh sách phải có của tiệm;
- lần kiểm nằm trong giờ mở cửa của tiệm.

Khoảng 5 phút không có capture (camera hay hub tắt) thì không có lần kiểm. Nó không tính là có hàng, cũng không tính
là hết hàng.

**Trạng thái kệ của mỗi SKU.**
- Mỗi SKU có mức đã xác nhận L (số đơn vị) và trạng thái: OOS khi L = 0, LOW khi 1 ≤ L ≤ 2, IN STOCK khi L > 2.
- Trạng thái chỉ đổi khi 2 lần kiểm được tính liền nhau cùng chỉ một hướng. Nhờ vậy, một khách đứng che kệ trong một
  lần kiểm không sinh sự kiện.
- Gọi x1, x2 là 2 lần kiểm được tính gần nhất của SKU. Xét các dòng theo thứ tự, và mỗi lần kiểm sinh nhiều nhất 1
  sự kiện:

| Sự kiện | Khi | Ghi |
| --- | --- | --- |
| OOS | x1 = x2 = 0, và L > 0 | "0 units (−L)"; L = 0 |
| LOW STOCK | 1 ≤ x1 ≤ 2, 1 ≤ x2 ≤ 2, và L > 2 | "n left (−Δ)"; L = max(x1, x2) |
| DEPLETED | x1 ≤ L − 3, x2 ≤ L − 3, và cả hai ≥ 3 | "−Δ (n left)"; L = max(x1, x2) |
| RESTOCKED | x1 ≥ L + 2 và x2 ≥ L + 2 | "+Δ (n total)"; L = min(x1, x2) |

Quy tắc kèm theo:
- Nếu không có sự kiện mà x1 = x2, thì L = x2. Nhờ vậy L bám theo mức thật khi khách lấy lẻ từng hộp.
- Lần đầu có x1 = x2 cho một SKU (mới thêm vào danh sách, hoặc trạng thái vừa được tính lại): đặt L = x2 và trạng thái
  theo L, không sinh sự kiện.
- Thời điểm của sự kiện là đầu lần kiểm x1.
- Một lần OOS kết thúc ở sự kiện RESTOCKED kế tiếp. Thời gian hết hàng chỉ tính các phút trong giờ mở cửa.

**Các số:**
- **OSA** = số lần kiểm được tính có ít nhất 1 đơn vị, chia cho tổng số lần kiểm được tính, trong khoảng thời gian
  chọn. Đếm theo từng cặp SKU × lần kiểm.
- **Out-of-Stock** (tab xu hướng) = số lần OOS bắt đầu trong mỗi ngày.
- **Đang hết hàng** = số SKU đang ở trạng thái OOS, tính đến lần kiểm cuối. Trang ghi giờ của lần kiểm đó.
- **Restock Volume** = tổng Δ của các sự kiện RESTOCKED.
- **Restock Rate (vs Last Cycle)** = số đơn vị được bổ sung mỗi ngày trong khoảng chọn, so với khoảng liền trước có
  cùng độ dài, tính bằng % thay đổi.
  - "Last cycle" là khoảng liền trước đó.
  - Khoảng chọn mặc định là 14 ngày, đúng chu kỳ 2 tuần của Datagent.
  - Với Today, khoảng liền trước là hôm qua, tính tới cùng giờ.
  - Khoảng liền trước không có lần kiểm, hoặc không có lần bổ sung nào, thì ô hiện "—".
- **Total Stock Units** (tab xu hướng) và biểu đồ cột **Shelf Stock Count** = tổng đơn vị của các SKU phải có, lấy
  trung bình qua các lần kiểm được tính.
  - Biểu đồ cột chuyển sang số này để hai chỗ khớp nhau.
  - Hiện biểu đồ cột dùng `units_found` của mọi capture, gồm cả ban đêm và cả hàng không nhận ra.
- **Top 50 SKU Accuracy** = KPI #1 `sku_identification_accuracy` trong khoảng chọn, tính từ các khung team đã chấm ở
  trang Model.
  - Chưa có danh sách top 50 của Datagent thì tính trên mọi SKU và ghi rõ trên ô, đúng như NHAT-P01 đã chốt ngày 21/11.
  - Ô ghi kèm số khung n.
- **Detection Accuracy** (tab xu hướng) = KPI #2 `overall_identification_accuracy` theo ngày, cùng nguồn với Top 50.
- **Recent Shelf Activities** = các sự kiện trong bảng trên, mới nhất trước. Bộ lọc:
  - All;
  - Alerts only: OOS, LOW STOCK, DEPLETED;
  - Restocked.

### 2. Kế hoạch kệ của tiệm (Settings)

- **Trường mới** trên mỗi mục `store_list` *(đề xuất; không có trong Data Dictionary)*:
  - `open_time`, `close_time`: dạng "HH:MM", giờ UTC+7, một khoảng dùng cho mọi ngày, giờ đóng phải sau giờ mở;
  - `expected_skus`: danh sách `sku_id`;
  - `shelf_plan_updated_by`, `shelf_plan_updated_at`.
- **Chưa lưu danh sách:** dùng danh sách gợi ý. Danh sách gợi ý là các SKU có ít nhất một hộp với độ tin cậy ≥ 0.70
  trong 7 ngày gần nhất ở tiệm đó, tính từ `captures` bằng `capture_boxes` của `backend/model_health.py`. Dashboard
  và Settings ghi rõ danh sách là "automatic".
- **Chưa đặt giờ mở cửa:** OSA, hết hàng, sự kiện và số bổ sung của tiệm đó tạm tắt. Ô hiện "Set this store's opening
  hours in Settings". Vì sao: giờ mặc định sai sẽ sinh hết hàng giả, như đêm 23/11.
- **Khối mới "Shelf plan" trong Settings**, mỗi tiệm một khối:
  - giờ mở và giờ đóng;
  - danh sách SKU nhóm theo hãng · dòng như trang Products. Mỗi SKU có ô chọn và nhãn "seen in the last 7 days".
  - nút "Use suggestion".

  team_admin sửa và lưu; các nhóm khác chỉ xem.
- **Lưu xong** thì tính lại 15 ngày gần nhất của tiệm đó (mục 4).
- **Tìm camera của tiệm:** lấy các `camera_id` trong `latest_stock` có `store_id` đó. Mã tiệm trong `capture_id`
  (`CAP-<mã>-…`) lấy theo cách hàm `cameras()` của Lambda ingest đang làm.

### 3. Bảng mới (DynamoDB, cùng kiểu các bảng hiện có)

**`milk-backend-<env>-shelf`** (PK `store_id`, SK `key`):
- **`state`:**
  - map SKU → {L, status, since, last: [x1, x2]};
  - `last_bucket`: lần kiểm cuối đã xử lý.
  - Không có TTL.
- **`check#YYYYMMDD-HHMM`**, mỗi lần kiểm một item:
  - map SKU → số đơn vị;
  - số capture và các camera;
  - `open`: lần kiểm có nằm trong giờ mở cửa không.
  - TTL 15 ngày, đủ để tính lại một chu kỳ khi kế hoạch kệ thay đổi.
- **`hour#YYYYMMDD-HH`** và **`day#YYYYMMDD`:**
  - map SKU → {checks, available, units_sum, oos_started, restock_units, restock_events}, chỉ cộng các lần kiểm được
    tính;
  - `max_total`: tổng đơn vị các SKU phải có cao nhất trong một lần kiểm, tính cho cả tiệm.
  - TTL 90 ngày, như model-health.

**`milk-backend-<env>-shelf-events`** (PK `store_id`, SK `YYYYMMDD-HHMM#sku_id#type`):
- Mỗi sự kiện gồm type, sku_id, at, delta, level_before, level_after. Riêng sự kiện RESTOCKED kết thúc một lần OOS có
  thêm duration_min.
- Khoá cố định theo thời điểm, SKU và loại, nên ghi lại không sinh bản trùng.
- TTL 90 ngày.

### 4. Tính (Lambda ingest)

**Lịch mới.** EventBridge chạy `rate(5 minutes)` và gọi `{"action": "shelf_tick"}`. Với mỗi tiệm:
- Xử lý các lần kiểm đã đóng ít nhất 2 phút, để chờ các capture đến trễ.
- Đi từ sau `last_bucket` tới hiện tại, tối đa 36 lần kiểm mỗi lượt (3 giờ). Sau một sự cố, các lượt sau đuổi kịp dần.

**Mỗi lần kiểm:**
1. Đọc capture của các camera của tiệm trong 5 phút đó, bằng Query `capture_id` between, giống `captures_in_hour`.
2. Ghi item `check#…`.
3. Nếu lần kiểm được tính (đã đặt giờ mở cửa và có danh sách), chạy phần trạng thái ở mục 1 rồi ghi các sự kiện.
4. Ghi lại `state` với điều kiện `last_bucket` vẫn bằng giá trị cũ. Nếu hai lượt chạy chồng nhau, một lượt sẽ bị bỏ.
5. Tính lại item `hour#` của giờ đó từ các `check#` trong giờ, và item `day#` từ các `hour#` trong ngày. Dùng SET,
   không dùng ADD, nên chạy lại vẫn ra cùng kết quả.

Lần kiểm ngoài giờ mở cửa vẫn lưu `check#` với `open = false`, nhưng không đổi trạng thái kệ.

**Tính lại.** `{"action": "shelf_recompute", "store_id": …, "days": 15}`:
- Xoá `state`, các `hour#`, `day#` và sự kiện của tiệm trong khoảng đó.
- Tính lại từ các `check#`. Phần nào còn trong 7 ngày mà thiếu `check#` thì lấy từ `captures`.
- Khi lưu kế hoạch kệ, API đặt cờ `shelf_recompute_requested_at` trên mục `store_list`. Lượt `shelf_tick` kế tiếp,
  trong vòng 5 phút, tính lại rồi xoá cờ. Cách này không cần cho Lambda API quyền gọi Lambda ingest. Khi triển khai
  thì chạy tay một lần.

Phần logic thuần (dựng lần kiểm, trạng thái kệ, gộp theo giờ và ngày) để trong một module riêng không gọi AWS, giống
`backend/model_health.py`.

### 5. API (Lambda API)

- **`GET /v1/stores/{store_id}/shelf-plan`**, mọi nhóm đã duyệt: trả giờ mở cửa, danh sách đang dùng, nguồn
  ("saved" hoặc "suggested"), và danh sách gợi ý kèm lần thấy gần nhất của từng SKU.
- **`PUT /v1/stores/{store_id}/shelf-plan`**, chỉ team_admin: kiểm tra giờ hợp lệ và `sku_id` có trong SKU master, lưu,
  rồi gọi tính lại.
- **`GET /v1/kpi?days=&store_id=&category=`**, mặc định `days=14`. Thêm các trường:
  - `osa` {value, previous}
  - `restock_rate` {units_per_day, previous_units_per_day, change_pct}
  - `oos_now` {count, as_of}
  - `top_50_sku_accuracy` {value, n_frames, scope_note}
  - với mỗi ô, một `blocked_reason` nếu thiếu giờ mở cửa, thiếu danh sách hay thiếu dữ liệu.

  Các trường đang có giữ nguyên nghĩa, vì trang Home cũng đọc chúng. Chỉ các trường mới theo `days`, `store_id` và
  `category`.
- **`GET /v1/reports/trends?metric=total_stock|oos|accuracy|restock_volume&days=&store_id=&category=`**: trả danh sách
  {date hoặc hour, value}. Với `days=1` thì theo giờ.
- **`GET /v1/shelf-events?days=&store_id=&category=&kind=all|alerts|restocked&limit=&cursor=`**
- **`GET /v1/reports/series`**: đọc từ các item `day#` thay vì quét `captures`. Mỗi ngày trả:
  - `avg_units`: tổng đơn vị các SKU phải có, trung bình theo lần kiểm được tính;
  - `max_units`: lấy từ `max_total`;
  - `checks`: thay cho `captures`.
- Lọc theo category dùng cột `category` của SKU master. Với "All stores", gộp kết quả từ các tiệm.

### 6. Trang Dashboard

- **Bộ lọc:**
  - Timeframe: Today, Last 7 days, Last 14 days (one cycle; mặc định), Last 90 days.
  - Store.
  - Category: All, Milk, Snacks.

  Mọi ô và biểu đồ theo bộ lọc, trừ "Total On-Shelf Units": ô này là số hiện tại và có nhãn "now".
- **Ô OSA:** % kèm "±x pts vs the previous 14 days" và sparkline theo ngày.
- **Ô Top 50 SKU Accuracy:** % kèm "from n frames the team labelled; all SKUs until Datagent sends its top-50 list".
- **Ô Restock Rate:** ±% kèm "x units/day vs y" và sparkline.
- **Mỗi ô và mỗi tab** có một dòng nói ô đo gì, theo đúng định nghĩa ở mục 1. Làm giống Live health.
- **Trends & Insights**, cả 4 tab có số thật:
  - Total Stock theo ngày, hoặc theo giờ khi chọn Today;
  - Out-of-Stock: số lần hết hàng bắt đầu mỗi ngày;
  - Detection Accuracy theo ngày, kèm n khung;
  - Restock Volume theo ngày.
- **Recent Shelf Activities:** 20 sự kiện mới nhất theo bộ lọc. Nút "View all activity" mở danh sách đầy đủ, có chia
  trang.
- **Ô chưa có số:** nói thiếu gì và ai làm. Ví dụ:
  - "Set opening hours for DEMO-S01 in Settings";
  - "Label frames on the Model page";
  - "Needs two 14-day periods of data; first comparison on dd/mm".

### 7. Kiểm thử

- **pytest, phần logic thuần:**
  - dựng lần kiểm: lấy trung vị, SKU vắng tính 0, nhiều camera thì cộng;
  - trạng thái kệ: mỗi dòng trong bảng ở mục 1 có một test;
  - khách che kệ trong 1 lần kiểm thì không sinh sự kiện;
  - lần đầu thấy SKU thì không sinh sự kiện;
  - OSA bỏ lần kiểm ngoài giờ và SKU ngoài danh sách;
  - gộp theo giờ và theo ngày.
- **pytest + moto:**
  - `shelf_tick` chạy 2 lần liền vẫn ra cùng kết quả;
  - lần kiểm đóng chưa đủ 2 phút thì chưa xử lý;
  - tính lại sau khi đổi danh sách;
  - các API kpi, trends, shelf-events, shelf-plan, và quyền team_admin khi PUT.
- **node --test:** định dạng các số và dấu ±.
- **Trình duyệt** (như `ui_check`):
  - Dashboard của tiệm chưa đặt giờ: các ô chỉ đường sang Settings;
  - lưu kế hoạch kệ bằng tài khoản team_admin;
  - Dashboard sau khi đã tính lại.

### 8. Triển khai

1. Change set CloudFormation (`--tags project=milk-demo`): thêm 2 bảng, lịch 5 phút, biến môi trường và quyền cho cả
   2 Lambda.
2. Cập nhật code 2 Lambda, rồi deploy Amplify.
3. team_admin đặt giờ mở cửa và danh sách cho DEMO-S01. Việc lưu tự tính lại 15 ngày. Dữ liệu thật chỉ có từ 22/11, và
   capture chỉ giữ 7 ngày.
4. Chi phí: lịch 5 phút là khoảng 8 700 lượt Lambda mỗi tháng. Với 1 tiệm, mỗi ngày thêm khoảng 300 item `check#` và
   vài chục item tổng hợp.

## Để người làm tự quyết

- Tên trường JSON của API và kích thước một trang.
- Cấu trúc component và kiểu biểu đồ, bám theo Figma.
- Logic thuần nằm trong một hay nhiều file.
