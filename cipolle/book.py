"""Die Buchhaltungsdatei: eine SQLite-Datei pro Geschäftsjahr.

Jede Änderung wird sofort gespeichert. Konten werden über eine interne ID
referenziert, deshalb lassen sich Kontonummern nachträglich ändern.
"""

from __future__ import annotations

import calendar
import functools
import shutil
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .parsing import format_amount, format_date, natural_key
from .templates import ASSET, EXPENSE, KLASS_NAMES, LIABILITY, REVENUE, Chart

APPLICATION_ID = 0x43495030  # "CIP0"
SCHEMA_VERSION = 3
MAX_UNDO_STEPS = 500
UNDO_TABLES = ("meta", "groups", "accounts", "entries")
FILE_SUFFIX = ".cipolle"

UNDO_SCHEMA = """
CREATE TABLE undo_steps (
    id INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    undone INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE undo_log (
    id INTEGER PRIMARY KEY,
    step_id INTEGER NOT NULL REFERENCES undo_steps(id),
    tbl TEXT NOT NULL,
    pk TEXT NOT NULL,
    sql TEXT NOT NULL
);
CREATE INDEX undo_log_step ON undo_log(step_id);
"""

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE groups (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT '',
    parent_id INTEGER REFERENCES groups(id)
);
CREATE TABLE accounts (
    id INTEGER PRIMARY KEY,
    number TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT '',
    klass INTEGER NOT NULL CHECK (klass BETWEEN 1 AND 4),
    group_id INTEGER REFERENCES groups(id),
    opening INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE entries (
    id INTEGER PRIMARY KEY,
    position INTEGER NOT NULL,
    date TEXT,
    doc TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL DEFAULT '',
    debit_id INTEGER REFERENCES accounts(id),
    credit_id INTEGER REFERENCES accounts(id),
    amount INTEGER
);
CREATE INDEX entries_position ON entries(position);
""" + UNDO_SCHEMA


MIGRATE_V1 = """
CREATE TABLE groups (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT '',
    parent_id INTEGER REFERENCES groups(id)
);
ALTER TABLE accounts ADD COLUMN group_id INTEGER REFERENCES groups(id);
"""


class BookError(Exception):
    """Fehler, der dem Benutzer direkt angezeigt werden kann."""


def undoable(label: str):
    """Macht aus einer Änderungsfunktion einen Schritt für «Rückgängig»."""

    def decorate(method):
        @functools.wraps(method)
        def wrapper(self, *args, **kwargs):
            with self.step(label):
                return method(self, *args, **kwargs)

        return wrapper

    return decorate


@dataclass(frozen=True)
class Account:
    id: int
    number: str
    name: str
    klass: int
    group: str  # Code der Gruppe (Spalte «Summe in»), leer wenn keine
    opening: int  # in natürlicher Richtung: Guthaben der Passiven sind positiv

    @property
    def label(self) -> str:
        return f"{self.number} {self.name}".strip()

    @property
    def is_balance_sheet(self) -> bool:
        return self.klass in (ASSET, LIABILITY)

    @property
    def debit_normal(self) -> bool:
        return self.klass in (ASSET, EXPENSE)


@dataclass(frozen=True)
class Group:
    id: int
    code: str
    name: str
    parent: str  # Code der übergeordneten Gruppe, leer wenn keine

    @property
    def label(self) -> str:
        return f"{self.code} {self.name}".strip()


@dataclass(frozen=True)
class ChartRow:
    """Eine Zeile des Kontenplans. ``item`` fehlt bei der Zeile für den Jahreserfolg."""

    kind: str  # "account", "group" oder "profit"
    item: Account | Group | None
    depth: int
    parent: str = ""

    @property
    def key(self) -> tuple[str, int]:
        return self.kind, self.item.id if self.item else 0


@dataclass(frozen=True)
class HistoryResult:
    """Was «Rückgängig» oder «Wiederholen» zuletzt berührt hat."""

    label: str
    table: str
    row_id: int | None  # fehlt, wenn die Zeile nicht mehr existiert


@dataclass(frozen=True)
class Entry:
    id: int
    position: int
    date: date | None
    doc: str
    text: str
    debit_id: int | None
    credit_id: int | None
    amount: int | None


class Book:
    def __init__(self, path: Path, connection: sqlite3.Connection):
        self.path = path
        self.db = connection
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self._step_id: int | None = None
        self.db.create_function("cipolle_undo_step", 0, lambda: self._step_id)

    # -- Datei ---------------------------------------------------------

    @classmethod
    def create(
        cls,
        path: str | Path,
        company: str,
        start: date,
        end: date,
        chart: Chart | None = None,
    ) -> "Book":
        path = Path(path)
        if path.exists():
            raise BookError(f"Die Datei existiert bereits: {path}")
        if end < start:
            raise BookError("Das Geschäftsjahr endet vor seinem Beginn.")
        connection = sqlite3.connect(path)
        book = cls(path, connection)
        with book.db:
            book.db.execute(f"PRAGMA application_id = {APPLICATION_ID}")
            book.db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            book.db.executescript(SCHEMA)
            book.set_properties(company, start, end)
            book._apply_chart(chart or Chart())
        book._install_undo_triggers()
        return book

    def _apply_chart(self, chart: Chart) -> None:
        for code, name, _parent in chart.groups:
            self.add_group(code, name)
        for code, _name, parent in chart.groups:
            if parent:
                self.update_group(self.group_by_code(code).id, parent=parent)
        for number, name, klass, group in chart.accounts:
            self.add_account(number, name, klass, group)
        self.set_profit_group(chart.profit_group)

    def chart(self) -> Chart:
        return Chart(
            [(g.code, g.name, g.parent) for g in self.groups()],
            [(a.number, a.name, a.klass, a.group) for a in self.accounts()],
            self.profit_group,
        )

    @classmethod
    def open(cls, path: str | Path, backup: bool = True) -> "Book":
        path = Path(path)
        if not path.is_file():
            raise BookError(f"Datei nicht gefunden: {path}")
        connection = sqlite3.connect(path)
        try:
            application_id = connection.execute("PRAGMA application_id").fetchone()[0]
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        except sqlite3.DatabaseError as exc:
            connection.close()
            raise BookError(f"Keine Cipolle-Datei: {path}") from exc
        if application_id != APPLICATION_ID:
            connection.close()
            raise BookError(f"Keine Cipolle-Datei: {path}")
        if version > SCHEMA_VERSION:
            connection.close()
            raise BookError("Die Datei stammt von einer neueren Cipolle-Version.")
        if backup:
            shutil.copy2(path, path.with_name(path.name + ".bak"))
        book = cls(path, connection)
        if version < 2:
            book._migrate_from_v1()
        if version < 3:
            book.db.executescript(UNDO_SCHEMA + f"PRAGMA user_version = {SCHEMA_VERSION};")
        book._install_undo_triggers()
        return book

    def _migrate_from_v1(self) -> None:
        """Wandelt die frühere Gruppenbezeichnung pro Konto in echte Gruppen um."""
        names = []
        for row in self.db.execute("SELECT number, grp FROM accounts").fetchall():
            names.append((natural_key(row["number"]), row["grp"]))
        ordered = list(dict.fromkeys(name for _key, name in sorted(names) if name))
        with self.db:
            self.db.executescript(MIGRATE_V1)
            for index, name in enumerate(ordered, start=1):
                cursor = self.db.execute(
                    "INSERT INTO groups (code, name) VALUES (?, ?)", (f"G{index}", name)
                )
                self.db.execute(
                    "UPDATE accounts SET group_id = ? WHERE grp = ?", (cursor.lastrowid, name)
                )
                if name == "Eigenkapital":
                    self.db.execute(
                        "INSERT INTO meta (key, value) VALUES ('profit_group', ?)",
                        (str(cursor.lastrowid),),
                    )
            self.db.execute("ALTER TABLE accounts DROP COLUMN grp")
            self.db.execute("PRAGMA user_version = 2")

    def close(self) -> None:
        self.db.close()

    # -- Rückgängig ----------------------------------------------------

    def _install_undo_triggers(self) -> None:
        """Erzeugt die Trigger, die zu jeder Änderung den Umkehrbefehl schreiben.

        TEMP-Trigger leben nur in dieser Verbindung. Sie passen deshalb immer
        zum aktuellen Schema, und fremde Werkzeuge schreiben nicht ins Log.
        """
        for table in UNDO_TABLES:
            info = self.db.execute(f"PRAGMA table_info({table})").fetchall()
            columns = [f'"{row["name"]}"' for row in info]
            pk = next(f'"{row["name"]}"' for row in info if row["pk"])

            assignments = " || ',' || ".join(f"'{c}=' || quote(old.{c})" for c in columns)
            originals = " || ',' || ".join(f"quote(old.{c})" for c in columns)
            changed = " OR ".join(f"old.{c} IS NOT new.{c}" for c in columns)
            recording = "cipolle_undo_step() IS NOT NULL"
            log = f"INSERT INTO undo_log (step_id, tbl, pk, sql) VALUES (cipolle_undo_step(), '{table}'"
            self.db.executescript(
                f"""
                CREATE TEMP TRIGGER undo_{table}_insert AFTER INSERT ON main.{table}
                WHEN {recording} BEGIN
                    {log}, new.{pk}, 'DELETE FROM {table} WHERE {pk}=' || quote(new.{pk}));
                END;
                CREATE TEMP TRIGGER undo_{table}_update AFTER UPDATE ON main.{table}
                WHEN {recording} AND ({changed}) BEGIN
                    {log}, old.{pk}, 'UPDATE {table} SET ' || {assignments}
                        || ' WHERE {pk}=' || quote(old.{pk}));
                END;
                CREATE TEMP TRIGGER undo_{table}_delete AFTER DELETE ON main.{table}
                WHEN {recording} BEGIN
                    {log}, old.{pk}, 'INSERT INTO {table} ({", ".join(columns)}) VALUES ('
                        || {originals} || ')');
                END;
                """
            )

    @contextmanager
    def step(self, label: str):
        """Fasst alle Änderungen im Block zu einem Rückgängig-Schritt zusammen."""
        if self._step_id is not None:
            yield
            return
        with self.db:
            self._step_id = self.db.execute(
                "INSERT INTO undo_steps (label) VALUES (?)", (label,)
            ).lastrowid
        try:
            yield
        finally:
            step_id, self._step_id = self._step_id, None
            self._finish_step(step_id)

    def _finish_step(self, step_id: int) -> None:
        with self.db:
            logged = self.db.execute("SELECT 1 FROM undo_log WHERE step_id = ? LIMIT 1", (step_id,)).fetchone()
            if not logged:
                self.db.execute("DELETE FROM undo_steps WHERE id = ?", (step_id,))
                return
            # Eine neue Änderung beendet die Möglichkeit, Zurückgenommenes zu wiederholen.
            self.db.execute(
                "DELETE FROM undo_log WHERE step_id IN (SELECT id FROM undo_steps WHERE undone = 1)"
            )
            self.db.execute("DELETE FROM undo_steps WHERE undone = 1")
            oldest = "SELECT id FROM undo_steps ORDER BY id DESC LIMIT -1 OFFSET ?"
            self.db.execute(f"DELETE FROM undo_log WHERE step_id IN ({oldest})", (MAX_UNDO_STEPS,))
            self.db.execute(f"DELETE FROM undo_steps WHERE id IN ({oldest})", (MAX_UNDO_STEPS,))

    def _next_undo(self) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT id, label FROM undo_steps WHERE undone = 0 ORDER BY id DESC LIMIT 1"
        ).fetchone()

    def _next_redo(self) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT id, label FROM undo_steps WHERE undone = 1 ORDER BY id LIMIT 1"
        ).fetchone()

    @property
    def undo_label(self) -> str | None:
        row = self._next_undo()
        return row["label"] if row else None

    @property
    def redo_label(self) -> str | None:
        row = self._next_redo()
        return row["label"] if row else None

    def undo(self) -> HistoryResult | None:
        row = self._next_undo()
        return self._replay(row, 1) if row else None

    def redo(self) -> HistoryResult | None:
        row = self._next_redo()
        return self._replay(row, 0) if row else None

    def _replay(self, step: sqlite3.Row, undone: int) -> HistoryResult:
        """Führt die Umkehrbefehle rückwärts aus. Die Trigger schreiben dabei die Gegenrichtung."""
        rows = self.db.execute(
            "SELECT tbl, pk, sql FROM undo_log WHERE step_id = ? ORDER BY id DESC", (step["id"],)
        ).fetchall()
        self._step_id = step["id"]
        try:
            with self.db:
                self.db.execute("DELETE FROM undo_log WHERE step_id = ?", (step["id"],))
                for row in rows:
                    self.db.execute(row["sql"])
                self.db.execute("UPDATE undo_steps SET undone = ? WHERE id = ?", (undone, step["id"]))
        finally:
            self._step_id = None
        for row in rows:
            if row["tbl"] != "meta":
                found = self.db.execute(f"SELECT id FROM {row['tbl']} WHERE id = ?", (row["pk"],)).fetchone()
                if found:
                    return HistoryResult(step["label"], row["tbl"], found["id"])
        return HistoryResult(step["label"], rows[0]["tbl"], None)

    def clear_undo(self) -> None:
        with self.db:
            self.db.execute("DELETE FROM undo_log")
            self.db.execute("DELETE FROM undo_steps")

    # -- Eigenschaften -------------------------------------------------

    def _meta(self, key: str) -> str:
        return self.db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()[0]

    @property
    def company(self) -> str:
        return self._meta("company")

    @property
    def start(self) -> date:
        return date.fromisoformat(self._meta("start"))

    @property
    def end(self) -> date:
        return date.fromisoformat(self._meta("end"))

    @undoable("Eigenschaften ändern")
    def set_properties(self, company: str, start: date, end: date) -> None:
        if end < start:
            raise BookError("Das Geschäftsjahr endet vor seinem Beginn.")
        with self.db:
            self.db.executemany(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                [
                    ("company", company),
                    ("start", start.isoformat()),
                    ("end", end.isoformat()),
                ],
            )

    # -- Gruppen -------------------------------------------------------

    GROUP_QUERY = (
        "SELECT g.id, g.code, g.name, COALESCE(p.code, '') AS parent "
        "FROM groups g LEFT JOIN groups p ON p.id = g.parent_id"
    )

    @staticmethod
    def _group(row: sqlite3.Row) -> Group:
        return Group(row["id"], row["code"], row["name"], row["parent"])

    def groups(self) -> list[Group]:
        rows = self.db.execute(self.GROUP_QUERY).fetchall()
        return sorted(map(self._group, rows), key=lambda g: natural_key(g.code))

    def group(self, group_id: int) -> Group:
        row = self.db.execute(f"{self.GROUP_QUERY} WHERE g.id = ?", (group_id,)).fetchone()
        if row is None:
            raise BookError("Gruppe nicht gefunden.")
        return self._group(row)

    def group_by_code(self, code: str) -> Group | None:
        row = self.db.execute(f"{self.GROUP_QUERY} WHERE g.code = ?", (code,)).fetchone()
        return self._group(row) if row else None

    def _group_id(self, text: str) -> int | None:
        """Findet die Gruppe aus ``Code`` oder ``Code Bezeichnung``. Leer ergibt ``None``."""
        words = text.split()
        if not words:
            return None
        group = self.group_by_code(words[0])
        if group is None:
            raise BookError(f"Gruppe «{words[0]}» nicht gefunden.")
        return group.id

    @undoable("Gruppe anlegen")
    def add_group(self, code: str, name: str = "", parent: str = "") -> int:
        code = code.strip()
        self._check_group_code(code)
        if self.group_by_code(code):
            raise BookError(f"Die Gruppe {code} existiert bereits.")
        with self.db:
            cursor = self.db.execute(
                "INSERT INTO groups (code, name, parent_id) VALUES (?, ?, ?)",
                (code, name.strip(), self._group_id(parent)),
            )
        return cursor.lastrowid

    @undoable("Gruppe ändern")
    def update_group(self, group_id: int, **fields) -> None:
        current = self.group(group_id)
        code = fields.get("code", current.code).strip()
        name = fields.get("name", current.name).strip()
        parent_id = self._group_id(fields.get("parent", current.parent))
        self._check_group_code(code)
        other = self.group_by_code(code)
        if other and other.id != group_id:
            raise BookError(f"Die Gruppe {code} existiert bereits.")
        ancestor = parent_id
        while ancestor is not None:
            if ancestor == group_id:
                raise BookError("Eine Gruppe kann nicht in sich selbst summieren.")
            ancestor = self.db.execute(
                "SELECT parent_id FROM groups WHERE id = ?", (ancestor,)
            ).fetchone()[0]
        with self.db:
            self.db.execute(
                "UPDATE groups SET code = ?, name = ?, parent_id = ? WHERE id = ?",
                (code, name, parent_id, group_id),
            )

    @staticmethod
    def _check_group_code(code: str) -> None:
        if not code:
            raise BookError("Der Gruppencode darf nicht leer sein.")
        if " " in code:
            raise BookError("Der Gruppencode darf keine Leerzeichen enthalten.")

    @undoable("Gruppe löschen")
    def delete_group(self, group_id: int) -> None:
        used = self.db.execute(
            "SELECT 1 FROM accounts WHERE group_id = ? "
            "UNION SELECT 1 FROM groups WHERE parent_id = ? LIMIT 1",
            (group_id, group_id),
        ).fetchone()
        if used:
            raise BookError("In die Gruppe summieren noch Konten oder Gruppen, sie kann nicht gelöscht werden.")
        with self.db:
            self.db.execute("DELETE FROM meta WHERE key = 'profit_group' AND value = ?", (str(group_id),))
            self.db.execute("DELETE FROM groups WHERE id = ?", (group_id,))

    @property
    def profit_group(self) -> str:
        """Code der Gruppe, in der der Jahreserfolg erscheint, leer wenn keine."""
        row = self.db.execute("SELECT value FROM meta WHERE key = 'profit_group'").fetchone()
        return self.group(int(row[0])).code if row else ""

    @undoable("Gruppe für Jahreserfolg ändern")
    def set_profit_group(self, code: str) -> None:
        group_id = self._group_id(code)
        with self.db:
            self.db.execute("DELETE FROM meta WHERE key = 'profit_group'")
            if group_id is not None:
                self.db.execute(
                    "INSERT INTO meta (key, value) VALUES ('profit_group', ?)", (str(group_id),)
                )

    def chart_rows(self) -> list[ChartRow]:
        """Kontenplan in Baumfolge. Eine Gruppe steht wie ein Total unter ihrem Inhalt."""
        groups = self.groups()
        accounts = self.accounts()
        profit_group = self.profit_group
        rows: list[ChartRow] = []

        def walk(group: Group, depth: int) -> None:
            for account in accounts:
                if account.group == group.code:
                    rows.append(ChartRow("account", account, depth + 1, group.code))
            if group.code == profit_group:
                rows.append(ChartRow("profit", None, depth + 1, group.code))
            for child in groups:
                if child.parent == group.code:
                    walk(child, depth + 1)
            rows.append(ChartRow("group", group, depth, group.parent))

        for group in groups:
            if not group.parent:
                walk(group, 0)
        rows.extend(ChartRow("account", a, 0) for a in accounts if not a.group)
        return rows

    def group_balances(self) -> dict[str, int]:
        """Saldo pro Gruppencode, inklusive Untergruppen und Jahreserfolg.

        Enthält eine Gruppe nur eine Kontenklasse, gilt deren natürliche
        Richtung. Bei gemischten Klassen zählen Aktiven und Ertrag positiv.
        """
        movements = self.movements()
        parents = {g.code: g.parent for g in self.groups()}
        members: dict[str, list[Account]] = {code: [] for code in parents}
        for account in self.accounts():
            code = account.group
            while code:
                members[code].append(account)
                code = parents[code]
        profit_codes = set()
        code = self.profit_group
        while code:
            profit_codes.add(code)
            code = parents[code]
        profit = self.profit()
        result = {}
        for code, accounts in members.items():
            mixed = len({a.klass for a in accounts}) > 1
            total = 0
            for account in accounts:
                amount = self.balance(account, movements)
                negative = mixed and account.klass in (LIABILITY, EXPENSE)
                total += -amount if negative else amount
            result[code] = total + (profit if code in profit_codes else 0)
        return result

    # -- Konten --------------------------------------------------------

    ACCOUNT_QUERY = (
        "SELECT a.id, a.number, a.name, a.klass, a.opening, COALESCE(g.code, '') AS grp "
        "FROM accounts a LEFT JOIN groups g ON g.id = a.group_id"
    )

    @staticmethod
    def _account(row: sqlite3.Row) -> Account:
        return Account(row["id"], row["number"], row["name"], row["klass"], row["grp"], row["opening"])

    def accounts(self) -> list[Account]:
        rows = self.db.execute(self.ACCOUNT_QUERY).fetchall()
        return sorted(map(self._account, rows), key=lambda a: natural_key(a.number))

    def account(self, account_id: int) -> Account:
        row = self.db.execute(f"{self.ACCOUNT_QUERY} WHERE a.id = ?", (account_id,)).fetchone()
        if row is None:
            raise BookError("Konto nicht gefunden.")
        return self._account(row)

    def account_by_number(self, number: str) -> Account | None:
        row = self.db.execute(f"{self.ACCOUNT_QUERY} WHERE a.number = ?", (number,)).fetchone()
        return self._account(row) if row else None

    def resolve_account(self, text: str) -> Account | None:
        """Findet ein Konto aus einer Eingabe im Soll- oder Habenfeld.

        Akzeptiert die Nummer, ``Nummer Bezeichnung`` oder einen Teil davon,
        solange er eindeutig ist. Leere Eingabe ergibt ``None``.
        """
        needle = text.strip()
        if not needle:
            return None
        exact = self.account_by_number(needle) or self.account_by_number(needle.split()[0])
        if exact:
            return exact
        lowered = needle.lower()
        matches = [a for a in self.accounts() if lowered in a.label.lower()]
        prefix = [a for a in matches if a.number.startswith(needle)]
        candidates = prefix or matches
        if len(candidates) == 1:
            return candidates[0]
        if candidates:
            raise BookError(f"«{needle}» ist nicht eindeutig ({len(candidates)} Konten).")
        raise BookError(f"Konto «{needle}» nicht gefunden.")

    @undoable("Konto anlegen")
    def add_account(self, number: str, name: str, klass: int, group: str = "", opening: int = 0) -> int:
        number = number.strip()
        self._check_account(number, klass, opening)
        if self.account_by_number(number):
            raise BookError(f"Die Kontonummer {number} existiert bereits.")
        with self.db:
            cursor = self.db.execute(
                "INSERT INTO accounts (number, name, klass, group_id, opening) VALUES (?, ?, ?, ?, ?)",
                (number, name.strip(), klass, self._group_id(group), opening),
            )
        return cursor.lastrowid

    @undoable("Konto ändern")
    def update_account(self, account_id: int, **fields) -> None:
        current = self.account(account_id)
        number = fields.get("number", current.number).strip()
        name = fields.get("name", current.name).strip()
        klass = fields.get("klass", current.klass)
        group_id = self._group_id(fields.get("group", current.group))
        opening = fields.get("opening", current.opening)
        if klass in (EXPENSE, REVENUE):
            opening = 0 if "klass" in fields else opening
        self._check_account(number, klass, opening)
        other = self.account_by_number(number)
        if other and other.id != account_id:
            raise BookError(f"Die Kontonummer {number} existiert bereits.")
        with self.db:
            self.db.execute(
                "UPDATE accounts SET number = ?, name = ?, klass = ?, group_id = ?, opening = ? WHERE id = ?",
                (number, name, klass, group_id, opening, account_id),
            )

    @staticmethod
    def _check_account(number: str, klass: int, opening: int) -> None:
        if not number:
            raise BookError("Die Kontonummer darf nicht leer sein.")
        if " " in number:
            raise BookError("Die Kontonummer darf keine Leerzeichen enthalten.")
        if klass not in KLASS_NAMES:
            raise BookError("Ungültige Kontenklasse.")
        if opening and klass in (EXPENSE, REVENUE):
            raise BookError("Aufwand- und Ertragskonten haben keinen Eröffnungssaldo.")

    def account_is_used(self, account_id: int) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM entries WHERE debit_id = ? OR credit_id = ? LIMIT 1",
            (account_id, account_id),
        ).fetchone()
        return row is not None

    @undoable("Konto löschen")
    def delete_account(self, account_id: int) -> None:
        if self.account_is_used(account_id):
            raise BookError("Das Konto wird in Buchungen verwendet und kann nicht gelöscht werden.")
        with self.db:
            self.db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))

    # -- Buchungen -----------------------------------------------------

    @staticmethod
    def _entry(row: sqlite3.Row) -> Entry:
        return Entry(
            row["id"],
            row["position"],
            date.fromisoformat(row["date"]) if row["date"] else None,
            row["doc"],
            row["text"],
            row["debit_id"],
            row["credit_id"],
            row["amount"],
        )

    def entries(self) -> list[Entry]:
        rows = self.db.execute("SELECT * FROM entries ORDER BY position, id").fetchall()
        return [self._entry(row) for row in rows]

    @undoable("Buchung anlegen")
    def add_entry(
        self,
        date: date | None = None,
        doc: str = "",
        text: str = "",
        debit_id: int | None = None,
        credit_id: int | None = None,
        amount: int | None = None,
        before_position: int | None = None,
    ) -> int:
        with self.db:
            if before_position is None:
                position = self.db.execute(
                    "SELECT COALESCE(MAX(position), 0) + 1 FROM entries"
                ).fetchone()[0]
            else:
                position = before_position
                self.db.execute(
                    "UPDATE entries SET position = position + 1 WHERE position >= ?",
                    (position,),
                )
            cursor = self.db.execute(
                "INSERT INTO entries (position, date, doc, text, debit_id, credit_id, amount) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (position, date.isoformat() if date else None, doc, text, debit_id, credit_id, amount),
            )
        return cursor.lastrowid

    @undoable("Buchung ändern")
    def update_entry(self, entry_id: int, **fields) -> None:
        allowed = {"date", "doc", "text", "debit_id", "credit_id", "amount"}
        if not fields or not set(fields) <= allowed:
            raise ValueError(f"Ungültige Felder: {fields}")
        if "date" in fields and fields["date"] is not None:
            fields["date"] = fields["date"].isoformat()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        with self.db:
            self.db.execute(
                f"UPDATE entries SET {assignments} WHERE id = ?",
                (*fields.values(), entry_id),
            )

    @undoable("Buchungen löschen")
    def delete_entries(self, entry_ids: list[int]) -> None:
        with self.db:
            self.db.executemany("DELETE FROM entries WHERE id = ?", [(i,) for i in entry_ids])

    @undoable("Buchungen sortieren")
    def sort_entries_by_date(self) -> None:
        """Sortiert stabil nach Datum, Zeilen ohne Datum bleiben am Schluss."""
        entries = sorted(self.entries(), key=lambda e: (e.date is None, e.date or date.max))
        with self.db:
            self.db.executemany(
                "UPDATE entries SET position = ? WHERE id = ?",
                [(index, entry.id) for index, entry in enumerate(entries, start=1)],
            )

    # -- Prüfung und Salden --------------------------------------------

    def entry_problems(self) -> dict[int, list[str]]:
        """Liefert pro Buchungs-ID die Fehlermeldungen.

        Zeilen mit nur Soll oder nur Haben gehören zu einer Sammelbuchung.
        Aufeinanderfolgende solche Zeilen müssen sich zu null summieren.
        """
        start, end = self.start, self.end
        problems: dict[int, list[str]] = {}
        open_sum = 0
        last_partial: int | None = None

        def close_group() -> None:
            nonlocal open_sum, last_partial
            if open_sum and last_partial is not None:
                problems.setdefault(last_partial, []).append(
                    f"Sammelbuchung geht nicht auf, Differenz {format_amount(open_sum)}"
                )
            open_sum, last_partial = 0, None

        for entry in self.entries():
            messages = self._row_problems(entry, start, end)
            if messages:
                problems[entry.id] = messages
            partial = bool(entry.debit_id) != bool(entry.credit_id)
            if partial and entry.amount is not None:
                open_sum += entry.amount if entry.debit_id else -entry.amount
                last_partial = entry.id
                if open_sum == 0:
                    last_partial = None
            else:
                close_group()
        close_group()
        return problems

    @staticmethod
    def _row_problems(entry: Entry, start: date, end: date) -> list[str]:
        messages = []
        if entry.date is None:
            messages.append("Datum fehlt")
        elif not start <= entry.date <= end:
            messages.append(f"Datum ausserhalb des Geschäftsjahrs ({format_date(start)} bis {format_date(end)})")
        if not entry.debit_id and not entry.credit_id:
            messages.append("Konto fehlt")
        elif entry.debit_id == entry.credit_id:
            messages.append("Soll und Haben sind dasselbe Konto")
        if entry.amount is None:
            messages.append("Betrag fehlt")
        return messages

    def posted_entries(self) -> list[Entry]:
        """Buchungen, die in den Auswertungen zählen."""
        start, end = self.start, self.end
        return [e for e in self.entries() if not self._row_problems(e, start, end)]

    def movements(self, until: date | None = None, since: date | None = None) -> dict[int, tuple[int, int]]:
        """Soll- und Habenumsatz pro Konto im Zeitraum."""
        totals: dict[int, list[int]] = {}
        for entry in self.posted_entries():
            if until and entry.date > until:
                continue
            if since and entry.date < since:
                continue
            if entry.debit_id:
                totals.setdefault(entry.debit_id, [0, 0])[0] += entry.amount
            if entry.credit_id:
                totals.setdefault(entry.credit_id, [0, 0])[1] += entry.amount
        return {key: (debit, credit) for key, (debit, credit) in totals.items()}

    def balance(self, account: Account, movements: dict[int, tuple[int, int]], with_opening: bool = True) -> int:
        """Saldo in natürlicher Richtung des Kontos."""
        debit, credit = movements.get(account.id, (0, 0))
        change = debit - credit if account.debit_normal else credit - debit
        return (account.opening if with_opening else 0) + change

    def profit(self, until: date | None = None, since: date | None = None) -> int:
        """Ertrag minus Aufwand. Positiv ist Gewinn, negativ Verlust."""
        movements = self.movements(until, since)
        result = 0
        for account in self.accounts():
            if account.klass == REVENUE:
                result += self.balance(account, movements)
            elif account.klass == EXPENSE:
                result -= self.balance(account, movements)
        return result

    def opening_difference(self) -> int:
        """Aktiven minus Passiven der Eröffnungsbilanz."""
        total = 0
        for account in self.accounts():
            if account.klass == ASSET:
                total += account.opening
            elif account.klass == LIABILITY:
                total -= account.opening
        return total

    def posting_difference(self) -> int:
        """Soll minus Haben aller gültigen Buchungen."""
        return sum(debit - credit for debit, credit in self.movements().values())

    def warnings(self) -> list[str]:
        result = []
        problems = self.entry_problems()
        excluded = len(self.entries()) - len(self.posted_entries())
        if excluded:
            subject = "1 fehlerhafte Buchung fehlt" if excluded == 1 else f"{excluded} fehlerhafte Buchungen fehlen"
            result.append(f"{subject} in den Auswertungen.")
        elif problems:
            result.append("1 Buchung hat Fehler." if len(problems) == 1 else f"{len(problems)} Buchungen haben Fehler.")
        difference = self.posting_difference()
        if difference:
            result.append(f"Differenz Soll/Haben: {format_amount(difference)}")
        opening = self.opening_difference()
        if opening:
            result.append(f"Differenz Eröffnungsbilanz: {format_amount(opening)}")
        for code in self._groups_mixing_sides():
            result.append(f"Gruppe {code} enthält Aktiv- und Passivkonten.")
        return result

    def _groups_mixing_sides(self) -> list[str]:
        """Oberste Gruppen, in die Konten beider Bilanzseiten summieren."""
        parents = {g.code: g.parent for g in self.groups()}
        sides: dict[str, set[int]] = {}
        for account in self.accounts():
            code = account.group
            if not code or not account.is_balance_sheet:
                continue
            while parents[code]:
                code = parents[code]
            sides.setdefault(code, set()).add(account.klass)
        return [code for code, klasses in sides.items() if len(klasses) > 1]


def next_period(start: date, end: date) -> tuple[date, date]:
    """Berechnet das Folgejahr, auch über Schaltjahre hinweg."""
    next_start = end + timedelta(days=1)
    year = end.year + 1
    if end.day == calendar.monthrange(end.year, end.month)[1]:
        day = calendar.monthrange(year, end.month)[1]
    else:
        day = end.day
    return next_start, date(year, end.month, day)


def carry_over(source: Book, target: Book, equity_number: str) -> None:
    """Überträgt die Schlusssalden von ``source`` als Eröffnung in ``target``.

    Der Jahreserfolg wird dem Eigenkapitalkonto ``equity_number`` zugewiesen.
    Fehlende Konten werden in ``target`` angelegt.
    """
    if source.end >= target.start:
        raise BookError("Das Vorjahr muss vor dem Beginn dieses Geschäftsjahrs enden.")
    with target.step("Eröffnung aus Vorjahr aktualisieren"):
        _carry_over(source, target, equity_number)


def _carry_over(source: Book, target: Book, equity_number: str) -> None:
    equity = source.account_by_number(equity_number)
    if equity is None or equity.klass != LIABILITY:
        raise BookError("Für den Jahreserfolg wird ein Passivkonto benötigt.")
    movements = source.movements()
    profit = source.profit()
    missing = [g for g in source.groups() if target.group_by_code(g.code) is None]
    for group in missing:
        target.add_group(group.code, group.name)
    for group in missing:
        if group.parent:
            target.update_group(target.group_by_code(group.code).id, parent=group.parent)
    closing = {}
    for account in source.accounts():
        if account.is_balance_sheet:
            closing[account.number] = source.balance(account, movements)
        if target.account_by_number(account.number) is None:
            target.add_account(account.number, account.name, account.klass, account.group)
    closing[equity_number] += profit
    for account in target.accounts():
        if account.is_balance_sheet:
            target.update_account(account.id, opening=closing.get(account.number, 0))


def create_next_year(source: Book, path: str | Path, equity_number: str) -> Book:
    """Erstellt die Datei des Folgejahrs mit Kontenplan und Eröffnungssaldi."""
    start, end = next_period(source.start, source.end)
    target = Book.create(path, source.company, start, end, source.chart())
    carry_over(source, target, equity_number)
    target.clear_undo()
    return target
