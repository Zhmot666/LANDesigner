from __future__ import annotations

import math
from pathlib import Path
from uuid import UUID

from PySide6.QtGui import QImage

from landesigner.domain.entities import Device, Floor, FloorPlanAsset, FloorPlanRoute, ProjectSnapshot

MAX_PLAN_SIDE_PX = 4096
LAYOUT_STEP = 80.0
LAYOUT_COLS = 6
LAYOUT_ORIGIN = 60.0


def assets_dir_for_project(project_file: str | Path) -> Path:
    """Каталог рядом с .lanproj: `demo.lanproj.assets/`."""
    return Path(str(project_file) + ".assets")


def resolve_plan_image(project_file: str | Path | None, relpath: str) -> Path | None:
    if not project_file or not relpath:
        return None
    path = assets_dir_for_project(project_file) / relpath
    return path if path.is_file() else None


def rooms_on_floor(snapshot: ProjectSnapshot, floor_id: UUID) -> set[UUID]:
    return {r.id for r in snapshot.rooms if r.floor_id == floor_id}


def devices_on_floor(snapshot: ProjectSnapshot, floor_id: UUID) -> list[Device]:
    room_ids = rooms_on_floor(snapshot, floor_id)
    return [d for d in snapshot.devices if d.room_id in room_ids]


def assets_for_floor(snapshot: ProjectSnapshot, floor_id: UUID) -> list[FloorPlanAsset]:
    return [a for a in snapshot.floor_plan_assets if a.floor_id == floor_id]


def asset_for_device(
    snapshot: ProjectSnapshot,
    floor_id: UUID,
    device_id: UUID,
) -> FloorPlanAsset | None:
    return next(
        (
            a
            for a in snapshot.floor_plan_assets
            if a.floor_id == floor_id and a.device_id == device_id
        ),
        None,
    )


def get_floor(snapshot: ProjectSnapshot, floor_id: UUID) -> Floor:
    floor = next((f for f in snapshot.floors if f.id == floor_id), None)
    if floor is None:
        raise ValueError("Этаж не найден")
    return floor


def set_scale(snapshot: ProjectSnapshot, floor_id: UUID, scale_m_per_px: float) -> Floor:
    if scale_m_per_px <= 0:
        raise ValueError("Масштаб должен быть > 0")
    floor = get_floor(snapshot, floor_id)
    floor.scale_m_per_px = float(scale_m_per_px)
    return floor


def set_plan_image_relpath(
    snapshot: ProjectSnapshot,
    floor_id: UUID,
    relpath: str,
) -> Floor:
    floor = get_floor(snapshot, floor_id)
    floor.plan_image_relpath = relpath.strip()
    return floor


