"""Seite für eine Auswertung, mit Zeitraum und Export nach PDF, CSV und Drucker."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, QSettings, QUrl, Signal
from PySide6.QtGui import QFont, QPageLayout, QPageSize, QPalette, QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..book import Book
from ..reports import Report


def to_qdate(value: date) -> QDate:
    return QDate(value.year, value.month, value.day)


def to_date(value: QDate) -> date:
    return date(value.year(), value.month(), value.day())


def write_pdf(report: Report, path: str | Path) -> None:
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(path))
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setDocName(report.title)
    if len(report.columns) > 5:
        printer.setPageOrientation(QPageLayout.Orientation.Landscape)
    print_report(report, printer)


def print_report(report: Report, printer: QPrinter) -> None:
    document = QTextDocument()
    document.setDefaultFont(QFont("Sans Serif", 9))
    document.setHtml(report.to_html(links=False))
    document.print_(printer)


class ReportPage(QWidget):
    """``build`` erhält Buchhaltung, Beginn, Ende, Nullkonten und Konto-ID."""

    link_activated = Signal(str)

    def __init__(
        self,
        build: Callable[..., Report],
        uses_start: bool = True,
        zero_option: bool = False,
        account_picker: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.book: Book | None = None
        self.build = build

        controls = QHBoxLayout()
        self.account = QComboBox()
        self.account.setMinimumWidth(280)
        if account_picker:
            controls.addWidget(QLabel("Konto"))
            controls.addWidget(self.account)
        self.start = self._date_edit()
        self.end = self._date_edit()
        if uses_start:
            controls.addWidget(QLabel("Von"))
            controls.addWidget(self.start)
            controls.addWidget(QLabel("Bis"))
        else:
            controls.addWidget(QLabel("Per"))
        controls.addWidget(self.end)
        self.show_zero = QCheckBox("Konten ohne Saldo zeigen")
        if zero_option:
            controls.addWidget(self.show_zero)
        controls.addStretch()
        for label, handler in (("PDF…", self.export_pdf), ("CSV…", self.export_csv), ("Drucken…", self.print)):
            button = QPushButton(label)
            button.clicked.connect(handler)
            controls.addWidget(button)

        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        self.view.anchorClicked.connect(self._link_clicked)

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.view)

        self.account_picker = account_picker
        self.uses_start = uses_start
        self.start.dateChanged.connect(self.refresh)
        self.end.dateChanged.connect(self.refresh)
        self.show_zero.toggled.connect(self.refresh)
        self.account.currentIndexChanged.connect(self.refresh)

    @staticmethod
    def _date_edit() -> QDateEdit:
        edit = QDateEdit()
        edit.setDisplayFormat("dd.MM.yyyy")
        edit.setCalendarPopup(True)
        return edit

    def set_book(self, book: Book) -> None:
        self.book = book
        self.set_period(book.start, book.end)
        self.reload_accounts()
        self.refresh()

    def clear_book(self) -> None:
        self.book = None
        self.view.clear()

    def set_period(self, start: date, end: date) -> None:
        for edit, value in ((self.start, start), (self.end, end)):
            edit.blockSignals(True)
            edit.setDate(to_qdate(value))
            edit.blockSignals(False)

    def reload_accounts(self) -> None:
        if not self.account_picker or self.book is None:
            return
        current = self.account.currentData()
        self.account.blockSignals(True)
        self.account.clear()
        for account in self.book.accounts():
            self.account.addItem(account.label, account.id)
        position = self.account.findData(current)
        self.account.setCurrentIndex(max(position, 0))
        self.account.blockSignals(False)

    def show_account(self, account_id: int) -> None:
        self.reload_accounts()
        self.account.setCurrentIndex(self.account.findData(account_id))
        self.refresh()

    def report(self) -> Report | None:
        if self.book is None or (self.account_picker and self.account.currentData() is None):
            return None
        return self.build(
            self.book,
            to_date(self.start.date()) if self.uses_start else None,
            to_date(self.end.date()),
            self.show_zero.isChecked(),
            self.account.currentData(),
        )

    def refresh(self) -> None:
        self.reload_accounts()
        report = self.report()
        position = self.view.verticalScrollBar().value()
        text = self.palette().color(QPalette.ColorRole.Text).name()
        self.view.document().setDefaultStyleSheet(f"a {{ color: {text}; text-decoration: none; }}")
        self.view.setHtml(report.to_html() if report else "")
        self.view.verticalScrollBar().setValue(position)

    def _link_clicked(self, url: QUrl) -> None:
        self.link_activated.emit(url.toString())

    def _ask_path(self, suffix: str, description: str) -> str | None:
        report = self.report()
        if report is None:
            return None
        settings = QSettings()
        folder = settings.value("exportDir", str(Path.home()))
        name = f"{report.title} {self.book.end.year}{suffix}".replace("/", "-")
        path, _ = QFileDialog.getSaveFileName(self, "Exportieren", str(Path(folder) / name), description)
        if path:
            settings.setValue("exportDir", str(Path(path).parent))
        return path or None

    def export_pdf(self) -> None:
        path = self._ask_path(".pdf", "PDF (*.pdf)")
        if path:
            write_pdf(self.report(), path)

    def export_csv(self) -> None:
        path = self._ask_path(".csv", "CSV (*.csv)")
        if not path:
            return
        try:
            Path(path).write_text(self.report().to_csv(), encoding="utf-8-sig", newline="")
        except OSError as exc:
            QMessageBox.warning(self, "Export fehlgeschlagen", str(exc))

    def print(self) -> None:
        report = self.report()
        if report is None:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        if QPrintDialog(printer, self).exec() == QDialog.DialogCode.Accepted:
            print_report(report, printer)
