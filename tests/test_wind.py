"""Winds-aloft profiles read from file, and the load cases built from them.

The book's flight-load recipe says to use the launch site's own winds-aloft profile (Sec. 9.1.6.3 step 4,
p.573) and then prints one site's, the AMR 95 % envelope of Fig. 9.35. These tests cover the three things that
decide whether reading a site profile helps or quietly produces a wrong design load:

  * the built-in book curve still reproduces the book's own numbers, including its step at 20 km;
  * a STEADY profile and a GUST ENVELOPE are not interchangeable - a steady profile without a declared gust
    increment is refused rather than used as if it were already a worst case;
  * an ensemble of profiles picks the governing LOAD, not the biggest wind, and records which profile won.
"""
import math
import os

import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import loads as L, trajectory as tj, wind as W


from scratch import Scratch

TMP = Scratch("lv_wind_")
PROFILES = os.path.join(ROOT, "examples", "wind_profiles")

_C = {}


def flown():
    if "f" not in _C:
        r = default_result()
        _C["f"] = (r, tj.fly_design(r, dt=0.4))
    return _C["f"]


def write(name, text):
    p = TMP / name
    p.write_text(text)
    return str(p)


# ------------------------------------------------------------------ the book's own curve
def test_the_book_fit_reproduces_its_printed_breakpoints():
    """Fig. 9.35's SI fit: a ramp to 76.2 m/s at 9.6 km, flat to 14 km, down to 22.5, then a step to 24.384."""
    assert W.book_amr_95_mps(0.0) == pytest.approx(9.144)
    assert W.book_amr_95_mps(9600.0) == pytest.approx(76.2, abs=0.05)
    assert W.book_amr_95_mps(12000.0) == pytest.approx(76.2)
    assert W.book_amr_95_mps(19999.0) == pytest.approx(22.5, abs=0.05)
    assert W.book_amr_95_mps(20000.0) == pytest.approx(24.384)


def test_the_step_at_20_km_is_the_books_and_is_preserved_by_the_wrapper():
    """The fit jumps UP at 20 km. That is the book's discontinuity, not a transcription slip, and sampling the
    curve into a table must not smooth it away."""
    p = W.book_profile()
    assert p.gust_at(19999.0) < p.gust_at(20001.0)
    assert p.gust_at(20001.0) == pytest.approx(24.384, abs=0.01)
    assert p.kind == "gust_envelope" and "Fig. 9.35" in p.source


def test_the_default_design_still_flies_the_book_profile():
    ps = W.load(default_spec().mission.get("wind"))
    assert len(ps) == 1 and ps[0].name == W.BOOK_AMR_95


def test_no_wind_block_at_all_falls_back_to_the_book():
    assert W.load(None)[0].name == W.BOOK_AMR_95
    assert W.load({})[0].name == W.BOOK_AMR_95


# ------------------------------------------------------------------------- reading files
def test_a_csv_of_altitude_and_speed_is_read():
    p = write("a.csv", "altitude_m,speed_mps\n0,5\n5000,30\n10000,50\n20000,12\n")
    pr = W.read_csv(p)
    assert pr.altitudes_m == [0.0, 5000.0, 10000.0, 20000.0]
    assert pr.peak_mps == pytest.approx(50.0)
    assert pr.peak_altitude_m == pytest.approx(10000.0)


def test_units_in_the_column_name_are_converted():
    km_kt = W.read_csv(write("b.csv", "altitude_km,speed_kt\n0,10\n10,100\n"))
    assert km_kt.altitudes_m == [0.0, 10000.0]
    assert km_kt.speeds_mps[1] == pytest.approx(100 * 0.514444)
    ft = W.read_csv(write("c.csv", "height_ft,wind_speed_kmh\n0,18\n32808,180\n"))
    assert ft.altitudes_m[1] == pytest.approx(32808 * 0.3048)
    assert ft.speeds_mps[1] == pytest.approx(50.0)


def test_rows_out_of_order_are_sorted_not_rejected():
    pr = W.read_csv(write("d.csv", "altitude_m,speed_mps\n10000,50\n0,5\n5000,30\n"))
    assert pr.altitudes_m == sorted(pr.altitudes_m)
    assert pr.speeds_mps == [5.0, 30.0, 50.0]


def test_interpolation_is_linear_and_held_flat_outside_the_data():
    pr = W.read_csv(write("e.csv", "altitude_m,speed_mps\n1000,10\n3000,30\n"))
    assert pr.steady_at(2000.0) == pytest.approx(20.0)
    assert pr.steady_at(0.0) == pytest.approx(10.0), "below the data: held, never extrapolated to nonsense"
    assert pr.steady_at(99000.0) == pytest.approx(30.0), "above the data: held"


