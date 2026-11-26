# Một đường đọc chung cho mọi nhóm hàng: tìm → xác nhận → gộp cửa sổ — thiết kế

Ngày 26/11/2026. Trạng thái: hoang duyệt ngày 26/11 ("ok duyệt thiết kế"). Nhánh: `feat/common-read-path`, tách từ `feat/auto-label-part2`
(63caa5a, PR #15 đang mở).

**Quan hệ với các thiết kế khác:**
- `2026-11-25-slide-fusion-gallery-design.md` (gọi là "thiết kế Slide"): bản này đổi thứ tự làm (Slide không còn chờ TH
  lên live) và dùng lại mục 5.1–5.4 của nó. Khi hai bản lệch nhau, bản này thắng.
- `2026-11-25-th-store-view-design.md` (gọi là "thiết kế TH"): bản này thay "vòng kế" ở mục 5.4 của nó (gom ảnh 26/11,
  vẽ thêm keyframe, nạp lại database) và thay cách bật live ở mục 5.5. Cổng đo giữ nguyên.
- `2026-11-25-auto-label-design.md`: không đổi. Hàng chờ review của nó là một nguồn nhãn cho kho ảnh ở mục 5.3.

## 1. Vì sao làm

**hoang nói ngày 26/11:**
- "model đã detect được tương đối nhưng chưa hiệu quả đôi lúc ví dụ khi gặp lốc sữa TH, hiện tại thì tôi vẫn chưa tìm
  ra cách để xử lí hiệu quả."
- "ở tiệm tạp hóa thì họ vừa bán lốc vừa có thể xé lẻ mua." Vì vậy vẫn phải đếm từng hộp, không đếm lốc.
- "ngoài sữa ra thì slide khoai tây cũng gặp 1 số vấn đề về dự đoán."
- hoang chọn cách 2 ở mục 4: "ok chọn cách 2".

**TH và Slide hỏng cùng một kiểu:** bước tìm tạm ổn, bước gọi tên hoặc xác nhận gãy khi điều kiện đổi, và mỗi lần đọc
chỉ dựa vào một frame.

| Nhóm | Số đo hiện có | Chỗ hỏng |
|---|---|---|
| TH (model `store_v1`, chưa live) | Tập giữ riêng 25/11: tìm đúng 0,806, số hộp lệch ≤ 1 ở 0,703 số frame. Trượt cổng | Kiểu xếp đã thấy lúc dạy: khoảng 0,96. Kiểu xếp mới sáng 25/11: 0,16–0,56 |
| Slide (v3, đang live) | Thử nghiệm 25/11: tìm thấy 86%, đúng vị 71% | Sai vị theo ánh sáng (Original thành Hot buổi chiều, thành Cheese buổi tối). Sót lon chỉ lộ nắp (29/45) |

**Phép đo ngày 26/11 (chạy ngoài live, trên HUYHOANG; file ở mục 6).**

*a) Hỏi lại database v2 khi giấu bớt ảnh đã nạp.* 3.968 ảnh cắt hộp TH thật được tra lại, bằng đúng luật bỏ phiếu của
`recognize.Recognizer.lookup`.

| Ảnh bị giấu khỏi kho | Được nhận ở ngưỡng 0,9825 | Được nhận khi bỏ hẳn ngưỡng |
|---|---|---|
| Chỉ chính frame đó | 0,95 | 0,97 |
| Cả kiểu xếp của nó | 0,64 | 0,83 |
| Cả ngày của nó | 0,28 | 0,52 |
| Mọi ảnh thật (chỉ còn ảnh tổng hợp) | 0,15 | 0,36 |

Nới ngưỡng không đủ. Phần lớn ảnh bị gạt vì cả 10 láng giềng gần nhất đều là `none` (kho có 35.004 vector nền và hộp
khác). Embedder chỉ học ảnh tổng hợp, nên hộp TH ở góc nhìn mới nằm gần "nền" hơn gần hộp sữa.

*b) 594 frame giữ riêng (4.154 hộp), detector `best_store_v1.pt` ở ngưỡng 0,25, sau bước `one_box_per_unit` như worker.*

| Cách đọc | Tìm đúng | Box đúng | Số hộp lệch ≤ 1 | Box trên 48 frame không có TH |
|---|---|---|---|---|
| Database như hiện nay | 0,813 | 0,979 | 0,709 | 0 |
| **Không hỏi database cho lớp TH** | **0,952** | **0,946** | **0,974** | 0 |
| Như trên, thêm luật bỏ box chồng ≥ 0,5 box nhỏ | 0,948 | 0,968 | 0,960 | 0 |

