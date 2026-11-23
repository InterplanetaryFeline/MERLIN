# Changelog

Newest first. Entries are kept as written at each release, so what they say about the tool's limits and numbers
was true of that version. [`ACCURACY.md`](ACCURACY.md) has the current measurements.

**What changed in v1.2.1 - drawing and table fixes**

* **Common bulkheads.** The shared dome that bulges into the upper tank is now filled with the lower tank's colour,
  in the 2D drawings. It was outlined only, so part of the lower tank showed the upper propellant's colour.
* **Sorting by words.** A column of names sorts alphabetically, A to Z on the first click, with "Stage 2" before
  "Stage 10". Every word used to count as zero, so clicking did nothing.
* **Loads figure.** The vehicle beside the curves is drawn to scale. It had a fixed width, which made a slender
  vehicle look too fat (about 2.7 times, for the default rocket).

**What changed in v1.2.0 - your own propellants and materials, and the first user feedback**

*Your own propellants and tank materials.* A **Library...** button in the top bar, and a **+ own** button beside
every fuel, oxidiser, solid propellant, propellant combination and tank-material dropdown, open a form that adds
an entry of your own to `designs/my_library.yaml` (`user_library.py`). Four kinds can be added:

* a **fuel or oxidiser**: role and density, with the boiling point (blank means storable), insulation and a
  Table 8.6-style tank coefficient optional;
* a **propellant combination**: an oxidiser and a fuel that must both be in the library, and the mixture ratio
  the engines run at, which a stage takes when the combination is picked; reference Isp, c* and the rest optional;
* a **solid propellant**: the cast density, with c* and the burn-rate exponent optional but given together,
  since only the internal ballistics reads them;
* a **tank material**: density, minimum yield, minimum gauge, Young's modulus and thermal expansion, with a blank
  allowable taking 0.633 x yield, the basis every shipped material uses.

Entries are annotated `{v, u, d, s, t}` like the shipped library, every number is range-checked, a source is
required, and a shipped name is refused. They appear in the dropdowns marked "(my library)". A saved design carries
a copy of every entry it uses in a `library:` block, including the fuel and oxidiser a custom combination names, so
it opens on a computer that has never seen your library; the design's copy wins, so editing the library later does
not change a design already saved.

*Library values can be changed from the GUI.* Found while building the above: changing ANY value in the
Propellant library, Material library or Modelling assumptions sections made sizing fail with a KeyError, because
the change was written into the design instead of the library. It now reaches the library, and a saved design
keeps the changed field in its `library:` block rather than touching the shipped file.

*Checked by sizing with custom entries.* Clones of a shipped fuel, alloy, solid and combination size the same
vehicle to the kilogram. Denser fuel gives a shorter, lighter stage; tank volume follows the bulk density of the
combination (N2O/IPA needs 31 % more than LOX/RP-1, the inverse of their 1,026 and 786 kg/m^3 bulk densities);
pressure-vessel tank mass falls as allowable stress times weld efficiency over density rises, Al-Li 2195 lightest
and a 304-class steel heaviest. Solid density changes the motor's length but hardly its mass, because the
published casing relations work from propellant mass, not case volume; that is a property of those relations.

*Uninsulated cryogens are flagged.* Tank insulation is a switch on the stage, not a property of the propellant, so
moving a stage to a cryogen - the shipped LH2 or LCH4, or one of your own - left its tank bare and the vehicle too
light, with nothing said. A new warning, TANKINSUL, says so and offers a one-click switch. No shipped design
triggers it.

*Launch sites.* Two added at a user's request. **CPSP Ustka**, the Polish Air Force range on the Baltic used for
suborbital rockets, is marked suborbital-only and sits at the village of Wicko Morskie inside the range, because no
coordinate is published for the range or its pad. **SUAS Aerospace**, a proposed Irish spaceport whose site is not
yet chosen, sits at a stand-in coordinate (the company's base near Midleton, County Cork), which the row and the
dropdown both say. The site list is now grouped by continent, alphabetical within each, so Kourou is under South
America, and every entry names its country.

*Clearer fields.* "Credit Earth's rotation" is now "Include Earth's rotation". The winds-aloft profile says what it
is and that only the loads analysis reads it. When picking a site has to raise the orbit inclination, the note says
why in plain words, on the inclination field as well as on the site.

*Interactive tables.* Every results table with three or more rows sorts by a click on its heading (largest first,
smallest first, original order), with totals kept at the bottom. The mass ledger can be filtered to one stage or
one group, can leave the propellant out, and shows each item's share of what is shown and of the lift-off mass. Its
stage column names the payload, the fairing and the strap-ons instead of printing the internal numbers 0, -1 and -2,
where the fairing read as "stage -1"; the report's ledger, which called both the fairing and the boosters "upper",
does the same.

*Nothing in the engineering changed for an existing design.* The default design, the examples and the check cases
size to the same lift-off masses as v1.1.0: the TSTO example gives 397,246 kg with the optimised split and 410,003 kg
as written, under both versions.

*Saving to a folder on another drive no longer fails.* The first release run of this version failed on the GitHub
build machine, whose project is on drive D: and whose temporary folder is on C:: showing a saved design's path
relative to the project raised an error across drives. Such a path is now shown in full.

**What changed in v1.1.0 - drag from the vehicle's own geometry, and a vertical rise that is vertical**

*Drag is estimated from the shape being flown.* Every design used to fly on the Titan II curve of book Fig. 6.13,
whatever its shape. The default is now a component build-up from the sized geometry (M104, SUPPLEMENTARY: the
book gives no such method and points to Missile DATCOM, p.358): skin friction, pressure drag on the nose and on
every flare, boattail and base drag, for the core and for each strap-on while it is attached, with the shape
changing as strap-ons and stages leave. The Titan II curve, your own table of Cd against Mach, and a single fixed
Cd are still selectable; the table's `mach_table` and `cd_table` are now inputs in the design file and the GUI,
where before they could only be typed into the YAML by hand. **The ZOOM lift/drag file reader (M62) is removed**
at the owner's request, leaving 103 registered methods; a design that still asks for `zoom_ld` is told to use
`table`. In the GUI the drag model dropdown is always shown under Mission, Trajectory model, with only the inputs of the
model that is selected: tagging the choice `assumed` had folded the dropdown out of sight while the fixed Cd and the
table of the models not chosen stayed in view.

*GUI tidy-up.* The bars of the velocity budget never drew: the fill was an inline element, which ignores its
width, so each line showed an empty grey track. They now show each line against the largest line of the budget.
The **Model checks** and **Architecture & families** tabs are hidden at the owner's request; their code, their
server routes and the `architecture` and `family` commands are unchanged.

*Names and units a first-time user can read.* About sixty input labels were rewritten after an audit of the page
as a newcomer sees it: a bare "Diameter", "Length", "Material" or "Kind" now says of what, "User mass fuel", "Paf a"
and "Tol" are gone, and the "Mer" fold is "Mass-estimating relations". The page shows chamber and tank pressures in
bar, the dynamic-pressure limits in kPa, thrust in kN, allowable stresses in MPa and wall gauges in mm, and converts
back as you type; the design file, saved overrides and the engine are SI as before. Numbers are written one way
whatever the machine's locale (a decimal point, a thin space between thousands), where a Polish machine used to show
"7671,7 m/s" beside "54.87 m". The trajectory summary no longer prints raw keys such as "drag loss mps".

*Did it reach orbit?* The trajectory used to end on a burnout altitude and a speed and leave the reader to work out
what they meant. It now says (M105, SUPPLEMENTARY): the launch site's speed is added back to the flown burnout
state the way the delta-v budget took it out, the orbit that state is on follows from two-body energy and angular
momentum, and its perigee and apogee are set against the ones the mission asked for. The verdict is one of
reached, in orbit but short of the target, or not in orbit. The thresholds are assumptions and are stated where
the verdict is shown: within the larger of 10 km and 2 % of each target apsis, and a perigee above 100 km to count
as an orbit at all. A speed surplus shows as a high apogee, because this model has no cutoff on reaching the orbit.
The check is in the Trajectory tab, on the Summary tab under "What governs this design", and in the report.

*Events timeline.* The Trajectory tab and the report list the ascent in time order: lift-off, the pitch kick,
Mach 1, maximum dynamic pressure, peak acceleration, each burnout, ignition and jettison, with altitude, downrange,
speed, Mach number, flight path angle, dynamic pressure and mass at each.

*What the check finds.* It is a report of what the trajectory already computed, and it is not flattering to every
shipped design: the default two-stage design reaches 399 x 606 km against 400 x 400 km, while the Electron check
case burns out 1,054 m/s short and the strap-on example 528 m/s short. Those shortfalls were already in the
report as a negative speed margin; they are now stated as "not in orbit". Nothing was changed to make them pass.

*Picking a real engine fills the fields.* The pick used to blank the figures the engine supplies and leave the
database to fill them unseen when the design was sized, so the page showed empty boxes for the Isp and the area
ratio. It now writes them in: specific impulses, chamber pressure, area ratio, dimensions and mass where the
source gives them, and the stage's propellants and mixture ratio. A figure the source does not give keeps your
value and the note under the pick says which; the engine's thrust is not written into a stage that sets its thrust
from a thrust-to-weight ratio, and the note says that too. A published engine mass switches the engine mass method
to "mass I give", since that is the only method that reads it. A saved file records each value as the database's.

*Inputs that the chosen method does not read are no longer shown.* Thirty-four inputs now appear only under the
setting that reads them, directly beneath the choice they hang on: the engine length under "dimensions I give",
the tank mass under "mass I give", the three loss estimates under "my own loss estimates", and so on. Each rule
was checked against the code that reads the input. A field that the choice above has just made necessary and
that is still empty is marked.

*The characteristic velocity has a field.* Choosing "from the book relations" for the engine dimensions failed
with a message naming `cstar_mps`, an input no shipped design states and the page had no field for. The field now
appears under that choice, the error takes you to it, and it offers two ways out: the propellant combination
table's reference c* (a theoretical value, and said to be), or going back to typed dimensions.

*Errors and warnings point at their input.* About sixty checks raised a sentence with no field, so the page could
only print it. Each check code now maps to the input it is about (`validation.infer_field`), for errors and for
the warnings on the Checks tab alike. A check about no single input still names none.

*Every real engine was picked and sized.* All 35 liquid engines in the database were picked onto each stage of
the default design in the live page, 70 picks, and each offered fix applied as a user would. 68 end sized. Two
stop at an error that needs a number only the user has: Gamma-2 and BE-4 on stage 1, where the source gives one
specific impulse and not the other, so the design's own leftover value contradicts it. (BE-4 no longer stops
after the correction below.) Every error named an input
the page has and was showing. What that sweep fixed: "Go to" did nothing when the field sat in a closed fold, and
now opens every fold above it; a propellant with no coefficient in the propellant-mass tank relation (UDMH, N2O4,
A-50, LCH4, HTP) was refused in the middle of sizing with no field, and is now refused before sizing with a
button for each tank that needs another method; the sea-level-above-vacuum message gives both numbers and says
which one the database left to the design; and a field the source could not fill carries a note saying so at the
field itself.

*The BE-4 row's specific impulse was the wrong way round.* Its source page gives a single 340 s with no
altitude, and the row had recorded it as the sea-level value. It is now recorded as the vacuum value, with the
sea-level Isp unknown. The grounds are stated in the row: the only page found that names a condition gives 310 s
at sea level and 340 s in vacuum, and 340 s at sea level is more than methane engines at twice the chamber
pressure deliver there. No primary figure was found, so this remains a reading of an ambiguous number, marked
`approximate`, and the unsourced 310 s is not adopted. No validation case uses this engine.

*The delta-v split is optimised by default.* `vehicle.optimise_dv_split` is now on in the default design, the
examples and every check case, at the owner's request. The accuracy figures in `ACCURACY.md` have always been
for the optimised split, while the page sized a check case with its split as written, so Delta II opened in the
page gave 297 t against the documented 231 t and looked like a 28 % error where the documented one is -0.4 %.
The page now reproduces the documented figures. It costs between about 1 and 8 seconds per sizing on the shipped
designs. Where no split gives a vehicle that sizes (the peroxide example and Delta IV Heavy are two), the split
as written is used and the page says the optimisation was not applied, as before. A reference split taken from a
source, such as the Saturn V's from book Example 5.1, is likewise replaced unless the option is switched off.
`size_vehicle` itself is unchanged and still sizes exactly the split it is given; the option is applied by the
page and by the `run` command.

