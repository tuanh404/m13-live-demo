# M13 · Kế hoạch kiểm thử và bằng chứng L06

Môi trường: Python3.11.17, CVAT2.74.1 local, Chrome/Chromium thật, SQLite riêng từng job,
PostgreSQL14 test local và PostgreSQL17 Render(L05). Nhánh feat/tuanh-mvp-live-rebuild,
nền72b1e4c; working tree có diff, không dùng commit nền để khẳng định diff đã được CI remote kiểm.
Bản cập nhật17/10 có bằng chứng triển khai riêng trong data/mvp-final/. Không đọc secrets trong báo cáo.

## Chạy lại

```bash
source .venv/bin/activate
pytest -q -rs
ruff check .
python .github/scripts/check_repo.py
```

Browser opt-in trên máy hiện tại, không dùng profile Chrome cá nhân:

```bash
PLAYWRIGHT_BROWSERS_PATH="$PWD/data/runtime/playwright" \
M13_BROWSER_TESTS=1 M13_WEB_BROWSER_TESTS=1 \
pytest -q tests/test_web_review_browser.py tests/test_extension_browser.py \
  tests/test_job_intake_browser.py tests/test_web_cvat_browser.py \
  tests/test_deployment_browser.py tests/test_guideline_editor_browser.py tests/test_pilot_browser.py
```

Nếu chưa có Chromium, operator cài runtime theo Playwright trước, không đổi Python policy.
Test PostgreSQL bật M13_TEST_DATABASE_URL đến DB test riêng có quyền tạo DB tạm; mỗi test tạo/drop
đúng DB của nó. Không trỏ biến này vào DB CVAT, DB public hoặc DB chứa dữ liệu người review.
Kết quả cuối và fingerprint source ở `reports/mvp-verification.json`; log đầy đủ ở data/mvp-final/pytest-final.log (log L06 giữ nguyên làm lịch sử).

## Ma trận nghiệm thu intake

| Yêu cầu | Fixture/browser test | CVAT thật/local | Public |
|---|---|---|---|
|1.2job, job mới, tự chuẩn bị | test_job_intake_browser.py; registry chưa có job9/10 | Job20/21 mới ở lúc bắt đầu,3ảnh/job; UI Kiểm tra job này → queue | Không bật intake cho demo |
|2. Scope/mapping/switch | Cùng task,frame0/1,basename trùng; sai origin/task bị chặn |20↔21,reload đúng job; ảnh BDD/hash/mapping ID thực | Session tách, không dẫn localhost |
|3.3verdict/retry/restart | Lost ACK intake/verdict/recheck; request_id dedup, focus/timer |3loại verdict/job; restart giữ9rows/9request_id của3queue lịch sử | L05 giữ cookie/3verdict qua restart, review đủ10 |
|4. Canvas chưa Save và nguồn mới | stale409, history trước/sau; thất bại không activate | Native canvas drag/Save task20; chưa Save giữ tọa độ cũ, Save/recheck5,43→0; trước/sau đọc được | Chưa có CVAT public |
|5. Thiếu input/quyền/lỗi | Timeout,permission,deleted/frame-step,3D/size/rotation/tracks/tags/duplicate,missing spec/preds | Profile7geometry báo kiểm một phần | Role demo quản trị403, chưa auth401, Origin sai403 |
|6. Cache/resume | Cùng request dedup; request mới cùng input giữqueue/rows; ảnh cache hỏng refetch; source đổi invalidation | Hai job giữ history; cache/adapter có regression test; phát hành riêng17/10 | L05 immutable bundle hydrate/cache; không LLM online |
|7. UX không cấu hình | Browser form URL/model/batch vắng; lỗi mạng có retry | Toolbar mở/đóng bền, không floating QC; progress/status/3verdict | Một nút vào demo; không extension |

Job20/21 được provision MỘT LẦN trước lượt UI bằng bộ dữ liệu kiểm thử riêng. Không dùng CLI/import,
mapping hoặc đổi port giữa jobs. Chuỗi tương tác thật được tự động hóa bằng Playwright, toolbar dùng
handler Chrome thực trong headless. Đây không phải người mới tự dùng hoặc pilot người thật.

Lần chạy script kiểm đầu đã tạo2queue choA trước khi sửa cache; cả6rows còn giữ với request_id khác nhau,
3rows mỗi version. B có3rows. Không gọi các rows khác version là retry trùng hoặc xóa để làm đẹp số.
Sau recheckA, queue mới0/3 nghĩa là snapshot mới cần review; rows phiên bản trước vẫn còn.
Proof restart kiểm count=distinct request_id=6(A),3(B), không biến0/3 thành mất dữ liệu.

## Bằng chứng

- L06-real-CVAT-UI.json/png: hai job mới, switch/reload/3verdict.
- L06-real-CVAT-save-recheck.json/png; L06-unsaved-still-old.png: Save thật/history.
- L06-restart-preservation.json: API restart, rows riêng và hash tasks16/19 nguyên.
- L06-browser-targeted.log, L06-final-pytest.log: tests tại phiên này; không gọi log L05 là test mới.
- L05-public-browser.json/public-deployment.json/accepted-backup-proof.json: public acceptance, backup/restore,
  ghi timestamp L05 và không giả thành thao tác CVAT public.
- data/mvp-submission/asset-check.json:12trang PDF, thumbnail1600×900, nguồn chỉnh sửa.
- video-record.json: browser thật/phụ đề/thời lượng; các verdict trong video là demo tự động.

## Build, checker và các lỗi đã xử lý

Wheel build dùng `uv build --wheel`: thêm build-system setuptools/wheel tối thiểu vì môi trường
không có pip/setuptools ngầm. Kiểm wheel có web HTML/CSS/JS và job registry, không env/DB/secrets.
Wheel không chứa configs/dataset: phát hành bằng source bundle + cấu hình/backend artifacts,
cài editable trong repo; không quảng cáo wheel tự chạy standalone.

