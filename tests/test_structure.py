"""Shell stress, buckling and required thickness (book Chapter 10).

Chapter 10 works five numbered examples with every input and output printed, so almost all of this file is the
book's own arithmetic re-run through the module: Example 1a (area, inertia, axial and bending stress, their
sum against two allowables), 1b (shear), 2 (unpressurised buckling for steel and aluminium), 3a and 3b (hoop
and axial pressure stress, and the buckling benefit pressure buys), and 5 (required thickness for strength).

After those come the properties that must hold for any vehicle: more pressure never demands a thicker wall for
axial strength, the buckling solver's root really is a root, minimum gauge floors every answer, and the ground
cases carry no tank pressure.
"""
import math
import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import structure as st, loads as L, trajectory as tj

_C = {}

# The book's example tank, used by Examples 1a through 5 (pp.630-653)
R_EX, L_EX, T_EX = 1.25, 8.0, 0.001
E_STEEL, E_AL = 207e9, 68.95e9
SIG_STEEL, SIG_AL = 1034e6, 448e6          # 150 ksi and 65 ksi, "typical when one includes the strength loss
P_EX, M_EX, V_EX = 1_225e3, 392e3, 98e3    # due to welds" (p.632)
FS_EX = 1.25


def analysed():
    if "a" not in _C:
        r = default_result()
        t = tj.fly_design(r, dt=0.4)
        _C["r"], _C["out"] = r, st.analyse(r, L.standard_cases(r, t))
    return _C["r"], _C["out"]


# ====================================================================== Example 1a, pp.630-632
def test_area_and_moment_of_inertia_of_a_thin_shell():
    """Eqs. 10.6 and 10.8, against the printed 0.007854 m2 and 0.006136 m4."""
    assert 2 * math.pi * R_EX * T_EX == pytest.approx(0.007854, rel=1e-4)
    assert math.pi * R_EX ** 3 * T_EX == pytest.approx(0.006136, rel=1e-4)


def test_example_1a_axial_and_bending_stress():
    """Eqs. 10.16-10.18: 195.1 MPa axial, 99.9 MPa bending, 295.0 MPa together, all with FS = 1.25 applied."""
    sa = st.axial_stress_Pa(P_EX, R_EX, T_EX) * FS_EX
    sb = st.bending_stress_Pa(M_EX, R_EX, T_EX) * FS_EX
    assert sa / 1e6 == pytest.approx(195.1, rel=0.002)
    assert sb / 1e6 == pytest.approx(99.9, rel=0.003)
    assert (sa + sb) / 1e6 == pytest.approx(295.0, rel=0.002)


def test_example_1a_stress_against_both_allowables():
    """Eqs. 10.19-10.20: 28.5 % of the steel allowable and 65.8 % of the aluminium one."""
    tot = (st.axial_stress_Pa(P_EX, R_EX, T_EX) + st.bending_stress_Pa(M_EX, R_EX, T_EX)) * FS_EX
    assert 100 * tot / SIG_STEEL == pytest.approx(28.5, abs=0.2)
    assert 100 * tot / SIG_AL == pytest.approx(65.8, abs=0.3)


def test_example_1b_shear_thickness_is_negligible():
    """p.633: 0.024 mm of steel and 0.056 mm of aluminium carry the shear, with the shear allowable at half
    the compressive one - which is why the book drops shear from everything that follows."""
    assert st.SHEAR_ALLOWABLE_FRACTION == 0.5
    t_steel = st.t_required_shear_m(V_EX, R_EX, SIG_STEEL, 1.0)
    t_al = st.t_required_shear_m(V_EX, R_EX, SIG_AL, 1.0)
    assert t_steel * 1e3 == pytest.approx(0.024, abs=0.002)
    assert t_al * 1e3 == pytest.approx(0.056, abs=0.003)
    assert max(t_steel, t_al) < st.MIN_GAUGE_SKIN_M, "both are under minimum gauge, as the book says"


