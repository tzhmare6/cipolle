"""Hauptfenster."""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import reports
from ..book import FILE_SUFFIX, Book, BookError, HistoryResult, carry_over, create_next_year, next_period
from ..parsing import format_date
from ..chart_io import apply_import, chart_to_json, parse_chart
from ..templates import Chart
from .branding import Backdrop, StartDialog
from .dialogs import EquityDialog, ImportDialog, NewBookDialog, PropertiesDialog
from .models import AccountsModel, EntriesModel
from .report_page import ReportPage
from .tables import AccountsDelegate, EntriesDelegate, LedgerTable

FILE_FILTER = f"Cipolle-Buchhaltung (*{FILE_SUFFIX})"
CHART_FILTER = "Kontenplan (*.json)"
MAX_RECENT = 8


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.book: Book | None = None
        self.entries_model: EntriesModel | None = None
        self.accounts_model: AccountsModel | None = None
        self._save_error_open = False
        self.settings = QSettings()
        self.resize(1180, 760)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_welcome())
        self.stack.addWidget(self._build_tabs())
        self.setCentralWidget(self.stack)
        self._attach_backdrop()

        self.summary = QLabel()
        self.statusBar().addPermanentWidget(self.summary)
        self._build_menus()
        self._set_book(None)

    # -- Aufbau --------------------------------------------------------

    def _build_welcome(self) -> QWidget:
        page = self.welcome_page = QWidget()
        title = QLabel("<h1>Cipolle</h1><p>Lege eine neue Buchhaltung an oder öffne eine bestehende Datei.</p>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        new_button = QPushButton("Neue Buchhaltung…")
        new_button.clicked.connect(self.new_book)
        open_button = QPushButton("Datei öffnen…")
        open_button.clicked.connect(self.open_book)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(new_button)
        buttons.addWidget(open_button)
        buttons.addStretch()
        layout = QVBoxLayout(page)
        layout.addStretch()
        layout.addWidget(title)
        layout.addLayout(buttons)
        layout.addStretch()
        return page

    def _build_tabs(self) -> QWidget:
        self.tabs = QTabWidget()
        self.entries_table = LedgerTable()
        self.entries_table.setItemDelegate(EntriesDelegate(self.entries_table))
        self.accounts_table = LedgerTable()
        self.accounts_table.setItemDelegate(AccountsDelegate(self.accounts_table))
        for table in (self.entries_table, self.accounts_table):
            table.insert_requested.connect(self.insert_row)
            table.delete_requested.connect(self.delete_rows)

        self.statement_page = ReportPage(
            lambda book, start, end, zero, account: reports.account_statement(book, account, start, end),
            account_picker=True,
        )
        self.balance_page = ReportPage(
            lambda book, start, end, zero, account: reports.balance_sheet(book, end, zero),
            uses_start=False,
            zero_option=True,
        )
        self.income_page = ReportPage(
            lambda book, start, end, zero, account: reports.income_statement(book, start, end, zero),
            zero_option=True,
        )
        self.journal_page = ReportPage(
            lambda book, start, end, zero, account: reports.journal(book, start, end),
        )
        self.report_pages = [self.statement_page, self.balance_page, self.income_page, self.journal_page]
        self.tabs.addTab(self.accounts_table, "Konten")
        self.tabs.addTab(self.entries_table, "Buchungen")
        self.tabs.addTab(self.statement_page, "Kontoauszug")
        self.tabs.addTab(self.balance_page, "Bilanz")
        self.tabs.addTab(self.income_page, "Erfolgsrechnung")
        self.tabs.addTab(self.journal_page, "Journal")
        self.tabs.currentChanged.connect(self._tab_changed)
        for page in self.report_pages:
            page.link_activated.connect(self._follow_link)
        self.accounts_table.doubleClicked.connect(self._account_double_clicked)
        return self.tabs

    def _attach_backdrop(self) -> None:
        backdrop = Backdrop(self.stack)
        backdrop.attach(self.welcome_page)
        backdrop.attach(self.entries_table)
        backdrop.attach(self.accounts_table)
        for page in self.report_pages:
            backdrop.attach(page)
            backdrop.attach(page.view)

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&Datei")
        self._add(file_menu, "&Neu…", self.new_book, QKeySequence.StandardKey.New)
        self._add(file_menu, "Ö&ffnen…", self.open_book, QKeySequence.StandardKey.Open)
        self.recent_menu = file_menu.addMenu("&Zuletzt geöffnet")
        file_menu.addSeparator()
        self.book_actions = [
            self._add(file_menu, "&Schliessen", self.close_book, QKeySequence.StandardKey.Close),
        ]
        file_menu.addSeparator()
        self.book_actions += [
            self._add(file_menu, "&Eigenschaften…", self.edit_properties),
            self._add(file_menu, "Neues &Jahr erstellen…", self.new_year),
            self._add(file_menu, "Eröffnung aus &Vorjahr aktualisieren…", self.update_opening),
        ]
        file_menu.addSeparator()
        self.book_actions += [
            self._add(file_menu, "Kontenplan e&xportieren…", self.export_chart),
            self._add(file_menu, "Kontenplan &importieren…", self.import_chart),
        ]
        file_menu.addSeparator()
        self._add(file_menu, "&Beenden", self.close, QKeySequence.StandardKey.Quit)

        edit_menu = self.menuBar().addMenu("&Bearbeiten")
        self.undo_action = self._add(edit_menu, "Rückgängig", self.undo, QKeySequence.StandardKey.Undo)
        self.redo_action = self._add(edit_menu, "Wiederholen", self.redo, "Ctrl+Y")
        self.redo_action.setShortcuts(["Ctrl+Y", "Ctrl+Shift+Z"])
        edit_menu.addSeparator()
        self.book_actions += [
            self._add(edit_menu, "Zeile einfügen &oben", lambda: self.insert_row(False), "Ctrl+I"),
            self._add(edit_menu, "Zeile einfügen &unten", lambda: self.insert_row(True), "Ctrl+Shift+I"),
            self._add(edit_menu, "Zeile &löschen", self.delete_rows, "Ctrl+Del"),
            self._add(edit_menu, "Buchungen nach &Datum sortieren", self.sort_entries),
        ]

        view_menu = self.menuBar().addMenu("&Ansicht")
        for index in range(self.tabs.count()):
            action = self._add(
                view_menu,
                self.tabs.tabText(index),
                lambda _=False, i=index: self.tabs.setCurrentIndex(i),
                f"Ctrl+{index + 1}",
            )
            self.book_actions.append(action)

        help_menu = self.menuBar().addMenu("&Hilfe")
        self._add(help_menu, "Über Cipolle", self.about)
        self._update_recent_menu()

    def _add(self, menu, text, handler, shortcut=None) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(handler)
        if shortcut is not None:
            action.setShortcut(shortcut)
        menu.addAction(action)
        return action

    # -- Datei ---------------------------------------------------------

    def open_initial(self, path: str | None) -> None:
        recent = self._recent()
        if path:
            self.open_path(path)
        elif (
            self.settings.value("reopenLast", True, type=bool)
            and recent
            and Path(recent[0]).is_file()
        ):
            self.open_path(recent[0])

    def _commit_edits(self) -> None:
        if self.book is not None:
            self.entries_table.commit_open_editor()
            self.accounts_table.commit_open_editor()

    def _close_book(self) -> None:
        self._commit_edits()
        if self.book is not None:
            self.accounts_model.needs_resort = False
            self.book.close()
            self.book = None

    def _set_book(self, book: Book | None) -> None:
        self._close_book()
        self.book = book
        for action in self.book_actions:
            action.setEnabled(book is not None)
        if book is None:
            self.entries_table.setModel(None)
            self.accounts_table.setModel(None)
            self.entries_model = self.accounts_model = None
            for page in self.report_pages:
                page.clear_book()
            self.stack.setCurrentIndex(0)
            self.setWindowTitle("Cipolle")
            self.summary.clear()
            self._update_history_actions()
            return
        self.entries_model = EntriesModel(book, self)
        self.accounts_model = AccountsModel(book, self)
        self.entries_table.setModel(self.entries_model)
        self.accounts_table.setModel(self.accounts_model)
        for model in (self.entries_model, self.accounts_model):
            model.message.connect(self._show_error)
            model.changed.connect(self._update_summary)
            # Verzögert, weil der Dialog sonst einem offenen Eingabefeld den Fokus nimmt.
            model.save_failed.connect(self._show_save_error, Qt.ConnectionType.QueuedConnection)
        # Verzögert, weil das Neuordnen ein noch offenes Eingabefeld schliessen würde.
        self.accounts_model.order_changed.connect(
            self.accounts_table.apply_resort, Qt.ConnectionType.QueuedConnection
        )
        self._configure_columns()
        for page in self.report_pages:
            page.set_book(book)
        self.stack.setCurrentIndex(1)
        self.tabs.setCurrentWidget(self.accounts_table)
        self._update_title()
        self._update_summary()
        self._remember(book.path)
        self.settings.setValue("reopenLast", True)
        self.settings.setValue("lastDir", str(book.path.parent))
        QTimer.singleShot(0, self._focus_current_table)

    def _configure_columns(self) -> None:
        stretch = QHeaderView.ResizeMode.Stretch
        entries = self.entries_table.horizontalHeader()
        for column, width in enumerate((100, 80, 0, 210, 210, 110)):
            if width:
                self.entries_table.setColumnWidth(column, width)
        entries.setSectionResizeMode(EntriesModel.TEXT, stretch)
        accounts = self.accounts_table.horizontalHeader()
        for column, width in enumerate((80, 80, 0, 100, 90, 120, 120)):
            if width:
                self.accounts_table.setColumnWidth(column, width)
        accounts.setSectionResizeMode(AccountsModel.NAME, stretch)

    def _focus_current_table(self) -> None:
        """Setzt den Cursor: im Kontenplan oben, bei den Buchungen in die neue Zeile."""
        table = self._current_table()
        if table is None or table.model() is None:
            return
        model = table.model()
        row = model.rowCount() - 1 if table is self.entries_table else 0
        index = model.index(row, model.FIRST_COLUMN)
        table.setCurrentIndex(index)
        table.scrollTo(index)
        table.setFocus()

    def _update_title(self) -> None:
        book = self.book
        self.setWindowTitle(f"{book.company} {format_date(book.start)} bis {format_date(book.end)} – Cipolle")

    def _update_history_actions(self) -> None:
        undo = self.book.undo_label if self.book else None
        redo = self.book.redo_label if self.book else None
        self.undo_action.setText(f"Rückgängig: {undo}" if undo else "Rückgängig")
        self.redo_action.setText(f"Wiederholen: {redo}" if redo else "Wiederholen")
        self.undo_action.setEnabled(undo is not None)
        self.redo_action.setEnabled(redo is not None)

    def _update_summary(self) -> None:
        self._update_history_actions()
        if self.book is None:
            return
        warnings = self.book.warnings()
        count = len(self.book.entries())
        text = f"{count} Buchungen"
        if warnings:
            text += " · " + " · ".join(warnings)
            self.summary.setStyleSheet("color: #c0392b; font-weight: bold")
        else:
            text += " · keine Differenzen"
            self.summary.setStyleSheet("")
        self.summary.setText(text)

    def _show_error(self, message: str) -> None:
        self.statusBar().showMessage(message, 8000)

    def _show_save_error(self, detail: str) -> None:
        """Zeigt einen Schreibfehler. Folgefehler derselben Aktion öffnen keinen zweiten Dialog."""
        if self._save_error_open:
            return
        self._save_error_open = True
        try:
            text = f"Die Änderung konnte nicht in die Datei geschrieben werden.\n\n{detail}"
            QMessageBox.warning(self, "Nicht gespeichert", text)
        finally:
            self._save_error_open = False

    @contextmanager
    def _saving(self):
        """Meldet Schreibfehler im Block und zeigt danach den Stand der Datei."""
        try:
            yield
        except sqlite3.Error as exc:
            self._show_save_error(str(exc))
            self.entries_model.reload()
            self.accounts_model.reload()
            self._update_summary()

    def _start_dir(self) -> str:
        return self.settings.value("lastDir", str(Path.home()))

    def _ask_new_path(self, suggestion: str) -> str | None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Datei anlegen",
            str(Path(self._start_dir()) / suggestion),
            FILE_FILTER,
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not path:
            return None
        if not path.endswith(FILE_SUFFIX):
            path += FILE_SUFFIX
        return path

    @staticmethod
    def _file_name(company: str, year: int) -> str:
        cleaned = re.sub(r"[^\w -]", "", company).strip() or "Buchhaltung"
        return f"{cleaned} {year}{FILE_SUFFIX}"

    def new_book(self) -> None:
        dialog = NewBookDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        company, start, end = dialog.values()
        path = self._ask_new_path(self._file_name(company, end.year))
        if path:
            self.create_path(path, company, start, end, dialog.chart.currentData())

    def create_path(self, path, company, start, end, chart) -> None:
        try:
            self._set_book(Book.create(path, company, start, end, chart))
        except (BookError, sqlite3.Error, OSError) as exc:
            QMessageBox.warning(self, "Datei nicht angelegt", str(exc))

    def close_book(self) -> None:
        """Schliesst die Datei. Der nächste Start beginnt dann auf der Startseite."""
        self._set_book(None)
        self.settings.setValue("reopenLast", False)

    def open_book(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Datei öffnen", self._start_dir(), FILE_FILTER)
        if path:
            self.open_path(path)

    def open_path(self, path: str | Path) -> None:
        try:
            book = Book.open(path)
        except (BookError, sqlite3.Error, OSError) as exc:
            QMessageBox.warning(self, "Datei nicht geöffnet", str(exc))
            return
        self._set_book(book)

    def open_from_system(self, path: str) -> None:
        """Öffnet eine Datei aus dem Finder. Offene Dialoge hängen an der aktuellen Datei."""
        dialog = QApplication.activeModalWidget()
        if dialog is not None and not isinstance(dialog, StartDialog):
            self._show_error("Zuerst den offenen Dialog schliessen, dann die Datei erneut öffnen.")
            return
        self.open_path(path)
        self.raise_()
        self.activateWindow()

    def edit_properties(self) -> None:
        self._commit_edits()
        book = self.book
        dialog = PropertiesDialog(book.company, book.start, book.end, "Eigenschaften", self, book)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            book.set_properties(*dialog.values())
            book.set_profit_group(dialog.profit_group.currentData())
        except (BookError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "Nicht gespeichert", str(exc))
            return
        self.entries_model.reload()
        self.accounts_model.reload()
        for page in self.report_pages:
            page.set_book(book)
        self._update_title()
        self._update_summary()

    def _confirm_warnings(self, title: str) -> bool:
        warnings = self.book.warnings()
        if not warnings:
            return True
        text = "\n".join(warnings) + "\n\nTrotzdem fortfahren?"
        return QMessageBox.question(self, title, text) == QMessageBox.StandardButton.Yes

    def new_year(self) -> None:
        self._commit_edits()
        title = "Neues Jahr erstellen"
        if not self._confirm_warnings(title):
            return
        start, end = next_period(self.book.start, self.book.end)
        note = (
            f"Erstellt eine neue Datei für {format_date(start)} bis {format_date(end)} "
            "mit dem Kontenplan und den Schlusssalden dieses Jahrs als Eröffnung."
        )
        dialog = EquityDialog(self.book, title, note, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.equity_number() is None:
            return
        path = self._ask_new_path(self._file_name(self.book.company, end.year))
        if path:
            self.create_next_year_at(path, dialog.equity_number())

    def create_next_year_at(self, path, equity_number: str) -> None:
        try:
            target = create_next_year(self.book, path, equity_number)
        except (BookError, sqlite3.Error, OSError) as exc:
            QMessageBox.warning(self, "Neues Jahr nicht erstellt", str(exc))
            return
        self._set_book(target)

    def update_opening(self) -> None:
        self._commit_edits()
        title = "Eröffnung aus Vorjahr aktualisieren"
        path, _ = QFileDialog.getOpenFileName(self, "Vorjahr wählen", self._start_dir(), FILE_FILTER)
        if not path:
            return
        try:
            source = Book.open(path, backup=False)
        except (BookError, sqlite3.Error, OSError) as exc:
            QMessageBox.warning(self, title, str(exc))
            return
        try:
            note = "Ersetzt alle Eröffnungssaldi dieses Jahrs durch die Schlusssalden der gewählten Datei."
            dialog = EquityDialog(source, title, note, self)
            if dialog.exec() == QDialog.DialogCode.Accepted and dialog.equity_number():
                carry_over(source, self.book, dialog.equity_number())
        except (BookError, sqlite3.Error) as exc:
            QMessageBox.warning(self, title, str(exc))
        finally:
            source.close()
        self.accounts_model.reload()
        self.entries_model.reload()
        self._refresh_current()
        self._update_summary()

    def export_chart(self) -> None:
        self._commit_edits()
        name = f"Kontenplan {re.sub(r'[^\w -]', '', self.book.company).strip()}.json"
        folder = self.settings.value("exportDir", str(Path.home()))
        path, _ = QFileDialog.getSaveFileName(
            self, "Kontenplan exportieren", str(Path(folder) / name), CHART_FILTER
        )
        if path:
            self.settings.setValue("exportDir", str(Path(path).parent))
            self.export_chart_to(path if path.endswith(".json") else f"{path}.json")

    def export_chart_to(self, path: str | Path) -> None:
        try:
            Path(path).write_text(chart_to_json(self.book.chart()), encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Export fehlgeschlagen", str(exc))
            return
        self.statusBar().showMessage(f"Kontenplan exportiert: {path}", 5000)

    def import_chart(self) -> None:
        self._commit_edits()
        folder = self.settings.value("exportDir", str(Path.home()))
        path, _ = QFileDialog.getOpenFileName(self, "Kontenplan importieren", folder, CHART_FILTER)
        if not path:
            return
        chart = self.read_chart(path)
        if chart is None:
            return
        dialog = ImportDialog(self.book, chart, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.import_chart_data(chart, dialog.replace.isChecked())

    def read_chart(self, path: str | Path) -> Chart | None:
        try:
            return parse_chart(Path(path).read_text(encoding="utf-8"))
        except (BookError, OSError, UnicodeDecodeError) as exc:
            QMessageBox.warning(self, "Kontenplan nicht importiert", str(exc))
            return None

    def import_chart_data(self, chart: Chart, replace: bool) -> None:
        try:
            apply_import(self.book, chart, replace)
        except (BookError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "Kontenplan nicht importiert", str(exc))
        self.accounts_model.reload()
        self.entries_model.reload()
        self.tabs.setCurrentWidget(self.accounts_table)
        self._update_summary()

    def _recent(self) -> list[str]:
        value = self.settings.value("recent", [])
        return [value] if isinstance(value, str) else list(value or [])

    def _remember(self, path: Path) -> None:
        text = str(path.resolve())
        recent = [text] + [p for p in self._recent() if p != text]
        self.settings.setValue("recent", recent[:MAX_RECENT])
        self._update_recent_menu()

    def _update_recent_menu(self) -> None:
        self.recent_menu.clear()
        for path in self._recent():
            action = self.recent_menu.addAction(path)
            action.triggered.connect(lambda _=False, p=path: self.open_path(p))
        self.recent_menu.setEnabled(not self.recent_menu.isEmpty())

    # -- Bearbeiten ----------------------------------------------------

    def _current_table(self) -> LedgerTable | None:
        page = self.tabs.currentWidget()
        return page if isinstance(page, LedgerTable) else None

    def _select_cell(self, table: LedgerTable, row: int) -> None:
        model = table.model()
        index = model.index(min(row, model.rowCount() - 1), model.FIRST_COLUMN)
        flag = QItemSelectionModel.SelectionFlag.ClearAndSelect
        table.selectionModel().setCurrentIndex(index, flag)
        table.scrollTo(index)
        table.setFocus()

    def insert_row(self, below: bool = False) -> None:
        self._commit_edits()
        table = self._current_table()
        rows = table.selected_data_rows() if table else []
        if not rows:
            return
        with self._saving():
            if below:
                table.model().insert_after(rows[-1])
                self._select_cell(table, rows[-1] + 1)
            else:
                table.model().insert_before(rows[0])
                self._select_cell(table, rows[0])

    def delete_rows(self) -> None:
        self._commit_edits()
        table = self._current_table()
        if table is None:
            return
        model = table.model()
        rows = [row for row in table.selected_rows() if row < len(model.rows)]
        if table is self.accounts_table:
            rows = [row for row in rows if model.rows[row].kind != "profit"]
        if not rows:
            return
        text = f"{len(rows)} Zeilen löschen?" if len(rows) > 1 else self._delete_question(table, rows[0])
        if text and QMessageBox.question(self, "Löschen", text) != QMessageBox.StandardButton.Yes:
            return
        with self._saving():
            model.delete_rows(rows)
            if table is self.accounts_table:
                self.entries_model.reload()
            self._select_cell(table, rows[0])

    def _delete_question(self, table: LedgerTable, row: int) -> str | None:
        """Frage vor dem Löschen. Eine leere eingefügte Zeile braucht keine."""
        if table is self.entries_table:
            return "Diese Buchung löschen?"
        chart_row = self.accounts_model.rows[row]
        if chart_row.kind == "blank":
            return None
        kind = "Gruppe" if chart_row.kind == "group" else "Konto"
        return f"{kind} {chart_row.item.label} löschen?"

    def undo(self) -> None:
        self._commit_edits()
        if self.book is not None:
            with self._saving():
                self._show_history(self.book.undo(), "Rückgängig")

    def redo(self) -> None:
        self._commit_edits()
        if self.book is not None:
            with self._saving():
                self._show_history(self.book.redo(), "Wiederholt")

    def _show_history(self, result: HistoryResult | None, verb: str) -> None:
        """Zeigt das Ergebnis und springt in Tabellen zur betroffenen Zeile."""
        if result is None:
            return
        table = self._current_table()
        current_row = table.currentIndex().row() if table else 0
        self.entries_model.reload()
        self.accounts_model.reload()
        self._update_title()
        self._update_summary()
        self.statusBar().showMessage(f"{verb}: {result.label}", 5000)
        if table is None:
            for page in self.report_pages:
                page.set_book(self.book)
            return
        if result.table == "meta":
            self._select_cell(table, max(current_row, 0))
            return
        table = self.entries_table if result.table == "entries" else self.accounts_table
        self.tabs.setCurrentWidget(table)
        if result.table == "entries":
            row = self.entries_model.row_of(result.row_id)
        else:
            row = self.accounts_model.row_of("group" if result.table == "groups" else "account", result.row_id)
        self._select_cell(table, max(current_row, 0) if row is None else row)

    def sort_entries(self) -> None:
        self._commit_edits()
        with self._saving():
            self.book.sort_entries_by_date()
            self.entries_model.reload()
            self._update_summary()

    # -- Navigation ----------------------------------------------------

    def _tab_changed(self, _index: int) -> None:
        self._commit_edits()
        self._refresh_current()
        if self.book is not None:
            self._focus_current_table()

    def _refresh_current(self) -> None:
        if self.book is None or self.entries_model is None:
            return
        page = self.tabs.currentWidget()
        if page is self.entries_table:
            self.entries_model.reload()
        elif page is self.accounts_table:
            self.accounts_model.reload()
        elif isinstance(page, ReportPage):
            page.refresh()

    def _follow_link(self, link: str) -> None:
        kind, _, value = link.partition(":")
        if kind == "account":
            self.show_statement(int(value))
        elif kind == "entry":
            self.show_entry(int(value))

    def show_statement(self, account_id: int) -> None:
        self.tabs.setCurrentWidget(self.statement_page)
        self.statement_page.show_account(account_id)

    def show_entry(self, entry_id: int) -> None:
        self.tabs.setCurrentWidget(self.entries_table)
        row = self.entries_model.row_of(entry_id)
        if row is not None:
            index = self.entries_model.index(row, EntriesModel.TEXT)
            self.entries_table.setCurrentIndex(index)
            self.entries_table.scrollTo(index)
            self.entries_table.setFocus()

    def _account_double_clicked(self, index) -> None:
        if index.column() == AccountsModel.BALANCE:
            account = self.accounts_model.account_at(index.row())
            if account:
                self.show_statement(account.id)

    def about(self) -> None:
        StartDialog(self, auto_close=False).exec()

    def closeEvent(self, event) -> None:
        self._close_book()
        super().closeEvent(event)
