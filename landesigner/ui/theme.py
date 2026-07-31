from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

# Teal / slate — «сетевой» акцент, без фиолетового AI-дефолта.
STYLESHEET = """
QWidget {
    color: #1a2332;
    font-size: 13px;
}

QMainWindow, QDialog {
    background-color: #e8eef4;
}

QMenuBar {
    background-color: #0f2744;
    color: #e8f4f8;
    padding: 4px 8px;
    border-bottom: 2px solid #14b8a6;
}

QMenuBar::item {
    background: transparent;
    padding: 6px 12px;
    border-radius: 4px;
}

QMenuBar::item:selected {
    background-color: #1a3a5c;
}

QMenu {
    background-color: #ffffff;
    border: 1px solid #c5d4e0;
    border-radius: 8px;
    padding: 6px;
}

QMenu::item {
    padding: 8px 24px 8px 16px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #ccfbf1;
    color: #0f2744;
}

QStatusBar {
    background-color: #0f2744;
    color: #a7f3d0;
    border-top: 1px solid #14b8a6;
    min-height: 26px;
    padding: 2px 10px;
}

QSplitter::handle {
    background-color: #c5d4e0;
    width: 2px;
    height: 2px;
}

QSplitter::handle:hover {
    background-color: #14b8a6;
}

/* —— боковая панель площадки (светлая — читаемый текст) —— */
#SiteSidebar {
    background-color: #f8fafc;
    border-right: 1px solid #cbd5e1;
}

#SiteSidebar QLabel#SidebarTitle {
    color: #0d9488;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.5px;
    padding: 14px 14px 4px 14px;
}

#SiteSidebar QLabel#SidebarBrand {
    color: #0f2744;
    font-size: 18px;
    font-weight: 700;
    padding: 0 14px 10px 14px;
}

#SiteSidebar QTreeWidget {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    color: #0f172a;
    outline: none;
    padding: 4px;
    margin: 0 8px;
}

#SiteSidebar QTreeWidget::item {
    color: #0f172a;
    padding: 6px 8px;
    border-radius: 6px;
    margin: 1px 2px;
}

#SiteSidebar QTreeWidget::item:hover {
    background-color: #ccfbf1;
    color: #0f172a;
}

#SiteSidebar QTreeWidget::item:selected {
    background-color: #14b8a6;
    color: #042f2e;
}

#SiteSidebar QTreeWidget::item:selected:!active {
    background-color: #99f6e4;
    color: #042f2e;
}

#SiteSidebar QTreeWidget::branch {
    background: transparent;
}

#SiteSidebar QPushButton {
    background-color: #ffffff;
    color: #0f2744;
    border: 1px solid #94a3b8;
    border-radius: 6px;
    padding: 6px 8px;
    font-size: 12px;
}

#SiteSidebar QPushButton:hover {
    background-color: #ccfbf1;
    color: #0f766e;
    border-color: #14b8a6;
}

#SiteSidebar QPushButton#DangerButton {
    background-color: #fff1f2;
    border-color: #fda4af;
    color: #9f1239;
}

#SiteSidebar QPushButton#DangerButton:hover {
    background-color: #be123c;
    color: #fff;
    border-color: #be123c;
}

/* —— вкладки —— */
QTabWidget::pane {
    background-color: #f4f7fa;
    border: 1px solid #c5d4e0;
    border-radius: 10px;
    top: -1px;
    padding: 4px;
}

QTabBar::tab {
    background-color: #d5e0ea;
    color: #475569;
    border: 1px solid #c5d4e0;
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 9px 18px;
    margin-right: 3px;
    font-weight: 600;
}

QTabBar::tab:selected {
    background-color: #f4f7fa;
    color: #0f2744;
    border-bottom: 2px solid #14b8a6;
}

QTabBar::tab:hover:!selected {
    background-color: #e2eaf1;
    color: #0f2744;
}

/* —— таблицы —— */
QTableWidget {
    background-color: #ffffff;
    alternate-background-color: #f0f9f7;
    border: 1px solid #c5d4e0;
    border-radius: 8px;
    gridline-color: #e2e8f0;
    selection-background-color: #99f6e4;
    selection-color: #042f2e;
}

QHeaderView::section {
    background-color: #0f2744;
    color: #99f6e4;
    padding: 8px 10px;
    border: none;
    border-right: 1px solid #1a3a5c;
    font-weight: 600;
}

QHeaderView::section:last {
    border-right: none;
}

/* —— кнопки —— */
QPushButton {
    background-color: #ffffff;
    color: #0f2744;
    border: 1px solid #94a3b8;
    border-radius: 7px;
    padding: 7px 14px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #ccfbf1;
    border-color: #14b8a6;
    color: #0f766e;
}

QPushButton:pressed {
    background-color: #99f6e4;
}

QPushButton:disabled {
    background-color: #e2e8f0;
    color: #94a3b8;
    border-color: #cbd5e1;
}

QPushButton#PrimaryButton {
    background-color: #0d9488;
    color: #f0fdfa;
    border: 1px solid #0f766e;
}

QPushButton#PrimaryButton:hover {
    background-color: #14b8a6;
    border-color: #14b8a6;
    color: #042f2e;
}

/* —— поля ввода —— */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #ffffff;
    border: 1px solid #94a3b8;
    border-radius: 6px;
    padding: 6px 8px;
    min-height: 22px;
    selection-background-color: #99f6e4;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 2px solid #14b8a6;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QListWidget {
    background-color: #ffffff;
    border: 1px solid #c5d4e0;
    border-radius: 8px;
    padding: 4px;
}

QListWidget::item {
    padding: 4px 6px;
    border-radius: 4px;
}

QListWidget::item:selected {
    background-color: #ccfbf1;
    color: #0f2744;
}

QLabel#SectionTitle {
    color: #0f2744;
    font-size: 13px;
    font-weight: 700;
    padding: 2px 0;
}

QLabel#EmptyTitle {
    color: #0f2744;
    font-size: 22px;
    font-weight: 700;
}

QLabel#EmptySubtitle {
    color: #64748b;
    font-size: 14px;
}

QFrame#EmptyPane {
    background-color: #f4f7fa;
    border: 1px dashed #94a3b8;
    border-radius: 12px;
}

QMessageBox {
    background-color: #f4f7fa;
}

QScrollBar:vertical {
    background: #e8eef4;
    width: 10px;
    margin: 0;
    border-radius: 5px;
}

QScrollBar::handle:vertical {
    background: #94a3b8;
    border-radius: 5px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background: #14b8a6;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")

    font = QFont("Segoe UI", 10)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#e8eef4"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#1a2332"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#f0f9f7"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#1a2332"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#0f2744"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#14b8a6"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#042f2e"))
    palette.setColor(QPalette.ColorRole.Link, QColor("#0d9488"))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)
