from __future__ import annotations

from PySide6.QtWidgets import QApplication

from landesigner.domain.entities import ProjectMeta, ProjectSnapshot, Site
from landesigner.domain.enums import CableKind, DeviceRole
from landesigner.services import inventory as inv
from landesigner.ui.widgets.device_card import ContextCard, ContextKind


def test_context_card_shows_cable_bundle(qapp: QApplication | None = None):
    app = QApplication.instance() or QApplication([])
    _ = app
    meta = ProjectMeta(name="C")
    snap = ProjectSnapshot(meta=meta, sites=[Site(project_id=meta.id, name="S")])
    dtype = inv.add_device_type(
        snap, vendor="X", model="Y", role=DeviceRole.SWITCH, port_count=2
    )
    a = inv.add_device(snap, dtype.id, "sw-a")
    b = inv.add_device(snap, dtype.id, "sw-b")
    pa0, pa1 = inv.ports_for_device(snap, a.id)
    pb0, pb1 = inv.ports_for_device(snap, b.id)
    c1 = inv.add_cable(snap, pa0.id, pb0.id, label="L1", kind=CableKind.COPPER)
    c2 = inv.add_cable(snap, pa1.id, pb1.id, label="L2", kind=CableKind.COPPER)

    card = ContextCard()
    card.set_snapshot(snap)
    card.show_cables([c1.id, c2.id])
    assert card._kind == ContextKind.CABLE  # noqa: SLF001
    assert not card._cab_list.isHidden()
    assert card._cab_list.count() == 2
    assert "L1" in card._cab_label.text() or card._cable_id == c1.id
    card.show_cables([c2.id])
    assert card._cab_list.isHidden()
    assert card._cab_label.text() == "L2"
