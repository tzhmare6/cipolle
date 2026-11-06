"""Tabellenmodelle für Buchungen und Konten.

Beide Tabellen haben am Ende eine leere Zeile. Wer dort etwas eingibt, legt
einen neuen Datensatz an. Jede Eingabe wird sofort in die Datei geschrieben.
"""

from __future__ import annotations

import sqlite3

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


class LedgerModel(QAbstractTableModel):
    """Gemeinsame Signale der beiden Tabellen."""

    message = Signal(str)
    changed = Signal()
    save_failed = Signal(str)

    last_error: str | None = None

    def report_save_error(self, error: sqlite3.Error) -> None:
        """Meldet einen Schreibfehler. Ein offenes Eingabefeld bleibt dadurch offen."""
        self.last_error = str(error)
        self.save_failed.emit(str(error))


class EntriesModel(LedgerModel):
    DATE, DOC, TEXT, DEBIT, CREDIT, AMOUNT = range(6)
    HEADERS = ["Datum", "Beleg", "Beschreibung", "Soll", "Haben", "Betrag"]
    FIRST_COLUMN = DATE
    needs_resort = False  # Buchungen behalten ihre Reihenfolge

    def __init__(self, book: Book, parent=None):
        super().__init__(parent)
        self.book = book
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
            entry = self.entry_at(index.row())
            if entry is None:
                if not any(v not in (None, "") for v in fields.values()):
                    return False
                if "date" not in fields and self.rows:
                    fields["date"] = self.rows[-1].date
                self.book.add_entry(**fields)
            else:
                self.book.update_entry(entry.id, **fields)
        except (ValueError, BookError) as exc:
            self.last_error = str(exc)
            self.message.emit(str(exc))
            return False
        except sqlite3.Error as exc:
            self.report_save_error(exc)
            return False
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

    def clear_cell(self, index) -> None:
        self.setData(index, "")

    def insert_before(self, row: int) -> None:
        entry = self.entry_at(row)
        if entry is None:
            return
        with self.book.step("Zeile einfügen"):
            self.book.add_entry(date=entry.date, before_position=entry.position)
        self.beginInsertRows(QModelIndex(), row, row)
        self._load()
        self.endInsertRows()
        self.changed.emit()

    def insert_after(self, row: int) -> None:
        entry = self.entry_at(row)
        if entry is None:
            return
        following = self.entry_at(row + 1)
        with self.book.step("Zeile einfügen"):
            self.book.add_entry(date=entry.date, before_position=following.position if following else None)
        self.beginInsertRows(QModelIndex(), row + 1, row + 1)
        self._load()
        self.endInsertRows()
        self.changed.emit()

    def delete_rows(self, rows: list[int]) -> None:
        ids = [self.rows[row].id for row in rows if row < len(self.rows)]
        self.book.delete_entries(ids)
        self.reload()
        self.changed.emit()


