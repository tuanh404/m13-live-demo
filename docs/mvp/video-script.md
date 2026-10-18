# Video M13 · bản cập nhật web + ZIP YOLO

Đầu ra: `data/mvp-submission/M13-demo.mp4` (≤180giây,1600×900), `demo.srt` và `video-record.json`.
Quay thao tác browser thật trên public live bằng phiên tự động riêng; không dùng làm số liệu pilot.
Tiêu đề và phụ đề nằm trong dải140px bên dưới, không đè lên ảnh/nút giao diện. Không có giọng người thu.

| Cảnh | Nội dung chạy thật | Ý chính ở dưới video |
|---|---|---|
| Mở đầu | Màn bắt đầu có hai lựa chọn | Trợ lý ưu tiên ảnh cần review; mở web, không extension. |
| Demo BDD | Queue → ảnh/nhãn/evidence → danh sách box |10ảnh BDD, detector cache; điểm là rủi ro, không xác suất sai. |
| Kết luận | Lỗi thật / Bot nhầm / Bỏ qua | Người review xác nhận. Thao tác minh họa tự động, không phải pilot. |
| Mở lại | Reload, stats giữ3/10 | Verdict không sửa/Save annotation. |
| Baseline | Gain curve trên trang kết quả | Lỗi tiêm offline, recall top20%27,67%; random20,15%. Chưa recall lỗi thật. |
| Ảnh của tôi | Chọn ZIP YOLO1.1, kiểm dữ liệu và tạo queue | Nhận trực tiếp ZIP từ CVAT/Ultralytics; cần ảnh+nhãn. |
| Kiểm một phần | Review ảnh tổng hợp có box trùng và ảnh clean |6tín hiệu hình học/ngữ cảnh; không detector/guideline trên ảnh upload. |
| Tiếp tục | Lưu verdict, mở lại từ Bộ ảnh của tôi | Tiến độ còn nguyên trong phiên đăng nhập hiện tại. |
| Kết | Màn bắt đầu, URL live | Giới hạn ảnh upload và điểm0 không bảo đảm đúng. |

Gói `CVAT-YOLO-1.1-mau.zip` có ảnh tổng hợp không vẽ sẵn box; nhãn trong file riêng, chỉ dùng kiểm phần mềm.
Video không dựng cảnh CVAT Save/recheck, inference/Gemini hoặc human pilot chưa chạy.
Chỉ rút ngắn đoạn chờ mạng dài nếu cần; các khoảng cắt nguồn và lý do nằm trong video-record.json.
Không tăng tốc thao tác review để quảng cáo thời gian tiết kiệm. Thời lượng cuối xác minh từ MP4.

Chạy lại bằng môi trường đang có, không cần account.env hoặc credentials CVAT:

```bash
PLAYWRIGHT_BROWSERS_PATH="$PWD/data/runtime/playwright" .venv/bin/python docs/mvp/capture_demo.py
.venv/bin/python docs/mvp/render_assets.py
```

Công cụ tạo screenshots ở data/mvp-submission/media để slide nguồn HTML dùng tại máy này;
PDF đã nhúng ảnh và mở độc lập. Không đưa ảnh dữ liệu hoặc browser cookies vào source Git.
Mở MP4 kiểm đầu/cuối, phụ đề, ảnh và các giới hạn trước nộp; xác nhận link /submission ẩn danh sau publish.
