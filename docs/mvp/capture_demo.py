"""Record real browser actions, with captions; never create human-pilot results.

Needs the existing L06 local acceptance API/task21. That task is ALREADY registered:
the recording must say this explicitly instead of claiming a first-time intake.
Only the backend holds CVAT credentials; the recording uses the local web intake UI.
"""

import json
import shutil
import time
from pathlib import Path

import httpx
from add_captions import encode_video
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]


def stamp(seconds):
    ms = round(seconds * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def main():
    expect.set_options(timeout=45000)
    output = ROOT / "data/mvp-submission"
    output.mkdir(parents=True, exist_ok=True)
    live = "https://m13-live-demo.onrender.com"
    assert httpx.get(live + "/health", timeout=120).status_code == 200
    marks = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=shutil.which("google-chrome"))
        ctx = browser.new_context(
            viewport={"width": 1366, "height": 900},
            record_video_dir=str(output / "raw"),
            record_video_size={"width": 1366, "height": 900},
        )
        page = ctx.new_page()
        video = page.video
        started = time.monotonic()

        def caption(text, seconds=6):
            marks.append({"start": time.monotonic() - started, "text": text})
            page.wait_for_timeout(seconds * 1000)

        page.goto(live, timeout=90000)
        expect(page.locator("#guest-demo")).to_be_visible()
        caption("M13 · Web live: ưu tiên ảnh cần QC.\nMở bằng trình duyệt thường, không cần extension.")
        page.locator("#guest-demo").click()
        expect(page.locator("[data-verdict=error]")).to_be_enabled(timeout=45000)
        caption(
            "10 ảnh BDD thật; nhãn và predictions đã đóng băng.\nKhông chạy detector hoặc Gemini online.", 8
        )
        caption("Xanh: nhãn hiện có. Cam: nghi vấn máy gợi ý.\nĐiểm là rủi ro; điểm 0 vẫn có thể có lỗi.", 8)
        page.locator("#boxes-details").click()
        caption("Có thể đối chiếu danh sách box và tọa độ.\nNgười QC xác nhận, máy không tự quyết định.", 6)
        page.locator("#boxes-details").click()
        for verdict, text in [
            ("error", "Lỗi thật: đã xác nhận lỗi nhãn cần sửa."),
            ("false_alarm", "Bot nhầm: không xác nhận nghi vấn máy."),
            ("skip", "Bỏ qua: chưa đủ thông tin kết luận."),
        ]:
            page.locator(f"[data-verdict={verdict}]").scroll_into_view_if_needed()
            caption(text + "\nThao tác minh họa tự động, không phải kết quả pilot.", 4)
            page.locator(f"[data-verdict={verdict}]").click()
            expect(page.locator("[data-verdict=error]")).to_be_enabled()
        page.reload()
        expect(page.locator("#progress")).to_contain_text("3/10")
        page.locator("#stats").scroll_into_view_if_needed()
        caption("Kết luận đã lưu; reload vẫn giữ3/10.\nLịch sử/session được lưu ở Postgres.", 7)
        page.goto(live + "/results")
        expect(page.locator("#gain")).to_be_visible(timeout=45000)
        caption(
            "Baseline offline:2.000 ảnh test, lỗi TIÊM có đáp án.\n"
            "Recall lỗi theo ảnh ở top 20%:27,67%; random20,15%.",
            9,
        )
        page.locator("#team-timing").scroll_into_view_if_needed()
        caption(
            "Nhóm cung cấp: cùng10ảnh, assisted20phút/manual45phút.\n"
            "Giảm55,6% từ số liệu này; chưa đối chiếu log, không phải pilot30.",
            6,
        )
        page.goto(
            "http://127.0.0.1:8010/intake?cvat_origin=http%3A%2F%2Flocalhost%3A8080&task_id=21&job_id=21"
        )
        expect(page.locator("#check-job")).to_be_enabled(timeout=45000)
        caption("Web LOCAL nối backend CVAT có quyền.\nẢnh BDD thật, nhãn fixture; không phải pilot.", 7)
        caption(
            "Job21 ĐÃ được đăng ký trong lượt nghiệm thu trước.\n"
            "Đây là kiểm lại, không phải cảnh tiếp nhận lần đầu.",
            7,
        )
        page.locator("#check-job").click()
        expect(page.locator("#review-job")).to_be_visible(timeout=45000)
        caption(
            "Nhãn đã Save không đổi: backend tái dùng snapshot hợp lệ.\n"
            "Job mới chưa có detector/spec/GBM: kiểm MỘT PHẦN.",
            7,
        )
        page.locator("#review-job").click()
        expect(page.locator("[data-verdict=error]")).to_be_enabled(timeout=45000)
        caption(
            "Queue/ảnh/evidence và lịch sử tách theo server/task/job.\n"
            "Verdict không sửa hoặc Save annotation vào CVAT.",
            7,
        )
        page.locator("#cvat-tools > summary").click()
        page.locator("#read-saved").click()
        expect(page.locator("#read-saved")).to_be_enabled()
        caption(
            "Đọc nhãn đã Save trước khi yêu cầu kiểm lại.\n"
            "Save/recheck thật đã nghiệm thu riêng:5,43 → 0, giữ trước/sau.",
            8,
        )
        page.goto(live)
        expect(page.locator("[data-verdict=error]")).to_be_enabled(timeout=45000)
        caption(
            "Trải nghiệm: m13-live-demo.onrender.com\n"
            "Public hiện chỉ review10 ảnh; upload batch mới là bước phát triển tiếp.\n"
            "Ảnh/nhãn BDD100K ©2018 The Regents of the University of California.",
            8,
        )
        duration = time.monotonic() - started
        ctx.close()
        raw = Path(video.path())
        browser.close()
    assert duration < 175, f"Recording too long: {duration:.1f}s; edit before claiming180s"
    srt = output / "demo.srt"
    srt.write_text(
        "\n".join(
            f"{i + 1}\n{stamp(m['start'])} --> "
            f"{stamp(marks[i + 1]['start'] if i + 1 < len(marks) else duration)}\n{m['text']}\n"
            for i, m in enumerate(marks)
        ),
        encoding="utf-8",
    )
    target = output / "M13-demo.mp4"
    encode_video(raw, srt, target)
    (output / "video-record.json").write_text(
        json.dumps(
            {
                "duration_recorded_seconds": round(duration, 3),
                "max_seconds": 180,
                "actual_browser_recording": True,
                "narration": "Vietnamese captions, no human voice",
                "human_pilot": False,
                "public_live": live,
                "local_job": 21,
                "local_job_pre_registered_explicitly_captioned": True,
                "mutations": "public demo verdicts only; local reads/reused snapshot; no CVAT Save",
                "captions": marks,
                "video": str(target.relative_to(ROOT)),
                "publication": "local_only",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(f"Actual browser MP4 with Vietnamese captions: {duration:.1f}s (<180s), local only.")


if __name__ == "__main__":
    main()
