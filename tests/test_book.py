from datetime import date

import pytest

import sqlite3

from cipolle.book import APPLICATION_ID, Book, BookError, carry_over, create_next_year, next_period
from cipolle.templates import ASSET, EXPENSE


def post(book, ids, debit, credit, amount, day=date(2026, 3, 1), text="x"):
    return book.add_entry(
        date=day,
        text=text,
        debit_id=ids.get(debit),
        credit_id=ids.get(credit),
        amount=amount,
    )


def test_create_refuses_existing_file(tmp_path, book):
    with pytest.raises(BookError):
        Book.create(book.path, "x", date(2026, 1, 1), date(2026, 12, 31))


def test_reopen_keeps_data_and_writes_backup(book, ids):
    post(book, ids, "1020", "3000", 10000)
    path = book.path
    book.db.commit()
    reopened = Book.open(path)
    assert reopened.company == "Muster GmbH"
    assert len(reopened.entries()) == 1
    assert path.with_name(path.name + ".bak").exists()
    reopened.close()


def test_open_rejects_foreign_file(tmp_path):
    other = tmp_path / "other.cipolle"
    other.write_text("keine Datenbank, nur Text " * 50)
    with pytest.raises(BookError):
        Book.open(other)


def test_balances_follow_natural_direction(book, ids):
    book.update_account(ids["1020"], opening=100000)
    book.update_account(ids["2800"], opening=100000)
    post(book, ids, "1020", "3000", 50000)
    post(book, ids, "6000", "1020", 20000)
    movements = book.movements()
    assert book.balance(book.account(ids["1020"]), movements) == 130000
    assert book.balance(book.account(ids["2800"]), movements) == 100000
    assert book.balance(book.account(ids["3000"]), movements) == 50000
    assert book.balance(book.account(ids["6000"]), movements) == 20000
    assert book.profit() == 30000
    assert book.posting_difference() == 0
    assert book.opening_difference() == 0
    assert book.warnings() == []


def test_period_filters_movements(book, ids):
    post(book, ids, "1020", "3000", 100, date(2026, 1, 31))
    post(book, ids, "1020", "3000", 200, date(2026, 2, 1))
    assert book.profit(until=date(2026, 1, 31)) == 100
    assert book.profit(since=date(2026, 2, 1)) == 200


@pytest.mark.parametrize(
    "kwargs, message",
    [
        (dict(text="x"), "Datum fehlt"),
        (dict(date=date(2025, 12, 31), amount=1), "ausserhalb"),
        (dict(date=date(2026, 1, 1), amount=1), "Konto fehlt"),
    ],
)
def test_problems_are_reported_and_excluded(book, kwargs, message):
    entry_id = book.add_entry(**kwargs)
    assert any(message in text for text in book.entry_problems()[entry_id])
    assert book.posted_entries() == []
    assert book.warnings()[0] == "1 fehlerhafte Buchung fehlt in den Auswertungen."


def test_warning_counts_several_excluded_entries(book):
    book.add_entry(text="a")
    book.add_entry(text="b")
    assert book.warnings()[0] == "2 fehlerhafte Buchungen fehlen in den Auswertungen."


def test_same_account_is_a_problem(book, ids):
    entry_id = post(book, ids, "1020", "1020", 100)
    assert "dasselbe Konto" in book.entry_problems()[entry_id][0]


def test_balanced_split_entry_has_no_problem(book, ids):
    post(book, ids, "1020", None, 300)
    post(book, ids, None, "3000", 200)
    post(book, ids, None, "3200", 100)
    post(book, ids, "6000", "1020", 50)
    assert book.entry_problems() == {}
    assert book.posting_difference() == 0


def test_unbalanced_split_entry_is_flagged_on_last_row(book, ids):
    post(book, ids, "1020", None, 300)
    last = post(book, ids, None, "3000", 200)
    post(book, ids, "6000", "1020", 50)
    assert "Differenz 1.00" in book.entry_problems()[last][0]
    assert book.posting_difference() == 100
    assert any("Differenz Soll/Haben" in text for text in book.warnings())


