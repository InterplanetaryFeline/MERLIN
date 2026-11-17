"""Development cost and cost per flight (book Chapter 17).

Table 17.4 prints a complete worked verification of TRANSCOST against the Ariane 5 programme - reference mass,
CER work-years, every f-factor and the final work-years, for five elements - so this file re-runs all five.
Two reproduce exactly. The other three do not, in three different ways, and each is pinned so the agreement
cannot drift without a test noticing.
"""
import math
import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import cost as C

_C = {}


def estimate():
    if "e" not in _C:
        r = default_result()
        _C["r"], _C["e"] = r, C.estimate(r, year=2010)
    return _C["r"], _C["e"]


def a5(name):
    return C.ARIANE5_FACTORS[name]


def factors(d):
    return (d["f1"], d["f2"], d["f3"], d["f8"])


# ====================================================================== the five printed CERs
def test_the_cers_are_the_coefficients_printed_on_the_figures():
    """Figs. 17.12-17.16, read off the figure labels themselves."""
    assert (C.CERS["ES"].a, C.CERS["ES"].x) == (16.3, 0.54)
    assert (C.CERS["EL"].a, C.CERS["EL"].x) == (277.0, 0.48)
    assert (C.CERS["EP"].a, C.CERS["EP"].x) == (167.0, 0.35)
    assert (C.CERS["VR"].a, C.CERS["VR"].x) == (10.4, 0.60)
    assert (C.CERS["VS"].a, C.CERS["VS"].x) == (100.0, 0.555)
    for cer in C.CERS.values():
        assert cer.figure.startswith("Fig. 17.1")


def test_the_cer_is_a_power_law_in_mass():
    """Eq. 17.3: C = a M^x, so doubling the mass multiplies the effort by 2^x and nothing else."""
    for cer in C.CERS.values():
        assert cer.effort_wyr(2000.0) / cer.effort_wyr(1000.0) == pytest.approx(2.0 ** cer.x, rel=1e-12)
        assert cer.effort_wyr(0.0) == 0.0


# ====================================================================== Table 17.4, element by element
def test_both_engine_cers_reproduce_the_ariane_5_table_exactly():
    """The Vulcain on the turbopump CER and the Aestus on the pressure-fed one: both the raw CER value and
    the value after the table's own f-factors come out on the printed numbers."""
    for name in ("Vulcain engine", "Aestus engine"):
        d = a5(name)
        assert C.CERS[d["code"]].effort_wyr(d["mass_kg"]) == pytest.approx(d["wyr_cer"], rel=0.002), name
        got = C.element_effort_wyr(d["code"], d["mass_kg"], *factors(d))
        assert got["wyr"] == pytest.approx(d["wyr"], rel=0.002), name


def test_the_srb_row_closes_on_the_cer_value_not_on_its_printed_one():
    """H_VR = 10.4 M^0.60 at 39,300 kg gives 5,938 work-years, not the 5,398 the table prints. But the
    table's FINAL column, 5,056, is exactly 5,938 times its own f-factors - and is not 5,398 times them.
    So the final column was computed from the CER and the printed CER value is the slip."""
    d = a5("SRB")
    cer = C.CERS["VR"].effort_wyr(d["mass_kg"])
    assert cer == pytest.approx(5_938, rel=0.002)
    assert cer / d["wyr_cer"] == pytest.approx(1.10, abs=0.01), "10 % above what the table prints"
    fprod = d["f1"] * d["f3"] * d["f8"]
    assert cer * fprod == pytest.approx(d["wyr"], rel=0.002), "the CER value closes the row"
    assert d["wyr_cer"] * fprod != pytest.approx(d["wyr"], rel=0.02), "the printed value does not"


