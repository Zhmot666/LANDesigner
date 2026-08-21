from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
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

    def boundingRect(self) -> QRectF:  # noqa: N802
        extra = 8.0
        rect = self.rect().adjusted(-extra, -extra, extra, extra)
        return rect.united(self.childrenBoundingRect())

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(self.rect())
        return path

    def itemChange(self, change, value):  # noqa: N802
        return super().itemChange(change, value)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._drag_start = self.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        super().mouseReleaseEvent(event)
        if self._drag_start is not None and self._drag_start != self.pos():
            scene = self.scene()
            if hasattr(scene, "commit_asset_move"):
                scene.commit_asset_move(self, self._drag_start, self.pos())  # type: ignore[attr-defined]
        self._drag_start = None

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
