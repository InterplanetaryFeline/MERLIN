"""Moments of inertia: shape formulas (book Tables 8.10/8.16/8.17), parallel-axis assembly (Eq. 8:37), book worked examples."""
import math
import numpy as np
import pytest
from launch_vehicle import inertia as inr
from launch_vehicle import mass_properties as mp

# Book Table 8.22 (p.533-534): (name, mass kg, location above reference m, J0_pitch kg m^2). Residual & loaded propellant rows have J0 = 0.
TABLE_8_22 = [
 ("PLF", 388, 41.22, 993), ("Payload", 10000, 42.97, 10833), ("PAF", 805, 39.59, 5501), ("Fwd skirt 2", 258, 38.19, 382),
 ("Avionics 2", 280, 38.19, 315), ("Wiring 2", 25, 36.43, 648), ("Ox tank 2", 429, 35.27, 1566), ("Ox insulation 2", 66, 35.27, 151),
 ("LOx residual 2", 784, 32.32, 0), ("Intertank 2", 360, 31.94, 652), ("Fuel tank 2", 185, 30.10, 368), ("Fuel residual 2", 245, 28.63, 0),
 ("Aft skirt 2", 258, 28.66, 382), ("Thrust structure 2", 118, 28.66, 0), ("Gimbals 2", 18, 28.15, 0), ("Engines 2", 574, 27.89, 0),
 ("Interstage", 590, 25.54, 1702), ("Avionics 1", 70, 25.05, 140), ("Wiring 1", 40, 13.82, 2515), ("Ox tank 1", 2012, 17.73, 23261),
 ("Ox insulation 1", 213, 17.73, 2458), ("Ox residual 1", 3665, 11.15, 0), ("Intertank 1", 640, 9.90, 2061), ("Fuel tank 1", 870, 5.99, 1998),
 ("Fuel residual 1", 1145, 4.58, 0), ("Aft skirt 1", 669, 2.00, 2228), ("Thrust structure 1", 1068, 2.00, 0), ("Gimbals 1", 162, 1.00, 0),
 ("Engines 1", 4257, 0.50, 0), ("RP-1 fuel 2", 12280, 30.10, 0), ("LOx 2", 39296, 35.27, 0), ("RP-1 fuel 1", 57616, 5.99, 0), ("LOx 1", 184373, 17.73, 0)]


def _items():
    return [mp.MassItem(n, 1, "g", m, z, "book Table 8.22", "dry", J0_pitch=j) for n, m, z, j in TABLE_8_22]


def test_assembly_reproduces_book_table_8_22_total_pitch_inertia():
    # Basis: Book Table 8.22 bottom line: total pitch MoI = 3.16E+07 kg m^2; sum of J0 = 58,154 (0.18 % of total); CM ~18.8 m above reference.
    items = _items()
    m, zc = mp.cm_of(items)
    assert zc == pytest.approx(18.8, abs=0.1)
    j = mp.inertia_of(items)
    assert j["J_pitch"] == pytest.approx(3.16e7, rel=0.01)
    assert sum(i.J0_pitch for i in items) == pytest.approx(58154, rel=0.02)
    assert sum(i.J0_pitch for i in items) / j["J_pitch"] == pytest.approx(0.0018, abs=0.0002)


def test_frustum_book_example_7_interstage():
    # Basis: Book Example 7 (p.530-531): m = 590 kg, R1 = 2 m, R2 = 1.5 m, h = 4 m -> Jpitch0 = 1,702 and Jroll = 1,842 kg m^2
    jr, jp = inr.frustum_shell(590.0, 1.5, 2.0, 4.0)
    assert jp == pytest.approx(1702.0, rel=2e-3)
    assert jr == pytest.approx(1842.0, rel=2e-3)
    # CM height of the frustum above its base = 1.90 m (book Example 4, p.522)
    assert mp._frustum_zc(4.0, 2.0, 1.5) == pytest.approx(1.90, abs=0.01)


