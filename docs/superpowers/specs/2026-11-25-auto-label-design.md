# Tự động gắn nhãn cho camera tiệm: "thầy – trò" có kiểm chéo — thiết kế

Ngày 25/11/2026. Trạng thái:
- hoang duyệt ngày 25/11; phần 1 đã xây.
- Ngày 26/11 thêm mục 5.4b (dùng lại quyết định của người) và sửa cổng 1. Phần sửa này chờ hoang duyệt.

Liên quan:
- `2026-11-25-slide-fusion-gallery-design.md`: kho ảnh màu và luật đọc vị dùng chung.
- `2026-11-25-th-store-view-design.md`: cách chia đoạn và lan nhãn từ keyframe.

## 1. Vì sao làm

**hoang nêu ngày 25/11:**
1. Nhiều frame lặp lại, máy làm được phần đó thì đỡ phần lớn công.
2. Gắn được nhiều nhãn hơn.
3. Model cần đứng vững ở tiệm khác, cảnh khác. hoang đoán rằng nhiễu từ nhãn tự động có thể giúp việc này.
   - Đã thống nhất: nhiễu trên **ảnh** thì giúp, còn nhiễu trên **nhãn** thì dạy sai.

Hiện chưa có tiệm mới, nhưng hệ thống đang được xây theo hướng nhiều tiệm.

**Hiện trạng:**
- **TH:** 64 keyframe vẽ tay, lan nhãn ra 6.860 frame (`training/store_view/labels.py`).
- **Slide:**
  - Có 61 đoạn ban ngày nhưng chỉ 18 keyframe có đáp án (`truth.json`).
  - Model Slide v3 chỉ được train trên ảnh tổng hợp.
  - Script render ảnh Slide đã bị xoá.
- **Gắn nhãn tay tối 25/11** (46 frame, khoảng 40 phút):
  - Vị trên lon thấy mặt gần như đúng hết.
  - Lỗi 1: chấp nhận lời đoán sai của model, ở 3 lon Original.
  - Lỗi 2: gán vị theo cảm giác cho một nắp không nhìn ra vị, 20 box.
  - Lỗi 3: không chấm lon bị sót.

**Chạy thử ngày 25/11:**
- Script: `C:\Users\huyho\Datagent\_sam3\proposers_spike.py`.
- Kết quả: `store_eval\proposers_spike_20261125.json`.
- Tập đo: 10 keyframe giữ riêng, 121 lon trên tầng trên.
- Một lon tính là tìm thấy khi tâm box nằm trong box đáp án.

| Cách | Tìm thấy | Nắp | Đúng vị | Box ở chỗ không có lon trong đáp án |
|---|---|---|---|---|
| Slide v3 đang chạy thật, ngưỡng 0,25 | 86% | 29/45 | 71% | 0 |
| **YOLOE-11L, box mẫu từ 1 keyframe ngày 23/11, ngưỡng 0,3** | **96%** | **43/45** | không đoán được | 2,8 mỗi frame, đa số là lon Slide thật ở tầng dưới |
| YOLOE bằng chữ "can" | ~0% | | | |
| OWLv2 bằng ảnh mẫu | không dùng được: hàng nghìn box, 15 giây/ảnh | | | |
| Kho ảnh màu (thử nghiệm buổi chiều) | | | 85% trên các box tìm thấy | |

**Giới hạn của lần chạy thử:**
- một camera, 10 frame, một keyframe mẫu;
- ngưỡng được chọn sau khi đã thấy số.

## 2. Mục tiêu, không làm, thất bại dù chạy

**Mục tiêu:**
1. **Pipeline chạy ngoài live, tự gắn box và vị** cho các frame ban ngày của một camera.
   - Người chỉ nhìn chỗ các nguồn bất đồng, tối đa một frame mỗi đoạn, trên trang Model.
2. **Train lại Slide bằng ảnh thật (Slide v4)** từ các nhãn đó, và phải qua cổng đo trên tập giữ riêng.
3. **Dùng lại được cho camera và tiệm mới**, chỉ cần:
   - một keyframe vẽ box;
   - danh mục SKU của tiệm.

