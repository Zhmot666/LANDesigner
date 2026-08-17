from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from landesigner.domain.entities import DeviceType, ProjectSnapshot
from landesigner.services import search as search_service
from landesigner.ui.labels import role_label
from landesigner.ui.table_utils import make_item, select_row_by_id, table_update, tune_table
from landesigner.ui.widgets.panel_card import PanelCard


def _primary_btn(text: str, parent: QWidget) -> QPushButton:
    btn = QPushButton(text, parent)
    btn.setObjectName("PrimaryButton")
    btn.setProperty("role", "primary")
    return btn


class DeviceTypesView(QWidget):
    """Справочник типов оборудования проекта + пресеты."""

    add_requested = Signal()
    add_from_catalog_requested = Signal()
    edit_requested = Signal(object)  # UUID
    delete_requested = Signal(object)  # UUID
    export_preset_requested = Signal()
    import_preset_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self._search = QLineEdit(self)
        self._search.setPlaceholderText("Поиск по типам…  (Ctrl+K)")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._on_search_changed)
        self._search_hint = QLabel("", self)
        self._search_hint.setProperty("muted", True)
        self._search_hint.setObjectName("PanelSubtitle")
        search_row.addWidget(self._search, stretch=1)
        search_row.addWidget(self._search_hint)
        layout.addLayout(search_row)

        QShortcut(QKeySequence("Ctrl+K"), self, activated=self.focus_search)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self._search, activated=self._clear_search)

        card = PanelCard("Типы устройств", self)
        self._btn_add = _primary_btn("+ Добавить", card)
        self._btn_catalog = QPushButton("Каталог…", card)
        self._btn_edit = QPushButton("Изменить", card)
        self._btn_delete = QPushButton("Удалить", card)
        self._btn_delete.setObjectName("DangerButton")
        self._btn_delete.setProperty("role", "danger")
        self._btn_export = QPushButton("Экспорт пресета…", card)
        self._btn_import = QPushButton("Импорт пресета…", card)

        self._btn_add.clicked.connect(self.add_requested.emit)
        self._btn_catalog.clicked.connect(self.add_from_catalog_requested.emit)
        self._btn_edit.clicked.connect(self._on_edit)
        self._btn_delete.clicked.connect(self._on_delete)
        self._btn_export.clicked.connect(self.export_preset_requested.emit)
        self._btn_import.clicked.connect(self.import_preset_requested.emit)

        for btn in (
            self._btn_add,
            self._btn_catalog,
            self._btn_edit,
            self._btn_delete,
            self._btn_export,
            self._btn_import,
        ):
            card.add_action(btn)

        self._table = QTableWidget(card)
        tune_table(self._table)
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            ["Производитель", "Модель", "Роль", "Портов", "Скорости"]
        )
        self._table.itemDoubleClicked.connect(self._on_edit)
        card.set_body_widget(self._table)
        layout.addWidget(card, stretch=1)

        self._snapshot: ProjectSnapshot | None = None
        self._types: list[DeviceType] = []
        self._query = ""

    def focus_search(self) -> None:
        self._search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._search.selectAll()

    def _clear_search(self) -> None:
        if self._search.text():
            self._search.clear()
        else:
            self._search.clearFocus()

    def _on_search_changed(self, text: str) -> None:
        self._query = text
        self._refresh_table(preserve_selection=True)

    def set_snapshot(self, snapshot: ProjectSnapshot | None) -> None:
        self._snapshot = snapshot
        self._types = list(snapshot.device_types) if snapshot else []
        self._refresh_table(preserve_selection=True)

    def selected_type_id(self) -> UUID | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self._table.item(rows[0].row(), 0)
        if item is None:
            return None
        raw = item.data(Qt.ItemDataRole.UserRole)
        return UUID(raw) if raw else None

    def _refresh_table(self, *, preserve_selection: bool) -> None:
        selected = self.selected_type_id() if preserve_selection else None
        if self._snapshot is None:
            with table_update(self._table):
                self._table.setRowCount(0)
            self._search_hint.setText("")
            return

        types = search_service.filter_device_types(self._types, self._query)
        with table_update(self._table):
            self._table.setRowCount(len(types))
            for row_idx, dt in enumerate(types):
                speeds = sorted({int(p.get("speed", 0)) for p in dt.port_template})
                speed_txt = "/".join(str(s) for s in speeds if s) or "—"
                max_speed = max(speeds) if speeds else 0
                self._table.setItem(
                    row_idx, 0, make_item(dt.vendor, entity_id=dt.id)
                )
                self._table.setItem(row_idx, 1, make_item(dt.model))
                self._table.setItem(row_idx, 2, make_item(role_label(dt.role)))
                self._table.setItem(
                    row_idx,
                    3,
                    make_item(str(len(dt.port_template)), sort_key=len(dt.port_template)),
                )
                self._table.setItem(
                    row_idx, 4, make_item(f"{speed_txt} Мбит/с", sort_key=max_speed)
                )

        total = len(self._types)
        shown = len(types)
        if search_service.normalize_query(self._query):
            self._search_hint.setText(f"{shown} из {total}")
        else:
            self._search_hint.setText(f"{total}" if total else "")

        if not select_row_by_id(self._table, selected):
            if shown and search_service.normalize_query(self._query):
                self._table.selectRow(0)

    def _on_edit(self) -> None:
        type_id = self.selected_type_id()
        if type_id is not None:
            self.edit_requested.emit(type_id)

    def _on_delete(self) -> None:
        type_id = self.selected_type_id()
        if type_id is not None:
            self.delete_requested.emit(type_id)
