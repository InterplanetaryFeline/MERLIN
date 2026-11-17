"""Run all real-vehicle validation cases and the propellant-combination comparison. Writes outputs/validation/*."""
import json, math, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from launch_vehicle.config_io import load_design
from launch_vehicle.convergence import size_vehicle
from launch_vehicle.optimization import optimize_dv_split
from launch_vehicle.main import run
from launch_vehicle.units import G0
from launch_vehicle import propulsion as prop

ASSUMP = os.path.join(ROOT, "config", "engineering_assumptions.yaml")
VAL = os.path.join(ROOT, "validation")
OUT = os.path.join(ROOT, "outputs", "validation")
os.makedirs(OUT, exist_ok=True)

# Published reference values. (value, source, confidence)
REF = {
 # Ariane 62 and 64 share ONE core and ONE upper stage, so the pair measures something no single case can:
 # whether a tool that sizes every stage minimally can reproduce a vehicle whose core is sized for its
 # bigger sibling. No LLPM dry mass is published, so neither can join the published-mass delta-v check.
 # SLS and H3 complete the hydrolox-core-plus-solid-boosters group that R34 unblocked. Neither publishes
 # a dry mass for every element, so neither joins the published-mass delta-v check.
 "sls_block1": dict(title="NASA SLS Block 1 (2 x five-segment SRB + 4 x RS-25 + ICPS)",
                    glom=(2610000, "Wikipedia 'Space Launch System' infobox, Block 1: 2,610,000 kg"),
                    length=(98.1, "orbitalradar / NASA fact sheet: 98.1 m (322 ft)"), prop={}, dry={}),
 "h3_24l": dict(title="JAXA/MHI H3-24L (4 x SRB-3 + 2 x LE-9 + LE-5B-3)",
                glom=(575000, "Mitsubishi Heavy Industries launch-vehicle page (manufacturer): 575 t"),
                length=(63.0, "Mitsubishi Heavy Industries: 63 m with the long fairing"), prop={}, dry={}),
 "ariane62": dict(title="Ariane 62 (2 x P120C + Vulcain 2.1 + Vinci)",
                  glom=(530000, "Wikipedia 'Ariane 6' infobox, A62: 530,000 kg"),
                  length=(63.0, "Wikipedia 'Ariane 6' infobox: 63 m"), prop={}, dry={}),
 "ariane64": dict(title="Ariane 64 (4 x P120C + Vulcain 2.1 + Vinci)",
                  glom=(860000, "Wikipedia 'Ariane 6' infobox, A64: 860,000 kg"),
                  length=(63.0, "Wikipedia 'Ariane 6' infobox: 63 m, both variants"), prop={}, dry={}),
 "minotaur1": dict(title="Orbital/Northrop Minotaur I (4 solid stages)",
                   glom=(36200, "Minotaur I User's Guide (Orbital ATK Rel. 3.0) via Wikipedia: 36,200 kg"),
                   length=(19.21, "Encyclopedia Astronautica 'Minotaur': 19.21 m"),
                   prop={1: (20785, "Astronautix stage table: gross 23,077 - empty 2,292"),
                         2: (6237, "Astronautix stage table: gross 7,032 - empty 795"),
                         3: (3925, "Wikipedia Pegasus XL table: Orion 50 XL propellant 3,925 kg"),
                         4: (770, "Wikipedia Pegasus XL table: Orion 38 propellant 770 kg")},
                   dry={1: (2292, "Astronautix stage table: empty 2,292 kg"),
                        2: (795, "Astronautix stage table: empty 795 kg"),
                        3: (416, "Wikipedia Pegasus XL table: Orion 50 XL empty 416 kg"),
                        4: (126, "Wikipedia Pegasus XL table: Orion 38 empty 126 kg")}),
 # No stage masses are published for the CZ-12, so it carries no prop/dry rows and cannot join the
 # published-mass delta-v check. Its value is the three payload/orbit pairings on one lift-off mass.
 "cz12": dict(title="CASC/SAST Long March 12 (2 kerolox stages)",
              glom=(433000, "Wikipedia 'Long March 12' infobox: 433 t"),
              length=(62.0, "Wikipedia 'Long March 12' infobox: 62 m"), prop={}, dry={}),
 "electron": dict(title="Rocket Lab Electron (LOX/RP-1, composite)", glom=(13000, "rocketlabusa.com/electron wet mass 13,000 kg"), length=(18.0, "rocketlabusa.com height 18 m"),
                  prop={1: (9250, "r/rocketlab wiki: wet 10,200 - dry 950 (LOW confidence)"), 2: (2050, "r/rocketlab wiki: wet 2,300 - dry 250 (LOW confidence)")},
                  dry={1: (950, "r/rocketlab wiki (LOW confidence)"), 2: (250, "r/rocketlab wiki (LOW confidence)")}),
 "falcon9": dict(title="SpaceX Falcon 9 Block 5 (expendable, LOX/RP-1)", glom=(549054, "NASA blog / wevolver 549,054 kg"), length=(70.0, "NASA blog 70 m"),
                 prop={1: (395700, "wevolver (FAA quotes 411,000)"), 2: (92670, "wevolver (older figure; 107,500 est. elsewhere)")},
                 dry={1: (25600, "wevolver (includes recovery hardware)"), 2: (3900, "wevolver")}),
 "titan2": dict(title="Titan II GLV (N2O4/Aerozine-50)", glom=(154000, "Wikipedia 154,000 kg (150,530-155,000 range)"), length=(33.2, "bricksin.space/orbitcodex GLV 33.2 m"),
                prop={1: (117800, "Book Table 5.1 p.276"), 2: (28900, "Book Table 5.2 p.277")}, dry={1: (6700, "Book Table 5.1 (inert)"), 2: (2400, "Book Table 5.2 (inert)")}),
 "saturn5": dict(title="Saturn V (RP-1/LOX, LH2/LOX, LH2/LOX) to TLI", glom=(2894000, "Wikipedia 2,822,171-2,965,241 kg (mid-range)"), length=(110.6, "Wikipedia 110.6 m (incl. LES)"),
                 prop={1: (2145700, "Book Table 5.1"), 2: (456100, "Book Table 5.2"), 3: (106300, "Book Table 5.2")},
                 dry={1: (133270, "Book Table 5.1 (inert)"), 2: (32500, "Book Table 5.2 (inert)"), 3: (11660, "Book Table 5.2 (inert)")}),
 "zhuque2": dict(title="LandSpace Zhuque-2 (LOX/CH4)", glom=(219000, "Wikipedia 219,000 kg (216 t elsewhere)"), length=(49.5, "Wikipedia 49.5 m"), prop={}, dry={}),
 # ---- v0.3: small launchers and solid-motor vehicles -------------------------------------------------
 "pegasus_xl": dict(title="Pegasus XL (3 solid stages, air-launched)", glom=(23130, "Wikipedia 'Northrop Grumman Pegasus': 23,130 kg"),
                    length=(17.6, "Wikipedia: 17.6 m"),
                    prop={1: (15014, "Wikipedia XL table"), 2: (3925, "Wikipedia XL table"), 3: (770, "Wikipedia XL table")},
                    dry={1: (1369, "Wikipedia XL table (empty mass)"), 2: (416, "Wikipedia"), 3: (126, "Wikipedia")}),
 "vega": dict(title="Vega (P80 + Zefiro 23 + Zefiro 9 + AVUM)", glom=(137000, "Wikipedia 'Vega (rocket)': 137,000 kg"),
              length=(30.0, "Wikipedia: 30 m"),
              prop={1: (88365, "Wikipedia infobox"), 2: (24000, "Wikipedia stage table"), 3: (10500, "Wikipedia"), 4: (550, "Wikipedia")},
              dry={1: (7330, "Wikipedia infobox"), 2: (1950, "Wikipedia stage table"), 3: (915, "Wikipedia stage table"), 4: (131, "Wikipedia stage table")}),
 "epsilon": dict(title="Epsilon (3 solid stages)", glom=(95400, "Wikipedia 'Epsilon (rocket)': 95.4 t (Enhanced)"),
                 length=(26.0, "Wikipedia: 26 m"), prop={1: (65900, "Wikipedia: SRB-A3 65.9 t")}, dry={}),
 # Scout G-1 is the only case whose per-stage INERT masses are published by the manufacturer, which makes it
 # the one vehicle here that tests the solid inert relations stage by stage rather than only through GLOM.
 # The published lift-off weight of 21,543 kg is the four stages plus the heatshield and EXCLUDES the
 # payload: the stage masses sum to 21,478 kg, leaving 65 kg, which is the heatshield and nothing else. The
 # comparison below therefore uses 21,543 + 165 = 21,708 kg, and says so.
 "scout_g1": dict(title="Scout G-1 (4 solid stages)",
                  glom=(21708, "Tanck & Williams (LTV), 'The Scout Launch Vehicle System', citing SCOUT "
                               "Planning Guide (LTV, May 1987): lift-off 21,543 kg for the stages plus "
                               "heatshield, plus the 165 kg polar payload"),
                  length=(22.90, "Tanck & Williams (LTV): 22.90 m overall"),
                  prop={1: (12817, "LTV Figure 4"), 2: (3768, "LTV Figure 4"), 3: (1299, "LTV Figure 4"),
                        4: (215, "LTV Figure 4")},
                  dry={1: (1939, "LTV Figure 4 inert mass"), 2: (1064, "LTV Figure 4 inert mass"),
                       3: (335, "LTV Figure 4 inert mass"), 4: (41, "LTV Figure 4 inert mass")}),
 "vega_c": dict(title="Vega C (3 solid stages + AVUM+)",
                glom=(210000, "Wikipedia 'Vega C': 210,000 kg at lift-off"),
                length=(34.8, "Wikipedia 'Vega C': 34.8 m"),
                prop={1: (141634, "Wikipedia 'Vega C' stage table"), 2: (36239, "same"),
                      3: (10567, "same"), 4: (740, "same: 492 kg N2O4 + 248 kg UDMH")},
                dry={1: (11200, "Wikipedia 'Vega C' empty mass"), 2: (3230, "same"), 3: (929, "same"),
                     4: (695, "same")}),
 # The only case whose stage data comes from the agency that built the vehicle. M-V's first stage is
 # HEAVIER than the book's constant (inert/propellant 0.153 against k = 0.1154), which makes it the one
 # solid vehicle here the book does not over-predict - a counter-example worth keeping in the set.
 "m_v": dict(title="M-V (3 solid stages)",
             glom=(139000, "Wikipedia 'M-V': 137,500-139,000 kg; upper end used"),
             length=(30.8, "Wikipedia 'M-V': 30.8 m"),
             prop={1: (72000, "ISAS/JAXA M-V-7 configuration page"), 2: (33000, "same"), 3: (11000, "same")},
             dry={1: (11000, "ISAS: motor mass 83 t minus propellant 72 t"),
                  2: (3000, "ISAS: 36 t minus 33 t"), 3: (1000, "ISAS: 12 t minus 11 t")}),
 "firefly_alpha": dict(title="Firefly Alpha (LOX/RP-1, composite)", glom=(54000, "Wikipedia 'Firefly Alpha': 54,000 kg"),
                       length=(29.0, "Wikipedia: 29 m"), prop={}, dry={}),
 # ---- v0.3: vehicles with strap-on boosters (parallel burn) -----------------------------------------
 "delta2_7920": dict(title="Delta II 7920 (9 x GEM-40, 6 ground-lit + 3 air-lit)",
                     glom=(231870, "Wikipedia Delta II: 9 x 13,080 + 101,800 + 6,954 kg (fairing extra)"),
                     length=(38.9, "Wikipedia: 38.9 m"),
                     prop={1: (96120, "Wikipedia: gross 101,800 - dry 5,680"), 2: (6004, "Wikipedia: 6,954 - 950")},
                     dry={1: (5680, "Wikipedia"), 2: (950, "Wikipedia")},
                     boosters=(9, 11765, 1315, "Wikipedia GEM-40: gross 13,080, empty 1,315")),
 "atlas5_551": dict(title="Atlas V 551 (5 x AJ-60A + CCB + Centaur III)",
                    glom=(587000, "Derived: CCB 305,143 + Centaur 23,073 + 5 x 46,697 + payload/fairing"),
                    length=(58.3, "Wikipedia: up to 58.3 m"),
                    prop={1: (284089, "Wikipedia CCB"), 2: (20830, "Wikipedia Centaur III")},
                    dry={1: (21054, "Wikipedia CCB"), 2: (2243, "Wikipedia Centaur III")},
                    boosters=(5, 42630, 4067, "Wikipedia AJ-60A: gross 46,697, propellant 42,630")),
 "ariane5_eca": dict(title="Ariane 5 ECA (2 x EAP + EPC + ESC-A)",
                     glom=(780000, "Derived: 2 x 273,000 + 184,700 + 19,440 + payload/fairing"),
                     length=(52.0, "Wikipedia: 46-52 m"),
                     prop={1: (170000, "Wikipedia EPC"), 2: (14900, "Wikipedia ESC-A")},
                     dry={1: (14700, "Wikipedia EPC"), 2: (4540, "Wikipedia ESC-A")},
                     boosters=(2, 240000, 33000, "Wikipedia EAP: gross 273,000, empty 33,000")),
 "h2a_202": dict(title="H-IIA 202 (2 x SRB-A + LE-7A core + LE-5B)",
                 glom=(285000, "spaceflight101 'H-IIA 202': 285,000 kg at lift-off"),
                 length=(53.0, "spaceflight101: 53 m"),
                 prop={1: (102800, "spaceflight101 first stage"), 2: (16600, "spaceflight101 second stage")},
                 dry={1: (11200, "Derived: 114,000 - 102,800"), 2: (3000, "ASSUMED: the source does not give it")},
                 boosters=(2, 65040, 11360, "spaceflight101: SRB-A propellant 65,040 kg, launch 76,400 kg")),
 "soyuz2_1b": dict(title="Soyuz-2.1b (4 tapered strap-ons + Blok A + Blok I)",
                   glom=(312000, "Derived: 4 x 44,413 + 99,765 + 27,755 + payload and fairing"),
                   length=(46.1, "spaceflight101: 46.1 m"),
                   prop={1: (90100, "spaceflight101 core stage"), 2: (25400, "spaceflight101 third stage")},
                   dry={1: (6545, "spaceflight101 core empty"), 2: (2355, "spaceflight101 third stage empty")},
                   boosters=(4, 39160, 3784, "spaceflight101: strap-on propellant 39,160 kg, dry 3,784 kg")),
 "delta4_heavy": dict(title="Delta IV Heavy (3 x Common Booster Core + DCSS)",
                      glom=(733000, "Wikipedia 'Delta IV Heavy': 733,000 kg at lift-off"),
                      length=(70.7, "Wikipedia: 70.7 m"),
                      prop={1: (200400, "Wikipedia CBC"), 2: (27220, "Wikipedia DCSS 5 m")},
                      dry={1: (26760, "Wikipedia CBC empty"), 2: (3490, "Wikipedia DCSS empty")},
                      boosters=(2, 200400, 26760, "Wikipedia: the strap-ons ARE Common Booster Cores - "
                                                  "same propellant load and empty mass as the core")),
}
# Published casing/inert mass fractions for the solid stages (inert mass / propellant mass). Used ONLY for the
# diagnostic 'calibrated' run that replaces the book's SRM casing MER with the real motor's ratio. These published
# empty masses include skirts and attachments, so the calibrated run is slightly conservative.
#: Case material of each validation vehicle's solid motors, so the published stage-level regressions of
#: solid_inert can be applied to the right ones. This is a property of the HARDWARE, taken from the motor's
#: own description, not a knob tuned to improve an answer - and the book's own result is still reported
#: beside it, which is the point of the column.
CASE_MATERIAL = {
 "vega": "composite",            # P80 / Zefiro filament-wound graphite-epoxy
 "pegasus_xl": "composite",      # Orion motors, graphite-epoxy
 "epsilon": "composite",         # SRB-A3 / M-35, CFRP
 "delta2_7920": "composite",     # GEM-40, graphite-epoxy
 "atlas5_551": "composite",      # AJ-60A, graphite-epoxy
 "ariane5_eca": "steel",         # EAP P241, steel segments
 "h2a_202": "composite",        # SRB-A, CFRP - and one of the 17 composite stages solid_inert is fitted to
 # Scout is mixed: Algol IIIA and Castor IIA are steel cases, Antares IIIA (Star-31) and Altair IIIA
 # (Star-20) are filament-wound. Steel is used here because the two steel stages carry 96 % of the
 # propellant, so they decide the vehicle; the per-stage comparison below shows both materials properly.
 "scout_g1": "steel",
 "vega_c": "composite",         # P120C / Zefiro, filament-wound
 "m_v": "composite",            # M-14/M-25/M-34, CFRP cases
}

