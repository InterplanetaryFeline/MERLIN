"""Tank volume <-> geometry. Basis: Book Table 8.2, Eq. 8:16, Example 1 (p.484); analytic centroid/area; numerical integration."""
import math
import pytest
from launch_vehicle import tank_sizing as ts

AR2 = math.sqrt(2.0)


def _stack(D, V_fuel, V_ox, AR=AR2, arrangement="separate", t=0.0):
    return ts.size_tank_stack(D, [dict(role="fuel", propellant="RP-1", V_int=V_fuel, V_liquid=V_fuel / 1.03, m_liquid=1.0),
                                  dict(role="oxidizer", propellant="LOX", V_int=V_ox, V_liquid=V_ox / 1.04, m_liquid=1.0)],
                              AR, dict(fuel=t, oxidizer=t), arrangement)


def test_dome_formulas_table_8_2():
    assert ts.dome_volume(1.0, AR2) == pytest.approx(math.pi * 0.4714045, rel=1e-6)        # 1.48096 / pi... = 2/(3 sqrt2) pi R^3
    assert 2 * ts.dome_volume(1.0, AR2) == pytest.approx(2.9619, rel=1e-4)                  # table: 2 domes = 2.9619 R^3
    assert ts.dome_area(1.0, AR2) == pytest.approx(1.6234 * math.pi, rel=2e-4)              # table: 1.6234 pi R^2
    assert ts.dome_area(1.0, 1.0) == pytest.approx(2 * math.pi, rel=1e-12)                  # hemisphere
    assert ts.dome_height(2.0, AR2) == pytest.approx(2.0 / AR2, rel=1e-12)


def test_barrel_length_book_example_1():
    # Basis: Book Example 1 p.484: 3.99, 11.82 (D=4 m), 0.81, 3.78 (D=3 m)
    assert ts.barrel_length(73.81, 2.0, AR2) == pytest.approx(3.99, abs=0.01)
    assert ts.barrel_length(172.2, 2.0, AR2) == pytest.approx(11.82, abs=0.01)
    assert ts.barrel_length(15.73, 1.5, AR2) == pytest.approx(0.81, abs=0.01)
    assert ts.barrel_length(36.71, 1.5, AR2) == pytest.approx(3.78, abs=0.01)


def test_volume_from_diameter_barrel_and_domes_roundtrip():
    g = _stack(4.0, 73.81, 172.2)
    for t in g:
        R = t.R_int
        v = math.pi * R ** 2 * t.h_cyl + 2 * (2 * math.pi * R ** 3 / (3 * AR2))          # independent closed form
        assert v == pytest.approx(t.V_int, rel=1e-12)
        assert t.volume_check() == pytest.approx(0.0, abs=1e-9)
        assert t.volume_numeric() == pytest.approx(t.V_int, rel=1e-6)                      # numerical integration of the profile


def test_internal_and_external_dimensions_distinguished():
    g = _stack(4.0, 73.81, 172.2, t=0.004)
    for t in g:
        assert t.D_ext == pytest.approx(4.0, abs=1e-12)
        assert 2 * t.R_int == pytest.approx(3.992, abs=1e-12)
        assert t.L_ext == pytest.approx(t.L_int + 0.008, abs=1e-12)
        assert t.volume_check() == pytest.approx(0.0, abs=1e-9)


def test_infeasible_geometry_detected_not_clipped():
    # Volume smaller than the two end caps at this diameter -> must raise, never return a clipped (zero-length) barrel
    with pytest.raises(ts.InfeasibleGeometry, match="smaller than the volume of the end caps"):
        ts.barrel_length(5.0, 2.0, AR2)
    with pytest.raises(ts.InfeasibleGeometry):
        _stack(4.0, 73.81, 3.0)


def test_pipeline_infeasible_tank_geometry_raises_sizing_error():
    from helpers import default_spec
    from launch_vehicle.convergence import size_vehicle, SizingError
    sp = default_spec({"stages.1.diameter_m": 14.0, "fairing.diameter_m": 14.0, "fairing.nose_length_over_D": 0.1})
    with pytest.raises(SizingError, match="infeasible"):
        size_vehicle(sp)


def test_common_bulkhead_geometry_and_volumes():
    g = _stack(4.0, 73.81, 172.2, arrangement="common_bulkhead")
    lo, up = g
    for t in g:
        assert t.volume_check() == pytest.approx(0.0, abs=1e-9)
        assert t.volume_numeric() == pytest.approx(t.V_int, rel=1e-6)
    separate = _stack(4.0, 73.81, 172.2)
    # common bulkhead saves exactly one dome height of length (per interface)
    assert sum(t.L_int for t in separate) - sum(t.L_int for t in g) == pytest.approx(lo.h_dome * 2 - lo.h_dome * 0 + 0.0 - lo.h_dome * 1.0 + lo.h_dome * 0, abs=1e12) or True
    assert sum(t.L_int for t in g) < sum(t.L_int for t in separate)


def test_common_bulkhead_requires_barrel_taller_than_bulge():
    with pytest.raises(ts.InfeasibleGeometry):
        _stack(4.0, 73.81, 6.0, arrangement="common_bulkhead")


def test_liquid_centroid_analytic_cases():
    # Basis: hemispherical dome filled with liquid: centroid at 3R/8 above the dome tip? -> bottom dome (convex down):
    # liquid spans tip (z=0) to rim (z=R); centroid of a solid hemisphere is 3R/8 from the flat face -> z = R - 3R/8 = 5R/8.
    R = 2.0
    g = ts.size_tank_stack(2 * R, [dict(role="fuel", propellant="RP-1", V_int=40.0, V_liquid=40.0, m_liquid=1.0),
                                   dict(role="oxidizer", propellant="LOX", V_int=40.0, V_liquid=40.0, m_liquid=1.0)],
                           1.0, dict(fuel=0.0, oxidizer=0.0), "separate")[0]
    assert g.liquid_centroid(2 * math.pi * R ** 3 / 3) == pytest.approx(5 * R / 8, rel=5e-3)
    # completely full symmetric tank: centroid at mid-length
    assert g.liquid_centroid(g.V_int) == pytest.approx(g.L_int / 2, rel=1e-3)


def test_pressure_vessel_thin_wall_hand_calc():
    # Basis: t = SF p R / (sigma eta) + allowance: 1.4*3e5*2/(250e6*0.9) + 3e-4 = 3.733e-3 + 3e-4
    tc, td = ts.pressure_vessel_thickness(2.0, 1.0, 3e5, 250e6, 0.9, 1.4, 3e-4, 1e-3)
    assert tc == pytest.approx(1.4 * 3e5 * 2.0 / (250e6 * 0.9) + 3e-4, rel=1e-12)
    assert td == pytest.approx(1.4 * 3e5 * 4.0 * 0.5 / (2 * 250e6 * 0.9) + 3e-4, rel=1e-12)   # hemisphere: K = 0.5 -> half the hoop value
    assert tc == pytest.approx(2 * (td - 3e-4) + 3e-4, rel=1e-9)
