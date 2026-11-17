# How close is this tool to real launch vehicles, and why isn't it closer?

Generated from `outputs/validation/validation_results.json` and `outputs/validation/error_attribution.json`
(`tools/run_validation.py`, then `tools/attribute_error.py`). **No parameter has been tuned to match a
vehicle.** Every input in `validation/*.yaml` carries its own source in its `s:` field.

This document answers two questions that the validation report answers only in pieces: *how far off is each
vehicle*, and *which part of the model put it there*. If you only read one thing, read §1 and §5.

---

## 1. The short version

Twenty-four real vehicles, sized from payload and orbit with the delta-v split re-optimised:

| | N | median \|GLOM error\| | mean |
|---|---|---|---|
| **All-liquid vehicles** | 17 | **13.2 %** | 13.3 % |
| **Vehicles with serial solid stages** | 7 | **11.5 %** | 10.5 % |

Both groups now sit near 12 %, which is the headline result: the solid penalty that dominated this document
through v0.25 is gone. Minotaur I, added in v0.27, is the strongest independent check on that — a four-stage
solid spanning 770 kg to 20,785 kg of propellant per motor, predicted to a **mass bias of +2.2 %** using
`book_steel` on its two 1960s Minuteman stages and `kibbey_medium` on its two composite Orion motors, which
is its real construction rather than a fitted choice.

The solid gap is closed. It was median 33.4 % until the composite-cased solid stages were moved off the
book's flat casing constant (Eq. 8:18, k = 0.1154, which carries no scale term at all) and onto Kibbey's
size-dependent NASA relation. Measured on the 16 published solid stages at their published propellant loads,
that one change took the mean absolute stage-inert error from 51 % to 23 % and the median bias from +52 % to
−8 %. Holding everything else constant, across all eighteen vehicles it took the mean absolute GLOM error
**on the as-written splits** from 37.8 % to 18.0 % and left every liquid vehicle unchanged to the
kilogram. That comparison deliberately holds the delta-v split fixed, so the casing relation is the only
variable; the optimised-split figures in §2 average 11.4 % over the same 18 vehicles. See §6.

**The material matters more than the fitting form, so steel cases were deliberately left alone.** Kibbey on
a segmented-steel case is catastrophic — Ariane 5's EAP −45 %, Scout's Algol −49 % — where the book's steel
constant lands within −2 % and +5 %. Scout G-1 therefore keeps `book_steel` on stages 1–2 and uses Kibbey on
3–4, which is its real construction, not a per-vehicle fit.

**Use it for liquid architectures at the ±12 % level, and for composite solid stages at about ±10 %.** Two
cautions remain: a motor below roughly one tonne of propellant is badly served by every relation here (real
inert fractions climb to 0.16–0.19 and nothing reproduces that), and Scout G-1 and Pegasus XL now *under*
predict (−11.5 % and −17.6 %) where they used to over-predict, so the sign of the solid error is no longer
one-directional.

The liquid column moved from 9.4 % because the v0.25 staging optimiser finds better splits than the one that
generated the previous table, not because anything in the mass model changed. For a vehicle the tool already
under-predicts, a better GLOM-minimising optimiser makes the error against the published mass *larger* —
Saturn V goes −8.4 % → −13.2 %. That is the optimiser working as specified.

---

## 2. Every vehicle, measured

`GLOM error` is the optimised-split run against the published lift-off mass. `dv gap` is what the tool asks
of the mission minus what that vehicle's own published masses and Isp actually deliver — positive means the
tool thinks the mission is harder than the real rocket found it. `mass bias` is the tool's predicted stage
inert against the published stage inert **at the published propellant load**, averaged over the stages whose
masses are published; feeding the real propellant removes the delta-v budget, the Isp and the staging split
from that comparison, so what is left is the mass model alone. `dGLOM/dInert` is measured, not assumed: every
stage's inert margin is raised 10 % and the resulting GLOM change is divided by 0.10.

| vehicle | solid | GLOM error | dv gap [m/s] | mass bias | dGLOM/dInert |
|---|---|---|---|---|---|
| Delta IV Heavy | – | +0.4 % | | | 0.11 |
| **Vega** | **YES** | **+0.5 %** | +403 | **−0.1 %** | 0.90 |
| **M-V** | **YES** | **+0.6 %** | **−1,088** | **+34.2 %** | 1.28 |
| Delta II 7920 | – | −0.4 % | | | 0.48 |
| Ariane 5 ECA | – | +2.9 % | | | 0.32 |
| **Vega C** | **YES** | **+4.6 %** | +85 | **−1.9 %** | 0.84 |
| H-IIA 202 | – | +6.0 % | | | 0.24 |
| Firefly Alpha | – | +6.1 % | | | 0.79 |
| H3-24L | – | −6.4 % | | | 0.40 |
| Ariane 64 | – | −10.3 % | | | 0.13 |
| Soyuz-2.1b | – | −10.5 % | | | 0.43 |
| **Scout G-1** | **YES** | **−11.5 %** | +616 | **−33.4 %** | 1.43 |
| Saturn V | – | −13.2 % | −628 | | 0.40 |
| **Minotaur I** | **YES** | **−13.4 %** | +319 | **+2.2 %** | 0.68 |
| Falcon 9 | – | +14.2 % | −123 | | 0.23 |
| Titan II GLV | – | +15.8 % | −213 | | 0.53 |
| **Pegasus XL** | **YES** | **−17.6 %** | +485 | **−23.2 %** | 0.53 |
| Atlas V 551 | – | −19.0 % | | | 0.21 |
| Long March 12 | – | −19.3 % | | | 0.41 |
| SLS Block 1 | – | −20.8 % | | | 0.25 |
| Ariane 62 | – | −23.6 % | | | 0.11 |
| **Epsilon** | **YES** | **−25.2 %** | | | 0.57 |
| Electron | – | +25.8 % | +415 | | 0.53 |
| Zhuque-2 | – | −31.7 % | | | 0.59 |

