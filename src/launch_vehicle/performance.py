"""Performance curves: what a **built** vehicle delivers to other orbits (book Sec. 3.8, pp.195-197).

The sizing loop answers "how big must the vehicle be for this payload and this orbit". A performance curve asks
the opposite and far more practical question: *the vehicle is what it is - what does it lift to a different
orbit?* That is the carpet plot every launch-service user guide opens with (book Figs. 3.27-3.29), and it is the
output a payload customer asks for by name.

Method (method register M54). Freeze the hardware of the converged design: each stage's loaded propellant and its
split into mission / start-up / residual / loading margin, its dry mass, its effective Isp, the fairing and the
strap-ons. Only the payload changes, and with it the payload adapter, which follows the payload through its own
MER because an adapter is sized for the spacecraft it carries. For a trial payload the stack masses follow from
the same bookkeeping the sizing loop uses, the rocket equation gives the delta-v the vehicle *achieves*, and
`delta_v.build_budget` gives the delta-v the target orbit *requires*. The capability is the root of
`achieved(m_PL) - required(m_PL) = 0`; achieved falls monotonically with payload while required does not depend
on it except through lift-off acceleration, so the root is unique and bisection cannot miss it.

What this is not. The structure is not re-optimised: a payload far from the reference one flies on a fairing and
an avionics suite sized for a different mission, so the curve is this vehicle's performance, not a family of
re-sized vehicles. The delta-v requirement keeps the loss model's own limits - the book regressions are low-Earth
-orbit fits, which is why the sweeps stop at 1,000 km. An inclination below the launch-site latitude is reported
as unreachable rather than flown, because the dog-leg or plane change that would reach it is not modelled.
"""
from __future__ import annotations
import copy
import math
from dataclasses import dataclass, field

from . import delta_v as dvmod
from .mass_budget import paf_mass
from .units import EARTH_MODELS, G0

MAX_SWEEP_ALTITUDE_KM = 1000.0     # the book's ascent-loss regressions are LEO fits; above this they extrapolate


@dataclass
class FrozenVehicle:
    """The hardware of a converged design, with the payload left free."""
    name: str
    isp_s: list                       # effective Isp per stage [s]
    m_dry_kg: list
    m_loaded_kg: list                 # propellant loaded on the stage
    m_startup_kg: list
    m_unusable_kg: list               # residual + loading margin: still on board at burnout
    fairing_kg: float
    fairing_jettison_stage: int
    booster_mass_kg: float = 0.0      # loaded strap-ons, carried by their attach stage
    booster_attach_stage: int = 0
    booster_dv_mps: float = 0.0       # delta-v the parallel phases contribute in the reference design
    liftoff_thrust_N: float = 0.0
    burn_times_s: list = field(default_factory=list)
    staging_delay_s: float = 0.0
    ascent_time_s: float = 0.0
    reference_payload_kg: float = 0.0
    reference_paf_kg: float = 0.0
    reference_dv_mps: float = 0.0
    spec: object = None               # the design the vehicle came from (read-only here)

    @property
    def n_stages(self):
        return len(self.isp_s)

    # -- the payload adapter is the one piece of structure that follows the payload
    def paf_kg(self, payload_kg: float) -> float:
        if self.spec is None:
            return self.reference_paf_kg
        s = copy.copy(self.spec)
        s.payload_mass_kg = payload_kg
        return paf_mass(s)

    def glom(self, payload_kg: float) -> float:
        return (payload_kg + self.paf_kg(payload_kg) + self.fairing_kg + self.booster_mass_kg
                + sum(self.m_dry_kg) + sum(self.m_loaded_kg))

    def stage_delta_v(self, payload_kg: float) -> list:
        """Delta-v of each stage with this payload, by the mass bookkeeping the sizing loop uses."""
        N = self.n_stages
        paf = self.paf_kg(payload_kg)
        out = []
        for j in range(N):
            carried = payload_kg + paf
            if (j + 1) < self.fairing_jettison_stage:
                carried += self.fairing_kg
            carried += sum(self.m_dry_kg[k] + self.m_loaded_kg[k] for k in range(j + 1, N))
            m_ignition = carried + self.m_dry_kg[j] + self.m_loaded_kg[j]
            if (j + 1) == self.booster_attach_stage:
                m_ignition += self.booster_mass_kg
            m_burn_start = m_ignition - self.m_startup_kg[j]
            m_burnout = carried + self.m_dry_kg[j] + self.m_unusable_kg[j]
            out.append(G0 * self.isp_s[j] * math.log(m_burn_start / m_burnout)
                       if m_burnout > 0 and m_burn_start > m_burnout else 0.0)
        return out

    def delta_v(self, payload_kg: float) -> float:
        """Total delta-v achieved. With strap-ons the parallel phases are not re-solved: their contribution is
        held at the reference design's value, so a boosted vehicle's curve is a first-order answer near its
        design payload (said so in the report)."""
        return sum(self.stage_delta_v(payload_kg)) + self.booster_dv_mps


