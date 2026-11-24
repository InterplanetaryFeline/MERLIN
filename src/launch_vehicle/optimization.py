"""Optional optimisation mode - separate from the converged sizing solution.

Searches the stage delta-v allocation (the free design variables of a serial stack at fixed stage count,
propellants, diameters and structural model). Each objective evaluation is a full converged sizing. The
result is a LOCAL optimum inside the stated bounds; global optimality is NOT claimed. Stage count and
propellant combinations are compared by evaluating explicitly supplied configurations (compare_designs),
never by implicit search.

WHY THERE IS AN EXPLORATION PHASE, which is the part worth understanding.

The first version went straight to a local search from the equal split. On a two-stage vehicle that works.
On `examples/example_3stage_leo.yaml` it FAILED SILENTLY: the equal split does not size at all, every
neighbouring point in the simplex is equally infeasible, so the search saw a flat penalty, gave up after 11
evaluations and returned the equal split it started from - reporting it as the optimum. The GUI then wrote
that worse split into the user's design. A random multi-start finds 338,329 kg against the design's own
355,389 kg, so the answer was there to be found; nothing was looking in the right place.

The lesson is structural, not a tuning problem. A launch vehicle's feasible region in the staging simplex is
a narrow band - most splits ask some stage for more delta-v than it can carry - and a local search started
outside it has no gradient to follow, because "infeasible" is one flat value however far outside you are.
So the search now SAMPLES the simplex first, keeps the feasible points, and refines from the best of them.
That is also what the MDO literature does for the same reason (Balesdent 2011, App. B.1, measured a 10 %
success rate for a local search started at random on this problem; our own measurement is in ACCURACY.md).

OBJECTIVES are normalised before the penalties are added. The three objectives have wildly different scales
- kilograms, dollars, kilograms of payload - so a fixed penalty of 1e9 that sits above GLOM sits BELOW a
development cost, and the ordering silently inverts. Everything the search sees is divided by the baseline
value first, so a penalty of 1e3 means the same thing whatever is being minimised.
"""
from __future__ import annotations
import math
import copy
import numpy as np
from scipy.optimize import minimize_scalar, minimize
from .convergence import size_vehicle, SizingError
from .validation import InputError

PENALTY = 1e12

#: Penalties on the NORMALISED objective (value / baseline ~ 1), one per rung of the feasibility ladder, so
#: the search always prefers a feasible design to an error-carrying one and an error-carrying one to a
#: vehicle that would not size - while still ordering within each rung by the objective itself.
PENALTY_ERRORS = 1e3          # sized and converged, but validation reports an ERROR
PENALTY_NO_CONVERGE = 1e4     # sized, did not converge
PENALTY_NO_SIZE = 1e5         # refused to size at all

#: Exploration is adaptive: sample in batches until there are enough feasible points to seed the local
#: searches, then stop. An easy two-stage vehicle finds its feasible band almost immediately and should not
#: pay for two hundred sizings; a vehicle whose feasible band is narrow keeps looking until the cap. The cap
#: is what a hard case costs - 200 sizings, about 7 s - and the floor is what an easy one costs.
DEFAULT_SAMPLES = 200         # cap on exploration points
SAMPLE_BATCH = 25
ENOUGH_FEASIBLE = 12          # feasible points that make further sampling unlikely to change the answer
DEFAULT_STARTS = 4
DEFAULT_SEED = 20260101

OBJECTIVES = ("glom", "cost", "payload")


def _glom(spec, fractions):
    """GLOM for one allocation, or PENALTY. Kept for `staging_sweep` and `glom_for_fractions`, which want a
    single number per point and do not care about the feasibility ladder."""
    ev = evaluate(spec, fractions, "glom")
    return ev["glom_kg"] if ev["rung"] == 0 and ev["glom_kg"] else PENALTY


def _sized(spec, fractions):
    """Size the vehicle for one delta-v allocation. Returns the result, or None if it would not size."""
    s = copy.deepcopy(spec)
    s.dv_mode, s.dv_fractions, s.dv_fixed = "fractions", list(fractions), None
    try:
        return size_vehicle(s, keep_history=False)
    except (SizingError, InputError):
        return None


