# Chuyển worker đếm và pipeline huấn luyện từ máy long sang máy HUYHOANG

Ngày 2026-11-23 · hoang chọn phạm vi và cách dựng trong chat · nối tiếp HOANG-P10

## Vì sao

- **hoang, chat 23/11:** *"kéo pipeline trainning và model từ máy a long qua máy huyhoang để chạy chính"*.
  Từ 22/11 hoang đã nhận phần việc của long.
- Hiện worker đếm sống (sữa và Slide v3) và mọi dữ liệu, script huấn luyện đều nằm trên máy long (Ubuntu 24.04,
  RTX 5090). Đó là máy dùng chung của người khác.
- HUYHOANG là PC Windows của hoang, cũng RTX 5090 32 GB, ổ C còn trống 884 GB. Máy đã có Blender 5.3 và code
  render Slide của HOANG-P09.

## Đã chốt với hoang

- **Phạm vi:** "Chạy đếm + huấn luyện lại".
  - Mang sang: worker và các model đang chạy, code huấn luyện sữa và Slide, ảnh test và đáp án chấm, dữ liệu
    thật không render lại được.
  - Không mang: các dataset đã render (sẽ render lại trên HUYHOANG), ComfyUI/FLUX (tải thẳng từ internet khi
    cần), `arch_bench` và `rfdetr`.
  - Lý do: máy long chỉ đẩy ra được khoảng 0,6 MB/s, nên 240 GB sẽ mất 4–5 ngày.
- **Cách dựng:** "Chạy thẳng trên Windows". Không dùng WSL2, không dùng Docker.
  - Đã kiểm: code worker và code huấn luyện không có lời gọi riêng của Linux.
  - Đã kiểm: code huấn luyện không ghi cứng đường dẫn `/home/long`.

## Mục tiêu

1. Worker chạy trên HUYHOANG với đúng model và code đang chạy trên máy long. Nó tự bật khi máy khởi động và
   tự chạy lại khi lỗi.
2. Chạy được trên HUYHOANG cả hai việc huấn luyện:
   - Sữa: YOLO nhận loại hộp, embedder, CSDL LanceDB.
   - Slide: render, ghép ảnh, train, chấm.
3. Sau khi HUYHOANG chạy ổn thì tắt worker trên máy long. Có sẵn cách quay lại.

## Không làm

- Không đổi model, không đổi code đếm.
- Không xoá gì trên máy long. Chỉ dừng và tắt tự khởi động của service `milk-worker` ở đó.
- Chưa đưa code huấn luyện của long (`carton_recognition`, `slide_pilot/code`, `cctv_dataset/*.py`) vào repo
  của team. Việc này để hoang quyết sau.

## Không được xảy ra

- Hai worker cùng gửi kết quả cho một camera. Chuyển phải theo thứ tự: tắt máy long trước, rồi mới bật HUYHOANG.
- Mất đếm sống quá vài phút lúc chuyển.
- Mật khẩu luồng hoặc token của hub lọt vào repo, log hay màn hình.

## Thiết kế

### 1. Bố trí trên HUYHOANG

