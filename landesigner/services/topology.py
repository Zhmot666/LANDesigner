from __future__ import annotations

import math
from uuid import UUID

from landesigner.domain.entities import (
    ProjectSnapshot,
    TopologyLink,
    TopologyNode,
)
from landesigner.domain.enums import DeviceRole, PortMode
from landesigner.services import inventory as inv

# Шаг сетки авторазмещения новых узлов (логические единицы сцены).
LAYOUT_STEP_X = 220.0
LAYOUT_STEP_Y = 140.0
LAYOUT_COLS = 4
LAYOUT_ORIGIN_X = 80.0
LAYOUT_ORIGIN_Y = 80.0
# Сетка редактора (совпадает с UI TopologyView.GRID).
SNAP_GRID = 20.0

_ROLE_LAYOUT_ORDER = {
    DeviceRole.ROUTER: 0,
    DeviceRole.FIREWALL: 1,
    DeviceRole.LOAD_BALANCER: 2,
    DeviceRole.MODEM: 3,
    DeviceRole.SWITCH: 4,
    DeviceRole.CONTROLLER: 5,
    DeviceRole.HYPERVISOR: 6,
    DeviceRole.SERVER: 7,
    DeviceRole.STORAGE: 8,
    DeviceRole.PATCH_PANEL: 9,
    DeviceRole.ODF: 10,
    DeviceRole.PDU: 11,
    DeviceRole.UPS: 12,
    DeviceRole.KVM: 13,
    DeviceRole.AP: 14,
    DeviceRole.NVR: 15,
    DeviceRole.VIRTUAL_MACHINE: 16,
    DeviceRole.WORKSTATION: 17,
    DeviceRole.IP_PHONE: 18,
    DeviceRole.PRINTER: 19,
    DeviceRole.OTHER: 20,
}


def snap_coord(value: float, grid: float = SNAP_GRID) -> float:
    if grid <= 0:
        return float(value)
    return round(float(value) / grid) * grid


def snap_point(x: float, y: float, grid: float = SNAP_GRID) -> tuple[float, float]:
    return snap_coord(x, grid), snap_coord(y, grid)


def ensure_topology(snapshot: ProjectSnapshot) -> bool:
    """
    Синхронизирует узлы/линки схемы с устройствами и кабелями.
    Возвращает True, если snapshot изменился.
    """
    changed = False
    changed = _sync_nodes(snapshot) or changed
    changed = _sync_links(snapshot) or changed
    return changed


def node_for_device(snapshot: ProjectSnapshot, device_id: UUID) -> TopologyNode | None:
    return next((n for n in snapshot.topology_nodes if n.device_id == device_id), None)


def link_for_cable(snapshot: ProjectSnapshot, cable_id: UUID) -> TopologyLink | None:
    return next((link for link in snapshot.topology_links if link.cable_id == cable_id), None)


def move_node(snapshot: ProjectSnapshot, node_id: UUID, x: float, y: float) -> TopologyNode:
    node = next((n for n in snapshot.topology_nodes if n.id == node_id), None)
    if node is None:
        raise ValueError("Узел схемы не найден")
    sx, sy = snap_point(x, y)
    node.x = sx
    node.y = sy
    return node


def auto_layout(snapshot: ProjectSnapshot) -> dict[UUID, tuple[float, float, float, float]]:
    """
    Переложить узлы по слоям (роль + связность) на сетке.
    Возвращает {node_id: (old_x, old_y, new_x, new_y)} только для изменившихся.
    """
    ensure_topology(snapshot)
    if not snapshot.topology_nodes:
        return {}

    # Степень связности по кабельным линкам.
    degree: dict[UUID, int] = {n.id: 0 for n in snapshot.topology_nodes}
    for link in snapshot.topology_links:
        if link.topology_node_a_id in degree:
            degree[link.topology_node_a_id] += 1
        if link.topology_node_b_id in degree:
            degree[link.topology_node_b_id] += 1

    devices = {d.id: d for d in snapshot.devices}

    def sort_key(node: TopologyNode) -> tuple:
        device = devices.get(node.device_id)
        role = device.role if device is not None else DeviceRole.OTHER
        host = (device.hostname if device is not None else "").casefold()
        return (
            _ROLE_LAYOUT_ORDER.get(role, 99),
            -degree.get(node.id, 0),
            host,
        )

    ordered = sorted(snapshot.topology_nodes, key=sort_key)
    # Ширина ряда зависит от числа узлов.
    cols = max(3, min(8, int(math.ceil(math.sqrt(len(ordered))))))
    changes: dict[UUID, tuple[float, float, float, float]] = {}
    for index, node in enumerate(ordered):
        col = index % cols
        row = index // cols
        new_x, new_y = snap_point(
            LAYOUT_ORIGIN_X + col * LAYOUT_STEP_X,
            LAYOUT_ORIGIN_Y + row * LAYOUT_STEP_Y,
        )
        old_x, old_y = float(node.x), float(node.y)
        if abs(old_x - new_x) > 0.01 or abs(old_y - new_y) > 0.01:
            changes[node.id] = (old_x, old_y, new_x, new_y)
            node.x = new_x
            node.y = new_y
    return changes


