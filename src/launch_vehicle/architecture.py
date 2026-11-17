"""Pinned-hardware architecture trades: keep a design's stages, change the strap-ons, ask what it lifts.

Why this is a separate module from `performance`. A performance curve holds *everything* fixed and moves only
the payload, so the parallel burn's contribution can be carried through as the one number the reference design
produced - which is what `performance.FrozenVehicle.booster_dv_mps` does, and says so in its docstring. Change
the number of strap-ons and that number is no longer a property of the vehicle: the parallel phase has a
different total mass flow, a different mass-averaged Isp, a different burnout mass and a different jettison
mass. On the shipped Ariane 64 design the stored term is **negative** (about -2,900 m/s), because it is the
difference between the serial rocket equation applied to the core stage and the phase model's answer for the
same stage - a bookkeeping correction, not a contribution. Holding a correction of that size constant while
removing half the boosters would produce a confident, meaningless number.

So this module re-solves the parallel phase. `PinnedVehicle` is a `FrozenVehicle` that also carries the strap-on
*unit* design - propellant, inert mass, mass flow, effective Isp, burn time - and the core's own mass flow and
sea-level thrust. `with_boosters(n)` returns the same hardware with a different count, with the attach stage's
delta-v coming from `boosters.phase_sequence` rather than from the stored correction. Everything in
`performance` that goes through `delta_v()` and `glom()` - the payload root-find, the altitude and inclination
sweeps - then works on it unchanged.

Method register M58. The two directions a user wants:

  Fixed core, different boosters. `pin(res)` then `payload_for_architecture(pv, n_total=k)`. The stages keep the
  reference design's propellant loads, dry masses and Isp; the strap-on unit keeps its design; only the count and
  the payload move. The payload is the root of achieved(m) - required(m) = 0, found by the same bisection
  `performance.payload_capability_kg` uses, and the required side moves with the count too, because lift-off
  acceleration enters the loss model.

  Fixed boosters, different core. That is the sizing loop's own job: override `boosters.*` in the spec and run
  `convergence.size_vehicle`, which sizes a core to carry them. `core_for_boosters` is a thin wrapper that does
  exactly that, so both directions are reachable from one place.

What this is NOT. The stages are not re-optimised and not re-sized: a pinned core flies with the tankage,
engine count, avionics and fairing it was sized for, so the answer is *this* core's performance under a
different booster architecture, not the vehicle a designer would draw for it. Lift-off thrust-to-weight is
reported, never corrected for: removing boosters can leave a stack that cannot leave the pad, and the result
says so rather than quietly returning a payload. The delta-v requirement keeps the loss model's own limits.
"""
from __future__ import annotations
import copy
import math
from dataclasses import dataclass, field

from . import boosters as bst
from . import performance as pf
from .units import G0


class ArchitectureError(ValueError):
    """The pinned hardware cannot be flown in the requested architecture."""


