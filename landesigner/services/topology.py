from __future__ import annotations

import math
from uuid import UUID

from landesigner.domain.entities import (
    ProjectSnapshot,
    TopologyLink,
    TopologyNode,
)
from landesigner.services import inventory as inv

# Шаг сетки авторазмещения новых узлов (логические единицы сцены).
LAYOUT_STEP_X = 220.0
LAYOUT_STEP_Y = 140.0
LAYOUT_COLS = 4
LAYOUT_ORIGIN_X = 80.0
LAYOUT_ORIGIN_Y = 80.0


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
    node.x = float(x)
    node.y = float(y)
    return node


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
    """Короткая подпись линии на схеме: метка + имена портов."""
    cable = next((c for c in snapshot.cables if c.id == cable_id), None)
    if cable is None:
        return ""
    port_a = next((p for p in snapshot.ports if p.id == cable.end_a_port_id), None)
    port_b = next((p for p in snapshot.ports if p.id == cable.end_b_port_id), None)
    ends = f"{port_a.name if port_a else '?'} ↔ {port_b.name if port_b else '?'}"
    label = cable.label.strip() if cable.label else ""
    if label:
        return f"{label}\n{ends}"
    return ends


def distance(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(bx - ax, by - ay)


def restore_topology_link(snapshot: ProjectSnapshot, link: TopologyLink) -> TopologyLink:
    if any(existing.id == link.id for existing in snapshot.topology_links):
        return link
    snapshot.topology_links.append(link)
    return link
