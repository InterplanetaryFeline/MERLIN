"""Check the ascent simulation against real vehicles flown on their PUBLISHED masses.

The other checks fly the vehicle this tool sizes, so an ascent that falls short can be the sizing's fault. Here the
sizing is taken out: every propellant load, empty mass, thrust and Isp is the published one (the references of
tools/run_validation.py and the validation design files), the payload and orbit are the published ones, and only the
flight is this tool's. A real vehicle reaches its published orbit with its published payload and nothing to spare, so
the speed in hand at the end should be near zero. What it is not is the error of the simulation together with the error
of the published data, and the two cannot be separated; the sources' own confidence is printed with each row.

Nothing is tuned. Where a figure is missing it is the validation design's own assumption and is listed.

Writes docs/ASCENT_VALIDATION.md:  python tools/validate_ascent.py
"""
import ast
import math
import os
import re
import statistics
import sys
import time
from dataclasses import replace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from launch_vehicle import ascent, propulsion as prop, trajectory as tj          # noqa: E402
from launch_vehicle.atmosphere import P0_PA                                      # noqa: E402
from launch_vehicle.config_io import load_design                                 # noqa: E402
from launch_vehicle.convergence import size_vehicle, thrust_mode                 # noqa: E402
from launch_vehicle.units import G0                                              # noqa: E402

ASSUMP = os.path.join(ROOT, "config", "engineering_assumptions.yaml")

#: Hardware the published stage masses leave out, carried to the end (adapter, equipment bay). From run_validation's
#: CAP table where it gives one.
NOTES = {
    "electron": "stage masses are a community wiki's (low confidence), and the first stage's only published Isp is used "
                "as its vacuum one",
    "vega": "the published AVUM empty mass is 131 kg; the table for Vega C gives 695 kg for its successor",
    "m_v": "the published stage masses are the motors alone: 5.6 t of the lift-off mass is in none of them",
    "scout_g1": "the published masses and Isp give 8,879 m/s ideal, 1,293 m/s more than the orbital speed, for a 555 km "
                "polar orbit with no help from the Earth's rotation",
    "delta4_heavy": "the real core throttles to about 55 % while the strap-ons burn; the engine data here cannot say so, "
                    "so the core is flown at full thrust",
    "h2a_202": "the second stage's empty mass is assumed in the reference table",
    "ariane5_eca": "real GTO ascents go straight in, with one burn of an engine that cannot restart",
    "saturn5": "flown to the orbit of the design file; the S-IVB does both burns",
    "soyuz2_1b": "the core is lit on the ground and burns through, as in the design file",
    "pegasus_xl": "no wing lift in this model",
}


def reference_tables():
    """REF and CAP of tools/run_validation.py, read without running it."""
    src = open(os.path.join(ROOT, "tools", "run_validation.py"), encoding="utf-8").read()
    out = {}
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") in ("REF", "CAP"):
            out[node.targets[0].id] = eval(compile(ast.Expression(node.value), "run_validation", "eval"),   # noqa: S307
                                           {"dict": dict})
    return out["REF"], out["CAP"]


