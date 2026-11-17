"""The geometry drag build-up (M104): its relations against the sources they were read from, its behaviour
against what a drag coefficient has to do, and its measured error against published data.

The last group pins measurements, not hopes. Where the build-up is wrong the test says by how much and in which
direction, so that a change which moves the error - either way - has to be looked at. No fixtures and no
parametrize: tools/run_tests.py calls every test with no arguments.
"""
from __future__ import annotations
import math
import os
import sys

import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import aerodynamics as aero, drag_buildup as db, trajectory as tj, webgui
from launch_vehicle.atmosphere import us76
from launch_vehicle.config_io import load_design
from launch_vehicle.convergence import size_vehicle

sys.path.insert(0, os.path.join(ROOT, "tools"))
import validate_drag as vd                                   # noqa: E402

S = db.Section
_C = {}


def cylinder_with_cone(nose_over_d=2.0, length_over_d=10.0, d=1.0, exit_area=0.0, tip=0.0, shape="cone"):
    secs = [S("nose", nose_over_d * d, tip, d, shape), S("body", (length_over_d - nose_over_d) * d, d, d)]
    return db.Configuration("test", [db.Body("core", secs, 1, exit_area, True, tip)], 0.25 * math.pi * d * d)


def flown(path="config/default_design.yaml"):
    if path not in _C:
        res = size_vehicle(load_design(os.path.join(ROOT, path), ASSUMP), keep_history=False)
        _C[path] = (res, tj.fly_design(res))
    return _C[path]


# ------------------------------------------------------------------ the relations, against their sources
def test_base_drag_reproduces_fleemans_worked_example():
    """Fleeman p.23, Fig. 2.7: at Mach 2 the coasting base drag is 0.25/2 = 0.13, and with Ae = 11.22 in2 on
    Sref = 50.26 in2 the powered value is (1 - 0.223)(0.25/2) = 0.10."""
    assert db.base_cd(2.0) == pytest.approx(0.125, rel=1e-12)
    assert db.base_cd(0.5) == pytest.approx(0.12 + 0.13 * 0.25, rel=1e-12)
    sref = 50.26
    body = db.Body("m", [S("b", 100.0, 8.0, 8.0)], 1, 11.22, True)
    body.sections[0].d_fwd_m = body.sections[0].d_aft_m = math.sqrt(4 * sref / math.pi)
    on = db._body_pressure_terms(body, 2.0, True)["base"] / sref
    off = db._body_pressure_terms(body, 2.0, False)["base"] / sref
    assert off == pytest.approx(0.125, rel=1e-9)
    assert on == pytest.approx((1 - 11.22 / 50.26) * 0.125, rel=1e-9)
    assert round(on, 2) == 0.10, "the figure Fleeman prints"


def test_base_drag_is_continuous_at_mach_one():
    assert db.base_cd(1.0 - 1e-9) == pytest.approx(db.base_cd(1.0 + 1e-9), rel=1e-6)
    assert db.base_cd(1.0) == pytest.approx(0.25)


def test_the_cone_relation_meets_every_condition_its_source_states():
    for half_angle in (5.0, 12.5, 20.0, 30.0):
        s = math.sin(math.radians(half_angle))
        assert db.cone_pressure_cd(1.0, s) == pytest.approx(s, rel=1e-12), "sin(eps) at Mach 1"
        slope = (db.cone_pressure_cd(1.0 + 1e-6, s) - db.cone_pressure_cd(1.0, s)) / 1e-6
        assert slope == pytest.approx(4 / 2.4 * (1 - 0.5 * s), rel=1e-3), "the stated slope at Mach 1"
        below = (db.cone_pressure_cd(1.0, s) - db.cone_pressure_cd(1.0 - 1e-6, s)) / 1e-6
        assert below == pytest.approx(slope, rel=1e-3), "and the subsonic branch arrives with the same slope"
        m = db.CONE_SUPERSONIC_FROM_MACH
        assert db.cone_pressure_cd(m - 1e-9, s) == pytest.approx(db.cone_pressure_cd(m + 1e-9, s), rel=1e-6)
        assert db.cone_pressure_cd(2.0, s) == pytest.approx(2.1 * s * s + 0.5 * s / math.sqrt(3.0), rel=1e-12)
        assert db.cone_pressure_cd(0.0, s) == pytest.approx(0.8 * s * s, rel=1e-12)
        assert db.cone_pressure_cd(1e5, s) == pytest.approx(2.1 * s * s, rel=1e-3), "the high-Mach limit"


