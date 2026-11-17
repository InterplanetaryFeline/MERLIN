"""Ground and flight loads (book Chapter 9).

The strongest checks here are the book's own two worked Saturn V cases, reproduced from its published inputs:
Table 9.5 (ground wind shear and moment, p.566), Table 9.8 (max-q air loads resolved into body axes, p.596),
Sec. 9.2.5 (gimbal trim and the lateral load factor) and Table 9.11 (the max-q axial running total, p.603).
Where this module disagrees with a printed number the cause is identified and asserted, so that a future change
that breaks the agreement for a different reason is caught.

After that come the identities that must hold for any vehicle: on the ground the axial curve closes on the
vehicle's weight and the shear on the total wind force; in flight the axial curve closes on the thrust, the
shear closes to zero, and the bending moment is zero at both ends because the vehicle is a free-free beam
(book p.606).
"""
import math
import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import loads as L, trajectory as tj

_C = {}


def flown():
    if "r" not in _C:
        _C["r"] = default_result()
        _C["t"] = tj.fly_design(_C["r"], dt=0.25)
    return _C["r"], _C["t"]


def cases():
    if "c" not in _C:
        r, t = flown()
        _C["c"] = L.standard_cases(r, t)
    return _C["c"]


# ====================================================================== wind models
def test_ground_wind_profile_matches_book_table_94():
    """Eq. 9:20 against the tabulated Eastern Test Range steady winds (Table 9.4, p.560)."""
    for h, v in [(3.0, 11.8), (9.1, 14.8), (18.3, 16.9), (30.5, 18.8),
                 (61.0, 21.6), (91.4, 23.4), (121.9, 24.7), (152.4, 25.9)]:
        got = L.ground_wind_steady_mps(h)
        assert abs(got - v) / v < 0.02, f"h = {h} m: {got:.2f} vs tabulated {v}"


def test_effective_ground_wind_and_dynamic_pressure():
    """Eqs. 9:22 and 9:23, checked against the one worked value in Table 9.5 (3,036 Pa at 24.2 m/s)."""
    assert L.ground_wind_effective_mps(100.0) == pytest.approx(2.85 * L.ground_wind_steady_mps(100.0))
    h = 106.405                                               # centroid of the escape tower in Table 9.5
    assert L.ground_wind_steady_mps(h) == pytest.approx(24.2, abs=0.05)
    assert L.ground_wind_q_Pa(h) == pytest.approx(3036, rel=0.002)


def test_winds_aloft_fit_reproduces_its_own_breakpoints():
    """The AMR 95% envelope fit (p.572): continuous, 76.2 m/s plateau, 24.384 m/s above 20 km."""
    assert L.winds_aloft_mps(0.0) == pytest.approx(9.144)
    assert L.winds_aloft_mps(9_600.0) == pytest.approx(76.2, rel=0.002)   # 6.9288*9.6 + 9.144 = 75.66
    assert L.winds_aloft_mps(12_000.0) == pytest.approx(76.2)
    assert L.winds_aloft_mps(19_999.0) == pytest.approx(76.2 - 8.9474 * 5.999, rel=1e-6)
    assert L.winds_aloft_mps(30_000.0) == pytest.approx(24.384)
    # the book's own fit is discontinuous at 20 km: the ramp ends at 22.5 m/s and the plateau above is
    # 24.384 m/s. It is reproduced as printed rather than smoothed.
    assert L.winds_aloft_mps(20_000.0) == pytest.approx(24.384)
    assert L.winds_aloft_mps(19_999.0) < L.winds_aloft_mps(20_000.0)


def test_gust_angle_of_attack():
    """alpha = atan(v_wind/v) (recipe step 4). The book's Saturn V case: 76.2 m/s against 504 m/s -> 8.6 deg."""
    a = math.atan(76.2 / 504.0)
    assert math.degrees(a) == pytest.approx(8.6, abs=0.05)
    assert math.degrees(L.gust_alpha_rad(504.0, 12_000.0)) == pytest.approx(8.6, abs=0.05)
    assert L.gust_alpha_rad(0.0, 10_000.0) == 0.0


# ====================================================================== panel geometry
def test_side_areas_and_centroids_match_book_table_93():
    """Table 9.3 (p.555) side areas, and its cone and cylinder centroids."""
    assert L.panel_side_area_m2(10.0, 4.0, 4.0) == pytest.approx(40.0)          # cylinder d*l
    assert L.panel_side_area_m2(10.0, 4.0, 0.0) == pytest.approx(20.0)          # cone d*l/2
    assert L.panel_side_area_m2(10.0, 6.0, 4.0) == pytest.approx(50.0)          # skirt (d1+d3)l/2
    assert L.panel_centroid_above_base(9.0, 4.0, 4.0) == pytest.approx(4.5)     # cylinder l/2
    assert L.panel_centroid_above_base(9.0, 4.0, 0.0) == pytest.approx(3.0)     # cone l/3


