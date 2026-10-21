"""Finalizing with acknowledged open problems, and the JSON download."""

import json
import re

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.clock import now_iso
from app.export import build_export
from app.models import Invoice
from app.status import Status, StatusConflict, claim, locked_invoice
from app.web.review import review_summary
from app.web.routes import conflict_page, templates

router = APIRouter()


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def open_problems(session, invoice_id: int) -> dict:
    """The counts the user must acknowledge before finalizing, and the sentence that states them."""
    summary = review_summary(session, invoice_id)
    counts = {"no_match": summary.no_match, "price_flags": summary.price_flags,
              "arithmetic_warnings": summary.arithmetic_warnings}
    text = ", ".join([
        _plural(summary.no_match, "line with no match", "lines with no match"),
        _plural(summary.price_flags, "price difference", "price differences"),
        _plural(summary.arithmetic_warnings, "arithmetic warning", "arithmetic warnings"),
    ])
    return {**counts, "text": text}


def _summary_page(request: Request, invoice_id: int, problems: dict, status_code: int = 200, changed: bool = False):
    return templates.TemplateResponse(
        request, "finalize.html", {"invoice_id": invoice_id, "problems": problems, "changed": changed},
        status_code=status_code,
    )


@router.get("/invoices/{invoice_id}/finalize", response_class=HTMLResponse)
def finalize_page(request: Request, invoice_id: int):
    with request.app.state.sessions() as s:
        invoice = s.get(Invoice, invoice_id)
        if invoice is None:
            raise HTTPException(404, "There's no invoice with that number.")
        if invoice.status != Status.IN_REVIEW:
            return conflict_page(request, invoice_id, Status(invoice.status))
        problems = open_problems(s, invoice_id)
    return _summary_page(request, invoice_id, problems)


class _CountsChanged(Exception):
    def __init__(self, problems: dict):
        self.problems = problems


@router.post("/invoices/{invoice_id}/finalize")
def finalize(request: Request, invoice_id: int, no_match: int = Form(...), price_flags: int = Form(...),
             arithmetic_warnings: int = Form(...)):
    """Finalize only if the open problems are still the ones the user confirmed (checked under the lock)."""
    shown = {"no_match": no_match, "price_flags": price_flags, "arithmetic_warnings": arithmetic_warnings}
    with request.app.state.sessions() as s:
        try:
            with locked_invoice(s, invoice_id, allowed={Status.IN_REVIEW}):
                problems = open_problems(s, invoice_id)
                if {k: problems[k] for k in shown} != shown:
                    raise _CountsChanged(problems)
                claim(s, invoice_id, expected={Status.IN_REVIEW}, new=Status.FINALIZED,
                      finalize_summary=json.dumps(problems), finalized_at=now_iso())
        except StatusConflict as conflict:
            return conflict_page(request, invoice_id, conflict.current)
        except _CountsChanged as changed:
            return _summary_page(request, invoice_id, changed.problems, status_code=409, changed=True)
    return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)


@router.get("/invoices/{invoice_id}/export.json")
def export(request: Request, invoice_id: int):
    with request.app.state.sessions() as s:
        invoice = s.get(Invoice, invoice_id)
        if invoice is None:
            raise HTTPException(404, "There's no invoice with that number.")
        if invoice.status != Status.FINALIZED:
            return conflict_page(request, invoice_id, Status(invoice.status))
        data = build_export(s, invoice_id)
    return JSONResponse(data, headers={"Content-Disposition": f'attachment; filename="{download_name(data, invoice_id)}"'})


def download_name(data: dict, invoice_id: int) -> str:
    """A safe file name: the invoice number came from an untrusted document, so only letters, digits,
    dot, dash and underscore are kept (no quotes or line breaks can reach the header)."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", data["invoice_number"] or "").strip("-.")[:100]
    return f"{cleaned or f'invoice-{invoice_id}'}.json"
