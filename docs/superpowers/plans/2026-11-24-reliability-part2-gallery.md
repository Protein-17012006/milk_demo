# Độ tin cậy của số đếm, phần 2 — kho ảnh lon thật (kế hoạch làm)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** YOLO vẫn tìm lon. Mỗi hộp Slide được đối chiếu với kho ảnh lon thật cắt từ khung dạy:
- kho chắc chắn là vị khác thì đổi vị theo kho;
- kho không chắc thì hạ độ tin cậy của hộp.

Chỉ bật khi qua cổng (spec mục 2.3).

**Architecture:**
- **Laptop** (có quyền AWS): `scripts/export_audit_crops.py` xuất lon cắt ra từ khung `done`. Khung dạy trước ngày
  cắt dùng để dựng kho; khung chấm điểm từ ngày cắt trở đi dùng cho cổng.
- **HUYHOANG** (GPU, có embedder của `carton_recognition`):
  - `scripts/build_slide_gallery.py` dựng kho;
  - `scripts/gallery_gate.py` chấm bản đang chạy và bản mới trên các khung chấm điểm, rồi ghi báo cáo đạt hay không.
- **Worker:**
  - `server/milk/gallery.py` (numpy thuần) bỏ phiếu và quyết định;
  - `slide_adapter.py` gọi nó khi có biến `MILK_SLIDE_GALLERY`;
  - mỗi hộp ghi thêm nhãn YOLO gốc và kết quả đối chiếu.
- **Backend:** `model_health` thêm tỉ lệ hộp mà kho đổi vị, và `capture_boxes` giữ nhãn YOLO gốc.

**Tech Stack:**
- Python 3.12, numpy, opencv-python-headless.
- Embedder của `carton_recognition` trên HUYHOANG (torch).
- pytest.

**Spec:** `docs/superpowers/specs/2026-11-24-reliability-design.md` (mục 2). Bắt đầu sau phần 1, Task 3 (đã có khung dạy).

## Global Constraints

- **Không bao giờ đưa khung chấm điểm (`AUD-…`) hay `slide_pilot\test_frames` vào kho.** Script xuất và script dựng
  kho đều từ chối khi gặp mã `AUD-`.
- **Ngày cắt D:** kho chỉ chứa khung dạy chụp trước ngày D. Cổng chỉ dùng khung chấm điểm chụp từ ngày D trở đi.
- **Tên phiên bản:** `gallery-<YYYYMMDD của D>`. `MILK_MODEL_VERSION` thêm hậu tố, ví dụ
  `long-2026-10-13+slide-v3+gallery-20261128`.
- **Nhãn của lon cắt ra:**

  | Hộp | Verdict | Nhãn |
  |---|---|---|
  | Có tên SKU | `correct` | nhãn model |
  | Bất kỳ | `wrong_sku` | `true_sku_id` |
  | Có tên SKU | `not_product` | `none` |
  | UNRECOGNIZED | `correct` | `none` (hàng ngoài danh mục) |
  | UNRECOGNIZED | `not_product` | `none` |
  | Bất kỳ | `out_of_scope` | không xuất |

- **Cổng (spec mục 2.3).** Đạt khi thoả cả 4 điều kiện:
  - ít nhất 30 khung chấm điểm, trong ít nhất 2 ngày, đủ 3 buổi;
  - "found right" của `original145` ≥ 0.70;
  - không SKU nào giảm quá 0.05 ở "named right" hay "found right" so với bản đang chạy;
  - KPI #1 và #2 không giảm.
- **Hộp kho không chắc:** độ tin cậy thành `min(conf, 0.69)`. Cờ của dòng vẫn tính theo trung bình các hộp, như CV
  Output hiện nay.
