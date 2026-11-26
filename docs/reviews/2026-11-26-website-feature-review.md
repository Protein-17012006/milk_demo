# Đánh giá tính năng website (26/11/2026)

Lúc xem: 26/11/2026 từ 20:13 đến 20:40 (UTC+7). Tiệm đã cất kệ từ 15:45 vì mưa nên camera không thấy kệ; mọi số "hiện tại" trong báo cáo là của lần kiểm 15:45.

Cách làm: đi bản đang chạy bằng hai tài khoản thử, một của nhóm `datagent` (người thường) và một của nhóm
`team_admin` (team vận hành), thử từng nút và chụp ảnh. Không lưu gì lên dữ liệu thật: script chặn mọi lệnh ghi
và không lệnh ghi nào được gửi đi. Nhóm `field_team` không có tài khoản thử nên phần khác biệt đọc từ mã nguồn.
Thiết kế: `docs/superpowers/specs/2026-11-26-website-feature-review-design.md`.

**Bốn mức xếp loại:** `giữ` (để nguyên), `sửa` (giữ nhưng làm gọn hoặc dễ hiểu hơn), `chuyển chỗ` (đúng việc
nhưng đang hiện sai nơi hoặc sai người), `bỏ` (không giúp việc nào của ai).

## Tóm tắt

- **78 tính năng đã xem:** 25 giữ, 31 sửa, 10 chuyển chỗ, 12 bỏ.
- **Website đang phục vụ team tốt hơn người thường.** Trang Model, hàng chờ duyệt và shelf plan đủ dùng và giải
  thích rõ. Còn người thường thì đăng nhập xong bị đưa vào Category, Dashboard không có số từng sản phẩm, và ba
  trong sáu thẻ số là số của team.
- **Một tính năng đang hỏng:** nút "Export CV Output" trả lỗi 502 mỗi lần bấm.
- **Trên điện thoại Dashboard gần như không dùng được:** thanh bên mở sẵn chiếm hơn nửa màn hình.
- **Khoảng mười thứ không có tác dụng** (nút giả, ô tích không dùng tới, danh sách "gần đây" cố định) làm website
  trông nhiều việc hơn thực tế.
- **Việc của team hiện ra với người thường:** hàng chờ duyệt, form sửa kết quả và nút Import nằm ngay đầu trang
  Category của một tài khoản không được phép dùng chúng.

## 1. Thay đổi đáng làm nhất

Xếp theo lợi ích so với công làm. Công làm: `nhỏ` (chỉ đổi chữ hoặc ẩn hiện), `vừa` (một component, không đụng
backend), `lớn` (cần backend hoặc API mới).

### 1. Sửa nút "Export CV Output" đang hỏng

**Đổi gì:** nút ở Category trả 502 sau 21 giây. Theo mã nguồn, giao diện thử lại hai lần rồi mới báo lỗi, tức khoảng
65 giây không có dấu hiệu gì. Log của Lambda ghi "Exceeded maximum allowed payload size (6291556 bytes)": file CSV đã lớn
hơn mức 6 MB mà Lambda được trả về. Nút "Download" ở Dashboard còn chạy (14,6 giây, 1,15 MB, 9.819 dòng) nhưng
sẽ gặp cùng giới hạn khi dữ liệu nhiều lên. Cách sửa: giới hạn theo khoảng ngày, hoặc ghi file ra S3 rồi trả
đường dẫn tải.
**Cho ai:** team và Datagent (đây là file CV Output 16 cột Datagent yêu cầu).
**Vì sao:** một nút nổi bật mà bấm lần nào cũng hỏng làm mất lòng tin vào cả trang.
**Công làm:** `lớn`
**File:** `backend/api/handler.py` (`_handle_export_csv`), `frontend/components/category/CategoryProductsView.tsx`,
`frontend/components/reports/ReportsDashboard.tsx`
**Dẫn tới:** Category › Export CV Output; Dashboard › Download.

### 2. Đăng nhập xong vào thẳng Dashboard

**Đổi gì:** hiện mọi tài khoản đều bị đưa vào `/category` sau khi đăng nhập. Đổi thành Dashboard cho người
thường. Khi đó "Default Landing Page" trong Settings hoặc được nối cho có tác dụng, hoặc gỡ đi.
**Cho ai:** người thường.
**Vì sao:** bạn nói người thường "chỉ cần nhìn Dashboard là xong", nhưng thứ đầu tiên họ thấy lại là nút Import
và hàng chờ duyệt.
**Công làm:** `nhỏ`
**File:** `frontend/components/auth/LoginView.tsx` (bốn chỗ `router.push("/category")`),
`frontend/components/settings/SettingsView.tsx`
**Dẫn tới:** Đăng nhập › Trang đến sau khi đăng nhập; Settings › Default Landing Page; Home › Cả trang Home.

### 3. Dashboard: thêm bảng "từng sản phẩm còn bao nhiêu" và số "đang hết hàng"

**Đổi gì:** thay biểu đồ "Shelf Stock Count" (trùng số với Trends) bằng một bảng ngắn: tên sản phẩm, số hộp lúc
này, hết hay sắp hết. Thêm thẻ "Hết hàng lúc này". Cả hai số API đã trả sẵn (`/products` có `unit_count`, `/kpi`
có `oos_now`) nhưng Dashboard chưa hiện. Đổi một lệnh gọi lấy một lệnh gọi nên không tăng tải lên giới hạn 10
Lambda.
**Cho ai:** người thường.
**Vì sao:** hai câu hỏi chính của họ là "mỗi sản phẩm còn bao nhiêu" và "món nào hết"; hiện Dashboard chỉ có một
tổng chung (13) và phải sang Category, mở từng nhóm mới thấy.
**Công làm:** `vừa`
**File:** `frontend/components/reports/ReportsDashboard.tsx`, `frontend/components/reports/KpiGrid.tsx`,
`frontend/components/reports/MonthlyStockChart.tsx` (gỡ), `frontend/lib/reports-ui.ts`
**Dẫn tới:** Dashboard › Shelf Stock Count, Total On-Shelf Units; mục 2 › hai dòng đầu.

