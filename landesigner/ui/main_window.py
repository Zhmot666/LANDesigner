from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from landesigner.adapters.local_sqlite.repository import LocalSqliteRepository
from landesigner.adapters.remote import RemoteHttpClient
from landesigner.domain.entities import ProjectMeta, ProjectSnapshot, Site, utcnow
from landesigner.ports.remote import RemoteConflictError
from landesigner.services import catalog as catalog_svc
from landesigner.services import device_type_preset as type_preset_svc
from landesigner.services import import_export as csv_io
from landesigner.services import inventory as inventory_service
from landesigner.services import snapshots as snap_svc
from landesigner.services import sync as sync_svc
from landesigner.services.project import ProjectService
from landesigner.ui.dialogs.catalog_dialog import DeviceTypeCatalogDialog
from landesigner.ui.dialogs.inventory_dialogs import (
    BuildingDialog,
    CableDialog,
    DeviceDialog,
    DeviceTypeDialog,
    FloorDialog,
    IpDialog,
    LagDialog,
    NameDialog,
    PortNetworkDialog,
    PortPropertiesDialog,
    ProjectDialog,
    RackDialog,
    VlanDialog,
)
from landesigner.ui.dialogs.snapshot_dialog import SnapshotRestoreDialog
from landesigner.ui.dialogs.sync_dialogs import (
    RemoteProjectsDialog,
    SyncConflictDialog,
    SyncSettingsDialog,
    load_sync_settings,
    save_sync_settings,
)
from landesigner.ui.views.device_types_view import DeviceTypesView
from landesigner.ui.views.floor_plan_view import FloorPlanView
from landesigner.ui.views.inventory_view import InventoryView
from landesigner.ui.views.reports_view import ReportsView
from landesigner.ui.views.topology_view import TopologyView
from landesigner.ui.widgets.device_card import ContextCard
from landesigner.ui.widgets.site_tree import SiteTreeView, TreeKind


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LanDesigner")

        self._active_file: str | None = None
        self._active_snapshot: ProjectSnapshot | None = None
        self._dirty = False

        self._service = ProjectService(LocalSqliteRepository())
        self._site_tree = SiteTreeView()
        self._device_types_view = DeviceTypesView()
        self._inventory_view = InventoryView()
        self._topology_view = TopologyView()
        self._floor_plan_view = FloorPlanView()
        self._reports_view = ReportsView()
        self._device_card = ContextCard()
        self._syncing_selection = False

        self._init_ui()
        self._wire_signals()

    def _init_ui(self) -> None:
        self.setMinimumSize(1200, 750)

        status = QStatusBar(self)
        self.setStatusBar(status)
        self._update_sync_status()

        menu = self.menuBar()
        file_menu = menu.addMenu("Файл")
        action_new = QAction("Новый…", self)
        action_open = QAction("Открыть…", self)
        action_save = QAction("Сохранить", self)
        action_export_csv = QAction("Экспорт CSV…", self)
        action_import_csv = QAction("Импорт CSV…", self)
        action_exit = QAction("Выход", self)
        file_menu.addAction(action_new)
        file_menu.addAction(action_open)
        file_menu.addAction(action_save)
        file_menu.addSeparator()
        file_menu.addAction(action_export_csv)
        file_menu.addAction(action_import_csv)
        file_menu.addSeparator()
        action_snapshot = QAction("Создать снимок…", self)
        action_restore = QAction("Восстановить снимок…", self)
        file_menu.addAction(action_snapshot)
        file_menu.addAction(action_restore)
        file_menu.addSeparator()
        action_project_props = QAction("Свойства проекта…", self)
        file_menu.addAction(action_project_props)
        action_project_props.triggered.connect(self._on_edit_project)
        file_menu.addSeparator()
        file_menu.addAction(action_exit)
        action_exit.triggered.connect(self.close)
        action_new.triggered.connect(self._on_new)
        action_open.triggered.connect(self._on_open)
        action_save.triggered.connect(self._on_save)
        action_export_csv.triggered.connect(self._on_export_csv)
        action_import_csv.triggered.connect(self._on_import_csv)
        action_snapshot.triggered.connect(self._on_create_snapshot)
        action_restore.triggered.connect(self._on_restore_snapshot)

        edit_menu = menu.addMenu("Правка")
        self._action_undo = QAction("Отменить", self)
        self._action_redo = QAction("Повторить", self)
        self._action_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self._action_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self._action_undo.setEnabled(False)
        self._action_redo.setEnabled(False)
        edit_menu.addAction(self._action_undo)
        edit_menu.addAction(self._action_redo)
        self._action_undo.triggered.connect(self._on_undo)
        self._action_redo.triggered.connect(self._on_redo)

        sync_menu = menu.addMenu("Синхронизация")
        action_sync_settings = QAction("Настройки сервера…", self)
        action_clone = QAction("Клонировать с сервера…", self)
        action_publish = QAction("Опубликовать на сервер…", self)
        action_push = QAction("Push", self)
        action_pull = QAction("Pull", self)
        sync_menu.addAction(action_sync_settings)
        sync_menu.addSeparator()
        sync_menu.addAction(action_clone)
        sync_menu.addAction(action_publish)
        sync_menu.addAction(action_push)
        sync_menu.addAction(action_pull)
        action_sync_settings.triggered.connect(self._on_sync_settings)
        action_clone.triggered.connect(self._on_sync_clone)
        action_publish.triggered.connect(self._on_sync_publish)
        action_push.triggered.connect(self._on_sync_push)
        action_pull.triggered.connect(lambda: self._on_sync_pull())

        tools_menu = menu.addMenu("Инструменты")
        action_catalog = QAction("Тип из каталога…", self)
        tools_menu.addAction(action_catalog)
        action_catalog.triggered.connect(self._on_add_device_type_from_catalog)

        central = QWidget(self)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 12, 10)
        layout.setSpacing(0)

        splitter = QSplitter(central)
        splitter.setHandleWidth(1)
        splitter.addWidget(self._site_tree)

        right = QWidget(splitter)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(10, 10, 4, 0)
        right_layout.setSpacing(8)

        content = QSplitter(Qt.Orientation.Horizontal, right)
        content.setHandleWidth(1)
        content.setChildrenCollapsible(False)
        self._content_splitter = content

        tabs = QTabWidget(content)
        tabs.setObjectName("MainTabs")
        tabs.setDocumentMode(True)
        tabs.addTab(self._topology_view, "Схема")
        tabs.addTab(self._floor_plan_view, "План")
        tabs.addTab(self._device_types_view, "Каталог")
        tabs.addTab(self._inventory_view, "Инвентарь")
        tabs.addTab(self._reports_view, "Отчёты")
        self._tabs = tabs
        tabs.setCurrentIndex(3)
        tabs.currentChanged.connect(self._update_edit_actions)
        tabs.currentChanged.connect(self._dock_device_card)
        content.addWidget(tabs)

        self._side_card_host = QWidget(content)
        self._side_card_layout = QVBoxLayout(self._side_card_host)
        self._side_card_layout.setContentsMargins(0, 0, 0, 0)
        self._side_card_layout.setSpacing(0)
        content.addWidget(self._side_card_host)
        content.setSizes([1000, 0])
        content.setStretchFactor(0, 1)
        content.setStretchFactor(1, 0)
        right_layout.addWidget(content)
        splitter.addWidget(right)
        splitter.setSizes([280, 1000])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)
        self.setCentralWidget(central)

        QShortcut(QKeySequence("Ctrl+K"), self, activated=self._focus_search)
        self._dock_device_card()

    def _dock_device_card(self, *_args) -> None:
        """На инвентаре — карточка внизу справа; на схеме/плане — справа от вкладки."""
        card = self._device_card
        current = self._tabs.currentWidget()
        if current is self._inventory_view:
            if card.parent() is self._side_card_host:
                self._side_card_layout.removeWidget(card)
            self._inventory_view.attach_device_card(card)
            self._side_card_host.hide()
            self._content_splitter.setSizes([1000, 0])
            card.show()
            return

        self._inventory_view.detach_device_card()
        if current in (self._topology_view, self._floor_plan_view):
            if card.parent() is not self._side_card_host:
                self._side_card_layout.addWidget(card)
            self._side_card_host.show()
            self._content_splitter.setSizes([780, 320])
            card.show()
            return

        if card.parent() is self._side_card_host:
            self._side_card_layout.removeWidget(card)
            card.setParent(None)
        self._side_card_host.hide()
        self._content_splitter.setSizes([1000, 0])
        card.hide()

    def _focus_search(self) -> None:
        if self._tabs.currentWidget() is self._device_types_view:
            self._device_types_view.focus_search()
            return
        self._tabs.setCurrentWidget(self._inventory_view)
        self._inventory_view.focus_search()

    def _wire_signals(self) -> None:
        self._site_tree.add_requested.connect(self._on_tree_add)
        self._site_tree.edit_requested.connect(self._on_tree_edit)
        self._site_tree.delete_requested.connect(self._on_tree_delete)
        self._device_types_view.add_requested.connect(self._on_add_device_type)
        self._device_types_view.add_from_catalog_requested.connect(
            self._on_add_device_type_from_catalog
        )
        self._device_types_view.edit_requested.connect(self._on_edit_device_type)
        self._device_types_view.delete_requested.connect(self._on_delete_device_type)
        self._device_types_view.export_preset_requested.connect(self._on_export_type_preset)
        self._device_types_view.import_preset_requested.connect(self._on_import_type_preset)
        self._inventory_view.add_device_requested.connect(self._on_add_device)
        self._inventory_view.edit_device_requested.connect(self._on_edit_device)
        self._inventory_view.delete_device_requested.connect(self._on_delete_device)
        self._inventory_view.add_cable_requested.connect(self._on_add_cable)
        self._inventory_view.edit_cable_requested.connect(self._on_edit_cable)
        self._inventory_view.delete_cable_requested.connect(self._on_delete_cable)
        self._inventory_view.add_vlan_requested.connect(self._on_add_vlan)
        self._inventory_view.edit_vlan_requested.connect(self._on_edit_vlan)
        self._inventory_view.delete_vlan_requested.connect(self._on_delete_vlan)
        self._inventory_view.add_ip_requested.connect(self._on_add_ip)
        self._inventory_view.edit_ip_requested.connect(self._on_edit_ip)
        self._inventory_view.delete_ip_requested.connect(self._on_delete_ip)
        self._inventory_view.add_lag_requested.connect(self._on_add_lag)
        self._inventory_view.edit_lag_requested.connect(self._on_edit_lag)
        self._inventory_view.delete_lag_requested.connect(self._on_delete_lag)
        self._inventory_view.edit_port_network_requested.connect(self._on_edit_port_network)
        self._inventory_view.edit_port_properties_requested.connect(
            self._on_edit_port_properties
        )
        self._inventory_view.add_port_requested.connect(self._on_add_port)
        self._inventory_view.delete_port_requested.connect(self._on_delete_port)
        self._topology_view.topology_changed.connect(self._on_topology_changed)
        self._topology_view.device_selected.connect(self._on_topology_device_selected)
        self._topology_view.connect_devices_requested.connect(self._on_topology_connect_devices)
        self._topology_view.edit_device_requested.connect(self._on_edit_device)
        self._inventory_view.device_selection_changed.connect(self._on_inventory_device_selected)
        self._floor_plan_view.plan_changed.connect(self._on_floor_plan_changed)
        self._floor_plan_view.device_selected.connect(self._on_floor_plan_device_selected)
        self._floor_plan_view.measure_finished.connect(self._on_measure_finished)
        self._site_tree.selection_changed.connect(self._on_tree_selection_changed)
        self._device_card.edit_project_requested.connect(self._on_edit_project)
        self._device_card.edit_building_requested.connect(self._on_edit_building_from_card)
        self._device_card.edit_device_requested.connect(self._on_edit_device)
        self._device_card.show_on_topology_requested.connect(self._on_show_on_topology)
        self._device_card.show_on_floor_plan_requested.connect(self._on_show_on_floor_plan)
        self._update_edit_actions()

    def _show_device_card(self, device_id: object) -> None:
        if isinstance(device_id, UUID):
            self._device_card.show_device(device_id)
        else:
            self._device_card.show_project()

    def _on_edit_project(self) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        site = snapshot.sites[0] if snapshot.sites else None
        dlg = ProjectDialog(
            project_name=snapshot.meta.name,
            site_name=site.name if site else "",
            address=site.address if site else "",
            notes=site.notes if site else "",
            parent=self,
        )
        if dlg.exec() != ProjectDialog.DialogCode.Accepted:
            return
        project_name, site_name, address, notes = dlg.values()
        snapshot.meta.name = project_name
        if site is not None:
            site.name = site_name
            site.address = address
            site.notes = notes
        self._mark_dirty()
        self._device_card.show_project()
        self.statusBar().showMessage(f"Проект: {project_name}")

    def _on_edit_building_from_card(self, building_id: UUID) -> None:
        self._on_tree_edit(TreeKind.BUILDING, building_id)

    def _on_show_on_topology(self, device_id: UUID) -> None:
        self._tabs.setCurrentIndex(0)
        self._topology_view.select_device(device_id)
        self._device_card.show_device(device_id)

    def _on_show_on_floor_plan(self, device_id: UUID) -> None:
        self._tabs.setCurrentIndex(1)
        self._floor_plan_view.select_device(device_id)
        self._device_card.show_device(device_id)
        # Если устройство на этаже — переключить комбо этажа
        snapshot = self._active_snapshot
        if snapshot is None:
            return
        device = next((d for d in snapshot.devices if d.id == device_id), None)
        if device is None or device.room_id is None:
            return
        room = next((r for r in snapshot.rooms if r.id == device.room_id), None)
        if room is not None:
            self._floor_plan_view.select_floor(room.floor_id)
            self._floor_plan_view.select_device(device_id)
    def _update_edit_actions(self) -> None:
        view = self._active_undo_view()
        self._action_undo.setEnabled(bool(view and view.can_undo()))
        self._action_redo.setEnabled(bool(view and view.can_redo()))

    def _active_undo_view(self):
        idx = self._tabs.currentIndex()
        if idx == 0:
            return self._topology_view
        if idx == 1:
            return self._floor_plan_view
        return None

    def _on_undo(self) -> None:
        view = self._active_undo_view()
        if view is not None:
            view.undo()
            self._update_edit_actions()

    def _on_redo(self) -> None:
        view = self._active_undo_view()
        if view is not None:
            view.redo()
            self._update_edit_actions()

    def _on_create_snapshot(self) -> None:
        if not self._active_file:
            QMessageBox.information(
                self,
                "Снимок",
                "Сначала сохраните проект в файл .lanproj.",
            )
            return
        if self._dirty:
            answer = QMessageBox.question(
                self,
                "Снимок",
                "Есть несохранённые изменения. Сохранить перед снимком?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                return
            if answer == QMessageBox.StandardButton.Yes:
                self._on_save()
                if self._dirty:
                    return
        dlg = NameDialog("Создать снимок", label="Метка (необязательно)", parent=self)
        if dlg.exec() != NameDialog.DialogCode.Accepted:
            return
        try:
            path = snap_svc.create_snapshot(self._active_file, label=dlg.value())
        except Exception as e:
            QMessageBox.critical(self, "Снимок", str(e))
            return
        self.statusBar().showMessage(f"Снимок создан: {path.parent.name}")

    def _on_restore_snapshot(self) -> None:
        if not self._active_file:
            QMessageBox.information(self, "Снимок", "Сначала сохраните/откройте .lanproj.")
            return
        items = snap_svc.list_snapshots(self._active_file)
        if not items:
            QMessageBox.information(self, "Снимок", "Снимков пока нет.")
            return
        dlg = SnapshotRestoreDialog(self._active_file, parent=self)
        if dlg.exec() != SnapshotRestoreDialog.DialogCode.Accepted:
            return
        path = dlg.selected_path()
        if not path:
            return
        answer = QMessageBox.question(
            self,
            "Восстановить снимок",
            "Текущий файл проекта будет заменён снимком.\nПродолжить?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            snap_svc.restore_snapshot(self._active_file, path)
            self._active_snapshot = self._service.open_project(self._active_file)
            self._dirty = False
            self._refresh_ui()
        except Exception as e:
            QMessageBox.critical(self, "Снимок", str(e))
            return
        self.statusBar().showMessage("Снимок восстановлен")

    def _on_topology_changed(self) -> None:
        # Не пересобираем схему целиком — иначе сбрасывается QUndoStack.
        self._dirty = True
        self._inventory_view.set_snapshot(self._active_snapshot)
        self._site_tree.set_snapshot(self._active_snapshot)
        title = "LanDesigner"
        if self._active_snapshot is not None:
            title += f" — {self._active_snapshot.meta.name} *"
        self.setWindowTitle(title)
        self.statusBar().showMessage("Есть несохранённые изменения")
        self._update_edit_actions()
        self._device_card.set_snapshot(self._active_snapshot)

    def _on_floor_plan_changed(self) -> None:
        self._dirty = True
        self._inventory_view.set_snapshot(self._active_snapshot)
        self._site_tree.set_snapshot(self._active_snapshot)
        title = "LanDesigner"
        if self._active_snapshot is not None:
            title += f" — {self._active_snapshot.meta.name} *"
        self.setWindowTitle(title)
        self.statusBar().showMessage("Есть несохранённые изменения")
        self._update_edit_actions()
        self._device_card.set_snapshot(self._active_snapshot)

    def _on_measure_finished(self, length_m: float) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None or not snapshot.cables:
            self.statusBar().showMessage(f"Измерено: {length_m:.2f} м")
            return
        answer = QMessageBox.question(
            self,
            "Длина трассы",
            f"Измерено {length_m:.2f} м.\nЗаписать длину в выбранный кабель инвентаря?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.statusBar().showMessage(f"Измерено: {length_m:.2f} м")
            return
        cable_id = self._inventory_view.selected_cable_id()
        if cable_id is None:
            QMessageBox.information(
                self,
                "Длина трассы",
                "Выберите кабель на вкладке «Инвентарь», затем повторите измерение.",
            )
            self.statusBar().showMessage(f"Измерено: {length_m:.2f} м (кабель не выбран)")
            return
        try:
            inventory_service.update_cable(
                snapshot,
                cable_id,
                length_m=length_m,
            )
        except Exception as e:
            QMessageBox.critical(self, "Кабель", str(e))
            return
        self._mark_dirty()
        self.statusBar().showMessage(f"Длина кабеля обновлена: {length_m:.2f} м")

    def _on_tree_selection_changed(self, kind: object, obj_id: object) -> None:
        if kind == TreeKind.FLOOR and isinstance(obj_id, UUID):
            self._floor_plan_view.select_floor(obj_id)
        if not isinstance(obj_id, UUID):
            self._device_card.show_project()
            self._inventory_view.set_location_filter(None, None)
            return
        snapshot = self._active_snapshot
        if snapshot is None:
            return
        elif kind == TreeKind.RACK:
            self._device_card.show_rack(obj_id)
            self._inventory_view.set_location_filter("rack", obj_id)
        elif kind == TreeKind.ROOM:
            room = next((r for r in snapshot.rooms if r.id == obj_id), None)
            if room is None:
                return
            floor = next((f for f in snapshot.floors if f.id == room.floor_id), None)
            if floor is not None:
                self._device_card.show_building(floor.building_id)
            self._inventory_view.set_location_filter("room", obj_id)
        elif kind == TreeKind.FLOOR:
            floor = next((f for f in snapshot.floors if f.id == obj_id), None)
            if floor is not None:
                self._device_card.show_building(floor.building_id)
            self._inventory_view.set_location_filter("floor", obj_id)
        elif kind == TreeKind.BUILDING:
            self._device_card.show_building(obj_id)
            self._inventory_view.set_location_filter("building", obj_id)
        elif kind == TreeKind.SITE:
            self._device_card.show_project()
            self._inventory_view.set_location_filter(None, None)

    def _on_topology_connect_devices(self, device_a: object, device_b: object) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        if not isinstance(device_a, UUID) or not isinstance(device_b, UUID):
            return
        dlg = CableDialog(
            snapshot,
            parent=self,
            device_a_id=device_a,
            device_b_id=device_b,
        )
        if dlg.exec() != CableDialog.DialogCode.Accepted:
            return
        if not dlg.is_valid():
            QMessageBox.warning(self, "Кабель", "Выберите оба порта.")
            return
        try:
            end_a, end_b, label, kind, category, length_m = dlg.values()
            self._topology_view.apply_add_cable(
                end_a,
                end_b,
                label=label,
                kind=kind,
                category=category,
                length_m=length_m,
            )
        except Exception as e:
            QMessageBox.critical(self, "Кабель", str(e))
            return
        self.statusBar().showMessage("Связь создана на схеме")

    def _on_topology_device_selected(self, device_id: object) -> None:
        if self._syncing_selection:
            return
        self._syncing_selection = True
        try:
            if isinstance(device_id, UUID):
                self._inventory_view.select_device(device_id)
                self._floor_plan_view.select_device(device_id)
            self._show_device_card(device_id)
        finally:
            self._syncing_selection = False

    def _on_floor_plan_device_selected(self, device_id: object) -> None:
        if self._syncing_selection:
            return
        self._syncing_selection = True
        try:
            if isinstance(device_id, UUID):
                self._inventory_view.select_device(device_id)
                self._topology_view.select_device(device_id)
            self._show_device_card(device_id)
        finally:
            self._syncing_selection = False

    def _on_inventory_device_selected(self, device_id: object) -> None:
        if self._syncing_selection:
            return
        self._syncing_selection = True
        try:
            if isinstance(device_id, UUID):
                self._topology_view.select_device(device_id)
                self._floor_plan_view.select_device(device_id)
            else:
                self._topology_view.select_device(None)
                self._floor_plan_view.select_device(None)
            self._show_device_card(device_id)
        finally:
            self._syncing_selection = False

    def _refresh_ui(self) -> None:
        self._site_tree.set_snapshot(self._active_snapshot)
        self._device_types_view.set_snapshot(self._active_snapshot)
        self._inventory_view.set_snapshot(self._active_snapshot)
        self._topology_view.set_snapshot(self._active_snapshot)
        self._floor_plan_view.set_project_file(self._active_file)
        self._floor_plan_view.set_snapshot(self._active_snapshot)
        self._reports_view.set_snapshot(self._active_snapshot)
        self._device_card.set_project_file(self._active_file)
        self._device_card.set_snapshot(self._active_snapshot)
        title = "LanDesigner"
        if self._active_snapshot is not None:
            title += f" — {self._active_snapshot.meta.name}"
            if self._dirty:
                title += " *"
        self.setWindowTitle(title)

    def _mark_dirty(self, *, refresh: bool = True) -> None:
        self._dirty = True
        if refresh:
            self._refresh_ui()
        else:
            title = "LanDesigner"
            if self._active_snapshot is not None:
                title += f" — {self._active_snapshot.meta.name} *"
            self.setWindowTitle(title)
        self._update_sync_status()

    def _update_sync_status(self) -> None:
        self.statusBar().showMessage(
            sync_svc.status_label(
                file_path=self._active_file,
                snapshot=self._active_snapshot,
                dirty=self._dirty,
            )
        )

    def _remote_client(self) -> RemoteHttpClient:
        url, token = load_sync_settings()
        return RemoteHttpClient(url, api_token=token)

    def _require_snapshot(self) -> ProjectSnapshot | None:
        if self._active_snapshot is None:
            QMessageBox.warning(self, "Проект", "Сначала создайте или откройте проект.")
            return None
        return self._active_snapshot

    def _offer_save_before_leave(self) -> bool:
        """
        Если есть несохранённые изменения — спросить пользователя.
        True = можно продолжать (сохранили / отбросили), False = отмена действия.
        """
        if not self._dirty or self._active_snapshot is None:
            return True

        answer = QMessageBox.question(
            self,
            "Несохранённые изменения",
            "В проекте есть несохранённые изменения.\nСохранить перед продолжением?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Discard:
            return True
        self._on_save()
        # Если пользователь отменил диалог сохранения файла — проект всё ещё dirty.
        return not self._dirty

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt API
        if self._offer_save_before_leave():
            event.accept()
        else:
            event.ignore()

    def _on_new(self) -> None:
        if not self._offer_save_before_leave():
            return
        self._active_file = None
        meta = ProjectMeta(name="Новый проект")
        site = Site(project_id=meta.id, name="Площадка")
        self._active_snapshot = ProjectSnapshot(meta=meta, sites=[site])
        self._dirty = True
        self._refresh_ui()
        self._update_sync_status()

    def _on_open(self) -> None:
        if not self._offer_save_before_leave():
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Открыть проект",
            "",
            "Проект LanDesigner (*.lanproj);;Все файлы (*.*)",
        )
        if not file_path:
            return

        try:
            self._active_snapshot = self._service.open_project(file_path)
            self._active_file = file_path
            self._dirty = False
            self._refresh_ui()
            self._update_sync_status()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка открытия", str(e))

    def _on_save(self) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return

        file_path = self._active_file
        if file_path is None:
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Сохранить проект",
                "",
                "Проект LanDesigner (*.lanproj);;Все файлы (*.*)",
            )
            if not file_path:
                return
            if not file_path.lower().endswith(".lanproj"):
                file_path += ".lanproj"

        snapshot.meta.updated_at = utcnow()
        snapshot.meta.revision += 1

        try:
            self._service.save_project(file_path=file_path, snapshot=snapshot)
            self._active_file = file_path
            self._dirty = False
            self._refresh_ui()
            self._update_sync_status()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка сохранения", str(e))

    def _on_sync_settings(self) -> None:
        dialog = SyncSettingsDialog(self)
        if dialog.exec() != SyncSettingsDialog.DialogCode.Accepted:
            return
        url, token = dialog.values()
        if not url:
            QMessageBox.warning(self, "Синхронизация", "Укажите URL сервера.")
            return
        save_sync_settings(url, token)
        self._update_sync_status()

    def _on_sync_clone(self) -> None:
        if not self._offer_save_before_leave():
            return
        try:
            client = self._remote_client()
            projects = sync_svc.list_remote_projects(client)
        except Exception as e:
            QMessageBox.critical(self, "Синхронизация", str(e))
            return
        if not projects:
            QMessageBox.information(self, "Синхронизация", "На сервере нет проектов.")
            return
        picker = RemoteProjectsDialog(projects, self)
        if picker.exec() != RemoteProjectsDialog.DialogCode.Accepted:
            return
        project_id = picker.selected_project_id()
        if project_id is None:
            return
        dest, _ = QFileDialog.getSaveFileName(
            self,
            "Куда сохранить клон",
            "",
            "Проект LanDesigner (*.lanproj);;Все файлы (*.*)",
        )
        if not dest:
            return
        if not dest.lower().endswith(".lanproj"):
            dest += ".lanproj"
        try:
            url, _ = load_sync_settings()
            sync_svc.clone_project(client, project_id=project_id, dest_path=dest, server_url=url)
            self._active_snapshot = self._service.open_project(dest)
            self._active_file = dest
            self._dirty = False
            self._refresh_ui()
            self._update_sync_status()
        except Exception as e:
            QMessageBox.critical(self, "Клонирование", str(e))

    def _on_sync_publish(self) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        if self._active_file is None or self._dirty:
            self._on_save()
            if self._active_file is None or self._dirty:
                return
        if sync_svc.load_sync_state(self._active_file) is not None:
            QMessageBox.information(
                self,
                "Синхронизация",
                "Проект уже привязан к серверу. Используйте Push.",
            )
            return
        try:
            url, _ = load_sync_settings()
            client = self._remote_client()
            sync_svc.publish_project(
                client,
                file_path=self._active_file,
                snapshot=snapshot,
                server_url=url,
            )
            self._service.save_project(file_path=self._active_file, snapshot=snapshot)
            self._update_sync_status()
            QMessageBox.information(self, "Синхронизация", "Проект опубликован на сервере.")
        except Exception as e:
            QMessageBox.critical(self, "Публикация", str(e))

    def _on_sync_push(self) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        if self._active_file is None or self._dirty:
            self._on_save()
            if self._active_file is None or self._dirty:
                return
        if sync_svc.load_sync_state(self._active_file) is None:
            self._on_sync_publish()
            return
        try:
            client = self._remote_client()
            sync_svc.push_project(
                client,
                file_path=self._active_file,
                snapshot=snapshot,
            )
            self._update_sync_status()
            QMessageBox.information(self, "Push", "Изменения отправлены на сервер.")
        except RemoteConflictError as e:
            self._resolve_push_conflict(e)
        except Exception as e:
            QMessageBox.critical(self, "Push", str(e))

    def _resolve_push_conflict(self, error: RemoteConflictError) -> None:
        remote = error.remote
        dialog = SyncConflictDialog(
            title="Конфликт Push",
            message=(
                f"На сервере другая revision ({remote.revision}, «{remote.name}»).\n"
                "Оставить локальное (отмена push), принять серверное (Pull) "
                "или принудительно перезаписать сервер?"
            ),
            allow_force_push=True,
            parent=self,
        )
        if dialog.exec() != SyncConflictDialog.DialogCode.Accepted or dialog.choice is None:
            return
        if dialog.choice == SyncConflictDialog.KEEP_LOCAL:
            return
        if dialog.choice == SyncConflictDialog.TAKE_REMOTE:
            self._on_sync_pull(force=True)
            return
        snapshot = self._require_snapshot()
        if snapshot is None or self._active_file is None:
            return
        try:
            client = self._remote_client()
            sync_svc.push_project(
                client,
                file_path=self._active_file,
                snapshot=snapshot,
                force=True,
            )
            self._update_sync_status()
            QMessageBox.information(self, "Push", "Сервер перезаписан локальной версией.")
        except Exception as e:
            QMessageBox.critical(self, "Push", str(e))

    def _on_sync_pull(self, force: bool = False) -> None:
        if self._active_file is None:
            QMessageBox.warning(self, "Pull", "Сначала откройте сохранённый проект.")
            return
        if sync_svc.load_sync_state(self._active_file) is None:
            QMessageBox.warning(
                self,
                "Pull",
                "Проект не привязан к серверу. Сначала опубликуйте или клонируйте.",
            )
            return
        if self._dirty and not force:
            answer = QMessageBox.question(
                self,
                "Pull",
                "Есть несохранённые изменения. Pull перезапишет локальный файл.\nПродолжить?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            client = self._remote_client()
            blob, _ = sync_svc.pull_project(client, file_path=self._active_file)
            self._active_snapshot = self._service.open_project(self._active_file)
            self._dirty = False
            self._refresh_ui()
            self._update_sync_status()
            QMessageBox.information(
                self,
                "Pull",
                f"Загружена серверная версия (rev {blob.info.revision}).",
            )
        except Exception as e:
            QMessageBox.critical(self, "Pull", str(e))

    def _on_export_csv(self) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return

        suggested = (snapshot.meta.name or "project").strip() or "project"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт CSV",
            f"{suggested}.ldcsv",
            "LanDesigner CSV (*.ldcsv);;CSV (*.csv);;Все файлы (*.*)",
        )
        if not file_path:
            return
        lower = file_path.lower()
        if not (lower.endswith(".ldcsv") or lower.endswith(".csv")):
            file_path += ".ldcsv"

        try:
            csv_io.export_snapshot(snapshot, file_path)
            self.statusBar().showMessage(f"Экспортировано: {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка экспорта", str(e))

    def _on_import_csv(self) -> None:
        if self._active_snapshot is not None and self._dirty:
            answer = QMessageBox.question(
                self,
                "Импорт CSV",
                "Есть несохранённые изменения. Импорт заменит текущие данные проекта.\nПродолжить?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        elif self._active_snapshot is not None:
            answer = QMessageBox.question(
                self,
                "Импорт CSV",
                "Импорт заменит данные открытого проекта (файл .lanproj не меняется до сохранения).\nПродолжить?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Импорт CSV",
            "",
            "LanDesigner CSV (*.ldcsv *.csv);;Все файлы (*.*)",
        )
        if not file_path:
            return

        try:
            imported = csv_io.import_snapshot(file_path)
            self._active_snapshot = imported
            # Импорт в текущую сессию: .lanproj-путь сохраняем, но помечаем dirty.
            self._dirty = True
            self._refresh_ui()
            self.statusBar().showMessage(
                f"Импортировано из CSV: {imported.meta.name} (сохраните .lanproj)"
            )
        except Exception as e:
            QMessageBox.critical(self, "Ошибка импорта", str(e))

    def _on_tree_add(self, kind: TreeKind) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return

        selected_kind, selected_id = self._site_tree.current()

        try:
            if kind == TreeKind.BUILDING:
                dlg = BuildingDialog(parent=self)
                if dlg.exec() != BuildingDialog.DialogCode.Accepted:
                    return
                name, address, notes = dlg.values()
                building = inventory_service.add_building(
                    snapshot, name, address=address, notes=notes
                )
                self._mark_dirty()
                self._device_card.show_building(building.id)
                return
            elif kind == TreeKind.FLOOR:
                if selected_kind != TreeKind.BUILDING or selected_id is None:
                    QMessageBox.information(self, "Этаж", "Выберите здание в дереве.")
                    return
                dlg = FloorDialog(parent=self)
                if dlg.exec() != FloorDialog.DialogCode.Accepted:
                    return
                name, level = dlg.values()
                inventory_service.add_floor(snapshot, selected_id, name, level)
            elif kind == TreeKind.ROOM:
                if selected_kind != TreeKind.FLOOR or selected_id is None:
                    QMessageBox.information(self, "Комната", "Выберите этаж в дереве.")
                    return
                dlg = NameDialog("Добавить комнату", parent=self)
                if dlg.exec() != NameDialog.DialogCode.Accepted:
                    return
                inventory_service.add_room(snapshot, selected_id, dlg.value() or "Комната")
            elif kind == TreeKind.RACK:
                if selected_kind != TreeKind.ROOM or selected_id is None:
                    QMessageBox.information(self, "Шкаф", "Выберите комнату в дереве.")
                    return
                dlg = RackDialog(parent=self)
                if dlg.exec() != RackDialog.DialogCode.Accepted:
                    return
                name, units = dlg.values()
                inventory_service.add_rack(snapshot, selected_id, name, units)
            else:
                return
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
            return

        self._mark_dirty()

    def _on_tree_edit(self, kind: TreeKind, obj_id: UUID) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return

        try:
            if kind == TreeKind.SITE:
                self._on_edit_project()
                return
            elif kind == TreeKind.BUILDING:
                building = next((b for b in snapshot.buildings if b.id == obj_id), None)
                if building is None:
                    return
                dlg = BuildingDialog(
                    initial_name=building.name,
                    initial_address=building.address,
                    initial_notes=building.notes,
                    parent=self,
                )
                if dlg.exec() != BuildingDialog.DialogCode.Accepted:
                    return
                name, address, notes = dlg.values()
                inventory_service.update_building(
                    snapshot, obj_id, name=name, address=address, notes=notes
                )
                self._mark_dirty()
                self._device_card.show_building(obj_id)
                return
            elif kind == TreeKind.FLOOR:
                floor = next((f for f in snapshot.floors if f.id == obj_id), None)
                if floor is None:
                    return
                dlg = FloorDialog(
                    initial_name=floor.name,
                    initial_level=floor.level,
                    parent=self,
                )
                if dlg.exec() != FloorDialog.DialogCode.Accepted:
                    return
                name, level = dlg.values()
                inventory_service.update_floor(snapshot, obj_id, name, level)
            elif kind == TreeKind.ROOM:
                room = next((r for r in snapshot.rooms if r.id == obj_id), None)
                if room is None:
                    return
                dlg = NameDialog("Изменить комнату", initial=room.name, parent=self)
                if dlg.exec() != NameDialog.DialogCode.Accepted:
                    return
                inventory_service.update_room(snapshot, obj_id, dlg.value() or room.name)
            elif kind == TreeKind.RACK:
                rack = next((rk for rk in snapshot.racks if rk.id == obj_id), None)
                if rack is None:
                    return
                dlg = RackDialog(
                    initial_name=rack.name,
                    initial_units=rack.units,
                    parent=self,
                )
                if dlg.exec() != RackDialog.DialogCode.Accepted:
                    return
                name, units = dlg.values()
                inventory_service.update_rack(snapshot, obj_id, name, units)
            else:
                return
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
            return

        self._mark_dirty()

    def _on_tree_delete(self, kind: TreeKind, obj_id: UUID) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        if kind == TreeKind.SITE:
            QMessageBox.information(
                self,
                "Площадка",
                "Площадку нельзя удалить. Можно только переименовать.",
            )
            return

        labels = {
            TreeKind.BUILDING: "здание",
            TreeKind.FLOOR: "этаж",
            TreeKind.ROOM: "комнату",
            TreeKind.RACK: "шкаф",
        }
        label = labels.get(kind)
        if label is None:
            return

        reply = QMessageBox.question(
            self,
            "Удаление",
            f"Удалить {label} вместе с вложенными объектами?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            if kind == TreeKind.BUILDING:
                inventory_service.delete_building(snapshot, obj_id)
            elif kind == TreeKind.FLOOR:
                inventory_service.delete_floor(snapshot, obj_id)
            elif kind == TreeKind.ROOM:
                inventory_service.delete_room(snapshot, obj_id)
            elif kind == TreeKind.RACK:
                inventory_service.delete_rack(snapshot, obj_id)
            else:
                return
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
            return

        self._mark_dirty()

    def _on_add_device_type(self) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        dlg = DeviceTypeDialog(parent=self)
        if dlg.exec() != DeviceTypeDialog.DialogCode.Accepted:
            return
        vendor, model, role, port_groups = dlg.values()
        if not port_groups:
            QMessageBox.warning(self, "Тип устройства", "Добавьте хотя бы одну группу портов.")
            return
        dtype = inventory_service.add_device_type(
            snapshot,
            vendor=vendor,
            model=model,
            role=role,
            port_groups=port_groups,
        )
        self._mark_dirty()
        speeds = sorted({int(p["speed"]) for p in dtype.port_template})
        speed_txt = "/".join(str(s) for s in speeds)
        self.statusBar().showMessage(
            f"Добавлен тип: {dtype.vendor} {dtype.model} "
            f"({len(dtype.port_template)} порт., {speed_txt} Мбит/с)"
        )

    def _on_add_device_type_from_catalog(self) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        dlg = DeviceTypeCatalogDialog(parent=self)
        if dlg.exec() != DeviceTypeCatalogDialog.DialogCode.Accepted:
            return
        key = dlg.selected_key()
        if not key:
            return
        try:
            dtype = catalog_svc.add_device_type_from_preset(snapshot, key)
        except Exception as e:
            QMessageBox.critical(self, "Каталог", str(e))
            return
        self._mark_dirty()
        self.statusBar().showMessage(
            f"Из каталога: {dtype.vendor} {dtype.model} ({len(dtype.port_template)} порт.)"
        )

    def _on_edit_device_type(self, type_id: UUID) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        device_type = next((dt for dt in snapshot.device_types if dt.id == type_id), None)
        if device_type is None:
            return

        dlg = DeviceTypeDialog(device_type=device_type, parent=self)
        if dlg.exec() != DeviceTypeDialog.DialogCode.Accepted:
            return
        vendor, model, role, port_groups = dlg.values()
        if not port_groups:
            QMessageBox.warning(self, "Тип устройства", "Добавьте хотя бы одну группу портов.")
            return

        in_use = any(d.device_type_id == type_id for d in snapshot.devices)
        if in_use:
            QMessageBox.information(
                self,
                "Тип устройства",
                "Тип обновлён. Порты уже созданных устройств не пересоздаются — "
                "новый шаблон применяется только к новым устройствам.",
            )

        inventory_service.update_device_type(
            snapshot,
            type_id,
            vendor=vendor,
            model=model,
            role=role,
            port_groups=port_groups,
        )
        self._mark_dirty()
        self.statusBar().showMessage(f"Тип обновлён: {vendor} {model}")

    def _on_delete_device_type(self, type_id: UUID) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        device_type = next((dt for dt in snapshot.device_types if dt.id == type_id), None)
        if device_type is None:
            return
        in_use = any(d.device_type_id == type_id for d in snapshot.devices)
        if in_use:
            QMessageBox.warning(
                self,
                "Тип устройства",
                f"Тип «{device_type.vendor} {device_type.model}» используется устройствами "
                "и не может быть удалён.",
            )
            return
        answer = QMessageBox.question(
            self,
            "Удалить тип",
            f"Удалить тип «{device_type.vendor} {device_type.model}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            inventory_service.delete_device_type(snapshot, type_id)
        except Exception as e:
            QMessageBox.critical(self, "Тип устройства", str(e))
            return
        self._mark_dirty()
        self.statusBar().showMessage(
            f"Удалён тип: {device_type.vendor} {device_type.model}"
        )

    def _on_export_type_preset(self) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        if not snapshot.device_types:
            QMessageBox.information(self, "Пресет типов", "В проекте нет типов устройств.")
            return
        suggested = (snapshot.meta.name or "types").strip() or "types"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт пресета типов",
            f"{suggested}.ldtypes",
            "Пресет типов (*.ldtypes);;Все файлы (*.*)",
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".ldtypes"):
            file_path += ".ldtypes"
        try:
            type_preset_svc.export_device_types(snapshot, file_path)
            self.statusBar().showMessage(f"Пресет экспортирован: {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Экспорт пресета", str(e))

    def _on_import_type_preset(self) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Импорт пресета типов",
            "",
            "Пресет типов (*.ldtypes);;Все файлы (*.*)",
        )
        if not file_path:
            return
        try:
            result = type_preset_svc.import_device_types(snapshot, file_path)
        except Exception as e:
            QMessageBox.critical(self, "Импорт пресета", str(e))
            return
        if result.added or result.updated:
            self._mark_dirty()
        QMessageBox.information(
            self,
            "Импорт пресета",
            f"Импорт завершён: {result.summary()}.",
        )
        self.statusBar().showMessage(f"Импорт типов: {result.summary()}")

    def _on_add_device(self) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        if not snapshot.device_types:
            QMessageBox.information(
                self,
                "Устройство",
                "Сначала добавьте тип на вкладке «Каталог».",
            )
            return

        dlg = DeviceDialog(snapshot, parent=self)
        if dlg.exec() != DeviceDialog.DialogCode.Accepted:
            return
        if not dlg.is_valid():
            QMessageBox.warning(self, "Устройство", "Укажите тип, имя хоста и гипервизор (для ВМ).")
            return

        type_id, hostname, serial, tag, room_id, rack_id, rack_u, rack_h, host_id = (
            dlg.values()
        )
        try:
            inventory_service.add_device(
                snapshot,
                device_type_id=type_id,
                hostname=hostname,
                serial=serial,
                inventory_tag=tag,
                room_id=room_id,
                rack_id=rack_id,
                rack_u=rack_u,
                rack_u_height=rack_h,
                host_device_id=host_id,
            )
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
            return
        self._mark_dirty()

    def _on_edit_device(self, device_id: UUID) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        device = next((d for d in snapshot.devices if d.id == device_id), None)
        if device is None:
            return

        dlg = DeviceDialog(snapshot, device=device, parent=self)
        if dlg.exec() != DeviceDialog.DialogCode.Accepted:
            return
        if not dlg.is_valid():
            QMessageBox.warning(self, "Устройство", "Укажите имя хоста (для ВМ — и гипервизор).")
            return

        _, hostname, serial, tag, room_id, rack_id, rack_u, rack_h, host_id = dlg.values()
        try:
            inventory_service.update_device(
                snapshot,
                device_id,
                hostname=hostname,
                serial=serial,
                inventory_tag=tag,
                room_id=room_id,
                rack_id=rack_id,
                rack_u=rack_u,
                rack_u_height=rack_h,
                host_device_id=host_id,
                clear_room=room_id is None and host_id is None,
                clear_rack=room_id is not None and rack_id is None,
            )
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
            return
        self._mark_dirty()

    def _on_delete_device(self, device_id: UUID) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        answer = QMessageBox.question(
            self,
            "Удалить устройство",
            "Удалить устройство вместе с портами? Связанные кабели будут разорваны.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            inventory_service.delete_device(snapshot, device_id)
        except Exception as e:
            QMessageBox.critical(self, "Удаление", str(e))
            return
        self._mark_dirty()

    def _on_add_cable(self) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        if len(snapshot.devices) < 2:
            QMessageBox.information(
                self,
                "Кабель",
                "Нужны как минимум два устройства со свободными портами.",
            )
            return
        dlg = CableDialog(snapshot, parent=self)
        if dlg.exec() != CableDialog.DialogCode.Accepted:
            return
        if not dlg.is_valid():
            QMessageBox.warning(self, "Кабель", "Выберите оба порта.")
            return
        try:
            end_a, end_b, label, kind, category, length_m = dlg.values()
            cable = inventory_service.add_cable(
                snapshot,
                end_a,
                end_b,
                label=label,
                kind=kind,
                category=category,
                length_m=length_m,
            )
        except Exception as e:
            QMessageBox.critical(self, "Кабель", str(e))
            return
        self._mark_dirty()
        self.statusBar().showMessage(
            f"Кабель: {inventory_service.port_endpoint_label(snapshot, cable.end_a_port_id)} ↔ "
            f"{inventory_service.port_endpoint_label(snapshot, cable.end_b_port_id)}"
        )

    def _on_edit_cable(self, cable_id: UUID) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        cable = next((c for c in snapshot.cables if c.id == cable_id), None)
        if cable is None:
            return
        dlg = CableDialog(snapshot, cable=cable, parent=self)
        if dlg.exec() != CableDialog.DialogCode.Accepted:
            return
        try:
            _, _, label, kind, category, length_m = dlg.values()
            inventory_service.update_cable(
                snapshot,
                cable_id,
                label=label,
                kind=kind,
                category=category,
                length_m=length_m,
                clear_length=length_m is None,
            )
        except Exception as e:
            QMessageBox.critical(self, "Кабель", str(e))
            return
        self._mark_dirty()

    def _on_delete_cable(self, cable_id: UUID) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        answer = QMessageBox.question(
            self,
            "Разорвать кабель",
            "Удалить кабель и освободить порты?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        inventory_service.delete_cable(snapshot, cable_id)
        self._mark_dirty()
        self.statusBar().showMessage("Кабель удалён")

    def _on_add_vlan(self) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        dlg = VlanDialog(parent=self)
        if dlg.exec() != VlanDialog.DialogCode.Accepted:
            return
        vlan_id, name, description = dlg.values()
        try:
            vlan = inventory_service.add_vlan(snapshot, vlan_id, name, description)
        except Exception as e:
            QMessageBox.critical(self, "VLAN", str(e))
            return
        self._mark_dirty()
        self.statusBar().showMessage(f"Добавлен VLAN {vlan.vlan_id}")

    def _on_edit_vlan(self, vlan_uuid: UUID) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        vlan = next((v for v in snapshot.vlans if v.id == vlan_uuid), None)
        if vlan is None:
            return
        dlg = VlanDialog(
            initial_vlan_id=vlan.vlan_id,
            initial_name=vlan.name,
            initial_description=vlan.description,
            editing=True,
            parent=self,
        )
        if dlg.exec() != VlanDialog.DialogCode.Accepted:
            return
        vlan_id, name, description = dlg.values()
        try:
            inventory_service.update_vlan(
                snapshot,
                vlan_uuid,
                vlan_id=vlan_id,
                name=name,
                description=description,
            )
        except Exception as e:
            QMessageBox.critical(self, "VLAN", str(e))
            return
        self._mark_dirty()

    def _on_delete_vlan(self, vlan_uuid: UUID) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        answer = QMessageBox.question(
            self,
            "Удалить VLAN",
            "Удалить VLAN? С портов будет снят access VLAN.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        inventory_service.delete_vlan(snapshot, vlan_uuid)
        self._mark_dirty()

    def _on_add_ip(self) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        preferred = self._inventory_view.selected_port_id()
        dlg = IpDialog(snapshot, preferred_port_id=preferred, parent=self)
        if dlg.exec() != IpDialog.DialogCode.Accepted:
            return
        if not dlg.is_valid():
            QMessageBox.warning(self, "IP", "Укажите адрес.")
            return
        address, cidr, gateway, port_id, lag_id = dlg.values()
        try:
            ip = inventory_service.add_ip(
                snapshot,
                address=address,
                cidr=cidr,
                gateway=gateway,
                port_id=port_id,
                lag_id=lag_id,
            )
        except Exception as e:
            QMessageBox.critical(self, "IP", str(e))
            return
        self._mark_dirty()
        self.statusBar().showMessage(f"Добавлен IP {inventory_service.ip_label(ip)}")

    def _on_edit_ip(self, ip_id: UUID) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        ip = next((item for item in snapshot.ips if item.id == ip_id), None)
        if ip is None:
            return
        dlg = IpDialog(snapshot, ip=ip, parent=self)
        if dlg.exec() != IpDialog.DialogCode.Accepted:
            return
        if not dlg.is_valid():
            QMessageBox.warning(self, "IP", "Укажите адрес.")
            return
        address, cidr, gateway, port_id, lag_id = dlg.values()
        try:
            inventory_service.update_ip(
                snapshot,
                ip_id,
                address=address,
                cidr=cidr,
                gateway=gateway,
                port_id=port_id,
                lag_id=lag_id,
                clear_port=port_id is None and lag_id is None,
                clear_lag=port_id is None and lag_id is None,
            )
        except Exception as e:
            QMessageBox.critical(self, "IP", str(e))
            return
        self._mark_dirty()

    def _on_delete_ip(self, ip_id: UUID) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        answer = QMessageBox.question(self, "Удалить IP", "Удалить IP-адрес?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        inventory_service.delete_ip(snapshot, ip_id)
        self._mark_dirty()

    def _on_add_lag(self) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        if not snapshot.devices:
            QMessageBox.information(self, "LAG", "Сначала добавьте устройство.")
            return
        preferred = self._inventory_view.selected_device_id()
        dlg = LagDialog(snapshot, preferred_device_id=preferred, parent=self)
        if dlg.exec() != LagDialog.DialogCode.Accepted:
            return
        if not dlg.is_valid():
            QMessageBox.warning(self, "LAG", "Выберите устройство и минимум два порта.")
            return
        device_id, name, mode, members, notes, mac = dlg.values()
        try:
            lag = inventory_service.add_lag(
                snapshot,
                device_id=device_id,
                name=name,
                mode=mode,
                member_port_ids=members,
                notes=notes,
                mac=mac,
            )
        except Exception as e:
            QMessageBox.critical(self, "LAG", str(e))
            return
        self._mark_dirty()
        self.statusBar().showMessage(f"Добавлен LAG {lag.name}")

    def _on_edit_lag(self, lag_id: UUID) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        lag = next((item for item in snapshot.lags if item.id == lag_id), None)
        if lag is None:
            return
        dlg = LagDialog(snapshot, lag=lag, parent=self)
        if dlg.exec() != LagDialog.DialogCode.Accepted:
            return
        if not dlg.is_valid():
            QMessageBox.warning(self, "LAG", "Выберите минимум два порта.")
            return
        _device_id, name, mode, members, notes, mac = dlg.values()
        try:
            inventory_service.update_lag(
                snapshot,
                lag_id,
                name=name,
                mode=mode,
                member_port_ids=members,
                notes=notes,
                mac=mac,
            )
        except Exception as e:
            QMessageBox.critical(self, "LAG", str(e))
            return
        self._mark_dirty()

    def _on_delete_lag(self, lag_id: UUID) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        answer = QMessageBox.question(
            self,
            "Удалить LAG",
            "Удалить LAG? Связанные IP будут удалены, порты и кабели останутся.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        inventory_service.delete_lag(snapshot, lag_id)
        self._mark_dirty()

    def _on_add_port(self) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        device_id = self._inventory_view.selected_device_id()
        if device_id is None:
            QMessageBox.information(self, "Порт", "Выберите устройство.")
            return
        dlg = PortPropertiesDialog(snapshot, device_id=device_id, parent=self)
        if dlg.exec() != PortPropertiesDialog.DialogCode.Accepted:
            return
        name, speed, media, mac = dlg.values()
        try:
            port = inventory_service.add_port(
                snapshot, device_id, name, speed=speed, media=media, mac=mac
            )
        except Exception as e:
            QMessageBox.critical(self, "Порт", str(e))
            return
        self._mark_dirty()
        self.statusBar().showMessage(f"Добавлен порт {port.name}")

    def _on_delete_port(self, port_id: UUID) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        port = next((p for p in snapshot.ports if p.id == port_id), None)
        if port is None:
            return
        label = inventory_service.port_endpoint_label(snapshot, port_id)
        answer = QMessageBox.question(
            self,
            "Удалить порт",
            f"Удалить порт «{label}»?\n"
            "Кабель и IP на этом порту будут сняты.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            inventory_service.delete_port(snapshot, port_id)
        except Exception as e:
            QMessageBox.critical(self, "Порт", str(e))
            return
        self._mark_dirty()
        self.statusBar().showMessage(f"Порт удалён: {port.name}")

    def _on_edit_port_properties(self, port_id: UUID) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        if not any(p.id == port_id for p in snapshot.ports):
            return
        dlg = PortPropertiesDialog(snapshot, port_id, parent=self)
        if dlg.exec() != PortPropertiesDialog.DialogCode.Accepted:
            return
        name, speed, media, mac = dlg.values()
        try:
            inventory_service.update_port(
                snapshot, port_id, name=name, speed=speed, media=media, mac=mac
            )
        except Exception as e:
            QMessageBox.critical(self, "Порт", str(e))
            return
        self._mark_dirty()
        self.statusBar().showMessage(f"Порт обновлён: {name}")

    def _on_edit_port_network(self, port_id: UUID) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        if not any(p.id == port_id for p in snapshot.ports):
            return
        dlg = PortNetworkDialog(snapshot, port_id, parent=self)
        if dlg.exec() != PortNetworkDialog.DialogCode.Accepted:
            return
        mode, vlan_uuid, tagged, address, cidr, gateway, existing_ip_id = dlg.values()
        try:
            inventory_service.set_port_network(
                snapshot,
                port_id,
                mode=mode,
                access_vlan_id=vlan_uuid,
                tagged_vlan_ids=tagged,
            )
            if address:
                if existing_ip_id is not None:
                    inventory_service.update_ip(
                        snapshot,
                        existing_ip_id,
                        address=address,
                        cidr=cidr,
                        gateway=gateway,
                        port_id=port_id,
                    )
                else:
                    inventory_service.add_ip(
                        snapshot,
                        address=address,
                        cidr=cidr,
                        gateway=gateway,
                        port_id=port_id,
                    )
            elif existing_ip_id is not None:
                inventory_service.delete_ip(snapshot, existing_ip_id)
        except Exception as e:
            QMessageBox.critical(self, "Сеть порта", str(e))
            return
        self._mark_dirty()
        self.statusBar().showMessage(
            f"Сеть обновлена: {inventory_service.port_endpoint_label(snapshot, port_id)}"
        )
