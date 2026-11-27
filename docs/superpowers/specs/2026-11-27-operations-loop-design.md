# Vòng vận hành lâu dài: gán nhãn, train và đưa model lên chạy thật — thiết kế

Ngày 27/11/2026. Trạng thái: hoang duyệt ngày 27/11 (*"ok duyệt"*). Kế hoạch phần 1: `docs/superpowers/plans/2026-11-27-operations-loop-part1-backbone.md`.

Đây là bản thiết kế chung cho cả vòng: mỗi phần làm gì và nối với phần khác thế nào. Năm phần ở mục 5 được lên kế hoạch và làm lần lượt, mỗi phần một kế hoạch riêng.

Liên quan:
- `2026-11-25-auto-label-design.md`: tự gán nhãn, frame review, cổng 1 và cổng 2. Đã xây phần 1, 2a, 2b.
- `2026-11-26-common-read-path-design.md`: đường đọc "tìm → xác nhận → gộp cửa sổ" và luật "bước xác nhận phải tự chứng minh" (mục 5.5).
- `2026-11-25-slide-fusion-gallery-design.md`: kho ảnh màu của Slide và bước gộp frame.
- `2026-11-23-model-quality-page-design.md`: trang Model, frame chấm điểm.
- `2026-11-25-th-store-view-design.md`: cách chia đoạn, lan nhãn và cổng của sữa TH.

## 1. Vì sao làm

**hoang nêu ngày 27/11:**
- Gán nhãn và train là việc lặp đi lặp lại. Giảm được công đó thì team có thời gian cho việc khác, ví dụ lấy mẫu và render model 3D, và team vận hành cải thiện được model theo thời gian mà không phải làm tay liên tục.
- Teammate và client dùng thử website nói: *"hàng ngày họ lên website thường lên bấm phần review reading và label frame thì không biết là những gì họ làm có được sử dụng để tự động cải thiện model không"*.
- Mọi sản phẩm, cũ hay mới, đều đi một đường: model 3D, ảnh tổng hợp, rồi đưa lên chạy thử. *"Đó là cách chúng tôi luôn làm chưa đổi."*

**Hiện trạng, kiểm ngày 27/11:**
- **Công của người đi vào ba chỗ tách rời.**
  - Trang Model: 45 frame chấm điểm và 22 frame dạy đã gán, 17 frame chờ. Frame chấm điểm đang được dùng để tính số trên trang Model. Nhãn của 22 frame dạy chưa vào lần train nào.
  - Keyframe vẽ tay ngoài website: 64 cái của TH đã dùng để train; 18 cái của Slide mới dùng để đo.
  - Review reading trên trang Category: sáng 27/11 có 14 lượt lưu, không lượt nào đổi tên hay số lượng, ba mục bị lưu hai lần. Trường `fed_back_to_model` chỉ từng được ghi `false`, không có gì đọc nó.
- **Tự gán nhãn** đã xây và qua cổng 1 ngày 26/11, nhưng chưa chạy thật lần nào: 4 frame cần người xem chưa được đẩy lên trang Model, Slide chưa được train bằng ảnh thật.
- **Thêm sản phẩm** mới làm thật một lần (TH, 25–26/11, khoảng một ngày rưỡi). Mọi bước là lệnh chạy tay qua ssh. Hướng dẫn nằm trong `TRAINING.md` trên HUYHOANG, ngoài repo.
- **Đưa model lên:** chép file model, sửa `worker.env`, khởi động lại task `milk-worker`. Quay lui bằng nhánh và file sao lưu.
- **Một máy** HUYHOANG vừa đếm thật vừa train.

**Tài liệu của team nói gì:**
- Data Dictionary, Accuracy Report phần C: mỗi lần sửa có trường `fed_back_to_model`, và *"Tech Partner should retrain the model at least once per bi-weekly cycle using all accumulated corrections."* README bước 6: *"Discrepancies feed back as training corrections for the CV model"*.
- Architecture design (bản 7, 07/11):
  - chuỗi model là "tìm hộp bằng YOLO, tra SKU bằng DINOv2-S và kho LanceDB";
  - train lại hai tuần một lần, và *"model mới chỉ được dùng nếu điểm trên tập kiểm định cố định không giảm"*;
  - *"Thêm SKU thì phải train lại model"*;
  - công cụ dự kiến: SageMaker Pipelines, Model Registry, CVAT. Các chỗ khác với bản thiết kế này ghi ở mục 6.

**Hai lần chạy thử ngày 27/11** (script và kết quả ở `C:\Users\huyho\Datagent\_ops_spike` trên HUYHOANG):

*Đặt tên sản phẩm bằng kho ảnh mẫu, không train.* Box lấy từ đáp án vẽ tay ở các ngày giữ riêng; máy đặt tên bằng cách so với kho ảnh, theo phiếu của các ảnh gần nhất. Mọi thông số được chọn trước khi xem kết quả.

