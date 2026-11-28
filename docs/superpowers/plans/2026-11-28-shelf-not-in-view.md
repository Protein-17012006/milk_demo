# Hàng còn trong khung thì vẫn đếm; không thấy thì ghi "Not in view" — kế hoạch làm

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Khi tủ bị dời, Dashboard vẫn đếm hàng còn trong khung; sản phẩm mà hệ thống không biết chỗ có đang trong khung hay không thì hiện "Not in view" thay vì hết hàng, không vào OSA, không sinh sự kiện.

**Architecture:** Mọi quyết định nằm ở backend, tính từ dữ liệu capture đã lưu; worker và hub không đổi. `backend/shelf.py` thêm các hàm thuần: luật "thấy kệ" (vùng cũ khớp hoặc ≥ 3 hộp chắc chắn ở bất kỳ đâu), vị trí các lon, "cách bày" theo camera và trạng thái "không thấy" của từng SKU. Tick 5 phút và lần tính lại dùng chúng; ingest mỗi capture, API, website và luật ban đêm của bộ chạy thử đọc kết quả.

**Tech Stack:** Python 3.12, boto3, pytest, moto. Next.js (đọc `frontend/AGENTS.md` và `node_modules/next/dist/docs/` trước khi sửa frontend), test frontend bằng `node --test` trên `frontend/lib/*.test.ts`.

**Spec:** `docs/superpowers/specs/2026-11-28-shelf-not-in-view-design.md` (hoang duyệt 28/11: *"ok duyệt thực hiện và build luôn, sử dụng sub-agent build full"*). Đọc cả spec trước khi làm task nào.

## Global Constraints

- Ngưỡng, đúng như spec mục 7.1: `PRODUCTS_MIN_BOXES = 3`, `PRODUCTS_MIN_CONF = 0.8`, `ARRANGEMENT_JUMP_PX = 500`; "thấy lại" dùng `CONFIDENT = 0.70` sẵn có của `shelf.py`.
- Một hộp "có tên" là hộp có `sku_id` khác `None` (nhãn model trong `detections_json`, hoặc `model_alias`/`sku_id` của dòng khi không có `detections_json`, như `model_health.capture_boxes` đọc).
- Không đổi worker (`server/`), hub, `infra/*.yaml`, bảng DynamoDB hay biến môi trường.
- Không push, không deploy trong đợt này. Deploy là việc riêng, sau khi phần 1 đóng (29/11) và hoang duyệt (mục cuối).
- Chữ trên website bằng tiếng Anh, đúng spec 7.7: nhãn **Not in view**; dòng phụ `since 12:15 · last seen 6 at 12:10` hoặc `since 12:15 · was out of stock at 12:10`; ngày khác hôm nay thêm ` on DD/MM` sau giờ.
- Commit bằng danh tính noreply, có dòng đồng tác giả:
  `git -c user.name="Nguyen Huy Hoang" -c user.email="193206418+Protein-17012006@users.noreply.github.com" commit -m "<message>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`
- Python để test: `C:/Users/huyho/AppData/Local/Temp/claude/cf23e0181d28b9db/d784bd5c-f3c9-452f-a00b-c9c0fe504e3e/scratchpad/venv/Scripts/python.exe` (viết tắt `PY` dưới đây), chạy từ thư mục repo `milk_demo`. Bộ test đầy đủ: `PY -m pytest -q` (khoảng 2,5 phút).
- Frontend, trong `milk_demo/frontend`: `npm test`, `npx tsc --noEmit`, `npm run build`, `npm run lint`. `npm run lint` đã có sẵn 3 lỗi `react-hooks/set-state-in-effect` (CategoryProductsView, SettingsView, lib/auth) từ trước nhánh này; không thêm lỗi mới.
- Một test cũ trượt vì capture "tủ đã cất" của nó có ≥ 3 hộp ở độ tin cậy 0,9: chỉ sửa dữ liệu đầu vào cho đúng nghĩa cũ (thêm hộp ma độ tin cậy 0,5, xem từng task), không nới lỏng assert. Ghi tên test đã sửa vào sổ.

## Review Focus

- Một người đứng che tủ trọn một lần kiểm (các hộp chắc chắn dồn về một phía, tâm lệch 150–400 px) → không phải đổi cách bày. Test ở Task 2.
- Capture cũ đến muộn sau khi tủ đã dời (SQS không giữ thứ tự), ở vị trí cũ → không đếm lùi gì, không làm sản phẩm "không thấy" thành 0. Test ở Task 4.
- Vị trí đọc lại từ DynamoDB là `Decimal`: ingest phải qua `from_dynamodb` trước khi so khoảng cách. Test ở Task 4 (moto lưu `Decimal` thật).
- Tủ dời lúc tiệm đóng cửa (đêm, trước giờ mở): lần kiểm ngoài giờ không định cách bày; lần kiểm đầu trong giờ so với lần cuối trong giờ. Test ở Task 3.
- Sản phẩm đang hết hàng thì tủ bị dời → không bao giờ hiện "Out of stock" nữa mà hiện `was out of stock at …`. Test ở Task 3 (số cuối 0 được giữ) và Task 6 (câu chữ).

---

### Task 1: Luật "thấy kệ" và vị trí các lon (`shelf.py`, `build_check`)

**Files:**
- Modify: `backend/shelf.py` (hằng số và hàm mới cạnh `sees_display`; `build_check`)
- Test: `tests/test_shelf.py`

