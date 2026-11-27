# Đường đọc chung, giai đoạn 1: TH đọc được khi tiệm xếp lại lốc — kế hoạch làm

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Worker đếm được hộp TH cả ở kiểu xếp chưa có trong ảnh dạy, bằng cách thôi cho database gạt box của lớp
`th_true_milk`, và có số đo trên ảnh chưa ai nhìn trước khi bật.

**Architecture:**
- **Repo:** `long_adapter.py` nhận biến `MILK_LONG_TH_CONFIRM`. Ở chế độ `detector`, box lớp gộp `th_true_milk` không
  được gửi sang database và lấy điểm của YOLO. Mọi lớp khác đi đường cũ.
- **Đo:** `evaluate.py` nhận thêm cửa sổ thời gian và đếm riêng frame lúc tủ đã cất.
- **Laptop** (có quyền AWS) gom frame mới và Claude vẽ đáp án. **HUYHOANG** (GPU) chạy phép đo.
- Lên live là task cuối, chỉ làm khi hoang OK.

**Tech Stack:** Python 3.12, numpy, pytest, ruff. ultralytics, lancedb và code của Long trên HUYHOANG. boto3 trên
laptop.

**Spec:** `docs/superpowers/specs/2026-11-26-common-read-path-design.md` (hoang duyệt 26/11), mục 5.2, 5.6 và giai
đoạn 1 của mục 5.7. Giai đoạn 2 (gộp cửa sổ, kho ảnh màu Slide) có kế hoạch riêng, viết sau khi Task 1–3 xong.

## Global Constraints

- **Biến mới:** `MILK_LONG_TH_CONFIRM`, giá trị `database` (mặc định, y hệt hiện nay) hoặc `detector`.
- **Chỉ lớp gộp `th_true_milk`** đổi cách đọc. Các lớp Vinamilk và hai lớp TH cũ của `best_types.pt` vẫn qua database.
- **Ở chế độ `detector`:** nhãn `TMP-MLK-TH-00`, `unit_score` bằng độ tin cậy của YOLO.
- **Không thêm luật bỏ box trùng.** `one_box_per_unit` giữ nguyên.
- **Worker tiếp tục đọc database v1** (`carton_recognition`). `MILK_LONG_DIR` không đổi. Database v2 không lên live.
- **Cổng TH** (mục 5.4 của thiết kế TH), tính theo frame và theo đoạn:

  | Chỉ số | Ngưỡng |
  |---|---|
  | recall | ≥ 0,85 |
  | precision | ≥ 0,90 |
  | frame có TH đếm lệch ≤ 1 | ≥ 80% |
  | box sữa trên frame không có TH | ≤ 1 / 100 frame |
  | box Slide | giống hệt bản đang chạy |

- **Đáp án của ảnh mới** do Claude vẽ tay từ ảnh phóng to. Không dùng box nháp của detector.
- **Ảnh mới** là frame từ `2026-11-25T13:00:00+07:00` trở đi. Bản gom hiện có dừng ở đó.
- **Tập giữ riêng** không bao giờ dùng để train, nạp kho hay chỉnh ngưỡng. Frame AUD cũng vậy.
- **Không ghi đè file worker đang đọc.** Không cài gì vào `C:\Users\huyho\Datagent\.venv`.
- **Trên Windows:** `import torch` trước cv2, ssl và lancedb.
- **Ảnh, nhãn và báo cáo đo** không vào repo, không vào OneDrive.
- **Lệnh trên HUYHOANG:** cmd.exe từ chối lệnh dài hơn 8191 ký tự. Script dài thì scp file `.ps1` sang rồi chạy
  `powershell -NoProfile -ExecutionPolicy Bypass -File`.
- **`worker.env` không bao giờ được in ra.**
- **Mọi bước lên live chờ hoang OK.** Quay lui: xoá biến mới khỏi `worker.env`, khởi động lại task `milk-worker`.
- **Test:** `PYTEST` =
  `C:\Users\huyho\AppData\Local\Temp\claude\cf23e0181d28b9db\60a1e66e-e64a-44a1-b0a1-d67403b3c1db\scratchpad\venv312\Scripts\python.exe -m pytest -q -p no:cacheprovider`.
  Nếu venv đó mất thì dùng venv py3.12 nào có `requirements-dev.txt` và `opencv-python`. Cả bộ test phải xanh; `ruff
  check .` và `ruff format --check .` sạch.
- **Nhánh:** `feat/common-read-path`. Commit có dòng Co-Authored-By ở cuối.

## Review Focus

1. **`MILK_LONG_TH_CONFIRM` gõ sai hoặc dính ký tự xuống dòng** (`worker.env` có dòng CRLF): khoảng trắng và chữ hoa
   được bỏ qua; giá trị lạ làm worker dừng ngay lúc khởi động với lỗi nêu tên biến, không lặng lẽ chạy theo
   `database`. Test ở Task 1.
2. **Frame chỉ có box TH:** database không được gọi lần nào và không lỗi. Test ở Task 1.
3. **Frame có cả TH lẫn Vinamilk:** box Vinamilk vẫn sang database, và kết quả giữ thứ tự của detector. Test ở Task 1.
4. **Đặt `detector` nhưng vẫn chạy model cũ 12 lớp:** kết quả y như `database`, vì lớp cũ không phải lớp gộp. Test ở
   Task 1.
5. **Phép đo chạy hai pipeline liền nhau:** pipeline "current" không được thừa hưởng `MILK_LONG_TH_CONFIRM` của
   pipeline "new". Test ở Task 2.

