from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
)

from landesigner.domain.entities import ProjectSnapshot
from landesigner.services import inventory as inv
from landesigner.ui.table_utils import make_item, table_update, tune_table

_STATUS_COLOR = {
    "free": QColor("#667784"),
    "half": QColor("#b54708"),
    "through": QColor("#2f7c85"),
}


class PatchPanelMatrixDialog(QDialog):
    """Матрица сквозных пар Front↔Rear патч-панели."""

    connect_port_requested = Signal(object)  # UUID свободного порта PP

    def __init__(
        self,
        snapshot: ProjectSnapshot,
        device_id: UUID,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._snapshot = snapshot
        self._device_id = device_id
        device = next((d for d in snapshot.devices if d.id == device_id), None)
        name = device.hostname if device else str(device_id)
        self.setWindowTitle(f"Матрица пар — {name}")
        self.resize(780, 480)

        layout = QVBoxLayout(self)
        hint = QLabel(
            "Двойной клик по свободной стороне (Front/Rear) — создать кабель с этого порта. "
            "«Проброс» — кабели с обеих сторон пары.",
            self,
        )
        hint.setWordWrap(True)
        hint.setObjectName("HintLabel")
        layout.addWidget(hint)

        self._table = QTableWidget(self)
        tune_table(self._table)
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(
            ["#", "Front", "К Front", "Rear", "К Rear", "Статус"]
        )
        self._table.cellDoubleClicked.connect(self._on_cell_double)
        layout.addWidget(self._table, stretch=1)

        row = QHBoxLayout()
        self._summary = QLabel(self)
        self._summary.setProperty("muted", True)
        row.addWidget(self._summary, stretch=1)
        self._btn_connect = QPushButton("Кабель к выбранному…", self)
        self._btn_connect.clicked.connect(self._on_connect_clicked)
        row.addWidget(self._btn_connect)
        layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.setText("Закрыть")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        self.reload()

    def reload(self) -> None:
        pairs = inv.patch_panel_pairs(self._snapshot, self._device_id)
        free = half = through = 0
        with table_update(self._table):
            self._table.setRowCount(len(pairs))
            for row_idx, pair in enumerate(pairs):
                if pair.status == "free":
                    free += 1
                elif pair.status == "half":
                    half += 1
                else:
                    through += 1
                front_peer = (
                    inv.port_endpoint_label(self._snapshot, pair.front_peer_id)
                    if pair.front_peer_id
                    else "—"
                )
                rear_peer = (
                    inv.port_endpoint_label(self._snapshot, pair.rear_peer_id)
                    if pair.rear_peer_id
                    else "—"
                )
                status = inv.PATCH_PAIR_STATUS_RU.get(pair.status, pair.status)
                items = [
                    make_item(str(pair.position), sort_key=pair.position),
                    make_item(pair.front.name, entity_id=pair.front.id),
                    make_item(front_peer),
                    make_item(pair.rear.name, entity_id=pair.rear.id),
                    make_item(rear_peer),
                    make_item(status),
                ]
                color = _STATUS_COLOR.get(pair.status)
                for col, item in enumerate(items):
                    if color is not None and col == 5:
                        item.setForeground(QBrush(color))
                    if pair.status == "through" and col in (2, 4):
                        item.setToolTip(inv.patch_through_path_label(self._snapshot, pair))
                    self._table.setItem(row_idx, col, item)
        self._summary.setText(
            f"Пар: {len(pairs)} · свободных {free} · одна сторона {half} · проброс {through}"
        )

    def _selected_free_port_id(self) -> UUID | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        row = rows[0].row()
        pair_rows = inv.patch_panel_pairs(self._snapshot, self._device_id)
        if row < 0 or row >= len(pair_rows):
            return None
        pair = pair_rows[row]
        if pair.front_peer_id is None:
            return pair.front.id
        if pair.rear_peer_id is None:
            return pair.rear.id
        return None

    def _on_connect_clicked(self) -> None:
        port_id = self._selected_free_port_id()
        if port_id is None:
            return
        self.connect_port_requested.emit(port_id)

    def _on_cell_double(self, row: int, column: int) -> None:
        pairs = inv.patch_panel_pairs(self._snapshot, self._device_id)
        if row < 0 or row >= len(pairs):
            return
        pair = pairs[row]
        port_id: UUID | None = None
        if column in (1, 2) and pair.front_peer_id is None:
            port_id = pair.front.id
        elif column in (3, 4) and pair.rear_peer_id is None:
            port_id = pair.rear.id
        elif column == 0:
            port_id = self._selected_free_port_id()
        if port_id is not None:
            self.connect_port_requested.emit(port_id)
