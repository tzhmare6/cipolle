"""Erzeugt erfundene Testdaten: eine kleine Beratungsfirma über zwei Geschäftsjahre.

Aufruf im Projektordner: python testdaten/make_testdata.py
Ergebnis in testdaten/:
    Muster GmbH 2025.cipolle  ganzes Jahr mit rund 200 Buchungen
    Muster GmbH 2026.cipolle  per Jahreswechsel erstellt, Januar bis März gebucht
Vorhandene Dateien werden ersetzt. Alle Namen und Beträge sind erfunden, die
Zufallszahlen sind fest, jeder Lauf ergibt dieselben Daten.
"""

import random
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cipolle.book import Book, create_next_year  # noqa: E402
from cipolle.templates import KMU_CHART  # noqa: E402

HERE = Path(__file__).resolve().parent
COMPANY = "Muster GmbH"
CUSTOMERS = ["Müller AG", "Keller GmbH", "Brunner & Partner", "Gemeinde Seedorf", "Huber Treuhand", "Alpina Sport AG"]

OPENING = {
    "1000": 800_00, "1020": 42_000_00, "1100": 5_400_00, "1510": 9_000_00, "1520": 4_200_00,
    "2000": 2_600_00, "2400": 15_000_00, "2800": 40_000_00, "2970": 3_800_00,
}


class Journal:
    """Bucht über Kontonummern und Beträge in Franken."""

    def __init__(self, book: Book):
        self.book = book
        self.ids = {account.number: account.id for account in book.accounts()}
        self.doc = 0
        self.open_invoices: list[tuple[date, str, float]] = []

    def post(self, day: date, text: str, debit: str | None, credit: str | None, francs: float, doc: bool = True) -> None:
        if doc:
            self.doc += 1
        self.book.add_entry(day, str(self.doc) if doc else "", text, self.ids.get(debit), self.ids.get(credit),
                            round(francs * 100))

    def invoices(self, year: int, month: int, count: int, low: int, high: int, rng: random.Random) -> None:
        """Stellt Rechnungen und verbucht die Zahlung der Rechnungen, die älter als 30 Tage sind."""
        for _ in range(count):
            customer = rng.choice(CUSTOMERS)
            amount = rng.randrange(low, high, 50)
            day = date(year, month, rng.randint(5, 24))
            self.post(day, f"Honorar {customer}", "1100", "3000", amount)
            self.open_invoices.append((day, customer, amount))
        paid_on = date(year, month, 28)
        for invoice in [i for i in self.open_invoices if (paid_on - i[0]).days >= 30]:
            self.open_invoices.remove(invoice)
            self.post(paid_on, f"Zahlung {invoice[1]}", "1020", "1100", invoice[2])

    def split(self, day: date, text: str, credit: str, parts: list[tuple[str, str, float]]) -> None:
        """Sammelbuchung: ein Haben-Konto, mehrere Soll-Konten."""
        self.post(day, text, None, credit, sum(amount for _t, _n, amount in parts))
        for part_text, debit, amount in parts:
            self.post(day, part_text, debit, None, amount, doc=False)


def remove(path: Path) -> None:
    for candidate in (path, path.with_name(path.name + ".bak")):
        candidate.unlink(missing_ok=True)


