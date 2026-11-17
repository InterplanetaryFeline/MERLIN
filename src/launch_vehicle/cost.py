"""Development cost and cost per flight (book Chapter 17).

What this chapter gives, and what it keeps in its references
------------------------------------------------------------
Section 17.6.2 introduces TRANSCOST, whose cost-estimating relationships all have the form

    C = a M^x                                                                           Eq. 17.3

and prints five of them on Figs. 17.12-17.16, as development effort in work-years against a reference mass:

    H_ES = 16.3  M^0.54     solid-propellant motors          (motor net mass)
    H_EL = 277   M^0.48     liquid engines with turbopumps   (engine dry mass)
    H_EP = 167   M^0.35     pressure-fed engines             (engine dry mass)
    H_VR = 10.4  M^0.60     solid-propellant boosters        (booster net mass)
    H_VS = 100   M^0.555    expendable vehicles              (vehicle dry mass WITHOUT engines)

Those five are the whole of the cost model this book contains in equation form. The production submodel's
coefficients, the learning curve f4 and the operations model are all deferred to Koelle's TRANSCOST handbook,
reference [15], which is not in hand - so cost per flight here does NOT come from a CER. It comes from the
chapter's own rules of thumb (Sec. 17.5.3) and from its table of real launch prices (Table 17.5), and it is
reported as a range, which is what those sources support.

The f-factors
-------------
TRANSCOST multiplies each CER by development-status (f1), technical-quality (f2) and team-experience (f3)
factors, with a programme-level systems-engineering factor f0. The book describes what they mean and defers
their values to [15] as well, but Table 17.4 prints the set actually used for Ariane 5, so those are offered as
documented examples. They are inputs, and on a first-of-its-kind vehicle they move the answer by tens of
per cent.

Accuracy
--------
"Based on historical data, the accuracy of TRANSCOST is usually within +/- 20%" (p.998), and its estimates
"will almost always be higher than estimates derived from a bottom-up approach" because they include the cost
of unforeseen development problems.
"""
from __future__ import annotations

import math
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


# Book Figs. 17.12-17.16, pp.1003-1005. The labels are printed on the figures themselves.
CERS = {c.code: c for c in (
    CER("ES", "Solid-propellant motor development", 16.3, 0.54, "motor net mass", "Fig. 17.12, p.1003"),
    CER("EL", "Liquid engine development (turbopump)", 277.0, 0.48, "engine dry mass", "Fig. 17.13, p.1003"),
    CER("EP", "Pressure-fed engine development", 167.0, 0.35, "engine dry mass", "Fig. 17.14, p.1004"),
    CER("VR", "Solid-propellant booster development", 10.4, 0.60, "booster net mass", "Fig. 17.15, p.1004"),
    CER("VS", "Expendable vehicle development", 100.0, 0.555, "vehicle dry mass without engines",
        "Fig. 17.16, p.1005"),
)}

# Book Table 17.3, p.1002: the dollar value of one work-year. The 2010 US figure is the NASA reference value
# from 533 contracts, printed in bold.
WORK_YEAR_USD = {1970: 38_000, 1980: 92_200, 1990: 156_200, 1997: 191_600, 2000: 208_700, 2010: 296_000}
WORK_YEAR_REFERENCE_YEAR = 2010

INFLATION_PER_YEAR = 0.031          # Eq. 17.1: I_f = 1.031^n, the CPI average 1926-1992
SYSTEM_ENGINEERING_F0 = 1.043       # Table 17.4's programme-level factor for Ariane 5
TRANSCOST_ACCURACY = 0.20           # "usually within +/- 20%" (p.998)

# Book Sec. 17.5.3, p.995: the chapter's own rules of thumb for an initial estimate.
RULE_OF_THUMB_USD_PER_LB = 5_000.0
RULE_OF_THUMB_RANGE_USD_PER_LB = (2_000.0, 120_000.0)
RULE_OF_THUMB_PER_VEHICLE_USD = (6e6, 600e6)