def test_an_ogive_differs_from_a_cone_only_below_mach_one():
    s = math.sin(math.radians(15.0))
    assert db.cone_pressure_cd(0.0, s, 0.0) == 0.0
    assert db.cone_pressure_cd(0.6, s, 0.0) < db.cone_pressure_cd(0.6, s)
    for m in (1.0, 1.2, 2.0, 4.0):
        assert db.cone_pressure_cd(m, s, 0.0) == pytest.approx(db.cone_pressure_cd(m, s), rel=1e-12)


def test_skin_friction_is_the_formula_and_its_roughness_limit():
    assert db.skin_friction_coefficient(1e7, 0.0, 0.0) == pytest.approx(1 / (1.5 * math.log(1e7) - 5.6) ** 2)
    assert db.skin_friction_coefficient(5e3, 0.0, 0.0) == pytest.approx(1.48e-2)
    rel = 50e-6 / 50.0
    re_crit = 51 * rel ** -1.039
    assert db.skin_friction_coefficient(10 * re_crit, 0.0, rel) == pytest.approx(0.032 * rel ** 0.2)
    assert db.skin_friction_coefficient(0.1 * re_crit, 0.0, rel) == pytest.approx(
        1 / (1.5 * math.log(0.1 * re_crit) - 5.6) ** 2)
    assert db.skin_friction_coefficient(1e8, 0.5, 0.0) == pytest.approx(
        db.skin_friction_coefficient(1e8, 0.0, 0.0) * (1 - 0.1 * 0.25))
    assert db.skin_friction_coefficient(1e8, 2.0, 0.0) == pytest.approx(
        db.skin_friction_coefficient(1e8, 0.0, 0.0) / (1 + 0.15 * 4) ** 0.58)


def test_friction_has_no_step_where_the_two_compressibility_corrections_meet():
    worst = max(abs(db.skin_friction_coefficient(1e8, m / 1000 + 0.001, 1e-6)
                    - db.skin_friction_coefficient(1e8, m / 1000, 1e-6)) for m in range(800, 1200))
    assert worst < 2e-6


def test_viscosity_and_reynolds_number_are_the_standard_ones():
    assert db.viscosity_Pa_s(288.15) == pytest.approx(1.789e-5, rel=2e-3)        # US76 sea-level value
    st = us76(0.0)
    assert db.reynolds_number(1.0, 0.0, 10.0) == pytest.approx(
        st.density_kg_m3 * st.sound_speed_mps * 10.0 / db.viscosity_Pa_s(st.temperature_K))
    assert db.reynolds_number(2.0, 200e3, 10.0) == 0.0, "no air, no Reynolds number"


def test_the_boattail_factor_follows_the_three_stated_ranges():
    assert db.boattail_factor(0.5, 2.0, 1.0) == 1.0
    assert db.boattail_factor(2.0, 2.0, 1.0) == pytest.approx(0.5)
    assert db.boattail_factor(4.0, 2.0, 1.0) == 0.0
    assert db.boattail_factor(1.0, 1.0, 2.0) == 0.0, "a flare is not a boattail"


def test_wetted_areas_are_the_closed_forms():
    assert S("c", 3.0, 2.0, 2.0).wetted_area_m2 == pytest.approx(math.pi * 2.0 * 3.0)
    assert S("n", 4.0, 0.0, 6.0).wetted_area_m2 == pytest.approx(math.pi * 3.0 * 5.0)      # 3-4-5 cone


# ------------------------------------------------------------------ what a drag coefficient has to do
def test_the_terms_add_up_and_the_fast_evaluation_matches_the_exact_one():
    c = cylinder_with_cone(exit_area=0.3)
    for m in (0.3, 0.95, 1.0, 1.17, 2.4, 6.0):
        for h in (0.0, 9_300.0, 31_000.0):
            b = c.breakdown(m, h, True)
            assert b["total"] == pytest.approx(b["friction"] + b["forebody"] + b["boattail"] + b["base"])
            assert c.cd(m, h, True) == pytest.approx(b["total"], rel=0.01)
            assert c.cd(m, h, False) == pytest.approx(c.breakdown(m, h, False)["total"], rel=0.01)


