"""Build a local, secret-free source/submission bundle. Never push or publish."""

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def main():
    import os

    os.chdir(ROOT)
    out = ROOT / "data/mvp-submission"
    out.mkdir(parents=True, exist_ok=True)
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, default=ROOT / "data/mvp-final/pytest-final.log")
    parser.add_argument(
        "--source-public",
        action="store_true",
        help="Operator has verified anonymous access to the source repository",
    )
    args = parser.parse_args()
    source_public = args.source_public
    log = args.log
    deploy_path = ROOT / "data/mvp-final/03-public-deployment.json"
    deploy = json.loads(deploy_path.read_text()) if deploy_path.exists() else {}
    public_path = ROOT / "data/mvp-final/06-published-assets.json"
    public_assets = json.loads(public_path.read_text()).get("assets", {}) if public_path.exists() else {}
    text = log.read_text()
    if not re.search(r"\d+ passed, 1 skipped", text) or " failed," in text:
        raise ValueError("Final pytest is not green; do not claim a completed verification")
    result = re.search(r"(\d+) passed, (\d+) skipped.* in ([\d.]+)s", text)
    stamp = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat()
    verification = {
        "checked_at": stamp,
        "base_commit": "72b1e4c05f37969f0806746862a7657d585502ce",
        "branch": "feat/tuanh-mvp-live-rebuild",
        "uncommitted_working_tree": True,
        "pytest_passed": int(result[1]),
        "pytest_skipped": int(result[2]),
        "pytest_seconds": float(result[3]),
        "pytest_log_sha256": digest(log),
        "opt_in": ["M13_BROWSER_TESTS", "M13_WEB_BROWSER_TESTS", "M13_TEST_DATABASE_URL"],
        "skip": "BDD loader default path absent; separate acquired BDD bundle checked independently",
        "real_CVAT_jobs": [20, 21],
        "annotations": "synthetic test boxes on real BDD photos",
        "human_pilot": False,
        "usability_with_new_person": "not_evaluated",
        "public_deploy_commit": deploy.get("commit"),
        "remote_ci": deploy.get("ci_url"),
        "remote_ci_conclusion": deploy.get("ci_conclusion"),
        "remote_ci_workflow_status": deploy.get("ci_workflow_status", "completed"),
        "L06_changes_deployed": deploy.get("status") == "live_verified",
        "team_timing": "10 images,20/45 minutes, team-reported; logs not verified",
        "backend_test_commit": deploy.get("commit"),
        "media_checks": json.loads((ROOT / "data/mvp-media-refresh/media-verification.json").read_text())
        if (ROOT / "data/mvp-media-refresh/media-verification.json").exists()
        else None,
    }
    (ROOT / "reports/mvp-verification.json").write_text(json.dumps(verification, indent=2) + "\n")
    names = set()
    for args in (("ls-files", "-z"), ("ls-files", "--others", "--exclude-standard", "-z")):
        names.update(subprocess.check_output(["git", *args]).decode().split("\0"))
    excluded = ("data/", "models/", "build/", "dist/", ".git/", ".venv/", ".aws/", ".codex/", ".agents/")
    files = sorted(
        n
        for n in names
        if n
        and not n.startswith(excluded)
        and ".egg-info/" not in n
        and n != "LENH_HOAN_THIEN_MVP_M13.md"
        and not Path(n).name.startswith(".env")
        and Path(n).suffix not in {".env", ".key", ".pem", ".db", ".sqlite", ".sqlite3"}
        and (ROOT / n).is_file()
        and not (ROOT / n).is_symlink()
    )
    module = importlib.util.spec_from_file_location("repo_checker", ROOT / ".github/scripts/check_repo.py")
    checker = importlib.util.module_from_spec(module)
    module.loader.exec_module(checker)
    bad = {n: errors for n in files if (errors := checker.check(n))}
    if bad:
        raise ValueError(f"Source packaging rejected paths: {list(bad)}")
    assert "src/data/bdd_subset.py" in files and "src/api/job_registry.py" in files
    snapshot = {
        "checked_at": stamp,
        "base_commit": verification["base_commit"],
        "working_tree": True,
        "files": {n: digest(ROOT / n) for n in files},
    }
    source = out / "M13-source-final.zip"
    with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as z:
        for name in files:
            z.write(ROOT / name, name)
        z.writestr("SOURCE_SNAPSHOT.json", json.dumps(snapshot, indent=2) + "\n")
    entries = {
        "readme": "README.md",
        "architecture": "docs/mvp/architecture.svg",
        "spec_design": "docs/mvp/spec-design.md",
        "testing": "docs/mvp/testing.md",
        "weekly_logs": "reports/weekly-mvp-2026-10-16.md",
        "support": "docs/mvp/support-matrix.md",
        "status_13_groups": "docs/mvp/acceptance-status.md",
        "pitch_source": "docs/mvp/pitch.html",
        "pitch_pdf": "data/mvp-submission/pitch.pdf",
        "thumbnail_source": "docs/mvp/thumbnail.svg",
        "thumbnail_png": "data/mvp-submission/thumbnail.png",
        "video": "data/mvp-submission/M13-demo.mp4",
        "video_script": "docs/mvp/video-script.md",
        "source_zip": "data/mvp-submission/M13-source-final.zip",
        "verification": "reports/mvp-verification.json",
        "team_timing": "reports/team-timing.json",
        "detector_cache": "docs/mvp/detector-cache.md",
        "weekly_release": "reports/weekly-mvp-2026-10-17.md",
        "upload_guide": "docs/mvp/upload-quickstart.md",
        "media_refresh": "docs/mvp/media-refresh.md",
        "editable_slides": "data/mvp-submission/M13-slides-editable.zip",
        "weekly_latest": "reports/weekly-mvp-2026-10-18.md",
    }
    artifacts = {}
    for key, name in entries.items():
        p = ROOT / name
        if not p.is_file():
            raise ValueError(f"Missing submission artifact: {name}")
        published = public_assets.get(p.name)
        if published and published["sha256"] != digest(p):
            raise ValueError(f"Public artifact is stale: {p.name}")
        artifacts[key] = {
            "path": name,
            "bytes": p.stat().st_size,
            "sha256": digest(p),
            "publication": "public_verified" if published else "local_only",
            "public_url": published.get("url") if published else None,
        }
    manifest = {
        "project_name": "M13 — Reviewer Prioritization Assistant",
        "description_vi": "Trợ lý ưu tiên kiểm nhãn detection2D trên BDD100K: xếp hàng đợi rủi ro, "
        "hiện lý do và box nghi vấn để QC đối chiếu, lưu kết luận và thống kê.",
        "checked_at": stamp,
        "plan": "6-lenh-v1/L06/media-refresh-2026-10-18",
        "live": {
            "url": "https://m13-live-demo.onrender.com",
            "access": "public; Trải nghiệm demo",
            "scope": "10 real BDD demo images with cached predictions; private YOLO detection uploads "
            "with six partial geometry/context checks; no public CVAT or new-image detector inference",
        },
        "source": {
            "team_url": "https://github.com/cuongherok4/qc2d_auto_assistant",
            "team_access": "L06 historical public check; not final-source publication",
            "team_contains_L06_diff": False,
            "deploy_repo": "https://github.com/tuanh404/m13-live-demo",
            "deploy_repo_visibility": "public_verified" if source_public else "not_verified_by_this_build",
            "latest_source_url": "https://github.com/tuanh404/m13-live-demo" if source_public else None,
            "L06_source": "sanitized source ZIP and separate source repository; team repo unchanged",
        },
        "artifacts": artifacts,
        "video": json.loads((out / "video-record.json").read_text()),
        "submission_status": "NOT_SUBMITTED",
        "remaining_human_actions": ([] if source_public else ["Verify source publication access"])
        + [
            "Human usability and30-image/two-reviewer pilot, if claiming real measured benefit",
            "Fill actual shared URLs and submit BTC form",
        ],
        "limits": [
            "Team reports10-image20/45minutes; no raw logs or30-image pilot",
            "No public CVAT Save/recheck",
            "New-job detector only uses image/model/hash-verified cache; no online inference",
            "Rechecks retain the original audit schedule; source baseline remains immutable",
        ],
    }
    (out / "submission.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    (out / "source-check.json").write_text(
        json.dumps(
            {
                "source_files": len(files),
                "checker": "standard tracked checker plus every packaged new file",
                "rejected": [],
                "source_zip_sha256": digest(source),
                "exclusions": list(excluded) + ["personal plan file"],
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Local submission: {len(files)} checked source files; {len(artifacts)} artifacts; no publish.")


if __name__ == "__main__":
    main()
