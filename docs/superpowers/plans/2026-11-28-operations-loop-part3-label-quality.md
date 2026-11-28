# Vòng vận hành, phần 3: chất lượng nhãn và cho người làm thấy — kế hoạch làm

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Một reading được sửa kéo frame của nó vào hàng chờ gán nhãn; người gán thấy nhãn của mình đang ở đâu; `team_admin` thấy độ khớp của từng người gán, đo bằng frame có đáp án mà người gán không được báo trước.

**Architecture:** Mọi thứ nằm trong hai Lambda đã có (`api`, `ingest`) và trang Model, không thêm Lambda, không thêm bảng. Lần sửa ghi một "yêu cầu frame" lên chính dòng correction; luật mỗi giờ của `ingest` phục vụ yêu cầu đó bằng suất frame dạy của giờ, nên số frame mỗi ngày không tăng. Frame có đáp án là một frame đã chấm mà `team_admin` đánh dấu; mỗi người gán nhận một "tờ kiểm" riêng (dòng `CHK-` trong bảng audits) sau mỗi 9 frame, và câu trả lời trên tờ kiểm không bao giờ ghi đè đáp án. Độ khớp và các câu hiển thị là hàm thuần, test không cần AWS.

**Tech Stack:** Python 3.12, boto3, pytest, moto. Next.js (đọc `frontend/AGENTS.md` và `node_modules/next/dist/docs/` trước khi sửa frontend), test frontend bằng `node --test` trên `frontend/lib/*.test.ts`. CloudFormation (`infra/backend.yaml`).

**Spec:** `docs/superpowers/specs/2026-11-27-operations-loop-design.md`, mục 5.4, dòng "Chất lượng nhãn và hiển thị" ở mục 5.7, mục 5.8 và 5.9. hoang duyệt spec ngày 27/11. Ngày 28/11 hoang nói *"ok làm những việc có thể làm bây giờ"* sau khi Claude đề xuất viết kế hoạch phần 3 rồi xây trên nhánh, chưa deploy.

## Những điều Claude tự quyết trong kế hoạch này

hoang đổi được mọi điều dưới đây. Điều 4 đổi câu chữ của spec 5.4, nên cần hoang gật trước khi làm Task 5.

1. **Tín hiệu 2 và 4 của spec chưa làm.** Tín hiệu 2 (kho ảnh nói "không chắc") không có nguồn: phép đo 28/11 cho thấy kho không được bật. Tín hiệu 4 (kiểu xếp hàng mới theo `segments.py`) cần chuỗi chia đoạn chạy tự động, tức phần 4. Phần này làm tín hiệu 1 (reading bị sửa), 3 (số đếm nhảy trong một cửa sổ) và 5 (ngẫu nhiên).
2. **Yêu cầu frame được phục vụ bằng suất frame dạy của giờ kế tiếp,** mỗi camera mỗi giờ một yêu cầu, cũ nhất trước. Nhờ vậy số frame mỗi ngày không tăng, đúng spec. Frame của reading có thể thuộc một giờ trước đó; audit vẫn mang id của giờ đang lấy mẫu (`TRN-<camera>-<giờ>`).
3. **Số của tín hiệu "đếm nhảy":** hai capture cách nhau quá 60 giây thuộc hai cửa sổ; độ nhảy của một capture là chênh lệch lớn nhất, trên mọi sản phẩm, giữa số đếm của nó và trung vị của cửa sổ; dưới 2 đơn vị thì không coi là tín hiệu.
4. **Đáp án do một `team_admin` đánh dấu, không lấy từ "hai người chấm giống nhau".** Lý do: ngày 28/11, 7 trong 9 box "Cheese" Claude xem bằng mắt là lon Original mà người chấm đã bấm "đúng" theo tên model gợi ý, và cùng một lon được hai frame cách nhau 5 phút gọi hai tên. Hai người cùng bấm theo gợi ý thì vẫn khớp nhau, nên "khớp nhau" không phải là đáp án. Đáp án vẽ tay (`truth.json`) chỉ có cho 23–25/11 và không nằm trong bảng audits, nên cũng không dùng trực tiếp được.
5. **Tờ kiểm là dòng riêng trong bảng audits, id `CHK-<8 ký tự>`,** chép ảnh và box của frame đáp án, gán cho đúng một người. Code đọc nhãn để train chỉ nhận `TRN-` và `REV-` (kho ảnh của phần 2, chưa bật, nhận thêm `CMP-`), và các con số trên trang Model chỉ nhận `AUD-`, nên tờ kiểm không lọt vào đâu cả. *Sửa sau bản soát 28/11:* câu "giao diện không in id nên người gán không thấy khác biệt" trong bản đầu là chưa đủ. Xem mục "Sau bản soát ngày 28/11" bên dưới.
6. **Nhịp kiểm:** sau 9 frame một người lưu thì frame kế là tờ kiểm (1 trong 10, số của spec). Không có đáp án phù hợp thì không có tờ kiểm, và lần lưu vẫn thành công.
7. **Cách tính độ khớp:** đơn vị là từng box của frame, từng điểm sót của đáp án, và từng điểm sót thừa của người gán. Box khớp khi cùng verdict và, với "sai tên", cùng tên đúng. Điểm sót khớp khi cùng sản phẩm và cách điểm của đáp án không quá 40 px (nắp lon ở CAM-S01-A rộng 60–80 px trên frame 2560×1440).
8. **Chưa làm ở phần này: giữ nhãn của người có độ khớp thấp chờ người thứ hai.** Spec nói ngưỡng do người làm đề xuất sau vài tuần có số, và nơi dùng nhãn (tập train) thuộc phần 4. Phần này chỉ đo và hiển thị.
9. **Chưa làm ở phần này: `fed_back_to_model = true`, câu "đã vào bản X", danh sách nhãn đáng ngờ.** Cả ba chỉ có nghĩa khi một lần train dùng nhãn của người, tức phần 4. Câu trên trang Model nói thật là chưa bản live nào dùng nhãn của người.
10. **Backend từ chối một lần sửa không đổi gì** (`NOTHING_CHANGED`), để luật "Save Correction không lưu khi không đổi gì" không chỉ nằm ở trình duyệt.
11. **Thẻ sản phẩm mở từ hàng chờ có nút "Confirm reading"** khi người dùng không đổi gì. Spec nói "khi đó dùng Confirm"; nút Confirm hiện chỉ có ở danh sách hàng chờ.

