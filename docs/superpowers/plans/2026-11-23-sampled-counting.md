# Kế hoạch: đếm theo nhịp

> **Cho agent thực hiện:** làm theo superpowers:executing-plans, từng task theo TDD. Các bước đánh dấu bằng `- [ ]`.

**Mục tiêu:** worker chỉ đọc luồng camera trong lượt 30 giây mỗi 5 phút, nhờ đó giảm khoảng 90% tiền dữ liệu của
luồng hub.

**Cách làm:**
- Lớp `Sampler` quyết định lúc nào mở và đóng `LatestFrameReader`.
- `counter.main` dùng `Sampler` thay cho một reader chạy mãi.
- Dashboard của hub hiện trạng thái "đếm theo nhịp".

**Công nghệ:** Python 3.12, pytest, ffmpeg, JavaScript thuần (dashboard hub).

**Spec:** `docs/superpowers/specs/2026-11-23-sampled-counting-design.md`

## Ràng buộc chung

- `MILK_SAMPLE_EVERY_S=0` (mặc định) phải giữ nguyên hành vi hiện nay: đếm liên tục, cách lưu và cách gửi giống
  hệt.
- Trên HUYHOANG đặt `MILK_SAMPLE_EVERY_S=300` và `MILK_SAMPLE_FOR_S=30`.
- Không đổi cách đếm, model, backend hay website.
- Test chạy bằng Python 3.12 (`requirements-dev.txt`). `ruff check` và `ruff format --check` phải sạch.

## Điểm cần soi khi review

1. **Lượt kết thúc trong lúc `newer_than` đang chờ khung:** chờ tối đa 2 giây rồi phải đóng reader, không được
   treo.
2. **Không có khung nào trong cả lượt** (camera hoặc hub chậm): không lưu gì, không báo lỗi giả, lượt sau thử
   lại.
3. **Ngừng ngay khi hết lượt:** `stop()` gọi lúc ffmpeg đang chạy thì ffmpeg phải dừng ngay, và không có
   ffmpeg mồ côi.
4. **Dashboard hub ngoài lượt** không được báo đỏ "Chưa có luồng từ camera".
5. **Cấu hình sai** (`for_s >= every_s`, hoặc `for_s <= 0` khi `every_s > 0`) phải báo lỗi rõ ngay lúc khởi
   động.

---

### Task 1: Cấu hình

**File:** sửa `server/milk/config.py`, test ở `tests/test_config.py`.

**Cung cấp cho task sau:** `Settings.sample_every_s: float`, mặc định 0.0, và `Settings.sample_for_s: float`,
mặc định 30.0.

- [ ] **Test:**
  - `test_sampling_defaults_to_continuous`: không có biến nào thì `(0.0, 30.0)`.
  - `test_sampling_settings_from_env`: đặt 300 và 30 thì ra `(300.0, 30.0)`.
  - `test_sampling_window_must_fit_the_period`: các cặp (300, 300), (300, 0), (60, 90) đều `ValueError`.
- [ ] Chạy để thấy test hỏng, viết code, chạy lại để thấy test qua, rồi commit.

### Task 2: `Sampler`

**File:** tạo `server/milk/sampling.py`, test ở `tests/test_sampling.py`.

**Cung cấp cho task sau:**
- `Sampler(every_s: float, for_s: float, open_reader: Callable[[], Reader])`.
- `continuous: bool`.
- `in_window(now) -> bool`.
- `next_start(now) -> float`.
- `reader_at(now) -> tuple[Reader | None, bool]`.
- `describe(now) -> dict | None`.
- `close() -> None`.

Trong đó `Reader` cần có `start()` và `stop()`.

