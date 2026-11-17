"""Engine / propulsion relations.

Verified book references
------------------------
Eq. 4:18  c_eff = (1/3) c_SL + (2/3) c_vac            (p. 225)  -> effective-Isp weighting, selectable
Eq. 4:19  rocket equation                              (p. 225)
Eq. 4:23-4:26  T/W, T/W = mdot Isp / m0, mdot = m_p/t_b (p. 226)
Eq. 8:2   startup propellant = mdot * t_start          (p. 470)
Table 8.9 row 1  liquid pump-fed engine mass  m = T [7.81e-4 + 3.37e-5 sqrt(eps)] + 59   (p. 495)
Table 8.8 row 3  thrust-structure mass = 2.55e-4 T[N]  (p. 495; reproduces the book's 1,068 kg in Table 8.11)

mdot = F/(g0 Isp) is only used with a (thrust, Isp) pair that refer to the SAME operating condition.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from .units import G0


class PropulsionError(ValueError):
    pass


def effective_isp(isp_vac: float, isp_sl: float | None, mode: str, weight_sl: float = 1.0 / 3.0,
                  user_value: float | None = None) -> float:
    """Effective Isp used in the rocket equation for the stage's whole burn (explicit modelling assumption).

    mode 'vacuum'   : Isp_vac (appropriate for stages firing in vacuum).
    mode 'weighted' : w*Isp_SL + (1-w)*Isp_vac; book Eq. 4:18 uses w = 1/3 (c scales linearly with Isp).
    mode 'user'     : explicit user value.
    """
    if mode == "vacuum":
        return isp_vac
    if mode == "weighted":
        if isp_sl is None:
            raise PropulsionError("weighted effective Isp needs a sea-level Isp")
        if not 0.0 <= weight_sl <= 1.0:
            raise PropulsionError("sea-level weighting must be in [0, 1]")
        return weight_sl * isp_sl + (1.0 - weight_sl) * isp_vac
    if mode == "user":
        if user_value is None or user_value <= 0:
            raise PropulsionError("user effective Isp must be positive")
        return user_value
    raise PropulsionError(f"unknown effective-Isp mode '{mode}'")


def mass_flow(thrust_N: float, isp_s: float) -> float:
    """mdot = F / (g0 Isp); valid only when F and Isp refer to the same condition."""
    if thrust_N <= 0 or isp_s <= 0:
        raise PropulsionError("thrust and Isp must be positive")
    return thrust_N / (G0 * isp_s)


def thrust_from_mass_flow(mdot: float, isp_s: float) -> float:
    return mdot * G0 * isp_s


def burn_time(m_prop_kg: float, mdot_kgs: float) -> float:
    """Eq. 4:26 rearranged: t_b = m_p / mdot (average flow, constant-thrust assumption)."""
    return m_prop_kg / mdot_kgs


def thrust_to_weight(thrust_N: float, mass_kg: float) -> float:
    """T/W = T / (m g0) (Eq. 4:23)."""
    return thrust_N / (mass_kg * G0)


def startup_propellant(mdot_kgs: float, t_start_s: float) -> float:
    """Eq. 8:2: m_start = mdot * t_start."""
    return mdot_kgs * t_start_s


def engine_mass_mer(thrust_vac_N: float, expansion_ratio: float, coeffs: dict) -> float:
    """Table 8.9 row 1 (per engine): T[7.81e-4 + 3.37e-5 sqrt(eps)] + 59 kg. T = vacuum thrust of ONE engine, N."""
    return (thrust_vac_N * (coeffs["a"] + coeffs["b"] * math.sqrt(expansion_ratio)) + coeffs["c"])


def thrust_structure_mass(thrust_N: float, k: float) -> float:
    """Table 8.8 row 3: m = 2.55e-4 * T[N]."""
    return k * thrust_N


def engine_ring_radius(n: int, exit_diameter_m: float) -> float:
    """Radius of the pitch circle on which n engines of given exit diameter just touch (n>=2)."""
    if n <= 1:
        return 0.0
    return exit_diameter_m / (2.0 * math.sin(math.pi / n))


def cluster_fits(n: int, exit_diameter_m: float, stage_diameter_m: float, clearance_m: float = 0.0) -> bool:
    """Single ring packing check (n=1 centred). Not a substitute for a real engine-bay layout."""
    if n == 1:
        return exit_diameter_m + 2 * clearance_m <= stage_diameter_m
    return 2 * engine_ring_radius(n, exit_diameter_m) + exit_diameter_m + 2 * clearance_m <= stage_diameter_m


@dataclass
class PropEnvelope:
    """Outside dimensions of one stage's propulsion system, used for layout, drawing and clearance checks."""
    n: int
    length_m: float             # axial envelope of one engine (liquid) or of the protruding nozzle (solid)
    exit_diameter_m: float
    embed_fraction: float
    source: str
    dims: object = None         # EngineDimensions when computed from the book relations

    @property
    def protrusion_m(self) -> float:
        return self.length_m * (1.0 - self.embed_fraction)