*Grouping.* The engine pick and the propellant combination lead their folds. The cost year has its own "Cost"
fold, the pad height sits with the winds it is used with, the avionics override with the other masses and the
stage length limit with the layout. Three new inputs: surface roughness, nose shape and nose bluntness. The Trajectory tab and the report
show the build-up term by term against Mach number. [`DRAG.md`](DRAG.md) has the sources and the measurements.

*Measured, not tuned.* Against the Saturn V's measured axial force at max-q, −6 %. Against the Vanguard
wind-tunnel curve, 18 % mean absolute error, 34-44 % high from Mach 0.8 to 1.0. Against the book's Titan II
curve, 35 % high, and 89 % high at Mach 5, where the curve falls below the pressure drag of that missile's own
re-entry vehicle. Apollo 11's first stage, flown from the book's masses and engine table, reaches Mach 1 at 64.0 s
against 66.3 s and is within 5 % on speed and 3 % on dynamic pressure at 83 s; that comparison checks the
integrator and cannot tell the two drag models apart. `tools/validate_drag.py` regenerates all of it.

*What moves.* The sizing loop does not: it takes its losses from the book's regression. Everything flown does.
Large vehicles lose 10-25 m/s of burnout speed. The 17-tonne Electron design loses 182 m/s, and most of that is
its `assumed` nose length of 0.8 diameters: at 2.0 the drag loss falls from 130 to 61 m/s.
`fairing.nose_length_over_D` used to affect only the drawing and the fairing mass and now decides a small
vehicle's drag.

*The vertical rise was not vertical.* Found while validating. Before the pitch kick the flight path angle was
left to Eq. 6:43, whose pitch rate is −(g/v) cos γ. In floating point cos(π/2) is 6e-17, not zero, and g/v is
enormous in the first second, so rounding error grew into a real tilt: under a thousandth of a degree at a
lift-off thrust-to-weight of 1.2, a tenth of a degree at 1.18, as large as the kick itself. The angle is now held
at 90 degrees until the kick. Shipped designs barely move, because their kicks were well above the noise.

*The pitch-programme optimiser's "what stopped me" check had a blind spot.* It probed only a lower handover
altitude, so an optimum already at the 1,000 m floor was compared with itself and reported that no limit was
binding, at 99 % of its q-alpha limit. It now also probes a larger steering angle.

**What changed in v1.0.0 - the first release**

No engineering method or result-producing calculation changed. The validation was re-run on NumPy 2.4 and SciPy
1.17 for this release, and all 24 vehicles in `ACCURACY.md` reproduced to the published decimal.

*Portability.* The test suite had only ever run on Linux, and the first run on Windows found two bugs.
`np.trapezoid` needs NumPy 2, while `requirements.txt` allowed 1.24: **the minimum is now NumPy 2.0 and SciPy
1.13.** Exports opened files in text mode with nothing specified, which on Windows meant CRLF line endings and
the ANSI code page, so a KML file could declare UTF-8 while not being UTF-8. Every text file the code opens now
names its encoding, the interchange exports always use LF, and `tests/test_text_files_portable.py` guards this.
A vehicle sheet that is not UTF-8 is now refused with an explanation instead of being read as garbled text.

*Desktop app.* `tools/build_app.py` builds a Windows folder with `MERLIN.exe`, which runs the full GUI in its own
window with no Python and no browser, using pywebview over Edge WebView2. The data folders sit beside the exe, so
the folder is the whole installation. To make that possible, seven modules that each worked out the project folder
from their own location now share `launch_vehicle.paths`. PDF export also tries Microsoft Edge, which ships with
Windows, so it works without Chrome or wkhtmltopdf. The app is distributed as a GitHub Release download, linked at
the top of the README: pushing a version tag runs `.github/workflows/release.yml`, which tests, builds and attaches
`MERLIN-<version>-windows.zip`. The built app is never committed to the repository.

*Name.* The tool is now **MERLIN**, Mass Estimation Relationships for Launch vehicle Initial sizing. The GUI,
reports and workbook say so. The Python package is still `launch_vehicle`.

*Licence.* MIT with an added attribution requirement, by Szymon Błażejewicz, replacing the all-rights-reserved placeholder,
plus a `CITATION.cff`.

*Git rather than archives.* The project now lives in a repository, so `tools/make_release.py` is gone. A
`.gitignore` takes over its exclusions, and `tests/test_project_metadata.py` keeps its version checks.

*Documentation.* This changelog moved out of the README, which is now a front page. Claims that had gone stale
were corrected, among them "no trajectory simulation, no loads" and the commands written as `lv ...`, which never
existed. The method register now ships in `outputs/`, where the docs always said it was. Leftover notes about a
transfer limit were removed.

**What changed in v0.29.0 — launch vehicle families, and the GUI panel v0.28.0 was missing**

*The architecture trade is now in the GUI.* v0.28.0 shipped the `/api/architecture` endpoint and five tests
for it, and no front end at all — the feature was reachable from a terminal and nowhere else, which for a tool
whose primary interface is the browser means it was not really shipped. There is now an **Architecture &
families** tab: pin the open design's stages and sweep the strap-on count, or re-size the core for a fixed
booster set instead. Two new tests guard the wiring rather than the drawing: every tab the page offers must
have something in `render()` that draws it, and every `/api/…` the page names must be a path the server
actually serves. Both would have caught v0.28.0's gap; neither existed.

*Launch vehicle families.* A family is a folder with a `family.yaml` in it, discovered under
`designs/families/`, `examples/families/` or `validation/families/` with nothing to register. **Delta II
7320/7420/7920** and **Ariane 62/64** ship as families, which also closes a gap v0.28.0 left: the Delta II
3- and 4-booster variants existed only as published numbers inside a test constant, openable by nobody. They
are now designs.

A variant is the base design **plus overrides**, never a copy. Three standalone YAMLs would duplicate three
hundred lines three times and let the "shared" core drift apart one edit at a time — the family property would
be an aspiration. Here the variants literally load the same file, so sharing is structural, and the overrides
are the dotted paths `deep_set` and the GUI already use, so a variant is openable with no new machinery. A
test asserts the A62 expressed as overrides on the A64 sizes to the same vehicle as the separately shipped
`validation/ariane62.yaml`, to one part in 10⁹ — the drift the format exists to prevent. Published figures per
variant are optional but, when present, must carry a source and be marked `reference`: a validation set that
accepts an assumption as a published value has started grading itself against its own guess, and the manifest
refuses it by name. The figures the architecture tests measure against are now **read from those manifests**
rather than hard-coded, so the numbers the tool is graded against live beside the designs they describe.

*And the measurement that came out of it.* A family is the one configuration where the shared-core limitation
is checkable rather than arguable, because the variants fly one core and each publishes its own figure. Both
of the tool's answers are wrong, in **opposite directions**:

| | sized on its own | reference core pinned |
|---|---|---|
| Delta II 7320 | −10.0 % GLOM | +23.1 % payload |
| Delta II 7420 | −6.9 % | +19.7 % |
| Ariane 62 | −23.6 % | +51.5 % |

One cause: the tool never carries a core that is **oversized for the mission being flown**. Sized alone, each
variant gets its own minimal core — the A62's comes out near 52,000 kg against the real shared LLPM's
140,000 kg, so it is far too light. Pinned, the A64's core is about 78,000 kg: bigger, still far short, and a
core lighter than the real one *flatters* the payload, because the strap-ons are never asked to lift
propellant this mission does not need. Real core mass runs tool-alone < pinned < real shared, and the published
payload sits below both estimates — the real A62 pays for sharing the A64's core and the tool never charges it.
That also explains why Ariane's errors are about twice Delta II's: the P120C/LLPM split puts far more of the
stack in the shared core. **Nothing is corrected** — two families and five points, with a mechanism that would
be fitted rather than derived, is the situation §6b and R32 already measured. The gain is that the measurement
is now reproducible on anyone's own vehicle: write a manifest, get both numbers. R38 records the experiment
that would split the bias into its two causes.

**What changed in v0.28.0 — pin a vehicle's stages and change its strap-ons**

*The trade a launcher family is built on.* One core, several booster counts, a published payload for each —
that is how Ariane 6, Delta II, H3 and H-IIA are actually sold. The tool could size each variant from scratch
but could not answer the question a designer asks: *take THIS core and upper stage exactly as they are, fit a
different number of strap-ons, what does it lift?* `python -m launch_vehicle.main architecture` answers it, and `--size-core` answers the
reverse — hold the booster set and let the sizing loop draw a core for it.

*Why the existing performance machinery could not do it.* `performance.FrozenVehicle` carries the parallel burn
as a single stored number and its docstring says the parallel phases "are not re-solved". On Ariane 64 that
number is about **−2,900 m/s**: not a contribution but the difference between the serial rocket equation
applied to the core and the phase model's answer for the same stage — a bookkeeping correction, and a property
of *four* boosters. Holding it fixed while removing two would have produced a confident, meaningless number.
`architecture.PinnedVehicle` subclasses `FrozenVehicle` and re-solves `boosters.phase_sequence` for the
requested count, so everything in `performance` that goes through `delta_v()` and `glom()` works on it
unchanged.

*Verified by round trip, then measured against data.* At its own booster count a pinned design reproduces the
sizing loop's per-stage Δv to one part in 10⁹, the same GLOM and the same lift-off T/W, on all six boosted
check vehicles, and the payload root-find returns the design's own payload to better than 0.1 %. Then the
honest part: pinning inherits the core-sizing error of whatever you pin, and against the two families that
publish a payload for several counts of one core it **over-predicts the smaller variants by 19–52 %** — Delta
II 7920's core with 3 GEM-40 gives 3,436 kg against a published 2,800 kg, Ariane 64's with 2 P120C gives
10,910 kg against 7,200 kg. Both families err in the same direction and the two pinned Ariane cores agree with
each other, so it is a model property, not scatter. **No correction is fitted** — §6b already measured that
fitted loss corrections do not survive leave-one-out, and this one would be absorbing a core-sizing error under
the name of a loss model. The bias is printed beside every sweep instead, and the open item it produced (R36,
per-configuration ascent time) names the avoidable half.

*Refusals that are refusals.* A count whose lift-off T/W is at or below 1.0 returns **no payload at all** —
Ariane 64's hydrolox core alone gives 983 kN against 1,518 kN of weight — with the Δv-feasible value moved to
a field that cannot be mistaken for a capability. A count whose boosters outlast the core's propellant comes
back with the phase model's own message and its two solved remedies.

*Also in this release.* An air-lit booster is lift-off mass and no lift-off thrust, so Delta II 7920's T/W
peaks at its six ground-lit boosters and falls after — the ignition-split rule now preserves a design's
ground-lit count rather than inventing an air-lit group a design never had. The R34 infeasible-geometry message
regained the word "infeasible" it lost in v0.27.

*A test that was asserting something its file format cannot carry.* `test_dxf_silhouette_matches_the_geometry`
compared DXF coordinates to 1 nm while the exporters write `{value:.6f}`, so it was only ever passing while
every profile coordinate happened to land on six decimals. It failed on 13.320160296483188 being stored as
"13.320160" — a 3.0 × 10⁻⁷ m rounding artifact, not a geometry error. Reproduced on the untouched v0.26.0
package before changing anything, so it was not a regression. The comparison now runs at half a unit in the
exporters' last decimal (5 × 10⁻⁷ m, half a micron, finer than any CAD tolerance a launch vehicle is built
to), which is the tightest bound the format can actually support; the way to tighten it further is to give the
writers more decimals, not to raise the number in the test.

*And the reason that test looked green: the two runners did not agree.* Chasing the above turned up something
worse than the test itself. The project ships `tools/mini_pytest` as an offline stand-in for pytest, and its
`approx` computed `max(abs, 1e-6 · |expected|)` in every case — so `approx(x, abs=…)` was always at least as
loose as a part-per-million relative check. Real pytest does the opposite: giving `abs` alone **suppresses**
the default relative tolerance. The suite calls that form **151 times across 29 files**, so every one of those
assertions was quietly weaker offline than it reads — `approx(13.32016, abs=1e-9)` was really a 1.3 × 10⁻⁵
check. A suite that is green under one runner and red under the other is worse than no suite, so the shim now
implements real pytest's three documented regimes exactly, including the 1 × 10⁻¹² absolute floor that applies
when only `rel` is given (dropping that floor broke a faceted-volume test offline while it passed under real
pytest — the same divergence in the other direction). `tests/test_python_compatibility.py` now **differentially
tests the shim against real pytest** on fourteen cases spanning all three regimes, and walks the whole suite's
AST for every `pytest.X` attribute the tests reach for. That scan immediately found two more gaps: `mark.
parametrize` was missing entirely, which stopped the offline runner dead on the first file that used it, and
there was no top-level `skip()`, so test_loads.py's two legitimate self-skips were being reported offline as
*failures*. Both are fixed, and the runner now prints `SKIP` for a skip.