**Interfaces:**
- Produces (trong `backend/shelf.py`):
  - `PRODUCTS_MIN_BOXES = 3`, `PRODUCTS_MIN_CONF = 0.8`, `ARRANGEMENT_JUMP_PX = 500`
  - `sure_boxes(capture: dict) -> list[dict]`: các hộp của `capture_boxes(capture)` có `sku_id` và `conf >= PRODUCTS_MIN_CONF`.
  - `sees_products(capture: dict) -> bool`: `len(sure_boxes(capture)) >= PRODUCTS_MIN_BOXES`.
  - `sees_shelf(capture: dict) -> bool`: `sees_display(capture) or sees_products(capture)`.
  - `capture_position(capture: dict) -> list[int] | None`: `[round(x), round(y)]`, trung vị (`statistics.median`, x và y riêng) tâm `(bx + bw / 2, by + bh / 2)` của `sure_boxes`; `None` khi `sees_products` sai.
  - `products_position(captures: list[dict]) -> list[int] | None`: trung vị (x, y riêng, làm tròn) của các `capture_position` khác `None`; `None` khi không có.
  - `far_apart(a, b) -> bool`: khoảng cách Euclid giữa hai điểm `[x, y]` lớn hơn `ARRANGEMENT_JUMP_PX` (bằng 500 thì không). Nhận cả `int`, `float`.
  - `build_check` dùng `sees_shelf` thay `sees_display` để chọn capture đếm và tính `measurable` (công thức nửa số capture giữ nguyên), và thêm 3 trường: `positions: dict[str, list[int]]` (camera → `products_position` của các capture thấy kệ của camera đó; camera không có vị trí thì vắng mặt), `confident_by_camera: dict[str, list[str]]` (camera → tên sản phẩm có hộp ≥ `CONFIDENT`, sắp xếp; `confident_skus` giữ là hợp của chúng), `captures_zone: int` (số capture qua `sees_display`).

- [ ] **Step 1: Viết test trượt** trong `tests/test_shelf.py` (mục mới `# --- Shelf not in view: seeing the shelf ---`), dùng `cap(..., boxes=[...], visible=...)` có sẵn; hộp dạng `{"sku_id": "cheese145", "conf": 0.9, "box": [x, y, w, h]}`:

```python
def test_a_capture_away_from_the_zone_sees_the_shelf_by_three_sure_boxes():
    sure = [{"sku_id": "cheese145", "conf": 0.9, "box": [100 * k, 0, 10, 10]} for k in range(3)]
    assert sees_shelf(cap("CAM-S01-A", TS, {}, boxes=sure, visible=False))
    assert not sees_shelf(cap("CAM-S01-A", TS, {}, boxes=sure[:2], visible=False))
    assert not sees_shelf(cap("CAM-S01-A", TS, {}, boxes=[{**b, "conf": 0.79} for b in sure], visible=False))
    assert not sees_shelf(cap("CAM-S01-A", TS, {}, boxes=[{**b, "sku_id": None} for b in sure], visible=False))


def test_a_capture_the_zone_check_passes_sees_the_shelf_without_boxes():
    assert sees_shelf(cap("CAM-S01-A", TS, {}, boxes=[], visible=True))
    assert sees_shelf(cap("CAM-S01-A", TS, {}))  # older than the display check


def test_capture_position_is_the_median_centre_of_its_sure_boxes():
    boxes = [
        {"sku_id": "cheese145", "conf": 0.9, "box": [0, 0, 10, 10]},
        {"sku_id": "hot160", "conf": 0.9, "box": [100, 0, 10, 10]},
        {"sku_id": "hot160", "conf": 0.95, "box": [200, 40, 10, 10]},
        {"sku_id": "hot160", "conf": 0.5, "box": [2000, 2000, 10, 10]},  # not sure: left out
    ]
    assert capture_position(cap("CAM-S01-A", TS, {}, boxes=boxes, visible=False)) == [105, 5]
    assert capture_position(cap("CAM-S01-A", TS, {}, boxes=boxes[:2], visible=False)) is None


def test_products_position_is_the_median_of_the_captures_positions():
    # three captures centred near (100, 10), (110, 12) and (400, 50), and one without a position
    assert products_position([...]) == [110, 12]
    assert products_position([cap("CAM-S01-A", TS, {}, visible=False)]) is None


def test_far_apart_means_more_than_500_px():
    assert not far_apart([0, 0], [300, 400])  # exactly 500
    assert far_apart([0, 0], [300, 401])
    assert far_apart([1068, 246], [290, 412])  # 28/11 12:10 -> 12:15
    assert not far_apart([820, 148], [934, 527])  # 27/11 12:05, 399 px


def test_a_check_counts_captures_that_see_products_away_from_the_zone():
    # two captures with display_visible False but 5 sure Cheese boxes each: measurable, Cheese counted 5
    ...


def test_a_check_keeps_positions_confident_products_by_camera_and_zone_captures():
    # CAM-S01-A: two captures with sure boxes centred at x 1000 (one in the zone, one not); CAM-S01-B: no boxes
    # -> positions == {"CAM-S01-A": [...]}, "CAM-S01-B" not in positions,
    #    confident_by_camera["CAM-S01-A"] == ["Slide Cheese 145g"], captures_zone == the zone captures
    ...
```

`TS` là một giờ hằng trong file (ví dụ `"2026-11-21T14:00:10+07:00"`). Các test có dấu `...` viết đủ dữ liệu và assert theo chú thích; con số trong chú thích là đáp số.

- [ ] **Step 2: Chạy, thấy trượt**

Run: `PY -m pytest tests/test_shelf.py -q`
Expected: FAIL, `ImportError` (chưa có `sees_shelf`, `capture_position`, …).

- [ ] **Step 3: Viết code** theo khối Interfaces ở `backend/shelf.py`; thêm các tên mới vào import của test. `import statistics`, `import math`.

- [ ] **Step 4: Chạy lại, sửa test cũ đổi nghĩa**

Run: `PY -m pytest tests/test_shelf.py -q`
Expected: test mới qua. Test cũ có capture `visible=False` mà `counts` ≥ 3 (hộp từ `rows_json` ở 0,9) sẽ trượt, dự kiến gồm `test_a_check_counts_only_captures_that_see_the_display`, `test_a_check_mostly_without_the_display_is_not_measurable`, `test_a_check_without_the_display_says_why`, `test_a_check_without_the_display_does_not_start_a_sku_by_its_counts`. Với mỗi test đó, cho capture ẩn `boxes=[PHANTOM]` với `PHANTOM = {"sku_id": "cheese145", "conf": 0.5, "box": [0, 0, 8, 8]}` (hộp ma ban đêm: độ tin cậy thấp), giữ nguyên assert. Chạy lại: tất cả qua.

