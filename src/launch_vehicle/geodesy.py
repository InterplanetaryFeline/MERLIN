"""Spherical geodesy: turn a downrange distance and a launch azimuth into coordinates on the ground.

The trajectory module integrates in the pitch plane on a spherical, non-rotating Earth, so what it produces is a
scalar downrange arc `x` - distance along the ground from the pad. That is all the information a pitch-plane model
can carry. Putting a point on a map needs one more thing from outside the integration: the direction the plane is
pointing, which is the launch azimuth from `launch_sites.direct_ascent_azimuths_deg`.

So an impact coordinate here is exactly: start at the pad, walk `x` metres along the great circle whose initial
bearing is the launch azimuth. That is the direct problem of spherical geodesy, and the formulae are the standard
ones (Bowring / "destination point given distance and bearing").

THE SPHERE, and what it costs. The radius used is the same 6,378 km equatorial radius the trajectory integrates
with, so that the arc the integrator produced and the arc walked here are the same arc. Earth is not a sphere: a
great-circle arc on this sphere differs from the WGS84 geodesic by up to roughly half a percent of its length,
which at a 2,000 km downrange is on the order of 10 km of along-track position error. That is small next to the
drag and dispersion uncertainties this is fed by, but it is a real bias and it is reported rather than ignored.

WHAT IS NOT MODELLED HERE, because a pitch-plane trajectory cannot supply it:
  * The ground track does not bend. A real ascent's azimuth changes - a dog-leg, a yaw steer, or simply the
    rotating-Earth path - and this walks a single great circle.
  * There is no cross-range at all. A pitch-plane model has no out-of-plane state, so any corridor WIDTH here is
    an assumed input, never a prediction. See `debris.py` for how that assumption is carried and labelled.
"""
from __future__ import annotations
import math

R_EARTH_M = 6378e3        # the same equatorial radius trajectory.AscentVehicle integrates with

# Great-circle arc on this sphere against the WGS84 geodesic, as a fraction of the distance travelled. The
# flattening is 1/298.257, and the spread between a meridional and an equatorial path of the same angular length
# is of that order; half a percent is the honest round number to quote for an arbitrary azimuth.
SPHERE_VS_WGS84_REL = 0.005


def destination(lat_deg: float, lon_deg: float, azimuth_deg: float, distance_m: float,
                r_planet_m: float = R_EARTH_M) -> tuple[float, float]:
    """Walk `distance_m` from (lat, lon) along the great circle of initial bearing `azimuth_deg`.

    Returns (latitude_deg, longitude_deg) with longitude wrapped to (-180, +180]. Distance may be zero; a
    negative distance walks backwards along the same great circle, which is what an uprange point needs.
    """
    d = distance_m / float(r_planet_m)                      # angular distance, radians
    phi1 = math.radians(lat_deg)
    lam1 = math.radians(lon_deg)
    theta = math.radians(azimuth_deg)
    sin_phi2 = math.sin(phi1) * math.cos(d) + math.cos(phi1) * math.sin(d) * math.cos(theta)
    sin_phi2 = max(-1.0, min(1.0, sin_phi2))
    phi2 = math.asin(sin_phi2)
    y = math.sin(theta) * math.sin(d) * math.cos(phi1)
    x = math.cos(d) - math.sin(phi1) * sin_phi2
    lam2 = lam1 + math.atan2(y, x)
    lon = math.degrees(lam2)
    lon = (lon + 180.0) % 360.0 - 180.0
    if lon == -180.0:
        lon = 180.0
    return math.degrees(phi2), lon


def initial_bearing(lat1_deg: float, lon1_deg: float, lat2_deg: float, lon2_deg: float) -> float:
    """Initial great-circle bearing from point 1 to point 2, in [0, 360)."""
    phi1, phi2 = math.radians(lat1_deg), math.radians(lat2_deg)
    dlam = math.radians(lon2_deg - lon1_deg)
    y = math.sin(dlam) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam)
    return math.degrees(math.atan2(y, x)) % 360.0


def arc_distance_m(lat1_deg: float, lon1_deg: float, lat2_deg: float, lon2_deg: float,
                   r_planet_m: float = R_EARTH_M) -> float:
    """Great-circle distance between two points, by the haversine formula."""
    phi1, phi2 = math.radians(lat1_deg), math.radians(lat2_deg)
    dphi = phi2 - phi1
    dlam = math.radians(lon2_deg - lon1_deg)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2.0 * r_planet_m * math.asin(min(1.0, math.sqrt(a)))


def track(lat_deg: float, lon_deg: float, azimuth_deg: float, distance_m: float, n: int = 48,
          r_planet_m: float = R_EARTH_M) -> list[tuple[float, float]]:
    """The ground track as a polyline: `n` points from the pad out to `distance_m` along one great circle.

    A straight line between two distant lat/lon pairs is not a great circle on any map projection, so a track
    drawn as two points would be visibly wrong over thousands of kilometres. This samples it.
    """
    n = max(2, int(n))
    return [destination(lat_deg, lon_deg, azimuth_deg, distance_m * k / (n - 1), r_planet_m)
            for k in range(n)]


def corridor_polygon(lat_deg: float, lon_deg: float, azimuth_deg: float, near_m: float, far_m: float,
                     half_width_m: float, n: int = 24,
                     r_planet_m: float = R_EARTH_M) -> list[tuple[float, float]]:
    """A closed polygon `half_width_m` either side of the great circle, between `near_m` and `far_m` downrange.

    Built by walking the centreline and stepping perpendicular at each station, so the box follows the curve of
    the great circle instead of cutting the corner. The returned ring is closed (last point equals first).

    `half_width_m` is an input, not a result: nothing in a pitch-plane trajectory predicts cross-range.
    """
    n = max(2, int(n))
    left, right = [], []
    for k in range(n):
        s = near_m + (far_m - near_m) * k / (n - 1)
        c_lat, c_lon = destination(lat_deg, lon_deg, azimuth_deg, s, r_planet_m)
        # the local course at this station, so the offset is perpendicular to the track rather than to the
        # launch azimuth (they differ by the convergence of the meridians once the track has run a long way)
        course = initial_bearing(*destination(lat_deg, lon_deg, azimuth_deg, s - 1000.0, r_planet_m),
                                 *destination(lat_deg, lon_deg, azimuth_deg, s + 1000.0, r_planet_m))
        left.append(destination(c_lat, c_lon, (course - 90.0) % 360.0, half_width_m, r_planet_m))
        right.append(destination(c_lat, c_lon, (course + 90.0) % 360.0, half_width_m, r_planet_m))
    ring = left + list(reversed(right))
    ring.append(ring[0])
    return ring


def position_error_m(distance_m: float) -> float:
    """The along-track position error from treating Earth as a sphere, at this downrange distance."""
    return abs(float(distance_m)) * SPHERE_VS_WGS84_REL