def freeze(res) -> FrozenVehicle:
    """Freeze a converged VehicleResult into the hardware a performance sweep flies."""
    spec = res.spec
    fv = FrozenVehicle(
        name=spec.name,
        isp_s=[s.isp_eff_s for s in res.stages],
        m_dry_kg=[s.m_dry_kg for s in res.stages],
        m_loaded_kg=[s.m_prop_loaded_kg for s in res.stages],
        m_startup_kg=[s.m_startup_kg for s in res.stages],
        m_unusable_kg=[s.m_residual_kg + s.m_margin_prop_kg for s in res.stages],
        fairing_kg=res.fairing_mass_kg,
        fairing_jettison_stage=spec.fairing.jettison_stage,
        liftoff_thrust_N=res.liftoff_thrust_N,
        burn_times_s=[s.burn_time_s for s in res.stages],
        staging_delay_s=spec.mission.get("staging_delay_s", 0.0) or 0.0,
        reference_payload_kg=res.payload_mass_kg,
        reference_paf_kg=res.paf_mass_kg,
        reference_dv_mps=res.dv_required_mps,
        spec=spec)
    if res.boosters is not None:
        b = res.boosters
        fv.booster_mass_kg = b.m_total_kg
        fv.booster_attach_stage = b.attach_stage
        sr = res.stages[b.attach_stage - 1]
        # with boosters attached the stage's delta-v comes from the phase model, not from the serial rocket
        # equation; the difference between the two is the parallel burn's contribution, carried through unchanged
        fv.booster_dv_mps = sr.dv_mps - fv.stage_delta_v(res.payload_mass_kg)[b.attach_stage - 1]
    fv.ascent_time_s = sum(fv.burn_times_s) + fv.staging_delay_s * (fv.n_stages - 1)
    return fv


# --------------------------------------------------------------------------- delta-v required for an orbit
def required_dv_mps(spec, fv: FrozenVehicle, orbit: dict, payload_kg: float) -> float:
    """Delta-v required for `orbit`, with the ascent inputs the loss models need taken from the frozen vehicle.

    `orbit` overrides mission keys (orbit_type, perigee_altitude_m, apogee_altitude_m, eccentricity,
    inclination_deg). Burn times are hardware and do not move during a sweep, so only the lift-off acceleration
    changes with payload.
    """
    m = dict(spec.mission)
    m.update(orbit or {})
    glom = fv.glom(payload_kg)
    mp_tot = sum(fv.m_loaded_kg) or 1.0
    ascent = dict(t_ascent_s=m.get("ascent_time_override_s") or fv.ascent_time_s,
                  accel0_mps2=(fv.liftoff_thrust_N / glom) if glom > 0 else G0,
                  isp_s=sum(p * i for p, i in zip(fv.m_loaded_kg, fv.isp_s)) / mp_tot)
    return dvmod.build_budget(EARTH_MODELS[spec.earth_model], m, ascent).total_mps


