"""The GUI is a thin shell over the same model: these tests check that it stays thin and that it cannot be used
to read files outside the project.

The HTTP layer is exercised against a real server on an ephemeral port, because the interesting failures (JSON that
will not serialise, a figure key that does not exist, a traversal path that should be refused) only appear there.
"""
import json
import os
import socket
import threading
import urllib.error
import urllib.request

import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import webgui
from launch_vehicle.config_io import ConfigError

_SRV = {}


def _server():
    """One server for the whole module, on a free port."""
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
    _SRV["httpd"] = httpd
    _SRV["url"] = f"http://127.0.0.1:{port}"
    return _SRV["url"]


def _get(path, raw=False):
    with urllib.request.urlopen(_server() + path, timeout=120) as r:
        body = r.read()
        return (body, r.headers) if raw else json.loads(body)


def _post(path, payload):
    req = urllib.request.Request(_server() + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())


# ------------------------------------------------------------------ pure functions (no server)
def test_design_listing_finds_the_examples_and_validation_cases():
    paths = {d["path"] for d in webgui.list_designs()}
    assert "config/default_design.yaml" in paths
    assert any(p.startswith("examples/") for p in paths)
    assert any(p.startswith("validation/") for p in paths)
    assert not any("engineering_assumptions" in p for p in paths)


def test_path_traversal_is_refused():
    for bad in ("../../etc/passwd", "/etc/passwd", "config/../../../etc/shadow", "src/launch_vehicle/main.py"):
        with pytest.raises(ConfigError):
            webgui._safe_design_path(bad)
    assert webgui._safe_design_path("config/default_design.yaml").endswith("default_design.yaml")


def test_input_grouping_is_stable():
    assert webgui._group_of("mission.payload_mass_kg") == "Mission"
    assert webgui._group_of("stages.1.engine.isp_vac_s") == "Stage 2"
    assert webgui._group_of("boosters.n_total") == "Boosters"
    assert webgui._group_of("fairing.diameter_m") == "Vehicle, payload, fairing"
    assert webgui._group_of("mer.unpressurized_kg_m2") == "Assumptions and MER coefficients"


def test_design_inputs_carry_units_description_source_and_provenance():
    d = webgui.design_inputs(DESIGN, ASSUMP)
    assert d["n_stages"] == 2 and len(d["items"]) > 150
    for it in d["items"]:
        assert set(it) >= {"path", "value", "units", "description", "source", "provenance", "group", "type"}
    assert {it["provenance"] for it in d["items"]} <= {"user", "reference", "assumed", "calculated"}


def test_result_json_is_serialisable_and_matches_the_model():
    res = default_result()
    j = webgui.result_json(res, "tok")
    s = json.dumps(j)                                        # must not raise
    assert len(s) > 10_000
    assert j["glom_kg"] == res.glom_kg
    assert len(j["stages"]) == len(res.stages)
    assert len(j["ledger"]) == len(res.ledger)
    assert len(j["issues"]) == len(res.issues)
    assert j["budget_total"] == res.budget.total_mps


# ------------------------------------------------------------------ over HTTP
def test_index_and_api_over_http():
    body, _ = _get("/", raw=True)
    assert b"<title>MERLIN - launch vehicle sizing</title>" in body
    # the page is built around the configuration you are working on, so its name field is the first control
    assert b'id="name"' in body and b"Name this configuration" in body
    assert b"http://" not in body.replace(b"http://127.0.0.1", b"")   # no CDN, no external asset
    assert b"https://" not in body, "the GUI must work with no network at all"
    d = _get("/api/designs")
    assert d["designs"] and d["version"]


def test_sizing_over_http_applies_overrides():
    base = _post("/api/size", {"path": "config/default_design.yaml", "overrides": {}})
    heavy = _post("/api/size", {"path": "config/default_design.yaml",
                                "overrides": {"mission.payload_mass_kg": 12000.0}})
    assert base["converged"] and heavy["converged"]
    assert heavy["payload_kg"] == 12000.0
    assert heavy["glom_kg"] > base["glom_kg"] * 1.1          # a 20 % heavier payload must cost more than 10 %
    _SRV["token"] = base["token"]


def test_figure_report_workbook_and_yaml_endpoints():
    tok = _SRV.get("token") or _post("/api/size", {"path": "config/default_design.yaml", "overrides": {}})["token"]
    png, hdr = _get(f"/api/figure?token={tok}&key=vehicle_png", raw=True)
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and hdr["Content-Type"] == "image/png"
    rep, hdr = _get(f"/api/report?token={tok}", raw=True)
    assert b"<!DOCTYPE html>" in rep and b"Engineering method register" in rep
    xl, hdr = _get(f"/api/workbook?token={tok}", raw=True)
    assert xl[:2] == b"PK" and "spreadsheetml" in hdr["Content-Type"]
    y, _ = _get(f"/api/yaml?token={tok}", raw=True)
    assert b"overrides:" in y


def test_unknown_token_and_unknown_figure_are_reported_not_crashed():
    with pytest.raises(urllib.error.HTTPError) as e:
        _get("/api/figure?token=deadbeef&key=vehicle_png")
    assert e.value.code in (400, 404)
    tok = _SRV.get("token") or _post("/api/size", {"path": "config/default_design.yaml", "overrides": {}})["token"]
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(f"/api/figure?token={tok}&key=stage99_png")
    assert e.value.code == 404


def test_a_bad_override_returns_an_error_not_a_stack_trace_page():
    try:
        out = _post("/api/size", {"path": "config/default_design.yaml",
                                  "overrides": {"mission.nonexistent_parameter": 1.0}})
        assert "error" in out
    except urllib.error.HTTPError as ex:
        body = json.loads(ex.read())
        assert "unknown parameter path" in body["error"]


# =========================================================== everything the GUI gained in v0.13
def test_the_listing_groups_designs_so_check_cases_are_findable():
    d = _get("/api/designs")
    groups = {g["key"]: g["label"] for g in d["groups"]}
    assert "validation" in groups and "check" in groups["validation"].lower()
    assert {x["group"] for x in d["designs"]} <= set(groups)
    electron = [x for x in d["designs"] if x["path"].endswith("electron.yaml")]
    assert electron and electron[0]["group"] == "validation"
    assert electron[0]["description"], "a check case should say what vehicle it is"


def test_the_analyses_on_offer_declare_what_they_depend_on():
    studies = {s["key"]: s for s in _get("/api/designs")["studies"]}
    assert {"trajectory", "loads", "structure", "cost"} <= set(studies)
    assert studies["structure"]["needs"] == "loads"
    assert studies["loads"]["needs"] == "trajectory"
    assert studies["trajectory"]["needs"] is None


def test_asking_for_structure_runs_what_structure_needs():
    assert webgui._expand_studies(["structure"]) == {"structure", "loads", "trajectory"}
    assert webgui._expand_studies([]) == set()


