# M13 · Đặc tả và thiết kế MVP

Phiên bản tài liệu:6-lenh-v1 / cvat-job-intake-v1 / L06 + release17/10/2026.
Sản phẩm hỗ trợ QC ưu tiên ảnh có nguy cơ sai nhãn, kèm lý do và evidence. Người review
xác nhận; tool không tự kết luận, tự sửa annotation hoặc coi verdict là Save.

## Hai đường sử dụng

| Đường chạy | Đầu vào | Người dùng làm gì | Khả năng hiện tại |
|---|---|---|---|
| Public Render |10BDD thật, nhãn/predictions/queue đã freeze | Trải nghiệm demo → đối chiếu →3verdict → stats | Không extension/CVAT, không upload batch mới |
| Local CVAT | Task/job được operator cấp quyền; bbox1280×720, classes BDD | Mở job → biểu tượng Chrome → Kiểm tra job này → queue |7checks hình học/ngữ cảnh, báo kiểm một phần |

Ảnh BDD demo có provenance mirror/revision/LFS SHA256, chưa đối chiếu checksum ảnh chính thức.
Local nghiệm thu job20/21 dùng ảnh BDD nhưng nhãn fixture kiểm phần mềm; không dùng làm ground truth.

## Contracts và nguồn kiểm

- `SignalResult`: value0–1, lý do tiếng Việt có số; không đổi contract.
- `yolo_preds.parquet`: image_id,x1,y1,x2,y2,category,conf. Predictions phải từ detector độc lập
  trên đúng ảnh. Không lấy nhãn chuẩn đóng vai detector.
- `ranked_queue_*.csv`: image_id,risk_score,rank,top_reasons,model_version; risk0–100,
  tối đa3reasons. Evidence/labels/features/manifest là artifacts riêng kiểm hash.
- Public demo:4signals model_missing_label,model_class_conflict,model_loose_box,label_unsupported
  với cached RT-DETR predictions; rule-mvp-original-v1. Không inference/Gemini/training online.
- Intake:7signals trong configs/job_intake.yaml, scorer rule được chọn rõ. Thiếu spec/detector phải hiển thị kiểm một phần. Detector cache tùy chọn có
  kiểm model/revision/config, hash Parquet và ảnh; xem detector-cache.md. Không inference mới. Chưa hỗ trợ video tracking, polygon, tags, rotation, frame step,
  ảnh khác1280×720, class ngoài BDD hoặc basename trùng trong cùng job.

## Registry, mapping và bất biến

JobReader lấy task/job/meta/labels/annotations và raw images từ CVAT server cho phép.
Mapping sinh từ ID/frame thực; không mặc định task/job1/3. Deleted frames được loại đúng metadata.
Namespace=SHA256(origin chuẩn hóa,task_id,job_id)[:32]. Hai job trùng basename được tách namespace;
hai server không được lẫn dù cùng ID. Pagination không được đi ngoài server đã cấp quyền.

Registry SQLite giữ request_id,trạng thái,source fingerprint,profile và publication. Một worker,
file lock và transaction bảo vệ publish. File stage chỉ thành queue phục vụ khi input/hash/contract
hợp lệ và source không đổi giữa chừng. /jobs/{key}/ dispatch sang app/store/snapshot riêng; cùng API/cổng.
Retry cùng request không tạo batch mới; thất bại giữ publication cũ. Restart có thể resume intake dở.

Trạng thái: chưa kiểm → queued → reading → checking → partial/completed; lỗi → failed → retry.
Profile hiện tại cố ý trả partial. Một lỗi không được biến thành score0 hoặc fixture thay thế.
Release demo lấy score/rank/evidence/audit từ cùng nguồn 10.000 ảnh. Recheck nhãn sau đó vẫn giữ
lịch review gốc để không thay plan khi reviewer đã bắt đầu. Điểm sau sửa có thể khác lịch đã freeze.
Muốn đổi lịch theo scorer mới phải tạo full-batch plan/queue mới, không âm thầm thay baseline lịch sử.

## Save, recheck và verdict

Canvas CVAT chưa Save không phải đầu vào backend. Người dùng Save bên CVAT, bấm đọc nhãn đã lưu,
nhận snapshot/hash/version, rồi yêu cầu kiểm lại. Backend đọc xác nhận nguồn còn khớp trước chạy;
snapshot cũ →409, thất bại không activate. Kết quả thành công tạo queue/version mới và trước/sau
đọc lại được. Không đổi queue đang phục vụ tại chỗ. Recheck bị ngắt giữ trạng thái thất bại có giải thích.

