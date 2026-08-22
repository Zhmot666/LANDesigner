from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from uuid import UUID


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


@dataclass(frozen=True)
class StoredProject:
    id: UUID
    name: str
    revision: int
    updated_at: datetime
    data: bytes


class ConflictError(Exception):
    def __init__(self, remote: StoredProject) -> None:
        super().__init__("revision conflict")
        self.remote = remote


class ProjectStoreBackend(Protocol):
    def list_projects(self) -> list[StoredProject]: ...

    def get(self, project_id: UUID) -> StoredProject | None: ...

    def create(
        self,
        *,
        project_id: UUID,
        name: str,
        revision: int,
        data: bytes,
    ) -> StoredProject: ...

    def push(
        self,
        project_id: UUID,
        *,
        name: str,
        expected_revision: int,
        new_revision: int,
        data: bytes,
        force: bool = False,
    ) -> StoredProject: ...


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    revision INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    data BLOB NOT NULL
)
"""

_PG_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    revision INTEGER NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    data BYTEA NOT NULL
)
"""


class SqliteProjectStore:
    """Локальное серверное хранилище (SQLite, blob .lanproj + meta)."""

    def __init__(self, db_path: str | Path) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA_SQL)
            conn.commit()

    def list_projects(self) -> list[StoredProject]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name, revision, updated_at, data FROM projects ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [self._row_to_project(row) for row in rows]

    def get(self, project_id: UUID) -> StoredProject | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, name, revision, updated_at, data FROM projects WHERE id = ?",
                (str(project_id),),
            ).fetchone()
        return None if row is None else self._row_to_project(row)

    def create(
        self,
        *,
        project_id: UUID,
        name: str,
        revision: int,
        data: bytes,
    ) -> StoredProject:
        existing = self.get(project_id)
        if existing is not None:
            raise ValueError(f"Проект уже существует: {project_id}")
        now = _utcnow()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO projects(id, name, revision, updated_at, data)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(project_id), name, revision, now.isoformat(), data),
            )
            conn.commit()
        return StoredProject(
            id=project_id,
            name=name,
            revision=revision,
            updated_at=now,
            data=data,
        )

    def push(
        self,
        project_id: UUID,
        *,
        name: str,
        expected_revision: int,
        new_revision: int,
        data: bytes,
        force: bool = False,
    ) -> StoredProject:
        current = self.get(project_id)
        if current is None:
            raise KeyError(project_id)
        if not force and current.revision != expected_revision:
            raise ConflictError(current)
        now = _utcnow()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE projects
                SET name = ?, revision = ?, updated_at = ?, data = ?
                WHERE id = ?
                """,
                (name, new_revision, now.isoformat(), data, str(project_id)),
            )
            conn.commit()
        return StoredProject(
            id=project_id,
            name=name,
            revision=new_revision,
            updated_at=now,
            data=data,
        )

    @staticmethod
    def _row_to_project(row: sqlite3.Row) -> StoredProject:
        return StoredProject(
            id=UUID(str(row["id"])),
            name=str(row["name"]),
            revision=int(row["revision"]),
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
            data=bytes(row["data"]),
        )


class PostgresProjectStore:
    """Серверное хранилище PostgreSQL (blob .lanproj + meta)."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn.strip()
        if not self._dsn:
            raise ValueError("Пустой DATABASE_URL")
        self._init_db()

    def _connect(self):
        import psycopg

        return psycopg.connect(self._dsn)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(_PG_SCHEMA_SQL)
            conn.commit()

    def list_projects(self) -> list[StoredProject]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name, revision, updated_at, data FROM projects ORDER BY name"
            ).fetchall()
        return [self._row_to_project(row) for row in rows]

    def get(self, project_id: UUID) -> StoredProject | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, name, revision, updated_at, data FROM projects WHERE id = %s",
                (project_id,),
            ).fetchone()
        return None if row is None else self._row_to_project(row)

    def create(
        self,
        *,
        project_id: UUID,
        name: str,
        revision: int,
        data: bytes,
    ) -> StoredProject:
        existing = self.get(project_id)
        if existing is not None:
            raise ValueError(f"Проект уже существует: {project_id}")
        now = _utcnow()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO projects(id, name, revision, updated_at, data)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (project_id, name, revision, now, data),
            )
            conn.commit()
        return StoredProject(
            id=project_id,
            name=name,
            revision=revision,
            updated_at=now,
            data=data,
        )

    def push(
        self,
        project_id: UUID,
        *,
        name: str,
        expected_revision: int,
        new_revision: int,
        data: bytes,
        force: bool = False,
    ) -> StoredProject:
        current = self.get(project_id)
        if current is None:
            raise KeyError(project_id)
        if not force and current.revision != expected_revision:
            raise ConflictError(current)
        now = _utcnow()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE projects
                SET name = %s, revision = %s, updated_at = %s, data = %s
                WHERE id = %s
                """,
                (name, new_revision, now, data, project_id),
            )
            conn.commit()
        return StoredProject(
            id=project_id,
            name=name,
            revision=new_revision,
            updated_at=now,
            data=data,
        )

    @staticmethod
    def _row_to_project(row: tuple) -> StoredProject:
        project_id, name, revision, updated_at, data = row
        if isinstance(updated_at, datetime) and updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        return StoredProject(
            id=project_id if isinstance(project_id, UUID) else UUID(str(project_id)),
            name=str(name),
            revision=int(revision),
            updated_at=updated_at,
            data=bytes(data),
        )


def create_project_store(
    *,
    db_path: str | Path | None = None,
    database_url: str | None = None,
) -> ProjectStoreBackend:
    """
    SQLite по пути (LANDESIGNER_SERVER_DB) или PostgreSQL (LANDESIGNER_DATABASE_URL).

    Приоритет: явный database_url → env LANDESIGNER_DATABASE_URL → SQLite.
    """
    url = (database_url or os.environ.get("LANDESIGNER_DATABASE_URL", "")).strip()
    if url:
        return PostgresProjectStore(url)
    path = db_path if db_path is not None else os.environ.get(
        "LANDESIGNER_SERVER_DB", "data/landesigner_server.db"
    )
    return SqliteProjectStore(path)


# Обратная совместимость: старый импорт ProjectStore(path) = SQLite.
ProjectStore = SqliteProjectStore  # type: ignore[misc,assignment]
