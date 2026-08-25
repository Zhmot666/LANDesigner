from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from landesigner.domain.entities import ProjectSnapshot
from landesigner.domain.enums import RackMountFace
from landesigner.services import inventory as inv
from landesigner.ui.labels import (
    cable_category_label,
    cable_kind_label,
    media_label,
    role_label,
    status_label,
)


class ReportKind(StrEnum):
    DEVICES = "devices"
    PORTS = "ports"
    CABLES = "cables"
    VLANS = "vlans"
    VRFS = "vrfs"
    RACKS = "racks"
    GXP_IQ = "gxp_iq"
    CHANGE_LOG = "change_log"


REPORT_TITLES: dict[ReportKind, str] = {
    ReportKind.DEVICES: "Реестр оборудования",
    ReportKind.PORTS: "Порт-матрица",
    ReportKind.CABLES: "Кабели",
    ReportKind.VLANS: "VLAN map",
    ReportKind.VRFS: "VRF / IP scope",
    ReportKind.RACKS: "Шкафы / юниты",
    ReportKind.GXP_IQ: "GxP Infrastructure IQ (черновик)",
    ReportKind.CHANGE_LOG: "Журнал изменений",
}


@dataclass(frozen=True)
class ReportTable:
    kind: ReportKind
    title: str
    headers: list[str]
    rows: list[list[str]]


def build_report(snapshot: ProjectSnapshot, kind: ReportKind) -> ReportTable:
    if kind == ReportKind.DEVICES:
        return _devices_report(snapshot)
    if kind == ReportKind.PORTS:
        return _ports_report(snapshot)
    if kind == ReportKind.CABLES:
        return _cables_report(snapshot)
    if kind == ReportKind.VLANS:
        return _vlans_report(snapshot)
    if kind == ReportKind.VRFS:
        return _vrfs_report(snapshot)
    if kind == ReportKind.RACKS:
        return _racks_report(snapshot)
    if kind == ReportKind.GXP_IQ:
        return _gxp_iq_report(snapshot)
    if kind == ReportKind.CHANGE_LOG:
        return _change_log_report(snapshot)
    raise ValueError(f"Неизвестный отчёт: {kind}")


def report_to_csv(table: ReportTable) -> str:
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(table.headers)
    writer.writerows(table.rows)
    return buf.getvalue()


def export_report_csv(table: ReportTable, path: str | Path) -> None:
    Path(path).write_text(report_to_csv(table), encoding="utf-8-sig")