**Không nằm trong kế hoạch này:**
- Biến điểm sót trên frame dạy thành box để train (phần 4; xem đề xuất B3 dưới đây).
- Mọi thay đổi luật gán nhãn (đề xuất B1, B2).
- Deploy: Task 8 chỉ chạy khi hoang duyệt, và sau khi phần 1 đóng.

## Sau bản soát ngày 28/11

Một người soát độc lập đọc cả nhánh sau Task 7. Không có lỗi nghiêm trọng; bốn lỗi quan trọng đã sửa trên nhánh, mỗi lỗi có test trượt trước:

- **Một capture không bao giờ vừa là frame dạy vừa là frame chấm điểm.** Yêu cầu frame của một reading thuộc giờ muộn hơn giờ đang lấy mẫu phải chờ lượt của chính giờ đó. Lượt rút frame chấm điểm và frame dạy bỏ qua capture đã là một frame gán nhãn.
- **Yêu cầu không phục vụ được thì được đóng, kèm lý do.** Chỉ một capture id đúng dạng mới sinh yêu cầu (thẻ không có reading gửi "—"). Dòng capture hết hạn sau 7 ngày (`CAPTURE_TTL_DAYS`), sớm hơn hạn giữ ảnh, nên yêu cầu cho reading cũ hơn thế bị đóng với ghi chú. Một yêu cầu gây lỗi không chặn các yêu cầu sau. Câu báo đổi thành "Its frame is in line for the labelling queue."
- **Tờ kiểm đọc như mọi frame.** Hàng chờ xếp theo lúc frame vào hàng (`queue_at`), không theo lúc chụp, nên tờ kiểm đến như frame mới nhất. Sau mỗi lần lưu, màn gán nhãn lấy thêm các frame vừa vào hàng, nên tờ kiểm xuất hiện ngay trong phiên. Tiêu đề chỉ hiện capture id, giờ chụp và tên model cho `team_admin`. Câu báo lỗi không in id. `picked_by` và `correction_id` không gửi về trình duyệt. Tờ kiểm được dựng từ đáp án có ảnh chụp mới nhất.
- **Khi một người hết đáp án, `team_admin` được báo.** Mỗi đáp án chỉ kiểm một người một lần. Khối độ khớp nêu tên những người không còn đáp án nào, và câu giải thích nói rõ điều kiện đó.

**Giới hạn còn lại, đã biết:** ảnh của camera in sẵn ngày giờ, nên một frame đáp án cũ vẫn có thể bị nhận ra giữa các frame hôm nay. Muốn "1 trong 10" giữ được, `team_admin` phải đánh dấu đáp án mới đều đặn, khoảng một đáp án cho mỗi mười frame mỗi người gán. `team_admin` cũng gán nhãn thì có thể nhận ra tờ kiểm của chính mình qua danh sách đáp án.

## Đề xuất bổ sung từ phát hiện ngày 28/11 — chưa duyệt, chưa có task

Số liệu và ảnh: `C:\Users\huyho\milk_store_labels\ops_loop_tools_20261127\day2_20261128\missed\`.

- **B1. Cho phép "không thấy vị" khi đánh dấu lon sót.** Hiện một điểm sót bắt buộc mang tên sản phẩm (`validate_labels`), nên người gán phải đoán vị khi chỉ thấy nắp. Bằng chứng: 7 cặp điểm cùng chỗ, hai frame cách nhau dưới 30 phút, mang hai tên khác nhau (trên 47 cặp). Cần hoang quyết vì nó đổi cách đếm.
- **B2. Luật cho lon bị che** (dưới túi kẹo, sau hộp nhựa trong, sau lưới): có đánh dấu sót hay không. 42 trong 227 điểm sót thuộc loại này theo cách đọc của Claude.
- **B3. Phần 4 phải đọc điểm sót trên frame dạy.** Hiện 180 điểm trên frame `TRN-` không được code nào đọc. Với cài đặt không đổi so với lần thử 25/11, YOLOE đề xuất được một box mới cho 93/163 điểm Slide trên frame dạy (57%); các điểm còn lại cần che xám để model không học chúng là nền.

## Global Constraints

- Số frame đưa cho người mỗi ngày không tăng so với hiện nay, trừ frame so sánh khi có ứng viên (tối đa 8).
- Một lần sửa không dạy thẳng cho model. Nó chỉ đưa frame của reading lên đầu hàng chọn frame dạy.
- Người gán không được báo frame nào là frame có đáp án. Không chữ nào trên giao diện, không trường nào trong câu trả lời của API cho người không phải `team_admin`, nói một frame là tờ kiểm.
- Độ khớp của từng người chỉ `team_admin` thấy. Áp dụng cho mọi người gán, kể cả người của client.
- Chỉ nói nhãn "đã vào" một bản khi bản đó đã live.
- Frame chấm điểm (`AUD-`) không bao giờ thành dữ liệu dạy. Tờ kiểm (`CHK-`) không bao giờ thành dữ liệu dạy và không bao giờ vào số của trang Model.
- Giao diện bằng tiếng Anh, như cả website từ 26/11.
- Không thêm Lambda, không thêm bảng. Thay đổi template duy nhất: một dòng biến môi trường cho Lambda `ingest`.
- Không ai tự gán nhãn thay người: test dùng dữ liệu dựng trong moto, kiểm tra trên live dùng frame và reading thật do người trong nhóm xử lý.
- Ảnh tiệm và nhãn không vào repo, cũng không vào OneDrive.
- Python 3.12. Chạy `python -m pytest -q`, rồi `ruff check .` và `ruff format --check .`. Frontend: trong `frontend/`, `npm test`, `npm run lint`, `npm run build`. Template: `cfn-lint infra/backend.yaml`.
- Commit bằng danh tính noreply: `git -c user.name="Nguyen Huy Hoang" -c user.email=193206418+Protein-17012006@users.noreply.github.com commit …`. Không push khi hoang chưa bảo.
- Mỗi lần lên live phải chờ hoang OK. Backend lên bằng change set, không bao giờ `--tags`.

## Review Focus

1. **Frame của reading được sửa đã hết hạn giữ (30 ngày) hoặc không có ảnh:** yêu cầu bị đóng với ghi chú, và giờ đó vẫn có frame dạy của nó. Test ở Task 3.
2. **Hai lần sửa cho cùng một reading, hoặc sửa một reading mà frame đã nằm trong hàng chờ:** chỉ một frame, cả hai lần sửa đều được ghi là đã vào hàng. Test ở Task 3.
3. **Người gán không có đáp án nào phù hợp** (chính họ đã chấm hoặc đánh dấu mọi đáp án): không có tờ kiểm, lần lưu vẫn thành công. Test ở Task 5.
4. **Tờ kiểm của người này hiện trong hàng chờ, số đếm "pending", hoặc số của trang Model của người khác:** không bao giờ. Test ở Task 5.
5. **Frame đáp án bị gán lại sau khi đã có tờ kiểm:** độ khớp vẫn so với bản đáp án chép lúc đánh dấu. Test ở Task 5 và Task 6.

## File Structure

| File | Việc |
|---|---|
| `backend/label_signals.py` (mới) | Hàm thuần: chia cửa sổ, độ nhảy của số đếm, chọn frame dạy |
| `backend/label_checks.py` (mới) | Hàm thuần: khi nào tới lượt kiểm, đáp án nào hợp với ai, dựng tờ kiểm |
| `backend/label_agreement.py` (mới) | Hàm thuần: so một tờ kiểm với đáp án, gộp theo người và tuần |
| `backend/api/handler.py` | Lần sửa ghi yêu cầu frame; đánh dấu đáp án; lọc tờ kiểm; phát tờ kiểm sau khi lưu; `GET /model/labellers`; `GET /model/my-labels` |
| `backend/ingest/handler.py` | `sample_frames` phục vụ yêu cầu rồi tới tín hiệu đếm nhảy rồi ngẫu nhiên |
| `infra/backend.yaml` | `CORRECTIONS_TABLE` cho Lambda `ingest` |
| `frontend/lib/review-queue.ts`, `model-ui.ts`, `model-versions.ts`, `api.ts` | Hàm thuần cho chữ và điều kiện nút; kiểu dữ liệu và lời gọi API mới |
| `frontend/components/category/ProductDetailsModal.tsx`, `CategoryProductsView.tsx` | Nút Save Correction, Confirm reading, câu báo |
| `frontend/components/model/LabellerAgreement.tsx` (mới), `ModelQualityView.tsx`, `AuditLabeler.tsx`, `ModelVersions.tsx` | Khối độ khớp, dòng "Your labels", ô "Use as answer key", dòng nhãn của mỗi bản |
| `tests/test_label_signals.py`, `tests/test_label_checks.py`, `tests/test_label_agreement.py` (mới), `tests/test_backend_integration_moto.py` | Test |

---

### Task 1: Lần sửa ghi yêu cầu frame, và không lưu khi không đổi gì

**Files:**
- Modify: `backend/api/handler.py` (`_handle_post_correction`)
- Test: `tests/test_backend_integration_moto.py`

**Interfaces:**
- Produces: dòng correction có `label_request = "pending"` khi lần sửa có `capture_id`; câu trả lời `201` có khoá `label_request` (`"pending"` hoặc `null`). Task 3 đọc `label_request`, Task 4 đọc câu trả lời.

- [ ] **Step 1: Viết ba test, đặt cạnh `test_a_correction_without_a_key_leaves_the_queue_item_waiting`**

```python
@mock_aws
def test_a_correction_asks_for_the_frame_of_its_reading(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "140010", [("hot160", 1)], with_frame=True)
    body = {
        "store_id": "DEMO-S01",
        "capture_id": "CAP-S01-20261121-140010",
        "sku_id": HOT,
        "corrected_sku_id": CHEESE,
        "action": "correct",
    }
    status, out = _call(api, "POST", "/v1/corrections", groups="field_team", body=body)
    assert (status, out["label_request"]) == (201, "pending")
    (saved,) = _table("test-corrections").scan()["Items"]
    assert saved["label_request"] == "pending"


