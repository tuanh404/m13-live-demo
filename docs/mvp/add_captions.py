"""Encode actual screen footage with a separate bottom title/caption band."""

import re
import subprocess
from pathlib import Path


def seconds(value):
    h, m, s = value.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def encode_video(raw, srt, target, *, cuts=None):
    folder = target.parent / "caption-text"
    folder.mkdir(exist_ok=True)
    clips = target.parent / "encoded-scenes"
    clips.mkdir(exist_ok=True)
    font = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    if not font.is_file():
        raise ValueError("Need DejaVu Sans for Vietnamese captions")
    blocks = srt.read_text().strip().split("\n\n")
    segments = []
    for i, block in enumerate(blocks):
        lines = block.splitlines()
        start, end = lines[1].split(" --> ")
        title, body = folder / f"{i:02}-title.txt", folder / f"{i:02}-body.txt"
        title.write_text(lines[2], encoding="utf-8")
        body.write_text("\n".join(lines[3:]), encoding="utf-8")
        source_start, source_end = cuts[i] if cuts else (seconds(start), seconds(end))
        clip = clips / f"{i:02}.mp4"
        graph = (
            "pad=1600:900:0:0:color=0x0b1425,"
            f"drawtext=fontfile='{font}':textfile='{title.resolve()}':fontsize=29:"
            "expansion=none:fontcolor=0x74e5ce:x=38:y=780,"
            f"drawtext=fontfile='{font}':textfile='{body.resolve()}':fontsize=25:"
            "expansion=none:fontcolor=white:line_spacing=7:x=38:y=823"
        )
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{source_start:.6f}",
                "-i",
                str(raw),
                "-t",
                f"{source_end - source_start:.6f}",
                "-vf",
                graph,
                "-r",
                "25",
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
                "-an",
                str(clip),
            ],
            check=True,
            capture_output=True,
        )
        segments.append(clip)
        print(f"Encoded scene {i + 1}/{len(blocks)}", flush=True)
    listing = clips / "concat.txt"
    listing.write_text("\n".join(f"file '{p.name}'" for p in segments), encoding="utf-8")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(target),
        ],
        check=True,
        capture_output=True,
    )

    probe = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(target)], capture_output=True, text=True)
    match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", probe.stderr)
    if not match:
        raise ValueError("Cannot verify encoded video duration")
    duration = int(match[1]) * 3600 + int(match[2]) * 60 + float(match[3])
    if not 0 < duration <= 180:
        raise ValueError("Encoded video exceeds the180second submission limit")
    return duration
