"""Static stability and thrust vector control authority (book Chapter 12, Secs. 12.2 and 12.3.6).

A launch vehicle without fins is statically unstable, so the question is never "is it stable" but "can the
control system hold it". Chapter 12 gives three numerical rules of thumb for that, and this module evaluates
all three along the flown ascent:

  1. Controllability ratio      M_delta / M_A >= 2.0, "typically > 1, although values less than 1/2 have been
                                observed in Delta III vehicles" (Sec. 12.3.6, rule 1)
  2. Time to double             T2 = ln(2) sqrt(I_y / M_A) > 0.5 s, "if less, very fast actuators are needed
                                to stabilize the vehicle" (Eq. 12.4, rule 2)
  3. Steady-state deflection    the gimbal angle needed to balance the aerodynamic moment "should not exceed
                                2 deg. This provides margin for steering and wind corrections" (rule 3)

plus the control bandwidth f_b = sqrt(M_A / I_y) / (2 pi) that rule 9 asks to be kept a factor of ten away from
the structural frequencies - which this tool does not compute, so the number is reported and the separation is
left to the reader.

The deflection budget follows Table 12.4: the steady-state wind term is computed here from the vehicle's own
trim, and the other four contributors are root-sum-squared with it, as the book's table does.

What is deliberately absent
---------------------------
Slosh, body bending, tail-wags-dog and POGO all appear in Chapter 12 as phenomena, and the chapter explicitly
declines to model the first: "The sloshing situation can get very complicated, and analytical analysis is
beyond the scope of this book" (p.778). There is no slosh frequency, no bending mode and no root locus here,
because the book supplies no equation for any of them and inventing one would be worse than the gap.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .loads import G0

# Book Sec. 12.3.6 rules of thumb
MIN_CONTROLLABILITY_RATIO = 2.0
MIN_TIME_TO_DOUBLE_S = 0.5
MAX_STEADY_GIMBAL_DEG = 2.0
# Book Table 12.4, the "260-in. Solid/S-IVB Apollo" column: the deflection contributors other than the
# steady-state wind, which is computed from the vehicle itself. These are one NASA study's numbers for one
# family of vehicles, not general requirements.
TABLE_12_4_CONTRIBUTORS_DEG = {"wind gusts (3 sigma)": 0.15, "thrust misalignment (3 sigma)": 0.25,
                               "thrust and weights (3 sigma)": 0.15, "pitch programme (maximum)": 0.50}


def time_to_double_s(I_pitch_kg_m2: float, M_aero_Nm: float) -> float:
    """Eq. 12.4: T2 = ln(2) sqrt(I_y / M_A).

    M_A is the aerodynamic pitching moment about the centre of mass, and it must be the DESTABILISING one -
    the expression has no meaning for a stable vehicle, which does not diverge at all. Infinity is returned in
    that case rather than a complex number.
    """
    if M_aero_Nm <= 0 or I_pitch_kg_m2 <= 0:
        return math.inf
    return math.log(2.0) * math.sqrt(I_pitch_kg_m2 / M_aero_Nm)


def bandwidth_Hz(I_pitch_kg_m2: float, M_aero_Nm: float) -> float:
    """Sec. 12.3.6 rule 9: f_b = sqrt(M_A / I_y) / (2 pi)."""
    if M_aero_Nm <= 0 or I_pitch_kg_m2 <= 0:
        return 0.0
    return math.sqrt(M_aero_Nm / I_pitch_kg_m2) / (2.0 * math.pi)


def control_moment_Nm(thrust_N: float, arm_m: float, delta_max_deg: float,
                      gimballed_fraction: float = 1.0) -> float:
    """The pitching moment the engines can produce at full travel: T sin(delta) l_c (book Eq. 6:48's T l_c sin d).

    `gimballed_fraction` is the share of the thrust that is actually steerable - the Saturn V gimballed four of
    its five F-1s, so 0.8 there (Sec. 9.2.7).
    """
    return gimballed_fraction * thrust_N * math.sin(math.radians(delta_max_deg)) * arm_m


def trim_deflection_deg(M_aero_Nm: float, thrust_N: float, arm_m: float,
                        gimballed_fraction: float = 1.0) -> float:
    """The steady-state gimbal angle that balances the aerodynamic moment."""
    denom = gimballed_fraction * thrust_N * arm_m
    if denom <= 0:
        return float("nan")
    s = M_aero_Nm / denom
    return math.degrees(math.asin(s)) if abs(s) <= 1.0 else float("inf")


def deflection_budget(trim_deg: float, contributors_deg: dict | None = None) -> dict:
    """Table 12.4: the deflection contributors root-sum-squared.

    "RSSing is an accepted method to estimate the 'effective' value of a group of measurements or components,
    under the assumption that they do not all occur simultaneously. If they all happened to be simultaneous, we
    would simply total the columns" - so both the RSS and the arithmetic total are reported, as the book does.
    """
    terms = dict(contributors_deg or TABLE_12_4_CONTRIBUTORS_DEG)
    terms = {"steady-state wind (this vehicle's trim)": abs(trim_deg), **terms}
    rss = math.sqrt(sum(v * v for v in terms.values()))
    return dict(terms=terms, rss_deg=rss, worst_case_total_deg=sum(terms.values()))


@dataclass
class ControlPoint:
    t_s: float
    mach: float
    q_Pa: float
    alpha_deg: float
    mass_kg: float
    I_pitch_kg_m2: float
    z_cm_m: float
    z_cp_m: float
    arm_m: float
    thrust_N: float
    M_aero_Nm: float
    M_delta_Nm: float
    controllability: float
    t_double_s: float
    bandwidth_Hz: float
    trim_deg: float
    stable: bool


@dataclass
class ControlAssessment:
    points: list = field(default_factory=list)
    delta_max_deg: float = 0.0
    gimballed_fraction: float = 1.0
    budget: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def worst(self, attr: str, smallest: bool = True):
        if not self.points:
            return None
        return (min if smallest else max)(self.points, key=lambda p: getattr(p, attr))


def assess(res, traj, cp_rows: list, delta_max_deg: float = 5.0, gimballed_fraction: float = 1.0,
           contributors_deg: dict | None = None) -> ControlAssessment:
    """Evaluate the three rules of thumb along the atmospheric ascent.

    `cp_rows` are the rows of aerodynamics.cp_over_trajectory, which already carry the normal-force slope, the
    centre of pressure and the centre of mass at each point.
    """
    from .aerodynamics import normal_force_buildup
    from .loads import _items_at, _gimbal_plane_z, gust_alpha_rad
    from .mass_properties import inertia_of

    geom = res.geometry
    sref = math.pi * geom.max_diameter ** 2 / 4.0
    z_gimbal = _gimbal_plane_z(res, geom)
    out = ControlAssessment(delta_max_deg=delta_max_deg, gimballed_fraction=gimballed_fraction)

    for row in cp_rows:
        k = min(range(len(traj.t_s)), key=lambda i: abs(traj.t_s[i] - row["t_s"]))
        alpha = gust_alpha_rad(traj.v_mps[k], traj.h_m[k])
        thrust = traj.thrust_N[k] if traj.thrust_N else 0.0
        if traj.thrust_N and thrust <= 0.0:
            continue                          # a coast between stages: no gimbal to steer with, and the check is of one
        try:
            items, _n, _s, _b = _items_at(res, traj, k)
        except Exception:                                        # noqa: BLE001
            continue
        I_pitch = inertia_of(items, row["z_cm_m"])["J_pitch"]
        # M_A = CNa alpha q Sref (z_cp - z_cm): positive when the normal force sits forward of the CM and so
        # drives the angle of attack further open, which is the book's definition of unstable (p.357)
        M_aero = row["cna_per_rad"] * alpha * row["q_Pa"] * sref * (row["z_cp_m"] - row["z_cm_m"])
        arm = row["z_cm_m"] - z_gimbal
        M_delta = control_moment_Nm(thrust, arm, delta_max_deg, gimballed_fraction)
        out.points.append(ControlPoint(
            t_s=row["t_s"], mach=row["mach"], q_Pa=row["q_Pa"], alpha_deg=math.degrees(alpha),
            mass_kg=row["mass_kg"], I_pitch_kg_m2=I_pitch, z_cm_m=row["z_cm_m"], z_cp_m=row["z_cp_m"],
            arm_m=arm, thrust_N=thrust, M_aero_Nm=M_aero, M_delta_Nm=M_delta,
            controllability=(M_delta / M_aero) if M_aero > 0 else math.inf,
            t_double_s=time_to_double_s(I_pitch, M_aero), bandwidth_Hz=bandwidth_Hz(I_pitch, M_aero),
            trim_deg=trim_deflection_deg(M_aero, thrust, arm, gimballed_fraction),
            stable=M_aero <= 0))

    if not out.points:
        out.notes.append("No atmospheric points could be assessed, so there is nothing to report here.")
        return out

    worst_c = out.worst("controllability")
    worst_t = out.worst("t_double_s")
    worst_d = out.worst("trim_deg", smallest=False)
    out.budget = deflection_budget(worst_d.trim_deg, contributors_deg)
    out.checks = [
        dict(rule="Controllability ratio M_delta / M_A", source="book Sec. 12.3.6 rule 1",
             limit=f">= {MIN_CONTROLLABILITY_RATIO:.1f}", value=f"{worst_c.controllability:.2f}",
             at=f"t = {worst_c.t_s:,.0f} s", passed=worst_c.controllability >= MIN_CONTROLLABILITY_RATIO),
        dict(rule="Time to double", source="book Eq. 12.4 and rule 2",
             limit=f"> {MIN_TIME_TO_DOUBLE_S:.1f} s", value=f"{worst_t.t_double_s:.2f} s",
             at=f"t = {worst_t.t_s:,.0f} s", passed=worst_t.t_double_s > MIN_TIME_TO_DOUBLE_S),
        dict(rule="Steady-state gimbal deflection", source="book Sec. 12.3.6 rule 3",
             limit=f"<= {MAX_STEADY_GIMBAL_DEG:.1f} deg", value=f"{worst_d.trim_deg:.2f} deg",
             at=f"t = {worst_d.t_s:,.0f} s", passed=abs(worst_d.trim_deg) <= MAX_STEADY_GIMBAL_DEG),
        dict(rule="Total deflection budget against actuator travel", source="book Table 12.4 (RSS)",
             limit=f"<= {delta_max_deg:.1f} deg", value=f"{out.budget['rss_deg']:.2f} deg",
             at="root-sum-squared", passed=out.budget["rss_deg"] <= delta_max_deg),
    ]
    out.notes.append(
        f"Angle of attack comes from the same horizontal gust the load cases use (the book's Atlantic Missile "
        f"Range 95% envelope), so these are the moments a worst-case wind produces, not the moments of an "
        f"undisturbed ascent.")
    out.notes.append(
        f"Control authority assumes {gimballed_fraction*100:.0f}% of the thrust is steerable through "
        f"+/-{delta_max_deg:.1f} deg about a gimbal plane {z_gimbal:.2f} m above the nozzle exit. The moment "
        f"arm is the distance from there to the centre of mass, which grows as the first stage drains.")
    if all(not p.stable for p in out.points):
        out.notes.append(
            "The vehicle is statically unstable throughout, which is normal for a finless launch vehicle "
            "(book p.357) and is why these three checks exist at all: a stable vehicle would not need them.")
    bw = out.worst("bandwidth_Hz", smallest=False)
    out.notes.append(
        f"Control bandwidth peaks at {bw.bandwidth_Hz:.3f} Hz. Rule 9 asks for a factor of ten between this "
        f"and the structural frequencies; this tool computes no structural frequencies, so that separation "
        f"cannot be checked here.")
    out.notes.append(
        "Not assessed: slosh, body bending, tail-wags-dog and POGO. Chapter 12 describes all four and declines "
        "to model the first - \"analytical analysis is beyond the scope of this book\" (p.778) - and gives no "
        "equation for the others either, so there is nothing here to implement rather than invent.")
    return out
