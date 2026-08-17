from __future__ import annotations

from dataclasses import dataclass

from landesigner.domain.entities import DeviceType, ProjectSnapshot
from landesigner.domain.enums import DeviceRole, PortMedia, PortSide
from landesigner.services import inventory as inv


def _pp_groups(count: int) -> tuple[dict, ...]:
    return (
        {
            "prefix": "Front-",
            "count": count,
            "media": PortMedia.COPPER.value,
            "speed": 1000,
            "start": 1,
            "side": PortSide.FRONT.value,
            "paired": True,
        },
        {
            "prefix": "Rear-",
            "count": count,
            "media": PortMedia.COPPER.value,
            "speed": 1000,
            "start": 1,
            "side": PortSide.REAR.value,
            "paired": True,
        },
    )


@dataclass(frozen=True)
class DeviceTypePreset:
    key: str
    title: str
    vendor: str
    model: str
    role: DeviceRole
    port_groups: tuple[dict, ...]
    description: str = ""


@dataclass(frozen=True)
class RackPreset:
    key: str
    title: str
    units: int


DEVICE_TYPE_PRESETS: tuple[DeviceTypePreset, ...] = (
    DeviceTypePreset(
        key="sw24_4x10",
        title="Коммутатор 24×1G + 4×10G",
        vendor="Generic",
        model="SW-24T",
        role=DeviceRole.SWITCH,
        description="Типичный access/aggregation switch",
        port_groups=(
            {"prefix": "Gi1/0/", "count": 24, "media": PortMedia.COPPER.value, "speed": 1000, "start": 1},
            {"prefix": "Te1/0/", "count": 4, "media": PortMedia.FIBER.value, "speed": 10000, "start": 1},
        ),
    ),
    DeviceTypePreset(
        key="sw48_4x10",
        title="Коммутатор 48×1G + 4×10G",
        vendor="Generic",
        model="SW-48T",
        role=DeviceRole.SWITCH,
        description="Плотный access-коммутатор",
        port_groups=(
            {"prefix": "Gi1/0/", "count": 48, "media": PortMedia.COPPER.value, "speed": 1000, "start": 1},
            {"prefix": "Te1/0/", "count": 4, "media": PortMedia.FIBER.value, "speed": 10000, "start": 1},
        ),
    ),
    DeviceTypePreset(
        key="router_4",
        title="Маршрутизатор 4 порта",
        vendor="Generic",
        model="RTR-4",
        role=DeviceRole.ROUTER,
        port_groups=(
            {"prefix": "Gi0/", "count": 4, "media": PortMedia.COPPER.value, "speed": 1000, "start": 0},
        ),
    ),
    DeviceTypePreset(
        key="ap_1",
        title="Точка доступа",
        vendor="Generic",
        model="AP-1",
        role=DeviceRole.AP,
        port_groups=(
            {"prefix": "Gi0/", "count": 1, "media": PortMedia.COPPER.value, "speed": 1000, "start": 0},
        ),
    ),
    DeviceTypePreset(
        key="server_2",
        title="Сервер 2×1G",
        vendor="Generic",
        model="SRV-2",
        role=DeviceRole.SERVER,
        port_groups=(
            {"prefix": "eth", "count": 2, "media": PortMedia.COPPER.value, "speed": 1000, "start": 0},
        ),
    ),
    DeviceTypePreset(
        key="ws_1",
        title="Рабочая станция",
        vendor="Generic",
        model="PC-1",
        role=DeviceRole.WORKSTATION,
        port_groups=(
            {"prefix": "eth", "count": 1, "media": PortMedia.COPPER.value, "speed": 1000, "start": 0},
        ),
    ),
    DeviceTypePreset(
        key="pp24",
        title="Патч-панель 24",
        vendor="Generic",
        model="PP-24",
        role=DeviceRole.PATCH_PANEL,
        description="24 пары Front/Rear",
        port_groups=_pp_groups(24),
    ),
    DeviceTypePreset(
        key="pp48",
        title="Патч-панель 48",
        vendor="Generic",
        model="PP-48",
        role=DeviceRole.PATCH_PANEL,
        description="48 пар Front/Rear",
        port_groups=_pp_groups(48),
    ),
)

RACK_PRESETS: tuple[RackPreset, ...] = (
    RackPreset("u12", "12U", 12),
    RackPreset("u24", "24U", 24),
    RackPreset("u42", "42U (стандарт)", 42),
    RackPreset("u48", "48U", 48),
)


def list_device_type_presets() -> list[DeviceTypePreset]:
    return list(DEVICE_TYPE_PRESETS)


def list_rack_presets() -> list[RackPreset]:
    return list(RACK_PRESETS)


def add_device_type_from_preset(
    snapshot: ProjectSnapshot,
    preset_key: str,
) -> DeviceType:
    preset = next((p for p in DEVICE_TYPE_PRESETS if p.key == preset_key), None)
    if preset is None:
        raise ValueError(f"Неизвестный пресет: {preset_key}")
    return inv.add_device_type(
        snapshot,
        vendor=preset.vendor,
        model=preset.model,
        role=preset.role,
        port_groups=list(preset.port_groups),
    )
