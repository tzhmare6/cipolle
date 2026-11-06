"""Spielt die Oberfläche ohne Bildschirm durch."""

import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QItemSelectionModel, QLocale, QObject, QPoint, QSettings, Qt
from PySide6.QtGui import QFileOpenEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QLineEdit, QMessageBox

from cipolle import __version__, reports
from cipolle.__main__ import CipolleApplication, configure, report_unexpected_error
from cipolle.book import Book
from cipolle.templates import KMU_CHART
from cipolle.ui import branding
from cipolle.ui.branding import ICON_SIZES, StartDialog, app_icon
from cipolle.ui.dialogs import ImportDialog
from cipolle.ui.main_window import MainWindow
from cipolle.ui.models import AccountsModel, EntriesModel
from cipolle.ui.report_page import ReportPage, write_pdf


@pytest.fixture(scope="session")
def app():
    instance = QApplication.instance() or CipolleApplication([])
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
    main.tabs.setCurrentWidget(main.entries_table)
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
    model.delete_rows([model.row_of("group", window.book.group_by_code("10").id)])
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


@pytest.fixture
def answer_yes(monkeypatch):
    asked = []

    def question(_parent, _title, text):
        asked.append(text)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr("cipolle.ui.main_window.QMessageBox.question", question)
    return asked


def account_row(window, number):
    return window.accounts_model.row_of("account", window.book.account_by_number(number).id)


def fill_entries(window, *texts):
    model = window.entries_model
    for row, text in enumerate(texts):
        model.setData(model.index(row, EntriesModel.TEXT), text)


def click_row_number(app, table, row):
    header = table.verticalHeader()
    QTest.mouseClick(header.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(5, header.sectionViewportPosition(row) + 5))
    app.processEvents()


def test_both_tables_show_row_numbers(app, window):
    fill_entries(window, "A")
    for table in (window.entries_table, window.accounts_table):
        window.tabs.setCurrentWidget(table)
        app.processEvents()
        model = table.model()
        assert table.verticalHeader().isVisible()
        assert model.headerData(0, Qt.Orientation.Vertical) == "1"
        assert model.headerData(model.rowCount() - 1, Qt.Orientation.Vertical) == "*"


def test_click_on_row_number_selects_whole_row(app, window):
    table = window.accounts_table
    window.tabs.setCurrentWidget(table)
    app.processEvents()
    click_row_number(app, table, 2)
    assert [index.row() for index in table.selectionModel().selectedRows()] == [2]


def test_delete_key_clears_entry_cell(app, window):
    fill_entries(window, "A")
    table = window.entries_table
    model = window.entries_model
    model.setData(model.index(0, EntriesModel.AMOUNT), "10")
    table.setCurrentIndex(model.index(0, EntriesModel.AMOUNT))
    table.setFocus()
    QTest.keyClick(table, Qt.Key.Key_Delete)
    entry = window.book.entries()[0]
    assert entry.amount is None
    assert entry.text == "A"


def test_delete_key_clears_several_cells(app, window):
    fill_entries(window, "A", "B")
    table = window.entries_table
    model = window.entries_model
    table.selectionModel().select(model.index(0, EntriesModel.TEXT), QItemSelectionModel.SelectionFlag.Select)
    table.selectionModel().select(model.index(1, EntriesModel.TEXT), QItemSelectionModel.SelectionFlag.Select)
    QTest.keyClick(table, Qt.Key.Key_Delete)
    assert [e.text for e in window.book.entries()] == ["", ""]


def test_delete_key_clears_account_cells(app, window):
    table = window.accounts_table
    model = window.accounts_model
    window.tabs.setCurrentWidget(table)
    row = account_row(window, "1020")
    model.setData(model.index(row, AccountsModel.OPENING), "100")
    for column in (AccountsModel.NAME, AccountsModel.SUM_IN, AccountsModel.OPENING):
        table.setCurrentIndex(model.index(row, column))
        QTest.keyClick(table, Qt.Key.Key_Delete)
    account = window.book.account_by_number("1020")
    assert (account.name, account.group, account.opening) == ("", "", 0)


