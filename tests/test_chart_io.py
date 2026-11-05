import json
from datetime import date

import pytest

from cipolle.book import Book, BookError
from cipolle.chart_io import FORMAT, VERSION, apply_import, chart_to_json, parse_chart, plan_import
from cipolle.templates import ASSET, EXPENSE, KMU_CHART, LIABILITY, Chart
from tests.test_book import post


def document(**overrides):
    data = {
        "format": FORMAT,
        "version": VERSION,
        "jahreserfolg_in": "",
        "gruppen": [{"code": "1", "name": "A", "summe_in": ""}],
        "konten": [{"nummer": "1000", "name": "Kasse", "klasse": "Aktiven", "summe_in": "1"}],
    }
    data.update(overrides)
    return json.dumps(data)


@pytest.fixture
def empty(tmp_path):
    instance = Book.create(tmp_path / "leer.cipolle", "Leer", date(2027, 1, 1), date(2027, 12, 31))
    yield instance
    instance.close()


def test_round_trip_keeps_the_whole_chart(book):
    assert parse_chart(chart_to_json(book.chart())) == book.chart()


def test_export_is_readable_and_has_no_balances(book, ids):
    book.update_account(ids["1020"], opening=987654)
    text = chart_to_json(book.chart())
    data = json.loads(text)
    assert data["format"] == "cipolle-kontenplan"
    assert data["jahreserfolg_in"] == "28"
    bank = next(item for item in data["konten"] if item["nummer"] == "1020")
    assert bank == {"nummer": "1020", "name": "Bank", "klasse": "Aktiven", "summe_in": "100"}
    assert "Flüssige Mittel" in text
    assert "987654" not in text


def test_import_into_empty_book(book, empty):
    apply_import(empty, parse_chart(chart_to_json(book.chart())), replace=False)
    assert empty.chart() == book.chart()
    assert empty.undo_label == "Kontenplan importieren"
    empty.undo()
    assert empty.accounts() == []
    assert empty.groups() == []
    assert empty.profit_group == ""


@pytest.mark.parametrize(
    "text, message",
    [
        ("kein json", "Keine gültige JSON-Datei"),
        ("[]", "kein Cipolle-Kontenplan"),
        ('{"format": "anderes"}', "kein Cipolle-Kontenplan"),
        (document(version=99), "Nicht unterstützte Version"),
        (document(gruppen="x"), "«gruppen» fehlt"),
        (document(konten=[1]), "«konten» fehlt"),
        (document(konten=[{"nummer": 1020, "klasse": "Aktiven"}]), "muss ein Text sein"),
        (document(konten=[{"nummer": "", "klasse": "Aktiven"}]), "«nummer» fehlt"),
        (document(konten=[{"nummer": "1 0", "klasse": "Aktiven"}]), "keine Leerzeichen"),
        (document(konten=[{"nummer": "1", "klasse": "Falsch"}]), "Unbekannte Klasse"),
        (document(konten=[{"nummer": "1", "klasse": "Aktiven", "summe_in": "9"}]), "nicht gefunden"),
        (
            document(konten=[{"nummer": "1", "klasse": "Aktiven"}, {"nummer": "1", "klasse": "Aktiven"}]),
            "doppelt",
        ),
        (document(gruppen=[{"code": "1"}, {"code": "1"}], konten=[]), "doppelt"),
        (document(gruppen=[{"code": "1", "summe_in": "9"}], konten=[]), "nicht gefunden"),
        (document(gruppen=[{"code": "1", "summe_in": "1"}], konten=[]), "in sich selbst"),
        (
            document(gruppen=[{"code": "1", "summe_in": "2"}, {"code": "2", "summe_in": "1"}], konten=[]),
            "in sich selbst",
        ),
        (document(jahreserfolg_in="9"), "Jahreserfolg"),
    ],
)
def test_invalid_files_are_refused(text, message):
    with pytest.raises(BookError, match=message):
        parse_chart(text)


def test_minimal_file_uses_defaults():
    chart = parse_chart(
        json.dumps(
            {
                "format": FORMAT,
                "version": VERSION,
                "gruppen": [{"code": "1"}],
                "konten": [{"nummer": " 1000 ", "klasse": "Aufwand"}],
            }
        )
    )
    assert chart == Chart([("1", "", "")], [("1000", "", EXPENSE, "")], "")


