"""Operator-owned review setup; reviewers supply a name, never paths or policy."""

import json
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field


class StartReview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reviewer: str = Field(min_length=1, max_length=100)
    request_id: UUID


def install_workspace(app, settings, store):
    def workspace():
        return {
            "batch": settings.review_batch or "",
            "order": settings.review_order,
            "guideline_url": settings.guideline_url,
            "local_start_allowed": not settings.accounts_file and not settings.pilot_arm_file,
        }

    app.get("/review/workspace")(workspace)

    @app.post("/review/start")
    def start(value: StartReview):
        if not workspace()["local_start_allowed"]:
            raise HTTPException(409, "Dùng trang đăng nhập hoặc đăng ký pilot của môi trường này.")
        key = "review-start:" + str(value.request_id)
        with store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
            if row:
                existing = json.loads(row[0])
                if existing["reviewer"] != value.reviewer:
                    raise HTTPException(409, "Yêu cầu bắt đầu đã dùng cho người khác.")
                return existing
            # Freeze the operator's selection per session. Retries/restarts keep the same scope.
            result = {
                **workspace(), "reviewer": value.reviewer,
                "session_id": "review-" + value.request_id.hex,
            }
            db.execute("INSERT INTO state(key,value) VALUES(?,?)", (key, json.dumps(result)))
        return result
