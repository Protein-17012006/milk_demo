# Nhận ra sữa TH ở góc camera thật — kế hoạch làm

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Worker đếm mọi hộp TH 180ml lộ mặt trước hoặc nắp trên CAM-S01-A thành một dòng sản phẩm, và website hiện số đó.
Model sữa được dạy lại bằng ảnh thật của camera cộng với bộ ảnh tổng hợp của Long.

**Architecture:**
- **Laptop (có quyền AWS):** gom mọi frame về và chép sang HUYHOANG.
- **HUYHOANG (GPU):**
  - chia frame thành các đoạn theo cách xếp lốc;
  - Claude vẽ khung trên frame mẫu (keyframe) và lan nhãn sang cả đoạn;
  - tạo bộ dạy, train YOLO 11 lớp, dựng database v2, đo trên tập giữ riêng.
- **Repo:**
  - `long_adapter.py` tự quyết SKU và điểm, có cắt ô và tuỳ chọn gọi tên loại;
  - backend thêm alias `TMP-MLK-TH-00`;
  - website đổi quy tắc gắn nhãn sang B.

**Tech Stack:**
- Python 3.12, numpy, opencv-python-headless, pytest.
- ultralytics và các script của Long (`yolo\train.py`, `cctv_dataset`, `carton_recognition`) trên HUYHOANG.
- boto3 trên laptop.
- Next.js (frontend), AWS SAM/CloudFormation (backend).

**Spec:** `docs/superpowers/specs/2026-11-25-th-store-view-design.md`

## Global Constraints

- **Đơn vị đếm:** một hộp TH 180ml lộ mặt trước hoặc nắp, đủ để người nhìn biết đó là hộp TH.
- **Nhãn gộp:** `TMP-MLK-TH-00`.
  - Tên: `TH true MILK Sữa Tươi Tiệt Trùng 180ml (Có đường + Ít đường)`.
  - Tên tiếng Anh: `TH true MILK Fresh Milk 180ml (Sweetened + Low Sugar)`.
- **Lớp YOLO mới (11, theo đúng thứ tự):** `th_true_milk, vinamilk_banana, vinamilk_soy, vinamilk_fresh_less_sugar,
  vinamilk_chocolate, vinamilk_fresh_no_sugar, vinamilk_fresh_sweetened, vinamilk_soy_black_sesame,
  vinamilk_soy_almond, vinamilk_melon, vinamilk_9_seeds`. Lớp cũ 0 và 1 (hai loại TH) thành 0. Lớp cũ k (2–11)
  thành k−1.
- **Biến môi trường:**
  - `MILK_LONG_TILE`: mặc định 0, nghĩa là chỉ chạy cả khung như hiện nay. CAM-S01-A đặt 1280.
  - `MILK_LONG_VARIANTS`: mặc định 0. CAM-S01-A để 0.
  - `VARIANT_SHARE = 0.7`.
- **Tập giữ riêng:** frame chụp từ `2026-11-25T00:00+07:00` trở đi, cho tới lúc train, cộng frame từ
  `2026-11-23T18:00+07:00` đến `2026-11-23T21:00+07:00`.
  - Không bao giờ vào train, val, database, hay bước chỉnh ngưỡng.
  - Chia train/val theo đoạn, không chia theo frame.
- **Cổng:**

  | Chỉ số | Ngưỡng |
  |---|---|
  | recall | ≥ 0,85 |
  | precision (mọi SKU sữa, trừ `UNRECOGNIZED`) | ≥ 0,90 |
  | frame có TH đếm lệch ≤ 1 | ≥ 80% |
  | box sữa trên frame âm | ≤ 1 / 100 frame |
  | mAP50 từng lớp Vinamilk trên val tổng hợp | giảm ≤ 0,02 so với `best_types.pt` trên cùng ảnh |
  | số Slide | giống hệt bản đang chạy |