Two things changed shape in this table when the composite solid relation changed, and both are worth noting.
**The solid errors changed sign.** Vega and Vega C now land at +0.5 % and +4.6 % with a mass bias of
−0.1 % and −1.9 % — essentially exact — while Scout G-1, Pegasus XL and Epsilon moved from over-predicting
to *under*-predicting. A solid estimate from this tool is no longer reliably conservative.
**The solid sensitivities fell**, from 1.16–1.87 to 0.53–1.43, because a lighter, better-estimated stage sits
further from the edge of its own capability. M-V keeps the highest leverage at 1.28 and is also the one case
still on the book relation (see §6).

Blank cells mean the published data needed for that measurement does not exist for that vehicle — per-stage
inert masses for the mass bias, per-stage masses and Isp for the dv gap. Nothing has been estimated to fill
a blank.

**The sensitivity column is the one most worth staring at.** Liquid vehicles sit at 0.11–0.79: a 10 % inert
error moves GLOM by 1–8 %. Solid vehicles sit at **1.16–1.87**: the same 10 % error moves GLOM by 12–19 %.
A solid stage carries a bigger inert fraction and a worse mass ratio, so the fixed point amplifies rather
than damps. **The solid mass model is worse AND it matters more.** That is the whole story in one line.

---

## 3. Why each solid vehicle lands where it does

These six are the interesting cases, and no two fail the same way.

**M-V, +0.6 % — the one the book gets right, for the wrong reason.** Its dv gap is **−1,088 m/s**: the real
vehicle carries over a kilometre per second more capability than the tool asks of the mission. An earlier
revision of this document explained that away as the quoted payload and the published stage masses "not being
from the same flight"; that is not supported — `mission.payload_mass_kg` is sourced "Wikipedia 'M-V':
1,800 kg to a 250 km low Earth orbit", which is the mission modelled. The gap is unexplained, and assuming
otherwise is what nearly produced a bogus loss correction (§6b). That surplus almost
exactly cancels a **+34.2 %** mass bias. Two large errors in opposite directions. M-V is also the only solid
vehicle here whose first stage is **heavier** than the book's constant — inert/propellant 0.153 against
k = 0.1154 — which is a useful corrective to the idea that the book is uniformly conservative about solids.
It is not conservative; it is uncalibrated, and which way it errs depends on the vehicle.

**Vega C, +17.3 % and Vega, +24.8 % — the clean cases.** Modest dv gaps (+174, +389 m/s) and the largest mass
biases in the set (**+62.0 %, +65.2 %**). These are modern filament-wound motors, which are much lighter than
the book's coefficient, and nothing else is going on. Substituting each stage's own published
inert/propellant ratio brings Vega to **+5 %** and Vega C to **+3.4 %**, which is the proof that the sizing
machinery around the coefficient is sound.

**Epsilon, +42.0 %.** No published per-stage inert masses, so no mass bias can be measured. Its sensitivity
is 1.30 and its stages are the same filament-wound class as Vega's, so the same cause is the likely one, but
this is inference rather than measurement and is labelled as such.

**Pegasus XL, +45.4 %.** A +485 m/s dv gap on top of a +42.3 % mass bias, and both are explicable. The dv gap
is an air-launch loss regression that was never fitted to air launch — the published errata replaces the
40 m/s drag figure with the **322 m/s measured on the first flight**, and the tool now carries that. The
mass bias is the usual filament-wound story.

**Scout G-1, +62.3 % — the worst, and the one with the *smallest* mass bias.** Only **+12.4 %**, yet the
largest GLOM error in the set. Two reasons. Its dv gap is the largest (**+651 m/s**, against a loss
regression whose own stated RMS error is 260 m/s), and its sensitivity is the highest (**1.87**). A
four-stage solid sized to the edge of its capability multiplies everything. The low mass bias is itself
two errors cancelling: the book over-predicts Scout's motors by ~50 % while the build-up under-charges its
stage equipment by a similar amount — see §4.3.

---

## 4. The sources of discrepancy, each with its measured size

Ordered by how much damage each does.

### 4.1 The solid casing coefficient is a constant where reality has a strong size trend

**Measured against 55 STAR-family motors** whose loaded and burnout masses are published together, so the
difference is motor inert with no stage equipment in it (`solid_inert.MOTOR_DATASET`):

| propellant | motors | measured inert/propellant | book k = 0.1154 |
|---|---|---|---|
| under 100 kg | 8 | 0.184 | **−36 %** |
| 100 – 500 kg | 20 | 0.092 | **+26 %** |
| 500 – 1,500 kg | 19 | 0.080 | **+44 %** |
| over 1,500 kg | 8 | 0.076 | **+51 %** |

Motor inert fraction falls from ~0.18 at 30 kg of propellant toward a floor near 0.060, so a single constant
crosses the real curve near 150–200 kg and is wrong in opposite directions either side. The fitted
alternative, `star_motor` (`f = 0.0602 + 0.0051 (m_p/4536)^(-2/3)`, MAPE 14 %), is scoped to upper-stage
class: tested against real launch-vehicle *stages* it runs 31 % light, because apogee-kick motors carry no
TVC and no flight structure and are genuinely a different product.

**Effect on a vehicle:** the dominant term for Vega, Vega C and Pegasus. Worth 29 % of lift-off mass on a
three-stage solid carrying 150 kg to 500 km polar.

### 4.2 The ascent-loss regression was not fitted to small multi-stage solids

Book Eq. 3:37–3:38, stated RMS error ~260 m/s. Measured dv gaps: Scout **+651**, Pegasus **+485**,
Electron **+415**, Vega **+389**. All four are small vehicles; the large ones sit at −123 to −628 m/s, i.e.
the regression is generous to them.

