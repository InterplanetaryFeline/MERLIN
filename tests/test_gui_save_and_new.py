"""Save, Save as, and what a New design asks for.

The rule worth protecting is that Save can never rewrite a shipped file. config/, examples/ and validation/
are reference material: a check case quietly edited is a check case that no longer checks anything, and a
default design quietly edited means every later "based on the default" claim is false. So Save overwrites
only under designs/, and anywhere else it has to become Save as.

The other half is what a NEW design clears. The obvious rule - "everything tagged provenance: user" - was
tried and is wrong, and the test below pins the two fields that proved it: `engine.throttle_min_fraction`
(1.0, meaning no throttling) and `launch_site.altitude_m` (0.0, sea level) are user-tagged defaults that mean
something, and blanking the first makes the design unsizable. A new design is a blank BRIEF, not a blank
method.
"""
import os
import shutil

import yaml

from launch_vehicle import gui_meta, webgui
from launch_vehicle.config_io import load_design
from launch_vehicle.convergence import size_vehicle

ASSUMPTIONS = webgui.DEFAULT_ASSUMPTIONS
DEFAULT = "config/default_design.yaml"
TEST_STEM = "pytest_save_target"


def _cleanup():
    for p in (os.path.join(webgui.SAVE_DIR, TEST_STEM + ".yaml"),
              os.path.join(webgui.SAVE_DIR, TEST_STEM + "_two.yaml")):
        if os.path.exists(p):
            os.unlink(p)
    if os.path.isdir(webgui.DRAFT_DIR):
        shutil.rmtree(webgui.DRAFT_DIR, ignore_errors=True)


# ------------------------------------------------------------------ which files may be overwritten
def test_only_the_users_own_designs_are_writable():
    assert webgui.is_writable_design(os.path.join(webgui.SAVE_DIR, "mine.yaml"))
    for shipped in (DEFAULT, "examples/example_solid_smallsat.yaml", "validation/delta4_heavy.yaml",
                    "config/launch_sites.yaml", "config/engineering_assumptions.yaml"):
        assert not webgui.is_writable_design(os.path.join(webgui.ROOT, shipped)), (
            f"{shipped} must not be overwritable by Save")


def test_a_draft_is_not_writable_so_save_has_to_ask_for_a_name():
    """A draft has no name the user chose. If Save took it, a converted stage would vanish into a scratch file."""
    assert webgui.is_draft(os.path.join(webgui.DRAFT_DIR, "x.yaml"))
    assert not webgui.is_writable_design(os.path.join(webgui.DRAFT_DIR, "x.yaml"))


def test_save_refuses_a_shipped_file_by_name_and_says_what_to_do_instead():
    try:
        webgui.save_design(os.path.join(webgui.ROOT, DEFAULT), {}, "x", target=DEFAULT)
    except webgui.ConfigError as e:
        assert "Save as" in str(e), "the refusal should name the way out"
        assert "default_design" in str(e)
    else:
        raise AssertionError("Save must not overwrite the shipped default")


# ------------------------------------------------------------------ save, save again, save as
def test_the_first_save_writes_a_new_file_that_loads():
    _cleanup()
    try:
        # a payload near the default's own, because the default's 4 m / 3 m stages are sized for a 10 t
        # payload and the tool rightly refuses a design whose tanks are wider than their contents
        out = webgui.save_design(os.path.join(webgui.ROOT, DEFAULT),
                                 {"mission.payload_mass_kg": 9000.0}, TEST_STEM)
        assert out["path"] == f"designs/{TEST_STEM}.yaml"
        assert out["writable"] is True
        res = size_vehicle(load_design(os.path.join(webgui.ROOT, out["path"]), ASSUMPTIONS))
        assert res.glom_kg > 0
    finally:
        _cleanup()


def test_saving_the_same_name_again_is_refused_until_the_user_says_replace():
    _cleanup()
    try:
        webgui.save_design(os.path.join(webgui.ROOT, DEFAULT), {}, TEST_STEM)
        try:
            webgui.save_design(os.path.join(webgui.ROOT, DEFAULT), {}, TEST_STEM)
        except webgui.DesignExists as e:
            assert e.path == f"designs/{TEST_STEM}.yaml"
        else:
            raise AssertionError("a second Save as under the same name should ask first")
        # and with the answer given, it goes through
        out = webgui.save_design(os.path.join(webgui.ROOT, DEFAULT), {}, TEST_STEM, replace=True)
        assert out["path"] == f"designs/{TEST_STEM}.yaml"
    finally:
        _cleanup()


