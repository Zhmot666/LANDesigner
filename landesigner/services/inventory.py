from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from uuid import UUID

from landesigner.domain.entities import (
    Building,
    Cable,
    Device,
    DeviceType,
    Floor,
    IpAddress,
    Lag,
    Port,
    PortGroup,
    ProjectSnapshot,
    Rack,
    Room,
    VirtualSwitch,
    Vlan,
    Vrf,
)
from landesigner.domain.enums import (
    CableCategory,
    CableKind,
    DeviceRole,
    LagMode,
    PortMedia,
    PortMode,
    PortSide,
    PortStatus,
)


def normalize_mac(value: str) -> str:
    """Нормализовать MAC к виду AA:BB:CC:DD:EE:FF; пустая строка допустима."""
    raw = (value or "").strip()
    if not raw:
        return ""
    hex_chars = "".join(ch for ch in raw if ch.isalnum())
    if len(hex_chars) != 12 or any(
        ch not in "0123456789abcdefABCDEF" for ch in hex_chars
    ):
        raise ValueError("MAC должен быть вида AA:BB:CC:DD:EE:FF (12 hex-цифр)")
    return ":".join(hex_chars[i : i + 2].upper() for i in range(0, 12, 2))


def _require_site(snapshot: ProjectSnapshot) -> UUID:
    if not snapshot.sites:
        raise ValueError("В проекте нет Site")
    return snapshot.sites[0].id


def add_building(
    snapshot: ProjectSnapshot,
    name: str,
    *,
    address: str = "",
    notes: str = "",
) -> Building:
    site_id = _require_site(snapshot)
    building = Building(
        site_id=site_id,
        name=name.strip() or "Здание",
        address=address.strip(),
        notes=notes.strip(),
    )
    snapshot.buildings.append(building)
    return building


def update_building(
    snapshot: ProjectSnapshot,
    building_id: UUID,
    *,
    name: str,
    address: str = "",
    notes: str = "",
) -> Building:
    building = next((b for b in snapshot.buildings if b.id == building_id), None)
    if building is None:
        raise ValueError("Здание не найдено")
    building.name = name.strip() or "Здание"
    building.address = address.strip()
    building.notes = notes.strip()
    return building


def building_stats(snapshot: ProjectSnapshot, building_id: UUID) -> dict[str, int]:
    floors = [f for f in snapshot.floors if f.building_id == building_id]
    floor_ids = {f.id for f in floors}
    rooms = [r for r in snapshot.rooms if r.floor_id in floor_ids]
    room_ids = {r.id for r in rooms}
    racks = [rk for rk in snapshot.racks if rk.room_id in room_ids]
    devices = [d for d in snapshot.devices if d.room_id in room_ids]
    return {
        "floors": len(floors),
        "rooms": len(rooms),
        "racks": len(racks),
        "devices": len(devices),
    }


def project_stats(snapshot: ProjectSnapshot) -> dict[str, int]:
    return {
        "buildings": len(snapshot.buildings),
        "floors": len(snapshot.floors),
        "rooms": len(snapshot.rooms),
        "racks": len(snapshot.racks),
        "devices": len(snapshot.devices),
        "cables": len(snapshot.cables),
        "types": len(snapshot.device_types),
        "vlans": len(snapshot.vlans),
        "vrfs": len(snapshot.vrfs),
    }


def add_floor(
    snapshot: ProjectSnapshot,
    building_id: UUID,
    name: str,
    level: float = 0.0,
) -> Floor:
    floor = Floor(
        building_id=building_id,
        name=name.strip() or "Этаж",
        level=level,
    )
    snapshot.floors.append(floor)
    return floor


def add_room(snapshot: ProjectSnapshot, floor_id: UUID, name: str) -> Room:
    room = Room(floor_id=floor_id, name=name.strip() or "Комната")
    snapshot.rooms.append(room)
    return room


def add_rack(
    snapshot: ProjectSnapshot,
    room_id: UUID,
    name: str,
    units: int = 42,
) -> Rack:
    rack = Rack(
        room_id=room_id,
        name=name.strip() or "Шкаф",
        units=units,
        unit_start=1,
        unit_end=units,
    )
    snapshot.racks.append(rack)
    return rack


def update_site(snapshot: ProjectSnapshot, site_id: UUID, name: str) -> None:
    site = next((s for s in snapshot.sites if s.id == site_id), None)
    if site is None:
        raise ValueError("Площадка не найдена")
    site.name = name.strip() or site.name


def update_floor(
    snapshot: ProjectSnapshot,
    floor_id: UUID,
    name: str,
    level: float,
) -> None:
    floor = next((f for f in snapshot.floors if f.id == floor_id), None)
    if floor is None:
        raise ValueError("Этаж не найден")
    floor.name = name.strip() or floor.name
    floor.level = level


def update_room(snapshot: ProjectSnapshot, room_id: UUID, name: str) -> None:
    room = next((r for r in snapshot.rooms if r.id == room_id), None)
    if room is None:
        raise ValueError("Комната не найдена")
    room.name = name.strip() or room.name


def update_rack(
    snapshot: ProjectSnapshot,
    rack_id: UUID,
    name: str,
    units: int,
) -> None:
    rack = next((r for r in snapshot.racks if r.id == rack_id), None)
    if rack is None:
        raise ValueError("Шкаф не найден")
    rack.name = name.strip() or rack.name
    rack.units = units
    rack.unit_end = units


def _clear_device_location_refs(
    snapshot: ProjectSnapshot,
    *,
    room_ids: set[UUID] | None = None,
    rack_ids: set[UUID] | None = None,
) -> None:
    room_ids = room_ids or set()
    rack_ids = rack_ids or set()
    for device in snapshot.devices:
        if device.room_id in room_ids:
            device.room_id = None
        if device.rack_id in rack_ids:
            device.rack_id = None


def delete_building(snapshot: ProjectSnapshot, building_id: UUID) -> None:
    floor_ids = {f.id for f in snapshot.floors if f.building_id == building_id}
    room_ids = {r.id for r in snapshot.rooms if r.floor_id in floor_ids}
    rack_ids = {rk.id for rk in snapshot.racks if rk.room_id in room_ids}
    _clear_device_location_refs(snapshot, room_ids=room_ids, rack_ids=rack_ids)
    snapshot.racks = [rk for rk in snapshot.racks if rk.id not in rack_ids]
    snapshot.rooms = [r for r in snapshot.rooms if r.id not in room_ids]
    snapshot.floors = [f for f in snapshot.floors if f.id not in floor_ids]
    snapshot.buildings = [b for b in snapshot.buildings if b.id != building_id]


def delete_floor(snapshot: ProjectSnapshot, floor_id: UUID) -> None:
    room_ids = {r.id for r in snapshot.rooms if r.floor_id == floor_id}
    rack_ids = {rk.id for rk in snapshot.racks if rk.room_id in room_ids}
    _clear_device_location_refs(snapshot, room_ids=room_ids, rack_ids=rack_ids)
    snapshot.floor_plan_assets = [
        a for a in snapshot.floor_plan_assets if a.floor_id != floor_id
    ]
    snapshot.racks = [rk for rk in snapshot.racks if rk.id not in rack_ids]
    snapshot.rooms = [r for r in snapshot.rooms if r.id not in room_ids]
    snapshot.floors = [f for f in snapshot.floors if f.id != floor_id]


def delete_room(snapshot: ProjectSnapshot, room_id: UUID) -> None:
    rack_ids = {rk.id for rk in snapshot.racks if rk.room_id == room_id}
    _clear_device_location_refs(snapshot, room_ids={room_id}, rack_ids=rack_ids)
    snapshot.racks = [rk for rk in snapshot.racks if rk.id not in rack_ids]
    snapshot.rooms = [r for r in snapshot.rooms if r.id != room_id]


def delete_rack(snapshot: ProjectSnapshot, rack_id: UUID) -> None:
    _clear_device_location_refs(snapshot, rack_ids={rack_id})
    snapshot.racks = [rk for rk in snapshot.racks if rk.id != rack_id]


def add_device_type(
    snapshot: ProjectSnapshot,
    vendor: str,
    model: str,
    role: DeviceRole | str,
    port_groups: list[dict] | None = None,
    *,
    port_count: int | None = None,
    media: PortMedia | str = PortMedia.COPPER,
    speed: int = 1000,
) -> DeviceType:
    """
    Создаёт тип устройства.

    port_groups — список групп портов с разной скоростью/средой, например:
      [{"prefix": "Gi1/0/", "count": 24, "media": "COPPER", "speed": 1000, "start": 1},
       {"prefix": "Te1/0/", "count": 4, "media": "FIBER", "speed": 10000, "start": 1}]

    Устаревшие аргументы port_count/media/speed поддерживаются для простых случаев
    и тестов: одна группа на все порты.
    """
    site_id = _require_site(snapshot)
    role_enum = role if isinstance(role, DeviceRole) else DeviceRole(str(role))

    if port_groups is None:
        media_enum = media if isinstance(media, PortMedia) else PortMedia(str(media))
        port_groups = [
            {
                "prefix": "Gi1/0/",
                "count": max(1, int(port_count or 24)),
                "media": media_enum.value,
                "speed": int(speed),
                "start": 1,
            }
        ]

    template = build_port_template(port_groups)
    device_type = DeviceType(
        site_id=site_id,
        vendor=vendor.strip(),
        model=model.strip(),
        role=role_enum,
        port_template=template,
    )
    snapshot.device_types.append(device_type)
    return device_type


