# Slide: gộp các frame của một cửa sổ lấy mẫu và đọc vị bằng kho ảnh màu — thiết kế

Ngày 25/11/2026. Trạng thái: chờ hoang duyệt. Làm sau khi model TH (`2026-11-25-th-store-view-design.md`) đã lên live,
vì cả hai cùng sửa worker. Thay cho kế hoạch `docs/superpowers/plans/2026-11-24-reliability-part2-gallery.md` (kho ảnh
dùng embedding, chỉ cho Slide, không gộp frame).

## 1. Vì sao làm

**hoang yêu cầu ngày 25/11:**
- Hỏi có cách nào khác ngoài gắn nhãn để train, giúp model nhận ra nhiều hơn và đoán nhầm ít hơn. Ví dụ: hoang đếm
  được khoảng 18 bịch Slide trong khung hình mà model sót nhiều.
- "gpu còn vram nên có thể dùng thoải mái thử thêm như bạn đề xuất".
- Sau khi xem kết quả: "ok lên bản thiết kế".

**Thử nghiệm ngày 25/11** (chạy ngoài live; script scratchpad `slide_exp.py`, báo cáo
`C:\Users\huyho\Datagent\store_eval\slide_spike_20261125.json`):
- **Đáp án vẽ tay:** 18 keyframe, 196 lon, ở `C:\Users\huyho\milk_store_labels\slide\truth.json`.
  - Mỗi lon được ghi loại: thấy mặt, bị che, chỉ thấy nắp, hoặc bỏ qua.
  - Lon tầng dưới không tính, theo quy tắc gắn nhãn.
- **Đo:** 10 keyframe giữ riêng (121 lon), gồm tối 23/11 và sáng 25/11.
- **Kho ảnh:** 2.027 ảnh cắt từ 8 keyframe phía train, mỗi keyframe cắt ở nhiều frame cùng đoạn.

| Cách | Tìm thấy | Đúng vị | Sai vị | Box thừa | Nắp tìm thấy |
|---|---|---|---|---|---|
| Live: Slide v3, ngưỡng 0,25 | 86% | 71% | 18 | 0 | 29/45 |
| TTA / cân màu gray-world cả khung | không cải thiện | | | | |
| Ngưỡng 0,10 + kho ảnh dùng embedding của Long | 89% | 79% | 13 | 0 | 32/45 |
| Ngưỡng 0,10 + kho ảnh so màu | 89% | 85% | 5 | 0 | 32/45 |
| **6 frame cùng cửa sổ + ngưỡng 0,05 + kho ảnh so màu + thấy ở ≥ 3 frame** | **94%** | **89%** | 6 | 2 | **39/45** |

**Rút ra từ thử nghiệm:**
- **Model gần như không sót lon thấy mặt (60/61).** Lon bị sót chủ yếu là lon chỉ lộ nắp.
- **Lỗi lớn nhất là gọi sai vị:** Original bị gọi là Hot vào buổi chiều và Cheese vào buổi tối, ở độ tin cậy ≥ 0,9.
- **Giới hạn của thử nghiệm:**
  - tập đo nhỏ, thực chất khoảng 3 cách xếp;
  - phương án được chọn sau khi đã thấy số;
  - không có lon Hot nào trong các frame.

## 2. Mục tiêu, không làm, thất bại dù chạy

**Mục tiêu:**
1. Worker gộp các frame của mỗi cửa sổ lấy mẫu (30 giây, khoảng 6 frame) thành **một lần đọc**:
   - một lon được đếm khi xuất hiện ở cùng chỗ trong đủ số frame;
   - vị lấy theo phiếu bầu.
2. Mỗi box Slide được đọc lại vị bằng **kho ảnh màu** của chính camera đó. Kho lấy từ đáp án vẽ tay và từ các frame
   TRN mà team gắn nhãn trên website. Đây là vòng "label → model tốt hơn" mà hoang hỏi.
3. Số đúng vị trên tập giữ riêng tăng ít nhất 10 điểm so với live, không giảm số tìm thấy, và không vị nào tệ đi.

**Không làm lần này:**
- Train lại Slide. Việc này để sau, khi GPU rảnh, bằng ảnh thật như với TH.
- Ước lượng lon khuất hẳn.
- Tầng dưới.

**Thất bại dù vẫn chạy:**
- Đổi vị sang một vị mà kho ảnh chưa có (như Hot hiện nay).
- Hàng chờ review ngập vì các box ngưỡng thấp.
- Box "ma" chỉ hiện ở 1 frame mà vẫn được đếm.
- Mất khả năng quay lui chỉ bằng `worker.env`.
- Dùng frame AUD để dựng kho ảnh.

## 3. Ràng buộc

- **Worker** chạy trên HUYHOANG (task `milk-worker`). Vòng lặp trong `server/milk/counter.py` hiện xử lý từng frame:
  1. `pipeline.detect`;
  2. `build_capture` và `CountSmoother`;
  3. gửi `/internal/result` (xem live) và `/internal/persist` (lưu capture).
