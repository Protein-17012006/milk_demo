# Hàng còn trong khung thì vẫn đếm; không thấy thì ghi "không thấy" — thiết kế

Ngày 28/11/2026. Trạng thái: hoang duyệt hành vi ngày 28/11 (*"ok duyệt"*); bản thiết kế này chờ duyệt.

Liên quan:
- `2026-11-24-reliability-design.md` mục 1.1: phép kiểm "thấy tủ" (`MILK_DISPLAY_ZONE`), lần kiểm đo được, khoảng
  trống, tính lại 15 ngày.
- `2026-11-24-dashboard-shelf-metrics-design.md`: lần kiểm 5 phút, trạng thái kệ, sự kiện, OSA.
- `2026-11-26-website-feature-review-design.md` và các đợt tối ưu 1–3: bảng "On the shelf now" trên Dashboard.
- `2026-11-27-operations-loop-design.md`: chạy song song, luật ban đêm của bộ chạy thử.

## 1. Vì sao làm

**Chuyện ngày 28/11.** Khoảng 12:12 tiệm dời các khay Slide sang mép trái khung hình, đặt trên kệ MILO, phủ ni-lông
lên bàn chính (nền ướt, có lẽ do mưa).
- Phép kiểm "thấy tủ" chỉ nhìn một vùng cố định (`MILK_DISPLAY_ZONE`: x 860–1480, y 120–640 trên khung 2560×1440).
  Điểm giống rơi từ 0,91 (12:10:29) xuống 0,50 (12:15:04) rồi 0,46 (13:05), dưới ngưỡng 0,6. Từ 12:15:04 mọi capture
  mang `display_visible = false`.
- Model vẫn đếm được 12–18 lon Slide ở chỗ mới (lúc 13:05 các hộp nằm ở x 128–337). Hai model đọc cả khung hình:
  worker không đặt `MILK_ROI`, adapter Slide và adapter milk/TH không cắt vùng nào.
- Khay TH, nơi model đọc 6 hộp lúc 12:10 (x 828–875, y 98–142), không còn ở đó lúc 13:05 (chỗ đó là nải chuối); tôi
  không tìm thấy nó ở phần còn lại của khung.
- Dashboard bỏ mọi lần đọc từ 12:15: OSA, hết hàng và bổ sung hàng không được đo, bảng "On the shelf now" đứng ở số
  lúc 12:10. Không có báo hết hàng sai (`oos_now` = 0).
- Phép kiểm không tự theo được chỗ mới: nó chỉ học ảnh mẫu từ capture có ít nhất 3 hộp độ tin cậy ≥ 0,8 *nằm trong
  vùng*.

**hoang nói ngày 28/11:**
- *"miễn là vẫn trong khung hình thì vẫn phải hiển thị hàng"*.
- Với hàng không còn trong khung: chọn ghi "không thấy" thay vì hết hàng, *"giải quyết lâu dài"*.
- Duyệt các tình huống ở mục 4 (*"ok duyệt"*).

Mục đích của website (hoang, 26/11): xem trên kệ đang có gì. Camera vẫn thấy hàng mà Dashboard đứng là trái mục đích
đó.

## 2. Hiện trạng

- **Worker** (`server/milk/display.py`) tính `display_score` và `display_visible` cho mỗi capture; worker và hub
  không cần đổi gì trong thiết kế này.
- **Capture** (bảng `milk-backend-development-captures`) lưu mọi hộp kèm `sku_id`, `conf` và `box` (pixel trên khung
  2560×1440) trong `detections_json`, cùng `display_visible` và `display_score`. Capture được giữ 7 ngày
  (`CAPTURE_TTL_DAYS`).
- **Nơi đọc cờ "thấy tủ"** (`shelf.sees_display` hoặc `display_visible`):
  - ingest, mỗi capture: cập nhật `latest_stock` và hàng chờ duyệt, đếm lùi sản phẩm vắng mặt (`_count_down_missing`),
    ghi trạng thái camera `display#<camera>` (`_record_display`);
  - ingest, mỗi 5 phút (`shelf_tick`, `shelf_recompute`): `build_check` đánh dấu cả lần kiểm là đo được hay không;
  - ingest, mỗi giờ: khung huấn luyện TRN chỉ lấy capture thấy tủ; nhánh phần 3 thêm phục vụ yêu cầu khung
    (`serve_label_request`) cũng bỏ capture không thấy tủ;
  - API `/kpi`: `displays` (dòng "cannot see the display"), `coverage.display_away_hours`;
  - trang Model: `display_agreement` (độ khớp của phép kiểm vùng với người gán nhãn);
  - bộ chạy thử trên HUYHOANG: `ops/decide.py night_rate` coi capture `display_visible = false` là khung ban đêm.
