from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSplitter,
    QTabWidget,
    QTableWidget,
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
    Vrf,
)
from landesigner.domain.enums import PortStatus, PortMedia, DeviceRole
from landesigner.services import inventory as inventory_service
from landesigner.services import search as search_service
from landesigner.ui.icons import icon_action_button
from landesigner.ui.labels import (
    cable_category_label,
    cable_kind_label,
    lag_mode_label,
    media_label,
    role_label,
    status_label,
)
from landesigner.ui.table_utils import (
    ip_sort_key,
    mac_sort_key,
    make_ip_item,
    make_item,
    select_row_by_id,
    table_update,
    tune_table,
)
from landesigner.ui.widgets.panel_card import PanelCard

_ACCENT = QColor("#2f7c85")
_STATUS_COLOR = {
    PortStatus.FREE: QColor("#667784"),
    PortStatus.OCCUPIED: QColor("#2f9e6f"),
    PortStatus.RESERVED: QColor("#c9842f"),
    PortStatus.DISABLED: QColor("#94a2ad"),
}
_STATUS_DOT = {
    PortStatus.FREE: "○",
    PortStatus.OCCUPIED: "●",
    PortStatus.RESERVED: "●",
    PortStatus.DISABLED: "●",
}


class InventoryView(QWidget):
    add_device_requested = Signal()
    edit_device_requested = Signal(object)  # UUID
    delete_device_requested = Signal(object)  # UUID
    add_cable_requested = Signal()
    edit_cable_requested = Signal(object)  # UUID
    delete_cable_requested = Signal(object)  # UUID
    add_vlan_requested = Signal()
    edit_vlan_requested = Signal(object)  # UUID
    delete_vlan_requested = Signal(object)  # UUID
    add_vrf_requested = Signal()
    edit_vrf_requested = Signal(object)  # UUID
    delete_vrf_requested = Signal(object)  # UUID
    add_ip_requested = Signal()
    edit_ip_requested = Signal(object)  # UUID
    delete_ip_requested = Signal(object)  # UUID
    add_lag_requested = Signal()
    edit_lag_requested = Signal(object)  # UUID
    delete_lag_requested = Signal(object)  # UUID
    add_vswitch_requested = Signal()
    edit_vswitch_requested = Signal(object)  # UUID
    delete_vswitch_requested = Signal(object)  # UUID
    add_port_group_requested = Signal()
    edit_port_group_requested = Signal(object)  # UUID
    delete_port_group_requested = Signal(object)  # UUID
    edit_port_network_requested = Signal(object)  # UUID
    edit_port_properties_requested = Signal(object)  # UUID
    edit_vnic_host_requested = Signal(object)  # UUID
    patch_matrix_requested = Signal(object)  # UUID device
    add_port_requested = Signal()
    delete_port_requested = Signal(object)  # UUID
    device_selection_changed = Signal(object)  # UUID | None

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self._search = QLineEdit(self)
        self._search.setPlaceholderText("Поиск по инвентарю…  (Ctrl+K)")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._on_search_changed)
        self._location_hint = QLabel("", self)
        self._location_hint.setProperty("muted", True)
        self._location_hint.setObjectName("PanelSubtitle")
        self._btn_clear_location = icon_action_button(
            "clear", "Сбросить фильтр локации", self
        )
        self._btn_clear_location.setVisible(False)
        self._btn_clear_location.clicked.connect(self.clear_location_filter)
        self._search_hint = QLabel("", self)
        self._search_hint.setProperty("muted", True)
        self._search_hint.setObjectName("PanelSubtitle")
        search_row.addWidget(self._search, stretch=1)
        search_row.addWidget(self._location_hint)
        search_row.addWidget(self._btn_clear_location)
        search_row.addWidget(self._search_hint)
        layout.addLayout(search_row)

        QShortcut(QKeySequence("Ctrl+K"), self, activated=self.focus_search)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self._search, activated=self._clear_search)

        root = QSplitter(Qt.Orientation.Vertical, self)
        root.setChildrenCollapsible(False)
        layout.addWidget(root, stretch=1)

        # Верх: Устройства | Порты (порты шире — карточка ушла вниз)
        top = QSplitter(Qt.Orientation.Horizontal, root)
        top.setChildrenCollapsible(False)

        devices_card = PanelCard("Устройства", top)
        self._btn_add = icon_action_button(
            "add", "Добавить устройство", devices_card, role="primary"
        )
        self._btn_edit = icon_action_button("edit", "Изменить устройство", devices_card)
        self._btn_delete = icon_action_button(
            "delete", "Удалить устройство", devices_card, role="danger"
        )
        self._btn_add.clicked.connect(self.add_device_requested.emit)
        self._btn_edit.clicked.connect(self._on_edit)
        self._btn_delete.clicked.connect(self._on_delete)
        devices_card.add_action(self._btn_add)
        devices_card.add_action(self._btn_edit)
        devices_card.add_action(self._btn_delete)
        self._table = QTableWidget(devices_card)
        tune_table(self._table)
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(
            ["Имя хоста", "Серийный №", "Инв. №", "Роль", "Тип", "Хост"]
        )
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.itemDoubleClicked.connect(self._on_edit)
        devices_card.set_body_widget(self._table)
        top.addWidget(devices_card)

        self._ports_card = PanelCard("Порты", top, subtitle="Выберите устройство")
        self._btn_add_port = icon_action_button(
            "add", "Добавить порт", self._ports_card, role="primary"
        )
        self._btn_add_port.clicked.connect(self.add_port_requested.emit)
        self._btn_port_props = icon_action_button(
            "port", "Свойства порта", self._ports_card
        )
        self._btn_port_props.clicked.connect(self._on_edit_port_properties)
        self._btn_port_net = icon_action_button(
            "network", "Сеть порта (VLAN / IP)", self._ports_card
        )
        self._btn_port_net.clicked.connect(self._on_edit_port_network)
        self._btn_vnic_host = icon_action_button(
            "vnic", "Port Group / NIC хоста для vNIC", self._ports_card
        )
        self._btn_vnic_host.clicked.connect(self._on_edit_vnic_host)
        self._btn_patch_matrix = icon_action_button(
            "port", "Матрица пар Front↔Rear", self._ports_card
        )
        self._btn_patch_matrix.clicked.connect(self._on_patch_matrix)
        self._btn_delete_port = icon_action_button(
            "delete", "Удалить порт", self._ports_card, role="danger"
        )
        self._btn_delete_port.clicked.connect(self._on_delete_port)
        self._ports_card.add_action(self._btn_add_port)
        self._ports_card.add_action(self._btn_port_props)
        self._ports_card.add_action(self._btn_port_net)
        self._ports_card.add_action(self._btn_vnic_host)
        self._ports_card.add_action(self._btn_patch_matrix)
        self._ports_card.add_action(self._btn_delete_port)
        self._ports = QTableWidget(self._ports_card)
        tune_table(self._ports)
        self._ports.setColumnCount(10)
        self._ports.setHorizontalHeaderLabels(
            ["Имя", "Пара", "MAC", "Скорость", "Среда", "Статус", "Связь", "vNIC→", "VLAN", "IP"]
        )
        self._ports.itemDoubleClicked.connect(self._on_edit_port_network)
        self._ports_card.set_body_widget(self._ports)
        top.addWidget(self._ports_card)
        top.setSizes([420, 780])
        top.setStretchFactor(0, 0)
        top.setStretchFactor(1, 1)
        root.addWidget(top)

        # Низ: Связи и адреса | карточка устройства
        bottom = QSplitter(Qt.Orientation.Horizontal, root)
        bottom.setChildrenCollapsible(False)

        bottom_card = PanelCard("Связи и адреса", bottom)
        bottom_tabs = QTabWidget(bottom_card)
        bottom_tabs.setDocumentMode(True)
        bottom_tabs.addTab(self._build_cables_tab(bottom_tabs), "Кабели")
        bottom_tabs.addTab(self._build_vlans_tab(bottom_tabs), "VLAN")
        bottom_tabs.addTab(self._build_vrfs_tab(bottom_tabs), "VRF")
        bottom_tabs.addTab(self._build_ips_tab(bottom_tabs), "IP")
        bottom_tabs.addTab(self._build_lags_tab(bottom_tabs), "LAG")
        bottom_tabs.addTab(self._build_vswitch_tab(bottom_tabs), "vSwitch")
        bottom_card.set_body_widget(bottom_tabs)
        bottom.addWidget(bottom_card)

        self._card_host = QWidget(bottom)
        self._card_host_layout = QVBoxLayout(self._card_host)
        self._card_host_layout.setContentsMargins(0, 0, 0, 0)
        self._card_host_layout.setSpacing(0)
        self._card_host.setMinimumWidth(280)
        self._card_host.setMaximumWidth(400)
        bottom.addWidget(self._card_host)
        bottom.setSizes([780, 320])
        bottom.setStretchFactor(0, 1)
        bottom.setStretchFactor(1, 0)
        bottom.setMinimumHeight(220)
        root.addWidget(bottom)
        root.setSizes([480, 280])
        root.setStretchFactor(0, 1)
        root.setStretchFactor(1, 0)

        self._attached_card: QWidget | None = None
        self._snapshot: ProjectSnapshot | None = None
        self._devices: list[Device] = []
        self._types_by_id: dict[UUID, DeviceType] = {}
        self._ports_by_device: dict[UUID, list[Port]] = {}
        self._cables: list[Cable] = []
        self._vlans: list[Vlan] = []
        self._vrfs: list[Vrf] = []
        self._ips: list[IpAddress] = []
        self._lags = []
        self._vswitches = []
        self._port_groups = []
        self._query = ""
        self._location_kind: str | None = None
        self._location_id: UUID | None = None

    def attach_device_card(self, card: QWidget) -> None:
        """Поместить карточку устройства в нижний правый слот."""
        if self._attached_card is card and card.parent() is self._card_host:
            card.show()
            return
        self.detach_device_card()
        self._card_host_layout.addWidget(card)
        self._attached_card = card
        card.show()

    def detach_device_card(self) -> None:
        if self._attached_card is None:
            return
        self._card_host_layout.removeWidget(self._attached_card)
        self._attached_card.setParent(None)
        self._attached_card = None

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
        self._refresh_tables(preserve_selection=True)

    def set_location_filter(self, kind: str | None, location_id: UUID | None) -> None:
        self._location_kind = kind
        self._location_id = location_id
        self._update_location_hint()
        self._refresh_tables(preserve_selection=True)

    def clear_location_filter(self) -> None:
        self.set_location_filter(None, None)

    def _update_location_hint(self) -> None:
        snapshot = self._snapshot
        if (
            not self._location_kind
            or self._location_id is None
            or snapshot is None
        ):
            self._location_hint.setText("")
            self._btn_clear_location.setVisible(False)
            return
        kind = self._location_kind
        lid = self._location_id
        label = "локация"
        if kind == "building":
            b = next((x for x in snapshot.buildings if x.id == lid), None)
            label = f"здание «{b.name}»" if b else "здание"
        elif kind == "floor":
            f = next((x for x in snapshot.floors if x.id == lid), None)
            label = f"этаж «{f.name}»" if f else "этаж"
        elif kind == "room":
            r = next((x for x in snapshot.rooms if x.id == lid), None)
            label = f"комната «{r.name}»" if r else "комната"
        elif kind == "rack":
            rk = next((x for x in snapshot.racks if x.id == lid), None)
            label = f"шкаф «{rk.name}»" if rk else "шкаф"
        self._location_hint.setText(f"фильтр: {label}")
        self._btn_clear_location.setVisible(True)

    def _build_cables_tab(self, parent: QWidget) -> QWidget:
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        header = QHBoxLayout()
        header.setSpacing(4)
        header.addStretch(1)
        self._btn_add_cable = icon_action_button(
            "cable", "Соединить порты кабелем", panel, role="primary"
        )
        self._btn_edit_cable = icon_action_button("edit", "Изменить кабель", panel)
        self._btn_delete_cable = icon_action_button(
            "delete", "Разорвать кабель", panel, role="danger"
        )
        self._btn_add_cable.clicked.connect(self.add_cable_requested.emit)
        self._btn_edit_cable.clicked.connect(self._on_edit_cable)
        self._btn_delete_cable.clicked.connect(self._on_delete_cable)
        header.addWidget(self._btn_add_cable)
        header.addWidget(self._btn_edit_cable)
        header.addWidget(self._btn_delete_cable)
        layout.addLayout(header)
        self._cables_table = QTableWidget(panel)
        tune_table(self._cables_table)
        self._cables_table.setColumnCount(8)
        self._cables_table.setHorizontalHeaderLabels(
            ["Метка", "Вид", "Категория", "Цвет", "Назначение", "Длина", "Конец A", "Конец B"]
        )
        self._cables_table.itemDoubleClicked.connect(self._on_edit_cable)
        layout.addWidget(self._cables_table)
        return panel

    def _build_vlans_tab(self, parent: QWidget) -> QWidget:
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        header = QHBoxLayout()
        header.setSpacing(4)
        header.addStretch(1)
        self._btn_add_vlan = icon_action_button(
            "add", "Добавить VLAN", panel, role="primary"
        )
        self._btn_edit_vlan = icon_action_button("edit", "Изменить VLAN", panel)
        self._btn_delete_vlan = icon_action_button(
            "delete", "Удалить VLAN", panel, role="danger"
        )
        self._btn_add_vlan.clicked.connect(self.add_vlan_requested.emit)
        self._btn_edit_vlan.clicked.connect(self._on_edit_vlan)
        self._btn_delete_vlan.clicked.connect(self._on_delete_vlan)
        header.addWidget(self._btn_add_vlan)
        header.addWidget(self._btn_edit_vlan)
        header.addWidget(self._btn_delete_vlan)
        layout.addLayout(header)
        self._vlans_table = QTableWidget(panel)
        tune_table(self._vlans_table)
        self._vlans_table.setColumnCount(3)
        self._vlans_table.setHorizontalHeaderLabels(["VLAN ID", "Имя", "Описание"])
        self._vlans_table.itemDoubleClicked.connect(self._on_edit_vlan)
        layout.addWidget(self._vlans_table)
        return panel

    def _build_vrfs_tab(self, parent: QWidget) -> QWidget:
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        header = QHBoxLayout()
        header.setSpacing(4)
        header.addStretch(1)
        self._btn_add_vrf = icon_action_button(
            "add", "Добавить VRF", panel, role="primary"
        )
        self._btn_edit_vrf = icon_action_button("edit", "Изменить VRF", panel)
        self._btn_delete_vrf = icon_action_button(
            "delete", "Удалить VRF", panel, role="danger"
        )
        self._btn_add_vrf.clicked.connect(self.add_vrf_requested.emit)
        self._btn_edit_vrf.clicked.connect(self._on_edit_vrf)
        self._btn_delete_vrf.clicked.connect(self._on_delete_vrf)
        header.addWidget(self._btn_add_vrf)
        header.addWidget(self._btn_edit_vrf)
        header.addWidget(self._btn_delete_vrf)
        layout.addLayout(header)
        self._vrfs_table = QTableWidget(panel)
        tune_table(self._vrfs_table)
        self._vrfs_table.setColumnCount(4)
        self._vrfs_table.setHorizontalHeaderLabels(["Имя", "RD", "Описание", "IP"])
        self._vrfs_table.itemDoubleClicked.connect(self._on_edit_vrf)
        layout.addWidget(self._vrfs_table)
        return panel

    def _build_ips_tab(self, parent: QWidget) -> QWidget:
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        header = QHBoxLayout()
        header.setSpacing(4)
        header.addStretch(1)
        self._btn_add_ip = icon_action_button(
            "add", "Добавить IP", panel, role="primary"
        )
        self._btn_edit_ip = icon_action_button("edit", "Изменить IP", panel)
        self._btn_delete_ip = icon_action_button(
            "delete", "Удалить IP", panel, role="danger"
        )
        self._btn_add_ip.clicked.connect(self.add_ip_requested.emit)
        self._btn_edit_ip.clicked.connect(self._on_edit_ip)
        self._btn_delete_ip.clicked.connect(self._on_delete_ip)
        header.addWidget(self._btn_add_ip)
        header.addWidget(self._btn_edit_ip)
        header.addWidget(self._btn_delete_ip)
        layout.addLayout(header)
        self._ips_table = QTableWidget(panel)
        tune_table(self._ips_table)
        self._ips_table.setColumnCount(5)
        self._ips_table.setHorizontalHeaderLabels(
            ["Адрес", "Префикс", "Шлюз", "VRF", "Привязка"]
        )
        self._ips_table.itemDoubleClicked.connect(self._on_edit_ip)
        layout.addWidget(self._ips_table)
        return panel

    def _build_lags_tab(self, parent: QWidget) -> QWidget:
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        header = QHBoxLayout()
        header.setSpacing(4)
        header.addStretch(1)
        self._btn_add_lag = icon_action_button(
            "add", "Добавить LAG", panel, role="primary"
        )
        self._btn_edit_lag = icon_action_button("edit", "Изменить LAG", panel)
        self._btn_delete_lag = icon_action_button(
            "delete", "Удалить LAG", panel, role="danger"
        )
        self._btn_add_lag.clicked.connect(self.add_lag_requested.emit)
        self._btn_edit_lag.clicked.connect(self._on_edit_lag)
        self._btn_delete_lag.clicked.connect(self._on_delete_lag)
        header.addWidget(self._btn_add_lag)
        header.addWidget(self._btn_edit_lag)
        header.addWidget(self._btn_delete_lag)
        layout.addLayout(header)
        self._lags_table = QTableWidget(panel)
        tune_table(self._lags_table)
        self._lags_table.setColumnCount(6)
        self._lags_table.setHorizontalHeaderLabels(
            ["Имя", "Устройство", "Режим", "MAC", "Порты", "IP"]
        )
        self._lags_table.itemDoubleClicked.connect(self._on_edit_lag)
        layout.addWidget(self._lags_table)
        return panel

    def _build_vswitch_tab(self, parent: QWidget) -> QWidget:
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        header = QHBoxLayout()
        header.setSpacing(4)
        header.addStretch(1)
        self._btn_add_vswitch = icon_action_button(
            "add", "Добавить vSwitch", panel, role="primary"
        )
        self._btn_edit_vswitch = icon_action_button("edit", "Изменить vSwitch", panel)
        self._btn_delete_vswitch = icon_action_button(
            "delete", "Удалить vSwitch", panel, role="danger"
        )
        self._btn_add_pg = icon_action_button("catalog", "Добавить Port Group", panel)
        self._btn_edit_pg = icon_action_button("network", "Изменить Port Group", panel)
        self._btn_delete_pg = icon_action_button(
            "clear", "Удалить Port Group", panel, role="danger"
        )
        self._btn_add_vswitch.clicked.connect(self.add_vswitch_requested.emit)
        self._btn_edit_vswitch.clicked.connect(self._on_edit_vswitch)
        self._btn_delete_vswitch.clicked.connect(self._on_delete_vswitch)
        self._btn_add_pg.clicked.connect(self.add_port_group_requested.emit)
        self._btn_edit_pg.clicked.connect(self._on_edit_port_group)
        self._btn_delete_pg.clicked.connect(self._on_delete_port_group)
        for btn in (
            self._btn_add_vswitch,
            self._btn_edit_vswitch,
            self._btn_delete_vswitch,
            self._btn_add_pg,
            self._btn_edit_pg,
            self._btn_delete_pg,
        ):
            header.addWidget(btn)
        layout.addLayout(header)
        self._vswitch_table = QTableWidget(panel)
        tune_table(self._vswitch_table)
        self._vswitch_table.setColumnCount(5)
        self._vswitch_table.setHorizontalHeaderLabels(
            ["Хост", "vSwitch", "Port Group", "VLAN", "Uplink"]
        )
        self._vswitch_table.itemDoubleClicked.connect(self._on_edit_port_group)
        layout.addWidget(self._vswitch_table)
        return panel

    def set_snapshot(self, snapshot: ProjectSnapshot | None) -> None:
        self._snapshot = snapshot
        if snapshot is None:
            self._devices = []
            self._types_by_id = {}
            self._ports_by_device = {}
            self._cables = []
            self._vlans = []
            self._vrfs = []
            self._ips = []
            self._lags = []
            self._vswitches = []
            self._port_groups = []
            self._refresh_tables(preserve_selection=False)
            return

        types = list(snapshot.device_types)
        self._types_by_id = {dt.id: dt for dt in types}
        self._devices = list(snapshot.devices)
        self._ports_by_device = {
            device.id: inventory_service.ports_for_device(snapshot, device.id)
            for device in self._devices
        }
        self._cables = list(snapshot.cables)
        self._vlans = sorted(snapshot.vlans, key=lambda v: v.vlan_id)
        self._vrfs = sorted(snapshot.vrfs, key=lambda v: v.name.casefold())
        self._ips = list(snapshot.ips)
        self._lags = list(snapshot.lags)
        self._vswitches = list(snapshot.virtual_switches)
        self._port_groups = list(snapshot.port_groups)
        self._refresh_tables(preserve_selection=True)

    def _refresh_tables(self, *, preserve_selection: bool) -> None:
        selected_device = self.selected_device_id() if preserve_selection else None
        selected_cable = self.selected_cable_id() if preserve_selection else None
        selected_vlan = self.selected_vlan_id() if preserve_selection else None
        selected_vrf = self.selected_vrf_id() if preserve_selection else None
        selected_ip = self.selected_ip_id() if preserve_selection else None
        selected_lag = self.selected_lag_id() if preserve_selection else None
        selected_port = self.selected_port_id() if preserve_selection else None
        snapshot = self._snapshot
        query = self._query

        if snapshot is None:
            with table_update(self._table):
                self._table.setRowCount(0)
            with table_update(self._ports):
                self._ports.setRowCount(0)
            with table_update(self._cables_table):
                self._cables_table.setRowCount(0)
            with table_update(self._vlans_table):
                self._vlans_table.setRowCount(0)
            with table_update(self._vrfs_table):
                self._vrfs_table.setRowCount(0)
            with table_update(self._ips_table):
                self._ips_table.setRowCount(0)
            with table_update(self._lags_table):
                self._lags_table.setRowCount(0)
            with table_update(self._vswitch_table):
                self._vswitch_table.setRowCount(0)
            self._ports_card.set_subtitle("Выберите устройство")
            self._search_hint.setText("")
            return

        scoped_devices = self._devices
        if self._location_kind and self._location_id is not None:
            scoped_devices = inventory_service.devices_for_location(
                snapshot, self._location_kind, self._location_id
            )
        devices = search_service.filter_devices(
            snapshot, scoped_devices, self._types_by_id, query
        )
        cables = search_service.filter_cables(snapshot, self._cables, query)
        vlans = search_service.filter_vlans(self._vlans, query)
        vrfs = search_service.filter_vrfs(self._vrfs, query)
        ips = search_service.filter_ips(snapshot, self._ips, query)

        with table_update(self._table):
            self._table.setRowCount(len(devices))
            accent = QBrush(_ACCENT)
            for row_idx, d in enumerate(devices):
                dt = self._types_by_id.get(d.device_type_id)
                type_label = f"{dt.vendor} {dt.model}" if dt else str(d.device_type_id)
                host_item = make_item(d.hostname, entity_id=d.id)
                host_item.setForeground(accent)
                self._table.setItem(row_idx, 0, host_item)
                self._table.setItem(row_idx, 1, make_item(d.serial))
                self._table.setItem(row_idx, 2, make_item(d.inventory_tag))
                self._table.setItem(row_idx, 3, make_item(role_label(d.role)))
                self._table.setItem(row_idx, 4, make_item(type_label))
                host = inventory_service.host_for_device(snapshot, d)
                host_txt = host.hostname if host is not None else "—"
                self._table.setItem(row_idx, 5, make_item(host_txt))

        with table_update(self._cables_table):
            self._cables_table.setRowCount(len(cables))
            for row_idx, cable in enumerate(cables):
                length = f"{cable.length_m:g} м" if cable.length_m is not None else "—"
                length_key = cable.length_m if cable.length_m is not None else -1.0
                path = inventory_service.cable_path_label(snapshot, cable)
                label_item = make_item(cable.label or "—", entity_id=cable.id)
                label_item.setToolTip(path)
                self._cables_table.setItem(row_idx, 0, label_item)
                self._cables_table.setItem(
                    row_idx, 1, make_item(cable_kind_label(cable.kind))
                )
                self._cables_table.setItem(
                    row_idx, 2, make_item(cable_category_label(cable.category))
                )
                self._cables_table.setItem(
                    row_idx, 3, make_item(cable.color or "—")
                )
                self._cables_table.setItem(
                    row_idx, 4, make_item(cable.purpose or "—")
                )
                self._cables_table.setItem(
                    row_idx, 5, make_item(length, sort_key=length_key)
                )
                self._cables_table.setItem(
                    row_idx,
                    6,
                    make_item(
                        inventory_service.port_endpoint_label(snapshot, cable.end_a_port_id)
                    ),
                )
                self._cables_table.setItem(
                    row_idx,
                    7,
                    make_item(
                        inventory_service.port_endpoint_label(snapshot, cable.end_b_port_id)
                    ),
                )

        with table_update(self._vlans_table):
            self._vlans_table.setRowCount(len(vlans))
            for row_idx, vlan in enumerate(vlans):
                self._vlans_table.setItem(
                    row_idx,
                    0,
                    make_item(str(vlan.vlan_id), sort_key=vlan.vlan_id, entity_id=vlan.id),
                )
                self._vlans_table.setItem(row_idx, 1, make_item(vlan.name))
                self._vlans_table.setItem(row_idx, 2, make_item(vlan.description))

        with table_update(self._vrfs_table):
            self._vrfs_table.setRowCount(len(vrfs))
            for row_idx, vrf in enumerate(vrfs):
                ip_count = sum(1 for ip in snapshot.ips if ip.vrf_id == vrf.id)
                self._vrfs_table.setItem(
                    row_idx, 0, make_item(vrf.name, entity_id=vrf.id)
                )
                self._vrfs_table.setItem(row_idx, 1, make_item(vrf.rd or "—"))
                self._vrfs_table.setItem(row_idx, 2, make_item(vrf.description or "—"))
                self._vrfs_table.setItem(
                    row_idx, 3, make_item(str(ip_count), sort_key=ip_count)
                )

        with table_update(self._ips_table):
            self._ips_table.setRowCount(len(ips))
            for row_idx, ip in enumerate(ips):
                if ip.lag_id is not None:
                    lag = next((item for item in snapshot.lags if item.id == ip.lag_id), None)
                    bind_txt = f"LAG {lag.name}" if lag else "LAG"
                elif ip.port_id is not None:
                    bind_txt = inventory_service.port_endpoint_label(snapshot, ip.port_id)
                else:
                    bind_txt = "—"
                if ip.vrf_id is not None:
                    vrf = next((v for v in snapshot.vrfs if v.id == ip.vrf_id), None)
                    vrf_txt = inventory_service.vrf_label(vrf) if vrf else "—"
                else:
                    vrf_txt = "(глобально)"
                cidr_key = int(ip.cidr) if ip.cidr.isdigit() else -1
                self._ips_table.setItem(
                    row_idx, 0, make_ip_item(ip.address, entity_id=ip.id)
                )
                self._ips_table.setItem(
                    row_idx, 1, make_item(ip.cidr or "—", sort_key=cidr_key)
                )
                self._ips_table.setItem(row_idx, 2, make_ip_item(ip.gateway or "—"))
                self._ips_table.setItem(row_idx, 3, make_item(vrf_txt))
                self._ips_table.setItem(row_idx, 4, make_item(bind_txt))

        lags = list(self._lags)
        if search_service.normalize_query(query):
            q = search_service.normalize_query(query)
            lags = [
                lag
                for lag in lags
                if q in lag.name.casefold()
                or any(
                    q in (d.hostname or "").casefold()
                    for d in snapshot.devices
                    if d.id == lag.device_id
                )
            ]
        with table_update(self._lags_table):
            self._lags_table.setRowCount(len(lags))
            for row_idx, lag in enumerate(lags):
                device = next((d for d in snapshot.devices if d.id == lag.device_id), None)
                host = device.hostname if device else "—"
                ips_txt = ", ".join(
                    inventory_service.ip_label(ip)
                    for ip in inventory_service.ips_for_lag(snapshot, lag.id)
                ) or "—"
                self._lags_table.setItem(
                    row_idx, 0, make_item(lag.name, entity_id=lag.id)
                )
                self._lags_table.setItem(row_idx, 1, make_item(host))
                self._lags_table.setItem(
                    row_idx, 2, make_item(lag_mode_label(lag.mode))
                )
                self._lags_table.setItem(
                    row_idx,
                    3,
                    make_item(lag.mac or "—", sort_key=mac_sort_key(lag.mac)),
                )
                self._lags_table.setItem(
                    row_idx,
                    4,
                    make_item(inventory_service.lag_member_labels(snapshot, lag)),
                )
                self._lags_table.setItem(row_idx, 5, make_item(ips_txt))

        # vSwitch / Port Group rows (одна строка на PG; vSwitch без PG — отдельная строка)
        vs_rows: list[tuple] = []
        for vs in self._vswitches:
            groups = [pg for pg in self._port_groups if pg.vswitch_id == vs.id]
            if not groups:
                vs_rows.append((vs, None))
            else:
                for pg in groups:
                    vs_rows.append((vs, pg))
        if search_service.normalize_query(query):
            q = search_service.normalize_query(query)
            filtered = []
            for vs, pg in vs_rows:
                host = next((d for d in snapshot.devices if d.id == vs.host_device_id), None)
                hay = " ".join(
                    [
                        vs.name,
                        host.hostname if host else "",
                        pg.name if pg else "",
                    ]
                ).casefold()
                if q in hay:
                    filtered.append((vs, pg))
            vs_rows = filtered
        with table_update(self._vswitch_table):
            self._vswitch_table.setRowCount(len(vs_rows))
            for row_idx, (vs, pg) in enumerate(vs_rows):
                host = next((d for d in snapshot.devices if d.id == vs.host_device_id), None)
                host_name = host.hostname if host else "—"
                vlan_txt = "—"
                if pg is not None and pg.vlan_id is not None:
                    vlan = next((v for v in snapshot.vlans if v.id == pg.vlan_id), None)
                    vlan_txt = (
                        f"{vlan.vlan_id}" + (f" — {vlan.name}" if vlan and vlan.name else "")
                        if vlan
                        else "?"
                    )
                item0 = make_item(host_name, entity_id=vs.id)
                item0.setData(Qt.ItemDataRole.UserRole + 1, str(pg.id) if pg else "")
                self._vswitch_table.setItem(row_idx, 0, item0)
                self._vswitch_table.setItem(row_idx, 1, make_item(vs.name))
                self._vswitch_table.setItem(
                    row_idx, 2, make_item(pg.name if pg else "—")
                )
                self._vswitch_table.setItem(row_idx, 3, make_item(vlan_txt))
                self._vswitch_table.setItem(
                    row_idx,
                    4,
                    make_item(inventory_service.vswitch_uplink_labels(snapshot, vs)),
                )

        if search_service.normalize_query(query):
            self._search_hint.setText(
                f"уст. {len(devices)} · каб. {len(cables)} · "
                f"VLAN {len(vlans)} · VRF {len(vrfs)} · IP {len(ips)} · LAG {len(lags)} · "
                f"vSw {len(vs_rows)}"
            )
        else:
            self._search_hint.setText("")

        if select_row_by_id(self._table, selected_device):
            self._fill_ports(selected_device, preferred_port_id=selected_port)
        elif devices:
            # При активном поиске показываем первое совпадение
            if search_service.normalize_query(query):
                self._table.selectRow(0)
            else:
                with table_update(self._ports):
                    self._ports.setRowCount(0)
                self._ports_card.set_subtitle("Выберите устройство")
        else:
            with table_update(self._ports):
                self._ports.setRowCount(0)
            self._ports_card.set_subtitle(
                "Нет совпадений" if query else "Выберите устройство"
            )

        select_row_by_id(self._cables_table, selected_cable)
        select_row_by_id(self._vlans_table, selected_vlan)
        select_row_by_id(self._vrfs_table, selected_vrf)
        select_row_by_id(self._ips_table, selected_ip)
        select_row_by_id(self._lags_table, selected_lag)

    def selected_device_id(self) -> UUID | None:
        return self._selected_id(self._table)

    def selected_cable_id(self) -> UUID | None:
        return self._selected_id(self._cables_table)

    def selected_vlan_id(self) -> UUID | None:
        return self._selected_id(self._vlans_table)

    def selected_vrf_id(self) -> UUID | None:
        return self._selected_id(self._vrfs_table)

    def selected_ip_id(self) -> UUID | None:
        return self._selected_id(self._ips_table)

    def selected_lag_id(self) -> UUID | None:
        return self._selected_id(self._lags_table)

    def selected_vswitch_id(self) -> UUID | None:
        return self._selected_id(self._vswitch_table)

    def selected_port_group_id(self) -> UUID | None:
        rows = self._vswitch_table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self._vswitch_table.item(rows[0].row(), 0)
        if item is None:
            return None
        raw = item.data(Qt.ItemDataRole.UserRole + 1)
        return UUID(str(raw)) if raw else None

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

    def _fill_ports(
        self,
        device_id: UUID | None,
        *,
        preferred_port_id: UUID | None = None,
    ) -> None:
        snapshot = self._snapshot
        ports = self._ports_by_device.get(device_id, []) if device_id else []
        if snapshot is not None and ports:
            ports = search_service.filter_ports(snapshot, ports, self._query)

        if device_id is not None and snapshot is not None:
            device = next((d for d in snapshot.devices if d.id == device_id), None)
            name = device.hostname if device else "устройство"
            self._ports_card.set_subtitle(f"Порты: {name}")
            port = next((p for p in ports if p.id == preferred_port_id), None) if preferred_port_id else None
            if port is None and ports:
                port = ports[0]
            show_vnic = (
                device is not None
                and device.role == DeviceRole.VIRTUAL_MACHINE
                and port is not None
                and port.media == PortMedia.VIRTUAL
            )
            self._btn_vnic_host.setVisible(device is not None and device.role == DeviceRole.VIRTUAL_MACHINE)
            self._btn_vnic_host.setEnabled(show_vnic)
            self._btn_patch_matrix.setVisible(
                device is not None and device.role == DeviceRole.PATCH_PANEL
            )
            self._btn_patch_matrix.setEnabled(
                device is not None and device.role == DeviceRole.PATCH_PANEL
            )
        else:
            self._ports_card.set_subtitle("Выберите устройство")
            self._btn_vnic_host.setVisible(False)
            self._btn_vnic_host.setEnabled(False)
            self._btn_patch_matrix.setVisible(False)
            self._btn_patch_matrix.setEnabled(False)

        with table_update(self._ports):
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
                ip_parts = [inventory_service.ip_label(ip) for ip in ips]
                lag = inventory_service.lag_for_port(snapshot, p.id) if snapshot else None
                if lag is not None and snapshot is not None:
                    lag_ips = inventory_service.ips_for_lag(snapshot, lag.id)
                    if lag_ips:
                        ip_parts.append(
                            f"{lag.name}: "
                            + ", ".join(inventory_service.ip_label(ip) for ip in lag_ips)
                        )
                    else:
                        ip_parts.append(lag.name)
                ip_txt = ", ".join(ip_parts) if ip_parts else "—"
                name_item = make_item(p.name, entity_id=p.id)
                if lag is not None:
                    name_item.setToolTip(f"Член LAG «{lag.name}»")
                pair = (
                    inventory_service.paired_port(snapshot, p) if snapshot is not None else None
                )
                if pair is not None:
                    pair_txt = f"→ {pair.name}"
                    pair_tip = f"Сквозная пара: {p.name} ↔ {pair.name}"
                else:
                    pair_txt = "—"
                    pair_tip = ""
                pair_item = make_item(pair_txt)
                if pair_tip:
                    pair_item.setToolTip(pair_tip)
                    name_item.setToolTip(
                        (name_item.toolTip() + "\n" if name_item.toolTip() else "")
                        + pair_tip
                    )
                status_item = make_item(
                    f"{_STATUS_DOT.get(p.status, '●')} {status_label(p.status)}",
                    sort_key=p.status.value,
                )
                status_item.setForeground(
                    QBrush(_STATUS_COLOR.get(p.status, QColor("#23313a")))
                )
                self._ports.setItem(row_idx, 0, name_item)
                self._ports.setItem(row_idx, 1, pair_item)
                self._ports.setItem(
                    row_idx,
                    2,
                    make_item(p.mac or "—", sort_key=mac_sort_key(p.mac)),
                )
                self._ports.setItem(
                    row_idx, 3, make_item(f"{p.speed} Мбит/с", sort_key=int(p.speed))
                )
                self._ports.setItem(row_idx, 4, make_item(media_label(p.media)))
                self._ports.setItem(row_idx, 5, status_item)
                self._ports.setItem(row_idx, 6, make_item(link))
                host_nic = (
                    inventory_service.vnic_binding_label(snapshot, p.id)
                    if snapshot is not None and p.media == PortMedia.VIRTUAL
                    else "—"
                )
                self._ports.setItem(row_idx, 7, make_item(host_nic))
                self._ports.setItem(row_idx, 8, make_item(vlan_txt))
                ip_item = make_item(ip_txt, sort_key=ip_sort_key(ip_parts[0] if ip_parts else ""))
                if lag is not None:
                    ip_item.setForeground(QBrush(_ACCENT))
                    ip_item.setToolTip(
                        f"IP на LAG «{lag.name}»" if ":" in ip_txt else f"LAG «{lag.name}»"
                    )
                self._ports.setItem(row_idx, 9, ip_item)

        select_row_by_id(self._ports, preferred_port_id)

    def _on_selection_changed(self) -> None:
        device_id = self.selected_device_id()
        self._fill_ports(device_id)
        self.device_selection_changed.emit(device_id)

    def select_device(self, device_id: UUID | None) -> None:
        if device_id is None:
            self._table.clearSelection()
            return
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is None:
                continue
            raw = item.data(Qt.ItemDataRole.UserRole)
            if raw and UUID(raw) == device_id:
                self._table.selectRow(row)
                self._table.scrollToItem(item)
                return
        self._table.clearSelection()

    def _on_edit(self) -> None:
        device_id = self.selected_device_id()
        if device_id is not None:
            self.edit_device_requested.emit(device_id)

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

    def _on_edit_vrf(self) -> None:
        vrf_id = self.selected_vrf_id()
        if vrf_id is not None:
            self.edit_vrf_requested.emit(vrf_id)

    def _on_delete_vrf(self) -> None:
        vrf_id = self.selected_vrf_id()
        if vrf_id is not None:
            self.delete_vrf_requested.emit(vrf_id)

    def _on_edit_ip(self) -> None:
        ip_id = self.selected_ip_id()
        if ip_id is not None:
            self.edit_ip_requested.emit(ip_id)

    def _on_delete_ip(self) -> None:
        ip_id = self.selected_ip_id()
        if ip_id is not None:
            self.delete_ip_requested.emit(ip_id)

    def _on_edit_lag(self) -> None:
        lag_id = self.selected_lag_id()
        if lag_id is not None:
            self.edit_lag_requested.emit(lag_id)

    def _on_delete_lag(self) -> None:
        lag_id = self.selected_lag_id()
        if lag_id is not None:
            self.delete_lag_requested.emit(lag_id)

    def _on_edit_vswitch(self) -> None:
        vs_id = self.selected_vswitch_id()
        if vs_id is not None:
            self.edit_vswitch_requested.emit(vs_id)

    def _on_delete_vswitch(self) -> None:
        vs_id = self.selected_vswitch_id()
        if vs_id is not None:
            self.delete_vswitch_requested.emit(vs_id)

    def _on_edit_port_group(self) -> None:
        pg_id = self.selected_port_group_id()
        if pg_id is not None:
            self.edit_port_group_requested.emit(pg_id)
        else:
            vs_id = self.selected_vswitch_id()
            if vs_id is not None:
                self.edit_vswitch_requested.emit(vs_id)

    def _on_delete_port_group(self) -> None:
        pg_id = self.selected_port_group_id()
        if pg_id is not None:
            self.delete_port_group_requested.emit(pg_id)

    def _on_edit_port_network(self) -> None:
        port_id = self.selected_port_id()
        if port_id is not None:
            self.edit_port_network_requested.emit(port_id)

    def _on_edit_port_properties(self) -> None:
        port_id = self.selected_port_id()
        if port_id is not None:
            self.edit_port_properties_requested.emit(port_id)

    def _on_edit_vnic_host(self) -> None:
        port_id = self.selected_port_id()
        if port_id is not None:
            self.edit_vnic_host_requested.emit(port_id)

    def _on_patch_matrix(self) -> None:
        device_id = self.selected_device_id()
        if device_id is not None:
            self.patch_matrix_requested.emit(device_id)

    def _on_delete_port(self) -> None:
        port_id = self.selected_port_id()
        if port_id is not None:
            self.delete_port_requested.emit(port_id)