def test_merge_updates_and_keeps_the_rest(book, ids):
    chart = Chart(
        [("100", "Geld", "10"), ("10", "Umlauf", "1"), ("1", "Total Aktiven", ""), ("7", "Neu", "")],
        [("1020", "Hausbank", ASSET, "100"), ("7000", "Neu", EXPENSE, "7")],
        "",
    )
    before = len(book.accounts())
    plan = apply_import(book, chart, replace=False)
    assert plan.new_accounts == ["7000"]
    assert plan.changed_accounts == ["1020"]
    assert plan.new_groups == ["7"]
    assert book.account_by_number("1020").name == "Hausbank"
    assert book.group_by_code("100").name == "Geld"
    assert len(book.accounts()) == before + 1
    assert book.profit_group == "28"


def test_merge_keeps_opening_balances(book, ids):
    book.update_account(ids["1020"], opening=500)
    apply_import(book, book.chart(), replace=False)
    assert book.account(ids["1020"]).opening == 500


def test_import_can_reverse_group_order_without_cycle_error(book):
    chart = book.chart()
    groups = [("10", "x", "100") if g[0] == "10" else ("100", "y", "") if g[0] == "100" else g for g in chart.groups]
    apply_import(book, Chart(groups, chart.accounts, chart.profit_group), replace=False)
    assert book.group_by_code("10").parent == "100"
    assert book.group_by_code("100").parent == ""


def test_replace_removes_unused_and_keeps_used(book, ids):
    post(book, ids, "1020", "3000", 100)
    chart = Chart([("1", "Aktiven", "")], [("1000", "Kasse", ASSET, "1")], "")
    plan = apply_import(book, chart, replace=True)
    assert sorted(a.number for a in plan.kept_accounts) == ["1020", "3000"]
    assert [a.number for a in book.accounts()] == ["1000", "1020", "3000"]
    assert book.account_by_number("1020").group == "100"
    assert book.group_by_code("10") is not None
    assert book.group_by_code("30") is not None
    assert book.group_by_code("2") is None
    assert book.group_by_code("150") is None
    assert book.profit_group == ""
    assert book.entries()[0].debit_id == ids["1020"]


def test_replace_is_one_undo_step(book):
    before = book.chart()
    apply_import(book, Chart([("1", "A", "")], [("1", "A", ASSET, "1")], ""), replace=True)
    assert len(book.accounts()) == 1
    book.undo()
    assert book.chart() == before


def test_plan_changes_nothing(book):
    before = book.chart()
    plan = plan_import(book, Chart(), replace=True)
    assert len(plan.removed_accounts) == len(before.accounts)
    assert len(plan.removed_groups) == len(before.groups)
    assert book.chart() == before
    assert book.undo_label is None


def test_same_chart_has_no_changes(book):
    plan = plan_import(book, book.chart(), replace=True)
    assert not plan.has_changes
    apply_import(book, book.chart(), replace=True)
    assert book.undo_label is None


def test_profit_group_alone_counts_as_change(book):
    chart = book.chart()
    changed = Chart(chart.groups, chart.accounts, "2")
    assert plan_import(book, changed, replace=False).has_changes
    apply_import(book, changed, replace=False)
    assert book.profit_group == "2"


def test_merge_keeps_profit_group_when_file_has_none(book):
    chart = book.chart()
    without = Chart(chart.groups, chart.accounts, "")
    assert not plan_import(book, without, replace=False).has_changes
    assert plan_import(book, without, replace=True).has_changes


def test_plan_reports_opening_lost_by_klass_change(book, ids):
    book.update_account(ids["1020"], opening=500)
    chart = book.chart()
    accounts = [(n, name, EXPENSE if n == "1020" else k, g) for n, name, k, g in chart.accounts]
    plan = plan_import(book, Chart(chart.groups, accounts, chart.profit_group), replace=False)
    assert plan.lost_openings == ["1020"]


def test_kmu_chart_survives_export(empty):
    apply_import(empty, parse_chart(chart_to_json(KMU_CHART)), replace=False)
    assert empty.account_by_number("2800").klass == LIABILITY
    assert empty.profit_group == "28"
