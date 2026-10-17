# Dựng lại demo review M13

Chạy lệnh từ gốc repo. Hướng dẫn dùng cấu hình và ID của máy đang cài; không chép
DB, credentials hay mapping từ máy khác. Bằng chứng của từng phiên thuộc mô tả PR
và dữ liệu local, không thuộc tiến độ chung. Việc chưa merge chưa được tính Done.

## Extension trong CVAT: chỉ mở/đóng từ thanh công cụ Chrome

Bản0.4.5 dùng biểu tượng QC trên thanh công cụ Chrome, không tạo icon nổi trong CVAT.
Sau khi cập nhật source: vào `chrome://extensions` → Reload M13 → F5 tab CVAT.
Nếu chưa thấy QC trên thanh công cụ, dùng menu Extensions của Chrome để ghim M13.
Mở một job CVAT rồi bấm QC để hiện bảng, bấm lại chính nút đó để ẩn. Click/kéo trên
CVAT không tự đóng bảng; reload trang giữ trạng thái đã chọn. Không có nút đóng riêng
bên trong bảng. Có thể kéo cạnh trái để đổi độ rộng.

Chữ chính14px, thông tin phụ12px; ba nút **Có lỗi / Báo nhầm / Chưa rõ** cố định ở đáy bảng
(payload vẫn error/false_alarm/skip). Mở lần đầu chỉ cần nhập tên → **Bắt đầu**.
Sau đó chọn ảnh → đối chiếu nghi vấn → chọn kết luận; sửa nhãn thì Save trong CVAT
trước rồi bấm **Kiểm tra nhãn đã lưu**. Kết luận không tự sửa/lưu nhãn.
Đổi người dùng nút **Đổi người**; trong Thống kê phiên có **Bắt đầu lượt mới**,
luôn giữ lịch sử cũ. Khi còn kết quả chưa xác nhận, phải thử lưu lại trước.

**Phần dành cho người cài đặt:** cấu hình `review_batch`, `review_order`, `guideline_url`
ở `configs/review.yaml` hoặc biến môi trường `M13_REVIEW_BATCH`, `M13_REVIEW_ORDER`,
`M13_GUIDELINE_URL` của API. Backend cấp mã lượt và đóng băng lựa chọn này khi bắt đầu;
gửi lại sau lỗi mạng/restart vẫn nhận cùng lượt. Không đăng ký pilot qua bước nhập tên.
Extension cần biết đúng một địa chỉ để kết nối, do người cài đặt đặt trong
`extension/connection.json` trước khi đóng gói/nạp. Không điền secrets vào đó.
Tên, mã lượt và batch/order cũ được giữ khi nâng cấp. Địa chỉ API lấy từ bộ cài,
không còn bị URL cũ trong Chrome ghi đè. Ngoại lệ: verdict/recheck chưa xác nhận
vẫn gắn với dịch vụ ban đầu, không tự chuyển sang backend khác; cần phục hồi dịch vụ
cũ để xác nhận. Ảnh đã mở từ dịch vụ khác cần chọn lại trước khi lưu hoặc kiểm tra.
Địa chỉ guideline từ backend thay cho cấu hình cũ trên trình duyệt.
Khởi động lại API để nạp route mới `/review/start`, rồi Reload extension và F5 CVAT.
Người review không có form URL API, batch, mã phiên, thứ tự hoặc model; thông tin
provenance/phiên bản/hash vẫn giữ trong artifacts, DB và API dành cho kiểm chứng.
Backend còn tạo bản diễn giải để hiển thị: dùng “độ khớp 56% dưới 70%” thay IoU,
không đưa confidence detector lên trước người review. Lý do/evidence gốc giữ nguyên
để đối chiếu; đây chỉ là cách trình bày, không tính lại điểm hoặc sửa ngưỡng.

## Web review độc lập (L02)

Không cần Chrome extension, CVAT, Gemini key hoặc cấu hình URL API để thử giao diện.
Trong venv đã cài dependency `demo`, tạo batch riêng và mở web:

```bash
python -m src.cli review-fixtures --scored --count 10 --out data/web-demo
source data/web-demo/review/runtime.env
python -m src.cli serve --port 8000
```

