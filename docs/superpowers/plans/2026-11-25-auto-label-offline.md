# Auto-label phần 1: pipeline chạy ngoài live — kế hoạch triển khai

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Từ frame của một đoạn ban ngày, pipeline đề xuất box và vị cho mỗi lon. Mỗi lon được quyết định là chấp
nhận, cần người xem, hay bỏ. Pipeline ghi nhãn YOLO, có che xám vùng chưa rõ, và đo được cổng 1 trên đáp án.

**Architecture:**
- **Hai nguồn box:** A là Slide v3 (`SlidePipeline`, ngưỡng 0,05). B là YOLOE với box mẫu lấy từ keyframe của camera.
- **Kho ảnh màu** đọc vị trên từng box.
- **Gom cụm** box theo vị trí qua cả đoạn, rồi luật quyết định thuần chạy trên mỗi cụm.
- **Hai lệnh dòng lệnh:**
  - `propose` ghi kết quả theo đoạn;
  - `labels` ghi nhãn, sau khi áp quyết định của người.
- **Cổng 1** chấm trên các đoạn giữ riêng.

**Tech Stack:** Python 3.12, numpy, opencv, ultralytics (YOLOE trong `.venv-label`), pytest.

**Spec:** `docs/superpowers/specs/2026-11-25-auto-label-design.md` (hoang duyệt 25/11 khoảng 23:15).

Phần 2 (hàng chờ Review trên website) và phần 3 (train Slide v4, cổng 2) là kế hoạch riêng.

## Global Constraints

**Dữ liệu không bao giờ được dùng:**
- Frame có audit AUD: lọc bằng `training.store_view.dataset.read_scoring_frames(frames_dir)`.
- Đoạn giữ riêng (`segments.HOLDOUT`): không dùng để train, làm box mẫu hay đưa vào kho ảnh dùng để đo.
- `slide_pilot\test_frames`.

**Kho ảnh màu:**
- Chỉ nhận nhãn người: `truth.json` và verdict TRN. Không bao giờ nhận nhãn tự động.

**Hằng số từ spec:**

| Thứ | Giá trị |
|---|---|
| Vùng Slide của CAM-S01-A (x0, y0, x1, y1) | `880,120,1520,720` |
| Nguồn A | ngưỡng 0,05, `imgsz 2560` |
| Nguồn B | ảnh cắt vùng, `imgsz 640`, ngưỡng 0,3 |
| Ghép box | IoU ≥ 0,5 |
| Đặc trưng màu | phần giữa 70% cao × 60% rộng, gray-world, HSV H18×S8, căn bậc hai, chuẩn L2 (144 chiều) |
| Luật đọc vị | k = 10; một vị ≥ 0,6 tổng trọng số; ≥ 3/10 láng giềng; vị đó ≥ 20 ảnh trong kho |
| Có lon thật | A ≥ 30% và B ≥ 30% số frame; hoặc chỉ B ≥ 60% và kho không nói none |
| Box ma | < 30% số frame thì bỏ |
| Vị ổn định | ≥ 80% số frame |
| Cổng 1 | lon thật ≥ 0,99; đúng vị ≥ 0,98; phủ ≥ 0,95; đoạn cần review ≤ 0,40 |

**Môi trường và lưu trữ:**
- Không cài gì vào `C:\Users\huyho\Datagent\.venv` (Smart App Control).
- Code cần model chạy trong `C:\Users\huyho\Datagent\.venv-label`, mượn torch qua file `.pth`.
- Danh sách lớp lấy từ file cấu hình camera, không hardcode trong code.
- Ảnh tiệm, nhãn và kho ảnh không vào repo hay OneDrive.

**Test:**
- Chạy được không cần GPU và không cần model: `<venv312>\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/<file>`.
- Test cần model đặt `pytest.importorskip("ultralytics")`, và bỏ qua khi thiếu `MILK_AUTOLABEL_MODELS`.

