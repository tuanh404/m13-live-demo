"""Separate team-reported timing from reproducible offline/injected-error metrics."""

import json

from src import config


def read_timing():
    value = json.loads((config.ROOT / "reports/team-timing.json").read_text())
    manual, assisted = value["manual_minutes"], value["assisted_minutes"]
    if (
        value["kind"] != "team_reported_measurement"
        or value["image_count"] != 10
        or not 0 < assisted <= manual
        or value["log_verified"] is not False
        or value["error_count"] is not None
        or value["recall"] is not None
    ):
        raise ValueError("Kết quả nhóm cung cấp thiếu trạng thái kiểm chứng")
    return {**value, "reduction_fraction": (manual - assisted) / manual}
