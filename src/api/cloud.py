"""Small immutable demo bundle in Postgres, separate from mutable review history.

Free Render disks are ephemeral. Frozen assets are hydrated and hash checked on
every start, while verdicts and sessions stay in Postgres. No data/credentials
need to enter Git, and a sleeping service does not need a laptop or image mirror.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import PurePosixPath

from src import config, pipeline
from src.api.saved_labels import atomic_json, canonical


def asset_name(name):
    p = PurePosixPath(name)
    if (
        p.is_absolute()
        or ".." in p.parts
        or "\\" in name
        or not p.parts
        or any(part.startswith(".") for part in p.parts)
        or p.suffix not in {".json", ".csv", ".jsonl", ".parquet", ".jpg", ".png", ".txt"}
        or any(word in name.lower() for word in ("account", "secret", "access", "credential", "pilot"))
    ):
        raise ValueError("Tên artifact cloud không hợp lệ")
    return name


def prepare_bundle(source, output, *, acquisition, evaluation=None):
    from src.api.review_setup import verify

    record = verify(source)
    if (
        record["purpose"] != "real"
        or record["images"] != 10
        or record["identity"].get("original_labels_sha256")
        != config.load("review_acceptance")["labels_sha256"]
        or "fixture" in record["version"].lower()
    ):
        raise ValueError("Bản public cần đúng bộ10ảnh thật đã xác minh, không dùng pilot/fixture")
    if record["identity"].get("role", "review") != "review":
        raise ValueError("Không dùng batch pilot làm demo")
    version = record["version"]
    manifest_file = source / f"ranked_queue_{version}.manifest.json"
    manifest = json.loads(manifest_file.read_text())
    names = [
        f"ranked_queue_{version}.csv",
        f"evidence_{version}.jsonl",
        f"labels_{version}.json",
        f"features_{version}.parquet",
        manifest_file.name,
        "predictions.parquet",
    ]
    photos = json.loads(acquisition.read_text())
    queue_ids = set(__import__("pandas").read_csv(source / names[0]).image_id)
    if not photos["complete"] or not queue_ids <= set(photos["images"]):
        raise ValueError("Thiếu provenance ảnh")
    files = {}
    for name in names:
        raw = (source / name).read_bytes()
        files[name] = raw
    for image_id in sorted(queue_ids):
        name = f"images/{image_id}.jpg"
        raw = (source / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != photos["images"][image_id]["sha256"]:
            raise ValueError("Hash ảnh khác nguồn đã kiểm")
        files[name] = raw
    files["source-images.json"] = canonical(
        {
            **{k: v for k, v in photos.items() if k != "images"},
            "images": {i: photos["images"][i] for i in sorted(queue_ids)},
        }
    )
    files["BDD100K-LICENSE.txt"] = (config.ROOT / "deployment/render/BDD100K-LICENSE.txt").read_bytes()
    if evaluation:
        result = json.loads(evaluation.read_text())
        for name in ("comparison.csv", "gain_curve.png"):
            raw = (evaluation.parent / name).read_bytes()
            if hashlib.sha256(raw).hexdigest() != result["artifacts"][name]:
                raise ValueError("Baseline artifact sai hash")
            files["baseline/" + name] = raw
        files["baseline/evaluation.json"] = evaluation.read_bytes()
    hashes = {asset_name(name): hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    descriptor = {
        "schema": 1,
        "version": version,
        "images": 10,
        "files": hashes,
        "queue_sha256": manifest["queue_sha256"],
        "purpose": "public_demo_not_human_pilot",
        "data_purpose": "real",
    }
    bundle_id = hashlib.sha256(canonical(descriptor)).hexdigest()
    output.mkdir(parents=True, exist_ok=False)
    for name, raw in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    atomic_json(output / "bundle.json", descriptor)
    return {"bundle_id": bundle_id, "files": len(files), "images": 10, "folder": str(output)}


def database():
    import psycopg

    from src.api.postgres import CONNECTION_OPTIONS

    url = os.environ.get("M13_DATABASE_URL")
    if not url:
        raise ValueError("Thiếu M13_DATABASE_URL trong môi trường backend")
    try:
        return psycopg.connect(url, **CONNECTION_OPTIONS)
    except psycopg.Error:
        raise RuntimeError("Không kết nối được database cloud") from None


def asset_schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS demo_assets (
        bundle_id TEXT NOT NULL,name TEXT NOT NULL,sha256 TEXT NOT NULL,
        content BYTEA NOT NULL,PRIMARY KEY(bundle_id,name))""")
    db.execute("""CREATE OR REPLACE FUNCTION m13_assets_append_only() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'demo assets are immutable'; END $$""")
    db.execute("""DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='demo_assets_immutable'
            AND tgrelid='demo_assets'::regclass AND NOT tgisinternal) THEN
            CREATE TRIGGER demo_assets_immutable BEFORE UPDATE OR DELETE ON demo_assets
                FOR EACH ROW EXECUTE FUNCTION m13_assets_append_only();
        END IF;
    END $$""")