# ====================================================================== Example 2, pp.636-637
def test_example_2_unpressurised_critical_stress():
    """Eqs. 10.26-10.29: sigma_c/E of 9.58e-6 for steel at 0.228 mm and 3.64e-5 for aluminium at 0.527 mm,
    giving 1.98 MPa and 2.51 MPa - "hardly anything"."""
    for t, E, ratio, sc in ((0.228e-3, E_STEEL, 9.58e-6, 1.98e6), (0.527e-3, E_AL, 3.64e-5, 2.51e6)):
        assert st.unpressurised_critical_stress_ratio(t, R_EX, L_EX) == pytest.approx(ratio, rel=0.01)
        assert st.critical_stress_Pa(t, R_EX, L_EX, E, 0.0) == pytest.approx(sc, rel=0.01)


def test_the_two_printed_forms_of_the_unpressurised_criterion_agree():
    """Eq. 10.25 is written as sigma_c/E = 9(t/R)^1.6 + 0.16(t/L)^1.3, and Eq. 10.32 as a coefficient
    K0 = 9(t/R)^0.6 + 0.16(R/L)^1.3 (t/R)^0.3 with sigma_c = K0 E t/R. They are the same expression; this
    asserts it over a range rather than trusting the algebra."""
    for t in (0.1e-3, 0.5e-3, 2e-3, 8e-3):
        for R, Lm in ((1.25, 8.0), (2.0, 17.8), (0.5, 1.0)):
            lhs = st.unpressurised_critical_stress_ratio(t, R, Lm)
            rhs = st.k0(t, R, Lm) * t / R
            assert lhs == pytest.approx(rhs, rel=1e-12), (t, R, Lm)


# ====================================================================== Examples 3a and 3b, pp.642-644
def test_example_3a_hoop_and_axial_pressure_stress():
    """p.642: at 344.7 kPa in the example tank, 215.5 MPa axial and 431 MPa hoop, hoop exactly twice axial."""
    p = 344.7e3
    assert st.pressure_axial_relief_Pa(p, R_EX, T_EX) / 1e6 == pytest.approx(215.5, rel=0.002)
    assert st.hoop_stress_Pa(p, R_EX, T_EX) / 1e6 == pytest.approx(431.0, rel=0.002)
    assert st.hoop_stress_Pa(p, R_EX, T_EX) == pytest.approx(2 * st.pressure_axial_relief_Pa(p, R_EX, T_EX))


def test_example_3b_pressure_coefficients_and_critical_stress():
    """Table 10.4: K0 = 0.05249 (steel) and 0.08630 (aluminium), Kp saturated at 0.229 for both, giving
    10.63 MPa and 9.158 MPa - 5.4x and 3.7x the unpressurised values."""
    p = 344.75e3
    for t, E, k0_want, sc_want, factor in ((0.228e-3, E_STEEL, 0.05249, 10.63e6, 5.4),
                                           (0.527e-3, E_AL, 0.08630, 9.158e6, 3.7)):
        assert st.k0(t, R_EX, L_EX) == pytest.approx(k0_want, rel=0.002)
        assert st.kp(p, E, R_EX, t) == pytest.approx(0.229, rel=1e-9), "saturated at its cap"
        sc = st.critical_stress_Pa(t, R_EX, L_EX, E, p)
        assert sc == pytest.approx(sc_want, rel=0.005)
        assert sc / st.critical_stress_Pa(t, R_EX, L_EX, E, 0.0) == pytest.approx(factor, abs=0.1)


def test_the_pressure_coefficient_is_capped():
    """p.643: Kp rises "up to a maximum value of 0.229, when it stays constant"."""
    assert st.kp(1e3, E_AL, 1.25, 0.01) < 0.229, "a small pressure is below the cap"
    assert st.kp(1e9, E_AL, 1.25, 0.001) == 0.229
    assert st.kp(0.0, E_AL, 1.25, 0.001) == 0.0