**Không làm lần này:**
- Không tự gắn frame AUD. Cách chấm frame AUD giữ nguyên.
- Không đổi worker. Việc gộp frame trong worker thuộc bản thiết kế slide-fusion.
- Không đưa TH vào pipeline: TH đã có keyframe và lan nhãn. Pipeline chỉ cần cấu hình được để thêm TH sau.
- SAM 3 chỉ được chạy so sánh khi Meta duyệt quyền tải.
- Không tự chạy pipeline hằng đêm.

**Thất bại dù vẫn chạy:**
- Một nhãn vị vào tập train mà chỉ có một nguồn nói vậy.
- Kho ảnh màu được nuôi bằng nhãn tự động, thành vòng tự khen. Kho chỉ nhận nhãn của người.
- Frame AUD, frame giữ riêng hoặc `slide_pilot\test_frames` vào tập train hay vào kho ảnh. Lỗi này đã xảy ra với TH (mục 6).
- Lon nhìn thấy được mà không có nhãn bị để làm nền. Model sẽ học cách bỏ qua lon.
- Hàng chờ của người bị ngập.
- Box đang tranh chấp hiện sẵn một vị gợi ý, khiến người bấm theo. Đó chính là lỗi 3 lon Original tối 25/11.
- Làm nhiễu màu (hue, saturation) khi train, trong khi màu là thứ phân biệt vị. Bài học từ v5: hue bị trải rộng thì model sụp.
- Làm chết worker vì cài thư viện có DLL mới vào `.venv` (mục 3, Smart App Control).

## 3. Ràng buộc

**Frame:**
- `training/store_view/harvest.py` gom frame về `store_frames` trên HUYHOANG.
- `manifest.jsonl` có trường `audit_ids`, cho biết frame nào là AUD hay TRN.
- S3 giữ frame 30 ngày.

**Đoạn:**
- `segments.py` chia đoạn theo vùng Slide `880,120,1520,720`.
- Cửa sổ giữ riêng `HOLDOUT`: 23/11 18:00–21:00, và từ 25/11 trở đi không có điểm kết thúc. Vì vậy mọi ngày mới đều đang bị giữ riêng (xem 5.7).

**HUYHOANG:**
- GPU dùng chung với worker và các lần train.
- Smart App Control đang bật, nên DLL mới cài bị chặn. Cách đã chạy được: môi trường riêng mượn torch của `.venv` qua file `.pth`, như `.venv-sam3`.
- `.venv` của worker dùng ultralytics 8.4.47. YOLOE chạy trong môi trường riêng.

**AWS:** chỉ laptop có quyền, để đọc bảng audits và ghi frame review.

**Trang Model:**
- Bảng audits có `purpose` là `scoring` (AUD) hoặc `training` (TRN).
- Người gắn bấm qua các trạng thái Right → Wrong SKU → Not our SKU → Out of scope, và chấm điểm cho lon bị sót.
- Backend chỉ lưu `verdicts_json` và `missed_json`. Số liệu được tính khi đọc.

**Khác:**
- TRAINING.md: không train và không đưa vào kho ảnh các frame AUD và `slide_pilot\test_frames`. Frame TRN thì được.
- Danh mục SKU theo từng tiệm (`sku_master`). Không hardcode 4 vị Slide.
- Ảnh tiệm, nhãn và kho ảnh không vào repo hay OneDrive.

## 4. Các cách đã cân nhắc

| Cách | Được | Mất |
|---|---|---|
| 1. Lan nhãn từ keyframe, như TH | Nhãn chắc như người gắn | Mỗi cách xếp mới vẫn cần người. Tiệm mới bắt đầu từ đầu |
| **2. Thầy – trò có kiểm chéo (chọn)** | Người chỉ nhìn chỗ khó. Mở rộng không giới hạn | Lỗi mà mọi nguồn cùng mắc thì vẫn lọt. Mỗi vòng phải đo lại |
| 3. Model nền tảng đề xuất box | Chạy được ở tiệm chưa có model. Lỗi khác hẳn detector của mình | Không biết vị |

