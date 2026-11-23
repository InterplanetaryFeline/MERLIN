"""Fly an exported MERLIN vehicle in Kerbal Space Program along MERLIN's own trajectory, and compare.

    python tools/ksp_fly.py <design.yaml> [key=value ...]

KSP must be running the save that holds the exported craft, at the Space Centre or in flight, with the kRPC server
started (kRPC 0.6). The design is sized and flown by MERLIN first; the craft of the same name is then put on the
launch pad and flown by kRPC's autopilot with the thrust pointed where MERLIN pointed it - flight-path angle plus
angle of attack, gamma + alpha, against time - staging when the active engines burn out and lighting the next
stage after MERLIN's coast. Nothing is steered to a target: the point is to see whether KSP, given the same
vehicle and the same steering, flies the same ascent. The comparison is written to
outputs/ksp_export/<tag>_flight.json and printed.

Overrides are dotted paths as in load_design, e.g. vehicle.optimise_dv_split=false.
"""
from __future__ import annotations
import bisect
import json
import math
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))


def _value(text):
    low = text.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return float(text)
    except ValueError:
        return text


def merlin_ascent(design, overrides):
    from launch_vehicle.config_io import load_design
    from launch_vehicle.convergence import size_vehicle
    from launch_vehicle import trajectory as tr, ksp_export as kx
    spec = load_design(design, os.path.join(ROOT, "config", "engineering_assumptions.yaml"), overrides)
    res = size_vehicle(spec, keep_history=False)
    t = tr.fly_design(res)
    veh = tr.ascent_vehicle_from_result(res)
    coasts = [b.duration_s for b in veh.burns if not b.powered]
    return res, kx._tag(spec.name), dict(t=list(t.t_s), gamma=list(t.gamma_deg), alpha=list(t.alpha_deg),
                                         h=list(t.h_m), v=list(t.v_mps), m=list(t.m_kg), coasts=coasts,
                                         n_stages=len(res.stages))


def _at(series, ts, t):
    if t <= ts[0]:
        return series[0]
    if t >= ts[-1]:
        return series[-1]
    i = bisect.bisect_right(ts, t) - 1
    f = (t - ts[i]) / (ts[i + 1] - ts[i])
    return series[i] * (1 - f) + series[i + 1] * f


def fly(M, craft, kick_time_s=10.0, timeout_s=1500.0, log=print):
    import krpc
    conn = krpc.connect(name="MERLIN ksp_fly", address="127.0.0.1", rpc_port=50000, stream_port=50001)
    sc = conn.space_center
    sc.launch_vessel("VAB", craft, "LaunchPad", [], True, "")
    time.sleep(10)
    v = sc.active_vessel
    T = M["t"]
    pitch = [g + a for g, a in zip(M["gamma"], M["alpha"])]
    ap = v.auto_pilot
    ap.reference_frame = v.surface_reference_frame
    ap.target_pitch_and_heading(90, 90)
    ap.target_roll = float("nan")
    ap.engaged = True
    v.control.sas = False
    v.control.throttle = 1.0
    ut = conn.add_stream(getattr, sc, "ut")
    t0 = ut()
    v.control.activate_next_stage()                         # stage 1 ignition
    stage, out_at, hist, events, last = 1, None, [], [], -1e9
    body = v.orbit.body
    while True:
        t = ut() - t0
        v = sc.active_vessel
        ap = v.auto_pilot
        if t > kick_time_s:
            ap.target_pitch_and_heading(max(_at(pitch, T, t), -20.0), 90)
        burning = [e for e in v.parts.engines if e.active]
        if out_at is None and burning and all(not e.has_fuel for e in burning):
            out_at = t
            events.append((t, f"stage {stage} burnout"))
            if stage == M["n_stages"]:
                break
            v.control.activate_next_stage()                 # separation
            events.append((t, f"stage {stage} separation"))
        if out_at is not None and t >= out_at + M["coasts"][stage - 1]:
            stage += 1
            sc.active_vessel.control.activate_next_stage()  # next stage ignition (and the fairing, if due)
            sc.active_vessel.control.throttle = 1.0
            events.append((t, f"stage {stage} ignition"))
            out_at = None
        if t - last >= 1.0:
            o = v.orbit
            fl = v.flight(body.reference_frame)
            hist.append(dict(t=t, alt=fl.mean_altitude, surf_speed=fl.speed, vs=fl.vertical_speed,
                             mass=v.mass, thrust=v.thrust, ap=o.apoapsis_altitude, pe=o.periapsis_altitude,
                             pitch_cmd=_at(pitch, T, t), pitch=v.flight(v.surface_reference_frame).pitch,
                             stage=stage))
            last = t
        if t > timeout_s or (v.situation.name in ("splashed", "landed") and t > 30):
            events.append((t, f"stopped: {v.situation.name}"))
            break
        time.sleep(0.05)
    sc.active_vessel.control.throttle = 0.0
    sc.active_vessel.auto_pilot.engaged = False
    o = sc.active_vessel.orbit
    return hist, events, dict(apoapsis_m=o.apoapsis_altitude, periapsis_m=o.periapsis_altitude,
                              inclination_deg=math.degrees(o.inclination))


def compare(M, hist, every_s=20.0):
    rows = []
    t_end = min(M["t"][-1], hist[-1]["t"])
    t = every_s
    while t <= t_end + 1e-9:
        h = min(hist, key=lambda r: abs(r["t"] - t))
        rows.append(dict(t=t, h_merlin=_at(M["h"], M["t"], t), h_ksp=h["alt"], v_merlin=_at(M["v"], M["t"], t),
                         v_ksp=h["surf_speed"], m_merlin=_at(M["m"], M["t"], t), m_ksp=h["mass"]))
        t += every_s
    return rows


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    design = sys.argv[1]
    ov = {k: _value(v) for k, v in (a.split("=", 1) for a in sys.argv[2:])}
    res, tag, M = merlin_ascent(design, ov)
    print(f"MERLIN: {len(M['t'])} points, ends at {M['t'][-1]:.1f} s, {M['h'][-1] / 1e3:.1f} km, {M['v'][-1]:.0f} m/s",
          flush=True)
    hist, events, orbit = fly(M, f"{tag}_MERLIN")
    rows = compare(M, hist)
    for t, name in events:
        print(f"  {t:7.1f} s  {name}")
    print("   t [s] | altitude MERLIN / KSP [km] | speed MERLIN / KSP [m/s] | mass MERLIN / KSP [kg]")
    for r in rows:
        print(f"  {r['t']:6.0f} | {r['h_merlin'] / 1e3:8.1f} / {r['h_ksp'] / 1e3:8.1f} | {r['v_merlin']:7.0f} / "
              f"{r['v_ksp']:7.0f} | {r['m_merlin']:9.0f} / {r['m_ksp']:9.0f}")
    print("orbit after burnout:", orbit)
    out = os.path.join(ROOT, "outputs", "ksp_export", f"{tag}_flight.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(dict(design=design, overrides=ov, merlin=M, ksp=hist, events=events, orbit=orbit,
                       comparison=rows), fh)
    print("written", out)
