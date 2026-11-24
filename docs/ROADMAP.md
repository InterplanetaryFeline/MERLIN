# Roadmap and book-coverage matrix

Two questions, answered in order:

1. **What does the tool already do, measured against what the book covers?** — section 2, chapter by chapter.
2. **What should be built next to make it genuinely useful to a launch-vehicle designer?** — sections 3 to 7,
   in priority order with effort estimates and the book sections each item implements.

Reference throughout: Edberg & Costa, *Design of Rockets and Space Launch Vehicles*, 2nd ed., AIAA 2022
(printed page numbers; PDF page = printed + 35), with the published 1st-edition errata applied
(`docs/ERRATA_COMPLIANCE.md`).

---

## 1. Where the tool stands (v1.2.1, and the unreleased cost and ascent work)

It sizes an expendable multistage vehicle from a mission statement and closes the mass budget, then analyses
that vehicle: a 3-DoF ascent trajectory and its optimisation, ground and flight loads with a user's own
winds-aloft profile, shell stress and buckling, aerodynamics and stability, solid internal ballistics, payload
environments, development, production and per-flight cost, performance envelopes, Monte-Carlo uncertainty, optimum
staging, trade studies, multi-design comparison, and from the command line launcher families and pinned-architecture
trades. Drag comes from the vehicle's own geometry. The ascent is flown to orbit with linear tangent steering, cutoff, a coast and a
restart, the tab says whether the orbit is reached, and the sizing can use the losses of that flight. Propellants,
combinations and tank materials can be the user's own. A drop-zone study exists and its tab is hidden. It exports a report, an Excel
workbook, DXF/STL/OBJ/3MF, and STEP through an optional geometry kernel. **108 engineering methods** are
registered with their book page, assumptions, limits and verification basis; **24 real
vehicles** are in a validation set with the errors published rather than tuned away, and `docs/ACCURACY.md`
attributes each error to its cause. The GUI is the primary interface, and a Windows app packages it.

What it is **not**: little is fed back (only the ascent losses, when asked for). The structure is never re-sized to carry the loads it is shown to
need, the vehicle is never re-sized around the better ascent the optimiser finds, and no motor casing is
re-sized for the chamber pressure its own grain would reach. It cannot represent a reusable vehicle at all.
And its answers carry a measured median absolute error on lift-off mass of **13.2 % for all-liquid vehicles and
11.5 % for vehicles with serial solid stages** — see [`ACCURACY.md`](ACCURACY.md) for where each error comes
from, and section 3b for the plan to do something about it.

<details>
<summary>The v0.6 version of this section, kept for the record</summary>

It sizes an expendable multistage vehicle from a mission statement and closes the mass budget: liquid stages,
solid-motor stages, strap-on boosters in parallel burn, tankage and motor-case geometry, an inboard profile,
mass properties with inertias, dimensioned drawings, an Excel engineering workbook with live cross-check
formulas, a self-contained design report, and a local GUI. On top of that it now answers the three questions a
designer asks next: **what does this vehicle lift to other orbits** (performance curves), **how wrong could the
mass be** (a Monte-Carlo over the MER scatter), and **is the stage split right** (the book's closed-form optimum
beside the numerical one) - and a design can fly **real engines** from a sourced database instead of rubber ones.
59 engineering methods are registered with their book page, assumptions, limits and verification basis; 236 tests
pass; 12 real vehicles are in a validation set with the errors published rather than tuned away.

What it is **not**: there is no trajectory *optimisation*, no loads, no stress, no stability and control, no
thermal, no cost. Those are where the roadmap goes next.

</details>

---

## 2. Book-coverage matrix

Legend: **full** = the book's method is implemented and verified against the book's own worked example where one
exists · **partial** = part of the chapter's method is in, with the gap named · **none** = not implemented ·
*(n/a)* = narrative, history or process chapters with no calculation to implement.

### Chapter 1 — Launch vehicles: introduction, operation, the design process (pp. 1–36)

| Section | Topic | Status | Notes |
|---|---|---|---|
| 1.2 | Anatomy of an LV | **full** | the component set the layout model builds (tanks, skirts, intertank, interstage, fairing, PAF) |
| 1.3–1.4 | Launch phases, mission elements | **full** for the ascent | mass events, and an events timeline of the flown ascent (M105) |
| 1.5 | The design process | **partial** | the tool implements the sizing loop of the process; the trade and requirements-flow parts are manual |
| 1.6–1.7 | Launch sites and selection | **partial** | a library of 30 sites by continent; no site-selection trade and no range azimuth limits |
| 1.8–1.9 | The space industry | *(n/a)* | |

### Chapter 2 — Technical history (pp. 37–146)

*(n/a)* as a calculation, but it is the source of the validation set: vehicles described here are among the
24 modelled in `validation/`, whose published masses are the benchmark in `docs/ACCURACY.md`.

### Chapter 3 — Missions, orbits, energy requirements (pp. 147–210)

| Section | Topic | Status | Where |
|---|---|---|---|
| 3.2 | Orbital parameters, vis-viva, period, energy | **full** | M01–M03; book Examples 3.1–3.2 reproduced |
| 3.3 | Mission orbits (LEO, SSO, GTO, GEO) | **full** | M07 SSO inclination, GTO/GEO transfer budgets |
| 3.4 | Required energy: all three loss models | **full** | M37 (Eqs. 3:35–3:38), M50 (Eq. 3:32), M51 (Eqs. 3:33–3:34) — all three fits available and cross-checked |
| 3.5 | The LV velocity vector, launch-site speed | **full** | M04–M05, book Example 3.9 reproduced (errata `sin β` form) |
| 3.6–3.7 | Direct orbit; inclination below latitude | **partial** | azimuth from inclination is in (M06); **dog-leg manoeuvres are not** |
| 3.8 | Performance curves (payload vs orbit) | **full** | done in v0.5, R1 |
| 3.9 | Launch windows | **none** | RAAN/launch-window geometry; see R10 |

### Chapter 4 — Propulsion (pp. 211–270)

| Section | Topic | Status | Where |
|---|---|---|---|
| 4.2–4.3 | Thrust equation, rocket equation, Isp, c*, C_F | **full** | M09, M15, M16; Eq. 8:1 in the errata-corrected form |
| 4.4 | Solid-propellant motors, burn-rate law | **done in v0.8** | M43's implied-burn-rate check plus a full equilibrium internal-ballistics solution (M81–M83) for the two grain shapes the book describes completely. No erosive burning, no ignition transient, no temperature sensitivity, and no star or finocyl grains — the book gives equations for none of those |
| 4.5 | Liquid engines | **partial** | engine mass and envelope MERs (M29, M45); feed system is a per-engine mass input |
| 4.6 | Engine performance examples | **full** | a database of 35 engines and 16 motors, R2 |
| 4.7 | Power cycles (gas generator, staged combustion, expander, electric) | **partial** | a cycle carries a usual chamber-pressure band and raises a warning outside it, and a pressure-fed engine is costed as one; it does not change Isp or mass |
| 4.8–4.9 | Aerospike, hybrids | **none** | out of scope for now |

### Chapter 5 — Performance and staging (pp. 271–336)

