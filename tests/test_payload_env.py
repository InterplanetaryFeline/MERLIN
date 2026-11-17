"""Payload environment: the quasi-static load factors a payload customer is given (book Chapter 11).

The book prints two real payload planners' guides, Ariane 5's (Table 11.3) and Atlas V's (Table 11.4), and
states the range a preliminary design should expect (p.691). Those are what there is to check against: the
shape of the table, the range the answer should land in, and - just as much - that the parts of a real guide
this tool cannot produce are declared rather than filled in.
"""
import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import payload_env as pe, trajectory as tj, loads as L

_C = {}


def env():
    if "e" not in _C:
        r = default_result()
        t = tj.fly_design(r, dt=0.4)
        _C["r"], _C["t"] = r, t
        _C["e"] = pe.build(r, t, L.standard_cases(r, t))
    return _C["r"], _C["t"], _C["e"]


# ====================================================================== the book's own tables
def test_the_books_two_real_guides_are_carried_whole():
    """Kept so the generated table can be shown beside real ones. Spot-checked against the printed values."""
    assert dict((e, (a, d, l)) for e, a, d, l in pe.ARIANE5_QSL)["Max-q"] == (-2.7, 0.5, 2.0)
    assert dict((e, (a, d, l)) for e, a, d, l in pe.ATLAS5_QSL)["BECO (max axial)"] == (5.5, 1.0, 0.5)
    assert len(pe.ARIANE5_QSL) == 5 and len(pe.ATLAS5_QSL) == 7


def test_the_real_guides_sit_inside_the_books_own_typical_range():
    """p.691: "Typical values are around 4-8 g0 axial and 1.5-3 g0 lateral". The Atlas V guide's worst axial
    and worst lateral must land there, which is the check that the range and the tables describe one thing."""
    worst_axial = max(a + d for _e, a, d, _l in pe.ATLAS5_QSL)
    worst_lateral = max(l for *_x, l in pe.ATLAS5_QSL)
    assert pe.TYPICAL_AXIAL_G[0] <= worst_axial <= pe.TYPICAL_AXIAL_G[1]
    assert pe.TYPICAL_LATERAL_G[0] <= worst_lateral <= pe.TYPICAL_LATERAL_G[1]


def test_ariane_5_longitudinal_statics_are_compressive_except_at_srb_jettison():
    """Table 11.3's signs: "the static axial values are all negative, indicating compression (which is to be
    expected for a rocket launching)", with the jettison row the max-tension case."""
    for event, static, _d, _l in pe.ARIANE5_QSL:
        if "jettison" in event:
            assert static > 0, "the max-tension case"
        else:
            assert static < 0, event


# ====================================================================== the generated table
def test_the_table_has_the_events_a_payload_guide_has():
    r, t, e = env()
    kinds = {row.kind for row in e.rows}
    assert "liftoff" in kinds and "max_q" in kinds and "burnout" in kinds
    assert all(row.axial_static_g >= 0 for row in e.rows)
    assert all(row.t_s >= 0 for row in e.rows)


def test_one_row_per_instant():
    """Burnout, jettison and the next stage's ignition are three names for one moment; the payload feels one
    event there, so the table must not list it three times."""
    r, t, e = env()
    times = [row.t_s for row in e.rows]
    assert len(times) == len(set(round(x, 1) for x in times))
    for i in range(len(times) - 1):
        assert times[i + 1] - times[i] > 0.5
    assert not any("pitch kick" in row.event.lower() for row in e.rows), "a guidance event, not a load event"


def test_the_axial_factor_comes_from_the_trajectory():
    r, t, e = env()
    from launch_vehicle.loads import axial_load_factor
    for row in e.rows:
        k = min(range(len(t.t_s)), key=lambda i: abs(t.t_s[i] - row.t_s))
        assert row.axial_static_g == pytest.approx(axial_load_factor(t, k), rel=1e-9)


def test_the_worst_axial_is_at_a_burnout_not_at_max_q():
    """Axial acceleration peaks when a stage is nearly empty, which is why a payload guide's largest axial
    number sits on a cutoff row - as both of the book's real tables show (BECO and MECO on Atlas V, SRB end
    of flight on Ariane 5)."""
    r, t, e = env()
    worst = max(e.rows, key=lambda x: x.axial_total_g)
    assert worst.kind == "burnout"
    assert e.governing_axial_event == worst.event


def test_the_design_factors_are_the_worst_sums_over_all_events():
    r, t, e = env()
    assert e.design_axial_g == pytest.approx(max(x.axial_total_g for x in e.rows), rel=1e-12)
    assert e.design_lateral_g == pytest.approx(max(x.lateral_total_g for x in e.rows), rel=1e-12)
    for x in e.rows:
        assert x.axial_total_g == pytest.approx(x.axial_static_g + x.axial_dynamic_g, rel=1e-12)


def test_this_vehicle_lands_in_the_books_typical_range():
    r, t, e = env()
    assert e.within_typical["axial"], f"{e.design_axial_g:.1f} g against {pe.TYPICAL_AXIAL_G}"
    assert e.within_typical["lateral"], f"{e.design_lateral_g:.1f} g against {pe.TYPICAL_LATERAL_G}"


def test_the_lateral_factor_comes_from_the_chapter_9_load_case_where_one_exists():
    r, t, e = env()
    cases = L.standard_cases(r, t)
    # both max-q and max-q alpha are max-q-family cases, and the worst of them is the one a payload guide
    # would quote - so the row must carry the larger, not whichever came first
    family = [c for c in cases.values() if hasattr(c, "stations") and "max-q" in c.name.lower()]
    assert len(family) >= 2, "the load module builds both max-q and max-q alpha"
    row = next(x for x in e.rows if x.kind == "max_q")
    assert row.lateral_static_g == pytest.approx(max(abs(c.state["n_z"]) for c in family), rel=1e-9)
    assert row.lateral_static_g > min(abs(c.state["n_z"]) for c in family)


# ====================================================================== what is declared missing
def test_the_dynamic_column_is_declared_a_stand_in():
    """It is not computed and must not look as though it were: a published QSL's dynamic half comes from a
    coupled-loads analysis this tool cannot do."""
    r, t, e = env()
    joined = " ".join(e.notes)
    assert "dynamic column is not computed" in joined.lower()
    assert "coupled-loads" in joined and "stand-ins, not predictions" in joined
    # and the increments really are the book's, not invented
    assert pe.DYNAMIC_AXIAL_G["liftoff"] == 2.0 and pe.DYNAMIC_LATERAL_G["liftoff"] == 2.0
    assert all(v in {a for _e, _s, a, _l in pe.ATLAS5_QSL} | {0.5, 0.6, 1.6, 2.0}
               for v in pe.DYNAMIC_LATERAL_G.values())


def test_acoustics_and_shock_are_declared_absent():
    r, t, e = env()
    joined = " ".join(e.notes)
    assert "No acoustic or shock specification" in joined
    assert "difficult to estimate" in joined
    assert not hasattr(e, "sound_pressure_level_dB")


def test_the_frequency_requirement_is_declared_unissuable():
    """Sec. 11.5.3's rule needs the vehicle's own structural modes, which this tool does not compute."""
    r, t, e = env()
    assert pe.MIN_FREQUENCY_RATIO == 2.0
    assert "cannot be issued" in " ".join(e.notes)


def test_without_a_trajectory_there_is_no_table_and_it_says_so():
    r, _t, _e = env()
    out = pe.build(r, None, None)
    assert out.rows == []
    assert "cannot be produced without one" in " ".join(out.notes)
    assert out.design_axial_g == 0.0
