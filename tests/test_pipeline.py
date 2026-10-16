"""Chạy thử bước 1 -> 3a -> 4 trên fixture: kiểm các module ghép được với nhau."""
from pathlib import Path

import pandas as pd
import pytest

from src import pipeline
from src.contracts import check_queue
from src.data import bdd100k
from src.features import geometric, model_disagreement
from src.scoring import rule

FIXTURE = Path(__file__).parent / "fixtures" / "det_mini.json"


def test_rule_queue_on_fixture():
    objects, images = bdd100k.to_tables(bdd100k.read_frames(FIXTURE))
    signals = {"hard_condition": geometric.hard_condition(objects, images)}
    queue = rule.rank(signals, {"hard_condition": 1.0}, "rule-test")
    assert check_queue(queue) == []
    assert queue.iloc[0]["image_id"] == "img-night-2"
    assert "đêm" in queue.iloc[0]["top_reasons"]


def test_recheck_keeps_detector_thresholds_when_code_defaults_change(tmp_path, monkeypatch):
    from src.contracts import PRED_COLS

    preds = tmp_path / "fixture-predictions.parquet"
    pd.DataFrame([["f", 10, 10, 200, 200, "car", 0.9]], columns=PRED_COLS).to_parquet(preds)
    source = pipeline.publish(
        [{"name": "f.jpg", "labels": []}], tmp_path / "source", "rule-detector-fixture",
        names=[], weights={"model_missing_label": 1}, options={"signals": []}, preds_file=preds,
        provenance={"kind": "unit_test_synthetic_predictions"},
    )
    original = Path(source["queue_file"]).read_bytes()
    before = pd.read_csv(source["queue_file"])
    assert before.risk_score.iloc[0] > 0
    threshold = source["options"]["detector_options"]["missing_conf"]
    assert threshold == model_disagreement.DEFAULTS["missing_conf"]
    monkeypatch.setitem(model_disagreement.DEFAULTS, "missing_conf", 0.99)
    result = pipeline.recheck(
        snapshot={"image_id": "f", "width": 1280, "height": 720, "boxes": []},
        queue=before, output_dir=tmp_path / "after", model_version="rechecked-fixture", seed=42,
        manifest_file=Path(source["manifest_file"]),
    )
    after = pd.read_csv(result["queue_file"])
    assert after.risk_score.tolist() == before.risk_score.tolist()
    assert after.top_reasons.tolist() == before.top_reasons.tolist()
    assert Path(source["queue_file"]).read_bytes() == original
    # An old queue with unknown detector thresholds must not attribute a defaults change to a box edit.
    import json

    manifest = Path(source["manifest_file"])
    legacy = json.loads(manifest.read_text())
    legacy["options"]["detector_options"] = {}
    manifest.write_text(json.dumps(legacy))
    with pytest.raises(ValueError, match="baseline mới"):
        pipeline.recheck(
            snapshot={"image_id": "f", "width": 1280, "height": 720, "boxes": []},
            queue=before, output_dir=tmp_path / "legacy", model_version="legacy-fixture", seed=42,
            manifest_file=manifest,
        )
    assert not (tmp_path / "legacy").exists()
