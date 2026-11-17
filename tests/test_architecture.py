"""Pinned-hardware architecture trades (architecture.py, method register M58).

The tests that matter here are the round-trip and the cross-family measurement. The round-trip is the
correctness test: pin a converged design, ask for the payload at the count it was designed with, and the answer
must come back to the design's own payload - if it does not, the phase model is being re-solved wrongly. The
cross-family measurement is the honesty test: Delta II and Ariane 6 really do fly one core across several
booster counts with published payloads for each, so pinning one variant and asking for another is checkable
against data, and the recorded numbers say how far off it is rather than asserting that it is right.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from launch_vehicle import architecture as ar          # noqa: E402
from launch_vehicle import boosters as bst             # noqa: E402
from launch_vehicle import families as fam             # noqa: E402
from launch_vehicle import performance as pf           # noqa: E402
from launch_vehicle.config_io import load_design       # noqa: E402
from launch_vehicle.convergence import size_vehicle    # noqa: E402

ASSUMP = os.path.join(ROOT, "config", "engineering_assumptions.yaml")
VAL = os.path.join(ROOT, "validation")

_CACHE = {}


def sized(name):
    if name not in _CACHE:
        _CACHE[name] = size_vehicle(load_design(os.path.join(VAL, name + ".yaml"), ASSUMP), keep_history=False)
    return _CACHE[name]


# --------------------------------------------------------------------------- the round trip
@pytest.mark.parametrize("name", ["ariane62", "ariane64", "h3_24l", "h2a_202", "soyuz2_1b", "delta2_7920"])
def test_pinning_reproduces_the_sizing_loop_at_the_reference_count(name):
    """At its own booster count a pinned vehicle must reproduce the sizing loop exactly: same per-stage
    delta-v, same GLOM, same lift-off T/W. This is what says the parallel phase is re-solved correctly rather
    than merely plausibly."""
    res = sized(name)
    pv = ar.pin(res)
    m_pl = res.payload_mass_kg
    assert pv.n_boosters == res.boosters.n_total
    per = pv.stage_delta_v(m_pl)
    for j, st in enumerate(res.stages):
        assert per[j] == pytest.approx(st.dv_mps, rel=1e-9), f"stage {j + 1} delta-v"
    assert pv.glom(m_pl) == pytest.approx(res.glom_kg, rel=1e-9)
    assert pv.liftoff_tw(m_pl) == pytest.approx(res.liftoff_tw, rel=1e-9)
    assert sum(per) == pytest.approx(res.dv_required_mps, rel=1e-6)


@pytest.mark.parametrize("name", ["ariane62", "ariane64", "h3_24l", "h2a_202", "soyuz2_1b", "delta2_7920"])
def test_solved_payload_returns_the_design_payload_at_the_reference_count(name):
    """The root-find closes on the design's own payload. The tolerance is 0.5 % because the payload adapter
    follows the payload through its own MER, so the root is a fixed point, not a closed form."""
    res = sized(name)
    out = ar.payload_for_architecture(ar.pin(res))
    assert out.flyable, out.reason
    assert out.is_reference
    assert out.payload_kg == pytest.approx(res.payload_mass_kg, rel=5e-3)
    assert out.glom_kg == pytest.approx(res.glom_kg, rel=5e-3)


def test_the_stored_booster_correction_is_not_used():
    """FrozenVehicle carries the parallel phase as one stored number; on Ariane 64 it is about -2,900 m/s,
    a bookkeeping correction between the serial rocket equation and the phase model. A pinned vehicle must not
    be using it, or every non-reference count would inherit it."""
    res = sized("ariane64")
    fv = pf.freeze(res)
    assert fv.booster_dv_mps < -1000.0, "the premise of this test has changed: the stored term is no longer a " \
                                        "large negative correction on Ariane 64"
    pv = ar.pin(res)
    assert pv.booster_dv_mps == 0.0
    # and the pinned answer is still right, which it could not be if the correction were simply dropped
    assert sum(pv.stage_delta_v(res.payload_mass_kg)) == pytest.approx(res.dv_required_mps, rel=1e-6)


def test_more_boosters_lift_more_and_fewer_lift_less():
    pv = ar.pin(sized("h3_24l"))
    ref = ar.payload_for_architecture(pv).payload_kg
    less = ar.payload_for_architecture(pv, n_total=2).payload_kg
    more = ar.payload_for_architecture(pv, n_total=6).payload_kg
    assert less < ref < more


# --------------------------------------------------------------------------- the published cross-check
# The published figures are NOT written here. They live in the family manifests beside the designs
# (validation/families/*/family.yaml), where each one carries its own source and must be marked
# `reference`, and where a user adding their own family gets the same check for free. Hard-coding them in a
# test file would have put the numbers the tool is graded against in the one place a user never looks, and
# let them drift from the designs they describe.
def _published(slug, key):
    """{booster count: published payload kg} for a shipped family, read from its manifest."""
    f = fam.find(ROOT, slug)
    out = {}
    for v in f.variants:
        n, kg = v.overrides.get("boosters.n_total"), v.published_kg("payload_kg")
        if n is not None and kg:
            out[int(n)] = kg
    assert out, f"family {slug!r} publishes no payloads; this test would pass vacuously"
    return out


DELTA2_PUBLISHED_KG = _published("delta_ii", "payload_kg")
ARIANE6_PUBLISHED_KG = _published("ariane_6", "payload_kg")


def test_pinned_smaller_variants_over_predict_their_published_payload():
    """MEASURED, not a target. Pinning a large variant's core and taking boosters off over-predicts the small
    variant, on both families that publish the numbers, in the same direction:

        Delta II 7920 core pinned -> 3 GEM-40:  about +23 % against the published 2,800 kg
        Delta II 7920 core pinned -> 4 GEM-40:  about +19 % against the published 3,200 kg
        Ariane 64 core pinned     -> 2 P120C:   about +52 % against the published 7,200 kg

    The mechanism is named in docs/ACCURACY.md 6b.5: the pinned core is the one the sizing loop drew for the
    reference mission, and `performance.required_dv_mps` holds ascent time at the reference design's value, so
    the extra gravity loss a thrust-starved configuration really pays is not charged to it. The band is wide
    and one-sided on purpose - this test exists to catch the sign silently flipping or the bias doubling, not to
    bless the number.
    """
    bias = {}
    for design, published in (("delta2_7920", DELTA2_PUBLISHED_KG), ("ariane64", ARIANE6_PUBLISHED_KG)):
        pv = ar.pin(sized(design))
        for n, ref_kg in published.items():
            if n == pv.reference_n_boosters:
                continue
            out = ar.payload_for_architecture(pv, n_total=n)
            assert out.flyable, f"{design} at n={n}: {out.reason}"
            bias[(design, n)] = out.payload_kg / ref_kg - 1.0
    for key, err in bias.items():
        assert err > 0.05, f"{key}: over-prediction became {err:+.1%}; the measured bias has changed sign or " \
                           f"vanished, which is a finding and needs docs/ACCURACY.md 6b.5 revisited"
        assert err < 0.90, f"{key}: over-prediction grew to {err:+.1%}, far beyond the measured range"
    assert bias[("delta2_7920", 3)] == pytest.approx(0.227, abs=0.06)
    assert bias[("delta2_7920", 4)] == pytest.approx(0.194, abs=0.06)
    assert bias[("ariane64", 2)] == pytest.approx(0.515, abs=0.10)


def test_the_payload_slope_against_booster_count_is_too_shallow():
    """The same finding stated as a slope, which is how a user reads the sweep. Real families lose more payload
    per booster removed than the pinned model does."""
    pv = ar.pin(sized("delta2_7920"))
    tool = (ar.payload_for_architecture(pv, n_total=9).payload_kg
            / ar.payload_for_architecture(pv, n_total=3).payload_kg)
    real = DELTA2_PUBLISHED_KG[9] / DELTA2_PUBLISHED_KG[3]
    assert real > tool, "the premise of docs/ACCURACY.md 6b.5 has changed: the model is no longer shallower"
    assert tool == pytest.approx(1.48, abs=0.10)
    assert real == pytest.approx(1.82, abs=0.01)


# --------------------------------------------------------------------------- refusals
def test_a_count_that_cannot_lift_off_is_refused_not_answered():
    """Ariane 64's hydrolox core alone weighs more than it pushes. A payload number for that stack would be a
    delta-v answer to a question physics has already settled."""
    out = ar.payload_for_architecture(ar.pin(sized("ariane64")), n_total=0)
    assert not out.flyable
    assert out.payload_kg is None, "an unflyable configuration must not report a capability"
    assert "thrust-to-weight" in out.reason and "cannot leave the pad" in out.reason
    # the delta-v-feasible payload is kept, under a name that cannot be mistaken for a capability
    assert out.dv_limited_payload_kg is not None and out.dv_limited_payload_kg > 0
    assert out.liftoff_tw <= 1.0
    assert out.payload_fraction is None


def test_boosters_outlasting_the_core_propellant_is_refused_with_the_phase_models_reason():
    """Adding air-lit boosters to Ariane 64 makes the core burn alongside strap-ons for a second interval it has
    no propellant for. The refusal must come from the phase model, not from a guess here."""
    out = ar.payload_for_architecture(ar.pin(sized("ariane64")), n_total=6, n_ground_lit=4)
    assert not out.flyable
    assert "runs out of propellant" in out.reason


def test_a_serial_vehicle_cannot_be_pinned_for_a_booster_trade():
    with pytest.raises(ar.ArchitectureError, match="no strap-on"):
        ar.pin(sized("vega"))


def test_an_air_lit_group_with_nothing_to_ignite_it_is_rejected():
    pv = ar.pin(sized("ariane64"))
    with pytest.raises(ar.ArchitectureError, match="nothing to ignite"):
        pv.with_boosters(4, n_ground_lit=0)
    with pytest.raises(ar.ArchitectureError, match="between 0 and"):
        pv.with_boosters(2, n_ground_lit=3)
    with pytest.raises(ar.ArchitectureError, match="cannot be negative"):
        pv.with_boosters(-1)


# --------------------------------------------------------------------------- the ignition split
def test_a_design_that_lights_them_all_on_the_ground_keeps_doing_so_at_any_count():
    """Ariane 64 lights all four P120C on the ground. Asking for six must not invent an air-lit group the
    design never had - that is a different vehicle, and usually an unflyable one."""
    pv = ar.pin(sized("ariane64"))
    assert pv.reference_n_ground_lit == pv.reference_n_boosters
    for n in (1, 2, 3, 6, 8):
        assert pv.with_boosters(n).n_ground_lit == n


def test_a_design_that_really_stages_its_ignition_keeps_its_ground_lit_count():
    """Delta II 7920 lights six GEM-40 on the ground and three in the air. The ground-lit count is what is
    preserved, capped at the total, so the lift-off thrust of a larger count does not grow without limit."""
    pv = ar.pin(sized("delta2_7920"))
    assert (pv.reference_n_boosters, pv.reference_n_ground_lit) == (9, 6)
    assert pv.with_boosters(4).n_ground_lit == 4
    assert pv.with_boosters(6).n_ground_lit == 6
    assert pv.with_boosters(12).n_ground_lit == 6


def test_liftoff_thrust_follows_the_ground_lit_count_only():
    """An air-lit booster is mass at lift-off and no thrust, so Delta II's T/W must peak at its ground-lit
    count and fall after it. A model that credited air-lit thrust at lift-off would rise monotonically."""
    pv = ar.pin(sized("delta2_7920"))
    tw = {}
    for n in (5, 6, 7, 9, 12):
        out = ar.payload_for_architecture(pv, n_total=n)
        tw[n] = out.liftoff_tw if out.flyable else pv.with_boosters(n).liftoff_tw(0.0)
    assert tw[6] > tw[5]
    assert tw[7] < tw[6] and tw[9] < tw[7] and tw[12] < tw[9]


def test_phase_sequence_is_what_answers_the_attach_stage():
    """The attach stage's delta-v must equal the phase model's total for that stage, not the serial equation's."""
    res = sized("h2a_202")
    pv = ar.pin(res).with_boosters(3)
    phases = pv.parallel_phases(9000.0)
    per = pv.stage_delta_v(9000.0)
    assert per[pv.booster_attach_stage - 1] == pytest.approx(bst.total_dv(phases), rel=1e-12)
    assert any("Parallel burn" in p.name for p in phases)
    assert any("Jettison" in p.name for p in phases)
    assert any("Core stage alone" in p.name for p in phases)


