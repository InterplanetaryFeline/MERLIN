"""Drag models for the ascent trajectory.

Where the numbers come from
---------------------------
The default drag model is a build-up from the vehicle's own geometry (`drag_buildup.py`, SUPPLEMENTARY: the
book has no such method and points to Missile DATCOM, p.358). It replaced the Titan II curve below as the
default because one vehicle's curve is wrong for every other shape; `docs/DRAG.md` measures both.

The book's own model is still here, and it is the only one that is exact rather than read off a figure.
Fig. 6.13 (p.361, after Linshue [10]) prints the Titan II drag coefficient as three analytic pieces:

    Cd = 0.29                 0   <= M <= 0.8
    Cd = M - 0.51             0.8 <= M <= 1.068
    Cd = 0.091 + 0.5/M        M   >= 1.068

They are continuous at both joins (0.29 and 0.5585), peak at M = 1.068, and decay like 1/M afterwards - the shape
every launch-vehicle drag curve in the book has. The book also gives a rule of thumb on p.359: "the minimum drag
coefficient tends to be around 0.2 for much of the flight envelope", which this curve satisfies above M ~ 4.

Other sources the book shows (and this module does NOT invent numbers from): Fig. 6.9 V-2, Fig. 6.10 Vanguard,
Fig. 6.11 Saturn C-1 power-on/power-off, Fig. 6.12 a generic curve peaking near Cd = 0.45. Those are plotted
curves, not tabulated data; reading values off them would be guesswork dressed as a reference, so instead this
module takes real data through `table`: your own Mach / Cd points.

Power on vs power off
---------------------
Fig. 6.11 shows the two differ: with the motor running the exhaust plume fills the base and base drag drops. The
book prints the Saturn C-1 relation in that figure, D_power-on = 3,260 kg/(1 + 1,000 M^4) + Cd q A, which is a
*vehicle-specific force*, not a coefficient, so it cannot be transplanted to another vehicle. What this module
offers instead is two coefficient curves, one for thrusting and one for coasting, with the thrusting one used
whenever the engines are lit. With a single curve the same Cd is used for both and the report says so.
"""
from __future__ import annotations
import math
from bisect import bisect_right
from dataclasses import dataclass, field


# --------------------------------------------------------------------------- book Fig. 6.13 (Titan II)
def cd_titan2(mach: float) -> float:
    """Book Fig. 6.13, p.361: the Titan II drag coefficient, printed as analytic equations.

    Exact, not digitised, and used exactly as printed. The first join is exactly continuous (0.29 from both
    sides). The second is continuous to the precision the book prints: the two branches actually cross at
    M = 1.06882 (the root of M^2 - 0.601 M - 0.5), so the printed breakpoint of 1.068 leaves a step of 0.0012 in
    Cd - two parts in a thousand, which is rounding in the source rather than an error, and is left alone rather
    than silently "corrected" into a curve the book does not print.
    """
    m = max(mach, 0.0)
    if m <= 0.8:
        return 0.29
    if m <= 1.068:
        return m - 0.51
    return 0.091 + 0.5 / m


CD_TITAN2_EXACT_JOIN_MACH = 1.0688177  # where the two branches really cross; the book prints 1.068
CD_TITAN2_PEAK_MACH = 1.068
CD_TITAN2_PEAK = cd_titan2(CD_TITAN2_PEAK_MACH)


# --------------------------------------------------------------------------- interpolation helper
def _interp(xs, ys, x):
    """Linear interpolation, clamped at both ends: a table is never extrapolated past its own points."""
    if not xs:
        raise ValueError("empty table")
    if len(xs) == 1 or x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = bisect_right(xs, x) - 1
    x0, x1 = xs[i], xs[i + 1]
    if x1 == x0:
        return ys[i]
    f = (x - x0) / (x1 - x0)
    return ys[i] * (1.0 - f) + ys[i + 1] * f


