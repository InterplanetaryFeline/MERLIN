"""Rocket equation, structural-factor conventions and stage-propellant solutions.

PRIMARY CONVENTION (book Eq. 5:5a, p. 274):  s = m_s / (m_s + m_p)   (stage inert / stage inert + mission propellant,
payload EXCLUDED). 'Inert' here = everything that is on the stage at burnout other than carried upper mass:
dry hardware + residual propellant + loading margin. epsilon = m_s/m_p (Eq. 5:5b) is only used via the
conversions Eq. 5:91a/b. No other structural-coefficient definition is used inside the engine.

Verified book equations: 5:3 (rocket eq.), 5:4 (mass ratio), 5:13 (staging sum), 5:84-5:91 (sizing relations), pp. 274-322.
"""
from __future__ import annotations
import math
from .units import G0


class StagingError(ValueError):
    pass


def mass_ratio_from_dv(dv_mps: float, isp_s: float) -> float:
    """Eq. 5:84: mu = exp(dv/(g0 Isp))."""
    if isp_s <= 0:
        raise StagingError("Isp must be positive")
    return math.exp(dv_mps / (G0 * isp_s))


def delta_v(isp_s: float, m0: float, mf: float) -> float:
    """Eq. 5:3: dv = g0 Isp ln(m0/mf)."""
    if m0 <= mf or mf <= 0:
        raise StagingError(f"non-physical mass pair m0={m0}, mf={mf}")
    return G0 * isp_s * math.log(m0 / mf)


def eps_from_s(s: float) -> float:          # Eq. 5:91a
    return s / (1.0 - s)


def s_from_eps(eps: float) -> float:        # Eq. 5:91b
    return eps / (1.0 + eps)


def inert_from_propellant_s(m_p: float, s: float) -> float:
    """Eq. 5:90a: m_s = m_p s/(1-s)  (NOT s*m_p)."""
    return m_p * s / (1.0 - s)


def propellant_aggregate(m_carried: float, s: float, mu: float) -> float:
    """Eq. 5:85: m_p = m_PL (mu-1)(1-s)/(1-mu s), with m_PL = everything carried above the stage."""
    den = 1.0 - mu * s
    if den <= 0:
        raise StagingError(f"infeasible: mu*s = {mu*s:.3f} >= 1 (structure too heavy for this mass ratio; "
                           f"mu={mu:.3f}, s={s:.3f})")
    return m_carried * (mu - 1.0) * (1.0 - s) / den


def propellant_bottom_up(m_carried: float, m_dry: float, mu: float, f_unburned: float) -> float:
    """Mission propellant for a stage whose dry mass is known.

    Burnout mass  m_f = U + dry + f_unburned * m_p   (f_unburned = residual + loading-margin fractions of m_p)
    Rocket eq.    m_p = (mu - 1) m_f      =>   m_p = (mu - 1)(U + dry) / (1 - f_unburned (mu - 1))
    """
    den = 1.0 - f_unburned * (mu - 1.0)
    if den <= 0:
        raise StagingError(f"infeasible: unburned-propellant fraction {f_unburned:.3f} with mu={mu:.3f} "
                           "leaves no usable propellant")
    return (mu - 1.0) * (m_carried + m_dry) / den


def allocate_dv(total_dv: float, n: int, mode: str, fractions: list | None = None,
                fixed: list | None = None) -> list:
    """Stage delta-v allocation. 'fractions' normalised to 1; 'fixed' must sum to the total (within 1 m/s)
    or the last entry is treated as the remainder if None."""
    if mode == "fractions":
        if fractions is None or len(fractions) != n or any(f <= 0 for f in fractions):
            raise StagingError("dv_fractions must have one positive entry per stage")
        ssum = sum(fractions)
        return [total_dv * f / ssum for f in fractions]
    if mode == "fixed":
        if fixed is None or len(fixed) != n:
            raise StagingError("fixed stage delta-v list must have one entry per stage")
        vals = list(fixed)
        if vals[-1] is None:
            vals[-1] = total_dv - sum(vals[:-1])
        if any(v is None or v <= 0 for v in vals):
            raise StagingError("fixed stage delta-v entries must be positive")
        if abs(sum(vals) - total_dv) > 1.0:
            raise StagingError(f"fixed stage delta-v sum {sum(vals):.1f} m/s differs from requirement {total_dv:.1f} m/s")
        return vals
    raise StagingError(f"unknown allocation mode '{mode}'")
