"""The faults a user hit in the GUI that nothing in the suite had caught.

Every one of these was reported from use, not found by a test, and they share a shape worth naming: the
engine was right and the layer around it threw the answer away. A legitimate NaN made a whole response
unparseable; a part-filled design produced a raw TypeError and a broken file; a dropdown pushed a value into
a field no design had. So these tests sit at the boundary - the JSON that reaches the browser, the file that
reaches the disk, the error that reaches the user - rather than on the physics, which was never wrong.
"""
import glob
import json
import math
import os
import pathlib

import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import webgui
from launch_vehicle.config_io import ConfigError, load_design
from launch_vehicle.convergence import SizingError, size_vehicle

ASSUMP = "config/engineering_assumptions.yaml"


# ------------------------------------------------------------------ NaN and infinity on the wire
def test_non_finite_numbers_become_null_everywhere_in_the_payload():
    """JSON has no NaN. Python writes one happily and JSON.parse then rejects the WHOLE document.

    This is how eight shipped designs - Saturn V, Falcon 9, Titan II and Vega C among them - came to fail in
    the browser with "is not valid JSON" while sizing perfectly well from Python. One stray value did not
    spoil one field, it lost the entire response.
    """
    dirty = {"a": float("nan"), "b": float("inf"), "c": float("-inf"), "d": 1.5,
             "nested": {"e": [float("nan"), 2.0, {"f": float("inf")}]}, "s": "text", "n": None}
    clean = webgui._json_safe(dirty)
    json.dumps(clean, allow_nan=False)                       # must not raise
    assert clean["a"] is None and clean["b"] is None and clean["c"] is None
    assert clean["d"] == 1.5 and clean["s"] == "text" and clean["n"] is None
    assert clean["nested"]["e"][0] is None and clean["nested"]["e"][1] == 2.0
    assert clean["nested"]["e"][2]["f"] is None


def test_json_safe_leaves_everything_else_exactly_as_it_was():
    for v in (0, -3, 2.5, "x", True, False, None, [], {}, [1, "a", None]):
        assert webgui._json_safe(v) == v


def test_a_trim_deflection_that_is_not_a_number_still_says_which_case_it_was():
    """null on the wire cannot tell 'no gimbal authority' from 'no deflection balances it'."""
    assert "no gimbal authority" in webgui._trim_note(float("nan"))
    assert "balances" in webgui._trim_note(float("inf"))
    assert webgui._trim_note(2.0) == ""


def test_every_shipped_design_produces_strictly_valid_json():
    """The check that would have caught it: strict JSON over every design, with the default analysis on."""
    import tempfile
    wd = tempfile.mkdtemp()
    designs = sorted(glob.glob("examples/*.yaml") + glob.glob("validation/*.yaml")) \
        + ["config/default_design.yaml"]
    bad = []
    for i, p in enumerate(designs):
        if "trade_study" in p or "engine_database" in p:
            continue
        try:
            out = webgui.run_sizing(p, ASSUMP, {}, wd, f"t{i}", ("trajectory",))
            json.dumps(webgui._json_safe(out), allow_nan=False)
        except Exception as ex:                              # noqa: BLE001
            bad.append((p, f"{type(ex).__name__}: {ex}"))
    assert not bad, "designs that cannot reach the browser: " + "; ".join(f"{p} ({w})" for p, w in bad)


# ------------------------------------------------------------------ a required field left empty
def test_an_empty_required_input_names_itself_instead_of_raising_a_typeerror():
    """`perigee_altitude_km: null` used to surface as "unsupported operand type(s) for *: 'NoneType'"."""
    with pytest.raises(ConfigError) as ei:
        load_design("config/default_design.yaml", ASSUMP, {"mission.orbit.perigee_altitude_km": None})
    assert "perigee_altitude_km" in str(ei.value)
    assert "empty" in str(ei.value)
    assert ei.value.field == "mission.orbit.perigee_altitude_km"