def test_delete_key_keeps_required_account_fields(app, window):
    table = window.accounts_table
    model = window.accounts_model
    window.tabs.setCurrentWidget(table)
    row = account_row(window, "1020")
    table.setCurrentIndex(model.index(row, AccountsModel.NUMBER))
    QTest.keyClick(table, Qt.Key.Key_Delete)
    assert window.book.account_by_number("1020") is not None
    assert "darf nicht leer" in window.statusBar().currentMessage()
    table.setCurrentIndex(model.index(row, AccountsModel.KLASS))
    QTest.keyClick(table, Qt.Key.Key_Delete)
    assert window.book.account_by_number("1020").klass == 1


def test_delete_key_on_marked_row_deletes_entry(app, window, answer_yes):
    fill_entries(window, "A", "B", "C")
    table = window.entries_table
    app.processEvents()
    click_row_number(app, table, 1)
    QTest.keyClick(table, Qt.Key.Key_Delete)
    assert [e.text for e in window.book.entries()] == ["A", "C"]
    assert answer_yes == ["Diese Buchung löschen?"]
    assert table.currentIndex().row() == 1


def test_declined_question_keeps_row(app, window, monkeypatch):
    fill_entries(window, "A")
    monkeypatch.setattr(
        "cipolle.ui.main_window.QMessageBox.question", lambda *a: QMessageBox.StandardButton.No
    )
    table = window.entries_table
    table.selectRow(0)
    QTest.keyClick(table, Qt.Key.Key_Delete)
    assert len(window.book.entries()) == 1


def test_delete_key_on_marked_row_deletes_account(app, window, answer_yes):
    table = window.accounts_table
    window.tabs.setCurrentWidget(table)
    app.processEvents()
    table.selectRow(account_row(window, "1000"))
    QTest.keyClick(table, Qt.Key.Key_Delete)
    assert window.book.account_by_number("1000") is None
    assert "Konto 1000 Kasse löschen?" in answer_yes


def test_group_and_its_accounts_can_be_deleted_together(app, window, answer_yes):
    table = window.accounts_table
    model = window.accounts_model
    window.tabs.setCurrentWidget(table)
    group_row = model.row_of("group", window.book.group_by_code("130").id)
    table.selectRow(group_row - 1)
    table.selectionModel().select(
        model.index(group_row, 0),
        QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
    )
    window.delete_rows()
    assert window.book.group_by_code("130") is None
    assert window.book.account_by_number("1300") is None


def test_profit_row_cannot_be_deleted(app, window, answer_yes):
    table = window.accounts_table
    model = window.accounts_model
    window.tabs.setCurrentWidget(table)
    table.selectRow(next(i for i, r in enumerate(model.rows) if r.kind == "profit"))
    window.delete_rows()
    assert answer_yes == []
    assert any(r.kind == "profit" for r in model.rows)


def test_insert_shortcut_stays_on_accounts_tab(app, window):
    table = window.accounts_table
    model = window.accounts_model
    window.tabs.setCurrentWidget(table)
    row = account_row(window, "1020")
    table.setCurrentIndex(model.index(row, AccountsModel.NAME))
    window.insert_row()
    assert window.tabs.currentWidget() is table
    assert model.row_at(row).kind == "blank"
    assert table.currentIndex().row() == row
    assert table.currentIndex().column() == AccountsModel.NUMBER
    assert model.account_at(row + 1).number == "1020"


def test_account_in_inserted_row_joins_group_at_that_place(app, window):
    table = window.accounts_table
    model = window.accounts_model
    window.tabs.setCurrentWidget(table)
    row = account_row(window, "1500")
    table.setCurrentIndex(model.index(row, AccountsModel.NUMBER))
    window.insert_row()
    table.setFocus()
    type_row(app, table, ["1505", "Neue Anlage"], Qt.Key.Key_Tab)
    table.commit_open_editor()
    account = window.book.account_by_number("1505")
    assert (account.name, account.group) == ("Neue Anlage", "150")
    assert model.account_at(row).number == "1500"
    assert model.account_at(row + 1).number == "1505"


def test_row_inserted_above_group_total_belongs_to_that_group(app, window):
    model = window.accounts_model
    row = model.row_of("group", window.book.group_by_code("100").id)
    model.insert_before(row)
    assert model.setData(model.index(row, AccountsModel.NUMBER), "1010")
    assert window.book.account_by_number("1010").group == "100"


def test_group_in_inserted_row_sums_into_surrounding_group(app, window):
    model = window.accounts_model
    row = model.row_of("group", window.book.group_by_code("10").id)
    model.insert_before(row)
    assert model.setData(model.index(row, AccountsModel.GROUP), "135")
    assert window.book.group_by_code("135").parent == "10"


