# Độ tin cậy của số đếm: không đếm lúc không thấy kệ, đo cho đúng, sửa nhầm vị

Ngày 2026-11-24 · hoang chọn hướng trong chat ("duyệt hướng A", "ok làm theo thứ tự mà bạn đề xuất"; ảnh sự kiện:
"cách A") · nối tiếp HOANG-P10, spec trang Model (2026-11-23) và spec Dashboard (2026-11-24)

## Vì sao

- **hoang, chat 24/11:** *"bây giờ ta sẽ tập trung vào cải thiện tính tin cậy của hệ thống bao gồm nhiều thông số ví dụ
  (hệ thống báo chính xác các hàng đang có đến mức nào, độ chính xác của từng sản phẩm như thế nào,...). Để mà một hệ
  thống báo đúng 100% là không thể nhưng có thể làm cho hệ thống báo ra 1 con số gần nhất và có trend chung là hướng đi
  ổn nhất."*
- **Data Dictionary (bản tải 24/11):**
  - README: *"Test the CV system's ability to produce PRECISE stock counts at store level. Precision = CV output vs
    human-verified ground truth, measured per store per SKU."*
  - README, bước 6: *"Discrepancies feed back as training corrections for the CV model"*.
  - Accuracy Report, phần C (Feedback Loop): mỗi lần sửa có trường `fed_back_to_model`, và *"Tech Partner should
    retrain the model at least once per bi-weekly cycle using all accumulated corrections."*
- **Số liệu thật, kiểm ngày 24/11** (11 khung team đã chấm, chuỗi capture 23–24/11, bảng shelf, ảnh xem trực tiếp):
  - **Thấy lon thì tốt, gọi tên vị thì sai có hệ thống.**
    - Trong 8 khung ban ngày có tủ, mọi hộp model vẽ đều là lon Slide thật.
    - Nguyên bản chỉ được gọi đúng 5 trên 21 lon: 11 lon bị gọi là Phô mai, 5 lon là Hot & Spicy. Độ tin cậy trung bình
      của các hộp gọi sai này là 0.93, cao hơn hộp đúng (0.84), nên cờ "Low Confidence" (< 0.70) không bắt được.
    - Kem chua hành đúng 30 trên 31.
    - Lỗi đổi theo thời điểm: 12:49–16:20 ngày 23/11 Nguyên bản bị gọi là Hot; 17:44–20:33 bị gọi là Phô mai; 09:35
      ngày 24/11 gọi đúng.
    - Chưa tách được lỗi do ánh sáng hay do cách xếp: lúc 17:33 ngày 23/11 worker cũng chuyển sang HUYHOANG. Hai máy
      dùng cùng trọng số `runs_v3/best.pt` và cùng thiết lập mặc định.
    - Tiệm có 2 mẫu bao bì Nguyên bản (chữ "NGUYÊN BẢN" và chữ "ORIGINAL", cùng thân cam).
  - **Làm mượt không sửa được lỗi nhầm vị.**
    - Nhiễu ngẫu nhiên đã được xử lý. Ví dụ, trong một cửa sổ 30 giây, số Kem chua hành nhảy từ 4 đến 8, nhưng trung
      vị 5 phút chỉ lệch ±1.
    - Nhầm vị lặp lại ở mọi capture. Dashboard báo Nguyên bản hết hàng lúc 17:30 và 18:40 ngày 23/11, trong khi khung
      chấm lúc 17:44 và 18:49 có 3 và 2 lon.
  - **Lúc không thấy kệ thì bị tính là hết hàng.**
    - Khoảng 20:40 tiệm cất tủ kính: ảnh 21:15 không còn tủ, ảnh 22:00 bàn đã phủ bìa. Kế hoạch kệ lại đặt giờ mở cửa
      06:00–22:00, nên hệ thống ghi OOS lúc 20:40.
    - Sáng 24/11 lúc 08:45, khi hub bật lại, hệ thống ghi RESTOCKED.
    - Trong 16 sự kiện kệ đã ghi, ít nhất 13 là giả: do cất tủ, hub mới bật, hộp ảo ban đêm, hoặc nhầm vị. Chỉ
      1 sự kiện có vẻ thật (Hot hết lúc 17:30). 2 sự kiện chưa rõ.
  - **Con số tổng che lỗi của từng SKU.**
    - OSA ngày 23/11 hệ thống tính ra 66%. Theo các khung đã chấm, con số đúng khoảng 81%.
    - Nguyên bản bị báo thấp khoảng 42 điểm, Hot bị báo cao khoảng 30 điểm. Hai lỗi bù nhau trong số tổng.
  - **Thước đo còn mỏng.**
    - KPI #2 là 78.7%, tính trên 89 hộp của 11 khung. Khoảng tin cậy 95% là 69–86% nếu tính theo hộp, và 75–83% nếu
      lấy mẫu lại theo khung. Nhưng cả 11 khung thuộc 2 ngày liền nhau và cùng một cách xếp hàng, nên chưa nói được gì
      về ngày khác hay cách xếp khác.
    - Bảng theo SKU chỉ có tỉ lệ "model gọi X thì đúng bao nhiêu". Với Nguyên bản tỉ lệ này là 62.5%, trong khi tỉ lệ
      "lon X thật được gọi đúng" chỉ là 24%.
    - Chưa khung nào có điểm sót. Thế nhưng khung 17:44 có ít nhất 3 lon ở tầng dưới, và 1 lon đỏ ở khay trên bị che
      một nửa, mà model không vẽ khung nào.

