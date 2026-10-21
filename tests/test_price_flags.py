import json
from decimal import Decimal as D

import pytest

from app.checks import price_flag, refresh_flag
from app.models import CatalogSnapshotItem, LineItem, LineMatch
from tests.test_line_matching import Env, env, expected_answer  # noqa: F401  (env is a fixture)


@pytest.mark.parametrize("invoice, catalog, text", [
    ("550.00", "500.00", "Invoice $550.00, catalog $500.00, +$50.00 (+10%)"),
    ("475.00", "450.00", "Invoice $475.00, catalog $450.00, +$25.00 (+5.6%)"),
    ("450.00", "475.00", "Invoice $450.00, catalog $475.00, -$25.00 (-5.3%)"),
])
def test_flag_text(invoice, catalog, text):
    assert price_flag(D(invoice), D(catalog)).text == text


def test_flag_values():
    flag = price_flag(D("550.00"), D("500.00"))
    assert (flag.invoice, flag.catalog, flag.diff, flag.pct) == (D("550.00"), D("500.00"), D("50.00"), D("10.0"))


def test_same_price_no_flag():
    assert price_flag(D("42.00"), D("42.00")) is None


def test_one_cent_counts():
    assert price_flag(D("500.01"), D("500.00")).diff == D("0.01")


def test_no_fixed_price_never_flagged():
    assert price_flag(D("125.00"), D("0.00")) is None
    assert price_flag(D("10.00"), None) is None


def test_missing_invoice_price_not_flagged():
    assert price_flag(None, D("10.00")) is None


def _large_line(env, invoice_id, position):
    with env.client.app.state.sessions() as s:
        line = s.query(LineItem).filter_by(invoice_id=invoice_id, position=position).one()
        match = s.query(LineMatch).filter_by(line_item_id=line.id).one()
        return line, match


def _snapshot_id(env, invoice_id, code):
    with env.client.app.state.sessions() as s:
        return s.query(CatalogSnapshotItem).filter_by(invoice_id=invoice_id, item_code=code).one().catalog_item_id


def test_flags_saved_with_matches(env):
    invoice_id = env.run()
    _, ct = _large_line(env, invoice_id, 20)
    assert json.loads(ct.price_flag)["text"] == "Invoice $475.00, catalog $450.00, +$25.00 (+5.6%)"
    flagged = [m for m in env.matches(invoice_id).values() if m.price_flag]
    assert len(flagged) == 1


def test_refresh_on_override(env):
    invoice_id = env.run()
    with env.client.app.state.sessions() as s:
        line = s.query(LineItem).filter_by(invoice_id=invoice_id, position=20).one()
        match = s.query(LineMatch).filter_by(line_item_id=line.id).one()
        match.override_kind, match.override_catalog_item_id = "item", _snapshot_id(env, invoice_id, "IMG-MRI")
        refresh_flag(s, match)
        assert json.loads(match.price_flag)["text"] == "Invoice $475.00, catalog $650.00, -$175.00 (-26.9%)"
        match.override_kind, match.override_catalog_item_id = "no_match", None
        refresh_flag(s, match)
        assert match.price_flag is None


def test_medium_invoice_flags(env):
    env.claude.match = expected_answer("medium_invoice")
    invoice_id = env.run("medium_invoice")
    flagged = {p: json.loads(m.price_flag) for p, m in env.matches(invoice_id).items() if m.price_flag}
    assert list(flagged) == [11]
    assert flagged[11]["text"] == "Invoice $550.00, catalog $500.00, +$50.00 (+10%)"
