"""Orbital-mechanics helpers: speeds, periods, energy, launch azimuth, rotation benefit.

References
----------
Eq. 3:1 circular speed, Eq. 3:2 r = R + h, Eq. 3:3/3:4 vis-viva: book pp. 156-157 (verified).
Launch-site rotation velocity and SEZ-vector treatment of 'needed' speed: book Example 3.9, p. 185
(verified numerically: 0.4087 km/s at 28.5 deg latitude).
Azimuth from inclination (sin(beta) = cos(i)/cos(lat)) is the standard spherical-trig result (the book
treats the same geometry around pp. 188-190); implemented independently here (supplementary).
SSO node-rate relation uses the J2 secular drift (supplementary).
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from .units import EarthModel, SIDEREAL_YEAR_S


class OrbitError(ValueError):
    """Invalid or unsupported orbit definition."""


@dataclass(frozen=True)
class OrbitElements:
    perigee_alt_m: float
    apogee_alt_m: float
    a_m: float
    e: float
    r_p_m: float
    r_a_m: float
    v_perigee_ms: float
    v_apogee_ms: float
    period_s: float
    specific_energy_J_kg: float
    inclination_deg: float


def circular_speed(r: float, mu: float) -> float:
    """Eq. 3:1: v = sqrt(mu/r)."""
    if r <= 0:
        raise OrbitError("orbital radius must be positive")
    return math.sqrt(mu / r)


def vis_viva(r: float, a: float, mu: float) -> float:
    """Eq. 3:4: v = sqrt(mu (2/r - 1/a))."""
    val = mu * (2.0 / r - 1.0 / a)
    if val <= 0:
        raise OrbitError("vis-viva gives non-positive v^2 (bound orbit requires r <= 2a)")
    return math.sqrt(val)


def period(a: float, mu: float) -> float:
    return 2.0 * math.pi * math.sqrt(a ** 3 / mu)


def specific_energy(a: float, mu: float) -> float:
    return -mu / (2.0 * a)


def orbit_from_altitudes(earth: EarthModel, perigee_alt_m: float, apogee_alt_m: float | None = None,
                         eccentricity: float | None = None, inclination_deg: float = 0.0) -> OrbitElements:
    R = earth.radius_m
    if perigee_alt_m <= 0:
        raise OrbitError("perigee altitude must be > 0")
    rp = R + perigee_alt_m
    if apogee_alt_m is None and eccentricity is None:
        apogee_alt_m = perigee_alt_m
    if apogee_alt_m is not None and eccentricity is not None:
        ra_chk = rp * (1 + eccentricity) / (1 - eccentricity)
        if abs(ra_chk - (R + apogee_alt_m)) > 1.0:
            raise OrbitError("apogee altitude and eccentricity are inconsistent (specify only one)")
    if apogee_alt_m is None:
        if not (0 <= eccentricity < 1):
            raise OrbitError("eccentricity must satisfy 0 <= e < 1")
        ra = rp * (1 + eccentricity) / (1 - eccentricity)
        apogee_alt_m = ra - R
    ra = R + apogee_alt_m
    if ra < rp:
        raise OrbitError("apogee radius is below perigee radius")
    a = 0.5 * (ra + rp)
    e = (ra - rp) / (ra + rp)
    mu = earth.mu_m3s2
    return OrbitElements(perigee_alt_m, apogee_alt_m, a, e, rp, ra,
                         vis_viva(rp, a, mu), vis_viva(ra, a, mu), period(a, mu),
                         specific_energy(a, mu), inclination_deg)


def sso_inclination_deg(earth: EarthModel, a_m: float, e: float) -> float:
    """Inclination of a sun-synchronous orbit from the J2 secular nodal rate (supplementary).

    dOmega/dt = -1.5 J2 n (R/p)^2 cos i  =  2*pi / (tropical year)
    """
    n = math.sqrt(earth.mu_m3s2 / a_m ** 3)
    p = a_m * (1 - e * e)
    rate = 2.0 * math.pi / SIDEREAL_YEAR_S
    cos_i = -rate / (1.5 * earth.j2 * n * (earth.radius_m / p) ** 2)
    if abs(cos_i) > 1:
        raise OrbitError("no sun-synchronous inclination exists for this altitude")
    return math.degrees(math.acos(cos_i))


def launch_azimuth_deg(inclination_deg: float, latitude_deg: float) -> float:
    """Inertial launch azimuth (deg from North, clockwise) for a direct ascent: sin(beta)=cos(i)/cos(lat).

    Returns the ascending-pass azimuth in [-90, 90]; negative = west of north (retrograde).
    Raises if inclination < |latitude| (would need a dog-leg: not modelled).
    """
    c = math.cos(math.radians(inclination_deg)) / math.cos(math.radians(latitude_deg))
    if abs(c) > 1.0 + 1e-12:
        raise OrbitError(
            f"inclination {inclination_deg:.2f} deg is lower than launch-site latitude "
            f"{latitude_deg:.2f} deg: a direct ascent is impossible (dog-leg / plane change not modelled)")
    return math.degrees(math.asin(max(-1.0, min(1.0, c))))


def site_rotation_speed(earth: EarthModel, latitude_deg: float) -> float:
    """Eastward launch-site speed from Earth rotation: omega R cos(lat) (book Example 3.9: 0.4087 km/s at 28.5 deg)."""
    return earth.omega_rad_s * earth.radius_m * math.cos(math.radians(latitude_deg))


def needed_speed(earth: EarthModel, v_inj: float, azimuth_deg: float, latitude_deg: float,
                 flight_path_angle_deg: float = 0.0, include_rotation: bool = True) -> tuple[float, float]:
    """Magnitude of velocity the vehicle must add relative to the launch site (book Example 3.9 method).

    Returns (v_needed, v_site_used): |v_injection - v_launch_site| with the site moving due East.
    """
    b = math.radians(azimuth_deg)
    g = math.radians(flight_path_angle_deg)
    vN = v_inj * math.cos(g) * math.cos(b)
    vE = v_inj * math.cos(g) * math.sin(b)
    vZ = v_inj * math.sin(g)
    vs = site_rotation_speed(earth, latitude_deg) if include_rotation else 0.0
    return math.sqrt(vN ** 2 + (vE - vs) ** 2 + vZ ** 2), vs
