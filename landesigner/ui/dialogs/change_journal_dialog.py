from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
)

from landesigner.domain.entities import ProjectSnapshot
from landesigner.services import change_journal as journal
from landesigner.ui.dialogs.inventory_dialogs import _russian_buttons
from landesigner.ui.dialogs.sync_dialogs import KEY_CLIENT_NAME, SETTINGS_APP, SETTINGS_ORG
from landesigner.ui.table_utils import make_item, table_update, tune_table


class ChangeJournalDialog(QDialog):
    """Просмотр журнала изменений проекта (кто / что / когда)."""

    def __init__(self, snapshot: ProjectSnapshot, parent=None) -> None:
        super().__init__(parent)
        self._snapshot = snapshot
        self.setWindowTitle("Журнал изменений проекта")
        self.resize(900, 520)

        layout = QVBoxLayout(self)
        actor_row = QHBoxLayout()
        actor_row.addWidget(QLabel("Оператор (автор записей):", self))
        self._actor = QLineEdit(journal.resolve_actor(), self)
        self._actor.setPlaceholderText("Имя для журнала и блокировок sync")
        actor_row.addWidget(self._actor, stretch=1)
        btn_save_actor = QPushButton("Сохранить имя", self)
        btn_save_actor.clicked.connect(self._save_actor)
        actor_row.addWidget(btn_save_actor)
        layout.addLayout(actor_row)

        hint = QLabel(
            "Записи добавляются при правках проекта и сохраняются в файле .lanproj. "
            "Удаление записей из UI недоступно (append-only).",
            self,
        )
        hint.setWordWrap(True)
        hint.setObjectName("PanelSubtitle")
        hint.setProperty("muted", True)
        layout.addWidget(hint)

        self._table = QTableWidget(self)
        tune_table(self._table)
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            ["Когда (UTC)", "Кто", "Действие", "Подробности", "Объект"]
        )
        layout.addWidget(self._table, stretch=1)
        self._reload()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        _russian_buttons(buttons)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save_actor(self) -> None:
        name = self._actor.text().strip()
        if not name:
            QMessageBox.warning(self, "Оператор", "Укажите имя.")
            return
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        settings.setValue(KEY_CLIENT_NAME, name)
        QMessageBox.information(
            self,
            "Оператор",
            f"Имя сохранено: {name}\n"
            "Оно же используется при блокировке проекта на sync-сервере.",
        )

    def _reload(self) -> None:
        entries = journal.entries_newest_first(self._snapshot)
        with table_update(self._table):
            self._table.setRowCount(len(entries))
            for row, entry in enumerate(entries):
                when = entry.created_at.strftime("%Y-%m-%d %H:%M:%S")
                obj = entry.entity_kind
                if entry.entity_id is not None:
                    obj = (
                        f"{obj}:{str(entry.entity_id)[:8]}"
                        if obj
                        else str(entry.entity_id)[:8]
                    )
                self._table.setItem(
                    row, 0, make_item(when, sort_key=entry.created_at.isoformat())
                )
                self._table.setItem(row, 1, make_item(entry.actor or "—"))
                self._table.setItem(row, 2, make_item(entry.action or "—"))
                self._table.setItem(row, 3, make_item(entry.detail or "—"))
                self._table.setItem(row, 4, make_item(obj or "—"))
        self._table.resizeColumnsToContents()
