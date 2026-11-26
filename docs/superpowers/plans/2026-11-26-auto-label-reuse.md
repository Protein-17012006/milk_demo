# Auto-label phần 2a: dùng lại quyết định của người, cổng 1 mới — kế hoạch triển khai

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Một lon cần xem nhận lại quyết định mà người đã đưa ra cho lon cùng chỗ, cùng màu. Hàng chờ chỉ mở frame
review cho lon chưa ai quyết. Cổng 1 đo lại theo luật mới trên các đoạn giữ riêng.

**Architecture:**
- Mỗi `Track` mang thêm màu trung bình của các box của nó.
- Module mới `auto_label_reuse.py` gồm:
  - `Precedent`: một quyết định của người, có chỗ, màu và nhãn;
  - hàm `queue()`: duyệt các đoạn theo thời gian; mỗi lon cần xem thì nhận lại quyết định, chờ cùng lon đang chờ, hoặc mở frame mới.
- Ba nguồn `Precedent`: đáp án phía train, verdict TRN và file review.
- Cổng 1 mô phỏng người bằng đáp án và đo thêm "dùng lại đúng".

**Tech Stack:** Python 3.12, numpy, opencv, pytest. YOLOE/Slide v3 chỉ dùng lại qua `propose` sẵn có.

**Spec:** `docs/superpowers/specs/2026-11-25-auto-label-design.md`, mục 5.4b và 5.7 (hoang duyệt ngày 26/11).

**Nối tiếp:** kế hoạch phần 1 `docs/superpowers/plans/2026-11-25-auto-label-offline.md`. Phần 2b (hàng chờ Review trên
website) là kế hoạch riêng, viết sau Task 6.

## Global Constraints

**Dữ liệu:**
- Frame AUD không bao giờ là nguồn quyết định, không vào kho ảnh, không vào nhãn. Lọc bằng `dataset.read_scoring_frames(frames_dir)`.
- Đáp án của đoạn giữ riêng (`segments.json`, `split == "holdout"`) không bao giờ là `Precedent` thật. Nó chỉ được dùng để mô phỏng người trong `simulate()` của cổng 1.
- Verdict TRN của frame giữ riêng bị loại, như `slide_gallery.build`: `segments.holdout(capture_timestamp)`.
- Kho ảnh dùng cho cả hai split là `slide_gallery_CAM-S01-A_20261125_eval.npz` (build với `--exclude-holdout`). Nhãn train không được chứa thông tin từ đáp án giữ riêng.

**Luật 5.4b:**

| Thứ | Giá trị |
|---|---|
| Cùng chỗ | IoU box trung vị ≥ 0,5, chỉ IoU (không dùng luật "nằm trong 80%" của `same_can`) |
| Cùng màu | tích vô hướng hai vector màu đơn vị ≥ `REUSE_MIN_SIM` (đo ở Task 6) |
| Precedent khớp mà nhãn khác nhau | không nhận lại, lý do `reuse_conflict`, vẫn cần người |
| Nhãn | một vị (`sku`), `not_product` hoặc `out_of_scope` |
| Áp nhãn | vị → `accept`; `not_product` → `drop`; `out_of_scope` → `masked` |
| Lon chưa có màu (`colour is None`) | không bao giờ khớp gì |

**Cổng 1:**

| Chỉ số | Ngưỡng |
|---|---|
| `real` | ≥ 0,99 |
| `flavour` | ≥ 0,98 |
| `coverage` | ≥ 0,95 |
| `review_share` | ≤ 0,40 (đoạn cần frame review **mới**) |
| `reuse_right` | ≥ 0,99 |

**Môi trường và lưu trữ:**
- Không cài gì vào `C:\Users\huyho\Datagent\.venv`. Code cần model chạy trong `.venv-label` (mượn torch qua `.pth`).
- Ảnh tiệm, nhãn và kho ảnh không vào repo hay OneDrive.

**Test:**
- Laptop: `C:\Users\huyho\AppData\Local\Temp\claude\cf23e0181d28b9db\c11d7523-35fb-4e66-a00b-2c45dc42d78f\scratchpad\venv312\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/<file>` (gọi tắt `PYTEST` bên dưới). Nếu venv đó mất thì dùng bất kỳ venv py3.12 nào có `requirements-dev.txt` và `opencv-python`.
- Cả bộ test phải xanh trước mỗi commit (434 đạt, 2 bỏ qua lúc bắt đầu).