## hoang đã chọn (24/11)

- **Phạm vi A: "hàng đang có" là các lon ở khay trên thấy được mặt hoặc nắp.** Áp cho tiệm khác theo cùng nguyên tắc:
  hàng thấy được trong vùng trưng bày. Lon ở tầng dưới và lon khuất phía sau không tính.
  - Khớp với Data Dictionary: cột `unit_count` của CV Output ghi *"Count of individual visible units on shelf"*.
  - Khác với Human Audit: xem "Khác biệt với nguồn" ở cuối.
- **Thứ tự:** làm phần chung trước (không đo được thì không tính là 0; đo cho đúng; web nói rõ mức tin cậy), rồi đến
  Cách 2.
- **Đồng ý sửa luật trong `TRAINING.md`**, từ "không bao giờ train trên ảnh audit" thành "không bao giờ dạy bằng khung
  dùng để chấm điểm". Mỗi giờ có 1 khung để chấm điểm và 1 khung để dạy.

## Phương án sửa lỗi nhầm vị

hoang chọn Cách 2.

- **Cách 1 — Chỉnh số sau model, không đụng model.** Dùng bảng nhầm lẫn để điều chỉnh số, cộng thêm nhớ vị theo vị trí
  lon. Loại vì:
  - lỗi đổi theo thời điểm, nên hệ số cố định sai cả buổi chiều lẫn buổi sáng;
  - 21 lon Nguyên bản đã chấm là quá ít để ước lượng hệ số;
  - nhớ theo vị trí hỏng mỗi khi tiệm xếp lại (23/11 và 24/11 đã xếp khác nhau);
  - Validation Card vẫn hiện sai vị từng lon.
- **Cách 2 — YOLO vẫn tìm lon, thêm bước đối chiếu từng lon với kho ảnh lon thật của tiệm. Chọn.**
  - Giống cách pipeline sữa đang làm: `carton_recognition/recognize.py` và `enroll.py`, vector trong LanceDB. Thêm ảnh
    vào kho là nhận tốt hơn, không phải train lại.
  - Sửa đúng chỗ hỏng: tìm lon đã tốt, chỉ gọi tên sai.
  - Đúng với Feedback Loop của Datagent.
- **Cách 3 — Train lại YOLO Slide bằng ảnh thật.** Loại vì:
  - phải vẽ khung cho mọi lon, trong khi màn hình chấm chỉ có điểm cho lon sót;
  - tốn công chấm gấp nhiều lần;
  - mỗi lần cải thiện là một lần train lại;
  - dễ làm hỏng phần tìm lon đang chạy tốt.

## Mục tiêu

- Lúc không thấy tủ (cất tủ, bị che, camera lệch, hub tắt) thì ghi "không đo được". Không bao giờ thành 0, OOS hay
  RESTOCKED.
- Trả lời được bằng số, kèm khoảng tin cậy và n, hai câu hoang hỏi:
  - hệ thống báo đúng SKU nào đang có, SKU nào không, đến mức nào;
  - mỗi SKU được gọi đúng bao nhiêu (cả hai chiều), theo buổi trong ngày.
- Đo được tỉ lệ cảnh báo kệ đúng, vì đó là con số khách hàng cảm nhận.
- Người xem web biết SKU nào đáng tin, SKU nào chưa.
- Lỗi Nguyên bản bị gọi là Phô mai hoặc Hot được sửa tận gốc. Bản sửa chỉ được bật khi đã chứng minh bằng khung để
  riêng.
- Mỗi khung chấm thêm đều làm hệ thống tốt lên (Feedback Loop).

## Không làm (bản này)

- Không train lại YOLO (Cách 3).
- Không đếm tầng dưới hay lon khuất (phạm vi A).
- Không nhập Human Audit của Datagent. Không gửi cảnh báo qua email, Slack hay SNS.
- Không đổi cột hay định dạng CV Output, CSV, Capture Log. Không đổi công thức 12 KPI.
- Không xử lý 12 SKU sữa mà tiệm không bán (không nằm trong danh sách phải có của DEMO-S01).
- Không dùng bộ phát hiện người để giảm trọng số lần kiểm có người đứng che. Để sau.
- Không có màn hình vẽ vùng tủ trong Settings. Vùng tủ đặt trong `worker.env`.

## Không được xảy ra

