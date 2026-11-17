"""Published solid-stage inert-mass relations (R18).

The point of this file is that a published coefficient is not taken on trust. Both sources tabulate the
stages they fitted, so every relation here is re-fitted from that same table and compared with what the
source printed. That is how the ambiguous constant in Zandbergen's S2 was resolved (tonnes, not kilograms)
and how the two transcriptions were confirmed.

It also measures what the relations are worth on data they did not come from, which is the part a user
actually needs: Kibbey's NASA technology parameters turn out to under-predict Zandbergen's 34 flown stages
by 22-58%, and that is recorded here rather than smoothed over.
"""
import math

import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import solid_inert as si
from launch_vehicle import solid_motor as sm
from launch_vehicle.config_io import load_design
from launch_vehicle.convergence import size_vehicle

ASSUMP_ = ASSUMP


# --------------------------------------------------------------- the data, and the published fits
def test_the_dataset_is_the_one_the_sources_tabulate():
    steel = si.by_case("steel")
    comp = si.by_case("composite")
    assert len(steel) == 17 and len(comp) == 17, "both source tables hold 17 stages"
    assert len(si.DATASET) == 34
    for s in si.DATASET:
        assert s.m_prop_kg > 0 and s.m_inert_kg > 0, s.name
        assert 0.02 < s.f_inert < 0.5, f"{s.name}: inert fraction {s.f_inert:.3f} is not credible"
        # lambda and f are two spellings of one number
        assert s.lambda_pmf == pytest.approx(1.0 / (1.0 + s.f_inert), rel=1e-12)
    assert any("Vega P80" in s.name for s in comp)
    assert any("Space Shuttle SRB" in s.name for s in steel)


def test_the_published_steel_coefficient_is_reproduced_from_the_published_table():
    """Zandbergen S1 is m_i = 0.1707 m_p. Refitting his own 17 steel stages must give that back."""
    a = si.fit_proportional(si.by_case("steel"))
    assert a == pytest.approx(0.1707, abs=5e-5), f"refit {a:.4f} against the printed 0.1707"


def test_the_published_composite_coefficient_is_reproduced_within_two_percent():
    a = si.fit_proportional(si.by_case("composite"))
    assert a == pytest.approx(0.1110, rel=0.03), f"refit {a:.4f} against the printed 0.1110"


def test_the_ambiguous_steel_constant_is_tonnes_not_kilograms():
    """The source prints S2's constant two ways. Refitting its own table settles which is meant.

    m_i = 0.1689 m_p + C. If C were 1,173 kg the refit would land near that; it lands near 590 kg, which
    is the tonnes reading of the printed 0.5090. Getting this wrong would put a 600 kg error on every
    steel-cased stage, which on a small motor is the whole inert mass.
    """
    a, b = si.fit_affine(si.by_case("steel"))
    assert a == pytest.approx(0.1689, rel=0.02), f"slope {a:.4f}"
    assert 400.0 < b < 800.0, f"intercept {b:,.0f} kg is consistent with 0.509 t, not with 1,173 kg"
    assert abs(b - 1173.0) > 300.0, "the kilograms reading would be inconsistent with the source's own data"


def test_the_power_law_refit_is_close_to_the_printed_one():
    """A log-log refit is not the same estimator as a fit in linear space, so agreement is approximate."""
    a, b = si.fit_power(si.by_case("steel"))
    assert b == pytest.approx(0.9030, abs=0.02), f"exponent {b:.4f} against the printed 0.9030"
    a_t = a / 1000.0 ** (1.0 - b)                            # express in the source's tonne units
    assert a_t == pytest.approx(0.2851, rel=0.10), f"coefficient {a_t:.4f} against the printed 0.2851"


# ------------------------------------------------------- what the relations are worth, measured
def test_the_zandbergen_relations_are_near_unbiased_on_their_own_data():
    for key in ("zandbergen_steel_S2", "zandbergen_steel_S3",
                "zandbergen_composite_C1", "zandbergen_composite_C2"):
        st = si.error_stats(key)
        assert abs(st["mpe"]) < 0.05, f"{key}: mean error {100*st['mpe']:+.1f}% is a bias, not scatter"
        assert st["mape"] < 0.25, f"{key}: mean absolute error {100*st['mape']:.0f}%"


def test_the_nasa_size_dependent_relations_underpredict_flown_stages_and_we_say_so():
    """Kibbey's technology parameters describe concept vehicles, not the historical population.

    This is not a transcription error to be fixed - it is a real disagreement between two published
    sources, and the number is pinned here so nobody adopts kibbey_low as a default by accident.
    """
    high = si.error_stats("kibbey_high")
    med = si.error_stats("kibbey_medium")
    low = si.error_stats("kibbey_low")
    assert high["mpe"] < -0.15, "kibbey_high should come out light against flown stages"
    assert med["mpe"] < low_bound(high["mpe"]), "medium should be lighter still"
    assert low["mpe"] < med["mpe"], "low should be the lightest"
    assert low["mpe"] < -0.50, f"kibbey_low under-predicts by {100*low['mpe']:+.0f}%"