def test_malformed_files_are_refused_with_a_message_naming_the_problem():
    with pytest.raises(W.WindError, match="altitude"):
        W.read_csv(write("f.csv", "height_furlongs,speed_mps\n0,5\n1,9\n"))
    with pytest.raises(W.WindError, match="speed"):
        W.read_csv(write("g.csv", "altitude_m,velocity\n0,5\n1000,9\n"))
    with pytest.raises(W.WindError, match="two altitudes"):
        W.read_csv(write("h.csv", "altitude_m,speed_mps\n0,5\n"))
    with pytest.raises(W.WindError, match="duplicate"):
        W.read_csv(write("i.csv", "altitude_m,speed_mps\n0,5\n0,9\n"))
    with pytest.raises(W.WindError, match="negative"):
        W.read_csv(write("j.csv", "altitude_m,speed_mps\n0,5\n1000,-9\n"))


def test_a_missing_file_says_so_rather_than_silently_using_the_book():
    """Falling back to the book here would be the worst outcome: a design that believes it flew its own site."""
    with pytest.raises(W.WindError, match="not found"):
        W.load({"profile": "no_such_wind_file.csv"})


# ------------------------------------------------------- steady and envelope are different inputs
def test_a_steady_profile_without_a_gust_increment_is_refused():
    """This is the whole safety argument for the feature. A sounding is a mean wind; the gust rides on top.

    Taking a steady profile as if it were the book's envelope would drop the gust entirely and under-predict
    the governing flight load. The book gives no gust increment for an arbitrary site, so the module refuses
    rather than inventing one.
    """
    p = write("k.csv", "altitude_m,speed_mps\n0,5\n10000,40\n")
    with pytest.raises(W.WindError, match="gust"):
        W.read_csv(p, kind="steady")
    with pytest.raises(W.WindError, match="gust"):
        W.load({"profile": p, "kind": "steady"})


def test_the_gust_increment_rides_on_top_of_a_steady_profile_only():
    p = write("l.csv", "altitude_m,speed_mps\n0,5\n10000,40\n")
    steady = W.read_csv(p, kind="steady", gust_increment_mps=12.0)
    env = W.read_csv(p, kind="gust_envelope")
    assert steady.steady_at(10000.0) == pytest.approx(40.0)
    assert steady.gust_at(10000.0) == pytest.approx(52.0)
    assert env.gust_at(10000.0) == pytest.approx(40.0), "an envelope already contains its gust"
    assert steady.gust_at(10000.0) > env.gust_at(10000.0)


def test_an_unknown_kind_is_refused():
    with pytest.raises(W.WindError, match="kind"):
        W.WindProfile("x", [0.0, 1000.0], [5.0, 9.0], kind="breezy")


# --------------------------------------------------------------- the shipped example profiles
def test_the_shipped_examples_read_and_are_labelled_for_what_they_are():
    env = W.read_any(os.path.join(PROFILES, "book_amr_95_envelope.csv"))
    assert env.peak_mps == pytest.approx(76.2, abs=0.1)
    steady = W.read_any(os.path.join(PROFILES, "example_steady_sounding.csv"),
                        kind="steady", gust_increment_mps=9.0)
    assert steady.kind == "steady"
    assert steady.peak_mps == pytest.approx(53.0, abs=0.1)
    text = open(os.path.join(PROFILES, "example_steady_sounding.csv")).read()
    assert "NOT MEASURED DATA" in text, "a synthetic profile must say so on its face"


def test_the_written_template_round_trips_through_the_reader():
    """write_template_csv exists so a user starts from the book's curve; it must read back as itself."""
    p = W.write_template_csv(TMP / "t.csv")
    back = W.read_csv(p)
    book = W.book_profile()
    for h in (0.0, 5000.0, 9600.0, 12000.0, 18000.0, 25000.0):
        assert back.gust_at(h) == pytest.approx(book.gust_at(h), abs=0.05)


# ------------------------------------------------------------------- into the load cases
def test_a_profile_changes_the_flight_load_it_produces():
    res, traj = flown()
    calm = W.read_csv(write("m.csv", "altitude_m,speed_mps\n0,1\n30000,2\n"))
    book = W.book_profile()
    quiet = L.flight_case(res, traj, "max_q_alpha", profile=calm)
    loud = L.flight_case(res, traj, "max_q_alpha", profile=book)
    assert quiet.state["wind_mps"] < loud.state["wind_mps"]
    assert abs(quiet.max_moment_Nm) < abs(loud.max_moment_Nm), \
        "less wind must bend the vehicle less, or the profile is not reaching the load case"
    assert quiet.state["wind_profile"] == calm.name


def test_each_case_records_which_profile_produced_it():
    res, traj = flown()
    c = L.standard_cases(res, traj, wind_profiles=[W.book_profile()])
    st = c["max_q"].state
    assert st["wind_profile"] == W.BOOK_AMR_95 and st["wind_profile_kind"] == "gust_envelope"
    assert c["wind_profiles_considered"] == [W.BOOK_AMR_95]


