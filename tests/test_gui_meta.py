"""What the GUI needs to turn a YAML path into a question a person can answer.

Two things decide whether the GUI is usable: that a field with a fixed set of values offers that set rather
than a text box, and that the choices offered are the ones the model will actually accept. So the tests here
check the lists against their enforcers - the propellant library, the engine database, and the validators in
validation.py - rather than against a copy of themselves. A dropdown that offers a value the model rejects is
worse than a text box, because it looks authoritative.
"""
import os

import pytest
import yaml
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import gui_meta as M
from launch_vehicle.config_io import _Loader, load_design
from launch_vehicle.webgui import design_inputs

_C = {}


def assumptions():
    if "a" not in _C:
        with open(ASSUMP, encoding="utf-8") as fh:
            _C["a"] = yaml.load(fh, Loader=_Loader)
    return _C["a"]


def described(path=None):
    key = path or DESIGN
    if key not in _C:
        d = design_inputs(key, ASSUMP, describe=True)
        _C[key] = d
    return _C[key]


# ------------------------------------------------------------------- path handling
def test_both_index_spellings_normalise_together():
    """The register writes stages[0]...; overrides and the design dict write stages.0... ."""
    assert M.normalise("stages[0].engine.isp_vac_s") == "stages.*.engine.isp_vac_s"
    assert M.normalise("stages.0.engine.isp_vac_s") == "stages.*.engine.isp_vac_s"
    assert M.normalise("stages[11].tank.material") == M.normalise("stages.11.tank.material")
    assert M.normalise("mission.orbit.type") == "mission.orbit.type"


def test_a_stage_field_lands_in_its_stage_whichever_spelling_is_used():
    for p in ("stages[0].engine.isp_vac_s", "stages.0.engine.isp_vac_s"):
        assert M.place(p) == ("Stage 1", "Engine")
    assert M.place("stages[2].tank.material") == ("Stage 3", "Tankage")
    assert M.place("stages[0].layout.aft_skirt_over_D") == ("Stage 1", "Layout")
    assert M.place("stages[0].diameter_m") == ("Stage 1", "Propellants and size")


def test_mission_splits_into_what_the_mission_is_and_how_it_is_flown():
    assert M.place("mission.payload_mass_kg") == ("Mission", "Payload and orbit")
    assert M.place("mission.orbit.inclination_deg") == ("Mission", "Orbit")
    assert M.place("mission.launch_site.latitude_deg") == ("Mission", "Launch site")
    assert M.place("mission.wind.profile") == ("Mission", "Winds aloft")
    assert M.place("mission.aerodynamics.drag_model") == ("Mission", "Trajectory model")
    assert M.place("mission.atmosphere_model") == ("Mission", "Trajectory model")


# ------------------------------------------------------------------- labels
def test_every_input_gets_a_label_that_is_not_the_path():
    for it in described()["items"]:
        lab = it["label"]
        assert lab and not lab.startswith("stages"), it["path"]
        assert "_" not in lab, f"{it['path']} still reads like a variable name: {lab!r}"


def test_the_labels_people_read_most_are_the_curated_ones():
    want = {"mission.payload_mass_kg": "Payload mass",
            "stages[0].engine.isp_vac_s": "Vacuum specific impulse",
            "stages[0].mixture_ratio_OF": "Mixture ratio (oxidiser/fuel)",
            "stages[0].engine.from_database": "Pick a real engine (fills the fields below)",
            "fairing.diameter_m": "Fairing diameter",
            "constraints.max_vehicle_length_m": "Maximum vehicle length"}
    got = {it["path"]: it["label"] for it in described()["items"]}
    for p, lab in want.items():
        assert got.get(p) == lab, f"{p}: {got.get(p)!r}"


def test_an_unlisted_field_still_gets_something_readable():
    """A field added to the YAML without touching this module must not break the page."""
    assert M.label_for("mission.some_new_thing_kg") == "Some new thing"
    assert M.label_for("stages.0.engine.another_value_mps") == "Another value"


# ------------------------------------------------------------------- choices
def test_propellant_choices_are_the_propellants_the_model_has():
    """The two lists together must be the whole library - split by role, but nothing lost.

    This used to assert that the FUEL list was the entire library, which was true and wrong: it meant the
    fuel box offered LOX. The invariant that actually matters is that every propellant stays reachable.
    """
    lib = M.library_choices(assumptions())
    fuels = {v for v, _ in lib["stages.*.fuel"]}
    oxes = {v for v, _ in lib["stages.*.oxidizer"]}
    assert fuels | oxes == set(assumptions()["propellants"]), "a propellant became unreachable"
    assert "RP-1" in fuels and "HTP-98" in oxes