def test_the_skirt_centroid_of_book_table_93_is_wrong_and_this_module_is_not():
    """Table 9.3's skirt entry, l(d1/d3 + 2)/(3(d1/d3 + 1)) above the bottom, contradicts its own cone entry.

    As the forward diameter d1 goes to zero a skirt becomes a cone, so the two expressions must agree there.
    The book's gives 2l/3, its cone entry gives l/3, and l/3 is correct. The book's expression is the correct
    one with the two diameters interchanged, which puts the centroid on the wrong side of mid-span.
    """
    l, d_aft, d_fwd = 8.76, 6.60, 3.91                        # Saturn V LM adapter, Table 9.5
    book = l * ((d_fwd / d_aft) + 2) / (3 * ((d_fwd / d_aft) + 1))
    mine = L.panel_centroid_above_base(l, d_aft, d_fwd)
    assert book == pytest.approx(4.754, abs=0.002)
    assert mine == pytest.approx(4.006, abs=0.002)
    assert mine + book == pytest.approx(l, abs=0.01), "the two are mirror images about mid-span"
    # the cone limit, which is what proves which one is right
    assert L.panel_centroid_above_base(l, d_aft, 0.0) == pytest.approx(l / 3.0)
    assert l * (0 + 2) / (3 * (0 + 1)) == pytest.approx(2 * l / 3.0)
    # and the centroid must sit on the wide side of mid-span, because that is where the area is
    assert mine < l / 2.0 < book


def test_cross_area_change_sign_reverses_for_a_boattail():
    """A reverse taper's normal force changes sign (book p.579)."""
    assert L.panel_cross_area_change_m2(6.60, 3.91) > 0        # widens going aft: flare
    assert L.panel_cross_area_change_m2(3.91, 6.60) < 0        # narrows going aft: boattail
    assert L.panel_cross_area_change_m2(3.91, 0.0) == pytest.approx(math.pi * 3.91 ** 2 / 4)
    assert L.panel_cross_area_change_m2(4.0, 4.0) == pytest.approx(0.0)


def test_cylindrical_panels_carry_no_normal_force():
    p = L.Panel("barrel", "tank", 1, 0.0, 10.0, 4.0, 4.0)
    cna, src = L.cna_per_rad(p, 1.7)
    assert cna == 0.0 and "cylindrical" in src


def test_cna_override_is_applied_by_panel_name():
    p = L.Panel("Interstage 1/2", "interstage", 1, 0.0, 5.0, 5.0, 4.0)
    assert L.cna_per_rad(p, 1.7)[0] == pytest.approx(2.0)
    cna, src = L.cna_per_rad(p, 1.7, {"interstage": 1.3})
    assert cna == pytest.approx(1.3) and "override" in src


# ====================================================================== book Table 9.5: Saturn V ground wind
#   (name, elevation of top, length, aft diameter, forward diameter, book side area, book drag kN)
SAT5_GROUND = [
    ("Launch escape tower", 110.98, 9.15, 0.66, 0.66, 6.0, 14.1),
    ("Apollo capsule", 101.83, 2.84, 3.91, 0.00, 5.55, 12.7),
    ("Service module", 98.99, 4.52, 3.91, 3.91, 17.7, 39.8),
    ("LM adapter", 94.47, 8.76, 6.60, 3.91, 46.0, 100.7),
    ("S-IVB and IU", 85.71, 13.01, 6.60, 6.60, 85.9, 178.4),
    ("S-II/S-IVB skirt", 72.70, 5.79, 10.06, 6.60, 48.2, 95.3),
    ("S-II", 66.91, 19.28, 10.06, 10.06, 194.0, 353.9),
    ("S-II aft", 47.63, 4.97, 10.06, 10.06, 50.0, 83.0),
    ("S-IC LOx tank", 42.66, 16.57, 10.06, 10.06, 166.7, 248.0),
    ("S-IC RP-1 tank", 26.09, 13.89, 10.06, 10.06, 139.7, 164.5),
    ("S-IC aft and fairings", 12.20, 8.04, 12.49, 10.06, 107.8, 90.3),
]
SAT5_FAIRING_SIDE_AREA = 2 * 8.555         # engine fairing effective side area, Table 9.5's own footnote
SAT5_GROUND_SHEAR_KN = [0, 14.1, 26.8, 66.6, 167.3, 345.7, 440.9, 794.9, 877.8, 1125.8, 1290.3, 1380.6]
SAT5_GROUND_MOMENT_KNM = [0, 64.6, 116.7, 327.7, 1390, 4726, 7298, 19211, 23367, 39967, 56747, 67860]


def _sat5_ground_panels():
    out = []
    for name, z_top, ln, d_aft, d_fwd, _, _ in SAT5_GROUND:
        out.append(L.Panel(name, "x", 1, z_top - ln, z_top, d_aft, d_fwd))
    return out