def test_inputs_arrive_ready_to_render():
    d = _get("/api/design?path=config/default_design.yaml")
    assert d["meta"]["name"] and d["open_sections"]
    it = {x["path"]: x for x in d["items"]}
    assert it["mission.payload_mass_kg"]["label"] == "Payload mass"
    assert it["mission.orbit.type"]["choices"], "orbit type must arrive as a list, not a text box"
    assert it["stages[0].engine.isp_vac_s"]["section"] == "Stage 1"


def test_a_stage_value_can_actually_be_overridden():
    """The register spells stage paths with brackets; overrides must accept exactly what it hands out.

    This is the bug the GUI rebuild found: every per-stage edit failed with a bare KeyError, because the
    browser sent back the path the server gave it and deep_set only walked the dotted form.
    """
    d = _get("/api/design?path=config/default_design.yaml")
    path = next(x["path"] for x in d["items"] if x["path"].endswith("stages[0].engine.isp_vac_s"))
    base = _post("/api/size", {"path": "config/default_design.yaml", "overrides": {}})
    hotter = _post("/api/size", {"path": "config/default_design.yaml", "overrides": {path: 320.0}})
    assert hotter["stages"][0]["isp_eff_s"] != base["stages"][0]["isp_eff_s"]
    assert hotter["glom_kg"] < base["glom_kg"], "a better first-stage Isp must make the vehicle lighter"


def test_picking_a_real_engine_through_the_gui_resolves_the_database():
    out = _post("/api/size", {"path": "config/default_design.yaml",
                              "overrides": {"stages[0].engine.from_database": "RD-180"}})
    codes = {i["code"] for i in out["issues"]}
    assert "ENGDB" in codes, "the database row was not resolved"


def test_a_run_can_carry_its_analyses_and_says_which_ran():
    out = _post("/api/size", {"path": "config/default_design.yaml", "overrides": {}, "studies": ["loads"]})
    assert {"trajectory", "loads"} <= set(out["studies"]), "loads must drag the trajectory in with it"
    assert "loads" in out["study_summary"]
    s = out["study_summary"]["loads"]
    assert s["moment_kNm"] > 0 and s["governing"] and s["profiles"]
    assert "loads_png" in out["figures"]


def test_the_figures_a_run_advertises_are_all_fetchable():
    out = _post("/api/size", {"path": "config/default_design.yaml", "overrides": {}, "studies": ["trajectory"]})
    for key in out["figures"]:
        with urllib.request.urlopen(f"{_server()}/api/figure?token={out['token']}&key={key}", timeout=120) as r:
            assert r.status == 200 and r.read(8).startswith(b"\x89PNG"), key


def test_cad_downloads_come_back_as_the_format_asked_for():
    out = _post("/api/size", {"path": "config/default_design.yaml", "overrides": {}})
    for fmt, probe in (("dxf", b"SECTION"), ("obj", b"v "), ("stl", None)):
        with urllib.request.urlopen(f"{_server()}/api/cad?token={out['token']}&fmt={fmt}", timeout=180) as r:
            body = r.read()
        assert len(body) > 500, fmt
        if probe:
            assert probe in body[:4000], fmt
    # STEP is a format the tool knows about but cannot write without a geometry kernel, so the
    # refusal is 409 Conflict with the reason, not 400 "never heard of it" as it was before
    # cad_kernel existed. Either way it must not pretend to produce one.
    try:
        urllib.request.urlopen(f"{_server()}/api/cad?token={out['token']}&fmt=step", timeout=30)
        raise AssertionError("STEP cannot be produced here and must not pretend to be")
    except urllib.error.HTTPError as e:
        assert e.code == 409, f"expected 409 with the reason, got {e.code}"


def test_saving_writes_a_design_that_loads_and_keeps_its_annotations():
    import glob
    import yaml as _yaml
    from launch_vehicle.config_io import _Loader
    name = "pytest temp config"
    try:
        out = webgui.save_design(DESIGN, {"stages[0].engine.isp_vac_s": 321.0,
                                          "mission.payload_mass_kg": 11000.0},
                                 name, "written by the test suite")
        path = os.path.join(ROOT, out["path"])
        assert os.path.exists(path) and out["n_overrides"] == 2
        raw = _yaml.load(open(path), Loader=_Loader)
        leaf = raw["stages"][0]["engine"]["isp_vac_s"]
        assert leaf["v"] == 321.0
        assert leaf["t"] == "user", "a value a person typed must not keep the book's provenance"
        assert "GUI" in leaf["s"]
        assert leaf["u"] == "s" and leaf["d"], "units and description must survive the save"
        assert raw["meta"]["name"] == name
        # and it must be a design the tool can actually run
        from launch_vehicle.convergence import size_vehicle
        from launch_vehicle.config_io import load_design
        res = size_vehicle(load_design(path, ASSUMP))
        assert res.converged
    finally:
        for p in glob.glob(os.path.join(webgui.SAVE_DIR, "pytest_temp_config*.yaml")):
            os.remove(p)


def test_saving_refuses_a_nameless_configuration_and_a_bad_path():
    with pytest.raises(ConfigError, match="name"):
        webgui.save_design(DESIGN, {}, "")
    with pytest.raises(ConfigError, match="unknown parameter"):
        webgui.save_design(DESIGN, {"mission.not_a_real_field": 1.0}, "x")


def test_a_saved_name_cannot_escape_the_designs_directory():
    assert webgui._safe_name("../../etc/passwd") == "etc_passwd"
    assert webgui._safe_name("My design / v2") == "My_design_v2"
    assert webgui._safe_name("   ") == ""


# -------------------------------------------------------------------------- CAD downloads
def test_cad_format_list_offers_each_name_exactly_once():
    """Two writers claiming one name would make one of them unreachable from the GUI."""
    d = _get("/api/cad_formats")
    names = [f["fmt"] for f in d["formats"]]
    assert len(names) == len(set(names)), f"duplicate CAD format offered: {names}"
    assert {"dxf", "stl", "obj", "3mf"} <= set(names)
    faceted = {f["fmt"] for f in d["formats"] if not f["exact"]}
    exact = {f["fmt"] for f in d["formats"] if f["exact"]}
    assert faceted == {"dxf", "stl", "obj", "3mf"}
    assert exact == {"step", "brep", "gltf"}
    assert all(f["available"] for f in d["formats"] if not f["exact"]), \
        "the dependency-free formats must always be on offer"
    assert all(f["label"] for f in d["formats"]), "a button with no tooltip explains nothing"


def test_cad_format_list_states_the_facet_deficit_and_the_kernel_state():
    d = _get("/api/cad_formats")
    assert d["facet_deficit"] == pytest.approx(1.60561e-3, rel=1e-4)
    k = d["kernel"]
    assert k["available"] is False, "no kernel is installed in this environment"
    assert "cadquery" in k["reason"] and "pip install cadquery" in k["install"]
    assert all(not f["available"] for f in d["formats"] if f["exact"]), \
        "an exact format cannot be offered as available without a kernel"


