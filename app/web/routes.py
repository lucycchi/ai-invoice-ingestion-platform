"""The app's pages and form handlers."""

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.clock import now_iso
from app.models import Invoice
from app.status import Status
from app.uploads import UploadRejected, check_upload, store

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
    return templates.TemplateResponse(
        request, "upload.html", {"invoices": invoices, "message": message}, status_code=status_code
    )


@router.post("/invoices")
async def upload(request: Request, file: UploadFile = File(...)):
    data = await file.read()
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
    return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)


@router.get("/invoices/{invoice_id}", response_class=HTMLResponse)
def invoice_page(request: Request, invoice_id: int):
    with _sessions(request)() as s:
        invoice = s.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(404, "There's no invoice with that number.")
    return templates.TemplateResponse(request, "invoice.html", {"invoice": invoice})
