"""Static stability and thrust vector control authority (book Chapter 12).

The book works one complete example - the Saturn V's time to double at max-q - and prints one complete table of
deflection requirements, so both are reproduced here. Two things in them do not add up, and are asserted as
such so that a future change cannot quietly "fix" the agreement for the wrong reason.
"""
import math
import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import control as C, aerodynamics as A, trajectory as tj

_C = {}

# Book Example 1, p.740: the Saturn V at max-q, from Table 9.10
SAT5_I_PITCH = 765.32e6          # kg m2 (765,320 T m2)
SAT5_M_AERO = 33.610e6           # N m, with fins
SAT5_M_AERO_NO_FINS = 37.06e6    # N m, the value the book's own 3.15 s implies (see the test below)


def assessed():
    if "a" not in _C:
        r = default_result()
        t = tj.fly_design(r, dt=0.4)
        cp = A.cp_over_trajectory(r, t, every=4)
        _C["r"], _C["t"], _C["cp"] = r, t, cp
        _C["a"] = C.assess(r, t, cp["rows"])
    return _C["r"], _C["t"], _C["a"]


# ====================================================================== Eq. 12.4, the book's own example
def test_saturn_v_time_to_double_at_max_q():
    """Book Example 1, p.740: 765,320 T m2 against 33,610 kN m gives 3.31 s, comfortably over the 0.5 s rule."""
    assert C.time_to_double_s(SAT5_I_PITCH, SAT5_M_AERO) == pytest.approx(3.31, abs=0.01)
    assert C.time_to_double_s(SAT5_I_PITCH, SAT5_M_AERO) > C.MIN_TIME_TO_DOUBLE_S


def test_the_books_no_fin_moment_must_be_meganewton_metres():
    """The same example continues: without fins "Maero = 37 kNm ... which yields a Tdouble = 3.15 s". 37 kN m
    would give 100 s, not 3.15. The value that produces the book's own 3.15 s is 37 MN m, so the printed unit
    is a slip of three orders of magnitude."""
    assert C.time_to_double_s(SAT5_I_PITCH, 37e3) > 90.0, "37 kN m gives nothing like 3.15 s"
    implied = SAT5_I_PITCH * math.log(2.0) ** 2 / 3.15 ** 2
    assert implied == pytest.approx(37.06e6, rel=0.01), "3.15 s implies 37 MN m"
    assert C.time_to_double_s(SAT5_I_PITCH, SAT5_M_AERO_NO_FINS) == pytest.approx(3.15, abs=0.01)


def test_removing_the_fins_leaves_less_time_not_more():
    """The book says of the finless case that "there would be slightly more time, about 160 ms, to initiate
    emergency procedures". Its own numbers say the opposite: 3.15 s is 160 ms LESS than 3.31 s. The sign
    matters, because Sec. 9.2.7 argues the fins existed precisely to buy the crew that time - which the
    numbers support and the sentence contradicts."""
    with_fins = C.time_to_double_s(SAT5_I_PITCH, SAT5_M_AERO)
    without = C.time_to_double_s(SAT5_I_PITCH, SAT5_M_AERO_NO_FINS)
    assert without < with_fins
    assert with_fins - without == pytest.approx(0.160, abs=0.01), "160 ms, in the fins' favour"


def test_a_stable_vehicle_has_no_time_to_double():
    """The expression has no meaning for a vehicle that does not diverge, and must not return a complex number
    or a misleadingly small one."""
    assert C.time_to_double_s(SAT5_I_PITCH, -1.0e6) == math.inf
    assert C.time_to_double_s(SAT5_I_PITCH, 0.0) == math.inf
    assert C.bandwidth_Hz(SAT5_I_PITCH, -1.0e6) == 0.0


def test_time_to_double_and_bandwidth_are_the_same_quantity():
    """Rule 9's f_b = sqrt(M_A/I_y)/2pi is the reciprocal time constant that Eq. 12.4 scales."""
    t2 = C.time_to_double_s(SAT5_I_PITCH, SAT5_M_AERO)
    fb = C.bandwidth_Hz(SAT5_I_PITCH, SAT5_M_AERO)
    assert t2 * fb == pytest.approx(math.log(2.0) / (2 * math.pi), rel=1e-12)


