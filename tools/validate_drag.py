"""Measure the geometry drag build-up, and the trajectory that flies on it, against published figures.

    python tools/validate_drag.py          # prints the tables, writes docs/DRAG_VALIDATION_DATA.md
                                           # and outputs/validation/drag_validation.json

Nothing here is tuned. Every published number below carries where it was read, and every dimension that could
not be sourced is marked ASSUMED, with the result re-run across a range of the assumption so its weight is
visible. Three things are measured:

  1. Cd against Mach number, for vehicles whose curve is published AND whose outside shape is known.
  2. The first-stage ascent of the Apollo 11 Saturn V, flown from the masses, thrust and flow rate the book
     reproduces from NASA, against the flight's own Mach 1, max-q and cutoff figures.
  3. Drag loss, against the book's Table 3.4.

Curves read off a printed figure were digitised from a 4x rendering of the page, with the axes located from
the plot frame; they are good to about 0.01 in Cd, which is the width of the printed line.
"""
from __future__ import annotations
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from launch_vehicle import aerodynamics as aero                      # noqa: E402
from launch_vehicle import drag_buildup as db                        # noqa: E402
from launch_vehicle import trajectory as tj                          # noqa: E402
from launch_vehicle.atmosphere import us76                           # noqa: E402
from launch_vehicle.units import G0                                  # noqa: E402

LBM, LBF, FT, IN, PSF = 0.45359237, 4.4482216, 0.3048, 0.0254, 47.880259
S = db.Section

# =========================================================================================== 1. Cd curves
#: Book Fig. 6.10 (p.359), "Vanguard CD vs Mach and AoA of 0 deg and 6 deg", source Klawans, Martin ER 11022.
#: The 0 deg curve, digitised. Below Mach 0.7 the printed curve climbs steeply towards Mach 0, which no
#: coefficient on a fixed reference area does for a slender body; those points are left out and said so.
VANGUARD_FIG_6_10 = {0.7: 0.308, 0.8: 0.270, 0.9: 0.279, 1.0: 0.362, 1.1: 0.428, 1.2: 0.450, 1.3: 0.441,
                     1.5: 0.386, 1.75: 0.317, 2.0: 0.261, 2.5: 0.197, 3.0: 0.182, 3.5: 0.176, 4.0: 0.171,
                     5.0: 0.171}

#: Book Fig. 6.12 (p.360), "Generic drag coefficient curve for launch vehicles", source Dergarabedian & Ten
#: Dyke 1959. No geometry goes with it, so it is context for the others and is not scored.
GENERIC_FIG_6_12 = {0.5: 0.189, 0.8: 0.196, 0.9: 0.202, 1.1: 0.358, 1.2: 0.392, 1.3: 0.413, 1.5: 0.408,
                    2.0: 0.345, 2.5: 0.294, 3.0: 0.264, 4.0: 0.228, 5.0: 0.206, 6.0: 0.191, 7.0: 0.182}

TITAN_MACHS = (0.3, 0.6, 0.8, 0.9, 1.0, 1.068, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0)


def vanguard(transition_length_m: float = 1.143) -> db.Configuration:
    """The Vanguard launch vehicle.

    45 in first stage and 32 in second stage: Martin ER 11022, Sec. III.F.1 ("basically a 45-inch diameter
    cylinder", "basically a 32-inch diameter cylinder"), read in the archive.org text. Nose cone 12 ft 6.72 in
    long, first stage 12.07 m, second stage 5.68 m: thisdayinaviation.com 'Vanguard 3', as returned by a web
    search and not read in the original. The conical transition between the two diameters is described in
    ER 11022 as "a semimonocoque truncated cone" with no length given: ASSUMED one first-stage diameter long.
    """
    d1, d2 = 45 * IN, 32 * IN
    secs = [S("nose cone", 3.8283, 0.0, d2), S("second stage", 5.68 - 0.5 * transition_length_m, d2, d2),
            S("transition", transition_length_m, d2, d1),
            S("first stage", 12.07 - 0.5 * transition_length_m, d1, d1)]
    return db.Configuration("Vanguard", [db.Body("core", secs)], 0.25 * math.pi * d1 ** 2)


