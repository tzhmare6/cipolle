"""Export und Import des Kontenplans als JSON.

Die Datei enthält nur die Struktur: Gruppen, Konten und die Gruppe für den
Jahreserfolg. Eröffnungssaldi und Buchungen gehören zum Geschäftsjahr und
bleiben draussen.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .book import Account, Book, BookError, Group
from .templates import ASSET, KLASS_NAMES, LIABILITY, Chart

FORMAT = "cipolle-kontenplan"
VERSION = 1
KLASS_BY_NAME = {name: klass for klass, name in KLASS_NAMES.items()}


def chart_to_json(chart: Chart) -> str:
    data = {
        "format": FORMAT,
        "version": VERSION,
        "jahreserfolg_in": chart.profit_group,
        "gruppen": [{"code": c, "name": n, "summe_in": p} for c, n, p in chart.groups],
        "konten": [
            {"nummer": number, "name": name, "klasse": KLASS_NAMES[klass], "summe_in": group}
            for number, name, klass, group in chart.accounts
        ],
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _text(item: dict, key: str, where: str, required: bool = False) -> str:
    value = item.get(key, "")
    if not isinstance(value, str):
        raise BookError(f"{where}: «{key}» muss ein Text sein.")
    value = value.strip()
    if required and not value:
        raise BookError(f"{where}: «{key}» fehlt.")
    if required and " " in value:
        raise BookError(f"{where}: «{key}» darf keine Leerzeichen enthalten.")
    return value


def _items(data: dict, key: str) -> list[dict]:
    items = data.get(key)
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise BookError(f"Die Liste «{key}» fehlt oder ist ungültig.")
    return items


def parse_chart(text: str) -> Chart:
    """Liest und prüft eine Kontenplan-Datei, bevor irgendetwas geändert wird."""
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise BookError(f"Keine gültige JSON-Datei: {exc}") from exc
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise BookError("Die Datei ist kein Cipolle-Kontenplan.")
    if data.get("version") != VERSION:
        raise BookError(f"Nicht unterstützte Version des Kontenplans: {data.get('version')}")

    groups = []
    for position, item in enumerate(_items(data, "gruppen"), start=1):
        where = f"Gruppe {position}"
        groups.append((_text(item, "code", where, True), _text(item, "name", where), _text(item, "summe_in", where)))
    accounts = []
    for position, item in enumerate(_items(data, "konten"), start=1):
        where = f"Konto {position}"
        klass = _text(item, "klasse", where, True)
        if klass not in KLASS_BY_NAME:
            raise BookError(f"{where}: Unbekannte Klasse «{klass}».")
        accounts.append(
            (_text(item, "nummer", where, True), _text(item, "name", where), KLASS_BY_NAME[klass], _text(item, "summe_in", where))
        )
    profit_group = _text(data, "jahreserfolg_in", "Kontenplan")
    chart = Chart(groups, accounts, profit_group)
    _check_references(chart)
    return chart


def _check_references(chart: Chart) -> None:
    parents = {}
    for code, _name, parent in chart.groups:
        if code in parents:
            raise BookError(f"Die Gruppe {code} kommt doppelt vor.")
        parents[code] = parent
    numbers = set()
    for number, _name, _klass, group in chart.accounts:
        if number in numbers:
            raise BookError(f"Das Konto {number} kommt doppelt vor.")
        numbers.add(number)
        if group and group not in parents:
            raise BookError(f"Konto {number}: Gruppe «{group}» nicht gefunden.")
    for code, parent in parents.items():
        if parent and parent not in parents:
            raise BookError(f"Gruppe {code}: Gruppe «{parent}» nicht gefunden.")
        seen = {code}
        while parent:
            if parent in seen:
                raise BookError(f"Gruppe {code} summiert in sich selbst.")
            seen.add(parent)
            parent = parents[parent]
    if chart.profit_group and chart.profit_group not in parents:
        raise BookError(f"Gruppe «{chart.profit_group}» für den Jahreserfolg nicht gefunden.")


@dataclass
class ImportPlan:
    """Was ein Import ändern würde."""

    new_accounts: list[str] = field(default_factory=list)
    changed_accounts: list[str] = field(default_factory=list)
    removed_accounts: list[Account] = field(default_factory=list)
    kept_accounts: list[Account] = field(default_factory=list)  # hätten Buchungen verloren
    new_groups: list[str] = field(default_factory=list)
    changed_groups: list[str] = field(default_factory=list)
    removed_groups: list[Group] = field(default_factory=list)
    lost_openings: list[str] = field(default_factory=list)
    profit_group_changes: bool = False

    @property
    def has_changes(self) -> bool:
        return any(
            (self.new_accounts, self.changed_accounts, self.removed_accounts,
             self.new_groups, self.changed_groups, self.removed_groups, self.profit_group_changes)
        )


def plan_import(book: Book, chart: Chart, replace: bool) -> ImportPlan:
    plan = ImportPlan()
    plan.profit_group_changes = (bool(chart.profit_group) or replace) and chart.profit_group != book.profit_group
    current_groups = {g.code: g for g in book.groups()}
    for code, name, parent in chart.groups:
        existing = current_groups.get(code)
        if existing is None:
            plan.new_groups.append(code)
        elif (existing.name, existing.parent) != (name, parent):
            plan.changed_groups.append(code)

    current_accounts = {a.number: a for a in book.accounts()}
    for number, name, klass, group in chart.accounts:
        existing = current_accounts.get(number)
        if existing is None:
            plan.new_accounts.append(number)
        elif (existing.name, existing.klass, existing.group) != (name, klass, group):
            plan.changed_accounts.append(number)
            if existing.opening and klass not in (ASSET, LIABILITY):
                plan.lost_openings.append(number)
    if not replace:
        return plan

    imported = {number for number, *_rest in chart.accounts}
    for account in current_accounts.values():
        if account.number in imported:
            continue
        if book.account_is_used(account.id):
            plan.kept_accounts.append(account)
        else:
            plan.removed_accounts.append(account)
            if account.opening:
                plan.lost_openings.append(account.number)

    # Gruppen bleiben, solange ein behaltenes Konto hineinsummiert.
    needed = {code for code, *_rest in chart.groups}
    for account in plan.kept_accounts:
        code = account.group
        while code and code not in needed:
            needed.add(code)
            code = current_groups[code].parent
    plan.removed_groups = [g for g in current_groups.values() if g.code not in needed]
    return plan


def apply_import(book: Book, chart: Chart, replace: bool) -> ImportPlan:
    """Führt den Import als einen Rückgängig-Schritt aus."""
    plan = plan_import(book, chart, replace)
    if not plan.has_changes:
        return plan
    with book.step("Kontenplan importieren"):
        for code, name, parent in chart.groups:
            existing = book.group_by_code(code)
            if existing is None:
                book.add_group(code, name)
            else:
                # Erst lösen, sonst könnte beim Umhängen ein Zwischenstand im Kreis laufen.
                book.update_group(existing.id, name=name, parent=parent if parent == existing.parent else "")
        for code, _name, parent in chart.groups:
            if parent:
                book.update_group(book.group_by_code(code).id, parent=parent)
        for number, name, klass, group in chart.accounts:
            existing = book.account_by_number(number)
            if existing is None:
                book.add_account(number, name, klass, group)
            else:
                book.update_account(existing.id, name=name, klass=klass, group=group)
        if chart.profit_group or replace:
            book.set_profit_group(chart.profit_group)
        if replace:
            for account in plan.removed_accounts:
                book.delete_account(account.id)
            removed = {g.code for g in plan.removed_groups}
            # chart_rows liefert Untergruppen vor ihren Obergruppen.
            for row in book.chart_rows():
                if row.kind == "group" and row.item.code in removed:
                    book.delete_group(row.item.id)
    return plan
