"""Same-origin review presentation. No Chrome, CVAT or arbitrary file access required."""

from __future__ import annotations

import hashlib
import io
import ipaddress
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src import config, pipeline
from src.api.schemas import Evidence
from src.api.service import QueueService, safe_id


def verified_manifest(service: QueueService, queue_id=None):
    frame, current_id, path = service.snapshot()
    if path and path.with_suffix('.manifest.json').is_file():
        try:
            if json.loads(path.with_suffix('.manifest.json').read_text())['queue_sha256'] != current_id:
                raise ValueError('hash')
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise HTTPException(503, 'Snapshot hàng đợi đang phục vụ thiếu hoặc sai hash') from exc
    if queue_id and queue_id != current_id:
        version = next(
            (v for v in (service.store.state("versions") or {}).values() if v["queue_id"] == queue_id), None
        )
        if version is None:
            raise HTTPException(409, "Snapshot không còn khả dụng; tải lại hàng đợi")
        path = Path(version["queue_file"])
        try:
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != queue_id:
                raise ValueError("hash")
            frame = pd.read_csv(io.BytesIO(raw), dtype={"image_id": str, "model_version": str})
        except (OSError, ValueError) as exc:
            raise HTTPException(503, "Snapshot lịch sử thiếu hoặc thay đổi") from exc
        current_id = queue_id
    queue_id = current_id
    if path is None or not path.with_suffix(".manifest.json").is_file():
        return frame, queue_id, None, None
    try:
        manifest = json.loads(path.with_suffix(".manifest.json").read_text(encoding="utf-8"))
        if manifest["queue_sha256"] != queue_id:
            raise ValueError("Queue khác manifest")
        return frame, queue_id, path, manifest
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, "Không xác minh được snapshot hàng đợi") from exc


