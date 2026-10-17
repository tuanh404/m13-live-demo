"""Encode real browser footage with explicitly positioned, readable captions."""

import subprocess
from pathlib import Path


def seconds(value):
    h, m, s = value.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def encode_video(raw, srt, target):
    folder = target.parent / "caption-text"
    folder.mkdir(exist_ok=True)
    font = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    if not font.is_file():
        raise ValueError("Need DejaVu Sans for Vietnamese captions")
    filters = []
    for i, block in enumerate(srt.read_text().strip().split("\n\n")):
        lines = block.splitlines()
        start, end = lines[1].split(" --> ")
        text = folder / f"{i:02}.txt"
        text.write_text("\n".join(lines[2:]))
        filters.append(
            f"drawtext=fontfile='{font}':textfile='{text.resolve()}':fontsize=28:"
            "fontcolor=white:box=1:boxcolor=black@0.80:boxborderw=8:line_spacing=5:"
            f"x=(w-text_w)/2:y=14:enable='gte(t,{seconds(start)})*lt(t,{seconds(end)})'"
        )
    graph = target.parent / "video-filter.txt"
    graph.write_text(",\n".join(filters))
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(raw),
            "-filter_script:v",
            str(graph),
            "-c:v",
            "libx264",
            "-threads",
            "2",
            "-preset",
            "fast",
            "-crf",
            "24",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-an",
            str(target),
        ],
        check=True,
        capture_output=True,
    )
