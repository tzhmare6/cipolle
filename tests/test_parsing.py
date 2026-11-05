from datetime import date

import pytest

from cipolle.parsing import format_amount, natural_key, parse_amount, parse_date, plain_amount


@pytest.mark.parametrize(
    "text, cents",
    [
        ("1234.50", 123450),
        ("1'234.50", 123450),
        ("1 234,5", 123450),
        ("12", 1200),
        ("-0.05", -5),
        (".5", 50),
        ("0.07", 7),
        ("1.10", 110),
        ("", None),
        ("  ", None),
    ],
)
def test_parse_amount(text, cents):
    assert parse_amount(text) == cents


@pytest.mark.parametrize("text", ["abc", "1.234", "1.2.3", "--4", "1e5"])
def test_parse_amount_rejects(text):
    with pytest.raises(ValueError):
        parse_amount(text)


@pytest.mark.parametrize(
    "cents, text",
    [(123450, "1'234.50"), (-5, "-0.05"), (0, "0.00"), (100000000, "1'000'000.00"), (None, "")],
)
def test_format_amount(cents, text):
    assert format_amount(cents) == text


def test_plain_amount_has_no_separator():
    assert plain_amount(123450) == "1234.50"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("31.12.2026", date(2026, 12, 31)),
        ("31.12.26", date(2026, 12, 31)),
        ("31.12", date(2026, 12, 31)),
        ("31.12.", date(2026, 12, 31)),
        ("3112", date(2026, 12, 31)),
        ("311225", date(2025, 12, 31)),
        ("1.2", date(2026, 2, 1)),
        ("2026-03-04", date(2026, 3, 4)),
        ("", None),
    ],
)
def test_parse_date(text, expected):
    assert parse_date(text, 2026) == expected


@pytest.mark.parametrize("text", ["31.02.2026", "abc", "32.1", "1"])
def test_parse_date_rejects(text):
    with pytest.raises(ValueError):
        parse_date(text, 2026)


def test_natural_key_orders_numbers():
    assert sorted(["10", "2", "1020.1", "1020"], key=natural_key) == ["2", "10", "1020", "1020.1"]
