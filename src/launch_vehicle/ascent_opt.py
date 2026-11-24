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
Every flight already solves its own steering and picks the pitch kick that leaves the most speed in hand (see
`ascent.py`). Two things are left to choose: how long the vehicle rises vertically before the pitch kick, and the
altitude at which it stops flying a pure gravity turn and starts steering. Both are searched here, with the vehicle's
limits enforced: the dynamic pressure limit rules out a kick, and the q*alpha limit bounds the angle between thrust and
velocity wherever there is air.

The objective is the margin: the speed left in the tanks when the orbit has been reached, or minus the speed that is
missing. What it is worth is found afterwards by flying the vehicle heavier until the margin is zero.

Why the constraints decide the answer
-------------------------------------
Left alone, the objective improves as the vehicle is steered earlier, until it is carving through the lower atmosphere.
That is the book's trajectory B, and the thing that stops it is not the objective but the vehicle: dynamic pressure, the
product q*alpha that sets air loads, and axial acceleration. The limits are inputs, not discoveries; with none given,
the result says plainly that the answer is the edge of the search box and means nothing.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from . import ascent, trajectory as tj

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
        # half a per cent: the flight holds q and q.alpha at the limit itself, and the history is sampled
        if self.max_q_Pa and r.max_q_Pa > 1.005 * self.max_q_Pa:
            bad.append(f"max-q {r.max_q_Pa/1e3:,.1f} kPa over the {self.max_q_Pa/1e3:,.1f} kPa limit")
        qa = max_q_alpha(r)
        if self.max_q_alpha_Pa_deg and qa > 1.005 * self.max_q_alpha_Pa_deg:
            bad.append(f"q.alpha {qa/1e3:,.0f} kPa.deg over the {self.max_q_alpha_Pa_deg/1e3:,.0f} limit")
        if self.max_axial_g and r.max_accel_g > 1.005 * self.max_axial_g:
            bad.append(f"axial acceleration {r.max_accel_g:.2f} g over the {self.max_axial_g:.2f} g limit")
        if abs(r.burnout_gamma_deg) > self.max_gamma_burnout_deg:
            bad.append(f"burnout flight path angle {r.burnout_gamma_deg:+.1f} deg is not an insertion")
        return bad


def max_q_alpha(r) -> float:
    """Peak of q times the angle between thrust and velocity, in Pa.deg - the book's air-load parameter
    (Fig. 9.36). Alpha is recorded only where the vehicle steers; inside the gravity turn it is zero by construction,
    which is the whole point of flying one."""
    if not r.alpha_deg:
        return 0.0
    return max(r.q_Pa[k] * abs(r.alpha_deg[k]) for k in range(min(len(r.q_Pa), len(r.alpha_deg))))


@dataclass
class Candidate:
    handover_h_m: float
    vertical_rise_s: float
    objective_mps: float                 # speed in hand; -inf when the candidate is unusable
    feasible: bool
    violations: list = field(default_factory=list)
    result: object = None
    solution: object = None

    def key(self) -> tuple:
        return (round(self.handover_h_m, 1), round(self.vertical_rise_s, 3))

    def summary(self) -> dict:
        r = self.result
        nan = float("nan")
        return dict(handover_h_m=self.handover_h_m, vertical_rise_s=self.vertical_rise_s, feasible=self.feasible,
                    violations=list(self.violations),
                    margin_mps=getattr(r, "margin_mps", nan),
                    max_alpha_deg=getattr(r, "max_alpha_deg", nan),
                    burnout_v_mps=getattr(r, "burnout_v_mps", nan),
                    kick_deg=getattr(r, "kick_deg", nan),
                    total_loss_mps=getattr(r, "total_loss_mps", nan),
                    gravity_loss_mps=getattr(r, "gravity_loss_mps", nan),
                    drag_loss_mps=getattr(r, "drag_loss_mps", nan),
                    steering_loss_mps=getattr(r, "steering_loss_mps", nan),
                    propulsion_loss_mps=getattr(r, "propulsion_loss_mps", nan),
                    max_q_Pa=getattr(r, "max_q_Pa", nan),
                    max_q_alpha_Pa_deg=max_q_alpha(r) if r else nan,
                    max_accel_g=getattr(r, "max_accel_g", nan),
                    burnout_h_m=getattr(r, "burnout_h_m", nan),
                    burnout_gamma_deg=getattr(r, "burnout_gamma_deg", nan))