PUBK = {
 "pegasus_xl": {1: (1369 / 15014, "Wikipedia: 1,369/15,014"), 2: (416 / 3925, "Wikipedia: 416/3,925"), 3: (126 / 770, "Wikipedia: 126/770")},
 "vega": {1: (7330 / 88365, "Wikipedia: 7,330/88,365"), 2: (1950 / 24000, "Wikipedia table: 1,950/24,000"), 3: (915 / 10500, "Wikipedia table: 915/10,500")},
 # Scout is deliberately NOT here, and the reason is worth writing down because it applies to the two rows
 # above as well.
 #
 # `casing_mass_fraction` is a MOTOR-level input: the build-up then adds skirts, interstage, avionics,
 # separation hardware and margin on top of it. Every "published inert" figure available for these vehicles
 # is STAGE-level - it already contains those items - so feeding one in here double-counts them. For Pegasus
 # (k = 0.091) and Vega (k = 0.083) the error is small enough to hide. Scout's stage 2 ratio is 0.282,
 # because that stage carries the Scout guidance section, and substituting it drives the sized vehicle to
 # 72 t against a published 21.7 t - worse than the book's own answer, and worse for a reason that has
 # nothing to do with the book being wrong.
 #
 # The honest way to use a stage-level published figure is the stage-level mechanism (solid_inert relation
 # keys, which return the WHOLE stage inert and suppress the build-up), not this one. Until the two rows
 # above are reworked that way, nothing is added here.
}
# Published stage masses for the 'delta-v from published masses' check:
#   dict(stages=[(propellant kg, inert kg, effective Isp s), ...], payload=kg, extra=kg carried to orbit, source=...)
CAP = {
 # Minotaur I is the reason this vehicle was added: a SMALL payload (580 kg) to a LOW orbit (185 km) with
 # every stage mass published, which the loss-model analysis in docs/ACCURACY.md section 6b had no example
 # of - there, every small-payload case flew to 500-700 km SSO, so payload and altitude could not be told
 # apart. `extra` is DERIVED, and the derivation is the case's own consistency check: the four stages plus
 # the payload sum to 35,926 kg against a published 36,200 kg, so 274 kg is fairing + avionics + adapter.
 "minotaur1": dict(stages=[(20785, 2292, (237 + 2 * 262) / 3), (6237, 795, 288.0),
                           (3925, 416, 283.8), (770, 126, 281.7)], payload=580, extra=274.0,
                   source="Astronautix Minotaur stage table for M55A1/SR19; Wikipedia Pegasus XL table for "
                          "Orion 50XL and Orion 38; stage 1 Isp weighted 1/3 SL per book Eq. 4:18"),
 "falcon9": dict(stages=[(395700, 25600, (285 + 2 * 313) / 3), (107500, 3900, 348)], payload=22800,
                 source="wevolver masses; S2 propellant 107.5 t est.; Isp orbitcodex"),
 "titan2": dict(stages=[(117800, 6700, (258 + 2 * 296) / 3), (28900, 2400, 316)], payload=3574,
                source="Book Tables 5.1/5.2; Isp Wikipedia LR-87/LR91"),
 "saturn5": dict(stages=[(2145700, 133270, (263 + 2 * 304) / 3), (456100, 32500, 427), (106300, 11660, 427)],
                 payload=48600, source="Book Tables 5.1/5.2; payload Wikipedia TLI"),
 "electron": dict(stages=[(9250, 950, 311), (2050, 250, 343)], payload=300,
                  source="r/rocketlab wiki masses (LOW confidence); Isp rocketlabusa.com"),
 # Scout's is the sharpest version of this check in the set, because every mass is the manufacturer's. The
 # 65 kg heatshield is left out of `extra`: it is jettisoned during stage 3, so carrying it to orbit would
 # overstate what stage 4 has to push by 15 % while changing stage 1 by 0.3 %.
 "vega_c": dict(stages=[(141634, 11200, (240 + 2 * 279) / 3), (36239, 3230, 293.5),
                        (10567, 929, 295.9), (740, 695, 315.8)], payload=2300, extra=0.0,
                source="Wikipedia 'Vega C' stage table; stage 1 Isp weighted 1/3 SL per book Eq. 4:18"),
 "m_v": dict(stages=[(72000, 11000, (235 + 2 * 274) / 3), (33000, 3000, 289.0), (11000, 1000, 300.0)],
             payload=1800, extra=0.0,
             source="ISAS/JAXA M-V-7 configuration page; stage 1 Isp weighted 1/3 SL per book Eq. 4:18"),
 "scout_g1": dict(stages=[(12817, 1939, (229.0 + 2 * 254.8) / 3), (3768, 1064, 262.0),
                          (1299, 335, 293.5), (215, 41, 286.5)], payload=165, extra=0.0,
                  source="LTV Figure 4 masses; Isp: stages 3-4 Thiokol catalogue, stages 1-2 derived "
                         "(see the design file's source fields)"),
 "pegasus_xl": dict(stages=[(15014, 1369, 284.6), (3925, 416, 283.8), (770, 126, 281.7)], payload=450, extra=240,
                    source="Wikipedia Pegasus XL stage table; 'extra' = assumed fairing + adapter carried"),
 "vega": dict(stages=[(88365, 7330, (240 + 2 * 280) / 3), (24000, 1950, 287.5), (10500, 915, 296), (550, 131, 315.5)],
              payload=1430, extra=700, source="Wikipedia Vega stage table; 'extra' = assumed fairing + adapter"),
}


