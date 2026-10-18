"""Render editable SVG/HTML submission assets; no data/credentials enter source."""

import json
import shutil
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]


def main():
    output = ROOT / "data/mvp-submission"
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=shutil.which("google-chrome"))
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.goto((ROOT / "docs/mvp/thumbnail.svg").as_uri())
        page.screenshot(path=str(output / "thumbnail.png"))
        page.set_viewport_size({"width": 1280, "height": 720})
        page.goto((ROOT / "docs/mvp/pitch.html").as_uri())
        page.wait_for_function("() => [...document.images].every(im => im.complete && im.naturalWidth > 0)")
        page.locator("#mode").click()
        overflow = page.locator(".slide").evaluate_all("""els => els.map((el,i)=>{
            document.querySelectorAll('.slide').forEach(s=>s.classList.remove('active'));
            el.classList.add('active');
            return {slide:i+1,height:el.clientHeight,content:el.scrollHeight};
        }).filter(x=>x.content>x.height+2)""")
        if overflow:
            raise ValueError(f"Slides overflow: {overflow}")
        page.pdf(path=str(output / "pitch.pdf"), width="1280px", height="720px", print_background=True)
        page.locator("nav").evaluate("el => el.style.display = 'none'")
        for i in range(12):
            page.evaluate("i => show(i)", i)
            page.screenshot(path=str(output / f"slide-{i + 1:02}.png"))
        page.evaluate("show(0)")
        page.screenshot(path=str(output / "pitch-cover.png"))
        browser.close()
    import pdfplumber

    with pdfplumber.open(output / "pitch.pdf") as pdf:
        assert len(pdf.pages) == 12
        assert all(len(p.extract_text() or "") > 50 for p in pdf.pages)
    (output / "asset-check.json").write_text(
        json.dumps(
            {
                "slides": 12,
                "pdf_pages": 12,
                "thumbnail_width": 1600,
                "thumbnail_height": 900,
                "editable_sources": ["docs/mvp/pitch.html", "docs/mvp/thumbnail.svg"],
                "slide_overflow": overflow,
                "publication": "local_only",
            },
            indent=2,
        )
        + "\n"
    )
    print("12-slide PDF and1600×900 thumbnail rendered; editable sources retained.")


if __name__ == "__main__":
    main()
