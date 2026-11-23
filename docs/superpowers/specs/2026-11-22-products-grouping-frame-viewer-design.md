# Trang Products: gộp SKU cùng dòng và xem khung hình model khoanh

Ngày 2026-11-22 · hoang duyệt hướng trong chat · thuộc HOANG-P10 (website dùng số thật)

## Vì sao

Trang Products (`/category`) hiện mỗi SKU một dòng. Danh mục thật là biến thể của vài dòng sản phẩm
(10 Vinamilk, 4 Slide, 2 TH), nên danh sách dài, lặp và khó nhìn tổng thể. hoang chọn **phương án A:
gộp theo hãng + dòng sản phẩm**. hoang cũng muốn **mở được ảnh có các khung model khoanh** ngay trong
thẻ View (Validation Card), để thấy model đã đếm cái gì.

## Mục tiêu

- Danh sách mặc định gọn: mỗi dòng sản phẩm một hàng tổng, bấm để mở các biến thể.
- Từ thẻ View mở được khung hình (đã làm mờ mặt) có vẽ các khung của lần đọc đó.

## Không làm

- Không đổi số đếm hay API: số vẫn theo từng SKU (`sku_id` = tên sản phẩm, Data Dictionary); CSV xuất ra không đổi.
- Không sửa danh mục theo tiệm và không thêm ngưỡng tối thiểu ở worker: hai việc này còn chờ hoang quyết.
- Không vẽ khung của SKU khác trong cùng khung hình, không sửa khung, không đổi backend.

## Cách làm

**Phương án đã cân nhắc** (gộp): A hãng + dòng, 5 nhóm (**hoang chọn**); B chỉ theo hãng, 3 nhóm (mở
Vinamilk vẫn 10 dòng); C theo ngành hàng, 2 nhóm (quá thô).
**Ảnh** (agent chọn): vẽ khung trên trình duyệt bằng SVG phủ lên ảnh. Đã loại: backend vẽ sẵn ảnh
(thêm Lambda và thư viện ảnh) và chỉ đưa link ảnh gốc như hàng chờ duyệt (không có khung, không đúng yêu cầu).

### 1. Gộp nhóm (trang Products)

- **Khoá nhóm:** `brand` + `subcategory` lấy từ SKU Master qua `/products`. Thiếu `subcategory` thì chỉ theo
  `brand`; thiếu cả hai thì nhóm "Other". Nhãn dạng `Vinamilk · Plant Milk` (tiếng Anh như dữ liệu và giao diện).
  Với dữ liệu hiện tại ra 5 nhóm: TH · Fresh Milk (2), Vinamilk · Fresh Milk (3), Vinamilk · Flavored Milk (3),
  Vinamilk · Plant Milk (4), Slide · Potato Crisps (4).
- **Hàng tổng của nhóm**, cùng các cột như hàng SKU:
  - Product: mũi tên mở/đóng, ảnh của biến thể đầu, nhãn nhóm, "N variants · M on shelf".
  - Category: pill ngành hàng. Pack: chung một quy cách thì ghi (vd `Box 180 ml`), khác nhau thì "Mixed".
  - SKU code: "N SKUs".
  - On-shelf stock: tổng hộp các biến thể.
  - Confidence: trung bình theo số hộp của các biến thể đang có hộp (cùng cách backend tính theo tiệm), kèm "⚑ K flagged". Không biến thể nào có hộp thì "—".
  - Avail in stores: lớn nhất trong các biến thể / tổng số tiệm. Đúng tuyệt đối khi còn 1 tiệm; nhiều tiệm thì cần API trả theo tiệm *(ghi chú cho sau)*.
  - Actions: không có View, vì View là của từng SKU.
- **Mặc định đóng hết.** Trạng thái mở/đóng giữ nguyên qua lần tải lại 15 giây và khi đổi bộ lọc. Đầu bảng có nút "Expand all / Collapse all".
- **Lọc, tìm, sắp xếp:**
  - Bộ lọc và ô tìm áp lên từng biến thể; nhóm còn ít nhất một biến thể khớp thì hiện.
  - Đang có chữ tìm thì nhóm khớp tự mở.
  - Sắp xếp nhóm theo giá trị tổng (tồn kho, độ tin cậy, tên nhãn); biến thể trong nhóm sắp theo cùng tiêu chí.
- **Chọn:** ô chọn của nhóm chọn hoặc bỏ mọi biến thể đang hiện trong nhóm, có trạng thái chọn dở.
- **Code:** logic gộp là hàm thuần trong `frontend/lib/product-groups.ts`; giao diện hàng nhóm ở `CategoryProductsView.tsx`.

### 2. Xem khung hình có khung (thẻ View)

- Nút **"View frame"** trong mục "Capture & S3 Traceability" của Validation Card.
  - Bật khi `GET /products/{sku}` trả về `frame_presigned_url` và có ít nhất một khung.
  - Không có thì nút tắt, kèm lý do "No frame stored for this reading".
- **Trình xem** phủ toàn màn hình trên thẻ:
  - Ảnh khung hình (đã làm mờ mặt) với các khung `bounding_box` của đúng lần đọc trên thẻ, đánh số 1..N.
  - Đầu trình xem ghi reading id, giờ chụp, số hộp, độ tin cậy, số mặt đã làm mờ.
- **Thu phóng:** khung trong ảnh 2560×1440 rất nhỏ, nên mặc định mở **phóng vào vùng quanh các khung** (chừa lề bằng một khung ở mỗi bên), có nút "Full frame" để xem cả ảnh. Kích thước gốc lấy từ chính ảnh (`naturalWidth/Height`), không dùng số cứng 2560×1440.
- **Link hết hạn:** link ký của S3 sống 15 phút.
  - Trình xem dùng dữ liệu thẻ đang có. Nếu đã quá 10 phút hoặc ảnh tải lỗi thì gọi lại `GET /products/{sku}`, cập nhật cả thẻ lẫn trình xem.
  - Gọi lại thì thẻ nhảy sang lần đọc mới nhất, và trình xem ghi rõ điều đó.
- **Riêng tư:** link ký không lưu và không ghi log. Ai xem được thẻ (mọi nhóm đã duyệt) thì xem được ảnh, như API hiện tại.
- **Code:** hàm tính vùng phóng là hàm thuần trong `frontend/lib/frame-geometry.ts`; giao diện ở `components/category/FrameViewer.tsx`.

## Kiểm tra

- Hàm thuần (gộp nhóm, tổng, sắp xếp, vùng phóng) kiểm bằng `node --test --experimental-strip-types`, không thêm thư viện.
- `next build` qua.
- Chạy Edge ngầm với tài khoản `api-check@example.com` trên dữ liệu sống:
  - Chụp danh sách gộp ở trạng thái đóng và mở.
  - Mở trình xem, kiểm số khung vẽ ra bằng số khung trên thẻ.

## Để người làm tự quyết

Màu, khoảng cách và icon theo các trang hiện có; câu chữ tiếng Anh như giao diện; cách viết chi tiết các hàm.