- Không có số giả. Chỗ chưa đủ mẫu thì ghi "Chưa đủ mẫu" kèm n, không hiện %.
- Không dạy kho ảnh bằng khung chấm điểm (`AUD-…`) hay `slide_pilot\test_frames`.
- "Không đo được" không bao giờ được tính là có hàng, hết hàng hay bổ sung hàng.
- Không giấu khoảng không đo được: biểu đồ để trống, các ô ghi số giờ không đo được.
- Không đưa ảnh tiệm vào repo (repo public), kể cả ảnh dùng để kiểm thử.
- Không bật kho ảnh trên worker khi chưa qua cổng ở mục 2.3.

## Thiết kế

### 1. Phần chung

#### 1.1 Không đo được thì không tính là 0

**a. Giờ bày hàng (làm ngay, không cần code).** team_admin sửa giờ của DEMO-S01 trong Settings theo giờ tủ thật sự
được bày. Giờ cụ thể do hoang quyết; ngày 23/11 tủ được cất khoảng 20:40. Lưu xong, hệ thống tự tính lại 15 ngày.

**b. Worker báo có thấy tủ hay không.**
- Biến mới `MILK_DISPLAY_ZONE=x,y,w,h`: vùng tủ trưng bày, tính bằng phần của khung hình như `MILK_ROI`. Không đặt
  thì không kiểm, và mọi capture được coi là thấy tủ như hiện nay.
  - CAM-S01-A: khoảng x 860–1480, y 120–640 trên khung 2560×1440.
- Mỗi capture được so vùng tủ với một bộ ảnh mẫu, ra `display_score` từ 0 đến 1 và `display_visible`
  (`display_score` ≥ `MILK_DISPLAY_MIN`).
- Bộ ảnh mẫu tự cập nhật, vì tiệm dời tủ mỗi ngày (sáng 24/11 tủ đặt lệch so với 23/11):
  - Capture có ít nhất 3 hộp hàng với độ tin cậy ≥ 0.8 nằm trong vùng tủ thì vùng tủ của nó thành một mẫu.
  - Giữ khoảng 50 mẫu mới nhất, rải đều theo giờ.
  - Mẫu lưu ra file cạnh `worker.env`, để khởi động lại không mất.
  - Chưa có mẫu nào thì coi là thấy tủ.
- Record gửi hub có thêm `display_score` và `display_visible`.
  - Hub không cần sửa, vì nó ghi nguyên record ra `results/*.json`.
  - Ingest (`_normalize_record`, bảng captures) đọc thêm 2 trường. Bản ghi cũ không có 2 trường này thì coi là thấy
    tủ.
- **Đã thử trên chuỗi 60 khung ngày 23–24/11**, mỗi 10 phút một khung. Mẫu là 3 khung ngày 23/11, lúc 14:10, 17:40 và
  20:20.
  - Độ giống màu (histogram H-S): 0.58–1.00 khi có tủ, kể cả các khung sáng 24/11; 0.17–0.37 khi tủ đã cất.
  - Độ giống hướng cạnh: ≥ 0.94 khi có tủ, ≤ 0.86 khi tủ đã cất.
  - So điểm đặc trưng ORB hỏng khi tủ bị dời: 12–17 điểm khớp vào sáng 24/11, so với 532–1500 ngày 23/11.
  - Đề xuất: so màu, `MILK_DISPLAY_MIN` = 0.5. Người làm được đổi cách so, miễn đạt bài kiểm ở mục 3.

**c. Lần kiểm đo được** (`backend/shelf.py`, `shelf_tick`):
- Chỉ capture thấy tủ được dùng để đếm.
- Lần kiểm 5 phút là *đo được* khi ít nhất một nửa số capture trong đó thấy tủ. Ngược lại, ghi `measurable = false`
  với lý do `display_not_visible`.
- Lần kiểm không đo được vẫn lưu `check#`, như lần ngoài giờ mở cửa. Nó không đổi trạng thái kệ và không tính vào OSA.
- **Qua khoảng trống** *(tôi chốt; ngưỡng đề xuất 30 phút)*. Khoảng trống là quãng hơn 30 phút giữa 2 lần kiểm đo được
  liền nhau. Nó xảy ra khi tiệm đóng cửa qua đêm, hub tắt, worker dừng, đang chuyển máy, hoặc không thấy tủ.
  - Trạng thái kệ giữ nguyên qua khoảng trống. Lần kiểm đo được đầu tiên sau khoảng trống được so với lần cuối trước
    khoảng trống, theo đúng quy tắc 2 lần kiểm liền nhau.
  - Sự kiện có lần kiểm x1 nằm ngay sau một khoảng trống được đánh dấu `after_gap`, kèm `gap_from` và `gap_to`. Web ghi
    "trong khoảng hh:mm–hh:mm (không đo được)", vì không biết thay đổi xảy ra lúc nào trong khoảng đó.
  - Phút hết hàng chỉ tính các phút đo được, như hiện nay.
  - Vì sao không đặt lại trạng thái mỗi sáng: làm vậy sẽ mất các lần bổ sung hàng qua đêm, nên Restock Volume và
    Restock Rate thấp hơn thật. Khi đã có kiểm thấy tủ và giờ bày hàng đúng, so lần đo cuối buổi tối với lần đo đầu
    buổi sáng là hợp lệ.