def build_port_template(port_groups: list[dict]) -> list[dict]:
    template: list[dict] = []
    for group in port_groups:
        count = max(0, int(group.get("count", 0)))
        if count <= 0:
            continue
        prefix = str(group.get("prefix", "Port"))
        start = int(group.get("start", 1))
        speed = int(group.get("speed", 1000))
        media_raw = str(group.get("media", PortMedia.COPPER.value))
        try:
            media = PortMedia(media_raw).value
        except ValueError:
            media = PortMedia.COPPER.value
        side_raw = str(group.get("side", PortSide.NONE.value))
        try:
            side = PortSide(side_raw).value
        except ValueError:
            side = PortSide.NONE.value
        use_position = side != PortSide.NONE.value or bool(group.get("paired"))
        for i in range(start, start + count):
            entry: dict = {"name": f"{prefix}{i}", "media": media, "speed": speed}
            if side != PortSide.NONE.value:
                entry["side"] = side
            if use_position:
                entry["position"] = i
            template.append(entry)
    if not template:
        template = [{"name": "Gi1/0/1", "media": PortMedia.COPPER.value, "speed": 1000}]
    return template


def build_patch_panel_port_groups(
    count: int = 24,
    *,
    media: PortMedia | str = PortMedia.COPPER,
    speed: int = 1000,
) -> list[dict]:
    """Группы портов патч-панели: Front-1..N и Rear-1..N."""
    media_enum = media if isinstance(media, PortMedia) else PortMedia(str(media))
    n = max(1, int(count))
    return [
        {
            "prefix": "Front-",
            "count": n,
            "media": media_enum.value,
            "speed": int(speed),
            "start": 1,
            "side": PortSide.FRONT.value,
            "paired": True,
        },
        {
            "prefix": "Rear-",
            "count": n,
            "media": media_enum.value,
            "speed": int(speed),
            "start": 1,
            "side": PortSide.REAR.value,
            "paired": True,
        },
    ]


def build_patch_panel_template(
    count: int = 24,
    *,
    media: PortMedia | str = PortMedia.COPPER,
    speed: int = 1000,
) -> list[dict]:
    return build_port_template(build_patch_panel_port_groups(count, media=media, speed=speed))


def update_device_type(
    snapshot: ProjectSnapshot,
    device_type_id: UUID,
    vendor: str,
    model: str,
    role: DeviceRole | str,
    port_groups: list[dict],
) -> DeviceType:
    device_type = next((dt for dt in snapshot.device_types if dt.id == device_type_id), None)
    if device_type is None:
        raise ValueError("Тип устройства не найден")

    role_enum = role if isinstance(role, DeviceRole) else DeviceRole(str(role))
    device_type.vendor = vendor.strip()
    device_type.model = model.strip()
    device_type.role = role_enum
    device_type.port_template = build_port_template(port_groups)

    # Роль на существующих устройствах этого типа обновляем;
    # порты существующих устройств не пересоздаём (чтобы не рвать кабели).
    for device in snapshot.devices:
        if device.device_type_id == device_type_id:
            device.role = role_enum

    return device_type


def delete_device_type(snapshot: ProjectSnapshot, device_type_id: UUID) -> None:
    in_use = any(d.device_type_id == device_type_id for d in snapshot.devices)
    if in_use:
        raise ValueError("Тип используется устройствами — сначала удалите или смените их")
    snapshot.device_types = [dt for dt in snapshot.device_types if dt.id != device_type_id]


def _ports_from_template(device_id: UUID, template: list[dict]) -> list[Port]:
    ports: list[Port] = []
    for item in template:
        media_raw = str(item.get("media", PortMedia.COPPER.value))
        try:
            media = PortMedia(media_raw)
        except ValueError:
            media = PortMedia.COPPER
        side_raw = str(item.get("side", PortSide.NONE.value))
        try:
            side = PortSide(side_raw)
        except ValueError:
            side = PortSide.NONE
        ports.append(
            Port(
                device_id=device_id,
                name=str(item.get("name", "port")),
                speed=int(item.get("speed", 1000)),
                media=media,
                status=PortStatus.FREE,
                side=side,
                position=int(item.get("position", 0) or 0),
            )
        )
    return ports


def update_port(
    snapshot: ProjectSnapshot,
    port_id: UUID,
    *,
    name: str | None = None,
    speed: int | None = None,
    media: PortMedia | str | None = None,
    mac: str | None = None,
) -> Port:
    port = next((p for p in snapshot.ports if p.id == port_id), None)
    if port is None:
        raise ValueError("Порт не найден")
    if name is not None:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("Имя порта не может быть пустым")
        siblings = [
            p for p in snapshot.ports if p.device_id == port.device_id and p.id != port_id
        ]
        if any(p.name == cleaned for p in siblings):
            raise ValueError(f"Порт «{cleaned}» уже есть на устройстве")
        port.name = cleaned
    if speed is not None:
        if int(speed) <= 0:
            raise ValueError("Скорость должна быть больше 0")
        port.speed = int(speed)
    if media is not None:
        new_media = media if isinstance(media, PortMedia) else PortMedia(str(media))
        if port.media == PortMedia.VIRTUAL and new_media != PortMedia.VIRTUAL:
            port.host_port_id = None
        port.media = new_media
    if mac is not None:
        port.mac = normalize_mac(mac)
    return port


def add_port(
    snapshot: ProjectSnapshot,
    device_id: UUID,
    name: str,
    *,
    speed: int = 1000,
    media: PortMedia | str = PortMedia.COPPER,
    mac: str = "",
) -> Port:
    device = next((d for d in snapshot.devices if d.id == device_id), None)
    if device is None:
        raise ValueError("Устройство не найдено")
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("Имя порта не может быть пустым")
    if any(p.name == cleaned for p in snapshot.ports if p.device_id == device_id):
        raise ValueError(f"Порт «{cleaned}» уже есть на устройстве")
    if int(speed) <= 0:
        raise ValueError("Скорость должна быть больше 0")
    media_enum = media if isinstance(media, PortMedia) else PortMedia(str(media))
    if device.role == DeviceRole.VIRTUAL_MACHINE:
        media_enum = PortMedia.VIRTUAL
        if not cleaned.lower().startswith("vnic"):
            cleaned = f"vNIC{len(ports_for_device(snapshot, device_id))}"
    port = Port(
        device_id=device_id,
        name=cleaned,
        speed=int(speed),
        media=media_enum,
        status=PortStatus.FREE,
        mac=normalize_mac(mac),
    )
    snapshot.ports.append(port)
    return port


def delete_port(snapshot: ProjectSnapshot, port_id: UUID) -> None:
    port = next((p for p in snapshot.ports if p.id == port_id), None)
    if port is None:
        return
    lag = lag_for_port(snapshot, port_id)
    if lag is not None:
        raise ValueError(
            f"Порт входит в LAG «{lag.name}». Сначала уберите его из агрегата."
        )
    for vs in snapshot.virtual_switches:
        if port_id in vs.uplink_port_ids:
            raise ValueError(
                f"Порт — uplink vSwitch «{vs.name}». Сначала уберите его из vSwitch."
            )
    cable = cable_for_port(snapshot, port_id)
    if cable is not None:
        delete_cable(snapshot, cable.id)
    _clear_vnic_mappings_to_port(snapshot, port_id)
    snapshot.ips = [ip for ip in snapshot.ips if ip.port_id != port_id]
    snapshot.ports = [p for p in snapshot.ports if p.id != port_id]


def vms_for_host(snapshot: ProjectSnapshot, host_id: UUID) -> list[Device]:
    vms = [
        d
        for d in snapshot.devices
        if d.host_device_id == host_id and d.role == DeviceRole.VIRTUAL_MACHINE
    ]
    vms.sort(key=lambda d: d.hostname.casefold())
    return vms


def host_for_device(snapshot: ProjectSnapshot, device: Device) -> Device | None:
    if device.host_device_id is None:
        return None
    return next((d for d in snapshot.devices if d.id == device.host_device_id), None)


def host_nics_for_vm(snapshot: ProjectSnapshot, vm_device_id: UUID) -> list[Port]:
    """Физические NIC гипервизора, доступные для привязки vNIC."""
    device = next((d for d in snapshot.devices if d.id == vm_device_id), None)
    if device is None or device.role != DeviceRole.VIRTUAL_MACHINE:
        return []
    host = host_for_device(snapshot, device)
    if host is None:
        return []
    ports = [
        p
        for p in ports_for_device(snapshot, host.id)
        if p.media != PortMedia.VIRTUAL
    ]
    ports.sort(key=lambda p: (p.name.casefold(), str(p.id)))
    return ports