| Section | Topic | Status | Where |
|---|---|---|---|
| 5.1–5.4 | Mass categories, Δv in free space, SSTO | **full** | M11 (errata-confirmed σ convention), M09 |
| 5.5–5.6 | Staging, multistage Δv | **full** | M12, M14 |
| 5.7 | Payload ratio | **full** | reported; plus the errata's PAYFRAC plausibility check (M53) |
| 5.8–5.9 | Unrestricted staging, optimum split, TSTO families | **full** | numerical optimisation of the Δv split (M36), and the analytical Lagrange optimum of §5.8 beside it (R4) |
| 5.10 | All-hydrogen Saturn V study | **full** (as a capability) | the propellant-combination comparison does exactly this kind of study |
| 5.11 | Parallel burns and staging | **full** | M44, Eqs. 5:65–5:66, three-phase Fig. 5.21 structure, book Shuttle exercise reproduced |
| 5.12 | Design sensitivities | **full** | one-at-a-time sensitivity studies, and a Monte-Carlo with a tornado (R3) |
| 5.13 | Determining component mass values | **full** | Eqs. 5:84–5:91 are the aggregate sizing path |

### Chapter 6 — Ascent trajectory analysis and optimisation (pp. 337–406)

| Section | Topic | Status |
|---|---|---|
| 6.1–6.3 | Vertical/inclined/general flight with gravity, drag, thrust | **done in v0.6** |
| 6.4 | LV aerodynamics (C_D, normal force, centre of pressure) | **done**: normal force in v0.7, drag from the geometry in v1.1 (not a book method) |
| 6.5–6.6 | Getting to orbit; trajectory simulation | **done in v0.6**; the orbit check in v1.1 (M105); flown to orbit in v1.3 (M108): linear tangent steering, cutoff, coast and restart, rotation, air launch |
| 6.7 | Trajectory optimisation (gravity turn, pitch programme) | **done in v0.7** (M71–M73): the book's trade searched within the gravity-turn family, with the limits of Fig. 9.36. Not a free-profile optimal-control solution — no costate equations, no GPOPS-class solver |
| 6.8–6.9 | Example launch profiles | used in v1.3 to check the ascent (Pegasus, Saturn V; `docs/ASCENT_VALIDATION.md`) |

**What is left here:** wind and lift, plane changes and apogee burns, engines shut down in flight, and an optimal-control
steering law. The feedback into the sizing exists (M109) and is off by default.

### Chapter 7 — Structures and layout (pp. 407–462)

| Section | Topic | Status | Notes |
|---|---|---|---|
| 7.6–7.7 | Tank dome shapes; spherical vs cylindrical | **full** | Table 8.2 dome family, errata-checked √2 EH coefficients, common bulkhead |
| 7.10 | Engine configurations, layout considerations | **partial** | engine count and ring layout drive the aft skirt and inertia; no clustering/gimbal-envelope check |
| 7.11 | Payload accommodations | **full** | PAF (both MERs), envelope, fairing fit check, widening adapter |
| 7.12 | Structure types (skin-stringer, monocoque, isogrid, sandwich) | **partial** — monocoque is sized in full (M74–M78); the stiffened types are named but not sized, because the book gives no allowables for them |
| 7.13 | Structural materials | **partial** | a tank-material table exists for the pressure-vessel option only |

### Chapter 8 — Sizing, inboard profile, mass properties (pp. 463–544) — *the tool's core*

| Section | Topic | Status | Where |
|---|---|---|---|
| 8.1 | Inboard profile | **full** | M33, geometry/layout module, drawings |
| 8.2 | Step mass calculations | **full** | M12, M13 |
| 8.3 | Liquid system real-life additions (start-up, residual, ullage, pressurant, insulation) | **full** | M17–M19, M27 |
| 8.4 | Other components (skirts, interstage, fairing, PAF, avionics, wiring) | **full** | M28, M32, M46 |
| 8.5 | Solid propulsion sizing | **full** | M40–M43, Eqs. 8:17–8:24 |
| 8.6 | Upper steps and fairings | **full** | incl. the errata's step-1 fairing accounting |
| 8.7 | Mass estimation process (all MER tables) | **full** | M24–M32, M45; book Examples 1–3 reproduced |
| 8.8 | Tank/shell thickness calculation | **done in v0.8** | membrane sizing (M26) plus the full Chapter 10 required-thickness set: axial, hoop, buckling and minimum gauge over every load case (M74–M78) |
| 8.7.8 | Mass properties, CM, inertia | **full** | M34, M38, M39; book Table 8.22 reproduced within 1 % |

### Chapter 9 — Ground and flight loads (pp. 545–622)

| Section | Topic | Status |
|---|---|---|
| 9.1 | Load cases (pre-launch, lift-off, max-q, max-g, staging) | **done in v0.7** (M66, M68): ground wind and max-q/max-qα, marched station by station; the max axial-g case remains a separate sizing check |
| 9.2 | Max-q air load calculation (the Saturn V worked example) | **done in v0.7** — reproduced from the book's published inputs as the verification case (`tests/test_loads.py`, VALIDATION_REPORT §6) |
| 9.3 | Load curve rules of thumb | **done in v0.7** — the closure rules of p.606 are asserted on every case |
| 9.4–9.8 | Global vs local loads, CFD/FEM, high-altitude winds, fin loads | **none** — the AMR 95 % wind envelope is used (p.572), but no local pressure distributions, no fins, no CFD |

Done as R8 in v0.7. Chapter 9 gives a *load*; Chapter 10 turns it into a stress and a thickness (R7, v0.8).

### Chapter 10 — Stress analysis (pp. 623–668)

**mostly done in v0.8** (M74–M78). Strength, buckling allowables and pressure stabilisation are all implemented
and every worked example in the chapter is reproduced. Still absent: the combined stress state (which the
chapter also declines to do, p.649), the stiffened constructions of Sec. 10.3.3, domes and bulkheads, joints and
cut-outs, and finite-element anything (Sec. 10.6).

### Chapter 11 — Environments: vibration, shock, acoustic, thermal (pp. 669–712)

**partly done in v0.9** (M86). The quasi-static load factor table a payload planner's guide opens with is produced for the designed vehicle, in the format of the chapter's own Ariane 5 and Atlas V tables. The acoustic, shock and thermal environments are not: the chapter describes them without giving a prediction method for any, and the dynamic half of a load factor needs a coupled-loads analysis this tool cannot do.

### Chapter 12 — Stability and control; vibration and instabilities (pp. 713–794)

**partial, and as far as this book allows.** Centre of pressure, static margin and the pitching-moment slope
(M70), and the rigid-body control checks of Sec. 12.3.6 — controllability, time to double, gimbal deflection
budget (M79–M80). Absent, because the chapter gives no equations for them: slosh (which it declines explicitly,
p.778), body bending, tail-wags-dog, POGO, and anything in the frequency domain — no transfer functions, no root
locus, no gain or phase margins.

### Chapters 13–16 — Manufacturing, systems and pad facilities, testing and reliability, failures

Mostly *(n/a)* for calculation, with **one exception that was dismissed too quickly here and should not have
been**. Sec. 15.2.6 gives the k-of-n engine reliability relation in full —
R_s = sum_{j=k}^{n} C(n,j) R^j (1-R)^(n-j) — with two worked examples to check an implementation against
(3-of-5 at R = 0.95 gives 99.88 %; 7-of-9 at R = 0.95 gives 99.164 %, which is *worse*, the point of the pair)
and Table 15.4's measured liquid-engine reliability statistics to supply R. That is a complete, verifiable
method, and it bears directly on an input the tool already has: `n_engines`. The default design's own comment
says six engines "gives one-engine-out T/W margin", and nothing in the tool had ever checked what that buys.
Done in v0.15: see R24.

Sec. 14.9 (recovery and reuse) is genuinely descriptive: Table 14.3 lists recovery modes with their
advantages and complications, and there is **no numbered equation in the section** — confirmed by scanning
it rather than assumed. Anything built for R12 is therefore physics the tool already owns (the rocket
equation applied to declared burns) plus declared hardware masses, not a book method.