**Nhánh:** `feat/th-store-view` (đang ở `e14470c`), làm thẳng trên nhánh này như phần 1 sau khi đã merge.

## Review Focus

1. **Một file đề xuất cũ không có `colour`** (chạy trước Task 1): `_track_from` phải đọc được với `colour=None`, và lon đó không bao giờ được nhận lại. Test nằm ở Task 1 và Task 2.
2. **Lon bị đổi giữa hai đoạn**, cùng chỗ nhưng khác màu: không nhận lại, mà mở frame review. Test nằm ở Task 2.
3. **Đáp án giữ riêng hoặc frame AUD lọt vào làm `Precedent` thật**: phần CLI chỉ lấy keyframe của đoạn `train` và loại frame AUD và TRN giữ riêng. Test nằm ở Task 5.
4. **Người sửa một quyết định:** nhãn phải đổi theo ở lần chạy `labels` sau. `queue()` không ghi gì vào file đề xuất và không sửa dict đầu vào. Test nằm ở Task 2.
5. **Thứ tự thời gian của đoạn:** `queue()` sắp đoạn theo frame đầu (`frames[0]`), không theo tên file. Một lon "chờ cùng" chỉ được trỏ tới lon của đoạn trước. Test nằm ở Task 2.

---

### Task 1: Màu của mỗi lon

**Files:**
- Modify: `training/store_view/slide_gallery.py` (thêm `mean_colour` sau `colour`)
- Modify: `training/store_view/auto_label.py` (`Track`)
- Modify: `training/store_view/auto_label_run.py` (`run_segment`, `_track_json`, `_track_from`)
- Test: `tests/test_auto_label_run.py`, `tests/test_slide_gallery.py`

**Interfaces:**
- Produces:
  - `slide_gallery.mean_colour(feats: list[np.ndarray]) -> np.ndarray | None`: trung bình rồi chuẩn L2; danh sách rỗng thì trả `None`.
  - `Track.colour: np.ndarray | None = None`.
  - JSON của track có khoá `"colour"`: list float làm tròn 5 chữ số, hoặc `null`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_slide_gallery.py
def test_mean_colour_is_a_unit_vector_and_none_for_nothing():
    m = mean_colour([patch(YELLOW), patch(YELLOW), patch(GREEN)])
    assert abs(float(np.linalg.norm(m)) - 1.0) < 1e-6
    assert float(m @ patch(YELLOW)) > float(m @ patch(GREEN))
    assert mean_colour([]) is None

# tests/test_auto_label_run.py
def test_run_segment_gives_each_can_the_colour_of_its_boxes():
    tracks, _, _ = run_segment("seg-1", ["C1", "C2"], lambda c: scene(), FakeSources(), gallery())
    by_box = {tuple(t.box): t for t in tracks}
    assert float(by_box[CAN1].colour @ patch(YELLOW)) > 0.99
    assert float(by_box[CAN2].colour @ patch(GREEN)) > 0.99

def test_a_track_round_trips_with_and_without_colour():
    t = Track("s-t0", (1.0, 2.0, 3.0, 4.0)); t.colour = patch(YELLOW)
    back = _track_from(json.loads(json.dumps(_track_json(t))))
    assert np.allclose(back.colour, t.colour, atol=1e-4)
    old = _track_json(t); del old["colour"]
    assert _track_from(old).colour is None
```

`patch` và `YELLOW`/`GREEN` trong `test_slide_gallery.py` dùng helper sẵn có của file đó. Nếu file chưa có thì chép `patch` từ `test_auto_label_run.py`.

- [ ] **Step 2: Run them to verify they fail**

Run: `PYTEST tests/test_slide_gallery.py tests/test_auto_label_run.py`
Expected: FAIL với lỗi `ImportError: mean_colour` và `AttributeError: colour`.

- [ ] **Step 3: Implement**

**`run_segment`:** màu của track là `mean_colour` của các đặc trưng `feats[(cid, p)]`. Mỗi frame lấy box mà track dùng ở frame đó (A nếu có, không thì B), giống cách chọn box cho `votes`.

**`_track_json`:** ghi khoá `"colour"`.

**`_track_from`:** đọc khoá `"colour"`, thiếu thì `None`.

- [ ] **Step 4: Run to verify they pass**

Run: `PYTEST tests/test_slide_gallery.py tests/test_auto_label_run.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add training/store_view/slide_gallery.py training/store_view/auto_label.py training/store_view/auto_label_run.py tests/test_slide_gallery.py tests/test_auto_label_run.py
git commit -m "Auto-label: each can carries the mean colour of its boxes"
```

### Task 2: Dùng lại quyết định và hàng chờ

**Files:**
- Create: `training/store_view/auto_label_reuse.py`
- Modify: `training/store_view/auto_label_labels.py` (`apply_review`: `out_of_scope` → status `masked`)
- Test: `tests/test_auto_label_reuse.py`, `tests/test_auto_label_labels.py` (sửa kỳ vọng `out_of_scope`)

**Interfaces:**
- Consumes: `Track.colour` (Task 1); `auto_label.Decision`, `auto_label._overlap`.
- Produces (trong `auto_label_reuse.py`):

```python
REUSE_MIN_SIM: float = 0.95  # tạm; Task 6 thay bằng số đo
NOT_PRODUCT, OUT_OF_SCOPE = "not_product", "out_of_scope"

