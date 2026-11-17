# Mass-estimating relations from outside the book, and why none of them were adopted

The tool's mass-estimating relations (MERs) come from Edberg & Costa, *Design of Rockets and Space Launch
Vehicles*, 2nd ed. (AIAA 2022), with the page and equation number recorded against every coefficient. This
document records what happened when an outside compilation of MERs was evaluated against them, so that the
answer is reproducible rather than remembered.

**Nothing in this document is used by the tool.** It exists because "we looked and here is what we found" is
a more useful record than silence, and because the next person to find the same document should not have to
repeat the measurement.

---

## 1. The document

> R. A. Rohrschneider, *Development of a Mass Estimating Relationship Database for Launch Vehicle
> Conceptual Design*, Georgia Institute of Technology, Space Systems Design Lab, April 2002 (AE 8900
> special project report, advisor Dr. J. R. Olds).

It is a compilation rather than a derivation: relations gathered from fourteen sources (NASA LaRC, NASA MSFC,
Boeing, Marquardt, Raymer's and Roskam's aircraft texts, and others), each tabulated with its originating
organisation, and checked as a set against the Space Shuttle's published mass statement.

Two properties of the document decide most of what follows.

**It is organised around a winged, reusable vehicle.** Its 28 sections are Wing, Tail, Body, TPS, Landing
Gear, Main Propulsion, RCS, OMS, Primary Power, Electrical Conversion & Distribution, Hydraulics, Surface
Control & Actuators, Avionics, ECLSS, Personnel Equipment, Dry Weight Margin, Crew & Gear, Payload
Provisions, Cargo, and then eight propellant and reserve categories. That is the mass breakdown of a Shuttle
orbiter or an airbreathing booster, not of an expendable stack.

**It is in English units throughout** — pounds, feet, psi, pounds-force. Every coefficient would need
converting, which is mechanical but is one more place for an error to hide in a tool whose entire input
convention is SI.

---

## 2. Solid motors: there is nothing here to take

This was the specific question asked of the document, because solid stages are where the tool is weakest
(median GLOM error 33 % against six real vehicles — see `ACCURACY.md` §1).

A full-text search for `solid`, `SRB`, `motor case`, `casing`, `grain` and `propellant grain` across the
document returns four hits in 5,870 lines of extracted text:

| Where | What it is |
|---|---|
| Nomenclature | `SRB — Solid Rocket Booster from Space Shuttle System` (an abbreviation, not a relation) |
| Body / attach structure | `M_stg_attach = 0.000314 · M_strapon` — the mass of the structure attaching an SRB to the core, which *stays with the SRB* |
| Body / attach structure | `M_stg_attach` for the orbiter-to-ET case, same family |
| Body | `M_strapon` appearing in the nomenclature of those two relations |

**There is no casing MER, no grain MER, no nozzle MER and no igniter MER in this document.** It does not
model a solid motor; it models a vehicle that has solid boosters hanging off it, and asks only what the
brackets weigh. The one relation it does give is for hardware this tool accounts for under booster attach
structure, where the book's own relation is already used.

The tool's solid-motor error therefore stands where `ACCURACY.md` leaves it: the remedy is naming a real
motor — `motor.from_database: "Star 37FM"` with `casing_mass_method: mass_fraction`, from the eleven STAR
motors in `config/engine_database.yaml` — rather than letting the casing MER extrapolate. See
`ACCURACY.md` §6 item 1.

---

## 3. Liquid engines: measured, and worse than the book

The document's Main Propulsion section does overlap the tool, so the overlap was measured rather than
assumed. Two relations are directly comparable with the tool's engine mass method:

```
Ref. 1   M_engines = 0.0146 · T_vac · N_eng + 300        (lb, lbf)   LOX/LH2 second stage
Ref. 2   M_main_prop = 0.0205 · T_vac · N_eng            (lb, lbf)   installed T/W of 48.8
```

Both were evaluated against the same 16 engines in `config/engine_database.yaml` that the book's own
Table 8.9 row 1 is measured against (`engine_db.mer_check()`), each with a published dry mass:

| Relation | median error | mean abs error | sd |
|---|---|---|---|
| **Book Table 8.9 row 1 (p.495, what the tool uses)** | **−23.8 %** | **31.9 %** | **36.9 %** |
| Book × 1.221 (the `mer_calibrated` opt-in) | −6.9 % | 26.5 % | 45.1 % |
| Rohrschneider Ref. 1, `0.0146·T + 300 lb` | +19.6 % | 41.9 % | 62.9 % |
| Rohrschneider Ref. 2, `0.0205·T` | +35.1 % | 67.1 % | 90.3 % |

