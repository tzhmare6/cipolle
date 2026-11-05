"""Dialoge für neue Dateien, Eigenschaften und den Jahreswechsel."""

from __future__ import annotations

from datetime import date

from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from ..book import Book
from ..templates import KMU_CHART, LIABILITY
from .report_page import to_date, to_qdate


class PropertiesDialog(QDialog):
    def __init__(self, company: str, start: date, end: date, title: str, parent=None, book: Book | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.form = QFormLayout()
        self.company = QLineEdit(company)
        self.start = self._date_edit(start)
        self.end = self._date_edit(end)
        self.form.addRow("Name", self.company)
        self.form.addRow("Geschäftsjahr von", self.start)
        self.form.addRow("bis", self.end)
        self.profit_group = QComboBox()
        if book is not None:
            self.profit_group.addItem("Eigene Zeile vor Total Passiven", "")
            for group in book.groups():
                self.profit_group.addItem(group.label, group.code)
            self.profit_group.setCurrentIndex(max(self.profit_group.findData(book.profit_group), 0))
            self.form.addRow("Jahreserfolg in Gruppe", self.profit_group)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(self.form)
        layout.addWidget(buttons)
        self.setMinimumWidth(380)

    @staticmethod
    def _date_edit(value: date) -> QDateEdit:
        edit = QDateEdit(to_qdate(value))
        edit.setDisplayFormat("dd.MM.yyyy")
        edit.setCalendarPopup(True)
        return edit

    def values(self) -> tuple[str, date, date]:
        return self.company.text().strip(), to_date(self.start.date()), to_date(self.end.date())


class NewBookDialog(PropertiesDialog):
    def __init__(self, parent=None):
        year = date.today().year
        super().__init__("", date(year, 1, 1), date(year, 12, 31), "Neue Buchhaltung", parent)
        self.chart = QComboBox()
        self.chart.addItem("KMU-Kontenplan (Schweiz)", KMU_CHART)
        self.chart.addItem("Leerer Kontenplan", None)
        self.form.addRow("Kontenplan", self.chart)


class EquityDialog(QDialog):
    """Fragt nach dem Konto, das den Jahreserfolg aufnimmt."""

    def __init__(self, book: Book, title: str, note: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.account = QComboBox()
        for account in book.accounts():
            if account.klass == LIABILITY:
                self.account.addItem(account.label, account.number)
        preferred = self.account.findData("2970")
        if preferred >= 0:
            self.account.setCurrentIndex(preferred)
        form = QFormLayout()
        form.addRow("Jahreserfolg auf Konto", self.account)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        label = QLabel(note)
        label.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setMinimumWidth(420)

    def equity_number(self) -> str | None:
        return self.account.currentData()
