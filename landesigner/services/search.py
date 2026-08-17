from __future__ import annotations

from landesigner.domain.entities import (
    Cable,
    Device,
    DeviceType,
    IpAddress,
    Port,
    ProjectSnapshot,
    Vlan,
)
from landesigner.services import inventory as inv
from landesigner.ui.labels import (
    cable_category_label,
    cable_kind_label,
    media_label,
    role_label,
    status_label,
)


def normalize_query(query: str) -> str:
    return query.casefold().strip()


def matches(query: str, *parts: object) -> bool:
    """Подстрока без учёта регистра по любому из текстовых полей."""
    q = normalize_query(query)
    if not q:
        return True
    haystack = " ".join(str(p) for p in parts if p is not None and str(p)).casefold()
    return q in haystack


def filter_device_types(types: list[DeviceType], query: str) -> list[DeviceType]:
    return [
        dt
        for dt in types
        if matches(query, dt.vendor, dt.model, role_label(dt.role), len(dt.port_template))
    ]


def filter_devices(
    snapshot: ProjectSnapshot,
    devices: list[Device],
    types_by_id: dict,
    query: str,
) -> list[Device]:
    result: list[Device] = []
    for device in devices:
        dt = types_by_id.get(device.device_type_id)
        type_txt = f"{dt.vendor} {dt.model}" if dt else ""
        # Также ищем по IP/портам устройства
        port_bits: list[str] = []
        for port in inv.ports_for_device(snapshot, device.id):
            port_bits.append(port.name)
            if port.mac:
                port_bits.append(port.mac)
                port_bits.append("".join(ch for ch in port.mac if ch.isalnum()))
            port_bits.append(inv.port_vlan_summary(snapshot, port))
            for ip in inv.ips_for_port(snapshot, port.id):
                port_bits.append(inv.ip_label(ip))
                port_bits.append(ip.gateway)
        for lag in inv.lags_for_device(snapshot, device.id):
            port_bits.append(lag.name)
            if lag.mac:
                port_bits.append(lag.mac)
                port_bits.append("".join(ch for ch in lag.mac if ch.isalnum()))
        host = inv.host_for_device(snapshot, device)
        host_name = host.hostname if host is not None else ""
        if matches(
            query,
            device.hostname,
            device.serial,
            device.inventory_tag,
            role_label(device.role),
            type_txt,
            host_name,
            *port_bits,
        ):
            result.append(device)
    return result


def filter_cables(snapshot: ProjectSnapshot, cables: list[Cable], query: str) -> list[Cable]:
    return [
        c
        for c in cables
        if matches(
            query,
            c.label,
            cable_kind_label(c.kind),
            cable_category_label(c.category),
            c.length_m,
            inv.port_endpoint_label(snapshot, c.end_a_port_id),
            inv.port_endpoint_label(snapshot, c.end_b_port_id),
        )
    ]


def filter_vlans(vlans: list[Vlan], query: str) -> list[Vlan]:
    return [v for v in vlans if matches(query, v.vlan_id, v.name, v.description)]


def filter_ips(snapshot: ProjectSnapshot, ips: list[IpAddress], query: str) -> list[IpAddress]:
    return [
        ip
        for ip in ips
        if matches(
            query,
            ip.address,
            ip.cidr,
            ip.gateway,
            inv.port_endpoint_label(snapshot, ip.port_id) if ip.port_id else "",
        )
    ]


def filter_ports(snapshot: ProjectSnapshot, ports: list[Port], query: str) -> list[Port]:
    result: list[Port] = []
    for port in ports:
        peer = inv.peer_port(snapshot, port.id)
        link = inv.port_endpoint_label(snapshot, peer.id) if peer else ""
        ips = inv.ips_for_port(snapshot, port.id)
        ip_txt = ", ".join(inv.ip_label(ip) for ip in ips)
        bits = [
            port.name,
            port.mac,
            "".join(ch for ch in port.mac if ch.isalnum()) if port.mac else "",
            port.speed,
            media_label(port.media),
            status_label(port.status),
            link,
            inv.port_vlan_summary(snapshot, port),
            ip_txt,
        ]
        if matches(query, *bits):
            result.append(port)
    return result
