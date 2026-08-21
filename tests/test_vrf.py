from __future__ import annotations

from pathlib import Path

from landesigner.adapters.local_sqlite.repository import LocalSqliteRepository
from landesigner.domain.entities import ProjectMeta, ProjectSnapshot, Site
from landesigner.services import import_export as csv_io
from landesigner.services import inventory as inv
from landesigner.services import reports as reports_svc
from landesigner.services import validation as validation_svc
from landesigner.services.project import ProjectService


def _snap() -> ProjectSnapshot:
    meta = ProjectMeta(name="VRF")
    site = Site(project_id=meta.id, name="S")
    return ProjectSnapshot(meta=meta, sites=[site])


def test_same_ip_allowed_in_different_vrfs():
    snap = _snap()
    a = inv.add_vrf(snap, "Cust-A", rd="65000:1")
    b = inv.add_vrf(snap, "Cust-B", rd="65000:2")
    inv.add_ip(snap, address="10.0.0.1", vrf_id=a.id)
    inv.add_ip(snap, address="10.0.0.1", vrf_id=b.id)
    inv.add_ip(snap, address="10.0.0.1")  # глобально
    assert len(snap.ips) == 3
    issues = validation_svc.validate_project(snap)
    assert not any(i.code == "duplicate_ip" for i in issues)


def test_duplicate_ip_inside_same_vrf():
    snap = _snap()
    vrf = inv.add_vrf(snap, "Cust-A")
    inv.add_ip(snap, address="10.0.0.1", vrf_id=vrf.id)
    try:
        inv.add_ip(snap, address="10.0.0.1", vrf_id=vrf.id)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "VRF" in str(e) or "уже" in str(e)
    issues = validation_svc.validate_project(snap)
    # один адрес — нет duplicate
    assert not any(i.code == "duplicate_ip" for i in issues)
    # вручную добавим конфликт в snapshot
    from landesigner.domain.entities import IpAddress

    snap.ips.append(
        IpAddress(site_id=snap.sites[0].id, address="10.0.0.1", vrf_id=vrf.id)
    )
    issues = validation_svc.validate_project(snap)
    dup = [i for i in issues if i.code == "duplicate_ip"]
    assert dup
    assert "Cust-A" in dup[0].message or "VRF" in dup[0].message


def test_vrf_persists_and_csv_roundtrip(tmp_path: Path):
    snap = _snap()
    vrf = inv.add_vrf(snap, "MGMT", rd="1:100", description="mgmt")
    inv.add_ip(snap, address="192.168.1.1", cidr="24", vrf_id=vrf.id)

    path = tmp_path / "v.lanproj"
    service = ProjectService(LocalSqliteRepository())
    service.save_project(str(path), snap)
    loaded = service.open_project(str(path))
    assert len(loaded.vrfs) == 1
    assert loaded.vrfs[0].name == "MGMT"
    assert loaded.vrfs[0].rd == "1:100"
    assert loaded.ips[0].vrf_id == loaded.vrfs[0].id

    text = csv_io.export_to_text(loaded)
    assert "#section=vrfs" in text
    again = csv_io.import_from_text(text)
    assert again.vrfs[0].name == "MGMT"
    assert again.ips[0].vrf_id == again.vrfs[0].id


def test_vrf_report_lists_scopes():
    snap = _snap()
    vrf = inv.add_vrf(snap, "Cust-A")
    inv.add_ip(snap, address="10.1.1.1", vrf_id=vrf.id)
    inv.add_ip(snap, address="10.0.0.1")
    table = reports_svc.build_report(snap, reports_svc.ReportKind.VRFS)
    assert table.headers[0] == "VRF"
    names = [row[0] for row in table.rows]
    assert "(глобально)" in names
    assert "Cust-A" in names
