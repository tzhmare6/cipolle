"""Spielt die Oberfläche ohne Bildschirm durch."""

import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QLocale, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from cipolle import reports
from cipolle.__main__ import configure
from cipolle.book import Book
from cipolle.templates import KMU_CHART
from cipolle.ui.main_window import MainWindow
from cipolle.ui.models import AccountsModel, EntriesModel
from cipolle.ui.report_page import write_pdf


@pytest.fixture(scope="session")
def app():
    instance = QApplication.instance() or QApplication([])
    QCoreApplication.setOrganizationName("CipolleTest")
    QCoreApplication.setApplicationName("CipolleTest")
    return instance


@pytest.fixture
def window(app, tmp_path):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    main = MainWindow()
    main.show()
    main.create_path(tmp_path / "a.cipolle", "Muster", date(2026, 1, 1), date(2026, 12, 31), KMU_CHART)
    app.processEvents()
    yield main
    main.close()


def press(editor, key):
    """Sendet die Taste dorthin, wo sie auch am Bildschirm ankommt."""
    QTest.keyClick(QApplication.activePopupWidget() or editor, key)


def type_field(app, table, value, key=Qt.Key.Key_Return):
    if table.state() != table.State.EditingState:
        QTest.keyClick(table, Qt.Key.Key_Return)
    app.processEvents()
    editor = QApplication.focusWidget()
    assert isinstance(editor, QLineEdit), editor
    editor.selectAll()
    QTest.keyClicks(editor, value)
    app.processEvents()
    press(editor, key)
    app.processEvents()


def type_row(app, table, values, key=Qt.Key.Key_Return):
    for value in values:
        type_field(app, table, value, key)


def test_keyboard_entry_runs_through_rows(app, window):
    table = window.entries_table
    table.setFocus()
    type_row(app, table, ["15.1", "B1", "Honorar", "1020", "3000", "1'500.50"])
    type_row(app, table, ["31.3", "B2", "Miete", "6000", "1020", "400"])
    entries = window.book.entries()
    assert len(entries) == 2
    assert entries[0].date == date(2026, 1, 15)
    assert entries[0].amount == 150050
    assert entries[1].text == "Miete"
    assert window.book.warnings() == []
    assert "2 Buchungen" in window.summary.text()


def test_tab_with_open_suggestions_moves_one_field(app, window):
    table = window.entries_table
    table.setFocus()
    type_row(app, table, ["15.1", "B1", "Honorar", "1020", "3000", "10"], Qt.Key.Key_Tab)
    assert window.book.entries()[0].amount == 1000
    assert (table.currentIndex().row(), table.currentIndex().column()) == (1, 0)


def test_highlighted_suggestion_is_taken(app, window):
    table = window.entries_table
    table.setCurrentIndex(window.entries_model.index(0, EntriesModel.DEBIT))
    table.setFocus()
    QTest.keyClick(table, Qt.Key.Key_Return)
    app.processEvents()
    editor = QApplication.focusWidget()
    QTest.keyClicks(editor, "kasse")
    app.processEvents()
    popup = QApplication.activePopupWidget()
    assert popup is not None
    QTest.keyClick(popup, Qt.Key.Key_Down)
    QTest.keyClick(popup, Qt.Key.Key_Return)
    app.processEvents()
    assert window.book.entries()[0].debit_id == window.book.account_by_number("1000").id
    assert table.currentIndex().column() == EntriesModel.CREDIT


def test_invalid_field_stays_open_for_correction(app, window):
    table = window.entries_table
    table.setCurrentIndex(window.entries_model.index(0, EntriesModel.AMOUNT))
    table.setFocus()
    type_field(app, table, "abc")
    assert table.state() == table.State.EditingState
    assert table.currentIndex().column() == EntriesModel.AMOUNT
    assert window.book.entries() == []
    type_field(app, table, "12")
    assert window.book.entries()[0].amount == 1200
    assert (table.currentIndex().row(), table.currentIndex().column()) == (1, 0)


def open_editor_with(app, window, text):
    table = window.entries_table
    table.setCurrentIndex(window.entries_model.index(0, EntriesModel.TEXT))
    table.setFocus()
    QTest.keyClick(table, Qt.Key.Key_Return)
    app.processEvents()
    QTest.keyClicks(QApplication.focusWidget(), text)


def test_closing_with_open_field_saves_it(app, window):
    path = window.book.path
    open_editor_with(app, window, "Noch offen")
    window.close()
    saved = Book.open(path, backup=False)
    assert [e.text for e in saved.entries()] == ["Noch offen"]
    saved.close()


def test_switching_tab_with_open_field_saves_it(app, window):
    window.book.add_entry(text="alt")
    window.entries_model.reload()
    open_editor_with(app, window, "neu")
    window.tabs.setCurrentWidget(window.balance_page)
    app.processEvents()
    assert [e.text for e in window.book.entries()] == ["neu"]


def test_invalid_input_keeps_value_and_shows_message(app, window):
    model = window.entries_model
    model.setData(model.index(0, EntriesModel.AMOUNT), "100")
    assert not model.setData(model.index(0, EntriesModel.AMOUNT), "abc")
    assert window.book.entries()[0].amount == 10000
    assert "Ungültiger Betrag" in window.statusBar().currentMessage()


