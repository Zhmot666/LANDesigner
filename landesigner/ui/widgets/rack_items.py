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

from landesigner.domain.enums import DeviceRole, PortSide
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


def placement_text(rack_u: int, height_u: int) -> str:
    height = max(1, int(height_u))
    start = int(rack_u)
    end = start + height - 1
    if start == end:
        return f"U{start}"
    return f"U{start}–{end}"


class FreeUnitHighlight(QGraphicsRectItem):
    """Подсветка свободного юнита."""

    def __init__(self, units: int, unit: int) -> None:
        y = unit_top_y(units, unit) + FRAME_TOP
        super().__init__(LABEL_WIDTH, y, RACK_INNER_WIDTH, U_HEIGHT)
        self.setZValue(0.5)
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setBrush(QBrush(QColor(47, 124, 133, 28)))
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)


class RackDeviceItem(QGraphicsRectItem):
    def __init__(
        self,
        device_id: UUID,
        hostname: str,
        role: DeviceRole,
        rack_u: int,
        height_u: int,
        units: int,
        *,
        face: PortSide = PortSide.FRONT,
        side_total: int = 0,
        side_busy: int = 0,
    ) -> None:
        self.device_id = device_id
        self.hostname = hostname or "—"
        self.role = role
        self.rack_u = int(rack_u)
        self.height_u = max(1, int(height_u))
        self.units = units
        self.face = face
        self._side_total = max(0, int(side_total))
        self._side_busy = max(0, int(side_busy))
        self._occupied: set[int] = set()
        self._valid_rack_u = self.rack_u
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
        self.setAcceptHoverEvents(True)
        self.setToolTip(self._build_tooltip())

        self._label = QGraphicsTextItem(self.hostname, self)
        self._label.setDefaultTextColor(QColor("#23313a"))
        self._label.setFont(QFont("Segoe UI", 8))
        self._label.setTextWidth(RACK_INNER_WIDTH - 56)

        self._u_label = QGraphicsTextItem(self)
        self._u_label.setDefaultTextColor(QColor("#2f7c85"))
        self._u_label.setFont(QFont("Segoe UI", 7, QFont.Weight.DemiBold))

        self._meta_label = QGraphicsTextItem(self)
        self._meta_label.setDefaultTextColor(QColor("#667784"))
        self._meta_label.setFont(QFont("Segoe UI", 7))

        self._drag_start_u: int | None = None
        self._update_child_labels()
        self.sync_to_rack_u()

    def set_occupied_units(self, occupied: set[int]) -> None:
        self._occupied = set(occupied)

    def set_face_summary(self, face: PortSide, total: int, busy: int) -> None:
        self.face = face
        self._side_total = max(0, int(total))
        self._side_busy = max(0, int(busy))
        self._update_child_labels()
        self.setToolTip(self._build_tooltip())

    def _build_tooltip(self) -> str:
        parts = [self.hostname, placement_text(self.rack_u, self.height_u)]
        if self.role == DeviceRole.PATCH_PANEL and self._side_total:
            side = "Front" if self.face == PortSide.FRONT else "Rear"
            parts.append(f"{side}: {self._side_busy}/{self._side_total}")
        return " · ".join(parts)

    def _update_child_labels(self) -> None:
        self._u_label.setPlainText(placement_text(self.rack_u, self.height_u))
        meta = ""
        if self.role == DeviceRole.PATCH_PANEL and self._side_total:
            side = "F" if self.face == PortSide.FRONT else "R"
            meta = f"{side} {self._side_busy}/{self._side_total}"
        elif self.height_u > 1:
            meta = f"{self.height_u}U"
        self._meta_label.setPlainText(meta)

        h = self.rect().height()
        self._label.setPos(6, max(1.0, (h - self._label.boundingRect().height()) / 2 - 4))
        u_br = self._u_label.boundingRect()
        self._u_label.setPos(RACK_INNER_WIDTH - u_br.width() - 6, 2)
        if meta:
            m_br = self._meta_label.boundingRect()
            self._meta_label.setPos(6, h - m_br.height() - 1)
            self._meta_label.show()
        else:
            self._meta_label.hide()

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
        self._valid_rack_u = self.rack_u
        self._update_child_labels()

    def _block_units(self, rack_u: int) -> set[int]:
        return set(range(rack_u, rack_u + self.height_u))

    def _fits(self, rack_u: int) -> bool:
        if rack_u < 1 or rack_u + self.height_u - 1 > self.units:
            return False
        return not (self._block_units(rack_u) & self._occupied)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._drag_start_u = self.rack_u
        self._valid_rack_u = self.rack_u
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        super().mouseReleaseEvent(event)
        if self._drag_start_u is not None and self._drag_start_u != self.rack_u:
            scene = self.scene()
            if hasattr(scene, "commit_device_move"):
                scene.commit_device_move(self, self._drag_start_u, self.rack_u)  # type: ignore[attr-defined]
        self._drag_start_u = None
        self.setToolTip(self._build_tooltip())

    def itemChange(self, change, value):  # noqa: N802
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            pos: QPointF = value
            new_rack_u = rack_u_from_scene_y(self.units, pos.y(), self.height_u)
            if not self._fits(new_rack_u):
                new_rack_u = self._valid_rack_u
            else:
                self._valid_rack_u = new_rack_u
            top_u = new_rack_u + self.height_u - 1
            snapped_y = unit_top_y(self.units, top_u) + FRAME_TOP
            self.rack_u = new_rack_u
            self._update_child_labels()
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
        if self.role == DeviceRole.PATCH_PANEL:
            # Маркер стороны (Front слева / Rear справа)
            strip = QRectF(2, 2, 4, self.rect().height() - 4)
            if self.face == PortSide.REAR:
                strip.moveLeft(self.rect().width() - 6)
            painter.fillRect(strip, QColor("#2f7c85"))
