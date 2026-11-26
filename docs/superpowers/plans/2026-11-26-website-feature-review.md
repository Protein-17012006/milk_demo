# Đánh giá tính năng website — kế hoạch làm

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Một báo cáo xếp loại mọi tính năng của website (giữ, sửa, chuyển chỗ, bỏ) theo góc nhìn của người
thường và của team vận hành, kèm danh sách thay đổi đáng làm nhất cho cảm giác dùng.

**Architecture:**
- Một script trình duyệt đăng nhập bản đang chạy bằng tài khoản thử của từng nhóm, đi từng trang, chụp ảnh,
  lưu chữ trên màn hình và mọi câu trả lời của API. Script chặn mọi lệnh ghi, nên bấm nhầm cũng không đổi dữ
  liệu thật.
- Người làm đọc ảnh và mã nguồn, viết bảng xếp loại vào một file trong `docs/reviews/`.
- Từ file đó dựng một trang báo cáo riêng tư có ảnh.

**Tech Stack:** Python 3.12 + boto3 (lấy tài khoản thử từ SSM), Node 22 + `puppeteer-core@23.11.1` điều khiển
Edge đã cài sẵn, Artifact cho trang báo cáo.

**Spec:** `docs/superpowers/specs/2026-11-26-website-feature-review-design.md` (hoang duyệt 26/11).

## Global Constraints

- **Không sửa, không xoá, không deploy gì.** Đợt này chỉ ra báo cáo.
- **Không ghi dữ liệu thật.** Script huỷ mọi request tới host `qq20q6drmi.execute-api.ap-southeast-1.amazonaws.com`
  có method khác `GET` và `OPTIONS`, và ghi nó vào `blocked`. Tính năng ghi chỉ xem tới bước trước khi lưu.
- **Không gửi form Register.** Script huỷ request tới `cognito-idp` có `X-Amz-Target` kết thúc bằng một trong:
  `SignUp`, `ConfirmSignUp`, `ResendConfirmationCode`, `ForgotPassword`, `ConfirmForgotPassword`,
  `ChangePassword`, `UpdateUserAttributes`, `SetUserMFAPreference`, `AssociateSoftwareToken`,
  `VerifySoftwareToken`, `DeleteUser`.
- **Website:** `https://main.d2k8euxy0yoiv8.amplifyapp.com`.
- **Tài khoản thử** (SSM, profile `default`, vùng `ap-southeast-1`): người thường = `/milk-demo/web/api-check-account`
  (nhóm `datagent`); team = `/milk-demo/web/model-check-account` (nhóm `team_admin`). Không có tài khoản thử
  `field_team`: phần khác biệt của nhóm này đọc từ mã nguồn.
- **Cỡ màn hình:** máy tính 1440×1000; điện thoại 390×844 (chỉ trang đăng nhập và Dashboard).
- **Xếp loại** chỉ dùng bốn từ: `giữ`, `sửa`, `chuyển chỗ`, `bỏ`. Thứ chưa có ghi ở mục riêng "Còn thiếu".
- **Mỗi tính năng ghi bốn điều bằng lời, không chấm điểm số:** cho ai điều gì; có dễ thấy và dễ hiểu không;
  có tác dụng thật không; có hiện cho đúng nhóm không.
- **Kết luận `bỏ`** phải nói rõ tính năng đó không giúp việc nào của ai.
- **Ảnh** không lộ mã MFA hay mã QR. Không dùng ảnh khung hình camera có người lọt vào.
- **Không làm:** đo lượt dùng, bật ghi log, đánh giá độ chính xác của model, tính số bán.
- **Ảnh và file tạm** nằm trong scratchpad của phiên làm (gọi là `$SP`), không vào repo vì repo nằm trong
  OneDrive. Chỉ file chữ của báo cáo vào repo.
- **Ngôn ngữ báo cáo:** tiếng Việt; tên nút và tên mục giữ nguyên tiếng Anh như trên màn hình.

## Review Focus

Những chỗ bản thiết kế không nói tới nhưng dễ làm kết luận sai. Mỗi dòng đã được gắn vào một task.

1. **Tính năng có trên màn hình nhưng không có trong "Danh sách đi qua" của spec.** Mỗi trang phải được dò
   hết nút, ô nhập và liên kết; thứ ngoài danh sách vẫn được một dòng trong bảng. (Task 1 `controls`, Task 4.)
