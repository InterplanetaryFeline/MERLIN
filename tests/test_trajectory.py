"""The 3-DoF ascent trajectory, its atmosphere and its aerodynamics (book Chapter 6).

Three kinds of check here. First, the pieces against published numbers: US Standard Atmosphere 1976 to five
figures, and the book's own Titan II drag equations at their breakpoints. Second, the integration against
itself: the four losses plus the final speed must reconstruct the vacuum ideal delta-v exactly, which is the one
identity that catches almost any mistake in the loss accounting. Third, the whole thing against the book's own
expectations for a good trajectory (p.379): max-q between 50 and 90 s, a smooth 90 -> 0 deg flight path angle,
gravity loss near 1.5 km/s and drag loss of 100-200 m/s.
"""
import math
import os
import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import atmosphere as atm, aerodynamics as aero, trajectory as tj
from launch_vehicle.config_io import load_design
from launch_vehicle.convergence import size_vehicle

_C = {}


def flown():
    """The default design, flown once (every trajectory test but the failure cases reuses it)."""
    if "r" not in _C:
        _C["r"] = default_result()
        _C["t"] = tj.fly_design(_C["r"], dt=0.25)
    return _C["r"], _C["t"]


# ------------------------------------------------------------------ atmosphere
def test_us76_reproduces_the_published_layer_values():
    """The 1976 standard's own defining values at each layer base, entered as geopotential altitudes."""
    def geometric(hp):
        return atm.R_EARTH_US76 * hp / (atm.R_EARTH_US76 - hp)
    published = {0: (288.15, 101325.0), 11000: (216.65, 22632.1), 20000: (216.65, 5474.89),
                 32000: (228.65, 868.019), 47000: (270.65, 110.906), 71000: (214.65, 3.95642)}
    for hp, (T, p) in published.items():
        a = atm.us76(geometric(hp))
        assert a.temperature_K == pytest.approx(T, rel=1e-5), hp
        assert a.pressure_Pa == pytest.approx(p, rel=1e-4), hp


def test_us76_sea_level_density_and_sound_speed():
    a = atm.us76(0.0)
    assert a.density_kg_m3 == pytest.approx(1.225, rel=1e-4)
    assert a.sound_speed_mps == pytest.approx(340.29, rel=1e-3)


def test_book_exponential_is_the_book_formula():
    """Eqs. 6:50 and 6:53 with h0 = 7.64 km, and the pressure and density falling by the same factor."""
    for h in (0.0, 5000.0, 20000.0):
        a = atm.book_exponential(h)
        k = math.exp(-h / 7640.0)
        assert a.density_kg_m3 == pytest.approx(1.225 * k, rel=1e-12)
        assert a.pressure_Pa == pytest.approx(101325.0 * k, rel=1e-12)


def test_the_book_scale_height_is_within_a_quarter_of_the_standard_atmosphere():
    """A sanity bound on the approximation the book asks for: a single scale height cannot match a layered
    atmosphere everywhere, but it must not be wildly off where the drag is."""
    for h in (10000.0, 20000.0, 30000.0):
        eq = atm.scale_height_from_models(h)
        assert 0.75 < eq / atm.SCALE_HEIGHT_M < 1.30, (h, eq)


def test_gravity_falls_with_the_inverse_square():
    assert atm.gravity_mps2(0.0) == pytest.approx(9.80665, rel=1e-12)
    assert atm.gravity_mps2(400e3) == pytest.approx(9.80665 / (1 + 400e3 / 6378e3) ** 2, rel=1e-12)


def test_an_unknown_atmosphere_model_is_refused():
    with pytest.raises(ValueError):
        atm.air(0.0, "exponential-ish")


