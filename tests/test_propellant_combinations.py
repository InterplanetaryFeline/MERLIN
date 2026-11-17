"""Propellant combinations: mixture ratio, bulk density and reference thermochemistry.

The library is mostly the book's Table 4.10 (p.240) transcribed, so the tests that matter are the ones that
check the transcription against something independent rather than against itself. Two do that:

  * every Table 4.10 row's printed specific gravity is recomputed from the component densities in
    `propellants` and the row's own mixture ratio. Six of the seven agree inside 2 %, and the two that do not
    are explained rather than tuned away;
  * that same identity, run with the Aerozine-50 density Table 4.6 PRINTS (1,450 kg/m^3) instead of the
    corrected 903, gives 1.45 against Table 4.10's printed 1.21 - which is independent confirmation, from the
    book's own two tables, that the Table 4.6 figure is a misprint duplicating the N2O4 row above it.

The rest check the rule the module exists to enforce: a named combination fills what the stage left out, never
overrides what it states, and says so when the two disagree.
"""
import math
import os

import pytest
import yaml
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import propellant_db as pdb
from launch_vehicle.config_io import _Loader, load_design
from launch_vehicle.convergence import size_vehicle
from launch_vehicle.validation import validate_spec

_C = {}


def assumptions():
    if "a" not in _C:
        _C["a"] = yaml.load(open(ASSUMP), Loader=_Loader)
    return _C["a"]


def combos():
    return pdb.load(assumptions())


def densities(override=None):
    """{name: object with .density_kg_m3}, as PropellantSpec presents it."""
    out = {}
    for k, v in assumptions()["propellants"].items():
        rho = (override or {}).get(k, v["density_kg_m3"]["v"])
        out[k] = type("P", (), {"density_kg_m3": rho})()
    return out


# ------------------------------------------------------------------- the library itself
def test_every_combination_names_propellants_the_library_actually_has():
    props = assumptions()["propellants"]
    for name, c in combos().items():
        assert c.oxidizer in props, f"{name}: unknown oxidizer {c.oxidizer!r}"
        assert c.fuel in props, f"{name}: unknown fuel {c.fuel!r}"
        assert c.of_ratio is not None and c.of_ratio > 0, f"{name}: no usable mixture ratio"


def test_every_combination_carries_a_source():
    for name, c in combos().items():
        assert c.source and len(c.source) > 20, f"{name}: no source worth the name"


def test_the_book_rows_are_transcribed_from_table_4_10():
    """Spot-check the four corners of the book's table rather than every cell."""
    c = combos()
    assert c["LOX/RP-1"].of_ratio_optimum == pytest.approx(2.56)      # shifting equilibrium, lower row
    assert c["LOX/RP-1"].of_ratio_optimum_frozen == pytest.approx(2.24)
    assert c["LOX/RP-1"].isp_ref_s == pytest.approx(300.0)
    assert c["LOX/RP-1"].cstar_ref_mps == pytest.approx(1804.0)
    assert c["LOX/LH2"].isp_ref_s == pytest.approx(391.0)
    assert c["LOX/LH2"].Tc_ref_K == pytest.approx(2724.0)
    assert c["N2O4/A-50"].of_ratio_optimum == pytest.approx(2.00)
    assert c["LOX/N2H4"].of_ratio_optimum_frozen == pytest.approx(0.74)


def test_shifting_equilibrium_always_beats_frozen():
    """The book prints frozen above and shifting below; shifting must be the higher Isp, every row."""
    checked = 0
    for name, c in combos().items():
        if c.isp_ref_s is None or c.isp_ref_frozen_s is None:
            continue
        assert c.isp_ref_s > c.isp_ref_frozen_s, f"{name}: frozen Isp exceeds shifting"
        checked += 1
    assert checked >= 7, "the seven Table 4.10 rows should all carry both values"


def test_the_table_4_5_rows_are_the_reciprocal_of_what_the_book_prints():
    """Table 4.5 gives fuel per kg of LOx; the tool stores O/F, so it must be the reciprocal.

    The two tables can be checked against each other for RP-1: Table 4.5's 0.43 inverts to 2.33, which sits
    between Table 4.10's frozen 2.24 and shifting 2.56 optima. They agree.
    """
    c = combos()
    assert c["LOX/LCH4"].of_ratio_optimum == pytest.approx(1 / 0.41, abs=0.01)
    assert c["LOX/Propane"].of_ratio_optimum == pytest.approx(1 / 0.34, abs=0.01)
    rp1_from_table_4_5 = 1 / 0.43
    assert c["LOX/RP-1"].of_ratio_optimum_frozen < rp1_from_table_4_5 < c["LOX/RP-1"].of_ratio_optimum


