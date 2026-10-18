# Thử M13 không cần hiểu kỹ thuật

## Người trải nghiệm web public

1. Mở https://m13-live-demo.onrender.com. Nếu service vừa ngủ, chờ khoảng1phút rồi tải lại.
2. Bấm **Trải nghiệm demo**. Không cần tài khoản CVAT, key, extension hay cấu hình.
3. Xem ảnh giữa màn hình: xanh là nhãn hiện có, cam/nét đứt là gợi ý máy cần đối chiếu.
4. Đọc **Cần xem gì?**, chọn **Lỗi thật**(1), **Bot nhầm**(2) hoặc **Bỏ qua**(3).
5. Kết luận được lưu rồi chuyển ảnh tiếp. Xem thống kê bên phải; reload vẫn giữ kết quả.

Màn bắt đầu có một nút chính **Trải nghiệm demo**. Phần tài khoản được cấp có thể mở/đóng riêng;
không cần nhập tài khoản để thử public demo. Lỗi kết nối có thông báo và nút thử lại.
Menu chỉ hiện chức năng môi trường đang cung cấp: baseline khi báo cáo hợp lệ, hồ sơ khi đã publish,
pilot khi được cấu hình và có quyền, CVAT khi ảnh có mapping và người dùng có quyền dùng.
Public demo không hiện các nút CVAT/pilot không dùng được; các adapter local vẫn giữ nguyên.

Điểm0 vẫn có thể có lỗi. Verdict chưa sửa/Save annotation. Demo mẫu có10ảnh cố định; muốn dùng ảnh riêng, chọn **Kiểm tra bộ ảnh của tôi** và
tải nguyên ZIP YOLO1.1/Ultralytics Detection có ảnh+nhãn. Xem [giới hạn upload](upload-quickstart.md).
Hai luồng không phải pilot người thật. Mục baseline là lỗi tiêm, không phải số đo người thật.

## Người review CVAT local đã được operator cấu hình

Mở task/job trong CVAT → bấm biểu tượng QC trên thanh Chrome → **Kiểm tra job này**.
Chờ đọc ảnh/nhãn đã Save và tính queue. **Kiểm một phần** nghĩa là hiện có hình học/ngữ cảnh,
chưa có guideline đã duyệt; detector chỉ có khi cache khớp hash ảnh/model. Chọn ảnh trong queue rồi đối chiếu và bấm kết luận.
Extension yêu cầu chọn ảnh kế tiếp; web review tự chuyển ảnh. Bấm biểu tượng Chrome lần nữa để đóng bảng;
bấm ra ngoài không đóng. Không có logo nổi thứ hai trong canvas.

Muốn sửa: chọn đúng ảnh ở CVAT → sửa → **Save** → **Đọc nhãn đã lưu** → **Kiểm tra lại lỗi**.
Đọc nhãn không tự chấm điểm. Di chuyển box không tác động phép kiểm đang bật có thể không đổi điểm;
hình học không biết đâu là chiếc xe nếu không có detector. Xem lịch sử trước/sau khi recheck xong.

Khi có lỗi kết nối, bấm thử lại. Nếu thiếu quyền/không hỗ trợ dữ liệu thì nhờ operator;
không đổi URL/key/model hoặc dùng fixture thay job đang mở.

## Bật lại nghiệm thu local trên máy hiện tại

Các lệnh sau dùng dữ liệu/task test đã tạo trước nghiệm thu; không import hoặc sửa mapping giữa jobs.
Nếu8010 đang chạy đúng API này, không bật thêm tiến trình. Không dừng CVAT/API khác.

```bash
source .venv/bin/activate
set -a
source data/cvat-runtime/account.env
set +a
PYTHONPATH="$PWD" python data/mvp-L06-acceptance/run_api.py
```

Web intake hai task test đã được cấp quyền:

- http://127.0.0.1:8010/intake?cvat_origin=http%3A%2F%2Flocalhost%3A8080&task_id=20&job_id=20
- http://127.0.0.1:8010/intake?cvat_origin=http%3A%2F%2Flocalhost%3A8080&task_id=21&job_id=21

Hoặc nạp unpacked extension từ `data/mvp-L06-acceptance/extension` trong chrome://extensions
(Developer mode), ghim QC, mở http://localhost:8080/tasks/20/jobs/20 hoặc task21/job21.
Credentials mở riêng bằng editor khi cần; không in terminal hoặc gửi chat.
Ảnh là BDD thật, nhãn hai task này là fixture kiểm phần mềm; không dùng làm phiếu kiểm tay/pilot.

## Operator cài máy khác một lần

Python3.11/3.12; `python -m pip install -e '.[dev,demo,browser]'`.
CVAT phải có server truy cập được và task2D đúng adapter. Dùng configs/job_intake.yaml làm mẫu,
đặt allowlist và thư mục persistent mới ở backend; mặc định allowlist rỗng là từ chối mọi task.
Đặt M13_INTAKE_CONFIG,CVAT_USER,CVAT_PASSWORD và M13_CVAT_URL trong môi trường backend.
Chạy `python -m src.cli serve --host 127.0.0.1 --port 8000`, cấu hình extension/connection.json
một lần cho máy đó, không chứa credentials. Mỗi máy tự đọc ID/frame thực, không dùng lại mapping20/21.
Triển khai ngoài loopback cần auth/HTTPS/persistent storage theo [deploy](../deploy-mvp.md),
không mở API local ra Internet. Chưa tính là đã cài/kiểm đủ4máy.

## Bản cập nhật17/10

Tên tất cả box được thu gọn mặc định để dễ nhìn ảnh. Muốn xem tên/tọa độ: mở **Danh sách nhãn**,
chọn box cần đối chiếu; hoặc bật **Hiện tên tất cả box**. Ba kết luận và phím1/2/3 giữ nguyên.

Ở **Kết quả baseline**, bảng lỗi tiêm/proxy và kết quả nhóm cung cấp tách riêng. Cùng10ảnh,
assisted20phút/manual45phút là nhóm báo lại, chưa có log đối chiếu; không phải pilot30ảnh.

Mở https://m13-live-demo.onrender.com/submission để lấy video, slides và thumbnail đã publish.
Nếu chưa có bộ artifacts, trang ghi rõ chờ công bố, không giả link hoặc mở source private.
Source bản mới nằm trong sourceZIP bàn giao; không tự công khai repo private.

Operator có detector cache đúng nguồn có thể bật adapter theo [detector-cache](detector-cache.md).
Không có manifest đúng hash/model/ảnh thì chỉ kiểm hình học/ngữ cảnh, không giả detector đã chạy.
