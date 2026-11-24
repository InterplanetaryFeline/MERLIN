"""The single-file design report must be self-contained, complete, and must not invent numbers.

The report is the artefact that leaves the tool, so these tests check the two properties that matter to a reader
who was not in the room: every number in it traces to the model, and the file renders on its own with no network.
"""
import os
import re
import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import report
from launch_vehicle.config_io import load_design
from launch_vehicle.convergence import size_vehicle


_CACHE = {}


def html():
    """The default design's report, built once and reused (the sizing run is the slow part)."""
    if "h" not in _CACHE:
        _CACHE["h"] = report.build_html(default_result(), {}, DESIGN, ASSUMP)
    return _CACHE["h"]


def test_report_is_self_contained():
    html = globals()["html"]()
    """No external requests: no http(s) URLs in src/href, no <script>, no remote fonts."""
    assert "<script" not in html.lower()
    for m in re.finditer(r'(?:src|href)\s*=\s*"([^"]*)"', html):
        u = m.group(1)
        assert u.startswith("#") or u.startswith("data:"), f"external reference in the report: {u}"
    assert "@import" not in html
    assert html.lstrip().startswith("<!DOCTYPE html>")
    assert html.rstrip().endswith("</html>")


def test_every_section_is_present():
    html = globals()["html"]()
    for anchor in ("id=req", "id=cfg", "id=drw", "id=perf", "id=mass", "id=ledger", "id=geo",
                   "id=inputs", "id=chk", "id=meth"):
        assert anchor in html, anchor


def test_headline_numbers_match_the_model():
    res = default_result()
    h = report.build_html(res, {}, DESIGN, ASSUMP)
    assert f"{res.glom_kg:,.0f} kg" in h
    assert f"{res.dv_required_mps:,.0f} m/s" in h
    assert f"{res.geometry.total_length:.2f} m" in h
    assert f"{100 * res.payload_mass_kg / res.glom_kg:.2f} %" in h


def test_every_input_appears_with_its_provenance():
    """The input register section must list all of them - a report that silently drops inputs is worse than none."""
    res = default_result()
    h = report.build_html(res, {}, DESIGN, ASSUMP)
    reg = res.spec.inputs_register
    assert len(reg) > 150
    for r in reg:
        assert r["path"] in h, f"input missing from the report: {r['path']}"
    for prov in ("user", "reference", "assumed"):
        assert f"p-{prov}" in h


def test_every_mass_ledger_item_and_every_issue_appears():
    res = default_result()
    h = report.build_html(res, {}, DESIGN, ASSUMP)
    for item in res.ledger:
        assert item.name.replace("&", "&amp;") in h, item.name
    for iss in res.issues:
        assert iss.code in h


def test_method_register_is_included():
    html = globals()["html"]()
    from launch_vehicle.method_register import REGISTER
    for row in REGISTER:
        assert row[0] in html                      # every method ID
    assert "SUPPLEMENTARY" in html                 # the honest-source marking survives into the report


def test_limitations_are_stated():
    html = globals()["html"]()
    for phrase in ("No trajectory simulation", "No structural analysis", "not a design qualification"):
        assert phrase in html


def test_solid_and_booster_designs_report_their_own_sections():
    for name, must in (("example_solid_smallsat.yaml", ("Solid motor grain and casing", "implied burn rate")),
                       ("example_boosters.yaml", ("Parallel-burn phases", "mass-averaged"))):
        res = size_vehicle(load_design(os.path.join(ROOT, "examples", name), ASSUMP))
        h = report.build_html(res, {}, name, ASSUMP)
        for phrase in must:
            assert phrase in h, f"{name}: {phrase}"


def test_missing_figures_do_not_break_the_report():
    h = report.build_html(default_result(), {"vehicle_png": "/nonexistent/x.png"}, DESIGN, ASSUMP)
    assert "figure not available" in h


def test_html_escaping_of_a_hostile_design_name():
    res = default_result()
    res.spec.name = '<script>alert(1)</script>'
    h = report.build_html(res, {}, DESIGN, ASSUMP)
    assert "<script>alert" not in h
    assert "&lt;script&gt;" in h


def test_unconverged_run_is_flagged_in_bold():
    res = default_result()
    res.converged, res.status = False, "hit the iteration limit"
    h = report.build_html(res, {}, DESIGN, ASSUMP)
    assert "NOT CONVERGED" in h and "must not be used" in h


def test_write_report_creates_the_file():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "sub", "design_report.html")
        out = report.write_report(default_result(), p, {}, DESIGN, ASSUMP, pdf=False)
        assert out["html"] == p and os.path.getsize(p) > 50_000
        assert "pdf" not in out


def test_no_html_entities_leak_into_the_rendered_text():
    """Symbols are written as literal UTF-8 (Δ, μ, Ø, ², ³), never as entities: a header that passes through the
    escaper would otherwise print as a visible '&Delta;'. This caught exactly that bug in the table headers."""
    import re
    h = html()
    body = re.sub(r"<style>.*?</style>", "", h, flags=re.S)
    allowed = {"&amp;", "&lt;", "&gt;", "&quot;", "&#x27;", "&#39;"}
    found = {m for m in re.findall(r"&[#A-Za-z0-9]{1,8};", body)} - allowed
    assert not found, f"HTML entities should be literal characters: {sorted(found)}"
    assert "Δv" in h and "μ" in h


