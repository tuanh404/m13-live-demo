"""Render entrypoint: fail closed without Postgres, frozen data and a backend secret."""

import hashlib
import json
import os
from pathlib import Path

from src.api.auth import password_hash
from src.api.cloud import hydrate
from src.api.saved_labels import atomic_json
from src.api.settings import Settings


def create_render_app():
    import faulthandler

    print("M13 startup: validating backend configuration", flush=True)
    url, secret = os.environ.get("M13_DATABASE_URL"), os.environ.get("M13_AUTH_SECRET", "")
    origin = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("M13_PUBLIC_ORIGIN", "")
    if not url or len(secret) < 32 or not origin.startswith("https://"):
        raise ValueError("Render cần Postgres, auth secret và HTTPS origin; không chạy public chưa bảo vệ")
    root = Path(os.environ.get("M13_RENDER_DATA", "/tmp/m13-render"))
    # A fresh hydrate folder avoids silently replacing immutable files after a redeploy.
    bundle = os.environ["M13_DEMO_BUNDLE_ID"]
    artifacts = root / "assets"
    if artifacts.exists():
        # Manifest locations are derived on every boot; raw source files remain in Postgres.
        import tempfile

        artifacts = Path(tempfile.mkdtemp(prefix="assets-", dir=root))
    # A slow startup must leave a useful diagnostic, without logging config values.
    faulthandler.dump_traceback_later(60)
    try:
        print("M13 startup: loading immutable demo assets", flush=True)
        descriptor = hydrate(bundle, artifacts)
    finally:
        faulthandler.cancel_dump_traceback_later()
    print("M13 startup: assets verified; preparing review API", flush=True)
    accounts = root / "accounts.json"
    atomic_json(
        accounts,
        {
            "users": {
                "guest": {
                    "role": "demo",
                    "password_hash": password_hash(
                        secret, salt=hashlib.sha256(("m13-demo:" + secret).encode()).hexdigest()[:32]
                    ),
                }
            }
        },
    )
    accounts.chmod(0o600)
    settings = Settings(
        database=root / "unused.db",
        database_url=url,
        images=artifacts / "images",
        reports=artifacts,
        queue_file=artifacts / f"ranked_queue_{descriptor['version']}.csv",
        queue_batches={},
        mapping=artifacts / "absent-map.parquet",
        predictions=artifacts / "predictions.parquet",
        cvat_url="https://cvat.invalid",
        guideline_url="",
        data_purpose=descriptor.get("data_purpose", "development"),
        accounts_file=accounts,
        guest_demo=True,
        public_origin=origin.rstrip("/"),
        auth_cookie_secure=True,
        snapshot_dir=str(root / "disabled-snapshots"),
        recheck_dir=str(root / "disabled-rechecks"),
        intake_config=None,
        recheck_backend=None,
        evaluation_file=(artifacts / "baseline/evaluation.json")
        if (artifacts / "baseline/evaluation.json").is_file()
        else None,
    )
    from src.api.main import create_app

    faulthandler.dump_traceback_later(60)
    try:
        app = create_app(settings)
        previous_ids = json.loads(os.environ.get("M13_PREVIOUS_DEMO_BUNDLE_IDS", "[]"))
        if not isinstance(previous_ids, list) or len(previous_ids) > 5:
            raise ValueError("Chỉ giữ tối đa 5 bundle lịch sử đã kiểm")
        versions = app.state.store.state("versions") or {}
        for previous in previous_ids:
            if previous == bundle:
                continue
            # hydrate derives local manifest paths. A process restart must not
            # compare those rewritten runtime paths with the original raw blob.
            # The current hydrate root is fresh on every boot; history follows it.
            history = artifacts / "history" / previous
            old = hydrate(previous, history)
            versions[old["version"]] = {
                "queue_id": old["queue_sha256"],
                "queue_file": str(history / f"ranked_queue_{old['version']}.csv"),
                "model_version": old["version"],
            }
        if versions:
            app.state.store.state("versions", versions)
    finally:
        faulthandler.cancel_dump_traceback_later()
    print("M13 startup: review API ready", flush=True)
    @app.get("/build", include_in_schema=False)
    def build():
        import re

        revision = os.environ.get("RENDER_GIT_COMMIT", "")
        return {"revision": revision if re.fullmatch(r"[a-f0-9]{40}", revision) else None}

    return app
