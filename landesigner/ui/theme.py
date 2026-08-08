from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

# Корень репозитория: landesigner/ui/theme.py → ../..
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DESIGNER_STYLE = _PROJECT_ROOT / "Designer" / "Стиль.css"

# Дополнения поверх Designer/Стиль.css: меню, статусбар, сайдбар, плейсхолдеры,
# алиасы objectName → role из макета.
_APP_EXTRAS = """
QMenuBar {
    background: #eef3f5;
    color: #23313a;
    padding: 4px 8px;
    border-bottom: 1px solid #d8e0e6;
}

QMenuBar::item {
    background: transparent;
    padding: 6px 12px;
    border-radius: 4px;
}

QMenuBar::item:selected {
    background: #e7f2f3;
    color: #2f7c85;
}

QMenu {
    background: #ffffff;
    border: 1px solid #d8e0e6;
    border-radius: 8px;
    padding: 6px;
}

QMenu::item {
    padding: 8px 20px 8px 14px;
    border-radius: 4px;
}

QMenu::item:selected {
    background: #e7f2f3;
    color: #2f7c85;
}

QStatusBar {
    background: #eef3f5;
    color: #667784;
    border-top: 1px solid #d8e0e6;
    min-height: 26px;
    padding: 2px 10px;
}

QSplitter::handle {
    background: #d8e0e6;
    width: 2px;
    height: 2px;
}

QFrame#TopologyCanvas,
QGraphicsView#TopologyCanvas {
    background: #f4f7f8;
    border: 1px solid #d8e0e6;
    border-radius: 8px;
}


QDoubleSpinBox {
    background: #ffffff;
    color: #23313a;
    border: 1px solid #c7d1d8;
    border-radius: 6px;
    padding: 2px 8px;
    min-height: 22px;
    max-height: 26px;
}

QDoubleSpinBox:focus {
    border: 1px solid #2f7c85;
}

/* Primary как в макете: teal-текст/обводка, не заливка */
QPushButton#PrimaryButton,
QPushButton[role="primary"] {
    background: #ffffff;
    color: #2f7c85;
    border: 1px solid #2f7c85;
    font-weight: 600;
}

QPushButton#PrimaryButton:hover,
QPushButton[role="primary"]:hover {
    background: #e7f2f3;
    color: #276871;
    border: 1px solid #276871;
}

QPushButton#PrimaryButton:pressed,
QPushButton[role="primary"]:pressed {
    background: #dbecee;
}

QPushButton#DangerButton {
    background: #f6eaea;
    color: #b85c5c;
    border: 1px solid #ebcaca;
}

QPushButton#DangerButton:hover {
    background: #f2dfdf;
    border: 1px solid #dfb5b5;
}

#SiteSidebar {
    background: #ffffff;
    border-right: 1px solid #d8e0e6;
}

#SiteSidebar QLabel#SidebarTitle {
    color: #2f7c85;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.2px;
    padding: 14px 16px 2px 16px;
}

#SiteSidebar QLabel#SidebarBrand {
    color: #23313a;
    font-size: 17px;
    font-weight: 700;
    padding: 0 16px 10px 16px;
}

#SiteSidebar QTreeWidget {
    margin: 0 10px 8px 10px;
}

QLabel#SectionTitle {
    color: #23313a;
    font-size: 14px;
    font-weight: 700;
    padding: 0;
}

QLabel#PanelSubtitle {
    color: #667784;
    font-size: 12px;
    padding-top: 1px;
}

QLabel#EmptyTitle {
    color: #23313a;
    font-size: 22px;
    font-weight: 700;
}

QLabel#EmptySubtitle {
    color: #667784;
    font-size: 14px;
}

QFrame#EmptyPane,
QFrame#PanelCard,
QFrame[panel="true"] {
    background: #ffffff;
    border: 1px solid #d8e0e6;
    border-radius: 8px;
}

QFrame#EmptyPane {
    border-style: dashed;
}

QTabWidget::pane {
    border: none;
    background: transparent;
    top: 0;
    padding: 0;
}

QTableWidget,
QTableView {
    border: none;
    background: transparent;
}

QHeaderView::section {
    background: #f8fafb;
    color: #667784;
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid #e9eef2;
    border-right: none;
    font-weight: 600;
    font-size: 12px;
}
"""


def _load_designer_stylesheet() -> str:
    if not _DESIGNER_STYLE.is_file():
        raise FileNotFoundError(f"Не найден стиль макета: {_DESIGNER_STYLE}")
    return _DESIGNER_STYLE.read_text(encoding="utf-8")


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")

    font = QFont("Segoe UI", 10)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)

    # Палитра из Designer/Палитра.css
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#f4f6f8"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#23313a"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#fbfcfd"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#23313a"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#23313a"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#e7f2f3"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#2f7c85"))
    palette.setColor(QPalette.ColorRole.Link, QColor("#2f7c85"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#667784"))
    app.setPalette(palette)

    app.setStyleSheet(_load_designer_stylesheet() + "\n" + _APP_EXTRAS)
