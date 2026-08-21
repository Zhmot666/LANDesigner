from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QKeySequence,
    QPainter,
    QPen,
    QShortcut,
    QUndoStack,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from landesigner.domain.entities import ProjectSnapshot
from landesigner.domain.enums import CableCategory, CableKind, DeviceRole
from landesigner.services import topology as topo_service
from landesigner.ui.commands.topology_commands import (
    AddCableCommand,
    DeleteCableCommand,
    LayoutTopologyCommand,
    MoveNodeCommand,
    MoveNodesCommand,
)
from landesigner.ui.icons import icon_action_button
from landesigner.ui.labels import role_label
from landesigner.ui.widgets.topology_items import (
    ROLE_COLORS,
    CableLinkItem,
    DeviceNodeItem,
)

GRID = 20.0


class TopologyScene(QGraphicsScene):
    node_move_committed = Signal(object, float, float, float, float)  # id, ox, oy, nx, ny
    nodes_moved = Signal(object)  # dict[UUID, (ox, oy, nx, ny)]
    edit_device_requested = Signal(object)  # device_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSceneRect(-2000, -2000, 6000, 6000)
        self.setBackgroundBrush(QBrush(QColor("#f4f7f8")))
        self._group_drag_primary: DeviceNodeItem | None = None

    def request_edit_device(self, item: DeviceNodeItem) -> None:
        self.edit_device_requested.emit(item.device_id)

    def notify_node_moved(self, item: DeviceNodeItem) -> None:
        for graphic in self.items():
            if isinstance(graphic, CableLinkItem) and (
                graphic.node_a is item or graphic.node_b is item
            ):
                graphic.update_geometry()

    def commit_node_move(
        self,
        item: DeviceNodeItem,
        old_pos: QPointF,
        new_pos: QPointF,
    ) -> None:
        self.node_move_committed.emit(
            item.node_id,
            old_pos.x(),
            old_pos.y(),
            new_pos.x(),
            new_pos.y(),
        )

    def commit_nodes_moved(
        self,
        changes: dict[UUID, tuple[float, float, float, float]],
    ) -> None:
        if not changes:
            return
        if len(changes) == 1:
            node_id, (ox, oy, nx, ny) = next(iter(changes.items()))
            self.node_move_committed.emit(node_id, ox, oy, nx, ny)
            return
        self.nodes_moved.emit(changes)

    def drawBackground(self, painter: QPainter, rect) -> None:  # noqa: N802
        super().drawBackground(painter, rect)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        left = int(rect.left()) - (int(rect.left()) % int(GRID))
        top = int(rect.top()) - (int(rect.top()) % int(GRID))
        painter.setPen(QPen(QColor("#e1e8ec"), 1.0))
        x = left
        while x < rect.right():
            painter.drawLine(int(x), int(rect.top()), int(x), int(rect.bottom()))
            x += GRID
        y = top
        while y < rect.bottom():
            painter.drawLine(int(rect.left()), int(y), int(rect.right()), int(y))
            y += GRID


