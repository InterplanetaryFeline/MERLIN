"""Rubber-engine dimensioning (book Sec. 8.7.7, Eqs. 8:28-8:33) against the book's own worked Example 3.

Book Example 3 (printed pp. 509-511), step-1 engine of the example two-step vehicle:
  inputs  T_SL = 698.2 kN per engine, eps = 20, Pc = 20.68 MPa, c*_delivered = 1,789 m/s, Isp_vac = 336 s
  printed A_t = 0.0183 m2, D_throat = 0.153 m, D_exit = 0.68 m, L_nozzle = 0.79 m,
          L_chamber = 0.251 m, D_chamber = 0.278 m, L_convergent = 0.109 m, overall 1.15 m
"""
import math
import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import engine_geometry as eg
from launch_vehicle.units import G0

PC, CSTAR, ISP, EPS = 20.68e6, 1789.0, 336.0, 20.0


def test_vacuum_thrust_satisfies_the_books_own_identity_and_flags_its_printed_value():
    """Eq. 8:29 with the example's inputs gives 737.4 kN, NOT the 705.2 kN printed on p.509.

    The book states T_SL = T_vac - P1 A_e. Only 737.4 kN satisfies that identity with the example's own
    698.2 kN sea-level thrust (705.2 kN would imply T_SL = 667.7 kN), so the printed intermediate value is an
    arithmetic slip and this tool follows the equation. Everything downstream of T_vac is verified separately
    against the book's printed numbers in test_full_engine_dimensions_reproduce_book_example.
    """
    t_vac = eg.vacuum_thrust_from_sea_level(698.2e3, 101325.0, CSTAR, EPS, PC, ISP)
    assert t_vac / 1e3 == pytest.approx(737.4, abs=0.5)
    d = eg.engine_dimensions(t_vac, PC, EPS, ISP, CSTAR)
    assert t_vac - 101325.0 * EPS * d.throat_area_m2 == pytest.approx(698.2e3, rel=1e-6)
    assert abs(t_vac / 1e3 - 705.2) > 20.0                     # the printed value is not self-consistent


def test_throat_area_and_diameter_reproduce_book_example():
    """Eq. 8:28 and D = sqrt(4A/pi) with the book's own T_vac: 0.0183 m2 and 0.153 m (book p.510)."""
    at = eg.throat_area(705.2e3, CSTAR, PC, ISP)
    assert at == pytest.approx(0.0183, abs=0.0005)             # book rounds to 3 significant digits
    assert math.sqrt(4 * at / math.pi) == pytest.approx(0.153, abs=0.002)


def test_full_engine_dimensions_reproduce_book_example():
    """Given the book's own T_vac, every printed dimension of Example 3 is reproduced."""
    d = eg.engine_dimensions(705.2e3, PC, EPS, ISP, CSTAR)
    assert d.throat_diameter_m == pytest.approx(0.153, abs=0.002)       # book 0.153 m
    assert d.exit_diameter_m == pytest.approx(0.68, abs=0.01)           # book 0.68 m
    assert d.nozzle_length_m == pytest.approx(0.79, abs=0.01)           # book 0.79 m
    assert d.chamber_length_m == pytest.approx(0.251, abs=0.004)        # book 0.251 m
    assert d.chamber_diameter_m == pytest.approx(0.278, abs=0.005)      # book 0.278 m
    assert d.convergent_length_m == pytest.approx(0.109, abs=0.004)     # book 0.109 m
    assert d.overall_length_m == pytest.approx(1.15, abs=0.02)          # book 1.15 m


def test_step_2_engine_of_the_book_example_and_its_printed_nozzle_length_discrepancy():
    """Book step-2 column: T = 461 kN, eps = 100 -> printed D_throat 0.123 m, D_exit 1.23 m, L_nozzle 1.87 m.

    Eq. 8:30 applied to the book's OWN printed diameters gives 1.65 m, not 1.87 m. This test pins the
    equation-consistent value and documents the discrepancy rather than hiding it.
    """
    d = eg.engine_dimensions(461e3, PC, 100.0, ISP, CSTAR)
    assert d.throat_diameter_m == pytest.approx(0.123, abs=0.002)
    assert d.exit_diameter_m == pytest.approx(1.23, abs=0.02)
    book_printed = 1.87
    by_equation = (d.exit_diameter_m - d.throat_diameter_m) * 0.80 / (2 * math.tan(math.radians(15.0)))
    assert d.nozzle_length_m == pytest.approx(by_equation, rel=1e-12)
    assert d.nozzle_length_m == pytest.approx(1.65, abs=0.03)
    assert abs(book_printed - d.nozzle_length_m) > 0.15                  # the printed value is not reproducible


def test_solid_motor_nozzle_only_has_no_chamber():
    d = eg.nozzle_only_dimensions(1.0e6, 6.0e6, 16.0, 282.0, 1577.0)
    assert d.chamber_length_m == 0.0 and d.convergent_length_m == 0.0
    assert d.overall_length_m == pytest.approx(d.nozzle_length_m, rel=1e-12)
    assert d.exit_diameter_m == pytest.approx(4.0 * d.throat_diameter_m, rel=1e-12)   # sqrt(16) = 4


def test_expansion_ratio_must_exceed_one_and_inputs_must_be_positive():
    with pytest.raises(eg.EngineGeometryError):
        eg.engine_dimensions(1e6, PC, 0.9, ISP, CSTAR)
    with pytest.raises(eg.EngineGeometryError):
        eg.throat_area(-1.0, CSTAR, PC, ISP)


def test_nozzle_grows_with_expansion_ratio():
    small = eg.engine_dimensions(705.2e3, PC, 10.0, ISP, CSTAR)
    big = eg.engine_dimensions(705.2e3, PC, 100.0, ISP, CSTAR)
    assert big.exit_diameter_m > small.exit_diameter_m
    assert big.nozzle_length_m > small.nozzle_length_m
    assert big.throat_diameter_m == pytest.approx(small.throat_diameter_m, rel=1e-12)
