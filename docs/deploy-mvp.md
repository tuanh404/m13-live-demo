# Deploy M13 web/API và kiểm staging

Source repo nhóm ở nhánh việc, chưa commit/push. Bản deploy riêng được người dùng cho phép
push vào repo private https://github.com/tuanh404/m13-live-demo, nhánh deploy/render-free.
Dùng đúng source đã kiểm; không tự merge repo nhóm.
Web review không cần extension hoặc CVAT cho người trải nghiệm. CVAT Save/recheck là
chức năng operator, cần backend credentials và mapping đúng máy. Không nhập key vào web.

## Public đã nghiệm thu ngày16/10

- URL **https://m13-live-demo.onrender.com**. Mở bằng browser thường hoặc ẩn danh,
  bấm **Trải nghiệm demo**, xem ảnh/nhãn/nghi vấn rồi chọn **Lỗi thật / Bot nhầm / Bỏ qua**.
  Mỗi lần chọn lưu kết luận và chuyển ảnh; thống kê riêng cho lượt của bạn. Phím1/2/3 tương ứng.
- Web Free srv-db8udds9v7es73dtr770 và Postgres17 Free dpg-db8rg53bc2fs73bu9kug-a,
  Singapore, trong project M13. Commit phục vụ65f1c44a3429f8304e9348363d8667dbe34d9386,
  CI https://github.com/tuanh404/m13-live-demo/actions/runs/38884395867 xanh.
-10ảnh BDD thật có hash; nhãn/predictions cache và4signals bất đồng detector tính trước.
  Không chạy detector/Gemini/training trên Render; không có CVAT public. Baseline trên trang kết quả
  là lỗi tiêm có đáp án, time_saved là proxy; chưa phải số đo pilot người thật.
- Chrome sạch1366×768 đã kiểm ảnh/nhãn/evidence,3verdict, mất ACK→retry không trùng,
  reload,2phiên cô lập, route quản trị403 và CSRF. Restart thật đã kiểm giữ cookie/session/verdict.
  Health200 và queue còn đủ10ảnh sau khi đóng external DB access. Session tự động không tính pilot.
- Immutable assets và lịch sử/session nằm trong Postgres; hydrate kiểm hash sau restart/mất disk.
  Backup sau nghiệm thu đã restore vào DB local riêng:22assets,10verdict test,0login session được phục hồi.
  File backup riêng mode0600, ngoài Git. Không backup/restore đè stack CVAT.