Riêng các kiểu xếp mới E0/E1/E2 (180 frame, 1.380 hộp):

| Cách đọc | Tìm đúng | Box đúng | Số hộp lệch ≤ 1 |
|---|---|---|---|
| Database như hiện nay | 0,467 | 0,900 | 0,128 |
| Không hỏi database cho lớp TH | 0,856 | 0,840 | 0,922 |

Dòng "database như hiện nay" khớp báo cáo cổng tối 25/11 (0,806 / 0,980 / 0,703), nên cách tính lại là tin được. Tính
theo đoạn, cách "không hỏi database" đạt 0,958 / 0,954 / 0,975.

*c) 1.380 hộp ở kiểu xếp mới đi đâu* (trước bước `one_box_per_unit`): 682 được nhận, 485 bị "nền" thắng phiếu, 119 dưới
ngưỡng 0,9825, 94 không có box.

*d) Box thừa của detector ở kiểu xếp mới* (trước bước `one_box_per_unit`): 332 box, trong đó 330 là box thứ hai trên
cùng một hộp và 2 nằm ngoài mọi hộp. Detector gần như không khoanh thứ khác thành TH.

**Rút ra:**
- Với TH ở camera này, database gạt hộp thật nhiều hơn box sai. Nó là thứ làm trượt cổng.
- Chỉ cần thôi hỏi database cho lớp TH, không thêm luật hay ngưỡng nào, là qua mọi ngưỡng của cổng TH trên tập 25/11.
- Tôi (Claude) đã nói sai với hoang hôm 26/11 rằng lỗi nằm ở cách đặt ngưỡng. Phép đo a cho thấy ngưỡng chỉ là phần
  nhỏ.

**Giới hạn của phép đo:**
- Tập giữ riêng 25/11 đã được nhìn ba lần: cổng tối 25/11, lần chẩn đoán, và lần này.
- Chỉ có 48 frame không có TH, đều chụp ngày 23/11 lúc 20:39–20:55, ngay sau khi tủ được cất. Chưa đo đêm khuya và
  các đêm khác, nơi model cũ từng báo cái chai trắng là TH.
- Chưa tính bước gộp với Slide (`pipeline.merge`).
- Một camera, một tiệm.

## 2. Mục tiêu, không làm, thất bại dù chạy

**Mục tiêu:**
1. **TH:** worker đếm được hộp TH cả khi tiệm xếp lại lốc theo kiểu chưa có trong ảnh dạy. Qua cổng của thiết kế TH
   trên tập 25/11 và trên một ngày chưa ai nhìn (26/11).
2. **Slide:** đúng vị tăng ít nhất 10 điểm so với live, tìm thấy không giảm (cổng của thiết kế Slide).
3. **Mọi nhóm hàng đi chung một đường đọc ba bước.** Mỗi bước bật hay tắt theo từng nhóm bằng `worker.env`.
4. **Một bước xác nhận chỉ được bật khi đã đo là nó có lợi** (luật ở mục 5.5). Luật này dùng lại cho camera và tiệm mới.
5. **Quay lui chỉ bằng `worker.env`.**

**Không làm lần này:**
- Train lại detector hay embedder.
- Gọi tên Có đường và Ít đường.
- Đếm lốc.
- Slide tầng dưới.
- Camera hoặc tiệm mới.

**Thất bại dù vẫn chạy:**
- Đếm vật khác thành TH khi không còn database chặn, như cái chai trắng ban đêm.
- Kết quả Vinamilk đổi.
- Số Slide đổi khi mới chỉ bật phần TH.
- Chọn luật hay ngưỡng bằng tập giữ riêng rồi báo số của chính tập đó như số thật.
- Box "ma" chỉ hiện ở 1 frame mà vẫn được đếm. Đổi vị sang vị kho ảnh chưa có. Hàng chờ review ngập.
- Ảnh tiệm, kho ảnh hay nhãn lọt vào repo hoặc OneDrive.

## 3. Ràng buộc

- **GPU HUYHOANG dùng chung với worker.** Worker chiếm khoảng 6,4 GB trên 32 GB. Phép đo 26/11 chạy cùng lúc không
  làm worker dừng.
- **Không ghi đè file worker đang đọc:** `yolo\best_types.pt`, `carton_recognition\…`, `slide_pilot\runs_v3\best.pt`.
- **Trên Windows phải `import torch` trước** cv2, ssl và lancedb.
- **PR #15 chưa merge và chưa deploy.** Nó mang quy tắc gắn nhãn B và dòng gộp `TMP-MLK-TH-00` (commit 891076e) cho
  backend và website. TH lên live cần phần đó được deploy; hoang quyết việc này.