# Book Table 17.4, p.1007: the factors actually used for Ariane 5, as worked examples of f1, f2, f3 and f8.
ARIANE5_FACTORS = {
    "SRB": dict(mass_kg=39_300, code="VR", f1=1.1, f2=None, f3=0.9, f8=0.86, wyr_cer=5_398, wyr=5_056),
    "Vehicle and shroud": dict(mass_kg=11_210, code="VS", f1=1.6, f2=1.16, f3=0.85, f8=0.86,
                               wyr_cer=19_692, wyr=18_368),
    "Vulcain engine": dict(mass_kg=1_685, code="EL", f1=1.1, f2=0.79, f3=0.9, f8=0.86,
                           wyr_cer=9_800, wyr=6_592),
    "Third stage and equipment bay": dict(mass_kg=1_200, code="VS", f1=0.9, f2=1.09, f3=0.9, f8=0.86,
                                          wyr_cer=7_689, wyr=5_838),
    "Aestus engine": dict(mass_kg=119, code="EP", f1=0.8, f2=None, f3=0.8, f8=0.77, wyr_cer=890, wyr=438),
}

# Book Table 17.5, pp.1010-1011, ca. 2013: real vehicles, their LEO payload and their price per flight.
# (name, LEO payload kg, cost per flight in millions of USD as a (low, high) range, work-years per flight)
TABLE_17_5 = [
    ("Atlas V 401", 9_600, (130, 140), (420, 460)), ("Atlas V 431", 15_400, (140, 160), (460, 530)),
    ("Atlas V 551", 18_700, (165, 180), (550, 600)), ("Delta II 7320", 2_690, (75, 90), (250, 300)),
    ("Delta IV M", 8_100, (150, 150), (500, 500)), ("Delta IV M+4,2", 10_400, (170, 170), (570, 570)),
    ("Delta IV H", 23_000, (360, 360), (1200, 1200)), ("Falcon 1", 420, (8.9, 8.9), (57, 57)),
    ("Falcon 1e", 1_010, (10.9, 10.9), (62, 62)), ("Falcon 9", 10_450, (54, 59.5), (290, 290)),
    ("Minotaur", 600, (21, 24), (70, 80)), ("Pegasus XL", 450, (20, 25), (80, 100)),
    ("Taurus XL", 1_590, (45, 50), (150, 160)), ("Taurus II", 5_000, (45, 45), (150, 150)),
    ("Ariane 5 ES", 21_000, (152, 160), (620, 650)), ("Ariane 5 ECA", 25_000, (165, 175), (675, 720)),
    ("Proton-K", 20_700, (100, 100), None), ("Soyuz/Molniya", 6_200, (65, 65), None),
    ("Vega", 2_400, (50, 50), None), ("ISRO PSLV", 3_500, (32, 32), None),
    ("ISRO GSLV", 4_500, (40, 40), None), ("Dnepr", 3_700, (12, 12), None),
    ("Zenit 2", 13_700, (120, 120), None), ("Zenit 3SL", 6_000, (150, 150), None),
]


def inflate(amount: float, from_year: int, to_year: int) -> float:
    """Eq. 17.1: I_f = 1.031^n, n years since the reference year."""
    return amount * (1.0 + INFLATION_PER_YEAR) ** (to_year - from_year)


def work_year_usd(year: int) -> tuple:
    """Dollars per work-year in `year`, and how it was obtained.

    Table 17.3 is used directly where it has an entry, and Eq. 17.1 escalates from the 2010 reference value
    otherwise - which is what the chapter does itself when it converts between years.
    """
    if year in WORK_YEAR_USD:
        return float(WORK_YEAR_USD[year]), f"book Table 17.3 entry for {year}"
    base = WORK_YEAR_USD[WORK_YEAR_REFERENCE_YEAR]
    return (inflate(base, WORK_YEAR_REFERENCE_YEAR, year),
            f"Table 17.3's {WORK_YEAR_REFERENCE_YEAR} value escalated by Eq. 17.1 at "
            f"{INFLATION_PER_YEAR*100:.1f} %/yr")


