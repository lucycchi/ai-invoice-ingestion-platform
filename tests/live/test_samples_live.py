"""Live tests: the real Claude and the running reference API, on the four sample invoices.

They cost money and take a few minutes, so they run only when asked for:
    .venv/bin/pytest -m live -v -s
They need ANTHROPIC_API_KEY in .env and the reference API running at http://localhost:8000.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.checks import current_item_id
from app.clients.reference_api import ReferenceClient
from app.config import MissingSetting, get_settings
from app.main import create_app
from app.models import CatalogSnapshotItem, Extraction, Invoice, LineItem, LineMatch, MetadataSuggestion

pytestmark = pytest.mark.live

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = json.loads((ROOT / "tests" / "fixtures" / "expected_results.json").read_text())
GENERATED = ROOT / "sample-invoices" / "generated"
SCORE_BAR = 45  # of the 47 lines that have an expected catalog item


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    try:
        settings = get_settings(env_file=str(ROOT / ".env"))
    except MissingSetting:
        # Asking for the live tests without a key must not look like a pass.
        pytest.fail("The live tests need ANTHROPIC_API_KEY in .env (copy .env.example to .env and add your key).")
    settings.data_dir = tmp_path_factory.mktemp("live-data")
    settings.allowed_hosts = ["localhost", "127.0.0.1", "testserver"]
    app = create_app(settings, reference=ReferenceClient("http://localhost:8000"))
    with TestClient(app, follow_redirects=False) as c:
        yield c


def upload(client, path: Path) -> int:
    response = client.post("/invoices", files={"file": (path.name, path.read_bytes())})
    assert response.status_code == 303, response.text
    return int(response.headers["location"].rsplit("/", 1)[1])


def status(client, invoice_id) -> tuple[str, str | None]:
    with client.app.state.sessions() as s:
        invoice = s.get(Invoice, invoice_id)
        return invoice.status, invoice.status_reason


def suggestions(client, invoice_id) -> dict:
    with client.app.state.sessions() as s:
        return {m.field: (m.entity_id, m.confidence) for m in s.query(MetadataSuggestion).filter_by(invoice_id=invoice_id)}


def reading(client, invoice_id) -> tuple[Decimal | None, list[LineItem]]:
    with client.app.state.sessions() as s:
        extraction = s.query(Extraction).filter_by(invoice_id=invoice_id).one()
        lines = s.query(LineItem).filter_by(invoice_id=invoice_id).order_by(LineItem.position).all()
        return extraction.printed_total, lines


def results(client, invoice_id) -> dict[int, tuple[str | None, str | None]]:
    """Position -> (current item code or None for no match, price flag text)."""
    with client.app.state.sessions() as s:
        codes = {i.catalog_item_id: i.item_code for i in s.query(CatalogSnapshotItem).filter_by(invoice_id=invoice_id)}
        rows = (s.query(LineItem.position, LineMatch).join(LineMatch, LineMatch.line_item_id == LineItem.id)
                .filter(LineItem.invoice_id == invoice_id).all())
        return {p: (codes.get(current_item_id(m)), json.loads(m.price_flag)["text"] if m.price_flag else None)
                for p, m in rows}


def run_sample(client, path: Path, expected: dict) -> tuple[int, dict]:
    invoice_id = upload(client, path)
    assert status(client, invoice_id)[0] == "awaiting_confirmation", status(client, invoice_id)
    ids = {field: expected[field]["id"] for field in ("sponsor", "study", "site")}
    response = client.post(f"/invoices/{invoice_id}/confirm",
                           data={"sponsor_id": ids["sponsor"], "study_id": ids["study"], "site_id": ids["site"]})
    assert response.status_code == 303
    assert status(client, invoice_id)[0] == "in_review", status(client, invoice_id)
    return invoice_id, results(client, invoice_id)


def test_pdf_samples(client):
    matched = misses = 0
    flags = []
    for name, expected in EXPECTED.items():
        invoice_id, got = run_sample(client, ROOT / "sample-invoices" / expected["file"], expected)
        found = suggestions(client, invoice_id)
        for field in ("sponsor", "study", "site"):
            entity_id, level = found[field]
            assert entity_id == expected[field]["id"], (name, field, found[field])
            assert level in expected[field]["levels"], (name, field, level)
        total, lines = reading(client, invoice_id)
        assert total == Decimal(expected["total"]), (name, total)
        assert len(lines) == len(expected["lines"]), (name, len(lines))
        for line, want in zip(lines, expected["lines"]):
            assert line.description == want["description"], (name, line.position, line.description)
            assert Decimal(str(line.quantity)) == Decimal(want["quantity"]), (name, line.position)
            assert line.unit_price == Decimal(want["unit_price"]), (name, line.position)
            assert line.amount == Decimal(want["quantity"]) * Decimal(want["unit_price"]), (name, line.position)
            code, flag = got[line.position]
            if want["item_code"] is None:
                assert code is None, (name, line.position, "expected no match", code)
                continue
            if code == want["item_code"]:
                matched += 1
            else:
                misses += 1
                print(f"MISS {name} line {line.position} ({line.description}): expected {want['item_code']}, got {code}")
            if flag:
                flags.append((name, line.position, flag))
    print(f"SCORE {matched}/47")
    assert sorted(flags) == [
        ("large_invoice", 20, "Invoice $475.00, catalog $450.00, +$25.00 (+5.6%)"),
        ("medium_invoice", 11, "Invoice $550.00, catalog $500.00, +$50.00 (+10%)"),
    ]
    assert matched + misses == 47 and matched >= SCORE_BAR


def test_png_matches_pdf(client):
    expected = EXPECTED["simple_invoice"]
    png_id, png = run_sample(client, GENERATED / "simple-invoice.png", expected)
    pdf_id, pdf = run_sample(client, ROOT / "sample-invoices" / "simple-invoice.pdf", expected)
    assert suggestions(client, png_id) == suggestions(client, pdf_id)
    assert png == pdf


def test_photo_recorded(client):
    """The photo-like copy's results are printed for the README, not asserted."""
    invoice_id = upload(client, GENERATED / "simple-invoice-photo.jpg")
    state, reason = status(client, invoice_id)
    print(f"PHOTO status: {state} {reason or ''}")
    assert state == "awaiting_confirmation", "the photo-like copy should at least be read"
    if state == "awaiting_confirmation":
        total, lines = reading(client, invoice_id)
        print(f"PHOTO total {total}, {len(lines)} lines: " + "; ".join(
            f"{l.description} {l.quantity:g} x {l.unit_price}" for l in lines))
        print(f"PHOTO suggestions: {suggestions(client, invoice_id)}")


