# Vòng vận hành, phần 1: xương sống (phiên bản, chạy song song, duyệt) — kế hoạch làm

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mọi thay đổi của model lên chạy thật qua một cửa: bản ứng viên chạy song song với bản live mà người xem không thấy, người chấm phân xử trên frame gộp, `team_admin` bấm đưa lên hoặc quay lui trên trang Model, không ai sửa `worker.env`.

**Architecture:** Một *bản chạy* là một thư mục trên HUYHOANG chứa `release.json` (các biến model); file `live.json` trỏ tới bản live, bản trước và bản ứng viên. Worker đọc con trỏ lúc khởi động, cho bản ứng viên đọc lại các frame đã lưu của mỗi cửa sổ sau khi phần live gửi xong, rồi gửi kết quả ứng viên qua hub vào S3, SQS và bảng captures của backend. Backend gộp box của hai bản khi tạo frame để chấm, tính kết luận từ câu trả lời của người, và ghi yêu cầu của `team_admin` vào một bảng mới; một tiến trình trên HUYHOANG (`ops.runner`) đọc bảng đó, đổi con trỏ và khởi động lại worker.

**Tech Stack:** Python 3.12 (worker, hub FastAPI, Lambda, runner với boto3), DynamoDB, S3, SQS, CloudFormation, Next.js 16 (frontend), pytest, moto, node:test.

**Spec:** `docs/superpowers/specs/2026-11-27-operations-loop-design.md`, mục 5.2 (và 5.7 dòng "Xương sống"). hoang duyệt ngày 27/11.

## Những điều Claude tự quyết trong kế hoạch này

Spec để người làm tự quyết các điểm sau; đây là lựa chọn của kế hoạch:
- **Ứng viên chạy cùng tiến trình với worker**, đọc lại ảnh gốc còn trong bộ nhớ của các frame vừa lưu, sau khi cửa sổ lấy mẫu đóng. Lý do: ứng viên phải thấy đúng điểm ảnh mà bản live thấy; ảnh trên đĩa đã làm mờ mặt và nén JPEG.
- **Kết quả ứng viên là một thông điệp riêng**, gửi sau thông điệp của capture, vào khoá S3 `results/<camera>/<ngày>/<capture_id>.candidate.json`. Lý do: tiền tố `results/` và hậu tố `.json` đã được báo sang SQS, nên không phải sửa stack của hub bucket.
- **Trạng thái của ứng viên trong worker** được ghi ra file `candidate-status.json` cạnh `live.json`; `ops.runner` chép nó lên bảng. Lý do: worker không cần quyền AWS.
- **Hai box là "cùng một chỗ"** khi phần chung chiếm từ 0,5 diện tích của box nhỏ hơn, giống luật bỏ box trùng đang dùng (`MILK_LONG_TH_OVERLAP=0.5`).
- **Id của bản chạy đầu tiên** là `long-store-v1-det+slide-v3`, đúng `model_version` đang chạy, để lịch sử KPI trên trang Model không bị tách đôi.
- **`live.json` hoặc `release.json` của bản live đọc không được thì worker dừng**, không lặng lẽ chạy bằng biến cũ. Hỏng ở bản ứng viên thì bản live vẫn chạy, không có ứng viên.
- **Kết quả ứng viên tới khi chưa có dòng capture thì bỏ qua**, có ghi log; không thử lại, để hàng chờ lỗi của ingest không báo động vì một thứ không ai nhìn thấy.
- **Bản ứng viên giả của lần kiểm cuối** dùng tiêu chí rút gọn (1 ngày, 5 frame) ghi trong bản ghi của chính nó.
- **Tiêu chí thắng được ghi vào `release.json` lúc tạo bản chạy** (mặc định theo `kind`), rồi chép vào dòng của bảng khi bản được đăng ký. Backend chỉ đọc tiêu chí từ dòng đó, nên tiêu chí luôn có trước khi chạy song song.

Ba điều trong mục 5.2 của spec **không nằm trong kế hoạch này**, vì chưa có gì để chúng chạy trên đó:
- ứng viên chỉ khác kho ảnh dùng lại box của detector live: thuộc phần 2, khi có kho ảnh;
- worker giữ lại trên đĩa bản frame nó đã gửi: thuộc phần 4, khi có việc gom frame để train;
- tiêu chí riêng cho sản phẩm mà bản live chưa biết: thuộc phần 5.

## Global Constraints

- Kết quả của ứng viên không bao giờ vào `latest_stock`, `cv_output`, review queue, bảng shelf, `model_health`, Dashboard hay Category.
- Trình duyệt không bao giờ nhận được box nào của bản nào: các trường `src`, `live_sku`, `cand_sku` không rời backend.
- Box mà hai bản nói khác nhau, hoặc chỉ một bản có, không hiện gợi ý (`needs_flavour: true`, `sku_id: null`).
- Bản live luôn được ưu tiên: ứng viên không được làm chậm hay làm mất một frame nào của live.
- Mỗi camera mỗi lúc chỉ một ứng viên.
- Chỉ `team_admin` gửi được yêu cầu đưa lên, bỏ, quay lui.
- Chữ trên website bằng tiếng Anh.
- Không cài gì vào `.venv` của worker trên HUYHOANG. `ops.runner` chạy trong `.venv-ops` riêng, chỉ có `boto3`.
- Các con số của spec: 3 ngày và 30 frame đã chấm (thay detector hoặc luật đọc); 1 ngày và 30 box khác nhau đã chấm (chỉ thay kho ảnh); p < 0,05; không sản phẩm nào kém quá 5 điểm; tối đa 8 frame so sánh mỗi camera mỗi ngày; dừng khi trễ 3 cửa sổ liên tiếp; dừng khi quá 1 box trên 100 frame lúc tủ đã cất.
- Python 3.12; `python -m pytest -q`; `ruff check . && ruff format --check .` (ruff cũng định dạng các khối Python trong file kế hoạch này). Frontend: `cd frontend && npm test && npm run build`.
- Commit bằng danh tính noreply: `git -c user.name="Nguyen Huy Hoang" -c user.email=193206418+Protein-17012006@users.noreply.github.com commit …`. Không push khi hoang chưa bảo.
- Backend lên live bằng change set, không bao giờ `--tags`. Stack `milk-demo-server` không bao giờ được cập nhật ngoài change set. Mỗi lần lên live chờ hoang OK.

## Review Focus

1. **Capture không bao giờ có kết quả ứng viên** (ứng viên bị trễ, bị dừng): frame để chấm phải hiện box của live như hiện nay, và phép so bỏ qua frame đó. Test ở Task 6 và Task 7.
2. **Kết quả ứng viên tới trước hoặc không có dòng capture:** bỏ qua, không tạo dòng mới, không lỗi. Test ở Task 5.
3. **`live.json` hỏng hoặc trỏ tới bản không tồn tại:** worker dừng với thông báo nêu tên file; con trỏ được ghi theo kiểu thay file nguyên khối nên không bao giờ dở dang. Test ở Task 1.
4. **Hai bản cùng vẽ hai box trên một lon, hoặc một box chồng lên hai box:** phép gộp phải một đối một và cho cùng kết quả mỗi lần chạy; box thừa thành box một phía. Test ở Task 6.
5. **`ops.runner` chết giữa lúc đổi con trỏ và khởi động lại worker:** lần chạy sau phải nhận ra yêu cầu còn dở và làm tiếp, không làm lại từ đầu, không bỏ. Test ở Task 8.

## File Structure

