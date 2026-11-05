"""Erscheinungsbild: App-Icon, Hintergrundbild und Startdialog."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QMovie, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import QAbstractScrollArea, QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget

from .. import __authors__, __version__

ASSETS = Path(__file__).resolve().parent.parent / "assets"
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
BACKDROP_OPACITY = 0.10
BACKDROP_MARGIN = 24
ALTERNATE_ROW = QColor(0, 0, 0, 10)
START_HOLD_MS = 1800


def app_icon() -> QIcon:
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addFile(str(ASSETS / f"icon_{size}.png"), QSize(size, size))
    return icon


class Backdrop(QObject):
    """Zeichnet das Logo aufgehellt hinter den Inhalt der angemeldeten Flächen.

    Alle Flächen teilen sich ein Bild, das in ``anchor`` zentriert ist. Dadurch
    steht es auf jedem Reiter an derselben Stelle.
    """

    def __init__(self, anchor: QWidget):
        super().__init__(anchor)
        self.anchor = anchor
        self.source = QPixmap(str(ASSETS / "logo.png"))
        self.scaled = QPixmap()

    def attach(self, widget: QWidget) -> None:
        """Meldet eine Fläche an. Bei Listen und Texten ist das ihr Viewport."""
        if isinstance(widget, QAbstractScrollArea):
            palette = widget.palette()
            palette.setColor(QPalette.ColorRole.AlternateBase, ALTERNATE_ROW)
            widget.setPalette(palette)
            # Beim Rollen verschiebt Qt nur die Pixel, das Bild soll aber stehen bleiben.
            for bar in (widget.verticalScrollBar(), widget.horizontalScrollBar()):
                bar.valueChanged.connect(widget.viewport().update)
            widget = widget.viewport()
        widget.installEventFilter(self)

    def _picture(self) -> QPixmap:
        space = self.anchor.size() - QSize(2 * BACKDROP_MARGIN, 2 * BACKDROP_MARGIN)
        fitted = self.source.size().scaled(space, Qt.AspectRatioMode.KeepAspectRatio)
        if self.scaled.size() != fitted and fitted.isValid() and not fitted.isEmpty():
            self.scaled = self.source.scaled(
                fitted, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        return self.scaled

    def eventFilter(self, widget, event):
        if event.type() == QEvent.Type.Paint:
            picture = self._picture()
            area = QRect(QPoint(0, 0), picture.size())
            area.moveCenter(self.anchor.rect().center())
            painter = QPainter(widget)
            painter.setOpacity(BACKDROP_OPACITY)
            painter.drawPixmap(area.topLeft() - widget.mapTo(self.anchor, QPoint(0, 0)), picture)
            painter.end()
        return False


class StartDialog(QDialog):
    """Zeigt die Animation einmal ab und nennt Version und Autoren.

    Beim Programmstart schliesst er sich danach von selbst, ein Klick oder eine
    Taste schliesst ihn sofort. Unter «Über Cipolle» bleibt er offen.
    """

    def __init__(self, parent=None, auto_close: bool = True):
        super().__init__(parent)
        self.auto_close = auto_close
        self.setWindowTitle("Über Cipolle")
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("white"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#3b2a20"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        self.movie = QMovie(str(ASSETS / "start.gif"), parent=self)
        self.movie.frameChanged.connect(self._frame_changed)
        self.animation = QLabel()
        self.animation.setMovie(self.movie)
        self.animation.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info = QLabel(
            f"<b>Cipolle {__version__}</b><br>"
            "Lokale doppelte Buchhaltung. Alle Daten bleiben auf diesem Rechner.<br>"
            f"Autoren: {', '.join(__authors__)}"
        )
        self.info.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 16)
        layout.addWidget(self.animation)
        layout.addWidget(self.info)
        if auto_close:
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        else:
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            buttons.button(QDialogButtonBox.StandardButton.Close).setText("Schliessen")
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)
            layout.setContentsMargins(0, 0, 16, 16)
        self.movie.start()

    def _frame_changed(self, frame: int) -> None:
        """Hält auf dem letzten Bild an, denn von dort springt die Animation sonst zurück."""
        if frame == self.movie.frameCount() - 1:
            self.movie.setPaused(True)
            if self.auto_close:
                QTimer.singleShot(START_HOLD_MS, self.accept)

    def mousePressEvent(self, event):
        if self.auto_close:
            self.accept()
        else:
            super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if self.auto_close:
            self.accept()
        else:
            super().keyPressEvent(event)
