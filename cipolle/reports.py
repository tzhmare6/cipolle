"""Auswertungen: Bilanz, Erfolgsrechnung, Kontoauszug und Journal.

Ein ``Report`` beschreibt nur Inhalte. Beträge bleiben ganze Rappen, die
Ausgabe als HTML oder CSV formatiert sie selbst.
"""

from __future__ import annotations

import csv
import html
import io
from dataclasses import dataclass, field
from datetime import date
from typing import Union

from .book import Account, Book, Group
from .parsing import format_amount, format_date, plain_amount
from .templates import ASSET, EXPENSE, LIABILITY, REVENUE

Cell = Union[str, int, None]  # int ist immer ein Betrag in Rappen

LINE, GROUP, SUBTOTAL, TOTAL = "line", "group", "subtotal", "total"


@dataclass
class Row:
    cells: list[Cell]
    kind: str = LINE
    link: str | None = None
    indent: int = 0


@dataclass
class Report:
    title: str
    subtitle: str
    columns: list[str]
    numeric: list[bool]
    widths: list[int]  # Spaltenbreiten in Prozent
    rows: list[Row] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_html(self, links: bool = True) -> str:
        parts = [f"<h2>{html.escape(self.title)}</h2><p>{html.escape(self.subtitle)}</p>"]
        for warning in self.warnings:
            parts.append(f'<p style="color:#c0392b"><b>{html.escape(warning)}</b></p>')
        parts.append('<table width="100%" cellspacing="0" cellpadding="3">')
        header = "".join(
            self._cell(f"<b>{html.escape(c)}</b>", n, w)
            for c, n, w in zip(self.columns, self.numeric, self.widths)
        )
        parts.append(f"<thead><tr>{header}</tr></thead>")
        for row in self.rows:
            cells = []
            for index, (cell, numeric) in enumerate(zip(row.cells, self.numeric)):
                text = format_amount(cell) if isinstance(cell, int) else html.escape(cell or "")
                if row.kind in (GROUP, SUBTOTAL, TOTAL):
                    text = f"<b>{text}</b>" if text else ""
                if index == 1 and row.indent:
                    text = "&nbsp;" * (3 * row.indent) + text
                if links and row.link and index == 0:
                    text = f'<a href="{html.escape(row.link)}">{text}</a>'
                cells.append(self._cell(text, numeric))
            parts.append(f"<tr>{''.join(cells)}</tr>")
            if row.kind == TOTAL:
                parts.append(f'<tr><td colspan="{len(self.columns)}">&nbsp;</td></tr>')
        parts.append("</table>")
        return "".join(parts)

    @staticmethod
    def _cell(content: str, numeric: bool, width: int | None = None) -> str:
        align = ' align="right"' if numeric else ""
        size = f' width="{width}%"' if width else ""
        return f"<td{align}{size}>{content}</td>"

    def to_csv(self) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
        writer.writerow(self.columns)
        for row in self.rows:
            writer.writerow(plain_amount(c) if isinstance(c, int) else (c or "") for c in row.cells)
        return buffer.getvalue()


def _period(book: Book, start: date | None, end: date | None) -> tuple[date, date]:
    return start or book.start, end or book.end


def _total_label(name: str) -> str:
    return name if name.startswith("Total") else f"Total {name}"


def _section(
    report: Report,
    book: Book,
    klass: int,
    title: str,
    movements: dict[int, tuple[int, int]],
    show_zero: bool,
    profit_row: Row | None = None,
) -> int:
    """Fügt die Konten einer Klasse als Gruppenbaum ein und gibt die Summe zurück.

    Jede Gruppe zeigt nur Konten dieser Klasse, damit eine gemischte Gruppe
    die Bilanz oder die Erfolgsrechnung nicht verfälschen kann. ``profit_row``
    erscheint in der Gruppe für den Jahreserfolg oder sonst am Ende.
    """
    groups = book.groups()
    accounts = [a for a in book.accounts() if a.klass == klass]
    section_label = f"Total {title}"
    roots = [g for g in groups if not g.parent]
    profit_group = book.profit_group if profit_row else ""
    if profit_row and not profit_group:
        # Ohne gewählte Gruppe gehört der Erfolg in die Gruppe, die das Schlusstotal bildet.
        profit_group = next((g.code for g in roots if _total_label(g.name) == section_label), "")
    placed = False

    def lines(members: list[Account], depth: int) -> tuple[list[Row], int]:
        rows, total = [], 0
        for account in members:
            amount = book.balance(account, movements)
            total += amount
            if amount or show_zero or account.id in movements:
                rows.append(Row([account.number, account.name, amount], link=f"account:{account.id}", indent=depth))
        return rows, total

    def node(group: Group, depth: int, header: bool, kind: str = SUBTOTAL) -> tuple[list[Row], int]:
        nonlocal placed
        body, total = lines([a for a in accounts if a.group == group.code], depth + 1)
        for child in groups:
            if child.parent == group.code:
                rows, amount = node(child, depth + 1, True)
                body += rows
                total += amount
        if group.code == profit_group:
            profit_row.indent = depth + 1
            body.append(profit_row)
            total += profit_row.cells[2]
            placed = True
        if not body:
            return [], 0
        top = [Row(["", group.name, None], GROUP, indent=depth)] if header else []
        return top + body + [Row(["", _total_label(group.name), total], kind, indent=depth)], total

    report.rows.append(Row(["", title, None], GROUP))
    loose = [a for a in accounts if not a.group]
    # Gibt es genau eine Wurzel namens «Aktiven» oder «Total Aktiven», ist sie das Schlusstotal.
    rendered = [(g, node(g, 0, _total_label(g.name) != section_label)) for g in roots]
    rendered = [(g, rows, amount) for g, (rows, amount) in rendered if rows]
    orphan = profit_row if profit_row and not placed else None
    if len(rendered) == 1 and _total_label(rendered[0][0].name) == section_label and not loose and not orphan:
        _group, rows, amount = rendered[0]
        rows[-1].kind = TOTAL
        report.rows.extend(rows)
        return amount
    total = 0
    for _group, rows, amount in rendered:
        report.rows.extend(rows)
        total += amount
    rows, amount = lines(loose, 0)
    report.rows.extend(rows)
    total += amount
    if orphan:
        report.rows.append(orphan)
        total += orphan.cells[2]
    report.rows.append(Row(["", section_label, total], TOTAL))
    return total


