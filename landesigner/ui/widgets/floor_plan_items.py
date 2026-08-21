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
