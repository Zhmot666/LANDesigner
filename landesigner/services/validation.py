from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from landesigner.domain.entities import ProjectSnapshot
from landesigner.domain.enums import DeviceRole, PortMedia, PortStatus
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
    "patch_pair_half_connected": "Пара патч-панели занята с одной стороны",
    "vm_missing_host": "ВМ без гипервизора",
    "vm_invalid_host": "ВМ: некорректный хост",
    "host_on_non_vm": "Хост у не-ВМ",
    "vm_in_rack": "ВМ в шкафу",
    "vnic_missing_host_nic": "vNIC без привязки",
    "vnic_invalid_host_nic": "vNIC: некорректный NIC хоста",
    "vnic_invalid_port_group": "vNIC: некорректный Port Group",
    "vswitch_no_uplink": "vSwitch без uplink",
    "port_group_orphan": "Port Group без vSwitch",
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
    issues.extend(_check_patch_panel_pairs(snapshot))
    issues.extend(_check_virtual_machines(snapshot))
    issues.extend(_check_vswitches(snapshot))
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


def _check_patch_panel_pairs(snapshot: ProjectSnapshot) -> list[ValidationIssue]:
    """Предупреждение: у сквозной пары Front/Rear кабель только с одной стороны."""
    issues: list[ValidationIssue] = []
    seen: set[tuple[UUID, int]] = set()
    for port in snapshot.ports:
        pair = inv.paired_port(snapshot, port)
        if pair is None:
            continue
        key = (port.device_id, port.position)
        if key in seen:
            continue
        seen.add(key)
        cable_a = inv.cable_for_port(snapshot, port.id)
        cable_b = inv.cable_for_port(snapshot, pair.id)
        if (cable_a is None) == (cable_b is None):
            continue
        connected = port if cable_a is not None else pair
        free = pair if cable_a is not None else port
        label_c = inv.port_endpoint_label(snapshot, connected.id)
        label_f = inv.port_endpoint_label(snapshot, free.id)
        issues.append(
            ValidationIssue(
                IssueSeverity.WARNING,
                "patch_pair_half_connected",
                f"Пара патч-панели: кабель только на {label_c}, свободен {label_f}",
                entity_kind="port",
                entity_id=connected.id,
            )
        )
    return issues