---

### Task 1: Biến `MILK_LONG_TH_CONFIRM` trong adapter

**Files:**
- Modify: `server/milk/long_adapter.py`
- Test: `tests/test_long_adapter.py`

**Interfaces:**
- Produces:
  - `_th_confirm() -> str`: đọc `MILK_LONG_TH_CONFIRM`, trả `"database"` hoặc `"detector"`.
  - `needs_lookup(cls_name: str, variants: bool, th_confirm: str) -> bool`.
  - `decide(cls_name, yolo_conf, brand, kind_share, variants, th_confirm: str = "database") -> tuple[str | None, float]`.
  - `readings(rows, names, lookups, shares, product, variants, th_confirm: str = "database") -> list[Detection]`.
  - `LongPipeline` đọc biến một lần trong `__init__` và giữ ở `self._th_confirm`.

- [ ] **Step 1: Viết test** (thêm vào `tests/test_long_adapter.py`; import thêm `LongPipeline`, `_th_confirm`,
  `needs_lookup`)

```python
def test_th_confirm_setting(monkeypatch):
    monkeypatch.delenv("MILK_LONG_TH_CONFIRM", raising=False)
    assert _th_confirm() == "database"
    for raw, want in (
        ("", "database"),
        ("detector", "detector"),
        (" Detector\r", "detector"),
        ("DATABASE", "database"),
    ):
        monkeypatch.setenv("MILK_LONG_TH_CONFIRM", raw)
        assert _th_confirm() == want


def test_a_misspelt_th_confirm_stops_the_worker(monkeypatch):
    monkeypatch.setenv("MILK_LONG_TH_CONFIRM", "detecter")
    with pytest.raises(ValueError, match="MILK_LONG_TH_CONFIRM"):
        _th_confirm()


def test_only_merged_th_boxes_skip_the_database():
    assert needs_lookup("th_true_milk", False, "detector") is False
    assert needs_lookup("th_true_milk", True, "detector") is True  # variants: the database names the type
    assert needs_lookup("th_true_milk", False, "database") is True
    assert needs_lookup("vinamilk_soy", False, "detector") is True
    assert needs_lookup("th_true_milk_sweetened", False, "detector") is True  # the old 12-class model


def test_detector_confirm_keeps_a_th_box_the_database_rejects():
    assert decide("th_true_milk", 0.83, "unknown", {}, False, "detector") == ("TMP-MLK-TH-00", pytest.approx(0.83))
    share = {"th_true_milk": 0.5, "vinamilk_soy": 0.5}
    assert decide("th_true_milk", 0.8, "th_true_milk", share, False, "detector") == (
        "TMP-MLK-TH-00",
        pytest.approx(0.8),
    )


def test_detector_confirm_leaves_every_other_class_to_the_database():
    for cls in ("th_true_milk_sweetened", "vinamilk_soy"):
        assert decide(cls, 0.9, "unknown", {cls: 1.0}, False, "detector") == (None, 0.0)
    share = {"vinamilk_soy": 0.5, "vinamilk_melon": 0.5}
    assert decide("vinamilk_soy", 0.8, "vinamilk", share, False, "detector") == ("TMP-MLK-VNM-07", pytest.approx(0.4))
    assert decide("th_true_milk_sweetened", 0.9, "vinamilk", {"vinamilk_soy": 1.0}, False, "detector") == (
        "TMP-MLK-TH-01",
        0.0,
    )


def test_detector_confirm_with_variants_names_but_never_rejects():
    lead = {"th_true_milk_sweetened": 0.8, "th_true_milk_less_sugar": 0.2}
    assert decide("th_true_milk", 0.9, "th_true_milk", lead, True, "detector") == ("TMP-MLK-TH-01", pytest.approx(0.9))
    assert decide("th_true_milk", 0.9, "unknown", lead, True, "detector") == ("TMP-MLK-TH-00", pytest.approx(0.9))


def test_readings_pass_the_confirm_mode_on():
    rows = np.array([[100.2, 50.0, 140.4, 110.0, 0.9, 0, 0], [300.0, 50.0, 330.0, 110.0, 0.7, 2, 1]])
    names = {0: "th_true_milk", 2: "vinamilk_soy"}
    lookups = [{"brand": "unknown"}, {"brand": "unknown"}]
    out = readings(rows, names, lookups, [{}, {"vinamilk_soy": 1.0}], {"TMP-MLK-TH-00": "TH gộp"}, False, "detector")
    assert out == [
        Detection("TMP-MLK-TH-00", "TH gộp", pytest.approx(0.9), (100, 50, 40, 60)),
        Detection(None, None, 0.0, (300, 50, 30, 60)),
    ]


ROWS = np.array([[100.0, 50.0, 140.0, 110.0, 0.9, 0, 0], [300.0, 50.0, 330.0, 110.0, 0.7, 2, 0]])  # TH, Vinamilk


def _pipeline_with_fakes(rows, th_confirm, variants=False):
    """A LongPipeline around stand-ins for the detector, the embedder and the database; calls["crops"] counts the
    crops sent to the database."""
    calls = {"crops": 0}

    class Embedder:
        device = "cpu"

        def embed(self, crops):
            calls["crops"] += len(crops)
            return np.zeros((len(crops), 4), np.float32)

    class Rec:
        embedder = Embedder()

        def lookup(self, vectors):
            return [{"brand": "vinamilk"} for _ in vectors]

    class Cvo:
        detect = staticmethod(lambda image, yolo, device, conf, imgsz, tile=0: rows)
        one_box_per_unit = staticmethod(lambda det: det)
        crop_box = staticmethod(lambda image, box: np.zeros((2, 2, 3), np.uint8))
        type_support = staticmethod(lambda rec, vectors: [{"vinamilk_soy": 1.0} for _ in vectors])

    class Yolo:
        names = {0: "th_true_milk", 2: "vinamilk_soy"}

    pipe = object.__new__(LongPipeline)
    pipe._cvo, pipe._rec, pipe._yolo, pipe._product = Cvo, Rec(), Yolo(), {}
    pipe._conf, pipe._imgsz, pipe._tile, pipe._variants, pipe._th_confirm = 0.25, 1280, 0, variants, th_confirm
    return pipe, calls


FRAME = np.zeros((8, 8, 3), np.uint8)


def test_detector_mode_sends_only_other_classes_to_the_database():
    pipe, calls = _pipeline_with_fakes(ROWS, "detector")
    out = pipe.detect(FRAME)
    assert calls["crops"] == 1
    assert [(d.sku_id, d.confidence) for d in out] == [
        ("TMP-MLK-TH-00", pytest.approx(0.9)),
        ("TMP-MLK-VNM-07", pytest.approx(0.7)),
    ]


def test_a_frame_of_only_th_boxes_never_calls_the_database():
    pipe, calls = _pipeline_with_fakes(ROWS[:1], "detector")
    assert [d.sku_id for d in pipe.detect(FRAME)] == ["TMP-MLK-TH-00"]
    assert calls["crops"] == 0


def test_database_mode_still_sends_every_box():
    pipe, calls = _pipeline_with_fakes(ROWS, "database")
    pipe.detect(FRAME)
    assert calls["crops"] == 2


def test_detector_mode_with_variants_asks_the_database_for_the_name():
    pipe, calls = _pipeline_with_fakes(ROWS[:1], "detector", variants=True)
    assert [d.sku_id for d in pipe.detect(FRAME)] == ["TMP-MLK-TH-00"]
    assert calls["crops"] == 1
```

