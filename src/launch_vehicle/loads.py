"""Ground and flight loads: axial force, shear and bending moment along the vehicle (book Chapter 9).

Two design conditions are built, as the book directs (p.557): "we will consider the loads incurred during two
different vehicle conditions: on the ground, and in-flight during max-q."

  GROUND WIND    the vehicle clamped to the pad, tanks full and UNPRESSURISED, exposed to the launch site's
                 ground wind profile. Axial load is the running weight above each station at 1 g0; lateral load
                 is the wind drag on each segment's projected side area (book Sec. 9.1.5.1-9.1.5.3).

  FLIGHT         the vehicle at max-q (and, separately, at max-q alpha) flying at the angle of attack induced by
                 a horizontal gust, trimmed with engine gimbal side force, with d'Alembert inertia relief on
                 every mass (book Sec. 9.1.6, worked for the Saturn V in Sec. 9.2, recipe on pp.573-574).

Sign conventions
  z           metres UPWARD from the first-stage nozzle exit plane - the same axis as geometry.py and the mass
              ledger. "Station" is the book's coordinate: distance from the nose, = total_length - z.
  axial       positive in COMPRESSION (the running total of apparent weights above the station).
  lateral     positive in the direction the wind pushes; aerodynamic normal forces are positive, inertia relief
              forces are negative (book Fig. 9.66: right-facing aero loads, left-facing inertial loads).
  moment      positive when the lateral loads above the station bend the vehicle in the wind direction.

Marching rule. Both the shear and the moment at a station are the sums over every load applied ABOVE it
(book Eqs. 9:13-9:19 are the incremental form of exactly these sums; they are evaluated here directly, which
avoids accumulating round-off down a long vehicle and gives the same numbers). A load applied exactly at a
station is carried by the structure below it, so each station reports the value just above and just below the
cut; the peak is taken from the "below" column.

Area centroids. The book's Table 9.3 (p.555) gives the projected side areas and their centroids. Its skirt
centroid entry, h = l(d1/d3 + 2)/(3(d1/d3 + 1)) "above bottom" with d1 the forward and d3 the aft diameter, is
not the centroid of that trapezoid: it does not reduce to the book's own cone entry (h = l/3) as d1 -> 0, where
it gives 2l/3, and it places the centroid on the narrow side of mid-span instead of the wide side. The correct
result, derived in panel_centroid_above_base() below and consistent with the book's cone entry and with the
thin-frustum shell centroid already used by mass_properties._frustum_zc, is l(2 d_fwd + d_aft)/(3(d_fwd + d_aft)).
This module uses the correct expression; docs/VALIDATION_REPORT.md records the difference it makes against the
book's own Saturn V tables (about 1% on the peak ground-wind moment).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .aerodynamics import (FLIGHT_SEGMENT_CD, SLENDER_BODY_CNA_PER_RAD, Panel, cna_per_rad,
                           panel_centroid_above_base, panel_cross_area_change_m2, panel_side_area_m2,
                           panels_from_geometry)

G0 = 9.80665

# --- ground wind model (book Sec. 9.1.5.1) -----------------------------------------------------------------
GROUND_WIND_REF_MPS = 9.5          # Eq. 9:20, v_ss = (9.5 m/s) h^0.2, Eastern Test Range
GROUND_WIND_EXPONENT = 0.2
GROUND_GUST_FACTOR = 2.85          # Eq. 9:22, vortex shedding + gust combined into an effective speed
GROUND_WIND_DENSITY = 1.2807       # kg/m3, recommended with Eq. 9:23 (p.561)
GROUND_WIND_CD = 0.77              # recommended transverse drag coefficient (p.561)



# =========================================================================== wind profiles
def ground_wind_steady_mps(h_m: float) -> float:
    """Steady-state ground wind at height h above the pad surface (book Eq. 9:20, Eastern Test Range)."""
    if h_m <= 0.0:
        return 0.0
    return GROUND_WIND_REF_MPS * h_m ** GROUND_WIND_EXPONENT


def ground_wind_effective_mps(h_m: float) -> float:
    """Effective wind speed including vortex shedding and gusts (book Eq. 9:22): v_R = 2.85 v_ss."""
    return GROUND_GUST_FACTOR * ground_wind_steady_mps(h_m)


def ground_wind_q_Pa(h_m: float) -> float:
    """Ground wind dynamic pressure (book Eq. 9:23) at the recommended density of 1.2807 kg/m3."""
    v = ground_wind_effective_mps(h_m)
    return 0.5 * GROUND_WIND_DENSITY * v * v


def winds_aloft_mps(h_m: float, profile=None) -> float:
    """Horizontal gust speed vs altitude.

    With no profile this is the book's SI curve fit to the Atlantic Missile Range 95 % wind envelope of
    Fig. 9.35 (p.572) - h above ground, the fit written in km there. A profile from the site's own data
    (see wind.py) replaces it; `gust_at` is the quantity the book's step 4 asks for, which for a steady
    profile is the data plus its declared gust increment.
    """
    if profile is not None:
        return profile.gust_at(h_m)
    from .wind import book_amr_95_mps
    return book_amr_95_mps(h_m)


def gust_alpha_rad(v_mps: float, h_m: float, profile=None) -> float:
    """Instantaneous angle of attack induced by the horizontal gust (book recipe step 4, p.573):
    alpha = atan(v_wind / v)."""
    if v_mps <= 1e-6:
        return 0.0
    return math.atan(winds_aloft_mps(h_m, profile) / v_mps)


# =========================================================================== the station march
@dataclass
class PointLoad:
    z_m: float
    axial_N: float          # positive = adds compression below this point
    lateral_N: float        # positive = in the wind direction
    label: str
    source: str


@dataclass
class Station:
    z_m: float
    station_m: float        # distance from the nose
    label: str
    axial_above_N: float
    axial_below_N: float
    shear_above_N: float
    shear_below_N: float
    moment_Nm: float


def march(loads: list, stations: list, total_length: float) -> list:
    """Axial force, shear and moment at each station: the sums of every load applied above the cut.

    `stations` is a list of (z, label). The moment needs no "above/below" pair - a point force contributes
    zero moment at its own station - so one value is reported.
    """
    eps = 1e-9
    out = []
    for z, label in sorted(stations, key=lambda s: -s[0]):
        a_above = sum(l.axial_N for l in loads if l.z_m > z + eps)
        a_below = sum(l.axial_N for l in loads if l.z_m > z - eps)
        v_above = sum(l.lateral_N for l in loads if l.z_m > z + eps)
        v_below = sum(l.lateral_N for l in loads if l.z_m > z - eps)
        m = sum(l.lateral_N * (l.z_m - z) for l in loads if l.z_m > z + eps)
        out.append(Station(z, total_length - z, label, a_above, a_below, v_above, v_below, m))
    return out


@dataclass
class LoadCase:
    name: str
    condition: str                       # "ground_wind" | "flight"
    panels: list = field(default_factory=list)
    loads: list = field(default_factory=list)
    stations: list = field(default_factory=list)
    state: dict = field(default_factory=dict)       # the flight/ground condition that produced the case
    closure: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)

    def peak(self, attr: str) -> tuple:
        """(value, station) of the largest magnitude of `attr` over the stations."""
        if not self.stations:
            return 0.0, None
        s = max(self.stations, key=lambda st: abs(getattr(st, attr)))
        return getattr(s, attr), s

    @property
    def max_axial_N(self) -> float:
        return self.peak("axial_below_N")[0]

    @property
    def max_shear_N(self) -> float:
        return self.peak("shear_below_N")[0]

    @property
    def max_moment_Nm(self) -> float:
        return self.peak("moment_Nm")[0]


# =========================================================================== mass bookkeeping
def _axial_application_z(z_cm: float, panels: list) -> float:
    """Where an item's apparent weight enters the shell: "the lower junction of the weight's support structure
    (i.e., lower tank bulkhead) and the outer shell of the vehicle" (book recipe step 10, p.574). That is the
    aft end of the panel the item sits in - a tank's propellant at the tank's aft bulkhead, a stage's engines
    and thrust structure at the stage's aft ring, the payload at the bottom of the payload attach fitting."""
    inside = [p for p in panels if p.z_aft - 1e-9 <= z_cm <= p.z_fwd + 1e-9]
    if inside:
        return max(p.z_aft for p in inside)
    below = [p for p in panels if p.z_aft <= z_cm]
    if below:
        return max(p.z_aft for p in below)
    return min(p.z_aft for p in panels)


