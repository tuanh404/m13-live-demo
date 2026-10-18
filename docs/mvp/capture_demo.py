"""Record the current public web product; use a separate automation session, never human pilot data."""

import io
import json
import shutil
import time
import zipfile
from pathlib import Path

from add_captions import encode_video
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
LIVE = "https://m13-live-demo.onrender.com"


def stamp(value):
    ms = round(value * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def cvat_sample(raw):
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        dst.writestr("obj.names", src.read("classes.txt"))
        dst.writestr("obj.data", "classes = 2\nnames = obj.names\ntrain = train.txt\n")
        dst.writestr(
            "train.txt",
            "\n".join("obj_train_data/" + Path(n).name for n in src.namelist() if n.startswith("images/")),
        )
        for name in src.namelist():
            if name.startswith(("images/", "labels/")):
                dst.writestr("obj_train_data/" + Path(name).name, src.read(name))
    return out.getvalue()


def main():
    expect.set_options(timeout=60000)
    output = ROOT / "data/mvp-submission"
    media = output / "media"
    media.mkdir(parents=True, exist_ok=True)
    scenes, segments, marks = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=shutil.which("google-chrome"))
        warm = browser.new_context()
        warm.set_default_timeout(90000)
        r = warm.request.post(LIVE + "/auth/demo", headers={"Origin": LIVE}, timeout=90000)
        assert r.status == 200, r.status
        revision = warm.request.get(LIVE + "/build", timeout=90000).json()["revision"]
        r = warm.request.get(LIVE + "/my-batches/sample.zip", timeout=90000)
        assert r.status == 200
        sample = output / "CVAT-YOLO-1.1-mau.zip"
        sample.write_bytes(cvat_sample(r.body()))
        warm.close()
        ctx = browser.new_context(
            viewport={"width": 1600, "height": 760},
            record_video_dir=str(output / "raw-current"),
            record_video_size={"width": 1600, "height": 760},
        )
        ctx.set_default_timeout(90000)
        page = ctx.new_page()
        video = page.video
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        started = time.monotonic()

        def shot(title, body, action, duration=9, image=None):
            start = time.monotonic() - started
            action()
            ready = time.monotonic() - started
            action_seconds = ready - start
            keep = min(action_seconds, 6)
            page.wait_for_timeout(max(3, duration - keep) * 1000)
            end = time.monotonic() - started
            parts = [(start, end)] if action_seconds <= 8 else [(start, start + 2), (ready - 4, end)]
            for a, b in parts:
                segments.append((a, b))
                marks.append({"duration": b - a, "title": title, "text": body})
            scenes.append(
                {
                    "title": title,
                    "raw_start": start,
                    "raw_end": end,
                    "removed_network_wait": max(0, action_seconds - 6) if action_seconds > 8 else 0,
                }
            )
            if image:
                page.screenshot(path=str(media / image))
            print("Recorded:", title, flush=True)

        def entry():
            page.goto(LIVE + "/login", timeout=90000)
            expect(page.locator("#my-images")).to_be_visible()

        shot(
            "M13 / Kiểm đúng chỗ. Review có lý do.",
            "Trợ lý ưu tiên ảnh có nguy cơ sai nhãn.\nMở web để trải nghiệm, không cần cài extension.",
            entry,
            9,
            "entry.png",
        )

        def demo():
            page.locator("#guest-demo").click()
            expect(page.locator("[data-verdict=error]")).to_be_enabled()

        shot(
            "01 / Hàng đợi ưu tiên",
            "Demo có 10 ảnh BDD thật và dự đoán detector đã lưu.\n"
            "Điểm cao gợi ý ảnh nên xem trước; không phải xác suất sai.",
            demo,
            11,
            "demo-review.png",
        )
        shot(
            "02 / Biết vì sao máy nghi ngờ",
            "Đối chiếu ảnh, nhãn và vùng nghi vấn cùng lý do.\n"
            "Người review xác nhận; hệ thống không tự sửa nhãn.",
            lambda: page.locator("#boxes-details").click(),
            9,
            "evidence.png",
        )
        page.locator("#boxes-details").click()
        for verdict, title, text in [
            ("error", "Lỗi thật", "Tôi đã đối chiếu và xác nhận lỗi nhãn cần xử lý."),
            ("false_alarm", "Bot nhầm", "Tôi không xác nhận nghi vấn mà máy đưa ra."),
            ("skip", "Bỏ qua", "Tôi chưa đủ thông tin để kết luận, cần kiểm sau."),
        ]:

            def decide(v=verdict):
                page.locator(f"[data-verdict={v}]").click()
                expect(page.locator("[data-verdict=error]")).to_be_enabled()

            shot(
                "03 / " + title,
                text + "\nĐây là lượt thao tác minh họa tự động, không phải pilot người thật.",
                decide,
                6,
            )

        def resume_demo():
            page.reload()
            expect(page.locator("#progress")).to_contain_text("3/10")
            page.locator("#stats").scroll_into_view_if_needed()

        shot(
            "04 / Kết luận đã lưu",
            "Reload vẫn giữ 3/10 ảnh đã review và thống kê ba kết luận.\n"
            "Bấm kết luận không đồng nghĩa sửa hoặc Save nhãn.",
            resume_demo,
            8,
            "stats.png",
        )

        def baseline():
            page.goto(LIVE + "/results")
            expect(page.locator("#gain")).to_be_visible()

        shot(
            "05 / Đánh giá có đáp án",
            "Baseline offline trên lỗi tiêm: recall theo ảnh ở top 20% là 27,67%.\n"
            "Random đạt 20,15%; đây chưa phải recall trên lỗi thật.",
            baseline,
            9,
            "baseline.png",
        )

        def own_images():
            page.goto(LIVE + "/my-batches")
            expect(page.locator("#archive")).to_be_visible()
            page.locator("#archive").set_input_files(sample)
            page.locator("#upload-form").scroll_into_view_if_needed()

        shot(
            "06 / Kiểm tra bộ ảnh của tôi",
            "Chọn nguyên ZIP YOLO 1.1 hoặc Ultralytics Detection có ảnh và nhãn.\n"
            "Tối đa 10 ảnh 1280×720; gói minh họa là dữ liệu kiểm thử tổng hợp.",
            own_images,
            10,
            "upload.png",
        )

        def upload():
            page.locator("#upload-check").click()
            expect(page.locator("#uploaded-review")).to_be_visible()
            expect(page.locator("#upload-status")).to_contain_text("CVAT YOLO1.1")

        shot(
            "07 / Tự ghép ảnh và nhãn",
            "Không cần giải nén hay sắp lại thư mục: tool tạo hàng đợi riêng.\n"
            "Luồng ảnh mới kiểm một phần bằng 6 tín hiệu hình học/ngữ cảnh.",
            upload,
            9,
            "uploaded.png",
        )
        batch_url = page.locator("#uploaded-review").get_attribute("href")

        def uploaded_review():
            page.locator("#uploaded-review").click()
            expect(page.locator("[data-verdict=error]")).to_be_enabled()

        shot(
            "08 / Nghi vấn được tính từ nhãn mới",
            "Hai box car trùng khít được đánh dấu để bạn đối chiếu.\n"
            "Luồng upload chưa chạy detector hoặc guideline trên ảnh mới.",
            uploaded_review,
            10,
            "upload-review.png",
        )

        def clean_image():
            for button in page.locator("#queue button").all():
                if "clean" in button.inner_text():
                    button.click()
                    break
            expect(page.locator("#image-title")).to_contain_text("clean")

        shot(
            "09 / Điểm 0 vẫn cần được hiểu đúng",
            "Điểm 0 nghĩa là các phép kiểm hiện tại chưa tìm ra nghi vấn.\n"
            "Chưa thể kết luận box bám đúng vật thể hoặc ảnh không thiếu nhãn.",
            clean_image,
            9,
        )

        def reopen_batch():
            page.goto(LIVE + batch_url)
            expect(page.locator("[data-verdict=error]")).to_be_enabled()
            page.locator('#queue button[data-image="duplicate"]').click()
            expect(page.locator("#image-title")).to_contain_text("duplicate")
            page.locator("[data-verdict=error]").click()
            expect(page.locator("#progress")).to_contain_text("1/3")
            page.goto(LIVE + "/my-batches")
            page.locator("#batch-list a").click()
            expect(page.locator("#progress")).to_contain_text("1/3")

        shot(
            "10 / Tiếp tục bộ ảnh của bạn",
            "Mở lại Bộ ảnh của tôi để tiếp tục review; kết luận trước vẫn được giữ.\n"
            "Dữ liệu gắn với phiên đăng nhập hiện tại, không phải kho tài khoản lâu dài.",
            reopen_batch,
            9,
        )
        shot(
            "Trải nghiệm tại m13-live-demo.onrender.com",
            "M13 giúp chọn ảnh cần kiểm, giải thích nghi vấn và lưu kết luận.\n"
            "Ảnh BDD100K ©2018 The Regents of the University of California.",
            entry,
            9,
        )
        assert not errors, errors
        raw_duration = time.monotonic() - started
        ctx.close()
        raw = Path(video.path())
        browser.close()
    duration = sum(b - a for a, b in segments)
    assert duration <= 175, f"Edit length {duration:.1f}s exceeds budget; inspect scenes before encoding"
    at = 0
    blocks = []
    for i, mark in enumerate(marks):
        blocks.append(
            f"{i + 1}\n{stamp(at)} --> {stamp(at + mark['duration'])}\n{mark['title']}\n{mark['text']}\n"
        )
        at += mark["duration"]
    srt = output / "demo.srt"
    srt.write_text("\n".join(blocks), encoding="utf-8")
    record = {
        "duration_recorded_seconds": round(raw_duration, 3),
        "edited_duration_seconds": round(duration, 3),
        "max_seconds": 180,
        "actual_browser_recording": True,
        "public_live": LIVE,
        "build_revision_recorded": revision,
        "caption_position": "separate 140px bottom band",
        "narration": "Vietnamese bottom titles/captions; no human voice",
        "human_pilot": False,
        "source_video": str(raw.relative_to(ROOT)),
        "cuts": segments,
        "scenes": scenes,
        "captions": marks,
        "network_waits_shortened": any(s["removed_network_wait"] for s in scenes),
        "mutations": "separate automated demo verdicts/upload fixture; no CVAT annotations",
        "sample": "synthetic software-test photos and YOLO labels, not human pilot",
        "video": "data/mvp-submission/M13-demo.mp4",
        "publication": "local_only",
    }
    (output / "video-edit.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    record["encoded_duration_seconds"] = encode_video(raw, srt, output / "M13-demo.mp4", cuts=segments)
    (output / "video-record.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(f"New current-live recording: {duration:.1f}s, captions below UI.", flush=True)


if __name__ == "__main__":
    main()
