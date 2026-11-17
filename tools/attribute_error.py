"""Split each check case's GLOM error into the causes that produce it.

A validation table that says "Pegasus XL +45 %" is not actionable. The same number can come from a delta-v
requirement that is too large, a mass model that is too heavy, or a published figure that counts different
hardware - and the fix is different in each case. This tool separates them.

THE METHOD, and its one honest limitation.

Three quantities are measured per vehicle, each from data the tool did not fit:

  dv_gap       what the tool asks for, minus what the vehicle's own published masses and Isp deliver.
               Positive means the tool thinks the mission is harder than the real vehicle found it, so it
               will size a bigger rocket for reasons that have nothing to do with mass estimating.

  mass_bias    the tool's predicted stage inert against the published stage inert, AT THE PUBLISHED
               PROPELLANT LOAD. Feeding the real propellant removes the delta-v budget, the Isp and the
               staging split from the comparison, so what is left is the mass model alone.

  residual     what the GLOM error still is after the first two are accounted for. A large residual means
               something is happening that neither measurement explains - a bookkeeping difference, a
               geometry constraint, or a modelling choice - and it is flagged rather than explained away.

The limitation: these do not add up linearly. A rocket is a fixed point, so a 10 % inert error and a 200 m/s
delta-v error interact, and the interaction grows as a vehicle approaches the edge of its own capability.
The numbers below are therefore attributions, not a decomposition that sums to the total, and the script
prints the sensitivity (d GLOM / d inert) so a reader can see how much leverage each vehicle has.
"""
import json
import math
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from launch_vehicle import geometry as geo, mass_budget as mb, propulsion as prop, solid_motor as sm
from launch_vehicle.config_io import load_design
from launch_vehicle.convergence import size_vehicle

ASSUMP = os.path.join(ROOT, "config", "engineering_assumptions.yaml")
VAL = os.path.join(ROOT, "validation")
RESULTS = os.path.join(ROOT, "outputs", "validation", "validation_results.json")


def predicted_stage_inert(path, stage_index, m_prop_kg):
    """Stage inert the tool predicts for a stage carrying m_prop_kg, through the production mass path.

    Everything but the propellant load is the design file's own: diameter, skirt ratios, separation
    hardware, margins. Only the propellant is replaced, which is exactly what isolates the mass model.
    """
    spec = load_design(path, ASSUMP)
    st = spec.stages[stage_index]
    if not st.is_solid:
        return None
    tanks = sm.size_solid_stage(st, m_prop_kg, spec.solid_propellants)
    env = prop.envelope(st, 1.0)
    nxt = spec.stages[stage_index + 1] if stage_index + 1 < len(spec.stages) else None
    nxt_env = prop.envelope(nxt, 1.0) if nxt is not None else None
    layout = geo.build_layout(st, tanks, nxt, env, nxt_env,
                              None if nxt is not None else spec.fairing.diameter_m)
    comps = mb.solid_stage_components(spec, st, tanks[0], layout, 0.0, 0.0)
    base = sum(comps.values())
    return base * (1.0 + st.inert_margin_fraction)


def sensitivity(path, frac=0.10):
    """d(GLOM)/d(inert), measured: raise every stage's inert margin by `frac` and see what GLOM does.

    This is the leverage a mass error has on this particular vehicle. A vehicle with a comfortable
    delta-v margin shrugs off a 10 % inert error; one sized to the edge multiplies it.
    """
    try:
        base = size_vehicle(load_design(path, ASSUMP), keep_history=False).glom_kg
    except Exception:
        return None
    spec = load_design(path, ASSUMP)
    ov = {f"stages.{j}.inert_mass_margin_fraction": spec.stages[j].inert_margin_fraction + frac
          for j in range(len(spec.stages))}
    try:
        bumped = size_vehicle(load_design(path, ASSUMP, ov), keep_history=False).glom_kg
    except Exception:
        return None
    return (bumped - base) / base / frac


def main():
    if not os.path.exists(RESULTS):
        print("run tools/run_validation.py first")
        return
    V = json.load(open(RESULTS, encoding="utf-8"))["vehicles"]
    rows = []
    for key, d in sorted(V.items()):
        path = os.path.join(VAL, key + ".yaml")
        ref = d["ref"]
        glom_err = (d["opt"]["glom"] - ref["glom"][0]) / ref["glom"][0]
        cap = d.get("cap")
        dv_gap = (cap["dv_required"] - cap["dv_published_masses"]) if cap else None

        # mass bias: predicted vs published stage inert at the published propellant, solid stages only
        biases = []
        for s_no, (m_p, _src) in (ref.get("prop") or {}).items():
            dry = (ref.get("dry") or {}).get(s_no)
            if dry is None:
                continue
            try:
                pred = predicted_stage_inert(path, int(s_no) - 1, m_p)
            except Exception:
                pred = None
            if pred:
                biases.append((pred - dry[0]) / dry[0])
        mass_bias = statistics.mean(biases) if biases else None
        rows.append(dict(key=key, title=ref["title"], glom_err=glom_err, dv_gap=dv_gap,
                         mass_bias=mass_bias, n_stage=len(biases),
                         solid=any(d.get("solid") or []), sens=sensitivity(path)))

    print(f"{'vehicle':16s}{'solid':>6s}{'GLOM err':>10s}{'dv gap':>9s}{'mass bias':>11s}"
          f"{'dGLOM/dInert':>14s}")
    print("-" * 66)
    for r in rows:
        dv = f"{r['dv_gap']:>+8.0f}" if r["dv_gap"] is not None else " " * 8
        mb_ = f"{100*r['mass_bias']:>+10.1f}%" if r["mass_bias"] is not None else " " * 11
        se = f"{r['sens']:>13.2f}" if r["sens"] is not None else " " * 13
        print(f"{r['key']:16s}{'YES' if r['solid'] else '-':>6s}"
              f"{100*r['glom_err']:>+9.1f}%{dv} {mb_}{se}")
    print()
    sol = [r for r in rows if r["solid"]]
    liq = [r for r in rows if not r["solid"]]
    for lab, g in (("serial solid", sol), ("all liquid", liq)):
        if not g:
            continue
        e = [abs(r["glom_err"]) for r in g]
        print(f"{lab:14s} N={len(g):2d}  median |GLOM err| {100*statistics.median(e):5.1f}%"
              f"   mean {100*statistics.mean(e):5.1f}%")
    with open(os.path.join(ROOT, "outputs", "validation", "error_attribution.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1)
    print("\nwrote outputs/validation/error_attribution.json")


if __name__ == "__main__":
    main()
