"""Solid-motor internal ballistics (book Secs. 4.4.2-4.4.3).

The book gives no worked internal-ballistics example, so there is no printed answer to reproduce. What there is:
three relations that must close into one another (Eqs. 4:32, 4:33 and Table 4.4), a stability statement about
the exponent, and two grain shapes described in enough detail to implement - the end burner and the hollow
cylinder - with a stated expectation for each one's thrust profile. All of that is testable.
"""
import math
import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import solid_motor as sm, engine_geometry as eg
from launch_vehicle.config_io import load_design
from launch_vehicle.convergence import size_vehicle

_C = {}
SOLID = "examples/example_solid_smallsat.yaml"


def solid_case():
    """The first solid stage of the example, with everything the ballistics needs."""
    if "c" not in _C:
        spec = load_design(SOLID, "config/engineering_assumptions.yaml")
        res = size_vehicle(spec)
        s = res.stages[0]
        st = spec.stages[0]
        case = [x for x in res.geometry.stage_segments(1) if x.kind == "tank"][0].tank
        ps = spec.solid_propellants[case.propellant]
        At = eg.throat_area(s.thrust_vac_N / st.motor.n_motors, ps.c_star_mps,
                            st.motor.chamber_pressure_Pa, st.motor.isp_vac_s)
        _C["c"] = dict(res=res, spec=spec, stage=s, motor=st.motor, case=case, prop=ps, A_t=At)
    return _C["c"]


def profile(grain="core"):
    key = f"p_{grain}"
    if key not in _C:
        d = solid_case()
        _C[key] = sm.burn_profile(d["case"], d["prop"].density_kg_m3, d["prop"].c_star_mps,
                                  d["prop"].burn_rate_exponent, d["A_t"],
                                  d["motor"].chamber_pressure_Pa, d["motor"].isp_vac_s, grain=grain)
    return _C[key]


# ====================================================================== the three relations must close
def test_the_equilibrium_pressure_satisfies_all_three_book_relations():
    """Pc = [rho a c* A_b/A_t]^(1/(1-n)) is only a shorthand; the test is that at that pressure the propellant
    produces exactly as much gas as the throat passes:  rho A_b (a Pc^n) == Pc A_t / c*."""
    rho, a, c_star, n = 1740.0, 2.0e-5, 1577.0, 0.35
    for A_b, A_t in ((50.0, 0.085), (12.0, 0.085), (3.0, 0.004)):
        pc = sm.chamber_pressure_Pa(rho, a, c_star, A_b, A_t, n)
        produced = rho * A_b * (a * pc ** n)                  # Eqs. 4:32 + 4:33
        passed = pc * A_t / c_star                            # Table 4.4
        assert produced == pytest.approx(passed, rel=1e-9)


def test_an_unstable_exponent_is_refused_rather_than_solved():
    """Book p.231: at n > 1 "a small decrease in chamber pressure could result in a catastrophic drop in burn
    rate". There is no equilibrium to report, and the exponent 1/(1-n) changes sign through it."""
    with pytest.raises(ValueError, match="unstable"):
        sm.chamber_pressure_Pa(1740.0, 2e-5, 1577.0, 50.0, 0.085, 1.2)
    with pytest.raises(ValueError):
        sm.chamber_pressure_Pa(1740.0, 2e-5, 1577.0, 50.0, 0.085, 1.0)
    assert profile()["stable"] is True
    assert profile()["n"] < 1.0


def test_pressure_rises_with_burning_area_and_falls_with_throat_area():
    """Both follow from Kn = A_b/A_t, which is the only way the geometry enters."""
    rho, a, c_star, n = 1740.0, 2.0e-5, 1577.0, 0.35
    p_small = sm.chamber_pressure_Pa(rho, a, c_star, 20.0, 0.085, n)
    p_big = sm.chamber_pressure_Pa(rho, a, c_star, 60.0, 0.085, n)
    p_wide = sm.chamber_pressure_Pa(rho, a, c_star, 20.0, 0.170, n)
    assert p_big > p_small > p_wide
    # and it depends on the ratio alone
    assert sm.chamber_pressure_Pa(rho, a, c_star, 40.0, 0.170, n) == pytest.approx(p_small, rel=1e-12)


def test_the_calibration_hits_the_design_pressure_exactly():
    """`a` is solved for, not assumed, so at the reference burning area the pressure must come out at the
    design value to machine precision."""
    rho, c_star, n, A_t, pc = 1740.0, 1577.0, 0.35, 0.085, 6.0e6
    for A_ref in (20.0, 45.0, 80.0):
        a = sm.calibrate_burning_rate_coefficient(rho, c_star, A_ref, A_t, n, pc)
        assert sm.chamber_pressure_Pa(rho, a, c_star, A_ref, A_t, n) == pytest.approx(pc, rel=1e-9)


