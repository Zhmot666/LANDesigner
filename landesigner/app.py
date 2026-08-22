import sys

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
from PySide6.QtWidgets import QApplication

from landesigner.ui.main_window import MainWindow
from landesigner.ui.icons import app_icon
from landesigner.ui.theme import apply_theme


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("LanDesigner")
    app.setOrganizationName("LanDesigner")
    app.setWindowIcon(app_icon())
    apply_theme(app)

    # Стандартные диалоги Qt (Open/Save, Yes/No) — на русском, если есть перевод.
    QLocale.setDefault(QLocale(QLocale.Language.Russian, QLocale.Country.Russia))
    translator = QTranslator(app)
    translations_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load(QLocale(QLocale.Language.Russian), "qtbase", "_", translations_path):
        app.installTranslator(translator)

    window = MainWindow()
    window.showMaximized()
    sys.exit(app.exec())
