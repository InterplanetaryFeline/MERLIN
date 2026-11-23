# Export to Kerbal Space Program

**Summary → Export to Kerbal Space Program** turns a sized vehicle into Kerbal Space Program parts and a craft
file (`src/launch_vehicle/ksp_export.py`). It is an engineering export, not a 3D model export. Every vehicle gets
parts of its own, generated from the sized design, so KSP flies with MERLIN's masses, thrust and Isp rather than
those of a stock part that looks similar.

## What you need

* **KSP 1.12.5** with **Real Solar System** (and Kopernicus, which it needs) and **ModuleManager**. Without RSS the
  vehicle still loads, but on stock Kerbin (a tenth of Earth's size) it is hugely overpowered and MERLIN's
  delta-v budget does not apply.
* **Ferram Aerospace Research** is optional. With it, drag comes from the parts' shapes.
* Not needed, and not the target: RealFuels, Realism Overhaul, RP-1. The parts define their own propellants,
  so nothing from those mods is used.

## Using it

1. Size the vehicle, then press **Export to Kerbal Space Program** on the Summary tab.
2. The panel shows MERLIN beside the KSP export, stage by stage: lift-off mass, dry mass, usable propellant,
   vacuum thrust, vacuum Isp and mixture ratio. They should agree. If they do not, the export is wrong; please
   report it.
3. Either:
   * **Install into KSP**: MERLIN finds the game in any Steam library (or takes the folder you type). It copies
     the parts into `GameData/MERLIN_Export/<vehicle>/` and the craft into `saves/<save>/Ships/VAB/`. Nothing
     else in the game folder is written.
   * **Download zip**: the same files plus a README, to unzip into the game folder yourself.
   The parts are named after the configuration's name. Exporting a changed design under the same name replaces
   the earlier parts, and the earlier craft then flies with the new numbers. Give a design you want to keep
   beside another its own name.
4. Start KSP, or restart it, since it reads parts only at start-up. Open the save and load the craft in the VAB.
5. Staging:
   * space ignites stage 1;
   * after burnout, space separates;
   * space again ignites the next stage, and jettisons the fairing at the stage MERLIN jettisons it.

## What is generated, and where the numbers come from

| KSP | from MERLIN |
|---|---|
| one part per geometry segment (aft skirt, tanks, intertank, forward skirt) | station, length and diameter from `res.geometry`; dry mass is the sum of the ledger items whose station falls in that segment; `CoMOffset` puts the dry centre of mass where those items put it |
| propellant in each tank | MERLIN's usable propellant (mission + start-up), as a resource of its own (`MERLIN_<vehicle>_<propellant>`) at MERLIN's density. Residual and loading-margin propellant, which MERLIN keeps on board to burnout, is counted in the tank's dry mass |
| one part per engine, on MERLIN's cluster ring | vacuum thrust; vacuum Isp; an Isp-versus-pressure curve; propellant ratios. The curve is exactly the straight line MERLIN's thrust model follows, `T = mdot ve - Pa Ae` at constant `mdot`. It is given with explicit tangents so KSP's spline does not bend it. The ratios are MERLIN's mass mixture ratio converted to the volume ratio KSP uses |
| a solid stage's motor casing | the grain, as a propellant of its own at the grain's density (`spec.solid_propellants`), in the casing part. Slivers and slag (residual) count in the casing's dry mass |
| a solid stage's nozzle | an engine that cannot be throttled, shut down or restarted. It has MERLIN's vacuum thrust and Isp and the same straight-line Isp curve, and burns the grain at a constant mass flow, which is MERLIN's neutral-burn model, so it burns for MERLIN's burn time. It **weighs nothing**: MERLIN's casing relation already includes the nozzle, insulation and TVC, and splitting that mass would mean inventing the split |
| interstage | a decoupler |
| payload adapter | the base of a stock procedural fairing, carrying the PAF mass. The fairing outline is MERLIN's fairing segments, and the panel mass per area is set so the panels weigh MERLIN's fairing mass |
| payload | a mass part of MERLIN's payload mass and envelope |

**Not from MERLIN**, and needed for the vehicle to fly at all:

* a 20 kNm reaction wheel and 5000 units of ElectricCharge in the top stage's forward skirt, which is the
  command part;
* a 5° engine gimbal;
* four stock launch clamps on the first stage's aft skirt, released at stage 1 ignition. They stay on the pad
  and are not in the mass check. They were added after Scout G-1, standing on its single nozzle, toppled on
  the pad and broke up before ignition. KSP's own mass readout on the pad includes them, 4 × 100 kg.

**The Isp curve never goes below 1 s.** A vacuum engine with a large nozzle, such as Vega's AVUM, has
a straight line that crosses zero before one atmosphere (AVUM's reaches −2,246 s at sea level). A negative Isp
would be negative thrust in KSP, so the curve follows MERLIN's line down to 1 s and stays flat from there.
Such an engine is never lit that low anyway.

**Burn time includes the start-up propellant.** MERLIN burns it at ignition with no Δv credit, while KSP burns
it in flight. KSP's burn is therefore longer by start-up mass ÷ mass flow: 1 s for the TSTO's stage 1 and for
AVUM. The check compares the two on that basis.

The parts reuse stock meshes, scaled (the Size 3 tank, the Mainsail engine and the Size 3 fairing base), so no
new art is needed and no mesh can be missing. They look like stock parts stretched to MERLIN's sizes.

**Not exported yet**, and refused with a reason rather than exported wrong:

* strap-on boosters.

Solid stages are exported since the second version. The seven validation vehicles with solid stages and no
boosters all export with every stage's dry mass, propellant, thrust, Isp and burn time equal to MERLIN's:
Scout G-1, Minotaur I, Vega, Vega C, Epsilon, Pegasus XL and M-V.

**Solid stages have not yet been checked in the game.** The one attempt got as far as Scout G-1 loading with no
part errors. It then toppled on the pad (which is why the clamps were added), and KSP crashed while reloading,
on a 12 GB machine. The readback and a flight with `tools/ksp_fly.py`, which has not been run yet either, are
still to do.

## Checked in the game

This was checked once by hand, not in the test suite. The vehicle was the default two-stage LOX/RP-1 rocket (10
t to LEO) with its delta-v split as written (`vehicle.optimise_dv_split: false`). The game was KSP 1.12.5, RSS
20.1.3, FAR 0.16.1.2, kRPC 0.6. `tools/ksp_verify.py` launched the craft and read back what KSP built:

| | MERLIN | KSP |
|---|---|---|
| parts | 20 | 20, all found |
| lift-off mass | 410,002.7 kg | 410,002.8 kg |
| stage 1 thrust, vacuum | 6 × 967.96 kN | 6 × 967.96 kN |
| stage 1 Isp, vacuum / sea level | 300 s / 270 s | 300 s / 270 s |
| stage 2 thrust, vacuum | 497.71 kN | 497.71 kN |
| stage 2 Isp, vacuum | 340 s | 340 s |
| staging | ignite 1, separate, ignite 2 + fairing | the same |

The sea-level Isp is the curve's value at one atmosphere. For stage 1 that is MERLIN's own 270 s. For stage 2,
a vacuum engine, it is 100.3 s, which is what MERLIN's straight-line thrust model gives at one atmosphere.

### Flights

The vehicle was then flown by kRPC's autopilot along MERLIN's own computed trajectory
(`outputs/ksp_export/fly_merlin.py`). Flight 1 pointed it along MERLIN's flight-path angle γ(t). That proved
wrong for stage 2: MERLIN flies stage 2 with an angle of attack α between thrust and velocity, up to its 15°
limit (`trajectory._steering_alpha`), and Flight 1 left that out. Flight 2 points it along γ + α, which is the
thrust direction MERLIN actually flew.

MERLIN's speed is relative to the rotating Earth. KSP's is shown the same way, surface speed:

| t [s] | altitude MERLIN / KSP [km] | speed MERLIN / KSP [m/s] | mass MERLIN / KSP [t] |
|---|---|---|---|
| 60 | 8.1 / 8.3 | 348 / 348 | 289.6 / 291.3 |
| 120 | 41.6 / 41.8 | 1,415 / 1,392 | 171.1 / 174.0 |
| 158 (stage 1 burnout) | 82.4 / 84.0 | 2,915 / 2,887 | 96.1 / 97.7 |
| 250 | 198.3 / 205.5 | 3,237 / 3,241 | 59.1 / 59.4 |
| 400 | 336.0 / 359.9 | 4,450 / 4,405 | 36.7 / 37.1 |
| 546 (stage 2 burnout) | 398.6 / 453.2 | 7,310 / 7,144 | 14.7 / 15.3 |

Flight 2 is shown above.

* **Burnout times.** Stage 1 burned out at 159.5 s in KSP against 158.5 s in MERLIN, and stage 2 at 548.5 s
  against 546.4 s.
* **Mass.** KSP is 1-3 t heavier during stage 1. KSP burns MERLIN's start-up propellant in flight, where MERLIN
  burns it on the pad before lift-off, which shifts the KSP burn by about a second. The gap closes to 0.3-0.6 t
  through stage 2.
* **Speed.** It agrees within 2.3% throughout.
* **Altitude.** It drifts 55 km high by the end of stage 2. The steering is open-loop: a pitch-versus-time
  programme with no feedback, which is how MERLIN flies too. KSP started stage 2 0.8° steeper than MERLIN, and
  its autopilot held 0.53° above the command on average (2.66° at worst). A climb angle 2° steeper over the
  burn's last 300 s is enough for the extra altitude.
* **Orbit.** Both flights reached orbit, at 28.2° inclination from Cape Canaveral's latitude:
  * Flight 2: 255 × 764 km.
  * Flight 1 (γ only, which flew too flat in the middle of the burn and so built speed instead of height):
    300 × 1,510 km.

  MERLIN's own burnout is 398.6 km at 7,321 m/s and γ = 0, with the verdict "reached".

What this does and does not show:

* **It shows** that the exported vehicle is the sized vehicle: mass, propellant, thrust, Isp and staging are
  MERLIN's, read back from the game, and the mass flow tracks MERLIN's through both burns.
* **It does not show** that MERLIN's trajectory is right. KSP and MERLIN differ in their atmosphere, drag
  model, gravity model, the Earth's rotation and the autopilot's tracking. Agreement here shows only that the
  two simulations agree, not that either matches a real flight.