def test_flight_ratios_differ_from_the_optimum_where_the_book_says_they_do():
    """Hydrogen engines run far richer than peak Isp, and the library must not flatten that away."""
    c = combos()["LOX/LH2"]
    assert c.of_ratio_optimum == pytest.approx(4.02)
    assert c.of_ratio_flight == pytest.approx(5.50)             # J-2, book Table 4.12 p.242
    assert c.of_ratio == c.of_ratio_flight, "a stage must get the flown ratio, not the ideal one"
    assert c.of_ratio_flight / c.of_ratio_optimum > 1.3, "the gap is large and is the point of carrying both"


# -------------------------------------------------- bulk density: the independent check on the transcription
def test_computed_bulk_density_reproduces_the_books_printed_specific_gravity():
    """rho_bulk = (1+r)/(r/rho_ox + 1/rho_fuel), against the S.G. column of Table 4.10.

    Evaluated at each row's OWN optimum ratio, which is the ratio that row describes. Six of the seven agree
    inside 2 %. The exception is LOX/Ethanol at -4.6 %, and it is explained rather than fitted: the book's row
    is 75 % ethanol / 25 % water, roughly 7 % denser than the pure ethanol the propellant library carries.
    """
    props = densities()
    checked, worst = 0, 0.0
    for name, c in combos().items():
        if c.bulk_sg_book is None or c.of_ratio_optimum is None:
            continue
        rho = pdb.bulk_density_kg_m3(c, props, c.of_ratio_optimum)
        err = abs(rho / 1000.0 - c.bulk_sg_book) / c.bulk_sg_book
        if name == "LOX/Ethanol":
            assert 0.03 < err < 0.06, "the 75 %-ethanol gap should be about 4.6 %"
            continue
        if name == "HTP-98/RP-1":
            # not a book row: the source computes its 1.295 with RP-1 at 773 kg/m^3, not this tool's 820
            assert err < 0.03
            continue
        assert err < 0.02, f"{name}: computed S.G. {rho / 1000:.3f} vs book {c.bulk_sg_book}"
        worst = max(worst, err)
        checked += 1
    assert checked >= 6, "at least six book rows should be checkable"
    assert worst < 0.02


def test_the_same_identity_exposes_the_aerozine_50_misprint():
    """Table 4.6 prints 1,450 kg/m^3 for Aerozine 50 - the same number as the N2O4 row directly above it.

    Table 4.10 prints a mixture specific gravity of 1.21 for N2O4/Aerozine-50 at O/F 2.00. With a fuel density
    of 903 kg/m^3 the identity gives 1.21; with the 1,450 Table 4.6 prints it gives 1.45, 20 % away from the
    book's own figure. The book contradicts itself, and the corrected density is the one that closes.
    """
    c = combos()["N2O4/A-50"]
    good = pdb.bulk_density_kg_m3(c, densities(), c.of_ratio_optimum) / 1000.0
    printed = pdb.bulk_density_kg_m3(c, densities({"A-50": 1450.0}), c.of_ratio_optimum) / 1000.0
    assert good == pytest.approx(c.bulk_sg_book, rel=0.01), "the corrected density closes on Table 4.10"
    assert printed == pytest.approx(1.45, rel=0.01)
    assert abs(printed - c.bulk_sg_book) / c.bulk_sg_book > 0.15, "and the printed one is nowhere near"


def test_bulk_density_sits_between_the_two_components():
    for name, c in combos().items():
        rho = pdb.bulk_density_kg_m3(c, densities())
        lo = min(densities()[c.oxidizer].density_kg_m3, densities()[c.fuel].density_kg_m3)
        hi = max(densities()[c.oxidizer].density_kg_m3, densities()[c.fuel].density_kg_m3)
        assert lo <= rho <= hi, f"{name}: bulk density {rho} outside [{lo}, {hi}]"


def test_bulk_density_moves_the_right_way_with_mixture_ratio():
    """More of the denser propellant must make the mixture denser. LOX is denser than RP-1."""
    c = combos()["LOX/RP-1"]
    props = densities()
    lean = pdb.bulk_density_kg_m3(c, props, 1.5)
    rich = pdb.bulk_density_kg_m3(c, props, 3.5)
    assert rich > lean
    # and at the extremes it must tend to the pure components
    assert pdb.bulk_density_kg_m3(c, props, 1e6) == pytest.approx(props["LOX"].density_kg_m3, rel=1e-4)
    assert pdb.bulk_density_kg_m3(c, props, 1e-6) == pytest.approx(props["RP-1"].density_kg_m3, rel=1e-4)