@dataclass(frozen=True)
class Precedent:
    key: str                                  # capture id nơi người quyết (so sánh chuỗi = so thời gian)
    box: tuple[float, float, float, float]
    colour: np.ndarray                        # vector đơn vị 144 chiều
    label: str                                # một sku, NOT_PRODUCT hoặc OUT_OF_SCOPE
    source: str                               # "review:<track id>", "truth:<key>#<i>", "trn:<cid>@x,y", "sim:<track id>"

def same_place(a, b) -> bool                                          # IoU >= 0.5
def matching(track: Track, precedents: Sequence[Precedent], min_sim: float) -> list[Precedent]
def decision_for(label: str, reason: str) -> Decision                 # sku→accept, NOT_PRODUCT→drop, OUT_OF_SCOPE→masked
def label_of(d: Decision) -> str | None                               # ngược lại: accept→sku, drop→NOT_PRODUCT, masked→OUT_OF_SCOPE, khác→None
def reuse(track: Track, precedents: Sequence[Precedent], min_sim: float) -> Decision | None

@dataclass
class QueueResult:
    decisions: dict[str, dict[str, Decision]]   # đoạn → track → quyết định sau khi dùng lại
    new_frames: dict[str, list[str]]            # đoạn cần frame review mới → các track người phải quyết trên frame đó
    links: list[tuple[str, str, str]]           # (đoạn, track id, source của precedent mới nhất) cho mỗi lon được nhận lại

def queue(
    proposals: list[dict],                      # như load_proposals(): segment, frames, tracks, decisions
    precedents: Sequence[Precedent],
    min_sim: float = REUSE_MIN_SIM,
    human: Callable[[dict, Track], str | None] | None = None,
) -> QueueResult
```

**Luật của `reuse()`:**
- Không có precedent khớp thì trả `None`.
- Các precedent khớp mang nhãn khác nhau thì trả `Decision("review", None, "reuse_conflict")`.
- Còn lại trả `decision_for(label, f"reused:{source}")`, với `source` của precedent có `key` lớn nhất.

**Luật của `queue()`:**
1. Sắp các đoạn theo `frames[0]`.
2. Trong mỗi đoạn, chỉ xét lon có status `review`. Lon `out_of_scope` giờ là `masked` nên tự đứng ngoài.
3. Thứ tự với mỗi lon:
   1. `reuse()` với các precedent đã quyết.
   2. Nếu không khớp, so cùng chỗ và cùng màu với lon đang chờ ở đoạn trước. Khớp thì `Decision("review", None, f"waits:{track id}")`.
   3. Nếu vẫn không khớp, lon vào `new_frames[segment]`.
4. Với lon mới, nếu có `human`:
   - gọi `human(proposal, track)`;
   - có nhãn trả về thì thêm `Precedent(key=frames[0], label=..., source=f"sim:{track.id}")` vào danh sách đã quyết, và đặt quyết định của lon là `decision_for(label, "human")`;
   - trả `None` thì lon thành "đang chờ".
5. Lon có `reuse_conflict` cũng vào `new_frames`.
6. Không sửa dict đầu vào: copy `decisions` của từng đoạn.

- [ ] **Step 1: Write the failing tests** (`tests/test_auto_label_reuse.py`)

**Fixture:**
- Helper `can(tid, box, colour)` dựng `Track` có `colour` sẵn.
- Helper `prop(seg, first_frame, tracks, decisions)` dựng một dict đề xuất.
- Màu dùng `patch(YELLOW)` và `patch(GREEN)` từ `test_auto_label_run.py`. Đưa vào `tests/conftest.py` nếu cần dùng chung.

**Các test:**

```python
def test_a_can_at_the_same_place_with_the_same_colour_takes_the_human_flavour():
    # precedent original145 tại (100,500,70,160) màu YELLOW; lon review cùng box, cùng màu
    assert reuse(t, [p], 0.95) == Decision("accept", "original145", "reused:truth:K#0")

