"""Full data refresh dates must be explicit, not inferred from individual imports."""

from dataclasses import replace
from datetime import date

from fastapi.testclient import TestClient
import pytest

from app.api import data
from app.core.config import Settings
from app.main import app


@pytest.mark.parametrize("recorded_date", [None, date(2026, 10, 15)])
def test_public_status_reports_only_configured_full_refresh_date(monkeypatch, recorded_date):
    monkeypatch.setattr(data, "settings", replace(data.settings, data_updated_on=recorded_date))
    response = TestClient(app).get("/api/data/status")
    assert response.status_code == 200
    assert response.json() == {"updated_on": recorded_date.isoformat() if recorded_date else None}


def test_settings_parse_explicit_full_refresh_date(monkeypatch):
    monkeypatch.setenv("DATA_UPDATED_ON", "2026-10-15")
    assert Settings.from_environment().data_updated_on == date(2026, 10, 15)
    monkeypatch.setenv("DATA_UPDATED_ON", "")
    assert Settings.from_environment().data_updated_on is None
    monkeypatch.delenv("DATA_UPDATED_ON")
    assert Settings.from_environment().data_updated_on is None


def test_invalid_full_refresh_date_fails_explicitly(monkeypatch):
    monkeypatch.setenv("DATA_UPDATED_ON", "2026-02-30")
    with pytest.raises(ValueError):
        Settings.from_environment()
