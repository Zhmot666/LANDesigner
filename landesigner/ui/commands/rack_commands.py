from __future__ import annotations

from uuid import UUID

from PySide6.QtGui import QUndoCommand

from landesigner.domain.entities import ProjectSnapshot
from landesigner.services import inventory as inv


class MoveRackDeviceCommand(QUndoCommand):
    def __init__(
        self,
        snapshot: ProjectSnapshot,
        device_id: UUID,
        old_rack_u: int,
        new_rack_u: int,
        on_changed=None,
    ) -> None:
        super().__init__("Перемещение в стойке")
        self._snapshot = snapshot
        self._device_id = device_id
        self._old = int(old_rack_u)
        self._new = int(new_rack_u)
        self._on_changed = on_changed

    def _apply(self, rack_u: int) -> None:
        device = next((d for d in self._snapshot.devices if d.id == self._device_id), None)
        if device is None or device.rack_id is None:
            return
        inv.set_device_rack_placement(
            self._snapshot,
            self._device_id,
            rack_id=device.rack_id,
            rack_u=rack_u,
            rack_u_height=device.rack_u_height,
            room_id=device.room_id,
        )

    def redo(self) -> None:
        self._apply(self._new)
        if self._on_changed:
            self._on_changed()

    def undo(self) -> None:
        self._apply(self._old)
        if self._on_changed:
            self._on_changed()


class MountRackDeviceCommand(QUndoCommand):
    def __init__(
        self,
        snapshot: ProjectSnapshot,
        device_id: UUID,
        rack_id: UUID,
        rack_u: int,
        rack_u_height: int = 1,
        *,
        on_changed=None,
    ) -> None:
        super().__init__("Монтаж в стойку")
        self._snapshot = snapshot
        self._device_id = device_id
        self._rack_id = rack_id
        self._rack_u = int(rack_u)
        self._rack_u_height = max(1, int(rack_u_height))
        device = next((d for d in snapshot.devices if d.id == device_id), None)
        self._prev_rack_id = device.rack_id if device is not None else None
        self._prev_rack_u = device.rack_u if device is not None else None
        self._prev_rack_h = device.rack_u_height if device is not None else 1
        self._prev_room_id = device.room_id if device is not None else None
        self._on_changed = on_changed
        rack = next((r for r in snapshot.racks if r.id == rack_id), None)
        self._target_room_id = rack.room_id if rack is not None else self._prev_room_id

    def _mount(
        self,
        rack_id: UUID | None,
        rack_u: int | None,
        rack_u_height: int,
        room_id,
    ) -> None:
        device = next((d for d in self._snapshot.devices if d.id == self._device_id), None)
        if device is None:
            return
        if rack_id is None:
            device.rack_id = None
            device.rack_u = None
            device.rack_u_height = 1
            if room_id is not None:
                device.room_id = room_id
            return
        inv.set_device_rack_placement(
            self._snapshot,
            self._device_id,
            rack_id=rack_id,
            rack_u=rack_u,
            rack_u_height=rack_u_height,
            room_id=room_id,
        )

    def redo(self) -> None:
        self._mount(self._rack_id, self._rack_u, self._rack_u_height, self._target_room_id)
        if self._on_changed:
            self._on_changed()

    def undo(self) -> None:
        self._mount(
            self._prev_rack_id,
            self._prev_rack_u,
            self._prev_rack_h,
            self._prev_room_id,
        )
        if self._on_changed:
            self._on_changed()
