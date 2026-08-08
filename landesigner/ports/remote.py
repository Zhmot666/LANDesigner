from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class RemoteProjectInfo:
    id: UUID
    name: str
    revision: int
    updated_at: datetime


@dataclass(frozen=True)
class RemoteProjectBlob:
    info: RemoteProjectInfo
    data: bytes


class RemoteConflictError(Exception):
    """Optimistic locking: локальная база revision не совпала с сервером."""

    def __init__(self, message: str, remote: RemoteProjectInfo) -> None:
        super().__init__(message)
        self.remote = remote


class RemoteAuthError(Exception):
    pass


class RemoteRepository(Protocol):
    """
    Порт общего репозитория: clone / push / pull.
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
    ) -> RemoteProjectInfo: ...