def _sat5_ground_forces():
    out = []
    for p, row in zip(_sat5_ground_panels(), SAT5_GROUND):
        area = p.side_area_m2 + (SAT5_FAIRING_SIDE_AREA if "fairings" in p.name else 0.0)
        out.append((p, area, L.GROUND_WIND_CD * L.ground_wind_q_Pa(p.z_centroid) * area))
    return out


def test_saturn5_ground_wind_side_areas_and_drag_forces():
    """Every side area and every drag force of Table 9.5, from the wind profile and Cd = 0.77 alone."""
    for (p, area, force), row in zip(_sat5_ground_forces(), SAT5_GROUND):
        assert area == pytest.approx(row[5], rel=0.01), f"{p.name} side area"
        assert force / 1e3 == pytest.approx(row[6], rel=0.01), f"{p.name} drag force"


def test_saturn5_ground_wind_shear_matches_the_book():
    """The shear column of Table 9.5, to its printed precision."""
    pl = [L.PointLoad(p.z_centroid, 0.0, f, p.name, "") for p, _, f in _sat5_ground_forces()]
    stations = [(r[1], r[0]) for r in SAT5_GROUND] + [(4.16, "base")]
    got = L.march(pl, stations, 110.98)
    for s, want in zip(got, SAT5_GROUND_SHEAR_KN):
        assert s.shear_above_N / 1e3 == pytest.approx(want, abs=0.5, rel=0.003), f"shear at {s.z_m} m"


def test_saturn5_ground_wind_moment_agrees_once_the_book_centroid_is_used():
    """The moment column of Table 9.5 to 0.1% for the upper half of the vehicle, with the book's own centroid.

    This isolates the marching from the centroid question: substituting Table 9.3's skirt centroid reproduces
    the book's first four moments almost exactly, which shows the two calculations are the same calculation.
    Two of the book's lower rows cannot be reproduced by anyone, including the book: their moment increment
    exceeds (V_above + F_segment) x L, the largest value the printed shear and force columns allow, which is
    asserted below so the claim stands on arithmetic rather than assertion.
    """
    pl = []
    for p, _, f in _sat5_ground_forces():
        z = p.z_centroid
        if p.tapering and p.d_fwd > 0:                         # book Table 9.3 skirt entry
            x = p.d_fwd / p.d_aft
            z = p.z_aft + p.length * (x + 2) / (3 * (x + 1))
        pl.append(L.PointLoad(z, 0.0, f, p.name, ""))
    stations = [(r[1], r[0]) for r in SAT5_GROUND] + [(4.16, "base")]
    got = L.march(pl, stations, 110.98)
    for s, want in list(zip(got, SAT5_GROUND_MOMENT_KNM))[:6]:
        if want:
            assert s.moment_Nm / 1e3 == pytest.approx(want, rel=0.002), f"moment at {s.z_m} m"


def test_two_of_the_books_table_95_moment_rows_exceed_their_own_geometric_bound():
    """A point force inside a segment of length L cannot raise the moment by more than (V_above + F) L."""
    for i, (name, z_top, ln, _, _, _, force_kn) in enumerate(SAT5_GROUND):
        d_moment = SAT5_GROUND_MOMENT_KNM[i + 1] - SAT5_GROUND_MOMENT_KNM[i]
        bound = (SAT5_GROUND_SHEAR_KN[i] + force_kn) * ln
        if name in ("S-II/S-IVB skirt", "S-IC aft and fairings"):
            assert d_moment > bound, f"{name}: the book's {d_moment} kNm is meant to exceed {bound:.0f}"
        else:
            assert d_moment <= bound * 1.001, f"{name}: {d_moment} kNm vs bound {bound:.0f}"


def test_saturn5_ground_wind_total_moment_is_within_two_percent():
    """End to end: the base moment of Table 9.5 from this module's own centroids."""
    pl = [L.PointLoad(p.z_centroid, 0.0, f, p.name, "") for p, _, f in _sat5_ground_forces()]
    got = L.march(pl, [(4.16, "base")], 110.98)[0]
    assert got.moment_Nm / 1e3 == pytest.approx(67860, rel=0.02)


# ====================================================================== book Sec. 9.2: Saturn V at max-q
SAT5_Q = 35.2e3
SAT5_ALPHA = math.radians(8.6)
SAT5_MASS = 1_814_668.0
SAT5_THRUST = 38.55e6
#   (name, z_aft, z_fwd, d_aft, d_fwd, CNa/rad read off Figs. 9.38/9.39, book L, D, V, A in kN)
SAT5_FLIGHT = [
    ("Apollo capsule", 98.99, 101.83, 3.91, 0.00, 0.05 * 180 / math.pi, 181.6, 289.0, 222.8, 258.6),
    ("LM adapter", 85.71, 94.47, 6.60, 3.91, 1.55, 181.8, 547.0, 261.6, 513.7),
    ("S-II/S-IVB skirt", 66.91, 72.70, 10.06, 6.60, 1.30, 374.5, 1115.5, 537.1, 1047.0),
    ("S-IC aft skirt", 4.16, 12.20, 12.49, 10.06, 1.20, 272.7, 1060.0, 428.1, 1007.3),
]


