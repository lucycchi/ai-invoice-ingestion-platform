"""Step 1: Claude reads the uploaded file; the reading and its arithmetic checks are stored."""

import json

from app.checks import arithmetic_warnings
from app.clients.claude import ClaudeFailed, Usage
from app.clients.reference_api import ReferenceUnavailable, load_reference_data
from app.clock import now_iso
from app.models import Extraction, Invoice, LineItem, MetadataSuggestion, Run
from app.schemas import ExtractedHeader
from app.money import parse_money, parse_quantity
from app.status import Status, claim, fail
from app.steps.metadata import suggest

NOT_AN_INVOICE = "This file doesn't look like an invoice."


def _safe(parse, text):
    """A number Claude returned that isn't readable is stored as missing, which the arithmetic check reports."""
    try:
        return parse(text)
    except ValueError:
        return None


def run_extraction(app, invoice_id: int) -> None:
    sessions = app.state.sessions
    with sessions() as s:
        invoice = s.get(Invoice, invoice_id)
        already_read = s.query(Extraction).filter_by(invoice_id=invoice_id).first() is not None
        stored_path = app.state.settings.data_dir / "uploads" / invoice.stored_path
        media_type = invoice.media_type
        # The upload or Retry that asked for this reading opened its run with the time of the request.
        open_run = (s.query(Run).filter_by(invoice_id=invoice_id, step="extraction", outcome=None)
                    .order_by(Run.id.desc()).first())
        started_at = open_run.started_at if open_run else now_iso()

    if not already_read:
        data = stored_path.read_bytes()
        try:
            answer, usage = app.state.claude.extract(data, media_type)
        except ClaudeFailed as failed:
            with sessions() as s:
                _record_run(s, invoice_id, started_at, failed.usage, f"failed: {failed.reason}")
                fail(s, invoice_id, f"Couldn't read the invoice: {failed.reason}")
                s.commit()
            return
        with sessions() as s:
            _record_run(s, invoice_id, started_at, usage, "succeeded" if answer.is_invoice else "not an invoice")
            if not answer.is_invoice:
                fail(s, invoice_id, NOT_AN_INVOICE)
                s.commit()
                return
            _store(s, invoice_id, answer, app.state.claude.model)
            s.commit()

    if already_read:  # a Retry after the reading was saved reruns only the suggestions
        with sessions() as s:
            _record_run(s, invoice_id, started_at, Usage(), "succeeded: suggestions only")
            s.commit()
    try:
        data = load_reference_data(app.state.reference)
    except ReferenceUnavailable as down:
        with sessions() as s:
            fail(s, invoice_id, str(down))
            s.commit()
        return
    with sessions() as s:
        header = ExtractedHeader.model_validate_json(s.query(Extraction).filter_by(invoice_id=invoice_id).one().header)
        s.query(MetadataSuggestion).filter_by(invoice_id=invoice_id).delete()
        for suggestion in suggest(header, data):
            s.add(MetadataSuggestion(
                invoice_id=invoice_id,
                field=suggestion.field,
                entity_id=suggestion.entity_id,
                entity_name=suggestion.entity_name,
                confidence=suggestion.confidence,
                reasons=json.dumps(suggestion.reasons),
            ))
        claim(s, invoice_id, expected={Status.EXTRACTING}, new=Status.AWAITING_CONFIRMATION)
        s.commit()


def _unreadable(position: int, what: str, text: str | None, value) -> list[str]:
    if text is not None and value is None:
        return [f"Line {position}: the {what} is printed as '{text}', but it couldn't be read as a number."]
    return []


def _store(s, invoice_id: int, answer, model: str) -> None:
    lines, notes = [], []
    for position, extracted in enumerate(answer.lines, start=1):
        quantity = _safe(parse_quantity, extracted.quantity)
        unit_price = _safe(parse_money, extracted.unit_price)
        amount = _safe(parse_money, extracted.amount)
        notes += _unreadable(position, "quantity", extracted.quantity, quantity)
        notes += _unreadable(position, "unit price", extracted.unit_price, unit_price)
        notes += _unreadable(position, "amount", extracted.amount, amount)
        line = LineItem(
            invoice_id=invoice_id,
            position=position,
            description=extracted.description,
            quantity=None if quantity is None else float(quantity),
            unit_price=unit_price,
            amount=amount,
        )
        lines.append(line)
        s.add(line)
    printed_total = _safe(parse_money, answer.header.printed_total)
    s.add(
        Extraction(
            invoice_id=invoice_id,
            is_invoice=True,
            header=answer.header.model_dump_json(),
            printed_total=printed_total,
            arithmetic_warnings=json.dumps(
                notes + arithmetic_warnings(lines, printed_total, answer.header.printed_total)
            ),
            raw_answer=answer.model_dump_json(),
            model=model,
        )
    )


def _record_run(s, invoice_id: int, started_at: str, usage, outcome: str) -> None:
    """Complete the reading's open run (opened by the upload or Retry), or add one if none is open."""
    run = (s.query(Run).filter_by(invoice_id=invoice_id, step="extraction", outcome=None)
           .order_by(Run.id.desc()).first())
    if run is None:
        run = Run(invoice_id=invoice_id, step="extraction", started_at=started_at)
        s.add(run)
    run.stored_at = now_iso()
    run.claude_requests = usage.requests
    run.input_tokens = usage.input_tokens
    run.output_tokens = usage.output_tokens
    run.cache_read_tokens = usage.cache_read_tokens
    run.outcome = outcome
