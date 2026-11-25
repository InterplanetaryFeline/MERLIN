"""3-DoF ascent trajectory: the book's Table 6.1 equations of motion, integrated (book Sec. 6.3-6.6).

`fly_design` flies a sized design to orbit with the solver in `ascent.py` (gravity turn, then linear tangent steering
to a level arrival, engine cutoff, coast and second burn, on a turning Earth). This module holds what that shares with
everything else: the vehicle as the integrator sees it, the result, the orbit check and the timeline. `integrate` and
`shoot_for_altitude` below are the book's pure gravity turn and its shooting method (Fig. 6.18), kept because the drag
validation and the tests fly published pitch programmes with them.

This is the module that stops the tool taking its losses on faith. Everywhere else, the delta-v requirement comes
from a published regression fitted to historical launches; here the vehicle is actually flown, and the gravity,
drag, propulsion and steering losses fall out of the integration as the book defines them (Eq. 6:58).

The equations (book Table 6.1, p.364), in the pitch plane, with lift and side thrust neglected because the
vehicle flies at essentially zero angle of attack (Sec. 6.3.3 assumptions):

    dv/dt     = (T - D)/m - g sin(gamma)                        Eq. 6:42
    dgamma/dt = -(g/v - v/(Rp + h)) cos(gamma)                   Eq. 6:43 / 6:58
    dh/dt     = v sin(gamma)
    dx/dt     = v cos(gamma) / (1 + h/Rp)                        downrange, Table 6.1
    m(t)      = m0 - mdot t
    T         = mdot ve + (Pe - Pinf) Ae                         Eq. 6:52
    D         = Cd Sref rho v^2 / 2                              Eq. 6:49
    g(h)      = g0 / (1 + h/Rp)^2                                Eq. 6:31

Guidance is the book's gravity turn (Sec. 6.4.7): the vehicle rises vertically, is given a pitch kick - a step
change in gamma - and then turns on its own, because dgamma/dt is zero only while gamma is exactly 90 deg. The
kick angle is found by the book's own method of "shooting" (Fig. 6.18): burnout altitude falls monotonically as
the kick grows, so a bisection converges on the altitude the mission wants. Nothing here is optimised; a gravity
turn is not the optimal ascent, it is the one the book describes and the one real vehicles approximate.

The loss decomposition is Eq. 6:58:

    dv = c ln(mu) - integral[2T sin^2((alpha+delta)/2)/m]dt - integral[D/m]dt - integral[g sin(gamma)]dt
         ideal        steering loss                            drag loss        gravity loss

to which this module adds the propulsion (back-pressure) loss separately, because it computes thrust from
Eq. 6:52 rather than assuming a constant effective exhaust speed: with the ideal taken at vacuum Isp, the
difference integral[Ae Pinf / m]dt is exactly the thrust the atmosphere steals. Those four losses plus the final
speed reconstruct the vacuum ideal delta-v to integration accuracy, which the result carries as a residual and
the tests pin.

What this is not: a 6-DoF simulation or a guidance design. There is no wind, no lift and no attitude dynamics, and
`integrate` itself is on a spherical, non-rotating Earth with no throttling.
"""
from __future__ import annotations
import math
import re
from dataclasses import dataclass, field, replace

from . import aerodynamics as aero
from .atmosphere import air, gravity_mps2, AirState, P0_PA
from .units import G0


class TrajectoryError(RuntimeError):
    """The ascent could not be integrated or the shooting did not converge."""


# --------------------------------------------------------------------------- the vehicle, as the integrator sees it
@dataclass
class Burn:
    """One powered or coasting segment of the ascent."""
    name: str
    duration_s: float
    thrust_vac_N: float = 0.0
    mdot_kgs: float = 0.0
    exit_area_m2: float = 0.0
    isp_vac_s: float = 0.0
    startup_kg: float = 0.0           # consumed at ignition with no delta-v credit (book Eq. 8:2)
    jettison_kg: float = 0.0          # mass dropped at the END of this segment
    jettison_note: str = ""
    powered: bool = True
    stoppable: bool = False           # can be shut down before it runs dry, and lit again (a liquid engine)
    throttle_min: float = 1.0         # the smallest fraction of full thrust it can run at


@dataclass
class AscentVehicle:
    """Everything the integrator needs: a mass to start from, a sequence of burns, and a frontal area."""
    name: str
    m0_kg: float
    burns: list
    reference_area_m2: float
    drag: aero.DragModel
    atmosphere: str = "book_exponential"
    r_planet_m: float = 6378e3
    g0: float = G0
    fairing_jettison_index: int | None = None     # burn index at whose START the fairing is dropped
    fairing_kg: float = 0.0
    drag_by_burn: list | None = None              # one DragModel per burn when the shape changes in flight
                                                  # (strap-ons and spent stages leaving); None = `drag` throughout

    def drag_for_burn(self, index: int):
        if self.drag_by_burn and index < len(self.drag_by_burn) and self.drag_by_burn[index] is not None:
            return self.drag_by_burn[index]
        return self.drag

    @property
    def total_powered_time_s(self):
        return sum(b.duration_s for b in self.burns if b.powered)


# --------------------------------------------------------------------------- guidance
@dataclass
class Guidance:
    """Ascent guidance: the book's gravity turn, with an optional terminal phase above the atmosphere.

    A pure gravity turn (Sec. 6.4.7) is free flight: thrust along the velocity vector, no steering loss, and the
    pitch rate entirely set by Eq. 6:43. It is the right model inside the atmosphere, where flying at any angle
    of attack costs air loads, and it is what the book integrates. It is not, on its own, enough to put a
    multistage vehicle in orbit: once the vehicle is level and still below orbital speed, g/v exceeds
    v/(Rp + h), so Eq. 6:43 keeps pitching it down and it flies into the ground. Real vehicles hand over to
    closed-loop guidance above the atmosphere - the book's Sec. 6.4.8 "Other Methods of Guidance", and its
    Shuttle example (Fig. 6.33) shows exactly this, the thrust no longer parallel to the velocity, "leading to a
    steering loss".

    `terminal_mode = "gamma_linear"` models that handover in the simplest honest way: above `terminal_start_h_m`
    the flight path angle is commanded to run linearly from wherever it is to `terminal_gamma_deg` at the end of
    the last burn. The thrust then sits at an angle alpha to the velocity vector, which the integrator solves for
    from the normal equation (book Eq. 6:41) and charges as a steering loss through Eq. 6:58 - so the cost of the
    manoeuvre is paid, not hidden. `alpha` is limited to `max_alpha_deg`; when the limit binds, the vehicle
    simply does not follow the commanded profile and the result says the angle-of-attack limit was reached.
    """
    vertical_rise_s: float = 10.0
    kick_deg: float = 1.0
    min_gamma_deg: float = -89.0         # stop only on a genuine dive; the ground is the real stopping condition
    terminal_mode: str = "gamma_linear"  # "none" (pure gravity turn) | "gamma_linear"
    terminal_start_h_m: float = 60000.0  # handover altitude: above the atmosphere, so no air-load penalty
    terminal_start_q_Pa: float = 1000.0  # or as soon as dynamic pressure falls this low, whichever comes first
    terminal_gamma_deg: float = 0.0      # commanded flight path angle at the end of the last powered burn
    max_alpha_deg: float = 15.0          # limit on the angle between thrust and velocity