- **`detection_method`** vẫn là `"Visual"`.
- **Không đưa ảnh tiệm hay lon cắt ra vào repo:**
  - thư mục xuất trên laptop: `C:\Users\huyho\OneDrive\Desktop\Milk_Demo\gallery\<D>\` (nằm ngoài repo);
  - kho trên HUYHOANG: `C:\Users\huyho\Datagent\slide_gallery\gallery-<D>\`.
- **Mặc định** (người làm được chỉnh, nhưng phải qua cổng): `GALLERY_K = 10`, `MIN_SHARE = 0.6`,
  `MIN_SIMILARITY = 0.5`, `MIN_SUPPORT = 3`. Biến môi trường `MILK_GALLERY_MIN_SHARE` và `MILK_GALLERY_MIN_SIM` ghi
  đè được.
- **Muốn đổi vị phải có ít nhất `MIN_SUPPORT` láng giềng mang vị đó.** Một vị mới có 1–2 lon trong kho không bao giờ
  được dùng để đổi vị.
- **Bật trên worker cần hoang đồng ý.** Tài khoản commit như phần 1.

## Review Focus

1. **Kho thiếu vị:** ví dụ Hot & Spicy mới có vài lon. Kho không được tự đổi vị sang vị đó khi phiếu ít. Test ở
   Task 1.
2. **Hộp rất nhỏ hoặc nằm sát mép khung:** cắt có lề vẫn phải nằm trong ảnh, và không ra ảnh rỗng. Test ở Task 3.
3. **Thư mục kho hỏng hoặc thiếu file:** worker phải dừng ngay lúc khởi động và báo rõ lỗi, không âm thầm chạy không có
   kho. Test ở Task 2.
4. **Hộp không phải Slide** (sữa, UNRECOGNIZED): không đối chiếu, giữ nguyên. Test ở Task 2.
5. **Cổng khi bản đang chạy đã có kho:** so với nhãn bản đang chạy đã ghi, và quyết định lại từ nhãn YOLO gốc. Test ở
   Task 4.

---

### Task 1: Bỏ phiếu và quyết định (`server/milk/gallery.py`)

**Files:**
- Create: `server/milk/gallery.py`, `tests/test_gallery.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Vote: label: str; share: float; similarity: float; margin_none: float; support:
    int`. `support` là số láng giềng mang `label`.
  - `class Gallery(vectors: np.ndarray, labels: list[str], meta: dict)`. `vectors` là mảng N×D, float32, đã chuẩn hoá
    L2.
    - `Gallery.load(folder: str) -> Gallery`: đọc `gallery.npz` (`vectors`, `labels`) và `gallery.json` (`meta`).
    - `save(folder: str) -> None`
    - `vote(vecs: np.ndarray, k: int = GALLERY_K) -> list[Vote]`
  - `decide(yolo_label: str, yolo_conf: float, vote: Vote, min_share: float = MIN_SHARE, min_similarity: float =
    MIN_SIMILARITY) -> tuple[str, float, str]`: trả `(nhãn, độ tin cậy, kết quả)`. Kết quả là `"agree"`,
    `"relabelled"` hoặc `"unsure"`.

- [ ] **Step 1: Viết test.** Dùng vector tổng hợp 4 chiều, mỗi nhãn một trục: `original145` = 0, `cheese145` = 1,
  `hot160` = 2, `none` = 3.

```python
def gal(per_label: dict[str, int]) -> Gallery:  # n copies of each label's axis, jittered by <= 0.02, L2-normalised
    ...


def test_vote_picks_the_flavour_with_most_similar_neighbours():
    v = gal({"original145": 8, "cheese145": 8, "none": 4}).vote(np.array([[1.0, 0.05, 0, 0]], np.float32))[0]
    assert v.label == "original145" and v.share > 0.6 and v.similarity > 0.9 and v.support == 8


def test_decide_relabels_only_when_sure():
    sure = Vote("original145", share=0.9, similarity=0.85, margin_none=0.3, support=6)
    assert decide("cheese145", 0.97, sure) == ("original145", 0.9, "relabelled")
    weak = Vote("original145", share=0.55, similarity=0.85, margin_none=0.3, support=6)
    assert decide("cheese145", 0.97, weak) == ("cheese145", 0.69, "unsure")


