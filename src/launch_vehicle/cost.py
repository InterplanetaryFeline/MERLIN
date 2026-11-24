"""Development, production and per-flight cost, in work-years first (book Chapter 17 and Koelle's TRANSCOST 7.2).

Two sources
-----------
* Edberg & Costa, Chapter 17 ("the book"), which introduces TRANSCOST and prints its five development CERs,
  Figs. 17.12-17.16, one worked verification (Ariane 5, Table 17.4) and a table of real prices (Table 17.5).
* Koelle, *Handbook of Cost Engineering*, TCS-TR-184, TRANSCOST 7.2, 2007 ("Koelle"), the model itself. The book
  defers to it as reference [15] for the factor values, the production submodel, the learning factor and the
  operations model. Page numbers below are its printed ones, and every relation was read off the page image.

The five development CERs are the same in both, work-years against a reference mass, each multiplied by f1
(development status), f2 (technical quality), f3 (team experience) and, for the region, f8 (productivity):

    H_ES = 16.3  M^0.54   solid motors            motor net mass        Koelle p.34
    H_EL = 277   M^0.48   turbopump engines       ONE engine's mass     Koelle p.37
    H_EP = 167   M^0.35   pressure-fed engines    ONE engine's mass     Koelle p.42
    H_VR = 10.4  M^0.60   solid boosters          one booster's net mass  Koelle p.47
    H_VS = 100   M^0.555  expendable stages       dry mass WITHOUT engines  Koelle p.52

The programme is the sum of the elements times f0 = 1.04^N, N stages (Koelle p.28). Table 17.4's "f0 = 1.04" with a
superscript 3 was once transcribed here as 1.043, which made every three-stage programme 7 % too cheap.

Table 17.4 and its misprints: Koelle's own Table 2-V (p.104) is the original. The book's copy drops the 2,400 kg
shroud from the core's reference mass and the 1,300 kg equipment bay from the third stage's, prints the SRB's CER
value as 5,398 for 5,938, and the core's f1 as 1.6 for 1.1. With Koelle's values all five rows close.

Production (Koelle ch. 3): the first unit's cost, times the learning reduction f4 averaged over the units built,
times f0^N with f0 between 1.02 and 1.03. Operations (ch. 4): preflight ground work and launch and mission work.
Indirect cost has no CER; Koelle gives it as 8 to 15 % of the cost per flight (p.180).

What is not modelled: reuse and refurbishment, propellants (about 0.3 % of a Falcon 9 launch, book p.1013),
transport, insurance, profit, schedule slips and the customer agency's own cost (22-27 % on top, Koelle p.30).

Accuracy: Koelle quotes +/- 15 to 20 % for the reference data (p.13) and the book +/- 20 % (p.998). Both describe
government programmes run conventionally; Koelle puts commercial developments at 20 to 50 % of that (pp.94-95).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

LB_PER_KG = 2.2046226218


@dataclass(frozen=True)
class CER:
    code: str
    name: str
    a: float
    x: float
    mass_basis: str
    figure: str

    def effort_wyr(self, mass_kg: float) -> float:
        """Eq. 17.3 in work-years."""
        return self.a * mass_kg ** self.x if mass_kg > 0 else 0.0


# Book Figs. 17.12-17.16, pp.1003-1005; the same in Koelle, pp.34, 37, 42, 47 and 52.
CERS = {c.code: c for c in (
    CER("ES", "Solid-propellant motor development", 16.3, 0.54, "motor net mass", "Fig. 17.12, p.1003"),
    CER("EL", "Liquid engine development (turbopump)", 277.0, 0.48, "one engine's dry mass", "Fig. 17.13, p.1003"),
    CER("EP", "Pressure-fed engine development", 167.0, 0.35, "one engine's dry mass", "Fig. 17.14, p.1004"),
    CER("VR", "Solid-propellant booster development", 10.4, 0.60, "one booster's net mass", "Fig. 17.15, p.1004"),
    CER("VS", "Expendable vehicle development", 100.0, 0.555, "vehicle dry mass without engines",
        "Fig. 17.16, p.1005"),
)}

#: first-unit production CERs: code -> (a, x, Koelle page)
PRODUCTION_CERS = {
    "solid": (2.3, 0.399, "Koelle p.125"),                  # motors and boosters, propellant included
    "engine_cryo": (5.16, 0.45, "Koelle p.129"),            # LH2 engines
    "engine_storable": (1.9, 0.535, "Koelle p.129"),        # every other bipropellant engine
    "vehicle_cryo": (1.30, 0.65, "Koelle p.134"),           # LH2 stages
    "vehicle_storable": (0.83, 0.65, "Koelle p.133"),       # every other liquid stage
}

#: dollars per US aerospace work-year: Koelle Table 1-II, p.19 (2007 is his estimate), and the book's Table 17.3 for 2010
WORK_YEAR_USD = {
    1960: 26_000, 1961: 27_000, 1962: 28_000, 1963: 29_000, 1964: 30_000, 1965: 31_000, 1966: 32_300, 1967: 33_200,
    1968: 34_300, 1969: 36_000, 1970: 38_000, 1971: 40_000, 1972: 44_000, 1973: 50_000, 1974: 55_000, 1975: 59_500,
    1976: 66_000, 1977: 72_000, 1978: 79_700, 1979: 86_300, 1980: 92_200, 1981: 98_770, 1982: 105_300,
    1983: 113_000, 1984: 120_800, 1985: 127_400, 1986: 132_400, 1987: 137_700, 1988: 143_500, 1989: 150_000,
    1990: 156_200, 1991: 162_500, 1992: 168_200, 1993: 172_900, 1994: 177_200, 1995: 182_000, 1996: 186_900,
    1997: 191_600, 1998: 197_300, 1999: 203_000, 2000: 208_700, 2001: 214_500, 2002: 220_500, 2003: 226_400,
    2004: 232_100, 2005: 240_000, 2006: 246_000, 2007: 252_000, 2010: 296_000}
WORK_YEAR_REFERENCE_YEAR = 2010

INFLATION_PER_YEAR = 0.031          # Eq. 17.1: I_f = 1.031^n, the CPI average 1926-1992
SYSTEM_ENGINEERING_F0 = 1.04        # per stage: f0 = 1.04^N, Koelle p.28 and the book's Table 17.4
PRODUCTION_F0 = 1.025               # per stage: "between 1.02 and 1.03", Koelle p.124
TRANSCOST_ACCURACY = 0.20           # "usually within +/- 20%" (book p.998)
WORK_HOURS_PER_YEAR = 2080          # book p.986
INDIRECT_SHARE = 0.115              # of the cost per flight; "8 to 15 %", Koelle p.180: the middle
OPERATIONS_LEARNING = 0.90          # "0.85 to 0.95", Koelle p.158, and only from 6 launches a year

#: productivity factor f8, Koelle Table 1-IV, p.21 (1980-99 values)
REGIONS = {"USA": 1.00, "Europe": 0.86, "France": 0.77, "Germany": 0.77, "Japan": 0.70, "Russia": 2.11,
           "China": 1.34}
#: assembly mode factor f_c, Koelle p.158
ASSEMBLY = {"vertical_on_pad": (1.0, "Vertical, on the launch pad"),
            "vertical_then_move": (0.7, "Vertical, then moved to the pad"),
            "horizontal": (0.5, "Horizontal, then moved and erected")}

# Book Sec. 17.5.3, p.995: the chapter's own rules of thumb for an initial estimate.
RULE_OF_THUMB_USD_PER_LB = 5_000.0
RULE_OF_THUMB_RANGE_USD_PER_LB = (2_000.0, 120_000.0)

#: Ariane 5: Koelle Table 2-V, p.104, the original of the book's Table 17.4 (p.1007).
ARIANE5_FACTORS = {
    "SRB": dict(mass_kg=39_300, code="VR", f1=1.1, f2=None, f3=0.9, f8=0.86, wyr_cer=5_938, wyr=5_056),
    "Vehicle and shroud": dict(mass_kg=11_210 + 2_400, code="VS", f1=1.1, f2=1.16, f3=0.85, f8=0.86,
                               wyr_cer=19_692, wyr=18_368),
    "Vulcain engine": dict(mass_kg=1_685, code="EL", f1=1.1, f2=0.79, f3=0.9, f8=0.86,
                           wyr_cer=9_800, wyr=6_592),
    "Third stage and equipment bay": dict(mass_kg=1_200 + 1_300, code="VS", f1=0.9, f2=1.09, f3=0.9, f8=0.86,
                                          wyr_cer=7_689, wyr=5_838),
    "Aestus engine": dict(mass_kg=119, code="EP", f1=0.8, f2=None, f3=0.8, f8=0.77, wyr_cer=890, wyr=438),
}

# Book Table 17.5, pp.1010-1011, ca. 2013: real vehicles that state a LEO payload and a price per flight.
# (name, LEO payload kg, (low, high) price in millions of `currency`, work-years per flight or None, currency)
TABLE_17_5 = [
    ("Atlas V 401", 9_600, (130, 140), (420, 460), "USD"), ("Atlas V 431", 15_400, (140, 160), (460, 530), "USD"),
    ("Atlas V 551", 18_700, (165, 180), (550, 600), "USD"), ("Delta II 7320", 2_690, (75, 90), (250, 300), "USD"),
    ("Delta IV M", 8_100, (150, 150), (500, 500), "USD"), ("Delta IV M+4,2", 10_400, (170, 170), (570, 570), "USD"),
    ("Delta IV H", 23_000, (360, 360), (1200, 1200), "USD"), ("Falcon 1", 420, (8.9, 8.9), (57, 57), "USD"),
    ("Falcon 1e", 1_010, (10.9, 10.9), (62, 62), "USD"), ("Falcon 9", 10_450, (54, 59.5), (290, 290), "USD"),
    ("Minotaur", 600, (21, 24), (70, 80), "USD"), ("Pegasus XL", 450, (20, 25), (80, 100), "USD"),
    ("Taurus XL", 1_590, (45, 50), (150, 160), "USD"), ("Taurus II", 5_000, (45, 45), (150, 150), "USD"),
    ("Saturn IB (1963)", 15_000, (43, 43), (1500, 1500), "USD"),
    ("Saturn V (1974)", 127_000, (220, 220), (4280, 4280), "USD"),
    ("Space Shuttle", 24_000, (1250, 3000), (2200, 2200), "USD"),
    ("Ariane 5 ES", 21_000, (152, 160), (620, 650), "EUR"), ("Ariane 5 ECA", 25_000, (165, 175), (675, 720), "EUR"),
    ("CZ-2C Long March", 2_800, (25, 30), None, "USD"), ("CZ-2E/HO", 8_800, (60, 76), None, "USD"),
    ("Dnepr", 3_700, (12, 12), None, "USD"), ("H-IIA-202", 9_900, (16_000, 16_000), (540, 540), "JPY"),
    ("H-IIB", 19_000, (23_000, 23_000), (730, 730), "JPY"), ("ISRO GSLV", 4_500, (40, 40), None, "USD"),
    ("ISRO PSLV", 3_500, (32, 32), None, "USD"), ("Kosmos-3M", 1_400, (15, 15), None, "USD"),
    ("M-5", 1_850, (7_000, 7_000), (280, 280), "JPY"), ("Proton-K", 20_700, (100, 100), None, "USD"),
    ("Rockot", 1_850, (30, 30), None, "EUR"), ("Soyuz/Molniya", 6_200, (65, 65), None, "USD"),
    ("Soyuz-2 Kourou", 6_200, (75, 80), None, "EUR"), ("Tsyklon-3", 3_600, (30, 35), None, "USD"),
    ("Vega", 2_400, (50, 50), None, "EUR"), ("Zenit 2", 13_700, (120, 120), None, "USD"),
]

#: Fit of Table 17.5's work-years per flight against LEO payload, without the government-built Saturns and Shuttle.
#: SUPPLEMENTARY: the book draws the trend line (Fig. 17.17) and its +100 %/-50 % scatter but prints no equation.
TREND_A, TREND_X = 110.0, -0.387
TREND_BAND = (0.5, 2.0)

# ----------------------------------------------------------------------------- charts read off the page
#: reference net mass fraction k_ref against usable propellant [Mg], read off Koelle Figs. 2-28 and 2-29, pp.54-55
KREF_CRYO = [(7.0, 0.200), (8.3, 0.180), (13.5, 0.145), (21.0, 0.127), (45.0, 0.106), (107.0, 0.090),
             (155.0, 0.084), (420.0, 0.076), (800.0, 0.073), (1000.0, 0.0727)]
KREF_STORABLE = [(1.6, 0.320), (2.1, 0.260), (3.0, 0.222), (4.5, 0.180), (9.0, 0.120), (10.0, 0.115),
                 (18.0, 0.092), (30.0, 0.075), (45.0, 0.068), (90.0, 0.0565), (160.0, 0.049), (300.0, 0.0445),
                 (1000.0, 0.0390)]
#: learning factor p of stages at 2 and at 100 units a year against unit mass, read off Koelle Fig. 3-07, p.120
STAGE_LEARNING = [(1.0, 0.852, 0.734), (10.0, 0.878, 0.767), (100.0, 0.904, 0.800), (1_000.0, 0.931, 0.833),
                  (10_000.0, 0.956, 0.865), (100_000.0, 0.981, 0.900)]


def _interp_log(table, x):
    """Linear in log x between the tabulated points, held at the ends. Returns (value, inside the table)."""
    if x <= table[0][0]:
        return table[0][1], x == table[0][0]
    if x >= table[-1][0]:
        return table[-1][1], x == table[-1][0]
    for (x0, y0), (x1, y1) in zip(table, table[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * math.log(x / x0) / math.log(x1 / x0), True
    raise AssertionError("unreachable")


def net_mass_fraction_reference(prop_kg: float, cryo: bool) -> tuple:
    """(k_ref, inside the chart) for a stage with `prop_kg` of usable propellant."""
    return _interp_log(KREF_CRYO if cryo else KREF_STORABLE, prop_kg / 1000.0)


def stage_learning_factor(mass_kg: float, per_year: float) -> float:
    """p of a stage, Koelle Fig. 3-07."""
    lo = _interp_log([(m, a) for m, a, _b in STAGE_LEARNING], max(mass_kg, 1.0))[0]
    hi = _interp_log([(m, b) for m, _a, b in STAGE_LEARNING], max(mass_kg, 1.0))[0]
    r = min(max(per_year, 2.0), 100.0)
    return lo + (hi - lo) * math.log(r / 2.0) / math.log(50.0)


def engine_learning_factor(mass_kg: float, per_year: float) -> float:
    """p of an engine, Koelle Fig. 3-15, p.130: parallel straight lines against the log of the rate."""
    m = min(max(mass_kg, 10.0), 10_000.0)
    at_100 = 0.715 + 0.110 * math.log10(m / 10.0) / 3.0
    r = min(max(per_year, 1.0), 100.0)
    return min(at_100 + 0.1275 * (2.0 - math.log10(r)), 1.0)


def learning_average(p: float, n: int) -> float:
    """f4: mean cost of units 1 to n over the first unit's, each doubling costing p times as much (Koelle p.118)."""
    n = max(int(n), 1)
    b = math.log(p) / math.log(2.0)
    if n <= 5000:
        return sum(k ** b for k in range(1, n + 1)) / n
    head = sum(k ** b for k in range(1, 5001))
    return (head + ((n + 0.5) ** (b + 1) - 5000.5 ** (b + 1)) / (b + 1)) / n


