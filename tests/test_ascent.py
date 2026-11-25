"""The ascent to orbit (ascent.py), the losses it gives the sizing (simulated_loss.py), and how both reach the user.

The strongest checks here need no published number. A coast has to keep its inertial energy and angular momentum, which
only a turning-frame integration with both rotation terms right does; the losses have to close on the ideal speed; a
vehicle sized with its own flown losses has to arrive with nothing left over. The published check is the last section:
real vehicles flown on their published masses (tools/validate_ascent.py).
"""
import copy
import math
import os
import sys

import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import ascent, simulated_loss, trajectory as tj, webgui
from launch_vehicle.atmosphere import P0_PA
from launch_vehicle.config_io import load_design
from launch_vehicle.convergence import SizingError, size_vehicle
from launch_vehicle.optimization import optimize_dv_split
from launch_vehicle.units import G0

_C = {}


def sized(name, **ov):
    key = (name, tuple(sorted(ov.items())))
    if key not in _C:
        path = {"default": "config/default_design.yaml"}.get(name, f"validation/{name}.yaml")
        if name.startswith("example"):
            path = f"examples/{name}.yaml"
        _C[key] = size_vehicle(load_design(os.path.join(ROOT, path), ASSUMP, dict(ov)), keep_history=False)
    return _C[key]


def flown(name):
    key = ("flown", name)
    if key not in _C:
        _C[key] = tj.fly_design(sized(name))
    return sized(name), _C[key]


def flight(name, **kw):
    res = sized(name)
    return ascent.flight_for(res, tj.ascent_vehicle_from_result(res), **kw)


# ------------------------------------------------------------------ the integration
def test_the_losses_and_the_speed_gained_reconstruct_the_ideal():
    for name in ("default", "pegasus_xl", "epsilon", "ariane62"):
        _, t = flown(name)
        assert t.converged, (name, t.status)
        assert abs(t.closure_residual_mps) < 1e-6, (name, t.closure_residual_mps)


def test_a_coast_keeps_its_inertial_energy_and_angular_momentum():
    """The frame turns with the Earth; only with the Coriolis and centrifugal terms both right does an unpowered arc
    come out as a Kepler orbit in inertial space."""
    f = flight("default")
    assert f.om > 0.0, "the default design launches east, so the frame turns"
    s = f.fresh()
    s.kicked, s.h, s.v, s.g, s.bi = True, 200e3, 7300.0, math.radians(5.0), f.last
    vh, vr = f.inertial(s)
    e0, l0 = f.energy(s), vh * (f.R + s.h)
    f.coast_for(s, 2000.0, 10.0)
    vh, vr = f.inertial(s)
    assert f.energy(s) == pytest.approx(e0, rel=1e-7)
    assert vh * (f.R + s.h) == pytest.approx(l0, rel=1e-7)


def test_the_time_to_the_top_of_a_coast_is_right():
    f = flight("default")
    s = f.fresh()
    s.kicked, s.h, s.v, s.g, s.bi = True, 200e3, 7000.0, math.radians(8.0), f.last
    f.coast_for(s, f.time_to_apex(s), 2.0)
    assert abs(math.degrees(s.g)) < 0.01


def test_an_eastward_launch_gains_about_the_speed_of_the_site():
    res = sized("default")
    veh = tj.ascent_vehicle_from_result(res)
    east = ascent.flight_for(res, veh).search()[0].margin
    still = copy.copy(res)
    still.spec = copy.copy(res.spec)
    still.spec.mission = dict(res.spec.mission, include_earth_rotation=False)
    none = ascent.flight_for(still, veh).search()[0].margin
    assert 300.0 < east - none < 480.0, (east, none)


def test_the_speed_across_the_orbit_plane_is_paid_for():
    """Ariane 64 flies to a sun-synchronous orbit: the site's eastward speed is nearly all across its plane."""
    f = flight("ariane62") if abs(flight("ariane62").w_out) > 100 else flight("vega")
    assert abs(f.w_out) > 100.0
    assert 0.0 < math.degrees(math.acos(f.cyaw)) < 10.0