def ideal_dv(c):
    """Ideal (loss-free) delta-v of a vehicle built from its PUBLISHED stage masses."""
    stages, pl = c["stages"], c["payload"] + c.get("extra", 0.0)
    tot = 0.0
    for k, (p, i, e) in enumerate(stages):
        above = pl + sum(pp + ii for pp, ii, _ in stages[k + 1:])
        tot += G0 * e * math.log((above + i + p) / (above + i))
    return tot


def metrics(r):
    return dict(glom=r.glom_kg, length=r.geometry.total_length, dv=r.dv_required_mps,
                prop={s.index: s.m_prop_loaded_kg for s in r.stages}, dry={s.index: s.m_inert_burnout_kg for s in r.stages}, s={s.index: s.structural_factor_s for s in r.stages},
                tw={s.index: s.tw_ignition for s in r.stages}, ok=r.converged and not any(i.level == "ERROR" for i in r.issues),
                errors=[str(i) for i in r.issues if i.level == "ERROR"], fractions=[s.dv_mps / r.dv_required_mps for s in r.stages])


def try_size(path, ov, label):
    """Size a variant, returning None (plus the reason) instead of crashing the whole validation run."""
    try:
        return size_vehicle(load_design(path, ASSUMP, ov), keep_history=False), None
    except Exception as ex:                      # noqa: BLE001 - the reason is reported, not hidden
        print(f"    [{label}] not feasible: {type(ex).__name__}: {str(ex)[:160]}")
        return None, f"{type(ex).__name__}: {ex}"