def test_an_optional_input_may_still_be_null():
    """The emptiness rule must not catch the many fields where null means 'use the relationship'."""
    spec = load_design("config/default_design.yaml", ASSUMP, {"mission.launch_site.azimuth_deg": None})
    assert spec.mission["launch_azimuth_deg"] is None


def test_an_engine_without_a_published_chamber_pressure_still_loads():
    """RL10C-1 publishes no chamber pressure; a design that never needs one must not be refused."""
    spec = load_design("examples/example_engine_database.yaml", ASSUMP)
    assert spec.stages[1].engine.chamber_pressure_Pa is None


# ------------------------------------------------------------------ saving a half-filled design
def test_saving_a_part_filled_design_refuses_clearly_and_leaves_no_file(tmp_path=None):
    """It used to raise a raw TypeError AND leave the broken file it was complaining about on disk."""
    from launch_vehicle import gui_meta
    d = webgui.design_inputs("config/default_design.yaml", ASSUMP, describe=True)
    blanks = {x["path"]: None for x in (gui_meta.new_design_plan(d["items"]).get("blank") or [])}
    assert blanks, "the New-design plan should clear some fields"
    name = "PartFilledRegressionCase"
    target = os.path.join(webgui.SAVE_DIR, name + ".yaml")
    try:
        with pytest.raises(ConfigError) as ei:
            webgui.save_design("config/default_design.yaml", blanks, name, "test")
        msg = str(ei.value)
        assert "Not saved" in msg and "still empty" in msg
        assert ei.value.field in blanks, "the error must name a field the page can jump to"
        assert not os.path.exists(target), "a refused save must not leave a file behind"
        assert not os.path.exists(target + ".part"), "nor its temporary file"
    finally:
        for p in (target, target + ".part"):
            if os.path.exists(p):
                os.remove(p)


# ------------------------------------------------------------------ what the Open dialog offers
def test_the_open_dialog_lists_only_things_that_are_designs():
    """A trade-study declaration is not a vehicle. Offering it meant opening it failed with a message about
    undocumented bare values, which says nothing about why it was in the list."""
    paths = [d["path"] for d in webgui.list_designs()]
    assert "examples/example_trade_study.yaml" not in paths
    assert "config/default_design.yaml" in paths
    assert all("launch_sites" not in p and "engineering_assumptions" not in p for p in paths)


# ------------------------------------------------------------------ an error that can be acted on
def test_an_impossible_solid_casing_names_the_field_and_offers_a_value_that_works():
    """The heart of it: the suggested number must actually fix the design, not merely sound plausible.

    A motor whose propellant volume is smaller than its own two domes has no barrel length. The model solves
    both ways out exactly - the widest feasible diameter, and the propellant needed at this one - and the
    diameter is handed back as a value a user interface can apply in one click. So the test applies it.
    """
    ov = {"stages[3].diameter_m": 2.0, "fairing.diameter_m": 2.4}
    with pytest.raises(SizingError) as ei:
        size_vehicle(load_design("validation/scout_g1.yaml", ASSUMP, ov))
    err = ei.value
    assert err.field == "stages[3].diameter_m", err.field
    assert len(err.options) >= 2, "two ways out exist, so two should be offered"
    fix = next(o for o in err.options if o.get("path") and o.get("value") is not None)
    assert fix["path"] == "stages[3].diameter_m"
    assert 0.0 < fix["value"] < 2.0

    ov[fix["path"]] = fix["value"]
    res = size_vehicle(load_design("validation/scout_g1.yaml", ASSUMP, ov))
    assert res.glom_kg > 0, "the suggested diameter has to produce a design that actually sizes"


def test_every_offered_option_is_readable_and_says_what_it_does():
    ov = {"stages[3].diameter_m": 2.0, "fairing.diameter_m": 2.4}
    with pytest.raises(SizingError) as ei:
        size_vehicle(load_design("validation/scout_g1.yaml", ASSUMP, ov))
    for opt in ei.value.options:
        assert opt.get("label"), "every option needs something a person can read"
        assert opt.get("note"), "and a reason, since the label is only a sentence fragment"


