"""Turning printed money and quantities into exact Decimals, and back into text."""

from decimal import Decimal, InvalidOperation


def _clean(text: str) -> str:
    return text.strip().replace("$", "").replace(",", "").replace(" ", "")


def parse_money(text: str | None) -> Decimal | None:
    """"$1,020.00" -> Decimal("1020.00"). Raises ValueError for text that isn't a number."""
    if text is None:
        return None
    try:
        amount = Decimal(_clean(text))
    except InvalidOperation as err:
        raise ValueError(f"not a money amount: {text!r}") from err
    return amount.quantize(Decimal("0.01")) if amount.as_tuple().exponent > -2 else amount


def parse_quantity(text: str | None) -> Decimal | None:
    if text is None:
        return None
    try:
        return Decimal(_clean(text))
    except InvalidOperation as err:
        raise ValueError(f"not a quantity: {text!r}") from err


def format_money(amount: Decimal) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"
