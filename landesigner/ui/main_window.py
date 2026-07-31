from __future__ import annotations

from uuid import UUID

from PySide6.QtGui import QAction
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
from landesigner.domain.entities import ProjectMeta, ProjectSnapshot, Site, utcnow
from landesigner.services import inventory as inventory_service
from landesigner.services.project import ProjectService
from landesigner.ui.dialogs.inventory_dialogs import (
    CableDialog,
    DeviceDialog,
    DeviceTypeDialog,
    FloorDialog,
    IpDialog,
    NameDialog,
    PortNetworkDialog,
    RackDialog,
    VlanDialog,
)
from landesigner.ui.views.inventory_view import InventoryView
from landesigner.ui.widgets.empty_pane import EmptyPane
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
        self._inventory_view = InventoryView()

        self._init_ui()
        self._wire_signals()

    def _init_ui(self) -> None:
        self.setMinimumSize(1200, 750)

        status = QStatusBar(self)
        self.setStatusBar(status)
        status.showMessage("Готово · локальный проект")

        menu = self.menuBar()
        file_menu = menu.addMenu("Файл")
        action_new = QAction("Новый…", self)
        action_open = QAction("Открыть…", self)
        action_save = QAction("Сохранить", self)
        action_exit = QAction("Выход", self)
        file_menu.addAction(action_new)
        file_menu.addAction(action_open)
        file_menu.addAction(action_save)
        file_menu.addSeparator()
        file_menu.addAction(action_exit)
        action_exit.triggered.connect(self.close)
        action_new.triggered.connect(self._on_new)
        action_open.triggered.connect(self._on_open)
        action_save.triggered.connect(self._on_save)

        central = QWidget(self)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 10, 8)
        layout.setSpacing(0)

        splitter = QSplitter(central)
        splitter.setHandleWidth(3)
        splitter.addWidget(self._site_tree)

        right = QWidget(splitter)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 8, 0, 0)
        tabs = QTabWidget(right)
        tabs.setDocumentMode(True)
        tabs.addTab(
            EmptyPane(
                "Схема топологии",
                "Здесь появится редактор связей между устройствами.\nПока собираем CMDB — кабели уже в инвентаре.",
                tabs,
            ),
            "Схема",
        )
        tabs.addTab(
            EmptyPane(
                "План этажа",
                "Подложка здания и расстановка оборудования.\nСледующий крупный этап после схемы.",
                tabs,
            ),
            "План",
        )
        tabs.addTab(self._inventory_view, "Инвентарь")
        tabs.addTab(
            EmptyPane(
                "Отчёты",
                "Реестр оборудования, порт-матрица, VLAN map — позже.\nДанные уже копятся в проекте.",
                tabs,
            ),
            "Отчёты",
        )
        tabs.setCurrentIndex(2)
        right_layout.addWidget(tabs)
        splitter.addWidget(right)
        splitter.setSizes([300, 920])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)
        self.setCentralWidget(central)

    def _wire_signals(self) -> None:
        self._site_tree.add_requested.connect(self._on_tree_add)
        self._site_tree.edit_requested.connect(self._on_tree_edit)
        self._site_tree.delete_requested.connect(self._on_tree_delete)
        self._inventory_view.add_device_type_requested.connect(self._on_add_device_type)
        self._inventory_view.edit_device_type_requested.connect(self._on_edit_device_type)
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
        self._inventory_view.edit_port_network_requested.connect(self._on_edit_port_network)

    def _refresh_ui(self) -> None:
        self._site_tree.set_snapshot(self._active_snapshot)
        self._inventory_view.set_snapshot(self._active_snapshot)
        title = "LanDesigner"
        if self._active_snapshot is not None:
            title += f" — {self._active_snapshot.meta.name}"
            if self._dirty:
                title += " *"
        self.setWindowTitle(title)

    def _mark_dirty(self) -> None:
        self._dirty = True
        self._refresh_ui()
        self.statusBar().showMessage("Есть несохранённые изменения")

    def _require_snapshot(self) -> ProjectSnapshot | None:
        if self._active_snapshot is None:
            QMessageBox.warning(self, "Проект", "Сначала создайте или откройте проект.")
            return None
        return self._active_snapshot

    def _on_new(self) -> None:
        self._active_file = None
        meta = ProjectMeta(name="Новый проект")
        site = Site(project_id=meta.id, name="Площадка")
        self._active_snapshot = ProjectSnapshot(meta=meta, sites=[site])
        self._dirty = True
        self._refresh_ui()
        self.statusBar().showMessage("Создан новый проект (нужно сохранить .lanproj)")

    def _on_open(self) -> None:
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
            self.statusBar().showMessage(f"Открыт проект: {self._active_snapshot.meta.name}")
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
            self.statusBar().showMessage(f"Проект сохранён: {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка сохранения", str(e))

    def _on_tree_add(self, kind: TreeKind) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return

        selected_kind, selected_id = self._site_tree.current()

        try:
            if kind == TreeKind.BUILDING:
                dlg = NameDialog("Добавить здание", parent=self)
                if dlg.exec() != NameDialog.DialogCode.Accepted:
                    return
                inventory_service.add_building(snapshot, dlg.value() or "Здание")
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
                site = next((s for s in snapshot.sites if s.id == obj_id), None)
                if site is None:
                    return
                dlg = NameDialog("Переименовать площадку", initial=site.name, parent=self)
                if dlg.exec() != NameDialog.DialogCode.Accepted:
                    return
                inventory_service.update_site(snapshot, obj_id, dlg.value() or site.name)
            elif kind == TreeKind.BUILDING:
                building = next((b for b in snapshot.buildings if b.id == obj_id), None)
                if building is None:
                    return
                dlg = NameDialog("Изменить здание", initial=building.name, parent=self)
                if dlg.exec() != NameDialog.DialogCode.Accepted:
                    return
                inventory_service.update_building(snapshot, obj_id, dlg.value() or building.name)
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

    def _on_add_device(self) -> None:
        snapshot = self._require_snapshot()
        if snapshot is None:
            return
        if not snapshot.device_types:
            QMessageBox.information(self, "Устройство", "Сначала создайте тип устройства.")
            return

        dlg = DeviceDialog(snapshot, parent=self)
        if dlg.exec() != DeviceDialog.DialogCode.Accepted:
            return
        if not dlg.is_valid():
            QMessageBox.warning(self, "Устройство", "Укажите тип и имя хоста.")
            return

        type_id, hostname, serial, tag, room_id = dlg.values()
        try:
            inventory_service.add_device(
                snapshot,
                device_type_id=type_id,
                hostname=hostname,
                serial=serial,
                inventory_tag=tag,
                room_id=room_id,
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
            QMessageBox.warning(self, "Устройство", "Укажите имя хоста.")
            return

        _, hostname, serial, tag, room_id = dlg.values()
        inventory_service.update_device(
            snapshot,
            device_id,
            hostname=hostname,
            serial=serial,
            inventory_tag=tag,
            room_id=room_id,
            clear_room=room_id is None,
        )
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
        inventory_service.delete_device(snapshot, device_id)
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
        vlan_id, name = dlg.values()
        try:
            vlan = inventory_service.add_vlan(snapshot, vlan_id, name)
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
            editing=True,
            parent=self,
        )
        if dlg.exec() != VlanDialog.DialogCode.Accepted:
            return
        vlan_id, name = dlg.values()
        try:
            inventory_service.update_vlan(
                snapshot, vlan_uuid, vlan_id=vlan_id, name=name
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
        address, cidr, gateway, port_id = dlg.values()
        try:
            ip = inventory_service.add_ip(
                snapshot,
                address=address,
                cidr=cidr,
                gateway=gateway,
                port_id=port_id,
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
        address, cidr, gateway, port_id = dlg.values()
        try:
            inventory_service.update_ip(
                snapshot,
                ip_id,
                address=address,
                cidr=cidr,
                gateway=gateway,
                port_id=port_id,
                clear_port=port_id is None,
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
