from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest

from landesigner.adapters.local_sqlite.repository import LocalSqliteRepository
from landesigner.domain.entities import ProjectMeta, ProjectSnapshot, Site
from landesigner.ports.remote import (
    RemoteConflictError,
    RemoteLockConflictError,
    RemoteLockInfo,
    RemoteProjectBlob,
    RemoteProjectInfo,
)
from landesigner.services import sync as sync_svc
from landesigner.services.project import ProjectService
from server.store import ConflictError, ProjectStore


class StoreRemoteAdapter:
    """Тестовый RemoteRepository поверх ProjectStore (без HTTP)."""

    def __init__(self, store: ProjectStore) -> None:
        self._store = store

    def list_projects(self) -> list[RemoteProjectInfo]:
        items: list[RemoteProjectInfo] = []
        for p in self._store.list_projects():
            lock = self._store.get_lock(p.id)
            locked_by = lock.holder_name if lock and lock.is_active else None
            items.append(
                RemoteProjectInfo(
                    id=p.id,
                    name=p.name,
                    revision=p.revision,
                    updated_at=p.updated_at,
                    locked_by=locked_by,
                )
            )
        return items

    def get_project(self, project_id: UUID) -> RemoteProjectBlob:
        project = self._store.get(project_id)
        if project is None:
            raise KeyError(project_id)
        info = RemoteProjectInfo(
            id=project.id,
            name=project.name,
            revision=project.revision,
            updated_at=project.updated_at,
        )
        return RemoteProjectBlob(info=info, data=project.data)

    def create_project(
        self,
        *,
        project_id: UUID,
        name: str,
        revision: int,
        data: bytes,
    ) -> RemoteProjectInfo:
        project = self._store.create(
            project_id=project_id,
            name=name,
            revision=revision,
            data=data,
        )
        return RemoteProjectInfo(
            id=project.id,
            name=project.name,
            revision=project.revision,
            updated_at=project.updated_at,
        )

    def push_project(
        self,
        project_id: UUID,
        *,
        name: str,
        expected_revision: int,
        new_revision: int,
        data: bytes,
        force: bool = False,
        client_id: str = "",
        client_name: str = "",
    ) -> RemoteProjectInfo:
        if client_id.strip() and not force:
            lock = self._store.get_lock(project_id)
            if (
                lock is not None
                and lock.is_active
                and lock.holder_id != client_id.strip()
            ):
                raise RemoteLockConflictError(
                    "locked",
                    RemoteLockInfo(
                        project_id=project_id,
                        holder_name=lock.holder_name,
                        holder_id=lock.holder_id,
                        acquired_at=lock.acquired_at,
                        expires_at=lock.expires_at,
                    ),
                )
        try:
            project = self._store.push(
                project_id,
                name=name,
                expected_revision=expected_revision,
                new_revision=new_revision,
                data=data,
                force=force,
            )
        except ConflictError as exc:
            remote = RemoteProjectInfo(
                id=exc.remote.id,
                name=exc.remote.name,
                revision=exc.remote.revision,
                updated_at=exc.remote.updated_at,
            )
            raise RemoteConflictError("conflict", remote) from exc
        return RemoteProjectInfo(
            id=project.id,
            name=project.name,
            revision=project.revision,
            updated_at=project.updated_at,
        )

    def get_lock(self, project_id: UUID) -> RemoteLockInfo | None:
        lock = self._store.get_lock(project_id)
        if lock is None or not lock.is_active:
            return None
        return RemoteLockInfo(
            project_id=lock.project_id,
            holder_name=lock.holder_name,
            holder_id=lock.holder_id,
            acquired_at=lock.acquired_at,
            expires_at=lock.expires_at,
        )

    def acquire_lock(
        self,
        project_id: UUID,
        *,
        client_id: str,
        client_name: str,
    ) -> RemoteLockInfo:
        from server.locks import LockConflictError

        try:
            lock = self._store.acquire_lock(
                project_id,
                holder_name=client_name,
                holder_id=client_id,
            )
        except LockConflictError as exc:
            current = exc.current
            raise RemoteLockConflictError(
                "locked",
                RemoteLockInfo(
                    project_id=current.project_id,
                    holder_name=current.holder_name,
                    holder_id=current.holder_id,
                    acquired_at=current.acquired_at,
                    expires_at=current.expires_at,
                ),
            ) from exc
        return RemoteLockInfo(
            project_id=lock.project_id,
            holder_name=lock.holder_name,
            holder_id=lock.holder_id,
            acquired_at=lock.acquired_at,
            expires_at=lock.expires_at,
        )

    def release_lock(self, project_id: UUID, *, client_id: str) -> bool:
        return self._store.release_lock(project_id, client_id)