@mock_aws
def test_a_correction_without_a_capture_asks_for_no_frame(monkeypatch: pytest.MonkeyPatch):
    api, _ = _backend(monkeypatch)
    body = {"store_id": "DEMO-S01", "sku_id": HOT, "corrected_sku_id": CHEESE, "action": "correct"}
    status, out = _call(api, "POST", "/v1/corrections", groups="field_team", body=body)
    (saved,) = _table("test-corrections").scan()["Items"]
    assert (status, out["label_request"]) == (201, None) and "label_request" not in saved


@mock_aws
def test_a_correction_that_changes_nothing_is_refused(monkeypatch: pytest.MonkeyPatch):
    api, _ = _backend(monkeypatch)
    for body in (
        {
            "store_id": "DEMO-S01",
            "sku_id": HOT,
            "corrected_sku_id": HOT,
            "discrepancy_category": "None",
            "action": "correct",
        },
        {"store_id": "DEMO-S01", "sku_id": HOT, "corrected_sku_id": "", "action": "correct"},
    ):
        status, out = _call(api, "POST", "/v1/corrections", groups="field_team", body=body)
        assert (status, out["error"]) == (400, "NOTHING_CHANGED")
    assert _table("test-corrections").scan()["Items"] == []
```

- [ ] **Step 2: Chạy, thấy trượt.** `python -m pytest tests/test_backend_integration_moto.py -q -k "correction"`. Ba test mới trượt (`KeyError: 'label_request'`, `201 != 400`).

- [ ] **Step 3: Sửa `_handle_post_correction`.** "Không đổi gì" là: `corrected_sku_id` rỗng hoặc bằng `sku_id`, **và** `discrepancy_category` vắng, rỗng hoặc `"None"`, **và** `corrected_unit_count` là `None`. Luật này chỉ áp cho `action == "correct"`; `"confirm"` giữ nguyên. Câu trả lời 400 có `message`: `"Nothing was changed. Use Confirm to accept the reading as it is."`. Lưu ý dòng hiện có `"discrepancy_category": body.get("discrepancy_category") or "Wrong SKU"`: phải xét "không đổi gì" trên giá trị thô của body, trước dòng đó.

- [ ] **Step 4: Chạy lại, thấy qua,** kể cả hai test correction cũ. Rồi `python -m pytest -q`.

- [ ] **Step 5: Commit** `Corrections: a correction asks for the frame of its reading; one that changes nothing is refused`.

### Task 2: Tín hiệu chọn frame dạy (hàm thuần)

**Files:**
- Create: `backend/label_signals.py`
- Test: `tests/test_label_signals.py`

**Interfaces:**
- Produces:
  - `WINDOW_GAP_S = 60`, `JUMP_MIN = 2`
  - `windows(items: list[dict]) -> list[list[dict]]` — capture theo thứ tự `capture_timestamp`, cắt chỗ hai capture liền nhau cách quá `WINDOW_GAP_S` giây.
  - `count_jumps(items: list[dict], boxes_of: Callable[[dict], list[dict]]) -> dict[str, int]` — `capture_id` → độ nhảy. `boxes_of(item)` trả các box, mỗi box có `sku_id` (có thể `None`, bỏ qua).
  - `pick_training(seeing: list[dict], jumps: dict[str, int], rng: random.Random) -> tuple[dict, str]` — `(capture, "count_jump" | "random")`.

- [ ] **Step 1: Viết test.** Dựng capture bằng một hàm phụ `cap(hhmmss: str, **counts)` trả `{"capture_id": f"CAP-S01-20261121-{hhmmss}", "capture_timestamp": "2026-11-21T14:..:..+07:00", "boxes": [{"sku_id": sku}] * n ...}` và `boxes_of = lambda it: it["boxes"]`.

```python
def test_a_gap_of_more_than_a_minute_starts_a_new_window():
    items = [cap("140000"), cap("140010"), cap("140500"), cap("140505")]
    assert [[c["capture_id"][-6:] for c in w] for w in windows(items)] == [["140000", "140010"], ["140500", "140505"]]


