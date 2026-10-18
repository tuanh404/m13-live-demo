# Nhật ký MVP17/10/2026 · Tú Anh

- Giữ nền72b1e4c, nhánh feat/tuanh-mvp-live-rebuild và diff L01–L06. Repo nhóm không Git mutation.
- Demo release mới giữ đúng10ảnh, dùng score/rank/evidence/audit từ full queue rule-mvp-original-v1
  10.000ảnh cùng config. Không đổi baseline lỗi tiêm hoặc queue/verdict cũ.
- Thêm selection tường minh, chặn initial plan/scorer khác version. Audit freeze trước crop.
- Intake thêm adapter detector cache, kiểm model/revision/conf/class-map/Parquet/hash ảnh/coverage;
  không có cache đúng thì kiểm một phần. Torch/Transformers/model chưa có, không inference mới.
- Backup DB public trước thay đổi; bundle immutable mới được nạp, số verdict20 không đổi;
  policy network DB tạm được khôi phục. CI/deploy/public kiểm riêng trước ghi nhận thành công.
- Kết quả nhóm cung cấp: cùng10ảnh,20phút assisted/45phút manual,55,6% tính từ hai số đó,
  chưa đối chiếu log/quy trình/ảnh hưởng nhớ ảnh; không biến thành30ảnh đã đo.
- Overlay thu gọn tên box, vẫn có danh sách/chọn box và tùy chọn hiện tên; browser kiểm kỹ thuật,
  chưa người mới dùng độc lập. Người dùng sẽ feedback sau bàn giao.
- Hồ sơ PDF/PNG/MP4 có đường publish immutable qua Postgres hiện có, chỉ whitelist3file;
  sourceZIP/private repo không tự công khai. Không nộp BTC thay người dùng.
- Bằng chứng mới: data/mvp-final/; reports/mvp-verification.json và checkpoint ghi kết quả cuối.
  Lượt test sandbox bị treo TestClient được dừng; chạy môi trường có socket. Role DB test khôi phục
  được xác minh là m13test; các lần chạy sai role không được ghi thành test đạt.

## Bàn giao phát hành

- Runtime bfb498e; CI đúng commit276passed1skipped. Local276passed1skipped129,27s; Ruff/checker sạch.
- Bổ sung regression cùng-disk restart: hydrate history theo fresh artifact root; trước/sau deploy/restart
  public vẫn3/10, duplicate retry đúng1row, history/auth/isolation đạt.
- Hai task20/21 UI kiểm lại, annotations hash không đổi. Không chạy detector mới hoặc duyệt guideline.
- Video mới137,92s; sửa lỗi drawtext ký tự% khi kiểm frame, mã hóa lại từ raw quay thật, không dựng cảnh.
- Video/PDF/PNG publish immutable vào Postgres hiện có và kiểm ẩn danh. Source mới giữ private/local;
  manifest chỉ ghi URL thực, không gọi repo nhóm cũ là bản source mới. Không nộp BTC.
- Ngân sách0: không tạo/nâng gói dịch vụ. Mọi lần mở DB từ local chỉ CIDR operator và khôi phục policy.


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
