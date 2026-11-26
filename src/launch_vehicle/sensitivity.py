"""One-at-a-time sensitivity and configuration-comparison studies.

All cases share the base mission requirement and assumptions; only the named parameter(s) change. When a delta-v loss is
varied it is varied inside the same budget (no extra margin or equipment appears in one case only).
Infeasible cases are reported, never dropped.

Every case is the BASE VEHICLE with one thing changed. The base is the result the user is looking at, so the cases
carry the same overrides and the same delta-v split it was sized with - including a split the optimiser replaced
before sizing, which is held fixed rather than re-optimised for each case. Until v1.3.1 each case was re-read from the
design file alone, so on an optimised design or one with unsaved edits the 0 % case was a different vehicle from the
baseline every delta was measured against.

The ranges are set about the design point - payload, diameter and the margins as steps either side of the design's own
value, and densities only for the propellants this vehicle carries - because fixed ranges (a 5 to 15 t payload, a
3.4 to 5 m first stage, RP-1 and LOX) described a medium launcher whatever design was open.
"""
from __future__ import annotations
import copy
from .config_io import load_design
from .convergence import size_vehicle, SizingError
from .validation import InputError

#: the relative steps either side of the design point for a quantity that scales: payload, diameter, density
STEPS = (-0.20, -0.10, -0.05, 0.0, 0.05, 0.10, 0.20)
#: the tank-mass relationships a liquid stage can use, in the order the book presents them
TANK_METHODS = (("akin_propellant_mass", "Table 8.6 (propellant-mass MER)"), ("akin_volume", "Table 8.7 (volume MER)"),
                ("mass_fraction", "Mass fraction (assumed 1.5% / 1.1%)"),
                ("pressure_vessel", "Pressure vessel, 3 bar (membrane only)"))


def _row(study, label, value, res=None, err=None, base_glom=None, design_point=False):
    if res is None:
        return dict(study=study, case=label, value=value, converged=False, feasible=False, status=f"infeasible: {err}",
                    design_point=design_point)
    prop = sum(s.m_prop_loaded_kg for s in res.stages)
    errs = [i for i in res.issues if i.level == "ERROR"]
    row = dict(study=study, case=label, value=value, glom_kg=res.glom_kg,
               delta_glom_pct=None if base_glom is None else 100 * (res.glom_kg / base_glom - 1),
               prop_total_kg=prop, dry_total_kg=sum(s.m_dry_kg for s in res.stages),
               payload_fraction=res.payload_mass_kg / res.glom_kg, prop_fraction=prop / res.glom_kg,
               length_m=res.geometry.total_length, dv_req_mps=res.dv_required_mps, dv_margin_mps=res.dv_achieved_mps - res.dv_required_mps,
               converged=res.converged, feasible=not errs, status=res.status if not errs else "; ".join(i.code for i in errs),
               design_point=design_point)
    for s in res.stages:
        row[f"dry_s{s.index}_kg"] = s.m_dry_kg
        row[f"len_s{s.index}_m"] = s.length_m
    return row


def _case_spec(design, assump, ov, base_overrides, base_spec):
    """The base vehicle with `ov` on top: the same overrides, and the delta-v split the base was sized with."""
    sp = load_design(design, assump, {**(base_overrides or {}), **ov} or None)
    if base_spec is not None and len(sp.stages) == len(base_spec.stages):
        sp.dv_mode = base_spec.dv_mode
        sp.dv_fractions = copy.deepcopy(base_spec.dv_fractions)
        sp.dv_fixed = copy.deepcopy(base_spec.dv_fixed)
        sp.optimise_dv = False
    return sp


def run_cases(design, assump, study, cases, base_glom=None, base_overrides=None, base_res=None) -> list:
    """Size each case. A case is (label, value, overrides), or (label, value, overrides, True) for the design point,
    which is the base result itself rather than a second sizing of it."""
    out = []
    base_spec = base_res.spec if base_res is not None else None
    for case in cases:
        label, value, ov = case[:3]
        here = len(case) > 3 and case[3]
        if here and base_res is not None:
            out.append(_row(study, label, value, base_res, base_glom=base_glom, design_point=True))
            continue
        try:
            sp = _case_spec(design, assump, ov, base_overrides, base_spec)
            out.append(_row(study, label, value, size_vehicle(sp, keep_history=False), base_glom=base_glom,
                            design_point=here))
        except (SizingError, InputError, ValueError) as ex:
            out.append(_row(study, label, value, err=str(ex), design_point=here))
    return out


