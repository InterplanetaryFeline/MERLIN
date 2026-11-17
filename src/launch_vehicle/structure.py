"""Shell stress, buckling and required wall thickness (book Chapter 10).

Chapter 9 gave the loads; this turns them into stresses, margins and the thickness each piece of structure needs
to survive them. The vehicle is treated as the book treats it: a set of thin-walled circular shells, each carrying
the axial force, bending moment and internal pressure at its own station.

The four quantities the book asks for (Sec. 10.5.1, Eqs. 10.39-10.46)
--------------------------------------------------------------------
    axial     sigma_vert = |P|/(2 pi R t) + |M|/(pi R^2 t) - (p + p_h) R / (2 t)        Eq. 10.39
    hoop      sigma_hoop = (p + p_h) R / t                                              Eq. 10.40
    buckling  sigma_c    = [9 (t/R)^0.6 + 0.16 (R/L)^1.3 (t/R)^0.3] E t / R             Eq. 10.41, unpressurised
                           + min(0.191 (p/E)(R/t)^2, 0.229) E t / R                     Eq. 10.42, pressurised
    and their inverses, the required thicknesses, Eqs. 10.43-10.46.

Shear is computed and reported but does not size anything, which is the book's own choice: its Example 1b works
the shear thickness out at 0.024-0.056 mm and concludes "we will neglect horizontal shear stresses in the
remainder of our calculations" (p.633).

Two rules that decide most of the answers
-----------------------------------------
Ground loads carry NO tank pressure. The book is explicit (p.650): the analysis is done unpressurised "to
ensure that the structure remains stable and safe regardless of the state of pressurization of ANY of the tanks
on the launch pad... in case of an emergency requiring depressurization". So the pad case gets no pressure
relief and no pressure stabilisation, and it is usually what sizes the tanks.

Minimum gauge usually wins on upper stages. Table 10.2 gives 0.50 mm for aluminium skin, and the book warns the
equations "may produce unrealistically-low wall thicknesses that need to be replaced with a minimum gauge
value" (p.654). Where that happens this module says so rather than reporting a thickness nobody can build.

What is NOT sized here
----------------------
Only monocoque shells. Section 10.3.3 lists the ways to beat buckling - honeycomb sandwich, ring frames,
stringers, isogrid, orthogrid - but gives no allowables or mass-per-area laws for any of them; it points at
NASA CR-124075 for isogrid and stops. Sizing them would mean inventing numbers, so instead, where buckling
drives a thickness far above what strength needs, this module says that this is the regime real vehicles leave
monocoque for, and leaves the gap visible. Domes, bulkheads, joints, cut-outs, local pressure peaks, thermal
stress and fatigue are all out of scope too.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import geometry as geo
from .loads import G0

# Book Table 10.2 (p.634), suggested minimum aluminium thicknesses
MIN_GAUGE_SKIN_M = 0.0005
MIN_GAUGE_HONEYCOMB_FACE_M = 0.00025
# Book Sec. 10.3.1.1 (p.638): the Poisson ratio of a typical alloy, used by the frustum buckling criterion
DEFAULT_POISSON = 0.31
# Book Example 1b (p.633): the shear allowable is taken as half the compressive allowable
SHEAR_ALLOWABLE_FRACTION = 0.5


@dataclass
class Material:
    name: str
    E_Pa: float
    poisson: float
    rho_kg_m3: float
    sigma_allow_Pa: float
    t_min_m: float = MIN_GAUGE_SKIN_M

    @classmethod
    def from_tank_material(cls, tm) -> "Material":
        """From the TankMaterial the design already carries, so the structure is checked in the material the
        tanks are actually made of rather than one named separately."""
        return cls(name=tm.name, E_Pa=tm.E_Pa, poisson=tm.poisson, rho_kg_m3=tm.rho_kg_m3,
                   sigma_allow_Pa=tm.sigma_allow_Pa, t_min_m=tm.t_min_structural_m)


# =========================================================================== stresses, Eqs. 10.7-10.11, 10.37-10.40
def axial_stress_Pa(P_N: float, R_m: float, t_m: float) -> float:
    """Eq. 10.7: sigma_a = P / (2 pi R t). Positive here means compressive, as the book's P does."""
    return P_N / (2.0 * math.pi * R_m * t_m)