On Scout this accounts for roughly **35 of its 62 percentage points** — more than the mass model does. A
four-stage solid that is over in 176 s of burn is not the kind of ascent the regression was fitted to.
`losses.model: user` or the 3-DoF trajectory are the ways out.

### 4.3 Stage equipment that does not scale

The build-up's skirts, avionics, wiring and separation hardware are assumed values that do not change with
stage size. On a large stage they are a rounding error. On a small one they are most of the mass, and the
assumption is badly short:

* Scout stage 3: the real stage carries **237 kg** of equipment on a 98 kg motor. The tool charges **50 kg**.
* Scout stage 4: predicted 73 kg against 41 kg published, **but 36 kg of that is a forward adapter cone**
  that LTV books separately as the heatshield. Like-for-like the error is **−19 %**, not +77 %.

This is the half of the solid problem that is still unmodelled (roadmap **R33**). It has been invisible
because it cancels against §4.1 — and that cancellation is accidental and size-dependent, so **fixing §4.1
alone makes small notional upper stages come out light**. Naming a real motor fixes both at once, which is
why §6 recommends it.

### 4.4 Bookkeeping: the sources do not agree on what a "stage" contains

Three separate instances found:

* **Scout stage 4** — the adapter/heatshield above, worth 96 percentage points of apparent error.
* **Vega C** — stage inert masses differ by **20–54 %** between Wikipedia (11,200 / 3,230 / 929 kg) and
  Zandbergen (13,393 / 4,238 / 1,433 kg) *for the same three motors*. Almost certainly motor-level against
  stage-level, and neither source says which. The case cites the figures it uses.
* **Motor versus stage generally** — the book's k is a motor coefficient; most published "inert masses" are
  stage-level. Comparing them directly is what made solid results unreadable before `MOTOR_DATASET` existed.

When a published figure and a predicted one disagree by more than about 30 %, **check what each contains
before believing the model is wrong**.

### 4.5 The delta-v split matters more than almost anything else

Vega sized with its as-published split is **304 t**; re-optimised it is **171 t**, against 137 t published.
The same vehicle, the same mass model, a 78 % difference. Scout: 54.7 t against 35.2 t. A fixed split that
is far from optimal inflates mass enormously, and for a marginal vehicle the inflation is violent.

The optimiser also **does not know about casing geometry**: on M-V it starves the 2.2 m third stage below
what that diameter can physically hold, and the run falls back to the as-published split and says so.

### 4.6 Smaller contributors, for completeness

* **Engine mass MER** is biased low by about 22 % against 16 real engines; `mer_calibrated` applies the
  measured 1.221 factor.
* **The avionics MER is a step function** — 75 kg below a 1 t payload, 350 kg above it. A small launcher
  just over the threshold is charged 350 kg on an upper stage weighing a few hundred kilograms.
  `avionics_mass_override_kg` exists for this.
* **Solid thrust is modelled as the burn average**, where a real grain is front-loaded. Lift-off T/W comes
  out low (1.12 against ~1.8 for Ariane 5). A modelling choice, not an error, but it matters if you
  constrain on lift-off T/W.
* **Liquid strap-ons are one bulk-density envelope** with no intertank, so the modelled Delta IV Common
  Booster Core is 37.3 m against a real 40.8 m (roadmap R27).
* **An oversized design produces oversized hardware, and the tool says so.** Scout G-1 and M-V both raise
  `ENGFIT` on the as-published split: the nozzle is computed from the thrust the *sized* vehicle needs, and
  a nozzle for a 54 t Scout does not fit on a 1.14 m case. The error is a true statement about the design
  the tool produced, not a bad assumption, and it is left in rather than suppressed by lowering an assumed
  expansion ratio - which would hide the oversizing instead of fixing it.
* **Length is predicted worse than mass, everywhere.** The tool runs long — Vega 60 m against 30 m, Scout
  42.5 m against 22.9 m — because stages are sized at a fixed user diameter and the layout adds generous
  skirts and interstages. Treat predicted length as an upper bound.

---

## 5. What this means for a trade study

**The error is not random, so it does not cancel between architectures.** A liquid-versus-solid comparison
run on defaults is biased against the solid option by roughly the amount in §4.1, amplified by the
sensitivity in §2. On the three-stage solid example that is 29 % of lift-off mass — larger than the margin
most such trades turn on.

Three practical consequences:

1. **A trade whose two architectures sit within 30 % of each other is not decidable on defaults.** Replace
   the solid mass method first (§6), then re-run.
2. **Comparisons within one architecture class are far more trustworthy than comparisons across classes.**
   Two liquid variants, or two solid variants, share their biases; a liquid against a solid does not.
3. **The relative ordering of propellant combinations on the same mission is more reliable than any
   absolute mass**, because the delta-v and loss terms are common to all of them.

---

## 6. What to do about it

**Done, as of v0.26: composite solid stages default to `kibbey_medium`.** The book's Eq. 8:18 constant
(k = 0.1154 for graphite-epoxy) has no scale term, so it predicts the same inert fraction for a 141-tonne
P120C and a 215 kg Altair. Real motors do not behave that way. Measured against the 16 published solid stages
at their published propellant loads:

| relation | predicts | mean \|err\| | mean bias | median bias |
|---|---|---|---|---|
| `book_steel` | motor | 66 % | +60 % | +76 % |
| `book_composite` | motor | 51 % | +40 % | +52 % |
| `star_motor` | motor | 24 % | −11 % | −10 % |
| `kibbey_high` | stage | 36 % | +15 % | +36 % |
| **`kibbey_medium`** | stage | **23 %** | −22 % | **−8 %** |
| `zandbergen_composite_C2` | stage | 38 % | +17 % | +39 % |

