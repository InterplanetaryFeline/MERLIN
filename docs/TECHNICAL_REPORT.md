# Technical report — Preliminary Launch Vehicle Sizing Tool v0.3

> **Kept for the record.** This describes the model as it stood at v0.3, including limits that have since been
> lifted, such as "no trajectory simulation". For the current tool, read [`USER_MANUAL.md`](USER_MANUAL.md) and
> [`ACCURACY.md`](ACCURACY.md).

## 1. Scope and model

Expendable vehicles built from serial **liquid** and **solid** stages plus, optionally, one set of **strap-on
boosters** burning in parallel with stage 1. Pipeline:

validate inputs → delta-v budget (ideal injection speed, vector Earth-rotation term, ascent losses from the
book's regression or user values, optional air-launch credit, allowances, one margin) → stage delta-v
allocation → coupled fixed-point sizing from the top stage down:

* rocket equation → mission propellant; with strap-ons, the **phase sequence of book Fig. 5.21** is solved
  instead (parallel burn with the mass-averaged Isp of Eq. 5:66, jettison, then the core alone) and the core
  propellant is found by bisection so the phases deliver exactly the allocated delta-v;
* thrust and mass flow from a lift-off T/W, a fixed thrust, or (solids) a given burn time; start-up propellant;
* **liquid**: propellant split by mixture ratio → volumes with ullage and cryogenic shrinkage → tank geometry
  at fixed external diameter (tanks may be narrower than the stage) → MER masses;
  **solid**: grain volume → casing volume = 1.12 × grain (Eq. 8:24) → hemispherical-dome casing → centre-
  perforated grain → casing mass from Eq. 8:18;
* engine/nozzle envelope from the book's dimensioning relations (Eqs. 8:28–8:33) or user dimensions;
* stage layout (skirts, intertank, interstage, forward adapter cone) → component masses → new dry mass;
* burn times and lift-off acceleration feed back into the loss regression (under-relaxed, see §5).

Convergence requires the relative change of GLOM, stage dry masses, loaded propellant, overall length **and**
the delta-v requirement to fall below 1e-9. Convergence is never declared at the iteration limit.

## 2. Default demonstration case (software demonstration, not a vehicle claim)

10 t to 400 km / 28.5° from latitude 28.5°. Requirement **9,408 m/s** (ideal 7,672 − rotation 408 +
book-regression losses 2,144; margin 0). Result: **GLOM 410,003 kg**; stage 1 322,638 kg propellant, 14,156 kg
dry (s = 0.0656), 158 s burn, T/W₀ 1.30, 33.9 m; stage 2 59,037 kg propellant, 2,661 kg dry (s = 0.0666),
385 s burn; overall 54.9 m (L/D 13.7); lift-off CM z = 22.8 m; J_pitch 6.27e7 kg·m² (book-style 5.65e7),
J_roll 7.4e5 kg·m². Variants: 3-stage 355,389 kg; optimised split (0.351/0.649) 397,246 kg (−3.1 %).
Sensitivities: ±5 % Isp → −16 %/+22 % GLOM; ±300 m/s delta-v → −12 %/+13.5 %; loading margin 3 % → +27 %.

New worked examples: `examples/example_solid_smallsat.yaml` — 150 kg to 500 km SSO on three solid stages,
GLOM 40.3 t, implied burn rates 3.0–4.5 mm/s; `examples/example_boosters.yaml` — the default kerolox vehicle
with four solid strap-ons, GLOM 413.1 t, parallel phase 75 s at a mass-averaged Isp of 278.8 s delivering
1,296 m/s before jettisoning 9,970 kg of inert mass.

## 3. Verification actually executed

`python tools/run_tests.py` → **148 passed, 0 failed**. Real `pytest` could not be
installed in this offline sandbox (PyPI unreachable); the tests use only `pytest.approx`/`pytest.raises` and a
minimal compatible shim runs them. **Please also run `python -m pytest -v` in your environment.**

`python tools/verify_workbook.py <workbook>` recalculates each generated workbook in **LibreOffice** and checks
every "should be zero" cell: rocket-equation and mass-closure columns, tank/casing volume checks, the
parallel-burn phase delta-v, the delta-v budget total, the GLOM closure, and the `SUMPRODUCT` recomputation of
the lift-off centre of mass and pitch inertia. All workbooks pass (11–15 cross-check cells each).

Independent bases used by the tests: hand calculations; **book Example 1** (two-step sizing, pp. 480–484 —
stage-2 propellant 51.4 t, GLOM 328.6 t within 0.2 %, tank barrel lengths); the MER worked examples (engine
710/574 kg, thrust structure 1,068 kg, PAF 805 kg, pp. 504–505); **Examples 5–7** for inertia (pp. 527–531);
**Example 3** for engine dimensions (pp. 509–511); **Eq. 5:66 and the Space Shuttle exercise** (pp. 323–325)
for the parallel burn, transcribed independently in the test and compared with the module; numerical
integration of tank and grain profiles against the closed-form volumes; conservation of mass across burns,
separations and booster jettison; delta-v summation; convergence/limit/infeasibility detection.

Two printed intermediate values in the book are **not reproducible from its own equations**, and the tests pin
the equation-consistent values instead of hiding the discrepancy:
* p. 509, Example 3: the printed vacuum thrust 705.2 kN does not satisfy the book's own identity
  T_SL = T_vac − P₁A_e for the stated 698.2 kN sea-level thrust; Eq. 8:29 gives 737.4 kN, which does.
* p. 511, Example 3 step-2 column: the printed nozzle length 1.87 m does not follow from Eq. 8:30 with the
  book's own printed throat and exit diameters, which give 1.65 m.
(Given the book's own T_vac, every other printed dimension of Example 3 is reproduced exactly.)

Defects found and fixed by the tests during this version: the mass-ledger event at strap-on burnout initially
ignored the core propellant burned during the parallel phase (now matched to the phase model to 1e-9); the
workbook's rocket-equation and mass-closure cross-checks were invalid for a parallel-burn stage (discovered by
recalculating the workbook in LibreOffice — the columns now account for the jettisoned strap-ons and direct the
reviewer to the `Parallel_Burn` sheet).

## 4. Key assumptions requiring engineering validation

Loss estimates; effective-Isp weighting (explicit per stage); representative engine/motor performance where no
datasheet was available; layout length factors, nozzle embedding and component CM locations; the 10 % mass-
growth margin; the SRM casing MER (**known to be 20–60 % conservative for modern filament-wound motors — see
the validation report**); the avionics MER's 75 kg / 350 kg step at a 1 t payload; metallic-tank pressure-vessel
inputs (membrane only); methane density; MER scatter (~3 significant digits); constant thrust and Isp per stage
(a front-loaded solid motor is represented by its burn-average thrust).

## 5. Numerical notes

The ascent-loss regression depends on burn times and lift-off acceleration, which depend on the delta-v it
produces. That feedback can oscillate — violently when a low-thrust upper stage is present. Three measures
keep it stable without changing the converged fixed point: the ascent estimate is under-relaxed by 0.5 between
iterations; the lift-off acceleration inside Eq. 3:36 is floored at 1 g₀ (a design that cannot lift off is
still reported by the T/W check); and `mission.losses.ascent_time_override_s` lets the user supply the powered
ascent time when a stage burns after a long coast. If the ascent time still exceeds 3,000 s the tool raises an
explicit error naming the cause instead of diverging.

## 6. Limitations

No trajectory simulation, loads/buckling, stability and control, thermal, boil-off or combustion modelling.
No propellant crossfeed, recovery hardware, multiple booster sets, boosters on a stage other than the first,
throttling profiles, dog-leg ascents or products of inertia. Solid grains are represented by a single
centre-perforated charge (no star/finocyl thrust tailoring). Orbit achievability is not demonstrated.

## 7. Validation summary

**[`docs/ACCURACY.md`](ACCURACY.md) is the authoritative account** and supersedes the figures that used to sit
in this section. The short version, over eighteen real vehicles:

* **All-liquid vehicles: 9.4 % median absolute gross-mass error** (twelve cases).
* **Vehicles with serial solid stages: 33.4 %** (six cases).

The delta-v side is good to a few per cent, checked against published stage masses. The gap between the two
populations is not one mistake: the solid inert-mass model is worse *and* it matters more, because
`dGLOM/dInert` is 0.11–0.79 for liquid vehicles and 1.16–1.87 for solids. The book's SRM casing MER
(k = 0.135 steel, 0.1154 composite) is the single largest contributor, and it is a motor-level constant being
asked to predict stage-level hardware; `solid_inert.py` offers size-dependent alternatives measured against 55
STAR motors. `docs/VALIDATION_REPORT.md` carries the per-vehicle runs.