def element_effort_wyr(code: str, mass_kg: float, f1: float = 1.0, f2: float | None = None,
                       f3: float = 1.0, f8: float = 1.0) -> dict:
    """One element's development effort: the CER, then the factors applied multiplicatively (Fig. 17.11)."""
    cer = CERS[code]
    raw = cer.effort_wyr(mass_kg)
    factors = [f for f in (f1, f2, f3, f8) if f is not None]
    applied = raw
    for f in factors:
        applied *= f
    return dict(code=code, name=cer.name, mass_kg=mass_kg, wyr_cer=raw, wyr=applied,
                f1=f1, f2=f2, f3=f3, f8=f8, basis=cer.mass_basis, figure=cer.figure)


@dataclass
class CostEstimate:
    elements: list = field(default_factory=list)
    year: int = 2010
    work_year_usd: float = 0.0
    work_year_source: str = ""
    f0: float = SYSTEM_ENGINEERING_F0
    development_wyr: float = 0.0
    development_usd: float = 0.0
    per_flight_usd: tuple = (0.0, 0.0)
    per_flight_central_usd: float = 0.0
    usd_per_kg: float = 0.0
    comparables: list = field(default_factory=list)
    notes: list = field(default_factory=list)


def _engine_code(stage_spec) -> str:
    """Which engine CER applies. The book separates turbopump-fed from pressure-fed (Table 17.2)."""
    if getattr(stage_spec, "is_solid", False):
        return "ES"
    cycle = (getattr(getattr(stage_spec, "prop_system", None), "cycle", "") or "").lower()
    return "EP" if "pressure" in cycle else "EL"


def estimate(res, year: int = 2010, f1: float = 1.0, f2: float | None = None, f3: float = 1.0,
             f8: float = 1.0, f0: float = SYSTEM_ENGINEERING_F0,
             usd_per_lb: float = RULE_OF_THUMB_USD_PER_LB) -> CostEstimate:
    """Development effort and cost, element by element, plus a cost per flight from the chapter's rules.

    The element breakdown follows Table 17.4's: one entry per engine type and one per vehicle step, with the
    step's mass taken WITHOUT its engines because that is the mass basis Fig. 17.16 is plotted against.
    """
    out = CostEstimate(year=year, f0=f0)
    out.work_year_usd, out.work_year_source = work_year_usd(year)

    for s in res.stages:
        spec_s = res.spec.stages[s.index - 1]
        eng_mass = _engine_mass_kg(res, s.index)
        dry_less_engines = max(s.m_dry_kg - eng_mass, 0.0)
        if eng_mass > 0:
            out.elements.append(element_effort_wyr(_engine_code(spec_s), eng_mass, f1, f2, f3, f8)
                                | {"element": f"Stage {s.index} engines"})
        if dry_less_engines > 0:
            code = "ES" if getattr(spec_s, "is_solid", False) else "VS"
            out.elements.append(element_effort_wyr(code, dry_less_engines, f1, f2, f3, f8)
                                | {"element": f"Stage {s.index} vehicle"})
    if res.boosters is not None:
        b = res.boosters
        m_each = getattr(b, "m_inert_each_kg", 0.0) or 0.0
        if m_each > 0:
            out.elements.append(element_effort_wyr("VR", m_each, f1, f2, f3, f8)
                                | {"element": "Strap-on booster (one unit)"})

    out.development_wyr = f0 * sum(e["wyr"] for e in out.elements)
    out.development_usd = out.development_wyr * out.work_year_usd

    # Cost per flight: Sec. 17.5.3's rules of thumb, NOT a CER - the production submodel's coefficients are
    # not in this book.
    pl_lb = res.payload_mass_kg * LB_PER_KG
    lo, hi = RULE_OF_THUMB_RANGE_USD_PER_LB
    out.per_flight_usd = (pl_lb * lo, pl_lb * hi)
    out.per_flight_central_usd = pl_lb * usd_per_lb
    out.usd_per_kg = out.per_flight_central_usd / res.payload_mass_kg if res.payload_mass_kg > 0 else 0.0
    out.comparables = comparable_vehicles(res.payload_mass_kg)
    out.notes = _notes(out, res, usd_per_lb)
    return out


