"""Where the jettisoned hardware comes down, so the areas that need closing can be drawn.

Every item the vehicle drops - each spent stage, the fairing, any strap-on - leaves the ascent with a state the
trajectory module already computed: altitude, planet-relative speed, flight path angle and downrange distance at
the moment of separation (`trajectory.integrate` records these on its jettison events). From there the item is on
its own. This module takes that state and answers two questions in order:

  1. DOES IT COME DOWN AT ALL? An upper stage released near orbital speed does not. The test is done properly,
     in inertial terms: the planet-relative velocity is turned into an inertial one by adding the eastward speed
     of the rotating surface at the separation point, and the resulting orbit's perigee is computed. A perigee
     above `REENTRY_PERIGEE_M` means the item stays up and gets no impact point - it is an orbital-debris
     question, with a lifetime this tool does not model, not a range-safety one. Getting this wrong in the other
     direction is the obvious failure mode of a naive tool: propagate everything into the ground and you invent
     an impact point for a stage that is actually in orbit.

  2. IF IT DOES, WHERE? The item is flown down with the same equations of motion as the ascent (book Table 6.1)
     with the thrust set to zero, carrying its own mass and its own frontal area.

WHAT ACTUALLY SETS THE SIZE OF THE AREA, measured rather than assumed.

The intuition that a tumbling stage's unknown drag is the dominant uncertainty is wrong, and this module was
built on that assumption until it was checked. Sweeping the drag coefficient of the reference design's first
stage from 0.9 to 2.8 - the full range between flying nose-first and tumbling broadside - moves its impact point
by 12 km out of 1,084 km, about 1 %. The reason is geometric: nearly all of the downrange is covered on a vacuum
coast above the atmosphere, and drag only acts in the last tens of kilometres, where it is spent almost entirely
on killing vertical speed. Drag changes the impact VELOCITY enormously (3,208 m/s with no drag, 142 m/s at
Cd 1.6) and the impact POSITION very little.

What does move the impact point is the state the item separates at. For the same stage, a 5 % error in
separation speed moves the impact point about 100 km, and 2 degrees of flight path angle moves it about 26 km.
So the hazard area is set by how well the vehicle's performance is known, which puts it downstream of the mass
model: a vehicle class whose inert masses are only good to tens of percent cannot have its drop zones predicted
to better than a hundred kilometres or so. The two uncertainties are reported separately so that is visible.

Accordingly the dispersion is a `Dispersion` of three declared inputs - a fractional separation-speed
uncertainty, a flight-path-angle uncertainty, and the drag bracket - and every item is flown at all the corner
combinations. What comes out is an along-track interval, not a point.

WHAT THIS IS NOT. This is a conceptual-design estimate, not a range-safety or debris-hazard analysis. A real one
has, and this has none of:
  * a breakup model - a stage reentering at kilometres per second very likely fragments, and a fragment field is
    both wider and shorter than a single intact body;
  * wind, which moves light fragments substantially during descent;
  * a real dispersion. The separation-state uncertainties here are DECLARED ASSUMPTIONS standing in for the
    guidance and performance dispersions that a real analysis gets from Monte Carlo over the actual flight
    software. They are not derived from anything in this tool and must not be read as 3-sigma;
  * Coriolis force. The descent is integrated in the planet-relative frame with no rotation terms, so the
    cross-range it would produce is missing. Because that omission is large - of order 40 to 90 km for these
    fall times, far larger than the along-track drag spread - its magnitude is estimated separately
    (`coriolis_cross_range_m`) and used as the FLOOR on the corridor half-width, so the drawn area is at least
    as wide as the error known to be absent from it;
  * any probability of casualty, which is the quantity a range-safety decision is actually made on.

Treat the output as "roughly here, and here is how roughly", never as a cleared area.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field, replace

from . import geodesy
from .atmosphere import air, gravity_mps2
from .units import G0

OMEGA_EARTH_RAD_S = 7.2921159e-5      # sidereal rotation rate
MU_EARTH_M3_S2 = 3.986004418e14

# Above this perigee altitude an item is treated as staying in orbit rather than reentering on this flight.
# 100 km is the conventional edge-of-space line, used as a declared convention and not a physical threshold:
# an item with a perigee just above it reenters within hours to days, which is an orbital-lifetime question.
REENTRY_PERIGEE_M = 100e3

# Separation speed above which an empty stage is unlikely to reach the ground in one piece. A declared
# threshold for a warning, not a breakup criterion: nothing here models fragmentation.
BREAKUP_SPEED_MPS = 2000.0

MAX_FALL_TIME_S = 20000.0

# An along-track dispersion longer than this has stopped describing a place, so it is reported as an interval
# of downrange rather than drawn as a hazard area. A quarter of the Earth's circumference: beyond that, "the
# area to close" is not a useful idea and a polygon would wrap the planet.
MAX_LOCALISABLE_SPREAD_M = 10000e3


class DebrisError(RuntimeError):
    """The descent could not be propagated."""


@dataclass
class Dispersion:
    """The declared uncertainties the hazard area is built from. Every one of these is an assumption.

    `sep_speed_frac` and `sep_gamma_deg` stand in for guidance and performance dispersion at separation, and
    they are what the along-track interval is mostly made of. The defaults are round numbers chosen to be
    representative, NOT derived from this tool's validation and NOT a sigma of anything; a user with a real
    dispersion analysis should replace them.

    `cd` is the drag bracket: a slender body flying nose-first sits near 0.9, one tumbling through every
    attitude is far higher. It is kept because it is honest about an unknown, not because it matters much to
    the answer - see the module docstring.
    """
    sep_speed_frac: float = 0.03
    sep_gamma_deg: float = 1.0
    cd: tuple = (0.9, 1.6, 2.8)
    cross_half_width_m: float | None = None     # None = use the Coriolis estimate as the floor

    @property
    def cd_nominal(self) -> float:
        return self.cd[len(self.cd) // 2]


@dataclass
class Item:
    """One piece of hardware the vehicle drops, as the descent model sees it."""
    name: str
    mass_kg: float
    diameter_m: float
    t_jettison_s: float
    h_m: float
    v_mps: float
    gamma_deg: float
    x_m: float

    @property
    def area_m2(self) -> float:
        return 0.25 * math.pi * self.diameter_m ** 2


@dataclass
class Impact:
    """What became of one item."""
    name: str
    fate: str                     # "impact" | "marginal" | "in_orbit" | "failed"
    localisable: bool = True      # False: it comes down, but not anywhere this model can point to
    mass_kg: float = 0.0
    diameter_m: float = 0.0
    t_jettison_s: float = 0.0
    h_jettison_m: float = 0.0
    v_jettison_mps: float = 0.0
    gamma_jettison_deg: float = 0.0
    x_jettison_m: float = 0.0
    # suborbital results
    downrange_m: float = 0.0          # nominal everything
    downrange_min_m: float = 0.0      # shortest corner of the dispersion
    downrange_max_m: float = 0.0      # longest corner
    drag_spread_m: float = 0.0        # the part of the interval the drag bracket alone accounts for
    state_spread_m: float = 0.0       # the part the separation-state uncertainty alone accounts for
    km_per_percent_speed: float = 0.0  # leverage: impact-point shift per 1 % of separation speed
    fall_time_s: float = 0.0
    impact_v_mps: float = 0.0
    peak_h_m: float = 0.0
    ballistic_coefficient: float = 0.0
    coriolis_cross_range_m: float = 0.0
    # orbital results
    perigee_altitude_m: float | None = None
    apogee_altitude_m: float | None = None
    v_inertial_mps: float = 0.0
    notes: list = field(default_factory=list)


def items_from_trajectory(res, traj) -> list:
    """Read the jettisoned hardware off a sizing result and its flown trajectory.

    An event carries `dropped_kg` only when it actually dropped something, which is what distinguishes a
    jettison from a burnout or an ignition. The diameter comes from the stage the item belongs to, because
    frontal area is what drag acts on and a stage's own diameter is the best available estimate of it.
    """
    out = []
    for e in traj.events:
        dropped = e.get("dropped_kg") or 0.0
        if dropped <= 0.0:
            continue
        out.append(Item(name=e["name"], mass_kg=dropped, diameter_m=_diameter_for(res, e["name"]),
                        t_jettison_s=e["t_s"], h_m=e["h_m"], v_mps=e["v_mps"],
                        gamma_deg=e["gamma_deg"], x_m=e.get("x_m", 0.0)))
    return out


def _diameter_for(res, event_name: str) -> float:
    """The frontal diameter to charge an item, from the stage named in its event."""
    if "fairing" in event_name.lower():
        return res.spec.fairing.diameter_m
    for s in res.stages:
        if f"stage {s.index}" in event_name:
            return res.spec.stages[s.index - 1].diameter_m
    return res.geometry.max_diameter


def orbit_of(item: Item, latitude_deg: float, azimuth_deg: float,
             r_planet_m: float = geodesy.R_EARTH_M) -> dict:
    """The osculating orbit of an item at separation, in the inertial frame.

    The trajectory's speed is planet-relative. An orbit is not: the surface the vehicle launched from is itself
    moving east at omega * r * cos(latitude), and that is real velocity the item keeps when it separates. Adding
    it is the whole reason an eastward launch is cheaper, and leaving it out would make every upper stage look
    suborbital.

    Returns {perigee_altitude_m, apogee_altitude_m, v_inertial_mps, energy_J_kg}; perigee is None for a
    non-closed orbit.
    """
    r = r_planet_m + item.h_m
    g = math.radians(item.gamma_deg)
    az = math.radians(azimuth_deg)
    v = item.v_mps
    v_radial = v * math.sin(g)
    v_horiz = v * math.cos(g)
    v_north = v_horiz * math.cos(az)
    v_east = v_horiz * math.sin(az) + OMEGA_EARTH_RAD_S * r * math.cos(math.radians(latitude_deg))
    v_transverse = math.hypot(v_north, v_east)
    v_in = math.hypot(v_radial, v_transverse)
    energy = 0.5 * v_in * v_in - MU_EARTH_M3_S2 / r
    h_ang = r * v_transverse
    if energy >= 0.0:
        return {"perigee_altitude_m": None, "apogee_altitude_m": None, "v_inertial_mps": v_in,
                "energy_J_kg": energy}
    a = -MU_EARTH_M3_S2 / (2.0 * energy)
    e = math.sqrt(max(0.0, 1.0 + 2.0 * energy * h_ang * h_ang / (MU_EARTH_M3_S2 ** 2)))
    return {"perigee_altitude_m": a * (1.0 - e) - r_planet_m,
            "apogee_altitude_m": a * (1.0 + e) - r_planet_m,
            "v_inertial_mps": v_in, "energy_J_kg": energy}


def fall(item: Item, cd: float, dt: float = 0.5, atmosphere: str = "book_exponential",
         r_planet_m: float = geodesy.R_EARTH_M) -> dict:
    """Fly one item from separation to the surface with thrust zero. RK4 on (v, gamma, h, x).

    Same equations of motion as the ascent (book Table 6.1), same atmosphere, so the descent is consistent with
    the trajectory that produced the separation state rather than being a separate model with its own biases.

    The Coriolis cross-range is accumulated alongside as a double integral of 2*omega*v, the magnitude of the
    acceleration the planet-relative frame leaves out. It is an order-of-magnitude indicator used to size the
    corridor width; it is NOT a predicted cross-range and carries no sign.
    """
    v, gamma = float(item.v_mps), math.radians(item.gamma_deg)
    h, x, m = float(item.h_m), float(item.x_m), float(item.mass_kg)
    area = item.area_m2
    if m <= 0.0 or area <= 0.0:
        raise DebrisError(f"{item.name}: mass {m} kg and area {area} m2 must both be positive")
    t, peak, cross_v, cross = 0.0, h, 0.0, 0.0

    def rates(vv, gg, hh):
        st = air(max(hh, 0.0), atmosphere)
        dN = cd * area * 0.5 * st.density_kg_m3 * vv * vv
        g = gravity_mps2(max(hh, 0.0), G0, r_planet_m)
        dv = -dN / m - g * math.sin(gg)
        dgamma = 0.0 if abs(vv) < 1e-6 else -(g / vv - vv / (r_planet_m + hh)) * math.cos(gg)
        return dv, dgamma, vv * math.sin(gg), vv * math.cos(gg) / (1.0 + hh / r_planet_m)

    while h > 0.0 and t < MAX_FALL_TIME_S:
        k1 = rates(v, gamma, h)
        k2 = rates(v + k1[0] * dt / 2, gamma + k1[1] * dt / 2, h + k1[2] * dt / 2)
        k3 = rates(v + k2[0] * dt / 2, gamma + k2[1] * dt / 2, h + k2[2] * dt / 2)
        k4 = rates(v + k3[0] * dt, gamma + k3[1] * dt, h + k3[2] * dt)
        dv = (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0]) / 6.0
        dg = (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1]) / 6.0
        dh = (k1[2] + 2 * k2[2] + 2 * k3[2] + k4[2]) / 6.0
        dx = (k1[3] + 2 * k2[3] + 2 * k3[3] + k4[3]) / 6.0
        h_next = h + dh * dt
        if h_next <= 0.0 and dh < 0.0:
            # land exactly on the surface: take the fraction of the step that reaches h = 0
            frac = max(0.0, min(1.0, h / (-dh * dt)))
            v += dv * dt * frac
            x += dx * dt * frac
            gamma += dg * dt * frac
            t += dt * frac
            h = 0.0
            break
        v += dv * dt
        gamma += dg * dt
        h = h_next
        x += dx * dt
        cross_v += 2.0 * OMEGA_EARTH_RAD_S * abs(v) * dt
        cross += cross_v * dt
        t += dt
        peak = max(peak, h)
        if v < 0.0:
            raise DebrisError(f"{item.name}: descent speed went negative - step {dt} s is too coarse")
    if h > 0.0:
        raise DebrisError(f"{item.name}: still at {h/1e3:.0f} km after {MAX_FALL_TIME_S:.0f} s of descent")
    return {"downrange_m": x, "fall_time_s": t, "impact_v_mps": v, "peak_h_m": peak,
            "gamma_impact_deg": math.degrees(gamma), "coriolis_cross_range_m": cross,
            "ballistic_coefficient": m / (cd * area)}


def _sweep(item: Item, disp: Dispersion, dt: float, atmosphere: str,
           latitude_deg: float, azimuth_deg: float) -> dict:
    """Fly every corner of the dispersion box, and separate what each uncertainty contributes.

    Returns the nominal run plus the along-track interval, with the drag-only and separation-state-only spreads
    kept apart so a reader can see which one is setting the size of the area.

    A corner is checked for orbital energy BEFORE it is flown. An upper stage separating near orbital speed can
    have a nominal case that comes down and a +3 % case that does not, and a descent integrator handed that
    case will happily accumulate downrange for most of a revolution and report a "hazard area" tens of
    thousands of kilometres long. That is not an area, and drawing it as one would be worse than saying
    nothing. Such an item is reported as NOT LOCALISABLE instead, which is the true statement: a small
    performance error puts it anywhere from the nominal point to a full orbit away.
    """
    v_set = (item.v_mps * (1.0 - disp.sep_speed_frac), item.v_mps, item.v_mps * (1.0 + disp.sep_speed_frac))
    g_set = (item.gamma_deg - disp.sep_gamma_deg, item.gamma_deg, item.gamma_deg + disp.sep_gamma_deg)
    cd_nom = disp.cd_nominal

    def corner_is_orbital(v, g):
        orb = orbit_of(replace(item, v_mps=v, gamma_deg=g), latitude_deg, azimuth_deg)
        per = orb["perigee_altitude_m"]
        return per is None or per > REENTRY_PERIGEE_M

    def run(v, g, cd):
        return fall(replace(item, v_mps=v, gamma_deg=g), cd, dt=dt, atmosphere=atmosphere)

    orbital_corners = sum(1 for v in v_set for g in g_set if corner_is_orbital(v, g))
    nominal = run(item.v_mps, item.gamma_deg, cd_nom)
    if orbital_corners:
        return {"nominal": nominal, "min": nominal["downrange_m"], "max": nominal["downrange_m"],
                "drag_spread": 0.0, "state_spread": 0.0, "km_per_percent_speed": 0.0,
                "orbital_corners": orbital_corners, "localisable": False}

    all_ranges, drag_only, state_only = [], [], []
    for v in v_set:
        for g in g_set:
            for cd in disp.cd:
                r = run(v, g, cd)["downrange_m"]
                all_ranges.append(r)
                if v == item.v_mps and g == item.gamma_deg:
                    drag_only.append(r)
                if cd == cd_nom:
                    state_only.append(r)
    # leverage, from the two nominal-attitude speed corners: km of impact point per 1 % of separation speed
    lo = run(v_set[0], item.gamma_deg, cd_nom)["downrange_m"]
    hi = run(v_set[2], item.gamma_deg, cd_nom)["downrange_m"]
    per_pct = ((hi - lo) / 2.0) / (100.0 * disp.sep_speed_frac) if disp.sep_speed_frac else 0.0
    spread = max(all_ranges) - min(all_ranges)
    return {"nominal": nominal, "min": min(all_ranges), "max": max(all_ranges),
            "drag_spread": max(drag_only) - min(drag_only) if drag_only else 0.0,
            "state_spread": max(state_only) - min(state_only) if state_only else 0.0,
            "km_per_percent_speed": per_pct, "orbital_corners": 0,
            # even with every corner suborbital, a dispersion this long has stopped describing a place
            "localisable": spread < MAX_LOCALISABLE_SPREAD_M}


def resolve(res, traj, latitude_deg: float, azimuth_deg: float, dispersion: Dispersion | None = None,
            dt: float = 0.5, atmosphere: str = "book_exponential") -> list:
    """Every jettisoned item: does it come down, and if so over what interval of downrange.

    One `Impact` per item, in jettison order.
    """
    disp = dispersion or Dispersion()
    out = []
    for item in items_from_trajectory(res, traj):
        orb = orbit_of(item, latitude_deg, azimuth_deg)
        per = orb["perigee_altitude_m"]
        imp = Impact(name=item.name, fate="impact", mass_kg=item.mass_kg, diameter_m=item.diameter_m,
                     t_jettison_s=item.t_jettison_s, h_jettison_m=item.h_m, v_jettison_mps=item.v_mps,
                     gamma_jettison_deg=item.gamma_deg, x_jettison_m=item.x_m,
                     perigee_altitude_m=per, apogee_altitude_m=orb["apogee_altitude_m"],
                     v_inertial_mps=orb["v_inertial_mps"])
        if per is None or per > REENTRY_PERIGEE_M:
            imp.fate = "in_orbit"
            if per is None:
                imp.notes.append("separation state is not a closed orbit (escape energy), so it has no perigee: "
                                 "that is a design or trajectory problem rather than a real case")
            else:
                imp.notes.append(
                    f"separates at {orb['v_inertial_mps']:.0f} m/s inertial with a perigee of {per/1e3:.0f} km, "
                    f"so it stays up and has no impact point on this flight. When it comes down is an "
                    f"orbital-lifetime question this tool does not model.")
            out.append(imp)
            continue

        try:
            sw = _sweep(item, disp, dt, atmosphere, latitude_deg, azimuth_deg)
        except DebrisError as ex:
            imp.fate = "failed"
            imp.notes.append(str(ex))
            out.append(imp)
            continue
        nom = sw["nominal"]
        imp.downrange_m = nom["downrange_m"]
        imp.downrange_min_m, imp.downrange_max_m = sw["min"], sw["max"]
        imp.drag_spread_m, imp.state_spread_m = sw["drag_spread"], sw["state_spread"]
        imp.km_per_percent_speed = sw["km_per_percent_speed"]
        imp.fall_time_s = nom["fall_time_s"]
        imp.impact_v_mps = nom["impact_v_mps"]
        imp.peak_h_m = nom["peak_h_m"]
        imp.ballistic_coefficient = nom["ballistic_coefficient"]
        imp.coriolis_cross_range_m = nom["coriolis_cross_range_m"]
        imp.localisable = sw["localisable"]
        if not imp.localisable:
            imp.fate = "marginal"
            if sw["orbital_corners"]:
                imp.notes.append(
                    f"NOT LOCALISABLE: {sw['orbital_corners']} of 9 separation-state corners are orbital. This "
                    f"item separates close enough to orbital speed that a {100*disp.sep_speed_frac:.0f} % "
                    f"performance error decides whether it comes down at all. Its nominal impact is "
                    f"{imp.downrange_m/1e3:.0f} km downrange, but no hazard area is drawn, because the honest "
                    f"answer spans everything from there to a full revolution.")
            else:
                imp.notes.append(
                    f"NOT LOCALISABLE: the dispersion spans "
                    f"{(imp.downrange_max_m - imp.downrange_min_m)/1e3:.0f} km, which has stopped describing a "
                    f"place. The nominal impact is {imp.downrange_m/1e3:.0f} km downrange; no area is drawn.")
            out.append(imp)
            continue
        imp.notes.append(
            f"nominal impact {imp.downrange_m/1e3:.0f} km downrange; the dispersion box spans "
            f"{imp.downrange_min_m/1e3:.0f} to {imp.downrange_max_m/1e3:.0f} km. Of that interval the "
            f"separation-state assumption accounts for {imp.state_spread_m/1e3:.0f} km and the drag bracket "
            f"for {imp.drag_spread_m/1e3:.0f} km, so the area is set by how well the vehicle's performance is "
            f"known, not by the tumbling drag.")
        imp.notes.append(
            f"leverage: every 1 % of error in separation speed moves this impact point "
            f"{imp.km_per_percent_speed/1e3:.0f} km.")
        if item.v_mps > BREAKUP_SPEED_MPS:
            imp.notes.append(
                f"separates at {item.v_mps:.0f} m/s, above the {BREAKUP_SPEED_MPS:.0f} m/s at which an empty "
                f"stage is unlikely to survive reentry intact. No breakup is modelled, so this is reported as "
                f"one body; a real fragment field would land shorter and spread wider than this interval.")
        out.append(imp)
    return out


def half_width_m(impacts, dispersion: Dispersion | None = None) -> float:
    """The corridor half-width to draw: the stated width, or the Coriolis estimate when that is larger.

    Neither number is a predicted cross-range. The first is an assumption and the second is the size of a term
    the model omits; the corridor is drawn at the larger of the two so that it is never narrower than an error
    known to be missing from it.
    """
    disp = dispersion or Dispersion()
    cor = max([i.coriolis_cross_range_m for i in impacts if i.fate == "impact"], default=0.0)
    if disp.cross_half_width_m is None:
        return cor
    return max(float(disp.cross_half_width_m), cor)