def test_empty_inserted_row_goes_without_question(app, window, answer_yes):
    table = window.accounts_table
    model = window.accounts_model
    window.tabs.setCurrentWidget(table)
    count = model.rowCount()
    model.insert_before(3)
    table.selectRow(3)
    window.delete_rows()
    assert answer_yes == []
    assert model.rowCount() == count


def test_inserted_row_survives_edits_elsewhere(app, window):
    model = window.accounts_model
    model.insert_before(3)
    assert model.setData(model.index(0, AccountsModel.NAME), "Handkasse")
    assert model.row_at(3).kind == "blank"
    blank = model.rowCount() - 1
    assert model.setData(model.index(blank, AccountsModel.NUMBER), "1999")
    assert model.row_at(3).kind == "blank"
    assert model.account_at(blank).number == "1999"


def test_changing_sum_in_moves_account_at_once(app, window):
    table = window.accounts_table
    model = window.accounts_model
    window.tabs.setCurrentWidget(table)
    table.setCurrentIndex(model.index(account_row(window, "1140"), AccountsModel.SUM_IN))
    table.setFocus()
    type_field(app, table, "100", Qt.Key.Key_Tab)
    target = model.row_of("group", window.book.group_by_code("100").id)
    assert account_row(window, "1140") == target - 1
    assert model.index(target, AccountsModel.BALANCE).data() == "0.00"
    assert table.currentIndex().row() == account_row(window, "1140")
    assert table.currentIndex().column() == AccountsModel.OPENING
    table.commit_open_editor()


def test_changing_group_parent_moves_group_with_its_accounts(app, window):
    table = window.accounts_table
    model = window.accounts_model
    window.tabs.setCurrentWidget(table)
    row = model.row_of("group", window.book.group_by_code("130").id)
    table.setCurrentIndex(model.index(row, AccountsModel.SUM_IN))
    table.setFocus()
    type_field(app, table, "14")
    table.commit_open_editor()
    moved = model.row_of("group", window.book.group_by_code("130").id)
    assert moved > model.row_of("group", window.book.group_by_code("10").id)
    assert account_row(window, "1300") == moved - 1


def test_changing_group_code_reorders(app, window):
    table = window.accounts_table
    model = window.accounts_model
    window.tabs.setCurrentWidget(table)
    group = window.book.group_by_code("130")
    table.setCurrentIndex(model.index(model.row_of("group", group.id), AccountsModel.GROUP))
    table.setFocus()
    type_field(app, table, "105")
    table.commit_open_editor()
    assert model.row_of("group", group.id) < model.row_of("group", window.book.group_by_code("110").id)


def test_changing_account_number_reorders(app, window):
    table = window.accounts_table
    model = window.accounts_model
    window.tabs.setCurrentWidget(table)
    table.setCurrentIndex(model.index(account_row(window, "1530"), AccountsModel.NUMBER))
    table.setFocus()
    type_field(app, table, "1505")
    table.commit_open_editor()
    assert account_row(window, "1505") == account_row(window, "1500") + 1


def test_new_account_in_last_row_moves_to_its_place(app, window):
    table = window.accounts_table
    model = window.accounts_model
    window.tabs.setCurrentWidget(table)
    table.setCurrentIndex(model.index(model.rowCount() - 1, AccountsModel.NUMBER))
    table.setFocus()
    type_row(app, table, ["1025", "Sparkonto"], Qt.Key.Key_Tab)
    table.commit_open_editor()
    assert account_row(window, "1025") == account_row(window, "1020") + 1
    assert window.book.account_by_number("1025").name == "Sparkonto"


def test_click_away_after_editing_reorders_and_keeps_new_cursor(app, window):
    table = window.accounts_table
    model = window.accounts_model
    window.tabs.setCurrentWidget(table)
    table.setCurrentIndex(model.index(account_row(window, "1140"), AccountsModel.SUM_IN))
    table.setFocus()
    QTest.keyClick(table, Qt.Key.Key_Return)
    app.processEvents()
    QApplication.focusWidget().setText("100")
    other = model.index(account_row(window, "2000"), AccountsModel.NAME)
    table.setCurrentIndex(other)
    app.processEvents()
    assert window.book.account_by_number("1140").group == "100"
    assert account_row(window, "1140") < model.row_of("group", window.book.group_by_code("100").id)
    assert table.currentIndex().row() == account_row(window, "2000")