def bending_stress_Pa(M_Nm: float, R_m: float, t_m: float) -> float:
    """Eq. 10.9: sigma_b = M R / I with I = pi R^3 t (Eq. 10.8), so sigma_b = M / (pi R^2 t)."""
    return M_Nm / (math.pi * R_m * R_m * t_m)


def hoop_stress_Pa(p_Pa: float, R_m: float, t_m: float) -> float:
    """Eq. 10.40: sigma_hoop = p R / t, tensile."""
    return p_Pa * R_m / t_m


def pressure_axial_relief_Pa(p_Pa: float, R_m: float, t_m: float) -> float:
    """The tensile axial stress internal pressure puts in the wall: + p R / (2 t) (p.642)."""
    return p_Pa * R_m / (2.0 * t_m)


def shear_stress_Pa(V_N: float, R_m: float, t_m: float) -> float:
    """tau = V / (2 pi R t) (p.648)."""
    return V_N / (2.0 * math.pi * R_m * t_m)


def hydrostatic_pressure_Pa(rho_kg_m3: float, n_x: float, depth_m: float) -> float:
    """p_h = rho g0 n_x h, the head of an accelerating liquid column (p.648). Zero for solid motors."""
    return max(rho_kg_m3 * G0 * n_x * depth_m, 0.0)


def max_compressive_stress_Pa(P_N: float, M_Nm: float, p_Pa: float, R_m: float, t_m: float) -> float:
    """Eq. 10.39: the axial compression left after internal pressure has relieved what it can."""
    return (abs(axial_stress_Pa(P_N, R_m, t_m)) + abs(bending_stress_Pa(M_Nm, R_m, t_m))
            - pressure_axial_relief_Pa(p_Pa, R_m, t_m))


# =========================================================================== buckling, Eqs. 10.25, 10.31-10.33
def k0(t_m: float, R_m: float, L_m: float) -> float:
    """Eq. 10.32. Identical to the unpressurised form of Eq. 10.25 rewritten as a coefficient: the second term
    0.16 (R/L)^1.3 (t/R)^0.3 equals 0.16 (t/L)^1.3 (R/t), so the two expressions agree exactly."""
    if R_m <= 0 or L_m <= 0 or t_m <= 0:
        return 0.0
    return 9.0 * (t_m / R_m) ** 0.6 + 0.16 * (R_m / L_m) ** 1.3 * (t_m / R_m) ** 0.3


def kp(p_Pa: float, E_Pa: float, R_m: float, t_m: float) -> float:
    """Eq. 10.33: Kp = 0.191 (p/E)(R/t)^2, capped at 0.229 - "up to a maximum value of 0.229, when it stays
    constant" (p.643)."""
    if p_Pa <= 0 or t_m <= 0:
        return 0.0
    return min(0.191 * (p_Pa / E_Pa) * (R_m / t_m) ** 2, 0.229)


def critical_stress_Pa(t_m: float, R_m: float, L_m: float, E_Pa: float, p_Pa: float = 0.0) -> float:
    """Eqs. 10.31-10.33: sigma_c = (K0 + Kp) E t / R. With p = 0 this is Eq. 10.25 exactly."""
    if R_m <= 0 or t_m <= 0:
        return 0.0
    return (k0(t_m, R_m, L_m) + kp(p_Pa, E_Pa, R_m, t_m)) * E_Pa * t_m / R_m


