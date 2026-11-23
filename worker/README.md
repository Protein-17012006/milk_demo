# Worker đếm trên GPU (máy long)

Kiến trúc hybrid: AWS là hub (nhận luồng từ tiệm, dashboard, lưu trữ), còn việc đếm chạy
trên GPU của máy long. Worker kéo luồng từ hub qua RTSPS, đếm, rồi gửi kết quả về hub qua
HTTPS kèm token. Máy long **không mở cổng nào, không giữ key AWS, không lưu ảnh**: ảnh đã
che mặt do hub lưu lên S3.

```
camera -> relay tại tiệm -> hub AWS (MediaMTX) --RTSPS--> worker máy long (GPU)
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

## Chạy nền

Theo quy tắc dùng máy chung (job dài hơn 30 phút thì ghi vào `RESOURCES.md`), chạy bằng
systemd của user, có giới hạn RAM và nice 10 như các job P05, P06. File mẫu:
[milk-worker.service](milk-worker.service).

## Tiết kiệm băng thông

Luồng từ hub về máy long tính phí ra internet của AWS (100 GB/tháng đầu miễn phí, khoảng
2 GB mỗi giờ với luồng 4K 4–6 Mbps). Tắt worker khi không dùng; `MILK_MAX_FPS` và
`MILK_PUBLISH_FPS` giới hạn số khung đếm và số lần gửi về dashboard mỗi giây.