# ------------------------------------------------------------------ aerodynamics
def test_titan2_drag_matches_the_printed_equations_and_is_continuous():
    """Book Fig. 6.13: Cd = 0.29 to M 0.8, then M - 0.51, then 0.091 + 0.5/M above M 1.068."""
    assert aero.cd_titan2(0.0) == 0.29 and aero.cd_titan2(0.8) == pytest.approx(0.29)
    assert aero.cd_titan2(1.0) == pytest.approx(0.49, rel=1e-12)
    # the printed breakpoint 1.068 is the rounded root of the two branches (the exact crossing is 1.06882), so
    # the curve has a step of about 0.0012 there. That is the book's rounding, and it is reproduced rather than
    # smoothed away; the test pins its size so it cannot grow.
    lo, hi = aero.cd_titan2(1.068 - 1e-9), aero.cd_titan2(1.068 + 1e-9)
    assert abs(hi - lo) < 0.002, (lo, hi)
    assert aero.cd_titan2(aero.CD_TITAN2_EXACT_JOIN_MACH - 1e-9) == pytest.approx(
        aero.cd_titan2(aero.CD_TITAN2_EXACT_JOIN_MACH + 1e-9), rel=1e-5)
    assert aero.cd_titan2(1.068) == pytest.approx(0.558, abs=0.001)
    assert aero.cd_titan2(8.0) == pytest.approx(0.091 + 0.5 / 8.0, rel=1e-12)


def test_the_drag_curve_has_the_transonic_peak_every_book_figure_shows():
    samples = [(m / 20.0, aero.cd_titan2(m / 20.0)) for m in range(1, 161)]
    peak_m = max(samples, key=lambda s: s[1])[0]
    assert 0.9 < peak_m < 1.3, peak_m
    assert aero.cd_titan2(6.0) < aero.cd_titan2(peak_m) / 2


def test_constant_and_table_models():
    assert aero.constant_model(0.25).cd(3.0) == 0.25
    t = aero.table_model([0.0, 1.0, 5.0], [0.2, 0.6, 0.25])
    assert t.cd(0.5) == pytest.approx(0.4)
    assert t.cd(-1.0) == 0.2 and t.cd(99.0) == 0.25     # clamped, never extrapolated
    with pytest.raises(ValueError):
        aero.table_model([1.0], [0.3])


def test_a_drag_table_from_the_design_file_is_flown_and_a_ragged_one_is_refused():
    m = aero.model_from_config({"drag_model": "table", "mach_table": [0.0, 1.0, 5.0], "cd_table": [0.2, 0.6, 0.25]})
    assert m.kind == "table" and m.cd(0.5) == pytest.approx(0.4)
    with pytest.raises(ValueError):
        aero.model_from_config({"drag_model": "table"})
    with pytest.raises(ValueError):
        aero.model_from_config({"drag_model": "table", "mach_table": [0.0, 1.0, 5.0], "cd_table": [0.2, 0.6]})


def test_the_shipped_placeholder_table_is_the_books_titan2_curve():
    """The default design carries a table so that the GUI has something to edit. It is the book's curve sampled,
    and says so; it must not drift into numbers with no source."""
    from launch_vehicle.config_io import load_design
    a = load_design(os.path.join(ROOT, "config", "default_design.yaml"),
                    os.path.join(ROOT, "config", "engineering_assumptions.yaml")).mission["aerodynamics"]
    assert len(a["mach_table"]) == len(a["cd_table"]) >= 2
    for mach, cd in zip(a["mach_table"], a["cd_table"]):
        assert cd == pytest.approx(aero.cd_titan2(mach), abs=6e-4), mach


def test_the_removed_file_reader_says_what_to_use_instead():
    with pytest.raises(ValueError) as e:
        aero.model_from_config({"drag_model": "zoom_ld"})
    assert "table" in str(e.value)


# ------------------------------------------------------------------ the integration identity
def test_the_four_losses_and_the_final_speed_reconstruct_the_ideal_delta_v():
    """Book Eq. 6:58. This is the identity that makes the loss budget trustworthy: it is not four separate
    estimates, it is one integration decomposed, and it must close to integration accuracy."""
    _, t = flown()
    assert t.converged
    assert t.closure_residual_mps == pytest.approx(0.0, abs=1e-6)
    assert t.ideal_dv_mps == pytest.approx(t.burnout_v_mps + t.total_loss_mps, rel=1e-9)


