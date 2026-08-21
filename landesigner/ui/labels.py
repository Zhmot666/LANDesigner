from __future__ import annotations

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

DEVICE_ROLE_RU: dict[DeviceRole, str] = {
    DeviceRole.SWITCH: "Коммутатор",
    DeviceRole.ROUTER: "Маршрутизатор",
    DeviceRole.AP: "Точка доступа",
    DeviceRole.SERVER: "Сервер",
    DeviceRole.HYPERVISOR: "Гипервизор",
    DeviceRole.VIRTUAL_MACHINE: "Виртуальный сервер",
    DeviceRole.WORKSTATION: "Рабочая станция",
    DeviceRole.PATCH_PANEL: "Патч-панель",
    DeviceRole.OTHER: "Прочее",
}

LAG_MODE_RU: dict[LagMode, str] = {
    LagMode.ACTIVE_BACKUP: "Active-Backup",
    LagMode.LACP: "LACP",
    LagMode.STATIC: "Static",
}

PORT_MEDIA_RU: dict[PortMedia, str] = {
    PortMedia.COPPER: "Медь",
    PortMedia.FIBER: "Оптика",
    PortMedia.DAC: "DAC",
    PortMedia.VIRTUAL: "vNIC",
}

PORT_STATUS_RU: dict[PortStatus, str] = {
    PortStatus.FREE: "Свободен",
    PortStatus.OCCUPIED: "Занят",
    PortStatus.RESERVED: "Резерв",
    PortStatus.DISABLED: "Отключён",
}

PORT_MODE_RU: dict[PortMode, str] = {
    PortMode.ACCESS: "Access",
    PortMode.TRUNK: "Trunk",
}

PORT_SIDE_RU: dict[PortSide, str] = {
    PortSide.NONE: "—",
    PortSide.FRONT: "Front",
    PortSide.REAR: "Rear",
}

CABLE_KIND_RU: dict[CableKind, str] = {
    CableKind.COPPER: "Медь",
    CableKind.FIBER: "Оптика",
    CableKind.DAC: "DAC",
}

CABLE_CATEGORY_RU: dict[CableCategory, str] = {
    CableCategory.CAT5E: "Cat5e",
    CableCategory.CAT6: "Cat6",
    CableCategory.CAT6A: "Cat6a",
    CableCategory.OM3: "OM3",
    CableCategory.OM4: "OM4",
    CableCategory.OS2: "OS2",
    CableCategory.OTHER: "Прочее",
}


def role_label(role: DeviceRole) -> str:
    return DEVICE_ROLE_RU.get(role, role.value)


def media_label(media: PortMedia) -> str:
    return PORT_MEDIA_RU.get(media, media.value)


def status_label(status: PortStatus) -> str:
    return PORT_STATUS_RU.get(status, status.value)


def port_mode_label(mode: PortMode) -> str:
    return PORT_MODE_RU.get(mode, mode.value)


def port_side_label(side: PortSide) -> str:
    return PORT_SIDE_RU.get(side, side.value)


def cable_kind_label(kind: CableKind) -> str:
    return CABLE_KIND_RU.get(kind, kind.value)


def cable_category_label(category: CableCategory) -> str:
    return CABLE_CATEGORY_RU.get(category, category.value)


def lag_mode_label(mode: LagMode) -> str:
    return LAG_MODE_RU.get(mode, mode.value)