def test_decide_keeps_an_agreeing_box():
    assert decide("cheese145", 0.8, Vote("cheese145", 0.4, 0.6, 0.1, 2)) == ("cheese145", 0.8, "agree")


def test_background_like_box_is_unsure_not_relabelled():
    assert decide("hot160", 0.9, Vote("none", 0.8, 0.9, -0.2, 8)) == ("hot160", 0.69, "unsure")


def test_a_flavour_with_two_crops_cannot_relabel():
    v = gal({"hot160": 2, "original145": 12}).vote(np.array([[0.0, 0.0, 1.0, 0.0]], np.float32))[0]
    assert (v.label, v.support) == ("hot160", 2)
    assert decide("original145", 0.9, v) == ("original145", 0.69, "unsure")


def test_save_and_load_round_trip(tmp_path):
    g = gal({"cheese145": 3})
    g.save(str(tmp_path))
    assert Gallery.load(str(tmp_path)).labels == g.labels
```

- [ ] **Step 2: Chạy test, phải FAIL.** Lệnh: `python -m pytest tests/test_gallery.py -q`.
- [ ] **Step 3: Viết code.**
  - `vote` làm như `Recognizer.lookup` của `carton_recognition/recognize.py`:
    1. Tìm k láng giềng gần nhất theo cosine.
    2. Mỗi láng giềng bỏ phiếu bằng `max(sim, 0)`.
    3. `label` là nhãn khác `none` có tổng phiếu lớn nhất. Mọi láng giềng đều là `none` thì `label = "none"`.
    4. `share` = phiếu của `label` ÷ tổng phiếu.
    5. `similarity` = độ giống lớn nhất trong các láng giềng mang `label`.
    6. `margin_none` = `similarity` − độ giống lớn nhất của láng giềng `none` (không có láng giềng `none` thì bằng
       `similarity`).
    7. `support` = số láng giềng mang `label`.
  - `decide`:
    - `vote.label == yolo_label` → `"agree"`, giữ nguyên nhãn và độ tin cậy.
    - Nhãn khác, khác `none`, `share ≥ min_share`, `similarity ≥ min_similarity`, `margin_none > 0` và `support ≥
      MIN_SUPPORT` → `"relabelled"`, độ tin cậy là `round(vote.share, 3)`.
    - Mọi trường hợp còn lại → `"unsure"`, giữ nhãn YOLO, độ tin cậy là `min(yolo_conf, 0.69)`.
- [ ] **Step 4: Chạy lại test.** Mong đợi: PASS.
- [ ] **Step 5:** Commit `Gallery: vote and decide for Slide boxes (pure numpy)`.

### Task 2: Worker dùng kho, và mỗi hộp ghi nhãn YOLO gốc

**Files:**
- Modify: `server/milk/cvoutput.py` (`Detection`, `persist_record`)
- Modify: `server/milk/slide_adapter.py`, `server/milk/counter.py` (mục `detections` của `meta`)
- Modify: `backend/model_health.py` (`capture_boxes`)
- Test: `tests/test_pipeline.py`, `tests/test_cvoutput.py`, `tests/test_model_health.py`

**Interfaces:**
- Consumes: `Gallery`, `Vote`, `decide` (Task 1).
- Produces:
  - `Detection.extra: dict | None = field(default=None, compare=False, hash=False)`.
  - `slide_adapter.apply_votes(dets: list[Detection], votes: list[Vote], product: dict[str, str]) -> list[Detection]`:
    - mỗi hộp mang `extra = {"yolo_sku_id", "gallery_label", "gallery_share", "gallery_outcome"}`;
    - hộp được đổi vị thì `sku_name` lấy theo `product`.
  - `SlidePipeline` đọc `MILK_SLIDE_GALLERY`:
    - có biến thì nạp `Gallery.load` và embedder của `carton_recognition`. Loại embedder đọc từ `meta["embedder"]`:
      `"brand"` hoặc `"types"`;
    - thư mục thiếu `gallery.npz` hoặc `gallery.json` thì báo `FileNotFoundError` ngay khi khởi động.
  - `persist_record` và `meta.detections` của worker chép các khoá trong `extra` vào từng hộp.
  - `model_health.capture_boxes` giữ `yolo_sku_id` khi hộp có trường này.

- [ ] **Step 1: Viết test.**
  - `test_apply_votes_relabels_and_records_the_yolo_label`: hộp `cheese145`, phiếu chắc chắn cho `original145`. Kết
    quả: `sku_id == "original145"`, `sku_name` là tên Nguyên bản trong `skus.json`, `extra["yolo_sku_id"] ==
    "cheese145"`, `extra["gallery_outcome"] == "relabelled"`.
  - `test_apply_votes_lowers_an_unsure_box`: kết quả có `confidence == 0.69` và giữ nhãn.
  - `test_slide_pipeline_without_the_gallery_is_unchanged`: không đặt biến thì `to_detections` ra đúng như trước, và
    mọi `extra` đều là `None`.
  - `test_a_broken_gallery_folder_stops_the_worker`: thư mục rỗng thì `Gallery.load` báo `FileNotFoundError`.
  - `test_only_slide_boxes_are_checked`: `CombinedPipeline` với phần sữa giả. Hộp `TMP-MLK-*` và hộp UNRECOGNIZED
    không có `extra`.
  - `test_persist_record_keeps_gallery_fields`: `persist_record(...)["detections"][0]["yolo_sku_id"] == "cheese145"`.
  - `test_capture_boxes_keep_the_yolo_label`: item có `detections_json` mang `yolo_sku_id` thì giữ trường đó.
- [ ] **Step 2: Chạy test, phải FAIL.**
- [ ] **Step 3: Viết code.**
  - `SlidePipeline.detect`:
    1. Chạy YOLO rồi `to_detections` như cũ.
    2. Có kho thì cắt từng hộp bằng `crop_box(image, (x0, y0, x1, y1), margin=0.06)` của `carton_recognition/embedder.py`.
    3. Embed các lon cắt ra, chuẩn hoá L2, rồi `gallery.vote` và `apply_votes`.
- [ ] **Step 4: Chạy test**, cùng các test cũ của pipeline, cvoutput và model_health. Mong đợi: PASS.
- [ ] **Step 5:** Commit `Worker: re-check Slide boxes against the real-crop gallery when MILK_SLIDE_GALLERY is set`.

### Task 3: Xuất lon cắt ra (laptop)

**Files:**
- Create: `scripts/export_audit_crops.py`, `tests/test_export_audit_crops.py`

**Interfaces:**
- Produces:
  - `crop_label(box: dict, verdict: dict) -> str | None`: theo bảng ở Global Constraints.
  - `crop_xyxy(box: list[int], width: int, height: int, margin: float = 0.06) -> tuple[int, int, int, int]`: hộp x, y,
    w, h cộng lề, cắt cho nằm trong ảnh. Kết quả luôn rộng và cao ít nhất 1 pixel.
  - `select_audits(items: list[dict], purpose: str, before: str | None, since: str | None) -> list[dict]`:
    - `purpose = "training"`: chỉ lấy mã `TRN-`, chụp trước `before`. Gặp mã `AUD-` trong danh sách đã lọc thì báo
      `ValueError`;
    - `purpose = "scoring"`: chỉ lấy mã `AUD-`, chụp từ `since`;
    - cả hai chỉ lấy `status == "done"`.
  - Dòng lệnh: `python scripts/export_audit_crops.py --purpose training --before 20261128 --out <thư mục>`.
    - Ghi `crops/<audit_id>-<box_id>.jpg`.
    - Ghi `manifest.jsonl`, mỗi lon một dòng `{audit_id, box_id, label, model_label, yolo_label, conf,
      capture_timestamp, period, file}`.
    - Ghi `audits.jsonl`, mỗi khung một dòng `{audit_id, capture_timestamp, ai_boxes, verdicts, missed}`, để cổng dựng
      lại khung.

- [ ] **Step 1: Viết test**, không gọi AWS.
  - `crop_label` đúng từng dòng của bảng.
  - `crop_xyxy([0, 0, 10, 10], 100, 100)` bắt đầu ở `(0, 0)`.
  - Hộp sát mép phải dưới không vượt ra ngoài ảnh.
  - `select_audits(..., "training", "20261128", None)` bỏ khung chụp ngày 28/11. Danh sách lẫn mã `AUD-` thì báo lỗi
    như Interfaces.
- [ ] **Step 2: Chạy test, phải FAIL.**
- [ ] **Step 3: Viết code.**
  - Đọc bảng `audits` và ảnh trong bucket analytics bằng profile `default`.
  - Ghi ra thư mục nằm ngoài repo.
  - Script từ chối `--out` nằm trong repo.
- [ ] **Step 4: Chạy lại test.** Mong đợi: PASS.
- [ ] **Step 5:** Commit `Scripts: export labelled crops (training before the cut-off, scoring from it)`.

### Task 4: Dựng kho và cổng (HUYHOANG)

**Files:**
- Create: `scripts/build_slide_gallery.py`, `scripts/gallery_gate.py`, `tests/test_gallery_gate.py`

**Interfaces:**
- Consumes:
  - `Gallery`, `decide` (Task 1);
  - `manifest.jsonl` và `audits.jsonl` (Task 3);
  - `audit_scoring.summarize` (`backend/`, nạp qua `sys.path`).
- Produces:
  - `build_slide_gallery.py --manifest <training>/manifest.jsonl --cutoff 20261128 --embedder types|brand --out <thư
    mục kho>`:
    - ghi `gallery.npz`;
    - ghi `gallery.json` gồm `{version, cutoff, embedder, n_per_label, built_at}`;
    - từ chối khi manifest có mã `AUD-`.
  - `gallery_gate.relabel(audit: dict, new_labels: dict[int, str]) -> dict`: dựng lại verdict của khung theo nhãn
    mới, so với nhãn thật của lon:
    - nhãn thật `none` → `not_product`;
    - nhãn mới trùng nhãn thật → `correct`;
    - còn lại → `wrong_sku` kèm `true_sku_id`.

    Điểm sót và hộp `out_of_scope` giữ nguyên.
  - `gallery_gate.gate_decision(old: dict, new: dict, frames: int, days: int, periods: set[str]) -> tuple[bool,
    list[str]]`. `old` và `new` là kết quả `summarize`. Trả đạt hay không, và danh sách lý do không đạt.
  - `gallery_gate.py --scoring <thư mục scoring> --gallery <thư mục kho> --out <thư mục báo cáo>`:
    - ghi `report.json` và `report.md`: bảng theo SKU của bản đang chạy và bản mới, KPI #1/#2, kết luận;
    - thoát với mã 0 khi đạt, 1 khi không đạt.

    "Bản đang chạy" là `model_label` (nhãn hệ thống đã ghi). Nhãn mới là `decide(yolo_label or model_label, conf,
    vote)`.

- [ ] **Step 1: Viết test.** Kết quả `summarize` dựng tay.

```python
def test_the_gate_passes_a_clear_improvement():
    ok, reasons = gate_decision(OLD, NEW_GOOD, frames=32, days=2, periods={"morning", "afternoon", "evening"})
    assert ok and reasons == []


