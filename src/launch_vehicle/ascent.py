"""Ascent to orbit: gravity turn, linear tangent steering, engine cutoff, coast and restart.

What it adds to `trajectory.integrate`, which flies the book's pure gravity turn to the end of the last burn
-------------------------------------------------------------------------------------------------------------
* LINEAR TANGENT STEERING above the atmosphere (book Eq. 6:59, p.371, after Perkins): the tangent of the thrust's
  pitch angle changes linearly with time. The book states it is optimal for orbital insertion. Eq. 6:59 is the case
  that ends level; here both ends are free, so the two constants can be solved for the two things an insertion needs:
  the altitude and a level arrival.
* ENGINE CUTOFF when the orbit is reached, for a last stage that can stop, so what is left in the tanks is a result.
* THE WAY TO ORBIT the book recommends (Sec. 6.5, pp.372-373, Fig. 6.20): straight in up to about 200 km; above that,
  insertion low with enough speed to coast up, and a second burn at the top.
* A ROTATING EARTH, flown in the plane of the orbit: the frame turns with the in-plane part of the Earth's rotation,
  omega cos(i), so the Coriolis and centrifugal terms are in the equations and the site's speed is not added
  afterwards. The out-of-plane part of the site's speed is removed by a constant yaw angle of the thrust, and what that
  costs is a steering loss.
* Throttling to the axial acceleration limit, for engines that say they can throttle.
* A coast to the top before a SOLID last stage, which cannot restart.
* AIR LAUNCH from the carrier's speed, altitude and flight path angle.

Equations (polar, in the turning frame; book Table 6.1 with the two rotation terms added)
    dv/dt     = (T cos(alpha) cos(yaw) - D)/m - (g - w^2 r) sin(gamma)
    v dgam/dt = T sin(alpha) cos(yaw)/m - (g - w^2 r - v^2/r) cos(gamma) + 2 w v
    dh/dt     = v sin(gamma),   dx/dt = v cos(gamma) R/r,   w = omega cos(i)

The book's Table 6.1 has w = 0. The rotation terms are standard mechanics and SUPPLEMENTARY.

What is free and how it is chosen
---------------------------------
The pitch kick is the one number left after the steering constants have been solved for the insertion. It is
searched for the flight that leaves the most speed in hand, so every design is flown well rather than anyhow. Dynamic
pressure over the design's own limit counts against a kick (Q_PENALTY_MPS_PER_KPA, an assumption).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

G0 = 9.80665

#: hand-over from the gravity turn to linear tangent steering: at this altitude or once the dynamic pressure has fallen
#: to this, whichever is first. ASSUMED, the same values the gravity-turn model uses.
HANDOVER_H_M = 60e3
HANDOVER_Q_PA = 1000.0
#: book p.373: "lower orbits (200 km) burn directly to injection"
DIRECT_LIMIT_M = 200e3
#: above this apogee the second burn is made from a circular parking orbit at the perigee instead of at the apogee
HIGH_APOGEE_M = 2000e3
#: the first insertion of a flight that raises its orbit afterwards. ASSUMED.
PARKING_M = 185e3
#: how strongly a kick is discouraged from exceeding the design's dynamic pressure limit. ASSUMED.
Q_PENALTY_MPS_PER_KPA = 3.0
VERTICAL_RISE_S = 10.0
#: the pitch kick also waits for this speed. ASSUMED: it is what a lift-off at 1.3 g has after the 10 s above. A slow
#: lift-off kicked at 8 m/s has no gravity turn at all: the angle grows as (v/v_kick)^(g/a) and the smallest kick
#: noses over.
KICK_SPEED_MPS = 30.0
DT_ATM, DT_EXO, DT_SOLVE, DT_COAST = 0.25, 1.0, 2.5, 10.0
MAX_COAST_S = 20_000.0


class State:
    """One instant of the flight, and the loss integrals up to it."""
    __slots__ = ("t", "v", "g", "h", "x", "m", "bi", "left", "lit", "kicked", "qmax", "ideal", "grav", "drag", "bp",
                 "steer", "T", "D", "alpha", "amax")

    def __init__(self):
        self.t = self.v = self.h = self.x = self.m = 0.0
        self.g = math.pi / 2
        self.bi, self.left, self.lit, self.kicked, self.qmax = 0, None, False, False, 0.0
        self.ideal = self.grav = self.drag = self.bp = self.steer = 0.0
        self.T = self.D = self.alpha = self.amax = 0.0

    def copy(self):
        s = State.__new__(State)
        for k in State.__slots__:
            setattr(s, k, getattr(self, k))
        return s


class Air:
    """Density, pressure and sound speed on a 100 m grid, so the solver is not slowed by the atmosphere model."""
    TOP = 140_000.0
    _cache: dict = {}

    def __new__(cls, model):
        if model not in cls._cache:
            from .atmosphere import air
            o = object.__new__(cls)
            n = int(cls.TOP / 100) + 2
            st = [air(100.0 * i, model) for i in range(n)]
            o.rho = [s.density_kg_m3 for s in st]
            o.p = [s.pressure_Pa for s in st]
            o.a = [s.sound_speed_mps for s in st]
            cls._cache[model] = o
        return cls._cache[model]

    def at(self, h):
        if h >= self.TOP:
            return 0.0, 0.0, self.a[-1]
        if h < 0.0:
            h = 0.0
        y = h * 0.01
        i = int(y)
        f = y - i
        r, p, a = self.rho, self.p, self.a
        return r[i] + f * (r[i + 1] - r[i]), p[i] + f * (p[i + 1] - p[i]), a[i] + f * (a[i + 1] - a[i])


@dataclass
class Plan:
    """What the ascent is asked to do, after the mission and the vehicle have been read."""
    kind: str                       # direct | transfer | parking | solid
    h_ins_m: float                  # altitude of the insertion
    a_ins_m: float                  # semi-major axis to insert into
    perigee_m: float                # target altitudes
    apogee_m: float
    why: str = ""
    later_dv_mps: float = 0.0       # ideal speed the second burn needs, so the search prices it


@dataclass
class Solution:
    kick_deg: float = 0.0
    A: float = 0.0                  # tan(pitch) when linear tangent steering starts
    B: float = 0.0                  # tan(pitch) at the reference time Tref after that
    tref: float = 1.0
    tau: float = 0.0                # solid plan: ignition of the last stage relative to centred on the apex
    coast: bool = False
    margin: float = -math.inf
    ok: bool = False
    why: str = ""
    score: float = -math.inf


class Flight:
    def __init__(self, veh, plan: Plan, mu: float, radius: float, omega: float = 0.0, w_out: float = 0.0,
                 rise_s: float = VERTICAL_RISE_S, q_limit_Pa: float | None = None, accel_limit_g: float | None = None,
                 handover_h_m: float = HANDOVER_H_M, handover_q_Pa: float = HANDOVER_Q_PA, qalpha_limit: float | None = None,
                 kick_speed: float = KICK_SPEED_MPS, q_hard: bool = False, start: dict | None = None,
                 node_angle=None):
        self.veh, self.plan, self.mu, self.R, self.om = veh, plan, mu, radius, omega
        self.rise, self.q_limit, self.a_lim = rise_s, q_limit_Pa, accel_limit_g
        self.hh, self.hq = handover_h_m, handover_q_Pa
        self.qa = math.radians(qalpha_limit) if qalpha_limit else None      # [Pa rad]
        self.vkick = kick_speed
        self.q_pen = 1000.0 if q_hard else Q_PENALTY_MPS_PER_KPA
        self.air = Air(veh.atmosphere)
        self.start = start
        self.node_angle = node_angle
        ideal, m = 0.0, veh.m0_kg
        for i, b in enumerate(veh.burns):
            if veh.fairing_jettison_index == i:
                m -= veh.fairing_kg
            m -= b.startup_kg
            if b.powered and b.mdot_kgs > 0:
                mp = b.mdot_kgs * b.duration_s
                ideal += b.thrust_vac_N / b.mdot_kgs * math.log(m / (m - mp))
                m -= mp
            m -= b.jettison_kg
        self.ideal_total = ideal
        self.w_out = w_out
        self.cyaw = math.sqrt(max(0.0, 1.0 - (w_out / ideal) ** 2)) if ideal > 0 else 1.0
        self.powered = [i for i, b in enumerate(veh.burns) if b.powered and b.mdot_kgs > 0]
        self.last = self.powered[-1]
        self.events: list = []
        self.tk = rise_s
        self.allow_over = False         # accept an orbit already passed when the last stage lights
        self.pulling = False            # an air launch pulling up, which its wing does and this model does not
        self.grids_left = 3             # grid searches for a start; a vehicle that fails three will fail the rest
        self.stop_below = -1.0
        self.vacuum = False             # the solver's first pass ignores the air above the hand-over

    # ------------------------------------------------------------------------------------- frame and orbit
    def inertial(self, s):
        """Inertial horizontal and vertical speed in the orbit plane."""
        return s.v * math.cos(s.g) + self.om * (self.R + s.h), s.v * math.sin(s.g)

    def energy(self, s):
        vh, vr = self.inertial(s)
        return 0.5 * (vh * vh + vr * vr) - self.mu / (self.R + s.h)

    def apses(self, s):
        """(perigee altitude, apogee altitude) of the present orbit; apogee None when unbound."""
        vh, vr = self.inertial(s)
        r = self.R + s.h
        e = 0.5 * (vh * vh + vr * vr) - self.mu / r
        L = r * vh
        ecc = math.sqrt(max(0.0, 1 + 2 * e * L * L / self.mu ** 2))
        if e >= 0:
            return L * L / self.mu / (1 + ecc) - self.R, None
        a = -self.mu / (2 * e)
        return a * (1 - ecc) - self.R, a * (1 + ecc) - self.R

    # ------------------------------------------------------------------------------------- the integrator
    def fresh(self):
        s = State()
        s.m = self.veh.m0_kg
        if self.start:
            s.v, s.h, s.g = self.start["v"], self.start["h"], self.start["g"]
            s.kicked = True
            self.tk = 0.0
        return s

    def _step(self, s, dt, b, dm, f, steer, vertical, losses):
        """One RK4 step in place. `f` throttle held over the step; `steer(t, gamma)` gives the thrust pitch angle."""
        mu, R, om, veh = self.mu, self.R, self.om, self.veh
        S = veh.reference_area_m2
        cy = self.cyaw
        at = self.air.at
        powered = b.powered and b.mdot_kgs > 0
        Tv = f * b.thrust_vac_N if powered else 0.0
        ae = b.exit_area_m2 if powered else 0.0
        md = f * b.mdot_kgs if powered else 0.0
        sin, cos, vac, qa = math.sin, math.cos, self.vacuum, self.qa
        pull = self.pulling

        def rates(v, g, h, m, t):
            r = R + h
            if h < Air.TOP and not vac:
                rho, p, a = at(h)
                T = Tv - ae * p
                if T < 0.0:
                    T = 0.0
                D = dm.cd(v / a, h, powered) * S * 0.5 * rho * v * v if rho > 0.0 else 0.0
            else:
                rho, p, T, D = 0.0, 0.0, Tv, 0.0
            gl = mu / (r * r) - om * om * r
            sg, cg = sin(g), cos(g)
            if T > 0.0 and steer is not None:
                al = steer(t, g) - g
                if qa is not None and rho > 0.0 and not pull:
                    lim = qa / max(0.5 * rho * v * v, 1e-9)      # the air load the vehicle may take
                    al = lim if al > lim else (-lim if al < -lim else al)
                sa, ca = sin(al), cos(al)
            else:
                al, sa, ca = 0.0, 0.0, 1.0
            dv = (T * ca * cy - D) / m - gl * sg
            if vertical or v < 1e-6:
                dg = 0.0
            else:
                dg = T * sa * cy / (m * v) - (gl / v - v / r) * cg + 2.0 * om
            if losses:
                il = (gl * sg, D / m, ae * p / m if T > 0 else 0.0, Tv / m, T * (1.0 - ca * cy) / m)
            else:
                il = None
            return dv, dg, v * sg, v * cg * R / r, T, D, al, il

        v, g, h, x, m, t = s.v, s.g, s.h, s.x, s.m, s.t
        h2 = 0.5 * dt
        k1 = rates(v, g, h, m, t)
        mh = m - md * h2
        k2 = rates(v + k1[0] * h2, g + k1[1] * h2, h + k1[2] * h2, mh, t + h2)
        k3 = rates(v + k2[0] * h2, g + k2[1] * h2, h + k2[2] * h2, mh, t + h2)
        me = m - md * dt
        k4 = rates(v + k3[0] * dt, g + k3[1] * dt, h + k3[2] * dt, me, t + dt)
        w = dt / 6.0
        s.v = v + w * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0])
        s.g = g + w * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1])
        s.h = h + w * (k1[2] + 2 * k2[2] + 2 * k3[2] + k4[2])
        s.x = x + w * (k1[3] + 2 * k2[3] + 2 * k3[3] + k4[3])
        s.m, s.t = me, t + dt
        s.T, s.D, s.alpha = k4[4], k4[5], k4[6]
        if losses:
            i1, i2, i3, i4 = k1[7], k2[7], k3[7], k4[7]
            s.grav += w * (i1[0] + 2 * i2[0] + 2 * i3[0] + i4[0])
            s.drag += w * (i1[1] + 2 * i2[1] + 2 * i3[1] + i4[1])
            s.bp += w * (i1[2] + 2 * i2[2] + 2 * i3[2] + i4[2])
            s.ideal += w * (i1[3] + 2 * i2[3] + 2 * i3[3] + i4[3])
            s.steer += w * (i1[4] + 2 * i2[4] + 2 * i3[4] + i4[4])
            s.amax = max(s.amax, abs(k1[6]))

    def throttle(self, b, m):
        if self.a_lim and b.powered and b.throttle_min < 1.0 and b.thrust_vac_N > 0:
            return min(1.0, max(b.throttle_min, self.a_lim * G0 * m / b.thrust_vac_N))
        return 1.0

    def _event(self, log, s, name, **kw):
        if log is not None:
            rho = self.air.at(s.h)[0]
            log.append(dict(t_s=s.t, name=name, mass_kg=s.m, h_m=s.h, v_mps=s.v, x_m=s.x, gamma_deg=math.degrees(s.g),
                            q_Pa=0.5 * rho * s.v * s.v, **kw))

    def _ignite(self, s, log):
        b = self.veh.burns[s.bi]
        if self.veh.fairing_jettison_index == s.bi:
            s.m -= self.veh.fairing_kg
            self._event(log, s, "fairing jettison", dropped_kg=self.veh.fairing_kg)
        s.m -= b.startup_kg
        s.left = b.mdot_kgs * b.duration_s if (b.powered and b.mdot_kgs > 0) else b.duration_s
        s.lit = True
        self._event(log, s, f"{b.name} start")

    def _finish_burn(self, s, log, cut=False, jettison=True):
        b = self.veh.burns[s.bi]
        if b.powered and b.mdot_kgs > 0:
            self._event(log, s, f"{b.name} {'cutoff' if cut else 'burnout'}")
        if jettison and b.jettison_kg:
            s.m -= b.jettison_kg
            self._event(log, s, b.jettison_note or f"{b.name} jettison", dropped_kg=b.jettison_kg)
        s.bi += 1
        s.lit = False

    def run(self, s, mode, steer=None, kick_deg=0.0, dt=DT_SOLVE, e_target=None, stop_before=None, rec=None, log=None,
            losses=False):
        """Advance `s` in place. mode "atmo" stops at the hand-over; "exo" flies on under `steer`. Returns the reason:
        handover, cutoff, depleted, before (stop_before reached), ground, nose."""
        veh = self.veh
        air = self.air.at
        while s.bi < len(veh.burns):
            if stop_before is not None and s.bi >= stop_before:
                return "before"
            if not s.lit:
                self._ignite(s, log)
            b = veh.burns[s.bi]
            dm = veh.drag_for_burn(s.bi)
            powered = b.powered and b.mdot_kgs > 0
            can_cut = e_target is not None and s.bi == self.last and powered and b.stoppable
            if can_cut and self.energy(s) >= e_target and not self.allow_over:
                return "over"
            while s.left > 1e-9:
                vertical = False
                if mode == "atmo":
                    d = DT_ATM
                    if not s.kicked:
                        if s.t >= self.rise - 1e-9 and s.v >= self.vkick:
                            s.g -= math.radians(kick_deg)
                            self.tk = s.t
                            s.kicked = True
                            self._event(log, s, f"pitch kick {kick_deg:.3f} deg")
                        else:
                            vertical = True
                            if s.t < self.rise - 1e-9:
                                d = min(d, self.rise - s.t)
                            elif s.t > 60.0:
                                return "no rise"
                else:
                    d = dt if powered else max(dt, 1.0)
                f = self.throttle(b, s.m) if powered else 1.0
                d = min(d, s.left / (f * b.mdot_kgs) if powered else s.left)
                before = s.copy() if can_cut else None
                self._step(s, d, b, dm, f, steer if mode == "exo" or self.start else None, vertical, losses)
                s.left -= f * b.mdot_kgs * d if powered else d
                if can_cut and self.energy(s) >= e_target:
                    lo, hi = 0.0, d
                    for _ in range(40):
                        mid = 0.5 * (lo + hi)
                        q = before.copy()
                        self._step(q, mid, b, dm, f, steer, vertical, False)
                        if self.energy(q) >= e_target:
                            hi = mid
                        else:
                            lo = mid
                        if hi - lo < 1e-6:
                            break
                    self._copy_into(s, before)
                    self._step(s, hi, b, dm, f, steer, vertical, losses)
                    s.left = before.left - f * b.mdot_kgs * hi
                    if rec is not None:
                        rec(s, True)
                    return "cutoff"
                if rec is not None:
                    rec(s, False)
                if s.h < Air.TOP:
                    q = 0.5 * air(s.h)[0] * s.v * s.v
                    if q > s.qmax:
                        s.qmax = q
                    if mode == "atmo":
                        if s.h < -1.0 and s.t > 1.0:
                            return "ground"
                        if s.g < -0.2 and s.kicked and not self.start:
                            return "nose"
                        if s.kicked and s.t > self.tk + 5.0 and (
                                s.h >= self.hh or (s.h > 25e3 and q <= self.hq and s.qmax > q)):
                            return "handover"
                elif mode == "atmo":
                    return "handover"
                if mode == "exo" and (s.h < -50e3 if not self.vacuum else s.h < -0.5 * self.R):
                    return "ground"
                if rec is not None and (s.h < -1.0 or (s.h < self.stop_below and s.g < 0.0)):
                    return "ground"
            self._finish_burn(s, log, jettison=s.bi != self.last)
        return "depleted"

    @staticmethod
    def _copy_into(dst, src):
        for k in State.__slots__:
            setattr(dst, k, getattr(src, k))

    # ------------------------------------------------------------------------------------- steering
    @staticmethod
    def linear_tangent(A, B, t0, tref):
        c = (B - A) / tref
        at = math.atan

        def steer(t, g):
            return at(A + c * (t - t0))
        return steer

    def remaining_time(self, s):
        tot = 0.0
        for i in range(s.bi, len(self.veh.burns)):
            b = self.veh.burns[i]
            if i == s.bi and s.lit:
                tot += s.left / b.mdot_kgs if (b.powered and b.mdot_kgs > 0) else s.left
            else:
                tot += b.duration_s
        return max(tot, 1.0)

    def e_insert(self):
        return -self.mu / (2.0 * self.plan.a_ins_m)

    def speed_need(self, h):
        return math.sqrt(max(0.0, 2.0 * (self.e_insert() + self.mu / (self.R + h))))

    def margin_of(self, s, why):
        """Speed in hand [m/s]: what the propellant left at cutoff is worth, or minus the speed that is missing."""
        if why == "cutoff":
            b = self.veh.burns[self.last]
            ve = b.thrust_vac_N / b.mdot_kgs
            return ve * math.log(s.m / max(s.m - s.left, 1e-6))
        vh, vr = self.inertial(s)
        return math.hypot(vh, vr) - self.speed_need(s.h)

    # ------------------------------------------------------------------------------------- the solver
    def _newton(self, f, z0, n=14, span=(0.35, 0.35), eps=(1e-3, 1e-3), tol=(150.0, 3e-4)):
        """Damped Newton on two unknowns for (altitude error, flight path angle error)."""
        z = list(z0)
        r = f(z)
        if r is None:
            return None, None
        def size(q):
            return math.hypot(q[0] / 2e4, q[1] / 0.02)
        for _ in range(n):
            if abs(r[0]) < tol[0] and abs(r[1]) < tol[1]:
                return z, r
            J = []
            for k in (0, 1):
                y = list(z)
                y[k] += eps[k]
                q = f(y)
                if q is None:
                    return None, None
                J.append(((q[0] - r[0]) / eps[k], (q[1] - r[1]) / eps[k]))
            det = J[0][0] * J[1][1] - J[1][0] * J[0][1]
            if abs(det) < 1e-14:
                return None, None
            d0 = -(r[0] * J[1][1] - J[1][0] * r[1]) / det
            d1 = -(J[0][0] * r[1] - r[0] * J[0][1]) / det
            sc = min(1.0, span[0] / max(abs(d0), 1e-12), span[1] / max(abs(d1), 1e-12))
            best = None
            for _try in range(6):
                y = [z[0] + sc * d0, z[1] + sc * d1]
                q = f(y)
                if q is not None and size(q) < size(r) * (1 - 1e-4):
                    best = (y, q)
                    break
                sc *= 0.5
            if best is None:
                break
            z, r = best
        return (z, r) if abs(r[0]) < 10 * tol[0] and abs(r[1]) < 10 * tol[1] else (None, r)

    def solve_steering(self, s0, guess=None, dt=None):
        """Linear tangent constants that arrive level at the insertion altitude from hand-over state `s0`."""
        tref = self.remaining_time(s0)
        dt = dt or min(10.0, max(DT_SOLVE, tref / 160.0))
        et = self.e_insert()
        ht = self.plan.h_ins_m
        out = {}

        def f(z):
            if max(abs(z[0]), abs(z[1])) > 30:
                return None
            s = s0.copy()
            why = self.run(s, "exo", self.linear_tangent(z[0], z[1], s0.t, tref), dt=dt, e_target=et)
            if why == "ground":
                return None
            out["s"], out["why"] = s, why
            return s.h - ht, s.g

        def polish(z0):
            z, r = self._newton(f, z0)
            if z is None:
                return None
            f(z)
            if out["why"] == "over" and not self.allow_over:
                return None
            return z, tref, out["s"], out["why"]

        if guess:
            got = polish(guess)
            if got:
                return got
        g0 = math.tan(min(s0.g, 1.2))
        self.vacuum = True
        try:
            first = None
            for z0 in [(g0 + d, e) for d in (0.15, 0.6, -0.2) for e in (-0.1, 0.4, -0.5)]:
                first, r = self._newton(f, z0)
                if first is not None:
                    break
            if first is None and self.grids_left > 0:
                self.grids_left -= 1
                grid = []
                for d in (-1.5, -0.8, -0.3, 0.0, 0.3, 0.8, 1.5, 3.0):
                    for e in (-4.0, -2.0, -1.0, -0.4, 0.0, 0.4, 1.0, 2.0):
                        r = f((g0 + d, e))
                        if r is not None:
                            grid.append((math.hypot(r[0] / 1e5, r[1] / 0.1), (g0 + d, e)))
                for _, z0 in sorted(grid)[:3]:
                    first, r = self._newton(f, z0, n=25)
                    if first is not None:
                        break
        finally:
            self.vacuum = False
        return polish(first) if first is not None else None

    def solve_solid(self, s0, guess=None, dt=DT_SOLVE):
        """Constant pitch to the last stage, a coast to near the top, and the last stage fired level."""
        ht = self.plan.h_ins_m
        b = self.veh.burns[self.last]
        tb = b.duration_s
        out = {}

        def f(z):
            if abs(z[0]) > 30:
                return None
            s = s0.copy()
            A = z[0]
            if self.run(s, "exo", self.linear_tangent(A, A, s0.t, 1.0), dt=dt, stop_before=self.last) != "before":
                return None
            if not self.coast_to_apex(s, -tb / 2 + z[1] * 100.0, dt=DT_SOLVE):
                return None
            t1 = s.t
            why = self.run(s, "exo", self.linear_tangent(0.0, 0.0, t1, 1.0), dt=min(dt, 1.0))
            out["s"], out["why"] = s, why
            return s.h - ht, s.g

        g0 = math.tan(min(s0.g, 1.2))
        for z0 in ([guess] if guess else []) + [(g0 + d, 0.0) for d in (0.1, 0.5, 1.2, -0.2, 2.5)]:
            z, r = self._newton(f, z0, span=(0.4, 0.4), tol=(300.0, 1e-3))
            if z is not None:
                f(z)
                return z, 1.0, out["s"], out["why"]
        return None

    def coast_to_apex(self, s, shift, dt=DT_COAST, rec=None, losses=False):
        """Coast until `shift` seconds after the moment the climb stops. False when there is no climb left to coast."""
        need = self.time_to_apex(s)
        if need is None:
            return False
        self.coast_for(s, max(0.0, need + shift), dt, rec, losses)
        return True

    def time_to_apex(self, s):
        """Two-body time from this state to apoapsis."""
        vh, vr = self.inertial(s)
        r = self.R + s.h
        e = 0.5 * (vh * vh + vr * vr) - self.mu / r
        if e >= 0:
            return None
        a = -self.mu / (2 * e)
        L = r * vh
        ecc = math.sqrt(max(1e-16, 1 + 2 * e * L * L / self.mu ** 2))
        cE = max(-1.0, min(1.0, (1 - r / a) / ecc))
        E = math.acos(cE)
        if vr < 0:
            E = 2 * math.pi - E
        n = math.sqrt(self.mu / a ** 3)
        M = E - ecc * math.sin(E)
        dt = (math.pi - M) / n
        return dt if dt >= 0 else dt + 2 * math.pi / n

    def coast_for(self, s, secs, dt=DT_COAST, rec=None, losses=False):
        from types import SimpleNamespace
        b = SimpleNamespace(powered=False, mdot_kgs=0.0, thrust_vac_N=0.0, exit_area_m2=0.0)
        dm = self.veh.drag_for_burn(min(s.bi, len(self.veh.burns) - 1))
        left = min(secs, MAX_COAST_S)
        while left > 1e-9:
            d = min(dt, left)
            self._step(s, d, b, dm, 1.0, None, False, losses)
            left -= d
            if rec is not None:
                rec(s, False)
            if s.h < 0:
                return False
        return True

    def atmosphere_leg(self, kick, rec=None, log=None, losses=False):
        s = self.fresh()
        steer = None
        if self.start:
            th = math.radians(kick)           # air launch: thrust held at this pitch attitude until the hand-over

            def steer(t, g):
                return th
        self.pulling = bool(self.start)
        why = self.run(s, "atmo", steer, kick_deg=kick, rec=rec, log=log, losses=losses)
        self.pulling = False
        return s, why

    def try_kick(self, kick, guess=None):
        sol = Solution(kick_deg=kick)
        s, why = self.atmosphere_leg(kick)
        if why != "handover":
            sol.why = why
            return sol
        got = []
        if self.plan.kind == "solid":
            a = self.solve_solid(s, guess.get("solid") if guess else None)
            if a:
                got.append((a, True))
        b = self.solve_steering(s, guess.get("lt") if guess else None)
        if b:
            got.append((b, False))
        for (z, tref, e, w), coast in got:
            m = self.margin_of(e, w) - self.plan.later_dv_mps
            pen = 0.0
            if self.q_limit and s.qmax > self.q_limit:
                pen = self.q_pen * (s.qmax - self.q_limit) / 1e3
            if m - pen > sol.score:
                sol.A, sol.B, sol.tref, sol.margin, sol.ok, sol.why = z[0], z[1], tref, m, True, w
                sol.coast, sol.tau = coast, (z[1] if coast else 0.0)
                sol.score = m - pen
        if not sol.ok:
            sol.why = "no steering"
        return sol

    def kicks(self):
        """Kicks whose gravity turn reaches the hand-over, spread over its flight path angle rather than over the kick:
        a slow lift-off makes the turn depend on the kick exponentially, and a fast one hardly at all."""
        legs = {}

        def leg(y):
            s, why = self.atmosphere_leg(math.exp(y))
            legs[y] = math.degrees(s.g) if why == "handover" else None

        lo, hi = math.log(1e-4), math.log(40.0)
        n = 13
        for i in range(n):
            leg(lo + (hi - lo) * i / (n - 1))
        for _ in range(16):                                    # halve the widest gap in hand-over angle
            ys = sorted(legs)
            gaps = []
            for a, b in zip(ys, ys[1:]):
                ga, gb = legs[a], legs[b]
                if ga is None and gb is None:
                    continue
                gap = abs((90.0 if ga is None else ga) - (0.0 if gb is None else gb))
                if b - a > 0.01:
                    gaps.append((gap, a, b))
            if not gaps or max(gaps)[0] < 7.0:
                break
            _, a, b = max(gaps)
            leg(0.5 * (a + b))
        ok = [y for y in sorted(legs) if legs[y] is not None and 2.0 < legs[y] < 88.5]
        out, last = [], None
        for y in ok:
            if last is None or abs(legs[y] - last) > 3.0:
                out.append(math.exp(y))
                last = legs[y]
        return out

    def search(self, around=None):
        """The kick with the most speed in hand. `around`: a solution of a similar flight, to look near first."""
        if around is not None and around.ok and around.kick_deg > 0:
            k0 = around.kick_deg
            xs = ([k0 - 6.0, k0, k0 + 6.0] if self.start else [k0 * q for q in (0.4, 0.7, 1.0, 1.4, 2.2)])
            lo, hi, to, fro = ((5.0, 80.0, (lambda k: k), (lambda y: y)) if self.start
                               else (math.log(1e-4), math.log(40.0), math.log, math.exp))
        elif self.start:
            xs = [10.0, 18.0, 26.0, 34.0, 42.0, 50.0, 60.0, 70.0]
            lo, hi, to, fro = 5.0, 80.0, (lambda k: k), (lambda y: y)
        else:
            xs = self.kicks()
            lo, hi, to, fro = math.log(1e-4), math.log(40.0), math.log, math.exp
        sols, guess = [], None
        if around is not None and around.ok:
            guess = {"solid": (around.A, around.tau)} if around.coast else {"lt": (around.A, around.B)}
        for i, k in enumerate(xs):
            if guess is None and len(sols) >= 4 and i % 4:
                continue                                       # nothing so far: look more coarsely
            q = self.try_kick(k, guess)
            sols.append(q)
            if q.ok:
                guess = {"solid": (q.A, q.tau)} if q.coast else {"lt": (q.A, q.B)}
        good = [q for q in sols if q.ok]
        if not good and around is not None:
            return self.search()
        if not good and not self.allow_over:
            # the stages below may carry past the insertion orbit on their own: fly that rather than nothing
            self.allow_over = True
            best, more = self.search(around)
            if best.ok:
                return best, more
            self.allow_over = False
            return best, more
        if not good:
            return (sols[0] if sols else Solution(why="no gravity turn leaves the atmosphere")), sols
        best = max(good, key=lambda q: q.score)
        xs = [q.kick_deg for q in sols]
        i = sols.index(best)
        a = to(xs[i - 1]) if i > 0 else max(lo, to(xs[0]) - 1.0)
        c = to(xs[i + 1]) if i < len(xs) - 1 else min(hi, to(xs[-1]) + (0.6 if not self.start else 8.0))
        gr = 0.5 * (math.sqrt(5) - 1)
        guess = {"solid": (best.A, best.tau)} if best.coast else {"lt": (best.A, best.B)}
        x1, x2 = c - gr * (c - a), a + gr * (c - a)
        q1, q2 = self.try_kick(fro(x1), guess), self.try_kick(fro(x2), guess)
        for _ in range(9):
            for q in (q1, q2):
                if q.ok and q.score > best.score:
                    best = q
                    guess = {"solid": (q.A, q.tau)} if q.coast else {"lt": (q.A, q.B)}
            if (q1.score if q1.ok else -math.inf) >= (q2.score if q2.ok else -math.inf):
                c, x2, q2 = x2, x1, q1
                x1 = c - gr * (c - a)
                q1 = self.try_kick(fro(x1), guess)
            else:
                a, x1, q1 = x1, x2, q2
                x2 = a + gr * (c - a)
                q2 = self.try_kick(fro(x2), guess)
        for q in (q1, q2):
            if q.ok and q.score > best.score:
                best = q
        return best, sols


# --------------------------------------------------------------------------------------------- choosing the plan
def make_plan(mu, radius, perigee_m, apogee_m, profile="auto", parking_m=PARKING_M, stoppable=True) -> Plan:
    """Pick how the vehicle goes to orbit: see the module notes and book pp.372-373."""
    rp, ra = radius + perigee_m, radius + apogee_m
    a = 0.5 * (rp + ra)
    if not stoppable:
        return Plan("solid", perigee_m, a, perigee_m, apogee_m,
                    "the last stage is solid: it fires once, level, after a coast to the top of the climb")
    if profile == "direct":
        return Plan("direct", perigee_m, a, perigee_m, apogee_m, "direct insertion was asked for")
    if apogee_m > HIGH_APOGEE_M and (apogee_m - perigee_m) > 1000e3:
        park = perigee_m if perigee_m <= 350e3 else parking_m
        r0 = radius + park
        dv = math.sqrt(mu * (2 / r0 - 2 / (r0 + ra))) - math.sqrt(mu / r0)
        return Plan("parking", park, r0, perigee_m, apogee_m,
                    f"parking orbit at {park/1e3:.0f} km, then a second burn to the high apogee", dv)
    if profile == "auto" and perigee_m <= DIRECT_LIMIT_M:
        return Plan("direct", perigee_m, a, perigee_m, apogee_m,
                    f"the perigee is at or below {DIRECT_LIMIT_M/1e3:.0f} km, so the last stage burns straight in")
    park = min(parking_m, perigee_m)
    r0 = radius + park
    at = 0.5 * (r0 + ra)
    dv = math.sqrt(mu * (2 / ra - 1 / a)) - math.sqrt(mu * (2 / ra - 1 / at))
    return Plan("transfer", park, at, perigee_m, apogee_m,
                f"insertion at {park/1e3:.0f} km, coast to {apogee_m/1e3:.0f} km, second burn there", dv)


# --------------------------------------------------------------------------------------------- flying a design
def flight_for(res, veh, profile="auto", parking_m=PARKING_M, target_altitude_m=None, last_ascent_stage=None, **kw) -> Flight:
    """Read the mission and set the flight up: the plan, the Earth's rotation in the orbit plane, the limits."""
    from .units import EARTH_MODELS
    spec = res.spec
    earth = EARTH_MODELS[spec.earth_model]
    info = res.budget.info
    o = info["orbit"]
    mission = spec.mission
    om = w_out = 0.0
    if mission.get("include_earth_rotation", True):
        lat, az = math.radians(mission["site_latitude_deg"]), math.radians(info["azimuth_deg"])
        om = earth.omega_rad_s * math.cos(lat) * math.sin(az)
        w_out = earth.omega_rad_s * earth.radius_m * math.cos(lat) * math.cos(az)
    hp, ha = o.perigee_alt_m, o.apogee_alt_m
    if target_altitude_m is not None:
        hp, ha, profile = target_altitude_m, target_altitude_m, "direct"
    if last_ascent_stage is not None:
        ha, profile = hp, "direct"
    last = [q for q in res.stages if last_ascent_stage is None or q.index <= last_ascent_stage][-1]
    plan = make_plan(earth.mu_m3s2, earth.radius_m, hp, ha, profile, parking_m, stoppable=not last.is_solid)
    al = mission.get("air_launch")
    start = dict(v=al["release_speed_mps"], h=al["release_altitude_m"],
                 g=math.radians(al.get("flight_path_angle_deg", 0.0))) if al else None
    c = spec.constraints or {}
    kw.setdefault("q_limit_Pa", c.get("max_dynamic_pressure_Pa"))
    kw.setdefault("qalpha_limit", c.get("max_q_alpha_Pa_deg"))
    kw.setdefault("accel_limit_g", c.get("max_accel_g"))
    f = Flight(veh, plan, earth.mu_m3s2, earth.radius_m, om, w_out, start=start, **kw)
    f.lat, f.inc = math.radians(mission["site_latitude_deg"]), math.radians(info["inclination_deg"])
    return f