- [ ] **Step 2: Chạy test, phải FAIL**

Run: `PYTEST tests/test_long_adapter.py`
Expected: FAIL khi import, vì chưa có `_th_confirm`, `needs_lookup`.

- [ ] **Step 3: Viết code trong `server/milk/long_adapter.py`**

  - `_th_confirm()`: bỏ khoảng trắng hai đầu và đổi về chữ thường. Rỗng hoặc không đặt thì `"database"`. Giá trị khác
    hai giá trị hợp lệ thì `raise ValueError` với câu có tên biến và giá trị nhận được.
  - `needs_lookup`: chỉ trả `False` khi `cls_name == TH_BRAND`, `th_confirm == "detector"` và `variants` là `False`.
  - `decide`, khi `cls_name == TH_BRAND` và `th_confirm == "detector"`:
    - không bao giờ trả `(None, 0.0)`;
    - điểm là `round(yolo_conf, 3)`;
    - nhãn là `TMP-MLK-TH-00`, trừ khi `variants` bật, `brand != "unknown"` và một loại dẫn đủ `VARIANT_SHARE` theo
      đúng luật hiện có.
  - `LongPipeline.detect`: chỉ cắt ảnh, embed và hỏi database cho các dòng mà `needs_lookup` trả `True`. Các dòng còn
    lại nhận `{"brand": "unknown"}` và `{}`. Thứ tự dòng giữ nguyên. Không có dòng nào cần hỏi thì không gọi `embed`.
  - Thêm biến vào docstring đầu file, cùng kiểu với các biến khác.

- [ ] **Step 4: Chạy test, phải PASS**

Run: `PYTEST tests/test_long_adapter.py`, rồi `PYTEST tests`, `ruff check .`, `ruff format --check .`
Expected: PASS và sạch. Các test cũ của file không đổi một dòng nào.

- [ ] **Step 5: Commit**

```bash
git add server/milk/long_adapter.py tests/test_long_adapter.py
git commit -m "Milk adapter: MILK_LONG_TH_CONFIRM=detector keeps merged TH boxes without asking the database"
```

### Task 2: Phép đo nhận cửa sổ thời gian và đếm frame lúc tủ đã cất

**Files:**
- Modify: `training/store_view/evaluate.py`
- Test: `tests/test_store_view_evaluate.py`

**Interfaces:**
- Consumes: biến `MILK_LONG_TH_CONFIRM` (Task 1).
- Produces:
  - `LONG_KEYS: tuple[str, ...]`: năm biến `MILK_LONG_DIR`, `MILK_LONG_YOLO`, `MILK_LONG_TILE`, `MILK_LONG_VARIANTS`,
    `MILK_LONG_TH_CONFIRM`.
  - `apply_env(base: dict[str, str], overrides: dict[str, str]) -> None`: xoá `LONG_KEYS` khỏi `os.environ`, đặt các
    biến `MILK_*` của `base`, rồi đặt `overrides`. `_pipeline` gọi hàm này.
  - `in_window(first_ts: str, since: str | None) -> bool`.
  - `night(results: list[dict]) -> dict`: `{"frames", "milk_boxes", "per_100"}` trên các dòng có `kind == "negative"`.
  - CLI `run` nhận thêm `--since <ISO có múi giờ>`.
  - File báo cáo có thêm `"since"`, `"settings": {"new": ..., "current": ...}`, `"night"`; mỗi dòng của `"frames"` có
    thêm `"kind"`.

