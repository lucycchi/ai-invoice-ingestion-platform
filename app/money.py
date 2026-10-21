"""Turning printed money and quantities into exact Decimals, and back into text."""

import re
from decimal import Decimal, InvalidOperation

CURRENCY = re.compile(r"\b(USD|US\$|EUR|GBP|CAD|AUD)\b|[$€£]", re.IGNORECASE)


def _clean(text: str) -> str:
    """Drop currency codes, symbols, thousands separators and spaces; "(50.00)" means -50.00."""
    cleaned = CURRENCY.sub("", text).replace(",", "").replace(" ", "").strip()
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    return cleaned


def _number(text: str, what: str) -> Decimal:
    try:
        value = Decimal(_clean(text))
    except InvalidOperation as err:
        raise ValueError(f"not {what}: {text!r}") from err
    if not value.is_finite():
        raise ValueError(f"not {what}: {text!r}")
    return value


def parse_money(text: str | None) -> Decimal | None:
    """"$1,020.00" -> Decimal("1020.00"). Raises ValueError for text that isn't a number."""
    if text is None:
        return None
    amount = _number(text, "a money amount")
    return amount.quantize(Decimal("0.01")) if amount.as_tuple().exponent > -2 else amount


def parse_quantity(text: str | None) -> Decimal | None:
    if text is None:
        return None
    return _number(text, "a quantity")


def format_money(amount: Decimal) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"
