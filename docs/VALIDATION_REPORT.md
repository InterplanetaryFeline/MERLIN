# Validation report — real launch vehicles, solid motors and strap-on boosters

> **Kept for the record.** This is the narrative written at v0.3, and its figures predate later changes to the
> mass model. [`ACCURACY.md`](ACCURACY.md) has the current measurements.

*Software v0.3. Every number below was produced by `tools/run_validation.py` + `tools/build_validation_report.py`
(raw data in `outputs/validation/`). **Nothing was tuned to match a vehicle.** Values that were not found in the
sources are tagged `assumed` inside the corresponding `validation/*.yaml`, where every leaf carries its source.*

## 0. What is being compared

For each vehicle the tool is given the **published payload, orbit, launch site, propellants, engine/motor
performance and diameters** — and nothing about the stage masses. It then sizes the vehicle from scratch. The
comparison is therefore between *the tool's predicted gross mass* and *the real vehicle's published gross mass*.

Four runs are reported per vehicle:

| Run | Meaning |
|---|---|
| **As-published split** | the delta-v split written in the case file (derived from published stage masses where available, otherwise assumed) |
| **Optimised split** | the GLOM-minimising split found by `optimize_dv_split()` — the primary result |
| **Lean margins** | *diagnostic*: optimised split with no mass-growth margin, no loading margin, residual 1 % (liquids) / 0 % (solids) |
| **Published casing k** | *diagnostic, solid vehicles only*: the book's SRM casing MER replaced by each motor's real inert/propellant ratio |

The last two are not calibrations. They exist to separate "the model is wrong" from "this particular
statistical mass relation is conservative".

---

## 1. Results: thirteen real vehicles

| Vehicle | Class | Published GLOM [t] | As-published | **Optimised** | Lean (diag.) | Published casing k (diag.) | Length pred./pub. [m] |
|---|---|---|---|---|---|---|---|
| Rocket Lab Electron | small, liquid | 13.0 | 16.8 (+29 %) | **16.4 (+26 %)** | 13.6 (+5 %) | n/a | 20.8 / 18.0 |
| Pegasus XL | small, 3× solid, air-launched | 23.1 | 36.9 (+60 %) | **33.6 (+45 %)** | 30.4 (+32 %) | 32.3 (+40 %) | 25.7 / 17.6 |
| Scout G-1 | small, 4× solid | 21.7 | 54.7 (+152 %) | **35.2 (+62 %)** | 30.7 (+41 %) | see §3.1² | 42.5 / 22.9 |
| Firefly Alpha | small, liquid | 54.0 | 59.0 (+9 %) | **57.5 (+6 %)** | 44.2 (−18 %) | n/a | 33.4 / 29.0 |
| Epsilon | small, 3× solid | 95.4 | 151.1 (+58 %) | **135.5 (+42 %)** | 121.4 (+27 %) | n/a | 38.1 / 26.0 |
| Vega | small, 3× solid + liquid | 137.0 | 304.2 (+122 %) | **171.0 (+25 %)** | 151.8 (+11 %) | **144.3 (+5 %)** | 60.0 / 30.0 |
| Titan II GLV | medium, hypergolic | 154.0 | 178.6 (+16 %) | **178.3 (+16 %)** | 148.1 (−4 %) | n/a | 39.4 / 33.2 |
| Zhuque-2 | medium, methalox | 219.0 | 150.1 (−31 %) | **149.5 (−32 %)** | 126.7 (−42 %) | n/a | 39.9 / 49.5 |
| Delta II 7920 | medium, 9 strap-ons | 231.9 | 297.4 (+28 %) | **231.0 (−0 %)** | 210.2 (−9 %) | n/a | 56.3 / 38.9 |
| Falcon 9 Block 5 | medium, liquid | 549.1 | 636.3 (+16 %) | **627.1 (+14 %)** | 544.3 (−1 %) | n/a | 81.5 / 70.0 |
| Atlas V 551 | heavy, 5 strap-ons | 587.0 | 538.6 (−8 %) | **475.5 (−19 %)** | not feasible¹ | n/a | 78.4 / 58.3 |
| Ariane 5 ECA | heavy, 2 strap-ons | 780.0 | 855.4 (+10 %) | **802.8 (+3 %)** | 757.1 (−3 %) | n/a | 80.6 / 52.0 |
| Saturn V (to TLI) | heavy, liquid | 2,894.0 | 2,825.7 (−2 %) | **2,651.5 (−8 %)** | 2,253.1 (−22 %) | n/a | 130.0 / 110.6 |

² Scout is deliberately absent from the published-casing-k column; §3.1 finding 5 explains why that
column double-counts a stage-level figure, which Scout's unusually high ratios make impossible to miss.

¹ With lean margins the Atlas V core becomes light enough that it would burn out *before* the solid boosters
finish; the tool refuses that configuration and says so rather than silently producing a number.

