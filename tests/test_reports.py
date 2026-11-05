from datetime import date

from cipolle import reports
from tests.test_book import post


def find(report, label):
    return next(row for row in report.rows if label in row.cells)


def setup_year(book, ids):
    book.update_account(ids["1020"], opening=100000)
    book.update_account(ids["2800"], opening=100000)
    post(book, ids, "1020", "3000", 50000, date(2026, 2, 1), "Honorar")
    post(book, ids, "6000", "1020", 20000, date(2026, 3, 1), "Miete")


def test_balance_sheet_balances_with_profit(book, ids):
    setup_year(book, ids)
    report = reports.balance_sheet(book)
    assert find(report, "Total Aktiven").cells[2] == 130000
    assert find(report, "Total Passiven").cells[2] == 130000
    assert find(report, "Gewinn laufendes Jahr").cells[2] == 30000


def test_balance_sheet_labels_a_loss(book, ids):
    post(book, ids, "6000", "1020", 100)
    report = reports.balance_sheet(book)
    assert find(report, "Verlust laufendes Jahr").cells[2] == -100
    assert find(report, "Total Aktiven").cells[2] == find(report, "Total Passiven").cells[2]


def test_balance_sheet_as_of_date(book, ids):
    setup_year(book, ids)
    report = reports.balance_sheet(book, until=date(2026, 2, 15))
    assert find(report, "Total Aktiven").cells[2] == 150000


def test_zero_accounts_are_hidden_unless_requested(book, ids):
    setup_year(book, ids)
    assert not any("1000" in row.cells for row in reports.balance_sheet(book).rows)
    assert any("1000" in row.cells for row in reports.balance_sheet(book, show_zero=True).rows)


def test_income_statement(book, ids):
    setup_year(book, ids)
    report = reports.income_statement(book)
    assert find(report, "Total Ertrag").cells[2] == 50000
    assert find(report, "Total Aufwand").cells[2] == 20000
    assert find(report, "Gewinn").cells[2] == 30000


def test_income_statement_period(book, ids):
    setup_year(book, ids)
    report = reports.income_statement(book, start=date(2026, 3, 1))
    assert find(report, "Verlust").cells[2] == -20000


def test_statement_running_balance(book, ids):
    setup_year(book, ids)
    report = reports.account_statement(book, ids["1020"])
    assert [row.cells[6] for row in report.rows] == [100000, 150000, 130000, 130000]
    assert report.rows[1].cells[3] == "3000"
    assert report.rows[2].cells[3] == "6000"
    assert report.rows[-1].cells[4:6] == [50000, 20000]


def test_statement_carries_forward_earlier_movements(book, ids):
    setup_year(book, ids)
    report = reports.account_statement(book, ids["1020"], start=date(2026, 3, 1))
    assert report.rows[0].cells[2] == "Saldovortrag"
    assert report.rows[0].cells[6] == 150000
    assert report.rows[-1].cells[6] == 130000


def test_statement_of_liability_is_positive_on_credit(book, ids):
    post(book, ids, "1020", "2400", 500)
    report = reports.account_statement(book, ids["2400"])
    assert report.rows[-1].cells[6] == 500


def test_statement_marks_split_entries(book, ids):
    post(book, ids, "1020", None, 300)
    post(book, ids, None, "3000", 300)
    report = reports.account_statement(book, ids["1020"])
    assert report.rows[1].cells[3] == "Sammelbuchung"


def test_nested_groups_show_subtotals(book, ids):
    setup_year(book, ids)
    report = reports.balance_sheet(book)
    assert find(report, "Total Flüssige Mittel").cells[2] == 130000
    assert find(report, "Total Umlaufvermögen").cells[2] == 130000
    assert find(report, "Total Eigenkapital").cells[2] == 130000
    labels = [row.cells[1] for row in report.rows]
    assert labels.index("Bank") < labels.index("Total Flüssige Mittel") < labels.index("Total Umlaufvermögen")
    assert labels.count("Total Aktiven") == 1
    assert find(report, "Bank").indent > find(report, "Total Flüssige Mittel").indent


def test_empty_groups_are_hidden_unless_requested(book, ids):
    setup_year(book, ids)
    assert not any("Total Vorräte" in row.cells for row in reports.balance_sheet(book).rows)
    assert any("Total Vorräte" in row.cells for row in reports.balance_sheet(book, show_zero=True).rows)


def test_profit_sits_inside_its_group(book, ids):
    setup_year(book, ids)
    labels = [row.cells[1] for row in reports.balance_sheet(book).rows]
    assert labels.index("Eigenkapital") < labels.index("Gewinn laufendes Jahr") < labels.index("Total Eigenkapital")


def test_without_profit_group_profit_stands_before_total(book, ids):
    setup_year(book, ids)
    book.set_profit_group("")
    report = reports.balance_sheet(book)
    labels = [row.cells[1] for row in report.rows]
    assert labels.index("Gewinn laufendes Jahr") + 1 == len(labels) - 1
    assert find(report, "Total Aktiven").cells[2] == report.rows[-1].cells[2]
    assert report.rows[-1].cells[1] == "Total Passiven"


def test_ungrouped_account_still_counts(book, ids):
    setup_year(book, ids)
    book.update_account(ids["1020"], group="")
    report = reports.balance_sheet(book)
    assert find(report, "Bank").cells[2] == 130000
    assert find(report, "Total Aktiven").cells[2] == 130000
    assert find(report, "Total Passiven").cells[2] == 130000


def test_mixed_group_does_not_break_the_statement(book, ids):
    post(book, ids, "1020", "6950", 300)
    post(book, ids, "6900", "1020", 100)
    report = reports.income_statement(book)
    assert find(report, "Total Ertrag").cells[2] == 300
    assert find(report, "Total Aufwand").cells[2] == 100
    assert find(report, "Gewinn").cells[2] == 200


def test_group_mixing_klasses_keeps_balance_sheet_even(book, ids):
    setup_year(book, ids)
    book.update_account(ids["2800"], group="100")
    report = reports.balance_sheet(book)
    assert find(report, "Total Aktiven").cells[2] == report.rows[-1].cells[2] == 130000
    assert "Gruppe 1 enthält Aktiv- und Passivkonten." in report.warnings


def test_journal_lists_posted_entries(book, ids):
    setup_year(book, ids)
    book.add_entry(text="unfertig")
    report = reports.journal(book)
    assert [row.cells[2] for row in report.rows] == ["Honorar", "Miete"]
    assert report.warnings


def test_html_escapes_and_links(book, ids):
    post(book, ids, "1020", "3000", 100, text="<script>&")
    report = reports.journal(book)
    assert "<script>" not in report.to_html()
    assert "&lt;script&gt;" in report.to_html()
    assert 'href="entry:' in report.to_html()
    assert "href=" not in report.to_html(links=False)


def test_csv_uses_plain_amounts(book, ids):
    post(book, ids, "1020", "3000", 123450, text="Honorar")
    lines = reports.journal(book).to_csv().splitlines()
    assert lines[0].startswith("Datum;Beleg")
    assert lines[1].endswith(";1234.50")
