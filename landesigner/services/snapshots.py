from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class SnapshotInfo:
    path: Path
    name: str
    created_at: datetime
    size_bytes: int


def snapshots_dir(project_file: str | Path) -> Path:
    return Path(str(project_file) + ".snapshots")


def assets_dir(project_file: str | Path) -> Path:
    return Path(str(project_file) + ".assets")


def _safe_label(label: str) -> str:
    text = re.sub(r"[^\w\-а-яА-ЯёЁ]+", "_", (label or "").strip(), flags=re.UNICODE)
    text = text.strip("._") or "snapshot"
    return text[:60]


def create_snapshot(project_file: str | Path, label: str = "") -> Path:
    """
    Копирует .lanproj (+ .assets при наличии) в каталог снимков рядом с проектом.
    Возвращает путь к скопированному .lanproj.
    """
    src = Path(project_file)
    if not src.is_file():
        raise ValueError("Проект ещё не сохранён в файл")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{stamp}_{_safe_label(label)}" if label.strip() else stamp
    dest_dir = snapshots_dir(src) / folder_name
    if dest_dir.exists():
        dest_dir = snapshots_dir(src) / f"{folder_name}_{uuid4().hex[:6]}"
    dest_dir.mkdir(parents=True, exist_ok=False)

    dest_proj = dest_dir / src.name
    shutil.copy2(src, dest_proj)

    src_assets = assets_dir(src)
    if src_assets.is_dir():
        shutil.copytree(src_assets, dest_dir / src_assets.name)

    return dest_proj


def list_snapshots(project_file: str | Path) -> list[SnapshotInfo]:
    root = snapshots_dir(project_file)
    if not root.is_dir():
        return []
    project_name = Path(project_file).name
    result: list[SnapshotInfo] = []
    for folder in sorted(root.iterdir(), reverse=True):
        if not folder.is_dir():
            continue
        candidate = folder / project_name
        if not candidate.is_file():
            # На случай переименования — любой .lanproj внутри
            lan = list(folder.glob("*.lanproj"))
            if not lan:
                continue
            candidate = lan[0]
        result.append(
            SnapshotInfo(
                path=candidate,
                name=folder.name,
                created_at=datetime.fromtimestamp(candidate.stat().st_mtime),
                size_bytes=candidate.stat().st_size,
            )
        )
    return result


def restore_snapshot(
    project_file: str | Path,
    snapshot_lanproj: str | Path,
    *,
    make_safety_copy: bool = True,
) -> None:
    """
    Восстанавливает снимок поверх текущего файла проекта.
    Перед заменой опционально делает safety-снимок текущего состояния.
    """
    dest = Path(project_file)
    src = Path(snapshot_lanproj)
    if not src.is_file():
        raise ValueError("Файл снимка не найден")
    if not dest.is_file():
        raise ValueError("Текущий проект не сохранён")

    if make_safety_copy:
        create_snapshot(dest, label="before_restore")

    shutil.copy2(src, dest)

    assets_src = Path(str(src) + ".assets")
    assets_dst = assets_dir(dest)
    if assets_dst.exists():
        shutil.rmtree(assets_dst)
    if assets_src.is_dir():
        shutil.copytree(assets_src, assets_dst)
