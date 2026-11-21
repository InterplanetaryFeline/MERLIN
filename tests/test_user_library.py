"""Your own propellants and tank materials (user_library.py), and the library values the GUI can change.

Two things are pinned here. The new capability: an entry added from the GUI's Library dialog is validated,
annotated like the shipped library, offered in the dropdowns, sized with, and carried inside any design saved
with it. And a bug found while building it: changing ANY library value in the GUI (the density of RP-1, say)
made sizing fail with a KeyError, because the override was written into the design instead of the library.
"""
import os
import tempfile

import pytest
import yaml
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import user_library as ul, webgui
from launch_vehicle.config_io import load_design
from launch_vehicle.convergence import size_vehicle

A = os.path.join(ROOT, "config", "engineering_assumptions.yaml")
D = os.path.join(ROOT, "config", "default_design.yaml")
FUEL = {"role": "fuel", "density_kg_m3": 860, "boiling_K": "", "insulation_kg_m2": "", "tank_mer_per_kg": ""}
ALLOY = {"name": "Aluminium-lithium 2195-T8", "rho_kg_m3": 2710, "yield_min_Pa": 490, "t_min_m": 1.2, "E_Pa": 76,
         "alpha_per_K": 22}


class _Scratch:
    """Point the personal library at a temporary file for the duration of a test, then put it back."""

    def __enter__(self):
        self.old = ul.USER_LIBRARY_PATH
        self.dir = tempfile.mkdtemp()
        ul.USER_LIBRARY_PATH = os.path.join(self.dir, "my_library.yaml")
        return self

    def __exit__(self, *exc):
        ul.USER_LIBRARY_PATH = self.old
        return False


def test_an_entry_is_annotated_and_blank_fields_are_unknown_or_a_stated_assumed_default():
    e = ul.build_entry("propellant", FUEL, "my estimate", "assumed")
    for k, leaf in e.items():
        assert set(leaf) == {"v", "u", "d", "s", "t"} and str(leaf["s"]).strip(), k
    assert e["density_kg_m3"]["v"] == 860.0 and e["density_kg_m3"]["s"] == "my estimate"
    assert e["boiling_K"]["v"] is None, "a blank boiling point means storable, not zero kelvin"
    assert e["insulation_kg_m2"]["v"] == 0.0 and e["insulation_kg_m2"]["t"] == "assumed"
    assert "Default" in e["insulation_kg_m2"]["s"]
    assert e["tank_mer_per_kg"]["v"] is None and e["tank_mer_ref_density"]["v"] is None


def test_a_material_is_stored_in_si_and_takes_the_shipped_allowable_basis_when_none_is_given():
    m = ul.build_entry("material", ALLOY, "a datasheet", "reference")
    assert m["yield_min_Pa"]["v"] == pytest.approx(490e6) and m["E_Pa"]["v"] == pytest.approx(76e9)
    assert m["t_min_m"]["v"] == pytest.approx(1.2e-3) and m["alpha_per_K"]["v"] == pytest.approx(22e-6)
    assert m["sigma_allow_Pa"]["v"] == pytest.approx(0.633 * 490e6) and m["sigma_allow_Pa"]["t"] == "assumed"
    with pytest.raises(ul.LibraryError) as e:
        ul.build_entry("material", dict(ALLOY, sigma_allow_Pa=600), "a datasheet", "reference")
    assert e.value.field == "sigma_allow_Pa"


def test_an_entry_without_a_source_a_number_out_of_range_or_a_missing_field_is_refused_at_its_field():
    for values, source, field in ((FUEL, "", "source"), (dict(FUEL, density_kg_m3=99999), "x", "density_kg_m3"),
                                  (dict(FUEL, density_kg_m3=""), "x", "density_kg_m3"),
                                  (dict(FUEL, role="propellant"), "x", "role"),
                                  (dict(FUEL, density_kg_m3="heavy"), "x", "density_kg_m3")):
        with pytest.raises(ul.LibraryError) as e:
            ul.build_entry("propellant", values, source, "user")
        assert e.value.field == field, (values, e.value.field)