def test_opening_difference_warns(book, ids):
    book.update_account(ids["1020"], opening=100)
    assert "Eröffnungsbilanz" in book.warnings()[0]


def test_account_number_can_change_without_touching_entries(book, ids):
    post(book, ids, "1020", "3000", 100)
    book.update_account(ids["1020"], number="1021")
    assert book.resolve_account("1021").id == ids["1020"]
    assert book.entries()[0].debit_id == ids["1020"]


def test_used_account_cannot_be_deleted(book, ids):
    post(book, ids, "1020", "3000", 100)
    with pytest.raises(BookError):
        book.delete_account(ids["1020"])
    book.delete_account(ids["1000"])
    assert book.account_by_number("1000") is None


def test_duplicate_number_is_rejected(book, ids):
    with pytest.raises(BookError):
        book.add_account("1020", "Zweite Bank", ASSET)
    with pytest.raises(BookError):
        book.update_account(ids["1000"], number="1020")


def test_opening_is_rejected_on_income_accounts(book, ids):
    with pytest.raises(BookError):
        book.update_account(ids["6000"], opening=100)
    with pytest.raises(BookError):
        book.add_account("6999", "x", EXPENSE, opening=1)


def test_changing_klass_to_expense_clears_opening(book, ids):
    book.update_account(ids["1000"], opening=100)
    book.update_account(ids["1000"], klass=EXPENSE)
    assert book.account(ids["1000"]).opening == 0


@pytest.mark.parametrize(
    "text, number",
    [("1020", "1020"), ("1020 Bank", "1020"), ("kasse", "1000"), ("102", "1020"), ("", None)],
)
def test_resolve_account(book, text, number):
    account = book.resolve_account(text)
    assert (account.number if account else None) == number


@pytest.mark.parametrize("text", ["10", "aufwand", "9999"])
def test_resolve_account_rejects_ambiguous_or_unknown(book, text):
    with pytest.raises(BookError):
        book.resolve_account(text)


def test_insert_before_and_sort(book, ids):
    late = post(book, ids, "1020", "3000", 1, date(2026, 5, 1))
    early = post(book, ids, "1020", "3000", 2, date(2026, 1, 1))
    between = book.add_entry(date=date(2026, 2, 1), before_position=book.entries()[1].position)
    assert [e.id for e in book.entries()] == [late, between, early]
    book.sort_entries_by_date()
    assert [e.id for e in book.entries()] == [early, between, late]


def test_update_entry_rejects_unknown_field(book):
    entry_id = book.add_entry(text="x")
    with pytest.raises(ValueError):
        book.update_entry(entry_id, position=9)


@pytest.mark.parametrize(
    "start, end, expected",
    [
        (date(2026, 1, 1), date(2026, 12, 31), (date(2027, 1, 1), date(2027, 12, 31))),
        (date(2026, 7, 1), date(2027, 6, 30), (date(2027, 7, 1), date(2028, 6, 30))),
        (date(2023, 3, 1), date(2024, 2, 29), (date(2024, 3, 1), date(2025, 2, 28))),
        (date(2024, 3, 1), date(2025, 2, 28), (date(2025, 3, 1), date(2026, 2, 28))),
        (date(2022, 3, 1), date(2023, 2, 28), (date(2023, 3, 1), date(2024, 2, 29))),
    ],
)
def test_next_period(start, end, expected):
    assert next_period(start, end) == expected


def test_next_year_carries_balances_and_profit(book, ids, tmp_path):
    book.update_account(ids["1020"], opening=100000)
    book.update_account(ids["2800"], opening=100000)
    post(book, ids, "1020", "3000", 50000)
    post(book, ids, "6000", "1020", 20000)
    target = create_next_year(book, tmp_path / "2027.cipolle", "2970")
    assert target.start == date(2027, 1, 1)
    assert target.account_by_number("1020").opening == 130000
    assert target.account_by_number("2800").opening == 100000
    assert target.account_by_number("2970").opening == 30000
    assert target.account_by_number("3000").opening == 0
    assert target.opening_difference() == 0
    assert target.entries() == []
    target.close()


