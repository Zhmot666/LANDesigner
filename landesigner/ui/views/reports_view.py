from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from landesigner.domain.entities import ProjectSnapshot
from landesigner.services import reports as reports_svc
from landesigner.services import validation as validation_svc
from landesigner.services.reports import ReportKind
from landesigner.services.validation import IssueSeverity
from landesigner.ui.widgets.panel_card import PanelCard

_SEVERITY_RU = {
    IssueSeverity.ERROR: "Ошибка",
    IssueSeverity.WARNING: "Предупреждение",
    IssueSeverity.INFO: "Инфо",
}

_SEVERITY_COLOR = {
    IssueSeverity.ERROR: QColor("#b42318"),
    IssueSeverity.WARNING: QColor("#b54708"),
    IssueSeverity.INFO: QColor("#667784"),
}


class ReportsView(QWidget):
    """Валидация проекта и табличные отчёты (CSV / печать)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._snapshot: ProjectSnapshot | None = None
        self._current_report: reports_svc.ReportTable | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, stretch=1)

        # --- Валидация ---
        issues_card = PanelCard("Проверки", splitter, subtitle="Нажмите «Проверить»")
        self._btn_validate = QPushButton("Проверить", issues_card)
        self._btn_validate.setObjectName("PrimaryButton")
        self._btn_validate.setProperty("role", "primary")
        self._btn_validate.clicked.connect(self.run_validation)
        issues_card.add_action(self._btn_validate)
        self._issues_table = QTableWidget(issues_card)
        self._tune_table(self._issues_table)
        self._issues_table.setColumnCount(3)
        self._issues_table.setHorizontalHeaderLabels(["Уровень", "Проверка", "Сообщение"])
        issues_card.set_body_widget(self._issues_table)
        splitter.addWidget(issues_card)

        # --- Отчёты ---
        reports_card = PanelCard("Отчёты", splitter)
        self._report_kind = QComboBox(reports_card)
        for kind in ReportKind:
            self._report_kind.addItem(reports_svc.REPORT_TITLES[kind], kind.value)
        self._btn_build = QPushButton("Сформировать", reports_card)
        self._btn_build.setObjectName("PrimaryButton")
        self._btn_build.setProperty("role", "primary")
        self._btn_csv = QPushButton("CSV…", reports_card)
        self._btn_print = QPushButton("Печать…", reports_card)
        self._btn_build.clicked.connect(self.build_report)
        self._btn_csv.clicked.connect(self.export_csv)
        self._btn_print.clicked.connect(self.print_report)
        reports_card.add_action(self._btn_build)
        reports_card.add_action(self._btn_csv)
        reports_card.add_action(self._btn_print)

        body = QWidget(reports_card)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(6)
        kind_row = QHBoxLayout()
        kind_row.addWidget(QLabel("Тип:", body))
        kind_row.addWidget(self._report_kind, stretch=1)
        body_layout.addLayout(kind_row)
        self._report_hint = QLabel("", body)
        self._report_hint.setObjectName("PanelSubtitle")
        self._report_hint.setProperty("muted", True)
        body_layout.addWidget(self._report_hint)
        self._report_table = QTableWidget(body)
        self._tune_table(self._report_table)
        body_layout.addWidget(self._report_table, stretch=1)
        reports_card.set_body_widget(body)
        splitter.addWidget(reports_card)
        splitter.setSizes([220, 420])

    def set_snapshot(self, snapshot: ProjectSnapshot | None) -> None:
        self._snapshot = snapshot
        self._issues_table.setRowCount(0)
        self._report_table.setRowCount(0)
        self._current_report = None
        self._report_hint.setText("")
        if snapshot is not None:
            # Автопроверка при открытии вкладки с данными — лёгкая.
            self.run_validation()

    def run_validation(self) -> None:
        self._issues_table.setRowCount(0)
        if self._snapshot is None:
            return
        issues = validation_svc.validate_project(self._snapshot)
        stats = validation_svc.summary(issues)
        card = self._issues_table.parent()
        # PanelCard — родитель таблицы через body; подпись обновим через find.
        parent = self._issues_table.parentWidget()
        while parent is not None and not isinstance(parent, PanelCard):
            parent = parent.parentWidget()
        if isinstance(parent, PanelCard):
            if stats["total"] == 0:
                parent.set_subtitle("Замечаний нет")
            else:
                parent.set_subtitle(
                    f"ошибок {stats['errors']} · предупр. {stats['warnings']} · "
                    f"инфо {stats['infos']}"
                )

        self._issues_table.setRowCount(len(issues))
        for row, issue in enumerate(issues):
            sev = QTableWidgetItem(_SEVERITY_RU.get(issue.severity, issue.severity.value))
            sev.setForeground(_SEVERITY_COLOR.get(issue.severity, QColor("#23313a")))
            self._issues_table.setItem(row, 0, sev)
            check = QTableWidgetItem(issue.code_label)
            check.setToolTip(issue.code)
            self._issues_table.setItem(row, 1, check)
            self._issues_table.setItem(row, 2, QTableWidgetItem(issue.message))
        self._issues_table.resizeColumnsToContents()

    def build_report(self) -> None:
        if self._snapshot is None:
            QMessageBox.information(self, "Отчёты", "Сначала откройте или создайте проект.")
            return
        raw = self._report_kind.currentData()
        kind = ReportKind(str(raw))
        table = reports_svc.build_report(self._snapshot, kind)
        self._current_report = table
        self._fill_report_table(table)
        self._report_hint.setText(f"{table.title}: строк {len(table.rows)}")

    def export_csv(self) -> None:
        if self._current_report is None:
            self.build_report()
        if self._current_report is None:
            return
        suggested = f"{self._current_report.kind.value}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт отчёта CSV",
            suggested,
            "CSV (*.csv);;Все файлы (*.*)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            reports_svc.export_report_csv(self._current_report, path)
        except Exception as e:
            QMessageBox.critical(self, "Экспорт", str(e))
            return
        QMessageBox.information(self, "Экспорт", f"Сохранено:\n{path}")

    def print_report(self) -> None:
        if self._current_report is None:
            self.build_report()
        if self._current_report is None:
            return
        name = self._snapshot.meta.name if self._snapshot else ""
        html = reports_svc.report_to_html(self._current_report, project_name=name)
        doc = QTextDocument()
        doc.setHtml(html)
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("Печать отчёта")
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return
        doc.print_(printer)

    def _fill_report_table(self, table: reports_svc.ReportTable) -> None:
        self._report_table.clear()
        self._report_table.setColumnCount(len(table.headers))
        self._report_table.setHorizontalHeaderLabels(table.headers)
        self._report_table.setRowCount(len(table.rows))
        for r_idx, row in enumerate(table.rows):
            for c_idx, cell in enumerate(row):
                self._report_table.setItem(r_idx, c_idx, QTableWidgetItem(cell))
        self._report_table.resizeColumnsToContents()

    @staticmethod
    def _tune_table(table: QTableWidget) -> None:
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
