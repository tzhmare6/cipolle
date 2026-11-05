"""Tabellenmodelle für Buchungen und Konten.

Beide Tabellen haben am Ende eine leere Zeile. Wer dort etwas eingibt, legt
einen neuen Datensatz an. Jede Eingabe wird sofort in die Datei geschrieben.
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor, QFont

from ..book import Account, Book, BookError, ChartRow, Entry, Group
from ..parsing import format_amount, format_date, natural_key, parse_amount, parse_date
from ..templates import KLASS_NAMES, guess_klass

ERROR_BACKGROUND = QColor(214, 69, 65, 70)
# Oberste Gruppen sind am stärksten getönt, die Tönung wirkt hell und dunkel.
GROUP_BACKGROUND = [QColor(52, 104, 192, alpha) for alpha in (70, 45, 28, 16)]

DISPLAY = Qt.ItemDataRole.DisplayRole
EDIT = Qt.ItemDataRole.EditRole
RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


class EntriesModel(QAbstractTableModel):
    DATE, DOC, TEXT, DEBIT, CREDIT, AMOUNT = range(6)
    HEADERS = ["Datum", "Beleg", "Beschreibung", "Soll", "Haben", "Betrag"]

    message = Signal(str)
    changed = Signal()

    def __init__(self, book: Book, parent=None):
        super().__init__(parent)
        self.book = book
        self.last_error: str | None = None
        self.rows: list[Entry] = []
        self.problems: dict[int, list[str]] = {}
        self.accounts: dict[int, Account] = {}
        self._load()

    def _load(self) -> None:
        self.rows = self.book.entries()
        self.problems = self.book.entry_problems()
        self.accounts = {a.id: a for a in self.book.accounts()}

    def reload(self) -> None:
        self.beginResetModel()
        self._load()
        self.endResetModel()

    def _refresh(self) -> None:
        """Lädt neu, ohne Auswahl und laufende Eingabe zu verlieren."""
        old_count = len(self.rows)
        entries = self.book.entries()
        if len(entries) > old_count:
            self.beginInsertRows(QModelIndex(), old_count + 1, len(entries))
            self._load()
            self.endInsertRows()
        else:
            self._load()
        self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount() - 1, self.columnCount() - 1))
        self.changed.emit()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows) + 1

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=DISPLAY):
        if role != DISPLAY:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return str(section + 1) if section < len(self.rows) else "*"

    def flags(self, index):
        return super().flags(index) | Qt.ItemFlag.ItemIsEditable

    def entry_at(self, row: int) -> Entry | None:
        return self.rows[row] if 0 <= row < len(self.rows) else None

    def row_of(self, entry_id: int) -> int | None:
        return next((i for i, e in enumerate(self.rows) if e.id == entry_id), None)

    def _account_text(self, account_id: int | None, editing: bool) -> str:
        account = self.accounts.get(account_id)
        if account is None:
            return ""
        return account.number if editing else account.label

    def data(self, index, role=DISPLAY):
        entry = self.entry_at(index.row())
        column = index.column()
        if role == Qt.ItemDataRole.TextAlignmentRole and column == self.AMOUNT:
            return RIGHT
        if entry is None:
            return None
        if role in (DISPLAY, EDIT):
            if column == self.DATE:
                return format_date(entry.date)
            if column == self.DOC:
                return entry.doc
            if column == self.TEXT:
                return entry.text
            if column == self.DEBIT:
                return self._account_text(entry.debit_id, role == EDIT)
            if column == self.CREDIT:
                return self._account_text(entry.credit_id, role == EDIT)
            return format_amount(entry.amount)
        if entry.id in self.problems:
            if role == Qt.ItemDataRole.BackgroundRole:
                return ERROR_BACKGROUND
            if role == Qt.ItemDataRole.ToolTipRole:
                return "\n".join(self.problems[entry.id])
        return None

    def setData(self, index, value, role=EDIT) -> bool:
        if role != EDIT or not index.isValid():
            return False
        try:
            fields = self._parse(index.column(), str(value))
        except (ValueError, BookError) as exc:
            self.last_error = str(exc)
            self.message.emit(str(exc))
            return False
        entry = self.entry_at(index.row())
        if entry is None:
            if not any(v not in (None, "") for v in fields.values()):
                return False
            if "date" not in fields and self.rows:
                fields["date"] = self.rows[-1].date
            self.book.add_entry(**fields)
        else:
            self.book.update_entry(entry.id, **fields)
        self._refresh()
        return True

    def _parse(self, column: int, text: str) -> dict:
        if column == self.DATE:
            return {"date": parse_date(text, self.book.start.year)}
        if column == self.DOC:
            return {"doc": text.strip()}
        if column == self.TEXT:
            return {"text": text.strip()}
        if column in (self.DEBIT, self.CREDIT):
            account = self.book.resolve_account(text)
            key = "debit_id" if column == self.DEBIT else "credit_id"
            return {key: account.id if account else None}
        return {"amount": parse_amount(text)}

    def insert_before(self, row: int) -> None:
        entry = self.entry_at(row)
        if entry is None:
            return
        self.beginInsertRows(QModelIndex(), row, row)
        self.book.add_entry(date=entry.date, before_position=entry.position)
        self._load()
        self.endInsertRows()
        self.changed.emit()

    def delete_rows(self, rows: list[int]) -> None:
        ids = [self.rows[row].id for row in rows if row < len(self.rows)]
        self.book.delete_entries(ids)
        self.reload()
        self.changed.emit()


class AccountsModel(QAbstractTableModel):
    """Kontenplan wie bei Banana: Konten mit «Summe in» und Gruppenzeilen als Totale."""

    GROUP, NUMBER, NAME, KLASS, SUM_IN, OPENING, BALANCE = range(7)
    HEADERS = ["Gruppe", "Konto", "Bezeichnung", "Klasse", "Summe in", "Eröffnung", "Saldo"]

    message = Signal(str)
    changed = Signal()

    def __init__(self, book: Book, parent=None):
        super().__init__(parent)
        self.book = book
        self.last_error: str | None = None
        self.rows: list[ChartRow] = []
        self.balances: dict[int, int] = {}
        self.group_balances: dict[str, int] = {}
        self.profit = 0
        self._load(sort=True)

    def _load(self, sort: bool) -> None:
        rows = self.book.chart_rows()
        movements = self.book.movements()
        self.balances = {a.id: self.book.balance(a, movements) for a in self.book.accounts()}
        self.group_balances = self.book.group_balances()
        self.profit = self.book.profit()
        if sort:
            self.rows = rows
            return
        # Neue Zeilen bleiben beim Erfassen unten, damit die Eingabe nicht springt.
        by_key = {row.key: row for row in rows}
        kept = [by_key.pop(row.key) for row in self.rows if row.key in by_key]
        self.rows = kept + list(by_key.values())

    def reload(self) -> None:
        """Lädt neu und ordnet alle Zeilen in den Gruppenbaum ein."""
        self.beginResetModel()
        self._load(sort=True)
        self.endResetModel()

    def _refresh(self) -> None:
        count = len(self.rows)
        added = len(self.book.chart_rows()) - count
        if added > 0:
            # Hinter der leeren Zeile einfügen, damit der Cursor auf seiner Zeile bleibt.
            self.beginInsertRows(QModelIndex(), count + 1, count + added)
            self._load(sort=False)
            self.endInsertRows()
        elif added < 0:
            self.reload()
        else:
            self._load(sort=False)
        self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount() - 1, self.columnCount() - 1))
        self.changed.emit()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows) + 1

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=DISPLAY):
        if role == DISPLAY and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def row_at(self, row: int) -> ChartRow | None:
        return self.rows[row] if 0 <= row < len(self.rows) else None

    def account_at(self, row: int) -> Account | None:
        chart_row = self.row_at(row)
        return chart_row.item if chart_row and chart_row.kind == "account" else None

    def row_of(self, kind: str, item_id: int) -> int | None:
        return next((i for i, r in enumerate(self.rows) if r.key == (kind, item_id)), None)

    def flags(self, index):
        base = super().flags(index)
        row = self.row_at(index.row())
        column = index.column()
        if row is None:
            editable = column in (self.GROUP, self.NUMBER)
        elif row.kind == "group":
            editable = column in (self.GROUP, self.NAME, self.SUM_IN)
        elif row.kind == "account":
            if column == self.OPENING:
                editable = row.item.is_balance_sheet
            else:
                editable = column in (self.NUMBER, self.NAME, self.KLASS, self.SUM_IN)
        else:
            editable = False
        return base | Qt.ItemFlag.ItemIsEditable if editable else base

    def _profit_label(self) -> str:
        return "Jahresgewinn" if self.profit >= 0 else "Jahresverlust"

    def data(self, index, role=DISPLAY):
        column = index.column()
        if role == Qt.ItemDataRole.TextAlignmentRole and column in (self.OPENING, self.BALANCE):
            return RIGHT
        row = self.row_at(index.row())
        if row is None:
            return None
        if role == Qt.ItemDataRole.FontRole and row.kind == "group":
            font = QFont()
            font.setBold(True)
            return font
        if role == Qt.ItemDataRole.BackgroundRole and row.kind == "group":
            return GROUP_BACKGROUND[min(row.depth, len(GROUP_BACKGROUND) - 1)]
        if role not in (DISPLAY, EDIT):
            return None
        if row.kind == "profit":
            return {
                self.NAME: self._profit_label(),
                self.SUM_IN: row.parent,
                self.BALANCE: format_amount(self.profit),
            }.get(column)
        if row.kind == "group":
            return self._group_data(row.item, column)
        return self._account_data(row.item, column, role)

    def _group_data(self, group: Group, column: int):
        return {
            self.GROUP: group.code,
            self.NAME: group.name,
            self.SUM_IN: group.parent,
            self.BALANCE: format_amount(self.group_balances[group.code]),
        }.get(column)

    def _account_data(self, account: Account, column: int, role):
        if column == self.KLASS:
            return account.klass if role == EDIT else KLASS_NAMES[account.klass]
        return {
            self.NUMBER: account.number,
            self.NAME: account.name,
            self.SUM_IN: account.group,
            self.OPENING: format_amount(account.opening) if account.is_balance_sheet else "",
            self.BALANCE: format_amount(self.balances[account.id]),
        }.get(column)

    def setData(self, index, value, role=EDIT) -> bool:
        if role != EDIT or not index.isValid():
            return False
        row = self.row_at(index.row())
        column = index.column()
        text = str(value)
        try:
            if row is None:
                if not text.strip():
                    return False
                self._add(column, text.strip())
            elif row.kind == "group":
                field = {self.GROUP: "code", self.NAME: "name", self.SUM_IN: "parent"}[column]
                self.book.update_group(row.item.id, **{field: text})
            elif column == self.OPENING:
                self.book.update_account(row.item.id, opening=parse_amount(text) or 0)
            elif column == self.KLASS:
                self.book.update_account(row.item.id, klass=int(value))
            else:
                field = {self.NUMBER: "number", self.NAME: "name", self.SUM_IN: "group"}[column]
                self.book.update_account(row.item.id, **{field: text})
        except (ValueError, BookError) as exc:
            self.last_error = str(exc)
            self.message.emit(str(exc))
            return False
        self._refresh()
        return True

    def _add(self, column: int, text: str) -> None:
        if column == self.GROUP:
            self.book.add_group(text)
            return
        # Ein neues Konto übernimmt die Gruppe des vorangehenden Kontos derselben Klasse.
        klass = guess_klass(text)
        key = natural_key(text)
        before = [a for a in self.book.accounts() if a.klass == klass and natural_key(a.number) < key]
        self.book.add_account(text, "", klass, before[-1].group if before else "")

    def delete_row(self, row: int) -> None:
        chart_row = self.row_at(row)
        if chart_row is None or chart_row.kind == "profit":
            return
        try:
            if chart_row.kind == "group":
                self.book.delete_group(chart_row.item.id)
            else:
                self.book.delete_account(chart_row.item.id)
        except BookError as exc:
            self.message.emit(str(exc))
            return
        self.reload()
        self.changed.emit()

    def group_labels(self) -> list[str]:
        return [g.label for g in self.book.groups()]
