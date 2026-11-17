"""Launch vehicle families (families.py, roadmap R37).

A family is the one configuration where this tool's hardest limitation is checkable against published data,
so these tests are in two halves. The first half is the manifest: it must refuse anything that would let a
family quietly grade itself against its own guesses - an unsourced published figure, a figure marked
`assumed`, a base design that does not exist, a single-variant "family". The second half is the measurement
itself, pinned to the numbers two real families publish, with the directions asserted rather than the
magnitudes trusted.
"""
import os
import sys

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from launch_vehicle import families as fam                    # noqa: E402
from launch_vehicle.config_io import load_design              # noqa: E402
from launch_vehicle.convergence import size_vehicle           # noqa: E402

ASSUMP = os.path.join(ROOT, "config", "engineering_assumptions.yaml")

_SIZED = {}


def sized_family(slug):
    if slug not in _SIZED:
        _SIZED[slug] = fam.size_family(fam.find(ROOT, slug), ASSUMP)
    return _SIZED[slug]


# --------------------------------------------------------------------------- discovery and the manifest
def test_the_shipped_families_are_found_and_well_formed():
    found = {f.slug: f for f in fam.discover(ROOT)}
    assert {"delta_ii", "ariane_6"} <= set(found), f"found {sorted(found)}"
    for f in found.values():
        assert len(f.variants) >= 2, "a family needs at least two variants"
        assert os.path.isfile(f.base_path)
        assert f.reference and sum(1 for v in f.variants if v.is_reference) == 1
        assert f.note.strip(), f"{f.slug}: a family must say what its variants share"


def test_a_family_can_be_found_by_slug_or_by_name_either_case():
    for key in ("delta_ii", "DELTA_II", "Delta II 7000 series", "delta ii 7000 SERIES"):
        assert fam.find(ROOT, key).slug == "delta_ii"
    with pytest.raises(fam.FamilyError, match="no family"):
        fam.find(ROOT, "no_such_family")


def test_every_variant_is_the_base_design_plus_overrides_so_the_core_is_shared_in_fact():
    """The point of the manifest. If a variant were a copy of the base, the shared core would be an
    aspiration; here every variant loads the same file, so it cannot drift."""
    f = fam.find(ROOT, "delta_ii")
    assert len({v.base_path for v in f.variants}) == 1
    specs = {v.key: v.spec(ASSUMP) for v in f.variants}
    # the first stage is byte-identical across the variants, by construction
    firsts = {k: (s.stages[0].propellant_mass_kg if hasattr(s.stages[0], "propellant_mass_kg") else None,
                  s.stages[0].diameter_m) for k, s in specs.items()}
    assert len(set(firsts.values())) == 1, f"the shared first stage differs between variants: {firsts}"
    # and what makes each variant itself really did apply
    assert [specs[k].boosters.n_total for k in ("7320", "7420", "7920")] == [3, 4, 9]
    assert [specs[k].payload_mass_kg for k in ("7320", "7420", "7920")] == [2800.0, 3200.0, 5100.0]


def test_a_published_figure_must_carry_a_source_and_be_marked_reference(tmp_path=None):
    """A validation set that accepts an assumed figure as 'published' grades itself against its own guess.
    Each case below is a manifest that must be refused, and the reason must name the problem."""
    import tempfile
    base = os.path.relpath(os.path.join(ROOT, "validation", "delta2_7920.yaml"))
    good = {"v": 1.0, "u": "kg", "d": "d", "s": "a real source", "t": "reference"}
    cases = [
        ("bare value", 152000.0, "annotated"),
        ("missing keys", {"v": 1.0, "u": "kg"}, "missing documentation keys"),
        ("assumed", dict(good, t="assumed"), "must be 'reference'"),
        ("empty source", dict(good, s="   "), "empty source"),
        ("bad provenance", dict(good, t="guesswork"), "provenance"),
    ]
    for label, node, expect in cases:
        d = tempfile.mkdtemp()
        doc = {"family": {"name": "T", "base": os.path.join(ROOT, "validation", "delta2_7920.yaml"),
                          "reference": "a",
                          "variants": {"a": {"overrides": {"boosters.n_total": 9},
                                             "published": {"glom_kg": node}},
                                       "b": {"overrides": {"boosters.n_total": 3}}}}}
        p = os.path.join(d, "family.yaml")
        with open(p, "w", encoding="utf-8") as fh:
            yaml.safe_dump(doc, fh)
        with pytest.raises(fam.FamilyError, match=expect):
            fam.load_manifest(p)
    assert base  # the base path above is real, so each refusal is about the published figure and nothing else


