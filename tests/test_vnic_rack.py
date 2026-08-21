from __future__ import annotations

from pathlib import Path

import pytest

from landesigner.adapters.local_sqlite.repository import LocalSqliteRepository
from landesigner.domain.entities import ProjectMeta, ProjectSnapshot, Site
from landesigner.domain.enums import DeviceRole, PortMedia
from landesigner.services import inventory as inv
from landesigner.services import validation as validation_svc


def _base() -> ProjectSnapshot:
    meta = ProjectMeta(name="Vnic")
    site = Site(project_id=meta.id, name="S")
    return ProjectSnapshot(meta=meta, sites=[site])


def test_vm_ports_are_vnic_and_map_to_host_nic():
    snap = _base()
    hv_type = inv.add_device_type(
        snap, vendor="VMware", model="ESXi", role=DeviceRole.HYPERVISOR, port_count=2
    )
    vm_type = inv.add_device_type(
        snap, vendor="Generic", model="VM", role=DeviceRole.VIRTUAL_MACHINE, port_count=2
    )
    host = inv.add_device(snap, hv_type.id, "esxi-1")
    vm = inv.add_device(snap, vm_type.id, "vm-1", host_device_id=host.id)
    vm_ports = inv.ports_for_device(snap, vm.id)
    assert len(vm_ports) == 2
    assert all(p.media == PortMedia.VIRTUAL for p in vm_ports)
    assert vm_ports[0].name == "vNIC0"

    host_nic = inv.ports_for_device(snap, host.id)[0]
    inv.set_vnic_host_port(snap, vm_ports[0].id, host_nic.id)
    assert vm_ports[0].host_port_id == host_nic.id
    assert inv.vnic_host_port_label(snap, vm_ports[0].id) == inv.port_endpoint_label(
        snap, host_nic.id
    )

    with pytest.raises(ValueError, match="гипервизор"):
        inv.set_vnic_host_port(snap, vm_ports[1].id, vm_ports[0].id)


def test_vm_host_change_clears_vnic_mapping():
    snap = _base()
    hv_type = inv.add_device_type(
        snap, vendor="VMware", model="ESXi", role=DeviceRole.HYPERVISOR, port_count=1
    )
    vm_type = inv.add_device_type(
        snap, vendor="Generic", model="VM", role=DeviceRole.VIRTUAL_MACHINE, port_count=1
    )
    host_a = inv.add_device(snap, hv_type.id, "esxi-a")
    host_b = inv.add_device(snap, hv_type.id, "esxi-b")
    vm = inv.add_device(snap, vm_type.id, "vm-1", host_device_id=host_a.id)
    vnic = inv.ports_for_device(snap, vm.id)[0]
    inv.set_vnic_host_port(snap, vnic.id, inv.ports_for_device(snap, host_a.id)[0].id)
    inv.update_device(snap, vm.id, host_device_id=host_b.id)
    assert vnic.host_port_id is None


def test_vnic_validation_warnings():
    snap = _base()
    hv_type = inv.add_device_type(
        snap, vendor="VMware", model="ESXi", role=DeviceRole.HYPERVISOR, port_count=1
    )
    vm_type = inv.add_device_type(
        snap, vendor="Generic", model="VM", role=DeviceRole.VIRTUAL_MACHINE, port_count=1
    )
    host = inv.add_device(snap, hv_type.id, "esxi-1")
    vm = inv.add_device(snap, vm_type.id, "vm-1", host_device_id=host.id)
    issues = validation_svc.validate_project(snap)
    vnic = inv.ports_for_device(snap, vm.id)[0]
    codes = [i.code for i in issues if i.entity_id == vnic.id]
    assert "vnic_missing_host_nic" in codes


def test_host_port_id_roundtrip(tmp_path: Path):
    snap = _base()
    hv_type = inv.add_device_type(
        snap, vendor="X", model="HV", role=DeviceRole.HYPERVISOR, port_count=1
    )
    vm_type = inv.add_device_type(
        snap, vendor="X", model="VM", role=DeviceRole.VIRTUAL_MACHINE, port_count=1
    )
    host = inv.add_device(snap, hv_type.id, "host")
    vm = inv.add_device(snap, vm_type.id, "vm", host_device_id=host.id)
    vnic = inv.ports_for_device(snap, vm.id)[0]
    nic = inv.ports_for_device(snap, host.id)[0]
    inv.set_vnic_host_port(snap, vnic.id, nic.id)

    path = tmp_path / "vnic.lanproj"
    repo = LocalSqliteRepository()
    repo.save_project(str(path), snap)
    loaded = repo.load_project(str(path))
    vnic2 = next(p for p in loaded.ports if p.id == vnic.id)
    assert vnic2.host_port_id == nic.id