### Chapter 17 — Financial analysis and project management (pp. 975–1022)

**done, apart from reuse.** The five development CERs (M84), with their factors, work-year values and inflation; the
production, learning and operations relations from Koelle's TRANSCOST handbook, which the chapter defers to (M106-M107); and
the chapter's rules of thumb and real prices as cross-checks (M85). All of it in work-years first, on a Cost tab.
`docs/COST_VALIDATION.md` measures it. Reusability economics (Sec. 17.7) is not covered.

### Coverage summary

*(revised at v0.14.1 — the table below had not been updated since v0.6 and said "not started" for four
areas that have since been delivered.)*

| Area | Chapters | Status |
|---|---|---|
| Orbits and energy requirements | 3 | essentially complete; launch windows (R10) outstanding |
| Propulsion sizing relations | 4, 5 | complete, including cycles and solid internal ballistics |
| Staging and performance | 5 | complete, numerical and analytical optimum both |
| Structures, layout, sizing, mass properties | 7, 8 | complete — this is the tool's centre, and where its measured error is |
| Trajectory | 6 | done (v0.6–v0.7), including the ascent optimisation the book declines to solve |
| Loads, stress, control | 9, 10, 12 | done (v0.7–v0.8); the structure result is **not fed back** into sizing |
| Environments | 11 | quasi-static load factors only; the book gives no prediction method for acoustic or shock |
| Reliability | 15 | k-of-n engine reliability done in v0.15, see R24 |
| Recovery and reuse | 14.9, 17.7 | **not started**; the book is descriptive here, see R12 |
| Cost | 17 | development, production with learning and operations done; no reuse economics |

---

## 3. Roadmap

Ordered by value to a designer per unit of effort. "Effort" is an engineering estimate for one developer:
S = days, M = one to two weeks, L = several weeks.

### Phase A — make what exists more usable (mostly delivered in v0.4)

| # | Item | Book | Effort | Status |
|---|---|---|---|---|
| **R0a** | **Single-file design report** — every input with units, description, source and provenance; Δv budget; mass statement and full ledger; geometry; drawings; checks; method register; limitations | 8 | M | **done in v0.4** (`docs/USER_MANUAL.md` §Report) |
| **R0b** | **GUI** — browse and edit every annotated input, size, compare against a baseline, see the drawing and the report, download workbook/report/overrides | — | M | **done in v0.4** (`python tools/gui.py`) |
| **R1** | **Performance curves**: payload against orbit altitude and inclination for the *built* vehicle - the carpet plot of §3.8. Implemented as a frozen-hardware model plus a bisection on payload, so a full envelope costs no re-sizing and runs in well under a second. Report section 5; `--performance` | 3.8 | S | **done in v0.5** |
| **R2** | **Engine and motor database** with cycle types: 13 real engines and motors (Merlin 1D and 1D Vacuum, RD-180, RL10B-2, RL10C-1, Vulcain 2, HM7B, Rutherford, P80FW, Zefiro 23, Orion 50S XL, GEM-40, AJ-60A), each with its own cited source and a `published`/`approximate` confidence, referenced by `from_database`. A row is a *default, never an override*: a field the design states is kept and the disagreement is reported. Power-cycle pressure bands flag an implausible chamber pressure | 4.5–4.7 | M | **done in v0.5** |
| **R3** | **Uncertainty**: every MER carries a documented 1-sigma scatter and the sizing loop is resampled, so the answer is an interval with a tornado of what drives it, not a false-precision number. On the default design: GLOM 372 / 415 / 474 t at the 5 / 50 / 95 percentiles, with residual propellant and delivered Isp the two biggest contributors. Report section 9; `--uncertainty` | 5.12, 8.7 | M | **done in v0.5** |
| **R4** | **Analytical optimum staging**: the Lagrange closed form of Eqs. 5:32–5:33 beside the numerical search, plus Eq. 5:40 for how much another step is worth. The gap between the two prices the closed form's fixed-sigma assumption - about 4 % of GLOM on the default design. Report section 10; `--staging` | 5.8 | S | **done in v0.5** |

**Phase F (section 3b below) is the current plan, written at v0.14.1 from the measured accuracy of the
thirteen check cases rather than from what sounded worth building.**