def test_hydrogen_is_the_bulky_one_and_peroxide_the_dense_one():
    """The ordering that actually decides tank volume, as a sanity check on the whole library."""
    props = densities()
    rho = {n: pdb.bulk_density_kg_m3(c, props) for n, c in combos().items()}
    assert rho["LOX/LH2"] < 400, "hydrogen stages are mostly volume"
    assert rho["HTP-98/RP-1"] > rho["LOX/RP-1"] > rho["LOX/LCH4"] > rho["LOX/LH2"]
    assert rho["HTP-98/RP-1"] > 1250, "peroxide/kerosene is the dense option, which is its whole appeal"


def test_density_impulse_ranks_combinations_differently_from_isp():
    """Hydrogen wins on Isp and loses badly on density impulse - the trade the figure of merit exists for."""
    props = densities()
    h2, rp1 = combos()["LOX/LH2"], combos()["LOX/RP-1"]
    assert h2.isp_ref_s > rp1.isp_ref_s
    assert pdb.density_impulse_s_kg_m3(h2, props) < pdb.density_impulse_s_kg_m3(rp1, props)


def test_missing_data_returns_none_rather_than_a_guess():
    c = combos()["LOX/RP-1"]
    assert pdb.bulk_density_kg_m3(c, {}) is None
    assert pdb.bulk_density_kg_m3(c, densities(), 0.0) is None
    assert pdb.density_impulse_s_kg_m3(combos()["HTP-90/RP-1"], densities(), None) is not None
    assert pdb.density_impulse_s_kg_m3(combos()["LOX/LCH4"], densities()) is not None


# ---------------------------------------------------------------- the HTP rows the book does not have
def test_the_peroxide_rows_are_present_and_sourced_outside_the_book():
    c = combos()
    for name in ("HTP-90/RP-1", "HTP-98/RP-1"):
        assert name in c
        assert "Book" not in c[name].source, f"{name} is not in the book and must not claim to be"
    assert c["HTP-90/RP-1"].of_ratio_flight == pytest.approx(6.5)     # AR2-3, NASA MSFC
    assert c["HTP-98/RP-1"].of_ratio_optimum == pytest.approx(7.38)   # Krishnan et al.
    assert c["HTP-98/RP-1"].of_ratio_flight == pytest.approx(7.5)


def test_peroxide_runs_far_richer_in_oxidiser_than_lox_does():
    """Peroxide is mostly water and carries its own oxygen, so it takes a lot of it per kg of fuel."""
    c = combos()
    assert c["HTP-98/RP-1"].of_ratio > 2.5 * c["LOX/RP-1"].of_ratio


def test_the_two_peroxide_grades_differ_in_density_as_published():
    props = assumptions()["propellants"]
    assert props["HTP-98"]["density_kg_m3"]["v"] == pytest.approx(1431.0)
    assert props["HTP-90"]["density_kg_m3"]["v"] < props["HTP-98"]["density_kg_m3"]["v"]
    assert props["HTP-90"]["density_kg_m3"]["t"] == "assumed", \
        "the 90 % density is interpolated, not published, and must say so"
    assert props["HTP-98"]["density_kg_m3"]["t"] == "reference"


# ---------------------------------------------------------------------- resolving into a design
def with_combination(name, tank_method=None, **stage_extra):
    """custom_spec hands `modify` the design ALREADY UNWRAPPED, so values here are plain, not {v,u,d,s,t}."""
    def modify(design, assump):
        st = design["stages"][0]
        for k in ("fuel", "oxidizer", "mixture_ratio_OF"):
            st.pop(k, None)
        st["propellant_combination"] = name
        if tank_method:                    # Table 8.6 has no MER for every propellant; see the test below
            st["tank"]["mass_method_fuel"] = tank_method
            st["tank"]["mass_method_oxidizer"] = tank_method
        st.update(stage_extra)
    return modify


def test_a_named_combination_fills_the_propellants_and_the_mixture_ratio():
    spec = custom_spec(with_combination("LOX/LCH4"))
    st = spec.stages[0]
    assert st.fuel == "LCH4" and st.oxidizer == "LOX"
    assert st.of_ratio == pytest.approx(2.44, abs=0.01)
    note = spec.propellant_combination_notes[0]
    assert set(note["filled"]) == {"fuel", "oxidizer", "mixture_ratio_OF"}
    assert note["entry"] == "LOX/LCH4"


def test_what_the_stage_states_always_wins():
    spec = custom_spec(with_combination("LOX/RP-1", mixture_ratio_OF=2.9))
    assert spec.stages[0].of_ratio == pytest.approx(2.9)
    assert "mixture_ratio_OF" not in spec.propellant_combination_notes[0]["filled"]


