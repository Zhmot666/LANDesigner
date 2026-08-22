from __future__ import annotations

from pathlib import Path

import pytest

from landesigner.adapters.local_sqlite.repository import LocalSqliteRepository
from landesigner.domain.entities import ProjectMeta, ProjectSnapshot, Site
from landesigner.domain.enums import CableKind, DeviceRole, PortSide, RackMountFace
from landesigner.services import catalog as catalog_svc
from landesigner.services import import_export as csv_io
from landesigner.services import inventory as inv
from landesigner.services import reports as reports_svc
from landesigner.services import validation as validation_svc
from landesigner.services.reports import ReportKind


def _base() -> ProjectSnapshot:
    meta = ProjectMeta(name="RacksPP")
    site = Site(project_id=meta.id, name="S")
    return ProjectSnapshot(meta=meta, sites=[site])


def _hierarchy(snap: ProjectSnapshot):
    building = inv.add_building(snap, "B1")
    floor = inv.add_floor(snap, building.id, "F1", level=1)
    room = inv.add_room(snap, floor.id, "R1")
    room2 = inv.add_room(snap, floor.id, "R2")
    rack = inv.add_rack(snap, room.id, "Шкаф 1", units=42)
    return building, floor, room, room2, rack


def test_rack_placement_and_unit_conflict():
    snap = _base()
    _, _, room, _, rack = _hierarchy(snap)
    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SWITCH, port_count=1
    )
    a = inv.add_device(
        snap,
        dtype.id,
        "sw-a",
        room_id=room.id,
        rack_id=rack.id,
        rack_u=10,
        rack_u_height=2,
    )
    assert a.rack_u == 10
    assert a.rack_u_height == 2
    assert inv.rack_placement_label(a) == "U10–11"
    assert "U10–11" in inv.device_location_label(snap, a.id)

    with pytest.raises(ValueError, match="Пересечение"):
        inv.add_device(
            snap,
            dtype.id,
            "sw-b",
            room_id=room.id,
            rack_id=rack.id,
            rack_u=11,
            rack_u_height=1,
        )

    b = inv.add_device(
        snap,
        dtype.id,
        "sw-b",
        room_id=room.id,
        rack_id=rack.id,
        rack_u=12,
        rack_u_height=1,
    )
    assert inv.rack_placement_label(b) == "U12"
    ordered = inv.devices_in_rack(snap, rack.id)
    assert [d.hostname for d in ordered] == ["sw-a", "sw-b"]


def test_dual_sided_rack_mount():
    snap = _base()
    _, _, room, _, rack = _hierarchy(snap)
    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SWITCH, port_count=1
    )
    inv.add_device(
        snap,
        dtype.id,
        "sw-front",
        room_id=room.id,
        rack_id=rack.id,
        rack_u=10,
        rack_mount_face=RackMountFace.FRONT,
    )
    rear = inv.add_device(
        snap,
        dtype.id,
        "pdu-rear",
        room_id=room.id,
        rack_id=rack.id,
        rack_u=10,
        rack_mount_face=RackMountFace.REAR,
    )
    assert rear.rack_mount_face == RackMountFace.REAR
    assert inv.rack_placement_label(rear) == "U10, Rear"
    front_devices = inv.devices_in_rack(snap, rack.id, face=RackMountFace.FRONT)
    rear_devices = inv.devices_in_rack(snap, rack.id, face=RackMountFace.REAR)
    assert {d.hostname for d in front_devices} == {"sw-front"}
    assert {d.hostname for d in rear_devices} == {"pdu-rear"}

    with pytest.raises(ValueError, match="Пересечение"):
        inv.add_device(
            snap,
            dtype.id,
            "sw-conflict",
            room_id=room.id,
            rack_id=rack.id,
            rack_u=10,
            rack_mount_face=RackMountFace.FRONT,
        )

    with pytest.raises(ValueError, match="Пересечение"):
        inv.add_device(
            snap,
            dtype.id,
            "full-depth",
            room_id=room.id,
            rack_id=rack.id,
            rack_u=12,
            rack_mount_face=RackMountFace.FULL,
        )
        inv.add_device(
            snap,
            dtype.id,
            "rear-blocked",
            room_id=room.id,
            rack_id=rack.id,
            rack_u=12,
            rack_mount_face=RackMountFace.REAR,
        )


