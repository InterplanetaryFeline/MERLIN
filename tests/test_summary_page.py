"""The report's front page: the summary a reader sees before deciding whether to read the other twenty sections.

What it has to get right is not prose but arithmetic agreement: every number on the front page is quoted from a
study reported in full further down, and a front page that disagrees with its own appendix is worse than no
front page at all. These tests check that agreement, that the drivers appear only when the study that produces
them was actually run, and that the warnings are not quietly dropped.
"""
import os
import re

import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import report as R
from launch_vehicle.main import _studies
from launch_vehicle.config_io import load_design
from launch_vehicle.convergence import size_vehicle


from scratch import Scratch

TMP = Scratch("lv_sum_")
_C = {}


def full():
    """A run with the driver studies, which is what the summary is designed around."""
    if "f" not in _C:
        spec = load_design(DESIGN, ASSUMP)
        res = size_vehicle(spec)
        ex = _studies(DESIGN, ASSUMP, spec, res, str(TMP / "studies"), {},
                      {"trajectory", "loads", "structure", "payload_env", "stability"}, 40, False)
        _C["f"] = (res, ex)
    return _C["f"]


def text_of(html):
    import html as _h
    return _h.unescape(re.sub(r"<[^>]+>", " ", html))


# --------------------------------------------------------------------------- the drivers table
def test_the_summary_quotes_the_same_bending_moment_the_loads_section_does():
    """The front page's headline driver must be the number the loads section reports, to the digit."""
    res, ex = full()
    cases = [c for k, c in ex["loads"].items() if hasattr(c, "stations") and c.stations]
    worst = max(cases, key=lambda c: max(abs(s.moment_Nm) for s in c.stations))
    wst = max(worst.stations, key=lambda s: abs(s.moment_Nm))
    txt = text_of(R._drivers(res, ex))
    assert f"{wst.moment_Nm / 1e3:,.0f} kN" in txt
    assert f"z = {wst.z_m:.1f} m" in txt
    assert worst.name in txt, "the governing case must be named, not just its number quoted"


def test_the_summary_quotes_the_structure_section_s_own_numbers():
    res, ex = full()
    thick = max(ex["structure"]["shells"], key=lambda sh: sh.t_required_m)
    txt = text_of(R._drivers(res, ex))
    assert f"{1e3 * thick.t_required_m:.2f} mm" in txt
    assert thick.governing_driver in txt, "the driver that sized the shell must be named"
    assert f"{ex['structure']['mass_ratio']:.2f}" in txt


def test_the_two_acceleration_figures_are_reconciled_not_left_to_collide():
    """The flown peak and the sizing loop's burnout figure differ, and the page must say why.

    The sizing loop quotes vacuum thrust over burnout mass; the trajectory quotes thrust less drag at the real
    altitude. Printing one of them beside an ACCEL warning quoting the other reads as a contradiction.
    """
    res, ex = full()
    txt = text_of(R._drivers(res, ex))
    assert "flown" in txt
    assert "vacuum thrust" in txt
    sized = max(s.accel_max_g for s in res.stages)
    assert f"{sized:.2f} g" in txt


def test_every_driver_row_points_at_the_section_that_derives_it():
    res, ex = full()
    html = R._drivers(res, ex)
    anchors = set(re.findall(r'href="#([a-z]+)"', html))
    assert anchors, "a driver with no link back to its working is an orphan number"
    for a in anchors:
        assert f"<h2 id={a}>" in R.build_html(res, {}, "", "", ex), f"driver links to #{a}, which does not exist"


def test_a_run_with_no_studies_says_so_instead_of_inventing_drivers():
    res, _ex = full()
    txt = text_of(R._drivers(res, {}))
    assert "No driver study was run" in txt
    assert "all-studies" in txt, "it should say how to get them"


def test_drivers_appear_only_when_their_study_ran():
    """A partial run must produce a shorter table, never a padded one."""
    res, ex = full()
    only_loads = R._drivers(res, {"loads": ex["loads"]})
    txt = text_of(only_loads)
    assert "Governing bending moment" in txt
    for absent in ("Thickest shell required", "Maximum dynamic pressure", "Payload design load factors"):
        assert absent not in txt, f"{absent!r} appeared without the study that produces it"


# ------------------------------------------------------------------------------- the warnings
def test_the_warnings_reach_the_front_page():
    res, ex = full()
    txt = text_of(R._summary(res, ex, {}))
    codes = {i.code for i in res.issues if i.level in ("ERROR", "WARNING")}
    assert codes, "the default design should raise at least one warning for this test to mean anything"
    for c in sorted(codes)[:8]:
        assert c in txt, f"warning {c} never reached the summary"


def test_a_clean_design_says_so_rather_than_showing_an_empty_box():
    res, ex = full()

    class _Clean:                       # a stand-in with no issues, to exercise the other branch
        def __getattr__(self, k):
            return getattr(res, k)
        issues = []
    txt = text_of(R._summary(_Clean(), ex, {}))
    assert "No errors or warnings" in txt
    assert "Nothing in the model flagged" in txt


def test_the_banner_severity_follows_the_worst_issue():
    res, ex = full()
    html = R._summary(res, ex, {})
    worst = "no" if any(i.level == "ERROR" for i in res.issues) else \
            ("warn" if any(i.level == "WARNING" for i in res.issues) else "ok")
    assert f'class="banner {worst}"' in html


# ------------------------------------------------------------------------------ the page itself
def test_the_summary_states_the_mission_and_the_vehicle_in_one_place():
    res, ex = full()
    txt = text_of(R._summary(res, ex, {}))
    assert f"{res.payload_mass_kg:,.0f} kg to a" in txt
    assert f"{res.glom_kg:,.0f} kg lift-off mass" in txt
    assert f"{res.geometry.total_length:.1f} m long" in txt
    assert f"{res.dv_required_mps:,.0f} m/s" in txt


def test_the_summary_sits_before_the_contents_and_the_body():
    """Front matter, not a section buried behind the table of contents."""
    res, ex = full()
    html = R.build_html(res, {}, "", "", ex)
    assert html.index("<h2>Summary</h2>") < html.index("<h2>Contents</h2>")
    assert html.index("<h2>Summary</h2>") < html.index("<h2 id=req>")


def test_the_summary_does_not_disturb_the_section_numbering():
    """It carries no `# ` marker, so _number_sections must neither number it nor complain about it."""
    res, ex = full()
    html = R.build_html(res, {}, "", "", ex)
    assert "<h2>Summary</h2>" in html, "the summary must not have been given a number"
    assert "<h2 id=req>1. " in html, "the first numbered section is still the mission requirement"