def test_the_frame_that_strays_from_its_window_has_the_jump():
    items = [cap("140000", hot160=5), cap("140005", hot160=5), cap("140010", hot160=2), cap("140015", hot160=5)]
    assert count_jumps(items, boxes_of) == {
        items[0]["capture_id"]: 0,
        items[1]["capture_id"]: 0,
        items[2]["capture_id"]: 3,
        items[3]["capture_id"]: 0,
    }


def test_a_window_of_one_frame_has_no_jump():
    assert count_jumps([cap("140000", hot160=7)], boxes_of) == {"CAP-S01-20261121-140000": 0}


def test_a_product_missing_from_one_frame_counts_as_zero_there():
    items = [cap("140000", hot160=3, cheese145=2), cap("140005", hot160=3), cap("140010", hot160=3, cheese145=2)]
    assert count_jumps(items, boxes_of)[items[1]["capture_id"]] == 2


def test_the_largest_jump_is_picked():
    items = [cap("140000", hot160=5), cap("140005", hot160=5), cap("140010", hot160=2)]
    assert pick_training(items, count_jumps(items, boxes_of), random.Random(0)) == (items[2], "count_jump")


def test_a_jump_of_one_is_not_a_signal_and_the_draw_is_the_plain_one():
    items = [cap("140000", hot160=5), cap("140005", hot160=4), cap("140010", hot160=5)]
    assert pick_training(items, count_jumps(items, boxes_of), random.Random(7)) == (
        random.Random(7).choice(items),
        "random",
    )
```

- [ ] **Step 2: Chạy, thấy trượt** (`ModuleNotFoundError: label_signals`). `python -m pytest tests/test_label_signals.py -q`.

- [ ] **Step 3: Viết `backend/label_signals.py`.** Trung vị dùng `statistics.median`; độ nhảy làm tròn lên số nguyên (`math.ceil`). Khi không có độ nhảy nào đạt `JUMP_MIN`, `pick_training` gọi `rng.choice(seeing)` **đúng một lần** và không gọi `rng` lần nào khác: các test lấy mẫu cũ dựa vào chuỗi số của `random.Random(seed)`. Khi nhiều capture cùng độ nhảy lớn nhất, lấy capture có `capture_id` nhỏ nhất (không gọi `rng`).

- [ ] **Step 4: Chạy lại, thấy qua.**

- [ ] **Step 5: Commit** `Label signals: windows, count jumps and the choice of the training frame`.

### Task 3: Luật mỗi giờ phục vụ yêu cầu frame, rồi tới tín hiệu

**Files:**
- Modify: `backend/ingest/handler.py` (`sample_frames`, `_write_frame_audit`; hằng `CORRECTIONS_TABLE`)
- Modify: `infra/backend.yaml` (khối `Environment` của `IngestLambda`: thêm `CORRECTIONS_TABLE: !Ref CorrectionsTable`; role dùng chung đã có quyền trên bảng này)
- Test: `tests/test_backend_integration_moto.py`

**Interfaces:**
- Consumes: `label_request == "pending"` trên dòng correction (Task 1); `label_signals.count_jumps`, `pick_training` (Task 2); `capture_boxes` đã import sẵn từ `model_health`.
- Produces: audit `TRN-` có thêm `picked_by` (`"correction" | "count_jump" | "random"`) và, khi do lần sửa, `correction_id`. Dòng correction chuyển sang `label_request = "queued"` kèm `label_audit_id`, hoặc `"dropped"` kèm `label_request_note`.

- [ ] **Step 1: Viết test** (cạnh `test_an_hour_gives_a_scoring_frame_and_a_training_frame`). Hàm phụ `_correct(api, capture_id)` gọi `POST /v1/corrections` như Task 1 và trả `correction_id`.

```python
@mock_aws
def test_a_corrected_reading_becomes_the_next_training_frame(monkeypatch: pytest.MonkeyPatch):
    api, ingest = _backend(monkeypatch)
    _ingest(ingest, "CAM-S01-A", "130500", [("hot160", 1)], with_frame=True)
    for t in ("140700", "141200"):
        _ingest(ingest, "CAM-S01-A", t, [("hot160", 2)], with_frame=True)
    cid = _correct(api, "CAP-S01-20261121-130500")
    ingest.lambda_handler({"action": "sample_audits", "hour": "20261121-14"})
    trn = _audits()[TRN_14]
    assert (trn["capture_id"], trn["picked_by"], trn["correction_id"]) == ("CAP-S01-20261121-130500", "correction", cid)
    (corr,) = _table("test-corrections").scan()["Items"]
    assert (corr["label_request"], corr["label_audit_id"]) == ("queued", TRN_14)
