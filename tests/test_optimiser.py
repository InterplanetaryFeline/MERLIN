"""The delta-v allocation search: that it finds the feasible region, and that what it finds is applied.

Two defects motivated this file and both are pinned here.

The search used to go straight to a local search from the equal split. On `examples/example_3stage_leo.yaml`
the equal split does not size, every neighbouring point is equally infeasible, and Nelder-Mead on a flat
penalty gave up after 11 evaluations and returned the split it started from - reporting it as the optimum,
with `success` False that nothing checked. The GUI then wrote that worse split into the user's design and
told them it was about a trillion kilograms lighter.

And the optimum was never applied. The report printed an optimal split beside a vehicle sized from the
user's own split: two different rockets in one document, with the better one reachable only by reading the
number off the report and typing it back in by hand.
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from launch_vehicle import optimization as opt                                         # noqa: E402
from launch_vehicle import convergence as cvg                                          # noqa: E402
from launch_vehicle.config_io import load_design                                       # noqa: E402
from launch_vehicle.convergence import size_vehicle                                    # noqa: E402
from launch_vehicle.validation import InputError                                       # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSUMPTIONS = os.path.join(ROOT, "config", "engineering_assumptions.yaml")
DEFAULT = os.path.join(ROOT, "config", "default_design.yaml")
THREE_STAGE = os.path.join(ROOT, "examples", "example_3stage_leo.yaml")


def spec_of(path):
    return load_design(path, ASSUMPTIONS)


# ---------------------------------------------------------------- the seed of the sizing loop (Phase 0)

def test_the_converged_answer_does_not_depend_on_where_the_loop_starts():
    """The sizing loop is a fixed-point iteration and needs a first guess. If the answer moved with the
    guess, the loop would have more than one fixed point and every number downstream would be a function of
    where the search began. Measured across the seeds that can start at all: it does not move."""
    spec = spec_of(DEFAULT)
    base = cvg.SEED_S
    try:
        got = []
        for s in (0.05, 0.08, 0.10, 0.14, 0.18):
            cvg.SEED_S = s
            got.append(size_vehicle(spec, keep_history=False).glom_kg)
    finally:
        cvg.SEED_S = base
    spread = (max(got) - min(got)) / min(got)
    assert spread < 1e-6, f"GLOM moved {100 * spread:.2e} % with the seed: {got}"


# ---------------------------------------------------------------- the search finds the feasible region

def test_a_three_stage_vehicle_whose_equal_split_does_not_size_is_still_optimised():
    """THE regression. The equal split of this design does not size at all, so a local search started there
    sees a flat penalty in every direction. The answer is nonetheless there to be found."""
    spec = spec_of(THREE_STAGE)
    baseline = size_vehicle(spec).glom_kg
    out = opt.optimize_dv_split(spec)
    assert out["success"], out["note"]
    assert out["glom_kg"] < baseline, (
        f"found {out['glom_kg']:,.0f} kg against a baseline of {baseline:,.0f} kg - no improvement at all")
    assert out["improvement_rel"] > 0.02, f"only {100 * out['improvement_rel']:.2f} % better"
    # and it must not simply hand back the equal split it would once have returned
    assert max(out["fractions"]) - min(out["fractions"]) > 0.05, out["fractions"]


def test_the_equal_split_really_is_infeasible_on_that_design():
    """Guards the test above: if this design ever becomes feasible at the equal split, the regression it
    pins has stopped being tested and someone should notice."""
    ev = opt.evaluate(spec_of(THREE_STAGE), [1 / 3, 1 / 3, 1 / 3], "glom")
    assert ev["rung"] != 0, "the equal split now sizes; this file's main regression no longer bites"


def test_the_two_stage_answer_did_not_move():
    """The rebuild must not disturb a case the old search already got right."""
    out = opt.optimize_dv_split(spec_of(DEFAULT))
    assert out["success"]
    assert abs(out["fractions"][0] - 0.351) < 0.01, out["fractions"]
    assert abs(out["glom_kg"] - 397_246) < 2_000, out["glom_kg"]


def test_a_search_that_finds_nothing_says_so_instead_of_returning_a_penalty():
    """The old code returned 1e12 as though it were a lift-off mass, with `success` False that no caller
    looked at. A failure has to be reported as one, with the reasons counted."""
    spec = spec_of(DEFAULT)
    spec.payload_mass_kg = 5.0e7                      # no allocation can fly this
    out = opt.optimize_dv_split(spec, samples=25)
    assert out["success"] is False
    assert out["glom_kg"] is None, "a failed search must not report a lift-off mass"
    assert "cannot fly this mission" in out["note"], out["note"]


def test_every_start_is_reported_so_a_local_optimum_cannot_pose_as_a_global_one():
    out = opt.optimize_dv_split(spec_of(DEFAULT))
    assert len(out["starts"]) >= 1
    assert out["spread_rel"] is not None
    assert "local optimum" in out["note"].lower()


def test_the_search_is_reproducible_from_its_seed():
    a = opt.optimize_dv_split(spec_of(DEFAULT), seed=12345)
    b = opt.optimize_dv_split(spec_of(DEFAULT), seed=12345)
    assert a["fractions"] == b["fractions"]
    c = opt.optimize_dv_split(spec_of(DEFAULT), seed=999)
    assert abs(c["glom_kg"] - a["glom_kg"]) / a["glom_kg"] < 0.01, (
        "two different seeds should still find the same optimum to within 1 %")


# ---------------------------------------------------------------- the three objectives

def test_each_objective_runs_and_reports_its_own_units():
    spec = spec_of(DEFAULT)
    for objective in opt.OBJECTIVES:
        out = opt.optimize_dv_split(spec, objective=objective, samples=50)
        assert out["success"], f"{objective}: {out['note']}"
        assert out["objective"] == objective
        assert out["objective_value"] is not None
        assert abs(sum(out["fractions"]) - 1.0) < 1e-6


def test_an_objective_the_tool_cannot_compute_is_refused():
    try:
        opt.optimize_dv_split(spec_of(DEFAULT), objective="cheapness")
    except InputError as ex:
        assert "glom" in str(ex)
    else:
        raise AssertionError("'cheapness' was accepted as an objective")


def test_cost_means_development_cost_because_cost_per_flight_cannot_see_the_design():
    """The chapter's cost per flight is a rule of thumb on PAYLOAD mass, so it is the same dollar for every
    vehicle carrying the same payload - an objective blind to what it is optimising. This pins the reason
    the `cost` objective uses the development CERs instead, and will fail if per-flight ever becomes
    design-sensitive and the choice is worth revisiting."""
    from launch_vehicle import cost as costing
    spec = spec_of(DEFAULT)
    seen = set()
    for f1 in (0.30, 0.44, 0.60):
        res = opt._sized(spec, [f1, 1 - f1])
        assert res is not None
        seen.add(round(costing.estimate(res).per_flight_central_usd, 2))
    assert len(seen) == 1, f"cost per flight now varies with the design ({seen}) - reconsider the objective"


def test_maximising_payload_lands_near_the_lightest_vehicle():
    """Minimising mass at a fixed payload and maximising payload at a fixed mass are duals, so they should
    agree closely. They are not identical, because the mass relationships are not scale-invariant."""
    spec = spec_of(DEFAULT)
    g = opt.optimize_dv_split(spec, objective="glom", samples=50)
    p = opt.optimize_dv_split(spec, objective="payload", samples=25)
    assert p["payload_kg"] > spec.payload_mass_kg, "no more payload than the design already carries"
    assert abs(p["fractions"][0] - g["fractions"][0]) < 0.05, (
        f"payload optimum {p['fractions']} is far from the GLOM optimum {g['fractions']}")


# ---------------------------------------------------------------- applying it to the design

def test_the_optimum_is_not_applied_unless_the_design_asks():
    """With the option off the split is the user's decision and is used as written. The shipped designs have
    it ON since v1.1, at the owner's request, because the published accuracy figures are for the optimised
    split and the page was sizing check cases with the split as written; a file that does not carry the key
    at all is still treated as off, so an old design is not silently re-staged."""
    spec = spec_of(THREE_STAGE)
    assert spec.optimise_dv is True, "the shipped three-stage example asks for the optimum"
    spec.optimise_dv = False
    out, note = opt.apply_optimum(spec)
    assert out is spec and note is None
    from launch_vehicle import config_io
    import inspect
    assert 'vh.get("optimise_dv_split", False)' in inspect.getsource(config_io)


def test_when_asked_the_vehicle_that_is_sized_is_the_vehicle_that_was_optimised():
    spec = spec_of(THREE_STAGE)
    before = size_vehicle(spec).glom_kg
    spec.optimise_dv = True
    sized_spec, note = opt.apply_optimum(spec)
    assert note and note["applied"]
    after = size_vehicle(sized_spec).glom_kg
    assert after < before, f"{after:,.0f} kg is no better than {before:,.0f} kg"
    assert sized_spec.dv_fractions == note["now"]
    assert note["was"] != note["now"]


def test_applying_the_optimum_does_not_mutate_the_design_it_was_given():
    """The file on disk is untouched until the user saves, and so is the spec in memory."""
    spec = spec_of(THREE_STAGE)
    spec.optimise_dv = True
    original = list(spec.dv_fractions)
    opt.apply_optimum(spec)
    assert spec.dv_fractions == original


def test_the_note_says_what_it_changed_and_from_what():
    spec = spec_of(THREE_STAGE)
    spec.optimise_dv = True
    _s, note = opt.apply_optimum(spec)
    for expected in ("optimised", "%"):
        assert expected in note["why"], note["why"]
    assert "unchanged until you save" in note["why"]


def test_a_single_stage_design_declines_politely_rather_than_raising():
    spec = spec_of(DEFAULT)
    spec.stages = spec.stages[:1]
    spec.optimise_dv = True
    out, note = opt.apply_optimum(spec)
    assert out is spec and note is not None and note["applied"] is False


def test_the_objective_is_validated_when_the_design_is_checked_not_after_a_search():
    from launch_vehicle.validation import validate_spec, InputError as VErr
    spec = spec_of(DEFAULT)
    spec.optimise_dv = True
    spec.optimise_objective = "nonsense"
    try:
        validate_spec(spec)
    except VErr as ex:
        assert "OPTOBJ" in str(ex) or "optimise_objective" in str(ex), str(ex)
    else:
        raise AssertionError("an unknown optimisation objective passed validation")


def test_every_shipped_design_declares_the_option_so_the_gui_can_show_it():
    """The unreachable-input defect class: a key the loader reads that no design carries appears in no form
    and cannot be set."""
    import glob
    missing = []
    for path in sorted(glob.glob(os.path.join(ROOT, "config", "default_design.yaml"))
                       + glob.glob(os.path.join(ROOT, "examples", "*.yaml"))
                       + glob.glob(os.path.join(ROOT, "validation", "*.yaml"))):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if "vehicle:" not in text:
            continue                                  # a study declaration, not a design
        if "optimise_dv_split" not in text or "optimise_objective" not in text:
            missing.append(os.path.relpath(path, ROOT))
    assert not missing, f"designs with no optimisation control: {missing}"


def test_the_search_never_returns_a_design_worse_than_the_one_it_was_given():
    """The starting design is evaluated as one of the candidates, so the best point considered is never
    worse than where the user already was. Without this the optimiser could make a design worse - which is
    exactly what the old one did on the three-stage example."""
    for path in (DEFAULT, THREE_STAGE):
        spec = spec_of(path)
        baseline = size_vehicle(spec).glom_kg
        out = opt.optimize_dv_split(spec, samples=50)
        assert out["success"], out["note"]
        assert out["glom_kg"] <= baseline + 1.0, (
            f"{os.path.basename(path)}: returned {out['glom_kg']:,.0f} kg, worse than the design's own "
            f"{baseline:,.0f} kg")
        assert out["improvement_rel"] is None or out["improvement_rel"] >= -1e-9