def envelope(stage, thrust_vac_each_N: float) -> PropEnvelope:
    """Engine/nozzle envelope for a stage.

    geometry_method 'user'     : the length/exit diameter given in the configuration are used as-is.
    geometry_method 'book_mer' : computed from thrust, chamber pressure, expansion ratio, Isp and c* with
                                 book Eqs. 8:28-8:33 (liquid, full engine) or Eqs. 8:28/8:30 (solid, nozzle only).
    """
    from . import engine_geometry as eg
    p = stage.prop_system
    if stage.is_solid:
        n, method = 1, p.nozzle_geometry_method
    else:
        n, method = p.n_engines, getattr(p, "geometry_method", "user")
    if method == "user":
        L = p.nozzle_length_m if stage.is_solid else p.length_m
        D = p.exit_diameter_m
        if L is None or D is None:
            raise PropulsionError(f"stage {stage.index}: geometry_method 'user' needs an explicit nozzle length and exit diameter")
        return PropEnvelope(n, L, D, p.embed_fraction, "user-specified dimensions")
    if method != "book_mer":
        raise PropulsionError(f"stage {stage.index}: unknown geometry method '{method}'")
    if not p.cstar_mps:
        raise PropulsionError(f"stage {stage.index}: geometry_method 'book_mer' needs cstar_mps (Table 8.12 gives delivered c*)")
    if not p.chamber_pressure_Pa:
        raise PropulsionError(
            f"stage {stage.index}: geometry_method 'book_mer' sizes the engine from its chamber pressure, and "
            f"this stage has none. Either type a chamber pressure, or set the stage's geometry_method to "
            f"'user' and give the engine length and exit diameter directly. Some real engine rows do not "
            f"publish a chamber pressure, so naming a database engine does not always supply one.")
    if stage.is_solid:
        d = eg.nozzle_only_dimensions(thrust_vac_each_N, p.chamber_pressure_Pa, p.expansion_ratio, p.isp_vac_s, p.cstar_mps)
    else:
        d = eg.engine_dimensions(thrust_vac_each_N, p.chamber_pressure_Pa, p.expansion_ratio, p.isp_vac_s, p.cstar_mps)
    return PropEnvelope(n, d.overall_length_m, d.exit_diameter_m, p.embed_fraction, d.source, d)


def gimbal_mass_mer(thrust_engine_N: float, chamber_pressure_Pa: float, k: float, expo: float) -> float:
    """Table 8.9 row 2 (per engine): m = 237.8 (T/Pc)^0.9375, T in N, Pc in Pa.
    Units interpretation verified against the book's worked example (p. 505: 162 kg for six engines)."""
    if not chamber_pressure_Pa:
        raise PropulsionError(
            "the gimbal mass relationship is a function of thrust over chamber pressure, and this engine has "
            "no chamber pressure. Either type one, or set the stage's gimbal_method to 'user' and give the "
            "gimbal mass directly. Some real engine rows do not publish a chamber pressure.")
    return k * (thrust_engine_N / chamber_pressure_Pa) ** expo