| File | Việc |
|---|---|
| `server/milk/release.py` (mới) | Đọc `release.json`, đọc và ghi `live.json`, dựng bộ biến model của một bản chạy |
| `server/milk/candidate.py` (mới) | Giữ frame của cửa sổ, chạy bản ứng viên, đếm trễ và lỗi, ghi `candidate-status.json` |
| `server/milk/config.py`, `counter.py`, `pipeline.py`, `long_adapter.py`, `slide_adapter.py` | Worker đọc bản live; adapter nhận bộ biến thay vì chỉ `os.environ`; vòng lặp gọi ứng viên lúc rảnh |
| `server/milk/store.py`, `web/app.py`, `reindex.py` | Hub nhận và lưu kết quả ứng viên |
| `backend/compare.py` (mới) | Gộp box, tách frame gộp thành hai frame kiểu cũ, đếm và kết luận |
| `backend/model_versions.py` (mới) | Dạng dòng của bảng phiên bản, tiêu chí mặc định, hành động nào được phép |
| `backend/model_health.py`, `backend/ingest/handler.py`, `backend/api/handler.py`, `infra/backend.yaml` | Nhận kết quả ứng viên, tạo frame gộp và frame so sánh, route `/model/versions`, bảng mới |
| `ops/decide.py`, `ops/runner.py`, `ops/make_release.py` (mới) | Việc cần làm kế tiếp (thuần logic); vòng lặp đọc bảng, đổi con trỏ, khởi động lại worker; tạo bản chạy từ `worker.env` hoặc từ bản khác |
| `worker/windows/run-ops.ps1`, `register-ops-task.ps1` (mới) | Task `milk-ops` trên HUYHOANG |
| `frontend/lib/model-versions.ts` (+ test), `components/model/ModelVersions.tsx`, `lib/api.ts`, `lib/audit-labeling.ts`, `ModelQualityView.tsx`, `AuditLabeler.tsx` | Khối "Model versions" và frame so sánh |
| `tests/test_release.py`, `test_candidate.py`, `test_compare.py`, `test_model_versions.py`, `test_ops_decide.py` (mới) | Test của các file mới; test của file sửa nằm trong file test sẵn có |

**Dạng dữ liệu dùng chung** (mọi task đều theo):

```text
<MILK_RELEASES_DIR>\<id>\release.json
  {"id": "...", "parent": "..."|null, "kind": "baseline"|"detector"|"gallery"|"rules",
   "env": {"MILK_PIPELINE": "long+slide", "MILK_LONG_...": "...", "MILK_SLIDE_...": "..."},
   "criteria": {...}|null, "created_at": "2026-11-27T15:00:00+07:00"}
<MILK_RELEASES_DIR>\live.json
  {"live": "<id>", "previous": "<id>"|null, "candidate": "<id>"|null}
<MILK_RELEASES_DIR>\candidate-status.json
  {"candidate": "<id>", "windows": 0, "late": 0, "errors": 0, "load_times": ["..."],
   "stopped": null|"too_slow"|"error: ...", "updated_at": "..."}

worker -> hub  POST /internal/candidate
  {"camera_id", "capture_id", "capture_timestamp", "candidate_version", "processing_time_ms",
   "detections": [{"sku_id", "conf", "box": [x, y, w, h]}]}
hub -> S3      results/<camera_id>/<YYYY-MM-DD>/<capture_id>.candidate.json   (cùng nội dung)
bảng captures  thêm candidate_version, candidate_detections_json

bảng milk-backend-<env>-model-versions   (HASH camera_id, RANGE version_id)
  dòng "#state":  live, previous, candidate, request {id, action, version_id, by, at}|null,
                  last_result {request_id, ok, message, at}|null, runner_seen_at
  dòng phiên bản: kind, parent, status, created_at, criteria, parallel_started_at, stopped_reason,
                  decided_by, decided_at, worker {windows, late, errors},
                  inputs, quick_check (để trống ở phần 1; phần 2 và phần 4 điền)
  status: candidate | parallel | live | replaced | discarded | stopped

box gộp trong ai_boxes_json của audit
  {"box_id", "sku_id", "conf", "box", "needs_flavour", "src": "both"|"live"|"cand", "live_sku", "cand_sku"}
audit có thêm candidate_version; frame so sánh có id CMP-<camera>-<YYYYMMDD>-<n> và purpose "compare"
```

Hàm phụ xuất hiện trong các khối test bên dưới (`box(...)`, `tables`, `api`, `P(...)`, `state(...)`, `rows(...)`, `write_release(...)`, `FakePipeline`, `FakeClock`…) là hàm của file test. Người làm viết chúng theo fixture sẵn có của file test đó; tên và đối số như trong khối test.

---

### Task 0: HUYHOANG có quyền AWS dùng được, và có môi trường cho runner

**Files:** không có file trong repo. Kết quả ghi vào ledger của lần thực thi.

- [ ] **Step 1:** Trên HUYHOANG tạo `C:\Users\huyho\Datagent\.venv-ops` bằng Python 3.12 của hệ thống và `pip install boto3`. Không đụng `.venv`.
- [ ] **Step 2:** Bằng `.venv-ops` và `boto3.Session(profile_name="milk", region_name="ap-southeast-1")`: in tài khoản của `sts.get_caller_identity()` (phải là `754361433393`); đọc một dòng của bảng `milk-backend-development-audits`; ghi rồi xoá object `ops/selfcheck/<giờ>.txt` trong bucket analytics (tên bucket lấy từ output của stack `milk-backend-development`). Không in khoá.
- [ ] **Step 3:** Chạy lại Step 2 dưới tài khoản SYSTEM với `AWS_SHARED_CREDENTIALS_FILE=C:\Users\huyho\.aws\credentials` và `AWS_CONFIG_FILE=C:\Users\huyho\.aws\config` (task `milk-ops` sẽ chạy như vậy). Cách chạy: một scheduled task tạm, chạy một lần, ghi kết quả ra file.
- [ ] **Step 4:** Một trong ba phép thử thất bại thì DỪNG và báo hoang; các task sau vẫn viết và test được trên laptop, nhưng Task 11 không làm được.

### Task 1: Bản chạy trên đĩa, và worker đọc bản live

**Files:**
- Create: `server/milk/release.py`, `tests/test_release.py`
- Modify: `server/milk/config.py` (hàm `load`), `tests/test_config.py`

**Interfaces:**
- Produces:
  - `MODEL_KEYS = {"MILK_PIPELINE", "MILK_MODEL_VERSION"}`, `MODEL_PREFIXES = ("MILK_LONG_", "MILK_SLIDE_")`
  - `DEFAULT_CRITERIA: dict[str, dict]`:
    - `baseline`, `detector`, `rules`: `{"min_days": 3, "min_frames": 30, "min_diff_boxes": 0, "alpha": 0.05, "max_sku_drop": 0.05}`
    - `gallery`: `{"min_days": 1, "min_frames": 0, "min_diff_boxes": 30, "alpha": 0.05, "max_sku_drop": 0.05}`
  - `@dataclass(frozen=True) class Release: id: str; parent: str | None; kind: str; env: dict[str, str]; criteria: dict` — `release.json` không có `criteria` thì lấy mặc định theo `kind`; có thì các khoá của nó đè lên mặc định.
  - `@dataclass(frozen=True) class Pointer: live: str; previous: str | None; candidate: str | None`
  - `load_release(root: Path, release_id: str) -> Release` — `ValueError` nêu đường dẫn khi thiếu file, JSON hỏng, `id` trong file khác tên thư mục, hoặc `env` có khoá ngoài `MILK_PIPELINE` và hai tiền tố.
  - `read_pointer(root: Path) -> Pointer`, `write_pointer(root: Path, pointer: Pointer) -> None` (ghi file tạm rồi `os.replace`)
  - `model_env(base: Mapping[str, str], release: Release) -> dict[str, str]` — `base` bỏ mọi khoá model, cộng `release.env`, cộng `MILK_MODEL_VERSION = release.id`.
  - `config.load`: khi có `MILK_RELEASES_DIR`, áp `model_env` của bản live vào `os.environ` trước khi dựng `Settings`. Không có biến đó thì y hệt hiện nay.

- [ ] **Step 1: Viết test (chưa có code nên phải trượt)**