def _cost_usd(res) -> float | None:
    """DEVELOPMENT cost, and deliberately not cost per flight.

    The development CERs are mass-driven (Fig. 17.16, effort ~ dry mass^0.555 per stage) and respond to the split.
    The cost per flight now responds too, but it also depends on launch rate and production run, which are
    assumptions rather than properties of the vehicle, so development is what `cost` means here.

    Worth knowing before choosing it: the development-cost optimum is NOT the GLOM optimum. On the shipped
    default, minimum GLOM is near a 35/65 split and minimum development cost near 53/47, because the sum of
    per-element powers of mass is not minimised by minimising the total. That is a real trade, not an error.
    """
    from . import cost as _cost
    try:
        return float(_cost.estimate(res).development_usd) or None
    except Exception:                                        # noqa: BLE001 - costing must not kill a search
        return None


def _payload_at_glom_cap(spec, fractions, cap_kg: float, tol_kg: float = 1.0, max_iter: int = 24):
    """The largest payload this allocation can carry without the vehicle exceeding `cap_kg` of lift-off mass.

    GLOM rises monotonically with payload at a fixed allocation, so a bisection is enough. This is what
    "maximise payload" has to mean here: the tool sizes a vehicle TO a payload, so payload is only a free
    quantity once something else is held fixed, and the honest thing to hold fixed is the lift-off mass.
    """
    lo_p, hi_p = 0.0, max(spec.payload_mass_kg * 4.0, 1.0)
    best = None
    r0 = _sized(_with_payload(spec, hi_p), fractions)
    if r0 is not None and r0.converged and r0.glom_kg <= cap_kg:
        return hi_p, r0                                      # the cap does not bind inside the bracket
    for _ in range(max_iter):
        mid = 0.5 * (lo_p + hi_p)
        r = _sized(_with_payload(spec, mid), fractions)
        if r is not None and r.converged and r.glom_kg <= cap_kg:
            best, lo_p = (mid, r), mid
        else:
            hi_p = mid
        if hi_p - lo_p < tol_kg:
            break
    return best if best else (None, None)


def _with_payload(spec, payload_kg: float):
    s = copy.deepcopy(spec)
    s.payload_mass_kg = float(payload_kg)
    return s


def evaluate(spec, fractions, objective: str = "glom", glom_cap_kg: float | None = None) -> dict:
    """One point of the search: size the vehicle and say how good and how legal it is.

    `rung` is the feasibility ladder - 0 feasible, 1 sized with validation ERRORs, 2 did not converge, 3
    would not size - and `value` is the quantity being MINIMISED (payload is negated). Both are reported
    raw; the normalisation and the penalties happen in the search, which knows the baseline.
    """
    if objective not in OBJECTIVES:
        raise InputError(f"objective must be one of {OBJECTIVES}, not {objective!r}")

    if objective == "payload":
        if not glom_cap_kg:
            raise InputError("maximising payload needs a lift-off mass to hold it under (glom_cap_kg)")
        payload, res = _payload_at_glom_cap(spec, fractions, glom_cap_kg)
        if res is None:
            return dict(fractions=list(fractions), rung=3, value=None, glom_kg=None, payload_kg=None,
                        cost_usd=None, errors=[], why="no payload at all fits under the lift-off mass cap")
        errs = [i for i in res.issues if i.level == "ERROR"]
        return dict(fractions=list(fractions), rung=1 if errs else 0, value=-payload,
                    glom_kg=res.glom_kg, payload_kg=payload, cost_usd=None,
                    errors=[f"{i.code}: {i.message}" for i in errs],
                    why="" if not errs else f"{len(errs)} validation error(s)")

    res = _sized(spec, fractions)
    if res is None:
        return dict(fractions=list(fractions), rung=3, value=None, glom_kg=None, payload_kg=None,
                    cost_usd=None, errors=[], why="the vehicle would not size")
    if not res.converged:
        return dict(fractions=list(fractions), rung=2, value=None, glom_kg=res.glom_kg, payload_kg=None,
                    cost_usd=None, errors=[], why="the sizing loop did not converge")
    errs = [i for i in res.issues if i.level == "ERROR"]
    value = res.glom_kg if objective == "glom" else _cost_usd(res)
    if value is None:
        return dict(fractions=list(fractions), rung=2, value=None, glom_kg=res.glom_kg, payload_kg=None,
                    cost_usd=None, errors=[], why="the cost model could not price this vehicle")
    return dict(fractions=list(fractions), rung=1 if errs else 0, value=value, glom_kg=res.glom_kg,
                payload_kg=spec.payload_mass_kg, cost_usd=value if objective == "cost" else None,
                errors=[f"{i.code}: {i.message}" for i in errs],
                why="" if not errs else f"{len(errs)} validation error(s)")


