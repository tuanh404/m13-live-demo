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
