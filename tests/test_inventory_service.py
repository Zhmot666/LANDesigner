from landesigner.domain.entities import ProjectMeta, ProjectSnapshot, Site
from landesigner.domain.enums import CableKind, DeviceRole, PortMedia, PortStatus
from landesigner.services import inventory as inv


def test_add_hierarchy_and_device_with_ports():
    meta = ProjectMeta(name="T")
    site = Site(project_id=meta.id, name="S")
    snap = ProjectSnapshot(meta=meta, sites=[site])

    building = inv.add_building(snap, "B1")
    floor = inv.add_floor(snap, building.id, "F1", level=1)
    room = inv.add_room(snap, floor.id, "R1")
    rack = inv.add_rack(snap, room.id, "Rack1", units=42)

    dtype = inv.add_device_type(
        snap,
        vendor="Cisco",
        model="2960",
        role=DeviceRole.SWITCH,
        port_groups=[
            {"prefix": "Gi1/0/", "count": 4, "media": "COPPER", "speed": 1000, "start": 1},
            {"prefix": "Te1/0/", "count": 2, "media": "FIBER", "speed": 10000, "start": 1},
        ],
    )
    device = inv.add_device(
        snap,
        device_type_id=dtype.id,
        hostname="sw1",
        serial="ABC",
        inventory_tag="IT-1",
        room_id=room.id,
        rack_id=rack.id,
    )

    ports = inv.ports_for_device(snap, device.id)
    assert len(ports) == 6
    assert ports[0].status == PortStatus.FREE
    assert ports[0].name == "Gi1/0/1"
    assert ports[0].speed == 1000
    assert ports[-1].name == "Te1/0/2"
    assert ports[-1].speed == 10000
    assert device.role == DeviceRole.SWITCH

    inv.delete_device(snap, device.id)
    assert snap.devices == []
    assert inv.ports_for_device(snap, device.id) == []


def test_add_and_delete_cable_updates_port_status():
    meta = ProjectMeta(name="T")
    site = Site(project_id=meta.id, name="S")
    snap = ProjectSnapshot(meta=meta, sites=[site])
    dtype = inv.add_device_type(
        snap,
        vendor="Cisco",
        model="2960",
        role=DeviceRole.SWITCH,
        port_groups=[
            {"prefix": "Gi1/0/", "count": 2, "media": "COPPER", "speed": 1000, "start": 1},
        ],
    )
    a = inv.add_device(snap, dtype.id, "sw-a")
    b = inv.add_device(snap, dtype.id, "sw-b")
    port_a = inv.ports_for_device(snap, a.id)[0]
    port_b = inv.ports_for_device(snap, b.id)[0]

    cable = inv.add_cable(
        snap,
        port_a.id,
        port_b.id,
        label="C1",
        kind=CableKind.COPPER,
        length_m=3.5,
    )
    assert port_a.status == PortStatus.OCCUPIED
    assert port_b.status == PortStatus.OCCUPIED
    assert inv.peer_port(snap, port_a.id).id == port_b.id
    assert inv.port_endpoint_label(snap, port_a.id) == "sw-a / Gi1/0/1"

    inv.delete_cable(snap, cable.id)
    assert snap.cables == []
    assert port_a.status == PortStatus.FREE
    assert port_b.status == PortStatus.FREE


def test_cable_rejects_busy_and_media_mismatch():
    meta = ProjectMeta(name="T")
    site = Site(project_id=meta.id, name="S")
    snap = ProjectSnapshot(meta=meta, sites=[site])
    dtype = inv.add_device_type(
        snap,
        vendor="X",
        model="Y",
        role=DeviceRole.SWITCH,
        port_groups=[
            {"prefix": "Gi", "count": 1, "media": "COPPER", "speed": 1000, "start": 1},
            {"prefix": "Te", "count": 1, "media": "FIBER", "speed": 10000, "start": 1},
        ],
    )
    a = inv.add_device(snap, dtype.id, "a")
    b = inv.add_device(snap, dtype.id, "b")
    copper_a = next(p for p in inv.ports_for_device(snap, a.id) if p.media == PortMedia.COPPER)
    fiber_b = next(p for p in inv.ports_for_device(snap, b.id) if p.media == PortMedia.FIBER)
    copper_b = next(p for p in inv.ports_for_device(snap, b.id) if p.media == PortMedia.COPPER)

    try:
        inv.add_cable(snap, copper_a.id, fiber_b.id, kind=CableKind.COPPER)
        assert False, "expected media mismatch"
    except ValueError:
        pass

    inv.add_cable(snap, copper_a.id, copper_b.id, kind=CableKind.COPPER)
    try:
        inv.add_cable(
            snap,
            inv.ports_for_device(snap, a.id)[1].id,
            copper_b.id,
            kind=CableKind.FIBER,
        )
        assert False, "expected busy port"
    except ValueError:
        pass


