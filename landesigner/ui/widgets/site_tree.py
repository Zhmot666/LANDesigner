from __future__ import annotations

from enum import Enum
from uuid import UUID

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPalette
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from landesigner.domain.entities import ProjectSnapshot


class TreeKind(str, Enum):
    SITE = "site"
    BUILDING = "building"
    FLOOR = "floor"
    ROOM = "room"
    RACK = "rack"


class SiteTreeView(QWidget):
    selection_changed = Signal(object, object)  # kind, id
    add_requested = Signal(object)  # TreeKind to add
    edit_requested = Signal(object, object)  # kind, id
    delete_requested = Signal(object, object)  # kind, id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SiteSidebar")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 8, 10)
        layout.setSpacing(6)

        brand = QLabel("LANDESIGNER", self)
        brand.setObjectName("SidebarTitle")
        layout.addWidget(brand)
        title = QLabel("Площадка", self)
        title.setObjectName("SidebarBrand")
        layout.addWidget(title)

        self._tree = QTreeWidget(self)
        self._tree.setHeaderHidden(True)
        self._tree.setAnimated(True)
        self._tree.setIndentation(18)
        self._tree.setUniformRowHeights(True)
        # Явная палитра: глобальный QSS на Windows часто игнорирует цвет item.
        pal = self._tree.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#0f172a"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#0f172a"))
        pal.setColor(QPalette.ColorRole.Highlight, QColor("#14b8a6"))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#042f2e"))
        self._tree.setPalette(pal)
        self._fg = QBrush(QColor("#0f172a"))
        self._tree.itemSelectionChanged.connect(self._emit_selection)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._tree, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        self._btn_building = QPushButton("Здание", self)
        self._btn_floor = QPushButton("Этаж", self)
        self._btn_room = QPushButton("Комната", self)
        self._btn_rack = QPushButton("Шкаф", self)
        for btn, kind in (
            (self._btn_building, TreeKind.BUILDING),
            (self._btn_floor, TreeKind.FLOOR),
            (self._btn_room, TreeKind.ROOM),
            (self._btn_rack, TreeKind.RACK),
        ):
            btn.clicked.connect(lambda _=False, k=kind: self.add_requested.emit(k))
            btn_row.addWidget(btn)
        layout.addLayout(btn_row)

        edit_row = QHBoxLayout()
        edit_row.setSpacing(4)
        self._btn_edit = QPushButton("Изменить…", self)
        self._btn_delete = QPushButton("Удалить", self)
        self._btn_delete.setObjectName("DangerButton")
        self._btn_edit.clicked.connect(self._emit_edit)
        self._btn_delete.clicked.connect(self._emit_delete)
        edit_row.addWidget(self._btn_edit)
        edit_row.addWidget(self._btn_delete)
        layout.addLayout(edit_row)

    def set_snapshot(self, snapshot: ProjectSnapshot | None) -> None:
        current = self.current()
        self._tree.clear()
        if snapshot is None or not snapshot.sites:
            return

        site = snapshot.sites[0]
        site_item = QTreeWidgetItem([site.name])
        site_item.setForeground(0, self._fg)
        site_item.setData(0, Qt.ItemDataRole.UserRole, (TreeKind.SITE, site.id))
        self._tree.addTopLevelItem(site_item)

        for building in [b for b in snapshot.buildings if b.site_id == site.id]:
            b_item = QTreeWidgetItem([building.name])
            b_item.setForeground(0, self._fg)
            b_item.setData(0, Qt.ItemDataRole.UserRole, (TreeKind.BUILDING, building.id))
            site_item.addChild(b_item)

            for floor in [f for f in snapshot.floors if f.building_id == building.id]:
                f_item = QTreeWidgetItem([f"{floor.name} (ур. {floor.level:g})"])
                f_item.setForeground(0, self._fg)
                f_item.setData(0, Qt.ItemDataRole.UserRole, (TreeKind.FLOOR, floor.id))
                b_item.addChild(f_item)

                for room in [r for r in snapshot.rooms if r.floor_id == floor.id]:
                    r_item = QTreeWidgetItem([room.name])
                    r_item.setForeground(0, self._fg)
                    r_item.setData(0, Qt.ItemDataRole.UserRole, (TreeKind.ROOM, room.id))
                    f_item.addChild(r_item)

                    for rack in [rk for rk in snapshot.racks if rk.room_id == room.id]:
                        rk_item = QTreeWidgetItem([f"{rack.name} ({rack.units} юн.)"])
                        rk_item.setForeground(0, self._fg)
                        rk_item.setData(0, Qt.ItemDataRole.UserRole, (TreeKind.RACK, rack.id))
                        r_item.addChild(rk_item)

        self._tree.expandAll()
        self._restore_selection(current)

    def _restore_selection(self, current: tuple[TreeKind | None, UUID | None]) -> None:
        kind, obj_id = current
        if kind is None or obj_id is None:
            return

        def walk(item: QTreeWidgetItem) -> bool:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == kind and data[1] == obj_id:
                self._tree.setCurrentItem(item)
                return True
            for i in range(item.childCount()):
                if walk(item.child(i)):
                    return True
            return False

        for i in range(self._tree.topLevelItemCount()):
            if walk(self._tree.topLevelItem(i)):
                return

    def current(self) -> tuple[TreeKind | None, UUID | None]:
        items = self._tree.selectedItems()
        if not items:
            return None, None
        data = items[0].data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return None, None
        kind, obj_id = data
        return kind, obj_id

    def _emit_selection(self) -> None:
        kind, obj_id = self.current()
        self.selection_changed.emit(kind, obj_id)

    def _emit_edit(self) -> None:
        kind, obj_id = self.current()
        if kind is not None and obj_id is not None:
            self.edit_requested.emit(kind, obj_id)

    def _emit_delete(self) -> None:
        kind, obj_id = self.current()
        if kind is not None and obj_id is not None:
            self.delete_requested.emit(kind, obj_id)

    def _on_double_click(self, item: QTreeWidgetItem, _column: int) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data:
            self.edit_requested.emit(data[0], data[1])

    def _on_context_menu(self, pos) -> None:
        item = self._tree.itemAt(pos)
        if item is not None:
            self._tree.setCurrentItem(item)
        kind, obj_id = self.current()
        menu = QMenu(self)
        if kind in (TreeKind.SITE, None):
            menu.addAction("Добавить здание", lambda: self.add_requested.emit(TreeKind.BUILDING))
        if kind == TreeKind.BUILDING:
            menu.addAction("Добавить этаж", lambda: self.add_requested.emit(TreeKind.FLOOR))
        if kind == TreeKind.FLOOR:
            menu.addAction("Добавить комнату", lambda: self.add_requested.emit(TreeKind.ROOM))
        if kind == TreeKind.ROOM:
            menu.addAction("Добавить шкаф", lambda: self.add_requested.emit(TreeKind.RACK))

        if kind is not None and obj_id is not None:
            if menu.actions():
                menu.addSeparator()
            if kind != TreeKind.SITE:
                menu.addAction("Изменить…", lambda: self.edit_requested.emit(kind, obj_id))
                menu.addAction("Удалить", lambda: self.delete_requested.emit(kind, obj_id))
            else:
                menu.addAction("Переименовать…", lambda: self.edit_requested.emit(kind, obj_id))

        if not menu.actions():
            return
        menu.exec(self._tree.viewport().mapToGlobal(pos))