def learning_of_batch(p: float, first: int, last: int) -> float:
    """f4 of units `first` to `last` of a running production."""
    b = math.log(p) / math.log(2.0)
    return sum(k ** b for k in range(first, last + 1)) / (last - first + 1)


def engine_quality_factor(firings: float) -> float:
    """f2 of a pump-fed engine from its qualification firings: 0.026 (ln N_Q)^2, 1.0 near 500 (Koelle p.40)."""
    return 0.026 * math.log(firings) ** 2


def typical_development_years(wyr: float) -> float:
    """Years to first flight that suit an effort of this size, from Koelle's three ranges on p.92."""
    return _interp_log([(10_000.0, 5.5), (20_000.0, 6.5), (42_500.0, 7.5)], max(wyr, 1.0))[0]


def inflate(amount: float, from_year: int, to_year: int) -> float:
    """Eq. 17.1: I_f = 1.031^n, n years since the reference year."""
    return amount * (1.0 + INFLATION_PER_YEAR) ** (to_year - from_year)


def work_year_usd(year: int) -> tuple:
    """Dollars per work-year in `year`, and how it was obtained."""
    if year in WORK_YEAR_USD:
        src = "book Table 17.3" if year == 2010 else "Koelle Table 1-II, p.19"
        return float(WORK_YEAR_USD[year]), f"{src}, entry for {year}"
    known = sorted(WORK_YEAR_USD)
    if known[0] < year < known[-1]:
        y0 = max(y for y in known if y < year)
        y1 = min(y for y in known if y > year)
        f = (year - y0) / (y1 - y0)
        return (WORK_YEAR_USD[y0] ** (1 - f) * WORK_YEAR_USD[y1] ** f,
                f"interpolated between the {y0} and {y1} values")
    base = WORK_YEAR_REFERENCE_YEAR if year > known[-1] else known[0]
    return (inflate(WORK_YEAR_USD[base], base, year),
            f"the {base} value escalated by Eq. 17.1 at {INFLATION_PER_YEAR*100:.1f} %/yr")