- **Đo được hay không là của cả lần kiểm**, cho mọi sản phẩm cùng lúc. Chưa có khái niệm "sản phẩm này không thấy".
- **Bảng "On the shelf now"** lấy số từ `latest_stock` (GET `/products`); trạng thái là `shelf.status_of(units)` (OOS
  ở 0, LOW ở 1–2, IN_STOCK trên đó). Thẻ "Out of stock now" lấy từ trạng thái kệ của lần kiểm cuối.

## 3. Mục tiêu

**Làm:**
1. Hàng còn trong khung thì vẫn được đếm và hiện, dù tủ bị dời khỏi vùng cũ.
2. Sản phẩm mà hệ thống không biết chỗ của nó có đang trong khung hay không thì hiện **Not in view**, kèm từ lúc nào
   và lần cuối thấy bao nhiêu; không tính vào OSA, không sinh sự kiện, không tính là hết hàng.
3. Dời tủ không sinh sự kiện giả (hết hàng, giảm mạnh, bổ sung hàng), lúc dời đi cũng như lúc dời về.
4. Ban đêm và sáng sớm chưa bày tủ vẫn là "không đo được" như hiện nay.
5. Tính lại 15 ngày qua theo luật mới.

**Không làm:**
- So hình dạng từng chỗ đặt hàng để phân biệt khay trống với khay bị dời.
- Dạy model nhận lon chỉ thấy nắp ở tầng dưới (việc của phần 4, train lại).
- Sửa phép kiểm vùng trong worker, hay đổi `MILK_DISPLAY_ZONE`.
- Đổi số đo `display_agreement` trên trang Model: nó vẫn đo riêng phép kiểm vùng.
- Thêm dòng báo "tủ đã dời" trên Dashboard.

**Không được xảy ra:**
- Báo hết hàng sai vào ban đêm hoặc sau khi dời tủ.
- Ghi "bổ sung hàng" khi tủ được dời về chỗ cũ.
- Mất một lần hết hàng mà luật cũ báo đúng khi tủ đứng yên ở chỗ quen.
- Dashboard lại đứng trong lúc hàng vẫn nằm trong khung.

## 4. Hành vi đã duyệt (28/11)

Nguyên tắc: hệ thống chỉ nói "hết hàng" khi nó biết chỗ của sản phẩm đang nằm trong khung; không biết thì nói "không
thấy".

1. Tủ ở chỗ cũ, Cheese bán hết → **Out of stock**, như hiện nay.
2. Tủ bị dời như trưa 28/11: 4 vị Slide hiện số lon đếm được ở chỗ mới; TH hiện **Not in view since 12:15** và không
   tính vào OSA trong lúc đó.
3. Ở chỗ mới, Cheese đã được thấy rồi sau đó bán hết → **Out of stock**.
4. Ban đêm, sáng sớm chưa bày → không đo, như hiện nay.
5. Sáng hôm sau bày lại đúng chỗ cũ → tính tiếp như hôm trước (sản phẩm hết từ hôm qua vẫn Out of stock). Bày ở chỗ
   mới → như tình huống 2. "Đổi chỗ" là vị trí các lon trong khung nhảy xa; người đứng che một lúc không tính.
6. Lúc đổi chỗ không ghi sự kiện giảm mạnh hay bổ sung hàng giả.

Cái giá hoang đã chấp nhận: sản phẩm hết hàng đúng lúc đang "không thấy" thì không bị báo hết hàng; Dashboard chỉ cho
thấy nó "không thấy từ …".

Bảng "On the shelf now" khi đó (số của ảnh 13:05):

```
Slide Sour Cream    7   IN STOCK
Slide Cheese        3   IN STOCK
Slide Original      3   IN STOCK
Slide Hot & Spicy   2   LOW STOCK
TH true MILK        –   NOT IN VIEW since 12:15 · last seen 6 at 12:10
```

