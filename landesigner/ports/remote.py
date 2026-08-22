from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class RemoteLockInfo:
    project_id: UUID
    holder_name: str
    holder_id: str
    acquired_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class RemoteProjectInfo:
    id: UUID
    name: str
    revision: int
    updated_at: datetime
    locked_by: str | None = None


@dataclass(frozen=True)
class RemoteProjectBlob:
    info: RemoteProjectInfo
    data: bytes


class RemoteConflictError(Exception):
    """Optimistic locking: локальная база revision не совпала с сервером."""

    def __init__(self, message: str, remote: RemoteProjectInfo) -> None:
        super().__init__(message)
        self.remote = remote


class RemoteLockConflictError(Exception):
    def __init__(self, message: str, lock: RemoteLockInfo) -> None:
        super().__init__(message)
        self.lock = lock


class RemoteAuthError(Exception):
    pass


class RemoteRepository(Protocol):
    """
    Порт общего репозитория: clone / push / pull / lock.
    Локальный .lanproj остаётся offline-кэшем.
    """

    def list_projects(self) -> list[RemoteProjectInfo]: ...

    def get_project(self, project_id: UUID) -> RemoteProjectBlob: ...

    def create_project(
        self,
        *,
        project_id: UUID,
        name: str,
        revision: int,
        data: bytes,
    ) -> RemoteProjectInfo: ...

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
    ) -> RemoteProjectInfo: ...

    def get_lock(self, project_id: UUID) -> RemoteLockInfo | None: ...

    def acquire_lock(
        self,
        project_id: UUID,
        *,
        client_id: str,
        client_name: str,
    ) -> RemoteLockInfo: ...

    def release_lock(self, project_id: UUID, *, client_id: str) -> bool: ...
