"""Engine-cluster reliability and the engine-out case (R24, book Sec. 15.2.6).

The book works two examples and prints their answers, so this implementation has an acceptance test that
does not depend on anything in this project: 3-of-5 at R = 0.95 gives 99.88%, and 7-of-9 gives 99.164%.
The second being worse than the first is the whole point of the pair and is asserted as such.
"""
import math

import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import reliability as rel


# ------------------------------------------------------------------ the book's own worked examples
def test_the_books_first_worked_example_is_reproduced():
    """Sec. 15.2.6.1: a 5-engine rocket needing 3, each 95% reliable, is 99.88% reliable."""
    r = rel.k_of_n(5, 3, 0.95)
    assert r == pytest.approx(0.9988, abs=5e-5), f"{r:.5f}"


def test_the_books_second_worked_example_is_reproduced():
    """Sec. 15.2.6.2: 7-of-9 at the same per-engine reliability, 99.164%."""
    r = rel.k_of_n(9, 7, 0.95)
    assert r == pytest.approx(0.99164, abs=5e-6), f"{r:.6f}"


def test_more_engines_is_not_automatically_more_reliable():
    """The reason the book prints the two examples together, asserted so it cannot be lost."""
    five = rel.k_of_n(5, 3, 0.95)
    nine = rel.k_of_n(9, 7, 0.95)
    assert nine < five, "9 engines tolerating 2 failures is WORSE than 5 tolerating 2"
    # and the general shape: with a fixed number of tolerated failures, adding engines eventually hurts
    sweep = rel.more_engines_sweep(0.95, n_max=10, tolerate=1)
    best = max(sweep, key=lambda s: s["r_cluster"])
    assert best["n"] < 10, "a cluster tolerating one failure should not improve without limit"
    assert sweep[-1]["r_cluster"] < sweep[1]["r_cluster"], "ten engines is worse than two, one-out tolerant"


def test_all_must_work_degrades_with_every_engine_added():
    prev = 1.1
    for n in range(1, 10):
        r = rel.k_of_n(n, n, 0.99)
        assert r < prev, "with no redundancy, each extra engine can only make things worse"
        prev = r
    assert rel.k_of_n(9, 9, 0.99) == pytest.approx(0.99 ** 9, rel=1e-12)


# -------------------------------------------------------------------------------- the binomial itself
def test_the_sum_is_a_real_binomial_tail():
    for n, r in ((5, 0.9), (9, 0.95), (3, 0.5)):
        total = sum(math.comb(n, j) * r ** j * (1 - r) ** (n - j) for j in range(0, n + 1))
        assert total == pytest.approx(1.0, rel=1e-12), "the full sum must be 1"
        assert rel.k_of_n(n, 0, r) == pytest.approx(1.0, rel=1e-12), "0-of-n always succeeds"
    assert rel.k_of_n(4, 1, 0.5) == pytest.approx(1 - 0.5 ** 4, rel=1e-12), "1-of-n is 1 - all fail"


def test_nonsense_clusters_are_refused():
    for bad in (lambda: rel.k_of_n(0, 0, 0.9), lambda: rel.k_of_n(5, 6, 0.9),
                lambda: rel.k_of_n(5, -1, 0.9), lambda: rel.k_of_n(5, 3, 1.5)):
        try:
            bad()
            raise AssertionError("should have been refused")
        except ValueError:
            pass


# ------------------------------------------------------- the flight record, and what it really shows
def test_table_15_4_is_transcribed_as_counts_and_the_percentages_follow():
    recs = {r["engine"]: r for r in rel.records_table()}
    assert set(recs) == {"Merlin 1D", "Rutherford", "RS-25", "RD-180", "RD-107/108", "F-1"}
    # the book prints the reliability column; it must fall out of the counts rather than be stored twice
    for name, printed in (("Merlin 1D", 0.99922), ("RS-25", 0.9975), ("RD-180", 0.9883),
                          ("RD-107/108", 0.99989)):
        assert recs[name]["point"] == pytest.approx(printed, abs=1e-4), name
    assert recs["Rutherford"]["point"] == 1.0 and recs["F-1"]["point"] == 1.0