def test_tabbing_through_unchanged_field_does_not_reorder(app, window):
    model = window.accounts_model
    row = account_row(window, "1140")
    assert model.setData(model.index(row, AccountsModel.SUM_IN), "114")
    assert not model.needs_resort


def test_name_change_does_not_reorder(app, window):
    model = window.accounts_model
    assert model.setData(model.index(0, AccountsModel.NAME), "Handkasse")
    assert not model.needs_resort


def test_inserted_row_survives_reordering(app, window):
    table = window.accounts_table
    model = window.accounts_model
    window.tabs.setCurrentWidget(table)
    model.insert_before(account_row(window, "1510"))
    table.setCurrentIndex(model.index(account_row(window, "1140"), AccountsModel.SUM_IN))
    table.setFocus()
    type_field(app, table, "100")
    table.commit_open_editor()
    assert model.row_at(account_row(window, "1510") - 1).kind == "blank"


def test_closing_right_after_structural_edit_is_safe(app, window):
    path = window.book.path
    model = window.accounts_model
    model.setData(model.index(account_row(window, "1140"), AccountsModel.SUM_IN), "100")
    window.close()
    app.processEvents()
    saved = Book.open(path, backup=False)
    assert saved.account_by_number("1140").group == "100"
    saved.close()


def test_insert_on_entries_via_row_menu(app, window):
    fill_entries(window, "A", "B")
    table = window.entries_table
    table.selectRow(1)
    menu = table.row_menu()
    assert [action.text() for action in menu.actions()] == [
        "Zeile einfügen oben", "Zeile einfügen unten", "Zeile löschen",
    ]
    menu.actions()[0].trigger()
    assert [e.text for e in window.book.entries()] == ["A", "", "B"]
    assert table.currentIndex().row() == 1


def test_insert_below_on_entries(app, window):
    fill_entries(window, "A", "B")
    table = window.entries_table
    table.selectRow(0)
    table.row_menu().actions()[1].trigger()
    assert [e.text for e in window.book.entries()] == ["A", "", "B"]
    assert table.currentIndex().row() == 1


def test_insert_below_last_entry(app, window):
    fill_entries(window, "A")
    window.entries_model.setData(window.entries_model.index(0, EntriesModel.DATE), "5.5")
    table = window.entries_table
    table.selectRow(0)
    window.insert_row(below=True)
    entries = window.book.entries()
    assert [e.text for e in entries] == ["A", ""]
    assert entries[1].date == date(2026, 5, 5)
    assert table.currentIndex().row() == 1
    assert window.entries_model.rowCount() == 3


def test_insert_below_uses_last_of_several_rows(app, window):
    fill_entries(window, "A", "B", "C")
    table = window.entries_table
    flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
    table.selectionModel().select(window.entries_model.index(0, 0), flags)
    table.selectionModel().select(window.entries_model.index(1, 0), flags)
    window.insert_row(below=True)
    assert [e.text for e in window.book.entries()] == ["A", "B", "", "C"]


def test_insert_below_account_stays_in_its_group(app, window):
    table = window.accounts_table
    model = window.accounts_model
    window.tabs.setCurrentWidget(table)
    row = account_row(window, "1000")
    table.selectRow(row)
    table.row_menu().actions()[1].trigger()
    assert model.row_at(row + 1).kind == "blank"
    assert table.currentIndex().row() == row + 1
    assert table.currentIndex().column() == AccountsModel.NUMBER
    assert model.setData(model.index(row + 1, AccountsModel.NUMBER), "1010")
    assert window.book.account_by_number("1010").group == "100"


def test_insert_below_group_total_lies_outside_that_group(app, window):
    model = window.accounts_model
    row = model.row_of("group", window.book.group_by_code("100").id)
    model.insert_after(row)
    assert model.setData(model.index(row + 1, AccountsModel.GROUP), "105")
    assert window.book.group_by_code("105").parent == "10"


def test_insert_above_on_empty_last_row_does_nothing(app, window):
    table = window.entries_table
    table.selectRow(0)
    window.insert_row()
    window.insert_row(below=True)
    assert window.book.entries() == []


def test_edit_menu_offers_both_insert_commands(app, window):
    labels = [a.text().replace("&", "") for a in window.book_actions]
    assert "Zeile einfügen oben" in labels
    assert "Zeile einfügen unten" in labels


