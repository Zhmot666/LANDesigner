from __future__ import annotations

import ipaddress
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
    ProjectSnapshot,
    Rack,
    Room,
    Vlan,
)
from landesigner.domain.enums import (
    CableCategory,
    CableKind,
    DeviceRole,
    LagMode,
    PortMedia,
    PortMode,
    PortStatus,
)


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
        for i in range(start, start + count):
            template.append({"name": f"{prefix}{i}", "media": media, "speed": speed})
    if not template:
        template = [{"name": "Gi1/0/1", "media": PortMedia.COPPER.value, "speed": 1000}]
    return template


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
        ports.append(
            Port(
                device_id=device_id,
                name=str(item.get("name", "port")),
                speed=int(item.get("speed", 1000)),
                media=media,
                status=PortStatus.FREE,
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
        port.media = media if isinstance(media, PortMedia) else PortMedia(str(media))
    return port


def add_port(
    snapshot: ProjectSnapshot,
    device_id: UUID,
    name: str,
    *,
    speed: int = 1000,
    media: PortMedia | str = PortMedia.COPPER,
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
    port = Port(
        device_id=device_id,
        name=cleaned,
        speed=int(speed),
        media=media_enum,
        status=PortStatus.FREE,
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
    cable = cable_for_port(snapshot, port_id)
    if cable is not None:
        delete_cable(snapshot, cable.id)
    snapshot.ips = [ip for ip in snapshot.ips if ip.port_id != port_id]
    snapshot.ports = [p for p in snapshot.ports if p.id != port_id]


def add_device(
    snapshot: ProjectSnapshot,
    device_type_id: UUID,
    hostname: str,
    serial: str = "",
    inventory_tag: str = "",
    room_id: UUID | None = None,
    rack_id: UUID | None = None,
) -> Device:
    site_id = _require_site(snapshot)
    device_type = next((dt for dt in snapshot.device_types if dt.id == device_type_id), None)
    if device_type is None:
        raise ValueError("Тип устройства не найден")

    device = Device(
        site_id=site_id,
        device_type_id=device_type.id,
        hostname=hostname.strip() or "устройство",
        serial=serial.strip(),
        inventory_tag=inventory_tag.strip(),
        role=device_type.role,
        room_id=room_id,
        rack_id=rack_id,
    )
    snapshot.devices.append(device)
    snapshot.ports.extend(_ports_from_template(device.id, device_type.port_template))
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
    clear_room: bool = False,
    clear_rack: bool = False,
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
    if clear_room:
        device.room_id = None
    elif room_id is not None:
        device.room_id = room_id
    if clear_rack:
        device.rack_id = None
    elif rack_id is not None:
        device.rack_id = rack_id
    return device


def delete_device(snapshot: ProjectSnapshot, device_id: UUID) -> None:
    device = next((d for d in snapshot.devices if d.id == device_id), None)
    if device is None:
        return

    port_ids = {p.id for p in snapshot.ports if p.device_id == device_id}
    lag_ids = {lag.id for lag in snapshot.lags if lag.device_id == device_id}
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
    exclude_id: UUID | None = None,
) -> None:
    for ip in snapshot.ips:
        if exclude_id is not None and ip.id == exclude_id:
            continue
        if ip.address == address:
            raise ValueError(f"IP {address} уже используется в проекте")


def add_ip(
    snapshot: ProjectSnapshot,
    *,
    address: str,
    cidr: str = "",
    gateway: str = "",
    port_id: UUID | None = None,
    lag_id: UUID | None = None,
) -> IpAddress:
    site_id = _require_site(snapshot)
    if port_id is not None and lag_id is not None:
        raise ValueError("IP нельзя привязать и к порту, и к LAG одновременно")
    if port_id is not None:
        _find_port(snapshot, port_id)
    if lag_id is not None:
        if not any(lag.id == lag_id for lag in snapshot.lags):
            raise ValueError("LAG не найден")
    normalized = _normalize_address(address)
    _ensure_unique_ip(snapshot, normalized)
    gw = gateway.strip()
    if gw:
        _normalize_address(gw)  # validate
    ip = IpAddress(
        site_id=site_id,
        port_id=port_id,
        lag_id=lag_id,
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
    clear_port: bool = False,
    clear_lag: bool = False,
) -> IpAddress:
    ip = next((item for item in snapshot.ips if item.id == ip_id), None)
    if ip is None:
        raise ValueError("IP-адрес не найден")
    if address is not None:
        normalized = _normalize_address(address)
        _ensure_unique_ip(snapshot, normalized, exclude_id=ip_id)
        ip.address = normalized
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