# ------------------------------------------------------------------ the launch site cascade
def test_picking_a_launch_site_works_on_every_shipped_design():
    """The cascade pushes site, latitude and longitude. A design lacking any of those fields used to fail
    with "unknown parameter path", which read as the tool demanding a longitude it had just been given."""
    ov = {"mission.launch_site.site": "Guiana Space Centre, Kourou",
          "mission.launch_site.latitude_deg": 5.2374,
          "mission.launch_site.longitude_deg": -52.7695}
    bad = []
    for p in sorted(["config/default_design.yaml"] + glob.glob("examples/*.yaml")
                    + glob.glob("validation/*.yaml")):
        if "trade_study" in p:
            continue
        try:
            load_design(p, ASSUMP, ov)
        except Exception as ex:                              # noqa: BLE001
            bad.append((p, f"{type(ex).__name__}: {ex}"))
    assert not bad, "designs that refuse a picked launch site: " + "; ".join(f"{p} ({w})" for p, w in bad)


def test_every_design_exposes_a_longitude_field_for_the_map():
    """Drop zones need a meridian. Without the field there was no way to supply one by hand."""
    missing = []
    for p in sorted(["config/default_design.yaml"] + glob.glob("examples/*.yaml")
                    + glob.glob("validation/*.yaml")):
        if "trade_study" in p:
            continue
        items = webgui.design_inputs(p, ASSUMP, describe=True)["items"]
        if not any(i["path"] == "mission.launch_site.longitude_deg" for i in items):
            missing.append(p)
    assert not missing, "designs with no longitude field: " + ", ".join(missing)


# ------------------------------------------------------------------ materials
def test_the_material_library_offers_more_than_aluminium():
    import yaml
    from launch_vehicle.config_io import _Loader
    with open(ASSUMP, encoding="utf-8") as fh:
        mats = yaml.load(fh, Loader=_Loader)["tank_materials"]
    assert len(mats) >= 4, sorted(mats)
    assert {"Al-2219", "SS-301-FH", "SS-304L", "Ti-6Al-4V"} <= set(mats)


def test_every_material_records_the_yield_its_allowable_was_derated_from():
    """A trade between materials is only meaningful if each is derated on the same basis, so each entry
    carries the published yield behind its allowable and the ratio has to match."""
    import yaml
    from launch_vehicle.config_io import _Loader
    with open(ASSUMP, encoding="utf-8") as fh:
        mats = yaml.load(fh, Loader=_Loader)["tank_materials"]
    for key, m in mats.items():
        assert "yield_min_Pa" in m, f"{key} does not say what its allowable came from"
        allow = m["sigma_allow_Pa"]["v"]
        yld = m["yield_min_Pa"]["v"]
        assert 0.55 < allow / yld < 0.70, (
            f"{key} is derated to {allow / yld:.3f} of yield; the library's basis is 0.633 and a material "
            f"on a different basis would decide a trade by bookkeeping")


def test_a_material_that_the_tank_mass_method_ignores_is_flagged():
    """Choosing stainless and watching the mass not move looks broken. It is not - the relationship-based
    methods are functions of propellant mass alone - but the user has to be told which case they are in."""
    from launch_vehicle import validation as V
    spec = load_design("config/default_design.yaml", ASSUMP, {"stages[0].tank.material": "SS-304L"})
    assert any(i.code == "MATUNUSED" for i in V.validate_spec(spec))

    pv = {f"stages[{i}].tank.mass_method_{r}": "pressure_vessel" for i in (0, 1) for r in ("fuel", "oxidizer")}
    pv["stages[0].tank.material"] = "SS-304L"
    spec2 = load_design("config/default_design.yaml", ASSUMP, pv)
    assert not any(i.code == "MATUNUSED" for i in V.validate_spec(spec2))


