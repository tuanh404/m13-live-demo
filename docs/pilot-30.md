# Pilot 30 ảnh: chuẩn bị, chạy và đọc kết quả

Pilot cần **hai người khác nhau, chưa từng xem batch**, cùng30ảnh và nhãn ban đầu,
hai task/DB riêng. Agent chỉ chuẩn bị/kiểm công cụ, không đăng ký hoặc tạo số liệu người thật.
Hiện bộ local là **fixture**, đã freeze/readback CVAT nhưng không đủ điều kiện human pilot.

## Operator chuẩn bị khi có ảnh BDD gốc

Từ gốc repo, trong venv; dùng queue từ nhãn gốc, không dùng queue nhãn đã tiêm lỗi.
Các thư mục output phải mới. Không dùng lại batch đã thao tác demo.

```bash
python -m src.cli review-prepare --bundle data/bdd-bundle \
  --queue data/bdd-bundle/reports/ranked_queue_rule-v1.2-goc.csv \
  --images data/bdd-images --original-labels data/bdd-bundle/data/bdd100k/labels/det_20/det_val.json \
  --out data/pilot-source --pilot --purpose real --exclude-batch data/bdd-demo
python -m src.cli pilot-prepare-pair data/pilot-source --out data/pilot-pair \
  --original-labels data/bdd-bundle/data/bdd100k/labels/det_20/det_val.json
```

Source credentials CVAT vào môi trường backend riêng (không nhập trên web), rồi:

```bash
python -m src.cli review-connect data/pilot-pair/priority --url http://localhost:8080 --name pilot-priority
python -m src.cli review-connect data/pilot-pair/file --url http://localhost:8080 --name pilot-file
python -m src.cli pilot-check-pair data/pilot-pair --verify-cvat --freeze --out data/pilot-pair-check.json
```

Chỉ giao lượt cho người thật khi `setup_ready=true`, `human_eligible=true`. Checker giữ
N/rank/policy nguồn, cùng queue/nhãn/ảnh, mapping/task/DB độc lập và baseline nhãn Save.
Không freeze lại khi đã có đăng ký/verdict. Không sửa nhãn giữa hai lượt. Không chia sẻ
ảnh, bảng tọa độ hay link task CVAT cho reviewer xem trước. Thiếu ảnh/nguồn/mapping thì dừng pilot,
vẫn có thể kiểm công cụ bằng fixture và phải ghi rõ.

Hai terminal dùng cùng source code nhưng runtime/DB khác, bind local:

```bash
# Terminal người A (priority); môi trường có credentials CVAT backend
source data/pilot-pair/priority/runtime.env
python -m src.cli serve --port 8005

# Terminal người B (file); môi trường có credentials CVAT backend
source data/pilot-pair/file/runtime.env
python -m src.cli serve --port 8006
```

Mỗi người nhận đúng URL `/pilot` của arm được giao. Đây là local lab, chưa public URL;
không gửi địa chỉ localhost cho người dùng máy khác. Môi trường shared/live thuộc L05.

## Reviewer: thao tác trên giao diện

1. Mở `/pilot`, đọc hướng dẫn. Không mở ảnh trước hoặc làm lượt còn lại.
2. Tự nhập tên, xác nhận mình là người review thật, chưa xem batch, chỉ ghi verdict.
   Bấm **Đăng ký và bắt đầu**. Không dùng agent/script để bấm thay người trong pilot thật.
3. Xem ảnh/nhãn/nghi vấn, chọn **Lỗi thật / Bot nhầm / Bỏ qua** hoặc phím1/2/3.
   Note tùy chọn. Không sửa nhãn/CVAT trong lượt này.
4. Chờ thông báo đã lưu, tiếp tục đủ30ảnh. Có thể reload/retry, giữ nguyên phiên.
   Không đổi thứ tự hoặc tạo lượt demo mới. Nếu dữ liệu đổi hoặc API báo dừng pilot,
   báo operator; không ghi tiếp vào snapshot khác.
5. Điền độ rõ1–5 và góp ý sau lượt. Không tự diễn giải điểm0 là nhãn chắc đúng.

Đồng hồ chỉ đếm khi ảnh đã tải và web có focus, không tính chờ/tabẩn hay sửa CVAT.
Reload trước verdict bắt đầu lại đồng hồ ảnh đó; hạn chế reload khi đang đo và ghi lại
trong phản hồi nếu xảy ra. Đây là hạn chế đo thời gian cần công bố, không tự sửa số.

## Export và so sánh

Mỗi arm có runtime riêng. Dùng tên output chưa tồn tại:

```bash
source data/pilot-pair/priority/runtime.env
python -m src.cli pilot-export --out data/pilot-priority.csv
source data/pilot-pair/file/runtime.env
python -m src.cli pilot-export --out data/pilot-file.csv
python -m src.cli pilot-compare data/pilot-priority.summary.json \
  data/pilot-file.summary.json --out data/pilot-comparison.json
```

Export giữ append-only events, verdict cuối, skip, thời gian, policy/rank nguồn và feedback.
Session tự động/development không được trộn vào export human. `--include-development`
chỉ dùng debug riêng, không dùng làm kết quả pilot. Compare yêu cầu hai arm đủ ảnh,
hai reviewer, task/DB riêng, cùng baseline và time scope; partial export không phải pilot hoàn tất.

Báo mô tả lỗi/phút, giây/ảnh, chi phí review, số lỗi reviewer xác nhận trong những vị trí
review đầu; không gọi đó là recall nếu chưa có đáp án độc lập. `measured_time_saved` để trống
khi chưa định nghĩa mục tiêu chất lượng chung và dữ liệu hỗ trợ. Hai người có tốc độ khác nhau,
N30 nhỏ và có skip/bất đồng: không suy rộng chắc chắn cho toàn dataset.

## Bộ fixture hiện có của L04

- `data/mvp-l04-pilot-pair/{priority,file}`:30ảnh giống nhau, task14/job14 và task15/job15;
  DB riêng; không trùng demo10 ảnh L04/L01 đã loại trừ. Chưa có reviewer/human verdict.
- `data/mvp-handoff/L04-C-pair-check.json`: readback/freeze đạt nhưng `human_eligible=false`.
- UI/API chặn preview trước đăng ký và chặn fixture thành human pilot. Không cố đổi
  `M13_DATA_PURPOSE` hoặc tên version để biến fixture thành dữ liệu thật.
- `data/mvp-handoff/L04-A-runtime.json`: kiểm tự động10fixture/real CVAT, không phải pilot.