def titan2(adapter_length_m: float = 1.5, exit_area_m2: float = 2.0) -> db.Configuration:
    """The Titan II missile with its Mark 6 re-entry vehicle.

    Missile 103.4 ft long and 10 ft in diameter: National Museum of the USAF fact sheet. Mark 6: 3.1 m long,
    base radius 1.15 m, nose radius 0.59 m, 12.5 deg half-angle - from a web search digest, not read in the
    original; the four numbers are mutually consistent (a 0.59 m sphere tangent to a 12.5 deg cone reaching
    1.15 m radius is 3.05 m long). The adapter from the 2.30 m re-entry vehicle to the 3.05 m body: length
    ASSUMED. Nozzle exit area of the two first-stage chambers: ASSUMED, and it only enters power-on.
    """
    rn, th, rb = 0.59, math.radians(12.5), 1.15
    tip = 2.0 * rn * math.cos(th)
    cone = (rb - 0.5 * tip) / math.tan(th)
    cap = rn * (1.0 - math.sin(th))
    body = 103.4 * FT - cap - cone - adapter_length_m
    secs = [S("Mk 6 cone", cone, tip, 2 * rb), S("adapter", adapter_length_m, 2 * rb, 10 * FT),
            S("stages", body, 10 * FT, 10 * FT)]
    return db.Configuration("Titan II", [db.Body("core", secs, 1, exit_area_m2, True, tip)],
                            0.25 * math.pi * (10 * FT) ** 2)


def saturn5(exit_diameter_m: float = 3.7) -> db.Configuration:
    """The Apollo Saturn V, from the segment table the book prints: Table 9.5, p.566 (elevation at the top,
    length and diameter at the top of each segment). The launch escape tower is a 0.66 m cylinder ahead of the
    command module, whose cone therefore starts at 0.66 m. Reference area 79.49 m2, the 10.06 m core (p.172).

    Left out: the four engine fairings and four fins, which the book says raise the frontal area from 79.49 to
    123.55 m2 (p.172). F-1 nozzle exit diameter: ASSUMED 3.7 m, as in validation/saturn5.yaml.
    """
    secs = [S("launch escape tower", 9.15, 0.66, 0.66), S("command module", 2.84, 0.66, 3.91),
            S("service module", 4.52, 3.91, 3.91), S("LM adapter", 8.76, 3.91, 6.60),
            S("S-IVB and IU", 13.01, 6.60, 6.60), S("S-II forward skirt", 5.79, 6.60, 10.06),
            S("S-II", 19.28, 10.06, 10.06), S("interstage", 4.97, 10.06, 10.06),
            S("S-IC", 16.57 + 13.89 + 8.04, 10.06, 10.06)]
    ae = 5 * 0.25 * math.pi * exit_diameter_m ** 2
    return db.Configuration("Saturn V", [db.Body("core", secs, 1, ae, True, 0.66)], 79.49)


#: Book p.588: "the axial force Fmax-q = 260 klbf = 1,156.5 kN" at "qmax = 750 lbf/ft2 = 35.91 kPa", read by
#: the book from an MSFC plot for SA-503 (its Fig. 9.51). The book divides by 122.5 m2 to get 0.263; on the
#: 79.49 m2 core area every other number here uses, the same force is Cd = 0.405. Mach number at max-q is
#: 1.71 for Apollo 11 (p.584) and is assumed the same for SA-503, as the book assumes.
SATURN5_AXIAL_FORCE_N = 260e3 * LBF
SATURN5_AXIAL_Q_PA = 750 * PSF
SATURN5_MAXQ_MACH = 1.71
SATURN5_MAXQ_ALT_M = 13568.0


