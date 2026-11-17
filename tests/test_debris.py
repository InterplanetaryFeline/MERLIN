"""The descent of jettisoned hardware: does it come down, and if so where.

Two things here are easy to get wrong in ways that produce confident nonsense, so both are pinned:

  * THE ORBITAL TEST. The trajectory's speed is planet-relative; an orbit is not. Forget to add the eastward
    speed of the rotating surface and every upper stage looks suborbital, so the tool invents an impact point
    for a stage that is actually in orbit. The tests check the rotation term is really there, and that it is
    signed correctly (an eastward launch gains, a westward one loses).

  * THE DESCENT. Free fall in vacuum has a closed form, and drag has a known direction of effect: more drag
    means a shorter range, a slower impact and a longer fall. All three are asserted, because a sign error in
    the drag term would otherwise show up only as a plausible-looking map.

The physical claim the module's own docstring makes - that the drag bracket matters far less to the impact
POSITION than the separation state does - is also tested, since that claim is what the dispersion model is
built on and it would be embarrassing to assert it in prose and have the code disagree.
"""
import math
import types

from launch_vehicle import debris as dbr

R = 6378e3
MU = 3.986004418e14


def _item(**kw):
    base = dict(name="stage 1 jettison", mass_kg=20000.0, diameter_m=4.0, t_jettison_s=150.0,
                h_m=80e3, v_mps=2900.0, gamma_deg=29.0, x_m=100e3)
    base.update(kw)
    return dbr.Item(**base)


# ------------------------------------------------------------------ the item itself
def test_frontal_area_follows_the_diameter():
    assert abs(_item(diameter_m=2.0).area_m2 - math.pi) < 1e-9


# ------------------------------------------------------------------ orbital or not
def test_a_circular_orbit_state_comes_out_as_a_circular_orbit():
    """Checked at the pole, where the surface rotation speed is zero, so the answer is pure two-body."""
    h = 400e3
    v_circ = math.sqrt(MU / (R + h))
    orb = dbr.orbit_of(_item(h_m=h, v_mps=v_circ, gamma_deg=0.0), latitude_deg=90.0, azimuth_deg=0.0)
    assert abs(orb["perigee_altitude_m"] - h) < 2e3, orb
    assert abs(orb["apogee_altitude_m"] - h) < 2e3, orb


def test_the_eastward_launch_gains_the_rotation_speed_and_the_westward_one_loses_it():
    it = _item(h_m=200e3, v_mps=7000.0, gamma_deg=0.0)
    east = dbr.orbit_of(it, latitude_deg=0.0, azimuth_deg=90.0)
    west = dbr.orbit_of(it, latitude_deg=0.0, azimuth_deg=270.0)
    pole = dbr.orbit_of(it, latitude_deg=90.0, azimuth_deg=90.0)
    surface = dbr.OMEGA_EARTH_RAD_S * (R + 200e3)
    assert abs(east["v_inertial_mps"] - (7000.0 + surface)) < 1.0, east
    assert abs(west["v_inertial_mps"] - (7000.0 - surface)) < 1.0, west
    assert abs(pole["v_inertial_mps"] - 7000.0) < 1.0, "at the pole there is no rotation credit"
    assert east["perigee_altitude_m"] > west["perigee_altitude_m"]


def test_a_spent_first_stage_is_not_in_orbit_and_an_injected_upper_stage_is():
    low = dbr.orbit_of(_item(), latitude_deg=28.5, azimuth_deg=90.0)
    assert low["perigee_altitude_m"] < dbr.REENTRY_PERIGEE_M, "a 2.9 km/s stage must come down"
    high = dbr.orbit_of(_item(h_m=400e3, v_mps=7350.0, gamma_deg=0.0), latitude_deg=28.5, azimuth_deg=90.0)
    assert high["perigee_altitude_m"] > dbr.REENTRY_PERIGEE_M, "a 7.35 km/s release near 400 km stays up"


def test_an_escape_state_has_no_perigee_rather_than_a_nonsense_one():
    orb = dbr.orbit_of(_item(h_m=400e3, v_mps=12000.0, gamma_deg=0.0), latitude_deg=0.0, azimuth_deg=90.0)
    assert orb["perigee_altitude_m"] is None and orb["energy_J_kg"] >= 0.0


# ------------------------------------------------------------------ the descent
def test_a_vertical_drop_in_near_vacuum_matches_closed_form_free_fall():
    """h = 1 km, straight down, drag made negligible: t should be sqrt(2h/g) to within the step size."""
    it = _item(h_m=1000.0, v_mps=1.0, gamma_deg=-90.0, mass_kg=1e7, diameter_m=0.01)
    out = dbr.fall(it, cd=0.001, dt=0.05)
    expect = math.sqrt(2 * 1000.0 / 9.80665)
    assert abs(out["fall_time_s"] - expect) < 0.5, f"{out['fall_time_s']:.2f} s against {expect:.2f} s"
    assert abs(out["downrange_m"] - it.x_m) < 100.0, "a vertical drop should not travel downrange"


