"""Optional same-origin login for a shared deployment; local development stays unchanged."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from src import config

COOKIE = "m13_session"


def password_hash(password, *, salt=None):
    salt = salt or secrets.token_hex(16)
    iterations = config.load("deployment")["password_iterations"]
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def password_matches(password, encoded):
    try:
        algorithm, iterations, salt, digest = encoded.split("$")
        if algorithm != "pbkdf2_sha256" or not 600000 <= int(iterations) <= 2000000:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations)).hex()
        return hmac.compare_digest(actual, digest)
    except (ValueError, TypeError):
        return False


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


def install_auth(app, settings, store, service):
    if not settings.accounts_file:

        @app.get("/auth/session")
        def local_session():
            return {"enabled": False}

        return
    cfg = config.load("deployment")
    origin = settings.public_origin.rstrip("/")
    url = urlsplit(origin)
    if url.scheme not in {"http", "https"} or not url.netloc or url.path or url.query or url.fragment:
        raise ValueError("Cần M13_PUBLIC_ORIGIN là origin đầy đủ, không prefix")
    if (
        url.username
        or url.password
        or (url.scheme != "https" and url.hostname not in {"localhost", "127.0.0.1", "[::1]", "::1"})
        or (url.scheme == "https" and not settings.auth_cookie_secure)
    ):
        raise ValueError("Shared deployment cần HTTPS và cookie Secure; HTTP chỉ cho loopback test")
    accounts = json.loads(settings.accounts_file.read_text())["users"]
    if not accounts or any(
        user.get("role") not in {"demo", "admin"}
        or not user.get("password_hash", "").startswith("pbkdf2_sha256$600000$")
        for user in accounts.values()
    ):
        raise ValueError("Account file cần role và password hash PBKDF2 hợp lệ")
    dummy = password_hash(secrets.token_urlsafe(32))
    assets = Path(__file__).with_name("web")

    def identity(request):
        token = request.cookies.get(COOKIE, "")
        if not token or len(token) > 200:
            return None
        state = store.state("auth-session:" + hashlib.sha256(token.encode()).hexdigest())
        if not state or state["expires"] <= time.time() or state["username"] not in accounts:
            return None
        account_hash = hashlib.sha256(accounts[state["username"]]["password_hash"].encode()).hexdigest()
        return state if state.get("account_hash") == account_hash else None

    def batch_identity(session, key):
        import re

        if not session or not re.fullmatch("[a-f0-9]{32}", key):
            raise HTTPException(404, "Không tìm thấy bộ ảnh trong phiên của bạn.")
        record = store.state("upload-batch:" + key)
        owner = hashlib.sha256(session["reviewer"].encode()).hexdigest()
        if not record or record["owner"] != owner:
            raise HTTPException(404, "Không tìm thấy bộ ảnh trong phiên của bạn.")
        return {**session, "session_id": record["review_session"]}

    @app.middleware("http")
    async def protect(request: Request, call_next):
        # Trust only the configured origin, never the forwarded Host supplied by a visitor.
        if request.headers.get("host", "").lower() != url.netloc.lower():
            return JSONResponse({"detail": "Host không thuộc deployment"}, status_code=400)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if request.headers.get("origin") != origin:
                return JSONResponse({"detail": "Origin không hợp lệ"}, status_code=403)
            upload = settings.uploads_enabled and request.url.path == "/my-batches/upload"
            if upload and not identity(request):
                return JSONResponse({"detail": "Cần đăng nhập"}, status_code=401)
            limit = config.load("upload")["max_zip_bytes"] if upload else cfg["max_body_bytes"]
            try:
                if int(request.headers.get("content-length", "0")) > limit:
                    return JSONResponse({"detail": "Request quá lớn"}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "Content-Length không hợp lệ"}, status_code=400)
            # Check actual bytes as well, including requests without Content-Length.
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit:
                    return JSONResponse({"detail": "Request quá lớn"}, status_code=413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        path = request.url.path
        session = identity(request)
        import re

        batch = re.match(r"^/batches/([a-f0-9]{32})(?:/|$)", path)
        if session and batch:
            try:
                session = batch_identity(session, batch[1])
            except HTTPException as exc:
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        request.state.auth_identity = session
        public = (
            path in {"/login", "/auth/login", "/auth/session", "/health"}
            or path.startswith("/assets/")
            or (settings.guest_demo and path == "/auth/demo")
        )
        if request.method in {"GET", "HEAD"} and (
            path in {"/submission", "/web/submission"} or path.startswith("/submission/assets/")
        ):
            public = True
        if not public and not session:
            if "text/html" in request.headers.get("accept", "") and request.method == "GET":
                return RedirectResponse("/login", status_code=303)
            return JSONResponse({"detail": "Cần đăng nhập"}, status_code=401)
        if session:
            if session["role"] == "demo":
                admin = path.startswith(
                    (
                        "/intake",
                        "/jobs/",
                        "/retrain",
                        "/model",
                        "/rechecks",
                        "/web/cvat",
                        "/web/recheck-history",
                        "/pilot",
                    )
                ) or (path.startswith("/image/") and path.endswith(("/saved", "/recheck")))
                if admin:
                    return JSONResponse(
                        {"detail": "Chức năng dành cho operator; demo chỉ review"}, status_code=403
                    )
            import re

            scoped_path = re.sub(r"^/(jobs|batches)/[a-f0-9]{32}", "", path)
            if scoped_path in {"/queue", "/stats"} and not settings.pilot_arm_file:
                if any(request.query_params.get(k) != session[k] for k in ("reviewer", "session_id")):
                    return JSONResponse(
                        {"detail": "Chỉ đọc lượt review của phiên đăng nhập"}, status_code=403
                    )
        response = await call_next(request)
        if not (public and path.startswith("/submission/assets/") and response.status_code == 200):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; "
            "connect-src 'self'; object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'none'; form-action 'self'"
        )
        return response

    @app.get("/login", include_in_schema=False)
    def login_page():
        return FileResponse(assets / "login.html")

    @app.get("/auth/session")
    def current(request: Request, upload_batch: str | None = None):
        session = identity(request)
        if upload_batch is not None:
            session = batch_identity(session, upload_batch)
        guest_ready = settings.guest_demo and accounts.get("guest", {}).get("role") == "demo"
        return {
            "enabled": True,
            "authenticated": bool(session),
            "guest_demo": guest_ready,
            "uploads_enabled": settings.uploads_enabled,
            "identity": {k: session[k] for k in ("username", "role", "reviewer", "session_id")}
            if session
            else None,
        }

    def rate_limit(request):
        # Fixed-window limit shared across workers; do not trust forwarded IPs.
        peer = request.client.host if request.client else "unknown"
        key = "login-attempts:" + hashlib.sha256(peer.encode()).hexdigest()
        now = time.time()
        with store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
            count = json.loads(row[0]) if row else {"start": now, "count": 0}
            if now - count["start"] >= cfg["login_window_seconds"]:
                count = {"start": now, "count": 0}
            if count["count"] >= cfg["login_attempts"]:
                raise HTTPException(429, "Quá nhiều lần đăng nhập; thử lại sau")
            count["count"] += 1
            db.execute(
                "INSERT INTO state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(count)),
            )
        return now

    def sign_in(username, user, now):
        token = secrets.token_urlsafe(32)
        session = {
            "username": username,
            "role": user["role"],
            "reviewer": "live-" + secrets.token_hex(8),
            "session_id": "live-" + secrets.token_hex(16),
            "account_hash": hashlib.sha256(user["password_hash"].encode()).hexdigest(),
            "expires": now + cfg["session_seconds"],
        }
        store.state("auth-session:" + hashlib.sha256(token.encode()).hexdigest(), session)
        response = JSONResponse({"status": "signed_in"})
        response.set_cookie(
            COOKIE,
            token,
            max_age=cfg["session_seconds"],
            httponly=True,
            secure=settings.auth_cookie_secure,
            samesite="strict",
            path="/",
        )
        return response

    @app.post("/auth/demo")
    def guest(request: Request):
        user = accounts.get("guest")
        if not settings.guest_demo or not user or user["role"] != "demo":
            raise HTTPException(403, "Chưa bật chế độ trải nghiệm demo")
        return sign_in("guest", user, rate_limit(request))

    @app.post("/auth/login")
    def login(value: Login, request: Request):
        now = rate_limit(request)
        user = accounts.get(value.username)
        valid = password_matches(value.password, user["password_hash"] if user else dummy)
        if not valid or not user:
            raise HTTPException(401, "Tên hoặc mật khẩu không đúng")
        return sign_in(value.username, user, now)

    @app.post("/auth/logout")
    def logout(request: Request):
        token = request.cookies.get(COOKIE, "")
        store.state("auth-session:" + hashlib.sha256(token.encode()).hexdigest(), {"expires": 0})
        response = JSONResponse({"status": "signed_out"})
        response.delete_cookie(
            COOKIE, path="/", secure=settings.auth_cookie_secure, httponly=True, samesite="strict"
        )
        return response

    @app.post("/auth/new-review")
    def new_review(request: Request):
        if settings.pilot_arm_file:
            raise HTTPException(409, "Không tạo lượt demo trong pilot")
        session = dict(request.state.auth_identity)
        session["session_id"] = "live-" + secrets.token_hex(16)
        token = request.cookies[COOKIE]
        store.state("auth-session:" + hashlib.sha256(token.encode()).hexdigest(), session)
        return {"status": "new_review"}