def _engine_mass_kg(res, stage_index: int) -> float:
    """Engine (or motor) mass of one stage, from the ledger the mass build-up already produced."""
    want = ("Engines", "Engine gimbals")
    return sum(i.mass_kg for i in res.ledger if i.stage == stage_index and i.name in want)


def comparable_vehicles(payload_kg: float, band: float = 0.5) -> list:
    """Real vehicles from Table 17.5 whose LEO payload is within a factor of (1 +/- band) of this one's."""
    lo, hi = payload_kg * (1 - band), payload_kg * (1 + band)
    out = []
    for name, pl, cost_m, wyr in TABLE_17_5:
        if lo <= pl <= hi:
            mid = 0.5 * (cost_m[0] + cost_m[1]) * 1e6
            out.append(dict(name=name, leo_kg=pl, cost_low_usd=cost_m[0] * 1e6, cost_high_usd=cost_m[1] * 1e6,
                            usd_per_kg=mid / pl, wyr_per_flight=wyr))
    return sorted(out, key=lambda r: r["leo_kg"])


def _notes(out: CostEstimate, res, usd_per_lb: float) -> list:
    n = [f"Development effort is {out.development_wyr:,.0f} work-years, including the programme-level "
         f"systems-engineering factor f0 = {out.f0:.3f} from Table 17.4. At "
         f"${out.work_year_usd:,.0f} per work-year ({out.work_year_source}) that is "
         f"${out.development_usd/1e9:,.2f} billion in {out.year} dollars.",
         f"TRANSCOST's own accuracy is \"usually within +/- {TRANSCOST_ACCURACY*100:.0f}%\" (p.998), and it "
         f"says its estimates \"will almost always be higher than estimates derived from a bottom-up "
         f"approach\" because they include the cost of unforeseen development problems and their resolution.",
         f"The f-factors above are INPUTS and they dominate the answer. The values used here are "
         f"f1 = {out.elements[0]['f1'] if out.elements else 1:.2f} (development status), "
         f"f3 = {out.elements[0]['f3'] if out.elements else 1:.2f} (team experience); the book describes what "
         f"they mean, defers their values to its reference [15], and prints one worked set for Ariane 5 in "
         f"Table 17.4 where they range from 0.77 to 1.6.",
         f"Cost per flight is NOT from a cost-estimating relationship. The production submodel's coefficients "
         f"and the learning curve are deferred to the same reference, so the figure here is Sec. 17.5.3's rule "
         f"of thumb - \"assume an average cost of ${usd_per_lb:,.0f} per pound to orbit\" - with the "
         f"${RULE_OF_THUMB_RANGE_USD_PER_LB[0]:,.0f} to ${RULE_OF_THUMB_RANGE_USD_PER_LB[1]:,.0f} per pound "
         f"range the same section gives. That range is a factor of 60 wide, and it is the honest width of what "
         f"this book supports."]
    if out.comparables:
        lo = min(c["cost_low_usd"] for c in out.comparables)
        hi = max(c["cost_high_usd"] for c in out.comparables)
        n.append(f"{len(out.comparables)} real vehicle(s) in the book's Table 17.5 lift a comparable payload "
                 f"to LEO, at ${lo/1e6:,.0f}M to ${hi/1e6:,.0f}M per flight (ca. 2013 dollars). Those are "
                 f"prices actually charged, which is a firmer number than anything estimated above.")
    else:
        n.append("No vehicle in the book's Table 17.5 lifts a comparable payload, so there is no price "
                 "actually charged to compare against.")
    return n


def specific_transportation_cost_wyr_per_Mg(wyr_per_flight: float, payload_kg: float) -> float:
    """Book Sec. 17.6.4 and Fig. 17.17: work-years per tonne of payload to LEO, the cost-efficiency measure.

    The book's own scatter around its trendline is +100%/-50%, and it notes that a 60-80% payload utilisation
    factor raises the real figure 20-60% above the theoretical one.
    """
    if payload_kg <= 0:
        return float("nan")
    return wyr_per_flight / (payload_kg / 1000.0)
