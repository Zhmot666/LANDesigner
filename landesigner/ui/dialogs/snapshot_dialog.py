from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from landesigner.services import snapshots as snap_svc
from landesigner.ui.dialogs.inventory_dialogs import _russian_buttons


class SnapshotRestoreDialog(QDialog):
    def __init__(self, project_file: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Восстановить снимок")
        self.resize(520, 320)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel("Выберите снимок. Перед восстановлением будет создан safety-снимок.", self)
        )
        self._list = QListWidget(self)
        for info in snap_svc.list_snapshots(project_file):
            stamp = info.created_at.strftime("%Y-%m-%d %H:%M:%S")
            item = QListWidgetItem(f"{info.name}  ·  {stamp}  ·  {info.size_bytes // 1024} КБ")
            item.setData(Qt.ItemDataRole.UserRole, str(info.path))
            self._list.addItem(item)
        layout.addWidget(self._list)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        _russian_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if self._list.count():
            self._list.setCurrentRow(0)

    def selected_path(self) -> str | None:
        item = self._list.currentItem()
        if item is None:
            return None
        return str(item.data(Qt.ItemDataRole.UserRole))
