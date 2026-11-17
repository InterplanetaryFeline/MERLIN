"""Regression tests for the real-vehicle validation cases (validation/*.yaml). Published figures and sources are listed in tools/run_validation.py.
These tests pin the *documented* agreement levels; they are not proof of predictive accuracy."""
import math
import os
import pytest
from helpers import ROOT, ASSUMP
from launch_vehicle.config_io import load_design
from launch_vehicle.convergence import size_vehicle, SizingError
from launch_vehicle.units import G0

V = lambda n: os.path.join(ROOT, "validation", n + ".yaml")
LEAN = lambda N, fr=None: dict({f"stages.{j}.{k}": v for j in range(N) for k, v in (("residual_fraction", 0.01), ("loading_margin_fraction", 0.0), ("inert_mass_margin_fraction", 0.0))},
                               **({"vehicle.dv_fractions": fr} if fr else {}))


def test_all_validation_cases_converge_without_hard_errors():
    for n in ("electron", "falcon9", "titan2", "saturn5", "zhuque2", "combo_kerolox", "combo_methalox", "combo_hydrolox", "combo_kerolox_hydrolox", "combo_hypergolic"):
        r = size_vehicle(load_design(V(n), ASSUMP))
        assert r.converged, n
        assert not [i for i in r.issues if i.level == "ERROR"], (n, [str(i) for i in r.issues if i.level == "ERROR"])
        assert sum(s.dv_check_mps for s in r.stages) == pytest.approx(r.dv_required_mps, abs=1e-4)


def test_saturn_v_with_book_dv_split_matches_published_gross_mass_within_5_percent():
    # Basis: Wikipedia 2,822,171-2,965,241 kg; dv split from Book Example 5.1. (Model result: about -2 %.)
    r = size_vehicle(load_design(V("saturn5"), ASSUMP))
    assert r.glom_kg == pytest.approx(2894000.0, rel=0.05)
    assert 12000.0 < r.dv_required_mps < 12800.0                    # book Example 5.1 ideal sum 12,133 m/s plus losses/rotation


def test_falcon_9_and_titan_ii_with_lean_margins_within_8_percent():
    # Diagnostic (not calibration): with 1 % residual, no loading margin and no mass-growth margin, as in operational vehicles.
    f9 = size_vehicle(load_design(V("falcon9"), ASSUMP, LEAN(2, [0.40, 0.60])))
    assert f9.glom_kg == pytest.approx(549054.0, rel=0.08)
    t2 = size_vehicle(load_design(V("titan2"), ASSUMP, LEAN(2, [0.38, 0.62])))
    assert t2.glom_kg == pytest.approx(154000.0, rel=0.08)


def test_default_margins_make_the_model_conservative_versus_real_vehicles():
    # With the book's 2 % residual + 0.5 % margin + 10 % mass-growth margin the prediction exceeds the published GLOM for these vehicles.
    for n, pub in (("falcon9", 549054.0), ("titan2", 154000.0), ("electron", 13000.0)):
        assert size_vehicle(load_design(V(n), ASSUMP)).glom_kg > pub


def test_delta_v_regression_is_consistent_with_published_stage_masses():
    # Ideal dv of the published Falcon 9 and Titan II stage masses is within +/-5 % of the book-regression requirement for their missions.
    def ideal(stages, payload):
        tot = 0.0
        for k, (p, i, e) in enumerate(stages):
            above = payload + sum(pp + ii for pp, ii, _ in stages[k + 1:])
            tot += G0 * e * math.log((above + i + p) / (above + i))
        return tot
    f9 = ideal([(395700, 25600, (285 + 2 * 313) / 3), (107500, 3900, 348)], 22800)
    t2 = ideal([(117800, 6700, (258 + 2 * 296) / 3), (28900, 2400, 316)], 3574)
    rf = size_vehicle(load_design(V("falcon9"), ASSUMP))
    rt = size_vehicle(load_design(V("titan2"), ASSUMP))
    assert f9 == pytest.approx(rf.dv_required_mps, rel=0.05)
    assert t2 == pytest.approx(rt.dv_required_mps, rel=0.05)


