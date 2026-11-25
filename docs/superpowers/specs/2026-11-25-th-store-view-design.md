# Nhận ra sữa TH ở góc camera thật của cửa hàng — thiết kế

Ngày 25/11/2026. Trạng thái: chờ hoang duyệt. Nhánh: `feat/th-store-view`.

## 1. Vì sao làm

**Hiện trạng ở DEMO-S01:**
- Có hai lốc TH true MILK 180ml đặt trên nóc tủ Slide, trong khung hình của CAM-S01-A: một lốc Có đường và một lốc
  Ít đường. hoang xác nhận điều này ngày 25/11.
- Hệ thống chưa đếm được lốc nào lần nào:
  - Dashboard báo 2 SKU TH hết hàng liên tục, từ 22/11 và 23/11.
  - Trang Model không có số nào về TH.

**Nguyên nhân, đo ngày 25/11:**
- Model sữa của Long (YOLO `best_types.pt` cùng DINOv2 và LanceDB, ngày 13/10) chỉ học trên ảnh tổng hợp 1920×1080:
  - từng hộp đứng riêng, cao khoảng 94 px;
  - hộp chỉ được gắn nhãn khi thấy chữ thương hiệu ở mặt trước. Hộp nhìn từ trên hay quay ngang bị loại khỏi nhãn;
  - không có lốc bọc màng.
- Ở tiệm:
  - mỗi hộp chỉ rộng 25–45 px trong ảnh 2560×1440;
  - lốc lúc đứng (23/11), lúc nằm chỉ lộ nắp hộp (24–25/11), và hay bị hũ kẹo che.
- Thử trên 5 ảnh ban ngày:
  - cấu hình worker (cả khung, imgsz 1280): 0 box;
  - cắt ô 640: được vài box yếu, nhưng database trả "unknown". Database chỉ có ảnh tổng hợp, ngưỡng giống nhau
    0,9556.
- "TH" duy nhất hệ thống từng báo là một vật trắng dưới gầm tủ đông, lúc ban đêm.
- Ghi chú chi tiết: memory `th-not-counted-2026-11-25`. Script đo: scratchpad phiên 25/11, `th_diag_remote.py`.

**hoang chốt ngày 25/11:**
- Model phải nhận ra sữa để hệ thống đếm được và hiển thị được. Cần chạy được, chưa cần đẹp.
- Phần đã làm đủ cho demo rồi. Bây giờ là làm sản phẩm cho client dùng được.
- Tận dụng mọi dữ liệu có được, không bị trói bởi các quy tắc cũ (ví dụ quy tắc "chỉ dạy bằng frame TRN").
- Train lâu cũng không sao.

## 2. Mục tiêu, không làm, thất bại dù chạy

**Mục tiêu:**
1. Worker đếm mọi hộp TH 180ml lộ mặt trước hoặc nắp trên CAM-S01-A. Gồm các trường hợp: lốc đứng, lốc nằm, hộp
   trong lốc bọc màng, hộp bị che một phần nhưng người nhìn vẫn biết là hộp TH.
2. Products và Dashboard hiện số đó như mọi SKU khác.
3. Không làm mất khả năng nhận 10 SKU Vinamilk của model sữa.
4. Có số đo trên ảnh giữ riêng trước khi bật lên live. Sau khi bật, trang Model đo tiếp.
5. Quy trình lặp lại được cho camera và tiệm mới: gom ảnh → gắn nhãn → train → nạp database → đo → bật.

**Không làm lần này:**
- Phân biệt Có đường và Ít đường ở camera này (lý do ở mục 5.1).
- Render lốc tổng hợp.
- Sản phẩm khác ngoài sữa.
- Train lại Slide.

**Thất bại dù vẫn chạy:**
- Đếm vật khác thành TH, như cái chai trắng ban đêm.
- Số TH không do model đọc từ ảnh thật mà ra.
- Số Slide thay đổi vì phần sữa.
- Model nhớ đúng mấy tấm ảnh đã học nhưng hụt khi tiệm xếp lại lốc.
- Ảnh tiệm lọt vào repo.

## 3. Ràng buộc

- **GPU HUYHOANG (RTX 5090, 32 GB) dùng chung:**
  - Worker đang chiếm khoảng 6–8 GB.
  - Train YOLO batch 12 ở 1280 cần khoảng 19 GB.
  - Nếu số khung/phút trên hub tụt rõ trong lúc train thì giảm batch.