def _simplex_samples(n_stages: int, n: int, lo: float, hi: float, rng) -> list:
    """Points spread over the allocation simplex, inside the per-stage bounds.

    A Dirichlet(1,...,1) draw is uniform on the simplex, which is what "sample the possibilities" should
    mean. Draws that fall outside [lo, hi] on any stage are redrawn rather than clipped, because clipping
    piles samples up on the bound and makes the edge look more interesting than it is.
    """
    out, guard = [], 0
    while len(out) < n and guard < 60 * n:
        guard += 1
        f = rng.dirichlet(np.ones(n_stages))
        if all(lo <= x <= hi for x in f):
            out.append([float(x) for x in f])
    return out


def _to_simplex(v, n_stages: int) -> list:
    e = np.exp(np.clip(v, -6, 6))
    return [float(x) for x in np.append(e, 1.0) / (e.sum() + 1.0)]


def _from_simplex(fr) -> np.ndarray:
    f = np.clip(np.asarray(fr, dtype=float), 1e-9, None)
    return np.log(f[:-1] / f[-1])


def optimize_dv_split(spec, lo: float = 0.05, hi: float = 0.95, objective: str = "glom",
                      samples: int = DEFAULT_SAMPLES, starts: int = DEFAULT_STARTS,
                      seed: int = DEFAULT_SEED, glom_cap_kg: float | None = None) -> dict:
    """Search the stage delta-v allocation for the best `objective`.

    Explore then refine: sample the simplex, keep what is feasible, run a local search from the best few.
    The spread across those searches is reported rather than hidden, because it is the only honest evidence
    about whether the answer is a local optimum or THE optimum, and this returns a local one.
    """
    N = len(spec.stages)
    if N == 1:
        raise InputError("nothing to optimise for a single stage")
    if objective not in OBJECTIVES:
        raise InputError(f"objective must be one of {OBJECTIVES}, not {objective!r}")
    rng = np.random.default_rng(seed)

    # Maximising payload is only meaningful with something held fixed, and the honest thing to hold fixed is
    # the lift-off mass the design already has: "the same rocket, carrying as much as it can". Settle that
    # BEFORE the baseline is evaluated, because the baseline evaluation needs it too.
    if objective == "payload" and not glom_cap_kg:
        base_sized = _sized(spec, list(spec.dv_fractions)) if spec.dv_fractions else None
        glom_cap_kg = base_sized.glom_kg if base_sized is not None else None
        if not glom_cap_kg:
            raise InputError("maximising payload needs a lift-off mass cap, and the current design does not "
                             "size, so there is no mass to hold it to. Give glom_cap_kg explicitly.")

    # the design as it stands, which is both the thing to beat and the scale everything is measured in
    baseline = evaluate(spec, list(spec.dv_fractions), objective, glom_cap_kg) \
        if spec.dv_mode == "fractions" and spec.dv_fractions else None

    n_eval = 0

    def look(fr):
        nonlocal n_eval
        n_eval += 1
        return evaluate(spec, fr, objective, glom_cap_kg)

    # ---- explore: find the feasible band before trying to walk down it, in batches so that an easy
    # vehicle stops early and a hard one keeps looking up to the cap
    seen = [baseline] if baseline else []
    feasible = [e for e in seen if e["rung"] == 0 and e["value"] is not None]
    drawn = 0
    while drawn < samples and len(feasible) < ENOUGH_FEASIBLE:
        batch = min(SAMPLE_BATCH, samples - drawn)
        pts = _simplex_samples(N, batch, lo, hi, rng)
        if not pts:
            break
        drawn += len(pts)
        for f in pts:
            e = look(f)
            seen.append(e)
            if e["rung"] == 0 and e["value"] is not None:
                feasible.append(e)
    if not feasible:
        why = {}
        for e in seen:
            why[e["why"]] = why.get(e["why"], 0) + 1
        return dict(fractions=list(spec.dv_fractions) if spec.dv_fractions else [1.0 / N] * N,
                    glom_kg=None, baseline_glom_kg=(baseline or {}).get("glom_kg"), evaluations=n_eval,
                    success=False, objective=objective, starts=[], spread_rel=None, active_constraints=[],
                    note=("No allocation of the delta-v between these stages produces a vehicle that sizes, "
                          f"out of {len(seen)} tried. This is not a search that failed - it is a vehicle "
                          "that cannot fly this mission as specified. "
                          + "; ".join(f"{v}x {k}" for k, v in sorted(why.items(), key=lambda kv: -kv[1]))))

    # the scale everything is judged on: the baseline if it is usable, otherwise the best sample
    ref = abs(baseline["value"]) if (baseline and baseline["rung"] == 0 and baseline["value"]) \
        else abs(min(feasible, key=lambda e: e["value"])["value"])
    ref = ref or 1.0

    def scalar(v):
        e = look(_to_simplex(v, N))
        if e["rung"] == 0:
            return e["value"] / ref
        rung_penalty = {1: PENALTY_ERRORS, 2: PENALTY_NO_CONVERGE, 3: PENALTY_NO_SIZE}[e["rung"]]
        # still ordered by the objective within a rung where there is one, so the search can climb back out
        return rung_penalty + (e["value"] / ref if e["value"] is not None else 0.0)

    # ---- refine: a local search from each of the best few feasible samples
    feasible.sort(key=lambda e: e["value"])
    seeds, used = [], []
    for e in feasible:
        if any(np.allclose(e["fractions"], s, atol=0.02) for s in used):
            continue                                        # do not spend a start on a near-duplicate
        used.append(e["fractions"])
        seeds.append(e)
        if len(seeds) >= max(1, starts):
            break

    runs = []
    for e in seeds:
        res = minimize(scalar, _from_simplex(e["fractions"]), method="Nelder-Mead",
                       options=dict(xatol=1e-4, fatol=1e-4, maxiter=400))
        fr = _to_simplex(res.x, N)
        got = look(fr)
        if got["rung"] == 0 and got["value"] is not None:
            runs.append(got)
        else:
            runs.append(e)                                  # the search wandered out; keep where it started

    best = min(runs + feasible, key=lambda e: e["value"])
    vals = sorted(r["value"] for r in runs)
    spread = (vals[-1] - vals[0]) / abs(vals[0]) if len(vals) > 1 and vals[0] else 0.0

    # ---- what the optimum is pressed against, which is the engineering answer: a number alone does not
    # tell you what to change. Reported as a DIFFERENCE against the design the user started from, because
    # the warnings a design already carried are properties of that design and not of the optimisation -
    # listing them here would bury the one new constraint under housekeeping the user has already seen.
    final = _sized(spec if objective != "payload" else _with_payload(spec, best["payload_kg"]),
                   best["fractions"])
    base_codes = set()
    if baseline:
        b = _sized(spec, list(spec.dv_fractions)) if spec.dv_fractions else None
        if b is not None:
            base_codes = {i.code for i in b.issues if i.level in ("ERROR", "WARNING")}
    active = []
    if final is not None:
        active = [f"{i.code}: {i.message}" for i in final.issues
                  if i.level in ("ERROR", "WARNING") and i.code not in base_codes][:8]

    base_val = baseline["value"] if (baseline and baseline["value"] is not None) else None
    gain = (base_val - best["value"]) / abs(base_val) if base_val else None
    return dict(
        fractions=best["fractions"],
        glom_kg=best["glom_kg"],
        baseline_glom_kg=(baseline or {}).get("glom_kg"),
        objective=objective,
        objective_value=best["value"] if objective != "payload" else -best["value"],
        baseline_objective_value=(base_val if objective != "payload" or base_val is None else -base_val),
        payload_kg=best.get("payload_kg"),
        cost_usd=best.get("cost_usd"),
        improvement_rel=gain,
        evaluations=n_eval,
        feasible_samples=len(feasible),
        samples=len(seen),
        starts=[r["value"] if objective != "payload" else -r["value"] for r in runs],
        spread_rel=spread,
        active_constraints=active,
        success=True,
        note=(f"Local optimum of {objective} over the stage delta-v allocation, from {len(seeds)} start(s) "
              f"chosen out of {len(feasible)} feasible points in {len(seen)} sampled. Stage count, "
              f"propellants, diameters and the structural model are fixed. "
              + (f"The {len(runs)} searches agreed to within {100 * spread:.2f} %. " if len(runs) > 1 else "")
              + "This is a local optimum, not a global one."))