class TopologyView(QWidget):
    """Редактор топологии: узлы = устройства, линки = кабели."""

    device_selected = Signal(object)  # UUID | None
    cable_selected = Signal(object)  # UUID | None
    topology_changed = Signal()
    connect_devices_requested = Signal(object, object)  # device_a, device_b
    edit_device_requested = Signal(object)  # UUID

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._snapshot: ProjectSnapshot | None = None
        self._nodes: dict[UUID, DeviceNodeItem] = {}
        self._links: dict[UUID, CableLinkItem] = {}
        self._undo = QUndoStack(self)
        self._panning = False
        self._pan_start = QPoint()
        self._suppress_selection = False
        self._rebuild_guard = False
        self._connect_mode = False
        self._connect_from: UUID | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self._hint = QLabel(
            "Колёсико — зум · Shift+ЛКМ — пан · рамка — группа · узлы к сетке · Delete — связь",
            self,
        )
        self._hint.setObjectName("PanelSubtitle")
        self._hint.setProperty("muted", True)
        self._btn_connect = QPushButton("Соединить", self)
        self._btn_connect.setCheckable(True)
        self._btn_connect.setObjectName("PrimaryButton")
        self._btn_connect.setProperty("role", "primary")
        self._btn_delete = QPushButton("Удалить связь", self)
        self._btn_delete.setEnabled(False)
        self._btn_layout = icon_action_button("topology", "Автораскладка узлов", self)
        self._btn_fit = icon_action_button("plan", "Вписать схему", self)
        self._btn_undo = QPushButton("Отменить", self)
        self._btn_redo = QPushButton("Повторить", self)
        self._btn_connect.toggled.connect(self._on_connect_toggled)
        self._btn_delete.clicked.connect(self._delete_selected_link)
        self._btn_layout.clicked.connect(self._auto_layout)
        self._btn_fit.clicked.connect(self.fit_content)
        self._btn_undo.clicked.connect(self._undo.undo)
        self._btn_redo.clicked.connect(self._undo.redo)
        self._undo.canUndoChanged.connect(self._btn_undo.setEnabled)
        self._undo.canRedoChanged.connect(self._btn_redo.setEnabled)
        self._btn_undo.setEnabled(False)
        self._btn_redo.setEnabled(False)
        toolbar.addWidget(self._hint, stretch=1)
        toolbar.addWidget(self._btn_connect)
        toolbar.addWidget(self._btn_delete)
        toolbar.addWidget(self._btn_layout)
        toolbar.addWidget(self._btn_undo)
        toolbar.addWidget(self._btn_redo)
        toolbar.addWidget(self._btn_fit)
        layout.addLayout(toolbar)

        self._scene = TopologyScene(self)
        self._view = QGraphicsView(self._scene, self)
        self._view.setObjectName("TopologyCanvas")
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self._view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._view.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate
        )
        self._view.setFrameShape(QFrame.Shape.StyledPanel)
        self._view.viewport().installEventFilter(self)
        layout.addWidget(self._view, stretch=1)

        legend = QHBoxLayout()
        legend.setSpacing(12)
        legend_title = QLabel("Роли:", self)
        legend_title.setProperty("muted", True)
        legend.addWidget(legend_title)
        for role in DeviceRole:
            chip = QLabel(f"● {role_label(role)}", self)
            color = ROLE_COLORS.get(role, ROLE_COLORS[DeviceRole.OTHER])
            chip.setStyleSheet(f"color: {color.name()}; font-size: 11px;")
            legend.addWidget(chip)
        legend.addStretch(1)
        layout.addLayout(legend)

        self._scene.node_move_committed.connect(self._on_node_move_committed)
        self._scene.nodes_moved.connect(self._on_nodes_moved)
        self._scene.selectionChanged.connect(self._on_selection_changed)
        self._scene.edit_device_requested.connect(self.edit_device_requested.emit)

        QShortcut(QKeySequence.StandardKey.Undo, self, activated=self._undo.undo)
        QShortcut(QKeySequence.StandardKey.Redo, self, activated=self._undo.redo)
        QShortcut(QKeySequence("Ctrl+0"), self, activated=self.fit_content)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self, activated=self._delete_selected_link)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self._cancel_connect_mode)

    def set_snapshot(self, snapshot: ProjectSnapshot | None) -> None:
        self._snapshot = snapshot
        self._undo.clear()
        self._cancel_connect_mode()
        self._rebuild()

    def select_device(self, device_id: UUID | None) -> None:
        self._suppress_selection = True
        try:
            self._scene.clearSelection()
            if device_id is None:
                return
            item = next((n for n in self._nodes.values() if n.device_id == device_id), None)
            if item is not None:
                item.setSelected(True)
                self._view.centerOn(item)
        finally:
            self._suppress_selection = False

    def undo(self) -> None:
        self._undo.undo()

    def redo(self) -> None:
        self._undo.redo()

    def can_undo(self) -> bool:
        return self._undo.canUndo()

    def can_redo(self) -> bool:
        return self._undo.canRedo()

    def apply_add_cable(
        self,
        end_a_port_id: UUID,
        end_b_port_id: UUID,
        *,
        label: str = "",
        kind: CableKind = CableKind.COPPER,
        category: CableCategory = CableCategory.OTHER,
        length_m: float | None = None,
        color: str = "",
        purpose: str = "",
    ) -> None:
        if self._snapshot is None:
            return
        cmd = AddCableCommand(
            self._snapshot,
            end_a_port_id,
            end_b_port_id,
            label=label,
            kind=kind,
            category=category,
            length_m=length_m,
            color=color,
            purpose=purpose,
            on_changed=self._on_cable_command_changed,
        )
        self._undo.push(cmd)
        self.topology_changed.emit()

    def fit_content(self) -> None:
        if not self._nodes:
            self._view.resetTransform()
            return
        rect = self._scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        self._view.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self._view.viewport():
            et = event.type()
            if et == QEvent.Type.Wheel:
                self._zoom(event)
                return True
            if et == QEvent.Type.MouseButtonPress:
                if self._connect_mode and event.button() == Qt.MouseButton.LeftButton:
                    self._handle_connect_click(event.position().toPoint())
                    return True
                if event.button() == Qt.MouseButton.MiddleButton or (
                    event.button() == Qt.MouseButton.LeftButton
                    and bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                ):
                    self._panning = True
                    self._pan_start = event.position().toPoint()
                    self._view.setCursor(Qt.CursorShape.ClosedHandCursor)
                    return True
            if et == QEvent.Type.MouseMove and self._panning:
                delta = event.position().toPoint() - self._pan_start
                self._pan_start = event.position().toPoint()
                self._view.horizontalScrollBar().setValue(
                    self._view.horizontalScrollBar().value() - delta.x()
                )
                self._view.verticalScrollBar().setValue(
                    self._view.verticalScrollBar().value() - delta.y()
                )
                return True
            if et == QEvent.Type.MouseButtonRelease and self._panning:
                self._panning = False
                self._view.unsetCursor()
                return True
        return super().eventFilter(obj, event)

    def _zoom(self, event: QWheelEvent) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        current = self._view.transform().m11()
        if factor > 1 and current > 4:
            return
        if factor < 1 and current < 0.2:
            return
        self._view.scale(factor, factor)

    def _on_connect_toggled(self, checked: bool) -> None:
        self._connect_mode = checked
        self._connect_from = None
        self._set_nodes_movable(not checked)
        if checked:
            self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self._hint.setText("Режим соединения: кликните первое устройство, затем второе (Esc — отмена)")
            self._view.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self._view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self._hint.setText(
                "Колёсико — зум · Shift+ЛКМ — пан · рамка — группа · узлы к сетке · Delete — связь"
            )
            self._view.unsetCursor()
            self._clear_connect_highlight()

    def _cancel_connect_mode(self) -> None:
        if self._btn_connect.isChecked():
            self._btn_connect.setChecked(False)
        else:
            self._on_connect_toggled(False)

    def _set_nodes_movable(self, movable: bool) -> None:
        for item in self._nodes.values():
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, movable)

    def _clear_connect_highlight(self) -> None:
        for item in self._nodes.values():
            item.setOpacity(1.0)

    def _handle_connect_click(self, view_pos: QPoint) -> None:
        item = self._view.itemAt(view_pos)
        node: DeviceNodeItem | None = None
        while item is not None:
            if isinstance(item, DeviceNodeItem):
                node = item
                break
            item = item.parentItem()
        if node is None:
            return

        if self._connect_from is None:
            self._connect_from = node.device_id
            self._clear_connect_highlight()
            for other in self._nodes.values():
                other.setOpacity(1.0 if other.device_id == node.device_id else 0.45)
            self._hint.setText(
                f"Выбрано: {node.hostname} — кликните второе устройство (Esc — отмена)"
            )
            return

        if node.device_id == self._connect_from:
            return

        device_a = self._connect_from
        device_b = node.device_id
        self._cancel_connect_mode()
        self.connect_devices_requested.emit(device_a, device_b)

    def _delete_selected_link(self) -> None:
        if self._snapshot is None:
            return
        cable_id = None
        for item in self._scene.selectedItems():
            if isinstance(item, CableLinkItem) and item.cable_id is not None:
                cable_id = item.cable_id
                break
        if cable_id is None:
            return
        answer = QMessageBox.question(
            self,
            "Удалить связь",
            "Удалить кабель и освободить порты?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        cmd = DeleteCableCommand(
            self._snapshot,
            cable_id,
            on_changed=self._on_cable_command_changed,
        )
        if cmd.isObsolete():
            return
        self._undo.push(cmd)
        self.topology_changed.emit()

    def _on_cable_command_changed(self) -> None:
        self._rebuild()

    def _auto_layout(self) -> None:
        if self._snapshot is None:
            return
        before = {n.id: (n.x, n.y) for n in self._snapshot.topology_nodes}
        changes_new = topo_service.auto_layout(self._snapshot)
        if not changes_new:
            return
        changes = {
            nid: (before[nid][0], before[nid][1], nx, ny)
            for nid, (_ox, _oy, nx, ny) in changes_new.items()
            if nid in before
        }
        # Откат к before — redo команды применит new
        topo_service.apply_layout_positions(self._snapshot, before)
        cmd = LayoutTopologyCommand(
            self._snapshot,
            changes,
            on_changed=self._apply_positions_from_snapshot,
        )
        if cmd.isObsolete():
            return
        self._undo.push(cmd)
        self.fit_content()
        self.topology_changed.emit()

    def _rebuild(self) -> None:
        if self._rebuild_guard:
            return
        self._rebuild_guard = True
        try:
            selected_device = None
            selected_cable = None
            for item in self._scene.selectedItems():
                if isinstance(item, DeviceNodeItem):
                    selected_device = item.device_id
                    break
                if isinstance(item, CableLinkItem) and item.cable_id is not None:
                    selected_cable = item.cable_id

            self._scene.clear()
            self._nodes.clear()
            self._links.clear()

            snapshot = self._snapshot
            if snapshot is None:
                return

            if topo_service.ensure_topology(snapshot):
                self.topology_changed.emit()

            devices = {d.id: d for d in snapshot.devices}
            for node in snapshot.topology_nodes:
                device = devices.get(node.device_id)
                if device is None:
                    continue
                item = DeviceNodeItem(
                    node_id=node.id,
                    device_id=device.id,
                    hostname=device.hostname,
                    role=device.role,
                    role_label=role_label(device.role),
                    x=node.x,
                    y=node.y,
                )
                self._scene.addItem(item)
                self._nodes[node.id] = item

            for link in snapshot.topology_links:
                a = self._nodes.get(link.topology_node_a_id)
                b = self._nodes.get(link.topology_node_b_id)
                if a is None or b is None:
                    continue
                label = ""
                if link.cable_id is not None:
                    label = topo_service.link_caption(snapshot, link.cable_id)
                item = CableLinkItem(link.id, link.cable_id, a, b, label=label)
                self._scene.addItem(item)
                self._links[link.id] = item

            self._set_nodes_movable(not self._connect_mode)

            if selected_device is not None:
                self.select_device(selected_device)
            elif selected_cable is not None:
                self._suppress_selection = True
                try:
                    for link_item in self._links.values():
                        if link_item.cable_id == selected_cable:
                            link_item.setSelected(True)
                            break
                finally:
                    self._suppress_selection = False
        finally:
            self._rebuild_guard = False

    def _on_node_move_committed(
        self,
        node_id: UUID,
        old_x: float,
        old_y: float,
        new_x: float,
        new_y: float,
    ) -> None:
        if self._snapshot is None or self._connect_mode:
            return
        cmd = MoveNodeCommand(
            self._snapshot,
            node_id,
            old_x,
            old_y,
            new_x,
            new_y,
            on_changed=self._apply_positions_from_snapshot,
        )
        self._undo.push(cmd)
        self.topology_changed.emit()

    def _on_nodes_moved(
        self,
        changes: dict[UUID, tuple[float, float, float, float]],
    ) -> None:
        if self._snapshot is None or self._connect_mode or not changes:
            return
        cmd = MoveNodesCommand(
            self._snapshot,
            changes,
            on_changed=self._apply_positions_from_snapshot,
        )
        self._undo.push(cmd)
        self.topology_changed.emit()

    def _apply_positions_from_snapshot(self) -> None:
        if self._snapshot is None:
            return
        by_id = {n.id: n for n in self._snapshot.topology_nodes}
        for node_id, item in self._nodes.items():
            node = by_id.get(node_id)
            if node is None:
                continue
            if abs(item.pos().x() - node.x) > 0.01 or abs(item.pos().y() - node.y) > 0.01:
                item.setPos(node.x, node.y)
        for link in self._links.values():
            link.update_geometry()

    def _on_selection_changed(self) -> None:
        if self._suppress_selection or self._rebuild_guard:
            return
        device_id = None
        cable_id = None
        for item in self._scene.selectedItems():
            if isinstance(item, DeviceNodeItem):
                device_id = item.device_id
                break
            if isinstance(item, CableLinkItem) and item.cable_id is not None:
                cable_id = item.cable_id
        self._btn_delete.setEnabled(cable_id is not None)
        self.device_selected.emit(device_id)
        self.cable_selected.emit(cable_id)
