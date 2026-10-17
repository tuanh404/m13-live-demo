"""Authenticated, small YOLO batches; durable snapshots use the existing review store."""

from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import math
import re
import tempfile
import threading
import zipfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import yaml
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, Response
from starlette.concurrency import run_in_threadpool

from src import config, pipeline
from src.api.saved_labels import canonical
from src.features import geometric, simple_signals

SCOPE = (
    "Kiểm một phần: hình học/ngữ cảnh, không chạy detector hoặc guideline. "
    "Không phát hiện chắc chắn box lệch vật thể hay vật thể bị bỏ sót. "
    "Các ngưỡng là heuristic kỹ thuật; thống kê bất thường phụ thuộc cỡ bộ ảnh. Điểm 0 vẫn có thể có lỗi."
)


def fail(message):
    raise HTTPException(422, message)


def parse_zip(raw, cfg):
    from PIL import Image, UnidentifiedImageError

    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
        entries = archive.infolist()
        if len(entries) > cfg["max_entries"] or sum(i.file_size for i in entries) > cfg["max_unpacked_bytes"]:
            fail("ZIP có quá nhiều file hoặc vượt20MB sau giải nén.")
        files = {}
        for entry in entries:
            name = entry.filename
            path = PurePosixPath(name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in name
                or "\x00" in name
                or str(path) != name.rstrip("/")
                or entry.flag_bits & 1
                or (entry.external_attr >> 16) & 0o170000 == 0o120000
            ):
                fail("ZIP có đường dẫn, liên kết hoặc mã hóa không được hỗ trợ.")
            if entry.is_dir():
                continue
            if name.casefold() in {n.casefold() for n in files}:
                fail("ZIP có tên file trùng hoặc mơ hồ.")
            allowed = (
                name in {"classes.txt", "data.yaml"}
                or re.fullmatch(r"images/[A-Za-z0-9][A-Za-z0-9_-]{0,79}\.(jpg|jpeg|png)", name)
                or re.fullmatch(r"labels/[A-Za-z0-9][A-Za-z0-9_-]{0,79}\.txt", name)
            )
            if not allowed:
                fail("ZIP chỉ nhận images/*.jpg|jpeg|png, labels/*.txt và classes.txt hoặc data.yaml.")
            files[name] = archive.read(entry)
        if ("classes.txt" in files) == ("data.yaml" in files):
            fail("Cần đúng một file classes.txt hoặc data.yaml để xác định tên lớp.")
        if "classes.txt" in files:
            names = files["classes.txt"].decode("utf-8-sig").splitlines()
        else:
            if len(files["data.yaml"]) > 10000:
                fail("data.yaml quá lớn.")
            data = yaml.safe_load(files["data.yaml"].decode("utf-8-sig"))
            names = data.get("names") if isinstance(data, dict) else None
            if isinstance(names, dict):
                if set(names) != set(range(len(names))):
                    fail("Chỉ số names trong data.yaml phải liên tiếp từ0.")
                names = [names[i] for i in range(len(names))]
        if (
            not isinstance(names, list)
            or not names
            or not all(isinstance(n, str) and n.strip() for n in names)
        ):
            fail("Danh sách tên lớp thiếu hoặc không hợp lệ.")
        class_map = config.load("class_map")
        names = [class_map["rename"].get(n.strip(), n.strip()) for n in names]
        if len(set(names)) != len(names) or not set(names) <= set(class_map["classes"]):
            fail("Tên lớp cần duy nhất và thuộc10lớp BDD trong hướng dẫn.")
        photos = {PurePosixPath(n).stem: n for n in files if n.startswith("images/")}
        photo_names = [n for n in files if n.startswith("images/")]
        labels = {PurePosixPath(n).stem: n for n in files if n.startswith("labels/")}
        if not 1 <= len(photos) <= cfg["max_images"] or len(photos) != len(photo_names):
            fail("Cần1–10ảnh, tên ảnh không trùng dù khác đuôi file.")
        if set(photos) != set(labels):
            fail("Mỗi ảnh cần đúng một file nhãn cùng tên. Ảnh không có box dùng file .txt rỗng.")
        frames, images, hashes = [], {}, {}
        for image_id, name in sorted(photos.items()):
            with Image.open(io.BytesIO(files[name])) as im:
                if im.format not in {"JPEG", "PNG"} or im.size != (1280, 720):
                    fail(f"{name}: cần ảnh JPG/PNG1280×720; không tự đổi kích thước hay tọa độ.")
                if im.getexif().get(274, 1) != 1:
                    fail(f"{name}: ảnh có xoay EXIF; hãy xuất ảnh và nhãn về cùng hướng trước.")
                im.load()
                buf = io.BytesIO()
                im.convert("RGB").save(buf, format="JPEG", quality=95)
                images[image_id + ".jpg"] = buf.getvalue()
            rows = files[labels[image_id]].decode("utf-8-sig").splitlines()
            if len(rows) > cfg["max_boxes_per_image"]:
                fail(f"{image_id}: vượt500box/ảnh.")
            boxes = []
            for line, row in enumerate(rows, 1):
                if not row.strip():
                    continue
                parts = row.split()
                if len(parts) != 5 or not parts[0].isdigit():
                    fail(
                        f"{image_id}, dòng{line}: cần class_id x_center y_center width height; "
                        "không nhận polygon."
                    )
                cls = int(parts[0])
                values = list(map(float, parts[1:]))
                if cls >= len(names) or not all(math.isfinite(v) for v in values):
                    fail(f"{image_id}, dòng{line}: class hoặc tọa độ không hợp lệ.")
                x, y, w, h = values
                if not (
                    w > 0 and h > 0 and 0 <= x - w / 2 < x + w / 2 <= 1 and 0 <= y - h / 2 < y + h / 2 <= 1
                ):
                    fail(f"{image_id}, dòng{line}: box phải nằm trong ảnh, tọa độ YOLO chuẩn hóa0–1.")
                boxes.append(
                    {
                        "id": str(len(boxes) + 1),
                        "category": names[cls],
                        "box2d": dict(
                            zip(
                                ("x1", "y1", "x2", "y2"),
                                (
                                    (x - w / 2) * 1280,
                                    (y - h / 2) * 720,
                                    (x + w / 2) * 1280,
                                    (y + h / 2) * 720,
                                ),
                                strict=True,
                            )
                        ),
                    }
                )
            frames.append({"name": image_id + ".jpg", "labels": boxes})
            hashes[image_id] = hashlib.sha256(files[name]).hexdigest()
        return frames, images, hashes
    except HTTPException:
        raise
    except (
        zipfile.BadZipFile,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        RecursionError,
    ):
        fail("Không đọc được ZIP, ảnh hoặc nhãn. Hãy dùng cấu trúc gói mẫu và thử lại.")