def test_book_example_5_and_6_sphere_rod_dumbbell():
    # Sphere 2 kg r = 0.141 m on a 1 kg 1 m rod: Jpitch = 0.0992, Jroll = 0.0159;  dumbbell: 0.5913 and 0.0080 (book pp.527-529)
    sph = lambda m: inr.solid_sphere(m, 0.1)
    rod = inr.thin_bar(1.0, 1.0)
    jr, jp = inr.solid_sphere(2.0, 0.141)
    assert jp + rod[1] == pytest.approx(0.0992, abs=2e-4)
    assert jr == pytest.approx(0.0159, abs=1e-4)
    items = [mp.MassItem("s1", 1, "g", 1.0, 0.0, "", "dry", *sph(1.0)[::1][:0] or (sph(1.0)[0], sph(1.0)[1])),
             mp.MassItem("s2", 1, "g", 1.0, 1.0, "", "dry", sph(1.0)[0], sph(1.0)[1]),
             mp.MassItem("rod", 1, "g", 1.0, 0.5, "", "dry", rod[0], rod[1])]
    j = mp.inertia_of(items)
    assert j["J_pitch"] == pytest.approx(0.5913, abs=1e-3)
    assert j["J_roll"] == pytest.approx(0.0080, abs=1e-4)


def test_thin_shell_and_solid_formulas_analytic():
    assert inr.cyl_shell(10.0, 2.0, 6.0) == (pytest.approx(40.0), pytest.approx(10 * (2 + 3.0)))
    assert inr.cone_shell(9.0, 2.0, 3.0)[1] == pytest.approx(9 * (1.0 + 0.5))
    assert inr.ring(3.0, 2.0) == (pytest.approx(12.0), pytest.approx(6.0))
    assert inr.solid_cyl(8.0, 1.0, 3.0) == (pytest.approx(4.0), pytest.approx(8 * (0.25 + 0.75)))
    assert inr.frustum_shell(5.0, 2.0, 2.0, 3.0)[1] == pytest.approx(inr.cyl_shell(5.0, 2.0, 3.0)[1])   # r = R reduces to the cylinder


def test_numeric_shell_of_revolution_matches_analytic_hemisphere():
    # Basis: thin hemispherical shell: CM at R/2 above its base, Jroll = 2/3 m R^2, Jpitch(CM) = 5/12 m R^2.
    z = np.linspace(0, 1, 6001)
    zc, jr, jp = inr.shell_of_revolution(1.0, z, np.sqrt(1 - z ** 2))
    assert zc == pytest.approx(0.5, rel=1e-4)
    assert jr == pytest.approx(2 / 3, rel=1e-4)
    assert jp == pytest.approx(5 / 12, rel=1e-4)


def test_numeric_shell_cylinder_matches_table_8_10():
    z = np.linspace(0, 6.0, 4001)
    zc, jr, jp = inr.shell_of_revolution(10.0, z, np.full_like(z, 2.0))
    assert (zc, jr, jp) == (pytest.approx(3.0), pytest.approx(40.0, rel=1e-9), pytest.approx(50.0, rel=1e-6))


def test_numeric_solid_matches_sphere_and_cylinder():
    # sphere radius 1 as a solid of revolution: J = 2/5 m r^2 about any axis
    z = np.linspace(0, 2, 8001)
    A = math.pi * (1 - (z - 1) ** 2)
    m, zc, jr, jp = inr.solid_of_revolution(1000.0, z, A)
    assert m == pytest.approx(1000.0 * 4 / 3 * math.pi, rel=1e-5)
    assert jr == pytest.approx(0.4 * m, rel=1e-4) and jp == pytest.approx(0.4 * m, rel=1e-4)
    zc_ = np.linspace(0, 3, 2001)
    m, zc, jr, jp = inr.solid_of_revolution(100.0, zc_, np.full_like(zc_, math.pi * 4))      # r = 2, h = 3 solid cylinder
    assert jr == pytest.approx(m * 4 / 2, rel=1e-9) and jp == pytest.approx(m * (4 / 4 + 9 / 12), rel=1e-6)