- Free web ngủ sau15phút không truy cập, lần mở đầu có thể mất khoảng1phút.
  DB này hết hạn **15/11/2026**; phải backup/chuyển DB trước hạn để dùng tiếp.
  Tham khảo [giới hạn Render Free](https://render.com/docs/free). Không bật gói trả phí.
- Bằng chứng local: data/mvp-handoff/L05-public-deployment.json,
  L05-public-browser.json, L05-accepted-backup-proof.json; ảnh L05-public-review.png,
  L05-public-after-restart.png, L05-public-completed.png. Không chứa cookie/API key.

Giới hạn cần giữ khi bàn giao: lịch xem tiếp tục theo audit plan của queue nguồn đã freeze,
điểm hiển thị thuộc snapshot kiểm hiện tại; có thể không giảm dần theo điểm mới. Không đổi policy,
rank nguồn hoặc baseline trong L05. Trước khi khẳng định đang xếp lại theo scorer mới, cần thống nhất
việc tạo full-batch queue/plan mới; giữ nguyên lịch sử phiên cũ. Ảnh nhiều box vẫn dày chữ;
laptop nhỏ có thể cần cuộn. Chưa đánh giá usability với reviewer mới.

## Những gì đã kiểm trên máy này

- 40 ảnh BDD từ mirror Hugging Face ghim revision, LFS SHA256/filename/JPEG1280×720
  đã khớp:10demo và30pilot không trùng. Có provenance local; chưa có checksum ảnh chính thức.
- Demo dùng baseline mới `rule-bdd-live-v1`,4 tín hiệu detector-disagreement, cached predictions,
  ngưỡng được lưu đầy đủ. Không chạy detector/training mới hoặc Gemini. Queue cũ giữ nguyên.
- HTTPS local **https://127.0.0.1:8445/** → Caddy → API127.0.0.1:8005, SQLite riêng.
  Đăng nhập, cô lập phiên,10ảnh/3verdict, retry/restart; CVAT API Save/recheck task19 riêng.
  Các verdict kiểm tự động không phải kết luận QC/human pilot.
- Caddy dùng CA nội bộ; chưa cài CA vào hệ thống. Đây là staging local, không phải URL
  public có chứng chỉ được mọi trình duyệt tin cậy. API8000 và CVAT8080 cũ giữ nguyên.
- Compose/Caddy configuration đã kiểm. Chưa build/chạy container mới vì thiếu quyền
  Docker daemon. Chưa nghiệm thu máy thứ hai hoặc CVAT live; public native Render đã kiểm riêng ở trên.

Tài khoản được tạo riêng, mật khẩu ngẫu nhiên; mở file local `data/mvp-live-deployment-access.txt`
bằng editor để xem. Không đưa file này vào package, Git, log hoặc screenshot. Operator là
tài khoản quản trị; chỉ cấp tài khoản `demo` cho người trải nghiệm.

## Bật lại staging khi đã dừng

Chỉ chạy nếu các cổng trên đang trống. Từ gốc repo, dùng venv đã cài, không tạo lại môi trường.
Credentials CVAT chỉ source cho backend nếu cần kiểm Save/recheck local:

```bash
source .venv/bin/activate
set -a
source data/cvat-runtime/account.env
set +a
source data/mvp-live-deployment/runtime.env
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  python -m src.cli serve --host 127.0.0.1 --port 8005
```

Terminal khác, Caddy binary đã kiểm checksum nằm trong data/runtime (không nằm trong Git):

```bash
export XDG_DATA_HOME="$PWD/data/runtime/caddy-state"
export XDG_CONFIG_HOME="$PWD/data/runtime/caddy-config"
data/runtime/caddy/caddy run --config deployment/mvp/Caddyfile.staging --adapter caddyfile
```

Mở HTTPS staging; chỉ bỏ qua cảnh báo CA nội bộ khi tự kiểm đúng localhost này.
Không hướng dẫn người chấm bỏ qua chứng chỉ của public URL.

## Chuẩn bị bộ chạy trên máy đích

Máy cần Python3.11/3.12 để chạy tooling; Docker Engine/Compose nếu dùng container.
Dockerfile ghim base digest, dependencies trong requirements.lock, Caddy ghim2.11.7;
nguồn ở deployment/mvp/provenance.json. Hiện chỉ runtime native x86_64 được kiểm.

Với batch đã chuẩn bị ở máy đích, tạo deployment **mới**:

```bash
python -m src.cli deployment-prepare data/bdd-demo --out data/live-demo \
  --origin https://review.example.org \
  --original-labels data/bdd-bundle/data/bdd100k/labels/det_20/det_val.json \
  --evaluation data/baseline/evaluation.json
```

Thay hostname/đầu vào bằng giá trị thật. Lệnh không publish và không ghi đè folder/DB.
Sinh accounts.json chỉ chứa hash; file mật khẩu nằm ngoài deployment. Mỗi lần đăng nhập có
reviewer/session riêng do server cấp, refresh giữ phiên; nút lượt mới giữ lịch sử cũ.
Demo không được gọi retrain/rollback/CVAT/pilot; API cũng được bảo vệ, không chỉ giao diện.
Các route ghi kiểm Origin; cookie HttpOnly/Secure/SameSite, password PBKDF2 và giới hạn đăng nhập.

Nếu cần CVAT, import/sinh mapping **trước khi chạy API lần đầu** trên deployment mới:

```bash
# Credentials CVAT ở môi trường backend riêng; không đưa vào container.env/account demo.
python -m src.cli review-connect data/live-demo --url https://cvat.example.org --name live-demo-10
```

URL CVAT phải khớp URL đã chọn khi chuẩn bị batch. Không chép task/job/frame của máy khác.
Không dùng CVAT localhost làm link cho người chấm public. Nếu không có CVAT phù hợp,
demo core vẫn chạy; không công bố Save/recheck live đã đạt.

## Docker: validate, build, start, rollback

```bash
bash deployment/mvp/manage.sh validate data/live-demo/compose.env
bash deployment/mvp/manage.sh build data/live-demo/compose.env
bash deployment/mvp/manage.sh start data/live-demo/compose.env
```

Đây là lệnh operator chạy khi có quyền Docker, không phải bằng chứng đã dựng container.
Mặc định bind127.0.0.1 để tránh công khai ngoài ý muốn. Trước public cần được cấp máy/quyền,
DNS hoặc hostname của nhà cung cấp, HTTPS443 và HTTP80 cho ACME; chỉnh compose.env
`M13_BIND_ADDRESS`, `M13_HTTPS_PORT`, `M13_HTTP_PORT`, origin/site đúng hostname thực.
Không cần domain mua riêng nếu nhà cung cấp đã cấp hostname phù hợp.
API không publish cổng trực tiếp; proxy cùng origin chuyển cả web/API, không CORS wildcard.

Data bind mount riêng tồn tại qua container restart, TLS state ở volumes của project riêng.
UID/GID trong compose.env phải đọc/ghi được deployment của operator; không chmod777.
Healthcheck, restart-unless-stopped, log rotation, read-only root filesystem được khai báo.
Nếu dùng CVAT mới, tái dùng `cvat-prepare` và source chính thức2.74.1 trong deployment/cvat;
project/ports/volumes phải riêng. Chưa được chạy fresh stack trong phiên này. CVAT router,
đăng nhập, websocket và đường task phải nghiệm thu trên hostname đích trước công bố.

Chỉ rollback image đã build/kiểm sẵn và tương thích DB; backup trước:

```bash
bash deployment/mvp/manage.sh rollback data/live-demo/compose.env m13-demo:previous-tested
# Dừng demo nếu cần; không xóa volumes và không đụng project CVAT.
bash deployment/mvp/manage.sh stop data/live-demo/compose.env
```

## Backup/restore và mang dữ liệu sang máy khác

```bash
python -m src.cli deployment-backup data/live-demo --out data/backup-new
python -m src.cli deployment-restore data/backup-new --out data/restored-demo \
  --origin https://review.example.org
```

Output phải mới. Backup dùng SQLite online backup, giữ verdict/state và snapshot artifacts,
kiểm hash trước restore. Loại accounts.json, plaintext credentials và cấu hình container
riêng khỏi backup. Restore sinh tài khoản mới và vô hiệu hóa cookie đăng nhập cũ, chuyển
đường dẫn về folder mới, giữ lịch sử. Các file này là dữ liệu private, không commit Git.

Mapping CVAT cũ được cách ly thành `cvat_map.previous-host.parquet`, không tự liên kết
task máy mới. Restore core không đồng nghĩa restore CVAT. Khôi phục CVAT cần backup
DB/annotations/volumes của chính stack đó và xác minh lại mapping; chưa chạy thao tác này.
Không dùng `down -v`, không restore đè DB/task đang dùng. Giữ deployment cũ để rollback.

## Checklist trước khi báo public live

1. Browser ngoài máy phát triển truy cập HTTPS, chứng chỉ tin cậy; chưa login không đọc được ảnh/API.
2. Login demo, queue/ảnh/nhãn/evidence đúng,3verdict, stats, reload/retry không trùng.
3. Hai browser độc lập không đọc/ghi lượt của nhau; demo gọi route quản trị bị403.
4. Restart service giữ DB/login/history; backup/restore vào folder mới được kiểm.
5. Không có URL localhost của developer hoặc credentials trong frontend/package/log.
6. CVAT link/Save/recheck chỉ ghi đã đạt khi kiểm hostname/task/frame thật của môi trường đó.
7. Tách dữ liệu demo/pilot, không dùng automatic events làm kết quả người thật.

Khi chưa có máy đích/quyền/public URL, trạng thái vẫn **local staging verified**, không ghi
Live URL đã hoàn thành. Pilot30 người thật xem docs/pilot-30.md; số20/45phút trên10ảnh do
người dùng báo giữ riêng, số30ảnh ngoại suy và verdict mô phỏng không phải kết quả thực nghiệm.

## Render Free — bản deploy riêng của Tú Anh

Repo deploy: https://github.com/tuanh404/m13-live-demo (private), nhánh `deploy/render-free`.
Bản checkout local nằm ở `data/mvp-handoff/m13-live-demo-repo`; đây là repo riêng,
không phải worktree/remote của repo nhóm. Không push/merge repo nhóm để deploy.

Project đích: https://dashboard.render.com/project/prj-db8r7l2vcj2c73au8oag.
Postgres `m13-demo-db` đang dùng plan Free, cùng region Singapore. Không tạo DB Free
thứ hai trong workspace hoặc bật storage autoscaling/gói trả phí. Free DB hiện hết hạn
15/11/2026; cần xuất backup trước thời điểm đó nếu tiếp tục dùng dữ liệu.

Ảnh, queue, evidence và manifest được nạp thành bundle immutable trong Postgres,
cùng nơi lưu verdict/state. Khi Render mất ephemeral disk, app hydrate lại assets và
kiểm SHA256 từ database; không phụ thuộc laptop hoặc tải lại mirror trong mỗi cold-start.
Không commit dataset/ảnh/DB/accounts/.env/key vào Git. Không dùng SQLite ephemeral
làm kho kết quả trên Render Free. Đồng thời giữ SQLite mặc định cho bản local cũ.

Các lệnh operator từ gốc repo (database URL chỉ ở môi trường backend):

```bash
python -m src.cli render-bundle data/mvp-bdd-live-demo \
  --out data/render-bundle-new \
  --acquisition data/bdd-mvp-original-images/acquisition.json \
  --evaluation data/mvp-handoff/L04-baseline-final/evaluation.json
python -m src.cli render-upload data/render-bundle-new
python -m src.cli render-backup --out data/render-backup-new.private.json
# Chỉ khi M13_DATABASE_URL trỏ DB mới trống, không dùng trên DB đang phục vụ:
python -m src.cli render-restore data/render-backup-new.private.json
```

Đầu ra phải mới, hash đúng; restore chặn DB có bảng/dữ liệu và vô hiệu hóa cookie đăng nhập cũ.
Backup chứa lịch sử riêng, file0600, phải giữ ngoài Git. Các integration tests backup/restore
đã chạy PostgreSQL thật riêng; không tự restore lên DB public đang phục vụ.

Cấu hình dựng lại nằm ở `deployment/render/render.yaml`, dependencies ghim trong
`deployment/render/requirements.lock`. Web/API cùng origin, Python3.11.17,1worker,
health `/health`; auto-deploy tắt. Render tự cung cấp HTTPS và restart service.
`M13_DATABASE_URL` dùng Internal Connection String của DB cùng region,
`M13_AUTH_SECRET` là secret ngẫu nhiên của server, `M13_DEMO_BUNDLE_ID` là ID bundle đã nạp.
Không đổi secret khi restart nếu muốn giữ phiên đăng nhập; chỉ rotate khi chủ động vô hiệu hóa phiên.

Start command của Render:

```bash
python -m uvicorn src.api.render_app:create_render_app --factory \
  --host 0.0.0.0 --port "$PORT" --workers 1 --no-access-log
```

Người trải nghiệm bấm **Trải nghiệm demo**; server cấp cookie HttpOnly/Secure và lượt riêng.
Không phải nhập API URL/key hoặc tài khoản CVAT. Chưa vào demo thì API/ảnh bị chặn;
role demo không được đọc/khởi chạy intake job, recheck, retrain, rollback hoặc pilot.
Cấu hình kỹ thuật và credentials đều ở backend. CVAT local **chưa phải CVAT public**,
nên không công bố sửa/Save/recheck nhãn qua live URL; core review web vẫn sử dụng được.

GitHub App Render cần được cấp quyền đọc riêng repo `m13-live-demo` bằng Configure
Repository access tại https://github.com/apps/render/installations/new. Chỉ có OAuth CLI
không đồng nghĩa Render Git provider đã được cấp repo mới. Giữ quyền các repo cũ.
Sau khi kết nối, deploy commit đã có CI xanh; kiểm browser ngoài và restart trước ghi nhận Live URL đạt.

Free web ngủ sau15phút không truy cập, đánh thức khoảng1phút. Không có cam kết uptime24/7;
không dùng ping giả để quảng cáo dịch vụ luôn thức. Các giới hạn/quota khác xem Render Free docs.
Rollback chỉ tới commit đã kiểm và bundle/schema tương thích, backup trước đổi schema.
Chặn external DB access sau nạp/kiểm; khi cần backup local, operator cho phép đúng IP của mình
trong Database → Networking, dùng External URL ở backend rồi thu hồi quyền tạm sau khi xong.

## Release17/10 · cập nhật không mất lịch sử

Demo mới ở `data/mvp-bdd-consistent-demo`, giữ10ảnh cũ và lấy điểm/evidence/rank/plan từ
full queue rule-mvp-original-v1 (10.000ảnh). Tạo qua `review-prepare --include-batch`;
không sort frontend hoặc dùng plan rule-v1.2-goc cho scorer khác.

Trước deploy: backup DB riêng tư0600; append immutable bundle; giữ nguyên M13_AUTH_SECRET.
Đổi M13_DEMO_BUNDLE_ID sang bundle mới và cấu hình M13_PREVIOUS_DEMO_BUNDLE_IDS là JSON
array ID bundle trước. App hydrate các snapshot lịch sử và đăng ký version/path mới sau restart;
verdict cũ không chuyển sang queue mới, stats cũ vẫn đọc theo queue_id và đúng session.
Lost-ACK đã commit vẫn trả duplicate; verdict chưa commit cho queue cũ được409 và cần đối chiếu lại.
Rollback dùng commit65f1c44 và bundle cũ đã lưu, không restore đè DB/đổi secret/xóa bundle mới.

Video/PDF/thumbnail có namespace immutable riêng trong Postgres. Operator gọi hàm
`src.api.submission.publish_assets(Path('data/mvp-submission'))` bằng môi trường backend đã cấp quyền,
không có endpoint ghi từ trình duyệt. `/submission` công khai đường xem ba artifacts;
source ZIP/secrets không được phục vụ. Upload mới đổi pointer nhưng URL có hash cũ vẫn giữ.
Chỉ cập nhật schema append-only hiện có; không thêm dịch vụ lưu trữ hoặc chi phí.

Nếu thao tác DB từ máy local, chỉ mở tạm đúng CIDR IP operator rồi khôi phục allowlist ban đầu
trong finally; không mở0.0.0.0/0. Mọi credential chỉ ở môi trường/file private0600 ngoài Git.
CI/deploy/bằng chứng public mới ở data/mvp-final, không lấy CI L05 làm CI cho bản sửa này.
