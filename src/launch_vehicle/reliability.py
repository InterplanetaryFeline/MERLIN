"""Engine-cluster reliability and the engine-out case (R24, book Sec. 15.2.6, pp. 934-937).

The tool has always had `n_engines` as an input, and the default design's own comment says six engines
"gives one-engine-out T/W margin" - but nothing ever checked what that buys or costs. This module does.

THE BOOK'S METHOD, used as given
For n identical components in parallel of which k must work, the reliability of the cluster is the upper
tail of a binomial:

    R_s = sum(j = k..n) C(n,j) R^j (1-R)^(n-j)                                     (Sec. 15.2.6)

The book works two examples and they are the implementation's acceptance test: a 3-of-5 cluster of 95%
engines gives 99.88%, and a 7-of-9 cluster of the same engines gives 99.164%. The second being WORSE than
the first is the book's point and the one worth surfacing, because the tool's inputs quietly imply the
opposite: more engines looks like more redundancy, and it is only redundancy if the stage can actually fly
with one shut down.

WHERE THE PER-ENGINE NUMBERS COME FROM
Table 15.4 (p.936) tabulates flight statistics for six real engines as fails/uses. They are carried here as
the raw counts, not as the percentages the book prints, for one reason: two of the six rows have ZERO
failures, and the book reports those as "100%". No finite number of successes demonstrates a reliability of
1. What this module reports for a 0/207 record is the exact Clopper-Pearson lower confidence bound - 98.6%
at 95% confidence - beside the 100% point estimate, so a cluster calculation built on the Rutherford row
cannot silently assume perfection.

WHAT THIS DOES NOT DO
It is a cluster calculation over a single per-engine number. It says nothing about common-cause failures -
a shared propellant feed, a shared controller, debris from the engine that failed - and those dominate real
clusters. The independence assumption is the book's and it is stated wherever a result is reported. Nor is
engine reliability fed back into sizing: nothing here changes a mass or a dimension.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .units import G0


# --------------------------------------------------------------------------- the binomial machinery
def _comb(n: int, k: int) -> int:
    return math.comb(n, k)


def k_of_n(n: int, k: int, r: float) -> float:
    """Reliability of a cluster of n identical units of which at least k must succeed.

    R_s = sum(j = k..n) C(n,j) R^j (1-R)^(n-j)   - the book's Sec. 15.2.6 relation, unchanged.
    """
    if n <= 0:
        raise ValueError("a cluster needs at least one unit")
    if not (0 <= k <= n):
        raise ValueError(f"need 0 <= k <= n, got k={k}, n={n}")
    if not (0.0 <= r <= 1.0):
        raise ValueError(f"per-unit reliability must be in [0, 1], got {r}")
    return sum(_comb(n, j) * r ** j * (1.0 - r) ** (n - j) for j in range(k, n + 1))


def _binom_cdf(x: int, n: int, q: float) -> float:
    """P(X <= x) for X ~ Binomial(n, q)."""
    return sum(_comb(n, j) * q ** j * (1.0 - q) ** (n - j) for j in range(0, x + 1))


def lower_confidence_bound(fails: int, uses: int, confidence: float = 0.95) -> float:
    """Exact (Clopper-Pearson) one-sided lower bound on per-unit reliability from a flight record.

    The point estimate 1 - fails/uses is what the book prints. It is also 1.000 whenever a record happens to
    contain no failures, which is not a statement anyone should design against: 0 failures in 207 uses is
    consistent with a true reliability of 98.6%. This returns the largest reliability the record would
    support at the stated confidence, which for the zero-failure case reduces to (1 - c)^(1/n).
    """
    if uses <= 0:
        raise ValueError("a flight record needs at least one use")
    if not (0 <= fails <= uses):
        raise ValueError(f"fails must be in [0, uses], got {fails}/{uses}")
    if not (0.0 < confidence < 1.0):
        raise ValueError("confidence must be strictly between 0 and 1")
    if fails == 0:
        return (1.0 - confidence) ** (1.0 / uses)
    lo, hi = 0.0, 1.0                       # bisect on the failure probability q
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if _binom_cdf(fails, uses, mid) > 1.0 - confidence:
            lo = mid
        else:
            hi = mid
    return 1.0 - 0.5 * (lo + hi)


# ------------------------------------------------------------------------------- the published record
@dataclass(frozen=True)
class EngineRecord:
    name: str
    vehicle: str
    n_per_vehicle: int
    fails: int
    uses: int
    note: str = ""

    @property
    def point(self) -> float:
        """The book's own figure: 1 - fails/uses."""
        return 1.0 - self.fails / self.uses

    def bound(self, confidence: float = 0.95) -> float:
        return lower_confidence_bound(self.fails, self.uses, confidence)