def low_bound(x):
    return x


def test_every_relation_knows_what_mass_it_predicts():
    for key, rel in si.RELATIONS.items():
        assert rel.predicts in ("stage", "motor"), key
        assert rel.source and rel.stats, key
        assert rel.valid_kg[0] < rel.valid_kg[1]
        assert 0 < rel.scatter < 1, f"{key}: scatter {rel.scatter} is not a fraction"
    # STAGE_RELATIONS is the subset that predicts a finished stage, and it is the subset for which
    # mass_budget suppresses the bottom-up build-up. A motor-level relation must NOT be in it, or the
    # skirts, interstage, avionics and wiring would be dropped and the stage built short.
    assert set(si.STAGE_RELATIONS) == {k for k, r in si.RELATIONS.items() if r.predicts == "stage"}
    assert set(si.STAGE_RELATIONS) < set(si.RELATIONS), (
        "every relation is stage-level again; if that is deliberate, this test should say why")
    for key in set(si.RELATIONS) - set(si.STAGE_RELATIONS):
        assert si.RELATIONS[key].predicts == "motor"


def test_a_relation_outside_its_fitted_range_says_so():
    _m, _k, src = sm.casing_mass(50.0, "zandbergen_composite_C1")
    assert "EXTRAPOLATED" in src, "a 50 kg motor is far below the 3 t floor of the fit"
    _m, _k, ok = sm.casing_mass(50_000.0, "zandbergen_composite_C1")
    assert "EXTRAPOLATED" not in ok


# ------------------------------------------------------------------ wiring into the mass budget
def test_a_stage_level_relation_is_recognised_as_such():
    assert sm.is_stage_level("zandbergen_composite_C1")
    assert sm.is_stage_level("kibbey_high")
    assert not sm.is_stage_level("book_steel")
    assert not sm.is_stage_level("book_composite")
    assert not sm.is_stage_level("mass_fraction")


def test_the_component_build_up_is_suppressed_so_nothing_is_counted_twice():
    """The relation contains the skirts. If the bottom-up build-up still ran, they would be added again."""
    path = os.path.join(ROOT, "validation", "vega.yaml")
    # book_composite is forced: Vega ships with kibbey_medium since v0.26, which is itself a stage-level
    # relation, so the design file's own method would no longer exercise the bottom-up build-up at all.
    book = size_vehicle(load_design(path, ASSUMP_, {
        "stages.0.motor.casing_mass_method": "book_composite"}))
    rel = size_vehicle(load_design(path, ASSUMP_, {
        "stages.0.motor.casing_mass_method": "zandbergen_composite_C1",
        "stages.0.inert_mass_margin_fraction": 0.0}))

    assert any("Motor casing" in k for k in book.stages[0].components), "the book path builds components"
    comps = rel.stages[0].components
    # the margin line is added by the stage assembly, outside the build-up; with the margin set to zero it
    # must carry no mass, and nothing else may be present
    assert comps.get("Mass growth margin", 0.0) == pytest.approx(0.0, abs=1e-9)
    body = {k: v for k, v in comps.items() if k != "Mass growth margin"}
    assert len(body) == 1, f"a stage-level relation must yield one component, got {list(body)}"
    key = next(iter(body))
    assert "Solid stage inert" in key and "zandbergen_composite_C1" in key
    for gone in ("Aft skirt", "Forward skirt", "Interstage", "Avionics", "Wiring"):
        assert not any(gone in k for k in comps), f"{gone} was added on top of a stage-level relation"
    # and the number is the relation's own answer
    assert body[key] == pytest.approx(0.1110 * rel.stages[0].m_prop_loaded_kg, rel=1e-6)