| Kho ảnh gồm | Slide: gọi đúng vị, 121 lon | TH: nhận đúng là TH, 800 hộp |
|---|---|---|
| Chỉ ảnh render từ 3D | 56% ở cách tốt nhất | 34%: mặt trước 275/320, hộp chỉ thấy nắp 0/480 |
| Ảnh thật đã gán nhãn của ngày khác | 75 lon: 96% (màu), 93% (DINOv2 + màu), 69% (DINOv2), 82% (embedder của dự án) | 20 hộp: 96,5% (DINOv2 + màu), 87% (DINOv2), 67% (embedder của dự án). 100 hộp: 98%, 98%, 81% |

- Mảng nền bị gọi là sản phẩm: 0,6–1,5% khi kho chỉ có ảnh thật; 16% khi ảnh render nằm chung kho.
- Để so: model đang chạy gọi đúng vị Slide 71% (đo 25/11, trên box của chính nó).
- Giới hạn: box là box đáp án, không phải box của detector (bài thử 25/11 với box của detector đạt 85% cho Slide); một camera; mẫu "không phải sản phẩm" là mảng nền ngẫu nhiên; tầng trên của các frame giữ riêng không có lon Hot.

*Công cụ render chung.*
- BlenderProc 2.8.0 không chạy được trên HUYHOANG: Smart App Control chặn một file DLL của scipy mà nó cần.
- Blender 4.2.1 thuần chạy được: bốn file `.glb` (hai lon Slide, hai hộp sữa) nạp nguyên trạng trong 0,2 giây, mỗi ảnh 960×540 mất khoảng 1,2 giây trên RTX 5090, box nằm đúng trên sản phẩm. Ảnh đầu tiên mất thêm 6 phút, chỉ một lần.
- File 3D của hộp sữa không đúng tỉ lệ (khối 2×2×4, đáy vuông). Box của lần thử chưa xét che khuất.

**Quy trình có sẵn đã tham khảo** (hoang đồng ý đưa vào ngày 27/11):
- Hướng dẫn vận hành model của Google, mức "continuous training": các kiểu kích hoạt train lại, kiểm dữ liệu trước khi train, sổ ghi mỗi lần chạy.
- "Data engine" (Tesla, nguồn thứ cấp) và active learning cho object detection (NVIDIA): chọn frame đưa người gán bằng tín hiệu, không chọn ngẫu nhiên.
- Shadow test (AWS) và phép so cặp McNemar: chạy model mới trên bản sao dữ liệu thật, tiêu chí đặt trước, chỉ chỗ hai model khác nhau mới phân định.
- Kiểm chất lượng người gán: frame biết trước đáp án; tìm nhãn đáng ngờ sau khi train.

## 2. Mục tiêu, không làm, thất bại dù chạy

**Mục tiêu:**
1. Việc người làm trên website (label frame, review reading) đi vào model, và người làm thấy được nó đã đi vào đâu.
2. Trong trường hợp bình thường, người vận hành chỉ cần website. Không ai phải ssh hay gõ lệnh.
3. Mọi thay đổi của model lên chạy thật qua cùng một cửa: đo nhanh, chạy song song, một người duyệt. Quay lui bằng một lần bấm.
4. Sản phẩm mới vẫn bắt đầu bằng model 3D, ảnh tổng hợp và chạy thử. Phần nào máy làm được thì máy làm.
5. Model được train lại ít nhất một lần mỗi chu kỳ hai tuần, và ghi được lần sửa nào đã vào phiên bản nào.

**Không làm:**
- Không tự đưa model lên khi chưa có người duyệt.
- Không dùng nền tảng ngoài (SageMaker Pipelines, Kubeflow, MLflow, Label Studio, CVAT).
- Không tắt Smart App Control, không cài gì vào `.venv` của worker.
- Không dùng review reading làm nhãn train trực tiếp: nó không có box.
- Không đổi định nghĩa các KPI.
- Không xây cho nhiều client. Không vẽ lại kiến trúc tổng; đó là việc mở riêng.
- Bước gộp frame trong cửa sổ lấy mẫu thuộc thiết kế common-read-path, không thuộc bản này.

**Thất bại dù vẫn chạy:**
- Frame chấm điểm (`AUD-`) hoặc frame giữ riêng lọt vào tập train hay kho ảnh.
- Kho ảnh nhận nhãn tự động hoặc ảnh render.
- Kết quả của model ứng viên lọt lên Dashboard, Category, CV Output, review queue hay các sự kiện kệ.
- Người chấm biết box nào của model nào, hoặc thấy gợi ý ở box hai model đang nói khác nhau.
- Tiêu chí thắng được chọn sau khi đã thấy số.
- Hàng chờ của người bị ngập.
- Chạy song song hoặc train làm worker chậm hay chết.
- Website nói "nhãn của bạn đã được dùng" khi nó chưa được dùng.
- Quy trình chạy đều nhưng người làm không thấy gì đổi.

## 3. Ràng buộc

**Máy HUYHOANG:**
- RTX 5090 32 GB, dùng chung cho worker (khoảng 8–10 GB), các lần train (khoảng 19 GB với batch 12, ảnh 1280) và người dùng máy.
- Smart App Control đang bật: DLL mới cài có thể bị chặn (torch, scipy). Môi trường riêng mượn torch của `.venv` qua file `.pth` là cách đã chạy được.
- Không ghi đè file worker đang dùng (`TRAINING.md`).