# ------------------------------------------------------------------ steering and cutoff
def test_the_default_design_goes_low_first_and_raises_its_orbit():
    r, t = flown("default")
    assert t.converged and t.profile == "transfer", t.status
    assert t.burnout_h_m == pytest.approx(185e3, abs=500.0)
    assert abs(t.burnout_gamma_deg) < 0.05, "the first insertion is level"
    hohmann = flight("default").plan.later_dv_mps
    assert t.second_burn_dv_mps == pytest.approx(hohmann, rel=0.03)
    i = t.insertion
    assert i["verdict"] == "reached"
    assert i["perigee_alt_m"] == pytest.approx(400e3, abs=2e3) and i["apogee_alt_m"] == pytest.approx(400e3, abs=2e3)


def test_the_engine_stops_when_the_orbit_is_reached_and_the_rest_is_reported():
    r, t = flown("default")
    assert t.propellant_left_kg > 100.0 and t.margin_mps > 50.0
    names = [e["name"] for e in t.events]
    assert "stage 2 cutoff" in names and "stage 2 second burn start" in names and "stage 2 second cutoff" in names
    last = t.events[-1]
    assert last["name"] == "stage 2 jettison"
    assert last["mass_kg"] == pytest.approx(r.payload_mass_kg + r.paf_mass_kg, rel=1e-6), "only the payload is left"


def test_no_neighbouring_kick_leaves_more_speed():
    f = flight("default")
    best = f.search()[0]
    for q in (0.8, 0.95, 1.05, 1.25):
        other = f.try_kick(best.kick_deg * q)
        assert other.score <= best.score + 0.5, q


def test_linear_tangent_steering_is_eq_6_59():
    """Book Eq. 6:59, p.371: the tangent of the pitch angle is linear in time, and zero at the end when it ends level."""
    steer = ascent.Flight.linear_tangent(0.6, 0.0, 100.0, 400.0)
    for k in (0.0, 0.25, 0.5, 1.0):
        assert math.tan(steer(100.0 + 400.0 * k, 0.0)) == pytest.approx(0.6 * (1.0 - k), abs=1e-12)


def test_a_direct_ascent_to_a_high_orbit_costs_more_than_raising_it():
    r, t = flown("default")
    direct = tj.fly_design(r, profile="direct")
    assert direct.profile == "direct"
    assert direct.margin_mps < t.margin_mps - 50.0, "this is why the book flies high orbits in two burns (pp.372-373)"


def test_a_low_orbit_is_flown_straight_in():
    _, t = flown("falcon9")
    assert t.profile == "direct" and t.second_burn_dv_mps == 0.0
    assert t.insertion["verdict"] == "reached"


def test_a_transfer_orbit_to_geostationary_is_flown_through_a_parking_orbit():
    _, t = flown("h3_24l")
    assert t.attempted and t.converged and t.profile == "parking"
    assert t.insertion["apogee_alt_m"] == pytest.approx(35786e3, rel=0.02)


def test_a_solid_last_stage_coasts_to_the_top_and_fires_level():
    _, t = flown("epsilon")
    assert t.profile == "solid"
    assert any(e["name"] == "coast to the last stage start" for e in t.events)
    assert t.burnout_h_m == pytest.approx(250e3, abs=1e3) and abs(t.burnout_gamma_deg) < 0.1
    assert t.propellant_left_kg == 0.0


def test_an_upper_stage_too_weak_to_hold_itself_up_is_diagnosed():
    """Delta II as this tool sizes it: a 12 minute second stage at T/W 0.27. Flown on its published masses the real one
    makes it (docs/ASCENT_VALIDATION.md), so this is the sizing's fault and the message says what to change."""
    _, t = flown("delta2_7920")
    assert not t.converged
    assert any("thrust-to-weight" in n for n in t.notes), t.notes
    assert t.t_s, "a failed attempt still has a history to look at"


def test_a_heavier_vehicle_has_less_to_spare():
    res = sized("default")
    veh = tj.ascent_vehicle_from_result(res)
    veh2 = copy.copy(veh)
    veh2.m0_kg = veh.m0_kg + 1000.0
    a, b = (ascent.flight_for(res, v).search()[0].margin for v in (veh, veh2))
    assert 100.0 < a - b < 400.0


def test_a_finer_step_does_not_move_the_answer():
    r, _ = flown("default")
    a, b = tj.fly_design(r, dt=1.0, kick_deg=0.45), tj.fly_design(r, dt=0.25, kick_deg=0.45)
    assert a.margin_mps == pytest.approx(b.margin_mps, abs=2.0)
    assert a.gravity_loss_mps == pytest.approx(b.gravity_loss_mps, rel=2e-3)


