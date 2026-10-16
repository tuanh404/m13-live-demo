"""Human-operated enrollment for a preconfigured pilot arm. No automatic enrollment."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from src.api.pilot import PilotPlan, register, session_key
from src.api.saved_labels import canonical


class Enrollment(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reviewer: str = Field(min_length=1, max_length=100)
    request_id: UUID = Field(default_factory=uuid4)
    is_human: Literal[True]
    unseen_batch: Literal[True]
    follow_protocol: Literal[True]


class Feedback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(pattern=r"^[a-zA-Z0-9-]{1,100}$")
    clarity: int = Field(ge=1, le=5)
    confusing: str = Field(default="", max_length=2000)


def install_pilot(app, settings, store, service, saved):
    def descriptor():
        if not settings.pilot_arm_file:
            return None
        try:
            return json.loads(settings.pilot_arm_file.read_text())
        except (OSError, ValueError) as exc:
            raise HTTPException(503, "Chưa đọc được cấu hình pilot arm") from exc

    def access(request):
        token = request.headers.get("X-M13-Pilot-Session", "")
        if not token:
            return None
        identity = store.state("pilot-access:" + hashlib.sha256(token.encode()).hexdigest())
        if not identity:
            return None
        return store.state(session_key(identity["reviewer"], identity["session_id"]))

    @app.middleware("http")
    async def protect_preview(request: Request, call_next):
        protected = request.url.path.startswith(
            (
                "/queue",
                "/image/",
                "/web/review/",
                "/web/cvat/",
                "/web/recheck-history/",
                "/verdict",
                "/stats",
                "/rechecks/",
            )
        )
        if settings.pilot_arm_file and protected:
            manifest = access(request)
            if manifest is None:
                return JSONResponse(
                    {"detail": "Đăng ký pilot trước khi xem ảnh; không xem trước batch."}, status_code=403
                )
            plan = manifest["plan"]
            for key, field in [("reviewer", "reviewer"), ("session_id", "session_id"), ("order", "order")]:
                if request.query_params.get(key) not in {None, plan[field]}:
                    return JSONResponse(
                        {"detail": "Pilot phải dùng đúng phiên/thứ tự đã đăng ký"}, status_code=403
                    )
            request.state.pilot_manifest = manifest
        return await call_next(request)

    @app.get("/pilot", include_in_schema=False)
    def page():
        return FileResponse(Path(__file__).with_name("web") / "pilot.html")

    @app.get("/pilot/review", include_in_schema=False)
    def review_page():
        return FileResponse(Path(__file__).with_name("web") / "index.html")

    @app.get("/pilot/status")
    def status(request: Request):
        arm = descriptor()
        if arm is None:
            return {
                "configured": False,
                "eligible": False,
                "message": "Chưa cấu hình arm pilot30ảnh. Demo vẫn dùng bình thường.",
            }
        eligible = (
            arm["purpose"] == "real"
            and arm["setup_frozen"]
            and settings.data_purpose == "real"
            and arm["n_images"] == settings.pilot_images
        )
        manifest = access(request)
        return {
            "configured": True,
            "eligible": eligible,
            "order": arm["order"],
            "n_images": arm["n_images"],
            "comparison_id": arm["comparison_id"],
            "session": manifest["plan"] if manifest else None,
            "message": "Sẵn sàng cho người thật đăng ký"
            if eligible
            else "Chỉ có fixture hoặc chưa freeze/đủ đầu vào BDD; chưa được chạy human pilot.",
        }

    @app.post("/pilot/register")
    def enroll(value: Enrollment):
        arm = descriptor()
        if not arm or arm["purpose"] != "real" or not arm["setup_frozen"] or settings.data_purpose != "real":
            raise HTTPException(
                409, "Chưa có arm BDD thật đã freeze; không đăng ký fixture thành human pilot"
            )
        claim = {
            "payload_sha256": hashlib.sha256(canonical(value.model_dump(mode="json"))).hexdigest(),
            "comparison_id": arm["comparison_id"],
        }
        with store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            key = "pilot-enrollment:" + str(value.request_id)
            db.execute(
                "INSERT INTO state(key,value) VALUES(?,?) ON CONFLICT(key) DO NOTHING",
                (key, json.dumps(claim)),
            )
            if json.loads(db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()[0]) != claim:
                raise HTTPException(409, "Mã đăng ký đã dùng cho nội dung khác")
        plan = PilotPlan(
            reviewer=value.reviewer,
            session_id="pilot-" + value.request_id.hex,
            comparison_id=arm["comparison_id"],
            order=arm["order"],
        )
        try:
            manifest = register(plan, confirmed=True, settings=settings, saved=saved)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        token = uuid4().hex + uuid4().hex
        store.state("pilot-access:" + hashlib.sha256(token.encode()).hexdigest(), plan.model_dump())
        return {"token": token, "session": manifest["plan"], "url": "/pilot/review"}

    @app.post("/pilot/feedback")
    def feedback(value: Feedback, request: Request):
        manifest = access(request)
        if manifest is None:
            raise HTTPException(403, "Chưa có phiên human pilot")
        plan = manifest["plan"]
        stats = service.stats(reviewer=plan["reviewer"], session_id=plan["session_id"], order=plan["order"])
        if stats["reviewed_images"] != manifest["n_images"]:
            raise HTTPException(409, "Hoàn thành đủ ảnh trước khi gửi phản hồi")
        key = "pilot-feedback:" + value.request_id
        row = {**value.model_dump(), "reviewer": plan["reviewer"], "session_id": plan["session_id"]}
        previous = store.state(key)
        if previous and previous["payload"] != row:
            raise HTTPException(409, "Mã phản hồi đã dùng cho nội dung khác")
        if not previous:
            store.state(
                key,
                {
                    "reviewer": plan["reviewer"],
                    "session_id": plan["session_id"],
                    "payload": row,
                    "created_at": datetime.now(UTC).isoformat(),
                    "payload_sha256": hashlib.sha256(canonical(row)).hexdigest(),
                },
            )
        return {"status": "saved", "duplicate": previous is not None}
