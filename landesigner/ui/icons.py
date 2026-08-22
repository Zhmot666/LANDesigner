from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QPushButton, QSizePolicy, QWidget

_ACCENT = QColor("#2f7c85")
_DANGER = QColor("#b85c5c")
_ICON_PX = 18
_BTN_PX = 28


def _dpr() -> float:
    app = QApplication.instance()
    if app is None:
        return 1.0
    screen = app.primaryScreen()
    return float(screen.devicePixelRatio()) if screen is not None else 1.0


def _pen(color: QColor, width: float = 1.6) -> QPen:
    pen = QPen(color)
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _draw_edit(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c))
    p.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    path.moveTo(4.5, 13.5)
    path.lineTo(4.2, 15.8)
    path.lineTo(6.5, 15.5)
    path.lineTo(14.8, 7.2)
    path.lineTo(12.6, 5.0)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(11.2, 4.4), QPointF(14.0, 7.2))


def _draw_topology(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QPointF(5.5, 6.0), QPointF(12.5, 9.0))
    p.drawLine(QPointF(5.5, 12.0), QPointF(12.5, 9.0))
    p.drawLine(QPointF(5.5, 6.0), QPointF(5.5, 12.0))
    p.setBrush(c)
    p.drawEllipse(QPointF(5.5, 6.0), 2.1, 2.1)
    p.drawEllipse(QPointF(5.5, 12.0), 2.1, 2.1)
    p.drawEllipse(QPointF(12.5, 9.0), 2.1, 2.1)


def _draw_plan(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(3.5, 3.5, 11.0, 11.0), 1.5, 1.5)
    p.drawLine(QPointF(3.5, 9.0), QPointF(14.5, 9.0))
    p.drawLine(QPointF(9.0, 3.5), QPointF(9.0, 14.5))
    p.setBrush(c)
    p.drawEllipse(QPointF(6.2, 6.2), 1.3, 1.3)


def _draw_rack(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(4.0, 3.0, 10.0, 12.0), 1.4, 1.4)
    p.drawRoundedRect(QRectF(5.5, 4.8, 7.0, 2.4), 0.6, 0.6)
    p.drawRoundedRect(QRectF(5.5, 7.8, 7.0, 2.4), 0.6, 0.6)
    p.drawRoundedRect(QRectF(5.5, 10.8, 7.0, 2.4), 0.6, 0.6)


def _draw_add(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 2.0))
    p.drawLine(QPointF(9.0, 4.0), QPointF(9.0, 14.0))
    p.drawLine(QPointF(4.0, 9.0), QPointF(14.0, 9.0))


def _draw_delete(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(5.0, 6.5, 8.0, 9.0), 1.2, 1.2)
    p.drawLine(QPointF(4.0, 6.5), QPointF(14.0, 6.5))
    p.drawLine(QPointF(7.0, 6.5), QPointF(7.0, 5.0))
    p.drawLine(QPointF(11.0, 6.5), QPointF(11.0, 5.0))
    p.drawLine(QPointF(7.5, 5.0), QPointF(10.5, 5.0))
    p.drawLine(QPointF(7.5, 9.0), QPointF(7.5, 13.0))
    p.drawLine(QPointF(10.5, 9.0), QPointF(10.5, 13.0))


def _draw_network(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(9.0, 9.0), 5.5, 5.5)
    p.drawEllipse(QPointF(9.0, 9.0), 2.8, 5.5)
    p.drawLine(QPointF(3.5, 9.0), QPointF(14.5, 9.0))


def _draw_port(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(3.5, 5.5, 11.0, 7.0), 1.5, 1.5)
    p.drawRect(QRectF(5.5, 7.5, 2.0, 3.0))
    p.drawRect(QRectF(8.0, 7.5, 2.0, 3.0))
    p.drawRect(QRectF(10.5, 7.5, 2.0, 3.0))


