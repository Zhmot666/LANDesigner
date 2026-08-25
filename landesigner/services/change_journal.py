"""Журнал изменений проекта (actor / action / detail / время)."""

from __future__ import annotations

import os
from uuid import UUID

from landesigner.domain.entities import ChangeLogEntry, ProjectSnapshot, utcnow

# Совпадает с sync-настройками: одно «имя инженера» для блокировок и журнала.
SETTINGS_ORG = "LanDesigner"
SETTINGS_APP = "LanDesigner"
KEY_CLIENT_NAME = "sync/client_name"


def resolve_actor(explicit: str | None = None) -> str:
    if explicit is not None and explicit.strip():
        return explicit.strip()
    try:
        from PySide6.QtCore import QSettings

        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        name = str(settings.value(KEY_CLIENT_NAME, "") or "").strip()
        if name:
            return name
    except Exception:
        pass
    return (
        os.environ.get("USERNAME")
        or os.environ.get("USER")
        or os.environ.get("COMPUTERNAME")
        or "Неизвестный"
    )


def append_change(
    snapshot: ProjectSnapshot,
    action: str,
    *,
    detail: str = "",
    entity_kind: str = "",
    entity_id: UUID | None = None,
    actor: str | None = None,
) -> ChangeLogEntry:
    entry = ChangeLogEntry(
        created_at=utcnow(),
        actor=resolve_actor(actor),
        action=(action or "").strip() or "Изменение",
        detail=(detail or "").strip(),
        entity_kind=(entity_kind or "").strip(),
        entity_id=entity_id,
    )
    snapshot.change_log.append(entry)
    return entry


def entries_newest_first(snapshot: ProjectSnapshot) -> list[ChangeLogEntry]:
    return sorted(snapshot.change_log, key=lambda e: e.created_at, reverse=True)
