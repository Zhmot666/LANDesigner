from __future__ import annotations

from enum import StrEnum


class PortStatus(StrEnum):
    FREE = "FREE"
    OCCUPIED = "OCCUPIED"
    RESERVED = "RESERVED"
    DISABLED = "DISABLED"


class PortMedia(StrEnum):
    COPPER = "COPPER"
    FIBER = "FIBER"
    DAC = "DAC"
    VIRTUAL = "VIRTUAL"


class PortMode(StrEnum):
    ACCESS = "ACCESS"
    TRUNK = "TRUNK"


class CableKind(StrEnum):
    COPPER = "COPPER"
    FIBER = "FIBER"
    DAC = "DAC"


class CableCategory(StrEnum):
    CAT5E = "CAT5E"
    CAT6 = "CAT6"
    CAT6A = "CAT6A"
    OM3 = "OM3"
    OM4 = "OM4"
    OS2 = "OS2"
    OTHER = "OTHER"


class DeviceRole(StrEnum):
    SWITCH = "SWITCH"
    ROUTER = "ROUTER"
    AP = "AP"
    SERVER = "SERVER"
    WORKSTATION = "WORKSTATION"
    PATCH_PANEL = "PATCH_PANEL"
    OTHER = "OTHER"

