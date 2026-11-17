"""Rocket equation, structural-factor conventions, aggregate sizing. Basis stated per test."""
import math
import pytest
from launch_vehicle import staging as s
from launch_vehicle.units import G0
from helpers import default_result, book_tsto_overrides


def test_rocket_equation_independent_numeric_example():
    # Basis: hand calculation: 9.80665*300*ln(100000/20000) = 2941.995 * 1.609438 = 4734.99 m/s
    assert s.delta_v(300.0, 100000.0, 20000.0) == pytest.approx(4734.99, rel=1e-5)


def test_mass_ratio_roundtrip():
    mu = s.mass_ratio_from_dv(4842.0, 340.0)
    assert mu == pytest.approx(4.2725, rel=1e-4)       # Book Example 1 p.480: mu2 = 4.27
    assert s.delta_v(340.0, mu * 1000.0, 1000.0) == pytest.approx(4842.0, rel=1e-12)


def test_nonphysical_mass_pair_raises():
    with pytest.raises(s.StagingError):
        s.delta_v(300.0, 1000.0, 1200.0)


def test_structural_factor_conversions_book_5_91():
    # Basis: Book Table 5.1 Soyuz: s = 0.0880 <-> eps = 0.0965
    assert s.eps_from_s(0.0880) == pytest.approx(0.0965, abs=1e-4)
    assert s.s_from_eps(0.0965) == pytest.approx(0.0880, abs=1e-4)
    assert s.inert_from_propellant_s(1000.0, 0.1) == pytest.approx(111.111, rel=1e-5)   # Eq. 5:90a, NOT 0.1*m_p


def test_aggregate_stage_book_example_1_step_2():
    # Basis: Book Example 1 (p.480): m_PL=10 t, dv2=4842 m/s, Isp=340, s=0.10 -> m_p2 = 51.44 t, m_s2 = 5.72 t
    mu = s.mass_ratio_from_dv(4842.0, 340.0)
    mp = s.propellant_aggregate(10000.0, 0.10, mu)
    assert mp == pytest.approx(51440.0, rel=1e-3)
    assert s.inert_from_propellant_s(mp, 0.10) == pytest.approx(5720.0, rel=2e-3)


def test_aggregate_infeasible_when_mu_s_ge_1():
    with pytest.raises(s.StagingError, match="infeasible"):
        s.propellant_aggregate(1000.0, 0.3, 4.0)


def test_bottom_up_propellant_satisfies_rocket_equation():
    U, dry, mu, fun = 12000.0, 3000.0, 3.5, 0.025
    mp = s.propellant_bottom_up(U, dry, mu, fun)
    mf = U + dry + fun * mp
    assert (mf + mp) / mf == pytest.approx(mu, rel=1e-12)


def test_bottom_up_infeasible_unburned_fraction():
    with pytest.raises(s.StagingError):
        s.propellant_bottom_up(1000.0, 100.0, 6.0, 0.25)       # 0.25*(6-1) = 1.25 >= 1


def test_full_pipeline_reproduces_book_example_1_two_stage():
    # Basis: Book Example 1 p.480-481: stage 1: m_p = 240.5 t, m_s = 20.9 t, GLOM = 328.6 t (book rounds mu to 3 digits)
    r = default_result(book_tsto_overrides())
    assert r.converged
    s1, s2 = r.stages
    assert s2.m_prop_mission_kg == pytest.approx(51440.0, rel=2e-3)
    assert s1.m_prop_mission_kg == pytest.approx(240500.0, rel=3e-3)
    assert s1.m_inert_burnout_kg == pytest.approx(20900.0, rel=3e-3)       # book 'structure' mass convention
    assert r.glom_kg == pytest.approx(328600.0, rel=2e-3)
    assert s1.structural_factor_s == pytest.approx(0.08, abs=1e-9)
    assert s2.structural_factor_s == pytest.approx(0.10, abs=1e-9)