```python
def test_model_env_replaces_every_model_key(tmp_path):
    write_release(tmp_path, "v2", env={"MILK_PIPELINE": "long", "MILK_LONG_TILE": "1280"})
    base = {"MILK_HUB_URL": "https://hub", "MILK_PIPELINE": "long+slide", "MILK_SLIDE_WEIGHTS": "old.pt"}
    env = release.model_env(base, release.load_release(tmp_path, "v2"))
    assert env == {
        "MILK_HUB_URL": "https://hub",
        "MILK_PIPELINE": "long",
        "MILK_LONG_TILE": "1280",
        "MILK_MODEL_VERSION": "v2",
    }


def test_release_with_a_foreign_key_is_refused(tmp_path):
    write_release(tmp_path, "v2", env={"MILK_HUB_URL": "https://elsewhere"})
    with pytest.raises(ValueError, match="MILK_HUB_URL"):
        release.load_release(tmp_path, "v2")


def test_pointer_round_trip_leaves_no_partial_file(tmp_path):
    release.write_pointer(tmp_path, release.Pointer(live="v1", previous=None, candidate="v2"))
    assert release.read_pointer(tmp_path) == release.Pointer(live="v1", previous=None, candidate="v2")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["live.json"]


def test_broken_pointer_names_the_file(tmp_path):
    (tmp_path / "live.json").write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="live.json"):
        release.read_pointer(tmp_path)


def test_criteria_default_by_kind_and_partial_override(tmp_path):
    write_release(tmp_path, "g1", kind="gallery", env={})
    write_release(tmp_path, "d1", kind="rules", env={}, criteria={"min_days": 1, "min_frames": 5})
    assert release.load_release(tmp_path, "g1").criteria["min_diff_boxes"] == 30
    assert release.load_release(tmp_path, "d1").criteria == {
        "min_days": 1,
        "min_frames": 5,
        "min_diff_boxes": 0,
        "alpha": 0.05,
        "max_sku_drop": 0.05,
    }
```

Trong `tests/test_config.py`:

```python
def test_load_takes_the_live_release(tmp_path, monkeypatch):
    write_release(tmp_path, "v1", env={"MILK_PIPELINE": "null"})
    release.write_pointer(tmp_path, release.Pointer(live="v1", previous=None, candidate=None))
    monkeypatch.setenv("MILK_RELEASES_DIR", str(tmp_path))
    monkeypatch.setenv("MILK_PIPELINE", "long+slide")
    monkeypatch.setenv("MILK_SLIDE_WEIGHTS", "stale.pt")
    settings = config.load()
    assert (settings.pipeline, settings.model_version) == ("null", "v1")
    assert "MILK_SLIDE_WEIGHTS" not in os.environ


def test_load_stops_when_the_live_release_is_missing(tmp_path, monkeypatch):
    release.write_pointer(tmp_path, release.Pointer(live="gone", previous=None, candidate=None))
    monkeypatch.setenv("MILK_RELEASES_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="gone"):
        config.load()


def test_load_without_releases_dir_is_unchanged(monkeypatch):
    monkeypatch.delenv("MILK_RELEASES_DIR", raising=False)
    monkeypatch.setenv("MILK_PIPELINE", "null")
    monkeypatch.setenv("MILK_MODEL_VERSION", "by-hand")
    assert config.load().model_version == "by-hand"
```

- [ ] **Step 2:** `python -m pytest tests/test_release.py tests/test_config.py -q` — phải trượt vì chưa có `milk.release`.
- [ ] **Step 3:** Viết `server/milk/release.py` và sửa `config.load` theo Interfaces. `write_release` là hàm phụ trong test.
- [ ] **Step 4:** Chạy lại lệnh Step 2 — phải qua. Chạy cả `python -m pytest -q`.
- [ ] **Step 5:** Commit: `Worker: the model settings come from the live release when MILK_RELEASES_DIR is set`.

### Task 2: Adapter nhận bộ biến của một bản chạy

**Files:**
- Modify: `server/milk/long_adapter.py` (`_settings`, `_th_confirm`, `_th_overlap`, `LongPipeline.__init__`), `server/milk/slide_adapter.py` (`SlidePipeline.__init__`), `server/milk/pipeline.py` (`_one`, `load_pipeline`)
- Test: `tests/test_long_adapter.py`, `tests/test_pipeline.py`

**Interfaces:**
- Produces: `load_pipeline(kind: str, models_dir: str, env: Mapping[str, str] | None = None) -> Pipeline`; `LongPipeline(models_dir="", env=None)`; `SlidePipeline(models_dir="", env=None)`; `_settings(env)`, `_th_confirm(env)`, `_th_overlap(env)`. `env=None` nghĩa là `os.environ`. Không hàm nào trong hai adapter còn đọc `os.environ` trực tiếp.

- [ ] **Step 1: Test**

```python
def test_th_settings_read_the_mapping_not_the_process(monkeypatch):
    monkeypatch.setenv("MILK_LONG_TH_CONFIRM", "database")
    monkeypatch.setenv("MILK_LONG_TH_OVERLAP", "0")
    env = {"MILK_LONG_TH_CONFIRM": "detector", "MILK_LONG_TH_OVERLAP": "0.5", "MILK_LONG_TILE": "1280"}
    assert long_adapter._th_confirm(env) == "detector"
    assert long_adapter._th_overlap(env) == 0.5
    assert long_adapter._settings(env) == (1280, False)


def test_load_pipeline_passes_the_mapping(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        pipeline, "_one", lambda kind, models_dir, env=None: seen.setdefault(kind, env) or pipeline.NullPipeline()
    )
    pipeline.load_pipeline("long+slide", "", env={"MILK_LONG_TILE": "1280"})
    assert seen == {"long": {"MILK_LONG_TILE": "1280"}, "slide": {"MILK_LONG_TILE": "1280"}}
```

- [ ] **Step 2:** Chạy hai file test — phải trượt.
- [ ] **Step 3:** Sửa theo Interfaces. Thêm một test trong `tests/test_long_adapter.py`: đọc mã nguồn hai file adapter và khẳng định chuỗi `os.environ` chỉ còn xuất hiện ở chỗ gán mặc định `env = os.environ if env is None else env`.
- [ ] **Step 4:** `python -m pytest -q` — phải qua, các test adapter cũ không đổi.
- [ ] **Step 5:** Commit: `Worker: the model adapters take their settings as a mapping`.

### Task 3: Ứng viên chạy trong worker lúc rảnh

**Files:**
- Create: `server/milk/candidate.py`, `tests/test_candidate.py`
- Modify: `server/milk/counter.py` (hàm `main`), `tests/test_counter_helpers.py`

**Interfaces:**
- Consumes: `release.load_release`, `release.read_pointer`, `release.model_env` (Task 1); `load_pipeline(..., env=)` (Task 2).
- Produces:
  - `MAX_HELD = 12`, `LATE_LIMIT = 3`
  - `class CandidateRunner(pipeline, version: str, status_path: Path, clock=time.monotonic)`
    - `hold(capture_id: str, capture_timestamp: str, camera_id: str, crop: np.ndarray, offset: tuple[int, int]) -> None` — giữ bản sao; khi đã có `MAX_HELD` frame thì bỏ frame mới.
    - `flush(deadline: float) -> list[dict]` — chạy ứng viên trên các frame đang giữ theo thứ tự, dừng khi `clock() >= deadline`; trả các payload đúng dạng `POST /internal/candidate`; luôn xoá hết frame đang giữ. Còn frame chưa chạy thì tính một lần trễ; không còn thì số trễ liên tiếp về 0. Trễ `LATE_LIMIT` lần liên tiếp thì `stopped = "too_slow"`. `detect` ném lỗi thì `stopped = "error: <tên lỗi>"`. Đã dừng thì `hold` và `flush` không làm gì nữa. Mỗi lần gọi ghi `candidate-status.json`. `windows` tăng một sau mỗi lần `flush` có frame.
    - thuộc tính `stopped: str | None`
  - `load_candidate(root: Path, base_env: Mapping[str, str], models_dir: str, sampled: bool) -> CandidateRunner | None` — `None` khi con trỏ không có ứng viên hoặc worker đọc liên tục (`sampled` sai, có ghi log). Nạp hỏng thì ghi `candidate-status.json` với `stopped = "error: …"` và trả `None`; không bao giờ ném lỗi ra ngoài. Mỗi lần nạp được thì thêm giờ hiện tại vào `load_times` (giữ 5 giờ gần nhất, đọc từ file trạng thái cũ của cùng ứng viên), để runner nhận ra worker bị khởi động lại liên tục.
- `counter.main`: sau khi nạp pipeline live, gọi `load_candidate` nếu có `MILK_RELEASES_DIR`. Sau mỗi `hub.post("/internal/persist", …)` thành công, gọi `hold(...)` với `crop` và `(x0, y0)`. Ở nhánh đang chờ cửa sổ kế, gọi `flush(deadline = lúc cửa sổ kế bắt đầu trừ 5 giây)` một lần cho mỗi cửa sổ và `hub.post("/internal/candidate", payload)` cho từng payload.