**Phases A and B are complete.** **Phase C is complete as of v0.8**: R8, R7, R9 and R6. **Phase D is partly done in v0.9**: R11 (cost) and R13 (payload environment, the quasi-static part); R10 (launch windows) and R12 (reusability) are not started, R12 having been skipped deliberately. **Phase E is complete as of v0.10** except for two named gaps: R14, R17, R15 and R16 are done, with no public dataset to import under R16 — explained in the row below (R15's missing STEP was closed in v0.14 through an optional kernel). Wiring the comparison table into the GUI also remains.

### Phase B — the trajectory, and everything it unlocks

| # | Item | Book | Effort |
|---|---|---|---|
| **R5** | **3-DoF ascent trajectory simulation**: point-mass integration with a standard atmosphere, drag from a C_D(M) table, a gravity-turn/pitch-programme steering law, staging events and fairing jettison. Outputs: actual gravity, drag and steering losses (replacing the regression fit), the altitude/velocity/dynamic-pressure history, max-q and its Mach number, the staging state, and whether the orbit is actually reached. **Everything in Phase C depends on this.** Verify against the book's own §6.8–6.9 profiles and against the loss figures of the validation vehicles | 6.1–6.6 | L |
| ~~**R5b**~~ | **Trajectory optimisation — done in v0.7.** Pattern search over hand-over altitude, angle-of-attack allowance and vertical rise, with the pitch kick solved by shooting inside every evaluation so the target altitude is always met; objective burnout speed, priced in payload on a frozen vehicle. The optimum sits on the qα limit, +93 m/s and +430 kg on the default design. The book poses the problem and declines to solve it (p.383), so the objective and trade are its and the search is supplementary. What it does **not** do is turn the tool into "find the best vehicle": the optimisation does not feed back into the sizing loop, which still uses the regression losses | 6.7 | L |
| ~~**R5c**~~ | **Aerodynamics — done. Drag from the vehicle's own geometry added in v1.1 (M104, `docs/DRAG.md`).** Drag in v0.6 (book Fig. 6.13, a user table, a ZOOM lift/drag file reader); the normal-force and centre-of-pressure build-up in v0.7, with static margin and the pitching-moment slope through the whole atmospheric ascent. R9 can start from it. Cylinders carry no normal force, per the book's own first-order assumption, which biases the CP forward — stated in the report rather than hidden | 6.4 | M |

### Phase C — loads, structure, control (each needs R5)

| # | Item | Book | Effort |
|---|---|---|---|
| ~~**R6**~~ | **Solid-motor internal ballistics — done in v0.8** (M81–M83): burning area from grain regression, equilibrium chamber pressure assembled from Eqs. 4:32, 4:33 and Table 4.4, and the thrust-time curve, with the burning-rate coefficient calibrated to the motor's own design pressure rather than invented. Two qualifications on this row as written: **star and finocyl are not implemented**, because Fig. 4.12 draws those grains without dimensioning them, so only the end burner and hollow cylinder the book describes fully are offered; and it does **not** "let the tool shape thrust" — the profile is computed and compared with the sizing, not fed back into it. The finding is that the simplest grain cannot deliver the constant thrust the sizing assumes, by a factor of 5 on the example vehicle | 4.4 | M |
| ~~**R7**~~ | **Structural analysis — done in v0.8** (M74–M78): axial plus bending stress, hoop from pressure and hydrostatic head, buckling allowables pressurised and unpressurised, the SP-8019 frustum criterion, required thickness per shell per load case, minimum gauge, and the sized monocoque mass beside the MER mass. All five of Chapter 10's worked examples are reproduced. What is **not** done, and was over-promised in this row: the stiffened concepts (honeycomb, isogrid, skin-stringer) are **not** sized, because Sec. 10.3.3 names them without giving allowables or mass-per-area laws for any of them; and the result is **not** fed back into the sizing loop, so structural mass is still the MER. The monocoque sizing coming out at 2.0x the MER mass is the measure of what stiffening buys, and is the honest version of the "fix for the biggest known error" — the fix itself needs stiffened-shell allowables from outside the book | 7.12, 8.8, 10 | L |
| ~~**R8**~~ | **Load cases — done in v0.7.** Ground wind (Eqs. 9:20–9:23) and flight at both max-q and max-qα, with gimbal trim and inertia relief; axial, shear and bending marched station by station; the Saturn V examples of §9.2 reproduced as the verification case. Three internal inconsistencies in the book's own Chapter 9 were found and are documented in VALIDATION_REPORT §6. Feeds R7 | 9 | M |
| ~~**R9**~~ | **Stability and control — done in v0.8** (M79–M80): centre of pressure against centre of mass through flight with static margin and the pitching-moment slope (v0.7, R5c), plus the three rules of thumb of Sec. 12.3.6 — controllability ratio, time to double (Eq. 12.4), steady-state gimbal deflection — and the Table 12.4 deflection budget. The Saturn V's 3.31 s time to double is reproduced from the book's own numbers, and two slips in that example are documented. The **slosh frequency estimate** in this row is withdrawn rather than delivered: Chapter 12 declines slosh analysis outright (p.778) and gives no equation for bending or POGO either, so there is nothing to implement from this book | 12.1–12.3 | M |

### Phase D — the questions that decide programmes

| # | Item | Book | Effort |
|---|---|---|---|
| **R10** | **Launch windows and mission design**: RAAN alignment, window duration, plane-change and dog-leg penalties for an inclination below the site latitude | 3.7, 3.9 | M |
| ~~**R11**~~ | **Cost model — done in v0.9** (M84–M85): the five TRANSCOST development CERs the book prints, with the f-factors, work-year values and inflation; cost per flight and cost per kilogram beside GLOM; real prices for comparable vehicles from Table 17.5. Two qualifications on this row as written: **there is no learning curve and no per-flight CER**, because the production submodel, f4 and the operations model are all deferred to Koelle's handbook — per-flight cost is Sec. 17.5.3's rule of thumb and is reported as the factor-of-60 range that rule supports; and **reusability economics is not covered**, which belongs with R12 and was skipped | 17 | M |
| **R12** | **Reusability** — **re-scoped in Phase F, see section 3b.** The book citation on this row was optimistic: Sec. 14.9 is descriptive and has no numbered equation, so this cannot be "implement the book's method". What it can be is honest bookkeeping of a declared recovery budget | 14.9 (descriptive only) | L |
| ~~**R13**~~ | **Payload environments — partly done in v0.9** (M86): the quasi-static load factor table by flight event, in the format of the two real planners' guides the book prints, with the steady half computed from this vehicle's own flight. The **acoustic and shock specification is not produced** — Chapter 11 describes ignition overpressure, lift-off acoustics, buffet and pyrotechnic shock without giving a prediction method for any of them — and the **coupled-loads inputs are not either**, because the dynamic half of a QSL needs structural modes this tool does not compute. Both gaps are stated in the report rather than filled | 11 | M |

### Phase E — quality of life

| # | Item | Effort |
|---|---|---|
| ~~**R14**~~ | **Multi-design comparison — done in v0.9** (M87), as a `compare` command rather than in the GUI: several designs sized and tabulated with GLOM, length, payload fraction, delta-v and each one's warnings, with a CSV, a chart and a page. Wiring the same table into the GUI remains | S |
| ~~**R15**~~ | **CAD export — mostly done in v0.10** (M88): a layered DXF R12 inboard profile (outer mould line, stations, tanks and domes, grain and bore, nozzles, strap-ons, payload envelope, dimensions, each on its own layer), the outer mould line revolved into closed triangle meshes and written as **STL and OBJ**, and an isometric view rendered from those same meshes. **Completed in v0.14**: 3MF added (units and part names, which STL has neither of), and STEP/BREP/glTF through an OPTIONAL CadQuery kernel the user installs. CadQuery is not installable in this environment, so the kernel route has never reached OpenCASCADE here; instead it verifies itself at run time, comparing every solid's kernel volume against a closed-form frustum sum and refusing to write anything that disagrees by more than 1e-6 (`--verify-kernel` prints it). Faceted exports are checked here as before (exact faceted volumes, edge-manifoldness, the 3MF re-parsed against its specification, the DXF parsed back with an independent reader). What no test here can show is that the files open correctly in a CAD application, and that check has not been run | M |
| ~~**R16**~~ | **Vehicle-data importer — done in v0.10** (M89): a declared CSV/JSON vehicle sheet becomes an annotated design YAML, each imported leaf tagged `t: reference` with its own source, everything else left at the base design's value and listed in an import report. Two corrections to this row as written. **launchercalculator.com publishes no data**: it is a calculator the user types parameters into — no download, endpoint or API — so there was nothing to import from it. **Wikipedia infoboxes cannot be imported blind**: one cell routinely holds several vehicle variants (Falcon 9's mass cell gives three), so the infobox path is a transcription aid that refuses any field not reducing to a single figure and lists it as ambiguous. The sheet path is the supported one, and the shipped example imports two vehicles that size to within 8 % and 17 % of their hand-written validation cases | S |
| ~~**R17**~~ | **Trade-study driver — done in v0.9** (M87): a `trade_study:` block declares the base design, the parameters and grid or one-at-a-time mode; `trade` runs every case and writes a table, a chart and a page. Failed cases stay in the table | S |

---

## 3b. Phase F — planned at v0.14.1

### What the tool is worth right now, measured

Every check case sized against its published figures. This is the table the rest of this phase argues from.

| Case | GLOM error | Length error |
|---|---|---|
| Delta IV Heavy | +0.4 % | +9.1 % |
| Saturn V (TLI) | −2.4 % | +11.8 % |
| Atlas V 551 | −8.2 % | +18.3 % |
| Firefly Alpha | +8.9 % | +16.9 % |
| Ariane 5 ECA | +9.7 % | +50.0 % |
| Falcon 9 B5 | +15.9 % | +17.7 % |
| Titan II GLV | +16.0 % | +18.7 % |
| Delta II 7920 | +28.3 % | +54.8 % |
| Electron | +29.0 % | +17.4 % |
| Zhuque-2 | −31.5 % | −19.3 % |
| Epsilon | +58.4 % | +45.3 % |
| Pegasus XL | +59.6 % | +50.3 % |
| Vega | +122.0 % | +97.7 % |

**Median |GLOM error| 16 %. Median |length error| 19 %.** Two things fall out of it.

**The error is not uniform — it tracks what the book was written around.** The large expendable vehicles of
the book's own era land inside about 10 %. The small solid-propellant launchers are out by 50–120 %. That is
not thirteen separate problems; it is a few assumptions failing outside the population they were fitted to.