def test_saturn5_maxq_air_loads_match_book_table_98():
    """Lift, drag and their rotation into body axes (Table 9.8), from the book's chart reads.

    Three of the four areas agree to better than 2.5%. The fourth, skirt 3, does not: Sec. 9.2.3 states
    CNa = 1.3/rad and then uses CN = 0.235, but 1.3/rad x 8.6 deg = 0.195. The 0.235 is skirt 2's CN value
    carried down a line. The assertion below holds this module to the product of the book's own stated CNa and
    alpha, and records what the book printed instead.
    """
    ca, sa = math.cos(SAT5_ALPHA), math.sin(SAT5_ALPHA)
    for name, za, zf, da, df, cna, Lb, Db, Vb, Ab in SAT5_FLIGHT:
        p = L.Panel(name, "x", 1, za, zf, da, df)
        dA = p.cross_area_change_m2
        lift = cna * SAT5_ALPHA * SAT5_Q * dA
        drag = L.FLIGHT_SEGMENT_CD * SAT5_Q * abs(dA)
        assert drag / 1e3 == pytest.approx(Db, rel=0.025), f"{name} drag"
        assert (drag * ca - lift * sa) / 1e3 == pytest.approx(Ab, rel=0.03), f"{name} body axial"
        if name == "S-II/S-IVB skirt":
            assert cna * SAT5_ALPHA == pytest.approx(0.195, abs=0.001)
            assert lift / 1e3 == pytest.approx(311.0, rel=0.01)
            assert Lb / (lift / 1e3) == pytest.approx(0.235 / 0.195, rel=0.02), "the book's slip, exactly"
        else:
            assert lift / 1e3 == pytest.approx(Lb, rel=0.025), f"{name} lift"
            assert (lift * ca + drag * sa) / 1e3 == pytest.approx(Vb, rel=0.025), f"{name} body shear"


def test_saturn5_maxq_area_centroids_match_the_three_the_book_names():
    """Table 9.11 names the three skirt centroids it used: 90.5, 70.0 and 8.3 m. Those are Table 9.3's
    mirrored values; this module's differ by exactly the mirror, which is asserted here so the 1% difference
    in the Saturn V moment comparison stays traceable to one cause."""
    for name, za, zf, da, df, *_ in SAT5_FLIGHT[1:]:
        p = L.Panel(name, "x", 1, za, zf, da, df)
        book = p.z_aft + p.length * ((p.d_fwd / p.d_aft) + 2) / (3 * ((p.d_fwd / p.d_aft) + 1))
        assert (p.z_centroid - p.z_aft) + (book - p.z_aft) == pytest.approx(p.length, abs=0.01)
    name, za, zf, da, df = SAT5_FLIGHT[0][:5]
    cap = L.Panel(name, "x", 1, za, zf, da, df)
    assert cap.z_centroid == pytest.approx(99.95, abs=0.02), "the book's cone centroid is correct"


def test_saturn5_gimbal_trim_and_lateral_load_factor():
    """Sec. 9.2.5: trim about the CM gives 1,161 kN of gimbal side force, F_lat 2,736 kN and n_z = 0.154."""
    z_cm, z_gimbal = 34.5, 5.47
    forces = [(223e3, 99.95), (262e3, 90.46), (537e3, 70.0), (554e3, 8.3)]
    f_gimbal = sum(f * (z - z_cm) for f, z in forces) / (z_cm - z_gimbal)
    assert f_gimbal / 1e3 == pytest.approx(1161, rel=0.005)
    f_lat = sum(f for f, _ in forces) + f_gimbal
    assert f_lat / 1e3 == pytest.approx(2736, rel=0.005)
    assert f_lat / (SAT5_MASS * L.G0) == pytest.approx(0.154, abs=0.001)
    assert math.degrees(math.asin(f_gimbal / 4 / (SAT5_THRUST / 5))) == pytest.approx(2.15, abs=0.05)