def test_each_material_sizes_and_they_do_not_all_give_the_same_answer():
    """With real pressure-vessel sizing the material has to matter, and in the direction metallurgy says:
    titanium lighter than aluminium, annealed 304L far heavier than either."""
    pv = {f"stages[{i}].tank.mass_method_{r}": "pressure_vessel" for i in (0, 1) for r in ("fuel", "oxidizer")}
    glom = {}
    for mat in ("Al-2219", "SS-301-FH", "SS-304L", "Ti-6Al-4V"):
        ov = dict(pv, **{"stages[0].tank.material": mat, "stages[1].tank.material": mat})
        glom[mat] = size_vehicle(load_design("config/default_design.yaml", ASSUMP, ov)).glom_kg
    assert glom["Ti-6Al-4V"] < glom["Al-2219"] < glom["SS-304L"]
    assert glom["SS-304L"] > 1.5 * glom["Al-2219"], (
        f"annealed 304L has roughly a seventh of 2219's allowable, so it must come out much heavier: {glom}")


# ------------------------------------------------------------------ the liquid-tank twin of that error
def test_a_tank_too_wide_for_its_propellant_names_the_field_and_offers_a_working_value():
    """The same treatment as the solid casing, on the path a user actually hit.

    The message already quoted the maximum radius, but carried no field and no value, so the GUI showed a
    paragraph and no way to act on it. Worse, it told the reader to set `tank.diameter_m` - a field that
    `tank_sizing` reads and the method register documents as M47, but which no shipped design file
    contained, so it appeared in no form and could not be set at all.
    """
    # Stage 2 is WIDENED (with the fairing to match) rather than the payload being shrunk to 150 kg. The
    # old form shrank the whole vehicle, which since v0.27 makes stage 1's tank the binding one too: the
    # geometry checks now run on the CONVERGED design (R34) and report the first stage that fails, so a
    # configuration meant to exercise stage 2 was being answered about stage 1. Widening only stage 2
    # isolates it, which is what this test is named for.
    ov = {"stages[1].diameter_m": 4.0, "fairing.diameter_m": 4.0}
    with pytest.raises(SizingError) as ei:
        size_vehicle(load_design("config/default_design.yaml", ASSUMP, ov))
    err = ei.value
    assert err.field == "stages[1].tank.diameter_m", err.field
    fix = next(o for o in err.options if o.get("path") and o.get("value") is not None)
    assert fix["path"] == "stages[1].tank.diameter_m"

    # the suggested diameter must actually clear THIS stage's complaint
    ov[fix["path"]] = fix["value"]
    try:
        size_vehicle(load_design("config/default_design.yaml", ASSUMP, ov))
    except SizingError as again:
        assert "stages[1]" not in (again.field or ""), (
            f"the suggested tank diameter did not clear stage 2's geometry: {again}")


def test_every_design_exposes_the_tank_diameter_the_error_tells_you_to_set():
    missing = [p for p in sorted(glob.glob("examples/*.yaml") + glob.glob("validation/*.yaml")
                                 + ["config/default_design.yaml"])
               if "trade_study" not in p
               and any(s.is_solid is False for s in load_design(p, ASSUMP).stages)
               and not any(i["path"].endswith("tank.diameter_m")
                           for i in webgui.design_inputs(p, ASSUMP, describe=True)["items"])]
    assert not missing, "liquid designs with no settable tank diameter: " + ", ".join(missing)