def _make_lanproj(tmp_path: Path, name: str = "SyncDemo") -> tuple[str, ProjectSnapshot]:
    path = str(tmp_path / f"{name}.lanproj")
    meta = ProjectMeta(name=name, revision=1, origin="local")
    site = Site(project_id=meta.id, name="S")
    snap = ProjectSnapshot(meta=meta, sites=[site])
    ProjectService(LocalSqliteRepository()).save_project(path, snap)
    return path, snap


def test_publish_push_pull_roundtrip(tmp_path: Path):
    store = ProjectStore(tmp_path / "server.db")
    remote = StoreRemoteAdapter(store)
    path, snap = _make_lanproj(tmp_path)

    state = sync_svc.publish_project(
        remote,
        file_path=path,
        snapshot=snap,
        server_url="memory://test",
    )
    assert state.remote_revision == 1
    assert sync_svc.load_sync_state(path) is not None

    snap.meta.name = "After edit"
    snap.meta.revision = 2
    ProjectService(LocalSqliteRepository()).save_project(path, snap)
    state = sync_svc.push_project(remote, file_path=path, snapshot=snap)
    assert state.remote_revision == 2

    listed = sync_svc.list_remote_projects(remote)
    assert len(listed) == 1
    assert listed[0].name == "After edit"

    # Simulate another local copy falling behind, then pull.
    other = tmp_path / "clone.lanproj"
    blob, clone_state = sync_svc.clone_project(
        remote,
        project_id=listed[0].id,
        dest_path=other,
        server_url="memory://test",
    )
    assert blob.info.revision == 2
    assert clone_state.remote_revision == 2
    opened = ProjectService(LocalSqliteRepository()).open_project(str(other))
    assert opened.meta.name == "After edit"


def test_push_conflict_and_force(tmp_path: Path):
    store = ProjectStore(tmp_path / "server.db")
    remote = StoreRemoteAdapter(store)
    path, snap = _make_lanproj(tmp_path, "Conflict")
    sync_svc.publish_project(remote, file_path=path, snapshot=snap, server_url="memory://t")

    # Remote advanced by another client.
    remote.push_project(
        snap.meta.id,
        name="Remote wins",
        expected_revision=1,
        new_revision=5,
        data=Path(path).read_bytes(),
    )

    snap.meta.revision = 2
    ProjectService(LocalSqliteRepository()).save_project(path, snap)
    with pytest.raises(RemoteConflictError) as exc:
        sync_svc.push_project(remote, file_path=path, snapshot=snap)
    assert exc.value.remote.revision == 5

    state = sync_svc.push_project(remote, file_path=path, snapshot=snap, force=True)
    assert state.remote_revision == 2


def test_status_label_local_and_synced(tmp_path: Path):
    path, snap = _make_lanproj(tmp_path, "Status")
    assert "локальный" in sync_svc.status_label(file_path=path, snapshot=snap, dirty=False)
    sync_svc.save_sync_state(
        path,
        sync_svc.SyncState(
            server_url="http://127.0.0.1:8765",
            project_id=str(snap.meta.id),
            remote_revision=1,
            last_synced_at=datetime.now(timezone.utc).isoformat(),
        ),
    )
    label = sync_svc.status_label(file_path=path, snapshot=snap, dirty=False)
    assert "синхронизирован" in label


