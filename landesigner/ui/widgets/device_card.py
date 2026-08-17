from __future__ import annotations

from enum import Enum
from uuid import UUID

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from landesigner.domain.entities import Building, Device, ProjectSnapshot, Rack
from landesigner.domain.enums import PortStatus
from landesigner.services import inventory as inv
from landesigner.ui.labels import lag_mode_label, role_label
from landesigner.ui.widgets.panel_card import PanelCard


class ContextKind(str, Enum):
    EMPTY = "empty"
    PROJECT = "project"
    BUILDING = "building"
    RACK = "rack"
    DEVICE = "device"


class ContextCard(QWidget):
    """Контекстная карточка: проект / здание / устройство."""

    edit_project_requested = Signal()
    edit_building_requested = Signal(object)  # UUID
    edit_device_requested = Signal(object)  # UUID
    show_on_topology_requested = Signal(object)  # UUID
    show_on_floor_plan_requested = Signal(object)  # UUID

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(260)
        self.setMaximumWidth(400)
        self._snapshot: ProjectSnapshot | None = None
        self._kind = ContextKind.EMPTY
        self._building_id: UUID | None = None
        self._rack_id: UUID | None = None
        self._device_id: UUID | None = None
        self._project_file: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._card = PanelCard("Свойства", self, subtitle="Нет открытого проекта")
        self._btn_edit = QPushButton("Изменить…", self._card)
        self._btn_topo = QPushButton("На схеме", self._card)
        self._btn_plan = QPushButton("На плане", self._card)
        self._btn_edit.clicked.connect(self._emit_edit)
        self._btn_topo.clicked.connect(self._emit_topo)
        self._btn_plan.clicked.connect(self._emit_plan)
        self._card.add_action(self._btn_edit)
        self._card.add_action(self._btn_topo)
        self._card.add_action(self._btn_plan)

        self._stack = QStackedWidget(self._card)
        self._page_empty = self._build_empty_page()
        self._page_project = self._build_project_page()
        self._page_building = self._build_building_page()
        self._page_rack = self._build_rack_page()
        self._page_device = self._build_device_page()
        self._stack.addWidget(self._page_empty)
        self._stack.addWidget(self._page_project)
        self._stack.addWidget(self._page_building)
        self._stack.addWidget(self._page_rack)
        self._stack.addWidget(self._page_device)
        self._card.set_body_widget(self._stack)
        root.addWidget(self._card)

        self._set_nav_visible(False)
        self._btn_edit.setEnabled(False)

    def _title_label(self, parent: QWidget) -> QLabel:
        label = QLabel("—", parent)
        font = QFont(label.font())
        font.setPointSize(12)
        font.setBold(True)
        label.setFont(font)
        label.setStyleSheet("color: #2f7c85;")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def _muted(self, parent: QWidget, text: str = "") -> QLabel:
        label = QLabel(text, parent)
        label.setWordWrap(True)
        label.setProperty("muted", True)
        label.setObjectName("PanelSubtitle")
        return label

    def _build_empty_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        hint = self._muted(
            page,
            "Откройте или создайте проект.\n"
            "Выберите площадку, здание или устройство.",
        )
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)
        layout.addWidget(hint)
        layout.addStretch(1)
        return page

    def _build_project_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._proj_title = self._title_label(page)
        layout.addWidget(self._proj_title)
        form = QFormLayout()
        form.setSpacing(4)
        form.setContentsMargins(0, 0, 0, 0)
        self._proj_site = QLabel("—", page)
        self._proj_address = QLabel("—", page)
        self._proj_notes = QLabel("—", page)
        self._proj_revision = QLabel("—", page)
        self._proj_origin = QLabel("—", page)
        self._proj_updated = QLabel("—", page)
        self._proj_file = QLabel("—", page)
        self._proj_stats = QLabel("—", page)
        for label in (
            self._proj_site,
            self._proj_address,
            self._proj_notes,
            self._proj_revision,
            self._proj_origin,
            self._proj_updated,
            self._proj_file,
            self._proj_stats,
        ):
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Площадка", self._proj_site)
        form.addRow("Адрес", self._proj_address)
        form.addRow("Заметки", self._proj_notes)
        form.addRow("Ревизия", self._proj_revision)
        form.addRow("Источник", self._proj_origin)
        form.addRow("Обновлён", self._proj_updated)
        form.addRow("Файл", self._proj_file)
        form.addRow("Состав", self._proj_stats)
        layout.addLayout(form)
        layout.addStretch(1)
        return page

    def _build_building_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._bld_title = self._title_label(page)
        layout.addWidget(self._bld_title)
        form = QFormLayout()
        form.setSpacing(4)
        form.setContentsMargins(0, 0, 0, 0)
        self._bld_address = QLabel("—", page)
        self._bld_notes = QLabel("—", page)
        self._bld_stats = QLabel("—", page)
        self._bld_floors = QLabel("—", page)
        for label in (self._bld_address, self._bld_notes, self._bld_stats, self._bld_floors):
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Адрес", self._bld_address)
        form.addRow("Заметки", self._bld_notes)
        form.addRow("Состав", self._bld_stats)
        form.addRow("Этажи", self._bld_floors)
        layout.addLayout(form)
        layout.addStretch(1)
        return page

    def _build_rack_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._rack_title = self._title_label(page)
        layout.addWidget(self._rack_title)
        form = QFormLayout()
        form.setSpacing(4)
        form.setContentsMargins(0, 0, 0, 0)
        self._rack_location = QLabel("—", page)
        self._rack_units = QLabel("—", page)
        self._rack_fill = QLabel("—", page)
        self._rack_devices = QLabel("—", page)
        for label in (
            self._rack_location,
            self._rack_units,
            self._rack_fill,
            self._rack_devices,
        ):
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Расположение", self._rack_location)
        form.addRow("Высота", self._rack_units)
        form.addRow("Занято", self._rack_fill)
        form.addRow("Устройства", self._rack_devices)
        layout.addLayout(form)
        layout.addStretch(1)
        return page

    def _build_device_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._dev_title = self._title_label(page)
        layout.addWidget(self._dev_title)
        form = QFormLayout()
        form.setSpacing(4)
        form.setContentsMargins(0, 0, 0, 0)
        self._dev_role = QLabel("—", page)
        self._dev_type = QLabel("—", page)
        self._dev_serial = QLabel("—", page)
        self._dev_tag = QLabel("—", page)
        self._dev_host = QLabel("—", page)
        self._dev_vms = QLabel("—", page)
        self._dev_location = QLabel("—", page)
        self._dev_ports = QLabel("—", page)
        self._dev_lags = QLabel("—", page)
        for label in (
            self._dev_role,
            self._dev_type,
            self._dev_serial,
            self._dev_tag,
            self._dev_host,
            self._dev_vms,
            self._dev_location,
            self._dev_ports,
            self._dev_lags,
        ):
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Роль", self._dev_role)
        form.addRow("Тип", self._dev_type)
        form.addRow("S/N", self._dev_serial)
        form.addRow("Инв. №", self._dev_tag)
        form.addRow("Гипервизор", self._dev_host)
        form.addRow("ВМ", self._dev_vms)
        form.addRow("Расположение", self._dev_location)
        form.addRow("Порты", self._dev_ports)
        form.addRow("LAG", self._dev_lags)
        layout.addLayout(form)
        layout.addStretch(1)
        return page

    def set_project_file(self, path: str | None) -> None:
        self._project_file = path
        if self._kind == ContextKind.PROJECT and self._snapshot is not None:
            self.show_project()

    def set_snapshot(self, snapshot: ProjectSnapshot | None) -> None:
        self._snapshot = snapshot
        if snapshot is None:
            self.clear()
            return
        if self._kind == ContextKind.DEVICE and self._device_id is not None:
            if any(d.id == self._device_id for d in snapshot.devices):
                self.show_device(self._device_id)
                return
        if self._kind == ContextKind.RACK and self._rack_id is not None:
            if any(r.id == self._rack_id for r in snapshot.racks):
                self.show_rack(self._rack_id)
                return
        if self._kind == ContextKind.BUILDING and self._building_id is not None:
            if any(b.id == self._building_id for b in snapshot.buildings):
                self.show_building(self._building_id)
                return
        self.show_project()

    def clear(self) -> None:
        self._kind = ContextKind.EMPTY
        self._building_id = None
        self._rack_id = None
        self._device_id = None
        self._card.set_subtitle("Нет открытого проекта")
        self._stack.setCurrentWidget(self._page_empty)
        self._set_nav_visible(False)
        self._btn_edit.setEnabled(False)

    def show_project(self) -> None:
        if self._snapshot is None:
            self.clear()
            return
        self._kind = ContextKind.PROJECT
        self._building_id = None
        self._rack_id = None
        self._device_id = None
        self._fill_project()
        self._stack.setCurrentWidget(self._page_project)
        self._set_nav_visible(False)
        self._btn_edit.setEnabled(True)

    def show_building(self, building_id: UUID | None) -> None:
        if building_id is None or self._snapshot is None:
            self.show_project()
            return
        building = next((b for b in self._snapshot.buildings if b.id == building_id), None)
        if building is None:
            self.show_project()
            return
        self._kind = ContextKind.BUILDING
        self._building_id = building_id
        self._rack_id = None
        self._device_id = None
        self._fill_building(building)
        self._stack.setCurrentWidget(self._page_building)
        self._set_nav_visible(False)
        self._btn_edit.setEnabled(True)

    def show_rack(self, rack_id: UUID | None) -> None:
        if rack_id is None or self._snapshot is None:
            self.show_project()
            return
        rack = next((r for r in self._snapshot.racks if r.id == rack_id), None)
        if rack is None:
            self.show_project()
            return
        self._kind = ContextKind.RACK
        self._rack_id = rack_id
        self._building_id = None
        self._device_id = None
        self._fill_rack(rack)
        self._stack.setCurrentWidget(self._page_rack)
        self._set_nav_visible(False)
        self._btn_edit.setEnabled(True)

    def show_device(self, device_id: UUID | None) -> None:
        if device_id is None or self._snapshot is None:
            self.show_project()
            return
        device = next((d for d in self._snapshot.devices if d.id == device_id), None)
        if device is None:
            self.show_project()
            return
        self._kind = ContextKind.DEVICE
        self._device_id = device_id
        self._building_id = None
        self._rack_id = None
        self._fill_device(device)
        self._stack.setCurrentWidget(self._page_device)
        self._set_nav_visible(True)
        self._btn_edit.setEnabled(True)

    def current_device_id(self) -> UUID | None:
        return self._device_id if self._kind == ContextKind.DEVICE else None

    def current_building_id(self) -> UUID | None:
        return self._building_id if self._kind == ContextKind.BUILDING else None

    def _fill_project(self) -> None:
        assert self._snapshot is not None
        snap = self._snapshot
        meta = snap.meta
        site = snap.sites[0] if snap.sites else None
        stats = inv.project_stats(snap)
        self._card.set_subtitle("Проект")
        self._proj_title.setText(meta.name or "—")
        self._proj_site.setText(site.name if site else "—")
        self._proj_address.setText((site.address if site else "") or "—")
        self._proj_notes.setText((site.notes if site else "") or "—")
        self._proj_revision.setText(str(meta.revision))
        origin = {"local": "локальный", "remote": "сервер"}.get(meta.origin, meta.origin)
        self._proj_origin.setText(origin or "—")
        stamp = meta.updated_at.strftime("%Y-%m-%d %H:%M") if meta.updated_at else "—"
        self._proj_updated.setText(stamp)
        self._proj_file.setText(self._project_file or "ещё не сохранён")
        self._proj_stats.setText(
            f"зданий {stats['buildings']} · этажей {stats['floors']} · "
            f"комнат {stats['rooms']} · шкафов {stats['racks']}\n"
            f"устройств {stats['devices']} · типов {stats['types']} · "
            f"кабелей {stats['cables']} · VLAN {stats['vlans']}"
        )

    def _fill_building(self, building: Building) -> None:
        assert self._snapshot is not None
        snap = self._snapshot
        stats = inv.building_stats(snap, building.id)
        floors = sorted(
            (f for f in snap.floors if f.building_id == building.id),
            key=lambda f: (f.level, f.name),
        )
        floors_txt = (
            "\n".join(f"{f.name} (ур. {f.level:g})" for f in floors) if floors else "—"
        )
        self._card.set_subtitle("Здание")
        self._bld_title.setText(building.name or "—")
        self._bld_address.setText(building.address or "—")
        self._bld_notes.setText(building.notes or "—")
        self._bld_stats.setText(
            f"этажей {stats['floors']} · комнат {stats['rooms']} · "
            f"шкафов {stats['racks']} · устройств {stats['devices']}"
        )
        self._bld_floors.setText(floors_txt)

    def _fill_rack(self, rack: Rack) -> None:
        assert self._snapshot is not None
        snap = self._snapshot
        room = next((r for r in snap.rooms if r.id == rack.room_id), None)
        floor = (
            next((f for f in snap.floors if f.id == room.floor_id), None)
            if room is not None
            else None
        )
        building = (
            next((b for b in snap.buildings if b.id == floor.building_id), None)
            if floor is not None
            else None
        )
        loc_parts = [
            p.name
            for p in (building, floor, room)
            if p is not None
        ]
        devices = inv.devices_in_rack(snap, rack.id)
        used = 0
        lines: list[str] = []
        for device in devices:
            label = inv.rack_placement_label(device) or "U?"
            lines.append(f"{label} · {device.hostname}")
            rng = inv.rack_u_range(device)
            if rng is not None:
                used += rng[1] - rng[0] + 1
        self._card.set_subtitle("Шкаф")
        self._rack_title.setText(rack.name or "—")
        self._rack_location.setText(" / ".join(loc_parts) if loc_parts else "—")
        self._rack_units.setText(f"{rack.units} U")
        self._rack_fill.setText(f"{used} из {rack.units} U · устройств {len(devices)}")
        self._rack_devices.setText("\n".join(lines) if lines else "—")

    def _fill_device(self, device: Device) -> None:
        assert self._snapshot is not None
        snap = self._snapshot
        dtype = next((t for t in snap.device_types if t.id == device.device_type_id), None)
        type_txt = f"{dtype.vendor} {dtype.model}".strip() if dtype else "—"
        ports = inv.ports_for_device(snap, device.id)
        occupied = sum(1 for p in ports if p.status == PortStatus.OCCUPIED)
        free = sum(1 for p in ports if p.status == PortStatus.FREE)
        other = len(ports) - occupied - free
        parts = [f"{len(ports)} всего", f"{occupied} занято", f"{free} свободно"]
        if other:
            parts.append(f"{other} прочие")
        summary = " · ".join(parts)
        self._card.set_subtitle(f"Устройство · {role_label(device.role)}")
        self._dev_title.setText(device.hostname or "—")
        self._dev_role.setText(role_label(device.role))
        self._dev_type.setText(type_txt or "—")
        self._dev_serial.setText(device.serial or "—")
        self._dev_tag.setText(device.inventory_tag or "—")
        host = inv.host_for_device(snap, device)
        self._dev_host.setText(host.hostname if host is not None else "—")
        vms = inv.vms_for_host(snap, device.id)
        if vms:
            self._dev_vms.setText("\n".join(vm.hostname or str(vm.id) for vm in vms))
        else:
            self._dev_vms.setText("—")
        self._dev_location.setText(inv.device_location_label(snap, device.id))
        self._dev_ports.setText(summary)
        lags = inv.lags_for_device(snap, device.id)
        if lags:
            self._dev_lags.setText(
                "\n".join(
                    f"{lag.name} ({lag_mode_label(lag.mode)}) · "
                    f"{inv.lag_member_labels(snap, lag)}"
                    for lag in lags
                )
            )
        else:
            self._dev_lags.setText("—")

    def _set_nav_visible(self, visible: bool) -> None:
        self._btn_topo.setVisible(visible)
        self._btn_plan.setVisible(visible)
        self._btn_topo.setEnabled(visible)
        self._btn_plan.setEnabled(visible)

    def _emit_edit(self) -> None:
        if self._kind == ContextKind.PROJECT:
            self.edit_project_requested.emit()
        elif self._kind == ContextKind.BUILDING and self._building_id is not None:
            self.edit_building_requested.emit(self._building_id)
        elif self._kind == ContextKind.DEVICE and self._device_id is not None:
            self.edit_device_requested.emit(self._device_id)

    def _emit_topo(self) -> None:
        if self._device_id is not None:
            self.show_on_topology_requested.emit(self._device_id)

    def _emit_plan(self) -> None:
        if self._device_id is not None:
            self.show_on_floor_plan_requested.emit(self._device_id)


# Обратная совместимость со старым именем
DeviceCard = ContextCard
