import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from test_cli_flow import flow as flow

from src.api.main import create_app
from src.api.settings import Settings
from src.eval.replay import replay


def run(flow, output):
    return replay(
        flow / "reports_dir/ranked_queue_rule-t1.csv",
        bundle=flow,
        answer_file=flow / "injected_dir/injected_errors.json",
        source_labels=flow / "injected_dir/det_val_injected.json",
        original_labels=flow / "det.json",
        output=output,
    )


def test_replay_preserves_metric_table_hashes_and_proxy(flow, tmp_path):
    output = tmp_path / "replay"
    result = run(flow, output)
    table = pd.read_csv(output / "comparison.csv")
    assert table.iloc[0].recall20_weighted == pytest.approx(result["recall20_weighted"])
    assert table.iloc[1].recall20_weighted == pytest.approx(result["file_order"]["recall20_weighted"])
    assert (
        result["provenance"]["validation"]["changed_objects"]
        == result["provenance"]["validation"]["answer_errors"]
    )
    assert result["measured_time_saved"] is None and "proxy" in result["time_saved_kind"]
    assert result["random_seeds"] == 20
    with pytest.raises(ValueError, match="đã có"):
        run(flow, output)
    settings = Settings(database=tmp_path / "api.db", evaluation_file=output / "evaluation.json")
    client = TestClient(create_app(settings))
    assert client.get("/web/results").json()["provenance"]["answer_sha256"]
    assert client.get("/web/results/gain.png").headers["content-type"] == "image/png"
    (output / "comparison.csv").write_text("changed")
    assert client.get("/web/results").status_code == 503


def test_replay_rejects_wrong_answers_and_original_labels_queue(flow, tmp_path):
    answer_file = flow / "injected_dir/injected_errors.json"
    answer = json.loads(answer_file.read_text())
    answer["errors"].pop()
    answer_file.write_text(json.dumps(answer))
    with pytest.raises(ValueError, match="không khớp"):
        run(flow, tmp_path / "invalid")