2. **Xem vào lúc tiệm đóng hoặc camera không thấy kệ.** Một thẻ để "—" lúc đó không phải là thẻ vô dụng. Báo
   cáo ghi ngày giờ và trạng thái lúc xem; không xếp `bỏ` chỉ vì lúc xem không có số. (Task 2, Task 4.)
3. **Người thường mở thẳng đường dẫn của team.** Thanh bên giấu trang Model, nhưng gõ `/model/` thì sao, và API
   có trả dữ liệu không. (Task 2.)
4. **Người mới đăng ký, chưa được duyệt.** Không tạo được tài khoản như vậy trong đợt này, nên màn hình họ thấy
   phải đọc từ mã nguồn. (Task 3.)
5. **Chờ lâu mới ra số.** Dashboard gọi khoảng 9 API cùng lúc trong khi tài khoản AWS chỉ cho 10 Lambda chạy
   song song. Thời gian chờ là một phần của cảm giác dùng và phải được đo. (Task 1 `timings`, Task 2.)

---

### Task 1: Script đi website có chặn ghi

**Files** (ngoài repo):
- Nguồn để chép: `C:\Users\huyho\AppData\Local\Temp\claude\cf23e0181d28b9db\254ea2d8-f7ed-40e5-b977-07c6cb98101b\scratchpad\`
  (`tour_run.py`, `browser\tour.cjs`, `browser\tour2.cjs`).
- Thư viện dùng lại: `...\9b090daa-c672-470b-b293-4eed28f4e767\scratchpad\venv` (boto3) và
  `...\9b090daa-...\scratchpad\browser\node_modules` (puppeteer-core). Nếu đã bị dọn: `python -m venv` rồi
  `pip install boto3`, và `npm i puppeteer-core@23.11.1`.
- Create: `$SP\review_run.py`, `$SP\browser\review.cjs`, thư mục `$SP\api\`.

**Interfaces:**
- Produces: `python review_run.py ACCOUNT OUT_NAME STEPS`, với `ACCOUNT` là `datagent` hoặc `admin`, `STEPS`
  là danh sách tên bước cách nhau bằng dấu phẩy. Kết quả nằm ở `$SP\shots\OUT_NAME\`:
  `NN-ten.png`, `NN-ten.txt` (chữ trên màn hình), `NN-ten.controls.json`, `api-*.json`, `result.json`.
- `result.json` có các khoá: `shots`, `api` (`{step, method, path, status}`), `blocked` (`{step, method, url}`),
  `failed`, `notes`, `consoleErrors`, `timings` (`{<step>: {first_api_ms, last_api_ms}}` tính từ lúc bắt đầu
  mở trang).
- Hàm trong `review.cjs` mà Task 2 và 3 dùng: `shot(name, full)`, `shootAt(name, headingText)`,
  `clickByText(tag, text, nth)`, `dumpText(name)`, `controls(name)`, `setPhone()`, `setDesktop()`.

- [ ] **Step 1:** Chép `tour_run.py` thành `review_run.py`. Đổi `NODE_MODULES` thành đường dẫn tuyệt đối ở trên,
  script mặc định thành `review.cjs`, `STEPS` thành tham số bắt buộc. Giữ nguyên phần chờ mã TOTP (file
  `api\totp-ACCOUNT.last`): Cognito chỉ nhận mỗi mã một lần.
- [ ] **Step 2:** Chép `tour.cjs` thành `review.cjs`, lấy thêm `shootAt` từ `tour2.cjs`. Bỏ các bước đi trang
  có sẵn, chỉ để lại bước `home` tối thiểu (mở `/`, `shot("10-home")`, `dumpText`, `controls`); các bước còn
  lại do Task 2 và 3 thêm vào. Phần lưu câu trả lời API: khi thân không phải JSON (file CSV) thì lưu 2000 ký
  tự đầu dưới dạng chữ.
- [ ] **Step 3:** Thêm chặn ghi: `page.setRequestInterception(true)`, huỷ request theo hai luật ở Global
  Constraints, ghi vào `out.blocked`, còn lại cho đi.
- [ ] **Step 4:** Thêm `controls(name)`: ghi mọi `button`, `a`, `input`, `select`, `[role=option]`,
  `[role=tab]` đang hiển thị, kèm chữ hoặc `aria-label` hoặc `placeholder`, và có bị `disabled` không.
- [ ] **Step 5:** Thêm `timings`, `setPhone()` (390×844, `isMobile: true`) và `setDesktop()` (1440×1000).
- [ ] **Step 6:** Thêm bước `blocktest`: sau khi đăng nhập, trong trang chạy
  `fetch("https://qq20q6drmi.execute-api.ap-southeast-1.amazonaws.com/v1/__review_block_test", {method: "POST"})`.
  Đường dẫn này không tồn tại, nên nếu chặn hỏng thì API Gateway cũng chỉ trả lỗi và không đổi gì.
- [ ] **Step 7: Kiểm.** Chạy `python review_run.py datagent t1 home,blocktest`.
  Mong đợi: `fatal: None`; `blocked` có đúng một dòng `POST …/__review_block_test`; `api` không có dòng nào
  của đường dẫn đó; có `10-home.png` và `10-home.controls.json`.

### Task 2: Đi website bằng tài khoản người thường

**Files:** Modify `$SP\browser\review.cjs` (thêm các bước). Kết quả ở `$SP\shots\viewer\`.

**Interfaces:**
- Consumes: mọi hàm của Task 1.
- Produces: bộ ảnh và file chữ có tên bước dưới đây, để Task 4 dẫn tới.

- [ ] **Step 1: `login`.** Chụp trang đăng nhập ở cả hai cỡ màn hình, trang `/register/` (chỉ xem), và bước
  nhập mã 6 số **trước khi gõ mã**.
- [ ] **Step 2: `sidebar`, `home`.** Thu gọn và mở lại thanh bên; mở menu tài khoản; gõ vào ô tìm của thanh
  bên. Ở Home: chụp lúc mới vào; gõ `slide` vào ô tìm; mở một sản phẩm để ra hộp xem nhanh; bấm "View in
  Reports"; bấm hai nút "..." của Recents và ghi có gì xảy ra không.
- [ ] **Step 3: `dashboard`.** Ghi `timings`. Chụp cả trang rồi `shootAt` từng mục: sáu thẻ số, "Shelf Stock
  Count", "Trends & Insights", "Recent Shelf Activities". Chọn lần lượt bốn Timeframe; mở danh sách Store và
  Category; bấm từng nút đổi chỉ số của Trends; mở ảnh của một sự kiện; mở "xem tất cả"; ghi nút xác nhận sự
  kiện có hiện với người thường không. Bấm Download (đây là lệnh đọc) và ghi 5 dòng đầu của câu trả lời CSV.
- [ ] **Step 4: `dashboard-phone`.** `setPhone()`, chụp Dashboard, ghi thứ gì bị tràn, bị che hoặc phải cuộn
  ngang, rồi `setDesktop()`.
- [ ] **Step 5: `category`.** Chụp mặc định và sau "Expand all". Gõ `TH` vào ô tìm; mở từng bộ lọc Store,
  Category, Status và Sort; tích một ô chọn và ghi nó dẫn tới việc gì; mở thẻ của một sản phẩm rồi "View
  frame". Ghi người thường có thấy hàng chờ duyệt, "Confirm AI", "Correct", form "Human Audit & Correction",
  "Import SKU Master" không. Bấm "Export CV Output" (đây là lệnh đọc) và ghi 5 dòng đầu của câu trả lời CSV.
- [ ] **Step 6: `settings`, `model-direct`.** Chụp từng mục của Settings; ghi "Import Store List" và phần sửa
  Shelf plan có hiện không. Mở thẳng `/model/`: chụp, và ghi API có được gọi và trả gì.
- [ ] **Step 7: Kiểm.** Chạy `python review_run.py datagent viewer login,sidebar,home,dashboard,dashboard-phone,category,settings,model-direct`.
  Mong đợi: `fatal: None`; mọi dòng `api` có method `GET`; `blocked` rỗng (nếu không rỗng, ghi lại nút nào đã
  gửi lệnh ghi); mỗi bước có ít nhất một ảnh. Ghi vào `notes`: ngày giờ chạy, tiệm đang mở hay đóng, và
  Dashboard có hiện dòng báo camera không thấy kệ không.

### Task 3: Đi website bằng tài khoản team

**Files:** Modify `$SP\browser\review.cjs`. Kết quả ở `$SP\shots\team\`.

**Interfaces:**
- Consumes: mọi hàm của Task 1 và các bước của Task 2.
- Produces: bộ ảnh `team\`, và file `$SP\roles.md` liệt kê khác biệt giữa ba nhóm.

- [ ] **Step 1: `dashboard`, `category`, `settings` lần hai.** Chạy lại ba bước của Task 2 và chỉ ghi chỗ
  khác: nút xác nhận sự kiện, các nút Import, form Shelf plan sửa được.
- [ ] **Step 2: `model`.** Ghi `timings`. `shootAt` từng mục: "Datagent KPIs", "Per SKU", "Confusion (model →
  truth)", "By day", "Present or absent", "By time of day", "Live health, last 7 days". Đổi ô "Model version"
  và "Range"; đổi từng lựa chọn của "Health measure".
- [ ] **Step 3: `label`.** Mở "Label a frame" trên một khung hình. Chụp các lựa chọn Right / Wrong SKU / Not
  our SKU / Out of scope, ô "Missed SKU", bảng "Per SKU", lý do bỏ qua. Đóng lại, **không bấm lưu**.
- [ ] **Step 4: `review-queue`.** Ở Category: chụp hàng chờ duyệt; bấm "Correct" để mở thẻ trên lần đọc bị
  gắn cờ; chụp form "Human Audit & Correction"; đóng lại, **không bấm lưu**.
- [ ] **Step 5: `settings-edit`.** Đổi "Date Format" trên màn hình rồi **không lưu**; mở phần sửa Shelf plan,
  chụp, **không lưu**.
- [ ] **Step 6:** Đọc mã nguồn để viết `$SP\roles.md`: tìm `hasGroup(` và `groups` trong `frontend/`, và chỗ
  kiểm nhóm trong `backend/api/handler.py`. Ghi từng nhóm (`datagent`, `field_team`, `team_admin`) thấy gì và
  làm được gì; thêm màn hình của người đã đăng ký nhưng chưa được duyệt (`isApproved` sai) và của người chưa
  đăng nhập.
- [ ] **Step 7: Kiểm.** Chạy `python review_run.py admin team dashboard,category,settings,model,label,review-queue,settings-edit`.
  Mong đợi: `fatal: None`; mọi dòng `api` có method `GET`; `blocked` rỗng. `roles.md` có đủ năm dòng: ba
  nhóm, chưa được duyệt, chưa đăng nhập.

### Task 4: Bảng xếp loại theo từng trang

**Files:** Create `docs/reviews/2026-11-26-website-feature-review.md`.

**Interfaces:**
- Consumes: `$SP\shots\viewer\`, `$SP\shots\team\`, `$SP\roles.md`, mã nguồn trong `frontend/components/`.
- Produces: mục `## 3. Theo từng trang` của file, cấu trúc như sau. Task 5 viết mục 1 và 2.

```markdown
# Đánh giá tính năng website (26/11/2026)

Lúc xem: <ngày giờ>, <tiệm mở hay đóng>, <camera có thấy kệ không>.

## 1. Thay đổi đáng làm nhất
## 2. Còn thiếu
## 3. Theo từng trang
### Đăng nhập và đăng ký
| Tính năng | Cho người thường | Cho team vận hành | Nhận xét | Xếp loại | Đề xuất | Ảnh |
```

Các mục con của phần 3, theo thứ tự: Đăng nhập và đăng ký, Thanh bên, Home, Dashboard, Category, Model,
Settings. Cột "Nhận xét" viết ba ý ngắn theo thứ tự: dễ thấy và dễ hiểu; có tác dụng thật; đúng nhóm. Cột
"Ảnh" ghi tên file ảnh.

- [ ] **Step 1:** Với mỗi trang, so `*.controls.json` với "Danh sách đi qua" của spec. Thứ có trên màn hình mà
  không có trong danh sách thì thêm vào bảng.
- [ ] **Step 2:** Viết bảng từng trang. Mỗi mục trong "Danh sách đi qua" có ít nhất một dòng; sáu thẻ số của
  Dashboard mỗi thẻ một dòng; mỗi mục của trang Model một dòng.
- [ ] **Step 3:** Với mỗi dòng mà lúc xem không có số ("—", trống), kiểm bằng câu trả lời API đã lưu xem do
  tính năng hay do thời điểm, và viết rõ điều đó trong "Nhận xét".
- [ ] **Step 4: Kiểm.** Không ô nào trống. Cột "Xếp loại" chỉ có bốn từ cho phép. Mỗi dòng `bỏ` nói rõ không
  giúp việc nào của ai. Năm điều trong mục "Đã thấy khi đọc mã nguồn" của spec đều có dòng xác nhận hoặc bác
  bỏ.

### Task 5: Thay đổi đáng làm nhất và phần còn thiếu

**Files:** Modify `docs/reviews/2026-11-26-website-feature-review.md` (mục 1 và 2).

**Interfaces:**
- Consumes: bảng của Task 4, `timings` trong hai file `result.json`.

- [ ] **Step 1:** Viết mục 1, tối đa 10 thay đổi, xếp theo lợi ích so với công làm. Mỗi thay đổi có: đổi gì,
  cho ai, vì sao cảm giác dùng tốt hơn, công làm, file sẽ đụng tới. Công làm dùng ba mức: `nhỏ` (chỉ đổi chữ
  hoặc ẩn hiện), `vừa` (một component, không đụng backend), `lớn` (cần backend hoặc API mới).
- [ ] **Step 2:** Viết mục 2: thứ người thường hoặc team mong có mà chưa có, mỗi thứ gắn với một việc của họ
  trong spec. Không đưa số bán và ghi log vào đây.
- [ ] **Step 3:** Nếu `first_api_ms` hoặc `last_api_ms` của Dashboard trên 3000, đưa thời gian chờ vào mục 1
  kèm con số đo được.
- [ ] **Step 4: Kiểm.** Mỗi thay đổi ở mục 1 dẫn được tới ít nhất một dòng của mục 3. Mục 1 có cả việc cho
  người thường lẫn việc cho team, hoặc ghi rõ vì sao một bên không có.

### Task 6: Trang báo cáo có ảnh và bàn giao

**Files:** Create `$SP\report\index.html` và ảnh trong `$SP\report\img\`. Trang là Artifact riêng tư.

**Interfaces:**
- Consumes: file báo cáo của Task 4 và 5, ảnh trong `$SP\shots\`.

- [ ] **Step 1:** Chọn tối đa 30 ảnh, mỗi ảnh gắn với một dòng của báo cáo. Thu về bề ngang 1200 px. Xem lại
  từng ảnh: không có mã 6 số, không có mã QR, không có người trong khung hình camera.
- [ ] **Step 2:** Gọi Artifact `quickstart` và nạp kỹ năng `artifact-design` trước khi viết trang. Dựng trang
  theo đúng thứ tự của file báo cáo: mục 1, mục 2, rồi từng trang. Xuất bản riêng tư.
- [ ] **Step 3: Kiểm lần cuối.** Gộp `blocked` của mọi lần chạy: chỉ được có dòng `__review_block_test`, hoặc
  các dòng đã ghi chú ở Task 2 và 3. Đọc lại `GET /settings` và `GET` shelf plan bằng tài khoản `admin`:
  preferences và `updated_at` của shelf plan giống lần đọc đầu tiên trong `$SP\shots\team\`.
- [ ] **Step 4:** Commit ba file chữ lên nhánh mới, không push:

```bash
git switch -c docs/website-feature-review
git add docs/superpowers/specs/2026-11-26-website-feature-review-design.md \
        docs/superpowers/plans/2026-11-26-website-feature-review.md \
        docs/reviews/2026-11-26-website-feature-review.md
git -c user.name="Nguyen Huy Hoang" \
    -c user.email="193206418+Protein-17012006@users.noreply.github.com" \
    commit -m "Docs: website feature review (design, plan, findings)" \
           -m "Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>"
```

- [ ] **Step 5:** Gửi hoang đường dẫn trang báo cáo và ba thay đổi đứng đầu. Mọi thay đổi trên website là
  việc mới, chờ hoang duyệt từng mục.