```

Thêm bốn test nữa, cùng kiểu:
- `test_a_request_for_a_frame_already_in_the_queue_makes_no_second_frame`: lấy mẫu giờ 13 trước, sửa đúng capture của `TRN-…-13`, lấy mẫu giờ 14. Kết quả: `TRN_14` là một capture của giờ 14 với `picked_by == "random"`; correction `queued` với `label_audit_id == "TRN-CAM-S01-A-20261121-13"`.
- `test_a_request_whose_frame_is_gone_is_dropped_and_the_hour_keeps_its_frame`: xoá object ảnh của capture giờ 13 khỏi `test-hub-bucket` trước khi lấy mẫu giờ 14. Kết quả: correction `dropped`, `label_request_note == "the frame is no longer kept"`; `TRN_14` vẫn có, từ giờ 14.
- `test_two_corrections_of_one_reading_give_one_frame`: hai lần sửa cùng capture; sau giờ 14 cả hai `queued` cùng `label_audit_id`, và bảng audits chỉ có hai dòng.
- `test_the_frame_whose_count_jumps_is_the_training_frame`: ba capture trong một phút, số Hot là 5, 5, 2. Gọi thẳng `ingest.sample_frames` với 20 seed như test `test_the_training_frame_is_never_a_capture_that_hides_the_display`: khi frame chấm điểm không lấy mất capture "2", frame dạy phải là capture "2" với `picked_by == "count_jump"`.

- [ ] **Step 2: Chạy, thấy trượt.** `python -m pytest tests/test_backend_integration_moto.py -q -k "request or corrected or jumps or two_corrections"`.

- [ ] **Step 3: Sửa `ingest`.**
  - `CORRECTIONS_TABLE = os.environ.get("CORRECTIONS_TABLE", "")`. Không đặt thì không có yêu cầu nào (Lambda chưa có biến này vẫn chạy như cũ).
  - `_write_frame_audit(..., extra: dict[str, Any] | None = None)`: các khoá của `extra` được ghi thêm vào audit.
  - `pending_requests(ddb_resource, store_id: str) -> list[dict[str, Any]]`: Query bảng corrections theo `store_id`, giữ dòng `label_request == "pending"`, xếp theo `correction_id` tăng dần.
  - Trong `sample_frames`, ở nhánh tạo frame dạy, trước khi chọn theo tín hiệu, duyệt các yêu cầu theo thứ tự:
    1. capture không thuộc camera này (không có dòng `camera_id` + `capture_id` trong bảng captures): bỏ qua, để nguyên `pending`;
    2. capture không có `image_key`, hoặc `display_visible is False`: đóng `dropped`, ghi chú `"the reading has no usable frame"`;
    3. đã có audit nào của store mang `capture_id` này (kể cả frame chấm điểm vừa tạo của giờ này): đóng `queued` với id của audit đó;
    4. còn lại: ghi `TRN-` của giờ từ capture này với `extra={"picked_by": "correction", "correction_id": …}`. `copy_object` báo `NoSuchKey` hoặc `404` thì đóng `dropped`, ghi chú `"the frame is no longer kept"`, và xét yêu cầu kế. Ghi được thì đóng `queued` với id `TRN-` này, đóng luôn mọi yêu cầu `pending` khác của cùng capture, rồi dừng duyệt.
  - Không yêu cầu nào thành frame thì: `pick, picked_by = label_signals.pick_training(seeing, label_signals.count_jumps(seeing, capture_boxes), rng)` và ghi với `extra={"picked_by": picked_by}`.
  - Một lỗi khi đọc hay đóng yêu cầu không được làm mất frame dạy của giờ: bọc phần duyệt yêu cầu, in một dòng JSON `{"label_request_failed": …}` và rơi xuống nhánh tín hiệu.

- [ ] **Step 4: Thêm dòng biến môi trường vào `infra/backend.yaml`,** chạy `cfn-lint infra/backend.yaml`.

- [ ] **Step 5: Chạy `python -m pytest -q`.** Mọi test lấy mẫu cũ phải qua mà không sửa.

- [ ] **Step 6: Commit** `Hourly rule: the training frame serves a correction's request first, then a count jump, then chance`.

### Task 4: Trang Category — Save Correction, Confirm reading, câu báo

**Files:**
- Modify: `frontend/lib/review-queue.ts`, `frontend/lib/review-queue.test.ts`, `frontend/lib/api.ts`
- Modify: `frontend/components/category/ProductDetailsModal.tsx`, `frontend/components/category/CategoryProductsView.tsx`

**Interfaces:**
- Consumes: khoá `label_request` trong câu trả lời của `POST /corrections` (Task 1).
- Produces (trong `review-queue.ts`):
  - `correctionChanged(modelLabel: string, expectedLabel: string, mismatchType: string): boolean`
  - `correctionToast(checkedOff: boolean, labelRequest: string | null | undefined): string`

- [ ] **Step 1: Viết test trong `review-queue.test.ts`.**

```ts
test("a correction counts as changed only when the label or the mismatch type moved", () => {
  assert.equal(correctionChanged("Slide Hot & Spicy 160g", "Slide Hot & Spicy 160g", "None"), false);
  assert.equal(correctionChanged("Slide Hot & Spicy 160g", "", "None"), false);
  assert.equal(correctionChanged("Slide Hot & Spicy 160g", "Slide Cheese 145g", "None"), true);
  assert.equal(correctionChanged("Slide Hot & Spicy 160g", "Slide Hot & Spicy 160g", "Wrong count"), true);
});

test("the toast says what happened to the queue item and to the frame", () => {
  assert.equal(correctionToast(false, null), "Saved the correction.");
  assert.equal(correctionToast(true, null), "Saved the correction. The reading is checked off in the review queue.");
  assert.equal(
    correctionToast(false, "pending"),
    "Saved the correction. Its frame goes to the labelling queue within the hour."
  );
});
```

- [ ] **Step 2: Chạy `npm test` trong `frontend/`, thấy trượt.**

- [ ] **Step 3: Viết hai hàm.** `correctionChanged` phải cho cùng kết quả với luật backend của Task 1 trên cái frontend gửi (`sku_id = modelLabel`, `corrected_sku_id = expectedLabel`, `discrepancy_category = mismatchType`).

- [ ] **Step 4: Sửa hai component.**
  - `onSaveAudit` trả `Promise<boolean>` (đúng khi backend nhận). `handleSaveAudit` trả `false` ở mọi nhánh lỗi; hiện nay thẻ vẫn báo "Saved ✓" khi lời gọi API hỏng.
  - Nút "Save Correction": `disabled` khi `!correctionChanged(...)` hoặc đang lưu; đang lưu thì chữ là "Saving…". "Saved ✓" và đóng thẻ chỉ khi kết quả là `true`.
  - Khi chưa đổi gì: dưới nút có dòng `data-nothing-changed`: "Nothing changed yet. Change the label or the mismatch type to save a correction." Nếu thẻ mở từ hàng chờ (`product.reviewQueueKey`), thêm nút "Confirm reading" gọi prop mới `onConfirm?: () => Promise<boolean>`; `CategoryProductsView` nối nó với `api.submitCorrection({ store_id, queue_key, action: "confirm" })`, cùng toast và cùng tải lại như `confirmQueueItem`.
  - Toast sau khi lưu dùng `correctionToast(Boolean(queueKey), res.label_request)`.
  - `ApiCorrectionResponse` (hoặc kiểu trả về của `submitCorrection`) thêm `label_request?: "pending" | null`.

