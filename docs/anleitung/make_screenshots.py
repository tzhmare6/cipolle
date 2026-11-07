"""Fotografiert die echte App mit erfundenen Beispieldaten für die Anleitung.

Aufruf auf dem Mac im Projektordner, mit PySide6:
    QT_QPA_PLATFORM=cocoa python docs/anleitung/make_screenshots.py
Die Bilder landen in build/anleitung/shots. Fenster gehen dabei kurz auf.
"""

import tempfile
from datetime import date
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from cipolle.__main__ import configure
from cipolle.parsing import parse_amount, parse_date
from cipolle.templates import KMU_CHART
from cipolle.ui.branding import StartDialog
from cipolle.ui.dialogs import NewBookDialog
from cipolle.ui.main_window import MainWindow

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "build/anleitung/shots"

OPENING = (("1000", "1'500"), ("1020", "24'000"), ("1510", "8'500"), ("2000", "4'000"), ("2800", "30'000"))
ENTRIES = (
    ("05.01", "1", "Miete Januar", "6000", "1020", "1'800"),
    ("12.01", "2", "Honorar Müller AG", "1100", "3000", "6'400"),
    ("20.01", "3", "Bürobedarf", "6500", "1000", "185.50"),
    ("28.01", "4", "Zahlung Müller AG", "1020", "1100", "6'400"),
    ("31.01", "5", "Lohn Januar", "5000", "1020", "4'200"),
    ("05.02", "6", "Miete Februar", "6000", "1020", "1'800"),
    ("16.02", "7", "Honorar Keller GmbH", "1100", "3000", "4'850"),
    ("24.02", "8", "Neuer Laptop", "1520", "1020", "1'650"),
    ("27.02", "9", "Lohn Februar", "5000", "1020", "4'200"),
)


def settle(ms: int = 250) -> None:
    QTest.qWait(ms)


def shot(widget, name: str) -> None:
    settle()
    widget.grab().save(str(OUT / f"{name}.png"))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp())
    # Eigene Einstellungen, damit die Liste der zuletzt geöffneten Dateien unberührt bleibt.
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp / "settings"))
    app = QApplication([])
    configure(app)
    app.setOrganizationName("CipolleManual")
    app.setApplicationName("CipolleManual")
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)

    window = MainWindow()
    window.resize(1120, 640)
    window.show()
    settle(400)
    shot(window, "start")

    dialog = NewBookDialog(window)
    dialog.company.setText("Muster GmbH")
    dialog.start.setDate(dialog.start.date().fromString("01.01.2026", "dd.MM.yyyy"))
    dialog.end.setDate(dialog.end.date().fromString("31.12.2026", "dd.MM.yyyy"))
    dialog.show()
    shot(dialog, "neu")
    dialog.close()

    window.create_path(tmp / "Muster GmbH 2026.cipolle", "Muster GmbH", date(2026, 1, 1), date(2026, 12, 31), KMU_CHART)
    book = window.book
    ids = {account.number: account.id for account in book.accounts()}
    for number, amount in OPENING:
        book.update_account(ids[number], opening=parse_amount(amount))
    for day, doc, text, debit, credit, amount in ENTRIES:
        book.add_entry(parse_date(day, 2026), doc, text, ids[debit], ids[credit], parse_amount(amount))
    # Eine unvollständige Zeile, damit die rote Markierung zu sehen ist.
    book.add_entry(parse_date("03.03", 2026), "10", "Miete März", ids["6000"], None, None)

    def reload() -> None:
        window.entries_model.reload()
        window.accounts_model.reload()
        window._update_summary()

    reload()
    window.tabs.setCurrentWidget(window.accounts_table)
    settle()
    shot(window, "konten")
    window.tabs.setCurrentWidget(window.entries_table)
    settle()
    window.entries_table.setCurrentIndex(window.entries_model.index(len(window.entries_model.rows) - 1, 3))
    shot(window, "buchungen")

    book.delete_entries([book.entries()[-1].id])
    reload()
    window.resize(1120, 1000)
    window.tabs.setCurrentWidget(window.balance_page)
    settle()
    window.balance_page.refresh()
    shot(window, "bilanz")
    window.resize(1120, 720)
    window.tabs.setCurrentWidget(window.income_page)
    settle()
    window.income_page.refresh()
    shot(window, "erfolg")
    window.show_statement(ids["1020"])
    shot(window, "auszug")

    about = StartDialog(window, auto_close=False)
    about.show()
    QTest.qWait(3400)
    shot(about, "ueber")
    about.close()
    window.close()
    print(f"Fertig: {OUT}")


if __name__ == "__main__":
    main()
