from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from landesigner.ports.remote import RemoteProjectInfo
from landesigner.ui.dialogs.inventory_dialogs import _russian_buttons

SETTINGS_ORG = "LanDesigner"
SETTINGS_APP = "LanDesigner"
KEY_SERVER_URL = "sync/server_url"
KEY_API_TOKEN = "sync/api_token"
DEFAULT_SERVER_URL = "http://127.0.0.1:8765"


def load_sync_settings() -> tuple[str, str]:
    settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
    url = str(settings.value(KEY_SERVER_URL, DEFAULT_SERVER_URL) or DEFAULT_SERVER_URL)
    token = str(settings.value(KEY_API_TOKEN, "") or "")
    return url.rstrip("/"), token


def save_sync_settings(server_url: str, api_token: str) -> None:
    settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
    settings.setValue(KEY_SERVER_URL, server_url.rstrip("/"))
    settings.setValue(KEY_API_TOKEN, api_token)


class SyncSettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Сервер синхронизации")
        self.resize(460, 160)
        url, token = load_sync_settings()
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._url = QLineEdit(url, self)
        self._token = QLineEdit(token, self)
        self._token.setEchoMode(QLineEdit.EchoMode.Password)
        self._token.setPlaceholderText("Необязательно, если сервер без ключа")
        form.addRow("URL сервера", self._url)
        form.addRow("API-ключ", self._token)
        layout.addLayout(form)
        layout.addWidget(
            QLabel(
                "Локальный .lanproj остаётся offline-кэшем.\n"
                "Запуск сервера: python -m server",
                self,
            )
        )
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        _russian_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, str]:
        return self._url.text().strip().rstrip("/"), self._token.text().strip()


class RemoteProjectsDialog(QDialog):
    def __init__(self, projects: list[RemoteProjectInfo], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Проекты на сервере")
        self.resize(560, 360)
        self._selected_id: UUID | None = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Выберите проект для клонирования:", self))
        self._list = QListWidget(self)
        for info in projects:
            stamp = info.updated_at.strftime("%Y-%m-%d %H:%M")
            item = QListWidgetItem(f"{info.name}  ·  rev {info.revision}  ·  {stamp}")
            item.setData(Qt.ItemDataRole.UserRole, str(info.id))
            self._list.addItem(item)
        layout.addWidget(self._list)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        _russian_buttons(buttons)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if self._list.count():
            self._list.setCurrentRow(0)

    def _accept(self) -> None:
        item = self._list.currentItem()
        if item is None:
            QMessageBox.information(self, "Клонирование", "Выберите проект.")
            return
        self._selected_id = UUID(str(item.data(Qt.ItemDataRole.UserRole)))
        self.accept()

    def selected_project_id(self) -> UUID | None:
        return self._selected_id


class SyncConflictDialog(QDialog):
    """Разрешение конфликта: оставить локальное / принять серверное / force push + diff."""

    KEEP_LOCAL = "keep_local"
    TAKE_REMOTE = "take_remote"
    FORCE_PUSH = "force_push"

    def __init__(
        self,
        *,
        title: str,
        message: str,
        allow_force_push: bool,
        details: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(640, 420 if details else 200)
        self.choice: str | None = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(message, self))
        if details.strip():
            layout.addWidget(QLabel("Сравнение локального и серверного:", self))
            viewer = QPlainTextEdit(self)
            viewer.setReadOnly(True)
            viewer.setPlainText(details.strip())
            viewer.setMinimumHeight(180)
            layout.addWidget(viewer, stretch=1)
        row = QHBoxLayout()
        btn_keep = QPushButton("Оставить локальное", self)
        btn_remote = QPushButton("Принять серверное", self)
        btn_keep.clicked.connect(lambda: self._pick(self.KEEP_LOCAL))
        btn_remote.clicked.connect(lambda: self._pick(self.TAKE_REMOTE))
        row.addWidget(btn_keep)
        row.addWidget(btn_remote)
        if allow_force_push:
            btn_force = QPushButton("Принудительный push", self)
            btn_force.clicked.connect(lambda: self._pick(self.FORCE_PUSH))
            row.addWidget(btn_force)
        layout.addLayout(row)
        cancel = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        _russian_buttons(cancel)
        cancel.rejected.connect(self.reject)
        layout.addWidget(cancel)

    def _pick(self, choice: str) -> None:
        self.choice = choice
        self.accept()
