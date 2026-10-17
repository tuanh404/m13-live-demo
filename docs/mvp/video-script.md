# Video M13 · tối đa180giây

Đầu ra: `data/mvp-submission/M13-demo.mp4`, phụ đề `demo.srt`, thời điểm từng cảnh và
thời lượng ghi thật trong `video-record.json`. Bản này quay browser thật có phụ đề tiếng Việt,
chưa có giọng thu của người; bản publish ở /submission sau kiểm hash. Không phải video pilot người thật.

## Shot list và lời dẫn

| Khoảng dự kiến | Cảnh chạy thật | Lời dẫn/ý phụ đề |
|---|---|---|
|0–12s| Public HTTPS, Trải nghiệm demo | M13 giúp QC ưu tiên ảnh đáng xem, mở web không cần cài extension. |
|12–30s| Ảnh/nhãn/evidence, tọa độ |10BDD thật; predictions và queue cache. Xanh là nhãn, cam là nghi vấn; điểm không phải xác suất sai. |
|30–50s| Ba verdict, ảnh tiếp | Lỗi thật: xác nhận lỗi; Bot nhầm: bác bỏ nghi vấn; Bỏ qua: chưa chắc. Minh họa tự động không phải kết quả kiểm tay. |
|50–65s| Stats, reload | Lưu kết luận và giữ phiên/kết quả sau reload; verdict không Save annotation. |
|65–85s| Baseline/gain curve public |2.000ảnh test, lỗi tiêm; recall ảnh27,67% so random20,15%. Proxy không phải thời gian thực đo. |
|85–100s| Web intake local nối CVAT job21 | Chuyển môi trường LOCAL có quyền. Ảnh BDD thật, nhãn fixture kiểm phần mềm. |
|100–120s| Intake đã đăng ký → kiểm lại | Job21 đã có từ lượt nghiệm thu trước: dùng lại snapshot nếu nguồn không đổi. Không gọi đây là tiếp nhận lần đầu. |
|120–140s| Queue scoped, đọc nhãn đã Save | Scope riêng từng job;7checks hình học/ngữ cảnh. Detector/spec/GBM chưa có → kiểm một phần. |
|140–165s| Quay về web live/CTA | Public10ảnh cố định; upload mới/CVAT public/pilot là phần còn chờ. Người QC quyết định cuối cùng. |

Timing là mục tiêu biên tập; dùng `video-record.json` và metadata MP4 để xác nhận thời lượng thực.
Không dựng sự kiện Save/recheck trên public. Bằng chứng Save/recheck thật5,43→0 nằm riêng ở
L06-real-CVAT-save-recheck.json/png, không biến screenshot thành cảnh Save trực tiếp trong video.

## Tái quay trên máy hiện tại

API8010 phải đang chạy theo [quickstart](quickstart.md); không restart hoặc đổi mapping giữa cảnh.
Job21 đã có queue; không xóa registry/annotations để làm như lần đầu.

```bash
set -a
source data/cvat-runtime/account.env
set +a
PLAYWRIGHT_BROWSERS_PATH="$PWD/data/runtime/playwright" python docs/mvp/capture_demo.py
```

Backend giữ credentials CVAT; video chỉ quay web UI rồi thêm phụ đề. Không quay Save trực tiếp.
Các verdict public là lượt demo tự động riêng; không đăng ký human pilot. Khi thu giọng người,
dùng lời dẫn trong bảng, giữ nguyên nội dung các giới hạn và tổng thời lượng≤180giây.

## Trước khi gửi BTC

Mở MP4 từ đầu đến cuối, kiểm chữ/nhãn môi trường, không lộ mật khẩu/token hoặc desktop riêng.
Kiểm MP4/PDF/thumbnail ở /submission bằng cửa sổ ẩn danh sau khi operator publish.
Điền URL thực vào submission manifest; đường dẫn local chưa phải link nộp.
