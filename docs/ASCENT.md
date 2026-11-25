# The ascent simulation

Methods M108 (the flight) and M109 (its losses in the sizing). [`ASCENT_VALIDATION.md`](ASCENT_VALIDATION.md) is the generated
comparison with real vehicles; `USER_MANUAL.md` section 7.5 is how to use it.

## 1. What it replaced, and why

Until v1.3 an ascent was one continuous burn from lift-off to the target altitude: the book's gravity turn, one pitch kick found
by shooting for the altitude, and a flight path angle commanded linearly to zero above the air. The Earth did not turn, the
engine never stopped, and nothing coasted. Flown on the 24 validation vehicles it put 2 in their orbit. Most of what it called a
vehicle's shortfall was the way the vehicle was flown: the shipped default at its optimised split fell 318 m/s short of 400 km
climbing straight there, and has 193 m/s to spare inserted at 185 km and raised.

## 2. The flight

| Phase | What happens | Source |
|---|---|---|
| Vertical rise | 10 s (an input), and until 30 m/s | book p.369; the 30 m/s is ASSUMED |
| Pitch kick | a step in flight path angle, searched (below) | book Sec. 6.4.7 |
| Gravity turn | thrust along the velocity, so no angle of attack in the air | book Sec. 6.4.7, Eq. 6:58 |
| Hand-over | at 60 km, or when the dynamic pressure falls to 1 kPa | ASSUMED |
| Linear tangent steering | tan θ changes linearly with time, through every remaining burn | book Eq. 6:59, p.371 |
| Cutoff | when the orbital energy equals the target orbit's, for a last stage that can stop | - |
| Coast, second burn | above 200 km, and for high apogees | book pp.372-373, Fig. 6.20 |

The equations are the book's Table 6.1 in a frame turning with the part of the Earth's rotation that lies in the orbit plane,
ω = ω_E cos i, which adds a centrifugal and a Coriolis term (SUPPLEMENTARY). The launch site's speed across the plane is removed
by a constant yaw whose sine is that speed over the vacuum ideal speed.

Where the stages below a liquid last stage carry past the first orbit on their own (SLS), that orbit is flown as it is and the
second burn needs less.

**Solving it.** Eq. 6:59 with both ends free has two constants, which are exactly enough for two terminal conditions: the
altitude and a level arrival. A damped Newton iteration finds them, starting in vacuum when it has nothing better to start
from. The pitch kick is what is left, and it is chosen for the most speed in hand at the end: kicks are spread over the flight
path angle they reach the hand-over with, because a slow lift-off makes the turn depend on the kick exponentially. A flight
takes about a second.

**Ways to orbit.** `auto` goes straight in up to 200 km. Higher, it inserts at 185 km (an input) on an ellipse whose top is the
target, coasts there and burns level. A high apogee is left from a circular parking orbit, along the velocity, at the next
equator crossing. A solid last stage coasts to the top of the climb and fires once, level; the solver picks the pitch of the
stages below and the moment of ignition.

## 3. What was tried and measured

* **Linear tangent in inertial space instead of above the local horizon.** 2 m/s at most, on seven vehicles including the
  lowest-thrust upper stages. Not kept.
* **A pitch slope during the burns before a solid's last stage.** 1 m/s at most on Scout, Minotaur, Pegasus and M-V. Not kept.
* **A strap-on's effective Isp.** The boosters module carries a sea-level/vacuum average, which is right for a mass ratio. The
  old ascent flew on it and then took the core's back pressure off as well. The flight now uses vacuum thrust and every nozzle's
  back pressure; H-IIA as sized went from 511 m/s short to 207 to spare.
* **The kick at a fixed 10 s.** At a lift-off thrust-to-weight near 1.1 the vehicle has about 10 m/s then, and the smallest kick in
  double precision still nosed over: the angle grows as (v/v_kick)^(g/a). Hence the 30 m/s.

## 4. How it compares with reality

With the sizing taken out (published masses, thrust, payload and orbit), a perfect model and perfect data would leave no speed in
hand. Seven of fifteen flights are within 150 m/s of zero, which is about 1.5 % of the speed to orbit. The larger misses have a
likely reason that can be named:

* **M-V +956**: the published masses are the motors; 5.6 t of the lift-off mass is in none of them.
* **Vega +523**: the published AVUM empty mass is 131 kg, and its successor's is 695.
* **Soyuz +529, Atlas V +377, Minotaur I +249, Saturn V +197**: incomplete hardware in the published masses (Saturn V's
  instrument unit, escape tower and interstages), cores that really throttle, and this tool's own fairing and adapter masses.
* **Scout −543, Electron −459**: Scout's published masses and Isp give 8,879 m/s in total for a polar 555 km orbit; Electron's
  masses are a community wiki's.
* **Delta IV Heavy** does not fly: its core really throttles to about 55 % beside its strap-ons, and the design file's engine
  stands for the average, which leaves too little thrust to lift off.

The Pegasus of the book's Fig. 6.41 is followed to about 10 s and 25 km through two burnouts without its wing, with 68.6 kPa of
dynamic pressure against 66.9. Saturn V's S-IC burns out at 162 s and 64 km, and the S-II flies at up to 17 deg of angle of attack
against the book's 10-14.

## 5. Feeding the losses back into the sizing

Error in lift-off mass against the published figure, sized with the design's own loss method and with the simulated losses, with
the design's own Δv split and with the split optimised for lift-off mass. Regenerate with `python tools/measure_simulated_losses.py`.

| Vehicle | Design's loss method, own split | Simulated, own split | Design's method, optimised split | Simulated, optimised split | Optimised split: method / simulated [%] | Refused because |
|---|---|---|---|---|---|---|
| Ariane 5 ECA (2 x EAP + EPC + ESC-A) | +9.7 % | - | +2.9 % | - | 46 / 54; - | own split: ascent does not close; optimised: no split sizes and flies |
| Ariane 62 (2 x P120C + Vulcain 2.1 + Vinci) | -23.5 % | - | -23.6 % | - | 47 / 53; - | own split: core too small for its strap-ons; optimised: no split sizes and flies |
| Ariane 64 (4 x P120C + Vulcain 2.1 + Vinci) | -9.3 % | - | -10.3 % | -15.7 % | 60 / 40; 66 / 34 | own split: core too small for its strap-ons |
| Atlas V 551 (5 x AJ-60A + CCB + Centaur III) | -8.2 % | - | -19.0 % | - | 36 / 64; - | own split: ascent does not close; optimised: no split sizes and flies |
| CASC/SAST Long March 12 (2 kerolox stages) | -15.9 % | - | -19.3 % | - | 47 / 53; - | own split: ascent does not close; optimised: no split sizes and flies |
| Delta II 7920 (9 x GEM-40, 6 ground-lit + 3 air-lit) | +28.3 % | - | -0.4 % | - | 40 / 60; - | own split: ascent does not close; optimised: no split sizes and flies |
| Delta IV Heavy (3 x Common Booster Core + DCSS) | +0.4 % | - | +0.4 % | - | 70 / 30; - | own split: ascent does not close; optimised: no split sizes and flies |
| Rocket Lab Electron (LOX/RP-1, composite) | +29.0 % | +16.2 % | +25.8 % | +16.4 % | 33 / 67; 43 / 57 |  |
| Epsilon (3 solid stages) | -19.8 % | -24.5 % | -25.2 % | -24.6 % | 29 / 32 / 39; 36 / 38 / 26 |  |
| SpaceX Falcon 9 Block 5 (expendable, LOX/RP-1) | +15.9 % | +6.6 % | +14.2 % | +5.1 % | 32 / 68; 46 / 54 |  |
| Firefly Alpha (LOX/RP-1, composite) | +8.9 % | - | +6.1 % | -19.4 % | 40 / 60; 41 / 59 | own split: tank not buildable |
| H-IIA 202 (2 x SRB-A + LE-7A core + LE-5B) | +6.0 % | -5.9 % | +6.0 % | - | 66 / 34; - | optimised: tank not buildable |
| JAXA/MHI H3-24L (4 x SRB-3 + 2 x LE-9 + LE-5B-3) | -3.8 % | - | -6.4 % | -17.6 % | 54 / 46; 52 / 48 | own split: tank not buildable |
| M-V (3 solid stages) | +3.9 % | +1.6 % | +0.6 % | +0.4 % | 25 / 30 / 45; 26 / 26 / 48 |  |
| Orbital/Northrop Minotaur I (4 solid stages) | -8.0 % | -13.0 % | -13.4 % | -15.0 % | 17 / 17 / 33 / 33; 19 / 16 / 37 / 28 |  |
| Pegasus XL (3 solid stages, air-launched) | -13.0 % | -22.3 % | -17.6 % | -26.5 % | 32 / 31 / 37; 35 / 28 / 37 |  |
| Saturn V (RP-1/LOX, LH2/LOX, LH2/LOX) to TLI | -2.4 % | +1.7 % | -13.2 % | +1.7 % | 16 / 44 / 39; 26 / 38 / 35 |  |
| Scout G-1 (4 solid stages) | +41.3 % | +9.1 % | -11.5 % | -21.5 % | 22 / 23 / 24 / 31; 20 / 24 / 27 / 28 |  |
| NASA SLS Block 1 (2 x five-segment SRB + 4 x RS-25 + ICPS) | -10.2 % | - | -20.8 % | -22.4 % | 43 / 57; 64 / 36 | own split: losses run away |
| Soyuz-2.1b (4 tapered strap-ons + Blok A + Blok I) | +15.7 % | - | -10.5 % | -13.6 % | 38 / 62; 55 / 45 | own split: ascent does not close |
| Titan II GLV (N2O4/Aerozine-50) | +16.0 % | +16.7 % | +15.8 % | - | 40 / 60; - | optimised: tank not buildable |
| Vega (P80 + Zefiro 23 + Zefiro 9 + AVUM) | +37.5 % | -4.3 % | +0.5 % | - | 21 / 17 / 22 / 41; - | optimised: no split sizes and flies |
| Vega C (3 solid stages + AVUM+) | +37.0 % | -0.1 % | +4.6 % | - | 29 / 16 / 17 / 39; - | optimised: no split sizes and flies |
| LandSpace Zhuque-2 (LOX/CH4) | -31.5 % | -22.9 % | -31.7 % | - | 41 / 59; - | optimised: tank not buildable |

