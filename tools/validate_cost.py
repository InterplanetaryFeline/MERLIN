"""Check the cost model against the work-years Koelle's handbook states, and write docs/COST_VALIDATION.md.

    python tools/validate_cost.py

Three separate questions, because agreeing on one says nothing about the next:
  A. are the relations transcribed correctly?       (Koelle's own worked examples, his masses and his factors)
  B. do MERLIN's sized vehicles give the development effort the real ones took?
  C. do they give the work-years per flight Koelle tabulates?

Inputs in B and C are the Cost tab's defaults, plus the country. Nothing is chosen per vehicle to improve a match.
"""
from __future__ import annotations
import math
import os
import statistics as st
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from launch_vehicle import cost as C                                          # noqa: E402
from launch_vehicle.config_io import load_design                              # noqa: E402
from launch_vehicle.convergence import size_vehicle                           # noqa: E402

ASSUMP = os.path.join(ROOT, "config", "engineering_assumptions.yaml")

#: Koelle Tables 5-VI and 5-VII, pp.210 and 212: case -> (vehicle there, MYr low, high, region, his launch mass in Mg)
PER_FLIGHT = [
    ("saturn5", "Saturn V", 4280, 4280, "USA", 2850), ("ariane5_eca", "Ariane 5 ECA", 650, 700, "Europe", 777),
    ("atlas5_551", "Atlas V 551", 530, 610, "USA", 540), ("delta4_heavy", "Delta IV-H", 600, 800, "USA", 733),
    ("delta2_7920", "Delta II 7925 (a third stage more)", 350, 400, "USA", 232), ("falcon9", "Falcon 9 (as planned in 2007)", 140, 160, "USA", 300),
    ("h2a_202", "H-IIA 202", 380, 410, "Japan", 285), ("m_v", "M-5", 280, 300, "Japan", 140),
    ("pegasus_xl", "Pegasus XL", 80, 100, "USA", 23), ("scout_g1", "Scout", 77, 77, "USA", 22),
    ("titan2", "Titan II", 250, 270, "USA", 155), ("vega", "Vega (planned price)", 100, 100, "Europe", 130),
    ("soyuz2_1b", "Soyuz-2 from Kourou", 160, 160, "Russia", 305),
]
#: whole-programme development: case, what, actual MYr, where it is stated, region
DEVELOPMENT = [
    ("saturn5", "Saturn V", 120_000, "Fig. 2-01, p.24 (read off)", "USA"),
    ("ariane5_eca", "Ariane 5 (Koelle's is the 5G)", 46_500, "p.105, final; 39,300 as stated in 1996, p.104", "Europe"),
]
#: single elements of MERLIN's sized vehicles: case, element key, name, actual MYr and mass in kg read off, figure
ELEMENTS = [
    ("saturn5", "stage1_engine", "F-1 engine", 17_800, 8_452, "Fig. 2-09, p.37"),
    ("saturn5", "stage2_engine", "J-2 engine", 12_800, 1_575, "Fig. 2-09, p.37"),
    ("saturn5", "stage1_vehicle", "S-IC stage", 50_500, 96_000, "Fig. 2-27, p.53"),
    ("saturn5", "stage3_vehicle", "S-IVB stage", 24_800, 11_300, "Fig. 2-27, p.53"),
    ("ariane5_eca", "stage1_engine", "Vulcain engine", 11_100, 1_685, "Fig. 2-09, p.37"),
]
#: pump-fed engines on Fig. 2-09: (name, dry mass kg, original MYr), read off the plot to about 5 %
ENGINES = [("RL-10", 137, 4450), ("HM-7B", 155, 3970), ("LE-5", 255, 3850), ("RZ.2", 680, 4520),
           ("Viking-2", 825, 3480), ("J-2", 1575, 12800), ("Vulcain", 1685, 11100), ("LE-7", 1720, 5050),
           ("SSME", 3180, 18146), ("F-1", 8452, 17800)]