- **hoang chọn cách 2 ngày 25/11,** lấy cách chia đoạn của cách 1 và nguồn box của cách 3.
- **Nguồn box thứ hai là YOLOE, không phải SAM 3** (hoang chốt sau khi xem kết quả chạy thử). Lý do:
  - SAM 3 cần quyền tải và đang chờ Meta duyệt;
  - SAM 3 chỉ nhận box mẫu trong cùng một ảnh;
  - YOLOE chạy trong bộ ultralytics sẵn có và đã đo được trên camera này.
- **Khi SAM 3 được duyệt** thì chạy so sánh. Nếu SAM 3 tốt hơn rõ thì đổi.
- **So sánh tối 25/11** (`store_eval\sam3_spike_20261125.json`, cùng 10 keyframe):

  | Nguồn | Tìm thấy | Nắp | Box ở chỗ không có lon trong đáp án |
  |---|---|---|---|
  | YOLOE box mẫu, 0,3 | 116/121 | 43/45 | 2,8/frame |
  | SAM 3 bằng chữ "can", 0,6 | 120/121 | 45/45 | 6,4/frame |

  - Box thừa của SAM 3 phần lớn là lon Slide thật ở tầng dưới, phần còn lại là nắp hũ và lọ khác.
  - SAM 3 không tốt hơn rõ, nên **giữ YOLOE làm nguồn B**, vì nó chỉ tìm đúng lon Slide.
  - SAM 3 (bằng chữ, không cần box mẫu) dùng để đề xuất box trên keyframe đầu tiên của camera mới (5.8).

## 5. Thiết kế

### 5.1 Luồng

```
frames của một đoạn ban ngày (đã loại AUD, giữ riêng, frame có người che)
  ├─ nguồn A: Slide v3, ngưỡng 0,05            → box + vị
  └─ nguồn B: YOLOE, box mẫu của camera, 0,3   → box (không vị)
        ↓ ghép trong mỗi frame (IoU ≥ 0,5)
  cụm theo vị trí qua cả đoạn = "lon của đoạn"
        ↓ + kho ảnh màu đọc vị từng box
  luật quyết định (5.4): chấp nhận / đưa người xem / bỏ
        ↓ lon cần xem cùng chỗ + cùng màu với lon người đã quyết → nhận lại quyết định (5.4b)
  hàng chờ Review trên trang Model (≤ 1 frame mỗi đoạn)
        ↓ quyết định của người áp cho cả cụm, cả đoạn; nhãn người vào kho ảnh
  file nhãn YOLO cho các frame của đoạn (vùng chưa rõ bị che xám)
        ↓
  tập train Slide v4 (ảnh thật + ảnh tổng hợp v3) → train → cổng 2 → live khi hoang OK
```

### 5.2 Hai nguồn box

**Nguồn A: Slide v3 đang chạy thật.**
- Ngưỡng 0,05, `imgsz 2560`, như `slide_exp.py`.
- Cho box và vị.

**Nguồn B: YOLOE-11L-seg với box mẫu.**
- Box mẫu là box người vẽ trên các keyframe mẫu của camera, đưa vào qua `refer_image`.
- Với CAM-S01-A, keyframe mẫu là các keyframe phía train trong `truth.json`.
- Chạy trên ảnh cắt vùng Slide, `imgsz 640`, ngưỡng 0,3.
- Chỉ cho box, không cho vị.

**Ghép:** trong một frame, box A và box B có IoU ≥ 0,5 là cùng một lon.

### 5.3 Cụm theo đoạn

- Trong một đoạn ban ngày, cách xếp không đổi, nên mỗi lon đứng một chỗ.
- Box được gom thành cụm theo vị trí qua các frame được chọn của đoạn: IoU ≥ 0,5 với tâm cụm, như `fuse` trong slide-fusion.
- Mỗi cụm là một "lon của đoạn" và ghi lại:
  - tỉ lệ frame A thấy nó, tỉ lệ frame B thấy nó;
  - box trung vị;
  - phiếu vị của A, có trọng số độ tin cậy;
  - phiếu của kho ảnh màu trên từng box.