`star_motor` measures as well but is fitted to 25–4,300 kg motors; using it on Vega C's 141-tonne first stage
would extrapolate 33× past its range, which its own docstring forbids, so it is not the default. **One
relation was applied to every composite stage rather than picking a technology band per vehicle** — a
per-era band is physically defensible but, chosen after seeing the errors, is indistinguishable from fitting.

M-V is the single solid case left on `book_composite`, and the reason is recorded in its design file: under
`kibbey_medium` its third stage needs so little propellant that two hemispherical domes alone exceed the
casing volume and the geometry is refused. That is downstream of the Δv budget under-asking M-V by
1,058 m/s (§6b), not of the casing relation.

Then, in order of how much they buy you:

1. **Name a real motor for any solid stage.** `motor.from_database: "Star 37FM"` **with
   `casing_mass_method: mass_fraction`** uses that motor's own published inert/propellant ratio. Eleven STAR
   motors are in the database, 112–4,265 kg of propellant, k from 0.0616 to 0.125. This fixes §4.1 and §4.3
   together, because a real motor's mass is a real motor's mass. Naming a motor and leaving a `book_*`
   method in place now raises a `CASEDB` warning, because the real figure would otherwise be loaded and then
   ignored.
2. **For a notional upper-stage-class motor, use `casing_mass_method: star_motor`.** Not for a booster.
3. **Re-optimise the delta-v split** (§4.5) before reading any absolute mass.
4. **Replace the loss model** for a small multi-stage solid — `losses.model: user` with a measured or
   assumed allowance, or run the 3-DoF trajectory (§4.2).
5. **Override the avionics step** on a small launcher just above the 1 t payload threshold.
6. **Read the warnings.** `CASEDB`, `CASESTAGE`, `CASEMARGIN`, `ENGCAL` and `SITELAT` each mark a place
   where the tool knows the answer is suspect.

---

## 6b. The loss model: measured, and deliberately NOT corrected

This section records an attempt that failed, because the failure is the useful part.

The `dv gap` column of §2 is the book loss regression's error, almost directly. If a real vehicle flies its
mission on its published masses and Isp, the Δv those masses deliver *is* the true requirement, so

    gap = (orbit Δv + modelled loss − rotation) − (orbit Δv + true loss − rotation) = modelled − true loss

Seven check cases can supply it: the ones with published stage masses that also use `losses.model:
book_penalty`. Saturn V and Pegasus XL are excluded because they use `user` losses and so cannot calibrate
the book model at all.

Gaps below are on the **as-written** splits, which is how the fits were scored; the
optimised-split column in §2 differs slightly (M-V −1,088).

| vehicle | payload | perigee | Δv gap |
|---|---|---|---|
| Titan II GLV | 3,574 kg | 160 km | −214 m/s |
| Falcon 9 | 22,800 kg | 200 km | −127 m/s |
| **M-V** | **1,800 kg** | **250 km** | **−1,058 m/s** |
| Electron | 300 kg | 500 km | +415 m/s |
| Scout G-1 | 165 kg | 555 km | +559 m/s |
| Vega | 1,430 kg | 700 km | +340 m/s |
| Vega C | 2,300 kg | 700 km | +79 m/s |

The obvious reading is that the model over-charges small vehicles — and it is wrong twice over.

**First, payload and altitude are perfectly confounded in this sample.** Every small-payload vehicle here
flies to 500–700 km SSO and every large-payload one to about 200 km. M-V is the *only* vehicle with a small
payload and a low orbit, which makes it the single point that can tell the two hypotheses apart.

**Second, M-V refutes both of them.** Fitted on the other six, a payload model predicts M-V's gap at
+151 m/s against an actual −1,058 (out by 1,209 m/s); an altitude model predicts −24 m/s (out by 1,034).

Leave-one-out, against the null model of applying no correction at all:

| predictor | LOO RMS, n=6 (M-V dropped) | LOO RMS, n=7 (all) |
|---|---|---|
| *(no correction)* | 334 m/s | **505 m/s** |
| log payload | **201 m/s** | 587 m/s |
| perigee altitude | 287 m/s | 522 m/s |
| sqrt(altitude) | 266 m/s | 519 m/s |
| ascent time | 393 m/s | 679 m/s |
| constant offset | 341 m/s | 589 m/s |

With all seven vehicles, **every candidate correction is worse out-of-sample than doing nothing.** The
encouraging n=6 column exists only because M-V was dropped, and M-V was dropped on an assumption — that its
published masses were sized for an escape mission — which its own design file refutes: `mission.payload_mass_kg`
is sourced "Wikipedia 'M-V': 1,800 kg to a 250 km low Earth orbit", exactly the mission modelled.

So no loss correction is shipped. A fitted factor here would have been a factor that only looks good when
the one inconvenient vehicle is deleted, which is the population-scale version of tuning an input to match a
vehicle. What the tool offers instead is `losses.model: user`, where you supply gravity, drag and steering
losses yourself and the budget says so — which is what Saturn V and Pegasus XL already do.

### 6b.1 The confound was broken in v0.27, and the answer did not change

Two cases were added for exactly this purpose, and one of them is the small-payload/low-orbit example the
analysis above had none of:

| vehicle | payload | perigee | why it was added |
|---|---|---|---|
| **Minotaur I** | 580 kg | **185 km** | a small payload to a LOW orbit, with every stage mass published |
| **Long March 12** | 12,000 kg | 200 km | a large payload to a low orbit; three published pairings on one vehicle |

Minotaur I is the decisive one, because its masses close independently: the four stages plus payload sum to
35,926 kg against a lift-off mass of 36,200 kg published separately, leaving 274 kg for fairing, avionics and
adapter. Its measured Δv gap is **+247 m/s** on the as-written split, **+319 m/s** optimised; the leave-one-out table below uses as-written throughout, as the v0.26 analysis did.