def curve_comparison(name, published: dict, config: db.Configuration, power_on: bool, note: str) -> dict:
    rows = []
    for m, ref in published.items():
        h = db.representative_altitude_m(m)
        b = config.breakdown(m, h, power_on)
        rows.append(dict(mach=m, published=ref, model=b["total"], error_pct=100 * (b["total"] / ref - 1),
                         friction=b["friction"], forebody=b["forebody"], base=b["base"] + b["boattail"]))
    errs = [abs(r["error_pct"]) for r in rows]
    peak_p = max(published.items(), key=lambda kv: kv[1])
    grid = [0.6 + 0.02 * i for i in range(121)]
    peak_m = max(((m, config.breakdown(m, db.representative_altitude_m(m), power_on)["total"]) for m in grid),
                 key=lambda kv: kv[1])
    return dict(name=name, note=note, power_on=power_on, rows=rows, mean_abs_error_pct=sum(errs) / len(errs),
                max_abs_error_pct=max(errs), bias_pct=sum(r["error_pct"] for r in rows) / len(rows),
                published_peak=dict(mach=peak_p[0], cd=peak_p[1]), model_peak=dict(mach=peak_m[0], cd=peak_m[1]))


def all_curves() -> list:
    out = [curve_comparison(
        "Vanguard", VANGUARD_FIG_6_10, vanguard(), False,
        "Book Fig. 6.10, zero angle of attack, wind tunnel, so power off. Transition length assumed.")]
    out[-1]["sensitivity"] = {f"transition {L:.1f} m": curve_comparison("", VANGUARD_FIG_6_10, vanguard(L),
                              False, "")["mean_abs_error_pct"] for L in (0.6, 1.143, 2.0)}
    t2 = {m: aero.cd_titan2(m) for m in TITAN_MACHS}
    out.append(curve_comparison(
        "Titan II", t2, titan2(), True,
        "Book Fig. 6.13, the analytic curve after Linshue. Its configuration and power state are not stated; "
        "the missile with its Mk 6 re-entry vehicle is taken, engines on. Adapter length assumed."))
    out[-1]["sensitivity"] = {f"adapter {L:.1f} m": curve_comparison("", t2, titan2(L), True,
                              "")["mean_abs_error_pct"] for L in (1.0, 1.5, 3.0)}
    return out


def saturn5_point() -> dict:
    cfg = saturn5()
    measured = SATURN5_AXIAL_FORCE_N / (SATURN5_AXIAL_Q_PA * cfg.reference_area_m2)
    b = cfg.breakdown(SATURN5_MAXQ_MACH, SATURN5_MAXQ_ALT_M, True)
    return dict(mach=SATURN5_MAXQ_MACH, measured_cd=measured, model_cd=b["total"],
                error_pct=100 * (b["total"] / measured - 1), breakdown=b,
                titan2_curve_cd=aero.cd_titan2(SATURN5_MAXQ_MACH),
                titan2_error_pct=100 * (aero.cd_titan2(SATURN5_MAXQ_MACH) / measured - 1),
                frontal_area_ratio_with_fairings_and_fins=123.55 / 79.49)