**Quyền và tiền:**
- HUYHOANG đã có quyền AWS (hoang, 27/11: *"máy HUYHOANG có rồi"*). Kiểm ngày 27/11: `%USERPROFILE%\.aws` có profile `milk`, vùng `ap-southeast-1`. AWS CLI chưa cài trên máy đó, và chưa có lệnh gọi AWS nào được thử bằng profile này. Câu "chỉ laptop có quyền AWS" trong thiết kế auto-label (25/11) không còn đúng.
- Tài khoản AWS chạy tối đa 10 Lambda cùng lúc.
- Ảnh worker gửi về hub tốn tiền truyền dữ liệu. Worker đang đọc luồng 30 giây mỗi 5 phút để giảm tiền.

**Dữ liệu:**
- S3 giữ frame của hub 30 ngày. Frame `AUD-`, `TRN-`, `REV-` được giữ không thời hạn.
- Một tiệm, một camera (DEMO-S01, CAM-S01-A). Danh mục sản phẩm theo từng tiệm, lấy từ `sku_master`; không viết cứng danh sách sản phẩm.
- Ảnh tiệm, nhãn, kho ảnh và model không vào repo hay OneDrive.

**Luật đã có, giữ nguyên:**
- Frame `AUD-` và tập giữ riêng không bao giờ dùng để train, nạp kho hay chỉnh ngưỡng.
- Kho ảnh chỉ nhận nhãn của người.
- Một bước xác nhận chỉ được bật khi đã đo cả hai cách, có và không có nó, trên dữ liệu mà kho của nó chưa từng thấy.
- Box đang tranh chấp không hiện gợi ý cho người chấm.

**Website:**
- Vai trò: người xem (`datagent`), `field_team`, `team_admin`.
- Backend lên live bằng change set chỉ đổi mã, website bằng Amplify, đều làm tay và chờ hoang OK.

## 4. Các cách đã cân nhắc

**Dựng cả vòng thế nào:**

| Cách | Được | Mất |
|---|---|---|
| **A. Hai vòng: kho ảnh cộng với train định kỳ** | Việc người làm hôm nay có tác dụng sau vài ngày. Thêm một vị mới của loại hàng đã biết không cần train | Phải thêm bước tra kho vào worker và đo lại trên box của detector. Hai thứ phải quản phiên bản. Kho theo từng camera |
| B. Một vòng train định kỳ, giữ model như hiện nay | Ít đụng worker nhất, dùng ngay phần tự gán nhãn đã xây | Nhãn chỉ có tác dụng ở lần train kế, tới hai tuần. Lỗi gọi tên nằm đó cho tới khi train lại. Slide chưa từng được train bằng ảnh thật |
| Nền tảng có sẵn (SageMaker, Label Studio với MLflow) | Không phải tự viết | Website đã có màn hình gán nhãn; HUYHOANG chặn DLL lạ; thêm chi phí |

hoang chọn A ngày 27/11. Vòng chậm của A chính là cách B.

**Model mới lên chạy thật bằng cách nào:**

| Cách | Vì sao chọn hoặc loại |
|---|---|
| Tự lên khi thắng trên tập giữ riêng | Loại: với TH, bài đo đã hai lần lệch (tập giữ riêng thiếu kiểu xếp mới ngày 25/11, hàm chấm sai ngày 26/11) |
| **Máy làm tới "có model mới, đã đo xong", chạy song song, một người duyệt** | hoang chọn, và chính hoang thêm bước chạy song song |
| Người khởi động từng vòng | Loại: vẫn phải nhớ mà làm |

**Ai thắng khi chạy song song:** câu trả lời của người quyết định; tín hiệu máy tự đo chỉ dùng để dừng sớm một model hỏng rõ. hoang đồng ý ngày 27/11. Chỉ dùng tín hiệu máy bị loại vì máy không biết ai đúng: lỗi gọi Original thành Hot rất đều và rất tự tin (0,93).

**Sinh ảnh tổng hợp:** một công cụ chung cho mọi file `.glb`, viết trên Blender thuần. Giữ công cụ theo từng hình dạng bị loại vì mỗi hình dạng mới lại phải viết code. BlenderProc bị loại vì không chạy được trên HUYHOANG.

## 5. Thiết kế

### 5.1 Toàn cảnh

```
SẢN PHẨM MỚI (5.6)
  người: lấy mẫu → model 3D (.glb), thẻ sản phẩm
  máy:   sinh ảnh tổng hợp → train detector ─────────────────┐
                                                             ▼
VÒNG CHẬM (5.5), hai tuần một lần hoặc khi có tín hiệu       CỬA LÊN LIVE (5.2)
  máy:   gom frame → tự gán nhãn → train detector ─────────► đo nhanh
  người: xem chỗ máy không chắc (frame review)               → chạy song song, ẩn
                                                             → người chấm chỗ hai bản khác nhau
VÒNG NHANH (5.3), mỗi đêm                                    → một người duyệt → live
  máy:   nhãn mới của người → kho ảnh mới ─────────────────► (quay lui: một lần bấm)
                                                             │
NGƯỜI TRÊN WEBSITE (5.4)                                     ▼
  label frame, review reading ◄── frame được chọn bằng tín hiệu từ bản đang chạy
  thấy: nhãn của mình đã vào phiên bản nào
```