- Số tổng hợp theo giờ và theo ngày có thêm `unmeasured_checks`: số lần kiểm trong giờ mở cửa mà không đo được.
- API `kpi`, `reports/trends` và `reports/series` trả thêm số giờ không đo được. Dashboard ghi "x giờ không đo được"
  cạnh OSA. Biểu đồ để trống những giờ đó, không vẽ về 0.
- **Products:** capture không thấy tủ thì không cập nhật `latest_stock` và hàng chờ duyệt. Trang hiện một dòng, ví dụ
  "CAM-S01-A không thấy tủ từ 20:45 — số dưới đây là lần đo cuối lúc 20:40".
- Triển khai xong thì tính lại 15 ngày của DEMO-S01, bằng cờ `shelf_recompute_requested_at` như khi lưu kế hoạch kệ.

#### 1.2 Đo cho đúng

**a. Luật chấm theo phạm vi A** (hiện ngay trên màn hình chấm):
- Đếm: lon thuộc danh mục ở vùng trưng bày (DEMO-S01: khay trên tủ kính), thấy được mặt hoặc nắp, đủ để người chấm
  nhận ra vị.
- Không đếm: tầng dưới, lon khuất hẳn, lon không nhận ra vị.
- **Verdict mới "Ngoài phạm vi"** (`out_of_scope`) *(tôi chốt)*, dành cho hộp model vẽ trên một lon thật mà luật A
  không đếm: lon ở tầng dưới, lon khuất gần hết, lon không nhận ra vị.
  - Vòng bấm: chưa chấm → `correct` → `wrong_sku` → `not_product` → `out_of_scope` → chưa chấm.
  - Hộp `out_of_scope` không vào số thật, và bị bỏ khỏi mọi chỉ số (12 KPI và các chỉ số mới), coi như không có. Công
    thức 12 KPI không đổi.
  - Hộp này không xuất sang kho ảnh, kể cả dưới dạng một vị hay dạng `none`. Nếu chấm là `not_product` thì kho sẽ học
    cách từ chối lon thật.
  - Số đếm trên kệ chưa đổi theo verdict này, vì trên các khung đã xem, model không vẽ khung nào ở tầng dưới. Trang
    Model hiện tỉ lệ hộp `out_of_scope`. Nếu tỉ lệ này vượt 5% thì thêm một vùng đếm để bỏ các hộp ngoài khay trên.
- Trước khi Save, người chấm phải tích ô "Đã kiểm tra lon bị sót". Nghĩa là đã thêm điểm sót, hoặc xác nhận không có
  lon nào sót.
- Khung chấm theo luật này lưu `label_rule = "A"`.
- 11 khung cũ được chấm lại theo luật A. Trang Model ghi chú những khung chưa chấm lại.

**b. Khung chấm điểm và khung dạy:**

| Loại | Mã | Chọn | Dùng cho |
|---|---|---|---|
| Khung chấm điểm | `AUD-<camera>-<YYYYMMDD>-<HH>` (như hiện nay) | 1 khung mỗi camera-giờ trong giờ mở cửa, ngẫu nhiên trong mọi capture của giờ đó | Chỉ để tính chỉ số |
| Khung dạy *(mới)* | `TRN-<camera>-<YYYYMMDD>-<HH>` | 1 khung mỗi camera-giờ trong giờ mở cửa, ngẫu nhiên trong các capture thấy tủ, khác capture của khung chấm điểm | Chỉ cho kho ảnh (mục 2), không bao giờ vào chỉ số |

- **Chọn khung chấm điểm** *(tôi chốt)*:
  - Tiệm chưa đặt giờ mở cửa thì lấy mọi giờ có capture, như hiện nay.
  - Khung chấm điểm không lọc theo kiểm thấy tủ, để còn đo được chính phần kiểm thấy tủ (mục 1.2c).
  - Khung chấm điểm không thấy tủ (tủ đã cất, bị che hết, camera lệch) thì người chấm bỏ qua với lý do mới "Không thấy
    tủ" (`display_away`), không chấm thành toàn 0. Khung bỏ qua không vào chỉ số nào.
  - Lý do: chấm thành 0 sẽ thêm các cặp "model 0 / thật 0", làm các chỉ số có/không đẹp giả.
- Cả hai dùng chung bảng `audits` và màn hình chấm. Màn hình ghi rõ loại khung, và hàng chờ đưa khung chấm điểm lên
  trước.
- Lịch chọn khung chạy cùng lần chạy hằng giờ đang có.
- Luật mới trong `TRAINING.md` trên HUYHOANG (hoang đồng ý 24/11): *"Không bao giờ train hay đưa vào kho ảnh:
  `slide_pilot\test_frames` và khung chấm điểm `AUD-…`. Khung dạy `TRN-…` thì được."*