def test_a_name_must_be_new_and_safe_to_use_as_an_input_path():
    with _Scratch():
        for bad in ("RP-1", "Al.2195", "a[0]", "", " "):
            kind = "propellant"
            with pytest.raises(ul.LibraryError) as e:
                ul.add(kind, bad, FUEL, "x")
            assert e.value.field == "entry_name", bad
        ul.add("propellant", "Ethanol-75", FUEL, "x")
        with pytest.raises(ul.LibraryError):
            ul.add("propellant", "Ethanol-75", FUEL, "x")
        ul.add("propellant", "Ethanol-75", dict(FUEL, density_kg_m3=870), "x", replace=True)
        assert ul.listing()["propellant"][0]["values"]["density_kg_m3"] == 870.0
        assert ul.remove("propellant", "Ethanol-75") and not ul.listing()["propellant"]
        assert not ul.remove("propellant", "RP-1"), "a shipped entry is not the personal library's to remove"


def test_custom_entries_are_offered_marked_as_yours_and_are_sized_with():
    with _Scratch():
        ul.add("propellant", "Ethanol-75", FUEL, "my estimate", "assumed")
        ul.add("material", "Al-Li 2195", ALLOY, "a datasheet", "reference")
        items = {i["path"]: i for i in webgui.design_inputs(D, A, describe=True)["items"]}
        fuel = {c["value"]: c["label"] for c in items["stages[0].fuel"]["choices"]}
        oxid = {c["value"] for c in items["stages[0].oxidizer"]["choices"]}
        assert fuel["Ethanol-75"] == "Ethanol-75 (my library)" and "Ethanol-75" not in oxid
        mat = {c["value"]: c["label"] for c in items["stages[0].tank.material"]["choices"]}
        assert mat["Al-Li 2195"].endswith("(my library)") and "Aluminium-lithium" in mat["Al-Li 2195"]
        assert "propellants.Ethanol-75.density_kg_m3" in items, "the entry's values are in the panel like any other"
        ov = {"stages.0.fuel": "Ethanol-75", "stages.0.tank.mass_method_fuel": "akin_volume",
              "stages.0.tank.material": "Al-Li 2195", "stages.0.tank.mass_method_oxidizer": "pressure_vessel"}
        spec = load_design(D, A, ov)
        assert spec.propellants["Ethanol-75"].density_kg_m3 == 860.0
        assert spec.stages[0].tank.material.sigma_allow_Pa == pytest.approx(0.633 * 490e6)
        assert size_vehicle(spec, keep_history=False).glom_kg > 0


def test_changing_a_shipped_library_value_in_the_gui_reaches_the_sizing():
    """It used to raise KeyError: 'propellants', so no library value could be changed from the GUI at all."""
    base_spec = load_design(D, A)
    base = size_vehicle(base_spec, keep_history=False)
    spec = load_design(D, A, {"propellants.RP-1.density_kg_m3": 800.0})
    assert spec.propellants["RP-1"].density_kg_m3 == 800.0
    got = size_vehicle(spec, keep_history=False)
    # lighter fuel than RP-1's 820 kg/m^3 needs a longer fuel tank for the same mass
    assert got.geometry.total_length > base.geometry.total_length
    assert got.glom_kg > base.glom_kg
    r = webgui.run_sizing(D, A, {"propellants.RP-1.density_kg_m3": 800.0}, tempfile.mkdtemp(), "ul_t1")
    assert r["length_m"] > base.geometry.total_length - 1.0, "the GUI's own sizing call takes the value too"


