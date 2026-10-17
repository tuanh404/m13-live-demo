# Cache detector cho job mới

Operator cấu hình `predictions_manifest` trong YAML intake một lần. Reviewer không nhập đường dẫn.
`null` là chỉ kiểm hình học/ngữ cảnh. Model không được tự đổi; không có Torch/Transformers/model
trên máy hiện tại nên phiên này không chạy inference mới hoặc tải model lớn.

Manifest JSON schema1 cần: `model`, `revision` (commit40ký tự), `confidence_floor` khớp
`configs/pipeline.yaml:detector`; `predictions_file` là Parquet nằm cùng thư mục manifest;
`predictions_sha256`; `class_map_sha256` là SHA256 JSON canonical của COCO→BDD map khi inference;
`images` ánh xạ image_id → SHA256 bytes ảnh gốc thực sự đã dùng cho inference;
`empty_image_ids` ghi những ảnh detector đã chạy nhưng không có prediction; `source` ghi provenance.
Parquet giữ contract hiện có, tối đa20MiB cho adapter batch nhỏ.

Hash ảnh phải được ghi khi chuẩn bị/chạy detector hoặc có chứng cứ nguồn tương đương. Không điền
hash của ảnh mới vào cache cũ chỉ vì basename giống nhau. Manifest do operator chịu trách nhiệm
về nguồn; kiểm hash/model là kiểm tính toàn vẹn, không tự chứng minh nguồn khai báo là thật.

Adapter kiểm model/revision/config, hash Parquet và từng ảnh CVAT trước khi lấy predictions.
Ảnh không khớp hoặc thiếu coverage: không dùng predictions và công bố kiểm một phần.
Cache sai model/hash/contract: báo lỗi, giữ queue cũ. Empty predictions phải được khai báo riêng;
không đánh đồng file thiếu với detector không thấy vật thể.

Manifest fingerprint nằm trong profile/request; sửa cache tạo cấu hình mới. Snapshot giữ predictions
subset riêng, hash và provenance; recheck nhãn đã Save tái dùng đúng predictions của snapshot.
Không suy diễn thiếu box/sai lớp chỉ từ tọa độ. Guideline thiếu duyệt vẫn không được thực thi.
Tests dùng predictions synthetic độc lập với box nhãn, không công bố là detector đã inference thật.