- [ ] **Step 1: Test** (pipeline giả trả một `Detection` cố định; đồng hồ giả)

```python
def test_flush_returns_one_payload_per_held_frame():
    runner = CandidateRunner(FakePipeline(), "v2", status_path, clock=FakeClock(step=1.0))
    runner.hold("CAP-1", "2026-11-27T10:00:05+07:00", "CAM-S01-A", crop, (10, 20))
    runner.hold("CAP-2", "2026-11-27T10:00:15+07:00", "CAM-S01-A", crop, (10, 20))
    payloads = runner.flush(deadline=100.0)
    assert [p["capture_id"] for p in payloads] == ["CAP-1", "CAP-2"]
    assert payloads[0]["candidate_version"] == "v2"
    assert payloads[0]["detections"] == [{"sku_id": "original145", "conf": 0.9, "box": [15, 25, 30, 40]}]


def test_three_late_windows_in_a_row_stop_the_candidate():
    clock = FakeClock(step=10.0)  # every reading of the clock is 10 s later
    runner = CandidateRunner(FakePipeline(), "v2", status_path, clock=clock)
    for n in range(3):
        runner.hold(f"CAP-{n}a", TS, "CAM-S01-A", crop, (0, 0))
        runner.hold(f"CAP-{n}b", TS, "CAM-S01-A", crop, (0, 0))
        runner.flush(deadline=clock.now + 5.0)
    assert runner.stopped == "too_slow"
    assert json.loads(status_path.read_text())["late"] == 3
    runner.hold("CAP-x", TS, "CAM-S01-A", crop, (0, 0))
    assert runner.flush(deadline=1e9) == []


def test_an_error_stops_the_candidate_and_never_escapes():
    runner = CandidateRunner(RaisingPipeline(RuntimeError("boom")), "v2", status_path)
    runner.hold("CAP-1", TS, "CAM-S01-A", crop, (0, 0))
    assert runner.flush(deadline=1e9) == []
    assert runner.stopped == "error: RuntimeError"


def test_a_thirteenth_frame_is_not_held():
    runner = CandidateRunner(FakePipeline(), "v2", status_path)
    for n in range(13):
        runner.hold(f"CAP-{n}", TS, "CAM-S01-A", crop, (0, 0))
    assert len(runner.flush(deadline=1e9)) == 12


def test_load_candidate_is_none_when_reading_continuously(tmp_path):
    write_pointer_with_candidate(tmp_path, live="v1", candidate="v2")
    assert load_candidate(tmp_path, {}, "", sampled=False) is None
```

- [ ] **Step 2:** `python -m pytest tests/test_candidate.py -q` — phải trượt.
- [ ] **Step 3:** Viết `candidate.py`; nối vào `counter.main`. Box của ứng viên được dời về toạ độ frame bằng `normalise` như box live.
- [ ] **Step 4:** Thêm vào `tests/test_counter_helpers.py` một test cho hàm phụ mới `candidate_deadline(next_start: float) -> float` (trả `next_start - 5.0`). `python -m pytest -q` — phải qua.
- [ ] **Step 5:** Commit: `Worker: a candidate release reads each window's saved frames once the live part has been sent`.

### Task 4: Hub nhận và lưu kết quả ứng viên

**Files:**
- Modify: `server/milk/store.py` (`Persistence`), `server/milk/web/app.py`, `server/milk/reindex.py`
- Test: `tests/test_store.py`, `tests/test_web.py`

**Interfaces:**
- Produces:
  - `candidate_key(payload: dict) -> str` → `results/<camera_id>/<capture_timestamp[:10]>/<capture_id>.candidate.json`
  - `Persistence.submit_candidate(payload: dict) -> None` — cùng hàng chờ và cùng luật "đầy thì bỏ"; chỉ ghi một object S3, không ghi bảng của hub.
  - `POST /internal/candidate` — cùng kiểm `X-Internal-Token` như `/internal/persist`; thiếu một trong `camera_id`, `capture_id`, `capture_timestamp`, `candidate_version`, `detections` thì 422; trả 202.
  - `reindex` bỏ qua khoá kết thúc bằng `.candidate.json`.

- [ ] **Step 1: Test**

```python
def test_candidate_key_sits_beside_the_capture_result():
    payload = {
        "camera_id": "CAM-S01-A",
        "capture_id": "CAP-S01-20261127-100005",
        "capture_timestamp": "2026-11-27T10:00:05+07:00",
    }
    assert store.candidate_key(payload) == "results/CAM-S01-A/2026-11-27/CAP-S01-20261127-100005.candidate.json"


def test_internal_candidate_needs_the_token_and_the_fields(client, persisted):
    assert client.post("/internal/candidate", json=PAYLOAD).status_code in (401, 403)
    assert client.post("/internal/candidate", json={"capture_id": "x"}, headers=TOKEN).status_code == 422
    assert client.post("/internal/candidate", json=PAYLOAD, headers=TOKEN).status_code == 202
    assert persisted.candidates == [PAYLOAD]


def test_reindex_skips_candidate_files(s3_with_keys):
    keys = ["results/CAM-S01-A/2026-11-27/CAP-1.json", "results/CAM-S01-A/2026-11-27/CAP-1.candidate.json"]
    report = reindex.reindex(s3_with_keys(keys), FakeTable(), "bucket", dry_run=True)
    assert report["found"] == 1
```

- [ ] **Step 2:** Chạy hai file test — phải trượt. (Tên khoá đếm trong báo cáo của `reindex` lấy theo code đang có; sửa test cho khớp tên thật nếu khác `found`.)
- [ ] **Step 3:** Viết code theo Interfaces.
- [ ] **Step 4:** `python -m pytest -q` — phải qua.
- [ ] **Step 5:** Commit: `Hub: stores a candidate's result beside the capture's result file`.

### Task 5: Backend nhận kết quả ứng viên, và bảng phiên bản

**Files:**
- Create: `backend/model_versions.py`, `tests/test_model_versions.py`
- Modify: `backend/ingest/handler.py` (`lambda_handler`, hàm mới `ingest_candidate`), `infra/backend.yaml`, `tests/test_backend_integration_moto.py`

**Interfaces:**
- Produces:
  - `ingest_candidate(raw: dict, ddb_resource) -> dict` — cập nhật dòng `(camera_id, capture_id)` của bảng captures: `SET candidate_version, candidate_detections_json`, điều kiện `attribute_exists(capture_id)`. Không có dòng thì trả `{"status": "skipped", "reason": "no capture"}` và ghi log. Không đụng bảng nào khác.
  - `lambda_handler`: trong vòng SQS, khoá kết thúc bằng `.candidate.json` đi vào `ingest_candidate`; các khoá khác như hiện nay.
  - `model_versions.STATE_ID = "#state"`, `STATUSES = ("candidate", "parallel", "live", "replaced", "discarded", "stopped")`
  - `can(action: str, state: dict, version: dict | None, verdict_state: str | None) -> str | None` — trả câu báo lỗi tiếng Anh hoặc `None`:
    - còn `state["request"]` chưa có `last_result` cùng id → `"Another request is still running."`
    - `put_live`: `version["status"] == "parallel"` và `verdict_state in ("better", "no_difference")`
    - `discard`: `version["status"] in ("candidate", "parallel")`
    - `rollback`: `state.get("previous")` khác rỗng
  - `infra/backend.yaml`: bảng `ModelVersionsTable` (`milk-backend-${Env}-model-versions`, HASH `camera_id`, RANGE `version_id`, cùng các thuộc tính với `AuditsTable` kể cả `DeletionPolicy: Retain`); biến `MODEL_VERSIONS_TABLE` cho `ApiLambda` và `IngestLambda`; ARN của bảng trong câu lệnh IAM thứ nhất của `MilkBackendLeastPrivilege`.

- [ ] **Step 1: Test**

