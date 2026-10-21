"""Checks done in plain code: arithmetic on the extracted numbers."""

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