`C:\Users\huyho\Datagent\`, đặt tên giống `~/Desktop/Datagent` của máy long để lệnh và tài liệu đổi 1–1.

| Thư mục | Lấy từ máy long | Cỡ |
|---|---|---|
| `carton_recognition\` | `*.py`, `config*.json`, `embedder*.pt`, `db\`, `db_types\`, `checked_videos*\`, `cross_check_examples*\`, `checked_flux_samples\`, các file `*.json` kết quả. Bỏ `.venv` và `__pycache__` | ~0,77 GB |
| `yolo\` | toàn bộ: `train.py`, log, trọng số gốc, `runs\`, `best_types.pt` | 256 MB |
| `slide_pilot\` | `code\`, `runs\`, `runs_v3\`, `test_frames\`, `eval\`, `backgrounds_store\`, `gt_store_view*.json` | ~0,34 GB |
| `cctv_dataset\` | `*.py`, `props\`, `backgrounds\`, `dataset_hard_types\` | ~1,1 GB |
| `cv_output_sample\` | toàn bộ (để chạy `worker/regression.py`) | 20 MB |
| `ingest_bench\data\models\` | `face_detection_yunet_2023mar.onnx` | 0,2 MB |
| `milk_demo\` | `git clone` từ GitHub, nhánh `feat/model-page` (bản worker đang chạy) cho tới khi PR #5 vào `main` | — |
| `worker.env` | chép từ máy long, đổi 4 đường dẫn, `MILK_WORKER_NAME=huyhoang-gpu`. Chỉ `SYSTEM` và `huyho` được đọc | — |
| `.venv\`, `logs\` | dựng mới | — |

### 2. Chép từ máy long

- Laptop nối thẳng được tới máy long, còn HUYHOANG thì phải đi qua relay của Tailscale. Laptop và HUYHOANG cùng
  mạng LAN. Vì vậy dữ liệu đi theo đường: máy long → `tar` qua ssh → laptop (scratchpad) → `scp` qua LAN →
  HUYHOANG → giải nén.
- Máy long tính `sha256` cho từng file trước khi gửi. HUYHOANG kiểm lại sau khi giải nén. Sai một file thì
  chép lại file đó.

### 3. Môi trường

- **Python:** venv 3.12 tại `C:\Users\huyho\Datagent\.venv`. Phiên bản lấy từ `pip freeze` của venv worker trên
  máy long: torch 2.11.0+cu128 (index `download.pytorch.org/whl/cu128`), ultralytics 8.4.47, lancedb 0.40.0,
  opencv và numpy cùng bản. Cộng thêm `server/requirements-worker.txt`.
- **Kiểm GPU:** `torch.cuda.is_available()` và chạy được một phép tính trên RTX 5090 (sm_120).
- **ffmpeg:** cài bằng `winget`. Supervisor của worker tự đặt PATH nên không phụ thuộc PATH của tài khoản.

### 4. Worker chạy nền

- **Task Scheduler:** task `milk-worker`, chạy khi máy khởi động, tài khoản `SYSTEM`, quyền cao nhất. Không
  cần lưu mật khẩu, và chạy được cả khi chưa ai đăng nhập.
- **Supervisor** là script `worker/windows/run-worker.ps1` trong repo. Nó lặp mãi:
  - Chạy `python -m milk.counter --env worker.env` với độ ưu tiên BelowNormal (như `nice 10` trên máy long).
  - Ghi log vào `logs\worker-YYYY-MM-DD.log` và giữ 14 ngày.
  - Worker thoát thì 5 giây sau chạy lại (như `Restart=always`).
- **Nguồn điện:** khi cắm điện, HUYHOANG không tự ngủ. Màn hình vẫn được tắt.

### 5. Kiểm trước khi chuyển

| Mức | Kiểm | Đạt khi |
|---|---|---|
| G1 | `slide_pilot/code/synth/eval_real.py` với `runs_v3/best.pt` trên `test_frames` | Ra đúng số của v3 trên máy long: 91% / 68% / 10 |
| G2 | `worker/regression.py` trên `cv_output_sample` | Hàng CV Output của worker trùng với `cv_output.py` của long |
| G3 | Chạy worker trên HUYHOANG khoảng 2 phút, `MILK_HUB_URL` trỏ tới địa chỉ không tồn tại nên không gửi gì cho hub | Đọc được luồng camera, model chạy trên GPU, không có lỗi ngoài lỗi "không tới được hub" |
| G4 | Train thử trên HUYHOANG: (a) YOLO loại hộp sữa 1 epoch trên `dataset_hard_types`; (b) Slide: render 20 cảnh bằng code P09, ghép ảnh, train 1 epoch, chấm bằng `eval_real.py` | Mỗi bước chạy hết, không lỗi. Không đòi điểm cao |

### 6. Chuyển và quay lại

- **Chuyển:**
  1. Trên máy long: `systemctl --user stop milk-worker` và `disable`.
  2. Trên HUYHOANG: bật task `milk-worker`.
  3. Trong 2 phút phải thấy: `results/*.json` mới có `MILK_WORKER_NAME=huyhoang-gpu` trong trạng thái hub, có
     `model_version`, ingest không lỗi, website vẫn cập nhật.
- **Quay lại:** tắt task trên HUYHOANG, rồi `enable --now milk-worker` trên máy long.

### 7. Huấn luyện trên HUYHOANG

Viết `C:\Users\huyho\Datagent\TRAINING.md` (không đưa vào repo, vì code huấn luyện chưa ở trong repo). Nội dung:

- **Slide:** render bằng script P09 trong Blender → `compose_dataset.py` (`--backgrounds`, `--cctv-dataset`,
  `--props`, `--occlude`) → `train_detector.py` → `eval_real.py`.
- **Sữa:** `yolo\train.py` cho bộ nhận loại hộp; `carton_recognition` để train embedder và build/enroll CSDL.
- Cách lấy lại ComfyUI và FLUX khi cần sinh nền mới.
- Quy tắc cũ vẫn giữ: chấm mọi model mới bằng `eval_real.py` theo từng nhóm, không bao giờ train trên ảnh test.

### 8. Rủi ro

- **Tranh GPU** khi đang render hoặc train: worker chạy ở mức ưu tiên thấp; 32 GB đủ cho cả hai. Nếu khung/giây
  tụt rõ thì tạm dừng train.
- **HUYHOANG tắt máy hoặc Windows Update khởi động lại:** task tự bật khi máy lên. Trong lúc máy tắt thì không
  đếm, giống khi máy long tắt.
- **Băng thông:** luồng từ hub về HUYHOANG vẫn tốn khoảng 2 GB/giờ phí ra internet của AWS, như khi về máy long.

## Để người làm tự quyết

Tên log, cách xoay vòng log, lệnh `winget` cụ thể, cách đổi đường dẫn trong `worker.env`, và số cảnh render ở G4
(miễn là đủ để chạy hết một vòng).
