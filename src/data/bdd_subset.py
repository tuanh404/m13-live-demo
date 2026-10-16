"""Fetch only selected original JPEGs from a pinned public BDD mirror, never a ZIP."""

from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path

import httpx
from PIL import Image

REPOSITORY = "karthik789338/BDD100K-Images"
API = f"https://huggingface.co/api/datasets/{REPOSITORY}/tree"


def acquire(selection: Path, output: Path, revision: str, *, client=None):
    request = json.loads(selection.read_text())
    ids = request["demo_image_ids"] + request["pilot_image_ids"]
    if (
        not re.fullmatch(r"[a-f0-9]{40}", revision)
        or not 1 <= len(ids) <= 100
        or len(set(ids)) != len(ids)
        or any(not re.fullmatch(r"[a-f0-9]{8}-[a-f0-9]{8}", i) for i in ids)
    ):
        raise ValueError("Cần revision đã ghim và <=100image_id BDD duy nhất")
    identity = {"selection_sha256": hashlib.sha256(selection.read_bytes()).hexdigest(), "revision": revision}
    record_file = output / "acquisition.json"
    if output.exists() and any(output.iterdir()):
        if not record_file.is_file() or json.loads(record_file.read_text())["identity"] != identity:
            raise ValueError("Thư mục thuộc lượt tải khác; không ghi đè")
    output.mkdir(parents=True, exist_ok=True)
    if client is None:
        with httpx.Client(timeout=30, follow_redirects=True) as owned:
            return acquire(selection, output, revision, client=owned)

    def entries(directory):
        url = f"{API}/{revision}/{directory}?limit=1000"
        for _ in range(25):
            response = client.get(url)
            response.raise_for_status()
            yield from response.json()
            url = response.links.get("next", {}).get("url")
            if not url:
                return
            if not url.startswith(API + "/" + revision + "/"):
                raise ValueError("Pagination ngoài nguồn đã ghim")
        raise ValueError("Quá giới hạn metadata; không tải toàn dataset")

    files = {}
    for directory in entries("images/100k/val"):
        if directory["type"] != "directory":
            continue
        for item in entries(directory["path"]):
            image_id = Path(item["path"]).stem
            if image_id in ids:
                if image_id in files or not item["path"].endswith(".jpg"):
                    raise ValueError("Nguồn có filename trùng/mơ hồ")
                files[image_id] = item
    if set(files) != set(ids):
        raise ValueError(f"Nguồn thiếu {len(set(ids) - set(files))} ảnh đã chọn")
    if sum(item["size"] for item in files.values()) > 25 * 1024 * 1024:
        raise ValueError("Subset vượt25MiB; không tự tải ảnh lớn")
    record = {
        "identity": identity,
        "repository": REPOSITORY,
        "source_kind": "third_party_BDD_mirror_pinned_revision",
        "official_image_hashes_available": False,
        "note": "Verified mirror LFS hashes/filenames/JPEG dimensions; not an official image checksum list.",
        "complete": False,
        "images": {},
    }
    # Persist ownership before downloading, so a partial run can safely resume.
    record_file.write_text(json.dumps(record, indent=2) + "\n")
    for image_id in ids:
        item = files[image_id]
        expected = item.get("lfs", {}).get("oid")
        if not expected or not re.fullmatch(r"[a-f0-9]{64}", expected) or item["size"] > 2 * 1024 * 1024:
            raise ValueError("Nguồn thiếu SHA256 hoặc ảnh quá lớn")
        path = output / (image_id + ".jpg")
        url = f"https://huggingface.co/datasets/{REPOSITORY}/resolve/{revision}/{item['path']}"
        if path.exists():
            data = path.read_bytes()
        else:
            chunks, size = [], 0
            with client.stream("GET", url) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 2 * 1024 * 1024:
                        raise ValueError("Server trả ảnh quá lớn")
                    chunks.append(chunk)
            data = b"".join(chunks)
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected or len(data) != item["size"]:
            raise ValueError("Ảnh khác hash/size nguồn; không ghi đè ảnh đã có")
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "JPEG" or image.size != (1280, 720):
                raise ValueError("Không phải JPEG BDD1280x720")
            image.verify()
        if not path.exists():
            with path.open("xb") as handle:
                handle.write(data)
        record["images"][image_id] = {"source": url, "sha256": digest, "bytes": len(data)}
        record_file.write_text(json.dumps(record, indent=2) + "\n")
    record["complete"] = True
    record_file.write_text(json.dumps(record, indent=2) + "\n")
    return {"images": len(ids), "bytes": sum(v["bytes"] for v in record["images"].values()),
            "complete": True, "source": record["source_kind"], "output": str(output)}
