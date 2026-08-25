from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTextBrowser,
    QVBoxLayout,
)

from landesigner.services.app_changelog import app_version, changelog_path, load_changelog_markdown
from landesigner.ui.dialogs.inventory_dialogs import _russian_buttons


class ChangelogDialog(QDialog):
    """Просмотр CHANGELOG.md внутри приложения."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("История изменений")
        self.resize(720, 520)

        layout = QVBoxLayout(self)
        path = changelog_path()
        hint = QLabel(
            f"LanDesigner {app_version()}"
            + (f" · {path.name}" if path is not None else ""),
            self,
        )
        hint.setObjectName("PanelSubtitle")
        hint.setProperty("muted", True)
        layout.addWidget(hint)

        browser = QTextBrowser(self)
        browser.setOpenExternalLinks(True)
        browser.setMarkdown(load_changelog_markdown())
        layout.addWidget(browser, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        _russian_buttons(buttons)
        buttons.rejected.connect(self.reject)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.clicked.connect(self.accept)
        layout.addWidget(buttons)


class AboutDialog(QDialog):
    """Краткие сведения о программе."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("О программе")
        self.resize(420, 220)

        layout = QVBoxLayout(self)
        title = QLabel(f"<h2>LanDesigner</h2>", self)
        title.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(title)
        body = QLabel(
            f"<p>LAN CAD + CMDB lite</p>"
            f"<p>Версия <b>{app_version()}</b></p>"
            f"<p>Локальные проекты <code>.lanproj</code>, схема, план, стойка, "
            f"инвентарь, отчёты и синхронизация.</p>",
            self,
        )
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(body)
        layout.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        _russian_buttons(buttons)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