def test_engine_choices_are_the_database_and_split_liquid_from_solid():
    from launch_vehicle import engine_db
    lib = M.library_choices(assumptions())
    rows = engine_db.entries()
    liquid = {e["name"] for e in rows if e.get("kind", "liquid") != "solid"}
    solid = {e["name"] for e in rows if e.get("kind") == "solid"}
    assert {v for v, _ in lib["stages.*.engine.from_database"]} == liquid
    assert {v for v, _ in lib["stages.*.motor.from_database"]} == solid
    assert not (liquid & solid), "a row cannot be offered as both an engine and a motor"


def test_combination_and_material_choices_come_from_the_libraries():
    lib = M.library_choices(assumptions())
    assert {v for v, _ in lib["stages.*.propellant_combination"]} == set(assumptions()["propellant_combinations"])
    assert {v for v, _ in lib["stages.*.tank.material"]} == set(assumptions()["tank_materials"])


def test_tank_method_choices_track_their_validator():
    from launch_vehicle.validation import TANK_METHODS
    lib = M.library_choices(assumptions())
    assert tuple(v for v, _ in lib["stages.*.tank.mass_method_fuel"]) == tuple(TANK_METHODS)


def test_every_offered_choice_is_one_the_model_accepts():
    """The test that matters: a dropdown must not offer a value validate_spec would reject.

    Checked against the validators themselves for the code-level enums, by substituting each offered value
    into a real design and confirming the model does not reject it as unknown.
    """
    from launch_vehicle.validation import InputError
    checks = {"vehicle.payload_adapter_method": "PAF", "vehicle.dv_allocation_mode": "DVMODE",
              "fairing.material": None, "stages.0.structure_mode": "STRUCT",
              "stages.0.tank.arrangement": "TANKARR", "stages.0.engine.isp_effective_mode": "ISP",
              "stages.0.engine.mass_method": "ENGMASS", "stages.0.engine.gimbal_method": None,
              "stages.0.tank.mass_method_fuel": "TANKM"}
    lib = M.library_choices(assumptions())
    for path, _code in checks.items():
        ch = M.choices_for(path, lib)
        assert ch, f"{path} should have a choice list"
        for value, _label in ch:
            try:
                load_design(DESIGN, ASSUMP, {path: value})
            except InputError as e:
                # a value may be rejected for needing a companion field (user Isp needs the Isp); what must
                # never happen is the model calling the value itself unknown
                assert "unknown" not in str(e).lower(), f"{path}={value!r} is offered but unknown: {e}"
            except Exception as e:                           # noqa: BLE001
                assert "unknown" not in str(e).lower(), f"{path}={value!r}: {e}"


def test_a_free_value_gets_no_dropdown():
    lib = M.library_choices(assumptions())
    for p in ("mission.payload_mass_kg", "stages.0.engine.isp_vac_s", "fairing.diameter_m"):
        assert M.choices_for(p, lib) is None, f"{p} is a number, not a choice"


def test_the_choice_lists_survive_a_broken_engine_database():
    """A database that will not load should cost the engine dropdown, not the whole page."""
    import launch_vehicle.engine_db as db
    real = db.entries
    db.entries = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        lib = M.library_choices(assumptions())
    finally:
        db.entries = real
    assert "stages.*.engine.from_database" not in lib
    assert "stages.*.fuel" in lib, "the propellant lists should be unaffected"


# ------------------------------------------------------------------- the described payload
def test_describe_adds_what_the_browser_needs_without_losing_what_was_there():
    d = described()
    for it in d["items"]:
        assert {"path", "value", "units", "description", "source", "provenance", "type",
                "label", "section", "topic", "choices"} <= set(it)
    assert d["open_sections"], "the page needs to know which sections to open"
    assert d["meta"]["name"], "the configuration needs a name to show in the title bar"


def test_the_default_design_offers_the_two_library_pickers():
    """The engine and combination pickers are the point of the exercise; they must be present and non-empty."""
    by = {it["path"]: it for it in described()["items"]}
    for p in ("stages[0].engine.from_database", "stages[0].propellant_combination"):
        assert p in by, f"{p} is missing from the default design, so the GUI cannot offer it"
        assert by[p]["choices"], f"{p} has no choices"
        assert by[p]["provenance"] == "user"


