"""Startpunkt: ``python -m cipolle [datei.cipolle]``."""

from __future__ import annotations

import sys

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
from PySide6.QtWidgets import QApplication

from .ui.branding import StartDialog, app_icon
from .ui.main_window import MainWindow


def configure(app: QApplication) -> None:
    app.setApplicationName("Cipolle")
    app.setOrganizationName("Cipolle")
    app.setStyle("Fusion")
    app.setWindowIcon(app_icon())
    QLocale.setDefault(QLocale(QLocale.Language.German, QLocale.Country.Switzerland))
    translator = QTranslator(app)
    if translator.load("qtbase_de", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)


def main() -> int:
    app = QApplication(sys.argv)
    configure(app)
    window = MainWindow()
    window.show()
    window.open_initial(sys.argv[1] if len(sys.argv) > 1 else None)
    StartDialog(window).open()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
