# Drag estimated from the vehicle's geometry

Since v1.1 the ascent trajectory takes its drag coefficient from the shape of the vehicle being flown. This page
says how, where each relation comes from, and how far the result is from published data. The numbers are generated
by `tools/validate_drag.py` into [`DRAG_VALIDATION_DATA.md`](DRAG_VALIDATION_DATA.md); **nothing was tuned to
them**.

If you read one section, read §4.

---

## 1. Why

Until v1.1 every design was flown on one curve: the Titan II drag coefficient the book prints in Fig. 6.13
(p.361). It is exact as printed, and it is one vehicle's. A 1.2 m smallsat launcher, a hammerhead heavy-lifter and
a core with four strap-ons all got it.

The book has no method for doing better. Sec. 6.4.1 (p.358) lists wind-tunnel testing, a literature search, "or
... a drag prediction program such as Missile DATCOM". So what follows is **not a book method**, and the method
register marks it SUPPLEMENTARY (M104). It is the standard preliminary-design component build-up.

## 2. The build-up

```
Cd = Cd_friction + Cd_forebody + Cd_boattail + Cd_base        on one reference area, the largest core section
```

evaluated for the core and for each strap-on still attached, and summed. The shape changes in flight: strap-ons
leave, then spent stages, and the integrator switches to the new shape at each event while keeping the lift-off
reference area.

| Term | Relation | Read in |
|---|---|---|
| Skin friction | turbulent `Cf = 1/(1.50 ln Re − 5.6)²`; roughness-limited `Cf = 0.032 (Rs/L)^0.2` above `Re = 51 (Rs/L)^−1.039`; compressibility `(1 − 0.1 M²)` subsonic, `1/(1 + 0.15 M²)^0.58` supersonic; `Cd = Cf (1 + 1/(2 fB)) A_wet / Sref` | OpenRocket technical documentation, Sec. 3.4.2 |
| Nose cone, and any flare | on the frontal area it adds, half-angle ε: `2.1 sin²ε + 0.5 sin ε/√(M²−1)` for M ≥ 1.3; `sin ε` at M = 1 with slope `4/(γ+1)·(1 − 0.5 Cd)`; a cubic between; `0.8 sin²φ + a M^b` below | same, Appendix B.2 and Sec. 3.4.3 |
| Blunted tip | `Cd_sharp (Sref − S_tip)/Sref + Cd_hemisphere S_tip/Sref`, the hemisphere at a fineness of 0.5 | Fleeman p.24, Fig. 2.8 |
| Base | `0.12 + 0.13 M²` (M < 1), `0.25/M` (M > 1), on the base area; thrusting, on the base area less the nozzle exit area | Fleeman p.23, Fig. 2.7 |
| Boattail | base drag on the annulus it removes, × 1, `(3 − g)/2`, or 0 for `g = length/(d1 − d2)` below 1, from 1 to 3, above 3 | OpenRocket Sec. 3.4.3 |

The Reynolds number is built on the body length with US76 density and Sutherland viscosity at the flight altitude,
so friction depends on altitude as well as Mach number; everything else depends on Mach number alone.

**Sources, and how each was read.** Fleeman, *Tactical Missile Design* (AIAA, 2001), pp.23–24, was read in the
owner's copy, and its worked example (0.10 powered and 0.125 coasting base drag at Mach 2) is reproduced by a
test. The OpenRocket technical documentation (S. Niskanen, the edition for OpenRocket 1.1.6, 2011) was read in its
LaTeX source. That document attributes its relations to Barrowman (1967) and Hoerner (1965); **those two were not
read**, so they are named as the document's sources and not as this tool's.

**Three choices are this tool's**, where a source leaves the form open: a cubic between Mach 1 and 1.3 (the source
says "a polynomial"; a cubic is the lowest order that meets four conditions), a linear blend of the two friction
corrections across Mach 0.9–1.1 (they do not meet at Mach 1), and a default surface roughness of 50 µm, which is
an assumption and an input.

## 3. What it leaves out

* **Protuberances and fins:** raceways, feed lines, attach fairings, antennas, engine fairings.
* **Interference** between a core and its strap-ons. The strap-ons are added as isolated bodies.
* **Plume effects** beyond filling the nozzle exit area. The book's Fig. 6.11 shows two on the Saturn C-1: extra
  base drag at low speed and much lower drag at high Mach with the engines running. Neither is modelled.
