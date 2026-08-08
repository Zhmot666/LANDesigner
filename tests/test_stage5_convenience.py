from __future__ import annotations

from pathlib import Path

from landesigner.domain.entities import ProjectMeta, ProjectSnapshot, Site
from landesigner.domain.enums import DeviceRole
from landesigner.services import catalog as catalog_svc
from landesigner.services import floor_plan as fp
from landesigner.services import inventory as inv
from landesigner.services import snapshots as snap_svc
from landesigner.ui.commands.floor_plan_commands import RemoveFloorAssetCommand


def test_device_type_presets_add_to_project():
    meta = ProjectMeta(name="C")
    site = Site(project_id=meta.id, name="S")
    snap = ProjectSnapshot(meta=meta, sites=[site])
    presets = catalog_svc.list_device_type_presets()
    assert len(presets) >= 5
    dtype = catalog_svc.add_device_type_from_preset(snap, "sw24_4x10")
    assert dtype.role == DeviceRole.SWITCH
    assert len(dtype.port_template) == 28
    assert dtype.vendor == "Generic"


def test_rack_presets_include_42u():
    units = {p.units for p in catalog_svc.list_rack_presets()}
    assert {12, 24, 42, 48} <= units


def test_snapshot_create_list_restore(tmp_path: Path):
    project = tmp_path / "demo.lanproj"
    project.write_bytes(b"sqlite-or-bytes")
    assets = Path(str(project) + ".assets")
    assets.mkdir()
    (assets / "floor.png").write_bytes(b"img")

    snap_path = snap_svc.create_snapshot(project, label="before")
    assert snap_path.is_file()
    listed = snap_svc.list_snapshots(project)
    assert len(listed) == 1
    assert listed[0].path == snap_path

    # изменим оригинал
    project.write_bytes(b"changed")
    (assets / "floor.png").write_bytes(b"new")

    snap_svc.restore_snapshot(project, snap_path, make_safety_copy=True)
    assert project.read_bytes() == b"sqlite-or-bytes"
    assert (Path(str(project) + ".assets") / "floor.png").read_bytes() == b"img"
    # safety snapshot тоже появился
    assert len(snap_svc.list_snapshots(project)) >= 2


def test_remove_floor_asset_command_undo():
    from PySide6.QtWidgets import QApplication

    _ = QApplication.instance() or QApplication([])
    meta = ProjectMeta(name="P")
    site = Site(project_id=meta.id, name="S")
    snap = ProjectSnapshot(meta=meta, sites=[site])
    building = inv.add_building(snap, "B")
    floor = inv.add_floor(snap, building.id, "F")
    room = inv.add_room(snap, floor.id, "R")
    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SWITCH, port_count=1
    )
    inv.add_device(snap, dtype.id, "sw1", room_id=room.id)
    fp.ensure_assets_for_floor(snap, floor.id)
    asset_id = snap.floor_plan_assets[0].id

    cmd = RemoveFloorAssetCommand(snap, asset_id)
    cmd.redo()
    assert snap.floor_plan_assets == []
    cmd.undo()
    assert len(snap.floor_plan_assets) == 1
    assert snap.floor_plan_assets[0].id == asset_id
