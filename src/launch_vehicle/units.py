"""Physical constants and unit helpers (SI internally).

Earth model
-----------
Default model is the one used by the reference book (Edberg & Costa, 2nd ed.):
mu = g0 * R^2 with g0 = 9.80665 m/s^2 and R = 6378 km (book p. 156, Eq. 3:1 and
text following it, quoted as 398,924 km^3/s^2). Reference frame: Earth-centred
inertial speeds, spherical Earth, point-mass (Keplerian) gravity, no J2 in the
ascent model. Launch-site rotation speed is added as a vector (see orbit.py).
A WGS-84 style alternative is selectable (supplementary values, not from the book).
"""
from __future__ import annotations
import math
from dataclasses import dataclass

G0 = 9.80665                  # m/s^2, standard gravity (book p. 225, text after Eq. 4:19)
PI = math.pi


@dataclass(frozen=True)
class EarthModel:
    name: str
    radius_m: float
    mu_m3s2: float
    omega_rad_s: float
    j2: float
    source: str


EARTH_BOOK = EarthModel(
    name="book",
    radius_m=6378.0e3,
    mu_m3s2=G0 * (6378.0e3) ** 2,
    omega_rad_s=7.2921159e-5,   # sidereal rotation rate, supplementary (reproduces book's 0.4087 km/s at 28.5 deg)
    j2=1.08263e-3,              # supplementary (used only for SSO inclination)
    source="mu=g0*R^2, R=6378 km: book p.156; omega, J2: supplementary standard values",
)
EARTH_WGS84 = EarthModel(
    name="wgs84",
    radius_m=6378.137e3,
    mu_m3s2=3.986004418e14,
    omega_rad_s=7.2921151467e-5,
    j2=1.08262668e-3,
    source="WGS-84 / EGM96 standard constants (supplementary, not from the book)",
)
EARTH_MODELS = {"book": EARTH_BOOK, "wgs84": EARTH_WGS84}

SIDEREAL_YEAR_S = 365.2421897 * 86400.0   # tropical year, for sun-synchronous node rate (supplementary)
