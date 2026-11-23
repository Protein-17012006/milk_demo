# Worker đếm trên GPU

Kiến trúc hybrid: AWS là hub (nhận luồng từ tiệm, dashboard, lưu trữ), còn việc đếm chạy trên GPU của một máy
trong team. Từ 23/11/2026 đó là máy HUYHOANG (Windows, xem mục "Chạy trên Windows"); trước đó là máy long
(Linux, systemd). Worker kéo luồng từ hub qua RTSPS, đếm, rồi gửi kết quả về hub qua HTTPS kèm token. Máy chạy
worker **không mở cổng nào, không giữ key AWS, không lưu ảnh**: ảnh đã che mặt do hub lưu lên S3.

```
camera -> relay tại tiệm -> hub AWS (MediaMTX) --RTSPS--> worker trên máy GPU
                                   ^                            |
                                   +------ HTTPS + token -------+  (kết quả, ảnh đã che mặt)
```

## Cần có

- `ffmpeg` và `ffprobe` (`sudo apt install ffmpeg`).
- Python của môi trường đang chạy model (torch, ultralytics, lancedb), cộng thêm
  `pip install -r server/requirements-worker.txt`.
- File `worker.env` do hoang gửi riêng. File này chứa mật khẩu và token: không commit, không
  dán lên Confluence hay Sheet.
- Che người trước khi lưu hoặc hiển thị, hai lớp chạy nối nhau:
  - `MILK_PERSON_MODEL`: trọng số YOLO bản COCO gốc (ví dụ `yolo26s.pt`), che cả người. Bắt được
    cả người nhìn từ trên xuống, trường hợp YuNet bỏ sót.
  - `MILK_YUNET`: model YuNet `face_detection_yunet_2023mar.onnx`
    ([opencv_zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet)), che mặt.

  Không nạp được cả hai thì worker vẫn đếm nhưng hub không lưu ảnh nào.

## Chạy thử

```bash
git clone <repo> ~/milk-camera && cd ~/milk-camera/server
python -m milk.counter --env ~/milk-camera/worker.env
```

Đúng thì log có dòng `camera CAM-S01-A, pipeline ... on cuda` và dashboard hiện
`Model: ... (cuda · gpu-worker)`.

## Phiên bản model

Mỗi kết quả worker lưu đều có trường `model_version`. Trang Model trên website dựa vào trường này
để so trước và sau mỗi lần đổi model. Mỗi lần đổi trọng số thì đặt lại biến trong `worker.env`, ví dụ:

```
MILK_MODEL_VERSION=long-2026-10-13+slide-v3
```

Không đặt thì worker tự ghép `MILK_PIPELINE` với tên thư mục chứa `MILK_SLIDE_WEIGHTS`, ví dụ
`long+slide:runs_v3`. Kết quả còn có `detections`: từng hộp với độ tin cậy riêng của nó.

## Chạy trên Windows (máy HUYHOANG, từ 23/11)