own split: 13 vehicles size both ways. Mean absolute error 20.1 % with the design's method, 11.1 % simulated; median 16.0 % and 9.1 %; mean signed +8.6 % and -3.2 %.

optimised split: 13 vehicles size both ways. Mean absolute error 13.5 % with the design's method, 15.4 % simulated; median 13.2 % and 16.4 %; mean signed -6.3 % and -11.8 %.

A dash is a vehicle the simulated method refuses. Most are refused because the vehicle as this tool sizes it cannot be flown, and
CZ-12, Soyuz and SLS because their engines are fixed: a heavier vehicle flies worse on them, and the sizing runs away.

**What it says.** At the design's own split, for the 13 vehicles that size both ways, the mean absolute error falls from 20.1 % to
11.1 % and the median from 16.0 % to 9.1 %. Vega, Vega C and Scout, where the regression charges a fast solid or a slow last stage
far too much, go from about +40 % to within 10 %. With the split optimised for the lowest mass it does not help: 13.5 % against
15.4 %, and everything comes out lighter, because an optimiser takes every optimism there is in the mass model. So it is a good
check on a design whose split is known, and it stays off by default: it refuses 11 of the 24 vehicles at their own split.

On the shipped default the lift-off mass goes from 410.0 t to 349.4 t with its own split, and the optimised split from 35/65 to
45/55 (349.1 t). The regression's losses were a margin as well as an error, and this takes both away.

## 6. What it does not do

No wind, lift or attitude dynamics; no plane change; no apogee burn for a geostationary orbit (a GTO is where the flight ends);
no engines shut down in flight and no thrust profile beyond a minimum throttle held to an acceleration limit; no propellant lost
between two burns, and every liquid last stage may restart once; no optimal control, only one kick and one tangent arc.
