"""Fixed public presentation assets, immutable in the existing demo database.

No source archives, credentials, review records or client-supplied file paths.
"""

import hashlib
import json
import re
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response

from src.api.cloud import asset_schema, database
from src.api.saved_labels import canonical

ASSETS = {"pitch.pdf": "application/pdf", "thumbnail.png": "image/png", "M13-demo.mp4": "video/mp4"}


def publish_assets(folder):
    blobs = {name: (folder / name).read_bytes() for name in ASSETS}
    if sum(map(len, blobs.values())) > 20 * 1024 * 1024:
        raise ValueError("Presentation assets exceed20MiB")
    for name, raw in blobs.items():
        signature = {"pitch.pdf": b"%PDF-", "thumbnail.png": b"\x89PNG", "M13-demo.mp4": b"ftyp"}[name]
        if signature not in raw[:16]:
            raise ValueError("Presentation asset format differs from its name")
    descriptor = {"kind": "public_presentation_only", "files": {
        n: hashlib.sha256(raw).hexdigest() for n, raw in blobs.items()
    }}
    identity = hashlib.sha256(canonical(descriptor)).hexdigest()
    with database() as db:
        asset_schema(db)
        for name, raw in {"presentation.json": canonical(descriptor), **blobs}.items():
            digest = hashlib.sha256(raw).hexdigest()
            previous = db.execute(
                "SELECT sha256 FROM demo_assets WHERE bundle_id=%s AND name=%s", (identity, name)
            ).fetchone()
            if previous and previous[0] != digest:
                raise ValueError("Immutable presentation changed")
            if not previous:
                db.execute("INSERT INTO demo_assets VALUES (%s,%s,%s,%s)", (identity, name, digest, raw))
        db.execute("INSERT INTO state VALUES ('public-submission',%s) "
                   "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps({"id": identity}),))
    return {"id": identity, "assets": {
        n: {"path": f"/submission/assets/{identity}/{n}", "sha256": descriptor["files"][n], "bytes": len(raw)}
        for n, raw in blobs.items()
    }}


def install_submission(app, settings):
    def available():
        if not settings.database_url:
            raise HTTPException(404, "Hồ sơ local nằm trong data/mvp-submission; chưa publish ở server này")

    @app.get("/submission", include_in_schema=False)
    def page():
        return FileResponse(Path(__file__).with_name("web") / "submission.html")

    @app.get("/web/submission")
    def metadata():
        available()
        with database() as db:
            row = db.execute("SELECT value FROM state WHERE key='public-submission'").fetchone()
        if not row:
            raise HTTPException(404, "Chưa công bố bộ video/slides/thumbnail")
        identity = json.loads(row[0])["id"]
        if not re.fullmatch(r"[a-f0-9]{64}", identity):
            raise HTTPException(503, "Hồ sơ thiếu phiên bản hợp lệ")
        return {"id": identity, "assets": {n: f"/submission/assets/{identity}/{n}" for n in ASSETS},
                "source": "Source mới: bundle local/repo deploy private; chưa công khai bản mới."}

    @app.get("/submission/assets/{identity}/{name}")
    def asset(identity: str, name: str):
        available()
        if name not in ASSETS or not re.fullmatch(r"[a-f0-9]{64}", identity):
            raise HTTPException(404, "Không có artifact công khai này")
        with database() as db:
            row = db.execute("SELECT sha256,content FROM demo_assets WHERE bundle_id=%s AND name=%s",
                             (identity, name)).fetchone()
            meta = db.execute("SELECT content FROM demo_assets WHERE bundle_id=%s "
                              "AND name='presentation.json'",
                              (identity,)).fetchone()
        if not row or not meta:
            raise HTTPException(404, "Artifact chưa được công bố")
        descriptor = bytes(meta[0])
        digest, raw = row[0], bytes(row[1])
        if (hashlib.sha256(descriptor).hexdigest() != identity
                or json.loads(descriptor)["files"].get(name) != digest
                or hashlib.sha256(raw).hexdigest() != digest):
            raise HTTPException(503, "Artifact sai hash")
        return Response(raw, media_type=ASSETS[name], headers={
            "Cache-Control": "public, max-age=31536000, immutable", "ETag": '"' + digest + '"',
            "X-Content-Type-Options": "nosniff", "Content-Disposition": f'inline; filename="{name}"',
        })