def test_a_swapped_can_same_place_other_colour_is_not_reused():      # Review Focus 2
    # precedent sourcream150 màu GREEN; lon cùng box màu YELLOW
    assert reuse(t, [p], 0.95) is None

def test_iou_below_half_is_another_place():
    # box lệch để IoU = 0.4, cùng màu
    assert reuse(t, [p], 0.95) is None

def test_matching_precedents_that_disagree_send_the_can_to_a_person():
    assert reuse(t, [p_cheese, p_original], 0.95) == Decision("review", None, "reuse_conflict")

def test_not_product_drops_and_out_of_scope_masks():
    assert decision_for("not_product", "r").status == "drop"
    assert decision_for("out_of_scope", "r") == Decision("masked", None, "r")
    assert label_of(Decision("masked", None, "x")) == "out_of_scope"

def test_a_can_without_colour_never_matches():                        # Review Focus 1
    t.colour = None
    assert reuse(t, [p], 0.0) is None

def test_queue_opens_one_frame_then_later_segments_wait_on_it():
    # 3 đoạn cùng một lon review, không precedent, không human
    r = queue([s1, s2, s3], [], 0.95)
    assert list(r.new_frames) == ["s1"]
    assert r.decisions["s2"]["s2-t0"] == Decision("review", None, "waits:s1-t0")

def test_queue_orders_segments_by_first_frame_not_by_name():          # Review Focus 5
    # đoạn "s9" có frames[0] sớm hơn "s1"
    assert list(queue([s1_late, s9_early], [], 0.95).new_frames) == ["s9"]

def test_a_simulated_human_decision_is_reused_by_later_segments():
    r = queue([s1, s2], [], 0.95, human=lambda prop, t: "cheese145" if prop["segment"] == "s1" else None)
    assert r.decisions["s1"]["s1-t0"] == Decision("accept", "cheese145", "human")
    assert r.decisions["s2"]["s2-t0"] == Decision("accept", "cheese145", "reused:sim:s1-t0")
    assert r.links == [("s2", "s2-t0", "sim:s1-t0")]

def test_accepted_cans_and_out_of_scope_are_left_alone():
    # accept/agree và review/out_of_scope không đổi, không mở frame

def test_queue_does_not_change_its_input():                           # Review Focus 4
    before = copy.deepcopy(s1["decisions"]); queue([s1], [p], 0.95)
    assert s1["decisions"] == before
```

**Sửa `tests/test_auto_label_labels.py`:**
- Trong `test_review_file_turns_a_track_into_the_chosen_flavour`, kỳ vọng đổi thành `out["s-t2"] == Decision("masked", None, "out_of_scope")`.
- Trong `test_review_and_out_of_scope_are_masked_never_labelled`, dòng `s-t1` đổi thành `Decision("masked", None, "out_of_scope")`. Mask vẫn như cũ.

- [ ] **Step 2: Run to verify they fail**

Run: `PYTEST tests/test_auto_label_reuse.py tests/test_auto_label_labels.py`
Expected: FAIL với lỗi `ModuleNotFoundError: training.store_view.auto_label_reuse`, và kỳ vọng `masked` của `apply_review`.

- [ ] **Step 3: Implement** `auto_label_reuse.py` theo các Interfaces trên. Sửa `apply_review` cho verdict `out_of_scope` thành `Decision("masked", None, "out_of_scope")`. `frame_labels` đã che mọi status không phải `accept`/`drop`, nên không cần sửa.

- [ ] **Step 4: Run to verify they pass, then the whole suite**

Run: `PYTEST tests/test_auto_label_reuse.py tests/test_auto_label_labels.py`, sau đó `PYTEST tests`
Expected: PASS. Cả bộ test xanh.

- [ ] **Step 5: Commit**

```bash
git add training/store_view/auto_label_reuse.py training/store_view/auto_label_labels.py tests/test_auto_label_reuse.py tests/test_auto_label_labels.py
git commit -m "Auto-label: a can waiting for review takes a human decision on the same can (5.4b)"
```

### Task 3: Ba nguồn quyết định của người

**Files:**
- Modify: `training/store_view/auto_label_reuse.py`
- Test: `tests/test_auto_label_reuse.py`

**Interfaces:**
- Consumes: `slide_gallery.colour`, `slide_gallery.crop_of`; `Precedent`, `NOT_PRODUCT`, `OUT_OF_SCOPE` (Task 2).
- Produces:

```python
def truth_precedents(truth: dict[str, list[dict]], keys: Iterable[str],
                     load: Callable[[str], np.ndarray | None]) -> list[Precedent]
    # mỗi dòng của mỗi keyframe trong keys: màu cắt từ ảnh keyframe;
    # nhãn = sku nếu biết, OUT_OF_SCOPE nếu sku là None/"unknown" hoặc kind "ignore"; source "truth:<key>#<i>"
