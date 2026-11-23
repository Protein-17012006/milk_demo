# Chuyển worker đếm và pipeline huấn luyện sang HUYHOANG — kế hoạch làm

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** HUYHOANG (Windows, RTX 5090) chạy worker đếm sống thay máy long. Trên HUYHOANG chạy được cả huấn luyện
sữa lẫn Slide. Worker trên máy long tắt sau khi chuyển xong.

**Architecture:**
- Dữ liệu đi thẳng từ máy long sang HUYHOANG: gói `.tar` phục vụ bằng HTTP tạm trên IP Tailscale, tải bằng
  `curl`, kiểm `sha256`.
- Môi trường: một venv Python 3.12 trên Windows, cùng phiên bản thư viện như máy long.
- Worker chạy nền bằng Task Scheduler (`SYSTEM`), qua script canh `worker/windows/run-worker.ps1`.

**Tech Stack:** Windows 11, Python 3.12, torch 2.11.0+cu128, ultralytics 8.4.47, lancedb 0.40.0, ffmpeg (winget),
Task Scheduler, PowerShell 5.1, Blender 5.3 (render Slide của P09).

**Spec:** `docs/superpowers/specs/2026-11-23-huyhoang-gpu-machine-design.md`

## Global Constraints

- **Gốc dữ liệu** trên HUYHOANG là `C:\Users\huyho\Datagent`. Trong `worker.env` ghi đường dẫn bằng dấu `/`
  (`C:/Users/huyho/Datagent/...`).
- **Không bao giờ có hai worker** gửi kết quả cho `CAM-S01-A`. Tắt máy long trước, rồi mới bật HUYHOANG.
- **`worker.env`** không được in ra, không vào repo, không vào log. Chỉ `SYSTEM` và `huyho` được đọc.
- **Trên máy long** chỉ được tạo rồi xoá `~/transfer-huyhoang/`, và dừng cộng tắt tự khởi động service
  `milk-worker`. Không đụng vào file nào khác.
- **Phiên bản thư viện** lấy đúng từ `pip freeze` của `~/Desktop/Datagent/carton_recognition/.venv` trên máy long.
- **`MILK_WORKER_NAME=huyhoang-gpu`**.
- **Lệnh từ laptop:** dùng `ssh huyho@100.127.91.122` (cmd hoặc `powershell -NoProfile`) và
  `ssh long@100.71.161.102`. Riêng `worker.env` đi qua ống ssh; dữ liệu lớn không qua laptop.
- **Commit trên nhánh `ops/huyhoang-gpu`** dùng cùng danh tính noreply và dòng `Co-Authored-By` như plan trước.

## Review Focus

1. Worker chết hoặc máy khởi động lại thì phải tự chạy lại. Thử bằng cách giết `python.exe` của worker: trong
   khoảng 10 giây phải có tiến trình mới (Task 6).
2. `worker.env` có thể chứa CRLF, dấu nháy, hoặc mật khẩu có ký tự đặc biệt. Kiểm `config.load()` trên
   HUYHOANG đọc ra đúng 20 biến, đường dẫn tồn tại (Task 3).
3. Log không được phình mãi: log theo ngày, xoá log quá 14 ngày (Task 6).
4. GPU vừa render hoặc train vừa đếm: đo số khung/giây của worker lúc G4 đang chạy, ghi vào sổ tiến độ (Task 5).
5. Tải đứt giữa chừng: `curl -C -` phải tải tiếp, và `sha256` phải khớp trước khi giải nén (Task 1).

---

### Task 1: Đóng gói trên máy long, tải thẳng về HUYHOANG

- [ ] **Step 1:** Trên máy long, tạo các gói trong `~/transfer-huyhoang/` (đường dẫn tương đối từ `~/Desktop/Datagent`):
  - `carton_recognition.tar`: thư mục `carton_recognition`, bỏ `.venv` và `__pycache__`.
  - `yolo.tar`: thư mục `yolo`.
  - `slide_pilot.tar`: `slide_pilot/{code,runs,runs_v3,test_frames,eval,backgrounds_store}` và `slide_pilot/gt_store_view*.json`. Bỏ `__pycache__`.
  - `cctv_dataset.tar`: `cctv_dataset/*.py` và `cctv_dataset/{props,backgrounds,dataset_hard_types}`.
  - `misc.tar`: `cv_output_sample` và `ingest_bench/data/models/face_detection_yunet_2023mar.onnx`.
  - `sha256sum *.tar > SHA256SUMS`.
  - Mong đợi: tổng khoảng 2,5 GB.
- [ ] **Step 2:** Bật máy chủ tạm, có giới hạn thời gian:
  `timeout 4h python3 -m http.server 8765 --bind 100.71.161.102 --directory ~/transfer-huyhoang`, chạy nền và tách khỏi phiên ssh.