class Recorder:
    """Keeps the state history in a TrajectoryResult, thinned to what a chart needs."""

    def __init__(self, out, flight, every_s=1.0):
        self.o, self.f, self.every, self.last = out, flight, every_s, -1e9

    def __call__(self, s, force=False):
        if not force and s.t - self.last < self.every - 1e-9 and (s.left is None or s.left > 1e-9):
            return
        self.last = s.t
        o = self.o
        rho, _, a = self.f.air.at(s.h)
        o.t_s.append(s.t)
        o.v_mps.append(s.v)
        o.gamma_deg.append(math.degrees(s.g))
        o.h_m.append(s.h)
        o.x_m.append(s.x)
        o.m_kg.append(s.m)
        o.q_Pa.append(0.5 * rho * s.v * s.v)
        o.mach.append(s.v / a)
        o.thrust_N.append(s.T)
        o.drag_N.append(s.D)
        o.alpha_deg.append(math.degrees(s.alpha))


def node_coast_s(f: Flight, s) -> float:
    """Coast time to the next equator crossing of a parking orbit, where a transfer to a high apogee starts."""
    if abs(math.sin(f.inc)) < abs(math.sin(f.lat)) + 1e-9:
        u0 = math.pi / 2
    else:
        u0 = math.asin(math.sin(f.lat) / math.sin(f.inc))
    u = u0 + s.x / f.R
    left = (math.pi - u) % math.pi
    return left * math.sqrt((f.R + s.h) ** 3 / f.mu)