def test_ambiguous_account_is_refused(app, window):
    model = window.entries_model
    assert not model.setData(model.index(0, EntriesModel.DEBIT), "10")
    assert window.book.entries() == []
    assert "nicht eindeutig" in window.statusBar().currentMessage()


def test_empty_blank_row_creates_nothing(app, window):
    model = window.entries_model
    assert not model.setData(model.index(0, EntriesModel.TEXT), "")
    assert window.book.entries() == []


def test_new_row_takes_previous_date(app, window):
    model = window.entries_model
    model.setData(model.index(0, EntriesModel.DATE), "5.5")
    model.setData(model.index(1, EntriesModel.TEXT), "Zweite")
    assert window.book.entries()[1].date == date(2026, 5, 5)


def test_problem_rows_show_tooltip(app, window):
    model = window.entries_model
    model.setData(model.index(0, EntriesModel.DATE), "5.5.2025")
    tooltip = model.index(0, 0).data(Qt.ItemDataRole.ToolTipRole)
    assert "ausserhalb" in tooltip
    assert model.index(0, 0).data(Qt.ItemDataRole.BackgroundRole) is not None


def test_insert_and_delete_rows(app, window):
    model = window.entries_model
    model.setData(model.index(0, EntriesModel.TEXT), "A")
    model.setData(model.index(1, EntriesModel.TEXT), "B")
    model.insert_before(1)
    assert [e.text for e in window.book.entries()] == ["A", "", "B"]
    assert model.rowCount() == 4
    model.delete_rows([0, 1])
    assert [e.text for e in window.book.entries()] == ["B"]
    assert model.rowCount() == 2


def test_new_account_flow(app, window):
    window.tabs.setCurrentWidget(window.accounts_table)
    model = window.accounts_model
    blank = model.rowCount() - 1
    assert model.setData(model.index(blank, AccountsModel.NUMBER), "1025")
    assert model.setData(model.index(blank, AccountsModel.NAME), "Sparkonto")
    assert model.setData(model.index(blank, AccountsModel.OPENING), "1000")
    account = window.book.account_by_number("1025")
    assert (account.name, account.klass, account.group, account.opening) == ("Sparkonto", 1, "100", 100000)
    assert model.rows[-1].item.number == "1025"
    model.reload()
    assert model.account_at(2).number == "1025"


def test_new_group_flow(app, window):
    model = window.accounts_model
    blank = model.rowCount() - 1
    assert model.setData(model.index(blank, AccountsModel.GROUP), "105")
    assert model.setData(model.index(blank, AccountsModel.NAME), "Wertschriften")
    assert model.setData(model.index(blank, AccountsModel.SUM_IN), "10 Umlaufvermögen")
    assert window.book.group_by_code("105").parent == "10"
    row = model.row_of("account", window.book.account_by_number("1140").id)
    assert model.setData(model.index(row, AccountsModel.SUM_IN), "105")
    model.reload()
    row = model.row_of("group", window.book.group_by_code("105").id)
    assert model.index(row, AccountsModel.GROUP).data() == "105"
    assert model.index(row - 1, AccountsModel.NUMBER).data() == "1140"


def test_group_rows_show_totals(app, window):
    book = window.book
    book.update_account(book.account_by_number("1020").id, opening=5000)
    window.accounts_model.reload()
    model = window.accounts_model
    row = model.row_of("group", book.group_by_code("10").id)
    assert model.index(row, AccountsModel.BALANCE).data() == "50.00"
    assert model.index(row, AccountsModel.NAME).data() == "Umlaufvermögen"
    assert model.index(row, AccountsModel.SUM_IN).data() == "1"
    assert model.index(row, 0).data(Qt.ItemDataRole.FontRole).bold()


def test_group_row_edit_limits(app, window):
    model = window.accounts_model
    row = model.row_of("group", window.book.group_by_code("10").id)
    assert not model.index(row, AccountsModel.OPENING).flags() & Qt.ItemFlag.ItemIsEditable
    assert not model.index(row, AccountsModel.NUMBER).flags() & Qt.ItemFlag.ItemIsEditable
    profit = next(i for i, r in enumerate(model.rows) if r.kind == "profit")
    assert not model.index(profit, AccountsModel.NAME).flags() & Qt.ItemFlag.ItemIsEditable
    assert model.index(profit, AccountsModel.NAME).data() == "Jahresgewinn"


def test_unknown_sum_in_shows_message(app, window):
    model = window.accounts_model
    row = model.row_of("group", window.book.group_by_code("10").id)
    assert not model.setData(model.index(row, AccountsModel.SUM_IN), "XY")
    assert "nicht gefunden" in window.statusBar().currentMessage()


def test_deleting_used_group_shows_message(app, window):
    model = window.accounts_model
    model.delete_row(model.row_of("group", window.book.group_by_code("10").id))
    assert window.book.group_by_code("10") is not None
    assert "kann nicht gelöscht" in window.statusBar().currentMessage()


