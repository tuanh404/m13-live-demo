# M13 Reviewer Prioritization


**Mã nguồn dự án:** [tuanh404/m13-live-demo](https://github.com/tuanh404/m13-live-demo) · nhánh mặc định `deploy/render-free`.

**Trải nghiệm:** [Web live](https://m13-live-demo.onrender.com/login) · [Video125giây / slides12trang / thumbnail](https://m13-live-demo.onrender.com/submission).

Bản source này gồm backend, web, extension, công cụ dữ liệu/guideline/scoring/evaluation, cấu hình,
test và tài liệu. Dữ liệu ảnh/model, DB, phiên review, credentials và môi trường máy cá nhân được giữ ngoài Git.
Các ghi chú “private/local” trong nhật ký release17/10 bên dưới mô tả trạng thái trước khi công khai source18/10.
Repo nhóm không bị push/merge trong bước bàn giao này.

Trợ lý ưu tiên review nhãn detection 2D trên BDD100K. Thay vì QC review đều 100% ảnh, hệ thống chấm điểm rủi ro sai nhãn cho từng ảnh và xếp hàng đợi review, mỗi ảnh kèm 3 lý do tiếng Việt.

**Web demo cập nhật18/10:** https://m13-live-demo.onrender.com → **Trải nghiệm demo**.
Không cần extension/CVAT trên máy người xem. Dùng10ảnh BDD thật, queue/predictions đã đóng băng;
không phải inference/Gemini online hoặc pilot người thật. CVAT Save/recheck public chưa có.
**Hồ sơ mới:** [Video2phút05giây, slides12trang và thumbnail](https://m13-live-demo.onrender.com/submission).
Có luồng tải ZIPYOLO mới; [hướng dẫn](docs/mvp/upload-quickstart.md).
Render Free có thể cần khoảng1phút để thức dậy sau khi ngủ. Xem [triển khai và giới hạn](docs/deploy-mvp.md).

- **Dữ liệu:** BDD100K tập val, 10k ảnh, nhãn detection 2D
- **Chỉ số chính:** recall lỗi trong top 20% ảnh; thời gian review tiết kiệm
- **Nhóm:** Hoàng Mạnh Cường (lead), Long (BA), Tú Anh (BE), Sơn (BE)

**Tiến độ (cập nhật 13/10 tối):** [ai đã xong gì, ai làm tiếp, kết quả hiện có](docs/tien-do.md).

**Dành cho cả người không chuyên kỹ thuật:** [Hướng dẫn 10 việc cần làm: ai làm, làm thế nào, giao gì và khi nào tính là xong](docs/huong-dan-cong-viec-de-hieu.md).

**Cập nhật 13/10:** [Phân tích đề tài, hiện trạng các nhánh và phân công tiếp theo](docs/phan-tich-va-phan-cong-13-10.md) — gồm 4 sơ đồ SVG để chia sẻ với nhóm; ghi nhận phần API, CVAT, extension và guideline tools Tú Anh đã viết.

**Xem hệ thống qua một ví dụ cụ thể:** [Ảnh + guideline → LLM trích luật → detector/rule kiểm nhãn → hàng đợi review](docs/vi-du-xuyen-suot.md), có hai hình minh họa đầu vào và kết quả từng bước.

## Thử bộ ảnh của bạn ·18/10/2026

Mở [màn bắt đầu](https://m13-live-demo.onrender.com/login) → **Kiểm tra bộ ảnh của tôi**.
Tải gói mẫu ngay trên trang hoặc nhập nguyên ZIP YOLO1.1 từ CVAT/Ultralytics Detection;
không cần sắp lại thư mục. Tối đa10ảnh1280×720, ZIP5MB; cần có cả ảnh và nhãn.
Chạy6phép kiểm hình học/ngữ cảnh, không detector/guideline; điểm0 không bảo đảm đúng.
Bộ ảnh và verdict giữ riêng trong phiên login; reload/restart giữ tiến độ.
[Hướng dẫn và giới hạn](docs/mvp/upload-quickstart.md). CI bản upload316passed1skip;
source/runtime hiện ởrepo deploy riêng, không push/merge repo nhóm.

## Bộ bàn giao MVP · cập nhật 17/10/2026

[Video · Slides · Thumbnail công khai](https://m13-live-demo.onrender.com/submission).
Runtime 275330c, CI các bước đạt, workflow GitHub còn pending; local279passed1skipped.
Màn bắt đầu mới có CTA rõ, hỗ trợ laptop/mobile; menu chỉ hiện chức năng đang khả dụng.
Source bản mới: data/mvp-submission/M13-source-final.zip hoặc repo deploy private;
repo nhóm chưa chứa diff phát hành này. Chưa nộp BTC.

- [Hướng dẫn sử dụng](docs/mvp/quickstart.md) · [Phạm vi hỗ trợ](docs/mvp/support-matrix.md).
- [Kiến trúc hiện tại](docs/mvp/architecture.svg) · [Đặc tả/thiết kế](docs/mvp/spec-design.md).
- [Kiểm thử và ma trận nghiệm thu](docs/mvp/testing.md) · [Trạng thái13nhóm](docs/mvp/acceptance-status.md).
- [Pitch deck12slide mở bằng browser](docs/mvp/pitch.html) · [Nguồn thumbnail](docs/mvp/thumbnail.svg).
- [Kịch bản/video](docs/mvp/video-script.md) · [Nhật ký phiên16/10](reports/weekly-mvp-2026-10-16.md).
- PDF, PNG, MP4, source ZIP và submission manifest: `data/mvp-submission/` trên máy triển khai.
  Source ZIP là local/private; PDF/PNG/MP4 có đường chia sẻ `/submission` khi đã publish. Chưa nộp BTC. Không commit dữ liệu/video/DB/secrets.

Web public đã kiểm tại **https://m13-live-demo.onrender.com**. Repo nhóm public;
repo deploy riêng `tuanh404/m13-live-demo` giữ private. Bản sửa được phát hành riêng;
không commit/push repo nhóm. Commit/CI/live thực được ghi trong checkpoint bàn giao.
Không cần extension cho web public. Local intake hỗ trợ bbox1280×720/classes BDD, operator cấp quyền
server/task một lần; reviewer chỉ bấm nút. Chưa có public upload ảnh/nhãn mới hoặc CVAT public.

Baseline tái lập:2.000ảnh test/seed42, lỗi tiêm; recall@20% theo ảnh27,67%, random20,15%,
weighted30,99%. [Số liệu và provenance](reports/mvp-evaluation-summary.json).
Không phải recall lỗi thật hoặc time_saved đã kiểm log; pilot30×2reviewer còn chờ.
[Kết quả thời gian nhóm cung cấp](reports/team-timing.json) được trình bày riêng ở `/results`.
Hồ sơ video/slides/thumbnail công khai sau khi publish tại `/submission`; source mới giữ private/local.
Release demo mới lấy score/rank/evidence và audit plan từ cùng queue rule-mvp-original-v1
10.000 ảnh; giữ đúng 10 ảnh demo cũ. Audit chèn xen kẽ nên không phải mọi ảnh giảm dần theo điểm.
Recheck giữ lịch review gốc và tạo snapshot mới, không sửa baseline cũ.
Ảnh/nhãn BDD100K ©2018 The Regents of the University of California, dùng demo giáo dục/nghiên cứu;
[giấy phép](deployment/render/BDD100K-LICENSE.txt), provenance mirror/hash trong bundle ngoài Git.

Phần bắt đầu và sơ đồ đề xuất cũ bên dưới được giữ để tham khảo source nhóm;
để thử bản MVP hiện tại, ưu tiên quickstart/architecture ở trên.

## Bắt đầu

```bash
uv venv --python 3.11 && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest -q && ruff check .
```

Thành viên mới: đọc [CONTRIBUTING.md](CONTRIBUTING.md) để biết luồng, phân công, quy ước ghép code và quy trình hằng ngày.

## Thử web review local, không cần extension

Sau bước cài đặt, cài thêm Pillow và tạo batch tổng hợp riêng (không tải BDD hay gọi detector):

```bash
uv pip install -e '.[demo]'
python -m src.cli review-fixtures --scored --count 10 --out data/web-demo
source data/web-demo/review/runtime.env
python -m src.cli serve --port 8000
```

Mở **http://127.0.0.1:8000/**: xem ảnh, nhãn snapshot và nghi vấn → chọn **Lỗi thật / Bot nhầm / Bỏ qua** (phím **1/2/3**) → ảnh tiếp → thống kê. Không cần CVAT, URL API hay key để thử luồng này. SQLite giữ lịch sử sau khi khởi động lại; trình duyệt giữ phiên review. Nút tạo lượt demo mới nằm trong thông tin nâng cao, không xóa lịch sử.

Đây là **fixture**, chỉ kiểm `edge_no_trunc`, không chứng minh box bám đúng vật thể. Điểm 0–100 là mức rủi ro để ưu tiên, không phải xác suất sai; 0 không bảo đảm nhãn đúng. Cảnh báo detector cũng cần người xác nhận. **Lỗi thật**: người review xác nhận lỗi; **Bot nhầm**: đã đối chiếu và không xác nhận nghi vấn; **Bỏ qua**: chưa đủ thông tin, không tính vào mẫu số tỷ lệ lỗi. Verdict không tự sửa nhãn. Nhãn và evidence được đọc từ snapshot kiểm hash của queue, không lấy nhãn CVAT đang chỉnh.

Lệnh trên tạo URL local riêng; bản public ở link đầu README. Số đo tự thử/fixture không phải pilot người thật; `time_saved` trong đánh giá offline là proxy, chưa phải thời gian tiết kiệm đã đo.

Đã có mục **Sửa trong CVAT & kiểm tra lại nhãn đã Save** trên web: kiểm kết nối →
mở đúng task/job/frame → sửa và **Save trong CVAT** → quay về đọc nhãn đã lưu → kiểm
tra lại. Điểm/overlay chỉ đổi sau khi scorer chạy thành công trên nhãn mới; có lịch
sử trước/sau, queue cũ giữ nguyên. Nếu CVAT chưa sẵn sàng, vẫn xem ảnh và ghi verdict
trên web; không cung cấp link CVAT localhost cho URL web public. Backend API cần
CVAT_USER/CVAT_PASSWORD trong môi trường riêng cho luồng này, không nhập key lên web.
Đồng hồ web chỉ đo phần xem web có focus, không đo thời gian sửa trong CVAT.

Audit dùng5% phần ngoài top20%, seed42; freeze trên queue gốc trước khi cắt demo,
giữ rank nguồn và policy riêng. Với10k ảnh:2000top +400audit, tổng24%, không phải ngân
sách20%. Xem [định nghĩa và lệnh export](docs/dinh-nghia-audit.md).

## Baseline và pilot (L04)

Trang **`/results`** đọc `M13_EVALUATION_FILE` do backend cấu hình (file `evaluation.json`
từ `baseline-replay`), không yêu cầu người dùng nhập đường dẫn. Bảng/gain curve cùng split,
đáp án và hash; lỗi tiêm tách khỏi lỗi QC thật, proxy số ảnh tách khỏi thời gian đo từ người thật.
CLI `baseline-replay --help` kiểm nguồn nhãn/đáp án/artifacts trước khi đánh giá; không chạy
detector/training hoặc chọn tham số trên test. `review-acceptance --help` tạo checklist đầu vào,
không tự nhận có đủ file là đã nghiệm thu10ảnh BDD.

Trang **`/pilot`** là quy trình người thật tự đăng ký, giữ đúng arm/phiên/thứ tự và gửi phản hồi.
Ảnh pilot không xem được trước đăng ký; fixture không được đăng ký thành human pilot.
Xem [hướng dẫn pilot30ảnh](docs/pilot-30.md) cho operator và hai reviewer. Hiện chưa có dữ liệu
pilot người thật. Nhóm cung cấp kết quả cùng 10 ảnh: assisted20phút/manual45phút,
mức giảm tính từ hai số này55,6%; chưa đối chiếu log, không phải pilot30ảnh.

## Chạy pipeline

```bash
python -m src.cli load                                    # 1. đọc nhãn BDD100K
python -m src.cli inject                                  # 2. tiêm lỗi có đáp án
python -m src.cli rank --version rule-v0                  # 3–4. queue + evidence + manifest (thêm --preds/--spec khi có)
python -m src.cli evaluate --queue reports/ranked_queue_rule-v0.csv   # 7. so file order/random, gain curve
uvicorn src.api.main:app --reload                         # 5. API cho giao diện review
```

## Cấu trúc

```
configs/          tham số: paths, injection, weights, learning, class_map, batches, guidelines/
src/data/         loader BDD100K, tiêm lỗi
src/features/     tín hiệu rủi ro (hình học, detector, guideline) + SignalResult
src/guideline/    LLM đọc guideline -> spec YAML
src/scoring/      chấm điểm rule, GBM, học lại
src/eval/         metric, ghi reports/results.jsonl
src/api/          FastAPI hàng đợi + verdict
src/cli.py        điểm vào duy nhất
extension/        Chrome extension (side panel trong CVAT)
tests/            test + fixtures nhỏ, chạy không cần dữ liệu thật
docs/             đề xuất, tóm tắt dự án
reports/          báo cáo tuần, kết quả đánh giá
```

Dữ liệu, ảnh và model không đưa vào git; chia sẻ qua Drive.