def test_undo_menu_names_the_action(app, window):
    assert not window.undo_action.isEnabled()
    assert not window.redo_action.isEnabled()
    fill_entries(window, "A")
    assert window.undo_action.isEnabled()
    assert window.undo_action.text() == "Rückgängig: Buchung anlegen"
    window.undo()
    assert window.undo_action.text() == "Rückgängig"
    assert window.redo_action.text() == "Wiederholen: Buchung anlegen"
    assert "Rückgängig: Buchung anlegen" in window.statusBar().currentMessage()


def test_undo_restores_deleted_row_and_selects_it(app, window, answer_yes):
    fill_entries(window, "A", "B", "C")
    table = window.entries_table
    table.selectRow(1)
    window.delete_rows()
    assert [e.text for e in window.book.entries()] == ["A", "C"]
    window.undo()
    assert [e.text for e in window.book.entries()] == ["A", "B", "C"]
    assert window.entries_model.rowCount() == 4
    assert table.currentIndex().row() == 1
    window.redo()
    assert [e.text for e in window.book.entries()] == ["A", "C"]


def test_undo_deletes_several_rows_in_one_step(app, window, answer_yes):
    fill_entries(window, "A", "B", "C")
    table = window.entries_table
    table.selectAll()
    window.delete_rows()
    assert window.book.entries() == []
    window.undo()
    assert len(window.book.entries()) == 3


def test_clearing_cells_is_one_step(app, window):
    fill_entries(window, "A", "B")
    table = window.entries_table
    model = window.entries_model
    flag = QItemSelectionModel.SelectionFlag.Select
    table.selectionModel().select(model.index(0, EntriesModel.TEXT), flag)
    table.selectionModel().select(model.index(1, EntriesModel.TEXT), flag)
    QTest.keyClick(table, Qt.Key.Key_Delete)
    assert window.undo_action.text() == "Rückgängig: Zellen leeren"
    window.undo()
    assert [e.text for e in window.book.entries()] == ["A", "B"]


def test_undo_in_chart_moves_account_back_and_selects_it(app, window):
    table = window.accounts_table
    model = window.accounts_model
    window.tabs.setCurrentWidget(table)
    original = account_row(window, "1140")
    table.setCurrentIndex(model.index(original, AccountsModel.SUM_IN))
    table.setFocus()
    type_field(app, table, "100")
    table.commit_open_editor()
    app.processEvents()
    assert window.book.account_by_number("1140").group == "100"
    window.undo()
    assert window.book.account_by_number("1140").group == "114"
    assert account_row(window, "1140") == original
    assert table.currentIndex().row() == original


def test_undo_switches_to_the_table_concerned(app, window):
    fill_entries(window, "A")
    window.tabs.setCurrentWidget(window.accounts_table)
    window.undo()
    assert window.tabs.currentWidget() is window.entries_table


def test_undo_on_report_tab_stays_and_refreshes(app, window):
    book = window.book
    book.add_entry(
        date=date(2026, 1, 1), debit_id=book.account_by_number("1020").id,
        credit_id=book.account_by_number("3000").id, amount=12345,
    )
    window.tabs.setCurrentWidget(window.balance_page)
    assert "123.45" in window.balance_page.view.toPlainText()
    window.undo()
    assert window.tabs.currentWidget() is window.balance_page
    assert "123.45" not in window.balance_page.view.toPlainText()


def test_undo_commits_open_field_first(app, window):
    fill_entries(window, "A")
    open_editor_with(app, window, "neu")
    window.undo()
    assert [e.text for e in window.book.entries()] == ["A"]


def test_undo_of_properties_updates_title(app, window):
    window.book.set_properties("Neu AG", date(2026, 1, 1), date(2026, 12, 31))
    window.undo()
    assert window.windowTitle().startswith("Muster ")


def test_tabbing_through_fields_adds_no_undo_steps(app, window):
    fill_entries(window, "A")
    table = window.entries_table
    table.setCurrentIndex(window.entries_model.index(0, EntriesModel.DOC))
    table.setFocus()
    QTest.keyClick(table, Qt.Key.Key_Return)
    app.processEvents()
    press(QApplication.focusWidget(), Qt.Key.Key_Tab)
    press(QApplication.focusWidget(), Qt.Key.Key_Tab)
    app.processEvents()
    table.commit_open_editor()
    assert window.book.db.execute("SELECT count(*) FROM undo_steps").fetchone()[0] == 1