def element_effort_wyr(code: str, mass_kg: float, f1: float = 1.0, f2: float | None = None,
                       f3: float = 1.0, f8: float = 1.0) -> dict:
    """One element's development effort: the CER, then the factors applied multiplicatively (Fig. 17.11)."""
    cer = CERS[code]
    raw = cer.effort_wyr(mass_kg)
    applied = raw
    for f in (f1, f2, f3, f8):
        if f is not None:
            applied *= f
    return dict(code=code, name=cer.name, mass_kg=mass_kg, wyr_cer=raw, wyr=applied,
                f1=f1, f2=f2, f3=f3, f8=f8, basis=cer.mass_basis, figure=cer.figure)


# ------------------------------------------------------------------------------------------------ inputs
#: what the Cost tab asks for. `mission.cost` in a design file holds the ones somebody set; the rest are these.
#: name -> (default, units, label, description, provenance)
INPUTS = {
    "region": ("USA", "-", "Where it is developed and built", "Sets the productivity factor f8 (Koelle Table 1-IV, "
               "p.21, 1980-99 values). Work-years are multiplied by it.", "assumed"),
    "launch_rate": (6.0, "1/yr", "Launches per year", "Spreads the launch team over the flights, and sets how fast "
                    "production learns", "assumed"),
    "total_flights": (60.0, "-", "Flights over the programme", "How many vehicles are built, so how far production "
                      "learning goes, and how many flights share the development", "assumed"),
    "development_years": (None, "yr", "Years to first flight", "Gives the average team size. Blank uses the range "
                          "Koelle gives for an effort of this size (p.92)", "assumed"),
    "payload_utilisation": (0.7, "-", "Share of the payload capacity actually sold", "60 to 80 % is realistic "
                            "(book p.1009)", "reference"),
    "assembly": ("vertical_then_move", "-", "How the vehicle is assembled", "Sets the ground-operations factor "
                 "(Koelle p.158)", "assumed"),
}
ELEMENT_FIELDS = {"f1": "Development status f1", "f2": "Technical quality f2", "f3": "Team experience f3",
                  "existing": "Already developed"}
