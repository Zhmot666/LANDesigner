from __future__ import annotations

from landesigner.domain.entities import ProjectMeta, ProjectSnapshot, Site
from landesigner.domain.enums import DeviceRole
from landesigner.services import inventory as inv


def test_device_location_label():
    meta = ProjectMeta(name="L")
    site = Site(project_id=meta.id, name="S")
    snap = ProjectSnapshot(meta=meta, sites=[site])
    building = inv.add_building(snap, "Корпус A")
    floor = inv.add_floor(snap, building.id, "Этаж 1")
    room = inv.add_room(snap, floor.id, "Серверная")
    rack = inv.add_rack(snap, room.id, "Шкаф 1", units=42)
    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SWITCH, port_count=1
    )
    device = inv.add_device(
        snap, dtype.id, "core", room_id=room.id, rack_id=rack.id
    )
    label = inv.device_location_label(snap, device.id)
    assert "Корпус A" in label
    assert "Этаж 1" in label
    assert "Серверная" in label
    assert "Шкаф 1" in label

    bare = inv.add_device(snap, dtype.id, "orphan")
    assert inv.device_location_label(snap, bare.id) == "—"