Verdict error/false_alarm/skip lưu append-only cùng reviewer/session,queue_id,model_version,rank,
seconds_spent và policy metadata. request_id+payload_hash chống retry trùng/lost ACK và trả409 nếu
tái dùng key cho nội dung khác. Đồng hồ dừng khi mất focus/đổi frame/chuyển CVAT; không phải số liệu
pilot trừ khi session được đăng ký là người review thật. Skip loại khỏi mẫu số error+false_alarm.

## API chính

| Route | Vai trò |
|---|---|
| GET /health | Queue/config readiness, active checks; không chứa secrets |
| POST /auth/demo; GET /auth/session; POST /auth/logout | Public demo session; cookie HttpOnly/Secure/SameSite Strict |
| GET /queue; /web/context; /web/review/{image}; /image/{image}/file | Queue, nhãn/evidence/ảnh theo snapshot |
| POST /verdict; GET /stats | Lưu idempotent, stats theo phiên đăng nhập |
| GET /intake/status; POST /intake/check; GET /intake/requests/{id} | Local operator/authorized reviewer, task/server allowlist |
| GET/POST /jobs/{key}/{path} | Scope riêng, bảo vệ auth bên ngoài trước dispatch |
| GET /image/{image}/saved; POST /image/{image}/recheck | Nhãn CVAT Save, recheck snapshot/version |
| GET /web/recheck-history/{image}; GET /rechecks/{id} | Theo dõi và đối chiếu trước/sau |
| GET /web/results; /web/results/gain.png | Báo cáo baseline offline đã freeze, không phải pilot |

## Public deployment và bảo vệ

Browser/API cùng origin HTTPS trên Render. Host/Origin và body size được kiểm; login rate limit,
cookie session lưu PostgreSQL, CSRF chặn request ghi khác origin. Người dùng không nhập URL API/key.
Role demo không được intake/jobs/model/retrain/pilot/Save-recheck, không đọc stats phiên khác.
Không có endpoint nhận đường dẫn file tùy ý. Local API bind loopback; không coi đó là cấu hình public.

Postgres giữ immutable demo_assets, append-only verdicts và state. Disk Render chỉ cache hydrate
có hash; restart/mất disk không mất session/verdict. Auth secret cố định ở môi trường server,
không Git/frontend. Backup mode0600; restore chỉ DB mới trống, invalidate login sessions.
Web/DB Free, auto-deploy off; DB hiện hết hạn15/11/2026. Không có public CVAT hoặc cam kết uptime24/7.

## Guideline, audit và đánh giá

Gemini adapter trích luật từ DOCX/PDF, có schema/quote/page/hash/cache/provenance. Draft chưa duyệt
bị chặn; chỉnh bản đã duyệt sinh draft mới. Agent không tự approved_by. Demo public chưa tích hợp
spec được người phụ trách duyệt; không quảng cáo là đang kiểm guideline online.

Audit:5% đuôi ngoài top20%,seed42,freeze plan trước crop, chèn đều; không lộ cờ cho reviewer.
Recall@20% dùng rank gốc, ngân sách có audit không gọi là20%. Wilson và minimum sample được giữ;
không suy rộng khi thiếu mẫu. Baseline trên lỗi tiêm, split theo ảnh6k/2k/2k; human pilot tách DB/task,
30ảnh×2reviewer, kiểm hiệu ứng nhớ ảnh. Chưa có kết quả pilot30 hoặc measured time_saved.


## Kết quả nhóm và hồ sơ công khai

`reports/team-timing.json` giữ đúng cùng10ảnh/20phút assisted/45phút manual; giảm55,6% tính từ
số liệu nhóm cung cấp, chưa đối chiếu log/quy trình/ảnh hưởng nhớ ảnh. Không gán số lỗi/recall/reviewer
hoặc ngoại suy thành30ảnh đã đo. Endpoint/trang kết quả tách khỏi baseline lỗi tiêm/proxy.

`/submission` và danh sách `/web/submission` được đọc công khai. Chỉ ba artifact cố định PDF/PNG/MP4
được publish qua operator backend vào Postgres hiện có, hash/bundle immutable. Source/secrets/DB không
được phục vụ. Đường dẫn không cho đọc file tùy ý; tên ngoài whitelist404; không có API publish public.
Public assets không mở quyền queue/intake/admin. Chưa đăng nhập vẫn bị chặn các API review.