def test_cd_is_continuous_in_mach_and_peaks_just_above_one():
    c = cylinder_with_cone()
    cds = [c.breakdown(m / 100, db.representative_altitude_m(m / 100))["total"] for m in range(30, 600)]
    assert max(abs(b - a) for a, b in zip(cds, cds[1:])) < 0.02, "a step in Cd(M)"
    peak_mach = (30 + cds.index(max(cds))) / 100
    assert 1.0 <= peak_mach <= 1.4
    assert cds[-1] < 0.6 * max(cds), "and it decays well below the peak by Mach 6"


def test_shape_moves_drag_the_way_it_should():
    m, h = 1.5, 12_000.0
    blunt, slender = cylinder_with_cone(nose_over_d=0.8), cylinder_with_cone(nose_over_d=3.0)
    assert blunt.breakdown(m, h)["forebody"] > 3 * slender.breakdown(m, h)["forebody"]
    tipped = cylinder_with_cone(tip=0.3)
    assert tipped.breakdown(m, h)["forebody"] > cylinder_with_cone().breakdown(m, h)["forebody"]
    long_body = cylinder_with_cone(length_over_d=20.0)
    # twice the length is twice the wetted area, less a little: a longer body has a higher Reynolds number
    # and a finer shape, and both lower the coefficient
    ratio = long_body.breakdown(m, h)["friction"] / cylinder_with_cone().breakdown(m, h)["friction"]
    assert 1.6 < ratio < 2.0
    assert long_body.breakdown(m, h)["forebody"] == pytest.approx(cylinder_with_cone().breakdown(m, h)["forebody"])


def test_running_engines_fill_the_base_and_cannot_make_it_negative():
    c = cylinder_with_cone(exit_area=0.5)
    assert c.breakdown(2.0, 15e3, True)["base"] < c.breakdown(2.0, 15e3, False)["base"]
    huge = cylinder_with_cone(exit_area=50.0)
    assert huge.breakdown(2.0, 15e3, True)["base"] == 0.0


def test_a_flare_adds_pressure_drag_and_a_boattail_adds_base_drag():
    d = 1.0
    plain = [S("nose", 2.0, 0.0, d), S("body", 8.0, d, d)]
    flared = plain + [S("flare", 1.0, d, 1.5 * d), S("aft", 3.0, 1.5 * d, 1.5 * d)]
    hammer = [S("nose", 3.0, 0.0, 1.5 * d), S("fairing", 2.0, 1.5 * d, 1.5 * d), S("boattail", 0.3, 1.5 * d, d),
              S("body", 8.0, d, d)]
    sref = 0.25 * math.pi
    f = db.Configuration("f", [db.Body("c", flared)], sref).breakdown(2.0, 15e3)
    p = db.Configuration("p", [db.Body("c", plain)], sref).breakdown(2.0, 15e3)
    hm = db.Configuration("h", [db.Body("c", hammer)], sref).breakdown(2.0, 15e3)
    assert f["forebody"] > p["forebody"] and p["boattail"] == 0.0
    assert hm["boattail"] == pytest.approx(db.base_cd(2.0) * (1.5 ** 2 - 1.0), rel=1e-9)


# ------------------------------------------------------------------ bound to a sized design and flown
def test_the_default_drag_model_is_the_geometry_build_up():
    assert aero.model_from_config(None).kind == "geometry"
    assert aero.model_from_config({"drag_model": "book_titan2"}).kind == "book_titan2"
    assert default_spec().mission["aerodynamics"]["drag_model"] == "geometry"


def test_an_unbound_geometry_model_refuses_to_give_a_number():
    with pytest.raises(ValueError):
        aero.geometry_model().cd(1.0)