def apply_optimum(spec, **kw):
    """If this design asks to be optimised, return a copy whose delta-v split IS the optimum.

    WHY THIS EXISTS. The optimiser used to run as a study: the report printed an optimal split and the GLOM
    it would give, next to a vehicle sized from the user's own split. Two different rockets in one document,
    and the better one existed only as a footnote - to act on it you had to read the number off the report
    and type it back into the design by hand. Anyone who did not do that was reading a lift-off mass for a
    staging decision the report had already told them was not the best one.

    With `vehicle.optimise_dv_split` set, the allocation is replaced BEFORE sizing, so the mass, the
    geometry, the loads, the drawing and the cost all describe the same vehicle as the split that is shown.
    The user's own split is not lost - it is returned in the note as `was`, and the design file on disk is
    untouched until they save.

    Returns (spec_to_size, note_or_None). The note is what the interface tells the user, because silently
    changing someone's staging decision would be worse than not offering the option at all.
    """
    if not getattr(spec, "optimise_dv", False):
        return spec, None
    if len(spec.stages) < 2:
        return spec, {"applied": False, "why": "a single-stage vehicle has no allocation to optimise"}
    objective = getattr(spec, "optimise_objective", "glom") or "glom"
    try:
        out = optimize_dv_split(spec, objective=objective, **kw)
    except InputError as ex:
        return spec, {"applied": False, "why": str(ex)}
    if not out.get("success"):
        return spec, {"applied": False, "why": out.get("note", "the search found no feasible allocation"),
                      "objective": objective}
    was = list(spec.dv_fractions) if spec.dv_fractions else None
    s = copy.deepcopy(spec)
    s.dv_mode, s.dv_fractions, s.dv_fixed = "fractions", list(out["fractions"]), None
    pct = lambda fr: " / ".join(f"{100 * x:.1f} %" for x in fr)                           # noqa: E731
    gain = out.get("improvement_rel")
    note = {"applied": True, "objective": objective, "was": was, "now": list(out["fractions"]),
            "improvement_rel": gain, "result": out,
            "why": (f"the delta-v split was optimised for {objective} before sizing: "
                    + (f"{pct(was)} -> " if was else "") + pct(out["fractions"])
                    + (f", {100 * gain:+.2f} %" if gain else "")
                    + ". This design file is unchanged until you save it.")}
    return s, note