def test_an_ensemble_keeps_the_worst_load_and_lists_everything_it_considered():
    """Several profiles are flown and the hardest-bending case is kept - not the fastest wind."""
    res, traj = flown()
    calm = W.read_csv(write("n.csv", "altitude_m,speed_mps\n0,1\n30000,2\n"))
    book = W.book_profile()
    both = L.standard_cases(res, traj, wind_profiles=[calm, book])
    only_calm = L.standard_cases(res, traj, wind_profiles=[calm])
    assert set(both["wind_profiles_considered"]) == {calm.name, book.name}
    assert abs(both["max_q"].max_moment_Nm) > abs(only_calm["max_q"].max_moment_Nm)
    assert both["max_q"].state["wind_profile"] == book.name, "the governing profile must be the one recorded"


def test_the_ensemble_result_does_not_depend_on_the_order_given():
    res, traj = flown()
    calm = W.read_csv(write("o.csv", "altitude_m,speed_mps\n0,1\n30000,2\n"))
    book = W.book_profile()
    a = L.standard_cases(res, traj, wind_profiles=[calm, book])["max_q"]
    b = L.standard_cases(res, traj, wind_profiles=[book, calm])["max_q"]
    assert a.max_moment_Nm == pytest.approx(b.max_moment_Nm)
    assert a.state["wind_profile"] == b.state["wind_profile"]


def test_no_profiles_given_behaves_exactly_as_before_the_feature_existed():
    """The default must be unchanged: every validated load number in the docs was produced without a profile."""
    res, traj = flown()
    old = L.standard_cases(res, traj, pad_height_m=18.0)
    new = L.standard_cases(res, traj, pad_height_m=18.0, wind_profiles=[W.book_profile()])
    for key in ("max_q", "max_q_alpha"):
        if key in old and key in new:
            assert old[key].max_moment_Nm == pytest.approx(new[key].max_moment_Nm, rel=1e-9)


def test_the_wind_chart_is_produced():
    from launch_vehicle import charts
    p = TMP / "wind.png"
    charts.draw_wind_profiles([W.book_profile()], str(p), None, title="t")
    assert p.exists() and p.stat().st_size > 5_000


# ------------------------------------------------------- a file that declares what it is
def test_a_file_can_declare_its_own_kind_and_gust_increment():
    """`kind` is one setting for the whole ensemble, so a file has to be able to override it.

    Otherwise a steady sounding listed beside an envelope is read as an envelope, its gust is counted once
    instead of twice, and the design load comes out low - the exact mistake this module exists to prevent.
    """
    p = write("declared.csv",
              "# kind: steady\n"
              "# gust_increment_mps: 9.0\n"
              "# source: a synthetic example\n"
              "altitude_m,speed_mps\n0,5\n11000,40\n30000,10\n")
    prof = W.read_csv(p)                                  # note: no kind argument given
    assert prof.kind == "steady"
    assert prof.gust_increment_mps == pytest.approx(9.0)
    assert prof.steady_at(11000.0) == pytest.approx(40.0)
    assert prof.gust_at(11000.0) == pytest.approx(49.0), "the increment must ride on top of the steady wind"
    assert "synthetic example" in prof.source


def test_the_file_beats_the_block_for_kind():
    p = write("declared2.csv", "# kind: steady\n# gust_increment_mps: 4.0\n"
                               "altitude_m,speed_mps\n0,5\n10000,30\n")
    prof = W.read_csv(p, kind="gust_envelope", gust_increment_mps=0.0)
    assert prof.kind == "steady" and prof.gust_increment_mps == pytest.approx(4.0)
    assert prof.gust_at(10000.0) == pytest.approx(34.0)


def test_a_nonsense_declared_kind_is_refused():
    p = write("bad_kind.csv", "# kind: breezy\naltitude_m,speed_mps\n0,5\n10000,30\n")
    with pytest.raises(W.WindError, match="breezy"):
        W.read_csv(p)
    p2 = write("bad_inc.csv", "# kind: steady\n# gust_increment_mps: quite a lot\n"
                              "altitude_m,speed_mps\n0,5\n10000,30\n")
    with pytest.raises(W.WindError, match="not a number"):
        W.read_csv(p2)


def test_the_shipped_steady_example_declares_itself():
    """The example exists to exercise the steady path, so it must not read as an envelope."""
    prof = W.read_csv(os.path.join(PROFILES, "example_steady_sounding.csv"))
    assert prof.kind == "steady"
    assert prof.gust_increment_mps > 0.0
    assert prof.gust_at(11000.0) > prof.steady_at(11000.0)


def test_an_ensemble_can_mix_kinds():
    profs = W.load({"profile": [os.path.join(PROFILES, "book_amr_95_envelope.csv"),
                                os.path.join(PROFILES, "example_steady_sounding.csv")]}, root=".")
    kinds = {p.kind for p in profs}
    assert kinds == {"gust_envelope", "steady"}, f"kinds collapsed to {kinds}"
    text = W.summarise(profs)
    assert "steady" in text and "gust_envelope" in text
