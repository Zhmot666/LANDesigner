from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import QEvent, QPoint, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QUndoStack, QWheelEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from landesigner.domain.entities import ProjectSnapshot, Rack
from landesigner.domain.enums import DeviceRole, PortSide, RackMountFace
from landesigner.services import inventory as inv
from landesigner.ui.commands.rack_commands import (
    MountRackDeviceCommand,
    MoveRackDeviceCommand,
    ResizeRackDeviceCommand,
    UnmountRackDeviceCommand,
)
from landesigner.ui.icons import icon_action_button
from landesigner.ui.widgets.rack_items import (
    FRAME_TOP,
    LABEL_WIDTH,
    RACK_INNER_WIDTH,
    U_HEIGHT,
    FreeUnitHighlight,
    RackDeviceItem,
    unit_top_y,
)


class RackScene(QGraphicsScene):
    device_move_committed = Signal(object, int, int)  # device_id, old_u, new_u

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setBackgroundBrush(QBrush(QColor("#eef3f5")))

    def commit_device_move(
        self,
        item: RackDeviceItem,
        old_rack_u: int,
        new_rack_u: int,
    ) -> None:
        if old_rack_u != new_rack_u:
            self.device_move_committed.emit(item.device_id, old_rack_u, new_rack_u)


class RackView(QWidget):
    """Чертёж стойки: юниты U, Front/Rear, drag-and-drop устройств."""

    rack_changed = Signal()
    device_selected = Signal(object)  # UUID | None

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._snapshot: ProjectSnapshot | None = None
        self._rack_id: UUID | None = None
        self._face = RackMountFace.FRONT
        self._items: dict[UUID, RackDeviceItem] = {}
        self._free_highlights: list[FreeUnitHighlight] = []
        self._grid_lines: list[QGraphicsLineItem] = []
        self._unit_labels: list[QGraphicsTextItem] = []
        self._undo = QUndoStack(self)
        self._panning = False
        self._pan_start = QPoint()
        self._rebuild_guard = False
        self._suppress_selection = False

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.addWidget(QLabel("Шкаф:", self))
        self._rack_combo = QComboBox(self)
        self._rack_combo.currentIndexChanged.connect(self._on_rack_combo)
        toolbar.addWidget(self._rack_combo, stretch=1)

        self._add_combo = QComboBox(self)
        self._add_combo.setMinimumWidth(180)
        toolbar.addWidget(self._add_combo, stretch=1)
        self._btn_add = icon_action_button("add", "Монтировать в стойку", self, role="primary")
        self._btn_add.clicked.connect(self._mount_selected_device)
        toolbar.addWidget(self._btn_add)

        face_box = QHBoxLayout()
        face_box.setSpacing(4)
        self._face_group = QButtonGroup(self)
        self._radio_front = QRadioButton("Front", self)
        self._radio_rear = QRadioButton("Rear", self)
        self._radio_front.setChecked(True)
        self._face_group.addButton(self._radio_front, 0)
        self._face_group.addButton(self._radio_rear, 1)
        self._face_group.idToggled.connect(self._on_face_toggled)
        face_box.addWidget(self._radio_front)
        face_box.addWidget(self._radio_rear)
        toolbar.addLayout(face_box)

        self._btn_fit = icon_action_button("rack", "Вписать стойку", self)
        self._btn_undo = QPushButton("Отменить", self)
        self._btn_redo = QPushButton("Повторить", self)
        self._btn_fit.clicked.connect(self.fit_content)
        self._btn_undo.clicked.connect(self._undo.undo)
        self._btn_redo.clicked.connect(self._undo.redo)
        self._undo.canUndoChanged.connect(self._btn_undo.setEnabled)
        self._undo.canRedoChanged.connect(self._btn_redo.setEnabled)
        self._btn_undo.setEnabled(False)
        self._btn_redo.setEnabled(False)
        for btn in (self._btn_fit, self._btn_undo, self._btn_redo):
            toolbar.addWidget(btn)
        root.addLayout(toolbar)

        body = QHBoxLayout()
        body.setSpacing(8)
        self._scene = RackScene(self)
        self._scene.device_move_committed.connect(self._on_device_move_committed)
        self._scene.selectionChanged.connect(self._on_scene_selection)
        self._view = QGraphicsView(self._scene, self)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._view.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate
        )
        self._view.setFrameShape(QFrame.Shape.NoFrame)
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._view.customContextMenuRequested.connect(self._on_context_menu)
        self._view.viewport().installEventFilter(self)
        body.addWidget(self._view, stretch=1)
        root.addLayout(body, stretch=1)

        self._status = QLabel(self)
        self._status.setObjectName("HintLabel")
        self._status.setWordWrap(True)
        root.addWidget(self._status)
        self._update_status_hint()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._view.viewport():
            et = event.type()
            if et == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.MiddleButton:
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
            if et == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.MiddleButton:
                self._panning = False
                self._view.setCursor(Qt.CursorShape.ArrowCursor)
                return True
            if et == QEvent.Type.Wheel and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._zoom_wheel(event)
                return True
        return super().eventFilter(obj, event)

    def _zoom_wheel(self, event: QWheelEvent) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._view.scale(factor, factor)

    def undo(self) -> None:
        self._undo.undo()

    def redo(self) -> None:
        self._undo.redo()

    def can_undo(self) -> bool:
        return self._undo.canUndo()

    def can_redo(self) -> bool:
        return self._undo.canRedo()

    def set_snapshot(self, snapshot: ProjectSnapshot | None) -> None:
        prev = self._rack_id
        self._snapshot = snapshot
        self._undo.clear()
        self._reload_racks(prefer=prev)
        self._rebuild()

    def select_rack(self, rack_id: UUID | None) -> None:
        if rack_id is None:
            return
        idx = self._rack_combo.findData(str(rack_id))
        if idx >= 0:
            self._rack_combo.setCurrentIndex(idx)

    def select_device(self, device_id: UUID | None) -> None:
        self._suppress_selection = True
        try:
            self._scene.clearSelection()
            if device_id is None:
                return
            item = self._items.get(device_id)
            if item is not None:
                item.setSelected(True)
                self._view.centerOn(item)
        finally:
            self._suppress_selection = False

    def fit_content(self) -> None:
        rect = self._scene.sceneRect()
        if rect.isNull():
            return
        self._view.fitInView(rect.adjusted(-20, -20, 20, 20), Qt.AspectRatioMode.KeepAspectRatio)

    def _current_rack(self) -> Rack | None:
        if self._snapshot is None or self._rack_id is None:
            return None
        return next((r for r in self._snapshot.racks if r.id == self._rack_id), None)

    def _on_face_toggled(self, button_id: int, checked: bool) -> None:
        if not checked:
            return
        self._face = RackMountFace.FRONT if button_id == 0 else RackMountFace.REAR
        self._rebuild()

    def _update_status_hint(self) -> None:
        rack = self._current_rack()
        snap = self._snapshot
        face = inv.rack_mount_face_label(self._face)
        if rack is None or snap is None:
            self._status.setText(
                f"Монтаж: {face}. Выберите шкаф. ПКМ по устройству — снять / высота U."
            )
            return
        free = inv.rack_free_units(snap, rack.id, face=self._face)
        used_on_face = max(0, int(rack.units) - len(free))
        self._status.setText(
            f"Монтаж: {face} · {rack.units}U · занято {used_on_face}, свободно {len(free)}. "
            "Перетащите блок по вертикали; ПКМ — снять со стойки / высота U. "
            "U1 — снизу."
        )

    def _reload_racks(self, *, prefer: UUID | None = None) -> None:
        self._rack_combo.blockSignals(True)
        self._rack_combo.clear()
        racks: list[Rack] = []
        if self._snapshot is not None:
            racks = sorted(self._snapshot.racks, key=lambda r: r.name.casefold())
            for rack in racks:
                room = next(
                    (rm for rm in self._snapshot.rooms if rm.id == rack.room_id),
                    None,
                )
                suffix = f" ({room.name})" if room is not None else ""
                self._rack_combo.addItem(f"{rack.name}{suffix}", str(rack.id))
        self._rack_combo.blockSignals(False)

        if not racks:
            self._rack_id = None
            return
        prefer_idx = -1
        if prefer is not None:
            prefer_idx = self._rack_combo.findData(str(prefer))
        self._rack_combo.setCurrentIndex(prefer_idx if prefer_idx >= 0 else 0)
        raw = self._rack_combo.currentData()
        self._rack_id = UUID(str(raw)) if raw else None

    def _reload_add_combo(self) -> None:
        self._add_combo.blockSignals(True)
        self._add_combo.clear()
        rack = self._current_rack()
        snap = self._snapshot
        if rack is not None and snap is not None:
            room_devices = inv.devices_for_location(snap, "room", rack.room_id)
            for device in room_devices:
                if device.role == DeviceRole.VIRTUAL_MACHINE:
                    continue
                if device.rack_id == rack.id:
                    continue
                dtype = next((t for t in snap.device_types if t.id == device.device_type_id), None)
                type_txt = f"{dtype.vendor} {dtype.model}".strip() if dtype else ""
                label = device.hostname
                if type_txt:
                    label = f"{label} · {type_txt}"
                self._add_combo.addItem(label, str(device.id))
        self._add_combo.blockSignals(False)
        self._btn_add.setEnabled(self._add_combo.count() > 0)

    def _on_rack_combo(self) -> None:
        raw = self._rack_combo.currentData()
        self._rack_id = UUID(str(raw)) if raw else None
        self._rebuild()

    def _rebuild(self) -> None:
        if self._rebuild_guard:
            return
        self._rebuild_guard = True
        try:
            self._scene.clear()
            self._items.clear()
            self._free_highlights.clear()
            self._grid_lines.clear()
            self._unit_labels.clear()
            self._reload_add_combo()

            rack = self._current_rack()
            snap = self._snapshot
            if rack is None or snap is None:
                self._scene.setSceneRect(0, 0, 400, 300)
                self._update_status_hint()
                return

            units = max(1, int(rack.units))
            total_h = units * U_HEIGHT + 24
            total_w = LABEL_WIDTH + RACK_INNER_WIDTH + 24
            self._scene.setSceneRect(0, 0, total_w, total_h)

            frame = self._scene.addRect(
                LABEL_WIDTH,
                FRAME_TOP,
                RACK_INNER_WIDTH,
                units * U_HEIGHT,
                QPen(QColor("#94a2ad"), 1.5),
                QBrush(QColor("#ffffff")),
            )
            frame.setZValue(0)

            free = set(inv.rack_free_units(snap, rack.id))
            for u in free:
                hl = FreeUnitHighlight(units, u)
                self._scene.addItem(hl)
                self._free_highlights.append(hl)

            label_font = QFont("Segoe UI", 7)
            for u in range(1, units + 1):
                y = unit_top_y(units, u) + FRAME_TOP
                line = self._scene.addLine(
                    LABEL_WIDTH,
                    y,
                    LABEL_WIDTH + RACK_INNER_WIDTH,
                    y,
                    QPen(QColor("#d8e2e8"), 1.0),
                )
                line.setZValue(1)
                self._grid_lines.append(line)
                if u % 2 == 1 or u == units:
                    text = self._scene.addText(f"U{u}", label_font)
                    text.setDefaultTextColor(QColor("#667784"))
                    text.setPos(4, y - 8)
                    text.setZValue(1)
                    self._unit_labels.append(text)

            title = self._scene.addText(
                inv.rack_mount_face_label(self._face),
                QFont("Segoe UI", 9, QFont.Weight.DemiBold),
            )
            title.setDefaultTextColor(QColor("#2f7c85"))
            title.setPos(4, 0)
            title.setZValue(1)

            pp_side = (
                PortSide.FRONT
                if self._face == RackMountFace.FRONT
                else PortSide.REAR
            )
            for device in inv.devices_in_rack(snap, rack.id, face=self._face):
                dtype = next((t for t in snap.device_types if t.id == device.device_type_id), None)
                role = device.role if dtype is None else dtype.role
                height_u = max(1, int(device.rack_u_height or 1))
                rack_u = int(device.rack_u or 1)
                side_total = side_busy = 0
                if role == DeviceRole.PATCH_PANEL:
                    side_total, side_busy = inv.rack_side_port_summary(
                        snap, device.id, pp_side
                    )
                item = RackDeviceItem(
                    device.id,
                    device.hostname,
                    role,
                    rack_u,
                    height_u,
                    units,
                    mount_face=device.rack_mount_face,
                    pp_side=pp_side,
                    side_total=side_total,
                    side_busy=side_busy,
                )
                occupied = inv.rack_occupied_units(
                    snap, rack.id, face=self._face, exclude_device_id=device.id
                )
                item.set_occupied_units(occupied)
                self._scene.addItem(item)
                self._items[device.id] = item

            self.fit_content()
            self._update_status_hint()
        finally:
            self._rebuild_guard = False

    def _first_free_u(self, rack: Rack, height_u: int = 1) -> int | None:
        snap = self._snapshot
        if snap is None:
            return None
        used = inv.rack_occupied_units(snap, rack.id, face=self._face)
        height = max(1, int(height_u))
        for candidate in range(1, rack.units - height + 2):
            block = set(range(candidate, candidate + height))
            if not block & used:
                return candidate
        return None

    def _mount_selected_device(self) -> None:
        snap = self._snapshot
        rack = self._current_rack()
        raw = self._add_combo.currentData()
        if snap is None or rack is None or raw is None:
            return
        device_id = UUID(str(raw))
        device = next((d for d in snap.devices if d.id == device_id), None)
        if device is None:
            return
        height_u = max(1, int(device.rack_u_height or 1))
        rack_u = self._first_free_u(rack, height_u)
        if rack_u is None:
            QMessageBox.warning(self, "Стойка", "Нет свободного места для устройства.")
            return
        try:
            cmd = MountRackDeviceCommand(
                snap,
                device_id,
                rack.id,
                rack_u,
                height_u,
                rack_mount_face=self._face,
                on_changed=self._after_change,
            )
            self._undo.push(cmd)
        except Exception as exc:
            QMessageBox.critical(self, "Стойка", str(exc))

    def _on_device_move_committed(
        self,
        device_id: object,
        old_rack_u: int,
        new_rack_u: int,
    ) -> None:
        snap = self._snapshot
        if snap is None or not isinstance(device_id, UUID):
            self._rebuild()
            return
        if old_rack_u == new_rack_u:
            return
        device = next((d for d in snap.devices if d.id == device_id), None)
        if device is None:
            return
        try:
            cmd = MoveRackDeviceCommand(
                snap,
                device_id,
                old_rack_u,
                new_rack_u,
                on_changed=self._after_change,
            )
            self._undo.push(cmd)
        except Exception as exc:
            QMessageBox.warning(self, "Стойка", str(exc))
            self._rebuild()

    def _item_at(self, view_pos: QPoint) -> RackDeviceItem | None:
        scene_pos = self._view.mapToScene(view_pos)
        for gitem in self._scene.items(scene_pos):
            if isinstance(gitem, RackDeviceItem):
                return gitem
        return None

    def _on_context_menu(self, pos: QPoint) -> None:
        item = self._item_at(pos)
        if item is None:
            return
        menu = QMenu(self)
        act_unmount = menu.addAction("Снять со стойки")
        act_height = menu.addAction("Высота U…")
        chosen = menu.exec(self._view.mapToGlobal(pos))
        if chosen is act_unmount:
            self._unmount_device(item.device_id)
        elif chosen is act_height:
            self._resize_device(item.device_id)

    def _unmount_device(self, device_id: UUID) -> None:
        snap = self._snapshot
        if snap is None:
            return
        try:
            cmd = UnmountRackDeviceCommand(
                snap, device_id, on_changed=self._after_change
            )
            self._undo.push(cmd)
        except Exception as exc:
            QMessageBox.warning(self, "Стойка", str(exc))

    def _resize_device(self, device_id: UUID) -> None:
        snap = self._snapshot
        rack = self._current_rack()
        if snap is None or rack is None:
            return
        device = next((d for d in snap.devices if d.id == device_id), None)
        if device is None or device.rack_u is None:
            return
        old_h = max(1, int(device.rack_u_height or 1))
        max_h = rack.units - int(device.rack_u) + 1
        value, ok = QInputDialog.getInt(
            self,
            "Высота в U",
            f"Высота «{device.hostname}» (U):",
            old_h,
            1,
            max(1, max_h),
        )
        if not ok or value == old_h:
            return
        try:
            cmd = ResizeRackDeviceCommand(
                snap,
                device_id,
                old_h,
                value,
                on_changed=self._after_change,
            )
            self._undo.push(cmd)
        except Exception as exc:
            QMessageBox.warning(self, "Стойка", str(exc))
            self._rebuild()

    def _after_change(self) -> None:
        self._rebuild()
        self.rack_changed.emit()

    def _on_scene_selection(self) -> None:
        if self._suppress_selection:
            return
        selected = self._scene.selectedItems()
        if not selected:
            self.device_selected.emit(None)
            return
        for item in selected:
            if isinstance(item, RackDeviceItem):
                self.device_selected.emit(item.device_id)
                return