- Không chạy trên đoạn transient (có người che) và đoạn tối (tủ đã cất).

### 5.4 Luật quyết định

Luật viết thành hàm thuần, có test.

**Có lon thật không:**

| Bằng chứng | Quyết định |
|---|---|
| A và B đều thấy, mỗi nguồn ở ≥ 30% frame của đoạn | có lon |
| Chỉ B thấy ở ≥ 60% frame, và kho ảnh không nói "không phải sản phẩm" | có lon. Đây là đường bắt các nắp mà A sót |
| Chỉ A thấy | đưa người xem |
| Thấy ở < 30% frame | bỏ (box ma) |

**Vị gì:**
- **Kho ảnh đọc vị** theo luật của slide-fusion mục 5.1:
  - 10 láng giềng gần nhất;
  - một vị chiếm ≥ 0,6 tổng trọng số và có ≥ 3 trong 10 láng giềng;
  - vị đó có ≥ 20 ảnh trong kho.
- **Chấp nhận vị khi** A và kho ảnh nói cùng một vị, và mỗi bên giữ vị đó ở ≥ 80% số frame cụm được thấy.
- **Đưa người xem khi:**
  - hai bên bất đồng;
  - một bên không đủ chắc;
  - vị đó có < 20 ảnh trong kho (Hot hiện nay).

Đưa người xem nghĩa là cả nắp không nhìn ra vị cũng đến tay người. Người chấm Out of scope thì vùng đó bị che khi train.

Các ngưỡng 30%, 60% và 80% được chọn trên các đoạn phía train có đáp án. Người làm được chỉnh, nhưng kết quả phải qua cổng 1 (5.7).

### 5.4b Dùng lại quyết định của người (thêm ngày 26/11, hoang chọn cách C)

**Vì sao:**
- Cổng 1 chạy lần đầu (25/11) đẩy 32/36 đoạn giữ riêng sang người xem, vượt xa giới hạn 40%. Tổng cộng có 271 lon cần người chọn vị.
- Phần lớn các đoạn tối 23/11 là **cùng một cách xếp** lặp lại, nên người sẽ phải trả lời cùng những câu hỏi ở mỗi đoạn:
  - 3 lon mà A và kho ảnh bất đồng;
  - 4–5 nắp mà A sót.
- Không nới luật 5.4. Nhận vị khi chỉ có kho ảnh (85% đúng) là nhãn vị dựa trên một nguồn, đúng điều mục 2 cấm.

**Luật:**
- Một lon cần xem ở đoạn S được **nhận lại quyết định** của một lon P mà người đã quyết, khi thoả cả ba điều kiện:
  1. cùng camera;
  2. **cùng chỗ:** box trung vị của hai lon có IoU ≥ 0,5;
  3. **cùng màu:** đặc trưng màu trung bình của hai cụm (cùng đặc trưng 144 chiều của kho ảnh) gần nhau dưới ngưỡng τ.
- **Chỉ trùng chỗ thì chưa đủ.** Ví dụ có thật trong đáp án, tại box (943, 247): lúc 18:14 ngày 23/11 là lon Sour Cream màu xanh, đến 18:57 đã là lon Cheese màu vàng. Mô phỏng chỉ xét vị trí sẽ gán sai lon này.
- Quyết định nhận lại có thể là một vị, Not our SKU hoặc Out of scope. Out of scope vẫn che xám như trước.
- **Nguồn quyết định của người:**
  - quyết định trên frame review;
  - dòng `truth.json` phía train;
  - verdict TRN.
- **Không bao giờ dùng làm nguồn:** frame AUD, và đáp án giữ riêng (trừ khi mô phỏng người trong cổng 1).
- **Khi nhiều lon P cùng khớp:** lấy lon được quyết gần nhất về thời gian. Nếu các lon khớp đó mang quyết định khác nhau thì không nhận lại, mà đưa người xem.
- **Người sửa một quyết định** thì mọi lon đã nhận lại quyết định đó đổi theo, vì nhãn được tính lại mỗi lần chạy `labels`.

