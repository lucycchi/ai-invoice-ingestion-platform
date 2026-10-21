"""The confirmation screen and the gate: the only way into line matching."""

import json
from html import escape

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from app.clients.reference_api import ReferenceNotFound, ReferenceUnavailable, load_reference_data
from app.clock import now_iso
from app.models import CatalogSnapshotItem, Extraction, Invoice, LineItem, LineMatch, MetadataSuggestion, Run
from app.status import Status, StatusConflict, claim, locked_invoice
from app.steps.metadata import site_link_warning
from app.web.routes import conflict_page, templates

router = APIRouter()
CHANGEABLE = {Status.AWAITING_CONFIRMATION, Status.MATCHING_FAILED, Status.IN_REVIEW}
# An invoice whose sponsor, study and site are currently confirmed.
CONFIRMED = {Status.MATCHING, Status.MATCHING_FAILED, Status.IN_REVIEW, Status.FINALIZED}


def _reference(request: Request):
    return request.app.state.reference


def confirm_context(request: Request, invoice_id: int, sponsor_id: int | None, study_id: int | None) -> dict:
    """Everything the confirmation section of the invoice page needs."""
    with request.app.state.sessions() as s:
        suggestions = {
            m.field: {"id": m.entity_id, "name": m.entity_name, "confidence": m.confidence, "reasons": json.loads(m.reasons)}
            for m in s.query(MetadataSuggestion).filter_by(invoice_id=invoice_id)
        }
    try:
        data = load_reference_data(_reference(request))
    except ReferenceUnavailable as down:
        return {"suggestions": suggestions, "reference_error": str(down)}
    chosen_sponsor = sponsor_id or (suggestions.get("sponsor") or {}).get("id")
    chosen_study = study_id or (suggestions.get("study") or {}).get("id")
    offer = None
    study_record = next((st for st in data.studies if st["id"] == chosen_study), None)
    if study_record and study_record["sponsor_id"] != chosen_sponsor:
        owner = next(sp for sp in data.sponsors if sp["id"] == study_record["sponsor_id"])
        offer = {"sponsor": owner, "study": study_record}
    return {
        "suggestions": suggestions,
        "sponsors": data.sponsors,
        "studies": [st for st in data.studies if st["sponsor_id"] == chosen_sponsor],
        "sites": data.sites,
        "chosen": {"sponsor": chosen_sponsor, "study": chosen_study, "site": (suggestions.get("site") or {}).get("id")},
        "offer": offer,
        "choice_warnings": _warnings(request, invoice_id, chosen_study, (suggestions.get("site") or {}).get("id"), data),
    }


def _warnings(request: Request, invoice_id: int, study_id, site_id, data) -> list[str]:
    warnings = []
    if study_id and site_id:
        link = site_link_warning(study_id, site_id, data)
        if link:
            warnings.append(link)
    if site_id:
        with request.app.state.sessions() as s:
            mine = s.query(Extraction).filter_by(invoice_id=invoice_id).first()
            number = json.loads(mine.header).get("invoice_number") if mine else None
            if number:
                earlier = select(Invoice).where(
                    Invoice.id < invoice_id,
                    Invoice.confirmed_site_id == site_id,
                    Invoice.status.in_([status.value for status in CONFIRMED]),
                )
                for other in s.scalars(earlier):
                    theirs = s.query(Extraction).filter_by(invoice_id=other.id).first()
                    if theirs and json.loads(theirs.header).get("invoice_number") == number:
                        warnings.append(
                            f"An earlier upload, {other.original_filename}, has the same invoice number "
                            f"{number} and the same site. This may be a duplicate."
                        )
    return warnings


@router.get("/invoices/{invoice_id}/studies", response_class=HTMLResponse)
def studies(request: Request, invoice_id: int, sponsor_id: int, study_id: int | None = None):
    try:
        choices = _reference(request).list_studies(sponsor_id=sponsor_id)
    except ReferenceUnavailable as down:
        return HTMLResponse(f'<option value="">{escape(str(down))}</option>', status_code=503)
    return templates.TemplateResponse(request, "_study_options.html", {"studies": choices, "chosen": study_id})


@router.get("/invoices/{invoice_id}/warnings", response_class=HTMLResponse)
def warnings(request: Request, invoice_id: int, sponsor_id: int | None = None, study_id: int | None = None,
             site_id: int | None = None):
    try:
        found = _warnings(request, invoice_id, study_id, site_id, load_reference_data(_reference(request)))
    except ReferenceUnavailable as down:
        found = [str(down)]
    return templates.TemplateResponse(request, "_warnings.html", {"warnings": found})