def test_book_example_5_1_saturn_v_ideal_speed_reproduced():
    # Basis: Book Example 5.1 (p.283-284): ideal speed 3,099 + 4,775 + 4,259 = 12,133 m/s
    st = [(2080e3, 240e3, 263), (450e3, 36e3, 419), (108e3, 11e3, 426)]
    tot, pl = 0.0, 50e3
    for k, (p, i, e) in enumerate(st):
        above = pl + sum(pp + ii for pp, ii, _ in st[k + 1:])
        tot += G0 * e * math.log((above + i + p) / (above + i))
    assert tot == pytest.approx(12133.0, rel=2e-3)


def test_propellant_type_ordering_on_the_same_mission():
    # Physics expectation: higher Isp (LH2 > CH4 > RP-1 > hypergolic) gives lower gross mass for the same payload/orbit/stage count.
    g = {n: size_vehicle(load_design(V("combo_" + n), ASSUMP)).glom_kg for n in ("hydrolox", "kerolox_hydrolox", "methalox", "kerolox", "hypergolic")}
    assert g["hydrolox"] < g["kerolox_hydrolox"] < g["methalox"] < g["kerolox"] < g["hypergolic"]
    # dv requirements are consistent across combinations (same mission): within 2 % (they differ only through burn time in the regression)
    dvs = [size_vehicle(load_design(V("combo_" + n), ASSUMP)).dv_required_mps for n in g]
    assert max(dvs) / min(dvs) < 1.02


# ---------------------------------------------------------------- v0.3: solids, strap-ons and small launchers
#: every serial-solid check case. These are the ones that exercise the solid mass model, as opposed to the
#: BOOSTED_CASES below, whose booster masses are published inputs and so test the phase model instead.
SOLID_CASES = ("pegasus_xl", "vega", "epsilon", "scout_g1", "vega_c", "m_v")
BOOSTED_CASES = ("delta2_7920", "atlas5_551", "ariane5_eca")


#: Cases that converge but whose AS-PUBLISHED split produces a design the tool then refuses to build.
#:
#: This is not a test being relaxed to pass. The errors are correct outputs. The tool sizes these vehicles
#: 40-60% too heavy (docs/ACCURACY.md section 2), it computes each nozzle from the thrust the SIZED vehicle
#: needs, and a nozzle sized for a 54 t Scout does not fit on a 1.14 m case. The geometry error is a true
#: statement about the oversized design, and suppressing it by lowering an assumed expansion ratio would
#: hide the oversizing rather than fix it. What is asserted for these is that they converge, close their
#: delta-v, and produce only the geometry errors that follow from being too heavy - never a mass or
#: propellant error, which would mean something different was wrong.
#: Scout G-1 came OFF this list in v0.26 and that is the point of the assertion below: once composite
#: solid stages moved to kibbey_medium it is no longer sized 40-60 % heavy, its nozzles shrank with it,
#: and the geometry error it used to produce correctly disappeared. M-V stays, because M-V is the one
#: solid case still on the book flat constant (see its design file).
OVERSIZED_GEOMETRY = {"m_v": {"ENGFIT"}}


def test_v03_validation_cases_converge_without_hard_errors():
    for n in SOLID_CASES + BOOSTED_CASES + ("firefly_alpha",):
        r = size_vehicle(load_design(V(n), ASSUMP))
        assert r.converged, n
        errs = [i for i in r.issues if i.level == "ERROR"]
        allowed = OVERSIZED_GEOMETRY.get(n, set())
        unexpected = [str(i) for i in errs if i.code not in allowed]
        assert not unexpected, (n, unexpected)
        if allowed:
            assert errs, (f"{n} is listed in OVERSIZED_GEOMETRY but no longer produces those errors - if the "
                          "mass model improved enough to fix it, take it off the list")
        assert sum(s.dv_check_mps for s in r.stages) == pytest.approx(r.dv_required_mps, abs=1e-3), n


def test_boosted_vehicles_close_their_mass_and_phase_budgets():
    from launch_vehicle.boosters import total_dv
    for n in BOOSTED_CASES:
        r = size_vehicle(load_design(V(n), ASSUMP))
        b = r.boosters
        assert b is not None, n
        total = (r.payload_mass_kg + r.paf_mass_kg + r.fairing_mass_kg + b.m_total_kg
                 + sum(s.m_dry_kg + s.m_prop_loaded_kg for s in r.stages))
        assert total == pytest.approx(r.glom_kg, rel=1e-12), n
        s1 = r.stages[b.attach_stage - 1]
        assert total_dv(s1.phases) == pytest.approx(s1.dv_mps, rel=1e-6), n
        assert s1.burn_time_s > b.burn_time_s, n                      # the core must outlast the strap-ons


