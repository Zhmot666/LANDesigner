from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from landesigner.domain.entities import DeviceType, ProjectSnapshot
from landesigner.domain.enums import DeviceRole
from landesigner.services.import_export import CsvFormatError

PRESET_MAGIC = "#LANDESIGNER_DEVICE_TYPES"
PRESET_VERSION = 1
SECTION_NAME = "device_types"
HEADERS = ["id", "site_id", "vendor", "model", "role", "port_template_json"]


@dataclass(frozen=True)
class PresetImportResult:
    added: int = 0
    updated: int = 0
    skipped: int = 0

    def summary(self) -> str:
        return (
            f"добавлено {self.added}, обновлено {self.updated}, пропущено {self.skipped}"
        )


@dataclass(frozen=True)
class _PresetRow:
    vendor: str
    model: str
    role: DeviceRole
    port_template: list[dict]


def type_key(vendor: str, model: str) -> str:
    return f"{vendor.strip().casefold()}\0{model.strip().casefold()}"


def export_device_types(snapshot: ProjectSnapshot, path: str | Path) -> None:
    Path(path).write_text(export_device_types_to_text(snapshot), encoding="utf-8-sig")


def export_device_types_to_text(snapshot: ProjectSnapshot) -> str:
    buf = io.StringIO(newline="")
    buf.write(f"{PRESET_MAGIC};version={PRESET_VERSION}\n")
    buf.write(f"#section={SECTION_NAME}\n")
    writer = csv.DictWriter(buf, fieldnames=HEADERS, lineterminator="\n")
    writer.writeheader()
    for dt in snapshot.device_types:
        writer.writerow(
            {
                "id": str(dt.id),
                "site_id": str(dt.site_id),
                "vendor": dt.vendor,
                "model": dt.model,
                "role": dt.role.value,
                "port_template_json": json.dumps(dt.port_template, ensure_ascii=False),
            }
        )
    return buf.getvalue()


def import_device_types(
    snapshot: ProjectSnapshot,
    path: str | Path,
) -> PresetImportResult:
    text = Path(path).read_text(encoding="utf-8-sig")
    return import_device_types_from_text(snapshot, text)


def import_device_types_from_text(
    snapshot: ProjectSnapshot,
    text: str,
) -> PresetImportResult:
    rows = _parse_preset_rows(text)
    if not snapshot.sites:
        raise CsvFormatError("В проекте нет площадки — некуда добавить типы")
    site_id = snapshot.sites[0].id

    by_key = {type_key(dt.vendor, dt.model): dt for dt in snapshot.device_types}
    used_ids = {d.device_type_id for d in snapshot.devices}

    added = updated = skipped = 0
    for row in rows:
        key = type_key(row.vendor, row.model)
        existing = by_key.get(key)
        if existing is None:
            dtype = DeviceType(
                id=uuid4(),
                site_id=site_id,
                vendor=row.vendor.strip(),
                model=row.model.strip(),
                role=row.role,
                port_template=[dict(p) for p in row.port_template],
            )
            snapshot.device_types.append(dtype)
            by_key[key] = dtype
            added += 1
            continue
        if existing.id in used_ids:
            skipped += 1
            continue
        existing.role = row.role
        existing.port_template = [dict(p) for p in row.port_template]
        updated += 1

    return PresetImportResult(added=added, updated=updated, skipped=skipped)


def _parse_preset_rows(text: str) -> list[_PresetRow]:
    lines = text.splitlines()
    if not lines:
        raise CsvFormatError("Пустой пресет типов")

    first = lines[0].strip()
    if not first.startswith(PRESET_MAGIC):
        raise CsvFormatError(
            f"Ожидался заголовок {PRESET_MAGIC};version=N, получено: {first!r}"
        )
    version = _parse_version(first)
    if version != PRESET_VERSION:
        raise CsvFormatError(f"Неподдерживаемая версия пресета: {version}")

    section_lines: list[str] = []
    in_section = False
    for line in lines[1:]:
        stripped = line.strip()
        if stripped.startswith("#section="):
            name = stripped.split("=", 1)[1].strip()
            in_section = name == SECTION_NAME
            continue
        if stripped.startswith("#") and not stripped.startswith("#section="):
            continue
        if in_section:
            section_lines.append(line)

    if not section_lines:
        raise CsvFormatError(f"Нет секции {SECTION_NAME}")

    reader = csv.DictReader(io.StringIO("\n".join(section_lines) + "\n"))
    if reader.fieldnames is None:
        raise CsvFormatError("Пустая секция типов")

    result: list[_PresetRow] = []
    for raw in reader:
        row = {k: (v or "").strip() for k, v in raw.items() if k is not None}
        vendor = row.get("vendor", "")
        model = row.get("model", "")
        if not vendor and not model:
            continue
        raw_template = row.get("port_template_json") or "[]"
        try:
            template = json.loads(raw_template)
        except json.JSONDecodeError as exc:
            raise CsvFormatError(f"Некорректный port_template_json: {exc}") from exc
        if not isinstance(template, list):
            raise CsvFormatError("port_template_json должен быть JSON-массивом")
        role_raw = row.get("role") or DeviceRole.OTHER.value
        try:
            role = DeviceRole(role_raw)
        except ValueError:
            role = DeviceRole.OTHER
        result.append(
            _PresetRow(
                vendor=vendor,
                model=model,
                role=role,
                port_template=template,
            )
        )
    return result


def _parse_version(header: str) -> int:
    parts = header.split(";")
    for part in parts[1:]:
        part = part.strip()
        if part.startswith("version="):
            try:
                return int(part.split("=", 1)[1])
            except ValueError as exc:
                raise CsvFormatError(f"Некорректная версия: {part!r}") from exc
    raise CsvFormatError(f"В заголовке нет version=: {header!r}")
