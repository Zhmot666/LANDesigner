from __future__ import annotations

import sys

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_recent_projects_store_and_clean(qapp, tmp_path):
    from landesigner.ui.recent_projects import (
        _SETTINGS_KEY,
        add_recent_project,
        clear_recent_projects,
        list_recent_projects,
        recent_menu_label,
        recent_projects_start_dir,
    )

    settings = QSettings("LanDesigner", "LanDesigner")
    settings.remove(_SETTINGS_KEY)

    first = tmp_path / "office.lanproj"
    second = tmp_path / "lab.lanproj"
    first.write_text("a", encoding="utf-8")
    second.write_text("b", encoding="utf-8")

    add_recent_project(str(first))
    add_recent_project(str(second))
    add_recent_project(str(first))

    recent = list_recent_projects()
    assert recent[0] == str(first.resolve())
    assert recent[1] == str(second.resolve())
    assert "office.lanproj" in recent_menu_label(str(first))
    assert recent_projects_start_dir() == str(first.parent)

    missing = tmp_path / "gone.lanproj"
    settings.setValue(_SETTINGS_KEY, [str(first.resolve()), str(missing)])
    recent = list_recent_projects()
    assert recent == [str(first.resolve())]

    clear_recent_projects()
    assert list_recent_projects() == []