**Nhánh:** `feat/auto-label`, tách từ `feat/th-store-view` (cần `segments.py`, `labels.py` và bản sửa AUD `1d89c26`).

## Review Focus

1. **Đoạn quá ngắn** (1–4 frame dùng được): tỉ lệ frame nhảy rất mạnh. Đoạn đó phải ghi là `too_short` và không quyết
   định gì. Test ở Task 4.
2. **Box A (chỉ thân lon) và box B (nắp + thân) của cùng một lon** có IoU dưới 0,5: phải gom thành một cụm. Hai lon đứng
   sát nhau thì không được gom. Test ở Task 3.
3. **Frame AUD nằm trong đoạn train:** không bao giờ được ghi nhãn, không vào kho ảnh. Frame TRN ngày giữ riêng không
   vào kho dùng để đo. Test ở Task 1 và Task 5.
4. **Một frame trong đoạn mà lon bị tay che:** frame đó không được ghi box trung vị lên tay; vùng đó phải che xám. Test
   ở Task 5.
5. **Vị có dưới 20 ảnh trong kho** (Hot hiện nay): A gọi Hot thì cụm phải vào review. Kho cũng không bao giờ bỏ phiếu
   cho vị đó. Test ở Task 1 và Task 4.

---

### Task 1: Kho ảnh màu (`slide_gallery.py`)

**Files:**
- Create: `training/store_view/slide_gallery.py`
- Test: `tests/test_slide_gallery.py`

**Interfaces:**
- Consumes:
  - `segments.holdout(ts)` và `segments.similarity` / `segments.signature`;
  - `dataset.read_scoring_frames(frames_dir)`.
- Produces:
  - `colour(crop: np.ndarray) -> np.ndarray`: vector 144 chiều.
  - `@dataclass Gallery`:
    - các trường `features: np.ndarray (n,144)`, `labels: np.ndarray[str]`, `sources: np.ndarray[str]`
      (capture_id), `built_at: str`, `none_threshold: float | None`;
    - các method `save(path)`, `classmethod load(path)`, `counts() -> dict[str,int]`.
  - `@dataclass(frozen=True) GalleryVote(sku: str | None, share: float, votes: int, none_hit: bool)`.
  - `read(gallery: Gallery, feature: np.ndarray, k: int = 10) -> GalleryVote`. `sku` là `None` khi luật đọc vị không
    đủ chắc.
  - `MIN_IMAGES = 20`.
  - `trn_rows(audits: list[dict]) -> list[tuple[str, list[int], str]]`: `(capture_id, box xywh, label)` cho audit TRN
    có status `done`:
    - `correct` → `sku_id` của box;
    - `wrong_sku` → `true_sku_id`;
    - `not_product` → `"none"`;
    - `out_of_scope` → bỏ.
  - CLI:
    - `python -m training.store_view.slide_gallery export-trn --out trn_done.json`: chạy trên laptop, đọc bảng
      `milk-backend-development-audits`;
    - `python -m training.store_view.slide_gallery build --truth T --segments S --frames F --trn trn_done.json
      --region 880,120,1520,720 [--exclude-holdout] --out G.npz`.

- [ ] **Step 1: Viết test**

