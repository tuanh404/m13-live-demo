"""Prepare two isolated arms, without enrolling a person or recording a verdict."""

from __future__ import annotations

import hashlib
import json
from contextlib import ExitStack
from pathlib import Path
from uuid import uuid4

from src import config, pipeline
from src.api.acceptance import inspect_batch, write_new
from src.api.review_setup import prepare, verify
from src.api.saved_labels import SavedLabels, atomic_json, canonical
from src.api.service import QueueService
from src.api.settings import Settings
from src.api.store import ReviewStore


def baseline_from_frames(frames):
    rename = config.load("class_map")["rename"]
    result = []
    for frame in sorted(frames, key=lambda f: f["name"]):
        boxes = []
        for label in frame.get("labels") or []:
            if not label.get("box2d"):
                continue
            attrs = label.get("attributes") or {}
            boxes.append(
                {
                    "category": rename.get(label["category"], label["category"]),
                    "box": [float(label["box2d"][k]) for k in ("x1", "y1", "x2", "y2")],
                    "attributes": {
                        "occluded": bool(attrs.get("occluded", False)),
                        "truncated": bool(attrs.get("truncated", False)),
                    },
                }
            )
        result.append({"image_id": Path(frame["name"]).stem, "boxes": sorted(boxes, key=canonical)})
    return hashlib.sha256(canonical(result)).hexdigest()


def prepare_pair(source: Path, output: Path, *, original_labels=None):
    source, output = source.resolve(), output.resolve()
    record = verify(source)
    expected = config.load("review_acceptance")["pilot_images"]
    if record["images"] != expected or record["identity"]["role"] != "pilot":
        raise ValueError("Cần batch pilot30ảnh đã chuẩn bị, không dùng batch demo")
    if output.exists():
        raise ValueError("Pair đã có; không ghi đè task/DB/nhãn")
    output.parent.mkdir(parents=True, exist_ok=True)
    # prepare() embeds final paths, so create final arms; on failure retain for inspection, never reset data.
    output.mkdir()
    comparison_id = "pilot-" + uuid4().hex[:12]
    for order in ("priority", "file"):
        folder = output / order
        prepared = prepare(
            source / f"ranked_queue_{record['version']}.csv",
            source / "images",
            folder,
            source_root=source,
            limit=expected,
            purpose=record["purpose"],
            role="pilot",
            original_labels=original_labels,
            cvat_url=record["identity"]["cvat_url"],
        )
        manifest = json.loads((folder / f"ranked_queue_{prepared['version']}.manifest.json").read_text())
        descriptor = {
            "schema_version": 1,
            "comparison_id": comparison_id,
            "order": order,
            "n_images": expected,
            "queue_id": manifest["queue_sha256"],
            "purpose": record["purpose"],
            "annotation_baseline_sha256": baseline_from_frames(
                json.loads(pipeline.located(manifest["labels_file"]).read_text())
            ),
            "peer_database": pipeline.portable(
                output / ("file" if order == "priority" else "priority") / "review.db"
            ),
            "setup_frozen": False,
            "time_scope": "web_active_seconds_no_cvat_editing",
            "instructions": "Không sửa nhãn pilot; chỉ đối chiếu và chọn verdict. Chưa xem batch trước.",
        }
        atomic_json(folder / "pilot-arm.json", descriptor)
        with (folder / "runtime.env").open("a") as env:
            import shlex

            env.write("export M13_PILOT_ARM_FILE=" + shlex.quote(str(folder / "pilot-arm.json")) + "\n")
        prepared["files"]["runtime.env"] = pipeline.sha256(folder / "runtime.env")
        atomic_json(folder / "review.json", prepared)
    pair = {
        "comparison_id": comparison_id,
        "arms": ["priority", "file"],
        "n_images": expected,
        "human_pilot_complete": False,
        "note": "Preparation only; no reviewer/session enrollment",
    }
    write_new(output / "pilot-pair.json", pair)
    return pair