# --------------------------------------------------------------------------- the pinned vehicle
@dataclass
class PinnedVehicle(pf.FrozenVehicle):
    """A frozen vehicle whose strap-on count is free, with the parallel burn re-solved for each count."""
    n_boosters: int = 0
    n_ground_lit: int = 0
    booster_label: str = "strap-on"
    booster_prop_each_kg: float = 0.0        # mission propellant per unit (what the phase model burns)
    booster_inert_each_kg: float = 0.0       # jettisoned at burnout
    booster_mdot_each_kgs: float = 0.0
    booster_isp_eff_s: float = 0.0
    booster_burn_time_s: float = 0.0
    booster_thrust_sl_each_N: float = 0.0
    booster_thrust_vac_each_N: float = 0.0
    core_mdot_kgs: list = field(default_factory=list)      # per stage, from the reference design
    core_thrust_sl_N: float = 0.0            # the core's own sea-level thrust, boosters excluded
    reference_n_boosters: int = 0
    reference_n_ground_lit: int = 0
    reference_glom_kg: float = 0.0
    reference_liftoff_tw: float = 0.0

    # -- the strap-on unit, as the phase model wants it
    @property
    def booster_loaded_each_kg(self) -> float:
        return self.booster_prop_each_kg + self.booster_inert_each_kg

    def booster_groups(self) -> list:
        """Ignition groups for the current count: ground-lit first, then air-lit, as `phase_sequence` requires."""
        out = []
        n_gl = min(self.n_ground_lit, self.n_boosters)
        n_air = self.n_boosters - n_gl
        ref_sl = self.booster_thrust_sl_each_N or self.booster_thrust_vac_each_N
        if n_gl > 0:
            out.append(bst.BoosterGroup(f"{self.booster_label} (ground-lit)", n_gl, self.booster_mdot_each_kgs,
                                        self.booster_isp_eff_s, self.booster_prop_each_kg,
                                        self.booster_inert_each_kg, self.booster_burn_time_s, ref_sl))
        if n_air > 0:
            out.append(bst.BoosterGroup(f"{self.booster_label} (air-lit)", n_air, self.booster_mdot_each_kgs,
                                        self.booster_isp_eff_s, self.booster_prop_each_kg,
                                        self.booster_inert_each_kg, self.booster_burn_time_s,
                                        self.booster_thrust_vac_each_N or ref_sl))
        return out

    def with_boosters(self, n_total: int, n_ground_lit: int | None = None) -> "PinnedVehicle":
        """The same hardware with a different strap-on count. Lift-off thrust and carried mass follow."""
        if n_total < 0:
            raise ArchitectureError("the number of boosters cannot be negative")
        pv = copy.copy(self)
        pv.n_boosters = int(n_total)
        if n_ground_lit is None:
            # A reference design that lit every booster on the ground gets every booster lit on the ground at
            # any count: carrying the reference's ground-lit COUNT upward would invent an air-lit group the
            # design never had, and an air-lit group makes the core burn alongside boosters for a second
            # interval, which is a different vehicle and usually not a flyable one. A design that really does
            # stage its ignition keeps its ground-lit count, capped at the total.
            if self.reference_n_boosters == self.reference_n_ground_lit:
                pv.n_ground_lit = pv.n_boosters
            else:
                pv.n_ground_lit = min(self.reference_n_ground_lit, pv.n_boosters) or pv.n_boosters
        else:
            if not 0 <= n_ground_lit <= n_total:
                raise ArchitectureError(f"ground-lit count {n_ground_lit} must be between 0 and {n_total}")
            if n_total > 0 and n_ground_lit == 0:
                raise ArchitectureError("with no ground-lit boosters there is nothing to ignite the air-lit group")
            pv.n_ground_lit = int(n_ground_lit)
        pv.booster_mass_kg = pv.n_boosters * pv.booster_loaded_each_kg
        pv.liftoff_thrust_N = pv.core_thrust_sl_N + pv.n_ground_lit * pv.booster_thrust_sl_each_N
        pv.booster_dv_mps = 0.0        # re-solved per payload; the stored correction does not apply here
        return pv

    # -- mass bookkeeping, the same as the sizing loop's
    def _carried_kg(self, payload_kg: float, j: int) -> float:
        N = self.n_stages
        carried = payload_kg + self.paf_kg(payload_kg)
        if (j + 1) < self.fairing_jettison_stage:
            carried += self.fairing_kg
        carried += sum(self.m_dry_kg[k] + self.m_loaded_kg[k] for k in range(j + 1, N))
        return carried

    def parallel_phases(self, payload_kg: float) -> list:
        """The phases of the attach stage's burn with the current booster count (`boosters.phase_sequence`)."""
        j = self.booster_attach_stage - 1
        carried = self._carried_kg(payload_kg, j)
        m_ign = carried + self.m_dry_kg[j] + self.m_loaded_kg[j] + self.booster_mass_kg
        m_start = m_ign - self.m_startup_kg[j]
        mdot = self.core_mdot_kgs[j]
        if mdot <= 0:
            raise ArchitectureError(f"stage {j + 1} has no mass flow recorded; cannot re-solve the parallel burn")
        m_prop_mission = self.m_loaded_kg[j] - self.m_startup_kg[j] - self.m_unusable_kg[j]
        return bst.phase_sequence(m_start, mdot, self.isp_s[j], m_prop_mission, self.booster_groups())

    def stage_delta_v(self, payload_kg: float) -> list:
        """Per-stage delta-v, with the attach stage's value taken from the phase model when boosters are fitted."""
        per = super().stage_delta_v(payload_kg)
        if self.n_boosters > 0 and self.booster_attach_stage:
            per[self.booster_attach_stage - 1] = bst.total_dv(self.parallel_phases(payload_kg))
        return per

    def delta_v(self, payload_kg: float) -> float:
        """Total delta-v achieved. Unlike `FrozenVehicle.delta_v` the parallel phases ARE re-solved, so this is
        valid at booster counts other than the reference design's."""
        return sum(self.stage_delta_v(payload_kg))

    def liftoff_tw(self, payload_kg: float) -> float:
        g = self.glom(payload_kg)
        return (self.liftoff_thrust_N / (g * G0)) if g > 0 else 0.0