def test_delta_ii_air_lit_boosters_produce_three_powered_phases():
    r = size_vehicle(load_design(V("delta2_7920"), ASSUMP))
    assert r.boosters.n_ground_lit == 6 and r.boosters.n_total == 9
    powered = [p for p in r.stages[0].phases if p.duration_s > 0]
    assert len(powered) == 3
    assert "ground-lit" in powered[0].name and "air-lit" in powered[1].name


def test_solid_casing_mer_is_conservative_against_real_motors():
    """Documented finding: the book's SRM casing MER (Eq. 8:18) predicts a heavier motor than modern
    filament-wound hardware. Published inert/propellant ratios: Pegasus XL 0.091/0.106/0.164, Vega 0.083/0.081/0.087."""
    published = {"pegasus_xl": [1369 / 15014, 416 / 3925, 126 / 770], "vega": [7330 / 88365, 1950 / 24000, 915 / 10500]}
    from launch_vehicle.solid_motor import K_SRM
    for name, ks in published.items():
        for k in ks[:2]:                                              # the big lower stages
            assert K_SRM["composite"] > k                             # the MER is heavier than the real motor

    # The finding is about the BOOK relation, so force it rather than inherit the design file's method -
    # Vega ships with kibbey_medium since v0.26. Forced, the book path still over-predicts by about half.
    s_pub = 7330.0 / (7330.0 + 88365.0)
    forced = size_vehicle(load_design(V("vega"), ASSUMP, {
        f"stages.{j}.motor.casing_mass_method": "book_composite" for j in range(3)}))
    assert 1.3 < forced.stages[0].structural_factor_s / s_pub < 1.8   # ~+50 %, as the validation report says

    # And the other half of the same statement: the relation that replaced it is close. Measured 0.0765
    # against a published 0.0766 on Vega's P80. This is the assertion that would catch a regression back
    # toward the book's constant, which the one above cannot, since it now forces its own method.
    shipped = size_vehicle(load_design(V("vega"), ASSUMP))
    assert 0.9 < shipped.stages[0].structural_factor_s / s_pub < 1.15, (
        f"the shipped composite relation should land near the published structural factor, got "
        f"{shipped.stages[0].structural_factor_s:.4f} against {s_pub:.4f}")


def test_air_launch_credit_reduces_the_requirement_and_needs_user_losses():
    from launch_vehicle.validation import InputError
    r = size_vehicle(load_design(V("pegasus_xl"), ASSUMP))
    line = [l for l in r.budget.lines if "Air-launch" in l.name]
    assert len(line) == 1 and line[0].value_mps < 0
    assert r.dv_required_mps < 8600.0                                 # below a comparable ground launch
    with pytest.raises(InputError, match="air-launched"):
        size_vehicle(load_design(V("pegasus_xl"), ASSUMP, {"mission.losses.model": "book_penalty"}))


def test_small_launchers_are_over_predicted_but_the_calibrated_run_is_close():
    """Vega with each motor's published casing ratio lands within 10 % of the real vehicle."""
    N = 4
    ov = {f"stages.{j}.motor.casing_mass_method": "mass_fraction" for j in range(3)}
    ov.update({f"stages.{j}.motor.casing_mass_fraction": k for j, k in
               ((0, 7330 / 88365), (1, 1950 / 24000), (2, 915 / 10500))})
    ov.update({f"stages.{j}.inert_mass_margin_fraction": 0.0 for j in range(N)})
    ov["vehicle.dv_fractions"] = [0.2205, 0.1796, 0.2088, 0.3910]     # GLOM-minimising split from optimize_dv_split()
    r = size_vehicle(load_design(V("vega"), ASSUMP, ov))
    assert r.glom_kg == pytest.approx(137000.0, rel=0.10)