- **Không ghi đè file worker đang dùng:** `yolo\best_types.pt`, `carton_recognition\…` và `slide_pilot\runs_v3\best.pt`.
  Mọi thứ mới làm trong bản sao hoặc dưới tên mới, theo `TRAINING.md` trên HUYHOANG.
- **Trên Windows phải `import torch` trước** khi nạp cv2, ssl hay lancedb (`server/milk/torch_first.py`).
- **Ảnh trên hub tự xoá sau 7 ngày:**
  - bucket `milk-demo-base-databucket-xh85udq9bhrr`, prefix `frames/`, tham số `RetentionDays` của stack
    `milk-demo-base`;
  - ảnh ngày 22/11 mất lúc 07:00 ngày 30/11 (giờ VN).
- **Quyền AWS:** HUYHOANG không có, laptop có.
- **Ảnh tiệm và nhãn không vào repo.** Không để chúng trong thư mục OneDrive.
- **Change set:** stack `milk-backend-development` không bao giờ dùng `--tags`; stack `milk-demo-base` dùng
  `--tags project=milk-demo`.
- **Lambda của tài khoản bị giới hạn 10 chạy đồng thời.**

## 4. Các cách đã cân nhắc

| Cách | Được | Mất |
|---|---|---|
| 1. Chỉ frame thật của CAM-S01-A | Nhanh (khoảng 1 ngày), khớp đúng góc nhìn | Model quên các SKU khác. Chỉ biết những kiểu xếp đã thấy. Không dùng lại được cho tiệm khác |
| 2. Chỉ ảnh tổng hợp có lốc (sửa bộ sinh ảnh của Long) | Không phải vẽ khung tay, phủ nhiều kiểu xếp | Phải viết thêm phần render lốc và màng. Ảnh giả lệch ảnh thật (Slide đã phải làm nhiều vòng mới dùng được). Chậm nhất |
| **3. Kết hợp (chọn)** | Ảnh thật dạy đúng góc nhìn. Bộ ảnh tổng hợp có sẵn của Long giữ khả năng nhận 12 SKU cũ. Quy trình dùng lại được | Nhiều việc nhất trong ba cách |

hoang để Claude chọn cách làm. Claude chọn cách 3, vì hoang cần một sản phẩm client dùng được và cho phép dùng mọi dữ
liệu, train lâu.
- Cách 1 làm model quên Vinamilk.
- Cách 2 tự nó chưa đủ gần ảnh thật.
- Render lốc tổng hợp (cách 2) để sau. Chỉ làm khi số đo cho thấy model hụt ở kiểu xếp chưa có trong ảnh thật.

## 5. Thiết kế

### 5.1 Đếm cái gì

- **Đơn vị: một hộp TH 180ml lộ mặt trước hoặc nắp**, đủ để người nhìn biết đó là hộp TH. Cách định nghĩa này giống
  quy tắc A của Slide và giống `unit_count` của Data Dictionary ("individual visible units"). Claude đề xuất, hoang
  không phản đối.
- **Gộp hai loại thành một dòng sản phẩm:**
  - Nhãn model `TMP-MLK-TH-00`.
  - Tên: `TH true MILK Sữa Tươi Tiệt Trùng 180ml (Có đường + Ít đường)`. Tên này là quyết định của Claude; hoang có thể
    đổi.
  - Lý do: hai loại chỉ khác màu chữ ở mặt trước. Khi lốc đứng, lốc sau bị lốc trước che chữ. Khi lốc nằm, chỉ thấy
    nắp, và nắp hai loại giống hệt nhau.
  - Ảnh so sánh nằm ở scratchpad phiên 25/11, `packs_compare.jpg`.
- **Gọi tên từng loại là một tuỳ chọn của worker** (`MILK_LONG_VARIANTS`, mặc định tắt). Khi bật, worker chỉ đổi
  `TMP-MLK-TH-00` thành TH-01 hay TH-02 khi database nghiêng hẳn về một loại. Dành cho camera đọc được chữ.
  CAM-S01-A để tắt.

### 5.2 Dữ liệu

**a) Gom ảnh (làm ngay, trước 30/11):**
- **Nguồn:**
  - mọi frame của CAM-S01-A trên hub: 8.358 frame (khoảng 8 GB) tính đến trưa 25/11, cộng thêm mỗi ngày;
  - ảnh AUD và TRN trong bucket `milk-backend-development-754361433393`;
  - manifest lấy từ bảng `milk-backend-development-captures`: `capture_id`, `capture_timestamp`, `image_key`,
    `display_visible`, `detections_json`.
