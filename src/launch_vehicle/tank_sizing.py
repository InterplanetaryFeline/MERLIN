"""Propellant volumes, tank geometry and tank mass models.

Verified book equations
-----------------------
Eq. 8:5a/b  fuel/oxidizer split with the book's f = m_fuel/m_ox         (p. 470)   [this tool uses OF = m_ox/m_fuel = 1/f]
Eq. 8:6     Vol = m/rho                                                  (p. 471)
Eq. 8:8-8:10 ullage fraction and cryogenic shrinkage: Vol_all = Vol (1 + ullage + 3 alpha dT)  (pp. 471-472)
Table 8.2   dome volume/area (AR = R/h_dome; hemisphere AR = 1)         (p. 477)
Eq. 8:16    h_cyl = 4 Vol/(pi D^2) - 2 D/(3 AR)  (derived here for general AR; the book prints AR = sqrt2)  (p. 484)
Table 8.6   tank MERs by propellant mass (LOX 0.0107, RP-1 0.0148, LH2 0.128)                (p. 494)
Table 8.7   tank MERs by volume (12.16 kg/m^3; LH2 9.09 kg/m^3)                              (p. 495)
Pressure-vessel thin-wall sizing is SUPPLEMENTARY (standard theory, not a book equation).

Dimensions: 'internal' = inside the pressure shell; 'external' = internal + wall thickness.
"""
from __future__ import annotations
import contextlib
import math
import threading
from dataclasses import dataclass, field
import numpy as np

#: R34. The geometry checks below answer "is this tank buildable?", which is a question about a DESIGN, not
#: about an intermediate guess. The sizing loop is a fixed-point iteration whose early iterates are crude:
#: the seed under-fills a hydrolox core whose boosters carry most of the lift-off impulse, so iteration 1 can
#: ask a 5.4 m tank to hold 35 m^3 when the converged stage holds 384 m^3 and fits comfortably. Raising there
#: refused Ariane 62 - a real, flying vehicle with published masses - for a property its converged design does
#: not have. Inside this context a tank whose contents fit entirely within its end caps is reported with a
#: zero-length barrel (an oversized tank, which is what it physically is) instead of raising, and the loop is
#: allowed to converge. `size_vehicle` then re-checks the CONVERGED design outside the context, so a design
#: that is genuinely infeasible still fails, with the same message and the same one-click fixes as before.
#: Thread-local rather than a module global because the GUI serves on a threading HTTP server.
_tolerance = threading.local()


def oversized_tanks_tolerated() -> bool:
    return getattr(_tolerance, "allow", False)


@contextlib.contextmanager
def tolerate_oversized_tanks():
    """Within this block, a tank too wide for its contents yields a zero barrel instead of raising."""
    prev = getattr(_tolerance, "allow", False)
    _tolerance.allow = True
    try:
        yield
    finally:
        _tolerance.allow = prev


#: The largest dome aspect ratio (R/h) worth proposing as a fix. Beyond this the "dome" is a flat
#: plate: real tank domes are hemispherical (1.0) to about sqrt(2), and anything past a few is a
#: mathematical solution rather than a tank.
MAX_SENSIBLE_DOME_AR = 3.0


class InfeasibleGeometry(ValueError):
    """Required volume cannot be realised with the specified geometry.

    `options` carries the ways out, when they can be computed. Each is a dict with a `label` a person can
    read, and, where the remedy is a single input, the `path` of that input and the `value` that would make
    the design feasible. A user interface can then offer the fix instead of leaving someone to work out from
    prose which number to change and what to change it to.
    """

    def __init__(self, message, field: str | None = None, options=None):
        super().__init__(message)
        self.field = field
        self.options = list(options or ())


# ---------- propellant split / volumes --------------------------------------------------------
def split_propellant(m_total: float, of_ratio: float) -> tuple:
    """Return (m_ox, m_fuel) for OF = m_ox/m_fuel.  Equivalent to Eq. 8:5 with f = 1/OF."""
    if of_ratio <= 0:
        raise ValueError("mixture ratio O/F must be positive")
    m_fuel = m_total / (1.0 + of_ratio)
    return m_total - m_fuel, m_fuel