#   Table 9.11: (station label, elevation, mass in tonnes, axial air load kN, book running total kN)
SAT5_AXIAL = [
    ("Esc tower bottom", 111.0, 4.0, 0, 83), ("Module top", 101.8, 0.0, 295.7, 379),
    ("LM adapter top", 94.5, 28.8, 0, 972), ("Adapter AC", 90.5, 0.0, 514, 1486),
    ("S-IVB top", 85.7, 18.8, 0, 1873), ("S-IVB LH2 tank", 77.7, 19.8, 0, 2281),
    ("S-IVB LOx tank", 74.9, 99.3, 0, 4326), ("S-II upper skirt top", 72.7, 0.0, 0, 4326),
    ("Upper skirt AC", 70.0, 0.0, 1047, 5373), ("Skirt bottom", 66.9, 0.0, 0, 5373),
    ("S-II LH2 tank", 57.0, 71.7, 0, 6850), ("S-II LOx tank", 49.9, 408.2, 0, 15257),
    ("S-IC top", 42.7, 0.0, 0, 15257), ("S-IC LOx tank", 26.8, 711.3, 0, 29905),
    ("S-IC interstage", 26.1, 0.0, 0, 29905), ("S-IC RP-1 tank", 12.2, 443.1, 0, 39031),
    ("Bottom area AC", 8.3, 0.0, 987, 40018), ("F-1 engine gimbals", 5.5, 0.0, -38550, 1468),
]


def test_saturn5_maxq_axial_running_total_matches_book_table_911():
    """All eighteen rows of Table 9.11 through loads.march(), at the book's n_x = 2.10."""
    pl = [L.PointLoad(elev, (mT * 1e3 * 2.10 * L.G0) + air_kn * 1e3, 0.0, label, "")
          for label, elev, mT, air_kn, _ in SAT5_AXIAL]
    got = L.march(pl, [(r[1], r[0]) for r in SAT5_AXIAL], 111.0)
    for s, row in zip(got, SAT5_AXIAL):
        assert s.axial_below_N / 1e3 == pytest.approx(row[4], abs=3.0), f"{row[0]}"


def test_the_books_own_axial_load_factor_disagrees_with_its_own_air_load_total():
    """Sec. 9.2.2 computes n_x = 2.10 from a measured whole-vehicle axial force of 1,134 kN, while Table 9.11
    sums its own per-panel axial air loads to 2,843.7 kN - a factor of 2.5 on the same quantity, which is why
    the book's axial running total misses zero by 3.8%. This module scales the per-panel loads to the drag the
    trajectory flew with, so the two agree by construction."""
    measured = 0.263 * SAT5_Q * 122.5                         # CD q Sref, Sec. 9.2.2
    assert measured / 1e3 == pytest.approx(1134, rel=0.01)
    assert (SAT5_THRUST - measured) / (SAT5_MASS * L.G0) == pytest.approx(2.10, abs=0.01)
    panel_sum = sum(r[3] for r in SAT5_AXIAL if r[3] > 0)
    assert panel_sum == pytest.approx(2843.7, rel=0.001)
    assert panel_sum * 1e3 / measured == pytest.approx(2.5, abs=0.05)
    assert (SAT5_THRUST - panel_sum * 1e3) / (SAT5_MASS * L.G0) == pytest.approx(2.01, abs=0.01)


# ====================================================================== identities on the sized vehicle
def test_ground_case_closes_on_weight_and_total_wind_force():
    c = cases()["ground_wind"]
    assert abs(c.closure["axial_residual_N"]) < 1.0
    assert abs(c.closure["shear_residual_N"]) < 1.0
    assert c.closure["base_axial_N"] == pytest.approx(c.state["mass_kg"] * L.G0, rel=1e-9)


def test_ground_case_is_fully_loaded_at_one_g():
    r, _ = flown()
    c = cases()["ground_wind"]
    assert c.state["n_x"] == 1.0 and c.state["n_z"] == 0.0
    assert c.state["mass_kg"] == pytest.approx(r.glom_kg, rel=1e-9)


def test_ground_moment_and_shear_are_largest_at_the_hold_down_plane():
    """Book p.606: on the ground both peak at the restrained base, and both are zero at the top."""
    c = cases()["ground_wind"]
    base = c.stations[-1]
    assert abs(base.moment_Nm) == pytest.approx(abs(c.max_moment_Nm), rel=1e-9)
    assert abs(base.shear_below_N) == pytest.approx(abs(c.max_shear_N), rel=1e-9)
    assert c.stations[0].moment_Nm == pytest.approx(0.0, abs=1e-6)
    assert c.stations[0].shear_above_N == pytest.approx(0.0, abs=1e-6)


def test_flight_case_is_a_free_free_beam():
    """Book p.606: the airborne moment curve must be zero at both ends."""
    for key in ("max_q", "max_q_alpha"):
        c = cases().get(key)
        if c is None:
            continue
        assert abs(c.closure["moment_at_tip_Nm"]) < 1.0, key
        assert abs(c.closure["moment_at_base_Nm"]) < 1.0, key


def test_flight_axial_curve_closes_on_the_thrust():
    c = cases()["max_q"]
    assert abs(c.closure["axial_residual_N"]) < 1.0
    assert abs(c.closure["shear_residual_N"]) < 1.0
    assert c.state["n_x"] * c.state["mass_kg"] * L.G0 + c.state["axial_air_load_N"] == \
        pytest.approx(c.state["thrust_N"], rel=1e-9)