def test_a_zero_failure_record_is_not_reported_as_certainty():
    """The book prints 100% for 0/207 and 0/65. No finite record shows a reliability of 1."""
    recs = {r["engine"]: r for r in rel.records_table(confidence=0.95)}
    for name in ("Rutherford", "F-1"):
        r = recs[name]
        assert r["zero_failures"] and r["point"] == 1.0
        assert r["lower_bound"] < 1.0, f"{name}: a bound of 1.0 would be the same mistake"
    # 0 failures in n uses: the exact bound is (1 - c)^(1/n)
    assert recs["Rutherford"]["lower_bound"] == pytest.approx(0.05 ** (1 / 207), rel=1e-9)
    assert recs["F-1"]["lower_bound"] == pytest.approx(0.05 ** (1 / 65), rel=1e-9)
    # and the shorter record supports a weaker claim
    assert recs["F-1"]["lower_bound"] < recs["Rutherford"]["lower_bound"]


def test_the_confidence_bound_is_below_the_point_estimate_and_tightens_with_evidence():
    assert rel.lower_confidence_bound(1, 86) < 1 - 1 / 86
    assert rel.lower_confidence_bound(1, 9500) > rel.lower_confidence_bound(1, 86), \
        "9,500 uses must support a stronger claim than 86"
    assert rel.lower_confidence_bound(0, 1000, 0.95) > rel.lower_confidence_bound(0, 10, 0.95)
    assert rel.lower_confidence_bound(0, 100, 0.99) < rel.lower_confidence_bound(0, 100, 0.90), \
        "demanding more confidence must give a weaker bound"


def test_a_bad_flight_record_is_refused():
    for bad in (lambda: rel.lower_confidence_bound(2, 1), lambda: rel.lower_confidence_bound(-1, 10),
                lambda: rel.lower_confidence_bound(1, 0), lambda: rel.lower_confidence_bound(1, 10, 1.0)):
        try:
            bad()
            raise AssertionError("should have been refused")
        except ValueError:
            pass


# --------------------------------------------------------------------------- against a real vehicle
def test_the_default_vehicle_is_analysed_stage_by_stage():
    res = default_result()
    a = rel.analyse(res)
    assert a["r_engine"] == rel.EXAMPLE_R
    assert "book" in a["source"], "an assumed reliability must say where the number came from"
    assert a["stages"], "the default design has liquid stages and should be analysed"
    for s in a["stages"]:
        assert s["n_engines"] >= 1
        assert 0.0 < s["r_cluster"] <= 1.0
        assert s["tw_nominal"] > 0
    assert 0.0 < a["propulsion_reliability"] <= 1.0
    assert "common-cause" in a["independence_caveat"]


def test_the_six_engine_first_stage_can_actually_lose_one():
    """The default design's comment claims six engines give one-engine-out margin. Check it."""
    res = default_result()
    m = rel.engine_out_thrust_margin(res, 1)
    assert m["n_engines"] == 6 and m["is_first_stage"]
    assert m["tw_one_out"] == pytest.approx(m["tw_nominal"] * 5 / 6, rel=1e-9)
    assert m["lifts_off_one_out"] is (m["tw_one_out"] > 1.0)
    assert m["can_lose_an_engine"] is True, \
        f"T/W falls to {m['tw_one_out']:.2f} with one of six out, so the claim in the design file is wrong"


def test_a_single_engine_stage_has_no_redundancy_to_report():
    res = default_result()
    m = rel.engine_out_thrust_margin(res, 2)
    assert m["n_engines"] == 1
    assert m["tw_one_out"] is None and m["can_lose_an_engine"] is False
    c = rel.cluster(1, 0.98)
    assert c["one_out_tolerant"] is None and c["all_must_work"] == pytest.approx(0.98)


def test_a_named_flight_record_can_drive_the_analysis():
    res = default_result()
    a = rel.analyse(res, record="Merlin 1D")
    assert a["r_engine"] == pytest.approx(1 - 1 / 1278)
    assert "Falcon 9" in a["source"] and "Table 15.4" in a["source"]
    assert a["record"]["lower_bound"] < a["record"]["point"]
    try:
        rel.analyse(res, record="Raptor")
        raise AssertionError("an engine not in Table 15.4 should be refused")
    except ValueError as e:
        assert "Table 15.4" in str(e)


def test_redundancy_is_only_worth_something_when_the_stage_can_fly_without_the_engine():
    """A 9-engine stage that cannot lift off on 8 has no redundancy, whatever the binomial says."""
    c_tolerant = rel.cluster(9, 0.99, k_required=8)
    c_not = rel.cluster(9, 0.99, k_required=9)
    assert c_tolerant["r_cluster"] > c_not["r_cluster"]
    assert c_not["r_cluster"] == pytest.approx(0.99 ** 9, rel=1e-12)
    assert c_tolerant["redundancy_gain"] > 0