def artifact(manifest, kind):
    """Only read a server-configured manifest artifact; never accept a client path."""
    try:
        raw = pipeline.located(manifest[f"{kind}_file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest[f"{kind}_sha256"]:
            raise ValueError("hash mismatch")
        return raw
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, f"Snapshot {kind} thiếu hoặc sai hash; không hiển thị dữ liệu cũ") from exc


def install_web(app: FastAPI, service: QueueService):
    assets = Path(__file__).with_name("web")
    app.mount("/assets", StaticFiles(directory=assets), name="review-assets")

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(assets / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/data-license", include_in_schema=False)
    def data_license():
        return FileResponse(config.ROOT / "deployment/render/BDD100K-LICENSE.txt", media_type="text/plain")

    @app.get("/web/context")
    def context():
        frame, queue_id, path, manifest = verified_manifest(service)
        version = str(frame.model_version.iloc[0]) if len(frame) else None
        return {
            "queue_id": queue_id,
            "model_version": version,
            "data_purpose": service.settings.data_purpose,
            "fixture": "fixture" in (version or "").lower(),
            "active_checks": manifest.get("used_signals", []) if manifest else [],
            "method": manifest.get("method") if manifest else None,
            "verified": manifest is not None,
            "snapshot_at": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat() if path else None,
            "labels_sha256": manifest.get("labels_sha256") if manifest else None,
            "has_predictions": bool(manifest and manifest.get("preds_file")),
            "has_spec": bool(manifest and manifest.get("spec")),
        }

    @app.get("/web/review/{image_id}")
    def review(image_id: str, queue_id: str):
        safe_id(image_id)
        frame, current_id, path, manifest = verified_manifest(service, queue_id)
        if queue_id != current_id:
            raise HTTPException(409, "Queue đã đổi; tải lại trước khi review")
        rows = frame[frame.image_id == image_id]
        if rows.empty:
            raise HTTPException(404, "Ảnh không thuộc hàng đợi")
        labels, boxes, warnings = [], {}, []
        if manifest:
            try:
                frames = json.loads(artifact(manifest, "labels"))
                matches = [f for f in frames if Path(f["name"]).stem == Path(image_id).stem]
                if len(matches) != 1:
                    raise ValueError("Nhãn ảnh thiếu hoặc trùng")
                for obj in matches[0].get("labels") or []:
                    if not obj.get("box2d"):
                        continue
                    box = [float(obj["box2d"][key]) for key in ("x1", "y1", "x2", "y2")]
                    if not all(math.isfinite(n) for n in box) or box[0] >= box[2] or box[1] >= box[3]:
                        raise ValueError("Toạ độ nhãn không hợp lệ")
                    labels.append(
                        {
                            "number": len(labels) + 1,
                            "obj_id": str(obj.get("id", len(labels))),
                            "category": config.load("class_map")["rename"].get(
                                obj["category"], obj["category"]
                            ),
                            "box": box,
                        }
                    )
                seen = set()
                for line in artifact(manifest, "evidence").decode("utf-8").splitlines():
                    if not line.strip():
                        continue
                    item = json.loads(line)
                    if item["image_id"] in seen:
                        raise ValueError("Evidence trùng ảnh")
                    seen.add(item["image_id"])
                    if item["image_id"] == image_id:
                        boxes[image_id] = [Evidence.model_validate(b).model_dump() for b in item["boxes"]]
                        for b in boxes[image_id]:
                            coords = b["box"]
                            if (
                                not all(math.isfinite(n) for n in coords)
                                or coords[0] >= coords[2]
                                or coords[1] >= coords[3]
                            ):
                                raise ValueError("Toạ độ evidence không hợp lệ")
            except (ValueError, KeyError, TypeError) as exc:
                raise HTTPException(503, "Snapshot nhãn/evidence không hợp lệ") from exc
        else:
            warnings.append("Chưa có snapshot nhãn/evidence được xác minh; không suy đoán box từ điểm.")
        # Reuse the queue contract and severity policy, but never fetch CVAT or unrelated predictions.
        result = service.enrich(rows.iloc[0].to_dict(), current_id, None, boxes, {})
        return {
            **result,
            "annotations": labels,
            "warnings": warnings,
            "labels_verified": manifest is not None,
            "label_source": "queue_snapshot",
            "cvat_mapped": image_id in service.mapping()[0],
        }

    @app.get("/web/cvat/{image_id}")
    def cvat_link(image_id: str, queue_id: str, request: Request):
        from urllib.parse import urlsplit

        detail = service.detail(image_id, queue_id=queue_id)
        url = urlsplit(service.settings.cvat_url)

        def loopback(host):
            if host == "localhost":
                return True
            try:
                return ipaddress.ip_address(host or "").is_loopback
            except ValueError:
                return False

        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
            or (loopback(url.hostname) and not loopback(request.url.hostname))
        ):
            return {
                "available": False,
                "message": "CVAT chưa có địa chỉ truy cập phù hợp cho người dùng web.",
            }
        if detail["cvat"] is None:
            return {"available": False, "message": "Ảnh chưa có mapping CVAT; vẫn có thể review trên web."}
        # Verify job/task/frame against actual saved metadata before offering the link.
        try:
            capture = app.state.rechecks.capture(image_id, queue_id=queue_id)
        except HTTPException:
            return {
                "available": False,
                "message": "CVAT chưa sẵn sàng hoặc thiếu quyền; review web vẫn hoạt động.",
            }
        return {
            "available": True,
            "url": detail["cvat_url"],
            "target": detail["cvat"],
            "annotation_version": capture["annotation_version"],
            "message": "Mở CVAT, sửa và Save; quay về ảnh này để đọc nhãn đã lưu.",
        }

    @app.get("/web/recheck-history/{image_id}")
    def history(image_id: str):
        safe_id(image_id)
        entries = []
        for row in service.store.state_items("recheck:").values():
            if row.get("input", {}).get("image_id") != image_id:
                continue
            result = row.get("result")
            entries.append(
                {
                    "status": row["status"],
                    "result": result,
                    "error": row.get("error"),
                    "request_id": row["input"]["request_id"],
                }
            )
        return {"image_id": image_id, "entries": entries}
