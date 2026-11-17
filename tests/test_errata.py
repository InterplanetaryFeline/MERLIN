"""Checks tied to the published errata for the 1st edition of Edberg & Costa (last revised 2023 Jan 12).

Each test pins a value that the errata corrects or adds, so that a future change cannot silently drift away
from the corrected form. Where the 2nd edition (the copy this tool is built from) already prints the corrected
value, the test records that agreement; where the errata supplies new guidance, the test pins the behaviour the
tool adopted. See docs/ERRATA_COMPLIANCE.md for the full item-by-item table.
"""
import math
import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import delta_v as dv, tank_sizing as ts, orbit as orb
from launch_vehicle.mass_budget import paf_mass
from launch_vehicle.units import EARTH_MODELS, G0


# --------------------------------------------------------------- Table 8.2 (errata p.427, added 2022FEB04)
def test_table_8_2_sqrt2_ellipsoidal_dome_coefficients():
    """Errata: a sqrt(2) EH dome has area 1.62323 pi R^2 and volume 1.48096 R^3 (no pi);
    a cylinder with two such domes has area 2 pi R h + 3.24645 pi R^2 and volume pi R^2 h + 2.96192 R^3."""
    R, AR, h = 2.5, math.sqrt(2.0), 4.0
    assert ts.dome_area(R, AR) == pytest.approx(1.62323 * math.pi * R ** 2, rel=1e-5)
    assert ts.dome_volume(R, AR) == pytest.approx(1.48096 * R ** 3, rel=1e-5)
    area_total = 2 * math.pi * R * h + 2 * ts.dome_area(R, AR)
    vol_total = math.pi * R ** 2 * h + 2 * ts.dome_volume(R, AR)
    assert area_total == pytest.approx(2 * math.pi * R * h + 3.24645 * math.pi * R ** 2, rel=1e-5)
    assert vol_total == pytest.approx(math.pi * R ** 2 * h + 2.96192 * R ** 3, rel=1e-5)


def test_hemispherical_dome_is_the_ar_1_limit():
    R = 1.7
    assert ts.dome_area(R, 1.0) == pytest.approx(2 * math.pi * R ** 2, rel=1e-12)
    assert ts.dome_volume(R, 1.0) == pytest.approx(2 * math.pi * R ** 3 / 3, rel=1e-12)


# --------------------------------------------------------------- Eq. 3:32 (errata p.159 removes spurious units)
def test_eq_3_32_simple_total_speed():
    """dv_total = sqrt(v_circ^2 + 2 g0 h (R/(R+h))^2) + 0.0015 Ta^2 + 0.0882 Ta + 1,036 m/s."""
    earth = EARTH_MODELS["book"]
    h, Ta = 400e3, 450.0
    v_circ = orb.circular_speed(earth.radius_m + h, earth.mu_m3s2)
    out = dv.simple_total_mps(v_circ, h, Ta, earth.radius_m)
    expect_energy = math.sqrt(v_circ ** 2 + 2 * G0 * h * (earth.radius_m / (earth.radius_m + h)) ** 2)
    assert out["energy_speed"] == pytest.approx(expect_energy, rel=1e-12)
    assert out["loss"] == pytest.approx(0.0015 * Ta ** 2 + 0.0882 * Ta + 1036.0, rel=1e-12)
    assert out["loss"] == pytest.approx(1379.4, abs=1.0)                 # hand value
    assert out["total"] == pytest.approx(expect_energy + out["loss"], rel=1e-12)
    # the climb term is what distinguishes it from the plain circular speed
    assert out["energy_speed"] > v_circ


# --------------------------------------------------------------- Eqs. 3:33-3:34
def test_eq_3_33_k1_k2_penalty():
    k = dv.k1k2_penalty_mps(185.0, 500.0)
    assert k["K1"] == pytest.approx(662.1 + 1.602 * 185 + 0.001224 * 185 ** 2, rel=1e-12)
    assert k["K2"] == pytest.approx(1.7871 - 0.0009687 * 185, rel=1e-12)
    assert k["penalty"] == pytest.approx(k["K1"] + k["K2"] * 500.0, rel=1e-12)


def test_the_three_book_loss_models_agree_within_the_regression_scatter():
    """Eqs. 3:32, 3:33-3:34 and 3:35-3:38 are three fits of the same data; on one mission they should agree
    to within the stated RMS error of the regression (about 260 m/s)."""
    totals = {}
    for model in ("book_simple", "book_k1k2", "book_penalty"):
        r = default_result({"mission.losses.model": model})
        totals[model] = r.dv_required_mps
    lo, hi = min(totals.values()), max(totals.values())
    assert hi - lo < 400.0, totals
    assert all(8800.0 < v < 9900.0 for v in totals.values()), totals


# --------------------------------------------------------------- Example 3.9 (errata p.163: sin, not cos)
def test_example_3_9_east_component_uses_sine_of_the_azimuth():
    """v_burnout,East = v_burnout cos(gamma) sin(beta). The 1st edition printed cos(beta)."""
    earth = EARTH_MODELS["book"]
    v, lat = 7787.0, 28.5
    v_site = orb.site_rotation_speed(earth, lat)
    # due East (beta = 90 deg): the whole site speed is subtracted
    need_e, _ = orb.needed_speed(earth, v, 90.0, lat, 0.0, True)
    assert need_e == pytest.approx(v - v_site, rel=1e-9)
    # due North (beta = 0): the site speed is perpendicular, so it adds in quadrature
    need_n, _ = orb.needed_speed(earth, v, 0.0, lat, 0.0, True)
    assert need_n == pytest.approx(math.sqrt(v ** 2 + v_site ** 2), rel=1e-9)
    # with cos(beta) in the East component these two would be swapped
    assert need_e < v < need_n


