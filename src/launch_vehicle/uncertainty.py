"""Monte-Carlo over the mass-estimating relationships (roadmap R3).

Why this exists. The single biggest error in a conceptual mass estimate is not arithmetic, it is the MERs: they
are fits to a historical population, and an individual vehicle sits somewhere in that population's scatter. This
tool's own validation puts the median GLOM error against twelve real vehicles at 17 %. Reporting "GLOM
410,003 kg" to the kilogram against that background is false precision, and a designer who reads the number
without the band will size a pad, a transporter or a contract to it.

What it does. Each MER coefficient gets a relative 1-sigma (config/engineering_assumptions.yaml -> mer_scatter,
all ASSUMED and labelled as such). A sample draws a multiplier for each group from a log-normal distribution with
that sigma - log-normal because a mass coefficient is positive and multiplicative, so a 20 % overshoot and a 20 %
undershoot should be equally likely in ratio, not in difference - applies them as overrides, and re-sizes the
vehicle from scratch. The outcome is the distribution of GLOM, dry mass and length, plus a one-at-a-time
sensitivity that says which coefficient the answer actually depends on.

What it is not. The sigmas are engineering judgement, not measured statistics: nobody has published a covariance
for Table 8.8. The interval is "how wrong this method could be", not a probability. Correlations between
coefficients are not modelled, which makes the spread, if anything, optimistic.
"""
from __future__ import annotations
import math
import random
import statistics

from .config_io import load_design
from .convergence import size_vehicle, SizingError
from .validation import InputError

# scatter group -> the assumption paths it scales. A group moves together: one draw per group, not per
# coefficient, because the coefficients inside a group come from the same fit.
GROUPS = {
    "engine_mass": ["assumptions.mer.engine_a", "assumptions.mer.engine_b", "assumptions.mer.engine_c",
                    "assumptions.mer.gimbal_k"],
    "thrust_structure": ["assumptions.mer.thrust_structure_k"],
    "unpressurized_structure": ["assumptions.mer.unpressurized_kg_m2", "assumptions.mer.composite_fairing_kg_m2"],
    "tank_mass": ["assumptions.mer.tank_vol_mer_kg_m3", "assumptions.mer.tank_vol_mer_lh2_kg_m3",
                  "assumptions.propellants.LOX.tank_mer_per_kg", "assumptions.propellants.RP-1.tank_mer_per_kg",
                  "assumptions.propellants.LH2.tank_mer_per_kg"],
    "avionics": ["assumptions.mer.avionics_small_kg", "assumptions.mer.avionics_large_kg"],
    "paf": ["assumptions.mer.paf_a", "assumptions.mer.paf_b", "assumptions.mer.paf_small_payload_fraction"],
    "wiring": ["assumptions.mer.wiring_kg_per_m"],
}
# groups that are applied per stage rather than as a global assumption
PER_STAGE = {
    "solid_casing": "motor.casing_mass_fraction",
    "residual_propellant": "residual_fraction",
    "isp_delivered": "isp",
}


class UncertaintyError(RuntimeError):
    pass


def _scatter(spec) -> dict:
    sc = getattr(spec, "mer_scatter", None) or {}
    return {k: float(v) for k, v in sc.items() if isinstance(v, (int, float))}


def _overrides(spec, draws: dict) -> dict:
    """Turn per-group multipliers into the override dict load_design takes."""
    ov = {}
    base = _base_values(spec)
    for group, paths in GROUPS.items():
        f = draws.get(group)
        if f is None or f == 1.0:
            continue
        for p in paths:
            v = base.get(p)
            if isinstance(v, (int, float)):
                ov[p] = v * f
    f_case = draws.get("solid_casing")
    f_res = draws.get("residual_propellant")
    f_isp = draws.get("isp_delivered")
    for j, st in enumerate(spec.stages):
        if f_res is not None:
            ov[f"stages.{j}.residual_fraction"] = st.residual_fraction * f_res
        if f_isp is not None:
            p = st.prop_system
            ov[f"stages.{j}.{'motor' if st.is_solid else 'engine'}.isp_vac_s"] = p.isp_vac_s * f_isp
            if p.isp_sl_s is not None:
                ov[f"stages.{j}.{'motor' if st.is_solid else 'engine'}.isp_sl_s"] = p.isp_sl_s * f_isp
        if st.is_solid and f_case is not None:
            m = st.motor
            k = m.casing_mass_fraction
            if k is None:
                # the book's own k for the declared material, so the draw has something to scale
                k = {"book_steel": 0.135, "book_composite": 0.1154}.get(m.casing_mass_method)
            if k:
                ov[f"stages.{j}.motor.casing_mass_method"] = "mass_fraction"
                ov[f"stages.{j}.motor.casing_mass_fraction"] = k * f_case
    return ov


def _base_values(spec) -> dict:
    """The nominal value behind each override path, read from the spec rather than re-parsing the YAML."""
    out = {}
    for k, v in (spec.mer or {}).items():
        out[f"assumptions.mer.{k}"] = v
    for name, p in (spec.propellants or {}).items():
        out[f"assumptions.propellants.{name}.tank_mer_per_kg"] = p.tank_mer_per_kg
    return out


def _lognormal(rng: random.Random, sigma: float) -> float:
    """Multiplier with median 1 and relative 1-sigma `sigma` (positive and multiplicative, as a mass coefficient
    must be: 1.2x and 1/1.2x are equally likely)."""
    if sigma <= 0:
        return 1.0
    s = math.sqrt(math.log(1.0 + sigma ** 2))
    return math.exp(rng.gauss(-0.5 * s * s, s)) * math.exp(0.5 * s * s)