- **Nhịp chấm** *(đề xuất)*:
  - 3 ngày đầu chấm hết cả hai loại khung trong giờ bày hàng: khoảng 24 khung, khoảng 35 phút mỗi ngày.
  - Sau đó ưu tiên khung chấm điểm; khung dạy chấm khi có thời gian.

**c. Chỉ số trên trang Model.** Mọi chỉ số chỉ tính từ khung chấm điểm `done`.
- **Theo SKU, hai chiều:**
  - *Gọi tên đúng* (đã có, `id_accuracy`): số hộp model gọi X mà đúng ÷ số hộp model gọi X.
  - *Tìm ra đúng* (mới): số lon X mà model gọi đúng ÷ số lon X thật. Số lon thật gồm hộp `correct` của X, hộp
    `wrong_sku` có vị thật là X, và điểm sót của X.
  - *Lệch số lon mỗi khung* (mới): trung bình của (số model − số thật). Dương là đếm dư, âm là đếm thiếu.
- **Báo đúng có/không** (mới). Mỗi cặp khung × SKU là một mẫu. Xét các SKU trong danh sách phải có của tiệm, cộng các
  SKU có số model hoặc số thật > 0.
  - *Báo đúng có/không*: tỉ lệ cặp mà model và người cùng nói có, hoặc cùng nói không.
  - *Báo hết sai*: model nói 0 mà thật > 0, chia cho số cặp model nói 0.
  - *Bỏ sót hết hàng*: model > 0 mà thật = 0, chia cho số cặp thật = 0.
- **Mức lần kiểm** (mới): so số của lần kiểm 5 phút chứa khung chấm điểm (đây là số Dashboard dùng) với số thật của
  khung đó. Tính lệch số lon và báo đúng có/không. Lần kiểm không đo được thì không so.
- **Kiểm thấy tủ có đúng không** (mới): so khung chấm điểm với `display_visible` của capture đó.
  - Khung được chấm nghĩa là thấy tủ. Khung bỏ qua với lý do "Không thấy tủ" nghĩa là không thấy.
  - Ra tỉ lệ đúng, số lần báo nhầm "không thấy" và số lần báo nhầm "thấy".
  - Hiện trong Live health.
- **Theo buổi:** sáng (trước 12:00), chiều (12:00–17:00), tối (từ 17:00). Lý do: lỗi đổi theo thời điểm.
- **Khoảng tin cậy 95%** cho mọi tỉ lệ và trung bình. Lấy mẫu lại theo khung (bootstrap theo khung), vì các hộp trong
  cùng khung không độc lập. Hiện theo dạng "78.7% (75–83%, n = 11 khung)". Đây là số tính trên 11 khung hiện có.
  - Khoảng này chỉ phản ánh dao động giữa các khung đã chấm, không phản ánh những ngày hay cách xếp chưa gặp.
  - Vì vậy luật "Chưa đủ mẫu" đòi các khung có lon thật phải trải trên ít nhất 2 ngày.
- **"Chưa đủ mẫu"** khi có dưới 10 khung, dưới 20 lon thật của SKU đó, hoặc mọi khung có lon thật của SKU đó thuộc
  cùng 1 ngày *(đề xuất)*.
- **12 KPI của Datagent** giữ nguyên công thức, chỉ thêm khoảng tin cậy và n.

**d. Xác nhận sự kiện kệ** (mới):
- Trong Recent Shelf Activities và danh sách đầy đủ, mỗi sự kiện có:
  - nút "Xem ảnh": 1 ảnh của lần kiểm đo được ngay trước sự kiện, và 1 ảnh của lần kiểm sự kiện;
  - 3 nút Đúng / Sai / Không rõ, cho `team_admin` và `field_team`. `datagent` chỉ xem.
- Kết quả xác nhận lưu riêng theo `event_key`. Nó vẫn còn khi tính lại xoá hay đổi sự kiện, để so được trước và sau
  mỗi thay đổi (ví dụ: các sự kiện đã đánh Sai mà luật mới bỏ đi).
- Ô **"Cảnh báo đúng"** trên Dashboard: theo từng loại sự kiện, số Đúng ÷ số đã xác nhận, kèm n. Dưới 10 sự kiện đã
  xác nhận thì ghi "Chưa đủ mẫu".
