"""Ascent pitch-programme optimisation (book Sec. 6.7, conclusions Sec. 6.10).

What the book supplies and what it does not
-------------------------------------------
Section 6.7 defines the problem and the trade, and states the answer's shape: fly vertically and gravity loss
grows; pitch over early and gravity loss falls but air loads, drag and heating grow; the optimum "for a vehicle
with a moderate T/W ratio is a compromise somewhere between" the two (Fig. 6.26). Section 6.10 puts the same
thing as two rules:

    "Climbing vertically produces gravity loss, so try to get horizontal as soon as possible to minimize this."
    "A shallow climb produces significant drag loss, higher aerodynamic loads, or even overheating, so don't go
     shallow or level off too soon."

What the book does NOT supply is a method: "The mathematics behind the theory of optimization is relatively
complicated and will not be presented here" (p.383). It names the codes the industry uses - OTIS, POST-II, SORT,
GPOPS-II - and notes the first three are ITAR controlled. So the objective, the parameters and the constraints
below are the book's; the search is this module's own and is marked SUPPLEMENTARY in the method register.

What is optimised
-----------------
The guidance already flown has three things that can be chosen freely: how long the vehicle rises vertically
before the pitch kick, the altitude at which it stops flying a pure gravity turn and starts steering towards
the commanded injection flight path angle, and how much angle of attack that steering is allowed to use. The
pitch kick itself is NOT free - it is solved by shooting so that burnout lands on the target altitude, which
is how the terminal constraint is met exactly for every candidate rather than penalised.

The objective is burnout speed. For a fixed vehicle the vacuum ideal delta-v is fixed, so maximising burnout
speed is the same as minimising the sum of the losses, and the payload that buys is found afterwards by flying
the vehicle heavier until it just reaches the orbit again.

Why the constraints decide the answer
-------------------------------------
Left alone, the objective improves all the way down: steering towards horizontal earlier always trades gravity
loss for steering loss at a profit, until the vehicle is carving through the lower atmosphere. That is the
book's trajectory B, and the thing that stops it is not the objective but the vehicle: dynamic pressure, the
product q*alpha that sets air loads, and axial acceleration. So the optimum sits on whichever limit binds
first, and this module reports which one. The limits are inputs, not discoveries; with none given, the result
says plainly that the answer is the edge of the search box and means nothing.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from . import trajectory as tj

# Reference values from the book's own examples, for the config defaults. These are what real vehicles were
# measured at, NOT certified limits for any particular design:
#   max-q   Fig. 9.36 generic LV 920 psf = 44.0 kPa; Saturn V 35.2 kPa (Sec. 9.2); Delta III Shuttle-profile
#           695 psf = 33.3 kPa (p.405); Pegasus 66.9 kPa, which the book flags as high enough to cost 322 m/s
#           of drag loss (p.414).
#   q*alpha Fig. 9.36 generic LV (q alpha)max = 6,930 lbf deg/ft2 = 331.8 kPa deg.
BOOK_TYPICAL_MAX_Q_PA = 44_000.0
BOOK_TYPICAL_Q_ALPHA_PA_DEG = 331_800.0


@dataclass
class AscentLimits:
    """The constraints the optimum sits on. None means unconstrained in that direction."""
    max_q_Pa: float | None = None
    max_q_alpha_Pa_deg: float | None = None
    max_axial_g: float | None = None
    max_gamma_burnout_deg: float = 10.0

    def check(self, r) -> list:
        """Which limits a flown trajectory violates, and by how much."""
        bad = []
        if not r.converged:
            return [f"the ascent did not close: {r.status}"]
        if self.max_q_Pa and r.max_q_Pa > self.max_q_Pa:
            bad.append(f"max-q {r.max_q_Pa/1e3:,.1f} kPa over the {self.max_q_Pa/1e3:,.1f} kPa limit")
        qa = max_q_alpha(r)
        if self.max_q_alpha_Pa_deg and qa > self.max_q_alpha_Pa_deg:
            bad.append(f"q.alpha {qa/1e3:,.0f} kPa.deg over the {self.max_q_alpha_Pa_deg/1e3:,.0f} limit")
        if self.max_axial_g and r.max_accel_g > self.max_axial_g:
            bad.append(f"axial acceleration {r.max_accel_g:.2f} g over the {self.max_axial_g:.2f} g limit")
        if abs(r.burnout_gamma_deg) > self.max_gamma_burnout_deg:
            bad.append(f"burnout flight path angle {r.burnout_gamma_deg:+.1f} deg is not an insertion")
        return bad


def max_q_alpha(r) -> float:
    """Peak of q times the angle between thrust and velocity, in Pa.deg - the book's air-load parameter
    (Fig. 9.36). The trajectory records alpha only where the terminal guidance commands it; inside the gravity
    turn it is zero by construction, which is the whole point of flying one."""
    if not r.alpha_deg:
        return 0.0
    return max(r.q_Pa[k] * abs(r.alpha_deg[k]) for k in range(min(len(r.q_Pa), len(r.alpha_deg))))


@dataclass
class Candidate:
    handover_h_m: float
    max_alpha_deg: float
    vertical_rise_s: float
    objective_mps: float                 # burnout speed; -inf when the candidate is unusable
    feasible: bool
    violations: list = field(default_factory=list)
    result: object = None

    def key(self) -> tuple:
        return (round(self.handover_h_m, 1), round(self.max_alpha_deg, 4), round(self.vertical_rise_s, 3))

    def summary(self) -> dict:
        r = self.result
        return dict(handover_h_m=self.handover_h_m, max_alpha_deg=self.max_alpha_deg,
                    vertical_rise_s=self.vertical_rise_s, feasible=self.feasible,
                    violations=list(self.violations),
                    burnout_v_mps=getattr(r, "burnout_v_mps", float("nan")),
                    kick_deg=getattr(r, "kick_deg", float("nan")),
                    total_loss_mps=getattr(r, "total_loss_mps", float("nan")),
                    gravity_loss_mps=getattr(r, "gravity_loss_mps", float("nan")),
                    drag_loss_mps=getattr(r, "drag_loss_mps", float("nan")),
                    steering_loss_mps=getattr(r, "steering_loss_mps", float("nan")),
                    propulsion_loss_mps=getattr(r, "propulsion_loss_mps", float("nan")),
                    max_q_Pa=getattr(r, "max_q_Pa", float("nan")),
                    max_q_alpha_Pa_deg=max_q_alpha(r) if r else float("nan"),
                    max_accel_g=getattr(r, "max_accel_g", float("nan")),
                    burnout_h_m=getattr(r, "burnout_h_m", float("nan")),
                    burnout_gamma_deg=getattr(r, "burnout_gamma_deg", float("nan")))


# --------------------------------------------------------------------------- one candidate
def evaluate(veh, target_altitude_m: float, handover_h_m: float, max_alpha_deg: float,
             vertical_rise_s: float, limits: AscentLimits, dt: float = 0.4,
             tol_m: float = 150.0) -> Candidate:
    """Fly one pitch programme, with the kick solved by shooting so the target altitude is always met.

    The shooting tolerance matters more than it looks: at the 2 km default the burnout altitude wanders enough
    to move the burnout speed by several m/s, which is the same size as the differences being optimised over,
    and a search run on that noise chases the solver rather than the vehicle.
    """
    g = tj.Guidance(vertical_rise_s=vertical_rise_s, terminal_start_h_m=handover_h_m,
                    max_alpha_deg=max_alpha_deg)
    try:
        r = tj.shoot_for_altitude(veh, target_altitude_m, vertical_rise_s=vertical_rise_s, dt=dt,
                                  tol_m=tol_m, guidance=g)
    except Exception as ex:                                      # noqa: BLE001 - an unusable candidate, not a bug
        return Candidate(handover_h_m, max_alpha_deg, vertical_rise_s, -math.inf, False,
                         [f"{type(ex).__name__}: {ex}"], None)
    bad = limits.check(r)
    obj = r.burnout_v_mps if not bad else -math.inf
    return Candidate(handover_h_m, max_alpha_deg, vertical_rise_s, obj, not bad, bad, r)


# --------------------------------------------------------------------------- the search
def optimise(res, drag=None, atmosphere: str = "book_exponential", limits: AscentLimits | None = None,
             baseline_vertical_rise_s: float = 10.0, dt: float = 0.4, tol_m: float = 150.0,
             handover_bounds_m: tuple = (1_000.0, 90_000.0), alpha_bounds_deg: tuple = (2.0, 25.0),
             rise_bounds_s: tuple = (3.0, 25.0), max_evaluations: int = 120,
             last_ascent_stage: int | None = None) -> dict:
    """Pattern search on (handover altitude, angle-of-attack allowance, vertical rise) for burnout speed.

    A compass search is used rather than anything gradient-based: evaluations are discontinuous (a candidate
    can simply fail to reach orbit, or violate a limit), so only comparisons are safe. It polls each axis in
    both directions at the current step, moves to the best improvement, and halves the step when a poll finds
    none - which is a convergence proof on a smooth function and a sensible stopping rule on this one.
    """
    limits = limits or AscentLimits()
    veh = tj.ascent_vehicle_from_result(res, drag, atmosphere, last_ascent_stage=last_ascent_stage)
    target = res.spec.mission["perigee_altitude_m"]
    cache, evals = {}, 0

    def at(h, a, v):
        nonlocal evals
        h = min(max(h, handover_bounds_m[0]), handover_bounds_m[1])
        a = min(max(a, alpha_bounds_deg[0]), alpha_bounds_deg[1])
        v = min(max(v, rise_bounds_s[0]), rise_bounds_s[1])
        c = Candidate(h, a, v, -math.inf, False)
        if c.key() in cache:
            return cache[c.key()]
        if evals >= max_evaluations:
            return None
        evals += 1
        c = evaluate(veh, target, h, a, v, limits, dt, tol_m)
        cache[c.key()] = c
        return c

    base = evaluate(veh, target, tj.Guidance().terminal_start_h_m, tj.Guidance().max_alpha_deg,
                    baseline_vertical_rise_s, limits, dt, tol_m)
    evals += 1
    best = base if base.feasible else None

    # If the baseline itself breaks a limit there is nothing to improve from; walk the handover altitude up
    # until something is feasible, because higher handover always means less steering and less q.
    if best is None:
        for h in (40_000.0, 60_000.0, 80_000.0, 90_000.0):
            c = at(h, tj.Guidance().max_alpha_deg, baseline_vertical_rise_s)
            if c and c.feasible:
                best = c
                break
    if best is None:
        return dict(ok=False, baseline=base.summary(), best=None, sweep=[], evaluations=evals,
                    limits=_limits_dict(limits),
                    notes=["No pitch programme in the search box met the limits, so there is nothing to "
                           "optimise. The baseline's own violations are listed with it."])

    step = [20_000.0, 6.0, 6.0]                                  # handover [m], alpha [deg], rise [s]
    floor = [500.0, 0.25, 0.5]
    while evals < max_evaluations and any(s > f for s, f in zip(step, floor)):
        polled = []
        for axis, s in enumerate(step):
            if s <= floor[axis]:
                continue
            for sign in (-1, +1):
                p = [best.handover_h_m, best.max_alpha_deg, best.vertical_rise_s]
                p[axis] += sign * s
                c = at(*p)
                if c:
                    polled.append(c)
        better = [c for c in polled if c.feasible and c.objective_mps > best.objective_mps + 1e-6]
        if better:
            best = max(better, key=lambda c: c.objective_mps)
        else:
            step = [max(s / 2.0, 0.0) for s in step]
            if all(s <= f for s, f in zip(step, floor)):
                break

    sweep = _trade_sweep(veh, target, limits, best, dt, tol_m, handover_bounds_m)
    binding = _binding_constraint(veh, target, limits, best, dt, tol_m)
    gain = best.objective_mps - base.objective_mps if base.feasible else float("nan")
    return dict(ok=True, baseline=base.summary(), best=best.summary(), sweep=sweep, evaluations=evals,
                limits=_limits_dict(limits), binding=binding, speed_gain_mps=gain,
                notes=_notes(base, best, binding, limits, gain))


def _limits_dict(limits: AscentLimits) -> dict:
    return dict(max_q_Pa=limits.max_q_Pa, max_q_alpha_Pa_deg=limits.max_q_alpha_Pa_deg,
                max_axial_g=limits.max_axial_g, max_gamma_burnout_deg=limits.max_gamma_burnout_deg)


def _trade_sweep(veh, target, limits, best, dt, tol_m, bounds) -> list:
    """The book's Fig. 6.26 trade, as numbers: how the losses move as the vehicle is steered over earlier."""
    out = []
    lo, hi = bounds
    for i in range(9):
        h = lo + (hi - lo) * i / 8.0
        c = evaluate(veh, target, h, best.max_alpha_deg, best.vertical_rise_s, limits, dt, tol_m)
        if c.result is not None and c.result.converged:
            out.append(c.summary())
    return out


