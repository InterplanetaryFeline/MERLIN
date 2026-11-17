"""Zero-lift drag of a launch vehicle estimated from its geometry (a component build-up). SUPPLEMENTARY.

Why this exists
---------------
The book gives no method for estimating drag from a shape. Sec. 6.4.1 (p.358) lists wind-tunnel testing, a
literature search, "or ... a drag prediction program such as Missile DATCOM", and then prints curves for four
particular vehicles (Figs. 6.9-6.13). Until this module the tool flew every vehicle on one of them, the Titan II
curve of Fig. 6.13, whatever its shape. A 1.2 m solid smallsat launcher and a hammerhead heavy-lifter with four
strap-ons do not have the same drag coefficient, and neither has Titan II's.

So nothing here is a book method. It is the standard preliminary-design build-up, with every relation taken
from a source that was read, and the result is measured against the book's own wind-tunnel figures in
`docs/DRAG.md` rather than trusted.

The build-up
------------
    Cd = Cd_friction + Cd_forebody + Cd_boattail + Cd_base            all on one reference area, Sref

per body, summed over the core and any strap-ons still attached.

Skin friction  (OpenRocket technical documentation, Sec. 3.4.2, after Barrowman 1967 and Hoerner 1965)
    turbulent           Cf = 1 / (1.50 ln Re - 5.6)^2                       for 1e4 < Re < Re_crit
    roughness-limited   Cf = 0.032 (Rs/L)^0.2                               for Re > Re_crit = 51 (Rs/L)^-1.039
    very low Re         Cf = 1.48e-2                                        for Re < 1e4
    compressibility     subsonic  Cf (1 - 0.1 M^2);  supersonic  Cf / (1 + 0.15 M^2)^0.58  (turbulent)
                        or Cf / (1 + 0.18 M^2) (roughness-limited, never below the turbulent value)
    body                Cd = Cf (1 + 1/(2 fB)) A_wet / Sref,   fB = L / d_max
  Re is built on the body's own length with US76 density and Sutherland viscosity at the flight altitude, so
  this term - alone - depends on altitude as well as Mach number.

Forebody pressure drag: nose cones and flares  (same document, Appendix B.2, conical noses; Sec. 3.4.3)
  on the frontal area the cone or flare adds, pi (d_aft^2 - d_fwd^2)/4, with half-angle eps:
    M >= 1.3            Cd = 2.1 sin^2(eps) + 0.5 sin(eps) / sqrt(M^2 - 1)
    M  = 1              Cd = sin(eps),   dCd/dM = 4/(gamma+1) (1 - 0.5 Cd)
    1 < M < 1.3         a cubic matching value and slope at both ends (the source says "a polynomial" and
                        does not give its order; a cubic is the lowest order that can meet four conditions)
    M  < 1              Cd = Cd0 + a M^b,  Cd0 = 0.8 sin^2(phi), a and b matching value and slope at M = 1;
                        phi is the joint angle: eps for a cone, 0 for a tangent ogive
  A tangent ogive takes the cone's value at and above Mach 1, which is what the source does for lack of
  Mach-dependent ogive data. A flare (a skirt or interstage widening aft) is treated as a cone frustum on its
  own annulus, as the source does for "shoulders".

Blunted nose  (Fleeman, Tactical Missile Design, AIAA 2001, p.24, Fig. 2.8)
    Cd_blunt = Cd_sharp (Sref - S_tip)/Sref + Cd_hemisphere S_tip/Sref
  with the hemispherical tip evaluated, as Fleeman does, by the same nose relation at a fineness of 0.5.

Base drag  (Fleeman p.23, Fig. 2.7; the OpenRocket document cites the same page)
    coasting            Cd = 0.12 + 0.13 M^2   (M < 1);    0.25 / M   (M > 1)       on the base area
    thrusting           the same, on the base area less the nozzle exit area: (1 - Ae/S_base)

Boattail  (OpenRocket Sec. 3.4.3)
    Cd = Cd_base x (annulus area the boattail removes) x {1 if g < 1; (3 - g)/2 if 1 < g < 3; 0 if g > 3},
    g = length / (d_fwd - d_aft)

What it leaves out, and what that costs
---------------------------------------
* Protuberances - raceways, feed lines, fairings over attach hardware, antennas - and fins.
* Interference between a core and its strap-ons. The boosters are added as isolated bodies.
* Plume effects beyond filling the nozzle exit area: jet pumping of the base at low speed and plume-induced
  separation at altitude. Fig. 6.11 shows both on the Saturn C-1, and this model has neither.
* Clustered-tank and other non-circular cross-sections; angle of attack.
* Reynolds-number effects on anything but friction, and laminar flow.
The measured consequence is in `docs/DRAG.md`: against the book's wind-tunnel curves the build-up is close on
slender single-body vehicles and low on a blunt, clustered, eight-engine one.
"""
from __future__ import annotations
import math
from bisect import bisect_right
from dataclasses import dataclass, field

