from __future__ import annotations

from pathlib import Path

from landesigner.domain.entities import DeviceType, ProjectMeta, ProjectSnapshot, Site
from landesigner.domain.enums import DeviceRole, PortMedia
from landesigner.services import device_type_preset as preset_svc
from landesigner.services import inventory as inv


def _empty_project(name: str = "Preset") -> ProjectSnapshot:
    meta = ProjectMeta(name=name)
    site = Site(project_id=meta.id, name="S")
    return ProjectSnapshot(meta=meta, sites=[site])


def test_export_import_roundtrip_adds_types(tmp_path: Path):
    source = _empty_project("Src")
    inv.add_device_type(
        source,
        vendor="Cisco",
        model="C2960",
        role=DeviceRole.SWITCH,
        port_groups=[
            {
                "prefix": "Gi1/0/",
                "count": 2,
                "media": PortMedia.COPPER.value,
                "speed": 1000,
                "start": 1,
            }
        ],
    )
    path = tmp_path / "lib.ldtypes"
    preset_svc.export_device_types(source, path)
    text = path.read_text(encoding="utf-8-sig")
    assert preset_svc.PRESET_MAGIC in text

    target = _empty_project("Dst")
    result = preset_svc.import_device_types(target, path)
    assert result.added == 1
    assert result.updated == 0
    assert result.skipped == 0
    assert len(target.device_types) == 1
    assert target.device_types[0].vendor == "Cisco"
    assert target.device_types[0].model == "C2960"
    assert len(target.device_types[0].port_template) == 2
    # Новый UUID при импорте
    assert target.device_types[0].id != source.device_types[0].id


def test_import_merge_update_unused_and_skip_used():
    snap = _empty_project()
    unused = inv.add_device_type(
        snap,
        vendor="Generic",
        model="SW-24",
        role=DeviceRole.SWITCH,
        port_groups=[
            {
                "prefix": "Gi",
                "count": 1,
                "media": PortMedia.COPPER.value,
                "speed": 100,
                "start": 1,
            }
        ],
    )
    used = inv.add_device_type(
        snap,
        vendor="Eltex",
        model="MES",
        role=DeviceRole.SWITCH,
        port_groups=[
            {
                "prefix": "Gi",
                "count": 1,
                "media": PortMedia.COPPER.value,
                "speed": 1000,
                "start": 1,
            }
        ],
    )
    inv.add_device(snap, used.id, "sw1")

    preset_text = preset_svc.export_device_types_to_text(
        ProjectSnapshot(
            meta=ProjectMeta(name="Lib"),
            sites=[Site(name="S")],
            device_types=[
                DeviceType(
                    vendor="Generic",
                    model="SW-24",
                    role=DeviceRole.SWITCH,
                    port_template=[
                        {"name": "Gi1", "media": "COPPER", "speed": 1000},
                        {"name": "Gi2", "media": "COPPER", "speed": 1000},
                    ],
                ),
                DeviceType(
                    vendor="Eltex",
                    model="MES",
                    role=DeviceRole.SWITCH,
                    port_template=[
                        {"name": "X1", "media": "FIBER", "speed": 10000},
                    ],
                ),
                DeviceType(
                    vendor="HP",
                    model="Aruba",
                    role=DeviceRole.SWITCH,
                    port_template=[{"name": "1", "media": "COPPER", "speed": 1000}],
                ),
            ],
        )
    )

    result = preset_svc.import_device_types_from_text(snap, preset_text)
    assert result.added == 1
    assert result.updated == 1
    assert result.skipped == 1
    assert len(snap.device_types) == 3

    refreshed = next(dt for dt in snap.device_types if dt.id == unused.id)
    assert len(refreshed.port_template) == 2
    assert refreshed.port_template[0]["speed"] == 1000

    still = next(dt for dt in snap.device_types if dt.id == used.id)
    assert still.port_template[0]["name"].startswith("Gi")
    assert len(still.port_template) == 1


def test_import_skips_duplicate_casefold():
    snap = _empty_project()
    inv.add_device_type(
        snap,
        vendor="Cisco",
        model="Cat",
        role=DeviceRole.SWITCH,
        port_count=2,
    )
    inv.add_device(snap, snap.device_types[0].id, "core")

    text = preset_svc.export_device_types_to_text(
        ProjectSnapshot(
            meta=ProjectMeta(name="L"),
            sites=[Site(name="S")],
            device_types=[
                DeviceType(
                    vendor="cisco",
                    model="cat",
                    role=DeviceRole.ROUTER,
                    port_template=[{"name": "x", "media": "COPPER", "speed": 100}],
                )
            ],
        )
    )
    result = preset_svc.import_device_types_from_text(snap, text)
    assert result.skipped == 1
    assert snap.device_types[0].role == DeviceRole.SWITCH