def _binding_constraint(veh, target, limits, best, dt, tol_m) -> dict:
    """Which limit stops the optimiser going further, found by stepping past the optimum and seeing what breaks.

    There are two ways to fly more aggressively: hand over to steering lower, or allow a larger angle between
    thrust and velocity. Both are probed. Probing only the handover altitude compared the optimum with itself
    whenever the optimum was already at the 1,000 m floor, and reported "no limit is binding" for a programme
    sitting at 99 % of its q.alpha limit - which the geometry drag model was the first to expose, by moving
    the default design's optimum down to the floor.
    """
    floor_m = 1_000.0
    at_floor = best.handover_h_m <= floor_m + 1e-6
    probes = [] if at_floor else [(max(best.handover_h_m - 2_000.0, floor_m), best.max_alpha_deg)]
    probes.append((best.handover_h_m, best.max_alpha_deg + 1.0))
    gained = False
    for handover, alpha in probes:
        probe = evaluate(veh, target, handover, alpha, best.vertical_rise_s, limits, dt, tol_m)
        if probe.violations:
            return dict(name=probe.violations[0].split()[0], detail=probe.violations[0])
        gained = gained or (probe.feasible and probe.objective_mps > best.objective_mps)
    if gained:
        return dict(name="search box", detail="the optimiser reached the edge of the search box, not a limit")
    if at_floor:
        return dict(name="search box", detail=f"the handover altitude is at the {floor_m:,.0f} m floor of the "
                                              f"search and steering harder gains nothing, so the search box "
                                              f"stops it, not a limit")
    return dict(name="none", detail="going further gave no further gain, so no limit is binding here")