def test_every_loss_is_non_negative_and_the_biggest_is_gravity():
    _, t = flown()
    for name in ("gravity_loss_mps", "drag_loss_mps", "propulsion_loss_mps", "steering_loss_mps"):
        assert getattr(t, name) >= 0.0, name
    assert t.gravity_loss_mps > t.drag_loss_mps
    assert t.gravity_loss_mps > t.propulsion_loss_mps


def test_the_trajectory_looks_like_the_book_says_a_good_one_should():
    """Book p.379: max-q between 50 and 90 s, flight path angle running 90 -> ~0, altitude climbing smoothly."""
    _, t = flown()
    assert 50.0 <= t.max_q_t_s <= 90.0, t.max_q_t_s
    assert t.gamma_deg[0] == pytest.approx(90.0, abs=1e-6)
    assert abs(t.burnout_gamma_deg) < 5.0
    assert t.max_q_Pa > 10e3
    assert 0.8 < t.max_q_mach < 3.0
    assert t.burnout_h_m > 100e3


def test_the_altitude_and_speed_histories_are_monotone_where_they_should_be():
    _, t = flown()
    up = [h for h, s in zip(t.h_m, t.t_s) if s <= 200.0]
    assert all(b >= a - 1.0 for a, b in zip(up, up[1:])), "the vehicle climbs through the first stage and beyond"
    assert min(h for h, s in zip(t.h_m, t.t_s) if s > 300.0) > 150e3, "lofted or not, it stays out of the air"
    assert t.v_mps[0] == 0.0 and t.burnout_v_mps > 5000.0


def test_a_finer_time_step_does_not_move_the_answer():
    """If the losses depended on the step the whole exercise would be worthless."""
    r, _ = flown()
    a = tj.fly_design(r, dt=0.5, kick_deg=0.2382)
    b = tj.fly_design(r, dt=0.1, kick_deg=0.2382)
    assert a.burnout_v_mps == pytest.approx(b.burnout_v_mps, rel=2e-3)
    assert a.gravity_loss_mps == pytest.approx(b.gravity_loss_mps, rel=3e-3)
    assert a.drag_loss_mps == pytest.approx(b.drag_loss_mps, rel=2e-2)


# ------------------------------------------------------------------ guidance and shooting
def test_a_pure_gravity_turn_has_no_steering_loss():
    """The point of a gravity turn: thrust along the velocity vector, so the Eq. 6:58 steering integrand is
    identically zero."""
    r, _ = flown()
    veh = tj.ascent_vehicle_from_result(r)
    out = tj.integrate(veh, tj.Guidance(kick_deg=0.2382, terminal_mode="none"), dt=0.3)
    assert out.steering_loss_mps == 0.0
    assert out.max_alpha_deg == 0.0


def test_terminal_guidance_buys_altitude_and_charges_a_steering_loss():
    r, _ = flown()
    veh = tj.ascent_vehicle_from_result(r)
    free = tj.integrate(veh, tj.Guidance(kick_deg=0.2382, terminal_mode="none"), dt=0.3)
    guided = tj.integrate(veh, tj.Guidance(kick_deg=0.2382), dt=0.3)
    assert guided.steering_loss_mps > 0.0
    assert guided.burnout_h_m > free.burnout_h_m
    assert guided.burnout_v_mps < free.burnout_v_mps      # the manoeuvre is not free


def test_a_bigger_kick_gives_a_lower_flatter_trajectory():
    """The monotone behaviour the book's shooting method relies on (Fig. 6.18)."""
    r, _ = flown()
    veh = tj.ascent_vehicle_from_result(r)
    hs = [tj.integrate(veh, tj.Guidance(kick_deg=k), dt=0.4).burnout_h_m for k in (0.15, 0.25, 0.35)]
    assert hs[0] > hs[1] > hs[2], hs


def test_shooting_hits_the_target_altitude():
    r, _ = flown()
    out = tj.shoot_for_altitude(tj.ascent_vehicle_from_result(r), 200e3, dt=0.5)
    assert out.converged, out.status
    assert abs(out.burnout_h_m - 200e3) < 1e4