def shrink_fraction(alpha_per_K: float, t_load_K: float, t_boil_K: float) -> float:
    """Eq. 8:9 magnitude: 3 alpha |T_load - T_boil| (volumetric contraction of a tank filled with cryogen)."""
    return 3.0 * alpha_per_K * abs(t_load_K - t_boil_K)


def required_volume(m_kg: float, rho: float, ullage: float, shrink: float) -> tuple:
    """Return (liquid volume, ullage volume, shrink volume, required internal volume). Eq. 8:6, 8:7, 8:10."""
    if rho <= 0:
        raise ValueError("density must be positive")
    v = m_kg / rho
    return v, v * ullage, v * shrink, v * (1.0 + ullage + shrink)


# ---------- domes -----------------------------------------------------------------------------
def dome_height(R: float, AR: float) -> float:
    return R / AR


def dome_volume(R: float, AR: float) -> float:
    """Table 8.2: 2 pi R^3 / (3 AR) (hemisphere for AR = 1)."""
    return 2.0 * math.pi * R ** 3 / (3.0 * AR)


def dome_area(R: float, AR: float) -> float:
    """Table 8.2 surface area of a semi-oblate-spheroid dome. AR=1: 2 pi R^2; AR=sqrt2: 1.6234 pi R^2."""
    if AR < 1.0:
        raise ValueError("dome aspect ratio R/h must be >= 1 (oblate or hemispherical)")
    if abs(AR - 1.0) < 1e-12:
        return 2.0 * math.pi * R ** 2
    e = math.sqrt(1.0 - 1.0 / AR ** 2)
    return math.pi * R ** 2 * (1.0 + (1.0 - e * e) / e * math.atanh(e))


def max_feasible_radius(V_int: float, AR: float, n_domes_volume: float = 2.0) -> float:
    """Largest internal radius at which V_int still leaves a non-negative barrel.

    Dome volume goes as R^3 while the propellant does not, so past a certain radius the two end caps alone
    hold more than the tank needs and there is no cylinder left. Solving
    n_dome * (2 pi / 3) R^3 / AR = V_int for R gives the limit. Quoting it turns "this is infeasible" into
    "use at most this diameter", which is the question the user actually has.
    """
    if V_int <= 0 or AR < 1.0 or n_domes_volume <= 0:
        return 0.0
    # dome_volume(R, AR) = (2 pi / 3) R^3 / AR, so scale the unit-radius value rather than re-deriving it
    unit = dome_volume(1.0, AR) * n_domes_volume
    return (V_int / unit) ** (1.0 / 3.0) if unit > 0 else 0.0


