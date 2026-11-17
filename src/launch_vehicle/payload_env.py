"""Payload environment: the quasi-static load factors a payload customer is given (book Chapter 11).

Section 11.4 describes what a payload planner's guide contains and why: the spacecraft owner "is your paying
customer", and what they need to start designing is a table of design load factors - quasi-static loads, or
QSLs - by flight event, axial and lateral. The book prints two real ones, Ariane 5's (Table 11.3) and
Atlas V's (Table 11.4), and gives the range a preliminary design should expect: "Typical values are around
4-8 g0 axial and 1.5-3 g0 lateral" (p.691).

This module produces that table for the designed vehicle. The quasi-static part is computed - axial load factor
from the trajectory, lateral from the Chapter 9 trim - and that is the part this tool can honestly produce.

What a real planner's guide has that this does not
---------------------------------------------------
The dynamic increment. A published QSL is "the most severe combination of dynamic and steady state
acceleration values" (p.690), and the dynamic half comes from a coupled-loads analysis of the vehicle and
spacecraft together, which needs structural modes this tool does not compute. The increments used here are
taken from the two real tables the book prints, applied as stand-ins and labelled as such on every row.

The acoustic and shock specification. Chapter 11 describes ignition overpressure, lift-off acoustics, buffet
and pyrotechnic shock at length, but gives no prediction method for any of them - of ignition overpressure it
says plainly that it "is difficult to estimate" and that one scales model tests. There is no sound pressure
level here, because there is no equation in this book to produce one.

The frequency requirement. Section 11.5.3 gives the rule - a spacecraft's natural frequencies should be at
least twice the launch vehicle's - but the launch vehicle's structural modes are not computed by this tool, so
the number that would go in the guide cannot be issued.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# Book Sec. 11.4, p.691: what a preliminary payload design should expect.
TYPICAL_AXIAL_G = (4.0, 8.0)
TYPICAL_LATERAL_G = (1.5, 3.0)

# Book Table 11.3, p.691 (ESA) and Table 11.4, p.692 (ULA). Kept whole so the generated table can be shown
# beside real ones rather than asserted into a vacuum.
ARIANE5_QSL = [
    # event, longitudinal static (negative = compression), longitudinal dynamic +/-, lateral static+dynamic +/-
    ("Lift-off", -1.7, 1.5, 2.0),
    ("Max-q", -2.7, 0.5, 2.0),
    ("SRB end of flight", -4.55, 1.45, 1.0),
    ("Main core thrust tail-off", -0.2, 1.4, 0.25),
    ("SRB jettison (max tension)", 2.5, 0.0, 0.9),
]
ATLAS5_QSL = [
    # event, axial quasi-static, axial dynamic +/-, lateral +/-
    ("Lift-off", 1.8, 2.0, 2.0),
    ("Flight winds", 2.8, 0.5, 1.6),
    ("Strap-on separation", 3.3, 0.5, 0.5),
    ("BECO (max axial)", 5.5, 1.0, 0.5),
    ("BECO (max lateral)", 2.5, 1.0, 1.5),
    ("MECO (max axial)", 4.5, 1.0, 0.3),
    ("MECO (max lateral)", 2.0, 0.0, 0.6),
]
# The dynamic increments used as stand-ins, taken from the two tables above. Lift-off is the loudest and
# shakiest moment of the flight and carries the largest increment in both real guides; the quiet vacuum
# events carry the smallest.
DYNAMIC_AXIAL_G = {"liftoff": 2.0, "max_q": 0.5, "burnout": 1.0, "separation": 0.5, "other": 1.0}
DYNAMIC_LATERAL_G = {"liftoff": 2.0, "max_q": 1.6, "burnout": 0.5, "separation": 0.5, "other": 0.6}

MIN_FREQUENCY_RATIO = 2.0          # book Sec. 11.5.3: spacecraft modes at least twice the vehicle's


@dataclass
class QSLRow:
    event: str
    t_s: float
    kind: str                       # liftoff | max_q | burnout | separation | other
    axial_static_g: float           # computed: positive = compression
    axial_dynamic_g: float          # stand-in, from the real tables
    lateral_static_g: float         # computed where a load case provides it, else 0
    lateral_dynamic_g: float        # stand-in
    source: str = ""

    @property
    def axial_total_g(self) -> float:
        return self.axial_static_g + self.axial_dynamic_g

    @property
    def lateral_total_g(self) -> float:
        return self.lateral_static_g + self.lateral_dynamic_g


@dataclass
class PayloadEnvironment:
    rows: list = field(default_factory=list)
    payload_mass_kg: float = 0.0
    design_axial_g: float = 0.0
    design_lateral_g: float = 0.0
    governing_axial_event: str = ""
    governing_lateral_event: str = ""
    within_typical: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)


def _classify(name: str) -> str:
    n = name.lower()
    if "lift" in n or n.startswith("stage 1 start"):
        return "liftoff"
    if "max-q" in n or "max q" in n:
        return "max_q"
    if "burnout" in n:
        return "burnout"
    if "jettison" in n or "separation" in n or "start" in n:
        return "separation"
    return "other"


def build(res, traj=None, load_cases: dict | None = None,
          dynamic_axial: dict | None = None, dynamic_lateral: dict | None = None) -> PayloadEnvironment:
    """The QSL table for this vehicle, by flight event.

    Axial load factors come from the trajectory, which is the only place the vehicle's own accelerations are
    known; lateral from the Chapter 9 flight load cases, which are the only place a side load is computed.
    """
    from .loads import axial_load_factor

    da = dict(DYNAMIC_AXIAL_G, **(dynamic_axial or {}))
    dl = dict(DYNAMIC_LATERAL_G, **(dynamic_lateral or {}))
    out = PayloadEnvironment(payload_mass_kg=res.payload_mass_kg)

    lateral_by_kind = {}
    for _k, c in (load_cases or {}).items():
        if hasattr(c, "stations") and getattr(c, "condition", "") == "flight":
            kind = "max_q" if "max-q" in c.name.lower() else "other"
            lateral_by_kind[kind] = max(lateral_by_kind.get(kind, 0.0), abs(c.state.get("n_z", 0.0)))
        elif hasattr(c, "stations") and "Lift-off" in getattr(c, "name", ""):
            lateral_by_kind["liftoff"] = max(lateral_by_kind.get("liftoff", 0.0), 0.0)

    if traj is not None and traj.t_s:
        events = [dict(t_s=0.0, name="Lift-off")] + list(traj.events)
        imax = max(range(len(traj.q_Pa)), key=lambda k: traj.q_Pa[k]) if traj.q_Pa else 0
        events.append(dict(t_s=traj.t_s[imax], name="Max-q"))
        taken = []
        for ev in sorted(events, key=lambda e: e["t_s"]):
            name = ev["name"]
            if "pitch kick" in name.lower():
                continue                                      # a guidance event, not one the payload feels
            k = min(range(len(traj.t_s)), key=lambda i: abs(traj.t_s[i] - ev["t_s"]))
            kind = _classify(name)
            n_x = axial_load_factor(traj, k)
            if n_x <= 0.01 and kind != "liftoff":
                continue
            # several named events share one instant (burnout, jettison and the next stage's start all happen
            # at staging); the payload feels one event there, so the first name wins
            if any(abs(ev["t_s"] - t) < 0.5 for t in taken):
                continue
            taken.append(ev["t_s"])
            out.rows.append(QSLRow(
                event=name, t_s=traj.t_s[k], kind=kind, axial_static_g=n_x,
                axial_dynamic_g=da.get(kind, da["other"]),
                lateral_static_g=lateral_by_kind.get(kind, 0.0),
                lateral_dynamic_g=dl.get(kind, dl["other"]),
                source="axial from the flown trajectory; lateral from the Chapter 9 load case where one exists"))

    if not out.rows:
        out.notes.append("No trajectory was flown, so there are no flight events to tabulate. The quasi-static "
                         "part of a payload environment comes from the vehicle's own acceleration history and "
                         "cannot be produced without one.")
        return out

    ax = max(out.rows, key=lambda r: r.axial_total_g)
    lat = max(out.rows, key=lambda r: r.lateral_total_g)
    out.design_axial_g, out.governing_axial_event = ax.axial_total_g, ax.event
    out.design_lateral_g, out.governing_lateral_event = lat.lateral_total_g, lat.event
    out.within_typical = dict(
        axial=TYPICAL_AXIAL_G[0] <= out.design_axial_g <= TYPICAL_AXIAL_G[1],
        lateral=TYPICAL_LATERAL_G[0] <= out.design_lateral_g <= TYPICAL_LATERAL_G[1],
        axial_range=TYPICAL_AXIAL_G, lateral_range=TYPICAL_LATERAL_G)
    out.notes = _notes(out)
    return out


def _notes(out: PayloadEnvironment) -> list:
    n = [f"Design load factors for this vehicle: <b>{out.design_axial_g:.1f} g axial</b> "
         f"({out.governing_axial_event}) and <b>{out.design_lateral_g:.1f} g lateral</b> "
         f"({out.governing_lateral_event}), each the worst sum of static and dynamic over all events.",
         f"The book's expectation for a preliminary design is {TYPICAL_AXIAL_G[0]:.0f}-{TYPICAL_AXIAL_G[1]:.0f} g "
         f"axial and {TYPICAL_LATERAL_G[0]:.1f}-{TYPICAL_LATERAL_G[1]:.0f} g lateral (p.691). This vehicle is "
         + ("inside" if out.within_typical.get("axial") else "OUTSIDE") + " that range axially and "
         + ("inside" if out.within_typical.get("lateral") else "OUTSIDE") + " it laterally.",
         "The lateral load matters more than its size suggests: \"for design purposes, the highest QSLs are "
         "the axial compressive loads, but lateral loads bend the structure and tend to be worse than axial "
         "even though their magnitude is less\", because spacecraft are long and slender (p.690).",
         "<b>The dynamic column is not computed.</b> A published QSL is the worst combination of dynamic and "
         "steady-state acceleration, and the dynamic half comes from a coupled-loads analysis of the vehicle "
         "and the spacecraft together. This tool has no structural modes, so the increments here are taken "
         "from the two real guides the book prints (Ariane 5's Table 11.3 and Atlas V's Table 11.4) and are "
         "stand-ins, not predictions.",
         "<b>No acoustic or shock specification.</b> Chapter 11 describes ignition overpressure, lift-off "
         "acoustics, buffet and pyrotechnic shock without giving a prediction method for any of them - of "
         "ignition overpressure it says it \"is difficult to estimate\" and that one scales model tests. A real "
         "payload guide specifies all four, and none can be produced from this book.",
         f"<b>No frequency requirement.</b> Sec. 11.5.3 asks that a spacecraft's natural frequencies be at "
         f"least {MIN_FREQUENCY_RATIO:.0f}x the launch vehicle's, but this tool computes no structural modes "
         f"for the vehicle, so the number that would go in the guide cannot be issued."]
    return n