- [ ] **Step 5: Chạy toàn bộ, ghi các test moto trượt vì cùng lý do**

Run: `PY -m pytest -q`
Expected: `tests/test_shelf.py` qua hết. Test moto nào trượt do `build_check` đổi (capture ẩn có ≥ 3 hộp 0,9 qua `_ingest`) thì sửa dữ liệu đầu vào: thêm `detections=[{"sku_id": "<nhãn>", "conf": 0.5, "box": [10, 20, 50, 80]}]` cho capture ẩn đó. Ghi tên vào sổ. Không còn test trượt.

- [ ] **Step 6: Commit**

```bash
git add backend/shelf.py tests/test_shelf.py tests/test_backend_integration_moto.py
git commit -m "Shelf: a capture sees the shelf when the zone matches or three sure boxes are anywhere in the frame"
```

---

### Task 2: Cách bày và sản phẩm "không thấy" (`shelf.py`, hàm thuần; `rollup`)

**Files:**
- Modify: `backend/shelf.py` (hàm mới sau `step_state`; `SKU_FIELDS`, `rollup`)
- Test: `tests/test_shelf.py`

**Interfaces:**
- Consumes: `far_apart`, `CONFIDENT` (Task 1); `_NEW_STATE`, `step_state`.
- Produces (trong `backend/shelf.py`):
  - `in_view(state: dict | None) -> bool`: `False` chỉ khi `state["in_view"] is False`.
  - `view_of(state: dict | None) -> dict | None`: khi không thấy, `{"since": not_in_view_since, "last_units": last_seen_units, "last_at": last_seen_at}` (bucket `YYYYMMDD-HHMM` hoặc `None`); ngược lại `None`.
  - `step_arrangements(arrangements: dict[str, dict], check: dict) -> list[str]`: với từng camera trong `check["positions"]` (thứ tự tên): chưa có → tạo `{"position": pos, "since": check["bucket"]}`; `far_apart(arrangement["position"], pos)` → thay bằng `{"position": pos, "since": check["bucket"]}` và ghi camera vào danh sách đổi; ngược lại → `arrangement["position"] = pos`. Sửa `arrangements` tại chỗ; trả danh sách camera đổi cách bày (đã sắp xếp).
  - `move_skus(skus_state: dict[str, dict], cameras: list[str], check: dict) -> None`: với mỗi SKU trong `skus_state` có `camera` thuộc `cameras` hoặc chưa có `camera`:
    - được thấy chắc chắn ở lần kiểm này (có trong `check["confident_by_camera"][c]` của một camera `c` trong `cameras`, và `check["counts"][sku] > 0`) → thay bằng `{"in_view": True, "camera": c}`;
    - đang không thấy từ trước → thay bằng `{"in_view": False, "not_in_view_since": <giữ>, "last_seen_units": <giữ>, "last_seen_at": <giữ>, "camera": <giữ>}`;
    - còn lại → `{"in_view": False, "not_in_view_since": check["bucket"], "last_seen_units": L nếu L khác None, không thì prev, "last_seen_at": prev_bucket, "camera": <camera cũ>}`.
  - `see_skus(skus_state: dict[str, dict], check: dict, expected: list[str]) -> None`: với từng camera (thứ tự tên) và từng SKU trong `expected` có trong `confident_by_camera[camera]` với `counts[sku] > 0`, nếu SKU chưa được camera trước đó nhận: đang không thấy → thay bằng `{"in_view": True, "camera": camera}`; đã có trạng thái → `state["camera"] = camera`; chưa có → tạo `{"camera": camera}`.
  - `SKU_FIELDS` thêm `"unseen_checks"`. `rollup`: SKU dự kiến nằm trong `check.get("not_in_view")` thì cộng `unseen_checks`, không cộng `checks`, `available`, `units_sum`, và không vào tổng `total` của lần kiểm.

- [ ] **Step 1: Viết test trượt** trong `tests/test_shelf.py` (mục `# --- Shelf not in view: arrangements and products not in view ---`):

