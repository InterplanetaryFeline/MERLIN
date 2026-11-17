"""Strap-on boosters: parallel ("zeroth-stage") burn analysis.

Verified book method (Section 5.11 "Parallel Burns and Staging", printed pp. 305-308):
  Eq. 5:65  T_tot = v_e0 mdot_0 + v_e1 mdot_1 = v_e0ave (mdot_0 + mdot_1)
  Eq. 5:66  v_e0ave = (v_e0 mdot_0 + v_e1 mdot_1)/(mdot_0 + mdot_1)        (mass-averaged exhaust speed)
  Fig. 5.21 (p.308) phase structure: (1) core + strap-ons burning together, (2) strap-ons jettisoned and the
  core continues, (3) upper stage. The book also uses the effective Isp = 1/3 Isp_SL + 2/3 Isp_vac for BOTH the
  core and the strap-ons when forming the mass-averaged value (Shuttle exercise, pp. 323-324).

This module turns that into a phase sequence with constant mass flow in each phase. Supported:
  * ground-lit boosters (ignited at lift-off) and, optionally, a second group lit when the first group burns out
    (e.g. Delta II 7920: 6 ground-lit + 3 air-lit GEM-40s),
  * jettison of each group's inert mass at its burnout,
  * the core engine running continuously at constant mass flow through all phases.
NOT modelled: propellant crossfeed (book Sec. 5.11.3), throttling profiles, booster ignition at an arbitrary
time other than the previous group's burnout, boosters attached to a stage other than the one that is burning.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from .units import G0


class BoosterError(ValueError):
    """A booster configuration the parallel-burn model cannot fly.

    `field` and `options` are optional and are propagated by `convergence.size_vehicle` to the GUI, which
    turns them into "go to this input" and one-click fixes. They are worth filling in wherever the way out
    is a number this module can actually compute, rather than advice the user has to translate.
    """

    def __init__(self, message, field=None, options=None):
        super().__init__(message)
        self.message = message
        self.field = field
        self.options = options


@dataclass
class Phase:
    name: str
    duration_s: float
    mdot_total_kgs: float
    isp_eff_s: float
    thrust_eff_N: float
    m_start_kg: float
    m_end_kg: float
    dv_mps: float
    note: str = ""


@dataclass
class BoosterGroup:
    """One ignition group of identical boosters (derived values, not raw inputs)."""
    label: str
    n: int
    mdot_each_kgs: float
    isp_eff_s: float
    m_prop_mission_each_kg: float
    m_inert_each_kg: float          # jettisoned at burnout (dry + residual)
    burn_time_s: float
    thrust_ref_each_N: float = 0.0  # at the reference condition used for T/W (sea level for ground-lit)

    @property
    def m_loaded_each_kg(self) -> float:
        return self.m_prop_mission_each_kg + self.m_inert_each_kg

    @property
    def m_total_kg(self) -> float:
        return self.n * self.m_loaded_each_kg


def mass_averaged_isp(items: list) -> float:
    """Eq. 5:66 expressed with specific impulses: Isp_ave = sum(mdot_i Isp_i)/sum(mdot_i)."""
    num = sum(m * i for m, i in items)
    den = sum(m for m, _ in items)
    if den <= 0:
        raise BoosterError("total mass flow must be positive")
    return num / den


def phase_sequence(m_start_kg: float, mdot_core_kgs: float, isp_core_eff_s: float, m_prop_core_mission_kg: float,
                   groups: list) -> list:
    """Build the phases of a parallel burn and return them with delta-v filled in.

    groups must be ordered by ignition: groups[0] is ground-lit; groups[k>0] ignites when groups[k-1] burns out.
    The core burns continuously at mdot_core until its mission propellant is used up; it must outlast the boosters.
    """
    if mdot_core_kgs <= 0:
        raise BoosterError("core mass flow must be positive")
    phases = []
    m = m_start_kg
    prop_left = m_prop_core_mission_kg
    for k, g in enumerate(groups):
        if g.n <= 0 or g.burn_time_s <= 0:
            raise BoosterError(f"booster group '{g.label}': n and burn time must be positive")
        core_used = mdot_core_kgs * g.burn_time_s
        if core_used >= prop_left:
            # The core burns alongside the boosters, so a booster that burns for longer than the core's own
            # propellant lasts is not a flyable configuration. The burn time at which the two exactly meet
            # is computable here, so it is offered as a value rather than left as advice: everything else
            # the user could change (core propellant, throttle) is solved by the loop, not set directly.
            t_max = prop_left / mdot_core_kgs if mdot_core_kgs > 0 else 0.0
            # The margin is 10 % because 10 % is what converges. Shortening the burn changes the vehicle,
            # which changes the core's mass flow, which moves this limit - it is a fixed point, not a
            # one-shot calculation. Measured on the shipped default with an over-long booster burn: a 2 %
            # margin never settles and the user clicks forever, 10 % settles in three clicks, 20 % in two
            # at the cost of more performance given away. An offered fix that loops is worse than none,
            # because it looks like progress.
            m_boost = g.n * getattr(g, "m_prop_mission_each_kg", 0.0)
            # WHICH remedy to lead with. Shortening the burn is the right lever when the boosters are about
            # the size of the core and simply burn a little too long. It is the wrong one when they dwarf
            # it: at fixed propellant, a shorter burn means a higher mass flow and more thrust, the core
            # throttles back, and the limit moves again - that is the oscillation. Carrying less propellant
            # per booster is a different lever, and the one that actually shrinks the boosters.
            #
            # The trigger is not "boosters heavier than the core is bad" - Ariane 5's EAPs carry far more
            # than its core and size perfectly well, and never reach this line. It is: GIVEN that this
            # configuration has already failed, which of the two levers is worth offering first.
            oversized = m_boost > prop_left
            m_each_fit = prop_left / g.n if g.n else 0.0
            shrink = {"label": f"Carry {m_each_fit:,.0f} kg per booster instead of "
                               f"{getattr(g, 'm_prop_mission_each_kg', 0.0):,.0f} kg",
                      "path": "boosters.propellant_mass_each_kg", "value": round(m_each_fit, 1),
                      "note": "brings the boosters' total propellant down to what the core itself carries. "
                              "At the same burn time that lowers their thrust in proportion, which is what "
                              "shrinking a booster means - it is a starting point, not an optimum"}
            raise BoosterError(
                f"the core stage runs out of propellant {core_used - prop_left:.0f} kg before booster group "
                f"'{g.label}' burns out ({g.burn_time_s:.0f} s): throttle the core, shorten the booster burn, "
                "or add core propellant. If shortening the burn keeps bringing you back here, the boosters "
                f"are simply too large for this core - they carry {m_boost:,.0f} kg against the core's "
                f"{prop_left:,.0f} kg - and the propellant load per booster is the field to change",
                field=("boosters.propellant_mass_each_kg" if oversized else "boosters.burn_time_s"),
                options=([shrink] if oversized else []) + [
                    {"label": f"Shorten the booster burn to {0.90 * t_max:.0f} s",
                     "path": "boosters.burn_time_s", "value": round(0.90 * t_max, 1),
                     "note": f"the core has {prop_left:,.0f} kg left and burns {mdot_core_kgs:.1f} kg/s "
                             f"alongside the boosters, so it lasts {t_max:.0f} s. 10 % is left in hand "
                             "because shortening the burn moves this limit, and a thinner margin oscillates"},
                ] + ([] if oversized else [shrink]) + [
                    {"label": "Or use fewer boosters", "path": "boosters.n_total",
                     "note": "fewer boosters leave more of the lift-off thrust to the core, so the core "
                             "throttles up and gets through its propellant faster"},
                ])
        mdot_tot = mdot_core_kgs + g.n * g.mdot_each_kgs
        isp = mass_averaged_isp([(mdot_core_kgs, isp_core_eff_s), (g.n * g.mdot_each_kgs, g.isp_eff_s)])
        m_end = m - (core_used + g.n * g.m_prop_mission_each_kg)
        if m_end <= 0:
            raise BoosterError("non-physical mass during parallel burn")
        phases.append(Phase(f"Parallel burn: core + {g.n} x {g.label}", g.burn_time_s, mdot_tot, isp,
                            mdot_tot * G0 * isp, m, m_end, G0 * isp * math.log(m / m_end),
                            "Eq. 5:66 mass-averaged Isp"))
        prop_left -= core_used
        m = m_end - g.n * g.m_inert_each_kg
        if m <= 0:
            raise BoosterError("non-physical mass after booster jettison")
        phases.append(Phase(f"Jettison {g.n} x {g.label}", 0.0, 0.0, 0.0, 0.0, m_end, m, 0.0,
                            f"-{g.n * g.m_inert_each_kg:,.0f} kg inert, no delta-v"))
    m_end = m - prop_left
    if m_end <= 0:
        raise BoosterError("non-physical mass at core burnout")
    phases.append(Phase("Core stage alone", prop_left / mdot_core_kgs, mdot_core_kgs, isp_core_eff_s,
                        mdot_core_kgs * G0 * isp_core_eff_s, m, m_end, G0 * isp_core_eff_s * math.log(m / m_end),
                        "series portion after strap-on separation (Fig. 5.21)"))
    return phases


def total_dv(phases: list) -> float:
    return sum(p.dv_mps for p in phases)


def solve_core_propellant(dv_target_mps: float, u_above_kg: float, dry_core_kg: float, f_unburned: float,
                          mdot_core_kgs: float, isp_core_eff_s: float, groups: list,
                          m_startup_kg: float = 0.0, tol: float = 1e-10, max_iter: int = 200) -> tuple:
    """Find the core mission propellant that makes the whole parallel+series sequence deliver dv_target.

    Mass at lift-off: M0 = u_above + dry_core + m_p(1+f_unburned) + m_startup + sum(group loaded masses).
    The delta-v burn starts after start-up propellant is consumed. Returns (m_p, phases).
    Monotonic in m_p, so a bracketed bisection is used (robust, no derivative needed).
    """
    boost_mass = sum(g.m_total_kg for g in groups)

    def dv_of(mp):
        m_burn_start = u_above_kg + dry_core_kg + mp * (1.0 + f_unburned) + boost_mass
        return total_dv(phase_sequence(m_burn_start, mdot_core_kgs, isp_core_eff_s, mp, groups)), m_burn_start

    lo, hi = 1.0, max(10.0, (u_above_kg + dry_core_kg + boost_mass) * 50.0)
    try:
        dv_hi, _ = dv_of(hi)
    except BoosterError as ex:
        raise BoosterError(f"cannot bracket the core propellant solution: {ex}") from ex
    if dv_hi < dv_target_mps:
        raise BoosterError(f"even {hi:,.0f} kg of core propellant delivers only {dv_hi:,.0f} m/s of the required "
                           f"{dv_target_mps:,.0f} m/s: the stage is infeasible with these masses")
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        try:
            dv_mid, _ = dv_of(mid)
        except BoosterError:
            lo = mid           # too little core propellant: core cannot outlast the boosters
            continue
        if dv_mid < dv_target_mps:
            lo = mid
        else:
            hi = mid
        if (hi - lo) <= tol * max(1.0, hi):
            break
    mp = 0.5 * (lo + hi)
    _, m_burn_start = dv_of(mp)
    return mp, phase_sequence(m_burn_start, mdot_core_kgs, isp_core_eff_s, mp, groups)
