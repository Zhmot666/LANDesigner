from __future__ import annotations

from pathlib import Path

from landesigner.adapters.local_sqlite.repository import LocalSqliteRepository
from landesigner.domain.entities import ProjectMeta, ProjectSnapshot, Site
from landesigner.domain.enums import CableKind, DeviceRole
from landesigner.services import import_export as csv_io
from landesigner.services import inventory as inv
from landesigner.services import reports as reports_svc
from landesigner.services.reports import ReportKind


def _base() -> ProjectSnapshot:
    meta = ProjectMeta(name="PP")
    site = Site(project_id=meta.id, name="S")
    return ProjectSnapshot(meta=meta, sites=[site])


def test_patch_panel_matrix_and_through_path():
    snap = _base()
    pp_type = inv.add_device_type(
        snap,
        vendor="Generic",
        model="PP-24",
        role=DeviceRole.PATCH_PANEL,
        port_groups=list(inv.build_patch_panel_port_groups(2)),
    )
    sw_type = inv.add_device_type(
        snap, vendor="X", model="SW", role=DeviceRole.SWITCH, port_count=2
    )
    pc_type = inv.add_device_type(
        snap, vendor="X", model="PC", role=DeviceRole.WORKSTATION, port_count=1
    )
    pp = inv.add_device(snap, pp_type.id, "pp1")
    sw = inv.add_device(snap, sw_type.id, "sw1")
    pc = inv.add_device(snap, pc_type.id, "pc1")
    front1 = next(p for p in inv.ports_for_device(snap, pp.id) if p.name == "Front-1")
    rear1 = next(p for p in inv.ports_for_device(snap, pp.id) if p.name == "Rear-1")
    sw_p = inv.ports_for_device(snap, sw.id)[0]
    pc_p = inv.ports_for_device(snap, pc.id)[0]

    pairs = inv.patch_panel_pairs(snap, pp.id)
    assert len(pairs) == 2
    assert pairs[0].status == "free"

    inv.add_cable(
        snap, sw_p.id, rear1.id, label="SW-PP", kind=CableKind.COPPER, color="синий"
    )
    pairs = inv.patch_panel_pairs(snap, pp.id)
    assert pairs[0].status == "half"

    inv.add_cable(
        snap,
        front1.id,
        pc_p.id,
        label="PP-PC",
        kind=CableKind.COPPER,
        purpose="рабочее место",
    )
    pairs = inv.patch_panel_pairs(snap, pp.id)
    assert pairs[0].status == "through"
    path = inv.patch_through_path_label(snap, pairs[0])
    assert "sw1" in path and "pc1" in path and "Front-1" in path and "Rear-1" in path

    cable = next(c for c in snap.cables if c.label == "PP-PC")
    assert "sw1" in inv.cable_path_label(snap, cable)
    assert cable.purpose == "рабочее место"


def test_cable_color_purpose_roundtrip(tmp_path: Path):
    snap = _base()
    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SWITCH, port_count=1
    )
    a = inv.add_device(snap, dtype.id, "a")
    b = inv.add_device(snap, dtype.id, "b")
    inv.add_cable(
        snap,
        inv.ports_for_device(snap, a.id)[0].id,
        inv.ports_for_device(snap, b.id)[0].id,
        label="c1",
        color="orange",
        purpose="uplink",
    )
    path = tmp_path / "c.lanproj"
    repo = LocalSqliteRepository()
    repo.save_project(str(path), snap)
    loaded = repo.load_project(str(path))
    assert loaded.cables[0].color == "orange"
    assert loaded.cables[0].purpose == "uplink"

    text = csv_io.export_to_text(snap)
    restored = csv_io.import_from_text(text)
    assert restored.cables[0].color == "orange"
    assert restored.cables[0].purpose == "uplink"

    report = reports_svc.build_report(snap, ReportKind.CABLES)
    assert "Цвет" in report.headers
    assert "Путь" in report.headers
    row = report.rows[0]
    assert row[report.headers.index("Цвет")] == "orange"
    assert row[report.headers.index("Назначение")] == "uplink"