def vnic_host_port(snapshot: ProjectSnapshot, port_id: UUID) -> Port | None:
    port = next((p for p in snapshot.ports if p.id == port_id), None)
    if port is None or port.host_port_id is None:
        return None
    return next((p for p in snapshot.ports if p.id == port.host_port_id), None)


def vnic_port_group(snapshot: ProjectSnapshot, port_id: UUID) -> PortGroup | None:
    port = next((p for p in snapshot.ports if p.id == port_id), None)
    if port is None or port.port_group_id is None:
        return None
    return next((pg for pg in snapshot.port_groups if pg.id == port.port_group_id), None)


def vnic_binding_label(snapshot: ProjectSnapshot, port_id: UUID) -> str:
    """Подпись привязки vNIC: Port Group предпочтительнее прямой NIC."""
    pg = vnic_port_group(snapshot, port_id)
    if pg is not None:
        vs = next((v for v in snapshot.virtual_switches if v.id == pg.vswitch_id), None)
        vs_name = vs.name if vs is not None else "?"
        vlan = next((v for v in snapshot.vlans if v.id == pg.vlan_id), None) if pg.vlan_id else None
        vlan_txt = f" · VLAN {vlan.vlan_id}" if vlan is not None else ""
        return f"{vs_name}/{pg.name}{vlan_txt}"
    return vnic_host_port_label(snapshot, port_id)


def vnic_host_port_label(snapshot: ProjectSnapshot, port_id: UUID) -> str:
    host_port = vnic_host_port(snapshot, port_id)
    if host_port is None:
        return "—"
    return port_endpoint_label(snapshot, host_port.id)


def _clear_vnic_mappings_to_port(snapshot: ProjectSnapshot, host_port_id: UUID) -> None:
    for port in snapshot.ports:
        if port.host_port_id == host_port_id:
            port.host_port_id = None


def _clear_vnic_mappings_to_port_group(snapshot: ProjectSnapshot, port_group_id: UUID) -> None:
    for port in snapshot.ports:
        if port.port_group_id == port_group_id:
            port.port_group_id = None


def _clear_vm_vnic_mappings(snapshot: ProjectSnapshot, vm_device_id: UUID) -> None:
    for port in snapshot.ports:
        if port.device_id == vm_device_id and port.media == PortMedia.VIRTUAL:
            port.host_port_id = None
            port.port_group_id = None


def set_vnic_host_port(
    snapshot: ProjectSnapshot,
    port_id: UUID,
    host_port_id: UUID | None,
) -> Port:
    port = next((p for p in snapshot.ports if p.id == port_id), None)
    if port is None:
        raise ValueError("Порт не найден")
    device = next((d for d in snapshot.devices if d.id == port.device_id), None)
    if device is None:
        raise ValueError("Устройство не найдено")
    if device.role != DeviceRole.VIRTUAL_MACHINE:
        raise ValueError("Привязка NIC хоста доступна только для vNIC виртуального сервера")
    if port.media != PortMedia.VIRTUAL:
        raise ValueError("Привязка NIC хоста доступна только для vNIC (среда vNIC)")

    if host_port_id is None:
        port.host_port_id = None
        return port

    host_port = next((p for p in snapshot.ports if p.id == host_port_id), None)
    if host_port is None:
        raise ValueError("NIC хоста не найден")
    host_device = host_for_device(snapshot, device)
    if host_device is None:
        raise ValueError("У виртуального сервера не указан гипервизор")
    if host_port.device_id != host_device.id:
        raise ValueError("NIC должен принадлежать гипервизору этой ВМ")
    if host_port.media == PortMedia.VIRTUAL:
        raise ValueError("NIC хоста не может быть виртуальным портом")

    port.host_port_id = host_port.id
    port.port_group_id = None
    return port


def set_vnic_port_group(
    snapshot: ProjectSnapshot,
    port_id: UUID,
    port_group_id: UUID | None,
) -> Port:
    port = next((p for p in snapshot.ports if p.id == port_id), None)
    if port is None:
        raise ValueError("Порт не найден")
    device = next((d for d in snapshot.devices if d.id == port.device_id), None)
    if device is None:
        raise ValueError("Устройство не найдено")
    if device.role != DeviceRole.VIRTUAL_MACHINE:
        raise ValueError("Port Group доступен только для vNIC виртуального сервера")
    if port.media != PortMedia.VIRTUAL:
        raise ValueError("Port Group доступен только для vNIC")

    if port_group_id is None:
        port.port_group_id = None
        return port

    pg = next((item for item in snapshot.port_groups if item.id == port_group_id), None)
    if pg is None:
        raise ValueError("Port Group не найден")
    vs = next((item for item in snapshot.virtual_switches if item.id == pg.vswitch_id), None)
    if vs is None:
        raise ValueError("vSwitch Port Group не найден")
    host = host_for_device(snapshot, device)
    if host is None:
        raise ValueError("У виртуального сервера не указан гипервизор")
    if vs.host_device_id != host.id:
        raise ValueError("Port Group должен быть на гипервизоре этой ВМ")

    port.port_group_id = pg.id
    port.host_port_id = None
    return port


def vswitches_for_host(snapshot: ProjectSnapshot, host_device_id: UUID) -> list[VirtualSwitch]:
    items = [vs for vs in snapshot.virtual_switches if vs.host_device_id == host_device_id]
    items.sort(key=lambda vs: vs.name.casefold())
    return items


def port_groups_for_vswitch(snapshot: ProjectSnapshot, vswitch_id: UUID) -> list[PortGroup]:
    items = [pg for pg in snapshot.port_groups if pg.vswitch_id == vswitch_id]
    items.sort(key=lambda pg: pg.name.casefold())
    return items


def port_groups_for_vm(snapshot: ProjectSnapshot, vm_device_id: UUID) -> list[PortGroup]:
    device = next((d for d in snapshot.devices if d.id == vm_device_id), None)
    if device is None or device.role != DeviceRole.VIRTUAL_MACHINE:
        return []
    host = host_for_device(snapshot, device)
    if host is None:
        return []
    result: list[PortGroup] = []
    for vs in vswitches_for_host(snapshot, host.id):
        result.extend(port_groups_for_vswitch(snapshot, vs.id))
    return result


def vswitch_uplink_labels(snapshot: ProjectSnapshot, vs: VirtualSwitch) -> str:
    labels: list[str] = []
    for port_id in vs.uplink_port_ids:
        port = next((p for p in snapshot.ports if p.id == port_id), None)
        labels.append(port.name if port is not None else "?")
    return ", ".join(labels) if labels else "—"


def port_group_label(snapshot: ProjectSnapshot, pg: PortGroup) -> str:
    vs = next((v for v in snapshot.virtual_switches if v.id == pg.vswitch_id), None)
    host = (
        next((d for d in snapshot.devices if d.id == vs.host_device_id), None)
        if vs is not None
        else None
    )
    vlan = next((v for v in snapshot.vlans if v.id == pg.vlan_id), None) if pg.vlan_id else None
    parts = [
        host.hostname if host else "?",
        vs.name if vs else "?",
        pg.name,
    ]
    base = " / ".join(parts)
    if vlan is not None:
        return f"{base} (VLAN {vlan.vlan_id})"
    return base


def _validate_vswitch_uplinks(
    snapshot: ProjectSnapshot,
    host_device_id: UUID,
    uplink_port_ids: list[UUID],
    *,
    exclude_vswitch_id: UUID | None = None,
) -> list[UUID]:
    members: list[UUID] = []
    seen: set[UUID] = set()
    for port_id in uplink_port_ids:
        if port_id in seen:
            continue
        seen.add(port_id)
        port = next((p for p in snapshot.ports if p.id == port_id), None)
        if port is None:
            raise ValueError("Uplink-порт не найден")
        if port.device_id != host_device_id:
            raise ValueError("Uplink должен принадлежать гипервизору")
        if port.media == PortMedia.VIRTUAL:
            raise ValueError("Uplink не может быть виртуальным портом")
        for other in snapshot.virtual_switches:
            if exclude_vswitch_id is not None and other.id == exclude_vswitch_id:
                continue
            if port_id in other.uplink_port_ids:
                raise ValueError(
                    f"Порт «{port.name}» уже uplink у vSwitch «{other.name}»"
                )
        members.append(port_id)
    return members


