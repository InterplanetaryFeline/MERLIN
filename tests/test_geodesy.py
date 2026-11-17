"""Spherical geodesy: the step that turns a downrange distance into a place on the map.

Worth testing hard because every error here is silent. A downrange distance that is right and an azimuth that
is right still put the impact in the wrong ocean if the direct problem is coded wrong, and nothing downstream
would complain - a polygon in the wrong hemisphere looks exactly as plausible as one in the right hemisphere.
The tests are therefore mostly closed-form cases where the answer is known without trusting the formula:
quarter circumferences, the equator, the poles, and the antimeridian.
"""
import math

from launch_vehicle import geodesy as gd

R = gd.R_EARTH_M
QUARTER = 0.5 * math.pi * R          # a quarter of the way round, where the answer is exact


# ------------------------------------------------------------------ the direct problem
def test_due_east_a_quarter_circumference_from_the_equator_lands_on_the_equator():
    lat, lon = gd.destination(0.0, 0.0, 90.0, QUARTER)
    assert abs(lat) < 1e-6, f"a due-east great circle from the equator is the equator, got latitude {lat}"
    assert abs(lon - 90.0) < 1e-6, lon


def test_due_north_from_the_equator_climbs_one_degree_per_degree_of_arc():
    for deg in (1.0, 10.0, 45.0):
        lat, lon = gd.destination(0.0, 0.0, 0.0, math.radians(deg) * R)
        assert abs(lat - deg) < 1e-6, f"{deg} deg of arc due north gave latitude {lat}"
        assert abs(lon) < 1e-6, f"due north must not change longitude, got {lon}"


def test_due_north_a_quarter_circumference_reaches_the_pole():
    lat, _lon = gd.destination(0.0, 0.0, 0.0, QUARTER)
    assert abs(lat - 90.0) < 1e-6, lat


def test_zero_distance_stays_put():
    lat, lon = gd.destination(28.5, -80.604, 90.0, 0.0)
    assert abs(lat - 28.5) < 1e-12 and abs(lon + 80.604) < 1e-12


def test_a_negative_distance_walks_backwards_up_range():
    """An uprange point is wanted whenever a dispersion box starts behind the nominal impact."""
    fwd = gd.destination(0.0, 0.0, 90.0, 1000e3)
    back = gd.destination(0.0, 0.0, 90.0, -1000e3)
    assert fwd[1] > 0 > back[1], (fwd, back)
    assert abs(fwd[1] + back[1]) < 1e-9, "forwards and backwards should be symmetric on the equator"


def test_crossing_the_antimeridian_wraps_instead_of_running_past_180():
    lat, lon = gd.destination(0.0, 179.0, 90.0, math.radians(3.0) * R)
    assert -180.0 < lon <= 180.0, f"longitude {lon} is outside the wrapped range"
    assert abs(lon - (-178.0)) < 1e-6, f"3 deg east of 179 E is 178 W, got {lon}"


def test_a_due_east_track_from_mid_latitude_bends_towards_the_equator():
    """A great circle is not a parallel: this is the behaviour that makes the ground track curve on a map."""
    lat, _ = gd.destination(28.5, -80.6, 90.0, 1500e3)
    assert lat < 28.5, f"a due-east great circle must shed latitude, got {lat}"
    assert lat > 20.0, f"1500 km should not shed that much latitude, got {lat}"


# ------------------------------------------------------------------ the inverse problem, as a cross-check
def test_distance_and_bearing_invert_the_direct_problem():
    for (lat0, lon0, az, d) in ((28.5, -80.6, 90.0, 1084e3), (69.3, 16.0, 350.0, 600e3),
                                (-33.0, 151.0, 120.0, 2500e3)):
        lat, lon = gd.destination(lat0, lon0, az, d)
        back = gd.arc_distance_m(lat0, lon0, lat, lon)
        assert abs(back - d) < 1.0, f"round trip lost {abs(back - d):.1f} m"
        brg = gd.initial_bearing(lat0, lon0, lat, lon)
        assert abs((brg - az + 180.0) % 360.0 - 180.0) < 1e-6, f"bearing came back {brg} not {az}"


def test_initial_bearing_along_the_equator_is_due_east():
    assert abs(gd.initial_bearing(0.0, 0.0, 0.0, 10.0) - 90.0) < 1e-9


# ------------------------------------------------------------------ the track polyline
def test_the_track_starts_at_the_pad_and_ends_at_the_distance_asked_for():
    pts = gd.track(28.5, -80.6, 90.0, 1000e3, n=20)
    assert len(pts) == 20
    assert abs(pts[0][0] - 28.5) < 1e-9 and abs(pts[0][1] + 80.6) < 1e-9
    assert abs(gd.arc_distance_m(28.5, -80.6, *pts[-1]) - 1000e3) < 1.0


def test_the_track_is_sampled_not_just_two_points():
    """A two-point line is a straight line on a map, which a great circle is not."""
    assert len(gd.track(28.5, -80.6, 90.0, 3000e3)) >= 8


# ------------------------------------------------------------------ the corridor
def test_the_corridor_ring_is_closed():
    ring = gd.corridor_polygon(28.5, -80.6, 90.0, 900e3, 1200e3, 50e3, n=12)
    assert ring[0] == ring[-1], "an unclosed ring is not a polygon"
    assert len(ring) == 2 * 12 + 1


def test_the_corridor_is_as_wide_as_it_was_asked_to_be():
    """The width is the whole point: it is an assumption the caller states, so it must appear at full size."""
    half = 40e3
    ring = gd.corridor_polygon(0.0, 0.0, 90.0, 1000e3, 1000e3, half, n=3)
    centre = gd.destination(0.0, 0.0, 90.0, 1000e3)
    for p in ring:
        d = gd.arc_distance_m(*centre, *p)
        assert abs(d - half) < 2e3, f"ring point sits {d/1e3:.1f} km from the centreline, not {half/1e3:.0f} km"


def test_the_corridor_spans_the_along_track_interval_it_was_given():
    near, far = 900e3, 1200e3
    ring = gd.corridor_polygon(0.0, 0.0, 90.0, near, far, 30e3, n=8)
    along = [gd.arc_distance_m(0.0, 0.0, *p) for p in ring]
    assert min(along) < near + 60e3, f"nearest ring point is {min(along)/1e3:.0f} km, expected near {near/1e3:.0f}"
    assert max(along) > far - 60e3, f"farthest ring point is {max(along)/1e3:.0f} km, expected near {far/1e3:.0f}"


def test_a_southerly_corridor_is_offset_the_other_way_round():
    """Left and right of the track must not be hard-coded to a hemisphere."""
    north = gd.corridor_polygon(0.0, 0.0, 0.0, 500e3, 500e3, 50e3, n=3)
    east = gd.corridor_polygon(0.0, 0.0, 90.0, 500e3, 500e3, 50e3, n=3)
    # offsetting a due-north track moves it in longitude; a due-east track moves in latitude
    assert max(abs(p[1]) for p in north) > 0.3, "a northward track should be widened in longitude"
    assert max(abs(p[0]) for p in east) > 0.3, "an eastward track should be widened in latitude"


# ------------------------------------------------------------------ the sphere's own error
def test_the_sphere_error_is_reported_and_scales_with_distance():
    assert gd.position_error_m(0.0) == 0.0
    a, b = gd.position_error_m(1000e3), gd.position_error_m(2000e3)
    assert abs(b - 2 * a) < 1e-6, "the error is quoted as a fraction of distance, so it must scale linearly"
    assert 1e3 < a < 20e3, f"half a percent of 1000 km should be a few km, got {a/1e3:.1f} km"