def test_tank_liquid_inertia_sphere_case_from_tank_geometry():
    # A tank with h_cyl = 0 and hemispherical domes IS a sphere: full liquid J = 2/5 m R^2 (analytic).
    from launch_vehicle import tank_sizing as ts
    R = 1.5
    V = 4 / 3 * math.pi * R ** 3
    g = ts.size_tank_stack(2 * R, [dict(role="fuel", propellant="RP-1", V_int=V * (1 + 1e-9), V_liquid=V, m_liquid=1000.0),
                                   dict(role="oxidizer", propellant="LOX", V_int=V * (1 + 1e-9), V_liquid=V, m_liquid=1000.0)], 1.0, dict(fuel=0.0, oxidizer=0.0), "separate")[0]
    assert g.h_cyl == pytest.approx(0.0, abs=1e-6)
    zl, jr, jp = mp._liquid_inertia(g, V, 1000.0)
    assert zl == pytest.approx(R, rel=1e-3)
    assert jr == pytest.approx(0.4 * 1000.0 * R ** 2, rel=2e-3)
    assert jp == pytest.approx(0.4 * 1000.0 * R ** 2, rel=2e-3)


def test_vehicle_inertia_sanity_roll_much_smaller_than_pitch():
    # Book p.526: for long slender vehicles J_roll << J_pitch (sanity check). Also J0 terms are small versus parallel-axis terms (p.532).
    from helpers import default_result
    r = default_result()
    for e in r.mass_properties["events"][:4]:
        assert e["J_roll"] < 0.1 * e["J_pitch"]
        assert e["J_pitch"] >= e["J_pitch_book_form"]
    lift = r.mass_properties["events"][0]
    its = [i for i in r.ledger if i.kind in ("dry", "prop_loaded", "payload", "paf", "fairing")]
    # hardware self-inertia is small (book: 0.18-0.42 %); the liquid columns' own inertia is NOT negligible for 14 m tanks (~10 %),
    # which the book's point-mass propellant treatment (Table 8.22) neglects. Both values are reported.
    assert sum(i.J0_pitch for i in its if not i.kind.startswith("prop")) / lift["J_pitch"] < 0.02
    share = sum(i.J0_pitch for i in its if i.kind.startswith("prop")) / lift["J_pitch"]
    assert 0.02 < share < 0.2
    assert lift["J_pitch_book_form"] < lift["J_pitch"] < 1.2 * lift["J_pitch_book_form"]


def test_vehicle_inertia_independent_recomputation_and_parallel_axis_invariance():
    from helpers import default_result
    r = default_result()
    items = [i for i in r.ledger if i.kind in ("dry", "prop_loaded", "payload", "paf", "fairing")]
    m, zc = mp.cm_of(items)
    j = mp.inertia_of(items)
    manual = sum(i.J0_pitch + i.ext_pitch + i.mass_kg * (i.z_m - zc) ** 2 for i in items)
    assert j["J_pitch"] == pytest.approx(manual, rel=1e-12)
    # inertia about any other point exceeds the CM value by exactly M d^2 (parallel-axis theorem)
    d = 7.0
    about_other = sum(i.J0_pitch + i.ext_pitch + i.mass_kg * (i.z_m - (zc + d)) ** 2 for i in items)
    assert about_other == pytest.approx(j["J_pitch"] + m * d ** 2, rel=1e-9)
    assert r.mass_properties["events"][0]["J_pitch"] == pytest.approx(j["J_pitch"], rel=1e-9)


def test_engine_ring_adds_off_axis_roll_inertia():
    from helpers import default_result
    r = default_result()
    eng = [i for i in r.ledger if i.name == "Engines" and i.stage == 1][0]
    from launch_vehicle.propulsion import engine_ring_radius
    rho = engine_ring_radius(6, 1.2)
    assert eng.ext_roll == pytest.approx(eng.mass_kg * rho ** 2, rel=1e-12)
    assert eng.ext_pitch == pytest.approx(eng.mass_kg * rho ** 2 / 2, rel=1e-12)
    eng2 = [i for i in r.ledger if i.name == "Engines" and i.stage == 2][0]
    assert eng2.ext_roll == 0.0