def apply_layout_positions(
    snapshot: ProjectSnapshot,
    positions: dict[UUID, tuple[float, float]],
) -> None:
    for node in snapshot.topology_nodes:
        if node.id not in positions:
            continue
        x, y = positions[node.id]
        node.x, node.y = snap_point(x, y)


def auto_layout_positions(count: int) -> list[tuple[float, float]]:
    positions: list[tuple[float, float]] = []
    for index in range(count):
        col = index % LAYOUT_COLS
        row = index // LAYOUT_COLS
        positions.append(
            (
                LAYOUT_ORIGIN_X + col * LAYOUT_STEP_X,
                LAYOUT_ORIGIN_Y + row * LAYOUT_STEP_Y,
            )
        )
    return positions


def next_free_position(snapshot: ProjectSnapshot) -> tuple[float, float]:
    occupied = {(round(n.x, 1), round(n.y, 1)) for n in snapshot.topology_nodes}
    index = 0
    while True:
        col = index % LAYOUT_COLS
        row = index // LAYOUT_COLS
        pos = (
            LAYOUT_ORIGIN_X + col * LAYOUT_STEP_X,
            LAYOUT_ORIGIN_Y + row * LAYOUT_STEP_Y,
        )
        key = (round(pos[0], 1), round(pos[1], 1))
        if key not in occupied:
            return pos
        index += 1
        if index > 10_000:
            # Запасной вариант — чуть сместить от последнего узла.
            if snapshot.topology_nodes:
                last = snapshot.topology_nodes[-1]
                return last.x + LAYOUT_STEP_X, last.y
            return LAYOUT_ORIGIN_X, LAYOUT_ORIGIN_Y


def _sync_nodes(snapshot: ProjectSnapshot) -> bool:
    changed = False
    device_ids = {d.id for d in snapshot.devices}
    before = len(snapshot.topology_nodes)
    snapshot.topology_nodes = [
        n for n in snapshot.topology_nodes if n.device_id in device_ids
    ]
    if len(snapshot.topology_nodes) != before:
        changed = True

    existing = {n.device_id for n in snapshot.topology_nodes}
    site_id = snapshot.sites[0].id if snapshot.sites else None
    for device in snapshot.devices:
        if device.id in existing:
            continue
        if site_id is None:
            site_id = device.site_id
        x, y = next_free_position(snapshot)
        x, y = snap_point(x, y)
        snapshot.topology_nodes.append(
            TopologyNode(
                site_id=device.site_id,
                device_id=device.id,
                x=x,
                y=y,
            )
        )
        changed = True
    return changed


def _sync_links(snapshot: ProjectSnapshot) -> bool:
    changed = False
    node_by_device = {n.device_id: n for n in snapshot.topology_nodes}
    cable_ids = {c.id for c in snapshot.cables}
    node_ids = {n.id for n in snapshot.topology_nodes}

    kept: list[TopologyLink] = []
    for link in snapshot.topology_links:
        if link.topology_node_a_id not in node_ids or link.topology_node_b_id not in node_ids:
            changed = True
            continue
        if link.cable_id is not None and link.cable_id not in cable_ids:
            changed = True
            continue
        kept.append(link)
    if len(kept) != len(snapshot.topology_links):
        changed = True
    snapshot.topology_links = kept

    existing_cable_links = {
        link.cable_id for link in snapshot.topology_links if link.cable_id is not None
    }
    port_to_device = {p.id: p.device_id for p in snapshot.ports}

    for cable in snapshot.cables:
        if cable.id in existing_cable_links:
            continue
        device_a = port_to_device.get(cable.end_a_port_id)
        device_b = port_to_device.get(cable.end_b_port_id)
        if device_a is None or device_b is None:
            continue
        node_a = node_by_device.get(device_a)
        node_b = node_by_device.get(device_b)
        if node_a is None or node_b is None:
            continue
        if node_a.id == node_b.id:
            # Петля на одном устройстве на схеме не рисуем.
            continue
        snapshot.topology_links.append(
            TopologyLink(
                site_id=cable.site_id,
                topology_node_a_id=node_a.id,
                topology_node_b_id=node_b.id,
                cable_id=cable.id,
            )
        )
        changed = True
    return changed


