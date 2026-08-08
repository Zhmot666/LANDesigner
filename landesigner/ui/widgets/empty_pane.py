from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class EmptyPane(QFrame):
    """Плейсхолдер для вкладок, которые ещё не реализованы."""

    def __init__(
        self,
        title: str,
        subtitle: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("EmptyPane")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)

        title_lbl = QLabel(title, self)
        title_lbl.setObjectName("EmptyTitle")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sub_lbl = QLabel(subtitle, self)
        sub_lbl.setObjectName("EmptySubtitle")
        sub_lbl.setProperty("muted", True)
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_lbl.setWordWrap(True)

        layout.addStretch(1)
        layout.addWidget(title_lbl)
        layout.addWidget(sub_lbl)
        layout.addStretch(1)
