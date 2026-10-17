"""Durable job requests and atomic publication; reuses the existing review app/pipeline."""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pandas as pd
import yaml
from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from src import config, pipeline
from src.api.cvat_session import authenticated_client
from src.api.job_intake import IntakeError, JobReader, origin, workspace_key
from src.api.job_predictions import cache_identity, select_predictions
from src.api.saved_labels import atomic_json, canonical
from src.api.store import ReviewStore


class JobIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cvat_origin: str = Field(max_length=200)
    task_id: int = Field(gt=0)
    job_id: int = Field(gt=0)


class CheckJob(JobIdentity):
    request_id: str = Field(pattern=r"^[A-Za-z0-9-]{1,100}$")


class JobRegistry:
    def __init__(self, settings, client=None):
        self.settings, self.client = settings, client
        self.cfg = yaml.safe_load(settings.intake_config.read_text())
        if self.cfg["method"] != "rule" or not self.cfg["signals"]:
            raise ValueError("Intake profile cần chọn rule rõ ràng; không tự chuyển scorer")
        if settings.database_url:
            raise ValueError("Job intake cần persistent artifact storage; chưa bật trên ephemeral host")
        self.root = config.ROOT / self.cfg["root"]
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = ReviewStore(self.root / "registry.db")
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cvat-intake")
        self.running, self.guard, self.apps = set(), threading.Lock(), {}
        self.profile = {
            "name": self.cfg["profile"],
            "method": self.cfg["method"],
            "signals": self.cfg["signals"],
            "options": copy.deepcopy(config.load("pipeline")),
            "weights": copy.deepcopy(config.load("weights")["signals"]),
        }
        self.refresh_profile()

    def refresh_profile(self):
        self.profile["detector_cache"] = cache_identity(self.cfg, self.profile["options"])

    def identity(self, value):
        if origin(value.cvat_origin) != origin(self.settings.cvat_url):
            raise HTTPException(403, "Server CVAT chưa được operator cho phép")
        if value.task_id not in self.cfg["allowed_task_ids"]:
            raise HTTPException(403, "Task CVAT chưa được operator cấp quyền")
        return workspace_key(self.settings.cvat_url, value.task_id, value.job_id)

    def reader(self):
        from contextlib import nullcontext

        return nullcontext(self.client) if self.client else authenticated_client(self.settings.cvat_url)

    def cached_result(self, value, source, description):
        """Reuse a verified publication, without resetting verdicts on an unchanged job."""
        active = self.store.state("job:" + value["workspace"])
        if not active or active["source"] != source or active["profile"] != value["profile"]:
            return None
        try:
            path = Path(active["queue_file"])
            manifest = json.loads(path.with_suffix(".manifest.json").read_text())
            for kind in ("queue", "labels", "features", "evidence"):
                if pipeline.sha256(pipeline.located(manifest[kind + "_file"])) != manifest[kind + "_sha256"]:
                    return None
            if manifest.get("preds_file") and (
                pipeline.sha256(pipeline.located(manifest["preds_file"])) != manifest["preds_sha256"]
            ):
                return None
            for name, digest in manifest["provenance"]["image_sha256"].items():
                candidates = [Path(active["output"]) / "images" / (name + suffix)
                              for suffix in (".jpg", ".png")]
                files = [p for p in candidates if p.is_file()]
                if len(files) != 1 or pipeline.sha256(files[0]) != digest:
                    return None
            columns = ["image_id", "task_id", "job_id", "frame"]
            mapping = pd.read_parquet(Path(active["output"]) / "cvat_map.parquet")
            expected = [{k: row[k] for k in columns} for row in description["mapping"]]
            if mapping[columns].to_dict("records") != expected:
                return None
            # A later per-image recheck is a different publication. Checking the
            # entire job must not switch it back to the original intake queue.
            db = self.root / value["workspace"] / "review.db"
            model = ReviewStore(db).state("model") if db.exists() else None
            if model and Path(model["queue_file"]) != path:
                return None
            return {
                "review_url": f"/jobs/{value['workspace']}/",
                "api_prefix": f"/jobs/{value['workspace']}",
                "images": len(description["frames"]),
                "queue_id": manifest["queue_sha256"],
                "cache_hit": True,
            }
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def status(self, value):
        self.refresh_profile()
        key = self.identity(value)
        with self.reader() as client:
            description = JobReader(self.settings.cvat_url, client, self.cfg).describe(
                value.task_id, value.job_id
            )
        source = hashlib.sha256(canonical(description)).hexdigest()
        active = self.store.state("job:" + key)
        current_request = self.store.state("latest:" + key)
        operation = self.store.state("request:" + current_request["request_id"]) if current_request else None
        if operation and operation["status"] in {"queued", "reading", "checking"}:
            self.schedule(operation["input"]["request_id"])
        return {
            "workspace": key,
            "ready": bool(active),
            "needs_check": not active or active["source"] != source or active["profile"] != self.profile,
            "review_url": f"/jobs/{key}/" if active else None,
            "api_prefix": f"/jobs/{key}" if active else None,
            "scope": "Kiểm một phần: hình học/ngữ cảnh; detector chỉ dùng khi cache khớp hash ảnh "
            "và model. Chưa có guideline đã duyệt cho job này.",
            "operation": self.public_operation(operation),
        }

    @staticmethod
    def public_operation(operation):
        if not operation:
            return None
        return {k: operation.get(k) for k in ("request_id", "status", "progress", "message", "result")}

    def start(self, value):
        self.refresh_profile()
        key = self.identity(value)
        payload = {**value.model_dump(), "profile": self.profile, "workspace": key}
        request_key = "request:" + value.request_id
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT value FROM state WHERE key=?", (request_key,)).fetchone()
            if previous:
                operation = json.loads(previous[0])
                if operation["input"] != payload:
                    raise HTTPException(409, "Mã yêu cầu đã dùng cho job hoặc cấu hình khác")
                if operation["status"] == "failed":
                    operation.update(status="queued", message="Đang chờ thử lại", progress=[0, 0])
                    db.execute("UPDATE state SET value=? WHERE key=?", (json.dumps(operation), request_key))
            else:
                operation = {
                    "input": payload,
                    "request_id": value.request_id,
                    "status": "queued",
                    "progress": [0, 0],
                    "message": "Đang chờ kiểm tra",
                }
                db.execute("INSERT INTO state VALUES(?,?)", (request_key, json.dumps(operation)))
                db.execute(
                    "INSERT INTO state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    ("latest:" + key, json.dumps({"request_id": value.request_id})),
                )
        if operation["status"] not in {"completed", "partial"}:
            self.schedule(value.request_id)
        return self.public_operation(operation)

    def schedule(self, request_id):
        with self.guard:
            if request_id in self.running:
                return
            self.running.add(request_id)
        self.pool.submit(self.run, request_id)

    def run(self, request_id):
        # One job at a time across threads AND processes; an interrupted lock releases
        # automatically. The durable request is safe to resume without touching CVAT.
        with (self.root / "worker.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                operation = self.store.state("request:" + request_id)
                if operation["status"] in {"completed", "partial"}:
                    return
                value = operation["input"]

                def update(status, message, progress=None):
                    operation.update(status=status, message=message)
                    if progress is not None:
                        operation["progress"] = progress
                    self.store.state("request:" + request_id, operation)

                update("reading", "Đang đọc ảnh và nhãn đã Save")
                with self.reader() as client:
                    reader = JobReader(self.settings.cvat_url, client, self.cfg)
                    description = reader.describe(value["task_id"], value["job_id"])
                    source = hashlib.sha256(canonical(description)).hexdigest()
                    cached = self.cached_result(value, source, description)
                    if cached:
                        reader.check_unchanged(description)
                        operation.update(
                            status="partial", result=cached,
                            message="Nhãn đã Save và cấu hình không đổi; dùng lại kết quả đã kiểm.",
                        )
                        self.store.state("request:" + request_id, operation)
                        return
                    output = self.root / value["workspace"] / "snapshots" / uuid4().hex
                    hashes = reader.read_images(
                        description,
                        output,
                        lambda n, total: update("reading", "Đang đọc ảnh gốc", [n, total]),
                    )
                    update("checking", "Đang tính các phép kiểm hình học/ngữ cảnh")
                    frozen = value["profile"]
                    preds = select_predictions(
                        self.cfg, frozen["options"], hashes, output, frozen.get("detector_cache")
                    )
                    checks = "hình học/ngữ cảnh" + (" và bất đồng detector" if preds else "")
                    update("checking", "Đang kiểm " + checks)
                    version = "job-" + uuid4().hex
                    result = pipeline.publish(
                        description["frames"],
                        output,
                        version,
                        names=frozen["signals"],
                        weights=frozen["weights"],
                        options=frozen["options"],
                        preds_file=preds,
                        provenance={
                            "kind": "saved_cvat_job",
                            "server": origin(self.settings.cvat_url),
                            "task_id": value["task_id"],
                            "job_id": value["job_id"],
                            "annotation_version": description["annotations"]["version"],
                            "source_sha256": source,
                            "image_sha256": hashes,
                            "profile": frozen["name"],
                            "detector_cache": frozen.get("detector_cache") if preds else None,
                            "missing": ([] if preds else ["detector_predictions"]) + ["approved_guideline"],
                        },
                    )
                    reader.check_unchanged(description)
                pd.DataFrame(description["mapping"])[["image_id", "task_id", "job_id", "frame"]].to_parquet(
                    output / "cvat_map.parquet", index=False
                )
                atomic_json(output / "source.json", description)
                active = {
                    "source": source,
                    "profile": frozen,
                    "queue_file": result["queue_file"],
                    "output": str(output),
                    "request_id": request_id,
                    "task_id": value["task_id"],
                    "job_id": value["job_id"],
                }
                operation.update(
                    status="partial",
                    message="Đã kiểm " + checks + "; chưa kiểm guideline đã duyệt. "
                    + ("Detector dùng predictions cache, không inference mới." if preds
                       else "Chưa có predictions khớp ảnh; chưa kiểm bất đồng detector."),
                    result={
                        "review_url": f"/jobs/{value['workspace']}/",
                        "api_prefix": f"/jobs/{value['workspace']}",
                        "images": len(description["frames"]),
                        "queue_id": result["queue_sha256"],
                    },
                )
                self.store.states({"job:" + value["workspace"]: active, "request:" + request_id: operation})
            except Exception as exc:
                if "operation" in locals() and operation:
                    message = (
                        str(exc)
                        if isinstance(exc, (IntakeError, HTTPException))
                        else "Kiểm tra thất bại; queue cũ được giữ. Nhờ operator kiểm tra dữ liệu."
                    )
                    operation.update(status="failed", message=message)
                    self.store.state("request:" + request_id, operation)
            finally:
                with self.guard:
                    self.running.discard(request_id)

    def application(self, key):
        active = self.store.state("job:" + key)
        if not active:
            raise HTTPException(404, "Job chưa có snapshot QC được xuất bản")
        if active["task_id"] not in self.cfg["allowed_task_ids"]:
            raise HTTPException(403, "Task đã được operator gỡ quyền tiếp nhận")
        if key not in self.apps:
            from src.api.main import create_app

            output = Path(active["output"])
            settings = replace(
                self.settings,
                intake_config=None,
                accounts_file=None,
                public_origin="",
                queue_file=Path(active["queue_file"]),
                evidence_file=None,
                reports=self.root / key,
                images=output / "images",
                predictions=output / "absent-predictions.parquet",
                mapping=output / "cvat_map.parquet",
                database=self.root / key / "review.db",
                queue_batches={},
                review_batch=None,
                evaluation_file=None,
                pilot_arm_file=None,
                data_purpose="development",
                snapshot_dir=str(self.root / key / "saved"),
                recheck_dir=str(self.root / key / "rechecks"),
                recheck_backend="src.pipeline:recheck",
            )
            self.apps[key] = create_app(settings, cvat_client=self.client)
        app = self.apps[key]
        # A new intake is a new immutable queue version. Retain the previously
        # serving queue (including any rechecks) for history and lost-ACK retries.
        store = app.state.store
        if store.state("intake-publication") != {"request_id": active["request_id"]}:
            service = app.state.service
            with service.activation_lock:
                versions = store.state("versions") or {}
                old_frame, old_id, old_path = service.snapshot()
                if old_path and len(old_frame):
                    versions[str(old_frame.model_version.iloc[0])] = {
                        "queue_id": old_id,
                        "queue_file": str(old_path),
                        "model_version": str(old_frame.model_version.iloc[0]),
                    }
                queue = pd.read_csv(active["queue_file"])
                version = str(queue.model_version.iloc[0])
                state = {
                    "queue_id": pipeline.sha256(active["queue_file"]),
                    "queue_file": active["queue_file"],
                    "model_version": version,
                }
                versions[version] = state
                store.states(
                    {
                        "model": state,
                        "versions": versions,
                        "intake-publication": {"request_id": active["request_id"]},
                    }
                )
                # Same job identity means immutable images/mapping remain compatible.
                app.state.settings.images = Path(active["output"]) / "images"
                app.state.settings.mapping = Path(active["output"]) / "cvat_map.parquet"
        return app


def install_intake(app, settings, client=None):
    if not settings.intake_config:
        return
    registry = JobRegistry(settings, client)
    app.state.job_registry = registry

    @app.get("/intake/status")
    def status(cvat_origin: str, task_id: int, job_id: int):
        try:
            return registry.status(JobIdentity(cvat_origin=cvat_origin, task_id=task_id, job_id=job_id))
        except IntakeError as exc:
            raise HTTPException(409, str(exc)) from None
        except (ValueError, KeyError, TypeError):
            raise HTTPException(503, "Chưa đọc được job; kiểm dữ liệu/kết nối/quyền CVAT") from None

    @app.post("/intake/check", status_code=202)
    def check(value: CheckJob):
        try:
            return registry.start(value)
        except IntakeError as exc:
            raise HTTPException(503, str(exc)) from None

    @app.get("/intake/requests/{request_id}")
    def request_status(request_id: str):
        if not __import__("re").fullmatch(r"[A-Za-z0-9-]{1,100}", request_id):
            raise HTTPException(422, "Mã yêu cầu không hợp lệ")
        operation = registry.store.state("request:" + request_id)
        if not operation:
            raise HTTPException(404, "Chưa có yêu cầu")
        if operation["status"] in {"queued", "reading", "checking"}:
            registry.schedule(request_id)
        return registry.public_operation(operation)

    @app.get("/intake", include_in_schema=False)
    def intake_page():
        from fastapi.responses import FileResponse

        return FileResponse(Path(__file__).with_name("web") / "intake.html")

    # A single API/port hosts every job. Each existing review app retains its own
    # store/snapshots/recheck state; no global mutable "current job" switch.
    @app.api_route("/jobs/{key}/{path:path}", methods=["GET", "POST"])
    async def dispatch(key: str, path: str, request: Request):
        import re

        if not re.fullmatch(r"[a-f0-9]{32}", key):
            raise HTTPException(404, "Job không tồn tại")
        child = registry.application(key)
        # Dispatch directly through ASGI, preserving the outer authentication.
        from starlette.responses import Response

        class Forward(Response):
            async def __call__(self, scope, receive, send):
                forwarded = dict(scope, path="/" + path, raw_path=("/" + path).encode())
                await child(forwarded, receive, send)

        return Forward()
