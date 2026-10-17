# Nhật ký phiên MVP ·16/10/2026

Đây là ghi chép hoạt động thực tế phiên L06; không bổ sung nhật ký giả cho các ngày đã qua.
Nhật ký trước: [tuần4](bao-cao-tuan-4.md), [tiến độ nhóm](../docs/tien-do.md).

- Đối chiếu kế hoạch6-lenh-v1/cvat-job-intake-v1 và checkpoint L05. Giữ nhánh
  feat/tuanh-mvp-live-rebuild/nền72b1e4c, giữ diff/secrets/task cũ. Không commit/push/deploy.
- Nghiệm thu hai task/job test20/21 qua extension thật: đọc ảnh/nhãn, queue3ảnh/job,
  ba loại verdict, reload và chuyển job. Ảnh BDD thật, nhãn fixture; không human pilot.
- Task20 kéo box và Save thật trong CVAT; web đọc nhãn đã lưu, recheck5,43→0 và xem
  lịch sử trước/sau. Lần thử kéo không đổi giữ kết quả không đổi, không giả tăng/giảm score.
  Box đã sửa được giữ trong task test mới; không sửa nhãn tasks16/19/pilot.
- Sửa retry khi lỗi mạng lúc mở intake; thông báo bằng ngôn ngữ người dùng.
- Phát hiện kiểm cùng job bằng request mới tạo version thừa/reset tiến độ hiển thị; bổ sung
  cache verified source/profile/artifact/mapping/image hashes. Input Save đổi vẫn recompute.
  Giữ mọi rows/version đã tạo khi kiểm, không xóa để làm đẹp kết quả.
- Hoàn thiện đặc tả/kiến trúc, hướng dẫn reviewer/operator, bảng hỗ trợ, ma trận kiểm,
  pitch HTML12slides và PDF, thumbnail SVG/PNG, video phụ đề từ browser thật và manifest nộp.
- Kiểm link: live health200, repo nhóm public200, repo deploy private trả404 khi chưa đăng nhập.
  Assets mới còn local; không tự thay quyền repo hoặc dựng link chia sẻ chưa tồn tại.

Test/kết quả chi tiết và các lần kiểm còn thiếu ở [testing](../docs/mvp/testing.md),
checkpoint data/mvp-handoff/CHECKPOINT.md và các log L06. Số liệu baseline có nguồn/hash tại
mvp-evaluation-summary.json; lỗi tiêm và proxy tách khỏi human pilot thực đo.

Còn chờ người/hạ tầng: pilot30×2reviewer thật, usability người mới, CVAT public/quyền server,
chia sẻ source/assets/video đúng quyền trước nộp. Upload batch ảnh/nhãn mới chưa triển khai.