def test_table_headers_may_carry_markup():
    from launch_vehicle.report import _tbl
    t = _tbl(["Δv [m/s]", "T/W<sub>0</sub>"], [["1", "2"]])
    assert "Δv [m/s]" in t and "<sub>0</sub>" in t


def test_report_prefers_the_page_shaped_drawings():
    """The paged figures exist so one drawing fills one printed page, as a single continuous vehicle; when they
    are present they must be the ones embedded."""
    import tempfile
    from launch_vehicle import schematic_2d
    res = default_result()
    with tempfile.TemporaryDirectory() as d:
        page = os.path.join(d, "v_page.png")
        single = os.path.join(d, "v.png")
        schematic_2d.draw_vehicle_page(res, page, None)
        schematic_2d.draw_vehicle(res, single, None)
        h = report.build_html(res, {"vehicle_page_png": page, "vehicle_png": single}, DESIGN, ASSUMP)
        with open(page, "rb") as f:
            import base64
            b64 = base64.b64encode(f.read()).decode("ascii")
        assert b64[:200] in h, "the page-shaped drawing was not the one embedded"
        assert "one continuous view" in h


def test_the_limitations_section_tells_the_truth_about_the_trajectory():
    """A fixed "no trajectory simulation" disclaimer above a section that integrates one would tell the reader
    the report does not know its own contents. The bullet has to follow what was actually run."""
    from launch_vehicle import trajectory as tj
    res = default_result()
    plain = report.build_html(res, {}, DESIGN, ASSUMP)
    assert "No trajectory was flown" in plain
    assert "--trajectory" in plain

    flown = tj.fly_design(res, dt=0.4)
    assert flown.converged
    with_traj = report.build_html(res, {}, DESIGN, ASSUMP, extras={"trajectory": flown})
    assert "A trajectory was flown" in with_traj
    assert "No trajectory was flown" not in with_traj
    # the caveats that survive a flown trajectory must still be stated
    assert "sized" in with_traj and "a check after the fact" in with_traj
    assert "upper bound" in with_traj

    flown.converged = False
    flown.status = "shooting failed: test"
    failed = report.build_html(res, {}, DESIGN, ASSUMP, extras={"trajectory": flown})
    assert "did not close" in failed
    assert "not</b> demonstrated" in failed or "not demonstrated" in failed


def test_the_limitations_section_tells_the_truth_about_the_structure():
    """The same rule as the trajectory bullet: a flat "no structural analysis" claim above a section that
    computes the load distributions would misdescribe the report."""
    from launch_vehicle import trajectory as tj, loads as L
    res = default_result()
    plain = report.build_html(res, {}, DESIGN, ASSUMP)
    assert "No structural analysis" in plain
    assert "--loads" in plain

    cases = L.standard_cases(res, tj.fly_design(res, dt=0.4))
    withl = report.build_html(res, {}, DESIGN, ASSUMP, extras={"loads": cases})
    assert "Loads, but not stresses" in withl
    assert "No structural analysis" not in withl
    # what is computed, and what is still missing, both have to be said
    assert "bending moment" in withl and "margin of safety" in withl
    assert "not</b> re-sized" in withl


def test_the_loads_section_reports_both_conditions_and_their_closure():
    from launch_vehicle import trajectory as tj, loads as L
    res = default_result()
    cases = L.standard_cases(res, tj.fly_design(res, dt=0.4))
    h = report.build_html(res, {}, DESIGN, ASSUMP, extras={"loads": cases})
    assert "Ground and flight loads" in h
    assert "Ground wind, fully loaded and unpressurised" in h
    assert "Flight at max-q" in h
    assert "Closure." in h
    assert "free-free beam" in h
    # and it is absent when the study was not run
    assert "Ground and flight loads" not in report.build_html(res, {}, DESIGN, ASSUMP)


def test_section_numbers_are_generated_from_one_list():
    """Sections are numbered from the same list the contents is built from, so an optional section appearing
    or disappearing can never leave the document numbered two different ways."""
    import re
    from launch_vehicle import trajectory as tj, loads as L
    res = default_result()
    for extras in ({}, {"trajectory": tj.fly_design(res, dt=0.4)}):
        if extras:
            extras["loads"] = L.standard_cases(res, extras["trajectory"])
        h = report.build_html(res, {}, DESIGN, ASSUMP, extras=extras)
        heads = re.findall(r"<h2 id=(\w+)>(\d+)\. ([^<]+)</h2>", h)
        assert [int(n) for _, n, _ in heads] == list(range(1, len(heads) + 1)), "headings are not 1..N in order"
        toc = re.findall(r'<a href="#(\w+)">(\d+)\. ([^<]+)</a>', h)
        assert [(i, n) for i, n, _ in toc] == [(i, n) for i, n, _ in heads], "contents and headings disagree"
        assert "># " not in h, "a section was left without a number"
        assert ("loads" in [i for i, _, _ in heads]) == bool(extras)


