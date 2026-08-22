from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from landesigner.adapters.local_sqlite.repository import LocalSqliteRepository
from landesigner.domain.entities import ProjectSnapshot
from landesigner.ports.remote import (
    RemoteConflictError,
    RemoteLockConflictError,
    RemoteLockInfo,
    RemoteProjectBlob,
    RemoteProjectInfo,
    RemoteRepository,
)
from landesigner.services.project import ProjectService
from landesigner.services.snapshots import create_snapshot


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


@dataclass(frozen=True)
class ConflictDiff:
    """Краткое сравнение локального и серверного снимков для UI конфликта."""

    lines: tuple[str, ...]

    def as_text(self) -> str:
        return "\n".join(self.lines)


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
    lock_holder: str | None = None,
    lock_is_mine: bool = False,
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
    if lock_holder:
        if lock_is_mine:
            sync += f" · блокировка: вы ({lock_holder})"
        else:
            sync += f" · редактирует: {lock_holder}"
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
    client_id: str = "",
    client_name: str = "",
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
            client_id=client_id,
            client_name=client_name,
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
    backup_before: bool = True,
) -> tuple[RemoteProjectBlob, SyncState, Path | None]:
    path = Path(file_path)
    state = load_sync_state(path)
    if state is None:
        raise ValueError("Проект не привязан к серверу. Сначала опубликуйте или клонируйте.")
    backup_path: Path | None = None
    if backup_before and path.is_file():
        backup_path = create_snapshot(path, label="before_pull")
    blob = remote.get_project(state.project_uuid)
    path.write_bytes(blob.data)
    state.remote_revision = blob.info.revision
    state.last_synced_at = _now_iso()
    save_sync_state(path, state)
    return blob, state, backup_path


def acquire_project_lock(
    remote: RemoteRepository,
    *,
    file_path: str | Path,
    client_id: str,
    client_name: str,
) -> RemoteLockInfo:
    state = load_sync_state(file_path)
    if state is None:
        raise ValueError("Проект не привязан к серверу.")
    return remote.acquire_lock(
        state.project_uuid,
        client_id=client_id,
        client_name=client_name,
    )


def release_project_lock(
    remote: RemoteRepository,
    *,
    file_path: str | Path,
    client_id: str,
) -> bool:
    state = load_sync_state(file_path)
    if state is None:
        return False
    return remote.release_lock(state.project_uuid, client_id=client_id)


def fetch_project_lock(
    remote: RemoteRepository,
    *,
    file_path: str | Path,
) -> RemoteLockInfo | None:
    state = load_sync_state(file_path)
    if state is None:
        return None
    return remote.get_lock(state.project_uuid)


def list_remote_projects(remote: RemoteRepository) -> list[RemoteProjectInfo]:
    return remote.list_projects()


def open_lanproj_bytes(data: bytes) -> ProjectSnapshot:
    """Открыть .lanproj из blob’а (для сравнения при конфликте)."""
    with tempfile.TemporaryDirectory(
        prefix="ld_sync_", ignore_cleanup_errors=True
    ) as tmp:
        path = Path(tmp) / "project.lanproj"
        path.write_bytes(data)
        return ProjectService(LocalSqliteRepository()).open_project(str(path))


def _counts(snapshot: ProjectSnapshot) -> dict[str, int]:
    return {
        "devices": len(snapshot.devices),
        "cables": len(snapshot.cables),
        "vlans": len(snapshot.vlans),
        "ips": len(snapshot.ips),
        "racks": len(snapshot.racks),
        "routes": len(snapshot.floor_plan_routes),
    }


def _fmt_counts(counts: dict[str, int]) -> str:
    return (
        f"устройств {counts['devices']} · кабелей {counts['cables']} · "
        f"VLAN {counts['vlans']} · IP {counts['ips']} · шкафов {counts['racks']}"
    )