_ELEMENT_KEY = re.compile(r"^(stage\d+_(?:engine|vehicle|motor)|boosters)_(f1|f2|f3|existing)$")

F1_GUIDE = ("f1: 1.3-1.4 first of its kind, 1.1-1.2 new design with new features, 0.9-1.1 standard, "
            "0.7-0.9 modification, 0.4-0.6 minor variation (Koelle p.31)")
F3_GUIDE = ("f3: 1.3-1.4 new team, 1.1-1.2 partly new work, 1.0 some related experience, 0.8-0.9 has done similar, "
            "0.7-0.8 superior experience (Koelle p.32)")


class CostInputError(ValueError):
    def __init__(self, message, field=None):
        super().__init__(message)
        self.field = field


def known_input(key: str) -> bool:
    return key in INPUTS or bool(_ELEMENT_KEY.match(key))


def check_inputs(raw: dict | None) -> dict:
    """The settings as numbers, defaults filled in, anything impossible refused by name."""
    raw = {k: v for k, v in (raw or {}).items() if v is not None and v != ""}
    out = {k: d[0] for k, d in INPUTS.items()}
    for k, v in raw.items():
        if not known_input(k):
            raise CostInputError(f"there is no cost setting called '{k}'", k)
        if k == "region":
            if v not in REGIONS:
                raise CostInputError(f"the region must be one of {', '.join(REGIONS)}", k)
        elif k == "assembly":
            if v not in ASSEMBLY:
                raise CostInputError(f"the assembly mode must be one of {', '.join(ASSEMBLY)}", k)
        elif k.endswith("_existing"):
            v = v is True or str(v).lower() == "true"
        else:
            label = INPUTS[k][2] if k in INPUTS else k
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise CostInputError(f"'{label}' must be a number, not {v!r}", k) from None
            lo, hi = {"launch_rate": (0.1, 1000.0), "total_flights": (1.0, 100_000.0),
                      "development_years": (0.5, 40.0), "payload_utilisation": (0.05, 1.0)}.get(k, (0.1, 3.0))
            if not (math.isfinite(v) and lo <= v <= hi):
                raise CostInputError(f"'{label}' must be between {lo:g} and {hi:g}", k)
        out[k] = v
    return out


