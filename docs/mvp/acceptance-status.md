# Trạng thái13nhóm · cập nhật17/10

Không chuyển các trạng thái dưới thành phần trăm nghiệm thu tổng thể. Artifact local, test fixture,
BDD thật, backend thật và human pilot là các mức bằng chứng khác nhau.

| # | Đầu ra | Trạng thái đã kiểm | Còn thiếu/giới hạn |
|---|---|---|---|
|1| Nền, môi trường, Git | Python3.11, nhánh feat/tuanh-mvp-live-rebuild, nền72b1e4c | Diff local, không commit/push/merge L06 |
|2| Dữ liệu/batch/mapping |40BDD mirror có hash,10demo/30pilot tách; job20/21 mapping sinh tự động | Chưa checksum ảnh chính thức; ảnh mới trên public chưa hỗ trợ |
|3| Scorer/provenance | Rule thật;4signals detector-cache cho demo,7geometry cho intake | Demo cùng queue/score/audit nguồn10k; không detector/Gemini/GBM online |
|4| Web core | Public HTTPS10BDD; queue/evidence/verdict/stats | Batch cố định, không upload mới |
|5| CVAT/Save/recheck | Job20 UI thật5,43→0, đọc nhãn Save và trước/sau | Nhãn fixture trên ảnh thật; CVAT public chưa có |
|6| UX | Browser thật, không form kỹ thuật, retry/missing input rõ hơn | Chưa người mới dùng độc lập; tên box đã thu gọn, chờ feedback |
|7| Diễn giải | Điểm0/risk/verdict/fixture/cache được ghi rõ trong UI/tài liệu/slide/video | Cần người thuyết trình giữ đúng giới hạn |
|8| Audit | Policy5%đuôi/seed42/freeze/Wilson/export test đạt | Chưa audit người thật; không suy rộng khi thiếu mẫu |
|9| Nghiệm thu |10BDD public(L05) và2job CVAT thật(L06), restart/history | Đây là software acceptance tự động, không human pilot |
|10| Baseline | Replay cùng artifacts/split/đáp án, test2.000ảnh, lỗi tiêm | Chưa recall lỗi thật/measured time_saved |
|11| Pilot | Tooling +30BDD/task/DB riêng đã chuẩn bị | Nhóm báo cùng10ảnh20/45phút, chưa có log; không đổi thành30 |
|12| Intake/deploy | Hai job mới UI thật; public Render Free; backup/restart L05 | Cache/retry và adapter mới đã chuẩn bị phát hành riêng; CVAT public/4máy/container clean chưa nghiệm thu |
|13| Hồ sơ/nộp | README/spec/architecture/testing/logs,12slide PDF/HTML,thumbnail/video và manifest local | Video/PDF/PNG qua /submission khi publish; source mới private/local, chưa nộp BTC |

Commit/CI/public status thực của bản17/10 được ghi trong checkpoint và reports/mvp-verification.json.
Repo nhóm không commit/push; repo deploy giữ private. Chưa pilot30/người mới/nộp BTC.