def _mass_loads(items: list, panels: list, n_x: float, n_z: float) -> list:
    """Apparent weights (axial, at the support junction) and inertia relief (lateral, at the item CM)."""
    out = []
    for it in items:
        if it.mass_kg <= 0.0:
            continue
        w = it.mass_kg * G0
        out.append(PointLoad(_axial_application_z(it.z_m, panels), n_x * w, 0.0,
                             f"{it.name} weight", f"mass {it.mass_kg:,.0f} kg at n_x = {n_x:.3f}"))
        if n_z:
            out.append(PointLoad(it.z_m, 0.0, -n_z * w, f"{it.name} inertia relief",
                                 f"mass {it.mass_kg:,.0f} kg at n_z = {n_z:.4f}"))
    return out


def _station_list(panels: list, loads: list, extra: list | None = None) -> list:
    """Every panel boundary, every load application point and the vehicle ends, de-duplicated."""
    pts = {}

    def add(z, label):
        z = round(z, 6)
        if z not in pts:
            pts[z] = label

    for p in panels:
        add(p.z_fwd, f"top of {p.name}")
        add(p.z_aft, f"bottom of {p.name}")
    for l in loads:
        add(l.z_m, l.label)
    for z, label in (extra or []):
        add(z, label)
    return [(z, pts[z]) for z in sorted(pts, reverse=True)]