Mở http://127.0.0.1:8000/ → chọn ảnh trong hàng đợi → xem box snapshot màu xanh,
vùng nghi vấn màu cam → **Lỗi thật / Bot nhầm / Bỏ qua** hoặc phím **1/2/3**.
Kết luận được lưu rồi tự sang ảnh tiếp; thống kê chỉ tính reviewer/phiên/snapshot
hiện tại. Ghi chú là tùy chọn; cấu hình và mã hash không xuất hiện trong màn hình review.
Tải lại trang giữ tiến độ; lỗi lưu có nút thử lại dùng cùng request ID để không trùng.
Không bấm kết luận được khi ảnh hoặc snapshot chưa tải/xác minh xong.

### Job đang mở trong CVAT

Extension nhận task/job từ tab CVAT, hiển thị tên phạm vi và chỉ lấy các ảnh có
mapping thuộc đúng job/server đó. Không đổi rank/điểm gốc hoặc sampling plan. Chọn
ảnh khác task bị chặn, mở job khác không phục hồi điểm/lựa chọn của job trước.
Job chưa chuẩn bị queue/mapping báo chưa có hàng đợi, không dùng fixture thay thế.
Mở một job bất kỳ không có nghĩa detector/pipeline tự chạy trên toàn bộ dữ liệu mới.

Ở môi trường local hiện tại, `extension/connection.json` trỏ API8006 phục vụ10ảnh BDD
của **http://localhost:8080/tasks/19/jobs/19**. Cấu hình chạy lại cho người cài đặt:

```bash
source data/mvp-cvat19-local/runtime.env
# Source tài khoản CVAT bằng môi trường riêng nếu cần Save/recheck, không in secrets.
python -m src.cli serve --port 8006
```

API8000/DB fixture cũ giữ nguyên để xử lý lịch sử/pending cũ; không xóa annotations
hay verdict. API8006 dùng DB/snapshots/rechecks riêng trong data/mvp-cvat19-local,
đọc ảnh/queue/predictions/mapping đã chuẩn bị ở data/mvp-live-deployment. Một máy
local vẫn chỉ là một máy đã kiểm. Khi cài máy mới, operator chuẩn bị queue/mapping
thật và đặt connection.json theo dịch vụ của máy đó.

Đây là fixture `edge_no_trunc`, không kiểm box ôm sát vật thể. Điểm là rủi ro,
không phải xác suất sai; 0 không bảo đảm đúng. Lỗi thật do người xác nhận; Bot nhầm
là không xác nhận nghi vấn sau khi đối chiếu; Bỏ qua là chưa kết luận và không tính
vào mẫu số tỷ lệ lỗi. Verdict không sửa nhãn. Số đo tự thử không phải pilot người thật.
Web có mục CVAT Save/recheck tùy chọn (L03); không cần chạy các bước CVAT bên dưới
chỉ để xem ảnh/ghi verdict. URL trên là local, chưa public (L05).

### Thử sửa và chấm lại (L03)

Với batch đã `review-connect`, API cần CVAT_USER/CVAT_PASSWORD trong môi trường
backend riêng, cùng runtime.env của đúng batch. Không nhập credentials trên web.
Mở mục **Sửa trong CVAT & kiểm tra lại nhãn đã Save**:

1. Bấm **Kiểm tra kết nối CVAT**, sau đó **Mở CVAT để sửa ảnh này**. Mapping được
   kiểm theo job/task/frame thật. Nếu CVAT offline/thiếu mapping, web review vẫn dùng được.
2. Sửa box và bấm **Save bên CVAT**. Đang kéo nhưng chưa Save thì backend vẫn thấy
   nhãn cũ. Quay lại tab web vẫn là ảnh đang review, kể cả tải lại trang.
3. Bấm **Đã Save ở CVAT → đọc nhãn đã lưu**; xem version, thời điểm và tọa độ vừa đọc.
   Overlay/điểm vẫn thuộc queue cũ ở bước này; web không biết canvas chưa Save.
4. Bấm **Kiểm tra lại từ nhãn đã Save**. Backend đọc lại nguồn và từ chối nếu nhãn
   đã đổi sau bước3. Chỉ thành công mới phục vụ queue/snapshot mới và hiển thị điểm mới.
