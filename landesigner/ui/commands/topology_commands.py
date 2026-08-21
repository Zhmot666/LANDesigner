from __future__ import annotations

from uuid import UUID

from PySide6.QtGui import QUndoCommand

from landesigner.domain.entities import Cable, ProjectSnapshot, TopologyLink
from landesigner.domain.enums import CableCategory, CableKind
from landesigner.services import inventory as inv
from landesigner.services import topology as topo


class MoveNodeCommand(QUndoCommand):
    def __init__(
        self,
        snapshot: ProjectSnapshot,
        node_id: UUID,
        old_x: float,
        old_y: float,
        new_x: float,
        new_y: float,
        on_changed=None,
    ) -> None:
        super().__init__("Перемещение узла")
        self._snapshot = snapshot
        self._node_id = node_id
        self._old = (old_x, old_y)
        self._new = (new_x, new_y)
        self._on_changed = on_changed

    def redo(self) -> None:
        topo.move_node(self._snapshot, self._node_id, *self._new)
        if self._on_changed:
            self._on_changed()

    def undo(self) -> None:
        topo.move_node(self._snapshot, self._node_id, *self._old)
        if self._on_changed:
            self._on_changed()


class MoveNodesCommand(QUndoCommand):
    """Групповое перемещение: node_id → (old_x, old_y, new_x, new_y)."""

    def __init__(
        self,
        snapshot: ProjectSnapshot,
        changes: dict[UUID, tuple[float, float, float, float]],
        on_changed=None,
        *,
        title: str = "Перемещение узлов",
    ) -> None:
        super().__init__(title)
        self._snapshot = snapshot
        self._changes = dict(changes)
        self._on_changed = on_changed

    def isObsolete(self) -> bool:  # noqa: N802
        return not self._changes

    def redo(self) -> None:
        topo.apply_layout_positions(
            self._snapshot,
            {nid: (nx, ny) for nid, (_ox, _oy, nx, ny) in self._changes.items()},
        )
        if self._on_changed:
            self._on_changed()

    def undo(self) -> None:
        topo.apply_layout_positions(
            self._snapshot,
            {nid: (ox, oy) for nid, (ox, oy, _nx, _ny) in self._changes.items()},
        )
        if self._on_changed:
            self._on_changed()


class LayoutTopologyCommand(MoveNodesCommand):
    """Автораскладка — тот же механизм, другой заголовок Undo."""

    def __init__(
        self,
        snapshot: ProjectSnapshot,
        changes: dict[UUID, tuple[float, float, float, float]],
        on_changed=None,
    ) -> None:
        super().__init__(
            snapshot, changes, on_changed, title="Автораскладка схемы"
        )

class AddCableCommand(QUndoCommand):
    def __init__(
        self,
        snapshot: ProjectSnapshot,
        end_a_port_id: UUID,
        end_b_port_id: UUID,
        *,
        label: str = "",
        kind: CableKind = CableKind.COPPER,
        category: CableCategory = CableCategory.OTHER,
        length_m: float | None = None,
        color: str = "",
        purpose: str = "",
        on_changed=None,
    ) -> None:
        super().__init__("Создание связи")
        self._snapshot = snapshot
        self._end_a = end_a_port_id
        self._end_b = end_b_port_id
        self._label = label
        self._kind = kind
        self._category = category
        self._length_m = length_m
        self._color = color
        self._purpose = purpose
        self._cable: Cable | None = None
        self._link: TopologyLink | None = None
        self._on_changed = on_changed

    def redo(self) -> None:
        if self._cable is None:
            self._cable = inv.add_cable(
                self._snapshot,
                self._end_a,
                self._end_b,
                label=self._label,
                kind=self._kind,
                category=self._category,
                length_m=self._length_m,
                color=self._color,
                purpose=self._purpose,
            )
            topo.ensure_topology(self._snapshot)
            self._link = topo.link_for_cable(self._snapshot, self._cable.id)
        else:
            inv.restore_cable(self._snapshot, self._cable)
            if self._link is not None:
                topo.restore_topology_link(self._snapshot, self._link)
            else:
                topo.ensure_topology(self._snapshot)
        if self._on_changed:
            self._on_changed()

    def undo(self) -> None:
        if self._cable is None:
            return
        inv.delete_cable(self._snapshot, self._cable.id)
        if self._on_changed:
            self._on_changed()


class DeleteCableCommand(QUndoCommand):
    def __init__(
        self,
        snapshot: ProjectSnapshot,
        cable_id: UUID,
        on_changed=None,
    ) -> None:
        super().__init__("Удаление связи")
        self._snapshot = snapshot
        self._cable = next((c for c in snapshot.cables if c.id == cable_id), None)
        self._link = topo.link_for_cable(snapshot, cable_id)
        self._on_changed = on_changed
        if self._cable is None:
            self.setObsolete(True)

    def redo(self) -> None:
        if self._cable is None:
            return
        inv.delete_cable(self._snapshot, self._cable.id)
        if self._on_changed:
            self._on_changed()

    def undo(self) -> None:
        if self._cable is None:
            return
        inv.restore_cable(self._snapshot, self._cable)
        if self._link is not None:
            topo.restore_topology_link(self._snapshot, self._link)
        else:
            topo.ensure_topology(self._snapshot)
        if self._on_changed:
            self._on_changed()
