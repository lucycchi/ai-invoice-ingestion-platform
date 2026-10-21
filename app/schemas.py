"""The JSON shapes Claude must answer in (Claude's structured outputs)."""

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator


def _blank_to_none(value):
    """A field Claude left empty means "not printed", which is stored as null, never an empty string."""
    if isinstance(value, str) and not value.strip():
        return None
    return value


Text = Annotated[str | None, BeforeValidator(_blank_to_none)]

# Every field below is required and nullable (no defaults): Claude's structured outputs reject a schema
# with many optional fields ("Schema is too complex"), and the spec wants null, never a missing field.


class ExtractedHeader(BaseModel):
    @classmethod
    def blank(cls, **fields) -> "ExtractedHeader":
        """A header with every field null except those given (for building test examples)."""
        return cls(**({name: None for name in cls.model_fields} | fields))

    invoice_number: Text
    invoice_date: Text
    site_name: Text
    site_street: Text
    site_city: Text
    site_state: Text
    site_postal_code: Text
    site_country: Text
    pi_name: Text
    sponsor_name: Text
    study_name: Text
    protocol_number: Text
    printed_total: Text


class ExtractedLine(BaseModel):
    description: Text
    quantity: Text
    unit_price: Text
    amount: Text


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
