from __future__ import annotations

from landesigner.domain.entities import ProjectMeta, ProjectSnapshot, Site
from landesigner.domain.enums import CableKind, DeviceRole
from landesigner.services import cable_labels as lbl
from landesigner.services import inventory as inv


def _base() -> ProjectSnapshot:
    meta = ProjectMeta(name="L")
    site = Site(project_id=meta.id, name="Site-A")
    return ProjectSnapshot(meta=meta, sites=[site])


def test_suggest_wan_firewall_to_isp():
    snap = _base()
    fw_type = inv.add_device_type(
        snap, vendor="Fortinet", model="FG-70G", role=DeviceRole.FIREWALL, port_count=2
    )
    isp_type = inv.add_device_type(
        snap, vendor="ISP", model="CPE", role=DeviceRole.MODEM, port_count=1
    )
    fw = inv.add_device(snap, fw_type.id, "fg-edge")
    isp = inv.add_device(snap, isp_type.id, "ISP-CPE")
    wan = inv.ports_for_device(snap, fw.id)[0]
    wan.name = "wan1"
    isp_p = inv.ports_for_device(snap, isp.id)[0]

    purpose = lbl.suggest_cable_purpose(snap, wan.id, isp_p.id)
    assert purpose == "WAN"

    label = lbl.suggest_cable_label(snap, wan.id, isp_p.id, purpose=purpose, seq=1)
    assert label.startswith("CAB-0001 · WAN:")
    assert "fg-edge / wan1" in label
    assert "ISP-CPE" in label


def test_endpoint_order_is_stable():
    snap = _base()
    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SWITCH, port_count=1
    )
    a = inv.add_device(snap, dtype.id, "aaa")
    b = inv.add_device(snap, dtype.id, "bbb")
    pa = inv.ports_for_device(snap, a.id)[0]
    pb = inv.ports_for_device(snap, b.id)[0]

    one = lbl.endpoint_pair_label(snap, pa.id, pb.id)
    two = lbl.endpoint_pair_label(snap, pb.id, pa.id)
    assert one == two
    assert one.startswith("aaa")


def test_fill_missing_and_sequence_increment():
    snap = _base()
    from landesigner.domain.entities import Cable
    from landesigner.domain.enums import PortStatus

    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SWITCH, port_count=2
    )
    a = inv.add_device(snap, dtype.id, "sw-a")
    b = inv.add_device(snap, dtype.id, "sw-b")
    c = inv.add_device(snap, dtype.id, "sw-c")
    pa = inv.ports_for_device(snap, a.id)[1]
    pb = inv.ports_for_device(snap, b.id)[0]
    pc = inv.ports_for_device(snap, c.id)[0]
    inv.add_cable(snap, pa.id, pb.id, label="CAB-0003 · uplink: x", kind=CableKind.COPPER)
    empty = Cable(
        site_id=snap.sites[0].id,
        end_a_port_id=inv.ports_for_device(snap, a.id)[0].id,
        end_b_port_id=pc.id,
        label="",
    )
    snap.cables.append(empty)
    inv.ports_for_device(snap, a.id)[0].status = PortStatus.OCCUPIED
    pc.status = PortStatus.OCCUPIED

    assert lbl.next_cable_sequence(snap) == 4
    n = lbl.fill_missing_cable_labels(snap)
    assert n == 1
    assert empty.label.startswith("CAB-0004 ·")


def test_apply_if_missing_on_add_cable():
    snap = _base()
    fw_type = inv.add_device_type(
        snap, vendor="F", model="FG", role=DeviceRole.FIREWALL, port_count=1
    )
    isp_type = inv.add_device_type(
        snap, vendor="I", model="CPE", role=DeviceRole.MODEM, port_count=1
    )
    fw = inv.add_device(snap, fw_type.id, "fg")
    isp = inv.add_device(snap, isp_type.id, "isp")
    pa = inv.ports_for_device(snap, fw.id)[0]
    pb = inv.ports_for_device(snap, isp.id)[0]

    cable = inv.add_cable(snap, pa.id, pb.id, label="", purpose="", kind=CableKind.COPPER)
    assert cable.label.startswith("CAB-0001 · WAN:")
    assert cable.purpose == "WAN"


def test_collision_suffix():
    snap = _base()
    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SWITCH, port_count=1
    )
    a = inv.add_device(snap, dtype.id, "sw-a")
    b = inv.add_device(snap, dtype.id, "sw-b")
    pa = inv.ports_for_device(snap, a.id)[0]
    pb = inv.ports_for_device(snap, b.id)[0]
    base = lbl.suggest_cable_label(snap, pa.id, pb.id, purpose="uplink", seq=1)
    inv.add_cable(snap, pa.id, pb.id, label=base, kind=CableKind.COPPER)

    label = lbl.suggest_cable_label(snap, pa.id, pb.id, purpose="uplink", seq=1)
    assert label.endswith("#2")
