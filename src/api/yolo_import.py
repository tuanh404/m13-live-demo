"""Read common YOLO detection archives without extracting or following metadata paths."""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from pathlib import PurePosixPath

from fastapi import HTTPException

IMPORTER_VERSION = "yolo-auto-v2"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
CLASS_FILES = {"classes.txt", "obj.names", "data.yaml", "data.yml"}
IGNORED_METADATA = {
    "obj.data", "train.txt", "valid.txt", "val.txt", "test.txt", "README.txt", "README.md",
    "README.dataset.txt", "README.roboflow.txt",
}


def fail(message):
    raise HTTPException(422, message)


def _ultralytics_key(path, kind):
    parts = path.parts
    if len(parts) >= 2 and parts[0] == kind:
        return PurePosixPath(*parts[1:]).with_suffix("").as_posix()
    if len(parts) >= 3 and parts[0] in {"train", "val", "valid", "test"} and parts[1] == kind:
        return PurePosixPath(parts[0], *parts[2:]).with_suffix("").as_posix()
    return None


def read_yolo_zip(raw, cfg):
    """Return the existing canonical layout plus source mapping for immutable provenance."""
    if len(raw) > cfg["max_zip_bytes"]:
        raise HTTPException(413, "Gói ZIP vượt5MB.")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        if len(entries) > cfg["max_entries"] or sum(i.file_size for i in entries) > cfg["max_unpacked_bytes"]:
            fail("ZIP có quá nhiều file hoặc vượt20MB sau giải nén.")
        files, seen = {}, set()
        for entry in entries:
            name = entry.filename
            path = PurePosixPath(name)
            if (
                path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name
                or entry.orig_filename != name
                or any(ord(c) < 32 for c in name) or str(path) != name.rstrip("/")
                or entry.flag_bits & 1
                or (entry.external_attr >> 16) & 0o170000 == 0o120000
            ):
                fail("ZIP có đường dẫn, liên kết hoặc mã hóa không được hỗ trợ.")
            if entry.is_dir():
                continue
            if name.casefold() in seen:
                fail("ZIP có tên file trùng hoặc mơ hồ.")
            seen.add(name.casefold())
            if "__MACOSX" in path.parts or path.name == ".DS_Store":
                continue
            files[name] = archive.read(entry)

    metadata = [
        n for n in files if PurePosixPath(n).name in CLASS_FILES
        and not any(
            part in {"images", "labels"} or re.fullmatch(r"obj_[A-Za-z0-9_-]+_data", part)
            for part in PurePosixPath(n).parts[:-1]
        )
    ]
    if len(metadata) != 1:
        fail(
            "Cần đúng một danh sách lớp: obj.names (YOLO1.1), classes.txt hoặc data.yaml/data.yml "
            "(YOLO Detection). ZIP COCO/XML, polygon và định dạng khác chưa hỗ trợ."
        )
    class_file = metadata[0]
    root = PurePosixPath(class_file).parent
    local = {}
    original = {}
    for name, data in files.items():
        try:
            relative = PurePosixPath(name).relative_to(root).as_posix()
        except ValueError:
            fail("ZIP chứa nhiều bộ dữ liệu khác nhau; hãy chọn ZIP của một bộ ảnh.")
        local[relative], original[relative] = data, name

    cvat = PurePosixPath(class_file).name == "obj.names"
    photos, labels = {}, {}
    for name in local:
        path = PurePosixPath(name)
        if name == PurePosixPath(class_file).name or name in IGNORED_METADATA:
            continue
        suffix = path.suffix.lower()
        if cvat:
            if len(path.parts) < 2 or not re.fullmatch(r"obj_[A-Za-z0-9_-]+_data", path.parts[0]):
                fail("ZIP YOLO1.1 cần ảnh và nhãn trong obj_train_data/ hoặc obj_valid_data/.")
            key = path.with_suffix("").as_posix()
        else:
            kind = "images" if suffix in IMAGE_EXTENSIONS else "labels"
            key = _ultralytics_key(path, kind)
            if key is None:
                fail("ZIP YOLO Detection cần images/ và labels/ (có thể có train/val/test bên trong).")
        if suffix in IMAGE_EXTENSIONS:
            collection = photos
        elif suffix == ".txt":
            collection = labels
        else:
            fail("ZIP chỉ nhận ảnh JPG/PNG và nhãn YOLO box .txt; chưa hỗ trợ định dạng này.")
        if key in collection:
            fail("ZIP có ảnh hoặc nhãn trùng tên, không thể ghép an toàn.")
        collection[key] = name

    if not photos:
        fail(
            "ZIP chỉ có nhãn, chưa có ảnh JPG/PNG. Cần xuất kèm ảnh hoặc lấy ảnh gốc từ người tạo task; "
            "không thể tạo lại ảnh từ file nhãn."
        )
    if len(photos) > cfg["max_images"]:
        fail("Mỗi bộ hỗ trợ tối đa10ảnh. Hãy xuất một bộ nhỏ hơn.")
    if set(photos) != set(labels):
        missing = len(set(labels) - set(photos))
        if missing:
            fail(f"ZIP thiếu ảnh cho {missing} file nhãn. Cần xuất kèm ảnh gốc cùng bộ.")
        fail("Mỗi ảnh cần đúng một file nhãn cùng tên và thư mục tương ứng; ảnh không box dùng .txt rỗng.")

    normalized, sources, used = {}, {}, set()
    for key in sorted(photos):
        photo, label = photos[key], labels[key]
        stem = PurePosixPath(photo).stem
        image_id = stem if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", stem) else (
            "image-" + hashlib.sha256(original[photo].encode()).hexdigest()[:24]
        )
        if image_id.casefold() in used:
            fail("Các thư mục có ảnh trùng tên; hãy xuất riêng từng bộ để tránh ghép nhầm nhãn.")
        used.add(image_id.casefold())
        normalized[f"images/{image_id}{PurePosixPath(photo).suffix.lower()}"] = local[photo]
        normalized[f"labels/{image_id}.txt"] = local[label]
        sources[image_id] = {"image": original[photo], "label": original[label]}
    target = "data.yaml" if class_file.endswith((".yaml", ".yml")) else "classes.txt"
    normalized[target] = files[class_file]
    return normalized, {
        "importer_version": IMPORTER_VERSION,
        "input_format": "CVAT YOLO1.1" if cvat else "YOLO Detection",
        "class_file": class_file,
        "source_files": sources,
        "metadata_paths_followed": False,
    }