def barrel_length(V_int: float, R: float, AR: float, n_domes_volume: float = 2.0) -> float:
    """Cylinder length for given internal volume: V = pi R^2 h + n_dome * V_dome.  Raises if negative."""
    h = (V_int - n_domes_volume * dome_volume(R, AR)) / (math.pi * R ** 2)
    if h < 0 and oversized_tanks_tolerated():
        # An intermediate iterate, not a design. Report the tank as dome-to-dome with no barrel: it holds
        # more than its contents, which is an oversized tank rather than an impossible one. The converged
        # design is re-checked outside this tolerance by size_vehicle.
        return 0.0
    if h < 0:
        r_max = max_feasible_radius(V_int, AR, n_domes_volume)
        # Both settable remedies are exact, so solve for them and hand them over as values a user interface
        # can apply, rather than leaving the reader to work out which number to change and to what.
        #   diameter: R <= r_max, already solved above
        #   dome AR:  V_int >= n * (2 pi / 3) R^3 / AR  ->  AR >= n * (2 pi / 3) R^3 / V_int
        ar_min = n_domes_volume * dome_volume(R, 1.0) / V_int if V_int > 0 else 0.0
        raise InfeasibleGeometry(
            f"required internal volume {V_int:.3f} m^3 is smaller than the volume of the end caps "
            f"({n_domes_volume*dome_volume(R, AR):.3f} m^3) at internal radius {R:.3f} m. "
            f"THE TANK IS TOO WIDE FOR WHAT IT HOLDS: at this dome aspect ratio the internal radius must be "
            f"at most {r_max:.3f} m (about {2*r_max:.2f} m across) for any barrel to remain. Either set this "
            f"stage's tank.diameter_m below that - a stage whose tanks do not fill its envelope is normal, "
            f"and several real upper stages are built that way - or flatten the domes by raising "
            f"tank.dome_aspect_ratio, or give the stage more propellant",
            options=[
                {"label": f"Narrow this stage's tanks to {2*r_max:.2f} m",
                 "path": "tank.diameter_m", "value": round(2 * r_max - 5e-3, 3),
                 "note": "the widest tank whose end caps still leave a barrel. A stage whose tanks are "
                         "narrower than its envelope is normal; several real upper stages are built that way"},
                # Only offer the dome remedy when the required aspect ratio is still a tank. The algebra
                # always yields a number, but a dome at R/h = 27 is a flat plate, not an end cap: offering
                # it as a one-click fix would be the tool giving advice no designer should take.
                ({"label": f"Flatten the domes to an aspect ratio of {max(ar_min, AR):.2f}",
                  "path": "tank.dome_aspect_ratio", "value": round(max(ar_min, AR) + 0.02, 2),
                  "note": "a higher R/h makes each dome shallower, so the two caps hold less and a barrel "
                          "remains. Shallow domes are heavier for the same pressure"}
                 if ar_min <= MAX_SENSIBLE_DOME_AR else
                 {"label": "Flattening the domes cannot fix this one",
                  "note": f"it would take an aspect ratio of {ar_min:.1f}, and a dome that shallow is a "
                          f"flat plate rather than an end cap. Narrow the tank instead"}),
                {"label": "Give the stage more propellant",
                 "note": "propellant mass follows from the delta-v split, so raise this stage's share of "
                         "the delta-v, or the payload, rather than typing a propellant mass"},
            ])
    return h