def test_close_file_returns_to_welcome_page(app, window):
    path = window.book.path
    fill_entries(window, "Bleibt")
    window.close_book()
    assert window.book is None
    assert window.stack.currentIndex() == 0
    assert window.windowTitle() == "Cipolle"
    assert window.summary.text() == ""
    assert not any(action.isEnabled() for action in window.book_actions)
    assert not window.undo_action.isEnabled()
    window.open_path(path)
    assert [e.text for e in window.book.entries()] == ["Bleibt"]
    assert window.stack.currentIndex() == 1
    assert all(action.isEnabled() for action in window.book_actions)


def test_close_file_saves_open_field(app, window):
    path = window.book.path
    open_editor_with(app, window, "Noch offen")
    window.close_book()
    window.open_path(path)
    assert [e.text for e in window.book.entries()] == ["Noch offen"]


def test_close_file_right_after_structural_edit_is_safe(app, window):
    model = window.accounts_model
    model.setData(model.index(account_row(window, "1140"), AccountsModel.SUM_IN), "100")
    window.close_book()
    app.processEvents()
    assert window.book is None


def test_closing_window_after_file_close_is_safe(app, window):
    window.close_book()
    window.close()
    assert window.book is None


def test_closed_file_stays_in_recent_list(app, window):
    path = str(window.book.path.resolve())
    window.close_book()
    assert window.recent_menu.actions()[0].text() == path


def restart(app):
    main = MainWindow()
    main.show()
    main.open_initial(None)
    app.processEvents()
    return main


def test_quitting_with_open_file_reopens_it(app, window):
    path = window.book.path
    window.close()
    main = restart(app)
    assert main.book.path == path
    main.close()


def test_start_after_closing_file_shows_welcome_page(app, window):
    window.close_book()
    window.close()
    main = restart(app)
    assert main.book is None
    assert main.stack.currentIndex() == 0
    main.close()


def test_opening_a_file_again_restores_reopening(app, window):
    path = window.book.path
    window.close_book()
    window.open_path(path)
    window.close()
    main = restart(app)
    assert main.book.path == path
    main.close()


def test_file_given_on_command_line_opens_after_closing(app, window):
    path = window.book.path
    window.close_book()
    window.close()
    main = MainWindow()
    main.open_initial(str(path))
    assert main.book.path == path
    main.close()


def test_chart_export_and_import_through_window(app, window, tmp_path):
    path = tmp_path / "plan.json"
    window.export_chart_to(path)
    assert "exportiert" in window.statusBar().currentMessage()
    book = window.book
    book.delete_account(book.account_by_number("1000").id)
    chart = window.read_chart(path)
    window.import_chart_data(chart, replace=False)
    assert book.account_by_number("1000").group == "100"
    assert window.tabs.currentWidget() is window.accounts_table
    assert window.undo_action.text() == "Rückgängig: Kontenplan importieren"
    assert account_row(window, "1000") == 0
    window.undo()
    assert book.account_by_number("1000") is None


