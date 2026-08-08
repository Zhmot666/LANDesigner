from __future__ import annotations

from pathlib import Path

from landesigner.adapters.local_sqlite.repository import LocalSqliteRepository
from landesigner.domain.entities import ProjectMeta, ProjectSnapshot, Site
from landesigner.domain.enums import CableKind, DeviceRole, LagMode
from landesigner.services import import_export as csv_io
from landesigner.services import inventory as inv
from landesigner.services import validation as validation_svc
from landesigner.services.project import ProjectService


def _snap() -> ProjectSnapshot:
    meta = ProjectMeta(name="LAG")
    site = Site(project_id=meta.id, name="S")
    return ProjectSnapshot(meta=meta, sites=[site])


def test_add_lag_and_ip_on_lag():
    snap = _snap()
    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SERVER, port_count=2
    )
    srv = inv.add_device(snap, dtype.id, "srv1")
    ports = inv.ports_for_device(snap, srv.id)
    lag = inv.add_lag(
        snap,
        device_id=srv.id,
        name="bond0",
        mode=LagMode.ACTIVE_BACKUP,
        member_port_ids=[ports[0].id, ports[1].id],
    )
    assert lag.name == "bond0"
    assert len(lag.member_port_ids) == 2
    ip = inv.add_ip(snap, address="10.0.0.10", cidr="24", lag_id=lag.id)
    assert ip.lag_id == lag.id
    assert ip.port_id is None
    assert inv.ips_for_lag(snap, lag.id)[0].address == "10.0.0.10"


def test_port_cannot_join_two_lags():
    snap = _snap()
    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SERVER, port_count=3
    )
    srv = inv.add_device(snap, dtype.id, "srv1")
    ports = inv.ports_for_device(snap, srv.id)
    inv.add_lag(
        snap,
        device_id=srv.id,
        name="bond0",
        mode=LagMode.LACP,
        member_port_ids=[ports[0].id, ports[1].id],
    )
    try:
        inv.add_lag(
            snap,
            device_id=srv.id,
            name="bond1",
            mode=LagMode.LACP,
            member_port_ids=[ports[0].id, ports[2].id],
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "уже в LAG" in str(exc)


def test_delete_lag_removes_ips_keeps_ports():
    snap = _snap()
    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SERVER, port_count=2
    )
    srv = inv.add_device(snap, dtype.id, "srv1")
    ports = inv.ports_for_device(snap, srv.id)
    lag = inv.add_lag(
        snap,
        device_id=srv.id,
        name="bond0",
        mode=LagMode.STATIC,
        member_port_ids=[ports[0].id, ports[1].id],
    )
    inv.add_ip(snap, address="10.1.1.1", lag_id=lag.id)
    inv.delete_lag(snap, lag.id)
    assert snap.lags == []
    assert snap.ips == []
    assert len(inv.ports_for_device(snap, srv.id)) == 2


def test_lag_csv_and_sqlite_roundtrip(tmp_path: Path):
    snap = _snap()
    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SERVER, port_count=2
    )
    srv = inv.add_device(snap, dtype.id, "srv1")
    ports = inv.ports_for_device(snap, srv.id)
    lag = inv.add_lag(
        snap,
        device_id=srv.id,
        name="bond0",
        mode=LagMode.ACTIVE_BACKUP,
        member_port_ids=[ports[0].id, ports[1].id],
        notes="NIC team",
    )
    inv.add_ip(snap, address="10.2.2.2", cidr="24", lag_id=lag.id)

    csv_path = tmp_path / "lag.ldcsv"
    csv_io.export_snapshot(snap, csv_path)
    restored = csv_io.import_snapshot(csv_path)
    assert len(restored.lags) == 1
    assert restored.lags[0].name == "bond0"
    assert len(restored.lags[0].member_port_ids) == 2
    assert restored.ips[0].lag_id == restored.lags[0].id

    lanproj = tmp_path / "lag.lanproj"
    ProjectService(LocalSqliteRepository()).save_project(str(lanproj), snap)
    loaded = ProjectService(LocalSqliteRepository()).open_project(str(lanproj))
    assert len(loaded.lags) == 1
    assert loaded.lags[0].mode == LagMode.ACTIVE_BACKUP
    assert loaded.ips[0].lag_id == loaded.lags[0].id


def test_validation_lag_incomplete_links():
    snap = _snap()
    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SERVER, port_count=2
    )
    srv = inv.add_device(snap, dtype.id, "srv1")
    rtr_type = inv.add_device_type(
        snap, vendor="R", model="1", role=DeviceRole.ROUTER, port_count=2
    )
    rtr = inv.add_device(snap, rtr_type.id, "rtr1")
    sport = inv.ports_for_device(snap, srv.id)
    rport = inv.ports_for_device(snap, rtr.id)
    inv.add_lag(
        snap,
        device_id=srv.id,
        name="bond0",
        mode=LagMode.ACTIVE_BACKUP,
        member_port_ids=[sport[0].id, sport[1].id],
    )
    inv.add_cable(snap, sport[0].id, rport[0].id, label="uplink1", kind=CableKind.COPPER)
    issues = validation_svc.validate_project(snap)
    assert any(i.code == "lag_incomplete_links" for i in issues)