def published_vehicle(key, ref, extra_kg):
    """The AscentVehicle of the published masses, and the sized result whose mission, shape and drag it borrows."""
    spec = load_design(os.path.join(ROOT, "validation", key + ".yaml"), ASSUMP)
    res = size_vehicle(spec, keep_history=False)
    sized = tj.ascent_vehicle_from_result(res)
    N = len(spec.stages)
    # `extra` is the fairing, adapter and avionics of the reference table, lumped and carried to the end there. The
    # fairing and adapter are in this vehicle already, and the fairing leaves when the real one does.
    above = spec.payload_mass_kg + res.paf_mass_kg + max(extra_kg - res.paf_mass_kg - res.fairing_mass_kg, 0.0)
    stage_m = {}
    for k in range(N, 0, -1):
        stage_m[k] = (ref["prop"][k][0], ref["dry"][k][0], above)
        above += ref["prop"][k][0] + ref["dry"][k][0]
    fairing = res.fairing_mass_kg
    boost = ref.get("boosters")
    boost_total = boost[0] * (boost[1] + boost[2]) if boost else 0.0
    m0 = above + fairing + boost_total
    perf = {}
    bb = res.boosters
    for st in spec.stages:
        k = st.index
        mp, dry, up = stage_m[k]
        p = st.prop_system
        isp_sl = p.isp_sl_s
        first = k == 1 and isp_sl is not None
        fair_on = fairing if spec.fairing.jettison_stage > k else 0.0
        m_ign = up + mp + dry + fair_on + (boost_total if k == 1 else 0.0)
        if thrust_mode(st) == "tw":
            t_ref = p.tw_ignition * G0 * m_ign - (boost[0] * bb.thrust_sl_each_N if (boost and k == 1) else 0.0)
            mdot = t_ref / (G0 * (isp_sl if first else p.isp_vac_s))
        elif st.is_solid:
            mdot = mp / p.burn_time_s
        else:
            mdot = p.n_engines * p.thrust_vac_per_engine_N / (G0 * p.isp_vac_s)
        t_vac = mdot * G0 * p.isp_vac_s
        if isp_sl and isp_sl < p.isp_vac_s:
            ae = mdot * G0 * (p.isp_vac_s - isp_sl) / P0_PA
        else:
            env = prop.envelope(st, t_vac / (1 if st.is_solid else p.n_engines))
            ae = env.n * 0.25 * math.pi * env.exit_diameter_m ** 2
        perf[k] = (t_vac, mdot, ae)
    burns, left = [], {k: stage_m[k][0] for k in stage_m}
    for b in sized.burns:
        m = re.match(r"stage (\d+)", b.name)
        if not m:
            burns.append(replace(b))
            continue
        k = int(m.group(1))
        t_vac, mdot, ae = perf[k]
        on = re.search(r"core \+ (\d+) x", b.name)
        n_on = int(on.group(1)) if on else 0
        if n_on:
            b_mdot = n_on * boost[1] / bb.burn_time_s
            isp_v, isp_s = spec.boosters.isp_vac_s, spec.boosters.isp_sl_s
            dur = bb.burn_time_s
            left[k] -= mdot * dur
            burns.append(replace(b, duration_s=dur, startup_kg=0.0, mdot_kgs=mdot + b_mdot,
                                 thrust_vac_N=t_vac + b_mdot * G0 * isp_v,
                                 exit_area_m2=ae + (b_mdot * G0 * (isp_v - isp_s) / P0_PA if isp_s else 0.0),
                                 jettison_kg=n_on * boost[2]))
        else:
            burns.append(replace(b, duration_s=left[k] / mdot, startup_kg=0.0, mdot_kgs=mdot, thrust_vac_N=t_vac,
                                 exit_area_m2=ae, jettison_kg=stage_m[k][1]))
    veh = replace(sized, m0_kg=m0, burns=burns, fairing_kg=fairing)
    return veh, res


def fly(key, ref, cap):
    extra = (cap.get(key) or {}).get("extra", 0.0) or 0.0
    veh, res = published_vehicle(key, ref, extra)
    f = ascent.flight_for(res, veh)
    sol = f.search()[0]
    out = ascent.fly(f, sol, key)
    out.insertion = tj.insertion_orbit(res, out)
    return veh, res, f, out


#: What the model before this one made of the same designs, as sized (measured at v1.2.1): a continuous burn straight to
#: the target altitude on a gravity turn. Kept so that the change is on the record.
BEFORE = dict(falcon9="reached", ariane62="reached", saturn5="short", sls_block1="short", vega="short", vega_c="short",
              electron="suborbital", epsilon="suborbital", firefly_alpha="suborbital", h2a_202="suborbital",
              minotaur1="suborbital", pegasus_xl="suborbital", soyuz2_1b="suborbital", titan2="suborbital",
              zhuque2="suborbital", ariane64="no ascent", atlas5_551="no ascent", cz12="no ascent",
              delta2_7920="no ascent", delta4_heavy="no ascent", m_v="no ascent", scout_g1="no ascent",
              ariane5_eca="not attempted", h3_24l="not attempted")
WORD = dict(reached="reached", short="short", suborbital="suborbital", no_ascent="no ascent")


def verdict(res, out):
    return WORD.get((out.insertion or {}).get("verdict"), "no ascent")


def orbit(out):
    i = out.insertion or {}
    if not out.converged or i.get("perigee_alt_m") is None:
        return "-"
    if i["perigee_alt_m"] < 0:
        return f"apogee {i['apogee_alt_m']/1e3:,.0f}"
    return f"{i['perigee_alt_m']/1e3:,.0f} x {i['apogee_alt_m']/1e3:,.0f}"