- **Thư mục gốc** `C:\Users\huyho\Datagent`, đặt tên giống `~/Desktop/Datagent` của máy long. Bên trong có:
  - `carton_recognition\`, `yolo\`, `slide_pilot\runs_v3\`, `ingest_bench\data\models\`.
  - `milk_demo\` (repo này), `worker.env`.
  - `.venv\`: Python 3.12, torch 2.11.0+cu128, ultralytics 8.4.47, lancedb 0.40.0, opencv-contrib-python 4.10.0.84.
- **`worker.env`**: đường dẫn viết bằng `/`, ví dụ `C:/Users/huyho/Datagent/...`. Chỉ `SYSTEM` và người dùng máy
  được đọc file (đặt bằng `icacls`).
- **ffmpeg**: cài bằng `winget install --id Gyan.FFmpeg -e`. Script chạy nền tự tìm ffmpeg, vì PATH của
  `SYSTEM` không có thư mục của winget.
- **Chứng chỉ của hub**: hub dùng chứng chỉ TLS tự ký (`CN=milk-demo-ingest`), và ffmpeg 9 trên Windows từ chối
  chứng chỉ đó (log báo `Peer certificate failed verification`). Lấy chứng chỉ ngay trên hub bằng
  `.\infra\remote-run.ps1 "cat /etc/mediamtx/server.crt"`, lưu thành `C:\Users\huyho\Datagent\hub-ingest.crt`, rồi
  thêm hai dòng vào `worker.env`:

  ```
  MILK_STREAM_CA_FILE=C:/Users/huyho/Datagent/hub-ingest.crt
  MILK_STREAM_TLS_NAME=milk-demo-ingest
  ```

  Worker vẫn kiểm chứng chỉ, nhưng chỉ tin đúng chứng chỉ của hub. Dựng lại hub là sinh chứng chỉ mới, nên phải
  chép lại file này.
- **Đăng ký chạy nền** (một lần, PowerShell quyền admin):
  `powershell -ExecutionPolicy Bypass -File worker\windows\register-task.ps1 -Root C:\Users\huyho\Datagent`.
  Lệnh này tạo task `milk-worker`:
  - Chạy `worker\windows\run-worker.ps1` khi máy khởi động, dưới tài khoản `SYSTEM`.
  - Worker chạy ở mức ưu tiên thấp. Worker thoát thì 5 giây sau chạy lại.
  - Log ở `logs\worker-YYYY-MM-DD.log`, giữ 14 ngày.
- **Bật và tắt**: `Start-ScheduledTask milk-worker` và `Stop-ScheduledTask milk-worker`. Trước khi bật, phải tắt
  worker ở máy khác đang đếm cùng camera.
- **Nạp torch trước**: trên Windows, gói `milk` nạp torch trước mọi thư viện native khác. Nếu ssl và cv2 nạp trước
  torch thì pyarrow (lancedb dùng) làm tiến trình chết với lỗi 0xC0000005. Chi tiết ở `server/milk/torch_first.py`.
  Sau mỗi lần nâng torch hoặc pyarrow, chạy `python -m pytest tests/test_torch_first.py` trên máy đó.

## Chạy nền

Theo quy tắc dùng máy chung (job dài hơn 30 phút thì ghi vào `RESOURCES.md`), chạy bằng
systemd của user, có giới hạn RAM và nice 10 như các job P05, P06. File mẫu:
[milk-worker.service](milk-worker.service).

## Tiết kiệm băng thông

Hai chiều dữ liệu tốn tiền:
- **Video từ hub về máy chạy worker:** AWS tính phí ra internet. 100 GB đầu mỗi tháng miễn phí, sau đó $0,12/GB.
  Luồng 2560×1440 khoảng 2,5–3,2 GB mỗi giờ.
- **Ảnh kết quả gửi lên hub qua CloudFront:** $0,06/GB, khoảng 1,6–3,8 GB mỗi giờ.

`MILK_MAX_FPS` và `MILK_PUBLISH_FPS` giới hạn số khung đếm và số lần gửi về dashboard mỗi giây.

### Đếm theo nhịp

Website chỉ cần một lần đếm chính thức mỗi giờ, nên không cần đọc luồng liên tục:

```
MILK_SAMPLE_EVERY_S=300   # cứ 300 giây mở một lượt, ở các mốc 12:00, 12:05, ...
MILK_SAMPLE_FOR_S=30      # mỗi lượt đọc luồng 30 giây rồi ngắt
```

- **Ngoài lượt:**
  - Worker không mở luồng, nên MediaMTX trên hub cũng thôi kéo camera.
  - Hai chiều dữ liệu trên giảm khoảng 90%.
  - Worker vẫn gửi trạng thái mỗi 2 giây. Dashboard hub hiện "Đếm theo nhịp · lượt kế tiếp HH:MM".
- **Trong lượt:**
  - Bộ làm mượt bắt đầu lại từ đầu.
  - Chỉ lưu khi đã đủ `MILK_SMOOTH_WINDOW` khung, nên mỗi lượt lưu khoảng 3–4 lần.
- **Cần dashboard live** (ví dụ ngày demo): đặt `MILK_SAMPLE_EVERY_S=0` rồi khởi động lại worker. Bỏ trống thì cũng
  là đếm liên tục.
