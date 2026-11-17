"""Strap-on boosters: fitting them, taking them off, and being guided when they do not fit.

The model has handled strap-ons since Ariane 5 ECA and Delta IV Heavy became check cases, and the GUI renders
all 32 booster fields - but only for a design whose file already carried a `boosters:` block. A design
without one had no way in and a design with one had no way out, which is the same gap the stage count had.

These tests pin three things: the block is grafted from a shipped design rather than invented here, removing
it leaves the rest of the design alone, and every refusal along the way hands the user a way out that both
RESOLVES to a real field and actually converges. The last one is the point: an offered fix that oscillates
looks like progress and is worse than no fix at all.
"""
from __future__ import annotations
import copy
import os
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from launch_vehicle import strap_ons as so                                             # noqa: E402
from launch_vehicle.config_io import _Loader, load_design                              # noqa: E402
from launch_vehicle.convergence import size_vehicle, SizingError                       # noqa: E402
from launch_vehicle.tank_sizing import InfeasibleGeometry                              # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT = os.path.join(ROOT, "config", "default_design.yaml")
SMALLSAT = os.path.join(ROOT, "examples", "example_solid_smallsat.yaml")
ARIANE = os.path.join(ROOT, "validation", "ariane5_eca.yaml")
ASSUMPTIONS = os.path.join(ROOT, "config", "engineering_assumptions.yaml")


def doc_of(path):
    with open(path, encoding="utf-8") as fh:
        return yaml.load(fh, Loader=_Loader)


def val(leaf):
    return leaf.get("v") if isinstance(leaf, dict) else leaf


def _write(doc):
    fh = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8")
    yaml.safe_dump(doc, fh, sort_keys=False)
    fh.close()
    return fh.name


def _size_following_advice(path, max_clicks=8):
    """Size the design, applying the first applicable fix each refusal offers. Returns (result, clicks).

    This is the user's actual loop: press Size, click the button, press Size again. If the tool offers a
    value it must be a value that resolves - `load_design` raises on an unknown dotted path - and the loop
    must terminate, or the user is clicking forever.
    """
    overrides, clicks = {}, []
    for _ in range(max_clicks):
        try:
            return size_vehicle(load_design(path, ASSUMPTIONS, overrides or None)), clicks
        except (SizingError, InfeasibleGeometry) as ex:
            usable = [o for o in (getattr(ex, "options", None) or [])
                      if o.get("path") and o.get("value") is not None]
            if not usable:
                return None, clicks
            overrides[usable[0]["path"]] = usable[0]["value"]
            clicks.append(usable[0]["path"])
    raise AssertionError(f"the offered fixes never settled; clicked {clicks}")


# ---------------------------------------------------------------- reading what a design has

def test_current_kind_reads_the_shipped_designs_correctly():
    assert so.current_kind(doc_of(DEFAULT)) is None
    assert so.current_kind(doc_of(ARIANE)) == "solid"
    assert so.current_kind(doc_of(os.path.join(ROOT, "validation", "delta4_heavy.yaml"))) == "liquid"


def test_asking_for_what_it_already_has_changes_nothing():
    for path, kind in [(DEFAULT, None), (ARIANE, "solid")]:
        doc = doc_of(path)
        before = copy.deepcopy(doc)
        note = so.set_boosters(doc, kind)
        assert note["changed"] is False
        assert doc == before


def test_a_kind_that_is_not_a_kind_is_refused_and_names_the_field():
    for bad in ("hybrid", "Solid", 5, ["solid"]):
        try:
            so.set_boosters(doc_of(DEFAULT), bad)
        except so.StrapOnError as ex:
            assert ex.field == "boosters.type"
        else:
            raise AssertionError(f"{bad!r} was accepted as a booster kind")


# ---------------------------------------------------------------- fitting and removing

def test_both_kinds_can_be_fitted_to_a_design_that_had_none():
    for kind in so.KINDS:
        doc = doc_of(DEFAULT)
        note = so.set_boosters(doc, kind)
        assert note["changed"] and note["now"] == kind
        assert so.current_kind(doc) == kind
        assert note["donor"], "an added block must say where it came from"
        assert os.path.exists(os.path.join(ROOT, note["donor"]))


