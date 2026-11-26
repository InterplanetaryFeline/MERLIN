# MERLIN (v1.4.0)

**Mass Estimation Relationships for Launch vehicle Initial sizing**, by Szymon Błażejewicz.

## Download for Windows

**[⬇ Download the latest MERLIN for Windows](../../releases/latest)**: under *Assets*, take
`MERLIN-<version>-windows.zip`, unzip it, and run `MERLIN/MERLIN.exe`. No Python and no browser are needed; the full
GUI opens in its own window. Put the folder somewhere you can write to, such as Documents, because your saved
designs and outputs go inside it. It needs Microsoft Edge WebView2, which is part of Windows 11.
The app is not signed, so Windows may warn before its first start.

## About

Conceptual-design sizing for **expendable multistage launch vehicles with liquid stages, solid motor stages and
strap-on boosters**. You state a mission, and it closes the mass budget and then analyses the resulting vehicle.
Every input carries its units, source and provenance, and every method cites where it comes from. The primary
reference is Edberg & Costa, *Design of Rockets and Space Launch Vehicles*, 2nd ed. (AIAA, 2022).

> **This is a preliminary design tool, not a design authority.** A closed mass budget shows that the stated
> assumptions are self-consistent, not that a vehicle can fly the mission. Its errors are measured and published
> below.

## Install and run from source

You need Python 3.10 or later. From the project folder:

```bash
python -m venv .venv
```

Activate it with `.venv\Scripts\activate` on Windows or `source .venv/bin/activate` on Linux and macOS, then:

```bash
pip install -r requirements.txt
pip install -e .
python tools/gui.py
```

The GUI opens on http://127.0.0.1:8000 and is the main way to use the tool. It runs locally and sends nothing
anywhere. The same work is available from the command line:

```bash
python -m launch_vehicle.main run --design config/default_design.yaml --out outputs --all-studies
python -m launch_vehicle.main optimize --design config/default_design.yaml
python -m launch_vehicle.main architecture --help
python -m launch_vehicle.main family --help
```

`examples/` has starting points, including `example_solid_smallsat.yaml` (three-stage all-solid) and
`example_boosters.yaml` (kerolox core with four solid strap-ons).

## What it does

* **Sizing:** serial liquid and solid stages and strap-on boosters, with the number of stages and boosters as
  inputs; tank and motor-case geometry; engine and nozzle dimensions; mass ledger, centre of mass and moments of
  inertia at every flight event.
* **Mission:** LEO, SSO, GTO and GEO delta-v budgets, 30 launch sites, and ascent losses from the book's methods
  or the vehicle's own simulated flight.
* **Libraries:** real engines and motors, propellants, propellant combinations and tank materials, and your own
  entries beside them.
* **Trades:** optimum staging by lift-off mass, cost or payload; payload curves for other orbits; trade studies
  and side-by-side comparison; from the command line, launcher families, pinning a vehicle's stages to change its
  strap-on count, or re-sizing the core for a fixed booster set.
* **Analysis:** 3-DoF ascent to orbit (linear tangent steering, engine cutoff, coast and restart, solids, air launch, on a
  turning Earth) and its optimisation, with the drag coefficient built up from the vehicle's own geometry; ground and flight loads with your own winds-aloft
  profile; shell stress and buckling; aerodynamics and stability; solid internal ballistics; payload environments;
  development, production and per-flight cost in work-years and dollars; reliability; Monte-Carlo uncertainty.
* **Outputs:** a self-contained design report, an Excel workbook with live cross-check formulas, dimensioned
  drawings, DXF, STL, OBJ and 3MF exports, and STEP through an optional geometry kernel.

## What it does not do

* **Nothing is fed back.** The structure is not re-sized to carry the loads it is shown to need, the vehicle is
  not re-sized around the better ascent the optimiser finds, and no motor casing is re-sized for the chamber
  pressure its own grain reaches.
* **Reusable vehicles** cannot be represented, and there is no reuse economics.
* **The lightest vehicle may not be one that flies well.** With the book's loss methods the search for the best stage split
  does not see the ascent. The Trajectory tab says whether the orbit is reached, and an optional loss method sizes the vehicle
  with the losses of its own simulated flight (`docs/ASCENT.md`).
* **Shared-core families are biased.** The sizer never carries a core oversized for the mission being flown, so
  a family's smaller variants come out too light when sized alone, and over-predict payload when the core is
  pinned. This is measured in `docs/ACCURACY.md` section 6b, and is not corrected.
