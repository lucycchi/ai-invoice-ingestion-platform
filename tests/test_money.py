from decimal import Decimal

import pytest

from app.money import format_money, parse_money, parse_quantity


@pytest.mark.parametrize(
    "text, expected",
    [("$1,020.00", "1020.00"), ("1,020", "1020.00"), ("475", "475.00"), ("$0.50", "0.50"), (" $42.00 ", "42.00")],
)
def test_parse_money(text, expected):
    assert parse_money(text) == Decimal(expected)


def test_parse_money_none():
    assert parse_money(None) is None


def test_parse_money_garbage():
    with pytest.raises(ValueError):
        parse_money("abc")


def test_parse_quantity():
    assert parse_quantity("12") == Decimal("12")
    assert parse_quantity("1.5") == Decimal("1.5")
    assert parse_quantity(None) is None


def test_format_money():
    assert format_money(Decimal("2230")) == "$2,230.00"
    assert format_money(Decimal("-25")) == "-$25.00"


@pytest.mark.parametrize(
    "text, expected",
    [("USD 2,230.00", "2230.00"), ("€475", "475.00"), ("£42.50", "42.50"), ("(50.00)", "-50.00"), ("2230.00 USD", "2230.00")],
)
def test_parse_money_currency_and_accounting_forms(text, expected):
    assert parse_money(text) == Decimal(expected)


@pytest.mark.parametrize("text", ["NaN", "Infinity", "-inf", "sNaN"])
def test_parse_money_rejects_non_numbers(text):
    with pytest.raises(ValueError):
        parse_money(text)
    with pytest.raises(ValueError):
        parse_quantity(text)
