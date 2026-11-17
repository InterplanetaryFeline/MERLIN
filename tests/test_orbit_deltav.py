"""Orbit mechanics and delta-v budget. Expected values: hand calculations / book worked examples (cited per test)."""
import math
import pytest
from helpers import default_spec
from launch_vehicle import orbit as o, units as u, delta_v as dv
from launch_vehicle.delta_v import build_budget

E = u.EARTH_BOOK


def test_circular_speed_195km_hand_value():
    # Basis: v = sqrt(mu/r), mu = g0 R^2 = 3.98924e14, r = 6573 km -> 7790.5 m/s (book Example 3.9 quotes 7.787 km/s using rounded mu).
    assert o.circular_speed(E.radius_m + 195e3, E.mu_m3s2) == pytest.approx(7790.46, rel=1e-5)
    assert o.circular_speed(E.radius_m + 195e3, E.mu_m3s2) == pytest.approx(7787.0, rel=1e-3)


def test_vis_viva_molniya_book_example_3_2():
    # Basis: Book Example 3.2: rp = 6878 km, a = 26562 km -> 10.05 km/s
    assert o.vis_viva(6878e3, 26562e3, E.mu_m3s2) == pytest.approx(10050.0, rel=2e-3)


def test_period_energy_consistency():
    el = o.orbit_from_altitudes(E, 400e3)
    assert el.period_s == pytest.approx(2 * math.pi * math.sqrt(el.a_m ** 3 / E.mu_m3s2), rel=1e-12)
    assert el.specific_energy_J_kg == pytest.approx(-E.mu_m3s2 / (2 * el.a_m), rel=1e-12)
    assert el.e == pytest.approx(0.0, abs=1e-12)
    assert 5500 < el.period_s < 5600          # ~92.5 min for 400 km


def test_site_rotation_speed_book_example_3_9():
    # Basis: Book Example 3.9: 0.4087 km/s at 28.5 deg.
    assert o.site_rotation_speed(E, 28.5) == pytest.approx(408.7, rel=1e-3)


def test_launch_azimuth_due_east_when_inclination_equals_latitude():
    assert o.launch_azimuth_deg(28.5, 28.5) == pytest.approx(90.0, abs=1e-6)


def test_launch_azimuth_infeasible_inclination_raises():
    with pytest.raises(o.OrbitError, match="direct ascent"):
        o.launch_azimuth_deg(20.0, 28.5)


def test_sso_inclination_600km():
    # Basis: well-known value ~97.8 deg for a 600 km sun-synchronous orbit.
    el = o.orbit_from_altitudes(E, 600e3)
    assert o.sso_inclination_deg(E, el.a_m, el.e) == pytest.approx(97.8, abs=0.05)


def test_needed_speed_book_example_3_9():
    # Basis: Book Example 3.9: v_burnout 7.787 km/s due east, site speed 0.4087 -> needed 7.379 km/s
    vn, vs = o.needed_speed(E, 7787.0, 90.0, 28.5)
    assert vn == pytest.approx(7379.0, abs=1.5)


USER = dict(loss_model="user", gravity_loss_mps=1200.0, drag_loss_mps=100.0, steering_loss_mps=100.0, other_allowance_mps=0.0, design_margin_fraction=0.02)


def test_budget_sum_and_margin_applied_once():
    spec = default_spec()
    b = build_budget(u.EARTH_MODELS[spec.earth_model], dict(spec.mission, **USER))
    base = sum(l.value_mps for l in b.lines if l.category != "margin")
    marg = [l for l in b.lines if l.category == "margin"]
    assert len(marg) == 1
    assert marg[0].value_mps == pytest.approx(0.02 * base, rel=1e-12)
    assert b.total_mps == pytest.approx(base * 1.02, rel=1e-12)
    # explicit hand build: v_inj - rotation + losses
    el = o.orbit_from_altitudes(E, 400e3)
    expected = (el.v_perigee_ms - o.site_rotation_speed(E, 28.5) + 1200 + 100 + 100) * 1.02
    assert b.total_mps == pytest.approx(expected, rel=1e-9)