def test_a_manifest_is_refused_when_it_is_not_a_family():
    import tempfile
    real_base = os.path.join(ROOT, "validation", "delta2_7920.yaml")
    bad = [
        ({"not_family": {}}, "no 'family:' block"),
        ({"family": {"name": "T", "base": real_base}}, "missing 'variants'"),
        ({"family": {"name": "T", "base": real_base,
                     "variants": {"only": {"overrides": {}}}}}, "at least two variants"),
        ({"family": {"name": "T", "base": "nope.yaml",
                     "variants": {"a": {}, "b": {}}}}, "does not exist"),
        ({"family": {"name": "T", "base": real_base, "reference": "zz",
                     "variants": {"a": {}, "b": {}}}}, "reference"),
        ({"family": {"name": "T", "base": real_base,
                     "variants": {"a": {"overrides": "not a mapping"}, "b": {}}}}, "must be a mapping"),
    ]
    for doc, expect in bad:
        p = os.path.join(tempfile.mkdtemp(), "family.yaml")
        with open(p, "w", encoding="utf-8") as fh:
            yaml.safe_dump(doc, fh)
        with pytest.raises(fam.FamilyError, match=expect):
            fam.load_manifest(p)


def test_a_user_family_in_the_designs_tree_is_discovered_without_registering_anything():
    """The feature as a user meets it: make a folder, write a manifest, and it is there. Nothing in the
    tool lists the families it knows about, so there is nothing to forget to update."""
    import shutil
    d = os.path.join(ROOT, "designs", fam.FAMILIES_DIR, "_test_user_family")
    os.makedirs(d, exist_ok=True)
    try:
        doc = {"family": {"name": "A user's own family", "base": "../../../validation/delta2_7920.yaml",
                          "reference": "nine",
                          "variants": {"nine": {"label": "nine", "overrides": {"boosters.n_total": 9}},
                                       "four": {"label": "four", "overrides": {"boosters.n_total": 4}}}}}
        with open(os.path.join(d, "family.yaml"), "w", encoding="utf-8") as fh:
            yaml.safe_dump(doc, fh)
        slugs = {f.slug for f in fam.discover(ROOT)}
        assert "_test_user_family" in slugs
        f = fam.find(ROOT, "_test_user_family")
        assert f.variant("four").overrides["boosters.n_total"] == 4
        assert f.variant("four").published_kg("glom_kg") is None      # published figures are optional
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --------------------------------------------------------------------------- the measurement
def test_sizing_each_variant_on_its_own_under_predicts_the_smaller_members():
    """The §6b.3 shared-core finding, measured on a family rather than asserted. A sizer that gives every
    stage its own share of the delta-v gives every variant its own MINIMAL core, but a real family shares one
    core sized for its largest member - so the small variants must come out too light, and the error must
    shrink towards the largest. Measured: Delta II 7320 -10.0 %, 7420 -6.9 %, 7920 +1.5 %."""
    rows = {r["key"]: r for r in sized_family("delta_ii")}
    for r in rows.values():
        assert not r["error"], f"{r['label']}: {r['error']}"
    err = {k: r["glom_err"] for k, r in rows.items()}
    assert err["7320"] < err["7420"] < err["7920"], \
        f"the error must shrink as the variant grows, got {err}"
    assert err["7320"] < 0 and err["7420"] < 0, "the small variants must be under-predicted"
    assert err["7320"] == pytest.approx(-0.100, abs=0.05)
    assert err["7420"] == pytest.approx(-0.069, abs=0.05)
    assert err["7920"] == pytest.approx(+0.015, abs=0.05)