# ---------------------------------------------------------------------------------------------- estimate
@dataclass
class CostEstimate:
    elements: list = field(default_factory=list)
    year: int = 2010
    work_year_usd: float = 0.0
    work_year_source: str = ""
    f0: float = SYSTEM_ENGINEERING_F0               # the programme factor actually applied, 1.04^N
    n_stages: int = 0
    region: str = "USA"
    development_wyr: float = 0.0
    development_usd: float = 0.0
    development_years: float = 0.0
    development_years_from: str = ""
    average_team: float = 0.0
    production: list = field(default_factory=list)
    production_wyr: float = 0.0                     # one vehicle, averaged over the programme
    first_vehicle_wyr: float = 0.0
    ground_wyr: float = 0.0
    mission_wyr: float = 0.0
    indirect_wyr: float = 0.0
    flight_wyr: float = 0.0
    flight_usd: float = 0.0
    flight_wyr_with_development: float = 0.0
    wyr_per_tonne: float = 0.0
    wyr_per_tonne_utilised: float = 0.0
    trend_wyr: float | None = None                  # Table 17.5's trend, for a LEO payload
    trend_band_wyr: tuple = ()
    rule_usd: float = 0.0                           # $5,000 per pound
    rule_band_usd: tuple = (0.0, 0.0)
    usd_per_kg: float = 0.0
    comparables: list = field(default_factory=list)
    inputs: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)

    @property
    def per_flight_central_usd(self):
        return self.flight_usd

    def usd(self, wyr):
        return wyr * self.work_year_usd


def _engine_code(stage_spec) -> str:
    """Which engine CER applies. The book separates turbopump-fed from pressure-fed (Table 17.2)."""
    if getattr(stage_spec, "is_solid", False):
        return "ES"
    cycle = (getattr(getattr(stage_spec, "engine", None), "cycle", "") or "").lower()
    return "EP" if "pressure" in cycle else "EL"


