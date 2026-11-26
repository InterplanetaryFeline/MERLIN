"""Every tab describes the one vehicle on the Summary.

v1.3.1 had three ways to show a different one: the Masses tab added the burnout residuals to the lift-off mass,
the Sensitivity tab re-read the design file without the optimised split or the unsaved edits, and the hidden
Architecture and Drop-zone tabs sized their own copy the same way. These tests pin each of them.
"""
import json
import os
import socket
import threading
import urllib.error
import urllib.request

import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import webgui, sensitivity, payload_env, mass_properties
from launch_vehicle.optimization import apply_optimum

_SRV = {}


def _server():
    if "url" in _SRV:
        return _SRV["url"]
    from http.server import ThreadingHTTPServer
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    webgui.Handler.workdir = os.path.join(ROOT, "outputs", "gui_test")
    os.makedirs(webgui.Handler.workdir, exist_ok=True)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), webgui.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    _SRV["url"] = f"http://127.0.0.1:{port}"
    return _SRV["url"]


def _post(path, payload):
    req = urllib.request.Request(_server() + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read())


def _sized(name, overrides=None):
    return size_vehicle(apply_optimum(load_design(os.path.join(ROOT, "validation", f"{name}.yaml"), ASSUMP, overrides))[0])


@pytest.mark.parametrize("name", ["electron", "falcon9", "ariane64", "vega"])
def test_the_ledger_adds_up_to_the_lift_off_mass(name):
    """The residual and reserve propellant is listed for burnout and is inside the loaded propellant: adding every
    line made Falcon 9's ledger 14 t heavier than the vehicle."""
    res = _sized(name)
    assert mass_properties.liftoff_total(res) == pytest.approx(res.glom_kg, rel=1e-9)
    assert sum(i.mass_kg for i in res.ledger) > res.glom_kg or name == "vega", "the burnout lines are still listed"
    page = webgui.result_json(res, "t")
    assert sum(i["mass_kg"] for i in page["ledger"] if i["liftoff"]) == pytest.approx(page["glom_kg"], rel=1e-9)


def test_the_report_totals_the_ledger_at_lift_off():
    from launch_vehicle import report
    res = _sized("electron")
    html = report._ledger(res)
    assert "Total at lift-off" in html and f"{res.glom_kg:,.0f}" in html


def test_sensitivity_is_centred_on_the_design_and_starts_from_the_sized_vehicle():
    """Electron is designed for 300 kg; its payload study ran from 5 to 15 t. And on a design whose split is
    optimised, the 0 % case was sized from the file's own split, a different vehicle from the baseline."""
    res = _sized("electron")
    rows = sensitivity.standard_studies(os.path.join(ROOT, "validation", "electron.yaml"), ASSUMP, res)
    pay = [r for r in rows if r["study"].startswith("Payload mass")]
    vals = [r["value"] for r in pay]
    assert min(vals) == pytest.approx(240.0) and max(vals) == pytest.approx(360.0)
    here = [r for r in rows if r["design_point"]]
    assert here and all(r["glom_kg"] == pytest.approx(res.glom_kg, rel=1e-9) for r in here)
    # a case is the base vehicle with one thing changed, so the split it is sized with is the base's
    sp = sensitivity._case_spec(os.path.join(ROOT, "validation", "electron.yaml"), ASSUMP, {"mission.payload_mass_kg": 315.0}, None, res.spec)
    assert all(a == pytest.approx(b) for a, b in zip(sp.dv_fractions, res.spec.dv_fractions)) and not sp.optimise_dv
    # densities only for the propellants this vehicle carries
    assert {r["study"].split(" density")[0] for r in rows if "density" in r["study"]} == {"RP-1", "LOX"}


def test_sensitivity_keeps_the_unsaved_edits():
    ov = {"mission.payload_mass_kg": 250.0}
    res = _sized("electron", ov)
    rows = sensitivity.standard_studies(os.path.join(ROOT, "validation", "electron.yaml"), ASSUMP, res, ov)
    isp = [r for r in rows if r["study"].startswith("Specific impulse")]
    assert any(r["design_point"] for r in isp)
    near = [r for r in isp if r["value"] == pytest.approx(0.025)][0]
    assert abs(near["glom_kg"] / res.glom_kg - 1) < 0.10, "the +2.5 % Isp case lost the 250 kg payload edit"


def test_every_route_about_this_design_starts_from_the_stored_result():
    """The source rule behind the tests above: a route that sizes "this design" goes through _baseline or the
    stored result, never through load_design on its own."""
    import inspect
    src = inspect.getsource(webgui.Handler.do_POST)
    for route in ("/api/sensitivity", "/api/architecture", "/api/hazard", "/api/hazard_export"):
        body = src.split(f'u.path == "{route}"')[1].split("if u.path ==")[0]
        assert "load_design(" not in body, route
        assert "_baseline(b)" in body or "_STATE.get(" in body, route


def test_the_sensitivity_route_uses_the_vehicle_on_the_summary():
    out = _post("/api/size", {"path": "validation/electron.yaml", "overrides": {}, "studies": []})
    sens = _post("/api/sensitivity", {"path": "validation/electron.yaml", "overrides": {}, "token": out["token"]})
    assert sens["baseline_glom_kg"] == pytest.approx(out["glom_kg"], rel=1e-12)
    assert sens["token"] == out["token"]