# --------------------------------------------------------------------------- the integration result
@dataclass
class TrajectoryResult:
    vehicle_name: str
    converged: bool
    status: str
    t_s: list = field(default_factory=list)
    v_mps: list = field(default_factory=list)
    gamma_deg: list = field(default_factory=list)
    h_m: list = field(default_factory=list)
    x_m: list = field(default_factory=list)
    m_kg: list = field(default_factory=list)
    q_Pa: list = field(default_factory=list)
    mach: list = field(default_factory=list)
    accel_g: list = field(default_factory=list)
    drag_N: list = field(default_factory=list)
    thrust_N: list = field(default_factory=list)
    alpha_deg: list = field(default_factory=list)
    events: list = field(default_factory=list)
    # summary
    burnout_v_mps: float = 0.0
    burnout_h_m: float = 0.0
    burnout_gamma_deg: float = 0.0
    burnout_t_s: float = 0.0
    downrange_m: float = 0.0
    max_q_Pa: float = 0.0
    max_q_t_s: float = 0.0
    max_q_h_m: float = 0.0
    max_q_mach: float = 0.0
    max_accel_g: float = 0.0
    ideal_dv_mps: float = 0.0
    gravity_loss_mps: float = 0.0
    drag_loss_mps: float = 0.0
    steering_loss_mps: float = 0.0
    propulsion_loss_mps: float = 0.0
    closure_residual_mps: float = 0.0
    kick_deg: float = 0.0
    vertical_rise_s: float = 0.0
    peak_h_m: float = 0.0
    outcome: str = ""          # "flown" | "fell_back" | "nosed_over"
    max_alpha_deg: float = 0.0
    notes: list = field(default_factory=list)
    #: False when the ascent was never attempted because this model cannot represent the mission profile.
    #: Distinct from `converged`, which answers whether an attempt succeeded. A reader needs both: a failed
    #: attempt is a result about THIS vehicle, while an unattempted one is a statement about the model, and
    #: presenting the second as the first is what made the GTO check cases look broken rather than out of scope.
    attempted: bool = True
    #: the lift-off shape's Cd build-up against Mach number, when the geometry drag model flew it
    drag_table: dict | None = None
    #: the orbit the burnout state is on against the one asked for (see insertion_orbit), set by fly_design
    insertion: dict | None = None
    # ---- set by ascent.fly (a flight to orbit). `burnout_*`, the losses and the ideal above describe the ascent
    # proper, to the first cutoff; what follows describes the whole flight.
    profile: str = ""                  # direct | transfer | parking | solid
    profile_why: str = ""
    parking_altitude_m: float = 0.0    # altitude of the first insertion
    margin_mps: float = 0.0            # speed left in the tanks at the end (+), or missing (-)
    propellant_left_kg: float = 0.0
    second_burn_dv_mps: float = 0.0
    ideal_used_mps: float = 0.0        # ideal speed spent, every burn
    start_v_mps: float = 0.0           # speed at the start: zero on a pad, the carrier's in an air launch
    equivalent_loss_mps: float | None = None    # see equivalent_loss_mps(), against the budget's own losses
    budget_loss_mps: float = 0.0
    yaw_deg: float = 0.0               # constant out-of-plane thrust angle that cancels the site's crosswise speed
    final_state: dict | None = None    # the state after the last burn, with the inertial horizontal and vertical speed

    @property
    def total_loss_mps(self):
        return self.gravity_loss_mps + self.drag_loss_mps + self.steering_loss_mps + self.propulsion_loss_mps


# --------------------------------------------------------------------------- the integrator
def _steering_alpha(guidance, burn, t, t_total, v, gamma, h, m, thrust, g, r_planet, q_Pa=0.0):
    """The angle between thrust and velocity demanded by the terminal guidance, from book Eq. 6:41.

    Zero during the gravity turn, which is the whole point of a gravity turn. Above the handover altitude the
    flight path angle is commanded along a straight line to its terminal value, and the normal equation is solved
    for the alpha that produces that pitch rate:

        v dgamma/dt = T sin(alpha)/m - (g - v^2/(Rp+h)) cos(gamma)
    """
    if guidance.terminal_mode != "gamma_linear" or not burn.powered or thrust <= 0.0 or v < 50.0:
        return 0.0
    if h < guidance.terminal_start_h_m and q_Pa > guidance.terminal_start_q_Pa:
        return 0.0        # still in the air-load regime: fly the gravity turn, angle of attack zero
    remaining = max(t_total - t, 1e-3)
    gamma_cmd_rate = (math.radians(guidance.terminal_gamma_deg) - gamma) / remaining
    want = m * (v * gamma_cmd_rate + (g - v * v / (r_planet + h)) * math.cos(gamma))
    s_alpha = max(-1.0, min(1.0, want / thrust))
    alpha = math.asin(s_alpha)
    lim = math.radians(guidance.max_alpha_deg)
    return max(-lim, min(lim, alpha))


def _derivs(v, gamma, h, m, thrust_N, drag_N, g, r_planet, alpha=0.0):
    """Book Eqs. 6:40 and 6:41 (which reduce to 6:42 and 6:43 when alpha = 0), and the Table 6.1 kinematics."""
    dv = (thrust_N * math.cos(alpha) - drag_N) / m - g * math.sin(gamma)
    if v < 1e-6:                     # at rest the pitch-rate equation is singular; the vehicle is still vertical
        dgamma = 0.0
    else:
        dgamma = (thrust_N * math.sin(alpha) / m) / v - (g / v - v / (r_planet + h)) * math.cos(gamma)
    dh = v * math.sin(gamma)
    dx = v * math.cos(gamma) / (1.0 + h / r_planet)
    return dv, dgamma, dh, dx