def upload_bundle(folder):
    descriptor = json.loads((folder / "bundle.json").read_text())
    bundle_id = hashlib.sha256(canonical(descriptor)).hexdigest()
    blobs = {"bundle.json": canonical(descriptor)}
    for name, digest in descriptor["files"].items():
        path = folder / asset_name(name)
        if not path.resolve().is_relative_to(folder.resolve()):
            raise ValueError("Artifact ngoài bundle")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Bundle đổi nội dung; không upload")
        blobs[name] = raw
    if sum(map(len, blobs.values())) > 10 * 1024 * 1024:
        raise ValueError("Bundle demo vượt10MiB")
    with database() as db:
        db.execute("SELECT pg_advisory_xact_lock(731906)")
        asset_schema(db)
        for name, raw in blobs.items():
            digest = hashlib.sha256(raw).hexdigest()
            previous = db.execute(
                "SELECT sha256 FROM demo_assets WHERE bundle_id=%s AND name=%s", (bundle_id, name)
            ).fetchone()
            if previous:
                if previous[0] != digest:
                    raise ValueError("Bundle ID đã có nội dung khác")
            else:
                db.execute("INSERT INTO demo_assets VALUES (%s,%s,%s,%s)", (bundle_id, name, digest, raw))
    return {"bundle_id": bundle_id, "files": len(blobs), "status": "uploaded_verified"}


def hydrate(bundle_id, output):
    import re

    if not re.fullmatch("[a-f0-9]{64}", bundle_id):
        raise ValueError("Cần bundle ID SHA256 hợp lệ")
    with database() as db:
        rows = db.execute(
            "SELECT name,sha256,content FROM demo_assets WHERE bundle_id=%s", (bundle_id,)
        ).fetchall()
    blobs = {}
    for name, digest, content in rows:
        asset_name(name)
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError("Cloud asset sai hash")
        blobs[name] = bytes(content)
    descriptor = json.loads(blobs["bundle.json"])
    if hashlib.sha256(canonical(descriptor)).hexdigest() != bundle_id:
        raise ValueError("Cloud bundle descriptor sai ID")
    if set(blobs) != {"bundle.json", *descriptor["files"]}:
        raise ValueError("Bundle thiếu/thừa artifact")
    output.mkdir(parents=True, exist_ok=True)
    for name, digest in descriptor["files"].items():
        raw = blobs[name]
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Bundle artifact sai hash")
        target = output / name
        if not target.resolve().is_relative_to(output.resolve()):
            raise ValueError("Artifact path không an toàn")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != raw:
            raise ValueError("Artifact local đã đổi; dùng thư mục hydrate mới")
        if not target.exists():
            target.write_bytes(raw)
    version = descriptor["version"]
    manifest_path = output / f"ranked_queue_{version}.manifest.json"
    manifest = json.loads(blobs[manifest_path.name])
    # Preserve producer metadata verbatim, then derive runtime locations explicitly.
    source_path = output / "source.manifest.json"
    source_path.write_bytes(blobs[manifest_path.name])
    for kind, suffix in [
        ("queue", "csv"),
        ("evidence", "jsonl"),
        ("labels", "json"),
        ("features", "parquet"),
    ]:
        name = (f"ranked_queue_{version}" if kind == "queue" else f"{kind}_{version}") + "." + suffix
        manifest[kind + "_file"] = str(output / name)
    manifest["manifest_file"] = str(manifest_path)
    manifest["preds_file"] = str(output / "predictions.parquet") if manifest.get("preds_file") else None
    manifest["deployment_bundle_id"] = bundle_id
    atomic_json(manifest_path, manifest)
    return descriptor


def backup_cloud(output):
    if output.exists():
        raise ValueError("Backup đã có; chọn file mới")
    with database() as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        result = {"schema": 1, "tables": {}}
        for table in ("verdicts", "state", "demo_assets"):
            cursor = db.execute(f"SELECT * FROM {table}")  # fixed operator-owned table list
            columns = [column.name for column in cursor.description]
            result["tables"][table] = [dict(zip(columns, row, strict=True)) for row in cursor]
        for row in result["tables"]["demo_assets"]:
            row["content"] = base64.b64encode(row["content"]).decode()
    output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(canonical(result))
    return {"status": "backed_up", "file": str(output), "sha256": pipeline.sha256(output)}


def restore_cloud(source):
    from src.api.postgres import initialize

    result = json.loads(source.read_bytes())
    if result["schema"] != 1 or set(result["tables"]) != {"verdicts", "state", "demo_assets"}:
        raise ValueError("Backup không đúng schema")
    with database() as db:
        if any(
            db.execute("SELECT to_regclass(%s)", (name,)).fetchone()[0]
            for name in ("verdicts", "state", "demo_assets")
        ):
            raise ValueError("Chỉ restore database mới trống; không ghi đè dữ liệu đang dùng")
        initialize(db)
        asset_schema(db)
        from psycopg import sql

        for table in ("verdicts", "state", "demo_assets"):
            for row in result["tables"][table]:
                if table == "state" and row["key"].startswith(("auth-session:", "login-attempts:")):
                    continue
                if table == "demo_assets":
                    row["content"] = base64.b64decode(row["content"], validate=True)
                    if hashlib.sha256(row["content"]).hexdigest() != row["sha256"]:
                        raise ValueError("Backup asset sai hash")
                columns = list(row)
                db.execute(
                    sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                        sql.Identifier(table),
                        sql.SQL(",").join(map(sql.Identifier, columns)),
                        sql.SQL(",").join([sql.Placeholder()] * len(columns)),
                    ),
                    [row[c] for c in columns],
                )
        db.execute("SELECT setval('verdicts_id_seq', COALESCE((SELECT MAX(id) FROM verdicts),0)+1,false)")
    return {"status": "restored", "login_sessions": "invalidated"}