def sample_zip():
    from PIL import Image, ImageDraw

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("classes.txt", "car\ntruck\n")
        for name, rows in [
            ("clean", "0 0.5 0.55 0.25 0.2\n"),
            ("duplicate", "0 0.5 0.55 0.25 0.2\n0 0.5 0.55 0.25 0.2\n"),
            ("overlap", "0 0.5 0.55 0.25 0.2\n1 0.5 0.55 0.25 0.2\n"),
        ]:
            im = Image.new("RGB", (1280, 720), "#d5e4ef")
            draw = ImageDraw.Draw(im)
            draw.rectangle((0, 420, 1280, 720), fill="#65717b")
            draw.rounded_rectangle((485, 340, 795, 465), radius=30, fill="#366ea1")
            draw.ellipse((525, 430, 585, 490), fill="#263341")
            draw.ellipse((700, 430, 760, 490), fill="#263341")
            draw.text((30, 30), "SYNTHETIC TEST IMAGE - not human pilot", fill="#263341")
            buf = io.BytesIO()
            im.save(buf, format="JPEG")
            z.writestr(f"images/{name}.jpg", buf.getvalue())
            z.writestr(f"labels/{name}.txt", rows)
    return out.getvalue()


class Uploads:
    def __init__(self, settings, store):
        self.settings, self.store = settings, store
        self.cfg = config.load("upload")
        self.root = Path(tempfile.mkdtemp(prefix="m13-uploads-"))
        self.lock = threading.Lock()
        self.apps = {}
        options = copy.deepcopy(config.load("pipeline"))
        defaults = {**geometric.DEFAULTS, **simple_signals.DEFAULTS}
        options["signal_options"] = {
            n: {**defaults[n], **options.get("signal_options", {}).get(n, {})} for n in self.cfg["signals"]
        }
        self.profile = {
            "signals": self.cfg["signals"],
            "options": options,
            "weights": config.load("weights")["signals"],
        }

    @staticmethod
    def owner(request):
        identity = getattr(request.state, "auth_identity", None)
        if not identity:
            raise HTTPException(401, "Cần mở một phiên trước khi tải bộ ảnh.")
        return hashlib.sha256(identity["reviewer"].encode()).hexdigest()

    def owned(self, key, owner):
        if not re.fullmatch("[a-f0-9]{32}", key):
            raise HTTPException(404, "Không tìm thấy bộ ảnh trong phiên của bạn.")
        record = self.store.state("upload-batch:" + key)
        if not record or record["owner"] != owner:
            raise HTTPException(404, "Không tìm thấy bộ ảnh trong phiên của bạn.")
        return record

    @staticmethod
    def public(record):
        return {k: record[k] for k in ("id", "images", "created_at", "review_url", "queue_id")}

    def upload(self, raw, owner):
        if len(raw) > self.cfg["max_zip_bytes"]:
            raise HTTPException(413, "Gói ZIP vượt5MB.")
        key = hashlib.sha256(
            owner.encode() + hashlib.sha256(raw).digest() + canonical(self.profile)
        ).hexdigest()[:32]
        old = self.store.state("upload-batch:" + key)
        if old:
            return {**self.public(old), "reused": True}
        frames, images, hashes = parse_zip(raw, self.cfg)
        self.root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="stage-", dir=self.root) as stage:
            folder = Path(stage)
            (folder / "images").mkdir()
            for name, image in images.items():
                (folder / "images" / name).write_bytes(image)
            version = "upload-" + key
            result = pipeline.publish(
                frames,
                folder,
                version,
                names=self.profile["signals"],
                options=self.profile["options"],
                weights=self.profile["weights"],
                provenance={
                    "source": "user_yolo_upload",
                    "zip_sha256": hashlib.sha256(raw).hexdigest(),
                    "source_image_sha256": hashes,
                    "image_sha256": {Path(n).stem: hashlib.sha256(b).hexdigest() for n, b in images.items()},
                    "scope": SCOPE,
                    "image_conversion": "JPEG, no resize",
                },
            )
            blobs = {
                str(p.relative_to(folder)): base64.b64encode(p.read_bytes()).decode()
                for p in folder.rglob("*")
                if p.is_file()
            }
            snapshot = canonical(blobs).decode()
            record = {
                "id": key,
                "review_session": "batch-" + key,
                "owner": owner,
                "images": len(frames),
                "stored_bytes": len(snapshot),
                "created_at": datetime.now(UTC).isoformat(),
                "review_url": f"/batches/{key}/",
                "queue_id": result["queue_sha256"],
                "snapshot_sha256": hashlib.sha256(snapshot.encode()).hexdigest(),
            }
            with self.store.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                previous = db.execute(
                    "SELECT value FROM state WHERE key=?", ("upload-batch:" + key,)
                ).fetchone()
                if previous:
                    return {**self.public(json.loads(previous[0])), "reused": True}
                records = [
                    json.loads(r[0])
                    for r in db.execute(
                        "SELECT value FROM state WHERE substr(key,1,13)='upload-batch:'"
                    ).fetchall()
                ]
                if sum(r["owner"] == owner for r in records) >= self.cfg["max_batches_per_session"]:
                    raise HTTPException(409, "Phiên này đã có5bộ ảnh. Tiếp tục review các bộ đã tải.")
                if sum(r["stored_bytes"] for r in records) + len(snapshot) > self.cfg["max_stored_bytes"]:
                    raise HTTPException(503, "Kho thử nghiệm đã đầy; nhờ người phụ trách lưu trữ hỗ trợ.")
                for name, value in [
                    ("upload-assets:" + key, snapshot),
                    ("upload-batch:" + key, json.dumps(record)),
                ]:
                    db.execute("INSERT INTO state VALUES (?,?)", (name, value))
            return {**self.public(record), "reused": False}

    def application(self, key, owner):
        record = self.owned(key, owner)
        with self.lock:
            if key in self.apps:
                return self.apps[key]
            with self.store.connection() as db:
                row = db.execute("SELECT value FROM state WHERE key=?", ("upload-assets:" + key,)).fetchone()
            if not row or hashlib.sha256(row[0].encode()).hexdigest() != record["snapshot_sha256"]:
                raise HTTPException(503, "Snapshot thiếu hoặc sai hash; không dùng dữ liệu cũ.")
            folder = self.root / key
            folder.mkdir(exist_ok=True)
            for name, encoded in json.loads(row[0]).items():
                p = folder / name
                if not p.resolve().is_relative_to(folder.resolve()):
                    raise HTTPException(503, "Snapshot có đường dẫn không hợp lệ.")
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(base64.b64decode(encoded, validate=True))
            version = "upload-" + key
            manifest_path = folder / f"ranked_queue_{version}.manifest.json"
            manifest = json.loads(manifest_path.read_text())
            for kind, suffix in [
                ("queue", "csv"),
                ("labels", "json"),
                ("evidence", "jsonl"),
                ("features", "parquet"),
            ]:
                name = f"ranked_queue_{version}" if kind == "queue" else f"{kind}_{version}"
                manifest[kind + "_file"] = str(folder / f"{name}.{suffix}")
            manifest["manifest_file"] = str(manifest_path)
            manifest_path.write_bytes(canonical(manifest))
            from src.api.main import create_app

            child = replace(
                self.settings,
                uploads_enabled=False,
                store_namespace="upload:" + key + ":",
                accounts_file=None,
                public_origin="",
                intake_config=None,
                queue_file=folder / f"ranked_queue_{version}.csv",
                queue_batches={},
                evidence_file=None,
                reports=folder,
                images=folder / "images",
                mapping=folder / "absent-map.parquet",
                predictions=folder / "absent-predictions.parquet",
                recheck_backend=None,
                retrain_backend=None,
                evaluation_file=None,
                pilot_arm_file=None,
                review_batch=None,
                guideline_url="",
                data_purpose="development",
            )
            self.apps[key] = create_app(child)
            return self.apps[key]