from .atmosphere import us76, GAMMA_AIR

SOURCE = ("Geometry build-up (SUPPLEMENTARY): skin friction and conical forebody pressure drag after the "
          "OpenRocket technical documentation (Niskanen; Barrowman 1967; Hoerner 1965), base and blunt-nose "
          "drag after Fleeman, Tactical Missile Design (2001) pp.23-24")

#: Sutherland's law for air, the constants of the US Standard Atmosphere 1976
SUTHERLAND_BETA = 1.458e-6        # kg/(m s K^0.5)
SUTHERLAND_S_K = 110.4            # K

#: Surface roughness height. ASSUMED: a painted or bare-metal skin with rivets, weld lands and insulation is
#: far rougher than a wind-tunnel model, and the value is an input, not a measurement. 50 micrometres makes
#: every vehicle here roughness-limited at low altitude, which is the conservative side.
DEFAULT_ROUGHNESS_M = 50e-6

CONE_SUPERSONIC_FROM_MACH = 1.3   # the source's own switch-over


def viscosity_Pa_s(temperature_K: float) -> float:
    """Sutherland's law with the US76 constants."""
    return SUTHERLAND_BETA * temperature_K ** 1.5 / (temperature_K + SUTHERLAND_S_K)


def reynolds_number(mach: float, altitude_m: float, length_m: float) -> float:
    st = us76(max(altitude_m, 0.0))
    if st.density_kg_m3 <= 0.0:
        return 0.0
    return st.density_kg_m3 * mach * st.sound_speed_mps * length_m / viscosity_Pa_s(st.temperature_K)


# ------------------------------------------------------------------------------------------- skin friction
def skin_friction_coefficient(re: float, mach: float, roughness_over_length: float) -> float:
    """Compressible skin friction coefficient on wetted area."""
    if re <= 0.0:
        return 0.0
    turb = 1.48e-2 if re < 1e4 else 1.0 / (1.50 * math.log(re) - 5.6) ** 2
    rough = None
    if roughness_over_length > 0.0 and re > 51.0 * roughness_over_length ** -1.039:
        rough = 0.032 * roughness_over_length ** 0.2

    def subsonic(m):
        k = 1.0 - 0.1 * m * m
        return (rough if rough is not None else turb) * k

    def supersonic(m):
        t = turb / (1.0 + 0.15 * m * m) ** 0.58
        return t if rough is None else max(rough / (1.0 + 0.18 * m * m), t)

    # The two corrections do not meet at Mach 1 (0.900 against 0.922 of the incompressible value), so they are
    # blended linearly across 0.9-1.1. The blend is this module's, to keep Cd(M) continuous; it moves the
    # friction term by at most 2 %.
    if mach <= 0.9:
        return subsonic(mach)
    if mach >= 1.1:
        return supersonic(mach)
    f = (mach - 0.9) / 0.2
    return subsonic(0.9) * (1.0 - f) + supersonic(1.1) * f