def test_conflict_diff_compares_devices(tmp_path: Path):
    from landesigner.domain.enums import DeviceRole
    from landesigner.services import inventory as inv

    path, local = _make_lanproj(tmp_path, "DiffLocal")
    dtype = inv.add_device_type(
        local, vendor="X", model="Y", role=DeviceRole.SWITCH, port_count=1
    )
    inv.add_device(local, dtype.id, "sw-local")
    inv.add_device(local, dtype.id, "sw-both")
    ProjectService(LocalSqliteRepository()).save_project(path, local)

    remote_path = tmp_path / "DiffRemote.lanproj"
    remote = ProjectService(LocalSqliteRepository()).open_project(path)
    # remove local-only, rename shared, add remote-only
    both = next(d for d in remote.devices if d.hostname == "sw-both")
    local_only = next(d for d in remote.devices if d.hostname == "sw-local")
    inv.delete_device(remote, local_only.id)
    both.hostname = "sw-renamed"
    inv.add_device(remote, dtype.id, "sw-remote")
    remote.meta.revision = 9
    remote.meta.name = "DiffRemote"
    ProjectService(LocalSqliteRepository()).save_project(str(remote_path), remote)

    remote_loaded = sync_svc.open_lanproj_bytes(remote_path.read_bytes())
    text = sync_svc.compare_snapshots(local, remote_loaded).as_text()
    assert "rev 1" in text and "rev 9" in text
    assert "sw-local" in text
    assert "sw-remote" in text
    assert "sw-both" in text and "sw-renamed" in text


def test_project_lock_acquire_conflict_and_push(tmp_path: Path):
    store = ProjectStore(tmp_path / "locks.db")
    remote = StoreRemoteAdapter(store)
    path, snap = _make_lanproj(tmp_path, "LockDemo")
    sync_svc.publish_project(remote, file_path=path, snapshot=snap, server_url="http://t")

    lock_a = remote.acquire_lock(snap.meta.id, client_id="a", client_name="Alice")
    assert lock_a.holder_name == "Alice"

    with pytest.raises(RemoteLockConflictError) as exc:
        remote.acquire_lock(snap.meta.id, client_id="b", client_name="Bob")
    assert exc.value.lock.holder_name == "Alice"

    snap.meta.revision = 2
    ProjectService(LocalSqliteRepository()).save_project(path, snap)
    with pytest.raises(RemoteLockConflictError):
        remote.push_project(
            snap.meta.id,
            name=snap.meta.name,
            expected_revision=1,
            new_revision=2,
            data=Path(path).read_bytes(),
            client_id="b",
            client_name="Bob",
        )

    remote.release_lock(snap.meta.id, client_id="a")
    sync_svc.push_project(
        remote,
        file_path=path,
        snapshot=snap,
        client_id="b",
        client_name="Bob",
    )
    assert sync_svc.load_sync_state(path).remote_revision == 2


def test_pull_creates_backup_snapshot(tmp_path: Path):
    store = ProjectStore(tmp_path / "pull_backup.db")
    remote = StoreRemoteAdapter(store)
    path, snap = _make_lanproj(tmp_path, "PullBackup")
    sync_svc.publish_project(remote, file_path=path, snapshot=snap, server_url="http://t")

    snap.meta.name = "Remote name"
    snap.meta.revision = 2
    ProjectService(LocalSqliteRepository()).save_project(path, snap)
    sync_svc.push_project(remote, file_path=path, snapshot=snap, client_id="u1", client_name="U")

    local = ProjectService(LocalSqliteRepository()).open_project(path)
    local.meta.name = "Local edit"
    local.meta.revision = 3
    ProjectService(LocalSqliteRepository()).save_project(path, local)

    blob, _, backup = sync_svc.pull_project(remote, file_path=path, backup_before=True)
    assert blob.info.revision == 2
    assert backup is not None
    assert backup.is_file()
    restored = ProjectService(LocalSqliteRepository()).open_project(path)
    assert restored.meta.name == "Remote name"


def test_check_connection_health_and_auth(tmp_path: Path):
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from landesigner.adapters.remote.http_client import RemoteHttpClient
    from server.app import create_app

    store = ProjectStore(tmp_path / "auth_check.db")
    app = create_app(store, api_key="secret")
    client_http = TestClient(app)

    class _Patched(RemoteHttpClient):
        def _request_bytes(self, method, path, **kwargs):
            # TestClient path: use ASGI app instead of real HTTP.
            url = path
            headers = self._headers(kwargs.get("headers"))
            if method == "GET":
                resp = client_http.get(url, headers=headers)
            else:
                resp = client_http.request(method, url, headers=headers, content=kwargs.get("body"))
            if resp.status_code in (401, 403):
                from landesigner.ports.remote import RemoteAuthError

                raise RemoteAuthError(resp.text or "auth")
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
            return resp.content, {k: v for k, v in resp.headers.items()}

    ok_client = _Patched("http://test", api_token="secret", timeout_s=5)
    ok, msg = ok_client.check_connection()
    assert ok
    assert "доступен" in msg

    bad = _Patched("http://test", api_token="wrong", timeout_s=5)
    ok2, msg2 = bad.check_connection()
    assert not ok2
    assert "автор" in msg2.casefold() or "ключ" in msg2.casefold() or "auth" in msg2.casefold()