def integrate(vehicle: AscentVehicle, guidance: Guidance, dt: float = 0.25,
              stop_altitude_m: float = 0.0, record_every: int = 4) -> TrajectoryResult:
    """Fly the vehicle. RK4 on (v, gamma, h, x) with mass and thrust held over each step.

    The book's own example uses Euler integration with a 1 s step and says plainly that "Euler integration is
    less accurate than higher-order methods such as the fourth-order Runge-Kutta" (p.374). RK4 at a quarter of a
    second is used here because the loss integrals are the output, and a first-order integrator puts a percent of
    error into them for nothing.
    """
    res = TrajectoryResult(vehicle_name=vehicle.name, converged=False, status="not run",
                           kick_deg=guidance.kick_deg, vertical_rise_s=guidance.vertical_rise_s)
    t, v, gamma, h, x = 0.0, 0.0, math.pi / 2.0, 0.0, 0.0
    m = vehicle.m0_kg
    kicked = False
    grav = drag_l = steer_l = prop_l = 0.0
    ideal = 0.0
    step = 0
    max_alpha_used = 0.0
    t_last_burn_end = sum(b.duration_s for b in vehicle.burns)

    # thrust, drag and angle of attack at the last state evaluated, so that every recorded point carries the
    # forces that produced it (the loads analysis of Chapter 9 needs the thrust and drag at max-q)
    last_forces = [0.0, 0.0, 0.0]            # thrust [N], drag [N], alpha [rad]

    def record(force=False):
        nonlocal step
        if force or step % record_every == 0:
            st = air(h, vehicle.atmosphere)
            q = st.dynamic_pressure_Pa(v)
            res.t_s.append(t); res.v_mps.append(v); res.gamma_deg.append(math.degrees(gamma))
            res.h_m.append(h); res.x_m.append(x); res.m_kg.append(m)
            res.q_Pa.append(q); res.mach.append(st.mach(v))
            res.thrust_N.append(last_forces[0]); res.drag_N.append(last_forces[1])
            res.alpha_deg.append(math.degrees(last_forces[2]))
        step += 1

    if vehicle.burns and vehicle.burns[0].powered:               # lift-off thrust, for the t = 0 record
        b0, st0 = vehicle.burns[0], air(0.0, vehicle.atmosphere)
        last_forces[0] = max(b0.thrust_vac_N - b0.exit_area_m2 * st0.pressure_Pa, 0.0)
    record(force=True)                       # the state at lift-off belongs in the history too

    for bi, burn in enumerate(vehicle.burns):
        drag_model = vehicle.drag_for_burn(bi)
        if vehicle.fairing_jettison_index is not None and bi == vehicle.fairing_jettison_index:
            m -= vehicle.fairing_kg
            res.events.append(dict(t_s=t, name="fairing jettison", mass_kg=m, h_m=h, v_mps=v, x_m=x,
                                   dropped_kg=vehicle.fairing_kg,
                                   gamma_deg=math.degrees(gamma), q_Pa=air(h, vehicle.atmosphere).dynamic_pressure_Pa(v)))
        if burn.startup_kg:
            m -= burn.startup_kg
        res.events.append(dict(t_s=t, name=f"{burn.name} start", mass_kg=m, h_m=h, v_mps=v, x_m=x,
                               gamma_deg=math.degrees(gamma),
                               q_Pa=air(h, vehicle.atmosphere).dynamic_pressure_Pa(v)))
        m_start_burn = m
        remaining = burn.duration_s
        while remaining > 1e-12:
            step_dt = min(dt, remaining)
            # land a step boundary exactly on the pitch-kick time: a gravity turn is so sensitive to the kick
            # that applying it up to one step late would make the whole trajectory depend on the step size
            if not kicked and t < guidance.vertical_rise_s < t + step_dt:
                step_dt = guidance.vertical_rise_s - t

            # --- guidance: the pitch kick (a step change in gamma, book p.376)
            if (not kicked) and t >= guidance.vertical_rise_s:
                gamma -= math.radians(guidance.kick_deg)
                kicked = True
                res.events.append(dict(t_s=t, name=f"pitch kick {guidance.kick_deg:.3f} deg", mass_kg=m, h_m=h,
                                       v_mps=v, x_m=x, gamma_deg=math.degrees(gamma), q_Pa=0.0))

            def state_rates(vv, gg, hh, mm, tt):
                st = air(hh, vehicle.atmosphere)
                thrust = 0.0
                if burn.powered:
                    thrust = max(burn.thrust_vac_N - burn.exit_area_m2 * st.pressure_Pa, 0.0)
                cd = drag_model.cd(st.mach(vv), hh, power_on=burn.powered)
                dN = cd * vehicle.reference_area_m2 * 0.5 * st.density_kg_m3 * vv * vv
                g = gravity_mps2(hh, vehicle.g0, vehicle.r_planet_m)
                alpha = _steering_alpha(guidance, burn, tt, t_last_burn_end, vv, gg, hh, mm, thrust,
                                        g, vehicle.r_planet_m, st.dynamic_pressure_Pa(vv))
                rates = _derivs(vv, gg, hh, mm, thrust, dN, g, vehicle.r_planet_m, alpha)
                if not kicked:
                    # The vertical rise is vertical: the turn starts at the pitch kick and not before (book
                    # p.369). Eq. 6:43 cannot be left to say so. Its pitch rate is -(g/v) cos(gamma), cos(pi/2)
                    # is 6e-17 in floating point rather than zero, and g/v is enormous in the first second, so
                    # rounding error was amplified into a real tilt before the kick: under a thousandth of a
                    # degree at a lift-off thrust-to-weight of 1.2, a tenth of a degree at 1.18 - as large as
                    # the kick itself - and the shooting then solved for a kick on top of noise.
                    rates = (rates[0], 0.0, rates[2], rates[3])
                return rates, thrust, dN, g, st, alpha

            def integrands(vv, gg, hh, mm, st, dN, g, thrust, alpha):
                """The Eq. 6:58 loss integrands at one stage of the RK4 step, plus the vacuum ideal."""
                return (g * math.sin(gg),                                        # gravity
                        dN / mm,                                                 # drag
                        (burn.exit_area_m2 * st.pressure_Pa / mm) if burn.powered else 0.0,   # back pressure
                        (burn.thrust_vac_N / mm) if (burn.powered and burn.mdot_kgs > 0) else 0.0,
                        2.0 * thrust * math.sin(0.5 * alpha) ** 2 / mm)          # steering, Eq. 6:58

            (k1, th1, d1, g1, st1, a1) = state_rates(v, gamma, h, m, t)
            i1 = integrands(v, gamma, h, m, st1, d1, g1, th1, a1)
            m_half = m - burn.mdot_kgs * step_dt / 2.0
            (k2, th2, d2, g2, st2, a2) = state_rates(v + k1[0] * step_dt / 2, gamma + k1[1] * step_dt / 2,
                                                     h + k1[2] * step_dt / 2, m_half, t + step_dt / 2)
            i2 = integrands(v + k1[0] * step_dt / 2, gamma + k1[1] * step_dt / 2, h + k1[2] * step_dt / 2,
                            m_half, st2, d2, g2, th2, a2)
            (k3, th3, d3, g3, st3, a3) = state_rates(v + k2[0] * step_dt / 2, gamma + k2[1] * step_dt / 2,
                                                     h + k2[2] * step_dt / 2, m_half, t + step_dt / 2)
            i3 = integrands(v + k2[0] * step_dt / 2, gamma + k2[1] * step_dt / 2, h + k2[2] * step_dt / 2,
                            m_half, st3, d3, g3, th3, a3)
            m_end = m - burn.mdot_kgs * step_dt
            (k4, th4, d4, g4, st4, a4) = state_rates(v + k3[0] * step_dt, gamma + k3[1] * step_dt,
                                                     h + k3[2] * step_dt, m_end, t + step_dt)
            i4 = integrands(v + k3[0] * step_dt, gamma + k3[1] * step_dt, h + k3[2] * step_dt,
                            m_end, st4, d4, g4, th4, a4)
            max_alpha_used = max(max_alpha_used, abs(a1))

            # --- loss integrals (Eq. 6:58), accumulated with the same RK4 weights as the state, so that the
            # four losses and the final speed close against the vacuum ideal to integration accuracy
            w = step_dt / 6.0
            grav += w * (i1[0] + 2 * i2[0] + 2 * i3[0] + i4[0])
            drag_l += w * (i1[1] + 2 * i2[1] + 2 * i3[1] + i4[1])
            prop_l += w * (i1[2] + 2 * i2[2] + 2 * i3[2] + i4[2])
            ideal += w * (i1[3] + 2 * i2[3] + 2 * i3[3] + i4[3])
            steer_l += w * (i1[4] + 2 * i2[4] + 2 * i3[4] + i4[4])

            v += (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0]) * step_dt / 6.0
            gamma += (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1]) * step_dt / 6.0
            h += (k1[2] + 2 * k2[2] + 2 * k3[2] + k4[2]) * step_dt / 6.0
            x += (k1[3] + 2 * k2[3] + 2 * k3[3] + k4[3]) * step_dt / 6.0
            m = m_end
            t += step_dt
            remaining -= step_dt
            last_forces[0], last_forces[1], last_forces[2] = th4, d4, a4
            record()

            if h < stop_altitude_m - 1.0 and t > guidance.vertical_rise_s + 1.0:
                record(force=True)
                res.outcome = "fell_back"
                res.status = (f"the vehicle returned to the surface {t:.0f} s after lift-off with the pitch kick "
                              f"at {guidance.kick_deg:.4f} deg")
                _finish(res, t, v, gamma, h, x, ideal, grav, drag_l, steer_l, prop_l, vehicle)
                return res
            if math.degrees(gamma) < guidance.min_gamma_deg:
                record(force=True)
                res.outcome = "nosed_over"
                res.status = (f"flight path angle fell below {guidance.min_gamma_deg:.0f} deg at t = {t:.0f} s: "
                              f"the kick of {guidance.kick_deg:.4f} deg is too large")
                _finish(res, t, v, gamma, h, x, ideal, grav, drag_l, steer_l, prop_l, vehicle)
                return res

        if burn.powered and burn.mdot_kgs > 0:
            res.events.append(dict(t_s=t, name=f"{burn.name} burnout", mass_kg=m, h_m=h, v_mps=v, x_m=x,
                                   gamma_deg=math.degrees(gamma),
                                   q_Pa=air(h, vehicle.atmosphere).dynamic_pressure_Pa(v)))
        if burn.jettison_kg:
            m -= burn.jettison_kg
            res.events.append(dict(t_s=t, name=burn.jettison_note or f"{burn.name} jettison", mass_kg=m, h_m=h,
                                   v_mps=v, x_m=x, dropped_kg=burn.jettison_kg,
                                   gamma_deg=math.degrees(gamma), q_Pa=0.0))
        if m <= 0:
            raise TrajectoryError(f"{burn.name}: the vehicle mass went to zero - check the burn definitions")

    record(force=True)
    res.max_alpha_deg = math.degrees(max_alpha_used)
    res.converged = True
    res.outcome = "flown"
    res.status = "flown to the end of the last burn"
    _finish(res, t, v, gamma, h, x, ideal, grav, drag_l, steer_l, prop_l, vehicle)
    return res


