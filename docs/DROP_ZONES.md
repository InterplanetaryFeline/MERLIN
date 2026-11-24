# Jettison drop zones

> **The GUI tab is hidden at present.** Its map has no coastline, so it cannot show whether an area is over land. The
> calculation and its exports remain in the program (`hazard.areas()`); putting the tab back is one word in
> `HIDDEN_TABS` in `gui_static/index.html`. Mentions of the tab below describe it as it is when shown.

Where each piece of jettisoned hardware comes down, and how wide the uncertainty is. This document states what
the model does, what it refuses to do, and - most importantly - what actually sets the size of the areas it
draws, which is not what one would guess.

**This is a conceptual-design estimate. It is not a range-safety product and must not be used to clear an
area.** What a real hazard analysis has and this does not is listed under *What is missing* below.

---

## The chain

Four modules, each with a different failure mode, so each is kept separate:

| Module | Produces | Depends on |
|---|---|---|
| `trajectory.py` | the state each item separates at: altitude, planet-relative speed, flight path angle, downrange | the 3-DoF ascent integration (book Table 6.1) |
| `debris.py` | for each item: does it come down, and over what interval of downrange | the separation state, a ballistic descent, declared dispersions |
| `geodesy.py` | coordinates | the launch azimuth and the site's longitude |
| `hazard.py` | areas, KML, GeoJSON, the GUI payload | all of the above |

There is no path from the input file to a map that skips the trajectory. The GUI's Drop zones tab therefore
sizes and flies the design before it can answer.

## Step 1: does the item come down at all?

An upper stage released near orbital speed does not, and inventing an impact point for it would be the model's
worst failure mode. The test is done in inertial terms: the planet-relative velocity from the trajectory is
turned into an inertial one by adding the eastward speed of the rotating surface at the separation point,
`omega * r * cos(latitude)`, and the resulting orbit's perigee is computed.

Perigee above 100 km → the item stays up, gets no impact point, and is reported as an orbital-lifetime
question the tool does not model. On the reference design the second stage separates at 7,346 m/s
planet-relative, which is 7,780 m/s inertial, giving a 399 km perigee: it is in orbit, and the tool says so
rather than drawing a box in the Atlantic.

## Step 2: where does it land?

The item is flown down with the same equations of motion as the ascent, thrust set to zero, carrying its own
mass and its own frontal area (the stage's diameter, or the fairing's).

## What sets the size of the area

This was measured, not assumed, and the first answer was wrong.

The intuition is that a tumbling spent stage's unknown drag coefficient dominates. It does not. Sweeping the
reference design's first stage across the full plausible range - 0.9 flying nose-first to 2.8 tumbling
broadside - moves its impact point by **12 km out of 1,084 km, about 1 %**:

| Cd | Impact downrange | Fall time | Impact speed |
|---|---|---|---|
| 0.001 (no drag) | 1,095 km | 395 s | 3,208 m/s |
| 0.9 | 1,090 km | 428 s | 207 m/s |
| 1.6 | 1,084 km | 453 s | 142 m/s |
| 2.8 | 1,078 km | 486 s | 104 m/s |

The reason is geometric: almost all the downrange is covered on a vacuum coast above the atmosphere, and drag
only acts in the last tens of kilometres, where it is spent almost entirely on killing vertical speed. **Drag
changes the impact velocity by a factor of thirty and the impact position by one percent.**

What does move the impact point is the state the item separates at:

| Perturbation at separation | Impact point moves |
|---|---|
| speed −5 % | −95 km |
| speed +5 % | +101 km |
| flight path angle ±2° | ∓26 km |

So the hazard area is set by how well the vehicle's performance is known. For the reference design, **1 % of
separation-speed error moves the impact point about 20 km.**

### The consequence for solid vehicles

This puts the drop zones downstream of the mass model. `ACCURACY.md` records that the tool's solid-stage
lift-off masses carry a median error of 33 %, driven by inert-mass predictions that run 12 % to 65 % heavy. An
inert-mass error of that size moves burnout velocity by several percent, and at roughly 20 km per percent, the
impact point moves by **a hundred kilometres or more**. A drop zone computed for a solid vehicle on the default
mass method should be read as indicative of the region, not of the location.

## When no area is drawn at all

Some items get a nominal impact point and no box, reported as **not localisable**. This happens when the item
separates close enough to orbital speed that a corner of the dispersion is orbital — the ±3 % speed assumption
decides whether it comes down at all.