# ====================================================================== Table 12.4, pp.740-741
TABLE_12_4 = {"Apollo": ([1.35, 0.15, 0.25, 0.15, 0.50], 1.68, 2.40),
              "Voyager": ([2.30, 0.26, 0.25, 0.15, 0.50], 2.69, 3.46),
              "SSO PM": ([1.17, 0.13, 0.25, 0.15, 0.50], 1.49, 2.20)}


def test_table_12_4_simultaneous_totals_reproduce_exactly():
    """"If they all happened to be simultaneous, we would simply total the columns, and the deflection angles
    would be larger: 2.40, 3.46, and 2.20 deg" - which is the arithmetic sum of the printed rows, exactly. That
    is what shows the five rows are the whole table and nothing was dropped."""
    for name, (vals, _rss, total) in TABLE_12_4.items():
        assert sum(vals) == pytest.approx(total, abs=0.005), name


def test_table_12_4_printed_rss_totals_do_not_match_its_own_rows():
    """The book defines RSS in words - "square and add the components, and then take the square root" - and
    prints 1.68, 2.69 and 1.49. The root-sum-square of the five printed rows is 1.48, 2.39 and 1.31: every
    printed total is about 13 % high. Since the arithmetic totals match the rows exactly, the rows are complete
    and the discrepancy is in the totals. This module computes the RSS the book describes."""
    for name, (vals, printed, _total) in TABLE_12_4.items():
        rss = math.sqrt(sum(v * v for v in vals))
        assert printed > rss, name
        assert printed / rss == pytest.approx(1.13, abs=0.015), name


def test_deflection_budget_rsses_what_it_is_given():
    b = C.deflection_budget(1.35, {"wind gusts (3 sigma)": 0.15, "thrust misalignment (3 sigma)": 0.25,
                                   "thrust and weights (3 sigma)": 0.15, "pitch programme (maximum)": 0.50})
    assert b["rss_deg"] == pytest.approx(math.sqrt(1.35 ** 2 + 0.15 ** 2 + 0.25 ** 2 + 0.15 ** 2 + 0.50 ** 2))
    assert b["worst_case_total_deg"] == pytest.approx(2.40, abs=0.005)
    assert b["rss_deg"] < b["worst_case_total_deg"], "RSS is the point of RSSing"
    assert len(b["terms"]) == 5


def test_the_budget_defaults_are_the_books_apollo_column():
    assert C.TABLE_12_4_CONTRIBUTORS_DEG == {"wind gusts (3 sigma)": 0.15, "thrust misalignment (3 sigma)": 0.25,
                                             "thrust and weights (3 sigma)": 0.15,
                                             "pitch programme (maximum)": 0.50}
    assert sum(C.TABLE_12_4_CONTRIBUTORS_DEG.values()) + 1.35 == pytest.approx(2.40, abs=0.005)


# ====================================================================== control moment and trim
def test_control_moment_and_trim_deflection_are_inverses():
    """The gimbal angle that trims a moment must be the angle at which the control moment equals it."""
    T, arm = 5.0e6, 20.0
    d = C.trim_deflection_deg(3.0e6 * 20.0 / 20.0, T, arm)      # a moment of 3 MN m x arm... keep it explicit
    M = 3.0e6
    d = C.trim_deflection_deg(M, T, arm)
    assert C.control_moment_Nm(T, arm, d) == pytest.approx(M, rel=1e-9)


def test_only_the_gimballed_engines_count():
    """The Saturn V steered on four of its five F-1 engines (Sec. 9.2.7), so four fifths of the thrust."""
    full = C.control_moment_Nm(38.55e6, 29.0, 5.0, 1.0)
    four_of_five = C.control_moment_Nm(38.55e6, 29.0, 5.0, 0.8)
    assert four_of_five == pytest.approx(0.8 * full, rel=1e-12)
    assert C.trim_deflection_deg(1e6, 38.55e6, 29.0, 0.8) > C.trim_deflection_deg(1e6, 38.55e6, 29.0, 1.0)


