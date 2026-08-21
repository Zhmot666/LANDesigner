from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from landesigner.ports.remote import (
    RemoteAuthError,
    RemoteConflictError,
    RemoteProjectBlob,
    RemoteProjectInfo,
)


def _parse_dt(value: str) -> datetime:
    text = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _info_from_json(payload: dict[str, Any]) -> RemoteProjectInfo:
    return RemoteProjectInfo(
        id=UUID(str(payload["id"])),
        name=str(payload["name"]),
        revision=int(payload["revision"]),
        updated_at=_parse_dt(str(payload["updated_at"])),
    )


class RemoteHttpClient:
    """HTTP-клиент общего репозитория (stdlib urllib)."""

    def __init__(self, base_url: str, *, api_token: str = "", timeout_s: float = 30.0) -> None:
        self._base = base_url.rstrip("/")
        self._token = api_token.strip()
        self._timeout = timeout_s

    def list_projects(self) -> list[RemoteProjectInfo]:
        payload = self._request_json("GET", "/projects")
        return [_info_from_json(item) for item in payload["projects"]]

    def get_project(self, project_id: UUID) -> RemoteProjectBlob:
        data, headers = self._request_bytes("GET", f"/projects/{project_id}")
        info = RemoteProjectInfo(
            id=UUID(headers.get("X-Project-Id", str(project_id))),
            name=headers.get("X-Project-Name", "project"),
            revision=int(headers.get("X-Revision", "1")),
            updated_at=_parse_dt(headers.get("X-Updated-At", datetime.now(timezone.utc).isoformat())),
        )
        return RemoteProjectBlob(info=info, data=data)

    def create_project(
        self,
        *,
        project_id: UUID,
        name: str,
        revision: int,
        data: bytes,
    ) -> RemoteProjectInfo:
        payload = self._request_json(
            "POST",
            "/projects",
            body=data,
            content_type="application/octet-stream",
            headers={
                "X-Project-Id": str(project_id),
                "X-Project-Name": name,
                "X-Revision": str(revision),
            },
        )
        return _info_from_json(payload)

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
        headers = {
            "X-Project-Name": name,
            "X-Revision": str(new_revision),
            "If-Match": str(expected_revision),
        }
        if force:
            headers["X-Force"] = "1"
        try:
            payload = self._request_json(
                "PUT",
                f"/projects/{project_id}",
                body=data,
                content_type="application/octet-stream",
                headers=headers,
            )
        except RemoteConflictError:
            raise
        return _info_from_json(payload)

    def check_connection(self) -> tuple[bool, str]:
        """Проверка URL и API-ключа. Возвращает (ok, сообщение)."""
        try:
            data, _ = self._request_bytes("GET", "/health")
            status = "ok"
            try:
                payload = json.loads(data.decode("utf-8")) if data else {}
                status = str(payload.get("status", "ok"))
            except Exception:
                pass
            # Если ключ задан — дополнительно проверяем доступ к /projects.
            if self._token:
                projects = self.list_projects()
                return True, f"Сервер доступен ({status}), проектов: {len(projects)}"
            return True, f"Сервер доступен ({status})"
        except RemoteAuthError as exc:
            detail = str(exc).strip() or "Неверный API-ключ"
            return False, f"Ошибка авторизации: {detail}"
        except Exception as exc:
            return False, f"Нет связи: {exc}"

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
            headers["X-API-Key"] = self._token
        if extra:
            headers.update(extra)
        return headers

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        content_type: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        data, resp_headers = self._request_bytes(
            method,
            path,
            body=body,
            content_type=content_type,
            headers=headers,
        )
        if not data:
            return {}
        ctype = resp_headers.get("Content-Type", "")
        if "json" not in ctype and not data.startswith(b"{") and not data.startswith(b"["):
            return {}
        return json.loads(data.decode("utf-8"))

    def _request_bytes(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        content_type: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[bytes, dict[str, str]]:
        url = f"{self._base}{path}"
        req_headers = self._headers(headers)
        if content_type:
            req_headers["Content-Type"] = content_type
        request = urllib.request.Request(url, data=body, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                raw = response.read()
                header_map = {k: v for k, v in response.headers.items()}
                return raw, header_map
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code in (401, 403):
                raise RemoteAuthError(detail or "Ошибка авторизации") from exc
            if exc.code == 409:
                remote = self._conflict_info(detail)
                raise RemoteConflictError(detail or "Конфликт revision", remote) from exc
            raise RuntimeError(f"HTTP {exc.code}: {detail or exc.reason}") from exc

    def _conflict_info(self, detail: str) -> RemoteProjectInfo:
        try:
            payload = json.loads(detail)
            if "remote" in payload:
                return _info_from_json(payload["remote"])
            return _info_from_json(payload)
        except Exception:
            return RemoteProjectInfo(
                id=UUID(int=0),
                name="?",
                revision=-1,
                updated_at=datetime.now(timezone.utc),
            )
