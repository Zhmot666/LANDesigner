from __future__ import annotations

from landesigner.services import app_changelog as cl


def test_load_changelog_has_version_section():
    text = cl.load_changelog_markdown()
    assert "Changelog" in text or "История" in text
    assert "0.1.0" in text or "Unreleased" in text
    assert cl.changelog_path() is not None
    assert cl.app_version()


def test_changelog_path_prefers_readable_file():
    path = cl.changelog_path()
    assert path is not None
    assert path.is_file()
    assert path.name == "CHANGELOG.md"
