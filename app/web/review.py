"""The review screen: matching progress, the reviewed lines, overrides and the on-screen timing report."""

import json
from dataclasses import dataclass

from fastapi import APIRouter, Form, HTTPException, Request
from sqlalchemy import update
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.checks import current_item_id, refresh_flag
from app.clock import now_iso, seconds_between
from app.models import CatalogSnapshotItem, Extraction, Invoice, LineItem, LineMatch, Run
from app.status import Status, StatusConflict, locked_invoice
from app.web.routes import conflict_page, templates

router = APIRouter()
REVIEWABLE = {Status.MATCHING, Status.MATCHING_FAILED, Status.IN_REVIEW, Status.FINALIZED}


@dataclass
class ReviewSummary:
    matched: int
    no_match: int
    price_flags: int
    overridden: int
    arithmetic_warnings: int


def _matches(session, invoice_id: int) -> list[tuple[LineItem, LineMatch | None]]:
    rows = (
        session.query(LineItem, LineMatch)
        .outerjoin(LineMatch, LineMatch.line_item_id == LineItem.id)
        .filter(LineItem.invoice_id == invoice_id)
        .order_by(LineItem.position)
        .all()
    )
    return [(line, match) for line, match in rows]


def review_summary(session, invoice_id: int) -> ReviewSummary:
    pairs = [(line, match) for line, match in _matches(session, invoice_id) if match is not None]
    extraction = session.query(Extraction).filter_by(invoice_id=invoice_id).first()
    return ReviewSummary(
        matched=sum(1 for _, m in pairs if current_item_id(m) is not None),
        no_match=sum(1 for _, m in pairs if current_item_id(m) is None),
        price_flags=sum(1 for _, m in pairs if m.price_flag),
        overridden=sum(1 for _, m in pairs if m.override_kind != "none"),
        arithmetic_warnings=len(json.loads(extraction.arithmetic_warnings)) if extraction else 0,
    )


def review_context(session, invoice_id: int) -> dict:
    """Rows and summary for the review screen (also used while matching runs)."""
    items = {i.catalog_item_id: i for i in session.query(CatalogSnapshotItem).filter_by(invoice_id=invoice_id)}
    rows = []
    for line, match in _matches(session, invoice_id):
        row = {"line": line, "match": match}
        if match is not None:
            row["current"] = items.get(current_item_id(match))
            row["ai_item"] = items.get(match.ai_catalog_item_id)
            row["alternatives"] = [items[a] for a in json.loads(match.ai_alternatives) if a in items]
            row["flag"] = json.loads(match.price_flag)["text"] if match.price_flag else None
        rows.append(row)
    run = session.query(Run).filter_by(invoice_id=invoice_id, step="matching").order_by(Run.id.desc()).first()
    return {
        "rows": rows,
        "done": sum(1 for r in rows if r["match"] is not None),
        "summary": review_summary(session, invoice_id),
        "matching_run": run,
        "stored_seconds": seconds_between(run.started_at, run.stored_at) if run else None,
        "shown_seconds": seconds_between(run.started_at, run.shown_at) if run else None,
    }


def matching_progress(request: Request, invoice: Invoice):
    with request.app.state.sessions() as s:
        context = review_context(s, invoice.id)
    return templates.TemplateResponse(request, "_matching_progress.html", {"invoice": invoice, **context})


@router.get("/invoices/{invoice_id}/catalog", response_class=HTMLResponse)
def catalog_search(request: Request, invoice_id: int, q: str = ""):
    """Options for a line's picker: catalog items whose code or description contains the search text."""
    wanted = q.strip().lower()
    with request.app.state.sessions() as s:
        items = s.query(CatalogSnapshotItem).filter_by(invoice_id=invoice_id).order_by(CatalogSnapshotItem.item_code).all()
    found = [i for i in items if wanted in i.item_code.lower() or wanted in i.description.lower()]
    return templates.TemplateResponse(request, "_catalog_options.html", {"items": found})


class _Refused(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message


def _change_line(request: Request, invoice_id: int, line_id: int, change) -> Response:
    """Apply `change(session, match)` to one line, checked inside the invoice's write lock."""
    with request.app.state.sessions() as s:
        try:
            with locked_invoice(s, invoice_id, allowed={Status.IN_REVIEW}):
                line = s.get(LineItem, line_id)
                if line is None or line.invoice_id != invoice_id:
                    raise _Refused(404, "That line isn't on this invoice.")
                match = s.query(LineMatch).filter_by(line_item_id=line_id).one_or_none()
                if match is None:
                    raise _Refused(409, "This line has no match yet.")
                change(s, match)
                refresh_flag(s, match)
        except StatusConflict as conflict:
            return conflict_page(request, invoice_id, conflict.current)
        except _Refused as refused:
            if refused.status_code == 404:
                raise HTTPException(404, refused.message)
            return templates.TemplateResponse(
                request, "refused.html", {"invoice_id": invoice_id, "message": refused.message},
                status_code=refused.status_code,
            )
    return RedirectResponse(f"/invoices/{invoice_id}#line-{line.position}", status_code=303)


@router.post("/invoices/{invoice_id}/lines/{line_id}/override")
def override(request: Request, invoice_id: int, line_id: int, catalog_item_id: str = Form(...)):
    def change(s, match):
        if catalog_item_id == "none":
            item_id = None
        else:
            try:
                item_id = int(catalog_item_id)
            except ValueError:
                raise _Refused(422, "Choose a catalog item or No match.")
            in_catalog = s.query(CatalogSnapshotItem).filter_by(invoice_id=invoice_id, catalog_item_id=item_id).count()
            if not in_catalog:
                raise _Refused(422, "That item isn't in this invoice's catalog.")
        if item_id == match.ai_catalog_item_id:
            # Choosing what the AI suggested isn't an override: the line goes back to the AI's suggestion.
            match.override_kind, match.override_catalog_item_id = "none", None
        elif item_id is None:
            match.override_kind, match.override_catalog_item_id = "no_match", None
        else:
            match.override_kind, match.override_catalog_item_id = "item", item_id

    return _change_line(request, invoice_id, line_id, change)


@router.post("/invoices/{invoice_id}/lines/{line_id}/undo")
def undo(request: Request, invoice_id: int, line_id: int):
    def change(s, match):
        match.override_kind, match.override_catalog_item_id = "none", None

    return _change_line(request, invoice_id, line_id, change)


@router.post("/invoices/{invoice_id}/shown")
def shown(request: Request, invoice_id: int):
    """The page that followed matching live reports it has shown every result.

    Recorded once, only after matching finished; the write only succeeds while no time is recorded yet,
    so two reports arriving together can't overwrite the first. Answers with the updated times.
    """
    with request.app.state.sessions() as s:
        invoice = s.get(Invoice, invoice_id)
        run = s.query(Run).filter_by(invoice_id=invoice_id, step="matching").order_by(Run.id.desc()).first()
        finished = invoice is not None and invoice.status in (Status.IN_REVIEW, Status.FINALIZED)
        if not finished or run is None or run.stored_at is None:
            return Response(status_code=409)
        s.execute(update(Run).where(Run.id == run.id, Run.shown_at.is_(None)).values(shown_at=now_iso()))
        s.commit()
        s.refresh(run)
    return templates.TemplateResponse(request, "_matching_time.html", {
        "stored_seconds": seconds_between(run.started_at, run.stored_at),
        "shown_seconds": seconds_between(run.started_at, run.shown_at),
    })