- Kết quả "Không rõ" không tính vào tử số, mẫu số hay ngưỡng 10 sự kiện. Số "Không rõ" hiện riêng *(tôi chốt)*.
- **Giữ ảnh của sự kiện** (hoang chọn cách A, 24/11):
  - Khi sinh một sự kiện, Lambda ingest chép 2 ảnh từ bucket hub sang bucket analytics, vào prefix
    `shelf-events/frames/`. Ảnh thứ nhất là một capture của lần kiểm đo được ngay trước sự kiện. Ảnh thứ hai là một
    capture của lần kiểm x1.
  - Để làm được việc đó, mỗi item `check#` lưu thêm `image_key` và `source_bucket` của một capture có ảnh.
  - Prefix này có lifecycle xoá sau 90 ngày, bằng thời gian giữ sự kiện. Lifecycle được thêm vào change set.
  - Khi tính lại, ảnh đã có thì không chép lại. Sự kiện cũ hơn 7 ngày mà ảnh ở hub đã bị xoá thì trang ghi "ảnh không
    còn"; sự kiện vẫn được ghi.
  - Kết quả xác nhận Đúng / Sai / Không rõ được giữ không hạn, vì rất nhỏ và cần để so trước và sau mỗi thay đổi.
  - Ước tính: khoảng chục sự kiện mỗi ngày, mỗi sự kiện 2 ảnh khoảng 1 MB. Tổng dưới 2 GB trong 90 ngày, tốn chưa tới
    0.1 USD mỗi tháng.

#### 1.3 Web nói rõ mức tin cậy

**Nhãn tin cậy của mỗi SKU** *(ngưỡng là đề xuất)*. Tính trên khung chấm điểm của 14 ngày gần nhất, đúng một chu kỳ
Datagent:

| Nhãn | Khi |
|---|---|
| Chưa đủ mẫu | dưới 10 khung, dưới 20 lon thật, hoặc mọi khung có lon thật thuộc cùng 1 ngày |
| Cao | cận dưới khoảng tin cậy của cả "gọi tên đúng" và "tìm ra đúng" ≥ 90% |
| Trung bình | cả hai cận dưới ≥ 70% |
| Thấp | các trường hợp còn lại |

- **Hiện ở:**
  - Products: cạnh tên SKU. Bấm vào ra chi tiết, ví dụ "tìm ra đúng 24% · 21 lon · 9 khung · hay bị gọi thành Phô
    mai".
  - Dashboard: cạnh SKU trong danh sách sự kiện.
  - Trang Model: trong bảng theo SKU.
- Sự kiện của SKU mang nhãn Thấp được ghi thêm "chưa chắc" *(đề xuất)*.
- Mọi nhóm thấy nhãn, kể cả `datagent`. Cách này theo quyết định của hoang ngày 24/11 cho ô Top 50 SKU Accuracy.

### 2. Sửa nhầm vị bằng kho ảnh lon thật (Cách 2)

**2.1 Khi nào bắt đầu** *(đề xuất)*: khi có ít nhất 30 khung dạy `done`, trải đủ sáng, chiều và tối.

**2.2 Dựng kho:**
- **Xuất lon:** script trong repo, chạy trên laptop vì HUYHOANG không giữ khoá AWS.
  - Đọc các khung dạy `done` và ảnh của chúng ở bucket analytics.
  - Cắt từng hộp theo `ai_boxes` và gán vị thật: `correct` lấy nhãn model; `wrong_sku` lấy `true_sku_id`;
    `not_product` gán `none`, để kho học cách từ chối.
  - Điểm sót không có khung nên không dùng.
  - Ghi lon cắt ra và một manifest ra thư mục ngoài repo, rồi chép sang HUYHOANG.
- **Kho** trên HUYHOANG, làm theo `carton_recognition/enroll.py` và `recognize.py`:
  - Mỗi lon thành một vector, bằng embedder.
  - Dùng một kho riêng cho Slide, không đụng kho sữa.
- **Worker** (`server/milk/slide_adapter.py`): sau YOLO và bước bỏ khung trùng, mỗi hộp được đối chiếu với kho.
  - Kho đồng ý với YOLO thì giữ nguyên.
  - Kho chắc chắn là một vị khác (tỉ lệ phiếu và độ giống đủ cao) thì đổi vị theo kho.
  - Kho không chắc, hoặc thấy hộp giống `none` hơn, thì giữ vị của YOLO nhưng hạ độ tin cậy của hộp xuống dưới 0.70.
    Vì KPI #10 tính theo từng hộp, cách này đưa KPI #10 (độ tin cậy của hộp sai < 0.5) lại gần mục tiêu.
  - Cờ và hàng chờ duyệt vẫn tính theo dòng, tức trung bình các hộp, như CV Output hiện nay *(tôi chốt)*.
    - Vì vậy, một hộp bị hạ điểm giữa nhiều hộp chắc chắn thường không làm dòng bị cờ.
    - Những hộp đó hiện trên trang Model, qua tỉ lệ "kho và YOLO không đồng ý".
    - Không đổi cách tính điểm dòng, để CV Output gửi Datagent giữ đúng nghĩa của ngưỡng 0.7.
  - Mỗi hộp Slide ghi thêm nhãn YOLO gốc (`yolo_sku_id`) và kết quả đối chiếu: vị kho chọn, tỉ lệ phiếu, độ giống. Nhờ
    vậy, cổng của bản sau so được trên đúng các hộp đó.
  - Bật bằng `MILK_SLIDE_GALLERY=<đường dẫn kho>`. Không đặt thì chạy như hiện nay.
  - `MILK_MODEL_VERSION` thêm hậu tố, ví dụ `long-2026-10-13+slide-v3+gallery-20261128`.
  - `detection_method` vẫn là "Visual". Data Dictionary chỉ cho các giá trị Visual / OCR / Visual + OCR / Barcode.

