# Vòng vận hành, phần 2: vòng nhanh (kho ảnh) — kế hoạch làm

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nhãn người làm trên website (frame dạy, frame review, frame so sánh) vào một kho ảnh mỗi đêm. Kho đặt tên cho box Slide trong worker, nhưng chỉ khi phép đo trên box của detector cho thấy kho gọi tên đúng hơn. Kho mới lên live qua cửa của phần 1.

**Architecture:** Luật đọc của kho chuyển từ `training/store_view/slide_gallery.py` sang `server/milk/gallery.py` (`GalleryNamer`), để phép đo, worker và job đêm dùng chung một đoạn code. Phép đo lấy box đã chấm trên frame chấm điểm (`AUD-`) làm đáp án: đó chính là box của detector live, có người chấm. Mỗi ngày được đọc bằng một kho dựng từ các ngày còn lại. Worker đặt tên bằng kho mà bản live trỏ tới (`MILK_SLIDE_GALLERY`). Bản ứng viên chỉ khác kho thì không nạp detector, mà đặt tên lại box thô của bản live. Job đêm `milk-gallery` trên HUYHOANG dựng kho mới, đo, rồi tạo một bản chạy `kind gallery` cho cửa của phần 1.

**Tech Stack:** Python 3.12. numpy và OpenCV có sẵn trong `.venv` của worker. boto3 trong `.venv-ops`. pytest, moto. PowerShell cho scheduled task.

**Spec:** `docs/superpowers/specs/2026-11-27-operations-loop-design.md`, mục 5.3, câu về ứng viên chỉ khác kho ở mục 5.2, và dòng "Vòng nhanh" ở mục 5.7. Luật đọc gốc lấy từ `2026-11-25-slide-fusion-gallery-design.md` mục 5.1. hoang duyệt spec ngày 27/11. Ngày 28/11 hoang bảo viết plan này: *"Làm: viết plan phần 2"* (chỉ viết plan; build khi plan được duyệt).

## Những điều Claude tự quyết trong kế hoạch này

- **Đáp án của phép đo là box đã chấm trên frame `AUD-`.** Box trên frame chấm điểm là box detector live vẽ, và người đã chấm từng cái, nên đây đúng là "đo trên box của detector". Frame `AUD-` chỉ được đọc để đo; nó không bao giờ vào kho, đúng luật ở mục 3 của spec. Số của luật đọc (10 láng giềng, 60%, 3 phiếu, 20 lon) giữ nguyên, không chỉnh theo kết quả.
- **"Ngày kho chưa thấy" là giấu từng ngày.** Ngày của một capture lấy từ capture id (`CAP-S01-YYYYMMDD-…`, giờ Việt Nam). Mỗi ngày có frame `AUD-` đã chấm được đọc bằng một kho dựng từ nhãn của các ngày khác.
- **Quy tắc bật, chốt trước khi đo.** Kho được bật cho một nhóm hàng khi đủ ba điều:
  - số box kho sửa đúng lớn hơn số box kho làm sai;
  - phép thử nhị thức hai phía trên hai số đó cho p < 0,05 (cùng phép thử với cửa ở phần 1);
  - không sản phẩm nào có ít nhất 10 box mà tỉ lệ gọi đúng tụt quá 5 điểm.
- **Nhóm sữa được đo bằng cùng công cụ, nhưng chưa dựng DINOv2.** Ở CAM-S01-A, người chỉ gán cho hộp sữa một tên TH gộp (spec 5.3 cũng nói kho sữa chưa có gì để đổi tên). Nếu kho của một nhóm có dưới hai tên sản phẩm đủ 20 lon, công cụ ghi "không đổi tên được: kho biết N tên" và không bật kho cho nhóm đó. Cách "DINOv2-small cộng màu" mà spec đặt làm điểm xuất phát cho hộp sữa sẽ làm khi tiệm bày thêm một loại hộp khác.
- **Luật đọc trong worker** là `read()` hiện có, thêm luật 3 của thiết kế Slide: nếu tên của detector có dưới 20 lon trong kho thì kho không đọc box đó. Nhờ vậy kho không bao giờ đụng tới box sữa, và code không phải liệt kê sản phẩm. Kho không bỏ box nào, và nhãn `none` không bao giờ thành tên. Luật 4 của thiết kế Slide (bỏ box) đã bị spec 5.3 thay.
- **Dấu "không chắc":** box mà kho đã đọc nhưng không chắc, hoặc không cắt ra được, mang `"unsure": true` trong bản ghi capture. Phần 3 sẽ dùng dấu này để chọn frame.
- **Ứng viên chỉ khác kho:** điều kiện là `release.json` của nó chỉ khác bản live ở `MILK_SLIDE_GALLERY`. Khi đó nó không nạp detector, mà đặt tên lại box thô (trước bước kho) của bản live trên cùng frame.
- **Job đêm là một scheduled task riêng, `milk-gallery`, chạy lúc 23:20** (sau khi hub tắt lúc 23:00). Bước gọi AWS chạy trong `.venv-ops`. Bước dựng kho và đo chạy trong `.venv` của worker (numpy, OpenCV) như một tiến trình con. Không cài gì thêm.
- **Kho được lưu ở** `C:\Users\huyho\Datagent\slide_gallery\slide_gallery_<camera>_<YYYYMMDD-HHMM>.npz`, thư mục mà thiết kế Slide đã định. File không bao giờ bị ghi đè, vì các bản chạy trỏ tới nó.
- **Lần Put live của kho đầu tiên là thay đổi model thật,** nên hoang bấm, hoặc nói rõ cho Claude bấm. Theo lời hoang ngày 27/11, tài khoản test chỉ bấm cho các bản ứng viên thử.

