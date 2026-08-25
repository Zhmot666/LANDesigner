from __future__ import annotations

from landesigner.domain.entities import ProjectMeta, ProjectSnapshot, Site
from landesigner.domain.enums import CableKind, DeviceRole
from landesigner.services import gxp_iq as gxp
from landesigner.services import inventory as inv
from landesigner.services import reports as reports_svc
from landesigner.services import topology as topo
from landesigner.services.gxp_iq import IqVerdict
from landesigner.services.reports import ReportKind


def _base() -> ProjectSnapshot:
    meta = ProjectMeta(name="GxP-Demo")
    site = Site(project_id=meta.id, name="Site-A")
    return ProjectSnapshot(meta=meta, sites=[site])


def test_gxp_iq_empty_project_fails_edge():
    snap = _base()
    results = {r.code: r for r in gxp.run_gxp_iq(snap)}
    assert results["IQ-01"].verdict == IqVerdict.PASS
    assert results["IQ-02"].verdict == IqVerdict.NA
    assert results["IQ-07"].verdict == IqVerdict.FAIL
    assert results["IQ-08"].verdict == IqVerdict.NA
    assert not gxp.iq_overall_pass(list(results.values()))


def test_gxp_iq_firewall_wan_and_topology_pass():
    snap = _base()
    fw_type = inv.add_device_type(
        snap, vendor="F", model="FG", role=DeviceRole.FIREWALL, port_count=1
    )
    isp_type = inv.add_device_type(
        snap, vendor="I", model="CPE", role=DeviceRole.MODEM, port_count=1
    )
    fw = inv.add_device(snap, fw_type.id, "fg-edge")
    isp = inv.add_device(snap, isp_type.id, "ISP-CPE")
    pa = inv.ports_for_device(snap, fw.id)[0]
    pb = inv.ports_for_device(snap, isp.id)[0]
    inv.add_cable(
        snap,
        pa.id,
        pb.id,
        label="CAB-0001 · WAN: fg-edge / Gi1/0/1 ↔ ISP-CPE / Gi1/0/1",
        purpose="WAN",
        kind=CableKind.COPPER,
    )
    topo.ensure_topology(snap)

    results = {r.code: r for r in gxp.run_gxp_iq(snap)}
    assert results["IQ-01"].verdict == IqVerdict.PASS
    assert results["IQ-02"].verdict == IqVerdict.PASS
    assert results["IQ-06"].verdict == IqVerdict.PASS
    assert results["IQ-07"].verdict == IqVerdict.PASS
    assert results["IQ-08"].verdict == IqVerdict.PASS
    assert results["IQ-12"].verdict == IqVerdict.PASS
    assert gxp.iq_overall_pass(list(results.values()))


def test_gxp_iq_report_kind():
    snap = _base()
    table = reports_svc.build_report(snap, ReportKind.GXP_IQ)
    assert table.kind == ReportKind.GXP_IQ
    assert any(row[0] == "IQ-01" for row in table.rows)
    assert table.rows[0][4] in {"PASS", "FAIL"}
