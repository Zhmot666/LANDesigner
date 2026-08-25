from __future__ import annotations

from pathlib import Path

from landesigner.adapters.local_sqlite.repository import LocalSqliteRepository
from landesigner.domain.entities import ProjectMeta, ProjectSnapshot, Site
from landesigner.domain.enums import DeviceRole
from landesigner.services import change_journal as journal
from landesigner.services import import_export as csv_io
from landesigner.services import inventory as inv
from landesigner.services import reports as reports_svc
from landesigner.services.reports import ReportKind


def test_append_and_persist_change_log(tmp_path: Path):
    meta = ProjectMeta(name="J")
    site = Site(project_id=meta.id, name="S")
    snap = ProjectSnapshot(meta=meta, sites=[site])
    journal.append_change(snap, "Добавлено устройство", detail="sw1", actor="Иванов")
    assert len(snap.change_log) == 1
    assert snap.change_log[0].actor == "Иванов"

    path = tmp_path / "j.lanproj"
    repo = LocalSqliteRepository()
    repo.create_new_project(str(path), meta)
    # reload empty then save with journal
    loaded = repo.load_project(str(path))
    journal.append_change(loaded, "Тест", detail="x", actor="Петров")
    loaded.meta.revision += 1
    repo.save_project(str(path), loaded)
    again = repo.load_project(str(path))
    assert any(e.action == "Тест" and e.actor == "Петров" for e in again.change_log)


def test_change_log_csv_roundtrip():
    meta = ProjectMeta(name="J")
    site = Site(project_id=meta.id, name="S")
    snap = ProjectSnapshot(meta=meta, sites=[site])
    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SWITCH, port_count=1
    )
    inv.add_device(snap, dtype.id, "sw1")
    journal.append_change(snap, "Добавлено устройство", detail="sw1", actor="QA")
    text = csv_io.export_to_text(snap)
    assert "#section=change_log" in text
    restored = csv_io.import_from_text(text)
    assert any(e.action == "Добавлено устройство" and e.actor == "QA" for e in restored.change_log)


def test_change_log_report():
    meta = ProjectMeta(name="J")
    snap = ProjectSnapshot(meta=meta, sites=[Site(project_id=meta.id, name="S")])
    journal.append_change(snap, "X", detail="Y", actor="Z")
    table = reports_svc.build_report(snap, ReportKind.CHANGE_LOG)
    assert table.kind == ReportKind.CHANGE_LOG
    assert any(row[1] == "Z" and row[2] == "X" for row in table.rows)