## 5. Đo trên dữ liệu thật (28/11, chỉ đọc)

**Luật "thấy kệ"** = vùng cũ khớp, **hoặc** có ít nhất 3 hộp mang tên sản phẩm với độ tin cậy ≥ 0,8 ở bất kỳ đâu
trong khung. Thử trên 5.492 capture của 24–28/11:

| Nhóm capture | Số capture | Luật mới đổi |
|---|---|---|
| Sau khi dời tủ (28/11 từ 12:15) | 167 | 167 thành "thấy kệ" |
| Phép kiểm vùng nói "tủ đã cất" (trước 28/11 12:15) | 972 | 4 thành "thấy kệ": 25/11 06:50, 26/11 15:45 (×3) |
| Phép kiểm vùng nói "thấy tủ" | 3.878 | không đổi (99,2% cũng đạt luật 3 hộp) |

- Hai trong bốn capture đổi đã được xem bằng mắt: tủ vẫn ở chỗ cũ, bị người đứng che (25/11 06:50, điểm 0,596) hoặc
  bị tấm ni-lông che (26/11 15:45, điểm 0,589). Luật mới sửa đúng chỗ phép kiểm vùng sai.
- Không capture ban đêm nào đổi: hộp giả do đèn xe có độ tin cậy thấp (256 capture "tủ đã cất" có ≥ 3 hộp bất kỳ,
  chỉ 4 có ≥ 3 hộp ở ≥ 0,8).

**Vị trí các lon** = trung vị tâm các hộp ≥ 0,8 của mỗi capture, rồi trung vị theo lần kiểm 5 phút. 656 lần kiểm của
22–28/11:
- Hai lần kiểm liền nhau (≤ 30 phút): xê dịch trung vị 14 px, p90 44, p99 186. Lớn nhất 399 px (27/11 12:00–12:10,
  vị trí lệch rồi về lại chỗ cũ; chưa xem ảnh), trừ lần dời tủ 28/11 12:10 → 12:15: **795 px**.
- Lần đo đầu buổi sáng so với lần đo cuối tối hôm trước: 19–180 px (5 đêm).
- Ngưỡng đổi chỗ **500 px** tách lần dời thật khỏi mọi xê dịch khác của 7 ngày.

## 6. Các cách đã cân nhắc

**Về hành vi** (hoang chọn):
- A. Sản phẩm không thấy tính là hết hàng: đơn giản, nhưng báo sai khi khay chỉ bị dời ra ngoài góc camera. hoang
  không chọn.
- B chỉ xét lúc tủ không ở vùng cũ (Cheese ở tình huống 3 cũng thành "không thấy"): đơn giản hơn, nhưng không đúng với
  lần dời sau và cửa hàng khác. Tôi bỏ vì hoang muốn giải quyết lâu dài.
- **B theo "cách bày"** (mục 4): chọn.

**Về cách làm:**
- **Tính ở backend từ dữ liệu đã lưu** *(tôi chọn; hoang để tôi quyết cách làm)*. Worker giữ nguyên, không phải khởi
  động lại, nên lần chạy song song không bị ảnh hưởng. Tính lại được 15 ngày. Trạng thái kệ vốn là của cả cửa hàng
  và nằm ở backend.
- Để worker quyết định: phải sửa và khởi động lại worker đang chạy song song; chỉ áp dụng cho dữ liệu mới; worker chỉ
  thấy một camera. Bỏ.
- So hình dạng từng chỗ đặt hàng: cần ảnh mẫu khay trống và khay bị dời mà mình chưa có; hành vi đã duyệt không cần.
  Bỏ.

## 7. Thiết kế

### 7.1 Hai luật chung (`backend/shelf.py`, hàm thuần)

- `sees_shelf(capture)`: `display_visible` không phải `false`, **hoặc** capture có ít nhất `PRODUCTS_MIN_BOXES = 3`
  hộp có `sku_id` với `conf ≥ PRODUCTS_MIN_CONF = 0.8`. Capture cũ không có `display_visible` vẫn là thấy, như nay.
- `products_position(captures)`: trung vị (x, y) tâm các hộp có `sku_id` và `conf ≥ 0.8` của mỗi capture đạt luật 3
  hộp, rồi trung vị theo các capture; `None` khi không capture nào đạt. Tâm hộp = (x + w/2, y + h/2) với
  `box = [x, y, w, h]`.