# --------------------------------------------------------------------------- one candidate
def flight(res, veh, handover_h_m: float, vertical_rise_s: float, limits: AscentLimits, **mission):
    return ascent.flight_for(res, veh, rise_s=vertical_rise_s, handover_h_m=handover_h_m,
                             q_limit_Pa=limits.max_q_Pa, qalpha_limit=limits.max_q_alpha_Pa_deg,
                             accel_limit_g=limits.max_axial_g, q_hard=True, **mission)


def evaluate(res, veh, handover_h_m: float, vertical_rise_s: float, limits: AscentLimits, dt: float = 0.5,
             around=None, **mission) -> Candidate:
    """Fly one pitch programme, with its steering solved and its pitch kick searched."""
    try:
        f = flight(res, veh, handover_h_m, vertical_rise_s, limits, **mission)
        sol = f.search(around)[0]
        r = ascent.fly(f, sol, veh.name, dt)
    except Exception as ex:                                      # noqa: BLE001 - an unusable candidate, not a bug
        return Candidate(handover_h_m, vertical_rise_s, -math.inf, False, [f"{type(ex).__name__}: {ex}"], None)
    bad = limits.check(r)
    return Candidate(handover_h_m, vertical_rise_s, -math.inf if bad else r.margin_mps, not bad, bad, r, sol)


# --------------------------------------------------------------------------- the search
def optimise(res, drag=None, atmosphere: str = "book_exponential", limits: AscentLimits | None = None,
             baseline_vertical_rise_s: float = 10.0, dt: float = 0.5,
             handover_bounds_m: tuple = (5_000.0, 80_000.0), rise_bounds_s: tuple = (3.0, 25.0),
             max_evaluations: int = 40, last_ascent_stage: int | None = None, profile: str = "auto",
             parking_altitude_m: float | None = None) -> dict:
    """Compass search on (hand-over altitude, vertical rise) for the speed in hand.

    A compass search is used rather than anything gradient-based: evaluations are discontinuous (a candidate
    can simply fail to reach orbit, or violate a limit), so only comparisons are safe.
    """
    limits = limits or AscentLimits()
    veh = tj.ascent_vehicle_from_result(res, drag, atmosphere, last_ascent_stage=last_ascent_stage)
    mission = dict(profile=profile or "auto", parking_m=parking_altitude_m or ascent.PARKING_M,
                   last_ascent_stage=last_ascent_stage)
    cache, evals = {}, 0

    def at(h, v, around=None):
        nonlocal evals
        h = min(max(h, handover_bounds_m[0]), handover_bounds_m[1])
        v = min(max(v, rise_bounds_s[0]), rise_bounds_s[1])
        c = Candidate(h, v, -math.inf, False)
        if c.key() in cache:
            return cache[c.key()]
        if evals >= max_evaluations:
            return None
        evals += 1
        c = evaluate(res, veh, h, v, limits, dt, around, **mission)
        cache[c.key()] = c
        return c

    base = at(ascent.HANDOVER_H_M, baseline_vertical_rise_s)
    best = base if base.feasible else None
    if best is None:
        for h in (80_000.0, 40_000.0, 25_000.0):
            c = at(h, baseline_vertical_rise_s)
            if c and c.feasible:
                best = c
                break
    if best is None:
        return dict(ok=False, baseline=base.summary(), best=None, sweep=[], evaluations=evals,
                    limits=_limits_dict(limits),
                    notes=["No pitch programme in the search box met the limits, so there is nothing to "
                           "optimise. The baseline's own violations are listed with it."])

    step = [20_000.0, 6.0]                                       # hand-over [m], rise [s]
    floor = [1_000.0, 0.5]
    while evals < max_evaluations and any(s > f for s, f in zip(step, floor)):
        polled = []
        for axis, s in enumerate(step):
            if s <= floor[axis]:
                continue
            for sign in (-1, +1):
                q = [best.handover_h_m, best.vertical_rise_s]
                q[axis] += sign * s
                c = at(*q, around=best.solution)
                if c:
                    polled.append(c)
        better = [c for c in polled if c.feasible and c.objective_mps > best.objective_mps + 1e-3]
        if better:
            best = max(better, key=lambda c: c.objective_mps)
        else:
            step = [s / 2.0 for s in step]

    sweep = []
    lo, hi = handover_bounds_m
    for i in range(7):
        c = evaluate(res, veh, lo + (hi - lo) * i / 6.0, best.vertical_rise_s, limits, dt, best.solution, **mission)
        if c.result is not None and c.result.converged:
            sweep.append(c.summary())
    binding = _binding_constraint(res, veh, limits, best, dt, mission, handover_bounds_m)
    gain = best.objective_mps - base.objective_mps if base.feasible else float("nan")
    return dict(ok=True, baseline=base.summary(), best=best.summary(), sweep=sweep, evaluations=evals,
                limits=_limits_dict(limits), binding=binding, speed_gain_mps=gain,
                notes=_notes(base, best, binding, limits, gain))