def _refuse(request: Request, invoice_id: int, message: str, status_code: int):
    return templates.TemplateResponse(
        request, "refused.html", {"invoice_id": invoice_id, "message": message}, status_code=status_code
    )


@router.post("/invoices/{invoice_id}/confirm")
def confirm(request: Request, invoice_id: int, background_tasks: BackgroundTasks,
            sponsor_id: int = Form(...), study_id: int = Form(...), site_id: int = Form(...)):
    received_at = now_iso()
    # The status comes first: a wrong status is a 409 whatever the choices are. The claim below
    # re-checks it atomically.
    with request.app.state.sessions() as s:
        invoice = s.get(Invoice, invoice_id)
        current = Status(invoice.status) if invoice else None
    if current != Status.AWAITING_CONFIRMATION:
        return conflict_page(request, invoice_id, current)
    reference = _reference(request)
    try:
        sponsor = reference.get_sponsor(sponsor_id)
        study = reference.get_study(study_id)
        site = reference.get_site(site_id)
        owner = reference.get_sponsor(study["sponsor_id"]) if study["sponsor_id"] != sponsor["id"] else None
    except ReferenceNotFound as missing:
        return _refuse(request, invoice_id, str(missing), 422)
    except ReferenceUnavailable as down:
        return _refuse(request, invoice_id, f"{down}. Press Confirm to try again.", 503)
    if owner:
        return _refuse(request, invoice_id, f"{study['name']} belongs to {owner['name']}, not {sponsor['name']}.", 422)

    names = {"sponsor": sponsor["name"], "study": study["name"], "site": site["name"]}
    with request.app.state.sessions() as s:
        try:
            claim(s, invoice_id, expected={Status.AWAITING_CONFIRMATION}, new=Status.MATCHING,
                  confirmed_sponsor_id=sponsor_id, confirmed_study_id=study_id, confirmed_site_id=site_id,
                  confirmed_names=json.dumps(names))
        except StatusConflict as conflict:
            return conflict_page(request, invoice_id, conflict.current)
        s.add(Run(invoice_id=invoice_id, step="matching", started_at=received_at))
        s.commit()
    start_matching(background_tasks, request.app, invoice_id)
    # The page after Confirm follows matching live, so it may report when every result is on screen,
    # even if matching finishes before the page has loaded.
    return RedirectResponse(f"/invoices/{invoice_id}?from=matching", status_code=303)


def start_matching(background_tasks: BackgroundTasks, app, invoice_id: int) -> None:
    from app.jobs import start
    from app.steps.line_matching import run_matching

    start(background_tasks, app, invoice_id, run_matching)


def _match_counts(s, invoice_id: int) -> tuple[int, int]:
    matches = (
        s.query(LineMatch).join(LineItem, LineMatch.line_item_id == LineItem.id).filter(LineItem.invoice_id == invoice_id)
    )
    return matches.count(), matches.filter(LineMatch.override_kind != "none").count()


@router.get("/invoices/{invoice_id}/change-metadata", response_class=HTMLResponse)
def change_metadata_page(request: Request, invoice_id: int):
    with request.app.state.sessions() as s:
        invoice = s.get(Invoice, invoice_id)
        if invoice is None:
            raise HTTPException(404, "There's no invoice with that number.")
        if Status(invoice.status) not in CHANGEABLE:
            return conflict_page(request, invoice_id, Status(invoice.status))
        matches, overrides = _match_counts(s, invoice_id)
    return templates.TemplateResponse(
        request, "change_metadata.html", {"invoice_id": invoice_id, "matches": matches, "overrides": overrides}
    )


@router.post("/invoices/{invoice_id}/change-metadata")
def change_metadata(request: Request, invoice_id: int):
    with request.app.state.sessions() as s:
        try:
            with locked_invoice(s, invoice_id, allowed=CHANGEABLE) as invoice:
                line_ids = select(LineItem.id).where(LineItem.invoice_id == invoice_id)
                s.query(LineMatch).filter(LineMatch.line_item_id.in_(line_ids)).delete(synchronize_session=False)
                s.query(CatalogSnapshotItem).filter_by(invoice_id=invoice_id).delete()
                invoice.confirmed_sponsor_id = invoice.confirmed_study_id = invoice.confirmed_site_id = None
                invoice.confirmed_names = None
                if invoice.status != Status.AWAITING_CONFIRMATION:
                    claim(s, invoice_id, expected={Status(invoice.status)}, new=Status.AWAITING_CONFIRMATION)
        except StatusConflict as conflict:
            return conflict_page(request, invoice_id, conflict.current)
    return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)