# ---------- tank geometry objects -------------------------------------------------------------
@dataclass
class TankGeometry:
    role: str                    # 'fuel' | 'oxidizer'
    propellant: str
    R_int: float
    AR: float
    h_cyl: float
    h_dome: float
    t_wall: float                # thickness used for external dimension
    V_int: float
    V_liquid: float
    m_liquid_loaded: float
    bulkhead: str = "none"       # 'none' | 'lower_owner' | 'upper_user'
    # axial extent measured from the tank's own bottom (internal, local coordinates)
    L_int: float = 0.0
    L_prof: float = 0.0          # extent of the volume profile (lower tank of a common bulkhead includes the bulge)
    L_ext: float = 0.0
    area_ext: float = 0.0        # outer wetted surface (for insulation)
    mass_tank_kg: float = 0.0
    mass_insulation_kg: float = 0.0
    mass_method: str = ""
    t_dome: float = 0.0
    z_bottom: float = 0.0        # filled by geometry assembly (vehicle coordinates)
    z_top: float = 0.0
    notes: list = field(default_factory=list)

    @property
    def D_ext(self) -> float:
        return 2.0 * (self.R_int + self.t_wall)

    def volume_check(self) -> float:
        """Independent recomputation of internal volume from the dimensions, minus the required V_int (should be ~0).

        separate / lower tank : pi R^2 h_cyl + 2 V_dome  (bottom dome + barrel + top dome / shared bulkhead bulge)
        upper tank of a common bulkhead: barrel + top dome - bulkhead bulge = pi R^2 h_cyl (bulge cancels the top dome)
        """
        vd = dome_volume(self.R_int, self.AR)
        v = math.pi * self.R_int ** 2 * self.h_cyl + (0.0 if self.bulkhead == "upper_user" else 2 * vd)
        return v - self.V_int

    def volume_numeric(self, n: int = 20001) -> float:
        """Volume by numerical integration of the area profile (independent check of the closed-form dome volumes)."""
        z = np.linspace(0.0, self.L_prof or self.L_int, n)
        return float(np.trapezoid(self.area_profile(z), z))

    # --- cross-section area A(z) of the internal volume, z measured from the tank's bottom ---
    def area_profile(self, z: np.ndarray) -> np.ndarray:
        R, hd, hc = self.R_int, self.h_dome, self.h_cyl
        A = np.zeros_like(z, dtype=float)
        if self.bulkhead == "upper_user":
            # concave bottom: the shared bulkhead bulges UP by hd into this tank
            r_b2 = np.where(z < hd, R ** 2 * np.clip(1 - (z / hd) ** 2, 0, None), 0.0)
            A = np.pi * (R ** 2 - r_b2)
            top0 = hc
            zt = z - top0
            top = np.where(zt > 0, R ** 2 * np.clip(1 - (zt / hd) ** 2, 0, None), 0.0)
            A = np.where(z <= top0, A, np.pi * top)
            return np.where(z > top0 + hd, 0.0, A)
        zb = z
        bottom = R ** 2 * np.clip(1 - ((hd - zb) / hd) ** 2, 0, None)
        A = np.where(z < hd, np.pi * bottom, np.pi * R ** 2)
        zt = z - (hd + hc)
        top = R ** 2 * np.clip(1 - (zt / hd) ** 2, 0, None)
        A = np.where(z > hd + hc, np.pi * top, A)
        return np.where(z > 2 * hd + hc, 0.0, A)

    def liquid_arrays(self, V_liq: float, n: int = 4000):
        """(z, A(z)) of the liquid filling the tank from the bottom up to volume V_liq (for inertia integration)."""
        z = np.linspace(0.0, self.L_prof or self.L_int, n)
        A = self.area_profile(z)
        cum = np.concatenate([[0.0], np.cumsum(0.5 * (A[1:] + A[:-1]) * np.diff(z))])
        V_liq = min(max(V_liq, 1e-12), cum[-1])
        k = max(1, min(int(np.searchsorted(cum, V_liq)), n - 1))
        zi = float(np.interp(V_liq, cum[k - 1:k + 1], z[k - 1:k + 1])) if cum[k] > cum[k - 1] else float(z[k])
        zz = np.linspace(0.0, zi, 3000)
        return zz, self.area_profile(zz)

    def liquid_centroid(self, V_liq: float, n: int = 4000) -> float:
        """Axial centroid (local z from tank bottom) of liquid filling the tank from the bottom up to V_liq."""
        if V_liq <= 0:
            return 0.0
        z = np.linspace(0.0, self.L_prof or self.L_int, n)
        A = self.area_profile(z)
        cum = np.concatenate([[0.0], np.cumsum(0.5 * (A[1:] + A[:-1]) * np.diff(z))])
        V_tot = cum[-1]
        V_liq = min(V_liq, V_tot)
        k = int(np.searchsorted(cum, V_liq))
        k = max(1, min(k, n - 1))
        zi = np.interp(V_liq, cum[: k + 1], z[: k + 1]) if cum[k] > cum[k - 1] else z[k]
        zz = np.linspace(0.0, zi, 2000)
        AA = self.area_profile(zz)
        den = np.trapezoid(AA, zz)
        return float(np.trapezoid(AA * zz, zz) / den) if den > 0 else 0.0