def year_2025(path: Path) -> Book:
    remove(path)
    book = Book.create(path, COMPANY, date(2025, 1, 1), date(2025, 12, 31), KMU_CHART)
    with book.step("Testdaten"):
        for number, amount in OPENING.items():
            book.update_account(book.account_by_number(number).id, opening=amount)
        journal = Journal(book)
        rng = random.Random(2025)
        for month in range(1, 13):
            journal.post(date(2025, month, 2), f"Miete {month:02d}/2025", "6000", "1020", 1_800)
            journal.invoices(2025, month, rng.randint(2, 3), 1_800, 7_500, rng)
            journal.post(date(2025, month, rng.randint(8, 20)), "Bürobedarf", "6500", "1000", rng.randrange(40, 260) + 0.5)
            journal.post(date(2025, month, 15), "Software-Abos", "6570", "1020", 189)
            journal.post(date(2025, month, rng.randint(10, 22)), "Treibstoff", "6200", "1020", rng.randrange(90, 220))
            journal.post(date(2025, month, 25), f"Lohn {month:02d}/2025", "5000", "1020", 6_500)
            journal.post(date(2025, month, 25), f"Sozialversicherungen {month:02d}/2025", "5700", "1020", 1_105)
            journal.post(date(2025, month, 28), "Privatbezug", "2850", "1020", 1_500)
            journal.post(date(2025, month, 30 if month != 2 else 28), "Bankspesen", "6900", "1020", 12)
            if month % 3 == 0:
                journal.post(date(2025, month, 20), f"Strom Quartal {month // 3}", "6400", "1020", rng.randrange(180, 320))
                journal.post(date(2025, month, 30), "Bargeld für Kasse", "1000", "1020", 500)
                journal.post(date(2025, month, 30), f"Amortisation Darlehen Q{month // 3}", "2400", "1020", 1_250)
            if month in (3, 9):
                journal.post(date(2025, month, 12), "Inserat Gewerbezeitung", "6600", "1020", 780)

        journal.post(date(2025, 1, 20), "Zahlung Lieferant Vorjahr", "2000", "1020", 2_600)
        journal.post(date(2025, 2, 10), "Betriebshaftpflicht 2025", "6300", "1020", 960)
        journal.post(date(2025, 4, 14), "Neuer Laptop", "1520", "1020", 2_350)
        journal.post(date(2025, 5, 6), "Weiterbildung Projektleitung", "5800", "1020", 1_450)
        journal.split(date(2025, 6, 18), "Rechnung Bürocenter Zug", "2000", [
            ("Büromöbel", "1510", 1_980), ("Druckerpapier und Toner", "6500", 340), ("Reparatur Drucker", "6100", 260)])
        journal.post(date(2025, 7, 31), "Zahlung Bürocenter Zug", "2000", "1020", 2_580)
        journal.post(date(2025, 8, 22), "Gutschrift Keller GmbH", "1100", "3000", -350)
        journal.post(date(2025, 9, 30), "Verkauf Fachbuch", "1000", "3200", 120)
        journal.post(date(2025, 11, 12), "Spende Turnverein", "6700", "1020", 200)
        journal.post(date(2025, 12, 31), "Zinsertrag", "1020", "6950", 41.35)
        journal.post(date(2025, 12, 31), "Abschreibung Mobiliar", "6800", "1510", 1_100)
        journal.post(date(2025, 12, 31), "Abschreibung Informatik", "6800", "1520", 1_650)
        journal.post(date(2025, 12, 31), "Direkte Steuern Akonto", "8900", "1020", 1_800)
        book.sort_entries_by_date()
    book.clear_undo()
    return book


def year_2026(source: Book, path: Path) -> Book:
    remove(path)
    book = create_next_year(source, path, "2970")
    with book.step("Testdaten"):
        journal = Journal(book)
        rng = random.Random(2026)
        receivable = book.account_by_number("1100").opening
        journal.post(date(2026, 1, 29), "Zahlungen offene Rechnungen 2025", "1020", "1100", receivable / 100)
        for month in range(1, 4):
            journal.post(date(2026, month, 2), f"Miete {month:02d}/2026", "6000", "1020", 1_850)
            journal.invoices(2026, month, 3, 2_500, 7_500, rng)
            journal.post(date(2026, month, 15), "Software-Abos", "6570", "1020", 195)
            journal.post(date(2026, month, 25), f"Lohn {month:02d}/2026", "5000", "1020", 6_650)
            journal.post(date(2026, month, 25), f"Sozialversicherungen {month:02d}/2026", "5700", "1020", 1_130)
            journal.post(date(2026, month, 28), "Privatbezug", "2850", "1020", 1_500)
        journal.post(date(2026, 2, 10), "Betriebshaftpflicht 2026", "6300", "1020", 980)
        book.sort_entries_by_date()
    book.clear_undo()
    return book


def main() -> None:
    first = year_2025(HERE / f"{COMPANY} 2025.cipolle")
    second = year_2026(first, HERE / f"{COMPANY} 2026.cipolle")
    for book in (first, second):
        print(f"{book.path.name}: {len(book.entries())} Buchungen, Warnungen: {book.warnings() or 'keine'}")
        book.close()


if __name__ == "__main__":
    main()
