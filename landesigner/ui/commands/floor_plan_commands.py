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


class MoveFloorAssetsCommand(QUndoCommand):
    """Групповое перемещение маркеров: asset_id → (ox, oy, nx, ny)."""

    def __init__(
        self,
        snapshot: ProjectSnapshot,
        changes: dict[UUID, tuple[float, float, float, float]],
        on_changed=None,
    ) -> None:
        super().__init__("Перемещение маркеров")
        self._snapshot = snapshot
        self._changes = dict(changes)
        self._on_changed = on_changed

    def isObsolete(self) -> bool:  # noqa: N802
        return not self._changes

    def redo(self) -> None:
        for asset_id, (_ox, _oy, nx, ny) in self._changes.items():
            fp.move_asset(self._snapshot, asset_id, nx, ny)
        if self._on_changed:
            self._on_changed()

    def undo(self) -> None:
        for asset_id, (ox, oy, _nx, _ny) in self._changes.items():
            fp.move_asset(self._snapshot, asset_id, ox, oy)
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


class AddFloorRouteCommand(QUndoCommand):
    def __init__(
        self,
        snapshot: ProjectSnapshot,
        floor_id: UUID,
        points: list[tuple[float, float]],
        *,
        cable_id: UUID | None = None,
        label: str = "",
        on_changed=None,
    ) -> None:
        super().__init__("Трасса на плане")
        self._snapshot = snapshot
        self._floor_id = floor_id
        self._points = list(points)
        self._cable_id = cable_id
        self._label = label
        self._route = None
        self._on_changed = on_changed

    @property
    def route_id(self) -> UUID | None:
        return None if self._route is None else self._route.id

    def redo(self) -> None:
        if self._route is None:
            self._route = fp.add_route(
                self._snapshot,
                self._floor_id,
                self._points,
                cable_id=self._cable_id,
                label=self._label,
            )
        elif not any(r.id == self._route.id for r in self._snapshot.floor_plan_routes):
            self._snapshot.floor_plan_routes.append(self._route)
        if self._on_changed:
            self._on_changed()

    def undo(self) -> None:
        if self._route is None:
            return
        fp.remove_route(self._snapshot, self._route.id)
        if self._on_changed:
            self._on_changed()


class RemoveFloorRouteCommand(QUndoCommand):
    def __init__(
        self,
        snapshot: ProjectSnapshot,
        route_id: UUID,
        on_changed=None,
    ) -> None:
        super().__init__("Удаление трассы")
        self._snapshot = snapshot
        self._route = next(
            (r for r in snapshot.floor_plan_routes if r.id == route_id), None
        )
        self._on_changed = on_changed
        if self._route is None:
            self.setObsolete(True)

    def redo(self) -> None:
        if self._route is None:
            return
        fp.remove_route(self._snapshot, self._route.id)
        if self._on_changed:
            self._on_changed()

    def undo(self) -> None:
        if self._route is None:
            return
        if any(r.id == self._route.id for r in self._snapshot.floor_plan_routes):
            return
        self._snapshot.floor_plan_routes.append(self._route)
        if self._on_changed:
            self._on_changed()