def trn_precedents(rows: list[tuple[str, list[int], str]],
                   load: Callable[[str], np.ndarray | None]) -> list[Precedent]
    # rows từ slide_gallery.trn_rows(); nhãn "none" → NOT_PRODUCT; source "trn:<cid>@x,y"
def review_precedents(proposals: list[dict], review: dict) -> list[Precedent]
    # mỗi track mà file review quyết (verdict sku/not_product/out_of_scope) và có colour;
    # key = frames[0] của đoạn; box = track.box; source "review:<track id>"
```

**Quy ước chung:** crop không đọc được (`crop_of` trả `None`), hoặc ảnh không đọc được, thì bỏ dòng đó. Các hàm này không lọc giữ riêng hay AUD; việc lọc thuộc về CLI (Task 5).

- [ ] **Step 1: Write the failing tests**

```python
def test_truth_rows_become_precedents_with_their_crop_colour_and_unknown_as_out_of_scope():
    # ảnh scene(): row 0 vàng cheese145, row 1 xanh sku "unknown"
    ps = truth_precedents({"K": rows}, ["K"], lambda c: scene())
    assert [p.label for p in ps] == ["cheese145", "out_of_scope"]
    assert float(ps[0].colour @ patch(YELLOW)) > 0.99 and ps[0].source == "truth:K#0"

def test_trn_none_is_not_product():
    ps = trn_precedents([("C1", [10, 10, 20, 40], "none")], lambda c: scene())
    assert ps[0].label == "not_product" and ps[0].source == "trn:C1@10,10"

def test_review_decisions_become_precedents_keyed_by_the_segment_first_frame():
    review = {"s1": {"tracks": {"s1-t0": {"verdict": "sku", "sku": "hot160"}, "s1-t1": {"verdict": "out_of_scope"}}}}
    ps = review_precedents([s1], review)
    assert {(p.source, p.label, p.key) for p in ps} == {("review:s1-t0", "hot160", "C1"), ("review:s1-t1", "out_of_scope", "C1")}

def test_unreadable_images_give_no_precedent():
    assert truth_precedents({"K": rows}, ["K"], lambda c: None) == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTEST tests/test_auto_label_reuse.py`
Expected: FAIL với lỗi `ImportError: truth_precedents`.

- [ ] **Step 3: Implement** the three functions.

- [ ] **Step 4: Run to verify they pass**

Run: `PYTEST tests/test_auto_label_reuse.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git commit -am "Auto-label: precedents from the train-side truth, TRN verdicts and the review file"
```

### Task 4: Cổng 1 theo luật mới

**Files:**
- Modify: `training/store_view/auto_label_gate.py`
- Test: `tests/test_auto_label_gate.py`

**Interfaces:**
- Consumes: `queue`, `label_of`, `QueueResult`, `NOT_PRODUCT`, `OUT_OF_SCOPE` (Task 2).
- Produces:

```python
GATE1 = {"real": (">=", 0.99), "flavour": (">=", 0.98), "coverage": (">=", 0.95),
         "review_share": ("<=", 0.40), "reuse_right": (">=", 0.99)}

def truth_label(rows: list[dict], box) -> str
    # dòng đầu tiên có box chứa tâm của box: sku nếu biết; OUT_OF_SCOPE nếu sku None/"unknown" hoặc kind "ignore";
    # không dòng nào: NOT_PRODUCT