def _finish(res, t, v, gamma, h, x, ideal, grav, drag_l, steer_l, prop_l, vehicle):
    res.peak_h_m = max(res.h_m) if res.h_m else h
    res.burnout_t_s, res.burnout_v_mps = t, v
    res.burnout_gamma_deg, res.burnout_h_m = math.degrees(gamma), h
    res.downrange_m = x
    res.ideal_dv_mps = ideal
    res.gravity_loss_mps, res.drag_loss_mps = grav, drag_l
    res.steering_loss_mps, res.propulsion_loss_mps = steer_l, prop_l
    res.closure_residual_mps = ideal - (grav + drag_l + steer_l + prop_l) - v
    if res.q_Pa:
        i = max(range(len(res.q_Pa)), key=lambda k: res.q_Pa[k])
        res.max_q_Pa, res.max_q_t_s = res.q_Pa[i], res.t_s[i]
        res.max_q_h_m, res.max_q_mach = res.h_m[i], res.mach[i]
    if len(res.v_mps) > 2:
        acc = [(res.v_mps[k + 1] - res.v_mps[k]) / max(res.t_s[k + 1] - res.t_s[k], 1e-9) / G0
               for k in range(len(res.v_mps) - 1)]
        res.accel_g = acc + [acc[-1]]
        res.max_accel_g = max(acc)