def test_an_absurd_dome_aspect_ratio_is_explained_rather_than_offered():
    """The algebra always yields a number; a dome at R/h = 27 is a flat plate, not an end cap."""
    from launch_vehicle.tank_sizing import MAX_SENSIBLE_DOME_AR
    # 6.0 m rather than 3.0 m with a 150 kg payload: wide enough that the aspect ratio needed to rescue the
    # domes is past MAX_SENSIBLE_DOME_AR even for the CONVERGED design, which is what the checks now run on
    # (R34). At 4.0 m the required ratio is only 1.55 and is legitimately offered, so the absurd case has to
    # be forced further than it did when an early iterate could trigger it.
    ov = {"stages[1].diameter_m": 6.0, "fairing.diameter_m": 6.0}
    with pytest.raises(SizingError) as ei:
        size_vehicle(load_design("config/default_design.yaml", ASSUMP, ov))
    dome = [o for o in ei.value.options if "dome" in o["label"].lower() or "domes" in o["label"].lower()]
    assert dome, "the dome remedy should still be mentioned"
    assert dome[0].get("value") is None, (
        f"an aspect ratio beyond {MAX_SENSIBLE_DOME_AR} must not be offered as a one-click fix")
    assert "cannot fix" in dome[0]["label"]


# ------------------------------------------------------------------ the delta-v split
def test_the_split_optimiser_the_gui_button_calls_returns_usable_fractions():
    """The optimiser existed in the engine with no way to reach it from the browser.

    The field it fills used to be a text box holding "0.44, 0.56" - the single most consequential input in
    the design, asking the user to normalise in their head and remember which entry was which stage.
    """
    from launch_vehicle.optimization import optimize_dv_split
    spec = load_design("config/default_design.yaml", ASSUMP)
    out = optimize_dv_split(spec)
    fr = out["fractions"]
    assert len(fr) == len(spec.stages)
    assert all(0.0 < f < 1.0 for f in fr), fr
    assert abs(sum(fr) - 1.0) < 1e-6, f"the split has to be a partition of the delta-v: {fr}"
    assert out["glom_kg"] <= out["baseline_glom_kg"] + 1.0, (
        "the optimiser must not return something heavier than the design it started from")


def test_the_split_field_is_described_in_words_rather_than_as_a_bare_fraction_list():
    from launch_vehicle import gui_meta
    items = webgui.design_inputs("config/default_design.yaml", ASSUMP, describe=True)["items"]
    it = next(i for i in items if i["path"] == "vehicle.dv_fractions")
    assert it["label"] == "Delta-v share per stage", it["label"]
    assert "share" in it["description"].lower()
    assert "staging decision" in it["description"].lower(), (
        "the description should say what the field decides, not just what it contains")


# ------------------------------------------------------------------ inputs the GUI can never show
#: Keys the loader reads that are deliberately NOT design leaves: block names, and the per-stage overrides
#: that exist for programmatic use. Anything else read by the loader must appear in a shipped design, or it
#: is an input nobody can set.
NOT_LEAF_KEYS = {
    "mission", "orbit", "launch_site", "losses", "vehicle", "stages", "tank", "engine", "motor", "layout",
    "fairing", "boosters", "constraints", "aerodynamics", "wind", "air_launch", "geometry",
    "propellants", "solid_propellants", "tank_materials", "mer", "mer_scatter", "convergence",
    "cost",                   # the Cost tab's own block; its settings are made there (tests/test_cost.py)
}


def test_every_input_the_loader_accepts_appears_in_some_shipped_design():
    """Otherwise the input exists only in the loader, and nobody can reach it.

    Four were found this way, all with the same symptom - the capability is implemented, sometimes
    documented in the method register, and invisible:

      tank.diameter_m             tanks narrower than the stage (method M47); the geometry error told
                                  users to set it
      tank.user_mass_fuel_kg      the `user_mass` tank method is SELECTABLE in the GUI, and without these
      tank.user_mass_oxidizer_kg  it sized the tanks at zero, silently, for a vehicle 5 % light
      engine.geometry_method      the chamber-pressure error told users to switch it to 'user'

    A dropdown offering a method whose inputs do not exist is worse than a missing field: it produces a
    confident wrong number.
    """
    import re
    read = set()
    src = pathlib.Path("src/launch_vehicle/config_io.py").read_text(encoding="utf-8")
    for m in re.finditer(r'_need\(\s*\w+\s*,\s*"([^"]+)"', src):
        read.add(m.group(1))
    for m in re.finditer(r'\b\w+\.get\(\s*"([^"]+)"', src):
        read.add(m.group(1))

    offered = set()
    designs = ["config/default_design.yaml"] + sorted(glob.glob("examples/*.yaml")
                                                      + glob.glob("validation/*.yaml"))
    for p in designs:
        if "trade_study" in p:
            continue
        for i in webgui.design_inputs(p, ASSUMP, describe=True)["items"]:
            offered.add(i["path"].rsplit(".", 1)[-1])

    unreachable = sorted(k for k in read - offered - NOT_LEAF_KEYS if not k.startswith("_"))
    assert not unreachable, (
        "the loader reads these, but no shipped design contains them, so they appear in no form and "
        "cannot be set: " + ", ".join(unreachable))


