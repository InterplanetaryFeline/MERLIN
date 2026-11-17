"""Atmosphere models for the ascent trajectory (book Sec. 6.4.3, Eqs. 6:50 and 6:53).

The book uses a two-line exponential atmosphere and says so plainly: "it is expedient to use a simple exponential
atmosphere density model" (p.362). Density and ambient pressure both fall as exp(-h/h0) with a scale height of
7.64 km, which is all the trajectory needs for drag and for the pressure term of the thrust equation.

It is not all a drag *coefficient* needs. The book's own Cd curves (Figs. 6.9-6.13) are functions of Mach number,
and Mach needs a speed of sound, which needs a temperature - which the exponential model does not have. The book
never closes that gap. This module closes it with the US Standard Atmosphere 1976 layer model, marked
SUPPLEMENTARY throughout: it is a standard, not a book method.

So there are two models, and the choice is explicit:

    "book_exponential" (default)  density and pressure from Eqs. 6:50/6:53; temperature and speed of sound from
                                  US76, because the book's Cd(M) cannot be evaluated without them.
    "us76"                        every property from US Standard Atmosphere 1976, to 86 km geopotential.

Above the top of either model the air is treated as absent (zero density and pressure): at 86 km the density is
about 6e-6 of sea level and the drag force on a launch vehicle is already far below a newton per square metre of
frontal area, so the difference between "very thin" and "none" does not move a trajectory.
"""
from __future__ import annotations
import math
from dataclasses import dataclass

# ----------------------------------------------------------------------------- book exponential (Eqs. 6:50/6:53)
RHO0_KG_M3 = 1.225           # book p.362: density at h = 0 on Earth
P0_PA = 101325.0             # book p.363: surface pressure on Earth
SCALE_HEIGHT_M = 7640.0      # book p.362: "approximately 7.64 km on Earth"

# ----------------------------------------------------------------------------- US Standard Atmosphere 1976
# SUPPLEMENTARY: not a book model. Base of each layer: geopotential altitude [m], temperature [K], pressure [Pa],
# lapse rate [K/m]. Values are the defining constants of the 1976 standard.
R_AIR = 287.052874           # J/(kg K), specific gas constant for dry air
GAMMA_AIR = 1.4              # ratio of specific heats
G0_US76 = 9.80665            # m/s2, the standard gravity the model is defined with
R_EARTH_US76 = 6356766.0     # m, the effective Earth radius the geopotential conversion uses
_LAYERS = (
    # (h_base_geopotential_m, T_base_K, p_base_Pa, lapse_K_per_m)
    (0.0,     288.15,   101325.0,     -0.0065),
    (11000.0, 216.65,   22632.06,      0.0),
    (20000.0, 216.65,   5474.889,      0.001),
    (32000.0, 228.65,   868.0187,      0.0028),
    (47000.0, 270.65,   110.9063,      0.0),
    (51000.0, 270.65,   66.93887,     -0.0028),
    (71000.0, 214.65,   3.956420,     -0.002),
)
TOP_GEOPOTENTIAL_M = 84852.0     # the top of the 1976 model's lowest regime (86 km geometric)


@dataclass
class AirState:
    """Atmospheric properties at one altitude."""
    altitude_m: float
    density_kg_m3: float
    pressure_Pa: float
    temperature_K: float
    sound_speed_mps: float

    def mach(self, speed_mps: float) -> float:
        return speed_mps / self.sound_speed_mps if self.sound_speed_mps > 0 else float("inf")

    def dynamic_pressure_Pa(self, speed_mps: float) -> float:
        return 0.5 * self.density_kg_m3 * speed_mps * speed_mps


def geopotential_m(h_geometric_m: float) -> float:
    """Geometric to geopotential altitude, the independent variable US76 is tabulated against."""
    return R_EARTH_US76 * h_geometric_m / (R_EARTH_US76 + h_geometric_m)


def us76(h_geometric_m: float) -> AirState:
    """US Standard Atmosphere 1976 up to 86 km geometric. SUPPLEMENTARY - not a book model."""
    h = geopotential_m(max(h_geometric_m, 0.0))
    if h >= TOP_GEOPOTENTIAL_M:
        return AirState(h_geometric_m, 0.0, 0.0, 186.87, math.sqrt(GAMMA_AIR * R_AIR * 186.87))
    hb, Tb, pb, lapse = _LAYERS[0]
    for layer in _LAYERS:
        if h >= layer[0]:
            hb, Tb, pb, lapse = layer
        else:
            break
    dh = h - hb
    if lapse == 0.0:
        T = Tb
        p = pb * math.exp(-G0_US76 * dh / (R_AIR * Tb))
    else:
        T = Tb + lapse * dh
        p = pb * (T / Tb) ** (-G0_US76 / (lapse * R_AIR))
    rho = p / (R_AIR * T)
    return AirState(h_geometric_m, rho, p, T, math.sqrt(GAMMA_AIR * R_AIR * T))


def book_exponential(h_geometric_m: float, rho0=RHO0_KG_M3, p0=P0_PA, h0=SCALE_HEIGHT_M) -> AirState:
    """Book Eqs. 6:50 and 6:53: rho = rho0 exp(-h/h0), P = P0 exp(-h/h0), h0 = 7.64 km.

    The temperature and speed of sound come from US76 (SUPPLEMENTARY), because the exponential model has none and
    the book's own Cd curves are functions of Mach number.
    """
    h = max(h_geometric_m, 0.0)
    std = us76(h)
    k = math.exp(-h / h0)
    return AirState(h_geometric_m, rho0 * k, p0 * k, std.temperature_K, std.sound_speed_mps)


MODELS = {"book_exponential": book_exponential, "us76": us76}


def air(h_geometric_m: float, model: str = "book_exponential") -> AirState:
    """Atmospheric state at an altitude, by model name."""
    try:
        return MODELS[model](h_geometric_m)
    except KeyError:
        raise ValueError(f"unknown atmosphere model '{model}' (use {' or '.join(MODELS)})") from None


def gravity_mps2(h_geometric_m: float, g0: float = 9.80665, r_planet_m: float = 6378e3) -> float:
    """Book Eq. 6:31 / Table 6.1: g(h) = g0 / (1 + h/Rp)^2."""
    return g0 / (1.0 + h_geometric_m / r_planet_m) ** 2


def scale_height_from_models(h_m: float = 10000.0) -> float:
    """The scale height that makes the exponential model match US76 density at `h_m`.

    Reported, never used: it is how far the book's single 7.64 km scale height is from the standard atmosphere at
    the altitudes that matter for drag, and the trajectory report prints it so the reader can judge the
    approximation rather than take it on faith.
    """
    rho = us76(h_m).density_kg_m3
    return -h_m / math.log(rho / RHO0_KG_M3) if rho > 0 else float("nan")