def report_to_html(table: ReportTable, project_name: str = "") -> str:
    title = table.title
    if project_name:
        title = f"{project_name} — {title}"
    head = "".join(f"<th>{_esc(h)}</th>" for h in table.headers)
    body_rows = []
    for row in table.rows:
        cells = "".join(f"<td>{_esc(c)}</td>" for c in row)
        body_rows.append(f"<tr>{cells}</tr>")
    body = "\n".join(body_rows) or "<tr><td colspan='99'>Нет данных</td></tr>"
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>{_esc(title)}</title>
<style>
body {{ font-family: Segoe UI, sans-serif; color: #23313a; margin: 24px; }}
h1 {{ font-size: 18px; color: #2f7c85; }}
table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
th, td {{ border: 1px solid #d8e0e6; padding: 6px 8px; text-align: left; }}
th {{ background: #eef3f5; }}
</style></head>
<body>
<h1>{_esc(title)}</h1>
<table>
<thead><tr>{head}</tr></thead>
<tbody>
{body}
</tbody>
</table>
</body></html>
"""


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _devices_report(snapshot: ProjectSnapshot) -> ReportTable:
    types = {dt.id: dt for dt in snapshot.device_types}
    rooms = {r.id: r for r in snapshot.rooms}
    racks = {r.id: r for r in snapshot.racks}
    rows: list[list[str]] = []
    for d in sorted(snapshot.devices, key=lambda x: x.hostname.casefold()):
        dt = types.get(d.device_type_id)
        type_txt = f"{dt.vendor} {dt.model}".strip() if dt else ""
        room = rooms.get(d.room_id) if d.room_id else None
        rack = racks.get(d.rack_id) if d.rack_id else None
        u_label = inv.rack_placement_label(d) or ""
        rows.append(
            [
                d.hostname,
                d.serial,
                d.inventory_tag,
                role_label(d.role),
                type_txt,
                room.name if room else "",
                rack.name if rack else "",
                u_label,
                str(len(inv.ports_for_device(snapshot, d.id))),
            ]
        )
    return ReportTable(
        ReportKind.DEVICES,
        REPORT_TITLES[ReportKind.DEVICES],
        [
            "Имя хоста",
            "Серийный №",
            "Инв. №",
            "Роль",
            "Тип",
            "Комната",
            "Шкаф",
            "Юниты",
            "Портов",
        ],
        rows,
    )


def _ports_report(snapshot: ProjectSnapshot) -> ReportTable:
    devices = {d.id: d for d in snapshot.devices}
    rows: list[list[str]] = []
    for port in sorted(
        snapshot.ports,
        key=lambda p: (
            (devices.get(p.device_id).hostname if devices.get(p.device_id) else ""),
            p.name,
        ),
    ):
        device = devices.get(port.device_id)
        peer = inv.peer_port(snapshot, port.id)
        link = inv.port_endpoint_label(snapshot, peer.id) if peer else ""
        ips = ", ".join(inv.ip_label(ip) for ip in inv.ips_for_port(snapshot, port.id))
        rows.append(
            [
                device.hostname if device else "",
                port.name,
                port.mac,
                str(port.speed),
                media_label(port.media),
                status_label(port.status),
                port.mode.value,
                inv.port_vlan_summary(snapshot, port),
                ips,
                link,
            ]
        )
    return ReportTable(
        ReportKind.PORTS,
        REPORT_TITLES[ReportKind.PORTS],
        [
            "Устройство",
            "Порт",
            "MAC",
            "Скорость",
            "Среда",
            "Статус",
            "Режим",
            "VLAN",
            "IP",
            "Связь",
        ],
        rows,
    )


def _cables_report(snapshot: ProjectSnapshot) -> ReportTable:
    rows: list[list[str]] = []
    for cable in snapshot.cables:
        length = f"{cable.length_m:g}" if cable.length_m is not None else ""
        rows.append(
            [
                cable.label,
                cable_kind_label(cable.kind),
                cable_category_label(cable.category),
                length,
                cable.color,
                cable.purpose,
                inv.port_endpoint_label(snapshot, cable.end_a_port_id),
                inv.port_endpoint_label(snapshot, cable.end_b_port_id),
                inv.cable_path_label(snapshot, cable),
            ]
        )
    rows.sort(key=lambda r: (r[0].casefold(), r[6].casefold()))
    return ReportTable(
        ReportKind.CABLES,
        REPORT_TITLES[ReportKind.CABLES],
        [
            "Метка",
            "Вид",
            "Категория",
            "Длина, м",
            "Цвет",
            "Назначение",
            "Конец A",
            "Конец B",
            "Путь",
        ],
        rows,
    )


def _vlans_report(snapshot: ProjectSnapshot) -> ReportTable:
    rows: list[list[str]] = []
    for vlan in sorted(snapshot.vlans, key=lambda v: v.vlan_id):
        access_ports: list[str] = []
        tagged_ports: list[str] = []
        for port in snapshot.ports:
            if port.access_vlan_id == vlan.id:
                access_ports.append(inv.port_endpoint_label(snapshot, port.id))
            if vlan.id in port.tagged_vlan_ids:
                tagged_ports.append(inv.port_endpoint_label(snapshot, port.id))
        rows.append(
            [
                str(vlan.vlan_id),
                vlan.name,
                vlan.description,
                str(len(access_ports)),
                ", ".join(access_ports) or "—",
                str(len(tagged_ports)),
                ", ".join(tagged_ports) or "—",
            ]
        )
    return ReportTable(
        ReportKind.VLANS,
        REPORT_TITLES[ReportKind.VLANS],
        [
            "VLAN ID",
            "Имя",
            "Описание",
            "Access портов",
            "Access",
            "Tagged портов",
            "Tagged",
        ],
        rows,
    )


def _vrfs_report(snapshot: ProjectSnapshot) -> ReportTable:
    rows: list[list[str]] = []
    for vrf in sorted(snapshot.vrfs, key=lambda v: v.name.casefold()):
        ips = [ip for ip in snapshot.ips if ip.vrf_id == vrf.id]
        ip_labels = [inv.ip_label(ip) for ip in sorted(ips, key=lambda i: i.address)]
        rows.append(
            [
                vrf.name,
                vrf.rd or "—",
                vrf.description or "—",
                str(len(ips)),
                ", ".join(ip_labels) or "—",
            ]
        )
    global_ips = [ip for ip in snapshot.ips if ip.vrf_id is None]
    if global_ips or not rows:
        ip_labels = [
            inv.ip_label(ip) for ip in sorted(global_ips, key=lambda i: i.address)
        ]
        rows.insert(
            0,
            [
                "(глобально)",
                "—",
                "Без VRF",
                str(len(global_ips)),
                ", ".join(ip_labels) or "—",
            ],
        )
    return ReportTable(
        ReportKind.VRFS,
        REPORT_TITLES[ReportKind.VRFS],
        ["VRF", "RD", "Описание", "IP", "Адреса"],
        rows,
    )


def _free_unit_ranges(free: list[int]) -> str:
    if not free:
        return ""
    ranges: list[str] = []
    start = prev = free[0]
    for u in free[1:]:
        if u == prev + 1:
            prev = u
            continue
        ranges.append(f"U{start}" if start == prev else f"U{start}–{prev}")
        start = prev = u
    ranges.append(f"U{start}" if start == prev else f"U{start}–{prev}")
    return ", ".join(ranges)


def _racks_report(snapshot: ProjectSnapshot) -> ReportTable:
    rooms = {r.id: r for r in snapshot.rooms}
    rows: list[list[str]] = []
    for rack in sorted(snapshot.racks, key=lambda r: r.name.casefold()):
        room = rooms.get(rack.room_id)
        used_slots = inv.rack_occupied_slots(snapshot, rack.id)
        total_slots = max(1, int(rack.units) * 2)
        free_slots = total_slots - used_slots
        devices = inv.devices_in_rack(snapshot, rack.id)
        device_labels: list[str] = []
        for device in devices:
            label = device.hostname
            place = inv.rack_placement_label(device)
            if place:
                label = f"{label} ({place})"
            device_labels.append(label)
        free_txt = ""
        free_front = inv.rack_free_units(snapshot, rack.id, face=RackMountFace.FRONT)
        free_rear = inv.rack_free_units(snapshot, rack.id, face=RackMountFace.REAR)
        if free_front or free_rear:
            parts: list[str] = []
            if free_front:
                parts.append(f"Front: {_free_unit_ranges(free_front)}")
            if free_rear:
                parts.append(f"Rear: {_free_unit_ranges(free_rear)}")
            free_txt = "; ".join(parts)
        pct = f"{100 * used_slots / total_slots:.0f}%" if total_slots else "—"
        rows.append(
            [
                rack.name,
                room.name if room else "",
                str(rack.units),
                str(used_slots),
                str(free_slots),
                pct,
                str(len(devices)),
                ", ".join(device_labels) or "—",
                free_txt or "—",
            ]
        )
    return ReportTable(
        ReportKind.RACKS,
        REPORT_TITLES[ReportKind.RACKS],
        [
            "Шкаф",
            "Комната",
            "Всего U",
            "Слоты занято",
            "Слоты свободно",
            "Заполнение",
            "Устройств",
            "Монтаж",
            "Свободные юниты",
        ],
        rows,
    )


def _gxp_iq_report(snapshot: ProjectSnapshot) -> ReportTable:
    from landesigner.services import gxp_iq as gxp

    results = gxp.run_gxp_iq(snapshot)
    summary = gxp.iq_summary(results)
    overall = "PASS" if gxp.iq_overall_pass(results) else "FAIL"
    rows: list[list[str]] = [
        [
            "—",
            "Итог",
            f"GxP Infrastructure IQ — {overall}",
            (
                f"Черновик чек-листа квалификации инфраструктуры перед CSV. "
                f"PASS {summary['pass']} · FAIL {summary['fail']} · "
                f"N/A {summary['na']} · всего {summary['total']}. "
                f"Не заменяет CSV приложения и не является Part 11 / e-signature."
            ),
            overall,
            f"Проект: {snapshot.meta.name}; revision {snapshot.meta.revision}",
        ]
    ]
    for r in results:
        rows.append(
            [
                r.code,
                r.category,
                r.title,
                r.objective,
                r.verdict.value,
                r.evidence,
            ]
        )
    return ReportTable(
        ReportKind.GXP_IQ,
        REPORT_TITLES[ReportKind.GXP_IQ],
        [
            "Код",
            "Категория",
            "Тест",
            "Цель / критерий",
            "Вердикт",
            "Доказательство / отклонения",
        ],
        rows,
    )


def _change_log_report(snapshot: ProjectSnapshot) -> ReportTable:
    from landesigner.services import change_journal as journal

    rows: list[list[str]] = []
    for entry in journal.entries_newest_first(snapshot):
        obj = entry.entity_kind
        if entry.entity_id is not None:
            short = str(entry.entity_id)[:8]
            obj = f"{obj}:{short}" if obj else short
        rows.append(
            [
                entry.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                entry.actor,
                entry.action,
                entry.detail,
                obj or "",
            ]
        )
    return ReportTable(
        ReportKind.CHANGE_LOG,
        REPORT_TITLES[ReportKind.CHANGE_LOG],
        ["Когда (UTC)", "Кто", "Действие", "Подробности", "Объект"],
        rows,
    )
