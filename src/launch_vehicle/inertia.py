"""Mass moments of inertia of simple shapes about THEIR OWN centre of mass (axisymmetric: roll axis = x, pitch/yaw = transverse).

Verified book sources (printed page numbers):
  Table 8.10 (p.497) thin shells:   cylinder  Jroll = mR^2,           Jpitch = m(R^2/2 + h^2/12)
                                    cone      Jroll = mR^2/2,         Jpitch = m(R^2/4 + h^2/18)
                                    frustum   Jroll = m(R^2+r^2)/2,   Jpitch = m{(R^2+r^2)/4 + (h^2/18)[1 + 2rR/(r+R)^2]}
                                    (frustum formulas reproduce the book's Example 7, p.530-531: 1,702 and 1,842 kg m^2)
  Table 8.16 (p.521) thin ring Jroll = mR^2, Jpitch = mR^2/2.  Table 8.17 solids (cylinder, thin bar mL^2/12, sphere 2/5 m r^2: Examples 5-6, pp.527-529).
  Parallel-axis theorem, Eq. 8:37 (p.525):  J_i = J0_i + m_i x_i^2 ; assembly sums per pp.526.
The thin-hemisphere / ellipsoidal-dome rows of Table 8.16 are not legible in the supplied PDF text; dome and tank-shell inertias are
therefore obtained by NUMERICAL INTEGRATION of the thin shell of revolution (verified against the analytic hemisphere shell
Jpitch(CM) = 5/12 m R^2, Jroll = 2/3 m R^2 and the sphere), which is the same physical model.
"""
from __future__ import annotations
import math
import numpy as np


def cyl_shell(m, R, h):
    return m * R * R, m * (R * R / 2 + h * h / 12)


def cone_shell(m, R, h):
    return m * R * R / 2, m * (R * R / 4 + h * h / 18)


def frustum_shell(m, r, R, h):
    s = (r + R) ** 2
    ratio = (2 * r * R / s) if s > 0 else 0.0
    return m * (R * R + r * r) / 2, m * ((R * R + r * r) / 4 + h * h / 18 * (1 + ratio))


def ring(m, R):
    return m * R * R, m * R * R / 2


def solid_cyl(m, R, h):
    return m * R * R / 2, m * (R * R / 4 + h * h / 12)


def thin_bar(m, L):
    return 0.0, m * L * L / 12


def solid_sphere(m, r):
    return 0.4 * m * r * r, 0.4 * m * r * r


def point():
    return 0.0, 0.0


def shell_of_revolution(m, z: np.ndarray, r: np.ndarray):
    """Thin uniform shell of revolution r(z). Returns (z_cm, J_roll, J_pitch about its CM) for total mass m."""
    dz, dr = np.diff(z), np.diff(r)
    ds = np.sqrt(dz ** 2 + dr ** 2)
    rm, zm = 0.5 * (r[1:] + r[:-1]), 0.5 * (z[1:] + z[:-1])
    dA = 2 * math.pi * rm * ds
    A = dA.sum()
    w = m / A
    zc = float((w * dA * zm).sum() / m)
    j_roll = float((w * dA * rm ** 2).sum())
    j_pitch = float((w * dA * (rm ** 2 / 2 + (zm - zc) ** 2)).sum())
    return zc, j_roll, j_pitch


def solid_of_revolution(rho, z: np.ndarray, area: np.ndarray):
    """Solid of revolution from its cross-section area A(z) (disk integration). Returns (mass, z_cm, J_roll, J_pitch about CM)."""
    dz = np.diff(z)
    Am = 0.5 * (area[1:] + area[:-1])
    zm = 0.5 * (z[1:] + z[:-1])
    dm = rho * Am * dz
    m = float(dm.sum())
    if m <= 0:
        return 0.0, 0.0, 0.0, 0.0
    zc = float((dm * zm).sum() / m)
    r2 = Am / math.pi
    j_roll = float((dm * r2 / 2).sum())
    j_pitch = float((dm * (r2 / 4 + (zm - zc) ** 2)).sum())
    return m, zc, j_roll, j_pitch


def tank_outline(R_ext: float, h_dome_ext: float, h_cyl: float, n: int = 600):
    """Outer profile (z from tank bottom, r) of a cylinder with two semi-ellipsoidal domes (bottom dome convex downward)."""
    zb = np.linspace(0, h_dome_ext, n)
    rb = R_ext * np.sqrt(np.clip(1 - ((h_dome_ext - zb) / h_dome_ext) ** 2, 0, None))
    zc = np.linspace(h_dome_ext, h_dome_ext + h_cyl, 4)
    rc = np.full_like(zc, R_ext)
    zt = np.linspace(h_dome_ext + h_cyl, 2 * h_dome_ext + h_cyl, n)
    rt = R_ext * np.sqrt(np.clip(1 - ((zt - h_dome_ext - h_cyl) / h_dome_ext) ** 2, 0, None))
    return np.concatenate([zb, zc[1:-1], zt]), np.concatenate([rb, rc[1:-1], rt])
