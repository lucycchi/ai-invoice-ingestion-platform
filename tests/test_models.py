from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import make_engine, session_factory
from app.models import Base, Extraction, Invoice, LineItem


@pytest.fixture
def session(tmp_path):
    engine = make_engine(tmp_path / "app.db")
    Base.metadata.create_all(engine)
    with session_factory(engine)() as s:
        yield s


def _invoice(session):
    invoice = Invoice(
        status="extracting",
        original_filename="simple-invoice.pdf",
        stored_path="abc123.pdf",
        media_type="application/pdf",
        uploaded_at="2026-10-21T09:00:00.000Z",
    )
    session.add(invoice)
    session.flush()
    return invoice


def test_one_extraction_per_invoice(session):
    invoice = _invoice(session)
    session.add(Extraction(invoice_id=invoice.id, is_invoice=True, header="{}", raw_answer="{}", model="m"))
    session.flush()
    session.add(Extraction(invoice_id=invoice.id, is_invoice=True, header="{}", raw_answer="{}", model="m"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_line_position_unique(session):
    invoice = _invoice(session)
    session.add(LineItem(invoice_id=invoice.id, position=1, description="CBC"))
    session.flush()
    session.add(LineItem(invoice_id=invoice.id, position=1, description="CMP"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_money_round_trip(session):
    invoice = _invoice(session)
    session.add(LineItem(invoice_id=invoice.id, position=1, description="IRB", unit_price=Decimal("550.00")))
    session.commit()
    line = session.query(LineItem).one()
    assert line.unit_price == Decimal("550.00")
    stored = session.execute(text("SELECT unit_price FROM line_items")).scalar_one()
    assert stored == "550.00"


def test_wal_mode(tmp_path):
    engine = make_engine(tmp_path / "app.db")
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar_one() == "wal"


def test_money_never_rounded(session):
    invoice = _invoice(session)
    session.add(LineItem(invoice_id=invoice.id, position=1, unit_price=Decimal("1.005"), amount=Decimal("550")))
    session.commit()
    stored = session.execute(text("SELECT unit_price, amount FROM line_items")).one()
    assert tuple(stored) == ("1.005", "550.00")


def test_money_refuses_float(session):
    invoice = _invoice(session)
    session.add(LineItem(invoice_id=invoice.id, position=1, unit_price=0.1))
    with pytest.raises(Exception) as err:
        session.flush()
    assert "float" in str(err.value).lower()
