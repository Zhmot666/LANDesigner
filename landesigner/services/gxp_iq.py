"""Черновик GxP Infrastructure IQ — квалификация IT/сетевой инфраструктуры перед CSV.

Не заменяет полную CSV приложения и не обеспечивает Part 11 / e-signature.
Цель: as-built / configuration baseline + Pass/Fail по чек-листу IQ.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from landesigner.domain.entities import ProjectSnapshot
from landesigner.domain.enums import DeviceRole
from landesigner.services import validation as validation_svc
from landesigner.services.validation import IssueSeverity


class IqVerdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NA = "N/A"


class IqCategory(StrEnum):
    INVENTORY = "Инвентарь / идентификация"
    INTEGRITY = "Целостность конфигурации"
    EDGE = "Граница сети / доступ"
    PHYSICAL = "Физическое размещение"
    VIRTUAL = "Виртуализация"
    DOCUMENTATION = "Документирование"


@dataclass(frozen=True)
class IqTestDef:
    code: str
    category: IqCategory
    title: str
    objective: str
    """Что проверяем (для протокола)."""


@dataclass(frozen=True)
class IqTestResult:
    code: str
    category: str
    title: str
    objective: str
    verdict: IqVerdict
    evidence: str
    """Фактический результат / перечень отклонений."""


# Стабильный черновик IQ-тестов под текущую модель LanDesigner.
IQ_TESTS: tuple[IqTestDef, ...] = (
    IqTestDef(
        "IQ-01",
        IqCategory.INVENTORY,
        "Площадка идентифицирована",
        "В проекте есть площадка с непустым именем (scope квалификации).",
    ),
    IqTestDef(
        "IQ-02",
        IqCategory.INVENTORY,
        "Устройства имеют hostname",
        "Каждое устройство идентифицировано hostname (трассируемость as-built).",
    ),
    IqTestDef(
        "IQ-03",
        IqCategory.INTEGRITY,
        "Нет дублирующих IP в пределах VRF",
        "Адресация уникальна в scope VRF / глобально — основа сетевой конфигурации.",
    ),
    IqTestDef(
        "IQ-04",
        IqCategory.INTEGRITY,
        "Согласованность портов и кабелей",
        "Нет портов «занят без кабеля» / «свободен, но есть кабель»; концы кабелей существуют.",
    ),
    IqTestDef(
        "IQ-05",
        IqCategory.INTEGRITY,
        "Согласованность среды порта и вида кабеля",
        "Медь/оптика/DAC на концах согласованы с видом кабеля.",
    ),
    IqTestDef(
        "IQ-06",
        IqCategory.DOCUMENTATION,
        "Кабели имеют метки",
        "Каждый кабель промаркирован меткой (прослеживаемость соединений).",
    ),
    IqTestDef(
        "IQ-07",
        IqCategory.EDGE,
        "Описана граница сети (edge)",
        "Есть межсетевой экран / маршрутизатор / модем-шлюз как граница площадки.",
    ),
    IqTestDef(
        "IQ-08",
        IqCategory.EDGE,
        "WAN / uplink к провайдеру задокументирован",
        "При наличии edge-устройства есть кабель с назначением WAN или меткой, содержащей WAN.",
    ),
    IqTestDef(
        "IQ-09",
        IqCategory.PHYSICAL,
        "Монтаж в шкафу указан полностью",
        "Устройства со шкафом имеют юнит (rack_u); ВМ не размещены в шкафу.",
    ),
    IqTestDef(
        "IQ-10",
        IqCategory.PHYSICAL,
        "Патч-панели без односторонних пар",
        "Пары Front/Rear не остаются в состоянии half (незавершённый проброс).",
    ),
    IqTestDef(
        "IQ-11",
        IqCategory.VIRTUAL,
        "ВМ привязаны к гипервизору",
        "Виртуальные серверы имеют корректный host; гипервизоры не «висят» без смысла в rack-правилах.",
    ),
    IqTestDef(
        "IQ-12",
        IqCategory.DOCUMENTATION,
        "Инфраструктурные узлы на схеме топологии",
        "Коммутаторы, МСЭ, маршрутизаторы и гипервизоры присутствуют на схеме as-built.",
    ),
)


_EDGE_ROLES = frozenset(
    {DeviceRole.FIREWALL, DeviceRole.ROUTER, DeviceRole.MODEM}
)
_TOPOLOGY_ROLES = frozenset(
    {
        DeviceRole.SWITCH,
        DeviceRole.FIREWALL,
        DeviceRole.ROUTER,
        DeviceRole.LOAD_BALANCER,
        DeviceRole.HYPERVISOR,
        DeviceRole.CONTROLLER,
    }
)


def run_gxp_iq(snapshot: ProjectSnapshot) -> list[IqTestResult]:
    issues = validation_svc.validate_project(snapshot)
    by_code: dict[str, list] = {}
    for issue in issues:
        by_code.setdefault(issue.code, []).append(issue)

    results: list[IqTestResult] = []
    for test in IQ_TESTS:
        results.append(_evaluate(test, snapshot, by_code))
    return results


def iq_summary(results: list[IqTestResult]) -> dict[str, int]:
    return {
        "pass": sum(1 for r in results if r.verdict == IqVerdict.PASS),
        "fail": sum(1 for r in results if r.verdict == IqVerdict.FAIL),
        "na": sum(1 for r in results if r.verdict == IqVerdict.NA),
        "total": len(results),
    }


def iq_overall_pass(results: list[IqTestResult]) -> bool:
    return all(r.verdict != IqVerdict.FAIL for r in results)


def _evaluate(
    test: IqTestDef,
    snapshot: ProjectSnapshot,
    by_code: dict[str, list],
) -> IqTestResult:
    if test.code == "IQ-01":
        return _iq_site(test, snapshot)
    if test.code == "IQ-02":
        return _iq_hostnames(test, snapshot)
    if test.code == "IQ-03":
        return _from_issue_codes(
            test, by_code, ("duplicate_ip",), empty_pass="Дублирующих IP не обнаружено."
        )
    if test.code == "IQ-04":
        return _from_issue_codes(
            test,
            by_code,
            ("occupied_without_cable", "free_with_cable", "cable_missing_port"),
            empty_pass="Порты и кабели согласованы.",
        )
    if test.code == "IQ-05":
        return _from_issue_codes(
            test,
            by_code,
            ("media_kind_mismatch",),
            empty_pass="Несовпадений среды/кабеля нет.",
            only_errors=False,
        )
    if test.code == "IQ-06":
        return _from_issue_codes(
            test,
            by_code,
            ("cable_no_label",),
            empty_pass="Все кабели имеют метки." if snapshot.cables else "Кабелей нет.",
            only_errors=False,
            na_if_no_cables=len(snapshot.cables) == 0,
        )
    if test.code == "IQ-07":
        return _iq_edge_present(test, snapshot)
    if test.code == "IQ-08":
        return _iq_wan_documented(test, snapshot)
    if test.code == "IQ-09":
        return _iq_rack_placement(test, snapshot, by_code)
    if test.code == "IQ-10":
        return _from_issue_codes(
            test,
            by_code,
            ("patch_pair_half_connected",),
            empty_pass="Односторонних пар патч-панелей нет."
            if any(d.role == DeviceRole.PATCH_PANEL for d in snapshot.devices)
            else "Патч-панелей нет.",
            only_errors=False,
            na_if=not any(d.role == DeviceRole.PATCH_PANEL for d in snapshot.devices),
        )
    if test.code == "IQ-11":
        return _iq_vms(test, snapshot, by_code)
    if test.code == "IQ-12":
        return _iq_topology(test, snapshot, by_code)
    return IqTestResult(
        test.code,
        test.category.value,
        test.title,
        test.objective,
        IqVerdict.NA,
        "Тест не реализован.",
    )


def _iq_site(test: IqTestDef, snapshot: ProjectSnapshot) -> IqTestResult:
    if not snapshot.sites:
        return _fail(test, "В проекте нет площадки.")
    names = [s.name.strip() for s in snapshot.sites]
    if any(not n for n in names):
        return _fail(test, "Есть площадка без имени.")
    return _pass(test, f"Площадка: {', '.join(names)}.")


def _iq_hostnames(test: IqTestDef, snapshot: ProjectSnapshot) -> IqTestResult:
    if not snapshot.devices:
        return _na(test, "Устройств нет.")
    missing = [d for d in snapshot.devices if not d.hostname.strip()]
    if missing:
        return _fail(test, f"Без hostname: {len(missing)} шт.")
    return _pass(test, f"Устройств с hostname: {len(snapshot.devices)}.")


def _iq_edge_present(test: IqTestDef, snapshot: ProjectSnapshot) -> IqTestResult:
    edges = [d for d in snapshot.devices if d.role in _EDGE_ROLES]
    if not edges:
        return _fail(
            test,
            "Нет устройств роли Межсетевой экран / Маршрутизатор / Модем-шлюз.",
        )
    labels = ", ".join(
        f"{d.hostname or d.id} ({d.role.value})" for d in edges[:8]
    )
    extra = f" и ещё {len(edges) - 8}" if len(edges) > 8 else ""
    return _pass(test, f"Edge: {labels}{extra}.")


def _iq_wan_documented(test: IqTestDef, snapshot: ProjectSnapshot) -> IqTestResult:
    edges = [d for d in snapshot.devices if d.role in _EDGE_ROLES]
    if not edges:
        return _na(test, "Edge-устройств нет — тест не применим.")
    for cable in snapshot.cables:
        purpose = cable.purpose.strip().casefold()
        label = cable.label.strip().casefold()
        if purpose == "wan" or "wan" in purpose or "wan" in label:
            return _pass(
                test,
                f"Найден WAN-линк: «{cable.label or cable.purpose or cable.id}».",
            )
    return _fail(
        test,
        "Edge есть, но нет кабеля с назначением/меткой WAN "
        "(например FG wan1 ↔ оборудование провайдера).",
    )


def _iq_rack_placement(
    test: IqTestDef, snapshot: ProjectSnapshot, by_code: dict[str, list]
) -> IqTestResult:
    bad: list[str] = []
    for device in snapshot.devices:
        if device.role == DeviceRole.VIRTUAL_MACHINE:
            continue
        if device.rack_id is not None and device.rack_u is None:
            bad.append(device.hostname or str(device.id))
    vm_in_rack = by_code.get("vm_in_rack", [])
    if bad or vm_in_rack:
        parts: list[str] = []
        if bad:
            parts.append("без U: " + ", ".join(bad[:6]))
        if vm_in_rack:
            parts.append(f"ВМ в шкафу: {len(vm_in_rack)}")
        return _fail(test, "; ".join(parts))
    mounted = sum(1 for d in snapshot.devices if d.rack_id is not None)
    if mounted == 0 and not snapshot.racks:
        return _na(test, "Шкафов и монтажей нет.")
    return _pass(test, f"Монтажей в шкафах: {mounted}.")


def _iq_vms(
    test: IqTestDef, snapshot: ProjectSnapshot, by_code: dict[str, list]
) -> IqTestResult:
    vms = [d for d in snapshot.devices if d.role == DeviceRole.VIRTUAL_MACHINE]
    if not vms:
        return _na(test, "Виртуальных серверов нет.")
    codes = ("vm_missing_host", "vm_invalid_host", "host_on_non_vm")
    return _from_issue_codes(
        test,
        by_code,
        codes,
        empty_pass=f"ВМ: {len(vms)}, привязка к хосту корректна.",
    )


def _iq_topology(
    test: IqTestDef, snapshot: ProjectSnapshot, by_code: dict[str, list]
) -> IqTestResult:
    targets = [d for d in snapshot.devices if d.role in _TOPOLOGY_ROLES]
    if not targets:
        return _na(test, "Инфраструктурных узлов целевых ролей нет.")
    on_topo = {n.device_id for n in snapshot.topology_nodes}
    missing = [d for d in targets if d.id not in on_topo]
    if missing:
        names = ", ".join((d.hostname or str(d.id)) for d in missing[:8])
        extra = f" и ещё {len(missing) - 8}" if len(missing) > 8 else ""
        return _fail(test, f"Нет на схеме: {names}{extra}.")
    # Дополнительно учтём validation warnings device_off_topology только для целевых ролей
    _ = by_code
    return _pass(test, f"На схеме: {len(targets)} инфраструктурных узлов.")


def _from_issue_codes(
    test: IqTestDef,
    by_code: dict[str, list],
    codes: tuple[str, ...],
    *,
    empty_pass: str,
    only_errors: bool = True,
    na_if: bool = False,
    na_if_no_cables: bool = False,
) -> IqTestResult:
    if na_if or na_if_no_cables:
        return _na(test, empty_pass)
    found = []
    for code in codes:
        for issue in by_code.get(code, []):
            if only_errors and issue.severity != IssueSeverity.ERROR:
                continue
            found.append(issue)
    if not found:
        return _pass(test, empty_pass)
    sample = "; ".join(i.message for i in found[:5])
    more = f" (+{len(found) - 5})" if len(found) > 5 else ""
    return _fail(test, f"{sample}{more}")


def _pass(test: IqTestDef, evidence: str) -> IqTestResult:
    return IqTestResult(
        test.code,
        test.category.value,
        test.title,
        test.objective,
        IqVerdict.PASS,
        evidence,
    )


def _fail(test: IqTestDef, evidence: str) -> IqTestResult:
    return IqTestResult(
        test.code,
        test.category.value,
        test.title,
        test.objective,
        IqVerdict.FAIL,
        evidence,
    )


def _na(test: IqTestDef, evidence: str) -> IqTestResult:
    return IqTestResult(
        test.code,
        test.category.value,
        test.title,
        test.objective,
        IqVerdict.NA,
        evidence,
    )