**Median absolute error of the optimised runs, over all sixteen cases the suite now runs: 15.0 %**
(mean 19.5 %). The liquid vehicles sit inside ±20 %; the all-solid vehicles are systematically high, and the
ordering is almost exactly by size — the four worst are Zhuque-2 (−32 %), Epsilon (+42 %), Pegasus XL (+45 %)
and Scout G-1 (+62 %), the smallest all-solid vehicle in the set. Section 3 explains why, §3.1 takes Scout
apart to separate the mass model from the loss model, and section 4 gives the booster split.

The table above lists thirteen vehicles; the suite also runs H-IIA 202, Soyuz-2.1b and Delta IV Heavy, whose
results are in `docs/VALIDATION_REPORT_DATA.md` (generated) and section 4.

Two numbers moved when the published errata was applied (`docs/ERRATA_COMPLIANCE.md`):

* **Pegasus XL got worse, from +30 % to +45 %.** The errata (pp.165/183) replaces the 40 m/s drag loss printed
  in the 1st edition with the **322 m/s measured on Pegasus' first flight** [Mosier et al., 1990], and notes
  that this contradicts the usual assumption that air launch saves drag. The case previously carried a 50 m/s
  estimate. The larger error is the honest one: the tool now uses a measured flight value, and the remaining
  gap is the solid-casing MER of section 3 plus an ascent-loss regression that was never fitted to air launch.
* **Electron improved, from +32 % to +26 %**, because the errata's small-payload PAF rule (`m_PAF = 0.15 m_PL`,
  p.443) replaces a `0.0755 m_PL + 50` adapter that was 20–40 % of a 150–300 kg payload.

---

## 2. Is the delta-v requirement right?

An independent check that does not involve mass modelling: take the **published** stage masses, compute the
ideal (loss-free) delta-v they deliver with the published Isp values, and compare with the requirement the tool
computes for that mission.

| Vehicle | Ideal dv from published masses [m/s] | Required (tool) [m/s] | Margin |
|---|---|---|---|
| Rocket Lab Electron | 9,136 | 9,551 | −4.3 % |
| SpaceX Falcon 9 Block 5 | 9,221 | 9,097 | +1.4 % |
| Titan II GLV | 9,201 | 8,988 | +2.4 % |
| Saturn V (to TLI) | 12,987 | 12,359 | +5.1 % |
| Pegasus XL (air-launched) | 7,976 | 8,461 | −5.7 % |
| Vega (700 km polar) | 9,876 | 10,264 | −3.8 % |

Real vehicles should show a small positive margin. Falcon 9, Titan II and Saturn V do. Electron and Vega come
out slightly negative, within the ±260 m/s RMS error of the book's loss regression (≈ ±3 %), and both have
published payload figures whose exact reference orbit is not stated.

**Pegasus is the exception at −5.7 % (−485 m/s), and it is informative.** That is outside the regression's own
RMS error, and it is the air-launch case: the book's loss fits are built from ground launches, and the errata's
measured 322 m/s drag loss says air launch is not the benign case it is assumed to be. So for Pegasus the
delta-v side is contributing to the over-prediction, not only the casing MER. For the other eleven vehicles the
conclusion stands: the delta-v model is good to a few per cent and is **not** the cause of the solid-vehicle
over-prediction.

---

## 3. Structural factors: where the error actually is

`s = m_inert / (m_inert + m_propellant)`, book Eq. 5:5a.

| Vehicle | Stage | Type | s predicted | s published | ratio |
|---|---|---|---|---|---|
| Electron | 1 | liquid | 0.0802 | 0.0931 | 0.86 |
| Electron | 2 | liquid | 0.0816 | 0.1087 | 0.75 |
| Falcon 9 | 1 | liquid | 0.0611 | 0.0608 | **1.01** |
| Falcon 9 | 2 | liquid | 0.0508 | 0.0404 | 1.26 |
| Titan II | 1 | liquid | 0.0656 | 0.0538 | 1.22 |
| Titan II | 2 | liquid | 0.0827 | 0.0767 | 1.08 |
| Saturn V | 1 | liquid | 0.0728 | 0.0585 | 1.25 |
| Saturn V | 2 | liquid | 0.0792 | 0.0665 | 1.19 |
| Saturn V | 3 | liquid | 0.0939 | 0.0988 | 0.95 |
| Delta II | 1 | liquid | 0.0727 | 0.0558 | 1.30 |
| Atlas V | 1 | liquid | 0.0925 | 0.0690 | 1.34 |
| Atlas V | 2 (Centaur) | liquid | 0.0879 | 0.0972 | 0.90 |
| Ariane 5 | 1 (EPC) | liquid | 0.0895 | 0.0796 | 1.12 |
| **Pegasus XL** | 1 | **solid** | 0.1225 | 0.0836 | **1.47** |
| **Pegasus XL** | 2 | **solid** | 0.1324 | 0.0958 | **1.38** |
| **Pegasus XL** | 3 | **solid** | 0.1734 | 0.1406 | **1.23** |
| **Vega** | 1 (P80) | **solid** | 0.1178 | 0.0766 | **1.54** |
| **Vega** | 2 (Z23) | **solid** | 0.1229 | 0.0751 | **1.64** |
| **Vega** | 3 (Z9) | **solid** | 0.1264 | 0.0802 | **1.58** |