# ====================================================================== Example 5, pp.652-653
def test_example_5_required_hoop_thickness():
    """Eq. 10.44 with p = 345 kPa, n_x = 3, rho = 1,141 kg/m3, h = 8 m, sigma_allow = 448 MPa: 2.14 mm."""
    p_h = st.hydrostatic_pressure_Pa(1141.0, 3.0, 8.0)
    t = st.t_required_hoop_m(345e3 + p_h, R_EX, SIG_AL, FS_EX)
    assert t * 1e3 == pytest.approx(2.14, rel=0.01)


def test_example_5_axial_requirement_is_cancelled_by_the_pressure():
    """The same inputs give a NEGATIVE bracket in Eq. 10.43. The book reads that correctly - "the negative
    thickness result for t_req-axial indicates that the internal pressure alone is more than enough to sustain
    the applied load" (p.653) - while the number printed just above it, 0.41 mm, is that negative value's
    magnitude. The magnitude is the wrong thing to use, so the module floors the requirement at zero."""
    p_h = st.hydrostatic_pressure_Pa(1141.0, 3.0, 8.0)
    bracket = (abs(P_EX) / (2 * math.pi * R_EX) + abs(M_EX) / (math.pi * R_EX ** 2)
               - 0.5 * R_EX * (345e3 + p_h))
    assert bracket < 0, "the book's own example is pressure-dominated"
    assert abs(FS_EX * bracket / SIG_AL) * 1e3 == pytest.approx(0.41, abs=0.02), "which is the printed 0.41 mm"
    assert st.t_required_axial_m(P_EX, M_EX, 345e3 + p_h, R_EX, SIG_AL, FS_EX) == 0.0


def test_more_pressure_never_demands_a_thicker_wall_for_axial_strength():
    """The whole argument of Sec. 10.4 is that pressure helps. Taking the magnitude of Eq. 10.43's bracket
    would invert that for any pressure-dominated tank, so this pins the direction."""
    ts = [st.t_required_axial_m(P_EX, M_EX, p, R_EX, SIG_AL, FS_EX)
          for p in (0.0, 50e3, 100e3, 200e3, 400e3, 800e3)]
    assert ts == sorted(ts, reverse=True)
    assert ts[0] > 0 and ts[-1] == 0.0


def test_hydrostatic_head_grows_with_acceleration_and_depth_and_is_zero_for_solids():
    assert st.hydrostatic_pressure_Pa(1141.0, 3.0, 8.0) == pytest.approx(1141 * st.G0 * 3 * 8, rel=1e-12)
    assert st.hydrostatic_pressure_Pa(1141.0, 0.0, 8.0) == 0.0
    assert st.hydrostatic_pressure_Pa(0.0, 3.0, 8.0) == 0.0, "a solid grain carries no head (p.650 note)"


# ====================================================================== the buckling solver
def test_the_buckling_thickness_really_is_the_root():
    """At the thickness returned, the applied stress with its factor of safety equals the critical stress."""
    for P, M, R, Lm, p in ((3.9e6, 3.8e6, 2.0, 17.8, 0.0), (1.2e6, 0.4e6, 1.25, 8.0, 300e3),
                           (5e5, 0.0, 1.5, 4.0, 0.0)):
        t = st.t_required_buckling_m(P, M, R, Lm, E_AL, p, FS_EX)
        applied = FS_EX * (P / (2 * math.pi * R * t) + M / (math.pi * R * R * t))
        assert applied == pytest.approx(st.critical_stress_Pa(t, R, Lm, E_AL, p), rel=1e-5)


def test_pressure_reduces_the_buckling_thickness():
    """Sec. 10.4.1: pressurisation is the one way to improve stability without adding mass."""
    dry = st.t_required_buckling_m(3.9e6, 3.8e6, 2.0, 17.8, E_AL, 0.0, FS_EX)
    wet = st.t_required_buckling_m(3.9e6, 3.8e6, 2.0, 17.8, E_AL, 300e3, FS_EX)
    assert wet < dry


def test_no_axial_load_needs_no_buckling_thickness():
    assert st.t_required_buckling_m(0.0, 0.0, 2.0, 10.0, E_AL, 0.0, FS_EX) == 0.0


