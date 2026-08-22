from __future__ import annotations

import os
from uuid import UUID, uuid4

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
KEY_CLIENT_NAME = "sync/client_name"
KEY_CLIENT_ID = "sync/client_id"
DEFAULT_SERVER_URL = "http://127.0.0.1:8765"


def load_sync_settings() -> tuple[str, str]:
    settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
    url = str(settings.value(KEY_SERVER_URL, DEFAULT_SERVER_URL) or DEFAULT_SERVER_URL)
    token = str(settings.value(KEY_API_TOKEN, "") or "")
    return url.rstrip("/"), token


def load_sync_identity() -> tuple[str, str]:
    """Имя инженера и стабильный client_id для блокировок на сервере."""
    settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
    name = str(settings.value(KEY_CLIENT_NAME, "") or "").strip()
    client_id = str(settings.value(KEY_CLIENT_ID, "") or "").strip()
    if not client_id:
        client_id = str(uuid4())
        settings.setValue(KEY_CLIENT_ID, client_id)
    if not name:
        name = (
            os.environ.get("USERNAME")
            or os.environ.get("USER")
            or os.environ.get("COMPUTERNAME")
            or "Инженер"
        )
    return name, client_id


def save_sync_settings(server_url: str, api_token: str, client_name: str = "") -> None:
    settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
    settings.setValue(KEY_SERVER_URL, server_url.rstrip("/"))
    settings.setValue(KEY_API_TOKEN, api_token)
    if client_name.strip():
        settings.setValue(KEY_CLIENT_NAME, client_name.strip())
    load_sync_identity()


class SyncSettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Сервер синхронизации")
        self.resize(480, 260)
        url, token = load_sync_settings()
        client_name, _ = load_sync_identity()
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._url = QLineEdit(url, self)
        self._token = QLineEdit(token, self)
        self._token.setEchoMode(QLineEdit.EchoMode.Password)
        self._token.setPlaceholderText("Необязательно, если сервер без ключа")
        self._client_name = QLineEdit(client_name, self)
        self._client_name.setPlaceholderText("Отображается при блокировке проекта")
        form.addRow("URL сервера", self._url)
        form.addRow("API-ключ", self._token)
        form.addRow("Ваше имя", self._client_name)
        layout.addLayout(form)
        layout.addWidget(
            QLabel(
                "Локальный .lanproj остаётся offline-кэшем.\n"
                "При открытии привязанного проекта запрашивается блокировка на сервере.\n"
                "Запуск сервера: python -m server",
                self,
            )
        )
        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        self._status.setProperty("muted", True)
        layout.addWidget(self._status)
        test_row = QHBoxLayout()
        self._btn_test = QPushButton("Проверить соединение", self)
        self._btn_test.clicked.connect(self._on_test)
        test_row.addWidget(self._btn_test)
        test_row.addStretch(1)
        layout.addLayout(test_row)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        _russian_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, str, str]:
        return (
            self._url.text().strip().rstrip("/"),
            self._token.text().strip(),
            self._client_name.text().strip(),
        )

    def _on_test(self) -> None:
        from landesigner.adapters.remote import RemoteHttpClient

        url, token = self.values()[:2]
        if not url:
            self._status.setText("Укажите URL сервера.")
            return
        self._btn_test.setEnabled(False)
        self._status.setText("Проверка…")
        try:
            ok, message = RemoteHttpClient(url, api_token=token, timeout_s=8.0).check_connection()
        finally:
            self._btn_test.setEnabled(True)
        self._status.setText(message)
        if not ok:
            QMessageBox.warning(self, "Синхронизация", message)


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
            lock_txt = f"  ·  lock: {info.locked_by}" if info.locked_by else ""
            item = QListWidgetItem(
                f"{info.name}  ·  rev {info.revision}  ·  {stamp}{lock_txt}"
            )
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