#: Book Table 15.4 (p.936), "Selected Liquid-Propellant Engine Reliability", carried as the raw counts.
ENGINE_RECORDS = {
    "Merlin 1D": EngineRecord("Merlin 1D", "Falcon 9", 9, 1, 1278,
                              "as of 15 Jan 2022, 136 flights including three 27-engine Falcon Heavy flights"),
    "Rutherford": EngineRecord("Rutherford", "Electron", 9, 0, 207, "23 launches, Wikipedia 13 Jan 2022"),
    "RS-25": EngineRecord("RS-25", "Space Shuttle", 3, 1, 405, ""),
    "RD-180": EngineRecord("RD-180", "Atlas V", 1, 1, 86, ""),
    "RD-107/108": EngineRecord("RD-107/108", "Soyuz", 5, 1, 9500,
                               "'over 1,900' per Arianespace Sept 2019; the figure is for after year 2000"),
    "F-1": EngineRecord("F-1", "Saturn V", 5, 0, 65, ""),
}
TABLE_15_4 = "Book Table 15.4 (p.936), sources Everyday Astronaut March 2020 and Wikipedia"

#: What the book uses in its own two worked examples when it has no flight record.
EXAMPLE_R = 0.95


# ------------------------------------------------------------------------------------ the vehicle
def cluster(n: int, r: float, k_required: int | None = None) -> dict:
    """Reliability of one stage's engine cluster, all-must-work and one-out-tolerant side by side."""
    k_req = n if k_required is None else k_required
    out = {"n": n, "r_engine": r, "k_required": k_req,
           "all_must_work": k_of_n(n, n, r),
           "r_cluster": k_of_n(n, k_req, r)}
    out["one_out_tolerant"] = k_of_n(n, n - 1, r) if n >= 2 else None
    out["redundancy_gain"] = (out["one_out_tolerant"] - out["all_must_work"]
                              if out["one_out_tolerant"] is not None else None)
    return out


def engine_out_thrust_margin(res, stage_index: int) -> dict:
    """Can the stage still fly with one engine shut down, and what does the cluster reliability come to?

    The thrust-to-weight is recomputed at the stage's own ignition mass with one engine removed. For stage 1
    that is the question that decides whether the vehicle leaves the pad at all; for an upper stage, losing
    an engine lengthens the burn rather than ending the flight, and the result is reported as such.
    """
    sr = next(s for s in res.stages if s.index == stage_index)
    st = res.spec.stages[sr.index - 1]
    n = int(getattr(getattr(st, "engine", None), "n_engines", 0) or 1)
    first = stage_index == min(s.index for s in res.stages)
    m0 = sr.m_ignition_kg
    # the thrust the stage is judged on: sea level while it is still in the atmosphere, vacuum above it
    f_total = sr.thrust_sl_N if (first and sr.thrust_sl_N) else sr.thrust_vac_N
    per = f_total / n if n else 0.0
    tw = f_total / (m0 * G0) if m0 > 0 else 0.0
    tw_out = (f_total - per) / (m0 * G0) if (n >= 2 and m0 > 0) else 0.0
    return {"stage": stage_index, "n_engines": n, "is_first_stage": first,
            "thrust_total_N": f_total, "thrust_per_engine_N": per,
            "tw_nominal": tw, "tw_one_out": tw_out if n >= 2 else None,
            "lifts_off_one_out": (tw_out > 1.0) if (n >= 2 and first) else None,
            "can_lose_an_engine": bool(n >= 2 and (tw_out > 1.0 or not first)),
            "note": ("a first stage must still exceed T/W = 1 with one engine out or it does not leave the pad"
                     if first else
                     "an upper stage with an engine out burns longer rather than failing outright, at the "
                     "cost of extra gravity loss this tool does not re-fly")}