# ====================================================================== flared skirts, Sec. 10.3.1.1
def test_frustum_criterion_reduces_to_its_own_interaction_equation():
    """NASA SP-8019 via p.638: buckling is P/P_cr + M/M_cr = 1, with the small end's radius in M_cr."""
    f = st.frustum_buckling_margin(1e6, 5e5, 0.004, 1.5, 2.0, 1.87, E_AL, 0.31)
    assert f["alpha_deg"] == pytest.approx(math.degrees(math.atan2(0.5, 1.87)), rel=1e-9)
    assert f["interaction"] == pytest.approx(1e6 / f["P_cr_N"] + 5e5 / f["M_cr_Nm"], rel=1e-12)
    assert f["margin"] == pytest.approx(1.0 / f["interaction"] - 1.0, rel=1e-12)
    # a cylinder is the zero-angle limit, and must not blow up
    g = st.frustum_buckling_margin(1e6, 5e5, 0.004, 2.0, 2.0, 1.87, E_AL, 0.31)
    assert g["alpha_deg"] == pytest.approx(0.0, abs=1e-9)
    assert g["P_cr_N"] > f["P_cr_N"], "a straighter cone carries more"


# ====================================================================== on the sized vehicle
def test_every_shell_gets_every_load_case():
    r, out = analysed()
    assert out["shells"]
    for s in out["shells"]:
        assert len(s.cases) == len(out["cases"])


def test_the_fairing_is_not_run_through_an_aluminium_criterion():
    r, out = analysed()
    assert out["skipped"], "the fairing segments are skipped"
    assert all("Fairing" in n for n in out["skipped"])
    assert not any("Fairing" in s.name for s in out["shells"])
    assert any("composite sandwich" in n for n in out["notes"])


def test_ground_cases_carry_no_tank_pressure():
    """Book p.650, and it is the rule that makes the pad case size the tanks."""
    r, out = analysed()
    for s in out["shells"]:
        for c in s.cases:
            if "Ground" in c.case or "Lift-off" in c.case:
                assert c.p_Pa == 0.0, f"{s.name}/{c.case}"


def test_flight_cases_do_carry_tank_pressure_on_tanks():
    r, out = analysed()
    tanks = [s for s in out["shells"] if s.kind == "tank"]
    assert tanks
    for s in tanks:
        flight = [c for c in s.cases if c.case.startswith("Flight")]
        assert flight and all(c.p_Pa > 0 for c in flight)


def test_unpressurised_structures_never_get_pressure_in_any_case():
    r, out = analysed()
    for s in out["shells"]:
        if s.kind in ("aft_skirt", "fwd_skirt", "intertank", "interstage"):
            assert all(c.p_Pa == 0.0 and c.p_hydro_Pa == 0.0 for c in s.cases), s.name


def test_required_thickness_is_the_worst_case_floored_at_minimum_gauge():
    r, out = analysed()
    for s in out["shells"]:
        worst = max(c.t_required_m for c in s.cases)
        assert s.t_required_m == pytest.approx(max(worst, out["material"].t_min_m), rel=1e-12)
        assert s.min_gauge_applied == (worst < out["material"].t_min_m)


def test_the_governing_driver_is_the_requirement_that_won():
    r, out = analysed()
    for s in out["shells"]:
        if s.min_gauge_applied:
            assert s.governing_driver == "minimum gauge"
            continue
        c = max(s.cases, key=lambda c: c.t_required_m)
        assert s.governing_driver in ("axial", "hoop", "buckling")
        assert getattr(c, f"t_{s.governing_driver}_m") == pytest.approx(c.t_required_m, rel=1e-12)


def test_sized_mass_follows_from_thickness_area_and_density():
    r, out = analysed()
    rho = out["material"].rho_kg_m3
    for s in out["shells"]:
        assert s.mass_sized_kg == pytest.approx(rho * s.surface_area_m2 * s.t_required_m, rel=1e-12)


def test_monocoque_sizing_is_heavier_than_the_mass_relationships():
    """Not a defect in either: the MERs are fitted to real vehicles and real vehicles are stiffened. The point
    of reporting it is to show how much of the modelled structural mass is doing work that monocoque cannot."""
    r, out = analysed()
    assert out["mass_model_kg"] > 0
    assert out["mass_ratio"] > 1.0
    assert any("rings, stringers, waffle and isogrid" in n for n in out["notes"])