5. Bấm **Xem lịch sử trước/sau**, chọn **Xem trước / Xem sau** để đối chiếu điểm,
   tọa độ và queue ID. Chọn verdict chỉ ghi kết luận, không tự sửa box.

Scored fixture chỉ kiểm box chạm mép thiếu truncated: box trái x1=0 có điểm50;
kéo cả box sang phải để x1>2, giữ truncated=false và Save rồi chấm lại thì về0.
Kéo lệch so với hình xe nhưng không chạm mép không làm tín hiệu này tăng điểm.
Mỗi lần chấm lại tạo phiên bản mới; retry/status giữ nguyên request ID, không nhân đôi.
Đồng hồ chỉ tính phần xem web có focus, pause khi mở CVAT cho tới lúc đọc Save;
thời gian sửa ở CVAT không nằm trong số đo này, không dùng nó làm số liệu pilot.

### Audit và export local (L03)

`review-prepare` tạo sampling plan từ queue gốc trước khi chọn10/30ảnh; metadata
giữ N/rank nguồn và policy. Batch đã tạo từ trước mà thiếu plan không được tự lấy
audit trong subset: giữ batch cũ, chuẩn bị thư mục mới từ queue gốc khi cần audit.
Recheck kế thừa plan gốc. Không có cờ audit trên giao diện người review.

```bash
# source runtime.env của đúng batch trước; dùng tên output chưa tồn tại
python -m src.cli review-audit-export --out data/audit-result.json
```

JSON/CSV giữ policy version, source queue/model/rank, counts, Wilson95% và trạng thái
chưa đủ mẫu. Error+false_alarm là mẫu số, skip báo riêng; dưới30 không suy rộng số lỗi.
Với10k ảnh,2000top+400audit=2400ảnh, tách chi phí audit khỏi recall@20% theo rank gốc.
Export fixture/tự động không phải pilot người thật.

### Kết quả baseline từ artifacts đã đóng băng (L04)

Trang `/results` đọc file `M13_EVALUATION_FILE` do operator cấu hình; người xem
không nhập đường dẫn. Nếu chưa cấu hình, trang báo chưa có kết quả. Ví dụ chạy lại
trên bộ artifacts local hiện có, chọn output mới nếu thư mục đã tồn tại:

```bash
python -m src.cli baseline-replay \
  --queue data/mvp-input-2018/reports/ranked_queue_rule-v1.2.csv \
  --bundle data/mvp-input-2018 \
  --answer data/mvp-input-2018/data/injected/injected_errors.json \
  --labels data/mvp-input-2018/data/injected/det_val_injected.json \
  --original-labels data/mvp-input-2018/data/bdd100k/labels/det_20/det_val.json \
  --out data/baseline-replay-new --split test
export M13_EVALUATION_FILE="$PWD/data/baseline-replay-new/evaluation.json"
# Giữ runtime.env của batch review đang dùng, rồi khởi động API khi cổng trống.
python -m src.cli serve --port 8000
```

Replay xác minh hash, split và đáp án từ các thay đổi nhãn; không chạy detector
hoặc training. Bảng và gain curve là **lỗi tiêm có đáp án**, không phải QC xác nhận
lỗi thật. `time_saved` là proxy giảm số ảnh để đạt cùng recall, không phải thời gian
người thật. Không đổi tham số dựa trên kết quả test.

Checklist đầu vào 10 ảnh (không thay thế kiểm runtime/người nghiệm thu):

```bash
python -m src.cli review-acceptance data/bdd-demo --count 10 \
  --exclude-batch data/pilot-source --out data/acceptance-check-new.json
```

Thiếu ảnh BDD gốc thì chỉ kiểm fixture riêng, ghi rõ loại dữ liệu. Không chia sẻ
ảnh pilot cho reviewer xem trước; không đưa verdict kiểm tự động vào số liệu pilot.

Kiểm web bằng browser sạch (không cần extension; Chrome hệ thống nếu có,
hoặc Chromium của Playwright):

```bash
uv pip install -e '.[dev,demo,browser]'
# Nếu không có Google Chrome: python -m playwright install chromium
M13_WEB_BROWSER_TESTS=1 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  python -m pytest -q tests/test_web_review.py tests/test_web_review_browser.py
```

Các DB/session trong browser tests là fixture tạm; không đăng ký pilot.