**Không nằm trong kế hoạch này:**
- Các câu trên website ("nhãn của bạn đã vào…", "chỉ có tác dụng ở vòng chậm"): thuộc phần 3 (mục 5.4).
- Chọn frame dạy theo dấu "không chắc": thuộc phần 3.
- Gộp frame trong cửa sổ: thuộc thiết kế common-read-path.
- DINOv2 trong worker: làm khi có loại hộp sữa thứ hai.

## Global Constraints

- Kho chỉ nhận nhãn của người: câu trả lời trên frame `TRN-`, `REV-`, `CMP-`, và đáp án vẽ tay của các đoạn phía train. Không bao giờ nhận: capture nào có audit `AUD-`, frame trong `segments.HOLDOUT`, nhãn tự động, ảnh render.
- Kho không bỏ box nào. Kho không đổi tên box sang một tên nó có dưới 20 lon. `none` không bao giờ thành tên.
- Không đặt `MILK_SLIDE_GALLERY` thì worker đọc y hệt hiện nay: cùng box, cùng tên, cùng điểm, và không có khoá `unsure`.
- Kho của bản live đọc không được thì worker dừng, kèm tên file. Kho của ứng viên đọc không được thì ứng viên dừng, còn live vẫn chạy.
- Mỗi camera chỉ một ứng viên. Job đêm không tạo bản chạy khi đang có ứng viên hoặc một yêu cầu còn chạy.
- Luật đọc: 10 láng giềng, 60% trọng số, 3 phiếu, 20 lon.
- Quy tắc bật: sửa đúng nhiều hơn làm sai, p < 0,05 hai phía, và không sản phẩm nào có ≥ 10 box tụt quá 5 điểm.
- Tiêu chí chạy song song của bản chỉ đổi kho: `kind gallery` trong `release.DEFAULT_CRITERIA` (1 ngày, 30 box khác nhau đã chấm, p < 0,05, không sản phẩm nào kém quá 5 điểm). Không đổi.
- Không cài gì vào `.venv` của worker. `ops` chạy trong `.venv-ops`, chỉ có boto3.
- Ảnh tiệm, nhãn và kho không vào repo, cũng không vào OneDrive.
- Python 3.12. Chạy `python -m pytest -q`, rồi `ruff check .` và `ruff format --check .`.
- Commit bằng danh tính noreply: `git -c user.name="Nguyen Huy Hoang" -c user.email=193206418+Protein-17012006@users.noreply.github.com commit …`. Không push khi hoang chưa bảo.
- Mỗi lần lên live phải chờ hoang OK. Khởi động lại worker vào giây thứ 40–100 của chu kỳ 300 giây.

## Review Focus

1. **Một capture vừa có audit `AUD-` vừa có audit `TRN-`:** nó không bao giờ vào kho. Test ở Task 2.
2. **Box sát mép ảnh hoặc quá nhỏ để cắt:** box vẫn giữ tên của detector, được đánh dấu `unsure`, không bị bỏ. Test ở Task 1.
3. **Ranh giới ngày:** nhãn lúc 23:59 giờ Việt Nam thuộc đúng ngày đó, không bị đẩy sang ngày UTC. Test ở Task 2 (`day_of`).
4. **Frame `AUD-` có box gộp (lúc có ứng viên):** chỉ chấm box mà bản live có vẽ. Box `?` lấy tên `live_sku`, box chỉ ứng viên vẽ thì bỏ qua. Test ở Task 3.
5. **Job đêm chạy khi đang có ứng viên, có yêu cầu còn chạy, hoặc không có nhãn mới:** job không tạo gì và ghi lý do. Test ở Task 7.

## File Structure

