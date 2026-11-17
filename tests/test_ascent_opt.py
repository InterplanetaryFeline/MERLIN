"""Ascent pitch-programme optimisation (book Sec. 6.7 / 6.10).

The book gives no method here and says so, so there is no published answer to check against. What can be
checked is that the search does what the book says the physics does: steering over earlier trades gravity loss
for steering loss and air loads, the optimum therefore sits on a limit rather than at a stationary point, and
the result is never better than the constraints allow. Plus the usual mechanical properties of a search: it
never returns an infeasible point, it never returns worse than its own starting point, and it is deterministic.
"""
import math
import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import ascent_opt as ao, trajectory as tj

_C = {}


def vehicle():
    if "r" not in _C:
        _C["r"] = default_result()
        _C["v"] = tj.ascent_vehicle_from_result(_C["r"])
        _C["target"] = _C["r"].spec.mission["perigee_altitude_m"]
    return _C["r"], _C["v"], _C["target"]


def tight_limits():
    return ao.AscentLimits(max_q_Pa=44_000.0, max_q_alpha_Pa_deg=331_800.0, max_axial_g=6.0)


def run():
    if "opt" not in _C:
        r, _, _ = vehicle()
        _C["opt"] = ao.optimise(r, limits=tight_limits(), dt=0.5, max_evaluations=70)
    return _C["opt"]


# ------------------------------------------------------------------ the book's constants
def test_the_book_reference_values_are_the_figures_they_came_from():
    """Fig. 9.36: 920 lbf/ft2 of dynamic pressure and 6,930 lbf deg/ft2 of q.alpha, in SI."""
    assert ao.BOOK_TYPICAL_MAX_Q_PA == pytest.approx(920 * 47.8803, rel=0.005)
    assert ao.BOOK_TYPICAL_Q_ALPHA_PA_DEG == pytest.approx(6930 * 47.8803, rel=0.005)


def test_q_alpha_is_the_peak_of_the_product_not_the_product_of_the_peaks():
    r, v, target = vehicle()
    c = ao.evaluate(v, target, 20_000.0, 15.0, 10.0, ao.AscentLimits(), dt=0.5)
    assert c.result is not None
    qa = ao.max_q_alpha(c.result)
    assert qa <= max(c.result.q_Pa) * max(abs(a) for a in c.result.alpha_deg) + 1e-6
    assert qa > 0.0, "the terminal guidance does fly at an angle of attack"


def test_a_pure_gravity_turn_has_no_q_alpha():
    """Inside the gravity turn the thrust is along the velocity by construction, which is the whole reason to
    fly one: no steering loss and no air load from angle of attack (book Sec. 6.4.7)."""
    r, v, target = vehicle()
    g = tj.Guidance(vertical_rise_s=10.0, kick_deg=0.3, terminal_mode="none")
    out = tj.integrate(v, g, dt=0.5)
    assert ao.max_q_alpha(out) == pytest.approx(0.0, abs=1e-9)


# ------------------------------------------------------------------ the physics the book describes
def test_steering_over_earlier_trades_gravity_loss_for_steering_loss():
    """Book Sec. 6.10, both rules at once: "Climbing vertically produces gravity loss, so try to get
    horizontal as soon as possible" and "a shallow climb produces significant drag loss, higher aerodynamic
    loads... so don't go shallow or level off too soon"."""
    r, v, target = vehicle()
    lim = ao.AscentLimits()
    low = ao.evaluate(v, target, 10_000.0, 15.0, 10.0, lim, dt=0.5)
    high = ao.evaluate(v, target, 60_000.0, 15.0, 10.0, lim, dt=0.5)
    assert low.result.converged and high.result.converged
    assert low.result.gravity_loss_mps < high.result.gravity_loss_mps, "earlier turn, less gravity loss"
    assert low.result.steering_loss_mps > high.result.steering_loss_mps, "paid for in steering"
    assert low.result.drag_loss_mps > high.result.drag_loss_mps, "and in drag"
    assert ao.max_q_alpha(low.result) > ao.max_q_alpha(high.result), "and in air loads"
    assert low.result.burnout_v_mps > high.result.burnout_v_mps, "but the trade is profitable, which is why "\
                                                                 "a limit rather than the objective has to stop it"