**One of those assumptions is identifiable and dominant.** Replace the book's solid-motor casing relation
(Eq. 8:18, k_SRM = 0.135 for steel) with each motor's *published* inert fraction and **Vega goes from +122 %
to +5.3 %**, Pegasus XL from +59.6 % to +39.7 %. The real motors sit at k = 0.083–0.106; the book's own
"composite" alternative, k = 0.1154, is still high. This diagnostic already runs in `tools/run_validation.py`
and its answer has been sitting in the validation report unused.

**So the first thing to build is not capability — it is accuracy on what is already here.** Adding engines to
a database whose mass relation is 50 % light on a large engine (the RS-68 comes out at 3.4 t against a real
6.6 t) spreads the error wider rather than shrinking it. The libraries are worth expanding, and they are in
this phase, but they are not first.

**A note on the standing rule.** "Never tune inputs to match a vehicle" governs the three calibration items
below, and they are written to respect it. Tuning *one design's inputs* until it reproduces one published
answer is forbidden and stays forbidden. Fitting *a library assumption* to a published population, reporting
its residuals and scatter, and offering it **beside** the book's relation rather than replacing it is what
the book itself did to produce those MERs in the first place. The test for each item below: does the check
case still report the book's answer as well as the fitted one, and is the residual published? If not, it is
a fudge and should be rejected.

### Tier 1 — measurably wrong, with the data to fix it already in the repo