# ------------------------------------------------------------------------------------------- forebody
def cone_pressure_cd(mach: float, sin_eps: float, sin_joint: float | None = None) -> float:
    """Pressure drag coefficient of a cone (or cone frustum) of half-angle eps, on the frontal area it adds.

    `sin_joint` is the sine of the angle at which the shape meets the body behind it: the half-angle for a
    cone (the default), zero for a tangent ogive. It only matters below Mach 1.
    """
    s = min(max(sin_eps, 0.0), 1.0)
    if s <= 0.0:
        return 0.0
    c1 = s                                                     # at Mach 1
    k1 = 4.0 / (GAMMA_AIR + 1.0) * (1.0 - 0.5 * c1)            # slope at Mach 1
    m = max(mach, 0.0)
    if m >= CONE_SUPERSONIC_FROM_MACH:
        return 2.1 * s * s + 0.5 * s / math.sqrt(m * m - 1.0)
    if m >= 1.0:
        m2 = CONE_SUPERSONIC_FROM_MACH
        b2 = math.sqrt(m2 * m2 - 1.0)
        c2 = 2.1 * s * s + 0.5 * s / b2
        k2 = -0.5 * s * m2 / b2 ** 3
        h = m2 - 1.0
        t = (m - 1.0) / h
        return ((2 * t ** 3 - 3 * t ** 2 + 1) * c1 + (t ** 3 - 2 * t ** 2 + t) * h * k1
                + (-2 * t ** 3 + 3 * t ** 2) * c2 + (t ** 3 - t ** 2) * h * k2)
    sj = s if sin_joint is None else min(max(sin_joint, 0.0), 1.0)
    c0 = 0.8 * sj * sj
    a = c1 - c0
    if a <= 0.0:
        return c1
    return c0 + a * m ** (k1 / a)


def base_cd(mach: float) -> float:
    """Base drag coefficient on the base area, power off (Fleeman p.23)."""
    m = max(mach, 0.0)
    return 0.12 + 0.13 * m * m if m < 1.0 else 0.25 / m


def boattail_factor(length_m: float, d_fwd_m: float, d_aft_m: float) -> float:
    dd = d_fwd_m - d_aft_m
    if dd <= 0.0:
        return 0.0
    g = length_m / dd
    return 1.0 if g < 1.0 else (0.0 if g > 3.0 else 0.5 * (3.0 - g))


# ------------------------------------------------------------------------------------------- geometry
@dataclass
class Section:
    """One axisymmetric piece of a body. Sections are listed from the nose aft."""
    name: str
    length_m: float
    d_fwd_m: float
    d_aft_m: float
    shape: str = "cone"            # "cone" (a frustum; a cylinder when the diameters are equal) | "ogive"

    @property
    def wetted_area_m2(self) -> float:
        r1, r2 = 0.5 * self.d_fwd_m, 0.5 * self.d_aft_m
        return math.pi * (r1 + r2) * math.hypot(r2 - r1, self.length_m)


@dataclass
class Body:
    """A body of revolution: the core vehicle, or one of `count` identical strap-ons."""
    name: str
    sections: list
    count: int = 1
    nozzle_exit_area_m2: float = 0.0       # per body; fills that much of the base while thrusting
    thrusting: bool = True                 # False for a strap-on that has not ignited or has burnt out
    tip_diameter_m: float = 0.0            # spherical blunting of the nose tip (0 = sharp)

    @property
    def length_m(self) -> float:
        return sum(s.length_m for s in self.sections)

    @property
    def max_diameter_m(self) -> float:
        return max(max(s.d_fwd_m, s.d_aft_m) for s in self.sections)

    @property
    def wetted_area_m2(self) -> float:
        return sum(s.wetted_area_m2 for s in self.sections)

    @property
    def base_area_m2(self) -> float:
        return 0.25 * math.pi * self.sections[-1].d_aft_m ** 2