- **Bỏ trùng** theo `capture_id`.
- **Đường đi của ảnh:**
  1. Laptop tải về một thư mục ngoài OneDrive, ví dụ `C:\Users\huyho\milk_store_frames\`.
  2. Chép sang `C:\Users\huyho\Datagent\store_frames\CAM-S01-A\` trên HUYHOANG, có giới hạn băng thông để luồng
     camera của worker không bị ảnh hưởng.
- **Lưu lâu hơn:** tăng `RetentionDays` của `milk-demo-base` từ 7 lên 30 ngày.
  - Tham số này áp cho cả `frames/` và `results/`.
  - Thêm khoảng 30 GB, dưới 1 USD mỗi tháng.
  - Quyết định của Claude, theo ý "tận dụng mọi thứ".

**b) Chia đoạn theo cách xếp:**
- Camera cố định và lốc ít khi di chuyển. Nên chia chuỗi frame thành các đoạn: trong một đoạn, vùng lốc TH trông như
  nhau.
- So sánh dựa trên ảnh đã cân sáng. Frame có người hay tay che vùng lốc thì không thuộc đoạn nào.

**c) Gắn nhãn:**
- **Mỗi đoạn có một keyframe.** Claude vẽ khung từng hộp TH trên keyframe (lớp `th_true_milk`), dựa trên ảnh phóng to.
  Kết quả kèm một tấm ảnh tổng hợp các keyframe đã vẽ khung; hoang xem nếu muốn, không cần chờ.
- **Lan nhãn:** khung của keyframe được chép sang mọi frame cùng đoạn, nếu vùng lốc vẫn khớp keyframe. Từ vài chục
  keyframe ra vài nghìn frame có nhãn, đủ các mức sáng trong ngày.
- **Định dạng:**
  - Mỗi frame một file nhãn YOLO.
  - Danh sách đoạn và keyframe ghi trong một file JSON.
  - Tất cả để ở `C:\Users\huyho\Datagent\store_labels\`.

**d) Ảnh âm:**
- Frame không có TH: ban đêm khi tủ đã cất, và những lúc chưa bày lốc.
- Có cả cái chai trắng dưới gầm tủ đông, để model học cách không gọi nó là TH.

**e) Tập giữ riêng.** Đây là ngoại lệ duy nhất của "dùng mọi thứ", vì không có nó thì không biết model chạy thật hay
chỉ nhớ ảnh. Tập gồm:
- Mọi frame ngày 25/11. Lốc nằm, cách xếp mới hơn những gì có trong tập dạy.
  - Ban đầu là "từ 25/11 trở đi, không có điểm kết thúc".
  - Lần đo cổng đầu tiên (tối 25/11) trượt vì các cách xếp E0/E1/E2 chỉ có trong ngày 25/11.
  - hoang chọn (25/11, cách A): đóng cửa sổ lúc 26/11 00:00. Frame từ 26/11 được dùng để train, còn 25/11 vẫn là phép đo cổng.
- Frame ngày 23/11 từ 18:00 đến lúc tủ được cất (khoảng 20:40). Lốc đứng, lúc chạng vạng.
  - Phần này gần giống các giờ trước trong ngày, nên số đo sẽ hơi lạc quan. Báo cáo phải ghi rõ điều đó.
- Claude vẽ khung trên keyframe của tập này, theo đúng cách ở mục c.

Tập giữ riêng không được dùng để train, nạp database hay chỉnh ngưỡng. Muốn chỉnh ngưỡng thì tách một phần validation
từ các ngày dạy. Qua cổng (mục 5.4) rồi thì được train lần cuối trên toàn bộ, gồm cả tập giữ riêng. Từ đó, việc đo
model là trang Model trên website.

**f) Ảnh tổng hợp:**
- Sinh lại `dataset_hard` bằng `build_hard_dataset.py` của Long, dùng `backgrounds\` và `props\` sẵn có, rồi chạy
  `make_type_labels.py`.
- Gộp hai lớp TH thành lớp `th_true_milk`. Model mới có 11 lớp: 1 lớp TH và 10 lớp loại Vinamilk.
- Giữ tập val L1–L5 làm mốc so với `results_types.json`.

### 5.3 Model

**Detector:**
- YOLO train tiếp từ `best_types.pt`, với 11 lớp ở mục 5.2f.
- Ảnh dạy là ảnh thật cắt ô 1280×1280 từ frame 2560×1440, giữ nguyên độ phân giải: có ô quanh vùng lốc và ô ở nơi
  khác của khung. Trộn thêm ảnh tổng hợp.
- Lưu dưới tên mới, ví dụ `--tag store_v1` → `yolo\best_store_v1.pt`.

**Lúc chạy:**
- Chạy cả khung ở 1280, cộng thêm các ô 1280 ở độ phân giải gốc (`detect(..., tile=1280)` của Long).
- Gộp bằng NMS.
- Biến mới `MILK_LONG_TILE=1280`; 0 nghĩa là chỉ chạy cả khung như hiện nay.

**Database v2:**
1. Làm trong bản sao `carton_recognition_v2`.
2. Nạp ảnh cắt thật của hộp TH bằng `enroll.py --brand th_true_milk --kind th_true_milk`. Ảnh lấy từ các keyframe dạy,
   đủ cách xếp và mức sáng.
3. Nạp các ảnh cắt bị nhận nhầm bằng `--brand none` để database biết từ chối.
4. Đặt lại ngưỡng giống nhau theo ảnh cắt thật.
5. Chỉ train lại embedder (`train_embedder.py`, có ảnh thật) nếu database vẫn là chỗ làm trượt cổng.

**Bước đọc box chuyển vào repo:** `server/milk/long_adapter.py` thay cho `read_units` của Long. Adapter vẫn gọi
`detect` và `Recognizer` của Long, nhưng tự quyết SKU và điểm:
- **Lớp `th_true_milk`:** độ ủng hộ = tỉ lệ láng giềng trong database thuộc hãng TH, bất kể loại.
- **Lớp Vinamilk:** độ ủng hộ = tỉ lệ láng giềng đúng loại đó, như hiện nay.
- **Điểm:** `unit_score` = điểm YOLO × độ ủng hộ.
- **Database trả "unknown":** box thành `UNRECOGNIZED`, như hiện nay.
- **Tên sản phẩm:** đọc từ `server/milk/skus.json`. File này thêm `TMP-MLK-TH-00`.
- **Gọi tên loại:** theo `MILK_LONG_VARIANTS` ở mục 5.1.
- **Code mới vẫn chạy được với model cũ.** Với `best_types.pt` (12 lớp) và `MILK_LONG_TILE=0`, kết quả phải giống hệt
  bản hiện nay. Có test so trên vài frame thật. Nhờ vậy, quay lui chỉ cần đổi `worker.env`.

### 5.4 Đo và cổng

**Đo trên cả đường đếm như worker chạy:** sữa và Slide chạy chung rồi gộp lại, trên tập giữ riêng.

**Cách khớp box:** box của model khớp một khung thật nếu tâm box nằm trong khung đó. Khớp một đối một, box tự tin hơn
được khớp trước.

**Báo số theo hai cách:**
- theo frame;
- theo đoạn: mỗi đoạn một phiếu, để một đoạn dài gồm nhiều frame gần giống nhau không át số của các đoạn khác.

Báo cáo đo ghi ra `C:\Users\huyho\Datagent\store_eval\<phiên bản>.json`, kèm bản tóm tắt gửi hoang.

| Chỉ số | Ngưỡng để bật |
|---|---|
| Hộp TH tìm đúng (recall) | ≥ 0,85 |
| Box sữa báo ra đúng là hộp TH (precision, tính mọi SKU sữa, không tính `UNRECOGNIZED`) | ≥ 0,90 |
| Số hộp TH lệch không quá 1 | ≥ 80% số frame có TH |
| Box sữa trên frame không có TH (đêm, lúc chưa bày) | ≤ 1 box / 100 frame |
| Vinamilk trên val tổng hợp (mAP50 từng lớp) | giảm ≤ 0,02 so với `best_types.pt` chạy trên cùng tập val mới. Bộ ảnh sinh lại có val mới, nên không so thẳng với `results_types.json` |
| Số Slide | giống hệt bản đang chạy |

Ngưỡng là đề xuất của Claude. hoang đổi được.

**Trượt cổng:**
- Lặp lại theo thứ tự người làm chọn: thêm keyframe, train lại embedder, rồi đến render lốc tổng hợp.
- Nếu box Slide đè lên hộp TH và làm mất hộp ở bước gộp (`pipeline.merge` bỏ box sữa nằm dưới box Slide), sửa luật
  gộp. Ví dụ: chỉ bỏ box sữa khi box Slide đủ tự tin.
- Mỗi vòng báo số cho hoang.

### 5.5 Đưa vào chạy

**Repo, một PR:**
- adapter, `skus.json` và test;
- alias `TMP-MLK-TH-00` trong `backend/common.py` (`DEFAULT_ALIAS_MAP`): brand TH true MILK, Milk / Fresh Milk,
  180 ml;
- ảnh `frontend/public/images/products/th-true-milk-fresh-milk-180ml.png`: hai mặt hộp đặt cạnh nhau, từ ảnh có sẵn
  của hai loại;
- quy tắc gắn nhãn đổi từ A sang B:
  - nội dung mới: "đếm mọi đơn vị thuộc shelf plan của tiệm lộ mặt, nắp hoặc đỉnh đủ để nhận ra sản phẩm";
  - đổi chữ `"A"` thành `"B"` ở `backend/api/handler.py` (lưu và lọc) và `frontend/lib/audit-labeling.ts`;
  - frame gắn nhãn theo A sẽ hiện trong "Relabel them", vì thiếu TH.

**Live (sau khi qua cổng; hoang duyệt bước này như các lần trước):**
1. **Backend:** change set cho API và ingest, cộng dòng `sku_master` có `image_url`.
2. **Website:** Amplify, theo `frontend-deploy` trong memory.
3. **Worker:** cùng lúc thì đổi shelf plan.
   - Cập nhật bản clone repo trên HUYHOANG lên commit của PR, qua git bundle như các lần trước.
   - Sao lưu `worker.env`.
   - Đặt `MILK_LONG_DIR=…\carton_recognition_v2`, `MILK_LONG_YOLO=…\yolo\best_store_v1.pt`, `MILK_LONG_TILE=1280`,
     `MILK_LONG_VARIANTS=0`, `MILK_MODEL_VERSION=long-store-v1+slide-v3`.
   - Khởi động lại task `milk-worker`.
4. **Shelf plan DEMO-S01:** thay 2 SKU TH bằng dòng gộp. Làm bằng tài khoản team_admin qua API của trang Settings.
   Lịch sử 15 ngày sẽ được tính lại ở lần tick kế tiếp.
   - Cùng lúc, xoá hai dòng `latest_stock` cũ của TH-01 và TH-02 (đang 0 hộp). Như vậy Products không hiện hai dòng 0
     gây hiểu nhầm, vì worker sẽ không báo hai nhãn này nữa.
5. **Team gắn nhãn lại các frame AUD theo quy tắc B.** Từ đó trang Model có số TH theo `model_version` mới.
6. **Nếu muốn, train lần cuối trên toàn bộ dữ liệu.** Cập nhật `TRAINING.md` trên HUYHOANG và nhật ký HOANG-P10.

**Quay lui:**
- Chép lại `worker.env` từ bản sao lưu.
- Model và database cũ không bị đụng tới.
- Shelf plan khôi phục từ danh sách cũ (4 Slide + 2 TH).

**Script mới nằm trong repo, ở `training/store_view/`:**
- gom ảnh: chạy trên laptop;
- chia đoạn, lan nhãn, tạo bộ dạy, đo: chạy trên HUYHOANG từ bản clone repo.

Ảnh và nhãn không bao giờ vào repo.

### 5.6 Để người làm tự quyết

- Ngưỡng chia đoạn và lan nhãn.
- Độ chồng giữa các ô.
- Tỉ lệ trộn ảnh thật và ảnh tổng hợp, cùng các phép tăng cường ảnh.
- Số giờ train (dự kiến từ 4 giờ trở lên).
- Ngưỡng của database v2.
- Ngưỡng nghiêng về một loại khi `MILK_LONG_VARIANTS=1`.
- Tên file và thư mục (giữ theo mẫu trên).
- Cách viết test.
- Cách chép ảnh có giới hạn băng thông.

## 6. Để sau

- **Render lốc tổng hợp:** đứng, nằm, nhìn từ trên, có màng bọc. Dùng cho tiệm mới hoặc khi cổng hụt ở kiểu xếp chưa
  có.
- **Vẽ khung trên trang Model,** để team tự gắn nhãn khi đưa tiệm mới vào, không phải nhờ Claude.
- **Trang Model không chấm có/không có hàng cho SKU chưa ai gắn nhãn.** Đây là phương án (c) ngày 25/11.
- **Display check theo từng vùng,** khi một camera thấy nhiều kệ.
- **Gọi tên Có đường / Ít đường** ở camera đọc được chữ.
- **Các nhóm hàng khác** (snack, …).
