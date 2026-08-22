from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest

from server.store import (
    ConflictError,
    PostgresProjectStore,
    ProjectStoreBackend,
    SqliteProjectStore,
    create_project_store,
)


def _sample_data() -> bytes:
    return b"%LANPROJ-test-bytes%"


@pytest.fixture(params=["sqlite"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> ProjectStoreBackend:
    if request.param == "sqlite":
        return SqliteProjectStore(tmp_path / "store.db")
    url = os.environ.get("LANDESIGNER_TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("LANDESIGNER_TEST_DATABASE_URL не задан")
    pg = PostgresProjectStore(url)
    with pg._connect() as conn:
        conn.execute("TRUNCATE projects")
        conn.commit()
    request.addfinalizer(lambda: _truncate_pg(pg))
    return pg


def _truncate_pg(pg: PostgresProjectStore) -> None:
    with pg._connect() as conn:
        conn.execute("TRUNCATE projects")
        conn.commit()


def test_create_project_store_prefers_database_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from unittest.mock import patch

    monkeypatch.delenv("LANDESIGNER_DATABASE_URL", raising=False)
    sqlite = create_project_store(db_path=tmp_path / "a.db")
    assert isinstance(sqlite, SqliteProjectStore)

    monkeypatch.setenv("LANDESIGNER_DATABASE_URL", "postgresql://example/db")
    pytest.importorskip("psycopg")
    with patch.object(PostgresProjectStore, "_init_db"):
        pg = create_project_store(db_path=tmp_path / "ignored.db")
    assert isinstance(pg, PostgresProjectStore)


def test_store_create_get_push_conflict(store: ProjectStoreBackend):
    project_id = uuid4()
    data = _sample_data()

    created = store.create(
        project_id=project_id,
        name="Alpha",
        revision=1,
        data=data,
    )
    assert created.revision == 1
    assert created.data == data

    loaded = store.get(project_id)
    assert loaded is not None
    assert loaded.name == "Alpha"

    updated = store.push(
        project_id,
        name="Alpha-2",
        expected_revision=1,
        new_revision=2,
        data=data + b"-v2",
    )
    assert updated.revision == 2
    assert updated.name == "Alpha-2"

    with pytest.raises(ConflictError) as exc:
        store.push(
            project_id,
            name="X",
            expected_revision=1,
            new_revision=3,
            data=b"x",
        )
    assert exc.value.remote.revision == 2

    forced = store.push(
        project_id,
        name="Forced",
        expected_revision=0,
        new_revision=4,
        data=b"forced",
        force=True,
    )
    assert forced.revision == 4
    assert forced.data == b"forced"


def test_store_list_and_duplicate_create(store: ProjectStoreBackend):
    a_id, b_id = uuid4(), uuid4()
    store.create(project_id=a_id, name="Bravo", revision=1, data=b"a")
    store.create(project_id=b_id, name="Alpha", revision=1, data=b"b")

    names = [p.name for p in store.list_projects()]
    assert names == ["Alpha", "Bravo"]

    with pytest.raises(ValueError, match="уже существует"):
        store.create(project_id=a_id, name="Dup", revision=1, data=b"x")

    assert store.get(uuid4()) is None

    with pytest.raises(KeyError):
        store.push(
            uuid4(),
            name="n",
            expected_revision=1,
            new_revision=2,
            data=b"x",
        )


@pytest.mark.postgres
def test_postgres_store_roundtrip():
    url = os.environ.get("LANDESIGNER_TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("LANDESIGNER_TEST_DATABASE_URL не задан")
    store = PostgresProjectStore(url)
    _truncate_pg(store)
    project_id = uuid4()
    store.create(project_id=project_id, name="PG", revision=1, data=b"pg")
    assert store.get(project_id) is not None
    _truncate_pg(store)