def test_the_wind_settings_rerun_the_loads_without_resizing():
    out = _post("/api/size", {"path": "validation/electron.yaml", "overrides": {},
                              "studies": ["loads", "structure", "payload_env"]})
    before = out["study_summary"]["loads"]["moment_kNm"]
    sounding = os.path.join(webgui.Handler.workdir, "plain_sounding.csv")    # no gust of its own, unlike the example
    with open(sounding, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("altitude_m,speed_mps\n0,5\n4000,22\n10000,44\n16000,22\n30000,19\n")
    # a steady profile with no gust is refused rather than guessed, and the vehicle's loads are left as they were
    with pytest.raises(urllib.error.HTTPError):
        _post("/api/wind", {"token": out["token"],
                            "wind": {"profile": sounding, "kind": "steady", "gust_increment_mps": 0.0}})
    assert "mission.wind.profile" not in webgui._STATE[out["token"]]["overrides"]
    got = _post("/api/wind", {"token": out["token"], "pad_height_m": 12.0,
                              "wind": {"profile": sounding, "kind": "steady", "gust_increment_mps": 30.0}})
    assert {"loads", "structure", "payload_env"} <= set(got["study_summary"])
    # Electron's governing moment is the ground-wind case, which winds aloft do not touch, so check what was flown
    assert out["study_summary"]["loads"]["profiles"] == ["book_amr_95"]
    assert got["study_summary"]["loads"]["profiles"] == ["plain_sounding"]
    # the pad height raises the vehicle into a stronger ground wind, and the ground case governs Electron
    assert got["study_summary"]["loads"]["moment_kNm"] > before
    assert webgui._STATE[out["token"]]["overrides"]["mission.pad_height_m"] == 12.0
    with pytest.raises(urllib.error.HTTPError):
        _post("/api/wind", {"token": out["token"], "pad_height_m": -3, "wind": {}})
    assert webgui._STATE[out["token"]]["res"].glom_kg == pytest.approx(out["glom_kg"], rel=1e-12)
    assert webgui._STATE[out["token"]]["overrides"]["mission.wind.gust_increment_mps"] == 30.0


def test_the_payload_environment_reports_jettison_heating_and_venting():
    from launch_vehicle import trajectory as tj
    res = _sized("electron")
    tr = tj.fly_design(res)
    f = payload_env.flight_environment(res, tr)
    k = len(tr.t_s) // 3
    assert f["fmh_W_m2"][k] == pytest.approx(tr.q_Pa[k] * tr.v_mps[k])          # 1/2 rho v^3 = q v
    assert f["fmh_limit_W_m2"] == 1135.0 and f["vent_rate_kPa_s"] == (2.5, 4.0)
    assert 0.5 < f["max_dpdt_kPa_s"] < 5.0 and 10.0 < f["max_dpdt_t_s"] < 120.0
    assert "jettison_t_s" in f and f["jettison_ok"] == (f["jettison_fmh_after_W_m2"] <= 1135.0)
    assert f["fmh_ok_from_t_s"] > f["max_q_t_s"]
    assert all(len(r) == 4 for r in payload_env.ARIANE6_REFERENCE)


def test_the_uncertainty_nominal_is_the_vehicle_on_the_summary():
    """It re-read the design file too, losing the edits and the optimised split."""
    out = webgui.run_sizing(os.path.join(ROOT, "validation", "electron.yaml"), ASSUMP, {"mission.payload_mass_kg": 250.0},
                            os.path.join(ROOT, "outputs", "gui_test"), "unc-test", ("uncertainty",), n_mc=4)
    mc = webgui._STATE["unc-test"]["extras"]["uncertainty"]
    assert mc["nominal_glom_kg"] == pytest.approx(out["glom_kg"], rel=1e-9)


def test_the_constant_wind_example_is_offered_and_read():
    from launch_vehicle import wind
    shipped = {v: k for v, _lab, k in wind.shipped_profiles()}
    assert shipped.get("book_amr_95") == "gust_envelope"
    p = "examples/wind_profiles/example_constant_wind.csv"
    assert p in shipped
    pr = wind.load({"profile": p}, root=os.path.join(ROOT, "validation"))[0]   # found from any design's folder
    assert set(pr.speeds_mps) == {20.0} and pr.kind == "gust_envelope"


def test_the_uncertainty_tab_gets_its_numbers():
    """The summary asked for p05_glom_kg where the analysis says p05, and the tab showed only its chart."""
    out = webgui.run_sizing(os.path.join(ROOT, "validation", "electron.yaml"), ASSUMP, {},
                            os.path.join(ROOT, "outputs", "gui_test"), "unc-tab", ("uncertainty",), n_mc=4)
    u = out["study_summary"]["uncertainty"]
    assert u["p05_glom_kg"] <= u["p50_glom_kg"] <= u["p95_glom_kg"] and u["n"] >= 1
    assert u["nominal_glom_kg"] == pytest.approx(out["glom_kg"], rel=1e-9)