# ------------------------------------------------------------------ limits
def test_the_engine_throttles_to_the_acceleration_limit():
    res = sized("default")
    veh = tj.ascent_vehicle_from_result(res)
    for b in veh.burns:
        b.throttle_min = 0.4
    f = ascent.flight_for(res, veh, accel_limit_g=4.0)
    out = ascent.fly(f, f.search()[0], "x")
    felt = [(T - D) / (m * G0) for T, D, m, t in zip(out.thrust_N, out.drag_N, out.m_kg, out.t_s) if t < out.burnout_t_s]
    assert out.converged and max(felt) < 4.05
    free = flown("default")[1]
    assert out.ideal_dv_mps == pytest.approx(free.ideal_dv_mps, rel=0.05), "it burns the same propellant, longer"


def test_the_air_load_limit_bounds_the_angle_of_attack():
    f = flight("default", handover_h_m=12e3, qalpha_limit=100e3)
    out = ascent.fly(f, f.search()[0], "x")
    qa = max(q * abs(a) for q, a in zip(out.q_Pa, out.alpha_deg))
    assert out.converged and qa < 100e3 * 1.01


def test_an_air_launch_starts_where_it_is_dropped():
    r, t = flown("pegasus_xl")
    al = r.spec.mission["air_launch"]
    assert t.h_m[0] == al["release_altitude_m"] and t.v_mps[0] == al["release_speed_mps"]
    assert t.start_v_mps == al["release_speed_mps"] and t.converged


# ------------------------------------------------------------------ the vehicle as flown
def test_strap_ons_fly_on_their_vacuum_thrust_with_every_nozzle_back_pressured():
    """The parallel-burn phases carry an average of the sea-level and vacuum Isp. Flying that AND taking the core's back
    pressure off it charged the back pressure twice."""
    r = sized("h2a_202")
    veh = tj.ascent_vehicle_from_result(r)
    b, core, bst = veh.burns[0], r.stages[0], r.boosters
    n = bst.n_ground_lit
    assert b.thrust_vac_N == pytest.approx(core.thrust_vac_N + n * bst.thrust_vac_each_N, rel=1e-9)
    sl = b.thrust_vac_N - b.exit_area_m2 * P0_PA
    assert sl == pytest.approx(core.thrust_sl_N + n * bst.thrust_sl_each_N, rel=1e-9)
    assert sl / (r.glom_kg * G0) == pytest.approx(r.liftoff_tw, rel=1e-6), "the flight lifts off at the T/W the sizing reports"


def test_a_first_stage_without_a_sea_level_isp_lifts_off_at_the_tw_it_reports():
    """It was sized on its vacuum thrust: the report said 1.35 and the flight had 0.92."""
    r = sized("example_htp_kerolox")
    veh = tj.ascent_vehicle_from_result(r)
    b = veh.burns[0]
    tw = (b.thrust_vac_N - b.exit_area_m2 * P0_PA) / (veh.m0_kg * G0)
    assert tw == pytest.approx(r.liftoff_tw, rel=1e-6)
    assert tw == pytest.approx(1.35, abs=0.01)


def test_every_ground_launched_design_lifts_off_at_the_tw_it_reports():
    """Electron gives one Isp for sea level and vacuum: the sizing said 1.49 and the flight, with a back pressure from the
    nozzle's size, had 1.15."""
    for name in ("default", "electron", "falcon9", "vega", "soyuz2_1b", "example_htp_kerolox"):
        r = sized(name)
        b = tj.ascent_vehicle_from_result(r).burns[0]
        assert (b.thrust_vac_N - b.exit_area_m2 * P0_PA) / (r.glom_kg * G0) == pytest.approx(r.liftoff_tw, rel=1e-6), name


def test_losses_that_do_not_settle_are_refused_and_not_sized():
    """SLS on fixed engines: the loop once ended on thousands of times its mass and returned it as an answer."""
    with pytest.raises(SizingError) as e:
        sized("sls_block1", **{"mission.losses.model": "simulated"})
    assert e.value.options


def test_only_a_liquid_stage_can_be_stopped():
    assert [b.stoppable for b in tj.ascent_vehicle_from_result(sized("epsilon")).burns if b.powered] == [False] * 3
    assert all(b.stoppable for b in tj.ascent_vehicle_from_result(sized("default")).burns if b.powered)


# ------------------------------------------------------------------ the losses fed back into the sizing
def test_simulated_losses_are_off_unless_chosen():
    for name in ("default", "falcon9", "pegasus_xl"):
        assert sized(name).spec.mission["loss_model"] != "simulated"


