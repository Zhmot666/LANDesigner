from __future__ import annotations

from pathlib import Path

from landesigner.domain.entities import ProjectMeta, ProjectSnapshot, Site
from landesigner.domain.enums import CableKind, DeviceRole, PortMode
from landesigner.services import import_export as csv_io
from landesigner.services import inventory as inv


def _sample_snapshot() -> ProjectSnapshot:
    meta = ProjectMeta(name="CSV Demo", revision=3)
    site = Site(project_id=meta.id, name="HQ", address="Street 1", notes="note")
    snap = ProjectSnapshot(meta=meta, sites=[site])

    building = inv.add_building(snap, "B1")
    floor = inv.add_floor(snap, building.id, "F1", level=1)
    room = inv.add_room(snap, floor.id, "R1")
    rack = inv.add_rack(snap, room.id, "Rack-A", units=42)

    dtype = inv.add_device_type(
        snap,
        vendor="Cisco",
        model="2960",
        role=DeviceRole.SWITCH,
        port_groups=[
            {"prefix": "Gi1/0/", "count": 2, "media": "COPPER", "speed": 1000, "start": 1},
        ],
    )
    a = inv.add_device(
        snap,
        dtype.id,
        "core-sw",
        serial="SN1",
        inventory_tag="IT-1",
        room_id=room.id,
        rack_id=rack.id,
    )
    b = inv.add_device(snap, dtype.id, "acc-sw", serial="SN2")
    port_a = inv.ports_for_device(snap, a.id)[0]
    port_b = inv.ports_for_device(snap, b.id)[0]

    v10 = inv.add_vlan(snap, 10, "Users", "User access")
    v30 = inv.add_vlan(snap, 30, "Cam", "Cameras")
    inv.set_port_network(
        snap,
        port_a.id,
        mode=PortMode.TRUNK,
        access_vlan_id=v10.id,
        tagged_vlan_ids=[v30.id],
    )
    inv.add_ip(snap, address="10.0.0.1", cidr="24", gateway="10.0.0.254", port_id=port_a.id)
    inv.add_cable(
        snap,
        port_a.id,
        port_b.id,
        label="Uplink",
        kind=CableKind.COPPER,
        length_m=3.5,
    )
    return snap


def test_csv_round_trip_preserves_ids_and_links():
    original = _sample_snapshot()
    text = csv_io.export_to_text(original)
    assert text.startswith(csv_io.FORMAT_MAGIC)
    assert "#section=devices" in text

    restored = csv_io.import_from_text(text)

    assert restored.meta.id == original.meta.id
    assert restored.meta.name == "CSV Demo"
    assert restored.meta.revision == 3
    assert restored.sites[0].name == "HQ"
    assert restored.sites[0].address == "Street 1"
    assert len(restored.buildings) == 1
    assert len(restored.device_types) == 1
    assert restored.device_types[0].port_template == original.device_types[0].port_template
    assert {d.hostname for d in restored.devices} == {"core-sw", "acc-sw"}
    assert len(restored.ports) == 4
    assert len(restored.vlans) == 2
    assert len(restored.cables) == 1
    assert len(restored.ips) == 1

    # UUID связей сохранились
    assert {p.id for p in restored.ports} == {p.id for p in original.ports}
    cable = restored.cables[0]
    assert cable.label == "Uplink"
    assert cable.length_m == 3.5
    assert cable.end_a_port_id in {p.id for p in restored.ports}
    assert cable.end_b_port_id in {p.id for p in restored.ports}

    trunk = next(p for p in restored.ports if p.mode == PortMode.TRUNK)
    assert trunk.access_vlan_id == original.vlans[0].id
    assert original.vlans[1].id in trunk.tagged_vlan_ids
    assert restored.ips[0].address == "10.0.0.1"
    by_vid = {v.vlan_id: v for v in restored.vlans}
    assert by_vid[10].description == "User access"
    assert by_vid[30].description == "Cameras"


def test_csv_file_round_trip(tmp_path: Path):
    original = _sample_snapshot()
    path = tmp_path / "demo.ldcsv"
    csv_io.export_snapshot(original, path)
    restored = csv_io.import_snapshot(path)
    assert restored.meta.name == original.meta.name
    assert len(restored.devices) == len(original.devices)
    assert len(restored.cables) == 1


def test_csv_rejects_bad_magic():
    try:
        csv_io.import_from_text("id,name\n1,x\n")
        assert False, "expected error"
    except csv_io.CsvFormatError:
        pass


def test_csv_rejects_unknown_version():
    body = "#LANDESIGNER_CSV;version=99\n#section=meta\nid,name\n"
    try:
        csv_io.import_from_text(body)
        assert False, "expected error"
    except csv_io.CsvFormatError as exc:
        assert "верси" in str(exc).lower() or "version" in str(exc).lower() or "Неподдерживаемая" in str(exc)
