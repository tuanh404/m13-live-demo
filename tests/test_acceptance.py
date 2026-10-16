import json
from pathlib import Path

import pytest

from src.api.acceptance import inspect_batch, write_new
from src.api.fixtures import prepare_scored


def test_checklist_never_promotes_fixture_or_inputs_to_real_acceptance(tmp_path):
    folder = Path(prepare_scored(tmp_path / "fixture", count=10)["folder"])
    result = inspect_batch(folder)
    assert result["n_images"] == 10 and len(result["photo_sha256"]) == 10
    assert not result["real_bdd_acceptance"] and not result["mapping_ready"]
    assert set(result["runtime_checklist"].values()) == {"pending"}
    assert result["data_kind"] == "development_fixture_or_unverified"
    output = tmp_path / "checklist.json"
    write_new(output, result)
    assert json.loads(output.read_text())["real_bdd_acceptance"] is False
    with pytest.raises(FileExistsError):
        write_new(output, result)
    with pytest.raises(ValueError, match="trùng ảnh"):
        inspect_batch(folder, excluded_batches=[folder])


def test_checklist_blocks_missing_images_tampered_artifacts_and_wrong_count(tmp_path):
    folder = Path(prepare_scored(tmp_path / "fixture", count=10)["folder"])
    with pytest.raises(ValueError, match="count"):
        inspect_batch(folder, expected=30)
    photo = next((folder / "images").glob("*.jpg"))
    photo.write_bytes(b"not an image")
    with pytest.raises(ValueError, match="Artifact đã đổi"):
        inspect_batch(folder)


def test_original_bdd_alias_is_valid_without_changing_raw_labels(tmp_path):
    from src import pipeline

    folder = Path(prepare_scored(tmp_path / "alias", count=3)["folder"])
    manifest_file = next(folder.glob("*.manifest.json"))
    manifest = json.loads(manifest_file.read_text())
    labels_file = pipeline.located(manifest["labels_file"])
    labels = json.loads(labels_file.read_text())
    labels[0]["labels"][0]["category"] = "person"
    labels_file.write_text(json.dumps(labels))
    manifest["labels_sha256"] = pipeline.sha256(labels_file)
    manifest_file.write_text(json.dumps(manifest))
    record_file = folder / "review.json"
    record = json.loads(record_file.read_text())
    for path in (labels_file, manifest_file):
        record["files"][path.name] = pipeline.sha256(path)
    record_file.write_text(json.dumps(record))
    assert inspect_batch(folder, expected=3)["n_images"] == 3
    assert json.loads(labels_file.read_text())[0]["labels"][0]["category"] == "person"