def analyse(res, r_engine: float | None = None, record: str | None = None,
            confidence: float = 0.95) -> dict:
    """Engine-out and cluster reliability for every stage of a sized vehicle.

    `record` names a row of Table 15.4 to take the per-engine reliability from; `r_engine` overrides it
    directly. With neither, the book's own example value of 0.95 is used and labelled as such, because
    inventing a reliability for an engine that does not exist yet would be worse than borrowing the book's.
    """
    src = f"assumed {EXAMPLE_R}, the value the book's own worked examples use (Sec. 15.2.6)"
    rec = None
    if record is not None:
        rec = ENGINE_RECORDS.get(record)
        if rec is None:
            raise ValueError(f"unknown engine record {record!r}; Table 15.4 holds {sorted(ENGINE_RECORDS)}")
        r = rec.point
        src = (f"{rec.name} on {rec.vehicle}: {rec.fails}/{rec.uses} = {r:.5f}. {TABLE_15_4}")
    elif r_engine is not None:
        r = r_engine
        src = f"user-specified per-engine reliability {r:.5f}"
    else:
        r = EXAMPLE_R

    stages = []
    for sr in res.stages:
        if getattr(sr, "is_solid", False):
            continue                        # a single cast motor is not a cluster
        margin = engine_out_thrust_margin(res, sr.index)
        n = margin["n_engines"]
        k_req = n if not margin["can_lose_an_engine"] else n - 1
        c = cluster(n, r, k_req)
        stages.append({**margin, **c})

    overall = 1.0
    for s in stages:
        overall *= s["r_cluster"]
    out = {"r_engine": r, "source": src, "confidence": confidence, "stages": stages,
           "propulsion_reliability": overall if stages else None,
           "independence_caveat": (
               "Engines are treated as independent, which is the book's assumption and not a true one: a "
               "shared feed system, a shared controller or debris from the engine that failed are common-cause "
               "failures this does not model. Treat the result as an upper bound.")}
    if rec is not None:
        out["record"] = {"name": rec.name, "vehicle": rec.vehicle, "fails": rec.fails, "uses": rec.uses,
                         "point": rec.point, "lower_bound": rec.bound(confidence), "note": rec.note,
                         "zero_failures": rec.fails == 0}
    return out


def records_table(confidence: float = 0.95) -> list:
    """Table 15.4 with the confidence bound the book does not print."""
    rows = []
    for r in ENGINE_RECORDS.values():
        rows.append({"engine": r.name, "vehicle": r.vehicle, "n_per_vehicle": r.n_per_vehicle,
                     "fails": r.fails, "uses": r.uses, "point": r.point,
                     "lower_bound": r.bound(confidence), "zero_failures": r.fails == 0, "note": r.note})
    return rows


def more_engines_sweep(r: float, n_max: int = 12, tolerate: int = 1) -> list:
    """System reliability against engine count, for a cluster that tolerates `tolerate` failures.

    This is the book's 3-of-5 versus 7-of-9 point generalised: adding engines adds failure opportunities as
    fast as it adds redundancy, so the curve is not monotonic in the way the word "redundancy" suggests.
    """
    out = []
    for n in range(1, n_max + 1):
        k = max(1, n - tolerate)
        out.append({"n": n, "k": k, "r_cluster": k_of_n(n, k, r), "all_must_work": k_of_n(n, n, r)})
    return out
