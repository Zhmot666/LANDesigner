from __future__ import annotations

from pathlib import Path

from landesigner.adapters.local_sqlite.repository import LocalSqliteRepository
from landesigner.domain.entities import ProjectMeta, ProjectSnapshot, Site
from landesigner.domain.enums import CableKind, DeviceRole
from landesigner.services import inventory as inv
from landesigner.services import topology as topo
from landesigner.services.project import ProjectService


def _snap_with_devices() -> ProjectSnapshot:
    meta = ProjectMeta(name="Topo")
    site = Site(project_id=meta.id, name="S")
    snap = ProjectSnapshot(meta=meta, sites=[site])
    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SWITCH, port_count=2
    )
    a = inv.add_device(snap, dtype.id, "sw-a")
    b = inv.add_device(snap, dtype.id, "sw-b")
    port_a = inv.ports_for_device(snap, a.id)[0]
    port_b = inv.ports_for_device(snap, b.id)[0]
    inv.add_cable(snap, port_a.id, port_b.id, label="L1", kind=CableKind.COPPER)
    return snap


def test_ensure_topology_creates_nodes_and_links():
    snap = _snap_with_devices()
    assert snap.topology_nodes == []
    assert snap.topology_links == []

    changed = topo.ensure_topology(snap)
    assert changed
    assert len(snap.topology_nodes) == 2
    assert len(snap.topology_links) == 1
    assert snap.topology_links[0].cable_id == snap.cables[0].id

    # Повторный вызов идемпотентен.
    assert not topo.ensure_topology(snap)


def test_move_node_updates_coordinates():
    snap = _snap_with_devices()
    topo.ensure_topology(snap)
    node = snap.topology_nodes[0]
    topo.move_node(snap, node.id, 321.5, 44.0)
    assert node.x == 320.0
    assert node.y == 40.0


def test_delete_device_removes_topology_node():
    snap = _snap_with_devices()
    topo.ensure_topology(snap)
    device_id = snap.devices[0].id
    inv.delete_device(snap, device_id)
    assert all(n.device_id != device_id for n in snap.topology_nodes)
    # ensure подчистит осиротевшие линки после удаления через inventory
    topo.ensure_topology(snap)
    assert len(snap.topology_nodes) == 1


def test_topology_persists_in_lanproj(tmp_path: Path):
    snap = _snap_with_devices()
    topo.ensure_topology(snap)
    snap.topology_nodes[0].x = 111
    snap.topology_nodes[0].y = 222

    path = tmp_path / "t.lanproj"
    service = ProjectService(LocalSqliteRepository())
    service.save_project(str(path), snap)
    loaded = service.open_project(str(path))

    assert len(loaded.topology_nodes) == 2
    assert len(loaded.topology_links) == 1
    node = next(n for n in loaded.topology_nodes if n.x == 111)
    assert node.y == 222
    assert loaded.topology_links[0].cable_id == loaded.cables[0].id


def test_restore_cable_round_trip():
    snap = _snap_with_devices()
    cable = snap.cables[0]
    port_a = cable.end_a_port_id
    port_b = cable.end_b_port_id
    inv.delete_cable(snap, cable.id)
    assert snap.cables == []
    assert inv.ports_for_device(snap, snap.devices[0].id)[0].status.value == "FREE"

    inv.restore_cable(snap, cable)
    assert len(snap.cables) == 1
    assert snap.cables[0].id == cable.id
    assert next(p for p in snap.ports if p.id == port_a).status.value == "OCCUPIED"
    assert next(p for p in snap.ports if p.id == port_b).status.value == "OCCUPIED"


def test_link_caption_includes_ports_and_label():
    snap = _snap_with_devices()
    cable = snap.cables[0]
    caption = topo.link_caption(snap, cable.id)
    assert "L1" in caption
    assert "↔" in caption
    port_a = next(p for p in snap.ports if p.id == cable.end_a_port_id)
    assert port_a.name in caption


