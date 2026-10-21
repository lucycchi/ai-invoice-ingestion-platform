"""Fixes from the second review of the finished app against the PRD and the documents."""

import json
import re
import sqlite3
from decimal import Decimal as D
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.checks import NO_TOTAL, arithmetic_warnings, count_discrepancies
from app.main import create_app
from app.models import Extraction, Run
from tests.conftest import REPO_ROOT
from tests.test_line_matching import _bad_for, env, expected_answer  # noqa: F401  (env is a fixture)
from tests.test_metadata import _suggest
from tests.test_review import _item_id, _line, _override


# A not-found field starts empty (R23).

def test_site_lowered_to_not_found_is_not_preselected():
    site = _suggest(site_name="Harborview Clinic", protocol_number="CON-CAT-2024-101")["site"]
    assert site.confidence == "not_found"
    assert site.entity_id is None


# Container-only settings can't be overridden from .env.

def test_compose_pins_container_settings():
    compose = (REPO_ROOT / "docker-compose.yml").read_text()
    for line in ("REFERENCE_API_URL: http://api:8000", "DATA_DIR: /data", "HOST: 0.0.0.0"):
        assert line in compose, line
    assert "${REFERENCE_API_URL" not in compose


def test_app_listens_on_this_machine_only_by_default(settings, monkeypatch):
    import app.__main__ as entry

    seen = {}
    monkeypatch.setattr(entry, "get_settings", lambda: settings)
    monkeypatch.setattr(entry.uvicorn, "run", lambda app, host, port: seen.update(host=host, port=port))
    entry.main()
    assert seen == {"host": "127.0.0.1", "port": 8080}


# Skipped checks are notes, not arithmetic warnings (R16, R49).

def test_skipped_checks_are_not_counted():
    missing = "Line 2: this line's arithmetic couldn't be checked because a number is missing."
    wrong = "Line 3: 2 × $10.00 = $20.00, but the invoice says $25.00."
    assert count_discrepancies([NO_TOTAL, missing, wrong]) == 1


def test_finalize_summary_ignores_a_missing_total(env):
    invoice_id = env.run()
    with env.client.app.state.sessions() as s:
        s.query(Extraction).filter_by(invoice_id=invoice_id).one().arithmetic_warnings = json.dumps([NO_TOTAL])
        s.commit()
    assert "0 arithmetic warnings" in env.client.get(f"/invoices/{invoice_id}/finalize").text


# Fractions of a cent don't produce a contradictory warning.

def test_sub_cent_amounts_compared_to_the_cent():
    line = SimpleNamespace(quantity=1.0, unit_price=D("1.001"), amount=D("1.001"))
    assert arithmetic_warnings([line], D("1.001")) == []


# Every run records when it ended (R51).

def test_failed_matching_run_has_an_end_time(env):
    env.claude.match = _bad_for(set(range(7, 13)), expected_answer("large_invoice"))
    run = env.matching_run(env.run())
    assert run.outcome.startswith("failed") and run.stored_at is None and run.ended_at


def test_successful_runs_have_an_end_time(env):
    invoice_id = env.run()
    with env.client.app.state.sessions() as s:
        runs = s.query(Run).filter_by(invoice_id=invoice_id).all()
    assert {r.step for r in runs} == {"extraction", "matching"} and all(r.ended_at for r in runs)


def test_older_database_gains_the_end_time_column(settings):
    with TestClient(create_app(settings)):
        pass
    db = sqlite3.connect(settings.data_dir / "app.db")
    db.execute("ALTER TABLE runs DROP COLUMN ended_at")
    db.commit()
    db.close()
    with TestClient(create_app(settings)):
        pass
    columns = [row[1] for row in sqlite3.connect(settings.data_dir / "app.db").execute("PRAGMA table_info(runs)")]
    assert "ended_at" in columns


# Smaller fixes.

def test_retry_unknown_invoice_is_404(env):
    assert env.client.post("/invoices/999/retry").status_code == 404


def test_change_metadata_counts_are_singular(env):
    invoice_id = env.run()
    line, _ = _line(env, invoice_id, 10)
    _override(env, invoice_id, line.id, _item_id(env, invoice_id, "PROC-ECG-Read"))
    page = env.client.get(f"/invoices/{invoice_id}/change-metadata").text
    assert "27 matches and 1 override." in page


def test_oversized_upload_page_has_the_app_layout(env):
    big = b"%PDF-" + b"x" * (11 * 1024 * 1024)
    response = env.client.post("/invoices", files={"file": ("big.pdf", big)})
    assert response.status_code == 413
    assert "Invoice ingestion" in response.text and 'href="/"' in response.text


def test_picker_lists_each_item_once(env):
    invoice_id = env.run()
    line, match = _line(env, invoice_id, 10)
    alternative = _item_id(env, invoice_id, "PROC-ECG-Read")
    with env.client.app.state.sessions() as s:
        s.get(type(match), match.id).ai_alternatives = json.dumps([alternative])
        s.commit()
    _override(env, invoice_id, line.id, alternative)
    row = re.search(r'<tr id="line-10".*?</tr>', env.client.get(f"/invoices/{invoice_id}").text, re.S).group(0)
    values = re.findall(r'<option value="(\d+)"', row)
    assert len(values) == len(set(values))