def test_new_group_and_account_by_keyboard_only(app, window):
    model = window.accounts_model
    table = window.accounts_table
    window.tabs.setCurrentWidget(table)
    table.setCurrentIndex(model.index(model.rowCount() - 1, AccountsModel.GROUP))
    table.setFocus()
    type_row(app, table, ["105", "Wertschriften", "10"], Qt.Key.Key_Tab)
    group = window.book.group_by_code("105")
    assert (group.name, group.parent) == ("Wertschriften", "10")
    assert (table.currentIndex().column()) == AccountsModel.GROUP
    table.commit_open_editor()
    table.setCurrentIndex(model.index(model.rowCount() - 1, AccountsModel.NUMBER))
    type_row(app, table, ["1060", "Depot"], Qt.Key.Key_Tab)
    assert table.currentIndex().column() == AccountsModel.KLASS
    table.commit_open_editor()
    assert window.book.account_by_number("1060").name == "Depot"


def test_backtab_returns_to_previous_field(app, window):
    table = window.entries_table
    table.setCurrentIndex(window.entries_model.index(0, EntriesModel.TEXT))
    table.setFocus()
    type_field(app, table, "x", Qt.Key.Key_Backtab)
    assert table.currentIndex().column() == EntriesModel.DOC


def test_keyboard_entry_in_sum_in_column(app, window):
    model = window.accounts_model
    table = window.accounts_table
    window.tabs.setCurrentWidget(table)
    row = model.row_of("account", window.book.account_by_number("1140").id)
    table.setCurrentIndex(model.index(row, AccountsModel.SUM_IN))
    table.setFocus()
    type_field(app, table, "100")
    assert window.book.account_by_number("1140").group == "100"


def test_opening_not_editable_on_income_accounts(app, window):
    model = window.accounts_model
    row = model.row_of("account", window.book.account_by_number("6000").id)
    flags = model.index(row, AccountsModel.OPENING).flags()
    assert not flags & Qt.ItemFlag.ItemIsEditable


def test_deleting_used_account_shows_message(app, window):
    book = window.book
    book.add_entry(date=date(2026, 1, 1), debit_id=book.account_by_number("1020").id, amount=1)
    model = window.accounts_model
    row = model.row_of("account", book.account_by_number("1020").id)
    model.delete_row(row)
    assert book.account_by_number("1020") is not None
    assert "kann nicht gelöscht" in window.statusBar().currentMessage()


def test_reports_refresh_and_links_navigate(app, window):
    book = window.book
    bank = book.account_by_number("1020")
    entry = book.add_entry(
        date=date(2026, 1, 1), text="Honorar", debit_id=bank.id,
        credit_id=book.account_by_number("3000").id, amount=12345,
    )
    window.tabs.setCurrentWidget(window.balance_page)
    assert "123.45" in window.balance_page.view.toPlainText()
    window._follow_link(f"account:{bank.id}")
    assert window.tabs.currentWidget() is window.statement_page
    assert window.statement_page.account.currentData() == bank.id
    assert "Honorar" in window.statement_page.view.toPlainText()
    window._follow_link(f"entry:{entry}")
    assert window.tabs.currentWidget() is window.entries_table
    assert window.entries_table.currentIndex().row() == 0


def test_statement_picks_up_new_account(app, window):
    window.book.add_account("1999", "Neu", 1)
    window.tabs.setCurrentWidget(window.statement_page)
    labels = [window.statement_page.account.itemText(i) for i in range(window.statement_page.account.count())]
    assert "1999 Neu" in labels


def test_next_year_switches_to_new_file(app, window, tmp_path):
    book = window.book
    book.update_account(book.account_by_number("1020").id, opening=500)
    book.update_account(book.account_by_number("2800").id, opening=500)
    window.create_next_year_at(tmp_path / "b.cipolle", "2970")
    assert window.book.start == date(2027, 1, 1)
    assert window.book.account_by_number("1020").opening == 500
    assert "2027" in window.windowTitle()


def test_open_invalid_path_keeps_current_book(app, window, tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr("cipolle.ui.main_window.QMessageBox.warning", lambda *a: shown.append(a[2]))
    current = window.book
    window.open_path(tmp_path / "fehlt.cipolle")
    assert window.book is current
    assert "nicht gefunden" in shown[0]


def test_pdf_export_writes_file(app, window, tmp_path):
    path = tmp_path / "bilanz.pdf"
    write_pdf(reports.balance_sheet(window.book, show_zero=True), path)
    assert path.read_bytes().startswith(b"%PDF")


def test_application_setup_runs(app):
    name, organization = app.applicationName(), app.organizationName()
    configure(app)
    assert QLocale().name() == "de_CH"
    app.setApplicationName(name)
    app.setOrganizationName(organization)


def test_values_survive_reopen(app, window, tmp_path):
    model = window.entries_model
    model.setData(model.index(0, EntriesModel.TEXT), "Bleibt")
    path = window.book.path
    window.open_path(path)
    assert [e.text for e in window.book.entries()] == ["Bleibt"]
    copy = Book.open(path, backup=False)
    assert copy.company == "Muster"
    copy.close()