# =========================================================================== case 1: ground wind
def ground_wind_case(res, pad_height_m: float = 0.0, cd: float = GROUND_WIND_CD,
                     items: list | None = None, n_x: float = 1.0, name: str | None = None) -> LoadCase:
    """Pre-launch ground wind loads: tanks full, unpressurised, clamped to the pad (book Sec. 9.1.5).

    pad_height_m raises the first-stage nozzle exit plane above the ground, because the wind profile of
    Eq. 9:20 is a function of height above the ground and a vehicle stands on a launch mount.

    n_x is 1.0 on the pad, where the only axial load is weight. Passing the lift-off thrust-to-weight ratio
    instead gives the lift-off condition: the same wind, with the vehicle accelerating (book Table 9.1 lists
    lift-off as a load case of its own, though Sec. 9.1.5 works only the clamped one).
    """
    from .mass_properties import _present

    geom = res.geometry
    panels = panels_from_geometry(geom)
    N = len(res.stages)
    J = res.spec.fairing.jettison_stage
    bstage = res.boosters.attach_stage if res.boosters else 0
    if items is None:
        items = [i for i in res.ledger if _present(i, 1, "ignition", J, N, bstage)]

    loads = []
    for p in panels:
        h = p.z_centroid + pad_height_m
        q = ground_wind_q_Pa(h)
        f = cd * q * p.side_area_m2
        if f:
            loads.append(PointLoad(p.z_centroid, 0.0, f, f"{p.name} wind drag",
                                   f"Cd {cd} x q {q:,.0f} Pa x A_side {p.side_area_m2:.2f} m2 "
                                   f"at {h:.1f} m above the pad"))
    loads += _mass_loads(items, panels, n_x=n_x, n_z=0.0)

    mass = sum(i.mass_kg for i in items)
    base_z = min(p.z_aft for p in panels)
    stations = _station_list(panels, loads, [(base_z, "hold-down plane")])
    case = LoadCase(name or "Ground wind, fully loaded and unpressurised", "ground_wind", panels, loads,
                    march(loads, stations, geom.total_length))
    top_h = geom.total_length + pad_height_m
    case.state = dict(mass_kg=mass, pad_height_m=pad_height_m, cd=cd,
                      wind_steady_at_top_mps=ground_wind_steady_mps(top_h),
                      wind_effective_at_top_mps=ground_wind_effective_mps(top_h),
                      q_at_top_Pa=ground_wind_q_Pa(top_h), n_x=n_x, n_z=0.0,
                      density_kg_m3=GROUND_WIND_DENSITY)
    total_drag = sum(l.lateral_N for l in loads)
    base = case.stations[-1]
    case.closure = dict(total_wind_force_N=total_drag, base_shear_N=base.shear_below_N,
                        base_axial_N=base.axial_below_N, weight_N=mass * G0 * n_x,
                        axial_residual_N=base.axial_below_N - mass * G0 * n_x,
                        shear_residual_N=base.shear_below_N - total_drag)
    case.notes = [
        "Tanks are full and unpressurised, which the book names as the critical ground condition (p.561): "
        "without internal pressure the allowable shell stresses are lower.",
        "Shear and moment are largest at the hold-down plane, where the vehicle is restrained (p.606).",
        f"Wind: Eq. 9:20 steady profile v = 9.5 h^0.2, Eq. 9:22 effective speed 2.85 v_ss, Eq. 9:23 dynamic "
        f"pressure at rho = {GROUND_WIND_DENSITY} kg/m3, transverse Cd = {cd} (p.561).",
    ]
    if res.boosters:
        case.notes.append("Strap-on boosters are excluded: they are separate beams with their own load paths, "
                          "which the station method of this chapter does not cover.")
    return case


