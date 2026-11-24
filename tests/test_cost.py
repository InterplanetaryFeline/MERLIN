"""Development, production and per-flight cost (book Chapter 17; Koelle, TRANSCOST 7.2).

Koelle's Table 2-V (p.104) is the original of the book's Table 17.4: a worked Ariane 5 verification with reference
masses, CER work-years, every factor and the result. All five rows and the total reproduce. His production examples
(S-II, pp.140; F-1, pp.140-141) do too. How MERLIN's own sized vehicles compare with real programmes is measured by
tools/validate_cost.py and written to docs/COST_VALIDATION.md.
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


# ====================================================================== Koelle's worked examples
def test_all_five_ariane_5_rows_reproduce_koelles_table():
    for name, d in C.ARIANE5_FACTORS.items():
        assert C.CERS[d["code"]].effort_wyr(d["mass_kg"]) == pytest.approx(d["wyr_cer"], rel=0.002), name
        got = C.element_effort_wyr(d["code"], d["mass_kg"], *factors(d))
        assert got["wyr"] == pytest.approx(d["wyr"], rel=0.002), name


def test_the_ariane_5_programme_is_the_sum_times_one_point_oh_four_cubed():
    """The book prints f0 = 1.04 with a superscript 3. Read as 1.043 the total came out 7 % low."""
    total = sum(C.element_effort_wyr(d["code"], d["mass_kg"], *factors(d))["wyr"] for d in C.ARIANE5_FACTORS.values())
    assert total == pytest.approx(36_292, rel=0.001)
    assert C.SYSTEM_ENGINEERING_F0 == 1.04
    assert total * C.SYSTEM_ENGINEERING_F0 ** 3 == pytest.approx(40_827, rel=0.001)
    assert total * 1.043 != pytest.approx(40_827, rel=0.05)


def test_koelles_engine_development_examples():
    assert C.element_effort_wyr("EL", 3180, 1.30, 1.22, 0.85)["wyr"] == pytest.approx(17_921, rel=0.001)   # p.103
    assert C.element_effort_wyr("EL", 3176, 1.0, 1.07, 0.8, 0.86)["wyr"] == pytest.approx(9_780, rel=0.001)  # p.113
    assert C.engine_quality_factor(500) == pytest.approx(1.0, abs=0.01)                                      # p.40
    assert C.engine_quality_factor(900) == pytest.approx(1.22, abs=0.02)


def test_koelles_production_examples():
    a, x, _ = C.PRODUCTION_CERS["vehicle_cryo"]
    assert 5 * a * 29_700 ** x * 0.86 == pytest.approx(4_515, rel=0.002)                    # five S-II, p.140
    a, x, _ = C.PRODUCTION_CERS["engine_storable"]
    assert a * 8_452 ** x * 0.58 == pytest.approx(139.1, rel=0.003)                         # one F-1, p.141
    assert C.learning_of_batch(0.96, 11, 15) == pytest.approx(0.86, abs=0.005)              # p.140
    assert C.stage_learning_factor(29_700, 2.5) == pytest.approx(0.96, abs=0.01)
    assert C.engine_learning_factor(8_452, 14) == pytest.approx(0.92, abs=0.015)            # p.141


def test_learning_means_each_doubling_costs_p_times_as_much():
    """Koelle p.118: at 0.80 the second unit costs 80 % of the first, so two average 90 %."""
    assert C.learning_average(0.80, 1) == 1.0
    assert C.learning_average(0.80, 2) == pytest.approx(0.90)
    assert C.learning_of_batch(0.80, 4, 4) == pytest.approx(0.64)
    assert C.learning_average(1.0, 500) == pytest.approx(1.0)
    exact = sum(k ** (math.log(0.9) / math.log(2)) for k in range(1, 8001)) / 8000
    assert C.learning_average(0.9, 8000) == pytest.approx(exact, rel=1e-6)


def test_the_quality_factor_of_the_ariane_5_core_comes_off_the_chart():
    """Koelle p.104 uses f2 = 1.16 for a 11,210 kg core with 155 t of hydrolox."""
    k_ref, inside = C.net_mass_fraction_reference(155_000, True)
    assert inside and k_ref / (11_210 / 155_000) == pytest.approx(1.16, abs=0.02)


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
    assert "Table 17.3" in C.work_year_usd(2010)[1] and "Table 1-II" in C.work_year_usd(1990)[1]
    # Eq. 17.2's own example: $1.00 in 2010 is $1.36 in 2020
    assert C.inflate(1.0, 2010, 2020) == pytest.approx(1.36, abs=0.005)
    assert C.inflate(1.0, 2010, 2010) == 1.0
    assert C.work_year_usd(1997)[0] == 191_600 and C.work_year_usd(2006)[0] == 246_000      # Koelle Table 1-II
    assert 252_000 < C.work_year_usd(2008)[0] < C.work_year_usd(2009)[0] < 296_000
    off_table = C.work_year_usd(2020)
    assert off_table[0] == pytest.approx(296_000 * 1.031 ** 10, rel=1e-12)
    assert "Eq. 17.1" in off_table[1]


def test_inflation_is_reversible():
    assert C.inflate(C.inflate(100.0, 2000, 2020), 2020, 2000) == pytest.approx(100.0, rel=1e-12)


# ====================================================================== on the sized vehicle
def test_every_liquid_stage_contributes_an_engine_and_a_vehicle_element():
    r, e = estimate()
    assert [x["key"] for x in e.elements] == ["stage1_engine", "stage1_vehicle", "stage2_engine", "stage2_vehicle"]
    for x in e.elements:
        assert x["mass_kg"] > 0 and x["wyr"] > 0


def test_an_engine_is_developed_once_however_many_the_stage_carries():
    """Fig. 17.13 plots one engine's mass. The cluster's total was used, which made six engines cost 2.4 times one."""
    r, e = estimate()
    n = r.stages[0].envelope.n
    assert n > 1
    eng = next(x for x in e.elements if x["key"] == "stage1_engine")
    assert eng["mass_kg"] * n == pytest.approx(C._engine_mass_kg(r, 1), rel=1e-9)
    assert next(p for p in e.production if p["element"] == "Stage 1 engine")["n"] == n, "but n of them are built"


def test_the_stage_element_excludes_the_engines_and_one_carries_the_fairing():
    r, e = estimate()
    extra = r.fairing_mass_kg + r.paf_mass_kg
    for s in r.stages:
        veh = next(x for x in e.elements if x["key"] == f"stage{s.index}_vehicle")
        want = s.m_dry_kg - C._engine_mass_kg(r, s.index) + (extra if s.index == 1 else 0.0)
        assert veh["mass_kg"] == pytest.approx(want, rel=1e-9)
        assert veh["basis"] == "vehicle dry mass without engines"


def test_development_cost_is_effort_times_the_work_year_value_with_f0_per_stage():
    r, e = estimate()
    assert e.f0 == pytest.approx(1.04 ** len(r.stages))
    assert e.development_wyr == pytest.approx(e.f0 * sum(x["wyr"] for x in e.elements), rel=1e-12)
    assert e.development_usd == pytest.approx(e.development_wyr * e.work_year_usd, rel=1e-12)
    assert e.average_team * e.development_years == pytest.approx(e.development_wyr)


def test_the_cost_per_flight_is_the_sum_of_its_parts():
    r, e = estimate()
    parts = e.production_wyr + e.ground_wyr + e.mission_wyr + e.indirect_wyr
    assert e.flight_wyr == pytest.approx(parts)
    assert e.indirect_wyr / e.flight_wyr == pytest.approx(C.INDIRECT_SHARE)
    assert e.production_wyr < e.first_vehicle_wyr
    assert e.flight_wyr_with_development == pytest.approx(e.flight_wyr + e.development_wyr / 60)
    rate, n = 6.0, 2
    f4 = C.learning_average(0.9, 60)
    assert e.ground_wyr == pytest.approx(8 * (r.glom_kg / 1e3) ** .67 * rate ** -.9 * n ** .7 * 0.8 * 0.7 * f4)
    assert e.mission_wyr == pytest.approx(20 * 0.8 * rate ** -.65 * f4)


def test_settings_change_the_estimate_the_way_they_should():
    r, e = estimate()

    def est(**k):
        return C.estimate(r, 2010, k)
    assert est(stage1_engine_existing=True).development_wyr < e.development_wyr
    assert est(stage1_vehicle_f1=1.2).development_wyr > e.development_wyr
    assert est(region="Europe").development_wyr == pytest.approx(0.86 * e.development_wyr)
    assert est(launch_rate=12).flight_wyr < e.flight_wyr < est(launch_rate=2).flight_wyr
    assert est(total_flights=200).production_wyr < e.production_wyr
    assert est(development_years=10).average_team == pytest.approx(e.development_wyr / 10)
    assert est(stage1_vehicle_f2=1.0).elements[1]["f2"] == 1.0 and not est(stage1_vehicle_f2=1.0).elements[1]["f2_computed"]
    assert est(assembly="horizontal").ground_wyr == pytest.approx(e.ground_wyr * 0.5 / 0.7)


def test_impossible_settings_are_refused_by_name():
    r, _ = estimate()
    for bad, name in ((dict(launch_rate=0), "launch_rate"), (dict(region="Mars"), "region"),
                      (dict(total_flights="many"), "total_flights"), (dict(nonsense=1), "nonsense"),
                      (dict(stage1_vehicle_f1=9), "stage1_vehicle_f1"), (dict(payload_utilisation=1.5), "payload_utilisation"),
                      (dict(launch_rate=float("nan")), "launch_rate")):
        with pytest.raises(C.CostInputError) as ex:
            C.estimate(r, 2010, bad)
        assert ex.value.field == name


def test_settings_live_in_the_design_under_mission_cost():
    r = default_spec({"mission.cost.launch_rate": 9, "mission.cost.stage1_engine_existing": True})
    assert r.mission["cost"] == {"launch_rate": 9, "stage1_engine_existing": True}
    from launch_vehicle.config_io import ConfigError
    with pytest.raises(ConfigError, match="mission.cost.lunch_rate"):
        default_spec({"mission.cost.lunch_rate": 9})


def test_a_solid_vehicle_and_strap_ons_are_costed():
    def sized(name):
        return size_vehicle(load_design(os.path.join(ROOT, "validation", name + ".yaml"), ASSUMP), keep_history=False)
    sc = C.estimate(sized("scout_g1"))
    assert {x["code"] for x in sc.elements} == {"ES"} and sc.n_stages == 4
    assert {p["kind"] for p in sc.production} == {"solid"}
    a5 = C.estimate(sized("ariane5_eca"))
    assert a5.n_stages == 3, "a pair of boosters counts as one stage, as in Koelle's 1.04 cubed"
    assert next(x for x in a5.elements if x["key"] == "boosters")["code"] == "VR"
    assert next(p for p in a5.production if p["element"] == "Strap-on booster")["n"] == 2
    assert a5.trend_wyr is None and not a5.comparables, "the LEO trend says nothing about a GTO payload"
    vega = C.estimate(sized("vega"))
    top = next(x for x in vega.elements if x["key"] == "stage4_vehicle")
    assert top["f2"] is None and "too small" in top["note"]


def test_the_comparables_are_from_table_17_5_in_their_own_currency():
    r, e = estimate()
    assert e.comparables
    rows = {t[0]: t for t in C.TABLE_17_5}
    for c in e.comparables:
        assert 0.5 * r.payload_mass_kg <= c["leo_kg"] <= 1.5 * r.payload_mass_kg
        assert c["currency"] == rows[c["name"]][4]
    assert rows["Ariane 5 ECA"][4] == "EUR" and rows["Vega"][4] == "EUR"
    assert "Zenit 3SL" not in rows, "the book states only its GTO payload"


def test_the_trend_is_the_fit_it_says_it_is():
    """WYr per Mg against LEO payload over Table 17.5, without Saturn and Shuttle."""
    pts = [(t[1] / 1e3, sum(t[3]) / 2 / (t[1] / 1e3)) for t in C.TABLE_17_5
           if t[3] and not t[0].startswith(("Saturn", "Space"))]
    n = len(pts)
    xs, ys = [math.log(a) for a, _ in pts], [math.log(b) for _, b in pts]
    mx, my = sum(xs) / n, sum(ys) / n
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    assert n == 19
    assert slope == pytest.approx(C.TREND_X, abs=0.002)
    assert math.exp(my - slope * mx) == pytest.approx(C.TREND_A, rel=0.01)


def test_the_measurements_in_the_validation_document_are_current():
    """Part A only: parts B and C size a dozen vehicles. Regenerate with tools/validate_cost.py."""
    import importlib.util
    sp = importlib.util.spec_from_file_location("validate_cost", os.path.join(ROOT, "tools", "validate_cost.py"))
    vc = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(vc)
    with open(os.path.join(ROOT, "docs", "COST_VALIDATION.md"), encoding="utf-8") as fh:
        text = fh.read()
    for what, stated, ours, _where in vc.worked_examples():
        assert f"| {what} | {vc._n(stated)} | {vc._n(ours)} |" in text, what
        assert ours == pytest.approx(stated, rel=0.07), what


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
        class engine:
            cycle = "pressure_fed"
    assert C._engine_code(_S()) == "EP"

    class _T:
        is_solid = False
        class engine:
            cycle = "gas_generator"
    assert C._engine_code(_T()) == "EL"

    class _U:
        is_solid = True
    assert C._engine_code(_U()) == "ES"
