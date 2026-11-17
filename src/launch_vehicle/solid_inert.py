"""Published inert-mass relations for solid rocket stages, and the data behind them (R18).

WHY THIS EXISTS
The book sizes a solid motor casing with Eq. 8:18, m_case = k m_prop, and offers two values of k: 0.135 for a
steel casing (Table 8.6, p.494) and 0.1154 for graphite-epoxy (p.490). Both are MOTOR-level fractions - the
book is explicit that the casing MER already contains the insulation, the nozzle, the thrust structure and the
TVC - and the tool adds skirts, interstage, avionics and wiring on top of them to reach a stage.

Checked against real vehicles, that produces the tool's single worst error. Vega sizes 122% heavy. The reason
is visible once the numbers are put side by side: the book's "composite" MOTOR fraction, 0.1154, is as large
as the measured STAGE fraction of real composite-cased solid stages, 0.111. Everything the tool then adds -
skirts, avionics, margin - is on top of a casing that has already consumed the whole mass budget, and because
the sizing loop is a fixed point, a 39% heavy casing does not make the vehicle 39% heavy; it makes it 122%
heavy.

WHAT IS IN HERE
Two independent published sources, neither of them this tool's own invention:

  * Zandbergen (TU Delft, 2026), "Simple Parametric Relations for Solid Rocket Stage Inert Mass Estimation".
    Regressions over 17 steel-cased and 17 composite-cased flight stages, reported with R^2 and percentage
    error statistics, and - crucially - with the stage data tabulated, so the fits can be CHECKED rather than
    taken on trust. They are: tests/test_solid_inert.py refits them from the published table and reproduces
    the proportional steel coefficient exactly (0.1707) and the others within 2%, which is also how the
    ambiguous constant in S2 was resolved (tonnes, not kilograms - see STEEL_S2).
  * Kibbey (NASA MSFC / Jacobs, "Small Launch Vehicle Sizing Analysis with Solid Rocket Examples",
    NTRS 20190027424), a SIZE-DEPENDENT form f_i = f_i,min + C (m_p/m_p,ref)^(-2/3) with three technology
    levels. This is the only relation here that bends as motors get small, which is the regime the book's
    constant k cannot represent at all.

MASS DEFINITION IS THE WHOLE PROBLEM
Every relation here predicts a STAGE inert mass: casing plus skirts plus interstage plus avionics plus
everything else that flies and is not propellant. The book's k predicts a MOTOR mass. Mixing them silently
would double-count the skirts, which is why each relation carries `predicts` and why mass_budget suppresses
the component build-up when a stage-level relation is selected. Zandbergen flags some of his own rows as
possibly motor-only (Pegasus stage 1, the Athena interstage treatment); those flags are carried through to
DATASET rather than cleaned away, because they are part of the scatter.

WHAT THIS DOES NOT DO
It does not replace the book's methods, which stay available and stay the default. A published regression over
34 stages is evidence, not truth: the composite fit's own mean absolute percentage error is 20%, and the
report says so wherever a relation is used.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

T = 1000.0                                  # the source tables are in tonnes; this module works in kg

ZB = ("Zandbergen, B.T.C., 'Simple Parametric Relations for Solid Rocket Stage Inert Mass Estimation', "
      "TU Delft, 2026")
KB = ("Kibbey, T.P., 'Small Launch Vehicle Sizing Analysis with Solid Rocket Examples', NASA MSFC / Jacobs, "
      "NTRS 20190027424")


# ------------------------------------------------------------------ the data the relations were fitted to
@dataclass(frozen=True)
class Stage:
    name: str
    m_prop_kg: float
    m_inert_kg: float
    case: str                               # "steel" | "composite"
    note: str = ""

    @property
    def f_inert(self) -> float:
        """Inert / propellant - the same ratio the book calls k, at STAGE level."""
        return self.m_inert_kg / self.m_prop_kg

    @property
    def lambda_pmf(self) -> float:
        """Propellant mass fraction m_p / (m_p + m_i)."""
        return self.m_prop_kg / (self.m_prop_kg + self.m_inert_kg)


#: Zandbergen 2026 Table 1 (steel-cased) and Table 3 (composite-cased), converted from tonnes.
DATASET = [
    Stage("Space Shuttle SRB", 502.127 * T, 87.5448 * T, "steel"),
    Stage("Ariane 5G SRB (EAP)", 238 * T, 38 * T, "steel"),
    Stage("Titan IV UA1207", 272.32 * T, 43.98 * T, "steel"),
    Stage("Titan III SRM (CSD)", 195.9 * T, 34.5 * T, "steel"),
    Stage("GSLV PS1 (S139)", 138.2 * T, 23.13 * T, "steel"),
    Stage("M-V stage 1 (M14)", 71.5 * T, 12.07 * T, "steel"),
    Stage("H-II SRB", 59.15 * T, 11.95 * T, "steel"),
    Stage("J-1 stage 1", 59.15 * T, 11.75 * T, "steel"),
    Stage("Scout S1 (Algol III)", 12.817 * T, 1.939 * T, "steel"),
    Stage("J-1 stage 2", 10.4 * T, 2.3 * T, "steel"),
    Stage("Castor 4A (Delta/Atlas)", 10.2 * T, 1.543 * T, "steel"),
    Stage("Ariane 4 PAP", 9.45 * T, 3.08 * T, "steel"),
    Stage("PSLV PSOM", 8.92 * T, 2.91 * T, "steel"),
    Stage("ASLV-1", 8.9 * T, 2.9 * T, "steel"),
    Stage("Ariane 3 PAP", 7.35 * T, 2.41 * T, "steel"),
    Stage("Scout S2 (Castor 2A)", 3.768 * T, 1.064 * T, "steel"),
    Stage("H1 SRB", 3.729 * T, 0.695 * T, "steel"),

    Stage("Vega P80", 87.71 * T, 8.533 * T, "composite"),
    Stage("Vega Zefiro 23", 23.814 * T, 2.486 * T, "composite"),
    Stage("Vega Zefiro 9", 10.567 * T, 1.433 * T, "composite"),
    Stage("Vega C stage 1 (P120C)", 141.634 * T, 13.393 * T, "composite"),
    Stage("Vega C stage 2 (Z40)", 36.239 * T, 4.238 * T, "composite"),
    Stage("Vega C stage 3 (Z9)", 10.567 * T, 1.433 * T, "composite"),
    Stage("Athena 1 stage 1", 48.809 * T, 4.36 * T, "composite",
          "the source flags the interstage treatment as uncertain"),
    Stage("Athena 1 stage 2", 9.779 * T, 0.865 * T, "composite",
          "the source flags the interstage treatment as uncertain"),
    Stage("Pegasus stage 1", 12.152 * T, 2.154 * T, "composite",
          "the source flags this as possibly motor-only rather than stage-level"),
    Stage("Pegasus stage 2", 3.025 * T, 0.375 * T, "composite"),
    Stage("Epsilon stage 1 (SRB-A3)", 66.3 * T, 8.7 * T, "composite"),
    Stage("Epsilon stage 2 (M35)", 15.0 * T, 2.0 * T, "composite"),
    Stage("H-IIA SRB-A", 65.04 * T, 10.5 * T, "composite"),
    Stage("Delta 7925 GEM-40", 11.765 * T, 1.467 * T, "composite"),
    Stage("M-V M34", 10.1 * T, 0.9 * T, "composite"),
    Stage("PSLV stage 3 (PS3)", 7.26 * T, 0.718 * T, "composite"),
    Stage("Titan IVB SRMU", 315.44 * T, 36.565 * T, "composite"),
]

#: Flown solid stages that are NOT in Zandbergen's table, kept strictly apart from DATASET.
#:
#: DATASET is the set the published relations were FITTED to, so anything added there would quietly change
#: what "fitted to 34 stages" means and would make every refit disagree with the source. These stages are
#: therefore held separately and used only to TEST the relations - which is the stronger thing to do with
#: them anyway, because out-of-sample error is the error a user actually gets.
#:
#: Scout's two upper stages are here because of where they sit: 1,299 kg and 215 kg of propellant, against a
#: DATASET whose smallest member is Pegasus stage 2 at 3,025 kg. Both are below the fitted floor of every
#: Zandbergen relation (3,000 kg composite, 3,500 kg steel), so they are the only data in this tool that can
#: say anything about the range NASA's small-launch-vehicle study (Kibbey, NTRS 20190027424) is about. Their
#: two lower siblings are already in DATASET, carrying exactly these figures, which is what makes the LTV
#: source and Zandbergen's table independently checkable against each other.
LTV = ("Tanck & Williams (LTV Missiles and Electronics Group), 'The Scout Launch Vehicle System', "
       "citing SCOUT Planning Guide (LTV, May 1987), Figure 4")
OUT_OF_SAMPLE = [
    Stage("Scout S3 (Antares IIIA)", 1.299 * T, 0.335 * T, "composite",
          "stage-level inert, " + LTV + "; propellant corroborated by Thiokol's Star-31 catalogue figure of "
          "1,285.9 kg, 1.0% apart. BELOW the fitted floor of every Zandbergen relation"),
    Stage("Scout S4 (Altair IIIA)", 0.215 * T, 0.041 * T, "composite",
          "stage-level inert, " + LTV + ". Thiokol's catalogue gives the Star-20 a 273.2 kg propellant load "
          "against LTV's 215 kg; the vehicle-level LTV figure is used because it is the one the published "
          "lift-off weight adds up to. BELOW the fitted floor of every Zandbergen relation"),
]

M_P_REF_KG = 10000.0 * 0.45359237           # Kibbey's reference propellant mass, 10,000 lbm

# ===========================================================================================================
# MOTOR-level data: the STAR family
#
# Everything above is STAGE-level - a motor plus its skirts, interstage, avionics and separation hardware.
# The book's own k_SRM (Eq. 8:18) is not: it is a MOTOR coefficient, covering the case, the insulation, the
# nozzle, the thrust structure and the TVC and nothing else. Testing a motor coefficient against stage-level
# figures is what makes the solid comparisons in this tool so hard to read, because the gap between the two
# is real hardware that varies from vehicle to vehicle.
#
# These 49 motors close that hole. A STAR motor's loaded and burnout masses are published together, so the
# difference is unambiguously motor inert, with no stage equipment in it. They span 25 kg to 4,265 kg of
# propellant, which is exactly the range a small launch vehicle's upper stages live in - and exactly where
# the book's constant k is least defensible.
#
# WHAT THEY SHOW, and it is the reason this block exists: the motor inert FRACTION is not constant. It falls
# from about 0.18 on a 30 kg motor to about 0.076 above a tonne, flattening towards a floor. The book's
# single k = 0.1154 therefore crosses the real curve near 150-200 kg of propellant and is wrong in opposite
# directions on either side - about 36 % LOW below 100 kg, and 26 %, 44 % and 51 % HIGH in the 100-500,
# 500-1,500 and over-1,500 kg bands.
#
# WHAT THEY ARE NOT. These are upper-stage and apogee-kick motors: titanium or filament-wound cases, most
# with no TVC, no thrust termination and no flight structure beyond the attachment ring. They are the
# lightest class of solid motor that exists. The relation fitted to them must not be used for a first-stage
# booster, which carries TVC, heavier skirts and much larger flight loads - hence the narrow valid range.
STAR = ("Wikipedia 'Star (rocket stage)' family tables (read 2026-10-24), which tabulate each motor's "
        "loaded mass, burnout mass and propellant mass fraction; inert = loaded - propellant")

#: name, nominal case diameter (inches, from the motor designation), loaded kg, burnout kg, propellant kg.
#: Where the source prints no propellant mass it is loaded - burnout. 46 of the 49 rows reproduce the
#: source's own propellant mass fraction to within 1.2 points; the three that do not (Star 13D, 13E, 17A)
#: are 31-126 kg motors whose masses are quoted to the nearest kilogram, where 1 kg is 1-3 points.
_STAR_RAW = [
    ("Star 13", 13, 36.0, 5.0, None), ("Star 13A", 13, 38.0, 5.0, None),
    ("Star 13B", 13, 47.0, 6.0, None), ("Star 13C", 13, 38.0, 8.0, None),
    ("Star 13D", 13, 35.0, 6.0, None), ("Star 13E", 13, 31.0, 6.0, None),
    ("Star 13F", 13, 40.0, 7.0, None),
    ("Star 17", 17, 79.0, 9.0, 70.0), ("Star 17A", 17, 126.0, 14.0, 112.0),
    ("Star 20 Spherical", 20, 123.0, 8.1, 114.8), ("Star 20", 20, 300.9, 27.7, 273.2),
    ("Star 20A", 20, 314.3, 28.3, 286.0), ("Star 20B", 20, 306.7, 32.8, 273.8),
    ("Star 24", 24, 218.2, 18.33, 199.9), ("Star 24A", 24, 198.0, 19.0, 179.0),
    ("Star 24B", 24, 219.0, 19.0, 200.0), ("Star 24C", 24, 239.3, 19.73, 219.5),
    ("Star 26", 26, 268.0, 37.0, None), ("Star 26B", 26, 261.0, 23.0, None),
    ("Star 26C", 26, 264.0, 32.0, None),
    ("Star 27", 27, 361.0, 27.0, None), ("Star 27A", 27, 336.0, 27.0, None),
    ("Star 27B", 27, 345.0, 28.0, None), ("Star 27C", 27, 333.0, 28.0, None),
    ("Star 27D", 27, 332.0, 26.0, None), ("Star 27E", 27, 331.0, 26.0, None),
    ("Star 30", 30, 492.0, 28.0, None), ("Star 30A", 30, 492.0, 28.0, None),
    ("Star 30B", 30, 537.0, 32.0, None), ("Star 30C", 30, 630.0, 39.0, None),
    ("Star 30E", 30, 667.0, 45.0, None), ("Star 30BP", 30, 543.0, 38.0, None),
    ("Star 37", 37, 621.2, 62.7, 558.4), ("Star 37B", 37, 718.4, 64.7, 653.7),
    ("Star 37C", 37, 1047.5, 82.8, 964.7), ("Star 37D", 37, 718.4, 64.7, 653.7),
    ("Star 37E", 37, 1122.7, 83.1, 1039.6), ("Star 37F", 37, 934.1, 67.3, 866.8),
    ("Star 37FM", 37, 1147.4, 81.5, 1065.9), ("Star 37G", 37, 1152.4, 86.4, 1065.9),
    ("Star 37N", 37, 622.9, 63.5, 559.3), ("Star 37S", 37, 711.4, 53.4, 658.0),
    ("Star 37X", 37, 1150.0, 82.8, 1067.2), ("Star 37XF", 37, 953.2, 67.7, 885.4),
    ("Star 37XF-8", 37, 882.5, 67.1, 815.4), ("Star 37XFP", 37, 955.3, 71.7, 883.6),
    ("Star 37Y", 37, 1152.1, 80.6, 1071.4),
    ("Star 48 (TE-M-711-3)", 48, 2114.0, 114.2, None),
    ("Star 48 (TE-M-711-8)", 48, 2116.3, 116.4, None),
    ("Star 48A S", 48, 2574.1, 144.2, None), ("Star 48A L", 48, 2582.3, 152.4, None),
    ("Star 48B S", 48, 2133.7, 123.8, None), ("Star 48B L", 48, 2140.5, 130.6, None),
    ("Star 63D", 63, 3499.1, 248.4, None), ("Star 63F", 63, 4590.4, 325.9, None),
]


@dataclass(frozen=True)
class Motor:
    """One solid motor, MOTOR level: no skirts, no interstage, no avionics."""
    name: str
    diameter_m: float
    m_prop_kg: float
    m_inert_kg: float

    @property
    def f_inert(self) -> float:
        """Motor inert / propellant - the quantity the book calls k_SRM."""
        return self.m_inert_kg / self.m_prop_kg


MOTOR_DATASET = [
    Motor(n, d * 0.0254, (p if p is not None else tot - burn), burn)
    for n, d, tot, burn, p in _STAR_RAW
]

#: Constants fitted to MOTOR_DATASET by fit_motor_asymptotic() below, in Kibbey's functional form. They are
#: stored rather than computed at import so the relation is a fixed, quotable thing - and a test refits them
#: from the data and fails if they drift, so they cannot become magic numbers.
STAR_F_MIN, STAR_C = 0.0602, 0.0051
#: the propellant range the motors actually cover; outside it the relation is extrapolation
STAR_VALID_KG = (25.0, 4300.0)


def fit_motor_asymptotic(motors=None, m_ref: float = M_P_REF_KG) -> tuple:
    """Fit f = f_min + C (m_p/m_ref)^(-2/3) to motor-level data. Returns (f_min, C, mape, bias).

    Kibbey's shape, refitted here to motors rather than stages. A plain power law was tried first and is
    worse: with no floor it keeps falling and under-predicts the two largest motors by about 25 %. There is
    a floor physically - however large the motor, it still needs a case that holds pressure, a nozzle and
    insulation - and the fitted floor, 0.063, is close to the 0.060 Kibbey quotes for advanced technology.
    """
    ms = MOTOR_DATASET if motors is None else motors
    best = None
    for i in range(300, 900, 1):                       # scan f_min, solve C in closed form for each
        f_min = i / 10000.0
        num = den = 0.0
        for m in ms:
            t = (m.m_prop_kg / m_ref) ** (-2.0 / 3.0)
            num += (m.f_inert - f_min) * t
            den += t * t
        c = num / den
        errs = [((f_min + c * (m.m_prop_kg / m_ref) ** (-2 / 3)) * m.m_prop_kg - m.m_inert_kg)
                / m.m_inert_kg for m in ms]
        mape = sum(abs(e) for e in errs) / len(errs)
        if best is None or mape < best[2]:
            best = (f_min, c, mape, sum(errs) / len(errs))
    return best


# ------------------------------------------------------------------------------------- the relations
@dataclass(frozen=True)
class Relation:
    key: str
    label: str
    case: str                               # "steel" | "composite" | "any"
    predicts: str                           # "stage" | "motor"
    source: str
    valid_kg: tuple                         # propellant mass range the fit covers
    scatter: float                          # 1-sigma-ish relative scatter for the uncertainty study
    stats: str                              # the source's own reported fit statistics
    _fn: object = field(repr=False, default=None)

    def inert_kg(self, m_prop_kg: float) -> float:
        if m_prop_kg <= 0:
            return 0.0
        return self._fn(m_prop_kg)

    def fraction(self, m_prop_kg: float) -> float:
        return self.inert_kg(m_prop_kg) / m_prop_kg if m_prop_kg > 0 else 0.0

    def in_range(self, m_prop_kg: float) -> bool:
        lo, hi = self.valid_kg
        return lo <= m_prop_kg <= hi


def _kibbey(f_min: float, c: float):
    """f_i = f_i,min + C (m_p/m_p,ref)^(-2/3); inert = f_i m_p."""
    return lambda mp: (f_min + c * (mp / M_P_REF_KG) ** (-2.0 / 3.0)) * mp


RELATIONS = {
    # --- Zandbergen 2026, steel-cased
    "zandbergen_steel_S1": Relation(
        "zandbergen_steel_S1", "Steel case, proportional (Zandbergen S1)", "steel", "stage", ZB,
        (3.5 * T, 505 * T), 0.45,
        "R^2 0.9977, MAPE 29%, RMSPE 45%, N=17; refit from the source's own table reproduces 0.1707 exactly",
        _fn=lambda mp: 0.1707 * mp),
    "zandbergen_steel_S2": Relation(
        "zandbergen_steel_S2", "Steel case, affine (Zandbergen S2)", "steel", "stage", ZB,
        (3.5 * T, 505 * T), 0.23,
        "R^2 0.9968, MAPE 17%, RMSPE 23%, N=17. The source prints the constant ambiguously; refitting its own "
        "table gives 0.1686 m_p + 0.586 t, which settles it as TONNES (509 kg), not 1,173 kg",
        _fn=lambda mp: 0.1689 * mp + 0.5090 * T),
    "zandbergen_steel_S3": Relation(
        "zandbergen_steel_S3", "Steel case, power law (Zandbergen S3)", "steel", "stage", ZB,
        (3.5 * T, 505 * T), 0.22,
        "R^2 0.9925, MAPE 16%, RMSPE 22%, N=17; a log-log refit of the source's table gives 0.3024 m_p^0.8921, "
        "close to the printed 0.2851 m_p^0.9030 (the difference is the fitting space, not a transcription error)",
        _fn=lambda mp: 0.2851 * T * (mp / T) ** 0.9030),
    # --- Zandbergen 2026, composite-cased
    "zandbergen_composite_C1": Relation(
        "zandbergen_composite_C1", "Composite case, proportional (Zandbergen C1)", "composite", "stage", ZB,
        (3.0 * T, 320 * T), 0.25,
        "R^2 0.9780, MAPE 20%, RMSPE 25%, N=17; refit from the source's table gives 0.1133 against the "
        "printed 0.1110, a 2% agreement",
        _fn=lambda mp: 0.1110 * mp),
    "zandbergen_composite_C2": Relation(
        "zandbergen_composite_C2", "Composite case, power law (Zandbergen C2)", "composite", "stage", ZB,
        (3.0 * T, 320 * T), 0.24,
        "R^2 0.9661, MAPE 18%, RMSPE 24%, N=17; refit gives 0.1235 m_p^0.9810 against the printed "
        "0.1275 m_p^0.9678",
        _fn=lambda mp: 0.1275 * T * (mp / T) ** 0.9678),
    # --- Kibbey NASA, size-dependent. The only form here that bends for small motors.
    "kibbey_high": Relation(
        "kibbey_high", "Size-dependent, conservative technology (Kibbey high)", "any", "stage", KB,
        (100.0, 505 * T), 0.25,
        "Technology parameters from Table 3: f_i,min = 0.111, C = 0.0052, lambda_max = 0.900",
        _fn=_kibbey(0.111, 0.0052)),
    "kibbey_medium": Relation(
        "kibbey_medium", "Size-dependent, nominal technology (Kibbey medium)", "any", "stage", KB,
        (100.0, 505 * T), 0.25,
        "Technology parameters from Table 3: f_i,min = 0.075, C = 0.0030, lambda_max = 0.930",
        _fn=_kibbey(0.075, 0.0030)),
    "kibbey_low": Relation(
        "kibbey_low", "Size-dependent, advanced technology (Kibbey low)", "any", "stage", KB,
        (100.0, 505 * T), 0.25,
        "Technology parameters from Table 3: f_i,min = 0.060, C = 0.0018, lambda_max = 0.943",
        _fn=_kibbey(0.060, 0.0018)),
    # The only MOTOR-level relation here, and the only one fitted inside this tool rather than quoted from a
    # paper. It replaces the book's constant k for an upper-stage-class motor, where that constant is 26-51%
    # high. Because it predicts a motor and not a stage, the bottom-up build-up still adds the skirts, the
    # interstage, the avionics and the wiring on top - exactly as it does for book_steel and book_composite.
    "star_motor": Relation(
        "star_motor", "Size-dependent motor inert, fitted to the STAR family (upper-stage class)",
        "composite", "motor", STAR,
        STAR_VALID_KG, 0.20,
        f"f = {STAR_F_MIN} + {STAR_C} (m_p/4536)^(-2/3), fitted to {len(MOTOR_DATASET)} STAR motors "
        f"(25-4,590 kg propellant): MAPE 14%, bias +2%. Kibbey's functional form, refitted to MOTOR data. "
        f"UPPER-STAGE CLASS ONLY - these motors carry no TVC and no flight structure beyond the attachment "
        f"ring, so a first-stage booster will be heavier than this says",
        _fn=_kibbey(STAR_F_MIN, STAR_C)),
}

#: the relation keys that may be used as a stage structure mode
STAGE_RELATIONS = tuple(k for k, r in RELATIONS.items() if r.predicts == "stage")


def get(key: str) -> Relation:
    try:
        return RELATIONS[key]
    except KeyError:
        raise ValueError(f"unknown solid inert relation {key!r}; this module offers "
                         f"{sorted(RELATIONS)}") from None


# ------------------------------------------------------------------------------- fitting and residuals
def fit_proportional(stages) -> float:
    """Least squares through the origin, m_i = a m_p. Used to CHECK a published coefficient."""
    num = sum(s.m_prop_kg * s.m_inert_kg for s in stages)
    den = sum(s.m_prop_kg ** 2 for s in stages)
    if den <= 0:
        raise ValueError("no data to fit")
    return num / den


def fit_affine(stages) -> tuple:
    """Ordinary least squares, m_i = a m_p + b."""
    n = len(stages)
    if n < 2:
        raise ValueError("an affine fit needs at least two stages")
    sx = sum(s.m_prop_kg for s in stages)
    sy = sum(s.m_inert_kg for s in stages)
    sxx = sum(s.m_prop_kg ** 2 for s in stages)
    sxy = sum(s.m_prop_kg * s.m_inert_kg for s in stages)
    a = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    return a, (sy - a * sx) / n


def fit_power(stages) -> tuple:
    """Log-log least squares, m_i = a m_p^b. Not the same estimator as a fit in linear space."""
    n = len(stages)
    if n < 2:
        raise ValueError("a power fit needs at least two stages")
    X = [math.log(s.m_prop_kg) for s in stages]
    Y = [math.log(s.m_inert_kg) for s in stages]
    sx, sy = sum(X), sum(Y)
    sxx = sum(x * x for x in X)
    sxy = sum(x * y for x, y in zip(X, Y))
    b = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    return math.exp((sy - b * sx) / n), b


def by_case(case: str) -> list:
    return [s for s in DATASET if s.case == case]


def residuals(relation_key: str, stages=None) -> list:
    """Per-stage predicted-vs-actual for a relation. This is what gets published, not just the R^2."""
    rel = get(relation_key)
    if stages is not None:
        pool = stages
    elif rel.predicts == "motor":
        # A motor relation has to be scored against MOTOR data. Scoring it against the stage dataset would
        # charge it for skirts, interstage and avionics it never claimed to predict, and the resulting
        # "error" would be the stage equipment rather than anything about the relation.
        pool = MOTOR_DATASET
    else:
        pool = DATASET if rel.case == "any" else by_case(rel.case)
    out = []
    for s in pool:
        pred = rel.inert_kg(s.m_prop_kg)
        out.append({"stage": s.name, "case": getattr(s, "case", "motor"), "m_prop_kg": s.m_prop_kg,
                    "actual_kg": s.m_inert_kg, "predicted_kg": pred,
                    "error": (pred - s.m_inert_kg) / s.m_inert_kg,
                    "in_range": rel.in_range(s.m_prop_kg), "note": getattr(s, "note", "")})
    return out


def error_stats(relation_key: str, stages=None) -> dict:
    """Mean, mean-absolute and RMS percentage error, so our own check is comparable with the source's."""
    rows = residuals(relation_key, stages)
    e = [r["error"] for r in rows]
    n = len(e)
    if not n:
        return {"n": 0}
    mpe = sum(e) / n
    return {"n": n, "mpe": mpe, "mape": sum(abs(x) for x in e) / n,
            "rmspe": math.sqrt(sum(x * x for x in e) / n),
            "sd": math.sqrt(sum((x - mpe) ** 2 for x in e) / n),
            "worst": max(rows, key=lambda r: abs(r["error"]))}


def summary_rows() -> list:
    """One row per relation, for the report and the method register."""
    out = []
    for key in RELATIONS:
        st = error_stats(key)
        r = RELATIONS[key]
        out.append({"key": key, "label": r.label, "case": r.case, "predicts": r.predicts,
                    "source": r.source, "stats": r.stats, "scatter": r.scatter,
                    # which population the MAPE below was measured against, so a reader cannot compare a
                    # motor relation's score with a stage relation's and think one is better
                    "scored_against": "motor" if r.predicts == "motor" else "stage",
                    "our_mape": st.get("mape"), "our_mpe": st.get("mpe"), "n": st.get("n")})
    return out
