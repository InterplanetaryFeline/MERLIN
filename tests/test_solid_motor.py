"""Solid rocket motor sizing: book Eqs. 8:17-8:24 (Sec. 8.5, printed pp. 486-490)."""
import math
import numpy as np
import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import solid_motor as sm
from launch_vehicle.tank_sizing import InfeasibleGeometry
from launch_vehicle.units import G0
from launch_vehicle.config_io import load_design
from launch_vehicle.convergence import size_vehicle
import os

SOLID = os.path.join(ROOT, "examples", "example_solid_smallsat.yaml")


def solid_result():
    """The solid example as it SHIPS, which since v0.26 means a stage-level relation (kibbey_medium)."""
    return size_vehicle(load_design(SOLID, ASSUMP))


def book_solid_result():
    """The same example forced onto the book's motor-level casing MER (Eq. 8:18).

    Several tests below are specifically ABOUT that motor-level path: the K_SRM coefficient, the component
    build-up, the skirts of book p.490, and the structural factor that follows from them. The example now
    ships with kibbey_medium, which predicts a whole STAGE and therefore suppresses that build-up on
    purpose - so relying on the file's own method would have those tests asserting about a path the design
    no longer takes, and they failed with "Motor casing" simply absent. Forcing the method keeps each test
    pointed at the thing it is named after.
    """
    spec0 = load_design(SOLID, ASSUMP)
    ov = {f"stages.{i}.motor.casing_mass_method": "book_composite"
          for i, st in enumerate(spec0.stages) if st.is_solid}
    return size_vehicle(load_design(SOLID, ASSUMP, ov))


# ---------------------------------------------------------------- mass relations
def test_casing_mer_coefficients_and_structural_factors_match_the_book():
    """Eq. 8:18 k = 0.135 (steel) / 0.1154 (Gr-E) and Eq. 8:19 s = k/(1+k) = 0.1189 / 0.1035 (p.490)."""
    assert sm.K_SRM["steel"] == 0.135
    assert sm.K_SRM["composite"] == pytest.approx(0.855 * 0.135, abs=1e-4)   # 8.7.3.1: Gr/E = 0.855 x steel (book prints 0.1154)
    assert sm.S_SRM["steel"] == pytest.approx(0.1189, abs=0.0001)
    assert sm.S_SRM["composite"] == pytest.approx(0.1035, abs=0.0001)


def test_casing_mass_methods():
    m, k, src = sm.casing_mass(10000.0, "book_steel")
    assert m == pytest.approx(1350.0) and k == 0.135 and "8:18" in src
    m, k, _ = sm.casing_mass(10000.0, "book_composite")
    assert m == pytest.approx(1154.0)
    m, k, _ = sm.casing_mass(10000.0, "mass_fraction", k_user=0.09)
    assert m == pytest.approx(900.0)
    m, k, _ = sm.casing_mass(10000.0, "user_mass", user_mass_kg=777.0)
    assert m == 777.0 and k == pytest.approx(0.0777)
    with pytest.raises(ValueError):
        sm.casing_mass(1000.0, "nonsense")
    with pytest.raises(ValueError):
        sm.casing_mass(1000.0, "mass_fraction")


def test_total_impulse_specification_eq_8_22():
    """Eq. 8:22: m_p = I_tot/(g0 Isp). A 1e7 N s motor at 280 s needs 3,641 kg."""
    mp = sm.propellant_mass_from_total_impulse(1.0e7, 280.0)
    assert mp == pytest.approx(1.0e7 / (G0 * 280.0), rel=1e-12)
    assert mp == pytest.approx(3641.0, abs=1.0)
    with pytest.raises(ValueError):
        sm.propellant_mass_from_total_impulse(-1.0, 280.0)


# ---------------------------------------------------------------- geometry
def test_casing_volume_is_1_12_times_grain_volume_eq_8_23_8_24():
    g = sm.size_motor_case(2.0, 20000.0, 1740.0)
    assert g.V_prop == pytest.approx(20000.0 / 1740.0, rel=1e-12)          # Eq. 8:23
    assert g.V_int == pytest.approx(1.12 * g.V_prop, rel=1e-12)            # Eq. 8:24
    assert g.volume_check() == pytest.approx(0.0, abs=1e-9)                # cylinder + 2 hemispheres


def test_grain_volume_matches_the_propellant_volume_analytically_and_numerically():
    for D, m in ((2.0, 20000.0), (1.3, 30000.0), (3.0, 90000.0)):
        g = sm.size_motor_case(D, m, 1740.0)
        v_analytic = sm.grain_volume(g.R_int, g.h_dome, g.h_cyl, g.R_bore, g.bore_full_length)
        assert v_analytic == pytest.approx(g.V_prop, rel=1e-9)
        assert g.grain_volume_numeric() == pytest.approx(g.V_prop, rel=2e-3)
        assert 0 < g.R_bore < g.R_int
        assert g.web_m == pytest.approx(g.R_int - g.R_bore, rel=1e-12)


