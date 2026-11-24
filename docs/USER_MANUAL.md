# User manual — MERLIN

A conceptual-design sizing tool for expendable multistage launch vehicles with **liquid stages, solid motor
stages and strap-on boosters**. The methods come from Edberg & Costa, *Design of Rockets and Space Launch
Vehicles*, 2nd ed. (AIAA, 2022); every equation used is listed with its printed page number in the method
register (`outputs/engineering_method_register.xlsx`, also a sheet in every workbook).

> **What this tool does.** It closes a mass, geometry and delta-v budget that is self-consistent with the
> assumptions you give it, and reports every assumption and its source.
> **What it does not do.** It does not feed its analyses back: the structure is not re-sized for the loads it is
> shown to carry. It has no reusable vehicles, thermal behaviour or combustion modelling. A closed budget is
> *not* proof that a vehicle can fly the mission.

---

## Contents

1. [Install and first run](#1-install-and-first-run)
2. [How the tool works](#2-how-the-tool-works)
3. [Conventions you must know](#3-conventions-you-must-know)
4. [The configuration files](#4-the-configuration-files)
5. [Field reference](#5-field-reference)
6. [Workflows](#6-workflows)
7. [Outputs](#7-outputs)
   * [7.1 The design report](#71-the-design-report)
   * [7.2 The GUI](#72-the-gui)
   * [7.3 The optional studies](#73-the-optional-studies)
   * [7.4 Real engines: the database](#74-real-engines-the-database)
   * [7.5 The ascent trajectory](#75-the-ascent-trajectory)
   * [7.6 Trade studies and design comparison in the GUI](#76-trade-studies-and-design-comparison-in-the-gui)
   * [7.7 Sensitivity](#77-sensitivity)
   * [7.8 Drop zones (hidden)](#78-drop-zones-hidden)
   * [7.9 Ground and flight loads](#79-ground-and-flight-loads)
   * [7.10 Aerodynamic build-up and centre of pressure](#710-aerodynamic-build-up-and-centre-of-pressure)
   * [7.11 Optimising the pitch programme](#711-optimising-the-pitch-programme)
   * [7.12 Static stability and control authority](#712-static-stability-and-control-authority)
   * [7.13 Shell stress, buckling and required thickness](#713-shell-stress-buckling-and-required-thickness)
   * [7.14 Solid motor internal ballistics](#714-solid-motor-internal-ballistics)
   * [7.15 Cost](#715-cost)
   * [7.16 Payload environment](#716-payload-environment)
   * [7.17 Trade studies and design comparison](#717-trade-studies-and-design-comparison)
   * [7.18 CAD export](#718-cad-export)
   * [7.19 Importing vehicles from public sources](#719-importing-vehicles-from-public-sources)
   * [7.20 Propellants, mixture ratios and real engines](#720-propellants-mixture-ratios-and-real-engines)
   * [7.21 Winds aloft: using the launch site's own profile](#721-winds-aloft-using-the-launch-sites-own-profile)
   * [7.22 Reading the loads diagram](#722-reading-the-loads-diagram)
8. [Checks, warnings and errors](#8-checks-warnings-and-errors)
9. [Troubleshooting](#9-troubleshooting)
10. [Accuracy: what the validation shows](#10-accuracy-what-the-validation-shows)
11. [Tests and verification](#11-tests-and-verification)
12. [Extending the tool](#12-extending-the-tool)

---

## 1. Install and first run

**On Windows, the app needs nothing installed.** Download `MERLIN-<version>-windows.zip` from the release page, unzip
it somewhere you can write to, and run `MERLIN/MERLIN.exe`. It is the GUI of §7.2 in its own window. The rest of this
section is for running from source.

```bash
python -m venv .venv
.venv\Scripts\activate                    # Windows; on Linux and macOS: source .venv/bin/activate
pip install -r requirements.txt          # numpy, scipy, pyyaml, matplotlib, openpyxl
pip install -e .
```

Run the default two-stage kerolox demonstration:

```bash
python -m launch_vehicle.main run --design config/default_design.yaml --out outputs
```

That writes the workbook, the drawings and the CSV exports into `outputs/` and prints a short summary.
Useful variants:

```bash
# skip the sensitivity studies (faster), add the delta-v split optimisation
python -m launch_vehicle.main run --design config/default_design.yaml --out outputs --no-sensitivity --with-optimization

# only the optimisation, printed to the console
python -m launch_vehicle.main optimize --design config/default_design.yaml

# the optional studies (each adds its own report section; see 7.3)
python -m launch_vehicle.main run --design config/default_design.yaml --out outputs --all-studies
python -m launch_vehicle.main run --design config/default_design.yaml --out outputs --performance --staging
python -m launch_vehicle.main run --design config/default_design.yaml --out outputs --uncertainty --mc-samples 500

# the GUI (opens a browser on http://127.0.0.1:8000)
python tools/gui.py

# the worked examples
python -m launch_vehicle.main run --design examples/example_solid_smallsat.yaml --out outputs/solid
python -m launch_vehicle.main run --design examples/example_boosters.yaml      --out outputs/boosters
python -m launch_vehicle.main run --design examples/example_3stage_leo.yaml    --out outputs/3stage
```

Verification and validation:

```bash
python -m pytest -v                       # the test suite (see section 11)
python tools/run_tests.py                 # offline fallback runner if pytest is unavailable
python tools/verify_workbook.py outputs/launch_vehicle_sizing_workbook.xlsx   # recalculates the workbook in LibreOffice
python tools/run_validation.py            # re-runs every real-vehicle case
python tools/validate_cost.py             # the cost model against real work-years, docs/COST_VALIDATION.md
python tools/build_validation_report.py   # rebuilds the validation workbook, figure and tables
```

---

## 2. How the tool works

```
YAML design + YAML assumptions
        │  strict loader: every input must carry value/units/description/source/provenance
        ▼
   validation  ──────────────► hard errors (stop) and warnings (reported)
        ▼
 delta-v budget   ideal speed + Earth-rotation vector term + ascent losses + allowances + one margin
        ▼
 stage delta-v allocation (fractions or fixed values)
        ▼
 ┌─► coupled sizing loop (top stage downward) ────────────────────────────────┐
 │     rocket equation → propellant                                           │
 │     (with strap-ons: the parallel-burn phase sequence is solved instead)    │
 │     thrust and mass flow → burn time, nozzle/engine envelope                │
 │     tanks or motor casing → geometry → stage layout                         │
 │     mass-estimating relations → new dry mass                                │
 │     burn times feed back into the loss model                                │
 └── repeat until the relative change of GLOM, dry mass, propellant, length    │
     and delta-v is below the tolerance (never "converged" at the iteration cap)
        ▼
 mass ledger → centre of mass and moments of inertia at each flight event
        ▼
 workbook + drawings + CSV + method register
```

The Python engine is authoritative. The workbook **reports** it, with live Excel formulas that recompute key
results independently so a reviewer can audit them (see section 7).

---

## 3. Conventions you must know

| Topic | Convention |
|---|---|
| Units | SI everywhere (kg, m, s, N, Pa, K). Angles in degrees in the configuration. |
| Axial coordinate | `z` upward from the **first-stage nozzle exit plane**; every position in the ledger, geometry sheet and drawing uses it. |
| Stage numbering | Stage 1 is the first to burn. Strap-on boosters are "stage 0" in the book's language and are reported separately. |
| Mixture ratio | `mixture_ratio_OF` = m_oxidiser / m_fuel. (The book's *f* is the reciprocal.) |
| Structural factor | `s = m_inert / (m_inert + m_propellant)` (book Eq. 5:5a), payload excluded, where inert = dry hardware + residual + loading-margin propellant. |
| Propellant categories | *mission* (produces delta-v), *start-up* (consumed, no delta-v credit), *residual* and *loading margin* (still on board at burnout). They never overlap. |
| Effective Isp | An explicit assumption per stage: `vacuum`, `weighted` (book Eq. 4:18, 1/3 sea level + 2/3 vacuum) or `user`. |
| Margins | Exactly one mass-growth margin per stage and one delta-v margin for the mission. Nothing is margined twice. |
| Solid motors | No start-up propellant and no residual by default (book p.489); the casing MER already contains insulation, nozzle, thrust structure and TVC (book p.490). |

---

## 4. The configuration files

Two annotated YAML files drive everything:

* **`config/default_design.yaml`** — the vehicle and mission (copy it to start a new design, or press *New*
  in the GUI, which does the same thing and then clears the fields that are yours to answer).
* **`config/engineering_assumptions.yaml`** — MER coefficients, propellant properties, tank materials,
  convergence settings. Shared by all designs.

Two further files are **libraries**: real hardware and places a design may reference by name, never designs in
their own right, and the GUI does not offer them in *Open*.

* **`config/engine_database.yaml`** — real engines and motors (§7.4).
* **`config/launch_sites.yaml`** — real launch sites with their coordinates (§5.1). Each row names its own
  source. The file states plainly what it does not contain: no pad altitudes, because the sources used give
  none, and no range-safety azimuth corridors, because those are per-pad and per-vehicle and inventing them
  would be worse than leaving the user to know their own range.

**Every leaf must be a mapping with five keys**, or the loader rejects it:

```yaml
payload_mass_kg: {v: 10000.0, u: kg, d: "Payload delivered to the injection orbit", s: "User requirement", t: user}
```

| key | meaning |
|---|---|
| `v` | the value (`null` is allowed where the field is optional) |
| `u` | units |
| `d` | description |
| `s` | source or justification — free text, never empty |
| `t` | provenance: `user`, `reference` (traceable to a source) or `assumed` |

This is what makes the workbook's input sheets honest: each row is colour-coded by provenance, so a reviewer
immediately sees which numbers are assumptions. A bare value such as `payload_mass_kg: 10000` is an error.

Overrides on the command line and in code use dotted paths into the *unwrapped* design, e.g.
`stages.0.engine.isp_vac_s`, `vehicle.dv_fractions`, `boosters.n_total`.

---

## 5. Field reference

### 5.1 `mission`

| Field | Meaning |
|---|---|
| `payload_mass_kg` | Payload delivered to the injection orbit (adapter and fairing are separate). |
| `payload_adapter_mass_kg` | PAF mass; `null` uses the MER `0.0755 m_PL + 50 kg` (Table 8.8). |
| `payload_envelope_diameter_m`, `payload_envelope_length_m` | Static envelope; must fit inside the fairing with the radial clearance. |
| `delta_v_override_mps` | Replaces the whole budget with one number (study/testing only). |
| `report_apogee_maneuver` | For GTO, report the spacecraft's apogee burn as an informational line. |
| `orbit.type` | `LEO`, `SSO`, `GTO`, `GEO_VIA_GTO`, `GEO_DIRECT`, `CUSTOM`. |
| `orbit.perigee_altitude_km`, `apogee_altitude_km`, `eccentricity` | Injection orbit. LEO/SSO are circular. |
| `orbit.inclination_deg` | Target inclination; computed from J2 for `SSO`. Must be ≥ the launch-site latitude (no dog-legs). |
| `launch_site.site` | A site from `config/launch_sites.yaml` (30 sites, by name, listed in the GUI under their continent; one is a suborbital-only range and one a proposed site whose coordinate is a stand-in, and both say so when picked). Fills `latitude_deg` (and the longitude, which only the hidden drop-zone study reads) when you leave it `null`; if you state a latitude as well, **yours wins** and the disagreement is reported. `null` = Custom, use your own latitude. The library holds no pad altitudes rather than guessing them. |
| `launch_site.latitude_deg`, `altitude_m`, `azimuth_deg` | Site; azimuth `null` ⇒ `sin β = cos i / cos lat`. Latitude is what the model uses: it sets the Earth-rotation credit and the floor on reachable inclination. |
| `launch_site.include_earth_rotation` | "Include Earth's rotation" in the GUI: subtract the site's rotation speed, as a vector, from the delta-v the vehicle must supply (book Example 3.9). |
| `losses.model` | `book_penalty` (Eqs. 3:36–3:38 regression, recommended for ground launch) or `user`. |
| `losses.gravity_mps`, `drag_mps`, `steering_mps` | Used only when `model: user`. |
| `losses.other_allowance_mps` | Extra allowance added on top of the loss model. |
| `losses.staging_delay_s` | Added to the ascent time per separation. |
| `losses.ascent_time_override_s` | **Use when a stage burns after a long coast** (see section 9). Replaces the summed burn times in the loss regression. |
| `losses.design_margin_fraction` | Delta-v margin, applied once to the subtotal. |
| `cost.*`, `cost_year` | Optional. The Cost tab's settings (§7.15). |
| `air_launch.release_speed_mps`, `release_altitude_m`, `flight_path_angle_deg` | Optional. Credits the horizontal component of the carrier's release speed. Requires `losses.model: user`. |

### 5.2 `fairing`, `vehicle`, `constraints`

| Field | Meaning |
|---|---|
| `fairing.diameter_m` | May be **larger** than the upper stage: a conical forward adapter is added automatically (book Fig. 8.15). Smaller is an error. |
| `fairing.nose_length_over_D`, `axial_clearance_m`, `radial_clearance_m` | Fairing shape and payload clearances. |
| `fairing.material` | `metal` (13.3 kg/m²) or `composite` (9.89 kg/m²), Table 8.8. |
| `fairing.jettison_at_stage_start` | Jettisoned at the start of this stage's burn; `N+1` carries it to orbit (conservative). |
| `fairing.mass_override_kg` | Bypass the areal-mass MER. |
| `vehicle.paf_length_over_D` | Adapter height / upper-stage diameter. |
| `vehicle.dv_allocation_mode` | `fractions` (normalised shares) or `fixed` (m/s per stage; last may be `null` = remainder). |
| `vehicle.dv_fractions`, `dv_fixed_mps` | The allocation itself. In the GUI this is **one percentage per stage**, each showing the m/s it buys, with a running total and a **Find the lightest split** button that runs the optimiser (§6) and fills the result. Shares are normalised to 100 % if they do not add up, so you can type 60/50 and press Normalise. |
| `constraints.*` | `max_vehicle_length_m`, `min_tw_liftoff`, `max_accel_g`, `min_tw_upper`. Violations become ERROR or WARNING issues. |

### 5.3 A liquid stage

Required blocks: the stage itself, `layout`, `tank`, `engine`.

**The number of stages is the length of the `stages:` list** — there is no separate count to keep in step with
it, which is why there is none to get wrong. Three things elsewhere are counted in stages and must agree:
`vehicle.dv_fractions` needs one entry per stage, `fairing.jettison_at_stage_start` must be 2..N+1, and
`mission.last_ascent_stage`, where it is set at all, must name a stage that exists. In the GUI the **Number
of stages** control at the top of the panel adds or removes a stage and moves all three for you, saying what
it moved (§7.2); editing the YAML by hand, you move them yourself and validation tells you if you miss one.

| Field | Meaning |
|---|---|
| `stage_type` | `liquid` (default) or `solid`. |
| `fuel`, `oxidizer` | Keys into `propellants` in the assumptions file. |
| `mixture_ratio_OF` | m_ox / m_fuel. |
| `residual_fraction`, `loading_margin_fraction` | Unburned propellant fractions (of mission propellant). |
| `startup_time_s` | Start-up propellant = mass flow × this time (book Eq. 8:2). |
| `diameter_m` | Stage external diameter. |
| `structure_mode` | `bottom_up` (component MERs — normal) or `aggregate_s` (one structural factor, no component masses). |
| `structural_factor_s` | Only for `aggregate_s`. |
| `structure_mass_factor` | Multiplies tank and unpressurised-structure MERs (book p.498 suggests ~0.8 for composites). |
| `inert_mass_margin_fraction` | The single mass-growth margin for this stage. |
| `feed_system_mass_per_engine_kg`, `pressurant_mass_fraction_of_propellant`, `separation_hardware_mass_kg`, `other_equipment_mass_kg` | Explicit extra masses. |
| `avionics_mass_override_kg`, `max_length_m` | Optional. |
| `layout.aft_skirt_over_D`, `intertank_over_D`, `fwd_skirt_over_D` | Structure lengths as multiples of the diameter. |
| `layout.interstage_min_length_m`, `interstage_clearance_m`, `interstage_half_angle_deg` | Interstage sizing and diameter transitions. |
| `tank.arrangement` | `separate` or `common_bulkhead`. |
| `tank.order_bottom_to_top` | e.g. `[fuel, oxidizer]`. |
| `tank.diameter_m` | **Optional**: tanks narrower than the stage (upper stages with tanks inside a wider skirt). Defaults to the stage diameter. |
| `tank.dome_aspect_ratio` | R/h (1 = hemisphere, √2 = 2:1 ellipsoid). |
| `tank.ullage_fuel`, `ullage_oxidizer` | Ullage volume fractions (book Eq. 8:8). |
| `tank.mass_method_fuel`, `mass_method_oxidizer` | `akin_propellant_mass` (Table 8.6), `akin_volume` (Table 8.7), `pressure_vessel` (thin-wall membrane, supplementary), `mass_fraction`, `user_mass`. |
| `tank.wall_thickness_assumed_m`, `pressure_*_Pa`, `mass_fraction_*`, `user_mass_*_kg` | Inputs for those methods. |
| `tank.material`, `load_temperature_K`, `insulated_fuel`, `insulated_oxidizer` | Material (see §5.1) and insulation. |
| `engine.n_engines`, `thrust_vac_per_engine_N`, `thrust_to_weight_ignition` | Specify **exactly one** of the last two: fixed thrust, or a "rubber engine" scaled to a lift-off T/W. |
| `engine.isp_vac_s`, `isp_sl_s`, `isp_effective_mode`, `isp_sl_weight`, `isp_effective_user_s` | Performance and the effective-Isp convention. |
| `engine.expansion_ratio`, `chamber_pressure_Pa` | Used by the engine-mass and gimbal MERs and by the nozzle geometry. |
| `engine.geometry_method` | `user` (give `length_m` and `exit_diameter_m`) or `book_mer` (compute them from Eqs. 8:28–8:33; then `cstar_mps` is required). |
| `engine.length_m`, `exit_diameter_m`, `embed_fraction` | Envelope and how much of it sits inside the aft skirt. |
| `engine.mass_method`, `mass_user_per_engine_kg`, `gimbal_method`, `gimbal_user_per_engine_kg` | `mer` (Table 8.9), `user`, or `none` for gimbals. |

### 5.4 A solid stage

Set `stage_type: solid`, give `propellant` (a key into `solid_propellants`) and a `motor` block **instead of**
`tank` and `engine`. The stage-level fields are the same except that `fuel`, `oxidizer`, `mixture_ratio_OF`,
`feed_system_mass_per_engine_kg` and `pressurant_mass_fraction_of_propellant` do not apply.

| `motor` field | Meaning |
|---|---|
| `n_motors` | Must be 1 (use strap-on boosters for clusters). |
| `thrust_mode` | `tw_ignition` (lift-off T/W), `fixed_thrust` (`thrust_vac_total_N`) or `burn_time` (`burn_time_s` — the usual choice for a real motor). |
| `isp_vac_s`, `isp_sl_s`, `isp_effective_mode`, `isp_sl_weight` | Performance. |
| `expansion_ratio`, `chamber_pressure_Pa`, `cstar_mps` | Nozzle sizing inputs (Eq. 8:28). |
| `nozzle_geometry_method` | `book_mer` (only the protruding diverging cone is computed, book p.490) or `user` with `nozzle_length_m` and `exit_diameter_m`. |
| `embed_fraction` | How much of the nozzle is submerged in the aft dome/skirt. |
| `casing_mass_method` | **`kibbey_medium` is the default for a composite case** (size-dependent, f = 0.075 + 0.0030 (m_p/4536)^(-2/3), predicts the WHOLE stage inert). Also `book_steel` (k = 0.135 — keep this for a steel case, where Kibbey is 45–49 % light), `book_composite` (k = 0.1154, flat and scale-free), `star_motor` (size-dependent, fitted to 55 STAR motors, upper-stage class only), `mass_fraction` (`casing_mass_fraction`), `user_mass` (`casing_mass_kg`), or any `solid_inert` stage-level relation. See §7.3 on which to pick - the book constant is 26-51 % high for an upper-stage motor. |
| `casing_volume_factor` | Casing volume / grain volume; book Eq. 8:24 uses **1.12** (10 % grain openings + 2 % insulation and igniter). |
| `dome_aspect_ratio` | 1.0 (hemispherical) is the book's recommendation; shallower domes are allowed and warned about. |
| `wall_thickness_assumed_m` | For internal/external geometry only. |
| `tvc_mass_kg`, `igniter_mass_kg` | Normally 0: both are already inside the casing MER. |

The grain is modelled as a centre-perforated ("core burner") charge whose bore holds exactly the
non-propellant volume of Eq. 8:24; for short, fat motors the bore is run through the domes as well. The tool
reports the web thickness, bore radius and the **implied average burn rate** (web ÷ burn time) so you can check
it against propellant data (Eqs. 4:32–4:33); outside 1–40 mm/s it warns.

### 5.5 Strap-on boosters

One optional top-level `boosters:` block. The boosters burn in parallel with stage 1 ("stage 0"), then are
jettisoned (book Sec. 5.11, Fig. 5.21). **Their propellant load is an input, not a result.**

The block's presence is what decides whether the vehicle has strap-ons at all; in the GUI the **Strap-on
boosters** control at the top of the panel adds or removes it (§7.2). Six check cases fly on them —
Ariane 5 ECA, Atlas V 551, Delta II 7920, Delta IV Heavy, H-IIA 202 and Soyuz-2.1b — so both the solid and
the liquid paths are measured against real vehicles.

| Field | Meaning |
|---|---|
| `type` | `solid` or `liquid`. |
| `n_total`, `n_ground_lit` | Total number and how many ignite at lift-off; the rest ignite when the ground-lit group burns out (e.g. Delta II: 9 total, 6 ground-lit). |
| `attach_stage` | Must be 1 in this version. |
| `propellant` (solid) or `fuel`/`oxidizer`/`mixture_ratio_OF` (liquid) | Propellant. |
| `isp_vac_s`, `isp_sl_s`, `isp_effective_mode`, `isp_sl_weight` | Performance of one booster. |
| `propellant_mass_each_kg`, `burn_time_s` | Define the mass flow and thrust: ṁ = m_p / t_b, T = ṁ g₀ Isp. A real motor's **average** thrust results, which is lower than its peak. |
| `residual_fraction` | Propellant left at burnout (jettisoned with the booster). |
| `inert_mass_method` | `user_mass` (published empty mass — best), `book_steel`, `book_composite`, `mass_fraction`. |
| `inert_mass_each_kg`, `inert_mass_fraction`, `inert_mass_margin_fraction` | Inputs for those methods. |
| `diameter_m`, `dome_aspect_ratio`, `nose_length_over_D` | Booster geometry. Set `nose_length_over_D: 0` if the published empty mass already includes the nose cone. |
| `base_z_offset_m`, `radial_gap_m` | Where the booster sits relative to the core. |
| `exit_diameter_m`, `nozzle_length_m` | Nozzle envelope (for the drawing and the length). |
| `attach_hardware_mass_each_kg` | Attach/separation hardware carried on the booster. |

With boosters attached, `thrust_to_weight_ignition` on the core engine means the **total** lift-off T/W
(core + ground-lit boosters), which is how published figures are quoted; the core thrust is the remainder.
The core must outlast the boosters, or the tool reports an error telling you to throttle the core or shorten
the booster burn.

### 5.6 The assumptions file

`mer` (Tables 8.6–8.9 coefficients), `propellants` (density, boiling point, insulation areal mass, tank MERs),
`solid_propellants` (density from Table 4.7), `tank_materials`, `earth_model` (`book` or `wgs84`) and
`convergence` (`tol`, `max_iter`, `relax`). Change these only with a reason, and record it in the `s` field.

Their values can also be changed for one design in the GUI, in the *Propellant library*, *Material library* and
*Modelling assumptions* sections of the input panel. Such a change is not written into the shipped file: a
saved design keeps it in a `library:` block of its own, as a copy of the changed field, so that design sizes the
same vehicle wherever it is opened and every other design is unaffected. (Before v1.1 any such change made the
sizing fail.)

### 5.6b Your own propellants and tank materials

The **Library...** button in the GUI's top bar, and the **+ own** button beside every fuel, oxidiser, solid
propellant, propellant combination and tank material dropdown, open a form for adding an entry of your own. It is stored in `designs/my_library.yaml`, not in
the shipped file, and is offered in the dropdowns of every design, marked "(my library)".

* **A fuel or oxidiser** needs its role and its density as loaded, which sets the tank volume and matters most.
  Optional: the normal boiling point (blank means storable, so no cryogenic shrinkage), the insulation mass per
  square metre (blank is 0), and a tank-mass-per-kg coefficient for the "Akin, by propellant mass" tank method.
  Without that coefficient the tank must be sized "by volume" or "as a pressure vessel", and the tool says so with
  a button for each. Performance is not a property of the propellant here: the Isp is typed on the engine.
* **A tank material** needs its density, published minimum yield, minimum tank gauge, Young's modulus and
  thermal expansion coefficient. A blank allowable stress takes 0.633 x yield, the basis every shipped material
  uses, so a trade compares like with like. Weld efficiency, safety factor, corrosion allowance, Poisson's ratio
  and the minimum structural gauge default to the shipped aluminium's values, tagged `assumed`. Remember that a
  material changes the vehicle's mass only for a tank sized "as a pressure vessel" (§5.7).
* **A propellant combination** names an oxidiser and a fuel from the library (shipped or your own) and the
  mixture ratio O/F the engines run at, which is required. Picking it on a stage writes the fuel, the oxidiser and
  that mixture ratio into the stage, as a shipped combination does. Optional reference figures (O/F for peak Isp,
  Isp, c*, chamber temperature, exhaust molecular mass) are for reference only, except c*, which is offered when an
  engine sized from the book relations has none of its own. The name follows the two choices, OXIDISER/FUEL,
  until you type one of your own.
* **A solid propellant** needs the density of the cast grain, which sets the motor case volume. Its c* and
  burn-rate exponent are optional and go together: the internal ballistics analysis needs both and nothing else
  reads them. The motor's Isp is an input of the motor, not of the propellant.

Every entry needs a source, and each field is range-checked and annotated `{v, u, d, s, t}` like the shipped
library. A name already in the shipped library is refused: change that entry's values in the input panel
instead. A design saved with one of your entries carries a copy in its `library:` block, so it opens on a
computer that has never seen your library, and later edits to your library do not change a design already
saved. Removing an entry from your library leaves those copies alone.

### 5.7 Structural materials

Four are shipped, and the dropdown on `tank.material` lists them by name:

| Key | Material | Published min. yield | Allowable used | Density |
|---|---|---|---|---|
| `Al-2219` | Aluminium, 2219-class | 395 MPa | 250 MPa | 2,840 kg/m³ |
| `SS-301-FH` | Stainless 301, full hard (AMS 5519) | 965 MPa | 611 MPa | 7,880 kg/m³ |
| `SS-304L` | Stainless 304L, annealed | 170 MPa | 108 MPa | 8,030 kg/m³ |
| `Ti-6Al-4V` | Titanium grade 5, annealed (AMS 4911) | 825 MPa | 522 MPa | 4,430 kg/m³ |

**Two things to know before trading one against another.**

*The allowable is not the yield.* Every entry is derated to **0.633 of its published minimum yield** — the
same fraction the original Al-2219 entry implied (250/395). That one number stands in for everything a
preliminary model does not carry: temperature, weld softening beyond the joint efficiency, fatigue, fracture
control, and the gap between a specified minimum property and a design allowable. It is applied uniformly for
one reason: quoting one candidate at full yield and another at two thirds of it would decide a material trade
by bookkeeping rather than by metallurgy. Each entry records its `yield_min_Pa` so the basis can be checked
and changed. **None of these is a qualified allowable.**

*The material only changes the mass if the tank mass method reads it.* `akin_propellant_mass` and
`akin_volume` are relationships fitted to flown tanks, in propellant mass or tank volume, and the material
never enters — switch from aluminium to steel under them and the lift-off mass moves by hundredths of a
percent. Only `pressure_vessel` sizes a wall from the allowable stress and density. The tool raises a
**`MATUNUSED`** warning when a design names a material its own mass method ignores, so this cannot be
mistaken for the tool being broken. The shell stress and buckling study always reads the material directly.

With `pressure_vessel` sizing on both stages of the shipped default design, the four come out: Ti-6Al-4V −4.4 %,
Al-2219 baseline, SS-301-FH +4.3 %, SS-304L **+92 %**. The last is not a bug — annealed 304L has about a seventh of
2219's allowable. A real 304L vehicle tank is cold-worked and pressure-stabilised, which this entry does not
model; use `SS-301-FH` for the full-hard, thin-gauge case.

Solid motor casings do **not** use this library: their mass comes from the casing relationships in
§5.4, which are functions of propellant mass.

---

## 6. Workflows

### 6.1 Size a new liquid vehicle

1. Copy `config/default_design.yaml`.
2. Set the mission (payload, orbit, launch site) and the fairing.
3. Set stage diameters, propellants, Isp values and the thrust mode of each stage.
4. Choose a starting `dv_fractions` (e.g. `[0.45, 0.55]`) and run. With `optimise_dv_split` on, as shipped, the split
   is replaced by the optimum before sizing (§6.6); with it off, run `optimize` and feed the returned split back in.
   On three- and four-stage vehicles this matters a lot: a poor split can double the GLOM.
5. Check in the Trajectory tab that the vehicle reaches its orbit. The lightest vehicle need not (§7.5).
6. Read the Results dashboard: convergence status, errors and warnings first, then the masses.

### 6.2 Size a solid vehicle

Start from `examples/example_solid_smallsat.yaml`. Use `thrust_mode: burn_time` with a realistic motor action
time (60–120 s is typical). Watch two things: the **implied burn rate** (section 5.4) and the
**casing mass fraction** — the book's MER is conservative for modern filament-wound motors (section 10).

### 6.3 Add strap-on boosters

Start from `examples/example_boosters.yaml`. Give the booster's published propellant mass, empty mass and burn
time. Check the `Parallel_Burn` sheet: it lists each phase, its mass-averaged Isp (Eq. 5:66) and its delta-v,
and recomputes them in Excel.

### 6.4 Air launch

Add the `air_launch` block and set `losses.model: user`. Only the horizontal component of the release speed is
credited; the altitude benefit must be reflected in your (lower) gravity and drag loss estimates. See
`validation/pegasus_xl.yaml`.

### 6.5 Trade studies

`run` performs one-at-a-time sensitivity studies (Isp, delta-v, payload, margins, propellant type) and writes
them to the `Sensitivity` sheet. `--with-optimization` adds the GLOM-minimising delta-v split. For a
stage-count trade, write explicit configurations and compare (`examples/example_3stage_leo.yaml`).

### 6.6 Let the tool choose the staging split

Two inputs in the `vehicle:` block, both ordinary fields in the GUI:

| | |
|---|---|
| `optimise_dv_split` | On in every shipped design since v1.1 (it was off before); it adds a few seconds to each sizing. **On, the delta-v split is replaced by the optimum before the vehicle is sized**, so the mass, geometry, loads, drawing and cost all describe the same rocket as the split that is reported. The GUI writes the applied split back into the panel as a changed value, with its revert arrow; your file on disk is untouched until you save. |
| `optimise_objective` | `glom` (lightest vehicle, the default), `cost` (lowest development cost) or `payload` (most payload at the design's own lift-off mass). |

It was off by default until v1.1. It is on now because the published accuracy figures are for the optimised split. Turn
it off when the split is your decision; the result then uses yours exactly as written.

Before this existed the optimum was a **footnote**: the report printed an optimal split next to a vehicle
sized from your split, and acting on it meant reading the number off the report and typing it back in.

Two things worth knowing before you pick an objective. **`cost` means development cost**, because the
cost per flight also depends on the launch rate and production run you assume, not on the vehicle alone. And **the
cost optimum is not the mass optimum**: on the shipped default, lightest is near a 35/65 split and cheapest
to develop near 53/47, because development effort is a sum of per-element powers of mass and that sum is not
minimised by minimising the total. Full detail, including what the search does not promise, is in
[`docs/OPTIMISATION.md`](OPTIMISATION.md).

---

## 7. Outputs

| File | Content |
|---|---|
| `launch_vehicle_sizing_workbook.xlsx` | The engineering workbook (sheets below). |
| `vehicle_schematic.png/.pdf` | Longitudinal schematic to scale, dimensioned, with a data panel. |
| `stage<N>_schematic.png/.pdf` | One stage with every segment dimensioned. |
| `mass_distribution.png/.pdf` | Component mass vs axial position and the CM at each flight event. |
| `geometry_dimensions.csv`, `component_positions.csv`, `stage_summary.csv`, `parallel_burn_phases.csv` | Machine-readable exports. |
| `engineering_method_register.xlsx/.csv` | Every method, its equation, page number and limitations. |
| `design_report.html` | **The single-file design report** — see 7.1. Add `--pdf` to convert it. |
| `performance_curves.png` | Payload capability (`--performance`). |
| `uncertainty.png` | GLOM distribution and the tornado (`--uncertainty`). |
| `staging_optimum.png` | GLOM against the stage-1 Δv share, both optima marked (`--staging`). |
| `trajectory.png` | The ascent: altitude, speed, γ, dynamic pressure, ground track and loss budget (`--trajectory`). |
| `run_summary.json` | Key results for scripting. |

Workbook sheets: `README`, `Results_Dashboard`, `Mission_Inputs`, `Vehicle_Inputs`, `Stage_Inputs`,
`DeltaV_Budget`, `Stage_Sizing`, `Parallel_Burn` (only with strap-ons), `Mass_Breakdown`, `Tank_Sizing`,
`Geometry`, `Mass_Properties`, `Sensitivity`, `Engineering_References`.

**Grey cells are live Excel formulas** that recompute a Python result independently — the rocket equation, mass
closure, tank/casing volume, phase delta-v, and the centre of mass and pitch inertia via `SUMPRODUCT` over the
ledger. They must all read zero; `tools/verify_workbook.py` recalculates the file with LibreOffice and asserts
exactly that.

In the drawing, lengths are dimensioned on the left, outer diameters across the body with witness lines and
arrowheads, and all numerical results live in the right-hand panel so they never cover the vehicle.

### 7.1 The design report

The report opens with a **summary page**: the mission in one line, the vehicle in one line, a table of *what
governs this design* — the bending moment that sizes the structure and where, the thickest shell and what
drove it, max-q, the flown and quoted accelerations, the worst control margin, the payload load factors — and
the errors and warnings, each linked to the section that derives it. Everything after it is the working.

The driver table shows only what was actually computed, so a run without `--all-studies` produces a short
table saying so rather than a padded one.


```bash
python -m launch_vehicle.main run --design config/default_design.yaml --out outputs            # writes design_report.html
python -m launch_vehicle.main run --design config/default_design.yaml --out outputs --pdf      # and a PDF, if a converter is installed
python -m launch_vehicle.main run --design config/default_design.yaml --out outputs --no-report
```

One self-contained HTML file meant to be the thing that leaves the tool — handed to a reviewer, attached to a
design review, or printed. It carries, in this order:

1. **Cover** — headline numbers, configuration, the design and assumptions files with their SHA-256 digests (so
   a report can be matched to the inputs that produced it), the tool version and the date.
2. **Limitations** — what the result is and is not, stated before any number is read.
3. **Mission requirement and Δv budget** — every budget line with its book source, and which lines are in the
   total.
4. **Vehicle configuration** — stages, propellants, propulsion, upper assembly, boosters.
   The sections of the analyses that ran follow the drawings and the mass statement, in a fixed order.
5. **Drawings** — the general arrangement, the mass distribution and every stage, embedded as images. Each
   vehicle and stage drawing is **one continuous view**, drawn at the largest scale that fits the page height,
   with the dimensions on the left and each stage's data beside the stage it describes. Nothing is cut into
   pieces or distorted: a metre axially and a metre laterally are the same length everywhere.
6. **Propulsion and performance** — thrust, mass flow, burn times, T/W, the Δv recomputed from the sized masses,
   solid-motor grain data and the parallel-burn phases.
7. **Mass statement** — stage masses, the GLOM build-up with its closure check, and the dry-mass breakdown by
   component for each stage.
8. **Mass ledger and mass properties** — every mass, where it sits, the shape used for its inertia, and the rule
   it came from; then the centre of mass and inertia at each flight event.
9. **Geometry** — the segment table and the tank/motor-case geometry.
10. **Input register** — *all* ~500 inputs (the design's and the assumptions') with units, description, source and provenance, colour-coded.
11. **Checks and warnings** — every issue the validator raised.
12. **Engineering method register** — every registered method with their book page, assumptions, limits and verification.

Self-contained means it makes no network requests at all: images are embedded, the stylesheet is inline, there
is no JavaScript. It renders identically offline. It carries its own A4 print stylesheet, so printing to PDF
from any browser gives a usable document; `--pdf` does that automatically when headless Chrome/Chromium or
`wkhtmltopdf` is installed, and says so plainly when neither is.

### 7.2 The GUI

```bash
python tools/gui.py                       # http://127.0.0.1:8000, opens a browser
python tools/gui.py --port 8080 --no-browser
```

The Windows app is this same page in its own window. Standard library only — no framework, no CDN, nothing leaves the machine, and the server binds to the loopback
interface. It is the way to drive this tool: nobody should be typing a nine-hundred-line YAML file by hand.

**The configuration you are working on** is the thing in the title bar. Name it, change it, save it:

| | |
|---|---|
| **New** | Starts a blank design brief. The structure, the units and the book's own coefficients stay; what is cleared is what you decide — payload, orbit, launch site, diameters, staging split, engines per stage, Isp. Every cleared field is outlined, carries a one-line note saying why it is asked for, and its section is opened so you can see it. The header then counts what is still empty and takes you to the next one. |
| **Open…** | Every design, grouped: *My designs* (what you saved), *Starting points*, *Examples*, and *Check cases* — the real vehicles the tool is validated against, Electron and Falcon 9 and the rest. Pick one and it loads, with its own description. |
| **Save** | Writes a complete, annotated design file into `designs/`. Your changed values are written in with `t: user` and a source saying you set them in the GUI — they do not inherit the book's provenance. The file is reloaded to prove it parses before you are told it saved, and it runs from the command line like any other design. Once a design is bound to a file of its own, Save overwrites that file: same path, no dialog, no second copy. The header says which file that is. |
| **Save as…** | Saves under a different name and switches to it. If the name is taken you are asked before anything is replaced. |
| **Library…** | Your own propellants, combinations, solid propellants and tank materials (§5.6b). |
| **Analyses…** | Which of the eleven optional studies to run. Each adds a tab of its own; **Cost**, for instance, is there only when it is picked. Anything a study depends on comes with it: tick the shell stress and the trajectory and the load cases run too. |
| **Size vehicle** | Runs the same Python model the CLI runs. |

**Save never overwrites a shipped file.** `config/`, `examples/` and `validation/` are reference material — a
check case quietly edited is a check case that no longer checks anything — so Save on one of those behaves as
Save as and keeps your version in `designs/` under its own name. The button says which of the two it currently
is, and its tooltip names the file.

**An unfinished design is told apart from a broken one.** Press *Size vehicle* with fields still empty and the
page leads with how many are empty and which, and offers to take you to the first; what the model reported is
kept underneath for anyone who wants it. A blank numeric field otherwise surfaces as whatever arithmetic reached
the `null` first, which reads like a crash and is not one.

**How many stages is the first control in the panel.** It sits above the sections, because it is the shape of
the design rather than one of its values, and it is never filtered away. Changing it rewrites the design the
way the liquid/solid switch does — it adds or removes a whole annotated stage, so the result arrives as an
unsaved draft that you name with *Save*.

| | |
|---|---|
| **Where a new stage comes from** | The uppermost stage of the shipped example of the same type, grafted whole with its own units, descriptions, sources and provenance. Not a template written into the GUI — so an added stage is annotated exactly as if you had started from that example, and there is no second set of numbers to drift out of step with the book. The donor's *upper* stage is used, not its first: a first stage carries a sea-level nozzle and a first-stage thrust-to-weight, which above the atmosphere would quietly cost you delta-v. |
| **Where it goes** | On top. A stage is added above the ones you have and removed from the top, so your first stage is never silently re-plumbed. It takes the cross-section of the stage below it, because a stacked vehicle usually shares one. |
| **What moves with it** | The delta-v split gets one entry per stage, with the stages you already had keeping their split *in proportion* and an added stage taking an equal share — so a 44/56 decision stays a 44/56 decision. It is re-tagged `assumed`, because whatever you chose, it was not this. The fairing jettison stage and `last_ascent_stage` are pulled back inside the new count, and the fairing is widened if removing a stage left it narrower than the new top stage. Every one of these is named in the note you are shown. |
| **One to six** | Not a modelling limit — the sizing loop and the trajectory integrate any number — but a conceptual-design guard. Past six stages the staging optimum is flat and the per-stage inert masses dominate. Write the YAML if you really want more. |

Two honest consequences, both guided rather than hidden. A stage added on top starts as wide as the stage
below it, and a stage carrying a fraction of the delta-v may not have enough propellant to fill a tank that
wide — the end caps alone can exceed the volume needed. Sizing says so and offers the narrower tank diameter
to apply in one click. And if you ask for **one** stage to orbit, the tool will tell you the stage has been
asked for more delta-v than any single stage of that structural fraction can give, what the ceiling is at that
Isp, and that the delta-v needs spreading over more stages. That is the rocket equation, not a limitation of
the model, and the message says so instead of reporting `mu*s >= 1`.

**Naming a real engine clears what that engine supplies.** The database never overrides a value your design
file states — that contract is deliberate, so that a check case cannot be quietly rewritten by the library.
The consequence was that picking an engine on a stage that already had its own Isp and thrust did *nothing*:
same lift-off mass to the kilogram, with the explanation three warnings deep in the Checks tab. So the pick
now blanks the figures that engine provides (Isp, thrust, expansion ratio, chamber pressure and the rest) and
tells you which, and the library fills them as the design loads. Revert any one of them to go back to your own
number. On the shipped default, choosing Merlin 1D takes it from 397,246 kg to 376,450 kg; RD-180 to
332,211 kg.

**An ascent that does not close says so first.** When no steering brings the vehicle level at its insertion altitude, the
Trajectory tab leads with a red banner and the reason: usually an upper stage with too little thrust, which falls faster
than it gains speed. The charts below then describe the failed attempt, and the analyses that need a flown ascent are
listed as having produced nothing. The sizing is unaffected unless the ascent-loss method is *simulated* (§7.5).

**Strap-on boosters are the other shape control**, directly under the stage count, for the same reason: a
design either has a `boosters:` block or it does not, and the browser can only edit what the file contains.
Before, a design without strap-ons had no way to get them and Ariane 5 had no way to lose them.

| | |
|---|---|
| **None / Solid / Liquid** | Fitting them grafts the whole 32-field block from a shipped design — the generic GEM-class motor in `examples/example_boosters.yaml` for solid, Soyuz-2.1b's strap-ons for liquid. Both are the most modest of their kind in the set, so they have the best chance of sizing on an arbitrary core. Delta IV Heavy was the obvious liquid donor and is the wrong one: its Common Booster Cores carry 200 t each at 5.1 m and drive any smaller core out of propellant before they burn out — measured, not assumed. |
| **The numbers are the donor's** | They arrive with the donor's own provenance, and the note says so. You did not choose a Soyuz booster's propellant load; set the count, the propellant per booster and the diameter to what your vehicle should carry. **How many** boosters there are is an ordinary field once they are fitted, not part of this control. |
| **Switching kind** | Keeps how many boosters you asked for and how many light on the ground — that is your architecture decision. Everything else comes from the new donor. |
| **Taking them off** | Removes the block and nothing else. Nothing outside it refers to the boosters and `attach_stage` is pinned to stage 1 in this version, so there is no index to clamp and no delta-v split to rebalance. |

Expect the core to grow when the boosters come off — and do not expect the vehicle to get heavier. Ariane 5
ECA, with its own split, sizes at 855 t with its EAPs and **738 t without them**, with the core stage nearly tripling. That is the
right answer: the EAPs burn at about 275 s of specific impulse against the cryogenic core's ~430 s, so
replacing boosted thrust with core propulsion buys the same delta-v for less propellant. It is also a good
illustration of what strap-ons are actually for, which is thrust off the pad and a smaller core, not
efficiency.

If a booster configuration will not fly, the refusal picks the lever worth pulling. When the boosters are
about the size of the core and simply burn too long for it, you are offered a shorter burn time with the
arithmetic behind it. When they dwarf the core, you are offered a smaller propellant load per booster
instead — because at fixed propellant a shorter burn means more thrust, the core throttles back, and the
limit moves again, so that button would just bring you back here. The margin on the burn-time fix is 10 %
because 10 % is what converges; 2 % oscillates.

**The inputs, organised the way you would ask about them.** The left panel is still the complete input register,
but arranged as **section → topic → field**: Mission splits into payload and orbit, orbit, launch site, ascent
losses, trajectory model and winds aloft (the cost settings are on the Cost tab); each stage into propellants and size, engine, tankage, layout and mass
estimating.

Within each topic, **the specification is shown and the assumptions fold away.** What is shown is what you or a
source set — the payload mass, the diameters, the Isp. What folds is how the model fills the gaps: ullage
fractions, dome aspect ratios, margins, and optional fields left empty. The fold says how many it is hiding, and
opens with one click. Searching or ticking *changed only* opens everything that matches.

Note the fold is **not** by provenance tag alone. On a check case every published figure is tagged `reference`,
so grouping by "user" would hide the payload mass and show nothing but empty overrides. The rule is: anything you
changed, anything with a value that came from a person or a source, any empty dropdown — because an empty
dropdown is an invitation, not clutter — **and any control that changes the shape of the design**.

That last clause exists because of a real mistake. A liquid design does not spell out `stage_type`; liquid is
the default, so the row is synthesised and honestly tagged `assumed` — and the fold hid it. The one control
that turns a stage into a solid motor sat behind a disclosure reading "N assumed or unused values", while the
stage count and the boosters sat at the top of the panel. A dropdown that decides what a stage *is* is not an
assumption about a value, whatever its provenance says.

**Fields with fixed choices are dropdowns, not text boxes.** Propellants, propellant combinations, tank
materials, real engines and motors, tank mass methods, Isp modes, orbit types, loss models, drag models — around
thirty of them. The lists are read live from the libraries, so a propellant added to
`engineering_assumptions.yaml` or an engine added to `engine_database.yaml` appears without anyone touching the
GUI. **Pick a real engine** and **Propellant combination** are on every stage, and start empty: choosing one
fills the thrust, Isp, chamber pressure, area ratio, mass, envelope and mixture ratio from the database, exactly
as `from_database` does in the file.

**Picking a launch site fills the latitude, and tells you what it costs you.** *Launch site* on the Mission
panel lists 30 sites grouped by continent, each labelled with its latitude. Choosing one sets
`mission.launch_site.latitude_deg` from `config/launch_sites.yaml` and says where the site is. It also enforces
the thing a latitude implies: **a direct ascent cannot reach an inclination below the site latitude**, because
`sin β = cos i / cos φ` has no solution there. If the inclination you had asked for is under that floor, it is
raised to the floor and the note says so — otherwise you would meet the same fact as an infeasibility on
pressing *Size*. Both the latitude and the inclination land as ordinary changed values with their revert arrows,
so you can take either back. *Custom* leaves both to you and checks nothing.

What the library does **not** know is range safety. Every real site also has azimuth corridors fixed by what the
vehicle may overfly, and they are not modelled and have not been invented — the floor is a necessary condition
for a direct ascent, never a sufficient one. §5.1 and `config/launch_sites.yaml` say so at length.

**A stage can be switched between liquid and solid.** *Stage type* on each stage is the one control that is not
an override: a liquid stage carries fuel, oxidiser, an engine and tanks, a solid stage carries a propellant and a
motor, so switching rewrites the document rather than changing a value. The new propulsion block is grafted from
the shipped design of that type — `config/default_design.yaml` for liquid, `examples/example_solid_smallsat.yaml`
for solid — so it arrives fully annotated with its own sources, not from a template invented for the purpose.
Your name, diameter, structure mode, separation hardware, margins and layout ratios survive; the three values
that are genuinely type-dependent (residual, loading margin, start-up time — zero for a cast grain, book p.489)
come across with the new block. The result is an unsaved draft, so give it a name with *Save*. Anything you had
changed but not saved travels with it.

Every field carries a human label rather than its YAML path. Click a label to see its description, its source and
the path itself, which is what you need when you want to set it from the command line.

**Results.** Tabs for the summary, the Δv budget, the stages, the masses and ledger, the drawings, the geometry,
trade & compare, sensitivity and the checks — plus one tab per analysis that ran, each with its chart and its headline
numbers, and the full report. Any table with three or more rows sorts by a click on a heading: numbers largest first,
words A to Z. Three tabs exist but are hidden at present: Architecture & families (§7.17c), Model checks and Drop zones
(§7.8). The summary carries the KPI cards, **what governs this design** when the driver analyses have run, and
the warnings. From there you can download the report, the workbook, and the CAD export as DXF, STL, OBJ or 3MF — plus STEP and BREP when a geometry kernel is installed (§11.4.1); the buttons for those are shown greyed with the reason when it is not.

**Set as baseline** freezes a result; later runs then show the percentage change against it, which is what you
want when moving one input at a time.

**Nothing is calculated in the browser.** The YAML files remain the source of truth; the GUI sends overrides on
top of a file, shows you exactly which ones are active, and saving writes them back out as a real design file.

### 7.3 The optional studies

Eleven analyses can be picked, in the GUI under *Analyses…* or by a switch on the command line: trajectory, loads,
structure, stability, payload environment, pitch-programme optimisation, internal ballistics, capability, cost,
uncertainty and staging optimum. The first three below answer the questions that come straight after "how big is it";
the rest have sections of their own. Each is off by default because each
costs time, each adds its own section to the report, and each writes its own chart into the output directory.

**`--performance` — what this vehicle lifts elsewhere.**
The sizing loop answers "how big must it be for this mission". This answers the opposite: freeze the vehicle —
every stage keeps its dry mass, propellant load, mass flow, burn time and Isp — and find the payload whose
achieved Δv equals the requirement for another orbit. The result is the carpet plot of book Sec. 3.8: payload
against circular altitude for several inclinations, payload against inclination at the design altitude, and a GTO
line. Only the payload and its adapter change, so the curves are the vehicle's performance, not a family of
re-optimised designs. The design point is marked, and it lands on the curve by construction — which is also the
check that this study and the sizing loop agree (printed as a self-check, typically within 0.1 %).
It costs no re-sizing, so a full envelope takes well under a second.
Limits: an inclination below the launch-site latitude is reported unreachable rather than flown (no dog-leg), the
sweep stops at 1,000 km because the book's loss regressions are LEO fits, and with strap-ons the parallel phases
are held at the design value, so a boosted vehicle's curve is a first-order answer near its design payload.

**`--uncertainty` — how wrong the mass could be.**
A single GLOM number carries false precision: the MERs behind it are fits to a historical population, and this
tool's own validation puts the median GLOM error at 13 % for liquid vehicles. This study gives every MER group a 1-sigma scatter
(`mer_scatter` in the assumptions file — every value an **assumption**, documented there), draws log-normal
multipliers, and re-sizes the vehicle for each sample. You get the distribution, the 5/50/95 percentiles, and a
one-at-a-time tornado of what the spread is made of. On the default design: 367 / 417 / 497 t. Samples that fail to converge are counted and
reported, not dropped — a design that falls apart under plausible scatter is a finding. `--mc-samples N` sets the
count (default 200, about 25 s); set any group's sigma to 0 to freeze it.

**`--staging` — is the stage split right.**
The book solves the optimum split in closed form with a Lagrange multiplier (Eqs. 5:32–5:33), assuming each
step's structural ratio and exhaust speed are fixed. In this tool they are not — a stage's structural factor
falls out of a mass build-up that depends on its own size — so this study runs both the closed form and the
numerical search and prints them side by side over a sweep of GLOM against the stage-1 share. The gap between
them is the price of that assumption (0.3 % of GLOM on the default design, 397.2 t against 398.6 t). Also available in the API:
`optimization.restricted_staging_speed_ratio` implements Eq. 5:40, which reproduces the book's Fig. 5.11 exactly
and answers "is another step worth it" — after three, almost never.

**`--trajectory` — fly it, don't estimate it.** See 7.5.

`--all-studies` runs everything that applies to the design.

### 7.4 Real engines: the database

`config/engine_database.yaml` holds 35 real engines and 16 motors so a design can stop flying a rubber engine.
Reference one from a stage:

```yaml
engine:
  from_database: {v: "RD-180", u: "-", d: "Real engine", s: "config/engine_database.yaml", t: reference}
```

Every field you do **not** give in that stage is filled from the row and recorded in the input register with the
row's own source. Three rules make this safe to use:

* **A row is a default, never an override.** A value you wrote always wins. If it disagrees with the row, the
  tool says so (`ENGDBOVR`) rather than silently flying an RD-180 at someone else's Isp.
* **Nothing is invented.** A field the row does not have stays as the design file left it, and the gap is
  reported (`ENGDBMISS`).
* **Contradictions are refused, not merged.** A stage sized by thrust-to-weight does not get an absolute thrust
  filled in behind its back (`ENGDBSKIP`); a liquid row referenced as a solid motor is an error.

Each row carries its own source and a confidence of `published` (the source states the figure) or `approximate`
(derived, rounded, or secondary). **These are public figures, not book data**, and the tool says so on every run
(`ENGDB`). Power cycles (pressure-fed, electric-pump, gas-generator, staged-combustion, expander) carry a usual
chamber-pressure band, used to flag a design sitting outside it — a flag, not a limit.

Worked example: `examples/example_engine_database.yaml` (RD-180 first stage, RL10C-1 upper stage).

### 7.5 The ascent trajectory

```bash
python -m launch_vehicle.main run --design config/default_design.yaml --out outputs --trajectory
```

Everywhere else the ascent losses are a regression fitted to historical launches. This flies the vehicle to its orbit and
computes them instead. [`ASCENT.md`](ASCENT.md) explains the model and its choices, and
[`ASCENT_VALIDATION.md`](ASCENT_VALIDATION.md) measures it against real vehicles.

**What is integrated** (book Sec. 6.3-6.6, Table 6.1, with the rotation terms added), RK4:

```
dv/dt     = (T cos α cos ψ − D)/m − (g − ω²r) sin γ
v dγ/dt   = T sin α cos ψ/m − (g − ω²r − v²/r) cos γ + 2ωv
dh/dt     = v sin γ        dx/dt = v cos γ · Rp/(Rp+h)
T         = ṁ·ve + (Pe − P∞)Ae                   Eq. 6:52
D         = Cd·Sref·½ρv²                         Eq. 6:49
```

ω is the part of the Earth's rotation in the orbit plane, ω = ω_E cos i, so the flight starts with the launch site's speed
and is never corrected for it afterwards. The site's speed *across* the orbit plane is removed by a constant yaw ψ of the
thrust, charged to the steering loss.

**How it is flown:**

1. A vertical rise (10 s, and until 30 m/s), one small pitch kick, then the book's gravity turn (Sec. 6.4.7) with no angle
   of attack while there is air.
2. Above 60 km, or once the dynamic pressure has fallen to 1 kPa, **linear tangent steering** (Eq. 6:59): the tangent of the
   thrust's pitch angle changes linearly with time. Its two constants are solved for the insertion altitude and a level
   arrival.
3. **The engine stops when the orbit is reached.** What is left in the tanks is reported as speed in hand.
4. The pitch kick is searched for the flight that leaves the most speed in hand. Dynamic pressure over the design's
   `max_dynamic_pressure_Pa` counts against a kick.

**The way to orbit** (`mission.ascent_profile`, under Mission → Trajectory model) follows the book's advice (pp.372-373):

| Choice | What is flown |
|---|---|
| `auto` (default) | Straight in up to 200 km. Higher: insertion at `mission.parking_altitude_m` (185 km) with the speed to coast up, and a second burn at the top. A high apogee (GTO, the Moon): a circular parking orbit and a second burn at the next equator crossing. |
| `direct` | One burn, straight to the orbit's perigee. |
| `parking` | Low first, then a second burn, whatever the altitude. |

A **solid last stage** cannot stop or restart: it coasts to the top of the climb and fires once, level, and any surplus
shows as a higher apogee. An **air launch** starts at the release speed, altitude and angle, and holds its thrust at one
pitch angle until the hand-over; there is no wing lift in the model. An engine with a **minimum throttle** below 1 throttles
to the design's `max_accel_g`. `max_q_alpha_Pa_deg` bounds the angle of attack wherever there is air.

**The output is the loss budget** to the first cutoff, as Eq. 6:58 defines it, here for the default design with its own
44/56 split:

| Loss | Integral | Default design |
|---|---|---|
| gravity | ∫ (g − ω²r) sin γ dt | 1,398 m/s |
| drag | ∫ D/m dt | 56 m/s |
| propulsion (back pressure) | ∫ Ae·P∞/m dt | 89 m/s |
| steering | ∫ T(1 − cos α cos ψ)/m dt | 62 m/s |

The four losses plus the speed gained reconstruct the vacuum ideal Δv to better than 1e-6 m/s. That identity is the check
that this is one integration decomposed, and the tests pin it. To compare with the Δv budget, the tab also gives the losses
of the whole flight on the budget's own footing (second burn included): 1,700 m/s here, against the 2,145 m/s the design was
sized with. The difference, 445 m/s, is the speed in hand.

**How good is it?** Sixteen real vehicles were flown on their published masses, thrusts, payloads and orbits. A real vehicle
arrives with nothing to spare, so the speed in hand should be near zero: Falcon 9 +24 m/s, Titan II +8, Ariane 5 ECA +21,
Pegasus +39, H-IIA +72, Vega C +97, Delta II +108. The misses are mostly vehicles whose published masses are incomplete.
Nothing was tuned; see [`ASCENT_VALIDATION.md`](ASCENT_VALIDATION.md).

**Sizing with the simulated losses.** Set *Ascent loss method* to *From this vehicle's own simulated flight*
(`mission.losses.model: simulated`). The vehicle is sized, flown, sized again with the losses it had, and so on until the two
agree, usually in three flights. It then reaches its orbit with only its margin and allowance lines left. It is off unless
you choose it, adds two or three seconds to a sizing and ten to thirty to a split optimisation, and refuses a vehicle whose
ascent does not close. The optimised split then follows what can actually be flown: 45/55 on the default design instead of
35/65.

**Drag** defaults to `geometry`: the drag coefficient is built up from the vehicle's own shape - skin friction,
pressure drag on the nose and on every flare, boattail drag and base drag, with the strap-ons added while they are
attached and the shape changing as stages leave. It is a standard preliminary estimate and not a book method (the
book gives none, p.358); [`DRAG.md`](DRAG.md) says where each relation comes from and how far the result is from
published data. Three inputs under `mission.aerodynamics` shape it: `surface_roughness_m`, `nose_shape` (`cone` or
`ogive`) and `nose_bluntness` (tip diameter over fairing diameter). **The nose length matters more than any of
them**: `fairing.nose_length_over_D` sets the cone angle, a short nose can double the drag of a small vehicle, and
most shipped designs carry it as an assumption - set it from your fairing. The Trajectory tab and the report show
the build-up term by term against Mach number.

**Did it reach orbit?** The Trajectory tab opens with the answer. The inertial state at the end of the last burn gives the
orbit, from two-body energy and angular momentum. Its perigee and apogee are shown beside the ones you asked for, with one
of three verdicts: *reached*, *in orbit but short of the target*, or *not in orbit*. Two thresholds decide the verdict and
both are assumptions, not standards: an apsis counts as reached within the larger of 10 km and 2 % below its target, and a
perigee under 100 km is not an orbit. The check is not made when `last_ascent_stage` stops the ascent early.

**Events timeline.** Below it, the ascent in time order: lift-off, pitch kick, Mach 1, maximum dynamic pressure,
peak acceleration, and every ignition, burnout and jettison, with altitude, downrange, speed, Mach number, flight
path angle, dynamic pressure and mass. A coast and second burn are in it too.

The book's Titan II curve is still available as `book_titan2`: Fig. 6.13 prints it as analytic equations (exact,
not read off a plot), and until v1.1 every design was flown on it whatever its shape. `table` flies your own
data: put the Mach numbers in `mach_table` and the drag coefficient at each in `cd_table`. The design ships with the
Titan II curve sampled at eight points as a placeholder to overwrite. Cd is interpolated between your points and
held beyond the first and last. `constant` uses one Cd (`constant_cd`) at every Mach number; no real vehicle
behaves like that, and it is there for reproducing hand calculations and for sensitivity checks.

**Atmosphere**: `book_exponential` (Eqs. 6:50/6:53, h0 = 7.64 km) by default. The book's model has no
temperature, so it cannot give a speed of sound, and the book's own Cd curves are functions of Mach — the speed
of sound therefore comes from the US Standard Atmosphere 1976, marked supplementary. `us76` uses that standard
throughout.

**What it cannot fly** is a stage that falls faster than it gains speed. Several check vehicles *as this tool sizes them* are
in that class (Delta II, Atlas V 551, Ariane 64, Ariane 5 ECA: second stages of 12 to 30 minutes at a thrust-to-weight of 0.16
to 0.27). Their real counterparts, flown on their published masses, reach orbit, so the fault is in the sizing, and the
message says what to change. `mission.last_ascent_stage` ends the ascent with an earlier stage, if you want only that.

**Not modelled:** wind, lift, attitude dynamics, plane changes, an apogee burn for a geostationary orbit, engines shut down
in flight, and propellant lost between two burns. One kick and one linear tangent arc is close to the best a vehicle can do
and is not an optimal-control solution. A liquid last stage is assumed able to restart once; use `direct` for one that
cannot.

### 7.6 Trade studies and design comparison in the GUI

The **Trade & compare** tab runs the same two things the `trade` and `compare` subcommands do, and shows the
table `studies.to_rows` builds for the CLI and the report, so the browser never forms a second opinion about
which columns matter.

* **Trade study** — any YAML in `examples/`, `designs/` or `config/` carrying a `trade_study:` block is offered
  in the dropdown. The sweep sizes a complete vehicle per case, so a large grid takes a while.
* **Compare designs** — ctrl-click or shift-click two or more designs. They are sized as they are declared,
  which means **payload fraction is only a fair comparison when the missions match**; the notes under the
  table say so whenever the designs differ.

A case that does not converge keeps its label and its reason rather than being dropped, so a sweep never looks
smaller or healthier than it was. Each run also writes its own `.csv` and self-contained `.html` beside the
run, named under the tab.

The **Report** tab has a **Download PDF** button, which converts the same HTML the tab is showing using
headless Chrome, Edge or wkhtmltopdf. With neither installed it says so and does nothing else: the HTML report is
self-contained and carries its own A4 print stylesheet, so any browser will print it.

### 7.7 Sensitivity

The **Sensitivity** tab. Each case re-sizes the whole vehicle with one input changed, so what it reports is
the converged effect and not a derivative: payload mass, specific impulse, the inert mass-growth margin, the
delta-v requirement and its margin, staging delay, propellant densities, loading margin, stage-1 diameter and
the tank mass model, plus a configuration comparison. A case that does not converge keeps its row and its
reason rather than disappearing, so a study never looks healthier than it was.

It sizes the vehicle dozens of times, so it takes appreciably longer than a single run. These studies have
always run in the CLI (on by default, `--no-sensitivity` to skip) and appeared in the Excel workbook; until
v0.23.1 they had no way in from the browser.

Still command-line only: `import-vehicles`, which turns a CSV or JSON vehicle sheet into design files.

### 7.8 Drop zones (hidden)

> **Hidden at present.** The Drop zones tab is not offered in the GUI. Its map has no coastline, so it cannot say whether
> an area is over land, and an area drawn on a map looks more certain than it is.

The calculation is still in the program, as `hazard.areas()` in Python, with KML and GeoJSON export. It flies each spent
stage, fairing and strap-on from where it separates to the ground and gives an impact point with a spread. **It is not a
range-safety product and must not be used to clear an area.** [`DROP_ZONES.md`](DROP_ZONES.md) has the method and the
error budget. The launch-site longitude is read by this study and by nothing else, so its field is hidden too.

### 7.9 Ground and flight loads

```bash
python -m launch_vehicle.main run --design config/default_design.yaml --out outputs --loads
```

`--loads` implies `--trajectory`, because the flight cases are taken from the flown ascent. It computes what the
structure has to carry, at up to five conditions: the two the book works in full — **on the pad in a ground
wind** and **in flight at max-q** (p.557) — plus **lift-off**, **max-qα** and **maximum axial acceleration**,
which the book lists among its load cases but does not work.

**Ground wind** (book Sec. 9.1.5). The vehicle is clamped down, tanks full and *unpressurised* — the critical
ground condition, because without internal pressure the allowable shell stresses are lower. The Eastern Test
Range wind profile and the drag it produces:

```
v_ss = (9.5 m/s)·h^0.2                Eq. 9:20     steady wind at height h above the ground
v_R  = 2.85·v_ss                      Eq. 9:22     effective speed: vortex shedding plus gusts
q    = ½·(1.2807 kg/m³)·v_R²          Eq. 9:23
D_i  = 0.77·q·A_side,i                             at each segment's side-area centroid
```

Set `mission.pad_height_m` if the vehicle stands on a tall launch mount: the wind grows with height above the
*ground*, not above the nozzles. Axial load is the running weight above each station at 1 g. Shear and bending
moment both peak at the hold-down plane, where the vehicle is a cantilever.

**Flight at max-q** (book Sec. 9.1.6, recipe pp.573–574). A horizontal gust from the book's fit to the Atlantic
Missile Range 95 % wind envelope (p.572) forces an angle of attack α = atan(v_wind/v) on the vehicle. Each
tapering segment then carries a normal force and an axial force, which are rotated into body axes; the engines
gimbal to trim the resulting moment about the CM; the lateral acceleration that produces is applied back as
d'Alembert inertia relief at every mass:

```
N_i = CNα·α·q·ΔA_i     D_i = 0.7·q·|ΔA_i|            ΔA = π(D²−d²)/4, signed
V_i = L_i cos α + D_i sin α     A_i = D_i cos α − L_i sin α      Table 9.8
F_gimbal from ΣM about the CM = 0        n_z = F_lat/(m·g0)      n_x = (T−D)/(m·g0)
```

Both **max-q** and **max-qα** are computed, because the book states outright that which of the two governs
cannot be known before a trajectory exists (p.572). On the default design max-qα comes 7 s earlier and bends the
vehicle 29 % harder.

**Two more cases, for the same reason.** *Lift-off* is the same wind with the vehicle accelerating at its
lift-off thrust-to-weight: identical bending, axial load scaled by n_x. *Maximum axial acceleration* is the
instant of greatest n_x, which arrives at the end of a burn. Whether it governs the axial load is then a result rather than an assumption — and on the default design
it does **not**: at 4.6 g the stage is nearly empty, so there is little mass left above a station to compress
it, and max-q's 2.1 g acting on a much heavier vehicle wins. The report names which case governs axial load and which
governs bending.

**Three self-checks** run on every case and are printed with it. On the ground, the axial curve at the base must
equal the vehicle's weight and the shear must equal the total wind force. In flight, the axial curve must close
on the thrust at the gimbal plane, the shear must close to zero, and the bending moment must be zero at *both*
ends, because a vehicle in flight is a free-free beam (p.606). All of them hold to floating-point noise; if one
ever does not, the numbers in that section are wrong.

**Normal-force slopes.** The default is the slender-body value of 2/rad on the local area change, which is
exactly what the book's subsonic Table 9.7 gives. The book's *supersonic* charts (Figs. 9.38–9.39) are digitised
plots whose origin the book itself says is unknown, so they are not reproduced; against their Saturn V reads at
Mach 1.71 the default under-predicts a nose cone with an afterbody by about 30 % and over-predicts a flare by
29–67 %. If you have chart reads, put them in `mission.aerodynamics.cna_overrides` as
`{name fragment: CNα per radian}`.

**What this is not.** These are global beam loads on the outer shell. There are no shell stresses, no buckling
allowables, no local pressure distributions, no joints or cut-outs, and therefore **no margins of safety**. The
relief that tank pressurisation gives against axial compression is not included — the book defers it to
Chapter 10 — so the axial numbers are an upper bound. Structural masses still come from the MERs and are **not**
re-sized to carry these loads. Strap-on boosters are excluded from the panelling and the trim: they are separate
beams with their own load paths.

### 7.10 Aerodynamic build-up and centre of pressure

Produced with `--trajectory`, at no extra cost. Drag decides what the ascent costs; the **normal** force decides
whether the vehicle can be flown at all. It is built up over the outer mold line panel by panel — a cylinder
carries none to first order (book p.577), so only the changes of diameter matter — and each one acts at the
centroid of its own area change:

```
CNα_vehicle = Σ CNα_i · A_ref,i / Sref          A_ref,i = π(D² − d²)/4, signed
z_cp        = Σ CNα_i · A_ref,i · z_i / Σ CNα_i · A_ref,i
static margin = (z_cm − z_cp) / D   calibers, negative = unstable
Cmα         = Σ CNα_i (z_i − z_cm) / L          positive = a disturbance grows (p.357)
```

The report gives the panel table, the CP against the CM through the whole atmospheric ascent, and the static
margin between them. The default design's worst is about −5.1 calibers: statically unstable throughout, which is
the normal state — *"Most space launchers have no fins and are unstable, so some sort of stabilizing system is
required to keep the vehicle from diverging from its trajectory"* (p.357). The gimbal angle needed to hold it
is in the loads section; how fast an uncontrolled disturbance would diverge is a control question this tool
does not answer.

**Read Cmα, not the static margin, when reverse tapers are involved.** Static margin divides by the total
normal-force slope. A boattail contributes a negative slope, so a large enough one drives the total through
zero, and the centre of pressure runs off to infinity and changes sign while the vehicle has not changed at
all. Cmα never divides by anything and stays correct. The build-up flags when the CP is not to be trusted.

**What it leaves out.** Cylinders are taken to carry no normal force, which is the book's own first-order
assumption but omits viscous crossflow. That acts over the whole body, most of which is behind the nose, so
leaving it out puts the CP **further forward than it really is** and the margin is pessimistic by an amount
this tool cannot quantify. The slender-body slope is Mach-independent, so the CP does not move with speed;
supply chart reads through `mission.aerodynamics.cna_overrides` if you have them. No fins, boosters or
protuberances.

### 7.11 Optimising the pitch programme

```bash
python -m launch_vehicle.main run --design config/default_design.yaml --out outputs --optimise-ascent
```

The book poses this problem in §6.7 and declines to solve it: *"The mathematics behind the theory of
optimization is relatively complicated and will not be presented here"* (p.383). What it does give is the
trade, in §6.10:

> Climbing vertically produces gravity loss, so try to get horizontal as soon as possible to minimize this.
> A shallow climb produces significant drag loss, higher aerodynamic loads, or even overheating, so don't go
> shallow or level off too soon.

Every flight already solves its steering and searches its pitch kick (§7.5). Two things are left: how long the vehicle rises
vertically, and the altitude at which the gravity turn hands over to steering. Both are searched, with the vehicle's limits
enforced. The objective is the speed in hand at the end.

**A limit usually decides the answer.** Steering over earlier trades gravity loss for steering loss at a profit almost all the
way down. What stops it is the vehicle: dynamic pressure, the product qα that sets air loads, and axial acceleration. Those limits live in the design's `constraints` block:

| Key | Default | Where it comes from |
|---|---|---|
| `max_dynamic_pressure_Pa` | 44,000 | Fig. 9.36, the book's generic LV at 920 lbf/ft² |
| `max_q_alpha_Pa_deg` | 331,800 | Fig. 9.36, (qα)max = 6,930 lbf·deg/ft² |
| `max_accel_g` | 6.0 | the existing payload-environment limit |

**Those defaults are observed values, not certified limits.** They are what the book's own example vehicle
reached, and they decide the answer — change them and the optimum moves. For comparison the book gives Saturn V
at 35.2 kPa, the Shuttle's high-q profile at 33.3 kPa, and Pegasus at 66.9 kPa, which it flags as high enough
to cost 322 m/s of drag loss. Set them to your vehicle's numbers. With none set, the search runs to the edge of
its box and the report says the result means nothing.

**What the answer is worth** is priced in payload: the vehicle is flown heavier and heavier, everything else frozen, until no
speed is left over. On the default design's own 44/56 split the optimised programme is worth +41 m/s and +243 kg of payload,
with the optimum pinned to the qα limit and the hand-over at 14 km. That is the value on the vehicle *as built*.

**One result worth knowing before you tune anything.** With the kick searched again, the vertical rise time barely matters;
the kick simply moves to compensate. The hand-over altitude is the parameter that actually does something.

### 7.12 Static stability and control authority

Produced with `--trajectory`, alongside the centre-of-pressure build-up of §7.10. A finless launch vehicle is
statically unstable, so the question is never whether it is stable but whether the engines can hold it.
Chapter 12 gives three numerical rules of thumb, all evaluated at the *worst* instant of the atmospheric
ascent, not on average:

| Check | Limit | Source |
|---|---|---|
| Controllability ratio M_δ/M_A | ≥ 2.0 | §12.3.6 rule 1 — "typically > 1, although values less than ½ have been observed in Delta III vehicles" |
| Time to double, T₂ = ln2·√(I_y/M_A) | > 0.5 s | Eq. 12.4 and rule 2 — below it "very fast actuators are needed" |
| Steady-state gimbal deflection | ≤ 2° | §12.3.6 rule 3 — "provides margin for steering and wind corrections" |
| Total deflection budget (RSS) | ≤ actuator travel | Table 12.4 |

M_A is the aerodynamic pitching moment the gust-induced angle of attack produces about the CM, from the §7.10
build-up; I_y and the CM come from the mass ledger drained to the mass the trajectory had; the moment arm runs
from the gimbal plane to the CM and grows as the first stage empties. The default design passes all four, with
a time to double of 3.5 s — comparable to the Saturn V's 3.31 s at max-q, which the tests reproduce from
the book's own printed inertia and moment.

Only the first line of the deflection budget is the vehicle's own. The other four contributors are the book's
Table 12.4 figures for one NASA solid-Saturn study, used as stand-ins, and they are not requirements for your
design.

**Not assessed: slosh, body bending, tail-wags-dog, POGO.** Chapter 12 describes all four and declines to model
the first — *"The sloshing situation can get very complicated, and analytical analysis is beyond the scope of
this book"* (p.778) — and gives no equation for the others. There is no slosh frequency here, no bending mode
and no root locus, because there is nothing to implement rather than invent. Rule 9 asks for a factor of ten
between the control bandwidth and the structural frequencies; the bandwidth is reported, the structural
frequencies are not computed, so that separation cannot be checked.

### 7.13 Shell stress, buckling and required thickness

```bash
python -m launch_vehicle.main run --design config/default_design.yaml --out outputs --structure
```

`--structure` implies `--loads`. Chapter 9 produced loads; Chapter 10 turns them into stresses and into the wall
thickness each shell needs. Four requirements per shell per load case:

```
axial     t = FS/σ_allow · [ P/(2πR) + M/(πR²) − R(p + ρ g0 n_x h)/2 ]      Eq. 10.43, floored at zero
hoop      t = FS · R (p + ρ g0 n_x h) / σ_allow                            Eq. 10.44
buckling  applied = σ_c = [9(t/R)^0.6 + 0.16(R/L)^1.3 (t/R)^0.3            Eqs. 10.45–10.46,
                           + min(0.191 (p/E)(R/t)², 0.229)] E t / R           solved numerically
gauge     t ≥ 0.50 mm                                                      Table 10.2, aluminium skin
```

The reported thickness is the largest of those over every case. Tapering segments also get the NASA SP-8019
frustum criterion, P/P_cr + M/M_cr = 1 (§10.3.1.1), evaluated at the small end.

**Two rules decide most of the answers.** Ground loads carry **no tank pressure** — the book is explicit
(p.650), the pad case is run unpressurised "in case of an emergency requiring depressurization" — so on the pad
the tanks get neither the axial relief nor the stabilisation pressure gives them in flight, and that is usually
what sizes them. And minimum gauge wins wherever the loads are small: on those pieces what you can buy and weld
sizes the structure, not the flight.

**Buckling sizes nearly everything**, which is the expected result, not a bug. The book's own example tanks
buckle at 288–364 psi — "hardly anything" (p.637) — orders of magnitude below their strength.

**The mass comparison is the useful output.** The sized monocoque shells are put beside what the Chapter 8 mass
relationships carry for the same hardware. On the default design that is 12,908 kg against 5,708 kg, a factor of
2.26. Neither number is wrong: the relationships are fitted to real vehicles, real vehicles are not monocoque,
and the gap is the mass that rings, stringers, waffle and isogrid buy back. It is **not** a correction to apply
— nothing here is fed back into the vehicle, so the masses in the mass statement are still the MER ones and the
vehicle in the report is not the vehicle that was analysed.

**What is not sized.** Monocoque shells only. §10.3.3 lists the ways to beat buckling — honeycomb sandwich, ring
frames, stringers, isogrid, orthogrid — but gives no allowables or mass-per-area laws for any of them and points
at NASA CR-124075 for isogrid. Sizing them would mean inventing numbers. Also absent: domes and bulkheads,
joints, welds, cut-outs and local reinforcement, thermal stress, fatigue and fracture, acoustics and vibration,
and the combined stress state — which the book also sets aside ("beyond the scope of this book", p.649). The
payload fairing is skipped entirely: it is a composite sandwich sized by an areal-mass relationship, and running
it through an aluminium monocoque criterion would produce a number with nothing behind it. Shear is computed and
reported but sizes nothing, following Example 1b where it needs a twentieth of minimum gauge.

**The margins are margins on an assumption.** The installed thicknesses this is checked against are the design's
own geometry assumption — the tank masses come from a relationship, which never produces a thickness. The
*required* thicknesses are the result worth reading.

### 7.14 Solid motor internal ballistics

```bash
python -m launch_vehicle.main run --design examples/example_solid_smallsat.yaml --out outputs --ballistics
```

Every solid stage is sized on one thrust held for the whole burn. A grain does not deliver that. Three book
relations close the loop:

```
r    = a·P_c^n              Eq. 4:32, de Saint Robert's law
ṁ    = ρ·A_b·r              Eq. 4:33
ṁ    = P_c·A_t/c*           Table 4.4
⟹   P_c = [ρ·a·c*·(A_b/A_t)]^(1/(1−n))
```

whose exponent is the book's own stability argument: below n = 1 a disturbance settles, above it "a small
decrease in chamber pressure could result in a catastrophic drop in burn rate" (p.231). n ≥ 1 is refused rather
than solved.

**The result on the example vehicle.** A plain cylindrical bore is *progressive* — its burning surface grows as
it regresses — so thrust climbs 5× through the burn and chamber pressure reaches 11.1 MPa against a 6.0 MPa
design, which the casing was not sized for. That is exactly what the book predicts ("a cylindrical cutout will
produce thrust levels that increase with time", p.233) and it is the finding, not an error: the constant thrust
the sizing assumed needs a cog or double-cylinder grain, which Fig. 4.12 draws but never dimensions.

**Where the numbers come from.** The exponent n is in the propellant library (the book gives the range 0.4–0.7
but no value for any propellant, so it is tagged as an assumption); c* is Table 4.7's 1,577 m/s; the throat area
is Eq. 8:28. The burning-rate coefficient `a` is **not** assumed — it is solved for so each motor reaches its own
design chamber pressure at its mean burning area. That makes these curves a statement about the grain shape
rather than about a propellant this tool has no measured data for, and it is why the delivered burn time and
total impulse differ from the sized ones.

**Not modelled.** Only the two grain shapes the book describes completely: end burner and hollow cylinder. Star,
cog and finocyl are not offered. Also absent: erosive burning (described on p.231 without an equation), ignition
and tail-off transients, the factor-of-two burn-rate variation with grain temperature the book reports on p.233,
and any re-sizing of the casing for the peak pressure found.

### 7.15 Cost

```bash
python -m launch_vehicle.main run --design config/default_design.yaml --out outputs --cost
```

In the GUI, pick **Cost** in Analyses; a **Cost** tab then appears with the results. Everything is in work-years first,
because those do not change with inflation or currency, with dollars beside them.

| Code | Development effort | Mass basis |
|---|---|---|
| ES | H = 16.3 M^0.54 | solid motor net mass |
| EL | H = 277 M^0.48 | **one** turbopump engine's dry mass |
| EP | H = 167 M^0.35 | **one** pressure-fed engine's dry mass |
| VR | H = 10.4 M^0.60 | one solid booster's net mass (from 10 t; ES below) |
| VS | H = 100 M^0.555 | stage dry mass **without** engines; the first liquid stage also carries the fairing and adapter |

These are the book's (Figs. 17.12-17.16). The factors, production, learning and operations come from the handbook the
book defers to: Koelle, *Handbook of Cost Engineering*, TRANSCOST 7.2 (2007).

**On the tab you can set** where the vehicle is developed (productivity f8), launches per year, number of flights,
years to first flight, share of the payload sold, assembly mode and cost year; and for each element f1 (development
status), f2 (technical quality, stages and engines), f3 (team experience) and whether it is **already developed**, which
charges no development. Changing one re-costs at once without re-sizing, and Save keeps them under `mission.cost`.

**The factors dominate the answer.** With all of them neutral the engine relation misses Koelle's ten engines by
between 34 % low and 100 % high. Hover over a box for his guidance. f2 of a liquid stage is computed from its net mass
fraction; clear the box to go back to that.

**Cost per flight** is one vehicle's production averaged over the programme, plus ground and mission operations, plus
11.5 % indirect. It is a cost under conventional methods and not a price.

**How good is it?** [`COST_VALIDATION.md`](COST_VALIDATION.md), written by `tools/validate_cost.py`: the relations
reproduce Koelle's worked examples; Saturn V and Ariane 5 development come out within 6 % with single parts up to 41 % off;
cost per flight is 1.7 times his tables at the median of 13 vehicles.

### 7.16 Payload environment

```bash
python -m launch_vehicle.main run --design config/default_design.yaml --out outputs --payload-env
```

`--payload-env` implies `--trajectory`. This is what the spacecraft customer is handed: a table of design load
factors by flight event, axial and lateral, in the format of the two real payload planners' guides the book
prints (Ariane 5's Table 11.3 and Atlas V's Table 11.4), both of which the report shows beside it.

The **steady** half is computed — axial from the flown trajectory, lateral from the Chapter 9 flight trim. The
**dynamic** half is not: a published QSL is the worst combination of dynamic and steady acceleration, and the
dynamic part comes from a coupled-loads analysis of the vehicle and spacecraft together, which needs structural
modes this tool does not compute. The increments used are taken from those two real guides and are labelled as
stand-ins on every row.

The default design comes out at 5.6 g axial (stage-1 burnout) and 2.0 g lateral, inside the book's
expectation of 4–8 g and 1.5–3 g for a preliminary design.

**What a real guide has that this does not:** the acoustic and shock specification (Chapter 11 describes
ignition overpressure, lift-off acoustics, buffet and pyrotechnic shock without a prediction method for any —
of ignition overpressure it says it "is difficult to estimate"), and the frequency requirement (§11.5.3 asks for
spacecraft modes at least twice the vehicle's, and the vehicle's are not computed here).

### 7.17 Trade studies and design comparison

Two commands that run the whole tool over more than one vehicle.

```bash
# a sweep declared in YAML
python -m launch_vehicle.main trade --study examples/example_trade_study.yaml --out outputs/trade

# several designs side by side
python -m launch_vehicle.main compare --designs config/default_design.yaml examples/example_3stage_leo.yaml     --out outputs/compare
```

A trade study names the base design, the parameters to sweep and how to combine them:

```yaml
trade_study:
  name: Stage 1 diameter and mixture ratio
  design: config/default_design.yaml
  mode: grid                      # grid | one_at_a_time
  sweep:
    - path: stages.0.diameter_m
      values: [3.6, 3.8, 4.0, 4.2]
    - path: stages.0.mixture_ratio_OF
      values: [2.3, 2.5, 2.7]
```

Paths are the same dotted paths the sensitivity studies use, applied to the design file as written; an unknown
one is refused. Both commands write a CSV, a chart and a small self-contained HTML page.

**Failures stay in the table.** A 3.6 m stage 1 cannot fit its engines and raises ENGFIT; that row appears with
its error rather than disappearing, because a sweep that silently discards its failures looks better than it is.
One unreadable file or one bad parameter path costs its own row and nothing else.

**Read the spread against the uncertainty.** Every row is a full sizing run and carries the same uncertainty a
single-design run does — the Monte-Carlo study puts that at tens of per cent on GLOM. The diameter sweep above
moves GLOM by 0.4 %. A trade whose spread is smaller than the model's own uncertainty is telling you about the
model, not about the vehicles, and the generated page says so.

### 7.17b Architecture trades: pin the stages, change the strap-ons

The question this answers: *take this vehicle's core and upper stage exactly as they are, fit a different
number of strap-ons, and what does it lift?* That is how a launcher family is actually marketed — one core,
several booster counts — and it is the trade a user manual's first page is built on.

```bash
# Ariane 64's stages, pinned, with 1 to 5 P120C instead of 4
python -m launch_vehicle.main architecture --design validation/ariane64.yaml --boosters 1 2 3 4 5

# the reverse: hold the booster set and let the sizing loop re-size the core for it
python -m launch_vehicle.main architecture --design validation/h2a_202.yaml --size-core --boosters 2 4 6
```

```
VAL-Ariane-64: stages and the P120C unit PINNED at the design's values, booster count varied
   as designed: 4 booster(s), 15,500 kg payload, 779,654 kg GLOM

   n   payload kg       GLOM kg    T/W   vs design  note
   1        7,690       312,309   1.17      -7,810
   2       10,910       468,754   1.34      -4,590
   3       13,428       624,444   1.43      -2,072
   4       15,509       779,664   1.48          +9  as designed
   5       17,282       934,552   1.52      +1,782
```

What is held and what moves. Every stage keeps its loaded propellant and the split of it into mission,
start-up, residual and loading margin; its dry mass; its effective Isp; its mass flow. The strap-on keeps its
*unit* design — propellant, inert mass, mass flow, Isp, burn time. Only the count and the payload move. The
payload is the root of achieved Δv = required Δv, found by the same bisection the performance curves use.

**The parallel burn is re-solved, which is the whole point.** The performance sweeps of §7.x carry the parallel
phase as one stored number taken from the reference design, and say so. On Ariane 64 that number is about
**−2,900 m/s** — it is not a contribution but the difference between the serial rocket equation applied to the
core and the phase model's answer for the same stage. It is a property of *four* boosters. This command
re-solves the phase sequence for whatever count you ask for, so the answer is valid away from the reference.
At the reference count it reproduces the sizing loop's per-stage Δv to one part in 10⁹.

Two kinds of refusal, and neither returns a number:

| | |
|---|---|
| **Lift-off T/W ≤ 1** | The stack weighs more than it pushes. Ariane 64's hydrolox core alone gives 983 kN against 1,518 kN of weight, so `--boosters 0` reports that and no payload. The Δv-feasible payload is kept in a separate field, never under the name `payload_kg`, so nothing can read it as a capability. |
| **Boosters outlast the core** | An air-lit group makes the core burn alongside strap-ons for a second interval. The phase model's own message says how much propellant short the core is, and offers the burn time or the per-booster load that would fit. |

Ignition split. A design that lights every booster on the ground gets every booster lit on the ground at any
count. A design that really does stage its ignition — Delta II 7920, six on the ground and three in the air —
keeps its ground-lit *count*, capped at the total, which is why its lift-off T/W peaks at six boosters and
*falls* after: boosters past the sixth are mass at lift-off and no thrust. Override with `--ground-lit`.

**How accurate this is, measured.** Pinning inherits the core-sizing error of whichever design you pin, and
against the two families that publish a payload for several counts of one core it over-predicts the smaller
variants:

| pinned core | asked for | published | tool | error |
|---|---|---|---|---|
| Delta II 7920 | 3 × GEM-40 | 2,800 kg | 3,436 kg | +22.7 % |
| Delta II 7920 | 4 × GEM-40 | 3,200 kg | 3,820 kg | +19.4 % |
| Ariane 64 | 2 × P120C | 7,200 kg | 10,910 kg | +51.5 % |

So: one booster either side of the reference count is the useful range; two or more away, read the direction
and not the number. `docs/ACCURACY.md` §6b.5 gives both causes and says why no correction is fitted. Use
`--size-core` when the core is not yet built — nothing is pinned there, so none of this bias applies.


### 7.17c Launch vehicle families

A family is a folder with a `family.yaml` in it. Real launchers are sold this way — one core, several
strap-on counts, a published figure for each — and it is also the one configuration where this tool's hardest
limitation can be measured instead of argued (`docs/ACCURACY.md` §6b.6).

```bash
python -m launch_vehicle.main family                              # every family found
python -m launch_vehicle.main family --name delta_ii --pinned     # size it, and pin its reference core
```

```
Delta II 7000 series  -  3 variants, base validation/delta2_7920.yaml

Each variant sized on its OWN, delta-v split re-optimised:
  variant                              tool GLOM   published      err
  Delta II 7320 (3 x GEM-40)             136,843     152,000   -10.0%
  Delta II 7420 (4 x GEM-40)             150,764     162,000    -6.9%
  Delta II 7920 (9 x GEM-40, 6+3)        231,365     228,000    +1.5%  <- reference

Reference variant (7920) PINNED, booster count changed (method M102):
  Delta II 7320 (3 x GEM-40)               3,446       2,800   +23.1%
  Delta II 7420 (4 x GEM-40)               3,830       3,200   +19.7%
  Delta II 7920 (9 x GEM-40, 6+3)          5,100       5,100    +0.0%  <- reference
```

Those two tables err in **opposite directions** from one cause, and reading them is the point of the feature:
the tool never carries a core that is oversized for the mission being flown, so sizing each variant alone
gives it too small a core and pinning the reference variant's core pins one still smaller than the real
shared one. §6b.6 has the mechanism.

#### Making your own family

Put a folder under `designs/families/`, `examples/families/` or `validation/families/` and write a
`family.yaml`. There is nothing to register — the tool finds it.

```yaml
family:
  name: My booster family
  note: what the variants share, in one line
  base: ../../my_vehicle.yaml      # relative to this manifest; every variant starts from this design
  reference: "big"                 # the variant whose hardware an architecture trade pins
  variants:
    "small":
      label: My vehicle, 2 boosters
      overrides:                   # the same dotted paths the sensitivity studies and the GUI use
        boosters.n_total: 2
        boosters.n_ground_lit: 2
        mission.payload_mass_kg: 1200.0
      published:                   # OPTIONAL, and annotated like every other sourced input
        payload_kg: {v: 1200.0, u: kg, d: Published payload, s: where this came from, t: reference}
        glom_kg:    {v: 95000.0, u: kg, d: Published lift-off mass, s: where this came from, t: reference}
    "big":
      label: My vehicle, 4 boosters
      overrides:
        boosters.n_total: 4
        boosters.n_ground_lit: 4
        mission.payload_mass_kg: 2600.0
```

Three things are worth knowing about the format.

**A variant is the base design plus overrides, never a copy of it.** This is deliberate. Writing each variant
as a standalone YAML would duplicate hundreds of lines and let the "shared" core drift apart one edit at a
time — the family property would be an aspiration. Here the variants literally load the same file, so change
the base and every variant changes with it. The shipped Ariane family is checked for exactly this: a test
asserts that the A62 expressed as overrides on the A64 sizes to the same vehicle as the separately shipped
`validation/ariane62.yaml`, to one part in 10⁹.

**`published:` is optional, but if present it must be sourced.** Every figure under it carries the same five
documentation keys as any design input, and `t` must be `reference`. A figure marked `assumed` is refused with
a message saying why: a validation set that accepts an assumption as a published value starts grading itself
against its own guess. Leave `published:` out and the family is a convenience for comparing variants; put it
in and the family measures the tool.

**`name`, `label`, `base`, `reference` and the override paths are plain YAML**, the way `meta:` and
`trade_study:` are, because they are structure rather than engineering inputs.

Errors name the problem: a base design that does not exist, a reference that is not one of the variants, a
single-variant "family", an override block that is not a mapping, and each of the five ways a published
figure can be inadequate.

#### In the GUI

> **Hidden since v1.1.** The tab is not in the tab bar at present, at the owner's request: its lower half lists
> every family file on disk whatever design is open, which is confusing. The command line (`architecture`,
> `family`) still does all of this. What follows describes the tab as it is when shown.

The **Architecture & families** tab holds both halves. The upper half pins the open design's stages and
sweeps the strap-on count (§7.17b), with **Re-size the core instead** for the opposite question. The lower
half finds families, sizes one, and optionally pins its reference core — and the measured-bias caveat is
served with the numbers rather than kept in this manual, because a payload table shown without it reads as a
capability.


### 7.18 CAD export

```bash
python -m launch_vehicle.main run --cad                      # adds outputs/cad/ and an isometric view
python -m launch_vehicle.main run --cad --cad-facets 128     # smoother meshes, larger files
```

Five things come out of `--cad`, and none of them needs anything installed:

| File | What it is |
|---|---|
| `cad/vehicle_profile.dxf` | Layered DXF R12 inboard profile, in metres |
| `cad/vehicle.stl` | Outer mould line as a binary STL triangle mesh |
| `cad/vehicle.obj` | The same mesh as Wavefront OBJ, which keeps the part names STL cannot |
| `cad/vehicle.3mf` | The same mesh as 3MF, which keeps the part names **and** records its unit |
| `isometric_view.png` | Isometric render of those meshes, also placed in the report's Drawings section |

**Prefer 3MF over STL.** They carry identical triangles, but STL records no unit at all — every
consumer has to guess whether your 70 m vehicle is 70 mm or 70 inches — and it has no concept of a
part, so the airframe, the nozzles and the strap-ons arrive fused into one anonymous shell. 3MF is a
zip of XML with `unit="meter"` declared in it and one named object per part, and it compresses to
about an eighth of the STL's size. It is written from the 3MF Core Specification directly; the only
reason STL is still the default name people reach for is age.

The DXF layers are `LV_OML` (the one closed silhouette), `LV_STATION`, `LV_TANK`, `LV_GRAIN`, `LV_ENGINE`,
`LV_BOOSTER`, `LV_PAYLOAD`, `LV_AXIS`, `LV_TEXT` and `LV_DIM`, so you can switch off the annotation and keep the
geometry. Coordinates are metres with the vehicle vertical and `z = 0` at the first-stage nozzle exit plane,
matching every other drawing and table in the tool.

The mesh is **the outer mould line, not a solid model of hardware**. The parts are kept separate — airframe, one
per nozzle, one per strap-on — each individually watertight; they are not booleaned into one solid, which needs
a CAD kernel, and they overlap where a nozzle sits inside an aft skirt. A revolved surface is polygonal, so its
volume falls short of the true body of revolution by about **0.16 % at the default 64 facets** (the deficit goes
as `(2π/n)²/6`); do not take a mass off the exported solid without allowing for that.

#### 7.18.1 Exact solids: STEP and BREP, if you install a kernel

A faceted mesh is not a solid model. You cannot section it, you cannot measure a radius off it, and
its volume is low by the 0.16 % above. What a structures or GSE engineer wants is STEP: exact
cylinders and cones with a part tree. That needs a geometry kernel, so it is **optional**:

```bash
pip install cadquery        # brings in cadquery-ocp, a large OpenCASCADE binary wheel
```

With it installed, `--cad` adds `cad/vehicle.step` — exact B-rep solids, one named and coloured part
per mesh part, so the CAD tree reads like the DXF layers. `--cad-formats step,brep,gltf` picks which
of the three the kernel writes. Without it, nothing changes and nothing fails: the five files above
are still written, and the GUI greys out the solid buttons with the reason in their tooltip.

The kernel route asks the kernel only for what it alone can do. It deliberately does **not** re-export
STL or 3MF through CadQuery: our meridians are piecewise linear, so the only curvature in the body is
circumferential and `--cad-facets` already controls that exactly — a kernel tessellation of the same
shape is not a better mesh, and two routes writing one file name means one of them is unreachable.

**How much to trust it.** The author of this tool could not install CadQuery — the environment it was
written in has no network at all — so **no call in that module has ever reached a real OpenCASCADE
kernel**. Rather than hand you that uncertainty, the module checks itself on your machine: every solid's
volume, as the kernel computes it, is compared against a closed-form frustum sum that involves no kernel,
and against the bounding box the profile implies. A solid that disagrees by more than 1 part in 10⁶ is
never written — the export raises instead. So the failure mode of a wrong API convention is a loud,
specific error, not a plausible STEP file with the wrong geometry in it. To see that check for yourself:

```bash
python -m launch_vehicle.main run --verify-kernel --no-report
```

which prints each part's closed-form volume beside the kernel's and writes nothing.

**What is checked without a kernel**, and what is not: mesh volumes against the exact closed form for a
faceted solid of revolution, every edge shared by exactly two oppositely-wound triangles, the 3MF
unzipped and re-parsed against the specification's structure, winding and unit rules, and the DXF parsed
back by an independent group-code reader. **None of that proves the files open correctly in a CAD
application, and that has not been tested** — no export from this tool has been opened in any commercial
CAD package. If you hit a problem opening one, that is the gap, and it is a real one.

---

### 7.19 Importing vehicles from public sources

```bash
# write a blank sheet with every understood column
python -m launch_vehicle.main import-vehicles --template my_vehicles.csv

# turn a filled-in sheet into annotated design YAML
python -m launch_vehicle.main import-vehicles --sheet examples/example_vehicle_sheet.csv       --out validation/imported --report
```

One row per vehicle. Vehicle-level columns (`payload_mass_kg`, `perigee_altitude_km`, `fairing_diameter_m`, …)
and per-stage columns prefixed `stage1_`, `stage2_` and so on, with `stage1_type` declaring `liquid` or `solid`.
Any column may be given its own provenance by adding a `_source` column beside it — `stage1_thrust_to_weight_ignition_source`
— which is how a derived figure gets cited differently from the row's blanket source. A `source` column is
**required**: an imported figure without provenance is exactly what this tool refuses to produce.

Four things are errors rather than defaults, because each one would otherwise be silently wrong:

* a missing `payload_mass_kg` or `perigee_altitude_km`, or a stage with no diameter, no Isp or no thrust;
* `isp_effective_mode: user` without `isp_effective_user_s` — inheriting another vehicle's effective Isp here is
  invisible once it is in the file;
* a column that is filled in but not understood, including a solid field on a liquid stage;
* `n_stages` disagreeing with the stage columns actually filled in.

**What an import does not give you.** Public sources publish payload to a stated orbit, diameters, engine counts,
thrust, Isp and propellants. They do not publish stage dry masses, propellant masses, tankage, pressures,
materials or engine envelopes — and those stay at the base design's assumed values. That is the point: the tool
*predicts* them, which is what makes an imported file a validation case rather than a datasheet. The import
report says how many leaves came from the source and how many did not, and `--report` lists them.

**Absolute mass assumptions do not scale — this is the one to watch.** A stage template cloned from
`config/default_design.yaml` brings its kilogram constants with it: 100 kg of other equipment, 60 kg of
separation hardware and 25 kg per engine of feed system, per stage. On a Falcon 9 that is noise. On an
Electron it roughly **doubles** the inert mass, and the imported vehicle came out 2.0× the hand-written case
until those columns were filled in, after which it came out 1.17×. The importer warns whenever the payload
masses differ by more than 3× and names every carried-over leaf. The fixes are to fill the
`stage{n}_other_equipment_mass_kg`, `_separation_hardware_mass_kg`, `_feed_system_mass_per_engine_kg`,
`_structure_mass_factor` and `_engine_mass_per_engine_kg` columns, or to pass `--base` pointing at a design of a
similar size class.

**Expect an imported vehicle to trip checks, and read that as information.** The shipped Falcon 9 import sizes
cleanly but raises two ERRORs, both inherited rather than imported: `ENGFIT`, because the base design's assumed
engine exit diameter of 1.20 m is a big-engine figure and nine of those will not fit a 3.7 m stage; and
`VEHLEN`, because the 70 m length limit came from the base design while the sized vehicle is 84 m — this tool
over-predicts length by 20–50 % on real vehicles for the reasons in `docs/VALIDATION_REPORT.md` §8. Neither is a
bug in the import; both are the assumed half of the file announcing itself, which is what the checks are for.
Fill `stage{n}_engine_exit_diameter_m` and `stage{n}_engine_length_m` if you have sourced figures, and
`max_vehicle_length_m` from the published height.

**Wikipedia infoboxes: a transcription aid, not an import.** `vehicle_import.parse_infobox` reads
`{{Infobox rocket}}` wikitext, resolves `{{convert}}` templates and links, and converts imperial units — but a
single infobox cell routinely describes several vehicles at once ("FT: 549,000 kg; v1.1: 506,000 kg; v1.0:
333,000 kg"), and any field that does not reduce to one figure is **left out and listed as ambiguous** rather
than guessed. An infobox also carries no payload mass, no orbit and no Isp, so it cannot produce a design on its
own; `build_design` raises instead of filling the gaps from the base vehicle. Use it to transcribe the
unambiguous rows without typing errors, then finish the sheet by hand.

**`launchercalculator.com` has no dataset to import.** It is a calculator you type parameters into — the site
publishes no download, endpoint or API. If you know of a genuinely open launch-vehicle dataset, the importer's
field map is one dictionary and adding an adapter for it is small.

### 7.20 Propellants, mixture ratios and real engines

Three libraries, all in the same `{v,u,d,s,t}` form as everything else, all following the same rule: **they fill
what your design leaves out and never override what it states.**

**Propellants** (`assumptions.propellants`) — 15 entries: LOX, RP-1, LH2, LCH4, N2O4, A-50 and UDMH,
plus propane, MMH, hydrazine, ethanol, methanol and nitromethane from the book's Tables 4.5 and 4.6 (p.238),
plus two grades of high-test peroxide, **HTP-90** and **HTP-98**, as oxidisers.

**Propellant combinations** (`assumptions.propellant_combinations`) — 12 oxidiser/fuel pairs. Name one from a
stage and it supplies the fuel, the oxidiser and the mixture ratio:

```yaml
stages:
  - propellant_combination: {v: "HTP-98/RP-1", u: '-', d: "...", s: "...", t: user}
```

Each entry carries **two mixture ratios, deliberately kept apart**:

| | what it is | why both |
|---|---|---|
| `of_ratio_optimum` | the ratio that maximises Isp, from book Table 4.10 | the thermochemical answer |
| `of_ratio_flight` | what engines of that combination actually run, each one named | what gets used |

They are not the same number. For LOX/LH2 the Isp peak is at O/F 4.02 and the J-2 flew at 5.50 — hydrogen
engines run fuel-rich to hold turbine and chamber temperatures down. `of_ratio_flight` is what a stage gets,
because this tool sizes real vehicles.

The entries also carry the theoretical Isp, c*, chamber temperature and mixture specific gravity, which the
report shows beside your design's numbers. **The reference Isp is never filled into a stage.** Book Table 4.10
is computed at 1,000 psia expanded optimally to sea level, so a vacuum nozzle legitimately beats it — the RD-180
delivers 338 s against the 300 s tabulated for LOX/RP-1. It bounds the chemistry at that condition; it is not a
target and not a vacuum Isp.

Bulk density is **computed**, not read: `(1+r)/(r/ρ_ox + 1/ρ_fuel)` from the same densities the tanks are sized
with, so it cannot disagree with the geometry. Recomputing it reproduces the specific gravity the book prints
for six of its seven rows inside 2 %, and that same check is what independently confirms the Aerozine-50 density
in Table 4.6 is a misprint — see §10.

**Engines** (`config/engine_database.yaml`) — 35 engines and 16 motors. Most engines are the book's own tables: the
eighteen-engine summary in Table 4.14 (p.245), the F-1 (Table 4.11), the J-2 (Table 4.12) and the RS-68
(Table 4.13), alongside the public-source rows already there and three peroxide engines from published papers.
Naming one now also supplies the **propellants and the mixture ratio**, not just the performance:

```yaml
    engine:
      from_database: {v: "RD-180", u: '-', d: "...", s: "...", t: reference}
```

gives that stage LOX/RP-1 at O/F 2.72. An engine row is more specific than a combination, so where both are
named the engine's mixture ratio wins — the shipped peroxide example shows exactly that, its upper stage taking
the RD161P's 5.9 rather than the library's 7.5.

A stage that names an engine and then declares a different propellant is **reported, not silently accepted**
(`COMBOMM`, `ENGDBOVR`): the design always wins, but a vehicle sized on one propellant's density and another's
mixture ratio is almost always a template left half-edited.

**A worked example:** `examples/example_htp_kerolox.yaml` — two-stage HTP-98/RP-1, 2 t to 400 km, using both
libraries together. Two things it demonstrates that are worth knowing before you try peroxide yourself:

* **Table 8.6 has no peroxide row**, so the propellant-mass tank MER cannot be used and the design must choose
  `akin_volume` or `pressure_vessel`. The tool refuses rather than borrowing kerosene's coefficient for a
  1,431 kg/m³ oxidiser — the error names the two methods that do apply.
* **Peroxide is dense**, so the kerosene tank is small. At a 2.4 m upper stage it came out shorter than its own
  end caps and the geometry was refused; the example runs a 1.9 m upper stage for that reason.

### 7.21 Winds aloft: using the launch site's own profile

The book's flight-load recipe (§9.1.6.3 step 4, p.573) says to *"use the launch site's winds-aloft profile"* and
then prints one site's — the Atlantic Missile Range 95 % envelope of Fig. 9.35. Hard-coding that means every
vehicle is designed for Cape Canaveral. A design can now name its own:

```yaml
mission:
  wind:
    profile: {v: "wind_profiles/*.csv", u: '-', d: "...", s: "...", t: user}
```

`profile` takes the built-in name `book_amr_95`, a path, a glob, or a list of paths. CSV and Excel are both
read. Column names are matched loosely — `altitude_m`, `alt_km`, `height_ft` for the altitude and `speed_mps`,
`wind_kt`, `v_kmh` for the speed — and converted to SI. A `direction_deg` column is read and recorded but
**not used**: the load is built from speed alone.

```bash
python -m launch_vehicle.main run --loads --design mydesign.yaml   # uses whatever the design names
```

**Steady wind and gust envelope are not the same input.** This is the distinction that decides whether the
feature helps or silently halves your design load:

| `kind` | what it is | how it is used |
|---|---|---|
| `gust_envelope` (default) | a percentile envelope that **already contains the gust** — the book's AMR curve | fed straight in as the gust speed, as step 4 asks |
| `steady` | a mean wind, a balloon sounding, a range reference atmosphere | the gust rides **on top**, so an explicit `gust_increment_mps` is required |

A file can declare what it is, in `#` comment lines above the header, and that **beats the block's setting**
— so a sounding listed beside an envelope cannot be read as one:

```
# kind: steady
# gust_increment_mps: 9.0
# source: Vandenberg 12 Z sounding, 2026-03-14
altitude_m,speed_mps
0,5.0
...
```

A `steady` profile without a gust increment is **refused**, not defaulted. The book gives no increment for an
arbitrary site, and a number invented here would be indistinguishable from the answer being right.

**One profile is not a design wind.** Real practice is an ensemble: fly many soundings and take the governing
*load*, not the governing *wind*. Give several files and the tool flies all of them, because the worst wind and
the worst load sit at different altitudes for different vehicles — a profile with a lower peak but its shear
where the vehicle is flying fast can govern over a faster one. Each kept case records which profile produced
it, and the report lists everything it was chosen from, so a governing load can never be shown without showing
what it beat.

**What this does not do.** There is no wind in the trajectory integration. The vehicle is not flown through the
profile; the gust is imposed at the altitude the trajectory reached without it, and the angle of attack follows
from `α = atan(v_wind / v)`. Flying the profile would make qα a computed peak rather than an imposed one, and
is a larger change than this.

Shipped examples are in `examples/wind_profiles/`: the book's own envelope tabulated, and a synthetic steady
sounding that says **NOT MEASURED DATA** on its face. To start from the book's curve in your own units,
`wind.write_template_csv()` writes it out as a CSV you can edit.

---

### 7.22 Reading the loads diagram

The loads chart draws the vehicle beside the curves, upright, on the same axis — which is how the book presents
its own load distributions (Fig. 9.26 plots shear and moment against elevation). Stage joints and the fairing
base are ruled across all three panels, and the station that sizes the structure is circled on the bending
panel and named.

**One axial coordinate, everywhere.** `z` is measured **upward from the stage-1 nozzle exit plane** and is the
axis used by the drawings, the mass ledger, the CM-travel plot, the CAD export, the loads diagram and the loads
tables. The book's own tables use *station*, distance from the nose, so that is carried beside `z` in the
detailed per-station table and in the workbook — but `z` comes first and is what every chart is plotted
against. An earlier version plotted the loads from the nose, which put the one diagram you most want to read
against the vehicle on the opposite convention to the vehicle.

---

## 8. Checks, warnings and errors

Three levels appear on the dashboard and in the console:

* **ERROR** — the design violates a constraint or a physical/accounting check (mass closure, delta-v sum,
  tank volume, engine fit, lift-off T/W, length limit, convergence). Treat the result as unusable.
* **WARNING** — something is unusual or an assumption is doing a lot of work (high/low structural factor,
  long burn time, vacuum Isp on an atmospheric stage, aggregate mode, overridden ascent time, air launch).
* **INFO** — always includes the fidelity disclaimer.

Input errors (missing documentation keys, bare values, an inclination below the launch-site latitude, both
thrust modes specified at once, …) raise before any sizing runs, with a message naming the field.

---

## 9. Troubleshooting

| Message | What it means | What to do |
|---|---|---|
| `input '...' is an undocumented bare value` | A leaf is not a `{v,u,d,s,t}` mapping. | Wrap it, with a real source. |
| `required internal volume ... is smaller than the volume of the end caps` | The tank/casing is too wide for the propellant it holds. | Reduce the diameter, use `tank.diameter_m`, or use shallower domes (`dome_aspect_ratio` > 1). |
| `solid motor: even a bore through the whole casing cannot hold the required free volume` | Same problem for a solid motor. | Reduce the motor diameter or the casing volume factor. |
| `infeasible: mu*s >= 1` | The stage cannot reach its allocated delta-v with that structural factor. | Give the stage less delta-v, raise Isp, or reduce inert mass. |
| `unburned-propellant fraction ... leaves no usable propellant` | The allocated delta-v is impossible with the residual/margin fractions. | Re-allocate delta-v (run `optimize`). |
| `the core stage runs out of propellant before booster group ... burns out` | The core burns out during the parallel phase. | Throttle the core (lower thrust), shorten the booster burn, or give stage 1 more delta-v. |
| `ascent time ... far outside the range the regression was fitted to` | A low-thrust upper stage makes the loss model diverge. | Set `losses.ascent_time_override_s` to the powered ascent time to the parking orbit, or use `losses.model: user`. |
| `lift-off T/W ... below minimum` | Thrust too low for the sized mass. | Raise thrust or T/W, or reduce the required delta-v. |
| `engine(s) of exit diameter ... do not fit` | Nozzles do not fit in one ring. | Fewer/smaller engines, a lower expansion ratio, or a larger diameter. |
| `stalled / oscillating` | The loop is not converging. | Lower `convergence.relax` (e.g. 0.5) in the assumptions file, or relax a constraint that is fighting the loop. |
| `max iterations reached without convergence` | Not converged — the result is **not** reported as converged. | Raise `max_iter`, lower `relax`, or fix the infeasibility it is chasing. |

---

## 10. Accuracy: what the validation shows

`docs/ACCURACY.md` measures the tool against 24 real vehicles and attributes each error to its cause. The short
version:

* **All-liquid vehicles** have a median absolute gross-mass error of 13.2 %, over 17 vehicles.
* **Composite solid stages now default to `kibbey_medium`** (since v0.26), a size-dependent NASA relation,
  because the book's casing MER is a flat fraction with no scale term at all — the same inert fraction for a
  141-tonne P120C as for a 215 kg Altair. Measured on the 16 published solid stages at their published
  propellant loads, that change takes mean absolute stage-inert error from **51 % to 23 %** and median bias
  from **+52 % to −8 %**; the solid group's median GLOM error, 33.4 % before, is now **11.5 %** over 7 vehicles, with Vega at
  +0.5 % and Vega C at +4.6 %.

  Two consequences to carry into a design. **Solid estimates are no longer reliably conservative** — Scout
  G-1, Pegasus XL and Epsilon now come out −11.5 %, −17.6 % and −25.2 %, i.e. light, where they used to be
  heavy. And **a steel case must keep `book_steel`**: Kibbey is a composite-era technology level and runs
  45–49 % light on a segmented-steel case (Ariane 5's EAP, Scout's Algol), where the book's steel constant is
  within −2 % to +5 %. The tool does not infer your case material, so set the method to match it.
* **A motor below roughly one tonne of propellant is badly served by every relation here.** Real inert
  fractions climb to 0.16–0.19 at that size (Pegasus's Orion 38 at 770 kg, Scout's Altair at 215 kg) and none
  of the available relations reproduce that. Name a real motor instead.
* **If you are sizing a solid upper stage, do not accept the book's constant.** Measured against 55 STAR
  motors whose loaded and burnout masses are published together, `k = 0.1154` is about **36 % low below
  100 kg of propellant and 26 %, 44 % and 51 % high** in the 100–500, 500–1,500 and over-1,500 kg bands.
  Motor inert fraction is not constant — it falls from ~0.18 at 30 kg toward a floor near 0.060. Three ways
  out, in order of preference:
  1. **Name a real motor.** `motor.from_database: "Star 37FM"` with `casing_mass_method: mass_fraction`
     uses that motor's own published ratio. Eleven STAR motors are in the database, 112–4,265 kg of
     propellant, with k from 0.0616 to 0.125. Naming a motor and leaving a `book_*` method in place makes
     the tool warn, because the real figure would be loaded and then ignored.
  2. **`casing_mass_method: star_motor`** for a notional upper-stage-class motor: a size-dependent relation
     fitted to those 55 motors, `f = 0.0602 + 0.0051 (m_p/4536)^(-2/3)`, MAPE 14 %. **Upper-stage class
     only** — these are apogee-kick motors with no TVC and no flight structure, and the relation runs about
     31 % light against real launch-vehicle stages. Do not use it for a booster.
  3. **`mass_fraction`** with a k from a comparable motor (Orion/Zefiro/P80 class ≈ 0.08–0.09; steel-cased
     motors ≈ 0.13) when neither of the above fits.

  Every solid stage says in the report which of these it used, so a trade between a real motor and a
  notional one is readable. §3.2 of the validation report has the measurements; on a three-stage solid
  carrying 150 kg to 500 km polar the choice is worth **29 % of lift-off mass**.
* The **avionics MER** jumps from 75 kg to 350 kg at a 1 t payload (Table 8.8); for a small launcher just above
  that threshold this is heavy, and it is worth overriding with `avionics_mass_override_kg`.
* The **ascent-loss regression** has an RMS error of about 260 m/s and is an extrapolation above LEO.

None of these numbers were tuned to match a vehicle, and every input in `validation/*.yaml` carries its source.

---

## 11. Tests and verification

```bash
python -m pytest -v                             # preferred
python tools/run_tests.py                       # offline fallback: a minimal pytest-compatible runner
python tools/run_tests.py test_stage_count      # one file, by name or path
python tools/run_tests.py -k dv_fractions       # only tests whose name matches
```

The fallback runner used to ignore whatever you passed it and run everything regardless, which is worse than
slow: it tells you that you re-checked one file when you re-checked the whole tree as it stood when the run
began. It now selects, and a name that matches nothing is an error rather than a forty-minute full run.
Run one suite at a time: the full suite takes 20 to 45 minutes, and several at once have run out of memory.

The suite covers the rocket equation and staging algebra, orbit and delta-v budget, tank and
casing geometry (closed form vs numerical integration), the engine-dimensioning equations against the book's
worked example, solid-motor relations, the parallel-burn phase model (including the book's own Space Shuttle
exercise, pp. 323–325), mass conservation across burns and separations, centre of mass and inertia, geometry
and drawing consistency, input validation, convergence behaviour and the real-vehicle cases, plus the report (self-containment, completeness of the input register and ledger,
HTML escaping), the GUI server (JSON serialisation, override application, path-traversal refusal), the
performance curves (the capability at the design orbit reproduces the design payload; curves monotone in altitude
and inclination), the uncertainty sampler (reproducible from its seed, failures counted, contributors ordered
sensibly), the engine database (every row sourced, the fill-never-override contract) and the staging optimum
(book Fig. 5.11 reproduced to the two decimals it prints), and the ascent trajectory (US76 against its published
layer values, the Titan II drag equations at their breakpoints, step-size independence, and the Eq. 6:58 closure
identity).

Independent verification bases used by the tests: book Example 1 (two-step sizing, pp. 480–484), the MER
worked examples (pp. 504–505), Examples 5–7 for inertia (pp. 527–531), Example 3 for engine dimensions
(pp. 509–511), and Eq. 5:66 for parallel burns. Two printed intermediate values in the book are **not**
reproducible from its own equations; the tests pin the equation-consistent values and say so explicitly
(the step-2 nozzle length on p.511 and the vacuum thrust on p.509).

---

## 12. Extending the tool

The engine has no dependency on Excel or Matplotlib, so it is easy to script:

```python
from launch_vehicle.config_io import load_design
from launch_vehicle.convergence import size_vehicle

spec = load_design("config/default_design.yaml", "config/engineering_assumptions.yaml",
                   {"mission.payload_mass_kg": 12000.0})
res = size_vehicle(spec)
print(res.glom_kg, res.status, [s.structural_factor_s for s in res.stages])
```

Modules in `src/launch_vehicle/`: `aerodynamics` · `architecture` · `ascent` · `ascent_opt` · `atmosphere` · `boosters` · `cad_export` · `cad_kernel` · `charts` · `config_io` · `control` · `convergence` · `cost` · `debris` · `delta_v` · `desktop` · `drag_buildup` · `engine_db` · `engine_geometry` · `families` · `geodesy` · `geometry` · `gui_meta` · `hazard` · `inertia` · `launch_sites` · `loads` · `main` · `mass_budget` · `mass_properties` · `method_register` · `models` · `optimization` · `orbit` · `paths` · `payload_env` · `performance` · `propellant_db` · `propulsion` · `reliability` · `report` · `reporting` · `schematic_2d` · `sensitivity` · `solid_inert` · `solid_motor` · `stage_count` · `stage_type` · `staging` · `strap_ons` · `structure` · `studies` · `tank_sizing` · `trajectory` · `uncertainty` · `units` · `user_library` · `validation` · `vehicle_import` · `webgui` · `wind`.

**What it does not do:**

* **Nothing is fed back.** The structure is not re-sized to carry the loads it is shown to need, the vehicle is
  not re-sized around the better ascent the optimiser finds, and no motor casing is re-sized for the chamber
  pressure its own grain reaches.
* **Reusable vehicles** cannot be represented, and there is no reuse economics.
* **The lightest vehicle may not be one that flies well.** With the book's loss methods the split search does not see the
  ascent. The Trajectory tab shows the result; the simulated loss method (§7.5) puts it in the search.
* **Drag is an estimate** from the outside shape ([`DRAG.md`](DRAG.md)).
* **Shared-core families are biased.** The sizer never carries a core oversized for the mission being flown, so
  a family's smaller variants come out too light when sized alone, and over-predict payload when the core is
  pinned. This is measured in `docs/ACCURACY.md` section 6b, and is not corrected.
* **Not modelled:** propellant crossfeed, more than one booster set or boosters on a stage other than the first,
  throttling profiles, dog-leg ascents and plane changes, boil-off and chill-down mass, products of inertia, and
  acoustic or shock prediction. A motor below about one tonne of propellant is badly served by every mass
  relation here.
* **Out of scope:** six-degree-of-freedom simulation, finite elements, CFD and flight software.

There is also no Excel → YAML import, because the YAML is always the source of truth. `docs/ROADMAP.md` sets the
gaps against the book chapter by chapter and puts them in priority order.
