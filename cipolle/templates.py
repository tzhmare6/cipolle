"""Kontenplan-Vorlagen."""

from __future__ import annotations

from dataclasses import dataclass, field

ASSET, LIABILITY, EXPENSE, REVENUE = 1, 2, 3, 4

KLASS_NAMES = {
    ASSET: "Aktiven",
    LIABILITY: "Passiven",
    EXPENSE: "Aufwand",
    REVENUE: "Ertrag",
}

@dataclass(frozen=True)
class Chart:
    """Kontenplan: Gruppen (Code, Name, Summe in) und Konten."""

    groups: list[tuple[str, str, str]] = field(default_factory=list)
    accounts: list[tuple[str, str, int, str]] = field(default_factory=list)
    profit_group: str = ""  # Gruppe, in der der Jahreserfolg erscheint


# Vereinfachter Kontenplan nach Schweizer KMU-Kontenrahmen.
KMU_CHART = Chart(
    groups=[
        ("1", "Total Aktiven", ""),
        ("10", "Umlaufvermögen", "1"),
        ("100", "Flüssige Mittel", "10"),
        ("110", "Forderungen aus Lieferungen und Leistungen", "10"),
        ("114", "Übrige kurzfristige Forderungen", "10"),
        ("120", "Vorräte", "10"),
        ("130", "Aktive Rechnungsabgrenzungen", "10"),
        ("14", "Anlagevermögen", "1"),
        ("150", "Mobile Sachanlagen", "14"),
        ("2", "Total Passiven", ""),
        ("2A", "Fremdkapital", "2"),
        ("20", "Kurzfristiges Fremdkapital", "2A"),
        ("200", "Verbindlichkeiten aus Lieferungen und Leistungen", "20"),
        ("210", "Kurzfristige verzinsliche Verbindlichkeiten", "20"),
        ("230", "Passive Rechnungsabgrenzungen", "20"),
        ("24", "Langfristiges Fremdkapital", "2A"),
        ("240", "Langfristige verzinsliche Verbindlichkeiten", "24"),
        ("28", "Eigenkapital", "2"),
        ("30", "Betriebsertrag", ""),
        ("40", "Material- und Warenaufwand", ""),
        ("50", "Personalaufwand", ""),
        ("60", "Übriger Betriebsaufwand", ""),
        ("68", "Abschreibungen und Finanzerfolg", ""),
        ("80", "Ausserordentlicher Erfolg und Steuern", ""),
    ],
    accounts=[
        ("1000", "Kasse", ASSET, "100"),
        ("1020", "Bank", ASSET, "100"),
        ("1100", "Forderungen aus Lieferungen und Leistungen", ASSET, "110"),
        ("1140", "Vorschüsse und Darlehen", ASSET, "114"),
        ("1200", "Warenvorrat", ASSET, "120"),
        ("1300", "Aktive Rechnungsabgrenzung", ASSET, "130"),
        ("1500", "Maschinen und Apparate", ASSET, "150"),
        ("1510", "Mobiliar und Einrichtungen", ASSET, "150"),
        ("1520", "Büromaschinen, Informatik", ASSET, "150"),
        ("1530", "Fahrzeuge", ASSET, "150"),
        ("2000", "Verbindlichkeiten aus Lieferungen und Leistungen", LIABILITY, "200"),
        ("2100", "Bankverbindlichkeiten", LIABILITY, "210"),
        ("2300", "Passive Rechnungsabgrenzung", LIABILITY, "230"),
        ("2400", "Darlehen", LIABILITY, "240"),
        ("2800", "Eigenkapital", LIABILITY, "28"),
        ("2850", "Privat", LIABILITY, "28"),
        ("2970", "Gewinnvortrag", LIABILITY, "28"),
        ("3000", "Dienstleistungsertrag", REVENUE, "30"),
        ("3200", "Warenertrag", REVENUE, "30"),
        ("3800", "Erlösminderungen", REVENUE, "30"),
        ("3900", "Übriger Ertrag", REVENUE, "30"),
        ("4000", "Materialaufwand", EXPENSE, "40"),
        ("4200", "Warenaufwand", EXPENSE, "40"),
        ("5000", "Löhne", EXPENSE, "50"),
        ("5700", "Sozialversicherungsaufwand", EXPENSE, "50"),
        ("5800", "Übriger Personalaufwand", EXPENSE, "50"),
        ("6000", "Raumaufwand", EXPENSE, "60"),
        ("6100", "Unterhalt und Reparaturen", EXPENSE, "60"),
        ("6200", "Fahrzeugaufwand", EXPENSE, "60"),
        ("6300", "Sachversicherungen und Gebühren", EXPENSE, "60"),
        ("6400", "Energie und Entsorgung", EXPENSE, "60"),
        ("6500", "Verwaltungsaufwand", EXPENSE, "60"),
        ("6570", "Informatikaufwand", EXPENSE, "60"),
        ("6600", "Werbeaufwand", EXPENSE, "60"),
        ("6700", "Sonstiger Betriebsaufwand", EXPENSE, "60"),
        ("6800", "Abschreibungen", EXPENSE, "68"),
        ("6900", "Finanzaufwand", EXPENSE, "68"),
        ("6950", "Finanzertrag", REVENUE, "68"),
        ("8000", "Ausserordentlicher Aufwand", EXPENSE, "80"),
        ("8100", "Ausserordentlicher Ertrag", REVENUE, "80"),
        ("8900", "Direkte Steuern", EXPENSE, "80"),
    ],
    profit_group="28",
)


def guess_klass(number: str) -> int:
    """Leitet die Kontenklasse aus der ersten Ziffer ab."""
    return {"1": ASSET, "2": LIABILITY, "3": REVENUE}.get(number[:1], EXPENSE)