| File | Việc |
|---|---|
| `server/milk/gallery.py` (mới) | Đặc trưng màu, `Gallery`, `read`, `crop_of` (chuyển từ `slide_gallery.py`); `GalleryNamer`, `load_namer` |
| `server/milk/cvoutput.py` | `Detection.unsure`; `persist_record` ghi `"unsure": true` |
| `server/milk/counter.py`, `candidate.py`, `release.py` | Worker đặt tên bằng kho của bản live; ứng viên chỉ khác kho thì đặt tên lại box thô của live |
| `training/store_view/slide_gallery.py` | Lấy các hàm trên từ `milk.gallery`; nhận thêm frame `CMP-`; `exclude_days`; `built_from` |
| `training/store_view/gallery_measure.py` (mới) | Đo có kho và không có kho trên box `AUD-`, theo từng ngày bị giấu và từng nhóm hàng; quyết định bật |
| `ops/gallery_data.py` (mới, chỉ boto3) | Xuất audit đã xong và tải frame của chúng về HUYHOANG, kèm `manifest.jsonl` |
| `ops/gallery_nightly.py` (mới, chỉ boto3) | Job đêm: xuất dữ liệu, gọi bước dựng và đo trong `.venv`, rồi tạo bản chạy hoặc ghi vì sao không |
| `worker/windows/run-gallery.ps1`, `register-gallery-task.ps1` (mới) | Scheduled task `milk-gallery` lúc 23:20 |
| `training/store_view/cameras/CAM-S01-A.json` | Mỗi nhóm hàng thêm `skus` và `gallery.method` |
| `tests/test_gallery.py`, `test_gallery_measure.py`, `test_gallery_data.py`, `test_gallery_nightly.py` (mới); `test_slide_gallery.py`, `test_candidate.py`, `test_cvoutput.py`, `test_backend_integration_moto.py` | Test |

---

### Task 1: Luật đọc của kho thành code của worker

**Files:**
- Create: `server/milk/gallery.py`, `tests/test_gallery.py`
- Modify: `server/milk/cvoutput.py` (`Detection`), `training/store_view/slide_gallery.py` (import thay cho định nghĩa)

**Interfaces:**
- Produces:
  - Chuyển nguyên trạng từ `slide_gallery.py`: `MIN_IMAGES = 20`, `K = 10`, `MIN_SHARE = 0.6`, `MIN_VOTES = 3`, `colour(crop) -> np.ndarray`, `mean_colour`, `Gallery` (`save`, `load`, `counts`), `GalleryVote`, `read(gallery, feature, k=K) -> GalleryVote`, `crop_of(image, box) -> np.ndarray | None`. `slide_gallery.py` đặt `<repo>/server` vào `sys.path` như `evaluate.py` đang làm, rồi import lại các tên này, để mọi lệnh import cũ vẫn chạy.
  - `Detection.unsure: bool = False`, đặt làm trường cuối.
  - `class GalleryNamer(gallery: Gallery, product: Mapping[str, str], feature: Callable[[np.ndarray], np.ndarray] = colour)`. Hàm `name(image: np.ndarray, detections: list[Detection]) -> list[Detection]` trả về cùng số box, cùng thứ tự, cùng box và điểm. Chỉ tên (`sku_id`, `sku_name = product.get(sku, sku)`) hoặc `unsure` thay đổi.
  - `GALLERY_KEY = "MILK_SLIDE_GALLERY"`. Hàm `load_namer(env: Mapping[str, str]) -> GalleryNamer | None` trả `None` khi chưa đặt biến hoặc biến rỗng. Đặt biến mà file không có thì raise `FileNotFoundError`, kèm đường dẫn.

- [ ] **Step 1: Viết các test hỏng.** Kho thử có 25 lon `cheese145` (đặc trưng `e1`), 25 lon `original145` (`e2`) và 25 lon `none` (`e3`). Các vector đều là one-hot 144 chiều, `objects` khác nhau. Hàm `feature` giả trả về `e1`, `e2` hoặc `e3` tuỳ màu trung bình của phần cắt.

```python
def test_a_sure_gallery_renames_a_box_and_keeps_its_place_and_score():
    ...
    # cheese145 trên vùng e2 -> original145, cùng box, cùng confidence, unsure False


def test_an_unsure_read_keeps_the_detector_name_and_marks_the_box():
    ...
    # đặc trưng (e1+e2)/sqrt2 -> giữ cheese145, unsure True


def test_a_name_with_fewer_than_20_cans_in_the_gallery_is_not_read():
    ...
    # hot160 (0 lon) và TMP-MLK-TH-00 trên vùng e2 -> không đổi, unsure False


def test_none_never_becomes_a_name_and_no_box_is_dropped():
    ...
    # cheese145 trên vùng e3 -> vẫn cheese145, unsure True; len(out) == len(in)


def test_a_box_too_small_to_crop_is_kept_and_marked_unsure():
    ...
    # box rộng 2 px ở mép -> giữ tên, unsure True


def test_load_namer_is_none_without_the_key_and_names_the_missing_file(tmp_path): ...
```

- [ ] **Step 2: Chạy test.** Lệnh: `python -m pytest -q tests/test_gallery.py`. Kết quả cần thấy: FAIL với `ModuleNotFoundError: milk.gallery`.
- [ ] **Step 3: Viết code.** Chuyển các tên từ `slide_gallery.py`. Thêm `Detection.unsure`. Viết `GalleryNamer.name`:
  - box có `gallery.counts().get(sku, 0) < MIN_IMAGES` thì giữ nguyên;
  - không cắt được thì `unsure`;
  - `read` trả tên thì đổi sang tên đó, còn không thì `unsure`.