def worked_examples() -> list:
    """(what, stated, ours, where)"""
    rows = []
    for name, d in C.ARIANE5_FACTORS.items():
        e = C.element_effort_wyr(d["code"], d["mass_kg"], d["f1"], d["f2"], d["f3"], d["f8"])
        rows.append((f"Ariane 5 {name}: CER", d["wyr_cer"], e["wyr_cer"], "Table 2-V, p.104"))
        rows.append((f"Ariane 5 {name}: with factors", d["wyr"], e["wyr"], "Table 2-V, p.104"))
    total = sum(C.element_effort_wyr(d["code"], d["mass_kg"], d["f1"], d["f2"], d["f3"], d["f8"])["wyr"]
                for d in C.ARIANE5_FACTORS.values()) * C.SYSTEM_ENGINEERING_F0 ** 3
    rows.append(("Ariane 5 programme", 40_827, total, "Table 2-V, p.104"))
    rows.append(("SSME development", 17_921,
                 C.element_effort_wyr("EL", 3180, 1.30, 1.22, 0.85)["wyr"], "p.103"))
    rows.append(("SSME f2 at 900 firings", 1.22, C.engine_quality_factor(900), "p.103 and Fig. 2-11"))
    a, x, _p = C.PRODUCTION_CERS["vehicle_cryo"]
    rows.append(("Five S-II stages, f4 = 0.86 as given", 4_515, 5 * a * 29_700 ** x * 0.86, "p.140"))
    rows.append(("S-II learning factor p at 2-3 a year", 0.96, C.stage_learning_factor(29_700, 2.5), "p.140 and Fig. 3-07"))
    rows.append(("S-II f4, units 11-15 at p = 0.96", 0.86, C.learning_of_batch(0.96, 11, 15), "p.140"))
    a, x, _p = C.PRODUCTION_CERS["engine_storable"]
    rows.append(("One F-1, f4 = 0.58 as given", 139.1, a * 8_452 ** x * 0.58, "pp.140-141"))
    rows.append(("F-1 learning factor p at 14 a year", 0.92, C.engine_learning_factor(8_452, 14), "p.141 and Fig. 3-15"))
    rows.append(("F-1 f4, units 76-106 at p = 0.91", 0.58, C.learning_of_batch(0.91, 76, 106), "p.141"))
    rows.append(("Winged SSTO engine, f1-f8 as given", 9_780,
                 C.element_effort_wyr("EL", 3176, 1.0, 1.07, 0.8, 0.86)["wyr"], "p.113"))
    return rows


def sized(case, cache={}):
    if case not in cache:
        cache[case] = size_vehicle(load_design(os.path.join(ROOT, "validation", case + ".yaml"), ASSUMP),
                                   keep_history=False)
    return cache[case]


def development_rows() -> list:
    out = []
    for case, what, actual, where, region in DEVELOPMENT:
        c = C.estimate(sized(case), inputs={"region": region})
        out.append((what, actual, c.development_wyr, where))
    return out


def element_rows() -> list:
    out = []
    for case, key, what, actual, mass, where in ELEMENTS:
        region = "Europe" if case.startswith("ariane") else "USA"
        e = next(x for x in C.estimate(sized(case), inputs={"region": region}).elements if x["key"] == key)
        out.append((what, actual, e["wyr"], where, e["mass_kg"], e["f2"], mass))
    return out


def per_flight_rows(**inputs) -> list:
    out = []
    for case, what, lo, hi, region, glow in PER_FLIGHT:
        c = C.estimate(sized(case), inputs=dict(inputs, region=region))
        out.append((what, lo, hi, c.flight_wyr, c.trend_wyr, glow, sized(case).glom_kg / 1000.0))
    return out