Being exact about what is worse, because one number goes the other way: **Ref. 1's median bias is smaller in
magnitude than the book's** (+19.6 % against −23.8 %), so on the median engine it is no worse. What makes
both outside relations the worse estimator is the spread — 1.3× and 2.1× the book's mean absolute error, and
1.7× and 2.4× its scatter. A relation with a small median and a huge variance is the one that will be badly
wrong on the engine you happen to be sizing.

The reason is visible in the residuals: a pure thrust-proportional rule fixes the
installed thrust-to-weight at about 49 for every engine, so it does well on the Shuttle-class machines it was
drawn from and overpredicts small high-expansion upper-stage engines by factors of two to four. Merlin 1D
comes out at 2,051 kg against a published 470 kg. The book's relation carries an expansion-ratio term and a
fixed offset, which is why it tracks engines from 62 kN to 4,150 kN at all.

This is the measured version of the instruction that governs any overlap: **where an outside relation and the
book disagree, the book is used.** Here the book is not merely the default, it is the better estimator on
real hardware.

---

## 4. Avionics: inapplicable to small expendable stages

`ACCURACY.md` attributes part of the residual error on Vega to the book's two-value avionics step, so the
document's avionics section was checked for a continuous alternative. Its Ref. 1 relation is

```
M_av = K_av · M_dry^0.125        K_av = 1350 (1978 technology), 710 (1990 technology)   [lb]
```

An exponent of 0.125 makes this nearly flat in dry mass, which sets a floor rather than a trend:

| stage dry mass | `K=1350` (1978) | `K=710` (1990) | book's step |
|---|---|---|---|
| 147 kg (Vega AVUM) | 1,261 kg | **663 kg** | 280 kg |
| 400 kg | 1,429 kg | 752 kg | 350 kg |
| 68,000 kg | 2,716 kg | 1,429 kg | 350 kg |

The relation predicts **663 kg of avionics on a stage whose entire dry mass is 147 kg**. It was fitted to
crewed winged vehicles weighing tens of tonnes, where a ~1 t avionics suite is reasonable; extrapolating it
down two orders of magnitude is not a calibration question but a category error. The book's step function is
cruder in form and far closer in value, so it stays.

---

## 5. What would be worth revisiting

For completeness, the parts of the document that *could* matter if the tool's scope ever changed:

- **Wing, tail, TPS, landing gear, hydraulics, surface controls.** The tool has no model for any of these
  because it sizes expendable stacks. If a winged or lifting-body stage were ever added, this document is a
  reasonable starting point and is explicitly validated against the Shuttle as a set.
- **Cryogenic tank insulation** (`M_ins_ox`, and the rule that only cryogenic oxidiser is insulated, and not
  on booster stages). The tool's insulation treatment is simpler. This is the one relation family here that
  is both in scope and not obviously worse; it was not adopted because the book's own treatment is
  consistent with the rest of the tank model and mixing the two would make the tank mass unattributable.
- **Pressurisation feed-system factors** (`M_press = 0.192·ṁ` for an autogenous pump-fed system). Same
  conclusion for the same reason.

None of these change a number the tool currently reports.

---

## 6. Reproducing the engine comparison

```python
import sys, statistics as st
sys.path.insert(0, "src")
from launch_vehicle import engine_db

LB, LBF = 0.45359237, 4.4482216152605
chk = engine_db.mer_check()          # the book's relation, measured
rows = chk["rows"]

def stats(label, f):
    e = [(f(r) - r["published_kg"]) / r["published_kg"] for r in rows]
    print(f"{label:34s} median {100*st.median(e):+7.1f} %  "
          f"mean|err| {100*st.mean(abs(x) for x in e):6.1f} %  sd {100*st.pstdev(e):6.1f} %")

stats("book Table 8.9 row 1", lambda r: r["mer_kg"])
stats("Rohrschneider 0.0205 T_vac", lambda r: 0.0205 * (r["thrust_vac_N"] / LBF) * LB)
stats("Rohrschneider 0.0146 T + 300 lb", lambda r: (0.0146 * (r["thrust_vac_N"] / LBF) + 300) * LB)
```