def test_delete_device_frees_peer_port():
    meta = ProjectMeta(name="T")
    site = Site(project_id=meta.id, name="S")
    snap = ProjectSnapshot(meta=meta, sites=[site])
    dtype = inv.add_device_type(
        snap,
        vendor="X",
        model="Y",
        role=DeviceRole.SWITCH,
        port_count=1,
    )
    a = inv.add_device(snap, dtype.id, "a")
    b = inv.add_device(snap, dtype.id, "b")
    port_a = inv.ports_for_device(snap, a.id)[0]
    port_b = inv.ports_for_device(snap, b.id)[0]
    inv.add_cable(snap, port_a.id, port_b.id, kind=CableKind.COPPER)

    inv.delete_device(snap, a.id)
    assert snap.cables == []
    assert port_b.status == PortStatus.FREE


def test_vlan_and_ip_on_port():
    meta = ProjectMeta(name="T")
    site = Site(project_id=meta.id, name="S")
    snap = ProjectSnapshot(meta=meta, sites=[site])
    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SWITCH, port_count=2
    )
    device = inv.add_device(snap, dtype.id, "sw1")
    port = inv.ports_for_device(snap, device.id)[0]

    vlan = inv.add_vlan(snap, 10, "Users")
    inv.set_port_access_vlan(snap, port.id, vlan.id)
    assert port.access_vlan_id == vlan.id
    assert inv.vlan_label(snap, vlan.id) == "10 Users"

    ip = inv.add_ip(
        snap, address="10.0.0.2", cidr="24", gateway="10.0.0.1", port_id=port.id
    )
    assert inv.ip_label(ip) == "10.0.0.2/24"
    assert inv.ips_for_port(snap, port.id) == [ip]

    try:
        inv.add_ip(snap, address="10.0.0.2", port_id=None)
        assert False, "expected duplicate IP"
    except ValueError:
        pass

    try:
        inv.add_vlan(snap, 10, "Dup")
        assert False, "expected duplicate VLAN"
    except ValueError:
        pass

    inv.delete_vlan(snap, vlan.id)
    assert port.access_vlan_id is None
    inv.delete_ip(snap, ip.id)
    assert inv.ips_for_port(snap, port.id) == []


def test_trunk_tagged_vlans():
    from landesigner.domain.enums import PortMode

    meta = ProjectMeta(name="T")
    site = Site(project_id=meta.id, name="S")
    snap = ProjectSnapshot(meta=meta, sites=[site])
    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SWITCH, port_count=1
    )
    device = inv.add_device(snap, dtype.id, "sw1")
    port = inv.ports_for_device(snap, device.id)[0]
    v10 = inv.add_vlan(snap, 10, "Users")
    v30 = inv.add_vlan(snap, 30, "Cam")
    v99 = inv.add_vlan(snap, 99, "Native")

    inv.set_port_network(
        snap,
        port.id,
        mode=PortMode.TRUNK,
        access_vlan_id=v99.id,
        tagged_vlan_ids=[v10.id, v30.id],
    )
    assert port.mode == PortMode.TRUNK
    assert port.access_vlan_id == v99.id
    assert port.tagged_vlan_ids == [v10.id, v30.id]
    assert inv.port_vlan_summary(snap, port) == "T:n=99 Native;t=10,30"

    try:
        inv.set_port_network(
            snap,
            port.id,
            mode=PortMode.ACCESS,
            access_vlan_id=v10.id,
            tagged_vlan_ids=[v30.id],
        )
        assert False, "access cannot have tagged"
    except ValueError:
        pass

    inv.delete_vlan(snap, v30.id)
    assert v30.id not in port.tagged_vlan_ids
    assert v10.id in port.tagged_vlan_ids
