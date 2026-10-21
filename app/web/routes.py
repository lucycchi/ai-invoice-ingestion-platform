"""The app's pages and form handlers."""

from pathlib import Path

import json

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.clock import now_iso, seconds_between
from app.jobs import start
from app.models import Extraction, Invoice, LineItem, Run
from app.status import Status, StatusConflict, claim
from app.steps.extraction import run_extraction
from app.uploads import MAX_FILE_BYTES, UploadRejected, check_upload, store

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

STATUS_LABELS = {
    Status.EXTRACTING: "Reading",
    Status.EXTRACTION_FAILED: "Reading failed",
    Status.AWAITING_CONFIRMATION: "Waiting for confirmation",
    Status.MATCHING: "Matching line items",
    Status.MATCHING_FAILED: "Matching failed",
    Status.IN_REVIEW: "In review",
    Status.FINALIZED: "Finalized",
}
templates.env.globals["status_label"] = lambda status: STATUS_LABELS[Status(status)]

router = APIRouter()


def _sessions(request: Request):
    return request.app.state.sessions


@router.get("/", response_class=HTMLResponse)
def upload_page(request: Request, message: str | None = None, status_code: int = 200):
    with _sessions(request)() as s:
        invoices = s.scalars(select(Invoice).order_by(Invoice.id.desc())).all()
        numbers = {
            e.invoice_id: json.loads(e.header).get("invoice_number") for e in s.scalars(select(Extraction))
        }
    return templates.TemplateResponse(
        request,
        "upload.html",
        {"invoices": invoices, "numbers": numbers, "message": message},
        status_code=status_code,
    )


CONFLICT_SENTENCES = {
    Status.EXTRACTING: "The invoice is still being read.",
    Status.MATCHING: "Matching line items is already running.",
    Status.FINALIZED: "This invoice is finalized and can't be changed.",
}


def conflict_page(request: Request, invoice_id: int, current: Status | None):
    if current in CONFLICT_SENTENCES:
        sentence = CONFLICT_SENTENCES[current]
    else:
        sentence = f"This invoice is currently: {STATUS_LABELS[current]}." if current else "This invoice doesn't exist."
    return templates.TemplateResponse(
        request, "conflict.html", {"invoice_id": invoice_id, "sentence": sentence}, status_code=409
    )


@router.post("/invoices")
async def upload(request: Request, background_tasks: BackgroundTasks, file: list[UploadFile] = File(...)):
    if len(file) != 1:
        return upload_page(request, message="Please upload one file at a time.", status_code=422)
    file = file[0]
    data = await file.read(MAX_FILE_BYTES + 1)  # never read more than the limit into memory
    try:
        info = check_upload(data, file.filename or "")
    except UploadRejected as rejected:
        return upload_page(request, message=rejected.message, status_code=rejected.status_code)
    settings = request.app.state.settings
    stored = store(data, info.media_type, settings.data_dir)
    with _sessions(request)() as s:
        invoice = Invoice(
            status=Status.EXTRACTING.value,
            original_filename=file.filename or "upload",
            stored_path=stored,
            media_type=info.media_type,
            uploaded_at=now_iso(),
        )
        s.add(invoice)
        s.commit()
        invoice_id = invoice.id
    start(background_tasks, request.app, invoice_id, run_extraction)
    return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)


@router.post("/invoices/{invoice_id}/retry")
def retry(request: Request, invoice_id: int, background_tasks: BackgroundTasks):
    """Rerun whatever failed: reading (and suggestions), or matching for the lines without a result."""
    from app.steps.line_matching import run_matching

    with _sessions(request)() as s:
        invoice = s.get(Invoice, invoice_id)
        failed = Status(invoice.status) if invoice else None
        try:
            if failed == Status.MATCHING_FAILED:
                claim(s, invoice_id, expected={Status.MATCHING_FAILED}, new=Status.MATCHING)
                s.add(Run(invoice_id=invoice_id, step="matching", started_at=now_iso()))
                step = run_matching
            else:
                claim(s, invoice_id, expected={Status.EXTRACTION_FAILED}, new=Status.EXTRACTING)
                step = run_extraction
        except StatusConflict as conflict:
            return conflict_page(request, invoice_id, conflict.current)
        s.commit()
    start(background_tasks, request.app, invoice_id, step)
    return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)


@router.get("/invoices/{invoice_id}/progress", response_class=HTMLResponse)
def progress(request: Request, invoice_id: int):
    with _sessions(request)() as s:
        invoice = s.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(404, "There's no invoice with that number.")
    if invoice.status == Status.MATCHING:
        from app.web.review import matching_progress

        return matching_progress(request, invoice)
    if invoice.status in (Status.IN_REVIEW, Status.MATCHING_FAILED):
        # Matching just ended while this page watched: the review page may report when it's on screen.
        return HTMLResponse("", headers={"HX-Redirect": f"/invoices/{invoice_id}?from=matching"})
    if invoice.status != Status.EXTRACTING:
        return HTMLResponse("", headers={"HX-Refresh": "true"})
    return templates.TemplateResponse(request, "progress.html", {"invoice": invoice})


@router.get("/invoices/{invoice_id}", response_class=HTMLResponse)
def invoice_page(request: Request, invoice_id: int, sponsor_id: int | None = None, study_id: int | None = None,
                 from_: str | None = Query(None, alias="from")):
    with _sessions(request)() as s:
        invoice = s.get(Invoice, invoice_id)
        if invoice is None:
            raise HTTPException(404, "There's no invoice with that number.")
        extraction = s.query(Extraction).filter_by(invoice_id=invoice_id).first()
        lines = s.query(LineItem).filter_by(invoice_id=invoice_id).order_by(LineItem.position).all()
        runs = s.query(Run).filter_by(invoice_id=invoice_id).order_by(Run.id).all()
    reading = next((r for r in reversed(runs) if r.step == "extraction"), None)
    confirming = {}
    if invoice.status in (Status.MATCHING, Status.MATCHING_FAILED, Status.IN_REVIEW, Status.FINALIZED):
        from app.web.review import review_context

        with _sessions(request)() as s:
            confirming = review_context(s, invoice_id)
    if invoice.status == Status.AWAITING_CONFIRMATION:
        from app.web.confirm import confirm_context

        confirming = confirm_context(request, invoice_id, sponsor_id, study_id)
    return templates.TemplateResponse(
        request,
        "invoice.html",
        {
            **confirming,
            "invoice": invoice,
            "header": json.loads(extraction.header) if extraction else None,
            "extraction": extraction,
            "warnings": json.loads(extraction.arithmetic_warnings) if extraction else [],
            "lines": lines,
            "reading_seconds": seconds_between(reading.started_at, reading.stored_at) if reading else None,
            "from_matching": from_ == "matching",
        },
    )