# ====================================================================== burning area from the grain geometry
def test_core_burn_area_is_the_bore_surface_of_the_barrel():
    """For a bore through the barrel only, -dV/dw is its side, 2 pi (R_bore + w) h_cyl, plus its two flat ends
    burning into the domes, each the disc where the end face meets the dome at depth w."""
    d = solid_case()
    case = d["case"]
    assert not case.bore_full_length
    for w in (0.0, 0.05, 0.15):
        r = case.R_bore + w
        zb = case.h_dome * math.sqrt(max(1.0 - (r / case.R_int) ** 2, 0.0))
        rho_w = case.R_int * math.sqrt(max(1.0 - (w / case.h_dome) ** 2, 0.0))
        # the bore's side inside each dome, as deep as its end has burned (to where it meets the dome wall)
        want = (2 * math.pi * r * (case.h_cyl + 2 * min(w, zb)) + 2 * math.pi * min(r, rho_w) ** 2)
        assert sm.burn_area_m2(case, w) == pytest.approx(want, rel=0.02)


def test_a_cylindrical_bore_is_progressive_as_the_book_says():
    """p.233: "A grain with a cylindrical cutout will produce thrust levels that increase with time"."""
    p = profile()
    assert p["ok"] and p["progressive"]
    assert p["thrust_web_burnout_N"] > p["thrust_initial_N"]
    # it grows to its peak; near the end the bore's ends meet the curved dome wall and it eases, and once the
    # side reaches the case wall only the dome ends are left and it falls away
    main = [pt for pt in p["points"] if pt["t_s"] <= p["thrust_peak_t_s"]]
    areas = [pt["A_b_m2"] for pt in main]
    assert areas == sorted(areas), "the burning surface grows through the main burn"
    thrusts = [pt["thrust_N"] for pt in main]
    assert thrusts == sorted(thrusts)


def test_an_end_burner_is_neutral_as_the_book_says():
    """p.232: an end burner "will produce a nearly constant thrust level until all of the propellant is
    consumed", because its burning area is the casing cross-section and never changes."""
    p = profile("end")
    assert p["ok"]
    assert p["thrust_max_N"] / p["thrust_mean_N"] == pytest.approx(1.0, abs=1e-6)
    assert p["pc_max_Pa"] == pytest.approx(p["pc_min_Pa"], rel=1e-9)
    assert p["pc_max_Pa"] == pytest.approx(p["pc_design_Pa"], rel=1e-6), "neutral, so calibration lands on it"
    assert not p["progressive"]


def test_the_burning_area_vanishes_when_the_web_is_gone():
    d = solid_case()
    case = d["case"]
    assert sm.burn_area_m2(case, sm.burn_web_m(case) + 1e-6) == 0.0


def test_the_whole_grain_burns_including_the_domes():
    """Only the bore used to widen, so the dome propellant never burned: Scout's third stage consumed 597 kg of a
    985 kg grain. The bore's ends burn into the domes now, and the profile burns what was loaded."""
    d = solid_case()
    p = profile()
    loaded = d["prop"].density_kg_m3 * sm.grain_volume(d["case"].R_int, d["case"].h_dome, d["case"].h_cyl, d["case"].R_bore,
                                        d["case"].bore_full_length)
    assert p["mass_burned_kg"] == pytest.approx(loaded, rel=0.01)
    assert p["total_impulse_Ns"] == pytest.approx(loaded * 9.80665 * d["motor"].isp_vac_s, rel=0.01)
    assert sm.regressed_grain_volume(d["case"], 0.0) == pytest.approx(loaded / d["prop"].density_kg_m3, rel=1e-9)
    assert sm.regressed_grain_volume(d["case"], sm.burn_web_m(d["case"])) == pytest.approx(0.0, abs=1e-9)
    assert 0.0 <= p["tail_fraction"] < 0.5 and p["web_burnout_t_s"] <= p["burn_time_s"]


def test_burn_time_comes_from_integrating_dw_over_the_burn_rate():
    """t = integral dw / r(w), so a faster-burning grain must finish sooner."""
    p = profile()
    pts = p["points"]
    assert pts[0]["t_s"] == 0.0
    assert p["burn_time_s"] == pts[-1]["t_s"] > 0
    assert all(pts[i + 1]["t_s"] > pts[i]["t_s"] for i in range(len(pts) - 1))
    # the trapezoid of thrust over time is the reported impulse
    imp = sum(0.5 * (pts[i]["thrust_N"] + pts[i + 1]["thrust_N"]) * (pts[i + 1]["t_s"] - pts[i]["t_s"])
              for i in range(len(pts) - 1))
    assert p["total_impulse_Ns"] == pytest.approx(imp, rel=1e-12)
    assert p["thrust_mean_N"] == pytest.approx(imp / p["burn_time_s"], rel=1e-12)