def test_the_gate_names_every_reason_it_fails():
    _, reasons = gate_decision(OLD, NEW_GOOD, frames=29, days=1, periods={"morning"})
    assert {r.split(":")[0] for r in reasons} == {"frames", "days", "periods"}
    _, reasons = gate_decision(OLD, NEW_ORIGINAL_STILL_LOW, 32, 2, {"morning", "afternoon", "evening"})
    assert reasons == ["original145: found right 0.55 < 0.70"]
    _, reasons = gate_decision(OLD, NEW_SOUR_CREAM_DROPS, 32, 2, {"morning", "afternoon", "evening"})
    assert reasons == ["sourcream150: found right fell 0.97 -> 0.90"]


def test_relabel_rebuilds_verdicts_from_the_true_labels():
    ...  # one box truly original145 that the new gallery calls original145 becomes "correct"; a box truly none
    # becomes "not_product"; missed points and out_of_scope boxes are kept as they were
```

- [ ] **Step 2: Chạy test, phải FAIL.**
- [ ] **Step 3: Viết hai script.**
  - Embedder nạp từ `carton_recognition` (đường dẫn `MILK_LONG_DIR`), giống Task 2.
  - Lon cắt ra đã có sẵn, nên script không chạy YOLO.
- [ ] **Step 4: Chạy lại test.** Mong đợi: PASS.
- [ ] **Step 5:** Commit `Scripts: build the Slide gallery and gate it on scoring frames after the cut-off`.

### Task 5: Theo dõi trên trang Model và bật kho (lần đầu)

**Files:**
- Modify: `backend/model_health.py` (`hour_stats`), `frontend/lib/health-ui.ts`
- Create: `scripts/mark_used_in_gallery.py`
- Test: `tests/test_model_health.py`, `frontend/lib/health-ui.test.ts`

**Interfaces:**
- Produces:
  - `hour_stats(...)` có thêm `gallery_changed_pct`: số hộp có `yolo_sku_id` khác `sku_id` ÷ số hộp có `yolo_sku_id`.
    Không có hộp nào có `yolo_sku_id` thì trường này là `None`.
  - Live health có dòng "Gallery changed the flavour".
  - `mark_used_in_gallery.py --version gallery-<D> --manifest <training>/manifest.jsonl`:
    - đặt `used_in_gallery = <version>` trên các khung dạy có trong manifest;
    - từ chối mã `AUD-`.

- [ ] **Step 1: Viết test.**
  - `hour_stats` trên 1 capture có 4 hộp mang `yolo_sku_id`, trong đó 1 hộp bị đổi vị → `gallery_changed_pct ==
    0.25`.
  - Không có hộp nào mang trường này → `None`.
  - Test node cho cách hiện dòng mới.
- [ ] **Step 2: Chạy test, phải FAIL. Viết code. Chạy lại, phải PASS.** Commit `Model page: share of Slide boxes the
  gallery relabelled`.
- [ ] **Step 3: Chạy lần đầu.** Bắt đầu khi đủ 30 khung dạy `done`, trải đủ sáng, chiều và tối.
  1. Chọn ngày cắt D. Trên laptop, xuất khung dạy chụp trước D.
  2. Chép thư mục xuất sang HUYHOANG bằng `scp` qua Tailscale.
  3. Dựng kho 2 lần, một lần với `--embedder types` và một lần với `--embedder brand`.
- [ ] **Step 4:** Khi có đủ khung chấm điểm từ ngày D trở đi (30 khung, 2 ngày, 3 buổi), xuất chúng ra. Chạy cổng cho
  từng kho, rồi chọn kho đạt và có "found right" của Nguyên bản cao hơn. Không kho nào đạt thì báo hoang kèm báo cáo,
  và không bật.
- [ ] **Step 5 (cần hoang đồng ý):** Bật kho trên worker.
  1. Sao lưu `worker.env`.
  2. Đặt `MILK_SLIDE_GALLERY=C:/Users/huyho/Datagent/slide_gallery/gallery-<D>` và
     `MILK_MODEL_VERSION=long-2026-10-13+slide-v3+gallery-<D>`.
  3. Khởi động lại task `milk-worker`.
  4. Kiểm `results/*.json` mới có `yolo_sku_id`, và Live health hiện tỉ lệ đổi vị.
- [ ] **Step 6:** Chạy `mark_used_in_gallery.py`. Ghi Nhật ký HOANG-P10 kèm báo cáo cổng. Cập nhật memory.
  - Lần cập nhật kế tiếp sau 3–4 ngày, làm lại từ Step 3 với ngày cắt mới (spec mục 2.4).
  - Cổng của các lần sau so với bản kho đang chạy.