Vega C's third stage is the example. Its nominal impact is 2,550 km downrange, but the fast corner does not
reenter, and a descent integrator handed that corner will accumulate downrange for most of a revolution and
produce a "hazard area" 36,000 km long. An area that wraps the planet is not an area, so the tool reports the
nominal point, states that the dispersion is not localisable, and draws nothing. The same applies to any
dispersion spanning more than a quarter of the Earth's circumference.

On that flight the tool therefore gives three drawn zones (stages 1 and 2 and the fairing), one marginal item
(stage 3) and one that stays in orbit (stage 4) — which is the honest division of a four-stage solid vehicle.

## The dispersion that is actually drawn

Three declared inputs, all assumptions, all adjustable in the GUI:

| Input | Default | What it is |
|---|---|---|
| `sep_speed_frac` | ±3 % | separation-speed uncertainty — **this sets the length of the box** |
| `sep_gamma_deg` | ±1.0° | flight-path-angle uncertainty at separation |
| `cd` | 0.9 / 1.6 / 2.8 | drag bracket — kept for honesty, contributes little |

Every item is flown at all corner combinations; the along-track interval is the spread of the results. On the
reference design that gives the first stage a box from 1,008 to 1,163 km, of which the separation-state
assumption accounts for 143 km and the entire drag bracket for 12 km.

**These defaults are not sigmas.** They are round numbers standing in for the guidance and performance
dispersions that a real analysis obtains by Monte Carlo over the actual flight software. Replace them if you
have real numbers.

## The width of the box is an assumption, not a result

A pitch-plane trajectory has **no cross-range state at all**, so nothing in this tool predicts how far off the
centreline anything lands. The width is therefore stated, never computed.

It is not left bare, though. The descent is integrated in the planet-relative frame with no rotation terms, so
the Coriolis cross-range is a known missing effect, and its magnitude is estimated as a double integral of
`2*omega*v` over the fall — 40 km for the first stage, 92 km for the longer-falling fairing. The drawn
half-width is the larger of the stated width and that estimate, so the area is never narrower than an error
known to be absent from it. That is a floor, not a prediction.

## The sphere

Both the trajectory and the geodesy use a spherical Earth of 6,378 km radius, so the arc the integrator
produced and the arc walked to the impact point are the same arc. A great-circle arc on that sphere differs
from the WGS84 geodesic by up to about half a percent of its length — roughly 5 km at a 1,000 km downrange.
Each exported feature carries its own `sphere_error_m`.

## What is missing

A real range-safety or debris-hazard analysis has all of the following. None of it is here:

- **a breakup model.** Both items on the reference design separate above 2,900 m/s, well past the point where
  an empty stage is likely to survive reentry intact. A fragment field lands shorter and spreads wider than the
  single intact body modelled here. The tool flags the speed and does not pretend to model the breakup.
- **wind**, which moves light fragments substantially during descent.
- **Coriolis force in the descent** — estimated as a corridor-width floor, not integrated.
- **real dispersions** from the guidance and the flight software.
- **ground-track curvature.** A single great circle is walked; real ascents dog-leg and yaw-steer.
- **probability of casualty**, which is the quantity a range-safety decision is actually made on.
- **range-safety azimuth corridors.** The launch site library has never carried these, and still does not; a
  site that in reality cannot launch on a given azimuth is not flagged.

## Using it

**GUI.** The *Drop zones* tab. Pick the azimuth when two are available, set the dispersions, press Compute,
then export.

The in-page map is drawn from nothing — no tile layer, no mapping library, no CDN — because the GUI is
required to work with no network at all, and a tab that goes blank on an air-gapped machine would be worse
than a plain one. What that costs is the coastline, so for *"is this box over land?"* export the KML and open
it in Google Earth.

**Exports.** KML (Google Earth) and GeoJSON (QGIS, web maps). Every exported area carries its own description
stating that the width is an assumption and that the file is not a range-safety product, so the caveat travels
with the geometry instead of staying in this document.

**A longitude is required for coordinates, and only for coordinates.** A latitude alone fixes all of the
physics but not the meridian. Name a site from the library and both are filled; otherwise the tool reports the
downrange distances and says plainly why there is no map, rather than defaulting to Greenwich.

**Python.**

```python
from launch_vehicle import trajectory as tj, hazard, debris
traj = tj.fly_design(res)
a = hazard.areas(res, traj, lat, lon, azimuth_deg,
                 dispersion=debris.Dispersion(sep_speed_frac=0.02))
hazard.write_kml(a, "zones.kml")
```
