from decimal import Decimal
from types import SimpleNamespace

from app.checks import NO_TOTAL, arithmetic_warnings


def _line(quantity, unit_price, amount):
    d = lambda v: None if v is None else Decimal(str(v))
    return SimpleNamespace(quantity=None if quantity is None else float(quantity), unit_price=d(unit_price), amount=d(amount))


SIMPLE = [(1, "400.00", "400.00"), (2, "480.00", "960.00"), (1, "550.00", "550.00"), (1, "95.00", "95.00"), (1, "225.00", "225.00")]


def test_line_and_total_agree():
    assert arithmetic_warnings([_line(2, "480.00", "960.00")], Decimal("960.00")) == []


def test_line_disagrees():
    assert arithmetic_warnings([_line(2, "480.00", "950.00")], Decimal("950.00")) == [
        "Line 1: 2 × $480.00 = $960.00, but the invoice says $950.00."
    ]


def test_simple_invoice_total():
    lines = [_line(*row) for row in SIMPLE]
    assert arithmetic_warnings(lines, Decimal("2230.00")) == []
    assert arithmetic_warnings(lines, Decimal("2200.00")) == [
        "Total: the lines add up to $2,230.00, but the invoice says $2,200.00."
    ]


def test_no_total_printed():
    assert arithmetic_warnings([_line(1, "400.00", "400.00")], None) == [NO_TOTAL]
    assert NO_TOTAL == "No total is printed, so the total was not checked."


def test_missing_number():
    lines = [_line(None, "480.00", "960.00"), _line(1, "400.00", "400.00")]
    assert arithmetic_warnings(lines, Decimal("1360.00")) == [
        "Line 1: this line's arithmetic couldn't be checked because a number is missing."
    ]


def test_missing_number_left_out_of_failing_total():
    lines = [_line(1, "480.00", None), _line(1, "400.00", "400.00")]
    assert arithmetic_warnings(lines, Decimal("900.00")) == [
        "Line 1: this line's arithmetic couldn't be checked because a number is missing.",
        "Total: the lines add up to $400.00, but the invoice says $900.00 (1 line left out).",
    ]


def test_fractional_quantity_rounds_to_the_cent():
    assert arithmetic_warnings([_line(1.5, "33.33", "50.00")], Decimal("50.00")) == []
    assert arithmetic_warnings([_line(0.3, "0.33", "0.10")], Decimal("0.10")) == []


def test_unreadable_total_is_not_called_missing():
    warnings = arithmetic_warnings([_line(1, "400.00", "400.00")], None, printed_total_text="about 2k")
    assert warnings == ["The total is printed as 'about 2k', but it couldn't be read as a number, so the total was not checked."]