```python
def test_the_first_position_of_a_camera_starts_its_arrangement():
    arrangements = {}
    assert step_arrangements(arrangements, {"bucket": "20261128-1000", "positions": {"CAM-S01-A": [1000, 250]}}) == []
    assert arrangements == {"CAM-S01-A": {"position": [1000, 250], "since": "20261128-1000"}}


def test_a_jump_of_more_than_500_px_is_a_new_arrangement():
    arrangements = {"CAM-S01-A": {"position": [1068, 246], "since": "20261128-0625"}}
    assert step_arrangements(arrangements, {"bucket": "20261128-1215", "positions": {"CAM-S01-A": [290, 412]}}) == [
        "CAM-S01-A"
    ]
    assert arrangements["CAM-S01-A"] == {"position": [290, 412], "since": "20261128-1215"}


def test_a_person_in_front_or_a_slow_drift_is_the_same_arrangement():
    arrangements = {"CAM-S01-A": {"position": [1000, 250], "since": "20261128-0625"}}
    for pos in ([1180, 250], [820, 148], [934, 527], [1150, 283]):  # up to 399 px from the previous position
        assert step_arrangements(arrangements, {"bucket": "20261128-1300", "positions": {"CAM-S01-A": pos}}) == []
    assert arrangements["CAM-S01-A"] == {"position": [1150, 283], "since": "20261128-0625"}


def test_a_check_without_a_position_changes_no_arrangement(): ...  # positions {} -> [] and arrangements unchanged


def test_a_move_puts_products_not_seen_out_of_view_with_what_was_seen_last():
    # TH: level 6 last stepped at 12:10; Cheese: seen surely in the moved check; Hot: on another camera
    # -> TH: {"in_view": False, "not_in_view_since": "20261128-1215", "last_seen_units": 6,
    #         "last_seen_at": "20261128-1210", "camera": "CAM-S01-A"}
    # -> Cheese: {"in_view": True, "camera": "CAM-S01-A"} (its level is gone: it starts again)
    # -> Hot (camera CAM-S01-B) unchanged
    ...


def test_a_product_already_out_of_view_keeps_when_it_was_last_seen(): ...  # a second move keeps not_in_view_since, last_seen_units, last_seen_at of the first


def test_a_product_out_of_stock_before_a_move_keeps_zero_as_last_seen(): ...  # state with L 0, status OOS -> last_seen_units 0, in_view False, no status OOS left


def test_a_product_seen_again_starts_fresh_and_in_view():
    # not in view since 12:15; seen surely with 4 units at 12:30 -> {"in_view": True, "camera": "CAM-S01-A"}
    # then step_state twice with 4 -> level 4 and no event
    ...


def test_see_skus_names_the_camera_that_counted_a_product_surely(): ...  # two cameras: the first camera in name order that saw it surely; a product not expected is left alone


def test_in_view_and_view_of():
    assert in_view(None) and in_view({}) and in_view({"in_view": True})
    assert not in_view({"in_view": False})
    assert view_of(
        {"in_view": False, "not_in_view_since": "20261128-1215", "last_seen_units": 6, "last_seen_at": "20261128-1210"}
    ) == {"since": "20261128-1215", "last_units": 6, "last_at": "20261128-1210"}
    assert view_of({"in_view": True}) is None


def test_a_product_not_in_view_is_left_out_of_the_hours_numbers():
    # one open check, expected [Cheese, TH], counts {Cheese: 5}, not_in_view [TH]
    # -> Cheese checks 1 available 1; TH checks 0 available 0 unseen_checks 1; max_total 5
    ...
```

- [ ] **Step 2: Chạy, thấy trượt**

Run: `PY -m pytest tests/test_shelf.py -q`
Expected: FAIL, `ImportError` (chưa có `step_arrangements`, …).

- [ ] **Step 3: Viết code** theo khối Interfaces.

- [ ] **Step 4: Chạy lại**

Run: `PY -m pytest tests/test_shelf.py -q`
Expected: tất cả qua.

- [ ] **Step 5: Commit**

```bash
git add backend/shelf.py tests/test_shelf.py
git commit -m "Shelf: arrangements per camera, and products whose place is not in view are left out of the numbers"
```

---

### Task 3: Tick 5 phút và lần tính lại (`ingest/handler.py`)

**Files:**
- Modify: `backend/ingest/handler.py` (`_apply_check`, `_shelf_store_tick`, `shelf_recompute`)
- Test: `tests/test_backend_integration_moto.py` (mục mới sau các test shelf tick)

**Interfaces:**
- Consumes: `shelf.step_arrangements`, `shelf.move_skus`, `shelf.see_skus`, `shelf.in_view` (Task 2); các trường của lần kiểm từ Task 1.
- Produces:
  - `_apply_check(check, store, plan, skus_state, last_measured, since, arrangements) -> tuple[list[dict], str | None]`. Thứ tự: `open`; `expected = expected_at(...)`; không mở cửa hoặc không đo được → trả `([], last_measured)` (cách bày không đổi); `moved = shelf.step_arrangements(arrangements, check)`; có `moved` → `shelf.move_skus(...)`, ghi `check["arrangement_changed"] = True`; `shelf.see_skus(skus_state, check, expected)`; `check["not_in_view"] = [s for s in expected if not shelf.in_view(skus_state.get(s))]`; không có `expected` → trả `([], last_measured)`; chỉ chạy `step_state` cho SKU dự kiến đang thấy.
  - Item `state` của bảng shelf có thêm `arrangements` (đọc và ghi ở tick; tính lại bắt đầu từ `{}`).
  - `shelf_recompute` chép thêm `positions`, `confident_by_camera`, `captures_zone` từ lần kiểm đã lưu (thêm vào `display_fields`).

- [ ] **Step 1: Viết test trượt.** Thêm helper:

```python
def _sure_at(x: int, counts: list[tuple[str, int]]) -> list[dict]:
    """Sure boxes (conf 0.9) of each (model label, units), side by side from x, as the worker sends detections."""
```

(hộp `[x + 60 * k, 20, 50, 80]`, `k` chạy liên tục qua mọi nhãn). Mỗi capture trong các test này truyền cả `counts` và `detections=_sure_at(...)`. Vị trí "chỗ cũ" là `x = 1000` với `display_visible=True`; "chỗ mới" là `x = 200` với `display_visible=False`.