def balance_sheet(book: Book, until: date | None = None, show_zero: bool = False) -> Report:
    _, end = _period(book, None, until)
    report = Report(
        "Bilanz",
        f"{book.company}, per {format_date(end)}",
        ["Konto", "Bezeichnung", "CHF"],
        [False, False, True],
        [12, 68, 20],
        warnings=book.warnings(),
    )
    movements = book.movements(until=end)
    _section(report, book, ASSET, "Aktiven", movements, show_zero)
    profit = book.profit(until=end)
    label = "Gewinn laufendes Jahr" if profit >= 0 else "Verlust laufendes Jahr"
    _section(report, book, LIABILITY, "Passiven", movements, show_zero, Row(["", label, profit]))
    return report


def income_statement(
    book: Book, start: date | None = None, end: date | None = None, show_zero: bool = False
) -> Report:
    start, end = _period(book, start, end)
    report = Report(
        "Erfolgsrechnung",
        f"{book.company}, {format_date(start)} bis {format_date(end)}",
        ["Konto", "Bezeichnung", "CHF"],
        [False, False, True],
        [12, 68, 20],
        warnings=book.warnings(),
    )
    movements = book.movements(until=end, since=start)
    revenue = _section(report, book, REVENUE, "Ertrag", movements, show_zero)
    expense = _section(report, book, EXPENSE, "Aufwand", movements, show_zero)
    result = revenue - expense
    report.rows.append(Row(["", "Gewinn" if result >= 0 else "Verlust", result], TOTAL))
    return report


def account_statement(
    book: Book, account_id: int, start: date | None = None, end: date | None = None
) -> Report:
    start, end = _period(book, start, end)
    account = book.account(account_id)
    labels = {a.id: a.number for a in book.accounts()}
    report = Report(
        f"Kontoauszug {account.label}",
        f"{book.company}, {format_date(start)} bis {format_date(end)}",
        ["Datum", "Beleg", "Beschreibung", "Gegenkonto", "Soll", "Haben", "Saldo"],
        [False, False, False, False, True, True, True],
        [11, 7, 32, 14, 12, 12, 12],
        warnings=book.warnings(),
    )
    entries = [e for e in book.posted_entries() if account_id in (e.debit_id, e.credit_id)]
    balance = account.opening
    for entry in entries:
        if entry.date < start:
            balance += _change(account, entry.debit_id == account_id, entry.amount)
    label = "Eröffnung" if start == book.start else "Saldovortrag"
    report.rows.append(Row([format_date(start), "", label, "", None, None, balance], SUBTOTAL))
    total_debit = total_credit = 0
    for entry in entries:
        if not start <= entry.date <= end:
            continue
        is_debit = entry.debit_id == account_id
        balance += _change(account, is_debit, entry.amount)
        contra_id = entry.credit_id if is_debit else entry.debit_id
        contra = labels.get(contra_id, "Sammelbuchung")
        debit, credit = (entry.amount, None) if is_debit else (None, entry.amount)
        total_debit += debit or 0
        total_credit += credit or 0
        report.rows.append(
            Row(
                [format_date(entry.date), entry.doc, entry.text, contra, debit, credit, balance],
                link=f"entry:{entry.id}",
            )
        )
    report.rows.append(Row(["", "", "Total Umsatz und Schlusssaldo", "", total_debit, total_credit, balance], SUBTOTAL))
    return report


def _change(account: Account, is_debit: bool, amount: int) -> int:
    return amount if is_debit == account.debit_normal else -amount


def journal(book: Book, start: date | None = None, end: date | None = None) -> Report:
    start, end = _period(book, start, end)
    labels = {a.id: a.number for a in book.accounts()}
    report = Report(
        "Journal",
        f"{book.company}, {format_date(start)} bis {format_date(end)}",
        ["Datum", "Beleg", "Beschreibung", "Soll", "Haben", "Betrag"],
        [False, False, False, False, False, True],
        [11, 7, 46, 12, 12, 12],
        warnings=book.warnings(),
    )
    for entry in book.posted_entries():
        if start <= entry.date <= end:
            report.rows.append(
                Row(
                    [
                        format_date(entry.date),
                        entry.doc,
                        entry.text,
                        labels.get(entry.debit_id, ""),
                        labels.get(entry.credit_id, ""),
                        entry.amount,
                    ],
                    link=f"entry:{entry.id}",
                )
            )
    return report