# --------------------------------------------------------------------------- the drag model
@dataclass
class DragModel:
    """Cd as a function of Mach number (and, for the geometry build-up, altitude).

    `kind` is one of:
      "geometry"     a component build-up from the vehicle's own shape (the default; see drag_buildup.py).
                     It has to be bound to a sized vehicle before it can be evaluated, which
                     trajectory.ascent_vehicle_from_result does.
      "book_titan2"  book Fig. 6.13 analytic form
      "constant"     a single Cd, for sensitivity work and for reproducing hand calculations
      "table"        user Mach/Cd points, linearly interpolated and clamped
    """
    kind: str = "book_titan2"
    source: str = "Book Fig. 6.13, p.361 (Titan II, after Linshue [10]): analytic Cd(M)"
    constant_cd: float = 0.29
    mach_table: list = field(default_factory=list)
    cd_table: list = field(default_factory=list)
    cd_table_off: list = field(default_factory=list)       # power-off curve, when the source has one
    reference_area_m2: float | None = None                  # None = use the vehicle's own
    notes: list = field(default_factory=list)
    buildup: object = None                                  # drag_buildup.Configuration, kind "geometry"
    buildup_options: object = None                          # drag_buildup.BuildupOptions

    @property
    def has_power_split(self) -> bool:
        return bool(self.cd_table_off or self.kind == "geometry")

    def cd(self, mach: float, altitude_m: float = 0.0, power_on: bool = True) -> float:
        if self.kind == "geometry":
            if self.buildup is None:
                raise ValueError("the geometry drag model has no vehicle yet: it is built from a sized design "
                                 "by trajectory.ascent_vehicle_from_result or aerodynamics.geometry_model")
            return self.buildup.cd(mach, altitude_m, power_on)
        if self.kind == "book_titan2":
            return cd_titan2(mach)
        if self.kind == "constant":
            return self.constant_cd
        if self.kind == "table":
            tab = self.cd_table_off if (not power_on and self.cd_table_off) else self.cd_table
            return _interp(self.mach_table, tab, mach)
        raise ValueError(f"unknown drag model '{self.kind}'")

    def describe(self) -> str:
        return self.source


def book_titan2_model() -> DragModel:
    return DragModel(kind="book_titan2")


def geometry_model(configuration=None, options=None) -> DragModel:
    """The build-up drag model. With no `configuration` it is unbound: a request for the build-up that
    trajectory.ascent_vehicle_from_result fills in from the sized design, one shape per flight phase."""
    from . import drag_buildup as db
    return DragModel(kind="geometry", source=db.SOURCE, buildup=configuration,
                     buildup_options=options or db.BuildupOptions())


def constant_model(cd: float) -> DragModel:
    return DragModel(kind="constant", constant_cd=cd,
                     source=f"Constant Cd = {cd:.3f} (user); the book's rule of thumb on p.359 is that the "
                            f"minimum drag coefficient of a missile tends to be around 0.2")


def table_model(mach, cd, cd_off=None, source="user table") -> DragModel:
    pairs = sorted(zip(mach, cd))
    ms = [p[0] for p in pairs]
    cs = [p[1] for p in pairs]
    off = None
    if cd_off is not None:
        off = [c for _, c in sorted(zip(mach, cd_off))]
    if len(mach) != len(cd) or (cd_off is not None and len(cd_off) != len(mach)):
        raise ValueError(f"a drag table needs one Cd for each Mach number: {len(mach)} Mach points, {len(cd)} Cd"
                         + (f", {len(cd_off)} power-off Cd" if cd_off is not None else ""))
    if len(ms) < 2:
        raise ValueError("a drag table needs at least two Mach points")
    return DragModel(kind="table", mach_table=ms, cd_table=cs, cd_table_off=off or [], source=source)


def model_from_config(cfg: dict | None, root: str = "") -> DragModel:
    """Build a DragModel from the `aerodynamics` block of a design file."""
    cfg = cfg or {}
    kind = (cfg.get("drag_model") or "geometry").lower()
    if kind == "geometry":
        from . import drag_buildup as db
        return geometry_model(options=db.BuildupOptions.from_config(cfg))
    if kind == "book_titan2":
        return book_titan2_model()
    if kind == "constant":
        return constant_model(float(cfg.get("constant_cd", 0.29)))
    if kind == "table":
        mach, cd = cfg.get("mach_table"), cfg.get("cd_table")
        if not mach or not cd:
            raise ValueError("drag_model 'table' needs mach_table and cd_table: the Mach numbers and the "
                             "drag coefficient at each, under mission.aerodynamics")
        return table_model(mach, cd, cfg.get("cd_table_power_off"),
                           source=cfg.get("table_source") or "user table (design file)")
    if kind in ("zoom_ld", "zoom"):
        raise ValueError("drag_model 'zoom_ld' was removed in v1.1: put the file's Mach numbers and drag "
                         "coefficients in mach_table and cd_table and use drag_model 'table'")
    raise ValueError(f"unknown drag_model '{kind}' (geometry | book_titan2 | table | constant)")