def _scaled(base, fmt, path_of, steps=STEPS):
    """Cases at the design value and at relative steps either side of it."""
    out = []
    for k in steps:
        v = base * (1 + k)
        tag = "design point" if k == 0 else f"{100 * k:+.0f} %"
        out.append((f"{fmt(v)} ({tag})", v, path_of(v), k == 0))
    return out


def _offsets(base, offsets, fmt, path_of, lo=0.0):
    """Cases at the design value and at absolute offsets from it, never below `lo`; repeats are dropped."""
    out, seen = [], set()
    for d in sorted(offsets, key=lambda x: x != 0):          # the design point first, so a clipped repeat is not it
        v = max(lo, base + d)
        key = round(v, 9)
        if key in seen:
            continue
        seen.add(key)
        out.append((f"{fmt(v)}" + (" (design point)" if d == 0 else ""), v, path_of(v), d == 0))
    return sorted(out, key=lambda c: c[1])


def _per_stage(spec, attr):
    """One value for every stage when they all share it, else None: a study that sets every stage to one value
    would then change more than the one thing it names."""
    vals = {round(getattr(s, attr), 9) for s in spec.stages}
    return getattr(spec.stages[0], attr) if len(vals) == 1 else None


def _shifted(spec, attr, path, offsets):
    """Offsets added to each stage's own value, so stages that differ keep their difference."""
    out, seen = [], set()
    for d in sorted(offsets, key=lambda x: x != 0):
        vals = [max(0.0, getattr(s, attr) + d) for s in spec.stages]
        key = tuple(round(v, 9) for v in vals)
        if key in seen:
            continue
        seen.add(key)
        common = _per_stage(spec, attr)
        label = (f"{max(0.0, common + d):.3f}" if common is not None else f"{d:+.3f} on every stage")
        out.append((label + (" (design point)" if d == 0 else ""), d,
                    {f"stages.{j}.{path}": v for j, v in enumerate(vals)}, d == 0))
    return sorted(out, key=lambda c: c[1])


def _liquid_propellants(spec):
    """The liquid propellants this vehicle carries, in the order they first appear."""
    names = []
    for s in spec.stages:
        if not s.is_solid:
            names += [s.fuel, s.oxidizer]
    b = spec.boosters
    if b is not None and getattr(b, "kind", "") == "liquid":
        names += [b.fuel, b.oxidizer]
    return [n for i, n in enumerate(names) if n and n in spec.propellants and n not in names[:i]]


def standard_studies(design, assump, base_res, base_overrides=None) -> list:
    """The one-at-a-time studies about `base_res`, which was sized from `design` with `base_overrides`."""
    g0 = base_res.glom_kg
    spec = base_res.spec
    N = len(spec.stages)
    liquid = [j for j, s in enumerate(spec.stages) if not s.is_solid]
    run = lambda study, cases: run_cases(design, assump, study, cases, g0, base_overrides, base_res)  # noqa: E731
    rows = []
    rows += run("Payload mass [kg]", _scaled(spec.payload_mass_kg, lambda v: f"{v:,.0f}",
                                             lambda v: {"mission.payload_mass_kg": v}))
    cases = []
    for k in (-0.05, -0.025, 0.0, 0.025, 0.05):
        ov = {}
        for j, st in enumerate(spec.stages):
            ps = st.prop_system
            root = f"stages.{j}.motor" if st.is_solid else f"stages.{j}.engine"
            ov[f"{root}.isp_vac_s"] = ps.isp_vac_s * (1 + k)
            if getattr(ps, "isp_sl_s", None):
                ov[f"{root}.isp_sl_s"] = ps.isp_sl_s * (1 + k)
        cases.append((f"{100*k:+.1f}% (all stages)" + (" (design point)" if k == 0 else ""), k, ov, k == 0))
    rows += run("Specific impulse (scale, SL & vac)", cases)
    rows += run("Structural coefficient proxy: inert mass-growth margin",
                _shifted(spec, "inert_margin_fraction", "inert_mass_margin_fraction", (-0.10, -0.05, 0.0, 0.05, 0.10)))
    base_dv = base_res.dv_required_mps
    rows += run("Mission delta-v requirement [m/s] (total override)",
                [(f"{base_dv + d:,.0f} ({d:+d})" + (" (design point)" if d == 0 else ""), base_dv + d,
                  {"mission.delta_v_override_mps": base_dv + d}, d == 0) for d in (-300, -150, 0, 150, 300)])
    m = spec.mission
    rows += run("Delta-v design margin fraction (applied once to the subtotal)",
                _offsets(float(m.get("design_margin_fraction") or 0.0), (-0.02, -0.01, 0.0, 0.01, 0.02),
                         lambda v: f"{v:.3f}", lambda v: {"mission.losses.design_margin_fraction": v}))
    rows += run("Staging/ignition delay in ascent time [s] (enters the book loss regression)",
                _offsets(float(m.get("staging_delay_s") or 0.0), (-10.0, -5.0, 0.0, 5.0, 10.0),
                         lambda v: f"{v:.0f}", lambda v: {"mission.losses.staging_delay_s": v}))
    for name in _liquid_propellants(spec):
        rho = spec.propellants[name].density_kg_m3
        rows += run(f"{name} density [kg/m3] (tank volume)",
                    _scaled(rho, lambda v: f"{v:,.0f}",
                            lambda v, n=name: {f"assumptions.propellants.{n}.density_kg_m3": v}, (-0.04, -0.02, 0.0, 0.02, 0.04)))
    if liquid:
        rows += run("Propellant loading margin (all stages)",
                    _shifted(spec, "loading_margin_fraction", "loading_margin_fraction", (-0.01, -0.005, 0.0, 0.005, 0.01)))
    rows += run("Stage-1 diameter [m]", _scaled(spec.stages[0].diameter_m, lambda v: f"{v:.2f}",
                                                lambda v: {"stages.0.diameter_m": v}))
    if liquid:
        used = {spec.stages[j].tank.mass_method.get(r) for j in liquid for r in ("fuel", "oxidizer")}
        tank_cases = [("As designed: " + ", ".join(sorted(str(u) for u in used)), 0, {}, True)]
        for i, (method, label) in enumerate(TANK_METHODS, start=1):
            if used == {method}:
                continue
            tank_cases.append((label, i, {f"stages.{j}.tank.mass_method_{r}": method for j in liquid for r in ("fuel", "oxidizer")}))
        rows += run("Tank mass model (liquid stages)", tank_cases)
    return rows