The low-orbit group now spans payloads from 580 kg to 22,800 kg, so payload and altitude are no longer
confounded. The gaps there are **−214 (Titan II, 160 km), +247 (Minotaur I, 185 km), −127 (Falcon 9, 200 km)
and −1,088 (M-V, 250 km)** — a 1,300 m/s spread across four vehicles at essentially the same altitude, with
payloads spanning a factor of forty and no monotonic relationship to either variable.

Re-running the leave-one-out over all eight vehicles:

| predictor | LOO RMS, n=8 |
|---|---|
| *(no correction)* | **481 m/s** |
| sqrt(altitude) | 516 m/s |
| perigee altitude | 520 m/s |
| log payload | 539 m/s |
| constant offset | 548 m/s |

**Still nothing beats doing nothing**, and now that is a much stronger statement than in v0.26: the earlier
version could not tell a payload effect from an altitude effect, whereas this one can and finds neither. The
residual scatter is real, not a missing term in payload or altitude.

### 6b.2 A caution the Long March 12 case produced

CZ-12 was added hoping its three published pairings — 12,000 kg to 200 km, 10,000 kg to 300 km, 6,000 kg to
700 km SSO against one 433 t lift-off mass — would test the budget's altitude dependence with the hardware
held fixed. **They cannot, because the published figures are not mutually consistent.** Circular speed *falls*
59 m/s from 200 km to 300 km and this tool's whole budget moves by 75 m/s, yet the published payload drops
16.7 %; at an upper-stage Isp of 341.5 s that drop implies over 600 m/s of extra Δv. The three figures are
quoted on different assumptions — margin, inclination or launch site — and the 700 km SSO figure is
separately unusable, since SSO needs about 98° and every CZ-12 flight has been from Wenchang at 19.6°
latitude. The case therefore ships as a single mission at its headline figure, and
`tests/test_validation_cases.py` records the inconsistency so that nobody later "fixes" the case to hit all
three, which would mean tuning inputs to match numbers that disagree with each other.

### 6b.3 The shared-core family: what minimal stage sizing cannot reproduce

The large-payload/high-orbit slot is now filled, by a **pair** rather than a single vehicle, and the pair
measures something no single case can.

Ariane 62 and Ariane 64 fly **the same LLPM core and the same Vinci upper stage**. Only the booster count
(two P120C against four) and the payload change. So the A62's core is sized for the *A64's* mission, not its
own: it holds 140,000 kg of propellant where a minimum-mass core for the A62 mission needs about 52,000 kg.
A tool that sizes every stage for its own share of the delta-v must therefore under-predict the A62 heavily
and the A64 much less — and it does:

| | boosters | payload | published | tool | error |
|---|---|---|---|---|---|
| **Ariane 62** | 2 × P120C | 7,200 kg to 500 km SSO | 530,000 kg | 405,226 kg | **−23.5 %** |
| **Ariane 64** | 4 × P120C | 15,500 kg to 500 km SSO | 860,000 kg | 779,654 kg | **−9.3 %** |

**Two more vehicles of the same class, added in the same release, order themselves by the same rule.** All
four are hydrolox cores with large solid boosters — the class R34 unblocked — and they differ in exactly one
respect that matters to a tool which sizes each stage minimally for its own mission: how far the real core is
oversized relative to *that* mission, because a real core is shared across a family.

| vehicle | the core is sized for | published | tool | error |
|---|---|---|---|---|
| **H3-24L** | its own class | 575,000 kg | 552,866 kg | **−3.8 %** |
| **Ariane 64** | itself | 860,000 kg | 779,654 kg | −9.3 % |
| **SLS Block 1** | Block 1B and Block 2 as well | 2,610,000 kg | 2,343,799 kg | −10.2 % |
| **Ariane 62** | the A64, not the A62 | 530,000 kg | 405,226 kg | **−23.5 %** |

Every one comes out light, and the ordering follows the explanation rather than the vehicle size — the
2,610-tonne SLS and the 575-tonne H3 are 6 points apart, while the two Arianes, which share a core and a
launch site, are 14 points apart. `tests/test_validation_cases.py` pins that ordering, so if it ever breaks
this explanation is wrong and should be rewritten rather than patched.

Two independent checks make the group more convincing than the lift-off masses alone. **H3-24L's boosters
come out at exactly their published 67,200 kg**, and **SLS Block 1's length lands at 95.2 m against a
published 98.1 m** — a 3 % agreement on a dimension nothing was fitted to.

That spread is not noise, and it is not a defect to be excused. It is the boundary of what
"size each stage minimally for its share of the delta-v" can represent. A real launcher family amortises one
core across several configurations, and no stage-wise minimal sizer reproduces that. **Read an absolute mass
from this tool as the mass of a minimum vehicle for the stated mission, not as a prediction of what a
manufacturer will build.**

Two further honesty notes on this pair. The A64's closer agreement comes with a *different internal
distribution*: the tool puts 80,473 kg in the core and 55,045 kg in the upper stage, where the real vehicle
has 140,000 and 32,000 — so the lift-off mass agreeing to 9 % conceals a quite different vehicle, and the
GLOM column should not be read as "the stages are right". And the altitude for both is **derived, not
assumed**: no source states it, but sun-synchronicity fixes the inclination/altitude pair through
i = arccos(−(a/12352 km)^3.5), and the published 97.4° gives 500 km (against 97.03° at 400 km and 97.79° at
600 km).

Adding them required fixing **R34**, below, and nothing else. Their tank diameters are narrower than the
real 5.4 m stages, and that is a *consequence* of minimal sizing rather than an independent assumption: a
hydrolox stage's LOX tank is volumetrically about a third of its LH2 tank, and a minimal core's 48 m³ of LOX
does not fill a 5.4 m tank whose end caps alone take 58 m³. The real core's 105 m³ fits that tank with a
2.1 m barrel to spare.