def test_link_caption_includes_vlan_and_speed():
    from landesigner.domain.enums import PortMode

    snap = _snap_with_devices()
    cable = snap.cables[0]
    port_a = next(p for p in snap.ports if p.id == cable.end_a_port_id)
    port_b = next(p for p in snap.ports if p.id == cable.end_b_port_id)
    vlan = inv.add_vlan(snap, 20, "Users")
    inv.set_port_network(
        snap, port_a.id, mode=PortMode.ACCESS, access_vlan_id=vlan.id, tagged_vlan_ids=[]
    )
    inv.set_port_network(
        snap, port_b.id, mode=PortMode.ACCESS, access_vlan_id=vlan.id, tagged_vlan_ids=[]
    )
    caption = topo.link_caption(snap, cable.id)
    assert "V20" in caption
    assert "1G" in caption or "1000" in caption


def test_snap_and_auto_layout():
    snap = _snap_with_devices()
    topo.ensure_topology(snap)
    assert topo.snap_coord(23) == 20.0
    assert topo.snap_point(23, 37) == (20.0, 40.0)

    for i, node in enumerate(snap.topology_nodes):
        node.x = 10 + i * 3
        node.y = 10 + i * 5
    changes = topo.auto_layout(snap)
    assert changes
    for node in snap.topology_nodes:
        assert node.x % 20 == 0
        assert node.y % 20 == 0
    # Идемпотентность при уже разложенном
    again = topo.auto_layout(snap)
    assert again == {}


def test_move_nodes_command_group_undo():
    from PySide6.QtWidgets import QApplication

    from landesigner.ui.commands.topology_commands import MoveNodesCommand

    _ = QApplication.instance() or QApplication([])
    snap = _snap_with_devices()
    topo.ensure_topology(snap)
    a, b = snap.topology_nodes[0], snap.topology_nodes[1]
    old_a, old_b = (a.x, a.y), (b.x, b.y)
    changes = {
        a.id: (old_a[0], old_a[1], 200.0, 120.0),
        b.id: (old_b[0], old_b[1], 240.0, 160.0),
    }
    cmd = MoveNodesCommand(snap, changes)
    cmd.redo()
    assert (a.x, a.y) == (200.0, 120.0)
    assert (b.x, b.y) == (240.0, 160.0)
    cmd.undo()
    assert (a.x, a.y) == old_a
    assert (b.x, b.y) == old_b


def test_add_delete_cable_commands_undo():
    from PySide6.QtWidgets import QApplication

    from landesigner.ui.commands.topology_commands import AddCableCommand, DeleteCableCommand

    _ = QApplication.instance() or QApplication([])
    meta = ProjectMeta(name="T")
    site = Site(project_id=meta.id, name="S")
    snap = ProjectSnapshot(meta=meta, sites=[site])
    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SWITCH, port_count=2
    )
    a = inv.add_device(snap, dtype.id, "sw-a")
    b = inv.add_device(snap, dtype.id, "sw-b")
    topo.ensure_topology(snap)
    port_a = inv.ports_for_device(snap, a.id)[0]
    port_b = inv.ports_for_device(snap, b.id)[0]

    rebuilds = {"n": 0}

    def on_changed():
        rebuilds["n"] += 1

    add_cmd = AddCableCommand(
        snap,
        port_a.id,
        port_b.id,
        label="Uplink",
        kind=CableKind.COPPER,
        on_changed=on_changed,
    )
    add_cmd.redo()
    assert len(snap.cables) == 1
    assert len(snap.topology_links) == 1
    cable_id = snap.cables[0].id

    add_cmd.undo()
    assert snap.cables == []
    assert snap.topology_links == []

    add_cmd.redo()
    assert snap.cables[0].id == cable_id
    assert len(snap.topology_links) == 1

    del_cmd = DeleteCableCommand(snap, cable_id, on_changed=on_changed)
    del_cmd.redo()
    assert snap.cables == []
    del_cmd.undo()
    assert len(snap.cables) == 1
    assert snap.cables[0].id == cable_id
    assert rebuilds["n"] >= 4
