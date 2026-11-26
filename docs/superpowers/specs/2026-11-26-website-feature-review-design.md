# Đánh giá tính năng website: mang lại gì cho người xem và cho team vận hành

26/11/2026 · bản thiết kế ngắn · hoang duyệt 26/11

## Vì sao

Website đã chạy ổn định. hoang muốn rà lại các tính năng để biết cái nào cần, cái nào không cần hoặc ít tác
dụng. Mục đích chính là cải thiện cảm giác dùng website.

## hoang đã nói (26/11)

- Website dùng để xem hàng hoá hiện có trên kệ. Tới giờ chưa tính tới việc bán được hay không.
- Người thường chỉ cần nhìn Dashboard là xong.
- Website còn một mục đích nữa: vận hành model (gán nhãn, đánh giá, giám sát).
- Không cần đo lượt dùng để lấy dữ liệu. Đánh giá bằng góc nhìn của người thường và của team vận hành:
  website mang lại cho họ điều gì. Không cần cứng nhắc.

## Mục tiêu

- Một bảng xếp loại mọi tính năng trên 5 trang và phần đăng nhập: giữ, sửa (cho gọn hoặc dễ hiểu hơn),
  chuyển chỗ, bỏ.
- Một danh sách ngắn những thay đổi đáng làm nhất cho cảm giác dùng, xếp theo lợi ích so với công làm.
- Những thứ người xem mong có mà chưa có, nếu thấy rõ trong lúc đi qua.

## Không làm (đợt này)

- Không sửa, không xoá gì trên website. Mọi thay đổi là việc sau, hoang duyệt từng mục.
- Không bật ghi log, không đo lượt dùng.
- Không đánh giá độ chính xác của model. Việc đó đã có trang Model và các đợt riêng.
- Không tính số bán.

## Không được xảy ra

- Dữ liệu thật trên bản đang chạy bị đổi. Không lưu sửa kết quả, không xác nhận sự kiện, không lưu nhãn,
  không lưu shelf plan hay preferences, không import file. Tính năng ghi chỉ xem tới bước trước khi lưu, phần
  còn lại đọc mã nguồn.
- Kết luận "bỏ" chỉ vì người đánh giá không dùng tới. Mỗi kết luận phải nói rõ tính năng đó không giúp việc
  nào của ai.
- Ảnh chụp màn hình lộ mã MFA hoặc mã QR.

## Phương án

1. **Chấm theo việc cần làm của từng nhóm, đi trên website thật. Đã chọn.** Cho kết quả ngay và trả lời đúng
   câu hỏi "website mang lại gì cho họ".
2. Đo lượt dùng thật 1–2 tuần rồi mới kết luận. hoang: không cần thiết. Hiện chỉ có 7 tài khoản, gồm cả tài
   khoản kiểm thử, nên số liệu nói rất ít.
3. Cách 1 kèm bật ghi log để kiểm lại sau. Bỏ, cùng lý do với cách 2.

## Thiết kế

### Hai góc nhìn

**Người thường** (tài khoản nhóm `datagent`). Mở website để biết hàng trên kệ lúc này. Việc của họ:

- Mỗi sản phẩm còn bao nhiêu.
- Món nào hết hoặc sắp hết.
- Con số này mới tới lúc nào và tin được tới đâu.
- Đôi khi: xem ảnh để tự kiểm lại.

**Team vận hành** (nhóm `team_admin`, `field_team`). Việc của họ:

- Xem chỗ model đọc chưa chắc và sửa lại.
- Gán nhãn khung hình.
- Xem điểm của model.
- Biết camera và worker có đang chạy không.
- Cài đặt tiệm: giờ mở cửa, SKU trên kệ, danh sách tiệm.

### Cách đi

Đăng nhập bản đang chạy bằng một tài khoản của mỗi nhóm. Đi hết từng trang ở cỡ màn hình máy tính thường,
chụp ảnh, thử từng nút và từng bộ lọc. Xem thêm Dashboard ở bề ngang điện thoại.

Với mỗi tính năng, ghi bốn điều bằng lời, không chấm điểm số:

1. Nó cho ai điều gì, hoặc không cho ai.
2. Có dễ thấy và dễ hiểu không: vị trí, chữ trên màn hình, số bước.
3. Có tác dụng thật không: bấm có ra kết quả, cài đặt có đổi được gì.
4. Có hiện cho đúng nhóm không.

### Danh sách đi qua

- **Đăng nhập, đăng ký, MFA.**
- **Thanh bên:** điều hướng, thu gọn, ô tìm, menu tài khoản.
- **Home:** lời chào và dòng trạng thái, ô tìm (Ctrl K) sản phẩm và trang, hai cột Recents, hộp xem nhanh
  sản phẩm.
- **Dashboard:** ba bộ lọc (Timeframe, Store, Category), nút Download, dòng báo camera không thấy kệ, sáu
  thẻ số, biểu đồ Shelf Stock Count, biểu đồ Trends & Insights, Recent Shelf Activities (ảnh trước và sau,
  xác nhận sự kiện, xem tất cả).
- **Category:** danh sách sản phẩm theo nhóm, ô tìm, lọc Store / Category / Status, sắp xếp, ô chọn, Export CV
  Output, Import SKU Master, thẻ sản phẩm (Human Audit & Correction, View frame), hàng chờ duyệt (Confirm AI,
  Correct).
- **Model:** chọn phiên bản và khoảng ngày, gán nhãn khung hình, Datagent KPIs, Per SKU, Confusion, By day,
  Present or absent, By time of day, Live health.
- **Settings:** Account & Cognito Role, Personal Display Preferences, Timezone, Low-Confidence Flag Threshold,
  Monitored Stores và Import Store List, Shelf plan.

### Kết quả

Một trang báo cáo riêng tư có ảnh chụp màn hình:

- Phần đầu: những thay đổi đáng làm nhất.
- Sau đó mỗi trang một bảng. Mỗi dòng là một tính năng: xếp loại, lý do theo từng góc nhìn, đề xuất.

Bản chữ của báo cáo lưu trong `docs/`.

### Đã thấy khi đọc mã nguồn (kiểm lại trên website thật)

- Settings: "Date Format" và "Default Landing Page" được lưu nhưng không trang nào đọc.
- Home: cột Recents bên trái là danh sách cố định, nút "..." của nó không làm gì. Hộp xem nhanh có nút "View
  in Reports" trong khi trang tên là Dashboard.
- Dashboard không có số lượng từng sản phẩm, chỉ có một tổng chung. Số từng sản phẩm nằm ở Category.
- Nghi vấn: ba thẻ "Active Stores Monitored", "Avg. Inference Time" và "Top 50 SKU Accuracy" nghiêng về việc
  của team hơn là của người xem.
- Trên thanh bên chỉ trang Model giới hạn theo nhóm; các trang còn lại mọi tài khoản đều thấy.

## Để người làm tự quyết

- Công cụ đăng nhập và chụp ảnh, thứ tự đi các trang, bố cục trang báo cáo.

Ba điều sau là do Claude chọn, hoang chưa nói:

- Xem cả phần đăng nhập và đăng ký, vì đó là thứ đầu tiên người thường gặp.
- Xem Dashboard ở bề ngang điện thoại.
- Báo cáo là một trang có ảnh chụp, không chỉ là file chữ.
