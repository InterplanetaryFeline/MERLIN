"""One axial coordinate everywhere a figure is drawn: z upward from the first-stage nozzle exit plane.

The drawings, the mass ledger, the centre-of-mass plot and the CAD export have always used z from the base.
The loads, stability and structure charts used the book's station instead - distance from the NOSE - so the
three diagrams you most want to read against the vehicle were plotted on the opposite convention to the
vehicle, and to each other's neighbours in the same report. The book's own load figures use elevation from the
base as well (Fig. 9.26, p.566), so the station convention was not even buying agreement with the source.

`station_m` is still carried in the data, because the book's tables are written in it and the report and
workbook print both columns. What these tests pin is that nothing is PLOTTED in it any more, and that the two
coordinates remain exact complements of each other so either can be read off the other.
"""
import math

import matplotlib
import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import charts, loads as L, trajectory as tj

_C = {}


def flown():
    if "f" not in _C:
        res = default_result()
        tr = tj.fly_design(res, dt=0.5)
        _C["f"] = (res, tr, L.standard_cases(res, tr, pad_height_m=18.0))
    return _C["f"]


def line_xy(ax):
    return [(ln.get_xdata(), ln.get_ydata()) for ln in ax.get_lines() if len(ln.get_xdata())]


# ------------------------------------------------------------------ the two coordinates stay complements
def test_station_and_z_are_exact_complements():
    """station = total_length - z, every station of every case. The report prints both columns."""
    res, _tr, cases = flown()
    total = res.geometry.total_length
    checked = 0
    for case in cases.values():
        for st in getattr(case, "stations", []) or []:
            assert st.station_m == pytest.approx(total - st.z_m, abs=1e-9)
            checked += 1
    assert checked > 10


def test_the_nose_is_station_zero_and_the_base_is_z_zero():
    res, _tr, cases = flown()
    for case in cases.values():
        sts = getattr(case, "stations", []) or []
        if not sts:
            continue
        assert min(s.station_m for s in sts) == pytest.approx(0.0, abs=0.01), "station 0 is the nose"
        assert max(s.z_m for s in sts) == pytest.approx(res.geometry.total_length, abs=0.01)


# --------------------------------------------------------------------------- nothing is plotted in station
def test_the_loads_diagram_is_plotted_against_z():
    res, _tr, cases = flown()
    fig = charts.draw_loads(cases, None, None, res=res)
    total = res.geometry.total_length
    panels = [a for a in fig.axes if a.get_xlabel()]
    assert len(panels) == 3, "axial, shear and bending"
    zs = sorted({round(s.z_m, 6) for s in cases["ground_wind"].stations})
    for ax in panels:
        ys = [y for _x, yd in line_xy(ax) for y in yd if not math.isnan(y)]
        assert ys, f"no data on {ax.get_xlabel()}"
        assert max(ys) <= total + 1e-6 and min(ys) >= -1e-6
        assert "z from" in ax.get_ylabel() or ax.get_ylabel() == "", ax.get_ylabel()
    # the bending panel's stations must BE the z values, not their mirror image
    moment_ax = panels[2]
    drawn = sorted({round(y, 6) for _x, yd in line_xy(moment_ax) for y in yd})
    assert set(zs) <= set(drawn), "the bending moment is not plotted at the station z values"
    mirrored = sorted({round(total - z, 6) for z in zs})
    assert set(mirrored) - set(drawn), "the curve looks mirrored: plotted from the nose, not from the base"
    matplotlib.pyplot.close(fig)


def test_the_stability_plot_rises_with_the_vehicle_and_is_not_inverted():
    """Nose at the top used to need an inverted axis. With z from the base it is the natural direction."""
    from launch_vehicle import aerodynamics as aero
    res, tr, _cases = flown()
    cp = aero.cp_over_trajectory(res, tr, every=24)
    fig = charts.draw_stability(cp, None, None)
    ax = fig.axes[0]
    lo, hi = ax.get_ylim()
    assert lo < hi, "the station axis is still inverted, which z from the base does not need"
    assert "z from" in ax.get_ylabel()
    rows = cp["rows"]
    drawn = {round(y, 6) for _x, yd in line_xy(ax) for y in yd}
    assert {round(r["z_cp_m"], 6) for r in rows} <= drawn, "the CP is not plotted in z"
    matplotlib.pyplot.close(fig)


