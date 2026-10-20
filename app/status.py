"""The status guard: the only code that changes an invoice's status.

Every move is checked against ALLOWED_MOVES, and every check happens in the same
database statement or transaction as the write it protects.
"""

from contextlib import contextmanager
from enum import StrEnum

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Invoice


class Status(StrEnum):
    EXTRACTING = "extracting"
    EXTRACTION_FAILED = "extraction_failed"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    MATCHING = "matching"
    MATCHING_FAILED = "matching_failed"
    IN_REVIEW = "in_review"
    FINALIZED = "finalized"


ALLOWED_MOVES: dict[Status, set[Status]] = {
    Status.EXTRACTING: {Status.AWAITING_CONFIRMATION, Status.EXTRACTION_FAILED},
    Status.EXTRACTION_FAILED: {Status.EXTRACTING},
    Status.AWAITING_CONFIRMATION: {Status.MATCHING},
    Status.MATCHING: {Status.IN_REVIEW, Status.MATCHING_FAILED},
    Status.MATCHING_FAILED: {Status.MATCHING, Status.AWAITING_CONFIRMATION},
    Status.IN_REVIEW: {Status.AWAITING_CONFIRMATION, Status.FINALIZED},
    Status.FINALIZED: set(),
}

FAILURE_FOR = {Status.EXTRACTING: Status.EXTRACTION_FAILED, Status.MATCHING: Status.MATCHING_FAILED}
RESTART_REASON = "Interrupted by an app restart"


class StatusConflict(Exception):
    """The invoice's status doesn't allow what was asked."""

    def __init__(self, current: Status | None):
        self.current = current
        super().__init__(f"Not allowed while the invoice is {current}")


def _current_status(session: Session, invoice_id: int) -> Status | None:
    value = session.execute(select(Invoice.status).where(Invoice.id == invoice_id)).scalar_one_or_none()
    return Status(value) if value else None


def claim(session: Session, invoice_id: int, expected: set[Status], new: Status, **fields) -> None:
    """Move the invoice to `new`, but only if its status is still one of `expected`."""
    if any(new not in ALLOWED_MOVES[status] for status in expected):
        raise StatusConflict(current=_current_status(session, invoice_id))
    result = session.execute(
        update(Invoice)
        .where(Invoice.id == invoice_id, Invoice.status.in_([s.value for s in expected]))
        .values(status=new.value, status_reason=None, **fields)
    )
    if result.rowcount != 1:
        raise StatusConflict(current=_current_status(session, invoice_id))


@contextmanager
def locked_invoice(session: Session, invoice_id: int, allowed: set[Status]):
    """Hold the write lock on the database while working on an invoice whose status is in `allowed`.

    The opening no-change update both takes SQLite's write lock and checks the status, so the
    status can't change between the check and the caller's writes. Commits on success.
    """
    result = session.execute(
        update(Invoice)
        .where(Invoice.id == invoice_id, Invoice.status.in_([s.value for s in allowed]))
        .values(status=Invoice.status)
    )
    if result.rowcount != 1:
        current = _current_status(session, invoice_id)
        session.rollback()
        raise StatusConflict(current=current)
    try:
        yield session.get(Invoice, invoice_id)
        session.commit()
    except Exception:
        session.rollback()
        raise


def fail(session: Session, invoice_id: int, reason: str) -> None:
    """Move a running step to its failure status with a reason the user will read."""
    for running, failed in FAILURE_FOR.items():
        session.execute(
            update(Invoice)
            .where(Invoice.id == invoice_id, Invoice.status == running.value)
            .values(status=failed.value, status_reason=reason)
        )


def recover_interrupted(session: Session) -> int:
    """At startup, no background work is running, so any running step was cut off."""
    moved = 0
    for running, failed in FAILURE_FOR.items():
        result = session.execute(
            update(Invoice)
            .where(Invoice.status == running.value)
            .values(status=failed.value, status_reason=RESTART_REASON)
        )
        moved += result.rowcount
    return moved