```python
def test_a_moved_display_keeps_counting_what_is_in_view(monkeypatch):
    # plan Cheese + Hot; 14:00:10 and 14:05:10 at the old place: cheese 5, hot 3
    # 14:10:10 and 14:15:10 at the new place: cheese 5 only; tick at 14:22
    state = _shelf("state")
    assert {k: state["skus"][HOT][k] for k in ("in_view", "not_in_view_since", "last_seen_units", "last_seen_at")} == {
        "in_view": False,
        "not_in_view_since": "20261121-1410",
        "last_seen_units": 3,
        "last_seen_at": "20261121-1405",
    }
    assert state["skus"][CHEESE]["in_view"] is True and state["skus"][CHEESE]["L"] == 5
    assert _event_keys() == []
    check = _shelf("check#20261121-1410")
    assert check["arrangement_changed"] is True and check["not_in_view"] == [HOT]
    assert _shelf("hour#20261121-14")["skus"][HOT]["unseen_checks"] == 2
    assert state["arrangements"]["CAM-S01-A"]["since"] == "20261121-1410"


def test_after_a_gap_the_same_place_keeps_an_out_of_stock(monkeypatch):
    # plan Cheese; 14:00 and 14:05 cheese 5 + hot 3 at x 1000; 14:10 and 14:15 hot 3 only at x 1000 (Cheese OOS at 14:10);
    # 15:30 and 15:35 hot 3 at x 1010 (a gap of more than 30 min, same place); tick at 15:42
    assert _event_keys() == [f"20261121-1410#{CHEESE}#OOS"]
    assert _shelf("state")["skus"][CHEESE]["status"] == "OOS"


def test_moving_away_and_back_makes_no_depleted_or_restock(monkeypatch):
    # plan Cheese; 14:00, 14:05 cheese 6 at x 1000; 14:10, 14:15 cheese 2 + hot 3 at x 200 (hidden);
    # 14:20, 14:25 cheese 6 at x 1000; tick at 14:32
    assert _event_keys() == []


def test_a_product_seen_again_after_a_move_comes_back_without_an_event(monkeypatch):
    # plan Cheese + Hot; old place 14:00, 14:05 (cheese 5, hot 3); new place 14:10, 14:15 cheese only;
    # new place 14:20, 14:25 cheese 5 + hot 4; tick at 14:32
    hot = _shelf("state")["skus"][HOT]
    assert hot["in_view"] is True and hot["L"] == 4 and not hot.get("not_in_view_since")
    assert _event_keys() == []


def test_a_product_out_of_stock_when_the_display_moves_keeps_zero_as_last_seen(monkeypatch):
    # plan Cheese + Hot; 14:00, 14:05 cheese 5 + hot 3; 14:10, 14:15 cheese 5 only (Hot OOS at 14:10), old place;
    # 14:20, 14:25 cheese 5 at the new place; tick at 14:32
    hot = _shelf("state")["skus"][HOT]
    assert (hot["in_view"], hot["last_seen_units"], hot.get("status")) == (False, 0, None)
    assert _event_keys() == [f"20261121-1410#{HOT}#OOS"]


def test_checks_outside_opening_hours_do_not_set_the_arrangement(monkeypatch):
    # opening 14:10-22:00; 14:00 and 14:05 at x 200 (closed); 14:10 and 14:15 at x 1000 (open); tick at 14:22
    assert all(
        not (_shelf(f"check#20261121-{b}") or {}).get("arrangement_changed") for b in ("1400", "1405", "1410", "1415")
    )
    assert _shelf("state")["arrangements"]["CAM-S01-A"]["since"] == "20261121-1410"


def test_a_recompute_finds_the_same_moves_as_the_tick(monkeypatch):
    # the first scenario; tick; then ask for a recompute (as test_a_saved_plan_is_recomputed_on_the_next_tick does)
    # and tick again: the same events, the same view fields of Hot, check 1410 still arrangement_changed
    ...
```

- [ ] **Step 2: Chạy, thấy trượt**

Run: `PY -m pytest tests/test_backend_integration_moto.py -q -k "moved_display or same_place or moving_away or seen_again_after or out_of_stock_when_the_display or outside_opening_hours_do_not or same_moves"`
Expected: FAIL (chưa có `arrangements`, `not_in_view`).

- [ ] **Step 3: Viết code** theo khối Interfaces.

- [ ] **Step 4: Chạy lại, rồi cả bộ**

Run: `PY -m pytest -q`
Expected: tất cả qua (test tick và tính lại cũ không đổi kết quả vì `in_view` mặc định đúng).

- [ ] **Step 5: Commit**

```bash
git add backend/ingest/handler.py tests/test_backend_integration_moto.py
git commit -m "Shelf tick: a move of the display starts a new arrangement; products not seen there are not in view"
```

---

### Task 4: Ingest mỗi capture (`ingest/handler.py`)

**Files:**
- Modify: `backend/ingest/handler.py` (`ingest_capture`, `_count_down_missing`, `sample_frames`, `serve_label_request`)
- Test: `tests/test_backend_integration_moto.py`

**Interfaces:**
- Consumes: `shelf.sees_shelf`, `shelf.capture_position`, `shelf.far_apart` (Task 1); `shelf.in_view` (Task 2); item `state` có `arrangements` và `skus` (Task 3).
- Produces:
  - `ingest_capture` dùng `shelf.sees_shelf(capture_item)` (dict vừa dựng của bảng captures, có `detections_json`, `rows_json`, `display_visible`) thay `shelf.sees_display(record)` cho `latest_stock`, hàng chờ duyệt, `_count_down_missing` và `_record_display`.
  - `_shelf_state(ddb_resource, store_id: str) -> dict`: item `state` của cửa hàng qua `from_dynamodb`; `{}` khi không có `SHELF_TABLE` hoặc chưa có item.
  - `_count_down_missing(stock_tbl, store_id, camera_id, capture_ts, seen_skus, skip: frozenset[str] = frozenset())`: bỏ qua SKU trong `skip`. Ở `ingest_capture`: nếu `capture_position(capture_item)` và vị trí cách bày của camera trong `state` đều có và `far_apart` → không gọi `_count_down_missing`; ngược lại gọi với `skip` = các SKU mà `state["skus"]` ghi không thấy.
  - `sample_frames` (chọn frame dạy) và `serve_label_request` dùng `shelf.sees_shelf` thay cho `display_visible`.

- [ ] **Step 1: Viết test trượt:**

