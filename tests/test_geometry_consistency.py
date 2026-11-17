"""Geometry <-> drawing <-> ledger consistency."""
import pytest
from helpers import default_result, ROOT, ASSUMP


def test_segments_are_contiguous_and_sum_to_total_length():
    r = default_result()
    g = r.geometry
    segs = g.segments
    for a, b in zip(segs[:-1], segs[1:]):
        if a.stage != 0 or b.stage != 0:
            assert b.z0 == pytest.approx(a.z1, abs=1e-12)
    protrusion = r.spec.stages[0].engine.length_m * (1 - r.spec.stages[0].engine.embed_fraction)
    # the PAF sits inside the fairing cylinder, so it is not an additional stack element
    assert g.total_length == pytest.approx(protrusion + sum(s.length for s in segs), rel=1e-12)
    for s in segs:
        assert s.z1 - s.z0 == pytest.approx(s.length, abs=1e-12)


def test_stage_length_and_diameter_consistency():
    r = default_result()
    for sr in r.stages:
        segs = r.geometry.stage_segments(sr.index)
        assert sr.length_m == pytest.approx(sum(s.length for s in segs), rel=1e-12)
        assert r.geometry.stage_top_z[sr.index] - r.geometry.stage_base_z[sr.index] == pytest.approx(sr.length_m, rel=1e-12)
    # interstage 1-2 is a frustum from D1 to D2 and long enough for the stage-2 nozzle + clearance
    inter = [s for s in r.geometry.segments if s.kind == "interstage"][0]
    assert inter.d_bot == 4.0 and inter.d_top == 3.0
    e2 = r.spec.stages[1].engine
    assert inter.length >= e2.length_m * (1 - e2.embed_fraction) + 0.3 - 1e-12


def test_tank_segment_lengths_come_from_tank_geometry():
    r = default_result()
    for s in r.geometry.segments:
        if s.kind == "tank":
            assert s.length == pytest.approx(s.tank.L_ext, rel=1e-14)
            assert s.d_bot == pytest.approx(s.tank.D_ext, rel=1e-14)


def test_fairing_dimensions_follow_inputs():
    r = default_result()
    f = r.spec.fairing
    cyl = [s for s in r.geometry.segments if s.kind == "fairing_cyl"][0]
    nose = [s for s in r.geometry.segments if s.kind == "fairing_nose"][0]
    paf = r.geometry.paf_z1 - r.geometry.paf_z0
    assert paf == pytest.approx(0.25 * r.spec.stages[-1].diameter_m, rel=1e-12)
    assert cyl.length == pytest.approx(paf + f.envelope_length_m + f.axial_clearance_m, rel=1e-12)
    assert nose.length == pytest.approx(f.nose_length_over_D * f.diameter_m, rel=1e-12)


def test_ledger_positions_inside_vehicle_envelope():
    r = default_result()
    L = r.geometry.total_length
    for i in r.ledger:
        assert 0.0 <= i.z_m <= L, i.name


def test_schematic_is_generated_from_geometry_not_hardcoded():
    # Basis: the highest drawn polygon vertex must equal the engine-computed overall length; changing an input changes the drawing.
    from launch_vehicle import schematic_2d as sch
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    captured = {}
    orig = sch._save
    sch._save = lambda fig, png, pdf: captured.setdefault("fig", fig)
    try:
        r1 = default_result()
        sch.draw_vehicle(r1)
        fig1 = captured.pop("fig")
        top1 = max(v[1] for p in fig1.axes[0].patches if isinstance(p, Polygon) for v in p.get_xy())
        r2 = default_result({"stages.0.diameter_m": 4.4})
        sch.draw_vehicle(r2)
        fig2 = captured.pop("fig")
        top2 = max(v[1] for p in fig2.axes[0].patches if isinstance(p, Polygon) for v in p.get_xy())
    finally:
        sch._save = orig
        plt.close("all")
    assert top1 == pytest.approx(r1.geometry.total_length, abs=1e-9)
    assert top2 == pytest.approx(r2.geometry.total_length, abs=1e-9)
    assert abs(top1 - top2) > 1.0


def test_schematic_dimensions_the_outer_diameter_of_every_stage():
    """v0.3: each stage, the fairing (and any strap-on) must carry a proper diameter dimension, drawn small
    enough that it cannot cover the vehicle (the v0.2 drawing used a large bold banner instead)."""
    from launch_vehicle import schematic_2d as sch
    r = default_result()
    fig = sch.draw_vehicle(r)
    texts = [t for ax in fig.axes for t in ax.texts]
    labels = [t.get_text() for t in texts]
    for st in r.spec.stages:
        want = f"Ø {st.diameter_m:.2f} m"
        assert any(want == l for l in labels), (want, labels)
    assert any(f"Ø {r.spec.fairing.diameter_m:.2f} m" == l for l in labels)
    dims = [t for t in texts if t.get_text().startswith("Ø")]
    assert dims and all(t.get_fontsize() <= 8.0 for t in dims)
    assert all(t.get_fontweight() in ("normal", 400) for t in dims)
    # the vehicle outline, the length chain and the diameter dimensions all come from the same geometry
    L = [t.get_text() for t in texts]
    assert any(f"{r.geometry.total_length:.2f} m" in x for x in L)
    for sr in r.stages:
        assert any(f"{sr.length_m:.2f} m" in x for x in L)