def pin(res) -> PinnedVehicle:
    """Pin a converged design's hardware so its strap-on count can be varied.

    Raises ArchitectureError when the design has no strap-ons: there is no architecture to trade.
    """
    fv = pf.freeze(res)
    b = getattr(res, "boosters", None)
    if b is None:
        raise ArchitectureError(f"'{fv.name}' has no strap-on boosters, so there is no booster count to vary. "
                                "Use performance.payload_vs_altitude for a serial vehicle's capability.")
    mdots = [getattr(s, "mdot_kgs", 0.0) or 0.0 for s in res.stages]
    sl_each = b.thrust_sl_each_N or b.thrust_vac_each_N
    pv = PinnedVehicle(
        name=fv.name, isp_s=fv.isp_s, m_dry_kg=fv.m_dry_kg, m_loaded_kg=fv.m_loaded_kg,
        m_startup_kg=fv.m_startup_kg, m_unusable_kg=fv.m_unusable_kg, fairing_kg=fv.fairing_kg,
        fairing_jettison_stage=fv.fairing_jettison_stage, booster_mass_kg=fv.booster_mass_kg,
        booster_attach_stage=fv.booster_attach_stage, booster_dv_mps=0.0,
        liftoff_thrust_N=fv.liftoff_thrust_N, burn_times_s=fv.burn_times_s,
        staging_delay_s=fv.staging_delay_s, ascent_time_s=fv.ascent_time_s,
        reference_payload_kg=fv.reference_payload_kg, reference_paf_kg=fv.reference_paf_kg,
        reference_dv_mps=fv.reference_dv_mps, spec=fv.spec,
        n_boosters=b.n_total, n_ground_lit=b.n_ground_lit, booster_label=b.name,
        booster_prop_each_kg=b.m_prop_each_kg, booster_inert_each_kg=b.m_inert_each_kg,
        booster_mdot_each_kgs=b.mdot_each_kgs, booster_isp_eff_s=b.isp_eff_s,
        booster_burn_time_s=b.burn_time_s, booster_thrust_sl_each_N=sl_each,
        booster_thrust_vac_each_N=b.thrust_vac_each_N,
        core_mdot_kgs=mdots,
        # the core's own sea-level thrust by subtraction, so it is consistent with whatever the sizing loop
        # counted into lift-off thrust rather than with an assumption made here
        core_thrust_sl_N=fv.liftoff_thrust_N - b.n_ground_lit * sl_each,
        reference_n_boosters=b.n_total, reference_n_ground_lit=b.n_ground_lit,
        reference_glom_kg=getattr(res, "glom_kg", 0.0),
        reference_liftoff_tw=getattr(res, "liftoff_tw", 0.0))
    return pv


# --------------------------------------------------------------------------- the trade
@dataclass
class ArchitectureResult:
    """What a pinned vehicle delivers in one booster architecture."""
    name: str
    n_boosters: int
    n_ground_lit: int
    payload_kg: float | None
    glom_kg: float | None
    liftoff_tw: float | None
    dv_achieved_mps: float | None
    dv_required_mps: float | None
    stage_dv_mps: list = field(default_factory=list)
    booster_mass_kg: float = 0.0
    liftoff_thrust_N: float = 0.0
    flyable: bool = True
    reason: str = ""
    is_reference: bool = False
    # The payload at which delta-v closes, kept ONLY for a configuration that then fails on something else -
    # lift-off thrust-to-weight, so far. It is a diagnostic, not a capability: `payload_kg` stays None for an
    # unflyable configuration so that nothing which reads that field can mistake it for one.
    dv_limited_payload_kg: float | None = None

    @property
    def payload_fraction(self) -> float | None:
        if self.payload_kg is None or not self.glom_kg:
            return None
        return self.payload_kg / self.glom_kg


