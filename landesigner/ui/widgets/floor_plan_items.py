from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsTextItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from landesigner.domain.enums import DeviceRole
from landesigner.ui.widgets.topology_items import ROLE_COLORS

MARKER_R = 14.0


class FloorDeviceItem(QGraphicsEllipseItem):
    def __init__(
        self,
        asset_id: UUID,
        device_id: UUID,
        hostname: str,
        role: DeviceRole,
        x: float,
        y: float,
    ) -> None:
        super().__init__(-MARKER_R, -MARKER_R, MARKER_R * 2, MARKER_R * 2)
        self.asset_id = asset_id
        self.device_id = device_id
        self.hostname = hostname or "—"
        self.setPos(x, y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(2)
        accent = ROLE_COLORS.get(role, ROLE_COLORS[DeviceRole.OTHER])
        self._accent = accent
        self.setBrush(QBrush(accent))
        self.setPen(QPen(QColor("#ffffff"), 2.0))

        self._label = QGraphicsTextItem(self.hostname, self)
        self._label.setDefaultTextColor(QColor("#23313a"))
        self._label.setFont(QFont("Segoe UI", 8))
        br = self._label.boundingRect()
        self._label.setPos(-br.width() / 2, MARKER_R + 2)

        self._drag_start: QPointF | None = None
        self._group_starts: dict[UUID, QPointF] = {}
        self._in_group_move = False

    def boundingRect(self) -> QRectF:  # noqa: N802
        extra = 8.0
        rect = self.rect().adjusted(-extra, -extra, extra, extra)
        return rect.united(self.childrenBoundingRect())

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(self.rect())
        return path

    def itemChange(self, change, value):  # noqa: N802
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            scene = self.scene()
            primary = getattr(scene, "_group_drag_primary", None) if scene else None
            if (
                primary is not None
                and primary is not self
                and self.asset_id in getattr(primary, "_group_starts", {})
            ):
                return self.pos()
            if (
                primary is self
                and self._drag_start is not None
                and len(self._group_starts) > 1
            ):
                pos: QPointF = value
                dx = pos.x() - self._drag_start.x()
                dy = pos.y() - self._drag_start.y()
                if scene is not None and not self._in_group_move:
                    self._in_group_move = True
                    try:
                        for graphic in scene.items():
                            if not isinstance(graphic, FloorDeviceItem) or graphic is self:
                                continue
                            start = self._group_starts.get(graphic.asset_id)
                            if start is None:
                                continue
                            graphic.setPos(start.x() + dx, start.y() + dy)
                    finally:
                        self._in_group_move = False
                return QPointF(self._drag_start.x() + dx, self._drag_start.y() + dy)
        return super().itemChange(change, value)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        super().mousePressEvent(event)
        self._drag_start = QPointF(self.pos())
        self._group_starts = {}
        scene = self.scene()
        if scene is not None:
            for graphic in scene.selectedItems():
                if isinstance(graphic, FloorDeviceItem):
                    self._group_starts[graphic.asset_id] = QPointF(graphic.pos())
            if self.asset_id not in self._group_starts:
                self._group_starts[self.asset_id] = QPointF(self.pos())
            scene._group_drag_primary = (  # type: ignore[attr-defined]
                self if len(self._group_starts) > 1 else None
            )

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        super().mouseReleaseEvent(event)
        scene = self.scene()
        if scene is not None and getattr(scene, "_group_drag_primary", None) is self:
            scene._group_drag_primary = None  # type: ignore[attr-defined]
        if self._group_starts and scene is not None and hasattr(scene, "commit_assets_moved"):
            by_id = {
                graphic.asset_id: graphic
                for graphic in scene.items()
                if isinstance(graphic, FloorDeviceItem)
            }
            changes: dict[UUID, tuple[float, float, float, float]] = {}
            for asset_id, old_pos in self._group_starts.items():
                graphic = by_id.get(asset_id)
                if graphic is None:
                    continue
                new_pos = graphic.pos()
                if abs(old_pos.x() - new_pos.x()) > 0.01 or abs(old_pos.y() - new_pos.y()) > 0.01:
                    changes[asset_id] = (
                        old_pos.x(),
                        old_pos.y(),
                        new_pos.x(),
                        new_pos.y(),
                    )
            if changes:
                scene.commit_assets_moved(changes)  # type: ignore[attr-defined]
        elif (
            self._drag_start is not None
            and self._drag_start != self.pos()
            and scene is not None
            and hasattr(scene, "commit_asset_move")
        ):
            scene.commit_asset_move(self, self._drag_start, self.pos())  # type: ignore[attr-defined]
        self._drag_start = None
        self._group_starts = {}

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        selected = self.isSelected()
        painter.setBrush(QBrush(self._accent))
        painter.setPen(QPen(QColor("#ffffff"), 3.0 if selected else 2.0))
        painter.drawEllipse(self.rect())
        if selected:
            painter.setPen(QPen(QColor(47, 124, 133, 100), 6.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(self.rect().adjusted(-3, -3, 3, 3))


class FloorRouteItem(QGraphicsPathItem):
    """Сохранённая полилиния трассы на плане."""

    def __init__(
        self,
        route_id: UUID,
        points: list[tuple[float, float]],
        *,
        label: str = "",
        length_m: float | None = None,
        cable_label: str = "",
    ) -> None:
        super().__init__()
        self.route_id = route_id
        path = QPainterPath()
        if points:
            path.moveTo(points[0][0], points[0][1])
            for x, y in points[1:]:
                path.lineTo(x, y)
        self.setPath(path)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setZValue(1)
        self._accent = QColor("#c45c26")
        tip_parts = []
        if label:
            tip_parts.append(label)
        if cable_label:
            tip_parts.append(cable_label)
        if length_m is not None:
            tip_parts.append(f"{length_m:.2f} м")
        self.setToolTip(" · ".join(tip_parts) if tip_parts else "Трасса")
        self.setPen(QPen(self._accent, 2.5, Qt.PenStyle.SolidLine))

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        selected = self.isSelected()
        painter.setPen(
            QPen(self._accent, 4.0 if selected else 2.5, Qt.PenStyle.SolidLine)
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.path())
