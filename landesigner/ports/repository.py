from __future__ import annotations

from typing import Protocol

from landesigner.domain.entities import ProjectMeta, ProjectSnapshot


class ProjectRepository(Protocol):
    """
    Порт хранилища. UI и domain должны зависеть от него, а не от конкретной БД.
    """

    def create_new_project(self, file_path: str, meta: ProjectMeta) -> None: ...

    def load_project(self, file_path: str) -> ProjectSnapshot: ...

    def save_project(self, file_path: str, snapshot: ProjectSnapshot) -> None: ...