def _body_pressure_terms(body: Body, mach: float, power_on: bool) -> dict:
    """Drag areas [m2] (Cd x area) of one body's pressure terms at one Mach number."""
    fore = boat = 0.0
    cb = base_cd(mach)
    for i, s in enumerate(body.sections):
        a_fwd, a_aft = 0.25 * math.pi * s.d_fwd_m ** 2, 0.25 * math.pi * s.d_aft_m ** 2
        if s.d_aft_m > s.d_fwd_m + 1e-9 and s.length_m > 0.0:
            half = 0.5 * (s.d_aft_m - s.d_fwd_m)
            sin_eps = half / math.hypot(half, s.length_m)
            joint = 0.0 if s.shape == "ogive" else None
            cd_sharp = cone_pressure_cd(mach, sin_eps, joint)
            area = a_aft - a_fwd
            if i == 0 and body.tip_diameter_m > 0.0:
                # Fleeman p.24: the sharp nose on the area outside the tip, a hemisphere (fineness 0.5) on it
                a_tip = min(0.25 * math.pi * body.tip_diameter_m ** 2, a_aft)
                sin_hemi = 1.0 / math.sqrt(2.0)               # tan(eps) = 1/(2 x 0.5)
                fore += cd_sharp * (a_aft - a_tip) + cone_pressure_cd(mach, sin_hemi) * a_tip
            else:
                fore += cd_sharp * area
        elif s.d_aft_m > s.d_fwd_m + 1e-9:                     # a forward-facing step of no length
            fore += cone_pressure_cd(mach, 1.0) * (a_aft - a_fwd)
        elif s.d_fwd_m > s.d_aft_m + 1e-9:
            boat += cb * (a_fwd - a_aft) * boattail_factor(s.length_m, s.d_fwd_m, s.d_aft_m)
    a_base = body.base_area_m2
    if power_on and body.thrusting:
        a_base = max(a_base - body.nozzle_exit_area_m2, 0.0)
    return dict(forebody=fore * body.count, boattail=boat * body.count, base=cb * a_base * body.count)


def _body_friction_area(body: Body, mach: float, altitude_m: float, roughness_m: float) -> float:
    L = body.length_m
    if L <= 0.0:
        return 0.0
    cf = skin_friction_coefficient(reynolds_number(mach, altitude_m, L), mach, roughness_m / L)
    fb = L / body.max_diameter_m
    return cf * (1.0 + 0.5 / fb) * body.wetted_area_m2 * body.count


