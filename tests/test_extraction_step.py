import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.clients.claude import ClaudeFailed, Usage
from app.main import create_app
from app.models import Extraction, Invoice, LineItem, Run
from app.schemas import ExtractionAnswer
from tests.conftest import REPO_ROOT
from tests.fakes import FakeClaude, FakeReference

SAVED = Path(__file__).parent / "fixtures" / "claude"


def saved_extraction(name: str) -> ExtractionAnswer:
    return ExtractionAnswer.model_validate_json((SAVED / f"extract_{name}.json").read_text())


def _app(settings, claude, reference=None):
    return TestClient(create_app(settings, claude=claude, reference=reference or FakeReference()), follow_redirects=False)


def _upload(client, sample="simple-invoice.pdf"):
    data = (REPO_ROOT / "sample-invoices" / sample).read_bytes()
    response = client.post("/invoices", files={"file": (sample, data)})
    return int(response.headers["location"].rsplit("/", 1)[1])


def _get(client, model, invoice_id):
    with client.app.state.sessions() as s:
        if model is Invoice:
            return s.get(Invoice, invoice_id)
        return s.query(model).filter_by(invoice_id=invoice_id).order_by(model.id).all()


def test_simple_invoice_read(settings):
    with _app(settings, FakeClaude(extraction=saved_extraction("simple_invoice"))) as client:
        invoice_id = _upload(client)
        invoice = _get(client, Invoice, invoice_id)
        [extraction] = _get(client, Extraction, invoice_id)
        lines = _get(client, LineItem, invoice_id)
    assert invoice.status == "awaiting_confirmation"
    assert extraction.printed_total == Decimal("2230.00")
    assert json.loads(extraction.header)["invoice_number"] == "INV-2024-001"
    assert [line.position for line in lines] == [1, 2, 3, 4, 5]
    assert lines[1].unit_price == Decimal("480.00") and lines[1].quantity == 2
    assert json.loads(extraction.arithmetic_warnings) == []


def test_large_invoice_keeps_order(settings):
    with _app(settings, FakeClaude(extraction=saved_extraction("large_invoice"))) as client:
        invoice_id = _upload(client, "large-invoice.pdf")
        lines = _get(client, LineItem, invoice_id)
    assert len(lines) == 27
    assert lines[24].description == "Parking Reimbursement"
    assert lines[26].description == "Translator Services"


def test_not_an_invoice(settings):
    answer = saved_extraction("simple_invoice").model_copy(update={"is_invoice": False})
    with _app(settings, FakeClaude(extraction=answer)) as client:
        invoice = _get(client, Invoice, _upload(client))
    assert (invoice.status, invoice.status_reason) == ("extraction_failed", "This file doesn't look like an invoice.")


def test_claude_fails_three_times(settings):
    failure = ClaudeFailed("Claude timed out after 120 seconds (after 3 tries)", Usage(requests=3))
    with _app(settings, FakeClaude(extraction=failure)) as client:
        invoice_id = _upload(client)
        invoice = _get(client, Invoice, invoice_id)
        [run] = _get(client, Run, invoice_id)
    assert invoice.status == "extraction_failed"
    assert invoice.status_reason.startswith("Couldn't read the invoice:")
    assert run.claude_requests == 3 and run.outcome.startswith("failed")


def test_retry_after_failure(settings):
    claude = FakeClaude(extraction=ClaudeFailed("Claude timed out", Usage(requests=3)))
    with _app(settings, claude) as client:
        invoice_id = _upload(client)
        claude.extraction = saved_extraction("simple_invoice")
        response = client.post(f"/invoices/{invoice_id}/retry")
        assert response.status_code == 303
        assert _get(client, Invoice, invoice_id).status == "awaiting_confirmation"
        assert client.post(f"/invoices/{invoice_id}/retry").status_code == 409


def test_missing_file(settings):
    claude = FakeClaude(extraction=saved_extraction("simple_invoice"))
    app = create_app(settings, claude=claude, reference=FakeReference())
    with TestClient(app, follow_redirects=False) as client:
        from app.jobs import run_guarded
        from app.steps.extraction import run_extraction

        invoice_id = _upload(client)
        with client.app.state.sessions() as s:
            invoice = s.get(Invoice, invoice_id)
            invoice.status = "extracting"
            for row in s.query(LineItem).filter_by(invoice_id=invoice_id):
                s.delete(row)
            s.query(Extraction).filter_by(invoice_id=invoice_id).delete()
            s.commit()
            (settings.data_dir / "uploads" / invoice.stored_path).unlink()
        run_guarded(client.app.state.sessions, invoice_id, lambda: run_extraction(client.app, invoice_id))
        invoice = _get(client, Invoice, invoice_id)
    assert (invoice.status, invoice.status_reason) == (
        "extraction_failed",
        "The uploaded file is missing; please upload it again",
    )