```python
def test_colour_is_a_unit_144_vector_and_ignores_overall_brightness(): ...
    # crop ngẫu nhiên và crop * 0.6 cho cosine > 0.98 (nhờ gray-world); len 144; norm 1
def test_read_names_the_flavour_with_most_weight():
    # kho: 25 ảnh "cheese145" gần e1, 25 ảnh "original145" gần e2; read(e1) -> sku "cheese145", votes >= 3
def test_read_never_votes_for_a_flavour_with_fewer_than_20_images():
    # 12 ảnh "hot160" sát truy vấn + 30 ảnh "original145" xa hơn -> sku None (không phải "hot160")
def test_read_is_unsure_below_60_percent_weight():
    # 5 láng giềng "a" và 5 láng giềng "b", trọng số ngang nhau -> sku None
def test_none_hit_only_when_the_gallery_has_a_none_threshold():
    # none_threshold None -> none_hit False; none_threshold 0.9 và láng giềng gần nhất "none" có sim 0.95 -> True
def test_trn_rows_follow_the_verdicts():
    # correct -> nhãn model; wrong_sku -> true_sku_id; not_product -> "none"; out_of_scope bỏ; status pending bỏ;
    # audit_id AUD-... bỏ
def test_build_skips_scoring_frames_and_holdout_trn_when_asked(tmp_path):
    # manifest: C1 có AUD-, C2 TRN 24/11, C3 TRN 25/11; --exclude-holdout -> nguồn chỉ có C2
def test_save_and_load_round_trip(tmp_path): ...
```

- [ ] **Step 2:** Chạy `tests/test_slide_gallery.py`. Expected: FAIL (`ModuleNotFoundError`).
- [ ] **Step 3:** Viết `slide_gallery.py`.
  - `colour` giống hàm `colour()` của `slide_exp.py` (scratchpad 25/11):
    - phần cắt `[0.15h:0.85h, 0.2w:0.8w]`;
    - gray-world;
    - `cv2.calcHist` trên H, S với 18×8 ô;
    - lấy căn bậc hai, rồi chuẩn hoá L2.
  - `read`: 10 láng giềng theo cosine, mỗi láng giềng góp trọng số bằng độ giống của nó.
  - `build` từ `truth.json`:
    - chỉ keyframe của đoạn `split == "train"`;
    - mỗi box bỏ `kind == "ignore"`;
    - cắt ở tối đa 30 frame trải đều của đoạn, giữ frame có vùng box tương quan ≥ 0,85 với keyframe
      (`similarity(signature(...))`).
  - `build` từ `trn_done.json`: ảnh lấy theo `capture_id` trong `--frames`; thiếu ảnh thì bỏ và đếm.
  - Áp mọi loại trừ trong Global Constraints.
  - `none_threshold`: `None` khi kho có dưới 20 ảnh `none`. Khi đủ, người làm chọn ngưỡng trên phần val phía train và
    ghi vào `npz`.
- [ ] **Step 4:** Chạy test. Expected: PASS.
- [ ] **Step 5:** Commit `Auto-label: colour gallery of human-labelled Slide crops`.

### Task 2: Hai nguồn box (`proposers.py`) và môi trường `.venv-label`

**Files:**
- Create: `training/store_view/proposers.py`
- Test: `tests/test_proposers.py`

**Interfaces:**
- Consumes: `milk.slide_adapter.SlidePipeline`. Biến môi trường `MILK_SLIDE_WEIGHTS`, `MILK_SLIDE_CONF=0.05`,
  `MILK_SLIDE_IMGSZ=2560`.
- Produces:
  - `@dataclass(frozen=True) Proposal(source: str, box: tuple[float, float, float, float], conf: float, sku: str | None)`:
    - `source` là `"A"` hoặc `"B"`;
    - box là xywh theo pixel của frame.
  - `region_prompts(rows: list[dict], region: tuple[int,int,int,int]) -> np.ndarray`: box xyxy trong toạ độ ảnh cắt
    vùng. Bỏ `kind == "ignore"`.
  - `in_region(box, region) -> bool`: tâm box nằm trong vùng.
  - `union_nms(props: list[Proposal], iou: float = 0.5) -> list[Proposal]`: giữ box tự tin hơn.
  - `class Sources`:
    - `__init__(slide_weights: str, yoloe_weights: str, prompt_images: list[np.ndarray],
      prompt_boxes: list[np.ndarray], region)`;
    - `frame(image) -> list[Proposal]`: A cộng B, chỉ giữ box trong vùng. B là hợp các lần chạy theo từng keyframe mẫu,
      rồi `union_nms`.