- [ ] **Step 4: Chạy lại.** Lệnh: `python -m pytest -q tests/test_gallery.py tests/test_slide_gallery.py tests/test_cvoutput.py`. Kết quả cần thấy: PASS. Mọi test cũ của `slide_gallery` vẫn qua mà không sửa gì.
- [ ] **Step 5: Commit** `Worker: the gallery's read rule lives in milk.gallery and names boxes without ever dropping one`

### Task 2: Dữ liệu cho kho: mọi nguồn spec cho phép

**Files:**
- Create: `ops/gallery_data.py`, `tests/test_gallery_data.py`
- Modify: `training/store_view/slide_gallery.py`, `tests/test_slide_gallery.py`, `training/store_view/cameras/CAM-S01-A.json`

**Interfaces:**
- Consumes: `Gallery` (Task 1).
- Produces:
  - `LABEL_PREFIXES = ("TRN-", "REV-", "CMP-")`. Hàm `trn_rows(audits, prefixes=("TRN-", "REV-"))` giữ nguyên mặc định cho phần auto-label; kho gọi nó với `LABEL_PREFIXES`.
  - `day_of(capture_id: str) -> str` trả `"YYYY-MM-DD"`, đọc từ id.
  - `build(..., exclude_days: frozenset[str] = frozenset(), skus: frozenset[str] | None = None, region: tuple[int, int, int, int] | None = None)`:
    - bỏ keyframe đáp án và hàng nhãn của các ngày trong `exclude_days`;
    - khi có `skus`, chỉ giữ nhãn thuộc `skus`, cộng các nhãn `none` có tâm box nằm trong `region`. Mỗi nhóm hàng có kho riêng, nên một hộp sữa không bao giờ bị đọc bằng ảnh của lon Slide.
  - `Gallery.built_from: tuple[str, ...]` là các audit id và keyframe đã vào kho, đã sắp xếp. Được lưu trong npz. File cũ không có khoá này thì đọc ra `()`.
  - `ops/gallery_data.py`:
    - `export(table, s3, bucket, camera, out_dir: Path) -> dict` ghi `out_dir/audits.json`, gồm mọi audit `done` của camera có tiền tố `TRN-`, `REV-`, `CMP-`, `AUD-`. Mỗi audit giữ các trường `audit_id`, `status`, `capture_id`, `capture_timestamp`, `ai_boxes_json`, `verdicts_json`, `image_key`, `candidate_version`.
    - Nó tải các frame còn thiếu từ `image_key` trong bucket analytics về `out_dir/frames/<camera>/<YYYY-MM-DD>/<capture_id>.jpg`.
    - Nó ghi `out_dir/frames/<camera>/manifest.jsonl` theo dạng của `harvest.py`, mỗi capture một dòng: `capture_id`, `capture_timestamp`, `audit_ids`.
    - Trả về số đếm: audit theo tiền tố, frame mới tải, frame đã có.
  - Trong `CAM-S01-A.json`, nhóm `slide` thêm `"skus"` (bốn vị) và `"gallery": {"method": "colour"}`. Nhóm `th` thêm `"skus": ["TMP-MLK-TH-00"]` và `"gallery": {"method": "dinov2+colour"}`.

- [ ] **Step 1: Viết các test hỏng.**

```python
def test_cmp_frames_are_people_labels_and_a_disputed_box_takes_the_name_people_chose(): ...
def test_a_capture_with_an_aud_audit_never_enters_even_with_a_trn_audit(tmp_path): ...  # Review Focus 1
def test_day_of_reads_the_store_day_from_the_capture_id():
    assert day_of("CAP-S01-20261127-235959-3") == "2026-11-27"  # Review Focus 3


def test_build_leaves_out_the_excluded_days_and_records_what_it_was_built_from(tmp_path): ...
def test_a_group_gallery_keeps_its_own_names_and_only_the_none_crops_inside_its_region(tmp_path): ...
def test_export_writes_audits_frames_and_a_manifest_that_marks_scoring_frames(tmp_path): ...  # moto: S3 + DynamoDB
```

- [ ] **Step 2: Chạy test.** Lệnh: `python -m pytest -q tests/test_slide_gallery.py tests/test_gallery_data.py`. Kết quả cần thấy: FAIL vì các tên mới chưa có.
- [ ] **Step 3: Viết code.**
  - `gallery_data` dùng `scan` có lọc, như `_export_trn` hiện nay. Tải frame bằng `s3.download_file`, và bỏ qua file đã có.
  - Manifest được ghi lại từ đầu mỗi lần.
