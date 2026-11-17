"""One-at-a-time sensitivity and configuration-comparison studies.

All cases share the base mission requirement and assumptions; only the named parameter(s) change. When a delta-v loss is
varied it is varied inside the same budget (no extra margin or equipment appears in one case only).
Infeasible cases are reported, never dropped.
"""
from __future__ import annotations
from .config_io import load_design
from .convergence import size_vehicle, SizingError
from .validation import InputError


def _row(study, label, value, res=None, err=None, base_glom=None):
    if res is None:
        return dict(study=study, case=label, value=value, converged=False, feasible=False, status=f"infeasible: {err}")
    N = len(res.stages)
    prop = sum(s.m_prop_loaded_kg for s in res.stages)
    errs = [i for i in res.issues if i.level == "ERROR"]
    row = dict(study=study, case=label, value=value, glom_kg=res.glom_kg,
               delta_glom_pct=None if base_glom is None else 100 * (res.glom_kg / base_glom - 1),
               prop_total_kg=prop, dry_total_kg=sum(s.m_dry_kg for s in res.stages),
               payload_fraction=res.payload_mass_kg / res.glom_kg, prop_fraction=prop / res.glom_kg,
               length_m=res.geometry.total_length, dv_req_mps=res.dv_required_mps, dv_margin_mps=res.dv_achieved_mps - res.dv_required_mps,
               converged=res.converged, feasible=not errs, status=res.status if not errs else "; ".join(i.code for i in errs))
    for s in res.stages:
        row[f"dry_s{s.index}_kg"] = s.m_dry_kg
        row[f"len_s{s.index}_m"] = s.length_m
    return row


def run_cases(design, assump, study, cases, base_glom=None) -> list:
    out = []
    for label, value, ov in cases:
        try:
            sp = load_design(design, assump, ov)
            out.append(_row(study, label, value, size_vehicle(sp, keep_history=False), base_glom=base_glom))
        except (SizingError, InputError, ValueError) as ex:
            out.append(_row(study, label, value, err=str(ex)))
    return out