def test_an_unreachable_altitude_is_reported_not_faked():
    r, _ = flown()
    veh = tj.ascent_vehicle_from_result(r)
    out = tj.shoot_for_altitude(veh, 20_000e3, dt=0.5)       # 20,000 km on a two-stage kerolox: no
    assert not out.converged
    assert "altitude" in out.status


# ------------------------------------------------------------------ against real vehicles
def test_titan_ii_losses_land_inside_the_books_own_ranges():
    """The strongest external check available: book Table 3.4 (p.180) gives gravity 1,150-1,534 m/s, drag
    40-156 m/s for real launches, and p.379 says max-q should fall between 50 and 90 s."""
    r = size_vehicle(load_design(os.path.join(ROOT, "validation", "titan2.yaml"), ASSUMP))
    t = tj.fly_design(r, dt=0.3)
    assert t.converged, t.status
    assert 1100.0 < t.gravity_loss_mps < 1600.0, t.gravity_loss_mps
    assert 30.0 < t.drag_loss_mps < 200.0, t.drag_loss_mps
    assert 50.0 <= t.max_q_t_s <= 90.0, t.max_q_t_s


def test_a_restarting_upper_stage_can_be_stopped_at_insertion():
    """`last_ascent_stage` ends the ascent with that stage, whatever the ones above it would have done."""
    r = size_vehicle(load_design(os.path.join(ROOT, "validation", "saturn5.yaml"), ASSUMP))
    veh = tj.ascent_vehicle_from_result(r, last_ascent_stage=2)
    assert all("stage 3" not in b.name for b in veh.burns)
    t = tj.fly_design(r, dt=0.4, last_ascent_stage=2)
    assert t.converged, t.status
    assert 1200.0 < t.gravity_loss_mps < 2400.0


def test_the_vehicle_built_from_a_result_conserves_its_mass_budget():
    r, _ = flown()
    veh = tj.ascent_vehicle_from_result(r)
    m = veh.m0_kg - veh.fairing_kg
    for b in veh.burns:
        m -= b.startup_kg + b.mdot_kgs * b.duration_s + b.jettison_kg
    expect = r.payload_mass_kg + r.paf_mass_kg
    assert m == pytest.approx(expect, rel=1e-6), (m, expect)


# ------------------------------------------------------------------ every mission class is flown
def test_a_leo_mission_is_flown():
    for name in ("falcon9", "electron"):
        res = size_vehicle(load_design(f"validation/{name}.yaml", ASSUMP))
        tr = tj.fly_design(res)
        assert tr.attempted is True and tr.converged is True, f"{name}: {tr.status}"
        assert tr.t_s, "a flown ascent has a history"


def test_a_gto_mission_is_attempted_like_any_other():
    """It was refused until the model could coast and restart. Ariane 5 ECA as this tool sizes it carries twice the real
    ESC-A propellant, and its ascent still does not close - but that is now a finding about the vehicle."""
    res = size_vehicle(load_design("validation/ariane5_eca.yaml", ASSUMP))
    assert res.spec.mission["orbit_type"] == "GTO"
    tr = tj.fly_design(res)
    assert tr.attempted is True and tr.converged is False and tr.profile == "parking"
    assert any("thrust-to-weight" in n for n in tr.notes), tr.notes


def test_the_vertical_rise_is_vertical_until_the_kick():
    """With no kick the vehicle must climb straight up for ever. It did not: Eq. 6:43's pitch rate is
    -(g/v) cos(gamma), cos(pi/2) is 6e-17 rather than zero in floating point, and g/v is enormous in the first
    second, so rounding error grew into a real tilt before the kick - 57 degrees of unintended turn by 83 s for
    a Saturn V at a lift-off thrust-to-weight of 1.18. Slow, heavy vehicles are exactly the ones whose kick is
    small, so the shooting was solving for a kick on top of noise."""
    slow = tj.AscentVehicle("slow", 100_000.0, [tj.Burn("b", 120.0, 1.3e6, 420.0, 1.0, 315.0)], 7.0,
                            aero.constant_model(0.3))
    r = tj.integrate(slow, tj.Guidance(vertical_rise_s=10.0, kick_deg=0.0, terminal_mode="none"), dt=0.25)
    assert r.outcome == "flown"
    assert all(g == 90.0 for g in r.gamma_deg), "it tilted with no kick"
    assert max(abs(x) for x in r.x_m) < 1e-6, "and went downrange"      # v cos(pi/2) is 1e-14 m/s, not zero
    kicked = tj.integrate(slow, tj.Guidance(vertical_rise_s=10.0, kick_deg=0.5, terminal_mode="none"), dt=0.25)
    before = [g for t, g in zip(kicked.t_s, kicked.gamma_deg) if t < 10.0]
    assert before and all(g == 90.0 for g in before), "nothing turns before the kick"
    assert kicked.gamma_deg[-1] < 89.0, "and the kick still starts the turn"


