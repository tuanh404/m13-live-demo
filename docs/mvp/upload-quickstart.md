# Kiểm tra bộ ảnh của tôi

1. Mở màn bắt đầu, chọn **Kiểm tra bộ ảnh của tôi**. Không cần cài CVAT/extension.
2. Tải **gói mẫu3ảnh**, hoặc chuẩn bị ZIP ảnh và nhãn YOLO.
3. Chọn ZIP rồi bấm **Kiểm tra bộ ảnh**; lỗi/retry hiển thị trên trang.
4. Bấm **Review bộ vừa kiểm**, đối chiếu ảnh/nhãn/nghi vấn và chọn ba kết luận.
5. Mở **Bộ ảnh của tôi** để tiếp tục, reload/restart không mất kết quả.

ZIP tối đa5MB,1–10ảnh JPG/PNG1280×720; mỗi ảnh cần một nhãn YOLO bbox .txt tương ứng.
**Tự nhận trực tiếp, không cần sắp lại ZIP:**

- CVAT YOLO1.1: obj.names + obj_train_data/ (hoặc obj_valid_data/) chứa ảnh/nhãn;
  obj.data, train.txt và valid.txt được nhận nhưng không dùng để đọc URL/đường dẫn ngoài ZIP.
- YOLO Detection/Ultralytics: images/ + labels/ + classes.txt hoặc data.yaml/data.yml (names).
  Nhận images/train/ + labels/train/, train/images/ + train/labels/ và val/valid/test tương tự.
- Nhận một thư mục bọc ngoài; ảnh đuôi viết hoa và tên Unicode/khoảng trắng được chuẩn hóa ID nội bộ,
  giữ tên/đường dẫn gốc và hash trong provenance. Không tự sắp xếp lại chỉ số lớp.

ZIP chỉ có nhãn được báo thiếu ảnh cụ thể; tool không khôi phục được ảnh gốc từ nhãn.
COCO JSON, CVAT XML, VOC, polygon/segmentation/OBB chưa được nhận. Không phải ZIP nào cũng là YOLO.
Lớp trùng/mơ hồ, tên ảnh trùng giữa split và ảnh/nhãn không ghép đủ đều bị từ chối, không tự bỏ dữ liệu.
Tối đa500box/ảnh,5bộ/phiên; toàn kho100MB. Nhận10lớp BDD, alias person/motor/bike được chuẩn hóa.
Không tự resize tọa độ; ảnh được xuất JPEG cùng kích thước, provenance giữ hash nguồn và bản đã chuẩn hóa.
Định dạng gốc/phiên bản importer và bảng ghép ảnh–nhãn cũng lưu trong snapshot; batch cũ không đổi.

**Kiểm một phần:** dup_same_class, overlap_cross_class, size_outlier, crowded, many_tiny, rare_class.
Ngưỡng/trọng số lấy code/config có sẵn và freeze trong snapshot; không chạy edge_no_trunc vì YOLO thiếu
truncated. Không detector/Gemini/guideline, không suy đoán box lệch vật thể/missing object. Điểm0 vẫn có thể sai.
Size_outlier chỉ hoạt động khi đủ số box cùng lớp theo config; batch nhỏ không bảo đảm có nghi vấn.
Gói mẫu tổng hợp có clean/duplicate/overlap để kiểm luồng, không phải dataset/pilot người thật.

Snapshot/ảnh/queue/evidence được lưu trong state PostgreSQL hiện có, thư mục tạm chỉ là cache;
verdict dùng bảng append-only hiện có, state model/audit có namespace theo batch. Không đổi demoqueue.
Quyền gắn với phiên đăng nhập trình duyệt, hai phiên không đọc được nhau. Phiên review batch cố định,
tạo lượt demo mới không reset batch. Đăng xuất/hết hạn phiên rồi đăng nhập mới không tìm lại bộ cũ.
Cùng ZIP/profile/phiên retry mở lại batch cũ; không nhân đôi verdict khi mất ACK.

Cấu hình giới hạn riêng configs/upload.yaml. Chỉ endpoint upload có body limit5MB; API khác giữ32KB.
Không thêm dependency/framework hoặc dịch vụ phí; backup cloud hiện có chứa cả state/ảnh và verdict mới.
