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


def test_startup_recovers_interrupted_work(settings):
    from app.db import make_engine, session_factory
    from app.models import Base, Invoice

    settings.data_dir.mkdir(parents=True)
    engine = make_engine(settings.data_dir / "app.db")
    Base.metadata.create_all(engine)
    with session_factory(engine)() as s:
        s.add(Invoice(status="matching", original_filename="x.pdf", stored_path="x.pdf",
                      media_type="application/pdf", uploaded_at="2026-10-21T09:00:00.000Z"))
        s.commit()
    engine.dispose()

    with TestClient(create_app(settings)) as client:
        client.get("/health")
        with client.app.state.sessions() as s:
            invoice = s.query(Invoice).one()
    assert (invoice.status, invoice.status_reason) == ("matching_failed", "Interrupted by an app restart")
