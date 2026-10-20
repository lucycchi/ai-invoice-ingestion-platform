import pytest

from app.db import make_engine, session_factory
from app.models import Base, Invoice
from app.status import ALLOWED_MOVES, Status, StatusConflict, claim, fail, locked_invoice, recover_interrupted


@pytest.fixture
def sessions(tmp_path):
    engine = make_engine(tmp_path / "app.db")
    Base.metadata.create_all(engine)
    return session_factory(engine)


def _invoice(sessions, status: Status) -> int:
    with sessions() as s:
        invoice = Invoice(
            status=status.value,
            original_filename="x.pdf",
            stored_path="x.pdf",
            media_type="application/pdf",
            uploaded_at="2026-10-21T09:00:00.000Z",
        )
        s.add(invoice)
        s.commit()
        return invoice.id


def _status(sessions, invoice_id) -> tuple[str, str | None]:
    with sessions() as s:
        invoice = s.get(Invoice, invoice_id)
        return invoice.status, invoice.status_reason


def test_claim_wins_once(sessions):
    invoice_id = _invoice(sessions, Status.AWAITING_CONFIRMATION)
    with sessions() as s:
        claim(s, invoice_id, expected={Status.AWAITING_CONFIRMATION}, new=Status.MATCHING)
        s.commit()
    with sessions() as s, pytest.raises(StatusConflict) as err:
        claim(s, invoice_id, expected={Status.AWAITING_CONFIRMATION}, new=Status.MATCHING)
    assert err.value.current == Status.MATCHING
    assert _status(sessions, invoice_id)[0] == "matching"


def test_claim_stores_extra_fields(sessions):
    invoice_id = _invoice(sessions, Status.AWAITING_CONFIRMATION)
    with sessions() as s:
        claim(s, invoice_id, expected={Status.AWAITING_CONFIRMATION}, new=Status.MATCHING, confirmed_study_id=3)
        s.commit()
    with sessions() as s:
        assert s.get(Invoice, invoice_id).confirmed_study_id == 3


def test_claim_refuses_move_not_in_table(sessions):
    invoice_id = _invoice(sessions, Status.EXTRACTING)
    with sessions() as s, pytest.raises(StatusConflict):
        claim(s, invoice_id, expected={Status.EXTRACTING}, new=Status.MATCHING)
    assert _status(sessions, invoice_id)[0] == "extracting"


def test_finalized_has_no_moves(sessions):
    assert ALLOWED_MOVES[Status.FINALIZED] == set()
    invoice_id = _invoice(sessions, Status.FINALIZED)
    with sessions() as s, pytest.raises(StatusConflict):
        with locked_invoice(s, invoice_id, allowed={Status.IN_REVIEW}):
            pass


def test_locked_invoice_yields_when_allowed(sessions):
    invoice_id = _invoice(sessions, Status.IN_REVIEW)
    with sessions() as s:
        with locked_invoice(s, invoice_id, allowed={Status.IN_REVIEW}) as invoice:
            invoice.status_reason = "touched"
    assert _status(sessions, invoice_id) == ("in_review", "touched")


def test_recover_interrupted(sessions):
    ids = [_invoice(sessions, st) for st in (Status.EXTRACTING, Status.MATCHING, Status.IN_REVIEW)]
    with sessions() as s:
        moved = recover_interrupted(s)
        s.commit()
    assert moved == 2
    assert _status(sessions, ids[0]) == ("extraction_failed", "Interrupted by an app restart")
    assert _status(sessions, ids[1]) == ("matching_failed", "Interrupted by an app restart")
    assert _status(sessions, ids[2]) == ("in_review", None)


def test_fail_moves_to_matching_failure(sessions):
    invoice_id = _invoice(sessions, Status.MATCHING)
    with sessions() as s:
        fail(s, invoice_id, "boom")
        s.commit()
    assert _status(sessions, invoice_id) == ("matching_failed", "boom")


def test_fail_from_extracting(sessions):
    invoice_id = _invoice(sessions, Status.EXTRACTING)
    with sessions() as s:
        fail(s, invoice_id, "boom")
        s.commit()
    assert _status(sessions, invoice_id) == ("extraction_failed", "boom")