def score(segments, truth, keyframe_of, new_frames: set[str] | None = None) -> dict
    # như cũ, nhưng:
    #  - "accepted"/real/flavour chỉ đếm Decision có reason == "agree" (máy tự chấp nhận);
    #  - coverage tính status "accept", "review" và "masked";
    #  - new_frames khác None thì review_share = số đoạn (không too_short) nằm trong new_frames / số đoạn.

def simulate(proposals: list[dict], truth: dict[str, list[dict]],
             precedents: Sequence[Precedent], min_sim: float) -> dict
    # human(prop, track) = truth_label(truth[kf], track.box_in(kf) or track.box) nếu keyframe kf của đoạn có trong truth, ngược lại None;
    # r = queue(proposals, precedents, min_sim, human);
    # s = score({seg: (tracks, r.decisions[seg])}, truth, keyframe_of, set(r.new_frames));
    # s["reuse_right"] = đúng/tổng trên các link mà keyframe của đoạn có trong truth:
    #    đúng khi label_of(quyết định đã nhận lại) == truth_label(rows, box của lon tại keyframe);
    #    không link nào thì None;
    # s["counts"] thêm "new_frames", "reused", "waiting", "reuse_checked", "reuse_right".
```

- [ ] **Step 1: Write the failing tests**

```python
def test_reused_and_human_accepts_are_not_counted_as_machine_accepts():
    decisions = {"t0": Decision("accept", "cheese145", "reused:truth:K#0")}
    s = one([can("t0", (100, 500, 70, 160))], decisions, [{"box": [95, 495, 80, 170], "sku": "cheese145", "kind": "face"}])
    assert s["real"] is None and s["coverage"] == 1.0

def test_masked_counts_as_covered():
    ...  # Decision("masked", None, "out_of_scope") phủ dòng đáp án

def test_review_share_counts_only_segments_that_need_a_new_frame():
    s = score({...3 đoạn review...}, {}, {}, new_frames={"s1"})
    assert s["review_share"] == 1 / 3

def test_truth_label_reads_flavour_unknown_and_nothing():
    assert truth_label(rows, (100, 500, 70, 160)) == "cheese145"
    assert truth_label(rows, (305, 105, 60, 30)) == "out_of_scope"
    assert truth_label(rows, (900, 900, 50, 50)) == "not_product"

def test_simulate_scores_a_wrong_reuse_as_wrong():
    # đoạn s1 (keyframe K1: sourcream150 tại box) và s2 (keyframe K2: cheese145 cùng box),
    # cùng màu trên track (giả lập trường hợp nhìn giống nhau) → s2 nhận lại sourcream150 → reuse_right == 0.0
    s = simulate([s1, s2], {"K1": rows_sour, "K2": rows_cheese}, [], 0.95)
    assert s["reuse_right"] == 0.0 and s["counts"]["new_frames"] == 1

def test_simulate_leaves_segments_without_truth_waiting():
    s = simulate([s1_no_truth, s2_no_truth], {}, [], 0.95)
    assert s["counts"]["waiting"] == 1 and s["reuse_right"] is None

def test_failures_lists_reuse_right():
    assert "reuse_right" in GATE1
    assert any(f.startswith("reuse_right") for f in failures({**ok, "reuse_right": 0.9}))
```

**Sửa test cũ `test_failures_lists_each_metric_off_its_limit`:** tập khoá mong đợi thêm `"reuse_right"`.

- [ ] **Step 2: Run to verify they fail**

Run: `PYTEST tests/test_auto_label_gate.py`
Expected: FAIL

- [ ] **Step 3: Implement** `truth_label`, the `score` changes, `simulate`, and the new `GATE1` key. Cập nhật docstring đầu module cho đúng các chỉ số mới.

- [ ] **Step 4: Run to verify they pass, then the whole suite**

Run: `PYTEST tests/test_auto_label_gate.py`, sau đó `PYTEST tests`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git commit -am "Auto-label: gate 1 counts new review frames and scores reused decisions"
```

### Task 5: Lệnh `queue`, `labels`, `gate1`, `reuse-pairs`

**Files:**
- Modify: `training/store_view/auto_label_run.py`, `training/store_view/auto_label_reuse.py` (`pair_stats`, `suggest_min_sim`)
- Test: `tests/test_auto_label_run.py`, `tests/test_auto_label_reuse.py`

**Interfaces:**
- Consumes: Tasks 2–4; `dataset.read_scoring_frames`, `segments.holdout`, `slide_gallery.trn_rows`.
- Produces:

```python
# auto_label_reuse.py
def pair_stats(precedents: Sequence[Precedent]) -> list[tuple[float, bool]]
    # mọi cặp precedent khác key, cùng chỗ: (độ giống màu, cùng nhãn?)
def suggest_min_sim(pairs: list[tuple[float, bool]]) -> float
    # phân vị 5% của các cặp cùng nhãn; nếu thấp hơn hoặc bằng cặp khác nhãn giống nhất thì nâng lên cặp đó + 0.005

# auto_label_run.py
def human_precedents(truth_path: Path, segments: list[dict], frames_dir: Path,
                     trn_path: Path | None) -> list[Precedent]
    # đáp án: chỉ keyframe của đoạn kind "day" split "train";
    # TRN: trn_rows() bỏ frame AUD (read_scoring_frames) và frame có capture_timestamp giữ riêng (holdout())
```

**Các lệnh:**
- **`propose`:** không ghi `review.json` nữa. Hàng chờ do lệnh `queue` lập. Sửa assert trong test propose sẵn có.
- **`queue --proposals DIR --truth T --segments S --frames F [--trn TRN] [--review R]`:**
  - precedent = `human_precedents(...)` cộng `review_precedents` (nếu có `--review`);
  - ghi `DIR/review.json` = `new_frames`;
  - in `{"segments", "new_frames", "reused", "waiting", "conflict"}`.
- **`labels`:**
  - thêm `--truth`, `--segments` (đã có), `--trn`, `--review`;
  - quyết định của mỗi đoạn = `apply_review` rồi `queue(...)` (không `human`), với precedent = `human_precedents` + `review_precedents`;
  - `write_segment` như cũ.
- **`gate1`:**
  - thêm `--segments`, `--frames`, `--trn`;
  - precedent = `human_precedents(...)`;
  - kết quả = `simulate(...)`;
  - in thêm `reuse_right` và các số mới.
- **`reuse-pairs --truth T --segments S --frames F`:**
  - `pair_stats(truth_precedents(` keyframe phía train `))`;
  - in số cặp, phân vị 1/5/50% của cặp cùng nhãn, max của cặp khác nhãn, và `suggest_min_sim`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_auto_label_reuse.py
def test_suggest_min_sim_is_the_5th_percentile_of_same_label_pairs():
    pairs = [(0.90 + i / 1000, True) for i in range(100)]
    assert abs(suggest_min_sim(pairs) - 0.905) < 0.002

def test_suggest_min_sim_rises_above_the_closest_different_label_pair():
    assert suggest_min_sim([(0.95, True)] * 20 + [(0.97, False)]) == pytest.approx(0.975)

def test_pair_stats_pairs_only_different_keys_at_the_same_place():
    ...  # 2 precedent cùng key không thành cặp; khác key cùng chỗ thành 1 cặp

# tests/test_auto_label_run.py
def test_human_precedents_never_use_held_out_truth_or_scoring_frames(tmp_path):    # Review Focus 3
    # segments: K_train (split train), K_hold (split holdout); manifest.jsonl đánh dấu C_aud có audit AUD
    # trn: một dòng trên C_aud, một dòng TRN capture_timestamp trong HOLDOUT, một dòng TRN train
    ps = human_precedents(truth_path, segments, frames_dir, trn_path)
    assert {p.source.split(":")[0] for p in ps} == {"truth", "trn"}
    assert not any("K_hold" in p.source or "C_aud" in p.source for p in ps)
    assert sum(p.source.startswith("trn:") for p in ps) == 1

def test_queue_command_writes_only_new_frames(tmp_path):
    # 2 file seg-*.json (cùng một lon review, có colour) + truth rỗng → review.json == {"seg-1": ["seg-1-t0"]}