def test_geo_direct_circularisation_delta_v():
    # Basis: v_a (GTO apogee) ~1.60 km/s, v_GEO ~3.07 km/s -> ~1.47 km/s without plane change, ~1.8 km/s with 28.5 deg.
    spec = default_spec()
    m = dict(spec.mission, **USER, orbit_type="GEO_DIRECT", perigee_altitude_m=185e3, apogee_altitude_m=35786e3, inclination_deg=28.5)
    b = build_budget(E, m)
    line = [l for l in b.lines if l.category == "maneuver"][0]
    assert line.value_mps == pytest.approx(1830.0, rel=0.03)
    m0 = dict(m, inclination_deg=28.5)
    mid = dict(m, inclination_deg=28.5)
    # pure circularisation (i -> 0) hand value
    el = o.orbit_from_altitudes(E, 185e3, 35786e3)
    vc = o.circular_speed(el.r_a_m, E.mu_m3s2)
    assert vc - el.v_apogee_ms == pytest.approx(1470.0, rel=0.03)


def test_gto_does_not_include_spacecraft_apogee_maneuver_in_total():
    spec = default_spec()
    m = dict(spec.mission, **USER, orbit_type="GTO", perigee_altitude_m=185e3, apogee_altitude_m=35786e3, report_apogee_maneuver=True)
    b = build_budget(E, m)
    info = [l for l in b.lines if not l.in_total]
    assert len(info) == 1
    assert b.total_mps == pytest.approx(sum(l.value_mps for l in b.lines if l.in_total), rel=1e-12)


def test_unsupported_orbit_and_missing_apogee_raise():
    spec = default_spec()
    with pytest.raises(o.OrbitError):
        build_budget(E, dict(spec.mission, **USER, orbit_type="MOON"))
    with pytest.raises(o.OrbitError, match="apogee"):
        build_budget(E, dict(spec.mission, **USER, orbit_type="GTO", apogee_altitude_m=None, eccentricity=None))


def test_book_penalty_regression_hand_calculation():
    # Basis: Book Eq. 3:37-3:38 evaluated by hand for h_p = 400 km, T_a = 540 s, T_3s = 390 s:
    #   K3 = 429.9 + 1.602*400 + 0.001224*400^2 = 1266.5 ; K4 = 2.328 - 0.0009687*400 = 1.9405
    #   T_mix = 0.405*540 + 0.595*390 = 450.75 s ; penalty = 1266.5 + 1.9405*450.75 = 2141.2 m/s
    bp = dv.book_penalty_mps(400.0, 540.0, 390.0)
    assert bp["K3"] == pytest.approx(1266.54, abs=0.01)
    assert bp["K4"] == pytest.approx(1.94052, abs=1e-4)
    assert bp["penalty"] == pytest.approx(2141.2, abs=1.0)
    # sanity versus Book Table 3.4: total design speed for LEO vehicles 8.8-9.3 km/s at ~175 km (Saturn V: 9,267 m/s)
    bp185 = dv.book_penalty_mps(185.0, 520.0, 380.0)
    v_circ = o.circular_speed(E.radius_m + 185e3, E.mu_m3s2)
    assert 9000.0 < v_circ + bp185["penalty"] - 400.0 < 9500.0


def test_three_stage_equivalent_time_eq_3_36():
    # Basis: T3s = 3c/a0 (1 - exp(-dv/(3c))) with c = g0 Isp = 2942 m/s, a0 = 12.75 m/s^2, dv = 7263 m/s
    t3 = dv.equivalent_three_stage_time_s(7263.0, 300.0, 12.75)
    c = 9.80665 * 300
    assert t3 == pytest.approx(3 * c / 12.75 * (1 - math.exp(-7263.0 / (3 * c))), rel=1e-12)
    assert 380 < t3 < 400


def test_default_leo_total_delta_v_is_about_9_4_km_s_including_losses():
    from helpers import default_result
    r = default_result()
    assert 9300.0 < r.dv_required_mps < 9600.0
    assert r.budget.info["loss_model"]["penalty"] == pytest.approx(r.budget.subtotal("loss"), rel=1e-12)
    # ascent time used by the regression equals the sized burn times + start-up + staging delay (coupled iteration)
    lm = r.budget.info["loss_model"]
    t_expected = sum(s.burn_time_s for s in r.stages) + sum(st.startup_time_s for st in r.spec.stages) + 3.0
    assert lm["T_ascent_s"] == pytest.approx(t_expected, rel=1e-6)


def test_indicative_loss_split_is_not_added_to_total():
    from helpers import default_result
    r = default_result()
    info = [l for l in r.budget.lines if l.category == "info"]
    assert len(info) == 4 and not any(l.in_total for l in info)
    assert sum(l.value_mps for l in info) == pytest.approx(r.budget.info["loss_model"]["penalty"], rel=1e-9)
