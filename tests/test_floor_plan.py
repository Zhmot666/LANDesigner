from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from landesigner.adapters.local_sqlite.repository import LocalSqliteRepository
from landesigner.domain.entities import ProjectMeta, ProjectSnapshot, Site
from landesigner.domain.enums import DeviceRole
from landesigner.services import floor_plan as fp
from landesigner.services import inventory as inv
from landesigner.services.project import ProjectService


def _snap_with_floor() -> ProjectSnapshot:
    meta = ProjectMeta(name="Plan")
    site = Site(project_id=meta.id, name="S")
    snap = ProjectSnapshot(meta=meta, sites=[site])
    building = inv.add_building(snap, "B1")
    floor = inv.add_floor(snap, building.id, "F1", level=1)
    room = inv.add_room(snap, floor.id, "R1")
    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SWITCH, port_count=1
    )
    inv.add_device(snap, dtype.id, "sw1", room_id=room.id)
    inv.add_device(snap, dtype.id, "sw2", room_id=room.id)
    return snap


def test_ensure_assets_for_floor_devices():
    snap = _snap_with_floor()
    floor_id = snap.floors[0].id
    assert snap.floor_plan_assets == []
    assert fp.ensure_assets_for_floor(snap, floor_id)
    assert len(snap.floor_plan_assets) == 2
    assert not fp.ensure_assets_for_floor(snap, floor_id)


def test_move_asset_and_scale():
    snap = _snap_with_floor()
    floor_id = snap.floors[0].id
    fp.ensure_assets_for_floor(snap, floor_id)
    asset = snap.floor_plan_assets[0]
    fp.move_asset(snap, asset.id, 10.5, 20.25)
    assert asset.x == 10.5
    assert asset.y == 20.25
    fp.set_scale(snap, floor_id, 0.05)
    assert snap.floors[0].scale_m_per_px == 0.05


def test_path_length_m():
    pts = [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0)]
    assert abs(fp.path_length_px(pts) - 150.0) < 1e-9
    assert abs(fp.path_length_m(pts, 0.1) - 15.0) < 1e-9


def test_floor_plan_persists(tmp_path: Path):
    snap = _snap_with_floor()
    floor_id = snap.floors[0].id
    fp.ensure_assets_for_floor(snap, floor_id)
    fp.move_asset(snap, snap.floor_plan_assets[0].id, 33, 44)
    fp.set_scale(snap, floor_id, 0.02)

    path = tmp_path / "p.lanproj"
    service = ProjectService(LocalSqliteRepository())
    service.save_project(str(path), snap)
    loaded = service.open_project(str(path))
    assert len(loaded.floor_plan_assets) == 2
    assert loaded.floors[0].scale_m_per_px == 0.02
    assert any(a.x == 33 and a.y == 44 for a in loaded.floor_plan_assets)


def test_import_plan_image_resizes(tmp_path: Path):
    _ = QApplication.instance() or QApplication([])
    snap = _snap_with_floor()
    floor_id = snap.floors[0].id
    project = tmp_path / "demo.lanproj"
    project.write_text("placeholder")

    src = tmp_path / "big.png"
    img = QImage(5000, 2000, QImage.Format.Format_RGB32)
    img.fill(QColor("#2f7c85"))
    assert img.save(str(src), "PNG")

    rel = fp.import_plan_image(snap, floor_id, src, project)
    assert snap.floors[0].plan_image_relpath == rel
    dest = fp.resolve_plan_image(project, rel)
    assert dest is not None and dest.is_file()
    saved = QImage(str(dest))
    assert max(saved.width(), saved.height()) <= fp.MAX_PLAN_SIDE_PX