def _is_cryo(fuel) -> bool:
    return str(fuel or "").upper().replace("-", "") in ("LH2", "H2")


def _engine_mass_kg(res, stage_index: int) -> float:
    """All the engines of one stage, from the ledger the mass build-up already produced."""
    want = ("Engines", "Engine gimbals")
    return sum(i.mass_kg for i in res.ledger if i.stage == stage_index and i.name in want)


def estimate(res, year: int = 2010, inputs: dict | None = None) -> CostEstimate:
    """Development effort element by element, then production, operations and cost per flight.

    Every factor not set is TRANSCOST's neutral value: f1 = f3 = 1. f2 of a liquid stage is computed from the sized
    stage (Koelle p.54) because without it "the large data spread would not allow to establish a CER" (p.53).
    """
    if inputs is None:
        inputs = (res.spec.mission.get("cost") if isinstance(res.spec.mission, dict) else None) or {}
    inp = check_inputs(inputs)
    out = CostEstimate(year=year, inputs=inp, region=inp["region"])
    out.work_year_usd, out.work_year_source = work_year_usd(year)
    f8 = REGIONS[inp["region"]]
    rate, flights = inp["launch_rate"], max(int(round(inp["total_flights"])), 1)
    extra_mass = res.fairing_mass_kg + res.paf_mass_kg
    b = res.boosters
    seen_engines = {}

    def opt(key, name, default):
        return inp.get(f"{key}_{name}", default)

    def add(key, element, code, mass, f2, note="", **kw):
        e = element_effort_wyr(code, mass, opt(key, "f1", 1.0), opt(key, "f2", f2), opt(key, "f3", 1.0), f8)
        e.update(key=key, element=element, note=note, existing=bool(opt(key, "existing", False)),
                 f2_computed=f2 is not None and f"{key}_f2" not in inp, **kw)
        if e["existing"]:
            e["wyr"] = 0.0
        out.elements.append(e)

    def make(element, kind, mass, n, p):
        a, x, page = PRODUCTION_CERS[kind]
        first = a * mass ** x * f8
        f4 = learning_average(p, n * flights)
        out.production.append(dict(element=element, kind=kind, mass_kg=mass, n=n, first_unit_wyr=first, p=p, f4=f4,
                                   wyr=n * first * f4, source=page))

    # Koelle's Table 2-V counts the shroud with the core vehicle, so it goes with the first liquid stage here, or with
    # the first stage when there is no liquid one.
    carrier = next((s.index for s in res.stages if not s.is_solid), 1)
    for s in res.stages:
        sp = res.spec.stages[s.index - 1]
        plus = extra_mass if s.index == carrier else 0.0
        note = "with the fairing and payload adapter" if plus > 0 else ""
        k = s.index
        if s.is_solid:
            add(f"stage{k}_motor", f"Stage {k} solid motor", "ES", s.m_dry_kg + plus, None, note)
            make(f"Stage {k} solid motor", "solid", s.m_dry_kg + plus, 1,
                 stage_learning_factor(s.m_dry_kg + plus, rate))
            continue
        n_eng = int(s.envelope.n) if s.envelope is not None else int(sp.engine.n_engines)
        eng_all = _engine_mass_kg(res, k)
        eng = eng_all / max(n_eng, 1)
        dry = max(s.m_dry_kg - eng_all, 0.0)
        cryo = _is_cryo(sp.fuel)
        if eng > 0:
            same = sp.engine.db_entry and seen_engines.get(sp.engine.db_entry)
            if same:
                add(f"stage{k}_engine", f"Stage {k} engine", _engine_code(sp), eng, None,
                    f"the same engine as stage {same}, developed once")
                out.elements[-1]["wyr"], out.elements[-1]["existing"] = 0.0, True
            else:
                add(f"stage{k}_engine", f"Stage {k} engine", _engine_code(sp), eng, None,
                    f"one of {n_eng}" if n_eng > 1 else "")
            if sp.engine.db_entry:
                seen_engines.setdefault(sp.engine.db_entry, k)
            make(f"Stage {k} engine", "engine_cryo" if cryo else "engine_storable", eng, n_eng,
                 engine_learning_factor(eng, n_eng * rate))
        if dry > 0:
            usable = s.m_prop_mission_kg + s.m_startup_kg
            k_eff = (dry + s.m_residual_kg + s.m_margin_prop_kg) / usable if usable > 0 else 0.0
            k_ref, inside = net_mass_fraction_reference(usable, cryo)
            # below the chart there is no reference to compare with, so f2 stays neutral; above it the curve is nearly
            # flat and Koelle himself plots S-IC just past its end
            below = usable / 1000.0 < (KREF_CRYO if cryo else KREF_STORABLE)[0][0]
            f2 = k_ref / k_eff if k_eff > 0 and not below else None
            add(f"stage{k}_vehicle", f"Stage {k} vehicle", "VS", dry + plus, f2,
                (note + "; " if note and not inside else note)
                + ("" if inside else "too small for Koelle's f2 chart, so f2 = 1" if below else
                   "propellant load is above Koelle's f2 chart, so its end value is used"),
                k_eff=k_eff, k_ref=k_ref)
            make(f"Stage {k} vehicle", "vehicle_cryo" if cryo else "vehicle_storable", dry + plus, 1,
                 stage_learning_factor(dry + plus, rate))
    if b is not None and b.m_inert_each_kg > 0:
        m = b.m_inert_each_kg
        if b.kind == "liquid":
            add("boosters", "Strap-on booster (one unit)", "VS", m, None,
                "liquid: its engines are inside this mass and are not charged separately")
            make("Strap-on booster", "vehicle_cryo" if _is_cryo(res.spec.boosters.fuel) else "vehicle_storable", m,
                 b.n_total, stage_learning_factor(m, b.n_total * rate))
        else:
            # Fig. 2-21 covers large steered boosters of about 11 to 90 t; smaller ones are motors (Koelle pp.32-33)
            large = m >= 10_000.0
            add("boosters", "Strap-on booster (one unit)", "VR" if large else "ES", m, None,
                "" if large else "below the 10 t the booster CER covers, so the solid-motor CER")
            make("Strap-on booster", "solid", m, b.n_total, stage_learning_factor(m, b.n_total * rate))

    out.n_stages = len(res.stages) + (1 if b is not None else 0)
    out.f0 = SYSTEM_ENGINEERING_F0 ** out.n_stages
    out.development_wyr = out.f0 * sum(e["wyr"] for e in out.elements)
    out.development_usd = out.usd(out.development_wyr)
    if inp["development_years"]:
        out.development_years, out.development_years_from = inp["development_years"], "your figure"
    else:
        out.development_years = typical_development_years(out.development_wyr)
        out.development_years_from = "typical for this effort, Koelle p.92"
    out.average_team = out.development_wyr / out.development_years

    int_f0 = PRODUCTION_F0 ** out.n_stages
    out.production_wyr = int_f0 * sum(p["wyr"] for p in out.production)
    out.first_vehicle_wyr = int_f0 * sum(p["n"] * p["first_unit_wyr"] for p in out.production)

    # ---- operations, Koelle pp.157-158 and 164
    f4 = learning_average(OPERATIONS_LEARNING, flights) if rate >= 6.0 else 1.0
    fv, n_ops, q = [], 0.0, 0.0
    for s in res.stages:
        sp = res.spec.stages[s.index - 1]
        fv.append(0.3 if s.is_solid else 1.0 if _is_cryo(sp.fuel) else 0.8)
        n_ops += 1.0
        q += 0.15 if s.is_solid else 0.4
    if b is not None:
        large = b.kind == "liquid" or b.m_inert_each_kg >= 10_000.0
        n_ops += b.n_total * (1.0 if large else 0.5)
        q += b.n_total * (0.4 if large else 0.15)
        fv.append(0.3 if b.kind != "liquid" else 1.0 if _is_cryo(res.spec.boosters.fuel) else 0.8)
    out.ground_wyr = (8.0 * (res.glom_kg / 1000.0) ** 0.67 * rate ** -0.9 * n_ops ** 0.7 * (sum(fv) / len(fv))
                      * ASSEMBLY[inp["assembly"]][0] * f4 * f8)
    out.mission_wyr = 20.0 * q * rate ** -0.65 * f4 * f8
    direct = out.production_wyr + out.ground_wyr + out.mission_wyr
    out.flight_wyr = direct / (1.0 - INDIRECT_SHARE)
    out.indirect_wyr = out.flight_wyr - direct
    out.flight_usd = out.usd(out.flight_wyr)
    out.flight_wyr_with_development = out.flight_wyr + out.development_wyr / flights

    pl = res.payload_mass_kg
    if pl > 0:
        out.wyr_per_tonne = specific_transportation_cost_wyr_per_Mg(out.flight_wyr, pl)
        out.wyr_per_tonne_utilised = out.wyr_per_tonne / inp["payload_utilisation"]
        out.usd_per_kg = out.flight_usd / pl
        if str(res.spec.mission.get("orbit_type", "")).upper() == "LEO":
            out.trend_wyr = trend_wyr_per_flight(pl)
            out.trend_band_wyr = tuple(x * out.trend_wyr for x in TREND_BAND)
            out.comparables = comparable_vehicles(pl)
    pl_lb = pl * LB_PER_KG
    out.rule_usd = pl_lb * RULE_OF_THUMB_USD_PER_LB
    out.rule_band_usd = tuple(pl_lb * x for x in RULE_OF_THUMB_RANGE_USD_PER_LB)
    out.notes = _notes(out, res)
    return out