def second_burn(f: Flight, s, rec, log, dt, centre_s, level, energy):
    """Coast to the burn and burn until the orbit's energy is reached. `centre_s`: coast time to the middle of it."""
    b = f.veh.burns[f.last]
    ve = b.thrust_vac_N / b.mdot_kgs
    dv = f.plan.later_dv_mps
    tb = min(s.left, s.m * (1.0 - math.exp(-max(dv, 0.0) / ve))) / b.mdot_kgs
    f._event(log, s, "coast to the second burn start")
    f.coast_for(s, max(5.0, centre_s - 0.5 * tb), DT_COAST, rec, True)
    f._event(log, s, f"{b.name} second burn start")
    ideal0 = s.ideal
    steer = (lambda t, g: 0.0) if level else (lambda t, g: g)
    why = f.run(s, "exo", steer, dt=dt, e_target=energy, rec=rec, log=None, losses=True)
    return why, s.ideal - ideal0


def fly(f: Flight, sol: Solution, veh_name: str, dt=0.5):
    """Fly a solution at a fine step, recording everything, through the coast and the second burn."""
    from .trajectory import TrajectoryResult
    out = TrajectoryResult(vehicle_name=veh_name, converged=False, status="not run", kick_deg=sol.kick_deg,
                           vertical_rise_s=f.rise)
    rec, log = Recorder(out, f), out.events
    s = f.fresh()
    rec(s, True)
    steer = None
    if f.start:
        th = math.radians(sol.kick_deg)

        def steer(t, g):
            return th
    b0 = f.veh.burns[0]
    v0 = s.v
    f.pulling = bool(f.start)
    why = f.run(s, "atmo", steer, kick_deg=sol.kick_deg, rec=rec, log=log, losses=True)
    f.pulling = False
    out.thrust_N[0] = max(b0.thrust_vac_N - b0.exit_area_m2 * f.air.at(out.h_m[0])[1], 0.0)
    if why != "handover" or not sol.ok:
        # fly on with the thrust along the path, so that there is a history to look at
        if why == "handover":
            f.stop_below = 0.8 * s.h
            f.run(s, "exo", lambda t, g: g, dt=1.0, rec=rec, log=log, losses=True)
        rec(s, True)
        out.outcome = "nosed_over" if why == "nose" else "fell_back"
        out.status = {"nose": "the vehicle noses over in the atmosphere",
                      "no rise": "the vehicle does not gain speed off the pad"}.get(
            why, "no steering brings the vehicle level at the insertion altitude: it comes down before it has the speed")
        finish(f, out, s, v0)
        return out
    f._event(log, s, "linear tangent steering")
    if sol.coast:
        got = f.solve_solid(s, (sol.A, sol.tau), dt=1.0)
        z = got[0] if got else (sol.A, sol.tau)
        f.run(s, "exo", f.linear_tangent(z[0], z[0], s.t, 1.0), dt=1.0, stop_before=f.last, rec=rec, log=log, losses=True)
        f._event(log, s, "coast to the last stage start")
        tb = f.veh.burns[f.last].duration_s
        f.coast_to_apex(s, -tb / 2 + z[1] * 100.0, dt=DT_SOLVE, rec=rec, losses=True)
        why = f.run(s, "exo", lambda t, g: 0.0, dt=1.0, rec=rec, log=log, losses=True)
    else:
        tref = f.remaining_time(s)
        step = min(4.0, max(dt, tref / 600.0))
        got = f.solve_steering(s, (sol.A, sol.B), dt=step)
        z = got[0] if got else (sol.A, sol.B)
        why = f.run(s, "exo", f.linear_tangent(z[0], z[1], s.t, tref), dt=step, e_target=f.e_insert(),
                    rec=rec, log=log, losses=True)
        if why == "cutoff":
            f._event(log, s, f"{f.veh.burns[f.last].name} cutoff")
    rec(s, True)
    finish(f, out, s, v0)
    out.margin_mps = f.margin_of(s, why)
    second = 0.0
    if f.plan.kind in ("transfer", "parking") and why == "cutoff" and s.left > 1e-6:
        e_fin = -f.mu / (f.R + f.R + f.plan.perigee_m + f.plan.apogee_m)
        if f.plan.kind == "transfer":
            why, second = second_burn(f, s, rec, log, min(1.0, dt * 2), f.time_to_apex(s) or 0.0, True, e_fin)
        else:
            why, second = second_burn(f, s, rec, log, min(1.0, dt * 2), node_coast_s(f, s), False, e_fin)
        if why == "cutoff":
            f._event(log, s, f"{f.veh.burns[f.last].name} second cutoff")
            out.margin_mps = f.margin_of(s, why)
        else:
            f._event(log, s, f"{f.veh.burns[f.last].name} second burn burnout")
            vh, vr = f.inertial(s)
            out.margin_mps = math.hypot(vh, vr) - math.sqrt(max(0.0, 2 * (e_fin + f.mu / (f.R + s.h))))
        rec(s, True)
    elif f.plan.later_dv_mps:
        out.margin_mps -= f.plan.later_dv_mps
    out.second_burn_dv_mps = second
    out.ideal_used_mps = s.ideal
    out.propellant_left_kg = s.left if why == "cutoff" else 0.0
    vh, vr = f.inertial(s)
    out.final_state = dict(t_s=s.t, v_mps=s.v, gamma_deg=math.degrees(s.g), h_m=s.h, x_m=s.x, m_kg=s.m,
                           horizontal_mps=vh, vertical_mps=vr, r_planet_m=f.R, mu=f.mu)
    bl = f.veh.burns[f.last]
    if bl.jettison_kg:
        dropped = bl.jettison_kg + out.propellant_left_kg
        s.m -= dropped
        s.T = s.D = 0.0                                     # the engine is off: what is left feels no thrust
        f._event(log, s, bl.jettison_note or f"{bl.name} jettison", dropped_kg=dropped)
        rec(s, True)
    out.converged, out.outcome = True, "flown"
    out.status = {"cutoff": "flown to engine cutoff", "depleted": "flown to the end of the last burn"}.get(why, why)
    out.peak_h_m = max(out.h_m)
    return out