def test_a_vehicle_sized_with_its_own_losses_arrives_with_nothing_to_spare():
    r = sized("default", **{"mission.losses.model": "simulated"})
    info = r.budget.info["simulated_loss"]
    assert info["settled"] and info["flights"] <= 6
    t = tj.fly_design(r)
    assert abs(t.margin_mps - r.budget.subtotal("margin", "allowance")) < 5.0
    assert t.insertion["verdict"] == "reached"
    assert r.glom_kg < 0.95 * sized("default").glom_kg, "the regression overstates this vehicle's losses"


def test_an_air_launched_vehicle_may_use_simulated_losses():
    r = sized("pegasus_xl", **{"mission.losses.model": "simulated"})
    assert r.converged and r.budget.info["simulated_loss"]["settled"]


def test_a_vehicle_whose_ascent_does_not_close_is_refused_with_a_way_out():
    with pytest.raises(SizingError) as e:
        sized("delta2_7920", **{"mission.losses.model": "simulated"})
    assert e.value.field == "mission.losses.model"
    assert e.value.options and e.value.options[0]["value"] == "book_penalty"


def test_the_split_search_follows_the_losses():
    """With one loss for every split the search shrinks the first stage and grows the upper one, which no ascent can fly
    as well. With flown losses it does not."""
    ov = {"mission.losses.model": "simulated"}
    spec = load_design(os.path.join(ROOT, "config/default_design.yaml"), ASSUMP, ov)
    q = optimize_dv_split(spec)
    plain = optimize_dv_split(load_design(os.path.join(ROOT, "config/default_design.yaml"), ASSUMP))
    assert q["fractions"][0] > plain["fractions"][0] + 0.05
    spec.dv_mode, spec.dv_fractions, spec.dv_fixed = "fractions", q["fractions"], None
    assert size_vehicle(spec, keep_history=False).glom_kg == pytest.approx(q["glom_kg"], rel=0.005)


def test_the_loss_map_interpolates_and_remembers_what_did_not_fly():
    m = simulated_loss.LossMap()
    for a, y in ((0.3, 2000.0), (0.4, 1800.0), (0.5, 1750.0), (0.6, 1800.0)):
        m.add([a, 1 - a], y)
    assert m([0.4, 0.6]) == pytest.approx(1800.0, abs=1e-6)
    assert 1740.0 < m([0.47, 0.53]) < 1800.0
    m.add([0.2, 0.8], None)
    assert m([0.21, 0.79]) > 3000.0
    assert copy.deepcopy(m) is m


# ------------------------------------------------------------------ reaching it
def test_the_ascent_inputs_are_offered_for_every_design():
    for p in ("config/default_design.yaml", "validation/falcon9.yaml", "examples/example_boosters.yaml"):
        rows = {i["path"]: i for i in webgui.design_inputs(os.path.join(ROOT, p), ASSUMP, describe=True)["items"]}
        assert "mission.ascent_profile" in rows and "mission.parking_altitude_m" in rows, p
        assert rows["mission.ascent_profile"].get("choices"), "the way to orbit is picked from a list"
        assert rows["mission.ascent_profile"]["section"] == "Mission"
        assert [c[0] if isinstance(c, (list, tuple)) else c["value"] for c in rows["mission.losses.model"]["choices"]].count("simulated") == 1


def test_the_ascent_inputs_can_be_set_on_a_design_that_never_had_them():
    ov = {"mission.ascent_profile": "direct", "mission.parking_altitude_m": 200e3}
    spec = load_design(os.path.join(ROOT, "validation/falcon9.yaml"), ASSUMP, ov)
    o = tj.flight_options(spec)
    assert o["profile"] == "direct" and o["parking_altitude_m"] == 200e3


# ------------------------------------------------------------------ against real vehicles
def test_real_vehicles_on_their_published_masses_reach_their_published_orbits():
    """The whole chain against reality, with the sizing taken out. Not a tuned number: each has a published mass, thrust,
    payload and orbit, and nothing here was adjusted to make the margin small."""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import validate_ascent as V
    REF, CAP = V.reference_tables()
    for key, within in (("falcon9", 100.0), ("titan2", 100.0), ("ariane5_eca", 150.0), ("h2a_202", 150.0)):
        _, _, _, out = V.fly(key, REF[key], CAP)
        assert out.converged and abs(out.margin_mps) < within, (key, out.margin_mps, out.status)