Encouragingly, the 151 strict assertions all hold under the strict reading: **the whole suite passes under
both runners — 1,091 tests under real pytest, 1,081 under the offline shim, no failures either way.** The
difference is exactly the ten parametrized cases the shim collapses into their two wrappers, which is the
one behaviour it cannot reproduce without the runner expanding tests.

**What changed in v0.27.0 — two new check vehicles, and a case the tool cannot yet size**

*The payload/altitude confound is broken, and the v0.26 conclusion survives it.* `ACCURACY.md` §6b could not
calibrate an ascent-loss correction because every small-payload check case flew to 500–700 km SSO and every
large-payload one to about 200 km, so the two variables were indistinguishable. **Minotaur I** (580 kg to
**185 km**) is the small-payload/low-orbit example that was missing, and its masses close independently: the
four stage masses from one source plus the payload sum to 35,926 kg against a 36,200 kg lift-off mass
published by another, leaving 274 kg for fairing, avionics and adapter. **Long March 12** (12,000 kg to
200 km) adds the large-payload end. The low-orbit group now spans a forty-fold payload range and its Δv gaps
are −214, +247, −127 and −1,088 m/s — no monotonic relationship to either variable. Re-running leave-one-out
over all eight vehicles with published masses, **nothing still beats applying no correction** (481 m/s null,
best model 516). That is a stronger result than v0.26's: the earlier analysis could not tell the two
hypotheses apart, this one can and finds neither.

*Minotaur I is also the best independent check yet on the v0.26 casing decision.* It predicts stage inert to
a **mass bias of +2.2 %** across motors spanning 770 kg to 20,785 kg of propellant, using `book_steel` on its
two 1960s Minuteman stages and `kibbey_medium` on its two composite Orion motors — its real construction,
not a fitted choice.

*A regression worth admitting.* The v0.26 Kibbey change had been made by editing the generated YAML files
rather than the generator, so the first run of `tools/make_validation_cases.py` in this version silently
overwrote all six solid cases back to the book's constant. The change now lives in the generator, where
regeneration cannot undo it, together with the per-method source text and M-V's exemption reason.

*A whole vehicle class was unblocked, and then four of them added.* The tank geometry check ran at every
iteration **including the crude seed**, which under-fills a hydrolox core whose boosters carry most of the
lift-off impulse: iteration 1 asked a 5.4 m tank to hold 35 m³ where its end caps alone take 58 m³. It was
refusing designs that are feasible once converged. The checks now run inside
`tank_sizing.tolerate_oversized_tanks()` while iterating and the **converged** design is re-checked with the
tolerance released, so a genuinely unbuildable tank still fails identically. The core/booster phasing check
was deliberately left alone and still refuses a starved core. Recorded as **R34**.

That unblocked **Ariane 62, Ariane 64, SLS Block 1 and H3-24L**, and the four of them turn out to measure one
thing no single case can: how far a real core is oversized relative to its own mission, because a real core is
shared across a family.

| vehicle | the core is sized for | published | tool | error |
|---|---|---|---|---|
| **H3-24L** | its own class | 575,000 kg | 552,866 kg | **−3.8 %** |
| **Ariane 64** | itself | 860,000 kg | 779,654 kg | −9.3 % |
| **SLS Block 1** | Block 1B and 2 as well | 2,610,000 kg | 2,343,799 kg | −10.2 % |
| **Ariane 62** | the A64, not the A62 | 530,000 kg | 405,226 kg | **−23.5 %** |

Every one comes out light, and the ordering follows the explanation rather than the vehicle size. Two
independent checks make it more convincing than the lift-off masses alone: H3-24L's boosters come out at
exactly their published 67,200 kg, and SLS Block 1's length lands at 95.2 m against a published 98.1 m.
**Read an absolute mass from this tool as the mass of a minimum vehicle for the stated mission, not as a
prediction of what a manufacturer will build.**

*Long March 6A was rejected on data* — its four FG-112 boosters carry 67 % of lift-off thrust and no source
publishes their propellant mass, inert mass, Isp or burn time, so deriving it from the lift-off mass would
have meant fitting to the number under test.