def test_bad_chart_file_shows_warning(app, window, tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr("cipolle.ui.main_window.QMessageBox.warning", lambda *a: shown.append(a[2]))
    path = tmp_path / "x.json"
    path.write_bytes(b"\xff\xfe nichts")
    assert window.read_chart(path) is None
    assert window.read_chart(tmp_path / "fehlt.json") is None
    assert len(shown) == 2


def test_import_dialog_shows_what_changes(app, window):
    book = window.book
    chart = book.chart()
    book.add_account("1999", "Eigenes", 1, "100")
    dialog = ImportDialog(book, chart)
    ok = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert "Der Kontenplan entspricht bereits" in dialog.summary.text()
    assert not ok.isEnabled()
    dialog.replace.setChecked(True)
    assert "Konten: 0 neu, 0 geändert, 1 entfernt" in dialog.summary.text()
    assert ok.isEnabled()


def test_import_dialog_warns_about_used_accounts_and_openings(app, window):
    book = window.book
    chart = book.chart()
    used = book.add_account("1999", "Benutzt", 1, "100")
    book.add_entry(date=date(2026, 1, 1), debit_id=used, amount=1)
    book.add_account("1998", "Saldo", 1, "100", opening=500)
    dialog = ImportDialog(book, chart)
    dialog.replace.setChecked(True)
    assert "Bleiben, weil sie Buchungen haben: 1999" in dialog.summary.text()
    assert "Eröffnungssaldo geht verloren: 1998" in dialog.summary.text()


def test_tab_order_and_start_tab(app, window):
    labels = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert labels[:3] == ["Konten", "Buchungen", "Kontoauszug"]


def test_opening_a_file_focuses_the_chart(app, window):
    window.open_path(window.book.path)
    app.processEvents()
    table = window.accounts_table
    assert window.tabs.currentWidget() is table
    assert QApplication.focusWidget() is table
    assert table.currentIndex().row() == 0
    assert table.currentIndex().column() == AccountsModel.NUMBER


def test_switching_to_entries_lands_in_new_row(app, window):
    fill_entries(window, "A")
    window.tabs.setCurrentWidget(window.accounts_table)
    app.processEvents()
    window.tabs.setCurrentWidget(window.entries_table)
    app.processEvents()
    table = window.entries_table
    assert QApplication.focusWidget() is table
    assert table.currentIndex().row() == 1
    assert table.currentIndex().column() == EntriesModel.DATE


def test_switching_to_report_tab_is_safe(app, window):
    window.tabs.setCurrentWidget(window.balance_page)
    app.processEvents()
    assert window.tabs.currentWidget() is window.balance_page


def test_tab_shortcuts_follow_tab_order(app, window):
    view = next(a for a in window.menuBar().actions() if "Ansicht" in a.text()).menu()
    assert [(a.text(), a.shortcut().toString()) for a in view.actions()[:2]] == [
        ("Konten", "Ctrl+1"), ("Buchungen", "Ctrl+2"),
    ]
    view.actions()[0].trigger()
    assert window.tabs.currentWidget() is window.accounts_table


def test_row_menu_names_several_rows(app, window):
    fill_entries(window, "A", "B")
    table = window.entries_table
    table.selectAll()
    assert table.row_menu().actions()[2].text() == "2 Zeilen löschen"


def test_row_menu_is_disabled_on_the_empty_last_row(app, window):
    table = window.entries_table
    table.selectRow(0)
    assert not any(action.isEnabled() for action in table.row_menu().actions())


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
    model.delete_rows([row])
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


def test_app_icon_offers_every_size(app):
    assert {size.width() for size in app_icon().availableSizes()} == set(ICON_SIZES)


def backdrop_visible(widget):
    """Vergleicht die Fläche mit einem Bild ohne Filter: Das Logo färbt die Mitte."""
    image = widget.grab().toImage()
    center = image.pixelColor(image.width() // 2, image.height() // 2)
    return center != widget.palette().color(widget.backgroundRole())


def test_backdrop_shows_on_every_tab(app, window):
    for index in range(window.tabs.count()):
        window.tabs.setCurrentIndex(index)
        app.processEvents()
        page = window.tabs.currentWidget()
        view = page.view if isinstance(page, ReportPage) else page
        assert backdrop_visible(view.viewport()), window.tabs.tabText(index)


def test_backdrop_stays_in_place_while_scrolling(app, window):
    table = window.accounts_table
    window.tabs.setCurrentWidget(table)
    app.processEvents()
    bar = table.verticalScrollBar()
    assert bar.maximum() > 0
    repaints = []
    viewport = table.viewport()

    class Counter(QObject):
        def eventFilter(self, _widget, event):
            if event.type() == QEvent.Type.Paint:
                repaints.append(event.region().boundingRect().height())
            return False

    counter = Counter()
    viewport.installEventFilter(counter)
    bar.setValue(bar.value() + 1)
    app.processEvents()
    viewport.removeEventFilter(counter)
    assert viewport.height() in repaints


def test_start_dialog_names_version_and_authors(app):
    dialog = StartDialog()
    text = dialog.info.text()
    assert __version__ in text
    assert "Claude Opus" in text and "Remo Maurer" in text
    assert dialog.movie.isValid() and dialog.movie.frameCount() == 30


def test_start_dialog_closes_itself_after_the_animation(app, monkeypatch):
    monkeypatch.setattr(branding, "START_HOLD_MS", 0)
    dialog = StartDialog()
    dialog.show()
    QTest.qWait(3600)
    assert not dialog.isVisible()
    assert dialog.movie.currentFrameNumber() == dialog.movie.frameCount() - 1


def test_start_dialog_closes_on_key(app):
    dialog = StartDialog()
    dialog.show()
    QTest.keyClick(dialog, Qt.Key.Key_Space)
    assert not dialog.isVisible()


def test_about_dialog_stays_open(app):
    dialog = StartDialog(auto_close=False)
    dialog.show()
    dialog._frame_changed(dialog.movie.frameCount() - 1)
    QTest.mouseClick(dialog, Qt.MouseButton.LeftButton)
    app.processEvents()
    assert dialog.isVisible()
    dialog.close()


def block_writes(window, monkeypatch):
    """Lässt jedes Schreiben fehlschlagen, wie bei einer schreibgeschützten Datei."""
    shown = []
    monkeypatch.setattr("cipolle.ui.main_window.QMessageBox.warning", lambda *a: shown.append(a[2]))
    window.book.db.execute("PRAGMA query_only = ON")
    return shown


def add_entry(window):
    window.book.add_entry(text="Miete")
    window.entries_model.reload()
    window.entries_table.setCurrentIndex(window.entries_model.index(0, EntriesModel.TEXT))


def test_failed_save_warns_and_keeps_the_input_open(app, window, monkeypatch):
    shown = block_writes(window, monkeypatch)
    table = window.entries_table
    table.setCurrentIndex(window.entries_model.index(0, EntriesModel.TEXT))
    type_field(app, table, "Miete")
    app.processEvents()
    assert len(shown) == 1
    assert "nicht in die Datei geschrieben" in shown[0]
    assert table.state() == table.State.EditingState
    assert window.book.entries() == []
    # Das offene Feld wird beim Schliessen gespeichert und darf dann keinen Dialog mehr auslösen.
    window.book.db.execute("PRAGMA query_only = OFF")


def test_failed_account_save_warns(app, window, monkeypatch):
    shown = block_writes(window, monkeypatch)
    model = window.accounts_model
    row = account_row(window, "1020")
    assert not model.setData(model.index(row, AccountsModel.NAME), "Hausbank")
    app.processEvents()
    assert len(shown) == 1
    assert window.book.account_by_number("1020").name == "Bank"


def test_failed_row_actions_warn_and_keep_the_table(app, window, monkeypatch):
    add_entry(window)
    shown = block_writes(window, monkeypatch)
    window.insert_row()
    window.undo()
    window.sort_entries()
    assert len(shown) == 3
    assert window.entries_model.rowCount() == 2


def test_failed_delete_warns_and_keeps_the_row(app, window, monkeypatch, answer_yes):
    add_entry(window)
    shown = block_writes(window, monkeypatch)
    window.delete_rows()
    assert len(shown) == 1
    assert len(window.book.entries()) == 1


def test_failed_clearing_of_cells_warns(app, window, monkeypatch):
    add_entry(window)
    shown = block_writes(window, monkeypatch)
    QTest.keyClick(window.entries_table, Qt.Key.Key_Delete)
    app.processEvents()
    assert len(shown) == 1
    assert window.book.entries()[0].text == "Miete"


def test_unexpected_error_is_shown(app, monkeypatch):
    shown = []
    monkeypatch.setattr("cipolle.__main__.QMessageBox.critical", lambda *a: shown.append(a[2]))
    report_unexpected_error(ValueError, ValueError("kaputt"), None)
    assert "kaputt" in shown[0]


def test_file_from_the_finder_is_opened(app, window, tmp_path):
    path = tmp_path / "finder.cipolle"
    Book.create(path, "Finder", date(2026, 1, 1), date(2026, 12, 31)).close()
    app.file_opened.connect(window.open_from_system)
    try:
        QCoreApplication.sendEvent(app, QFileOpenEvent(str(path)))
    finally:
        app.file_opened.disconnect(window.open_from_system)
    assert window.book.company == "Finder"


def test_file_from_the_finder_waits_for_an_open_dialog(app, window, tmp_path, monkeypatch):
    monkeypatch.setattr("cipolle.ui.main_window.QApplication.activeModalWidget", lambda: QMessageBox())
    window.open_from_system(str(tmp_path / "finder.cipolle"))
    assert window.book.company == "Muster"
    assert "Dialog" in window.statusBar().currentMessage()


def test_file_from_the_finder_passes_the_start_dialog(app, window, tmp_path, monkeypatch):
    path = tmp_path / "finder.cipolle"
    Book.create(path, "Finder", date(2026, 1, 1), date(2026, 12, 31)).close()
    dialog = StartDialog()
    monkeypatch.setattr("cipolle.ui.main_window.QApplication.activeModalWidget", lambda: dialog)
    window.open_from_system(str(path))
    assert window.book.company == "Finder"
