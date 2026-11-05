"""Tabellenansicht und Eingabefelder für schnelles Erfassen per Tastatur."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (
    QAbstractItemDelegate,
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QHeaderView,
    QLineEdit,
    QStyledItemDelegate,
    QTableView,
)

from ..templates import KLASS_NAMES
from .models import AccountsModel, EntriesModel

NEXT_KEYS = {Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab}


class LedgerTable(QTableView):
    """Tabelle, in der Enter wie Tab zum nächsten Feld springt."""

    def __init__(self, parent=None):
        super().__init__(parent)
        triggers = QAbstractItemView.EditTrigger
        self.setEditTriggers(triggers.AnyKeyPressed | triggers.DoubleClicked | triggers.EditKeyPressed)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.verticalHeader().setDefaultSectionSize(26)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)

    def keyPressEvent(self, event):
        editing = self.state() == QAbstractItemView.State.EditingState
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not editing:
            self.edit(self.currentIndex())
            return
        super().keyPressEvent(event)

    def edit_neighbour(self, backwards: bool = False) -> None:
        """Öffnet das nächste bearbeitbare Feld und überspringt alle anderen."""
        model = self.model()
        columns = model.columnCount()
        current = self.currentIndex()
        position = current.row() * columns + current.column()
        step = -1 if backwards else 1
        position += step
        while 0 <= position < model.rowCount() * columns:
            index = model.index(*divmod(position, columns))
            if index.flags() & Qt.ItemFlag.ItemIsEditable:
                self.setCurrentIndex(index)
                self.edit(index)
                return
            position += step

    def commit_open_editor(self) -> None:
        """Speichert ein noch offenes Eingabefeld."""
        editor = self.indexWidget(self.currentIndex())
        if editor is not None:
            self.commitData(editor)
            self.closeEditor(editor, QAbstractItemDelegate.EndEditHint.NoHint)

    def selected_rows(self) -> list[int]:
        rows = {index.row() for index in self.selectionModel().selectedIndexes()}
        if not rows and self.currentIndex().isValid():
            rows = {self.currentIndex().row()}
        return sorted(rows)


class PopupKeys(QObject):
    """Leitet Enter und Tab der Vorschlagsliste an das Eingabefeld weiter.

    Ohne diesen Filter schluckt die Liste die Taste, und man müsste sie
    zweimal drücken, um das nächste Feld zu erreichen.
    """

    def __init__(self, delegate: "FormDelegate", editor: QLineEdit):
        super().__init__(editor)
        self.delegate = delegate
        self.editor = editor

    def eventFilter(self, popup, event):
        if event.type() == QEvent.Type.KeyPress and event.key() in NEXT_KEYS | {Qt.Key.Key_Backtab}:
            current = popup.currentIndex()
            if current.isValid():
                self.editor.setText(current.data())
            popup.hide()
            self.delegate.finish(self.editor, event.key())
            return True
        return False


class FormDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rejected = False

    def eventFilter(self, editor, event):
        if event.type() == QEvent.Type.KeyPress and event.key() in NEXT_KEYS | {Qt.Key.Key_Backtab}:
            self.finish(editor, event.key())
            return True
        return super().eventFilter(editor, event)

    def finish(self, editor, key) -> None:
        """Speichert das Feld und geht weiter. Ungültiges bleibt zum Korrigieren offen."""
        self.commitData.emit(editor)
        if self.rejected:
            if isinstance(editor, QLineEdit):
                editor.selectAll()
            return
        self.closeEditor.emit(editor, QAbstractItemDelegate.EndEditHint.NoHint)
        self.parent().edit_neighbour(backwards=key == Qt.Key.Key_Backtab)

    def setModelData(self, editor, model, index):
        model.last_error = None
        self.write(editor, model, index)
        self.rejected = model.last_error is not None

    def write(self, editor, model, index):
        super().setModelData(editor, model, index)

    def attach_completer(self, editor: QLineEdit, values: list[str]) -> None:
        completer = QCompleter(values, editor)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        editor.setCompleter(completer)
        # Der zuletzt installierte Filter läuft zuerst, also vor dem von QCompleter.
        completer.popup().installEventFilter(PopupKeys(self, editor))


class EntriesDelegate(FormDelegate):
    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        model: EntriesModel = index.model()
        column = index.column()
        if column in (model.DEBIT, model.CREDIT):
            self.attach_completer(editor, [a.label for a in model.book.accounts()])
        elif column == model.TEXT:
            self.attach_completer(editor, sorted({e.text for e in model.rows if e.text}))
        elif column == model.AMOUNT:
            editor.setAlignment(Qt.AlignmentFlag.AlignRight)
        return editor


class AccountsDelegate(FormDelegate):
    def createEditor(self, parent, option, index):
        model: AccountsModel = index.model()
        if index.column() == model.KLASS:
            editor = QComboBox(parent)
            for klass, name in KLASS_NAMES.items():
                editor.addItem(name, klass)
            return editor
        editor = QLineEdit(parent)
        if index.column() == model.SUM_IN:
            self.attach_completer(editor, model.group_labels())
        elif index.column() == model.OPENING:
            editor.setAlignment(Qt.AlignmentFlag.AlignRight)
        return editor

    def setEditorData(self, editor, index):
        if isinstance(editor, QComboBox):
            editor.setCurrentIndex(editor.findData(index.data(Qt.ItemDataRole.EditRole)))
        else:
            super().setEditorData(editor, index)

    def write(self, editor, model, index):
        if isinstance(editor, QComboBox):
            model.setData(index, editor.currentData())
        else:
            super().write(editor, model, index)
