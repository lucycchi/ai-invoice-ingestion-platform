"""The JSON shapes Claude must answer in (Claude's structured outputs)."""

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator


def _blank_to_none(value):
    """A field Claude left empty means "not printed", which is stored as null, never an empty string."""
    if isinstance(value, str) and not value.strip():
        return None
    return value


Text = Annotated[str | None, BeforeValidator(_blank_to_none)]


class ExtractedHeader(BaseModel):
    invoice_number: Text = None
    invoice_date: Text = None
    site_name: Text = None
    site_street: Text = None
    site_city: Text = None
    site_state: Text = None
    site_postal_code: Text = None
    site_country: Text = None
    pi_name: Text = None
    sponsor_name: Text = None
    study_name: Text = None
    protocol_number: Text = None
    printed_total: Text = None


class ExtractedLine(BaseModel):
    description: Text = None
    quantity: Text = None
    unit_price: Text = None
    amount: Text = None


class ExtractionAnswer(BaseModel):
    is_invoice: bool
    header: ExtractedHeader
    lines: list[ExtractedLine]


class LineResult(BaseModel):
    position: int
    catalog_item_id: int | None
    confidence: Literal["high", "medium", "low"]
    reason: str
    alternatives: list[int]


class GroupAnswer(BaseModel):
    results: list[LineResult]
