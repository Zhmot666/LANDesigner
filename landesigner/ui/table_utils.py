"""Общие настройки таблиц: разделители колонок и сортировка по заголовку."""

from __future__ import annotations

from contextlib import contextmanager
from ipaddress import ip_address
from typing import Iterator
from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

_SORT_ROLE = int(Qt.ItemDataRole.UserRole) + 32


class SortableTableItem(QTableWidgetItem):
    """Ячейка с опциональным ключом сортировки (числа, IP и т.п.)."""

    def __lt__(self, other: QTableWidgetItem) -> bool:  # type: ignore[override]
        left = self.data(_SORT_ROLE)
        right = other.data(_SORT_ROLE) if other is not None else None
        if left is not None and right is not None:
            try:
                return left < right
            except TypeError:
                pass
        return (self.text() or "").casefold() < ((other.text() if other else "") or "").casefold()


def ip_sort_key(value: str) -> tuple:
    """Ключ сортировки для IPv4/IPv6: 10.0.0.2 перед 10.0.0.10."""
    text = (value or "").strip()
    if not text or text == "—":
        return (2, 0, "")
    try:
        addr = ip_address(text.split("/")[0].strip())
        return (0 if addr.version == 4 else 1, int(addr), "")
    except ValueError:
        return (2, 0, text.casefold())


def mac_sort_key(value: str) -> tuple:
    text = (value or "").strip()
    if not text or text == "—":
        return (1, "")
    hex_chars = "".join(ch for ch in text if ch.isalnum()).upper()
    return (0, hex_chars)


def make_item(
    text: str,
    *,
    sort_key: object | None = None,
    entity_id: UUID | str | None = None,
) -> SortableTableItem:
    item = SortableTableItem(text)
    if sort_key is not None:
        item.setData(_SORT_ROLE, sort_key)
    if entity_id is not None:
        item.setData(Qt.ItemDataRole.UserRole, str(entity_id))
    return item


def make_ip_item(
    text: str,
    *,
    entity_id: UUID | str | None = None,
) -> SortableTableItem:
    return make_item(text, sort_key=ip_sort_key(text), entity_id=entity_id)


def tune_table(table: QTableWidget) -> None:
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setWordWrap(False)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(28)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    table.setFrameShape(QTableWidget.Shape.NoFrame)
    table.setSortingEnabled(True)

    header = table.horizontalHeader()
    header.setStretchLastSection(True)
    header.setHighlightSections(False)
    header.setSectionsClickable(True)
    header.setSortIndicatorShown(True)
    header.setMinimumSectionSize(56)
    header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)


@contextmanager
def table_update(table: QTableWidget) -> Iterator[None]:
    """Отключить сортировку на время заполнения, чтобы строки не «прыгали»."""
    sorting = table.isSortingEnabled()
    table.setSortingEnabled(False)
    try:
        yield
    finally:
        table.setSortingEnabled(sorting)


def select_row_by_id(
    table: QTableWidget,
    entity_id: UUID | None,
    *,
    column: int = 0,
) -> bool:
    if entity_id is None:
        return False
    key = str(entity_id)
    for row in range(table.rowCount()):
        item = table.item(row, column)
        if item is not None and item.data(Qt.ItemDataRole.UserRole) == key:
            table.selectRow(row)
            return True
    return False