def test_the_third_stage_row_closes_internally_but_not_on_the_vehicle_cer():
    """Its printed CER and final columns are consistent with each other, so the row is self-contained - but
    the vehicle CER gives 5,116 work-years at 1,200 kg against the printed 7,689. The likeliest reading is
    that an equipment bay is not an expendable-vehicle element at all; TRANSCOST has codes the book does not
    print, and this is left as a difference rather than explained away."""
    d = a5("Third stage and equipment bay")
    fprod = d["f1"] * d["f2"] * d["f3"] * d["f8"]
    assert d["wyr_cer"] * fprod == pytest.approx(d["wyr"], rel=0.002), "the row is internally consistent"
    assert C.CERS["VS"].effort_wyr(d["mass_kg"]) == pytest.approx(5_116, rel=0.002)
    assert C.CERS["VS"].effort_wyr(d["mass_kg"]) / d["wyr_cer"] == pytest.approx(0.665, abs=0.01)


def test_the_vehicle_and_shroud_row_closes_on_neither():
    """Its f-factors multiply to 1.357, so its printed CER would give 26,715 work-years, not the 18,368 it
    prints; and no mass reproduces both columns. This row cannot be reconciled from what the book prints."""
    d = a5("Vehicle and shroud")
    fprod = d["f1"] * d["f2"] * d["f3"] * d["f8"]
    assert fprod == pytest.approx(1.357, abs=0.005)
    assert d["wyr_cer"] * fprod == pytest.approx(26_715, rel=0.01)
    assert d["wyr"] == 18_368, "which is not that"
    assert abs(d["wyr_cer"] * fprod / d["wyr"] - 1.0) > 0.4


def test_the_whole_ariane_5_programme_comes_out_within_seven_percent_of_actual():
    """End to end: the five elements through this module's CERs and the table's factors, with f0, against the
    39,300 work-years ESA actually spent. This module gives 41,679, which is 6.1 % high; the book's own total
    is 40,827, 3.9 % high. Both are inside TRANSCOST's stated +/- 20 % accuracy, and the gap between them is
    the three rows above that do not reconcile."""
    total = sum(C.element_effort_wyr(d["code"], d["mass_kg"], *factors(d))["wyr"]
                for d in C.ARIANE5_FACTORS.values())
    with_f0 = total * C.SYSTEM_ENGINEERING_F0
    assert with_f0 == pytest.approx(41_679, rel=0.01)
    assert abs(with_f0 / 39_300 - 1.0) == pytest.approx(0.061, abs=0.005)
    assert abs(with_f0 / 39_300 - 1.0) < C.TRANSCOST_ACCURACY, "inside TRANSCOST's own accuracy"
    assert abs(with_f0 / 40_827 - 1.0) < 0.03, "and close to the book's own total"


# ====================================================================== factors, work-years, inflation
def test_the_factors_are_applied_multiplicatively_and_a_missing_one_is_skipped():
    """Fig. 17.11. Table 17.4 leaves f2 blank on two rows, which must mean 'not applied', not 'zero'."""
    e = C.element_effort_wyr("EL", 1000.0, 1.1, None, 0.9, 0.86)
    assert e["wyr"] == pytest.approx(e["wyr_cer"] * 1.1 * 0.9 * 0.86, rel=1e-12)
    e2 = C.element_effort_wyr("EL", 1000.0, 1.1, 1.0, 0.9, 0.86)
    assert e2["wyr"] == pytest.approx(e["wyr"], rel=1e-12)


def test_work_year_values_are_table_17_3_and_inflation_is_equation_17_1():
    assert C.work_year_usd(2010)[0] == 296_000
    assert C.work_year_usd(1970)[0] == 38_000
    assert "Table 17.3" in C.work_year_usd(1990)[1]
    # Eq. 17.2's own example: $1.00 in 2010 is $1.36 in 2020
    assert C.inflate(1.0, 2010, 2020) == pytest.approx(1.36, abs=0.005)
    assert C.inflate(1.0, 2010, 2010) == 1.0
    off_table = C.work_year_usd(2020)
    assert off_table[0] == pytest.approx(296_000 * 1.031 ** 10, rel=1e-12)
    assert "Eq. 17.1" in off_table[1]


def test_inflation_is_reversible():
    assert C.inflate(C.inflate(100.0, 2000, 2020), 2020, 2000) == pytest.approx(100.0, rel=1e-12)


