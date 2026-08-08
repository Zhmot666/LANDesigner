from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from landesigner.services import catalog as catalog_svc
from landesigner.ui.dialogs.inventory_dialogs import _russian_buttons
from landesigner.ui.labels import role_label


class DeviceTypeCatalogDialog(QDialog):
    """Выбор готового типа устройства из встроенного каталога."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Каталог типов устройств")
        self.resize(560, 380)
        layout = QVBoxLayout(self)

        hint = QLabel("Выберите шаблон — в проект добавится тип с группами портов.", self)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        body = QHBoxLayout()
        self._list = QListWidget(self)
        self._desc = QLabel("", self)
        self._desc.setWordWrap(True)
        self._desc.setMinimumWidth(220)
        for preset in catalog_svc.list_device_type_presets():
            item = QListWidgetItem(preset.title)
            item.setData(Qt.ItemDataRole.UserRole, preset.key)
            self._list.addItem(item)
        self._list.currentItemChanged.connect(self._on_sel)
        body.addWidget(self._list, stretch=1)
        body.addWidget(self._desc, stretch=1)
        layout.addLayout(body)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        _russian_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if self._list.count():
            self._list.setCurrentRow(0)

    def _on_sel(self, current: QListWidgetItem | None, _prev) -> None:
        if current is None:
            self._desc.setText("")
            return
        key = str(current.data(Qt.ItemDataRole.UserRole))
        preset = next((p for p in catalog_svc.list_device_type_presets() if p.key == key), None)
        if preset is None:
            self._desc.setText("")
            return
        ports = sum(int(g.get("count", 0)) for g in preset.port_groups)
        groups = "\n".join(
            f"• {g.get('prefix')} ×{g.get('count')} @ {g.get('speed')} Мбит/с ({g.get('media')})"
            for g in preset.port_groups
        )
        self._desc.setText(
            f"{preset.vendor} {preset.model}\n"
            f"Роль: {role_label(preset.role)}\n"
            f"Портов: {ports}\n\n"
            f"{preset.description}\n\n"
            f"{groups}"
        )

    def selected_key(self) -> str | None:
        item = self._list.currentItem()
        if item is None:
            return None
        return str(item.data(Qt.ItemDataRole.UserRole))