Repo checker chuẩn chạy trên tracked files; kiểm thêm các file source/docs mới theo cùng hàm check.
File lệnh cá nhân không thuộc gói source sản phẩm, vẫn giữ nguyên tại workspace. Binary MP4/PNG/PDF,
dataset, DB, profile browser và credentials chỉ ở data/ ngoài Git. Compose/Docker config L05 không đổi;
chưa có nghiệm thu clean container/máy thứ hai, không dùng build wheel thay bằng chứng đó.

Lỗi fixture browser đầu: thiếu headless_shell; đổi test dùng Chromium đầy đủ đã có, không bỏ test.
Login test5s không ổn khi máy chia tải: chờ15s phù hợp transport, vẫn giữ mọi assertion auth/isolation.
Lỗi intake mới: retry khi boot mất mạng, request mới trên nguồn không đổi sinh version thừa; đã sửa/test.

## Còn chờ

Usability người ít kỹ thuật chưa có người thử độc lập; overlay đã thu gọn tên, chờ người dùng feedback.
Pilot30×2reviewer, measured time_saved/recall lỗi thật, CVAT public,4máy và clean container chưa nghiệm thu.
Một test loader dữ liệu mặc định bỏ qua vì BDD không nằm ở đường dẫn mặc định; bộ40ảnh mirror và bundle
BDD đã kiểm riêng, không copy dataset vào Git để ép test qua. Các test pilot/approval chỉ dùng fixtures.


## Kiểm bổ sung17/10

- Explicit demo selection từ full population, chặn plan/scorer khác version, không thay queue cũ.
- Detector cache: hash/model/revision/conf/class-map, ảnh khác bytes cùng basename, empty predictions,
  hash sai, recheck giữ predictions. Những prediction trong unit test là fixture, không inference.
- Real PostgreSQL test: release mới vẫn đọc stats/snapshot cũ, cookie và lost-ACK retry; assets immutable.
- Public presentation whitelist PDF/PNG/MP4, source/secrets404, API review vẫn401 khi không đăng nhập.
- Team timing giữ10ảnh20/45phút và trạng thái chưa kiểm log; không tạo số lỗi/recall.
- Browser không extension: tên box tùy chọn, chọn box, laptop/retry và bảng kết quả tách biệt.

## Kết quả cuối release17/10

- Local full:276passed1skipped,129,27s; skip BDD ở path mặc định. Browser/MV3/PG flags bật.
- CI runtime bfb498e:276passed1skipped; log03-remote-ci-final.log, workflow39039111869.
- Public: /build đúng bfb498e,3verdict/lostACK/reload/auth/oldhistory đạt; redeploy và restart thật giữ3/10.
- Hai job20/21 được kiểm lại bằng UI, không ghi verdict hay sửa annotations; hash trước/sau khớp.
- Backup trước có20verdict, kiểm toàn bộ nội dung rows vẫn nguyên sau phát hành; demo tự động thêm6rows
  riêng cho nghiệm thu/video, không đưa vào pilot.
- MP4 encode137,92s, sửa drawtext expansion=none để dấu% không mất phụ đề, kiểm frame thực;
  browser ẩn danh phát được. Không dùng ffprobe vì máy không có; ffmpeg metadata kiểm riêng.
- PDF12trang không overflow, thumbnail1600×900. Whitelist3assets public, source/secrets404.
- Backup cuối restore vào DB local mới, kiểm assets/hash/verdict và vô hiệu hóa phiên đăng nhập cũ.
  Không restore lên production; database test sau probe được drop riêng.

## Bổ sung giao diện bắt đầu và chức năng khả dụng

- Entry layout riêng, không kế thừa grid205px của màn review. Kiểm1366/1024/768/390px, không tràn ngang.
- Guest auth/session lỗi có retry; mở demo lỗi không tự bật form mật khẩu. Đăng nhập tài khoản vẫn hoạt động.
- Chỉ quảng bá guest khi backend có tài khoản guest đúng role; không đổi auth/CSRF/ownership policy.
- CVAT chỉ hiện với người được phép và ảnh có mapping; không đưa URL nội bộ vào web review response.
  Test Save/recheck/history cũ vẫn phải đạt, không ẩn luôn chức năng local đang dùng được.
- Menu baseline/hồ sơ chỉ hiện khi API dữ liệu trả thành công, pilot chỉ hiện khi cấu hình/quyền phù hợp.
  Cả trang review và trang baseline đều chặn link pilot thừa trong chế độ demo.
- Bằng chứng bổ sung: data/mvp-ui-refresh/. Lượt test đầu phát hiện fixture thiếu guest account và
  /web/review cố ý không chứa mapping: đã sửa fixture và dùng boolean cvat_mapped riêng, giữ URL riêng tư.
  Chỉ kết quả targeted-fixed/full cuối được dùng cho nghiệm thu.


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


## Bổ sung18/10 · upload và media

Runtimec94265b: full local316passed1skipped, CI39057818496 xanh; browser/extension/PostgreSQL bật.
CVATYOLO1.1/Ultralytics: class order, source mapping/hash, traversal, thiếu ảnh, retry, ownership,
three-verdict/reload và restart đã kiểm. Bằng chứng data/mvp-yolo-import/.
Video mới quay chính runtime này; PDF12trang/không tràn, footer captions không che giao diện,
MP4≤180giây và link/hash/playback được kiểm riêng trong data/mvp-media-refresh/.
CI runtime cũ không được coi là CI riêng cho nội dung mỹ thuật mới; không đổi backend/API ở lượt media.
