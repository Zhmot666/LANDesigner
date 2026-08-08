from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from landesigner.domain.entities import ProjectSnapshot
from landesigner.ports.remote import (
    RemoteConflictError,
    RemoteProjectBlob,
    RemoteProjectInfo,
    RemoteRepository,
)


@dataclass
class SyncState:
    """Привязка локального .lanproj к удалённому проекту (offline-кэш)."""

    server_url: str
    project_id: str
    remote_revision: int
    last_synced_at: str | None = None

    @property
    def project_uuid(self) -> UUID:
        return UUID(self.project_id)


def sync_sidecar_path(file_path: str | Path) -> Path:
    path = Path(file_path)
    return path.with_suffix(path.suffix + ".sync.json")


def load_sync_state(file_path: str | Path) -> SyncState | None:
    path = sync_sidecar_path(file_path)
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return SyncState(
        server_url=str(raw["server_url"]),
        project_id=str(raw["project_id"]),
        remote_revision=int(raw["remote_revision"]),
        last_synced_at=raw.get("last_synced_at"),
    )


def save_sync_state(file_path: str | Path, state: SyncState) -> None:
    path = sync_sidecar_path(file_path)
    path.write_text(
        json.dumps(asdict(state), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def clear_sync_state(file_path: str | Path) -> None:
    path = sync_sidecar_path(file_path)
    if path.is_file():
        path.unlink()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def status_label(
    *,
    file_path: str | None,
    snapshot: ProjectSnapshot | None,
    dirty: bool,
) -> str:
    if snapshot is None:
        return "Готово · локальный проект"
    base = f"{snapshot.meta.name} · rev {snapshot.meta.revision}"
    if file_path is None:
        return f"{base} · не сохранён"
    state = load_sync_state(file_path)
    if state is None:
        dirty_s = " · есть изменения" if dirty else ""
        return f"{base} · локальный файл{dirty_s}"
    remote = state.remote_revision
    local = snapshot.meta.revision
    if dirty:
        sync = f"sync base {remote} · несохранено"
    elif local > remote:
        sync = f"впереди сервера (local {local} / remote {remote})"
    elif local < remote:
        sync = f"отстаёт от сервера (local {local} / remote {remote})"
    else:
        sync = f"синхронизирован (rev {local})"
    return f"{base} · {sync}"


def clone_project(
    remote: RemoteRepository,
    *,
    project_id: UUID,
    dest_path: str | Path,
    server_url: str,
) -> tuple[RemoteProjectBlob, SyncState]:
    dest = Path(dest_path)
    blob = remote.get_project(project_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(blob.data)
    state = SyncState(
        server_url=server_url.rstrip("/"),
        project_id=str(blob.info.id),
        remote_revision=blob.info.revision,
        last_synced_at=_now_iso(),
    )
    save_sync_state(dest, state)
    return blob, state


def publish_project(
    remote: RemoteRepository,
    *,
    file_path: str | Path,
    snapshot: ProjectSnapshot,
    server_url: str,
) -> SyncState:
    """Первая публикация локального файла на сервер."""
    path = Path(file_path)
    data = path.read_bytes()
    info = remote.create_project(
        project_id=snapshot.meta.id,
        name=snapshot.meta.name,
        revision=snapshot.meta.revision,
        data=data,
    )
    state = SyncState(
        server_url=server_url.rstrip("/"),
        project_id=str(info.id),
        remote_revision=info.revision,
        last_synced_at=_now_iso(),
    )
    save_sync_state(path, state)
    snapshot.meta.origin = "remote"
    return state


def push_project(
    remote: RemoteRepository,
    *,
    file_path: str | Path,
    snapshot: ProjectSnapshot,
    force: bool = False,
) -> SyncState:
    path = Path(file_path)
    state = load_sync_state(path)
    if state is None:
        raise ValueError("Проект не привязан к серверу. Сначала опубликуйте или клонируйте.")
    data = path.read_bytes()
    try:
        info = remote.push_project(
            state.project_uuid,
            name=snapshot.meta.name,
            expected_revision=state.remote_revision,
            new_revision=snapshot.meta.revision,
            data=data,
            force=force,
        )
    except RemoteConflictError:
        raise
    state.remote_revision = info.revision
    state.last_synced_at = _now_iso()
    save_sync_state(path, state)
    snapshot.meta.origin = "remote"
    return state


def pull_project(
    remote: RemoteRepository,
    *,
    file_path: str | Path,
) -> tuple[RemoteProjectBlob, SyncState]:
    path = Path(file_path)
    state = load_sync_state(path)
    if state is None:
        raise ValueError("Проект не привязан к серверу. Сначала опубликуйте или клонируйте.")
    blob = remote.get_project(state.project_uuid)
    path.write_bytes(blob.data)
    state.remote_revision = blob.info.revision
    state.last_synced_at = _now_iso()
    save_sync_state(path, state)
    return blob, state


def list_remote_projects(remote: RemoteRepository) -> list[RemoteProjectInfo]:
    return remote.list_projects()