def add_virtual_switch(
    snapshot: ProjectSnapshot,
    host_device_id: UUID,
    name: str,
    *,
    uplink_port_ids: list[UUID] | None = None,
    notes: str = "",
) -> VirtualSwitch:
    host = next((d for d in snapshot.devices if d.id == host_device_id), None)
    if host is None:
        raise ValueError("Гипервизор не найден")
    if host.role != DeviceRole.HYPERVISOR:
        raise ValueError("vSwitch можно создать только на гипервизоре")
    cleaned = (name or "").strip() or "vSwitch0"
    uplinks = _validate_vswitch_uplinks(
        snapshot, host_device_id, list(uplink_port_ids or [])
    )
    vs = VirtualSwitch(
        site_id=host.site_id,
        host_device_id=host.id,
        name=cleaned,
        notes=(notes or "").strip(),
        uplink_port_ids=uplinks,
    )
    snapshot.virtual_switches.append(vs)
    return vs


def update_virtual_switch(
    snapshot: ProjectSnapshot,
    vswitch_id: UUID,
    *,
    name: str | None = None,
    uplink_port_ids: list[UUID] | None = None,
    notes: str | None = None,
) -> VirtualSwitch:
    vs = next((item for item in snapshot.virtual_switches if item.id == vswitch_id), None)
    if vs is None:
        raise ValueError("vSwitch не найден")
    if name is not None:
        vs.name = name.strip() or vs.name
    if notes is not None:
        vs.notes = notes.strip()
    if uplink_port_ids is not None:
        vs.uplink_port_ids = _validate_vswitch_uplinks(
            snapshot,
            vs.host_device_id,
            uplink_port_ids,
            exclude_vswitch_id=vs.id,
        )
    return vs


def delete_virtual_switch(snapshot: ProjectSnapshot, vswitch_id: UUID) -> None:
    pg_ids = {pg.id for pg in snapshot.port_groups if pg.vswitch_id == vswitch_id}
    for port in snapshot.ports:
        if port.port_group_id in pg_ids:
            port.port_group_id = None
    snapshot.port_groups = [pg for pg in snapshot.port_groups if pg.vswitch_id != vswitch_id]
    snapshot.virtual_switches = [
        vs for vs in snapshot.virtual_switches if vs.id != vswitch_id
    ]


def add_port_group(
    snapshot: ProjectSnapshot,
    vswitch_id: UUID,
    name: str,
    *,
    vlan_id: UUID | None = None,
    notes: str = "",
) -> PortGroup:
    vs = next((item for item in snapshot.virtual_switches if item.id == vswitch_id), None)
    if vs is None:
        raise ValueError("vSwitch не найден")
    if vlan_id is not None and not any(v.id == vlan_id for v in snapshot.vlans):
        raise ValueError("VLAN не найден")
    cleaned = (name or "").strip() or "VM Network"
    pg = PortGroup(
        vswitch_id=vs.id,
        name=cleaned,
        vlan_id=vlan_id,
        notes=(notes or "").strip(),
    )
    snapshot.port_groups.append(pg)
    return pg


def update_port_group(
    snapshot: ProjectSnapshot,
    port_group_id: UUID,
    *,
    name: str | None = None,
    vlan_id: UUID | None = None,
    clear_vlan: bool = False,
    notes: str | None = None,
) -> PortGroup:
    pg = next((item for item in snapshot.port_groups if item.id == port_group_id), None)
    if pg is None:
        raise ValueError("Port Group не найден")
    if name is not None:
        pg.name = name.strip() or pg.name
    if notes is not None:
        pg.notes = notes.strip()
    if clear_vlan:
        pg.vlan_id = None
    elif vlan_id is not None:
        if not any(v.id == vlan_id for v in snapshot.vlans):
            raise ValueError("VLAN не найден")
        pg.vlan_id = vlan_id
    return pg


def delete_port_group(snapshot: ProjectSnapshot, port_group_id: UUID) -> None:
    _clear_vnic_mappings_to_port_group(snapshot, port_group_id)
    snapshot.port_groups = [pg for pg in snapshot.port_groups if pg.id != port_group_id]


def _require_hypervisor_host(
    snapshot: ProjectSnapshot,
    host_device_id: UUID,
    *,
    site_id: UUID,
    exclude_device_id: UUID | None = None,
) -> Device:
    if exclude_device_id is not None and host_device_id == exclude_device_id:
        raise ValueError("ВМ не может быть хостом самой себе")
    host = next((d for d in snapshot.devices if d.id == host_device_id), None)
    if host is None:
        raise ValueError("Гипервизор не найден")
    if host.role != DeviceRole.HYPERVISOR:
        raise ValueError("Хост должен иметь роль «Гипервизор»")
    if host.site_id != site_id:
        raise ValueError("Гипервизор должен быть на той же площадке")
    return host


def _apply_vm_host(
    snapshot: ProjectSnapshot,
    device: Device,
    host_device_id: UUID,
) -> None:
    host = _require_hypervisor_host(
        snapshot,
        host_device_id,
        site_id=device.site_id,
        exclude_device_id=device.id,
    )
    device.host_device_id = host.id
    device.room_id = host.room_id
    device.rack_id = None
    device.rack_u = None
    device.rack_u_height = 1
    _clear_vm_vnic_mappings(snapshot, device.id)


def add_device(
    snapshot: ProjectSnapshot,
    device_type_id: UUID,
    hostname: str,
    serial: str = "",
    inventory_tag: str = "",
    room_id: UUID | None = None,
    rack_id: UUID | None = None,
    rack_u: int | None = None,
    rack_u_height: int = 1,
    host_device_id: UUID | None = None,
) -> Device:
    site_id = _require_site(snapshot)
    device_type = next((dt for dt in snapshot.device_types if dt.id == device_type_id), None)
    if device_type is None:
        raise ValueError("Тип устройства не найден")

    is_vm = device_type.role == DeviceRole.VIRTUAL_MACHINE
    if is_vm and host_device_id is None:
        raise ValueError("Для виртуального сервера укажите гипервизор")
    if not is_vm and host_device_id is not None:
        raise ValueError("Привязка к гипервизору доступна только для ВМ")

    device = Device(
        site_id=site_id,
        device_type_id=device_type.id,
        hostname=hostname.strip() or "устройство",
        serial=serial.strip(),
        inventory_tag=inventory_tag.strip(),
        role=device_type.role,
        room_id=None,
        rack_id=None,
        rack_u=None,
        rack_u_height=1,
        host_device_id=None,
    )
    snapshot.devices.append(device)
    snapshot.ports.extend(_ports_from_template(device.id, device_type.port_template))

    if is_vm:
        vm_ports = [p for p in snapshot.ports if p.device_id == device.id]
        for index, port in enumerate(vm_ports):
            port.media = PortMedia.VIRTUAL
            port.name = f"vNIC{index}"
        assert host_device_id is not None
        _apply_vm_host(snapshot, device, host_device_id)
        return device

    if rack_id is not None or rack_u is not None:
        set_device_rack_placement(
            snapshot,
            device.id,
            rack_id=rack_id,
            rack_u=rack_u,
            rack_u_height=rack_u_height,
            room_id=room_id,
        )
    elif room_id is not None:
        device.room_id = room_id
    return device


def update_device(
    snapshot: ProjectSnapshot,
    device_id: UUID,
    *,
    hostname: str | None = None,
    serial: str | None = None,
    inventory_tag: str | None = None,
    room_id: UUID | None = None,
    rack_id: UUID | None = None,
    rack_u: int | None = None,
    rack_u_height: int | None = None,
    host_device_id: UUID | None = None,
    clear_room: bool = False,
    clear_rack: bool = False,
    clear_host: bool = False,
) -> Device:
    device = next((d for d in snapshot.devices if d.id == device_id), None)
    if device is None:
        raise ValueError("Устройство не найдено")

    if hostname is not None:
        device.hostname = hostname.strip() or device.hostname
    if serial is not None:
        device.serial = serial.strip()
    if inventory_tag is not None:
        device.inventory_tag = inventory_tag.strip()

    is_vm = device.role == DeviceRole.VIRTUAL_MACHINE
    if clear_host:
        if is_vm:
            raise ValueError("Для виртуального сервера укажите гипервизор")
        device.host_device_id = None
    elif host_device_id is not None:
        if not is_vm:
            raise ValueError("Привязка к гипервизору доступна только для ВМ")
        _apply_vm_host(snapshot, device, host_device_id)
        return device

    if is_vm:
        # ВМ не монтируется в шкаф; локация только через хост.
        if device.host_device_id is None:
            raise ValueError("Для виртуального сервера укажите гипервизор")
        host = _require_hypervisor_host(
            snapshot,
            device.host_device_id,
            site_id=device.site_id,
            exclude_device_id=device.id,
        )
        device.room_id = host.room_id
        device.rack_id = None
        device.rack_u = None
        device.rack_u_height = 1
        return device

    if clear_room:
        device.room_id = None
        device.rack_id = None
        device.rack_u = None
        device.rack_u_height = 1
        return device

    if room_id is not None:
        device.room_id = room_id
        # Шкаф другой комнаты сбрасываем.
        if device.rack_id is not None:
            rack = next((r for r in snapshot.racks if r.id == device.rack_id), None)
            if rack is None or rack.room_id != room_id:
                device.rack_id = None
                device.rack_u = None
                device.rack_u_height = 1

    if clear_rack:
        device.rack_id = None
        device.rack_u = None
        device.rack_u_height = 1
    elif rack_id is not None or rack_u is not None or rack_u_height is not None:
        set_device_rack_placement(
            snapshot,
            device_id,
            rack_id=rack_id if rack_id is not None else device.rack_id,
            rack_u=rack_u if rack_u is not None else device.rack_u,
            rack_u_height=(
                rack_u_height if rack_u_height is not None else device.rack_u_height
            ),
            room_id=device.room_id,
        )
    return device