```python
def test_a_capture_with_products_away_from_the_zone_updates_the_shelf_numbers(monkeypatch):
    # display_visible False, cheese 5 with _sure_at(200, ...)
    assert _units(api)[CHEESE] == 5
    assert _shelf("display#CAM-S01-A")["visible"] is True


def test_no_count_down_right_after_a_move(monkeypatch):
    # plan Cheese + Hot; old place 14:00, 14:05 (cheese 5, hot 3); tick at 14:12 (state knows the old place);
    # new place 14:10 cheese only -> Hot's latest_stock row unchanged
    stock = _table("test-latest-stock").get_item(Key={"store_id": "DEMO-S01", "sku_id": HOT})["Item"]
    assert stock["recent_counts"] == [3, 3]


def test_a_product_not_in_view_is_not_counted_down(monkeypatch):
    # as above, then 14:15 at the new place and a tick at 14:22 (Hot not in view, arrangement at the new place);
    # 14:20 at the new place without Hot -> Hot's row still [3, 3]
    ...


def test_a_late_capture_from_the_old_place_counts_nothing_down(monkeypatch):
    # after the tick at 14:22 of the test above: a late capture 14:08:30 at the old place, cheese only -> Hot unchanged
    ...


def test_training_frames_come_from_captures_that_see_products_away_from_the_zone(monkeypatch):
    # an hour whose captures all have display_visible False but 5 sure boxes and a frame -> a TRN- audit is written
    # (follow test_training_frames_only_come_from_captures_that_see_the_display)
    ...


def test_a_frame_request_for_a_capture_that_sees_products_away_from_the_zone_is_served(monkeypatch):
    # follow the existing label-request tests: a correction of a reading whose capture has display_visible False and
    # 5 sure boxes gets its TRN- frame, not "the reading has no usable frame"
    ...
```

- [ ] **Step 2: Chạy, thấy trượt**

Run: `PY -m pytest tests/test_backend_integration_moto.py -q -k "away_from_the_zone or count_down or counted_down or counts_nothing_down"`
Expected: FAIL.

- [ ] **Step 3: Viết code** theo khối Interfaces.

- [ ] **Step 4: Chạy cả bộ, sửa test cũ đổi nghĩa**

Run: `PY -m pytest -q`
Expected: test mới qua. Test cũ có capture ẩn mang ≥ 3 hộp 0,9 (dự kiến `test_a_hidden_capture_with_rows_changes_no_stock_and_queues_nothing`, có thể cả các test frame dạy và `display#`) trượt: cho capture ẩn `detections=[{"sku_id": "<nhãn>", "conf": 0.5, "box": [10, 20, 50, 80]}]`, giữ assert, ghi tên vào sổ. Cuối cùng tất cả qua.

- [ ] **Step 5: Commit**

```bash
git add backend/ingest/handler.py tests/test_backend_integration_moto.py
git commit -m "Ingest: products in frame keep the numbers going; nothing is counted down right after a move or while not in view"
```

---

### Task 5: API (`api/handler.py`)

**Files:**
- Modify: `backend/api/handler.py` (`_load_products_catalog`, `_handle_get_products`, `_handle_kpi`, `_on_shelf_units`)
- Test: `tests/test_backend_integration_moto.py`

**Interfaces:**
- Consumes: `shelf.view_of`, `shelf.bucket_time` (Task 2 và sẵn có); item `state`.
- Produces:
  - `_not_in_view_by_store(ddb, stores: list[dict]) -> dict[str, dict[str, dict]]`: store_id → {SKU → `{"since", "last_units", "last_at"}`}, giờ đổi từ bucket sang ISO ICT bằng `shelf.bucket_time(b).isoformat()` (`None` giữ `None`). Một lần `get_item` mỗi cửa hàng; đọc lỗi thì in log và coi như không có SKU nào không thấy.
  - `_load_products_catalog(ddb, tables=None, plan=None, not_in_view=None)`: `not_in_view: dict[str, dict] | None` (SKU → thông tin, đã gộp các cửa hàng). SKU thuộc `plan` và có trong `not_in_view` → `stock_status = "NOT_IN_VIEW"` và `not_in_view = <thông tin>`; SKU khác không có trường `not_in_view`.
  - Gộp cửa hàng *(spec 7.6)*: SKU không thấy khi ít nhất một cửa hàng ghi nó không thấy và không cửa hàng nào có nó trong `state["skus"]` với `in_view` đúng; thông tin lấy từ cửa hàng có `since` mới nhất.
  - `/kpi`: tổng không lọc bỏ SKU không thấy; `_on_shelf_units(ddb, params, hidden: dict[str, dict[str, dict]])` bỏ dòng `latest_stock` có `(store_id, sku_id)` không thấy.

- [ ] **Step 1: Viết test trượt:**

```python
def test_products_say_not_in_view_with_since_and_last_seen(monkeypatch):
    # plan Cheese + Hot; old place 14:00, 14:05; tick at 14:12; new place 14:10, 14:15 cheese only; tick at 14:22
    hot = next(p for p in _get(api, "/products")["items"] if p["sku_id"] == HOT)
    assert hot["stock_status"] == "NOT_IN_VIEW"
    assert hot["not_in_view"] == {
        "since": "2026-11-21T14:10:00+07:00",
        "last_units": 3,
        "last_at": "2026-11-21T14:05:00+07:00",
    }
    cheese = next(p for p in _get(api, "/products")["items"] if p["sku_id"] == CHEESE)
    assert cheese["stock_status"] == "IN_STOCK" and "not_in_view" not in cheese


def test_kpi_on_shelf_units_leave_out_products_not_in_view(monkeypatch):
    # the same scenario: Hot's latest_stock row still holds 3 (Task 4)
    assert _get(api, "/kpi")["total_on_shelf_units"] == 5
    assert _get(api, "/kpi", {"store_id": "DEMO-S01"})["total_on_shelf_units"] == 5


def test_oos_now_does_not_count_a_product_not_in_view(monkeypatch):
    # the Hot-was-out-of-stock-then-the-display-moved scenario of Task 3 -> oos_now count 0
    ...
```

`_get` là cách các test `/kpi`, `/products` hiện có gọi API (theo `test_kpi_on_shelf_units_follow_the_category_and_store_filters`); dùng đúng helper sẵn có trong file.

- [ ] **Step 2: Chạy, thấy trượt**

Run: `PY -m pytest tests/test_backend_integration_moto.py -q -k "not_in_view"`
Expected: FAIL.

- [ ] **Step 3: Viết code** theo khối Interfaces.

- [ ] **Step 4: Chạy cả bộ**

Run: `PY -m pytest -q`
Expected: tất cả qua.

- [ ] **Step 5: Commit**