## 1. Môi trường và cấu hình máy

Trên máy mới có Python 3.11 hoặc 3.12 và uv:

```bash
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[dev,demo,guideline,browser]"
```

Máy đã có môi trường hoạt động chỉ activate/cập nhật dependency; không tạo lại
`.venv`. Chạy kiểm tra theo mục 8. Docker Engine và Compose chỉ cần cho CVAT.

Đặt URL/cổng theo máy của bạn. Các giá trị dưới là mặc định local dùng chung,
không phải ID/cổng của phiên nghiệm thu. Nếu bị chiếm, chọn cổng khác.

```bash
export M13_CVAT_URL=http://localhost:8080
export M13_API_PORT=8000
```

Extension chỉ hỗ trợ HTTP localhost/127.0.0.1. CVAT thường định tuyến theo hostname
`localhost`; dùng đúng hostname được cấu hình. API và CVAT là hai dịch vụ riêng.

Tài khoản CVAT đặt trong môi trường terminal chạy import/API. Có thể dùng file
riêng không nằm trong Git chứa `CVAT_USER` và `CVAT_PASSWORD`, rồi source file đó
với `set -a`/`set +a`. Không đưa mật khẩu vào lệnh, ảnh chụp hoặc package. Gemini
không cần cho demo fixture; key phục vụ guideline đọc từ môi trường riêng.

## 2. CVAT hiện có hoặc máy mới

Nếu đã có CVAT, giữ nguyên stack/volumes và đăng nhập ở `$M13_CVAT_URL`; bỏ bước dựng
mới. Nếu source bind mount đã mất, chỉ dùng `cvat-restore-source --out <source-dir>`
sau khi kiểm đúng đường dẫn nguồn; công cụ không ghi đè nội dung khác.

Trên máy mới, chuẩn bị bộ Compose ghim phiên bản từ `configs/cvat-install.yaml`.
Chọn project và cổng mới, khác stack đang dùng:

```bash
python -m src.cli cvat-prepare --out data/cvat-install
python -m src.cli cvat-preflight data/cvat-install --out data/cvat-preflight.json
docker compose -f data/cvat-install/docker-compose.yml config --quiet
```

Đọc `install.json` để lấy project/cổng thật. Chỉ khi quyền Docker, tài nguyên và
cổng cho phép mới chạy:

```bash
docker compose -f data/cvat-install/docker-compose.yml up -d
docker compose -f data/cvat-install/docker-compose.yml exec cvat_server \
  python manage.py createsuperuser
```

Sau đó đặt lại `$M13_CVAT_URL` theo cổng của bộ cài. Tài khoản tạo tương tác, không
lưu mật khẩu trong hướng dẫn. Không dùng `down -v`. Kiểm Compose không đồng nghĩa
đã dựng mới thành công. Bộ cài không phục hồi dashboard analytics đã mất.

## 3. Fixture: chạy UI và phép kiểm thật khi chưa có ảnh BDD

Chọn thư mục mới. Lệnh sau tạo 3 ảnh tổng hợp, nhãn, queue/evidence/manifest và gói
extension; không tạo detector predictions:

```bash
python -m src.cli review-fixtures --scored --out data/demo-qc --url "$M13_CVAT_URL"
python -m src.cli review-connect data/demo-qc/review \
  --url "$M13_CVAT_URL" --name m13-qc-fixture
```

Task mới và ID thật được ghi trong `data/demo-qc/review/review.json`. Tên task phải
chưa tồn tại; retry dùng cùng tên/task đã đăng ký, không ghi lại annotations.
Chạy lại `review-fixtures --scored` giữ DB/mapping/queue và từ chối nguồn đã sửa.

```bash
source data/demo-qc/review/runtime.env
python -m src.cli doctor --verify-cvat --out data/demo-qc/doctor.json
python -m src.cli serve --port "$M13_API_PORT"
```

Chỉ rule `edge_no_trunc` chạy trên ảnh tổng hợp, dùng tham số của config. Nó kiểm
chạm mép nhưng thiếu truncated; không kiểm box ôm sát hình chiếc xe. Ảnh đầu có
điểm dương. Sau khi kéo box rời mép, Save và QC lại thì điểm về 0. Đây không phải
nghiệm thu detector, guideline, BDD hoặc pilot.