**Long March 6A was tried for this slot first and rejected on data.** Its four FG-112 boosters supply
4,828 kN of a 7,204 kN lift-off thrust and no source publishes their propellant mass, inert mass, Isp or
burn time. Deriving the booster propellant from the published lift-off mass would have meant fitting to the
number the case exists to validate.

### 6b.4 R34, found while adding the pair

Both Ariane cases were initially impossible to size, and the cause was a tool limitation rather than their
data:

* **Long March 6A** (6,500 kg to 500 km SSO) was rejected on data. Its four FG-112 boosters supply 4,828 kN
  of a 7,204 kN lift-off thrust and no source publishes their propellant mass, inert mass, Isp or burn time.
  Deriving the booster propellant from the published lift-off mass would have meant fitting to the number
  the case exists to validate.
The tank geometry check ran at **every iteration including the crude seed**, and the seed under-fills a
hydrolox core whose boosters carry most of the lift-off impulse: iteration 1 asked a 5.4 m tank to hold
about 35 m³ where its end caps alone take 58 m³. The converged stage holds far more and fits comfortably, so
the check was refusing a feasible design for a property only its *first guess* had. The checks now run
inside `tank_sizing.tolerate_oversized_tanks()` while iterating — a tank too wide for its contents reports a
zero-length barrel, which is what an oversized tank physically is — and `size_vehicle` re-checks the
**converged** design with the tolerance released, so a genuinely unbuildable tank still fails with the same
message and the same one-click fixes. The core/booster phasing check was not touched: a stage-1 Δv share
below 0.50 still correctly refuses the A62, because at 1,370 kN and 432 s the core burns 323.4 kg/s and must
carry at least 43,333 kg to outlast the P120C's 134 s.

This had blocked a whole vehicle class — hydrolox core plus large solid boosters, which is Ariane 6, H3 and
SLS.

**What would make this calibratable** is therefore not more vehicles of the same kind but a different
measurement: per-vehicle loss budgets from flown trajectory data, which no public source gives for these
vehicles. A large payload to a HIGH orbit is still missing from the set — Long March 6A (6,500 kg to 500 km
SSO from Taiyuan) is the best candidate and is not yet built. Other vehicles with published figures include
Astra Rocket 3.3, LauncherOne, Terran 1, RS1, Ceres-1, Kuaizhou-1A, Kinetica-1, Shavit, Black Arrow, Diamant
and SS-520-5. Reproduce the table above with `tools/attribute_error.py`.

### 6b.5 Pinned architectures: the same finding, measured from the other side

§6b.3 says a minimal stage sizer must under-predict the smaller member of a shared-core family. The pinned
architecture trade of v0.28 (`architecture.py`, method M102, `python -m launch_vehicle.main architecture`) lets that claim be tested
directly rather than argued: hold one variant's stages and its strap-on unit at the values the sizing loop
converged on, change only how many strap-ons are fitted, re-solve the parallel burn, and bisect the payload.

**The mechanism is exact at the reference count.** Pinned and re-solved, six boosted designs reproduce the
sizing loop's own per-stage Δv to 1 part in 10⁹, the same GLOM and the same lift-off T/W, and the payload
root-find returns the design's own payload to better than 0.1 %. This matters because the existing
`performance.FrozenVehicle` cannot do it: that class carries the parallel phase as one stored number, which on
Ariane 64 is about **−2,900 m/s** — not a contribution but the difference between the serial rocket equation
applied to the core and the phase model's answer for the same stage. Holding a correction that size fixed
while removing half the boosters would have produced a confident, meaningless number. `PinnedVehicle`
re-solves `boosters.phase_sequence` instead.

**And it over-predicts the smaller variants, on both families that publish figures for several counts of one
core.** This is the measurement, not a target:

| pinned core | asked for | published | pinned answer | error |
|---|---|---|---|---|
| Delta II 7920 (9 × GEM-40) | 3 × GEM-40 | 2,800 kg | 3,436 kg | **+22.7 %** |
| Delta II 7920 (9 × GEM-40) | 4 × GEM-40 | 3,200 kg | 3,820 kg | **+19.4 %** |
| Ariane 64 (4 × P120C) | 2 × P120C | 7,200 kg | 10,910 kg | **+51.5 %** |

Delta II figures: Space Launch Report Delta II data sheet (NASA-hosted copy), one table, 185 km × 28.5°, one
core, three counts. Ariane figures: the user-manual values the two design files already carry, 500 km SSO.

Stated as the slope a user actually reads off the sweep, Delta II's real payload ratio from 3 to 9 boosters is
5,100/2,800 = **1.82**; the pinned model gives 5,089/3,436 = **1.48**. Ariane 6's real 2→4 ratio is **2.15**
against the pinned model's **1.42**. Two independent families, same direction, and the two pinned Ariane cores
agree with each other (1.38 from the A62, 1.42 from the A64) while both disagree with reality the same way —
so this is a reproducible property of the model, not scatter.

**Why.** Two causes, and only the first is avoidable in principle:

1. The pinned core is the one the loop drew for the *reference* mission. The tool's A64 core holds about
   78,000 kg where the real shared LLPM holds 140,000 kg (§6b.3). Pin it and move the booster count and you
   have pinned the wrong core for the new architecture — the error of §6b.3 inherited, not a new one.
2. `performance.required_dv_mps` holds ascent time at the reference design's value, by design: "burn times are
   hardware and do not move during a sweep." They do not, but the *trajectory* does. A configuration with a
   third of its boosters removed climbs at a far lower initial acceleration for far longer, and pays a gravity
   loss the accel₀ term alone does not charge it. The loss model has no per-configuration ascent time to give.

**Not corrected.** A factor fitted to these six points would close them, and §6b (and R32) already measured
what happens to such factors under leave-one-out: nothing beat applying nothing. Two families are not a
calibration set, and the correction would be absorbing a core-sizing error under the name of a loss model.
What the tool does instead is print the bias beside every sweep and refuse the configurations that fail on
physics rather than on Δv — a count whose lift-off T/W is at or below 1.0 returns no payload at all, with the
Δv-feasible value moved to a separate field so nothing can read it as a capability.