def _draw_vnic(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(2.5, 6.0, 5.5, 6.0), 1.0, 1.0)
    p.drawRoundedRect(QRectF(10.0, 6.0, 5.5, 6.0), 1.0, 1.0)
    p.drawLine(QPointF(8.0, 9.0), QPointF(10.0, 9.0))
    p.setBrush(c)
    p.drawEllipse(QPointF(8.0, 9.0), 1.2, 1.2)
    p.drawEllipse(QPointF(10.0, 9.0), 1.2, 1.2)


def _draw_catalog(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(4.0, 3.5, 10.0, 11.0), 1.2, 1.2)
    p.drawLine(QPointF(6.5, 6.5), QPointF(11.5, 6.5))
    p.drawLine(QPointF(6.5, 9.0), QPointF(11.5, 9.0))
    p.drawLine(QPointF(6.5, 11.5), QPointF(10.0, 11.5))


def _draw_export(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.7))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QPointF(9.0, 3.5), QPointF(9.0, 11.0))
    p.drawLine(QPointF(6.0, 6.0), QPointF(9.0, 3.5))
    p.drawLine(QPointF(12.0, 6.0), QPointF(9.0, 3.5))
    p.drawLine(QPointF(4.5, 13.5), QPointF(13.5, 13.5))
    p.drawLine(QPointF(4.5, 13.5), QPointF(4.5, 11.5))
    p.drawLine(QPointF(13.5, 13.5), QPointF(13.5, 11.5))


def _draw_import(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.7))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QPointF(9.0, 3.5), QPointF(9.0, 11.0))
    p.drawLine(QPointF(6.0, 8.5), QPointF(9.0, 11.0))
    p.drawLine(QPointF(12.0, 8.5), QPointF(9.0, 11.0))
    p.drawLine(QPointF(4.5, 13.5), QPointF(13.5, 13.5))
    p.drawLine(QPointF(4.5, 13.5), QPointF(4.5, 11.5))
    p.drawLine(QPointF(13.5, 13.5), QPointF(13.5, 11.5))


def _draw_check(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 2.0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    path.moveTo(4.0, 9.5)
    path.lineTo(7.5, 13.0)
    path.lineTo(14.0, 5.0)
    p.drawPath(path)


def _draw_report(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(4.0, 3.0, 10.0, 12.0), 1.2, 1.2)
    p.drawLine(QPointF(6.5, 6.5), QPointF(11.5, 6.5))
    p.drawLine(QPointF(6.5, 9.0), QPointF(11.5, 9.0))
    p.drawLine(QPointF(6.5, 11.5), QPointF(10.5, 11.5))


def _draw_csv(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(3.5, 3.5, 11.0, 11.0), 1.2, 1.2)
    p.drawLine(QPointF(3.5, 7.0), QPointF(14.5, 7.0))
    p.drawLine(QPointF(3.5, 10.5), QPointF(14.5, 10.5))
    p.drawLine(QPointF(7.5, 3.5), QPointF(7.5, 14.5))
    p.drawLine(QPointF(11.0, 3.5), QPointF(11.0, 14.5))


def _draw_print(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(5.5, 2.5, 7.0, 3.5))
    p.drawRoundedRect(QRectF(3.5, 6.0, 11.0, 7.0), 1.2, 1.2)
    p.drawRect(QRectF(5.5, 10.5, 7.0, 4.0))
    p.setBrush(c)
    p.drawEllipse(QPointF(12.5, 8.0), 0.9, 0.9)


def _draw_pdf(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(4.0, 2.5, 10.0, 13.0), 1.2, 1.2)
    p.drawLine(QPointF(11.0, 2.5), QPointF(14.0, 5.5))
    p.drawLine(QPointF(11.0, 2.5), QPointF(11.0, 5.5))
    p.drawLine(QPointF(11.0, 5.5), QPointF(14.0, 5.5))
    p.drawLine(QPointF(6.0, 8.5), QPointF(12.0, 8.5))
    p.drawLine(QPointF(6.0, 11.0), QPointF(12.0, 11.0))
    p.drawLine(QPointF(6.0, 13.5), QPointF(10.0, 13.5))


def _draw_clear(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.8))
    p.drawLine(QPointF(5.0, 5.0), QPointF(13.0, 13.0))
    p.drawLine(QPointF(13.0, 5.0), QPointF(5.0, 13.0))


