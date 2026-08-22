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


class PortSide(StrEnum):
    NONE = "NONE"
    FRONT = "FRONT"
    REAR = "REAR"


class RackMountFace(StrEnum):
    """Сторона монтажа устройства в шкафу (лицевая / тыльная / на всю глубину)."""

    FRONT = "FRONT"
    REAR = "REAR"
    FULL = "FULL"


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
    FIREWALL = "FIREWALL"
    LOAD_BALANCER = "LOAD_BALANCER"
    AP = "AP"
    CONTROLLER = "CONTROLLER"
    SERVER = "SERVER"
    STORAGE = "STORAGE"
    HYPERVISOR = "HYPERVISOR"
    VIRTUAL_MACHINE = "VIRTUAL_MACHINE"
    WORKSTATION = "WORKSTATION"
    PATCH_PANEL = "PATCH_PANEL"
    ODF = "ODF"
    PDU = "PDU"
    UPS = "UPS"
    KVM = "KVM"
    NVR = "NVR"
    IP_PHONE = "IP_PHONE"
    PRINTER = "PRINTER"
    MODEM = "MODEM"
    OTHER = "OTHER"


class LagMode(StrEnum):
    ACTIVE_BACKUP = "ACTIVE_BACKUP"
    LACP = "LACP"
    STATIC = "STATIC"