- [ ] **Step 1: Viết test**

```python
def test_region_prompts_shift_boxes_into_the_crop():
    rows = [{"box": [900, 200, 70, 160], "kind": "face"}, {"box": [1, 1, 5, 5], "kind": "ignore"}]
    assert region_prompts(rows, (880, 120, 1520, 720)).tolist() == [[20, 80, 90, 240]]


def test_in_region_uses_the_box_centre(): ...
def test_union_nms_keeps_the_surer_of_two_overlapping_boxes(): ...
def test_sources_find_cans_on_a_store_frame():
    pytest.importorskip("ultralytics")
    # bỏ qua khi thiếu MILK_AUTOLABEL_MODELS; frame CAP-S01-20261124-112017-2 -> >= 6 Proposal "A" và >= 6 Proposal "B"
```

- [ ] **Step 2:** Chạy test. Expected: FAIL.
- [ ] **Step 3:** Viết `proposers.py`.
  - B gọi `YOLOE(w).predict(crop, refer_image=..., visual_prompts=dict(bboxes=..., cls=zeros),
    predictor=YOLOEVPSegPredictor, imgsz=640, conf=0.3)`, rồi cộng `region[:2]` để về toạ độ frame.
  - A dùng `SlidePipeline().detect(image)` và đổi mỗi `Detection` thành `Proposal("A", d.box, d.confidence, d.sku_id)`.
- [ ] **Step 4:** Tạo `.venv-label` trên HUYHOANG theo đúng cách đã làm với `.venv-sam3`:
  - `python -m venv`;
  - `pip install --no-deps ultralytics ultralytics-thop git+https://github.com/ultralytics/CLIP.git`;
  - `pip install matplotlib pyyaml requests scipy psutil polars ftfy regex wcwidth opencv-python-headless numpy pytest`;
  - tạo file `zz_borrow_worker_torch.pth` trỏ tới `.venv\Lib\site-packages`.
  
  Expected: `import torch` báo đường dẫn trong `.venv` và `cuda True`; `from ultralytics import YOLOE` chạy được.
- [ ] **Step 5:** Chạy test trên laptop. Expected: test model SKIP, còn lại PASS. Chạy cả file trên HUYHOANG với
  `MILK_AUTOLABEL_MODELS=1`. Expected: PASS.
- [ ] **Step 6:** Commit `Auto-label: two box sources, Slide v3 and YOLOE visual prompts`.

### Task 3: Gom box thành cụm theo đoạn (`auto_label.py`, phần 1)

**Files:**
- Create: `training/store_view/auto_label.py`
- Test: `tests/test_auto_label.py`

**Interfaces:**
- Consumes: `Proposal` (Task 2) và `GalleryVote` (Task 1).
- Produces:
  - `same_can(a_box, b_box) -> bool`: IoU ≥ 0,5, hoặc phần giao ≥ 0,8 diện tích box nhỏ hơn.
  - `@dataclass Track`:
    - `id: str`, `box: tuple` (trung vị);
    - `seen: dict[str, dict[str, Proposal]]`: `capture_id -> {"A": Proposal, "B": Proposal}`, mỗi nguồn tối đa một
      box mỗi frame (box tự tin hơn);
    - `votes: dict[str, GalleryVote]`: `capture_id -> phiếu của kho trên box của frame đó`.
  - `cluster(frames: dict[str, list[Proposal]], segment_id: str) -> list[Track]`:
    - duyệt frame theo thứ tự thời gian;
    - một box thuộc cụm đầu tiên mà `same_can(box, track.box)`;
    - box tâm cụm cập nhật bằng trung vị sau mỗi frame;
    - id là `"<segment>-t<n>"`.

- [ ] **Step 1: Viết test**