- **Lấy mẫu** (`sampling.py`, `MILK_SAMPLE_EVERY_S=300`, `MILK_SAMPLE_FOR_S=30`). Trong mỗi cửa sổ, `smooth_window - 1`
  frame đầu không được lưu.
- **Backend:**
  - ingest nhận từng capture, cập nhật `latest_stock` và hàng chờ review (dòng có độ tin cậy < 0,70);
  - `shelf_tick` lấy lower median các capture trong mỗi ô 5 phút;
  - lấy mẫu AUD/TRN chọn capture theo giờ.
- **Datagent:** dòng có độ tin cậy < 0,70 bị gắn cờ "Low Confidence".
- **Quay lui** chỉ bằng `worker.env`: tắt biến thì phải chạy y hệt hiện nay.
- **Ảnh tiệm và kho ảnh** không vào repo hay OneDrive.

## 4. Các cách đã cân nhắc

| Cách | Được | Mất |
|---|---|---|
| **1. Gộp trong worker (chọn)** | Worker có ảnh để đọc vị bằng kho ảnh. Mỗi cửa sổ gửi một capture, nên backend, Dashboard và trang Model không phải đổi cách đọc | Đổi vòng lặp chính của worker |
| 2. Gộp ở backend (`shelf_tick`) | Không đụng worker | Backend không có ảnh nên không đọc vị lại được. Box ngưỡng thấp sẽ tràn vào captures, `latest_stock` và hàng chờ review |
| 3. Chỉ train lại Slide bằng ảnh thật | Sửa tận gốc | Lâu; GPU đang train TH; script render Slide đã bị xoá. Bổ sung cho cách 1, không thay được |

Claude chọn cách 1. Cách 3 làm sau, và kho ảnh của cách 1 cũng dùng làm dữ liệu cho nó.

## 5. Thiết kế

### 5.1 Kho ảnh màu

**Đặc trưng của một box:**
- lấy phần giữa của box: 70% chiều cao, 60% chiều rộng;
- cân màu kiểu gray-world trên chính phần cắt đó;
- histogram Hue 18 × Saturation 8 trên HSV, lấy căn bậc hai từng ô, chuẩn hoá về độ dài 1 (vector 144 chiều).

Đúng như hàm `colour()` trong `slide_exp.py`.

**Nguồn ảnh:**
1. Đáp án vẽ tay (`truth.json`), chỉ các đoạn phía train. Mỗi box được cắt ở tối đa 30 frame cùng đoạn, giữ frame có vùng
   box giống keyframe (tương quan ≥ 0,85).
2. Frame TRN đã gắn nhãn trên trang Model (bảng `audits`, status `done`):
   - box `correct` → nhãn model;
   - `wrong_sku` → `true_sku_id`;
   - `not_product` → `none`;
   - `out_of_scope` → không dùng.
3. Script từ chối:
   - mọi frame `AUD-`;
   - frame thuộc cửa sổ giữ riêng (`training/store_view/segments.HOLDOUT`) khi dựng kho dùng để đo.