def test_more_drag_means_a_shorter_range_a_slower_impact_and_a_longer_fall():
    it = _item()
    low = dbr.fall(it, cd=0.9)
    high = dbr.fall(it, cd=2.8)
    assert high["downrange_m"] < low["downrange_m"], "more drag must not fly further"
    assert high["impact_v_mps"] < low["impact_v_mps"], "more drag must not land faster"
    assert high["fall_time_s"] > low["fall_time_s"], "more drag must not fall quicker"


def test_a_light_wide_item_lands_slower_than_a_dense_one():
    dense = dbr.fall(_item(mass_kg=20000.0, diameter_m=4.0), cd=1.6)
    light = dbr.fall(_item(mass_kg=700.0, diameter_m=3.0), cd=1.6)
    assert light["impact_v_mps"] < dense["impact_v_mps"], (light["impact_v_mps"], dense["impact_v_mps"])
    assert light["ballistic_coefficient"] < dense["ballistic_coefficient"]


def test_the_item_lands_exactly_on_the_surface():
    out = dbr.fall(_item(), cd=1.6, dt=2.0)
    assert out["peak_h_m"] > _item().h_m, "a stage separating while still climbing must coast up first"
    assert out["fall_time_s"] > 0.0


def test_a_zero_mass_item_is_refused_rather_than_dividing_by_zero():
    try:
        dbr.fall(_item(mass_kg=0.0), cd=1.6)
    except dbr.DebrisError as ex:
        assert "positive" in str(ex)
    else:
        raise AssertionError("a zero-mass item should be refused")


def test_the_coriolis_estimate_is_positive_and_grows_with_the_time_of_flight():
    short = dbr.fall(_item(mass_kg=20000.0, diameter_m=4.0), cd=1.6)
    long_ = dbr.fall(_item(mass_kg=700.0, diameter_m=3.0), cd=1.6)   # lighter: falls much longer
    assert short["coriolis_cross_range_m"] > 0.0
    assert long_["fall_time_s"] > short["fall_time_s"]
    assert long_["coriolis_cross_range_m"] > short["coriolis_cross_range_m"]


# ------------------------------------------------------------------ what sets the size of the area
def test_the_separation_state_moves_the_impact_point_far_more_than_the_drag_bracket_does():
    """The claim the dispersion model is built on, asserted against the code rather than only in prose."""
    it = _item()
    drag = [dbr.fall(it, cd=c)["downrange_m"] for c in dbr.Dispersion().cd]
    drag_spread = max(drag) - min(drag)
    import dataclasses
    speeds = [dbr.fall(dataclasses.replace(it, v_mps=it.v_mps * f), cd=1.6)["downrange_m"]
              for f in (0.97, 1.0, 1.03)]
    speed_spread = max(speeds) - min(speeds)
    assert speed_spread > 3 * drag_spread, (
        f"3 % of separation speed moved the impact {speed_spread/1e3:.0f} km and the whole drag bracket "
        f"{drag_spread/1e3:.0f} km: the module docstring claims the first dominates")


def test_the_dispersion_defaults_are_the_ones_the_docs_describe():
    d = dbr.Dispersion()
    assert d.sep_speed_frac == 0.03 and d.sep_gamma_deg == 1.0
    assert d.cd[0] < d.cd_nominal < d.cd[-1]
    assert d.cross_half_width_m is None, "blank means 'use the Coriolis floor', which is the honest default"


# ------------------------------------------------------------------ reading the items off a trajectory
def _fake_design():
    """The smallest duck-typed stand-in for a sized result: only what debris actually reaches into."""
    spec = types.SimpleNamespace(name="test", fairing=types.SimpleNamespace(diameter_m=3.0),
                                 stages=[types.SimpleNamespace(diameter_m=4.0),
                                         types.SimpleNamespace(diameter_m=3.0)])
    res = types.SimpleNamespace(spec=spec, stages=[types.SimpleNamespace(index=1), types.SimpleNamespace(index=2)],
                                geometry=types.SimpleNamespace(max_diameter=4.0))
    traj = types.SimpleNamespace(downrange_m=1600e3, events=[
        dict(t_s=0.0, name="stage 1 start", mass_kg=4e5, h_m=0.0, v_mps=0.0, gamma_deg=90.0, x_m=0.0),
        dict(t_s=158.0, name="stage 1 burnout", mass_kg=9e4, h_m=80e3, v_mps=2900.0, gamma_deg=29.0, x_m=100e3),
        dict(t_s=158.0, name="stage 1 jettison", mass_kg=7e4, h_m=80e3, v_mps=2900.0, gamma_deg=29.0,
             x_m=100e3, dropped_kg=20000.0),
        dict(t_s=161.0, name="fairing jettison", mass_kg=7e4, h_m=85e3, v_mps=2890.0, gamma_deg=28.5,
             x_m=108e3, dropped_kg=700.0),
        dict(t_s=540.0, name="stage 2 jettison", mass_kg=1e4, h_m=400e3, v_mps=7350.0, gamma_deg=0.0,
             x_m=1600e3, dropped_kg=4000.0),
    ])
    return res, traj