def import_plan_image(
    snapshot: ProjectSnapshot,
    floor_id: UUID,
    source_path: str | Path,
    project_file: str | Path,
) -> str:
    """
    Копирует/масштабирует подложку в `.lanproj.assets/`, пишет relpath в Floor.
    Возвращает относительный путь файла.
    """
    from PySide6.QtCore import Qt

    source = Path(source_path)
    if not source.is_file():
        raise ValueError(f"Файл не найден: {source}")

    image = QImage(str(source))
    if image.isNull():
        raise ValueError("Не удалось прочитать изображение")

    w, h = image.width(), image.height()
    longest = max(w, h)
    if longest > MAX_PLAN_SIDE_PX:
        scale = MAX_PLAN_SIDE_PX / float(longest)
        image = image.scaled(
            max(1, int(w * scale)),
            max(1, int(h * scale)),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    assets = assets_dir_for_project(project_file)
    assets.mkdir(parents=True, exist_ok=True)
    rel = f"floor_{floor_id.hex}.png"
    dest = assets / rel
    if not image.save(str(dest), "PNG"):
        raise ValueError("Не удалось сохранить подложку")

    set_plan_image_relpath(snapshot, floor_id, rel)
    return rel


def ensure_assets_for_floor(snapshot: ProjectSnapshot, floor_id: UUID) -> bool:
    """Создаёт маркеры для устройств комнат этажа, удаляет осиротевшие."""
    changed = False
    device_ids = {d.id for d in devices_on_floor(snapshot, floor_id)}
    before = len(snapshot.floor_plan_assets)
    snapshot.floor_plan_assets = [
        a
        for a in snapshot.floor_plan_assets
        if a.floor_id != floor_id or a.device_id in device_ids
    ]
    if len(snapshot.floor_plan_assets) != before:
        changed = True

    existing = {
        a.device_id for a in snapshot.floor_plan_assets if a.floor_id == floor_id
    }
    for index, device in enumerate(devices_on_floor(snapshot, floor_id)):
        if device.id in existing:
            continue
        col = index % LAYOUT_COLS
        row = index // LAYOUT_COLS
        snapshot.floor_plan_assets.append(
            FloorPlanAsset(
                floor_id=floor_id,
                device_id=device.id,
                x=LAYOUT_ORIGIN + col * LAYOUT_STEP,
                y=LAYOUT_ORIGIN + row * LAYOUT_STEP,
            )
        )
        changed = True
    return changed


def place_device(
    snapshot: ProjectSnapshot,
    floor_id: UUID,
    device_id: UUID,
    x: float | None = None,
    y: float | None = None,
) -> FloorPlanAsset:
    get_floor(snapshot, floor_id)
    if not any(d.id == device_id for d in snapshot.devices):
        raise ValueError("Устройство не найдено")
    existing = asset_for_device(snapshot, floor_id, device_id)
    if existing is not None:
        if x is not None:
            existing.x = float(x)
        if y is not None:
            existing.y = float(y)
        return existing
    count = len(assets_for_floor(snapshot, floor_id))
    col = count % LAYOUT_COLS
    row = count // LAYOUT_COLS
    asset = FloorPlanAsset(
        floor_id=floor_id,
        device_id=device_id,
        x=LAYOUT_ORIGIN + col * LAYOUT_STEP if x is None else float(x),
        y=LAYOUT_ORIGIN + row * LAYOUT_STEP if y is None else float(y),
    )
    snapshot.floor_plan_assets.append(asset)
    return asset


def move_asset(
    snapshot: ProjectSnapshot,
    asset_id: UUID,
    x: float,
    y: float,
) -> FloorPlanAsset:
    asset = next((a for a in snapshot.floor_plan_assets if a.id == asset_id), None)
    if asset is None:
        raise ValueError("Маркер на плане не найден")
    asset.x = float(x)
    asset.y = float(y)
    return asset


def remove_asset(snapshot: ProjectSnapshot, asset_id: UUID) -> None:
    snapshot.floor_plan_assets = [
        a for a in snapshot.floor_plan_assets if a.id != asset_id
    ]


def remove_routes_for_floor(snapshot: ProjectSnapshot, floor_id: UUID) -> None:
    snapshot.floor_plan_routes = [
        r for r in snapshot.floor_plan_routes if r.floor_id != floor_id
    ]


def path_length_px(points: list[tuple[float, float]]) -> float:
    if len(points) < 2:
        return 0.0
    total = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        total += math.hypot(x1 - x0, y1 - y0)
    return total


def path_length_m(points: list[tuple[float, float]], scale_m_per_px: float) -> float:
    return path_length_px(points) * float(scale_m_per_px)


def routes_for_floor(snapshot: ProjectSnapshot, floor_id: UUID) -> list[FloorPlanRoute]:
    return [r for r in snapshot.floor_plan_routes if r.floor_id == floor_id]


def add_route(
    snapshot: ProjectSnapshot,
    floor_id: UUID,
    points: list[tuple[float, float]],
    *,
    cable_id: UUID | None = None,
    label: str = "",
) -> FloorPlanRoute:
    get_floor(snapshot, floor_id)
    cleaned = [(float(x), float(y)) for x, y in points]
    if len(cleaned) < 2:
        raise ValueError("Трасса должна содержать минимум 2 точки")
    if cable_id is not None and not any(c.id == cable_id for c in snapshot.cables):
        raise ValueError("Кабель не найден")
    route = FloorPlanRoute(
        floor_id=floor_id,
        cable_id=cable_id,
        points=cleaned,
        label=label.strip(),
    )
    snapshot.floor_plan_routes.append(route)
    return route


def set_route_cable(
    snapshot: ProjectSnapshot,
    route_id: UUID,
    cable_id: UUID | None,
) -> FloorPlanRoute:
    route = next((r for r in snapshot.floor_plan_routes if r.id == route_id), None)
    if route is None:
        raise ValueError("Трасса не найдена")
    if cable_id is not None and not any(c.id == cable_id for c in snapshot.cables):
        raise ValueError("Кабель не найден")
    route.cable_id = cable_id
    return route


def remove_route(snapshot: ProjectSnapshot, route_id: UUID) -> None:
    snapshot.floor_plan_routes = [
        r for r in snapshot.floor_plan_routes if r.id != route_id
    ]


def route_length_m(snapshot: ProjectSnapshot, route_id: UUID) -> float:
    route = next((r for r in snapshot.floor_plan_routes if r.id == route_id), None)
    if route is None:
        raise ValueError("Трасса не найдена")
    floor = get_floor(snapshot, route.floor_id)
    return path_length_m(route.points, floor.scale_m_per_px)


def apply_route_length_to_cable(snapshot: ProjectSnapshot, route_id: UUID) -> float:
    """Записать длину трассы в привязанный кабель. Возвращает длину в метрах."""
    from landesigner.services import inventory as inv

    route = next((r for r in snapshot.floor_plan_routes if r.id == route_id), None)
    if route is None:
        raise ValueError("Трасса не найдена")
    if route.cable_id is None:
        raise ValueError("К трассе не привязан кабель")
    length = route_length_m(snapshot, route_id)
    inv.update_cable(snapshot, route.cable_id, length_m=round(length, 3))
    return length


def floor_label(snapshot: ProjectSnapshot, floor_id: UUID) -> str:
    floor = next((f for f in snapshot.floors if f.id == floor_id), None)
    if floor is None:
        return "?"
    building = next((b for b in snapshot.buildings if b.id == floor.building_id), None)
    bname = building.name if building else "?"
    return f"{bname} / {floor.name}"