```

Hai file JSON và frame giả có thể dựng từ helper `scene()` và `propose()` với `FakeSources` sẵn có. Ảnh ghi bằng `cv2.imwrite` vào `tmp_path/frames/2026-11-23/<cid>.jpg`. `manifest.jsonl` theo đúng định dạng mà `read_scoring_frames` đọc; xem `tests/test_store_view_dataset.py`.

- [ ] **Step 2: Run to verify they fail**

Run: `PYTEST tests/test_auto_label_reuse.py tests/test_auto_label_run.py`
Expected: FAIL

- [ ] **Step 3: Implement** `pair_stats`, `suggest_min_sim`, `human_precedents` and the commands. Cập nhật docstring đầu `auto_label_run.py` (danh sách lệnh và ví dụ gọi).

- [ ] **Step 4: Run to verify they pass, then the whole suite**

Run: `PYTEST tests`
Expected: PASS, toàn bộ xanh.

- [ ] **Step 5: Commit**

```bash
git commit -am "Auto-label: queue, labels and gate1 use reused decisions; reuse-pairs measures the colour threshold"
```

### Task 6: Đo trên HUYHOANG, chọn ngưỡng màu, chạy cổng 1

Chạy thật, không viết test. GPU dùng chung với worker; giữ như phần 1 (ưu tiên thấp, VRAM có giới hạn).

**Files:**
- Modify: `training/store_view/auto_label_reuse.py` (`REUSE_MIN_SIM` = số đo, kèm chú thích nguồn và ngày)
- Modify: `docs/superpowers/specs/2026-11-25-auto-label-design.md` (5.4b, dòng kết quả)

- [ ] **Step 1: Chép code sang HUYHOANG.**
  - `git archive HEAD training server pytest.ini` ra tar.
  - scp tar vào `C:\Users\huyho\Datagent\logs\autolabel_code.tar`, giải nén vào `autolabel_code` như script `autolabel_step5.ps1` của phần 1.

- [ ] **Step 2: Chạy lại `propose --split holdout`** để các lon có màu.
  - Lệnh và tham số y như phần 1, gallery `slide_gallery_CAM-S01-A_20261125_eval.npz`, `--out store_eval\autolabel_holdout_v2`.
  - Expected: 40 file `seg-*.json`, mỗi track có `"colour"` khác null khi có crop.

- [ ] **Step 3: Đo ngưỡng.**
  - Lệnh: `reuse-pairs --truth store_labels\slide\truth.json --segments store_labels\slide\segments.json --frames store_frames\CAM-S01-A`.
  - Đặt `REUSE_MIN_SIM` = `suggest_min_sim` in ra.
  - Nếu số cặp cùng nhãn < 30, ghi vào spec rằng ngưỡng đo trên ít cặp.

- [ ] **Step 4: Chạy cổng 1.**
  - Lệnh: `gate1 --proposals store_eval\autolabel_holdout_v2 --truth ... --segments ... --frames ... --trn logs\trn_done.json`, với code đã có ngưỡng mới. Lưu stdout vào `store_eval\gate1_reuse_20261126.txt`.
  - Expected: in đủ 5 chỉ số và dòng "gate 1 passed" hoặc "gate 1 FAILED: ...".
  - **Không hạ ngưỡng cổng.** Nếu `reuse_right` < 0,99 thì nâng `REUSE_MIN_SIM`. Nếu `review_share` > 0,40 thì báo hoang kèm số, không tự nới luật 5.4.

- [ ] **Step 5: Kiểm tra lon bị đổi đã biết.** Trên `seg-0029`, lon tại box khoảng (943, 247, 70, 76) không được nhận lại vị của `seg-0018`. Xem `r.decisions` qua một lệnh Python ngắn, hoặc in các link của hai đoạn này.

- [ ] **Step 6: Commit**

```bash
git commit -am "Auto-label: colour threshold for reuse measured on the train-side truth; gate 1 result"
```

### Task 7: Hàng chờ thật trên các đoạn train

- [ ] **Step 1: Chạy `propose --split train`.**
  - Cùng gallery eval (không đưa đáp án giữ riêng vào nhãn), `--out store_eval\autolabel_train`.
  - Expected: một file cho mỗi đoạn ban ngày phía train.

- [ ] **Step 2: Chạy `queue`** trên `store_eval\autolabel_train` với `--truth --segments --frames --trn`.
  - Expected: in số đoạn, số frame review mới, số lon nhận lại, số lon đang chờ.
  - Ghi các số này vào spec 5.4b ("Hàng chờ thật ngày 26/11"). Đây là đầu vào của kế hoạch 2b: hàng chờ trên website sẽ có bao nhiêu frame.

- [ ] **Step 3: Commit**

```bash
git commit -am "Docs: auto-label 5.4b, the first real queue on the train segments"
```

- [ ] **Step 4: Báo hoang.**
  - Kết quả cổng 1: đạt hay trượt, với số cụ thể.
  - Số frame review thật.
  - Sau đó mới viết kế hoạch 2b.
