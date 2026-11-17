"""Which check cases are sourced well enough for their error to mean anything?

A validation table that prints "Zhuque-2 -31.7 %" invites the reader to blame the mass model. For Zhuque-2
that is wrong: its stage-1 Isp is tagged `assumed` with the source text "ASSUMED (TQ-12 Isp not found)",
and Isp is the highest-leverage input a case has. These tests keep that distinction visible so an input
assumption is never read as a model measurement.
"""
import os
import sys

import pytest
from helpers import *                                        # noqa: F401,F403

sys.path.insert(0, os.path.join(ROOT, "tools"))
import reference_quality as rq                               # noqa: E402

CASES = os.path.join(ROOT, "validation")


def audited():
    out = {}
    for f in sorted(os.listdir(CASES)):
        if not f.endswith(".yaml") or f.startswith("combo_"):
            continue
        out[f[:-5]] = rq.audit(os.path.join(CASES, f))
    return out


def test_every_check_case_is_mostly_sourced_rather_than_assumed():
    """Not a style rule: a case that is mostly assumptions cannot validate anything."""
    for name, (counts, _weak) in audited().items():
        tot = sum(v for k, v in counts.items() if k != "other")
        assert tot > 100, f"{name}: only {tot} annotated inputs, which is too few to be a real case"
        sourced = counts["reference"] + counts["user"]
        assert sourced > counts["assumed"], (
            f"{name}: {counts['assumed']} assumed inputs against {sourced} sourced ones - this case would "
            f"be measuring its own assumptions")


def test_the_cases_whose_critical_inputs_are_assumed_are_exactly_the_known_ones():
    """A tripwire, not a target.

    If a NEW case appears here, its GLOM error is not evidence about the model and must not be reported as
    though it were. If one LEAVES, something was sourced properly and the list should shrink. Either way the
    change should be deliberate, which is why the list is pinned rather than counted.
    """
    weak = {n for n, (_c, w) in audited().items() if w}
    expected = {"zhuque2", "scout_g1", "delta2_7920", "ariane5_eca", "atlas5_551",
                "delta4_heavy", "firefly_alpha", "h2a_202", "soyuz2_1b",
                # cz12 joined in v0.27 and belongs here: the CZ-12 flies the UPRATED YF-100K, whose Isp is
                # not published, so the base YF-100's 300/335 s is used and tagged assumed. Its thrust is
                # derived from the published 1,250 kN sea-level figure, with the arithmetic in the source.
                "cz12",
                # Both Ariane cases: the Vulcain 2.1's own Isp is not published (the Vulcain 2's is used),
                # and the P120C's sea-level Isp is not stated - the same gap as the H-IIA SRB-A case.
                "ariane62", "ariane64",
                # SLS: the RS-25's sea-level Isp is derived from the published thrust ratio rather than
                # published, and the SRB's sea-level Isp is not stated. H3: no sea-level Isp is published
                # for the LE-9 or the SRB-3, and the SRB-3's inert mass is derived from the SRB-A3.
                "sls_block1", "h3_24l"}
    assert weak == expected, (
        f"the reference-weak set changed.\n  now missing: {sorted(expected - weak)}\n"
        f"  newly weak: {sorted(weak - expected)}\n"
        f"If a case became weak, do not reduce its error by editing the assumed value - source it or say "
        f"the error does not measure the model.")


def test_zhuque2_is_the_case_whose_isp_is_assumed_from_nothing():
    """The distinction that matters, and why Scout is not in the same position.

    Most of the reference-weak cases above assume ONE value, usually a sea-level Isp inferred from a
    published vacuum figure. Scout's three carry real sources - an SAE paper on the Algol III, and a
    documented derivation for the Castor. Zhuque-2's three say "not found", and its engine is a named
    placeholder. That is the case whose error cannot be attributed.
    """
    counts, weak = rq.audit(os.path.join(CASES, "zhuque2.yaml"))
    isp = {p.split(".")[-1]: (v, src) for p, v, src in weak}
    assert set(isp) >= {"isp_sl_s", "isp_vac_s"}, f"expected the Isp values to be the weak ones, got {isp}"
    for leaf, (_v, src) in isp.items():
        assert "not found" in src.lower() or "assumed" in src.lower(), (
            f"zhuque2 {leaf} is tagged assumed but its source text no longer says so: {src!r}. If a real "
            f"figure was found, retag it `reference` and this test should be updated to match.")

    scout_counts, scout_weak = rq.audit(os.path.join(CASES, "scout_g1.yaml"))
    assert scout_weak, "scout_g1 is expected to carry assumed-tagged Isp values"
    assert any("NTRS" in (s or "") or "SAE" in (s or "") or "DERIVED" in (s or "")
               for _p, _v, s in scout_weak), (
        "Scout's assumed Isp values are supposed to carry a real source or a stated derivation - if they no "
        "longer do, the two cases are not distinguishable and this test's premise is gone")


def test_an_assumed_isp_moves_glom_enough_to_matter():
    """The reason an assumed Isp disqualifies a case, measured rather than asserted.

    Zhuque-2 ships with 300/330 s on stage 1 and 355 s on stage 2, all assumed. Merlin 1D - a real
    gas-generator engine of the same class - is 285/313 and 348 s. Swapping to Merlin-class values moves
    Zhuque-2's lift-off mass by over 15 %, which is half its reported error. The values are NOT adopted;
    this only pins that the sensitivity is large enough to make the error uninterpretable.
    """
    from launch_vehicle.config_io import load_design
    from launch_vehicle.convergence import size_vehicle
    path = os.path.join(CASES, "zhuque2.yaml")
    shipped = size_vehicle(load_design(path, ASSUMP)).glom_kg
    lower = size_vehicle(load_design(path, ASSUMP, {
        "stages.0.engine.isp_sl_s": 285.0,
        "stages.0.engine.isp_vac_s": 315.0,
        "stages.1.engine.isp_vac_s": 340.0})).glom_kg
    change = (lower - shipped) / shipped
    assert change > 0.15, (
        f"a 15 s Isp change should move GLOM by more than 15 %, got {100*change:.1f}% "
        f"({shipped:,.0f} -> {lower:,.0f} kg)")