def test_flight_axial_air_load_is_the_drag_the_trajectory_flew():
    c = cases()["max_q"]
    assert c.state["axial_air_load_N"] == pytest.approx(c.state["drag_flown_N"], rel=1e-9)


def test_lateral_load_factor_follows_from_the_aero_and_gimbal_forces():
    c = cases()["max_q"]
    assert c.closure["lateral_force_N"] == pytest.approx(c.state["n_z"] * c.state["mass_kg"] * L.G0, rel=1e-9)


def test_flight_state_is_taken_at_max_q():
    r, t = flown()
    c = cases()["max_q"]
    assert c.state["q_Pa"] == pytest.approx(t.max_q_Pa, rel=1e-9)
    assert c.state["t_s"] == pytest.approx(t.max_q_t_s, rel=1e-9)
    assert c.state["h_m"] == pytest.approx(t.max_q_h_m, rel=1e-9)


def test_max_q_alpha_is_a_separate_and_here_worse_condition():
    """The book says which of max-q and max-q alpha governs cannot be known before a trajectory exists
    (p.572), so both are built. On this vehicle max-q alpha comes earlier and bends it harder."""
    cs = cases()
    if "max_q_alpha" not in cs:
        pytest.skip("max-q and max-q alpha fell on the same recorded point")
    q, qa = cs["max_q"], cs["max_q_alpha"]
    assert qa.state["q_alpha_Pa_deg"] > q.state["q_alpha_Pa_deg"]
    assert q.state["q_Pa"] >= qa.state["q_Pa"]
    assert cs["governing_flight_case"] == max((q, qa), key=lambda c: abs(c.max_moment_Nm)).name


def test_mass_at_max_q_is_the_flown_mass():
    """The ledger assembled for the load case must weigh what the trajectory says the vehicle weighed."""
    r, t = flown()
    c = cases()["max_q"]
    i = max(range(len(t.q_Pa)), key=lambda k: t.q_Pa[k])
    assert c.state["mass_kg"] == pytest.approx(t.m_kg[i], rel=0.001)


def test_gimbal_angle_is_within_a_plausible_actuator_travel():
    """Not a book limit, but a sanity bound: trimming max-q with more than ten degrees of engine deflection
    would mean the vehicle cannot be flown as drawn."""
    for key in ("max_q", "max_q_alpha"):
        c = cases().get(key)
        if c:
            assert c.state["gimbal_angle_deg"] < 10.0, f"{key}: {c.state['gimbal_angle_deg']:.1f} deg"


def test_axial_load_is_applied_at_the_supporting_structure_not_the_item_cm():
    """Book recipe step 10: apparent weights act at the lower junction of the support structure."""
    r, t = flown()
    panels = L.panels_from_geometry(r.geometry)
    tanks = [p for p in panels if p.kind == "tank"]
    assert tanks, "the default design has tanks"
    p = tanks[0]
    z_mid = 0.5 * (p.z_aft + p.z_fwd)
    assert L._axial_application_z(z_mid, panels) == pytest.approx(p.z_aft)


def test_stations_cover_the_whole_vehicle_and_are_ordered_from_the_nose():
    r, _ = flown()
    for c in (cases()["ground_wind"], cases()["max_q"]):
        zs = [s.z_m for s in c.stations]
        assert zs == sorted(zs, reverse=True)
        assert max(zs) == pytest.approx(r.geometry.total_length, abs=0.01)
        assert c.stations[0].station_m == pytest.approx(0.0, abs=0.01)


def test_a_reverse_taper_relieves_the_bending_moment():
    """Replacing a flare with a boattail of the same area change must flip the sign of its contribution."""
    flare = L.Panel("flare", "interstage", 1, 10.0, 15.0, 5.0, 3.0)
    boat = L.Panel("boattail", "interstage", 1, 10.0, 15.0, 3.0, 5.0)
    assert flare.cross_area_change_m2 == pytest.approx(-boat.cross_area_change_m2)


def test_loads_run_without_a_trajectory():
    """The two pad cases need no trajectory; standard_cases must still return them, and only them."""
    r, _ = flown()
    cs = L.standard_cases(r, None)
    assert {k for k, c in cs.items() if hasattr(c, "stations")} == {"ground_wind", "liftoff"}
    assert "governing_flight_case" not in cs
    assert cs["ground_wind"].max_axial_N > 0


def test_liftoff_is_the_pad_case_at_the_liftoff_thrust_to_weight():
    """Lift-off is the same wind with the vehicle accelerating, so bending is identical and axial scales."""
    r, _ = flown()
    cs = cases()
    g, lo = cs["ground_wind"], cs["liftoff"]
    assert lo.state["n_x"] == pytest.approx(r.liftoff_tw, rel=1e-9)
    assert lo.state["n_x"] > 1.0
    assert lo.max_moment_Nm == pytest.approx(g.max_moment_Nm, rel=1e-9), "same wind, same bending"
    assert lo.max_axial_N == pytest.approx(g.max_axial_N * r.liftoff_tw, rel=1e-9)
    assert abs(lo.closure["axial_residual_N"]) < 1.0