def unpressurised_critical_stress_ratio(t_m: float, R_m: float, L_m: float) -> float:
    """Eq. 10.25 in its printed form, sigma_c/E = 9(t/R)^1.6 + 0.16(t/L)^1.3, kept separately so the identity
    with Eq. 10.32 can be tested rather than assumed."""
    if R_m <= 0 or L_m <= 0:
        return 0.0
    return 9.0 * (t_m / R_m) ** 1.6 + 0.16 * (t_m / L_m) ** 1.3


def frustum_buckling_margin(P_N: float, M_Nm: float, t_m: float, r_small_m: float, R_large_m: float,
                            h_m: float, E_Pa: float, poisson: float) -> dict:
    """NASA SP-8019 via book Sec. 10.3.1.1 (p.638): P/P_cr + M/M_cr = 1 at buckling, with

        P_cr = 0.33 * 2 pi E t^2 cos^2(alpha) / sqrt(3(1 - mu^2))
        M_cr = 0.41 * pi E t^2 r cos^2(alpha) / sqrt(3(1 - mu^2))
        alpha = atan((R - r)/h), the semivertex angle

    and r the SMALL end radius, because "buckling occurs when the max stress near the small end of the cone is
    equal to the critical compressive stress for a cylinder having the same wall thickness and local radius"."""
    alpha = math.atan2(abs(R_large_m - r_small_m), max(h_m, 1e-9))
    den = math.sqrt(3.0 * (1.0 - poisson * poisson))
    c2 = math.cos(alpha) ** 2
    p_cr = 0.33 * 2.0 * math.pi * E_Pa * t_m * t_m * c2 / den
    m_cr = 0.41 * math.pi * E_Pa * t_m * t_m * r_small_m * c2 / den
    used = (abs(P_N) / p_cr if p_cr > 0 else math.inf) + (abs(M_Nm) / m_cr if m_cr > 0 else math.inf)
    return dict(alpha_deg=math.degrees(alpha), P_cr_N=p_cr, M_cr_Nm=m_cr, interaction=used,
                margin=(1.0 / used - 1.0) if used > 0 else math.inf)


# =========================================================================== required thickness, Eqs. 10.43-10.46
def t_required_axial_m(P_N: float, M_Nm: float, p_Pa: float, R_m: float, sigma_allow_Pa: float,
                       fs: float) -> float:
    """Eq. 10.43. The bracket goes negative when internal pressure more than cancels the applied compression;
    the book's own Example 5 hits that and reads it correctly - "the negative thickness result ... indicates
    that the internal pressure alone is more than enough to sustain the applied load" (p.653) - though the
    number printed just above drops the minus sign. Taking the magnitude would make MORE pressure demand a
    THICKER wall, the opposite of the chapter's whole argument, so the result is floored at zero."""
    bracket = abs(P_N) / (2.0 * math.pi * R_m) + abs(M_Nm) / (math.pi * R_m * R_m) - 0.5 * R_m * p_Pa
    return max(fs * bracket / sigma_allow_Pa, 0.0)


def t_required_hoop_m(p_Pa: float, R_m: float, sigma_allow_Pa: float, fs: float) -> float:
    """Eq. 10.44: t = FS R (p + p_h) / sigma_allow."""
    return max(fs * R_m * p_Pa / sigma_allow_Pa, 0.0)


def t_required_shear_m(V_N: float, R_m: float, sigma_allow_Pa: float, fs: float) -> float:
    """From tau = V/(2 pi R t) with the shear allowable at half the compressive allowable (Example 1b)."""
    tau_allow = SHEAR_ALLOWABLE_FRACTION * sigma_allow_Pa
    return max(fs * abs(V_N) / (2.0 * math.pi * R_m * tau_allow), 0.0)