results = {}
for key, ref in REF.items():
    print("---", key, flush=True)
    path = os.path.join(VAL, key + ".yaml")
    spec = load_design(path, ASSUMP)
    base = size_vehicle(spec, keep_history=False)
    opt = optimize_dv_split(spec)
    N = len(spec.stages)
    ov = {"vehicle.dv_fractions": opt["fractions"]}
    # The delta-v optimiser minimises mass and knows nothing about casing geometry, so on a vehicle with a
    # fat, short upper stage it can starve that stage below what its own diameter can physically hold -
    # M-V's 2.2 m third stage is the case that found this. That is a real limitation worth reporting, not a
    # reason for the whole validation run to die, so the optimised variant falls back to the as-published
    # split and the result says which split it used.
    opt_r, opt_err = try_size(path, ov, "optimised")
    opt_split_used = "optimised"
    if opt_r is None:
        opt_r, opt_split_used = base, "as-published (the optimised split was not geometrically feasible)"
        ov = {}
    lean = dict(ov)
    for j in range(N):
        lean[f"stages.{j}.residual_fraction"] = 0.0 if spec.stages[j].is_solid else 0.01
        lean[f"stages.{j}.loading_margin_fraction"] = 0.0
        lean[f"stages.{j}.inert_mass_margin_fraction"] = 0.0
    lean_r, lean_err = try_size(path, lean, "lean")
    # diagnostic: replace the book's SRM casing MER with each motor's PUBLISHED inert/propellant ratio
    cal_r = None
    if key in PUBK:
        cal = dict(ov)
        for j, (k_pub, _src) in ((j, PUBK[key][j + 1]) for j in range(N) if (j + 1) in PUBK[key]):
            cal[f"stages.{j}.motor.casing_mass_method"] = "mass_fraction"
            cal[f"stages.{j}.motor.casing_mass_fraction"] = k_pub
            cal[f"stages.{j}.inert_mass_margin_fraction"] = 0.0
        cal_r, cal_err = try_size(path, cal, "calibrated")
    # R18: the published stage-level regression for this motor's own case material, applied to every solid
    # stage. The book's answer stays in `base` - this is an additional column, not a replacement.
    rel_r = None
    if key in CASE_MATERIAL:
        rel_key = ("zandbergen_composite_C1" if CASE_MATERIAL[key] == "composite"
                   else "zandbergen_steel_S2")
        rel = dict(ov)
        touched = 0
        for j in range(N):
            if getattr(load_design(path, ASSUMP).stages[j], "is_solid", False):
                rel[f"stages.{j}.motor.casing_mass_method"] = rel_key
                rel[f"stages.{j}.inert_mass_margin_fraction"] = 0.0
                touched += 1
        # the same relation applies to SOLID STRAP-ONS, which is where most of these vehicles keep their
        # solid motors - and where most of the stages the relation was fitted to came from
        spec_b = load_design(path, ASSUMP)
        if getattr(spec_b, "boosters", None) is not None and spec_b.boosters.kind == "solid":
            rel["boosters.inert_mass_method"] = rel_key
            rel["boosters.inert_mass_margin_fraction"] = 0.0
            touched += 1
        if touched:
            rel_r, _rel_err = try_size(path, rel, "published relation")
    # full outputs (workbook + drawings) for the optimised split
    d = os.path.join(OUT, key)
    import tempfile, yaml, copy
    run_design = os.path.join(d, "design_used.yaml")
    os.makedirs(d, exist_ok=True)
    raw = open(path, encoding="utf-8").read()
    open(run_design, "w", encoding="utf-8").write(raw)
    # apply optimal fractions via a temp annotated copy
    from launch_vehicle.config_io import _Loader
    y = yaml.load(raw, Loader=_Loader)
    # Write the full outputs for whichever split actually sized. Forcing the optimised fractions here even
    # when they were infeasible is what used to kill the whole run on M-V, whose 2.2 m third stage cannot
    # hold the propellant the optimiser wants to give it.
    if opt_split_used == "optimised":
        y["vehicle"]["dv_fractions"] = dict(v=[round(float(x), 5) for x in opt["fractions"]], u="-", d="Stage dv shares (GLOM-minimising split from optimisation)", s="optimize_dv_split()", t="assumed")
    yaml.safe_dump(y, open(run_design, "w", encoding="utf-8"), sort_keys=False, width=220)
    try:
        run(run_design, ASSUMP, d, with_sens=False, with_opt=False, verbose=False)
    except Exception as ex:                      # noqa: BLE001 - reported, not hidden
        print(f"    [full outputs] not produced: {type(ex).__name__}: {str(ex)[:140]}")
    cap = None
    if key in CAP:
        cap = dict(dv_published_masses=ideal_dv(CAP[key]), dv_required=opt_r.dv_required_mps, source=CAP[key]["source"])
    results[key] = dict(ref=ref, base=metrics(base), opt=metrics(opt_r), lean=(metrics(lean_r) if lean_r else None),
                        calibrated=(metrics(cal_r) if cal_r else None),
                        relation=(metrics(rel_r) if rel_r else None),
                        relation_key=(rel_key if key in CASE_MATERIAL else None),
                        calibrated_k={k: v[0] for k, v in PUBK.get(key, {}).items()},
                        opt_fractions=opt["fractions"], opt_split_used=opt_split_used,
                        opt_infeasible=opt_err, cap=cap, n_stages=N,
                        solid=[bool(s.is_solid) for s in spec.stages])
    print(key, f"base {base.glom_kg:,.0f}  opt {opt_r.glom_kg:,.0f}  lean " + (f"{lean_r.glom_kg:,.0f}" if lean_r else "n/a")
               + (f"  calibrated {cal_r.glom_kg:,.0f}" if cal_r else "")
               + f"  ref {ref['glom'][0]:,}", "cap", None if not cap else f"{cap['dv_published_masses']:.0f} vs req {cap['dv_required']:.0f}")