def devices_in_rack(snapshot: ProjectSnapshot, rack_id: UUID) -> list[Device]:
    devices = [d for d in snapshot.devices if d.rack_id == rack_id]
    devices.sort(
        key=lambda d: (
            d.rack_u if d.rack_u is not None else 10**9,
            d.hostname.casefold(),
        )
    )
    return devices


def rack_u_range(device: Device) -> tuple[int, int] | None:
    if device.rack_id is None or device.rack_u is None:
        return None
    height = max(1, int(device.rack_u_height or 1))
    start = int(device.rack_u)
    return start, start + height - 1


def rack_placement_label(device: Device) -> str:
    rng = rack_u_range(device)
    if rng is None:
        return ""
    start, end = rng
    if start == end:
        return f"U{start}"
    return f"U{start}–{end}"


def rack_occupied_units(
    snapshot: ProjectSnapshot,
    rack_id: UUID,
    *,
    exclude_device_id: UUID | None = None,
) -> set[int]:
    used: set[int] = set()
    for device in devices_in_rack(snapshot, rack_id):
        if exclude_device_id is not None and device.id == exclude_device_id:
            continue
        rng = rack_u_range(device)
        if rng is None:
            continue
        start, end = rng
        used.update(range(start, end + 1))
    return used


def rack_free_units(snapshot: ProjectSnapshot, rack_id: UUID) -> list[int]:
    rack = next((r for r in snapshot.racks if r.id == rack_id), None)
    if rack is None:
        return []
    occupied = rack_occupied_units(snapshot, rack_id)
    return [u for u in range(1, int(rack.units) + 1) if u not in occupied]


def rack_side_port_summary(
    snapshot: ProjectSnapshot,
    device_id: UUID,
    side: PortSide,
) -> tuple[int, int]:
    """(всего портов стороны, занятых кабелем)."""
    total = 0
    busy = 0
    for port in ports_for_device(snapshot, device_id):
        if port.side != side:
            continue
        total += 1
        if peer_port(snapshot, port.id) is not None:
            busy += 1
    return total, busy


def validate_rack_placement(
    snapshot: ProjectSnapshot,
    rack_id: UUID,
    rack_u: int,
    rack_u_height: int = 1,
    *,
    exclude_device_id: UUID | None = None,
) -> None:
    rack = next((r for r in snapshot.racks if r.id == rack_id), None)
    if rack is None:
        raise ValueError("Шкаф не найден")
    height = max(1, int(rack_u_height))
    start = int(rack_u)
    if start < 1:
        raise ValueError("Юнит должен быть ≥ 1")
    end = start + height - 1
    if end > int(rack.units):
        raise ValueError(f"Размещение U{start}–{end} выходит за высоту шкафа ({rack.units}U)")
    for other in devices_in_rack(snapshot, rack_id):
        if exclude_device_id is not None and other.id == exclude_device_id:
            continue
        other_rng = rack_u_range(other)
        if other_rng is None:
            continue
        o_start, o_end = other_rng
        if start <= o_end and end >= o_start:
            raise ValueError(
                f"Пересечение с «{other.hostname}» ({rack_placement_label(other)})"
            )


def set_device_rack_placement(
    snapshot: ProjectSnapshot,
    device_id: UUID,
    *,
    rack_id: UUID | None,
    rack_u: int | None,
    rack_u_height: int = 1,
    room_id: UUID | None = None,
) -> Device:
    device = next((d for d in snapshot.devices if d.id == device_id), None)
    if device is None:
        raise ValueError("Устройство не найдено")
    if rack_id is None:
        device.rack_id = None
        device.rack_u = None
        device.rack_u_height = 1
        if room_id is not None:
            device.room_id = room_id
        return device
    rack = next((r for r in snapshot.racks if r.id == rack_id), None)
    if rack is None:
        raise ValueError("Шкаф не найден")
    if room_id is not None and rack.room_id != room_id:
        raise ValueError("Шкаф не принадлежит выбранной комнате")
    if rack_u is None:
        device.room_id = rack.room_id
        device.rack_id = rack_id
        device.rack_u = None
        device.rack_u_height = 1
        return device
    validate_rack_placement(
        snapshot,
        rack_id,
        rack_u,
        rack_u_height,
        exclude_device_id=device_id,
    )
    device.room_id = rack.room_id
    device.rack_id = rack_id
    device.rack_u = int(rack_u)
    device.rack_u_height = max(1, int(rack_u_height))
    return device


def devices_for_location(
    snapshot: ProjectSnapshot,
    kind: str | None,
    location_id: UUID | None,
) -> list[Device]:
    """Устройства в зоне building/floor/room/rack."""
    if not kind or location_id is None:
        return list(snapshot.devices)
    kind_l = kind.lower()
    if kind_l == "rack":
        return devices_in_rack(snapshot, location_id)
    if kind_l == "room":
        return [d for d in snapshot.devices if d.room_id == location_id]
    if kind_l == "floor":
        room_ids = {r.id for r in snapshot.rooms if r.floor_id == location_id}
        return [d for d in snapshot.devices if d.room_id in room_ids]
    if kind_l == "building":
        floor_ids = {f.id for f in snapshot.floors if f.building_id == location_id}
        room_ids = {r.id for r in snapshot.rooms if r.floor_id in floor_ids}
        return [d for d in snapshot.devices if d.room_id in room_ids]
    return list(snapshot.devices)


def paired_port(snapshot: ProjectSnapshot, port: Port) -> Port | None:
    if port.side == PortSide.NONE or port.position <= 0:
        return None
    want = PortSide.REAR if port.side == PortSide.FRONT else PortSide.FRONT
    for other in snapshot.ports:
        if other.device_id != port.device_id or other.id == port.id:
            continue
        if other.side == want and other.position == port.position:
            return other
    return None


@dataclass(frozen=True)
class PatchPairInfo:
    position: int
    front: Port
    rear: Port
    front_peer_id: UUID | None
    rear_peer_id: UUID | None

    @property
    def status(self) -> str:
        f_busy = self.front_peer_id is not None
        r_busy = self.rear_peer_id is not None
        if f_busy and r_busy:
            return "through"
        if f_busy or r_busy:
            return "half"
        return "free"


PATCH_PAIR_STATUS_RU = {
    "free": "Свободна",
    "half": "Одна сторона",
    "through": "Проброс",
}


def patch_panel_pairs(snapshot: ProjectSnapshot, device_id: UUID) -> list[PatchPairInfo]:
    """Сквозные пары Front↔Rear патч-панели, по возрастанию position."""
    device = next((d for d in snapshot.devices if d.id == device_id), None)
    if device is None or device.role != DeviceRole.PATCH_PANEL:
        return []
    fronts = {
        p.position: p
        for p in ports_for_device(snapshot, device_id)
        if p.side == PortSide.FRONT and p.position > 0
    }
    rears = {
        p.position: p
        for p in ports_for_device(snapshot, device_id)
        if p.side == PortSide.REAR and p.position > 0
    }
    rows: list[PatchPairInfo] = []
    for pos in sorted(set(fronts) & set(rears)):
        front = fronts[pos]
        rear = rears[pos]
        fp = peer_port(snapshot, front.id)
        rp = peer_port(snapshot, rear.id)
        rows.append(
            PatchPairInfo(
                position=pos,
                front=front,
                rear=rear,
                front_peer_id=fp.id if fp is not None else None,
                rear_peer_id=rp.id if rp is not None else None,
            )
        )
    return rows


def patch_through_path_label(snapshot: ProjectSnapshot, pair: PatchPairInfo) -> str:
    """Путь A ↔ Front ↔ Rear ↔ B (или короче, если сторона свободна)."""
    parts: list[str] = []
    if pair.front_peer_id is not None:
        parts.append(port_endpoint_label(snapshot, pair.front_peer_id))
    parts.append(port_endpoint_label(snapshot, pair.front.id))
    parts.append(port_endpoint_label(snapshot, pair.rear.id))
    if pair.rear_peer_id is not None:
        parts.append(port_endpoint_label(snapshot, pair.rear_peer_id))
    return " ↔ ".join(parts)