def compare_snapshots(
    local: ProjectSnapshot,
    remote: ProjectSnapshot,
) -> ConflictDiff:
    """Сводка различий local vs remote (мета, счётчики, hostname по id)."""
    lines: list[str] = []
    local_c = _counts(local)
    remote_c = _counts(remote)
    lines.append(
        f"Локально: «{local.meta.name}» rev {local.meta.revision} · {_fmt_counts(local_c)}"
    )
    lines.append(
        f"Сервер:   «{remote.meta.name}» rev {remote.meta.revision} · {_fmt_counts(remote_c)}"
    )
    if local.meta.name != remote.meta.name:
        lines.append(f"Имя проекта: «{local.meta.name}» ↔ «{remote.meta.name}»")
    if local.meta.revision != remote.meta.revision:
        lines.append(
            f"Revision: local {local.meta.revision} / remote {remote.meta.revision}"
        )

    for key, label in (
        ("devices", "устройства"),
        ("cables", "кабели"),
        ("vlans", "VLAN"),
        ("ips", "IP"),
        ("racks", "шкафы"),
        ("routes", "трассы"),
    ):
        if local_c[key] != remote_c[key]:
            lines.append(f"{label}: local {local_c[key]} / remote {remote_c[key]}")

    local_dev = {d.id: d for d in local.devices}
    remote_dev = {d.id: d for d in remote.devices}
    only_local = sorted(
        (d for did, d in local_dev.items() if did not in remote_dev),
        key=lambda d: (d.hostname or "").casefold(),
    )
    only_remote = sorted(
        (d for did, d in remote_dev.items() if did not in local_dev),
        key=lambda d: (d.hostname or "").casefold(),
    )
    renamed: list[str] = []
    for did, loc in local_dev.items():
        rem = remote_dev.get(did)
        if rem is None:
            continue
        if (loc.hostname or "") != (rem.hostname or ""):
            renamed.append(f"«{loc.hostname or '—'}» ↔ «{rem.hostname or '—'}»")

    if only_local or only_remote or renamed:
        lines.append("")
        lines.append("Устройства:")
        for d in only_local[:12]:
            lines.append(f"  − только локально: {d.hostname or '—'}")
        if len(only_local) > 12:
            lines.append(f"  − … ещё {len(only_local) - 12}")
        for d in only_remote[:12]:
            lines.append(f"  + только на сервере: {d.hostname or '—'}")
        if len(only_remote) > 12:
            lines.append(f"  + … ещё {len(only_remote) - 12}")
        for item in renamed[:12]:
            lines.append(f"  ~ hostname: {item}")
        if len(renamed) > 12:
            lines.append(f"  ~ … ещё {len(renamed) - 12}")

    local_cables = {c.id: c for c in local.cables}
    remote_cables = {c.id: c for c in remote.cables}
    cable_only_local = [
        c for cid, c in local_cables.items() if cid not in remote_cables
    ]
    cable_only_remote = [
        c for cid, c in remote_cables.items() if cid not in local_cables
    ]
    cable_changed: list[str] = []
    for cid, loc in local_cables.items():
        rem = remote_cables.get(cid)
        if rem is None:
            continue
        if (loc.label or "") != (rem.label or "") or loc.length_m != rem.length_m:
            cable_changed.append(
                f"«{loc.label or '—'}» ↔ «{rem.label or '—'}» "
                f"({loc.length_m or '—'} / {rem.length_m or '—'} м)"
            )
    if cable_only_local or cable_only_remote or cable_changed:
        lines.append("")
        lines.append("Кабели:")
        for cable in sorted(cable_only_local, key=lambda c: (c.label or "").casefold())[:8]:
            lines.append(f"  − только локально: {cable.label or '—'}")
        for cable in sorted(cable_only_remote, key=lambda c: (c.label or "").casefold())[:8]:
            lines.append(f"  + только на сервере: {cable.label or '—'}")
        for item in cable_changed[:8]:
            lines.append(f"  ~ изменён: {item}")

    local_vlans = {v.id: v for v in local.vlans}
    remote_vlans = {v.id: v for v in remote.vlans}
    vlan_only_local = [v for vid, v in local_vlans.items() if vid not in remote_vlans]
    vlan_only_remote = [v for vid, v in remote_vlans.items() if vid not in local_vlans]
    if vlan_only_local or vlan_only_remote:
        lines.append("")
        lines.append("VLAN:")
        for vlan in sorted(vlan_only_local, key=lambda v: v.vlan_id)[:8]:
            lines.append(f"  − только локально: {vlan.vlan_id} {vlan.name}")
        for vlan in sorted(vlan_only_remote, key=lambda v: v.vlan_id)[:8]:
            lines.append(f"  + только на сервере: {vlan.vlan_id} {vlan.name}")

    if len(lines) <= 2:
        lines.append("")
        lines.append("Содержимое похоже; отличаются в основном revision/мета.")
    return ConflictDiff(lines=tuple(lines))


def conflict_diff_for_blob(
    local: ProjectSnapshot,
    remote_data: bytes,
) -> ConflictDiff:
    remote = open_lanproj_bytes(remote_data)
    return compare_snapshots(local, remote)
