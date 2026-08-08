from __future__ import annotations

from uuid import UUID

from PySide6.QtGui import QUndoCommand

from landesigner.domain.entities import ProjectSnapshot
from landesigner.services import floor_plan as fp


class MoveFloorAssetCommand(QUndoCommand):
    def __init__(
        self,
        snapshot: ProjectSnapshot,
        asset_id: UUID,
        old_x: float,
        old_y: float,
        new_x: float,
        new_y: float,
        on_changed=None,
    ) -> None:
        super().__init__("Перемещение на плане")
        self._snapshot = snapshot
        self._asset_id = asset_id
        self._old = (old_x, old_y)
        self._new = (new_x, new_y)
        self._on_changed = on_changed

    def redo(self) -> None:
        fp.move_asset(self._snapshot, self._asset_id, *self._new)
        if self._on_changed:
            self._on_changed()

    def undo(self) -> None:
        fp.move_asset(self._snapshot, self._asset_id, *self._old)
        if self._on_changed:
            self._on_changed()


class RemoveFloorAssetCommand(QUndoCommand):
    def __init__(
        self,
        snapshot: ProjectSnapshot,
        asset_id: UUID,
        on_changed=None,
    ) -> None:
        super().__init__("Удаление маркера с плана")
        self._snapshot = snapshot
        self._asset = next((a for a in snapshot.floor_plan_assets if a.id == asset_id), None)
        self._on_changed = on_changed
        if self._asset is None:
            self.setObsolete(True)

    def redo(self) -> None:
        if self._asset is None:
            return
        fp.remove_asset(self._snapshot, self._asset.id)
        if self._on_changed:
            self._on_changed()

    def undo(self) -> None:
        if self._asset is None:
            return
        if any(a.id == self._asset.id for a in self._snapshot.floor_plan_assets):
            return
        self._snapshot.floor_plan_assets.append(self._asset)
        if self._on_changed:
            self._on_changed()