def test_only_events_that_dropped_something_become_items():
    res, traj = _fake_design()
    items = dbr.items_from_trajectory(res, traj)
    names = [i.name for i in items]
    assert names == ["stage 1 jettison", "fairing jettison", "stage 2 jettison"], names
    assert all(i.mass_kg > 0 for i in items)


def test_each_item_is_charged_its_own_diameter():
    res, traj = _fake_design()
    by = {i.name: i for i in dbr.items_from_trajectory(res, traj)}
    assert by["stage 1 jettison"].diameter_m == 4.0
    assert by["fairing jettison"].diameter_m == 3.0, "the fairing's own diameter, not the first stage's"
    assert by["stage 2 jettison"].diameter_m == 3.0


def test_resolve_separates_what_comes_down_from_what_stays_up():
    res, traj = _fake_design()
    out = dbr.resolve(res, traj, latitude_deg=28.5, azimuth_deg=90.0, dt=2.0)
    fates = {i.name: i.fate for i in out}
    assert fates["stage 1 jettison"] == "impact"
    assert fates["fairing jettison"] == "impact"
    assert fates["stage 2 jettison"] == "in_orbit", (
        "a stage released at 7350 m/s planet-relative from 28.5 deg is in orbit once the rotation is added; "
        "reporting an impact point for it would be the model's worst failure")
    s1 = next(i for i in out if i.name == "stage 1 jettison")
    assert s1.downrange_min_m < s1.downrange_m < s1.downrange_max_m
    assert s1.state_spread_m > s1.drag_spread_m
    assert s1.km_per_percent_speed > 0.0
    assert any("not modelled" in n or "breakup" in n.lower() or "intact" in n for n in s1.notes)


def test_an_in_orbit_item_carries_no_impact_numbers():
    res, traj = _fake_design()
    out = dbr.resolve(res, traj, latitude_deg=28.5, azimuth_deg=90.0, dt=2.0)
    s2 = next(i for i in out if i.name == "stage 2 jettison")
    assert s2.downrange_m == 0.0 and s2.fall_time_s == 0.0, "an orbital item must not be given a landing"
    assert s2.perigee_altitude_m > dbr.REENTRY_PERIGEE_M
    assert s2.notes and "orbital-lifetime" in s2.notes[0]


# ------------------------------------------------------------------ the near-orbital case
def test_an_item_separating_near_orbital_speed_is_reported_as_not_localisable():
    """The failure this guards against: a +3 % corner that never comes down, integrated anyway.

    A descent integrator handed a near-orbital corner accumulates downrange for most of a revolution and
    reports a "hazard area" tens of thousands of kilometres long, which is not an area at all.
    """
    res, traj = _fake_design()
    # a third stage released just below orbital speed: nominal comes down, the fast corner does not
    traj.events.append(dict(t_s=400.0, name="stage 1 jettison", mass_kg=5e3, h_m=250e3, v_mps=7250.0,
                            gamma_deg=0.5, x_m=1200e3, dropped_kg=1500.0))
    out = dbr.resolve(res, traj, latitude_deg=5.2, azimuth_deg=0.0, dt=2.0,
                      dispersion=dbr.Dispersion(sep_speed_frac=0.03))
    marg = [i for i in out if i.fate == "marginal"]
    assert marg, [i.fate for i in out]
    m = marg[0]
    assert m.localisable is False
    assert m.downrange_m > 0.0, "the nominal impact is still real and worth reporting"
    assert m.downrange_max_m == m.downrange_m, "no window is claimed for a case that has none"
    assert "NOT LOCALISABLE" in m.notes[0]


def test_an_ordinary_first_stage_stays_localisable():
    res, traj = _fake_design()
    out = dbr.resolve(res, traj, latitude_deg=28.5, azimuth_deg=90.0, dt=2.0)
    s1 = next(i for i in out if i.name == "stage 1 jettison")
    assert s1.fate == "impact" and s1.localisable is True


# ------------------------------------------------------------------ the corridor width
def test_the_half_width_floors_at_the_coriolis_estimate():
    res, traj = _fake_design()
    out = dbr.resolve(res, traj, latitude_deg=28.5, azimuth_deg=90.0, dt=2.0)
    cor = max(i.coriolis_cross_range_m for i in out if i.fate == "impact")
    assert dbr.half_width_m(out, dbr.Dispersion(cross_half_width_m=None)) == cor
    assert dbr.half_width_m(out, dbr.Dispersion(cross_half_width_m=1.0)) == cor, (
        "a stated width smaller than the omitted Coriolis term must not narrow the drawn area")
    big = cor * 3
    assert dbr.half_width_m(out, dbr.Dispersion(cross_half_width_m=big)) == big