# --------------------------------------------------------------------------- the capability root-find
class NoCapability(Exception):
    """The vehicle cannot reach the orbit even with no payload at all."""


def payload_capability_kg(spec, fv: FrozenVehicle, orbit: dict | None = None, tol_kg: float = 0.5,
                          max_iter: int = 80) -> float:
    """Payload this frozen vehicle delivers to `orbit`, in kg. Raises NoCapability when even zero payload falls
    short of the requirement.

    `margin(m) = achieved(m) - required(m)` falls monotonically in m, so a sign change between zero payload and an
    upper bracket is a unique root; bisection converges on it without derivatives and without ever reporting an
    extrapolated or negative payload.
    """
    orbit = orbit or {}

    def margin(m_pl):
        return fv.delta_v(m_pl) - required_dv_mps(spec, fv, orbit, m_pl)

    lo = 0.0
    short = margin(lo)
    if short <= 0.0:
        raise NoCapability(f"cannot reach this orbit: {-short:,.0f} m/s short even with no payload")
    hi = max(4.0 * (fv.reference_payload_kg or 1000.0), 1000.0)
    while margin(hi) > 0.0:
        hi *= 2.0
        if hi > 1e9:
            raise NoCapability("could not bracket the payload capability (check the frozen stage masses)")
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        if margin(mid) > 0.0:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol_kg:
            break
    return 0.5 * (lo + hi)


def _capability_or_none(spec, fv, orbit):
    try:
        return payload_capability_kg(spec, fv, orbit), ""
    except (NoCapability, ValueError) as ex:
        return None, str(ex)


# --------------------------------------------------------------------------- sweeps
def payload_vs_altitude(spec, fv: FrozenVehicle, altitudes_km=None, inclinations_deg=None,
                        orbit_type: str = "LEO") -> dict:
    """Payload against circular-orbit altitude, one curve per inclination (book Figs. 3.27-3.29).

    Returns {'orbit_type', 'design': {'altitude_km', 'payload_kg'},
             'curves': [{'inclination_deg', 'points': [{'altitude_km', 'payload_kg', 'note'}], 'note'}]}.
    A point the vehicle cannot reach is None - never a negative or extrapolated payload.
    """
    lat = abs(spec.mission["site_latitude_deg"])
    h0 = spec.mission["perigee_altitude_m"] / 1e3
    if altitudes_km is None:
        lo, hi = max(180.0, 0.45 * h0), min(MAX_SWEEP_ALTITUDE_KM, max(1.8 * h0, 500.0))
        altitudes_km = [lo + (hi - lo) * k / 6.0 for k in range(7)]
    altitudes_km = [h for h in altitudes_km if h <= MAX_SWEEP_ALTITUDE_KM]
    if inclinations_deg is None:
        cand = [spec.mission["inclination_deg"], max(lat, 51.6), max(lat, 70.0), 97.5]
        inclinations_deg = sorted({round(i, 2) for i in cand if i >= lat - 1e-9})[:4]
    out = {"orbit_type": orbit_type, "curves": [],
           "design": {"altitude_km": h0, "payload_kg": fv.reference_payload_kg,
                      "inclination_deg": spec.mission["inclination_deg"]}}
    for inc in inclinations_deg:
        pts, note = [], ""
        if orbit_type != "SSO" and inc < lat - 1e-9:
            note = (f"inclination {inc:.1f} deg is below the launch-site latitude {lat:.1f} deg: a direct ascent "
                    "cannot reach it, and the dog-leg or plane change that would is not modelled")
            pts = [{"altitude_km": h, "payload_kg": None, "note": note} for h in altitudes_km]
        else:
            for h in altitudes_km:
                pl, n = _capability_or_none(spec, fv, {
                    "orbit_type": orbit_type, "perigee_altitude_m": h * 1e3, "apogee_altitude_m": None,
                    "eccentricity": None, "inclination_deg": inc})
                pts.append({"altitude_km": h, "payload_kg": pl, "note": n})
        out["curves"].append({"inclination_deg": inc, "points": pts, "note": note})
    return out


