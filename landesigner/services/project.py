from __future__ import annotations

from landesigner.domain.entities import ProjectMeta, ProjectSnapshot
from landesigner.ports.repository import ProjectRepository


class ProjectService:
    def __init__(self, repo: ProjectRepository) -> None:
        self._repo = repo

    def new_project(self, file_path: str, meta: ProjectMeta) -> ProjectSnapshot:
        self._repo.create_new_project(file_path=file_path, meta=meta)
        return self._repo.load_project(file_path=file_path)

    def open_project(self, file_path: str) -> ProjectSnapshot:
        return self._repo.load_project(file_path=file_path)

    def save_project(self, file_path: str, snapshot: ProjectSnapshot) -> None:
        self._repo.save_project(file_path=file_path, snapshot=snapshot)