def payload_for_architecture(pv: PinnedVehicle, n_total: int | None = None, n_ground_lit: int | None = None,
                             orbit: dict | None = None, tol_kg: float = 0.5) -> ArchitectureResult:
    """Payload the pinned stages deliver with `n_total` strap-ons fitted, to `orbit` (default: as designed).

    The parallel phase is re-solved for the new count, so this is valid away from the reference architecture.
    A count that cannot lift off, or whose boosters outlast the core's propellant, comes back with
    `flyable=False` and the reason, never as a number.
    """
    n_total = pv.n_boosters if n_total is None else int(n_total)
    try:
        trial = pv.with_boosters(n_total, n_ground_lit)
    except ArchitectureError as ex:
        return ArchitectureResult(pv.name, n_total, n_ground_lit or 0, None, None, None, None, None,
                                  flyable=False, reason=str(ex))
    out = ArchitectureResult(
        name=pv.name, n_boosters=trial.n_boosters, n_ground_lit=trial.n_ground_lit,
        payload_kg=None, glom_kg=None, liftoff_tw=None, dv_achieved_mps=None, dv_required_mps=None,
        booster_mass_kg=trial.booster_mass_kg, liftoff_thrust_N=trial.liftoff_thrust_N,
        is_reference=(trial.n_boosters == pv.reference_n_boosters
                      and trial.n_ground_lit == pv.reference_n_ground_lit))
    try:
        m_pl = pf.payload_capability_kg(trial.spec, trial, orbit or {}, tol_kg=tol_kg)
    except (pf.NoCapability, bst.BoosterError, ArchitectureError, ValueError) as ex:
        out.flyable = False
        out.reason = str(ex)
        return out
    out.payload_kg = m_pl
    out.glom_kg = trial.glom(m_pl)
    out.liftoff_tw = trial.liftoff_tw(m_pl)
    out.stage_dv_mps = trial.stage_delta_v(m_pl)
    out.dv_achieved_mps = sum(out.stage_dv_mps)
    out.dv_required_mps = pf.required_dv_mps(trial.spec, trial, orbit or {}, m_pl)
    if out.liftoff_tw <= 1.0:
        # A stack that weighs more than it pushes does not leave the pad, so there is no capability to report:
        # the delta-v-feasible payload moves to its own field rather than staying under the name `payload_kg`,
        # where a caller that did not check `flyable` would read it as one.
        out.flyable = False
        out.reason = (f"lift-off thrust-to-weight {out.liftoff_tw:.2f} at the delta-v-feasible payload of "
                      f"{out.payload_kg:,.0f} kg: the stack cannot leave the pad. {trial.n_ground_lit} "
                      f"ground-lit booster(s) and the core give {out.liftoff_thrust_N / 1e3:,.0f} kN against "
                      f"{out.glom_kg * G0 / 1e3:,.0f} kN of weight")
        out.dv_limited_payload_kg = out.payload_kg
        out.payload_kg = None
    return out


def booster_count_sweep(pv: PinnedVehicle, counts=None, orbit: dict | None = None) -> list:
    """`payload_for_architecture` over a range of counts. Default: 0 up to twice the reference count."""
    if counts is None:
        top = max(2 * pv.reference_n_boosters, pv.reference_n_boosters + 2)
        counts = list(range(0, top + 1))
    return [payload_for_architecture(pv, n, orbit=orbit) for n in counts]


def core_for_boosters(spec, n_total: int, n_ground_lit: int | None = None, overrides: dict | None = None):
    """The other direction: hold the strap-on design and let the sizing loop size a core for it.

    This is `convergence.size_vehicle` with the booster count overridden - the core, its tanks and its engine
    count are all re-sized, which is what "design a core around a fixed booster" means. Returns a VehicleResult.
    """
    from .config_io import deep_set
    from .convergence import size_vehicle
    s = copy.deepcopy(spec)
    s.boosters.n_total = int(n_total)
    s.boosters.n_ground_lit = int(n_total if n_ground_lit is None else n_ground_lit)
    if s.boosters.n_ground_lit > s.boosters.n_total:
        raise ArchitectureError("ground-lit count cannot exceed the total")
    for k, v in (overrides or {}).items():
        deep_set(s.__dict__, k, v)
    return size_vehicle(s, keep_history=False)


# --------------------------------------------------------------------------- reporting
def sweep_table(results: list, reference_payload_kg: float | None = None) -> list:
    """Rows for a booster-count sweep: (label, payload, GLOM, T/W, payload change vs the reference)."""
    ref = None
    for r in results:
        if r.is_reference and r.payload_kg is not None:
            ref = r.payload_kg
    if reference_payload_kg is not None:
        ref = reference_payload_kg
    rows = []
    for r in results:
        if not r.flyable or r.payload_kg is None:
            rows.append((f"{r.n_boosters} boosters", None, None, None, None, r.reason))
            continue
        d = (r.payload_kg - ref) if ref else None
        rows.append((f"{r.n_boosters} boosters", r.payload_kg, r.glom_kg, r.liftoff_tw, d, ""))
    return rows
