"""Prepare an isolated shared demo and data-only backups. Never publish or run Docker here."""

from __future__ import annotations

import json
import os
import secrets
import shlex
import shutil
import sqlite3
from urllib.parse import urlsplit

from src import config, pipeline
from src.api.auth import password_hash
from src.api.review_setup import prepare, verify


def _target(output):
    output = output.resolve()
    if not output.is_relative_to(config.ROOT / "data") or output.exists():
        raise ValueError("Chọn thư mục data mới; không ghi đè deployment/DB có sẵn")
    if any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_/." for c in str(
        output.relative_to(config.ROOT)
    )):
        raise ValueError("Đường dẫn deployment chỉ dùng chữ/số/gạch nối")
    return output


def _configure(output, origin):
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path or parsed.query:
        raise ValueError("Origin cần http(s)://host[:port], không có prefix")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Origin không chứa credentials/fragment")
    if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Public/shared demo phải dùng HTTPS")
    relative = output.relative_to(config.ROOT).as_posix()
    record = json.loads((output / "review.json").read_text())
    version = record["version"]
    values = {
        "QUEUE_FILE": f"{relative}/ranked_queue_{version}.csv",
        "EVIDENCE_FILE": f"{relative}/evidence_{version}.jsonl", "IMAGES": f"{relative}/images",
        "PREDICTIONS": f"{relative}/predictions.parquet", "DATABASE": f"{relative}/review.db",
        "MAPPING": f"{relative}/cvat_map.parquet", "SNAPSHOT_DIR": f"{relative}/snapshots",
        "RECHECK_DIR": f"{relative}/rechecks", "DATA_PURPOSE": record["purpose"],
        "CVAT_URL": record["identity"]["cvat_url"], "ACCOUNTS_FILE": f"{relative}/accounts.json",
        "RECHECK_BACKEND": "src.pipeline:recheck",
        "PUBLIC_ORIGIN": origin, "AUTH_COOKIE_SECURE": str(parsed.scheme == "https").lower(),
    }
    if (output / "evaluation/evaluation.json").is_file():
        values["EVALUATION_FILE"] = f"{relative}/evaluation/evaluation.json"
    (output / "runtime.env").write_text("".join(
        f"export M13_{k}={shlex.quote(v)}\n" for k, v in values.items()
    ))
    (output / "container.env").write_text("".join(f"M13_{k}={v}\n" for k, v in values.items()))
    (output / "compose.env").write_text(
        f"M13_DEPLOY_ROOT={output}\nM13_DEPLOY_REL={relative}\n"
        f"M13_SITE={parsed.hostname}\nM13_PUBLIC_ORIGIN={origin}\n"
        f"M13_HTTPS_PORT={parsed.port or 443}\nM13_HTTP_PORT=8085\nM13_BIND_ADDRESS=127.0.0.1\n"
        f"M13_RUN_UID={os.getuid()}\nM13_RUN_GID={os.getgid()}\n"
    )
    users, access = {}, []
    for name, role in (("demo", "demo"), ("operator", "admin")):
        password = secrets.token_urlsafe(24)
        users[name] = {"role": role, "password_hash": password_hash(password)}
        access.append(f"{name}: {password}\n")
    (output / "accounts.json").write_text(json.dumps({"users": users}, indent=2) + "\n")
    (output / "accounts.json").chmod(0o600)
    # Plaintext access instructions stay outside the mounted deployment and backups.
    access_file = output.with_name(output.name + "-access.txt")
    with access_file.open("x") as handle:
        handle.write("PRIVATE: credentials for this deployment only. Never package/commit/screenshot.\n")
        handle.writelines(access)
    access_file.chmod(0o600)
    record["files"]["runtime.env"] = pipeline.sha256(output / "runtime.env")
    (output / "review.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    description = {"schema_version": 1, "origin": origin, "relative_root": relative,
                   "data_purpose": record["purpose"], "cvat_live_verified": False,
                   "mode": "isolated_shared_review_demo", "public_live_verified": False,
                   "image_tag": "m13-demo:local-verified"}
    (output / "deployment.json").write_text(json.dumps(description, indent=2) + "\n")
    output.chmod(0o700)
    return {"folder": str(output), "origin": origin, "credentials_file": str(access_file),
            "public_live_verified": False, "cvat_live_verified": False}