def _check_pair(root: Path, *, verify_cvat=False, freeze=False, client_for=None):
    root = root.resolve()
    reports = []
    tasks = []
    for order in ("priority", "file"):
        folder = root / order
        report = inspect_batch(folder, expected=config.load("review_acceptance")["pilot_images"])
        descriptor = json.loads((folder / "pilot-arm.json").read_text())
        if descriptor["order"] != order or descriptor["queue_id"] != report["queue_id"]:
            raise ValueError("Arm/snapshot khác cấu hình đã chuẩn bị")
        record = verify(folder)
        settings = Settings(
            queue_file=folder / f"ranked_queue_{record['version']}.csv",
            images=folder / "images",
            database=folder / "review.db",
            mapping=folder / "cvat_map.parquet",
            cvat_url=record["identity"]["cvat_url"],
            snapshot_dir=str(folder / "snapshots"),
        )
        service = QueueService(settings, ReviewStore(settings.database, settings.database_url))
        if service.store.records() or service.store.state_items("pilot:"):
            raise ValueError("Pair đã có review/đăng ký; không thay baseline sau khi bắt đầu")
        mapping, warnings = service.mapping()
        targets = {(settings.cvat_url, v["task_id"]) for v in mapping.values()}
        tasks.append(targets)
        if verify_cvat:
            if not report["mapping_ready"]:
                raise ValueError("Chưa có mapping đủ30ảnh")
            reader = SavedLabels(settings, service, client_for(settings.cvat_url))
            captured = []
            snapshots = {}
            for image_id in sorted(report["photo_sha256"]):
                value = reader.capture(image_id, queue_id=report["queue_id"])
                snapshots[image_id] = value["snapshot_id"]
                captured.append(
                    {
                        "image_id": image_id,
                        "boxes": sorted(
                            [
                                {k: b[k] for k in ("category", "box", "attributes")}
                                for b in value["payload"]["boxes"]
                            ],
                            key=canonical,
                        ),
                    }
                )
            if hashlib.sha256(canonical(captured)).hexdigest() != descriptor["annotation_baseline_sha256"]:
                raise ValueError("Nhãn CVAT khác nhãn ban đầu của batch")
            if any(
                reader.capture(i, queue_id=report["queue_id"])["snapshot_id"] != h
                for i, h in snapshots.items()
            ):
                raise ValueError("Nhãn thay đổi trong lúc freeze")
        reports.append((report, descriptor, settings))
    a, b = (r[0] for r in reports)
    if any(a[k] != b[k] for k in ("queue_id", "labels_sha256", "photo_sha256")):
        raise ValueError("Hai arm không cùng ảnh/queue/nhãn ban đầu")
    if tasks[0] & tasks[1] or reports[0][2].database.resolve() == reports[1][2].database.resolve():
        raise ValueError("Hai arm phải dùng task/DB riêng")
    if reports[0][1]["annotation_baseline_sha256"] != reports[1][1]["annotation_baseline_sha256"]:
        raise ValueError("Baseline nhãn khác nhau")
    ready = all(r["mapping_ready"] for r, _, _ in reports) and verify_cvat
    if freeze:
        if not ready:
            raise ValueError("Freeze cần --verify-cvat và mapping đủ")
        for report, descriptor, settings in reports:
            descriptor.update(
                setup_frozen=True,
                mapping_sha256=report["mapping_sha256"],
                photo_sha256=report["photo_sha256"],
            )
            atomic_json(settings.database.parent / "pilot-arm.json", descriptor)
    return {
        "comparison_id": reports[0][1]["comparison_id"],
        "n_images": a["n_images"],
        "same_queue_labels_photos": True,
        "independent_tasks": bool(tasks[0] and tasks[1]),
        "setup_ready": ready,
        "human_eligible": ready and all(r["data_kind"] == "bdd_inputs" for r, _, _ in reports),
        "human_pilot_complete": False,
        "note": "Chưa đăng ký reviewer; không có số liệu người thật",
    }


def check_pair(root: Path, *, verify_cvat=False, freeze=False):
    from src.api.cvat_session import authenticated_client

    with ExitStack() as stack:
        clients = {}

        def client_for(url):
            if url not in clients:
                clients[url] = stack.enter_context(authenticated_client(url))
            return clients[url]

        return _check_pair(root, verify_cvat=verify_cvat, freeze=freeze, client_for=client_for)