def test_buckling_sizes_most_of_a_monocoque_launch_vehicle():
    """The book's own example tanks buckle at 288-364 psi, orders of magnitude below their strength."""
    r, out = analysed()
    drivers = [s.governing_driver for s in out["shells"]]
    assert drivers.count("buckling") > len(drivers) / 2


def test_the_analysis_runs_with_the_ground_case_alone():
    """No trajectory, so no flight cases: the pad case must still size the vehicle."""
    r, _ = analysed()
    out = st.analyse(r, L.standard_cases(r, None))
    assert out["cases"] and all("Flight" not in c for c in out["cases"])
    assert all(s.t_required_m > 0 for s in out["shells"])


# ====================================================================== found in v1.3.1, fixed after it
def _structure_of(name):
    from launch_vehicle.config_io import load_design
    from launch_vehicle.convergence import size_vehicle
    r = size_vehicle(load_design(os.path.join(ROOT, "validation", f"{name}.yaml"), ASSUMP))
    t = tj.fly_design(r)
    return r, st.analyse(r, L.standard_cases(r, t))


def test_a_stage_already_dropped_is_not_loaded_by_a_later_flight_case():
    """Falcon 9's maximum-acceleration case is at stage-2 burnout. It used to load stage 1 too, with its tanks
    full, and sized the first-stage oxygen tank by a 1.2 MPa liquid head that never exists."""
    r, out = _structure_of("falcon9")
    late = [c for c in L.standard_cases(r, tj.fly_design(r)).values()
            if hasattr(c, "stations") and (c.state.get("stage_burning") or 1) > 1]
    for sh in out["shells"]:
        if sh.stage == 1:
            assert not {c.name for c in late} & {c.case for c in sh.cases}, sh.name


def test_a_solid_first_stage_does_not_stop_the_analysis():
    """Vega's first stage has no tanks, and reading its tank material raised: no Structure tab at all."""
    r, out = _structure_of("vega")
    assert out["shells"]
    names = [s.name for s in out["shells"]]
    assert not any("casing" in n.lower() for n in names), "a solid casing is not an aluminium monocoque shell"
    assert any("Solid-motor casings are not analysed" in n for n in out["notes"])


def test_a_tank_narrower_than_its_stage_carries_only_its_own_pressure():
    r, out = _structure_of("vega")
    inner = [s for s in out["shells"] if s.pressurised and s.R_m < 0.5 * r.spec.stages[s.stage - 1].diameter_m - 1e-3]
    assert inner
    for s in inner:
        assert all(c.P_N == 0.0 and c.M_Nm == 0.0 for c in s.cases)


def test_each_shell_is_checked_in_its_own_stage_material():
    r, out = analysed()
    for s in out["shells"]:
        assert s.material.name == r.spec.stages[s.stage - 1].tank.material.name


def test_at_the_required_buckling_thickness_the_buckling_margin_is_zero():
    """The margin and the required thickness now use the same applied stress."""
    sh = st.analyse_shell("x", "tank", 1, 2.0, 17.8, 2.0, 1.0, 0.005, st.Material("al", E_AL, 0.31, 2800.0, 448e6),
                          True, [dict(case="c", P_N=3.9e6, M_Nm=3.8e6, V_N=0.0, p_Pa=300e3, p_hydro_Pa=0.0, n_x=1.0)], FS_EX)
    t = sh.cases[0].t_buckling_m
    sh2 = st.analyse_shell("x", "tank", 1, 2.0, 17.8, 2.0, 1.0, t, st.Material("al", E_AL, 0.31, 2800.0, 448e6),
                           True, [dict(case="c", P_N=3.9e6, M_Nm=3.8e6, V_N=0.0, p_Pa=300e3, p_hydro_Pa=0.0, n_x=1.0)], FS_EX)
    assert sh2.cases[0].margin_buckling == pytest.approx(0.0, abs=1e-4)