- [ ] **Step 4: Chạy lại.** Lệnh như Step 2. Kết quả cần thấy: PASS. Thêm `python -m pytest -q tests/test_auto_label_run.py` để chắc `trn_rows` mặc định không đổi.
- [ ] **Step 5: Commit** `Gallery data: labels of training, review and comparison frames, by store day, never a scoring frame`

### Task 3: Phép đo có kho và không có kho trên box của detector

**Files:**
- Create: `training/store_view/gallery_measure.py`, `tests/test_gallery_measure.py`

**Interfaces:**
- Consumes: `GalleryNamer`, `Gallery` (Task 1); `build`, `day_of`, `LABEL_PREFIXES` (Task 2).
- Produces:
  - `ScoredBox(capture_id: str, day: str, box: tuple[int,int,int,int], live: str, truth: str)` (frozen dataclass).
  - `scored_boxes(audits: list[dict]) -> list[ScoredBox]` lấy từ các audit `AUD-` đã `done`:
    - chỉ lấy câu trả lời `correct` hoặc `wrong_sku`;
    - tên live là `box["live_sku"]` khi box có `src`, còn không thì là `box["sku_id"]`;
    - bỏ box `src == "cand"` và box không có tên live;
    - đáp án là tên live khi câu trả lời là `correct`, là `true_sku_id` khi là `wrong_sku`.
  - `GroupResult` (dataclass) gồm:
    - `group`, `n`, `right_without`, `right_with`, `fixed`, `broken`, `unsure`;
    - `per_sku: dict[str, tuple[int, int, int]]`: đáp án → (n, đúng khi không có kho, đúng khi có kho);
    - `names: int`: số tên sản phẩm có ≥ 20 lon, nhỏ nhất trong các kho đã dựng;
    - `days: list[str]`.
  - `measure(boxes: list[ScoredBox], gallery_for_day: Callable[[str], Gallery], image_of: Callable[[str], np.ndarray | None], skus: set[str], product: Mapping[str, str]) -> GroupResult`. Chỉ chấm box có tên live nằm trong `skus` của nhóm. Mỗi box được đọc bằng `GalleryNamer(gallery_for_day(box.day), product).name(image, [Detection(...)])`.
  - `binomial_two_sided(k: int, n: int) -> float`: cùng công thức với `backend/compare.binomial_two_sided`. Có test so hai hàm. Định nghĩa lại tại chỗ vì `compare.py` kéo theo `model_health`.
  - `decide(r: GroupResult) -> tuple[bool, list[str]]` theo quy tắc bật ở phần Global Constraints. Khi `r.names < 2`, nó trả `(False, ["cannot rename: the gallery knows N product names"])`.
  - Lệnh chạy `python -m training.store_view.gallery_measure --audits A --truth T --segments S --frames F --camera-config C --out O.json`:
    - với mỗi nhóm hàng trong cấu hình camera và mỗi ngày bị giấu, dựng một kho riêng (`skus` và `region` của nhóm, `exclude_days={day}`, `exclude_holdout=True`);
    - đo từng nhóm, ghi `O.json` và in một bảng.

- [ ] **Step 1: Viết các test hỏng.**

```python
def test_scored_boxes_use_the_live_name_and_skip_boxes_only_the_candidate_drew(): ...  # Review Focus 4
def test_measure_counts_fixed_broken_and_unsure_against_people_answers(): ...
def test_each_day_is_read_with_a_gallery_built_without_it(): ...  # gallery_for_day nhận đúng ngày của box
def test_decide_needs_more_fixed_than_broken_and_p_below_005():
    assert decide(result(fixed=12, broken=2))[0] is True
    assert decide(result(fixed=5, broken=3))[0] is False  # p ≈ 0,73


def test_decide_refuses_when_a_product_with_ten_boxes_falls_more_than_five_points(): ...
def test_decide_refuses_a_gallery_that_knows_fewer_than_two_names(): ...
def test_binomial_matches_the_parallel_run_test(): ...  # so với backend/compare.binomial_two_sided
```

- [ ] **Step 2: Chạy test.** Lệnh: `python -m pytest -q tests/test_gallery_measure.py`. Kết quả cần thấy: FAIL, module chưa có.
- [ ] **Step 3: Viết code.** Ảnh frame được đọc bằng `cv2.imread`, mỗi frame một lần. Kho của mỗi ngày được dựng một lần.
- [ ] **Step 4: Chạy lại.** Lệnh như Step 2, rồi cả bộ: `python -m pytest -q`. Kết quả cần thấy: PASS.
- [ ] **Step 5: Commit** `Gallery measure: with and without the gallery on the live detector's judged boxes, each day read by a gallery that never saw it`

### Task 4: Đo trên HUYHOANG và báo hoang (điểm dừng)

Không viết code mới. Đây là phép đo spec gọi là "việc đầu tiên của phần này".

