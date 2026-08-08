from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from landesigner.domain.entities import ProjectSnapshot
from landesigner.domain.enums import PortStatus
from landesigner.services import floor_plan as fp
from landesigner.services import inventory as inv


class IssueSeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


# Стабильные машинные коды → подписи для UI
ISSUE_CODE_LABELS: dict[str, str] = {
    "duplicate_ip": "Дублирующий IP",
    "occupied_without_cable": "Занят без кабеля",
    "free_with_cable": "Свободен, но есть кабель",
    "cable_missing_port": "Кабель без порта",
    "cable_no_label": "Кабель без метки",
    "media_kind_mismatch": "Несовпадение среды и кабеля",
    "device_off_topology": "Нет на схеме",
    "device_off_floor_plan": "Нет на плане этажа",
    "lag_incomplete_links": "LAG без двух кабелей",
}


def issue_code_label(code: str) -> str:
    return ISSUE_CODE_LABELS.get(code, code)


@dataclass(frozen=True)
class ValidationIssue:
    severity: IssueSeverity
    code: str
    message: str
    entity_kind: str = ""
    entity_id: UUID | None = None

    @property
    def code_label(self) -> str:
        return issue_code_label(self.code)


def validate_project(snapshot: ProjectSnapshot) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    issues.extend(_check_duplicate_ips(snapshot))
    issues.extend(_check_dangling_ports(snapshot))
    issues.extend(_check_cable_integrity(snapshot))
    issues.extend(_check_cables_without_labels(snapshot))
    issues.extend(_check_media_kind(snapshot))
    issues.extend(_check_devices_off_topology(snapshot))
    issues.extend(_check_devices_off_floor_plan(snapshot))
    issues.extend(_check_lag_links(snapshot))
    return issues


def summary(issues: list[ValidationIssue]) -> dict[str, int]:
    return {
        "errors": sum(1 for i in issues if i.severity == IssueSeverity.ERROR),
        "warnings": sum(1 for i in issues if i.severity == IssueSeverity.WARNING),
        "infos": sum(1 for i in issues if i.severity == IssueSeverity.INFO),
        "total": len(issues),
    }


def _check_duplicate_ips(snapshot: ProjectSnapshot) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    by_addr: dict[str, list] = {}
    for ip in snapshot.ips:
        key = ip.address.strip().casefold()
        if not key:
            continue
        by_addr.setdefault(key, []).append(ip)
    for key, group in by_addr.items():
        if len(group) < 2:
            continue
        hosts = ", ".join(
            inv.port_endpoint_label(snapshot, ip.port_id) if ip.port_id else "—"
            for ip in group
        )
        issues.append(
            ValidationIssue(
                IssueSeverity.ERROR,
                "duplicate_ip",
                f"Дублирующий IP {group[0].address}: {hosts}",
                entity_kind="ip",
                entity_id=group[0].id,
            )
        )
    return issues


def _check_dangling_ports(snapshot: ProjectSnapshot) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for port in snapshot.ports:
        cable = inv.cable_for_port(snapshot, port.id)
        label = inv.port_endpoint_label(snapshot, port.id)
        if port.status == PortStatus.OCCUPIED and cable is None:
            issues.append(
                ValidationIssue(
                    IssueSeverity.ERROR,
                    "occupied_without_cable",
                    f"Порт занят без кабеля: {label}",
                    entity_kind="port",
                    entity_id=port.id,
                )
            )
        elif port.status == PortStatus.FREE and cable is not None:
            issues.append(
                ValidationIssue(
                    IssueSeverity.ERROR,
                    "free_with_cable",
                    f"Порт свободен, но есть кабель: {label}",
                    entity_kind="port",
                    entity_id=port.id,
                )
            )
    return issues


def _check_cable_integrity(snapshot: ProjectSnapshot) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    port_ids = {p.id for p in snapshot.ports}
    for cable in snapshot.cables:
        if cable.end_a_port_id not in port_ids or cable.end_b_port_id not in port_ids:
            issues.append(
                ValidationIssue(
                    IssueSeverity.ERROR,
                    "cable_missing_port",
                    f"Кабель «{cable.label or cable.id}» ссылается на отсутствующий порт",
                    entity_kind="cable",
                    entity_id=cable.id,
                )
            )
    return issues


def _check_cables_without_labels(snapshot: ProjectSnapshot) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for cable in snapshot.cables:
        if cable.label.strip():
            continue
        ends = (
            f"{inv.port_endpoint_label(snapshot, cable.end_a_port_id)} ↔ "
            f"{inv.port_endpoint_label(snapshot, cable.end_b_port_id)}"
        )
        issues.append(
            ValidationIssue(
                IssueSeverity.WARNING,
                "cable_no_label",
                f"Кабель без метки: {ends}",
                entity_kind="cable",
                entity_id=cable.id,
            )
        )
    return issues


def _check_media_kind(snapshot: ProjectSnapshot) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    ports = {p.id: p for p in snapshot.ports}
    for cable in snapshot.cables:
        a = ports.get(cable.end_a_port_id)
        b = ports.get(cable.end_b_port_id)
        if a is None or b is None:
            continue
        for port in (a, b):
            if port.media.value != cable.kind.value:
                issues.append(
                    ValidationIssue(
                        IssueSeverity.WARNING,
                        "media_kind_mismatch",
                        f"Среда порта {inv.port_endpoint_label(snapshot, port.id)} "
                        f"({port.media.value}) не совпадает с кабелем ({cable.kind.value})",
                        entity_kind="cable",
                        entity_id=cable.id,
                    )
                )
    return issues


def _check_devices_off_topology(snapshot: ProjectSnapshot) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    on_schema = {n.device_id for n in snapshot.topology_nodes}
    # Если узлов ещё нет совсем — не шумим INFO по каждому устройству после ensure.
    # Сообщаем только когда схема уже начата (есть хотя бы один узел) или всегда INFO?
    # По плану: «устройства вне схемы» — INFO/WARNING для устройств без узла.
    for device in snapshot.devices:
        if device.id in on_schema:
            continue
        issues.append(
            ValidationIssue(
                IssueSeverity.INFO,
                "device_off_topology",
                f"Устройство не на схеме: {device.hostname or device.id}",
                entity_kind="device",
                entity_id=device.id,
            )
        )
    return issues


def _check_devices_off_floor_plan(snapshot: ProjectSnapshot) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for device in snapshot.devices:
        if device.room_id is None:
            continue
        room = next((r for r in snapshot.rooms if r.id == device.room_id), None)
        if room is None:
            continue
        if fp.asset_for_device(snapshot, room.floor_id, device.id) is not None:
            continue
        issues.append(
            ValidationIssue(
                IssueSeverity.INFO,
                "device_off_floor_plan",
                f"Устройство не на плане этажа: {device.hostname or device.id}",
                entity_kind="device",
                entity_id=device.id,
            )
        )
    return issues


def _check_lag_links(snapshot: ProjectSnapshot) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for lag in snapshot.lags:
        linked = sum(
            1
            for port_id in lag.member_port_ids
            if inv.cable_for_port(snapshot, port_id) is not None
        )
        if linked >= 2:
            continue
        device = next((d for d in snapshot.devices if d.id == lag.device_id), None)
        host = device.hostname if device else "?"
        issues.append(
            ValidationIssue(
                IssueSeverity.INFO,
                "lag_incomplete_links",
                f"LAG «{lag.name}» на {host}: занято кабелями {linked} из "
                f"{len(lag.member_port_ids)} портов",
                entity_kind="lag",
                entity_id=lag.id,
            )
        )
    return issues