- [ ] **Step 5: `npm test`, `npm run lint`, `npm run build`.** Cả ba sạch.

- [ ] **Step 6: Commit** `Category: Save Correction only saves a change, waits for the answer, and says where the frame goes`.

### Task 5: Frame đáp án và tờ kiểm (backend)

**Files:**
- Create: `backend/label_checks.py`
- Modify: `backend/api/handler.py` (`_handle_model_audits`, `_handle_model_audit_get`, `_handle_model_audit_put`, `_handle_model_audit_skip`, `_audit_view`, bảng route)
- Test: `tests/test_label_checks.py`, `tests/test_backend_integration_moto.py`

**Interfaces:**
- Produces (`label_checks.py`):
  - `CHECK_EVERY = 10`, `SHEET_PREFIX = "CHK-"`
  - `is_sheet(audit: dict) -> bool`
  - `can_be_key(audit: dict) -> str | None` — lý do không được, hoặc `None`. Được khi: `status == "done"`, không phải tờ kiểm, không có `candidate_version` (frame gộp box của hai bản không làm đáp án).
  - `due(audits: list[dict], email: str) -> bool` — `email` đã lưu `CHECK_EVERY - 1` frame (done, `labeled_by == email`, không phải tờ kiểm) có `labeled_at` sau `sampled_at` của tờ kiểm mới nhất của họ (không có tờ nào thì tính từ đầu), và không có tờ kiểm nào của họ còn `pending`.
  - `eligible_keys(audits: list[dict], email: str) -> list[dict]` — frame có `answer_key is True` mà `email` không chấm (`labeled_by`), không đánh dấu (`answer_key_by`), và chưa có tờ kiểm nào của `email` trỏ tới (`check_of`).
  - `sheet_for(key: dict, email: str, now_iso: str, token: str) -> dict` — dòng tờ kiểm: `audit_id = f"CHK-{token}"`, `check_of = key["audit_id"]`, `assigned_to = email`, `status = "pending"`, `sampled_at = now_iso`, `verdicts_json = "[]"`, `missed_json = "[]"`; chép từ đáp án: `store_id`, `purpose`, `camera_id`, `capture_id`, `capture_timestamp`, `image_key`, `model_version`, `pipeline`, `display_visible`, `ai_boxes_json`.
- Produces (API):
  - `PUT /model/audits/{id}/answer-key`, body `{"on": true | false}`, chỉ `ADMIN_GROUPS`. Bật: ghi `answer_key = True`, `answer_key_by`, `answer_key_at`, `key_verdicts_json`, `key_missed_json` (chép `verdicts_json`, `missed_json` lúc đó). Tắt: gỡ cả năm trường. Frame không hợp lệ: `400 NOT_A_KEY_FRAME` kèm lý do.
  - Dòng audit đã chấm của tờ kiểm giữ câu trả lời của người gán trong `verdicts_json`, `missed_json` như mọi audit. Task 6 đọc cặp (đáp án, tờ kiểm).

- [ ] **Step 1: Viết test thuần trong `tests/test_label_checks.py`:**
  - `test_a_check_is_due_after_nine_frames` (8 frame: chưa; 9 frame: tới lượt)
  - `test_no_second_check_while_one_waits`
  - `test_the_count_starts_again_after_a_sheet` (9 frame trước tờ kiểm, 3 frame sau: chưa)
  - `test_a_key_i_labelled_or_marked_is_not_for_me`
  - `test_a_key_i_was_checked_on_is_not_given_again`
  - `test_a_frame_showing_two_releases_cannot_be_a_key` (`can_be_key` trả chuỗi, không `None`)

- [ ] **Step 2: Viết test moto.** Dùng các hàm phụ đã có để dựng audit done (`_put_scoring_frames` hoặc ghi thẳng vào `test-audits`), hai người gán khác nhau bằng cách cho `_auth_event` một email khác (thêm tham số `email` cho `_call` nếu chưa có).
  - `test_an_admin_marks_a_frame_as_answer_key_and_the_key_keeps_its_answers`: bật đáp án, rồi `PUT` nhãn khác lên chính frame đó; `key_verdicts_json` không đổi.
  - `test_only_an_admin_marks_an_answer_key`: `field_team` nhận 403.
  - `test_a_pending_frame_cannot_be_an_answer_key`: 400 `NOT_A_KEY_FRAME`.
  - `test_the_tenth_frame_is_a_check_only_in_my_queue`: người A lưu 9 frame dạy; `GET /model/audits?status=pending` của A có đúng một dòng `CHK-`, với `purpose` của frame đáp án; của người B không có, và `counts["pending"]` của B không tính nó; B `GET` thẳng id đó nhận 404.
  - `test_a_labeller_with_no_key_left_gets_no_check_and_the_save_still_works`.
  - `test_saving_a_check_leaves_the_key_and_the_model_numbers_alone`: A lưu tờ kiểm với câu trả lời khác đáp án; frame đáp án không đổi; `GET /model/summary` trước và sau bằng nhau.
  - `test_the_browser_never_learns_a_frame_is_a_check`: câu trả lời `GET /model/audits/{CHK id}` cho A không có khoá nào trong `check_of`, `assigned_to`, `answer_key`, `answer_key_by`, `answer_key_at`.

- [ ] **Step 3: Chạy, thấy trượt.**

- [ ] **Step 4: Viết `label_checks.py` và sửa handler.**
  - `_handle_model_audits` nhận thêm `user`; bỏ mọi tờ kiểm không phải của `user["email"]` **trước** khi tính `counts`.
  - `_handle_model_audit_get`, `_put`, `_skip`: tờ kiểm của người khác trả 404 như frame không tồn tại.
  - `_audit_view` bỏ các khoá `check_of`, `assigned_to`, `answer_key`, `answer_key_by`, `answer_key_at` (các khoá `*_json` đã bị bỏ sẵn). Route đáp án trả `{"audit_id", "answer_key"}`.
  - Sau khi `_handle_model_audit_put` lưu xong một frame **không phải** tờ kiểm: nếu `label_checks.due(...)` và có `eligible_keys`, ghi một tờ kiểm (đáp án chọn bằng `random.choice`, `token = uuid.uuid4().hex[:8]`). Bước này bọc trong `try`: lỗi thì in một dòng JSON `{"check_sheet_failed": …}`, lần lưu vẫn trả 200.
  - `team_admin` gửi `on: true` lên một tờ kiểm nhận 400 như mọi frame không hợp lệ.