- [ ] **Step 1: Viết test**

```python
def test_the_current_pipeline_does_not_inherit_the_new_ones_settings(monkeypatch):
    # every variable is set through monkeypatch first, so pytest restores it after apply_env changed it
    monkeypatch.setenv("MILK_LONG_TH_CONFIRM", "detector")
    monkeypatch.setenv("MILK_LONG_TILE", "1280")
    monkeypatch.setenv("MILK_SLIDE_CONF", "0.9")
    monkeypatch.delenv("NOT_A_MILK_SETTING", raising=False)
    apply_env({"MILK_SLIDE_CONF": "0.25", "NOT_A_MILK_SETTING": "x"}, {"MILK_LONG_TILE": "0"})
    assert "MILK_LONG_TH_CONFIRM" not in os.environ
    assert os.environ["MILK_LONG_TILE"] == "0" and os.environ["MILK_SLIDE_CONF"] == "0.25"
    assert "NOT_A_MILK_SETTING" not in os.environ


def test_since_keeps_segments_that_start_at_or_after_it():
    since = "2026-11-25T13:00:00+07:00"
    assert in_window("2026-11-25T13:00:00+07:00", since) and in_window("2026-11-26T06:00:00+07:00", since)
    assert not in_window("2026-11-25T12:59:59+07:00", since)
    assert in_window("2026-11-23T18:00:00+07:00", None)


def test_night_counts_milk_boxes_on_frames_without_the_display():
    rows = [{"kind": "negative", "milk": 0}] * 199 + [{"kind": "negative", "milk": 2}, {"kind": "day", "milk": 5}]
    assert night(rows) == {"frames": 200, "milk_boxes": 2, "per_100": 1.0}


def test_night_without_frames_is_not_measured():
    assert night([{"kind": "day", "milk": 1}]) == {"frames": 0, "milk_boxes": 0, "per_100": None}
```

  File test cần thêm `import os` và import `apply_env`, `in_window`, `night`.

- [ ] **Step 2: Chạy test, phải FAIL**

Run: `PYTEST tests/test_store_view_evaluate.py`
Expected: FAIL khi import.

- [ ] **Step 3: Viết code**

  - `in_window` so sánh bằng `datetime.fromisoformat`, không so chuỗi.
  - `run` bỏ qua đoạn có `first_ts` trước `--since`.
  - `run` ghi `kind` của đoạn vào từng dòng kết quả, và in một dòng:
    `night frames <n>  milk boxes <m>  per 100 <x>`.
  - `"settings"` chỉ ghi chuỗi `--new` và `--current`. Không ghi gì đọc từ `--env-file`.

- [ ] **Step 4: Chạy test, phải PASS**

Run: `PYTEST tests/test_store_view_evaluate.py`, rồi `PYTEST tests`, `ruff check .`, `ruff format --check .`
Expected: PASS và sạch.

- [ ] **Step 5: Commit**

```bash
git add training/store_view/evaluate.py tests/test_store_view_evaluate.py
git commit -m "Store-view evaluate: a --since window, night frames counted apart, settings kept apart between runs"
```

### Task 3: Ngày 26/11 thành tập giữ riêng cho tới khi hoang quyết

**Files:**
- Modify: `training/store_view/segments.py` (`HOLDOUT` và chú thích phía trên nó)
- Test: `tests/test_store_view_segments.py`

**Interfaces:**
- Produces: `HOLDOUT` có thêm cửa sổ thứ ba `("2026-11-26T00:00:00+07:00", "2026-11-27T00:00:00+07:00")`. Task 6 gỡ nó.

- [ ] **Step 1: Sửa test.** Thay `test_frames_from_26_11_are_for_training_again` bằng:

```python
def test_26_11_is_held_out_until_the_th_decision():
    # design 2026-11-26 (5.6): 26/11 is the day nobody has looked at; the window is removed after hoang decides
    assert holdout("2026-11-25T23:59:59+07:00") and holdout("2026-11-26T10:00:00+07:00")
    assert not holdout("2026-11-27T00:00:00+07:00") and not holdout("2026-11-27T09:00:00+07:00")
```

- [ ] **Step 2: Chạy test, phải FAIL**

Run: `PYTEST tests/test_store_view_segments.py`
Expected: FAIL ở `holdout("2026-11-26T10:00:00+07:00")`.

- [ ] **Step 3: Thêm cửa sổ vào `HOLDOUT`**, và ghi vào chú thích rằng cửa sổ 26/11 là tạm, theo mục 5.6 của thiết kế
  26/11.

- [ ] **Step 4: Chạy test, phải PASS**

Run: `PYTEST tests`, `ruff check .`, `ruff format --check .`
Expected: PASS và sạch.

- [ ] **Step 5: Commit**

```bash
git add training/store_view/segments.py tests/test_store_view_segments.py
git commit -m "Store-view: 26/11 is held out until the TH decision (design 2026-11-26, 5.6)"
```

### Task 4: Gom ảnh mới và vẽ đáp án

Không có code mới. Chạy trên laptop bằng python của `PYTEST`, trong thư mục repo. Nên chạy sau 21:00 ngày 26/11 để có
trọn ngày bày hàng. Chạy sớm hơn thì ghi giờ cắt vào báo cáo ở Task 5.

