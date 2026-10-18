# M13 — Reviewer Prioritization Assistant

**Trợ lý ưu tiên kiểm tra nhãn ảnh 2D, giúp QC tập trung vào những ảnh có nguy cơ sai cao.**

Dự án thuộc chủ đề **Annotation & QC**, sử dụng dữ liệu **BDD100K**. Hệ thống tạo hàng đợi review theo điểm rủi ro, kèm ảnh, nhãn và lý do nghi vấn để người dùng xác nhận.

## Trải nghiệm và hồ sơ dự án

| Hạng mục | Liên kết |
|---|---|
| **MVP Live** | [Trải nghiệm sản phẩm](https://m13-live-demo.onrender.com/login) |
| **Source code** | [GitHub công khai](https://github.com/tuanh404/m13-live-demo) |
| **Video demo — 2 phút 05 giây** | [Xem video][video] |
| **Pitch Deck — 12 trang** | [Xem slides PDF][slides] |
| **Thumbnail** | [Ảnh đại diện dự án][thumbnail] |
| **Sơ đồ kiến trúc** | [Architecture diagram](docs/mvp/architecture.svg) |
| **Đặc tả và thiết kế** | [Spec & Design](docs/mvp/spec-design.md) |
| **Tài liệu kiểm thử** | [Testing](docs/mvp/testing.md) |
| **Nhật ký tuần** | [16/10](reports/weekly-mvp-2026-10-16.md) · [17/10](reports/weekly-mvp-2026-10-17.md) · [18/10](reports/weekly-mvp-2026-10-18.md) |

Slides trình bày bài toán, giải pháp, kiến trúc, kết quả đánh giá, tính khả thi và định hướng phát triển.

## Chức năng chính

- **Trải nghiệm demo:** review 10 ảnh BDD với hàng đợi và kết quả kiểm tra đã chuẩn bị.
- **Kiểm tra bộ ảnh của tôi:** tải ZIP ảnh và nhãn YOLO, chạy các phép kiểm được hỗ trợ và tạo hàng đợi riêng.
- **Review có giải thích:** xem ảnh, box, điểm rủi ro và lý do từng nghi vấn.
- **Lưu kết luận:** chọn **Lỗi thật / Bot nhầm / Bỏ qua**, chuyển ảnh tiếp theo và xem thống kê.
- **Tiếp tục sau reload:** giữ tiến độ trong phiên sử dụng.

## Cách thử nhanh

1. Mở **MVP Live**.
2. Chọn **Trải nghiệm demo**, hoặc **Kiểm tra bộ ảnh của tôi**.
3. Với bộ ảnh riêng, tải gói mẫu trên giao diện hoặc ZIP YOLO có cả ảnh và nhãn.
4. Xem nghi vấn và chọn kết luận cho từng ảnh.
5. Mở thống kê để xem kết quả review.

**Không cần cài extension hoặc CVAT để thử web public.**

## Phạm vi và giới hạn

- Upload hỗ trợ YOLO Detection 2D từ CVAT YOLO 1.1 hoặc Ultralytics: tối đa **10 ảnh JPG/PNG, 1280×720, ZIP 5 MB**, thuộc các lớp BDD được hỗ trợ.
- Bộ ảnh tải lên được **kiểm một phần** bằng các phép kiểm hình học/ngữ cảnh; chưa chạy detector hoặc Gemini trực tiếp trên ảnh mới.
- Điểm thể hiện **mức rủi ro để ưu tiên review**. Điểm 0 không bảo đảm nhãn đúng; nghi vấn cần người xác nhận.
- Kết luận review không tự sửa hoặc lưu nhãn trong CVAT.
- Demo BDD dùng predictions đã lưu; tích hợp CVAT local được trình bày riêng trong [phạm vi hỗ trợ](docs/mvp/support-matrix.md).
- Render Free có thể ngủ khi không sử dụng; lần mở đầu cần chờ dịch vụ khởi động.

## Kiểm thử và phát triển

Bản source công khai đã qua CI: **316 test đạt, 1 bỏ qua**, Ruff và repo checker đạt.

Xem [hướng dẫn chạy](docs/mvp/quickstart.md), [hướng dẫn upload](docs/mvp/upload-quickstart.md) và [quy trình đóng góp](CONTRIBUTING.md).

Hướng phát triển: bổ sung detector cho ảnh mới, mở rộng định dạng nhập, triển khai CVAT có quyền truy cập và đánh giá thời gian review bằng pilot có log đầy đủ.

## Nhóm thực hiện

Hoàng Mạnh Cường · Long · Tú Anh · Sơn

Dữ liệu BDD100K được sử dụng theo [giấy phép](deployment/render/BDD100K-LICENSE.txt). Credentials, database riêng và dữ liệu runtime không được đưa vào mã nguồn công khai.

[video]: https://m13-live-demo.onrender.com/submission/assets/e3aaccc7c5d6ac83c4c1c6cf25ee1c2eac2a3a40ca9c2f3d3066f509935d147a/M13-demo.mp4
[slides]: https://m13-live-demo.onrender.com/submission/assets/e3aaccc7c5d6ac83c4c1c6cf25ee1c2eac2a3a40ca9c2f3d3066f509935d147a/pitch.pdf
[thumbnail]: https://m13-live-demo.onrender.com/submission/assets/e3aaccc7c5d6ac83c4c1c6cf25ee1c2eac2a3a40ca9c2f3d3066f509935d147a/thumbnail.png