def test_schematic_of_a_boosted_vehicle_shows_the_span_and_booster_diameter():
    from launch_vehicle import schematic_2d as sch
    from launch_vehicle.config_io import load_design
    from launch_vehicle.convergence import size_vehicle
    import os
    r = size_vehicle(load_design(os.path.join(ROOT, "examples", "example_boosters.yaml"), ASSUMP))
    fig = sch.draw_vehicle(r)
    labels = [t.get_text() for ax in fig.axes for t in ax.texts]
    assert any(f"Ø {r.boosters.diameter_m:.2f} m" == l for l in labels)
    assert any(f"span {r.geometry.max_span_m:.2f} m" == l for l in labels)
    assert any(f"{r.boosters.n_total} x strap-on" == l for l in labels)


# --------------------------------------------------------------- paged (report) drawings
def test_column_count_maximises_the_drawn_scale():
    """A slender vehicle is split over several z-windows so it fills a page; the chosen count must be the one
    that actually draws the vehicle largest, not merely a count that fits."""
    from launch_vehicle.schematic_2d import _n_columns
    def scale(k, x, z, a=0.8):
        return min(a / (k * x), k / z)
    for x_span, z_span in ((8.8, 58.7), (12.0, 40.2), (6.0, 20.0), (10.0, 10.0), (4.0, 300.0)):
        n = _n_columns(x_span, z_span, 0.8)
        assert 1 <= n <= 4
        best = max(scale(k, x_span, z_span) for k in range(1, 5))
        assert scale(n, x_span, z_span) == pytest.approx(best, rel=1e-12)
    # a square drawing needs no splitting; a very slender one does
    assert _n_columns(10.0, 10.0, 0.8) == 1
    assert _n_columns(8.8, 58.7, 0.8) >= 2


def test_segment_labels_drop_the_stage_number():
    from launch_vehicle.schematic_2d import _seg_label
    assert _seg_label("Forward skirt 1", 1) == "Forward skirt"
    assert _seg_label("Interstage 1-2", 1) == "Interstage"
    assert _seg_label("Oxidizer tank 2", 2) == "Oxidizer tank"
    assert _seg_label("Aft skirt / engine section 1", 1) == "Aft skirt / engine section"
    assert _seg_label("Fuel tank 1", 2) == "Fuel tank 1"          # not this stage's number: left alone


def test_paged_drawings_render_for_every_example():
    """Solid, boosted and three-stage vehicles all have to survive the paged layout."""
    import os, tempfile
    import matplotlib
    matplotlib.use("Agg")
    from launch_vehicle.schematic_2d import draw_vehicle_page, draw_stage_page
    from launch_vehicle.config_io import load_design
    from launch_vehicle.convergence import size_vehicle
    for name in ("example_solid_smallsat.yaml", "example_boosters.yaml", "example_3stage_leo.yaml"):
        res = size_vehicle(load_design(os.path.join(ROOT, "examples", name), ASSUMP))
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "v.png")
            draw_vehicle_page(res, p, None)
            assert os.path.getsize(p) > 20_000, name
            q = os.path.join(d, "s.png")
            draw_stage_page(res, 1, q, None)
            assert os.path.getsize(q) > 20_000, name


def test_the_report_drawing_is_one_continuous_vehicle_not_a_split_view():
    """The report drawing must be a single column: one rocket, filling the page height, never cut into
    side-by-side z-windows. The split layout is still reachable with max_columns > 1, and it must actually
    produce a wider figure when asked - that is how we know the two paths are really different."""
    import os, tempfile
    import matplotlib
    matplotlib.use("Agg")
    from launch_vehicle.schematic_2d import draw_vehicle_page
    res = default_result()
    with tempfile.TemporaryDirectory() as d:
        one = draw_vehicle_page(res, os.path.join(d, "one.png"), None)
        w1, h1 = one.get_size_inches()
        split = draw_vehicle_page(res, os.path.join(d, "split.png"), None, max_columns=4)
        w4, h4 = split.get_size_inches()
    # a single continuous column of a 13:1 vehicle is tall and narrow; the split view is several times wider
    assert w1 / h1 < 0.45, f"the default drawing is {w1 / h1:.2f} wide for its height - it was split"
    assert w4 > 1.6 * w1, "max_columns had no effect, so the split path is gone rather than merely unused"


def test_a_single_column_drawing_has_no_break_marks():
    """A break symbol means the view was cut; there must be none when the vehicle is drawn whole."""
    import matplotlib
    matplotlib.use("Agg")
    from launch_vehicle.schematic_2d import draw_vehicle_page
    fig = draw_vehicle_page(default_result(), None, None)
    texts = [t.get_text() for ax in fig.axes for t in ax.texts]
    assert not any("break" in t for t in texts), texts
    assert len(fig.axes) == 1, "one continuous view means exactly one axes"