- `ARRANGEMENT_JUMP_PX = 500`: hai vị trí cách nhau hơn mức này là đổi cách bày. Khung của CAM-S01-A là 2560×1440;
  capture không mang kích thước khung nên ngưỡng tính bằng pixel.
- `sees_display` giữ tên cho phép kiểm vùng (trang Model vẫn dùng); mọi chỗ ở mục 7.3–7.6 chuyển sang `sees_shelf`.

### 7.2 Lần kiểm 5 phút (`build_check`)

- Chỉ capture `sees_shelf` được dùng để đếm. Lần kiểm đo được khi ít nhất một nửa số capture `sees_shelf`; ngược lại
  `measurable = false`, lý do `display_not_visible` như nay.
- Thêm vào lần kiểm:
  - `positions`: `{camera_id: [x, y]}` của từng camera có vị trí;
  - `confident_by_camera`: `{camera_id: [sku, …]}`, các SKU có hộp ≥ `CONFIDENT` (0,70) theo từng camera
    (`confident_skus` giữ nguyên là hợp của chúng);
  - `captures_zone`: số capture qua phép kiểm vùng, để xem lại.
- Lần kiểm cũ hơn 7 ngày (đọc từ bảng khi tính lại) không có `positions`: không bao giờ là đổi cách bày.

### 7.3 Cách bày và sản phẩm "không thấy" (`_apply_check`, trạng thái `state`)

- `state` thêm `arrangements: {camera_id: {"position": [x, y], "since": bucket}}`.
- Mỗi lần kiểm đo được, trong giờ mở cửa, với từng camera có vị trí:
  - chưa có cách bày: bắt đầu một cách bày (`since` = lần kiểm này), không đổi gì khác;
  - vị trí cách vị trí của cách bày hơn 500 px: **đổi cách bày** (`since` = lần kiểm này);
  - ngược lại: cùng cách bày; vị trí của cách bày lấy theo lần kiểm này, để theo được xê dịch chậm.
- So qua khoảng trống (ban đêm, hub tắt) như hai lần kiểm liền nhau: lần đo đầu buổi sáng so với vị trí cuối buổi tối.
- Trạng thái của mỗi SKU thêm `in_view` (mặc định `true`, gồm cả trạng thái cũ không có trường này),
  `not_in_view_since`, `last_seen_units`, `last_seen_at`, và `camera` (camera của lần đếm chắc chắn gần nhất).
- **Khi camera C đổi cách bày:** mọi SKU đang có trạng thái mà `camera` = C (hoặc chưa có `camera`) được đặt lại về
  trạng thái trống, không sinh sự kiện. Đây là cách giữ mục tiêu 3: số lon nhìn thấy đổi vì góc nhìn, không phải vì
  bán.
  - SKU được đếm với hộp chắc chắn ngay ở lần kiểm này: `in_view = true`, bắt đầu lại như SKU mới (hai lần kiểm bằng
    nhau đầu tiên đặt mức, không sự kiện; quy tắc sẵn có của `step_state`).
  - SKU còn lại: `in_view = false`, `not_in_view_since` = lần kiểm này, `last_seen_units` = mức `L` trước khi đặt lại
    (hoặc số đếm cuối `prev` nếu chưa có mức), `last_seen_at` = `prev_bucket` của nó (lần kiểm cuối đã tính SKU đó).
- **SKU `in_view = false`:** không chạy `step_state`, không sự kiện, không tính vào OSA. Trạng thái báo ra là
  `NOT_IN_VIEW`.
- **Thấy lại:** ở một lần kiểm đo được, SKU được đếm với hộp ≥ 0,70 (có trong `confident_by_camera` và số đếm > 0) thì
  `in_view = true`, xoá `not_in_view_since`, bắt đầu lại như SKU mới.
- SKU vào kế hoạch kệ (`joined`) sau khi đổi cách bày vẫn theo luật hiện nay (`in_view` mặc định `true`).
- Nhiều camera *(tôi chốt)*: mỗi camera một cách bày; SKU chỉ đổi theo camera đã đếm chắc chắn nó gần nhất. Cửa hàng
  hiện có một camera.