- [ ] **Test**, dùng reader giả có ghi lại các lần gọi start và stop:
  - `in_window`: lúc 600 và 629 thì đúng; lúc 630 và 899 thì sai (với 300/30).
  - `next_start(630) == 900` và `next_start(600) == 900`.
  - `reader_at`:
    - Vào lượt thì mở đúng một reader, với `opened=True`.
    - Trong cùng lượt thì trả lại reader đó, với `opened=False`.
    - Hết lượt thì gọi `stop()` một lần và trả `(None, False)`.
    - Sang lượt mới thì mở một reader mới.
  - Chế độ liên tục: lần đầu mở, sau đó luôn trả cùng reader, không bao giờ `stop()`. Còn `describe()` trả
    `None`.
  - `describe(630)`: `{"every_s": 300, "for_s": 30, "next_at": 900}`.
  - `close()` dừng reader đang mở.
- [ ] Chạy để thấy test hỏng, viết code, chạy lại để thấy test qua, rồi commit.

### Task 3: `LatestFrameReader.stop()` dừng ngay

**File:** sửa `server/milk/stream.py`, test ở `tests/test_stream.py`.

- [ ] **Test:** `test_stop_ends_ffmpeg_at_once_without_a_warning`.
  - Dùng Popen giả: stdout chặn cho tới khi `kill()` được gọi.
  - Chạy `run()` trong thread, gọi `stop()`.
  - Kiểm: thread kết thúc trong vòng 2 giây, `kill()` đã được gọi, và không có log WARNING.
- [ ] Chạy để thấy test hỏng, viết code, chạy lại để thấy test qua, rồi commit.

### Task 4: `counter.main` dùng `Sampler`

**File:** sửa `server/milk/counter.py`, test ở `tests/test_counter_helpers.py`, sửa `worker/README.md`.

**Dùng từ task trước:** `Sampler` (Task 2), các trường cấu hình (Task 1), `stop()` (Task 3).

- [ ] **Test:** hàm thuần `status_payload(...)`:
  - Ngoài lượt: `connected` là False, `stream` là `{}`, có `sampling.next_at`.
  - Trong lượt: lấy từ reader. Khi đếm liên tục thì không có khoá `sampling`.
- [ ] **Code:**
  - Vòng lặp chính lấy reader từ `sampler.reader_at(now)`.
  - Mở lượt thì `smoother.reset()`, đặt `last_seq = 0` và `last_smoothed = None`.
  - Ngoài lượt thì gửi status mỗi 2 giây, rồi ngủ tới đầu lượt sau (tối đa 1 giây mỗi lần).
  - Ở chế độ theo nhịp, chỉ lưu khi lượt đã có đủ `smooth_window` khung.
- [ ] README thêm mục "Đếm theo nhịp".
- [ ] Chạy cả bộ test, ruff, rồi commit.

### Task 5: Dashboard hub

**File:** sửa `server/milk/web/static/app.js`.

- [ ] **Code:** trong `renderStatus` và `statusLoop`, nếu `worker.sampling` có mà `!worker.connected`:
  - Chip luồng: "Đếm theo nhịp · lượt kế tiếp HH:MM", tone `ok`.
  - Chip tốc độ: "N phút/lượt".
  - Không đè bằng "Chưa có luồng từ camera".
- [ ] **Phát hành hub:** `infra/release.ps1`. Sau đó kiểm trên hub: `/healthz` có phiên bản mới, và `/api/status`
  vẫn trả đúng.
- [ ] Commit.

### Task 6: Triển khai trên HUYHOANG và đo

- [ ] Kéo nhánh về HUYHOANG.
- [ ] Thêm `MILK_SAMPLE_EVERY_S=300` và `MILK_SAMPLE_FOR_S=30` vào `worker.env` (không in file ra).
- [ ] Khởi động lại task `milk-worker`.
- [ ] **Theo dõi khoảng 20 phút:**
  - Log: mỗi 5 phút một lượt, không có lỗi.
  - S3: kết quả thành cụm, có `model_version` và `detections`.
  - Hub: chip "Đếm theo nhịp".
  - CloudWatch: NetworkOut của hub và BytesUploaded của CloudFront mỗi giờ, so với trước khi đổi.
- [ ] Mở PR, ghi Nhật ký HOANG-P10, cập nhật bộ nhớ.
