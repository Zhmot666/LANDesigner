from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
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


class ProjectStore:
    """
    Серверное хранилище проектов (.lanproj bytes + meta).

    По умолчанию SQLite (удобно для локального запуска).
    Тот же контракт можно реализовать поверх PostgreSQL позже.
    """

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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    data BLOB NOT NULL
                )
                """
            )
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


class ConflictError(Exception):
    def __init__(self, remote: StoredProject) -> None:
        super().__init__("revision conflict")
        self.remote = remote