### 4. Dọn sáu thẻ số của Dashboard

**Đổi gì:** gỡ "Avg. Inference Time"; chuyển "Active Stores Monitored" và "Top 50 SKU Accuracy" về trang Model
(Model đã có sẵn "Processing time" và "SKU identification"). "Restock Rate" lấy "5.6 units/day" làm số chính thay cho dấu "—". "OSA" gọn
còn một dòng chữ. Dòng dưới tiêu đề đổi thành "Cập nhật lúc 15:45". Sáu thẻ này cũng là phần đến chậm nhất của
trang: biểu đồ có số sau 0,5 giây, còn sáu thẻ sau khoảng 3 giây.
**Cho ai:** người thường.
**Vì sao:** ba trong sáu thẻ không nói gì về hàng trên kệ, và một thẻ đang để "—" dù có số thật.
**Công làm:** `vừa`
**File:** `frontend/components/reports/KpiGrid.tsx`, `frontend/lib/reports-ui.ts`, `frontend/lib/shelf-ui.ts`,
`frontend/components/model/ModelQualityView.tsx`
**Dẫn tới:** Dashboard › sáu dòng thẻ số và dòng dưới tiêu đề.

### 5. Điện thoại: thanh bên tự thu gọn

**Đổi gì:** ở màn hình hẹp thanh bên bắt đầu ở trạng thái thu gọn (56 px thay vì 216 px).
**Cho ai:** người thường.
**Vì sao:** ở bề ngang 390 px thanh bên chiếm 216 px, Dashboard còn một cột khoảng 170 px: chữ bộ lọc bị cắt
("Timefram…"), nút Download bị che.
**Công làm:** `nhỏ`
**File:** `frontend/components/layout/Sidebar.tsx`
**Dẫn tới:** Thanh bên › Thu gọn thanh bên; Dashboard › Dashboard trên điện thoại.

### 6. Category: việc của team chỉ hiện cho team

**Đổi gì:** dải báo "9 readings are waiting for a check", nút "Confirm AI" và "Correct", form "Human Audit &
Correction" với nút "Save Correction" chỉ hiện cho `field_team` và `team_admin`. Nút "Import SKU Master" chuyển
sang Settings, cạnh "Import Store List". Quyền ở backend đã đúng; đây chỉ là phần hiển thị.
**Cho ai:** người thường (trang gọn hơn), team (không đổi gì).
**Vì sao:** người thường thấy bốn thứ bấm được nhưng bấm xong mới biết mình không có quyền; nút cam nổi nhất
trang là một việc cài đặt hiếm khi làm.
**Công làm:** `nhỏ`
**File:** `frontend/components/category/CategoryProductsView.tsx`, `frontend/components/category/ReviewQueue.tsx`,
`frontend/components/category/ProductDetailsModal.tsx`, `frontend/components/settings/SettingsView.tsx`
**Dẫn tới:** Category › Hàng chờ duyệt, Human Audit & Correction, Import SKU Master.

### 7. Thẻ sản phẩm: ảnh có khoanh hộp lên đầu