# --------------------------------------------------------------------------- shooting on the kick angle
def shoot_for_altitude(vehicle: AscentVehicle, target_altitude_m: float, vertical_rise_s: float = 10.0,
                       kick_lo_deg: float = 0.002, kick_hi_deg: float = 30.0, tol_m: float = 2000.0,
                       max_iter: int = 48, dt: float = 0.25,
                       guidance: "Guidance | None" = None) -> TrajectoryResult:
    """Find the pitch kick that puts burnout at the target altitude - the book's "shooting" (Fig. 6.18).

    The book describes the method as adjusting the kick "depending on whether the terminal state is too high or
    too low". Burnout altitude does fall as the kick grows, but only over the range where the vehicle actually
    flies a turn: nudge it too little and it goes ballistic and falls back (a *low* final altitude reached for
    the opposite reason), nudge it too much and it noses into the ground. Comparing raw burnout altitudes across
    those regimes would send a bisection the wrong way, so each flight is first classified:

        fell_back  -> went up and came down: the kick was too SMALL
        nosed_over -> pitched below the floor: the kick was too LARGE
        flown      -> compare burnout altitude with the target in the ordinary way

    With that, the bracket is unambiguous and the bisection is safe.
    """
    def fly(kick):
        if guidance is None:
            g = Guidance(vertical_rise_s=vertical_rise_s, kick_deg=kick)
        else:
            g = replace(guidance, vertical_rise_s=vertical_rise_s, kick_deg=kick)
        return integrate(vehicle, g, dt=dt)

    def too_small(r):
        """Was this kick too small? A complete flight is judged on its burnout altitude. A flight that ended on
        the ground is judged on how high it got first: up and back down means it was lofted (kick too small),
        while never getting near the target means it was flat (kick too large)."""
        if r.outcome == "flown":
            return r.burnout_h_m > target_altitude_m
        return r.peak_h_m > target_altitude_m

    lo, hi = kick_lo_deg, kick_hi_deg
    r_lo, r_hi = fly(lo), fly(hi)
    if not too_small(r_lo):
        r_lo.converged = False
        r_lo.status = "shooting failed: even the smallest kick does not reach the target altitude"
        r_lo.notes.append(f"a {lo:.3f} deg kick burns out at {r_lo.burnout_h_m/1e3:.0f} km (peak "
                          f"{r_lo.peak_h_m/1e3:.0f} km) against a {target_altitude_m/1e3:.0f} km target: this "
                          f"vehicle cannot reach that altitude on a gravity turn with these burn times")
        return r_lo
    if too_small(r_hi):
        r_hi.converged = False
        r_hi.status = "shooting failed: even the largest kick stays above the target altitude"
        r_hi.notes.append(f"a {hi:.1f} deg kick still burns out at {r_hi.burnout_h_m/1e3:.0f} km against a "
                          f"{target_altitude_m/1e3:.0f} km target")
        return r_hi
    best = None
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        r = fly(mid)
        if r.outcome == "flown":
            best = r
            if abs(r.burnout_h_m - target_altitude_m) < tol_m:
                break
        if too_small(r):
            lo = mid
        else:
            hi = mid
    if best is None or best.outcome != "flown":
        out = best or fly(0.5 * (lo + hi))
        out.converged = False
        out.status = "shooting failed: no kick angle produced a complete ascent"
        return out
    best.notes.append(f"pitch kick {best.kick_deg:.4f} deg found by shooting (book Fig. 6.18) for a "
                      f"{target_altitude_m/1e3:.0f} km burnout altitude after a {vertical_rise_s:.0f} s "
                      f"vertical rise")
    if abs(best.burnout_h_m - target_altitude_m) > 5 * tol_m:
        best.converged = False
        best.status = (f"shooting did not converge: closest burnout altitude {best.burnout_h_m/1e3:.0f} km "
                       f"against a {target_altitude_m/1e3:.0f} km target")
    if abs(best.burnout_gamma_deg) > 10.0:
        # reaching the altitude on the way back down is not an insertion, and calling it converged would hand
        # the caller a loss budget for a trajectory that never got to orbit
        best.converged = False
        best.status = (f"the ascent crossed the target altitude with a flight path angle of "
                       f"{best.burnout_gamma_deg:+.1f} deg, so it is not an orbit insertion")
    elif abs(best.burnout_gamma_deg) > 3.0:
        best.notes.append(f"burnout flight path angle is {best.burnout_gamma_deg:+.1f} deg rather than ~0: a "
                          f"gravity turn has only one free parameter once the altitude is fixed, so the "
                          f"injection geometry is whatever that trajectory gives")
    return best