# ===========================================================================================================
# Panel decomposition and the normal-force build-up
#
# The outer mold line is cut into panels at every change of diameter. The book uses this decomposition twice:
# in Chapter 9 to put air loads on a structure, and in Chapter 12 to locate the centre of pressure. It is
# built here, in the aerodynamics module, and consumed by loads.py.
#
# A cylinder carries no normal force to first order (p.577), so only the tapering panels matter; each one's
# normal force acts at the centroid of its own area change, which for a frustum is the same point as the
# centroid of its projected side area.
# ===========================================================================================================
FLIGHT_SEGMENT_CD = 0.7            # axial force coefficient for a tapering segment (book p.577, recipe step 5)
SLENDER_BODY_CNA_PER_RAD = 2.0     # dCN/dalpha of an area change in the slender-body limit; the book's
                                   # subsonic Table 9.7 gives exactly this (2/rad = 0.0349/deg)

def panel_side_area_m2(length: float, d_aft: float, d_fwd: float) -> float:
    """Projected side (planform) area of a segment - book Table 9.3: cone d*l/2, cylinder d*l,
    skirt (d1+d3)*l/2. All three are the trapezoid, with d = 0 at the tip of a cone."""
    return 0.5 * (d_aft + d_fwd) * length


def panel_centroid_above_base(length: float, d_aft: float, d_fwd: float) -> float:
    """Height of the area centroid above the segment's aft end.

    The projected side area has width w(z) = d_aft + (d_fwd - d_aft) z / l, so
        zbar = int z w dz / int w dz = l (2 d_fwd + d_aft) / (3 (d_fwd + d_aft)).
    Checks: d_fwd = 0 (cone, apex up) -> l/3, the book's Table 9.3 cone entry; d_fwd = d_aft (cylinder) -> l/2,
    its cylinder entry. The same expression is the centroid of the normal-force distribution of a slender
    frustum, whose load per unit length also varies as the local radius, so one function serves both cases.
    """
    s = d_fwd + d_aft
    if s <= 0.0:
        return 0.5 * length
    return length * (2.0 * d_fwd + d_aft) / (3.0 * s)


def panel_cross_area_change_m2(d_aft: float, d_fwd: float) -> float:
    """Signed change in cross-sectional area from the forward to the aft end of the segment: the reference
    area of the book's normal-force charts, pi (D^2 - d^2)/4. Positive where the body widens going aft
    (nose cones, flares); negative for a reverse taper or boattail, whose normal force changes sign (p.579)."""
    return math.pi * (d_aft * d_aft - d_fwd * d_fwd) / 4.0


@dataclass
class Panel:
    """One aerodynamic panel of the outer mold line."""
    name: str
    kind: str
    stage: int
    z_aft: float
    z_fwd: float
    d_aft: float
    d_fwd: float

    @property
    def length(self) -> float:
        return self.z_fwd - self.z_aft

    @property
    def side_area_m2(self) -> float:
        return panel_side_area_m2(self.length, self.d_aft, self.d_fwd)

    @property
    def cross_area_change_m2(self) -> float:
        return panel_cross_area_change_m2(self.d_aft, self.d_fwd)

    @property
    def z_centroid(self) -> float:
        return self.z_aft + panel_centroid_above_base(self.length, self.d_aft, self.d_fwd)

    @property
    def tapering(self) -> bool:
        return abs(self.d_aft - self.d_fwd) > 1e-9


def panels_from_geometry(geom) -> list:
    """Outer-mold-line panels, aft to forward, from the sized vehicle geometry.

    Strap-on boosters are not panelled: they are separate beams with their own load paths and their own
    attachment reactions, which is past what this station method covers (see LoadCase.notes)."""
    out = []
    for s in sorted(geom.segments, key=lambda s: s.z0):
        out.append(Panel(s.name, s.kind, s.stage, s.z0, s.z1, s.d_bot, s.d_top))
    return out