Ba dòng việc (sản phẩm mới, vòng chậm, vòng nhanh) đều kết thúc ở cùng một cửa. Không có đường nào khác để một thay đổi của model lên chạy thật.

### 5.2 Phần 1. Xương sống: phiên bản, chạy song song, duyệt

**Phiên bản.**
- Một *bản chạy* là trọn bộ thứ worker dùng để đọc: detector sữa, detector Slide, kho ảnh của từng nhóm hàng, và các biến đọc (`MILK_LONG_*`, `MILK_SLIDE_*`).
- Mỗi bản chạy có một bản ghi:
  - id và bản cha;
  - loại thay đổi: kho ảnh, detector, hoặc luật đọc;
  - dữ liệu vào: id các frame đã gán, số frame, khoảng ngày, commit của code;
  - số đo nhanh;
  - trạng thái: ứng viên, đang chạy song song, live, đã thay, đã bỏ, bị dừng;
  - tiêu chí thắng, ghi trước khi chạy song song;
  - ai duyệt và lúc nào.
- Bản ghi nằm trong một bảng mới của backend *(đề xuất)*. File model và kho ảnh nằm trên HUYHOANG, mỗi bản một thư mục riêng, không bao giờ ghi đè.
- `model_version` trên mỗi capture là id của bản chạy.

**Chạy song song trong worker.**
- Worker nạp thêm bản ứng viên và cho nó đọc đúng các frame của cửa sổ lấy mẫu mà bản live vừa đọc.
- Kết quả của ứng viên đi kèm bản ghi capture trong một trường riêng (id bản ứng viên và các box của nó). Không gửi thêm ảnh.
- Backend lưu trường đó cùng capture và không đưa nó vào bất cứ thứ gì người xem thấy: `latest_stock`, `cv_output`, review queue, các sự kiện kệ.
- Trường này đi qua ba chỗ: worker gửi, hub lưu vào bảng capture của nó, ingest của backend đọc sang (`_normalize_record`). Cả ba hiện chỉ giữ các trường đã biết, nên cả ba phải sửa. Hub chỉ được cập nhật qua change set.
- Bản live luôn được ưu tiên: ứng viên chỉ chạy sau khi phần live của cửa sổ đã gửi xong. Thiếu thời gian hay thiếu bộ nhớ thì bỏ frame của ứng viên, không bao giờ bỏ frame của live.
- Khi ứng viên chỉ khác ở kho ảnh, nó dùng lại box của detector live và chỉ tra kho lần hai.
- Mỗi lúc chỉ có một ứng viên.

**Tín hiệu máy, chỉ để dừng sớm.** Ứng viên bị dừng, có ghi lý do, khi:
- nó lỗi hoặc làm worker khởi động lại;
- nó không đọc xong cửa sổ trước cửa sổ kế tiếp, ba lần liên tiếp;
- nó vẽ box sản phẩm lúc tủ đã cất, quá 1 box trên 100 frame (ngưỡng của cổng ban đêm đã dùng cho TH).

**Người phân xử.**
- Frame chấm điểm mỗi giờ (`AUD-`) hiện box của cả hai bản gộp lại, không ghi box nào của bản nào.
  - Hai bản vẽ cùng một chỗ và gọi cùng tên: một box có gợi ý, chấm như hiện nay.
  - Chỉ một bản có box, hoặc hai bản gọi khác tên: box không có gợi ý, người tự chọn (đúng kiểu box "?" của frame review hiện có).
- Thêm *frame so sánh*: lấy ngẫu nhiên trong các capture mà hai bản khác nhau, tối đa 8 frame một ngày *(số của Claude)*. Frame so sánh không tính vào các KPI.
- Từ một lần chấm tính được đúng, sai và sót cho cả hai bản.
- Frame `AUD-` vẫn là mẫu ngẫu nhiên, nên KPI của bản live không bị lệch. Một hệ quả cần biết: lon mà ứng viên tìm ra còn bản live bỏ sót sẽ được tính là sót của bản live. Số sót trên trang Model có thể tăng khi có ứng viên chạy; đó là số thật hơn.

**Tiêu chí thắng**, ghi vào bản ghi trước khi chạy song song:
- Thời gian tối thiểu:
  - thay detector hoặc luật đọc: 3 ngày và 30 frame đã chấm *(số của Claude, hoang đã nghe ngày 27/11)*;
  - chỉ thay kho ảnh: 1 ngày và 30 box khác nhau đã chấm *(số của Claude)*.
- Kết luận tính trên các box mà hai bản khác nhau và đã có người chấm:
  - *tốt hơn*: ứng viên đúng nhiều hơn bản live, phép thử nhị thức chính xác cho p < 0,05;
  - *kém hơn*: ngược lại;
  - *chưa thấy khác*: các trường hợp còn lại.