def test_devices_for_location_filter():
    snap = _base()
    building, floor, room, room2, rack = _hierarchy(snap)
    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SWITCH, port_count=1
    )
    in_rack = inv.add_device(
        snap,
        dtype.id,
        "in-rack",
        room_id=room.id,
        rack_id=rack.id,
        rack_u=1,
    )
    in_room = inv.add_device(snap, dtype.id, "in-room", room_id=room.id)
    other_room = inv.add_device(snap, dtype.id, "other", room_id=room2.id)

    assert {d.id for d in inv.devices_for_location(snap, "rack", rack.id)} == {in_rack.id}
    assert {d.id for d in inv.devices_for_location(snap, "room", room.id)} == {
        in_rack.id,
        in_room.id,
    }
    assert {d.id for d in inv.devices_for_location(snap, "floor", floor.id)} == {
        in_rack.id,
        in_room.id,
        other_room.id,
    }
    assert {d.id for d in inv.devices_for_location(snap, "building", building.id)} == {
        in_rack.id,
        in_room.id,
        other_room.id,
    }
    assert len(inv.devices_for_location(snap, None, None)) == 3


def test_patch_panel_ports_and_pairs():
    snap = _base()
    dtype = inv.add_device_type(
        snap,
        vendor="Generic",
        model="PP-24",
        role=DeviceRole.PATCH_PANEL,
        port_groups=list(inv.build_patch_panel_port_groups(24)),
    )
    device = inv.add_device(snap, dtype.id, "pp1")
    ports = inv.ports_for_device(snap, device.id)
    assert len(ports) == 48
    fronts = [p for p in ports if p.side == PortSide.FRONT]
    rears = [p for p in ports if p.side == PortSide.REAR]
    assert len(fronts) == 24
    assert len(rears) == 24
    assert fronts[0].name == "Front-1"
    assert rears[0].name == "Rear-1"
    assert fronts[0].position == 1
    pair = inv.paired_port(snap, fronts[2])
    assert pair is not None
    assert pair.name == "Rear-3"
    assert pair.position == 3
    assert inv.paired_port(snap, pair).id == fronts[2].id


def test_catalog_pp24_preset():
    snap = _base()
    preset = next(p for p in catalog_svc.DEVICE_TYPE_PRESETS if p.key == "pp24")
    dt = catalog_svc.add_device_type_from_preset(snap, preset.key)
    assert dt.role == DeviceRole.PATCH_PANEL
    device = inv.add_device(snap, dt.id, "pp-cat")
    assert len(inv.ports_for_device(snap, device.id)) == 48


def test_patch_pair_half_connected_warning():
    snap = _base()
    pp_type = inv.add_device_type(
        snap,
        vendor="Generic",
        model="PP-24",
        role=DeviceRole.PATCH_PANEL,
        port_groups=list(inv.build_patch_panel_port_groups(2)),
    )
    sw_type = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SWITCH, port_count=1
    )
    pp = inv.add_device(snap, pp_type.id, "pp1")
    sw = inv.add_device(snap, sw_type.id, "sw1")
    front = next(p for p in inv.ports_for_device(snap, pp.id) if p.name == "Front-1")
    sw_port = inv.ports_for_device(snap, sw.id)[0]
    inv.add_cable(snap, front.id, sw_port.id, label="Patch", kind=CableKind.COPPER)

    issues = validation_svc.validate_project(snap)
    assert any(i.code == "patch_pair_half_connected" for i in issues)


def test_devices_report_includes_units():
    snap = _base()
    _, _, room, _, rack = _hierarchy(snap)
    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SWITCH, port_count=1
    )
    inv.add_device(
        snap,
        dtype.id,
        "sw1",
        room_id=room.id,
        rack_id=rack.id,
        rack_u=5,
        rack_u_height=2,
    )
    report = reports_svc.build_report(snap, ReportKind.DEVICES)
    assert "Юниты" in report.headers
    row = next(r for r in report.rows if r[0] == "sw1")
    assert row[report.headers.index("Юниты")] == "U5–6"