# ====================================================================== on the sized vehicle
def test_every_stage_contributes_an_engine_and_a_vehicle_element():
    r, e = estimate()
    assert len(e.elements) == 2 * len(r.stages)
    assert {x["code"] for x in e.elements} <= {"EL", "EP", "ES", "VS", "VR"}
    for x in e.elements:
        assert x["mass_kg"] > 0 and x["wyr"] > 0


def test_the_vehicle_element_excludes_the_engines_because_the_cer_does():
    """Fig. 17.16 is plotted against "vehicle dry mass (w/o engines)"."""
    r, e = estimate()
    for s in r.stages:
        eng = next(x for x in e.elements if x["element"] == f"Stage {s.index} engines")
        veh = next(x for x in e.elements if x["element"] == f"Stage {s.index} vehicle")
        assert eng["mass_kg"] + veh["mass_kg"] == pytest.approx(s.m_dry_kg, rel=1e-9)
        assert veh["basis"] == "vehicle dry mass without engines"


def test_development_cost_is_effort_times_the_work_year_value_with_f0():
    r, e = estimate()
    assert e.development_wyr == pytest.approx(e.f0 * sum(x["wyr"] for x in e.elements), rel=1e-12)
    assert e.development_usd == pytest.approx(e.development_wyr * e.work_year_usd, rel=1e-12)


def test_cost_per_flight_is_the_rule_of_thumb_not_a_cer():
    """Sec. 17.5.3 is the only per-flight source in this chapter; the production submodel is in reference [15].
    The reported range must be the full factor of 60 the book gives, not a tightened version of it."""
    r, e = estimate()
    lb = r.payload_mass_kg * C.LB_PER_KG
    assert e.per_flight_central_usd == pytest.approx(lb * C.RULE_OF_THUMB_USD_PER_LB, rel=1e-12)
    assert e.per_flight_usd == (pytest.approx(lb * 2_000), pytest.approx(lb * 120_000))
    assert e.per_flight_usd[1] / e.per_flight_usd[0] == pytest.approx(60.0, rel=1e-9)
    assert any("NOT from a cost-estimating relationship" in n for n in e.notes)


def test_the_comparables_are_real_prices_from_table_17_5():
    r, e = estimate()
    assert e.comparables
    for c in e.comparables:
        assert 0.5 * r.payload_mass_kg <= c["leo_kg"] <= 1.5 * r.payload_mass_kg
        assert c["cost_low_usd"] > 0 and c["usd_per_kg"] > 0
        assert c["name"] in {n for n, *_ in C.TABLE_17_5}


def test_the_estimate_lands_inside_the_real_price_band_for_this_payload_class():
    """Not a validation of the model - the rule of thumb is a rule of thumb - but if the central estimate fell
    outside every real price for a comparable payload, the rule would be worth not reporting."""
    r, e = estimate()
    lo = min(c["cost_low_usd"] for c in e.comparables)
    hi = max(c["cost_high_usd"] for c in e.comparables)
    assert lo <= e.per_flight_central_usd <= hi * 1.5


def test_specific_transportation_cost_is_work_years_per_tonne():
    """Sec. 17.6.4. Checked on the book's own Atlas V 401 row: 420-460 work-years for 9,600 kg."""
    assert C.specific_transportation_cost_wyr_per_Mg(440.0, 9_600.0) == pytest.approx(45.8, abs=0.2)
    assert math.isnan(C.specific_transportation_cost_wyr_per_Mg(440.0, 0.0))
    # bigger vehicles are more efficient, which is the section's whole claim
    big = C.specific_transportation_cost_wyr_per_Mg(1200.0, 23_000.0)
    small = C.specific_transportation_cost_wyr_per_Mg(90.0, 450.0)
    assert big < small


def test_a_pressure_fed_stage_uses_the_pressure_fed_cer():
    """Table 17.2 separates EP from EL, and the two CERs differ by a factor of several at engine scale."""
    class _S:
        is_solid = False
        class prop_system:
            cycle = "pressure_fed"
    assert C._engine_code(_S()) == "EP"

    class _T:
        is_solid = False
        class prop_system:
            cycle = "gas_generator"
    assert C._engine_code(_T()) == "EL"

    class _U:
        is_solid = True
    assert C._engine_code(_U()) == "ES"
