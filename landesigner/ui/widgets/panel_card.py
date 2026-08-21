from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class PanelCard(QFrame):
    """Белая карточка как в Designer/Design.png: заголовок + действия справа + контент."""

    def __init__(
        self,
        title: str,
        parent: QWidget | None = None,
        *,
        subtitle: str = "",
    ) -> None:
        super().__init__(parent)
        self.setProperty("panel", True)
        self.setObjectName("PanelCard")

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self._title = QLabel(title, self)
        self._title.setObjectName("SectionTitle")
        titles.addWidget(self._title)
        self._subtitle = QLabel(subtitle, self)
        self._subtitle.setProperty("muted", True)
        self._subtitle.setObjectName("PanelSubtitle")
        self._subtitle.setVisible(bool(subtitle))
        titles.addWidget(self._subtitle)
        header.addLayout(titles, stretch=1)

        self._actions = QHBoxLayout()
        self._actions.setSpacing(4)
        self._actions.setContentsMargins(0, 0, 0, 0)
        header.addLayout(self._actions)
        root.addLayout(header)

        self._body = QVBoxLayout()
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.setSpacing(0)
        root.addLayout(self._body, stretch=1)

    def set_subtitle(self, text: str) -> None:
        self._subtitle.setText(text)
        self._subtitle.setVisible(bool(text))

    def add_action(self, button: QPushButton) -> QPushButton:
        self._actions.addWidget(button)
        return button

    def set_body_widget(self, widget: QWidget) -> None:
        while self._body.count():
            item = self._body.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self._body.addWidget(widget)