```python
def test_a_body_box_and_a_lid_plus_body_box_of_one_can_are_one_track():
    # A (100,200,70,160) và B (98,170,74,192) ở cùng frame -> 1 track có cả "A" và "B"
def test_two_cans_side_by_side_stay_two_tracks():
    # (100,200,70,160) và (172,200,70,160) -> 2 tracks
def test_a_can_seen_in_several_frames_is_one_track_with_a_median_box(): ...
def test_one_source_keeps_its_surer_box_when_it_gives_two_in_a_frame(): ...
```

- [ ] **Step 2:** Chạy test. Expected: FAIL.
- [ ] **Step 3:** Viết `same_can`, `Track` và `cluster`.
- [ ] **Step 4:** Chạy test. Expected: PASS.
- [ ] **Step 5:** Commit `Auto-label: cluster the boxes of a segment into cans`.

### Task 4: Luật quyết định (`auto_label.py`, phần 2)

**Files:**
- Modify: `training/store_view/auto_label.py`
- Test: `tests/test_auto_label.py`

**Interfaces:**
- Consumes: `Track` (Task 3), `MIN_IMAGES` (Task 1).
- Produces:
  - `PRESENT_BOTH = 0.30`, `PRESENT_B_ONLY = 0.60`, `GHOST = 0.30`, `STABLE = 0.80`, `MIN_FRAMES = 5`.
  - `@dataclass(frozen=True) Decision(status: str, sku: str | None, reason: str)`:
    - `status` là `"accept"`, `"review"`, `"drop"` hoặc `"too_short"`.
  - `decide(track: Track, frames: list[str], gallery_counts: dict[str, int]) -> Decision`. `frames` là các frame đã
    chạy của đoạn.

**Luật** (thứ tự kiểm tra, mỗi dòng là một `reason`):
1. `len(frames) < MIN_FRAMES` → `too_short`.
2. Tỉ lệ frame mà A hoặc B thấy < `GHOST` → `drop` (`ghost`).
3. Có lon thật khi:
   - A ≥ 0,30 **và** B ≥ 0,30; hoặc
   - A < 0,30, B ≥ 0,60, và phiếu kho `none_hit` ở dưới một nửa số frame B thấy.
   
   Nếu kho nói `none_hit` ở ≥ một nửa số frame đó → `drop` (`gallery_none`).
   
   Mọi trường hợp khác → `review`, với lý do `only_A` hoặc `weak`.
4. Vị của A là vị có nhiều frame nhất trong các frame A thấy, và phải chiếm ≥ `STABLE`. Vị của kho tính tương tự trên
   các phiếu có `sku`. Thiếu vị của A (lon chỉ B thấy) → `review` (`no_A_flavour`).
5. Vị của A có dưới `MIN_IMAGES` ảnh trong kho → `review` (`thin_gallery`).
6. A và kho cùng một vị, cả hai đều ổn định → `accept` với vị đó. Còn lại → `review` (`disagree` hoặc `unstable`).

- [ ] **Step 1: Viết test** (bảng `pytest.mark.parametrize`, mỗi dòng một luật, giá trị cụ thể):

```python
# (A thấy, B thấy, số frame, vị A theo frame, vị kho theo frame, none_hit theo frame) -> (status, sku, reason)
# 10/10, 10/10, 10, cheese x10, cheese x10           -> accept cheese145
# 2/10,  2/10,  10                                   -> drop ghost
# 0/10,  8/10,  10, -, original x8                    -> review no_A_flavour
# 0/10,  8/10,  10, none_hit x6                       -> drop gallery_none
# 10/10, 0/10,  10                                   -> review only_A
# 10/10, 10/10, 10, hot x10, (kho có 0 ảnh hot)       -> review thin_gallery
# 10/10, 10/10, 10, original x10, cheese x10          -> review disagree
# 10/10, 10/10, 10, original x7 + cheese x3, ...      -> review unstable
# 3 frames                                            -> too_short
```

