from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsTextItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from landesigner.domain.enums import DeviceRole

NODE_W = 150.0
NODE_H = 64.0

ROLE_COLORS: dict[DeviceRole, QColor] = {
    DeviceRole.SWITCH: QColor("#2f7c85"),
    DeviceRole.ROUTER: QColor("#3d6b9a"),
    DeviceRole.AP: QColor("#5a8f6a"),
    DeviceRole.SERVER: QColor("#8b6b4a"),
    DeviceRole.HYPERVISOR: QColor("#6a5a8b"),
    DeviceRole.VIRTUAL_MACHINE: QColor("#5a7a9a"),
    DeviceRole.WORKSTATION: QColor("#6b7c8a"),
    DeviceRole.PATCH_PANEL: QColor("#7a6b8a"),
    DeviceRole.OTHER: QColor("#667784"),
}


class DeviceNodeItem(QGraphicsRectItem):
    def __init__(
        self,
        node_id: UUID,
        device_id: UUID,
        hostname: str,
        role: DeviceRole,
        role_label: str,
        x: float,
        y: float,
    ) -> None:
        super().__init__(0, 0, NODE_W, NODE_H)
        self.node_id = node_id
        self.device_id = device_id
        self.hostname = hostname or "—"
        self.setPos(x, y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(2)

        accent = ROLE_COLORS.get(role, ROLE_COLORS[DeviceRole.OTHER])
        self._accent = accent
        self.setBrush(QBrush(QColor("#ffffff")))
        self.setPen(QPen(accent, 2.0))

        self._title = QGraphicsTextItem(hostname or "—", self)
        self._title.setDefaultTextColor(QColor("#23313a"))
        font = QFont("Segoe UI", 10)
        font.setBold(True)
        self._title.setFont(font)
        self._title.setPos(14, 10)

        self._subtitle = QGraphicsTextItem(role_label, self)
        self._subtitle.setDefaultTextColor(QColor("#667784"))
        self._subtitle.setFont(QFont("Segoe UI", 8))
        self._subtitle.setPos(14, 34)

        self._drag_start: QPointF | None = None

    def set_labels(self, hostname: str, role_label: str) -> None:
        self.hostname = hostname or "—"
        self._title.setPlainText(self.hostname)
        self._subtitle.setPlainText(role_label)

    def center_scene_pos(self) -> QPointF:
        return self.sceneBoundingRect().center()

    def itemChange(self, change, value):  # noqa: N802 — Qt API
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            scene = self.scene()
            if hasattr(scene, "notify_node_moved"):
                scene.notify_node_moved(self)  # type: ignore[attr-defined]
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        scene = self.scene()
        if hasattr(scene, "request_edit_device"):
            scene.request_edit_device(self)  # type: ignore[attr-defined]
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._drag_start = self.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        super().mouseReleaseEvent(event)
        if self._drag_start is not None and self._drag_start != self.pos():
            scene = self.scene()
            if hasattr(scene, "commit_node_move"):
                scene.commit_node_move(self, self._drag_start, self.pos())  # type: ignore[attr-defined]
        self._drag_start = None

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        selected = bool(self.isSelected())
        painter.setPen(QPen(self._accent, 3.0 if selected else 2.0))
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.drawRoundedRect(self.rect(), 8, 8)
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        painter.setBrush(QBrush(self._accent))
        painter.drawRoundedRect(QRectF(0, 0, 6, NODE_H), 8, 8)
        painter.drawRect(QRectF(3, 0, 3, NODE_H))
        if selected:
            painter.setPen(QPen(QColor(47, 124, 133, 80), 6.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(self.rect().adjusted(-2, -2, 2, 2), 10, 10)


class CableLinkItem(QGraphicsLineItem):
    def __init__(
        self,
        link_id: UUID,
        cable_id: UUID | None,
        node_a: DeviceNodeItem,
        node_b: DeviceNodeItem,
        label: str = "",
    ) -> None:
        super().__init__()
        self.link_id = link_id
        self.cable_id = cable_id
        self.node_a = node_a
        self.node_b = node_b
        self.setZValue(1)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setPen(QPen(QColor("#7a8b96"), 2.0))
        self._label = QGraphicsTextItem(label, self)
        self._label.setDefaultTextColor(QColor("#667784"))
        self._label.setFont(QFont("Segoe UI", 8))
        self._dot_a = QGraphicsEllipseItem(-3, -3, 6, 6, self)
        self._dot_b = QGraphicsEllipseItem(-3, -3, 6, 6, self)
        for dot in (self._dot_a, self._dot_b):
            dot.setBrush(QBrush(QColor("#2f7c85")))
            dot.setPen(QPen(Qt.PenStyle.NoPen))
        self.update_geometry()

    def set_label(self, label: str) -> None:
        self._label.setPlainText(label)
        self.update_geometry()

    def update_geometry(self) -> None:
        a = self.node_a.center_scene_pos()
        b = self.node_b.center_scene_pos()
        self.setLine(a.x(), a.y(), b.x(), b.y())
        self._dot_a.setPos(a)
        self._dot_b.setPos(b)
        mid = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
        br = self._label.boundingRect()
        self._label.setPos(mid.x() - br.width() / 2, mid.y() - br.height() - 4)
        # Толще hit-area для удобного выбора тонкой линии.
        self.setPen(QPen(QColor("#7a8b96"), 8.0))

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        color = QColor("#2f7c85") if self.isSelected() else QColor("#7a8b96")
        width = 3.0 if self.isSelected() else 2.0
        painter.setPen(QPen(color, width))
        painter.drawLine(self.line())
