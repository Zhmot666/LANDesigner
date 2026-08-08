from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
    QUndoStack,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGraphicsLineItem,
    QGraphicsPixmapItem,
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
from landesigner.services import floor_plan as fp
from landesigner.ui.commands.floor_plan_commands import (
    MoveFloorAssetCommand,
    RemoveFloorAssetCommand,
)
from landesigner.ui.widgets.floor_plan_items import FloorDeviceItem


class FloorPlanScene(QGraphicsScene):
    asset_move_committed = Signal(object, float, float, float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSceneRect(-500, -500, 5000, 5000)
        self.setBackgroundBrush(QBrush(QColor("#eef3f5")))

    def commit_asset_move(
        self,
        item: FloorDeviceItem,
        old_pos: QPointF,
        new_pos: QPointF,
    ) -> None:
        self.asset_move_committed.emit(
            item.asset_id,
            old_pos.x(),
            old_pos.y(),
            new_pos.x(),
            new_pos.y(),
        )


class FloorPlanView(QWidget):
    """План этажа: подложка, маркеры устройств, масштаб, измерение трассы."""

    plan_changed = Signal()
    device_selected = Signal(object)  # UUID | None
    measure_finished = Signal(float)  # длина в метрах

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._snapshot: ProjectSnapshot | None = None
        self._project_file: str | None = None
        self._floor_id: UUID | None = None
        self._markers: dict[UUID, FloorDeviceItem] = {}
        self._undo = QUndoStack(self)
        self._panning = False
        self._pan_start = QPoint()
        self._rebuild_guard = False
        self._suppress_selection = False
        self._measure_mode = False
        self._measure_points: list[QPointF] = []
        self._measure_lines: list[QGraphicsLineItem] = []
        self._bg_item: QGraphicsPixmapItem | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.addWidget(QLabel("Этаж:", self))
        self._floor_combo = QComboBox(self)
        self._floor_combo.currentIndexChanged.connect(self._on_floor_combo)
        toolbar.addWidget(self._floor_combo, stretch=1)

        self._btn_bg = QPushButton("Подложка…", self)
        self._btn_place = QPushButton("Расставить", self)
        self._btn_measure = QPushButton("Измерить", self)
        self._btn_measure.setCheckable(True)
        self._btn_delete_marker = QPushButton("Убрать маркер", self)
        self._btn_delete_marker.setEnabled(False)
        self._btn_fit = QPushButton("Вписать", self)
        self._btn_undo = QPushButton("Отменить", self)
        self._btn_redo = QPushButton("Повторить", self)
        self._btn_bg.clicked.connect(self._import_background)
        self._btn_place.clicked.connect(self._place_devices)
        self._btn_measure.toggled.connect(self._on_measure_toggled)
        self._btn_delete_marker.clicked.connect(self._delete_selected_marker)
        self._btn_fit.clicked.connect(self.fit_content)
        self._btn_undo.clicked.connect(self._undo.undo)
        self._btn_redo.clicked.connect(self._undo.redo)
        self._undo.canUndoChanged.connect(self._btn_undo.setEnabled)
        self._undo.canRedoChanged.connect(self._btn_redo.setEnabled)
        self._btn_undo.setEnabled(False)
        self._btn_redo.setEnabled(False)
        for btn in (
            self._btn_bg,
            self._btn_place,
            self._btn_measure,
            self._btn_delete_marker,
            self._btn_undo,
            self._btn_redo,
            self._btn_fit,
        ):
            toolbar.addWidget(btn)
        root.addLayout(toolbar)

        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel("Масштаб м/пикс:", self))
        self._scale = QDoubleSpinBox(self)
        self._scale.setDecimals(5)
        self._scale.setRange(0.00001, 10.0)
        self._scale.setSingleStep(0.001)
        self._scale.setValue(0.1)
        self._scale.valueChanged.connect(self._on_scale_changed)
        scale_row.addWidget(self._scale)
        self._hint = QLabel(
            "Выберите этаж · подложка · перетащите маркеры · Измерить — клики, Enter — готово",
            self,
        )
        self._hint.setObjectName("PanelSubtitle")
        self._hint.setProperty("muted", True)
        scale_row.addWidget(self._hint, stretch=1)
        self._measure_label = QLabel("", self)
        self._measure_label.setObjectName("PanelSubtitle")
        scale_row.addWidget(self._measure_label)
        root.addLayout(scale_row)

        self._scene = FloorPlanScene(self)
        self._view = QGraphicsView(self._scene, self)
        self._view.setObjectName("TopologyCanvas")
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self._view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._view.setFrameShape(QFrame.Shape.StyledPanel)
        self._view.viewport().installEventFilter(self)
        root.addWidget(self._view, stretch=1)

        self._scene.asset_move_committed.connect(self._on_asset_move_committed)
        self._scene.selectionChanged.connect(self._on_selection_changed)

        QShortcut(QKeySequence.StandardKey.Undo, self, activated=self._undo.undo)
        QShortcut(QKeySequence.StandardKey.Redo, self, activated=self._undo.redo)
        QShortcut(QKeySequence("Ctrl+0"), self, activated=self.fit_content)
        QShortcut(QKeySequence(Qt.Key.Key_Return), self, activated=self._finish_measure)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self, activated=self._finish_measure)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self._cancel_measure)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self, activated=self._delete_selected_marker)

    def undo(self) -> None:
        self._undo.undo()

    def redo(self) -> None:
        self._undo.redo()

    def can_undo(self) -> bool:
        return self._undo.canUndo()

    def can_redo(self) -> bool:
        return self._undo.canRedo()

    def set_project_file(self, path: str | None) -> None:
        self._project_file = path

    def set_snapshot(self, snapshot: ProjectSnapshot | None) -> None:
        prev = self._floor_id
        self._snapshot = snapshot
        self._undo.clear()
        self._cancel_measure()
        self._reload_floors(prefer=prev)
        self._rebuild()

    def select_floor(self, floor_id: UUID | None) -> None:
        if floor_id is None:
            return
        idx = self._floor_combo.findData(str(floor_id))
        if idx >= 0:
            self._floor_combo.setCurrentIndex(idx)

    def select_device(self, device_id: UUID | None) -> None:
        self._suppress_selection = True
        try:
            self._scene.clearSelection()
            if device_id is None:
                return
            for item in self._markers.values():
                if item.device_id == device_id:
                    item.setSelected(True)
                    self._view.centerOn(item)
                    break
        finally:
            self._suppress_selection = False

    def fit_content(self) -> None:
        if self._bg_item is not None:
            self._view.fitInView(
                self._bg_item.boundingRect(),
                Qt.AspectRatioMode.KeepAspectRatio,
            )
            return
        if self._markers:
            rect = self._scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
            self._view.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        else:
            self._view.resetTransform()

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self._view.viewport():
            et = event.type()
            if et == QEvent.Type.Wheel:
                self._zoom(event)
                return True
            if et == QEvent.Type.MouseButtonPress:
                if self._measure_mode and event.button() == Qt.MouseButton.LeftButton:
                    scene_pos = self._view.mapToScene(event.position().toPoint())
                    self._add_measure_point(scene_pos)
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
        if factor > 1 and current > 8:
            return
        if factor < 1 and current < 0.05:
            return
        self._view.scale(factor, factor)

    def _reload_floors(self, prefer: UUID | None = None) -> None:
        self._floor_combo.blockSignals(True)
        self._floor_combo.clear()
        if self._snapshot is None:
            self._floor_id = None
            self._floor_combo.blockSignals(False)
            return
        for floor in self._snapshot.floors:
            self._floor_combo.addItem(fp.floor_label(self._snapshot, floor.id), str(floor.id))
        if prefer is not None:
            idx = self._floor_combo.findData(str(prefer))
            if idx >= 0:
                self._floor_combo.setCurrentIndex(idx)
        if self._floor_combo.count() > 0:
            raw = self._floor_combo.currentData()
            self._floor_id = UUID(str(raw)) if raw else None
        else:
            self._floor_id = None
        self._floor_combo.blockSignals(False)

    def _on_floor_combo(self) -> None:
        raw = self._floor_combo.currentData()
        self._floor_id = UUID(str(raw)) if raw else None
        self._undo.clear()
        self._cancel_measure()
        self._rebuild()

    def _on_scale_changed(self, value: float) -> None:
        if self._snapshot is None or self._floor_id is None or self._rebuild_guard:
            return
        try:
            fp.set_scale(self._snapshot, self._floor_id, value)
        except ValueError:
            return
        self.plan_changed.emit()
        self._update_measure_label()

    def _import_background(self) -> None:
        if self._snapshot is None or self._floor_id is None:
            QMessageBox.information(self, "План", "Сначала выберите этаж.")
            return
        if not self._project_file:
            QMessageBox.information(
                self,
                "План",
                "Сохраните проект (.lanproj), затем импортируйте подложку — "
                "файл копируется в каталог рядом с проектом.",
            )
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Подложка этажа",
            "",
            "Изображения (*.png *.jpg *.jpeg *.bmp *.webp);;Все файлы (*.*)",
        )
        if not path:
            return
        try:
            fp.import_plan_image(
                self._snapshot,
                self._floor_id,
                path,
                self._project_file,
            )
        except Exception as e:
            QMessageBox.critical(self, "Подложка", str(e))
            return
        self._rebuild()
        self.plan_changed.emit()
        self.fit_content()

    def _place_devices(self) -> None:
        if self._snapshot is None or self._floor_id is None:
            return
        if fp.ensure_assets_for_floor(self._snapshot, self._floor_id):
            self._rebuild()
            self.plan_changed.emit()
            self._hint.setText("Маркеры расставлены для устройств комнат этого этажа.")
        else:
            # Разрешим вручную поставить устройство без комнаты — через выбор из списка
            free = [
                d
                for d in self._snapshot.devices
                if fp.asset_for_device(self._snapshot, self._floor_id, d.id) is None
            ]
            if not free:
                QMessageBox.information(self, "План", "Все устройства уже на плане или нет устройств.")
                return
            # Простое размещение первого незанятого в центре вида
            center = self._view.mapToScene(self._view.viewport().rect().center())
            fp.place_device(
                self._snapshot,
                self._floor_id,
                free[0].id,
                x=center.x(),
                y=center.y(),
            )
            self._rebuild()
            self.plan_changed.emit()

    def _delete_selected_marker(self) -> None:
        if self._snapshot is None or self._measure_mode:
            return
        asset_id = None
        for item in self._scene.selectedItems():
            if isinstance(item, FloorDeviceItem):
                asset_id = item.asset_id
                break
        if asset_id is None:
            return
        cmd = RemoveFloorAssetCommand(
            self._snapshot,
            asset_id,
            on_changed=self._rebuild,
        )
        if cmd.isObsolete():
            return
        self._undo.push(cmd)
        self.plan_changed.emit()

    def _on_measure_toggled(self, checked: bool) -> None:
        self._measure_mode = checked
        self._clear_measure_graphics()
        self._measure_points.clear()
        if checked:
            self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self._view.setCursor(Qt.CursorShape.CrossCursor)
            self._hint.setText("Измерение: клики по трассе, Enter — длина, Esc — отмена")
            self._measure_label.setText("")
        else:
            self._view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self._view.unsetCursor()
            self._hint.setText(
                "Выберите этаж · подложка · перетащите маркеры · Измерить — клики, Enter — готово"
            )

    def _cancel_measure(self) -> None:
        if self._btn_measure.isChecked():
            self._btn_measure.setChecked(False)
        else:
            self._on_measure_toggled(False)

    def _add_measure_point(self, pos: QPointF) -> None:
        self._measure_points.append(pos)
        if len(self._measure_points) >= 2:
            a = self._measure_points[-2]
            b = self._measure_points[-1]
            line = QGraphicsLineItem(a.x(), a.y(), b.x(), b.y())
            line.setPen(QPen(QColor("#c45c26"), 2.0, Qt.PenStyle.DashLine))
            line.setZValue(3)
            self._scene.addItem(line)
            self._measure_lines.append(line)
        self._update_measure_label()

    def _finish_measure(self) -> None:
        if not self._measure_mode:
            return
        if self._snapshot is None or self._floor_id is None:
            return
        floor = fp.get_floor(self._snapshot, self._floor_id)
        pts = [(p.x(), p.y()) for p in self._measure_points]
        length_m = fp.path_length_m(pts, floor.scale_m_per_px)
        self._measure_label.setText(f"Длина: {length_m:.2f} м")
        self.measure_finished.emit(length_m)
        self._btn_measure.setChecked(False)

    def _update_measure_label(self) -> None:
        if not self._measure_points or self._snapshot is None or self._floor_id is None:
            return
        floor = fp.get_floor(self._snapshot, self._floor_id)
        pts = [(p.x(), p.y()) for p in self._measure_points]
        length_m = fp.path_length_m(pts, floor.scale_m_per_px)
        self._measure_label.setText(f"Черновик: {length_m:.2f} м")

    def _clear_measure_graphics(self) -> None:
        for line in self._measure_lines:
            self._scene.removeItem(line)
        self._measure_lines.clear()

    def _rebuild(self) -> None:
        if self._rebuild_guard:
            return
        self._rebuild_guard = True
        try:
            selected = None
            for item in self._scene.selectedItems():
                if isinstance(item, FloorDeviceItem):
                    selected = item.device_id
                    break

            self._scene.clear()
            self._markers.clear()
            self._bg_item = None
            self._measure_lines.clear()
            self._measure_points.clear()

            if self._snapshot is None or self._floor_id is None:
                self._scale.blockSignals(True)
                self._scale.setValue(0.1)
                self._scale.blockSignals(False)
                return

            floor = fp.get_floor(self._snapshot, self._floor_id)
            self._scale.blockSignals(True)
            self._scale.setValue(floor.scale_m_per_px)
            self._scale.blockSignals(False)

            if floor.plan_image_relpath and self._project_file:
                img_path = fp.resolve_plan_image(self._project_file, floor.plan_image_relpath)
                if img_path is not None:
                    pix = QPixmap(str(img_path))
                    if not pix.isNull():
                        self._bg_item = QGraphicsPixmapItem(pix)
                        self._bg_item.setZValue(0)
                        self._bg_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                        self._scene.addItem(self._bg_item)
                        self._scene.setSceneRect(
                            self._bg_item.boundingRect().adjusted(-100, -100, 100, 100)
                        )

            devices = {d.id: d for d in self._snapshot.devices}
            for asset in fp.assets_for_floor(self._snapshot, self._floor_id):
                device = devices.get(asset.device_id)
                if device is None:
                    continue
                item = FloorDeviceItem(
                    asset_id=asset.id,
                    device_id=device.id,
                    hostname=device.hostname,
                    role=device.role,
                    x=asset.x,
                    y=asset.y,
                )
                self._scene.addItem(item)
                self._markers[asset.id] = item

            if selected is not None:
                self.select_device(selected)
        finally:
            self._rebuild_guard = False

    def _on_asset_move_committed(
        self,
        asset_id: UUID,
        old_x: float,
        old_y: float,
        new_x: float,
        new_y: float,
    ) -> None:
        if self._snapshot is None:
            return
        cmd = MoveFloorAssetCommand(
            self._snapshot,
            asset_id,
            old_x,
            old_y,
            new_x,
            new_y,
            on_changed=self._apply_positions,
        )
        self._undo.push(cmd)
        self.plan_changed.emit()

    def _apply_positions(self) -> None:
        if self._snapshot is None:
            return
        by_id = {a.id: a for a in self._snapshot.floor_plan_assets}
        for asset_id, item in self._markers.items():
            asset = by_id.get(asset_id)
            if asset is None:
                continue
            if abs(item.pos().x() - asset.x) > 0.01 or abs(item.pos().y() - asset.y) > 0.01:
                item.setPos(asset.x, asset.y)

    def _on_selection_changed(self) -> None:
        if self._suppress_selection or self._rebuild_guard:
            return
        device_id = None
        for item in self._scene.selectedItems():
            if isinstance(item, FloorDeviceItem):
                device_id = item.device_id
                break
        self._btn_delete_marker.setEnabled(device_id is not None and not self._measure_mode)
        self.device_selected.emit(device_id)