`demo-prepare --image <JPEG/PNG>` là lựa chọn ảnh chưa có nhãn: queue
manual-unscored, không có điểm QC. `review-fixtures` không có `--scored` là fixture
UI cũ có predictions tổng hợp được đánh dấu; không dùng chúng làm detector thật.

Để kiểm công cụ demo/pilot trên hai tập không trùng ảnh, có thể tạo nguồn fixture
40 ảnh rồi chọn demo 10 ảnh và pilot 30 ảnh. Hai bộ pilot dùng cùng các tham số
lựa chọn và thư mục đầu ra riêng. Chúng vẫn là development, không đăng ký làm
human pilot:

```bash
python -m src.cli review-fixtures --scored --count 40 --out data/fixture-source --url "$M13_CVAT_URL"
python -m src.cli review-prepare --bundle data/fixture-source \
  --queue data/fixture-source/source/ranked_queue_rule-fixture-qc-v1.csv \
  --images data/fixture-source/images --out data/fixture-demo --limit 10 --url "$M13_CVAT_URL"
python -m src.cli review-prepare --bundle data/fixture-source \
  --queue data/fixture-source/source/ranked_queue_rule-fixture-qc-v1.csv \
  --images data/fixture-source/images --out data/fixture-pilot-a --pilot \
  --exclude-batch data/fixture-demo --url "$M13_CVAT_URL"
```

`--exclude-batch` đọc batch đã kiểm hash và loại ảnh đã dùng; có thể lặp tham số.
Nếu không còn đủ ảnh, công cụ báo lỗi thay vì lấy lại ảnh demo. CSV subset giữ
rank 1..N theo contract; `selection` trong manifest/review.json lưu rank gốc và
kích thước queue nguồn. Không dùng rank subset để kết luận top 20% của toàn batch.

## 4. 10 ảnh BDD khi đã có dữ liệu tương ứng

Lấy bundle nhóm đã chốt và thư mục ảnh BDD2018 tương ứng từ Sơn. Không thay bằng
ảnh khác hoặc đổi tên ảnh. Giải nén bundle vào thư mục mới:

```bash
python -m src.cli review-unpack <bundle.zip> --out data/input
sha256sum data/input/data/bdd100k/labels/det_20/det_val.json
```

Checksum nhãn phải là
`f7cde1a3bc064b2cbd2ffbcf58b29889e7396f4a4176fd17e3d93e08dfb4ff00`.
Đặt `M13_INPUT_IMAGES` đến thư mục ảnh trên máy; đường dẫn này chỉ nằm trong cấu
hình local. Queue mặc định `rule-v1.2` ở `configs/review_acceptance.yaml`. Nếu
Cường chốt queue khác, dùng `--queue` trỏ CSV cùng manifest và artifact tương ứng.

```bash
python -m src.cli review-prepare --bundle data/input --images "$M13_INPUT_IMAGES" \
  --out data/review-10 --limit 10 --purpose real --url "$M13_CVAT_URL"
python -m src.cli review-connect data/review-10 --url "$M13_CVAT_URL" --name m13-bdd-review
source data/review-10/runtime.env
python -m src.cli doctor --verify-cvat --out data/review-10/doctor.json
python -m src.cli serve --port "$M13_API_PORT"
```

Công cụ kiểm hash, ảnh 1280×720, đúng tập ID, evidence/features và labels snapshot.
Không tự tính lại điểm khi chuẩn bị; không thay snapshot bằng nhãn khác. Snapshot
đã tiêm lỗi được nhận diện khác nhãn gốc. Queue không có manifest không thể recheck.
Ghi bảng từng ảnh: image_id, frame/ảnh đúng, evidence đúng box, verdict lưu, timer,
Save/recheck, lỗi tích hợp. Chưa có ảnh thì bảng phải để chưa kiểm.

## 5. Chrome extension, QC và restart

Nạp thư mục `extension/` hoặc giải nén gói extension của batch. Trong
`chrome://extensions`: Developer mode → Load unpacked. Khi code đổi: Reload
extension **và reload trang CVAT**. Ghim icon QC trên thanh Chrome.