def endpoint_label(snapshot: ProjectSnapshot, cable_id: UUID) -> str:
    cable = next((c for c in snapshot.cables if c.id == cable_id), None)
    if cable is None:
        return ""
    a = inv.port_endpoint_label(snapshot, cable.end_a_port_id)
    b = inv.port_endpoint_label(snapshot, cable.end_b_port_id)
    label = cable.label.strip() if cable.label else ""
    if label:
        return f"{label}: {a} ↔ {b}"
    return f"{a} ↔ {b}"


def link_caption(snapshot: ProjectSnapshot, cable_id: UUID) -> str:
    """Подпись на схеме для одного кабеля — не используется (детали в tooltip)."""
    return ""


def bundle_caption(cable_count: int) -> str:
    """На схеме только счётчик при нескольких кабелях между парой устройств."""
    if cable_count > 1:
        return f"×{cable_count}"
    return ""


def link_tooltip(snapshot: ProjectSnapshot, cable_id: UUID) -> str:
    """Полная подсказка по одному кабелю."""
    cable = next((c for c in snapshot.cables if c.id == cable_id), None)
    if cable is None:
        return ""
    lines: list[str] = []
    label = (cable.label or "").strip()
    if label:
        lines.append(label)
    purpose = (cable.purpose or "").strip()
    if purpose and purpose.casefold() not in (label or "").casefold():
        lines.append(f"Назначение: {purpose}")
    a = inv.port_endpoint_label(snapshot, cable.end_a_port_id)
    b = inv.port_endpoint_label(snapshot, cable.end_b_port_id)
    lines.append(f"{a} ↔ {b}")
    if cable.color.strip():
        lines.append(f"Цвет: {cable.color.strip()}")
    if cable.length_m is not None:
        lines.append(f"Длина: {cable.length_m:g} м")
    meta = _link_meta_parts(snapshot, cable)
    if meta:
        lines.append(" · ".join(meta))
    return "\n".join(lines)


def bundle_tooltip(snapshot: ProjectSnapshot, cable_ids: list[UUID]) -> str:
    """Tooltip для линии-пучка: все кабели между парой устройств."""
    ids = [cid for cid in cable_ids if cid is not None]
    if not ids:
        return ""
    if len(ids) == 1:
        return link_tooltip(snapshot, ids[0])
    blocks: list[str] = [f"Кабелей между устройствами: {len(ids)}"]
    for index, cable_id in enumerate(ids, start=1):
        tip = link_tooltip(snapshot, cable_id)
        if not tip:
            tip = str(cable_id)
        blocks.append(f"—— {index} ——\n{tip}")
    return "\n".join(blocks)


def _link_meta_parts(snapshot: ProjectSnapshot, cable) -> list[str]:
    port_a = next((p for p in snapshot.ports if p.id == cable.end_a_port_id), None)
    port_b = next((p for p in snapshot.ports if p.id == cable.end_b_port_id), None)
    meta_parts: list[str] = []
    if port_a is not None and port_b is not None:
        speed = min(int(port_a.speed), int(port_b.speed))
        if speed > 0:
            if speed >= 1000 and speed % 1000 == 0:
                meta_parts.append(f"{speed // 1000}G")
            else:
                meta_parts.append(f"{speed}M")
    vlan_bits: list[str] = []
    for port in (port_a, port_b):
        if port is None:
            continue
        if port.mode == PortMode.TRUNK and port.tagged_vlan_ids:
            ids = []
            for vid in port.tagged_vlan_ids:
                vlan = next((v for v in snapshot.vlans if v.id == vid), None)
                if vlan is not None:
                    ids.append(str(vlan.vlan_id))
            if ids:
                vlan_bits.append("T:" + ",".join(ids[:4]) + ("…" if len(ids) > 4 else ""))
                continue
        if port.access_vlan_id is not None:
            vlan = next((v for v in snapshot.vlans if v.id == port.access_vlan_id), None)
            if vlan is not None:
                vlan_bits.append(f"V{vlan.vlan_id}")
    seen: set[str] = set()
    for bit in vlan_bits:
        if bit not in seen:
            seen.add(bit)
            meta_parts.append(bit)
    return meta_parts


def distance(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(bx - ax, by - ay)


def restore_topology_link(snapshot: ProjectSnapshot, link: TopologyLink) -> TopologyLink:
    if any(existing.id == link.id for existing in snapshot.topology_links):
        return link
    snapshot.topology_links.append(link)
    return link