def test_the_options_are_read_and_nonsense_is_refused():
    o = db.BuildupOptions.from_config({"surface_roughness_m": 1e-5, "nose_shape": "Ogive", "nose_bluntness": 0.2})
    assert (o.roughness_m, o.nose_shape, o.nose_bluntness) == (1e-5, "ogive", 0.2)
    for bad in ({"nose_shape": "spike"}, {"nose_bluntness": 1.0}, {"surface_roughness_m": -1.0}):
        with pytest.raises(ValueError):
            db.BuildupOptions.from_config(bad)


def test_the_ascent_flies_one_shape_per_phase_on_one_reference_area():
    res, _ = flown()
    veh = tj.ascent_vehicle_from_result(res)
    assert veh.drag_by_burn and len(veh.drag_by_burn) == len(veh.burns)
    first, last = veh.drag_by_burn[0].buildup, veh.drag_by_burn[-1].buildup
    assert first.bodies[0].length_m > last.bodies[0].length_m, "the spent first stage has left the shape"
    assert first.reference_area_m2 == last.reference_area_m2 == pytest.approx(veh.reference_area_m2)
    assert first.reference_area_m2 == pytest.approx(0.25 * math.pi * res.geometry.max_diameter ** 2)


def test_strap_ons_add_drag_while_attached_and_stop_when_they_leave():
    res, _ = flown("examples/example_boosters.yaml")
    veh = tj.ascent_vehicle_from_result(res)
    counts = [sum(b.count for b in d.buildup.bodies if b.name == "strap-on") for d in veh.drag_by_burn]
    assert counts[0] == res.spec.boosters.n_total and counts[-1] == 0
    assert counts == sorted(counts, reverse=True), "strap-ons only ever leave"
    with_b = db.configuration_from_result(res, 1, res.spec.boosters.n_total)
    without = db.configuration_from_result(res, 1, 0)
    assert with_b.breakdown(1.5, 12e3)["total"] > 1.15 * without.breakdown(1.5, 12e3)["total"]


def test_the_flown_ascent_reports_its_drag_table_and_still_closes_its_loss_budget():
    _, tr = flown()
    assert tr.converged and abs(tr.closure_residual_mps) < 1e-3
    t = tr.drag_table
    assert t and len(t["rows"]) >= 10
    for r in t["rows"]:
        assert r["total"] == pytest.approx(r["friction"] + r["forebody"] + r["boattail"] + r["base"])
        assert r["total_power_off"] >= r["total"]
        assert r["book_titan2"] == pytest.approx(aero.cd_titan2(r["mach"]))
    assert any("geometry" in n.lower() for n in tr.notes)
    assert any("not modelled" in n for n in tr.notes), "the omissions travel with the result"


def test_the_book_curve_can_still_be_flown_and_gives_a_different_answer():
    res, tr = flown()
    old = tj.fly_design(res, drag=aero.book_titan2_model())
    assert old.converged and old.drag_table is None
    assert tr.drag_loss_mps != pytest.approx(old.drag_loss_mps, rel=0.05)


def test_the_gui_gets_the_drag_table_and_draws_it():
    """Rule 4: a capability the browser cannot show is not shipped."""
    _, tr = flown()
    s = webgui._study_summary({"trajectory": tr})["trajectory"]
    assert s["drag_rows"] and s["peak_cd"] > 0 and s["drag_shape"]
    with open(os.path.join(webgui.STATIC, "index.html"), encoding="utf-8") as fh:
        page = fh.read()
    assert "function dragTable(" in page and "ss.drag_rows" in page
    from launch_vehicle import gui_meta
    opts = [value for value, _label in gui_meta.STATIC_CHOICES["mission.aerodynamics.drag_model"]]
    assert opts[0] == "geometry" and "zoom_ld" not in opts
    assert "mission.aerodynamics.nose_shape" in gui_meta.STATIC_CHOICES


# ------------------------------------------------------------------ measured against published data
def curves():
    if "curves" not in _C:
        _C["curves"] = {c["name"]: c for c in vd.all_curves()}
    return _C["curves"]