def test_the_same_ordering_holds_on_a_second_family():
    rows = {r["key"]: r for r in sized_family("ariane_6")}
    for r in rows.values():
        assert not r["error"], f"{r['label']}: {r['error']}"
    assert rows["62"]["glom_err"] < rows["64"]["glom_err"] < 0, \
        "both Ariane variants are under-predicted and the smaller one worse"


def test_pinning_the_reference_core_errs_the_OTHER_WAY_which_is_the_whole_point():
    """Two measurements, opposite signs, one cause. Sizing a variant alone gives it a core that is too
    light; pinning the reference variant's core still pins one lighter than the real shared core, and a core
    lighter than the real one flatters the payload. A family shows both at once, which neither a single
    vehicle nor a single method can."""
    f = fam.find(ROOT, "delta_ii")
    sized = {r["key"]: r for r in sized_family("delta_ii")}
    pinned = {r["key"]: r for r in fam.pinned_family(f, ASSUMP)}
    for key in ("7320", "7420"):
        assert sized[key]["glom_err"] < 0 < pinned[key]["payload_err"], \
            f"{key}: expected under-prediction when sized alone and over-prediction when pinned, got " \
            f"{sized[key]['glom_err']:+.1%} and {pinned[key]['payload_err']:+.1%}"
    assert pinned["7320"]["payload_err"] == pytest.approx(0.231, abs=0.06)
    assert pinned["7420"]["payload_err"] == pytest.approx(0.197, abs=0.06)
    # the reference variant is the one point both methods must agree on, because nothing is being changed
    assert pinned["7920"]["payload_err"] == pytest.approx(0.0, abs=0.01)


def test_the_reference_variant_reproduces_its_own_design_file():
    """The Ariane family's base IS validation/ariane64.yaml, so the reference variant must size to exactly
    what that file sizes to on its own - otherwise the overrides are changing something they should not."""
    f = fam.find(ROOT, "ariane_6")
    direct = size_vehicle(load_design(os.path.join(ROOT, "validation", "ariane64.yaml"), ASSUMP),
                          keep_history=False)
    via_family = size_vehicle(f.reference_variant.spec(ASSUMP), keep_history=False)
    assert via_family.glom_kg == pytest.approx(direct.glom_kg, rel=1e-12)
    assert via_family.payload_mass_kg == pytest.approx(direct.payload_mass_kg, rel=1e-12)


def test_the_62_variant_reproduces_the_shipped_ariane62_design():
    """And the other direction: the A62 expressed as overrides on the A64 must give the same vehicle as the
    separately shipped validation/ariane62.yaml. If it does not, the two files differ in something this
    manifest claims they do not - which is exactly the drift the manifest exists to prevent."""
    f = fam.find(ROOT, "ariane_6")
    shipped = size_vehicle(load_design(os.path.join(ROOT, "validation", "ariane62.yaml"), ASSUMP),
                           keep_history=False)
    via_family = size_vehicle(f.variant("62").spec(ASSUMP), keep_history=False)
    assert via_family.glom_kg == pytest.approx(shipped.glom_kg, rel=1e-9), \
        "the A62-as-overrides and the shipped A62 design have diverged"
    assert via_family.stages[0].m_prop_loaded_kg == pytest.approx(shipped.stages[0].m_prop_loaded_kg, rel=1e-9)


def test_a_variant_without_a_booster_count_is_reported_not_crashed():
    f = fam.find(ROOT, "delta_ii")
    v = f.variant("7320")
    keep = dict(v.overrides)
    try:
        v.overrides.pop("boosters.n_total")
        rows = {r["key"]: r for r in fam.pinned_family(f, ASSUMP)}
        assert not rows["7320"]["flyable"]
        assert "boosters.n_total" in rows["7320"]["reason"]
    finally:
        v.overrides.clear()
        v.overrides.update(keep)