def _notes(base, best, binding, limits, gain) -> list:
    out = []
    if not any([limits.max_q_Pa, limits.max_q_alpha_Pa_deg, limits.max_axial_g]):
        out.append("No vehicle limits were given, so this is an UNCONSTRAINED optimum: the search will push the "
                   "vehicle as far into the atmosphere as the box allows, which is the book's trajectory B and "
                   "is not a design. Set the dynamic pressure, q.alpha and axial acceleration limits.")
    else:
        out.append(f"The optimum sits on a constraint, not on a stationary point of the objective: "
                   f"{binding.get('detail', '')}. That is the expected shape of this problem - steering over "
                   f"earlier always trades gravity loss for steering loss at a profit until the vehicle cannot "
                   f"take the air loads (book Sec. 6.10).")
    b, o = base.summary(), best.summary()
    def moved(key, label):
        d = o[key] - b[key]
        return f"{label} {'up' if d > 0 else 'down'} {abs(d):,.0f} m/s"
    out.append("Between the baseline and the optimum: " + ", ".join(
        moved(k, lab) for k, lab in (("gravity_loss_mps", "gravity loss"), ("steering_loss_mps", "steering loss"),
                                     ("drag_loss_mps", "drag loss"))) +
               f". The net is {gain:+,.0f} m/s of burnout speed.")
    out.append(f"max-q goes from {b['max_q_Pa']/1e3:,.1f} to {o['max_q_Pa']/1e3:,.1f} kPa and q.alpha from "
               f"{b['max_q_alpha_Pa_deg']/1e3:,.0f} to {o['max_q_alpha_Pa_deg']/1e3:,.0f} kPa.deg, which is "
               f"what the extra speed is bought with.")
    return out