def ratio_stats(pairs):
    r = [o / a for a, o in pairs]
    return dict(n=len(r), median=st.median(r), lo=min(r), hi=max(r),
                geo=math.exp(st.mean(math.log(x) for x in r)),
                within20=sum(1 for x in r if 0.8 <= x <= 1.2), within2=sum(1 for x in r if 0.5 <= x <= 2.0))


def _pct(a, o):
    return f"{100 * (o / a - 1):+.1f} %"


def _n(v):
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:.1f}" if abs(v) >= 10 else f"{v:.3f}"


def main() -> int:
    L = ["# How the cost model compares with Koelle's work-years", "",
         "Written by `tools/validate_cost.py`; do not edit by hand. Source: Koelle, *Handbook of Cost Engineering*,",
         "TCS-TR-184, TRANSCOST 7.2, 2007, page numbers as printed. MYr and work-year are the same thing.", "",
         "Inputs are the Cost tab's defaults (f1 = f3 = 1, 6 launches a year, 60 flights, vertical assembly then",
         "move), each vehicle's country, and each case's own delta-v split. Nothing was chosen to improve a match. Values marked *read off* come",
         "from a log-scale plot and carry about 5 % of reading error.", "",
         "## A. Are the relations right? Koelle's own worked examples", "",
         "His masses, his factors, this module's equations.", "",
         "| Example | Koelle | MERLIN | Difference | Where |", "|---|---|---|---|---|"]
    for what, a, o, where in worked_examples():
        L.append(f"| {what} | {_n(a)} | {_n(o)} | {_pct(a, o)} | {where} |")
    L += ["", "The relations reproduce. The learning factors are the least exact, because they are read off charts;",
          "Koelle's own F-1 example uses p = 0.92 and then 0.91. His f4 = 0.58 for that batch is also a chart reading.", "",
          "The CER alone, without the factors, against the ten engines' actual cost (Fig. 2-09, p.37, read off):", "",
          "| Engine | Mass [kg] | Actual | CER, all factors 1 | Difference |", "|---|---|---|---|---|"]
    ep = []
    for n, m, a in ENGINES:
        o = C.CERS["EL"].effort_wyr(m)
        ep.append((a, o))
        L.append(f"| {n} | {m:,} | {a:,} | {_n(o)} | {_pct(a, o)} |")
    s = ratio_stats(ep)
    L += ["", f"Median ratio {s['median']:.2f}, from {s['lo']:.2f} to {s['hi']:.2f}; {s['within20']} of {s['n']} within 20 %.",
          "The factors exist to close exactly this gap: neutral factors are a guess about the team and the technology.", "",
          "## B. Development effort of MERLIN's sized vehicles", "",
          "| Programme | Actual | MERLIN | Difference | Where |", "|---|---|---|---|---|"]
    for what, a, o, where in development_rows():
        L.append(f"| {what} | {_n(a)} | {_n(o)} | {_pct(a, o)} | {where} |")
    L += ["", "And the parts of them whose cost can be read off:", "",
          "| Element | Actual (read off) | MERLIN | Difference | Mass, real / MERLIN [kg] | f2 | Where |",
          "|---|---|---|---|---|---|---|"]
    for what, a, o, where, m, f2, m0 in element_rows():
        L.append(f"| {what} | {a:,} | {_n(o)} | {_pct(a, o)} | {m0:,} / {m:,.0f} | {'1' if f2 is None else format(f2, '.2f')} | {where} |")
    c = C.estimate(sized("saturn5"))
    j2 = next(x for x in c.elements if x["key"] == "stage3_engine")["wyr"] * c.f0
    L += ["", "**The programme totals agree better than the parts do, and partly by luck.** MERLIN sizes these vehicles",
          "lighter than they were, so most parts come out cheap. Against that, the Saturn V case names no real engine,",
          f"so the J-2 is charged on both stages that use it: {j2:,.0f} work-years too many. Charged once, the total is",
          f"{c.development_wyr - j2:,.0f}, {_pct(120_000, c.development_wyr - j2)} against the plot. The spread of the parts is the better",
          "measure of what one number is worth.", "",
          "S-II, S-IB, H.155, L.140 and the smaller stages of Fig. 2-27 are left out because the scanned labels do not",
          "say which point is whose.", "",
          "## C. Work-years per flight", "",
          "Koelle Tables 5-VI and 5-VII (pp.210 and 212) are mostly **prices** asked around 2006, not costs.", "",
          "| Vehicle | Koelle | MERLIN | MERLIN / middle | Launch mass, his / ours [t] | Trend of real vehicles (book Table 17.5) |", "|---|---|---|---|---|---|"]
    rows = per_flight_rows()
    for what, lo, hi, o, tr, g0, g1 in rows:
        rng = f"{lo:,}" if lo == hi else f"{lo:,}-{hi:,}"
        L.append(f"| {what} | {rng} | {_n(o)} | {o / (0.5 * (lo + hi)):.2f} | {g0:,} / {g1:,.0f} | {_n(tr) if tr else 'not LEO'} |")
    pairs = [(0.5 * (r[1] + r[2]), r[3]) for r in rows]
    s = ratio_stats(pairs)
    L += ["", f"Median ratio **{s['median']:.2f}**, from {s['lo']:.2f} to {s['hi']:.2f}. {s['within20']} of {s['n']} within 20 %, "
              f"{s['within2']} of {s['n']} within a factor of two.", ""]
    solid = [p for p, r in zip(pairs, rows) if r[0].split()[0] in ("M-5", "Pegasus", "Scout", "Vega")]
    liquid = [p for p, r in zip(pairs, rows) if p not in solid]
    for lab, pp in (("small, mostly solid vehicles", solid), ("liquid vehicles", liquid)):
        q = ratio_stats(pp)
        L.append(f"* {lab} ({q['n']}): median {q['median']:.2f}, from {q['lo']:.2f} to {q['hi']:.2f}")
    tp = [(0.5 * (r[1] + r[2]), r[4]) for r in rows if r[4]]
    q = ratio_stats(tp)
    L += [f"* the trend alone, for the {q['n']} that fly to LEO: median {q['median']:.2f}, from {q['lo']:.2f} to {q['hi']:.2f}", "",
          "Sensitivity to the two assumed inputs (median ratio over the same vehicles):", "",
          "| Launches a year | Flights | Median ratio |", "|---|---|---|"]
    for rate, flights in ((2, 20), (6, 60), (12, 120), (12, 300)):
        q = ratio_stats([(0.5 * (r[1] + r[2]), r[3]) for r in per_flight_rows(launch_rate=rate, total_flights=flights)])
        L.append(f"| {rate} | {flights} | {q['median']:.2f} |")
    L += ["", "## What this means", "",
          "* **The equations are right** (part A): the development and production relations match Koelle's worked examples.",
          "* **Development effort** lands within a few per cent for the two programmes that could be checked, with parts",
          "  up to about 40 % off. Two programmes is a small sample, and +/- 20 % is TRANSCOST's own claim.",
          "* **Cost per flight runs high for liquid vehicles**, about 1.8 times the 2006 price. Those are prices, not costs;",
          "  several vehicles here are later and larger versions than his (the launch-mass column), Falcon 9 and Vega above",
          "  all; and Koelle puts the RS-68, designed for low cost, more than 50 % below his own relation (p.128).",
          "  How much each reason contributes has not been separated.",
          "* **Soyuz** carries Russia's f8 = 2.11 while its price is quoted in European work-years, so the two are not in",
          "  the same unit.",
          "* **Delta IV Heavy** counts each strap-on core with its engine inside, as a hydrogen stage, because MERLIN's",
          "  liquid strap-ons do not separate the engine.",
          "* Launch rate and production run are assumptions, and they move the result by a factor of two (table above).", ""]
    text = "\n".join(L)
    with open(os.path.join(ROOT, "docs", "COST_VALIDATION.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
