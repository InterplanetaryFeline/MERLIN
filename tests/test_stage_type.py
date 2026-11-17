"""Switching a stage between liquid and solid.

The thing to prove is not that keys moved around - it is that what comes out still LOADS and still SIZES.
A conversion that leaves the document one key short of a valid design is worse than no conversion at all,
because the user only finds out when they press Size, by which time the stage they were editing is gone.
That is exactly what happened on the first attempt here: `layout` looked type-agnostic and is not, because a
liquid stage needs `intertank_over_D` for the gap between its two tanks and a solid stage has no such gap.
So every test in this file that converts anything goes on to size the result.

The strongest check is the round trip. Stage 1 of the shipped default IS the liquid donor, so converting it to
solid and back must reproduce the shipped design exactly - same GLOM, to the kilogram. Nothing about the
transform is special-cased to make that true; if the graft dropped or mangled anything, the number moves.
"""
import os
import tempfile

import yaml

from launch_vehicle import stage_type as st
from launch_vehicle.config_io import load_design
from launch_vehicle.convergence import size_vehicle

ASSUMPTIONS = os.path.join("config", "engineering_assumptions.yaml")
DEFAULT = os.path.join("config", "default_design.yaml")
SOLID_EXAMPLE = os.path.join("examples", "example_solid_smallsat.yaml")


def _size(doc):
    """Write an annotated document out, load it the way the tool does, and size it. Returns the result."""
    fd, path = tempfile.mkstemp(suffix=".yaml", dir="designs")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(doc, fh, sort_keys=False)
        return size_vehicle(load_design(path, ASSUMPTIONS))
    finally:
        os.unlink(path)


# ------------------------------------------------------------------ reading what a stage is
def test_a_declared_stage_type_is_read():
    doc = st._load_annotated(SOLID_EXAMPLE)
    assert st.current_type(doc["stages"][0]) == "solid"


def test_a_stage_with_no_stage_type_key_is_liquid_unless_it_has_a_motor():
    """config_io defaults `stage_type` to liquid, so the GUI must read it the same way."""
    assert st.current_type({"fuel": {"v": "RP-1"}}) == "liquid"
    assert st.current_type({"motor": {}}) == "solid"
    assert st.current_type({"propellant": {"v": "HTPB_AP_AL20"}}) == "solid"


def test_the_shipped_default_is_two_liquid_stages():
    doc = st._load_annotated(DEFAULT)
    assert [st.current_type(s) for s in doc["stages"]] == ["liquid", "liquid"]


# ------------------------------------------------------------------ the donors
def test_each_donor_is_a_shipped_design_that_really_has_that_kind_of_stage():
    """The templates are grafted from real files rather than written here, so the files must exist and fit."""
    for kind, path in st.DONORS.items():
        assert os.path.exists(path), f"the {kind} donor {path} is not there"
        assert st.current_type(st.donor_stage(kind)) == kind


def test_the_donor_blocks_carry_their_own_annotation():
    """A grafted block has to be annotated, or the converted design will not load at all."""
    for kind in st.TYPES:
        donor = st.donor_stage(kind)
        for key in (st.LIQUID_KEYS if kind == "liquid" else st.SOLID_KEYS):
            if key not in donor:
                continue
            node = donor[key]
            if isinstance(node, dict) and "v" in node:
                for k in ("v", "u", "d", "s", "t"):
                    assert k in node, f"{kind} donor {key} is missing the {k!r} key"


def test_an_unknown_type_is_refused():
    for bad in ("hybrid", "", None):
        try:
            st.convert_stage(st._load_annotated(DEFAULT), 0, bad)
        except st.StageTypeError:
            pass
        else:
            raise AssertionError(f"{bad!r} should not be accepted as a stage type")


def test_a_stage_that_does_not_exist_is_refused():
    try:
        st.convert_stage(st._load_annotated(DEFAULT), 7, "solid")
    except st.StageTypeError as e:
        assert "stage 7" in str(e)
    else:
        raise AssertionError("converting a stage that is not there should raise")


def test_converting_to_the_type_it_already_is_changes_nothing():
    doc = st._load_annotated(DEFAULT)
    before = yaml.safe_dump(doc, sort_keys=True)
    note = st.convert_stage(doc, 0, "liquid")
    assert note["changed"] is False
    assert yaml.safe_dump(doc, sort_keys=True) == before, "a no-op conversion edited the document"