#: Book Fig. 6.41 (p.397): the Pegasus flight to 648 km. Altitudes in km, times from the drop.
PEGASUS_BOOK = [("First stage burnout", 75.68, 52.6), ("Second stage ignition", 91.40, 71.0),
                ("Second stage burnout", 164.92, 187.0), ("Third stage ignition", 457.76, 621.0),
                ("Third stage burnout", 526.16, 648.0)]


def pegasus_figure(REF, CAP):
    """The published-mass Pegasus flown to the 648 km of the book's figure, against the figure's events."""
    veh, res = published_vehicle("pegasus_xl", REF["pegasus_xl"], (CAP.get("pegasus_xl") or {}).get("extra", 0.0))
    f = ascent.flight_for(res, veh)
    f.plan = ascent.make_plan(f.mu, f.R, 648e3, 648e3, stoppable=False)
    out = ascent.fly(f, f.search()[0], "pegasus")
    ev = {e["name"]: e for e in out.events}
    flown = [ev["stage 1 burnout"], ev["stage 2 start"], ev["stage 2 burnout"], ev["stage 3 start"], ev["stage 3 burnout"]]
    return out, flown


def main():
    REF, CAP = reference_tables()
    rows, t0 = [], time.time()
    for key, ref in REF.items():
        path = os.path.join(ROOT, "validation", key + ".yaml")
        n = len(load_design(path, ASSUMP).stages)
        if set(ref["prop"]) != set(range(1, n + 1)) or set(ref["dry"]) != set(range(1, n + 1)):
            continue
        veh, res, f, out = fly(key, ref, CAP)
        rows.append(dict(key=key, title=ref["title"], veh=veh, res=res, f=f, out=out, glom=ref["glom"][0]))
        print(f"{key:14s} m0 {veh.m0_kg/1e3:8.1f} t (published {ref['glom'][0]/1e3:8.1f})  {f.plan.kind:9s} "
              f"margin {out.margin_mps:+8.0f}  {verdict(res, out)}", flush=True)
    sized = []
    for key in sorted(REF):
        res = size_vehicle(load_design(os.path.join(ROOT, "validation", key + ".yaml"), ASSUMP), keep_history=False)
        out = tj.fly_design(res, **tj.flight_options(res.spec))
        sized.append((key, REF[key]["title"], res, out))
        print(f"as sized: {key:14s} {BEFORE.get(key, '-'):13s} -> {verdict(res, out):11s} {out.margin_mps:+8.0f}", flush=True)
    peg, flown = pegasus_figure(REF, CAP)
    write_doc(rows, sized, peg, flown)
    print(f"{time.time()-t0:.0f} s; wrote docs/ASCENT_VALIDATION.md")


