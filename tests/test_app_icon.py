from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from landesigner.ui.icons import app_icon


def test_app_icon_renders():
    app = QApplication.instance() or QApplication(sys.argv)
    icon = app_icon()
    assert not icon.isNull()
    pm = icon.pixmap(32, 32)
    assert not pm.isNull()
    assert pm.width() >= 32