- [ ] **Step 2:** Chạy test. Expected: FAIL.
- [ ] **Step 3:** Viết `decide`.
- [ ] **Step 4:** Chạy test. Expected: PASS.
- [ ] **Step 5:** Commit `Auto-label: decide each can, accept only when independent sources agree`.

### Task 5: Áp quyết định của người và ghi nhãn (`auto_label_labels.py`)

**Files:**
- Create: `training/store_view/auto_label_labels.py`
- Test: `tests/test_auto_label_labels.py`

**Interfaces:**
- Consumes: `Track` và `Decision` (Task 3–4); `labels.to_yolo`; `dataset.read_scoring_frames`.
- Produces:
  - **File review** (phần 2 sẽ ghi file này từ trang Model):

    ```json
    {"<segment id>": {"tracks": {"<track id>": {"verdict": "sku", "sku": "original145"}},
                      "missed": [[x, y]]}}
    ```

    `verdict` là `sku`, `not_product` hoặc `out_of_scope`.
  - `apply_review(decisions: dict[str, Decision], review: dict) -> dict[str, Decision]`:
    - `sku` → `accept` với vị người chọn;
    - `not_product` → `drop`;
    - `out_of_scope` → `review` với lý do `out_of_scope`, để vùng đó vẫn bị che.
  - `frame_labels(capture_id, tracks, decisions, classes, missed, mask_radius=40)
    -> tuple[list[str], list[tuple[int,int,int,int]]]`. Trả về dòng YOLO theo frame 2560×1440 và các vùng cần che:
    - `accept`: ghi box riêng của cụm trên frame đó (box A, không có thì box B);
    - `accept` nhưng frame đó không có box của cụm (lon bị che): **không ghi**, mà che vùng box trung vị;
    - `review`: che;
    - điểm lon sót: che hình vuông cạnh `2*mask_radius`;
    - `drop`: không ghi, không che.
  - `write_segment(...)`: chép frame đã che xám (127) vào `images/`, ghi `.txt` vào `labels/`. Bỏ frame AUD, frame giữ
    riêng và frame không đọc được, có đếm từng loại.

- [ ] **Step 1: Viết test**

```python
def test_an_accepted_can_is_written_with_its_own_box_in_that_frame(): ...
def test_a_frame_where_the_can_is_hidden_masks_it_instead_of_labelling(): ...
def test_review_and_out_of_scope_are_masked_never_labelled(): ...
def test_review_file_turns_a_track_into_the_chosen_flavour(): ...
def test_missed_points_are_masked(): ...
def test_write_segment_skips_scoring_and_holdout_frames(tmp_path): ...
def test_a_flavour_outside_the_classes_is_an_error(): ...
```

- [ ] **Step 2:** Chạy test. Expected: FAIL.
- [ ] **Step 3:** Viết `auto_label_labels.py`.
- [ ] **Step 4:** Chạy test. Expected: PASS.
- [ ] **Step 5:** Commit `Auto-label: human decisions, YOLO labels and grey masks`.

### Task 6: Cổng 1 (`auto_label_gate.py`)

**Files:**
- Create: `training/store_view/auto_label_gate.py`
- Test: `tests/test_auto_label_gate.py`

**Interfaces:**
- Consumes: `Track` và `Decision`; `truth.json`. Dòng `kind` gồm `face`, `partial`, `lid`, `lower` và `ignore`.
- Produces:
  - `GATE1 = {"real": (">=", 0.99), "flavour": (">=", 0.98), "coverage": (">=", 0.95), "review_share": ("<=", 0.40)}`.
  - `score(segments: dict[str, tuple[list[Track], dict[str, Decision]]], truth: dict[str, list[dict]],
    keyframe_of: dict[str, str]) -> dict`. Chấm trên keyframe của mỗi đoạn có đáp án:
    - box của cụm là box riêng ở keyframe, không có thì box trung vị;
    - "khớp" là tâm box nằm trong một dòng đáp án chưa bị lấy;
    - `real`: trong các cụm `accept`, tỉ lệ khớp được một dòng bất kỳ (kể cả `ignore` và `lower`);
    - `flavour`: trong các cụm `accept` khớp dòng có `sku` biết được, tỉ lệ đúng vị;
    - `coverage`: trong các dòng khác `ignore`, tỉ lệ được một cụm `accept` hoặc `review` khớp;
    - `review_share`: tỉ lệ đoạn có ít nhất một cụm `review`, trên số đoạn không bị `too_short`.
  - `failures(summary) -> list[str]`.