def test_a_moment_beyond_the_actuators_reports_infinity_not_a_wrong_angle():
    assert C.trim_deflection_deg(1e12, 1e6, 10.0) == math.inf
    assert math.isnan(C.trim_deflection_deg(1e6, 0.0, 10.0))


# ====================================================================== on the sized vehicle
def test_all_four_checks_are_evaluated_with_their_sources():
    r, t, a = assessed()
    assert len(a.checks) == 4
    for c in a.checks:
        assert c["source"].startswith("book")
        assert c["limit"] and c["value"] and c["at"]
        assert isinstance(c["passed"], bool)


def test_the_checks_are_evaluated_at_the_worst_point_not_the_average():
    r, t, a = assessed()
    worst_ratio = min(p.controllability for p in a.points)
    worst_t2 = min(p.t_double_s for p in a.points)
    worst_trim = max(p.trim_deg for p in a.points)
    assert a.checks[0]["value"] == f"{worst_ratio:.2f}"
    assert a.checks[1]["value"] == f"{worst_t2:.2f} s"
    assert a.checks[2]["value"] == f"{worst_trim:.2f} deg"


def test_the_worst_point_is_near_max_q():
    """Aerodynamic moment scales with q, so the hardest instant to control is around the peak of it."""
    r, t, a = assessed()
    worst = min(a.points, key=lambda p: p.controllability)
    assert abs(worst.t_s - t.max_q_t_s) < 25.0, f"worst at {worst.t_s:.0f} s, max-q at {t.max_q_t_s:.0f} s"


def test_the_default_vehicle_is_controllable_by_the_books_three_rules():
    r, t, a = assessed()
    for c in a.checks[:3]:
        assert c["passed"], f"{c['rule']}: {c['value']} against {c['limit']}"


def test_the_aerodynamic_moment_follows_the_centre_of_pressure_offset():
    """M_A = CNa alpha q Sref (z_cp - z_cm): it must vanish when the CP sits on the CM and grow with the gap."""
    r, t, a = assessed()
    for p in a.points:
        assert (p.M_aero_Nm > 0) == (p.z_cp_m > p.z_cm_m)
        assert p.stable == (p.M_aero_Nm <= 0)


def test_the_moment_arm_grows_as_the_first_stage_drains():
    r, t, a = assessed()
    arms = [p.arm_m for p in a.points]
    assert arms[-1] > arms[0], "the CM moves forward, away from the gimbal plane"


def test_time_to_double_is_computed_from_this_vehicles_own_inertia():
    r, t, a = assessed()
    for p in a.points[:5]:
        assert p.t_double_s == pytest.approx(C.time_to_double_s(p.I_pitch_kg_m2, p.M_aero_Nm), rel=1e-12)
        assert p.I_pitch_kg_m2 > 0


def test_slosh_and_bending_are_declared_absent_rather_than_guessed():
    """The chapter declines slosh outright (p.778) and gives no bending or POGO equation, so the assessment
    must say so rather than producing a number with nothing behind it."""
    r, t, a = assessed()
    joined = " ".join(a.notes)
    assert "slosh" in joined.lower() and "beyond the scope of this book" in joined
    assert "bending" in joined.lower()
    assert not hasattr(a, "slosh_frequency_Hz")


def test_tighter_actuators_make_the_vehicle_less_controllable():
    r, t, _ = assessed()
    cp = _C["cp"]["rows"]
    wide = C.assess(r, t, cp, delta_max_deg=8.0)
    narrow = C.assess(r, t, cp, delta_max_deg=2.0)
    assert min(p.controllability for p in narrow.points) < min(p.controllability for p in wide.points)
    assert narrow.checks[3]["limit"] == "<= 2.0 deg"