def test_the_kick_absorbs_the_vertical_rise_time():
    """With the kick re-solved to hit the same burnout altitude, how long the vehicle stands up straight
    barely matters - a result worth pinning, because it says which parameter in this guidance law is real."""
    r, v, target = vehicle()
    lim = ao.AscentLimits()
    vs = [ao.evaluate(v, target, 40_000.0, 15.0, t, lim, dt=0.5).result.burnout_v_mps for t in (5.0, 10.0, 20.0)]
    assert max(vs) - min(vs) < 5.0, f"burnout speeds {vs} should barely differ"
    kicks = [ao.evaluate(v, target, 40_000.0, 15.0, t, lim, dt=0.5).result.kick_deg for t in (5.0, 20.0)]
    assert kicks[0] != kicks[1], "because the kick moved to compensate"


# ------------------------------------------------------------------ the limits
def test_a_violated_limit_makes_a_candidate_infeasible_and_unranked():
    r, v, target = vehicle()
    strict = ao.AscentLimits(max_q_alpha_Pa_deg=1.0)
    c = ao.evaluate(v, target, 10_000.0, 15.0, 10.0, strict, dt=0.5)
    assert not c.feasible
    assert c.objective_mps == -math.inf
    assert any("q.alpha" in s for s in c.violations)


def test_each_limit_can_bind_on_its_own():
    r, v, target = vehicle()
    # Hand over at 10 km. This used 5 km while every design flew on the Titan II drag curve; with the drag built
    # up from this vehicle's own geometry, steering that low in the atmosphere no longer shoots to within the
    # 150 m altitude tolerance (it gets to 398 km of 400), so 5 km stopped being a candidate that is fine when
    # unconstrained. What is under test is each limit binding on its own, which needs a candidate that is.
    c = ao.evaluate(v, target, 10_000.0, 15.0, 10.0, ao.AscentLimits(), dt=0.5)
    assert c.feasible, "unconstrained, this is a fine candidate"
    for lim, word in ((ao.AscentLimits(max_q_Pa=1.0), "max-q"),
                      (ao.AscentLimits(max_q_alpha_Pa_deg=1.0), "q.alpha"),
                      (ao.AscentLimits(max_axial_g=0.1), "axial")):
        bad = ao.evaluate(v, target, 10_000.0, 15.0, 10.0, lim, dt=0.5)
        assert not bad.feasible and any(word in s for s in bad.violations), word


def test_a_non_insertion_is_rejected_however_fast_it_is_going():
    """A trajectory that arrives at the right altitude pointing somewhere else is not an ascent, and must not
    be allowed to win on burnout speed."""
    r, v, target = vehicle()
    lim = ao.AscentLimits(max_gamma_burnout_deg=0.001)
    c = ao.evaluate(v, target, 60_000.0, 15.0, 10.0, lim, dt=0.5)
    assert not c.feasible
    assert any("not an insertion" in s for s in c.violations)


# ------------------------------------------------------------------ the search itself
def test_the_search_never_returns_an_infeasible_or_worse_point():
    out = run()
    assert out["ok"]
    b, o = out["baseline"], out["best"]
    assert o["feasible"] and not o["violations"]
    assert o["burnout_v_mps"] >= b["burnout_v_mps"] - 1e-9, "never worse than where it started"
    assert out["speed_gain_mps"] >= 0.0
    assert out["evaluations"] <= 70


def test_the_optimum_respects_every_limit_it_was_given():
    out = run()
    o, lim = out["best"], out["limits"]
    assert o["max_q_Pa"] <= lim["max_q_Pa"] + 1e-6
    assert o["max_q_alpha_Pa_deg"] <= lim["max_q_alpha_Pa_deg"] + 1e-6
    assert o["max_accel_g"] <= lim["max_axial_g"] + 1e-6
    assert abs(o["burnout_gamma_deg"]) <= lim["max_gamma_burnout_deg"]


def test_the_optimum_lands_on_a_constraint_and_the_report_says_which():
    """The expected shape of this problem: the objective improves monotonically towards the atmosphere, so
    something other than the objective has to stop the search."""
    out = run()
    assert out["binding"]["name"] not in ("none",), out["binding"]
    assert out["binding"]["detail"]
    assert any("constraint" in n for n in out["notes"])


