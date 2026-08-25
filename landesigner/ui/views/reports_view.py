from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSplitter,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from landesigner.domain.entities import ProjectSnapshot
from landesigner.services import cable_labels as cable_label_service
from landesigner.services import reports as reports_svc
from landesigner.services import validation as validation_svc
from landesigner.services.reports import ReportKind
from landesigner.services.validation import IssueSeverity
from landesigner.ui.icons import icon_action_button
from landesigner.ui.table_utils import make_item, table_update, tune_table
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


def export_report_pdf(html: str, path: str | Path) -> None:
    """Сохранить HTML-отчёт в PDF через Qt (без внешних зависимостей)."""
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(path))
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setPageOrientation(QPageLayout.Orientation.Landscape)
    doc = QTextDocument()
    doc.setHtml(html)
    doc.print_(printer)


class ReportsView(QWidget):
    """Валидация проекта и табличные отчёты (CSV / PDF / печать)."""

    project_modified = Signal(int)

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
        issues_card = PanelCard(
            "Проверки", splitter, subtitle="Кнопка «галочка» в шапке — запуск проверки"
        )
        self._btn_validate = icon_action_button(
            "check", "Проверить проект", issues_card, role="primary"
        )
        self._btn_fill_labels = icon_action_button(
            "add", "Заполнить метки кабелей", issues_card
        )
        self._btn_validate.clicked.connect(self.run_validation)
        self._btn_fill_labels.clicked.connect(self.fill_cable_labels)
        issues_card.add_action(self._btn_validate)
        issues_card.add_action(self._btn_fill_labels)
        self._issues_table = QTableWidget(issues_card)
        tune_table(self._issues_table)
        self._issues_table.setColumnCount(3)
        self._issues_table.setHorizontalHeaderLabels(["Уровень", "Проверка", "Сообщение"])
        issues_card.set_body_widget(self._issues_table)
        splitter.addWidget(issues_card)

        # --- Отчёты ---
        reports_card = PanelCard("Отчёты", splitter)
        self._report_kind = QComboBox(reports_card)
        for kind in ReportKind:
            self._report_kind.addItem(reports_svc.REPORT_TITLES[kind], kind.value)
        self._btn_build = icon_action_button(
            "report", "Сформировать отчёт", reports_card, role="primary"
        )
        self._btn_csv = icon_action_button("csv", "Экспорт отчёта в CSV…", reports_card)
        self._btn_pdf = icon_action_button("pdf", "Экспорт отчёта в PDF…", reports_card)
        self._btn_print = icon_action_button("print", "Печать отчёта…", reports_card)
        self._btn_build.clicked.connect(self.build_report)
        self._btn_csv.clicked.connect(self.export_csv)
        self._btn_pdf.clicked.connect(self.export_pdf)
        self._btn_print.clicked.connect(self.print_report)
        reports_card.add_action(self._btn_build)
        reports_card.add_action(self._btn_csv)
        reports_card.add_action(self._btn_pdf)
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
        tune_table(self._report_table)
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

        with table_update(self._issues_table):
            self._issues_table.setRowCount(len(issues))
            for row, issue in enumerate(issues):
                sev = make_item(
                    _SEVERITY_RU.get(issue.severity, issue.severity.value),
                    sort_key=issue.severity.value,
                )
                sev.setForeground(_SEVERITY_COLOR.get(issue.severity, QColor("#23313a")))
                self._issues_table.setItem(row, 0, sev)
                check = make_item(issue.code_label)
                check.setToolTip(issue.code)
                self._issues_table.setItem(row, 1, check)
                self._issues_table.setItem(row, 2, make_item(issue.message))
        self._issues_table.resizeColumnsToContents()

    def fill_cable_labels(self) -> None:
        if self._snapshot is None:
            QMessageBox.information(self, "Метки кабелей", "Сначала откройте проект.")
            return
        count = cable_label_service.fill_missing_cable_labels(self._snapshot)
        if count <= 0:
            QMessageBox.information(
                self,
                "Метки кабелей",
                "Все кабели уже имеют метки.",
            )
            return
        self.project_modified.emit(count)
        self.run_validation()
        QMessageBox.information(
            self,
            "Метки кабелей",
            f"Сгенерировано меток: {count}.",
        )

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

    def export_pdf(self) -> None:
        if self._current_report is None:
            self.build_report()
        if self._current_report is None:
            return
        suggested = f"{self._current_report.kind.value}.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт отчёта PDF",
            suggested,
            "PDF (*.pdf);;Все файлы (*.*)",
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        name = self._snapshot.meta.name if self._snapshot else ""
        html = reports_svc.report_to_html(self._current_report, project_name=name)
        try:
            export_report_pdf(html, path)
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
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        printer.setPageOrientation(QPageLayout.Orientation.Landscape)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("Печать отчёта")
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return
        doc.print_(printer)

    def _fill_report_table(self, table: reports_svc.ReportTable) -> None:
        with table_update(self._report_table):
            self._report_table.clear()
            self._report_table.setColumnCount(len(table.headers))
            self._report_table.setHorizontalHeaderLabels(table.headers)
            self._report_table.setRowCount(len(table.rows))
            for r_idx, row in enumerate(table.rows):
                for c_idx, cell in enumerate(row):
                    self._report_table.setItem(r_idx, c_idx, make_item(cell))
        self._report_table.resizeColumnsToContents()
