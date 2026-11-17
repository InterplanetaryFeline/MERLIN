"""The stage count: the input that was not an input.

The number of stages used to be the length of the `stages:` list in the YAML, which meant the browser could
only ever edit the stages it was handed - a new design was two-stage because the shipped default is. These
tests pin the three things that make changing it safe rather than merely possible: the count-dependent fields
move with it, the grafted stage is a real annotated block that loads and sizes, and every refusal names the
field it is about.
"""
from __future__ import annotations
import copy
import os
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from launch_vehicle import stage_count as sc                                           # noqa: E402
from launch_vehicle.config_io import _Loader, load_design                              # noqa: E402
from launch_vehicle.convergence import size_vehicle, SizingError                       # noqa: E402
from launch_vehicle.tank_sizing import InfeasibleGeometry                              # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT = os.path.join(ROOT, "config", "default_design.yaml")
ASSUMPTIONS = os.path.join(ROOT, "config", "engineering_assumptions.yaml")


def base_doc():
    with open(DEFAULT, encoding="utf-8") as fh:
        return yaml.load(fh, Loader=_Loader)


def val(leaf):
    return leaf.get("v") if isinstance(leaf, dict) else leaf


def test_current_count_matches_the_shipped_default():
    assert sc.current_count(base_doc()) == 2


def test_adding_and_removing_lands_on_the_asked_for_count():
    for n in range(sc.MIN_STAGES, sc.MAX_STAGES + 1):
        doc = base_doc()
        note = sc.set_count(doc, n)
        assert sc.current_count(doc) == n, f"asked for {n}, got {sc.current_count(doc)}"
        assert note["now"] == n
        assert note["changed"] == (n != 2)


def test_no_change_is_reported_as_no_change_and_leaves_the_document_alone():
    doc = base_doc()
    before = copy.deepcopy(doc)
    note = sc.set_count(doc, 2)
    assert note["changed"] is False
    assert doc == before


def test_a_count_outside_the_bounds_is_refused_and_names_the_field():
    for bad in (0, -1, sc.MAX_STAGES + 1, 99):
        try:
            sc.set_count(base_doc(), bad)
        except sc.StageCountError as ex:
            assert ex.field == "stage_count"
            assert str(bad) in ex.message
        else:
            raise AssertionError(f"{bad} stages was accepted")


def test_a_count_that_is_not_a_number_is_refused_rather_than_crashing():
    for bad in ("two", None, [3], 2.5 if False else "x"):
        try:
            sc.set_count(base_doc(), bad)
        except sc.StageCountError as ex:
            assert ex.field == "stage_count"
        else:
            raise AssertionError(f"{bad!r} was accepted as a stage count")


# ---------------------------------------------------------------- the count-dependent fields

def test_dv_fractions_gets_one_entry_per_stage_and_still_sums_to_one():
    for n in range(sc.MIN_STAGES, sc.MAX_STAGES + 1):
        doc = base_doc()
        sc.set_count(doc, n)
        fr = val(doc["vehicle"]["dv_fractions"])
        assert len(fr) == n, f"{n} stages but {len(fr)} delta-v fractions"
        assert abs(sum(fr) - 1.0) < 1e-6, f"{n} stages: fractions sum to {sum(fr)}"
        assert all(f > 0 for f in fr)


def test_the_existing_stages_keep_their_split_in_proportion():
    """The staging decision survives. 44/56 stays 44/56 between those two stages, scaled to make room."""
    doc = base_doc()
    before = val(doc["vehicle"]["dv_fractions"])
    ratio_before = before[0] / before[1]
    sc.set_count(doc, 4)
    after = val(doc["vehicle"]["dv_fractions"])
    assert abs(after[0] / after[1] - ratio_before) < 1e-6, "the original split was not preserved"


def test_the_rebalanced_split_is_tagged_assumed_and_says_why():
    """Whatever the user chose, it was not this, so the provenance must not keep claiming it is theirs."""
    doc = base_doc()
    sc.set_count(doc, 3)
    leaf = doc["vehicle"]["dv_fractions"]
    assert leaf["t"] == "assumed"
    assert "stage count" in leaf["s"].lower()


