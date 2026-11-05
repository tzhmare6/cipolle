"""Eingabe und Anzeige von Beträgen und Daten.

Beträge sind überall ganze Rappen (int), damit keine Rundungsfehler entstehen.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation


def parse_amount(text: str) -> int | None:
    """Wandelt Eingaben wie ``1'234.50`` oder ``12,5`` in Rappen um.

    Leere Eingabe ergibt ``None``, ungültige Eingabe löst ``ValueError`` aus.
    """
    cleaned = re.sub(r"[\s'’]", "", text).replace(",", ".")
    if not cleaned:
        return None
    if not re.fullmatch(r"[+-]?(\d+(\.\d*)?|\.\d+)", cleaned):
        raise ValueError(f"Ungültiger Betrag: {text}")
    try:
        cents = Decimal(cleaned) * 100
    except InvalidOperation as exc:
        raise ValueError(f"Ungültiger Betrag: {text}") from exc
    if cents != cents.to_integral_value():
        raise ValueError(f"Höchstens zwei Dezimalstellen: {text}")
    return int(cents)


def format_amount(cents: int | None) -> str:
    """Formatiert Rappen im Schweizer Format, z. B. ``-1'234.50``."""
    if cents is None:
        return ""
    sign = "-" if cents < 0 else ""
    francs, rappen = divmod(abs(cents), 100)
    return f"{sign}{francs:,}".replace(",", "'") + f".{rappen:02d}"


def plain_amount(cents: int | None) -> str:
    """Betrag ohne Tausendertrennung, für CSV-Dateien."""
    return "" if cents is None else format_amount(cents).replace("'", "")


def parse_date(text: str, default_year: int) -> date | None:
    """Liest ``31.12.2026``, ``31.12.26``, ``31.12``, ``3112`` oder ``311226``.

    Fehlt das Jahr, gilt ``default_year``. Leere Eingabe ergibt ``None``,
    ungültige Eingabe löst ``ValueError`` aus.
    """
    cleaned = text.strip()
    if not cleaned:
        return None
    iso = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", cleaned)
    if iso:
        year, month, day = (int(part) for part in iso.groups())
    else:
        dotted = re.fullmatch(r"(\d{1,2})[./](\d{1,2})(?:[./](\d{2}|\d{4})?)?", cleaned)
        compact = re.fullmatch(r"(\d{2})(\d{2})(\d{2}|\d{4})?", cleaned)
        match = dotted or compact
        if not match:
            raise ValueError(f"Ungültiges Datum: {text}")
        day, month = int(match[1]), int(match[2])
        year = int(match[3]) if match[3] else default_year
        if year < 100:
            year += 2000
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise ValueError(f"Ungültiges Datum: {text}") from exc


def format_date(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


def natural_key(number: str) -> list:
    """Sortierschlüssel, der ``2`` vor ``10`` einordnet."""
    return [
        (0, int(part), "") if part.isdigit() else (1, 0, part.lower())
        for part in re.split(r"(\d+)", number)
        if part
    ]
