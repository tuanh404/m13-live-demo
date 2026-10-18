# Trạng thái 13 nhóm · cập nhật18/10/2026

Đầu ra local, runtime public, fixture và kết quả người thật là các mức bằng chứng khác nhau.
Không đổi bảng này thành 100% hoặc Done theo CONTRIBUTING khi repo nhóm chưa được merge.

| # | Đầu ra | Đã kiểm | Giới hạn/phần chờ |
|---|---|---|---|
|1| Nền, môi trường, Git | Python3.11; nhánh feat/tuanh-mvp-live-rebuild, nền72b1e4c | Repo nhóm giữ diff, không Git mutation; phát hành qua repo riêng; source tại github.com/tuanh404/m13-live-demo |
|2| Dữ liệu/batch/mapping |40 BDD mirror có hash;10demo/30pilot tách; job20/21 ID thực | Chưa checksum ảnh chính thức; public đã nhận ZIPYOLO ảnh+nhãn, scope partial |
|3| Scorer/provenance | Demo cùng queue/score/rank/evidence/audit từ full10k rule-mvp-original-v1 | Detector cache, không inference/Gemini/GBM online; cache job mới mới kiểm fixture |
|4| Web core | Public HTTPS10BDD; queue/ảnh/evidence/3verdict/next/stats | Demo10ảnh và batchYOLO riêng; không phải kết quả human pilot |
|5| CVAT/Save/recheck | L06 native Save5,43→0 giữ trước/sau; phiên này đọc lại hai job, hash annotations nguyên | Nhãn fixture trên ảnh BDD; không CVAT public; cache recheck có unit test |
|6| UX | Chrome thật, entry mới/CTA/retry/390–1366px; chức năng hiện theo quyền và dữ liệu | Chờ người dùng feedback; chưa nghiệm thu người mới; laptop có thể cần cuộn |
|7| Diễn giải | Risk≠xác suất;0 không bảo đảm đúng; verdict≠Save; fixture/cache/nguồn rõ | Không quảng cáo auto sửa nhãn hoặc detector chắc chắn đúng |
|8| Audit |5%ngoài top20%,seed42,freeze trước crop; denominator/Wilson/export test đạt | Chưa audit người thật; tổng top+audit24% khiN10k |
|9| Nghiệm thu |10BDD web public;2job CVAT local; lostACK/reload/redeploy/restart/history/auth | Software acceptance tự động; không human pilot |
|10| Baseline | Replay artifacts/split/hash cũ giữ nguyên; số nhóm cung cấp tách riêng | Baseline lỗi tiêm; chưa recall lỗi thật hoặc time_saved được kiểm log |
|11| Pilot | Tooling30BDD×2arm sẵn; cùng10ảnh20/45phút do nhóm cung cấp | Chưa log/quy trình/2reviewer cho30ảnh; không ngoại suy thành30đã đo |
|12| Intake/deploy | c94265b public, CI316passed1skip; backup/restore riêng; cache adapter local | Không public CVAT/intake/inference mới; chưa4máy/clean-container install |
|13| Hồ sơ/nộp | README/architecture/spec/testing/logs;12slide PDF;PNG;MP4125.16s, phụ đề dưới;manifest/sourceZIP | Video/PDF/PNG công khai qua /submission; source repo riêng đã chuẩn bị công khai; chưa nộp BTC |

Bằng chứng mới: `data/mvp-final/`, `reports/mvp-verification.json`.
Runtime public: https://m13-live-demo.onrender.com; hồ sơ: https://m13-live-demo.onrender.com/submission.
Source: https://github.com/tuanh404/m13-live-demo. Source ZIP cuối ở data/mvp-submission/M13-source-final.zip.


Video/slides bổ sung luồng upload theo runtimec94265b; nguồn/bằng chứng data/mvp-media-refresh/.
Không cộng thêm nghiệm thu human pilot/UX người mới/CVAT public vì làm lại hồ sơ.

Hồ sơ media mới đã GET/hash/playback ẩn danh đạt;12slide không tràn, gói chỉnh sửa đã kiểm.