def test_a_validation_case_is_described_too():
    """Check cases are loaded through the same path, so they must describe cleanly."""
    d = described(os.path.join(ROOT, "validation", "electron.yaml"))
    secs = {it["section"] for it in d["items"]}
    assert {"Mission", "Stage 1", "Stage 2"} <= secs
    assert any(it["choices"] for it in d["items"])


# ============================================ v0.17: the six GUI problems a user reported in one sitting
def test_the_fuel_box_offers_only_fuels_and_the_oxidiser_box_only_oxidisers():
    """'Why would a user ever choose LOX as fuel?' They should not be able to."""
    lib = M.library_choices(assumptions())
    fuels = {v for v, _ in lib["stages.*.fuel"]}
    oxes = {v for v, _ in lib["stages.*.oxidizer"]}
    assert "LOX" in oxes and "LOX" not in fuels, "LOX must not be offered as a fuel"
    assert "RP-1" in fuels and "RP-1" not in oxes, "kerosene must not be offered as an oxidiser"
    assert not (fuels & oxes), f"no propellant should be in both lists: {fuels & oxes}"
    assert fuels | oxes == set(assumptions()["propellants"]), \
        "every propellant must still be reachable in one list or the other"
    # and the split comes from the library, not from a list in the code
    for name, p in assumptions()["propellants"].items():
        role = p["role"]["v"]
        assert name in (oxes if role == "oxidizer" else fuels), f"{name} declares {role} but is not offered as one"


def test_an_untagged_propellant_is_offered_in_both_lists_rather_than_disappearing():
    """A gap in the library must not make a propellant unreachable."""
    import copy
    a = copy.deepcopy(assumptions())
    a["propellants"]["Mystery"] = {"density_kg_m3": {"v": 900.0, "u": "kg/m^3", "d": "x", "s": "x", "t": "assumed"}}
    lib = M.library_choices(a)
    assert "Mystery" in {v for v, _ in lib["stages.*.fuel"]}
    assert "Mystery" in {v for v, _ in lib["stages.*.oxidizer"]}


def test_the_libraries_are_split_one_fold_per_entry_instead_of_one_huge_list():
    """132 combination rows in a single fold is unreadable, and is how a reader concludes the tank is
    always sized for LOX: the first 'Density' they scroll to is LOX's."""
    d = described()
    folds = {}
    for it in d["items"]:
        folds.setdefault((it["section"], it["topic"]), 0)
        folds[(it["section"], it["topic"])] += 1

    combo_folds = [k for k in folds if k[0] == "Propellant combinations"]
    prop_folds = [k for k in folds if k[0] == "Propellant library"]
    assert len(combo_folds) >= 12, "each combination needs its own fold"
    assert len(prop_folds) >= 15, "each propellant needs its own fold"
    assert ("Propellant combinations", "LOX/RP-1") in folds
    assert ("Propellant library", "LOX") in folds
    for k in combo_folds + prop_folds:
        assert folds[k] <= 14, f"{k} still has {folds[k]} rows in one fold"


def test_library_fields_are_labelled_in_words_not_mangled_variable_names():
    d = described()
    by = {it["path"]: it["label"] for it in d["items"]}
    assert by["propellants.LOX.density_kg_m3"] == "Density"
    assert by["propellants.LOX.tank_mer_per_kg"] == "Tank mass per kg of this propellant"
    assert by["propellant_combinations.LOX/RP-1.of_ratio_flight"] == "O/F as actually flown"
    for it in d["items"]:
        lab = it["label"]
        assert "_" not in lab and not lab.endswith((" kg", " per")), f"{it['path']} -> {lab!r}"


def test_tank_order_is_a_choice_of_two_not_a_list_to_type():
    lib = M.library_choices(assumptions())
    ch = M.choices_for("stages.0.tank.order_bottom_to_top", lib)
    assert ch and len(ch) == 2, ch
    values = {v for v, _ in ch}
    assert values == {"fuel,oxidizer", "oxidizer,fuel"}
    for _v, lab in ch:
        assert "bottom" in lab.lower(), f"the label must say which end is which: {lab!r}"