# ---------------------------------------------------------------- propellant combination comparison (same mission)
combos = {}
for name in ("kerolox", "methalox", "hydrolox", "kerolox_hydrolox", "hypergolic"):
    path = os.path.join(VAL, f"combo_{name}.yaml")
    spec = load_design(path, ASSUMP)
    opt = optimize_dv_split(spec)
    r = size_vehicle(load_design(path, ASSUMP, {"vehicle.dv_fractions": opt["fractions"]}), keep_history=False)
    m = metrics(r)
    m["payload_fraction"] = r.payload_mass_kg / r.glom_kg
    m["prop_total"] = sum(s.m_prop_loaded_kg for s in r.stages)
    m["dry_total"] = sum(s.m_dry_kg for s in r.stages)
    m["fractions"] = opt["fractions"]
    combos[name] = m
    d = os.path.join(OUT, "combo_" + name)
    os.makedirs(d, exist_ok=True)
    import yaml
    from launch_vehicle.config_io import _Loader
    y = yaml.load(open(path, encoding="utf-8").read(), Loader=_Loader)
    y["vehicle"]["dv_fractions"] = dict(v=[round(float(x), 5) for x in opt["fractions"]], u="-", d="Stage dv shares (GLOM-minimising)", s="optimize_dv_split()", t="assumed")
    p2 = os.path.join(d, "design_used.yaml")
    yaml.safe_dump(y, open(p2, "w", encoding="utf-8"), sort_keys=False, width=220)
    run(p2, ASSUMP, d, with_sens=False, with_opt=False, verbose=False)
    print("combo", name, f"GLOM {r.glom_kg:,.0f} dry {m['dry_total']:,.0f} L {m['length']:.1f} ok={m['ok']}")

json.dump(dict(vehicles=results, combos=combos), open(os.path.join(OUT, "validation_results.json"), "w", encoding="utf-8"), indent=1, default=str)