def notes(f: Flight, sol: Solution, out) -> list:
    """What the reader of this flight has to know about it."""
    n = [f"way to orbit: {f.plan.why}"]
    if sol.ok and not f.start:
        n.append(f"pitch kick {sol.kick_deg:.4f} deg, chosen for the most speed in hand at the end")
    if f.start:
        n.append(f"air launch: released at {f.start['h']/1e3:.1f} km and {f.start['v']:.0f} m/s; the thrust is held "
                 f"{sol.kick_deg:.0f} deg above the horizon until the hand-over. Wing lift is not modelled, so the thrust "
                 f"does the pull-up that a wing does on a real vehicle")
    if abs(f.w_out) >= 1.0:
        n.append(f"the launch site's {abs(f.w_out):.0f} m/s across the orbit plane is removed by a constant "
                 f"{out.yaw_deg:.1f} deg yaw of the thrust, charged to the steering loss")
    thr = [b.name for b in f.veh.burns if b.powered and b.throttle_min < 1.0]
    if f.a_lim and thr:
        n.append(f"throttled to stay under {f.a_lim:.1f} g where the engine allows it: " + ", ".join(thr))
    if f.plan.kind == "parking":
        n.append("the second burn starts at the next equator crossing; a plane change or a burn at the apogee is not flown")
    return n


