# M13 · Reviewer Prioritization Assistant

Bản triển khai riêng cho demo web: ưu tiên ảnh có nguy cơ lỗi nhãn, hiển thị lý do/box nghi vấn, ghi kết luận và thống kê. Người dùng mở web, bấm **Trải nghiệm demo**, đối chiếu và chọn **Lỗi thật / Bot nhầm / Bỏ qua**. Không cần extension hoặc CVAT trên máy người xem.

Source kế thừa [dự án nhóm M13](https://github.com/cuongherok4/qc2d_auto_assistant), nền `72b1e4c05f37969f0806746862a7657d585502ce`, cùng phần triển khai MVP của Tú Anh. Đây là repo deploy riêng; không thay repo/nhánh chính của nhóm.

## Bản demo và giới hạn

- 10 ảnh BDD100K có provenance từ mirror Hugging Face ghim revision/hash; nhãn và detector predictions cache được đóng băng. Scorer demo là `rule-bdd-live-v1`, không phải inference/training/Gemini online.
- Điểm là mức rủi ro/ưu tiên xem. Điểm0 không bảo đảm nhãn đúng. Verdict chỉ ghi kết luận, không tự sửa nhãn.
- Bộ ảnh/queue/evidence/manifest và kết quả review nằm trong Postgres. Không commit ảnh, dữ liệu, DB hoặc credentials vào Git. Không dùng SQLite ephemeral của Render Free để lưu kết quả.
- CVAT local không được quảng cáo là CVAT live. Public demo chỉ review bộ ảnh chỉ định; intake/recheck/retrain/quản trị bị chặn với tài khoản demo. Intake nhiều job được kiểm riêng ở local bằng backend allowlist và adapter bbox1280×720; thiếu detector/spec/GBM báo kiểm một phần.
- Baseline là đánh giá offline trên lỗi tiêm có đáp án, có hash/split/seed; không phải lỗi người review xác nhận. Pilot30 người thật và thời gian tiết kiệm thực đo chưa nghiệm thu. Mọi lượt thử trên web là demo, không tự ghi thành human pilot.

## Deploy Render Free

`render.yaml` ghim Free Web + Free Postgres, Python3.11.17,1worker, cùng region Singapore. TLS/HTTPS do Render quản lý. Auto deploy tắt; chỉ deploy commit đã kiểm.

1. Tạo Postgres Free và nạp bundle đã kiểm bằng `python -m src.cli render-upload <bundle>`, với `M13_DATABASE_URL` chỉ ở môi trường backend.
2. Tạo web từ repo này. Build: `pip install --no-cache-dir -r deployment/render/requirements.lock`.
3. Start: `python -m uvicorn src.api.render_app:create_render_app --factory --host 0.0.0.0 --port $PORT --workers 1 --no-access-log`.
4. Cấu hình server: `M13_DATABASE_URL` là Internal URL của DB; `M13_DEMO_BUNDLE_ID` là ID artifact đã nạp; `M13_AUTH_SECRET` là secret ngẫu nhiên tối thiểu32ký tự. Không ghi giá trị vào Git, README hoặc frontend. Render cung cấp `RENDER_EXTERNAL_URL`.
5. Healthcheck `/health`. Kiểm browser sạch: demo → ảnh/nhãn/evidence →3verdict → stats → reload/restart; hai browser phải giữ lượt riêng.

Free web ngủ sau15phút không truy cập, mở lại khoảng1phút. Free Postgres hết hạn30ngày kể từ tạo, không có backup tự động; gói này chỉ dành demo ngắn hạn. Không bật gói trả phí/autoscale. Link public chỉ công bố sau kiểm truy cập thật.

## Backup và rollback

`python -m src.cli render-backup --out data/backup-new.json` xuất assets/verdict/state nhất quán, file0600. Giữ file ngoài Git. `render-restore <backup>` chỉ cho DB mới trống, vô hiệu hóa phiên đăng nhập cũ. Không restore đè DB đang dùng. Rollback source sang commit đã kiểm với cùng bundle ID/schema tương thích; backup trước khi đổi schema. Dịch vụ Render quản lý restart, dữ liệu và ảnh khôi phục từ DB sau mất disk.

## Kiểm thử

```bash
python -m pip install -e '.[dev,demo,postgres]'
pytest -q
ruff check .
```

Integration Postgres thật chỉ bật bằng `M13_TEST_DATABASE_URL` trỏ DB kiểm riêng, tài khoản có quyền tạo DB tạm. Browser opt-in: `M13_WEB_BROWSER_TESTS=1` hoặc `M13_BROWSER_TESTS=1`; không dùng test tự động làm pilot.

## Dữ liệu

Ảnh/nhãn BDD100K: Copyright ©2018 The Regents of the University of California. Chỉ dùng demo giáo dục/nghiên cứu, theo [giấy phép dữ liệu](deployment/render/BDD100K-LICENSE.txt). Nguồn mirror/checksum được giữ trong bundle; không phải danh sách checksum ảnh chính thức của BDD. Tham khảo [BDD100K](https://bdd-data.berkeley.edu/).