def test_removing_stages_pulls_the_fairing_jettison_stage_back_inside():
    """Validation accepts 2..N+1, so a three-stage vehicle may jettison at stage 4 and a two-stage one may
    not. Reducing the count has to bring it back rather than leave a design that will not validate."""
    doc = base_doc()
    sc.set_count(doc, 3)                                   # a three-stage vehicle, where 4 is legal
    doc["fairing"]["jettison_at_stage_start"]["v"] = 4
    note = sc.set_count(doc, 2)
    j = val(doc["fairing"]["jettison_at_stage_start"])
    assert 2 <= j <= 3, j
    assert any("jettison" in s for s in note["side_effects"]), note["side_effects"]


def test_removing_stages_pulls_last_ascent_stage_back_inside():
    doc = base_doc()
    doc["mission"]["last_ascent_stage"]["v"] = 2
    note = sc.set_count(doc, 1)
    assert val(doc["mission"]["last_ascent_stage"]) == 1
    assert any("last ascent" in s for s in note["side_effects"]), note["side_effects"]


def test_a_null_last_ascent_stage_is_left_null():
    """Null means 'fly every stage back to back'. Changing the count does not make that a number."""
    doc = base_doc()
    assert val(doc["mission"]["last_ascent_stage"]) is None
    sc.set_count(doc, 3)
    assert val(doc["mission"]["last_ascent_stage"]) is None


def test_the_fairing_is_never_left_narrower_than_the_new_top_stage():
    """Drop the narrow upper stage off a wide core and the fairing would sit on a stage wider than itself,
    which validation rejects outright. It is a consequence of the count change, so it is fixed and declared."""
    doc = base_doc()
    note = sc.set_count(doc, 1)
    top_d = val(doc["stages"][-1]["diameter_m"])
    assert val(doc["fairing"]["diameter_m"]) >= top_d - 1e-9
    assert any("fairing" in s for s in note["side_effects"]), note["side_effects"]


# ---------------------------------------------------------------- the grafted stage

def test_the_added_stage_is_a_real_annotated_block():
    """Every leaf grafted in carries its own units, description, source and provenance - the same contract
    every shipped design meets. A template written in the module would be the first thing to go stale."""
    doc = base_doc()
    sc.set_count(doc, 3)
    new = doc["stages"][2]
    assert new, "no third stage"
    bad = []
    for key, leaf in new.items():
        if isinstance(leaf, dict) and "v" in leaf:
            for f in ("u", "d", "s", "t"):
                if f not in leaf:
                    bad.append(f"{key}.{f}")
    assert not bad, f"grafted leaves missing annotation: {bad}"


def test_the_added_stage_is_the_donors_upper_stage_not_its_core():
    """A stage added on top is an upper stage. The shipped design's FIRST stage carries a sea-level nozzle and
    a first-stage thrust-to-weight; grafting that above the atmosphere would quietly cost delta-v."""
    doc = base_doc()
    donor_upper = sc.upper_donor("liquid")
    sc.set_count(doc, 3)
    new = doc["stages"][2]
    for key in ("fuel", "oxidizer"):
        if key in donor_upper and key in new:
            assert val(new[key]) == val(donor_upper[key]), key
    eng_new = (new.get("engine") or {}).get("expansion_ratio")
    eng_don = (donor_upper.get("engine") or {}).get("expansion_ratio")
    if eng_new is not None and eng_don is not None:
        assert val(eng_new) == val(eng_don), "the new stage did not come from the donor's upper stage"


def test_the_added_stage_takes_the_cross_section_of_the_stage_below():
    doc = base_doc()
    below = val(doc["stages"][-1]["diameter_m"])
    sc.set_count(doc, 3)
    assert val(doc["stages"][2]["diameter_m"]) == below


def test_added_stages_are_labelled_by_position():
    doc = base_doc()
    sc.set_count(doc, 4)
    names = [val(s["name"]) for s in doc["stages"]]
    assert names[2] == "Stage 3" and names[3] == "Stage 4", names
    assert len(set(names)) == len(names), f"duplicate stage names: {names}"


