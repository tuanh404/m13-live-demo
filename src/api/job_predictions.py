"""Operator-owned detector cache; never infer identity from an image basename alone."""

import hashlib
import json
import re

import pandas as pd

from src import config, contracts, pipeline
from src.api.job_intake import IntakeError
from src.api.saved_labels import canonical


def cache_description(cfg, options):
    location = cfg.get("predictions_manifest")
    if not location:
        return None
    try:
        path = (config.ROOT / location).resolve()
        if path.stat().st_size > 1024 * 1024:
            raise ValueError("manifest too large")
        value = json.loads(path.read_text())
        detector = options["detector"]
        if (
            value["schema"] != 1
            or value["model"] != detector["model"]
            or value["revision"] != detector["revision"]
            or not re.fullmatch(r"[a-f0-9]{40}", value["revision"])
            or value["confidence_floor"] != detector["conf"]
            or value["class_map_sha256"] != hashlib.sha256(
                canonical(config.load("class_map")["coco_to_bdd"])
            ).hexdigest()
            or not value["source"]
        ):
            raise ValueError("model provenance differs")
        preds = (path.parent / value["predictions_file"]).resolve()
        if (
            not preds.is_relative_to(path.parent)
            or preds.suffix != ".parquet"
            or preds.stat().st_size > 20 * 1024 * 1024
            or pipeline.sha256(preds) != value["predictions_sha256"]
        ):
            raise ValueError("predictions path/hash differs")
        if not value["images"] or any(
            not re.fullmatch(r"[a-f0-9]{64}", digest) for digest in value["images"].values()
        ):
            raise ValueError("missing image hashes")
        return path, preds, value
    except (OSError, ValueError, KeyError, TypeError):
        raise IntakeError(
            "Cache detector thiếu/sai hash, model hoặc cấu hình; nhờ operator kiểm tra"
        ) from None


def cache_identity(cfg, options):
    result = cache_description(cfg, options)
    if not result:
        return None
    path, _, value = result
    return {
        "manifest_sha256": pipeline.sha256(path),
        **{k: value[k] for k in ("model", "revision", "confidence_floor", "predictions_sha256")},
    }


def select_predictions(cfg, options, image_hashes, output, expected):
    if expected is None:
        return None
    if cache_identity(cfg, options) != expected:
        raise IntakeError("Cache detector đã đổi trong lúc kiểm; bắt đầu yêu cầu mới")
    _, path, value = cache_description(cfg, options)
    ids = set(image_hashes)
    if any(value["images"].get(i) != digest for i, digest in image_hashes.items()):
        # Geometry remains available, but predictions from different bytes must
        # never be presented as detector evidence for this job.
        return None
    frame = pd.read_parquet(path)
    if errors := contracts.check_preds(frame):
        raise IntakeError("Predictions không đúng contract: " + "; ".join(errors))
    empty = set(value.get("empty_image_ids", []))
    detected = set(frame.image_id)
    if detected - set(value["images"]) or empty - set(value["images"]) or empty & detected:
        raise IntakeError("Cache detector có ảnh ngoài manifest hoặc trạng thái rỗng mâu thuẫn")
    if not ids <= detected | empty:
        return None
    target = output / "predictions.parquet"
    frame[frame.image_id.isin(ids)].to_parquet(target, index=False)
    return target