- [ ] **Step 1: Đưa code lên HUYHOANG.** Dùng git bundle vào clone, như ở phần 1. Worker không khởi động lại: Task 1–3 không đổi đường chạy của worker.
- [ ] **Step 2: Xuất dữ liệu.** Trong `.venv-ops`, với profile `milk`, chạy `python -m ops.gallery_data --root C:\Users\huyho\Datagent\gallery --camera CAM-S01-A`. Kết quả cần thấy: số audit theo tiền tố, và mọi frame `AUD-` cùng frame nhãn đã nằm trên đĩa. Nếu profile `milk` không đọc được `audits/frames/` trong bucket analytics thì dừng và báo hoang. Spec mục 3 ghi rằng quyền của profile này chưa được xem hết.
- [ ] **Step 3: Đo.** Chạy `C:\Users\huyho\Datagent\.venv\Scripts\python.exe -m training.store_view.gallery_measure`, với:
  - đáp án `C:\Users\huyho\Datagent\store_labels\slide\truth.json`;
  - các đoạn `C:\Users\huyho\Datagent\store_labels\segments.json`;
  - frame trong `gallery\frames\CAM-S01-A`;
  - ghi kết quả ra `C:\Users\huyho\Datagent\store_eval\gallery_measure_<YYYYMMDD>.json`.

  Kết quả cần thấy: một bảng cho mỗi nhóm hàng gồm n, đúng khi không có kho, đúng khi có kho, sửa đúng, làm sai, không chắc, từng vị, p, quyết định.
- [ ] **Step 4: Ghi số vào ledger và báo hoang** cả hai cách, cho từng nhóm. Nhóm sữa có thể ra "không đổi tên được". **Nếu không nhóm nào đạt thì phần 2 dừng ở đây** (spec 5.7: "có số đo…"). Khi đó, nhãn của người chỉ có tác dụng ở vòng chậm. Task 5–8 không làm, và câu tương ứng trên website thuộc phần 3.

**Kết quả ngày 28/11 (Task 4):** Slide: 608 box đã chấm, 23–28/11. Gọi đúng 570 khi không có kho, 559 khi có kho; kho sửa đúng 29, làm sai 40, p = 0,228. Original 83 → 91/111, Hot 48 → 51/53, Cheese 171 → 156/173, Sour Cream 268 → 261/271. Không bật. TH: 109 box, không đổi tên được (kho biết 0 tên). Không bật. Phần 2 dừng ở đây; Task 5–8 chưa làm.

### Task 5: Worker đặt tên bằng kho của bản live

**Files:**
- Modify: `server/milk/counter.py` (quanh `pipeline.detect(crop)`, dòng ~242), `server/milk/cvoutput.py` (`persist_record`)
- Test: `tests/test_counter_loop.py`, `tests/test_cvoutput.py`, `tests/test_backend_integration_moto.py`

**Interfaces:**
- Consumes: `load_namer`, `GalleryNamer.name` (Task 1).
- Produces:
  - Trong vòng lặp: `raw = pipeline.detect(crop)`, rồi `named = namer.name(crop, raw) if namer else raw`, rồi `detections = normalise(named, x0, y0)`.
  - `namer = load_namer(os.environ)` được gọi một lần lúc khởi động. Lúc này môi trường đã là của bản live, vì có `config.use_live_release`.
  - Hàm `candidate.hold` nhận thêm `raw` (Task 6 dùng).
  - `persist_record` ghi `"unsure": true` chỉ cho box có `unsure`.

**Mang theo từ Task 1–4 (ghi ngày 28/11):**
- `counter.normalise` dựng lại `Detection` theo vị trí (counter.py:53) nên làm mất `unsure`; phải giữ `unsure` qua bước đó.
- `load_namer` chỉ nêu tên file khi file không có; file npz hỏng cũng phải làm worker dừng và nêu tên file. Test cả hai trường hợp.
- `read()` gọi `gallery.counts()` cho mỗi box; trong vòng lặp của worker phải tính một lần cho mỗi kho.

- [ ] **Step 1: Viết các test hỏng.**

```python
def test_without_a_gallery_the_record_is_exactly_as_before(): ...  # không có khoá "unsure", cùng tên
def test_the_live_gallery_renames_slide_boxes_and_marks_unsure_ones(): ...  # pipeline giả + kho thử
def test_a_live_gallery_that_cannot_be_read_stops_the_worker_naming_the_file(): ...
def test_ingest_keeps_the_unsure_mark_in_detections_json(): ...  # moto, _ingest
```

- [ ] **Step 2: Chạy test.** Lệnh: `python -m pytest -q tests/test_counter_loop.py tests/test_cvoutput.py tests/test_backend_integration_moto.py -k "gallery or unsure or exactly_as_before"`. Kết quả cần thấy: FAIL.
- [ ] **Step 3: Viết code** đúng như phần Interfaces ở trên.
- [ ] **Step 4: Chạy lại cả bộ:** `python -m pytest -q`. Kết quả cần thấy: PASS.
- [ ] **Step 5: Commit** `Worker: the live release's gallery names Slide boxes; unsure ones are marked in the capture`