# =========================================================================== case 2: flight at max-q
def axial_load_factor(traj, k: int) -> float:
    """n_x = (T - D)/(m g0) at history index k (book Sec. 9.2.2)."""
    if not traj.thrust_N or traj.m_kg[k] <= 0:
        return 0.0
    return (traj.thrust_N[k] - traj.drag_N[k]) / (traj.m_kg[k] * G0)


def _state_index(traj, criterion: str, profile=None) -> int:
    if not traj.q_Pa:
        raise ValueError("the trajectory carries no dynamic pressure history")
    if criterion == "max_q":
        return max(range(len(traj.q_Pa)), key=lambda k: traj.q_Pa[k])
    if criterion == "max_q_alpha":
        return max(range(len(traj.q_Pa)),
                   key=lambda k: traj.q_Pa[k] * gust_alpha_rad(traj.v_mps[k], traj.h_m[k], profile))
    if criterion == "max_axial":
        return max(range(len(traj.q_Pa)), key=lambda k: axial_load_factor(traj, k))
    raise ValueError(f"unknown criterion {criterion!r}: use 'max_q', 'max_q_alpha' or 'max_axial'")


def _items_at(res, traj, idx: int) -> tuple:
    """The mass ledger as flown at history index `idx`, and a note on how it was assembled."""
    from .mass_properties import _present, partial_core_prop_items

    N = len(res.stages)
    J = res.spec.fairing.jettison_stage
    bstage = res.boosters.attach_stage if res.boosters else 0
    t = traj.t_s[idx]

    # which stage is burning, and how much of its propellant has gone
    k, burned = 1, 0.0
    starts = [e for e in traj.events if e["name"].endswith(" start")]
    for e in starts:
        if e["t_s"] <= t + 1e-9 and e["name"].lower().startswith("stage "):
            try:
                k = int(e["name"].split()[1])
            except (IndexError, ValueError):
                pass
    m_now = traj.m_kg[idx]
    phase = "ignition"
    items = [i for i in res.ledger if _present(i, k, phase, J, N, bstage)
             and not (i.stage == k and i.kind == "prop_loaded")]
    loaded_k = sum(i.mass_kg for i in res.ledger if i.stage == k and i.kind == "prop_loaded")
    dry_now = sum(i.mass_kg for i in items)
    burned = max(min(loaded_k, loaded_k - (m_now - dry_now)), 0.0)
    items = items + partial_core_prop_items(res, k, burned)
    note = (f"stage {k} burning, {burned:,.0f} kg of its {loaded_k:,.0f} kg propellant load consumed by "
            f"t = {t:.0f} s; remaining propellant re-integrated in its tanks")
    return items, note, k, burned