- [ ] **Step 5: Chạy `python -m pytest -q`,** rồi `ruff check .` và `ruff format --check .`.

- [ ] **Step 6: Commit** `Model page: answer keys a team admin marks, and a check sheet for each labeller after nine frames`.

### Task 6: Độ khớp của từng người gán (backend)

**Files:**
- Create: `backend/label_agreement.py`
- Modify: `backend/api/handler.py` (route `GET /model/labellers`)
- Test: `tests/test_label_agreement.py`, `tests/test_backend_integration_moto.py`

**Interfaces:**
- Consumes: frame đáp án (`key_verdicts_json`, `key_missed_json`) và tờ kiểm done (`check_of`, `labeled_by`, `labeled_at`, `verdicts_json`, `missed_json`) của Task 5.
- Produces:
  - `MATCH_PX = 40`
  - `compare(key_verdicts: list[dict], key_missed: list[dict], verdicts: list[dict], missed: list[dict]) -> dict` với các khoá `units`, `agree`, `boxes`, `boxes_agree`, `marks_key`, `marks_matched`, `marks_extra`; `units = boxes + marks_key + marks_extra`, `agree = boxes_agree + marks_matched`.
  - `week_of(iso: str) -> str` — tuần ISO của ngày theo giờ Việt Nam, dạng `"2026-W48"`.
  - `weekly(pairs: list[tuple[dict, dict]]) -> list[dict]` — mỗi cặp là (frame đáp án, tờ kiểm done), cả hai ở dạng `_whole_audit` cộng `key_verdicts`, `key_missed`; trả các dòng `{"labeller", "week", "frames", "units", "agree", "agreement"}`, tuần mới trước, rồi theo `labeller`. `agreement = agree / units`, `None` khi `units == 0`.
  - `GET /model/labellers` (chỉ `ADMIN_GROUPS`): `{"rows": [...], "keys": [{"audit_id", "capture_timestamp", "answer_key_by", "answer_key_at", "sheets_done", "sheets_pending"}], "check_every": 10}`.

- [ ] **Step 1: Viết test thuần.**

```python
KEY_V = [{"box_id": 1, "verdict": "correct"}, {"box_id": 2, "verdict": "wrong_sku", "true_sku_id": "original145"}]
KEY_M = [{"sku_id": "hot160", "x": 900, "y": 500}]


def test_the_same_answers_agree_on_every_unit():
    assert compare(KEY_V, KEY_M, KEY_V, KEY_M) == {
        "units": 3,
        "agree": 3,
        "boxes": 2,
        "boxes_agree": 2,
        "marks_key": 1,
        "marks_matched": 1,
        "marks_extra": 0,
    }


def test_calling_the_models_wrong_name_right_is_a_disagreement():
    mine = [{"box_id": 1, "verdict": "correct"}, {"box_id": 2, "verdict": "correct"}]
    assert compare(KEY_V, KEY_M, mine, KEY_M)["boxes_agree"] == 1


def test_another_right_name_is_a_disagreement():
    mine = [KEY_V[0], {"box_id": 2, "verdict": "wrong_sku", "true_sku_id": "hot160"}]
    assert compare(KEY_V, KEY_M, mine, KEY_M)["boxes_agree"] == 1


def test_a_mark_within_forty_pixels_and_of_the_same_product_matches():
    assert compare(KEY_V, KEY_M, KEY_V, [{"sku_id": "hot160", "x": 925, "y": 520}])["marks_matched"] == 1


def test_a_mark_of_another_product_at_the_same_place_does_not_match():
    out = compare(KEY_V, KEY_M, KEY_V, [{"sku_id": "original145", "x": 900, "y": 500}])
    assert (out["marks_matched"], out["marks_extra"], out["units"], out["agree"]) == (0, 1, 4, 2)


def test_two_marks_on_one_can_match_once():
    mine = [{"sku_id": "hot160", "x": 900, "y": 500}, {"sku_id": "hot160", "x": 910, "y": 505}]
    out = compare(KEY_V, KEY_M, KEY_V, mine)
    assert (out["marks_matched"], out["marks_extra"]) == (1, 1)


def test_a_box_left_without_a_verdict_is_a_disagreement():
    assert compare(KEY_V, KEY_M, [KEY_V[0]], KEY_M)["boxes_agree"] == 1


def test_the_week_follows_the_store_clock():
    assert week_of("2026-11-29T23:30:00+07:00") == "2026-W48"
    assert week_of("2026-11-29T17:30:00+00:00") == "2026-W49"  # Monday 00:30 in Vietnam
```

Thêm `test_weekly_sums_units_per_labeller_and_week` (hai tờ kiểm của một người trong một tuần: `frames == 2`, `agreement == tổng agree / tổng units`, không phải trung bình của hai tỉ lệ).

- [ ] **Step 2: Viết test moto:** `test_only_an_admin_sees_the_agreement` (`field_team` và `datagent` nhận 403), và `test_agreement_is_measured_against_the_key_as_it_was_marked` (đánh dấu đáp án, A làm tờ kiểm giống hệt, rồi gán lại frame đáp án: dòng của A vẫn `agreement == 1.0`).

- [ ] **Step 3: Chạy, thấy trượt. Step 4: Viết module và route.** Ghép điểm sót: duyệt điểm của người gán theo thứ tự, mỗi điểm lấy điểm đáp án cùng sản phẩm, chưa ghép, gần nhất và trong `MATCH_PX`.

- [ ] **Step 5: `python -m pytest -q`, ruff. Step 6: Commit** `Model page: each labeller's agreement with the answer keys, by week, for team admins`.

### Task 7: "Your labels", khối độ khớp, ô đáp án, dòng nhãn của mỗi bản

**Files:**
- Modify: `backend/api/handler.py` (route `GET /model/my-labels`), `tests/test_backend_integration_moto.py`
- Modify: `frontend/lib/api.ts`, `frontend/lib/model-ui.ts`, `frontend/lib/model-ui.test.ts`, `frontend/lib/model-versions.ts`, `frontend/lib/model-versions.test.ts`
- Create: `frontend/components/model/LabellerAgreement.tsx`
- Modify: `frontend/components/model/ModelQualityView.tsx`, `AuditLabeler.tsx`, `ModelVersions.tsx`