- Không sản phẩm nào được kém đi quá 5 điểm so với bản live (ngưỡng của cổng 2 trong thiết kế auto-label).
- Sản phẩm mà bản live chưa biết: chỉ chấm ứng viên, theo ngưỡng ở mục 5.6.

**Trang Model, khối "Model versions"** (chỉ `team_admin` bấm được nút):
- bản đang live và từ lúc nào;
- bản ứng viên: đã chạy mấy ngày, đã có bao nhiêu frame chấm, còn thiếu gì;
- bảng so sánh theo sản phẩm và kết luận;
- nút "Put live" (bấm được khi kết luận là *tốt hơn* hoặc *chưa thấy khác*), "Discard", và "Roll back" về bản trước;
- lịch sử các bản.

**Đưa lên và quay lui.**
- Website ghi yêu cầu. Một tiến trình mới trên HUYHOANG, gọi là *máy chạy việc*, nhận yêu cầu: đổi con trỏ "bản live", khởi động lại worker, rồi xác nhận bằng `model_version` của capture kế tiếp.
- Quay lui là trỏ lại bản trước theo cùng cách.
- `worker.env` không còn được sửa tay để đổi model. Cách sửa tay vẫn dùng được khi máy chạy việc hỏng, và ghi trong `TRAINING.md`.

**Máy chạy việc nói chuyện với backend thế nào.**
- Nó dùng profile `milk` đã có trên HUYHOANG và đọc, ghi thẳng các bảng và bucket của backend, như các công cụ trong `training/store_view` đang làm từ laptop (đọc bảng audits, đẩy frame review). Không cần tài khoản máy mới hay route mới cho nó.
- Nó nhận yêu cầu của website (đưa lên, quay lui, bỏ, train ngay) bằng cách đọc bảng phiên bản theo nhịp.
- Việc đầu tiên của phần 1 là xác nhận profile `milk` đọc được bảng audits và ghi được vào bucket analytics.
- Worker giữ lại trên đĩa một bản của mỗi frame nó gửi đi, đúng bản đã làm mờ mặt, nên việc gom frame để train không tốn tiền tải từ S3 về *(đề xuất)*. `harvest.py` vẫn dùng cho các frame có trước lúc đó. Với nhịp đọc hiện nay là khoảng 1 GB một ngày, nên phải có hạn giữ; frame đã gán nhãn và frame đã dùng để train thì giữ lại. Danh sách frame nào là `AUD-` lấy qua API.

### 5.3 Phần 2. Vòng nhanh: kho ảnh

**Kho ảnh là gì.** Với mỗi camera và mỗi nhóm hàng: các ảnh cắt của sản phẩm thật, mỗi ảnh có tên do người xác nhận.
- Nguồn: nhãn trên frame dạy (`TRN-`), frame review (`REV-`) và frame so sánh; cộng đáp án vẽ tay phía train.
- Không bao giờ nhận: frame `AUD-`, frame giữ riêng, nhãn tự động, ảnh render.
- Code đã có để bắt đầu: `training/store_view/slide_gallery.py` (kho ảnh màu và luật đọc: 10 ảnh gần nhất, một tên chỉ được nêu khi giữ ít nhất 60% trọng số, ít nhất 3 phiếu, và kho có ít nhất 20 ảnh của tên đó; nếu không thì "không chắc").

**Kho làm gì trong worker.** Detector tìm box. Kho đặt tên cho box.
- Kho nói chắc: box mang tên của kho.
- Kho không chắc: box giữ tên của detector và được đánh dấu để vào hàng chọn frame (mục 5.4).
- Kho không được gạt bỏ box.

**Cách so ảnh** đặt theo nhóm hàng trong cấu hình camera. Điểm xuất phát theo lần thử 27/11: màu cho Slide, DINOv2-small cộng màu cho hộp sữa.

**Ở tiệm hiện nay, chỗ được lợi là Slide.** Lỗi gọi tên đã biết là của Slide (Original bị gọi thành Hot hoặc Cheese). Sữa ở CAM-S01-A chỉ có một lớp TH gộp, nên kho của nhóm sữa chưa có gì để đổi tên cho tới khi tiệm bày thêm một loại hộp khác.

**Việc đầu tiên của phần này: đo lại trên box của detector.** Theo luật "bước xác nhận phải tự chứng minh", với từng nhóm hàng phải đo cả hai cách, có kho và không có kho, bằng box của detector, trên các ngày kho chưa thấy.
- Nhóm nào kho làm tên đúng hơn thì bật kho cho nhóm đó.
- Nhóm nào không thì không bật. Khi đó nhãn của người cho nhóm ấy chỉ có tác dụng ở vòng chậm, và website phải nói đúng như vậy (mục 5.4).

**Mỗi đêm:**
1. Máy chạy việc lấy nhãn mới và dựng kho ứng viên. Việc này mất vài giây.
2. Đo nhanh: giấu từng ngày khỏi kho rồi đọc lại ngày đó. Kho ứng viên không được kém kho đang chạy.
3. Không có ứng viên nào đang chạy thì kho mới thành ứng viên và đi qua cửa ở mục 5.2. Đang có ứng viên thì nhãn mới chờ lượt sau.