- Lần kiểm ghi thêm `not_in_view: [sku, …]` (SKU dự kiến mà không thấy ở lần đó) và `arrangement_changed: true` khi có
  đổi cách bày.

### 7.4 Tổng hợp theo giờ, ngày (`rollup`, `merge`, `totals`)

- SKU dự kiến nằm trong `not_in_view` của lần kiểm: không cộng `checks` hay `available`; cộng vào trường mới
  `unseen_checks` của SKU.
- `unmeasured_checks` (giờ "display not in view") nay chỉ còn lần kiểm không thấy kệ.
- OSA = `available / checks` như nay; giờ "không thấy" của một SKU tự rơi khỏi mẫu số.

### 7.5 Ingest, mỗi capture

- `latest_stock`, hàng chờ duyệt và `_record_display` dùng `sees_shelf`. Dòng `display#<camera>` vì vậy nghĩa là
  "camera thấy kệ"; Dashboard chỉ còn báo "cannot see the display" khi không thấy gì.
- `_count_down_missing` *(tôi chốt)*:
  - không đếm lùi SKU mà `state` ghi `in_view = false`;
  - khi vị trí của capture (luật 3 hộp) cách vị trí cách bày của camera trong `state` hơn 500 px thì không đếm lùi SKU
    nào. Lượt 5 phút kế tiếp sẽ quyết. Nhờ vậy sản phẩm bị bỏ lại sau khi dời không hiện "Out of stock" trong mấy phút
    trước khi thành "Not in view". Trong khoảng đó chúng giữ số cuối cùng.
  - Đọc `state` một lần mỗi capture.
- Khung huấn luyện TRN mỗi giờ và `serve_label_request` (phần 3) dùng `sees_shelf`: ảnh ở chỗ mới được lấy làm khung
  huấn luyện.

### 7.6 API

- `/products`: với SKU thuộc kế hoạch kệ mà trạng thái kệ của cửa hàng ghi `in_view = false` → `stock_status:
  "NOT_IN_VIEW"` và `not_in_view: {since, last_units, last_at}` (giờ ICT). `unit_count` giữ như nay. Một SKU có ở
  nhiều cửa hàng: `NOT_IN_VIEW` chỉ khi không cửa hàng nào có nó trong khung; khi API lọc theo một cửa hàng thì dùng
  trạng thái của cửa hàng đó.
- `/kpi`: `oos_now` không đổi code (SKU không thấy không mang trạng thái `OOS`, vì trạng thái của nó đã được đặt lại).
  `total_on_shelf_units` không cộng SKU `NOT_IN_VIEW`. OSA, coverage đi theo mục 7.4.
- `/shelf-events`: không đổi.

### 7.7 Website

- `StockStatus` thêm `NOT_IN_VIEW`, nhãn **Not in view**, màu xám.
- Dòng của nó: ô số ghi "–"; dòng phụ "since 12:15 · last seen 6 at 12:10", hoặc "since 12:15 · was out of stock at
  12:10" khi số lần cuối là 0 *(tôi chốt)*. Ngày khác hôm nay thì thêm ngày, như `updatedText`.
- Thứ tự: Out of stock, Low, Not in view, In stock *(tôi chốt)*.
- Tổng dưới bảng: số lon không tính dòng Not in view; thêm "n not in view".
- Trang Category: cùng nhãn và màu ở chỗ đang hiện trạng thái tồn kho. Mọi chỗ hiện số lon của một SKU `NOT_IN_VIEW`
  đều ghi "–", không ghi số cũ.
- `displayBanner` không đổi code.

### 7.8 Luật ban đêm của bộ chạy thử (HUYHOANG)

- `ops/decide.py night_rate` chỉ tính khung mà bản live không thấy kệ: `display_visible = false` **và** dưới 3 hộp
  live có tên với độ tin cậy ≥ 0,8. Nếu không sửa, một bản thử đếm được nhiều lon hơn ở chỗ mới sẽ bị dừng oan.
- `ops` không import được `backend/`: chép hai con số, kèm test giữ chúng bằng với `shelf.py`.
- Triển khai bằng bundle như 28/11; chỉ khởi động lại task `milk-ops`, không đụng `milk-worker`.

### 7.9 Tính lại