def test_picking_a_combination_tells_the_page_what_propellants_it_implies():
    m = M.combination_map(assumptions())
    assert len(m) >= 12
    assert m["LOX/RP-1"]["fuel"] == "RP-1" and m["LOX/RP-1"]["oxidizer"] == "LOX"
    assert m["LOX/LH2"]["fuel"] == "LH2"
    for name, c in m.items():
        assert c["fuel"] and c["oxidizer"], name
        assert c["of_ratio"] is None or c["of_ratio"] > 0, name
        # the name itself is oxidiser/fuel, so the map must agree with it
        ox, _, fu = name.partition("/")
        assert c["oxidizer"] == ox and c["fuel"] == fu, f"{name} disagrees with its own entry: {c}"


def test_every_stage_section_opens_however_many_stages_there_are():
    """OPEN_SECTIONS named Stage 1 and Stage 2 only, because it was written when every design had two.
    A three-stage design therefore opened with its third stage folded away, and a stage added with the
    stage-count control arrived collapsed - with the fields the user had just been told to fill hidden
    behind a disclosure labelled as housekeeping."""
    import os
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(root, "src"))
    from launch_vehicle import gui_meta, webgui
    for design, n in (("config/default_design.yaml", 2),
                      ("examples/example_3stage_leo.yaml", 3),
                      ("validation/scout_g1.yaml", 4)):
        out = webgui.design_inputs(os.path.join(root, design), webgui.DEFAULT_ASSUMPTIONS, describe=True)
        opened = [s for s in out["open_sections"] if s.startswith("Stage ")]
        assert len(opened) == n, f"{design}: {n} stages but {len(opened)} stage sections open: {opened}"
        for i in range(1, n + 1):
            assert f"Stage {i}" in opened, f"{design}: Stage {i} would arrive collapsed"
    # and the helper must not invent sections the design does not have
    assert "Stage 9" not in gui_meta.open_sections_for([{"section": "Stage 1"}, {"section": "Mission"}])


def test_the_liquid_or_solid_switch_is_never_folded_away_as_an_assumption():
    """A liquid design does not spell out `stage_type` - liquid is the default - so the row is synthesised
    and honestly tagged `assumed`. The panel folds assumptions away, which put the one control that turns a
    stage into a solid motor behind a disclosure reading "N assumed or unused values". A control that
    changes the SHAPE of the design is not an assumption."""
    import os
    import re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "src", "launch_vehicle", "gui_static", "index.html"), encoding="utf-8") as fh:
        page = fh.read()
    assert "SHAPE_FIELD_RE" in page, "the page has no rule keeping shape controls out of the fold"
    m = re.search(r"const SHAPE_FIELD_RE = (/.+?/);", page)
    assert m, "SHAPE_FIELD_RE is not a literal regex any more; check the fold rule still covers stage_type"
    assert "stage_type" in m.group(1), f"the shape rule no longer matches stage_type: {m.group(1)}"
    # the filter that decides what shows must consult it
    assert re.search(r"SHAPE_FIELD_RE\.test\(r\.path\)", page), \
        "SHAPE_FIELD_RE exists but the specification filter does not use it"


# ------------------------------------------------------------------ names and units a first-time user reads
def _described(design):
    from launch_vehicle import webgui, paths
    out = webgui.design_inputs(os.path.join(paths.ROOT, design),
                               os.path.join(paths.ROOT, "config", "engineering_assumptions.yaml"))
    return M.describe_inputs(out["items"])


def test_no_design_input_is_labelled_with_a_bare_noun_or_a_raw_key():
    """A first-time-user audit at v1.1 found "Diameter", "Length", "Material", "Kind", "Paf a", "Tol" and
    "User mass fuel": names that do not say what the number is of. Design inputs must not fall back to those;
    the libraries are exempt, because their fold already names the propellant or material."""
    bare = {"Diameter", "Length", "Material", "Kind", "Max length", "Type", "Tol", "Relax", "Max iter"}
    for design in ("config/default_design.yaml", "examples/example_boosters.yaml",
                   "examples/example_solid_smallsat.yaml"):
        for row in _described(design):
            if row["section"].endswith("library") or row["section"] == "Propellant combinations":
                continue
            assert row["label"] not in bare, (row["path"], row["label"])
            assert not row["label"].startswith(("Paf ", "User mass", "Engine a", "Engine b", "Engine c")), row["path"]
            assert row["topic"] not in ("Mer", "Mer Scatter"), row["path"]