def compare_designs(specs: dict) -> list:
    rows = []
    for name, sp in specs.items():
        try:
            r = size_vehicle(sp, keep_history=False)
            rows.append(dict(name=name, glom_kg=r.glom_kg, converged=r.converged, feasible=not any(i.level == "ERROR" for i in r.issues),
                             length_m=r.geometry.total_length, dv_req=r.dv_required_mps))
        except (SizingError, InputError) as ex:
            rows.append(dict(name=name, glom_kg=float("nan"), converged=False, feasible=False, length_m=float("nan"), dv_req=float("nan"), note=str(ex)))
    return rows


# --------------------------------------------------------------------------- analytical optimum (book Sec. 5.8)
def analytical_optimum(c_eff_mps: list, sigma: list, dv_total_mps: float, tol: float = 1e-10) -> dict:
    """Book Eqs. 5:30-5:33 (pp.287-288): the Lagrange-multiplier optimum of the step mass ratios.

    The book writes mu_i = (1 + L c_i)/(L c_i sigma_i) with a Lagrange multiplier L that comes out negative;
    substituting lam = -L gives the equivalent positive form used here,

        mu_i = (lam c_i - 1) / (lam c_i sigma_i),        v_f = sum_i c_i ln mu_i,

    which is solved for lam by bisection. mu_i > 1 requires lam > 1/(c_i (1 - sigma_i)), so the search starts just
    above the largest of those bounds; mu_i < 1/sigma_i holds automatically, i.e. the optimum is always feasible.

    This is the *unrestricted* staging optimum: it assumes each step's structural ratio sigma_i and effective
    exhaust speed c_i are fixed and independent of its size. In this tool they are not - sigma comes out of a
    mass build-up that depends on the stage's own size - so the analytical answer is a cross-check and a first
    guess, not a replacement for the numerical search (see optimize_dv_split).
    """
    n = len(c_eff_mps)
    if n != len(sigma) or n < 2:
        raise InputError("analytical staging optimum needs at least two steps with matching c and sigma")
    if any(s <= 0 or s >= 1 for s in sigma):
        raise InputError("structural ratios must lie strictly between 0 and 1")
    lam_lo = max(1.0 / (c * (1.0 - s)) for c, s in zip(c_eff_mps, sigma)) * (1.0 + 1e-12)

    def dv_of(lam):
        tot = 0.0
        for c, s in zip(c_eff_mps, sigma):
            mu = (lam * c - 1.0) / (lam * c * s)
            if mu <= 1.0:
                return -1.0
            tot += c * math.log(mu)
        return tot

    lam_hi = lam_lo * 2.0
    for _ in range(200):
        if dv_of(lam_hi) > dv_total_mps:
            break
        lam_hi *= 2.0
    else:
        raise InputError("no Lagrange multiplier reaches the required delta-v with these structural ratios")
    lo, hi = lam_lo, lam_hi
    for _ in range(300):
        mid = 0.5 * (lo + hi)
        if dv_of(mid) < dv_total_mps:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol * max(1.0, hi):
            break
    lam = 0.5 * (lo + hi)
    mus = [(lam * c - 1.0) / (lam * c * s) for c, s in zip(c_eff_mps, sigma)]
    dvs = [c * math.log(mu) for c, mu in zip(c_eff_mps, mus)]
    tot = sum(dvs)
    return dict(lagrange_lambda=lam, lagrange_L=-lam, mass_ratios=mus, dv_mps=dvs,
                fractions=[d / tot for d in dvs], dv_total_mps=tot,
                note="Book Eqs. 5:32-5:33 (pp.288). Valid for fixed sigma_i and c_i; sigma here is the converged "
                     "structural factor of each stage, so the result is a cross-check on the numerical optimum.")