def flight_case(res, traj, criterion: str = "max_q", cna_overrides: dict | None = None,
                alpha_deg: float | None = None, name: str | None = None, profile=None) -> LoadCase:
    """Flight loads at max-q or max-q alpha (book Sec. 9.1.6, recipe pp.573-574, Saturn V example Sec. 9.2).

    alpha_deg overrides the gust-induced angle of attack. Otherwise it comes from the wind profile at the
    altitude of the condition - the site's own profile when the design names one (wind.py), and the book's
    Atlantic Missile Range 95 % envelope (Fig. 9.35) when it does not.
    """
    geom = res.geometry
    panels = panels_from_geometry(geom)
    # The profile has to reach BOTH of these. It selects the instant - max-q alpha is ranked on
    # q * alpha, and alpha is the profile's gust over the flight speed - and then sets alpha there.
    idx = _state_index(traj, criterion, profile)
    q = traj.q_Pa[idx]
    mach, v, h, t = traj.mach[idx], traj.v_mps[idx], traj.h_m[idx], traj.t_s[idx]
    alpha = math.radians(alpha_deg) if alpha_deg is not None else gust_alpha_rad(v, h, profile)
    items, mass_note, stage_k, burned = _items_at(res, traj, idx)
    mass = sum(i.mass_kg for i in items)
    thrust = traj.thrust_N[idx] if traj.thrust_N else 0.0

    # --- step 5: aerodynamic normal and axial loads, panel by panel, rotated into body axes (Table 9.8)
    ca, sa = math.cos(alpha), math.sin(alpha)
    raw = []
    for p in panels:
        if not p.tapering:
            continue
        dA = p.cross_area_change_m2
        cna, src = cna_per_rad(p, mach, cna_overrides)
        lift = cna * alpha * q * dA                      # signed: a reverse taper pushes the other way (p.579)
        drag = FLIGHT_SEGMENT_CD * q * abs(dA)           # per-panel axial estimate, book recipe step 5
        raw.append([p, cna, src, lift, drag])

    # The vehicle's total axial force is the drag the trajectory actually flew with, from the Mach-dependent
    # drag model and the reference area - not the sum of the per-panel Cd = 0.7 estimates, which take no account
    # of pressure recovery between panels and carry no skin friction on the cylinders. The book's own Saturn V
    # example shows how far apart the two can be: Table 9.11 sums its panel axial loads to 2,843.7 kN while
    # Sec. 9.2.2 computes n_x from a measured whole-vehicle axial force of 1,134 kN, a factor of 2.5, and the
    # table's running total then fails to close on the thrust by 3.8%. The panel estimates are therefore used
    # for the SHAPE of the axial air load and scaled so that their total is the flown drag, which makes n_x
    # consistent with the trajectory and closes the axial curve exactly at the gimbal plane.
    drag_flown = traj.drag_N[idx] if traj.drag_N else 0.0
    sum_drag = sum(r[4] for r in raw)
    sum_lift = sum(r[3] for r in raw)
    scale = 1.0
    if sum_drag > 0.0 and ca > 1e-6:
        want = (drag_flown + sa * sum_lift) / (ca * sum_drag)
        if want > 0.0:
            scale = want
    aero = []
    axial_air_total = 0.0
    for p, cna, src, lift, drag in raw:
        drag *= scale
        shear = lift * ca + drag * sa                    # book Table 9.8
        axial = drag * ca - lift * sa
        axial_air_total += axial
        aero.append((p, cna, src, lift, drag, shear, axial))

    # --- axial load factor from thrust minus total axial air load (book Sec. 9.2.2)
    n_x = (thrust - axial_air_total) / (mass * G0) if mass > 0 else 0.0

    # --- step 6: gimbal side force that trims the vehicle, and the lateral load factor
    _, z_cm = _cm(items)
    z_gimbal = _gimbal_plane_z(res, geom)
    moment_aero = sum(sh * (p.z_centroid - z_cm) for (p, _, _, _, _, sh, _) in aero)
    arm = z_cm - z_gimbal
    f_gimbal = moment_aero / arm if abs(arm) > 1e-9 else 0.0
    f_lat = sum(sh for (_, _, _, _, _, sh, _) in aero) + f_gimbal
    n_z = f_lat / (mass * G0) if mass > 0 else 0.0

    # --- assemble the point loads
    loads = []
    for (p, cna, src, lift, drag, shear, axial) in aero:
        loads.append(PointLoad(p.z_centroid, axial, shear, f"{p.name} air load",
                               f"CNa {cna:.3f}/rad ({src}), dA {dA_fmt(p)}, L {lift/1e3:,.1f} kN, "
                               f"D {drag/1e3:,.1f} kN"))
    loads += _mass_loads(items, panels, n_x=n_x, n_z=n_z)
    loads.append(PointLoad(z_gimbal, -thrust, f_gimbal, "engine thrust and gimbal side force",
                           f"T {thrust/1e6:.2f} MN axial, {f_gimbal/1e3:,.0f} kN lateral to trim"))

    stations = _station_list(panels, loads, [(z_gimbal, "gimbal plane"), (z_cm, "centre of mass")])
    titles = {"max_q": "Flight at max-q", "max_q_alpha": "Flight at max-q alpha",
              "max_axial": "Flight at maximum axial acceleration"}
    case = LoadCase(name or titles.get(criterion, f"Flight at {criterion}"), "flight",
                    panels, loads, march(loads, stations, geom.total_length))
    gimbal_deg = math.degrees(math.asin(min(abs(f_gimbal) / thrust, 1.0))) if thrust > 0 else float("nan")
    case.state = dict(criterion=criterion, t_s=t, h_m=h, v_mps=v, mach=mach, q_Pa=q,
                      alpha_deg=math.degrees(alpha), wind_mps=winds_aloft_mps(h, profile),
                      wind_profile=(profile.name if profile is not None else "book_amr_95"),
                      wind_profile_kind=(profile.kind if profile is not None else "gust_envelope"),
                      q_alpha_Pa_deg=q * math.degrees(alpha), mass_kg=mass, thrust_N=thrust,
                      axial_air_load_N=axial_air_total, drag_flown_N=drag_flown,
                      panel_drag_sum_N=sum_drag, panel_drag_scale=scale, n_x=n_x, n_z=n_z, z_cm_m=z_cm,
                      z_gimbal_m=z_gimbal, gimbal_force_N=f_gimbal, gimbal_angle_deg=gimbal_deg,
                      stage_burning=stage_k, propellant_burned_kg=burned)
    base = case.stations[-1]
    tip = case.stations[0]
    case.closure = dict(axial_residual_N=base.axial_below_N, shear_residual_N=base.shear_below_N,
                        moment_at_base_Nm=base.moment_Nm, moment_at_tip_Nm=tip.moment_Nm,
                        lateral_force_N=f_lat)
    case.notes = [
        f"Angle of attack {math.degrees(alpha):.2f} deg from a {winds_aloft_mps(h):.1f} m/s horizontal gust at "
        f"{h/1000:.1f} km, taken from the book's curve fit to the Atlantic Missile Range 95% wind envelope "
        f"(Fig. 9.35, p.572), against a flight speed of {v:.0f} m/s.",
        f"Axial load factor n_x = (T - D)/(m g0) = {n_x:.3f} (book Sec. 9.2.2); lateral load factor "
        f"n_z = {n_z:.4f} from the aerodynamic side loads plus {f_gimbal/1e3:,.0f} kN of gimbal side force.",
        mass_note,
        "Inertia relief: every mass carries a lateral load of -n_z m g0 at its own CM (d'Alembert, Sec. 9.2.6), "
        "which is why the shear changes sign along the vehicle.",
        "Axial load here excludes the relief from tank pressurisation, which the book defers to Chapter 10 "
        "(p.604); it is therefore an upper bound on shell compression.",
        f"Axial air load distributed over the tapering panels in proportion to the book's Cd = "
        f"{FLIGHT_SEGMENT_CD} per-panel estimate, scaled by {scale:.3f} so the total is the "
        f"{drag_flown/1e3:,.0f} kN of drag the trajectory flew with; the axial curve therefore closes on the "
        f"thrust at the gimbal plane.",
    ]
    if res.boosters:
        case.notes.append("Strap-on boosters are excluded from the panelling and from the trim: their thrust, "
                          "air loads and attachment reactions need a multi-beam model.")
    return case