def test_unexpected_error_reason(settings):
    with _app(settings, FakeClaude(extraction=RuntimeError("secret invoice text"))) as client:
        invoice = _get(client, Invoice, _upload(client))
    assert invoice.status == "extraction_failed"
    assert invoice.status_reason == "Unexpected error (RuntimeError); details are in the app log"


def test_run_recorded(settings):
    with _app(settings, FakeClaude(extraction=saved_extraction("simple_invoice"))) as client:
        [run] = _get(client, Run, _upload(client))
    assert run.step == "extraction"
    assert run.claude_requests == 1 and run.input_tokens == 1500 and run.output_tokens == 400
    assert run.started_at and run.stored_at and run.outcome == "succeeded"


def test_progress_while_reading(settings):
    with _app(settings, FakeClaude(extraction=saved_extraction("simple_invoice"))) as client:
        invoice_id = _upload(client)
        with client.app.state.sessions() as s:
            s.get(Invoice, invoice_id).status = "extracting"
            s.commit()
        part = client.get(f"/invoices/{invoice_id}/progress")
        assert "Reading your invoice" in part.text and "HX-Refresh" not in part.headers
        with client.app.state.sessions() as s:
            s.get(Invoice, invoice_id).status = "awaiting_confirmation"
            s.commit()
        assert client.get(f"/invoices/{invoice_id}/progress").headers.get("HX-Refresh") == "true"


def test_list_shows_invoice_number(settings):
    with _app(settings, FakeClaude(extraction=saved_extraction("simple_invoice"))) as client:
        _upload(client)
        page = client.get("/").text
    assert "INV-2024-001" in page


def test_invoice_page_shows_extraction_time(settings):
    with _app(settings, FakeClaude(extraction=saved_extraction("simple_invoice"))) as client:
        page = client.get(f"/invoices/{_upload(client)}").text
    assert "Reading took" in page


def test_suggestions_stored(settings):
    from app.models import MetadataSuggestion

    with _app(settings, FakeClaude(extraction=saved_extraction("simple_invoice"))) as client:
        rows = _get(client, MetadataSuggestion, _upload(client))
    assert {(r.field, r.entity_id, r.confidence) for r in rows} == {
        ("sponsor", 2, "exact"), ("study", 3, "exact"), ("site", 1, "exact")
    }


def test_reference_down_keeps_reading(settings):
    claude = FakeClaude(extraction=saved_extraction("simple_invoice"))
    reference = FakeReference()
    reference.down = True
    with _app(settings, claude, reference) as client:
        invoice_id = _upload(client)
        invoice = _get(client, Invoice, invoice_id)
        assert invoice.status == "extraction_failed"
        assert "http://api:8000" in invoice.status_reason
        assert len(_get(client, LineItem, invoice_id)) == 5
        reference.down = False
        client.post(f"/invoices/{invoice_id}/retry")
        assert _get(client, Invoice, invoice_id).status == "awaiting_confirmation"
    assert sum(1 for c in claude.calls if c["kind"] == "extract") == 1


def test_unreadable_values_explained(settings):
    answer = saved_extraction("simple_invoice")
    answer.lines[0].unit_price = "four hundred"
    answer.header.printed_total = "about 2k"
    with _app(settings, FakeClaude(extraction=answer)) as client:
        [extraction] = _get(client, Extraction, _upload(client))
    warnings = json.loads(extraction.arithmetic_warnings)
    assert "Line 1: the unit price is printed as 'four hundred', but it couldn't be read as a number." in warnings
    assert any(w.startswith("The total is printed as 'about 2k'") for w in warnings)
    assert NO_TOTAL_TEXT not in warnings


NO_TOTAL_TEXT = "No total is printed, so the total was not checked."


def test_retry_timing_starts_at_retry(settings):
    claude = FakeClaude(extraction=ClaudeFailed("Claude timed out", Usage(requests=3)))
    with _app(settings, claude) as client:
        invoice_id = _upload(client)
        with client.app.state.sessions() as s:
            s.get(Invoice, invoice_id).uploaded_at = "2020-01-01T00:00:00.000Z"
            s.commit()
        claude.extraction = saved_extraction("simple_invoice")
        client.post(f"/invoices/{invoice_id}/retry")
        runs = _get(client, Run, invoice_id)
        page = client.get(f"/invoices/{invoice_id}").text
    assert runs[-1].started_at > "2025"
    assert "Reading took 0." in page