def _limits_dict(limits: AscentLimits) -> dict:
    return dict(max_q_Pa=limits.max_q_Pa, max_q_alpha_Pa_deg=limits.max_q_alpha_Pa_deg,
                max_axial_g=limits.max_axial_g, max_gamma_burnout_deg=limits.max_gamma_burnout_deg)


def _binding_constraint(res, veh, limits, best, dt, mission, bounds) -> dict:
    """What stops the optimiser going further: which limit it is flying on, or that nothing is gained by going on."""
    r = best.result
    on = []
    if limits.max_q_Pa and r.max_q_Pa > 0.98 * limits.max_q_Pa:
        on.append(("max-q", f"dynamic pressure is at {r.max_q_Pa/1e3:,.1f} kPa of the {limits.max_q_Pa/1e3:,.1f} kPa limit"))
    qa = max_q_alpha(r)
    if limits.max_q_alpha_Pa_deg and qa > 0.98 * limits.max_q_alpha_Pa_deg:
        on.append(("q.alpha", f"q.alpha is at {qa/1e3:,.0f} of the {limits.max_q_alpha_Pa_deg/1e3:,.0f} kPa.deg limit"))
    if limits.max_axial_g and r.max_accel_g > 0.98 * limits.max_axial_g:
        on.append(("axial acceleration", f"axial acceleration is at {r.max_accel_g:.2f} of the {limits.max_axial_g:.2f} g limit"))
    if on:
        return dict(name=" + ".join(n for n, _ in on), detail="; ".join(d for _, d in on))
    if best.handover_h_m <= bounds[0] + 1e-6 or best.handover_h_m >= bounds[1] - 1e-6:
        return dict(name="search box", detail=f"the hand-over altitude is at the {best.handover_h_m/1e3:,.0f} km edge of "
                                              f"the search, not on a limit")
    probe = evaluate(res, veh, max(best.handover_h_m - 2_000.0, bounds[0]), best.vertical_rise_s, limits, dt,
                     best.solution, **mission)
    if probe.violations:
        return dict(name=probe.violations[0].split()[0], detail=probe.violations[0])
    return dict(name="none", detail="going further gave no further gain, so no limit is binding here")


def _notes(base, best, binding, limits, gain) -> list:
    out = []
    if not any([limits.max_q_Pa, limits.max_q_alpha_Pa_deg, limits.max_axial_g]):
        out.append("No vehicle limits were given, so this is an UNCONSTRAINED optimum: the search will push the "
                   "vehicle as far into the atmosphere as the box allows, which is the book's trajectory B and "
                   "is not a design. Set the dynamic pressure, q.alpha and axial acceleration limits.")
    else:
        out.append(f"What stops it: {binding.get('detail', '')} (book Sec. 6.10: get horizontal early to save gravity "
                   f"loss, but not so early that drag, air loads and heating pay for it).")
    b, o = base.summary(), best.summary()
    def moved(key, label):
        d = o[key] - b[key]
        return f"{label} {'up' if d > 0 else 'down'} {abs(d):,.0f} m/s"
    out.append("Between the baseline and the optimum: " + ", ".join(
        moved(k, lab) for k, lab in (("gravity_loss_mps", "gravity loss"), ("steering_loss_mps", "steering loss"),
                                     ("drag_loss_mps", "drag loss"))) +
               f". The net is {gain:+,.0f} m/s of speed in hand.")
    out.append(f"max-q goes from {b['max_q_Pa']/1e3:,.1f} to {o['max_q_Pa']/1e3:,.1f} kPa and q.alpha from "
               f"{b['max_q_alpha_Pa_deg']/1e3:,.0f} to {o['max_q_alpha_Pa_deg']/1e3:,.0f} kPa.deg, which is "
               f"what the extra speed is bought with.")
    return out