**How to use it, then.** Differences of one booster either side of the reference count are the model's
useful range. Two or more away, read the direction and not the number, and expect the small variant to be
flattered by roughly 20–50 %. The other direction — `--size-core`, where the loop re-sizes the core for a
fixed booster set — carries none of this bias, because nothing is pinned; it answers a different question
("design a core for these boosters") and is the one to use when the core is not yet built.

### 6b.6 Families: the two errors bracket the answer, and they have one cause

v0.29 added family folders (`families.py`, `python -m launch_vehicle.main family`), and with them the shipped Delta II and Ariane 6
families. A family is the one configuration where this tool's hardest limitation is checkable rather than
arguable, because the variants fly **one core** and each publishes its own figure. Delta II is the better of
the two: three variants, one Extra-Extended Long Tank Thor first stage, one AJ10-118K second stage, and one
published table covering all three.

Sizing each variant **on its own**, which is what the tool does everywhere else:

| variant | tool GLOM | published | error |
|---|---|---|---|
| Delta II 7320 (3 × GEM-40) | 136,843 kg | 152,000 kg | **−10.0 %** |
| Delta II 7420 (4 × GEM-40) | 150,764 kg | 162,000 kg | **−6.9 %** |
| Delta II 7920 (9 × GEM-40) | 231,365 kg | 228,000 kg | **+1.5 %** |
| Ariane 62 (2 × P120C) | 404,877 kg | 530,000 kg | **−23.6 %** |
| Ariane 64 (4 × P120C) | 771,076 kg | 860,000 kg | **−10.3 %** |

Pinning the **reference variant's** core and asking it for each other variant's booster count (§6b.5):

| variant | pinned payload | published | error |
|---|---|---|---|
| Delta II 7320 | 3,446 kg | 2,800 kg | **+23.1 %** |
| Delta II 7420 | 3,830 kg | 3,200 kg | **+19.7 %** |
| Delta II 7920 | 5,100 kg | 5,100 kg | **+0.0 %** (reference) |
| Ariane 62 | 10,910 kg | 7,200 kg | **+51.5 %** |
| Ariane 64 | 15,509 kg | 15,500 kg | **+0.1 %** (reference) |

**The two tables err in opposite directions, and that is the useful part.** Both come from one thing the tool
cannot represent: *a core that is oversized for the mission being flown.* Every stage here is sized for its own
share of the Δv, so

* sized alone, each variant gets its own **minimal** core. The tool's A62 core holds about 52,000 kg where the
  real shared LLPM holds 140,000 kg, so the small variants come out far too light.
* pinned, the reference variant's core is bigger — about 78,000 kg for the A64 — but still far lighter than
  the real 140,000 kg, and a core lighter than the real one **flatters** the payload, because the strap-ons
  are not being asked to lift propellant and tankage this mission does not need.

Real core mass therefore runs *tool's own variant < pinned reference < real shared core*, and the published
payload sits below both estimates. The real A62 pays for sharing the A64's core; the tool never charges that,
in either direction. This also explains why Ariane's errors are roughly twice Delta II's: the P120C/LLPM split
puts far more of the stack in the shared core than GEM-40s/Thor does, so there is more to be wrong about.

**What this does not license.** Two families, five points, and a mechanism that would be fitted rather than
derived — the same situation §6b and R32 measured, where no fitted correction survived leave-one-out. Nothing
is corrected. What the family machinery changes is that the measurement is now **reproducible by anyone**:
`python -m launch_vehicle.main family --name delta_ii --pinned` prints both tables, and a user who writes a manifest for their own family
gets the same two numbers for their own vehicle, with the published figures required to carry a source and to
be marked `reference` so a family can never quietly grade itself against its own assumptions.

**The experiment that would settle it** is now cheap and is R38: pin the core at the family's *real* published
propellant load instead of at the tool's own sizing, and re-run the pinned table. If the error collapses, the
whole of §6b.5 is core sizing; whatever is left is the ascent-time effect of R36. Neither is guesswork once the
family carries the real figure.

---

## 7. What would move the numbers most

From the roadmap, ordered by measured payoff rather than by effort:

| | what | worth |
|---|---|---|
| **R33** | A stage-equipment model that scales with stage size | the other half of the solid error; currently masked by §4.1 |
| **R32** | Flag when a design falls outside the loss regression's fitted population | 35 of Scout's 62 points |
| **R30** | Refuse to extrapolate an affine relation below its fitted floor | prevents a 378 % error that currently just happens |
| **R29** | The avionics step function | the biggest single term on a small launcher |
| **R21** | Close the structure → mass loop | the largest error the tool can see and declines to act on |

---

## 8. Honesty notes

* Six solid vehicles is a small sample, and two of them (M-V and Vega C) were added in v0.21. The medians in
  §1 will move as more are added: they moved from 43.7 % to 33.4 % when the sample went from four to six, and
  that was a change in the sample, not an improvement to the model.
* `mass bias` is measured only where per-stage inert masses are published — four of the six solid vehicles.
* The three attribution columns in §2 **do not sum to the GLOM error**, and are not meant to. A rocket is a
  fixed point; a mass error and a delta-v error interact, and the interaction grows as a vehicle approaches
  the edge of its capability. They are attributions, not a decomposition.
* Published figures disagree with each other (§4.4). Where two sources conflict the case cites the one it
  used, and the disagreement is reported rather than averaged away.