# =========================================================================== normal force coefficient
def cna_per_rad(panel: Panel, mach: float, overrides: dict | None = None) -> tuple:
    """Normal force slope of one panel, per radian, on reference area |cross_area_change|.

    Returns (CNa, source). Cylindrical panels carry no normal force to first order (p.577).

    The default is the slender-body value of 2/rad, which is what the book's subsonic Table 9.7 gives for both
    a nose cone (2/rad = 0.0349/deg on pi D^2/4) and a skirt (2 (D2^2 - D1^2) / Dref^2, i.e. 2/rad on the
    annulus). The book's supersonic charts, Figs. 9.38 and 9.39, are digitised plots of unknown provenance
    ("Unfortunately, he doesn't know their origin", p.577) and are not reproduced here. On the Saturn V at
    M = 1.71 they read 0.05/deg = 2.87/rad for the capsule cone and 1.2-1.55/rad for the three skirts, so
    slender-body under-predicts a nose-cone-plus-afterbody by about 30% (the chart includes carry-over lift
    onto the cylinder behind the cone) and over-predicts a flare by 29-67%. Pass chart reads through
    `aerodynamics.cna_overrides` in the mission configuration, keyed by panel name, to use them instead.
    """
    if not panel.tapering:
        return 0.0, "cylindrical panel, CNa ~ 0 to first order (book p.577)"
    if overrides:
        for key, val in overrides.items():
            if key.lower() in panel.name.lower():
                return float(val), f"user override for '{key}' (chart read or test data)"
    return SLENDER_BODY_CNA_PER_RAD, "slender-body 2/rad; book Table 9.7 subsonic value"


@dataclass
class PanelAero:
    """One panel's contribution to the vehicle's normal force."""
    panel: Panel
    cna_per_rad: float
    source: str
    ref_area_m2: float          # the panel's own reference area, |pi (D^2 - d^2)/4|
    cna_on_sref: float          # the same slope referred to the VEHICLE reference area, signed
    z_cp_m: float               # where its normal force acts

    @property
    def stabilising(self) -> bool:
        """A panel is stabilising when its normal force acts to turn the vehicle back into the wind. That
        depends on which side of the CM it sits, so it is only decidable with a CM in hand; what the panel
        itself fixes is the SIGN of its force - negative for a reverse taper (book p.579)."""
        return self.cna_on_sref < 0.0


@dataclass
class NormalForceBuildup:
    """Vehicle normal-force slope and centre of pressure, panel by panel."""
    mach: float
    panels: list
    sref_m2: float
    length_m: float
    cna_total_per_rad: float
    z_cp_m: float               # centre of pressure, in the z axis of geometry.py (upward from the nozzles)
    station_cp_m: float         # and as a station: distance from the nose
    notes: list

    def static_margin_calibers(self, z_cm_m: float, diameter_m: float) -> float:
        """(CM - CP) in body diameters. Positive means the CP is AFT of the CM: the vehicle is statically
        stable, and a gust turns it back into the wind. Launch vehicles are usually negative (book p.357:
        "Most space launchers have no fins and are unstable, so some sort of stabilizing system is required").

        Read it together with `cma_per_rad`, and only when `cp_is_meaningful` is true. Static margin is a
        safe way to say "stable" only while the total normal-force slope is positive; if reverse tapers make
        the total negative, the sign of this number inverts without the vehicle changing at all.
        """
        if diameter_m <= 0:
            return float("nan")
        return (z_cm_m - self.z_cp_m) / diameter_m

    @property
    def cp_is_meaningful(self) -> bool:
        """A centre of pressure is a single point only while the contributions do not cancel. With a large
        enough reverse taper the total slope passes through zero and the weighted centroid runs off to
        infinity and changes sign, so the CP must not be read on its own near that point."""
        return self.cna_total_per_rad > 1e-3

    def cma_per_rad(self, z_cm_m: float) -> float:
        """Pitching-moment slope about the centre of mass, per radian, on Sref and the vehicle length.

        POSITIVE means a disturbance in angle of attack produces a moment that INCREASES it: the vehicle is
        statically unstable, which is the book's own definition (p.357, "a disturbance from zero angle of
        attack produces a moment that tends to increase the AoA"). Unlike the static margin this is defined
        whatever the contributions do, because it never divides by their sum, so it is the measure to trust.
        """
        if self.length_m <= 0:
            return float("nan")
        return sum(p.cna_on_sref * (p.z_cp_m - z_cm_m) for p in self.panels) / self.length_m

    def is_stable(self, z_cm_m: float) -> bool:
        return self.cma_per_rad(z_cm_m) < 0.0