# --------------------------------------------------------------------------- what the speed is worth
def payload_for_programme(res, handover_h_m: float, max_alpha_deg: float, vertical_rise_s: float,
                          drag=None, atmosphere: str = "book_exponential", dt: float = 0.4,
                          tol_m: float = 150.0, tol_kg: float = 25.0, max_iter: int = 14,
                          last_ascent_stage: int | None = None) -> dict:
    """Payload this pitch programme delivers, by flying the vehicle heavier until it just reaches the orbit.

    Everything but the payload is frozen: the same stages, the same propellant loads, the same burn times. Only
    the mass at lift-off changes, which is what a performance trade on a built vehicle means. The root is the
    payload at which burnout speed equals the speed the orbit needs, both from the same integration - so the
    answer never mixes a flown trajectory with a regression estimate.
    """
    need = res.budget.info.get("v_needed_mps") or 0.0
    target = res.spec.mission["perigee_altitude_m"]
    base_veh = tj.ascent_vehicle_from_result(res, drag, atmosphere, last_ascent_stage=last_ascent_stage)
    g0_mass = base_veh.m0_kg

    def margin(dm):
        veh = replace(base_veh, m0_kg=g0_mass + dm)
        r = tj.shoot_for_altitude(veh, target, vertical_rise_s=vertical_rise_s, dt=dt, tol_m=tol_m,
                                  guidance=tj.Guidance(vertical_rise_s=vertical_rise_s,
                                                       terminal_start_h_m=handover_h_m,
                                                       max_alpha_deg=max_alpha_deg))
        if not r.converged or abs(r.burnout_gamma_deg) > 10.0:
            return -math.inf, r
        return r.burnout_v_mps - need, r

    m0, r0 = margin(0.0)
    if m0 == -math.inf:
        return dict(ok=False, reason="the vehicle does not reach the orbit on this programme at its design "
                                     "payload, so there is no capability to report")
    if m0 < 0:
        return dict(ok=False, reason=f"the flown ascent falls {-m0:,.0f} m/s short of the orbit at the design "
                                     f"payload, so this programme delivers less than the design payload")
    lo, hi = 0.0, max(0.25 * res.payload_mass_kg, 500.0)
    while True:
        mh, _ = margin(hi)
        if mh < 0:
            break
        lo = hi
        hi *= 2.0
        if hi > 20.0 * max(res.payload_mass_kg, 1.0):
            return dict(ok=False, reason="could not bracket the payload: the surplus speed is larger than this "
                                         "frozen-vehicle trade can meaningfully extrapolate")
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        m, _ = margin(mid)
        if m > 0:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol_kg:
            break
    dm = 0.5 * (lo + hi)
    return dict(ok=True, payload_kg=res.payload_mass_kg + dm, surplus_payload_kg=dm,
                design_payload_kg=res.payload_mass_kg, surplus_speed_mps=m0, v_needed_mps=need)