# --------------------------------------------------------------------------- building the vehicle from a design
def ascent_vehicle_from_result(res, drag: aero.DragModel | None = None, atmosphere: str = "book_exponential",
                               coast_between_stages: bool = True, last_ascent_stage: int | None = None) -> AscentVehicle:
    """Turn a converged sizing result into something the integrator can fly.

    Each stage becomes one powered burn at its sized thrust and mass flow, with its inert mass jettisoned at the
    end; the staging delay becomes an unpowered coast. A stage with strap-ons attached is expanded into the
    parallel-burn phases the boosters module already solved, with the vacuum thrust of everything burning and the
    back pressure on every nozzle. (The phases themselves carry a sea-level/vacuum average of the Isp, which is right
    for a mass ratio and wrong for a flight: with the core's back pressure taken off it as well, it charged that twice.)
    The nozzle exit area comes from the stage's own sea-level and vacuum thrust
    (Ae = (T_vac - T_SL)/P0, exact by Eq. 6:52), falling back to the engine geometry when a stage has no
    sea-level figure.
    """
    spec = res.spec
    drag = drag or aero.geometry_model()
    sref = 0.25 * math.pi * res.geometry.max_diameter ** 2
    if drag.reference_area_m2:
        sref = drag.reference_area_m2
    burns = []
    shapes = []                # per burn: (lowest stage still attached, strap-ons attached, strap-ons thrusting)
    n_boost = spec.boosters.n_total if getattr(spec, "boosters", None) is not None else 0
    fairing_index = None
    N = len(res.stages)
    # a vehicle whose upper stage restarts after a coast (a parking orbit, then a departure burn) must not have
    # that second burn flown as part of the ascent; `last_ascent_stage` ends the ascent at insertion
    stages = [s for s in res.stages if last_ascent_stage is None or s.index <= last_ascent_stage]
    for s in stages:
        st = spec.stages[s.index - 1]
        if spec.fairing.jettison_stage == s.index:
            fairing_index = len(burns)
        ae = 0.0
        if s.thrust_sl_N:
            # a design that gives one Isp for both conditions means no back pressure, and lifts off at the T/W it says
            ae = max(s.thrust_vac_N - s.thrust_sl_N, 0.0) / P0_PA
        elif not s.is_solid:
            ae = st.engine.n_engines * 0.25 * math.pi * st.engine.exit_diameter_m ** 2
        elif s.nozzle_dims is not None:
            ae = 0.25 * math.pi * getattr(s.nozzle_dims, "exit_diameter_m", 0.0) ** 2
        jett = s.m_dry_kg + s.m_residual_kg + s.m_margin_prop_kg
        stop = not s.is_solid
        thr = 1.0 if s.is_solid else float(getattr(st.engine, "throttle_min", None) or 1.0)
        phases = list(s.phases or [])
        if phases:
            # the phase model emits zero-duration "Jettison ..." phases whose mass step is the hardware dropped;
            # those become jettison events on the burn before them rather than burns of their own
            powered = [p for p in phases if p.duration_s > 0]
            for k, p in enumerate(phases):
                if p.duration_s <= 0:
                    drop = max(p.m_start_kg - p.m_end_kg, 0.0)
                    if drop > 0 and burns:
                        burns[-1].jettison_kg += drop
                        burns[-1].jettison_note = f"stage {s.index}: {p.name}"
                    gone = re.match(r"Jettison (\d+) x", p.name)
                    n_boost = max(n_boost - int(gone.group(1)), 0) if gone else 0
                    continue
                last = p is powered[-1]
                first = p is powered[0]
                on = re.match(r"Parallel burn: core \+ (\d+) x", p.name)
                n_on = int(on.group(1)) if on else 0
                bb = res.boosters
                t_vac = s.thrust_vac_N + (n_on * bb.thrust_vac_each_N if n_on else 0.0)
                a_all = ae
                if n_on and bb.thrust_sl_each_N and bb.thrust_vac_each_N > bb.thrust_sl_each_N:
                    a_all += n_on * (bb.thrust_vac_each_N - bb.thrust_sl_each_N) / P0_PA
                shapes.append((s.index, n_boost, p.name.startswith("Parallel burn"), ae))
                burns.append(Burn(startup_kg=s.m_startup_kg if first else 0.0,
                                  name=f"stage {s.index} {p.name}", duration_s=p.duration_s,
                                  thrust_vac_N=t_vac, mdot_kgs=p.mdot_total_kgs,
                                  exit_area_m2=a_all, isp_vac_s=t_vac / (p.mdot_total_kgs * G0),
                                  jettison_kg=jett if last else 0.0,
                                  jettison_note=f"stage {s.index} jettison" if last else "",
                                  stoppable=stop and last))
        else:
            shapes.append((s.index, 0, False, ae))
            burns.append(Burn(name=f"stage {s.index}", duration_s=s.burn_time_s, startup_kg=s.m_startup_kg,
                              thrust_vac_N=s.thrust_vac_N, mdot_kgs=s.mdot_kgs, exit_area_m2=ae,
                              isp_vac_s=st.prop_system.isp_vac_s, jettison_kg=jett,
                              jettison_note=f"stage {s.index} jettison", stoppable=stop, throttle_min=thr))
        if coast_between_stages and s.index < stages[-1].index and spec.mission.get("staging_delay_s"):
            burns.append(Burn(name=f"coast {s.index}/{s.index+1}", duration_s=spec.mission["staging_delay_s"],
                              powered=False))
            shapes.append((s.index + 1, 0, False, 0.0))
            if fairing_index is not None and fairing_index == len(burns) - 1:
                fairing_index -= 1
    by_burn = None
    if drag.kind == "geometry" and drag.buildup is None:
        # One shape per flight phase, all on the lift-off reference area: the strap-ons leave, then the spent
        # stages. Identical shapes share one Configuration so its Mach table is built once.
        from . import drag_buildup as db
        made = {}
        by_burn = []
        for burn, (first_stage, n_on, lit, core_ae) in zip(burns, shapes):
            key = (first_stage, n_on, lit, round(core_ae, 6))
            if key not in made:
                cfg = db.configuration_from_result(res, first_stage, n_on, lit, core_ae or None,
                                                   drag.buildup_options)
                cfg.reference_area_m2 = sref
                made[key] = replace(drag, buildup=cfg, notes=list(drag.notes))
            by_burn.append(made[key])
        drag = by_burn[0]
        drag.notes.append(
            f"drag built up from the sized geometry for {len(made)} flight shape(s); surface roughness "
            f"{1e6 * drag.buildup_options.roughness_m:.0f} micrometres, {drag.buildup_options.nose_shape} nose"
            + (f" blunted to {drag.buildup_options.nose_bluntness:.2f} of the fairing diameter"
               if drag.buildup_options.nose_bluntness else "")
            + ". Protuberances, fins, core-to-strap-on interference and plume effects are not modelled")
    return AscentVehicle(name=spec.name, m0_kg=res.glom_kg, burns=burns, reference_area_m2=sref, drag=drag,
                         atmosphere=atmosphere, fairing_jettison_index=fairing_index,
                         fairing_kg=res.fairing_mass_kg, drag_by_burn=by_burn)


def _diagnose(res, veh: AscentVehicle, out: TrajectoryResult) -> str:
    """Say why an ascent would not close, in terms the designer can act on."""
    bits = []
    for s in res.stages[1:]:
        if s.tw_ignition < 0.35 and s.burn_time_s > 600.0:
            bits.append(f"stage {s.index} ignites at a thrust-to-weight of {s.tw_ignition:.2f} and burns for "
                        f"{s.burn_time_s / 60.0:.0f} minutes. It falls faster than it gains speed: give it more thrust, or "
                        f"move delta-v to the stage below so that it starts closer to orbital speed")
    b0 = veh.burns[0] if veh.burns else None
    if b0 is not None and not res.spec.mission.get("air_launch"):
        tw = max(b0.thrust_vac_N - b0.exit_area_m2 * P0_PA, 0.0) / (veh.m0_kg * G0)
        if tw < 1.05:
            bits.append(f"the lift-off thrust-to-weight at sea level is {tw:.2f}")
    if not bits:
        bits.append("no single cause stands out; the state history shows where it turns over")
    return "why it did not close: " + "; ".join(bits)


def drag_table(veh: AscentVehicle, traj=None) -> dict | None:
    """The lift-off shape's Cd against Mach number, term by term, for the report and the GUI.

    Each Mach number is evaluated at the altitude this ascent actually reached it, so the friction term carries
    the right Reynolds number; a Mach number the ascent never reached uses a typical altitude instead.
    """
    d = veh.drag_for_burn(0)
    if d.kind != "geometry" or d.buildup is None:
        return None
    from . import drag_buildup as db
    cfg = d.buildup
    rows = []
    for m in (0.3, 0.6, 0.8, 0.9, 1.0, 1.1, 1.2, 1.5, 2.0, 3.0, 4.0, 5.0):
        h = db.representative_altitude_m(m)
        if traj is not None and traj.mach:
            for k in range(1, len(traj.mach)):
                if traj.mach[k - 1] <= m <= traj.mach[k]:
                    h = traj.h_m[k]
                    break
        on = cfg.breakdown(m, h, True)
        rows.append(dict(mach=m, altitude_m=h, friction=on["friction"], forebody=on["forebody"],
                         boattail=on["boattail"], base=on["base"], total=on["total"],
                         total_power_off=cfg.breakdown(m, h, False)["total"],
                         book_titan2=aero.cd_titan2(m)))
    peak = max(rows, key=lambda r: r["total"])
    return dict(rows=rows, shape=cfg.name, reference_area_m2=cfg.reference_area_m2,
                roughness_m=cfg.roughness_m, peak_cd=peak["total"], peak_mach=peak["mach"],
                bodies=[dict(name=b.name, count=b.count, length_m=b.length_m, diameter_m=b.max_diameter_m,
                             wetted_area_m2=b.wetted_area_m2) for b in cfg.bodies])