# ------------------------------------------------------------------ the v0.27 confound-breaking cases
def test_the_long_march_12_published_payload_figures_are_not_mutually_consistent():
    """This case was added hoping three published pairings on one vehicle would test the budget's altitude
    dependence with the hardware held fixed. They cannot, and the reason is in the published data.

    The CZ-12 infobox gives 12,000 kg to 200 km, 10,000 kg to 300 km and 6,000 kg to 700 km SSO. Going from
    200 km to 300 km drops the published payload by 16.7 %. But circular speed FALLS 59 m/s over that
    change, and this tool's whole budget moves by only -75 m/s; a delta-v change of that size cannot cost a
    sixth of the payload at an upper-stage Isp of 341.5 s. The three figures are therefore quoted on
    different assumptions - margin, inclination or launch site - and are not a self-consistent performance
    curve. The 700 km SSO figure is separately unusable here: SSO needs about 98 deg of inclination and
    every CZ-12 flight has been from Wenchang at 19.6 deg latitude, which cannot reach it without a dog-leg
    this tool does not model.

    So the case ships as a single mission at its headline 12,000 kg / 200 km figure, and this test exists to
    stop a future edit from "fixing" the case to hit all three - which would mean tuning inputs to match
    numbers that disagree with each other.
    """
    base = load_design(V("cz12"), ASSUMP)
    assert base.payload_mass_kg == 12000.0, "the headline pairing is the 200 km one"
    dv = {}
    for h in (200.0, 300.0):
        r = size_vehicle(load_design(V("cz12"), ASSUMP, {"mission.orbit.perigee_altitude_km": h}))
        dv[h] = r.dv_required_mps
    swing = abs(dv[300.0] - dv[200.0])
    assert swing < 250.0, (
        f"200->300 km should move the budget by well under 250 m/s, got {swing:.0f} m/s - if this grew, the "
        f"altitude handling changed and the argument below needs redoing")
    # the published payload drop implies a delta-v change far larger than that
    implied = 341.5 * 9.80665 * math.log(12000.0 / 10000.0)
    assert implied > 3.0 * swing, (
        f"the published 12,000->10,000 kg drop implies at least {implied:.0f} m/s of extra delta-v at the "
        f"upper-stage Isp, against the {swing:.0f} m/s the orbits actually differ by - that is the "
        f"inconsistency this test records")


def test_minotaur1_stage_masses_close_against_the_published_liftoff_mass():
    """The consistency check that makes this case worth having, asserted rather than trusted.

    The four stage gross/empty masses come from Encyclopedia Astronautica and the 36,200 kg lift-off mass
    from the Minotaur I User's Guide via Wikipedia - different sources. Summing the stages plus the payload
    must land just under the published lift-off mass, with the remainder being fairing, avionics and
    adapter. If a future edit breaks that, one of the two sources has been mistranscribed.
    """
    stages = [(20785, 2292), (6237, 795), (3925, 416), (770, 126)]
    payload = 580.0
    total = sum(p + i for p, i in stages) + payload
    published = 36200.0
    residual = published - total
    assert 0.0 < residual < 600.0, (
        f"stages + payload = {total:,.0f} kg against a published {published:,.0f} kg, leaving "
        f"{residual:,.0f} kg for fairing/avionics/adapter - outside the plausible range, so one of the "
        f"two independent sources is being read wrong")
    r = size_vehicle(load_design(V("minotaur1"), ASSUMP))
    assert r.converged
    assert abs(r.glom_kg - published) / published < 0.25, (
        f"Minotaur I sized to {r.glom_kg:,.0f} kg against {published:,.0f} kg")


def test_the_new_cases_are_the_low_orbit_small_payload_examples_the_set_lacked():
    """Why these two vehicles and not two more small SSO launchers.

    docs/ACCURACY.md section 6b could not separate a payload effect from an altitude effect because the set
    had no small payload at a low orbit. This pins that the gap is now covered, so that a future edit which
    re-points either case at a high orbit has to confront the reason it was added.
    """
    low_small = []
    for name in ("minotaur1", "m_v", "cz12", "titan2", "falcon9"):
        spec = load_design(V(name), ASSUMP)
        h = spec.mission["perigee_altitude_m"] / 1e3
        pl = spec.payload_mass_kg
        if h <= 300.0:
            low_small.append((name, pl, h))
    payloads = [pl for _n, pl, _h in low_small]
    assert min(payloads) < 1000.0, (
        f"no case under 1,000 kg of payload flies to 300 km or below any more: {low_small}")
    assert max(payloads) > 10000.0, (
        f"the low-orbit group needs a large payload too, or altitude and payload are confounded again: "
        f"{low_small}")