- [ ] **Step 3:** Trên HUYHOANG, tải `SHA256SUMS` và từng gói vào `C:\Users\huyho\Datagent\_incoming` bằng
  `curl.exe -C - -o <file> http://100.71.161.102:8765/<file>`, lặp lại tối đa 5 lần mỗi gói. Chạy nền từ laptop
  để theo dõi. Mong đợi: tải đủ 5 gói.
- [ ] **Step 4:** So `Get-FileHash -Algorithm SHA256` của từng gói với `SHA256SUMS`. Mong đợi: 5/5 khớp. Gói nào lệch thì tải lại.
- [ ] **Step 5:** Giải nén vào `C:\Users\huyho\Datagent` bằng `tar.exe -xf`. Kiểm các file phải có:
  `carton_recognition\embedder_types.pt`, `carton_recognition\db_types\`, `yolo\best_types.pt`, `yolo\yolo26s.pt`,
  `slide_pilot\runs_v3\best.pt`, `slide_pilot\test_frames\`, `slide_pilot\gt_store_view.json`,
  `cctv_dataset\props\props.json`, `ingest_bench\data\models\face_detection_yunet_2023mar.onnx`. Mong đợi: đủ cả.

### Task 2: Môi trường Python, ffmpeg, GPU

- [ ] **Step 1:** Lấy `pip freeze` của venv worker trên máy long. Chọn ra các gói worker và huấn luyện cần:
  torch, torchvision, ultralytics, lancedb, numpy, opencv-*, pillow, pyarrow, scipy, matplotlib, pandas, và những
  gì `carton_recognition`/`slide_pilot` import.
- [ ] **Step 2:** `py -3.12 -m venv C:\Users\huyho\Datagent\.venv`. Cài torch và torchvision đúng bản, từ
  `--index-url https://download.pytorch.org/whl/cu128`. Cài phần còn lại theo bản đã ghim, rồi
  `milk_demo/server/requirements-worker.txt` (sau Task 3, bước 1). Nếu bản nào không có wheel cho Windows thì
  chọn bản gần nhất và ghi lại quyết định.
- [ ] **Step 3:** `winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements`,
  rồi tìm thư mục `bin` của ffmpeg. Mong đợi: `ffmpeg -version` và `ffprobe -version` chạy được.
- [ ] **Step 4:** Kiểm GPU bằng
  `python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0)); x=torch.randn(2048,2048,device='cuda'); print(float((x@x).abs().sum()))"`.
  Mong đợi: `True`, `NVIDIA GeForce RTX 5090`, và một số hữu hạn.

### Task 3: Code worker và `worker.env`

- [ ] **Step 1:** `git clone https://github.com/Protein-17012006/milk_demo.git C:\Users\huyho\Datagent\milk_demo`,
  rồi `git checkout feat/model-page`.
- [ ] **Step 2:** Ghi `worker.env` sang HUYHOANG qua ống ssh, đổi trên đường đi:
  - `/home/long/Desktop/Datagent` thành `C:/Users/huyho/Datagent`.
  - `MILK_WORKER_NAME=` thành `huyhoang-gpu`.
  - CRLF thành LF.
  - Không in nội dung ra.
- [ ] **Step 3:** `icacls worker.env /inheritance:r /grant:r SYSTEM:F huyho:F`.
- [ ] **Step 4:** Kiểm bằng venv: `config.load("C:/Users/huyho/Datagent/worker.env")`. Mong đợi:
  - `pipeline == "long+slide"`, `model_version == "long-2026-10-13+slide-v3"`.
  - Các đường dẫn trong `MILK_LONG_DIR`, `MILK_YUNET`, `MILK_PERSON_MODEL`, `MILK_SLIDE_WEIGHTS` đều tồn tại.
  - Chỉ in tên biến và đúng/sai, không in giá trị.

### Task 4: Ba bước kiểm G1–G3

- [ ] **G1:** `python slide_pilot\code\synth\eval_real.py slide_pilot\runs_v3\best.pt slide_pilot\test_frames slide_pilot\gt_store_view.json slide_pilot\gt_store_view_1609.json`.
  Mong đợi: như v3 trên máy long, nhãn thấy được 91%, nắp 68%, nắp lạ bị gọi là của mình 10.
- [ ] **G2:** đặt `MILK_LONG_DIR` rồi chạy `python milk_demo\worker\regression.py cv_output_sample`. Mong đợi:
  regression báo các hàng trùng khớp, như khi chạy trên máy long.
- [ ] **G3:** chạy `python -m milk.counter --env worker.env` khoảng 120 giây, với `MILK_HUB_URL=http://127.0.0.1:9`
  đặt trong môi trường (biến đã có thì `load_env_file` không ghi đè). Mong đợi:
  - Log có `camera CAM-S01-A, pipeline long+slide on cuda, blur on`.
  - Không có traceback ngoài cảnh báo "could not reach the hub".
  - Tiến trình dừng gọn khi bị tắt.