# --------------------------------------------------------------------------- did it reach the orbit?
#: An orbit whose perigee is below this is not counted as an orbit. ASSUMED: 100 km is the conventional edge of
#: space, and a perigee under it does not survive a revolution. It is a reporting threshold, not a decay model.
ORBIT_FLOOR_ALTITUDE_M = 100e3
#: How far below a target apsis the flown one may fall and still count as reached. ASSUMED: the larger of
#: 10 km and 2 % of the target altitude, which is looser than a real injection accuracy and is meant only to
#: keep the shooting tolerance of this model from failing a vehicle that flew the mission.
ORBIT_TOLERANCE_M = 10e3
ORBIT_TOLERANCE_FRACTION = 0.02
#: above this the timeline gives no Mach number: there is no air for it to describe
TIMELINE_MACH_CEILING_M = 100e3


def insertion_orbit(res, traj, r_planet_m: float = 6378e3, last_ascent_stage: int | None = None) -> dict:
    """The orbit the end of the flight is on, against the orbit the mission asked for.

    A flight from `ascent.fly` carries its inertial horizontal and vertical speed, because it is integrated on a
    turning Earth. For any other state the integration is on a non-rotating Earth, its burnout speed is relative to
    the launch site, and the site's eastward speed is added back as the delta-v budget took it out (orbit.needed_speed,
    book Example 3.9): V = v_site sin(beta) + sqrt((v cos gamma)^2 - (v_site cos beta)^2). The orbit then follows from
    two-body energy and angular momentum:

        eps = v^2/2 - mu/r,  a = -mu/(2 eps),  h = r v cos(gamma_i),  e = sqrt(1 + 2 eps h^2/mu^2)
    """
    info = res.budget.info
    target = info.get("orbit")
    out = dict(checked=False, verdict="not_checked", headline="", notes=[],
               target_perigee_alt_m=getattr(target, "perigee_alt_m", None),
               target_apogee_alt_m=getattr(target, "apogee_alt_m", None))
    if not getattr(traj, "attempted", True):
        out["headline"] = "The ascent was not flown, so there is no burnout state to check."
        return out
    if not traj.converged:
        out.update(verdict="no_ascent",
                   headline="The ascent did not close, so no orbit was reached: " + (traj.status or ""))
        return out
    if target is None:
        out["headline"] = "The mission has no target orbit to check against."
        return out
    if last_ascent_stage is not None:
        out["headline"] = (f"Not checked: the ascent is stopped after stage {last_ascent_stage}, before the "
                           f"burn that completes the orbit, so the state it ends on is not the injection.")
        return out

    mu = G0 * r_planet_m * r_planet_m
    vs = float(info.get("v_site_mps") or 0.0)
    fin = getattr(traj, "final_state", None)
    if fin:
        r_planet_m, mu = fin.get("r_planet_m", r_planet_m), fin.get("mu", mu)
        v_hor, vv, h_end = fin["horizontal_mps"], fin["vertical_mps"], fin["h_m"]
    else:
        v, gam = traj.burnout_v_mps, math.radians(traj.burnout_gamma_deg)
        beta = math.radians(float(info.get("azimuth_deg") or 90.0))
        vh, vv, h_end = v * math.cos(gam), v * math.sin(gam), traj.burnout_h_m
        disc = vh * vh - (vs * math.cos(beta)) ** 2
        v_hor = vs * math.sin(beta) + math.sqrt(max(disc, 0.0))
    r = r_planet_m + h_end
    v_in = math.hypot(v_hor, vv)
    gam_in = math.atan2(vv, v_hor)
    eps = 0.5 * v_in * v_in - mu / r
    need = float(info.get("v_needed_mps") or 0.0)
    out.update(checked=True, inertial_speed_mps=v_in, inertial_gamma_deg=math.degrees(gam_in),
               site_speed_mps=vs, burnout_alt_m=h_end,
               speed_margin_mps=(traj.margin_mps if fin else (traj.burnout_v_mps - need) if need else None))
    tp, ta = target.perigee_alt_m, target.apogee_alt_m
    tol_p = max(ORBIT_TOLERANCE_M, ORBIT_TOLERANCE_FRACTION * tp)
    tol_a = max(ORBIT_TOLERANCE_M, ORBIT_TOLERANCE_FRACTION * ta)
    out.update(tolerance_perigee_m=tol_p, tolerance_apogee_m=tol_a)
    if eps >= 0.0:
        out.update(verdict="reached", perigee_alt_m=h_end, apogee_alt_m=None, eccentricity=None,
                   headline="Burnout is faster than escape speed: the target orbit is exceeded, not missed.")
        return out
    a = -mu / (2.0 * eps)
    ang = r * v_hor
    e = math.sqrt(max(0.0, 1.0 + 2.0 * eps * ang * ang / (mu * mu)))
    hp, ha = a * (1.0 - e) - r_planet_m, a * (1.0 + e) - r_planet_m
    out.update(perigee_alt_m=hp, apogee_alt_m=ha, eccentricity=e, semi_major_axis_m=a)
    km = lambda x: f"{x / 1e3:,.0f}".replace(",", " ")
    flown = f"{km(hp)} x {km(ha)} km"
    asked = f"{km(tp)} x {km(ta)} km"
    if hp >= tp - tol_p and ha >= ta - tol_a:
        out["verdict"] = "reached"
        out["headline"] = f"Target orbit reached: the flight ends on a {flown} orbit against {asked} asked for."
        if ha > ta + tol_a:
            out["notes"].append(f"The apogee is {km(ha - ta)} km above the target: the vehicle arrives with "
                                f"speed to spare, which is unused performance rather than an error."
                                + (" A solid last stage cannot be shut down to stop there."
                                   if getattr(traj, "profile", "") == "solid" else ""))
    elif hp >= ORBIT_FLOOR_ALTITUDE_M:
        out["verdict"] = "short"
        out["headline"] = (f"In orbit, but short of the target: the flight ends on a {flown} orbit against "
                           f"{asked} asked for.")
    else:
        out["verdict"] = "suborbital"
        path = (f"a path that comes back to the ground after an apogee of {km(ha)} km" if hp <= 0.0
                else f"a {flown} path, whose perigee is below {km(ORBIT_FLOOR_ALTITUDE_M)} km")
        out["headline"] = f"Not in orbit: the flight ends on {path}, against {asked} asked for."
    if abs(math.degrees(gam_in)) > 1.0:
        out["notes"].append(f"The flight path angle at the end is {math.degrees(gam_in):+.1f} deg, not level, "
                            f"so the flight does not end at the perigee.")
    return out