- **Frame AUD không bao giờ dùng để train, nạp kho ảnh hay chỉnh ngưỡng.**
- **Backend và Datagent:** dòng có độ tin cậy < 0,70 bị gắn cờ "Low Confidence" và vào hàng chờ review.
- **Change set:** stack `milk-backend-development` không bao giờ dùng `--tags`.
- Các ràng buộc khác ở mục 3 của thiết kế TH và thiết kế Slide vẫn giữ.

## 4. Các cách đã cân nhắc

| Cách | Được | Mất |
|---|---|---|
| 1. Vá riêng từng nhóm theo thứ tự đang định: TH trước, TH live rồi mới tới Slide | Ít đổi kế hoạch nhất | Slide tiếp tục chờ TH. Hai đường đọc khác nhau phải nuôi. Gặp kiểu xếp mới vẫn phải vẽ nhãn |
| **2. Một đường đọc chung: tìm → xác nhận → gộp cửa sổ (hoang chọn 26/11)** | Slide không chờ TH. Sửa một lần lợi cả hai nhóm. Tiệm mới chỉ cần kho ảnh và vài frame review | Phải sửa vòng lặp chính của worker, nên cần chạy song song một ngày |
| 3. Train lại detector bằng "xếp lại nhân tạo": cắt lốc, hộp, lon thật dán vào vị trí và góc khác | Sửa đúng gốc "nhớ kiểu xếp" và "sót nắp" | Mỗi vòng train nhiều giờ. Không chữa lỗi sai vị theo ánh sáng. Để sau (mục 7) |

**Điều đổi sau khi hoang chọn.** Lúc chọn, tôi mô tả bước xác nhận của TH là "so với database, đặt lại ngưỡng". Phép
đo ở mục 1 cho thấy làm vậy không đủ. Trong bản này, bước xác nhận của TH là **không hỏi database**. hoang cần biết điều
này khi duyệt.

## 5. Thiết kế

### 5.1 Đường đọc chung

Mỗi frame trong cửa sổ lấy mẫu đi qua "tìm" và "xác nhận" của từng nhóm hàng. Các nhóm được gộp bằng `pipeline.merge`
như hiện nay. Cuối cửa sổ, các frame được gộp thành một lần đọc.

| Bước | Sữa TH (lớp `th_true_milk`) | Sữa Vinamilk | Slide |
|---|---|---|---|
| Tìm | `best_store_v1.pt`, cả khung và ô 1280, ngưỡng 0,25. Không đổi | Như TH | Slide v3. Ngưỡng 0,05 khi bước gộp bật, 0,25 khi tắt |
| Xác nhận | Không hỏi database (mục 5.2) | Database như hiện nay | Kho ảnh màu của camera (mục 5.3) |
| Gộp cửa sổ | Thấy ở ≥ 3 trong 6 frame (mục 5.4) | Như TH | Thấy ở ≥ 3 trong 6 frame; vị theo phiếu bầu |

### 5.2 TH: database không còn quyền gạt box của lớp gộp

- **Biến mới `MILK_LONG_TH_CONFIRM`:**
  - `database` (mặc định): y hệt hiện nay.
  - `detector`: box của lớp `th_true_milk` nhận nhãn `TMP-MLK-TH-00` với `unit_score` bằng độ tin cậy của YOLO.
- **Chỉ áp cho lớp gộp `th_true_milk`** của model `store_v1`. Các lớp Vinamilk, và các lớp TH cũ của `best_types.pt`,
  vẫn đi qua database như hiện nay.
- **Khi `MILK_LONG_VARIANTS=1`:** database vẫn được hỏi, nhưng chỉ để gọi tên loại. Nó không được gạt box.
  CAM-S01-A để `MILK_LONG_VARIANTS=0`.
- **Không thêm luật bỏ box trùng.** Bước `one_box_per_unit` giữ nguyên. Luật "chồng ≥ 0,5 box nhỏ" đã thử ở mục 1b: box
  đúng tăng nhưng số hộp lệch ≤ 1 giảm, và không cần nó để qua cổng.
- **Worker tiếp tục đọc database v1** (`carton_recognition`, ngưỡng 0,9556) cho Vinamilk. Database v2 không lên live:
  ngưỡng 0,9825 của nó sẽ làm đổi kết quả Vinamilk, và TH không còn cần nó.
