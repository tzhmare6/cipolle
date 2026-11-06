"""Startpunkt: ``python -m cipolle [datei.cipolle]``."""

from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QLibraryInfo, QLocale, QTranslator, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

from .ui.branding import StartDialog, app_icon
from .ui.main_window import MainWindow

_reporting_error = False


class CipolleApplication(QApplication):
    """macOS meldet Dateien aus dem Finder als Ereignis, nicht als Argument."""

    file_opened = Signal(str)

    def event(self, event):
        if event.type() == QEvent.Type.FileOpen:
            self.file_opened.emit(event.file())
            return True
        return super().event(event)


def configure(app: QApplication) -> None:
    app.setApplicationName("Cipolle")
    app.setOrganizationName("Cipolle")
    app.setDesktopFileName("cipolle")
    app.setStyle("Fusion")
    app.setWindowIcon(app_icon())
    QLocale.setDefault(QLocale(QLocale.Language.German, QLocale.Country.Switzerland))
    translator = QTranslator(app)
    if translator.load("qtbase_de", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)


def report_unexpected_error(kind, error, trace) -> None:
    """Zeigt Fehler, die sonst nur auf einer oft fehlenden Konsole erscheinen."""
    global _reporting_error
    sys.__excepthook__(kind, error, trace)
    if _reporting_error or issubclass(kind, KeyboardInterrupt):
        return
    _reporting_error = True
    try:
        text = f"Die letzte Aktion wurde möglicherweise nicht gespeichert.\n\n{error}"
        QMessageBox.critical(None, "Unerwarteter Fehler", text)
    finally:
        _reporting_error = False


def main() -> int:
    app = CipolleApplication(sys.argv)
    configure(app)
    sys.excepthook = report_unexpected_error
    window = MainWindow()
    app.file_opened.connect(window.open_from_system)
    window.show()
    window.open_initial(sys.argv[1] if len(sys.argv) > 1 else None)
    StartDialog(window).open()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