def test_next_year_handles_a_loss(book, ids, tmp_path):
    book.update_account(ids["1020"], opening=1000)
    book.update_account(ids["2800"], opening=1000)
    post(book, ids, "6000", "1020", 400)
    target = create_next_year(book, tmp_path / "2027.cipolle", "2970")
    assert target.account_by_number("2970").opening == -400
    assert target.opening_difference() == 0
    target.close()


def test_carry_over_can_be_repeated_after_late_bookings(book, ids, tmp_path):
    book.update_account(ids["1020"], opening=1000)
    book.update_account(ids["2800"], opening=1000)
    target = create_next_year(book, tmp_path / "2027.cipolle", "2970")
    post(book, ids, "1020", "3000", 500)
    new_id = book.add_account("1025", "Zweites Konto", ASSET, "100")
    post(book, {"1025": new_id, "3000": ids["3000"]}, "1025", "3000", 100)
    carry_over(book, target, "2970")
    assert target.account_by_number("1020").opening == 1500
    assert target.account_by_number("1025").opening == 100
    assert target.account_by_number("2970").opening == 600
    assert target.opening_difference() == 0
    target.close()


def test_carry_over_needs_a_liability_account(book, tmp_path):
    other = Book.create(tmp_path / "x.cipolle", "x", date(2027, 1, 1), date(2027, 12, 31))
    with pytest.raises(BookError, match="Passivkonto"):
        carry_over(book, other, "1020")
    other.close()


def test_carry_over_rejects_a_later_or_same_year(book, tmp_path):
    other = Book.create(tmp_path / "x.cipolle", "x", date(2026, 1, 1), date(2026, 12, 31))
    with pytest.raises(BookError):
        carry_over(book, other, "2970")
    other.close()


def test_group_codes_and_tree(book, ids):
    assert book.account(ids["1020"]).group == "100"
    assert book.group_by_code("100").parent == "10"
    book.update_group(book.group_by_code("10").id, code="11")
    assert book.group_by_code("100").parent == "11"
    assert book.account(ids["1020"]).group == "100"


def test_chart_rows_put_group_below_its_content(book):
    labels = [(r.kind, r.item.code if r.kind == "group" else r.item.number if r.item else "") for r in book.chart_rows()]
    assert labels[:3] == [("account", "1000"), ("account", "1020"), ("group", "100")]
    assert labels.index(("group", "130")) < labels.index(("group", "10")) < labels.index(("group", "14"))
    assert labels.index(("group", "14")) < labels.index(("group", "1"))
    assert labels.index(("account", "2970")) + 1 == labels.index(("profit", ""))
    assert labels.index(("group", "2A")) < labels.index(("group", "28"))


def test_ungrouped_accounts_stay_in_chart(book, ids):
    book.update_account(ids["1000"], group="")
    last = book.chart_rows()[-1]
    assert last.item.number == "1000"
    assert last.depth == 0


def test_group_balances_roll_up_with_profit(book, ids):
    book.update_account(ids["1020"], opening=100000)
    book.update_account(ids["2800"], opening=100000)
    post(book, ids, "1020", "3000", 50000)
    post(book, ids, "6000", "1020", 20000)
    balances = book.group_balances()
    assert balances["100"] == 130000
    assert balances["10"] == 130000
    assert balances["1"] == 130000
    assert balances["28"] == 130000
    assert balances["2"] == 130000
    assert balances["30"] == 50000
    assert balances["60"] == 20000


def test_mixed_group_counts_revenue_minus_expense(book, ids):
    post(book, ids, "1020", "6950", 300)
    post(book, ids, "6900", "1020", 100)
    assert book.group_balances()["68"] == 200


def test_group_cycle_is_refused(book):
    with pytest.raises(BookError, match="in sich selbst"):
        book.update_group(book.group_by_code("10").id, parent="100")
    with pytest.raises(BookError, match="in sich selbst"):
        book.update_group(book.group_by_code("10").id, parent="10")


def test_unknown_group_is_refused(book, ids):
    with pytest.raises(BookError, match="nicht gefunden"):
        book.update_account(ids["1020"], group="999")
    with pytest.raises(BookError, match="nicht gefunden"):
        book.add_group("999", "x", "998")