def test_the_grafted_block_is_fully_annotated():
    """Every leaf carries its own units, description, source and provenance - the contract every shipped
    design meets. A template written into the module would be the first thing to go stale."""
    for kind in so.KINDS:
        doc = doc_of(DEFAULT)
        so.set_boosters(doc, kind)
        bad = []
        for key, leaf in doc["boosters"].items():
            if isinstance(leaf, dict) and "v" in leaf:
                bad += [f"{key}.{f}" for f in ("u", "d", "s", "t") if f not in leaf]
        assert not bad, f"{kind} graft missing annotation: {bad}"


def test_removing_the_boosters_leaves_the_rest_of_the_design_alone():
    """The block is self-contained: nothing outside it refers to the boosters, and `attach_stage` is pinned
    to 1 by validation, so there is no index to clamp and no delta-v split to rebalance."""
    doc = doc_of(ARIANE)
    before = copy.deepcopy(doc)
    before.pop("boosters")
    note = so.set_boosters(doc, None)
    assert note["changed"] and note["now"] is None
    assert "boosters" not in doc
    assert doc == before, "removing the boosters changed something else in the design"


def test_switching_kind_keeps_how_many_boosters_the_user_asked_for():
    """How many there are is the user's architecture decision; the rest of the block describes a particular
    motor and belongs to whichever design it was copied from."""
    doc = doc_of(ARIANE)
    n_before = val(doc["boosters"]["n_total"])
    note = so.set_boosters(doc, "liquid")
    assert val(doc["boosters"]["n_total"]) == n_before
    assert "n_total" in note["carried"]


def test_the_number_lit_on_the_ground_never_exceeds_the_number_fitted():
    doc = doc_of(DEFAULT)
    so.set_boosters(doc, "solid")
    doc["boosters"]["n_total"]["v"] = 2
    doc["boosters"]["n_ground_lit"]["v"] = 2
    so.set_boosters(doc, "liquid")
    assert val(doc["boosters"]["n_ground_lit"]) <= val(doc["boosters"]["n_total"])


def test_the_note_says_where_the_numbers_came_from():
    """They arrive with the donor's provenance. The user did not choose a Soyuz booster's propellant load,
    so the note must not let them think the block was fitted to their vehicle."""
    note = so.set_boosters(doc_of(DEFAULT), "liquid")
    assert note["donor"] in note["note"]
    assert any("starting point" in w for w in note["warnings"]), note["warnings"]


def test_the_liquid_donor_is_not_delta_iv():
    """Measured, not assumed: Delta IV's Common Booster Cores carry 200 t each at 5.1 m and drive any
    smaller core out of propellant before they burn out. Soyuz's 39 t strap-ons graft onto an ordinary
    vehicle and size. If someone retargets this donor, this test should make them check that again."""
    assert "soyuz" in so.DONORS["liquid"].lower()
    doc = doc_of(DEFAULT)
    so.set_boosters(doc, "liquid")
    path = _write(doc)
    try:
        result, clicks = _size_following_advice(path)
        assert result is not None and not clicks, (
            "the liquid donor should graft onto the shipped default and size with no fixes needed")
    finally:
        os.unlink(path)


# ---------------------------------------------------------------- it has to size, or guide

def test_every_host_and_kind_combination_either_sizes_or_guides_to_a_fix_that_settles():
    """The whole point. Each combination must either size, or refuse with fixes that actually converge -
    never a button that keeps bringing the user back to the same refusal."""
    for host in (DEFAULT, SMALLSAT, ARIANE):
        for kind in (None, "solid", "liquid"):
            doc = doc_of(host)
            so.set_boosters(doc, kind)
            path = _write(doc)
            try:
                result, clicks = _size_following_advice(path)
                assert result is not None, (
                    f"{os.path.basename(host)} + {kind}: refused with no applicable fix after {clicks}")
            finally:
                os.unlink(path)