def prepare_deployment(source, output, origin, *, original_labels=None, evaluation=None):
    output = _target(output)
    source = source.resolve()
    record = verify(source)
    prepare(source / f"ranked_queue_{record['version']}.csv", source / "images", output,
            source_root=source, limit=record["images"], purpose=record["purpose"],
            original_labels=original_labels, cvat_url=record["identity"]["cvat_url"])
    if evaluation:
        result = json.loads(evaluation.read_text())
        (output / "evaluation").mkdir()
        for name in ("comparison.csv", "gain_curve.png"):
            file = evaluation.parent / name
            if pipeline.sha256(file) != result["artifacts"][name]:
                raise ValueError("Báo cáo baseline khác hash")
            shutil.copyfile(file, output / "evaluation" / name)
        shutil.copyfile(evaluation, output / "evaluation/evaluation.json")
    return _configure(output, origin)


def backup(folder, output):
    folder = folder.resolve()
    output = _target(output)
    if output.is_relative_to(folder):
        raise ValueError("Backup phải nằm ngoài thư mục deployment")
    verify(folder)
    output.mkdir(parents=True, mode=0o700)
    skipped = {"accounts.json", "compose.env", "container.env"}
    for file in folder.rglob("*"):
        if file.is_symlink():
            raise ValueError("Không backup symlink ngoài deployment")
        if not file.is_file() or file.name in skipped or file.name.endswith(("-wal", "-shm")):
            continue
        target = output / file.relative_to(folder)
        target.parent.mkdir(parents=True, exist_ok=True)
        if file.name == "review.db":
            with sqlite3.connect(file) as src, sqlite3.connect(target) as dst:
                src.backup(dst)
        else:
            shutil.copyfile(file, target)
        target.chmod(0o600)
    manifest = {"source_relative_root": folder.relative_to(config.ROOT).as_posix(),
                "files": {p.relative_to(output).as_posix(): pipeline.sha256(p)
                          for p in output.rglob("*") if p.is_file()},
                "accounts_included": False, "cvat_volumes_included": False}
    (output / "backup.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return {"backup": str(output), "files": len(manifest["files"]), "accounts_included": False}


def restore(folder, output, origin):
    folder = folder.resolve()
    output = _target(output)
    if output.is_relative_to(folder):
        raise ValueError("Restore phải nằm ngoài thư mục backup")
    manifest = json.loads((folder / "backup.json").read_text())
    for name, digest in manifest["files"].items():
        file = folder / name
        if not file.resolve().is_relative_to(folder) or pipeline.sha256(file) != digest:
            raise ValueError("Backup sai hash/đường dẫn; không restore")
    output.mkdir(parents=True, mode=0o700)
    old, new = manifest["source_relative_root"], output.relative_to(config.ROOT).as_posix()

    def relocate(value):
        if isinstance(value, dict):
            return {k: relocate(v) for k, v in value.items()}
        if isinstance(value, list):
            return [relocate(v) for v in value]
        if isinstance(value, str) and value.startswith(old + "/"):
            return new + value[len(old):]
        if isinstance(value, str) and value.startswith(str(config.ROOT / old) + "/"):
            return str(output) + value[len(str(config.ROOT / old)):]
        return value

    for name in manifest["files"]:
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if name.endswith(".manifest.json"):
            target.write_text(json.dumps(relocate(json.loads((folder / name).read_text())), indent=2) + "\n")
        else:
            shutil.copyfile(folder / name, target)
    result = _configure(output, origin)
    if (output / "review.db").is_file():
        with sqlite3.connect(output / "review.db") as db:
            for key, value in db.execute("SELECT key,value FROM state").fetchall():
                db.execute(
                    "UPDATE state SET value=? WHERE key=?", (json.dumps(relocate(json.loads(value))), key)
                )
    record = json.loads((output / "review.json").read_text())
    # A backup may be restored on another host. Never reuse that machine's task IDs implicitly.
    mapping = output / "cvat_map.parquet"
    if mapping.exists():
        mapping.rename(output / "cvat_map.previous-host.parquet")
        record.pop("cvat", None)
        record["files"].pop("cvat_map.parquet", None)
    for name in record["files"]:
        record["files"][name] = pipeline.sha256(output / name)
    (output / "review.json").write_text(json.dumps(record, indent=2) + "\n")
    verify(output)
    # Fresh accounts invalidate restored login sessions; historical verdicts remain.
    return result