def dA_fmt(p: Panel) -> str:
    return f"{p.cross_area_change_m2:+.2f} m2"


def _cm(items) -> tuple:
    m = sum(i.mass_kg for i in items)
    return m, (sum(i.mass_kg * i.z_m for i in items) / m if m > 0 else 0.0)


def _gimbal_plane_z(res, geom) -> float:
    """Elevation of the first-stage gimbal block: the top of the engine envelope, which is where the thrust
    and the TVC side force enter the vehicle."""
    e = res.spec.stages[0].engine
    return geom.engine_exit_z.get(1, 0.0) + getattr(e, "length_m", 0.0)


# =========================================================================== both cases together
def standard_cases(res, traj=None, pad_height_m: float = 0.0, cna_overrides: dict | None = None,
                   wind_profiles=None) -> dict:
    """Every load case the vehicle can be put through with what is known about it.

    On the ground: the clamped case the book works (Sec. 9.1.5), and lift-off, which is the same wind with the
    vehicle accelerating at its lift-off thrust-to-weight ratio. In flight: max-q, max-q alpha, and the instant
    of greatest axial acceleration.

    Both of the first two flight cases are built because the book says plainly that which governs cannot be
    known in advance: "Until a trajectory analysis is done with the appropriate values inserted, it is not
    possible to say whether max-q or max-q alpha is more strenuous" (p.572). The third is added because neither
    of them is where a launch vehicle is most heavily compressed: axial acceleration peaks at the end of a burn,
    when the stage is nearly empty, and on a typical first stage that is three times the max-q value. The book
    lists it among its load cases (Sec. 9.1) but works only the two aerodynamic ones.

    `wind_profiles` is an ENSEMBLE, not a profile. Each flight case is built once per profile and the one that
    bends the vehicle hardest is kept, because the worst wind and the worst load are at different altitudes for
    different vehicles: a profile with a lower peak but its shear where the vehicle is flying fast can govern
    over a higher one. Each kept case records which profile produced it, and `wind_profiles_considered` lists
    them all so a report cannot show a governing load without showing what it was chosen from.
    """
    profiles = list(wind_profiles) if wind_profiles else [None]
    out = {"ground_wind": ground_wind_case(res, pad_height_m=pad_height_m)}
    tw = getattr(res, "liftoff_tw", 0.0) or 0.0
    if tw > 0:
        out["liftoff"] = ground_wind_case(res, pad_height_m=pad_height_m, n_x=tw,
                                          name=f"Lift-off in the same wind, n_x = {tw:.2f}")
    if traj is not None and traj.converged and traj.q_Pa:
        def worst(crit):
            """The hardest-bending version of this flight condition across the whole ensemble."""
            built = [flight_case(res, traj, crit, cna_overrides, profile=pr) for pr in profiles]
            return max(built, key=lambda c: abs(c.max_moment_Nm))

        out["max_q"] = worst("max_q")
        seen = {_state_index(traj, "max_q", pr) for pr in profiles}
        for crit in ("max_q_alpha", "max_axial"):
            idx = {_state_index(traj, crit, pr) for pr in profiles}
            if idx - seen:
                out[crit] = worst(crit)
                seen |= idx
    out["wind_profiles_considered"] = [getattr(pr, "name", "book_amr_95") for pr in profiles]
    flight = [c for k, c in out.items() if getattr(c, "condition", "") == "flight"]
    if flight:
        out["governing_flight_case"] = max(flight, key=lambda c: abs(c.max_moment_Nm)).name
    cs = [c for c in out.values() if hasattr(c, "stations")]
    out["governing_axial_case"] = max(cs, key=lambda c: abs(c.max_axial_N)).name
    out["governing_bending_case"] = max(cs, key=lambda c: abs(c.max_moment_Nm)).name
    return out