def t_required_buckling_m(P_N: float, M_Nm: float, R_m: float, L_m: float, E_Pa: float, p_Pa: float,
                          fs: float, t_hi_m: float = 0.25, tol: float = 1e-9) -> float:
    """Eqs. 10.45 / 10.46: the thickness at which the applied stress equals the critical stress.

    "The buckling stress equations 10.41 and 10.42 can't be solved in closed form, and must be instead solved
    numerically" (p.653) - the book suggests a spreadsheet goal-seek; this is a bisection, which cannot miss a
    root once it is bracketed. The applied stress falls like 1/t and the critical stress rises faster than t,
    so their difference changes sign exactly once and the bracket is guaranteed.
    """
    if R_m <= 0:
        return 0.0

    def excess(t):
        applied = fs * (abs(P_N) / (2.0 * math.pi * R_m * t) + abs(M_Nm) / (math.pi * R_m * R_m * t))
        return applied - critical_stress_Pa(t, R_m, L_m, E_Pa, p_Pa)

    lo, hi = 1e-7, t_hi_m
    if excess(hi) > 0:
        return hi                                            # even a very thick wall buckles: report the cap
    if excess(lo) < 0:
        return 0.0                                           # no axial load at all
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if excess(mid) > 0:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return 0.5 * (lo + hi)


# =========================================================================== per-shell analysis
@dataclass
class ShellCase:
    """One shell under one load case."""
    case: str
    P_N: float
    M_Nm: float
    V_N: float
    p_Pa: float                  # ullage pressure carried in this case (zero on the ground, by rule)
    p_hydro_Pa: float
    n_x: float
    t_axial_m: float
    t_hoop_m: float
    t_shear_m: float
    t_buckling_m: float
    sigma_vert_Pa: float         # at the installed thickness
    sigma_hoop_Pa: float
    tau_Pa: float
    margin_strength: float
    margin_buckling: float
    frustum: dict = field(default_factory=dict)

    @property
    def t_required_m(self) -> float:
        return max(self.t_axial_m, self.t_hoop_m, self.t_buckling_m)

    @property
    def driver(self) -> str:
        t = self.t_required_m
        if t <= 0:
            return "no requirement"
        for name, val in (("buckling", self.t_buckling_m), ("hoop", self.t_hoop_m), ("axial", self.t_axial_m)):
            if val >= t - 1e-12:
                return name
        return "?"


@dataclass
class Shell:
    name: str
    kind: str
    stage: int
    R_m: float
    L_m: float
    r_small_m: float
    pressurised: bool
    surface_area_m2: float
    t_installed_m: float
    material: Material
    cases: list = field(default_factory=list)
    t_required_m: float = 0.0
    min_gauge_applied: bool = False
    governing_case: str = ""
    governing_driver: str = ""
    mass_sized_kg: float = 0.0
    mass_model_kg: float = 0.0
    notes: list = field(default_factory=list)

    @property
    def margin(self) -> float:
        """Margin of safety at the installed thickness, over every case: positive means it survives."""
        if not self.cases:
            return float("nan")
        return min(min(c.margin_strength, c.margin_buckling) for c in self.cases)


