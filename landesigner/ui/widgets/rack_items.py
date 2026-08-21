from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsTextItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from landesigner.domain.enums import DeviceRole
from landesigner.ui.widgets.topology_items import ROLE_COLORS

U_HEIGHT = 22.0
RACK_INNER_WIDTH = 220.0
LABEL_WIDTH = 34.0
FRAME_TOP = 8.0


def unit_top_y(units: int, unit: int) -> float:
    """Y верхней границы юнита (U42 сверху, U1 снизу)."""
    return (units - unit) * U_HEIGHT


def rack_u_from_scene_y(units: int, scene_y: float, height_u: int) -> int:
    local_y = scene_y - FRAME_TOP
    top_u = units - int(round(local_y / U_HEIGHT))
    top_u = max(height_u, min(units, top_u))
    return top_u - height_u + 1


class RackDeviceItem(QGraphicsRectItem):
    def __init__(
        self,
        device_id: UUID,
        hostname: str,
        role: DeviceRole,
        rack_u: int,
        height_u: int,
        units: int,
    ) -> None:
        self.device_id = device_id
        self.hostname = hostname or "—"
        self.rack_u = int(rack_u)
        self.height_u = max(1, int(height_u))
        self.units = units
        super().__init__(0, 0, RACK_INNER_WIDTH, self.height_u * U_HEIGHT)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape, True)
        self.setZValue(2)
        accent = ROLE_COLORS.get(role, ROLE_COLORS[DeviceRole.OTHER])
        self._accent = accent
        self.setBrush(QBrush(accent.lighter(130)))
        self.setPen(QPen(accent.darker(110), 1.5))

        self._label = QGraphicsTextItem(self.hostname, self)
        self._label.setDefaultTextColor(QColor("#23313a"))
        self._label.setFont(QFont("Segoe UI", 8))
        self._label.setTextWidth(RACK_INNER_WIDTH - 12)
        br = self._label.boundingRect()
        self._label.setPos(6, max(2.0, (self.rect().height() - br.height()) / 2))

        self._drag_start_u: int | None = None
        self.sync_to_rack_u()

    def boundingRect(self) -> QRectF:  # noqa: N802
        return self.rect().adjusted(-6, -6, 6, 6)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(self.rect(), 3, 3)
        return path

    def sync_to_rack_u(self) -> None:
        top_u = self.rack_u + self.height_u - 1
        y = unit_top_y(self.units, top_u) + FRAME_TOP
        self.setPos(LABEL_WIDTH, y)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._drag_start_u = self.rack_u
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        super().mouseReleaseEvent(event)
        if self._drag_start_u is not None and self._drag_start_u != self.rack_u:
            scene = self.scene()
            if hasattr(scene, "commit_device_move"):
                scene.commit_device_move(self, self._drag_start_u, self.rack_u)  # type: ignore[attr-defined]
        self._drag_start_u = None

    def itemChange(self, change, value):  # noqa: N802
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            pos: QPointF = value
            new_rack_u = rack_u_from_scene_y(self.units, pos.y(), self.height_u)
            top_u = new_rack_u + self.height_u - 1
            snapped_y = unit_top_y(self.units, top_u) + FRAME_TOP
            self.rack_u = new_rack_u
            return QPointF(LABEL_WIDTH, snapped_y)
        return super().itemChange(change, value)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        selected = self.isSelected()
        painter.setBrush(QBrush(self._accent.lighter(130)))
        painter.setPen(QPen(self._accent.darker(110), 2.5 if selected else 1.5))
        painter.drawRoundedRect(self.rect(), 3, 3)
        if selected:
            painter.setPen(QPen(QColor(47, 124, 133, 120), 5.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(self.rect().adjusted(-2, -2, 2, 2), 4, 4)