- [ ] **Step 1: Viết test**

```python
def test_an_accepted_can_on_a_lower_tier_truth_row_counts_as_real(): ...
def test_an_accepted_box_where_no_truth_row_is_is_not_real(): ...
def test_flavour_ignores_rows_whose_flavour_is_unknown(): ...
def test_coverage_counts_review_as_covered(): ...
def test_review_share_is_per_segment(): ...
def test_failures_lists_each_metric_off_its_limit(): ...
```

- [ ] **Step 2:** Chạy test. Expected: FAIL.
- [ ] **Step 3:** Viết `auto_label_gate.py`.
- [ ] **Step 4:** Chạy test. Expected: PASS.
- [ ] **Step 5:** Commit `Auto-label: gate 1 on the held-out truth`.

### Task 7: Lệnh dòng lệnh và cấu hình camera (`auto_label_run.py`)

**Files:**
- Create:
  - `training/store_view/auto_label_run.py`
  - `training/store_view/cameras/CAM-S01-A.json`
- Test: `tests/test_auto_label_run.py`

**Interfaces:**
- Consumes: mọi thứ của Task 1–6; `labels.boxes_of`; `dataset.spread`.
- Produces:
  - **Cấu hình camera:**

    ```json
    {"camera": "CAM-S01-A",
     "groups": {
       "slide": {"region": [880, 120, 1520, 720],
                 "classes": ["cheese145", "hot160", "original145", "sourcream150"],
                 "prompts": {"source": "truth", "keyframes": ["CAP-S01-20261123-151304-2"]}},
       "th": {"region": [760, 0, 1200, 320], "classes": ["th_true_milk"],
              "prompts": {"source": "keyframes", "keyframes": []}}}}
    ```

    Danh sách keyframe mẫu của TH được điền khi chạy Step 6.
  - **Các lệnh:**
    - `propose --config C --group slide --segments S --frames F --truth T --gallery G --slide-weights W --yoloe W2
      --split train|holdout --per-segment 30 --out DIR`: ghi `DIR/<segment>.json` (cụm, quyết định, box theo frame)
      và `DIR/review.json` (danh sách đoạn có cụm `review`).
    - `labels --proposals DIR --review R.json --frames F --classes-from C --out OUT`: chỉ chạy cho đoạn `train`.
    - `gate1 --proposals DIR --truth T --segments S`: in bảng, rồi in `gate 1 passed` hoặc danh sách trượt.
    - `draft-keyframes --config C --group th|slide --frames F --keyframes K... --prompts-from P --out DIR`: chạy chỉ
      nguồn B trên các keyframe đưa vào, ghi box nháp (JSON) và ảnh phóng to để người kiểm.
  - `run_segment(frames, sources, gallery, region) -> tuple[list[Track], dict[str, Decision]]`:
    - nhận nguồn qua tham số để test được bằng nguồn giả;
    - với mỗi cụm và mỗi frame cụm được thấy, cắt box của frame đó (box A, không có thì box B) và gọi
      `slide_gallery.read(gallery, colour(crop))`, ghi vào `Track.votes`;
    - sau đó gọi `decide`.
  - Phần 2 sẽ đưa quyết định của người trong file review vào kho ảnh như một nguồn nhãn người. Kế hoạch này không làm
    việc đó.

- [ ] **Step 1: Viết test**