def cable_path_label(snapshot: ProjectSnapshot, cable: Cable) -> str:
    """Конец A ↔ B; если конец на PP и пара с другой стороны занята — полный проброс."""
    for end_id in (cable.end_a_port_id, cable.end_b_port_id):
        port = next((p for p in snapshot.ports if p.id == end_id), None)
        if port is None:
            continue
        pair = paired_port(snapshot, port)
        if pair is None:
            continue
        far = peer_port(snapshot, pair.id)
        if far is None:
            continue
        near = peer_port(snapshot, port.id)
        # near — другая сторона текущего кабеля
        if near is None:
            continue
        return (
            f"{port_endpoint_label(snapshot, near.id)} ↔ "
            f"{port_endpoint_label(snapshot, port.id)} ↔ "
            f"{port_endpoint_label(snapshot, pair.id)} ↔ "
            f"{port_endpoint_label(snapshot, far.id)}"
        )
    return (
        f"{port_endpoint_label(snapshot, cable.end_a_port_id)} ↔ "
        f"{port_endpoint_label(snapshot, cable.end_b_port_id)}"
    )


def delete_device(snapshot: ProjectSnapshot, device_id: UUID) -> None:
    device = next((d for d in snapshot.devices if d.id == device_id), None)
    if device is None:
        return

    guests = vms_for_host(snapshot, device_id)
    if guests:
        names = ", ".join(d.hostname or str(d.id) for d in guests[:5])
        extra = f" и ещё {len(guests) - 5}" if len(guests) > 5 else ""
        raise ValueError(
            f"Нельзя удалить гипервизор: есть ВМ ({names}{extra}). "
            "Сначала удалите или перенесите виртуальные серверы."
        )

    port_ids = {p.id for p in snapshot.ports if p.device_id == device_id}
    lag_ids = {lag.id for lag in snapshot.lags if lag.device_id == device_id}
    vs_ids = {
        vs.id for vs in snapshot.virtual_switches if vs.host_device_id == device_id
    }
    for cable in list(snapshot.cables):
        touches = cable.end_a_port_id in port_ids or cable.end_b_port_id in port_ids
        if not touches:
            continue
        other_id = (
            cable.end_b_port_id
            if cable.end_a_port_id in port_ids
            else cable.end_a_port_id
        )
        if other_id not in port_ids:
            _release_port(snapshot, other_id)
        snapshot.cables.remove(cable)

    for port_id in port_ids:
        _clear_vnic_mappings_to_port(snapshot, port_id)

    pg_ids = {pg.id for pg in snapshot.port_groups if pg.vswitch_id in vs_ids}
    for port in snapshot.ports:
        if port.port_group_id in pg_ids:
            port.port_group_id = None
    snapshot.port_groups = [
        pg for pg in snapshot.port_groups if pg.vswitch_id not in vs_ids
    ]
    snapshot.virtual_switches = [
        vs for vs in snapshot.virtual_switches if vs.id not in vs_ids
    ]
    for vs in snapshot.virtual_switches:
        vs.uplink_port_ids = [pid for pid in vs.uplink_port_ids if pid not in port_ids]

    snapshot.ips = [
        ip
        for ip in snapshot.ips
        if ip.port_id not in port_ids and ip.lag_id not in lag_ids
    ]
    snapshot.lags = [lag for lag in snapshot.lags if lag.device_id != device_id]
    snapshot.ports = [p for p in snapshot.ports if p.device_id != device_id]
    snapshot.devices = [d for d in snapshot.devices if d.id != device_id]
    snapshot.topology_nodes = [n for n in snapshot.topology_nodes if n.device_id != device_id]
    snapshot.floor_plan_assets = [a for a in snapshot.floor_plan_assets if a.device_id != device_id]


def ports_for_device(snapshot: ProjectSnapshot, device_id: UUID) -> list[Port]:
    return [p for p in snapshot.ports if p.device_id == device_id]


def lags_for_device(snapshot: ProjectSnapshot, device_id: UUID) -> list[Lag]:
    return [lag for lag in snapshot.lags if lag.device_id == device_id]


def lag_for_port(snapshot: ProjectSnapshot, port_id: UUID) -> Lag | None:
    for lag in snapshot.lags:
        if port_id in lag.member_port_ids:
            return lag
    return None


def ips_for_lag(snapshot: ProjectSnapshot, lag_id: UUID) -> list[IpAddress]:
    return [ip for ip in snapshot.ips if ip.lag_id == lag_id]


def lag_member_labels(snapshot: ProjectSnapshot, lag: Lag) -> str:
    names: list[str] = []
    ports = {p.id: p for p in snapshot.ports}
    for port_id in lag.member_port_ids:
        port = ports.get(port_id)
        names.append(port.name if port else str(port_id)[:8])
    return "+".join(names) if names else "—"


def _validate_lag_members(
    snapshot: ProjectSnapshot,
    device_id: UUID,
    member_port_ids: list[UUID],
    *,
    exclude_lag_id: UUID | None = None,
) -> list[UUID]:
    unique: list[UUID] = []
    seen: set[UUID] = set()
    for port_id in member_port_ids:
        if port_id in seen:
            continue
        seen.add(port_id)
        unique.append(port_id)
    if len(unique) < 2:
        raise ValueError("В LAG нужно минимум два порта")
    for port_id in unique:
        port = _find_port(snapshot, port_id)
        if port.device_id != device_id:
            raise ValueError("Все порты LAG должны принадлежать одному устройству")
        other = lag_for_port(snapshot, port_id)
        if other is not None and other.id != exclude_lag_id:
            raise ValueError(f"Порт {port.name} уже в LAG «{other.name}»")
    return unique


def add_lag(
    snapshot: ProjectSnapshot,
    *,
    device_id: UUID,
    name: str,
    mode: LagMode | str,
    member_port_ids: list[UUID],
    notes: str = "",
    mac: str = "",
) -> Lag:
    site_id = _require_site(snapshot)
    if not any(d.id == device_id for d in snapshot.devices):
        raise ValueError("Устройство не найдено")
    mode_enum = mode if isinstance(mode, LagMode) else LagMode(str(mode))
    members = _validate_lag_members(snapshot, device_id, member_port_ids)
    lag = Lag(
        site_id=site_id,
        device_id=device_id,
        name=(name.strip() or "bond0"),
        mode=mode_enum,
        member_port_ids=members,
        notes=notes.strip(),
        mac=normalize_mac(mac),
    )
    snapshot.lags.append(lag)
    return lag


def update_lag(
    snapshot: ProjectSnapshot,
    lag_id: UUID,
    *,
    name: str | None = None,
    mode: LagMode | str | None = None,
    member_port_ids: list[UUID] | None = None,
    notes: str | None = None,
    mac: str | None = None,
) -> Lag:
    lag = next((item for item in snapshot.lags if item.id == lag_id), None)
    if lag is None:
        raise ValueError("LAG не найден")
    if name is not None:
        lag.name = name.strip() or lag.name
    if mode is not None:
        lag.mode = mode if isinstance(mode, LagMode) else LagMode(str(mode))
    if member_port_ids is not None:
        lag.member_port_ids = _validate_lag_members(
            snapshot,
            lag.device_id,
            member_port_ids,
            exclude_lag_id=lag.id,
        )
    if notes is not None:
        lag.notes = notes.strip()
    if mac is not None:
        lag.mac = normalize_mac(mac)
    return lag


def delete_lag(snapshot: ProjectSnapshot, lag_id: UUID) -> None:
    snapshot.ips = [ip for ip in snapshot.ips if ip.lag_id != lag_id]
    snapshot.lags = [lag for lag in snapshot.lags if lag.id != lag_id]


def device_location_label(snapshot: ProjectSnapshot, device_id: UUID) -> str:
    device = next((d for d in snapshot.devices if d.id == device_id), None)
    if device is None:
        return "—"
    parts: list[str] = []
    room = next((r for r in snapshot.rooms if r.id == device.room_id), None) if device.room_id else None
    rack = next((r for r in snapshot.racks if r.id == device.rack_id), None) if device.rack_id else None
    floor = None
    building = None
    if room is not None:
        floor = next((f for f in snapshot.floors if f.id == room.floor_id), None)
    if floor is not None:
        building = next((b for b in snapshot.buildings if b.id == floor.building_id), None)
    if building is not None:
        parts.append(building.name)
    if floor is not None:
        parts.append(floor.name)
    if room is not None:
        parts.append(room.name)
    if rack is not None:
        parts.append(rack.name)
        u_label = rack_placement_label(device)
        if u_label:
            parts.append(u_label)
    return " / ".join(parts) if parts else "—"


def _find_port(snapshot: ProjectSnapshot, port_id: UUID) -> Port:
    port = next((p for p in snapshot.ports if p.id == port_id), None)
    if port is None:
        raise ValueError("Порт не найден")
    return port


def cable_for_port(snapshot: ProjectSnapshot, port_id: UUID) -> Cable | None:
    return next(
        (
            c
            for c in snapshot.cables
            if c.end_a_port_id == port_id or c.end_b_port_id == port_id
        ),
        None,
    )


def peer_port(snapshot: ProjectSnapshot, port_id: UUID) -> Port | None:
    cable = cable_for_port(snapshot, port_id)
    if cable is None:
        return None
    other_id = cable.end_b_port_id if cable.end_a_port_id == port_id else cable.end_a_port_id
    return next((p for p in snapshot.ports if p.id == other_id), None)


