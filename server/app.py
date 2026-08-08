from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from server.store import ConflictError, ProjectStore

DEFAULT_DB = Path(os.environ.get("LANDESIGNER_SERVER_DB", "data/landesigner_server.db"))


def create_app(store: ProjectStore | None = None, *, api_key: str | None = None) -> FastAPI:
    app = FastAPI(title="LanDesigner Sync API", version="0.1.0")
    app.state.store = store or ProjectStore(DEFAULT_DB)
    expected_key = api_key if api_key is not None else os.environ.get("LANDESIGNER_API_KEY", "")

    def require_auth(
        authorization: str | None = Header(default=None),
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ) -> None:
        if not expected_key:
            return
        token = None
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        elif x_api_key:
            token = x_api_key.strip()
        if token != expected_key:
            raise HTTPException(status_code=401, detail="Неверный API-ключ")

    def _info(project) -> dict:
        return {
            "id": str(project.id),
            "name": project.name,
            "revision": project.revision,
            "updated_at": project.updated_at.isoformat(),
        }

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/projects")
    def list_projects(_: None = Depends(require_auth)) -> dict:
        projects = app.state.store.list_projects()
        return {
            "projects": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "revision": p.revision,
                    "updated_at": p.updated_at.isoformat(),
                }
                for p in projects
            ]
        }

    @app.get("/projects/{project_id}")
    def get_project(project_id: UUID, _: None = Depends(require_auth)) -> Response:
        project = app.state.store.get(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Проект не найден")
        return Response(
            content=project.data,
            media_type="application/octet-stream",
            headers={
                "X-Project-Id": str(project.id),
                "X-Project-Name": project.name,
                "X-Revision": str(project.revision),
                "X-Updated-At": project.updated_at.isoformat(),
            },
        )

    @app.post("/projects")
    async def create_project(
        request: Request,
        _: None = Depends(require_auth),
        x_project_id: str = Header(..., alias="X-Project-Id"),
        x_project_name: str = Header("Проект", alias="X-Project-Name"),
        x_revision: int = Header(1, alias="X-Revision"),
    ) -> JSONResponse:
        data = await request.body()
        if not data:
            raise HTTPException(status_code=400, detail="Пустое тело проекта")
        try:
            project_id = UUID(x_project_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Некорректный X-Project-Id") from exc
        try:
            project = app.state.store.create(
                project_id=project_id,
                name=x_project_name,
                revision=x_revision,
                data=data,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return JSONResponse(_info(project), status_code=201)

    @app.put("/projects/{project_id}")
    async def push_project(
        project_id: UUID,
        request: Request,
        _: None = Depends(require_auth),
        x_project_name: str = Header("Проект", alias="X-Project-Name"),
        x_revision: int = Header(..., alias="X-Revision"),
        if_match: str | None = Header(default=None, alias="If-Match"),
        x_force: str | None = Header(default=None, alias="X-Force"),
    ) -> JSONResponse:
        data = await request.body()
        if not data:
            raise HTTPException(status_code=400, detail="Пустое тело проекта")
        force = (x_force or "").strip() in {"1", "true", "True", "yes"}
        try:
            expected = int(if_match) if if_match is not None else -1
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Некорректный If-Match") from exc
        try:
            project = app.state.store.push(
                project_id,
                name=x_project_name,
                expected_revision=expected,
                new_revision=x_revision,
                data=data,
                force=force,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Проект не найден") from exc
        except ConflictError as exc:
            return JSONResponse(
                {
                    "detail": "Конфликт revision",
                    "remote": _info(exc.remote),
                },
                status_code=409,
            )
        return JSONResponse(_info(project))

    return app


app = create_app()
