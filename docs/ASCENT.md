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

**Measured on the first 17 of the 24 validation vehicles only; the run was cut short and is to be finished.** Error in lift-off mass against the published figure:

| Vehicle | Regression, own split | Simulated, own split | Regression, optimised split | Simulated, optimised split |
|---|---|---|---|---|
| ariane5_eca | +9.7 % | - | +2.9 % | - |
| ariane62 | -23.5 % | - | -23.6 % | - |
| ariane64 | -9.3 % | - | -10.3 % | -15.7 % |
| atlas5_551 | -8.2 % | - | -19.0 % | - |
| cz12 | -15.9 % | - | -19.3 % | - |
| delta2_7920 | +28.3 % | - | -0.4 % | - |
| delta4_heavy | +0.4 % | - | +0.4 % | - |
| electron | +29.0 % | +33.4 % | +25.8 % | +33.4 % |
| epsilon | -19.8 % | -24.5 % | -25.2 % | -24.6 % |
| falcon9 | +15.9 % | +6.6 % | +14.2 % | +5.1 % |
| firefly_alpha | +8.9 % | - | +6.1 % | -19.4 % |
| h2a_202 | +6.0 % | -5.9 % | +6.0 % | - |
| h3_24l | -3.8 % | - | -6.4 % | -17.6 % |
| m_v | +3.9 % | +1.6 % | +0.6 % | +0.4 % |
| minotaur1 | -8.0 % | -13.0 % | -13.4 % | -15.0 % |
| pegasus_xl | -13.0 % | -22.3 % | -17.6 % | -26.5 % |
| saturn5 | -2.4 % | +1.7 % | -13.2 % | +1.7 % |

A dash is a vehicle the simulated method refuses: its ascent does not close, or it is not buildable at that loss. On the shipped default the lift-off mass goes from 410.0 t to 349.4 t with its own split, and the optimised split from 35/65 to 45/55 (349.1 t). Off by default, because the regression's margin goes with its error.

## 6. What it does not do

No wind, lift or attitude dynamics; no plane change; no apogee burn for a geostationary orbit (a GTO is where the flight ends);
no engines shut down in flight and no thrust profile beyond a minimum throttle held to an acceleration limit; no propellant lost
between two burns, and every liquid last stage may restart once; no optimal control, only one kick and one tangent arc.
