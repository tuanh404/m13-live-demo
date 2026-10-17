"""Fixed, server-configured evaluation artifacts; no client-supplied file paths."""

import json

from fastapi import HTTPException
from fastapi.responses import FileResponse

from src import config, pipeline


def install_results(app, settings):
    @app.get("/web/team-timing")
    def team_timing():
        from src.api.team_timing import read_timing

        try:
            return read_timing()
        except (OSError, ValueError, KeyError, TypeError):
            raise HTTPException(503, "Chưa đọc được kết quả nhóm cung cấp") from None

    def read():
        if not settings.evaluation_file or not settings.evaluation_file.is_file():
            raise HTTPException(404, "Chưa cấu hình báo cáo baseline đã tái lập")
        try:
            result = json.loads(settings.evaluation_file.read_text())
        except (OSError, ValueError) as exc:
            raise HTTPException(503, "Báo cáo baseline thiếu hoặc không đọc được") from exc
        for name in ("gain_curve.png", "comparison.csv"):
            path = settings.evaluation_file.parent / name
            if not path.is_file() or pipeline.sha256(path) != result["artifacts"][name]:
                raise HTTPException(503, "Artifact kết quả đã đổi hash; không hiển thị báo cáo cũ")
        return result

    @app.get("/results", include_in_schema=False)
    def page():
        from pathlib import Path

        return FileResponse(Path(__file__).with_name("web") / "results.html")

    @app.get("/web/results")
    def results():
        result = read()
        result["dataset_kind"] = (
            "bdd2018_labels_verified"
            if result["provenance"]["original_labels_sha256"]
            == config.load("review_acceptance")["labels_sha256"]
            else "fixture_or_unverified"
        )
        # Only hashes and metric metadata, not local producer/developer paths.
        return result

    @app.get("/web/results/gain.png")
    def figure():
        read()
        return FileResponse(settings.evaluation_file.parent / "gain_curve.png")