def timeline(traj) -> list:
    """The ascent as a list of events in time order: what the integration logged as it happened (ignitions,
    the pitch kick, burnouts, jettisons) with Mach 1, maximum dynamic pressure and peak acceleration added
    from the recorded history. Each row carries t_s, name, h_m, v_mps, mach, gamma_deg, q_Pa, mass_kg, x_m.

    `mach` is None above TIMELINE_MACH_CEILING_M: the number is still computable there and means nothing.
    The peak acceleration is the sensed axial one, (thrust - drag)/(m g0), which is what a payload and a
    structure feel and what the g limit is about; `max_accel_g` on the result is dv/dt along the flight path,
    which has gravity in it and is smaller."""
    if not traj.t_s:
        return []
    ts = traj.t_s

    def nearest(t):
        return min(range(len(ts)), key=lambda k: abs(ts[k] - t))

    def mach_at(k):
        return traj.mach[k] if traj.h_m[k] <= TIMELINE_MACH_CEILING_M else None

    def at(k, name, t=None):
        return dict(t_s=ts[k] if t is None else t, name=name, h_m=traj.h_m[k], v_mps=traj.v_mps[k],
                    mach=mach_at(k), gamma_deg=traj.gamma_deg[k], q_Pa=traj.q_Pa[k], mass_kg=traj.m_kg[k],
                    x_m=traj.x_m[k], derived=True)

    rows = []
    for i, e in enumerate(traj.events):
        name = e["name"]
        if i == 0 and e["t_s"] == 0.0 and name.endswith(" start"):
            name = f"Lift-off ({name[:-6]} ignition)"
        elif name.endswith(" start"):
            name = name[:-6] + (" begins" if name.lower().startswith("coast") else " ignition")
        elif name.lower().startswith("coast") and name.endswith(" burnout"):
            name = name[:-8] + " ends"
        rows.append(dict(t_s=e["t_s"], name=name[:1].upper() + name[1:], h_m=e["h_m"], v_mps=e["v_mps"],
                         mach=mach_at(nearest(e["t_s"])), gamma_deg=e["gamma_deg"], q_Pa=e.get("q_Pa", 0.0),
                         mass_kg=e["mass_kg"], x_m=e.get("x_m", 0.0), derived=False))
    for k in range(1, len(ts)):
        if traj.mach[k - 1] < 1.0 <= traj.mach[k]:
            f = (1.0 - traj.mach[k - 1]) / max(traj.mach[k] - traj.mach[k - 1], 1e-12)
            rows.append(at(k, "Mach 1", ts[k - 1] + f * (ts[k] - ts[k - 1])))
            break
    if traj.q_Pa and max(traj.q_Pa) > 0.0:
        k = max(range(len(ts)), key=lambda j: traj.q_Pa[j])
        rows.append(at(k, f"Maximum dynamic pressure, {traj.q_Pa[k] / 1e3:.1f} kPa"))
    if traj.thrust_N and len(traj.thrust_N) == len(ts):
        # The thrust recorded with a sample is the thrust of the step that ended on it. At a burnout the
        # sample's own mass is already the mass AFTER the spent stage has gone, so pairing the two would
        # report the dying stage's thrust pushing only what is left: 8.8 g on a vehicle that saw 4.7. The
        # burnout event carries the mass before the jettison, and that is the one to use there.
        before = {e["t_s"]: e["mass_kg"] for e in traj.events if e["name"].endswith((" burnout", " cutoff"))}
        mass = [max(traj.m_kg[j], before.get(ts[j], 0.0)) for j in range(len(ts))]
        sensed = [(traj.thrust_N[j] - traj.drag_N[j]) / (mass[j] * G0) for j in range(len(ts))]
        # nothing is felt after the last engine stops
        k = max(range(len(ts)), key=lambda j: sensed[j])
        row = at(k, f"Peak axial acceleration, {sensed[k]:.2f} g")
        row["mass_kg"] = mass[k]
        rows.append(row)
    order = sorted(range(len(rows)), key=lambda j: (rows[j]["t_s"], j))
    return [rows[j] for j in order]


def flight_options(spec) -> dict:
    """The ascent inputs of a design, as arguments for `fly_design` and the ascent optimiser (drag aside)."""
    m = spec.mission
    return dict(atmosphere=m.get("atmosphere_model") or "book_exponential",
                vertical_rise_s=float(m.get("vertical_rise_s") or 10.0),
                last_ascent_stage=m.get("last_ascent_stage"),
                profile=m.get("ascent_profile") or "auto",
                parking_altitude_m=m.get("parking_altitude_m"))


def equivalent_loss_mps(res, traj) -> float | None:
    """The losses of the whole flight on the delta-v budget's own footing: everything the budget added to the orbital
    speed, less the speed left in hand. Sized with this number the vehicle would arrive with only its margin lines.

    Not the sum of the loss integrals: those stop at the first cutoff, and they count the back pressure that the
    sizing has already taken out of the first stage's effective Isp.
    """
    if not traj.converged or not traj.ideal_used_mps or res.spec.mission.get("dv_override_mps") is not None:
        return None
    b = res.budget
    return b.total_mps - b.subtotal("ideal", "rotation") - traj.margin_mps


def fly_design(res, drag: aero.DragModel | None = None, atmosphere: str = "book_exponential",
               vertical_rise_s: float = 10.0, dt: float = 0.5, target_altitude_m: float | None = None,
               kick_deg: float | None = None, last_ascent_stage: int | None = None,
               profile: str = "auto", parking_altitude_m: float | None = None, **options) -> TrajectoryResult:
    """Fly a converged design to its orbit (see `ascent.py`), or fly one given pitch kick.

    `profile` is auto | direct | parking; `options` go to `ascent.Flight` (hand-over altitude and dynamic pressure,
    limits).
    """
    from . import ascent
    veh = ascent_vehicle_from_result(res, drag, atmosphere, last_ascent_stage=last_ascent_stage)
    f = ascent.flight_for(res, veh, profile or "auto", parking_altitude_m or ascent.PARKING_M, target_altitude_m,
                          last_ascent_stage, rise_s=vertical_rise_s, **options)
    sol = f.search()[0] if kick_deg is None else f.try_kick(kick_deg)
    out = ascent.fly(f, sol, veh.name, dt)
    if not out.converged:
        out.notes.append(_diagnose(res, veh, out))
    out.notes.extend(ascent.notes(f, sol, out))
    out.notes.append(f"drag model: {veh.drag.describe()}")
    out.notes.extend(veh.drag.notes)
    out.drag_table = drag_table(veh, out)
    out.notes.append(f"reference area {veh.reference_area_m2:.2f} m2 "
                     f"(max vehicle diameter {res.geometry.max_diameter:.2f} m)")
    out.notes.append(f"atmosphere: {atmosphere}")
    out.insertion = insertion_orbit(res, out, veh.r_planet_m, last_ascent_stage)
    out.equivalent_loss_mps = equivalent_loss_mps(res, out) if last_ascent_stage is None else None
    out.budget_loss_mps = res.budget.subtotal("loss")
    return out
