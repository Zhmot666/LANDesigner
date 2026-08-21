from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable
from uuid import UUID

from landesigner.domain.entities import (
    Building,
    Cable,
    Device,
    DeviceType,
    Floor,
    FloorPlanAsset,
    IpAddress,
    Lag,
    Port,
    PortGroup,
    ProjectMeta,
    ProjectSnapshot,
    Rack,
    Room,
    Site,
    TopologyLink,
    TopologyNode,
    VirtualSwitch,
    Vlan,
    Vrf,
    utcnow,
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

FORMAT_MAGIC = "#LANDESIGNER_CSV"
FORMAT_VERSION = 1

SECTION_ORDER = (
    "meta",
    "sites",
    "buildings",
    "floors",
    "rooms",
    "racks",
    "device_types",
    "devices",
    "vlans",
    "vrfs",
    "ports",
    "cables",
    "lags",
    "lag_members",
    "virtual_switches",
    "vswitch_uplinks",
    "port_groups",
    "ips",
    "topology_nodes",
    "topology_links",
    "floor_plan_assets",
)


class CsvFormatError(ValueError):
    """Некорректный файл LanDesigner CSV."""


def export_snapshot(snapshot: ProjectSnapshot, path: str | Path) -> None:
    path = Path(path)
    path.write_text(export_to_text(snapshot), encoding="utf-8-sig")


def import_snapshot(path: str | Path) -> ProjectSnapshot:
    text = Path(path).read_text(encoding="utf-8-sig")
    return import_from_text(text)


def export_to_text(snapshot: ProjectSnapshot) -> str:
    buf = io.StringIO(newline="")
    buf.write(f"{FORMAT_MAGIC};version={FORMAT_VERSION}\n")
    for name in SECTION_ORDER:
        rows = _section_rows(snapshot, name)
        buf.write(f"#section={name}\n")
        if not rows:
            # Пустая секция всё равно с заголовком — проще для round-trip и ручного редактирования.
            writer = csv.DictWriter(buf, fieldnames=_headers_for(name), lineterminator="\n")
            writer.writeheader()
            continue
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return buf.getvalue()


def import_from_text(text: str) -> ProjectSnapshot:
    lines = text.splitlines()
    if not lines:
        raise CsvFormatError("Пустой CSV")

    first = lines[0].strip()
    if not first.startswith(FORMAT_MAGIC):
        raise CsvFormatError(
            f"Ожидался заголовок {FORMAT_MAGIC};version=N, получено: {first!r}"
        )
    version = _parse_version(first)
    if version != FORMAT_VERSION:
        raise CsvFormatError(f"Неподдерживаемая версия CSV: {version}")

    sections = _parse_sections(lines[1:])
    missing = [name for name in ("meta", "sites") if name not in sections]
    if missing:
        raise CsvFormatError(f"Нет обязательных секций: {', '.join(missing)}")

    meta = _load_meta(sections.get("meta", []))
    sites = [_load_site(r, meta.id) for r in sections.get("sites", [])]
    if not sites:
        raise CsvFormatError("Секция sites пуста")

    buildings = [_load_building(r) for r in sections.get("buildings", [])]
    floors = [_load_floor(r) for r in sections.get("floors", [])]
    rooms = [_load_room(r) for r in sections.get("rooms", [])]
    racks = [_load_rack(r) for r in sections.get("racks", [])]
    device_types = [_load_device_type(r) for r in sections.get("device_types", [])]
    devices = [_load_device(r) for r in sections.get("devices", [])]
    vlans = [_load_vlan(r) for r in sections.get("vlans", [])]
    vrfs = [_load_vrf(r) for r in sections.get("vrfs", [])]
    ports = [_load_port(r) for r in sections.get("ports", [])]
    cables = [_load_cable(r) for r in sections.get("cables", [])]
    lags = _load_lags(sections.get("lags", []), sections.get("lag_members", []))
    virtual_switches = _load_virtual_switches(
        sections.get("virtual_switches", []),
        sections.get("vswitch_uplinks", []),
    )
    port_groups = [_load_port_group(r) for r in sections.get("port_groups", [])]
    ips = [_load_ip(r) for r in sections.get("ips", [])]
    topology_nodes = [_load_topology_node(r) for r in sections.get("topology_nodes", [])]
    topology_links = [_load_topology_link(r) for r in sections.get("topology_links", [])]
    floor_plan_assets = [
        _load_floor_plan_asset(r) for r in sections.get("floor_plan_assets", [])
    ]

    return ProjectSnapshot(
        meta=meta,
        sites=sites,
        buildings=buildings,
        floors=floors,
        rooms=rooms,
        racks=racks,
        device_types=device_types,
        devices=devices,
        ports=ports,
        cables=cables,
        vlans=vlans,
        vrfs=vrfs,
        lags=lags,
        virtual_switches=virtual_switches,
        port_groups=port_groups,
        ips=ips,
        topology_nodes=topology_nodes,
        topology_links=topology_links,
        floor_plan_assets=floor_plan_assets,
    )


def _parse_version(header: str) -> int:
    parts = header.split(";")
    for part in parts[1:]:
        key, _, value = part.partition("=")
        if key.strip() == "version":
            try:
                return int(value.strip())
            except ValueError as exc:
                raise CsvFormatError(f"Некорректная version: {value!r}") from exc
    raise CsvFormatError("В заголовке нет version=")


def _parse_sections(lines: Iterable[str]) -> dict[str, list[dict[str, str]]]:
    sections: dict[str, list[dict[str, str]]] = {}
    current: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer, current
        if current is None:
            buffer = []
            return
        body = "\n".join(buffer).strip("\n")
        buffer = []
        if not body.strip():
            sections[current] = []
            return
        reader = csv.DictReader(io.StringIO(body))
        rows: list[dict[str, str]] = []
        for raw in reader:
            if raw is None:
                continue
            # Пропускаем полностью пустые строки.
            if not any((v or "").strip() for v in raw.values()):
                continue
            rows.append({k: (v if v is not None else "") for k, v in raw.items() if k})
        sections[current] = rows

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#section="):
            flush()
            current = stripped.split("=", 1)[1].strip()
            if not current:
                raise CsvFormatError("Пустое имя секции")
            continue
        if stripped.startswith("#") and current is None:
            continue
        if current is None:
            if stripped:
                raise CsvFormatError(f"Данные вне секции: {stripped!r}")
            continue
        buffer.append(line)
    flush()
    return sections


def _headers_for(section: str) -> list[str]:
    mapping = {
        "meta": ["id", "name", "schema_version", "origin", "revision", "updated_at"],
        "sites": ["id", "name", "address", "notes"],
        "buildings": ["id", "site_id", "name", "address", "notes"],
        "floors": [
            "id",
            "building_id",
            "name",
            "level",
            "plan_image_relpath",
            "scale_m_per_px",
        ],
        "rooms": ["id", "floor_id", "name"],
        "racks": ["id", "room_id", "name", "units", "unit_start", "unit_end"],
        "device_types": ["id", "site_id", "vendor", "model", "role", "port_template_json"],
        "devices": [
            "id",
            "site_id",
            "device_type_id",
            "hostname",
            "serial",
            "inventory_tag",
            "role",
            "room_id",
            "rack_id",
            "rack_u",
            "rack_u_height",
            "host_device_id",
        ],
        "vlans": ["id", "site_id", "vlan_id", "name", "description"],
        "vrfs": ["id", "site_id", "name", "rd", "description"],
        "ports": [
            "id",
            "device_id",
            "name",
            "speed",
            "media",
            "status",
            "mode",
            "access_vlan_id",
            "tagged_vlan_ids",
            "mac",
            "side",
            "position",
            "host_port_id",
            "port_group_id",
        ],
        "cables": [
            "id",
            "site_id",
            "label",
            "kind",
            "category",
            "length_m",
            "end_a_port_id",
            "end_b_port_id",
            "color",
            "purpose",
        ],
        "lags": ["id", "site_id", "device_id", "name", "mode", "notes", "mac"],
        "lag_members": ["lag_id", "port_id"],
        "virtual_switches": [
            "id",
            "site_id",
            "host_device_id",
            "name",
            "notes",
        ],
        "vswitch_uplinks": ["vswitch_id", "port_id"],
        "port_groups": ["id", "vswitch_id", "name", "vlan_id", "notes"],
        "ips": [
            "id",
            "site_id",
            "port_id",
            "lag_id",
            "vrf_id",
            "address",
            "cidr",
            "gateway",
        ],
        "topology_nodes": ["id", "site_id", "device_id", "x", "y"],
        "topology_links": [
            "id",
            "site_id",
            "topology_node_a_id",
            "topology_node_b_id",
            "cable_id",
        ],
        "floor_plan_assets": ["id", "floor_id", "device_id", "x", "y", "rotation"],
    }
    return mapping[section]


def _section_rows(snapshot: ProjectSnapshot, name: str) -> list[dict[str, str]]:
    if name == "meta":
        m = snapshot.meta
        return [
            {
                "id": str(m.id),
                "name": m.name,
                "schema_version": str(m.schema_version),
                "origin": m.origin,
                "revision": str(m.revision),
                "updated_at": m.updated_at.isoformat(),
            }
        ]
    if name == "sites":
        return [
            {
                "id": str(s.id),
                "name": s.name,
                "address": s.address,
                "notes": s.notes,
            }
            for s in snapshot.sites
        ]
    if name == "buildings":
        return [
            {
                "id": str(b.id),
                "site_id": str(b.site_id),
                "name": b.name,
                "address": b.address,
                "notes": b.notes,
            }
            for b in snapshot.buildings
        ]
    if name == "floors":
        return [
            {
                "id": str(f.id),
                "building_id": str(f.building_id),
                "name": f.name,
                "level": _fmt_float(f.level),
                "plan_image_relpath": f.plan_image_relpath,
                "scale_m_per_px": _fmt_float(f.scale_m_per_px),
            }
            for f in snapshot.floors
        ]
    if name == "rooms":
        return [
            {"id": str(r.id), "floor_id": str(r.floor_id), "name": r.name}
            for r in snapshot.rooms
        ]
    if name == "racks":
        return [
            {
                "id": str(r.id),
                "room_id": str(r.room_id),
                "name": r.name,
                "units": str(r.units),
                "unit_start": str(r.unit_start),
                "unit_end": str(r.unit_end),
            }
            for r in snapshot.racks
        ]
    if name == "device_types":
        return [
            {
                "id": str(dt.id),
                "site_id": str(dt.site_id),
                "vendor": dt.vendor,
                "model": dt.model,
                "role": dt.role.value,
                "port_template_json": json.dumps(dt.port_template, ensure_ascii=False),
            }
            for dt in snapshot.device_types
        ]
    if name == "devices":
        return [
            {
                "id": str(d.id),
                "site_id": str(d.site_id),
                "device_type_id": str(d.device_type_id),
                "hostname": d.hostname,
                "serial": d.serial,
                "inventory_tag": d.inventory_tag,
                "role": d.role.value,
                "room_id": _opt_uuid(d.room_id),
                "rack_id": _opt_uuid(d.rack_id),
                "rack_u": "" if d.rack_u is None else str(d.rack_u),
                "rack_u_height": str(d.rack_u_height or 1),
                "host_device_id": _opt_uuid(d.host_device_id),
            }
            for d in snapshot.devices
        ]
    if name == "vlans":
        return [
            {
                "id": str(v.id),
                "site_id": str(v.site_id),
                "vlan_id": str(v.vlan_id),
                "name": v.name,
                "description": v.description,
            }
            for v in snapshot.vlans
        ]
    if name == "vrfs":
        return [
            {
                "id": str(v.id),
                "site_id": str(v.site_id),
                "name": v.name,
                "rd": v.rd,
                "description": v.description,
            }
            for v in snapshot.vrfs
        ]
    if name == "ports":
        return [
            {
                "id": str(p.id),
                "device_id": str(p.device_id),
                "name": p.name,
                "speed": str(p.speed),
                "media": p.media.value,
                "status": p.status.value,
                "mode": p.mode.value,
                "access_vlan_id": _opt_uuid(p.access_vlan_id),
                "tagged_vlan_ids": ";".join(str(v) for v in p.tagged_vlan_ids),
                "mac": p.mac,
                "side": p.side.value,
                "position": str(p.position or 0),
                "host_port_id": _opt_uuid(p.host_port_id),
                "port_group_id": _opt_uuid(p.port_group_id),
            }
            for p in snapshot.ports
        ]
    if name == "cables":
        return [
            {
                "id": str(c.id),
                "site_id": str(c.site_id),
                "label": c.label,
                "kind": c.kind.value,
                "category": c.category.value,
                "length_m": "" if c.length_m is None else _fmt_float(c.length_m),
                "end_a_port_id": str(c.end_a_port_id),
                "end_b_port_id": str(c.end_b_port_id),
                "color": c.color,
                "purpose": c.purpose,
            }
            for c in snapshot.cables
        ]
    if name == "lags":
        return [
            {
                "id": str(lag.id),
                "site_id": str(lag.site_id),
                "device_id": str(lag.device_id),
                "name": lag.name,
                "mode": lag.mode.value,
                "notes": lag.notes,
                "mac": lag.mac,
            }
            for lag in snapshot.lags
        ]
    if name == "lag_members":
        return [
            {"lag_id": str(lag.id), "port_id": str(port_id)}
            for lag in snapshot.lags
            for port_id in lag.member_port_ids
        ]
    if name == "virtual_switches":
        return [
            {
                "id": str(vs.id),
                "site_id": str(vs.site_id),
                "host_device_id": str(vs.host_device_id),
                "name": vs.name,
                "notes": vs.notes,
            }
            for vs in snapshot.virtual_switches
        ]
    if name == "vswitch_uplinks":
        return [
            {"vswitch_id": str(vs.id), "port_id": str(port_id)}
            for vs in snapshot.virtual_switches
            for port_id in vs.uplink_port_ids
        ]
    if name == "port_groups":
        return [
            {
                "id": str(pg.id),
                "vswitch_id": str(pg.vswitch_id),
                "name": pg.name,
                "vlan_id": _opt_uuid(pg.vlan_id),
                "notes": pg.notes,
            }
            for pg in snapshot.port_groups
        ]
    if name == "ips":
        return [
            {
                "id": str(ip.id),
                "site_id": str(ip.site_id),
                "port_id": _opt_uuid(ip.port_id),
                "lag_id": _opt_uuid(ip.lag_id),
                "vrf_id": _opt_uuid(ip.vrf_id),
                "address": ip.address,
                "cidr": ip.cidr,
                "gateway": ip.gateway,
            }
            for ip in snapshot.ips
        ]
    if name == "topology_nodes":
        return [
            {
                "id": str(n.id),
                "site_id": str(n.site_id),
                "device_id": str(n.device_id),
                "x": _fmt_float(n.x),
                "y": _fmt_float(n.y),
            }
            for n in snapshot.topology_nodes
        ]
    if name == "topology_links":
        return [
            {
                "id": str(link.id),
                "site_id": str(link.site_id),
                "topology_node_a_id": str(link.topology_node_a_id),
                "topology_node_b_id": str(link.topology_node_b_id),
                "cable_id": _opt_uuid(link.cable_id),
            }
            for link in snapshot.topology_links
        ]
    if name == "floor_plan_assets":
        return [
            {
                "id": str(a.id),
                "floor_id": str(a.floor_id),
                "device_id": str(a.device_id),
                "x": _fmt_float(a.x),
                "y": _fmt_float(a.y),
                "rotation": _fmt_float(a.rotation),
            }
            for a in snapshot.floor_plan_assets
        ]
    raise CsvFormatError(f"Неизвестная секция: {name}")


def _load_meta(rows: list[dict[str, str]]) -> ProjectMeta:
    if len(rows) != 1:
        raise CsvFormatError("Секция meta должна содержать ровно одну строку")
    row = rows[0]
    return ProjectMeta(
        id=_req_uuid(row, "id"),
        name=_get(row, "name") or "Проект",
        schema_version=_int(row, "schema_version", 1),
        origin=_get(row, "origin") or "local",
        revision=_int(row, "revision", 1),
        updated_at=_parse_dt(_get(row, "updated_at")) or utcnow(),
    )


def _load_site(row: dict[str, str], project_id: UUID) -> Site:
    return Site(
        id=_req_uuid(row, "id"),
        project_id=project_id,
        name=_get(row, "name") or "Площадка",
        address=_get(row, "address"),
        notes=_get(row, "notes"),
    )


def _load_building(row: dict[str, str]) -> Building:
    return Building(
        id=_req_uuid(row, "id"),
        site_id=_req_uuid(row, "site_id"),
        name=_get(row, "name") or "Здание",
        address=_get(row, "address"),
        notes=_get(row, "notes"),
    )


def _load_floor(row: dict[str, str]) -> Floor:
    return Floor(
        id=_req_uuid(row, "id"),
        building_id=_req_uuid(row, "building_id"),
        name=_get(row, "name") or "Этаж",
        level=_float(row, "level", 0.0),
        plan_image_relpath=_get(row, "plan_image_relpath"),
        scale_m_per_px=_float(row, "scale_m_per_px", 0.1),
    )


def _load_room(row: dict[str, str]) -> Room:
    return Room(
        id=_req_uuid(row, "id"),
        floor_id=_req_uuid(row, "floor_id"),
        name=_get(row, "name") or "Комната",
    )


def _load_rack(row: dict[str, str]) -> Rack:
    return Rack(
        id=_req_uuid(row, "id"),
        room_id=_req_uuid(row, "room_id"),
        name=_get(row, "name") or "Шкаф",
        units=_int(row, "units", 42),
        unit_start=_int(row, "unit_start", 1),
        unit_end=_int(row, "unit_end", 42),
    )


def _load_device_type(row: dict[str, str]) -> DeviceType:
    raw_template = _get(row, "port_template_json") or "[]"
    try:
        template = json.loads(raw_template)
    except json.JSONDecodeError as exc:
        raise CsvFormatError(f"Некорректный port_template_json: {exc}") from exc
    if not isinstance(template, list):
        raise CsvFormatError("port_template_json должен быть JSON-массивом")
    return DeviceType(
        id=_req_uuid(row, "id"),
        site_id=_req_uuid(row, "site_id"),
        vendor=_get(row, "vendor"),
        model=_get(row, "model"),
        role=_enum(DeviceRole, _get(row, "role"), DeviceRole.OTHER),
        port_template=template,
    )


def _load_device(row: dict[str, str]) -> Device:
    rack_u_raw = _get(row, "rack_u").strip()
    return Device(
        id=_req_uuid(row, "id"),
        site_id=_req_uuid(row, "site_id"),
        device_type_id=_req_uuid(row, "device_type_id"),
        hostname=_get(row, "hostname"),
        serial=_get(row, "serial"),
        inventory_tag=_get(row, "inventory_tag"),
        role=_enum(DeviceRole, _get(row, "role"), DeviceRole.OTHER),
        room_id=_opt_parse_uuid(_get(row, "room_id")),
        rack_id=_opt_parse_uuid(_get(row, "rack_id")),
        rack_u=int(rack_u_raw) if rack_u_raw else None,
        rack_u_height=max(1, _int(row, "rack_u_height", 1)),
        host_device_id=_opt_parse_uuid(_get(row, "host_device_id")),
    )


def _load_vlan(row: dict[str, str]) -> Vlan:
    return Vlan(
        id=_req_uuid(row, "id"),
        site_id=_req_uuid(row, "site_id"),
        vlan_id=_int(row, "vlan_id", 1),
        name=_get(row, "name"),
        description=_get(row, "description"),
    )


def _load_vrf(row: dict[str, str]) -> Vrf:
    return Vrf(
        id=_req_uuid(row, "id"),
        site_id=_req_uuid(row, "site_id"),
        name=_get(row, "name"),
        rd=_get(row, "rd"),
        description=_get(row, "description"),
    )


def _load_ip(row: dict[str, str]) -> IpAddress:
    return IpAddress(
        id=_req_uuid(row, "id"),
        site_id=_req_uuid(row, "site_id"),
        port_id=_opt_parse_uuid(_get(row, "port_id")),
        lag_id=_opt_parse_uuid(_get(row, "lag_id")),
        vrf_id=_opt_parse_uuid(_get(row, "vrf_id")),
        address=_get(row, "address"),
        cidr=_get(row, "cidr"),
        gateway=_get(row, "gateway"),
    )


def _load_port(row: dict[str, str]) -> Port:
    tagged_raw = _get(row, "tagged_vlan_ids")
    tagged = [
        UUID(part.strip())
        for part in tagged_raw.split(";")
        if part.strip()
    ]
    return Port(
        id=_req_uuid(row, "id"),
        device_id=_req_uuid(row, "device_id"),
        name=_get(row, "name"),
        speed=_int(row, "speed", 1000),
        media=_enum(PortMedia, _get(row, "media"), PortMedia.COPPER),
        status=_enum(PortStatus, _get(row, "status"), PortStatus.FREE),
        mode=_enum(PortMode, _get(row, "mode"), PortMode.ACCESS),
        access_vlan_id=_opt_parse_uuid(_get(row, "access_vlan_id")),
        tagged_vlan_ids=tagged,
        mac=_get(row, "mac"),
        side=_enum(PortSide, _get(row, "side"), PortSide.NONE),
        position=_int(row, "position", 0),
        host_port_id=_opt_parse_uuid(_get(row, "host_port_id")),
        port_group_id=_opt_parse_uuid(_get(row, "port_group_id")),
    )


def _load_cable(row: dict[str, str]) -> Cable:
    length_raw = _get(row, "length_m")
    length = None if not length_raw else float(length_raw.replace(",", "."))
    return Cable(
        id=_req_uuid(row, "id"),
        site_id=_req_uuid(row, "site_id"),
        label=_get(row, "label"),
        kind=_enum(CableKind, _get(row, "kind"), CableKind.COPPER),
        category=_enum(CableCategory, _get(row, "category"), CableCategory.OTHER),
        length_m=length,
        end_a_port_id=_req_uuid(row, "end_a_port_id"),
        end_b_port_id=_req_uuid(row, "end_b_port_id"),
        color=_get(row, "color"),
        purpose=_get(row, "purpose"),
    )


def _load_lags(
    lag_rows: list[dict[str, str]],
    member_rows: list[dict[str, str]],
) -> list[Lag]:
    members: dict[UUID, list[UUID]] = {}
    for row in member_rows:
        lag_id = _req_uuid(row, "lag_id")
        port_id = _req_uuid(row, "port_id")
        members.setdefault(lag_id, []).append(port_id)
    result: list[Lag] = []
    for row in lag_rows:
        lag_id = _req_uuid(row, "id")
        result.append(
            Lag(
                id=lag_id,
                site_id=_req_uuid(row, "site_id"),
                device_id=_req_uuid(row, "device_id"),
                name=_get(row, "name") or "bond0",
                mode=_enum(LagMode, _get(row, "mode"), LagMode.ACTIVE_BACKUP),
                notes=_get(row, "notes"),
                mac=_get(row, "mac"),
                member_port_ids=members.get(lag_id, []),
            )
        )
    return result


def _load_virtual_switches(
    vs_rows: list[dict[str, str]],
    uplink_rows: list[dict[str, str]],
) -> list[VirtualSwitch]:
    uplinks: dict[UUID, list[UUID]] = {}
    for row in uplink_rows:
        vs_id = _req_uuid(row, "vswitch_id")
        port_id = _req_uuid(row, "port_id")
        uplinks.setdefault(vs_id, []).append(port_id)
    result: list[VirtualSwitch] = []
    for row in vs_rows:
        vs_id = _req_uuid(row, "id")
        result.append(
            VirtualSwitch(
                id=vs_id,
                site_id=_req_uuid(row, "site_id"),
                host_device_id=_req_uuid(row, "host_device_id"),
                name=_get(row, "name") or "vSwitch0",
                notes=_get(row, "notes"),
                uplink_port_ids=uplinks.get(vs_id, []),
            )
        )
    return result


def _load_port_group(row: dict[str, str]) -> PortGroup:
    return PortGroup(
        id=_req_uuid(row, "id"),
        vswitch_id=_req_uuid(row, "vswitch_id"),
        name=_get(row, "name") or "VM Network",
        vlan_id=_opt_parse_uuid(_get(row, "vlan_id")),
        notes=_get(row, "notes"),
    )


def _load_topology_node(row: dict[str, str]) -> TopologyNode:
    return TopologyNode(
        id=_req_uuid(row, "id"),
        site_id=_req_uuid(row, "site_id"),
        device_id=_req_uuid(row, "device_id"),
        x=_float(row, "x", 0.0),
        y=_float(row, "y", 0.0),
    )


def _load_topology_link(row: dict[str, str]) -> TopologyLink:
    return TopologyLink(
        id=_req_uuid(row, "id"),
        site_id=_req_uuid(row, "site_id"),
        topology_node_a_id=_req_uuid(row, "topology_node_a_id"),
        topology_node_b_id=_req_uuid(row, "topology_node_b_id"),
        cable_id=_opt_parse_uuid(_get(row, "cable_id")),
    )


def _load_floor_plan_asset(row: dict[str, str]) -> FloorPlanAsset:
    return FloorPlanAsset(
        id=_req_uuid(row, "id"),
        floor_id=_req_uuid(row, "floor_id"),
        device_id=_req_uuid(row, "device_id"),
        x=_float(row, "x", 0.0),
        y=_float(row, "y", 0.0),
        rotation=_float(row, "rotation", 0.0),
    )


def _get(row: dict[str, str], key: str) -> str:
    return (row.get(key) or "").strip()


def _req_uuid(row: dict[str, str], key: str) -> UUID:
    value = _get(row, key)
    if not value:
        raise CsvFormatError(f"Поле {key} обязательно")
    try:
        return UUID(value)
    except ValueError as exc:
        raise CsvFormatError(f"Некорректный UUID в {key}: {value!r}") from exc


def _opt_parse_uuid(value: str) -> UUID | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError as exc:
        raise CsvFormatError(f"Некорректный UUID: {value!r}") from exc


def _opt_uuid(value: UUID | None) -> str:
    return "" if value is None else str(value)


def _int(row: dict[str, str], key: str, default: int) -> int:
    value = _get(row, key)
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise CsvFormatError(f"Некорректное целое в {key}: {value!r}") from exc


def _float(row: dict[str, str], key: str, default: float) -> float:
    value = _get(row, key)
    if not value:
        return default
    try:
        return float(value.replace(",", "."))
    except ValueError as exc:
        raise CsvFormatError(f"Некорректное число в {key}: {value!r}") from exc


def _fmt_float(value: float) -> str:
    text = f"{value:g}"
    return text


def _enum(enum_cls, value: str, default):
    value = (value or "").strip()
    if not value:
        return default
    try:
        return enum_cls(value)
    except ValueError as exc:
        raise CsvFormatError(f"Неизвестное значение {enum_cls.__name__}: {value!r}") from exc


def _parse_dt(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise CsvFormatError(f"Некорректная дата: {value!r}") from exc
