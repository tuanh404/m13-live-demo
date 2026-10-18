# Phạm vi hỗ trợ bản M13 hiện tại

Cập nhật18/10: runtimec94265b, CI316passed1skip; video/slides đã bổ sung luồng upload.
Các mục release17/10 bên dưới là bằng chứng lịch sử.

| Chức năng | Public Render | Local operator/CVAT | Giới hạn/bằng chứng |
|---|---|---|---|
| Web không extension | Đã kiểm HTTPS | Có |10BDD demo public, queue/predictions cache |
| Upload ảnh/nhãn mới | YOLO1.1/Ultralytics Detection đã kiểm | Dữ liệu có thể đưa vào CVAT trước | ZIP1–10ảnh1280×720/5MB,6checks hình học/ngữ cảnh,10lớp BDD; phiên login12giờ |
| Tự tiếp nhận task/job | Role demo bị chặn | Đã kiểm UI job20/21 | Task/server allowlist backend,1280×720 bbox BDD |
| Hình học/ngữ cảnh | Demo theo snapshot; upload mới6signals |7signals cho job mới | Không suy ra vị trí xe chỉ từ tọa độ |
| Bất đồng detector |4signals tính trước | Adapter cache kiểm hash ảnh/model đã có | Chỉ bật khi có manifest provenance khớp; chưa inference mới |
| Guideline/Gemini | Không online trong demo | Công cụ extract/edit/approve có test | Cần tài liệu/nguồn hợp lệ, key môi trường và người duyệt; không tự duyệt |
| GBM/retrain | Chặn demo | Adapter có test | Không báo training/model thật thành công bằng mock |
|3verdict/stats | Đã kiểm, tách phiên | Đã kiểm, tách job | Không đồng nghĩa sửa/Save nhãn |
| Save/recheck | Chưa có CVAT public | Task20 UI thật đạt5,43→0 | Nhãn fixture, không phải đo chất lượng BDD; giữ snapshot trước/sau |
| Retry/reload/restart | Đã kiểm L05 | Đã kiểm fixture + job thực L06 | New queue/version tạo lượt cần xem mới, lịch sử cũ vẫn giữ |
| Cache job không đổi | Có trong bản cập nhật; public không bật intake | Có regression test | Giữ queue/progress, kiểm hash/mapping/profile; input đổi mất hiệu lực |
| Audit5% ngoài top20% | Giữ plan nguồn | Fixture policy/export/Wilson đạt | Chưa kết quả audit người thật; không lộ cờ trong UI |
| Baseline/gain curve | Có báo cáo offline | Có replay/hash | Lỗi tiêm; không measured time_saved |
| Pilot30×2reviewer | Không dùng demo làm pilot | Bộ30BDD/task/DB riêng sẵn | Chưa có lượt người thật; không fake30 từ10 |
| Deploy | Native Render Free đạt | Bundle Docker/config có | Chưa clean container install/máy thứ hai; chưa4máy |
| Usability người mới | Browser đã kiểm | Browser đã kiểm | Chưa có người mới làm thử độc lập; tên box mặc định thu gọn, có chọn/toggle |

Bản cập nhật17/10 được phát hành qua repo deploy riêng private; commit/CI/URL và kết quả
kiểm thực xem checkpoint/reports mới. Repo nhóm giữ diff local, không commit/push.
Thời gian20/45phút trên cùng10ảnh là nhóm cung cấp, chưa đối chiếu log; không phải pilot30.

## Bằng chứng phát hành cuối

Commit runtime `bfb498e`, CI đúng commit xanh. Browser public trước/sau redeploy và restart thật giữ3/10,
retry request cũ không thêm row; snapshot cũ vẫn đọc và auth/role/session isolation đạt.
20verdict có trước phiên giữ nguyên nội dung. Video/PDF/PNG được GET ẩn danh và kiểm hash, không mở source ZIP.
Video137,92giây có phụ đề tiếng Việt; không giọng người hoặc human pilot. Hồ sơ chưa nộp BTC.


## UI refresh17/10 · 275330c

- Màn bắt đầu dùng layout riêng, CTA demo rõ, account login thu gọn, trạng thái mạng/retry dễ hiểu.
- Menu chỉ hiện baseline/hồ sơ đã có dữ liệu; pilot đúng cấu hình/quyền; CVAT đúng mapping/quyền.
  Pilot luôn giữ CVAT ẩn. Không xóa adapter/local workflow hoặc bỏ qua auth/CSRF.
- Local279passed1skipped120,31s; CI https://github.com/tuanh404/m13-live-demo/actions/runs/39050250157: CI các bước đạt, workflow GitHub còn pending. Ruff/checker/wheel đạt.
- Public Chrome sạch kiểm entry/desktop/mobile, vào demo, baseline,3artifact links, reload/logout;
  phiên cũ vẫn3/10, stats nguyên. Không ghi verdict thử mới. Bằng chứng data/mvp-ui-refresh/.
- Deploy chỉ repo private/Render hiện có, không đổi env/bundle/schema hoặc dữ liệu, không chi phí.
- Video137,92s giữ nguyên nội dung chức năng, được quay ở runtime bfb498e; màn entry hiện tại mới hơn.
  Không coi UI refresh là human pilot hoặc usability đã được người mới nghiệm thu.