def standard_studies(design, assump, base_res) -> list:
    g0 = base_res.glom_kg
    spec = base_res.spec
    N = len(spec.stages)
    rows = []
    rows += run_cases(design, assump, "Payload mass [kg]",
                      [(f"{v:,.0f}", v, {"mission.payload_mass_kg": v}) for v in (5000.0, 7500.0, 10000.0, 12500.0, 15000.0)], g0)
    e1 = spec.stages[0].engine
    cases = []
    for k in (-0.05, -0.025, 0.0, 0.025, 0.05):
        ov = {}
        for j, st in enumerate(spec.stages):
            ov[f"stages.{j}.engine.isp_vac_s"] = st.engine.isp_vac_s * (1 + k)
            if st.engine.isp_sl_s:
                ov[f"stages.{j}.engine.isp_sl_s"] = st.engine.isp_sl_s * (1 + k)
        cases.append((f"{100*k:+.1f}% (all stages)", k, ov))
    rows += run_cases(design, assump, "Specific impulse (scale, SL & vac)", cases, g0)
    cases = []
    for m in (0.0, 0.05, 0.10, 0.20, 0.30):
        cases.append((f"{m:.2f}", m, {f"stages.{j}.inert_mass_margin_fraction": m for j in range(N)}))
    rows += run_cases(design, assump, "Structural coefficient proxy: inert mass-growth margin", cases, g0)
    base_dv = base_res.dv_required_mps
    rows += run_cases(design, assump, "Mission delta-v requirement [m/s] (total override)",
                      [(f"{base_dv + d:,.0f} ({d:+d})", base_dv + d, {"mission.delta_v_override_mps": base_dv + d}) for d in (-300, -150, 0, 150, 300)], g0)
    rows += run_cases(design, assump, "Delta-v design margin fraction (applied once to the subtotal)",
                      [(f"{v:.2f}", v, {"mission.losses.design_margin_fraction": v}) for v in (0.0, 0.01, 0.02, 0.03, 0.05)], g0)
    rows += run_cases(design, assump, "Staging/ignition delay in ascent time [s] (enters the book loss regression)",
                      [(f"{v:.0f}", v, {"mission.losses.staging_delay_s": v}) for v in (0.0, 3.0, 10.0, 20.0, 40.0)], g0)
    rows += run_cases(design, assump, "RP-1 density [kg/m3] (tank volume)",
                      [(f"{v:,.0f}", v, {"assumptions.propellants.RP-1.density_kg_m3": v}) for v in (780.0, 800.0, 820.0, 840.0, 860.0)], g0)
    rows += run_cases(design, assump, "LOX density [kg/m3] (tank volume)",
                      [(f"{v:,.0f}", v, {"assumptions.propellants.LOX.density_kg_m3": v}) for v in (1080.0, 1140.0, 1230.0)], g0)
    rows += run_cases(design, assump, "Propellant loading margin (all stages)",
                      [(f"{m:.3f}", m, {f"stages.{j}.loading_margin_fraction": m for j in range(N)}) for m in (0.0, 0.005, 0.01, 0.02, 0.03)], g0)
    rows += run_cases(design, assump, "Stage-1 diameter [m]",
                      [(f"{d:.1f}", d, {"stages.0.diameter_m": d}) for d in (3.4, 3.6, 4.0, 4.4, 5.0)], g0)
    tank_cases = [("Table 8.6 (propellant-mass MER) [baseline]", 0, {}),
                  ("Table 8.7 (volume MER)", 1, {f"stages.{j}.tank.mass_method_{r}": "akin_volume" for j in range(N) for r in ("fuel", "oxidizer")}),
                  ("Mass fraction (assumed 1.5% / 1.1%)", 2, {f"stages.{j}.tank.mass_method_{r}": "mass_fraction" for j in range(N) for r in ("fuel", "oxidizer")}),
                  ("Pressure vessel, 3 bar (membrane only)", 3, {f"stages.{j}.tank.mass_method_{r}": "pressure_vessel" for j in range(N) for r in ("fuel", "oxidizer")})]
    rows += run_cases(design, assump, "Tank mass model", tank_cases, g0)
    return rows


def configuration_comparison(design, assump, base_res) -> list:
    """Propellant-combination comparison on the SAME mission: upper stage variants (all else equal)."""
    g0 = base_res.glom_kg
    N = len(base_res.spec.stages)
    j = N - 1
    lh2 = {f"stages.{j}.fuel": "LH2", f"stages.{j}.mixture_ratio_OF": 5.5, f"stages.{j}.engine.isp_vac_s": 450.0,
           f"stages.{j}.tank.insulated_fuel": True, f"stages.{j}.engine.thrust_to_weight_ignition": 0.5,
           f"stages.{j}.engine.expansion_ratio": 100.0, f"stages.{j}.tank.ullage_fuel": 0.03,
           f"stages.{j}.tank.order_bottom_to_top": ["oxidizer", "fuel"], f"stages.{j}.tank.mass_method_fuel": "akin_propellant_mass"}
    ch4 = {f"stages.{j}.fuel": "LCH4", f"stages.{j}.mixture_ratio_OF": 3.2, f"stages.{j}.engine.isp_vac_s": 360.0,
           f"stages.{j}.tank.insulated_fuel": True, f"stages.{j}.tank.mass_method_fuel": "akin_volume"}
    cases = [("Upper stage LOX/RP-1 (baseline)", "LOX/RP-1", {}),
             ("Upper stage LOX/LH2 (Isp 450 s, O/F 5.5) - illustrative engine values", "LOX/LH2", lh2),
             ("Upper stage LOX/LCH4 (Isp 360 s, O/F 3.2) - illustrative engine values", "LOX/LCH4", ch4)]
    return run_cases(design, assump, "Upper-stage propellant combination (same mission)", cases, g0)