Mở job theo task/ID trong `review.json`. Bấm icon QC hoặc nút QC nổi để mở bảng;
bấm icon lần nữa hoặc nút đóng để đóng. Click ngoài, kéo box, Save/chuyển frame
không đóng bảng. Kéo cạnh trái bảng để đổi chiều rộng.

Bảng → ⚙: API `http://127.0.0.1:<M13_API_PORT>`, reviewer thật, session riêng, batch
trống, priority → Lưu. Chọn ảnh từ hàng đợi. Sửa → **Save trong CVAT** → **Kiểm tra
nhãn đã lưu**. Nút QC đọc tọa độ đã Save rồi chấm lại bằng backend; tạo version và
snapshot mới. Nhãn chưa Save bị bỏ qua. Backend thiếu/bị chặn thì báo lý do và giữ
điểm cũ. Điểm 0 chỉ là chưa phát hiện lỗi qua phép kiểm đang bật.

Ba verdict: Xác nhận lỗi/error, Cảnh báo nhầm/false_alarm, Bỏ qua/skip. Có chọn box
và ghi chú trong phần chi tiết. Phím 1/2/3 chỉ hoạt động khi focus trong bảng;
timer dừng khi focus bảng, sai frame hoặc mất focus cửa sổ/tab. Verdict không thay
Save nhãn, điều hướng ảnh không tự ghi verdict. Thống kê có trong bảng; API root
không phải giao diện, dùng `/docs` để kiểm API.

Restart bằng Ctrl+C trong đúng terminal API này rồi source lại cùng runtime.env
và chạy cùng lệnh serve. Không xoá DB và không chạy hai API cho cùng DB. Queue
active, version, snapshot và verdict phải còn sau restart. Với queue đã đổi, dùng
`/stats?queue_id=<snapshot-id>` để xem thống kê lịch sử.

## 6. Audit đã tích hợp theo định nghĩa Long (L03)

Policy `tail-outside-top-v1` lấy ngẫu nhiên 5% phần ngoài top20%, seed42,
chèn đều vào lượt ưu tiên. Plan đóng băng từ queue nguồn trước khi cắt batch;
không dùng lại `audit_every=10` từ nửa dưới. Xem mục audit phía trên và
[định nghĩa audit](dinh-nghia-audit.md). Không hiển thị cờ audit cho reviewer.

## 7. Pilot 30 ảnh: chỉ người thật mới đăng ký (L04)

Dùng [hướng dẫn pilot 30 ảnh](pilot-30.md) để chuẩn bị một source rồi tạo hai arm
priority/file từ cùng queue, ảnh và nhãn ban đầu. Mỗi arm có task/DB riêng và phải
kiểm/freeze nhãn CVAT trước khi giao người thật. Không dùng batch demo đã thao tác.

Reviewer mở `/pilot`, tự nhập tên và xác nhận chưa xem batch, rồi review đủ30ảnh
trong arm được giao. UI nhận đúng phiên/thứ tự tự động, có phản hồi sau lượt.
Hai người khác nhau, không xem trước ảnh hoặc làm cả hai lượt. Fixture bị chặn
đăng ký thành pilot người thật. CLI register/export/compare vẫn được tái sử dụng;
export chỉ lấy session human theo mặc định và từ chối ghi đè file.

Không coi thời gian kiểm tự động là số liệu pilot. Kết quả hai reviewer là mô tả,
có ảnh hưởng tốc độ từng người; chưa có mục tiêu chất lượng chung thì chưa báo
thời gian tiết kiệm đo thật. Bỏ qua không phải nhãn đúng.

## 8. Kiểm tra trước bàn giao

```bash
python .github/scripts/check_repo.py
ruff check .
pytest -q
playwright install chromium
M13_BROWSER_TESTS=1 pytest -q -rs tests/test_extension_browser.py tests/test_guideline_editor_browser.py
python -m src.cli extension-pack --out data/extension.zip
```

Browser tests dùng transport CVAT mock; muốn nghiệm thu runtime phải kiểm task
fixture mới hoặc batch BDD thực tế và ghi bằng chứng riêng. Thời gian cài, import
và review chưa được đo trên máy của người đọc. Không coi hướng dẫn là nghiệm thu
máy sạch; không coi môi trường cô lập trên cùng máy là máy thứ hai.