- Sau khi deploy, đặt `shelf_recompute_requested_at` cho DEMO-S01. Lượt kế tiếp tính lại 15 ngày: 7 ngày có capture
  được tính từ capture, phần cũ hơn từ lần kiểm đã lưu. `shelf_recompute` chép thêm các trường mới của lần kiểm
  (`positions`, `confident_by_camera`, `captures_zone`) khi dựng lại, như nó đang chép `display_fields`; trạng thái
  cách bày bắt đầu trống.
- Báo hoang trước: OSA và sự kiện của 15 ngày sẽ đổi một chút, giờ "display not in view" giảm.

## 8. Ràng buộc

- Không đổi worker, hub, mẫu CloudFormation, bảng hay biến môi trường. Backend chỉ đổi code
  (`backend_changeset.sh`, không bao giờ `--tags` trên stack backend). Website qua Amplify.
- **Deploy sau khi đóng phần 1** (29/11, sau Put live và Roll back): bước kiểm một ngày của phần 1 cần Dashboard
  không đổi trong lúc chạy song song.
- Nhánh `feat/shelf-not-in-view` tách từ `feat/ops-loop-part3` (5d9608e), vì cả hai sửa `backend/ingest/handler.py`
  và `backend/api/handler.py`. Nếu phần 3 không được deploy trước, người làm rebase nhánh này lên phần 1 trước khi
  deploy.
- Lambda của tài khoản chỉ được chạy 10 bản cùng lúc. Lần tính lại 15 ngày ngày 24/11 mất khoảng 9 giây.
- Không dùng dữ liệu giả. Kiểm trên capture thật.

## 9. Xong khi

1. Test đơn vị cho `sees_shelf`, `products_position`, đổi cách bày (gồm qua đêm, người che, dời đi rồi dời về),
   `NOT_IN_VIEW`, rollup, `_count_down_missing`, `/products`, `night_rate`, và các hàm `shelf-now` của website. Bộ test
   backend, ruff, cfn-lint, test frontend, `tsc` và build đều qua.
2. **Chạy lại chỉ đọc trên capture 21–28/11**, chạy trước khi deploy, kết quả báo hoang:
   - cách bày đổi đúng một lần mỗi lần dời thật (28/11 12:15, và lúc dời về nếu có), không lần nào khác;
   - từ 28/11 12:15: Slide được đo, TH là `NOT_IN_VIEW`, không sự kiện nào lúc 12:15;
   - không sự kiện hết hàng hay bổ sung hàng mới vào ban đêm;
   - giờ đo được, OSA và số sự kiện theo ngày, trước và sau.
3. Sau deploy, trên live: `/products`, `/kpi` và Dashboard (bước kiểm viewer `opt2_run.py`) đúng với tình trạng tủ lúc
   đó; hàng đợi lỗi trống; log ingest không lỗi.

## 10. Để người làm quyết

- Tên trường và cách chia code, miễn giữ đúng nghĩa ở mục 7.
- Cách đọc `state` trong ingest (một lần mỗi capture), cách viết test.
- Câu chữ trên website trong khuôn nghĩa của mục 7.7.

## 11. Các quyết định tôi tự đưa ra (để hoang xem lại)

1. Luật "thấy kệ": 3 hộp ở ≥ 0,8; ngưỡng đổi chỗ 500 px; "thấy lại" ở ≥ 0,70 (ngưỡng `CONFIDENT` sẵn có). Đều dựa trên
   số đo ở mục 5.
2. Đổi cách bày thì đặt lại trạng thái của mọi SKU trên camera đó, kể cả SKU vẫn thấy. Hệ quả: một lần hết hàng đang
   diễn ra khi dời tủ kết thúc không có sự kiện bổ sung hàng; dòng của nó ghi "was out of stock at …".
3. `in_view` mặc định `true`: ngoài lúc đổi cách bày, mọi thứ chạy như hiện nay.
4. Ingest không đếm lùi khi vị trí capture nhảy xa (mục 7.5).
5. Thứ tự dòng Not in view và câu "was out of stock at …".
6. Không có dòng "tủ đã dời" trên Dashboard; số đo `display_agreement` của trang Model giữ nguyên.
7. Sửa luật ban đêm của bộ chạy thử trong cùng đợt.
8. Làm trên nền phần 3, deploy sau khi đóng phần 1.