def test_the_structure_plot_puts_each_shell_at_its_own_z():
    from launch_vehicle import structure as st
    res, tr, cases = flown()
    out = st.analyse(res, cases)
    fig = charts.draw_structure(out, res.geometry, None, None)
    ax = fig.axes[0]
    assert "z from" in ax.get_xlabel()
    by_name = {s.name: s for s in res.geometry.segments}
    shell = next(s for s in out["shells"] if s.name in by_name)
    seg = by_name[shell.name]
    xs = [x for coll in ax.collections for x in coll.get_paths()[0].vertices[:, 0]] if ax.collections else []
    assert xs, "nothing drawn"
    assert min(xs) >= -1e-6 and max(xs) <= res.geometry.total_length + 1e-6
    assert any(abs(x - seg.z0) < 1e-6 or abs(x - seg.z1) < 1e-6 for x in xs), \
        "a shell is not drawn at its own z extent"
    matplotlib.pyplot.close(fig)


def test_no_axial_figure_is_labelled_from_the_nose_any_more():
    """A label sweep, so a future chart cannot quietly reintroduce the other convention."""
    from launch_vehicle import aerodynamics as aero
    res, tr, cases = flown()
    figs = [charts.draw_loads(cases, None, None, res=res),
            charts.draw_stability(aero.cp_over_trajectory(res, tr, every=24), None, None)]
    for fig in figs:
        for ax in fig.axes:
            for lab in (ax.get_xlabel(), ax.get_ylabel()):
                assert "from the nose" not in lab.lower(), lab
        matplotlib.pyplot.close(fig)


# ------------------------------------------------------------------------- the vehicle beside the loads
def test_the_vehicle_strip_covers_the_whole_vehicle_on_the_shared_axis():
    res, _tr, _cases = flown()
    fig, ax = matplotlib.pyplot.subplots()
    charts.vehicle_strip(ax, res)
    lo, hi = ax.get_ylim()
    assert lo <= 0.0 and hi >= res.geometry.total_length
    half = 0.5 * max(res.geometry.max_span_m, res.geometry.max_diameter)
    x0, x1 = ax.get_xlim()
    assert x0 <= -half and x1 >= half, "the strip crops the vehicle laterally"
    assert ax.patches, "the strip drew no vehicle"
    matplotlib.pyplot.close(fig)


def test_the_loads_diagram_draws_the_vehicle_only_when_given_the_result():
    res, _tr, cases = flown()
    with_v = charts.draw_loads(cases, None, None, res=res)
    without = charts.draw_loads(cases, None, None)
    assert len(with_v.axes) == len(without.axes) + 1
    assert sum(len(a.patches) for a in with_v.axes) > sum(len(a.patches) for a in without.axes)
    for fig in (with_v, without):
        matplotlib.pyplot.close(fig)


def test_the_stage_joints_marked_are_real_joints_inside_the_vehicle():
    res, _tr, _cases = flown()
    joints = charts._stage_joints(res)
    assert joints, "a two-stage vehicle has at least one joint and a fairing base"
    zs = [z for z, _ in joints]
    assert all(0.0 < z < res.geometry.total_length for z in zs)
    assert res.geometry.fairing_base_z in zs
    for k in list(res.geometry.stage_top_z)[:-1]:
        assert res.geometry.stage_top_z[k] in zs
    # the top of the LAST stage is the same plane as the fairing base, so it must appear once, not twice
    assert len(zs) == len(set(zs)), f"a joint is drawn twice: {sorted(zs)}"
    assert len(zs) == len(res.stages), "one joint per stage boundary plus the fairing base"


def test_the_governing_station_marked_is_the_worst_bending_moment():
    res, _tr, cases = flown()
    fig = charts.draw_loads(cases, None, None, res=res)
    worst = max((s for c in cases.values() for s in getattr(c, "stations", []) or []),
                key=lambda s: abs(s.moment_Nm))
    texts = " ".join(t.get_text() for a in fig.axes for t in a.texts)
    assert f"z = {worst.z_m:.1f} m" in texts, texts[:200]
    matplotlib.pyplot.close(fig)