def test_the_aerodynamics_section_states_what_the_buildup_leaves_out():
    from launch_vehicle import trajectory as tj, aerodynamics as A
    res = default_result()
    tr = tj.fly_design(res, dt=0.4)
    cp = A.cp_over_trajectory(res, tr, every=6)
    h = report.build_html(res, {}, DESIGN, ASSUMP, extras={"trajectory": tr, "stability": cp})
    assert "Aerodynamic build-up and centre of pressure" in h
    assert "centre of pressure" in h.lower()
    # the honest caveats: no crossflow, Mach-independent default, no fins, no control analysis
    assert "crossflow" in h and "further forward than it really is" in h
    assert "independent of Mach" in h
    assert "does <b>not</b> assess control authority" in h
    assert "Aerodynamic build-up" not in report.build_html(res, {}, DESIGN, ASSUMP)


def test_the_limitations_section_changes_again_once_stresses_exist():
    """Third state of the structural bullet: loads only, loads plus stresses, or neither."""
    from launch_vehicle import trajectory as tj, loads as L, structure as stx
    res = default_result()
    tr = tj.fly_design(res, dt=0.4)
    cases = L.standard_cases(res, tr)
    loads_only = report.build_html(res, {}, DESIGN, ASSUMP, extras={"loads": cases})
    assert "Loads, but not stresses" in loads_only
    assert "--structure" in loads_only

    full = report.build_html(res, {}, DESIGN, ASSUMP,
                             extras={"loads": cases, "structure": stx.analyse(res, cases)})
    assert "Stresses and thicknesses, but not a structure" in full
    assert "Loads, but not stresses" not in full
    # the three things that must still be admitted
    assert "never re-sized" in full and "monocoque" in full and "combined stress state is not evaluated" in full


def test_the_structure_section_reports_thickness_drivers_and_the_mass_gap():
    from launch_vehicle import trajectory as tj, loads as L, structure as stx
    res = default_result()
    cases = L.standard_cases(res, tj.fly_design(res, dt=0.4))
    h = report.build_html(res, {}, DESIGN, ASSUMP,
                          extras={"loads": cases, "structure": stx.analyse(res, cases)})
    assert "Shell stress, buckling and required thickness" in h
    assert "t buckling [mm]" in h and "t required [mm]" in h
    assert "rings, stringers, waffle and isogrid" in h
    assert "What is not sized" in h
    assert "Shell stress" not in report.build_html(res, {}, DESIGN, ASSUMP)


def test_the_control_checks_appear_with_their_verdicts_and_sources():
    from launch_vehicle import trajectory as tj, aerodynamics as A, control as C
    res = default_result()
    tr = tj.fly_design(res, dt=0.4)
    cp = A.cp_over_trajectory(res, tr, every=6)
    ctl = C.assess(res, tr, cp["rows"])
    h = report.build_html(res, {}, DESIGN, ASSUMP,
                          extras={"trajectory": tr, "stability": cp, "control": ctl})
    assert "Can it be controlled?" in h
    assert "Controllability ratio" in h and "Time to double" in h
    assert "Gimbal deflection budget" in h
    assert "13 % above the root-sum-square" in h
    assert "not requirements for this design" in h
    # and the stability section stands alone without it
    assert "Can it be controlled?" not in report.build_html(res, {}, DESIGN, ASSUMP,
                                                           extras={"trajectory": tr, "stability": cp})


def test_the_ballistics_section_states_what_it_calibrated_and_what_it_omits():
    from launch_vehicle import solid_motor as sm, engine_geometry as eg
    from launch_vehicle.config_io import load_design
    from launch_vehicle.convergence import size_vehicle
    spec = load_design("examples/example_solid_smallsat.yaml", ASSUMP)
    res = size_vehicle(spec)
    s, stx = res.stages[0], spec.stages[0]
    case = [x for x in res.geometry.stage_segments(1) if x.kind == "tank"][0].tank
    ps = spec.solid_propellants[case.propellant]
    At = eg.throat_area(s.thrust_vac_N, ps.c_star_mps, stx.motor.chamber_pressure_Pa, stx.motor.isp_vac_s)
    pr = sm.burn_profile(case, ps.density_kg_m3, ps.c_star_mps, ps.burn_rate_exponent, At,
                         stx.motor.chamber_pressure_Pa, stx.motor.isp_vac_s)
    pr.update(stage=1, design_thrust_N=s.thrust_vac_N, design_burn_time_s=s.burn_time_s,
              propellant=case.propellant)
    h = report.build_html(res, {}, "examples/example_solid_smallsat.yaml", ASSUMP, extras={"ballistics": [pr]})
    assert "Solid motor internal ballistics" in h
    assert "cannot deliver the thrust the sizing assumed" in h
    assert "is <b>not</b> assumed" in h, "the calibration of a must be stated"
    assert "never dimensioned" in h and "erosive burning" in h
    assert "Solid motor internal ballistics" not in report.build_html(res, {}, "x", ASSUMP)