**Đổi gì:** mở thẻ là thấy ngay ảnh kệ đã phóng vào sản phẩm với các hộp được khoanh số (hiện nằm sau nút "View
frame" ở cuối thẻ). Phần kỹ thuật (toạ độ hộp, S3 key, Capture ID) gập lại, mặc định đóng. Ảnh "Photos" của sự
kiện trên Dashboard dùng cùng cách phóng và khoanh.
**Cho ai:** người thường (tin được con số), team (kiểm nhanh hơn).
**Vì sao:** ảnh có khoanh hộp là bằng chứng dễ hiểu nhất cho câu "con số tin được tới đâu", nhưng đang cách bốn
lần bấm.
**Công làm:** `vừa`
**File:** `frontend/components/category/ProductDetailsModal.tsx`, `frontend/components/category/FrameViewer.tsx`,
`frontend/components/reports/RecentActivitiesCard.tsx`
**Dẫn tới:** Category › Thẻ sản phẩm, View frame; Dashboard › Photos.

### 8. Trang Model: gán nhãn nhanh hơn, trạng thái chạy lên đầu

**Đổi gì:** thêm nút "các hộp còn lại đều đúng" và phím tắt (1 đến 4 cho bốn lựa chọn, Enter để lưu). Đưa một
dòng "camera và worker: ảnh gần nhất lúc …" lên đầu trang. Thêm chú giải cho hai đường của biểu đồ "By day".
**Cho ai:** team.
**Vì sao:** một khung hình 15 hộp cần ít nhất 17 lần bấm, và đang có 13 khung chờ cộng 42 khung cần gán lại.
Câu "camera và worker có chạy không" hiện nằm ở tab cuối cùng của khối cuối trang.
**Công làm:** `vừa`
**File:** `frontend/components/model/AuditLabeler.tsx`, `frontend/lib/audit-labeling.ts`,
`frontend/components/model/ModelQualityView.tsx`, `frontend/components/model/LiveHealth.tsx`
**Dẫn tới:** Model › Label frames, Live health, By day.

### 9. Gỡ những thứ không có tác dụng

**Đổi gì:** gỡ nút Google và SSO, ô "Remember this device", nút chọn ngôn ngữ, bốn liên kết chân trang; hai cột
"Recents" ở Home; ô chọn (checkbox) và menu "..." ở Category; ô "Quick search…" ở thanh bên; "Date Format" ở
Settings.
**Cho ai:** cả người thường lẫn team.
**Vì sao:** mỗi thứ này trông như bấm được nhưng không làm gì, nên người dùng mất công thử rồi mất lòng tin vào
các nút thật.
**Công làm:** `nhỏ`
**File:** `frontend/components/auth/LoginView.tsx`, `RegisterView.tsx`, `AuthShell.tsx`;
`frontend/components/home/HomePageView.tsx`, `frontend/lib/home-ui.ts`;
`frontend/components/category/CategoryProductsView.tsx`, `ProductRow.tsx`, `ProductGroupRow.tsx`;
`frontend/components/layout/Sidebar.tsx`; `frontend/components/settings/SettingsView.tsx`
**Dẫn tới:** mọi dòng xếp loại `bỏ` ở mục 3.

### 10. Viết lại chữ kỹ thuật bằng chữ thường

**Đổi gì:** "Live AWS data, 9809 captures synced", "Connected to live AWS Singapore backend", "Synced with AWS
Cognito & DynamoDB", "0.70 (MILK_FLAG_THRESHOLD)", "`403 PENDING_ROLE_ASSIGNMENT`", "Waiting (Chờ duyệt)",
"Pending SKU Master", "Not enough samples (n = 0)". Sửa luôn các tên cũ còn sót: "View in Reports", lựa chọn
"Reports" và "Products", câu "review queue on Products".
**Cho ai:** người thường là chính; team đọc cũng nhanh hơn.
**Vì sao:** người thường không biết Cognito hay DynamoDB là gì, và tên trang cũ làm họ tìm một trang không tồn tại.
**Công làm:** `nhỏ`
**File:** `frontend/components/reports/ReportsDashboard.tsx`, `frontend/components/home/HomePageView.tsx`,
`frontend/components/settings/SettingsView.tsx`, `frontend/components/layout/DashboardShell.tsx`,
`frontend/components/category/ReviewQueue.tsx`, `frontend/lib/shelf-ui.ts`, `frontend/lib/health-ui.ts`
**Dẫn tới:** các dòng xếp loại `sửa` có ghi "chữ kỹ thuật" ở mục 3.

## 2. Còn thiếu

Mỗi thứ gắn với một việc của người dùng trong bản thiết kế.

| Còn thiếu | Việc của ai | Hiện giờ |
|---|---|---|
| Số hộp của từng sản phẩm ngay trên Dashboard | Người thường: "mỗi sản phẩm còn bao nhiêu" | Chỉ có ở Category, sau khi mở từng nhóm. API đã có số. |
| Danh sách "đang hết" và "sắp hết" lúc này | Người thường: "món nào hết hoặc sắp hết" | Chỉ có nhật ký sự kiện đã xảy ra. API đã trả số đang hết nhưng chưa trang nào hiện. |
| Giờ cập nhật gần nhất, nói bằng chữ thường | Người thường: "con số mới tới lúc nào" | Chỉ hiện khi camera mất kệ. Lúc bình thường không có dòng nào nói giờ. |
| Một ảnh kệ mới nhất có khoanh hộp trên Dashboard | Người thường: "xem ảnh để tự kiểm" | Phải sang Category, mở nhóm, mở thẻ, kéo xuống, bấm "View frame". |
| Một dòng "camera và worker đang chạy hay ngừng" | Team: "biết camera và worker có chạy không" | Phải vào Model, kéo xuống cuối, chọn tab "Captures per hour". |
| Số việc đang chờ ở một chỗ | Team: sửa lần đọc chưa chắc, gán nhãn | 9 lần đọc chờ ở Category, 13 khung chờ ở Model, sự kiện chờ xác nhận ở Dashboard: ba trang khác nhau. |
| Hướng dẫn cho người vừa đăng ký | Người thường mới | Dải báo chỉ ghi mã lỗi, không nói ai duyệt và phải làm gì. |

Chưa rõ, cần bạn quyết: toàn bộ website bằng tiếng Anh. Nếu người thường là người Việt thì giao diện tiếng Việt
cũng là một thứ còn thiếu.

## 3. Theo từng trang

Cột "Nhận xét" ghi ba ý theo thứ tự: dễ thấy và dễ hiểu; có tác dụng thật; hiện cho đúng nhóm. Cột "Ảnh" là tên
file trong thư mục ảnh của đợt đánh giá.

### Đăng nhập và đăng ký

| Tính năng | Cho người thường | Cho team vận hành | Nhận xét | Xếp loại | Đề xuất | Ảnh |
|---|---|---|---|---|---|---|
| Form đăng nhập (email, mật khẩu) | Vào được website; trên điện thoại hiển thị tốt | Như người thường | Rõ. Có tác dụng. Đúng nhóm. | giữ | Không đổi | viewer/00-login.png, viewer/00-login-phone.png |
| Trang đến sau khi đăng nhập | Bị đưa vào Category, phải tự bấm sang Dashboard | Vào Category, hợp với việc duyệt | Người thường thấy ngay nút Import và hàng chờ duyệt. Luôn là `/category`, không theo Default Landing Page. Sai với người thường. | sửa | Người thường vào Dashboard | viewer/30-category.png |
| Bước nhập mã 6 số | Bắt buộc, một ô nhập | Như người thường | Hai dòng hướng dẫn nói cùng một ý, có chữ "TOTP". Có tác dụng. Đúng nhóm. | giữ | Bỏ bớt một dòng hướng dẫn | viewer/02-login-mfa-step.png |
| Continue with Google, Continue with SSO, Sign up with Google, Sign up with SSO | Bấm chỉ hiện dòng báo chưa bật | Như người thường | Đứng trên form thật nên dễ bấm nhầm. Không có tác dụng. Không giúp việc nào của ai. | bỏ | Gỡ bốn nút ở hai trang | viewer/00-login.png, viewer/01-register.png |
| Remember this device | Tích hay không cũng như nhau | Như người thường | Rõ. Không có tác dụng: giá trị ô tích không được dùng (theo mã nguồn). Không giúp việc nào của ai. | bỏ | Gỡ ô tích | viewer/00-login.png |
| Forgot your password? | Tự đặt lại mật khẩu | Như người thường | Rõ. Có luồng trong mã nguồn; không thử vì là lệnh đổi tài khoản. Đúng nhóm. | giữ | Không đổi | viewer/00-login.png |
| Nút chọn ngôn ngữ "English" | Chỉ đổi chữ trên nút | Như người thường | Gợi ý rằng có bản dịch. Không có tác dụng: website không dịch. Không giúp việc nào của ai. | bỏ | Gỡ cho tới khi có bản dịch thật | viewer/00-login.png |
| Bốn liên kết chân trang (Support, System Status, Terms of Use, Privacy Policy) | Support về Home, System Status về Dashboard, hai cái còn lại không làm gì | Như người thường | Trông như liên kết thật. Không có tác dụng. Không giúp việc nào của ai. | bỏ | Gỡ, hoặc giữ một địa chỉ liên hệ thật | viewer/00-login.png |
| Trang Register | Tự tạo tài khoản rồi chờ duyệt | Không dùng | Dòng "Pending Role Assignment … `team_admin` grants group permissions" là chữ kỹ thuật. Không thử gửi form. Đúng nhóm (trang này được chọn giữ lại ngày 21/11). | sửa | Viết lại: "Tài khoản mới cần quản trị viên duyệt trước khi xem được số liệu" | viewer/01-register.png |
| Dải báo "chờ duyệt" sau khi đăng ký | Biết mình chưa được duyệt | Không dùng | Có chữ `403 PENDING_ROLE_ASSIGNMENT`, không nói phải làm gì tiếp (đọc từ mã nguồn, không tạo tài khoản để xem). Có tác dụng. Đúng nhóm. | sửa | Viết lại bằng chữ thường, nói ai duyệt | viewer/01-register.png |
| Xem website khi chưa đăng nhập (Back to Workspace) | Thấy bốn trang rỗng và một dải xám nhắc đăng nhập | Như người thường | Trang rỗng dễ bị tưởng là website hỏng (đọc từ mã nguồn, không mở các trang này khi chưa đăng nhập). Không có số nào. Không ai cần xem trang rỗng. | sửa | Chưa đăng nhập thì đưa thẳng về trang đăng nhập | viewer/00-login.png |

### Thanh bên

| Tính năng | Cho người thường | Cho team vận hành | Nhận xét | Xếp loại | Đề xuất | Ảnh |
|---|---|---|---|---|---|---|
| Điều hướng (Home, Dashboard, Category, Model, Settings) | Bốn mục, không thấy Model | Năm mục | Rõ. Có tác dụng. Đúng nhóm: gõ thẳng `/model/` thì người thường chỉ thấy dòng báo, API trả 403. | giữ | Không đổi | viewer/10-home.png, viewer/60-model-direct.png |
| Thu gọn thanh bên | Trên điện thoại thanh bên mở sẵn, chiếm 216 trong 390 px | Dùng trên máy tính | Nút nhỏ ở góc dưới. Có tác dụng. Đúng nhóm. | sửa | Tự thu gọn khi màn hình hẹp | viewer/05-sidebar-collapsed.png, viewer/25-dashboard-phone-top.png |
| Ô "Quick search…" | Chỉ lọc danh sách ở Category; ở Home gõ rồi nhấn Enter không có gì xảy ra | Như người thường | Hiện ở mọi trang. Chỉ có tác dụng ở Category, nơi đã có ô tìm riêng. Không giúp thêm việc nào của ai. | bỏ | Gỡ; giữ ô tìm của Category | viewer/05-sidebar-search-on-home.png, viewer/30-category-sidebar-search.png |
| Menu tài khoản (email, nhóm, Sign out) | Biết mình đăng nhập bằng tài khoản nào, thoát ra | Như người thường | Tên nhóm `datagent` là chữ kỹ thuật nhưng ngắn. Có tác dụng. Đúng nhóm. | giữ | Không đổi | viewer/05-sidebar-account-menu.png |

### Home

| Tính năng | Cho người thường | Cho team vận hành | Nhận xét | Xếp loại | Đề xuất | Ảnh |
|---|---|---|---|---|---|---|
| Cả trang Home | Không có số hàng nào; là một bước đi vòng | Không dùng cho việc nào | Gọn, đẹp. Không trả lời câu hỏi nào về kệ. Không nhóm nào cần một trang riêng như vậy. | chuyển chỗ | Lấy Dashboard làm trang đầu; phần tìm sản phẩm chuyển sang Category | viewer/10-home.png |
| Lời chào và dòng trạng thái | "Let's get back to work api-check!" và "Connected to live AWS Singapore backend · 15 SKUs synced" | Như người thường | Dòng trạng thái là chữ kỹ thuật. Không cho biết số mới tới lúc nào. Đúng nhóm. | sửa | Thay bằng giờ cập nhật gần nhất | viewer/10-home.png |
| Ô tìm lớn (Ctrl K): sản phẩm và trang | Gõ tên là thấy còn mấy hộp | Ít dùng | Rõ, có phím tắt. Có tác dụng. Đúng nhóm; nhưng với 15 sản phẩm thì một danh sách hiện hết còn nhanh hơn. | chuyển chỗ | Đặt ở đầu Category | viewer/11-home-search-open.png, viewer/12-home-search-slide.png |
| "See all N results" | Sang Category nhưng mất từ đã gõ | Như người thường | Rõ. Sai: ô tìm bên Category trống. Đúng nhóm. | sửa | Mang từ khoá sang Category | viewer/17-home-see-all-landing.png |
| Hộp xem nhanh sản phẩm | Thấy số hộp của một sản phẩm | Ít dùng | Nút "View in Reports" dùng tên trang cũ. Nút dẫn tới Dashboard chung chứ không phải sản phẩm đó; "Store Presence 1/1" không nói gì. Đúng nhóm. | sửa | Nút mở thẻ của chính sản phẩm đó | viewer/13-home-quick-preview.png |
| Recents bên trái (trang) | Bốn liên kết giống thanh bên | Như người thường | Tên là "Recents" nhưng là danh sách cố định. Nút "..." không làm gì. Không giúp việc nào của ai. | bỏ | Gỡ | viewer/10-home.png, viewer/14-home-dots-left.png |
| Recents bên phải (sản phẩm vừa mở) | Mở lại sản phẩm vừa xem | Như người thường | Cùng tên với cột trái. Mất sạch khi rời trang; nút "..." xoá danh sách mà không hỏi (theo mã nguồn). Không giúp việc nào của ai. | bỏ | Gỡ | viewer/14-home-recents-after-open.png, viewer/15-home-recents-after-return.png |

### Dashboard

| Tính năng | Cho người thường | Cho team vận hành | Nhận xét | Xếp loại | Đề xuất | Ảnh |
|---|---|---|---|---|---|---|
| Dòng dưới tiêu đề ("Live AWS data, 9809 captures synced…") | Không biết số mới tới lúc nào | Biết hệ thống đang nhận ảnh | Chữ kỹ thuật. Có tác dụng với team. Sai với người thường. | sửa | "Cập nhật lúc 15:45"; số capture về Model | viewer/20-dashboard-top.png |
| Bộ lọc Timeframe | Đổi khoảng ngày cho các thẻ và Trends | Như người thường | "one cycle" không được giải thích. Có tác dụng; 14 và 90 ngày đang cho cùng số vì dữ liệu mới có từ 22/11 (do thời điểm, không phải lỗi). Đúng nhóm. | giữ | Thêm một dòng giải thích "cycle" | viewer/24-dashboard-dropdown-0.png, viewer/24-dashboard-tf0.png, viewer/24-dashboard-tf3.png |
| Bộ lọc Store | Chỉ có một tiệm nên không lọc được gì | Như người thường | Rõ. Sẽ có tác dụng khi nhiều tiệm. Đúng nhóm. | sửa | Ẩn khi chỉ có một tiệm | viewer/24-dashboard-dropdown-1.png |
| Bộ lọc Category | Xem riêng Milk hoặc Snacks | Như người thường | Rõ. Có tác dụng. Đúng nhóm. | giữ | Không đổi | viewer/24-dashboard-dropdown-2.png, viewer/24-dashboard-category-picked.png |
| Download | Chờ 14,6 giây không có dấu hiệu gì, rồi nhận file 9.819 dòng nhật ký ảnh chụp | Dùng để đối chiếu từng lần chụp | Người thường tưởng tải số trên màn hình. Có tác dụng nhưng chậm; khi lỗi thì lặng lẽ tải một file tóm tắt khác (theo mã nguồn). File này là của team. | sửa | Đổi tên thành "Download capture log", hiện trạng thái đang tải | team3/27-export-capture-log-1500ms.png |
| Dòng báo camera không thấy kệ | Biết số đang xem là của lần kiểm 15:45 | Như người thường | Rõ, hiện đúng lúc. Có tác dụng. Đúng nhóm. | giữ | Không đổi | viewer/20-dashboard-top.png |
| Active Stores Monitored | "1/1" không nói gì về hàng | Biết camera còn gửi ảnh | Rõ. Có tác dụng. Là việc giám sát của team. | chuyển chỗ | Về trang Model, cạnh Live health | viewer/20-dashboard-top.png |
| Total On-Shelf Units (now) | Tổng số hộp trên kệ: 13 | Như người thường | Rõ. Có tác dụng. Đúng nhóm; nhưng không tách theo sản phẩm. | giữ | Kèm giờ của lần kiểm; đặt cạnh bảng từng sản phẩm | viewer/20-dashboard-top.png |
| Avg. Inference Time | "76 ms" không liên quan tới hàng trên kệ | Đã có ở Model (Processing time, ms per frame) | Rõ. Có tác dụng. Không giúp việc nào của người thường, team đã có số này ở Model. | bỏ | Gỡ khỏi Dashboard | viewer/20-dashboard-top.png |
| On-Shelf Availability (OSA) | Tỉ lệ thời gian có hàng: 76,9% | Như người thường | Tên viết tắt, ba đoạn chữ nhỏ dưới con số. Có tác dụng. Đúng nhóm. | sửa | Giữ con số, gọn còn một dòng | viewer/20-dashboard-top.png |
| Top 50 SKU Accuracy | Khó đọc: "From 42 frames the team labelled" | Đã có ở Model (SKU identification) | Khó hiểu với người thường. Có tác dụng. Là số của team. | chuyển chỗ | Về Model; Dashboard chỉ cần một dòng độ tin cậy bằng chữ | viewer/20-dashboard-top.png |
| Restock Rate (vs Last Cycle) | Số chính là "—", còn "5.6 units/day" nằm ở dòng phụ | Như người thường | Dễ tưởng là không có số. "—" là do chưa có kỳ trước để so (do thời điểm), nhưng số thật vẫn có. Đúng nhóm. | sửa | Lấy units/day làm số chính | viewer/20-dashboard-top.png |
| Shelf Stock Count | Cột theo ngày, trùng số với Trends | Như người thường | Rõ. Cùng năm con số với "Total Stock Units" của Trends và không theo bộ lọc Timeframe. Không giúp thêm việc nào của ai. | bỏ | Thay bằng bảng từng sản phẩm còn bao nhiêu | viewer/21-dashboard-stock-chart.png |
| Trends & Insights (Total Stock Units, Out-of-Stock, Restock Volume) | Xem hàng nhiều lên hay ít đi theo ngày | Như người thường | Rõ, mỗi chỉ số có một dòng giải thích. Có tác dụng. Đúng nhóm. | giữ | Không đổi | viewer/22-dashboard-trends.png, viewer/22-dashboard-trends-1.png, viewer/22-dashboard-trends-3.png |
| Trends & Insights: Detection Accuracy | Không dùng | Đã có ở Model (By day) | Rõ. Có tác dụng. Là số của team. | chuyển chỗ | Về Model | viewer/22-dashboard-trends-2.png |
| Recent Shelf Activities (danh sách) | Biết món nào vừa hết, sắp hết, vừa được bổ sung | Như người thường | Nhãn "Reliability: Low", chữ đỏ "uncertain" và dòng "Not enough samples (n = 0)" khó hiểu. Có tác dụng; 13 trong 20 sự kiện gần nhất là LOW STOCK, nhiều dòng lặp lại cùng một sản phẩm. Đúng nhóm. | sửa | Gộp sự kiện lặp của cùng một sản phẩm; nhãn độ tin cậy nói bằng chữ thường | viewer/23-dashboard-activities.png |
| Lọc All / Alerts Only / Restocked | Xem riêng cảnh báo hoặc lần bổ sung | Như người thường | Rõ. Có tác dụng. Đúng nhóm. | giữ | Không đổi | viewer/23-dashboard-activities-0.png, viewer/23-dashboard-activities-1.png |
| Photos (Before / At the event) | Tự kiểm sự kiện bằng mắt | Như người thường | Hai ảnh nhỏ chụp cả sạp, không khoanh sản phẩm, không phóng to được. Có ảnh nhưng khó thấy khác biệt. Đúng nhóm. | sửa | Phóng vào sản phẩm và khoanh hộp như "View frame" | viewer/23-dashboard-event-photos.png |
| Right / Wrong / Unsure | Không thấy (ẩn đúng) | Xác nhận sự kiện đúng hay sai | Rõ. Có tác dụng nhưng chưa ai xác nhận lần nào (n = 0). Đúng nhóm; đây là chỗ kiểm tay thứ ba, bên cạnh hàng chờ duyệt và gán nhãn. | chuyển chỗ | Gom việc kiểm tay của team về một nơi | team/23-dashboard-activities.png |
| View all activity | Xem 20 sự kiện gần nhất và tải thêm | Như người thường | Rõ. Có tác dụng. Đúng nhóm. | giữ | Không đổi | viewer/23-dashboard-all-activity.png |
| Dashboard trên điện thoại | Thanh bên chiếm hơn nửa màn hình, chữ bộ lọc bị cắt, nút Download bị che | Ít dùng | Khó đọc. Vẫn chạy, không phải cuộn ngang. Đúng nhóm. | sửa | Thanh bên tự thu gọn (xem thay đổi 5) | viewer/25-dashboard-phone-top.png, viewer/25-dashboard-phone-full.png |

### Category

| Tính năng | Cho người thường | Cho team vận hành | Nhận xét | Xếp loại | Đề xuất | Ảnh |
|---|---|---|---|---|---|---|
| Danh sách sản phẩm theo nhóm | Nơi duy nhất thấy từng sản phẩm còn mấy hộp | Như người thường | Nhóm đóng sẵn, phải bấm "Expand all" mới thấy từng sản phẩm. Có tác dụng. Đúng nhóm; 10 dòng Vinamilk không nằm trong shelf plan của tiệm luôn là 0. | sửa | Mở sẵn; sản phẩm ngoài shelf plan gom xuống cuối hoặc ẩn | viewer/30-category.png, viewer/31-category-expanded.png |
| Ô tìm của trang | Tìm theo tên | Tìm theo tên hoặc mã | Rõ. Có tác dụng. Đúng nhóm. | giữ | Không đổi | viewer/32-category-search-TH.png |
| Lọc Store và cột AVAIL IN STORES | "1/1 stores" ở mọi dòng, không nói gì | Như người thường | Rõ. Sẽ có tác dụng khi nhiều tiệm. Đúng nhóm. | sửa | Ẩn khi chỉ có một tiệm | viewer/33-category-dropdown-0.png |
| Lọc Category | Xem riêng Milk hoặc Snacks | Như người thường | Rõ. Có tác dụng. Đúng nhóm. | giữ | Không đổi | viewer/33-category-dropdown-1.png |
| Lọc Status (Validated / Needs Review / Low Confidence) | Không biết các từ này nghĩa là gì | Lọc ra dòng cần xem lại | "Validated" được gán cho mọi dòng không bị gắn cờ, kể cả khi chưa ai kiểm (theo mã nguồn). Có tác dụng. Là việc của team. | sửa | Đổi "Validated" thành "Not flagged"; chỉ hiện cho team | viewer/33-category-dropdown-2.png |
| Sort | Xếp theo số hộp hoặc tên | Thêm xếp theo confidence | Rõ. Có tác dụng. Đúng nhóm. | giữ | Không đổi | viewer/33-category-dropdown-3.png |
| Ô chọn (checkbox) ở từng dòng và ô chọn tất cả | Tích xong không có gì xảy ra | Như người thường | Trông như chuẩn bị cho thao tác hàng loạt. Không có tác dụng: không hành động nào dùng tới lựa chọn (theo mã nguồn). Không giúp việc nào của ai. | bỏ | Gỡ cột ô chọn | viewer/34-category-selected.png |
| Cột SKU CODE | Thấy mã của model ("sourcream150") và chữ "Pending SKU Master" | Biết mã model của sản phẩm | Chữ kỹ thuật; "Pending SKU Master" thật ra là barcode chưa có. Có tác dụng với team. Sai với người thường. | sửa | Người thường không cần cột này; với team ghi "Chưa có barcode" | viewer/31-category-expanded.png |
| Cột CONFIDENCE, nhãn Reliability, nhãn "N flagged" | Ba dấu hiệu về độ tin cậy trên cùng một dòng, có khi ngược nhau (96% nhưng "Reliability: Low") | Hiểu được từng cái | Khó biết tin cái nào. Có tác dụng. Đúng với team, quá nhiều với người thường. | sửa | Người thường thấy một nhãn duy nhất; ba số chi tiết để cho team | viewer/35-category-reliability.png, viewer/31-category-expanded.png |
| Menu "..." của từng dòng (View Validation Details, Copy SKU Code, Export Row CSV) | Không dùng | Mục đầu trùng nút View | Ẩn sau dấu ba chấm. Có tác dụng. Không giúp thêm việc nào của ai: mục đầu trùng nút View, hai mục sau không thuộc việc nào đã nêu. | bỏ | Gỡ, trừ khi Datagent cần xuất từng dòng | viewer/35-category-more-actions.png |
| Thẻ sản phẩm (Validation Card Details) | Thấy số hộp; phần còn lại là toạ độ hộp, S3 key, "FALSE · No flag" | Đủ thông tin để kiểm một lần đọc | Tên và nội dung kỹ thuật; ảnh nằm cuối thẻ. Có tác dụng. Hợp với team hơn. | sửa | Ảnh có khoanh hộp lên đầu; phần kỹ thuật gập lại (xem thay đổi 7) | viewer/36-category-card.png, viewer/36-category-card-bottom.png |
| Human Audit & Correction, Save Correction | Thấy form và nút, bấm lưu mới biết không có quyền | Sửa một lần đọc sai | Rõ với team. Có tác dụng. Hiện sai nhóm. | sửa | Chỉ hiện cho `field_team` và `team_admin` | viewer/36-category-card.png, team/35-review-queue-correct-form.png |
| View frame (ảnh có khoanh hộp, Full frame / Zoom to boxes) | Bằng chứng dễ hiểu nhất cho con số | Kiểm nhanh model đếm đúng không | Rất rõ, có che người lọt vào khung. Có tác dụng. Đúng nhóm; nhưng nằm cuối thẻ. | giữ | Đưa lên đầu thẻ | viewer/37-category-frame.png |
| Hàng chờ duyệt (dải báo, Review queue, Confirm AI, Correct) | Dải cam chiếm đầu trang; nút bấm được nhưng báo không có quyền | Luồng rõ: xem khung hình, xác nhận hoặc sửa, mục được gạch khỏi hàng chờ | Chữ "Waiting (Chờ duyệt)" lẫn hai thứ tiếng. Có tác dụng với team. Hiện sai nhóm. | chuyển chỗ | Chỉ hiện cho team | viewer/38-category-review-queue.png, team/35-review-queue.png, team/35-review-queue-correct-card.png |
| Export CV Output | Không dùng | Cần để gửi Datagent, nhưng đang hỏng | Nút rõ. Không có tác dụng: 502 sau 21 giây mỗi lần thử. Là việc của team. | sửa | Sửa lỗi (xem thay đổi 1) | team3/28-export-cv-output-after.png |
| Import SKU Master | Nút cam nổi nhất trang, không dùng được | Việc cài đặt, hiếm khi làm | Rõ. Không thử gửi file. Hiện sai nhóm và sai chỗ. | chuyển chỗ | Sang Settings, cạnh Import Store List | viewer/39-category-import-dialog.png |
| Dòng báo camera không thấy kệ | Biết số đang xem là của lần kiểm 15:45 | Như người thường | Rõ. Có tác dụng. Đúng nhóm. | giữ | Không đổi | viewer/30-category.png |

### Model

| Tính năng | Cho người thường | Cho team vận hành | Nhận xét | Xếp loại | Đề xuất | Ảnh |
|---|---|---|---|---|---|---|
| Trang Model với người thường | Không thấy trong thanh bên; gõ thẳng địa chỉ chỉ thấy một dòng báo | Không liên quan | Rõ. API cũng từ chối (403). Đúng nhóm. | giữ | Không đổi | viewer/60-model-direct.png |
| Chọn phiên bản model và khoảng ngày | Không thấy | Xem điểm theo phiên bản và theo 7 ngày, 30 ngày, tất cả | Một lựa chọn phiên bản tên "unknown". Có tác dụng. Đúng nhóm. | giữ | Đổi "unknown" thành "Trước khi ghi phiên bản" | team/42-model-range-30.png, team/42-model-version.png |
| Label frames (gán nhãn khung hình) | Không thấy | Việc chính để có điểm model | Luật gán nhãn ghi ngay đầu màn hình. Có tác dụng; nhưng khung 15 hộp cần ít nhất 17 lần bấm, không có phím tắt. Đúng nhóm. | sửa | Nút "các hộp còn lại đều đúng" và phím tắt (xem thay đổi 8) | team2/45-label-open.png, team2/45-label-bottom.png |
| Dải báo "frames were labelled before rule B" và nút Relabel them | Không thấy | Biết 42 khung cần gán lại | Rõ. Không thử bấm lưu. Đúng nhóm. | giữ | Không đổi | team/40-model-top.png |
| Datagent KPIs (12 thẻ) | Không thấy | Điểm của model so với ngưỡng Datagent | Rõ: số, khoảng tin cậy, ngưỡng, số mẫu. Có tác dụng. Đúng nhóm. | giữ | Không đổi | team/41-model-0.png |
| Per SKU | Không thấy | Biết sản phẩm nào hay bị đọc sai và nhầm sang sản phẩm nào | Hai dòng TH hiện mã `TMP-MLK-TH-01`, `TMP-MLK-TH-02` thay cho tên. Có tác dụng. Đúng nhóm. | sửa | Hiện tên sản phẩm cho hai dòng TH | team/41-model-1.png |
| Confusion (model → truth) | Không thấy | Thấy cặp sản phẩm bị nhầm | Rõ. Có tác dụng. Đúng nhóm. | giữ | Không đổi | team/41-model-2.png |
| By day | Không thấy | Xem điểm theo ngày | Hai đường không có chú giải; tên chỉ hiện khi rê chuột. Có tác dụng. Đúng nhóm. | sửa | Thêm chú giải | team/41-model-3.png |
| Present or absent | Không thấy | Biết cảnh báo hết hàng trên Dashboard đáng tin tới đâu | Có đoạn giải thích cách đọc. Có tác dụng. Đúng nhóm. | giữ | Không đổi | team/41-model-4.png |
| By time of day | Không thấy | Biết sáng, chiều, tối model sai khác nhau ra sao | Rõ. Có tác dụng; nhiều ô "Not enough samples" vì mới có 42 khung (do thời điểm). Đúng nhóm. | giữ | Không đổi | team/41-model-5.png |
| Live health (5 tab) và dòng Display check | Không thấy | Biết camera, stream và worker có chạy không | Mỗi tab có "What it measures" và "How to read it". Có tác dụng. Đúng nhóm; nhưng nằm cuối trang và câu trả lời "đang chạy hay không" ở tab cuối. | sửa | Đưa một dòng trạng thái lên đầu trang | team/41-model-6.png, team/43-model-health-4.png |

### Settings

| Tính năng | Cho người thường | Cho team vận hành | Nhận xét | Xếp loại | Đề xuất | Ảnh |
|---|---|---|---|---|---|---|
| Account & Cognito Role | Thấy email và nhóm của mình, đã có trong menu tài khoản | Như người thường | Chữ kỹ thuật: "Cognito User Pool + TOTP MFA (single client: Datagent)". Có tác dụng. Đúng nhóm. | sửa | Đổi tên thành "Tài khoản"; bỏ dòng mô tả hạ tầng | viewer/50-settings-top.png |
| Date Format | Chọn và lưu được nhưng ngày giờ trên website không đổi | Như người thường | Rõ. Không có tác dụng: không trang nào đọc lựa chọn này (theo mã nguồn). Không giúp việc nào của ai. | bỏ | Gỡ | team/55-settings-edit-prefs-changed.png |
| Default Landing Page | Chọn và lưu được nhưng đăng nhập vẫn vào Category | Như người thường | Ba lựa chọn "Home, Reports, Products" dùng tên trang cũ. Không có tác dụng. Đúng nhóm. | sửa | Nối cho có tác dụng, mặc định Dashboard (xem thay đổi 2) | viewer/51-settings-0.png |
| Timezone | Một khối chỉ để đọc "Asia/Ho_Chi_Minh (UTC+7)" | Như người thường | Rõ. Không đổi được gì. Không cần một khối riêng. | chuyển chỗ | Thành một dòng chú thích cuối trang | viewer/50-settings-top.png |
| Low-Confidence Flag Threshold | "0.70 (MILK_FLAG_THRESHOLD)" và "sku_id = NULL" không có nghĩa với họ | Biết ngưỡng gắn cờ | Chữ kỹ thuật, chỉ để đọc. Có tác dụng với team. Hiện sai nhóm. | chuyển chỗ | Về trang Model, nơi ngưỡng 0.70 được dùng | viewer/50-settings-top.png |
| Monitored Stores và Import Store List | Thấy tên tiệm; không thấy nút Import (ẩn đúng) | `team_admin` nhập danh sách tiệm | Rõ. Không thử gửi file. Đúng nhóm; không hiện giờ ảnh gần nhất dù API `/stores` có trả. | sửa | Thêm "ảnh gần nhất lúc …" cho từng tiệm | viewer/51-settings-1.png, team/55-settings-edit-full.png |
| Shelf plan | Thấy giờ mở cửa và sản phẩm của tiệm, ô bị khoá, có dòng "Only team_admin can change the shelf plan" | `team_admin` đặt giờ mở cửa và sản phẩm trên kệ | Rõ, có nhãn "Seen in the last 7 days" và nút "Use suggestion". Không thử lưu. Đúng nhóm; nhưng nằm cuối trang, dưới năm khối gần như chỉ để đọc. | giữ | Đưa lên đầu trang cho `team_admin` | viewer/51-settings-2.png, team/55-settings-edit-shelf-plan.png |

## Đối chiếu với điều đã thấy khi đọc mã nguồn

Năm điều ghi trong bản thiết kế trước khi đi website, và kết quả sau khi kiểm trên bản đang chạy.

| Điều đã ghi | Kết quả |
|---|---|
| "Date Format" và "Default Landing Page" được lưu nhưng không trang nào đọc | Đúng. Đăng nhập luôn vào `/category`. |
| Home: cột Recents trái cố định, nút "..." không làm gì; nút "View in Reports" sai tên | Đúng cả ba. Thêm: cột Recents phải mất khi rời trang; "See all results" làm mất từ khoá. |
| Dashboard không có số từng sản phẩm | Đúng. API còn trả sẵn số sản phẩm đang hết (`oos_now`) mà chưa trang nào hiện. |
| Ba thẻ "Active Stores Monitored", "Avg. Inference Time", "Top 50 SKU Accuracy" nghiêng về team | Đúng. Hai trong ba số đã có ở trang Model. |
| Chỉ trang Model giới hạn theo nhóm | Đúng ở thanh bên và ở API. Thêm: Category hiện cả form sửa, nút duyệt và nút Import cho người thường; quyền chỉ bị chặn sau khi bấm. |

## Ghi chú về lúc xem

- Tiệm đã cất kệ nên các số "lúc này" là của 15:45; TH ở 0 hộp là đúng thực tế lúc đó.
- Dữ liệu mới có từ 22/11 (5 ngày), nên "Last 14 days" và "Last 90 days" cho cùng số, "Restock Rate" chưa có kỳ
  trước để so, và nhiều ô của trang Model còn "Not enough samples". Không dòng nào bị xếp `bỏ` vì những lý do này.
- Trong lúc đi, một lệnh đọc của Dashboard bị trả 500 một lần rồi tự thử lại thành công sau 0,7 giây: cơ chế thử
  lại đang làm đúng việc.
- Ba lượt thử nút xuất file đã gọi API xuất khoảng 8 lần (chỉ đọc), mỗi lần chạy 14 đến 22 giây trên Lambda.
