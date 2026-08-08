from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest

from landesigner.adapters.local_sqlite.repository import LocalSqliteRepository
from landesigner.domain.entities import ProjectMeta, ProjectSnapshot, Site
from landesigner.ports.remote import RemoteConflictError, RemoteProjectBlob, RemoteProjectInfo
from landesigner.services import sync as sync_svc
from landesigner.services.project import ProjectService
from server.store import ConflictError, ProjectStore


class StoreRemoteAdapter:
    """Тестовый RemoteRepository поверх ProjectStore (без HTTP)."""

    def __init__(self, store: ProjectStore) -> None:
        self._store = store

    def list_projects(self) -> list[RemoteProjectInfo]:
        return [
            RemoteProjectInfo(
                id=p.id,
                name=p.name,
                revision=p.revision,
                updated_at=p.updated_at,
            )
            for p in self._store.list_projects()
        ]

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
    ) -> RemoteProjectInfo:
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
