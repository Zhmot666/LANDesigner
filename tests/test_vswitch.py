from __future__ import annotations

from pathlib import Path

import pytest

from landesigner.adapters.local_sqlite.repository import LocalSqliteRepository
from landesigner.domain.entities import ProjectMeta, ProjectSnapshot, Site
from landesigner.domain.enums import DeviceRole, PortMedia
from landesigner.services import import_export as csv_io
from landesigner.services import inventory as inv
from landesigner.services import validation as validation_svc


def _base() -> ProjectSnapshot:
    meta = ProjectMeta(name="VSwitch")
    site = Site(project_id=meta.id, name="S")
    return ProjectSnapshot(meta=meta, sites=[site])


def _hv_vm(snap: ProjectSnapshot):
    hv_type = inv.add_device_type(
        snap, vendor="VMware", model="ESXi", role=DeviceRole.HYPERVISOR, port_count=2
    )
    vm_type = inv.add_device_type(
        snap, vendor="Generic", model="VM", role=DeviceRole.VIRTUAL_MACHINE, port_count=1
    )
    host = inv.add_device(snap, hv_type.id, "esxi-1")
    vm = inv.add_device(snap, vm_type.id, "vm-1", host_device_id=host.id)
    return host, vm


def test_vswitch_port_group_and_vnic_binding():
    snap = _base()
    host, vm = _hv_vm(snap)
    nics = inv.ports_for_device(snap, host.id)
    vs = inv.add_virtual_switch(
        snap, host.id, "vSwitch0", uplink_port_ids=[nics[0].id]
    )
    vlan = inv.add_vlan(snap, 100, "App")
    pg = inv.add_port_group(snap, vs.id, "VM Network", vlan_id=vlan.id)
    vnic = inv.ports_for_device(snap, vm.id)[0]
    inv.set_vnic_port_group(snap, vnic.id, pg.id)
    assert vnic.port_group_id == pg.id
    assert vnic.host_port_id is None
    assert "vSwitch0/VM Network" in inv.vnic_binding_label(snap, vnic.id)
    assert "VLAN 100" in inv.vnic_binding_label(snap, vnic.id)

    # Прямой NIC сбрасывает PG
    inv.set_vnic_host_port(snap, vnic.id, nics[1].id)
    assert vnic.host_port_id == nics[1].id
    assert vnic.port_group_id is None


def test_vswitch_uplink_exclusive_and_validation():
    snap = _base()
    host, vm = _hv_vm(snap)
    nic = inv.ports_for_device(snap, host.id)[0]
    inv.add_virtual_switch(snap, host.id, "vs0", uplink_port_ids=[nic.id])
    with pytest.raises(ValueError, match="уже uplink"):
        inv.add_virtual_switch(snap, host.id, "vs1", uplink_port_ids=[nic.id])

    vs_empty = inv.add_virtual_switch(snap, host.id, "vs-empty")
    issues = validation_svc.validate_project(snap)
    assert any(i.code == "vswitch_no_uplink" and i.entity_id == vs_empty.id for i in issues)
    vnic = inv.ports_for_device(snap, vm.id)[0]
    assert any(i.code == "vnic_missing_host_nic" and i.entity_id == vnic.id for i in issues)


def test_vswitch_sqlite_and_csv_roundtrip(tmp_path: Path):
    snap = _base()
    host, vm = _hv_vm(snap)
    nic = inv.ports_for_device(snap, host.id)[0]
    vs = inv.add_virtual_switch(snap, host.id, "vSwitch0", uplink_port_ids=[nic.id])
    pg = inv.add_port_group(snap, vs.id, "PG1")
    vnic = inv.ports_for_device(snap, vm.id)[0]
    inv.set_vnic_port_group(snap, vnic.id, pg.id)

    path = tmp_path / "vs.lanproj"
    repo = LocalSqliteRepository()
    repo.save_project(str(path), snap)
    loaded = repo.load_project(str(path))
    assert len(loaded.virtual_switches) == 1
    assert loaded.virtual_switches[0].uplink_port_ids == [nic.id]
    assert len(loaded.port_groups) == 1
    loaded_vnic = next(p for p in loaded.ports if p.media == PortMedia.VIRTUAL)
    assert loaded_vnic.port_group_id == pg.id

    text = csv_io.export_to_text(snap)
    restored = csv_io.import_from_text(text)
    assert len(restored.virtual_switches) == 1
    assert len(restored.port_groups) == 1
    r_vnic = next(p for p in restored.ports if p.media == PortMedia.VIRTUAL)
    assert r_vnic.port_group_id == pg.id