```bash
git add backend/api/handler.py tests/test_backend_integration_moto.py
git commit -m "API: a product whose place is not in view says so, with when it was last seen; on-shelf units leave it out"
```

---

### Task 6: Website

**Files:**
- Modify: `frontend/lib/api.ts` (kiểu sản phẩm), `frontend/lib/shelf-now.ts`, `frontend/components/reports/ShelfNowTable.tsx`, `frontend/components/reports/KpiGrid.tsx`, `frontend/components/category/CategoryProductsView.tsx`, `frontend/components/category/ProductRow.tsx`, `frontend/lib/product-groups.ts`
- Test: `frontend/lib/shelf-now.test.ts`, `frontend/lib/product-groups.test.ts`

**Interfaces:**
- Consumes: `stock_status: "NOT_IN_VIEW"` và `not_in_view: {since: string; last_units: number | null; last_at: string | null}` của `/products` (Task 5).
- Produces:
  - `lib/api.ts`: `stock_status?: "OOS" | "LOW" | "IN_STOCK" | "NOT_IN_VIEW" | null;` và `not_in_view?: { since: string; last_units: number | null; last_at: string | null } | null;`
  - `lib/shelf-now.ts`: `StockStatus` thêm `"NOT_IN_VIEW"`; `export interface NotInView { since: string; lastUnits: number | null; lastAt: string | null }`; `ShelfNowRow.notInView: NotInView | null`; thứ tự `OOS 0, LOW 1, NOT_IN_VIEW 2, IN_STOCK 3`; `ShelfNowSummary.notInView: number`, `units` không cộng dòng không thấy; `stockStatusLabel("NOT_IN_VIEW") === "Not in view"`; `notInViewText(view: NotInView, now: Date): string`.
  - `lib/product-groups.ts`: mục sản phẩm có `notInView?: boolean`; tổng số lon của nhóm không cộng mục không thấy; sắp xếp theo số lon coi mục không thấy là 0.
  - `ShelfNowTable`: màu `NOT_IN_VIEW` là `"bg-[#F3F4F6] text-[#6B7280]"`; ô số ghi `–` (giữ `data-units`), không có chữ "units"; dưới tên sản phẩm một dòng `notInViewText(...)` (`data-not-in-view`).
  - `KpiGrid`: trong thẻ "Out of stock now", cạnh dòng "Low: n", thêm `<Sub data="not-in-view-now">Not in view: {summary.notInView}</Sub>` khi lớn hơn 0.
  - Trang Category: `ProductRow` của mục không thấy ghi `–` và chữ `Not in view` thay cho số lon.

- [ ] **Step 1: Viết test trượt** (`node --test`, theo cách các test trong `shelf-now.test.ts` đang viết):

```ts
test("a product not in view comes after low stock and before in stock", () => { /* order OOS, LOW, NOT_IN_VIEW, IN_STOCK */ });
test("the summary leaves products not in view out of the units and counts them", () => {
  // rows: Cheese 5 IN_STOCK, TH NOT_IN_VIEW (unit_count 6 in the API) -> units 5, notInView 1, out 0
});
test("a product not in view reads Not in view", () => { assert.equal(stockStatusLabel("NOT_IN_VIEW"), "Not in view"); });
test("not in view says since when and what was seen last", () => {
  const now = new Date("2026-11-28T06:20:00Z"); // 13:20 in UTC+7
  assert.equal(notInViewText({ since: "2026-11-28T12:15:00+07:00", lastUnits: 6, lastAt: "2026-11-28T12:10:00+07:00" }, now),
    "since 12:15 · last seen 6 at 12:10");
  assert.equal(notInViewText({ since: "2026-11-28T12:15:00+07:00", lastUnits: 0, lastAt: "2026-11-28T12:10:00+07:00" }, now),
    "since 12:15 · was out of stock at 12:10");
  assert.equal(notInViewText({ since: "2026-11-27T20:00:00+07:00", lastUnits: 3, lastAt: "2026-11-27T19:55:00+07:00" }, now),
    "since 20:00 on 27/11 · last seen 3 at 19:55 on 27/11");
  assert.equal(notInViewText({ since: "2026-11-28T12:15:00+07:00", lastUnits: null, lastAt: null }, now), "since 12:15");
});
```

và trong `product-groups.test.ts`: `"a product not in view adds nothing to its group's units"`.

- [ ] **Step 2: Chạy, thấy trượt**

Run (trong `frontend`): `npm test`
Expected: FAIL (chưa có `notInViewText`, `NOT_IN_VIEW`).

- [ ] **Step 3: Viết code** theo khối Interfaces.

- [ ] **Step 4: Chạy kiểm**

Run (trong `frontend`): `npm test`, `npx tsc --noEmit`, `npm run build`, `npm run lint`
Expected: test qua; tsc và build sạch; lint chỉ còn 3 lỗi cũ.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/lib/shelf-now.ts frontend/lib/shelf-now.test.ts frontend/lib/product-groups.ts frontend/lib/product-groups.test.ts frontend/components/reports/ShelfNowTable.tsx frontend/components/reports/KpiGrid.tsx frontend/components/category/CategoryProductsView.tsx frontend/components/category/ProductRow.tsx
git commit -m "Website: a product whose place is not in view reads Not in view, with when it was last seen"
```

---

### Task 7: Luật ban đêm của bộ chạy thử (`ops/decide.py`)

**Files:**
- Modify: `ops/decide.py` (`night_rate`, hằng số mới cạnh `NIGHT_FRAMES`)
- Test: `tests/test_ops_decide.py`

**Interfaces:**
- Consumes: `PRODUCTS_MIN_BOXES`, `PRODUCTS_MIN_CONF` của `backend/shelf.py` (chỉ trong test).
- Produces: `LIVE_SHELF_BOXES = 3`, `LIVE_SHELF_CONF = 0.8` trong `ops/decide.py`; `night_rate` chỉ tính capture `display_visible is False` mà `detections_json` (bản live) có dưới `LIVE_SHELF_BOXES` hộp có `sku_id` với `conf >= LIVE_SHELF_CONF`.

- [ ] **Step 1: Viết test trượt** trong `tests/test_ops_decide.py`:

```python
def test_night_rate_leaves_out_frames_where_the_live_release_sees_the_shelf():
    # 28/11 12:15: the display moved out of the zone; the live release still saw its cans there
    shelf_frames = [
        {**c, "detections_json": json.dumps([HOT] * 3)} for c in night_captures(100, boxes=100, version="v2")
    ]
    assert night_rate(shelf_frames, "v2") is None  # not night frames: fewer than NIGHT_FRAMES left
    assert night_rate(night_captures(100, boxes=2, version="v2") + shelf_frames, "v2") == 2.0