def test_short_fat_motor_runs_the_bore_through_the_domes():
    """A small motor in a wide case cannot hold its free volume in a barrel bore alone."""
    g = sm.size_motor_case(0.97, 650.0, 1740.0, dome_AR=1.2)
    assert g.bore_full_length is True
    assert sm.grain_volume(g.R_int, g.h_dome, g.h_cyl, g.R_bore, True) == pytest.approx(g.V_prop, rel=1e-9)
    assert g.grain_volume_numeric() == pytest.approx(g.V_prop, rel=3e-3)


def test_dome_bore_volume_limits():
    R, h = 1.0, 1.0
    assert sm.dome_bore_volume(R, h, 0.0) == 0.0
    whole = 2.0 * math.pi * R * R * h / 3.0
    assert sm.dome_bore_volume(R, h, R) == pytest.approx(whole, rel=1e-12)
    assert 0 < sm.dome_bore_volume(R, h, 0.5) < whole


def test_motor_too_fat_for_its_propellant_is_rejected():
    with pytest.raises(InfeasibleGeometry):
        sm.size_motor_case(3.0, 200.0, 1740.0)              # two hemispheres already exceed the casing volume


def test_implied_burn_rate_is_web_over_burn_time():
    g = sm.size_motor_case(1.3, 30000.0, 1740.0)
    assert g.implied_burn_rate_mps(100.0) == pytest.approx(g.web_m / 100.0, rel=1e-12)


def test_hemispherical_domes_are_the_book_recommendation_but_ar_is_configurable():
    a = sm.size_motor_case(2.0, 20000.0, 1740.0, dome_AR=1.0)
    b = sm.size_motor_case(2.0, 20000.0, 1740.0, dome_AR=2.0)
    assert b.h_dome < a.h_dome                                  # shallower domes
    assert b.h_cyl > a.h_cyl                                    # longer barrel for the same volume
    assert b.V_int == pytest.approx(a.V_int, rel=1e-12)


# ---------------------------------------------------------------- stage level
def test_solid_stage_has_no_engine_thrust_structure_or_feed_system(capsys=None):
    """Book p.490: the casing MER already includes the nozzle, thrust structure, gimbals and insulation."""
    r = book_solid_result()
    for s in r.stages:
        assert s.is_solid
        names = set(s.components)
        assert not {"Engines", "Engine gimbals", "Thrust structure", "Feed system", "Pressurant system"} & names
        assert any(n.startswith("Motor casing") for n in names)
        assert "Aft skirt" in names and "Forward skirt" in names      # book p.490 item 7


def test_solid_stage_mass_closure_and_structural_factor_near_the_book_value():
    r = book_solid_result()
    for s in r.stages:
        assert s.m_prop_loaded_kg == pytest.approx(s.m_prop_mission_kg + s.m_startup_kg + s.m_residual_kg + s.m_margin_prop_kg, rel=1e-12)
        assert s.m_startup_kg == 0.0                                   # book p.489: instantaneous ignition
        assert s.m_residual_kg == 0.0                                  # book p.489: complete combustion
        casing = [v for k, v in s.components.items() if k.startswith("Motor casing")][0]
        assert casing == pytest.approx(sm.K_SRM["composite"] * s.m_prop_loaded_kg, rel=1e-9)
    # a bare Gr/E motor would have s = 0.1035; skirts, avionics and margin push the stage above that
    assert r.stages[0].structural_factor_s > sm.S_SRM["composite"]
    assert r.stages[0].structural_factor_s < 0.16


def test_solid_motor_reports_grain_geometry_and_a_plausible_burn_rate():
    r = book_solid_result()
    for s in r.stages:
        info = s.motor_info
        assert info["grain_volume_m3"] > 0
        assert info["casing_volume_m3"] == pytest.approx(1.12 * info["grain_volume_m3"], rel=1e-9)
        assert 1.0 < info["implied_burn_rate_mm_s"] < 40.0             # composite propellant range
        assert info["casing_k"] == pytest.approx(sm.K_SRM["composite"], rel=1e-9)


def test_solid_vehicle_converges_and_closes_mass():
    r = solid_result()
    assert r.converged
    total = r.payload_mass_kg + r.paf_mass_kg + r.fairing_mass_kg + sum(s.m_dry_kg + s.m_prop_loaded_kg for s in r.stages)
    assert total == pytest.approx(r.glom_kg, rel=1e-12)
    assert not [i for i in r.issues if i.level == "ERROR"]


def test_grain_centre_of_mass_lies_inside_the_casing():
    r = solid_result()
    for s in r.stages:
        seg = [x for x in r.geometry.stage_segments(s.index) if x.kind == "tank"][0]
        item = [i for i in r.ledger if i.stage == s.index and i.kind == "prop_loaded"][0]
        assert seg.z0 < item.z_m < seg.z1
        # a centre-perforated grain in a symmetric casing has its CM near the mid-length
        assert item.z_m == pytest.approx(seg.z_mid, rel=0.05)