**Interfaces:**
- Consumes: `HOLDOUT` mới (Task 3).
- Produces, trên cả laptop (`C:\Users\huyho\milk_store_frames\CAM-S01-A`, `C:\Users\huyho\milk_store_labels`) và
  HUYHOANG (`C:\Users\huyho\Datagent\store_frames\CAM-S01-A`, `store_labels`):
  - frame và `manifest.jsonl` tới giờ gom;
  - `segments_20261125.json`: bản `segments.json` cũ, giữ nguyên, để Task 5 chạy lại đúng 594 frame cũ;
  - `segments.json`, `keyframes.json` và `yolo\` mới.

- [ ] **Step 1: Sao lưu.** Trên cả hai máy: chép `segments.json` thành `segments_20261125.json`, `keyframes.json` thành
  `keyframes.json.bak-20261126`, và thư mục `yolo` thành `yolo.bak-20261126`.

- [ ] **Step 2: Gom frame**

Run: `python -m training.store_view.harvest --camera CAM-S01-A --first 2026-11-22 --last 2026-11-26 --out C:\Users\huyho\milk_store_frames`
Expected: số frame lớn hơn 8.391; số dòng `manifest.jsonl` bằng số file ảnh; có thư mục `2026-11-26`.

- [ ] **Step 3: Chia đoạn lại**

Run: `python -m training.store_view.segments --frames C:\Users\huyho\milk_store_frames\CAM-S01-A --region 760,0,1200,320 --out C:\Users\huyho\milk_store_labels\segments.json`
Expected: in số đoạn theo ngày, có ngày 25/11 và 26/11 ở `holdout`.

Rồi so với `segments_20261125.json`: mọi đoạn cũ có `last_ts` trước `2026-11-25T12:00` phải giữ nguyên `id`,
`keyframe` và `members`. Đoạn cuối của bản cũ được phép dài thêm. Có khác biệt nào khác thì dừng và tìm nguyên nhân
trước khi làm tiếp.

- [ ] **Step 4: Vẽ đáp án cho keyframe mới**

  - Chạy `python -m training.store_view.labels zoom --frames … --segments … --out C:\Users\huyho\milk_store_labels\zoom --split holdout`.
  - Claude xem ảnh phóng to của từng keyframe đoạn `day` có `first_ts` từ `2026-11-25T13:00:00+07:00`, và ghi vào
    `keyframes.json`: `boxes`, `packs`, `arrangement`.
  - Luật vẽ như mục 5.1 của thiết kế TH: một khung cho mỗi hộp TH lộ mặt trước hoặc nắp, đủ để biết đó là hộp TH.
  - Tên `arrangement`: dùng lại tên cũ (`E2`, …) nếu lốc nằm đúng kiểu cũ, ngược lại đặt tên mới `F0`, `F1`, ….
    Keyframe không có lốc ghi `empty`.
  - Keyframe có người che lốc, hoặc lốc khuất gần hết, thì bỏ trống như lần trước.
  - Không chạy `draft-keyframes` và không mở box của model trên các frame này.
  - Với mỗi đoạn `negative` mới: mở keyframe của nó và nhìn bằng mắt, chắc là tủ đã cất và không có lốc.

- [ ] **Step 5: Soát và ghi nhãn**

  - Chạy `labels review` và soát từng tấm: mỗi hộp nhìn thấy có đúng một khung, không khung nào nằm trên vật khác.
  - Chạy `labels write --frames … --segments … --keyframes … --out C:\Users\huyho\milk_store_labels\yolo`.
  - So `yolo\` với `yolo.bak-20261126`: file của frame chụp trước `2026-11-25T12:00` phải giống hệt từng byte.
  - Expected: có file nhãn cho các frame mới; đoạn `negative` nhận file rỗng.

- [ ] **Step 6: Chép sang HUYHOANG**

  - Frame: mỗi ngày mới một file `tar` (`tar --force-local`), `scp -l 50000`, giải nén bên kia. Chép cả
    `manifest.jsonl`.
  - Nhãn: `segments.json`, `segments_20261125.json`, `keyframes.json`, `yolo\`.
  - Code: chép `training\` và `server\milk` của nhánh sang `C:\Users\huyho\Datagent\store_view_code\`.
  - Expected: số file ảnh và số file nhãn trên HUYHOANG bằng trên laptop. Worker vẫn gửi capture đều trong lúc chép.

### Task 5: Đo trên HUYHOANG và báo số

Không có code vào repo. Script chạy để ở `C:\Users\huyho\Datagent\logs\`, theo mẫu `task7_eval.ps1` đã có ở đó:
`Set-Location store_view_code`, python của `.venv`, `--env-file C:\Users\huyho\Datagent\worker.env`, ghi log ra file.

**Interfaces:**
- Consumes: Task 1, 2 và 4.
- Produces, trong `C:\Users\huyho\Datagent\store_eval\`: `long-store-v1-det_holdout.json`,
  `long-store-v1-det_new.json`, `long-store-v1-db_new.json`, `vinamilk_same_20261126.txt`.

Hai chuỗi cài đặt dùng bên dưới (`$root` = `C:\Users\huyho\Datagent`):
- `DET` = `MILK_LONG_YOLO=$root\yolo\best_store_v1.pt;MILK_LONG_TILE=1280;MILK_LONG_VARIANTS=0;MILK_LONG_TH_CONFIRM=detector`
- `DB2` = `MILK_LONG_DIR=$root\carton_recognition_v2;MILK_LONG_YOLO=$root\yolo\best_store_v1.pt;MILK_LONG_TILE=1280`

- [ ] **Step 1: Chạy lại trên 594 frame cũ, bằng code thật**

Run: `evaluate run --frames $root\store_frames\CAM-S01-A --segments $root\store_labels\segments_20261125.json --labels $root\store_labels\yolo --env-file $root\worker.env --new "DET" --current "MILK_LONG_TILE=0" --out $root\store_eval\long-store-v1-det_holdout.json`
Expected:
- `held-out frames 594; Slide differs on 0`;
- dòng `new frames`: recall, precision và count_within_1 cách 0,952 / 0,946 / 0,974 không quá 0,02;
- `gate passed`.

Lệch quá 0,02 thì dừng: tìm chỗ code thật khác với phép đo 26/11 (bước `pipeline.merge` với Slide là chỗ đầu tiên cần
xem) trước khi làm tiếp.

- [ ] **Step 2: Đo trên ảnh mới, cả hai cách** (luật 5.5 của spec)

Run, hai lần, cùng `--segments $root\store_labels\segments.json --since 2026-11-25T13:00:00+07:00`:
- `--new "DET"`, ra `long-store-v1-det_new.json`;
- `--new "DB2"`, ra `long-store-v1-db_new.json`.

Expected ở lần `DET`: `gate passed` và `Slide differs on 0`. Lần `DB2` chỉ để so sánh.

- [ ] **Step 3: Đọc số ban đêm** từ dòng `night frames …` của lần `DET` ở Step 2.

Expected: `per 100` ≤ 1,0 trên ít nhất 150 frame. Ít hơn 150 frame thì ghi là "chưa đủ frame", gom thêm sau 23:05 rồi
chạy lại Step 2.

- [ ] **Step 4: Kiểm Vinamilk không đổi**

Viết script thử `C:\Users\huyho\Datagent\_confirm_spike\vinamilk_same.py` (không vào repo):
- lấy 200 dòng đầu của `store_eval\synth_val_11.txt`;
- nạp `LongPipeline` hai lần, cùng `best_store_v1.pt`, `MILK_LONG_TILE=0`, database v1, một lần
  `MILK_LONG_TH_CONFIRM=database` và một lần `detector`;
- trên mỗi ảnh, so các detection có `sku_id` không bắt đầu bằng `TMP-MLK-TH`;
- in số ảnh, số detection Vinamilk, số detection khác nhãn hoặc khác box, và độ lệch điểm lớn nhất.

Expected: có ít nhất 200 detection Vinamilk; 0 detection khác nhãn hoặc khác box; độ lệch điểm lớn nhất ≤ 0,002.

- [ ] **Step 5: Báo hoang**

Một bản tóm tắt gồm:
- bảng số của ba lần đo, theo frame và theo đoạn, và theo từng `arrangement` của ảnh mới;
- số ban đêm và kết quả Vinamilk;
- ngày 26/11 có kiểu xếp mới hay không. Nếu lốc vẫn nằm như 25/11 thì nói rõ phép đo này không nói thêm được gì về
  kiểu xếp mới;
- giờ cắt của ảnh mới;
- việc sẽ làm trên live và cách quay lui (Task 6).

Nếu ảnh mới trượt cổng: không làm Task 6 Step 2–5. Báo số và đề xuất giai đoạn 3 của spec.

### Task 6: Lên live (chờ hoang OK) và trả ngày 26/11 về tập dạy

- [ ] **Step 1: Push nhánh và mở PR vào `main`.** Body có số đo của Task 5 và đường dẫn spec. Expected: CI xanh.
  PR #15 đang mở từ `feat/auto-label-part2`; nhánh này chồng lên nó, nên PR chỉ còn commit của riêng nó sau khi PR #15
  merge.

- [ ] **Step 2: Chờ hoang OK** cho từng việc: deploy backend và website (PR #15 mang quy tắc B và dòng
  `TMP-MLK-TH-00`), rồi đổi worker.

- [ ] **Step 3: Backend và website**, nếu chưa deploy: theo Task 9 Step 3–4 của
  `docs/superpowers/plans/2026-11-25-th-store-view.md`.

- [ ] **Step 4: Worker và shelf plan, làm liền nhau.** Theo Task 9 Step 5 của kế hoạch TH, với các khác biệt:
  - đưa commit của nhánh này sang bản clone repo trên HUYHOANG bằng git bundle;
  - sao lưu `worker.env` thành `worker.env.bak-<ngày>`;
  - không đổi `MILK_LONG_DIR`;
  - đặt `MILK_LONG_YOLO=C:/Users/huyho/Datagent/yolo/best_store_v1.pt`, `MILK_LONG_TILE=1280`,
    `MILK_LONG_VARIANTS=0`, `MILK_LONG_TH_CONFIRM=detector`, `MILK_MODEL_VERSION=long-store-v1-det+slide-v3`;
  - Stop rồi Start task `milk-worker`;
  - lưu shelf plan DEMO-S01: 4 Slide cộng dòng gộp; xoá hai dòng `latest_stock` TH-01 và TH-02.

  Expected: trong 10 phút có capture mới mang box `TMP-MLK-TH-00`; Products hiện dòng TH gộp có số hộp; sau lần tick
  kế tiếp Dashboard thôi báo TH hết hàng. Log worker không có lỗi về `MILK_LONG_TH_CONFIRM`.

- [ ] **Step 5: Kiểm bằng trình duyệt** Products, Dashboard và trang Model như các lần trước. Expected: số TH khớp
  capture mới nhất.

- [ ] **Step 6: Trả ngày 26/11 về tập dạy.** Làm sau khi hoang đã quyết, dù quyết bật hay không.
  - Gỡ cửa sổ thứ ba khỏi `HOLDOUT`; đổi test của Task 3 lại thành
    `not holdout("2026-11-26T00:00:00+07:00") and not holdout("2026-11-27T09:00:00+07:00")`.
  - Run: `PYTEST tests`, `ruff check .`, `ruff format --check .`. Expected: PASS và sạch.
  - Commit: `git commit -m "Store-view: 26/11 goes back to training after the TH decision"`.

- [ ] **Step 7: Ghi chép.** Cập nhật `TRAINING.md` trên HUYHOANG (sao lưu trước), nhật ký HOANG-P10, memory. Nhắc team
  gắn nhãn lại frame AUD theo quy tắc B.

### Task 7: Luật bỏ box TH trùng, rồi đo lại (thêm ngày 26/11)

Thêm sau khi Task 5 cho thấy ảnh mới trượt cổng vì đếm thừa (spec mục 1e). hoang chọn ngày 26/11: "thử cách 1 trước".
Task này chạy **trước** Task 6. Ở Task 6 Step 4, thêm `MILK_LONG_TH_OVERLAP=0.5` vào các biến đặt cho worker.

**Files:**
- Modify: `server/milk/long_adapter.py`, `training/store_view/evaluate.py` (`LONG_KEYS`)
- Test: `tests/test_long_adapter.py`, `tests/test_store_view_evaluate.py`

**Interfaces:**
- Consumes: `LongPipeline.detect`, `_pipeline_with_fakes` trong test (Task 1); `LONG_KEYS`, `apply_env` (Task 2).
- Produces:
  - `_th_overlap() -> float`: đọc `MILK_LONG_TH_OVERLAP`. Không đặt hoặc rỗng là `0.0`.
  - `drop_shared(det: np.ndarray, is_th: Sequence[bool], limit: float) -> np.ndarray`: các dòng được giữ, theo thứ tự cũ.
  - `LongPipeline` giữ giá trị ở `self._th_overlap` và gọi `drop_shared` ngay sau `one_box_per_unit`.
  - `LONG_KEYS` có thêm `MILK_LONG_TH_OVERLAP`.

**Review Focus của task này:**
1. Giá trị dính khoảng trắng hoặc CR vẫn đọc được; giá trị không phải số trong khoảng 0–1 làm worker dừng.
2. Lốc thật: 8 hộp sát nhau của kiểu xếp E2 không hộp nào bị bỏ ở mức 0,5.
3. Model cũ 12 lớp, hoặc box Vinamilk: không bao giờ bị bỏ, và không làm box TH bị bỏ.

- [ ] **Step 1: Viết test** (thêm vào `tests/test_long_adapter.py`; import thêm `_th_overlap`, `drop_shared`;
  `_pipeline_with_fakes` nhận thêm tham số `th_overlap=0.0` và đặt `pipe._th_overlap`)

```python
def _rows(*boxes):
    """Detector rows (x0, y0, x1, y1, confidence, class 0, 0) from (x0, y0, x1, y1, confidence)."""
    return np.array([[*b, 0, 0] for b in boxes], dtype=float)