- **Thứ chặn box sai thay cho database:**
  - detector đã học ảnh âm thật của camera này;
  - bước gộp cửa sổ (mục 5.4);
  - display check hiện có, vốn không cho capture lúc tủ đã cất lên Dashboard;
  - cổng đo ban đêm ở mục 5.6.

### 5.3 Slide: đọc lại vị bằng kho ảnh màu

Theo mục 5.1 của thiết kế Slide, không đổi. Tóm tắt:
- Đặc trưng là histogram màu của phần giữa box, đã cân màu.
- Kho ảnh riêng cho từng camera. Nguồn: đáp án vẽ tay phía train, frame TRN đã gắn nhãn trên trang Model, và quyết định
  review (`REV-`) khi phần hàng chờ review của auto-label đã deploy.
- Chỉ đổi vị khi một vị thắng rõ và vị đó có ≥ 20 ảnh trong kho. Không bao giờ đổi sang vị kho chưa có.
- Worker đọc kho qua `MILK_SLIDE_GALLERY`. Không đặt biến thì chạy như hiện nay.

### 5.4 Gộp frame trong cửa sổ lấy mẫu

Theo mục 5.2 của thiết kế Slide, áp cho mọi nhóm hàng. Tóm tắt:
- Module thuần `server/milk/fusion.py`. Gom box theo vị trí. Giữ cụm thấy ở ≥ 3 frame của cửa sổ, hoặc ở mọi frame nếu
  cửa sổ có ít hơn 3 frame.
- Mỗi cửa sổ gửi một capture, có trường `frames_fused`.
- Điểm của một đơn vị = tỉ lệ frame thấy nó × tỉ lệ phiếu của nhãn thắng.
- Bật bằng `MILK_FUSE_WINDOW=1`. Chạy song song trước bằng `MILK_FUSE_SHADOW=1`.

### 5.5 Luật: bước xác nhận phải tự chứng minh

Áp cho mọi nhóm hàng và mọi camera, kể cả tiệm mới:
1. Đo cả hai cách, có và không có bước xác nhận, trên dữ liệu mà kho của bước đó chưa từng thấy. Đó là một ngày giữ
   riêng, hoặc tra lại kho với cả ngày đó bị giấu như mục 1a.
2. Bước xác nhận chỉ được bật khi nó bỏ được nhiều box sai hơn số đơn vị thật nó làm mất, và các chỉ số của cổng không
   chỉ số nào tệ hơn so với khi không có nó.
3. Báo cáo đo ghi cả hai cách.

Theo luật này, ở CAM-S01-A hiện nay: database tắt cho TH. Kho ảnh màu của Slide bật theo thử nghiệm 25/11 (đúng vị 71%
lên 85% trên một frame), và được kiểm lại ở cổng của giai đoạn 2.

### 5.6 Đo và cổng

**TH (giai đoạn 1).** Ngưỡng của cổng giữ nguyên như mục 5.4 của thiết kế TH.

| Phép đo | Trên ảnh nào | Yêu cầu |
|---|---|---|
| Chạy lại bằng code thật (`evaluate run`) | 594 frame giữ riêng hiện có | Qua cổng. Số phải gần mục 1b; lệch quá 2 điểm thì dừng và tìm nguyên nhân |
| Ngày chưa ai nhìn | Frame 26/11 | Qua cổng. Đây là số báo cho hoang |
| Ban đêm | Frame lúc tủ đã cất của đêm 25/11 và 26/11. Các đêm 22–24/11 đã dùng để train nên không tính | ≤ 1 box sữa trên 100 frame |
| Vinamilk không đổi | 200 ảnh val tổng hợp có hộp Vinamilk | Giữa `database` và `detector`: nhãn và box giống hệt, điểm lệch không quá 0,002 (ảnh được embed theo lô khác nhau ở half precision) |
| Slide không đổi | 594 frame giữ riêng | Box Slide giống hệt bản đang chạy |

Mọi phép đo trên chạy với đúng các biến sẽ bật live ở mục 5.7, kể cả database v1.

**Nếu tập 25/11 qua mà ngày 26/11 trượt:** không bật. Báo số cho hoang và chuyển sang giai đoạn 3.

**Cách làm phép đo 26/11:**
- Gom frame từ 25/11 13:00 đến hết 26/11 về laptop và HUYHOANG như mục 5.2a của thiết kế TH, rồi chia đoạn. Bản gom
  hiện có dừng ở 25/11 13:00.
- Claude vẽ khung trên keyframe từ ảnh phóng to. Không dùng box nháp của detector, để đáp án không nghiêng theo model
  đang được chấm.