Liquid stages scatter around 1.0 (0.75–1.34). **Every modern solid stage in this table is 1.2–1.6× heavy**,
and the cause is a single coefficient: the book's SRM casing MER, `m_casing = k m_p` with k = 0.135 (steel) or 0.1154
(graphite-epoxy, book p.490). Those values come from Shuttle-SRB-class hardware. Modern filament-wound motors
do much better:

| Motor | published inert / propellant | book k used here |
|---|---|---|
| Vega P80 | 0.083 | 0.1154 (+39 %) |
| Vega Zefiro 23 | 0.081 | 0.1154 (+42 %) |
| Vega Zefiro 9 | 0.087 | 0.1154 (+33 %) |
| Pegasus Orion 50S XL | 0.091 | 0.1154 (+27 %) |
| Pegasus Orion 50 XL | 0.106 | 0.1154 (+9 %) |
| Atlas V AJ-60A | 0.095 | — (published empty mass used) |
| Delta II GEM-40 | 0.112 | — (published empty mass used) |
| Ariane 5 EAP | 0.138 | — (published empty mass used) |

On a three- or four-stage all-solid vehicle a 40 % inert-mass error compounds through every stage, which is why
Vega lands at +25 % while its individual stages are "only" ~55 % heavy. **Replacing k with the published ratio
for each Vega motor gives 144.3 t against the real 137 t (+5 %)** — the rest of the model (delta-v, geometry,
sizing loop, skirts, avionics, convergence) is sound.

Scout is the exception that fixes the rule, and it is why "modern" is now in that sentence. Its four stages
come out at 1.05, **0.73**, **0.66** and 1.34 — the tool is *light* on two of them (generated table,
`docs/VALIDATION_REPORT_DATA.md`). A 1960s stage carrying its guidance section and bolted-on avionics is
heavier than the book's coefficient, not lighter. The coefficient is not simply "too high": it describes
Shuttle-SRB-era steel hardware and is wrong in *both* directions once you leave that era, high for a
filament-wound P80 and low for an Antares IIIA. §3.1 has the numbers.

**Practical consequence for a user:** when sizing a modern solid motor, set
`casing_mass_method: mass_fraction` with a k from a comparable motor (0.08–0.09 for a filament-wound case,
0.13 for steel) instead of accepting the book default.

A second, smaller effect hits small launchers: the book's avionics MER (Table 8.8) is a step function — 75 kg
below a 1 t payload and **350 kg above it**. Vega (1.43 t payload) and Epsilon (1.5 t) are charged 350 kg on a
vehicle whose whole upper stage weighs a few hundred kilograms. `avionics_mass_override_kg` exists for this.

### 3.1 Scout G-1: the smallest stages anyone publishes inert masses for

Scout was added to answer one question — *are the solid relations any good at the bottom of the size range?* —
and it is the only vehicle in the set that can answer it. Its per-stage inert masses come from the
manufacturer (Tanck & Williams, LTV Missiles and Electronics Group, *The Scout Launch Vehicle System*, citing
the **SCOUT Planning Guide**, LTV, May 1987), not from a wiki, and its four stages span **12,817 kg down to
215 kg** of propellant. The smallest stage in the dataset the published relations were fitted to is Pegasus
stage 2 at 3,025 kg, so Scout's two upper stages reach **14× lower** than anything the relations have seen.

Two of the four are independently corroborated: Zandbergen's table carries Scout S1 and S2 at exactly
12.817/1.939 t and 3.768/1.064 t, and Thiokol's own catalogue gives the Star-31 a 1,285.9 kg propellant load
against LTV's 1,299 kg for stage 3 — 1.0 % apart.

**Finding 1 — "solid stages are lighter than the book says" is a statement about modern motors, not about
solid stages.** Every motor in the table above has a published inert/propellant ratio of 0.08–0.14. Scout's
are 0.131, **0.282**, 0.258 and 0.191. Stage 2 is the outlier because it carries the Scout guidance section,
and stage 3 and 4 are high because a small stage cannot amortise its skirts and separation hardware. The book
coefficient is too *heavy* for a filament-wound P80 and too *light* for a 1960s stage with its avionics
bolted on.

**Finding 2 — the published regressions degrade sharply below their fitted range, and they under-predict.**
Given Scout's published propellant load and asked only for the inert mass — no delta-v budget, no loss model,
no Isp, nothing that can absorb the error — every applicable relation comes out low:

| Relation | Scout S3 (1,299 kg) | Scout S4 (215 kg) | out-of-sample bias | in-sample bias |
|---|---|---|---|---|
| Zandbergen composite C1 | 144 kg (−57 %) | 24 kg (−42 %) | −49 % | −3 % |
| Zandbergen composite C2 | 164 kg (−51 %) | 29 kg (−30 %) | −40 % | +1 % |
| Kibbey high | 160 kg (−52 %) | 32 kg (−21 %) | −37 % | −22 % |
| Kibbey medium | 106 kg (−68 %) | 21 kg (−49 %) | −58 % | −48 % |
| Kibbey low | 83 kg (−75 %) | 16 kg (−61 %) | −68 % | −58 % |
| *published* | **335 kg** | **41 kg** | | |