@dataclass
class Configuration:
    """A vehicle shape as it flies: a core body and whatever strap-ons are still attached."""
    name: str
    bodies: list
    reference_area_m2: float
    roughness_m: float = DEFAULT_ROUGHNESS_M
    mach_step: float = 0.01
    mach_max: float = 12.0
    _tab: dict = field(default_factory=dict, repr=False)

    def breakdown(self, mach: float, altitude_m: float = 0.0, power_on: bool = True) -> dict:
        """Every term of the build-up as a coefficient on the reference area, plus their sum."""
        out = dict(friction=0.0, forebody=0.0, boattail=0.0, base=0.0)
        for b in self.bodies:
            for k, v in _body_pressure_terms(b, mach, power_on).items():
                out[k] += v / self.reference_area_m2
            out["friction"] += (_body_friction_area(b, mach, altitude_m, self.roughness_m)
                                / self.reference_area_m2)
        out["total"] = out["friction"] + out["forebody"] + out["boattail"] + out["base"]
        return out

    def _pressure_table(self, power_on: bool) -> list:
        key = bool(power_on)
        if key not in self._tab:
            n = int(round(self.mach_max / self.mach_step))
            tab = []
            for i in range(n + 1):
                m = i * self.mach_step
                tot = 0.0
                for b in self.bodies:
                    t = _body_pressure_terms(b, m, power_on)
                    tot += t["forebody"] + t["boattail"] + t["base"]
                tab.append(tot / self.reference_area_m2)
            self._tab[key] = tab
        return self._tab[key]

    FRICTION_MACH_STEP = 0.1
    FRICTION_ALT_STEP_M = 2000.0
    FRICTION_ALT_MAX_M = 90000.0

    def _friction_table(self) -> list:
        if "friction" not in self._tab:
            nm = int(round(self.mach_max / self.FRICTION_MACH_STEP))
            nh = int(round(self.FRICTION_ALT_MAX_M / self.FRICTION_ALT_STEP_M))
            self._tab["friction"] = [
                [sum(_body_friction_area(b, i * self.FRICTION_MACH_STEP, j * self.FRICTION_ALT_STEP_M,
                                         self.roughness_m) for b in self.bodies) / self.reference_area_m2
                 for i in range(nm + 1)] for j in range(nh + 1)]
        return self._tab["friction"]

    def cd(self, mach: float, altitude_m: float = 0.0, power_on: bool = True) -> float:
        """Cd on the reference area, for the integrator: `breakdown` is the exact evaluation, this is the same
        build-up read from tables made on first use, because a shooting run asks for it a million times.

        The pressure terms depend on Mach number only (step 0.01). Friction also depends on altitude through
        the Reynolds number and is interpolated on a Mach-altitude grid; it is a tenth of the total and
        varies slowly, and tests hold the two evaluations together.
        """
        m = min(max(mach, 0.0), self.mach_max)
        tab = self._pressure_table(power_on)
        x = m / self.mach_step
        i = min(int(x), len(tab) - 2)
        f = x - i
        p = tab[i] * (1.0 - f) + tab[i + 1] * f
        ft = self._friction_table()
        xm = m / self.FRICTION_MACH_STEP
        im = min(int(xm), len(ft[0]) - 2)
        fm = xm - im
        xh = min(max(altitude_m, 0.0), self.FRICTION_ALT_MAX_M) / self.FRICTION_ALT_STEP_M
        ih = min(int(xh), len(ft) - 2)
        fh = xh - ih
        lo = ft[ih][im] * (1.0 - fm) + ft[ih][im + 1] * fm
        hi = ft[ih + 1][im] * (1.0 - fm) + ft[ih + 1][im + 1] * fm
        return p + lo * (1.0 - fh) + hi * fh


# ------------------------------------------------------------------------------------------- from a design
@dataclass
class BuildupOptions:
    roughness_m: float = DEFAULT_ROUGHNESS_M
    nose_shape: str = "cone"               # cone | ogive
    nose_bluntness: float = 0.0            # tip diameter / fairing diameter

    @classmethod
    def from_config(cls, cfg: dict | None) -> "BuildupOptions":
        cfg = cfg or {}
        o = cls()
        if cfg.get("surface_roughness_m") is not None:
            o.roughness_m = float(cfg["surface_roughness_m"])
        if cfg.get("nose_shape"):
            o.nose_shape = str(cfg["nose_shape"]).lower()
        if cfg.get("nose_bluntness") is not None:
            o.nose_bluntness = float(cfg["nose_bluntness"])
        if o.nose_shape not in ("cone", "ogive"):
            raise ValueError(f"nose_shape must be 'cone' or 'ogive', not '{o.nose_shape}'")
        if not 0.0 <= o.nose_bluntness < 1.0:
            raise ValueError("nose_bluntness is the tip diameter over the fairing diameter: 0 to below 1")
        if o.roughness_m < 0.0:
            raise ValueError("surface_roughness_m cannot be negative")
        return o