def _check_virtual_machines(snapshot: ProjectSnapshot) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    devices_by_id = {d.id: d for d in snapshot.devices}
    for device in snapshot.devices:
        name = device.hostname or str(device.id)
        if device.role == DeviceRole.VIRTUAL_MACHINE:
            host = None
            if device.host_device_id is None:
                issues.append(
                    ValidationIssue(
                        IssueSeverity.ERROR,
                        "vm_missing_host",
                        f"ВМ «{name}» без гипервизора",
                        entity_kind="device",
                        entity_id=device.id,
                    )
                )
            else:
                host = devices_by_id.get(device.host_device_id)
                if host is None:
                    issues.append(
                        ValidationIssue(
                            IssueSeverity.ERROR,
                            "vm_invalid_host",
                            f"ВМ «{name}»: гипервизор не найден",
                            entity_kind="device",
                            entity_id=device.id,
                        )
                    )
                elif host.role != DeviceRole.HYPERVISOR:
                    issues.append(
                        ValidationIssue(
                            IssueSeverity.ERROR,
                            "vm_invalid_host",
                            f"ВМ «{name}»: хост «{host.hostname}» не гипервизор",
                            entity_kind="device",
                            entity_id=device.id,
                        )
                    )
                elif host.site_id != device.site_id:
                    issues.append(
                        ValidationIssue(
                            IssueSeverity.ERROR,
                            "vm_invalid_host",
                            f"ВМ «{name}»: гипервизор на другой площадке",
                            entity_kind="device",
                            entity_id=device.id,
                        )
                    )
            if device.rack_id is not None:
                issues.append(
                    ValidationIssue(
                        IssueSeverity.WARNING,
                        "vm_in_rack",
                        f"ВМ «{name}» не должна быть в шкафу",
                        entity_kind="device",
                        entity_id=device.id,
                    )
                )
            for port in inv.ports_for_device(snapshot, device.id):
                if port.media != PortMedia.VIRTUAL:
                    continue
                if port.port_group_id is not None:
                    pg = next(
                        (item for item in snapshot.port_groups if item.id == port.port_group_id),
                        None,
                    )
                    if pg is None:
                        issues.append(
                            ValidationIssue(
                                IssueSeverity.ERROR,
                                "vnic_invalid_port_group",
                                f"ВМ «{name}»: vNIC «{port.name}» — Port Group не найден",
                                entity_kind="port",
                                entity_id=port.id,
                            )
                        )
                        continue
                    vs = next(
                        (item for item in snapshot.virtual_switches if item.id == pg.vswitch_id),
                        None,
                    )
                    if vs is None or host is None or vs.host_device_id != host.id:
                        issues.append(
                            ValidationIssue(
                                IssueSeverity.ERROR,
                                "vnic_invalid_port_group",
                                f"ВМ «{name}»: vNIC «{port.name}» — Port Group не на хосте ВМ",
                                entity_kind="port",
                                entity_id=port.id,
                            )
                        )
                    continue
                if port.host_port_id is None:
                    issues.append(
                        ValidationIssue(
                            IssueSeverity.WARNING,
                            "vnic_missing_host_nic",
                            f"ВМ «{name}»: vNIC «{port.name}» без Port Group / NIC хоста",
                            entity_kind="port",
                            entity_id=port.id,
                        )
                    )
                    continue
                host_port = next(
                    (p for p in snapshot.ports if p.id == port.host_port_id),
                    None,
                )
                if host_port is None:
                    issues.append(
                        ValidationIssue(
                            IssueSeverity.ERROR,
                            "vnic_invalid_host_nic",
                            f"ВМ «{name}»: vNIC «{port.name}» — NIC хоста не найден",
                            entity_kind="port",
                            entity_id=port.id,
                        )
                    )
                elif host is None or host_port.device_id != host.id:
                    issues.append(
                        ValidationIssue(
                            IssueSeverity.ERROR,
                            "vnic_invalid_host_nic",
                            f"ВМ «{name}»: vNIC «{port.name}» привязан к чужому NIC",
                            entity_kind="port",
                            entity_id=port.id,
                        )
                    )
                elif host_port.media == PortMedia.VIRTUAL:
                    issues.append(
                        ValidationIssue(
                            IssueSeverity.ERROR,
                            "vnic_invalid_host_nic",
                            f"ВМ «{name}»: vNIC «{port.name}» — NIC хоста виртуальный",
                            entity_kind="port",
                            entity_id=port.id,
                        )
                    )
        elif device.host_device_id is not None:
            issues.append(
                ValidationIssue(
                    IssueSeverity.WARNING,
                    "host_on_non_vm",
                    f"Устройство «{name}» не ВМ, но указан гипервизор",
                    entity_kind="device",
                    entity_id=device.id,
                )
            )
    return issues


def _check_vswitches(snapshot: ProjectSnapshot) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    vs_ids = {vs.id for vs in snapshot.virtual_switches}
    for vs in snapshot.virtual_switches:
        host = next((d for d in snapshot.devices if d.id == vs.host_device_id), None)
        host_name = host.hostname if host is not None else "?"
        if not vs.uplink_port_ids:
            issues.append(
                ValidationIssue(
                    IssueSeverity.WARNING,
                    "vswitch_no_uplink",
                    f"vSwitch «{vs.name}» на {host_name} без uplink NIC",
                    entity_kind="virtual_switch",
                    entity_id=vs.id,
                )
            )
        if host is None or host.role != DeviceRole.HYPERVISOR:
            issues.append(
                ValidationIssue(
                    IssueSeverity.ERROR,
                    "vswitch_no_uplink",
                    f"vSwitch «{vs.name}»: хост не гипервизор",
                    entity_kind="virtual_switch",
                    entity_id=vs.id,
                )
            )
    for pg in snapshot.port_groups:
        if pg.vswitch_id not in vs_ids:
            issues.append(
                ValidationIssue(
                    IssueSeverity.ERROR,
                    "port_group_orphan",
                    f"Port Group «{pg.name}» без vSwitch",
                    entity_kind="port_group",
                    entity_id=pg.id,
                )
            )
    return issues