# --------------------------------------------------------------- Table 8.8 PAF (errata p.443)
def test_payload_adapter_small_payload_guidance():
    """Errata p.443: 'Use m_PAF = 0.15 m_PL for smaller payloads'."""
    for pl, mer_expect, frac_expect in ((150.0, 0.0755 * 150 + 50, 22.5), (10000.0, 805.0, 1500.0)):
        s_mer = default_spec({"vehicle.payload_adapter_method": "mer", "mission.payload_mass_kg": pl})
        s_fr = default_spec({"vehicle.payload_adapter_method": "fraction", "mission.payload_mass_kg": pl})
        assert paf_mass(s_mer) == pytest.approx(mer_expect, rel=1e-9)
        assert paf_mass(s_fr) == pytest.approx(frac_expect, rel=1e-9)
    # 'auto' switches at the small-launcher payload threshold
    s_small = default_spec({"vehicle.payload_adapter_method": "auto", "mission.payload_mass_kg": 300.0})
    s_big = default_spec({"vehicle.payload_adapter_method": "auto", "mission.payload_mass_kg": 10000.0})
    assert paf_mass(s_small) == pytest.approx(45.0, rel=1e-9)
    assert paf_mass(s_big) == pytest.approx(805.0, rel=1e-9)


def test_heavy_adapter_on_a_small_payload_is_flagged():
    """On the 150 kg solid small-launcher example the Table 8.8 MER gives a 61 kg adapter: 41 % of the payload."""
    import os
    from launch_vehicle.config_io import load_design
    from launch_vehicle.convergence import size_vehicle
    path = os.path.join(ROOT, "examples", "example_solid_smallsat.yaml")
    r = size_vehicle(load_design(path, ASSUMP, {"vehicle.payload_adapter_method": "mer"}))
    assert r.paf_mass_kg > 0.20 * r.payload_mass_kg
    assert any(i.code == "PAFSMALL" for i in r.issues)
    lean = size_vehicle(load_design(path, ASSUMP, {"vehicle.payload_adapter_method": "auto"}))
    assert lean.paf_mass_kg == pytest.approx(0.15 * lean.payload_mass_kg, rel=1e-9)
    assert not any(i.code == "PAFSMALL" for i in lean.issues)
    assert lean.glom_kg < r.glom_kg


# --------------------------------------------------------------- errata p.296 NOTE on payload ratios
def test_optimistic_payload_fraction_is_flagged():
    """The errata warns that payload ratios above about 4 % are rarely real for expendable launchers."""
    opt = {"mission.delta_v_override_mps": 8000.0,                 # losses understated
           "stages.0.structure_mode": "aggregate_s", "stages.1.structure_mode": "aggregate_s",
           "stages.0.structural_factor_s": 0.02, "stages.1.structural_factor_s": 0.02,   # unrealistically light
           "stages.0.residual_fraction": 0.0, "stages.1.residual_fraction": 0.0,
           "stages.0.loading_margin_fraction": 0.0, "stages.1.loading_margin_fraction": 0.0}
    r = default_result(opt)
    assert r.payload_mass_kg / r.glom_kg > 0.06
    assert any(i.code == "PAYFRAC" for i in r.issues)
    # with a realistic delta-v the same optimistic structure cannot reach 6 %: the errata's point that the
    # delta-v requirement, not the structure, sets the ceiling
    real = default_result({k: v for k, v in opt.items() if k != "mission.delta_v_override_mps"})
    assert real.payload_mass_kg / real.glom_kg < 0.045
    # the default (realistic) design must NOT trip it
    assert not any(i.code == "PAYFRAC" for i in default_result().issues)


# --------------------------------------------------------------- Example 1 (errata p.430) and Eq. 8.1
def test_example_1_stage_2_propellant_matches_the_corrected_value():
    """Errata p.430: m_p2 = m_PL (mu-1)(1-sigma)/(1-mu sigma) = 51.44 T for m_PL = 10 T, sigma = 0.1.

    The errata prints mu rounded to 4.27, which alone gives 51.36 T; the unrounded mass ratio from the
    example's own dv = 4,842 m/s and Isp = 340 s is 4.2725 and reproduces the printed 51.44 T."""
    from launch_vehicle.staging import propellant_aggregate, mass_ratio_from_dv
    mu = mass_ratio_from_dv(4842.0, 340.0)
    assert mu == pytest.approx(4.27, abs=0.005)
    assert propellant_aggregate(10000.0, 0.10, mu) == pytest.approx(51440.0, rel=1e-3)
    assert propellant_aggregate(10000.0, 0.10, 4.27) == pytest.approx(51361.0, rel=1e-3)


def test_eq_8_1_mass_flow_is_thrust_over_g0_isp():
    """Errata p.419: the second term of Eq. 8.1 should read mdot = T/(g0 Isp)."""
    from launch_vehicle.propulsion import mass_flow
    assert mass_flow(1.0e6, 300.0) == pytest.approx(1.0e6 / (G0 * 300.0), rel=1e-12)