def test_a_stage_is_added_on_top_and_the_lower_stages_are_untouched():
    doc = base_doc()
    before = copy.deepcopy(doc["stages"])
    sc.set_count(doc, 3)
    assert doc["stages"][0] == before[0], "stage 1 was modified by adding a stage on top"
    assert doc["stages"][1] == before[1], "stage 2 was modified by adding a stage on top"


def test_removing_takes_from_the_top():
    doc = base_doc()
    first = copy.deepcopy(doc["stages"][0])
    sc.set_count(doc, 1)
    assert doc["stages"][0] == first


def test_a_design_with_no_stages_is_refused_rather_than_grafted_onto():
    doc = base_doc()
    doc["stages"] = []
    try:
        sc.set_count(doc, 2)
    except sc.StageCountError as ex:
        assert ex.field == "stage_count"
    else:
        raise AssertionError("a design with no stages was accepted")


# ---------------------------------------------------------------- it has to actually load and size

def _write(doc):
    fh = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8")
    yaml.safe_dump(doc, fh, sort_keys=False)
    fh.close()
    return fh.name


def test_every_stage_count_produces_a_document_that_loads():
    """Loading is the floor. Whether a 6-stage vehicle to LEO is a good idea is the user's business; whether
    the document this module writes is a valid design is this module's."""
    for n in range(sc.MIN_STAGES, sc.MAX_STAGES + 1):
        doc = base_doc()
        sc.set_count(doc, n)
        path = _write(doc)
        try:
            spec = load_design(path, ASSUMPTIONS)
            assert len(spec.stages) == n, f"wrote {n} stages, loaded {len(spec.stages)}"
        finally:
            os.unlink(path)


def test_a_three_stage_version_of_the_default_sizes_and_beats_the_two_stage():
    """The staging benefit, as a live check that a grafted stage is a working stage and not just a valid one.
    The third stage needs its tank narrowed - its propellant will not fill the core's cross-section - and the
    sizing error offers that diameter as a one-click fix, which is the path a user actually takes."""
    two = size_vehicle(load_design(DEFAULT, ASSUMPTIONS))

    doc = base_doc()
    sc.set_count(doc, 3)
    path = _write(doc)
    try:
        overrides, result = {}, None
        for _ in range(5):
            try:
                result = size_vehicle(load_design(path, ASSUMPTIONS, overrides or None))
                break
            except (SizingError, InfeasibleGeometry) as ex:
                usable = [o for o in (getattr(ex, "options", None) or [])
                          if o.get("path") and o.get("value") is not None]
                assert usable, f"a refusal with no applicable option: {ex}"
                overrides[usable[0]["path"]] = usable[0]["value"]
        assert result is not None, "the three-stage design never sized"
        assert len(result.stages) == 3
        assert result.glom_kg < two.glom_kg, (
            f"three stages ({result.glom_kg:,.0f} kg) should beat two ({two.glom_kg:,.0f} kg) for the same "
            "payload and mission")
    finally:
        os.unlink(path)


def test_a_single_stage_to_this_orbit_is_refused_with_the_reason_and_a_way_out():
    """One stage cannot reach LEO on kerosene, and the tool should say THAT rather than 'mu*s >= 1'."""
    doc = base_doc()
    sc.set_count(doc, 1)
    path = _write(doc)
    try:
        try:
            size_vehicle(load_design(path, ASSUMPTIONS))
        except SizingError as ex:
            msg = str(ex)
            assert "mass ratio" in msg, msg
            assert "MORE STAGES" in msg.upper(), msg
            labels = [o.get("label", "") for o in (ex.options or [])]
            assert any("another stage" in lbl for lbl in labels), labels
            assert ex.field is not None
        else:
            raise AssertionError("a single-stage kerosene vehicle to LEO was accepted")
    finally:
        os.unlink(path)


def test_the_note_names_every_change_it_made():
    """The note is what the user is shown. A change it does not mention is a change made behind their back."""
    doc = base_doc()
    doc["fairing"]["jettison_at_stage_start"]["v"] = 3
    note = sc.set_count(doc, 1)
    text = note["note"].lower()
    for expected in ("dv_fractions", "fairing"):
        assert expected in text, f"{expected!r} was changed but the note does not say so: {note['note']}"
    assert note["donor"] is None, "nothing was grafted, so there is no donor to name"