```python
def test_candidate_result_updates_only_its_capture(tables):
    ingest_capture(capture("CAP-1", units=5), ddb_resource=tables.ddb, s3_client=tables.s3)
    before = tables.snapshot(except_table="captures")
    out = ingest_candidate(candidate("CAP-1", version="v2", boxes=3), tables.ddb)
    row = tables.capture("CAM-S01-A", "CAP-1")
    assert out["status"] == "stored"
    assert row["candidate_version"] == "v2" and len(json.loads(row["candidate_detections_json"])) == 3
    assert tables.snapshot(except_table="captures") == before


def test_candidate_result_without_its_capture_is_skipped(tables):
    assert ingest_candidate(candidate("CAP-9", version="v2", boxes=1), tables.ddb)["status"] == "skipped"
    assert tables.capture("CAM-S01-A", "CAP-9") is None


def test_put_live_needs_a_parallel_run_and_a_verdict():
    state = {"live": "v1", "previous": None, "candidate": "v2", "request": None}
    assert can("put_live", state, {"status": "parallel"}, "better") is None
    assert can("put_live", state, {"status": "parallel"}, "no_difference") is None
    assert can("put_live", state, {"status": "parallel"}, "waiting") is not None
    assert can("put_live", state, {"status": "parallel"}, "worse") is not None
    assert can("put_live", state, {"status": "candidate"}, "better") is not None
    assert can("rollback", state, None, None) is not None
    assert can("rollback", {**state, "previous": "v0"}, None, None) is None


def test_one_request_at_a_time():
    state = {"live": "v1", "previous": "v0", "candidate": None, "request": {"id": "r1"}, "last_result": None}
    assert can("rollback", state, None, None) == "Another request is still running."
```

- [ ] **Step 2:** Chạy `tests/test_model_versions.py` và `tests/test_backend_integration_moto.py` — phải trượt.
- [ ] **Step 3:** Viết code; thêm bảng mới vào fixture moto. `cfn-lint infra/backend.yaml` phải sạch.
- [ ] **Step 4:** `python -m pytest -q` — phải qua.
- [ ] **Step 5:** Commit: `Backend: a candidate's result lands on its capture row; a table for model versions`.

### Task 6: Frame gộp để người chấm, và frame so sánh

**Files:**
- Create: `backend/compare.py`, `tests/test_compare.py`
- Modify: `backend/model_health.py` (`capture_boxes`), `backend/ingest/handler.py` (`_write_frame_audit`, `_run_hour`, hàm mới `sample_compare`), `backend/api/handler.py` (`_audit_view`, `_purpose`, chỗ tính số của trang Model), `tests/test_audit_scoring.py`, `tests/test_backend_api.py`

**Interfaces:**
- Produces trong `backend/compare.py`:
  - `SAME_PLACE = 0.5`, `PRIVATE_KEYS = ("src", "live_sku", "cand_sku")`, `CMP_PER_DAY = 8`
  - `merge_boxes(live: list[dict], cand: list[dict]) -> list[dict]` — ghép một đối một: duyệt box live theo `conf` giảm dần (hoà thì theo `box`), mỗi box nhận box ứng viên chưa ghép có phần chung lớn nhất và từ `SAME_PLACE` diện tích box nhỏ hơn. Ghép được và cùng `sku_id` → `src "both"`, giữ `sku_id`, `needs_flavour False`, hình của box live. Ghép được mà khác tên → `src "both"`, `sku_id None`, `needs_flavour True`. Không ghép được → `src "live"` hoặc `"cand"`, `sku_id None`, `needs_flavour True`. `box_id` đánh lại từ 1 theo thứ tự trên xuống, trái sang.
  - `differs(boxes: list[dict]) -> bool` — có box `needs_flavour` nào không.
  - `split_audit(audit: dict) -> tuple[dict, dict]` — frame gộp thành hai frame kiểu cũ (live, ứng viên), mỗi frame có `ai_boxes`, `verdicts`, `missed` mà `audit_scoring` đọc được. Với mỗi box gộp và câu trả lời của người:
    - box có gợi ý: cả hai phía nhận nguyên câu trả lời;
    - box không gợi ý, phía có box tên `N`: `wrong_sku` với `true_sku_id == N` → `correct`; `wrong_sku` khác → `wrong_sku`; `not_product` và `out_of_scope` giữ nguyên;
    - box không gợi ý, phía không có box: `wrong_sku` với tên thật `T` → thêm một `missed` của `T` tại tâm box; các câu khác → không thêm gì.
    - Audit không có `candidate_version` → phía live là chính audit đó, phía ứng viên `None`.
- `capture_boxes(item)`: khi dòng capture có `candidate_detections_json`, trả `merge_boxes(...)`; không có thì như hiện nay.
- `_write_frame_audit` ghi thêm `candidate_version` khi capture có.
- `_audit_view(item)` bỏ ba khoá `PRIVATE_KEYS` khỏi từng box trước khi trả cho trình duyệt. Mọi chỗ tính số của trang Model (`_handle_model_summary` và các hàm nó gọi) dùng phía live của `split_audit`.
- `sample_compare(s3_client, ddb_resource, camera_id, items, hour, rng, state) -> list[str]` — khi `state["candidate"]` có và dòng phiên bản của nó ở `parallel`: trong các capture của giờ đó có kết quả của đúng ứng viên ấy và `differs(...)`, lấy ngẫu nhiên một capture chưa là `AUD-`/`TRN-` của giờ đó, ghi audit `CMP-<camera>-<YYYYMMDD>-<n>` với `purpose "compare"`. Không ghi khi ngày đó đã có `CMP_PER_DAY` frame. `_run_hour` gọi nó sau `sample_frames`.
- `_purpose` trả `"compare"` cho id bắt đầu bằng `CMP-`. `_is_scoring` không đổi.

- [ ] **Step 1: Test**

```python
LIVE = [box(1, "original145", 0.9, [100, 100, 60, 120]), box(2, "cheese145", 0.8, [300, 100, 60, 120])]
CAND = [
    box(1, "original145", 0.7, [104, 102, 60, 120]),
    box(2, "hot160", 0.9, [302, 98, 60, 120]),
    box(3, "cheese145", 0.6, [500, 100, 60, 120]),
]


def test_merge_pairs_one_to_one_and_hides_disputed_names():
    merged = compare.merge_boxes(LIVE, CAND)
    assert [(b["src"], b["sku_id"], b["needs_flavour"]) for b in merged] == [
        ("both", "original145", False),
        ("both", None, True),
        ("cand", None, True),
    ]
    assert [b["box"] for b in merged][:2] == [[100, 100, 60, 120], [300, 100, 60, 120]]
    assert (merged[1]["live_sku"], merged[1]["cand_sku"]) == ("cheese145", "hot160")


def test_two_candidate_boxes_on_one_can_leave_one_unpaired():
    cand = [box(1, "original145", 0.9, [100, 100, 60, 120]), box(2, "original145", 0.5, [110, 104, 60, 120])]
    merged = compare.merge_boxes(LIVE[:1], cand)
    assert [b["src"] for b in merged] == ["both", "cand"]
    assert merged == compare.merge_boxes(LIVE[:1], list(reversed(cand)))


def test_capture_without_a_candidate_gives_the_old_boxes():
    item = {"detections_json": json.dumps([{"sku_id": "original145", "conf": 0.9, "box": [1, 2, 3, 4]}])}
    assert model_health.capture_boxes(item) == [
        {"box_id": 1, "sku_id": "original145", "conf": 0.9, "box": [1, 2, 3, 4]}
    ]


def test_split_audit_gives_each_side_its_own_verdicts():
    audit = merged_audit(
        LIVE, CAND, verdicts={1: ("correct", None), 2: ("wrong_sku", "hot160"), 3: ("wrong_sku", "cheese145")}
    )
    live, cand = compare.split_audit(audit)
    assert verdicts_of(live) == {1: "correct", 2: "wrong_sku"}
    assert [m["sku_id"] for m in live["missed"]] == ["cheese145"]
    assert verdicts_of(cand) == {1: "correct", 2: "correct", 3: "correct"}
    assert cand["missed"] == []


def test_the_browser_never_learns_which_version_drew_a_box(api):
    put_audit(api, "AUD-CAM-S01-A-2026112710", ai_boxes=compare.merge_boxes(LIVE, CAND), candidate_version="v2")
    body = api.get("/model/audits/AUD-CAM-S01-A-2026112710", as_group="field_team").json()
    assert all(not set(b) & {"src", "live_sku", "cand_sku"} for b in body["ai_boxes"])


def test_compare_frames_stop_at_eight_a_day(tables):
    for hour in range(6, 22):
        sample_compare_for(tables, hour, differing_captures=3)
    assert len(tables.audits_with_prefix("CMP-CAM-S01-A-20261127")) == 8
```

