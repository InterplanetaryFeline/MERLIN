"""Check an exported MERLIN vehicle inside a running KSP, through kRPC.

    python tools/ksp_verify.py <craft name without .craft> [--fly]

KSP must be running a save at the Space Centre with the kRPC server started. The script launches the craft from
the VAB onto the launch pad, reads back what KSP actually built - parts, masses, propellant, engines, staging -
and prints it beside what the export intended (from the export's check, written next to the craft by the
exporter). With --fly it also flies a gravity turn and records the ascent, so the flown vehicle can be compared
with MERLIN's own trajectory.
"""
from __future__ import annotations
import json
import math
import os
import sys
import time

import krpc


def connect():
    return krpc.connect(name="MERLIN export check", address="127.0.0.1", rpc_port=50000, stream_port=50001)


def read_vehicle(conn):
    sc = conn.space_center
    v = sc.active_vessel
    parts = v.parts
    out = dict(name=v.name, mass_kg=v.mass, dry_mass_kg=v.dry_mass, n_parts=len(parts.all), stages={},
               engines=[], resources={})
    for p in parts.all:
        out["resources"].setdefault(p.title, {})
        for r in p.resources.all:
            out["resources"][p.title][r.name] = dict(amount=r.amount, max=r.max, density_kg_per_unit=r.density)
    for e in parts.engines:
        p = e.part
        out["engines"].append(dict(part=p.title, stage=p.stage, max_vac_thrust_N=e.max_vacuum_thrust,
                                   isp_vac_s=e.vacuum_specific_impulse, isp_sl_s=e.kerbin_sea_level_specific_impulse,
                                   propellants=list(e.propellant_names), ratios=dict(e.propellant_ratios)))
    for p in parts.all:
        out["stages"].setdefault(str(p.stage), []).append(p.title)
    out["decouplers"] = [dict(part=d.part.title, stage=d.part.stage) for d in parts.decouplers]
    out["fairings"] = [dict(part=f.part.title, stage=f.part.stage) for f in parts.fairings]
    out["current_stage"] = v.control.current_stage
    # the stock launch clamps the export adds stay on the pad; MERLIN's lift-off mass is the vehicle without them
    clamps = [p for p in parts.all if p.name.startswith("launchClamp")]
    out["n_clamps"] = len(clamps)
    out["mass_without_clamps_kg"] = v.mass - sum(p.mass for p in clamps)
    return out


def stage_masses(conn):
    """Mass of the vessel at each decouple stage, as KSP's own resources and part masses give it."""
    v = conn.space_center.active_vessel
    rows = {}
    for p in v.parts.all:
        rows.setdefault(p.decouple_stage, 0.0)
        rows[p.decouple_stage] += p.mass
    return rows


def fly(conn, kick_deg=0.25, rise_s=10.0, target_ap_m=400e3, log_every=1.0, timeout_s=900):
    """A plain gravity turn: vertical rise, a pitch kick, then hold prograde. Stages when the active stage
    runs dry. Returns the recorded history."""
    sc = conn.space_center
    v = sc.active_vessel
    ap = v.auto_pilot
    ref = v.surface_reference_frame
    flight = v.flight(v.orbit.body.reference_frame)
    v.control.throttle = 1.0
    v.control.sas = False
    ap.reference_frame = ref
    ap.engaged = True
    ap.target_pitch_and_heading(90, 90)
    t0 = sc.ut
    hist = []
    v.control.activate_next_stage()                     # ignition
    kicked, prograde = False, False
    last = -1e9
    while sc.ut - t0 < timeout_s:
        t = sc.ut - t0
        if t > rise_s and not kicked:
            ap.target_pitch_and_heading(90 - kick_deg, 90)
            kicked = True
        if kicked and not prograde and t > rise_s + 5:
            prograde = True
        if prograde:
            d = flight.velocity
            spd = math.sqrt(sum(x * x for x in d)) or 1.0
            # pitch of the surface velocity above the horizon
            fl = v.flight(ref)
            ap.target_pitch_and_heading(max(fl.pitch if spd < 50 else math.degrees(math.asin(
                max(-1.0, min(1.0, v.flight(v.orbit.body.reference_frame).vertical_speed / spd)))), -5), 90)
        # stage when every engine of the current stage is out of propellant
        active = [e for e in v.parts.engines if e.active]
        if active and all(not e.has_fuel for e in active):
            v.control.activate_next_stage()
            time.sleep(0.5)
        if not active and v.control.current_stage > 0:
            v.control.activate_next_stage()
            time.sleep(0.5)
        if t - last >= log_every:
            o = v.orbit
            hist.append(dict(t=t, alt=flight.mean_altitude, speed=v.flight(v.orbit.body.non_rotating_reference_frame).speed,
                             surf_speed=flight.speed, q=flight.dynamic_pressure, mass=v.mass,
                             thrust=v.thrust, stage=v.control.current_stage, ap=o.apoapsis_altitude,
                             pe=o.periapsis_altitude, pitch=v.flight(ref).pitch))
            last = t
        if v.control.current_stage <= 0 and not [e for e in v.parts.engines if e.has_fuel and e.active]:
            if not any(e.has_fuel for e in v.parts.engines):
                break
        time.sleep(0.05)
    v.control.throttle = 0.0
    ap.engaged = False
    return hist


def fly_mechjeb(conn, altitude_m=400e3, inclination_deg=28.5, log_every=1.0, timeout_s=1500):
    """Fly to orbit with MechJeb's ascent autopilot (through kRPC's MechJeb service), recording the ascent."""
    sc = conn.space_center
    v = sc.active_vessel
    mj = conn.mech_jeb
    asc = mj.ascent_autopilot
    asc.desired_orbit_altitude = altitude_m
    asc.desired_inclination = inclination_deg
    asc.autostage = True
    asc.enabled = True
    t0 = sc.ut
    v.control.activate_next_stage()
    hist, last = [], -1e9
    nrf = v.orbit.body.non_rotating_reference_frame
    while sc.ut - t0 < timeout_s:
        v = sc.active_vessel
        t = sc.ut - t0
        if t - last >= log_every:
            fl = v.flight(v.orbit.body.reference_frame)
            o = v.orbit
            hist.append(dict(t=t, alt=fl.mean_altitude, speed=v.flight(nrf).speed, surf_speed=fl.speed,
                             q=fl.dynamic_pressure, mass=v.mass, thrust=v.thrust, stage=v.control.current_stage,
                             ap=o.apoapsis_altitude, pe=o.periapsis_altitude, inc=math.degrees(o.inclination),
                             pitch=v.flight(v.surface_reference_frame).pitch))
            last = t
        if not asc.enabled:
            break
        time.sleep(0.2)
    return hist


if __name__ == "__main__":
    name = sys.argv[1]
    conn = connect()
    sc = conn.space_center
    try:
        sc.launch_vessel("VAB", name, "LaunchPad", [], True, "")
    except Exception as ex:                                       # noqa: BLE001
        print("launch failed:", ex)
        raise
    time.sleep(8)
    data = read_vehicle(conn)
    data["mass_by_decouple_stage_kg"] = stage_masses(conn)
    print(json.dumps(data, indent=1, default=str))
    if "--fly" in sys.argv or "--mechjeb" in sys.argv:
        hist = fly_mechjeb(conn) if "--mechjeb" in sys.argv else fly(conn)
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "outputs", "ksp_export", "flight.json")
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(hist, fh)
        last = hist[-1]
        print("END", json.dumps(last))