def test_the_optimum_reaches_the_target_altitude_like_every_candidate():
    """The terminal altitude is met by the inner shooting solve, not by a penalty, so it holds exactly."""
    r, _, target = vehicle()
    out = run()
    assert abs(out["best"]["burnout_h_m"] - target) < 3_000.0
    assert abs(out["baseline"]["burnout_h_m"] - target) < 3_000.0


def test_the_search_is_deterministic():
    r, _, _ = vehicle()
    a = ao.optimise(r, limits=tight_limits(), dt=0.5, max_evaluations=40)
    b = ao.optimise(r, limits=tight_limits(), dt=0.5, max_evaluations=40)
    assert a["best"]["handover_h_m"] == b["best"]["handover_h_m"]
    assert a["best"]["burnout_v_mps"] == pytest.approx(b["best"]["burnout_v_mps"], rel=1e-12)
    assert a["evaluations"] == b["evaluations"]


def test_without_limits_the_result_says_it_means_nothing():
    r, _, _ = vehicle()
    out = ao.optimise(r, limits=ao.AscentLimits(), dt=0.6, max_evaluations=24)
    assert any("UNCONSTRAINED" in n for n in out["notes"])


def test_an_impossible_limit_reports_failure_rather_than_a_number():
    r, _, _ = vehicle()
    out = ao.optimise(r, limits=ao.AscentLimits(max_q_Pa=1.0), dt=0.6, max_evaluations=12)
    assert not out["ok"]
    assert out["best"] is None
    assert out["baseline"]["violations"]


def test_the_trade_sweep_spans_the_box_and_is_monotone_in_the_losses():
    out = run()
    sw = out["sweep"]
    assert len(sw) >= 6
    hs = [p["handover_h_m"] for p in sw]
    assert hs == sorted(hs)
    grav = [p["gravity_loss_mps"] for p in sw]
    assert grav == sorted(grav), "gravity loss grows as the hand-over is pushed higher"
    steer = [p["steering_loss_mps"] for p in sw]
    assert steer == sorted(steer, reverse=True), "steering loss falls as it is pushed higher"


# ------------------------------------------------------------------ pricing it in payload
def test_payload_pricing_is_self_consistent_with_the_trajectory():
    """The payload returned must be the one at which the FLOWN burnout speed meets the orbit requirement -
    no regression anywhere in the loop."""
    r, _, _ = vehicle()
    g = tj.Guidance()
    out = ao.payload_for_programme(r, g.terminal_start_h_m, g.max_alpha_deg, 10.0, dt=0.6)
    assert out["ok"]
    assert out["payload_kg"] > out["design_payload_kg"], "the design closes with margin, so it lifts more"
    assert out["surplus_speed_mps"] > 0
    need = r.budget.info["v_needed_mps"]
    assert out["v_needed_mps"] == pytest.approx(need, rel=1e-12)
    # fly it at the found payload: the margin should be about zero
    import dataclasses
    veh = dataclasses.replace(tj.ascent_vehicle_from_result(r),
                              m0_kg=r.glom_kg + out["surplus_payload_kg"])
    flown = tj.shoot_for_altitude(veh, r.spec.mission["perigee_altitude_m"], dt=0.6, tol_m=150.0)
    assert flown.converged
    assert abs(flown.burnout_v_mps - need) < 30.0, "the bisection really did land on the requirement"


def test_a_better_programme_is_worth_more_payload():
    r, _, _ = vehicle()
    g = tj.Guidance()
    base = ao.payload_for_programme(r, g.terminal_start_h_m, g.max_alpha_deg, 10.0, dt=0.6)
    better = ao.payload_for_programme(r, 10_000.0, g.max_alpha_deg, 10.0, dt=0.6)
    assert base["ok"] and better["ok"]
    assert better["payload_kg"] > base["payload_kg"]
    assert better["surplus_speed_mps"] > base["surplus_speed_mps"]


def test_limits_come_from_the_design_constraints_block():
    r, _, _ = vehicle()
    lim = ao.limits_from_spec(r.spec)
    assert lim.max_axial_g == pytest.approx(r.spec.constraints["max_accel_g"])
    assert lim.max_q_Pa == pytest.approx(r.spec.constraints["max_dynamic_pressure_Pa"])
    assert lim.max_q_alpha_Pa_deg == pytest.approx(r.spec.constraints["max_q_alpha_Pa_deg"])