```python
def test_run_segment_with_fake_sources_accepts_an_agreed_can_and_reviews_a_disputed_one(): ...
def test_propose_skips_scoring_frames_and_writes_one_file_per_segment(tmp_path): ...
def test_config_classes_come_from_the_file_not_the_code(tmp_path): ...
```

- [ ] **Step 2:** Chạy test. Expected: FAIL.
- [ ] **Step 3:** Viết `auto_label_run.py` và file cấu hình.
- [ ] **Step 4:** Chạy test. Expected: PASS. Sau đó chạy toàn bộ bộ test. Expected: mọi test PASS (trừ
  `test_torch_first` SKIP).
- [ ] **Step 5:** Chạy thật trên HUYHOANG (`.venv-label`; GPU rảnh, không có lần train nào khác đang chạy):
  1. Chạy `export-trn` trên laptop, chép file sang HUYHOANG, rồi `build --exclude-holdout` →
     `slide_gallery\slide_gallery_CAM-S01-A_<ngày>_eval.npz`.
     Expected: in số ảnh theo vị; Hot dưới 20 ảnh.
  2. Chạy `propose --split holdout` → `store_eval\autolabel_holdout\`, rồi `gate1`.
     Expected: in bảng 4 chỉ số. Ghi số vào ledger (trượt cũng ghi). Trượt độ đúng thì đẩy ngưỡng về phía review theo
     spec, không hạ cổng.
- [ ] **Step 6:** Chạy `draft-keyframes --group th` trên một frame TH của 24/11 có sẵn nhãn, với keyframe mẫu TH lấy từ
  `keyframes.json`. Expected: box nháp phủ ≥ 80% hộp đã có nhãn. Đây là việc chuẩn bị để vẽ keyframe 26/11 cho TH.
- [ ] **Step 7:** Commit `Auto-label: propose, labels, gate1 and draft-keyframes commands; camera config`.

### Task 8: Bổ sung lon tầng dưới vào đáp án, rồi đo lại cổng 1

**Files:**
- Modify: `C:\Users\huyho\milk_store_labels\slide\truth.json`, ngoài repo. Sao lưu trước thành `truth.json.bak-20261125`.
- Create: `training/store_view/truth_lower.py` (sheet phóng to và ghi dòng `lower`)
- Test: `tests/test_truth_lower.py`

**Interfaces:**
- Produces:
  - `candidates(truth_rows, proposals) -> list[list[int]]`: box của nguồn B không khớp dòng đáp án nào.
  - `add_lower(truth, keyframe, boxes_with_sku) -> dict`: thêm dòng `{"box", "sku", "kind": "lower"}`; vị không nhìn
    ra thì ghi `"unknown"`. Không đụng các dòng cũ.

- [ ] **Step 1: Viết test**

```python
def test_candidates_are_the_boxes_no_truth_row_holds(): ...
def test_add_lower_keeps_the_old_rows_and_marks_the_new_ones_lower(): ...
```

- [ ] **Step 2:** Chạy test. Expected: FAIL.
- [ ] **Step 3:** Viết `truth_lower.py`. Ảnh phóng to theo cách của `labels.zoom_view`.
- [ ] **Step 4:** Chạy test. Expected: PASS.
- [ ] **Step 5:** Ra box ứng viên cho 18 keyframe, dùng `draft-keyframes --group slide`.
  - Claude xem từng sheet phóng to: giữ lon Slide ở tầng dưới (vị nhìn được thì ghi, không thì `unknown`), bỏ những
    gì không phải lon Slide.
  - Ghi `truth.json` mới.
  
  Expected: số dòng `lower` được in theo từng keyframe.
- [ ] **Step 6:** Chạy lại `gate1` (Task 7, Step 5.2) với đáp án mới. Expected: in bảng. Ghi vào ledger và báo hoang.
- [ ] **Step 7:** Commit `Auto-label: lower-tier cans in the Slide truth`. Chỉ commit code; `truth.json` nằm ngoài repo.