**2.3 Cổng bật.** Chạy trên HUYHOANG, không cần chạy lại YOLO.
- Mỗi bản kho có một ngày cắt D: kho chỉ chứa khung dạy trước ngày D. Cổng chấm trên các khung chấm điểm `done` từ
  ngày D trở đi.
- Cắt các hộp đã lưu (`ai_boxes`) từ ảnh đã lưu, rồi đối chiếu với kho.
- So nhãn mới với nhãn của bản đang chạy (lần đầu là YOLO gốc) và với số thật đã chấm, theo các chỉ số ở mục 1.2c.
- Chỉ bật trên worker khi thoả cả 4 điều kiện *(đề xuất)*:
  - có ít nhất 30 khung chấm điểm, trong ít nhất 2 ngày, đủ 3 buổi;
  - "Tìm ra đúng" của Nguyên bản tăng từ khoảng 24% lên ít nhất 70%;
  - không SKU nào giảm quá 5 điểm ở "gọi tên đúng" hay "tìm ra đúng";
  - KPI #1 và #2 không giảm.
- Kết quả ghi thành một báo cáo, và ghi vào Nhật ký HOANG-P10. Bật trên worker cần hoang đồng ý, như mọi lần sửa
  worker.

**2.4 Vòng phản hồi:**
- Nhịp cập nhật khoảng 3–4 ngày *(tôi chốt)*:
  1. Chọn ngày cắt mới.
  2. Dựng bản kho mới từ mọi khung dạy trước ngày cắt.
  3. Chờ đủ khung chấm điểm sau ngày cắt: ít nhất 30 khung, trong 2 ngày, đủ 3 buổi.
  4. Chạy cổng.
  5. Qua cổng thì tăng hậu tố phiên bản và bật bản mới. Chưa qua thì bản đang chạy giữ nguyên.
- Cổng cần các khung mới hơn ngày cắt, nên không thể cập nhật mỗi 1–2 ngày. Nhịp 3–4 ngày vẫn đủ yêu cầu của Datagent:
  ít nhất một lần mỗi chu kỳ 2 tuần.
- Khung dạy đã vào kho được đánh dấu `used_in_gallery = <phiên bản>`, giống trường `fed_back_to_model` trong Feedback
  Loop của Datagent. Datagent yêu cầu cập nhật ít nhất một lần mỗi chu kỳ 2 tuần.

### 3. Kiểm thử

- **pytest, phần logic thuần, không gọi AWS:**
  - Điểm thấy tủ: tính trên ảnh tổng hợp (repo không chứa ảnh tiệm). Gồm: bộ mẫu tự cập nhật, chưa có mẫu thì coi là
    thấy tủ, và tìm vùng tủ bằng `MILK_DISPLAY_ZONE`.
  - Lần kiểm: dưới một nửa số capture thấy tủ thì không đo được.
  - Qua khoảng trống: trạng thái giữ nguyên; sự kiện ngay sau khoảng trống mang dấu `after_gap`; phút hết hàng chỉ
    tính phút đo được.
  - Hộp `out_of_scope` bị bỏ khỏi mọi chỉ số và không xuất sang kho. Khung bỏ qua với lý do `display_away` không vào
    chỉ số. Kết quả "Không rõ" không tính vào tỉ lệ cảnh báo đúng.
  - `unmeasured_checks` có trong số tổng hợp theo giờ và theo ngày.
  - `audit_scoring`:
    - các chỉ số "tìm ra đúng", "báo đúng có/không", "báo hết sai", "lệch số lon", và chia theo buổi;
    - bootstrap có seed, nên chạy lại ra cùng kết quả;
    - "Chưa đủ mẫu";
    - khung dạy không bao giờ vào chỉ số.
  - Ca 23/11 dựng tay (17:44: 3 Nguyên bản bị gọi là Phô mai) cho ra "báo hết sai" và "tìm ra đúng" đúng như tính tay.
- **pytest + moto:**
  - Ingest lưu 2 trường thấy tủ. Capture không thấy tủ thì không cập nhật `latest_stock`.
  - `shelf_tick` chạy với lần kiểm không đo được.
  - Chọn khung dạy: khác capture của khung chấm điểm, chỉ lấy capture thấy tủ, và chạy lại không tạo thêm.
  - API xác nhận sự kiện: lưu được; vẫn còn sau `shelf_recompute`; `datagent` nhận 403 khi xác nhận.
  - Ảnh sự kiện: sinh sự kiện thì chép đủ 2 ảnh; tính lại không chép trùng; ảnh ở hub đã mất thì sự kiện vẫn được ghi,
    chỉ không có ảnh.