- [ ] **Step 2:** Chạy `tests/test_compare.py`, `tests/test_audit_scoring.py`, `tests/test_backend_api.py` — phải trượt.
- [ ] **Step 3:** Viết code. Thêm vào `tests/test_audit_scoring.py` một test: KPI của một audit không có `candidate_version` giống hệt trước khi đổi (lấy số từ một test sẵn có).
- [ ] **Step 4:** `python -m pytest -q` — phải qua.
- [ ] **Step 5:** Commit: `Model page: a frame shows both versions' boxes as one set, and a disputed box shows no name`.

### Task 7: Kết luận của một lần chạy song song, và route của trang Model

**Files:**
- Modify: `backend/compare.py`, `backend/api/handler.py` (`_route_model`, ba hàm xử lý mới), `backend/openapi.yaml`, `tests/test_compare.py`, `tests/test_backend_api.py`

**Interfaces:**
- Consumes: `split_audit` (Task 6); `can`, `STATE_ID` (Task 5); `criteria` của dòng phiên bản (runner chép từ `release.json`, Task 8).
- Produces trong `backend/compare.py`:
  - `binomial_two_sided(k: int, n: int) -> float` — phép thử nhị thức chính xác hai phía với p = 0,5; `n == 0` trả `1.0`.
  - `tally(audits: list[dict], version: str) -> dict` — chỉ lấy audit `done`, id `AUD-` hoặc `CMP-`, có `candidate_version == version`. Trả `{"frames": số audit AUD-, "days": số ngày khác nhau của chúng, "cand_wins": n, "live_wins": n, "per_sku": {sku: {"units": n, "live_right": n, "cand_right": n}}}`. Một box là `cand_wins` khi phía ứng viên đúng và phía live sai hoặc sót; `live_wins` ngược lại; `out_of_scope` không tính.
  - `verdict(t: dict, criteria: dict) -> dict` — `{"state", "missing": [...], "p", "sku_drops": [...]}`:
    - `waiting` khi `days < min_days`, `frames < min_frames` hoặc `cand_wins + live_wins < min_diff_boxes`; `missing` nêu từng thứ còn thiếu và thiếu bao nhiêu;
    - `worse` khi có sản phẩm từ 10 `units` trở lên mà tỉ lệ đúng của ứng viên thấp hơn của live quá `max_sku_drop`, hoặc `live_wins > cand_wins` và `p < alpha`;
    - `better` khi `cand_wins > live_wins` và `p < alpha`;
    - còn lại `no_difference`.
- Route (đều cần đăng nhập; hai route ghi chỉ cho `team_admin`):
  - `GET /model/versions?camera_id=` → `{"state": {...}, "versions": [...], "candidate": {"version", "tally", "verdict", "criteria"} | null}`. Dòng ứng viên chưa có `criteria` thì `verdict` là `{"state": "waiting", "missing": ["criteria"], …}`.
  - `POST /model/versions/request` body `{"camera_id", "action": "put_live"|"discard"|"rollback", "version_id"?}` → 409 kèm câu của `can(...)` khi không được phép; được phép thì ghi `request = {id, action, version_id, by, at}` vào dòng `#state` với điều kiện dòng chưa có yêu cầu đang chạy, trả 202.

- [ ] **Step 1: Test**

```python
DETECTOR = {"min_days": 3, "min_frames": 30, "min_diff_boxes": 0, "alpha": 0.05, "max_sku_drop": 0.05}


def test_exact_binomial():
    assert compare.binomial_two_sided(0, 6) == pytest.approx(0.03125)
    assert compare.binomial_two_sided(2, 10) == pytest.approx(0.109375)
    assert compare.binomial_two_sided(0, 0) == 1.0


def test_tally_ignores_frames_of_another_candidate_and_frames_without_one():
    audits = [judged("AUD-…10", "v2", cand_wins=2), judged("AUD-…11", "v3", cand_wins=5), judged("AUD-…12", None)]
    t = compare.tally(audits, "v2")
    assert (t["frames"], t["cand_wins"], t["live_wins"]) == (1, 2, 0)


def test_verdict_waits_until_the_criteria_are_met():
    t = {"frames": 12, "days": 2, "cand_wins": 9, "live_wins": 0, "per_sku": {}}
    v = compare.verdict(t, DETECTOR)
    assert v["state"] == "waiting" and v["missing"] == ["1 more day", "18 more judged frames"]


def test_verdict_better_worse_and_no_difference():
    base = {"frames": 40, "days": 4, "per_sku": {}}
    assert compare.verdict({**base, "cand_wins": 9, "live_wins": 1}, DETECTOR)["state"] == "better"
    assert compare.verdict({**base, "cand_wins": 1, "live_wins": 9}, DETECTOR)["state"] == "worse"
    assert compare.verdict({**base, "cand_wins": 4, "live_wins": 3}, DETECTOR)["state"] == "no_difference"


def test_one_product_six_points_down_makes_it_worse():
    per_sku = {"Slide Original 145g": {"units": 50, "live_right": 45, "cand_right": 42}}
    t = {"frames": 40, "days": 4, "cand_wins": 12, "live_wins": 2, "per_sku": per_sku}
    v = compare.verdict(t, DETECTOR)
    assert v["state"] == "worse" and v["sku_drops"] == ["Slide Original 145g"]


def test_only_team_admin_may_request_and_only_what_is_allowed(api):
    seed_parallel_candidate(api, verdict_state="waiting")
    body = {"camera_id": "CAM-S01-A", "action": "put_live", "version_id": "v2"}
    assert api.post("/model/versions/request", json=body, as_group="field_team").status_code == 403
    assert api.post("/model/versions/request", json=body, as_group="team_admin").status_code == 409
    seed_parallel_candidate(api, verdict_state="better")
    assert api.post("/model/versions/request", json=body, as_group="team_admin").status_code == 202
    assert api.post("/model/versions/request", json=body, as_group="team_admin").status_code == 409
```

- [ ] **Step 2:** Chạy hai file test — phải trượt.
- [ ] **Step 3:** Viết code; thêm ba đường vào `backend/openapi.yaml`.
- [ ] **Step 4:** `python -m pytest -q` — phải qua.
- [ ] **Step 5:** Commit: `Model page: the verdict of a parallel run, and requests to put a version live, discard it or roll back`.

### Task 8: `ops.runner` trên HUYHOANG

**Files:**
- Create: `ops/__init__.py`, `ops/decide.py`, `ops/runner.py`, `ops/make_release.py`, `tests/test_ops_decide.py`, `worker/windows/run-ops.ps1`, `worker/windows/register-ops-task.ps1`

**Interfaces:**
- Consumes: `release.read_pointer`, `write_pointer`, `load_release` (Task 1); dạng bảng phiên bản (Task 5).
- Produces trong `ops/decide.py` (không gọi AWS, không gọi hệ điều hành):
  - `NIGHT_FRAMES = 100`, `NIGHT_LIMIT = 1.0`
  - `night_rate(captures: list[dict], version: str) -> float | None` — trên các capture có `display_visible` sai và có kết quả của `version`: số box có tên sản phẩm trên 100 frame; chưa đủ `NIGHT_FRAMES` frame thì `None`.
  - `next_steps(pointer: Pointer, state: dict, versions: dict[str, dict], on_disk: list[str], worker_status: dict | None, night: float | None) -> list[tuple]` — danh sách việc theo thứ tự, mỗi việc là một bộ:
    - `("register", id)` cho mỗi bản trên đĩa chưa có dòng;
    - `("stop", id, reason)` khi `worker_status["stopped"]` có; khi `night > NIGHT_LIMIT`; hoặc khi ba giờ nạp gần nhất trong `worker_status["load_times"]` nằm trong vòng 15 phút (lý do `"worker restarts"`);
    - `("start_parallel", id)` khi không có ứng viên, không có yêu cầu đang chạy, và có đúng một bản `candidate` (nhiều hơn một thì lấy bản cũ nhất theo `created_at`);
    - với `state["request"]` chưa có kết quả: `("point", Pointer mới)` nếu con trỏ chưa đúng đích, rồi `("restart_worker",)`, rồi `("confirm", request_id, model_version mong đợi)`. Con trỏ đã đúng đích thì không có `"point"`: đó là trường hợp runner chết giữa chừng.
    - `("sync_status", id, worker_status)` khi số của worker khác số trong dòng.
  - Đích của con trỏ: `put_live` → `live = version, previous = live cũ, candidate = None`; `discard` → chỉ xoá `candidate`; `rollback` → `live = previous, previous = live cũ, candidate = None`; `stop` → xoá `candidate`.