def trend_wyr_per_flight(payload_kg: float) -> float:
    t = payload_kg / 1000.0
    return TREND_A * t ** (1.0 + TREND_X)


def comparable_vehicles(payload_kg: float, band: float = 0.5) -> list:
    """Real vehicles from Table 17.5 whose LEO payload is within a factor of (1 +/- band) of this one's."""
    lo, hi = payload_kg * (1 - band), payload_kg * (1 + band)
    out = []
    for name, pl, cost_m, wyr, cur in TABLE_17_5:
        if lo <= pl <= hi:
            mid = 0.5 * (cost_m[0] + cost_m[1]) * 1e6
            out.append(dict(name=name, leo_kg=pl, currency=cur, price_low=cost_m[0] * 1e6, price_high=cost_m[1] * 1e6,
                            price_per_kg=mid / pl, wyr_per_flight=wyr))
    return sorted(out, key=lambda r: r["leo_kg"])


def _notes(out: CostEstimate, res) -> list:
    n = [f"Development is the sum of the elements times the systems-engineering factor f0 = 1.04^{out.n_stages} = "
         f"{out.f0:.3f} (one factor per stage{', strap-ons counting as one' if res.boosters is not None else ''}; "
         f"Koelle p.28). The model's own accuracy is \"usually within +/- {TRANSCOST_ACCURACY*100:.0f}%\" "
         f"(book p.998).",
         "TRANSCOST describes government programmes run conventionally. Koelle puts commercial developments at "
         "20 to 50 % of that (pp.94-95), so a company building its own vehicle may spend far less.",
         f"Work-years are for {out.region} (productivity factor f8 = {REGIONS[out.region]:.2f}). The dollars use the "
         f"US work-year, ${out.work_year_usd:,.0f} in {out.year} ({out.work_year_source})"
         + (", which is not what a work-year costs there" if out.region != "USA" else "") + ".",
         "f2 of each liquid stage is Koelle's reference net mass fraction over this stage's (pp.54-55), the reference "
         "read off his charts. A heavier stage than the reference has f2 below 1, because simple and heavy costs less "
         "to develop than light.",
         f"The cost per flight is production, ground and mission operations, plus "
         f"{INDIRECT_SHARE*100:.1f} % indirect (Koelle: 8 to 15 %, p.180). Learning factors are read off his charts. "
         f"Propellants, transport, insurance, profit and reuse are not included.",
         f"{F1_GUIDE}. {F3_GUIDE}."]
    if out.trend_wyr is None:
        n.append("The trend of real vehicles and the list of comparable ones are for LEO payloads, so they are not "
                 "shown for this orbit.")
    return n