ACROSS = _rows((0, 0, 30, 24, 0.94), (26, 0, 56, 24, 0.92), (12, 0, 44, 24, 0.80))  # two cartons, a box across the seam


def test_a_box_lying_across_two_cartons_is_dropped():
    # its IoU with each carton is 0.41, so one_box_per_unit keeps it; it shares 0.6 of the box of each carton
    assert drop_shared(ACROSS, [True, True, True], 0.5)[:, 4].tolist() == [0.94, 0.92]


def test_the_cartons_of_a_real_pack_are_all_kept():
    # the eight cells of the pack as it lay on 25/11 (keyframe truth): neighbours overlap, never by half
    from training.store_view.labels import grid_boxes

    cells = grid_boxes([(876, 84), (918, 70), (972, 128), (930, 146)], 4, 2)
    det = _rows(*[(x, y, x + w, y + h, 0.95 - 0.01 * n) for n, (x, y, w, h) in enumerate(cells)])
    assert len(drop_shared(det, [True] * 8, 0.5)) == 8


def test_the_surer_box_stays_and_the_order_of_rows_is_kept():
    det = _rows((12, 0, 44, 24, 0.80), (26, 0, 56, 24, 0.92), (0, 0, 30, 24, 0.94))
    assert drop_shared(det, [True, True, True], 0.5)[:, 4].tolist() == [0.92, 0.94]