| # | Item | Effort | How it is verified |
|---|---|---|---|
| ~~**R18**~~ | **DONE in v0.15, and not by fitting our own.** Two published sources were found instead: Zandbergen (TU Delft, 2026, 17 steel + 17 composite flight stages) and Kibbey (NASA MSFC, NTRS 20190027424, size-dependent). Both are selectable casing methods carrying their own error statistics; because they predict a WHOLE STAGE the component build-up is suppressed rather than stacked on top. Pegasus XL +59.6% -> -4.1%, Epsilon +58.4% -> -10.4%, Vega +122% -> +11.8%. Every coefficient was refitted from the source's own table before use. The ORIGINAL plan on this row, to fit k ourselves, Fit k_SRM against the published inert fractions of every solid motor in the engine database and the check cases, and offer it as a third `casing_mass_method` beside `book_steel` and `book_composite`, carrying its own fit statistics and 1-sigma scatter so R3's uncertainty study picks it up. Report the residual per motor. Do **not** change the book methods or make the fitted one the default without saying so in the report | **S** | Vega, Pegasus XL and Epsilon re-sized; the book method must still be reported alongside, and the per-motor residual table shipped. Target: the three solid cases inside 20 % on GLOM, with the ones that are not explained |
| **R19** | **Calibrated layout factors.** Lengths run long on every case but two. The aft skirt (0.5 D), intertank (0.25 D), forward skirt (0.25 D) and interstage factors are flat assumptions that have never been checked against a real vehicle. Measure the implied factors from the thirteen published lengths, publish the spread, and ship the fitted set as a named alternative profile | **M** | The length error table above, regenerated. This one will not come out clean — Ariane 5 (+50 %) and Delta II (+55 %) are long for different reasons (ESC-A's bottle-shaped stage, nine strap-ons), and the honest result may be "the factors are fine, the stage-diameter model is the problem" |
| ~~**R20**~~ | **DONE in v0.15 and CORRECTED in v0.16.** At ten engines the answer was "scattered, do not refit" (mean -7%, sd 45%). At sixteen - after R22a added the engines the new check cases needed - it is clearly BIASED LOW: 14 of 16 light, median -24%, sd 37%. A small sample hid a systematic offset, which is the lesson. There is now an opt-in `mer_calibrated` method (factor 1.22, fitted in log space) that helps the typical engine and makes the two exceptional ones worse; the book's coefficients stay the default. Original text: Table 8.9 row 1 is linear in thrust; the database now holds 33 engines with published masses, so the relation can be checked across two orders of magnitude of thrust instead of trusted. Report the residual per engine; fit a replacement only if the residual is structured rather than scattered | **S** | 33 published engine masses. The RS-68 (3.4 t modelled, 6.6 t real) and Rutherford are the two ends |

**NEW, and now the top item: R29 — the avionics relation.** Fixing R18 left Vega at +11.8 %, and the
residual is a different relation entirely. The book's Table 8.8 row 6 gives avionics as a two-value STEP:
75 kg if the payload is under 1 t, 350 kg if over. Vega's 1,500 kg payload lands just over the cliff, which
puts 280 kg on its AVUM upper stage — whose entire real dry mass is 147 kg. A step function at a round
number is not a mass-estimating relationship, and this is the same subsystem NASA's own small-launch-vehicle
study (Beers et al., 20140003210) names as one of four it had to refine for small vehicles, along with stage
separation, TVC and feed/pressurisation — all three of which this tool also carries as flat constants
(60 kg, 25 kg/engine, 100 kg). That paper does **not** publish its refined relations, so this needs an
outside source or an honest declared-input route. **S**, and it is the biggest remaining accuracy item.

### Tier 2 — the capability gap

| # | Item | Effort | Notes |
|---|---|---|---|
| **R12** | **Reusability — revised scope.** The original row cited Sec. 14.9 and 17.7 as if they were methods. They are not: 14.9 is descriptive and contains no numbered equation. What is buildable, and is worth building, is the **bookkeeping**: a declared recovery Δv budget (boostback, entry, landing burns, each tagged `t: user` or `assumed` with its own source), declared recovery hardware masses (legs, grid fins, TPS) carried as named dry-mass components of the stage that returns, and the resulting payload penalty computed by the loop the tool already has. Reserve propellant comes out of the stage's mission propellant, not out of thin air. Recovery mode (RTLS / downrange / none) selects which burns apply. Nothing about entry heating, nothing about landing accuracy, and the report must say so | **L** | Verified against Falcon 9's own published expendable-vs-reusable payload split, which is the only public number that prices the whole penalty at once. **This is the single biggest gap between the book's framing and a vehicle designed today, and the one most worth having.** The risk is that a declared Δv budget is an input the user has no good way to choose; mitigate by shipping a worked Falcon 9 budget as an example, clearly tagged as assumed |
| ~~**R30**~~ | **Partly done in v0.20.** The motor-level half is addressed: `solid_inert.MOTOR_DATASET` (55 STAR motors) and the `star_motor` relation give a size-dependent alternative to the book's constant, each relation is now scored against the population it predicts, and a stage that names a real motor but keeps a `book_*` method raises a `CASEDB` warning instead of silently ignoring the hardware's own mass. **Still outstanding:** nothing yet REFUSES an affine relation below its fitted floor, and the validation harness still picks one relation per vehicle regardless of range. Original text: Respect a relation's fitted range instead of extrapolating past it. Applying the affine `zandbergen_steel_S2` (0.1689 m_p + 509 kg) to Scout's 215 kg fourth stage gives 545 kg of inert, an effective k of 2.54, and a vehicle 378 % too heavy | **S** | (a) Choose the relation per STAGE, by that stage's own case material and whether its propellant load is inside the fit. (b) For an affine relation below its floor, refuse rather than extrapolate, or fall back to the proportional form of the same family, and say which happened |
| ~~**R34**~~ | **DONE in v0.27.** The tank geometry check ran against the SEED, and refused designs that are feasible once converged. Found while adding Ariane 62 in v0.27. The check fires at every iteration, and the seeding algebra under-fills a hydrolox core whose boosters carry most of the lift-off impulse: the seeded LLPM asks for about 35 m3 where a 5.4 m tank's end caps alone take 58 m3, so iteration 1 is refused. The real stage holds 140,000 kg of hydrolox, about 384 m3, which fits that tank comfortably. The vehicle is not infeasible; the first guess is. A second limitation sits behind it - the core must outlast the 134 s booster burn and the seeded core does not - The fix: the checks now run inside `tank_sizing.tolerate_oversized_tanks()` while iterating, where a tank too wide for its contents reports a zero-length barrel - which is what an oversized tank physically is - and `size_vehicle` re-checks the CONVERGED design with the tolerance released, so a genuinely unbuildable tank still fails with the same message and the same one-click fixes. The core/booster phasing check was deliberately NOT touched and still refuses an Ariane 62 whose stage-1 share starves the core below the 43,333 kg it needs to outlast the P120C burn. This unblocked Ariane 62 and Ariane 64, both now in the check set | **M** | Either defer the geometry checks until the fixed point has converged (keeping them as hard errors on the converged design), or widen the seed for a boosted vehicle so the core starts closer to its answer. The test is `validation/ariane62` sizing with its published 5.4 m tanks and no hand-chosen split. This blocks a whole vehicle class: hydrolox core plus large solid boosters, which is Ariane 6, H3 and SLS |
| ~~**R35**~~ | **DONE in v0.28.** **Pinned architecture trades: take one variant's stages, change the strap-on count, get the payload.** Asked for directly: "get the stages from the 64, remove 2 boosters and see how much payload we could get" - and the reverse, "design a core while having a fixed booster". The existing `performance.FrozenVehicle` could NOT answer it: it carries the parallel phase as one stored number, which on Ariane 64 is about -2,900 m/s - a bookkeeping correction between the serial rocket equation and the phase model, not a contribution - and that number is a property of the reference booster count, so holding it fixed while changing the count invalidates exactly the thing being traded. The fix: `architecture.PinnedVehicle` subclasses `FrozenVehicle` and re-solves `boosters.phase_sequence` for the new count, so everything in `performance` that goes through `delta_v()` and `glom()` works on it unchanged. Validated by round trip - six boosted designs reproduce the sizing loop's per-stage delta-v to 1e-9, the same GLOM and T/W, and the payload root-find returns the design payload to better than 0.1 % - and measured against the two families that publish figures for several counts of one core, where it over-predicts the smaller variant by 19-52 % (ACCURACY 6b.5). That bias is printed beside every sweep and NOT corrected. Reachable as `python -m launch_vehicle.main architecture`, with `--size-core` for the reverse direction | **M** | `tests/test_architecture.py` (29 tests). Method M102 |
| ~~**R37**~~ | **DONE in v0.29.** **Launch vehicle family folders.** Asked for directly: a folder per family holding the variants with different strap-on counts, and the user able to make their own. Built as `families.py` plus a `family.yaml` manifest, discovered under any of `designs/families/`, `examples/families/` and `validation/families/` with nothing to register. A variant is the base design PLUS OVERRIDES rather than a copy of it, which is the design decision that matters: three standalone YAMLs would duplicate three hundred lines three times and let the "shared" core drift apart silently, whereas here the variants literally load the same file, so sharing is structural. The overrides are the dotted paths `deep_set` already understands and the GUI already passes, so a variant is openable with no new machinery. Published figures per variant are required to carry a source and to be marked `reference`, so a family can never quietly grade itself against its own assumptions. Shipped families: Delta II 7320/7420/7920 and Ariane 62/64. Reachable as `python -m launch_vehicle.main family`, and in the GUI's new Architecture & families tab | **M** | `tests/test_families.py` (12 tests), including a check that the A62 expressed as overrides reproduces the separately shipped `validation/ariane62.yaml` exactly - the drift the manifest exists to prevent. Method M103 |
| **R38** | **Pin a family's core at its REAL published propellant load.** The experiment ACCURACY 6b.6 names, and the one that would split the 6b.5 bias into its two causes. Both of the tool's family numbers are wrong in opposite directions because it never carries a core oversized for the mission being flown: sized alone the A62 core holds about 52,000 kg, pinned from the A64 about 78,000 kg, and the real shared LLPM holds 140,000 kg. Pin the core at 140,000 kg - a figure the family manifest can carry as a sourced published input like any other - and re-run the pinned payload table. If the error collapses, 6b.5 is core sizing and nothing else; whatever remains is the per-configuration ascent time of R36, measured rather than argued | **S** | Needs a way to fix a stage's propellant load as an input rather than solving it from the delta-v split, which is a real change to the convergence loop and should be scoped before it is promised. Delta II is the better test than Ariane: three variants and one published table |
| **R36** | **Per-configuration ascent time.** Found while measuring R35, and the honest half of its error. `performance.required_dv_mps` holds ascent time at the reference design's value on the stated grounds that "burn times are hardware and do not move during a sweep." The burn times do not; the trajectory does. A configuration with a third of its strap-ons removed climbs at a far lower initial acceleration for far longer and pays a gravity loss that the accel0 term alone does not charge it - which is why the pinned payload-vs-count slope is 19-34 % too shallow on Delta II and Ariane 6. The accel0 term is the only channel the book's loss regressions give for this, and it is not enough | **L** | The clean fix is to fly each configuration: the trajectory module already integrates an ascent, so `required_dv_mps` could take its ascent time from a flown trajectory instead of from the frozen hardware. The cost is a trajectory integration inside every bisection step of every sweep point. Measure first on Delta II 7320/7420/7920, where three published payloads share one core, before it is wired into the sweeps |
| **R33** | **A stage-equipment model that scales.** Found while measuring R30. The build-up's skirts, avionics, wiring and separation hardware are assumed values that do not scale with the stage, and on a small stage they are badly short: Scout's third stage carries 237 kg of equipment on a 98 kg motor, where the tool charges 50 kg. This is the other half of the solid error and the half that is still unmodelled — it has been hidden until now because it cancels against the book's over-heavy motor coefficient | **M** | Needs stage-level data with the motor mass known separately, which the STAR dataset plus a published stage inert gives for a handful of stages (Scout S3/S4, Pegasus 3). Small N, so the honest output may be a documented range rather than a relation |
| **R31** | **The published-casing-k diagnostic double-counts.** Also found by Scout. That column feeds a published inert/propellant ratio into `casing_mass_fraction`, a MOTOR-level input, after which the build-up adds skirts, interstage, avionics, separation hardware and margin on top - but every published figure available is STAGE-level and already contains them. At Pegasus' k = 0.091 and Vega's 0.083 the error hides; at Scout's stage-2 ratio of 0.282 it produces 72 t against a published 21.7 t | **S** | Rework the column to use the stage-level mechanism (a `solid_inert` relation key, which returns the whole stage inert and suppresses the build-up), or drop it. Until then the Pegasus and Vega entries in that column should not be quoted - the validation report now says so |
| ~~**R32**~~ | **MEASURED in v0.26, and a correction was deliberately NOT shipped.** The Δv gap was computed for all seven check cases that use `book_penalty` and have published stage masses, and candidate corrections were fitted against payload, altitude, sqrt(altitude), GLOM and ascent time, each scored leave-one-out against the null model of applying nothing. **Every one is worse out-of-sample than no correction** (LOO RMS ≥ 505 m/s against the null's 505). The reason is a confound, not a bad fit: every small-payload vehicle in the set flies to 500–700 km SSO and every large-payload one to about 200 km, so payload and altitude are indistinguishable. M-V is the single vehicle with a small payload to a low orbit and it refutes both — a payload fit misses it by 1,209 m/s, an altitude fit by 1,034. The encouraging-looking fit exists only with M-V deleted, and M-V was deleted on an assumption its own design file refutes. What remains of this row is the original visibility idea: flag a design outside the regression's fitted population. See `docs/ACCURACY.md` §6b for the full attempt, and the named candidate vehicles that would break the confound. The ORIGINAL text follows. **The ascent-loss regression is not fitted to small multi-stage solids.** Scout's own published masses and Isp give 9,087 m/s of ideal delta-v; the tool asks for 9,738 m/s. The 651 m/s gap is against a regression whose stated RMS error is ~260 m/s, and it accounts for roughly 35 of Scout's 55 points of GLOM error - more than the mass model does. Book Eq. 3:37-3:38 was fitted to ordinary ascents, and a four-stage solid that is over in 176 s of burn is not one | **M** | Not fixable by refitting the book's own regression, which is what it is. The useful step is to make the limitation visible: flag when a design's ascent time or stage count falls outside the regression's fitted population, and point the user at `losses.model: user` or the 3-DoF trajectory, which the tool already has. Every solid case in the validation report previously attributed its whole error to the casing MER. **More reachable since v0.24:** the stage count is now a one-click GUI control, so a user can build a five- or six-stage vehicle in seconds and the regression will be answering about a population it was never fitted to. The flag is not implemented yet because the book does not publish the fitted population, and inventing a threshold would be exactly the kind of unsourced number this tool refuses to carry |
| **R21** | **Close the structure → mass loop.** The monocoque sizing already comes out at 2.04× the MER mass on the default design and is never fed back. Closing it is the largest single source of error in the mass budget that the tool can see and declines to act on | **L** | Previously deferred by request ("I do realise closing the loop is important, but for now don't do it") — listed here so it stays visible, not to reopen it. Needs stiffened-shell allowables from outside the book, or it just replaces an optimistic MER with a pessimistic monocoque |

### Tier 3 — libraries: cheap, visible, low risk

| # | Item | Effort | Notes |
|---|---|---|---|
| ~~**R22a**~~ | **DONE in v0.16**: seven engines added (LE-7A, LE-5B, RD-107A, RD-108A, RD-0124, RD-191, BE-4), five of them because the new check cases needed them, plus the expander-bleed cycle the LE-5B required. Doing it AFTER R20 was the right order for an unexpected reason: the larger sample overturned R20's verdict, see that row. Original text: 33 now (28 liquid, 5 solid). The conspicuous absences are modern staged-combustion and full-flow engines (BE-4, Raptor, RD-191, YF-100), the historic ones the book itself tabulates and we have not entered (F-1 from Table 4.11, J-2 from 4.12), and the small-launcher engines where the MERs are weakest | **S** | Each row needs a citable source and a `published`/`approximate` confidence, as the existing ones do. Worth doing **after R20**, so new rows land in a database whose mass relation has been checked |
| **R22b** | **More propellant combinations.** 15 liquid propellants and 12 combinations is already most of what flies. The real gaps are **solid propellants — only three** — and hybrids, which the tool cannot represent at all | **S** | The solid gap matters more than it looks: it is the same population whose casing relation is wrong (R18) |
| **R22c** | **More tank and structural materials.** The library holds exactly **one** material, Al-2219, so the GUI shows a dropdown with a single entry and the whole Chapter 10 structural analysis can only ever be run in aluminium. The book is no help — Table 10.2's minimum gauges are aluminium-only and it gives no allowables table — so this needs an outside handbook source, cited leaf by leaf | **M** | Minimum useful set: an aluminium-lithium, a steel, a titanium and a composite laminate. Every property tagged `t: reference` with the handbook it came from, never `assumed` |
| ~~**R23**~~ | **DONE in v0.16**: H-IIA 202 (+6.0% declared, -0.2% optimised - the second-best case in the set) and Soyuz-2.1b (-10.5% optimised, geometry deliberately wrong because its strap-ons are tapered). Between them they exposed the tank-vs-end-caps failure for the fourth and fifth time, which is now an error message that names the diameter that would work. Original text: Thirteen vehicles. The ones worth adding are the ones that stress parts of the model nothing currently reaches: **Falcon Heavy** (liquid strap-ons, cross-feed deleted in reality — pairs with today's Delta IV Heavy), **Soyuz-2** (four tapered liquid strap-ons, which the single-diameter booster model cannot represent), **H-IIA** or **SLS Block 1** (solid strap-ons on a hydrolox core), **Proton** (hypergolic, and a vehicle the Western MERs never saw), and two or three more **small launchers**, where the model is worst and therefore most informative | **M** | Each case is evidence, not decoration: the point of adding one is to find what it breaks. Delta IV Heavy found two bugs in an afternoon |

### Tier 4 — book methods still on the table

| # | Item | Effort | Notes |
|---|---|---|---|
| ~~**R24**~~ | **DONE in v0.15.** Both worked examples reproduced; Clopper-Pearson bounds added where the book prints 100% from zero failures; redundancy credited only where the stage can fly an engine down. Original text: The k-of-n binomial, Table 15.4's measured engine statistics, and the engine-out T/W check the tool implies but never performs: with one engine out, does the stage still make its required thrust-to-weight, and what does the cluster's reliability come to? Report it beside the thrust table | **S** | The book's two worked examples pin the implementation exactly: 3-of-5 at R = 0.95 → 99.88 %, 7-of-9 at R = 0.95 → 99.164 %. The second being *worse* than the first is the result worth surfacing — more engines is not automatically more reliable, and the tool currently implies it is |
| **R10** | **Launch windows and mission design.** RAAN alignment, window duration, plane-change and dog-leg penalties for an inclination below site latitude. Still unstarted as a *method* — but v0.18 made the gap visible rather than silent: the launch site library computes the inclination floor `\|φ\|` from the chosen site, the GUI raises an inclination below it and says why, and the manual states that a plane change is not modelled. The tool no longer ignores the case; it refuses it in words | **M** | Book 3.7, 3.9. The dog-leg penalty is the part that changes a vehicle's size, and it is still the part the tool does not compute. Range-safety azimuth corridors belong with this item too, and are deliberately absent from the site library rather than invented |

### Tier 5 — tool quality, and the loose ends of v0.14

| # | Item | Effort |
|---|---|---|
| **R25** | **Trade study and comparison in the GUI.** The last CLI capability with no GUI route, flagged since R14 and still true. The GUI is now the primary interface, so this is the gap that most changes what a user can actually reach | **M** |
| **R26** | **A throttle profile in the parallel burn.** Found while building the Delta IV Heavy case: `boosters.phase_sequence` runs the core at one constant mass flow, so a throttled core has to be hand-converted to a burn-average thrust. That understates lift-off thrust by about a sixth on Delta IV Heavy and makes the engine MER size a *smaller engine* rather than a throttled one. A per-phase core throttle setting would fix both | **M** |
| **R27** | **Liquid strap-ons get real tanks.** A liquid booster is currently one bulk-density envelope, so the modelled Common Booster Core is 37.3 m against a real 40.8 m, and there is no intertank. Share the stage tank-sizing code instead | **S** |
| **R28** | **Partly done in v0.16**: the tank-vs-end-caps error now names the largest workable diameter instead of just refusing. Still outstanding: two example files share the name `EXAMPLE-TSTO-LOX-RP1-10t-LEO` in the GUI's Open dialog (`example_design.yaml` and `example_engine_database.yaml`); the stage tank diameter has to be set by hand whenever a stage's own diameter makes a tank shorter than its end caps (hit by both Ariane 5's ESC-A and Delta IV Heavy's DCSS), which the tool could detect and suggest | **S** |

### Suggested order

1. **R18** — one small item, and it is worth more than everything in Tier 3 combined.
2. **R24** — small, self-verifying against two worked examples, and it makes `n_engines` mean something.
3. **R12** — the capability people actually want, and the biggest divergence from the book's expendable world.
4. **R20 → R22a** — check the engine relation, *then* widen the database.
5. **R23** — new check cases, chosen to break things.
6. **R19, R25, R26, R27** as they fit.

R21 stays parked until asked for.

---

## 4. The GUI: what was built and what should follow

**Built (v0.4):** a dependency-free local web GUI (`python tools/gui.py`, stdlib `http.server`, no CDN, no
framework, works offline). The left panel is the whole input register — every annotated input,
grouped, searchable, colour-coded by provenance, each showing its units and description, with the source on
hover. Edit a value and it becomes a visible *override*; the YAML file is never silently modified. The right
panel has the summary with KPI cards, the Δv budget with each line's book source, the stage table, mass
build-up and full ledger, the drawings, the geometry table, the checks, and the report, with buttons to
download the report, the workbook and the overrides as a YAML fragment that reproduces the run from the command
line. "Set baseline" freezes a result so later runs show the percentage change against it.

**Why this shape:** the YAML files stay the source of truth. The GUI sends overrides on top of a file and shows
exactly which ones are active, so no GUI session can produce a number that cannot be reproduced from the command
line. Nothing is calculated in the browser.

**Built (v0.18) — the user-experience pass.** Four things that were previously only reachable by editing YAML
by hand:

* **A launch site library.** `config/launch_sites.yaml`, now 30 sites with sourced coordinates, grouped by
  continent in a dropdown. Choosing one fills the latitude and enforces what a latitude implies: a direct ascent
  cannot reach an inclination below `|φ|`, so an inclination under that floor is raised to it with a note
  saying so, instead of becoming an infeasibility on pressing *Size*. The library deliberately carries **no
  pad altitudes** (the sources give none) and **no range-safety azimuth corridors** (per-pad, per-vehicle,
  per-year), and says so in the file, in the module and in the manual. The floor is a necessary condition for
  a direct ascent, never a sufficient one.
* **New design.** Starts from the shipped default and clears the *brief* — payload, orbit, site, diameters,
  staging split, engines, Isp — while leaving everything the method owns intact. The obvious rule, "clear
  everything tagged `provenance: user`", was tried and is wrong: it picks up `throttle_min_fraction` (1.0,
  meaning no throttling) and `launch_site.altitude_m` (0.0, sea level), and clearing the first makes the
  design unsizable. The brief is therefore a written-down list with a reason per field, which the page shows
  under each cleared field. Sections holding a cleared field are opened, the header counts what is still
  empty, and sizing an incomplete design leads with the empty fields rather than with whatever arithmetic hit
  the `null` first.
* **Save / Save as.** Save writes back to the bound file; Save as takes a new name and switches to it, asking
  before replacing an existing one. Neither can overwrite a shipped file: `config/`, `examples/` and
  `validation/` are reference material, and a check case quietly edited is a check case that no longer checks
  anything.
* **Liquid ↔ solid per stage.** The one edit that is not an override, since the two stage types are different
  documents. The new propulsion block is grafted from the shipped design of that type rather than from a
  template written for the purpose, so it arrives annotated with its own sources. The user's geometry and
  margins survive; the three genuinely type-dependent values come across with the block. Proved by a round
  trip: stage 1 of the default is the liquid donor, so liquid → solid → liquid reproduces the shipped design
  to the kilogram.

**What should follow, in order:**

1. **Compare several designs side by side** (R14) — the natural next step now that a baseline exists.
2. **Live sweep**: drag a slider on one input and watch GLOM move; the sizing run is about a second, so a
   debounced sweep of 20 points is a few seconds in the background.
3. **Plots in the GUI**: the carpet plots from R1 and the Monte-Carlo histogram from R3 exist as of v0.5 and are
   in the report; putting them on screen, with the sweep re-run as the designer edits, is the next GUI step.
4. ~~**Save back to YAML**~~ — done in v0.4 and completed in v0.18 with Save / Save as and file binding.
5. **Trajectory plots** once R5 exists: altitude, velocity, dynamic pressure and acceleration against time, with
   the staging events marked.

Since this list was written: comparison and trade studies are in the GUI (v0.23), each analysis has its own tab and
chart, the trajectory is plotted, and a Windows app packages the whole thing (v1.0). The live sweep is not built.

---

## 5. Known accuracy problems to fix (ahead of new features)

Written at v0.6, kept with what became of each; `docs/ACCURACY.md` has the current measurements:

| # | Problem | Evidence | Fix |
|---|---|---|---|
| **A1** | **Solved in v0.26 by `kibbey_medium`.** *Was:* **Solid-motor casing MER is 20–60 % heavy.** Eq. 8:18–8:19 with `k = 0.1154` gives `s = 0.1035`; real filament-wound motors are 0.08–0.09 (Vega P80 0.083, Zefiro 23 0.081, Orion 50S XL 0.091) | every solid stage in the validation set; substituting published ratios moves Vega from +25 % to +5 % | a modern composite-casing option alongside the book's, with its own source; properly, R7 |
| **A2** | **Avionics MER steps 75 → 350 kg at 1 t payload**, which is heavy for a small launcher and contributes several per cent of GLOM on Electron-class vehicles | small-launcher cases in the validation set | a continuous small-vehicle avionics relation with a cited source |
| **A3** | *(retired in v1.3 for those who choose it: the simulated loss method sizes with the flown losses, M109. Before that, largely retired in v0.6: `--trajectory` computes the losses instead of fitting them, and the two agree to a few per cent on the default design's own split but differ by 21 % on its optimised one. The regression remains the default inside the sizing loop, because the trajectory needs a converged vehicle to fly.)* **Ascent-loss regressions are fitted to LEO ground launches** and are extrapolated for air launch, high-energy orbits and very small vehicles. The three book fits disagree by 302 m/s on the default case, which is ±6 % on GLOM | `docs/ERRATA_COMPLIANCE.md` §3 | R5: compute the losses instead of fitting them |
| **A4** | **Pegasus XL is now −17.6 %.** *Was:* **Pegasus XL is +45 % on GLOM**, the worst case, after the errata's measured 322 m/s drag loss was applied | `docs/VALIDATION_REPORT.md` | partly A1 (three solid stages), partly A3 (air launch is outside the fit) |

---

## 6. Suggested order of work

1. ~~**R1 + R3** (performance curves and uncertainty bands)~~ — **done in v0.5**.
2. ~~**R2** (engine database)~~ — **done in v0.5**; ~~**R4**~~ (analytical staging optimum) with it.
3. ~~**A1**~~ — **done in v0.26**. **A2**, the avionics step, is still open.
4. ~~**R5** (trajectory)~~ — **done in v0.6**, and it retires most of A3: the losses can now be computed for any
   vehicle the gravity turn can fly. **R5b** (trajectory optimisation) is the natural next step, and it is also
   what would let the low-upper-stage-T/W vehicles close.
5. ~~**R8**~~ (load cases) and ~~**R7**~~ (stress and buckling) — **done in v0.7 and v0.8**. What remains of
   the structural story is the part the book cannot supply: allowables for stiffened shells, and feeding the
   sized thicknesses back into the convergence loop.
6. ~~**R11**~~ (cost) — done, with production and operations. **R12** (reusability) is what is left of the programme
   questions.

## 7. What will not be built

For the record, so the scope stays honest: this tool will not become a six-degree-of-freedom simulator, a finite
element solver, a CFD code, or a flight-software environment. Where a real analysis is needed, the right output
is a well-posed input deck for the tool that does it — which is why the geometry, mass properties and load cases
are exported in full.