- **node --test:** luật gán nhãn tin cậy, cách hiện khoảng tin cậy, và cách để trống biểu đồ.
- **Kiểm trên dữ liệu thật**, ngoài repo, bằng script đọc từ S3 lúc chạy:
  - Chuỗi 60 khung ngày 23–24/11: mọi khung từ 20:50 đến 22:00 ra "không thấy tủ"; mọi khung từ 12:40 đến 20:40 và
    sáng 24/11 ra "thấy tủ".
  - Tính lại ngày 22–24/11, với giờ bày hàng đóng trước 20:40:
    - Các sự kiện do cất tủ (20:40), hub mới bật (12:40) và hộp ảo đêm 22/11 không còn.
    - Các sự kiện lúc 08:45 sáng 24/11 vẫn còn, nhưng mang dấu "sau khoảng không đo", vì tiệm đã xếp lại tủ qua đêm.
    - Dữ liệu cũ chưa có điểm thấy tủ, nên phần lúc 20:40 dựa vào giờ bày hàng.
- **Trình duyệt**, như các lần trước: màn hình chấm có luật và ô bắt buộc; xác nhận một sự kiện; nhãn tin cậy hiện trên
  Products và Dashboard.
- **Phần 2:** báo cáo cổng bật ở mục 2.3.

### 4. Triển khai

Thứ tự *(đề xuất)*. Mỗi bước bật xong thì dùng được ngay:

0. Ngay khi hoang quyết giờ: team_admin sửa giờ bày hàng của DEMO-S01 (mục 1.1a).
1. Khung dạy, luật chấm và ô "đã kiểm tra lon sót" (mục 1.2a, 1.2b). Làm trước để team bắt đầu chấm sớm nhất.
2. Thấy tủ và khoảng trống, ở worker, ingest và shelf (mục 1.1b, 1.1c). Sau đó tính lại 15 ngày.
3. Chỉ số hai chiều, báo đúng có/không, chia theo buổi, khoảng tin cậy (mục 1.2c).
4. Xác nhận sự kiện (mục 1.2d).
5. Nhãn tin cậy trên web (mục 1.3).
6. Phần 2, khi đủ khung dạy.

Cách làm như các lần trước:
- **Backend:** change set cho `milk-backend-development`, **không** truyền `--tags`. Change set thêm lifecycle 90 ngày
  cho prefix `shelf-events/frames/` của bucket analytics. Code Lambda đưa lên `releases/backend/<sha>/`.
- **Frontend:** deploy tay lên Amplify.
- **Worker trên HUYHOANG:** sao lưu trước. Thêm `MILK_DISPLAY_ZONE` và `MILK_DISPLAY_MIN`, rồi khởi động lại task
  `milk-worker`. Cần hoang đồng ý.
- **Giới hạn 10 Lambda chạy cùng lúc:** Dashboard có thêm lời gọi thì gộp vào lời gọi đang có, đừng thêm lời gọi song
  song.
- Sửa `TRAINING.md` trên HUYHOANG.
- Ghi Nhật ký HOANG-P10 sau mỗi bước.

## Khác biệt với nguồn (để hoang biết)

1. **Human Audit của Datagent đếm mọi đơn vị trên kệ.** `unit_count_shelf` ghi *"Units on shelf counted by human …
   This is the GROUND TRUTH for shelf stock"*. Phạm vi A chỉ đếm lon thấy được, khớp với cột `unit_count` của CV Output
   (*"visible units"*).
   - Khi nhập Human Audit sau này, số đơn vị của mình sẽ thấp hơn ở những lon bị khuất.
   - OSA và hết hàng gần như không đổi.
   - Ví dụ ghi chú trong sheet (*"Product partially hidden behind display stand"*) cho thấy Datagent đã tính trước khác
     biệt này.
2. **Spec trang Model ngày 23/11 ghi "Không xuất dữ liệu huấn luyện".** Phần 2 nay xuất lon cắt ra để đưa vào kho ảnh,
   không xuất theo định dạng YOLO.
3. **`TRAINING.md` cấm train trên ảnh audit.** Đổi theo quyết định của hoang ngày 24/11, xem mục 1.2b.
4. **Spec Dashboard ngày 24/11 ghi "Không đọc độ sáng khung hình. Để sau."** Phần kiểm thấy tủ thay cho việc đó, và
   bắt được cả khung quá tối, vì khung tối không giống ảnh mẫu.

## Để người làm tự quyết

- Cách so vùng tủ và ngưỡng, miễn đạt bài kiểm trên chuỗi 60 khung.
- Số lần lấy mẫu của bootstrap, và cách giữ API nhanh: dưới 3 giây cho 30 ngày khung chấm.
- Embedder dùng cho kho (bản sữa đã fine-tune hay DINOv2 gốc), cách lưu kho (LanceDB hay tệp vector), số láng giềng và
  ngưỡng phiếu, miễn qua cổng ở mục 2.3.
- Chi tiết giao diện: vị trí nút, màu nhãn, chữ chú thích. Bám theo các trang hiện có.
- Chia module.