def test_a_tank_mass_method_without_its_input_is_refused_rather_than_sized_at_zero():
    """Selecting `user_mass` and leaving the mass blank used to give a tank of no mass and no warning."""
    from launch_vehicle import validation as V
    from launch_vehicle.validation import InputError
    ov = {"stages[0].tank.mass_method_fuel": "user_mass",
          "stages[0].tank.mass_method_oxidizer": "user_mass"}
    with pytest.raises(InputError) as ei:
        size_vehicle(load_design("config/default_design.yaml", ASSUMP, ov))
    assert "TANKUSER" in str(ei.value)
    assert "user_mass_fuel_kg" in str(ei.value), "the message must name the field to fill in"

    # and with the mass supplied it sizes, using it
    ov["stages[0].tank.user_mass_fuel_kg"] = 900.0
    ov["stages[0].tank.user_mass_oxidizer_kg"] = 1500.0
    res = size_vehicle(load_design("config/default_design.yaml", ASSUMP, ov))
    assert res.glom_kg > 0


def test_every_selectable_tank_mass_method_can_actually_be_used():
    """Each method in the dropdown must have whatever inputs it needs reachable in the same form."""
    from launch_vehicle.validation import TANK_METHODS
    items = webgui.design_inputs("config/default_design.yaml", ASSUMP, describe=True)["items"]
    paths = {i["path"] for i in items}
    needs = {
        "user_mass": ["stages[0].tank.user_mass_fuel_kg", "stages[0].tank.user_mass_oxidizer_kg"],
        "mass_fraction": ["stages[0].tank.mass_fraction_fuel", "stages[0].tank.mass_fraction_oxidizer"],
        "pressure_vessel": ["stages[0].tank.material", "stages[0].tank.pressure_fuel_Pa"],
    }
    missing = []
    for method, required in needs.items():
        assert method in TANK_METHODS, f"{method} is no longer offered; update this test"
        missing += [r for r in required if r not in paths]
    assert not missing, "tank methods are offered whose inputs are not in the form: " + ", ".join(missing)


def test_the_sensitivity_studies_are_reachable_from_the_browser():
    """They ran in the CLI by default and reached the workbook, with no way in from the GUI at all.

    "What is this design most sensitive to" is the question a preliminary sizing model exists to answer,
    and it could only be asked from a terminal.
    """
    from launch_vehicle import sensitivity
    base = size_vehicle(load_design("config/default_design.yaml", ASSUMP))
    rows = sensitivity.standard_studies("config/default_design.yaml", ASSUMP, base)
    comp = sensitivity.configuration_comparison("config/default_design.yaml", ASSUMP, base)
    assert len(rows) > 20 and len({r["study"] for r in rows}) >= 5
    assert comp, "the configuration comparison should produce rows"
    payload = webgui._json_safe({"baseline_glom_kg": base.glom_kg, "studies": rows, "configurations": comp})
    json.dumps(payload, allow_nan=False)
    # an infeasible case keeps its row and its reason rather than vanishing
    for r in rows:
        assert "case" in r and "study" in r and "feasible" in r