def port_endpoint_label(snapshot: ProjectSnapshot, port_id: UUID) -> str:
    port = next((p for p in snapshot.ports if p.id == port_id), None)
    if port is None:
        return "?"
    device = next((d for d in snapshot.devices if d.id == port.device_id), None)
    host = device.hostname if device else "?"
    return f"{host} / {port.name}"


def _media_matches_kind(media: PortMedia, kind: CableKind) -> bool:
    if media == PortMedia.VIRTUAL:
        return False
    return media.value == kind.value


def _occupy_port(snapshot: ProjectSnapshot, port_id: UUID) -> None:
    port = _find_port(snapshot, port_id)
    if port.status == PortStatus.DISABLED:
        raise ValueError(f"Порт {port.name} отключён")
    if port.status == PortStatus.OCCUPIED or cable_for_port(snapshot, port_id):
        raise ValueError(f"Порт {port.name} уже занят")
    port.status = PortStatus.OCCUPIED


def _release_port(snapshot: ProjectSnapshot, port_id: UUID) -> None:
    port = next((p for p in snapshot.ports if p.id == port_id), None)
    if port is None:
        return
    if port.status == PortStatus.OCCUPIED:
        port.status = PortStatus.FREE


def add_cable(
    snapshot: ProjectSnapshot,
    end_a_port_id: UUID,
    end_b_port_id: UUID,
    *,
    label: str = "",
    kind: CableKind | str = CableKind.COPPER,
    category: CableCategory | str = CableCategory.OTHER,
    length_m: float | None = None,
    color: str = "",
    purpose: str = "",
    allow_media_mismatch: bool = False,
) -> Cable:
    if end_a_port_id == end_b_port_id:
        raise ValueError("Концы кабеля должны быть разными портами")

    site_id = _require_site(snapshot)
    kind_enum = kind if isinstance(kind, CableKind) else CableKind(str(kind))
    category_enum = (
        category if isinstance(category, CableCategory) else CableCategory(str(category))
    )

    port_a = _find_port(snapshot, end_a_port_id)
    port_b = _find_port(snapshot, end_b_port_id)

    if not allow_media_mismatch:
        if not _media_matches_kind(port_a.media, kind_enum):
            raise ValueError(
                f"Среда порта {port_a.name} ({port_a.media.value}) "
                f"не совпадает с видом кабеля ({kind_enum.value})"
            )
        if not _media_matches_kind(port_b.media, kind_enum):
            raise ValueError(
                f"Среда порта {port_b.name} ({port_b.media.value}) "
                f"не совпадает с видом кабеля ({kind_enum.value})"
            )

    _occupy_port(snapshot, end_a_port_id)
    try:
        _occupy_port(snapshot, end_b_port_id)
    except Exception:
        _release_port(snapshot, end_a_port_id)
        raise

    cable = Cable(
        site_id=site_id,
        label=label.strip(),
        kind=kind_enum,
        category=category_enum,
        length_m=length_m if length_m and length_m > 0 else None,
        end_a_port_id=end_a_port_id,
        end_b_port_id=end_b_port_id,
        color=(color or "").strip(),
        purpose=(purpose or "").strip(),
    )
    snapshot.cables.append(cable)
    return cable


def delete_cable(snapshot: ProjectSnapshot, cable_id: UUID) -> None:
    cable = next((c for c in snapshot.cables if c.id == cable_id), None)
    if cable is None:
        return
    _release_port(snapshot, cable.end_a_port_id)
    _release_port(snapshot, cable.end_b_port_id)
    snapshot.cables = [c for c in snapshot.cables if c.id != cable_id]
    snapshot.topology_links = [
        link for link in snapshot.topology_links if link.cable_id != cable_id
    ]


def restore_cable(snapshot: ProjectSnapshot, cable: Cable) -> Cable:
    """Вернуть ранее удалённый кабель (для Undo), с теми же UUID."""
    if any(c.id == cable.id for c in snapshot.cables):
        return cable
    if cable.end_a_port_id == cable.end_b_port_id:
        raise ValueError("Концы кабеля должны быть разными портами")
    _occupy_port(snapshot, cable.end_a_port_id)
    try:
        _occupy_port(snapshot, cable.end_b_port_id)
    except Exception:
        _release_port(snapshot, cable.end_a_port_id)
        raise
    snapshot.cables.append(cable)
    return cable


def update_cable(
    snapshot: ProjectSnapshot,
    cable_id: UUID,
    *,
    label: str | None = None,
    kind: CableKind | str | None = None,
    category: CableCategory | str | None = None,
    length_m: float | None = None,
    clear_length: bool = False,
    color: str | None = None,
    purpose: str | None = None,
) -> Cable:
    cable = next((c for c in snapshot.cables if c.id == cable_id), None)
    if cable is None:
        raise ValueError("Кабель не найден")
    if label is not None:
        cable.label = label.strip()
    if kind is not None:
        cable.kind = kind if isinstance(kind, CableKind) else CableKind(str(kind))
    if category is not None:
        cable.category = (
            category if isinstance(category, CableCategory) else CableCategory(str(category))
        )
    if clear_length:
        cable.length_m = None
    elif length_m is not None:
        cable.length_m = length_m if length_m > 0 else None
    if color is not None:
        cable.color = color.strip()
    if purpose is not None:
        cable.purpose = purpose.strip()
    return cable


def vlan_label(snapshot: ProjectSnapshot, vlan_id: UUID | None) -> str:
    if vlan_id is None:
        return "-"
    vlan = next((v for v in snapshot.vlans if v.id == vlan_id), None)
    if vlan is None:
        return "?"
    return f"{vlan.vlan_id}" + (f" {vlan.name}" if vlan.name else "")


def port_vlan_summary(snapshot: ProjectSnapshot, port: Port) -> str:
    if port.mode == PortMode.ACCESS:
        return f"A:{vlan_label(snapshot, port.access_vlan_id)}"
    native = vlan_label(snapshot, port.access_vlan_id)
    tagged_vlans = []
    for vlan_uuid in port.tagged_vlan_ids:
        vlan = next((v for v in snapshot.vlans if v.id == vlan_uuid), None)
        if vlan is not None:
            tagged_vlans.append(vlan)
    tagged_vlans.sort(key=lambda v: v.vlan_id)
    tagged_txt = ",".join(str(v.vlan_id) for v in tagged_vlans) if tagged_vlans else "-"
    return f"T:n={native};t={tagged_txt}"


def ips_for_port(snapshot: ProjectSnapshot, port_id: UUID) -> list[IpAddress]:
    return [ip for ip in snapshot.ips if ip.port_id == port_id]


def ip_label(ip: IpAddress) -> str:
    if ip.cidr:
        return f"{ip.address}/{ip.cidr}"
    return ip.address


def vrf_label(vrf: Vrf) -> str:
    if vrf.rd:
        return f"{vrf.name} ({vrf.rd})"
    return vrf.name or "—"


def add_vrf(
    snapshot: ProjectSnapshot,
    name: str,
    *,
    rd: str = "",
    description: str = "",
) -> Vrf:
    site_id = _require_site(snapshot)
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("Укажите имя VRF")
    key = cleaned.casefold()
    if any(v.name.casefold() == key for v in snapshot.vrfs):
        raise ValueError(f"VRF «{cleaned}» уже существует")
    vrf = Vrf(
        site_id=site_id,
        name=cleaned,
        rd=rd.strip(),
        description=description.strip(),
    )
    snapshot.vrfs.append(vrf)
    return vrf


def update_vrf(
    snapshot: ProjectSnapshot,
    vrf_id: UUID,
    *,
    name: str | None = None,
    rd: str | None = None,
    description: str | None = None,
) -> Vrf:
    vrf = next((v for v in snapshot.vrfs if v.id == vrf_id), None)
    if vrf is None:
        raise ValueError("VRF не найден")
    if name is not None:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("Укажите имя VRF")
        key = cleaned.casefold()
        if any(v.name.casefold() == key and v.id != vrf_id for v in snapshot.vrfs):
            raise ValueError(f"VRF «{cleaned}» уже существует")
        vrf.name = cleaned
    if rd is not None:
        vrf.rd = rd.strip()
    if description is not None:
        vrf.description = description.strip()
    return vrf


def delete_vrf(snapshot: ProjectSnapshot, vrf_id: UUID) -> None:
    if not any(v.id == vrf_id for v in snapshot.vrfs):
        raise ValueError("VRF не найден")
    # Отвязываем IP; уникальность в глобальном scope проверяем заранее.
    detached = [ip for ip in snapshot.ips if ip.vrf_id == vrf_id]
    for ip in detached:
        for other in snapshot.ips:
            if other.id == ip.id or other.vrf_id is not None:
                continue
            if other.address == ip.address:
                raise ValueError(
                    f"Нельзя удалить VRF: IP {ip.address} совпадёт с глобальным адресом"
                )
    for ip in detached:
        ip.vrf_id = None
    snapshot.vrfs = [v for v in snapshot.vrfs if v.id != vrf_id]