### 5.4 Phần 3. Chất lượng nhãn, và cho người làm thấy

**Chọn frame dạy bằng tín hiệu.** Mỗi camera mỗi giờ vẫn có một frame chấm điểm ngẫu nhiên và một frame dạy, như hiện nay. Khác ở chỗ frame dạy được chọn theo thứ tự ưu tiên:
1. capture có reading vừa bị người sửa trên trang Category;
2. capture mà kho ảnh nói "không chắc";
3. capture có số đếm nhảy giữa các frame của cùng một cửa sổ;
4. capture thuộc một kiểu xếp hàng mới (đoạn mới theo `segments.py`);
5. không có tín hiệu nào thì chọn ngẫu nhiên như hiện nay.

Số frame đưa cho người mỗi ngày không tăng so với hiện nay, trừ frame so sánh khi có ứng viên (tối đa 8).

**Review reading.**
- Nút "Save Correction" không lưu khi người dùng không đổi gì; khi đó dùng "Confirm". Nút bị khoá trong lúc đang lưu.
- Một lần sửa không dạy thẳng cho model. Nó đưa frame của reading đó lên đầu hàng chọn frame dạy.
- Khi frame đó đã được gán và nhãn của nó vào một bản live, lần sửa được ghi `fed_back_to_model = true` kèm id của bản chạy.

**Frame biết trước đáp án.**
- Cứ 10 frame trong hàng chờ thì có 1 frame đã có đáp án (lấy từ đáp án vẽ tay, hoặc frame mà hai người đã chấm giống nhau). Người chấm không được báo frame nào.
- Kết quả là độ khớp của từng người theo tuần, chỉ `team_admin` thấy.
- Nhãn của một người có độ khớp dưới ngưỡng chưa vào kho hay tập train cho tới khi một người khác xác nhận.
- Áp dụng cho mọi người gán, kể cả người của client. hoang đồng ý ngày 27/11 (*"làm theo đề xuất của bạn"*). Ngưỡng độ khớp do người làm đề xuất sau khi có số của vài tuần đầu.

**Nhãn đáng ngờ.** Sau mỗi lần train, những box mà model mới bất đồng mạnh với nhãn được đưa vào danh sách xem lại, qua đường "Relabel them" đã có trên trang Model.

**Người làm thấy gì.**
- Trang Model, với người đang đăng nhập: "Nhãn của bạn: N box đã vào kho ảnh của bản X, live từ ngày D. M box chờ lần train kế, dự kiến ngày D2."
- Trang Category, sau khi sửa một reading: "Frame của reading này đã vào hàng chờ gán nhãn."
- Khối "Model versions": mỗi bản ghi nó dùng bao nhiêu frame, của bao nhiêu người.
- Chỉ nói "đã vào" khi bản đó đã live. Nhóm hàng chưa bật kho thì câu đầu chỉ có vế "chờ lần train kế".

### 5.5 Phần 4. Vòng chậm: tự gán nhãn và train lại

**Kích hoạt.** Một lần train bắt đầu khi có một trong các điều sau:
- đã 14 ngày từ lần train trước (chu kỳ của Datagent);
- có đủ nhãn mới của người cho một nhóm hàng (ngưỡng do người làm đề xuất, ghi trong cấu hình);
- KPI của bản live trên trang Model tụt quá 5 điểm so với lúc nó lên live, ba ngày liền *(số của Claude)*;
- có sản phẩm mới (mục 5.6);
- `team_admin` bấm "Train now".

Mỗi lúc chỉ một lần train. Train không chạy cùng lúc với chạy song song nếu phép đo bộ nhớ GPU cho thấy không đủ chỗ; khi đó việc đến sau xếp hàng.

**Chuỗi việc**, do máy chạy việc điều khiển, dùng code đã có trong `training/store_view`:
1. Chia đoạn các frame mới (`segments.py`).
2. Tự gán nhãn (`auto_label_run`: propose, queue, labels). Các lon cần người xem thành frame review và tự được đẩy lên trang Model (`auto_label_review push`).
3. Chờ người chấm frame review, tối đa một khoảng định trước. Đoạn chưa chấm xong bị che xám như thiết kế auto-label đã định, không chặn lần train.
4. Dựng tập train: ảnh thật cộng ảnh tổng hợp (`dataset.py`).
5. **Kiểm dữ liệu trước khi train.** Dừng và báo trên trang Model khi: có frame `AUD-` hoặc frame giữ riêng trong tập; thiếu một lớp của danh mục; số nhãn của một lớp tụt mạnh so với lần trước.
6. Train, ở mức ưu tiên thấp.
7. Đo nhanh trên tập giữ riêng (`evaluate.py`) theo các cổng đã có: cổng của TH (thiết kế TH mục 5.4) và cổng 2 của Slide (thiết kế auto-label mục 5.7). Trượt thì bản đó dừng ở trạng thái "đã bỏ", có ghi số.
8. Qua thì thành ứng viên và đi qua cửa ở mục 5.2.