class AccountsModel(LedgerModel):
    """Kontenplan wie bei Banana: Konten mit «Summe in» und Gruppenzeilen als Totale."""

    GROUP, NUMBER, NAME, KLASS, SUM_IN, OPENING, BALANCE = range(7)
    HEADERS = ["Gruppe", "Konto", "Bezeichnung", "Klasse", "Summe in", "Eröffnung", "Saldo"]
    FIRST_COLUMN = NUMBER

    order_changed = Signal()

    def __init__(self, book: Book, parent=None):
        super().__init__(parent)
        self.book = book
        self.rows: list[ChartRow] = []
        self.balances: dict[int, int] = {}
        self.group_balances: dict[str, int] = {}
        self.profit = 0
        self.needs_resort = False
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
        # Die Reihenfolge bleibt, bis die Tabelle sie mit resort() neu ordnet.
        by_key = {row.key: row for row in rows}
        kept = [
            row if row.kind == "blank" else by_key.pop(row.key)
            for row in self.rows
            if row.kind == "blank" or row.key in by_key
        ]
        self.rows = kept + list(by_key.values())

    def reload(self) -> None:
        """Lädt neu und ordnet alle Zeilen in den Gruppenbaum ein."""
        self.needs_resort = False
        self.beginResetModel()
        self._load(sort=True)
        self.endResetModel()

    def resort(self) -> None:
        """Ordnet neu. Eingefügte leere Zeilen bleiben vor ihrem Nachbarn stehen."""
        blanks = []
        for position, row in enumerate(self.rows):
            if row.kind == "blank":
                following = (r.key for r in self.rows[position + 1 :] if r.kind != "blank")
                blanks.append((row, next(following, None)))
        self.needs_resort = False
        self.beginResetModel()
        self._load(sort=True)
        for blank, key in blanks:
            position = next((i for i, r in enumerate(self.rows) if r.key == key), len(self.rows))
            self.rows.insert(position, blank)
        self.endResetModel()

    def position_of(self, row: ChartRow | None) -> int:
        """Findet eine Zeile nach dem Neuordnen wieder, sonst die leere Zeile am Ende."""
        for position, candidate in enumerate(self.rows):
            if candidate is row or (row and row.kind != "blank" and candidate.key == row.key):
                return position
        return len(self.rows)

    def _refresh(self) -> None:
        count = len(self.rows)
        blanks = sum(row.kind == "blank" for row in self.rows)
        added = len(self.book.chart_rows()) - (count - blanks)
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
        if role != DISPLAY:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return str(section + 1) if section < len(self.rows) else "*"

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
        if row is None or row.kind == "blank":
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
        if row is None or row.kind == "blank":
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
        before = self.data(index, EDIT)
        try:
            if row is None or row.kind == "blank":
                if not text.strip():
                    return False
                key = self._add(column, text.strip(), row.parent if row else "")
                if row:
                    self.rows[index.row()] = next(r for r in self.book.chart_rows() if r.key == key)
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
        except sqlite3.Error as exc:
            self.report_save_error(exc)
            return False
        self._refresh()
        if column in (self.GROUP, self.NUMBER, self.SUM_IN) and text.strip() != (before or ""):
            self.needs_resort = True
            self.order_changed.emit()
        return True

    def _add(self, column: int, text: str, parent: str) -> tuple[str, int]:
        """Legt eine Gruppe oder ein Konto an und gibt den Zeilenschlüssel zurück."""
        if column == self.GROUP:
            return "group", self.book.add_group(text, "", parent)
        klass = guess_klass(text)
        if not parent:
            # Ohne Einfügestelle gilt die Gruppe des vorangehenden Kontos derselben Klasse.
            key = natural_key(text)
            before = [a for a in self.book.accounts() if a.klass == klass and natural_key(a.number) < key]
            parent = before[-1].group if before else ""
        return "account", self.book.add_account(text, "", klass, parent)

    def clear_cell(self, index) -> None:
        if index.column() != self.KLASS and index.flags() & Qt.ItemFlag.ItemIsEditable:
            self.setData(index, "")

    def insert_before(self, row: int) -> None:
        """Fügt eine leere Zeile ein. Ein Eintrag dort gehört zur Gruppe dieser Stelle."""
        target = self.row_at(row)
        if target is None:
            return
        parent = target.item.code if target.kind == "group" else target.parent
        self.beginInsertRows(QModelIndex(), row, row)
        self.rows.insert(row, ChartRow("blank", None, target.depth, parent))
        self.endInsertRows()

    def insert_after(self, row: int) -> None:
        """Fügt eine leere Zeile darunter ein. Unter einer Gruppe liegt sie ausserhalb davon."""
        target = self.row_at(row)
        if target is None:
            return
        self.beginInsertRows(QModelIndex(), row + 1, row + 1)
        self.rows.insert(row + 1, ChartRow("blank", None, target.depth, target.parent))
        self.endInsertRows()

    def delete_rows(self, rows: list[int]) -> None:
        """Löscht Zeilen. Konten zuerst, damit ihre Gruppen danach leer sein können."""
        chart_rows = [self.rows[row] for row in rows if row < len(self.rows)]
        ordered = sorted(chart_rows, key=lambda r: r.kind != "account")
        errors = []
        with self.book.step("Zeilen löschen"):
            for row in ordered:
                try:
                    if row.kind == "group":
                        self.book.delete_group(row.item.id)
                    elif row.kind == "account":
                        self.book.delete_account(row.item.id)
                except BookError as exc:
                    errors.append(str(exc))
        self.reload()
        self.changed.emit()
        if errors:
            prefix = f"{len(errors)} Zeilen nicht gelöscht: " if len(errors) > 1 else ""
            self.message.emit(prefix + errors[0])

    def group_labels(self) -> list[str]:
        return [g.label for g in self.book.groups()]