def test_move_floor_assets_command(tmp_path: Path):
    from PySide6.QtWidgets import QApplication

    from landesigner.domain.enums import DeviceRole
    from landesigner.services import floor_plan as fp
    from landesigner.services import inventory as inv
    from landesigner.ui.commands.floor_plan_commands import MoveFloorAssetsCommand

    _ = QApplication.instance() or QApplication([])
    meta = ProjectMeta(name="G")
    site = Site(project_id=meta.id, name="S")
    snap = ProjectSnapshot(meta=meta, sites=[site])
    building = inv.add_building(snap, "B")
    floor = inv.add_floor(snap, building.id, "F")
    room = inv.add_room(snap, floor.id, "R")
    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SWITCH, port_count=1
    )
    inv.add_device(snap, dtype.id, "a", room_id=room.id)
    inv.add_device(snap, dtype.id, "b", room_id=room.id)
    fp.ensure_assets_for_floor(snap, floor.id)
    a, b = snap.floor_plan_assets[0], snap.floor_plan_assets[1]
    old = {a.id: (a.x, a.y), b.id: (b.x, b.y)}
    changes = {
        a.id: (a.x, a.y, a.x + 10, a.y + 5),
        b.id: (b.x, b.y, b.x + 10, b.y + 5),
    }
    cmd = MoveFloorAssetsCommand(snap, changes)
    cmd.redo()
    assert (a.x, a.y) == (old[a.id][0] + 10, old[a.id][1] + 5)
    cmd.undo()
    assert (a.x, a.y) == old[a.id]
    assert (b.x, b.y) == old[b.id]


def test_fastapi_http_roundtrip(tmp_path: Path):
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from landesigner.adapters.remote.http_client import RemoteHttpClient
    from server.app import create_app

    store = ProjectStore(tmp_path / "http_server.db")
    app = create_app(store, api_key="secret")
    client_http = TestClient(app)

    # Bridge urllib client to TestClient via monkeypatched urlopen is heavy;
    # exercise API surface directly and adapter contract via StoreRemoteAdapter above.
    path, snap = _make_lanproj(tmp_path, "Http")
    data = Path(path).read_bytes()
    created = client_http.post(
        "/projects",
        content=data,
        headers={
            "X-API-Key": "secret",
            "X-Project-Id": str(snap.meta.id),
            "X-Project-Name": snap.meta.name,
            "X-Revision": "1",
        },
    )
    assert created.status_code == 201
    assert created.json()["revision"] == 1

    listed = client_http.get("/projects", headers={"X-API-Key": "secret"})
    assert listed.status_code == 200
    assert len(listed.json()["projects"]) == 1

    got = client_http.get(f"/projects/{snap.meta.id}", headers={"X-API-Key": "secret"})
    assert got.status_code == 200
    assert got.content == data
    assert got.headers["X-Revision"] == "1"

    conflict = client_http.put(
        f"/projects/{snap.meta.id}",
        content=data,
        headers={
            "X-API-Key": "secret",
            "X-Project-Name": "x",
            "X-Revision": "2",
            "If-Match": "0",
        },
    )
    assert conflict.status_code == 409

    ok = client_http.put(
        f"/projects/{snap.meta.id}",
        content=data,
        headers={
            "X-API-Key": "secret",
            "X-Project-Name": "x",
            "X-Revision": "2",
            "If-Match": "1",
        },
    )
    assert ok.status_code == 200
    assert ok.json()["revision"] == 2

    denied = client_http.get("/projects")
    assert denied.status_code == 401

    # Also verify RemoteHttpClient against TestClient ASGI transport via real loopback is optional;
    # ensure client module parses conflict payload shape.
    remote_payload = conflict.json()["remote"]
    assert UUID(remote_payload["id"]) == snap.meta.id
    _ = RemoteHttpClient("http://example.invalid", api_token="secret")
    _ = fastapi