def test_the_published_relation_brings_the_small_solid_launchers_back_into_range():
    """The result R18 exists for. Checked on two vehicles, not one."""
    for case, ref_glom, book_floor in (("pegasus_xl", 23130, 1.40), ("epsilon", 95400, 1.40)):
        path = os.path.join(ROOT, "validation", case + ".yaml")
        spec0 = load_design(path, ASSUMP_)
        ov, book_ov = {}, {}
        for i, s in enumerate(spec0.stages):
            if s.is_solid:
                ov[f"stages.{i}.motor.casing_mass_method"] = "zandbergen_composite_C1"
                ov[f"stages.{i}.inert_mass_margin_fraction"] = 0.0
                # The book constant is FORCED here rather than taken from the design file. These cases ship
                # with kibbey_medium since v0.26, so relying on the file's own method would have this test
                # silently comparing two published relations and calling one of them "the book method".
                book_ov[f"stages.{i}.motor.casing_mass_method"] = "book_composite"
        book = size_vehicle(load_design(path, ASSUMP_, book_ov))
        rel = size_vehicle(load_design(path, ASSUMP_, ov))
        assert book.glom_kg > book_floor * ref_glom, \
            f"{case}: the book method is supposed to be the heavy one ({book.glom_kg:,.0f})"
        err = abs(rel.glom_kg - ref_glom) / ref_glom
        assert err < 0.15, f"{case}: published relation still {100*err:.0f}% out ({rel.glom_kg:,.0f} kg)"
        assert rel.glom_kg < book.glom_kg


def test_the_validator_accepts_every_relation_and_warns_what_it_means():
    from launch_vehicle.validation import CASING_METHODS
    assert set(si.RELATIONS) <= set(CASING_METHODS), "a relation exists that the validator would reject"
    for m in ("book_steel", "book_composite", "mass_fraction", "user_mass"):
        assert m in CASING_METHODS, "the book's methods must stay available"
    path = os.path.join(ROOT, "validation", "vega.yaml")
    res = size_vehicle(load_design(path, ASSUMP_, {
        "stages.0.motor.casing_mass_method": "zandbergen_composite_C1"}))
    codes = {i.code for i in res.issues}
    assert "CASESTAGE" in codes, "the user must be told the relation covers the whole stage"
    assert "CASEMARGIN" in codes, "a margin on top of flown hardware deserves a warning"


def test_the_gui_offers_exactly_what_the_validator_accepts():
    import yaml
    from launch_vehicle import gui_meta as M
    from launch_vehicle.config_io import _Loader
    from launch_vehicle.validation import CASING_METHODS
    with open(ASSUMP_, encoding="utf-8") as fh:
        a = yaml.load(fh, Loader=_Loader)
    offered = {v for v, _lab in M.choices_for("stages.0.motor.casing_mass_method", M.library_choices(a))}
    assert offered == set(CASING_METHODS), f"GUI and validator disagree: {offered ^ set(CASING_METHODS)}"
    labels = dict(M.choices_for("stages.0.motor.casing_mass_method", M.library_choices(a)))
    # Every relation must declare its scope in the label, because picking a stage-level relation where a
    # motor-level one was meant silently drops the skirts and avionics - and the other way round double-
    # counts them. The word has to match what the relation actually predicts.
    for key, rel in si.RELATIONS.items():
        want = "whole stage" if rel.predicts == "stage" else "motor only"
        assert want in labels[key], f"{key} predicts {rel.predicts} but its label says {labels[key]!r}"


def test_residuals_are_published_not_just_the_r_squared():
    rows = si.residuals("zandbergen_composite_C1")
    assert len(rows) == 17
    for r in rows:
        assert {"stage", "m_prop_kg", "actual_kg", "predicted_kg", "error", "in_range"} <= set(r)
    worst = max(rows, key=lambda r: abs(r["error"]))
    assert abs(worst["error"]) > 0.15, "a 17-stage fit with no outlier would be suspicious"
    # the source's own caveats travel with the data
    assert any("motor-only" in (r["note"] or "") for r in rows)


def test_the_relation_applies_to_solid_strap_ons_as_well_as_serial_stages():
    """Most of the stages these relations were fitted to ARE strap-ons - the Shuttle SRB, the EAP, the SRB-A.

    The booster path builds its own components (nose cone, attach hardware, margin) on top of the casing
    mass, so it needs the same double-count suppression a serial stage got, and this checks it has it.
    """
    path = os.path.join(ROOT, "validation", "h2a_202.yaml")
    book = size_vehicle(load_design(path, ASSUMP_))
    rel = size_vehicle(load_design(path, ASSUMP_, {
        "boosters.inert_mass_method": "zandbergen_composite_C1",
        "boosters.inert_mass_margin_fraction": 0.0}))

    assert any("Casing" in k for k in book.boosters.components)
    comps = rel.boosters.components
    assert len(comps) == 1, f"a stage-level relation must yield one component, got {list(comps)}"
    assert "Booster inert" in next(iter(comps))
    for gone in ("Nose cone", "Attach"):
        assert not any(gone in k for k in comps), f"{gone} was added on top of a whole-stage relation"
    # the nose cone still exists geometrically even though its mass is inside the relation
    assert rel.boosters.length_m == pytest.approx(book.boosters.length_m, rel=1e-6), \
        "suppressing the nose cone's MASS must not change the booster's LENGTH"


