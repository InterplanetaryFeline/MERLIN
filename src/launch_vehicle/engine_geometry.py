"""Rubber-engine / nozzle dimensioning from thrust, chamber pressure and expansion ratio.

Verified book equations (Section 8.7.7, printed pp. 507-511; PDF page = printed + 35):
  Eq. 8:28  A_t   = c_del T_vac / (P_c g0 Isp_vac)
  Eq. 8:29  T_vac = T_SL / (1 - P1 c_del eps / (P_c g0 Isp_vac))
  Eq. 8:30  L_nozzle = (D_exit - D_throat) * percent_length / (2 tan 15 deg)      (percent_length = 0.80)
  Eq. 8:31  L_cc  = cbrt(4 L* A_t LthRatio / pi)                                   (L* = 0.75 m, LthRatio = 0.9)
  Eq. 8:32  D_cc  = L_cc / LthRatio
  Eq. 8:33  L_conv = (D_cc - D_throat) / (2 tan alpha_conv)                        (alpha_conv = 30 deg)
  D_exit = sqrt(eps) D_throat ;  overall engine length = L_cc + L_conv + L_nozzle

Verified against the book's worked Example 3 (p. 509-510, step-1 engine: T_SL = 698.2 kN, eps = 20,
Pc = 20.68 MPa, c_del = 1789 m/s, Isp_vac = 336 s) which prints
  A_t = 0.0183 m^2, D_throat = 0.153 m, D_exit = 0.68 m, L_nozzle = 0.79 m, L_cc = 0.251 m,
  D_cc = 0.278 m, L_conv = 0.109 m, overall 1.15 m.
NOTE (documented discrepancy): the same example's step-2 column prints L_nozzle = 1.87 m, but Eq. 8:30 with
its own printed throat/exit diameters (0.123 m / 1.23 m) gives 1.65 m. This module follows the equation.

These are preliminary dimensions for layout and drawing only (the book: "replace as soon as a suitable
existing engine is found").
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from .units import G0

TAN15 = math.tan(math.radians(15.0))


class EngineGeometryError(ValueError):
    pass


@dataclass
class EngineDimensions:
    throat_area_m2: float
    throat_diameter_m: float
    exit_diameter_m: float
    nozzle_length_m: float
    chamber_length_m: float
    chamber_diameter_m: float
    convergent_length_m: float
    overall_length_m: float
    thrust_vac_N: float
    source: str = "Book Eqs. 8:28-8:33 (pp.507-511)"


def vacuum_thrust_from_sea_level(T_sl_N: float, p_ambient_Pa: float, c_del_mps: float, eps: float,
                                 pc_Pa: float, isp_vac_s: float) -> float:
    """Eq. 8:29. Raises if the denominator is non-positive (non-physical combination)."""
    den = 1.0 - p_ambient_Pa * c_del_mps * eps / (pc_Pa * G0 * isp_vac_s)
    if den <= 0:
        raise EngineGeometryError("Eq. 8:29 denominator <= 0: expansion ratio too large for this chamber pressure")
    return T_sl_N / den


def throat_area(T_vac_N: float, c_del_mps: float, pc_Pa: float, isp_vac_s: float) -> float:
    """Eq. 8:28."""
    if min(T_vac_N, c_del_mps, pc_Pa, isp_vac_s) <= 0:
        raise EngineGeometryError("thrust, c*, chamber pressure and Isp must be positive")
    return c_del_mps * T_vac_N / (pc_Pa * G0 * isp_vac_s)


def engine_dimensions(T_vac_N: float, pc_Pa: float, eps: float, isp_vac_s: float, c_del_mps: float,
                      percent_length: float = 0.80, l_star_m: float = 0.75, lth_ratio: float = 0.9,
                      alpha_conv_deg: float = 30.0) -> EngineDimensions:
    """Full set of Eqs. 8:28, 8:30-8:33 for ONE engine/motor of the given vacuum thrust."""
    if eps <= 1:
        raise EngineGeometryError("expansion ratio must exceed 1")
    At = throat_area(T_vac_N, c_del_mps, pc_Pa, isp_vac_s)
    Dt = math.sqrt(4.0 * At / math.pi)
    De = math.sqrt(eps) * Dt
    Ln = (De - Dt) * percent_length / (2.0 * TAN15)                      # Eq. 8:30
    Lcc = (4.0 * l_star_m * At * lth_ratio / math.pi) ** (1.0 / 3.0)     # Eq. 8:31
    Dcc = Lcc / lth_ratio                                                # Eq. 8:32
    Lconv = (Dcc - Dt) / (2.0 * math.tan(math.radians(alpha_conv_deg)))  # Eq. 8:33
    if Lconv < 0:
        raise EngineGeometryError("convergent length negative: throat larger than the chamber")
    return EngineDimensions(At, Dt, De, Ln, Lcc, Dcc, Lconv, Lcc + Lconv + Ln, T_vac_N)


def nozzle_only_dimensions(T_vac_N: float, pc_Pa: float, eps: float, isp_vac_s: float, c_del_mps: float,
                           percent_length: float = 0.80) -> EngineDimensions:
    """Solid motors: the book (p.490) only needs the PROTRUDING diverging nozzle length, because the
    combustion chamber is the motor casing itself. Chamber/convergent lengths are reported as zero."""
    At = throat_area(T_vac_N, c_del_mps, pc_Pa, isp_vac_s)
    Dt = math.sqrt(4.0 * At / math.pi)
    De = math.sqrt(eps) * Dt
    Ln = (De - Dt) * percent_length / (2.0 * TAN15)
    return EngineDimensions(At, Dt, De, Ln, 0.0, 0.0, 0.0, Ln, T_vac_N,
                            "Book Eqs. 8:28/8:30 (nozzle only; chamber = motor casing, p.490)")