# --------------------------------------------------------------------------- what the speed is worth
def payload_for_programme(res, handover_h_m: float, vertical_rise_s: float, limits: AscentLimits | None = None,
                          drag=None, atmosphere: str = "book_exponential", tol_kg: float = 25.0, max_iter: int = 12,
                          last_ascent_stage: int | None = None, profile: str = "auto",
                          parking_altitude_m: float | None = None, around=None) -> dict:
    """Payload this pitch programme delivers, by flying the vehicle heavier until the speed in hand is gone.

    Everything but the payload is frozen: the same stages, the same propellant loads, the same burn times. Only
    the mass at lift-off changes, which is what a performance trade on a built vehicle means.
    """
    limits = limits or AscentLimits()
    mission = dict(profile=profile or "auto", parking_m=parking_altitude_m or ascent.PARKING_M,
                   last_ascent_stage=last_ascent_stage)
    base_veh = tj.ascent_vehicle_from_result(res, drag, atmosphere, last_ascent_stage=last_ascent_stage)
    near = around

    def margin(dm):
        nonlocal near
        veh = replace(base_veh, m0_kg=base_veh.m0_kg + dm)
        c = evaluate(res, veh, handover_h_m, vertical_rise_s, limits, 0.5, near, **mission)
        if c.result is None or not c.result.converged:
            return -math.inf
        near = c.solution
        return c.result.margin_mps

    m0 = margin(0.0)
    if m0 == -math.inf:
        return dict(ok=False, reason="the vehicle does not reach the orbit on this programme at its design "
                                     "payload, so there is no capability to report")
    if m0 < 0:
        return dict(ok=False, reason=f"the flown ascent falls {-m0:,.0f} m/s short of the orbit at the design "
                                     f"payload, so this programme delivers less than the design payload")
    lo, hi, flo, fhi = 0.0, max(0.1 * res.payload_mass_kg, 100.0), m0, None
    while True:
        fhi = margin(hi)
        if fhi < 0:
            break
        lo, flo = hi, fhi
        hi *= 2.0
        if hi > 20.0 * max(res.payload_mass_kg, 1.0):
            return dict(ok=False, reason="could not bracket the payload: the surplus speed is larger than this "
                                         "frozen-vehicle trade can meaningfully extrapolate")
    for k in range(max_iter):
        # false position where both ends flew, kept off the ends; bisection otherwise
        frac = flo / (flo - fhi) if fhi > -math.inf else 0.5
        mid = lo + (hi - lo) * min(max(frac, 0.05), 0.95)
        m = margin(mid)
        if m > 0:
            lo, flo = mid, m
        else:
            hi, fhi = mid, m
        if hi - lo < tol_kg or abs(m) < 0.5:
            break
    dm = mid if abs(m) < 0.5 else 0.5 * (lo + hi)
    return dict(ok=True, payload_kg=res.payload_mass_kg + dm, surplus_payload_kg=dm,
                design_payload_kg=res.payload_mass_kg, surplus_speed_mps=m0)


def optimise_and_price(res, drag=None, atmosphere: str = "book_exponential", limits: AscentLimits | None = None,
                       dt: float = 0.5, max_evaluations: int = 40, vertical_rise_s: float = 10.0,
                       last_ascent_stage: int | None = None, profile: str = "auto",
                       parking_altitude_m: float | None = None) -> dict:
    """The whole study: optimise the programme, then price the baseline and the optimum in payload."""
    mission = dict(last_ascent_stage=last_ascent_stage, profile=profile, parking_altitude_m=parking_altitude_m)
    out = optimise(res, drag, atmosphere, limits, baseline_vertical_rise_s=vertical_rise_s, dt=dt,
                   max_evaluations=max_evaluations, **mission)
    if not out.get("ok"):
        return out
    b, o = out["baseline"], out["best"]
    out["payload_baseline"] = payload_for_programme(res, b["handover_h_m"], b["vertical_rise_s"], limits, drag,
                                                    atmosphere, **mission)
    out["payload_optimum"] = payload_for_programme(res, o["handover_h_m"], o["vertical_rise_s"], limits, drag,
                                                   atmosphere, **mission)
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
