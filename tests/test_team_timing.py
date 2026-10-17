import pytest
from fastapi.testclient import TestClient
from test_web_review import web_settings as web_settings

from src.api.main import create_app
from src.api.team_timing import read_timing


def test_team_report_does_not_invent_pilot_sample_recall_or_verified_logs(web_settings):
    result = read_timing()
    assert result['image_count'] == 10 and result['same_images']
    assert result['assisted_minutes'] == 20 and result['manual_minutes'] == 45
    assert result['reduction_fraction'] == pytest.approx(25 / 45)
    assert result['log_verified'] is False
    assert result['reviewer_count'] is None and result['recall'] is None
    assert result['error_count'] is None
    assert 'projection' not in result
    client = TestClient(create_app(web_settings))
    assert client.get('/web/team-timing').json() == result
    assert 'chưa đối chiếu log' in client.get('/results').text