def test_the_ariane_pair_shows_what_minimal_stage_sizing_cannot_reproduce():
    """Ariane 62 and 64 share one core, and that is the whole point of carrying both.

    A62 and A64 fly the SAME LLPM and the SAME ULPM; only the booster count and the payload change. So the
    A62's core is sized for the A64's mission, not its own - it holds 140,000 kg where a minimum-mass core
    for the A62 mission needs about 52,000 kg. A tool that sizes every stage minimally must therefore
    under-predict the A62 badly and the A64 much less, and the pair measures exactly that.

    This is not a defect being excused: it is the boundary of what "size each stage for its share of the
    delta-v" can represent, and a reader comparing a real vehicle against this tool needs it stated.
    """
    errs = {}
    for name, published in (("ariane62", 530000.0), ("ariane64", 860000.0)):
        r = size_vehicle(load_design(V(name), ASSUMP))
        assert r.converged, f"{name} must size"
        errs[name] = (r.glom_kg - published) / published
    assert errs["ariane62"] < -0.10, (
        f"the A62 is expected to come out LIGHT, because its core is sized for the A64: got "
        f"{100*errs['ariane62']:+.1f}%")
    assert abs(errs["ariane64"]) < abs(errs["ariane62"]), (
        f"the A64 should be the better-reproduced of the pair - its core is sized for its own mission. "
        f"A62 {100*errs['ariane62']:+.1f}%, A64 {100*errs['ariane64']:+.1f}%")


def test_a_core_that_cannot_outlast_its_boosters_is_still_refused():
    """The R34 tolerance must not have turned a real constraint into a silent pass.

    Ariane 62's core burns 323.4 kg/s at 1,370 kN and 432 s, so over the P120C's 134 s it must carry at
    least 43,333 kg. A stage-1 delta-v share below 0.50 starves it below that, and the design has to be
    REFUSED rather than quietly sized - this is the phasing check, not the tank check, and nothing in R34
    touched it.
    """
    with pytest.raises(SizingError) as ei:
        size_vehicle(load_design(V("ariane62"), ASSUMP, {"vehicle.dv_fractions": [0.44, 0.56]}))
    assert "propellant" in str(ei.value).lower(), str(ei.value)[:200]


def test_the_shared_core_pattern_holds_across_the_whole_hydrolox_booster_group():
    """Four vehicles, one explanation, and it orders them correctly.

    Ariane 62, Ariane 64, SLS Block 1 and H3-24L are all hydrolox cores with large solid boosters - the
    class R34 unblocked. They differ in ONE respect that matters to a tool which sizes every stage minimally
    for its own mission: how far each vehicle's core is oversized relative to that mission, because a real
    core is shared across a family.

        H3-24L       core sized for its own class            smallest error
        Ariane 64    core sized for itself
        SLS Block 1  core shared with Block 1B and Block 2
        Ariane 62    core sized for the A64, not the A62     largest error

    Every one of them should come out LIGHT, and the A62 should be the worst. If that ordering ever breaks,
    the explanation in docs/ACCURACY.md section 6b.3 is wrong and should be rewritten rather than patched.
    """
    errs = {}
    for name, published in (("h3_24l", 575000.0), ("ariane64", 860000.0),
                            ("sls_block1", 2610000.0), ("ariane62", 530000.0)):
        r = size_vehicle(load_design(V(name), ASSUMP))
        assert r.converged, f"{name} must size"
        errs[name] = (r.glom_kg - published) / published
    for name, e in errs.items():
        assert e < 0.0, (
            f"{name} came out HEAVY at {100*e:+.1f}%. Every vehicle in this group should be light, because "
            f"its real core carries more propellant than its own mission needs")
    assert abs(errs["ariane62"]) == max(abs(v) for v in errs.values()), (
        f"the A62 should be the worst of the group - its core is sized for the A64: "
        + ", ".join(f"{k} {100*v:+.1f}%" for k, v in errs.items()))
    assert abs(errs["h3_24l"]) < abs(errs["ariane62"]), (
        f"H3-24L, whose core is closest to minimally sized, should beat the A62: "
        f"{100*errs['h3_24l']:+.1f}% vs {100*errs['ariane62']:+.1f}%")