def normal_force_buildup(geom, mach: float, sref_m2: float | None = None,
                         cna_overrides: dict | None = None) -> NormalForceBuildup:
    """Build the vehicle's normal-force slope and centre of pressure up from its panels.

    Each tapering panel contributes CNa_i on its own reference area |pi (D^2 - d^2)/4| (book Fig. 9.39's
    convention), which is referred to the vehicle reference area so the contributions can be added:

        CNa_vehicle = sum_i CNa_i * A_ref,i / Sref
        z_cp        = sum_i CNa_i * A_ref,i * z_i / sum_i CNa_i * A_ref,i

    The centre of pressure is the normal-force-weighted centroid, so it is independent of angle of attack as
    long as every CNa is (which is what the linear CN = CNa*alpha assumption means). A reverse taper carries a
    negative contribution and so pulls the CP the other way, which is exactly how a boattail stabilises a
    vehicle (p.579).
    """
    panels = panels_from_geometry(geom)
    sref = sref_m2 or (math.pi * max(p.d_aft for p in panels) ** 2 / 4.0)
    out, num, den = [], 0.0, 0.0
    for p in panels:
        if not p.tapering:
            continue
        cna, src = cna_per_rad(p, mach, cna_overrides)
        if cna == 0.0:
            continue
        a_ref = abs(p.cross_area_change_m2)
        signed = cna * p.cross_area_change_m2 / sref        # sign from the area change, not from CNa
        out.append(PanelAero(p, cna, src, a_ref, signed, p.z_centroid))
        num += signed * p.z_centroid
        den += signed
    notes = []
    z_cp = num / den if abs(den) > 1e-12 else float("nan")
    if abs(den) <= 1e-12:
        notes.append("The normal-force contributions cancel, so the vehicle has no single centre of pressure "
                     "at this Mach number; the body is as nearly neutral as this panel model can represent.")
    notes.append(f"Reference area {sref:.2f} m2 (the largest cross-section, book p.358); "
                 f"{len(out)} tapering panel(s) carry normal force, cylinders none to first order (p.577).")
    return NormalForceBuildup(mach, out, sref, geom.total_length, den, z_cp,
                              geom.total_length - z_cp, notes)


def cp_over_trajectory(res, traj, cna_overrides: dict | None = None, every: int = 1) -> dict:
    """Centre of pressure, centre of mass and static margin along the flown ascent.

    The CP comes from the panel build-up at each Mach number; the CM comes from the mass ledger drained to the
    mass the trajectory had at that instant. Only the atmospheric part of the ascent is covered - above the
    fairing jettison there is no aerodynamic normal force to speak of, and the question stops being meaningful.
    """
    from .loads import _items_at                                  # the ledger as flown, shared with Chapter 9
    from .mass_properties import cm_of

    geom = res.geometry
    sref = math.pi * geom.max_diameter ** 2 / 4.0
    rows, notes = [], []
    q_floor = 0.01 * max(traj.q_Pa) if traj.q_Pa else 0.0
    for k in range(0, len(traj.t_s), max(1, every)):
        if traj.q_Pa[k] < q_floor:
            continue
        bu = normal_force_buildup(geom, traj.mach[k], sref, cna_overrides)
        try:
            items, _note, _stage, _burned = _items_at(res, traj, k)
        except Exception:                                         # noqa: BLE001 - a point we cannot mass is skipped
            continue
        m, z_cm = cm_of(items)
        rows.append(dict(t_s=traj.t_s[k], mach=traj.mach[k], h_m=traj.h_m[k], q_Pa=traj.q_Pa[k],
                         cna_per_rad=bu.cna_total_per_rad, z_cp_m=bu.z_cp_m, z_cm_m=z_cm,
                         station_cp_m=bu.station_cp_m, station_cm_m=geom.total_length - z_cm,
                         static_margin_cal=bu.static_margin_calibers(z_cm, geom.max_diameter),
                         cma_per_rad=bu.cma_per_rad(z_cm), stable=bu.is_stable(z_cm),
                         cp_is_meaningful=bu.cp_is_meaningful, mass_kg=m))
    if rows:
        worst = min(rows, key=lambda r: r["static_margin_cal"])
        best = max(rows, key=lambda r: r["static_margin_cal"])
        notes.append(f"Static margin runs from {worst['static_margin_cal']:+.2f} calibers at t = "
                     f"{worst['t_s']:,.0f} s to {best['static_margin_cal']:+.2f} at t = {best['t_s']:,.0f} s.")
        if not all(r["cp_is_meaningful"] for r in rows):
            notes.append("At some Mach numbers the panel normal-force contributions very nearly cancel, so the "
                         "centre of pressure is not a single point there; the pitching-moment slope is the "
                         "measure to read at those times.")
        if all(not r["stable"] for r in rows):
            notes.append("The centre of pressure is ahead of the centre of mass for the whole atmospheric "
                         "ascent, so the vehicle is statically unstable throughout and depends entirely on "
                         "thrust vector control - which is the normal state for a finless launch vehicle "
                         "(book p.357).")
    return dict(rows=rows, sref_m2=sref, diameter_m=geom.max_diameter, notes=notes)