def test_the_night_rule_and_the_shelf_numbers_agree():
    # the backend's rule for "the shelf is in view" (backend/shelf.py), imported by path
    assert (LIVE_SHELF_BOXES, LIVE_SHELF_CONF) == (shelf.PRODUCTS_MIN_BOXES, shelf.PRODUCTS_MIN_CONF)
```

(`shelf` nạp bằng `sys.path.insert(0, str(ROOT / "backend"))` như `tests/test_shelf.py`.)

- [ ] **Step 2: Chạy, thấy trượt**

Run: `PY -m pytest tests/test_ops_decide.py -q`
Expected: FAIL (`ImportError` của `LIVE_SHELF_BOXES`).

- [ ] **Step 3: Viết code** theo khối Interfaces.

- [ ] **Step 4: Chạy lại, rồi cả bộ**

Run: `PY -m pytest -q`
Expected: tất cả qua.

- [ ] **Step 5: Commit**

```bash
git add ops/decide.py tests/test_ops_decide.py
git commit -m "Ops: the night rule leaves out frames where the live release still sees the shelf"
```

---

### Task 8: Chạy lại chỉ đọc trên capture thật, và kiểm cuối

**Files:**
- Create: `scripts/shelf_replay.py`

**Interfaces:**
- Consumes: `shelf.build_check`, `shelf.rollup`, `shelf.totals` và `ingest.handler._apply_check` (Task 3), nạp bằng `sys.path` tới `backend/` như các test.
- Produces: lệnh `PY scripts/shelf_replay.py --profile default --region ap-southeast-1 --store DEMO-S01 --from 2026-11-21 --to 2026-11-28`. Chỉ đọc: `store-list`, `captures` của các camera của cửa hàng (camera lấy từ `latest_stock` như `_store_cameras`). Không ghi gì lên AWS.
  - Dựng lần kiểm 5 phút của từng bucket bằng `shelf.build_check`, rồi chạy `_apply_check` hai lượt trên cùng các lần kiểm: **luật mới** (code của nhánh), và **luật cũ** (tạm thay `shelf.sees_shelf` bằng `shelf.sees_display` và `shelf.ARRANGEMENT_JUMP_PX` bằng `float("inf")` trong process, rồi dựng lại lần kiểm).
  - In theo từng ngày: số lần kiểm đo được (cũ/mới), mỗi lần đổi cách bày (bucket, camera, khoảng cách px), các SKU không thấy và từ lúc nào, số sự kiện theo loại (cũ/mới) kèm sự kiện mới trong khoảng 21:00–06:30, OSA (cũ/mới) bằng `shelf.totals` trên các `rollup` theo giờ.

- [ ] **Step 1: Viết script** theo khối Interfaces (không cần unit test; đầu ra được đọc và báo lại).

- [ ] **Step 2: Chạy trên dữ liệu thật**

Run: `PY scripts/shelf_replay.py --profile default --region ap-southeast-1 --store DEMO-S01 --from 2026-11-21 --to 2026-11-28`
Expected (spec mục 9.2): cách bày đổi đúng một lần mỗi lần dời thật (28/11 12:15, và lúc dời về nếu đã có) và không lần nào khác; từ 28/11 12:15 Slide được đo, TH là không thấy; không sự kiện nào lúc 12:15; không có sự kiện hết hàng hay bổ sung hàng mới trong 21:00–06:30. Dán đầu ra vào sổ. Nếu đầu ra khác điều trên thì dừng và báo người điều phối, không chỉnh ngưỡng.

- [ ] **Step 3: Kiểm cuối toàn nhánh**

Run: `PY -m pytest -q`; `PY -m ruff check .`; `PY -m ruff format --check .`; trong `frontend`: `npm test`, `npx tsc --noEmit`, `npm run build`, `npm run lint`.
Expected: pytest qua hết; ruff sạch; frontend như Task 6.

- [ ] **Step 4: Commit**

```bash
git add scripts/shelf_replay.py
git commit -m "Scripts: replay the shelf checks of real captures with the old and the new rules, read-only"
```

---

## Không nằm trong đợt build này: deploy (sau khi phần 1 đóng, hoang duyệt riêng)

1. **Nền của nhánh.** Nhánh này chứa các commit của phần 3. Nếu phần 3 chưa được duyệt deploy thì rebase các commit của nhánh này lên `feat/ops-loop-part1` trước, chạy lại kiểm cuối.
2. **Backend:** gói Lambda (`package_lambdas.py` của bộ công cụ, xác nhận `shelf.py` có trong cả gói API và ingest), change set chỉ đổi code bằng `backend_changeset.sh`; không bao giờ `--tags` trên stack backend.
3. **Website:** Amplify, như các lần trước.
4. **HUYHOANG:** bundle nhánh tới clone, chỉ khởi động lại task `milk-ops` (không đụng `milk-worker`).
5. **Tính lại:** đặt `shelf_recompute_requested_at` cho DEMO-S01, chờ một lượt tick.
6. **Kiểm trên live:** `/products`, `/kpi`, Dashboard (bước kiểm viewer `opt2_run.py`), hàng đợi lỗi trống, log ingest không lỗi; báo hoang OSA trước/sau.