def size_tank_stack(D_ext: float, tanks: list, AR: float, wall_t: dict, arrangement: str) -> list:
    """Size the tanks of one stage (listed bottom -> top), at fixed EXTERNAL diameter.

    tanks: list of dicts {role, propellant, V_int, V_liquid, m_liquid}
    wall_t: {role: thickness} used for external/internal conversion
    arrangement: 'separate' | 'common_bulkhead' (2 tanks only)
    """
    out = []
    for k, t in enumerate(tanks):
        tw = wall_t[t["role"]]
        R = D_ext / 2.0 - tw
        if R <= 0:
            raise InfeasibleGeometry("tank wall thickness exceeds stage radius")
        out.append(TankGeometry(t["role"], t["propellant"], R, AR, 0.0, dome_height(R, AR), tw,
                                t["V_int"], t["V_liquid"], t["m_liquid"]))
    if arrangement == "common_bulkhead" and len(out) == 2:
        lo, up = out
        lo.bulkhead, up.bulkhead = "lower_owner", "upper_user"
        if abs(lo.R_int - up.R_int) > 1e-9:
            raise InfeasibleGeometry("common bulkhead requires equal internal radii")
        Vd = dome_volume(lo.R_int, AR)
        # lower tank: bottom dome + barrel + bulkhead dome volume (bulkhead bulges up into the upper tank)
        lo.h_cyl = (lo.V_int - 2 * Vd) / (math.pi * lo.R_int ** 2)
        # upper tank: barrel + top dome - bulkhead bulge
        up.h_cyl = (up.V_int - Vd + Vd) / (math.pi * up.R_int ** 2)  # = V_int/(pi R^2): bulge cancels top dome
        for g in (lo, up):
            if g.h_cyl < 0:
                if oversized_tanks_tolerated():
                    g.h_cyl = 0.0
                    continue
                raise InfeasibleGeometry(f"{g.role} tank barrel length negative for common-bulkhead layout")
        if up.h_cyl < up.h_dome:
            raise InfeasibleGeometry("upper tank barrel shorter than the shared bulkhead height")
        lo.L_int = lo.h_dome + lo.h_cyl                # bottom dome + barrel; bulkhead dome belongs to the interface
        up.L_int = up.h_cyl + up.h_dome                # barrel (containing bulkhead bulge) + top dome
    else:
        for g in out:
            g.h_cyl = barrel_length(g.V_int, g.R_int, AR)
            g.L_int = g.h_cyl + 2 * g.h_dome
    for g in out:
        g.L_prof = g.L_int + (g.h_dome if g.bulkhead == "lower_owner" else 0.0)
        g.L_ext = g.L_int + (2 * g.t_wall if g.bulkhead == "none" else g.t_wall)
        g.area_ext = 2 * math.pi * (g.R_int + g.t_wall) * g.h_cyl + 2 * dome_area(g.R_int + g.t_wall, AR)
    return out


# ---------- tank structural mass --------------------------------------------------------------
def pressure_vessel_thickness(R_int: float, AR: float, p_Pa: float, sigma_allow_Pa: float,
                              joint_eff: float, safety_factor: float, corrosion_m: float,
                              t_min_m: float) -> tuple:
    """SUPPLEMENTARY thin-wall membrane sizing (internal pressure only; no axial/bending loads, no buckling).

    cylinder: t = SF p R / (sigma eta) ;  hemisphere: t = SF p R / (2 sigma eta);
    ellipsoidal head: t = SF p D K / (2 sigma eta), K = (2 + AR^2)/6 (standard ASME-style shape factor, AR = R/h).
    Returns (t_cyl, t_dome) including corrosion/manufacturing allowance and a minimum gauge.
    """
    t_cyl = safety_factor * p_Pa * R_int / (sigma_allow_Pa * joint_eff) + corrosion_m
    K = (2.0 + AR ** 2) / 6.0
    t_dome = safety_factor * p_Pa * (2 * R_int) * K / (2.0 * sigma_allow_Pa * joint_eff) + corrosion_m
    return max(t_cyl, t_min_m), max(t_dome, t_min_m)


def pressure_vessel_mass(g: TankGeometry, rho_mat: float, t_cyl: float, t_dome: float) -> float:
    R_mid = g.R_int + 0.5 * t_cyl
    m_cyl = rho_mat * 2 * math.pi * R_mid * g.h_cyl * t_cyl
    n_dome = 2 if g.bulkhead == "none" else 1
    m_dome = rho_mat * dome_area(g.R_int + 0.5 * t_dome, g.AR) * t_dome * n_dome
    return m_cyl + m_dome


# ---------- whole-stage tank sizing (volumes -> geometry -> mass) -----------------------------
def size_stage_tanks(stage, m_loaded_total: float, props: dict, mer: dict) -> list:
    """Size all tanks of a stage for a total LOADED propellant mass (mission + startup + residual + margin).

    Returns TankGeometry list ordered bottom -> top with masses populated. Raises InfeasibleGeometry / ValueError.
    """
    try:
        return _size_stage_tanks(stage, m_loaded_total, props, mer)
    except InfeasibleGeometry as ex:
        # The geometry routines know the shape but not which stage it belongs to, so the dotted paths a
        # user interface needs are completed here, where the stage index is in hand.
        for opt in getattr(ex, "options", ()):
            if opt.get("path") and not opt["path"].startswith("stages"):
                opt["path"] = f"stages[{stage.index - 1}].{opt['path']}"
        ex.field = next((o["path"] for o in getattr(ex, "options", ()) if o.get("path")), None)
        raise


