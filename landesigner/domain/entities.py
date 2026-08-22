from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from landesigner.domain.enums import (
    CableCategory,
    CableKind,
    DeviceRole,
    LagMode,
    PortMedia,
    PortMode,
    PortSide,
    PortStatus,
    RackMountFace,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ProjectMeta:
    id: UUID = field(default_factory=uuid4)
    name: str = "Новый проект"
    schema_version: int = 1
    origin: str = "local"
    revision: int = 1
    updated_at: datetime = field(default_factory=utcnow)


@dataclass
class Site:
    id: UUID = field(default_factory=uuid4)
    project_id: UUID = field(default_factory=uuid4)
    name: str = "Площадка"
    address: str = ""
    notes: str = ""


@dataclass
class Building:
    id: UUID = field(default_factory=uuid4)
    site_id: UUID = field(default_factory=uuid4)
    name: str = "Здание"
    address: str = ""
    notes: str = ""


@dataclass
class Floor:
    id: UUID = field(default_factory=uuid4)
    building_id: UUID = field(default_factory=uuid4)
    name: str = "Этаж"
    level: float = 0.0
    plan_image_relpath: str = ""
    scale_m_per_px: float = 0.1


@dataclass
class Room:
    id: UUID = field(default_factory=uuid4)
    floor_id: UUID = field(default_factory=uuid4)
    name: str = "Комната"


@dataclass
class Rack:
    id: UUID = field(default_factory=uuid4)
    room_id: UUID = field(default_factory=uuid4)
    name: str = "Шкаф"
    units: int = 42
    unit_start: int = 1
    unit_end: int = 42


@dataclass
class DeviceType:
    id: UUID = field(default_factory=uuid4)
    site_id: UUID = field(default_factory=uuid4)
    vendor: str = ""
    model: str = ""
    role: DeviceRole = DeviceRole.OTHER
    # MVP: JSON-список шаблонов портов хранится как "сырые" dict, чтобы не ломать схему на старте.
    port_template: list[dict] = field(default_factory=list)


@dataclass
class Device:
    id: UUID = field(default_factory=uuid4)
    site_id: UUID = field(default_factory=uuid4)
    device_type_id: UUID = field(default_factory=uuid4)
    hostname: str = ""
    serial: str = ""
    inventory_tag: str = ""
    role: DeviceRole = DeviceRole.OTHER
    room_id: Optional[UUID] = None
    rack_id: Optional[UUID] = None
    rack_u: Optional[int] = None  # нижний юнит в шкафу
    rack_u_height: int = 1  # высота в U
    rack_mount_face: RackMountFace = RackMountFace.FRONT
    host_device_id: Optional[UUID] = None  # гипервизор для VIRTUAL_MACHINE


@dataclass
class Port:
    id: UUID = field(default_factory=uuid4)
    device_id: UUID = field(default_factory=uuid4)
    name: str = ""
    speed: int = 1000  # Mbps
    media: PortMedia = PortMedia.COPPER
    status: PortStatus = PortStatus.FREE
    mode: PortMode = PortMode.ACCESS
    mac: str = ""  # AA:BB:CC:DD:EE:FF, опционально
    side: PortSide = PortSide.NONE
    position: int = 0  # номер пары на патч-панели (1…N); 0 — обычный порт
    host_port_id: Optional[UUID] = None  # vNIC → физический NIC гипервизора (прямо)
    port_group_id: Optional[UUID] = None  # vNIC → Port Group (через vSwitch)
    # Access VLAN (ACCESS) или native/untagged (TRUNK).
    access_vlan_id: Optional[UUID] = None
    tagged_vlan_ids: list[UUID] = field(default_factory=list)


@dataclass
class Cable:
    id: UUID = field(default_factory=uuid4)
    site_id: UUID = field(default_factory=uuid4)
    label: str = ""
    kind: CableKind = CableKind.COPPER
    category: CableCategory = CableCategory.OTHER
    length_m: Optional[float] = None
    end_a_port_id: UUID = field(default_factory=uuid4)
    end_b_port_id: UUID = field(default_factory=uuid4)
    color: str = ""  # цвет маркировки
    purpose: str = ""  # назначение / роль в трассе


@dataclass
class Vlan:
    id: UUID = field(default_factory=uuid4)
    site_id: UUID = field(default_factory=uuid4)
    vlan_id: int = 1
    name: str = ""
    description: str = ""


@dataclass
class Vrf:
    """Виртуальный маршрутизатор / VRF — scope уникальности IP."""

    id: UUID = field(default_factory=uuid4)
    site_id: UUID = field(default_factory=uuid4)
    name: str = ""
    rd: str = ""  # Route Distinguisher, напр. 65000:100
    description: str = ""


@dataclass
class IpAddress:
    id: UUID = field(default_factory=uuid4)
    site_id: UUID = field(default_factory=uuid4)
    port_id: Optional[UUID] = None
    lag_id: Optional[UUID] = None
    vrf_id: Optional[UUID] = None
    address: str = ""  # e.g. 10.0.0.2
    cidr: str = ""  # e.g. 24
    gateway: str = ""


@dataclass
class Lag:
    """Агрегация портов одного устройства (bond / LAG / team)."""

    id: UUID = field(default_factory=uuid4)
    site_id: UUID = field(default_factory=uuid4)
    device_id: UUID = field(default_factory=uuid4)
    name: str = "bond0"
    mode: LagMode = LagMode.ACTIVE_BACKUP
    member_port_ids: list[UUID] = field(default_factory=list)
    notes: str = ""
    mac: str = ""  # MAC агрегата (часто у bond), опционально


@dataclass
class VirtualSwitch:
    """Виртуальный коммутатор гипервизора (vSwitch / vDS lite)."""

    id: UUID = field(default_factory=uuid4)
    site_id: UUID = field(default_factory=uuid4)
    host_device_id: UUID = field(default_factory=uuid4)
    name: str = "vSwitch0"
    notes: str = ""
    uplink_port_ids: list[UUID] = field(default_factory=list)


@dataclass
class PortGroup:
    """Порт-группа на vSwitch (имя + опциональный VLAN)."""

    id: UUID = field(default_factory=uuid4)
    vswitch_id: UUID = field(default_factory=uuid4)
    name: str = "VM Network"
    vlan_id: Optional[UUID] = None
    notes: str = ""


@dataclass
class TopologyNode:
    id: UUID = field(default_factory=uuid4)
    site_id: UUID = field(default_factory=uuid4)
    device_id: UUID = field(default_factory=uuid4)
    x: float = 0.0
    y: float = 0.0


@dataclass
class TopologyLink:
    id: UUID = field(default_factory=uuid4)
    site_id: UUID = field(default_factory=uuid4)
    topology_node_a_id: UUID = field(default_factory=uuid4)
    topology_node_b_id: UUID = field(default_factory=uuid4)
    cable_id: Optional[UUID] = None


@dataclass
class FloorPlanAsset:
    id: UUID = field(default_factory=uuid4)
    floor_id: UUID = field(default_factory=uuid4)
    device_id: UUID = field(default_factory=uuid4)
    x: float = 0.0
    y: float = 0.0
    rotation: float = 0.0


@dataclass
class FloorPlanRoute:
    """Полилиния трассы на плане этажа (опционально привязана к кабелю)."""

    id: UUID = field(default_factory=uuid4)
    floor_id: UUID = field(default_factory=uuid4)
    cable_id: Optional[UUID] = None
    points: list[tuple[float, float]] = field(default_factory=list)
    label: str = ""


@dataclass
class ProjectSnapshot:
    meta: ProjectMeta
    sites: list[Site] = field(default_factory=list)
    buildings: list[Building] = field(default_factory=list)
    floors: list[Floor] = field(default_factory=list)
    rooms: list[Room] = field(default_factory=list)
    racks: list[Rack] = field(default_factory=list)
    device_types: list[DeviceType] = field(default_factory=list)
    devices: list[Device] = field(default_factory=list)
    ports: list[Port] = field(default_factory=list)
    cables: list[Cable] = field(default_factory=list)
    vlans: list[Vlan] = field(default_factory=list)
    vrfs: list[Vrf] = field(default_factory=list)
    lags: list[Lag] = field(default_factory=list)
    virtual_switches: list[VirtualSwitch] = field(default_factory=list)
    port_groups: list[PortGroup] = field(default_factory=list)
    ips: list[IpAddress] = field(default_factory=list)
    topology_nodes: list[TopologyNode] = field(default_factory=list)
    topology_links: list[TopologyLink] = field(default_factory=list)
    floor_plan_assets: list[FloorPlanAsset] = field(default_factory=list)
    floor_plan_routes: list[FloorPlanRoute] = field(default_factory=list)