def test_used_group_cannot_be_deleted(book):
    with pytest.raises(BookError):
        book.delete_group(book.group_by_code("100").id)
    with pytest.raises(BookError):
        book.delete_group(book.group_by_code("10").id)
    book.add_group("999", "Leer")
    book.delete_group(book.group_by_code("999").id)
    assert book.group_by_code("999") is None


def test_deleting_profit_group_clears_it(tmp_path):
    book = Book.create(tmp_path / "x.cipolle", "x", date(2026, 1, 1), date(2026, 12, 31))
    book.add_group("9", "EK")
    book.set_profit_group("9")
    assert book.profit_group == "9"
    book.delete_group(book.group_by_code("9").id)
    assert book.profit_group == ""
    book.close()


def test_next_year_keeps_groups(book, tmp_path):
    book.add_group("15", "Neu", "1")
    target = create_next_year(book, tmp_path / "2027.cipolle", "2970")
    assert target.group_by_code("15").parent == "1"
    assert target.profit_group == "28"
    assert target.account_by_number("1020").group == "100"
    target.close()


def test_carry_over_adds_missing_groups(book, ids, tmp_path):
    target = create_next_year(book, tmp_path / "2027.cipolle", "2970")
    book.add_group("15", "Neu", "1")
    book.add_group("151", "Tief", "15")
    book.add_account("1599", "Neu", ASSET, "151")
    carry_over(book, target, "2970")
    assert target.group_by_code("151").parent == "15"
    assert target.account_by_number("1599").group == "151"
    target.close()


def make_v1_file(path):
    db = sqlite3.connect(path)
    db.executescript(
        f"""
        PRAGMA application_id = {APPLICATION_ID};
        PRAGMA user_version = 1;
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO meta VALUES ('company', 'Alt'), ('start', '2026-01-01'), ('end', '2026-12-31');
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY, number TEXT NOT NULL UNIQUE, name TEXT NOT NULL DEFAULT '',
            klass INTEGER NOT NULL, grp TEXT NOT NULL DEFAULT '', opening INTEGER NOT NULL DEFAULT 0
        );
        INSERT INTO accounts (number, name, klass, grp, opening) VALUES
            ('2800', 'EK', 2, 'Eigenkapital', 500),
            ('1020', 'Bank', 1, 'Umlaufvermögen', 500),
            ('1000', 'Kasse', 1, 'Umlaufvermögen', 0),
            ('3000', 'Ertrag', 4, '', 0);
        CREATE TABLE entries (
            id INTEGER PRIMARY KEY, position INTEGER NOT NULL, date TEXT, doc TEXT NOT NULL DEFAULT '',
            text TEXT NOT NULL DEFAULT '', debit_id INTEGER REFERENCES accounts(id),
            credit_id INTEGER REFERENCES accounts(id), amount INTEGER
        );
        INSERT INTO entries (position, date, text, debit_id, credit_id, amount)
            VALUES (1, '2026-02-01', 'Alt', 2, 4, 100);
        """
    )
    db.commit()
    db.close()


def test_old_file_is_migrated_and_backed_up(tmp_path):
    path = tmp_path / "alt.cipolle"
    make_v1_file(path)
    book = Book.open(path)
    assert [(g.code, g.name) for g in book.groups()] == [("G1", "Umlaufvermögen"), ("G2", "Eigenkapital")]
    assert book.account_by_number("1020").group == "G1"
    assert book.account_by_number("3000").group == ""
    assert book.profit_group == "G2"
    assert book.account_by_number("1020").opening == 500
    assert [e.text for e in book.entries()] == ["Alt"]
    book.close()
    again = Book.open(path)
    assert len(again.groups()) == 2
    again.close()
    backup = sqlite3.connect(path.with_name("alt.cipolle.bak"))
    assert backup.execute("PRAGMA user_version").fetchone()[0] == 3
    backup.close()


def snapshot(book):
    return (book.accounts(), book.groups(), book.entries(), book.company, book.start, book.end, book.profit_group)