# ------------------------------------------------------------------ orbit reached, and the timeline (M105)
class _Target:
    def __init__(self, hp, ha):
        self.perigee_alt_m, self.apogee_alt_m = hp, ha


class _FakeBudget:
    def __init__(self, info):
        self.info = info


class _FakeDesign:
    """Only what insertion_orbit reads from a sized design: the budget's target orbit and site geometry."""
    def __init__(self, perigee_km, apogee_km, v_site=0.0, azimuth=90.0, v_needed=0.0):
        self.budget = _FakeBudget(dict(orbit=_Target(perigee_km * 1e3, apogee_km * 1e3), v_site_mps=v_site,
                                       azimuth_deg=azimuth, v_needed_mps=v_needed))


def _burnout(v, gamma_deg, h_m):
    t = tj.TrajectoryResult(vehicle_name="x", converged=True, status="flown")
    t.burnout_v_mps, t.burnout_gamma_deg, t.burnout_h_m = v, gamma_deg, h_m
    return t


RP = 6378e3
MU = 9.80665 * RP * RP


def test_level_burnout_at_circular_speed_is_a_circular_orbit_at_that_altitude():
    r = RP + 400e3
    o = tj.insertion_orbit(_FakeDesign(400, 400), _burnout(math.sqrt(MU / r), 0.0, 400e3))
    assert o["checked"] and o["verdict"] == "reached"
    assert o["perigee_alt_m"] == pytest.approx(400e3, abs=1.0)
    assert o["apogee_alt_m"] == pytest.approx(400e3, abs=1.0)
    assert o["eccentricity"] == pytest.approx(0.0, abs=1e-6)


def test_a_speed_surplus_raises_the_apogee_and_a_deficit_drops_the_perigee_as_vis_viva_says():
    r = RP + 400e3
    vc = math.sqrt(MU / r)
    fast = tj.insertion_orbit(_FakeDesign(400, 400), _burnout(vc + 100.0, 0.0, 400e3))
    assert fast["perigee_alt_m"] == pytest.approx(400e3, abs=1.0)            # burnout point is the perigee
    a = 0.5 * (2 * RP + fast["perigee_alt_m"] + fast["apogee_alt_m"])
    assert math.sqrt(MU * (2 / r - 1 / a)) == pytest.approx(vc + 100.0, rel=1e-9)
    assert fast["verdict"] == "reached" and fast["notes"], "a surplus is reached, and says the apogee is high"
    slow = tj.insertion_orbit(_FakeDesign(400, 400), _burnout(vc - 30.0, 0.0, 400e3))
    assert slow["apogee_alt_m"] == pytest.approx(400e3, abs=1.0)             # burnout point is the apogee
    assert slow["verdict"] == "short" and 100e3 < slow["perigee_alt_m"] < 390e3
    lost = tj.insertion_orbit(_FakeDesign(400, 400), _burnout(vc - 500.0, 0.0, 400e3))
    assert lost["verdict"] == "suborbital" and lost["perigee_alt_m"] < tj.ORBIT_FLOOR_ALTITUDE_M