def optimise_and_price(res, drag=None, atmosphere: str = "book_exponential", limits: AscentLimits | None = None,
                       dt: float = 0.4, max_evaluations: int = 120, vertical_rise_s: float = 10.0,
                       last_ascent_stage: int | None = None) -> dict:
    """The whole study: optimise the programme, then price the baseline and the optimum in payload."""
    out = optimise(res, drag, atmosphere, limits, baseline_vertical_rise_s=vertical_rise_s, dt=dt,
                   max_evaluations=max_evaluations, last_ascent_stage=last_ascent_stage)
    if not out.get("ok"):
        return out
    b, o = out["baseline"], out["best"]
    out["payload_baseline"] = payload_for_programme(res, b["handover_h_m"], b["max_alpha_deg"],
                                                    b["vertical_rise_s"], drag, atmosphere, dt,
                                                    last_ascent_stage=last_ascent_stage)
    out["payload_optimum"] = payload_for_programme(res, o["handover_h_m"], o["max_alpha_deg"],
                                                   o["vertical_rise_s"], drag, atmosphere, dt,
                                                   last_ascent_stage=last_ascent_stage)
    pb, po = out["payload_baseline"], out["payload_optimum"]
    if pb.get("ok") and po.get("ok"):
        out["payload_gain_kg"] = po["payload_kg"] - pb["payload_kg"]
        out["notes"].append(
            f"Priced in payload on a frozen vehicle: {pb['payload_kg']:,.0f} kg on the baseline programme "
            f"against {po['payload_kg']:,.0f} kg on the optimised one, a gain of "
            f"{out['payload_gain_kg']:+,.0f} kg ({100*out['payload_gain_kg']/max(pb['payload_kg'], 1):+.1f} %). "
            f"This is a trade on the vehicle as built - nothing is re-sized, so it is what better steering is "
            f"worth, not what a vehicle designed around it would be.")
    return out


def limits_from_spec(spec) -> AscentLimits:
    """Read the limits from the design's constraints block."""
    c = spec.constraints or {}
    return AscentLimits(max_q_Pa=c.get("max_dynamic_pressure_Pa"),
                        max_q_alpha_Pa_deg=c.get("max_q_alpha_Pa_deg"),
                        max_axial_g=c.get("max_accel_g"))
