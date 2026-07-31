from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from landesigner.domain.entities import (
    Cable,
    Device,
    DeviceType,
    IpAddress,
    Port,
    ProjectSnapshot,
    Vlan,
)
from landesigner.services import inventory as inventory_service
from landesigner.ui.labels import (
    cable_category_label,
    cable_kind_label,
    media_label,
    role_label,
    status_label,
)


class InventoryView(QWidget):
    add_device_type_requested = Signal()
    edit_device_type_requested = Signal(object)  # UUID
    add_device_requested = Signal()
    edit_device_requested = Signal(object)  # UUID
    delete_device_requested = Signal(object)  # UUID
    add_cable_requested = Signal()
    edit_cable_requested = Signal(object)  # UUID
    delete_cable_requested = Signal(object)  # UUID
    add_vlan_requested = Signal()
    edit_vlan_requested = Signal(object)  # UUID
    delete_vlan_requested = Signal(object)  # UUID
    add_ip_requested = Signal()
    edit_ip_requested = Signal(object)  # UUID
    delete_ip_requested = Signal(object)  # UUID
    edit_port_network_requested = Signal(object)  # UUID

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)

        btn_row = QHBoxLayout()
        self._btn_type = QPushButton("Тип устройства…", self)
        self._btn_edit_type = QPushButton("Изменить тип…", self)
        self._btn_add = QPushButton("Добавить устройство…", self)
        self._btn_add.setObjectName("PrimaryButton")
        self._btn_edit = QPushButton("Изменить…", self)
        self._btn_delete = QPushButton("Удалить", self)
        self._btn_type.clicked.connect(self.add_device_type_requested.emit)
        self._btn_edit_type.clicked.connect(self._on_edit_type)
        self._btn_add.clicked.connect(self.add_device_requested.emit)
        self._btn_edit.clicked.connect(self._on_edit)
        self._btn_delete.clicked.connect(self._on_delete)
        btn_row.addWidget(self._btn_type)
        btn_row.addWidget(self._btn_edit_type)
        btn_row.addWidget(self._btn_add)
        btn_row.addWidget(self._btn_edit)
        btn_row.addWidget(self._btn_delete)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        outer = QSplitter(Qt.Orientation.Vertical, self)
        layout.addWidget(outer, stretch=1)

        types_panel = QWidget(outer)
        types_layout = QVBoxLayout(types_panel)
        types_layout.setContentsMargins(0, 0, 0, 0)
        types_title = QLabel("Типы устройств", types_panel)
        types_title.setObjectName("SectionTitle")
        types_layout.addWidget(types_title)
        self._types_table = QTableWidget(types_panel)
        self._types_table.setAlternatingRowColors(True)
        self._types_table.setColumnCount(5)
        self._types_table.setHorizontalHeaderLabels(
            ["Производитель", "Модель", "Роль", "Портов", "Скорости"]
        )
        self._types_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._types_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._types_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._types_table.horizontalHeader().setStretchLastSection(True)
        self._types_table.itemDoubleClicked.connect(self._on_edit_type)
        types_layout.addWidget(self._types_table)
        outer.addWidget(types_panel)

        mid = QSplitter(outer)
        left = QWidget(mid)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        devices_title = QLabel("Устройства", left)
        devices_title.setObjectName("SectionTitle")
        left_layout.addWidget(devices_title)
        self._table = QTableWidget(left)
        self._table.setAlternatingRowColors(True)
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            ["Имя хоста", "Серийный №", "Инв. №", "Роль", "Тип"]
        )
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.itemDoubleClicked.connect(self._on_edit)
        left_layout.addWidget(self._table)
        mid.addWidget(left)

        right = QWidget(mid)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        port_header = QHBoxLayout()
        ports_title = QLabel("Порты выбранного устройства", right)
        ports_title.setObjectName("SectionTitle")
        port_header.addWidget(ports_title)
        port_header.addStretch(1)
        self._btn_port_net = QPushButton("Сеть…", right)
        self._btn_port_net.clicked.connect(self._on_edit_port_network)
        port_header.addWidget(self._btn_port_net)
        right_layout.addLayout(port_header)
        self._ports = QTableWidget(right)
        self._ports.setAlternatingRowColors(True)
        self._ports.setColumnCount(7)
        self._ports.setHorizontalHeaderLabels(
            ["Имя", "Скорость", "Среда", "Статус", "Связь", "VLAN", "IP"]
        )
        self._ports.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._ports.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._ports.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._ports.horizontalHeader().setStretchLastSection(True)
        self._ports.itemDoubleClicked.connect(self._on_edit_port_network)
        right_layout.addWidget(self._ports)
        mid.addWidget(right)
        mid.setSizes([700, 400])
        outer.addWidget(mid)

        bottom = QTabWidget(outer)
        bottom.addTab(self._build_cables_tab(bottom), "Кабели")
        bottom.addTab(self._build_vlans_tab(bottom), "VLAN")
        bottom.addTab(self._build_ips_tab(bottom), "IP")
        outer.addWidget(bottom)
        outer.setSizes([120, 340, 220])

        self._snapshot: ProjectSnapshot | None = None
        self._devices: list[Device] = []
        self._types_by_id: dict[UUID, DeviceType] = {}
        self._ports_by_device: dict[UUID, list[Port]] = {}
        self._cables: list[Cable] = []
        self._vlans: list[Vlan] = []
        self._ips: list[IpAddress] = []

    def _build_cables_tab(self, parent: QWidget) -> QWidget:
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        header.addStretch(1)
        self._btn_add_cable = QPushButton("Соединить…", panel)
        self._btn_add_cable.setObjectName("PrimaryButton")
        self._btn_edit_cable = QPushButton("Изменить…", panel)
        self._btn_delete_cable = QPushButton("Разорвать", panel)
        self._btn_add_cable.clicked.connect(self.add_cable_requested.emit)
        self._btn_edit_cable.clicked.connect(self._on_edit_cable)
        self._btn_delete_cable.clicked.connect(self._on_delete_cable)
        header.addWidget(self._btn_add_cable)
        header.addWidget(self._btn_edit_cable)
        header.addWidget(self._btn_delete_cable)
        layout.addLayout(header)
        self._cables_table = QTableWidget(panel)
        self._cables_table.setAlternatingRowColors(True)
        self._cables_table.setColumnCount(6)
        self._cables_table.setHorizontalHeaderLabels(
            ["Метка", "Вид", "Категория", "Длина", "Конец A", "Конец B"]
        )
        self._cables_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._cables_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._cables_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._cables_table.horizontalHeader().setStretchLastSection(True)
        self._cables_table.itemDoubleClicked.connect(self._on_edit_cable)
        layout.addWidget(self._cables_table)
        return panel

    def _build_vlans_tab(self, parent: QWidget) -> QWidget:
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        header.addStretch(1)
        self._btn_add_vlan = QPushButton("Добавить…", panel)
        self._btn_edit_vlan = QPushButton("Изменить…", panel)
        self._btn_delete_vlan = QPushButton("Удалить", panel)
        self._btn_add_vlan.clicked.connect(self.add_vlan_requested.emit)
        self._btn_edit_vlan.clicked.connect(self._on_edit_vlan)
        self._btn_delete_vlan.clicked.connect(self._on_delete_vlan)
        header.addWidget(self._btn_add_vlan)
        header.addWidget(self._btn_edit_vlan)
        header.addWidget(self._btn_delete_vlan)
        layout.addLayout(header)
        self._vlans_table = QTableWidget(panel)
        self._vlans_table.setAlternatingRowColors(True)
        self._vlans_table.setColumnCount(2)
        self._vlans_table.setHorizontalHeaderLabels(["VLAN ID", "Имя"])
        self._vlans_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._vlans_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._vlans_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._vlans_table.horizontalHeader().setStretchLastSection(True)
        self._vlans_table.itemDoubleClicked.connect(self._on_edit_vlan)
        layout.addWidget(self._vlans_table)
        return panel

    def _build_ips_tab(self, parent: QWidget) -> QWidget:
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        header.addStretch(1)
        self._btn_add_ip = QPushButton("Добавить…", panel)
        self._btn_edit_ip = QPushButton("Изменить…", panel)
        self._btn_delete_ip = QPushButton("Удалить", panel)
        self._btn_add_ip.clicked.connect(self.add_ip_requested.emit)
        self._btn_edit_ip.clicked.connect(self._on_edit_ip)
        self._btn_delete_ip.clicked.connect(self._on_delete_ip)
        header.addWidget(self._btn_add_ip)
        header.addWidget(self._btn_edit_ip)
        header.addWidget(self._btn_delete_ip)
        layout.addLayout(header)
        self._ips_table = QTableWidget(panel)
        self._ips_table.setAlternatingRowColors(True)
        self._ips_table.setColumnCount(4)
        self._ips_table.setHorizontalHeaderLabels(["Адрес", "Префикс", "Шлюз", "Порт"])
        self._ips_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._ips_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._ips_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._ips_table.horizontalHeader().setStretchLastSection(True)
        self._ips_table.itemDoubleClicked.connect(self._on_edit_ip)
        layout.addWidget(self._ips_table)
        return panel

    def set_snapshot(self, snapshot: ProjectSnapshot | None) -> None:
        selected_device = self.selected_device_id()
        selected_cable = self.selected_cable_id()
        selected_vlan = self.selected_vlan_id()
        selected_ip = self.selected_ip_id()
        self._snapshot = snapshot
        if snapshot is None:
            self._devices = []
            self._types_by_id = {}
            self._ports_by_device = {}
            self._cables = []
            self._vlans = []
            self._ips = []
            self._types_table.setRowCount(0)
            self._table.setRowCount(0)
            self._ports.setRowCount(0)
            self._cables_table.setRowCount(0)
            self._vlans_table.setRowCount(0)
            self._ips_table.setRowCount(0)
            return

        types = list(snapshot.device_types)
        self._types_table.setRowCount(len(types))
        for row_idx, dt in enumerate(types):
            speeds = sorted({int(p.get("speed", 0)) for p in dt.port_template})
            speed_txt = "/".join(str(s) for s in speeds if s) or "—"
            self._types_table.setItem(row_idx, 0, QTableWidgetItem(dt.vendor))
            self._types_table.setItem(row_idx, 1, QTableWidgetItem(dt.model))
            self._types_table.setItem(row_idx, 2, QTableWidgetItem(role_label(dt.role)))
            self._types_table.setItem(
                row_idx, 3, QTableWidgetItem(str(len(dt.port_template)))
            )
            self._types_table.setItem(row_idx, 4, QTableWidgetItem(f"{speed_txt} Мбит/с"))
            self._types_table.item(row_idx, 0).setData(Qt.ItemDataRole.UserRole, str(dt.id))

        self._devices = list(snapshot.devices)
        self._types_by_id = {dt.id: dt for dt in types}
        self._ports_by_device = {}
        for device in self._devices:
            self._ports_by_device[device.id] = inventory_service.ports_for_device(
                snapshot, device.id
            )

        self._table.setRowCount(len(self._devices))
        restore_row = None
        for row_idx, d in enumerate(self._devices):
            dt = self._types_by_id.get(d.device_type_id)
            type_label = f"{dt.vendor} {dt.model}" if dt else str(d.device_type_id)
            self._table.setItem(row_idx, 0, QTableWidgetItem(d.hostname))
            self._table.setItem(row_idx, 1, QTableWidgetItem(d.serial))
            self._table.setItem(row_idx, 2, QTableWidgetItem(d.inventory_tag))
            self._table.setItem(row_idx, 3, QTableWidgetItem(role_label(d.role)))
            self._table.setItem(row_idx, 4, QTableWidgetItem(type_label))
            self._table.item(row_idx, 0).setData(Qt.ItemDataRole.UserRole, str(d.id))
            if selected_device is not None and d.id == selected_device:
                restore_row = row_idx

        self._cables = list(snapshot.cables)
        self._cables_table.setRowCount(len(self._cables))
        restore_cable_row = None
        for row_idx, cable in enumerate(self._cables):
            length = f"{cable.length_m:g} м" if cable.length_m is not None else "—"
            self._cables_table.setItem(row_idx, 0, QTableWidgetItem(cable.label or "—"))
            self._cables_table.setItem(row_idx, 1, QTableWidgetItem(cable_kind_label(cable.kind)))
            self._cables_table.setItem(
                row_idx, 2, QTableWidgetItem(cable_category_label(cable.category))
            )
            self._cables_table.setItem(row_idx, 3, QTableWidgetItem(length))
            self._cables_table.setItem(
                row_idx,
                4,
                QTableWidgetItem(inventory_service.port_endpoint_label(snapshot, cable.end_a_port_id)),
            )
            self._cables_table.setItem(
                row_idx,
                5,
                QTableWidgetItem(inventory_service.port_endpoint_label(snapshot, cable.end_b_port_id)),
            )
            self._cables_table.item(row_idx, 0).setData(Qt.ItemDataRole.UserRole, str(cable.id))
            if selected_cable is not None and cable.id == selected_cable:
                restore_cable_row = row_idx

        self._vlans = sorted(snapshot.vlans, key=lambda v: v.vlan_id)
        self._vlans_table.setRowCount(len(self._vlans))
        restore_vlan_row = None
        for row_idx, vlan in enumerate(self._vlans):
            self._vlans_table.setItem(row_idx, 0, QTableWidgetItem(str(vlan.vlan_id)))
            self._vlans_table.setItem(row_idx, 1, QTableWidgetItem(vlan.name))
            self._vlans_table.item(row_idx, 0).setData(Qt.ItemDataRole.UserRole, str(vlan.id))
            if selected_vlan is not None and vlan.id == selected_vlan:
                restore_vlan_row = row_idx

        self._ips = list(snapshot.ips)
        self._ips_table.setRowCount(len(self._ips))
        restore_ip_row = None
        for row_idx, ip in enumerate(self._ips):
            port_txt = (
                inventory_service.port_endpoint_label(snapshot, ip.port_id)
                if ip.port_id is not None
                else "—"
            )
            self._ips_table.setItem(row_idx, 0, QTableWidgetItem(ip.address))
            self._ips_table.setItem(row_idx, 1, QTableWidgetItem(ip.cidr or "—"))
            self._ips_table.setItem(row_idx, 2, QTableWidgetItem(ip.gateway or "—"))
            self._ips_table.setItem(row_idx, 3, QTableWidgetItem(port_txt))
            self._ips_table.item(row_idx, 0).setData(Qt.ItemDataRole.UserRole, str(ip.id))
            if selected_ip is not None and ip.id == selected_ip:
                restore_ip_row = row_idx

        if restore_row is not None:
            self._table.selectRow(restore_row)
        else:
            self._ports.setRowCount(0)

        if restore_cable_row is not None:
            self._cables_table.selectRow(restore_cable_row)
        if restore_vlan_row is not None:
            self._vlans_table.selectRow(restore_vlan_row)
        if restore_ip_row is not None:
            self._ips_table.selectRow(restore_ip_row)

    def selected_device_id(self) -> UUID | None:
        return self._selected_id(self._table)

    def selected_device_type_id(self) -> UUID | None:
        return self._selected_id(self._types_table)

    def selected_cable_id(self) -> UUID | None:
        return self._selected_id(self._cables_table)

    def selected_vlan_id(self) -> UUID | None:
        return self._selected_id(self._vlans_table)

    def selected_ip_id(self) -> UUID | None:
        return self._selected_id(self._ips_table)

    def selected_port_id(self) -> UUID | None:
        return self._selected_id(self._ports)

    def _selected_id(self, table: QTableWidget) -> UUID | None:
        rows = table.selectionModel().selectedRows()
        if not rows:
            return None
        item = table.item(rows[0].row(), 0)
        if item is None:
            return None
        raw = item.data(Qt.ItemDataRole.UserRole)
        return UUID(raw) if raw else None

    def _on_selection_changed(self) -> None:
        device_id = self.selected_device_id()
        ports = self._ports_by_device.get(device_id, []) if device_id else []
        snapshot = self._snapshot
        self._ports.setRowCount(len(ports))
        for row_idx, p in enumerate(ports):
            peer = inventory_service.peer_port(snapshot, p.id) if snapshot else None
            if peer is not None and snapshot is not None:
                link = inventory_service.port_endpoint_label(snapshot, peer.id)
            else:
                link = "—"
            vlan_txt = (
                inventory_service.port_vlan_summary(snapshot, p) if snapshot else "—"
            )
            ips = inventory_service.ips_for_port(snapshot, p.id) if snapshot else []
            ip_txt = ", ".join(inventory_service.ip_label(ip) for ip in ips) if ips else "—"
            self._ports.setItem(row_idx, 0, QTableWidgetItem(p.name))
            self._ports.setItem(row_idx, 1, QTableWidgetItem(f"{p.speed} Мбит/с"))
            self._ports.setItem(row_idx, 2, QTableWidgetItem(media_label(p.media)))
            self._ports.setItem(row_idx, 3, QTableWidgetItem(status_label(p.status)))
            self._ports.setItem(row_idx, 4, QTableWidgetItem(link))
            self._ports.setItem(row_idx, 5, QTableWidgetItem(vlan_txt))
            self._ports.setItem(row_idx, 6, QTableWidgetItem(ip_txt))
            self._ports.item(row_idx, 0).setData(Qt.ItemDataRole.UserRole, str(p.id))

    def _on_edit(self) -> None:
        device_id = self.selected_device_id()
        if device_id is not None:
            self.edit_device_requested.emit(device_id)

    def _on_edit_type(self) -> None:
        type_id = self.selected_device_type_id()
        if type_id is not None:
            self.edit_device_type_requested.emit(type_id)

    def _on_delete(self) -> None:
        device_id = self.selected_device_id()
        if device_id is not None:
            self.delete_device_requested.emit(device_id)

    def _on_edit_cable(self) -> None:
        cable_id = self.selected_cable_id()
        if cable_id is not None:
            self.edit_cable_requested.emit(cable_id)

    def _on_delete_cable(self) -> None:
        cable_id = self.selected_cable_id()
        if cable_id is not None:
            self.delete_cable_requested.emit(cable_id)

    def _on_edit_vlan(self) -> None:
        vlan_id = self.selected_vlan_id()
        if vlan_id is not None:
            self.edit_vlan_requested.emit(vlan_id)

    def _on_delete_vlan(self) -> None:
        vlan_id = self.selected_vlan_id()
        if vlan_id is not None:
            self.delete_vlan_requested.emit(vlan_id)

    def _on_edit_ip(self) -> None:
        ip_id = self.selected_ip_id()
        if ip_id is not None:
            self.edit_ip_requested.emit(ip_id)

    def _on_delete_ip(self) -> None:
        ip_id = self.selected_ip_id()
        if ip_id is not None:
            self.delete_ip_requested.emit(ip_id)

    def _on_edit_port_network(self) -> None:
        port_id = self.selected_port_id()
        if port_id is not None:
            self.edit_port_network_requested.emit(port_id)