def test_maximum_axial_acceleration_is_its_own_case():
    """Axial acceleration peaks at the end of a burn, not at max-q, so it gets its own case. Whether it
    actually governs the axial load is a result, not an assumption: by then the stage is nearly empty, so
    there is little mass left above a station to compress it."""
    r, t = flown()
    cs = cases()
    if "max_axial" not in cs:
        pytest.skip("max axial acceleration fell on the same recorded point as max-q")
    c = cs["max_axial"]
    assert c.state["n_x"] > cs["max_q"].state["n_x"]
    assert c.state["n_x"] == pytest.approx(max(L.axial_load_factor(t, k) for k in range(len(t.t_s))), rel=1e-9)
    assert c.state["q_Pa"] < cs["max_q"].state["q_Pa"] / 10, "it happens well out of the atmosphere"
    assert abs(c.closure["axial_residual_N"]) < 1.0
    assert cs["governing_axial_case"] in [x.name for x in cs.values() if hasattr(x, "stations")]


def test_the_governing_cases_are_the_worst_of_those_computed():
    cs = cases()
    all_c = [c for c in cs.values() if hasattr(c, "stations")]
    assert cs["governing_axial_case"] == max(all_c, key=lambda c: abs(c.max_axial_N)).name
    assert cs["governing_bending_case"] == max(all_c, key=lambda c: abs(c.max_moment_Nm)).name


def test_pad_height_raises_the_wind_and_the_moment():
    r, _ = flown()
    low = L.ground_wind_case(r, pad_height_m=0.0)
    high = L.ground_wind_case(r, pad_height_m=12.0)
    assert high.max_moment_Nm > low.max_moment_Nm
    assert high.state["q_at_top_Pa"] > low.state["q_at_top_Pa"]
    assert high.closure["base_axial_N"] == pytest.approx(low.closure["base_axial_N"], rel=1e-9)


# ====================================================================== normal force and centre of pressure
def test_centre_of_pressure_is_the_normal_force_weighted_centroid():
    """Checked against the book's own Saturn V force list (Fig. 9.65, p.598), which gives four body-axis side
    forces and their elevations. Their weighted centroid is the vehicle's centre of pressure."""
    from launch_vehicle import aerodynamics as A
    forces = [(223e3, 99.95), (262e3, 90.46), (537e3, 70.0), (554e3, 8.3)]
    z_cp = sum(f * z for f, z in forces) / sum(f for f, _ in forces)
    assert z_cp == pytest.approx(55.95, abs=0.05)
    # the CM at max-q is 34.5 m, so the CP is forward of it: the vehicle is unstable, as the book says (p.357)
    assert z_cp > 34.5
    assert (34.5 - z_cp) / 10.06 == pytest.approx(-2.13, abs=0.02), "about two calibers unstable"


def test_the_saturn_v_fins_move_the_centre_of_pressure_aft():
    """Sec. 9.2.7 asks whether the Saturn V needed fins and answers that they "added stability during the
    period of max-q". With the same weighting, dropping the fins' 126 kN from the aft force must move the CP
    forward and make the vehicle more unstable - which is that claim, as a number."""
    base = [(223e3, 99.95), (262e3, 90.46), (537e3, 70.0)]
    with_fins = base + [(554e3, 8.3)]
    without = base + [(428e3, 8.3)]                    # Table 9.8: skirt 4 alone, fins were item 5
    cp = lambda fs: sum(f * z for f, z in fs) / sum(f for f, _ in fs)
    assert cp(without) > cp(with_fins), "removing the fins moves the CP forward"
    assert cp(with_fins) == pytest.approx(55.95, abs=0.05)
    assert cp(without) == pytest.approx(60.09, abs=0.05)
    assert (cp(without) - cp(with_fins)) / 10.06 == pytest.approx(0.41, abs=0.02), "0.4 calibers of stability"


def test_buildup_adds_its_panels_and_places_the_cp_between_them():
    from launch_vehicle import aerodynamics as A
    r, _ = flown()
    bu = A.normal_force_buildup(r.geometry, 1.6)
    assert bu.panels, "the default design has tapering panels"
    assert bu.cna_total_per_rad == pytest.approx(sum(p.cna_on_sref for p in bu.panels), rel=1e-12)
    zs = [p.z_cp_m for p in bu.panels]
    assert min(zs) <= bu.z_cp_m <= max(zs), "a weighted mean lies between its points"
    assert bu.station_cp_m == pytest.approx(r.geometry.total_length - bu.z_cp_m, rel=1e-12)