def test_every_offered_faceted_format_actually_downloads():
    r = _post("/api/size", {"path": "config/default_design.yaml", "overrides": {}, "studies": []})
    magic = {"dxf": b"0\n", "stl": None, "obj": b"# ", "3mf": b"PK\x03\x04"}
    for fmt, head in magic.items():
        body, hdr = _get(f"/api/cad?token={r['token']}&fmt={fmt}", raw=True)
        assert len(body) > 1000, f"{fmt} came back empty"
        assert f"vehicle.{fmt}" in hdr["Content-Disposition"]
        if head:
            assert body.startswith(head), f"{fmt} does not start like a {fmt} file"


def test_asking_for_a_solid_format_without_a_kernel_explains_itself():
    r = _post("/api/size", {"path": "config/default_design.yaml", "overrides": {}, "studies": []})
    for fmt in ("step", "brep"):
        try:
            _get(f"/api/cad?token={r['token']}&fmt={fmt}")
            raise AssertionError(f"{fmt} should not have been served without a kernel")
        except urllib.error.HTTPError as e:
            assert e.code == 409, f"{fmt}: expected 409 Conflict, got {e.code}"
            msg = json.loads(e.read())["error"]
            assert fmt.upper() in msg and "kernel" in msg
            assert "cadquery" in msg, "the message must name what to install"


def test_an_unknown_cad_format_is_refused_not_guessed():
    r = _post("/api/size", {"path": "config/default_design.yaml", "overrides": {}, "studies": []})
    try:
        _get(f"/api/cad?token={r['token']}&fmt=iges")
        raise AssertionError("iges should have been refused")
    except urllib.error.HTTPError as e:
        assert e.code == 400 and "iges" in json.loads(e.read())["error"]


def test_the_page_builds_its_cad_buttons_from_the_server_not_a_hardcoded_list():
    """A hardcoded button list is how STEP ends up advertised on a machine without a kernel."""
    body, _ = _get("/", raw=True)
    html = body.decode()
    assert "/api/cad_formats" in html, "the page never asks what can be written"
    assert "cadButtons" in html and "cadNote" in html
    assert 'fmt=dxf' not in html, "a hardcoded format URL is left in the page"


# ------------------------------------------------------------------- Model checks tab (R18/R20/R24)
def test_model_checks_endpoint_returns_all_three_measurements():
    r = _post("/api/size", {"path": "config/default_design.yaml", "overrides": {}, "studies": []})
    d = _get(f"/api/model_checks?token={r['token']}")
    assert "reliability" in d and "engine_mer" in d and "solid_relations" in d, sorted(d)
    assert not any(k.endswith("_error") for k in d), [k for k in d if k.endswith("_error")]

    rel = d["reliability"]
    assert rel["stages"] and all(s["n_engines"] >= 1 for s in rel["stages"])
    assert 0 < rel["propulsion_reliability"] <= 1
    assert "common-cause" in rel["independence_caveat"], "the caveat must travel with the number"

    em = d["engine_mer"]
    assert em["n"] >= 16 and em["rows"]
    assert "BIASED LOW" in em["verdict"]
    assert 1.1 < em["calibration_factor"] < 1.4

    sr = d["solid_relations"]
    assert len(sr) >= 8 and d["solid_dataset_n"] == 34
    for x in sr:
        assert x["predicts"] in ("stage", "motor") and x["our_mape"] is not None
        # each relation must say which population its score was measured against: a motor relation scored
        # against stage data would be charged for skirts and avionics it never claimed to predict
        assert x["scored_against"] == ("motor" if x["predicts"] == "motor" else "stage")
    assert any(x["predicts"] == "motor" for x in sr), "the motor-level relation is missing"


def test_the_page_has_a_model_checks_tab_that_fetches_it():
    """The tab is hidden from the tab bar since v1.1 (HIDDEN_TABS) but its code and route are kept, so that it
    can come back by deleting one name."""
    body, _ = _get("/", raw=True)
    html = body.decode()
    assert '["model", "Model checks"]' in html, "the tab is not registered"
    assert "/api/model_checks" in html, "the tab never asks the server for anything"
    for probe in ("Engine-out and cluster reliability", "Engine-mass relation against real engines",
                  "Solid-stage inert relations"):
        assert probe in html, f"the tab does not render {probe!r}"


def test_the_new_check_cases_are_offered_in_the_open_dialog():
    """A check case nobody can load from the GUI is a file, not a feature."""
    names = {d["name"] for d in webgui.list_designs()}
    for want in ("VAL-H-IIA-202", "VAL-Soyuz-2.1b", "VAL-DeltaIVHeavy"):
        assert want in names, f"{want} is missing from the GUI design list"
    groups = {d["name"]: d.get("group") for d in webgui.list_designs()}
    assert groups["VAL-H-IIA-202"] == "validation"


def test_every_new_engine_reaches_the_gui_dropdown():
    import yaml
    from launch_vehicle import gui_meta as M
    from launch_vehicle.config_io import _Loader
    with open(ASSUMP, encoding="utf-8") as fh:
        a = yaml.load(fh, Loader=_Loader)
    offered = {v for v, _ in M.choices_for("stages.0.engine.from_database", M.library_choices(a))}
    for want in ("LE-7A", "LE-5B", "RD-107A", "RD-108A", "RD-0124", "RD-191", "BE-4"):
        assert want in offered, f"{want} is in the database but not selectable in the GUI"


# ------------------------------------------------------------------ the study vocabulary
# Three defects found in the v0.22 release audit, all with the same shape: a checkbox in the browser that
# silently produced nothing. None of them raised an error, so only an explicit check catches them.

def test_every_study_the_gui_offers_is_a_key_the_engine_actually_gates_on():
    """The browser's vocabulary must translate to the engine's, or a tick runs nothing.

    `ascent_optimum` is the key the RESULT comes back under; the engine asks for `optimise_ascent`. Sending
    the result key through to main._studies matched no gate at all.
    """
    import re
    import inspect
    from launch_vehicle import main as lvmain
    src = inspect.getsource(lvmain._studies)
    gates = set(re.findall(r'"([a-z_]+)" in want', src))
    # stability is produced as a by-product of a converged trajectory rather than having its own gate
    by_product = {"stability"}
    for key, label, _needs in webgui.STUDIES:
        engine_key = webgui.ENGINE_STUDY_KEY.get(key, key)
        assert engine_key in gates or key in by_product, (
            f"the GUI offers {label!r} as {key!r}, which maps to {engine_key!r}, but main._studies gates on "
            f"{sorted(gates)} - ticking it would run nothing")


def test_a_study_that_is_only_a_by_product_declares_its_dependency():
    """Stability needs a converged trajectory; asking for it alone used to produce nothing."""
    needs = {k: n for k, _l, n in webgui.STUDIES}
    assert needs["stability"] == "trajectory"
    assert "trajectory" in webgui._expand_studies(["stability"])


def test_expanding_studies_then_translating_gives_the_engine_what_it_wants():
    engine = webgui._engine_studies(webgui._expand_studies(["ascent_optimum", "stability", "structure"]))
    assert "optimise_ascent" in engine, engine
    assert "trajectory" in engine and "loads" in engine, engine
    assert "ascent_optimum" not in engine, "the result key must not be sent to the engine"


