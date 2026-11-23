# Đếm theo nhịp: worker chỉ đọc luồng camera theo lượt

Ngày 23/11/2026. hoang chọn phương án A trong chat ngày 23/11, sau khi xem bảng so sánh A, B1 và B2.

## Vì sao

- **Đọc luồng tốn tiền.** Worker trên HUYHOANG đọc luồng camera liên tục qua hub, khoảng 2,5–3,2 GB/giờ đi ra
  khỏi AWS. Chiều này tính $0,12/GB sau 100 GB miễn phí mỗi tháng.
- **Gửi ảnh kết quả cũng tốn.** Worker gửi ảnh kết quả lên hub qua CloudFront, khoảng 1,6–3,8 GB/giờ, tính
  $0,06/GB.
- **Tổng:** theo lịch hiện tại (hub bật khoảng 12:40–23:00), hai khoản này khoảng $180/tháng. Nếu chạy 24/7 thì
  khoảng $430/tháng.
- **Không cần đếm liên tục.** Website chỉ cần một lần đếm chính thức mỗi giờ (backend tự chọn), nên đếm liên tục
  khoảng 3,5 khung/giây là thừa.

## Các phương án đã cân nhắc

| | Tiền dữ liệu/tháng (lịch hiện tại / 24/7) | Đổi lại |
|---|---|---|
| **A. Đếm theo nhịp (chọn)** | ~$11 / ~$41 | Dashboard hub không còn live. Kiến trúc, mã hoá và mật khẩu camera giữ nguyên |
| B1. Worker đọc thẳng camera | ~$72 / ~$164 | Mật khẩu camera nằm trên HUYHOANG, video không mã hoá, đổi quyết định P10 số 1 |
| B2. B1 + gửi kết quả qua Tailscale | ~$0 / ~$0 | Như B1, cộng thêm hub phải gia nhập mạng Tailscale |

## Mục tiêu

- **Đọc theo lượt.** Worker chỉ đọc luồng trong các lượt: cứ `MILK_SAMPLE_EVERY_S` giây thì mở luồng trong
  `MILK_SAMPLE_FOR_S` giây. Trên HUYHOANG đặt 300 và 30.
  - Ngoài lượt, worker không mở luồng nào. MediaMTX trên hub kéo camera theo yêu cầu, nên không ai đọc thì hub
    cũng thôi kéo.
  - Lượt bám theo đồng hồ: mở ở các mốc chia hết cho `MILK_SAMPLE_EVERY_S`, ví dụ 12:00, 12:05, 12:10.
- **Vẫn đếm liên tục được.** `MILK_SAMPLE_EVERY_S=0` là giá trị mặc định trong code, cho kết quả đếm liên tục như
  hiện nay. Ngày demo cần live thì đặt lại 0 rồi khởi động lại task.
- **Đường dữ liệu và bảo mật không đổi.** Hub vẫn đứng giữa (RTSPS), mật khẩu camera vẫn chỉ nằm trên hub.

## Không làm

- Không đổi cách đếm, model hay ngưỡng.
- Không đổi backend và website.
- Không đổi đường đọc camera hay đường gửi kết quả (đó là cách B).

## Thiết kế

1. **`server/milk/sampling.py`, lớp `Sampler(every_s, for_s, open_reader)`:**
   - `in_window(now)`: đúng khi `every_s <= 0`, hoặc khi `now % every_s < for_s`.
   - `next_start(now)`: thời điểm mở lượt kế tiếp.
   - `reader_at(now) -> (reader | None, opened)`:
     - Vào lượt thì mở reader mới bằng `open_reader()` rồi `start()`.
     - Hết lượt thì `stop()`.
     - Chế độ liên tục chỉ mở một lần rồi giữ luôn.
   - `describe(now)`: trả `{"every_s", "for_s", "next_at"}`, hoặc `None` khi đếm liên tục.
2. **`server/milk/stream.py`:**
   - `LatestFrameReader.stop()` dừng luôn ffmpeg đang chạy, để hết lượt là ngắt ngay.
   - Khi chính worker ngắt luồng thì không ghi cảnh báo "stream unavailable".
3. **`server/milk/config.py`:**
   - `sample_every_s` đọc từ `MILK_SAMPLE_EVERY_S`, mặc định 0.
   - `sample_for_s` đọc từ `MILK_SAMPLE_FOR_S`, mặc định 30.
   - Khi `sample_every_s > 0` thì phải có `0 < sample_for_s < sample_every_s`. Sai thì báo lỗi ngay lúc đọc cấu
     hình.
4. **`server/milk/counter.py`:**
   - Dùng `Sampler` thay cho một reader chạy mãi.
   - Đầu mỗi lượt gọi `CountSmoother.reset()`, để số của lượt trước không lẫn vào lượt mới.
   - Ở chế độ theo nhịp, chỉ lưu (`/internal/persist`) khi lượt đã có đủ `MILK_SMOOTH_WINDOW` khung, để lần lưu
     đầu tiên đã được làm mượt. Chế độ liên tục giữ nguyên cách lưu cũ.
   - Ngoài lượt vẫn gửi `/internal/status` mỗi 2 giây, với `connected: false` và
     `sampling: {every_s, for_s, next_at}`. Nhờ vậy hub vẫn thấy worker còn sống.
5. **`server/milk/web/static/app.js` (dashboard của hub):** khi worker báo `sampling` mà đang không nối luồng:
   - Chip luồng hiện "Đếm theo nhịp · lượt kế tiếp HH:MM", màu bình thường, thay cho "Chưa có luồng từ camera"
     màu đỏ.
   - Chip tốc độ hiện "5 phút/lượt".
6. **`worker/README.md`:** thêm mục "Đếm theo nhịp", gồm hai biến, cách bật lại chế độ liên tục và hub hiện gì.

## Kiểm

- **Unit test (pytest):**
  - `Sampler`: trong và ngoài lượt, mốc kế tiếp, mỗi lượt mở và đóng reader đúng một lần, chế độ liên tục.
  - Cấu hình: giá trị mặc định, đọc biến, kết hợp sai thì báo lỗi.
  - `stop()` dừng ffmpeg ngay và không ghi cảnh báo.
  - Gói trạng thái gửi lúc ngoài lượt.
- **Chạy thật trên HUYHOANG** khoảng 20 phút, với 300/30:
  - Kết quả lên S3 thành cụm, 5 phút một cụm, có `model_version` và `detections`.
  - NetworkOut của hub và BytesUploaded của CloudFront giảm khoảng 90% so với lúc đếm liên tục.
  - Log không có lỗi.
  - Dashboard hub hiện "Đếm theo nhịp · lượt kế tiếp".

## Rủi ro

- **Mỗi lượt mất vài giây đầu để nối lại** (ffprobe, MediaMTX kéo camera, chờ keyframe), nên chỉ còn khoảng 20–25
  giây có khung. Lượt nào hụt thì lượt sau đếm bù. Ngoài lượt, `frames_last_minute` báo 0.
- **Nhịp thưa hơn trên các trang dùng số liệu.** Số capture mỗi giờ giảm từ vài trăm xuống khoảng 30–50. Trang
  Model và bộ chọn số chính thức mỗi giờ vẫn đủ dữ liệu.

## Để người làm tự quyết

Tên các hàm phụ, câu chữ trong log, và cách ngủ giữa hai lượt.