def test_only_merged_th_boxes_are_compared():
    det = _rows((0, 0, 30, 24, 0.94), (2, 2, 28, 22, 0.60), (4, 4, 26, 20, 0.50))  # each inside the one before
    assert drop_shared(det, [True, False, True], 0.5)[:, 4].tolist() == [0.94, 0.60]  # the other class stays
    assert len(drop_shared(det, [False, False, True], 0.5)) == 3  # another class never removes a TH box
    assert len(drop_shared(det, [False, False, False], 0.5)) == 3


def test_limit_zero_turns_the_rule_off():
    assert np.array_equal(drop_shared(ACROSS, [True, True, True], 0.0), ACROSS)


def test_th_overlap_setting(monkeypatch):
    monkeypatch.delenv("MILK_LONG_TH_OVERLAP", raising=False)
    assert _th_overlap() == 0.0
    for raw, want in (("", 0.0), ("0", 0.0), ("0.5", 0.5), (" 0.5\r", 0.5), ("1", 1.0)):
        monkeypatch.setenv("MILK_LONG_TH_OVERLAP", raw)
        assert _th_overlap() == want


@pytest.mark.parametrize("raw", ["half", "-0.1", "1.5", "50", "nan"])
def test_a_bad_th_overlap_stops_the_worker(monkeypatch, raw):
    monkeypatch.setenv("MILK_LONG_TH_OVERLAP", raw)
    with pytest.raises(ValueError, match="MILK_LONG_TH_OVERLAP"):
        _th_overlap()