def _size_stage_tanks(stage, m_loaded_total: float, props: dict, mer: dict) -> list:
    tk = stage.tank
    m_ox, m_f = split_propellant(m_loaded_total, stage.of_ratio)
    info = {"oxidizer": (stage.oxidizer, m_ox), "fuel": (stage.fuel, m_f)}
    if sorted(tk.order_bottom_to_top) != ["fuel", "oxidizer"]:
        raise ValueError("tank order must contain 'fuel' and 'oxidizer' exactly once")
    tanks_in = []
    shrink = {}
    for role in tk.order_bottom_to_top:
        pname, m = info[role]
        ps = props[pname]
        shrink[role] = 0.0 if ps.boiling_K is None else shrink_fraction(tk.material.alpha_per_K, tk.load_temperature_K, ps.boiling_K)
        v_liq, v_ull, v_shr, v_req = required_volume(m, ps.density_kg_m3, tk.ullage_fraction[role], shrink[role])
        tanks_in.append(dict(role=role, propellant=pname, V_int=v_req, V_liquid=v_liq, m_liquid=m))

    wall = dict(tk.wall_t_assumed_m)
    pv_t = {}
    D_tank = tk.diameter_m or stage.diameter_m          # tanks may be narrower than the stage structure
    if D_tank > stage.diameter_m + 1e-9:
        raise ValueError(f"stage {stage.index}: tank diameter {D_tank} m exceeds the stage diameter {stage.diameter_m} m")
    for _ in range(60):
        tanks = size_tank_stack(D_tank, tanks_in, tk.dome_AR, wall, tk.arrangement)
        changed = False
        for g in tanks:
            if tk.mass_method[g.role] == "pressure_vessel":
                mat = tk.material
                tc, td = pressure_vessel_thickness(g.R_int, tk.dome_AR, tk.pressure_Pa[g.role], mat.sigma_allow_Pa,
                                                   mat.joint_efficiency, mat.safety_factor, mat.corrosion_allowance_m, mat.t_min_m)
                pv_t[g.role] = (tc, td)
                if abs(tc - wall[g.role]) > 1e-10:
                    wall[g.role] = tc
                    changed = True
        if not changed:
            break
    else:
        raise InfeasibleGeometry("pressure-vessel thickness iteration did not converge")

    for g in tanks:
        ps = props[g.propellant]
        method = tk.mass_method[g.role]
        g.mass_method = method
        if method == "akin_propellant_mass":
            if ps.tank_mer_per_kg is None:
                raise ValueError(f"no Table 8.6 MER for {g.propellant}; choose akin_volume or pressure_vessel")
            dev = abs(ps.density_kg_m3 - ps.tank_mer_ref_density) / ps.tank_mer_ref_density
            if dev > mer["tank_mer_density_tolerance"]:
                raise ValueError(f"density of {g.propellant} deviates {dev:.0%} from the MER reference density; "
                                 "choose a different tank mass method")
            g.mass_tank_kg = ps.tank_mer_per_kg * g.m_liquid_loaded
        elif method == "akin_volume":
            k = mer["tank_vol_mer_lh2_kg_m3"] if g.propellant == "LH2" else mer["tank_vol_mer_kg_m3"]
            g.mass_tank_kg = k * g.V_int
        elif method == "pressure_vessel":
            tc, td = pv_t[g.role]
            g.t_dome = td
            g.mass_tank_kg = pressure_vessel_mass(g, tk.material.rho_kg_m3, tc, td)
            g.notes.append("thin-wall membrane sizing only; no buckling/axial/bending loads")
        elif method == "mass_fraction":
            g.mass_tank_kg = tk.mass_fraction[g.role] * g.m_liquid_loaded
        elif method == "user_mass":
            g.mass_tank_kg = tk.user_mass_kg[g.role]
        else:
            raise ValueError(f"unknown tank mass method '{method}'")
        if tk.insulated[g.role]:
            g.mass_insulation_kg = ps.insulation_kg_m2 * g.area_ext
    return tanks
