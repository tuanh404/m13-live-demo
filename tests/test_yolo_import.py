import io
import zipfile

import pytest
from fastapi import HTTPException

from src.api.uploads import parse_zip, sample_zip
from src.config import load


def archive_of(files):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            z.writestr(name, content)
    return out.getvalue()


def repack_yolo(raw, layout="cvat", prefix=""):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        original = {n: z.read(n) for n in z.namelist()}
    if layout == "cvat":
        files = {
            "obj.names": original["classes.txt"],
            "obj.data": b"classes = 2\nnames = data/obj.names\ntrain = data/train.txt\n",
            "train.txt": b"data/obj_train_data/clean.jpg\ndata/obj_train_data/duplicate.jpg\n"
            b"data/obj_train_data/overlap.jpg\n",
        }
        for name, content in original.items():
            if name != "classes.txt":
                files["obj_train_data/" + name.split("/")[-1]] = content
    elif layout in {"ultralytics", "split-first"}:
        files = {"data.yaml": b"names: [car, truck]\npath: /not-read\ntrain: images/train\n"}
        for name, content in original.items():
            if name != "classes.txt":
                folder, filename = name.split("/")
                files[(f"{folder}/train/" if layout == "ultralytics" else f"train/{folder}/")
                      + filename] = content
    else:
        files = original
    return archive_of({prefix + n: b for n, b in files.items()})


@pytest.mark.parametrize("layout", ["cvat", "ultralytics", "split-first", "canonical"])
@pytest.mark.parametrize("prefix", ["", "my-export/"])
def test_detection_auto_import_preserves_boxes_images_hashes_and_provenance(layout, prefix):
    raw = sample_zip()
    expected = parse_zip(raw, load("upload"))
    provenance = {}
    actual = parse_zip(repack_yolo(raw, layout, prefix), load("upload"), provenance=provenance)
    assert actual == expected
    assert provenance["importer_version"] == "yolo-auto-v2"
    assert provenance["input_format"] == ("CVAT YOLO1.1" if layout == "cvat" else "YOLO Detection")
    assert len(provenance["source_files"]) == 3
    assert provenance["source_files"]["duplicate"]["image"].startswith(prefix)
    assert not provenance["metadata_paths_followed"]


def test_class_order_is_not_sorted_and_unicode_names_do_not_become_paths():
    with zipfile.ZipFile(io.BytesIO(sample_zip())) as z:
        picture = z.read("images/clean.jpg")
    files = {
        "folder/obj.names": "truck\ncar\n",
        "folder/obj_train_data/ảnh xe (01).JPG": picture,
        "folder/obj_train_data/ảnh xe (01).txt": "1 .5 .5 .2 .4\n",
    }
    source = {}
    frames, images, hashes = parse_zip(archive_of(files), load("upload"), provenance=source)
    assert frames[0]["labels"][0]["category"] == "car"
    assert frames[0]["labels"][0]["box2d"] == pytest.approx(
        {"x1": 512., "y1": 216., "x2": 768., "y2": 504.}
    )
    assert list(images)[0].startswith("image-") and len(hashes) == 1
    assert list(source["source_files"].values())[0]["image"].endswith("ảnh xe (01).JPG")
    assert parse_zip(archive_of(files), load("upload")) == (frames, images, hashes)


def test_label_named_classes_and_yaml_yml_alias():
    with zipfile.ZipFile(io.BytesIO(sample_zip())) as z:
        picture = z.read("images/clean.jpg")
    files = {"data.yml": "names: [car]", "images/classes.JPG": picture, "labels/classes.txt": ""}
    assert parse_zip(archive_of(files), load("upload"))[0][0]["labels"] == []


@pytest.mark.parametrize("layout", ["cvat", "ultralytics"])
def test_labels_only_clearly_requests_missing_images(layout):
    raw = repack_yolo(sample_zip(), layout)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        files = {n: z.read(n) for n in z.namelist() if not n.endswith(".jpg")}
    with pytest.raises(HTTPException) as error:
        parse_zip(archive_of(files), load("upload"))
    assert "ZIP chỉ có nhãn" in error.value.detail


@pytest.mark.parametrize("issue", ["metadata", "orphan", "traversal", "ambiguous", "outside-root"])
def test_auto_detection_does_not_guess_ambiguous_or_unsafe_data(issue):
    with zipfile.ZipFile(io.BytesIO(repack_yolo(sample_zip(), "cvat"))) as z:
        files = {n: z.read(n) for n in z.namelist()}
    if issue == "metadata":
        files["classes.txt"] = b"truck\ncar\n"
    elif issue == "orphan":
        del files["obj_train_data/clean.jpg"]
    elif issue == "traversal":
        files["obj_train_data/../outside.jpg"] = b"bad"
    elif issue == "outside-root":
        files = {"export/" + n: b for n, b in files.items()}
        files["outside.jpg"] = b"bad"
    else:
        files["obj_valid_data/clean.jpg"] = files["obj_train_data/clean.jpg"]
        files["obj_valid_data/clean.txt"] = files["obj_train_data/clean.txt"]
    with pytest.raises(HTTPException) as error:
        parse_zip(archive_of(files), load("upload"))
    assert error.value.status_code == 422


def test_metadata_paths_are_never_followed_and_class_ids_remain_authoritative():
    with zipfile.ZipFile(io.BytesIO(repack_yolo(sample_zip(), "cvat"))) as z:
        files = {n: z.read(n) for n in z.namelist()}
    files["obj.data"] = b"names = https://invalid.example/secret\ntrain = ../../private.txt\n"
    assert len(parse_zip(archive_of(files), load("upload"))[0]) == 3


def test_not_every_zip_is_a_supported_annotation_format():
    with pytest.raises(HTTPException) as error:
        parse_zip(archive_of({"annotations/instances.json": "{}"}), load("upload"))
    assert "COCO/XML" in error.value.detail