**Tập giữ riêng.**
- Các cửa sổ giữ riêng hiện có và đáp án vẽ tay của chúng giữ nguyên.
- Đầu mỗi chu kỳ, máy chọn ngẫu nhiên một ngày của chu kỳ sắp tới và thêm nó vào tập giữ riêng. Ngày đó không sinh frame dạy, và không bao giờ quay lại làm dữ liệu dạy.
- Đáp án của ngày đó là các frame chấm điểm (`AUD-`) của nó, do người chấm trên trang Model như mọi ngày. Lon sót chỉ được chấm bằng một điểm, nên một box của model khớp khi nó chứa điểm đó.
- Chỗ yếu đã biết: người chấm ít khi đánh dấu lon sót (ghi nhận ngày 24–25/11), nên đáp án kiểu này dễ đếm thiếu lon sót. Frame gộp box của hai bản (mục 5.2) bù được một phần.

**Lần train thật đầu tiên của Slide** là Slide v4 theo thiết kế auto-label mục 5.6: nhãn gồm mọi lon nhìn thấy, vùng chưa rõ bị che xám, không làm nhiễu màu.

### 5.6 Phần 5. Sản phẩm mới

**Người làm:**
- lấy mẫu và dựng model 3D (`.glb`);
- điền thẻ sản phẩm trên website: tên đúng như trên bao bì, nhóm hàng, kích thước thật (rộng, sâu, cao), ảnh đại diện, tiệm nào bày. Kích thước là trường mới: file 3D hiện có không đúng tỉ lệ.

**Máy làm:**
1. **Sinh ảnh tổng hợp** bằng một công cụ chung trên Blender thuần, nhận mọi file `.glb`:
   - cảnh ngẫu nhiên trên nền thật của tiệm, có ánh sáng thay đổi, vật che và sản phẩm khác đứng lẫn;
   - box có xét che khuất;
   - không trải màu quá rộng (bài học Slide v5: trải hue thì model sụp).
   - Công cụ hộp sữa hiện có (`cctv_dataset`) vẫn được dùng cho tới khi công cụ chung chứng minh được nó không kém: detector train từ ảnh của công cụ mới, đo trên frame thật, không kém detector train từ ảnh của công cụ cũ.
2. **Train detector** có thêm sản phẩm mới (vòng chậm, kích hoạt "có sản phẩm mới").
3. **Chạy thử** chính là chạy song song ở mục 5.2: sản phẩm mới được đếm, nhưng chưa hiện cho người xem.

**Trong lúc chạy thử:**
- Việc chọn frame dạy ưu tiên các capture có box của sản phẩm mới.
- Người gán khoảng 10 frame. Nhãn đó vào kho ảnh (mục 5.3), nên tên của sản phẩm mới đúng dần mà không cần train thêm.

**Sản phẩm mới được hiện cho người xem khi:** trên ít nhất 30 box của nó đã có người chấm, tìm thấy đạt 85% và gọi đúng tên đạt 90% *(số của Claude; với hộp sữa dùng luôn ngưỡng của cổng TH)*, các sản phẩm cũ không kém đi theo mục 5.2, và một `team_admin` duyệt. Việc thêm nó vào shelf plan vẫn do người làm.

**Vị mới của một loại hàng detector đã tìm được:** thẻ sản phẩm và khoảng 10 frame gán nhãn là đủ để kho ảnh gọi đúng tên, không chờ train. Model 3D vẫn được làm như quy trình của team, để lần train kế có lớp đó.

### 5.7 Thứ tự làm, và mỗi phần xong khi nào

| Phần | Xong khi |
|---|---|
| 1. Xương sống | Một bản ứng viên giả (giống hệt bản live) chạy song song trọn một ngày mà Dashboard không đổi; người chấm được frame gộp; `team_admin` bấm đưa lên rồi quay lui được, không ai sửa `worker.env` |
| 2. Vòng nhanh | Có số đo có kho và không có kho trên box của detector cho từng nhóm hàng; nhóm nào đạt thì kho của nó đã đi qua cửa một lần |
| 3. Chất lượng nhãn và hiển thị | Một reading được sửa kéo frame của nó vào hàng chờ; người gán thấy nhãn của mình ở bản nào; `team_admin` thấy độ khớp của từng người |
| 4. Vòng chậm | Một lần train do lịch khởi động chạy hết chuỗi mà không ai gõ lệnh, và ra một bản ứng viên hoặc một bản "đã bỏ" có số |
| 5. Sản phẩm mới | Một file `.glb` và một thẻ sản phẩm đi hết đường tới "đang chạy thử" mà không ai sửa code |

Phần 1 đi trước vì mọi phần khác cần cửa lên live. Phần 2 đi kế vì nó trả lời câu hỏi của teammate và client sớm nhất.

### 5.8 Để người làm tự quyết