**Hàng chờ:**
- Xét các đoạn theo thứ tự thời gian. Một lon cần xem mà khớp với lon đang chờ người ở đoạn trước thì **chờ cùng**, không mở thêm frame.
- Một đoạn chỉ có frame review khi có ít nhất một lon không khớp với lon nào đã quyết hoặc đang chờ.
- Trên frame review, lon đã nhận lại quyết định hiện như lon đã chấp nhận: có vị và người vẫn sửa được. Lon cần xem vẫn không có vị gợi ý.

**Mô phỏng ngày 26/11** trên 36 đoạn giữ riêng. Màu được thay bằng vị đa số mà kho ảnh đọc, vì chưa chạy đặc trưng màu thật:

| Điều kiện khớp | Frame review | Lon người chọn vị |
|---|---|---|
| Không dùng lại (hiện nay) | 32 | 271 |
| Cùng chỗ + kho ảnh đọc cùng vị | 15 (42%) | 45 |
| Chỉ cùng chỗ (không an toàn, xem ví dụ trên) | 12 (33%) | 34 |

**Trên đáp án:** giữa các keyframe liên tiếp trong cùng ngày, 156/157 cặp lon cùng chỗ có cùng vị; cặp còn lại là lon bị đổi nói trên.

**Rủi ro còn lại:** hai lon khác vị nhưng trông giống hệt nhau đổi chỗ cho nhau, ví dụ nắp Original và nắp Hot trên camera này. Chỉ số "dùng lại đúng" ở cổng 1 (5.7) đo rủi ro này.

**Để người làm tự quyết:**
- ngưỡng τ, chọn trên các cặp keyframe phía train;
- có giới hạn khoảng thời gian dùng lại hay không;
- cách tính đặc trưng màu trung bình của cụm.

### 5.5 Hàng chờ Review trên trang Model

- **Loại frame mới "Review frame":** `purpose` là `review`, id dạng `REV-<camera>-<segment id>`. Chỉ đoạn còn ít nhất một cụm cần người xem, sau khi đã dùng lại quyết định (5.4b), mới có frame review. Mỗi đoạn tối đa một frame.
- **Box hiện trên frame:** mọi lon của đoạn.
  - Lon đã chấp nhận hiện vị, người vẫn sửa được.
  - **Lon cần xem không hiện vị gợi ý.** Người phải chọn vị, hoặc chọn Not our SKU hay Out of scope. Nút "Right" không dùng cho box này.
- **Thứ tự hàng chờ:** frame chấm điểm, rồi frame train, rồi frame review.
- **Frame review không tính vào số độ chính xác.**
- **Lon người chấm bị sót** trên frame review không có box, nên khi train thì vùng quanh điểm đó bị che.
- **Quyết định của người** áp cho cả cụm, trên mọi frame của đoạn, và đi vào kho ảnh màu như nhãn người.
- **Tạo frame review:** script chạy trên laptop, chép ảnh vào bucket analytics và ghi dòng audit, như `_write_frame_audit` của ingest.

### 5.6 Nhãn và tập train Slide v4

- **Nhãn train gồm mọi lon Slide nhìn thấy,** kể cả tầng dưới. Luật đếm (Rule A/B) là chuyện khác: lon thấy được mà không có nhãn sẽ dạy model bỏ qua lon.
- **Mỗi frame được chọn của đoạn** có một file nhãn YOLO, gồm các lon đã chấp nhận hoặc đã được người duyệt.
- **Vùng chưa rõ bị tô xám** trên bản sao ảnh, để không thành nền. Vùng chưa rõ gồm:
  - lon bị chấm Out of scope;
  - lon còn chờ người xem;
  - điểm lon sót;
  - đoạn chưa duyệt xong.
- **Lớp:** theo danh mục SKU của tiệm cho nhóm Slide, hiện là 4 vị.
- **Luôn loại:**
  - frame có audit AUD (theo `audit_ids` trong manifest);
  - đoạn giữ riêng;
  - `slide_pilot\test_frames`.