def install_uploads(app, settings, store):
    if not settings.uploads_enabled:
        return
    registry = Uploads(settings, store)
    app.state.uploads = registry

    @app.get("/my-batches", include_in_schema=False)
    def page():
        return FileResponse(Path(__file__).with_name("web") / "uploads.html")

    @app.get("/my-batches/list")
    def batches(request: Request):
        owner = registry.owner(request)
        return {
            "items": [
                registry.public(r) for r in store.state_items("upload-batch:").values() if r["owner"] == owner
            ],
            "scope": SCOPE,
        }

    @app.get("/my-batches/sample.zip")
    def sample(request: Request):
        registry.owner(request)
        return Response(
            sample_zip(),
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="M13-yolo-sample.zip"'},
        )

    @app.post("/my-batches/upload")
    async def upload(request: Request):
        owner = registry.owner(request)
        raw = await request.body()
        return await run_in_threadpool(registry.upload, raw, owner)

    @app.api_route("/batches/{key}/{path:path}", methods=["GET", "POST"])
    async def dispatch(key: str, path: str, request: Request):
        owner = registry.owner(request)
        allowed = (request.method == "POST" and path == "verdict") or (
            request.method == "GET"
            and (
                path in {"", "health", "queue", "stats", "web/context"}
                or re.fullmatch(r"web/review/[A-Za-z0-9_-]+", path)
                or re.fullmatch(r"image/[A-Za-z0-9_-]+/file", path)
            )
        )
        if not allowed:
            raise HTTPException(404, "Chức năng không áp dụng cho bộ ảnh tải lên.")
        child = await run_in_threadpool(registry.application, key, owner)

        class Forward(Response):
            async def __call__(self, scope, receive, send):
                await child(dict(scope, path="/" + path, raw_path=("/" + path).encode()), receive, send)

        return Forward()