# ====================================================================== what it says about the sizing
def test_the_simplest_grain_cannot_deliver_the_constant_thrust_the_sizing_assumed():
    """This is the point of running it. The stage was sized on one thrust for the whole burn; a plain
    cylindrical bore delivers a profile that rises by a factor of several and takes the chamber pressure well
    past its design value, which the casing was not sized for."""
    d, p = solid_case(), profile()
    assert p["thrust_web_burnout_N"] / p["thrust_initial_N"] > 3.0
    assert p["pc_max_Pa"] > 1.5 * p["pc_design_Pa"]
    assert p["Kn_max"] > 2 * p["Kn_min"]


def test_mass_flow_and_thrust_are_consistent_at_every_point():
    p = profile()
    d = solid_case()
    for pt in p["points"][::20]:
        assert pt["mdot_kgs"] == pytest.approx(
            d["prop"].density_kg_m3 * pt["A_b_m2"] * pt["r_mps"], rel=1e-12)       # Eq. 4:33
        assert pt["thrust_N"] == pytest.approx(pt["mdot_kgs"] * 9.80665 * d["motor"].isp_vac_s, rel=1e-12)
        assert pt["Kn"] == pytest.approx(pt["A_b_m2"] / p["A_t_m2"], rel=1e-12)


def test_a_propellant_without_ballistic_data_is_refused_not_guessed():
    """n and c* are measured properties the book gives for neither; without them there is nothing to solve."""
    d = solid_case()
    out = sm.burn_profile(d["case"], d["prop"].density_kg_m3, 0.0, 0.35, d["A_t"], 6e6, 282.0)
    assert not out["ok"] and "inventing" in out["reason"]
    out = sm.burn_profile(d["case"], d["prop"].density_kg_m3, 1577.0, 0.0, d["A_t"], 6e6, 282.0)
    assert not out["ok"]


def test_the_exponent_sits_in_the_books_stated_range_or_below_it():
    """p.231: "Typically, b will be between 0.4 and 0.7". The library's 0.35 is below that and is tagged as an
    assumption; what matters for the solution is only that it is under 1."""
    d = solid_case()
    n = d["prop"].burn_rate_exponent
    assert 0.0 < n < 1.0
    assert d["prop"].c_star_mps == pytest.approx(1577.0), "book Table 4.7"


def test_a_higher_exponent_makes_the_profile_more_extreme():
    """Pc ~ Kn^(1/(1-n)): the closer n gets to 1, the more violently pressure follows the burning area, which
    is the sensitivity behind the book's stability warning."""
    d = solid_case()
    args = (d["case"], d["prop"].density_kg_m3, d["prop"].c_star_mps)
    low = sm.burn_profile(*args, 0.2, d["A_t"], 6e6, 282.0)
    high = sm.burn_profile(*args, 0.6, d["A_t"], 6e6, 282.0)
    assert high["pc_max_Pa"] / high["pc_min_Pa"] > low["pc_max_Pa"] / low["pc_min_Pa"]


def test_every_shipped_solid_propellant_can_be_flown():
    """Scout's first two stages burn PBAN, whose c* sat only in a text note, so they vanished from the tab. Every
    propellant in the library carries the two numbers the burn needs: c* from the book, the exponent assumed."""
    import yaml
    with open("config/engineering_assumptions.yaml", encoding="utf-8") as fh:
        lib = yaml.safe_load(fh)["solid_propellants"]
    for name, p in lib.items():
        assert p["c_star_mps"]["v"] > 0 and p["c_star_mps"]["t"] == "reference", name
        assert 0 < p["burn_rate_exponent"]["v"] < 1 and p["burn_rate_exponent"]["t"] == "assumed", name


def test_scout_shows_all_four_stages():
    from launch_vehicle.main import _studies
    import os
    import tempfile
    spec = load_design("validation/scout_g1.yaml", "config/engineering_assumptions.yaml")
    res = size_vehicle(spec)
    with tempfile.TemporaryDirectory() as tmp:
        ex = _studies("validation/scout_g1.yaml", "config/engineering_assumptions.yaml", spec, res, tmp, {},
                      {"ballistics"}, 0, False)
    got = {p["stage"]: p for p in ex["ballistics"]}
    assert sorted(got) == [1, 2, 3, 4] and all(p["ok"] for p in got.values())
    # near the sized burn time: across six solid vehicles, sized from the file and optimised, it measured
    # 0.93-1.22 of it with the design pressure matched over the propellant
    for p in got.values():
        assert 0.85 < p["action_time_s"] / p["design_burn_time_s"] < 1.30, p["stage"]
