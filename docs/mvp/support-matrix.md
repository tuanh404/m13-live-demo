# Phạm vi hỗ trợ bản M13 hiện tại

| Chức năng | Public Render | Local operator/CVAT | Giới hạn/bằng chứng |
|---|---|---|---|
| Web không extension | Đã kiểm HTTPS | Có |10BDD demo public, queue/predictions cache |
| Upload ảnh/nhãn mới | Chưa có | Dữ liệu đưa vào CVAT trước | Không nhận ảnh trống nhãn để giả làm QC |
| Tự tiếp nhận task/job | Role demo bị chặn | Đã kiểm UI job20/21 | Task/server allowlist backend,1280×720 bbox BDD |
| Hình học/ngữ cảnh | Theo snapshot demo |7signals cho job mới | Không suy ra vị trí xe chỉ từ tọa độ |
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