def test_every_declared_dependency_is_itself_a_study():
    keys = {k for k, _l, _n in webgui.STUDIES}
    for key, _label, needs in webgui.STUDIES:
        assert needs is None or needs in keys, f"{key} depends on {needs}, which is not a study"


# ------------------------------------------------------------------ trade studies, comparison, PDF
# Three engine features that were command-line only until the v0.22 release audit. The risk in exposing them
# through the browser is that the GUI grows its own opinion of what a study is; these pin it to the CLI's.

def test_the_trade_study_listing_finds_declared_sweeps_and_nothing_else():
    found = webgui.trade_study_files()
    paths = [t["path"] for t in found]
    assert "examples/example_trade_study.yaml" in paths, paths
    for t in found:
        assert t["n_sweeps"] >= 1 and t["name"]
    # an ordinary design has no trade_study: block and must not be offered as one
    assert "config/default_design.yaml" not in paths


def test_a_design_without_a_sweep_is_refused_with_a_reason():
    import json as _json
    import urllib.error
    import urllib.request
    req = urllib.request.Request(_server() + "/api/trade", method="POST",
                                 data=_json.dumps({"path": "config/default_design.yaml"}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=120)
        raise AssertionError("a design with no trade_study: block should be refused")
    except urllib.error.HTTPError as ex:
        assert ex.code == 400
        assert "trade_study" in _json.loads(ex.read())["error"]


def test_comparing_fewer_than_two_designs_is_refused():
    import json as _json
    import urllib.error
    import urllib.request
    req = urllib.request.Request(_server() + "/api/compare", method="POST",
                                 data=_json.dumps({"paths": ["config/default_design.yaml"]}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=120)
        raise AssertionError("one design is not a comparison")
    except urllib.error.HTTPError as ex:
        assert ex.code == 400
        assert "two" in _json.loads(ex.read())["error"]


def test_a_comparison_payload_is_json_and_keeps_failed_cases():
    """A case that did not converge keeps its row, so a sweep never looks healthier than it was."""
    import json as _json
    import tempfile
    from launch_vehicle import studies
    study = studies.compare_designs(["config/default_design.yaml", "examples/example_solid_smallsat.yaml"],
                                    webgui.DEFAULT_ASSUMPTIONS)
    p = webgui._study_payload(study, tempfile.mkdtemp())
    _json.dumps(p)                                        # must survive the socket
    assert p["kind"] == "comparison"
    assert p["n_cases"] == 2 and len(p["rows"]) == 2
    assert p["header"][0] == "Case" and p["header"][-1] == "Status"
    assert all(len(r) == len(p["header"]) for r in p["rows"]), "every row must match the header width"
    # NaN is not JSON; a missing number must arrive as null, not as the string "NaN"
    for r in p["rows"]:
        for cell in r:
            assert not (isinstance(cell, float) and cell != cell)
    assert p["csv"].endswith(".csv") and p["html"].endswith(".html")


# ------------------------------------------------------------------ the stage count, over HTTP
def test_the_design_payload_reports_the_stage_count_and_its_bounds():
    """The count is not a leaf in the file - it is the length of the stages list - so the page cannot read it
    off an input row. It comes from the server, with the same bounds the server enforces."""
    from launch_vehicle import stage_count as sc
    d = _get("/api/design?path=config/default_design.yaml")
    assert d["stage_count"]["n"] == 2
    assert d["stage_count"]["min"] == sc.MIN_STAGES
    assert d["stage_count"]["max"] == sc.MAX_STAGES


def test_changing_the_stage_count_returns_a_draft_that_loads_with_that_many_stages():
    out = _post("/api/stage_count", {"path": "config/default_design.yaml", "count": 3})
    assert out["draft"] is True
    assert out["note"]["changed"] is True and out["note"]["now"] == 3
    again = _get("/api/design?path=" + out["path"])
    assert again["stage_count"]["n"] == 3
    # the added stage has real input rows of its own, which is the whole point of the control
    assert any(i["path"].startswith("stages[2].") for i in again["items"])


def test_asking_for_the_count_it_already_has_changes_nothing_and_writes_no_draft():
    out = _post("/api/stage_count", {"path": "config/default_design.yaml", "count": 2})
    assert out["draft"] is False and out["note"]["changed"] is False


def test_an_impossible_stage_count_is_refused_over_http_and_names_the_field():
    try:
        _post("/api/stage_count", {"path": "config/default_design.yaml", "count": 99})
    except urllib.error.HTTPError as ex:
        body = json.loads(ex.read())
        assert ex.code == 400
        assert body["field"] == "stage_count"
        assert "99" in body["error"]
    else:
        raise AssertionError("99 stages was accepted")


def test_unsaved_edits_survive_a_change_of_stage_count():
    """Changing the count is a document rewrite, so the user's in-progress overrides have to travel with it
    or the control would silently discard everything they had typed."""
    out = _post("/api/stage_count", {"path": "config/default_design.yaml", "count": 3,
                                     "overrides": {"mission.payload_mass_kg": 1234.0}})
    d = _get("/api/design?path=" + out["path"])
    payload = [i for i in d["items"] if i["path"] == "mission.payload_mass_kg"]
    assert payload and payload[0]["value"] == 1234.0, "an override was lost changing the stage count"


def test_a_blank_field_is_handed_back_rather_than_written_into_the_draft():
    """A half-filled brief has deliberate blanks, and a document with a blank required field does not load -
    so the draft cannot carry them. They come back for the page to re-apply."""
    out = _post("/api/stage_count", {"path": "config/default_design.yaml", "count": 3,
                                     "overrides": {"mission.payload_mass_kg": None}})
    assert "mission.payload_mass_kg" in (out["keep_overrides"] or {})
    _get("/api/design?path=" + out["path"])          # the draft itself still loads


def test_the_page_offers_the_stage_count_control():
    body, _h = _get("/", raw=True)
    assert b"/api/stage_count" in body, "the page cannot change the stage count"
    assert b"Number of stages" in body, "the control has no label the user can find"


# ------------------------------------------------------------------ strap-on boosters, over HTTP
def test_the_design_payload_says_whether_the_design_has_boosters():
    assert _get("/api/design?path=config/default_design.yaml")["boosters"]["kind"] is None
    a = _get("/api/design?path=validation/ariane5_eca.yaml")["boosters"]
    assert a["kind"] == "solid"
    assert set(a["kinds"]) == {"solid", "liquid"}


def test_fitting_boosters_returns_a_draft_whose_booster_fields_are_editable():
    out = _post("/api/boosters", {"path": "config/default_design.yaml", "kind": "solid"})
    assert out["draft"] is True and out["note"]["now"] == "solid"
    d = _get("/api/design?path=" + out["path"])
    assert d["boosters"]["kind"] == "solid"
    fields = [i["path"] for i in d["items"] if i["path"].startswith("boosters.")]
    assert len(fields) > 20, f"only {len(fields)} booster fields reached the page"
    assert "boosters.n_total" in fields and "boosters.propellant_mass_each_kg" in fields


def test_taking_the_boosters_off_removes_every_booster_field():
    out = _post("/api/boosters", {"path": "validation/ariane5_eca.yaml", "kind": None})
    assert out["draft"] is True and out["note"]["now"] is None
    d = _get("/api/design?path=" + out["path"])
    assert d["boosters"]["kind"] is None
    assert not [i for i in d["items"] if i["path"].startswith("boosters.")]


def test_asking_for_the_boosters_it_already_has_writes_no_draft():
    out = _post("/api/boosters", {"path": "validation/ariane5_eca.yaml", "kind": "solid"})
    assert out["draft"] is False and out["note"]["changed"] is False


def test_an_unknown_booster_kind_is_refused_over_http_and_names_the_field():
    try:
        _post("/api/boosters", {"path": "config/default_design.yaml", "kind": "nuclear"})
    except urllib.error.HTTPError as ex:
        body = json.loads(ex.read())
        assert ex.code == 400 and body["field"] == "boosters.type"
    else:
        raise AssertionError("'nuclear' was accepted as a booster kind")


def test_unsaved_edits_survive_fitting_boosters():
    out = _post("/api/boosters", {"path": "config/default_design.yaml", "kind": "liquid",
                                  "overrides": {"mission.payload_mass_kg": 2468.0}})
    d = _get("/api/design?path=" + out["path"])
    payload = [i for i in d["items"] if i["path"] == "mission.payload_mass_kg"]
    assert payload and payload[0]["value"] == 2468.0


def test_the_page_offers_the_booster_control():
    body, _h = _get("/", raw=True)
    assert b"/api/boosters" in body, "the page cannot fit or remove boosters"
    assert b"Strap-on boosters" in body, "the control has no label the user can find"


# ------------------------------------------------------------------ architecture trades (M102, R35)
def test_architecture_endpoint_pins_the_stages_and_varies_the_count():
    """The pinned sweep reachable from the browser. The reference row must come back to the design's own
    payload, or the endpoint is not running the same model the CLI does."""
    out = _post("/api/architecture", {"path": "validation/ariane64.yaml", "counts": [2, 4]})
    assert out["mode"] == "pinned"
    assert out["reference"]["n_boosters"] == 4
    rows = {r["n_boosters"]: r for r in out["rows"]}
    assert rows[4]["is_reference"] and rows[4]["flyable"]
    assert rows[4]["payload_kg"] == pytest.approx(out["reference"]["payload_kg"], rel=5e-3)
    assert rows[2]["payload_kg"] < rows[4]["payload_kg"]
    assert rows[2]["liftoff_tw"] > 1.0


def test_architecture_endpoint_carries_the_measured_bias_with_the_numbers():
    """A payload curve shown without its measured bias would read as a capability. The caveat ships with the
    data, not in the documentation only."""
    out = _post("/api/architecture", {"path": "validation/h3_24l.yaml", "counts": [4]})
    assert "NOT re-sized" in out["caveat"]
    assert "6b.5" in out["caveat"]


def test_architecture_endpoint_refuses_a_count_that_cannot_lift_off():
    out = _post("/api/architecture", {"path": "validation/ariane64.yaml", "counts": [0]})
    row = out["rows"][0]
    assert not row["flyable"]
    assert row["payload_kg"] is None
    assert row["dv_limited_payload_kg"] > 0
    assert "cannot leave the pad" in row["reason"]


def test_architecture_endpoint_rejects_a_serial_design_and_bad_counts():
    with pytest.raises(urllib.error.HTTPError) as e:
        _post("/api/architecture", {"path": "validation/vega.yaml", "counts": [2]})
    assert e.value.code == 400
    assert "no strap-on" in json.loads(e.value.read())["error"]
    with pytest.raises(urllib.error.HTTPError) as e:
        _post("/api/architecture", {"path": "validation/ariane64.yaml", "counts": [-1]})
    assert e.value.code == 400


def test_architecture_endpoint_can_resize_the_core_instead():
    """The other direction: more strap-ons, smaller core, same payload."""
    out = _post("/api/architecture", {"path": "validation/h2a_202.yaml", "counts": [2, 4],
                                      "size_core": True})
    assert out["mode"] == "size_core"
    rows = {r["n_boosters"]: r for r in out["rows"] if r["flyable"]}
    assert rows[4]["core_prop_kg"] < rows[2]["core_prop_kg"]
    assert rows[4]["payload_kg"] == rows[2]["payload_kg"] == out["payload_kg"]


# ------------------------------------------------------------------ families (R37)
def test_families_endpoint_lists_the_shipped_families_with_their_variants():
    out = _post("/api/families", {})
    fams = {f["slug"]: f for f in out["families"]}
    assert {"delta_ii", "ariane_6"} <= set(fams)
    d = fams["delta_ii"]
    assert d["reference"] == "7920" and len(d["variants"]) == 3
    assert d["base"] == "validation/delta2_7920.yaml"
    by = {v["key"]: v for v in d["variants"]}
    assert [by[k]["n_boosters"] for k in ("7320", "7420", "7920")] == [3, 4, 9]
    assert by["7320"]["published_payload_kg"] == 2800.0
    assert by["7320"]["published_source"].strip(), "a published figure must arrive with its source"
    # a variant is the base design plus overrides, which is exactly what /api/design already takes,
    # so the browser can open one with no new machinery
    assert by["7320"]["overrides"]["boosters.n_total"] == 3


def test_families_endpoint_sizes_a_family_and_scores_it_against_published_mass():
    out = _post("/api/families", {"name": "delta_ii", "pinned": True})
    sized = {r["key"]: r for r in out["sized"]}
    assert len(sized) == 3 and all(not r["error"] for r in sized.values())
    assert sized["7320"]["glom_err"] < sized["7920"]["glom_err"], \
        "the shared-core error must shrink as the variant grows"
    pinned = {r["key"]: r for r in out["pinned"]}
    assert pinned["7320"]["payload_err"] > 0 > sized["7320"]["glom_err"], \
        "the two methods must err in opposite directions; that is the finding the panel reports"
    assert "OPPOSITE" in out["caveat"]


def test_families_endpoint_rejects_an_unknown_family():
    with pytest.raises(urllib.error.HTTPError) as e:
        _post("/api/families", {"name": "not_a_family"})
    assert e.value.code == 400
    assert "no family" in json.loads(e.value.read())["error"]


# ------------------------------------------------------------------ the page itself
def _index_html():
    with open(os.path.join(ROOT, "src", "launch_vehicle", "gui_static", "index.html"),
              encoding="utf-8") as fh:
        return fh.read()


def _index_script():
    import re
    html = _index_html()
    blocks = re.findall(r"<script[^>]*>(.*?)</script>", html, re.S)
    assert blocks, "index.html has no script block"
    return max(blocks, key=len)


def test_every_tab_the_page_offers_has_something_that_draws_it():
    """Nothing checked this before, so a tab could be listed and then draw the empty "nothing sized yet"
    panel for ever - which is what the Architecture tab did between being written and being wired up."""
    import re
    js = _index_script()
    tabs = re.search(r"function TABS\(\)\s*\{(.*?)\n\}", js, re.S).group(1)
    listed = set(re.findall(r'\["([a-z_]+)",\s*"', tabs))
    study = set(re.findall(r"^\s*([a-z_]+):\s*\[\"", js, re.M))
    drawn = set(re.findall(r'S\.tab === "([a-z_]+)"', js))
    # a tab is drawn either by its own branch in render() or by the generic study-figure path
    for t in sorted(listed):
        assert t in drawn or t in study or re.search(r'case "%s"' % t, js) \
            or re.search(r'render%s\b' % t.capitalize(), js), \
            f'the page offers a "{t}" tab but nothing in render() draws it'
    assert "architecture" in listed and "architecture" in drawn


def test_the_architecture_panel_calls_endpoints_the_server_actually_serves():
    """A typo in a fetch URL is invisible until someone clicks the button, and the click is the one thing a
    test suite never does. Every /api/... the page names must exist in webgui.py."""
    import re
    js = _index_script()
    with open(os.path.join(ROOT, "src", "launch_vehicle", "webgui.py"), encoding="utf-8") as fh:
        server = fh.read()
    called = set(re.findall(r'"(/api/[a-z_]+)"', js))
    assert {"/api/architecture", "/api/families"} <= called, \
        "the architecture panel must reach both new endpoints"
    for path in sorted(called):
        assert f'u.path == "{path}"' in server, f"the page calls {path}, which the server does not serve"


def test_the_pages_javascript_parses():
    """`node --check` when node is available: brace counting cannot tell a syntax error from a string."""
    import shutil
    import subprocess
    import tempfile
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed, so the page's script cannot be parsed here")
    p = os.path.join(tempfile.mkdtemp(), "page.js")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(_index_script())
    r = subprocess.run([node, "--check", p], capture_output=True, text=True)
    assert r.returncode == 0, f"index.html's script does not parse:\n{r.stderr}"


def test_the_drag_model_dropdown_is_never_folded_away_and_only_its_own_inputs_show():
    """v1.1 tagged the drag model `assumed`, and the page folds assumed values away, so the dropdown vanished
    while the fixed Cd and the Mach table - inputs of models that were not selected - sat in view. The page
    script cannot be run here without node, so this pins the rule's two halves in the source and checks that
    every input the rule names is one the design really has."""
    import re as _re
    from launch_vehicle import paths as _paths
    with open(os.path.join(os.path.dirname(webgui.__file__), "gui_static", "index.html"), encoding="utf-8") as fh:
        page = fh.read()
    assert "MODEL_FIELD_RE.test(r.path) || dragInputFor(r.path) === drag" in page
    assert "if (needs && needs !== drag) continue;" in page
    block = _re.search(r"const DRAG_INPUT_MODEL = \{(.*?)\};", page, _re.S).group(1)
    named = dict(_re.findall(r'(\w+): "(\w+)"', block))
    out = webgui.design_inputs(os.path.join(_paths.ROOT, "config", "default_design.yaml"),
                               os.path.join(_paths.ROOT, "config", "engineering_assumptions.yaml"))
    items = out["items"] if isinstance(out, dict) else out
    aero_inputs = {i["path"].rsplit(".", 1)[1]: i for i in items if i["path"].startswith("mission.aerodynamics.")}
    assert set(named) <= set(aero_inputs), set(named) - set(aero_inputs)
    from launch_vehicle import gui_meta as _meta
    models = {value for value, _label in _meta.STATIC_CHOICES["mission.aerodynamics.drag_model"]}
    assert set(named.values()) <= models
    assert models == {"geometry", "book_titan2", "table", "constant"}


def test_the_hidden_tabs_are_hidden_and_nothing_else_is():
    with open(os.path.join(os.path.dirname(webgui.__file__), "gui_static", "index.html"), encoding="utf-8") as fh:
        page = fh.read()
    assert 'const HIDDEN_TABS = ["architecture", "model", "dropzones"];' in page
    assert page.count("HIDDEN_INPUTS.includes(it.path)") == 2, "the longitude is neither shown nor asked for"
    assert "base = base.filter(t => !HIDDEN_TABS.includes(t[0]));" in page


def test_the_velocity_budget_bars_can_draw():
    """The fill of each bar is a <span>. An inline span ignores width and height, so for as long as the rule
    lacked display:block every bar was an empty grey track and the chart showed nothing."""
    with open(os.path.join(os.path.dirname(webgui.__file__), "gui_static", "index.html"), encoding="utf-8") as fh:
        page = fh.read()
    assert ".bar .fl{display:block;" in page


# ------------------------------------------------------------------ errors that point at a field
def _items(design):
    out = webgui.design_inputs(os.path.join(ROOT, design), os.path.join(ROOT, "config", "engineering_assumptions.yaml"),
                               describe=True)
    return {i["path"] for i in out["items"]}


def test_every_check_code_points_at_an_input_the_page_has():
    """A message that names no field can only be printed. Every code in the map must resolve to a path that
    exists in a design of the kind it is about, or the "go to this field" button would go nowhere."""
    from launch_vehicle import validation as V
    liquid, boost, solid = (_items(d) for d in ("config/default_design.yaml", "examples/example_boosters.yaml",
                                                "examples/example_solid_smallsat.yaml"))
    everything = liquid | boost | solid
    for code, tmpl in V._CODE_FIELD.items():
        for variant, msg in ((0, "stage 1: something is wrong"), (1, "stage 1 (solid): something is wrong")):
            if not isinstance(tmpl, tuple) and variant:
                continue
            got = V.infer_field(code, msg)
            if variant and code.startswith("ENGDB"):
                continue        # raised only for a motor that names a database entry, which no shipped design does
            assert got in everything, (code, got)
    assert V.infer_field("ISP", "stage 2 (solid): vacuum Isp must be positive") == "stages[1].motor.isp_vac_s"
    assert V.infer_field("ENGDBOVR", "stages.0.engine: 'RD-180' gives isp") == "stages[0].engine.from_database"
    assert V.infer_field("DIAM", "diameter must be positive") is None, "no stage named, so no field guessed"
    assert V.infer_field("NOSUCH", "nothing recognisable") is None
    assert V.infer_field(None, "stage 2: geometry_method 'book_mer' needs cstar_mps") == "stages[1].engine.cstar_mps"


def test_choosing_the_book_engine_geometry_leads_to_the_field_it_needs_and_two_ways_out():
    from launch_vehicle.config_io import load_design
    from launch_vehicle.convergence import size_vehicle
    from launch_vehicle.validation import InputError
    assump = os.path.join(ROOT, "config", "engineering_assumptions.yaml")
    design = os.path.join(ROOT, "config", "default_design.yaml")
    with pytest.raises(InputError) as e:
        size_vehicle(load_design(design, assump, {"stages.0.engine.geometry_method": "book_mer"}))
    assert e.value.field == "stages[0].engine.cstar_mps"
    labels = [o["label"] for o in e.value.options]
    assert any("library" in x and "1,804" in x for x in labels) and any("myself" in x for x in labels)
    for o in e.value.options:                       # each way out, applied, must actually run
        r = size_vehicle(load_design(design, assump, {"stages.0.engine.geometry_method": "book_mer",
                                                      o["path"]: o["value"]}))
        assert r.glom_kg > 0


def test_a_characteristic_velocity_typed_in_the_page_is_saved_as_a_full_annotated_leaf():
    import yaml
    from launch_vehicle.config_io import _Loader, ConfigError as _CE, deep_set
    with open(os.path.join(ROOT, "config", "default_design.yaml"), encoding="utf-8") as fh:
        raw = yaml.load(fh, Loader=_Loader)
    assert "cstar_mps" not in raw["stages"][0]["engine"]
    webgui.apply_overrides(raw, {"stages[0].engine.cstar_mps": 1750.0})
    leaf = raw["stages"][0]["engine"]["cstar_mps"]
    assert leaf["v"] == 1750.0 and leaf["u"] == "m/s" and leaf["t"] == "user" and leaf["d"]
    with pytest.raises(_CE):
        webgui.apply_overrides(raw, {"stages[0].engine.no_such_input": 1.0})
    with pytest.raises(_CE):
        deep_set({"stages": [{"engine": {}}]}, "stages.0.engine.no_such_input", 1.0)


# ------------------------------------------------------------------ every real engine, picked and sized
def _pick_overrides(engine_name, entry, items, stage=0):
    """What the page writes when an engine is picked (index.html applyCascade), reproduced for the server:
    every figure the source gives, the stage's propellants and mixture ratio, the engine's mass with the
    method that reads it - and not the thrust, because the default stages set theirs from a ratio."""
    have = {i["path"] for i in items}
    out = {f"stages[{stage}].engine.from_database": engine_name}
    for prefix, leaves in ((f"stages[{stage}].engine.", entry["engine"]), (f"stages[{stage}].", entry["stage"])):
        for leaf, v in leaves.items():
            if v is None or leaf.startswith("thrust_vac_") or prefix + leaf not in have:
                continue
            out[prefix + leaf] = v
    if entry["engine"].get("mass_user_per_engine_kg") is not None:
        out[f"stages[{stage}].engine.mass_method"] = "user"
    return out


def test_every_real_engine_either_sizes_or_stops_at_a_field_the_page_can_show():
    """The owner picked BE-4 and RD-253 and got two errors, one whose "Go to" button did nothing and one that
    named no field at all. This picks every liquid engine in the database onto stage 1 of the default design,
    applies the fixes each error offers as the user would, and requires that it ends either sized or at an
    error naming an input the page has and is showing."""
    from launch_vehicle import gui_meta
    from launch_vehicle.config_io import load_design
    from launch_vehicle.convergence import size_vehicle, SizingError
    from launch_vehicle.validation import InputError
    assump = os.path.join(ROOT, "config", "engineering_assumptions.yaml")
    design = os.path.join(ROOT, "config", "default_design.yaml")
    items = webgui.design_inputs(design, assump, describe=True)["items"]
    by_path = {i["path"]: i for i in items}
    engines = {n: e for n, e in gui_meta.engine_map().items() if e["kind"] != "solid"}
    assert len(engines) >= 30
    sized, stopped = [], {}
    for name, entry in engines.items():
        ov = _pick_overrides(name, entry, items)
        for _attempt in range(6):
            try:
                size_vehicle(load_design(design, assump, dict(ov)), keep_history=False)
                sized.append(name)
                break
            except (InputError, SizingError) as ex:
                field = getattr(ex, "field", None)
                assert field in by_path, f"{name}: an error that points nowhere: {ex}"
                sw = by_path[field].get("shown_when")
                if sw:
                    now = ov.get(sw["path"], by_path[sw["path"]]["value"])
                    assert now in sw["values"], f"{name}: the error points at a field the page is hiding: {field}"
                ways = [o for o in (getattr(ex, "options", None) or []) if o.get("path") in by_path]
                if not ways:
                    stopped[name] = field
                    break
                for o in ways:
                    ov[o["path"]] = o["value"]
        else:
            raise AssertionError(f"{name}: still failing after six rounds of the offered fixes")
    assert len(sized) >= 30, (len(sized), stopped)
    # the one that cannot be finished without a number only the user has: an Isp its source does not publish
    assert stopped == {"Gamma-2": "stages[0].engine.isp_sl_s"}, stopped


def test_a_propellant_with_no_tank_coefficient_is_refused_before_sizing_with_a_fix_for_each_tank():
    from launch_vehicle.config_io import load_design
    from launch_vehicle.convergence import size_vehicle
    from launch_vehicle.validation import InputError
    assump = os.path.join(ROOT, "config", "engineering_assumptions.yaml")
    design = os.path.join(ROOT, "config", "default_design.yaml")
    ov = {"stages.0.fuel": "UDMH", "stages.0.oxidizer": "N2O4"}
    with pytest.raises(InputError) as e:
        size_vehicle(load_design(design, assump, ov))
    assert "TANKMER" in str(e.value) and e.value.field == "stages[0].tank.mass_method_fuel"
    paths = {o["path"] for o in e.value.options}
    assert paths == {"stages[0].tank.mass_method_fuel", "stages[0].tank.mass_method_oxidizer"}, \
        "both tanks need another method, so both must be offered - not only the first error's"
    ov.update({"stages.0.tank.mass_method_fuel": "akin_volume", "stages.0.tank.mass_method_oxidizer": "akin_volume"})
    assert size_vehicle(load_design(design, assump, ov)).glom_kg > 0


def test_sea_level_isp_above_vacuum_says_the_numbers_and_which_one_the_database_left():
    from launch_vehicle.config_io import load_design
    from launch_vehicle.convergence import size_vehicle
    from launch_vehicle.validation import InputError
    assump = os.path.join(ROOT, "config", "engineering_assumptions.yaml")
    design = os.path.join(ROOT, "config", "default_design.yaml")
    # the F-1 row gives a sea-level Isp (263 s) and no vacuum one; a design vacuum figure below it must be
    # reported as the design's own leftover, with both numbers
    with pytest.raises(InputError) as e:
        size_vehicle(load_design(design, assump, {"stages.0.engine.from_database": "F-1",
                                                   "stages.0.engine.isp_sl_s": None,
                                                   "stages.0.engine.isp_vac_s": 250.0}))
    msg = str(e.value)
    assert "263 s" in msg and "250 s" in msg and "no vacuum one" in msg
    assert e.value.field == "stages[0].engine.isp_vac_s"
    with pytest.raises(InputError) as e:
        size_vehicle(load_design(design, assump, {"stages.0.engine.isp_sl_s": 320.0}))
    assert e.value.field == "stages[0].engine.isp_vac_s" and "database" not in str(e.value)


def test_go_to_opens_every_fold_above_the_field():
    """ "Go to Vacuum specific impulse" did nothing: the row sat in the closed "assumed or unused" fold, and
    scrolling to an element that is not drawn does nothing."""
    with open(os.path.join(os.path.dirname(webgui.__file__), "gui_static", "index.html"), encoding="utf-8") as fh:
        page = fh.read()
    assert 'if (n.tagName === "DETAILS") n.open = true;' in page
    assert "!!S.rowNotes[r.path]" in page, "a row the page has just written a note on must not be folded away"


def test_the_be4_isp_is_recorded_as_vacuum_and_the_row_says_why():
    """The page it comes from gives one Isp, 340 s, with no altitude. Until v1.1 the row called it sea-level,
    which made BE-4 unusable on a first stage (sea-level above the design's vacuum figure) and is not what the
    only source stating a condition says. It is a reading of an ambiguous number either way, so the row must
    keep saying so."""
    from launch_vehicle import engine_db
    row = engine_db.find("BE-4")
    assert row["isp_vac_s"] == 340.0 and row["isp_sl_s"] is None
    assert row["confidence"] == "approximate"
    src = row["source"]
    assert "NOT a verified one" in src and "carries no" in src and "310 s is not adopted" in src


# ------------------------------------------------------------------ v1.1 user feedback: sorting, grouping, wording
def _page():
    with open(os.path.join(os.path.dirname(webgui.__file__), "gui_static", "index.html"), encoding="utf-8") as fh:
        return fh.read()


def test_every_results_table_sorts_and_keeps_its_totals_at_the_bottom():
    page = _page()
    assert "function sortKey(c)" in page and "const sortable = body.length >= 3;" in page
    assert '/\\b(sum|small)\\b/.test(r.cls' in page, "a total row must not be sorted into the middle"
    assert "for (const r of order.concat(fixed))" in page


def test_the_mass_ledger_filters_by_stage_and_group_and_can_leave_out_propellant():
    page = _page()
    for probe in ("S.ledgerFilter", '" leave out propellant"', '"% shown", "% lift-off"', '"Total shown at lift-off"'):
        assert probe in page, probe


def test_a_grouped_choice_list_is_drawn_with_headings():
    assert 'box = el("optgroup", {label: grp})' in _page()


def test_the_earth_rotation_and_wind_fields_say_what_they_do():
    from launch_vehicle import gui_meta as M
    assert M.label_for("mission.launch_site.include_earth_rotation") == "Include Earth's rotation"
    assert "air loads" in M.label_for("mission.wind.profile")
    items = webgui.design_inputs(os.path.join(ROOT, "config", "default_design.yaml"),
                                 os.path.join(ROOT, "config", "engineering_assumptions.yaml"))["items"]
    d = {i["path"]: i["description"] for i in items}
    assert "ONLY by the ground and flight loads" in d["mission.wind.profile"]
    assert "does not change the sizing" in d["mission.wind.profile"]
    assert d["mission.launch_site.include_earth_rotation"].startswith("Include Earth's rotation")


def test_the_ledger_names_the_parts_that_belong_to_no_stage():
    """The fairing showed as "stage -1" and the payload as a dash: the ledger's internal numbers, printed raw."""
    page = _page()
    assert '{0: "Payload", "-1": "Fairing", "-2": "Boosters"}' in page
    assert "stageName(i.stage), i.group" in page and "i.stage || " not in page
    from launch_vehicle import report
    import inspect
    src = inspect.getsource(report)
    assert 'where = {0: "payload", -1: "fairing", -2: "boosters"}' in src and 'else "upper"' not in src


def test_a_site_that_moves_the_inclination_says_so_in_plain_words_on_both_fields():
    page = _page()
    assert "cannot reach an orbit tilted less than" in page and "(a dog-leg), which this tool does not model." in page
    assert "flying straight up" not in page
    assert "S.rowNotes[incPath] = `Changed from ${was} deg" in page
    assert "below that floor" not in page


def test_table_columns_of_words_sort_alphabetically():
    """Stripping the letters off a word left "", which JavaScript reads as 0, so every name tied. A cell is a number
    only if it has digits; a column of words goes A to Z on the first click."""
    page = _page()
    assert "function sortCompare(x, y)" in page and "const d = sortCompare(x, y);" in page
    assert "numeric: true" in page, "Stage 2 goes before Stage 10"
    assert 'const first = words ? "asc" : "desc"' in page
    assert "{txt: t.toLowerCase()}" not in page


def test_the_cost_tab_is_offered_only_with_the_cost_analysis_and_recosts_without_resizing():
    page = _page()
    assert "function costTab(v, c)" in page and 'cost: ["cost", "Cost", null]' in page
    assert 'it.path.startsWith("mission.cost.")' in page, "its settings are on the tab, not in the input list"
    plain = _post("/api/size", {"path": "config/default_design.yaml", "overrides": {}, "studies": []})
    assert "cost" not in plain["studies"]
    r = _post("/api/size", {"path": "config/default_design.yaml", "overrides": {}, "studies": ["cost"]})
    c = r["study_summary"]["cost"]
    assert c["development_wyr"] > 1000 and c["flight_wyr"] > 10
    assert sum(e["share"] for e in c["elements"]) == pytest.approx(1.0)
    c2 = _post("/api/cost", {"token": r["token"], "year": 2006, "inputs": {"launch_rate": 12}})
    assert c2["flight_wyr"] < c["flight_wyr"] and c2["work_year_usd"] == 246_000
    assert c2["development_wyr"] == pytest.approx(c["development_wyr"])
    with urllib.request.urlopen(f"{_server()}/api/report?token={r['token']}", timeout=120) as rep:
        assert "246,000" in rep.read().decode("utf-8"), "the report follows the settings"
    for bad in ({"launch_rate": -1}, {"nonsense": 1}):
        with pytest.raises(urllib.error.HTTPError) as e:
            _post("/api/cost", {"token": r["token"], "year": 2010, "inputs": bad})
        assert e.value.code == 400


def test_cost_settings_are_saved_with_the_design():
    import yaml
    from launch_vehicle.config_io import load_design, _Loader
    out = webgui.save_design(os.path.join(ROOT, "config", "default_design.yaml"),
                             {"mission.cost.launch_rate": 9.0, "mission.cost.stage1_engine_existing": True},
                             "cost settings test", filename="zz_cost_settings_test", replace=True)
    path = os.path.join(ROOT, out["path"])
    try:
        with open(path, encoding="utf-8") as fh:
            leaf = yaml.load(fh, Loader=_Loader)["mission"]["cost"]["launch_rate"]
        assert leaf["v"] == 9.0 and leaf["t"] == "user" and leaf["d"] and leaf["u"] == "1/yr"
        assert load_design(path, webgui.DEFAULT_ASSUMPTIONS).mission["cost"]["stage1_engine_existing"] is True
    finally:
        os.remove(path)
