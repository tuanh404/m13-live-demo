# Video và slides · cập nhật18/10/2026

Bản này thay video/PDF trước upload, giữ nguyên runtime web đã kiểm `c94265b`.
Quay lại UI live hiện tại bằng phiên demo tự động riêng, không dùng phiên hoặc verdict của người thật.
Không cần CVAT localhost, credentials CVAT hoặc extension để quay và trải nghiệm luồng này.

- Video1600×900, tiêu đề và phụ đề ở dải140px riêng phía dưới, không che nút/box.
- Nội dung: demo10BDD → evidence → ba kết luận → reload/stats → baseline → ZIP YOLO1.1 → review/mở lại.
- Các đoạn chờ mạng dài có thể rút ngắn; lưu cut list nguồn, không giả cảnh đã xử lý thành công.
-12slides: cover, vấn đề, hành trình, screenshots live, evidence, upload,6tín hiệu,
  baseline, số liệu nhóm cung cấp, kiến trúc, phạm vi/roadmap và URL trải nghiệm.
- PDF nhúng ảnh; HTML nguồn chỉnh sửa được. Screenshots được tạo lại trong data/mvp-submission/media;
  góiM13-slides-editable.zip kèm HTML và ảnh để mang sang máy khác, không chứa secret/cookie/DB.

Phân biệt rõ:

1. Demo10BDD có cached predictions; không detector/Gemini inference online.
2. ZIP mới kiểm6tín hiệu hình học/ngữ cảnh; chưa khẳng định box bám vật thể hay phát hiện thiếu vật thể.
3. ZIP minh họa là ảnh tổng hợp và nhãn riêng, dùng kiểm phần mềm, không pilot người thật.
4. Baseline27,67%so random20,15% tính từ lỗi tiêm trên tập test, chưa phải recall lỗi thật.
5.20/45phút trên cùng10ảnh là số liệu nhóm báo, chưa đối chiếu log; không tăng thành30ảnh.

Không xóa source/test/tài liệu theo yêu cầuBTC hoặc dữ liệu, DB, annotations/verdict, backup và bằng chứng.
Chỉ dọn cache tải/build, bản build sinh lại được và profileChrome thử không còn process sử dụng.
Python runtime/.venv/browser runtime được giữ và kiểm import sau dọn.
Chi tiết paths đã dọn: data/mvp-media-refresh/cleanup.json (logical bytes không phải toàn bộ dung lượng đĩa
được giải phóng vì cache có hardlink tới .venv).

Các file nộp chính nằm data/mvp-submission/. Chỉ công bố video/PDF/thumbnail qua route assets cố định;
source ZIP và editable slide ZIP vẫn local để chủ dự án chủ động chia sẻ. Không tự nộp bàiBTC.