def test_vanguard_is_reproduced_to_about_a_fifth():
    """Book Fig. 6.10. Mean absolute error 18 %, and high: the build-up starts its transonic rise too early."""
    c = curves()["Vanguard"]
    assert c["mean_abs_error_pct"] == pytest.approx(18.0, abs=3.0)
    assert c["bias_pct"] > 10.0, "the build-up over-predicts Vanguard; if that flips, find out why"
    assert c["model_peak"]["cd"] == pytest.approx(c["published_peak"]["cd"], rel=0.25)
    assert abs(c["model_peak"]["mach"] - c["published_peak"]["mach"]) <= 0.2
    worst = max(c["rows"], key=lambda r: abs(r["error_pct"]))
    assert 0.8 <= worst["mach"] <= 1.0, "the worst point is the transonic onset"


def test_the_books_titan_ii_curve_is_not_reproduced_and_the_miss_is_one_sided():
    """Book Fig. 6.13. The build-up is 35 % high on average and 89 % high at Mach 5, where the printed curve
    falls to 0.19 - less than the pressure drag of a blunted re-entry vehicle alone. docs/DRAG.md argues the
    curve is not that configuration; this test only holds the measurement still."""
    c = curves()["Titan II"]
    assert c["mean_abs_error_pct"] == pytest.approx(35.0, abs=5.0)
    assert c["bias_pct"] > 25.0
    assert c["rows"][-1]["error_pct"] > 60.0
    assert c["rows"][0]["error_pct"] == pytest.approx(0.0, abs=10.0), "subsonic, the two agree"


def test_the_measured_saturn_v_drag_force_is_matched_within_a_tenth():
    """Book p.588: 260 klbf at 750 psf, SA-503. On the 79.49 m2 core that is Cd 0.405."""
    p = vd.saturn5_point()
    assert p["measured_cd"] == pytest.approx(0.405, abs=0.002)
    assert p["error_pct"] == pytest.approx(-6.0, abs=4.0)
    assert p["error_pct"] < 0.0, "low, as it should be with the fins and engine fairings left out"


def test_the_published_curves_were_typed_in_as_read():
    assert vd.VANGUARD_FIG_6_10[1.2] == max(vd.VANGUARD_FIG_6_10.values()) == 0.450
    assert vd.SATURN5_AXIAL_FORCE_N == pytest.approx(1156.5e3, rel=1e-3)       # the book's own conversion
    assert vd.SATURN5_AXIAL_Q_PA == pytest.approx(35.91e3, rel=1e-3)
    assert vd.TABLE_3_4_DRAG_LOSS["Saturn V"] == 40.0
    cfg = vd.saturn5()
    assert cfg.bodies[0].length_m == pytest.approx(110.98 - 4.16, abs=0.01), "Table 9.5: tower top to S-IC base"


def test_the_apollo_11_engine_reproduces_two_figures_it_was_not_given():
    e = vd.apollo11_engine()
    assert e["thrust_at_maxq_altitude_N"] == pytest.approx(38.55e6, rel=0.01)
    assert e["exit_diameter_each_m"] == pytest.approx(3.7, rel=0.05)
    odd = vd.apollo11_engine("Example 3.7 lift-off thrust")
    assert odd["exit_diameter_each_m"] < 3.3, "which is why that thrust figure is only a variant"


def test_the_apollo_11_first_stage_is_flown_to_within_a_few_per_cent_up_to_max_q():
    """Flight: Mach 1 at 66.3 s; 504 m/s and 35.2 kPa at 83 s and 13,568 m. The altitude at 83 s is the one
    flight number used as an input."""
    if "ap" not in _C:
        _C["ap"] = vd.fly_apollo11(aero.geometry_model(vd.saturn5()))
    r, a = _C["ap"], vd.APOLLO11
    assert r["h_at_83s_m"] == pytest.approx(a["maxq_h_m"], abs=20.0)
    assert r["mach1_s"] == pytest.approx(a["mach1_s"], abs=3.0)
    assert r["mach1_s"] < a["mach1_s"], "early, because the book's lift-off mass method takes off too much"
    assert r["v_at_83s_mps"] == pytest.approx(a["maxq_v_mps"], rel=0.07)
    assert r["q_at_83s_Pa"] == pytest.approx(a["maxq_Pa"], rel=0.05)
    assert r["oeco_accel_g"] == pytest.approx(a["max_accel_g"], rel=0.03)
    assert 25.0 < r["drag_loss_mps"] < 46.0, "published 40 to 46 m/s for the whole ascent"