### Task 6: Ứng viên chỉ khác kho dùng lại box của detector live

**Files:**
- Modify: `server/milk/release.py`, `server/milk/candidate.py`, `server/milk/counter.py` (lệnh gọi `hold`)
- Test: `tests/test_release.py`, `tests/test_candidate.py`

**Interfaces:**
- Consumes: `load_namer` (Task 1), `raw` truyền vào `hold` (Task 5).
- Produces:
  - `release.GALLERY_KEYS = ("MILK_SLIDE_GALLERY",)`. Hàm `release.gallery_only(live: Release, candidate: Release) -> bool` trả True khi hai bộ biến chỉ khác ở `GALLERY_KEYS`.
  - `CandidateRunner(pipeline: Pipeline | None, version, status_path, clock=..., load_times=None, namer: GalleryNamer | None = None)`:
    - `pipeline is None` nghĩa là ứng viên chỉ khác kho. Khi đó `flush` dùng `namer.name(crop, raw)`;
    - nếu không thì `flush` dùng `namer.name(crop, pipeline.detect(crop))` khi có namer, hoặc `pipeline.detect(crop)` khi không.
  - `hold(capture_id, capture_timestamp, camera_id, crop, offset, raw: list[Detection] | None = None)`.
  - `load_candidate` so bản ứng viên với bản live trong `live.json`. Khi `gallery_only` đúng, nó không nạp pipeline.
  - Ô kết quả của ứng viên mang `"unsure": true` theo đúng cách của `persist_record`.

- [ ] **Step 1: Viết các test hỏng.**

```python
def test_gallery_only_is_true_only_when_nothing_but_the_gallery_differs(): ...
def test_a_gallery_only_candidate_loads_no_detector_and_renames_the_live_raw_boxes(tmp_path): ...
def test_a_candidate_whose_gallery_cannot_be_read_is_stopped_and_live_goes_on(tmp_path): ...
def test_a_candidate_with_its_own_detector_still_runs_its_pipeline_then_its_gallery(tmp_path): ...
```

- [ ] **Step 2: Chạy test.** Lệnh: `python -m pytest -q tests/test_release.py tests/test_candidate.py`. Kết quả cần thấy: FAIL.
- [ ] **Step 3: Viết code.** Ứng viên giữ tối đa `MAX_HELD` frame, nên khi giữ thêm `raw` thì bộ nhớ chỉ tăng thêm danh sách box.
- [ ] **Step 4: Chạy lại cả bộ.** Kết quả cần thấy: PASS.
- [ ] **Step 5: Commit** `Candidate: a release that differs only in its gallery re-reads the live detector's boxes instead of loading a detector`

### Task 7: Job đêm: kho mới, đo nhanh, rồi cửa của phần 1

**Files:**
- Create: `ops/gallery_nightly.py`, `worker/windows/run-gallery.ps1`, `worker/windows/register-gallery-task.ps1`, `tests/test_gallery_nightly.py`
- Modify: `training/store_view/gallery_measure.py` (thêm lệnh `nightly`), `worker/README.md`

**Interfaces:**
- Consumes: `gallery_data.export` (Task 2); `gallery_measure.measure` và `decide` (Task 3); `release.read_pointer`, `load_release`, `ops.make_release` (phần 1).
- Produces:
  - `gallery_measure nightly --audits A --truth T --segments S --frames F --camera-config C --running <npz|none> --out-dir D --result R.json`:
    - dựng kho ứng viên của nhóm `slide` từ mọi nhãn (`skus` và `region` của nhóm, `exclude_holdout=True`, không giấu ngày nào) và lưu vào `D/slide_gallery_<camera>_<YYYYMMDD-HHMM>.npz`;
    - đo cả kho ứng viên lẫn kho đang chạy bằng cách giấu từng ngày;
    - ghi `R.json` gồm `{"candidate_npz", "built_from", "same_as_running": bool, "candidate": GroupResult, "running": GroupResult | null, "not_worse": bool, "enable": bool, "reasons": [...]}`.
  - Kho ứng viên "không kém" kho đang chạy khi `right_with` không ít hơn, và không sản phẩm nào có ≥ 10 box tụt quá 5 điểm. Khi bản live chưa có kho thì thay điều này bằng `decide` (quy tắc bật).
  - `ops.gallery_nightly.next_action(pointer: Pointer, state: dict, result: dict) -> tuple[str, str]` là hàm thuần, trả `("propose", npz)` hoặc `("wait", lý do)`. Lý do là một trong các câu: `"a candidate is running"`, `"a request is in hand"`, `"nothing new since the running gallery"`, `"worse than the running gallery"`, `"the gallery does not pass: …"`.
  - `ops.gallery_nightly main --root R --camera C --store-code S`. Nó chạy `export`, gọi `.venv` bằng tiến trình con cho lệnh `nightly`, đọc `R.json`, gọi `next_action`. Khi được `propose`, nó gọi `make_release --kind gallery --from-release <live> --set MILK_SLIDE_GALLERY=<npz>`. Mọi bước được ghi vào `logs\gallery-<ngày>.log`.
  - Task `milk-gallery` chạy dưới SYSTEM, mỗi ngày lúc 23:20, bằng `.venv-ops` và profile `milk` (giống `register-ops-task.ps1`).