- **Chia train/val** theo đoạn, không theo frame. Ảnh cắt thành cửa sổ kích thước gốc, như `dataset.py` của TH.
- **Trộn thêm ảnh tổng hợp v3** (`dataset_v3mix`).
- **Làm nhiễu khi train ("trò"):**
  - được: sáng/tối, tương phản, mờ, nhiễu hạt, che bằng người và tay (props của Long), co giãn, dán lon thật sang nền khác;
  - **không được** đổi hue hay saturation.

### 5.7 Đo, cổng và tập giữ riêng

**Tập giữ riêng:**
- Đóng cửa sổ "từ 25/11 trở đi" lúc 26/11 00:00, để các ngày mới được dùng cho train.
- Chọn thêm ít nhất một ngày giữ riêng mới, ưu tiên ngày tiệm bày lon Hot, để có đủ ≥ 20 keyframe trên ≥ 3 ngày.
- Đáp án cho tập mở rộng vẽ như `truth.json`:
  - YOLOE được phép đề xuất box;
  - người xác nhận từng lon và từng vị, và vẽ cả lon bị sót.
- Đáp án phải có cả lon tầng dưới, ghi `kind` là `lower`:
  - bổ sung cho 18 keyframe hiện có;
  - Rule A không đếm lon `lower`, nhưng cổng 1 tính chúng là lon thật, vì nhãn train có lon tầng dưới.
- Tập này dùng chung với cổng của slide-fusion.
- Giữ nguyên cửa sổ 25/11 để đo TH không đổi.

**Cổng 1: chất lượng nhãn tự động, trước khi train.**
- Chạy pipeline trên các đoạn giữ riêng, so với đáp án.
- Đáp án của các đoạn đó không được dùng làm box mẫu hay vào kho ảnh.

| Chỉ số | Ngưỡng |
|---|---|
| Box được chấp nhận không qua người là lon thật | ≥ 99% |
| Box được chấp nhận không qua người đúng vị | ≥ 98% |
| Lon trong đáp án được phủ (chấp nhận, đưa vào review hoặc nhận lại quyết định) | ≥ 95% |
| Đoạn cần một frame review **mới**, sau khi đã dùng lại quyết định (5.4b) | ≤ 40% |
| Quyết định dùng lại đúng (5.4b) | ≥ 99% |

**Cách đo khi dùng lại quyết định (thêm ngày 26/11):**
- **Mô phỏng người:**
  - đoạn có keyframe trong đáp án: người quyết đúng như đáp án;
  - đoạn không có keyframe trong đáp án: không mô phỏng quyết định, chỉ đếm xem đoạn đó có cần frame review mới hay không.
- **"Dùng lại đúng"** chấm trên các cặp lon được nối bởi luật 5.4b mà cả hai đoạn đều có keyframe trong đáp án. Đúng nghĩa là hai dòng đáp án ở hai đầu có cùng vị, hoặc cùng là nắp không rõ vị (`unknown` hoặc `ignore`).
- Các cặp keyframe phía train cũng được chấm để chọn τ. Đó chỉ là đo phép so khớp, không đưa đáp án vào kho ảnh hay làm box mẫu.

Nếu độ đúng không đạt thì dời ngưỡng về phía "đưa người xem", không hạ ngưỡng của cổng.

**Cổng 2: Slide v4 so với v3 đang chạy thật,** trên tập giữ riêng mở rộng.

| Chỉ số | Ngưỡng |
|---|---|
| Tìm thấy | ≥ live |
| Đúng vị | ≥ live + 10 điểm |
| Đúng vị của từng vị | không vị nào thấp hơn live quá 5 điểm |
| Box thừa | ≤ 0,3 mỗi frame |

**Phiên bản và lên live:**
- `MILK_MODEL_VERSION` mang hậu tố `+slide-v4real-<YYYYMMDD>`.
- Lên live bằng `MILK_SLIDE_WEIGHTS` trong `worker.env`, chỉ khi hoang OK.
- Quay lui: trả `MILK_SLIDE_WEIGHTS` về v3.