def write_doc(rows, sized, peg, flown):
    ok = [r for r in rows if r["out"].converged]
    m = [r["out"].margin_mps for r in ok]
    L = ["# The ascent simulation against real vehicles", "",
         "Generated by `tools/validate_ascent.py`. Do not edit by hand. `docs/ASCENT.md` explains the model.", "",
         "## 1. Real vehicles on their published masses", "",
         "Every propellant load, empty mass, thrust and Isp is the published one, and so are the payload and the orbit; "
         "only the flight is this tool's. A real vehicle reaches its published orbit with nothing to spare, so the "
         "speed in hand should be near zero. A margin is the simulation's error and the data's together, and the two "
         "cannot be separated: 100 m/s is about 1 % of the speed to orbit, and about the size of the uncertainty in most "
         "of these published masses. Fairing and adapter masses are this tool's own estimates, because the sources "
         "rarely give them. Nothing was adjusted.", "",
         "| Vehicle | Lift-off mass flown / published [t] | Way to orbit | Orbit asked [km] | Orbit flown [km] | Speed in "
         "hand [m/s] | Losses to first cutoff: gravity / drag / steering / back pressure [m/s] | Note |",
         "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        o, p = r["out"], r["f"].plan
        mar = f"**{o.margin_mps:+,.0f}**" if o.converged else "no ascent"
        loss = (f"{o.gravity_loss_mps:,.0f} / {o.drag_loss_mps:,.0f} / {o.steering_loss_mps:,.0f} / "
                f"{o.propulsion_loss_mps:,.0f}") if o.converged else "-"
        L.append(f"| {r['title']} | {r['veh'].m0_kg/1e3:,.1f} / {r['glom']/1e3:,.1f} | {p.kind} | {p.perigee_m/1e3:,.0f} x "
                 f"{p.apogee_m/1e3:,.0f} | {orbit(o)} | {mar} | {loss} | {NOTES.get(r['key'], '')} |")
    in150 = sum(1 for x in m if abs(x) <= 150)
    L += ["", f"{len(ok)} of {len(rows)} ascents closed. Speed in hand: median {statistics.median(m):+.0f} m/s, mean "
          f"{statistics.mean(m):+.0f}, mean absolute {statistics.mean(abs(x) for x in m):.0f}; {in150} of {len(ok)} within "
          f"150 m/s of zero. (Vehicles with a published mass for every stage only.)", "",
          "## 2. Against a published flight: Pegasus (book Fig. 6.41, p.397)", "",
          "The book's figure is a flight to 648 km; the same is flown here with the published masses of the Pegasus XL. "
          "The figure's times run from the drop, 5 s before ignition, and are shifted to ignition here. The real first "
          "stage has a wing, which this model does not.", "",
          "| Event | Book: time after ignition [s] | Flown [s] | Book: altitude [km] | Flown [km] |", "|---|---|---|---|---|"]
    for (name, t, h), e in zip(PEGASUS_BOOK, flown):
        L.append(f"| {name} | {t - 5.0:,.1f} | {e['t_s']:,.1f} | {h:,.1f} | {e['h_m']/1e3:,.1f} |")
    L += ["", f"Maximum dynamic pressure {peg.max_q_Pa/1e3:.1f} kPa flown, 66.9 kPa in the book (p.398, first mission). "
          f"Largest flight path angle {max(peg.gamma_deg):.0f} deg flown, 34 deg in the book. Drag loss "
          f"{peg.drag_loss_mps:,.0f} m/s flown, 322 m/s in the book: the wing and the tail are missing here.", ""]
    sat = next((r for r in rows if r["key"] == "saturn5"), None)
    if sat:
        o = sat["out"]
        s2 = [a for t, a in zip(o.t_s, o.alpha_deg) if 190 <= t <= 540]
        s1 = next(e for e in o.events if e["name"] == "stage 1 burnout")
        L += ["## 3. Saturn V (book pp.393-395)", "",
              f"The book's Figs. 6.35 and 6.37 show a lofted ascent whose angle of attack rises to 10-14 deg in the S-II "
              f"burn. Flown here: S-IC burnout at {s1['t_s']:.0f} s and {s1['h_m']/1e3:.0f} km, and an angle between thrust and "
              f"velocity of up to {max(s2):.0f} deg in the S-II burn. The real S-IC and S-II shut their centre engines down "
              f"early, which this model does not.", ""]

    def cnt(w, seq):
        return sum(1 for x in seq if x == w)
    after = [verdict(r, o) for _, _, r, o in sized]
    before = [BEFORE.get(k, "-") for k, _, _, _ in sized]
    L += ["## 4. The 24 validation vehicles, as this tool sizes them", "",
          "These are not the real vehicles: their masses are this tool's, and several carry far too much propellant in an "
          "upper stage (see `docs/ACCURACY.md`). The table says what changed with the ascent model. \"Before\" is the "
          "v1.2.1 model: one continuous burn straight to the target altitude on a gravity turn.", "",
          "| Vehicle | Before | Now | Orbit flown [km] | Speed in hand [m/s] | Losses of the flight / sized with [m/s] |",
          "|---|---|---|---|---|---|"]
    for k, title, r, o in sized:
        eq = f"{o.equivalent_loss_mps:,.0f}" if o.equivalent_loss_mps is not None else "-"
        L.append(f"| {title} | {BEFORE.get(k, '-')} | {verdict(r, o)} | {orbit(o)} | "
                 f"{format(o.margin_mps, '+,.0f') if o.converged else '-'} | {eq} / {o.budget_loss_mps:,.0f} |")
    L += ["", "| | Reached | Short | Suborbital | No ascent | Not attempted |", "|---|---|---|---|---|---|"]
    for name, seq in (("Before", before), ("Now", after)):
        L.append(f"| {name} | " + " | ".join(str(cnt(w, seq)) for w in
                                             ("reached", "short", "suborbital", "no ascent", "not attempted")) + " |")
    L.append("")
    with open(os.path.join(ROOT, "docs", "ASCENT_VALIDATION.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(L))


if __name__ == "__main__":
    main()
