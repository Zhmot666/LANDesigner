"""Загрузка текста истории изменений приложения (CHANGELOG.md)."""

from __future__ import annotations

from importlib import metadata
from pathlib import Path


def app_version() -> str:
    try:
        return metadata.version("lan-designer")
    except metadata.PackageNotFoundError:
        return "0.1.0"


def changelog_path() -> Path | None:
    """Путь к CHANGELOG.md: корень репозитория или пакетный resources/."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "CHANGELOG.md",  # …/landesigner/services → repo root
        here.parents[1] / "resources" / "CHANGELOG.md",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def load_changelog_markdown() -> str:
    path = changelog_path()
    if path is None:
        return (
            f"# История изменений\n\n"
            f"Файл CHANGELOG.md не найден.\n\n"
            f"Версия приложения: **{app_version()}**.\n"
        )
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return f"# История изменений\n\n(пусто)\n\nВерсия: **{app_version()}**.\n"
    return text