# =========================================================================================== 2. Apollo 11
#: Everything is the book's reproduction of NASA SP-2000-4029 (Orloff) unless marked.
APOLLO11 = dict(
    ignition_mass_kg=6_477_875 * LBM,           # p.585: "fully loaded ignition weight ... 6,477,875 lbm"
    ignition_before_liftoff_s=6.4,              # p.587: "The engines' startup sequence begins at -6.4 s"
    thrust_sl_per_engine_N=6.77e6,              # Table 4.11, p.241: F-1, SA-504 and subsequent, 6.77 MN
    isp_sl_s=263.0,                             # Table 4.11, p.241
    isp_vac_s=304.0,                            # Example 3.8, p.176: "the vacuum Isp-vac = 304 s"
    n_engines=5,
    # two more published figures, NOT used to build the nominal vehicle:
    mean_flow_kgs=(19_437 + 8_297) * LBM,       # p.585: LOx 19,437 lbm/s, RP-1 8,297 lbm/s
    thrust_liftoff_example_3_7_N=7.891e6 * LBF, # p.172, Example 3.7: "liftoff thrust 7.891 x 10^6 lb"
    thrust_at_maxq_N=38.55e6,                   # p.589, Fig. 9.52: "Tmax-q = 38.55 MN" at 83 s
    pitch_start_s=13.2,                         # NASA SP-4029 Apollo 11 timeline: pitch and roll start 13.2 s
    ceco_s=135.2, oeco_s=161.63,                # same timeline
    # what the flight did, to compare against
    mach1_s=66.3,                               # timeline: "Mach 1 achieved 000:01:06.3"
    maxq_s=83.0, maxq_Pa=735.17 * PSF,          # timeline; and book p.584
    maxq_h_m=13_568.0, maxq_v_mps=504.0,        # p.584: 7.326 NM = 13,568 m; 1653.4 ft/s = 504 m/s
    maxq_mach=1.71,                             # p.584
    maxq_mass_kg=1_814_668.0,                   # p.587
    max_accel_g=3.94,                           # timeline: S-IC maximum total inertial acceleration, at OECO
    drag_loss_mps=(40.0, 46.0),                 # Table 3.4 p.180; and p.174 "46 m/s"
)


VARIANTS = ("nominal", "Example 3.7 lift-off thrust", "no hold-down burn-off")


def apollo11_engine(variant: str = "nominal") -> dict:
    """Thrust, flow and nozzle area of the five F-1s.

    Nominal: the engine table's sea-level thrust and Isp, and the vacuum Isp of Example 3.8. Flow is thrust
    over g0 Isp, vacuum thrust is flow times g0 Isp_vac, and the exit area is the thrust difference over sea-
    level pressure (Eq. 6:52). Two independent published figures then check it without being used: the area
    comes out as five 3.6 m exits, and the thrust at the max-q altitude comes out within 1 % of the 38.55 MN
    the book reads from NASA's reconstructed thrust curve.

    The book also quotes a "liftoff thrust" of 7.891e6 lbf in Example 3.7. That is 3.7 % above five times the
    engine table's value and cannot be reconciled with it and the 38.55 MN at max-q using any real nozzle
    (it needs 40 m2 of exit against 52 m2), so it is flown only as a variant, to show what it would do.
    """
    a = APOLLO11
    p0 = us76(0.0).pressure_Pa
    tsl = a["n_engines"] * a["thrust_sl_per_engine_N"]
    mdot = tsl / (G0 * a["isp_sl_s"])
    tvac = mdot * G0 * a["isp_vac_s"]
    ae = (tvac - tsl) / p0
    if variant == "Example 3.7 lift-off thrust":
        p1 = us76(a["maxq_h_m"]).pressure_Pa
        ae = (a["thrust_at_maxq_N"] - a["thrust_liftoff_example_3_7_N"]) / (p0 - p1)
        tvac = a["thrust_liftoff_example_3_7_N"] + ae * p0
        tsl = a["thrust_liftoff_example_3_7_N"]
    return dict(thrust_sl_N=tsl, thrust_vac_N=tvac, mdot_kgs=mdot, exit_area_m2=ae,
                thrust_at_maxq_altitude_N=tvac - ae * us76(a["maxq_h_m"]).pressure_Pa,
                exit_diameter_each_m=math.sqrt(4 * ae / (math.pi * a["n_engines"])))