def test_the_relations_help_most_solid_vehicles_and_the_exception_is_named():
    """Six of seven improve. Atlas V 551 does not, and that is recorded rather than averaged away."""
    cases = {"vega": 137000, "pegasus_xl": 23130, "epsilon": 95400, "h2a_202": 285000}
    for key, ref in cases.items():
        path = os.path.join(ROOT, "validation", key + ".yaml")
        spec0 = load_design(path, ASSUMP_)
        ov, book_ov = {}, {}
        for i, s in enumerate(spec0.stages):
            if s.is_solid:
                ov[f"stages.{i}.motor.casing_mass_method"] = "zandbergen_composite_C1"
                ov[f"stages.{i}.inert_mass_margin_fraction"] = 0.0
                # forced, not inherited: these cases ship with kibbey_medium since v0.26
                book_ov[f"stages.{i}.motor.casing_mass_method"] = "book_composite"
        if getattr(spec0, "boosters", None) is not None and spec0.boosters.kind == "solid":
            ov["boosters.inert_mass_method"] = "zandbergen_composite_C1"
            ov["boosters.inert_mass_margin_fraction"] = 0.0
            book_ov["boosters.inert_mass_method"] = "book_composite"
        book = size_vehicle(load_design(path, ASSUMP_, book_ov))
        rel = size_vehicle(load_design(path, ASSUMP_, ov))
        assert abs(rel.glom_kg - ref) < abs(book.glom_kg - ref), (
            f"{key}: the published relation should be closer than the book's "
            f"({rel.glom_kg:,.0f} vs {book.glom_kg:,.0f} against {ref:,.0f})")


# ------------------------------------------------------------------ why the composite default is Kibbey
def test_the_book_composite_constant_has_no_scale_term_and_real_motors_do():
    """The reason the default changed, stated as a measurement rather than a preference.

    Eq. 8:18 is k * m_p with k = 0.1154 for graphite-epoxy, so it predicts the same inert FRACTION for a
    141-tonne P120C as for a 215 kg Altair. Real motors do not: the fraction climbs steeply as motors get
    small. Any relation without a scale term must therefore be wrong at one end or the other.
    """
    from launch_vehicle import solid_motor as sm
    big, _k_big, _s = sm.casing_mass(141634.0, "book_composite")
    small, _k_small, _s2 = sm.casing_mass(215.0, "book_composite")
    assert abs(big / 141634.0 - small / 215.0) < 1e-12, "the book constant is scale-free by construction"
    km_big = si.get("kibbey_medium").inert_kg(141634.0) / 141634.0
    km_small = si.get("kibbey_medium").inert_kg(215.0) / 215.0
    assert km_small > km_big * 1.2, (
        f"a size-dependent relation must charge a small motor more per kg: {km_small:.4f} vs {km_big:.4f}")


def test_kibbey_is_not_used_on_steel_cases_because_it_is_badly_wrong_there():
    """Material beats fitting form, measured on two published steel motors.

    Ariane 5's EAP P241 is segmented steel at 240,000 kg propellant / ~33,000 kg inert, and Scout's Algol IIB
    is steel at 12,817 / 1,939. Kibbey's nominal band is a composite-era technology level and comes out
    45-49 % light on both, where the book's steel constant is within a few per cent. This pins the reason
    steel stages were deliberately left alone when the composite default changed.
    """
    for m_p, inert in ((240000.0, 33000.0), (12817.0, 1939.0)):
        real = inert / m_p
        kib = si.get("kibbey_medium").inert_kg(m_p) / m_p
        steel = 0.135
        assert kib < real * 0.7, f"kibbey_medium should be far light on steel: {kib:.4f} vs real {real:.4f}"
        assert abs(steel - real) / real < abs(kib - real) / real, (
            "the book steel constant must beat kibbey_medium on a steel case")


def test_star_motor_is_not_the_composite_default_because_it_would_extrapolate():
    """It measures as well as kibbey_medium on the check set, and is still not the default.

    star_motor is fitted to 25-4,300 kg motors. Vega C's first stage carries 141,634 kg, a 33x extrapolation
    past its own declared range, which its docstring explicitly forbids. Measuring well out there is luck,
    not validity, so the range is what decides.
    """
    r = si.get("star_motor")
    lo, hi = r.valid_kg
    assert not r.in_range(141634.0), "Vega C's first stage must be outside the STAR fit"
    assert 141634.0 / hi > 20.0, f"and far outside: {141634.0 / hi:.0f}x the ceiling of {hi:,.0f} kg"
    assert r.in_range(1000.0), "while an upper-stage-class motor is inside it"