def core_body(geom, first_stage: int = 1, options: BuildupOptions | None = None,
              nozzle_exit_area_m2: float = 0.0) -> Body:
    """The core vehicle from the sized geometry, from the fairing tip down to the base of `first_stage`.

    Stages below `first_stage` have been dropped. The fairing is kept after its jettison: by then the dynamic
    pressure is a few pascals and the shape of what is left does not move the trajectory.
    """
    o = options or BuildupOptions()
    segs = [s for s in geom.segments if s.stage == 0 or s.stage >= first_stage]
    segs = sorted(segs, key=lambda s: -s.z1)                       # nose first
    sections = []
    tip = 0.0
    for k, s in enumerate(segs):
        d_fwd, d_aft, shape = s.d_top, s.d_bot, "cone"
        if k == 0 and s.kind == "fairing_nose":
            shape = o.nose_shape
            tip = o.nose_bluntness * s.d_bot
            d_fwd = tip
        sections.append(Section(s.name, s.length, d_fwd, d_aft, shape))
    return Body("core", sections, 1, nozzle_exit_area_m2, True, tip)


def booster_body(geom, count: int, nozzle_exit_area_m2: float, thrusting: bool) -> Body | None:
    if not geom.booster_segments or count <= 0:
        return None
    segs = sorted(geom.booster_segments, key=lambda s: -s.z1)
    sections = [Section(s.name, s.length, s.d_top, s.d_bot) for s in segs]
    return Body("strap-on", sections, count, nozzle_exit_area_m2, thrusting)


def configuration_from_result(res, first_stage: int = 1, boosters_attached: int = 0,
                              boosters_thrusting: bool = True, core_exit_area_m2: float | None = None,
                              options: BuildupOptions | None = None, name: str = "") -> Configuration:
    """The flying shape of a sized design at one point in its ascent."""
    o = options or BuildupOptions()
    geom, spec = res.geometry, res.spec
    if core_exit_area_m2 is None:
        st = spec.stages[first_stage - 1]
        d = getattr(st.engine, "exit_diameter_m", None)
        if not d and getattr(res.stages[first_stage - 1], "nozzle_dims", None) is not None:
            d = getattr(res.stages[first_stage - 1].nozzle_dims, "exit_diameter_m", 0.0)
        core_exit_area_m2 = getattr(st.engine, "n_engines", 1) * 0.25 * math.pi * (d or 0.0) ** 2
    bodies = [core_body(geom, first_stage, o, core_exit_area_m2)]
    if boosters_attached and spec.boosters is not None and first_stage <= spec.boosters.attach_stage:
        ae = 0.25 * math.pi * (spec.boosters.exit_diameter_m or 0.0) ** 2
        b = booster_body(geom, boosters_attached, ae, boosters_thrusting)
        if b is not None:
            bodies.append(b)
    sref = 0.25 * math.pi * geom.max_diameter ** 2
    return Configuration(name or f"stage {first_stage} and above"
                         + (f" + {boosters_attached} strap-ons" if len(bodies) > 1 else ""),
                         bodies, sref, o.roughness_m)


def mach_sweep(config: Configuration, machs=None, altitude_m: float = 0.0, power_on: bool = True) -> list:
    """Rows of the build-up against Mach number, for a report table or a chart."""
    machs = machs or [0.0, 0.3, 0.6, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0]
    rows = []
    for m in machs:
        r = config.breakdown(m, altitude_m, power_on)
        r["mach"] = m
        rows.append(r)
    return rows


def representative_altitude_m(mach: float) -> float:
    """A typical ascent altitude for a Mach number, used only to give friction a Reynolds number when a curve
    is drawn against Mach alone. Piecewise-linear through points typical of the ascents this tool flies
    (Mach 1 near 8 km, Mach 2 near 17 km, Mach 4 near 35 km); it is a plotting convention, not a model."""
    pts_m = [0.0, 0.5, 1.0, 2.0, 3.0, 4.0, 6.0, 8.0]
    pts_h = [0.0, 2500.0, 8000.0, 17000.0, 26000.0, 35000.0, 50000.0, 62000.0]
    if mach <= pts_m[0]:
        return pts_h[0]
    if mach >= pts_m[-1]:
        return pts_h[-1]
    i = bisect_right(pts_m, mach) - 1
    f = (mach - pts_m[i]) / (pts_m[i + 1] - pts_m[i])
    return pts_h[i] * (1 - f) + pts_h[i + 1] * f