- Tên bảng, tên route, định dạng bản ghi phiên bản và trường ứng viên trong capture.
- Cách worker nạp bản ứng viên (tiến trình riêng hay cùng tiến trình), miễn giữ được ưu tiên cho bản live.
- Dạng của con trỏ "bản live" và cách worker đọc nó lúc khởi động.
- Hạn giữ frame trên đĩa của HUYHOANG.
- Cách tính "tìm thấy" của sản phẩm mới từ các frame đã chấm (box đúng trên tổng box đúng và điểm lon sót).
- Cách gộp box của hai bản thành một frame để chấm, và ngưỡng coi hai box là "cùng một chỗ".
- Dạng lưu của kho ảnh; có dùng lại LanceDB hay không.
- Cách máy chạy việc xếp hàng công việc và ghi nhật ký.
- Ngưỡng "đủ nhãn mới" để kích hoạt train, và thời gian chờ frame review.
- Số ảnh tổng hợp cho mỗi sản phẩm, cách dựng cảnh trong Blender.
- Cách viết test.

### 5.9 Những điều hoang đã quyết, và những điều Claude tự quyết

**hoang quyết ngày 27/11:**
- Cách A: hai vòng, kho ảnh cộng với train định kỳ.
- Model mới chạy song song với bản đang chạy rồi mới được đưa lên; người chấm quyết định ai thắng, tín hiệu máy chỉ để dừng sớm; một người duyệt.
- Sản phẩm mới luôn bắt đầu bằng model 3D, ảnh tổng hợp và chạy thử.
- Máy chạy việc trên HUYHOANG dùng quyền AWS đã có trên máy đó.
- Đo độ khớp của từng người gán, kể cả người của client; chỉ `team_admin` thấy; nhãn của người có độ khớp thấp chờ người thứ hai xác nhận.

**Claude tự quyết** (hoang đổi được):
- Thứ tự năm phần. hoang đã nghe ngày 27/11 và không đổi.
- Người vận hành chỉ cần website; review reading chỉ dùng gián tiếp. hoang đã nghe ngày 27/11 và không đổi.
- Chỉ `team_admin` được đưa lên và quay lui.
- Các con số: 8 frame so sánh mỗi ngày; 1 ngày và 30 box cho thay đổi chỉ ở kho ảnh; p < 0,05; không sản phẩm nào kém quá 5 điểm; 1 trong 10 frame biết trước đáp án; KPI tụt 5 điểm trong ba ngày; 30 box, 85% và 90% cho sản phẩm mới.
- Worker giữ lại frame nó đã gửi, để gom frame không cần quyền S3.
- Kho ảnh không được gạt bỏ box, chỉ đặt tên.
- Frame dạy mỗi giờ chọn theo tín hiệu, tổng số frame không tăng.
- Khi có ứng viên, frame chấm điểm hiện box gộp của hai bản. Số sót của bản live trên trang Model có thể tăng, vì lon mà chỉ ứng viên tìm ra được tính là sót của bản live.
- Đáp án của các ngày giữ riêng mới lấy từ frame chấm điểm do người chấm, không còn do Claude vẽ tay.
- Máy chạy việc dùng profile `milk` như nó đang có. Claude chưa xem profile đó có những quyền gì; thu hẹp quyền cho một tiến trình chạy không người trông nằm ở mục 7.

## 6. Khác với tài liệu của team

| Tài liệu nói | Bản này làm | Vì sao |
|---|---|---|
| Architecture design: train lại bằng SageMaker Pipelines, phiên bản trong Model Registry | Train trên HUYHOANG, phiên bản trong một bảng của backend | Từ 23/11 hoang đã chuyển việc đếm và train sang HUYHOANG; trang kiến trúc chưa được vẽ lại |
| Architecture design: gán nhãn bằng CVAT trên EC2 | Gán nhãn trên trang Model của website | Trang Model đã chạy thật từ 23/11 |
| Architecture design: model mới chỉ được dùng nếu điểm trên tập kiểm định cố định không giảm | Giữ điều đó làm bước đo nhanh, thêm chạy song song và người duyệt | Tập cố định đã hai lần không bắt được lỗi |
| Architecture design: thêm SKU thì phải train lại | Hình dạng mới vẫn phải train. Vị mới của loại hàng đã biết thì kho ảnh đặt tên được | Lần thử 27/11 |
| Data Dictionary: train lại mỗi chu kỳ bằng mọi lần sửa đã tích lũy | Train mỗi 14 ngày. Lần sửa kéo frame của nó vào hàng gán nhãn, rồi được ghi `fed_back_to_model` khi nhãn đó vào bản live | Lần sửa không có box nên không dạy thẳng được |

## 7. Để sau

- Nhiều camera và nhiều tiệm: kho ảnh và tập giữ riêng theo từng camera đã nằm trong thiết kế, nhưng chưa có gì để đo.
- Train trên cloud khi một máy không đủ.
- Thay profile `milk` của máy chạy việc bằng một user AWS chỉ có quyền trên các bảng và thư mục nó cần.
- Chạy song song nhiều ứng viên cùng lúc.
- Vẽ box trên trang Model thay vì chỉ chấm điểm lon sót.
- Dọn frame `frames/corrections/` sau khi `fed_back_to_model = true` (đã ghi trong `docs/NHAT-P01.md`).
- Vẽ lại trang Architecture design theo hệ thống đang chạy.