- `ops/runner.py`: `python -m ops.runner --root C:\Users\huyho\Datagent --camera CAM-S01-A --store DEMO-S01 [--once]`; mỗi 60 giây đọc đĩa, bảng và captures của đêm, gọi `next_steps`, làm từng việc. `register` đọc bản bằng `load_release` và chép `kind`, `parent`, `criteria` (đã điền mặc định theo `kind`), `created_at` vào dòng mới với `status = "candidate"`. `start_parallel` ghi `parallel_started_at`, đặt `status = "parallel"`, đặt ứng viên vào con trỏ và vào dòng `#state`, rồi khởi động lại worker. `restart_worker` = `Stop-ScheduledTask milk-worker; Start-ScheduledTask milk-worker`. `confirm` = chờ tối đa 10 phút một capture mới có `model_version` mong đợi, rồi ghi `last_result` và đổi `status` của các dòng (bản lên live → `live`, bản bị thay → `replaced`, bản bị bỏ → `discarded`, bản bị dừng → `stopped` kèm `stopped_reason`). Quá 10 phút thì `last_result.ok = false` với câu nêu `model_version` đang thấy; không tự quay lui.
- `ops/make_release.py`:
  - `python -m ops.make_release --root R --id ID --kind KIND --from-env worker.env` — `env` của bản là các khoá model của file (trừ `MILK_MODEL_VERSION`);
  - `… --from-release ID0 [--set KEY=VALUE …] [--criteria '{"min_days":1,"min_frames":5}']` — chép `env` của bản khác, `parent = ID0`.
  - Từ chối ghi đè thư mục đã có. Lần đầu (`--from-env` và chưa có `live.json`) thì ghi luôn `live.json` trỏ tới bản đó.
- `run-ops.ps1` đặt `AWS_SHARED_CREDENTIALS_FILE`, `AWS_CONFIG_FILE`, `AWS_PROFILE=milk`, chạy runner bằng `.venv-ops`, ghi `logs\ops-yyyy-MM-dd.log`, tự chạy lại sau 30 giây như `run-worker.ps1`. `register-ops-task.ps1` đăng ký task `milk-ops` (SYSTEM, lúc khởi động) theo mẫu `register-task.ps1`.

- [ ] **Step 1: Test**

```python
def test_a_new_release_on_disk_is_registered_then_started():
    steps = next_steps(P(live="v1"), state(live="v1"), {"v1": row("live")}, ["v1", "v2"], None, None)
    assert steps == [("register", "v2")]
    steps = next_steps(
        P(live="v1"), state(live="v1"), {"v1": row("live"), "v2": row("candidate")}, ["v1", "v2"], None, None
    )
    assert steps == [("start_parallel", "v2")]


def test_put_live_points_restarts_and_confirms():
    st = state(live="v1", candidate="v2", request={"id": "r1", "action": "put_live", "version_id": "v2"})
    steps = next_steps(P(live="v1", candidate="v2"), st, rows(v1="live", v2="parallel"), ["v1", "v2"], None, None)
    assert steps == [("point", P(live="v2", previous="v1")), ("restart_worker",), ("confirm", "r1", "v2")]


def test_a_request_half_done_is_finished_not_repeated():
    st = state(live="v1", candidate="v2", request={"id": "r1", "action": "put_live", "version_id": "v2"})
    steps = next_steps(P(live="v2", previous="v1"), st, rows(v1="live", v2="parallel"), ["v1", "v2"], None, None)
    assert steps == [("restart_worker",), ("confirm", "r1", "v2")]


def test_rollback_swaps_live_and_previous():
    st = state(live="v2", previous="v1", request={"id": "r2", "action": "rollback"})
    steps = next_steps(P(live="v2", previous="v1"), st, rows(v1="replaced", v2="live"), ["v1", "v2"], None, None)
    assert steps[0] == ("point", P(live="v1", previous="v2"))


def test_a_stopped_or_night_drawing_candidate_is_stopped():
    st = state(live="v1", candidate="v2")
    args = (P(live="v1", candidate="v2"), st, rows(v1="live", v2="parallel"), ["v1", "v2"])
    assert next_steps(*args, {"candidate": "v2", "stopped": "too_slow"}, None)[0] == ("stop", "v2", "too_slow")
    assert next_steps(*args, None, 1.4)[0] == ("stop", "v2", "night boxes: 1.4 per 100 frames")
    assert next_steps(*args, None, 0.8) == []


def test_three_loads_within_fifteen_minutes_stop_the_candidate():
    st = state(live="v1", candidate="v2")
    args = (P(live="v1", candidate="v2"), st, rows(v1="live", v2="parallel"), ["v1", "v2"])
    quick = status(
        "v2", load_times=["2026-11-28T09:00:00+07:00", "2026-11-28T09:04:00+07:00", "2026-11-28T09:09:00+07:00"]
    )
    slow = status(
        "v2", load_times=["2026-11-27T09:00:00+07:00", "2026-11-28T05:50:00+07:00", "2026-11-28T09:09:00+07:00"]
    )
    assert next_steps(*args, quick, None)[0] == ("stop", "v2", "worker restarts")
    assert next_steps(*args, slow, None) == []


def test_night_rate_waits_for_a_hundred_frames():
    assert night_rate(night_captures(99, boxes=5, version="v2"), "v2") is None
    assert night_rate(night_captures(200, boxes=3, version="v2"), "v2") == 1.5
```

- [ ] **Step 2:** `python -m pytest tests/test_ops_decide.py -q` — phải trượt.
- [ ] **Step 3:** Viết `ops/decide.py`, rồi `ops/runner.py` và `ops/make_release.py` quanh nó. Thêm test cho `make_release`: bản tạo từ một `worker.env` mẫu cho `release.model_env(env_của_file, bản)` bằng đúng các khoá model của file đó cộng `MILK_MODEL_VERSION`; ghi đè thư mục đã có thì lỗi.
- [ ] **Step 4:** `python -m pytest -q` và `ruff check . && ruff format --check .` — phải qua.
- [ ] **Step 5:** Commit: `Ops: a runner on the counting machine carries out the Model page's requests`.

### Task 9: Trang Model, khối "Model versions" và frame so sánh

**Files:**
- Create: `frontend/lib/model-versions.ts`, `frontend/lib/model-versions.test.ts`, `frontend/components/model/ModelVersions.tsx`
- Modify: `frontend/lib/api.ts`, `frontend/lib/audit-labeling.ts` (`labelQueueOrder`), `frontend/lib/audit-labeling.test.ts`, `frontend/components/model/ModelQualityView.tsx`, `frontend/components/model/AuditLabeler.tsx`

**Interfaces:**
- Consumes: `GET /model/versions`, `POST /model/versions/request` (Task 7).
- Produces:
  - `api.getModelVersions(cameraId: string)`, `api.requestModelVersion(body)`; kiểu `ApiModelVersions`, `ApiModelVersion`, `ApiVerdict`.
  - `verdictText(v: ApiVerdict): string` — `better` → `"Better than the live version"`; `no_difference` → `"No difference seen"`; `worse` → `"Worse than the live version"`; `waiting` → `"Needs " + missing.join(" and ") + " before a decision."`
  - `canPutLive(v: ApiVerdict | null, isAdmin: boolean, busy: boolean): boolean` — đúng khi admin, không bận, và `state` là `better` hoặc `no_difference`.
  - `statusText(status: string, reason?: string): string` — `parallel` → `"Running in parallel"`, `stopped` → `"Stopped: " + reason`, `discarded` → `"Discarded"`, `replaced` → `"Replaced"`, `live` → `"Live"`, `candidate` → `"Waiting to start"`.
  - `labelQueueOrder`: scoring, compare, training, review.