### 5.8 Camera hoặc tiệm mới

**Cấu hình theo camera:**
- vùng hàng;
- nhóm SKU và danh sách SKU, lấy từ `sku_master`;
- các keyframe mẫu có box;
- đường dẫn kho ảnh.

**Các bước cho camera mới:**
1. Gom frame (harvest) và chia đoạn.
2. Người vẽ box trên 1–3 keyframe. SAM 3 với chữ "can" đề xuất box trước, người sửa.
3. Chạy pipeline.
4. Review.
5. Train.

Nếu nhóm SKU chưa có detector (không có nguồn A):
- chỉ chạy nguồn B;
- lần đầu, mọi vị đều qua người;
- kho ảnh lớn dần từ nhãn người, nên các vòng sau người nhìn ít hơn.

### 5.9 Chạy ở đâu, code ở đâu

- **HUYHOANG:**
  - Môi trường riêng `.venv-label`, mượn torch của `.venv` qua file `.pth`. Không cài gì vào `.venv` của worker.
  - Chạy ở mức ưu tiên thấp, có giới hạn VRAM.
  - Không chạy song song với một lần train khác nếu không có giới hạn VRAM.
- **Laptop:** đọc bảng audits, ghi frame review, rồi chép quyết định sang HUYHOANG.
- **Repo:**
  - `training/store_view/auto_label.py`: luồng chính và luật quyết định, có test.
  - `training/store_view/slide_gallery.py`: dùng chung với slide-fusion. Bản thiết kế nào làm trước thì xây file này.
  - Backend: thêm `purpose` `review` (đọc, lưu, không tính vào số độ chính xác).
  - Frontend: hiện Review frame; box cần xem không có vị gợi ý.
- **Sửa `training/store_view/dataset.py`** để loại frame AUD (mục 6).
- **Thay đổi backend và frontend** đi theo đường thường lệ: PR, CI, deploy tay. Chỉ lên live khi hoang OK.

### 5.10 Để người làm tự quyết

- Cách dùng nhiều keyframe mẫu cho YOLOE: hợp các lần chạy, hay chọn keyframe giống nhất.
- Số frame mỗi đoạn, và frame nào làm frame review.
- Các ngưỡng 30%, 60% và 80%, miễn là qua cổng 1.
- Bán kính vùng che quanh điểm lon sót.
- Tỉ lệ trộn ảnh tổng hợp.
- Cách train Slide v4: train tiếp từ `slide_pilot\runs_v3\best.pt` hay train lại từ đầu, số epoch, `imgsz`.
- Định dạng file trung gian, cách viết test.

## 6. Phát hiện khi viết thiết kế (cần hoang quyết riêng)

**Frame AUD lọt vào tập train TH:**
- `training/store_view` không lọc `audit_ids`.
- Có 30 ảnh (27 train, 3 val) cắt từ 21 frame AUD ngày 22–24/11 nằm trong `store_dataset_v1`, tập mà TH đang train.
- Không con số nào hiện nay bị sai:
  - cổng đo TH dùng cửa sổ giữ riêng;
  - trang Model chấm box mà model đang chạy thật trả ra lúc chụp, nên model TH mới không bao giờ bị chấm trên các frame cũ đó.
- `database v2` (chưa live) có 32 trong 4.000 ảnh cắt TH lấy từ 4 frame AUD.
- hoang chọn giữ lần train này (cách a).
- Commit `1d89c26`: `dataset.py` và `build_db.py` đọc manifest, bỏ mọi frame AUD, và từ chối chạy khi thiếu manifest. Pipeline mới phải làm như vậy.

**HUYHOANG bật Smart App Control:** torch mới cài bị chặn. Không được nâng cấp torch trong `.venv` của worker.

## 7. Để sau

- Chạy pipeline hằng đêm.
- Đưa TH vào pipeline.
- Vẽ box trên trang Model, thay vì chỉ chấm điểm lon sót.
- Chọn frame review theo mức "máy không chắc" (active learning) khi hàng chờ lớn.