- `segments.HOLDOUT` thêm cửa sổ 26/11 00:00 đến 27/11 00:00. Sau khi hoang quyết việc bật TH, cửa sổ này được gỡ bằng
  một commit riêng và frame 26/11 trở lại làm dữ liệu dạy.
- Nếu ngày 26/11 lốc vẫn nằm đúng kiểu của 25/11, báo cáo phải ghi rõ: phép đo vẫn tính, nhưng không nói thêm được gì
  về kiểu xếp mới.

**Slide và bước gộp (giai đoạn 2).**
- Cổng theo mục 5.3 của thiết kế Slide.
- Thêm một điều kiện: sau khi bật gộp, tìm đúng và số hộp lệch ≤ 1 của TH không thấp hơn số giai đoạn 1 quá 1 điểm.

### 5.7 Thứ tự làm và đưa vào chạy

**Giai đoạn 1: TH đọc được.** Chỉ đổi worker.
1. Thêm biến ở mục 5.2 vào `long_adapter.py`, có test. Tắt biến thì kết quả giống hệt hiện nay.
2. Làm các phép đo TH ở mục 5.6 và báo số cho hoang.
3. Khi hoang OK, bật live theo mục 5.5 của thiết kế TH, với các khác biệt sau:
   - `MILK_LONG_DIR` giữ nguyên (database v1);
   - `MILK_LONG_YOLO=…\yolo\best_store_v1.pt`, `MILK_LONG_TILE=1280`, `MILK_LONG_VARIANTS=0`,
     `MILK_LONG_TH_CONFIRM=detector`;
   - `MILK_MODEL_VERSION=long-store-v1-det+slide-v3`.
4. Bước này cần backend và website của PR #15 đã deploy (mục 3).

**Giai đoạn 2: gộp cửa sổ và kho ảnh màu Slide.** Bắt đầu ngay khi code giai đoạn 1 đã xong, không chờ TH lên live.
Chạy song song một ngày, qua cổng, hoang OK, rồi bật. Chi tiết theo mục 5.4 của thiết kế Slide.

**Giai đoạn 3, chỉ khi một cổng trượt:** train lại bằng "xếp lại nhân tạo" (cách 3). Cần một bản thiết kế riêng.

**Quay lui:** xoá các biến mới khỏi `worker.env` và khởi động lại task `milk-worker`. Model và database cũ không bị
đụng tới.

### 5.8 Để người làm tự quyết

- Chỗ đặt code đọc biến mới, và cách viết test.
- Cách chọn frame ban đêm: theo `display_visible` trong manifest, theo giờ, hoặc theo đoạn. Mỗi đoạn phải có một frame
  được nhìn bằng mắt để chắc không có lốc.
- Cách truyền biến mới vào `evaluate run`. Hàm `_pipeline` hiện chỉ xoá bốn biến `MILK_LONG_*` trước khi nạp.
- Số frame lấy ở mỗi đoạn khi đo.
- Mọi điểm mà mục 5.5 của thiết kế Slide đã để người làm tự quyết.

## 6. Phép đo 26/11 nằm ở đâu

Trên HUYHOANG, không vào repo:
- Script: `C:\Users\huyho\Datagent\_confirm_spike\`
  - `loao.py`: mục 1a;
  - `detonly.py`: xuất mọi box của detector kèm câu trả lời thô của database;
  - `final.py`, `analyze.py`, `dedupe.py`, `falses.py`: mục 1b–1d. Ba script đầu đọc `segments.json` và `keyframes.json`
    theo đường dẫn trên laptop.
- Kết quả, trong `C:\Users\huyho\Datagent\store_eval\`:
  - `confirm_spike_20261126.txt`: mục 1b và 1c;
  - `confirm_spike_20261126_database.txt`: mục 1a;
  - `confirm_spike_20261126_boxes.json`: mọi box của 594 frame.

Đây là code thử, không có test. Không dùng lại trong sản phẩm.

## 7. Để sau

- **Train lại bằng "xếp lại nhân tạo" (cách 3).** Làm khi một cổng trượt, hoặc khi cần nâng tỉ lệ box đúng ở kiểu xếp
  mới (hiện 0,84, phần sai là box thứ hai trên cùng một hộp).
- **Luật bỏ box trùng cho lưới hộp sát nhau.**
- **Train lại embedder bằng ảnh thật.** Cần cho việc gọi tên Có đường và Ít đường, và để database có thể làm bước xác
  nhận theo luật 5.5.
- **Database v2:** giữ làm dữ liệu, không dùng trên live.
- **Camera và tiệm mới:** áp luật 5.5 trước khi bật bất kỳ bước xác nhận nào.