def test_rack_free_units_and_side_summary():
    snap = _base()
    _, _, room, _, rack = _hierarchy(snap)
    sw_type = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SWITCH, port_count=1
    )
    pp_type = inv.add_device_type(
        snap,
        vendor="Generic",
        model="PP-24",
        role=DeviceRole.PATCH_PANEL,
        port_groups=list(inv.build_patch_panel_port_groups(2)),
    )
    inv.add_device(
        snap,
        sw_type.id,
        "sw1",
        room_id=room.id,
        rack_id=rack.id,
        rack_u=10,
        rack_u_height=2,
    )
    pp = inv.add_device(
        snap,
        pp_type.id,
        "pp1",
        room_id=room.id,
        rack_id=rack.id,
        rack_u=20,
        rack_u_height=1,
    )
    occupied = inv.rack_occupied_units(snap, rack.id)
    assert occupied == {10, 11, 20}
    free = inv.rack_free_units(snap, rack.id)
    assert 10 not in free and 11 not in free and 20 not in free
    assert 1 in free and 42 in free
    total, busy = inv.rack_side_port_summary(snap, pp.id, PortSide.FRONT)
    assert total == 2
    assert busy == 0
    front = next(p for p in inv.ports_for_device(snap, pp.id) if p.name == "Front-1")
    sw_port = inv.ports_for_device(snap, next(d for d in snap.devices if d.hostname == "sw1").id)[0]
    inv.add_cable(snap, front.id, sw_port.id, label="p", kind=CableKind.COPPER)
    total, busy = inv.rack_side_port_summary(snap, pp.id, PortSide.FRONT)
    assert busy == 1

    report = reports_svc.build_report(snap, ReportKind.RACKS)
    assert report.title == "Шкафы / юниты"
    row = report.rows[0]
    assert row[0] == "Шкаф 1"
    assert row[report.headers.index("Слоты занято")] == "3"
    assert row[report.headers.index("Слоты свободно")] == "81"
    assert "sw1 (U10–11)" in row[report.headers.index("Монтаж")]


def test_unmount_clears_rack_placement():
    snap = _base()
    _, _, room, _, rack = _hierarchy(snap)
    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SWITCH, port_count=1
    )
    device = inv.add_device(
        snap,
        dtype.id,
        "sw1",
        room_id=room.id,
        rack_id=rack.id,
        rack_u=5,
        rack_u_height=2,
    )
    inv.set_device_rack_placement(
        snap, device.id, rack_id=None, rack_u=None, room_id=room.id
    )
    assert device.rack_id is None
    assert device.rack_u is None
    assert device.room_id == room.id
    assert inv.rack_free_units(snap, rack.id) == list(range(1, 43))



def test_sqlite_and_csv_round_trip_rack_and_pp(tmp_path: Path):
    snap = _base()
    _, _, room, _, rack = _hierarchy(snap)
    pp_type = inv.add_device_type(
        snap,
        vendor="Generic",
        model="PP-24",
        role=DeviceRole.PATCH_PANEL,
        port_groups=list(inv.build_patch_panel_port_groups(24)),
    )
    pp = inv.add_device(
        snap,
        pp_type.id,
        "pp1",
        room_id=room.id,
        rack_id=rack.id,
        rack_u=20,
        rack_u_height=1,
    )
    front = next(p for p in inv.ports_for_device(snap, pp.id) if p.name == "Front-5")
    assert front.side == PortSide.FRONT
    assert front.position == 5

    path = tmp_path / "pp.lanproj"
    repo = LocalSqliteRepository()
    repo.save_project(str(path), snap)
    loaded = repo.load_project(str(path))
    loaded_pp = next(d for d in loaded.devices if d.hostname == "pp1")
    assert loaded_pp.rack_id == rack.id
    assert loaded_pp.rack_u == 20
    assert loaded_pp.rack_u_height == 1
    ports = inv.ports_for_device(loaded, loaded_pp.id)
    assert len(ports) == 48
    front5 = next(p for p in ports if p.name == "Front-5")
    rear5 = inv.paired_port(loaded, front5)
    assert rear5 is not None
    assert rear5.name == "Rear-5"

    text = csv_io.export_to_text(snap)
    restored = csv_io.import_from_text(text)
    restored_pp = next(d for d in restored.devices if d.hostname == "pp1")
    assert restored_pp.rack_u == 20
    assert restored_pp.rack_u_height == 1
    r_ports = inv.ports_for_device(restored, restored_pp.id)
    assert len(r_ports) == 48
    assert any(p.side == PortSide.FRONT and p.position == 5 for p in r_ports)
    assert any(p.side == PortSide.REAR and p.position == 5 for p in r_ports)