def test_a_stage_that_contradicts_its_own_combination_is_warned_about():
    spec = custom_spec(with_combination("LOX/RP-1", fuel="LH2"))
    note = spec.propellant_combination_notes[0]
    assert note["mismatched"] and note["mismatched"][0]["field"] == "fuel"
    codes = {i.code for i in validate_spec(spec)}
    assert "COMBOMM" in codes


def test_an_unknown_combination_is_refused_with_the_list_of_known_ones():
    with pytest.raises(pdb.PropellantDBError, match="LOX/RP-1"):
        custom_spec(with_combination("LOX/Unobtainium"))


def test_a_solid_stage_cannot_name_a_combination():
    def modify(design, assump):
        design["stages"][0]["stage_type"] = "solid"
        design["stages"][0]["propellant_combination"] = "LOX/RP-1"
    with pytest.raises(pdb.PropellantDBError, match="solid"):
        custom_spec(modify)


def test_a_filled_value_enters_the_input_register_with_the_librarys_source():
    spec = custom_spec(with_combination("N2O4/A-50"))
    rows = [r for r in spec.inputs_register if r.get("path", "").endswith("mixture_ratio_OF")
            and "combination" in str(r.get("source", ""))]
    assert rows, "the filled mixture ratio is not in the input register"
    assert rows[0]["provenance"] == "reference"
    assert "Table 4.14" in rows[0]["source"] or "Table 4.10" in rows[0]["source"]


def test_a_vehicle_built_from_a_combination_sizes():
    """The point of the library: naming a combination must give a design that actually runs."""
    spec = custom_spec(with_combination("HTP-98/RP-1", tank_method="akin_volume"))
    res = size_vehicle(spec)
    assert res.converged
    assert spec.stages[0].of_ratio == pytest.approx(7.5)


def test_a_propellant_with_no_table_8_6_mer_is_refused_rather_than_sized_on_a_wrong_one():
    """Table 8.6 covers LOX, RP-1 and LH2 only. Peroxide has no row, and borrowing kerosene's would be wrong.

    This is the right failure: the tool stops and names the two tank-mass methods that do apply, instead of
    quietly sizing a 1,431 kg/m^3 oxidiser tank with a coefficient fitted to 820 kg/m^3 kerosene.
    """
    from launch_vehicle.validation import InputError
    with pytest.raises(InputError, match="HTP-98") as e:        # refused before sizing since v1.1, with a field
        size_vehicle(custom_spec(with_combination("HTP-98/RP-1")))
    assert e.value.field == "stages[0].tank.mass_method_oxidizer"
    assert {o["value"] for o in e.value.options} == {"akin_volume", "pressure_vessel"}


def test_switching_combination_shrinks_the_tanks_but_does_not_touch_isp():
    """Changing combination changes the PROPELLANTS and the mixture ratio - deliberately not the Isp.

    The library carries a theoretical Isp at a stated reference condition, and filling it into a stage as if it
    were a delivered vacuum Isp would be wrong by tens of seconds in either direction, so it is not filled. What
    does change is the density: peroxide/kerosene at O/F 7.5 is about 29 % denser than LOX/kerosene at 2.27, so
    the same propellant mass needs visibly less tank.
    """
    lox = custom_spec(with_combination("LOX/RP-1", tank_method="akin_volume"))
    htp = custom_spec(with_combination("HTP-98/RP-1", tank_method="akin_volume"))
    assert lox.stages[0].engine.isp_vac_s == htp.stages[0].engine.isp_vac_s, \
        "naming a combination must not silently rewrite the engine's specific impulse"
    rl = size_vehicle(lox)
    rh = size_vehicle(htp)
    props = densities()
    rho_lox = pdb.bulk_density_kg_m3(combos()["LOX/RP-1"], props)
    rho_htp = pdb.bulk_density_kg_m3(combos()["HTP-98/RP-1"], props)
    assert rho_htp > 1.2 * rho_lox
    vol = lambda r: sum(t.V_int for s in r.stages for t in (getattr(s, "tanks", None) or []))
    if vol(rl) and vol(rh):
        assert vol(rh) / rh.stages[0].m_prop_loaded_kg < vol(rl) / rl.stages[0].m_prop_loaded_kg


# ------------------------------------------------------------------ the engine database does the same
def test_naming_an_engine_also_supplies_its_propellants_and_mixture_ratio():
    def modify(design, assump):
        st = design["stages"][0]
        for k in ("fuel", "oxidizer", "mixture_ratio_OF"):
            st.pop(k, None)
        st["engine"]["from_database"] = "RD-180"
        st["engine"]["thrust_to_weight_ignition"] = 1.3
    spec = custom_spec(modify)
    st = spec.stages[0]
    assert (st.fuel, st.oxidizer) == ("RP-1", "LOX")
    assert st.of_ratio == pytest.approx(2.72)                  # RD-180's own ratio, book Table 4.14
