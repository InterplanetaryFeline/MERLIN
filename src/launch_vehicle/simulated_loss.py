"""Size a vehicle with the ascent losses of its own simulated flight (loss model `simulated`). SUPPLEMENTARY.

The book's loss models are regressions: one number for every vehicle of a given burn time and lift-off acceleration.
This one sizes the vehicle with a first estimate, flies it (`ascent.py`), sizes it again with the losses that flight
had, and repeats until the two agree. The losses barely depend on the size of a vehicle whose thrust-to-weight and
split are fixed, so it settles in two or three flights.

It is off unless chosen. It costs a second or two per sizing, and half a minute to a few minutes when the stage split is
optimised as well, because every candidate split has different losses; there the losses are flown at a spread of splits
and interpolated between them, and flown again at each optimum found, until the two agree.

Where the simulated ascent does not close there is no loss to size with, and the sizing says so instead of falling back
to a regression behind the user's back.
"""
from __future__ import annotations

import copy

FIRST_GUESS_MPS = 1800.0
TOL_MPS = 1.0
MAX_FLIGHTS = 8
#: a loss above this is a vehicle running away, not an ascent
RUNAWAY_MPS = 5000.0
#: what a split whose ascent does not close is charged in the optimiser, above the worst that does
NO_ASCENT_PENALTY_MPS = 1500.0


class Memory:
    """The last solution flown, so that the next similar vehicle is searched near it."""

    def __init__(self):
        self.solution, self.loss = None, None


def flown(res, memory: Memory | None = None):
    """(equivalent loss, trajectory) of a sized vehicle; the loss is None when the ascent does not close."""
    from . import aerodynamics, ascent, trajectory as tj
    o = tj.flight_options(res.spec)
    drag = aerodynamics.model_from_config(res.spec.mission.get("aerodynamics"))
    veh = tj.ascent_vehicle_from_result(res, drag, o["atmosphere"], last_ascent_stage=o["last_ascent_stage"])
    f = ascent.flight_for(res, veh, o["profile"], o["parking_altitude_m"] or ascent.PARKING_M, None,
                          o["last_ascent_stage"], rise_s=o["vertical_rise_s"])
    sol = f.search(memory.solution if memory else None)[0]
    out = ascent.fly(f, sol, veh.name, 0.5)
    if not out.converged:
        out.notes.append(tj._diagnose(res, veh, out))
        return None, out
    if memory is not None:
        memory.solution = sol
    return tj.equivalent_loss_mps(res, out), out


def with_loss(spec, loss_mps: float):
    s = copy.copy(spec)
    s.mission = dict(spec.mission, simulated_loss_mps=float(loss_mps))
    return s


def first_guess(spec) -> float:
    """The book regression's loss for this vehicle, or a typical one where it does not apply."""
    from .convergence import SizingError, size_vehicle
    from .validation import InputError
    if spec.mission.get("air_launch"):
        return FIRST_GUESS_MPS
    s = copy.copy(spec)
    s.mission = dict(spec.mission, loss_model="book_penalty")
    try:
        r = size_vehicle(s, keep_history=False)
        return r.budget.subtotal("loss") if r.converged else FIRST_GUESS_MPS
    except (SizingError, InputError, ValueError):
        return FIRST_GUESS_MPS


def size(spec, keep_history: bool = True, memory: Memory | None = None, tol_mps: float = TOL_MPS):
    """Size `spec` with the losses of its own ascent."""
    from .convergence import SizingError, size_vehicle
    memory = memory or Memory()
    loss = memory.loss or first_guess(spec)
    tried = []
    for _ in range(MAX_FLIGHTS):
        res = size_vehicle(with_loss(spec, loss), keep_history=keep_history)
        res.spec = spec
        if not res.converged:
            return res
        new, out = flown(res, memory)
        if new is None:
            raise SizingError(
                "the simulated ascent of this vehicle does not close, so there are no losses to size it with: "
                + (out.notes[-1] if out.notes else out.status),
                field="mission.losses.model",
                options=[{"label": "Use the book's loss regression instead", "path": "mission.losses.model",
                          "value": "book_penalty",
                          "note": "the Trajectory analysis then says why the ascent of the sized vehicle fails"}])
        tried.append((loss, new))
        if abs(new - loss) < tol_mps:
            break
        if new > RUNAWAY_MPS:
            break
        if len(tried) >= 2 and abs(tried[-1][0] - tried[-2][0]) > 1e-6:
            (x0, y0), (x1, y1) = tried[-2:]
            slope = max(-0.8, min(0.8, (y1 - y0) / (x1 - x0)))      # secant on loss_out(loss_in) = loss_in
            loss = x1 + (y1 - x1) / (1.0 - slope)
        else:
            loss = new
        loss = max(100.0, min(6000.0, loss))
    memory.loss = tried[-1][1]
    res.budget.info["simulated_loss"] = dict(loss_mps=tried[-1][0], flown_mps=tried[-1][1], flights=len(tried),
                                             settled=abs(tried[-1][1] - tried[-1][0]) < tol_mps)
    if not res.budget.info["simulated_loss"]["settled"]:
        raise SizingError(
            f"the simulated losses do not settle: sized with {tried[-1][0]:,.0f} m/s the vehicle loses "
            f"{tried[-1][1]:,.0f} m/s, after {len(tried)} flights. Usually a heavier vehicle on the same engines flies worse, so "
            f"each sizing makes the next loss larger: give it more thrust, or another stage split",
            field="mission.losses.model",
            options=[{"label": "Use the book's loss regression instead", "path": "mission.losses.model",
                      "value": "book_penalty"}])
    return res