### Task 5: G4, chạy thử huấn luyện trên HUYHOANG

- [ ] **Step 1 (sữa):** đọc cách dùng của `yolo\train.py`, rồi train loại hộp 1 epoch trên `cctv_dataset\dataset_hard_types`, ghi ra thư mục tạm (không đè `yolo\runs`). Mong đợi: chạy hết 1 epoch, có `weights\last.pt`.
- [ ] **Step 2 (Slide):**
  - Render 20 cảnh bằng script P09 trong `C:\Users\huyho\OneDrive\Desktop\milk_camera\synth\` với Blender 5.3 (đọc cách dùng trước).
  - Ghép ảnh: `compose_dataset.py` với `--backgrounds slide_pilot\backgrounds_store`, `--cctv-dataset cctv_dataset`, `--props cctv_dataset\props`.
  - Train 1 epoch: `train_detector.py`.
  - Chấm: `eval_real.py`.
  - Mong đợi: bước nào cũng chạy hết, không đòi điểm cao.
- [ ] **Step 3:** Trong lúc G4 chạy, đo số khung/giây của worker ở G3 (nếu bật lại) hoặc ghi chú GPU đang bận. Ghi vào sổ tiến độ.

### Task 6: Script canh worker, Task Scheduler, nguồn điện

**Files:** Create `worker/windows/run-worker.ps1`; Modify `worker/README.md` (thêm mục chạy trên Windows).

- [ ] **Step 1:** Viết `run-worker.ps1`, tham số `-Root C:\Users\huyho\Datagent`. Script:
  - Thêm thư mục `bin` của ffmpeg vào PATH.
  - Vòng lặp: chạy `.venv\Scripts\python.exe -m milk.counter --env worker.env` (thư mục làm việc `milk_demo\server`, độ ưu tiên BelowNormal), ghi stdout và stderr vào `logs\worker-yyyy-MM-dd.log`.
  - Worker thoát thì ghi một dòng vào log, chờ 5 giây rồi chạy lại.
  - Mỗi vòng xoá log quá 14 ngày.
- [ ] **Step 2:** Đăng ký task `milk-worker` bằng `Register-ScheduledTask`:
  - Trigger AtStartup, tài khoản `SYSTEM`, RunLevel Highest.
  - Không giới hạn thời gian chạy (`ExecutionTimeLimit` = 0). Nếu task lỗi thì chạy lại sau 1 phút.
  - Chưa chạy ngay.
- [ ] **Step 3:** `powercfg /change standby-timeout-ac 0` và `powercfg /change hibernate-timeout-ac 0`.
  Mong đợi: `powercfg /query` cho thấy ngủ khi cắm điện là 0.

### Task 7: Chuyển

- [ ] **Step 1:** Trên máy long: `systemctl --user stop milk-worker && systemctl --user disable milk-worker`.
  Mong đợi: `inactive` và `disabled`.
- [ ] **Step 2:** Trên HUYHOANG: `Start-ScheduledTask milk-worker`. Mong đợi: trong 2 phút có thêm
  `results/CAM-S01-A/<hôm nay>/*.json` mới với `model_version` và `detections`. Log HUYHOANG có dòng `pipeline long+slide on cuda`.
- [ ] **Step 3:** Thử khả năng tự chạy lại: giết `python.exe` của worker. Mong đợi: trong 10 giây có tiến trình
  mới, và kết quả tiếp tục về hub.
- [ ] **Step 4:** Backend ingest không lỗi sau khi chuyển, DLQ = 0. Trang Model có giờ mới.
- [ ] **Quay lại (chỉ khi lỗi):** `Disable-ScheduledTask milk-worker` và dừng tiến trình trên HUYHOANG, rồi
  `systemctl --user enable --now milk-worker` trên máy long.

### Task 8: Kết thúc

- [ ] **Step 1:** Viết `C:\Users\huyho\Datagent\TRAINING.md` (lệnh Windows cho Slide và sữa, theo spec mục 7).
- [ ] **Step 2:** Trên máy long: dừng máy chủ tạm, rồi `rm -r ~/transfer-huyhoang`. Xoá `C:\Users\huyho\Datagent\_incoming`.
- [ ] **Step 3:** Commit `worker/windows/run-worker.ps1` và `worker/README.md`. Push nhánh `ops/huyhoang-gpu`, mở PR
  với base là `feat/model-page` (chồng lên PR #5).
- [ ] **Step 4:** Ghi Nhật ký HOANG-P10, cập nhật bộ nhớ (máy chạy worker giờ là HUYHOANG).