def test_hostile_invoice(client):
    medium = EXPECTED["medium_invoice"]
    invoice_id = upload(client, GENERATED / "hostile-invoice.pdf")
    assert status(client, invoice_id)[0] == "awaiting_confirmation"  # nothing confirmed without the user
    client.post(f"/invoices/{invoice_id}/confirm", data={"sponsor_id": 1, "study_id": 1, "site_id": 2})
    assert status(client, invoice_id)[0] == "in_review"
    got = results(client, invoice_id)
    for want in medium["lines"]:
        assert got[want["position"]][0] == want["item_code"], (want["position"], got[want["position"]])
    print(f"HOSTILE line 12 matched to: {got[12][0]}")
    # Price flags and arithmetic are decided in code, so the hostile line can't change them.
    assert [(p, flag) for p, (_, flag) in got.items() if flag and p != 12] == [
        (11, "Invoice $550.00, catalog $500.00, +$50.00 (+10%)")]
    with client.app.state.sessions() as s:
        warnings = json.loads(s.query(Extraction).filter_by(invoice_id=invoice_id).one().arithmetic_warnings)
    assert warnings == []
    with client.app.state.sessions() as s:
        snapshot = {i.catalog_item_id for i in s.query(CatalogSnapshotItem).filter_by(invoice_id=invoice_id)}
        stored = {m.ai_catalog_item_id for m in s.query(LineMatch).join(LineItem, LineMatch.line_item_id == LineItem.id)
                  .filter(LineItem.invoice_id == invoice_id)} - {None}
    assert stored <= snapshot
