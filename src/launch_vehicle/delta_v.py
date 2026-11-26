"""Mission delta-v budget.

Sign convention: every line item is a *requirement on the launch vehicle* in m/s; positive adds to the
requirement, negative reduces it (only the Earth-rotation contribution can be negative). The total is the
simple sum. Structure follows book Eq. 3:17 (dv_ideal = dv_orbit + steering + drag + gravity (+ reserves)),
p. 163, and the book's Example 3.9 treatment of Earth rotation (p. 185).

Margin is applied exactly once, as a fraction of (ideal + rotation + maneuvers + losses + allowances).
Loss terms are USER-DEFINED engineering estimates (this tool has no trajectory simulation).
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from .units import G0
from . import orbit as orb
from .units import EarthModel


@dataclass
class BudgetLine:
    name: str
    value_mps: float
    category: str          # ideal | rotation | maneuver | loss | allowance | margin
    source: str
    in_total: bool = True


@dataclass
class DeltaVBudget:
    lines: list = field(default_factory=list)
    info: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)

    @property
    def total_mps(self) -> float:
        return sum(l.value_mps for l in self.lines if l.in_total)

    def subtotal(self, *cats: str) -> float:
        return sum(l.value_mps for l in self.lines if l.in_total and l.category in cats)


# ---- Book regression for total ascent velocity losses ------------------------------------------------------------
# Book Eq. 3:36-3:38 (pp.181-182): dv_penalty = K3 + K4 T_mix, from a survey of >1,000 data points on 17 modern launch vehicles
# (RMS error ~260 m/s, <3 % of total dv for circular LEO). It lumps gravity + drag + steering + propulsion losses.
# Total design speed (Eq. 3:35): dv_total = dv_circ + dv_penalty + dv_rot.
def book_penalty_mps(h_p_km: float, t_ascent_s: float, t_3stage_s: float) -> dict:
    K3 = 429.9 + 1.602 * h_p_km + 0.001224 * h_p_km ** 2
    K4 = 2.328 - 0.0009687 * h_p_km
    t_mix = 0.405 * t_ascent_s + 0.595 * t_3stage_s
    return dict(K3=K3, K4=K4, T_mix=t_mix, penalty=K3 + K4 * t_mix)


def simple_total_mps(v_circ_mps: float, h_m: float, t_ascent_s: float, earth_radius_m: float) -> dict:
    """Book Eq. 3:32 (p.180): the single-expression estimate of the TOTAL required speed.

        dv_total = sqrt(v_circ^2 + 2 g0 h (R/(R+h))^2) + 0.0015 Ta^2 + 0.0882 Ta + 1,036 m/s

    The first term is the energy-form burnout speed (orbital speed plus the climb to altitude h); the rest is
    the loss allowance, with Ta the ascent time in seconds. The 1st-edition printing of this equation carried
    spurious 's' and 's^2' in the denominators of the two time coefficients; the errata (1st ed., p.159) removes
    them and the 2nd edition prints it as implemented here. Circular orbits only.
    """
    energy = math.sqrt(v_circ_mps ** 2 + 2.0 * G0 * h_m * (earth_radius_m / (earth_radius_m + h_m)) ** 2)
    loss = 0.0015 * t_ascent_s ** 2 + 0.0882 * t_ascent_s + 1036.0
    return dict(energy_speed=energy, loss=loss, total=energy + loss)


def k1k2_penalty_mps(h_p_km: float, t_ascent_s: float) -> dict:
    """Book Eqs. 3:33-3:34 (p.180): dv_penalty = K1 + K2 Ta, the intermediate-fidelity loss estimate.

    K1 = 662.1 + 1.602 Hp + 0.001224 Hp^2 ;  K2 = 1.7871 - 0.0009687 Hp  (Hp = parking-orbit altitude, km)
    Same structure as Eq. 3:35 but with the plain ascent time instead of the mixed three-step time.
    """
    k1 = 662.1 + 1.602 * h_p_km + 0.001224 * h_p_km ** 2
    k2 = 1.7871 - 0.0009687 * h_p_km
    return dict(K1=k1, K2=k2, penalty=k1 + k2 * t_ascent_s)


def equivalent_three_stage_time_s(dv_parking_mps: float, isp_s: float, accel0_mps2: float) -> float:
    """Eq. 3:36: T3s = (3 g0 Isp / (T/m0)) (1 - exp(-dv_p / (3 g0 Isp))), T/m0 = liftoff acceleration without gravity."""
    c = G0 * isp_s
    return 3.0 * c / accel0_mps2 * (1.0 - math.exp(-dv_parking_mps / (3.0 * c)))


class LossModelError(ValueError):
    """A loss-model input that cannot be used. `field` is the input to change, for the GUI."""

    def __init__(self, message, field: str = "mission.losses.model"):
        super().__init__(message)
        self.field = field


#: geostationary altitude above the equator, 35,786 km: the radius where an orbit's period is one sidereal day
GEO_ALT_M = 35786e3

# Table 3.2 (p.177) two-stage loss shares of dv_ideal, used ONLY to present an indicative split of the lumped penalty.
TABLE_3_2_SHARES = dict(gravity=1527.0, drag=116.0, steering=115.0, propulsion=77.0)


def build_budget(earth: EarthModel, m: dict, ascent: dict | None = None) -> DeltaVBudget:
    """m: validated mission dict (see config_io). ascent: {'t_ascent_s','accel0_mps2','isp_s'} needed by the
    'book_penalty' loss model (supplied by the sizing loop because burn times depend on the design). Returns the budget."""
    b = DeltaVBudget()
    otype = m["orbit_type"]
    lat = m["site_latitude_deg"]
    perigee = m["perigee_altitude_m"]
    apogee = m.get("apogee_altitude_m")
    ecc = m.get("eccentricity")
    inc = m["inclination_deg"]

    if otype in ("LEO", "SSO"):
        apogee, ecc = perigee, None
    elif otype in ("GTO", "GEO_VIA_GTO", "GEO_DIRECT"):
        if apogee is None and ecc is None:
            raise orb.OrbitError(f"{otype} needs an apogee altitude (e.g. 35786 km) or eccentricity",
                                 field="mission.orbit.apogee_altitude_km",
                                 options=[{"label": "Set the apogee to 35,786 km", "path": "mission.orbit.apogee_altitude_km",
                                           "value": 35786.0, "note": "geostationary altitude"},
                                          {"label": "Change the orbit type to LEO", "path": "mission.orbit.type",
                                           "value": "LEO", "note": "a circular orbit at the perigee altitude"}])
        if otype.startswith("GEO") and apogee is not None and abs(apogee - GEO_ALT_M) > 50e3:
            raise orb.OrbitError(f"{otype} goes to geostationary orbit, at 35,786 km, but the apogee is "
                                 f"{apogee / 1e3:,.0f} km", field="mission.orbit.apogee_altitude_km",
                                 options=[{"label": "Set the apogee to 35,786 km", "path": "mission.orbit.apogee_altitude_km",
                                           "value": 35786.0, "note": "geostationary altitude"},
                                          {"label": "Change the orbit type to CUSTOM", "path": "mission.orbit.type",
                                           "value": "CUSTOM", "note": "keeps the apogee you gave"}])
    elif otype != "CUSTOM":
        raise orb.OrbitError(f"unsupported orbit type {otype}", field="mission.orbit.type")

    el = orb.orbit_from_altitudes(earth, perigee, apogee, ecc, inc)
    if otype == "SSO":
        inc = orb.sso_inclination_deg(earth, el.a_m, el.e)
        b.notes.append(f"SSO inclination computed from J2 nodal drift: {inc:.3f} deg (supplementary formula)")
        el = orb.orbit_from_altitudes(earth, perigee, apogee, ecc, inc)

    az = m.get("launch_azimuth_deg")
    if az is None:
        az = orb.launch_azimuth_deg(inc, lat)
        az_src = "computed: sin(beta)=cos(i)/cos(lat), ascending pass"
    else:
        az_src = "user-specified"

    v_inj = el.v_perigee_ms      # injection assumed at perigee, flight-path angle 0 (documented limitation)
    v_need, v_site = orb.needed_speed(earth, v_inj, az, lat, 0.0, m["include_earth_rotation"])
    b.info.update(dict(orbit=el, inclination_deg=inc, azimuth_deg=az, azimuth_source=az_src,
                       v_injection_mps=v_inj, v_site_mps=v_site, v_needed_mps=v_need,
                       earth_model=earth.name, orbit_type=otype))

    b.lines.append(BudgetLine("Ideal injection speed (inertial, at perigee)", v_inj, "ideal",
                              "Eq. 3:1 / 3:4 (book pp.156-157)"))
    b.lines.append(BudgetLine("Earth-rotation contribution (vector, launch site)", v_need - v_inj, "rotation",
                              "Book Example 3.9 (p.185) method; negative = benefit"
                              if m["include_earth_rotation"] else "Rotation excluded by user"))

    if otype == "GEO_DIRECT":
        v_c = orb.circular_speed(el.r_a_m, earth.mu_m3s2)
        v_a = el.v_apogee_ms
        di = math.radians(inc)
        dv = math.sqrt(v_a ** 2 + v_c ** 2 - 2 * v_a * v_c * math.cos(di))
        b.lines.append(BudgetLine("Apogee circularisation + plane change (ideal)", dv, "maneuver",
                                  "Vector-difference burn at apogee (supplementary); needs restartable upper stage; "
                                  "coast and finite-burn losses of that burn not modelled"))

    al = m.get("air_launch")
    if al:
        # SUPPLEMENTARY (not a book method): an air-launched vehicle is released with speed and altitude already
        # gained by the carrier aircraft. Only the horizontal component of the release speed is credited; the
        # altitude gain is NOT credited as delta-v (it reduces gravity/drag losses, which the user must reflect
        # in the loss estimates). The book's loss regression was fitted to ground launches, so 'user' losses are
        # required with this option (enforced in validation.py).
        v_rel = al["release_speed_mps"] * math.cos(math.radians(al.get("flight_path_angle_deg", 0.0)))
        b.lines.append(BudgetLine("Air-launch release speed credit (horizontal component)", -v_rel, "rotation",
                                  f"Supplementary: carrier release at {al['release_speed_mps']:.0f} m/s, "
                                  f"{al['release_altitude_m']/1e3:.1f} km; altitude gain not credited as delta-v"))
        b.info["air_launch"] = dict(al, credit_mps=v_rel)

    model = m.get("loss_model", "user")
    if model in ("book_simple", "book_k1k2") and ascent is None:
        raise LossModelError(f"loss model '{model}' needs ascent-time information from the sizing loop")
    if model == "book_simple":
        if otype not in ("LEO", "SSO"):
            raise LossModelError("loss model 'book_simple' (Eq. 3:32) is defined for circular orbits only")
        sm = simple_total_mps(orb.circular_speed(el.r_p_m, earth.mu_m3s2), perigee, ascent["t_ascent_s"], earth.radius_m)
        b.info["loss_model"] = dict(sm, T_ascent_s=ascent["t_ascent_s"])
        # replace the ideal line with the equation's own energy-form speed so the budget is not double counted
        b.lines[0] = BudgetLine("Energy-form burnout speed sqrt(v_circ^2 + 2 g0 h (R/(R+h))^2) (Book Eq. 3:32)",
                                sm["energy_speed"], "ideal", "Book Eq. 3:32, p.180 (includes the climb to altitude)")
        b.lines.append(BudgetLine("Ascent losses 0.0015 Ta^2 + 0.0882 Ta + 1,036 (Book Eq. 3:32)", sm["loss"], "loss",
                                  f"Book Eq. 3:32, p.180, with Ta = {ascent['t_ascent_s']:.0f} s "
                                  "(1st-ed. errata p.159 removed spurious 's' and 's^2' from the coefficients)"))
        b.lines.append(BudgetLine("Other allowances (reserves, extra)", m["other_allowance_mps"] or 0.0, "allowance", "User-defined"))
    elif model == "book_k1k2":
        hp_km = m["perigee_altitude_m"] / 1e3
        kk = k1k2_penalty_mps(hp_km, ascent["t_ascent_s"])
        b.info["loss_model"] = dict(kk, T_ascent_s=ascent["t_ascent_s"])
        b.lines.append(BudgetLine("Ascent losses: K1 + K2 Ta (Book Eq. 3:33-3:34)", kk["penalty"], "loss",
                                  f"Book Eqs. 3:33-3:34, p.180: K1={kk['K1']:.1f}, K2={kk['K2']:.4f}, "
                                  f"Ta={ascent['t_ascent_s']:.0f} s"))
        b.lines.append(BudgetLine("Other allowances (reserves, extra)", m["other_allowance_mps"] or 0.0, "allowance", "User-defined"))
    elif model == "book_penalty":
        if ascent is None:
            raise LossModelError("book_penalty loss model needs ascent-time information from the sizing loop")
        hp_km = m["perigee_altitude_m"] / 1e3
        # Eq. 3:36 divides by the lift-off acceleration, so an intermediate design that cannot lift off would
        # produce an unbounded equivalent burn time and make the sizing loop diverge. The regression only means
        # anything for a vehicle that does lift off, so the acceleration is floored at 1 g0 here; whether the
        # final design really lifts off is checked separately (and reported) by the T/W constraint.
        a0 = ascent["accel0_mps2"]
        if a0 < G0:
            b.notes.append(f"Lift-off acceleration {a0:.2f} m/s2 is below 1 g0: the loss regression was evaluated "
                           "with a 1 g0 floor (see the T/W check for feasibility)")
            a0 = G0
        t3s = equivalent_three_stage_time_s(v_need, ascent["isp_s"], a0)
        bp = book_penalty_mps(hp_km, ascent["t_ascent_s"], t3s)
        b.info["loss_model"] = dict(bp, T_ascent_s=ascent["t_ascent_s"], T_3stage_s=t3s, accel0_mps2=a0,
                                    isp_mean_s=ascent["isp_s"], dv_parking_mps=v_need)
        if otype not in ("LEO", "SSO"):
            b.notes.append("Book regression Eq. 3:37 was fitted to LEO launches; for other injection orbits it is an extrapolation (RMS error ~260 m/s for LEO)")
        b.lines.append(BudgetLine("Ascent losses: gravity + drag + steering + propulsion (lumped, Book Eq. 3:37-3:38)", bp["penalty"], "loss",
                                  f"Book regression pp.181-182: K3={bp['K3']:.1f}, K4={bp['K4']:.4f}, T_mix={bp['T_mix']:.1f} s "
                                  f"(T_ascent={ascent['t_ascent_s']:.1f} s, T_3s={t3s:.1f} s)"))
        tot = sum(TABLE_3_2_SHARES.values())
        for nm, v in TABLE_3_2_SHARES.items():
            b.lines.append(BudgetLine(f"   indicative {nm} share of lumped losses (Table 3.2 proportions)", bp["penalty"] * v / tot, "info",
                                      "Informational split only - NOT added to the total (already inside the lumped penalty)", in_total=False))
        b.lines.append(BudgetLine("Other allowances (reserves, extra)", m["other_allowance_mps"] or 0.0, "allowance", "User-defined"))
    elif model == "simulated":
        if m.get("simulated_loss_mps") is None:
            raise LossModelError("loss model 'simulated' needs the flown losses, which the sizing loop supplies")
        b.lines.append(BudgetLine("Ascent losses of the simulated flight (gravity, drag, steering, back pressure, coast "
                                  "and second burn)", m["simulated_loss_mps"], "loss",
                                  "SUPPLEMENTARY: the ideal speed the flown ascent took to the orbit, less the lines above"))
        b.lines.append(BudgetLine("Other allowances (reserves, extra)", m["other_allowance_mps"] or 0.0, "allowance", "User-defined"))
    elif model == "user":
        for key, label, src in (
            ("gravity_loss_mps", "Gravity loss (estimate)", "User-defined; typical Table 3.4 range 1,150-1,534 m/s (p.180)"),
            ("drag_loss_mps", "Aerodynamic drag loss (estimate)", "User-defined; typical Table 3.4 range 40-156 m/s (p.180)"),
            ("steering_loss_mps", "Steering / trajectory-shaping loss (estimate)", "User-defined; Table 3.4 range 33-358 m/s (p.180)"),
            ("other_allowance_mps", "Other allowances (propulsion loss, reserves)", "User-defined; Example 3.9 'propulsion loss'"),
        ):
            if m.get(key) is None:
                raise LossModelError(f"loss model 'user' needs mission.losses.{key}", field=f"mission.losses.{key}")
            b.lines.append(BudgetLine(label, m[key], "allowance" if key == "other_allowance_mps" else "loss", src))
    else:
        raise LossModelError(f"unknown loss model '{model}' (use 'book_penalty', 'book_k1k2', 'book_simple', 'simulated' or 'user')")

    base = b.total_mps
    marg = m["design_margin_fraction"] * base
    b.lines.append(BudgetLine(f"Design margin ({m['design_margin_fraction']*100:.1f}% of subtotal)", marg, "margin",
                              "User-defined fraction applied once to the subtotal"))
    return b