def configuration_comparison(design, assump, base_res, base_overrides=None) -> list:
    """Propellant-combination comparison on the SAME mission: upper stage variants (all else equal)."""
    g0 = base_res.glom_kg
    N = len(base_res.spec.stages)
    j = N - 1
    top = base_res.spec.stages[j]
    if top.is_solid:
        return []
    lh2 = {f"stages.{j}.fuel": "LH2", f"stages.{j}.mixture_ratio_OF": 5.5, f"stages.{j}.engine.isp_vac_s": 450.0,
           f"stages.{j}.tank.insulated_fuel": True, f"stages.{j}.engine.expansion_ratio": 100.0, f"stages.{j}.tank.ullage_fuel": 0.03,
           f"stages.{j}.tank.order_bottom_to_top": ["oxidizer", "fuel"], f"stages.{j}.tank.mass_method_fuel": "akin_propellant_mass"}
    if top.engine.tw_ignition is not None:                 # a stage sized by thrust keeps its thrust
        lh2[f"stages.{j}.engine.thrust_to_weight_ignition"] = 0.5
    ch4 = {f"stages.{j}.fuel": "LCH4", f"stages.{j}.mixture_ratio_OF": 3.2, f"stages.{j}.engine.isp_vac_s": 360.0,
           f"stages.{j}.tank.insulated_fuel": True, f"stages.{j}.tank.mass_method_fuel": "akin_volume"}
    rp1 = {f"stages.{j}.fuel": "RP-1", f"stages.{j}.mixture_ratio_OF": 2.6, f"stages.{j}.engine.isp_vac_s": 340.0,
           f"stages.{j}.tank.insulated_fuel": False, f"stages.{j}.tank.mass_method_fuel": "akin_propellant_mass"}
    cases = [(f"Upper stage {top.oxidizer}/{top.fuel} as designed (baseline)", f"{top.oxidizer}/{top.fuel}", {}, True)]
    for fuel, label, ov in (("RP-1", "Upper stage LOX/RP-1 (Isp 340 s, O/F 2.6) - illustrative engine values", rp1),
                            ("LH2", "Upper stage LOX/LH2 (Isp 450 s, O/F 5.5) - illustrative engine values", lh2),
                            ("LCH4", "Upper stage LOX/LCH4 (Isp 360 s, O/F 3.2) - illustrative engine values", ch4)):
        if top.fuel == fuel and top.oxidizer == "LOX":
            continue
        if top.oxidizer != "LOX":
            ov = {**ov, f"stages.{j}.oxidizer": "LOX"}
        cases.append((label, f"LOX/{fuel}", ov))
    return run_cases(design, assump, "Upper-stage propellant combination (same mission)", cases, g0, base_overrides, base_res)