def test_undo_and_redo_of_new_entry(book, ids):
    post(book, ids, "1020", "3000", 100)
    assert book.undo_label == "Buchung anlegen"
    result = book.undo()
    assert book.entries() == []
    assert result.label == "Buchung anlegen"
    assert result.row_id is None
    assert book.undo_label is None
    assert book.redo_label == "Buchung anlegen"
    result = book.redo()
    assert book.entries()[0].amount == 100
    assert result.table == "entries"
    assert book.redo_label is None


def test_undo_restores_deleted_entry_exactly(book, ids):
    entry_id = post(book, ids, "1020", "3000", 123450, text="O'Brien; «Test»")
    before = book.entries()
    book.delete_entries([entry_id])
    book.undo()
    assert book.entries() == before


def test_undo_restores_null_values(book):
    entry_id = book.add_entry(text="ohne Datum")
    book.update_entry(entry_id, date=date(2026, 1, 1), amount=5)
    book.undo()
    entry = book.entries()[0]
    assert (entry.date, entry.amount) == (None, None)


def test_undo_steps_go_back_in_order(book, ids):
    entry_id = post(book, ids, "1020", "3000", 100)
    book.update_entry(entry_id, amount=200)
    book.update_entry(entry_id, amount=300)
    book.undo()
    assert book.entries()[0].amount == 200
    book.undo()
    assert book.entries()[0].amount == 100
    book.redo()
    book.redo()
    assert book.entries()[0].amount == 300


def test_new_change_discards_redo(book, ids):
    entry_id = post(book, ids, "1020", "3000", 100)
    book.update_entry(entry_id, amount=200)
    book.undo()
    book.update_entry(entry_id, text="neu")
    assert book.redo_label is None
    book.undo()
    assert book.entries()[0].amount == 100


def test_unchanged_value_creates_no_step(book, ids):
    entry_id = post(book, ids, "1020", "3000", 100)
    book.update_entry(entry_id, amount=200)
    book.undo()
    book.update_entry(entry_id, amount=100)
    assert book.redo_label == "Buchung ändern"
    assert book.undo_label == "Buchung anlegen"


def test_failed_change_keeps_history(book, ids):
    entry_id = post(book, ids, "1020", "3000", 100)
    book.update_entry(entry_id, amount=200)
    book.undo()
    with pytest.raises(BookError):
        book.update_account(ids["1000"], number="1020")
    assert book.redo_label == "Buchung ändern"


def test_step_groups_several_changes(book, ids):
    with book.step("Sammlung"):
        post(book, ids, "1020", "3000", 1)
        post(book, ids, "1020", "3000", 2)
    assert book.undo_label == "Sammlung"
    book.undo()
    assert book.entries() == []
    book.redo()
    assert [e.amount for e in book.entries()] == [1, 2]


def test_undo_of_inserted_row_restores_positions(book, ids):
    post(book, ids, "1020", "3000", 1)
    second = post(book, ids, "1020", "3000", 2)
    before = book.entries()
    book.add_entry(before_position=book.entries()[1].position)
    book.undo()
    assert book.entries() == before
    assert before[1].id == second


def test_undo_of_sort(book, ids):
    post(book, ids, "1020", "3000", 1, date(2026, 5, 1))
    post(book, ids, "1020", "3000", 2, date(2026, 1, 1))
    before = book.entries()
    book.sort_entries_by_date()
    assert book.undo_label == "Buchungen sortieren"
    book.undo()
    assert book.entries() == before


def test_undo_of_account_group_and_property_changes(book, ids):
    before = snapshot(book)
    book.update_account(ids["1020"], number="1021", opening=500, group="110")
    book.update_group(book.group_by_code("10").id, name="Anders", parent="")
    book.add_group("99", "Neu", "2")
    book.set_profit_group("99")
    book.set_properties("Anders AG", date(2027, 1, 1), date(2027, 12, 31))
    for _ in range(5):
        book.undo()
    assert snapshot(book) == before
    for _ in range(5):
        book.redo()
    assert book.company == "Anders AG"
    assert book.profit_group == "99"
    assert book.account(ids["1020"]).number == "1021"