Both stages are **below the fitted floor of every Zandbergen relation** (3,000 kg composite, 3,500 kg steel),
so this is extrapolation, and the table is what extrapolation costs. Kibbey's relations are the only ones that
claim this range at all — which is the point of them, since NASA fitted them for small launch vehicles
([NTRS 20190027424](https://ntrs.nasa.gov/citations/20190027424)) — and the best of them is still 37 % low.
These two stages are kept in `solid_inert.OUT_OF_SAMPLE`, deliberately **apart** from `DATASET`: adding them
to the fitting set would quietly change what "fitted to 34 stages" means and would make every refit disagree
with its source.

**Finding 3 — end to end, the book's build-up is 62 % high; the relation can be 2 % low or 378 % high
depending on whether it is applied inside its fitted range.**

| Variant | GLOM | vs published 21.7 t |
|---|---|---|
| As-published delta-v split | 54.7 t | +152 % |
| **Optimised split** | **35.2 t** | **+62 %** |
| Lean margins (diagnostic) | 30.7 t | +41 % |
| Published relation, *as this harness applies it* | 103.8 t | **+378 %** |
| Published relations, per stage, all six in-range combinations | 17.2 – 22.8 t | **−21 % … +5 %** |

The last two rows differ because of how the relation is *selected*, and that gap is the most practically
useful thing Scout has to say.

This harness picks **one** relation per vehicle from the vehicle's dominant case material, and for Scout that
is `zandbergen_steel_S2`, an *affine* fit: `m_inert = 0.1689 m_p + 509 kg`. Applied to a 215 kg fourth stage
the constant alone is 509 kg, giving 545 kg of inert on 215 kg of propellant — an effective k of **2.54** —
which then compounds through every stage below it. The tool does not hide this: `casing_mass` appends
`EXTRAPOLATED - 215 kg is outside the fitted range 3,500-505,000 kg` to the source string and `validate_spec`
raises a warning. The harness simply does not act on it. **An affine inert relation must not be extrapolated
below its fitted range**, because there the constant term stops being a correction and becomes the whole
answer.

Choosing instead per stage — one of the three steel relations for stages 1 and 2, both of which are inside
every steel fit's range, and a composite relation for stages 3 and 4, where no relation is in range because
none goes that low — gives six legitimate combinations:

| Stages 1–2 | Stages 3–4 | GLOM | vs published |
|---|---|---|---|
| steel S1 | composite C1 | 17.2 t | −21 % |
| steel S1 | composite C2 | 18.8 t | −13 % |
| steel S3 | composite C1 | 20.3 t | −7 % |
| steel S2 | composite C1 | 21.3 t | −2 % |
| steel S3 | composite C2 | 22.0 t | +1 % |
| steel S2 | composite C2 | 22.8 t | +5 % |

No single one of these is "the" answer and none is quoted here as such — the point is that the family
**brackets** the published 21.7 t, with a spread of about ±13 points around it. That spread is not a defect:
it is the scatter the sources themselves declare (MAPE 17–20 %), and it is what a conceptual-design estimate
of a small solid stage is actually worth. The book's own build-up, by contrast, misses on one side only, by
+62 %.

Findings 2 and 3 are then consistent rather than contradictory. The proportional relations *under*-predict
Scout's two small stages by 30–57 %, the affine one *over*-predicts them enormously, and stages 1 and 2 carry
96 % of the propellant — so what the closed loop lands on is decided by the two big stages, where every
relation is in range and roughly right.

**Finding 4 — about a third of the error is not mass at all, it is the ascent-loss regression.** Scout's own
published masses, flown with its own published Isp, give **9,087 m/s** of ideal delta-v. The tool asks for
**9,738 m/s** — a 651 m/s gap, against a regression whose stated RMS error is ~260 m/s. The book's
Eq. 3:37–3:38 was fitted to ordinary ascents; a four-stage solid that is all over in 176 s of burn is not one.
Holding everything else and substituting an explicit loss allowance shows the split directly:

| Loss allowance | GLOM | vs published |
|---|---|---|
| 2,051 m/s (what the book regression gives) | 33.6 t | +55 % |
| 1,537 m/s (what Scout's own masses imply) | 25.9 t | +19 % |

So roughly **35 of the 55 points are the loss model and 19 are the mass model** — which is worth knowing,
because every previous solid case in this report attributed the whole error to the casing MER.

**Finding 5 — a flaw in this report's own "published casing k" column.** That column feeds a published
inert/propellant ratio into `casing_mass_fraction`, which is a *motor-level* input: the build-up then adds
skirts, interstage, avionics, separation hardware and margin on top. Every published figure available for
these vehicles is *stage-level* and already contains those items, so the column double-counts. At Pegasus'
k = 0.091 and Vega's 0.083 the error hides; at Scout's stage-2 ratio of 0.282 it drives the sized vehicle to
72 t — worse than the book's own answer, and worse for a reason that has nothing to do with the book. Scout is
therefore **not** in that column, and the Pegasus and Vega rows should be reworked to use the stage-level
mechanism before they are quoted again.


### 3.2 Motor level vs stage level: the measurement that settles it

Everything above compares a MOTOR coefficient against STAGE figures, and that is why solid results in this
report have been so hard to read. The book's k_SRM (Eq. 8:18) covers a case, its insulation, the nozzle, the
thrust structure and the TVC. A published "stage inert mass" covers those plus skirts, interstage, avionics,
separation hardware — and on Scout's third stage that difference is **237 kg against a 98 kg motor**.

`solid_inert.MOTOR_DATASET` closes the hole: **55 STAR-family motors** whose loaded and burnout masses are
published together, so the difference is motor inert with no stage equipment in it. They span 25 kg to
4,590 kg of propellant — the range a small launch vehicle's upper stages live in.

**The book's constant is wrong in both directions, and which direction depends on size.** Motor inert
fraction is not constant: it falls from about 0.18 at 30 kg of propellant towards a floor near 0.060, so
k = 0.1154 crosses the real curve near 150–200 kg.

| propellant | motors | measured f | book k error |
|---|---|---|---|
| under 100 kg | 8 | 0.184 | **−36 %** |
| 100 – 500 kg | 20 | 0.092 | **+26 %** |
| 500 – 1,500 kg | 19 | 0.080 | **+44 %** |
| over 1,500 kg | 8 | 0.076 | **+51 %** |

**The relation fitted to them**, in Kibbey's functional form:

    f = 0.0602 + 0.0051 (m_p / 4536)^(-2/3)        MAPE 14 %, bias +2 %, N = 55

Two independent checks. The fitted floor, 0.0602, lands on the 0.060 Kibbey published from stage data and a
much smaller sample. And on **Star 31 — absent from the dataset, figures from Thiokol rather than
Wikipedia** — the book over-predicts by **+51.0 %** and this relation by **−5.8 %**.

**Why the stage-level comparisons looked better than the model deserved.** Two errors have been cancelling.
On Scout's third stage the book over-predicts the motor by 53 % while the build-up under-charges the stage
equipment by 187 kg; the stage total comes out 39 % low and the book's stage-level bias across twelve stages
is only +1.3 % median — against a 24.5 % MAPE. **The cancellation is accidental and size-dependent**, so it
offers no protection on a vehicle whose stages are smaller than the ones it happened to cancel on.

**Two populations, about 40 % apart.** Applying the STAR relation to real launch-vehicle stages runs 31 %
light, and that is not a defect of the fit: STAR motors are apogee-kick hardware with no TVC, no thrust
termination and no flight structure beyond the attachment ring, and a launch-vehicle stage of the same
propellant load is genuinely heavier. `star_motor` is therefore scoped to upper-stage class and says so in
every source string it emits; the Zandbergen stage-level relations remain the tool for a booster.

**What it is worth on a real vehicle.** A three-stage solid carrying 150 kg to 500 km polar, with only the
third stage's mass method changed:

| stage 3 sized by | GLOM | stage 3 inert fraction |
|---|---|---|
| notional, book Eq. 8:18 | **45,148 kg** | 0.206 |
| notional, `star_motor` | 32,581 kg | 0.129 |
| real Star 37FM, its own published k | **34,945 kg** | 0.147 |

The book's coefficient makes that vehicle **29 % heavier** than the real motor does — larger than the margin
most liquid-versus-solid trades turn on.

**A latent bug this found.** Naming a real motor loaded its published inert/propellant ratio into
`casing_mass_fraction`, and a stage that already stated `book_composite` then ignored it — 148 kg of book
motor against 98 kg of real motor, while the user believed they had selected real hardware. That now raises
a `CASEDB` warning naming the discrepancy, and every solid stage declares in the report whether it is a real
motor or a notional one.

**What was tried and rejected.** A pure power law (no floor; misses the largest motors by 25 %) and a
size-dependent relation fitted to LV *stages* (18.8 % MAPE against Zandbergen's 19.9 % on N = 17 is noise,
and the steel version predicts f > 1.0 at 215 kg of propellant). Neither earned a place.

---

## 4. Strap-on boosters (parallel burn)

The three booster vehicles exercise book Sec. 5.11 end to end, including Delta II's **six ground-lit plus three
air-lit** GEM-40s, which produce three powered phases.

| Vehicle | Boosters | Phases (powered) | Predicted GLOM | Published | Error |
|---|---|---|---|---|---|
| Delta II 7920 | 9 × GEM-40 (6 + 3 air-lit) | 3 | 231.0 t | 231.9 t | **−0.4 %** |
| Atlas V 551 | 5 × AJ-60A | 2 | 475.5 t | 587.0 t | −19 % |
| Ariane 5 ECA | 2 × EAP | 2 | 802.8 t | 780.0 t | **+2.9 %** |

The booster propellant and empty masses are inputs (published), so these cases test the **phase model, the
mass-averaged Isp of Eq. 5:66, the jettison bookkeeping and the core sizing**, not the booster mass model. The
mass ledger and the independent phase sequence agree to within 1e-9 at every event (tested).

Note on thrust: a real solid booster is front-loaded (Ariane 5's EAP peaks at 7,080 kN), while this tool models
constant thrust equal to the **burn average** (total impulse ÷ burn time), 4,456 kN for the EAP. The predicted
lift-off T/W is therefore lower than the quoted value (1.12 vs ~1.8 for Ariane 5). This is a modelling choice,
not an error, but it matters if you use lift-off T/W as a constraint.

---

## 5. Propellant types on one mission (10 t to 400 km LEO, 28.5°, GLOM-minimising split)

| Combination | GLOM [t] | Dry [t] | Payload fraction | Length [m] | dv [m/s] |
|---|---|---|---|---|---|
| LOX/LH2 + LOX/LH2 | 180.6 | 14.0 | 5.54 % | 53.8 | 9,546 |
| LOX/RP-1 + LOX/LH2 | 211.4 | 13.7 | 4.73 % | 53.1 | 9,521 |
| LOX/LCH4 + LOX/LCH4 | 299.9 | 14.5 | 3.33 % | 53.4 | 9,454 |
| LOX/RP-1 + LOX/RP-1 | 353.3 | 15.2 | 2.83 % | 51.8 | 9,429 |
| N2O4/Aerozine-50 | 478.8 | 18.3 | 2.09 % | 55.7 | 9,388 |

The **ordering** is the result; the exact masses are not, because the first-stage LH2 and all methalox Isp
values are illustrative rather than engine data. Hydrogen's advantage is overstated here: the tool charges no
penalty for the larger stage diameters that LH2 needs beyond the tank mass itself, and no boil-off.

---

## 6. Loads: the book's own Saturn V worked examples

Chapter 9 works two complete load cases on the Saturn V/Apollo 11 and prints their spreadsheets. Both are
reproduced from the book's published inputs in `tests/test_loads.py`, which is the closest thing to an
independent check this module can have.

### 6.1 Ground wind, Table 9.5 (p.566)

Eleven segments, from the escape tower to the engine fairings. Computed from the wind profile and C_D = 0.77
alone, with no number taken from the table itself:

| Quantity | Agreement |
|---|---|
| Side area of every segment | within 1 % of all eleven printed values |
| Wind speed at every centroid | within 0.5 % |
| Dynamic pressure at every centroid | within 0.5 % |
| Transverse drag force on every segment | within 1 % |
| Shear, all twelve stations | within 0.3 % |
| Bending moment at the base | 67,056 vs 67,860 kN·m, **−1.2 %** |

The moment difference has two identified causes, and nothing else.

**Cause 1 — Table 9.3's skirt centroid is wrong.** The table gives the centroid of a skirt's side area as
`h = l(d1/d3 + 2)/(3(d1/d3 + 1))` above the bottom, with `d1` forward and `d3` aft. As `d1 → 0` a skirt becomes
a cone, so that expression must reduce to the table's own cone entry, `l/3`. It gives `2l/3`. It is the correct
expression with the two diameters interchanged, and it puts the centroid on the *narrow* side of mid-span, where
there is less area. The correct form, `l(2·d_fwd + d_aft)/(3(d_fwd + d_aft))`, is derived in `loads.py`, agrees
with both of the table's other two entries, and is the same expression this tool already uses for the centroid
of a thin frustum shell in `mass_properties._frustum_zc`. The book's value propagated into its worked examples:
Table 9.11 names its skirt centroids as 90.5, 70.0 and 8.3 m elevation, each of which is the mirror of the
correct 89.7, 69.6 and 8.0 m. Substituting the book's centroid back in reproduces its first four moments to
0.1 %, which is what shows the two calculations are otherwise identical.

**Cause 2 — two rows of Table 9.5 exceed their own geometric bound.** A force applied inside a segment of
length `L` cannot raise the bending moment across it by more than `(V_above + F_segment)·L`. The S-II/S-IVB
skirt row rises by 2,572 kN·m against a bound of 2,553, and the bottom fairing row by 11,113 against 11,100.
Both overshoots are small (0.7 % and 0.1 %) but they are computed from the table's *own* printed shear and force
columns, so no centroid convention can produce them. `test_two_of_the_books_table_95_moment_rows_exceed_their_own_geometric_bound`
asserts this, and asserts that the other nine rows stay inside the bound.

### 6.2 Flight at max-q, Tables 9.8 and 9.11 (pp.596, 603)

| Quantity | Book | This module | Note |
|---|---|---|---|
| Air loads on four areas, body axes (Table 9.8) | — | within 2.7 % on 15 of 16 numbers | from the book's chart reads |
| Gimbal side force to trim | 1,161 kN | 1,165 kN | +0.3 % |
| Total lateral force | 2,736 kN | 2,741 kN | +0.2 % |
| Lateral load factor n_z | 0.154 | 0.1540 | — |
| Gimbal deflection, four of five engines | 2.15° | 2.16° | — |
| Axial running total, all 18 rows (Table 9.11) | up to 40,018 kN | within 3 kN | 0.005 % |

The sixteenth number is skirt 3's lift, 311.0 kN against the book's 374.5. Section 9.2.3 states
`CNα = 1.3/rad` and then computes with `CN = 0.235`, but 1.3/rad × 8.6° = 0.195. The 0.235 is skirt 2's `CN`
from four lines earlier. 311.0 kN is what the book's own stated coefficient gives.

**A third inconsistency, which this module resolves rather than reproduces.** Section 9.2.2 computes
n_x = 2.10 from a *measured* whole-vehicle axial force of 1,134 kN (C_D = 0.263 from Fig. 9.51), while Table 9.11
sums its *own* per-panel axial air loads to 2,843.7 kN — a factor of 2.5 on the same physical quantity. That is
why the book's axial running total misses zero at the gimbals by 1,468 kN, 3.8 % of the thrust, which the table
itself labels "should be ~0". Using the panel sum consistently would give n_x = 2.01 rather than 2.10. This
module scales the per-panel estimates so their total is the drag the trajectory actually flew with: n_x is then
consistent with the trajectory, and the axial curve closes on the thrust exactly.

### 6.3 What is not validated

The supersonic normal-force charts, Figs. 9.38–9.39, are not reproduced — the book says their origin is unknown
— so the default `CNα` is the slender-body 2/rad, which the book's subsonic Table 9.7 also gives. Against the
Saturn V chart reads at Mach 1.71 that is about 30 % low for a nose cone with an afterbody (the chart carries
lift over onto the cylinder behind it) and 29–67 % high for a flare. Per-panel chart reads can be supplied
through `mission.aerodynamics.cna_overrides`, and the Saturn V comparisons above use the book's.

Nothing downstream of the loads is validated, because nothing downstream of the loads exists yet: there are no
shell stresses, no buckling allowables and no margins of safety in this tool.

## 7. Cost: the book's own Ariane 5 verification table

Table 17.4 prints a complete check of TRANSCOST against the Ariane 5 programme — reference mass, CER
work-years, every f-factor and the final work-years, for five elements. All five are re-run in
`tests/test_cost.py`. Two reproduce exactly and three do not, in three different ways.

| Element | Code | Mass [kg] | Book CER [WYr] | This module [WYr] | |
|---|---|---|---|---|---|
| Vulcain engine | EL | 1,685 | 9,800 | 9,800 | exact |
| Aestus engine | EP | 119 | 890 | 890 | exact |
| SRB | VR | 39,300 | 5,398 | 5,938 | +10 % |
| Third stage and equipment bay | VS | 1,200 | 7,689 | 5,116 | −33 % |
| Vehicle and shroud | VS | 11,210 | 19,692 | 17,682 | −10 % |

**The SRB row.** Its printed CER value of 5,398 does not reconcile with its own final column: 5,398 times its
f-factors (1.1 × 0.9 × 0.86) is 4,596, not the 5,056 printed. But 5,938 — what H_VR = 10.4 M^0.60 gives —
times the same factors is 5,056 exactly. So the final column was computed from the CER and the printed CER
value is the slip.

**The third-stage row** is internally consistent (7,689 × its factors = 5,838, as printed) but 50 % away from
the vehicle CER. The likeliest reading is that an equipment bay is not an expendable-vehicle element at all;
TRANSCOST has codes the book lists in Table 17.2 but does not print CERs for. Left as a difference rather than
explained away.

**The vehicle-and-shroud row** closes on neither: its f-factors multiply to 1.357, so its printed CER would
give 26,715 work-years against the 18,368 printed, and no mass reproduces both columns.

**End to end**, the five elements through this module's CERs and the table's factors, with f0, give 41,679
work-years against the 39,300 ESA actually spent — 6.1 % high, where the book's own total is 3.9 % high. Both
sit inside TRANSCOST's stated ±20 %.

### What cost is not validated against

Nothing. Cost per flight is a rule of thumb, not a model, and the comparison against Table 17.5's real prices
is a sanity check on the payload class rather than a validation of anything computed. The f-factors, which
dominate the development estimate, are inputs with no basis in this tool at all.

## 8. Limitations of this validation

* Twelve vehicles, three of which (Electron, Epsilon, Zhuque-2) have low-confidence or partly assumed inputs.
  Zhuque-2's −32 % is dominated by its payload figure: sources quote 4 t and 6 t for different orbits.
* Published "payload to LEO" figures rarely state the exact orbit; where the altitude was not given it is
  assumed and flagged.
* Lengths are over-predicted for most vehicles (typically +20–50 %) because the layout factors — skirt,
  intertank, interstage and engine-bay lengths — are assumptions, and because the sized vehicles carry more
  propellant than the real ones.
* The vehicles above were **sized** with the book's loss regression (RMS ≈ 260 m/s), which is an extrapolation
  above LEO and for air launch is replaced by user estimates. Three checks run afterwards — a 3-DoF trajectory
  (`--trajectory`), the load distributions (`--loads`) and a pitch-programme search (`--optimise-ascent`) —
  but none feeds back into the sizing loop, so the GLOM errors in section 1 are errors of the regression-sized
  vehicle. The optimisation finding that a better profile is worth 4 % more payload on the default design is
  therefore a statement about steering, not a correction to the masses above.
* The centre-of-pressure build-up is validated only against the book's Saturn V force list (§6.2 above). No
  vehicle in the table has a published CP or static margin here to check against, and the build-up omits
  viscous crossflow on the cylinders, which biases it forward by an unquantified amount.
* **Nothing downstream of the loads is validated against a real vehicle.** The Chapter 10 stress and buckling
  analysis reproduces all five of the chapter's worked examples (so the equations are right), and the Chapter 12
  control checks reproduce its Saturn V time-to-double, but no vehicle in the table above has published wall
  thicknesses, margins of safety or gimbal budgets to compare with. The monocoque sizing coming out at 2.0× the
  MER mass is self-consistent arithmetic, not a measurement: it is the size of the gap between a monocoque shell
  and whatever construction the fitted relationships actually describe.
* The solid-motor internal ballistics has **no validation case at all**. The book works no example, and the
  burning-rate coefficient is calibrated to each motor's own design pressure rather than measured, so the
  thrust-time curves are statements about grain geometry and cannot be checked against a real motor's trace
  without ballistic data this tool does not have.
* Pegasus XL's wing and fins are not modelled; Falcon 9 is sized as expendable with no recovery hardware;
  Saturn V is sized to a translunar injection modelled as a highly eccentric orbit.
* **The CAD export is checked for internal consistency, never against a CAD application.** Mesh volumes are
  compared against the exact closed form for a faceted solid of revolution, every edge is required to be shared
  by exactly two oppositely-wound triangles, and the DXF is parsed back by a group-code reader written from the
  format specification rather than from the writer. The 3MF is unzipped and re-parsed against the 3MF Core
  Specification's own rules — part structure, namespaces, zero-based indices, outward winding, the six permitted
  units and their scaling — by a reader written from that specification, and its two OPC strings were confirmed
  against a package this project itself produces. No DXF, STL, OBJ or 3MF produced here has been opened in any
  CAD package, because none is available in this environment. The format work is therefore verified as
  *arithmetic and structure* and unverified as *interoperability*.
* **The exact-solid (STEP) route has never run against a real geometry kernel.** `cad_kernel.py` drives CadQuery
  when a user installs it, but CadQuery cannot be installed in this environment — it has no network — so no call
  in that module has reached OpenCASCADE. The tests drive it against a stub that computes each revolved volume
  by Pappus' theorem from the points and axis actually passed, which checks the *geometric content* of the calls
  and, through a deliberately wrong axis, that the guard rejects a bad solid; it cannot show that OpenCASCADE
  accepts the calls or that the workplane convention assumed is the one it implements. In place of that missing
  test the module verifies itself at run time on the user's machine: every solid's kernel volume is compared
  against a closed-form frustum sum and the profile's bounding box, and nothing is written if any part is out by
  more than 1e-6 relative. `--verify-kernel` prints that comparison. Until someone has run it on a real install,
  **treat STEP and BREP as unproven**; the faceted formats are the ones with checks behind them.
* **Delta IV Heavy is the first liquid-strap-on case, and its accuracy is partly inherited.** It lands
  within 0.4 % of the published 733 t lift-off mass, the best of the four strap-on cases, but 62 % of that
  mass is the two Common Booster Cores, whose propellant AND inert masses are both typed in from the
  published figures. Only the core's propellant is solved. The core's own dry mass comes out 24 % below the
  published CBC empty mass, so the headline agreement contains a real error that the typed-in boosters hide.
  Two further things about the vehicle do not fit the model and are declared in the case file rather than
  worked around silently: the real core THROTTLES so it can outlast the boosters, while the tool runs the
  core at one constant mass flow (the case gives it the burn-average 74 % flow, which understates lift-off
  thrust by about a sixth), and the strap-ons are the SAME article as the core on the real vehicle while the
  tool sizes the core and reads the boosters from input. That the two land within 2 % of each other for this
  mission is a result, not a constraint the tool enforces.
* **An imported vehicle is not an independent validation case.** The importer carries what a public source
  publishes — payload, diameters, engine counts, thrust, Isp, propellants — and leaves everything else at the
  base design's assumptions, so an imported file tests the sizing loop against a published payload and nothing
  more. Imported against the hand-written cases for the same vehicles, the shipped example sheet sizes Falcon 9
  8 % and Electron 17 % heavier; the gap is the assumed fields no source carries, and it is larger for the
  smaller vehicle because more of a small vehicle's inert mass comes from assumptions. Growing the table in
  section 1 by importing rows would make it longer without making it stronger, so the twelve vehicles there are
  still the evidence.
* These comparisons show that the model is in the right range and identify which assumptions dominate the
  error. They do not qualify it for design use.