**Interfaces:**
- Produces (API): `GET /model/my-labels` cho `WRITE_CORRECTION_GROUPS`:
  `{"teaching": {"frames", "boxes", "missed"}, "scoring": {"frames", "boxes", "missed"}, "in_live_version": null | {"version_id", "live_since", "label_frames"}}`. Đếm trên audit done có `labeled_by` là người gọi, không tính tờ kiểm. `teaching` là mục đích `training`, `review`, `compare`; `scoring` là `AUD-`. `in_live_version` lấy từ dòng bản live của camera nếu dòng đó có `label_frames` (phần 4 sẽ ghi), không thì `null`.
- Produces (frontend): `myLabelsText(res: ApiMyLabels): string[]` trong `model-ui.ts`; `versionLabelsText(v: { label_frames?: number; labellers?: number }): string` trong `model-versions.ts`; lời gọi `getMyLabels()`, `getLabellers()`, `setAnswerKey(auditId: string, on: boolean)` trong `api.ts`.

- [ ] **Step 1: Test backend** `test_my_labels_counts_only_my_frames_and_never_a_check` (hai người, một tờ kiểm done của người gọi: không được đếm) và `test_a_viewer_has_no_labels_route` (403 cho `datagent`).

- [ ] **Step 2: Test frontend.**

```ts
test("my labels: nothing yet", () => {
  assert.deepEqual(myLabelsText({ teaching: Z, scoring: Z, in_live_version: null }), ["You have not labelled a frame yet."]);
});
test("my labels: waiting, said plainly", () => {
  assert.deepEqual(
    myLabelsText({ teaching: { frames: 43, boxes: 618, missed: 180 }, scoring: { frames: 70, boxes: 774, missed: 47 }, in_live_version: null }),
    [
      "Your labels on training frames: 618 boxes and 180 missed units on 43 frames. No live version has been trained from people's labels yet, so they wait for the first training; no date is set.",
      "Scoring frames you labelled: 70. They measure the model on this page and are never used to train it.",
    ]
  );
});
test("my labels: a live version used labels", () => {
  const lines = myLabelsText({ teaching: { frames: 43, boxes: 618, missed: 180 }, scoring: Z,
    in_live_version: { version_id: "slide-v4", live_since: "2026-12-10T09:00:00+07:00", label_frames: 60 } });
  assert.equal(lines.length, 1);
  assert.match(lines[0], /Version slide-v4, live since 10\/12, was trained with 60 labelled frames\.$/);
});
test("a version says whether people's labels are in it", () => {
  assert.equal(versionLabelsText({}), "No people's labels in this version.");
  assert.equal(versionLabelsText({ label_frames: 60, labellers: 3 }), "Trained with 60 labelled frames from 3 people.");
});
```

(`Z = { frames: 0, boxes: 0, missed: 0 }`.)

- [ ] **Step 3: Chạy, thấy trượt. Step 4: Viết route và các hàm.**

- [ ] **Step 5: Nối vào trang Model.**
  - `ModelQualityView`: dưới nút "Label frames", các dòng của `myLabelsText` trong một khối `data-my-labels`. Với `hasGroup("team_admin")`, khối `<LabellerAgreement />`.
  - `LabellerAgreement.tsx` (`data-labeller-agreement`): bảng người gán × tuần (số tờ kiểm, số đơn vị, độ khớp %), dòng giải thích "Agreement with the answer keys on check frames. Labellers are not told which frames are checks." Danh sách frame đáp án, mỗi dòng có nút "Remove" gọi `setAnswerKey(id, false)`. Chưa có đáp án nào: "No answer keys yet. Label a frame with care, then tick 'Use as answer key'."
  - `AuditLabeler`: với `team_admin`, ô chọn `data-answer-key` "Use as answer key (I checked every unit)". Lưu thành công mà ô được chọn thì gọi `setAnswerKey(detail.audit_id, true)`; câu trả lời 400 được hiện nguyên văn. Ô này không hiện cho người khác.
  - `ModelVersions`: mỗi bản thêm một dòng `versionLabelsText(v)`.

- [ ] **Step 6: `npm test`, `npm run lint`, `npm run build`, `python -m pytest -q`, ruff.**

- [ ] **Step 7: Commit** `Model page: your labels and where they are, labeller agreement for team admins, answer-key tick`.

### Task 8: Kiểm tra cả nhánh, rồi lên live khi hoang duyệt

**Files:** không file mới. Công cụ deploy: `C:\Users\huyho\milk_store_labels\ops_loop_tools_20261127\deploy\` (`backend_changeset.sh`, `package_lambdas.py`).

- [ ] **Step 1: Cả bộ kiểm tra trên nhánh:** `python -m pytest -q`, `ruff check .`, `ruff format --check .`, `cfn-lint infra/backend.yaml`; trong `frontend/`: `npm test`, `npm run lint`, `npm run build`. Ghi số test qua.
- [ ] **Step 2: Thêm `label_signals.py`, `label_checks.py`, `label_agreement.py` vào danh sách file của `package_lambdas.py`** (file nào Lambda nào import thì đi theo Lambda đó), và kiểm bằng cách giải nén gói.
- [ ] **Step 3: Dừng ở đây và hỏi hoang.** Không lên live khi phần 1 chưa đóng (đang có bản thử chạy song song trọn ngày). Nói rõ với hoang: backend đổi code hai Lambda và một dòng biến môi trường; website thêm ba chỗ trên trang Model và đổi nút trên thẻ sản phẩm.
- [ ] **Step 4 (sau khi hoang OK): backend bằng change set** (`create`, đọc danh sách thay đổi, `execute`), rồi website qua Amplify. Giữ bản rollback như các lần trước.
- [ ] **Step 5: Kiểm tra trên live, không dựng dữ liệu giả:**
  - tài khoản viewer gọi `/model/labellers` và `/model/my-labels` nhận 403;
  - tài khoản nhóm thấy dòng "Your labels" khớp với số đếm trực tiếp trong bảng audits;
  - khi một người trong nhóm sửa một reading sai thật trên trang Category: toast có câu về hàng chờ; sau lần chạy mỗi giờ kế tiếp, frame dạy của giờ đó là capture ấy, `picked_by = "correction"`;
  - một `team_admin` (người, không phải Claude) gán cẩn thận một frame và đánh dấu đáp án; khối độ khớp hiện frame đó.
- [ ] **Step 6: Ghi sổ, cập nhật memory, báo hoang** mọi dòng `Ruling:` và `minor (deferred)`.