# --------------------------------------------------------------------------- the other direction
def test_sizing_a_core_around_a_fixed_booster_count_moves_the_core():
    """The reverse trade is the sizing loop's own job: with more strap-ons the loop should draw a smaller core
    for the same payload, because the boosters do more of the work."""
    spec = load_design(os.path.join(VAL, "h2a_202.yaml"), ASSUMP)
    two = ar.core_for_boosters(spec, 2)
    four = ar.core_for_boosters(spec, 4)
    assert four.stages[0].m_prop_loaded_kg < two.stages[0].m_prop_loaded_kg
    assert four.glom_kg > two.glom_kg          # the strap-ons themselves outweigh what the core gives back
    assert four.payload_mass_kg == two.payload_mass_kg == spec.payload_mass_kg


def test_core_for_boosters_does_not_mutate_the_spec_it_is_given():
    spec = load_design(os.path.join(VAL, "h2a_202.yaml"), ASSUMP)
    before = (spec.boosters.n_total, spec.boosters.n_ground_lit)
    ar.core_for_boosters(spec, 4)
    assert (spec.boosters.n_total, spec.boosters.n_ground_lit) == before


# --------------------------------------------------------------------------- the sweep and its table
def test_sweep_spans_the_reference_and_marks_it():
    pv = ar.pin(sized("h3_24l"))
    rows = ar.booster_count_sweep(pv)
    counts = [r.n_boosters for r in rows]
    assert 0 in counts and pv.reference_n_boosters in counts
    assert sum(1 for r in rows if r.is_reference) == 1


def test_sweep_table_reports_the_change_against_the_reference_and_carries_refusals():
    pv = ar.pin(sized("ariane64"))
    rows = ar.sweep_table(ar.booster_count_sweep(pv, counts=[0, 2, 4]))
    assert rows[0][1] is None and rows[0][5]            # n=0 refused, with a reason
    assert rows[2][4] == pytest.approx(0.0, abs=1.0)    # the reference row is its own baseline
    assert rows[1][4] < 0                               # two boosters lift less
    assert rows[1][1] < rows[2][1]


def test_payload_fraction_is_reported_and_consistent():
    out = ar.payload_for_architecture(ar.pin(sized("h3_24l")), n_total=3)
    assert out.payload_fraction == pytest.approx(out.payload_kg / out.glom_kg, rel=1e-12)
    assert 0.0 < out.payload_fraction < 0.1
