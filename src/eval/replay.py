"""Replay frozen artifacts; never run a detector, training or parameter selection here."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

import pandas as pd

from src import config, pipeline
from src.eval.evaluate import comparison


def check_answer(original, mutated, answer):
    rename = config.load("class_map")["rename"]

    def table(frames):
        images, objects = [], {}
        for frame in frames:
            image_id = Path(frame["name"]).stem
            images.append(image_id)
            for index, label in enumerate(frame.get("labels") or []):
                if not label.get("box2d"):
                    continue
                key = (image_id, str(label.get("id", index)))
                if key in objects:
                    raise ValueError("obj_id trùng trong nhãn")
                objects[key] = (
                    rename.get(label["category"], label["category"]),
                    [label["box2d"][k] for k in ("x1", "y1", "x2", "y2")],
                )
        if len(set(images)) != len(images):
            raise ValueError("image_id trùng trong nhãn")
        return images, objects

    original_ids, before = table(original)
    mutated_ids, after = table(mutated)
    if original_ids != answer["image_order"] or set(original_ids) != set(mutated_ids):
        raise ValueError("Đáp án và hai bộ nhãn không cùng tập/thứ tự ảnh")
    changed = {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
    declared = {(e["image_id"], str(e["obj_id"])) for e in answer["errors"]}
    if changed != declared or len(declared) != len(answer["errors"]):
        raise ValueError("Lỗi tiêm khai báo không khớp toàn bộ thay đổi nhãn")
    for error in answer["errors"]:
        key = (error["image_id"], str(error["obj_id"]))
        kind = error["type"]
        old, new = before.get(key), after.get(key)
        if kind not in {"missing", "wrong_class", "shift", "resize", "spurious"}:
            raise ValueError("Loại lỗi không được hỗ trợ")
        if kind != "spurious" and old != (error["category"], error["box_before"]):
            raise ValueError("box/category trước tiêm không khớp đáp án")
        expected = (
            None
            if kind == "missing"
            else (error.get("category_after", error["category"]), error["box_after"])
        )
        if new != expected or (kind == "spurious" and old is not None):
            raise ValueError("box/category sau tiêm không khớp đáp án")
    return {
        "changed_objects": len(changed),
        "answer_errors": len(answer["errors"]),
        "split_counts": dict(Counter(answer["splits"].values())),
    }


def replay(
    queue_file: Path,
    *,
    bundle: Path,
    answer_file: Path,
    source_labels: Path,
    original_labels: Path,
    output: Path,
    split="test",
    top_frac=0.2,
):
    bundle = bundle.resolve()
    if output.exists():
        raise ValueError("Kết quả đã có; chọn --out mới, không ghi đè")
    manifest_file = queue_file.with_suffix(".manifest.json")
    manifest = json.loads(manifest_file.read_text())

    def artifact(kind):
        raw = Path(manifest[kind + "_file"])
        choices = {
            p.resolve()
            for p in ([raw] if raw.is_absolute() else [bundle / raw, config.ROOT / raw])
            if p.is_file() and p.resolve().is_relative_to(bundle)
        }
        if len(choices) != 1:
            raise ValueError(f"Artifact thiếu/mơ hồ/ngoài bundle: {kind}")
        path = choices.pop()
        if pipeline.sha256(path) != manifest[kind + "_sha256"]:
            raise ValueError(f"Artifact khác hash: {kind}")
        return path

    paths = {kind: artifact(kind) for kind in ("queue", "labels", "features", "evidence")}
    if paths["queue"] != queue_file.resolve():
        raise ValueError("Manifest không thuộc queue đã chọn")
    if manifest.get("preds_file"):
        paths["preds"] = artifact("preds")
    if manifest.get("selection") or manifest.get("provenance", {}).get("kind") == "review_subset":
        raise ValueError("Không đánh giá recall trên subset demo/pilot")
    if pipeline.sha256(source_labels) != manifest.get("provenance", {}).get("labels_sha256"):
        raise ValueError("Queue không được tính từ đúng source labels đã cung cấp")
    answer = json.loads(answer_file.read_text())
    meta = answer["meta"]
    if (
        meta.get("purpose") != "synthetic_errors_not_real_qc"
        or hashlib.sha256(json.dumps(meta["config"], sort_keys=True).encode()).hexdigest()
        != meta["config_hash"]
    ):
        raise ValueError("Nguồn/config đáp án chưa xác minh")
    original = json.loads(original_labels.read_text())
    mutated = json.loads(source_labels.read_text())
    validation = check_answer(original, mutated, answer)
    del original
    if json.loads(paths["labels"].read_text()) != mutated:
        raise ValueError("Snapshot nhãn của queue khác đầu vào đã tiêm")
    del mutated
    queue = pd.read_csv(queue_file, dtype={"image_id": str, "model_version": str}).fillna({"top_reasons": ""})
    if len(queue) != manifest["n_images"] or set(queue.model_version) != {manifest["model_version"]}:
        raise ValueError("N/version khác manifest")
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    digest = hashlib.sha256()
    for folder in (config.ROOT / "src/eval", config.CONFIG_DIR):
        for path in sorted(folder.rglob("*")):
            if path.is_file() and path.suffix in {".py", ".yaml"}:
                digest.update(str(path.relative_to(config.ROOT)).encode())
                digest.update(path.read_bytes())
    provenance = {
        "queue_sha256": pipeline.sha256(queue_file),
        "manifest_sha256": pipeline.sha256(manifest_file),
        "answer_sha256": pipeline.sha256(answer_file),
        "source_labels_sha256": pipeline.sha256(source_labels),
        "original_labels_sha256": pipeline.sha256(original_labels),
        "split_sha256": hashlib.sha256(json.dumps(answer["splits"], sort_keys=True).encode()).hexdigest(),
        "evaluator_commit": commit,
        "evaluator_source_sha256": digest.hexdigest(),
        "producer_commit": None,
        "injection_config_hash": meta["config_hash"],
        "artifact_sha256": {k: pipeline.sha256(v) for k, v in paths.items()},
        "method": manifest["method"],
        "used_signals": manifest["used_signals"],
        "detector": manifest.get("options", {}).get("detector"),
        "spec_sha256": hashlib.sha256(json.dumps(manifest.get("spec"), sort_keys=True).encode()).hexdigest(),
        "validation": validation,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        stage = Path(temp) / "evaluation"
        result = comparison(queue, answer, stage, split=split, top_frac=top_frac)
        result.update(
            provenance=provenance,
            measured_time_saved=None,
            limitations=[
                "Injected errors, not human QC findings",
                "No measured review time; time_saved is an image-count proxy",
                "Frozen queue replay; producer commit and original effective defaults unknown",
                "No detector/training/threshold search performed",
            ],
        )
        result["artifacts"] = {
            name: pipeline.sha256(stage / name) for name in ("comparison.csv", "gain_curve.png")
        }
        pipeline.write_json(stage / "evaluation.json", result)
        stage.rename(output)
    return result