# --------------------------------------------------------------------------------------------- the stage split
class LossMap:
    """Losses flown at some splits, interpolated between them (thin-plate spline on all shares but the last)."""

    def __init__(self):
        self.x, self.y, self._f = [], [], None

    def add(self, fractions, loss):
        self.x.append([float(v) for v in fractions[:-1]])
        self.y.append(loss)
        self._f = None

    def _build(self):
        import numpy as np
        good = [v for v in self.y if v is not None]
        worst = max(good) + NO_ASCENT_PENALTY_MPS
        xs = np.array(self.x)
        rbf = None
        if len(good) >= len(xs[0]) + 2:
            from scipy.interpolate import RBFInterpolator
            g = np.array([v is not None for v in self.y])
            rbf = RBFInterpolator(xs[g], np.array(good), kernel="thin_plate_spline", degree=1)
        ys = self.y

        def f(fr):
            p = np.array([fr[:-1]], dtype=float)
            k = int(np.argmin(np.linalg.norm(xs - p, axis=1)))
            if ys[k] is None:                              # the nearest flight did not close: this one will not either
                return float(worst)
            v = float(rbf(p)[0]) if rbf is not None else float(ys[k])
            return min(max(v, 0.7 * min(good)), worst)
        self._f = f

    def __call__(self, fractions):
        if self._f is None:
            self._build()
        return self._f(fractions)

    def __deepcopy__(self, memo):
        return self                                        # the optimiser copies specs; they all read this one map


def sample_splits(n_stages: int, centre, n: int):
    """The design's own split, and `n` others spread round it (a fixed, repeatable set)."""
    import numpy as np
    rng = np.random.default_rng(7)
    out = [list(centre)]
    if n_stages == 2:
        return out + [[float(a), float(1.0 - a)] for a in np.linspace(0.25, 0.65, n)]
    for _ in range(n):
        v = np.array(centre) * np.exp(rng.normal(0.0, 0.35, n_stages))
        out.append([float(q) for q in v / v.sum()])
    return out


def optimise_split(spec, optimise, rounds: int = 3, **kw):
    """`optimise(spec, **kw)` (the ordinary split search) with losses that follow the split."""
    from .convergence import SizingError, size_vehicle
    from .validation import InputError
    N = len(spec.stages)
    centre = list(spec.dv_fractions) if spec.dv_fractions else [1.0 / N] * N
    centre = [c / sum(centre) for c in centre]
    table, memory = LossMap(), Memory()

    def fly_at(fr):
        s = copy.deepcopy(spec)
        s.dv_mode, s.dv_fractions, s.dv_fixed = "fractions", list(fr), None
        loss = memory.loss or first_guess(s)
        for _ in range(2):                                 # the loss hardly depends on the size: two passes settle it
            try:
                res = size_vehicle(with_loss(s, loss), keep_history=False)
            except (SizingError, InputError):
                return
            if not res.converged:
                return
            new, _o = flown(res, memory)
            if new is None or new > RUNAWAY_MPS:
                table.add(fr, None)
                return
            loss = new
        memory.loss = loss
        table.add(fr, loss)

    for fr in sample_splits(N, centre, 8 if N == 2 else 10):
        fly_at(fr)
    if not any(v is not None for v in table.y):
        raise SizingError("none of the stage splits tried gives a vehicle that both sizes and flies, so there are no losses "
                          "to optimise with", field="mission.losses.model",
                          options=[{"label": "Use the book's loss regression instead", "path": "mission.losses.model",
                                    "value": "book_penalty"}])
    out = None
    for _ in range(rounds):
        s = copy.copy(spec)
        s.mission = dict(spec.mission, simulated_loss_map=table)
        out = optimise(s, **kw)
        if not out.get("success", True) or not out.get("fractions"):
            return out
        expected = table(out["fractions"])
        n0 = len(table.y)
        fly_at(out["fractions"])
        if len(table.y) > n0 and table.y[-1] is not None and abs(table.y[-1] - expected) < 10.0:
            break
    out["note"] = ((out.get("note") or "")
                   + f" Losses were flown at {len(table.y)} splits and interpolated between them.").strip()
    return out