* **Non-circular sections**, such as clustered tanks, and **angle of attack**.

## 4. How far it is from published data

### 4.1 Drag coefficient

| Vehicle | Published data | Build-up | Reading |
|---|---|---|---|
| **Saturn V** at max-q, Mach 1.71 | Cd 0.405: a measured axial force of 260 klbf at 750 psf (SA-503, book p.588), on the 79.49 m² core | **0.379, −6 %** | Low, as it should be: the fins and engine fairings are left out, and the book says they make the frontal area 1.55 times the core's. Geometry from the book's Table 9.5 |
| **Vanguard**, Mach 0.7–5 | wind-tunnel curve, book Fig. 6.10 | **mean absolute error 18 %**, +17 % signed | Within 11 % from Mach 1.2 to 2 and at Mach 5. **34–44 % high from Mach 0.8 to 1.0**: the build-up starts its transonic rise too early. Peak 0.547 at Mach 1.08 against 0.450 at Mach 1.20 |
| **Titan II**, Mach 0.3–5 | analytic curve, book Fig. 6.13 | **35 % high** on average, 89 % high at Mach 5 | Within 8 % up to Mach 0.6 and within 15 % from Mach 0.9 to 1.07. Does not agree above. See below |

**The Titan II curve is not reproduced, and the reason is probably the curve.** It falls to 0.19 at Mach 5 and
tends to 0.09. The missile's Mark 6 re-entry vehicle is a 12.5° cone with a 0.59 m nose radius on a 2.3 m base; in
this build-up its pressure drag alone, with the adapter behind it, is 0.28 at Mach 5 on the 3.05 m reference
area, before any friction or base drag. A curve that sits below that is not of that configuration, or is not on
that reference area. The book gives neither for Fig. 6.13. This is an argument and not a measurement: the
build-up's blunt-tip treatment is itself the crudest part of it.

**Two results depend on a dimension that could not be sourced**, and the table above is not better than that:

* Vanguard's conical transition between its 32 in and 45 in stages is described in the Martin engineering summary
  with no length. Assumed one first-stage diameter. At 0.6 m the mean error is 40 %; at 2.0 m, 14 %.
* Titan II's adapter between the re-entry vehicle and the body. Assumed 1.5 m. At 1.0 m the mean error is 52 %; at
  3.0 m, 23 %.

In both cases a flare carries nearly half the reference area, so its angle decides the answer. The same is true of
your design: see §5.

Two more curves in the book were **not** used. The V-2 (Fig. 6.9) has fins, which this build-up does not model.
The Saturn C-1 (Fig. 6.11) has a blunt nose, clustered tanks and eight engines, and its outside dimensions were
not found in a source that could be read.

### 4.2 The trajectory: Apollo 11's first stage

The S-IC burn of AS-506 was flown from published numbers only: the ignition mass and the lift-off mass method of
book p.585–587, the F-1's sea-level thrust and specific impulse from Table 4.11 (p.241), the vacuum specific
impulse of Example 3.8 (p.176), and the pitch start and engine cutoff times of NASA's Apollo 11 timeline
(SP-2000-4029). The pitch kick was chosen so the vehicle is at the published 13,568 m at 83 s. **That altitude is
the only flight result used as an input.**

| | Flight | Model, geometry drag | Model, Titan II curve | Model, no drag |
|---|---|---|---|---|
| Mach 1 | 66.3 s | 64.0 s | 64.2 s | 63.3 s |
| Speed at 83 s | 504 m/s | 530 m/s (+5 %) | 526 m/s | 555 m/s |
| Dynamic pressure at 83 s | 35.2 kPa | 34.3 kPa (−3 %) | 33.7 kPa | 37.5 kPa |
| Acceleration at cutoff | 3.94 g | 3.97 g | 3.98 g | 3.98 g |
| Drag loss, lift-off to cutoff | 40–46 m/s (whole ascent) | 34 m/s | 33 m/s | 0 |

Two checks on the engine model were not used as inputs and came out right: the nozzle exit area implied by the two
specific impulses is five 3.64 m exits, and the thrust at the max-q altitude is 38.34 MN against the 38.55 MN the
book reads from NASA's reconstructed thrust curve (−0.6 %).

What this does and does not show:

* **The integrator, atmosphere and propulsion model are right to a few per cent** on a real ascent, up to max-q.
* **It cannot tell the two drag models apart.** They differ by 4 m/s at 83 s, and the inputs are uncertain by far
  more. On a vehicle this size and shape the Titan II curve and the build-up happen to agree at max-q (0.38 each).
* **The model runs a little fast** (Mach 1 2.3 s early), and the lift-off mass is why. The book's method takes
  6.4 s of full flow off the ignition mass, which is too much because the engines do not start at full flow.
  With nothing taken off, Mach 1 comes at 69.4 s and the vehicle cannot reach 13,568 m by 83 s even climbing
  vertically. The flight sits between the two, nearer the first.
* **The time of max-q is not reproduced** (76 s against 83 s). One pitch kick fixes one point of the trajectory;
  the real pitch programme is not a single-kick gravity turn. Nothing after 83 s is compared for the same reason.
* The book's Example 3.7 quotes a "liftoff thrust" of 7.891 × 10⁶ lbf. It is 3.7 % above five times the engine
  table's value and needs a nozzle 23 % smaller than the real one to meet the published thrust at max-q. Flown,
  it puts Mach 1 at 59.8 s and the speed at 83 s at 607 m/s. It was not used.

### 4.3 Drag loss

| | Published | Sized design, geometry drag | Sized design, Titan II curve |
|---|---|---|---|
| Saturn V | **40 m/s** (book Table 3.4, p.180); 46 m/s (p.174) | 35 m/s | 28 m/s |

Both are low; the build-up is nearer. The book's Table 3.4 also gives Atlas I 110, Delta 7925 136, Space Shuttle
107 and Titan IV/Centaur 156 m/s. The tool has no design for three of them. A Delta II 7920 flown on its published masses
(`docs/ASCENT_VALIDATION.md`) loses 110 m/s, against 136 for the 7925.

**Only one real rocket's flight was compared, and it is a 2,900-tonne one.** Flight timelines for small launchers
were not collected. For the vehicles this tool is mainly for, the build-up is checked on its coefficient
(Vanguard, 10 tonnes) and not on a trajectory.

## 5. What it means for a design

| Design | Lift-off mass | Nose length / diameter | Peak Cd | Drag loss, geometry | Drag loss, Titan II curve | Change in speed in hand |
|---|---|---|---|---|---|---|
| Saturn V (sized) | 2,826 t | 1.0 | 0.61 | 35 m/s | 28 m/s | −14 m/s |
| Falcon 9 (sized) | 636 t | 1.2 | 0.72 | 31 m/s | 19 m/s | −19 m/s |
| Default two-stage | 410 t | 1.0 | 0.72 | 56 m/s | 36 m/s | −31 m/s |
| Electron (sized) | 16.8 t | 0.8 | 1.10 | 179 m/s | 75 m/s | −158 m/s |
| Electron, nose lengthened to 2.0 | 16.9 t | 2.0 | 0.58 | 83 m/s | 74 m/s | −12 m/s |

* **Large vehicles barely notice.** The drag model moves the speed in hand by 14–31 m/s.
* **Small vehicles notice a great deal, and the nose is why.** Drag loss scales with frontal area over mass, which
  is the book's own point on p.174. On the 17-tonne Electron design the build-up more than doubles the drag loss
  and takes 158 m/s off the speed in hand.
* **Most of that is the assumed nose.** The Electron design carries a nose 0.8 diameters long, marked `assumed`.
  At 2.0 diameters, nearer a real fairing, the drag loss falls from 179 to 83 m/s. `fairing.nose_length_over_D` is
  an `assumed` input in nearly every shipped design, and until v1.1 it only affected the drawing and the fairing
  mass. **It now decides the drag of a small vehicle. Set it from your fairing.**

The sizing loop is unaffected, unless the simulated loss method is chosen: it takes its ascent losses from the book's regression.
The trajectory, the loads at max-q, the stability and control assessment, the payload environment, the
pitch-programme optimisation and the drop zones all fly on the new drag and all move with it.

## 6. Using it

`mission.aerodynamics.drag_model` is `geometry` by default. `book_titan2`, `table` and `constant` are
still available. Three more inputs sit beside it: `surface_roughness_m`, `nose_shape` (`cone` or `ogive`) and
`nose_bluntness`. In the GUI they are under Mission → Trajectory model, and the Trajectory tab shows the build-up
term by term against Mach number, beside the Titan II curve. The report carries the same table.
