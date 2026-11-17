"""Solid rocket motor (SRM) sizing: grain volume, motor casing geometry and casing mass.

Verified book equations (Section 8.5 "Solid Propulsion System Sizing", printed pp. 486-490):
  Eq. 8:17  mu = exp(dv/(g0 Isp))                      (rocket equation, same as 5:84)
  Eq. 8:18  m_casing = k_SRM m_p ,  k_SRM = 0.135 (steel, D6AC); 0.1154 for graphite-epoxy (p.490, Sec. 8.7.3.1:
            k_GrE = 0.855 k_steel, from Shuttle SRB casings 86.2 t steel vs 73.7 t Gr/E)
  Eq. 8:19  s_SRM = k/(1+k) = 0.1189 (steel), 0.1035 (Gr/E)
  Eq. 8:20  m_p = m_PL (mu-1)(1-s)/(1-mu s)            (aggregate sizing, same as 5:85)
  Eq. 8:22  m_p = I_total/(g0 Isp)                     (total-impulse specification)
  Eq. 8:23  Vol_prop = m_p / rho_prop
  Eq. 8:24  Vol_casing = 1.12 Vol_prop  (10 % grain openings for thrust tailoring + 2 % insulation/igniter)
Book modelling rules adopted here (p.489-490):
  * hemispherical domes (AR = 1) are suggested because of the high internal pressure; domes are filled with grain
  * NO start-up propellant (ignition assumed instantaneous) and, by default, NO residual propellant
  * the casing mass INCLUDES internal insulation, the nozzle, the thrust structure and TVC/gimbals
    -> a solid stage must NOT also be charged an engine, thrust-structure, gimbal, feed or pressurant mass
  * forward and aft skirts ARE added separately (unpressurised structure, Table 8.8 line 1)
  * only the PROTRUDING diverging nozzle length is added to the stage length (Eq. 8:30, see engine_geometry.py)
Burn rate: Eq. 4:32 (de Saint Robert) r = a Pc^n with n typically 0.4-0.7 (p.231) and Eq. 4:33 mdot = rho A_b r.
This module does not run an internal-ballistics solution: it reports the IMPLIED average burn rate web/t_burn
so the designer can check it against propellant data.

Grain model used for volume/geometry/inertia: a centre-perforated ("core burner", Fig. 4.10 right) grain whose
single cylindrical bore through the barrel holds exactly the 12 % non-propellant volume of Eq. 8:24; the domes
are filled with propellant. This is the simplest shape consistent with the book's volume rule.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
import numpy as np
from .tank_sizing import TankGeometry, dome_volume, dome_area, dome_height, InfeasibleGeometry
from .units import G0

G0_SM = 9.80665

# Book casing MER coefficients (Eq. 8:18 / p.490 list item 4)
K_SRM = {"steel": 0.135, "composite": 0.1154}
S_SRM = {k: v / (1.0 + v) for k, v in K_SRM.items()}          # Eq. 8:19
CASING_VOLUME_FACTOR = 1.12                                     # Eq. 8:24


def propellant_mass_from_total_impulse(I_total_Ns: float, isp_s: float) -> float:
    """Eq. 8:22: m_p = I_tot/(g0 Isp)."""
    if I_total_Ns <= 0 or isp_s <= 0:
        raise ValueError("total impulse and Isp must be positive")
    return I_total_Ns / (G0 * isp_s)


def is_stage_level(method: str) -> bool:
    """True when `method` predicts a whole STAGE's inert mass rather than just the motor casing.

    The book's methods give a MOTOR mass - casing, insulation, nozzle, thrust structure and TVC - and the
    caller adds skirts, interstage, avionics and wiring to reach a stage. The published regressions in
    solid_inert predict the finished stage, so a caller that adds those again would count them twice. Every
    caller of casing_mass() must ask this before building components on top of the answer.
    """
    from . import solid_inert
    return method in solid_inert.RELATIONS and solid_inert.RELATIONS[method].predicts == "stage"


def casing_mass(m_prop_kg: float, method: str, k_user: float | None = None, user_mass_kg: float | None = None) -> tuple:
    """Return (mass, k_effective, source text).

    method: book_steel | book_composite | mass_fraction | user_mass, or one of the published stage-level
    relations in solid_inert (see is_stage_level above - those return the WHOLE stage inert mass).
    """
    from . import solid_inert
    if method in solid_inert.RELATIONS:
        rel = solid_inert.get(method)
        m = rel.inert_kg(m_prop_kg)
        scope = "WHOLE STAGE inert" if rel.predicts == "stage" else "motor only"
        range_note = "" if rel.in_range(m_prop_kg) else (
            f"; EXTRAPOLATED - {m_prop_kg:,.0f} kg is outside the fitted range "
            f"{rel.valid_kg[0]:,.0f}-{rel.valid_kg[1]:,.0f} kg")
        return m, m / m_prop_kg if m_prop_kg > 0 else 0.0, (
            f"{rel.label} ({scope}): {rel.source}. {rel.stats}{range_note}")
    if method == "book_steel":
        return K_SRM["steel"] * m_prop_kg, K_SRM["steel"], "Eq. 8:18 with k_SRM = 0.135 (steel casing, Table 8.6 p.494)"
    if method == "book_composite":
        return K_SRM["composite"] * m_prop_kg, K_SRM["composite"], "Eq. 8:18 with k = 0.1154 (graphite-epoxy, p.490/8.7.3.1)"
    if method == "mass_fraction":
        if not k_user or k_user <= 0:
            raise ValueError("mass_fraction casing method needs casing_mass_fraction > 0")
        return k_user * m_prop_kg, k_user, f"user casing mass fraction k = {k_user:.4f} (Eq. 8:18 form)"
    if method == "user_mass":
        if user_mass_kg is None or user_mass_kg < 0:
            raise ValueError("user_mass casing method needs casing_mass_kg >= 0")
        return user_mass_kg, (user_mass_kg / m_prop_kg if m_prop_kg > 0 else 0.0), "user-specified casing mass"
    raise ValueError(f"unknown casing mass method '{method}'")


def dome_bore_volume(R: float, h_dome: float, r_bore: float) -> float:
    """Volume removed from ONE semi-ellipsoidal dome by a central cylindrical bore of radius r_bore.

    Dome profile r(z) = R sqrt(1 - (z/h)^2), z = 0 at the equator. The bore reaches the dome wall at
    z_b = h sqrt(1 - (r/R)^2); beyond that the whole remaining cap is inside the bore.
    """
    if r_bore <= 0:
        return 0.0
    if r_bore >= R:
        return 2.0 * math.pi * R * R * h_dome / 3.0
    zb = h_dome * math.sqrt(1.0 - (r_bore / R) ** 2)
    cap = math.pi * R * R * ((h_dome - zb) - (h_dome ** 3 - zb ** 3) / (3.0 * h_dome ** 2))
    return math.pi * r_bore ** 2 * zb + cap


def grain_volume(R: float, h_dome: float, h_cyl: float, r_bore: float, bore_full_length: bool) -> float:
    """Cast-grain volume inside a casing of radius R with a central bore (domes filled unless bored through)."""
    v = math.pi * (R * R - r_bore * r_bore) * h_cyl + 2.0 * (2.0 * math.pi * R * R * h_dome / 3.0)
    if bore_full_length:
        v -= 2.0 * dome_bore_volume(R, h_dome, r_bore)
    return v


@dataclass
class MotorCase(TankGeometry):
    """Motor casing geometry. Inherits the cylinder+2 domes volume/profile maths from TankGeometry.

    Added fields: V_prop (grain volume), R_bore, web_m. `area_profile` is the CASE internal cross-section;
    `grain_area_profile` is the propellant cross-section (annulus in the barrel, full in the domes).
    """
    V_prop: float = 0.0
    R_bore: float = 0.0
    web_m: float = 0.0
    volume_factor: float = CASING_VOLUME_FACTOR
    bore_full_length: bool = False       # True when the bore also runs through the domes (short, fat motors)
    stage_level_inert: bool = False      # mass_tank_kg is the whole stage's inert mass, not just the casing

    def grain_area_profile(self, z: np.ndarray) -> np.ndarray:
        """Propellant cross-section area at height z above the case internal bottom."""
        A = self.area_profile(z)
        hd, hc = self.h_dome, self.h_cyl
        bore = math.pi * self.R_bore ** 2
        if self.bore_full_length:
            return np.maximum(A - bore, 0.0)
        in_barrel = (z >= hd) & (z <= hd + hc)
        return np.where(in_barrel, np.maximum(A - bore, 0.0), A)

    def grain_volume_numeric(self, n: int = 20001) -> float:
        z = np.linspace(0.0, self.L_int, n)
        return float(np.trapezoid(self.grain_area_profile(z), z))

    def implied_burn_rate_mps(self, t_burn_s: float) -> float:
        """Average regression rate implied by the web thickness and the burn time (Eq. 4:33 context)."""
        return self.web_m / t_burn_s if t_burn_s > 0 else float("nan")


def size_motor_case(D_ext: float, m_prop_loaded_kg: float, rho_prop: float, dome_AR: float = 1.0,
                    wall_t_m: float = 0.0, volume_factor: float = CASING_VOLUME_FACTOR,
                    propellant_name: str = "solid") -> MotorCase:
    """Size one motor casing at fixed EXTERNAL diameter (Eqs. 8:23, 8:24 + Table 8.2 dome geometry).

    The bore through the barrel carries the whole non-propellant volume (grain openings + insulation + igniter).
    """
    if rho_prop <= 0:
        raise ValueError("solid propellant density must be positive")
    if volume_factor < 1.0:
        raise ValueError("casing volume factor must be >= 1 (Eq. 8:24 uses 1.12)")
    V_prop = m_prop_loaded_kg / rho_prop                       # Eq. 8:23
    V_case = volume_factor * V_prop                            # Eq. 8:24
    R = D_ext / 2.0 - wall_t_m
    if R <= 0:
        raise InfeasibleGeometry("casing wall thickness exceeds motor radius")
    hd = dome_height(R, dome_AR)
    h_cyl = (V_case - 2.0 * dome_volume(R, dome_AR)) / (math.pi * R ** 2)
    if h_cyl < 0:
        # Both ways out are exact, so solve for them rather than telling the user to experiment.
        # Feasible when V_case >= 2 * dome_volume(R) = 4 pi R^3 / (3 AR):
        #   on the diameter   R_max = cbrt(3 AR V_case / (4 pi)),  D_ext = 2 (R_max + wall)
        #   on the propellant m_p_min = rho V_case_needed / factor, V_case_needed = 4 pi R^3 / (3 AR)
        R_max = (3.0 * dome_AR * V_case / (4.0 * math.pi)) ** (1.0 / 3.0)
        D_max = 2.0 * (R_max + wall_t_m)
        m_min = rho_prop * (4.0 * math.pi * R ** 3 / (3.0 * dome_AR)) / volume_factor
        raise InfeasibleGeometry(
            f"solid motor: the casing needs {V_case:.3f} m^3 for its propellant, but two domes alone take "
            f"{2*dome_volume(R, dome_AR):.3f} m^3 at radius {R:.3f} m, so there is no barrel length left. "
            f"Either make the motor no wider than {D_max:.3f} m, or give it at least {m_min:,.0f} kg of "
            f"propellant at this diameter.",
            options=[
                # D_max is the exact boundary, and the offered value must not sit on it. Narrowing the stage
                # changes its mass, which redistributes the delta-v split, which changes the propellant, which
                # moves the boundary - so a value that is feasible for the CURRENT propellant can be infeasible
                # for the re-converged one. Measured on Scout G-1 stage 4 forced to 2.0 m: the old 0.5 mm
                # absolute margin failed, 1 % failed, 2 % was the first that settled. 5 % is taken for room on
                # other designs, and it is nearly free - 2 % to 20 % moves that vehicle's GLOM by 0.2 %.
                {"label": f"Make this stage no wider than {0.95 * D_max:.3f} m",
                 "path": "diameter_m", "value": round(0.95 * D_max, 3),
                 "note": "5 % inside the widest motor whose two domes still fit inside the propellant "
                         "volume, so that it stays feasible once the design re-converges"},
                {"label": f"Carry at least {m_min:,.0f} kg of propellant at {2*(R + wall_t_m):.3f} m",
                 "note": "propellant mass follows from the delta-v split, so raise this stage's share of "
                         "the delta-v, or the payload, rather than typing a propellant mass"},
            ])
    # Central bore holding the non-propellant volume (grain openings + insulation + igniter, Eq. 8:24).
    # Normal case: a bore through the barrel only. For a short, fat motor that bore would be unrealistically
    # wide, so it is run through the domes as well and its radius solved for the same grain volume.
    V_free = V_case - V_prop
    full_len = False
    R_bore = math.sqrt(V_free / (math.pi * h_cyl)) if h_cyl > 0 else float("inf")
    if R_bore > 0.8 * R:
        full_len = True
        lo, hi = 0.0, 0.95 * R
        if grain_volume(R, hd, h_cyl, hi, True) > V_prop:
            raise InfeasibleGeometry(
                "solid motor: even a bore through the whole casing cannot hold the required free volume - "
                "reduce the diameter, the casing volume factor or increase the propellant load")
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if grain_volume(R, hd, h_cyl, mid, True) > V_prop:
                lo = mid
            else:
                hi = mid
        R_bore = 0.5 * (lo + hi)
    if R_bore >= R:
        raise InfeasibleGeometry("solid motor: grain bore would exceed the casing radius")
    g = MotorCase(role="grain", propellant=propellant_name, R_int=R, AR=dome_AR, h_cyl=h_cyl, h_dome=hd,
                  t_wall=wall_t_m, V_int=V_case, V_liquid=V_prop, m_liquid_loaded=m_prop_loaded_kg,
                  V_prop=V_prop, R_bore=R_bore, web_m=R - R_bore, volume_factor=volume_factor,
                  bore_full_length=full_len)
    g.L_int = h_cyl + 2 * hd
    g.L_prof = g.L_int
    g.L_ext = g.L_int + 2 * wall_t_m
    g.area_ext = 2 * math.pi * (R + wall_t_m) * h_cyl + 2 * dome_area(R + wall_t_m, dome_AR)
    return g


def size_solid_stage(stage, m_prop_loaded_kg: float, solid_props: dict) -> list:
    """Stage-level entry point mirroring tank_sizing.size_stage_tanks(): returns [MotorCase] with mass filled in."""
    mo = stage.motor
    ps = solid_props[stage.propellant]
    if mo.n_motors != 1:
        raise ValueError("a serial solid stage must have exactly one motor casing (use strap-on boosters for clusters)")
    try:
        g = size_motor_case(stage.diameter_m, m_prop_loaded_kg, ps.density_kg_m3, mo.dome_AR,
                            mo.wall_t_assumed_m, mo.casing_volume_factor, stage.propellant)
    except InfeasibleGeometry as ex:
        # The casing sizer knows the geometry but not which stage it belongs to, so the dotted paths that a
        # user interface needs are completed here, where the stage index is known.
        for opt in getattr(ex, "options", ()):
            if opt.get("path") and not opt["path"].startswith("stages"):
                opt["path"] = f"stages[{stage.index - 1}].{opt['path']}"
        ex.field = next((o["path"] for o in getattr(ex, "options", ()) if o.get("path")), None)
        ex.args = (f"stage {stage.index}: " + str(ex),)
        raise
    m_case, k_eff, src = casing_mass(m_prop_loaded_kg, mo.casing_mass_method, mo.casing_mass_fraction,
                                     mo.casing_mass_kg)
    g.mass_tank_kg = m_case
    g.mass_method = mo.casing_mass_method
    g.stage_level_inert = is_stage_level(mo.casing_mass_method)
    g.notes.append(src)
    if g.stage_level_inert:
        g.notes.append("this figure is the WHOLE STAGE inert mass, so the skirts, interstage, avionics and "
                       "wiring the bottom-up build-up would otherwise add are suppressed - they are already "
                       "inside it")
    else:
        g.notes.append("casing mass includes internal insulation, nozzle, thrust structure and TVC (book p.490)")
    return [g]


# ===========================================================================================================
# Internal ballistics: what the grain actually delivers (book Sec. 4.4.2-4.4.3)
#
# The sizing above assumes constant thrust over the burn. A real grain does not deliver that, and the book says
# why: mass flow follows the burning area, which changes as the grain regresses (Eq. 4:33), and the burn rate
# follows the chamber pressure (Eq. 4:32). Three book relations close the loop:
#
#     r   = a Pc^n                      Eq. 4:32, de Saint Robert's law
#     mdot = rho A_b r                  Eq. 4:33
#     mdot = Pc A_t / c*                Table 4.4, p.228
#
# Eliminating mdot and r gives the equilibrium chamber pressure
#
#     Pc = [rho a c* (A_b/A_t)]^(1/(1-n))
#
# whose exponent 1/(1-n) is exactly the book's stability argument: n < 1 and a disturbance settles, n > 1 and
# "a small decrease in chamber pressure could result in a catastrophic drop in burn rate" (p.231).
#
# A note on Eq. 4:32 as printed. The book writes it "mdot = a Pc^b", but the surrounding text introduces it as
# the law for "the burn rate, and for solid propellant, is itself a function of the chamber pressure", and its
# exponent range of 0.4-0.7 is the burning-rate exponent. Taken literally alongside Eq. 4:33 it would give two
# different expressions for the same mdot. It is read here as r = a Pc^n, which is de Saint Robert's law as it
# is universally written and the only reading consistent with Eq. 4:33.
#
# Nothing here is invented: n comes from the propellant library (within the book's 0.4-0.7 range), c* from
# Table 4.7, the throat area from Eq. 8:28, and the burning-rate coefficient a is CALIBRATED so the motor
# delivers its own design chamber pressure at its mean burning area - so the solution reproduces the sizing on
# average and shows how far the real profile departs from it.
# ===========================================================================================================
def burn_area_m2(case: MotorCase, web_burned_m: float, dw: float = 1e-5) -> float:
    """Burning surface at a given regressed web, as -dV/dw of the cast grain.

    This is exact for any geometry the grain-volume function can describe, and for the hollow-cylinder grain of
    Fig. 4.12 #1 it reduces to 2 pi (R_bore + w) h_cyl - a surface that GROWS as the grain burns, which is why
    the book says that shape "will produce thrust levels that increase with time" (p.233).
    """
    r = case.R_bore + web_burned_m
    if r >= case.R_int:
        return 0.0
    lo = grain_volume(case.R_int, case.h_dome, case.h_cyl, min(r + dw, case.R_int), case.bore_full_length)
    hi = grain_volume(case.R_int, case.h_dome, case.h_cyl, max(r - dw, 0.0), case.bore_full_length)
    return max((hi - lo) / (min(r + dw, case.R_int) - max(r - dw, 0.0)), 0.0)


def end_burner_area_m2(case: MotorCase) -> float:
    """The other shape the book describes in full: a cigarette burn across the whole cross-section (p.232)."""
    return math.pi * case.R_int ** 2


def chamber_pressure_Pa(rho: float, a: float, c_star: float, A_b: float, A_t: float, n: float) -> float:
    """Pc = [rho a c* (A_b/A_t)]^(1/(1-n)), from Eqs. 4:32, 4:33 and Table 4.4."""
    if n >= 1.0:
        raise ValueError("burn-rate exponent n must be below 1: at n >= 1 combustion is unstable (book p.231) "
                         "and there is no equilibrium pressure to solve for")
    if min(rho, a, c_star, A_t) <= 0 or A_b <= 0:
        return 0.0
    return (rho * a * c_star * A_b / A_t) ** (1.0 / (1.0 - n))


def calibrate_burning_rate_coefficient(rho: float, c_star: float, A_b_ref: float, A_t: float, n: float,
                                       pc_design_Pa: float) -> float:
    """The `a` that makes the equilibrium pressure equal the design pressure at a reference burning area.

    The book gives the exponent's range but no coefficient for any propellant - those are "experimentally
    measured propellant characteristics that vary among propellants" (p.231). Rather than inventing one, it is
    solved for from the motor the sizing already produced, which makes the profile below a statement about the
    GRAIN SHAPE rather than about a propellant this tool has no data for.
    """
    if A_b_ref <= 0 or A_t <= 0 or pc_design_Pa <= 0:
        return 0.0
    return pc_design_Pa ** (1.0 - n) * A_t / (rho * c_star * A_b_ref)


def burn_profile(case: MotorCase, rho_kg_m3: float, c_star_mps: float, n: float, A_t_m2: float,
                 pc_design_Pa: float, isp_vac_s: float, grain: str = "core", steps: int = 240) -> dict:
    """Chamber pressure, burn rate, mass flow and thrust through the burn, against time.

    `grain` is "core" (hollow cylinder, Fig. 4.12 #1) or "end" (end burner, Fig. 4.10 left) - the two shapes
    the book describes completely. The star, cog and finocyl grains of Fig. 4.12 are drawn but never
    dimensioned, so they are not offered: their burning-area laws are not in this book.
    """
    if n <= 0 or c_star_mps <= 0:
        return dict(ok=False, reason="this propellant has no burn-rate exponent or c* in the library, so the "
                                     "internal ballistics cannot be solved without inventing them")
    web = max(case.R_int - case.R_bore, 0.0)
    if grain == "end":
        areas = [(w, end_burner_area_m2(case)) for w in
                 [case.h_cyl * i / steps for i in range(steps + 1)]]
        web = case.h_cyl
    else:
        areas = [(web * i / steps, burn_area_m2(case, web * i / steps)) for i in range(steps + 1)]
    live = [(w, A) for w, A in areas if A > 0]
    if len(live) < 2:
        return dict(ok=False, reason="the grain has no burning surface to regress")
    A_mean = sum(A for _w, A in live) / len(live)
    a = calibrate_burning_rate_coefficient(rho_kg_m3, c_star_mps, A_mean, A_t_m2, n, pc_design_Pa)

    pts, t = [], 0.0
    for i, (w, A_b) in enumerate(live):
        pc = chamber_pressure_Pa(rho_kg_m3, a, c_star_mps, A_b, A_t_m2, n)
        r = a * pc ** n
        mdot = rho_kg_m3 * A_b * r
        pts.append(dict(web_m=w, t_s=t, A_b_m2=A_b, Kn=A_b / A_t_m2, pc_Pa=pc, r_mps=r, mdot_kgs=mdot,
                        thrust_N=mdot * G0_SM * isp_vac_s))
        if i + 1 < len(live):
            dw = live[i + 1][0] - w
            r_next = a * chamber_pressure_Pa(rho_kg_m3, a, c_star_mps, live[i + 1][1], A_t_m2, n) ** n
            t += 2.0 * dw / (r + r_next) if (r + r_next) > 0 else 0.0
    thrusts = [p["thrust_N"] for p in pts]
    pcs = [p["pc_Pa"] for p in pts]
    impulse = sum(0.5 * (pts[i]["thrust_N"] + pts[i + 1]["thrust_N"]) * (pts[i + 1]["t_s"] - pts[i]["t_s"])
                  for i in range(len(pts) - 1))
    return dict(ok=True, grain=grain, points=pts, a_calibrated=a, n=n, c_star_mps=c_star_mps, A_t_m2=A_t_m2,
                web_m=web, burn_time_s=pts[-1]["t_s"], total_impulse_Ns=impulse,
                thrust_initial_N=thrusts[0], thrust_final_N=thrusts[-1], thrust_max_N=max(thrusts),
                thrust_mean_N=(impulse / pts[-1]["t_s"] if pts[-1]["t_s"] > 0 else 0.0),
                pc_max_Pa=max(pcs), pc_min_Pa=min(pcs), pc_design_Pa=pc_design_Pa,
                Kn_min=min(p["Kn"] for p in pts), Kn_max=max(p["Kn"] for p in pts),
                progressive=thrusts[-1] > thrusts[0], stable=n < 1.0)