def test_a_booster_too_wide_for_its_own_propellant_names_a_booster_field_not_a_bare_leaf():
    """The casing sizer names its way out as a bare `diameter_m`, because it knows the geometry and not what
    owns it. A serial stage completes that to `stages[N].…`; nothing completed it for a booster, so the GUI
    was handed a path that resolves to nothing. Only reachable once boosters could be fitted from a browser.
    """
    doc = doc_of(DEFAULT)
    so.set_boosters(doc, "solid")
    doc["boosters"]["diameter_m"]["v"] = 6.0          # far too wide for 17 t of grain
    path = _write(doc)
    try:
        try:
            size_vehicle(load_design(path, ASSUMPTIONS))
        except (SizingError, InfeasibleGeometry) as ex:
            paths = [o["path"] for o in (getattr(ex, "options", None) or []) if o.get("path")]
            assert paths, "the refusal offered no field at all"
            for p in paths:
                assert p.startswith("boosters."), f"bare path offered to the GUI: {p!r}"
            # and it must actually resolve, which is what the GUI's one-click fix needs
            load_design(path, ASSUMPTIONS, {paths[0]: 1.0})
        else:
            raise AssertionError("a 6 m booster holding 17 t of grain was accepted")
    finally:
        os.unlink(path)


def test_the_booster_burn_fix_leaves_enough_margin_to_settle():
    """Shortening the burn changes the vehicle, which moves this very limit - it is a fixed point. A 2 %
    margin oscillates and the user clicks forever; 10 % settles. This pins the margin, not the wording."""
    doc = doc_of(DEFAULT)
    so.set_boosters(doc, "solid")
    doc["boosters"]["burn_time_s"] = {"v": 200.0, "u": "s", "d": "deliberately too long",
                                      "s": "test", "t": "user"}
    path = _write(doc)
    try:
        result, clicks = _size_following_advice(path)
        assert result is not None, f"never sized; clicked {clicks}"
        assert len(clicks) <= 5, f"took {len(clicks)} clicks to settle: {clicks}"
    finally:
        os.unlink(path)


def test_boosters_that_outweigh_the_core_lead_with_shrinking_them_not_with_the_burn_time():
    """Given that a configuration has ALREADY failed, which lever is worth offering first. It is not a claim
    that heavy boosters are wrong - Ariane 5's EAPs carry far more than its core and never reach this line."""
    doc = doc_of(SMALLSAT)
    so.set_boosters(doc, "liquid")                    # 4 x 39 t of booster on a 40 t vehicle
    path = _write(doc)
    try:
        try:
            size_vehicle(load_design(path, ASSUMPTIONS))
        except (SizingError, InfeasibleGeometry) as ex:
            opts = [o for o in (getattr(ex, "options", None) or []) if o.get("path")]
            assert opts, "no way out offered"
            assert opts[0]["path"] == "boosters.propellant_mass_each_kg", (
                "the first fix offered should shrink the boosters, not retime them: "
                + str([o["path"] for o in opts]))
        else:
            raise AssertionError("four 39 t boosters on a 40 t vehicle were accepted")
    finally:
        os.unlink(path)


def test_the_core_grows_to_do_the_boosters_work_when_they_come_off():
    """Taking the strap-ons off a real vehicle must leave a design that still sizes, with the CORE carrying
    what the boosters used to.

    The core propellant is the invariant to assert, not the lift-off mass. Ariane 5 ECA comes out LIGHTER
    without its EAPs - 738 t against 855 t - and that is the right answer, not a bug: the EAPs burn at about
    275 s of specific impulse against the cryogenic EPC's ~430 s, so replacing boosted thrust with core
    propulsion buys the same delta-v for less propellant even though the core nearly triples. Asserting
    "heavier without boosters" would have been the naive guess, and the tool was right.
    """
    doc = doc_of(ARIANE)
    with_boosters = size_vehicle(load_design(ARIANE, ASSUMPTIONS))
    assert with_boosters.boosters is not None
    so.set_boosters(doc, None)
    path = _write(doc)
    try:
        without = size_vehicle(load_design(path, ASSUMPTIONS))
        assert without.boosters is None
        assert without.stages[0].m_prop_loaded_kg > 2.0 * with_boosters.stages[0].m_prop_loaded_kg, (
            "the core should take over the boosters' work: "
            f"{without.stages[0].m_prop_loaded_kg:,.0f} kg against "
            f"{with_boosters.stages[0].m_prop_loaded_kg:,.0f} kg")
    finally:
        os.unlink(path)