def test_the_launch_site_speed_is_added_back_the_way_the_budget_took_it_out():
    """orbit.needed_speed subtracts the site's eastward speed from the inertial injection velocity. The check
    must invert that exactly, or a vehicle that flies precisely the speed the budget asked for would be
    reported short of its orbit."""
    from launch_vehicle import orbit as orb
    r = RP + 400e3
    vc = math.sqrt(MU / r)

    class E:                                  # the two things needed_speed reads from an earth model
        omega_rad_s, radius_m = 7.2921159e-5, RP
    for az in (90.0, 45.0, -10.0):
        need, vs = orb.needed_speed(E, vc, az, 28.5)
        o = tj.insertion_orbit(_FakeDesign(400, 400, v_site=vs, azimuth=az, v_needed=need),
                               _burnout(need, 0.0, 400e3))
        assert o["inertial_speed_mps"] == pytest.approx(vc, rel=1e-9), az
        assert o["verdict"] == "reached" and o["speed_margin_mps"] == pytest.approx(0.0, abs=1e-6)


def test_the_check_declines_when_there_is_no_injection_to_check():
    bad = tj.TrajectoryResult(vehicle_name="x", converged=False, status="fell back")
    assert tj.insertion_orbit(_FakeDesign(400, 400), bad)["verdict"] == "no_ascent"
    never = tj.TrajectoryResult(vehicle_name="x", converged=False, status="not flown", attempted=False)
    assert not tj.insertion_orbit(_FakeDesign(400, 400), never)["checked"]
    stopped = tj.insertion_orbit(_FakeDesign(400, 400), _burnout(7000.0, 0.0, 400e3), last_ascent_stage=2)
    assert not stopped["checked"] and "stage 2" in stopped["headline"]


def test_the_default_design_reaches_its_orbit_and_its_timeline_is_in_order():
    _, t = flown()
    assert t.insertion["checked"] and t.insertion["verdict"] == "reached"
    assert t.insertion["perigee_alt_m"] == pytest.approx(400e3, abs=10e3)
    tl = tj.timeline(t)
    times = [e["t_s"] for e in tl]
    assert times == sorted(times) and tl[0]["name"].startswith("Lift-off") and tl[0]["t_s"] == 0.0
    names = " | ".join(e["name"] for e in tl)
    for must in ("Mach 1", "Maximum dynamic pressure", "Peak axial acceleration", "burnout", "Fairing jettison"):
        assert must in names, must
    assert "Coast 1/2 ignition" not in names and "start" not in names, "a coast does not ignite"
    assert all(e["mach"] is None for e in tl if e["h_m"] > tj.TIMELINE_MACH_CEILING_M)
    peak = next(e for e in tl if e["name"].startswith("Peak axial acceleration"))
    g = float(peak["name"].split(",")[1].split()[0])
    assert g > t.max_accel_g, "sensed acceleration has no gravity taken out of it, so it exceeds dv/dt"
    res, _ = flown()
    sized = max(s.accel_max_g for s in res.stages)
    assert g == pytest.approx(sized, rel=0.03), "the flown peak must agree with the sizing loop's burnout T/W"
    q = next(e for e in tl if e["name"].startswith("Maximum dynamic pressure"))
    assert q["t_s"] == pytest.approx(t.max_q_t_s) and q["q_Pa"] == pytest.approx(t.max_q_Pa)
    m1 = next(e for e in tl if e["name"] == "Mach 1")
    k = next(i for i in range(1, len(t.mach)) if t.mach[i - 1] < 1.0 <= t.mach[i])
    assert t.t_s[k - 1] <= m1["t_s"] <= t.t_s[k]


def test_the_orbit_check_and_the_timeline_reach_the_gui_and_the_report():
    from launch_vehicle import webgui, report
    _, t = flown()
    s = webgui._study_summary({"trajectory": t})["trajectory"]
    assert s["orbit"]["verdict"] == "reached" and len(s["timeline"]) >= 6
    with open(os.path.join(os.path.dirname(webgui.__file__), "gui_static", "index.html"), encoding="utf-8") as fh:
        page = fh.read()
    for probe in ("function orbitCheck(", "function timelineTable(", "ss.orbit", "ss.timeline", '"Orbit reached"'):
        assert probe in page, probe
    rows = report._orbit_rows(t)
    assert rows[0][0] == "Orbit reached?" and "Yes" in rows[0][1]