def add_vlan(
    snapshot: ProjectSnapshot,
    vlan_id: int,
    name: str = "",
    description: str = "",
) -> Vlan:
    site_id = _require_site(snapshot)
    if not 1 <= int(vlan_id) <= 4094:
        raise ValueError("VLAN ID должен быть в диапазоне 1–4094")
    if any(v.vlan_id == int(vlan_id) for v in snapshot.vlans):
        raise ValueError(f"VLAN {vlan_id} уже существует")
    vlan = Vlan(
        site_id=site_id,
        vlan_id=int(vlan_id),
        name=name.strip(),
        description=description.strip(),
    )
    snapshot.vlans.append(vlan)
    return vlan


def update_vlan(
    snapshot: ProjectSnapshot,
    vlan_uuid: UUID,
    *,
    vlan_id: int | None = None,
    name: str | None = None,
    description: str | None = None,
) -> Vlan:
    vlan = next((v for v in snapshot.vlans if v.id == vlan_uuid), None)
    if vlan is None:
        raise ValueError("VLAN не найден")
    if vlan_id is not None:
        if not 1 <= int(vlan_id) <= 4094:
            raise ValueError("VLAN ID должен быть в диапазоне 1–4094")
        if any(v.vlan_id == int(vlan_id) and v.id != vlan_uuid for v in snapshot.vlans):
            raise ValueError(f"VLAN {vlan_id} уже существует")
        vlan.vlan_id = int(vlan_id)
    if name is not None:
        vlan.name = name.strip()
    if description is not None:
        vlan.description = description.strip()
    return vlan


def delete_vlan(snapshot: ProjectSnapshot, vlan_uuid: UUID) -> None:
    for port in snapshot.ports:
        if port.access_vlan_id == vlan_uuid:
            port.access_vlan_id = None
        if vlan_uuid in port.tagged_vlan_ids:
            port.tagged_vlan_ids = [v for v in port.tagged_vlan_ids if v != vlan_uuid]
    for pg in snapshot.port_groups:
        if pg.vlan_id == vlan_uuid:
            pg.vlan_id = None
    snapshot.vlans = [v for v in snapshot.vlans if v.id != vlan_uuid]


def set_port_access_vlan(
    snapshot: ProjectSnapshot,
    port_id: UUID,
    vlan_uuid: UUID | None,
) -> Port:
    return set_port_network(
        snapshot,
        port_id,
        mode=PortMode.ACCESS,
        access_vlan_id=vlan_uuid,
        tagged_vlan_ids=[],
    )


def set_port_network(
    snapshot: ProjectSnapshot,
    port_id: UUID,
    *,
    mode: PortMode | str,
    access_vlan_id: UUID | None = None,
    tagged_vlan_ids: list[UUID] | None = None,
) -> Port:
    port = _find_port(snapshot, port_id)
    mode_enum = mode if isinstance(mode, PortMode) else PortMode(str(mode))
    known = {v.id for v in snapshot.vlans}
    if access_vlan_id is not None and access_vlan_id not in known:
        raise ValueError("Access/native VLAN не найден")

    tagged = list(dict.fromkeys(tagged_vlan_ids or []))
    for vlan_uuid in tagged:
        if vlan_uuid not in known:
            raise ValueError("Tagged VLAN не найден")
        if access_vlan_id is not None and vlan_uuid == access_vlan_id:
            raise ValueError("Native VLAN не должен дублироваться в tagged")

    # Стабильный порядок: по номеру VLAN.
    vlan_by_id = {v.id: v for v in snapshot.vlans}
    tagged.sort(key=lambda vid: vlan_by_id[vid].vlan_id)

    if mode_enum == PortMode.ACCESS:
        if tagged:
            raise ValueError("У access-порта не может быть tagged VLAN")
        port.mode = PortMode.ACCESS
        port.access_vlan_id = access_vlan_id
        port.tagged_vlan_ids = []
        return port

    port.mode = PortMode.TRUNK
    port.access_vlan_id = access_vlan_id
    port.tagged_vlan_ids = tagged
    return port


def _normalize_address(address: str) -> str:
    text = address.strip()
    if not text:
        raise ValueError("Укажите IP-адрес")
    try:
        return str(ipaddress.ip_address(text))
    except ValueError as exc:
        raise ValueError(f"Некорректный IP-адрес: {text}") from exc


def _normalize_cidr(cidr: str, address: str) -> str:
    text = cidr.strip().lstrip("/")
    if not text:
        return ""
    try:
        prefix = int(text)
    except ValueError as exc:
        raise ValueError("Префикс CIDR должен быть числом") from exc
    version = ipaddress.ip_address(address).version
    max_prefix = 32 if version == 4 else 128
    if not 0 <= prefix <= max_prefix:
        raise ValueError(f"Префикс CIDR должен быть 0–{max_prefix}")
    return str(prefix)


def _ensure_unique_ip(
    snapshot: ProjectSnapshot,
    address: str,
    *,
    vrf_id: UUID | None = None,
    exclude_id: UUID | None = None,
) -> None:
    for ip in snapshot.ips:
        if exclude_id is not None and ip.id == exclude_id:
            continue
        if ip.address == address and ip.vrf_id == vrf_id:
            scope = "в этом VRF" if vrf_id is not None else "в проекте (глобально)"
            raise ValueError(f"IP {address} уже используется {scope}")


def add_ip(
    snapshot: ProjectSnapshot,
    *,
    address: str,
    cidr: str = "",
    gateway: str = "",
    port_id: UUID | None = None,
    lag_id: UUID | None = None,
    vrf_id: UUID | None = None,
) -> IpAddress:
    site_id = _require_site(snapshot)
    if port_id is not None and lag_id is not None:
        raise ValueError("IP нельзя привязать и к порту, и к LAG одновременно")
    if port_id is not None:
        _find_port(snapshot, port_id)
    if lag_id is not None:
        if not any(lag.id == lag_id for lag in snapshot.lags):
            raise ValueError("LAG не найден")
    if vrf_id is not None and not any(v.id == vrf_id for v in snapshot.vrfs):
        raise ValueError("VRF не найден")
    normalized = _normalize_address(address)
    _ensure_unique_ip(snapshot, normalized, vrf_id=vrf_id)
    gw = gateway.strip()
    if gw:
        _normalize_address(gw)  # validate
    ip = IpAddress(
        site_id=site_id,
        port_id=port_id,
        lag_id=lag_id,
        vrf_id=vrf_id,
        address=normalized,
        cidr=_normalize_cidr(cidr, normalized),
        gateway=gw,
    )
    snapshot.ips.append(ip)
    return ip


def update_ip(
    snapshot: ProjectSnapshot,
    ip_id: UUID,
    *,
    address: str | None = None,
    cidr: str | None = None,
    gateway: str | None = None,
    port_id: UUID | None = None,
    lag_id: UUID | None = None,
    vrf_id: UUID | None = None,
    clear_port: bool = False,
    clear_lag: bool = False,
    clear_vrf: bool = False,
) -> IpAddress:
    ip = next((item for item in snapshot.ips if item.id == ip_id), None)
    if ip is None:
        raise ValueError("IP-адрес не найден")
    next_vrf = ip.vrf_id
    if clear_vrf:
        next_vrf = None
    elif vrf_id is not None:
        if not any(v.id == vrf_id for v in snapshot.vrfs):
            raise ValueError("VRF не найден")
        next_vrf = vrf_id
    if address is not None:
        normalized = _normalize_address(address)
        _ensure_unique_ip(snapshot, normalized, vrf_id=next_vrf, exclude_id=ip_id)
        ip.address = normalized
    elif next_vrf != ip.vrf_id:
        _ensure_unique_ip(snapshot, ip.address, vrf_id=next_vrf, exclude_id=ip_id)
    ip.vrf_id = next_vrf
    if cidr is not None:
        ip.cidr = _normalize_cidr(cidr, ip.address)
    if gateway is not None:
        gw = gateway.strip()
        if gw:
            _normalize_address(gw)
        ip.gateway = gw
    if clear_port:
        ip.port_id = None
    elif port_id is not None:
        _find_port(snapshot, port_id)
        ip.port_id = port_id
        ip.lag_id = None
    if clear_lag:
        ip.lag_id = None
    elif lag_id is not None:
        if not any(lag.id == lag_id for lag in snapshot.lags):
            raise ValueError("LAG не найден")
        ip.lag_id = lag_id
        ip.port_id = None
    if ip.port_id is not None and ip.lag_id is not None:
        raise ValueError("IP нельзя привязать и к порту, и к LAG одновременно")
    return ip


def delete_ip(snapshot: ProjectSnapshot, ip_id: UUID) -> None:
    snapshot.ips = [ip for ip in snapshot.ips if ip.id != ip_id]