*A reference-quality audit, prompted by Zhuque-2.* `tools/reference_quality.py` reports how much of each case
is sourced rather than assumed, and flags any case whose *critical* inputs — Isp, thrust, propellant load —
are assumptions. Zhuque-2's −31.7 % error turns out to measure an assumption, not the model: its three Isp
values are tagged `assumed` with source text reading "TQ-12 Isp not found", its engine is a named placeholder,
and a plausible 15 s Isp reduction moves its error to −19.0 %. Those values were **not** adjusted — picking an
Isp because it shrinks an error is tuning an input to match a vehicle. Long March 12 lands on the same list
(the uprated YF-100K's Isp is unpublished), which is the audit catching a case added in the same release.

**What changed in v0.26.0 — the solid mass model, and a calibration that was measured and then refused**

*The solid error is closed.* Composite-cased solid stages now use Kibbey's size-dependent NASA relation
instead of the book's flat casing constant (Eq. 8:18, k = 0.1154), which carries no scale term and so
predicts the same inert fraction for a 141-tonne P120C as for a 215 kg Altair. Measured on the 16 published
solid stages at their published propellant loads, mean absolute stage-inert error falls **51 % → 23 %** and
median bias **+52 % → −8 %**; across all eighteen check vehicles with everything else held constant, mean
absolute GLOM error **on the as-written splits** falls **37.8 % → 18.0 %** with every liquid vehicle
unchanged to the kilogram (that comparison holds the split fixed so the casing relation is the only variable;
with the split re-optimised the same 18 vehicles average 11.4 %). With the
split re-optimised, the solid group goes from a median \|error\| of **33.4 % to 8.0 %**. Vega and Vega C now
land at +0.5 % and +4.6 %. **Steel cases were deliberately left on the book constant** — Kibbey on a
segmented-steel case is 45–49 % light, where the book's steel k is within −2 % to +5 %. Two honest
consequences: solid estimates are no longer reliably conservative (Scout, Pegasus and Epsilon now
*under*-predict), and motors below about a tonne of propellant are still badly served by every relation.

*A loss-model correction was fitted, tested, and not shipped.* The Δv gap against each vehicle's own
published masses looks like a clean small-vehicle bias, and it is not: payload and altitude are perfectly
confounded across the check set, and M-V — the only vehicle with a small payload to a *low* orbit — refutes
both a payload fit (out by 1,209 m/s) and an altitude fit (1,034 m/s). Leave-one-out, **every candidate
correction is worse than applying none**. It only looked good with M-V deleted, and M-V was deleted on an
assumption its own design file refutes. [`docs/ACCURACY.md`](ACCURACY.md) §6b records the whole
attempt, including what data would make it calibratable.

*The ascent module no longer reports what it cannot model.* A GTO or GEO mission is not flown at all now,
because the real vehicles fly those as burn–coast–restart (Atlas V 551 uses three Centaur burns around a
508 s and a 9,000 s coast; Delta IV Heavy three DCSS burns through a 117 × 851 nmi parking orbit) and this
model burns every stage continuously to depletion. The Trajectory tab says "not simulated for this mission
class" rather than presenting a failed shoot as a diagnosis. Ariane 5 ECA is the case that proves this is
about the profile and not the orbit: its ESC-A is **not** restartable (945 s, one burn, direct ascent), and
its ascent failed because the tool gives it twice the real propellant.

*An offered one-click fix sat exactly on a boundary.* The suggested casing diameter was 0.5 mm inside the
feasibility limit, which does not survive the design re-converging — narrowing a stage changes its mass,
which moves the limit. Measured: 0.5 mm failed, 1 % failed, 2 % was the first that settled; the offer now
carries 5 %, verified on all 14 solid stages in the check set.

**What changed in v0.25.1 — a session spent using the GUI, and five things it turned up**

Not a feature release: this is what came out of building vehicles in the browser rather than testing modules.
All 31 shipped designs open and size through the GUI with no script errors, Save and reopen round-trips to
the kilogram, and every download works — but five real defects surfaced, four of them invisible from the
command line.

*A failed analysis was presented as a result.* Ariane 5 ECA, Delta IV Heavy and Atlas V 551 do not converge
their ascent trajectory — the shooting method cannot fly a stage that burns continuously for 1,300–1,900 s,
which is what the model builds for a mission the real vehicle flies with a coast and a restart
([`ACCURACY.md`](ACCURACY.md) §9 has the measured breakdown across all 24 check cases). The
Trajectory tab rendered that failure as though it were an answer: **burnout altitude −0.22 km** (the vehicle
had hit the ground), **max-q 4,833 kPa** (fifty times reality), under four authoritative-looking charts, with
"Converged: false" as the first of four unremarkable table rows. It now leads with a red banner saying the
analysis did not converge, **why** (the shooting status, which was not reported at all before), that the
figures below describe the failed attempt rather than the vehicle, and which other analyses produced nothing
as a result. A design whose trajectory does converge gets no banner.

*Naming a real engine did nothing.* Pick "Merlin 1D" for stage 1 and the lift-off mass came back identical
to the kilogram, because the database never overrides a value the design file states — a deliberate,
documented contract, warned about three times, but only in the Checks tab. At the dropdown itself nothing
happened, which reads as a broken control. The pick now **clears the figures that engine supplies**, exactly
as picking a propellant combination sets the fuel and oxidiser, and says what it cleared. Merlin 1D now takes
the shipped default from 410,003 kg to 382,231 kg, RD-180 to 332,231 kg.

*Any stage past the second opened collapsed.* `OPEN_SECTIONS` named "Stage 1" and "Stage 2" literally,
written when every design had two. So Scout's four stages opened with two of them folded away, and a stage
added with the new stage-count control arrived collapsed — with the fields the note had just told the user to
fill hidden behind a disclosure. Every stage a design has now opens.

*The liquid/solid switch was filed under housekeeping.* A liquid design does not spell out `stage_type`, so
the row is synthesised and honestly tagged `assumed` — and the panel folds assumptions away, which put the
one control that turns a stage into a solid motor behind a disclosure reading "N assumed or unused values".
A control that changes the shape of the design is not an assumption, and is no longer treated as one.

*Validation errors pointed nowhere.* The geometry and sizing errors have named their field for several
versions; `validate_spec` still raised a bare sentence, so the fairing being too narrow, the payload envelope
not fitting and a jettison stage out of range left the user to find the input themselves among several
hundred. Those now carry a field and computed one-click fixes — "Widen the fairing to 3.00 m", "Or shrink the
payload envelope to 2.80 m" — each verified to resolve in a single click. Warnings carry them too, so the
Checks tab offers the same jumps and buttons a hard refusal does.

Also: several dropdowns clipped the value you had *chosen* ("Geostationary tran…", "None - core stage…"), so
the select column is wider.

**What changed in v0.25 — the optimiser stopped being a footnote, and was caught failing silently**

*It was optimising nothing you could act on.* The report printed an optimal delta-v split beside a vehicle
sized from **your** split — two different rockets in one document, with the better one reachable only by
reading the number off the report and typing it back in by hand. `vehicle.optimise_dv_split` now replaces
the allocation **before** sizing, so the mass, geometry, loads, drawing and cost all describe the same
vehicle as the split that is reported. Off by default, because the staging split is a decision the user
makes; when it is on the GUI writes the applied split into the panel with its revert arrow, and the design
file is untouched until you save.

*And it was silently returning the wrong answer.* On `examples/example_3stage_leo.yaml` the equal split does
not size at all. Every neighbouring point in the simplex is equally infeasible, so the local search saw a
flat penalty with no gradient, **gave up after 11 evaluations and returned the equal split it started from —
reporting it as the optimum**. Nothing checked the `success` flag, so the GUI would have written that worse
split into the design and announced it as roughly a trillion kilograms lighter. A multi-start finds
**338,329 kg against that design's own 355,389 kg**. The search now samples the allocation simplex first,
keeps the feasible points and refines from the best of them; the spread between starts is reported rather
than claimed away; and a search that finds nothing comes back as a failure with the reasons counted.

*Three objectives, and one of them was a trap.* `glom`, `cost` and `payload` are now selectable. `cost`
means **development** cost, because the chapter's cost per flight is a rule of thumb on payload mass that
was measured not to move by a single dollar across a 28 % spread of lift-off mass — an objective blind to
what it is optimising. The development CERs are mass-driven and do respond, and they give a genuinely
different answer: on the shipped default, lightest is near 35/65 and cheapest to develop near 46/54.

*The sizing loop's own seed was checked while we were at it*, prompted by Balesdent (2011) App. B, which
found a fixed-point iteration landing on different optima from different seeds. Swept over s = 0.05–0.18 on
five designs, our converged GLOM is **identical to ~1e-8** — one fixed point, and now a test. No trajectory
quantity enters any objective, deliberately: the drag model is a single C_D(M) curve and there is no
throttle profile. The whole thing is written up in [`docs/OPTIMISATION.md`](OPTIMISATION.md).

**What changed in v0.24.1 — strap-on boosters became an input too**

*Same gap, same shape.* The model has flown strap-ons since Ariane 5 ECA, Atlas V 551, Delta II 7920, Delta
IV Heavy, H-IIA 202 and Soyuz-2.1b became check cases, and the GUI renders all 32 booster fields — but only
for a design whose file already carried a `boosters:` block. A design without one had no way to get them;
Ariane 5 had no way to lose them. There is now a **Strap-on boosters** control beside the stage count:
none, solid, or liquid.

The donors are chosen by measurement, not by obviousness. Solid comes from the generic GEM-class motor in
`examples/example_boosters.yaml`, liquid from **Soyuz-2.1b** — and explicitly not from Delta IV Heavy, whose
Common Booster Cores carry 200 t each at 5.1 m and drive any smaller core out of propellant before they burn
out. That was the one graft of four tried that would not size. Removing the block touches nothing else:
`attach_stage` is pinned to stage 1, so there is no index to clamp and no delta-v split to rebalance.

*Three defects found by building it.* The booster path called the solid-motor casing sizer, which names its
way out as a bare `diameter_m` — a serial stage completes that to `stages[N].…`, but nothing completed it
for a booster, so the GUI was handed a path resolving to nothing and the one-click fix died with "unknown
parameter path". The "no thrust left for the core" refusal carried no field at all; it now says the boosters
alone already produce a lift-off T/W of *x* against the *y* asked for, and offers the T/W that makes room.
And the "core runs out of propellant" fix **oscillated**: shortening the burn moves the very limit it is
solving, so a 2 % margin has the user clicking forever. It is 10 % now, because 10 % is what converges — and
when the boosters dwarf the core the refusal leads with shrinking them instead, since retiming is the wrong
lever there. An offered fix that loops looks like progress and is worse than none.

*A result worth knowing:* take the EAPs off Ariane 5 ECA and the tool sizes it at **738 t, lighter than the
855 t with them**, with the core nearly tripling. Not a bug — the EAPs run at about 275 s against the
cryogenic core's ~430 s, so core propulsion buys the same delta-v for less propellant. Strap-ons are for
thrust off the pad and a smaller core, not for efficiency. The first test written for this asserted the
naive opposite and was wrong.

**What changed in v0.24 — the number of stages became an input**

*It never was one.* The stage count was the LENGTH of the `stages:` list in the YAML, so a new design was
two-stage because the shipped default has two stages, and a three-stage vehicle meant editing YAML by hand.
Staging is the first decision in conceptual design. It is now the first control in the input panel, above the
sections, because it is the shape of the design rather than one of its values — and like the liquid/solid
switch it rewrites the document rather than setting an override, because adding a stage adds a whole
annotated sub-document.

What makes it safe rather than merely possible is that nothing moves silently. A new stage is **grafted from
the uppermost stage of the shipped example** of the same type, so it arrives with real units, descriptions,
sources and provenance tags; the donor's *upper* stage is used and not its first, because a first stage
carries a sea-level nozzle and a first-stage thrust-to-weight that above the atmosphere would quietly cost
delta-v. It goes on top, takes the cross-section of the stage below it, and the **delta-v split follows with
the existing stages kept in proportion** — a 44/56 decision stays a 44/56 decision — re-tagged `assumed`,
because whatever the user chose, it was not this. The fairing jettison stage and `last_ascent_stage` are
pulled back inside the new count, and the fairing is widened if removing a stage left it narrower than the
new top stage. Every one of those is named in the note shown against the control.

*Asking for one stage to orbit now gets an explanation instead of `mu*s >= 1`.* The seeding failure is the
rocket equation — one stage at 10 % structure cannot exceed Isp·g₀·ln 10, about 6,550 m/s at 290 s — and it
is one click away now that the count is a control. It says what the stage was asked for, what the ceiling is
at that Isp, and that the delta-v needs spreading over more stages, with a button that goes to the control.
`gotoField` used to bail out silently on a field with no input row behind it, which would have made that
button do nothing.

*An outside MER compilation was evaluated and rejected, with the measurement published.* Rohrschneider's 2002
Georgia Tech database was checked for solid-motor relations: it has none — its 28 sections are a winged-RLV
breakdown (Wing, Tail, TPS, Landing Gear, Crew & Gear) and its only solid content is an SRB attach-structure
coefficient. Where it does overlap, it was measured rather than assumed: its engine relations come out at
42–67 % mean absolute error against the 16 engines in the database, against **31.9 % for the book's
Table 8.9**, because a thrust-proportional rule fixes installed T/W at ~49 and overpredicts small
high-expansion engines fourfold. Its avionics relation predicts 663 kg of avionics on Vega's 147 kg AVUM. All
of it is in [`docs/EXTERNAL_MERS.md`](EXTERNAL_MERS.md) with the arithmetic to reproduce it.

*Packaging is a script now, and a checked one.* `tools/make_release.py` builds the archive, excludes
residuals by declared reason (bytecode, GUI drafts, saved designs, generated outputs), and **refuses to write
an archive that is missing anything the tool needs to run**. That check immediately found a file this
project's own documentation referred to and that has never existed. It also warns, on every build, that the
all-rights-reserved LICENSE still names `<COPYRIGHT HOLDER>` — a gap only the owner can fill, so it is
stated rather than invented. Section 7 of the user manual was renumbered: this session's additions had
collided into three duplicate numbers and the contents list was missing half the subsections.

**What changed in v0.23.1 — a syntax error on older Pythons, and the staging field made legible**

*It would not run at all on Python 3.11.* `report.py` had a backslash inside an f-string EXPRESSION, which
is PEP 701 syntax accepted only from 3.12; before that it is a hard `SyntaxError` and the module never
loads. The project declares support for 3.10. A guard for this existed and checked two PEP 701 forms but
not this one — and the first fix for THAT was written as an `elif` after the nested-quote test, so the very
token carrying the backslash was consumed before it could be examined. Both are fixed, and since an older
interpreter turned out to be installed, the suite now **compiles every file with the oldest Python on PATH**
and differential-tests the detector against it over twelve constructs, legal look-alikes included.

*The tank geometry error told users to set a field that did not exist.* `tank.diameter_m` is read by the
sizing code and documented as method M47, but appeared in no shipped design file, so it was in no form and
could not be set. Added to all 50 tank blocks. That error now carries the field and a **"Narrow this
stage's tanks to 1.12 m"** button, like the solid-casing one; where flattening the domes would need an
aspect ratio of 27, the tool says so instead of offering a flat plate as a fix.

*A GUI audit, done by method rather than by eye.* Comparing every key the loader reads against every field
any shipped design exposes found four inputs that existed only in the loader: `tank.diameter_m`,
`tank.user_mass_fuel_kg`/`_oxidizer_kg`, `engine.geometry_method`, plus `avionics_mass_override_kg` and
`max_length_m`. The worst was `user_mass`: **selectable in the tank-method dropdown**, and without its
fields it sized the tanks at zero, silently, for a vehicle 5 % light. That is now a hard error naming the
field, and the check is a permanent test. The **sensitivity studies and configuration comparison** — which
ran in the CLI by default and reached the Excel workbook — had no way in from the browser at all, and are
now a tab of their own.

*The delta-v split is no longer a list of fractions in a text box.* It was the most consequential input in
the design and read like a debug field. It is now one percentage per stage, each showing the m/s it buys, a
running total that says when it does not add up, and **"Find the lightest split"** — the optimiser that was
already in the engine with no button anywhere. On the shipped default it finds a split 73.9 t lighter.

**What changed in v0.23 — six faults found by using it, and three more materials**

*Eight shipped designs could not be sized in the GUI at all.* Saturn V, Falcon 9, Titan II, Vega C, Epsilon,
M-V, Zhuque-2 and one example returned `is not valid JSON`. The cause was one line: Python writes `NaN` and
`Infinity` into JSON, which `JSON.parse` rejects **for the whole document**, so a single legitimate
not-a-number — a trim deflection for a stage with no gimbal authority — lost the entire response. Non-finite
values now travel as `null`, with a note saying which case it was, and a test sizes every shipped design and
parses the result strictly.

*Picking a launch site broke sizing.* The site dropdown pushed a longitude into a field **no design had**, so
the tool refused with `unknown parameter path 'mission.launch_site.longitude_deg'` — which read as it
demanding a longitude it had just been given. Every design now carries `site` and `longitude_deg` leaves, and
a check case that names a site no longer reports its library-filled latitude as an empty field.

*Save on a new configuration raised a raw `TypeError` and left a broken file behind.* It wrote the file, then
validated it by loading it, and a deliberately blank field failed the load after the write. Saving is now
atomic — temp file, validate, move — and a part-filled design is refused by name: "Fill in 'mission > payload
mass kg' and 13 other(s)".

*Errors now point at the field and offer the fix.* An impossible solid casing used to say "reduce the
diameter or add propellant"; it now solves both exactly and offers **"Make this stage no wider than
0.554 m"** as a button that sets the value, beside the field it belongs to. A test applies the suggested
number and asserts the design then sizes.

*The Open dialog offered a trade-study file as if it were a vehicle.* It is listed by content now, not by
name.

*Three more structural materials*: stainless 301 full-hard, stainless 304L and Ti-6Al-4V, each with sourced
properties and all derated on **the same 0.633-of-minimum-yield basis** as the existing aluminium, so a
material trade is decided by metallurgy rather than bookkeeping. A `MATUNUSED` warning fires when a design
names a material that its own tank mass method ignores — which is most of them, and was previously silent.

**What changed in v0.22 — drop zones, and a release pass**

*Where each jettisoned item comes down.* A new `Drop zones` tab and three new modules: each spent stage,
fairing and strap-on is flown from its separation state down to the surface, and the result is an impact
point with an along-track dispersion interval, exportable as **KML** (Google Earth) or **GeoJSON** (QGIS).

*An item that does not come down is not given a landing.* The orbital test is done in inertial terms, adding
the rotating surface's eastward speed, so an upper stage released near orbital speed is reported as staying
up rather than having an impact point invented for it.

*What sets the size of a hazard area — measured, and not what the first guess said.* Sweeping a tumbling
stage's drag coefficient over its whole plausible range moves the impact point **12 km out of 1,084**, about
1 %, because nearly all the downrange is flown in vacuum. A **5 % error in separation speed moves it 100 km**.
The drop zones are therefore downstream of the mass model: at roughly 20 km per percent of separation speed,
the 33 % solid-vehicle mass error in `ACCURACY.md` is worth a hundred kilometres or more of impact point.

*An item that cannot be placed is not placed.* A stage separating near orbital speed has a dispersion corner
that never comes down; integrating it anyway yields a "hazard area" 36,000 km long. Such items are reported as
**not localisable** — nominal point, no box. On Vega C that gives three drawn zones, one marginal stage and
one that stays in orbit.

*Three things that were command-line only are now in the GUI.* A **Trade & compare** tab runs declared
trade-study sweeps and sizes several designs side by side, showing the same table the CLI and the report use;
the Report tab gained a **Download PDF** button. `import-vehicles` is still command-line only.

*The release pass found four defects worth naming.* Two GUI checkboxes ran nothing at all — the ascent
optimisation was requested under the key its RESULT comes back as, and stability was offered without the
trajectory it is computed from. `pandas` was a declared dependency that nothing imports. And the version in
`pyproject.toml` had been left behind at 0.21.0. All four are fixed and the first two now have tests that
compare the browser's study vocabulary against the keys the engine actually gates on.

*The width of every box is an assumption, stated as one.* A pitch-plane trajectory has no cross-range state
at all, so nothing here predicts it. The drawn half-width is floored at the Coriolis cross-range the descent
model omits (40–92 km), so the area is never narrower than an error known to be missing from it.

**What changed in v0.21 — an accuracy document, and two more solid vehicles**

*[`docs/ACCURACY.md`](ACCURACY.md) is the new headline.* It answers the two questions the validation
report only answered in pieces: how far off is each of the eighteen check cases, and **which part of the
model put it there**. Each vehicle's error is attributed to a delta-v part, a mass part measured at the
published propellant load, and a measured `dGLOM/dInert` sensitivity.

*The headline numbers.* All-liquid vehicles: **9.4 % median absolute GLOM error** over twelve cases.
Vehicles with serial solid stages: **33.4 %** over six.

*And the explanation.* The gap is not one mistake. It is two model errors that land on the same population
multiplied by a sensitivity three times higher there — liquid vehicles sit at `dGLOM/dInert` of 0.11–0.79,
solids at **1.16–1.87**. The solid mass model is worse *and* it matters more.

*Two new check cases, both with authoritative data.* **M-V** (ISAS/JAXA's own configuration page — the only
case sourced from the agency that built the vehicle) and **Vega C**. That takes the serial-solid sample from
four to six, and moved the median from 43.7 % to 33.4 %.

*M-V is the most interesting vehicle in the set, because it breaks the pattern.* Its first stage is
**heavier** than the book's constant — inert/propellant 0.153 against k = 0.1154 — where every other solid
here is lighter. It lands at **+3.9 %**, the best solid result in the suite, and it does so because a
−1,058 m/s delta-v surplus cancels a +34.2 % mass bias. Two large errors in opposite directions. The book
is not conservative about solids; it is uncalibrated, and which way it errs depends on the vehicle.

*Three bugs found while doing this.* The delta-v optimiser ignores casing geometry and can starve a stage
below what its own diameter holds (M-V's 2.2 m third stage); the full-outputs step forced the optimised
fractions regardless of feasibility, which killed the whole run; and Vega C's stage inert masses differ by
**20–54 %** between two sources for the same three motors, which is now reported rather than averaged away.

*One error that is not a bug.* Scout and M-V raise `ENGFIT` on their as-published split: the nozzle is
computed from the thrust the *sized* vehicle needs, and a nozzle for a 54 t Scout does not fit a 1.14 m
case. That is a true statement about an oversized design, so it is left in rather than suppressed by
quietly lowering an assumed expansion ratio.

**What changed in v0.20 — solid motors, measured instead of assumed**

*The question that started it: why do solid stages disagree with real data?* The answer turned out to be
four separate things, and the first one is that the tool was comparing a **motor** coefficient against
**stage** figures. The book's k_SRM covers a case, insulation, nozzle, thrust structure and TVC. A published
"stage inert mass" covers those plus skirts, interstage, avionics and separation hardware — and on Scout's
third stage that gap is **237 kg against a 98 kg motor**.

*55 motors, measured.* `solid_inert.MOTOR_DATASET` holds the STAR family, whose loaded and burnout masses
are published together, so the difference is motor inert with nothing else in it. They span 25–4,590 kg of
propellant. What they show is that **motor inert fraction is not constant**: it falls from ~0.18 at 30 kg
toward a floor near 0.060, so the book's single k = 0.1154 crosses the real curve near 150–200 kg and is
**36 % low below 100 kg and 26 %, 44 % and 51 % high** in the bands above it.

*A relation fitted to them.* `star_motor`: f = 0.0602 + 0.0051 (m_p/4536)^(−2/3), MAPE 14 %, bias +2 %. Two
independent checks — the fitted floor lands on the 0.060 Kibbey published from different data, and on
**Star 31, absent from the dataset and sourced from Thiokol rather than Wikipedia**, the book is +51.0 % and
this relation is **−5.8 %**.

*Eleven real motors in the database*, Star 17A through Star 63F, each with its own published
inert/propellant ratio — 0.0616 to 0.125, where the book uses 0.1154 for every one of them.

*Why nobody noticed.* Two errors were cancelling: the book over-predicts the motor while the build-up
under-charges the stage equipment. Across twelve stages the book's stage-level bias is only +1.3 % median —
against 24.5 % MAPE. **The cancellation is accidental and size-dependent**, so it protects nothing on a
smaller vehicle.

*A latent bug, found and fixed.* Naming a real motor loaded its published k into `casing_mass_fraction` and
then a stage stating `book_composite` ignored it — 148 kg of book motor against 98 kg of real motor, while
the user believed they had selected real hardware. That now warns, and every solid stage declares whether it
is a **real motor** or a **notional** one.

*What it is worth.* A three-stage solid carrying 150 kg to 500 km polar comes out at **45,148 kg** with the
book's coefficient and **34,945 kg** with the real Star 37FM — **29 % apart**, which is larger than the
margin most liquid-versus-solid trades turn on.

*Scoping, honestly.* `star_motor` is fitted to apogee-kick motors — no TVC, no flight structure — and runs
31 % light against real launch-vehicle stages. Those are two populations about 40 % apart, so it is scoped
to upper-stage class and says so in every source string it emits. Two things were tried and rejected: a pure
power law (no floor, misses the big motors by 25 %) and a size-dependent LV-stage relation (18.8 % MAPE
against Zandbergen's 19.9 % on N = 17 is noise, and its steel form predicts f > 1.0 at 215 kg).

12 new tests, 825 in total, all passing.

**What changed in v0.19 — Scout G-1, and what a four-stage solid exposes**

*A new check case, chosen to break things.* The NASA/LTV **Scout G-1** is the smallest vehicle in the
validation set and the only one whose **per-stage inert masses are published by the manufacturer** — from
Tanck & Williams (LTV Missiles and Electronics Group), citing the **SCOUT Planning Guide** (LTV, May 1987).
Its four solid stages run from 12,817 kg of propellant down to **215 kg**, which is 14× below the smallest
stage the published inert relations were fitted to. Two of the four are independently corroborated:
Zandbergen's table already carried Scout stages 1 and 2 at exactly these figures, and Thiokol's own catalogue
gives the Star-31 a propellant load 1.0 % from LTV's.

*It broke four things, which is what it was for.*

1. **The published relations under-predict small stages badly.** Given Scout's published propellant and asked
   only for inert mass — no delta-v, no Isp, nothing that could absorb the error — every applicable relation
   came out 30–75 % low on the two small upper stages, against an in-sample bias of −3 % to +1 %. Both stages
   are below the fitted floor of every Zandbergen relation. They are now kept in
   `solid_inert.OUT_OF_SAMPLE`, deliberately **apart** from `DATASET`, because adding them to the fitting set
   would quietly change what "fitted to 34 stages" means.
2. **An affine relation must never be extrapolated downwards.** `zandbergen_steel_S2` is
   `0.1689 m_p + 509 kg`; on a 215 kg stage the constant alone is 509 kg, giving an effective k of **2.54**
   and a vehicle **378 %** too heavy. The tool already says `EXTRAPOLATED` in the source string and warns —
   nothing acts on it. Now roadmap **R30**.
3. **The validation report's own "published casing k" column double-counts.** It feeds a *stage-level*
   published ratio into a *motor-level* input, after which the build-up adds skirts, avionics and margin on
   top. At Pegasus' k = 0.091 it hides; at Scout's stage-2 ratio of **0.282** it produces 72 t against a
   published 21.7 t. Scout is excluded from that column and the Pegasus/Vega entries are now flagged as not
   to be quoted. Roadmap **R31**.
4. **A third of the error is not the mass model at all.** Scout's own published masses and Isp give
   **9,087 m/s** of ideal delta-v; the tool asks for **9,738 m/s**, against an ascent-loss regression whose
   stated RMS error is ~260 m/s. Roughly **35 of Scout's 55 points of GLOM error are the loss model and 19
   are the mass model** — and every previous solid case in the report had attributed the whole error to the
   casing MER. Roadmap **R32**.

*And it corrected a claim this project had been making.* "Solid stages come out 1.2–1.6× heavy" was true of
every modern filament-wound motor in the set and is **not** a general statement. Scout's four stages come out
at 1.05, **0.73**, **0.66** and 1.34: a 1960s stage carrying its guidance section is *heavier* than the book's
coefficient, not lighter. The coefficient describes Shuttle-SRB-era steel hardware and is wrong in both
directions once you leave that era.

Scout itself lands at **+62 %** on the optimised split — the worst case in the set, and the smallest vehicle
in it. The six legitimate in-range relation combinations span −21 % to +5 %, bracketing the published 21.7 t.
Median absolute error over all sixteen cases is now **15.0 %**.

11 new tests, 813 in total, all passing.

**What changed in v0.18 — the user-experience pass**

*You can say where it launches from.* `config/launch_sites.yaml` holds **28 real launch sites** with sourced
coordinates — American, Russian and Kazakh, Chinese, European including **Andøya, Esrange and SaxaVord**, and
the rest — grouped by region in a dropdown. Picking one fills the latitude and then does the thing that
actually matters: a direct ascent cannot reach an inclination below the site latitude, because
`sin β = cos i / cos φ` has no solution there, so an inclination under that floor is **raised to the floor with
a note saying why**. Picking Kennedy (28.6082°) on the shipped default (28.5°) would otherwise have put the
mission one tenth of a degree under its own floor, and the user would have met that as an infeasibility on
pressing **Size**. The library deliberately holds **no pad altitudes** — the sources give none — and **no
range-safety azimuth corridors**, which are per-pad, per-vehicle and per-year; none were invented to fill the
gap, and the file, the module and the manual all say the floor is a *necessary* condition for a direct ascent,
never a sufficient one.

*There is a New button, and it clears the brief rather than the file.* What a new design asks for is the
payload, the orbit, the site, the diameters, the staging split, the engines and the Isp. What it leaves alone
is everything the method owns. The obvious rule — clear every leaf tagged `provenance: user` — was tried and is
**wrong**: it picks up `throttle_min_fraction` (1.0, meaning no throttling) and `launch_site.altitude_m` (0.0,
sea level), and clearing the first makes the design unsizable. So the brief is a written-down list with a
reason per field, shown under each cleared field. Sections holding a cleared field open themselves, the header
counts what is still empty, and **sizing an incomplete design leads with the empty fields** instead of with
whatever arithmetic reached the `null` first — which for a blank payload envelope was a bare
`TypeError: unsupported operand type(s) for *: 'NoneType' and 'float'`.

*Save means save.* Once a design is bound to a file of its own, **Save** overwrites that file — same path, no
dialog, no second copy — and the header says which file it is. **Save as** takes a new name and switches to it,
asking before replacing anything. Neither can touch a shipped file: `config/`, `examples/` and `validation/`
are reference material, and a check case quietly edited is a check case that no longer checks anything.

*A stage can be switched between liquid and solid.* This is the one edit that cannot be an override, because
the two are different documents — fuel, oxidiser, engine and tanks against propellant and motor. The new block
is **grafted from the shipped design of that type** rather than from a template written for the purpose, so it
arrives annotated with its own sources and nothing has to be kept in step with the book twice. Your name,
diameter, structure mode, separation hardware, margins and layout ratios survive; the three genuinely
type-dependent values (residual, loading margin, start-up time — zero for a cast grain, book p.489) come across
with the block. Building it found that `layout` is **not** type-agnostic: a liquid stage needs
`intertank_over_D` and a solid stage has no such key, so the block is merged rather than replaced. The proof it
is faithful is a round trip — stage 1 of the default *is* the liquid donor, so liquid → solid → liquid
reproduces the shipped design to the kilogram (410,003 kg).

*And one bug found on the way in.* `config/launch_sites.yaml` sits in a directory the GUI scans for designs, so
the new library promptly appeared in the **Open** dialog as a vehicle called "launch_sites". Libraries are now
named as such in one place.

64 new tests, 802 in total, all passing.

**What changed in v0.17 — six things found in one sitting with the GUI**

*The libraries were one wall of rows.* Propellant combinations were **132 rows in a single fold** with "O/F
as actually flown" appearing twelve times and nothing saying which pair each belonged to; the propellant
library was 75 rows with "Density" fifteen times. Each entry now gets its own fold — **Propellant
combinations → LOX/RP-1**, **Propellant library → LOX** — and every field is labelled in words
("Tank mass per kg of this propellant", not "Tank mer per").

*That flat list also caused a false alarm worth recording.* Scrolling to the first "Density" and reading
"Liquid oxygen density for tank sizing" makes it look as though tanks are always sized for LOX. **They are
not** — sizing the same vehicle with LOX, N2O4 and HTP-98 gives tank volumes implying exactly 1,140,
1,450 and 1,431 kg/m3, each the chosen oxidiser's own figure. The calculation was right; the presentation
made it look wrong, which is its own kind of bug.

*The fuel box offered LOX.* Every propellant now declares a `role`, and the two dropdowns are split by it:
11 fuels, 4 oxidisers, no overlap, nothing unreachable. A propellant with no role tag appears in both rather
than vanishing.

*Picking a combination left the propellants behind.* Choosing "LOX/LH2" now sets the stage's fuel, oxidiser
and mixture ratio too, as ordinary overrides you can still change on purpose. Before, the combination and the
fuel box could disagree and the sizing loop would resolve it and then warn — a contradiction the GUI
should never have let you build.

*Tank order was a text field.* It is a choice of two: "Fuel at the bottom, oxidiser above" or the reverse.

*And on whether that matters under a common bulkhead — it does, but less visibly than it should.* Swapping
the order leaves stage length and tank mass **identical**, which is why it looks inert. What it changes is
which tank is aft: the load model's aftmost panel becomes the fuel tank (3.12–13.32 m) instead of the
oxidiser tank (3.12–20.94 m), taking the whole mass distribution with it. A common bulkhead does not
remove that — it adds a second effect, deciding which tank owns the shared dome. The GUI now says so in
the Checks tab, citing the book's own S-II example (p.633), where moving the heavier tank forward took the
pre-launch wind running load from 140.4 to 290.5 kN/m.

*The analyses dialog was eleven loose checkboxes.* Now three named groups — how it flies, what the flight
does to it, what it is worth — with each dependency spelled out underneath.

**v0.16.1 — a syntax error that only existed on the Pythons we claim to support**

`main.py` held an f-string whose expression spanned two source lines. That is PEP 701 syntax, accepted only
from **Python 3.12**, while this project declares `requires-python = ">=3.10"`. The container the whole
725-test suite runs in is 3.13, so every test passed and the file shipped unparseable for anyone on 3.10 or
3.11 — and because the GUI's sizing path imports `main`, clicking **Size** failed on every vehicle with
`SyntaxError: unterminated string literal`. A syntax error is invisible to behavioural tests: the module
never loads, so there is nothing to test.

Fixed, and guarded. `tests/test_python_compatibility.py` reads the declared minimum out of `pyproject.toml`,
then walks every file in `src/`, `tools/` and `tests/` looking for the two PEP 701-only constructs — an
expression spanning lines inside a single-quoted f-string, and a nested string reusing the f-string's own
quote. It works in both directions: on 3.12+ the tokeniser makes those visible, which is a new interpreter
proving the code still suits an old one; on 3.10 or 3.11 the compile check catches it directly. One of its
tests feeds it the exact line that broke, because a guard nobody has seen fail is not a guard.

A sweep for other version-specific constructs (`tomllib`, `itertools.batched`, `datetime.UTC`, `except*`,
`match`, PEP 604 annotations without the future import) found nothing else, so **3.10 really is the floor**.

**What changed in v0.16 — more engines, two awkward new vehicles, and a correction to v0.15**

*R22a — seven engines, five of them because the new check cases needed them.* LE-7A and LE-5B (H-IIA),
RD-107A, RD-108A and RD-0124 (Soyuz-2), plus the two most conspicuous modern absences, **RD-191** and
**BE-4**. The BE-4 row is deliberately full of nulls: its page gives no vacuum thrust, no expansion ratio and
no mixture ratio, and quotes a single Isp without an altitude, so those stay unknown rather than being
invented. Adding the LE-5B also meant adding the **expander-bleed** cycle, which the book does not cover; its
pressure band is set from its own flown examples rather than assumed, as the electric-pump band already was.

**This overturned v0.15's R20 verdict, which is worth saying plainly.** At ten engines the engine-mass
relation looked merely scattered — mean −7 %, no structure — and the conclusion was "do not refit".
At sixteen it is clearly **biased low**: 14 of 16 come out light, median −24 %. A small sample hid a
systematic offset. There is now an opt-in `mer_calibrated` method applying a factor of 1.22 measured in log
space, and the honest caveat is built into it: the factor helps the typical engine (median −24 % →
−7 %) and makes the two exceptional ones — Merlin 1D, RD-253 — **worse**, because no single scale
factor fixes a distribution with one-sided outliers. The book's coefficients remain the default.

*R23 — two check cases chosen to break things.* **H-IIA 202**: composite solid strap-ons on a hydrolox
core, and its SRB-A is one of the 34 stages the R18 relations are fitted to, so the comparison is unusually
direct. It lands **+6.0 %** on lift-off mass as declared and **−0.2 %** with an optimised Δv split —
the second-best case in the set. **Soyuz-2.1b**: four strap-ons that are *tapered cylinders*, and this tool
gives a booster one diameter. It was added precisely because it does not fit. The sizing holds up
(−10.5 % optimised) and the geometry does not: the modelled booster is 17.3 m against a real 19.6 m and
the span is 18 % narrow. Both facts are asserted in tests, so if anyone later teaches the tool about tapered
boosters, the test tells them it mattered.

*And the R18 relations now reach strap-ons.* Most of the 34 stages they were fitted to ARE strap-on
boosters — the Shuttle SRB, Ariane's EAP, the H-IIA's own SRB-A — but v0.15 only applied them to serial
solid stages, so four vehicles never got the comparison. Across all seven solid-bearing check cases the
median lift-off-mass error falls from **28.3 % to 6.6 %**: Delta II 7920 +28.3 % → −0.7 %, H-IIA
+6.0 % → −5.5 %, Ariane 5 +9.7 % → +6.6 %. One gets **worse** — Atlas V 551, −8.2 % →
−17.9 %, because it was already light and a lighter relation makes it lighter still — and that is in the
validation report rather than averaged away.

*A recurring failure finally made actionable.* Four vehicles in a row (Ariane 5's ESC-A, Delta IV Heavy's
DCSS, and now both new cases) hit the same wall: a tank whose volume is smaller than its own end caps. The
error now computes and names **the largest diameter that would work**, and says that a stage whose tanks do
not fill its envelope is normal rather than a mistake.

*All of it is in the GUI.* The seven engines and the calibrated engine method appear in their dropdowns, both
vehicles are in Open → Check cases, and a new **Model checks** tab shows the three things v0.15 and v0.16
measured — engine-out and cluster reliability for the sized vehicle, the engine-mass relation against all
16 real engines with the outliers highlighted, and the solid-stage relations against all 34 flown stages.
Verified by driving a real browser, not by reading the code.

**What changed in v0.15 — the model gets measured against published data instead of trusted**

Three roadmap items from Phase F, all of them about accuracy rather than capability.

*R18 — solid stages stop being 50-120 % too heavy.* The diagnosis first: the book's COMPOSITE casing
coefficient, k = 0.1154, is a **motor-level** figure as large as the measured **stage-level** inert fraction
of real composite-cased stages (0.111). Everything the tool adds on top — skirts, avionics, margin —
therefore overshoots, and because sizing is a fixed point a 39 % heavy casing made Vega **122 %** heavy. The
fix is two published sources, not a number invented here: Zandbergen (TU Delft, 2026) regresses 17 steel and
17 composite flight stages, and Kibbey (NASA MSFC, NTRS 20190027424) gives a size-dependent form. Both are
selectable as casing methods, both carry their own error statistics, and because they predict a WHOLE STAGE
the component build-up is switched off rather than stacked on top. **Pegasus XL goes from +59.6 % to
−4.1 %, Epsilon from +58.4 % to −10.4 %.** Every published coefficient was re-fitted from the source's
own tabulated stages before being used — the steel one reproduces exactly at 0.1707 — which is also how
an ambiguously printed constant was resolved as tonnes rather than kilograms. NASA's own technology
parameters turn out to under-predict those 34 flown stages by 22-58 %, and that is recorded, not smoothed.

Vega still lands +11.8 %, and the remaining error is a **different** relation: the book's two-value avionics
step (75 kg under a 1 t payload, 350 kg over) puts 280 kg on Vega's AVUM, whose entire real dry mass is
147 kg. That is now the top item on the roadmap, and it is exactly the subsystem NASA's own small-launch-
vehicle study names as needing refinement.

*R24 — `n_engines` finally means something.* The book's Sec. 15.2.6 k-of-n binomial, verified against both
of its worked examples (3-of-5 at 95 % → 99.88 %, 7-of-9 → 99.164 %), with the engine-out thrust-to-weight
beside it. Redundancy is only **credited** where the stage can still fly with an engine shut down. Two
additions to what the book prints: its Table 15.4 reports two engines as 100 % reliable on records of 0/207
and 0/65, so the exact Clopper-Pearson lower bound is given beside the point estimate (98.6 % and 95.5 %);
and the default design's standing claim that six engines give one-engine-out margin is now **tested** — T/W
falls from 1.30 to 1.08, so it holds, but only just.

*R20 — a measurement that changed nothing, which is the point.* Table 8.9's engine-mass relation was run
against every database engine publishing a dry mass. Mean error −7 %, **standard deviation 45 %**, and the
trend with engine size (+15 %) is smaller than that scatter — so refitting on this sample would fit noise,
and the book's coefficients are kept. What did change: the uncertainty study's 1-sigma on engine mass was an
assumed 0.15 and is now the measured **0.45**, tagged `t: reference`. The two outliers are the ones the book
itself explains — the RS-68 is 55 % heavier than the relation because of its ablative nozzle, the Merlin 1D
104 % lighter because it has the highest thrust-to-weight ever flown.

**What changed in v0.14 — 3MF everywhere, and STEP for anyone who installs a kernel**

*3MF, with no new dependency.* `--cad` now writes **`cad/vehicle.3mf`** beside the DXF, STL and OBJ. It carries
the same triangles as the STL but fixes the two things STL cannot do: it **records the unit** its coordinates
are in (`unit="meter"`, so nobody has to guess whether a 70 m vehicle is 70 mm) and it **keeps one named object
per part**, where STL fuses airframe, nozzles and strap-ons into one anonymous shell. It is an OPC zip of XML
written straight from the 3MF Core Specification, so it compresses to about an eighth of the STL's size, and it
is read back in the tests by a parser written from that specification — structure, namespaces, zero-based
indices, outward winding, and the unit scaling for all six permitted units. The two OPC strings it needs were
confirmed against a package this project itself produces rather than quoted from memory. **Prefer it to STL.**

*Exact solids through an optional geometry kernel.* `pip install cadquery` and `--cad` additionally writes
**`cad/vehicle.step`** — exact B-rep cylinders and cones, one named and coloured part per mesh part, so the
CAD tree reads like the DXF layers — plus BREP and glTF on request (`--cad-formats`). Without the kernel
nothing changes and nothing fails: the faceted files are still written, and the GUI greys out the solid
buttons with the reason in the tooltip. The kernel is asked only for what it alone can do, and deliberately
does *not* re-export STL or 3MF: these meridians are piecewise linear, so `--cad-facets` already controls the
only curvature there is, and two routes writing one file name means one is unreachable.

**How much to trust the kernel route, stated plainly.** CadQuery could not be installed in the environment this
was written in — no network at all — so **no call in that module has ever reached a real OpenCASCADE
kernel.** Rather than hand that uncertainty over, the module checks itself on your machine: every solid's volume
as the kernel reports it is compared against a closed-form frustum sum that involves no kernel, and against the
bounding box the profile implies, and **a solid that disagrees by more than one part in a million is never
written** — the export raises instead. A wrong API convention therefore fails loudly rather than producing a
plausible STEP file with the wrong geometry in it. `--verify-kernel` prints that check part by part. The tests
exercise it against a stub that computes each volume by Pappus' theorem from the points and axis actually
passed, including a deliberately wrong axis to prove the guard rejects it — but a stub is not OpenCASCADE,
and that distinction is recorded at the top of `tests/test_cad_kernel.py` rather than glossed over.

*Liquid strap-on boosters, exercised for the first time.* `boosters.type: liquid` had been accepted by the
schema and handled in the mass budget since v0.5, but no shipped design used it and **no test covered it**.
`validation/delta4_heavy.yaml` is now the case that does: Delta IV Heavy, three identical Common Booster
Cores. It converges to within **0.4 % of the published 733 t** lift-off mass — the best of the four
strap-on cases — though 62 % of that mass is typed in from published booster figures, and the core's own
dry mass still comes out 24 % light. Exercising it turned up two defects: a liquid booster was being given a
solid motor's **cast-grain bore**, so the schematic drew a hatched propellant grain down the middle of a
liquid hydrogen tank and the DXF put it on the grain layer; and `ascent_time_override_s` — the field the
sizing loop *names* when a low-thrust upper stage puts the loss regression out of range, which a hydrolox
upper stage reliably does — was missing from the default design, so it had no row in the GUI and a GUI
user had no way to set what the error told them to set. Both fixed, with six tests on the liquid path.

Also: the report's Drawings section now states what the CAD export gives and what it costs — the 0.161 %
volume deficit of a 64-facet mesh, and whether a kernel was available — so nobody mistakes a mesh for a
solid model.

**What changed in v0.13 — the GUI becomes the way to use the tool**

Everything built since v0.4 was reachable only from the command line. A person sizing a vehicle should not be
hand-typing a nine-hundred-line YAML file, so the GUI now carries the whole tool.

*Configurations have names, and you can save them.* **Open…** lists every design grouped — your own saved work,
the starting points, the examples, and the **check cases**, the seventeen real vehicles the tool is validated
against. **Save** writes a complete annotated design file into `designs/`, with your changed values re-tagged
`t: user` and sourced to you rather than inheriting the book's provenance; it is reloaded to prove it parses
before you are told it saved, and it runs from the command line like any other design.

*The inputs are organised the way you would ask about them.* Section → topic → field, with **the specification
shown and the assumptions folded away**. The fold is not by provenance tag: on a check case every published
figure is tagged `reference`, so grouping by "user" would have hidden Electron's payload mass and shown nothing
but empty overrides. What shows is what you changed, what has a value from a person or a source, and any empty
dropdown — an empty dropdown being an invitation rather than clutter.

*Dropdowns instead of typing.* Around thirty fields now offer their valid values: propellants, propellant
combinations, tank materials, real engines and motors, tank mass methods, Isp modes, orbit types, loss and drag
models. The lists are read live from the libraries, so adding a propellant or an engine to the YAML makes it
appear in the GUI with no code change — and the tests check every offered value against the validator that
enforces it, because a dropdown offering something the model rejects is worse than a text box.

*Human labels.* "Vacuum specific impulse", not `stages.0.engine.isp_vac_s`. Click a label for its description,
its source and the path, which is what you need to set it from the command line.

*All eleven analyses, in the GUI.* Pick them from **Analyses…**; anything a study depends on comes with it. Each
gets its own tab with its chart and headline numbers, the summary gains the **what governs this design** table,
and the report, workbook and CAD exports (DXF, STL, OBJ, 3MF, plus STEP with an optional kernel) download from there.

**It also found a real bug.** Every per-stage edit in the GUI had been failing with a bare `KeyError`: the input
register spells stage paths `stages[0].engine.isp_vac_s`, the browser sent back exactly what the server gave it,
and `deep_set` only ever walked the dotted form. Both spellings are now accepted, with the test that catches it.
Changing a stage value in the GUI has never worked until now.

**What changed in v0.12 — the loads diagram reads like the book's, the wind is yours, and the report has a front page**

*The vehicle is drawn beside its loads.* The loads chart is now vertical, with the inboard profile upright on
the left and axial force, shear and bending moment sharing its axis — the way Fig. 9.26 presents the Saturn V's
own distributions. Stage joints and the fairing base rule across all three panels, and the station that sizes
the structure is circled and named. It is the same silhouette the general arrangement draws, not a second
outline that could disagree with it.

*One axial coordinate, tool-wide.* `z`, upward from the stage-1 nozzle exit plane, is now what every chart and
table is plotted and sorted against — drawings, mass ledger, CM travel, CAD export, loads diagram, loads
tables and the workbook. The loads chart previously used station-from-the-nose, which put the one diagram you
most want to read against the vehicle on the opposite convention to the vehicle. The book's station is still
carried beside `z` wherever the book's own tables use it.

*Winds aloft from the launch site.* §9.1.6.3 step 4 says to use the launch site's winds-aloft profile; the tool
hard-coded the book's Atlantic Missile Range curve, so every vehicle was designed for Cape Canaveral. A design
can now name a CSV or Excel profile, a glob, or a list. Three things the implementation refuses to fudge:
**steady wind and gust envelope are different inputs** (an envelope already contains the gust; a sounding does
not, so a `steady` profile without an explicit gust increment is refused rather than defaulted);
**one profile is not a design wind**, so several are flown as an ensemble and the case kept is the one that
*bends the vehicle hardest*, not the one with the fastest wind; and every kept case records which profile
produced it, with the report listing what it was chosen from.
Wiring it up also found the feature inert: the profile reached the recorded wind speed but not the angle of
attack or the instant selection, so a calm profile and a 76 m/s one produced identical bending moments. Fixed,
with the test that catches it.
Note the limit: there is still **no wind in the trajectory** — the gust is imposed at the altitude the
trajectory reached without it.

*The report has a front page.* Twenty sections and no summary. Now it opens with the mission, the vehicle, a
**what governs this design** table — governing bending moment and where, thickest shell and what drove it,
max-q, peak acceleration, worst control margin, payload load factors — and the warnings, each row linked to the
section that derives it. The two acceleration figures that used to appear to contradict each other on the same
page (5.62 g flown against a 6.22 g burnout warning) are now reconciled in the row that quotes them.

**What changed in v0.11 — more propellants, real mixture ratios, and a leaner report**

*Propellants and mixture ratios.* The propellant library goes from 7 entries to 15 — the book's remaining
Table 4.5/4.6 entries (propane, MMH, hydrazine, ethanol, methanol, nitromethane) plus two grades of high-test
peroxide, **HTP-90 and HTP-98**. On top of that a new **propellant-combination library** of 12 oxidiser/fuel
pairs: name one from a stage and it supplies the fuel, the oxidiser and the mixture ratio.
Each combination carries **two mixture ratios**, because they are not the same number: the one that maximises
Isp, and the one engines actually fly. For LOX/LH2 that is 4.02 against the J-2's 5.50 — hydrogen engines run
fuel-rich to keep turbine temperatures down — and a library that reported only the optimum would quietly
mis-size every hydrogen stage. The flown ratio is what a stage gets, and each one names the engine it came from.
The theoretical Isp, c*, chamber temperature and mixture density come too, and the report shows them beside the
design's own numbers — but the reference Isp is **never** filled into a stage, because Table 4.10's condition
(1,000 psia expanded to sea level) is one a vacuum nozzle legitimately beats.
Bulk density is computed rather than stored, and **that check found a book error independently**: recomputing
each Table 4.10 row's printed specific gravity from its component densities reproduces six of seven inside 2 %,
and the Aerozine-50 row only closes with a fuel density of ~903 kg/m³ — not the 1,450 kg/m³ Table 4.6 prints,
which duplicates the N2O4 row directly above it. Two of the book's own tables contradict each other, and the
arithmetic says which one is right.

*Real engines.* The engine database grows from 13 rows to 33, most of them now the book's own tables — the
eighteen-engine summary of Table 4.14, the F-1, the J-2 and the RS-68 — plus three peroxide engines from
published papers. Naming an engine now also supplies its **propellants and mixture ratio**, so `from_database:
RD-180` gives you LOX/RP-1 at O/F 2.72 rather than leaving a generic default in place beside a named engine.
Two things this surfaced and did not paper over: the book's Table 4.14 prints the RD-170 with a *vacuum* thrust
below its sea-level thrust, which is impossible, so that field is left empty rather than carried over; and four
real staged-combustion engines sit below the 150 bar floor the cycle band assumed, so the band was recalibrated
from the data — a band that flags its own flown engines is miscalibrated.
Worked example: `examples/example_htp_kerolox.yaml`, a two-stage HTP-98/RP-1 vehicle using both libraries.

*Report.* The 3-D isometric view is out of the report — it showed the same outer mould line the dimensioned
general arrangement already shows, and it still ships beside the DXF and meshes where it serves as a check on
that export. The component-mass-versus-axial-position scatter is out too: forty dots on a log axis said less
than the mass ledger table says exactly. Its other half, the centre-of-mass travel through the flight events,
is kept and promoted to a figure of its own — the CM moves nearly the length of the vehicle, which is what the
static margin has to be read against. The payload-versus-inclination chart now sweeps below the launch-site
latitude and **shades the band a direct ascent cannot reach**, which both moves the design point off the left
edge and says something the old chart did not.

**What changed in v0.10 — the layout into CAD, and vehicles in without typing YAML**

*CAD export (R15, `--cad`).* Three files and a picture. *(Superseded in v0.14: 3MF was added, and STEP is
available with an optional kernel — see the v0.14 notes above.)* A **layered DXF R12 inboard profile** — outer mould
line, stations, tank walls and domes, solid grain and bore, nozzles, strap-ons, payload envelope and overall
dimensions, each on its own layer — written straight from the published group-code format, so no dependency is
added. The **outer mould line revolved into closed triangle meshes** and written as **STL and OBJ**: one part
for the airframe, one per nozzle, one per strap-on, each individually watertight. And an **isometric view**
rendered from those very meshes, so the picture in the report is a check on the export rather than a separate
drawing.
**No STEP file.** A STEP B-rep must be generated *and verified* with a geometry kernel, and none can be
installed here; shipping an unverified solid model would be worse than shipping none. What is delivered is
verified instead: each mesh's volume is checked against the exact closed form for a faceted solid of
revolution, every edge must be shared by exactly two oppositely-wound triangles (with a deliberately holed mesh
in the tests to prove the check can fail), and the DXF is parsed back by a group-code reader written from the
format spec rather than from the writer. What none of that shows is that the files open correctly in a CAD
application — **that check has not been run.**

*Vehicle importer (R16, `import-vehicles`).* A declared CSV or JSON sheet of published figures becomes a full
annotated design YAML: every imported leaf tagged `t: reference` with its own source string, everything else
left at the base design's value and **listed in an import report** that says how many of each there are. The
shipped example imports Electron and Falcon 9 and sizes them to within 17 % and 8 % of the hand-written
validation cases for the same vehicles — the residual being the fields no public source carries.
Two things this row promised that turned out not to exist. **launchercalculator.com publishes no dataset**: it
is a calculator you type parameters into, with no download, endpoint or API, so there was nothing to import.
And **Wikipedia infoboxes cannot be imported blind** — a single cell routinely describes several vehicles
("FT: 549,000 kg; v1.1: 506,000 kg"), so the infobox path refuses any field that does not reduce to one figure
and lists it as ambiguous for a person to settle. Taking the first number would have fabricated a
specification for a variant nobody chose.
The importer also warns about its own likeliest failure: **absolute mass assumptions do not scale.** Cloning a
stage template from the 10 t-class default base carries 100 kg of equipment, 60 kg of separation hardware and
25 kg per engine of feed system into every stage — noise on a Falcon 9, and roughly double the inert mass of an
Electron. Whenever the payload masses differ by more than 3×, the report names every such leaf.

**What changed in v0.9 — cost, payload environment, and running the tool over many vehicles**

*Cost (R11, `--cost`).* The five TRANSCOST development CERs Chapter 17 prints on its figures, with the
f-factors, Table 17.3's work-year values and Eq. 17.1's inflation. **All five rows of the book's own Ariane 5
verification table are re-run in the tests**: both engine CERs reproduce exactly, and the three that do not are
each pinned — the SRB's printed CER value is 10 % below what its own formula gives while the table's *final*
column matches the formula exactly, so the printed value looks like a typo; the third-stage row is internally
consistent but 50 % from the vehicle CER; the vehicle-and-shroud row closes on neither. End to end the
programme comes out 6.1 % above what ESA actually spent, inside TRANSCOST's stated ±20 %.
**Cost per flight is not a CER** and is not presented as one: the production submodel, learning curve and
operations model are all deferred to the book's reference, so per-flight cost is §17.5.3's rule of thumb,
reported with the factor-of-60 range that rule supports and beside real prices from the book's Table 17.5.

*Payload environment (R13, `--payload-env`).* The quasi-static load factor table a payload customer is handed,
by flight event, in the format of the two real planners' guides the book prints — both shown beside it. The
default design comes out at 7.2 g axial and 2.0 g lateral, inside the book's 4–8 g and 1.5–3 g expectation.
The **steady** half is computed; the **dynamic** half is not, and says so on every row — it needs a
coupled-loads analysis. No acoustic or shock specification is produced, because Chapter 11 gives no prediction
method for any of them.

*Trade studies and comparison (R17 and R14).* `trade` runs a sweep declared in YAML — grid or one-at-a-time
over any dotted parameter path — and `compare` sizes several designs side by side; both write a CSV, a chart
and a page. **Failed cases stay in the table**: a 3.6 m stage 1 cannot fit its engines, and that row appears
with its ENGFIT error rather than disappearing. The generated page carries the caveat that matters: the
diameter sweep moves GLOM by 0.4 % while the Monte-Carlo puts the model's own uncertainty at tens of per cent,
so a trade with a spread that small is telling you about the model, not the vehicles.

**What changed in v0.8 — Phase C complete ([`docs/ROADMAP.md`](ROADMAP.md) R6, R7, R9)**

*Static stability and control authority (R9).* The three rules of thumb of §12.3.6, evaluated at the worst
instant of the ascent: controllability ratio M_δ/M_A ≥ 2, time to double > 0.5 s (Eq. 12.4), steady-state gimbal
deflection ≤ 2°, plus the Table 12.4 deflection budget. The book's Saturn V example — 3.31 s at max-q — is
reproduced from its own printed inertia and moment, and **two slips in it are pinned by tests**: the finless
moment is printed as "37 kNm" where 37 MN·m is needed for its own stated 3.15 s, and the text reads that case as
giving "slightly more time" when its numbers give 160 ms *less* — the direction that matches §9.2.7's argument
for why the fins were there. Table 12.4's printed RSS totals are also ~13 % above the root-sum-square of its own
rows, while its arithmetic totals match exactly. **Slosh is withdrawn rather than delivered**: Chapter 12
declines slosh analysis outright (p.778) and gives no bending or POGO equation either.

*Solid-motor internal ballistics (R6, `--ballistics`).* Burning area from grain regression, equilibrium chamber
pressure P_c = [ρ a c* A_b/A_t]^(1/(1−n)) assembled from Eqs. 4:32, 4:33 and Table 4.4, and the thrust-time
curve. The burning-rate coefficient is **calibrated to each motor's own design pressure**, not invented — the
book gives none for any propellant. The finding: a plain cylindrical bore is progressive, so thrust climbs **5×**
through the burn and chamber pressure reaches 11.1 MPa against a 6.0 MPa design. That is the book's own
prediction, and it says the constant-thrust sizing needs a shaped grain Fig. 4.12 draws but never dimensions.

**Phase C: stress and buckling (R7)**

*Shell stress, buckling and required thickness (`--structure`, implies `--loads`).* Chapter 10 in full: axial
and bending stress, hoop from ullage pressure and the head of accelerating liquid, buckling allowables both
pressurised and unpressurised, the NASA SP-8019 frustum criterion for tapering skirts, and the wall thickness
each shell needs — the larger of axial strength, hoop strength, elastic stability and minimum gauge, over every
load case. **All five of Chapter 10's worked examples reproduce**, including the ones that pin the buckling
coefficients (K₀ = 0.05249 and 0.08630, σ_c = 10.63 and 9.16 MPa, 5.4× and 3.7× the unpressurised values).

* **Buckling sizes almost everything**, as it must for a monocoque launch vehicle — the book's own example tanks
  buckle at 288–364 psi, "hardly anything" (p.637).
* **The pad case sizes the tanks**, because the book runs ground loads with *no* tank pressure by rule (p.650),
  so on the pad the tanks get neither the axial relief nor the stabilisation that pressure gives them in flight.
* **The mass comparison is the point.** Sized as monocoque the shells come to 11,946 kg against the 5,858 kg the
  Chapter 8 relationships carry for the same hardware — a factor of **2.04**. Neither is wrong: the
  relationships are fitted to real vehicles, real vehicles are not monocoque, and the gap is what rings,
  stringers, waffle and isogrid buy back. That is the honest measure of the tool's largest known error, and it
  is **not** a correction to apply.
* **Eq. 10.43's sign.** Its bracket goes negative when pressure more than cancels the compression; the book
  reads that correctly in its text but prints the magnitude (0.41 mm) just above. Using the magnitude would make
  *more* pressure demand a *thicker* wall, inverting the chapter's own argument, so the requirement is floored
  at zero and a test pins the direction.
* **What is not sized**, and the roadmap row that promised it has been corrected: the stiffened constructions of
  §10.3.3 (honeycomb, stringers, isogrid) are named by the book without allowables or mass-per-area laws, so
  they are not sized; nothing is fed back into the sizing loop, so the vehicle in the report is still the
  MER-sized one; and the fairing is skipped rather than run through an aluminium criterion it does not obey.

**What changed in v0.7 — the rest of Phase B, and the start of Phase C ([`docs/ROADMAP.md`](ROADMAP.md))**

*Pitch-programme optimisation (R5b, `--optimise-ascent`).* The book poses this in §6.7 and declines to solve it
— *"the mathematics behind the theory of optimization is relatively complicated and will not be presented
here"* (p.383) — but §6.10 states the trade exactly, so the objective and constraints are its and the pattern
search is the tool's own. Three guidance parameters are searched with the pitch kick re-solved by shooting
inside every evaluation, so every candidate reaches the target altitude exactly. On the default design the
optimised profile is worth **+93 m/s and +430 kg of payload (+4.1 %)**, priced by flying the vehicle heavier
until burnout speed just meets the orbit. The optimum sits **on the qα limit, not at a stationary point** —
steering over earlier always pays until the air loads stop it — so the limits decide the answer and the report
says so: the defaults are what the book's own generic vehicle reached in Fig. 9.36, not certified limits.
One finding worth stating: with the kick re-solved, the vertical rise time barely matters (5 s and 20 s differ
by under 5 m/s); the hand-over altitude is the parameter that does the work.

*Normal force and centre of pressure (R5c).* Built up panel by panel over the outer mold line, with static
margin and the pitching-moment slope through the whole atmospheric ascent. Checked against the book's own
Saturn V force list (Fig. 9.65): CP at 55.95 m, 2.13 calibers unstable, and removing the fins' 126 kN moves it
0.41 calibers forward — which is §9.2.7's claim that the fins added stability, as a number. The default design
runs at −5.5 calibers, unstable throughout, which is the normal state for a finless launch vehicle (p.357).
The report states what the build-up omits — viscous crossflow on the cylinders, which biases the CP forward and
makes the margin pessimistic — and warns that static margin is unsafe to read when reverse tapers drive the
total slope through zero, where the moment slope is the measure that stays correct.

*Ground and flight loads (R8, `--loads`).*
* axial force, shear and bending moment marched station by station
  along the vehicle, for five conditions — clamped to the pad in a ground wind with tanks full and
  unpressurised, lift-off in that same wind, and in flight at max-q, max-qα and maximum axial acceleration,
  each at the angle of attack a horizontal gust forces on it, trimmed with engine gimbal side force and
  relieved by d'Alembert inertia at every mass.
* **which case governs is computed, not assumed.** The book says outright that max-q versus max-qα cannot be
  decided before a trajectory exists (p.572); on the default design max-qα arrives 6 s earlier and bends the
  vehicle 21 % harder, while bending overall is governed by the ground wind and axial load by max-q — not by
  the 6.2 g at burnout, because by then the stage is empty and there is little mass left to compress it.
* **every case closes against an identity.** On the ground the axial curve must equal the vehicle's weight and
  the shear the total wind force; in flight the axial curve must close on the thrust, the shear on zero, and the
  bending moment must be zero at *both* ends because the vehicle is a free-free beam (p.606). All hold to
  floating-point noise, and the report prints the residuals.
* **verified against the book's own Saturn V worked examples**, Tables 9.5, 9.8 and 9.11, from its published
  inputs: every ground-wind side area, wind speed, dynamic pressure and drag force within 1 %, the shear column
  within 0.3 %, the gimbal trim within 0.4 %, and all eighteen rows of the max-q axial running total within
  3 kN of 40,018. Three internal inconsistencies in the book's Chapter 9 were found in the process — a skirt
  area-centroid formula that contradicts the book's own cone entry, two moment rows that exceed their own
  geometric bound, and an axial load factor computed from a drag 2.5× smaller than the one its own table sums
  to. All three are documented with the arithmetic in [`docs/VALIDATION_REPORT.md`](VALIDATION_REPORT.md) §6
  and asserted in `tests/test_loads.py`.
* **the report tells the truth about itself.** The limitations banner no longer claims "no structural analysis"
  when the load cases were computed; it says what is now known and what is still missing (shell stresses,
  buckling, pressurisation relief, margins of safety — and that structural masses were *not* re-sized to carry
  these loads).

**What changed in v0.6 — Phase B, the trajectory ([`docs/ROADMAP.md`](ROADMAP.md) R5)**
* **3-DoF ascent trajectory** (`--trajectory`): the book's Table 6.1 equations of motion integrated with RK4
  through an atmosphere, with Cd a function of Mach number. Guidance is the book's gravity turn (Sec. 6.4.7)
  with the pitch kick found by shooting (Fig. 6.18) — 0.31° for the default design — handing over above the
  atmosphere to a commanded flight path angle.
* **The ascent losses are now computed, not fitted.** Gravity, drag, propulsion (back pressure) and steering come
  out of the Eq. 6:58 integrals, and the four plus the burnout speed reconstruct the vacuum ideal Δv to better
  than 1e-6 m/s. On the default design the integration gives 2,204 m/s against the regression's 2,145 m/s — a
  2.8 % difference, inside the regression's own ±260 m/s RMS error. Titan II comes out at gravity 1,360 m/s and
  drag 49 m/s, both inside the book's Table 3.4 ranges, with max-q at 79 s (the book says 50–90 s).
* **Drag**: the book's Titan II curve from Fig. 6.13, printed there as analytic equations, so it is exact rather
  than digitised. Plus a constant, a user table, and **a reader for ZOOM lift/drag aerodynamic files** (ZOOM User
  Manual v1602 §19) so real aero data can be flown here — with a detector that flags the manual's own example
  file, which is a format demonstration rather than data.
* **Atmosphere**: the book's exponential model (Eqs. 6:50/6:53), with US Standard Atmosphere 1976 supplying the
  temperature and speed of sound the book's Cd(M) needs and the exponential model does not have.

**What changed in v0.5** (roadmap items R1–R4, [`docs/ROADMAP.md`](ROADMAP.md))
* **Performance curves** (`--performance`): what the *built* vehicle lifts to other orbits — payload against
  altitude and inclination, plus GTO (book Sec. 3.8). Freezes the hardware and bisects the payload, so a full
  envelope costs no re-sizing; the design point falls on the curve by construction and is printed as a self-check.
* **Uncertainty** (`--uncertainty`): every MER gets a documented 1-sigma scatter and the sizing loop is resampled.
  The default design comes out **372 / 415 / 474 t** at the 5 / 50 / 95 percentiles, with residual propellant and
  delivered Isp the biggest contributors — an interval instead of false precision.
* **Analytical staging optimum** (`--staging`): the book's Lagrange closed form (Eqs. 5:32–5:33) beside the
  numerical search, with the gap between them pricing its fixed-sigma assumption. Eq. 5:40 reproduces the book's
  Fig. 5.11 exactly, which is the honest answer to "is another stage worth it".
* **Real engines** (`config/engine_database.yaml`): 13 sourced engines and motors a design can reference with
  `from_database`. A row is a default, never an override — a value you wrote always wins, and the disagreement is
  reported rather than silently flown.
* Drawings in the report are page-shaped: **one continuous vehicle per printed page**, drawn at the largest
  scale that fits the page height, with the dimensions on the left and each stage's data beside the stage it
  describes. The report also writes symbols as real characters.

**What changed in v0.4**
* **The published errata applied** (1st ed., rev. 2023-01-12): the Pegasus drag loss corrected to the measured
  322 m/s, the small-payload PAF rule (`0.15 m_PL`), two further book loss models (Eq. 3:32 and Eqs. 3:33–3:34)
  alongside the existing regression, and new plausibility checks. Item-by-item table with the measured effect of
  each change: [`docs/ERRATA_COMPLIANCE.md`](ERRATA_COMPLIANCE.md).
* **A single-file design report** (`design_report.html`, `--pdf` to convert): every input with its units,
  description, source and provenance, the Δv budget line by line, the full mass statement and ledger, the
  geometry, the drawings, the checks and the complete method register — self-contained, no network, with an A4
  print stylesheet.
* **A local GUI** (`python tools/gui.py`): browse and edit all ~230 annotated inputs, size, compare against a
  frozen baseline, read the drawings and the report, download the workbook, the report and the overrides as
  reproducible YAML. Standard library only; nothing leaves the machine.
* **A roadmap and a chapter-by-chapter comparison with the book**:
  [`docs/ROADMAP.md`](ROADMAP.md).

**What changed in v0.3**
* **Solid rocket motors** as serial stages: book Sec. 8.5 (Eqs. 8:17–8:24) — casing MER, 1.12 × grain volume,
  hemispherical domes, centre-perforated grain, implied burn-rate check, no start-up/residual propellant.
* **Strap-on boosters** burning in parallel ("stage 0"): book Sec. 5.11 (Eqs. 5:65–5:66, Fig. 5.21), including
  a second air-lit group (Delta II style), jettison events, and off-axis mass properties.
* **Engine and nozzle dimensioning** from the book's own relations (Eqs. 8:28–8:33) instead of assumed sizes.
* **Redrawn schematics**: proper dimension lines (witness lines, arrowheads, compact labels), a separate data
  panel so numbers never cover the vehicle, solid-motor grain and strap-on boosters drawn to scale.
* **Validation against 12 real vehicles**, weighted toward small launchers (Electron, Pegasus XL, Vega,
  Epsilon, Firefly Alpha) plus Falcon 9, Titan II, Saturn V, Zhuque-2, Delta II 7920, Atlas V 551, Ariane 5 ECA
  — see [`docs/VALIDATION_REPORT.md`](VALIDATION_REPORT.md).
* Fairings wider than the upper stage (conical adapter), tanks narrower than their stage, air-launch release
  credit, and a workbook formula verifier that recalculates the file in LibreOffice.