def apollo11_vehicle(drag: aero.DragModel, variant: str = "nominal") -> tj.AscentVehicle:
    """The S-IC burn of AS-506 as two burns: five engines to centre-engine cutoff, then four.

    Lift-off mass is the ignition mass less 6.4 s of flow, which is the book's own method on p.587. It takes
    off too much, because the engines do not reach full flow at once; the "no hold-down burn-off" variant
    takes off nothing, and the truth is between the two.
    """
    a, e = APOLLO11, apollo11_engine(variant)
    m0 = a["ignition_mass_kg"]
    if variant != "no hold-down burn-off":
        m0 -= e["mdot_kgs"] * a["ignition_before_liftoff_s"]
    isp = e["thrust_vac_N"] / (e["mdot_kgs"] * G0)
    burns = [tj.Burn("S-IC, five engines", a["ceco_s"], e["thrust_vac_N"], e["mdot_kgs"], e["exit_area_m2"], isp),
             tj.Burn("S-IC, four engines", a["oeco_s"] - a["ceco_s"], 0.8 * e["thrust_vac_N"],
                     0.8 * e["mdot_kgs"], 0.8 * e["exit_area_m2"], isp)]
    return tj.AscentVehicle("Saturn V AS-506, S-IC burn", m0, burns, 79.49, drag, atmosphere="us76")


def _at(traj, t):
    """Linear interpolation of the recorded history at time t."""
    ts = traj.t_s
    for k in range(1, len(ts)):
        if ts[k] >= t:
            f = (t - ts[k - 1]) / max(ts[k] - ts[k - 1], 1e-12)
            pick = lambda arr: arr[k - 1] * (1 - f) + arr[k] * f
            return dict(h=pick(traj.h_m), v=pick(traj.v_mps), q=pick(traj.q_Pa), mach=pick(traj.mach),
                        m=pick(traj.m_kg), gamma=pick(traj.gamma_deg))
    raise ValueError("time past the end of the trajectory")


def fly_apollo11(drag: aero.DragModel, variant: str = "nominal") -> dict:
    """Gravity turn from the published pitch start, with the kick chosen so the vehicle is at the published
    altitude at the published max-q time. That one altitude is the only flight number used as an input; the
    actual pitch programme is not public in a form this model can fly."""
    a = APOLLO11
    veh = apollo11_vehicle(drag, variant)
    # A kick given at 13 s, when the vehicle is doing 30 m/s, is extremely sensitive: a tenth of a degree is
    # the difference between climbing out and falling back. The bracket therefore starts far below the
    # 0.01 deg a faster vehicle would need.
    lo, hi = 1e-7, 12.0
    traj = None
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        traj = tj.integrate(veh, tj.Guidance(vertical_rise_s=a["pitch_start_s"], kick_deg=mid,
                                             terminal_mode="none"), dt=0.1, record_every=1)
        # a kick so large that the vehicle noses over before 83 s is "too low", like any other overshoot
        too_high = traj.t_s[-1] >= a["maxq_s"] and _at(traj, a["maxq_s"])["h"] > a["maxq_h_m"]
        if too_high:
            lo = mid
        else:
            hi = mid
    s = _at(traj, a["maxq_s"])
    t_m1 = next(traj.t_s[k] for k in range(len(traj.t_s)) if traj.mach[k] >= 1.0)
    end = traj.events[-1]
    thrust_end, drag_end = traj.thrust_N[-1], traj.drag_N[-1]
    return dict(liftoff_mass_kg=veh.m0_kg, liftoff_thrust_to_weight=apollo11_engine(variant)["thrust_sl_N"]
                / (veh.m0_kg * G0), kick_deg=traj.kick_deg, mach1_s=t_m1, maxq_s=traj.max_q_t_s, maxq_Pa=traj.max_q_Pa,
                maxq_h_m=traj.max_q_h_m, q_at_83s_Pa=s["q"], v_at_83s_mps=s["v"], mach_at_83s=s["mach"],
                mass_at_83s_kg=s["m"], h_at_83s_m=s["h"],
                gamma_at_83s_deg=s["gamma"], cd_at_83s=drag.cd(s["mach"], s["h"], True),
                oeco_h_m=traj.burnout_h_m, oeco_v_mps=traj.burnout_v_mps, oeco_gamma_deg=traj.burnout_gamma_deg,
                oeco_accel_g=(thrust_end - drag_end) / (end["mass_kg"] * G0),
                drag_loss_mps=traj.drag_loss_mps, gravity_loss_mps=traj.gravity_loss_mps)