- Khối `ModelVersions` (đặt ngay dưới dòng "Camera and worker" của trang Model, có `data-model-versions`):
  - dòng live: `Live: {id}, since {dd/mm hh:mm}`;
  - dòng ứng viên: `Candidate: {id}`, `statusText`, `{days} days, {frames} frames judged`, `verdictText`, và bảng theo sản phẩm (Product, Units judged, Live right, Candidate right);
  - nút `Put live`, `Discard`, `Roll back to {previous}`: chỉ `team_admin` thấy; `Put live` bị khoá theo `canPutLive`;
  - hộp xác nhận của `Put live` và `Roll back`: `The counting worker restarts; counting pauses for about a minute.`;
  - sau khi gửi: `Waiting for the counting machine…` cho tới khi `last_result` của yêu cầu đó về; `ok` sai thì hiện `message`;
  - không có ứng viên: `No candidate version.`
  - phần gập `History`: các bản theo `created_at` mới nhất trước, mỗi dòng `{id} · {statusText} · {dd/mm}`.
- `AuditLabeler`: frame `compare` có nhãn `Comparison frame` ở chỗ đang ghi `Review frame`. Không thêm chữ nào nói tới hai model trên box.

- [ ] **Step 1: Test** (`frontend/lib/model-versions.test.ts`, `audit-labeling.test.ts`)

```ts
test("waiting verdict lists what is missing", () => {
  assert.equal(
    verdictText({ state: "waiting", missing: ["1 more day", "18 more judged frames"], p: 1, sku_drops: [] }),
    "Needs 1 more day and 18 more judged frames before a decision."
  );
});

test("put live only for an admin, when idle, on better or no difference", () => {
  const v = (state: string) => ({ state, missing: [], p: 0.01, sku_drops: [] }) as ApiVerdict;
  assert.equal(canPutLive(v("better"), true, false), true);
  assert.equal(canPutLive(v("no_difference"), true, false), true);
  assert.equal(canPutLive(v("worse"), true, false), false);
  assert.equal(canPutLive(v("waiting"), true, false), false);
  assert.equal(canPutLive(v("better"), false, false), false);
  assert.equal(canPutLive(v("better"), true, true), false);
  assert.equal(canPutLive(null, true, false), false);
});

test("comparison frames come after scoring frames and before training frames", () => {
  const order = labelQueueOrder([item("TRN-1", "training"), item("CMP-1", "compare"), item("REV-1", "review"), item("AUD-1", "scoring")]);
  assert.deepEqual(order.map((a) => a.audit_id), ["AUD-1", "CMP-1", "TRN-1", "REV-1"]);
});
```

- [ ] **Step 2:** `cd frontend && npm test` — phải trượt ở ba test mới. (Chữ ký thật của `labelQueueOrder` lấy theo file đang có; sửa cách gọi trong test cho khớp.)
- [ ] **Step 3:** Viết code.
- [ ] **Step 4:** `npm test && npm run build` — phải qua.
- [ ] **Step 5:** Commit: `Model page: the versions block, with put live, discard and roll back for the team admin`.

### Task 10: Tài liệu vận hành

**Files:**
- Modify: `worker/README.md` (mục "Phiên bản model")
- Ngoài repo: `C:\Users\huyho\Datagent\TRAINING.md` trên HUYHOANG (sao lưu `TRAINING.md.bak-<ngày>` trước khi sửa)

- [ ] **Step 1:** `worker/README.md`: thay đoạn "Mỗi lần đổi trọng số thì đặt lại biến trong `worker.env`" bằng cách mới: thư mục bản chạy, `live.json`, `ops.make_release`, khối "Model versions"; giữ một đoạn "Khi `milk-ops` hỏng" với cách đổi tay (sửa `live.json`, khởi động lại task) và cách bỏ hẳn (xoá `MILK_RELEASES_DIR` khỏi `worker.env`).
- [ ] **Step 2:** `TRAINING.md`, mục "Đổi model cho worker": cùng nội dung, viết theo đường dẫn của HUYHOANG.
- [ ] **Step 3:** Commit: `Worker README: models change through releases and the Model page`.

### Task 11: Kiểm trên máy, rồi lên live theo hai đợt khi hoang duyệt

- [ ] **Step 1:** `python -m pytest -q`, `ruff check . && ruff format --check .`, `cfn-lint infra/backend.yaml`, `cd frontend && npm test && npm run build` — đều phải qua.
- [ ] **Step 2: Kiểm trên laptop bằng bản build và dữ liệu giả.** Chạy hub cục bộ và một worker `MILK_PIPELINE=null` với hai bản chạy giống nhau làm live và ứng viên, trên một file video; khẳng định: có file `*.candidate.json` cho mỗi capture đã lưu; `candidate-status.json` có `late = 0`; kết quả live giống hệt một lần chạy không có ứng viên.
- [ ] **Step 3: DỪNG. Báo hoang và xin duyệt đợt 1.**
- [ ] **Step 4: Đợt 1, chỉ worker.** Trên HUYHOANG:
  - đưa nhánh sang bằng git bundle như các lần trước; giữ nhánh quay lui `backup/pre-releases-<ngày>` và `worker.env.bak-<ngày>`;
  - `python -m ops.make_release --root C:\Users\huyho\Datagent\releases --id "long-store-v1-det+slide-v3" --kind baseline --from-env C:\Users\huyho\Datagent\worker.env`;
  - thêm `MILK_RELEASES_DIR=C:/Users/huyho/Datagent/releases` vào `worker.env` (bằng script `.ps1` không in file, như ghi chú vận hành);
  - khởi động lại task `milk-worker`.
  - Xong khi: hai cửa sổ kế tiếp có capture với `model_version = long-store-v1-det+slide-v3`, số box TH và Slide nằm trong khoảng của một giờ trước đó, log của worker không có dòng lỗi.
  - Quay lui: chép `worker.env.bak-<ngày>` về, `git checkout backup/pre-releases-<ngày>`, khởi động lại task.
- [ ] **Step 5: DỪNG. Báo hoang và xin duyệt đợt 2.**
- [ ] **Step 6: Đợt 2.** Theo thứ tự:
  1. backend: `backend_changeset.sh <sha> create-template` (một bảng mới, hai biến môi trường, một dòng IAM; không thay thế tài nguyên nào), xem, `execute`. Trước đó kiểm script đóng gói Lambda có đưa `compare.py` và `model_versions.py` vào cả hai file zip;
  2. hub: phát hành theo `docs/runbook.md` mục 2;
  3. website: Amplify;
  4. HUYHOANG: cập nhật nhánh, khởi động lại `milk-worker`, chạy `worker\windows\register-ops-task.ps1`.
  - Đo bộ nhớ GPU trước và sau khi worker nạp một ứng viên; ghi số vào ledger.
- [ ] **Step 7: Kiểm bằng một ứng viên giả.**
  - `python -m ops.make_release --root … --id "long-store-v1-det+slide-v3-same-<ngày>" --kind rules --from-release "long-store-v1-det+slide-v3" --criteria "{\"min_days\":1,\"min_frames\":5}"`.
  - Trong 10 phút: khối "Model versions" hiện ứng viên `Running in parallel`; capture mới có `candidate_version`; `/products` và Dashboard cho cùng số như trước khi có ứng viên (so bằng `opt2_run.py` phía người xem).
  - Sau một ngày: các frame `AUD-` của ngày đó không có box "?" nào (hai bản giống nhau), không có frame `CMP-` nào, `late = 0`, kết luận `No difference seen` sau khi đủ 1 ngày và 5 frame đã chấm.
  - hoang (hoặc tài khoản thử, khi hoang cho phép) bấm `Put live`: trong 10 phút capture mới mang `model_version` của bản mới. Bấm `Roll back`: capture trở lại `long-store-v1-det+slide-v3`. Không ai mở `worker.env`.
  - Bản giống hệt không sinh ra box tranh chấp nào, nên kiểm thêm một ứng viên khác đi một chút: `… --id "long-store-v1-det+slide-v3-conf35-<ngày>" --kind rules --from-release "long-store-v1-det+slide-v3" --set MILK_SLIDE_CONF=0.35`. Trong hai giờ: có ít nhất một frame `CMP-` hoặc một frame `AUD-` mang box "?"; mở frame đó bằng tài khoản thử thì box "?" không có tên gợi ý, và câu trả lời của API không có `src`, `live_sku`, `cand_sku`. Xong thì bấm `Discard`; capture kế tiếp không còn `candidate_version`.
- [ ] **Step 8:** Ghi memory. Push và PR khi hoang bảo.