def specific_transportation_cost_wyr_per_Mg(wyr_per_flight: float, payload_kg: float) -> float:
    """Book Sec. 17.6.4 and Fig. 17.17: work-years per tonne of payload, the cost-efficiency measure."""
    if payload_kg <= 0:
        return float("nan")
    return wyr_per_flight / (payload_kg / 1000.0)


def as_json(c: CostEstimate) -> dict:
    """Everything the Cost tab shows."""
    raw = sum(e["wyr"] for e in c.elements) or 1.0
    d = {k: getattr(c, k) for k in (
        "year", "work_year_usd", "work_year_source", "f0", "n_stages", "region", "development_wyr", "development_usd",
        "development_years", "development_years_from", "average_team", "production_wyr", "first_vehicle_wyr",
        "ground_wyr", "mission_wyr", "indirect_wyr", "flight_wyr", "flight_usd", "flight_wyr_with_development",
        "wyr_per_tonne", "wyr_per_tonne_utilised", "trend_wyr", "trend_band_wyr", "rule_usd", "rule_band_usd",
        "usd_per_kg", "comparables", "inputs", "notes", "production")}
    d["elements"] = [dict(e, share=e["wyr"] / raw) for e in c.elements]
    d["accuracy"] = TRANSCOST_ACCURACY
    d["per_flight_usd"] = c.flight_usd
    d["hours_per_year"] = WORK_HOURS_PER_YEAR
    d["input_defs"] = [dict(key=k, default=v[0], units=v[1], label=v[2], help=v[3]) for k, v in INPUTS.items()]
    d["regions"] = [[k, f"{k} (f8 = {v:.2f})"] for k, v in REGIONS.items()]
    d["assemblies"] = [[k, f"{lab} (x {f:g})"] for k, (f, lab) in ASSEMBLY.items()]
    d["f1_guide"], d["f3_guide"] = F1_GUIDE, F3_GUIDE
    return d