def test_the_page_knows_everything_the_engine_database_fills_in():
    """A stage that NAMES a real engine leaves that engine's figures blank on purpose, and the library fills
    them as the design loads. The page has to know which keys those are, or it nags about fields the user is
    not supposed to set - which is what `examples/example_engine_database.yaml`, the example that exists to
    demonstrate naming an engine, used to do: it opened with "2 fields need you" against it.

    This pins the page's list against the loader's, so a key added to one and forgotten in the other fails
    here rather than in front of a user.
    """
    import re
    from launch_vehicle import engine_db
    with open(os.path.join(ROOT, "src", "launch_vehicle", "gui_static", "index.html"),
              encoding="utf-8") as fh:
        page = fh.read()
    m = re.search(r"const DATABASE_FILLS = \[(.*?)\];", page, re.S)
    assert m, "the page no longer declares DATABASE_FILLS"
    listed = set(re.findall(r'"([A-Za-z_0-9]+)"', m.group(1)))    # keys carry unit suffixes: _Pa, _N, _OF
    missing = set(engine_db.WATCHED) - listed
    assert not missing, f"the page does not know the database fills these in: {sorted(missing)}"


def test_naming_a_real_engine_is_not_a_no_op():
    """Picking an engine from the database used to change nothing at all.

    The database never overrides a value the design file states - deliberate, so a check case cannot be
    quietly rewritten by the library - so a stage that already had its own Isp and thrust kept them, and the
    lift-off mass came back identical to the kilogram. The tool warned three times, but only in the Checks
    tab; at the dropdown nothing happened, which reads as a broken control rather than a contract.

    The page now clears the figures that engine supplies. This pins the server side of that: with those
    figures blank, naming the engine must actually move the vehicle.
    """
    from launch_vehicle.config_io import load_design
    from launch_vehicle.convergence import size_vehicle
    base = size_vehicle(load_design("config/default_design.yaml", ASSUMP)).glom_kg

    have = {i["path"] for i in webgui.design_inputs("config/default_design.yaml", ASSUMP,
                                                    describe=True)["items"]}
    fills = ["isp_vac_s", "isp_sl_s", "thrust_vac_per_engine_N", "thrust_vac_total_N", "expansion_ratio",
             "chamber_pressure_Pa", "prop_mass_each_kg", "burn_time_s", "mixture_ratio_OF"]
    for engine, want_lighter in (("RD-180", True), ("Merlin 1D", True)):
        overrides = {"stages.0.engine.from_database": engine}
        for leaf in fills:
            path = f"stages[0].engine.{leaf}" if f"stages[0].engine.{leaf}" in have else f"stages[0].{leaf}"
            if path in have:
                overrides[path.replace("[0]", ".0")] = None
        got = size_vehicle(load_design("config/default_design.yaml", ASSUMP, overrides)).glom_kg
        assert abs(got - base) > 1000.0, (
            f"naming {engine} and clearing what it supplies still gave {got:,.0f} kg against the design's "
            f"own {base:,.0f} kg - the pick is doing nothing")
        if want_lighter:
            assert got < base, f"{engine} should beat the generic 290 s engine: {got:,.0f} vs {base:,.0f} kg"


def test_the_page_fills_in_what_a_named_engine_supplies():
    """Picking an engine used to BLANK the fields it supplies and leave the database to fill them unseen at
    sizing time, so the page showed empty boxes where the engine's Isp and area ratio should have been. It
    now writes them. The filling lives in the page; this pins that it is wired to the server's map, that the
    stage-level fields (propellants, mixture ratio) are included, and that the old clearing is gone."""
    with open(os.path.join(ROOT, "src", "launch_vehicle", "gui_static", "index.html"), encoding="utf-8") as fh:
        page = fh.read()
    assert "S.engines[value]" in page and "S.engines = d.engines" in page
    assert 'groups.push([stage + ".", eng.stage || {}])' in page, "the mixture ratio belongs to the stage"
    assert "Cleared ${cleared.length} figure(s)" not in page, "the pick must fill the fields, not blank them"
    assert "S.overrideSources[p] = src" in page, "a filled value must be recorded as the database's"