def test_a_saved_design_carries_its_custom_entries_and_its_changed_library_values():
    with _Scratch() as sc:
        ul.add("propellant", "Ethanol-75", FUEL, "my estimate", "assumed")
        old = webgui.SAVE_DIR
        webgui.SAVE_DIR = sc.dir
        try:
            ov = {"stages.0.fuel": "Ethanol-75", "stages.0.tank.mass_method_fuel": "akin_volume",
                  "propellants.LOX.density_kg_m3": 1150.0}
            out = webgui.save_design(D, ov, "carry test", filename="carry_test")
        finally:
            webgui.SAVE_DIR = old
        saved = out["path"] if os.path.isabs(out["path"]) else os.path.join(ROOT, out["path"])
        with open(saved, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        lib = doc["library"]
        assert set(lib["propellants"]) == {"Ethanol-75", "LOX"}
        assert lib["propellants"]["LOX"]["density_kg_m3"]["v"] == 1150.0
        assert lib["propellants"]["LOX"]["density_kg_m3"]["t"] == "user"
        assert "propellants" not in doc and doc["stages"][0]["fuel"]["v"] == "Ethanol-75"
        ul.USER_LIBRARY_PATH = os.path.join(sc.dir, "somebody_elses_empty_library.yaml")
        spec = load_design(saved, A)
        assert spec.propellants["Ethanol-75"].density_kg_m3 == 860.0, "the design opens without the library"
        assert spec.propellants["LOX"].density_kg_m3 == 1150.0
        assert spec.propellants["RP-1"].density_kg_m3 == 820.0, "only the field that was changed moves"
        assert size_vehicle(spec, keep_history=False).glom_kg > 0


def test_a_designs_own_copy_wins_over_the_library():
    with _Scratch():
        ul.add("propellant", "Ethanol-75", dict(FUEL, density_kg_m3=900), "changed later", "user")
        extra = ul.extra_entries({"propellants": {"Ethanol-75": ul.build_entry("propellant", FUEL, "x", "user")}})
        assert extra["propellants"]["Ethanol-75"]["density_kg_m3"]["v"] == 860.0


def test_the_library_file_is_not_offered_as_a_design_and_the_gui_has_the_dialog():
    assert "my_library" in webgui.NOT_DESIGNS
    with open(os.path.join(os.path.dirname(webgui.__file__), "gui_static", "index.html"), encoding="utf-8") as fh:
        page = fh.read()
    for probe in ('id="dlgLibrary"', 'id="libBtn"', "function openLibrary(", "function saveLibrary(",
                  "LIB_TARGET_RE", '"+ own"', "F.draft = {name, values", 'id: "lib_entry_name"'):
        assert probe in page, probe


# ------------------------------------------------------------------ solid propellants and combinations
SOLID = {"density_kg_m3": 1780, "c_star_mps": 1550, "burn_rate_exponent": 0.33, "isp_note": "265 s at 70 bar"}
SMALLSAT = os.path.join(ROOT, "examples", "example_solid_smallsat.yaml")


def test_a_custom_solid_propellant_is_offered_on_solid_stages_and_sized_with():
    with _Scratch():
        ul.add("solid", "HTPB-AP-18Al", SOLID, "my datasheet", "reference")
        items = {i["path"]: i for i in webgui.design_inputs(SMALLSAT, A, describe=True)["items"]}
        labels = {c["value"]: c["label"] for c in items["stages[0].propellant"]["choices"]}
        assert labels["HTPB-AP-18Al"] == "HTPB-AP-18Al (my library)"
        spec = load_design(SMALLSAT, A, {"stages.0.propellant": "HTPB-AP-18Al"})
        sp = spec.solid_propellants["HTPB-AP-18Al"]
        assert (sp.density_kg_m3, sp.c_star_mps, sp.burn_rate_exponent) == (1780.0, 1550.0, 0.33)
        assert sp.source == "my datasheet"
        assert size_vehicle(spec, keep_history=False).glom_kg > 0


def test_a_solid_needs_both_ballistics_numbers_or_neither():
    for values in (dict(SOLID, burn_rate_exponent=""), dict(SOLID, c_star_mps="")):
        with pytest.raises(ul.LibraryError):
            ul.build_entry("solid", values, "x", "user")
    e = ul.build_entry("solid", dict(SOLID, c_star_mps="", burn_rate_exponent=""), "x", "user")
    assert e["c_star_mps"]["v"] is None and e["burn_rate_exponent"]["v"] is None


def test_a_custom_combination_names_real_liquids_and_carries_its_mixture_ratio_into_the_stage():
    with _Scratch():
        ul.add("propellant", "Ethanol-75", FUEL, "my estimate", "assumed")
        combo = {"oxidizer": "LOX", "fuel": "Ethanol-75", "of_ratio_flight": 1.3, "isp_ref_s": 279}
        for bad, field in ((dict(combo, fuel="Nope"), "fuel"), (dict(combo, fuel="LOX"), "fuel"),
                           (dict(combo, oxidizer="RP-1"), "oxidizer"), (dict(combo, of_ratio_flight=""), "of_ratio_flight")):
            with pytest.raises(ul.LibraryError) as e:
                ul.add("combination", "LOX/Bad", bad, "x")
            assert e.value.field == field, bad
        ul.add("combination", "LOX/Ethanol-75", combo, "A-4 figures", "reference")
        schema = {f["key"]: f for f in ul.schema_for_gui()["combination"]}
        assert "Ethanol-75" in schema["fuel"]["choices"] and "LOX" in schema["oxidizer"]["choices"]
        assert "LOX" not in schema["fuel"]["choices"]
        assert webgui._combination_map()["LOX/Ethanol-75"] == {"fuel": "Ethanol-75", "oxidizer": "LOX", "of_ratio": 1.3}
        items = {i["path"]: i for i in webgui.design_inputs(D, A, describe=True)["items"]}
        labels = {c["value"]: c["label"] for c in items["stages[0].propellant_combination"]["choices"]}
        assert labels["LOX/Ethanol-75"] == "LOX/Ethanol-75 (my library)"
        spec = load_design(D, A, {"stages.0.propellant_combination": "LOX/Ethanol-75", "stages.0.fuel": None,
                                  "stages.0.mixture_ratio_OF": None, "stages.0.tank.mass_method_fuel": "akin_volume"})
        assert spec.stages[0].fuel == "Ethanol-75" and spec.stages[0].of_ratio == 1.3
        assert size_vehicle(spec, keep_history=False).glom_kg > 0


def test_a_design_using_a_custom_combination_carries_the_fuel_it_names_too():
    with _Scratch():
        ul.add("propellant", "Ethanol-75", FUEL, "my estimate", "assumed")
        ul.add("combination", "LOX/Ethanol-75", {"oxidizer": "LOX", "fuel": "Ethanol-75", "of_ratio_flight": 1.3},
               "A-4 figures", "reference")
        with open(D, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        raw["stages"][0]["propellant_combination"] = {"v": "LOX/Ethanol-75"}
        copied = ul.embed_used(raw)
        assert set(copied) == {"Ethanol-75", "LOX/Ethanol-75"}
        assert set(raw["library"]) == {"propellants", "propellant_combinations"}


def test_the_form_offers_all_four_kinds_and_a_plus_button_for_each_kind_of_field():
    assert set(ul.schema_for_gui()) == {"propellant", "material", "solid", "combination"}
    with open(os.path.join(os.path.dirname(webgui.__file__), "gui_static", "index.html"), encoding="utf-8") as fh:
        page = fh.read()
    for probe in ('combination: "Propellant combination (oxidiser + fuel)"', 'solid: "Solid propellant"',
                  "propellant|propellant_combination", 'if (F.kind === "combination") applyCascade(target, name);',
                  "if (S.lib.combinations) S.combinations = S.lib.combinations;"):
        assert probe in page, probe


def test_a_cryogenic_fuel_in_an_uninsulated_tank_is_flagged_with_the_switch_that_fixes_it():
    """Found by sizing custom entries: insulation is a switch on the stage, so a stage moved to a cryogen kept a
    bare tank and was lighter than it should be, with nothing said. True of the shipped LH2 and LCH4 as well."""
    for fuel in ("LH2", "LCH4"):
        r = size_vehicle(load_design(D, A, {"stages.0.fuel": fuel, "stages.0.tank.mass_method_fuel": "akin_volume"}),
                         keep_history=False)
        w = [i for i in r.issues if i.code == "TANKINSUL"]
        assert w and w[0].field == "stages[0].tank.insulated_fuel", fuel
        assert w[0].options[0] == {"label": "Insulate stage 1's fuel tank", "path": "stages[0].tank.insulated_fuel",
                                   "value": True, "note": w[0].options[0]["note"]}
        fixed = size_vehicle(load_design(D, A, {"stages.0.fuel": fuel, "stages.0.tank.mass_method_fuel": "akin_volume",
                                                "stages.0.tank.insulated_fuel": True}), keep_history=False)
        assert not [i for i in fixed.issues if i.code == "TANKINSUL"]
        assert fixed.stages[0].components["Tank insulation (fuel)"] > 0
    assert not [i for i in size_vehicle(load_design(D, A), keep_history=False).issues if i.code == "TANKINSUL"], \
        "the default design insulates its LOX and has a storable fuel, so nothing to say"
