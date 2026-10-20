import logging

import pytest
from fastapi.testclient import TestClient

from app.config import MissingSetting, get_settings
from app.main import create_app


def test_missing_key_refuses_start(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    with pytest.raises(MissingSetting) as err:
        get_settings(env_file=None)
    assert "ANTHROPIC_API_KEY" in str(err.value)
    assert ".env" in str(err.value)


def test_defaults(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-abc")
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("REFERENCE_API_URL", raising=False)
    settings = get_settings(env_file=None)
    assert settings.anthropic_model == "claude-opus-5-5"
    assert settings.reference_api_url == "http://api:8000"


def test_health(settings):
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_key_never_logged(settings, caplog):
    caplog.set_level(logging.DEBUG)
    with TestClient(create_app(settings)) as client:
        client.get("/health")
    assert all("SECRET123" not in record.getMessage() for record in caplog.records)