def test_the_engine_map_is_the_loaders_own_mapping_and_invents_nothing():
    from launch_vehicle import engine_db, gui_meta
    m = gui_meta.engine_map()
    assert len(m) == len(engine_db.entries())
    merlin, row = m["Merlin 1D"], engine_db.find("Merlin 1D")
    assert set(merlin["engine"]) == set(engine_db.ENGINE_FIELDS)
    assert set(merlin["stage"]) == set(engine_db.STAGE_FIELDS)
    assert merlin["engine"]["isp_vac_s"] == row["isp_vac_s"] and merlin["stage"]["mixture_ratio_OF"] == row["of_ratio"]
    assert merlin["engine"]["length_m"] is None, "a figure the source does not give stays empty"
    solid = next(v for v in m.values() if v["kind"] == "solid")
    assert set(solid["motor"]) == set(engine_db.MOTOR_FIELDS) and "engine" not in solid


def test_filling_an_engines_figures_gives_the_vehicle_the_loader_would_have_sized():
    """The page writes the engine's values where the loader used to fill blanks. For the fields both touch
    the vehicle must be the same one, or the visible numbers and the sized vehicle would disagree."""
    from launch_vehicle import gui_meta
    from launch_vehicle.config_io import load_design
    from launch_vehicle.convergence import size_vehicle
    e = gui_meta.engine_map()["Merlin 1D"]
    keys = ("isp_vac_s", "isp_sl_s", "chamber_pressure_Pa", "expansion_ratio")
    blank = {"stages.0.engine.from_database": "Merlin 1D", "stages.0.mixture_ratio_OF": None}
    blank.update({f"stages.0.engine.{k}": None for k in keys})
    filled = {"stages.0.engine.from_database": "Merlin 1D", "stages.0.mixture_ratio_OF": e["stage"]["mixture_ratio_OF"]}
    filled.update({f"stages.0.engine.{k}": e["engine"][k] for k in keys})
    a = size_vehicle(load_design("config/default_design.yaml", ASSUMP, blank)).glom_kg
    b = size_vehicle(load_design("config/default_design.yaml", ASSUMP, filled)).glom_kg
    assert b == pytest.approx(a, rel=1e-9)


def test_the_offered_casing_diameter_survives_the_design_reconverging():
    """The old offered value sat 0.5 mm inside the exact feasibility boundary, and that is not enough.

    Narrowing a stage changes its mass, which redistributes the delta-v split, which changes the propellant
    load, which MOVES the boundary the value was computed against. So a diameter that is feasible for the
    current propellant can be infeasible for the re-converged one. Measured on Scout G-1 stage 4 forced to
    2.0 m: 0.5 mm failed, 1 % failed, 2 % was the first margin that settled. The offer now carries 5 %.

    This pins the property that matters - every offered diameter must produce a design that actually
    sizes - across every solid stage in the check set, not just the one that exposed it.
    """
    forced = []
    for name in ("scout_g1", "vega", "vega_c", "epsilon", "pegasus_xl", "m_v"):
        path = f"validation/{name}.yaml"
        spec = load_design(path, ASSUMP)
        for i, st in enumerate(spec.stages):
            if not st.is_solid:
                continue
            ov = {f"stages[{i}].diameter_m": 4.0, "fairing.diameter_m": 4.4}
            try:
                size_vehicle(load_design(path, ASSUMP, ov))
                continue                      # this stage did not hit the corner; nothing to offer
            except SizingError as ex:
                opts = [o for o in (ex.options or []) if o.get("path") and o.get("value") is not None]
                if not opts:
                    continue
                o = opts[0]
                key = o["path"] if "." in o["path"] else f"stages[{i}].{o['path']}"
                ov2 = dict(ov)
                ov2[key] = o["value"]
                size_vehicle(load_design(path, ASSUMP, ov2))     # must not raise
                forced.append(f"{name} s{i+1}")
    assert len(forced) >= 10, (
        f"expected the dome-volume corner on most solid stages, only reached it on {forced}")
