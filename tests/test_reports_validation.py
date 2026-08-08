from __future__ import annotations

from landesigner.domain.entities import ProjectMeta, ProjectSnapshot, Site
from landesigner.domain.enums import CableKind, DeviceRole, PortMode, PortStatus
from landesigner.services import floor_plan as fp
from landesigner.services import inventory as inv
from landesigner.services import reports as reports_svc
from landesigner.services import topology as topo
from landesigner.services import validation as validation_svc
from landesigner.services.reports import ReportKind
from landesigner.services.validation import IssueSeverity


def _base_snap() -> ProjectSnapshot:
    meta = ProjectMeta(name="R")
    site = Site(project_id=meta.id, name="S")
    return ProjectSnapshot(meta=meta, sites=[site])


def test_validation_finds_duplicate_ip_and_cable_label():
    from landesigner.domain.entities import IpAddress

    snap = _base_snap()
    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SWITCH, port_count=2
    )
    a = inv.add_device(snap, dtype.id, "sw-a")
    b = inv.add_device(snap, dtype.id, "sw-b")
    pa = inv.ports_for_device(snap, a.id)[0]
    pb = inv.ports_for_device(snap, b.id)[0]
    inv.add_ip(snap, address="10.0.0.1", port_id=pa.id)
    # Обход API: симулируем битые данные с дублем IP.
    snap.ips.append(
        IpAddress(site_id=snap.sites[0].id, address="10.0.0.1", port_id=None)
    )
    inv.add_cable(snap, pa.id, pb.id, label="", kind=CableKind.COPPER)

    issues = validation_svc.validate_project(snap)
    codes = {i.code for i in issues}
    assert "duplicate_ip" in codes
    assert "cable_no_label" in codes
    stats = validation_svc.summary(issues)
    assert stats["errors"] >= 1
    assert stats["warnings"] >= 1


def test_validation_dangling_occupied_port():
    snap = _base_snap()
    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SWITCH, port_count=1
    )
    device = inv.add_device(snap, dtype.id, "sw1")
    port = inv.ports_for_device(snap, device.id)[0]
    port.status = PortStatus.OCCUPIED

    issues = validation_svc.validate_project(snap)
    assert any(i.code == "occupied_without_cable" for i in issues)


def test_validation_device_off_topology_and_plan():
    snap = _base_snap()
    building = inv.add_building(snap, "B")
    floor = inv.add_floor(snap, building.id, "F1")
    room = inv.add_room(snap, floor.id, "R1")
    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SWITCH, port_count=1
    )
    inv.add_device(snap, dtype.id, "sw1", room_id=room.id)

    issues = validation_svc.validate_project(snap)
    codes = {i.code for i in issues}
    assert "device_off_topology" in codes
    assert "device_off_floor_plan" in codes

    topo.ensure_topology(snap)
    fp.ensure_assets_for_floor(snap, floor.id)
    issues2 = validation_svc.validate_project(snap)
    codes2 = {i.code for i in issues2}
    assert "device_off_topology" not in codes2
    assert "device_off_floor_plan" not in codes2


def test_reports_devices_ports_cables_vlans():
    snap = _base_snap()
    dtype = inv.add_device_type(
        snap, vendor="Cisco", model="2960", role=DeviceRole.SWITCH, port_count=2
    )
    a = inv.add_device(snap, dtype.id, "core", serial="SN1", inventory_tag="IT-1")
    b = inv.add_device(snap, dtype.id, "acc")
    pa = inv.ports_for_device(snap, a.id)[0]
    pb = inv.ports_for_device(snap, b.id)[0]
    v10 = inv.add_vlan(snap, 10, "Users", "Офис")
    inv.set_port_network(
        snap, pa.id, mode=PortMode.ACCESS, access_vlan_id=v10.id, tagged_vlan_ids=[]
    )
    inv.add_ip(snap, address="10.0.0.2", cidr="24", port_id=pa.id)
    inv.add_cable(snap, pa.id, pb.id, label="Uplink", kind=CableKind.COPPER, length_m=5)

    devices = reports_svc.build_report(snap, ReportKind.DEVICES)
    assert devices.rows
    assert devices.rows[0][0] in {"acc", "core"}

    ports = reports_svc.build_report(snap, ReportKind.PORTS)
    assert len(ports.rows) == 4
    assert any("10.0.0.2" in row[7] for row in ports.rows)

    cables = reports_svc.build_report(snap, ReportKind.CABLES)
    assert cables.rows[0][0] == "Uplink"
    assert "5" in cables.rows[0][3]

    vlans = reports_svc.build_report(snap, ReportKind.VLANS)
    assert vlans.rows[0][0] == "10"
    assert vlans.rows[0][1] == "Users"
    assert vlans.rows[0][2] == "Офис"

    csv_text = reports_svc.report_to_csv(cables)
    assert "Uplink" in csv_text
    html = reports_svc.report_to_html(devices, project_name="Demo")
    assert "Demo" in html
    assert "<table>" in html


def test_issue_code_labels_russian():
    assert validation_svc.issue_code_label("cable_no_label") == "Кабель без метки"
    assert validation_svc.issue_code_label("duplicate_ip") == "Дублирующий IP"
    issue = validation_svc.ValidationIssue(
        IssueSeverity.WARNING, "cable_no_label", "msg"
    )
    assert issue.code_label == "Кабель без метки"