def test_a_reverse_taper_is_stabilising_in_front_of_the_cm_and_destabilising_behind_it():
    """Book p.579, stated exactly: "the reverse tapered part in front of the center of mass produces a
    stabilizing force. If it were located at the rear of the rocket, its force would be destabilizing."

    The pitching-moment slope is the thing to test, not the centre of pressure: a negative contribution makes
    the weighted centroid extrapolate outside the vehicle rather than move towards itself, so reading the CP
    alone here gives the wrong answer.
    """
    from launch_vehicle import aerodynamics as A
    from launch_vehicle.geometry import Segment

    class _G:
        total_length = 20.0
        max_diameter = 3.0
        booster_segments = []
        segments = []

    def seg(kind, name, z0, z1, d_bot, d_top):
        x = Segment(kind, name, z1 - z0, d_bot, d_top, 1)
        x.z0, x.z1 = z0, z1
        return x

    nose = seg("fairing_nose", "nose", 16.0, 20.0, 3.0, 0.0)
    body = seg("tank", "body", 2.0, 16.0, 3.0, 3.0)
    z_cm = 9.0
    plain = _G(); plain.segments = [nose, body]
    base = A.normal_force_buildup(plain, 2.0).cma_per_rad(z_cm)
    assert base > 0, "a nose cone alone, ahead of the CM, is destabilising"

    aft = _G(); aft.segments = [nose, body, seg("aft_skirt", "boattail aft", 0.0, 2.0, 2.0, 3.0)]
    fwd = _G(); fwd.segments = [nose, seg("tank", "upper", 12.0, 16.0, 3.0, 3.0),
                                seg("interstage", "boattail fwd", 10.0, 12.0, 2.0, 3.0),
                                seg("tank", "lower", 2.0, 10.0, 2.0, 2.0)]
    assert A.normal_force_buildup(aft, 2.0).cma_per_rad(z_cm) > base, "at the rear: destabilising"
    assert A.normal_force_buildup(fwd, 2.0).cma_per_rad(z_cm) < base, "in front of the CM: stabilising"


def test_the_centre_of_pressure_is_not_trusted_when_the_contributions_cancel():
    """With a reverse taper large enough to cancel the nose, the weighted centroid runs away and flips sign
    while the vehicle has not changed. The build-up says so rather than reporting a number that reads stable."""
    from launch_vehicle import aerodynamics as A
    from launch_vehicle.geometry import Segment

    class _G:
        total_length = 20.0
        max_diameter = 3.0
        booster_segments = []
        segments = []

    def seg(kind, name, z0, z1, d_bot, d_top):
        x = Segment(kind, name, z1 - z0, d_bot, d_top, 1)
        x.z0, x.z1 = z0, z1
        return x

    g = _G(); g.segments = [seg("fairing_nose", "nose", 16.0, 20.0, 3.0, 0.0),
                            seg("tank", "body", 4.0, 16.0, 3.0, 3.0),
                            seg("aft_skirt", "big boattail", 0.0, 4.0, 0.05, 3.0)]
    bu = A.normal_force_buildup(g, 2.0)
    assert abs(bu.cna_total_per_rad) < 1e-3
    assert not bu.cp_is_meaningful
    # but the moment slope is still perfectly well defined, and still says unstable
    assert bu.cma_per_rad(9.0) > 0


def test_static_margin_sign_convention():
    from launch_vehicle import aerodynamics as A
    r, _ = flown()
    bu = A.normal_force_buildup(r.geometry, 1.6)
    # CM far aft of the CP (low z) -> negative margin -> unstable
    assert bu.static_margin_calibers(bu.z_cp_m - 8.0, 4.0) == pytest.approx(-2.0, rel=1e-9)
    # CM forward of the CP -> positive -> stable
    assert bu.static_margin_calibers(bu.z_cp_m + 8.0, 4.0) == pytest.approx(+2.0, rel=1e-9)
    assert bu.static_margin_calibers(bu.z_cp_m, 4.0) == pytest.approx(0.0, abs=1e-12)


def test_the_default_vehicle_is_unstable_throughout_the_atmospheric_ascent():
    """Expected, not a defect: "Most space launchers have no fins and are unstable, so some sort of
    stabilizing system is required" (book p.357)."""
    from launch_vehicle import aerodynamics as A
    r, t = flown()
    d = A.cp_over_trajectory(r, t, every=4)
    assert d["rows"], "the atmospheric part of the ascent produced points"
    assert all(row["static_margin_cal"] < 0 for row in d["rows"])
    assert any("unstable" in n for n in d["notes"])
    # the CP does not move with mass, only the CM does, so the margin must vary over the flight
    assert len({round(row["z_cm_m"], 3) for row in d["rows"]}) > 1


def test_cp_over_trajectory_covers_only_the_atmospheric_part():
    from launch_vehicle import aerodynamics as A
    r, t = flown()
    d = A.cp_over_trajectory(r, t, every=4)
    q_max = max(t.q_Pa)
    assert all(row["q_Pa"] >= 0.01 * q_max for row in d["rows"])
    assert max(row["t_s"] for row in d["rows"]) < t.burnout_t_s