def analytical_optimum_from_result(res) -> dict:
    """Apply the book's analytical optimum to a converged design, using its own c_eff and structural factors."""
    from .units import G0
    c = [G0 * s.isp_eff_s for s in res.stages]
    sig = [s.structural_factor_s for s in res.stages]
    out = analytical_optimum(c, sig, res.dv_required_mps)
    out["c_eff_mps"] = c
    out["sigma"] = sig
    return out


def equal_isp_optimum(c_eff_mps: float, sigma: list, dv_total_mps: float) -> dict:
    """Book Eqs. 5:36-5:39: the closed form when every step has the same exhaust speed.

    mu_i = (1/sigma_i) exp[-(1/N)(v_f/c + sum_j ln sigma_j)] ... rearranged from the printed form; with equal
    sigma it reduces to the familiar 'each step provides v_f/N' (restricted staging, p.289).
    """
    n = len(sigma)
    k = math.exp((dv_total_mps / c_eff_mps + sum(math.log(s) for s in sigma)) / n)
    mus = [k / s for s in sigma]
    dvs = [c_eff_mps * math.log(mu) for mu in mus]
    tot = sum(dvs)
    return dict(mass_ratios=mus, dv_mps=dvs, fractions=[d / tot for d in dvs], dv_total_mps=tot,
                note="Book Eqs. 5:37-5:39 (p.289); equal exhaust speed for every step")


def glom_for_fractions(spec, fractions) -> float | None:
    """GLOM of a design whose delta-v is split in the given proportions, or None when that split is infeasible.

    Used to price the analytical optimum inside this tool's own model: the closed form assumes fixed structural
    ratios, so its split has to be re-sized here before its mass can be compared with anything.
    """
    g = _glom(spec, list(fractions))
    return None if g >= PENALTY else g


def restricted_staging_speed_ratio(n_steps: int, payload_ratio: float, sigma: float) -> float:
    """Book Eq. 5:40 (p.289): normalised burnout speed of a vehicle of N *similar* steps (restricted staging).

        v_f / v_e = N ln[ 1 / (pi^(1/N) (1 - sigma) + sigma) ],   and  (1 - sigma) ln(1/pi)  as N -> infinity.

    This is the curve behind the book's Fig. 5.11 and the honest answer to "is another step worth it": the gain
    per added step collapses after three or four. `n_steps=None` returns the infinite-step limit.
    """
    if payload_ratio <= 0 or payload_ratio >= 1:
        raise InputError("payload ratio must lie strictly between 0 and 1")
    if sigma <= 0 or sigma >= 1:
        raise InputError("structural ratio must lie strictly between 0 and 1")
    if n_steps is None:
        return (1.0 - sigma) * math.log(1.0 / payload_ratio)
    if n_steps < 1:
        raise InputError("a vehicle has at least one step")
    return n_steps * math.log(1.0 / (payload_ratio ** (1.0 / n_steps) * (1.0 - sigma) + sigma))


def staging_sweep(spec, n: int = 25, lo: float = 0.15, hi: float = 0.9) -> list:
    """GLOM against the share of delta-v given to stage 1 (two-stage vehicles only) - the curve behind the
    optimum, so a reader can see how flat or sharp it is."""
    if len(spec.stages) != 2:
        return []
    out = []
    for k in range(n):
        f1 = lo + (hi - lo) * k / (n - 1)
        g = _glom(spec, [f1, 1.0 - f1])
        if g < PENALTY:
            out.append(dict(f1=f1, glom_kg=g))
    return out