def _draw_cable(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(2.5, 7.0, 4.0, 4.0), 0.8, 0.8)
    p.drawRoundedRect(QRectF(11.5, 7.0, 4.0, 4.0), 0.8, 0.8)
    path = QPainterPath()
    path.moveTo(6.5, 9.0)
    path.cubicTo(8.0, 5.5, 10.0, 12.5, 11.5, 9.0)
    p.drawPath(path)


def _draw_building(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(4.0, 4.0, 10.0, 11.0))
    p.drawLine(QPointF(4.0, 7.5), QPointF(14.0, 7.5))
    p.drawLine(QPointF(4.0, 11.0), QPointF(14.0, 11.0))
    p.drawLine(QPointF(7.5, 4.0), QPointF(7.5, 15.0))
    p.drawLine(QPointF(11.0, 4.0), QPointF(11.0, 15.0))


def _draw_floor(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(3.5, 5.0, 11.0, 8.0), 1.2, 1.2)
    p.drawLine(QPointF(3.5, 9.0), QPointF(14.5, 9.0))


def _draw_room(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(3.5, 3.5, 11.0, 11.0), 1.5, 1.5)
    p.drawRect(QRectF(7.5, 9.5, 3.0, 5.0))


_DRAWERS = {
    "edit": _draw_edit,
    "topology": _draw_topology,
    "plan": _draw_plan,
    "rack": _draw_rack,
    "add": _draw_add,
    "delete": _draw_delete,
    "network": _draw_network,
    "port": _draw_port,
    "vnic": _draw_vnic,
    "catalog": _draw_catalog,
    "export": _draw_export,
    "import": _draw_import,
    "check": _draw_check,
    "report": _draw_report,
    "csv": _draw_csv,
    "pdf": _draw_pdf,
    "print": _draw_print,
    "clear": _draw_clear,
    "cable": _draw_cable,
    "building": _draw_building,
    "floor": _draw_floor,
    "room": _draw_room,
}


def action_icon(kind: str, color: QColor | None = None) -> QIcon:
    drawer = _DRAWERS[kind]

    def _pm(col: QColor) -> QPixmap:
        dpr = _dpr()
        px = max(1, int(_ICON_PX * dpr))
        pm = QPixmap(px, px)
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.scale(px / 18.0, px / 18.0)
        drawer(painter, col)
        painter.end()
        return pm

    normal = color or _ACCENT
    icon = QIcon()
    icon.addPixmap(_pm(normal), QIcon.Mode.Normal)
    icon.addPixmap(_pm(QColor("#94a2ad")), QIcon.Mode.Disabled)
    return icon


def icon_action_button(
    kind: str,
    tooltip: str,
    parent: QWidget | None = None,
    *,
    role: str | None = None,
) -> QPushButton:
    """Компактная кнопка-иконка для шапок PanelCard и тулбаров вкладок."""
    btn = QPushButton(parent)
    if role == "primary":
        btn.setObjectName("IconPrimaryButton")
        color = _ACCENT
    elif role == "danger":
        btn.setObjectName("IconDangerButton")
        color = _DANGER
    else:
        btn.setObjectName("IconActionButton")
        color = _ACCENT
    btn.setIcon(action_icon(kind, color))
    btn.setIconSize(QSize(_ICON_PX, _ICON_PX))
    btn.setToolTip(tooltip)
    btn.setAccessibleName(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFixedSize(_BTN_PX, _BTN_PX)
    btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    return btn