* **The sizing loop's answer does not depend on where it starts.** `size_vehicle` is a fixed-point
  iteration seeded from an aggregate guess, and if the converged answer moved with that guess, every error
  in this document would be partly an artefact of the seed. Swept over s = 0.05…0.18 on five designs — the
  shipped default, the three-stage example, the solid smallsat, Ariane 5 ECA and Delta IV Heavy — the
  converged GLOM is **identical to ~1e-8 relative**, i.e. to the convergence tolerance. Pinned as a test.
  Prompted by Balesdent (2011) App. B, which found a comparable iteration landing on *different* optima
  from different seeds; ours does not. See [`OPTIMISATION.md`](OPTIMISATION.md) §6.
* **Of the 18 check vehicles, 11 fly, 1 is not attempted and 6 fail**, and the reason is not what an earlier
  revision of this document said. It claimed the single-shooting pitch programme "will not reach a GTO
  insertion for a vehicle with strap-ons". That is false, and was inferred from three failures without
  checking the boosted vehicles that succeed: **Soyuz 2.1b flies with four strap-ons** (burnout 202 km,
  γ = −1.3°) and **H-IIA 202 with two** (298 km, γ = −8.2°), while **Scout G-1 and Vega have no strap-ons at
  all and fail**. Ariane 5 ECA is now the one *not attempted*, because it is a GTO mission (see the gating note below). The six
  that are attempted and fail are Atlas V 551, Delta IV Heavy, Delta II 7920, Pegasus XL, Scout G-1 and Vega.
  Measured outcomes, taken before the v0.26 mass change (which lightened the solid vehicles and moved Epsilon
  and M-V into the flown group):

  | design | strap-ons | target | last burn | outcome |
  |---|---|---|---|---|
  | Soyuz 2.1b | 4 | 200 km | 140 s | flown, γ = −1.3° |
  | H-IIA 202 | 2 | 300 km | 518 s | flown, γ = −8.2° |
  | Ariane 5 ECA | 2 | 250 km | **1,892 s** | peak 202 km, never reaches target |
  | Atlas V 551 | 5 | 200 km | **1,595 s** | no kick completes an ascent, γ = −18° |
  | Delta IV Heavy | 2 | 400 km | **1,299 s** | peak 9 km |
  | Delta II 7920 | 9 | 185 km | 709 s | lofts to 668 km, re-crosses at γ = −34° |
  | Vega | 0 | 700 km | **736 s** @ 2 kN | crosses at γ = +10.8° |
  | Scout G1 | 0 | 555 km | 27 s (185 s total) | crosses at γ = +50.6° |
  | Pegasus XL | 0 | 200 km | — | air-launched; no air-launch model |

  The discriminator is the **burn structure**, not the strap-ons. Every failure except Scout and Pegasus has
  a final burn of 700–1,900 s, because the model burns each stage continuously from ignition to propellant
  exhaustion. The real vehicles do not: a GTO mission burns to a parking orbit, **coasts**, and reignites.
  Two consequences follow. The vehicle reaches orbital speed long before its propellant is gone and keeps
  thrusting; and `_steering_alpha` spreads the commanded pitch change over `t_total - t`, the whole remaining
  burn, so with 1,500 s remaining the terminal guidance barely steers at all. Scout and Vega fail at the
  other end — short solid stages flying a genuinely lofted profile the 3 s inter-stage coast cannot represent.

  This does **not** affect the GLOM errors in §1: `convergence.py`, `mass_budget.py` and `delta_v.py` do not
  import `trajectory` at all, and the sizing loop takes its ascent losses from the book regression
  (Eq. 3:32–3:38). What it does mean is that for those vehicles there is no flown-ascent cross-check and no
  stability or control assessment, because both need a converged trajectory. The GUI says so on the
  Trajectory tab instead of presenting the failed attempt as a result.

* **A GTO or GEO mission is no longer flown at all** (`trajectory.UNFLOWN_ORBIT_TYPES`), and the result
  carries `attempted = False`, kept deliberately distinct from `converged = False`. A failed attempt is a
  finding about the vehicle; an unattempted one is a statement about the model, and the two look identical in
  a chart. The published sequences this rests on: Atlas V 551 (ULA MUOS-1 and MUOS-5 booklets) burns Centaur
  for 461 s, coasts 508 s, burns 361 s, coasts 9,000 s, burns 54 s — two restarts; Delta IV Heavy (ULA
  DSP-23) 422 s / 3,751 s / 396 s / 17,297 s / 181 s through a 117 × 851 nmi parking orbit; Delta IV M+(4,2)
  to GTO 517 s / 620 s / 299 s through 185 × 595 km; Vega's AVUM is certified for up to five restarts and
  VV01 flew three burns. **Ariane 5 ECA is the exception that locates the cause in the profile and not the
  orbit**: the Arianespace user manual gives its ESC-A a 945 s nominal single burn, direct ascent, no
  restart capability, and ESA's V187 timeline measures 932 s. Its ascent failed because the tool gives that
  stage 29,730 kg of propellant against a real 14,900 kg, a 1,892 s burn against 945 s — a Δv-split defect
  surfacing in the trajectory module, not a guidance one.

  Source caveat, which matters because this project does not accept unverified references: every figure in
  that paragraph was read through a text summarizer, because the workspace's egress proxy blocks direct PDF
  download from `ulalaunch.com` and the other hosts. The summarizer mis-aligned columns on its first pass
  over one ULA booklet and had to be re-fetched. MUOS-1/MUOS-5 and DSP-23/EFT-1 cross-validate each other
  structurally, which is why they are quoted. **Treat the individual times as provisional** until re-read
  from the PDFs directly; the restart *structure* is corroborated by the vehicles' user guides in text
  ("The standard Delta IV GTO mission profile uses two burns of the second stage", and the Atlas V guide's
  section headings for two- and three-burn Centaur ascents).
* **The optimised columns in this document come from a search that is local**, run from several starts with
  the spread between them reported. On the cases here the starts agree to 0.000 %, which is evidence and
  not a proof of global optimality. The same document records a case where the optimiser silently returned
  its own starting point, which is why it is now measured rather than assumed.