def test_undo_of_deleting_group_with_accounts_and_profit(book):
    before = snapshot(book)
    with book.step("Zeilen löschen"):
        for number in ("2800", "2850", "2970"):
            book.delete_account(book.account_by_number(number).id)
        book.delete_group(book.group_by_code("28").id)
    assert book.profit_group == ""
    book.undo()
    assert snapshot(book) == before


def test_history_survives_reopening(book, ids):
    entry_id = post(book, ids, "1020", "3000", 100)
    book.update_entry(entry_id, amount=200)
    path = book.path
    book.close()
    reopened = Book.open(path, backup=False)
    assert reopened.undo_label == "Buchung ändern"
    reopened.undo()
    assert reopened.entries()[0].amount == 100
    reopened.update_entry(entry_id, amount=300)
    reopened.undo()
    assert reopened.entries()[0].amount == 100
    book.db = reopened.db


def test_history_is_limited(book, ids, monkeypatch):
    monkeypatch.setattr("cipolle.book.MAX_UNDO_STEPS", 3)
    entry_id = post(book, ids, "1020", "3000", 0)
    for amount in range(1, 6):
        book.update_entry(entry_id, amount=amount)
    assert book.db.execute("SELECT count(*) FROM undo_steps").fetchone()[0] == 3
    assert book.db.execute("SELECT count(*) FROM undo_log").fetchone()[0] == 3
    for _ in range(3):
        assert book.undo()
    assert book.undo() is None
    assert book.entries()[0].amount == 2


def test_undo_and_redo_with_empty_history(book):
    assert book.undo() is None
    assert book.redo() is None


def test_result_names_the_touched_row(book, ids):
    entry_id = post(book, ids, "1020", "3000", 100)
    book.update_account(ids["1020"], name="Hausbank")
    assert book.undo().row_id == ids["1020"]
    book.update_entry(entry_id, amount=2)
    result = book.undo()
    assert (result.table, result.row_id) == ("entries", entry_id)


def test_new_file_starts_without_history(book):
    assert book.undo_label is None


def test_next_year_starts_without_history(book, ids, tmp_path):
    book.update_account(ids["1020"], opening=100)
    book.update_account(ids["2800"], opening=100)
    target = create_next_year(book, tmp_path / "2027.cipolle", "2970")
    assert target.undo_label is None
    assert target.account_by_number("1020").opening == 100
    target.close()


def test_carry_over_is_one_undoable_step(book, ids, tmp_path):
    book.update_account(ids["1020"], opening=100)
    book.update_account(ids["2800"], opening=100)
    target = create_next_year(book, tmp_path / "2027.cipolle", "2970")
    post(book, ids, "1020", "3000", 50)
    book.add_group("15", "Neu", "1")
    book.add_account("1599", "Neu", ASSET, "15")
    before = snapshot(target)
    carry_over(book, target, "2970")
    assert target.account_by_number("1020").opening == 150
    assert target.undo_label == "Eröffnung aus Vorjahr aktualisieren"
    target.undo()
    assert snapshot(target) == before
    assert target.undo_label is None
    target.close()


def test_v2_file_gets_history_tables(tmp_path):
    path = tmp_path / "v2.cipolle"
    book = Book.create(path, "x", date(2026, 1, 1), date(2026, 12, 31))
    book.add_group("1", "A")
    book.close()
    db = sqlite3.connect(path)
    db.executescript("DROP TABLE undo_log; DROP TABLE undo_steps; PRAGMA user_version = 2;")
    db.close()
    book = Book.open(path)
    book.add_group("2", "B")
    book.undo()
    assert [g.code for g in book.groups()] == ["1"]
    assert book.db.execute("PRAGMA user_version").fetchone()[0] == 3
    book.close()


def test_changes_by_other_connections_are_not_logged(book, ids):
    other = sqlite3.connect(book.path)
    other.execute("UPDATE accounts SET name = 'Fremd' WHERE number = '1000'")
    other.commit()
    other.close()
    assert book.undo_label is None
