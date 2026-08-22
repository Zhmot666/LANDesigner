from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

DEFAULT_LOCK_TTL_SEC = 7200


@dataclass(frozen=True)
class ProjectLock:
    project_id: UUID
    holder_name: str
    holder_id: str
    acquired_at: datetime
    expires_at: datetime

    @property
    def is_active(self) -> bool:
        return self.expires_at > datetime.now(timezone.utc)


class LockConflictError(Exception):
    def __init__(self, current: ProjectLock) -> None:
        super().__init__("project locked")
        self.current = current


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _resolve_acquire(
    current: ProjectLock | None,
    *,
    project_id: UUID,
    holder_name: str,
    holder_id: str,
    ttl_sec: int,
    now: datetime | None = None,
) -> ProjectLock:
    now = now or _utcnow()
    if (
        current is not None
        and current.expires_at > now
        and current.holder_id != holder_id
    ):
        raise LockConflictError(current)
    expires = now + timedelta(seconds=max(60, int(ttl_sec)))
    return ProjectLock(
        project_id=project_id,
        holder_name=holder_name.strip() or "—",
        holder_id=holder_id.strip(),
        acquired_at=now,
        expires_at=expires,
    )


LOCK_SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS project_locks (
    project_id TEXT PRIMARY KEY,
    holder_name TEXT NOT NULL,
    holder_id TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
)
"""

LOCK_SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS project_locks (
    project_id UUID PRIMARY KEY,
    holder_name TEXT NOT NULL,
    holder_id TEXT NOT NULL,
    acquired_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
)
"""


def sqlite_purge_expired(conn: sqlite3.Connection, now: datetime | None = None) -> None:
    now = now or _utcnow()
    conn.execute(
        "DELETE FROM project_locks WHERE expires_at <= ?",
        (now.isoformat(),),
    )


def sqlite_get_lock(conn: sqlite3.Connection, project_id: UUID) -> ProjectLock | None:
    sqlite_purge_expired(conn)
    row = conn.execute(
        """
        SELECT project_id, holder_name, holder_id, acquired_at, expires_at
        FROM project_locks WHERE project_id = ?
        """,
        (str(project_id),),
    ).fetchone()
    if row is None:
        return None
    return ProjectLock(
        project_id=UUID(str(row["project_id"])),
        holder_name=str(row["holder_name"]),
        holder_id=str(row["holder_id"]),
        acquired_at=datetime.fromisoformat(str(row["acquired_at"])),
        expires_at=datetime.fromisoformat(str(row["expires_at"])),
    )


def sqlite_acquire_lock(
    conn: sqlite3.Connection,
    project_id: UUID,
    *,
    holder_name: str,
    holder_id: str,
    ttl_sec: int = DEFAULT_LOCK_TTL_SEC,
) -> ProjectLock:
    sqlite_purge_expired(conn)
    current = sqlite_get_lock(conn, project_id)
    lock = _resolve_acquire(
        current,
        project_id=project_id,
        holder_name=holder_name,
        holder_id=holder_id,
        ttl_sec=ttl_sec,
    )
    conn.execute(
        """
        INSERT INTO project_locks(project_id, holder_name, holder_id, acquired_at, expires_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(project_id) DO UPDATE SET
            holder_name = excluded.holder_name,
            holder_id = excluded.holder_id,
            acquired_at = excluded.acquired_at,
            expires_at = excluded.expires_at
        """,
        (
            str(project_id),
            lock.holder_name,
            lock.holder_id,
            lock.acquired_at.isoformat(),
            lock.expires_at.isoformat(),
        ),
    )
    return lock


def sqlite_release_lock(conn: sqlite3.Connection, project_id: UUID, holder_id: str) -> bool:
    sqlite_purge_expired(conn)
    cur = conn.execute(
        "DELETE FROM project_locks WHERE project_id = ? AND holder_id = ?",
        (str(project_id), holder_id.strip()),
    )
    return cur.rowcount > 0


def pg_purge_expired(conn, now: datetime | None = None) -> None:
    now = now or _utcnow()
    conn.execute("DELETE FROM project_locks WHERE expires_at <= %s", (now,))


def pg_get_lock(conn, project_id: UUID) -> ProjectLock | None:
    pg_purge_expired(conn)
    row = conn.execute(
        """
        SELECT project_id, holder_name, holder_id, acquired_at, expires_at
        FROM project_locks WHERE project_id = %s
        """,
        (project_id,),
    ).fetchone()
    if row is None:
        return None
    pid, holder_name, holder_id, acquired_at, expires_at = row
    if isinstance(acquired_at, datetime) and acquired_at.tzinfo is None:
        acquired_at = acquired_at.replace(tzinfo=timezone.utc)
    if isinstance(expires_at, datetime) and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return ProjectLock(
        project_id=pid if isinstance(pid, UUID) else UUID(str(pid)),
        holder_name=str(holder_name),
        holder_id=str(holder_id),
        acquired_at=acquired_at,
        expires_at=expires_at,
    )


def pg_acquire_lock(
    conn,
    project_id: UUID,
    *,
    holder_name: str,
    holder_id: str,
    ttl_sec: int = DEFAULT_LOCK_TTL_SEC,
) -> ProjectLock:
    pg_purge_expired(conn)
    current = pg_get_lock(conn, project_id)
    lock = _resolve_acquire(
        current,
        project_id=project_id,
        holder_name=holder_name,
        holder_id=holder_id,
        ttl_sec=ttl_sec,
    )
    conn.execute(
        """
        INSERT INTO project_locks(project_id, holder_name, holder_id, acquired_at, expires_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (project_id) DO UPDATE SET
            holder_name = EXCLUDED.holder_name,
            holder_id = EXCLUDED.holder_id,
            acquired_at = EXCLUDED.acquired_at,
            expires_at = EXCLUDED.expires_at
        """,
        (
            project_id,
            lock.holder_name,
            lock.holder_id,
            lock.acquired_at,
            lock.expires_at,
        ),
    )
    return lock


def pg_release_lock(conn, project_id: UUID, holder_id: str) -> bool:
    pg_purge_expired(conn)
    cur = conn.execute(
        "DELETE FROM project_locks WHERE project_id = %s AND holder_id = %s",
        (project_id, holder_id.strip()),
    )
    return cur.rowcount > 0