def analyse_shell(name: str, kind: str, stage: int, R_m: float, L_m: float, r_small_m: float,
                  surface_area_m2: float, t_installed_m: float, material: Material, pressurised: bool,
                  case_loads: list, fs: float) -> Shell:
    """`case_loads` is a list of dicts: case, P_N, M_Nm, V_N, p_Pa, p_hydro_Pa, n_x."""
    sh = Shell(name, kind, stage, R_m, L_m, r_small_m, pressurised, surface_area_m2, t_installed_m, material)
    for cl in case_loads:
        p_tot = cl["p_Pa"] + cl["p_hydro_Pa"]
        t_ax = t_required_axial_m(cl["P_N"], cl["M_Nm"], p_tot, R_m, material.sigma_allow_Pa, fs)
        t_ho = t_required_hoop_m(p_tot, R_m, material.sigma_allow_Pa, fs)
        t_sh = t_required_shear_m(cl["V_N"], R_m, material.sigma_allow_Pa, fs)
        # buckling uses the ullage pressure only: the hydrostatic term "will vanish when the tank is empty"
        # and the book removes it from Eq. 10.42 for exactly that reason (p.651)
        t_bk = t_required_buckling_m(cl["P_N"], cl["M_Nm"], R_m, L_m, material.E_Pa, cl["p_Pa"], fs)
        t = t_installed_m
        s_vert = max_compressive_stress_Pa(cl["P_N"], cl["M_Nm"], p_tot, R_m, t)
        s_hoop = hoop_stress_Pa(p_tot, R_m, t)
        tau = shear_stress_Pa(cl["V_N"], R_m, t)
        s_crit = critical_stress_Pa(t, R_m, L_m, material.E_Pa, cl["p_Pa"])
        worst = max(abs(s_vert), abs(s_hoop))
        m_str = (material.sigma_allow_Pa / (fs * worst) - 1.0) if worst > 0 else math.inf
        m_bkl = (s_crit / (fs * s_vert) - 1.0) if s_vert > 0 else math.inf
        case = ShellCase(cl["case"], cl["P_N"], cl["M_Nm"], cl["V_N"], cl["p_Pa"], cl["p_hydro_Pa"],
                         cl["n_x"], t_ax, t_ho, t_sh, t_bk, s_vert, s_hoop, tau, m_str, m_bkl)
        if abs(R_m - r_small_m) > 1e-6:
            case.frustum = frustum_buckling_margin(cl["P_N"], cl["M_Nm"], t, r_small_m, R_m, L_m,
                                                   material.E_Pa, material.poisson)
        sh.cases.append(case)

    worst_case = max(sh.cases, key=lambda c: c.t_required_m) if sh.cases else None
    t_req = worst_case.t_required_m if worst_case else 0.0
    sh.governing_case = worst_case.case if worst_case else ""
    sh.governing_driver = worst_case.driver if worst_case else ""
    if t_req < material.t_min_m:
        sh.min_gauge_applied = True
        sh.governing_driver = "minimum gauge"
        t_req = material.t_min_m
    sh.t_required_m = t_req
    sh.mass_sized_kg = material.rho_kg_m3 * surface_area_m2 * t_req
    if worst_case and worst_case.t_buckling_m > 4.0 * max(worst_case.t_axial_m, worst_case.t_hoop_m, 1e-12):
        sh.notes.append("Buckling demands several times the thickness strength does. This is the regime real "
                        "vehicles leave monocoque for - rings, stringers or sandwich (book Sec. 10.3.2) - and "
                        "none of those is sized here, so the thickness above is the monocoque answer, not the "
                        "mass-efficient one.")
    return sh


# =========================================================================== whole vehicle
def _station_envelope(stations, z_lo: float, z_hi: float) -> tuple:
    """Largest |axial|, |shear| and |moment| anywhere inside a segment's span."""
    inside = [s for s in stations if z_lo - 1e-6 <= s.z_m <= z_hi + 1e-6]
    if not inside:
        nearest = min(stations, key=lambda s: min(abs(s.z_m - z_lo), abs(s.z_m - z_hi)))
        inside = [nearest]
    return (max(abs(s.axial_below_N) for s in inside),
            max(abs(s.shear_below_N) for s in inside),
            max(abs(s.moment_Nm) for s in inside))


# The ledger name each kind of segment's mass is reported under, so the sized mass can be put beside the
# mass-estimating relationship's answer for the same piece of hardware.
_LEDGER_NAME = {"aft_skirt": "Aft skirt", "intertank": "Intertank", "fwd_skirt": "Forward skirt",
                "interstage": "Interstage"}


def _model_mass_kg(res, seg) -> float:
    """What the mass build-up currently carries for this segment, from the ledger."""
    if seg.kind == "tank" and getattr(seg, "tank", None) is not None:
        want = f"Tank structure ({seg.tank.role})"
    elif seg.kind == "casing":
        want = "Motor casing"
    else:
        want = _LEDGER_NAME.get(seg.kind)
    if not want:
        return 0.0
    for it in res.ledger:
        if it.stage == seg.stage and it.name == want:
            return it.mass_kg
    return 0.0


