from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

_MAX_RECENT = 12
_SETTINGS_KEY = "files/recent_projects"


def _settings() -> QSettings:
    return QSettings("LanDesigner", "LanDesigner")


def normalize_project_path(path: str) -> str:
    return str(Path(path).expanduser().resolve())


def add_recent_project(path: str) -> None:
    """Добавить путь в начало списка последних открытых проектов."""
    if not path or not str(path).lower().endswith(".lanproj"):
        return
    resolved = normalize_project_path(path)
    if not Path(resolved).is_file():
        return

    raw = _settings().value(_SETTINGS_KEY, [])
    items = [str(x) for x in raw] if isinstance(raw, list) else []
    items = [p for p in items if p != resolved]
    items.insert(0, resolved)
    _settings().setValue(_SETTINGS_KEY, items[:_MAX_RECENT])


def list_recent_projects() -> list[str]:
    """Существующие файлы из списка последних (без пропавших с диска)."""
    raw = _settings().value(_SETTINGS_KEY, [])
    items = [str(x) for x in raw] if isinstance(raw, list) else []
    existing = [p for p in items if Path(p).is_file()]
    if existing != items:
        _settings().setValue(_SETTINGS_KEY, existing)
    return existing


def clear_recent_projects() -> None:
    _settings().remove(_SETTINGS_KEY)


def recent_projects_start_dir() -> str:
    """Начальная папка для диалога «Открыть» — каталог последнего проекта."""
    recent = list_recent_projects()
    if not recent:
        return ""
    return str(Path(recent[0]).parent)


def recent_menu_label(path: str, *, max_chars: int = 72) -> str:
    p = Path(path)
    name = p.name
    parent = str(p.parent)
    text = f"{name}  ({parent})"
    if len(text) <= max_chars:
        return text
    prefix = f"{name}  ("
    suffix = ")"
    budget = max_chars - len(prefix) - len(suffix)
    if budget < 8:
        return name if len(name) <= max_chars else name[: max_chars - 1] + "…"
    parent_short = parent if len(parent) <= budget else "…" + parent[-(budget - 1) :]
    return f"{prefix}{parent_short}{suffix}"
