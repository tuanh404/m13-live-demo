"""Read-only input checklist. Available files are not end-to-end acceptance evidence."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
from PIL import Image

from src import config, contracts, pipeline
from src.api.review_setup import exclusion_ids, verify
from src.api.service import QueueService
from src.api.settings import Settings
from src.api.store import ReviewStore

RUNTIME_CHECKS = (
    "correct_image_and_boxes",
    "three_verdicts",
    "lost_ack_retry",
    "process_restart",
    "timer_focus_reload",
    "saved_recheck_changed",
    "saved_recheck_unchanged",
)


def inspect_batch(folder: Path, *, expected=10, excluded_batches=()):
    folder = folder.resolve()
    record = verify(folder)
    queue = folder / f"ranked_queue_{record['version']}.csv"
    frame = pd.read_csv(queue, dtype={"image_id": str, "model_version": str}).fillna("")
    errors = contracts.check_queue(frame)
    if errors or len(frame) != expected:
        raise ValueError(f"Queue/count không đúng: {errors}; cần {expected}, có {len(frame)}")
    manifest = json.loads(queue.with_suffix(".manifest.json").read_text())
    for kind in ("queue", "labels", "evidence", "features"):
        if pipeline.sha256(pipeline.located(manifest[kind + "_file"])) != manifest[kind + "_sha256"]:
            raise ValueError(f"Artifact khác hash: {kind}")
    ids = set(frame.image_id)
    if ids & exclusion_ids(excluded_batches):
        raise ValueError("Batch trùng ảnh với batch cần cách ly (demo/pilot)")
    frames = json.loads(pipeline.located(manifest["labels_file"]).read_text())
    names = [Path(f["name"]).stem for f in frames]
    if len(set(names)) != len(names) or set(names) != ids:
        raise ValueError("Snapshot nhãn thiếu/trùng/thừa ảnh")
    for source in frames:
        for obj in source.get("labels") or []:
            if not obj.get("box2d"):
                continue
            box = [float(obj["box2d"][k]) for k in ("x1", "y1", "x2", "y2")]
            if (
                config.load("class_map")["rename"].get(obj["category"], obj["category"])
                not in contracts.BDD_CLASSES
                or not all(math.isfinite(n) for n in box)
                or not 0 <= box[0] < box[2] <= contracts.IMG_W
                or not 0 <= box[1] < box[3] <= contracts.IMG_H
            ):
                raise ValueError("Class/toạ độ nhãn không đúng contract")
    settings = Settings(
        queue_file=queue,
        images=folder / "images",
        database=folder / "review.db",
        mapping=folder / "cvat_map.parquet",
        evidence_file=pipeline.located(manifest["evidence_file"]),
    )
    service = QueueService(settings, ReviewStore(settings.database, settings.database_url))
    evidence, warnings = service.evidence(queue)
    if warnings or set(evidence) != ids:
        raise ValueError(f"Evidence không khớp ảnh: {warnings}")
    photos = {}
    for image_id in sorted(ids):
        photo = service.image_path(image_id)
        if photo is None:
            raise ValueError(f"Thiếu ảnh {image_id}")
        with Image.open(photo) as image:
            if image.size != (contracts.IMG_W, contracts.IMG_H):
                raise ValueError("Ảnh không đúng kích thước contract")
            image.verify()
        photos[image_id] = pipeline.sha256(photo)
    mapping, mapping_warnings = service.mapping()
    mapped = set(mapping) == ids and not mapping_warnings
    real = (
        record["purpose"] == "real"
        and record.get("annotation_kind") == "original"
        and "fixture" not in record["version"].lower()
        and record["identity"].get("original_labels_sha256")
        == config.load("review_acceptance")["labels_sha256"]
    )
    return {
        "schema_version": 1,
        "data_kind": "bdd_inputs" if real else "development_fixture_or_unverified",
        "expected_images": expected,
        "n_images": len(frame),
        "queue_id": pipeline.sha256(queue),
        "labels_sha256": manifest["labels_sha256"],
        "model_version": record["version"],
        "photo_sha256": photos,
        "mapping_sha256": pipeline.sha256(settings.mapping) if mapped else None,
        "mapping_ready": mapped,
        "mapping_warnings": mapping_warnings,
        "inputs_checked": [
            "artifact_hashes",
            "queue_contract",
            "labels_class_coordinates",
            "image_decode_dimensions_hashes",
            "evidence_images",
            "demo_pilot_disjoint",
        ],
        "runtime_checklist": {key: "pending" for key in RUNTIME_CHECKS},
        "real_bdd_acceptance": False,
        "photo_origin": "Operator-supplied images; hashes recorded; visual provenance needs acceptance",
        "status": "inputs_ready_for_runtime" if real and mapped else "not_real_bdd_acceptance",
        "note": "Preflight không phải nghiệm thu runtime; fixture/automatic sessions không phải human pilot.",
    }


def write_new(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.write("\n")