**Lưu trữ:**
- File `slide_gallery_<CAM>_<YYYYMMDD>.npz` gồm: đặc trưng, nhãn, nguồn (capture_id), `built_at`.
- Đặt trên HUYHOANG: `C:\Users\huyho\Datagent\slide_gallery\`.
- Worker đọc qua biến `MILK_SLIDE_GALLERY`.

**Luật đọc vị** (hàm thuần, có test):
1. Lấy 10 láng giềng gần nhất theo cosine.
2. Đổi vị khi thoả cả ba điều kiện:
   - một vị chiếm ≥ 0,6 tổng trọng số;
   - vị đó có ≥ 3 trong 10 láng giềng;
   - vị đó có ≥ 20 ảnh trong kho.
3. Nếu vị detector gán có < 20 ảnh trong kho (ví dụ Hot lúc này), giữ nguyên vị của detector, vì kho không đủ căn cứ để
   cãi.
4. Láng giềng gần nhất có nhãn `none` với độ giống ≥ ngưỡng tách: box bị bỏ.
   - Ngưỡng tách chọn trên phần val của phía train.
   - Nếu kho chưa có ảnh `none` thì bỏ qua bước này.

**Dựng kho:** script `training/store_view/slide_gallery.py`. Chạy trên laptop vì cần AWS để đọc bảng `audits` và tải ảnh
TRN, rồi chép sang HUYHOANG. Dựng lại bằng tay mỗi khi team gắn nhãn thêm frame TRN; tự động hoá để sau.

### 5.2 Gộp frame trong cửa sổ

**Module mới `server/milk/fusion.py`** (thuần, có test):
- `fuse(frames: list[list[Detection]], min_frames: int) -> list[FusedDetection]`;
- gom box theo vị trí: IoU ≥ 0,5 với tâm cụm;
- giữ cụm xuất hiện ở ≥ `min(min_frames, số frame của cửa sổ)` frame;
- box là trung vị của các box trong cụm;
- vị là phiếu bầu có trọng số độ tin cậy.

**Điểm của một lon sau gộp** = `tỉ lệ frame thấy nó × tỉ lệ phiếu của vị thắng`:
- thấy ở cả 6/6 frame và cùng một vị: điểm 1,0;
- thấy ở 3/6 frame và vị chia 60/40: điểm 0,3, bị gắn cờ.

Điểm này thay cho điểm YOLO trong CV Output. Vì vậy cờ < 0,70 nghĩa là "không ổn định giữa các frame". Đây là quyết
định của Claude; điểm này cần hiệu chỉnh trong lần chạy song song (mục 5.4).

**`counter.py` khi `MILK_FUSE_WINDOW=1`:**
1. Mỗi frame trong cửa sổ được dò: Slide ở `MILK_SLIDE_CONF=0,05`, rồi đọc vị bằng kho ảnh trong `slide_adapter`.
   Box sữa giữ ngưỡng và database của chúng.
2. Detection được giữ trong bộ nhớ, frame không được lưu.
3. Khi cửa sổ đóng, hoặc khi đủ `MILK_FUSE_FRAMES` (mặc định 6), worker tạo **một capture**:
   - box sau gộp và các dòng CV Output tính từ chúng;
   - ảnh là frame giữa cửa sổ, đã làm mờ người;
   - `display_visible` theo đa số frame;
   - trường mới `frames_fused` (số frame đã gộp).
4. `CountSmoother` không còn dùng trong chế độ này, vì gộp đã làm việc làm mượt.
5. Ảnh xem live (`/internal/result`) vẫn theo từng frame, nhưng chỉ vẽ box từ 0,25 trở lên cho dễ nhìn.

Gộp áp cho cả box sữa. Lon TH cũng phải thấy ở ≥ 3 frame, nhờ vậy loại được box "ma" kiểu cái chai trắng.

**Backend:**
- Mỗi cửa sổ có một capture thay vì khoảng 6, nên `shelf_tick` lấy đúng capture đó.
- Lấy mẫu AUD/TRN chọn capture đã gộp, nên trang Model chấm đúng thứ hệ thống báo ra.
- Ingest phải nhận được trường `frames_fused`, và trang Model hiện nó trong thông tin frame. Người làm kiểm
  `validate_capture_payload` cho phép trường lạ.

### 5.3 Phiên bản và đo

- **Phiên bản:** `MILK_MODEL_VERSION` thêm hậu tố, ví dụ `…+slide-v3+fuse6+galcol-<YYYYMMDD>`. Trang Model so theo phiên
  bản.
- **Cổng trước khi bật**, đo trên tập giữ riêng mở rộng: ≥ 20 keyframe, ≥ 3 ngày, có Hot nếu tiệm bày lại. Vẽ đáp án như
  `truth.json`.

| Chỉ số | Ngưỡng |
|---|---|
| Đúng vị | ≥ live + 10 điểm |
| Tìm thấy | ≥ live |
| Box thừa | ≤ 0,3 mỗi frame |
| Đúng vị của từng vị | không vị nào thấp hơn live quá 5 điểm |
| Phần box bị gắn cờ trong lần chạy song song | ≤ 25% |

### 5.4 Chạy song song rồi mới bật

1. **Chạy song song một ngày** (`MILK_FUSE_SHADOW=1`):
   - worker vẫn gửi như hiện nay;
   - đồng thời ghi kết quả gộp ra file cục bộ, `logs\fuse-shadow-YYYY-MM-DD.jsonl`;
   - so số mỗi cửa sổ với live và với nhãn AUD của ngày đó, và hiệu chỉnh điểm ở mục 5.2.
2. **Bật thật:** sau khi hoang OK, đặt `MILK_FUSE_WINDOW=1` và `MILK_SLIDE_GALLERY=…`, khởi động lại task.
3. **Quay lui:** xoá hai biến đó và khởi động lại. Worker chạy y hệt hiện nay (có test riêng cho điều này).

### 5.5 Để người làm tự quyết

- Cách giữ detection trong bộ nhớ.
- Frame dùng làm ảnh của capture (frame giữa hay frame nét nhất).
- Ngưỡng tách `none`.
- Định dạng file chạy song song.
- Cách so khớp nhãn TRN với box: theo `box_id` của audit.
- Cách viết test.

## 6. Để sau

- Train lại Slide bằng ảnh thật: lan nhãn theo đoạn như TH, cắt lon thật dán vào nền tiệm. Kho ảnh và đáp án của thiết
  kế này là dữ liệu cho bước đó.
- Tự động dựng lại kho ảnh mỗi đêm từ nhãn TRN mới.
- Đẩy frame mà review sửa vào hàng chờ gắn nhãn TRN (các ca khó).
- Vẽ khung cho lon bị sót trên trang Model, để nhãn có khung mà dùng train.
- Kho ảnh riêng cho mỗi camera khi có tiệm mới.