# ------------------------------------------------------------------ what the transform does
def test_liquid_to_solid_swaps_the_propulsion_and_keeps_the_rest():
    doc = st._load_annotated(DEFAULT)
    note = st.convert_stage(doc, 0, "solid")
    stage = doc["stages"][0]
    assert note["changed"] and note["was"] == "liquid" and note["now"] == "solid"
    for gone in ("engine", "tank", "fuel", "oxidizer", "mixture_ratio_OF"):
        assert gone not in stage, f"{gone} should have been removed"
    for added in ("motor", "propellant"):
        assert added in stage, f"{added} should have been added"
    assert st.current_type(stage) == "solid"


def test_the_users_own_settings_survive_the_switch():
    """Name, diameter, structure mode and margins are the user's decisions, not propulsion details."""
    doc = st._load_annotated(DEFAULT)
    before = {k: doc["stages"][0][k] for k in
              ("name", "diameter_m", "structure_mode", "separation_hardware_mass_kg",
               "other_equipment_mass_kg", "inert_mass_margin_fraction")}
    st.convert_stage(doc, 0, "solid")
    for k, v in before.items():
        assert doc["stages"][0][k] == v, f"{k} was changed by the conversion"


def test_the_type_dependent_values_are_taken_from_the_donor_not_carried_over():
    """A cast grain has no residual, no loading margin and no start-up transient (book p.489)."""
    doc = st._load_annotated(DEFAULT)
    assert doc["stages"][0]["residual_fraction"]["v"] > 0, "the liquid stage should start with a residual"
    st.convert_stage(doc, 0, "solid")
    for k in st.TYPE_DEPENDENT_KEYS:
        assert doc["stages"][0][k]["v"] == 0.0, f"{k} should be zero on a solid stage"


def test_solid_to_liquid_fills_in_the_layout_key_a_liquid_stage_needs():
    """The bug this file was written for: `layout` is not type-agnostic.

    A liquid stage needs `intertank_over_D`, a solid stage has no such key, and replacing the block outright
    would throw away the skirt and interstage ratios the user had set. So it is merged.
    """
    doc = st._load_annotated(SOLID_EXAMPLE)
    skirt_before = doc["stages"][0]["layout"]["aft_skirt_over_D"]
    note = st.convert_stage(doc, 0, "liquid")
    assert "layout.intertank_over_D" in note["filled_in"]
    assert "intertank_over_D" in doc["stages"][0]["layout"]
    assert doc["stages"][0]["layout"]["aft_skirt_over_D"] == skirt_before, (
        "merging the layout block overwrote a ratio the user had set")


def test_the_note_says_what_happened_in_words_a_user_can_act_on():
    note = st.convert_stage(st._load_annotated(DEFAULT), 1, "solid")
    assert "stage 2" in note["note"], "stages are numbered from 1 when spoken about"
    assert "liquid to solid" in note["note"]
    assert note["donor"].endswith(".yaml")


# ------------------------------------------------------------------ and does the result still work
def test_every_conversion_produces_a_design_that_loads_and_sizes():
    for src, index, to in ((DEFAULT, 0, "solid"), (DEFAULT, 1, "solid"),
                           (SOLID_EXAMPLE, 0, "liquid"), (SOLID_EXAMPLE, 1, "liquid"),
                           (SOLID_EXAMPLE, 2, "liquid")):
        doc = st._load_annotated(src)
        st.convert_stage(doc, index, to)
        res = _size(doc)
        assert res.glom_kg > 0
        assert res.stages[index].stage_type == to, (
            f"{src} stage {index} was converted to {to} but sized as {res.stages[index].stage_type}")


def test_the_round_trip_reproduces_the_shipped_design_to_the_kilogram():
    """Stage 1 of the default IS the liquid donor, so liquid -> solid -> liquid must be the identity.

    Nothing in the transform is special-cased for this; it holds only if the graft is faithful.
    """
    baseline = size_vehicle(load_design(DEFAULT, ASSUMPTIONS)).glom_kg
    doc = st._load_annotated(DEFAULT)
    st.convert_stage(doc, 0, "solid")
    st.convert_stage(doc, 0, "liquid")
    assert [st.current_type(s) for s in doc["stages"]] == ["liquid", "liquid"]
    after = _size(doc).glom_kg
    assert abs(after - baseline) < 1.0, (
        f"round trip moved GLOM from {baseline:,.0f} kg to {after:,.0f} kg: the graft is not faithful")


def test_converting_one_stage_leaves_the_others_alone():
    doc = st._load_annotated(DEFAULT)
    other_before = yaml.safe_dump(doc["stages"][1], sort_keys=True)
    st.convert_stage(doc, 0, "solid")
    assert yaml.safe_dump(doc["stages"][1], sort_keys=True) == other_before