- **Không ghi đè file worker đang dùng.** Tên mới: `yolo\best_store_v1.pt`, `carton_recognition_v2\`,
  `MILK_MODEL_VERSION=long-store-v1+slide-v3`.
- **Trên Windows:** `import torch` trước cv2, ssl và lancedb.
- **Ảnh và nhãn của tiệm** không vào repo và không vào OneDrive.
  - Laptop: `C:\Users\huyho\milk_store_frames\`.
  - HUYHOANG: `C:\Users\huyho\Datagent\store_frames\`, `store_labels\`, `store_dataset_v1\`, `store_eval\`.
- **Change set:** stack `milk-backend-development` không dùng `--tags`; stack `milk-demo-base` dùng
  `--tags project=milk-demo`.
- **Mọi bước lên live** (backend, website, worker, shelf plan, xoá dòng tồn kho) chờ hoang OK.
- **Quay lui:** code mới chạy với `best_types.pt` và `MILK_LONG_TILE=0` phải ra đúng nhãn và điểm như `read_units` của
  Long.
- **Lệnh trên HUYHOANG:** cmd.exe từ chối lệnh dài hơn 8191 ký tự. Script dài thì scp file `.ps1` sang rồi chạy
  `powershell -File`.
- **Commit** bằng danh tính noreply như các lần trước, cuối message có dòng Co-Authored-By.

## Review Focus

1. **Có người hoặc tay che lốc** ở một frame giữa đoạn: frame đó không được nhận khung của keyframe. Test ở Task 2.
2. **Frame không phải 2560×1440:**
   - ô và nhãn tính theo kích thước của chính frame đó;
   - frame khác kích thước keyframe thì bị bỏ khỏi bộ dạy.

   Test ở Task 4.
3. **Model cũ 12 lớp chạy qua adapter mới:** nhãn và điểm y như `read_units`. Test ở Task 5.
4. **Rò tập giữ riêng:** frame trong cửa sổ giữ riêng không bao giờ có trong danh sách train/val hay ảnh cắt nạp
   database. Test ở Task 4 và Task 6.
5. **Database trả "unknown":** box phải ra `UNRECOGNIZED`, không bao giờ thành `TMP-MLK-TH-00`. Box trên frame âm (chai
   trắng ban đêm) bị cổng đếm. Test ở Task 5 và Task 7.

---

### Task 1: Gom frame và giữ ảnh lâu hơn

**Files:**
- Create: `training/__init__.py`, `training/store_view/__init__.py` (rỗng), `training/store_view/harvest.py`
- Modify: `pytest.ini` (`pythonpath = server .`)
- Test: `tests/test_store_view_harvest.py`

**Interfaces:**
- Produces:
  - `frame_relpath(capture_id: str, capture_timestamp: str) -> str`, trả `"YYYY-MM-DD/<capture_id>.jpg"`. Ngày lấy
    theo giờ ICT, chính là 10 ký tự đầu của timestamp.
  - `rows_from_captures(items: list[dict]) -> list[dict]`
  - `rows_from_audits(items: list[dict], bucket: str) -> list[dict]`
  - `merge_rows(hub: list[dict], audits: list[dict]) -> list[dict]`
  - `manifest.jsonl` dưới `<out>/CAM-S01-A/`, mỗi dòng một frame: `capture_id`, `capture_timestamp`,
    `display_visible`, `display_score`, `bucket`, `image_key`, `boxes` (detections đã parse), `audit_ids` (list), `path`.

- [ ] **Step 1:** Viết test trong `tests/test_store_view_harvest.py`:
  - `test_frame_relpath_uses_the_ict_day`: `frame_relpath("CAP-S01-20261124-235959", "2026-11-24T23:59:59+07:00")`
    bằng `"2026-11-24/CAP-S01-20261124-235959.jpg"`.
  - `test_merge_keeps_one_row_per_capture_and_lists_its_audits`: hub có `CAP-A`, audit có `CAP-A` (`AUD-…`) và
    `CAP-A` (`TRN-…`). Kết quả là 1 dòng, `bucket` của hub, `audit_ids == ["AUD-…", "TRN-…"]`.
  - `test_an_audit_frame_whose_hub_copy_expired_is_kept`: audit có `CAP-B`, hub không có. Kết quả là 1 dòng,
    `bucket` là bucket analytics.
  - `test_captures_without_a_frame_are_left_out`: item không có `image_key` thì không ra dòng nào.
- [ ] **Step 2:** `py -3.12 -m pytest tests/test_store_view_harvest.py -q` (trong venv py3.12 của repo). Expected: FAIL
  vì chưa có module.
- [ ] **Step 3:** Viết các hàm trên và CLI
  `python -m training.store_view.harvest --camera CAM-S01-A --first 2026-11-22 --last 2026-11-25 --out C:\Users\huyho\milk_store_frames`.
  - Profile `default`, region `ap-southeast-1`.
  - Bảng `milk-backend-development-captures` và `milk-backend-development-audits`.
  - Ảnh audit nằm ở bucket `milk-backend-development-754361433393`.
  - Bỏ qua file đã tải. Ghi `manifest.jsonl` mới mỗi lần chạy.
- [ ] **Step 4:** Chạy lại test. Expected: PASS.
- [ ] **Step 5:** Chạy CLI thật. Expected:
  - khoảng 8.400 frame trở lên, nhiều hơn 8.358 vì có thêm frame chụp chiều 25/11;
  - số dòng manifest bằng số file trên đĩa.
- [ ] **Step 6:** Chép sang HUYHOANG `C:\Users\huyho\Datagent\store_frames\CAM-S01-A\`.
  - Mỗi ngày một file `tar`, `scp -l 50000` (khoảng 6 MB/s). Giải nén bằng `tar -xf` trên HUYHOANG.
  - Expected: số file trên HUYHOANG bằng trên laptop.
  - Trong lúc chép, xem hub còn nhận khung đều không: các capture mới vẫn về backend khoảng 6 cái/phút trong cửa sổ
    lấy mẫu.
- [ ] **Step 7:** Tăng thời gian giữ ảnh.
  - Change set cho `milk-demo-base`, chỉ đổi `RetentionDays=30`. Các tham số khác giữ giá trị cũ
    (`UsePreviousValue`), `--tags project=milk-demo`.
  - Xem trước change set: chỉ được có bucket dữ liệu ở dạng `Modify`, không có `Replacement`. Rồi mới execute.
  - Expected: `get-bucket-lifecycle-configuration` cho `expire-frames` 30 ngày.
- [ ] **Step 8:** Commit `harvest.py`, test và `pytest.ini`.

### Task 2: Chia đoạn theo cách xếp lốc

**Files:**
- Create: `training/store_view/segments.py`
- Test: `tests/test_store_view_segments.py`

**Interfaces:**
- Consumes: `manifest.jsonl` (Task 1).
- Produces:
  - `signature(image: np.ndarray, region: tuple[int, int, int, int]) -> np.ndarray`: cắt vùng `(x0, y0, x1, y1)`,
    chuyển xám, thu về 64×48, trừ trung bình, chia độ lệch chuẩn.
  - `similarity(a: np.ndarray, b: np.ndarray) -> float`: tương quan Pearson.
  - `split(rows: list[dict], sigs: list[np.ndarray], min_sim=0.8, max_gap_s=900, patience=3, min_len=3) -> list[dict]`.
  - `segments.json`, mỗi đoạn có:
    - `id`, `keyframe` (capture_id), `members` (capture_id), `first_ts`, `last_ts`;
    - `kind`, nhận giá trị `"day"`, `"negative"` hoặc `"transient"`;
    - `split`: `"holdout"` hoặc `"train"`. Task 4 tách val ra khỏi train.

- [ ] **Step 1:** Viết test với chữ ký nhân tạo (vector cố định cho từng "cảnh"):
  - `test_a_brief_occlusion_is_skipped_not_a_new_segment`: chuỗi A A A C A A với C khác A. Kết quả là 1 đoạn gồm 5
    frame A. C không thuộc đoạn nào.
  - `test_a_lasting_change_starts_a_new_segment`: A A A B B B B ra 2 đoạn.
  - `test_a_time_gap_splits`: hai cụm A cách nhau 20 phút ra 2 đoạn.
  - `test_keyframe_is_the_member_most_like_the_others`: keyframe là phần tử giống các phần tử khác nhất (medoid).
  - `test_short_segments_are_transient`: đoạn dưới `min_len` frame có `kind == "transient"`.
  - `test_frames_without_the_display_are_negative`: `display_visible is False` thì vào đoạn `"negative"`, không qua
    bước so chữ ký.
  - `test_holdout_window_marks_segments`: đoạn bắt đầu sau `2026-11-25T00:00+07:00` có `split == "holdout"`.
    Đoạn bắt đầu lúc 23/11 19:00 cũng vậy.
- [ ] **Step 2:** Chạy test. Expected: FAIL.
- [ ] **Step 3:** Viết `segments.py` theo luật sau.
  - Duyệt frame theo thời gian. Đoạn đang mở có frame neo là frame đầu tiên của đoạn.
  - Một frame không khớp neo (`similarity < min_sim`):
    - nếu một trong `patience` frame kế tiếp khớp lại neo, frame này là che khuất tạm thời và bị bỏ;
    - nếu không, mở đoạn mới tại frame này.
  - Khoảng cách thời gian lớn hơn `max_gap_s` cũng mở đoạn mới.
  - Đóng đoạn: chọn keyframe là medoid, rồi bỏ các thành viên có `similarity(keyframe) < min_sim`.
  - CLI: `python -m training.store_view.segments --frames <store_frames\CAM-S01-A> --region 760,0,1200,320 --out <store_labels\segments.json>`.
- [ ] **Step 4:** Chạy test. Expected: PASS.
- [ ] **Step 5:** Chạy trên HUYHOANG. Expected:
  - in ra số đoạn `day`/`negative`/`transient` cho cả train lẫn holdout;
  - có ít nhất một đoạn `day` ngày 23/11 (lốc đứng), 24/11 và 25/11 (lốc nằm).
- [ ] **Step 6:** Commit.

### Task 3: Vẽ khung keyframe

**Files:**
- Create: `training/store_view/labels.py`
- Test: `tests/test_store_view_labels.py`

**Interfaces:**
- Consumes: `segments.json` (Task 2).
- Produces:
  - `grid_boxes(quad: list[tuple[float, float]], rows: int, cols: int) -> list[list[int]]`: mỗi ô của tứ giác
    (trên-trái, trên-phải, dưới-phải, dưới-trái), nội suy song tuyến, ra khung `[x, y, w, h]` bao ô đó.
  - `to_yolo(boxes, w, h, cls=0) -> list[str]` và `from_yolo(lines, w, h) -> list[tuple[int, list[int]]]`.
  - `clip_box(box, w, h) -> list[int] | None`: trả None nếu khung rỗng sau khi cắt.
  - `zoom_view(image, region, scale=4, grid=20) -> np.ndarray`: vùng phóng to, có lưới và toạ độ khung gốc.
  - `draw(image, boxes) -> np.ndarray`.
  - `store_labels\keyframes.json`: `{capture_id: {"boxes": [[x, y, w, h], ...], "packs": [{"quad": [...], "rows": r, "cols": c}]}}`.
    `[]` nghĩa là keyframe không có hộp TH nào lộ ra.

- [ ] **Step 1:** Viết test:
  - `test_grid_boxes_of_an_upright_rectangle`: quad `(0,0),(40,0),(40,20),(0,20)`, 1 hàng 4 cột. Kết quả
    `[[0,0,10,20],[10,0,10,20],[20,0,10,20],[30,0,10,20]]`.
  - `test_grid_boxes_of_a_slanted_quad_cover_each_cell`: tứ giác nghiêng, 2×4. Mỗi khung chứa đủ 4 góc của ô.
  - `test_yolo_round_trip`.
  - `test_clip_box_drops_empty_and_trims_overhang`.
- [ ] **Step 2:** Chạy test. Expected: FAIL.
- [ ] **Step 3:** Viết `labels.py` và CLI:
  - `zoom` ghi ảnh lưới của mọi keyframe đoạn `day` vào `store_labels\zoom\`;
  - `review` ghi tấm ảnh tổng hợp keyframe kèm khung vào `store_labels\review\`;
  - `write` ghi file YOLO của mọi thành viên đoạn: đoạn `day` nhận khung của keyframe, đoạn `negative` nhận file rỗng.
- [ ] **Step 4:** Chạy test. Expected: PASS.
- [ ] **Step 5:** Claude vẽ khung cho mọi keyframe `day`, cả train lẫn holdout.
  - Luật: một khung cho mỗi hộp TH 180ml lộ mặt trước hoặc nắp, đủ để biết đó là hộp TH; khung bao phần nhìn thấy.
  - Lốc thì ghi `quad`, `rows`, `cols`, cộng khung lẻ nếu cần. Lưu vào `keyframes.json`.
- [ ] **Step 6:** Chạy `review`. Claude soát từng tấm và sửa chỗ lệch.
  - Expected: mỗi hộp nhìn thấy có đúng một khung; không khung nào nằm trên hũ kẹo, tay hay nền.
  - Gửi đường dẫn tấm ảnh tổng hợp cho hoang xem, không chờ trả lời.
- [ ] **Step 7:** Chạy `write`. Expected: số file nhãn bằng tổng số thành viên đoạn `day` và `negative`.
- [ ] **Step 8:** Commit code. Nhãn để trên HUYHOANG, không commit.

### Task 4: Bộ dạy (ảnh thật cắt ô + ảnh tổng hợp)

**Files:**
- Create: `training/store_view/dataset.py`
- Test: `tests/test_store_view_dataset.py`

**Interfaces:**
- Consumes: `segments.json`, các file nhãn (Task 3), ảnh tổng hợp ở `cctv_dataset\dataset_hard_store` (sinh ở Step 5).
- Produces:
  - `NAMES: list[str]`: 11 lớp ở Global Constraints.
  - `remap_synthetic(old: int) -> int`.
  - `windows(w: int, h: int, size=1280, overlap=0.3) -> list[tuple[int, int, int, int]]`: cùng luật với `tiles()` của
    Long.
  - `clip_to_window(boxes, window, min_inside=0.6) -> list[list[float]]`: toạ độ trong ô; bỏ khung còn dưới 60% diện
    tích nằm trong ô.
  - `val_segments(segment_ids: list[str], share=0.1) -> set[str]`: chọn theo hash ổn định của id.
  - `C:\Users\huyho\Datagent\store_dataset_v1\` gồm `images/{train,val}`, `labels/{train,val}`, `data.yaml` (11 tên),
    `val_L1.txt` … `val_L5.txt` (từ val tổng hợp, để `train.py` chấm được), `README.txt` (số ảnh mỗi phần).

- [ ] **Step 1:** Viết test:
  - `test_windows_cover_a_2560x1440_frame`: mọi điểm của frame thuộc ít nhất một ô.
  - `test_clip_keeps_70_percent_inside_and_drops_50`.
  - `test_remap_merges_the_two_th_classes`: `remap_synthetic(0) == remap_synthetic(1) == 0` và `remap_synthetic(11) == 10`.
  - `test_holdout_segments_never_reach_train_or_val`.
  - `test_val_is_chosen_by_segment`: mọi thành viên của một đoạn cùng nằm một phía.
  - `test_frames_of_another_size_than_their_keyframe_are_skipped`.
- [ ] **Step 2:** Chạy test. Expected: FAIL.
- [ ] **Step 3:** Viết `dataset.py` và CLI `build`.
  - **Mỗi đoạn train hay val:**
    - lấy tối đa 60 frame, rải đều theo thời gian;
    - với mỗi frame: mọi ô có hộp TH, cộng 1 ô ngẫu nhiên không có hộp TH, seed cố định.
  - **Mỗi đoạn `negative`:** tối đa 60 frame, mỗi frame 1 ô ngẫu nhiên. Phải có ô chứa vùng gầm tủ đông ban đêm
    `(850, 40, 1050, 220)`.
  - **Ảnh tổng hợp:** chép sang, đổi lớp bằng `remap_synthetic`.
- [ ] **Step 4:** Chạy test. Expected: PASS.
- [ ] **Step 5:** Sinh ảnh tổng hợp trên HUYHOANG.
  - `cctv_dataset\build_hard_dataset.py --out dataset_hard_store --per-background 60`, khoảng 24k ảnh.
  - Rồi `make_type_labels.py` cho thư mục đó. Nếu thiếu quyền symlink thì chạy PowerShell quyền admin hoặc sửa bản sao
    script để chép thay vì liên kết.
  - Expected: có `images/` và `labels/` với số file khớp nhau.
- [ ] **Step 6:** Chạy `build`. Expected: `README.txt` ghi số ảnh thật train, thật val, âm và tổng hợp; mỗi phần lớn hơn
  0; không ảnh nào thuộc đoạn holdout.
- [ ] **Step 7:** Commit code.

### Task 5: Adapter tự quyết SKU, cắt ô, tuỳ chọn gọi tên loại

**Files:**
- Create: `server/milk/catalog.py`, chuyển `product_names()` từ `slide_adapter.py` sang; `slide_adapter` import lại hàm
  này để test cũ vẫn chạy.
- Modify:
  - `server/milk/long_adapter.py`;
  - `server/milk/skus.json`: thêm `TMP-MLK-TH-00`; tên TH-02 bỏ phần "(tên chờ khớp…)", ghi chú đó chuyển sang `note`.
- Test: `tests/test_long_adapter.py`

**Interfaces:**
- Produces:
  - `LABEL_OF_CLASS: dict[str, str]`, 13 mục: `th_true_milk → TMP-MLK-TH-00`, cộng 12 mục theo `SKUS` của Long
    (`th_true_milk_sweetened → TMP-MLK-TH-01`, …, `vinamilk_9_seeds → TMP-MLK-VNM-10`).
  - `VARIANT_SHARE = 0.7`.
  - `decide(cls_name: str, yolo_conf: float, brand: str, kind_share: Mapping[str, float], variants: bool) -> tuple[str | None, float]`.
  - `LongPipeline.detect(image) -> list[Detection]`: dùng `detect(..., tile=MILK_LONG_TILE)` của Long,
    `cv_output.one_box_per_unit`, `rec.lookup`, `cv_output.type_support`, rồi `decide`. Tên sản phẩm lấy từ
    `catalog.product_names()`.
- Luật của `decide`:
  - `brand == "unknown"` → `(None, 0.0)`.
  - `cls_name == "th_true_milk"`:
    - độ ủng hộ = tổng `kind_share` của các kind bắt đầu bằng `th_true_milk`;
    - nhãn `TMP-MLK-TH-00`;
    - nếu `variants` và một kind loại TH chiếm từ `VARIANT_SHARE` trở lên của phần TH thì dùng nhãn của kind đó.
  - Lớp khác:
    - độ ủng hộ = `kind_share.get(cls_name, 0.0)`;
    - nhãn `LABEL_OF_CLASS[cls_name]`. Đúng như `read_units`, kể cả khi brand của database khác brand của lớp.
  - Điểm = `yolo_conf × độ ủng hộ`.

- [ ] **Step 1:** Viết test:
  - `test_unknown_to_the_database_is_unrecognized`: mọi lớp, kể cả `th_true_milk`, ra `(None, 0.0)`.
  - `test_old_classes_score_like_read_units`: `("vinamilk_soy", 0.8, "vinamilk", {"vinamilk_soy": 0.5, "vinamilk_melon": 0.5}, False)`
    ra `("TMP-MLK-VNM-07", 0.4)`. `("th_true_milk_sweetened", 0.9, "vinamilk", {"vinamilk_soy": 1.0}, False)` ra
    `("TMP-MLK-TH-01", 0.0)`.
  - `test_brand_level_th_adds_up_every_th_kind`: `("th_true_milk", 0.8, "th_true_milk", {"th_true_milk": 0.5, "th_true_milk_less_sugar": 0.25, "vinamilk_soy": 0.25}, False)`
    ra `("TMP-MLK-TH-00", 0.6)`.
  - `test_variants_named_only_when_one_kind_clearly_leads`:
    - với variants bật, `{"th_true_milk_sweetened": 0.8, "th_true_milk_less_sugar": 0.2}` ra `TMP-MLK-TH-01`;
    - `{… 0.5, … 0.5}` ra `TMP-MLK-TH-00`;
    - variants tắt luôn ra `TMP-MLK-TH-00`.
  - `test_every_label_has_a_product_name`: mọi giá trị trong `LABEL_OF_CLASS` có trong `skus.json`.
  - `test_worker_names_match_the_backend_alias_names`: với 12 nhãn `TMP-MLK-*` cũ, tên trong `skus.json` bằng
    `sku_name_vi` trong `backend/common.DEFAULT_ALIAS_MAP`.
  - `test_tile_and_variants_settings`: không có biến môi trường thì `tile == 0`, `variants is False`.
    `MILK_LONG_TILE=1280` và `MILK_LONG_VARIANTS=1` thì đổi tương ứng. Đọc qua một hàm `_settings()` thuần.
- [ ] **Step 2:** Chạy test. Expected: FAIL.
- [ ] **Step 3:** Viết code.
  - `_settings() -> tuple[int, bool]` đọc biến môi trường.
  - `LongPipeline` vẫn import code của Long một cách lười (lazy) như hiện nay.
  - `read_units`/`to_detections` chỉ giữ nếu repo còn chỗ gọi (`grep -rn read_units server worker scripts`).
- [ ] **Step 4:** Chạy test, rồi chạy cả bộ `py -3.12 -m pytest -q` và `ruff check .`. Expected: PASS.
- [ ] **Step 5:** Kiểm trên HUYHOANG (script trong scratchpad, không commit). Trên 20 frame thật, `best_types.pt`,
  `MILK_LONG_TILE=0`: so `LongPipeline.detect` mới với `read_units` của Long. Expected: cùng box, cùng nhãn, điểm lệch
  dưới 0,001.
- [ ] **Step 6:** Commit.

### Task 6: Train detector và dựng database v2

**Files:**
- Create: `training/store_view/build_db.py`
- Test: `tests/test_store_view_build_db.py`

**Interfaces:**
- Consumes: bộ dạy (Task 4), nhãn và đoạn (Task 2, Task 3).
- Produces:
  - `crop_jobs(segments: list[dict], labels_dir: Path, split: str, per_segment=40) -> list[tuple[str, list[int]]]`:
    danh sách (capture_id, khung). Từ chối đoạn holdout.
  - `pick_threshold(pos: list[float], neg: list[float], keep=0.98) -> float`: giá trị lớn nhất mà vẫn giữ được ít nhất
    `keep` phần ảnh dương.
  - `yolo\best_store_v1.pt` và `carton_recognition_v2\` (`db_types`, `config_types.json` mới).

- [ ] **Step 1:** Viết test:
  - `test_crop_jobs_refuse_holdout`.
  - `test_pick_threshold_keeps_98_percent_of_positives`: dương `[0.90..0.99]`, âm `[0.5..0.85]`, ra một giá trị nằm
    giữa 0,85 và 0,90.
  - `test_pick_threshold_with_overlap_still_keeps_positives`.
- [ ] **Step 2:** Chạy test. Expected: FAIL.
- [ ] **Step 3:** Viết `build_db.py`. CLI:
  - `crops`: ghi ảnh cắt TH của đoạn train vào `store_labels\crops\th\` và ảnh âm vào `store_labels\crops\none\`.
  - `threshold`: đo độ giống của ảnh cắt val (dương và âm) với database v2 bằng `Recognizer(strict=False)`, rồi ghi
    `min_similarity` vào `carton_recognition_v2\config_types.json`.
- [ ] **Step 4:** Chạy test. Expected: PASS.
- [ ] **Step 5:** Train trên HUYHOANG:

  ```
  python yolo\train.py --dataset C:\Users\huyho\Datagent\store_dataset_v1 --tag store_v1 --model best_types.pt --hours 6 --name cartons_store_v1 --batch 12
  ```

  Dùng `--batch 8` nếu thiếu bộ nhớ. Theo dõi `nvidia-smi` và số capture/phút của worker.
  Expected: có `yolo\best_store_v1.pt` và `results_store_v1.json`.
- [ ] **Step 6:** Dựng database v2.
  1. `robocopy carton_recognition carton_recognition_v2 /E /XD .venv __pycache__`.
  2. `enroll.py --brand th_true_milk --kind th_true_milk store_labels\crops\th`.
  3. Ảnh âm lấy từ box của `best_store_v1.pt` trên frame âm và ngoài khung TH của đoạn train. Nạp bằng
     `enroll.py --brand none store_labels\crops\none`.
  4. `build_db.py threshold`.

  Expected: ảnh cắt TH val được nhận ít nhất 98%.
- [ ] **Step 7:** Commit code.

### Task 7: Đo và cổng

**Files:**
- Create: `training/store_view/evaluate.py`
- Test: `tests/test_store_view_evaluate.py`

**Interfaces:**
- Consumes: `LongPipeline` (Task 5), nhãn holdout (Task 3), model và database (Task 6).
- Produces:
  - `match(model: list[tuple[list[int], float]], truth: list[list[int]]) -> tuple[int, int, int]` (tp, fp, fn):
    khớp khi tâm box nằm trong khung thật, một đối một, box tự tin hơn khớp trước.
  - `summarize(frames: list[dict]) -> dict`: recall, precision, `count_within_1` (trên frame có TH), `negatives_per_100`.
    Tính theo frame và theo đoạn.
  - `GATE = {"recall": 0.85, "precision": 0.90, "count_within_1": 0.80, "negatives_per_100": 1.0}`.
  - `gate(summary: dict) -> list[str]`: danh sách chỉ số trượt, rỗng là qua.
  - `C:\Users\huyho\Datagent\store_eval\long-store-v1.json`.

- [ ] **Step 1:** Viết test:
  - `test_centre_inside_matches`.
  - `test_one_truth_box_matches_one_model_box`: hai box trên một hộp thì 1 tp, 1 fp.
  - `test_precision_counts_every_milk_label_but_unrecognized`: `UNRECOGNIZED` không tính, `TMP-MLK-VNM-03` tính.
  - `test_boxes_on_negative_frames_are_counted_per_100`.
  - `test_segment_view_gives_each_segment_one_vote`.
  - `test_gate_lists_failures`.
- [ ] **Step 2:** Chạy test. Expected: FAIL.
- [ ] **Step 3:** Viết `evaluate.py`. CLI chạy trên HUYHOANG:
  - nạp `load_pipeline("long+slide")` với biến môi trường của bản mới, sau đó với bản đang chạy;
  - chạy trên frame holdout, mỗi đoạn tối đa 30 frame;
  - so số Slide giữa hai bản;
  - ghi JSON.

  Kiểm Vinamilk:
  - chạy `best_types.pt` trên val tổng hợp với nhãn gốc 12 lớp;
  - chạy `best_store_v1.pt` trên cùng ảnh với nhãn 11 lớp;
  - so mAP50 từng lớp Vinamilk.
- [ ] **Step 4:** Chạy test. Expected: PASS.
- [ ] **Step 5:** Chạy đo trên HUYHOANG. Expected:
  - in bảng chỉ số theo frame và theo đoạn;
  - in danh sách trượt cổng, hoặc dòng "gate passed";
  - in so sánh Slide và Vinamilk.
- [ ] **Step 6:** Nếu trượt, lặp lại Task 3–6 theo spec mục 5.4: thêm keyframe, train lại embedder, sửa luật gộp nếu
  box Slide đè mất hộp TH. Mỗi vòng ghi số vào báo cáo và gửi hoang bản tóm tắt.
- [ ] **Step 7:** Commit code.

### Task 8: Backend, ảnh sản phẩm và quy tắc gắn nhãn B

**Files:**
- Modify:
  - `backend/common.py` (`DEFAULT_ALIAS_MAP`);
  - `backend/api/handler.py` (dòng 1388–1391, 1404, 1492, 1630);
  - `frontend/lib/audit-labeling.ts`;
  - `frontend/components/model/AuditLabeler.tsx` (dòng 257–259);
  - `frontend/components/model/ModelQualityView.tsx` (dòng 126–127, 199–200);
  - `frontend/lib/api.ts` (chú thích dòng 310, 421, 666).
- Create: `frontend/public/images/products/th-true-milk-fresh-milk-180ml.png`, hai mặt hộp TH sẵn có đặt cạnh nhau,
  cùng cỡ với các ảnh sản phẩm khác.
- Test: `tests/test_product_images.py` (không đổi, tự phủ alias mới), `tests/test_backend_integration_moto.py`,
  `frontend/lib/audit-labeling.test.ts`, `tests/test_long_adapter.py`.

**Interfaces:**
- Produces:
  - alias `TMP-MLK-TH-00`: brand `TH true MILK`, manufacturer `TH Group`, `Milk / Fresh Milk`, `Box`, `180 ml`,
    `image_url` `/images/products/th-true-milk-fresh-milk-180ml.png`;
  - `LABEL_RULE = "B"` (backend) và `CURRENT_LABEL_RULE = "B"` (frontend).
  - Nội dung quy tắc B: "**Rule B** — count every unit of the store's shelf plan (can, carton, pack) whose face, lid or
    top shows enough to tell the product. Mark **Out of scope**: units almost fully hidden, units whose product you
    can't tell."

- [ ] **Step 1:** Sửa test:
  - các assert `"A"` trong `test_backend_integration_moto.py` (dòng 608, 640, 666, 1616) thành `"B"`, và frame
    `label_rule="A"` nay được tính là frame cũ;
  - test relabel ở `audit-labeling.test.ts` cũng vậy;
  - thêm `test_worker_and_backend_name_the_merged_th_row_alike` vào `tests/test_long_adapter.py`: tên trong
    `skus.json` của `TMP-MLK-TH-00` bằng `sku_name_vi` của alias.
- [ ] **Step 2:** Chạy `py -3.12 -m pytest -q` và `cd frontend && npm test`. Expected: các test vừa sửa FAIL.
- [ ] **Step 3:** Sửa code và ảnh theo Interfaces. Đổi tên `_before_rule_a` thành `_before_current_rule`.
- [ ] **Step 4:** Chạy lại cả hai bộ test, `ruff check .`, `cd frontend && npm run build`. Expected: PASS và build xong.
- [ ] **Step 5:** Commit.

### Task 9: PR và lên live (chờ hoang OK)

- [ ] **Step 1:**
  - Push nhánh `feat/th-store-view` và mở PR vào `main`. Body có số đo của Task 7 và kèm spec.
  - Sửa body bằng `gh api -X PATCH …` nếu `gh pr edit` lỗi.
  - Expected: CI xanh.
- [ ] **Step 2:** Báo hoang các số đo, danh sách việc sẽ làm trên live và cách quay lui. Chờ hoang OK.
- [ ] **Step 3:** Backend.
  - Change set code cho API và ingest, không dùng `--tags`. Soát trước: không có `Replacement`.
  - `put_item` một dòng `sku_master` cho `TMP-MLK-TH-00`, có `image_url`.
  - Expected: `GET /products` trả được tên mới khi đã có dữ liệu.
- [ ] **Step 4:** Website. Build từ một worktree sạch của commit PR, deploy Amplify theo memory `frontend-deploy`.
  Expected: job SUCCEED, trang Model hiện quy tắc B.
- [ ] **Step 5:** Worker và shelf plan, làm liền nhau.
  1. Đưa commit PR sang bản clone repo trên HUYHOANG bằng git bundle.
  2. Sao lưu `worker.env` thành `worker.env.bak-<ngày>`.
  3. Đặt `MILK_LONG_DIR=C:/Users/huyho/Datagent/carton_recognition_v2`,
     `MILK_LONG_YOLO=C:/Users/huyho/Datagent/yolo/best_store_v1.pt`, `MILK_LONG_TILE=1280`, `MILK_LONG_VARIANTS=0`,
     `MILK_MODEL_VERSION=long-store-v1+slide-v3`.
  4. Stop rồi Start task `milk-worker`.
  5. Lưu shelf plan DEMO-S01 qua API (tài khoản team_admin): 4 Slide cộng dòng gộp.
  6. Xoá hai dòng `latest_stock` TH-01 và TH-02 của DEMO-S01.

  Expected:
  - trong 10 phút, có capture mới mang box `TMP-MLK-TH-00`;
  - Products hiện dòng TH gộp có số hộp;
  - sau lần tick kế tiếp, Dashboard thôi báo TH hết hàng.
- [ ] **Step 6:** Kiểm bằng trình duyệt như các lần trước: Products, Dashboard, trang Model.
  Expected: số TH khớp với capture mới nhất.
- [ ] **Step 7:** Ghi chép.
  - Cập nhật `TRAINING.md` trên HUYHOANG, thêm mục quy trình góc camera thật. Sao lưu trước bằng `.bak-<ngày>`.
  - Ghi nhật ký vào trang HOANG-P10.
  - Cập nhật memory.
  - Nhắc team gắn nhãn lại các frame AUD theo quy tắc B.

### Task 10 (tuỳ chọn, sau khi qua cổng): train lần cuối trên toàn bộ

- [ ] **Step 1:** `dataset.py build --no-holdout` (thêm cờ này kèm một test) tạo `store_dataset_v1_all`, gồm cả đoạn
  holdout.
- [ ] **Step 2:** Train `--tag store_v1_all`. Nạp lại database v2 với ảnh cắt của mọi đoạn.
- [ ] **Step 3:** Kiểm frame âm và val tổng hợp như Task 7, vì không còn tập giữ riêng.
- [ ] **Step 4:** Đổi worker sang bản này, theo các bước của Task 9 Step 5, với `MILK_MODEL_VERSION=long-store-v1all+slide-v3`.
  Chờ hoang OK.