def apollo11() -> dict:
    models = {"geometry build-up": aero.geometry_model(saturn5()),
              "book Titan II curve": aero.book_titan2_model(),
              "no drag": aero.constant_model(0.0)}
    out = {k: fly_apollo11(m) for k, m in models.items()}
    out["_variants"] = {v: fly_apollo11(aero.geometry_model(saturn5()), v) for v in VARIANTS[1:]}
    out["_engine"] = apollo11_engine()
    return out


# =========================================================================================== 3. sized designs
#: Book Table 3.4, p.180 ("Design Velocities (in m/s) By Launch Vehicle"), drag column.
TABLE_3_4_DRAG_LOSS = {"Atlas I": 110.0, "Delta 7925": 136.0, "Space Shuttle": 107.0, "Saturn V": 40.0,
                       "Titan IV/Centaur": 156.0}


def sized_design_losses() -> list:
    """The tool's own sized designs, flown both ways. Only Saturn V has a published drag loss to stand
    against; the others show how far the choice of drag model moves a small vehicle against a large one."""
    from launch_vehicle.config_io import load_design
    from launch_vehicle.convergence import size_vehicle
    rows = []
    for path, pub, over in (("validation/saturn5.yaml", 40.0, None), ("validation/falcon9.yaml", None, None),
                            ("validation/electron.yaml", None, None),
                            ("validation/electron.yaml", None, {"fairing.nose_length_over_D": 2.0}),
                            ("examples/example_solid_smallsat.yaml", None, None),
                            ("config/default_design.yaml", None, None)):
        spec = load_design(os.path.join(ROOT, path), os.path.join(ROOT, "config", "engineering_assumptions.yaml"),
                           over)
        res = size_vehicle(spec, keep_history=False)
        g = tj.fly_design(res, drag=aero.model_from_config(spec.mission.get("aerodynamics")))
        t = tj.fly_design(res, drag=aero.book_titan2_model())
        rows.append(dict(design=path + (" with the nose lengthened" if over else ""), glom_kg=res.glom_kg, diameter_m=res.geometry.max_diameter,
                         nose_length_over_D=spec.fairing.nose_length_over_D,
                         converged=bool(g.converged and t.converged), published_drag_loss_mps=pub,
                         geometry=dict(drag_loss_mps=g.drag_loss_mps, max_q_Pa=g.max_q_Pa, max_q_t_s=g.max_q_t_s,
                                       burnout_v_mps=g.burnout_v_mps,
                                       peak_cd=(g.drag_table or {}).get("peak_cd")),
                         titan2=dict(drag_loss_mps=t.drag_loss_mps, max_q_Pa=t.max_q_Pa, max_q_t_s=t.max_q_t_s,
                                     burnout_v_mps=t.burnout_v_mps)))
    return rows