def test_the_note_names_the_donor_when_a_stage_is_grafted():
    note = sc.set_count(base_doc(), 3)
    assert note["donor"], "an added stage must say where its block came from"
    assert os.path.exists(os.path.join(ROOT, note["donor"])), note["donor"]


def test_a_stage_added_to_a_solid_vehicle_is_a_solid_stage():
    """The donor matches the type of the stage it sits on. A vehicle whose upper stage is a cast-grain motor
    is not asking for a sudden liquid stage with tanks and a turbopump on top of it."""
    from launch_vehicle import stage_type as stype
    path = os.path.join(ROOT, "examples", "example_solid_smallsat.yaml")
    with open(path, encoding="utf-8") as fh:
        doc = yaml.load(fh, Loader=_Loader)
    before = len(doc["stages"])
    assert stype.current_type(doc["stages"][-1]) == "solid", "this example is no longer all-solid"
    note = sc.set_count(doc, before + 1)
    new = doc["stages"][-1]
    assert stype.current_type(new) == "solid"
    assert "motor" in new and "propellant" in new, "a solid stage needs a motor block and a propellant"
    assert "tank" not in new and "engine" not in new, "liquid blocks were grafted onto a solid stage"
    assert "solid" in note["note"], note["note"]


def test_a_solid_vehicle_with_an_added_stage_still_loads():
    path = os.path.join(ROOT, "examples", "example_solid_smallsat.yaml")
    with open(path, encoding="utf-8") as fh:
        doc = yaml.load(fh, Loader=_Loader)
    n = len(doc["stages"]) + 1
    sc.set_count(doc, n)
    out = _write(doc)
    try:
        spec = load_design(out, ASSUMPTIONS)
        assert len(spec.stages) == n
        assert spec.stages[-1].stage_type == "solid"
    finally:
        os.unlink(out)


def test_a_design_whose_split_was_already_the_wrong_length_comes_out_right():
    """Hand-edited files exist. Changing the stage count must not hand the user a DVFRAC error about a field
    they never touched, so the length is made exact rather than trusted to the arithmetic."""
    # every case must be a real change of count: asking for the count a design already has is a no-op by
    # design, and should NOT quietly repair a field the user did not touch
    for junk, target in [([0.3, 0.3, 0.4], 4), ([0.5], 3), ([], 3), ([0.2] * 5, 1), ([0.2] * 5, 3)]:
        doc = base_doc()
        doc["vehicle"]["dv_fractions"]["v"] = list(junk)
        sc.set_count(doc, target)
        fr = val(doc["vehicle"]["dv_fractions"])
        if not junk:
            continue                      # an empty list is left alone: there is no split to rebalance
        assert len(fr) == target, f"{junk} -> {target} stages gave {len(fr)} fractions"
        assert abs(sum(fr) - 1.0) < 1e-9, f"{junk} -> {target}: sums to {sum(fr)}"


def test_asking_for_the_count_a_design_already_has_repairs_nothing():
    """A no-op must be a no-op. Silently fixing an unrelated malformed field would be a change the user did
    not ask for, and validation is the right place for that to surface."""
    doc = base_doc()
    doc["vehicle"]["dv_fractions"]["v"] = [0.3, 0.3, 0.4]
    note = sc.set_count(doc, 2)
    assert note["changed"] is False
    assert val(doc["vehicle"]["dv_fractions"]) == [0.3, 0.3, 0.4]


def test_the_split_sums_to_one_exactly_enough_to_pass_validation():
    """Six stages rounded to six places can leave the sum a hair off, and the sum is checked downstream."""
    for n in range(sc.MIN_STAGES, sc.MAX_STAGES + 1):
        doc = base_doc()
        sc.set_count(doc, n)
        fr = val(doc["vehicle"]["dv_fractions"])
        assert abs(sum(fr) - 1.0) < 1e-9, f"{n} stages: {sum(fr)!r}"