def payload_vs_inclination(spec, fv: FrozenVehicle, altitude_km: float | None = None,
                           inclinations_deg=None, orbit_type: str = "LEO") -> dict:
    """Payload against inclination at one altitude: the cost of the plane the customer wants."""
    lat = abs(spec.mission["site_latitude_deg"])
    h = altitude_km if altitude_km is not None else spec.mission["perigee_altitude_m"] / 1e3
    if inclinations_deg is None:
        top = 100.0
        # Start BELOW the site latitude. A direct ascent cannot reach an inclination under the latitude, so
        # those points come back empty by design - but sweeping into that band puts the unreachable region on
        # the axis where it can be shaded and labelled, instead of leaving the design point jammed against the
        # left edge of the plot with no indication that anything lies beyond it.
        low = max(0.0, lat - max(5.0, 0.15 * (top - lat)))
        inclinations_deg = ([low + (lat - low) * k / 2.0 for k in range(2)] if low < lat else []) + \
                           [lat + (top - lat) * k / 8.0 for k in range(9)]
    pts = []
    for inc in inclinations_deg:
        if inc < lat - 1e-9:
            pts.append({"inclination_deg": inc, "payload_kg": None,
                        "note": f"below the launch-site latitude ({lat:.1f} deg); plane change not modelled"})
            continue
        pl, n = _capability_or_none(spec, fv, {
            "orbit_type": orbit_type, "perigee_altitude_m": h * 1e3, "apogee_altitude_m": None,
            "eccentricity": None, "inclination_deg": inc})
        pts.append({"inclination_deg": inc, "payload_kg": pl, "note": n})
    return {"altitude_km": h, "orbit_type": orbit_type, "points": pts,
            "site_latitude_deg": lat,
            "design": {"inclination_deg": spec.mission["inclination_deg"],
                       "payload_kg": fv.reference_payload_kg}}


def payload_vs_transfer_orbit(spec, fv: FrozenVehicle, apogee_km: float = 35786.0,
                              perigee_altitudes_km=(185.0, 250.0, 300.0), inclination_deg=None) -> dict:
    """Payload to an elliptical transfer orbit (GTO), swept over the perigee altitude."""
    inc = inclination_deg if inclination_deg is not None else spec.mission["inclination_deg"]
    rows = []
    for hp in perigee_altitudes_km:
        pl, n = _capability_or_none(spec, fv, {
            "orbit_type": "GTO", "perigee_altitude_m": hp * 1e3, "apogee_altitude_m": apogee_km * 1e3,
            "eccentricity": None, "inclination_deg": inc})
        rows.append({"perigee_km": hp, "payload_kg": pl, "note": n})
    return {"apogee_km": apogee_km, "inclination_deg": inc, "rows": rows}


def standard_curves(res, with_gto: bool = True) -> dict:
    """The sweep set the report prints, from a converged result: altitude, inclination and (optionally) GTO.

    The design point is recomputed rather than assumed: `design_point_kg` is the capability at the design orbit,
    and it must come back as the design payload. That is the check that this module and the sizing loop agree.
    """
    fv = freeze(res)
    spec = res.spec
    curves = {"vs_altitude": payload_vs_altitude(spec, fv),
              "vs_inclination": payload_vs_inclination(spec, fv),
              "vehicle": fv.name, "reference_payload_kg": fv.reference_payload_kg}
    pl, note = _capability_or_none(spec, fv, {})
    curves["design_point_kg"] = pl
    curves["design_point_note"] = note
    curves["design_point_error_kg"] = None if pl is None else pl - fv.reference_payload_kg
    if with_gto and spec.mission["orbit_type"] in ("LEO", "SSO", "GTO"):
        try:
            curves["gto"] = payload_vs_transfer_orbit(spec, fv)
        except (ValueError, KeyError):
            curves["gto"] = None
    return curves
