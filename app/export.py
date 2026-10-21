"""The JSON download for a finalized invoice, built only from the app's own database."""

import json

from app.checks import current_item_id
from app.models import CatalogSnapshotItem, Extraction, Invoice, LineItem, LineMatch


def _item(item: CatalogSnapshotItem | None) -> dict | None:
    if item is None:
        return None
    return {"catalog_item_id": item.catalog_item_id, "item_code": item.item_code, "description": item.description,
            "unit_price": None if item.unit_price is None else str(item.unit_price)}


def _money(value) -> str | None:
    return None if value is None else str(value)


def build_export(session, invoice_id: int) -> dict:
    invoice = session.get(Invoice, invoice_id)
    extraction = session.query(Extraction).filter_by(invoice_id=invoice_id).one()
    header = json.loads(extraction.header)
    names = json.loads(invoice.confirmed_names)
    items = {i.catalog_item_id: i for i in session.query(CatalogSnapshotItem).filter_by(invoice_id=invoice_id)}
    rows = (
        session.query(LineItem, LineMatch)
        .outerjoin(LineMatch, LineMatch.line_item_id == LineItem.id)
        .filter(LineItem.invoice_id == invoice_id)
        .order_by(LineItem.position)
        .all()
    )
    lines = []
    for line, match in rows:
        ai_item = items.get(match.ai_catalog_item_id) if match else None
        override_item = items.get(match.override_catalog_item_id) if match and match.override_kind == "item" else None
        lines.append({
            "position": line.position,
            "description": line.description,
            "quantity": line.quantity,
            "unit_price": _money(line.unit_price),
            "amount": _money(line.amount),
            "ai_suggestion": None if match is None else {
                "item_code": ai_item.item_code if ai_item else None,
                "description": ai_item.description if ai_item else None,
                "confidence": match.ai_confidence,
                "reason": match.ai_reason,
            },
            "override": None if match is None or match.override_kind == "none" else {
                "kind": match.override_kind,
                "item_code": override_item.item_code if override_item else None,
            },
            "final_item": _item(items.get(current_item_id(match))) if match else None,
            "no_match": match is not None and current_item_id(match) is None,
            "price_flag": json.loads(match.price_flag) if match and match.price_flag else None,
        })
    return {
        "invoice_number": header.get("invoice_number"),
        "invoice_date": header.get("invoice_date"),
        "original_filename": invoice.original_filename,
        "sponsor": {"id": invoice.confirmed_sponsor_id, "name": names["sponsor"]},
        "study": {"id": invoice.confirmed_study_id, "name": names["study"]},
        "site": {"id": invoice.confirmed_site_id, "name": names["site"]},
        "printed_total": _money(extraction.printed_total),
        "arithmetic_warnings": json.loads(extraction.arithmetic_warnings),
        "lines": lines,
        "finalize_summary": {**json.loads(invoice.finalize_summary), "finalized_at": invoice.finalized_at},
    }