def monte_carlo(design_path: str, assumptions_path: str, n: int = 200, seed: int = 0,
                overrides: dict | None = None, progress=None, base_spec=None) -> dict:
    """Re-size the vehicle `n` times with the MER coefficients drawn from their scatter.

    Returns the samples, the percentiles, the nominal result and a one-at-a-time sensitivity. Samples that fail to
    converge are counted and reported rather than silently dropped: a design that falls apart under plausible MER
    scatter is a finding, not a nuisance.
    """
    # `base_spec` is the vehicle the other tabs show: every sample keeps its delta-v split, including one the
    # optimiser chose, so the nominal here is that vehicle and not the design file's own split
    split = None if base_spec is None else (base_spec.dv_mode, base_spec.dv_fractions, base_spec.dv_fixed)
    nominal_spec = _held(load_design(design_path, assumptions_path, overrides), None, split)
    nominal = size_vehicle(nominal_spec)
    # losses flown for every sample would take a quarter of an hour; they hardly move with the masses, so the nominal's
    # are held
    held = nominal.budget.subtotal("loss") if nominal_spec.mission.get("loss_model") == "simulated" else None
    sig = _scatter(nominal_spec)
    if not sig:
        raise UncertaintyError("no mer_scatter block in the assumptions file: nothing to sample")
    if all(v <= 0 for v in sig.values()):
        raise UncertaintyError("every mer_scatter entry is zero, so every sample would be the nominal design: "
                               "give at least one coefficient a non-zero 1-sigma")
    rng = random.Random(seed)
    glom, dry, length, failures = [], [], [], []
    draws_log = []
    for i in range(n):
        draws = {g: _lognormal(rng, s) for g, s in sig.items()}
        ov = dict(overrides or {})
        ov.update(_overrides(nominal_spec, draws))
        try:
            r = size_vehicle(_held(load_design(design_path, assumptions_path, ov), held, split))
            if not r.converged:
                raise SizingError(r.status)
            glom.append(r.glom_kg)
            dry.append(sum(s.m_dry_kg for s in r.stages))
            length.append(r.geometry.total_length)
            draws_log.append(draws)
        except (SizingError, InputError, ValueError) as ex:
            failures.append(str(ex))
        if progress:
            progress(i + 1, n)
    # the guard is on the FAILURE fraction, not on an absolute count: a small deliberate run (n = 8, all of which
    # converge) is a legitimate request, while 30 of 200 converging means the distribution is meaningless
    need = max(3, math.ceil(0.5 * n))
    if len(glom) < need:
        raise UncertaintyError(f"only {len(glom)} of {n} samples converged; the design is too close to infeasible "
                               f"for a meaningful distribution. First failure: {failures[0] if failures else '-'}")
    qs = _quantiles(glom)
    return dict(n_requested=n, n_converged=len(glom), failures=failures[:5], n_failed=len(failures),
                nominal_glom_kg=nominal.glom_kg,
                nominal_dry_kg=sum(s.m_dry_kg for s in nominal.stages),
                nominal_length_m=nominal.geometry.total_length,
                glom_kg=glom, dry_kg=dry, length_m=length,
                mean_glom_kg=statistics.fmean(glom), sd_glom_kg=statistics.pstdev(glom),
                p05=qs[0], p50=qs[1], p95=qs[2],
                dry_p05=_quantiles(dry)[0], dry_p50=_quantiles(dry)[1], dry_p95=_quantiles(dry)[2],
                sigma=dict(sig), seed=seed,
                sensitivity=one_at_a_time(design_path, assumptions_path, nominal_spec, nominal, sig, overrides, held, split),
                note="Log-normal multipliers on each MER group; sigmas are assumptions, see "
                     "config/engineering_assumptions.yaml -> mer_scatter")


def _quantiles(xs):
    s = sorted(xs)
    def q(p):
        if not s:
            return float("nan")
        k = p * (len(s) - 1)
        lo, hi = int(math.floor(k)), int(math.ceil(k))
        return s[lo] + (s[hi] - s[lo]) * (k - lo)
    return q(0.05), q(0.50), q(0.95)


def _held(spec, loss_mps, split=None):
    if loss_mps is not None:
        spec.mission["simulated_loss_mps"] = loss_mps
    if split is not None and len(spec.stages) >= 2:
        import copy
        spec.dv_mode, spec.dv_fractions, spec.dv_fixed = split[0], copy.deepcopy(split[1]), copy.deepcopy(split[2])
        spec.optimise_dv = False
    return spec


def one_at_a_time(design_path, assumptions_path, spec, nominal, sig: dict, overrides=None, held=None, split=None) -> list:
    """Move each group by +1 sigma on its own and record what GLOM does - the tornado behind the histogram."""
    out = []
    for group, s in sig.items():
        if s <= 0:
            continue
        ov = dict(overrides or {})
        ov.update(_overrides(spec, {group: 1.0 + s}))
        if not ov:
            continue
        try:
            r = size_vehicle(_held(load_design(design_path, assumptions_path, ov), held, split))
            d = (r.glom_kg - nominal.glom_kg) / nominal.glom_kg if r.converged else float("nan")
        except (SizingError, InputError, ValueError):
            d = float("nan")
        out.append(dict(parameter=group, sigma=s, d_glom_per_sigma=d))
    return sorted([o for o in out if o["d_glom_per_sigma"] == o["d_glom_per_sigma"]],
                  key=lambda o: -abs(o["d_glom_per_sigma"]))
