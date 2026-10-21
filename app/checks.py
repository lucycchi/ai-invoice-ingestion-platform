"""Checks done in plain code: arithmetic on the extracted numbers, and price flags."""

import json
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.money import format_money

NO_TOTAL = "No total is printed, so the total was not checked."


def _quantity_text(quantity: Decimal) -> str:
    return f"{quantity.normalize():f}"


def arithmetic_warnings(lines, printed_total: Decimal | None, printed_total_text: str | None = None) -> list[str]:
    """Each line's quantity × unit price against its amount, and the amounts against the printed total."""
    warnings = []
    left_out = 0
    total = Decimal("0")
    for position, line in enumerate(lines, start=1):
        if line.amount is None:
            left_out += 1
        else:
            total += line.amount
        if line.quantity is None or line.unit_price is None or line.amount is None:
            warnings.append(f"Line {position}: this line's arithmetic couldn't be checked because a number is missing.")
            continue
        quantity = Decimal(str(line.quantity))
        expected = (quantity * line.unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if expected != line.amount:
            warnings.append(
                f"Line {position}: {_quantity_text(quantity)} × {format_money(line.unit_price)} = "
                f"{format_money(expected)}, but the invoice says {format_money(line.amount)}."
            )
    if printed_total is None and printed_total_text:
        warnings.append(
            f"The total is printed as '{printed_total_text}', but it couldn't be read as a number, "
            "so the total was not checked."
        )
    elif printed_total is None:
        warnings.append(NO_TOTAL)
    elif total != printed_total:
        note = f" ({left_out} line{'s' if left_out != 1 else ''} left out)" if left_out else ""
        warnings.append(
            f"Total: the lines add up to {format_money(total)}, but the invoice says "
            f"{format_money(printed_total)}{note}."
        )
    return warnings


def _cents(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PriceFlag:
    invoice: Decimal
    catalog: Decimal
    diff: Decimal
    pct: Decimal
    text: str

    def to_json(self) -> str:
        return json.dumps({"invoice": str(self.invoice), "catalog": str(self.catalog), "diff": str(self.diff),
                           "pct": str(self.pct), "text": self.text})


def price_flag(unit_price: Decimal | None, catalog_price: Decimal | None) -> PriceFlag | None:
    """A flag when a line's unit price differs from its catalog item's, by even one cent.

    A catalog price of zero or empty means no fixed price, and a missing invoice price is covered by the
    arithmetic check, so neither is flagged.
    """
    if unit_price is None or not catalog_price:
        return None
    # Compared to the cent, so a sub-cent difference can't show as "+$0.00".
    unit_price, catalog_price = _cents(unit_price), _cents(catalog_price)
    if not catalog_price or unit_price == catalog_price:  # under half a cent rounds to no fixed price
        return None
    diff = unit_price - catalog_price
    pct = (diff / catalog_price * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    sign = "+" if diff > 0 else "-"
    pct_text = f"{abs(pct):f}".removesuffix(".0")
    text = (f"Invoice {format_money(unit_price)}, catalog {format_money(catalog_price)}, "
            f"{sign}{format_money(abs(diff))} ({sign}{pct_text}%)")
    return PriceFlag(unit_price, catalog_price, diff, pct, text)


def current_item_id(match) -> int | None:
    """The catalog item a line is matched to now: a person's override if any, else the AI's choice."""
    if match.override_kind == "item":
        return match.override_catalog_item_id
    if match.override_kind == "no_match":
        return None
    return match.ai_catalog_item_id


def refresh_flag(session, match) -> None:
    """Recompute a line's price flag from its current catalog item (none for no match)."""
    from app.models import CatalogSnapshotItem, LineItem

    line = session.get(LineItem, match.line_item_id)
    item_id = current_item_id(match)
    item = None if item_id is None else (
        session.query(CatalogSnapshotItem).filter_by(invoice_id=line.invoice_id, catalog_item_id=item_id).one_or_none()
    )
    flag = price_flag(line.unit_price, item.unit_price if item else None)
    match.price_flag = flag.to_json() if flag else None