# =========================================================================================== report
def markdown(curves, s5, ap, sized) -> str:
    L = ["# Drag validation data", "",
         "Generated by `tools/validate_drag.py`. **Nothing was tuned.** Read with `docs/DRAG.md`, which says "
         "what these numbers mean.", "", "## 1. Drag coefficient against published curves", ""]
    for c in curves:
        L += [f"### {c['name']}", "", c["note"], "",
              "| Mach | Published Cd | Build-up Cd | Error | friction | nose and flares | base |",
              "|---|---|---|---|---|---|---|"]
        for r in c["rows"]:
            L.append(f"| {r['mach']:.2f} | {r['published']:.3f} | {r['model']:.3f} | {r['error_pct']:+.0f} % | "
                     f"{r['friction']:.3f} | {r['forebody']:.3f} | {r['base']:.3f} |")
        L += ["", f"Mean absolute error **{c['mean_abs_error_pct']:.0f} %**, mean signed error "
                  f"{c['bias_pct']:+.0f} %, worst {c['max_abs_error_pct']:.0f} %. Published peak "
                  f"{c['published_peak']['cd']:.3f} at Mach {c['published_peak']['mach']:.2f}; build-up peak "
                  f"{c['model_peak']['cd']:.3f} at Mach {c['model_peak']['mach']:.2f}.", "",
              "Mean absolute error against the assumed dimension: "
              + "; ".join(f"{k}: {v:.0f} %" for k, v in c["sensitivity"].items()) + ".", ""]
    b = s5["breakdown"]
    L += ["### Saturn V at max-q (one measured point)", "",
          "| | Cd on 79.49 m2 | against measured |", "|---|---|---|",
          f"| Measured axial force, SA-503 (book p.588) | {s5['measured_cd']:.3f} | |",
          f"| Geometry build-up, Mach {s5['mach']:.2f} | {s5['model_cd']:.3f} | {s5['error_pct']:+.0f} % |",
          f"| Book Titan II curve, Mach {s5['mach']:.2f} | {s5['titan2_curve_cd']:.3f} | "
          f"{s5['titan2_error_pct']:+.0f} % |", "",
          f"Build-up terms: friction {b['friction']:.3f}, nose and flares {b['forebody']:.3f}, base "
          f"{b['base']:.3f}. The build-up leaves out the engine fairings and fins, which make the frontal area "
          f"{s5['frontal_area_ratio_with_fairings_and_fins']:.2f} times the core's.", "",
          "## 2. Apollo 11 first-stage ascent, flown from published masses and thrust", "",
          "The pitch kick is chosen so the vehicle is at the published 13,568 m at 83 s. Everything else is an "
          "output.", ""]
    variants, eng = ap.pop("_variants"), ap.pop("_engine")
    L += [f"Engine cross-checks, not used as inputs: the nozzle exit area comes out as five "
          f"{eng['exit_diameter_each_m']:.2f} m exits, and thrust at the max-q altitude as "
          f"{eng['thrust_at_maxq_altitude_N']/1e6:.2f} MN against the 38.55 MN the book reads from NASA's curve "
          f"({100*(eng['thrust_at_maxq_altitude_N']/38.55e6-1):+.1f} %). Five-engine flow "
          f"{eng['mdot_kgs']:,.0f} kg/s; the book's {APOLLO11['mean_flow_kgs']:,.0f} kg/s (p.585) is lower and "
          f"is consistent with a mean over the whole burn, four-engine phase included.", "",
          "| | Flight | " + " | ".join(ap) + " |", "|---|---|" + "---|" * len(ap)]
    a = APOLLO11

    def row(label, flight, key, fmt, scale=1.0):
        L.append(f"| {label} | {flight} | " + " | ".join(format(ap[k][key] * scale, fmt) for k in ap) + " |")
    row("Mach 1 [s]", f"{a['mach1_s']:.1f}", "mach1_s", ".1f")
    row("Time of max-q [s]", f"{a['maxq_s']:.1f}", "maxq_s", ".1f")
    row("Max-q [kPa]", f"{a['maxq_Pa']/1e3:.1f}", "maxq_Pa", ".1f", 1e-3)
    row("Altitude of max-q [km]", f"{a['maxq_h_m']/1e3:.2f}", "maxq_h_m", ".2f", 1e-3)
    row("q at 83 s [kPa]", f"{a['maxq_Pa']/1e3:.1f}", "q_at_83s_Pa", ".1f", 1e-3)
    row("Speed at 83 s [m/s]", f"{a['maxq_v_mps']:.0f}", "v_at_83s_mps", ".0f")
    row("Mach at 83 s", f"{a['maxq_mach']:.2f}", "mach_at_83s", ".2f")
    row("Mass at 83 s [t]", f"{a['maxq_mass_kg']/1e3:.1f} (book's estimate)", "mass_at_83s_kg", ".1f", 1e-3)
    row("Cd flown at 83 s", "0.405 (SA-503)", "cd_at_83s", ".3f")
    row("Acceleration at cutoff [g]", f"{a['max_accel_g']:.2f}", "oeco_accel_g", ".2f")
    row("Drag loss to cutoff [m/s]", "40 to 46", "drag_loss_mps", ".1f")
    row("Speed at cutoff [m/s]", "not collected", "oeco_v_mps", ".0f")
    row("Altitude at cutoff [km]", "not collected", "oeco_h_m", ".1f", 1e-3)
    row("Lift-off thrust to weight", "", "liftoff_thrust_to_weight", ".3f")
    L += ["", "How much the inputs matter (geometry build-up in each case). Only the flight up to 83 s is "
          "compared here: one pitch kick fixes one point of the trajectory, and what a single-kick gravity turn "
          "does after that point is not what the real pitch programme did.", "",
          "| Variant | Lift-off mass [t] | Lift-off T/W | Mach 1 [s] | Altitude at 83 s [km] | "
          "Speed at 83 s [m/s] | Mach at 83 s | q at 83 s [kPa] | Flight path angle at 83 s [deg] |",
          "|---|---|---|---|---|---|---|---|---|"]
    for name, v in [("nominal", ap["geometry build-up"])] + list(variants.items()):
        L.append(f"| {name} | {v['liftoff_mass_kg']/1e3:,.1f} | {v['liftoff_thrust_to_weight']:.3f} | "
                 f"{v['mach1_s']:.1f} | {v['h_at_83s_m']/1e3:.2f} | {v['v_at_83s_mps']:.0f} | "
                 f"{v['mach_at_83s']:.2f} | {v['q_at_83s_Pa']/1e3:.1f} | {v['gamma_at_83s_deg']:.0f} |")
    L.append(f"| flight | | | {a['mach1_s']:.1f} | {a['maxq_h_m']/1e3:.2f} | {a['maxq_v_mps']:.0f} | "
             f"{a['maxq_mach']:.2f} | {a['maxq_Pa']/1e3:.1f} | not collected |")
    low = [n for n, v in variants.items() if v["h_at_83s_m"] < a["maxq_h_m"] - 200.0]
    if low:
        L += ["", "A variant whose altitude at 83 s is below 13.57 km could not be flown through the published "
              "point with any kick, even a vertical climb: " + ", ".join(low) + ". At that lift-off mass the "
              "vehicle is too slow off the pad to be where the flight was, which bounds the real lift-off mass "
              "from above."]
    L += ["", "## 3. The tool's sized designs, flown on both drag models", "",
          "| Design | Lift-off mass [t] | Diameter [m] | Nose L/D | Peak Cd | Drag loss, build-up [m/s] | "
          "Drag loss, Titan II curve [m/s] | Published [m/s] | Burnout speed change [m/s] |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in sized:
        g, t = r["geometry"], r["titan2"]
        L.append(f"| `{r['design']}`{'' if r['converged'] else ' (ascent did not close)'} | "
                 f"{r['glom_kg']/1e3:,.1f} | {r['diameter_m']:.2f} | {r['nose_length_over_D']:.2f} | "
                 f"{(g['peak_cd'] or float('nan')):.2f} | {g['drag_loss_mps']:.0f} | {t['drag_loss_mps']:.0f} | "
                 f"{'' if r['published_drag_loss_mps'] is None else format(r['published_drag_loss_mps'], '.0f')} | "
                 f"{g['burnout_v_mps'] - t['burnout_v_mps']:+.0f} |")
    L += ["", "Published drag losses, book Table 3.4 (p.180): "
          + ", ".join(f"{k} {v:.0f} m/s" for k, v in TABLE_3_4_DRAG_LOSS.items()) + ".", ""]
    return "\n".join(L)


def main() -> int:
    curves, s5, ap, sized = all_curves(), saturn5_point(), apollo11(), sized_design_losses()
    text = markdown(curves, s5, ap, sized)
    print(text)
    with open(os.path.join(ROOT, "docs", "DRAG_VALIDATION_DATA.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    out = os.path.join(ROOT, "outputs", "validation")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "drag_validation.json"), "w", encoding="utf-8") as fh:
        json.dump(dict(curves=curves, saturn5_point=s5, apollo11=ap, sized=sized), fh, indent=1, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