def finish(f: Flight, out, s, v0):
    """The summary of the ascent proper, to the first cutoff or burnout of the last stage."""
    out.profile, out.profile_why = f.plan.kind, f.plan.why
    out.parking_altitude_m = f.plan.h_ins_m
    out.peak_h_m = max(out.h_m)
    out.burnout_t_s, out.burnout_v_mps, out.burnout_h_m = s.t, s.v, s.h
    out.burnout_gamma_deg, out.downrange_m = math.degrees(s.g), s.x
    out.ideal_dv_mps = s.ideal
    out.gravity_loss_mps, out.drag_loss_mps = s.grav, s.drag
    out.steering_loss_mps, out.propulsion_loss_mps = s.steer, s.bp
    out.start_v_mps = v0
    out.closure_residual_mps = s.ideal - out.total_loss_mps - (s.v - v0)
    out.max_alpha_deg = math.degrees(s.amax)
    out.yaw_deg = math.degrees(math.acos(max(-1.0, min(1.0, f.cyaw))))
    i = max(range(len(out.q_Pa)), key=lambda k: out.q_Pa[k])
    out.max_q_Pa, out.max_q_t_s, out.max_q_h_m, out.max_q_mach = out.q_Pa[i], out.t_s[i], out.h_m[i], out.mach[i]
    if len(out.v_mps) > 2:
        acc = [(out.v_mps[k + 1] - out.v_mps[k]) / (out.t_s[k + 1] - out.t_s[k]) / G0
               if out.t_s[k + 1] - out.t_s[k] > 1e-3 else 0.0 for k in range(len(out.v_mps) - 1)]
        out.accel_g = acc + [acc[-1]]
        out.max_accel_g = max(acc)
    vh, vr = f.inertial(s)
    out.final_state = dict(t_s=s.t, v_mps=s.v, gamma_deg=math.degrees(s.g), h_m=s.h, x_m=s.x, m_kg=s.m,
                           horizontal_mps=vh, vertical_mps=vr, r_planet_m=f.R, mu=f.mu)