* **Drag is an estimate.** It is built up from the outside shape, with no protuberances, fins, core-to-booster
  interference or plume effects, and it depends on the nose length, which most designs carry as an assumption.
  `docs/DRAG.md` has the measured error.
* **Not modelled:** propellant crossfeed, more than one booster set or boosters on a stage other than the first,
  engine shutdowns in flight, dog-leg ascents and plane changes, boil-off and chill-down mass, products of inertia, and
  acoustic or shock prediction. A motor below about one tonne of propellant is badly served by every mass
  relation here.
* **Out of scope:** six-degree-of-freedom simulation, finite elements, CFD and flight software.

## How accurate it is

Twenty-four real vehicles, sized from payload and orbit alone, against their published lift-off mass:

| | Vehicles | Median absolute error |
|---|---|---|
| All-liquid | 17 | 13.2 % |
| With serial solid stages | 7 | 11.5 % |

No input was tuned to match a vehicle. [`docs/ACCURACY.md`](docs/ACCURACY.md) gives every vehicle and attributes
each error to its cause.

## Documentation

| | |
|---|---|
| [`docs/USER_MANUAL.md`](docs/USER_MANUAL.md) | full manual: inputs, workflows, outputs, troubleshooting |
| [`docs/ACCURACY.md`](docs/ACCURACY.md) | what the tool gets wrong, measured, with the mechanism for each error |
| [`docs/DRAG.md`](docs/DRAG.md) | how drag is estimated from the geometry, and how far that is from published data |
| [`docs/OPTIMISATION.md`](docs/OPTIMISATION.md) | the staging objectives, and what the search does not promise |
| [`docs/COST_VALIDATION.md`](docs/COST_VALIDATION.md) | the cost model against real programmes' work-years |
| [`docs/EXTERNAL_MERS.md`](docs/EXTERNAL_MERS.md) | mass relations from outside the book, and why none was adopted |
| [`docs/ERRATA_COMPLIANCE.md`](docs/ERRATA_COMPLIANCE.md) | how the book's published errata were applied |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | coverage of the book by chapter, and open work |
| [`docs/CHANGELOG.md`](docs/CHANGELOG.md) | what changed in each version |
| [`outputs/engineering_method_register.xlsx`](outputs/engineering_method_register.xlsx) | every method with its source, assumptions, limits and verification |
| [`docs/VALIDATION_REPORT.md`](docs/VALIDATION_REPORT.md), [`docs/TECHNICAL_REPORT.md`](docs/TECHNICAL_REPORT.md) | earlier reports, kept for the record |
| [`docs/DROP_ZONES.md`](docs/DROP_ZONES.md) | jettison drop zones, whose tab is hidden at present |

## Conventions

SI units · z up from the stage-1 nozzle exit plane · stage 1 = first to burn · **O/F = m_ox/m_fuel** ·
**s = m_inert/(m_inert + m_propellant)** (Eq. 5:5a), inert = dry + residual + loading margin, payload excluded.
The YAML is the source of truth and the workbook is a report of it. Every input leaf is `{v, u, d, s, t}`: value,
units, description, source and provenance (`user`, `reference` or `assumed`). Bare values are rejected.

## Testing

```bash
python -m pytest                           # 20 to 45 minutes
python tools/verify_workbook.py outputs/launch_vehicle_sizing_workbook.xlsx
```

## Building and releasing the Windows app

Releases are built automatically. Push a version tag that matches `pyproject.toml`, and the GitHub workflow in
`.github/workflows/release.yml` runs the tests on Windows, builds the app, and attaches
`MERLIN-<version>-windows.zip` to the release that the download link above points at:

```bash
git tag v1.4.0
git push origin v1.4.0
```

To build it on your own machine instead, from a clean virtual environment:

```bash
pip install -r requirements.txt pywebview pyinstaller
python tools/build_app.py --zip
```

That writes the app to `dist/MERLIN/` and the zip beside it. Use a clean environment, because PyInstaller bundles
everything the building Python can import.

## Licence and credit

MIT with an added attribution requirement: see [`LICENSE`](LICENSE). You may use, change and share the tool freely,
and any work you share that uses it or its results must credit "MERLIN by Szymon Błażejewicz".
[`CITATION.cff`](CITATION.cff) has the citation details.
