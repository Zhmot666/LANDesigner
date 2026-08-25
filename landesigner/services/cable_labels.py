"""Смешанная автогенерация меток и назначений кабелей."""

from __future__ import annotations

import re
from uuid import UUID

from landesigner.domain.entities import ProjectSnapshot
from landesigner.domain.enums import DeviceRole
from landesigner.services import inventory as inv

_CAB_SEQ_RE = re.compile(r"^CAB-(\d+)", re.IGNORECASE)


def max_cable_sequence(snapshot: ProjectSnapshot) -> int:
    max_n = 0
    for cable in snapshot.cables:
        match = _CAB_SEQ_RE.match(cable.label.strip())
        if match is not None:
            max_n = max(max_n, int(match.group(1)))
    return max_n


def next_cable_sequence(snapshot: ProjectSnapshot) -> int:
    return max_cable_sequence(snapshot) + 1


def endpoint_pair_label(snapshot: ProjectSnapshot, port_a_id: UUID, port_b_id: UUID) -> str:
    a = inv.port_endpoint_label(snapshot, port_a_id)
    b = inv.port_endpoint_label(snapshot, port_b_id)
    left, right = sorted((a, b), key=str.casefold)
    return f"{left} ↔ {right}"


def suggest_cable_purpose(
    snapshot: ProjectSnapshot,
    port_a_id: UUID,
    port_b_id: UUID,
) -> str:
    role_a = _role_for_port(snapshot, port_a_id)
    role_b = _role_for_port(snapshot, port_b_id)
    roles = {role_a, role_b}

    if DeviceRole.FIREWALL in roles and roles & {DeviceRole.MODEM, DeviceRole.OTHER, DeviceRole.ROUTER}:
        if role_a != role_b:
            return "WAN"

    if DeviceRole.ROUTER in roles and DeviceRole.MODEM in roles:
        return "WAN"

    if DeviceRole.PATCH_PANEL in roles:
        other = role_b if role_a == DeviceRole.PATCH_PANEL else role_a
        if other == DeviceRole.WORKSTATION:
            return "рабочее место"
        if other in {
            DeviceRole.SWITCH,
            DeviceRole.ROUTER,
            DeviceRole.FIREWALL,
            DeviceRole.AP,
            DeviceRole.CONTROLLER,
        }:
            return "инфраструктура"
        if other in {DeviceRole.SERVER, DeviceRole.HYPERVISOR, DeviceRole.STORAGE}:
            return "сервер"

    if DeviceRole.SWITCH in roles and roles == {DeviceRole.SWITCH}:
        return "uplink"

    if DeviceRole.SWITCH in roles and roles & {
        DeviceRole.SERVER,
        DeviceRole.HYPERVISOR,
        DeviceRole.STORAGE,
        DeviceRole.VIRTUAL_MACHINE,
    }:
        return "сервер"

    if DeviceRole.AP in roles:
        return "Wi‑Fi"

    if DeviceRole.IP_PHONE in roles:
        return "телефон"

    if DeviceRole.PRINTER in roles:
        return "принтер"

    if DeviceRole.ODF in roles:
        return "оптика"

    return ""


def suggest_cable_label(
    snapshot: ProjectSnapshot,
    port_a_id: UUID,
    port_b_id: UUID,
    *,
    purpose: str = "",
    seq: int | None = None,
    exclude_cable_id: UUID | None = None,
) -> str:
    if seq is None:
        seq = next_cable_sequence(snapshot)
    ends = endpoint_pair_label(snapshot, port_a_id, port_b_id)
    body = f"{purpose.strip()}: {ends}" if purpose.strip() else ends
    base = f"CAB-{seq:04d} · {body}"
    return _ensure_unique_label(snapshot, base, exclude_cable_id=exclude_cable_id)


def suggest_cable_fields(
    snapshot: ProjectSnapshot,
    port_a_id: UUID,
    port_b_id: UUID,
    *,
    exclude_cable_id: UUID | None = None,
    seq: int | None = None,
) -> tuple[str, str]:
    purpose = suggest_cable_purpose(snapshot, port_a_id, port_b_id)
    label = suggest_cable_label(
        snapshot,
        port_a_id,
        port_b_id,
        purpose=purpose,
        seq=seq,
        exclude_cable_id=exclude_cable_id,
    )
    return label, purpose


def apply_if_missing(
    snapshot: ProjectSnapshot,
    port_a_id: UUID,
    port_b_id: UUID,
    label: str,
    purpose: str,
) -> tuple[str, str]:
    """Подставить метку/назначение, если пользователь оставил поля пустыми."""
    purpose_out = purpose.strip()
    if not purpose_out:
        purpose_out = suggest_cable_purpose(snapshot, port_a_id, port_b_id)
    label_out = label.strip()
    if not label_out:
        label_out = suggest_cable_label(
            snapshot,
            port_a_id,
            port_b_id,
            purpose=purpose_out,
        )
    return label_out, purpose_out


def fill_missing_cable_labels(snapshot: ProjectSnapshot) -> int:
    """Заполнить метки (и пустые назначения) у кабелей без метки. Возвращает число изменённых."""
    count = 0
    for cable in snapshot.cables:
        if cable.label.strip():
            continue
        purpose = cable.purpose.strip() or suggest_cable_purpose(
            snapshot, cable.end_a_port_id, cable.end_b_port_id
        )
        if not cable.purpose.strip() and purpose:
            cable.purpose = purpose
        cable.label = suggest_cable_label(
            snapshot,
            cable.end_a_port_id,
            cable.end_b_port_id,
            purpose=purpose,
            exclude_cable_id=cable.id,
        )
        count += 1
    return count


def _role_for_port(snapshot: ProjectSnapshot, port_id: UUID) -> DeviceRole:
    port = next((p for p in snapshot.ports if p.id == port_id), None)
    if port is None:
        return DeviceRole.OTHER
    device = next((d for d in snapshot.devices if d.id == port.device_id), None)
    if device is None:
        return DeviceRole.OTHER
    return device.role


def _ensure_unique_label(
    snapshot: ProjectSnapshot,
    label: str,
    *,
    exclude_cable_id: UUID | None = None,
) -> str:
    existing = {
        c.label.strip().casefold()
        for c in snapshot.cables
        if c.id != exclude_cable_id and c.label.strip()
    }
    candidate = label.strip()
    if candidate.casefold() not in existing:
        return candidate
    suffix = 2
    while f"{candidate} #{suffix}".casefold() in existing:
        suffix += 1
    return f"{candidate} #{suffix}"