def _tank_of(seg):
    return seg.tank if getattr(seg, "tank", None) is not None else None


def _liquid_depth_m(seg, z_m: float, fill_fraction: float) -> float:
    """Depth of liquid above `z_m` inside this tank segment, at the given fill fraction of its loaded volume."""
    g = _tank_of(seg)
    if g is None:
        return 0.0
    try:
        zz, _ = g.liquid_arrays(max(fill_fraction, 1e-9) * g.V_liquid)
        surface_z = seg.z0 + float(zz[-1])
    except Exception:                                        # noqa: BLE001 - a profile we cannot integrate
        surface_z = seg.z0 + fill_fraction * (g.L_int or seg.length)
    return max(surface_z - z_m, 0.0)


def _propellant_density(spec, seg) -> float:
    g = _tank_of(seg)
    if g is None or not g.propellant:
        return 0.0
    ps = spec.propellants.get(g.propellant) or spec.solid_propellants.get(g.propellant)
    return getattr(ps, "density_kg_m3", 0.0) if ps else 0.0


def analyse(res, cases: dict, material: "Material | None" = None, fs: float = 1.25,
            component_masses: dict | None = None) -> dict:
    """Stress, buckling and required thickness for every shell on the vehicle, over every load case.

    `cases` is the dict from loads.standard_cases. `fs` is the factor of safety; the book uses 1.25 throughout
    Chapter 10's examples.
    """
    spec, geom = res.spec, res.geometry
    mat = material or Material.from_tank_material(spec.stages[0].tank.material)
    shells, notes = [], []
    live = [(k, c) for k, c in cases.items() if hasattr(c, "stations")]

    skipped = []
    for seg in sorted(geom.segments, key=lambda s: -s.z0):
        R = 0.25 * (seg.d_bot + seg.d_top) if seg.d_top > 0 else 0.5 * seg.d_bot
        if R <= 0:
            continue
        if seg.stage < 1:
            skipped.append(seg.name)                          # the fairing: see the note below
            continue
        r_small = 0.5 * min(seg.d_bot, seg.d_top) if seg.d_top > 0 else 0.5 * seg.d_bot
        tank = _tank_of(seg)
        pressurised = tank is not None
        if tank is not None:
            t_installed = tank.t_wall
        elif seg.stage >= 1:
            t_installed = spec.stages[seg.stage - 1].tank.wall_t_assumed_m["fuel"]
        else:
            t_installed = mat.t_min_m
        p_op = 0.0
        if pressurised and seg.stage >= 1:
            p_op = spec.stages[seg.stage - 1].tank.pressure_Pa.get(tank.role, 0.0)
        rho_liq = _propellant_density(spec, seg)

        case_loads = []
        for key_c, c in live:
            P, V, M = _station_envelope(c.stations, seg.z0, seg.z1)
            n_x = c.state.get("n_x", 1.0)
            on_ground = c.condition == "ground_wind"
            # Book p.650: ground analysis carries NO tank pressure, by rule
            p = 0.0 if on_ground else p_op
            fill = 1.0 if on_ground else _flight_fill_fraction(res, c, seg)
            depth = _liquid_depth_m(seg, seg.z0, fill) if pressurised else 0.0
            p_h = hydrostatic_pressure_Pa(rho_liq, n_x, depth) if pressurised else 0.0
            case_loads.append(dict(case=c.name, P_N=P, M_Nm=M, V_N=V, p_Pa=p, p_hydro_Pa=p_h, n_x=n_x))

        sh = analyse_shell(seg.name, seg.kind, seg.stage, R, seg.length, r_small, geo.segment_area(seg),
                           t_installed, mat, pressurised, case_loads, fs)
        sh.mass_model_kg = ((component_masses or {}).get(seg.name)
                            if component_masses else _model_mass_kg(res, seg)) or 0.0
        shells.append(sh)

    paired = [s for s in shells if s.mass_model_kg > 0]
    sized = sum(s.mass_sized_kg for s in paired)
    modelled = sum(s.mass_model_kg for s in paired)
    if skipped:
        notes.append("The payload fairing is not analysed here: it is sized by an areal-mass relationship "
                     "(book Table 8.8) and is normally a composite sandwich, whose buckling allowables "
                     "Chapter 10 does not give. Running it through an aluminium monocoque criterion would "
                     "produce a number with nothing behind it. Skipped: " + ", ".join(skipped) + ".")
    notes.append("The installed thicknesses this is checked against are the design's own geometry assumption, "
                 "not a sized result - the tank masses in this design come from a mass-estimating relationship, "
                 "which never produces a thickness. So the margins are margins on that assumption; the "
                 "REQUIRED thicknesses are the output worth reading.")
    notes.append("Each shell is loaded with the largest axial force, shear and bending moment found anywhere "
                 "along its own length, which may be three different stations. That is conservative on purpose: "
                 "a conceptual tool should not report a margin that depends on where exactly inside a 17 m tank "
                 "the worst load happens to fall.")
    gauge = [s.name for s in shells if s.min_gauge_applied]
    if gauge:
        notes.append(f"{len(gauge)} of {len(shells)} shells come out below the {mat.t_min_m*1e3:.2f} mm minimum "
                     f"gauge of Table 10.2 and are set to it. On those pieces the loads do not size the "
                     f"structure at all - what you can buy and weld does.")
    buckling = [s for s in shells if s.governing_driver == "buckling"]
    if buckling:
        notes.append(f"Buckling sizes {len(buckling)} shell(s): " +
                     ", ".join(s.name for s in buckling[:6]) + ("..." if len(buckling) > 6 else "") +
                     ". That is the expected result for a monocoque launch vehicle - the book's own example "
                     "tanks buckle at a few hundred psi, 'hardly anything' (p.637).")
    ground_driven = [s for s in shells if "Ground" in s.governing_case or "Lift-off" in s.governing_case]
    if ground_driven:
        notes.append(f"{len(ground_driven)} shell(s) are sized by a pad case rather than by flight, which is "
                     f"the consequence of the book's rule that ground analysis carries no tank pressure "
                     f"(p.650): on the pad the tanks get neither the axial relief nor the stabilisation that "
                     f"pressure gives them in flight.")
    if modelled > 0:
        notes.append(f"Sized monocoque shells weigh {sized:,.0f} kg against the {modelled:,.0f} kg the mass "
                     f"relationships carry for the same pieces, a factor of {sized/modelled:.2f}. The MERs are "
                     f"fitted to real vehicles, and real vehicles are not monocoque: the gap is the mass that "
                     f"rings, stringers, waffle and isogrid buy back. It is NOT a correction to apply to the "
                     f"design - neither number is re-sized into the vehicle.")
    return dict(shells=shells, material=mat, factor_of_safety=fs,
                mass_sized_kg=sized, mass_model_kg=modelled,
                mass_ratio=(sized / modelled) if modelled else None,
                mass_delta_kg=(sized - modelled) if modelled else None, notes=notes,
                skipped=skipped, cases=[c.name for _k, c in live])


def _flight_fill_fraction(res, case, seg) -> float:
    """How full this tank is in a flight case: the stage burning is partly drained, everything above is full."""
    stage_burning = case.state.get("stage_burning")
    if stage_burning is None or seg.stage != stage_burning:
        return 1.0
    burned = case.state.get("propellant_burned_kg") or 0.0
    sr = res.stages[seg.stage - 1]
    loaded = sr.m_prop_loaded_kg or 1.0
    return max(1.0 - burned / loaded, 0.0)
