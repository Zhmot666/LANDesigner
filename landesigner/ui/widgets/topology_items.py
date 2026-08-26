from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPainterPathStroker, QPen
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
SNAP_GRID = 20.0

ROLE_COLORS: dict[DeviceRole, QColor] = {
    DeviceRole.SWITCH: QColor("#2f7c85"),
    DeviceRole.ROUTER: QColor("#3d6b9a"),
    DeviceRole.FIREWALL: QColor("#a04545"),
    DeviceRole.LOAD_BALANCER: QColor("#4578a0"),
    DeviceRole.AP: QColor("#5a8f6a"),
    DeviceRole.CONTROLLER: QColor("#7a5a9a"),
    DeviceRole.SERVER: QColor("#8b6b4a"),
    DeviceRole.STORAGE: QColor("#9a7a4a"),
    DeviceRole.HYPERVISOR: QColor("#6a5a8b"),
    DeviceRole.VIRTUAL_MACHINE: QColor("#5a7a9a"),
    DeviceRole.WORKSTATION: QColor("#6b7c8a"),
    DeviceRole.PATCH_PANEL: QColor("#7a6b8a"),
    DeviceRole.ODF: QColor("#8a6a9a"),
    DeviceRole.PDU: QColor("#8a7a5a"),
    DeviceRole.UPS: QColor("#7a8a4a"),
    DeviceRole.KVM: QColor("#6a6a8a"),
    DeviceRole.NVR: QColor("#5a6a7a"),
    DeviceRole.IP_PHONE: QColor("#4a8a7a"),
    DeviceRole.PRINTER: QColor("#7a7a7a"),
    DeviceRole.MODEM: QColor("#4a6a9a"),
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
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape, True)
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
        self._title.setTextWidth(NODE_W - 22)
        self._title.setPos(14, 10)

        self._subtitle = QGraphicsTextItem(role_label, self)
        self._subtitle.setDefaultTextColor(QColor("#667784"))
        self._subtitle.setFont(QFont("Segoe UI", 8))
        self._subtitle.setTextWidth(NODE_W - 22)
        self._subtitle.setPos(14, 34)

        self._drag_start: QPointF | None = None
        self._group_starts: dict[UUID, QPointF] = {}
        self._in_group_move = False

    def set_labels(self, hostname: str, role_label: str) -> None:
        self.hostname = hostname or "—"
        self._title.setPlainText(self.hostname)
        self._subtitle.setPlainText(role_label)

    def boundingRect(self) -> QRectF:  # noqa: N802
        # Обводка выбора и сглаживание рисуются чуть шире rect().
        return self.rect().adjusted(-8, -8, 8, 8)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(self.rect(), 8, 8)
        return path

    def center_scene_pos(self) -> QPointF:
        return self.mapToScene(self.rect().center())

    def itemChange(self, change, value):  # noqa: N802 — Qt API
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            scene = self.scene()
            primary = getattr(scene, "_group_drag_primary", None) if scene else None
            # Второстепенные узлы группы: отклоняем автосдвиг Qt, двигает primary.
            if (
                primary is not None
                and primary is not self
                and self.node_id in getattr(primary, "_group_starts", {})
            ):
                return self.pos()
            if (
                primary is self
                and self._drag_start is not None
                and len(self._group_starts) > 1
            ):
                pos: QPointF = value
                raw_dx = pos.x() - self._drag_start.x()
                raw_dy = pos.y() - self._drag_start.y()
                snap_dx = round(raw_dx / SNAP_GRID) * SNAP_GRID
                snap_dy = round(raw_dy / SNAP_GRID) * SNAP_GRID
                if scene is not None and not self._in_group_move:
                    self._in_group_move = True
                    try:
                        for graphic in scene.items():
                            if not isinstance(graphic, DeviceNodeItem) or graphic is self:
                                continue
                            start = self._group_starts.get(graphic.node_id)
                            if start is None:
                                continue
                            graphic.setPos(start.x() + snap_dx, start.y() + snap_dy)
                    finally:
                        self._in_group_move = False
                return QPointF(
                    self._drag_start.x() + snap_dx,
                    self._drag_start.y() + snap_dy,
                )
            pos = value
            gx = round(pos.x() / SNAP_GRID) * SNAP_GRID
            gy = round(pos.y() / SNAP_GRID) * SNAP_GRID
            return QPointF(gx, gy)
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
        super().mousePressEvent(event)
        self._drag_start = QPointF(self.pos())
        self._group_starts = {}
        scene = self.scene()
        if scene is not None:
            for graphic in scene.selectedItems():
                if isinstance(graphic, DeviceNodeItem):
                    self._group_starts[graphic.node_id] = QPointF(graphic.pos())
            if self.node_id not in self._group_starts:
                self._group_starts[self.node_id] = QPointF(self.pos())
            if len(self._group_starts) > 1:
                scene._group_drag_primary = self  # type: ignore[attr-defined]
            else:
                scene._group_drag_primary = None  # type: ignore[attr-defined]

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        super().mouseReleaseEvent(event)
        scene = self.scene()
        if scene is not None and getattr(scene, "_group_drag_primary", None) is self:
            scene._group_drag_primary = None  # type: ignore[attr-defined]
        if self._group_starts and scene is not None and hasattr(scene, "commit_nodes_moved"):
            by_id = {
                graphic.node_id: graphic
                for graphic in scene.items()
                if isinstance(graphic, DeviceNodeItem)
            }
            changes: dict[UUID, tuple[float, float, float, float]] = {}
            for node_id, old_pos in self._group_starts.items():
                graphic = by_id.get(node_id)
                if graphic is None:
                    continue
                new_pos = graphic.pos()
                if abs(old_pos.x() - new_pos.x()) > 0.01 or abs(old_pos.y() - new_pos.y()) > 0.01:
                    changes[node_id] = (
                        old_pos.x(),
                        old_pos.y(),
                        new_pos.x(),
                        new_pos.y(),
                    )
            if changes:
                scene.commit_nodes_moved(changes)  # type: ignore[attr-defined]
        self._drag_start = None
        self._group_starts = {}

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
        tooltip: str = "",
        *,
        cable_ids: list[UUID] | None = None,
    ) -> None:
        super().__init__()
        self.link_id = link_id
        self.cable_ids: list[UUID] = list(cable_ids or [])
        if cable_id is not None and cable_id not in self.cable_ids:
            self.cable_ids.insert(0, cable_id)
        self.cable_id = self.cable_ids[0] if self.cable_ids else cable_id
        self.node_a = node_a
        self.node_b = node_b
        self.setZValue(1)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setPen(QPen(QColor("#7a8b96"), 2.0))
        self._label = QGraphicsTextItem(label, self)
        self._label.setDefaultTextColor(QColor("#2f7c85"))
        self._label.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        tip = tooltip.strip()
        if tip:
            self.setToolTip(tip)
            self._label.setToolTip(tip)
        self._dot_a = QGraphicsEllipseItem(-3, -3, 6, 6, self)
        self._dot_b = QGraphicsEllipseItem(-3, -3, 6, 6, self)
        for dot in (self._dot_a, self._dot_b):
            dot.setBrush(QBrush(QColor("#2f7c85")))
            dot.setPen(QPen(Qt.PenStyle.NoPen))
        self.update_geometry()

    @property
    def cable_count(self) -> int:
        return len(self.cable_ids)

    def contains_cable(self, cable_id: UUID | None) -> bool:
        return cable_id is not None and cable_id in self.cable_ids

    def set_label(self, label: str, tooltip: str = "") -> None:
        self._label.setPlainText(label)
        tip = tooltip.strip()
        self.setToolTip(tip)
        self._label.setToolTip(tip)
        self.update_geometry()

    def boundingRect(self) -> QRectF:  # noqa: N802
        extra = 10.0
        rect = super().boundingRect().adjusted(-extra, -extra, extra, extra)
        return rect.united(self.childrenBoundingRect())

    def shape(self) -> QPainterPath:  # noqa: N802
        path = QPainterPath()
        path.moveTo(self.line().p1())
        path.lineTo(self.line().p2())
        stroker = QPainterPathStroker()
        stroker.setWidth(14.0)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        return stroker.createStroke(path)

    def update_geometry(self) -> None:
        self.prepareGeometryChange()
        a = self.node_a.center_scene_pos()
        b = self.node_b.center_scene_pos()
        self.setLine(a.x(), a.y(), b.x(), b.y())
        self._dot_a.setPos(a)
        self._dot_b.setPos(b)
        mid = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
        br = self._label.boundingRect()
        dx = b.x() - a.x()
        dy = b.y() - a.y()
        length = (dx * dx + dy * dy) ** 0.5 or 1.0
        nx, ny = -dy / length, dx / length
        offset = 12.0
        self._label.setPos(
            mid.x() - br.width() / 2 + nx * offset,
            mid.y() - br.height() / 2 + ny * offset,
        )
        selected = self.isSelected()
        count = self.cable_count
        base = 2.0 + min(4.0, max(0, count - 1) * 0.35)
        width = base + (0.8 if selected else 0.0)
        self.setPen(QPen(QColor("#2f7c85" if selected else "#7a8b96"), width))

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        selected = self.isSelected()
        count = self.cable_count
        color = QColor("#2f7c85") if selected else QColor("#7a8b96")
        width = 2.0 + min(4.0, max(0, count - 1) * 0.35) + (0.8 if selected else 0.0)
        painter.setPen(QPen(color, width))
        painter.drawLine(self.line())
