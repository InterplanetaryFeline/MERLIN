"""Mixture ratio convention, component masses, volumes (Book Eq. 8:5-8:10, Table 8.4, Example 1)."""
import pytest
from launch_vehicle import tank_sizing as ts


def test_mixture_ratio_split_book_table_8_4():
    # Basis: Book Table 8.4: f = m_f/m_ox = 5/16 (O/F = 3.2); fuel fraction 5/21, ox fraction 16/21; 240.5 t -> 57,262 / 183,238 kg
    m_ox, m_f = ts.split_propellant(240500.0, 3.2)
    assert m_ox / m_f == pytest.approx(3.2, rel=1e-12)
    assert m_f == pytest.approx(240500.0 * 5 / 21, rel=1e-12)
    assert m_ox + m_f == pytest.approx(240500.0, rel=1e-14)
    assert m_f == pytest.approx(57267.0, rel=2e-3)          # book value (from m_p1 = 240.55 t before rounding)
    assert m_ox == pytest.approx(183254.0, rel=2e-3)


def test_invalid_mixture_ratio_raises():
    with pytest.raises(ValueError):
        ts.split_propellant(1000.0, 0.0)


def test_cryogenic_shrinkage_book_eq_8_12():
    # Basis: Book Eq. 8:12: shrink_LOx = 3 alpha dT = 3(23.4e-6)(293-90) = 0.0143
    assert ts.shrink_fraction(23.4e-6, 293.0, 90.1) == pytest.approx(0.0143, abs=1e-4)
    assert ts.shrink_fraction(23.4e-6, 293.0, 20.7) == pytest.approx(0.0191, abs=2e-4)


def test_required_volumes_book_example_1():
    # Basis: Book Example 1 pp.483-484: RP-1 71.66 m3 -> 73.81 m3 (x1.03); LOX 164.95 -> 172.2 (x1.0443)
    v, ull, shr, req = ts.required_volume(58762.0, 820.0, 0.03, 0.0)
    assert v == pytest.approx(71.66, rel=1e-3)
    assert req == pytest.approx(73.81, rel=1e-3)
    v, ull, shr, req = ts.required_volume(188038.0, 1140.0, 0.03, 0.0143)
    assert v == pytest.approx(164.95, rel=1e-3)
    assert req == pytest.approx(172.2, rel=1e-3)
    assert ull == pytest.approx(0.03 * v, rel=1e-12)
    assert shr == pytest.approx(0.0143 * v, rel=1e-12)


def test_propellant_volumes_use_separate_densities_in_pipeline():
    from helpers import default_result
    r = default_result()
    s = r.stages[0]
    t = {x.role: x for x in s.tanks}
    assert t["fuel"].V_liquid == pytest.approx(s.prop_masses["fuel"] / 820.0, rel=1e-12)
    assert t["oxidizer"].V_liquid == pytest.approx(s.prop_masses["oxidizer"] / 1140.0, rel=1e-12)
    assert s.prop_masses["oxidizer"] / s.prop_masses["fuel"] == pytest.approx(2.5, rel=1e-12)
    assert s.prop_masses["oxidizer"] + s.prop_masses["fuel"] == pytest.approx(s.m_prop_loaded_kg, rel=1e-12)
    # ullage 3% on both, LOX also gets shrinkage (RP-1 none)
    assert t["fuel"].V_int == pytest.approx(t["fuel"].V_liquid * 1.03, rel=1e-12)
    assert t["oxidizer"].V_int > t["oxidizer"].V_liquid * 1.04