def test_plain_save_overwrites_the_bound_file_in_place_and_keeps_one_file():
    """The point of Save: same path, no second copy, the new value really in the file."""
    _cleanup()
    try:
        first = webgui.save_design(os.path.join(webgui.ROOT, DEFAULT), {}, TEST_STEM)
        bound = os.path.join(webgui.ROOT, first["path"])
        before = sorted(os.listdir(webgui.SAVE_DIR))
        again = webgui.save_design(bound, {"mission.payload_mass_kg": 9500.0}, TEST_STEM,
                                   target=first["path"])
        assert again["path"] == first["path"]
        assert sorted(os.listdir(webgui.SAVE_DIR)) == before, "Save created a second file"
        assert load_design(bound, ASSUMPTIONS).payload_mass_kg == 9500.0
    finally:
        _cleanup()


def test_an_overridden_value_is_retagged_as_the_users_and_keeps_its_units():
    _cleanup()
    try:
        out = webgui.save_design(os.path.join(webgui.ROOT, DEFAULT),
                                 {"mission.payload_mass_kg": 777.0}, TEST_STEM)
        with open(os.path.join(webgui.ROOT, out["path"]), encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        leaf = doc["mission"]["payload_mass_kg"]
        assert leaf["v"] == 777.0 and leaf["t"] == "user" and leaf["u"] == "kg"
        assert "GUI" in leaf["s"], "the source must say a person set it, not keep the book's citation"
    finally:
        _cleanup()


def test_saving_an_unknown_path_is_refused_rather_than_silently_dropped():
    try:
        webgui.save_design(os.path.join(webgui.ROOT, DEFAULT), {"mission.not_a_field": 1}, TEST_STEM)
    except webgui.ConfigError as e:
        assert "mission.not_a_field" in str(e)
    else:
        _cleanup()
        raise AssertionError("an unknown override path should not save quietly")


def test_a_library_file_is_not_offered_as_a_design_to_open():
    """config/launch_sites.yaml sits in a searched directory and is not a vehicle."""
    paths = {d["path"] for d in webgui.list_designs()}
    assert "config/default_design.yaml" in paths
    for lib in ("config/launch_sites.yaml", "config/engineering_assumptions.yaml",
                "config/engine_database.yaml"):
        assert lib not in paths, f"{lib} is a library, not a design, and must not be in the Open dialog"


# ------------------------------------------------------------------ drafts
def test_a_draft_is_written_proved_to_load_and_kept_out_of_the_open_dialog():
    _cleanup()
    try:
        from launch_vehicle import stage_type as st
        doc = st._load_annotated(os.path.join(webgui.ROOT, DEFAULT))
        st.convert_stage(doc, 0, "solid")
        rel = webgui.write_draft(doc, "unit-test-draft", "stage 1 to solid")
        assert rel.startswith("designs/.drafts/")
        assert os.path.exists(os.path.join(webgui.ROOT, rel))
        # it loaded once inside write_draft; prove it sizes too
        assert size_vehicle(load_design(os.path.join(webgui.ROOT, rel), ASSUMPTIONS)).glom_kg > 0
        assert rel not in {d["path"] for d in webgui.list_designs()}
    finally:
        _cleanup()


def test_a_draft_that_would_not_load_is_not_left_behind():
    """write_draft proves the document loads before handing back a path, and cleans up when it does not."""
    _cleanup()
    try:
        before = set(os.listdir(webgui.DRAFT_DIR)) if os.path.isdir(webgui.DRAFT_DIR) else set()
        try:
            webgui.write_draft({"mission": {}}, "broken")
        except Exception:
            pass
        else:
            raise AssertionError("a document with no stages should not pass as a draft")
        after = set(os.listdir(webgui.DRAFT_DIR)) if os.path.isdir(webgui.DRAFT_DIR) else set()
        assert after == before, "a draft that does not load was left on disk"
    finally:
        _cleanup()


# ------------------------------------------------------------------ what a new design asks for
def _items():
    return webgui.design_inputs(DEFAULT, ASSUMPTIONS, describe=True)["items"]


def test_the_new_design_brief_names_only_fields_this_design_really_has():
    plan = gui_meta.new_design_plan(_items())
    assert plan["missing"] == [], f"the brief names fields the default design does not have: {plan['missing']}"
    assert plan["blank"] and plan["flag"]


def test_the_brief_asks_for_the_mission_and_the_vehicle_and_every_stage():
    plan = gui_meta.new_design_plan(_items())
    blanked = {d["path"] for d in plan["blank"]}
    for want in ("mission.payload_mass_kg", "mission.orbit.perigee_altitude_km",
                 "mission.orbit.inclination_deg", "fairing.diameter_m", "vehicle.dv_fractions"):
        assert want in blanked, f"a new design should ask for {want}"
    # stages[*] must expand over the stages that exist, not be left as a pattern
    assert "stages[0].diameter_m" in blanked and "stages[1].diameter_m" in blanked
    assert not any("[*]" in p for p in blanked)


def test_the_brief_does_not_blank_a_user_tagged_default_that_means_something():
    """The two fields that disproved the obvious rule. Blanking throttle_min_fraction breaks sizing."""
    plan = gui_meta.new_design_plan(_items())
    blanked = {d["path"] for d in plan["blank"]}
    for keep in ("stages[0].engine.throttle_min_fraction", "stages[1].engine.throttle_min_fraction",
                 "mission.launch_site.altitude_m", "mission.report_apogee_maneuver"):
        assert keep not in blanked, (
            f"{keep} is a user-tagged default that means something; a new design must not clear it")


def test_a_pick_from_a_list_is_flagged_rather_than_emptied():
    """An empty dropdown helps nobody: the default stays and the field is marked for attention."""
    plan = gui_meta.new_design_plan(_items())
    flagged = {d["path"] for d in plan["flag"]}
    for want in ("mission.orbit.type", "mission.launch_site.site",
                 "stages[0].propellant_combination", "stages[0].name"):
        assert want in flagged, f"{want} should be flagged, not blanked"
    assert not ({d["path"] for d in plan["blank"]} & flagged), "a field cannot be both blanked and flagged"


def test_every_field_in_the_brief_says_why_it_is_asked_for():
    """The reason is what the page shows under the field, so an entry without one is a silent blank."""
    plan = gui_meta.new_design_plan(_items())
    for d in plan["blank"] + plan["flag"]:
        assert d["why"] and len(d["why"]) > 10, f"{d['path']} has no usable reason"


def test_nothing_the_method_owns_is_in_the_brief():
    """A blank MER helps nobody.

    Provenance alone cannot decide this: `stages[1].engine.isp_vac_s` is tagged `reference` because the
    default design takes 340 s from the book's own example, and vacuum Isp is still squarely a propulsion
    choice the user makes. What a new design must never clear is a coefficient of the METHOD - a mass
    estimating relationship, a structural factor, an ullage fraction, a margin - so those are named directly.
    """
    method_owned = ("_method", "factor", "residual", "margin", "ullage", "_over_D", "embed_",
                    "load_temperature", "startup_time", "insulated", "mass_fraction", "clearance")
    plan = gui_meta.new_design_plan(_items())
    for d in plan["blank"] + plan["flag"]:
        for frag in method_owned:
            assert frag not in d["path"], (
                f"{d['path']} looks like the method's business ({frag!r}); a new design must not clear it")


def test_the_items_mark_which_fields_are_the_users_to_supply():
    items = _items()
    req = [it for it in items if it.get("required")]
    assert req, "nothing is marked required"
    for it in req:
        assert it["provenance"] == "user" and it["value"] is not None
    # a user field the FILE leaves null is optional by construction
    opt = [it for it in items if it["provenance"] == "user" and it["value"] is None]
    assert opt, "the default design has optional user overrides; none were found"
    assert all(not it.get("required") for it in opt)


def test_every_stage_gets_a_type_row_even_when_its_file_does_not_say():
    """Without the row there is no control to switch the stage with."""
    for path, n in ((DEFAULT, 2), ("examples/example_solid_smallsat.yaml", 3),
                    ("validation/delta4_heavy.yaml", 2)):
        d = webgui.design_inputs(path, ASSUMPTIONS, describe=True)
        rows = [it for it in d["items"] if it["path"].endswith(".stage_type")]
        assert len(rows) == n == d["n_stages"], f"{path}: {len(rows)} type rows for {d['n_stages']} stages"
        assert {it["path"] for it in rows} == {f"stages[{i}].stage_type" for i in range(n)}, (
            f"{path}: the stage type rows are mis-indexed - register paths count from 0")
        for it in rows:
            assert it["value"] in ("liquid", "solid")
            assert it["section"].startswith("Stage")
