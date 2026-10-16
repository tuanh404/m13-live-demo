"""Read-only, allowlisted CVAT job intake. Files stay in a per-server/job namespace."""

from __future__ import annotations

import hashlib
import io
import math
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from PIL import Image

from src import contracts
from src.api.saved_labels import canonical


class IntakeError(ValueError):
    pass


def origin(value):
    url = urlsplit(value)
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username
        or url.password
        or url.path not in {"", "/"}
        or url.query
        or url.fragment
    ):
        raise IntakeError("Server CVAT không hợp lệ")
    host = "localhost" if url.hostname in {"localhost", "127.0.0.1"} else url.hostname
    port = url.port or (443 if url.scheme == "https" else 80)
    return f"{url.scheme}://{host}:{port}"


def workspace_key(server, task, job):
    return hashlib.sha256(canonical([origin(server), int(task), int(job)])).hexdigest()[:32]


class JobReader:
    def __init__(self, server, client, cfg):
        self.server, self.client, self.cfg = server.rstrip("/"), client, cfg
        self.deadline = time.monotonic() + cfg["timeout_seconds"]

    def get(self, endpoint, *, image=False):
        target = urljoin(self.server + "/", endpoint)
        if origin(target.split("/api/", 1)[0]) != origin(self.server):
            raise IntakeError("CVAT pagination ra ngoài server đã cấp quyền")
        if time.monotonic() > self.deadline:
            raise IntakeError("Đọc job quá thời gian; queue cũ vẫn được giữ")
        try:
            with self.client.stream("GET", target) as response:
                if response.status_code in {401, 403}:
                    raise IntakeError("Không có quyền đọc job CVAT")
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > self.cfg["max_image_bytes"]:
                        raise IntakeError("Dữ liệu CVAT vượt giới hạn cho phép")
                if image:
                    return bytes(content)
                import json

                return json.loads(content)
        except IntakeError:
            raise
        except Exception:
            raise IntakeError("Không đọc được CVAT; kiểm kết nối, quyền hoặc dữ liệu") from None

    def describe(self, task_id, job_id):
        if task_id not in self.cfg["allowed_task_ids"]:
            raise IntakeError("Task chưa được operator cấp quyền tiếp nhận")
        job = self.get(f"api/jobs/{job_id}")
        task = self.get(f"api/tasks/{task_id}")
        if int(job["task_id"]) != task_id or job.get("type") != "annotation":
            raise IntakeError("Job không thuộc annotation task đã chọn")
        if task.get("dimension") != "2d" or task.get("mode") != "annotation":
            raise IntakeError("Chỉ hỗ trợ job detection 2D ảnh rời, không hỗ trợ video/3D")
        meta = self.get(f"api/jobs/{job_id}/data/meta")
        start, stop = int(job["start_frame"]), int(job["stop_frame"])
        frames = meta.get("frames", [])
        if meta.get("frame_filter") or len(frames) != stop - start + 1:
            raise IntakeError("Job có frame step/metadata chưa hỗ trợ; không đoán mapping")
        if not frames or len(frames) > self.cfg["max_frames"]:
            raise IntakeError("Job rỗng hoặc quá số ảnh tối đa do operator cấu hình")
        deleted = set(meta.get("deleted_frames", []))
        selected, names = [], set()
        for offset, info in enumerate(frames):
            frame = start + offset
            if frame in deleted:
                continue
            image_id = Path(info["name"].replace("\\", "/")).stem
            from src.api.service import safe_id

            safe_id(image_id)
            if image_id in names:
                raise IntakeError("Tên ảnh trùng trong job; không tự đoán image_id")
            if (info["width"], info["height"]) != (contracts.IMG_W, contracts.IMG_H):
                raise IntakeError("Adapter hiện chỉ hỗ trợ BBox 1280×720 theo contract")
            names.add(image_id)
            selected.append(
                {
                    "image_id": image_id,
                    "task_id": task_id,
                    "job_id": job_id,
                    "frame": frame,
                    "source_name": info["name"],
                }
            )
        if not selected:
            raise IntakeError("Job không còn frame hợp lệ")
        labels, endpoint, seen = {}, f"api/labels?task_id={task_id}&page_size=100", set()
        while endpoint:
            if endpoint in seen:
                raise IntakeError("CVAT pagination lặp")
            seen.add(endpoint)
            page = self.get(endpoint)
            for label in page["results"]:
                if label["name"] not in contracts.BDD_CLASSES:
                    raise IntakeError("Class chưa thuộc BDD contract; cần class map được chốt")
                labels[int(label["id"])] = label
            endpoint = page.get("next")
        annotations = self.get(f"api/jobs/{job_id}/annotations")
        if annotations.get("tracks") or annotations.get("tags"):
            raise IntakeError("Chỉ hỗ trợ rectangle shapes, chưa hỗ trợ tracks/tags")
        by_frame = {item["frame"]: [] for item in selected}
        for shape in annotations["shapes"]:
            frame = int(shape["frame"])
            if frame in deleted:
                continue
            if frame not in by_frame:
                raise IntakeError("Nhãn không thuộc frame của job")
            if shape["type"] != "rectangle" or float(shape.get("rotation", 0)) != 0:
                raise IntakeError("Chưa hỗ trợ polygon/polyline/box xoay")
            points = [float(x) for x in shape["points"]]
            if (
                len(points) != 4
                or any(not math.isfinite(n) for n in points)
                or not 0 <= points[0] < points[2] <= contracts.IMG_W
                or not 0 <= points[1] < points[3] <= contracts.IMG_H
            ):
                raise IntakeError("Toạ độ BBox ngoài phạm vi hỗ trợ")
            label = labels[int(shape["label_id"])]
            specs = {int(a["id"]): a for a in label.get("attributes", [])}
            attrs = {"occluded": bool(shape["occluded"])}
            for attr in shape.get("attributes", []):
                spec = specs[int(attr["spec_id"])]
                value = attr["value"]
                if spec["input_type"] == "checkbox":
                    if value not in {"true", "false"}:
                        raise IntakeError("Checkbox attribute không hợp lệ")
                    value = value == "true"
                attrs[spec["name"]] = value
            by_frame[frame].append(
                {
                    "id": str(shape["id"]),
                    "category": label["name"],
                    "attributes": attrs,
                    "box2d": dict(zip(("x1", "y1", "x2", "y2"), points, strict=True)),
                }
            )
        return {
            "job": job,
            "meta": meta,
            "mapping": selected,
            "annotations": annotations,
            "labels": labels,
            "frames": [
                {"name": row["image_id"] + ".jpg", "attributes": {}, "labels": by_frame[row["frame"]]}
                for row in selected
            ],
        }

    def read_images(self, description, output, progress):
        (output / "images").mkdir(parents=True, exist_ok=True)
        hashes = {}
        for n, row in enumerate(description["mapping"]):
            raw = self.get(
                f"api/jobs/{row['job_id']}/data?type=frame&number={row['frame']}&quality=original", image=True
            )
            with Image.open(io.BytesIO(raw)) as image:
                if image.size != (contracts.IMG_W, contracts.IMG_H) or image.format not in {"JPEG", "PNG"}:
                    raise IntakeError("Ảnh gốc không khớp metadata/định dạng hỗ trợ")
                image.verify()
                suffix = ".jpg" if image.format == "JPEG" else ".png"
            target = output / "images" / (row["image_id"] + suffix)
            target.write_bytes(raw)
            hashes[row["image_id"]] = hashlib.sha256(raw).hexdigest()
            progress(n + 1, len(description["mapping"]))
        self.check_unchanged(description)
        return hashes

    def check_unchanged(self, description):
        job_id = description["mapping"][0]["job_id"]
        if canonical(self.get(f"api/jobs/{job_id}/annotations")) != canonical(
            description["annotations"]
        ) or canonical(self.get(f"api/jobs/{job_id}/data/meta")) != canonical(description["meta"]):
            raise IntakeError("Nhãn/metadata đã Save thay đổi trong lúc kiểm; hãy thử lại")