def test_pressures_thrusts_and_gauges_are_shown_in_a_designers_units_and_the_file_stays_si():
    rows = {M.normalise(r["path"]): r for r in _described("config/default_design.yaml")}
    cases = {"stages.*.engine.chamber_pressure_Pa": ("bar", 1.0e5), "stages.*.tank.pressure_fuel_Pa": ("bar", 1.0e5),
             "constraints.max_dynamic_pressure_Pa": ("kPa", 1.0e3),
             "stages.*.engine.thrust_vac_per_engine_N": ("kN", 1.0e3),
             "stages.*.tank.wall_thickness_assumed_m": ("mm", 1.0e-3)}
    for path, (unit, factor) in cases.items():
        r = rows[path]
        assert (r["display_units"], r["display_factor"]) == (unit, factor), path
        assert r["units"] in ("Pa", "N", "m"), "the file's own unit must stay SI"
    assert rows["stages.*.engine.chamber_pressure_Pa"]["value"] == 7093000.0      # untouched: still pascals
    assert "display_units" not in rows["mission.payload_mass_kg"]
    with open(os.path.join(os.path.dirname(M.__file__), "gui_static", "index.html"), encoding="utf-8") as fh:
        page = fh.read()
    assert "shown(toShown(val, it))" in page and "fromShown(parseVal(" in page
    assert 'it.display_units || (it.units === "-"' in page


def test_the_page_formats_numbers_one_way_whatever_the_locale():
    with open(os.path.join(os.path.dirname(M.__file__), "gui_static", "index.html"), encoding="utf-8") as fh:
        page = fh.read()
    assert 'toLocaleString("en-US"' in page and "toLocaleString(undefined" not in page


# ------------------------------------------------------------------ inputs that depend on a choice
DESIGNS = ("config/default_design.yaml", "examples/example_boosters.yaml", "examples/example_solid_smallsat.yaml")


def test_every_dependent_input_names_a_real_choice_and_real_values():
    """An input hidden unless a choice has one of some values is lost for good if the rule names a choice that
    does not exist or a value the choice cannot take."""
    seen = set()
    for design in DESIGNS:
        rows = {r["path"]: r for r in _described(design)}
        for r in rows.values():
            sw = r.get("shown_when")
            if not sw:
                continue
            seen.add(M.normalise(r["path"]))
            ctrl = rows[sw["path"]]
            assert ctrl.get("controls"), sw["path"]
            assert ctrl["section"] == r["section"] and ctrl["topic"] == r["topic"], r["path"]
            if ctrl["choices"]:
                legal = {c["value"] for c in ctrl["choices"]}
                assert set(sw["values"]) <= legal, (r["path"], sw["values"], legal)
            else:
                assert sw["values"] == [True] and ctrl["type"] == "bool", r["path"]
    assert len(seen) >= 25, "most of the rules must be exercised by the shipped designs"


def test_a_dependent_input_sits_directly_under_its_choice_and_picks_lead_their_fold():
    rows = _described("config/default_design.yaml")
    paths = [r["path"] for r in rows]
    for r in rows:
        sw = r.get("shown_when")
        if not sw:
            continue
        i, j = paths.index(sw["path"]), paths.index(r["path"])
        between = rows[i + 1:j]
        assert j > i and all(x.get("shown_when", {}).get("path") == sw["path"] for x in between), r["path"]
    engine = [r for r in rows if r["section"] == "Stage 1" and r["topic"] == "Engine"]
    assert engine[0]["path"].endswith("engine.from_database")
    props = [r for r in rows if r["section"] == "Stage 1" and r["topic"] == "Propellants and size"]
    assert props[0]["path"].endswith("propellant_combination")


def test_the_characteristic_velocity_has_a_field_even_though_no_shipped_design_states_it():
    rows = {r["path"]: r for r in _described("config/default_design.yaml")}
    c = rows["stages[0].engine.cstar_mps"]
    assert c["value"] is None and c["units"] == "m/s"
    assert c["shown_when"] == {"path": "stages[0].engine.geometry_method", "values": ["book_mer"], "required": True}
    assert "stages[0].motor.cstar_mps" not in rows
    solid = {r["path"] for r in _described("examples/example_solid_smallsat.yaml")}
    assert not any(p.endswith("engine.cstar_mps") for p in solid), "a solid stage has no engine block"


def test_the_page_hides_what_the_chosen_method_does_not_read():
    with open(os.path.join(os.path.dirname(M.__file__), "gui_static", "index.html"), encoding="utf-8") as fh:
        page = fh.read()
    assert "function hiddenByChoice(it)" in page and "if (hiddenByChoice(it)) continue;" in page
    assert "r.controls || !!r.shown_when" in page
    assert "it.shown_when.required && isBlank(val0)" in page
