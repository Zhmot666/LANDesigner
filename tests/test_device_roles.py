from __future__ import annotations

from landesigner.domain.enums import DeviceRole
from landesigner.services import topology as topo_svc
from landesigner.ui.labels import DEVICE_ROLE_RU, role_label
from landesigner.ui.widgets.topology_items import ROLE_COLORS


def test_every_device_role_has_russian_label():
    for role in DeviceRole:
        assert role in DEVICE_ROLE_RU
        assert role_label(role) == DEVICE_ROLE_RU[role]


def test_every_device_role_has_topology_color_and_layout():
    for role in DeviceRole:
        assert role in ROLE_COLORS
        assert role in topo_svc._ROLE_LAYOUT_ORDER