def test_the_pipeline_drops_th_duplicates_before_the_database():
    pipe, calls = _pipeline_with_fakes(ACROSS, "detector", th_overlap=0.5)
    assert [d.confidence for d in pipe.detect(FRAME)] == [pytest.approx(0.94), pytest.approx(0.92)]
    pipe, calls = _pipeline_with_fakes(ACROSS, "database", th_overlap=0.5)
    pipe.detect(FRAME)
    assert calls["crops"] == 2


def test_the_pipeline_keeps_every_box_with_the_rule_off():
    pipe, _ = _pipeline_with_fakes(ACROSS, "detector")
    assert len(pipe.detect(FRAME)) == 3
```

  Thêm vào `tests/test_store_view_evaluate.py`:

```python
def test_the_overlap_setting_is_cleared_between_pipelines(monkeypatch):
    monkeypatch.setenv("MILK_LONG_TH_OVERLAP", "0.5")
    apply_env({}, {})
    assert "MILK_LONG_TH_OVERLAP" not in os.environ
```

- [ ] **Step 2: Chạy test, phải FAIL**

Run: `PYTEST tests/test_long_adapter.py tests/test_store_view_evaluate.py`
Expected: FAIL khi import ở file đầu; file sau fail ở test mới.

- [ ] **Step 3: Viết code**

  - `_th_overlap()`: bỏ khoảng trắng; rỗng là `0.0`; không đổi được sang số, hoặc số ngoài khoảng 0–1 (kể cả `nan`),
    thì `raise ValueError` có tên biến và giá trị.
  - `drop_shared`: `limit <= 0` thì trả lại `det`. Ngược lại duyệt các dòng có `is_th` theo độ tin cậy giảm dần; bỏ dòng
    nào có (phần chung ÷ diện tích box nhỏ hơn) ≥ `limit` với một dòng TH đã giữ. Dòng không phải TH luôn được giữ.
    Trả các dòng được giữ theo thứ tự ban đầu.
  - `LongPipeline.detect`: gọi sau `one_box_per_unit`, với `is_th` là "lớp của dòng bằng `TH_BRAND`".
  - Thêm biến vào docstring đầu file và vào `LONG_KEYS`.

- [ ] **Step 4: Chạy test, phải PASS**

Run: `PYTEST tests/test_long_adapter.py tests/test_store_view_evaluate.py`, rồi `PYTEST tests`, `ruff check .`,
`ruff format --check .`
Expected: PASS và sạch.

- [ ] **Step 5: Commit**

```bash
git add server/milk/long_adapter.py training/store_view/evaluate.py tests/test_long_adapter.py tests/test_store_view_evaluate.py
git commit -m "Milk adapter: MILK_LONG_TH_OVERLAP drops a merged TH box that shares half of a surer one"
```

- [ ] **Step 6: Gom ảnh chụp sau 14:07 ngày 26/11 và vẽ đáp án**, theo đúng cách của Task 4.
  - Trước khi chia đoạn lại, chép `segments.json` thành `segments_20261126_1407.json` (844 frame mới của Task 5).
  - Sau khi ghi nhãn, tạo `segments_after1407.json`: bản `segments.json` mới, mỗi đoạn chỉ giữ thành viên chụp từ
    `2026-11-26T14:07:00+07:00`; đoạn không còn thành viên nào thì bỏ.
  - Chép frame, nhãn, ba file segments và code của commit Step 5 sang HUYHOANG.

- [ ] **Step 7: Đo bằng code thật trên HUYHOANG.** `OV` = chuỗi `DET` của Task 5 cộng `;MILK_LONG_TH_OVERLAP=0.5`.

  | Lượt | `--segments` | Thêm | Expected |
  |---|---|---|---|
  | a | `segments_20261125.json` | | `gate passed`; cách 0,948 / 0,968 / 0,960 không quá 0,02; Slide differs on 0 |
  | b | `segments_20261126_1407.json` | `--since 2026-11-25T13:00:00+07:00 --per-segment 200` | `gate passed`; cách 0,926 / 0,921 / 0,994 không quá 0,02; night 194 frame, per 100 ≤ 1,0 |
  | c | `segments_after1407.json` | `--per-segment 200` | `gate passed`. Đây là ảnh chưa ai nhìn, chụp sau khi luật đã chốt |

  Chạy lại `vinamilk_same.py` với `MILK_LONG_TH_OVERLAP=0.5` ở phía `detector`. Expected: 0 detection Vinamilk khác.

- [ ] **Step 8: Báo hoang** số của ba lượt, theo frame, theo đoạn và theo `arrangement`. Lượt c trượt thì không bật: báo
  số và dừng. Cả ba qua thì sang Task 6.