**Mang theo từ Task 1–4 (ghi ngày 28/11):**
- `export` ghi manifest sau khi tải frame xong, nên một lần chạy hỏng giữa chừng để lại manifest cũ. Job đêm phải dừng và không dựng gì khi `export` lỗi.
- `build()` chỉ dựa vào manifest để biết frame chấm điểm. Thêm vào tập loại trừ các capture có audit `AUD-` trong danh sách audit nó nhận, hoặc ghi manifest trước khi tải.
- Xuất thêm `model_version` của mỗi audit và báo các detector có trong mỗi nhóm (hoặc chỉ lấy box của detector Slide đang live), để phép đo sau một lần đổi detector không trộn hai detector.
- In ra các tên nhãn bị bộ lọc `skus` của nhóm bỏ qua: nếu không, một vị Slide mới sẽ không bao giờ vào kho mà không ai biết.
- `export` quét cả bảng audits: ổn với cỡ hiện nay, cần xem lại khi bảng lớn.

- [ ] **Step 1: Viết các test hỏng.**

```python
def test_next_action_waits_while_a_candidate_runs_or_a_request_is_in_hand(): ...  # Review Focus 5
def test_next_action_waits_when_nothing_is_new_or_the_gallery_is_worse(): ...
def test_next_action_proposes_the_first_gallery_only_when_it_passes_the_rule(): ...
def test_a_proposed_gallery_becomes_a_gallery_release_that_points_at_the_npz(tmp_path): ...
```

- [ ] **Step 2: Chạy test.** Lệnh: `python -m pytest -q tests/test_gallery_nightly.py`. Kết quả cần thấy: FAIL.
- [ ] **Step 3: Viết code.** Viết `next_action` trước. Phần gọi AWS và gọi tiến trình con được truyền vào như một tham số, để test không cần cả hai.
- [ ] **Step 4: Chạy lại cả bộ, rồi ruff.** Kết quả cần thấy: PASS và sạch.
- [ ] **Step 5: Commit** `Ops: a nightly job builds a gallery from new labels, measures it and offers it to the Model page`

### Task 8: Lên live, và kho đầu tiên đi qua cửa (cần hoang OK)

**Mang theo từ Task 1–4 (ghi ngày 28/11):**
- Trên HUYHOANG, worktree `C:\Users\huyho\Datagent\milk_demo_part2` đang giữ nhánh `feat/ops-loop-part2`: chạy `git worktree remove` trước khi checkout nhánh này trong clone live.
- Thư mục `C:\Users\huyho\Datagent\gallery` (audit và frame đã xuất ngày 28/11) dùng lại được cho job đêm.

- [ ] **Step 1: Xin hoang OK** với danh sách thay đổi:
  - code của worker (Task 1, 5, 6);
  - task mới `milk-gallery`;
  - bản kho đầu tiên sẽ chạy song song một ngày, người chấm các box có hai tên khác nhau, và hoang (hoặc Claude, nếu hoang nói) bấm Put live hoặc Discard.

  Không đổi backend, hub hay website. Ghi chú: test moto ở Task 5 đã cho thấy ingest giữ nguyên `unsure`.
- [ ] **Step 2: Cập nhật code của worker.** Đưa bundle vào clone trên HUYHOANG, tạo nhánh sao lưu, rồi khởi động lại `milk-worker` vào giây thứ 40–100 của chu kỳ. Kết quả cần thấy: các cửa sổ kế tiếp có số capture và số box như giờ trước, và không capture nào có `unsure` (bản live chưa có kho).
- [ ] **Step 3: Đăng ký `milk-gallery` và chạy job một lần bằng tay** ngoài giờ cửa sổ lấy mẫu. Kết quả cần thấy: `logs\gallery-<ngày>.log` ghi được `propose` hoặc `wait`, kèm lý do. Khi được `propose`, `ops.runner` đăng ký bản chạy `kind gallery` và chạy song song. `candidate-status` ghi rằng ứng viên không nạp detector, và bộ nhớ GPU của worker không tăng.
- [ ] **Step 4: Sau một ngày chạy song song** kiểm tra:
  - có frame `CMP-` hoặc box `?` trên frame `AUD-`;
  - `scan_keys.py` không thấy `src`, `live_sku`, `cand_sku`;
  - Dashboard không đổi;
  - kết luận trên trang Model.

  Người bấm Put live hoặc Discard theo kết luận. Ghi số vào ledger. Phần 2 xong (spec 5.7) khi kho của nhóm đạt đã đi qua cửa một lần.
- [ ] **Step 5: Ghi memory và ledger. Push và PR chỉ khi hoang bảo.**
