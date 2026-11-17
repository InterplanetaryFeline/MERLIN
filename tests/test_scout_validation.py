"""The Scout G-1 check case, and what its four stages say about the solid inert relations.

Scout earns its place in the validation set for one reason: it is the only vehicle here whose per-stage INERT
masses are published by the manufacturer, and its four stages span 12,817 kg down to 215 kg of propellant.
Everything else in the set is either bigger, or has only a wiki number for the dry mass, or both.

Two things are tested, and they are deliberately separate.

  * The DATA. The case is built from the manufacturer's own figures and must stay that way. The test below
    pins every published number against its source, so a later edit that nudges a mass to make the answer
    nicer fails here rather than silently improving the validation report.
  * The RELATIONS, tested at matched propellant load. Giving a relation Scout's published propellant and
    comparing its answer against Scout's published inert is a clean test: no delta-v budget, no loss model,
    no Isp, nothing that could absorb the error. That is what makes these numbers worth quoting.

What it finds is that the published stage-level regressions UNDER-predict Scout's two small upper stages by
37-68 %, against an in-sample bias of -3 % to +1 %. Both stages sit below the fitted floor of every
Zandbergen relation, so this is extrapolation error, and the test asserts the direction and the rough
magnitude so that a future refit cannot quietly lose it.
"""
import math
import os

import yaml

from launch_vehicle import solid_inert as si
from launch_vehicle.config_io import _Loader, load_design
from launch_vehicle.solid_motor import casing_mass

CASE = os.path.join("validation", "scout_g1.yaml")
ASSUMPTIONS = os.path.join("config", "engineering_assumptions.yaml")

#: The manufacturer's own figures: (propellant kg, stage inert kg, diameter m, length m).
#: Tanck & Williams (LTV Missiles and Electronics Group), "The Scout Launch Vehicle System", Figure 4,
#: citing SCOUT Planning Guide (LTV, May 1987).
PUBLISHED = {
    1: (12817.0, 1939.0, 1.14, 9.07),
    2: (3768.0, 1064.0, 0.79, 6.19),
    3: (1299.0, 335.0, 0.76, 2.89),
    4: (215.0, 41.0, 0.51, 1.46),
}
PUBLISHED_LIFTOFF_KG = 21543.0          # four stages + heatshield, EXCLUDING payload
PUBLISHED_PAYLOAD_KG = 165.0            # to 555 km circular polar, from Vandenberg
PUBLISHED_LENGTH_M = 22.90


# ------------------------------------------------------------------ the published data must stay published
def test_the_published_masses_add_up_to_the_published_lift_off_weight():
    """The arithmetic that shows what the 21,543 kg figure actually contains.

    The stages sum to 21,478 kg, which leaves 65 kg - the heatshield, and nothing else. So the published
    lift-off weight EXCLUDES the payload, and anything comparing a sized GLOM against it has to add the
    165 kg back. Getting this wrong would be a silent 0.8 % error in the headline validation number.
    """
    stages = sum(p + i for p, i, _, _ in PUBLISHED.values())
    assert abs(stages - 21478.0) < 1.0, stages
    left_over = PUBLISHED_LIFTOFF_KG - stages
    assert 50.0 < left_over < 120.0, (
        f"{left_over:.0f} kg is left over after the stages. That gap is the heatshield; if it no longer "
        "looks like a heatshield, one of the published masses has been changed")


def test_the_two_lower_stages_match_zandbergens_independent_table_exactly():
    """Scout S1 and S2 are already in DATASET, from a completely different source.

    Zandbergen's table and the LTV paper were compiled independently, so their agreeing to the kilogram is
    the strongest evidence available that both are reporting the real vehicle.
    """
    by_name = {s.name: s for s in si.DATASET}
    for key, name in ((1, "Scout S1 (Algol III)"), (2, "Scout S2 (Castor 2A)")):
        prop, inert, _, _ = PUBLISHED[key]
        assert abs(by_name[name].m_prop_kg - prop) < 1.0, name
        assert abs(by_name[name].m_inert_kg - inert) < 1.0, name


def test_the_design_file_carries_the_published_masses_and_names_its_source():
    with open(CASE, encoding="utf-8") as fh:
        doc = yaml.load(fh, Loader=_Loader)
    assert len(doc["stages"]) == 4
    for i, st in enumerate(doc["stages"]):
        _, _, dia, _ = PUBLISHED[i + 1]
        assert abs(st["diameter_m"]["v"] - dia) < 0.005, f"stage {i + 1} diameter"
        assert "SCOUT Planning Guide" in st["diameter_m"]["s"], (
            f"stage {i + 1} diameter does not cite the manufacturer's document")
        assert st["stage_type"]["v"] == "solid"


def test_the_isp_values_are_tagged_for_what_they_really_are():
    """Published where published, derived where derived. This is the line that must not blur.

    Thiokol publishes the Isp of the two upper motors; nothing found publishes it for Algol IIIA or
    Castor IIA, so those two are derived and tagged `assumed`, with the arithmetic in the source string.
    """
    with open(CASE, encoding="utf-8") as fh:
        doc = yaml.load(fh, Loader=_Loader)
    isp = [st["motor"]["isp_vac_s"] for st in doc["stages"]]
    for i in (0, 1):
        assert isp[i]["t"] == "assumed", f"stage {i + 1} Isp is derived and must not be tagged reference"
        assert "DERIVED" in isp[i]["s"], f"stage {i + 1} Isp does not show its derivation"
    for i in (2, 3):
        assert isp[i]["t"] == "reference", f"stage {i + 1} Isp is published and should be tagged reference"
        assert "Thiokol" in isp[i]["s"]
    assert isp[2]["v"] == 293.5 and isp[3]["v"] == 286.5, "the Thiokol catalogue values"


def test_the_case_loads_and_uses_the_launch_site_library():
    spec = load_design(CASE, ASSUMPTIONS)
    assert spec.launch_site_note is not None, "the case should name its launch site rather than a bare latitude"
    assert spec.launch_site_note["entry"] == "Vandenberg Space Force Base"
    assert abs(spec.mission["site_latitude_deg"] - 34.7720) < 1e-6, "latitude should come from the library"
    assert spec.mission["inclination_deg"] == 90.0
    assert len(spec.stages) == 4 and all(s.is_solid for s in spec.stages)


def test_the_published_vehicle_closes_its_own_mission():
    """Before blaming the tool, check the data: do Scout's own masses fly Scout's own mission?

    Ideal delta-v from the published masses must land near orbital speed at 555 km plus a believable loss
    allowance. If this failed, the case would be built on numbers that never described a real rocket, and
    nothing downstream would mean anything.
    """
    g0 = 9.80665
    isp = {1: (229.0 + 2 * 254.8) / 3, 2: 262.0, 3: 293.5, 4: 286.5}
    m = sum(p + i for p, i, _, _ in PUBLISHED.values()) + PUBLISHED_PAYLOAD_KG
    total = 0.0
    for k in (1, 2, 3, 4):
        prop, inert, _, _ = PUBLISHED[k]
        total += isp[k] * g0 * math.log(m / (m - prop))
        m = m - prop - inert
    v_circ = math.sqrt(398600.4418 / (6371.0 + 555.0)) * 1000.0
    losses = total - v_circ
    assert 8500.0 < total < 9600.0, f"ideal delta-v {total:,.0f} m/s is not what a Scout-sized vehicle makes"
    assert 1200.0 < losses < 1900.0, (
        f"implied losses {losses:,.0f} m/s are outside anything believable for a ground launch, so the "
        "published masses and the published payload do not describe the same vehicle")


# ------------------------------------------------------------------ the relations, at matched propellant
def _predictions(stage_no):
    """What every applicable relation predicts for this stage's PUBLISHED propellant load."""
    prop, inert, _, _ = PUBLISHED[stage_no]
    case = "steel" if stage_no <= 2 else "composite"
    out = {}
    for key, rel in si.RELATIONS.items():
        if rel.case in (case, "any"):
            out[key] = rel.inert_kg(prop)
    return prop, inert, out


def test_both_small_upper_stages_are_below_every_zandbergen_fit_floor():
    """Which is the whole point of them: they are the only data here about that range."""
    for stage_no in (3, 4):
        prop = PUBLISHED[stage_no][0]
        for key, rel in si.RELATIONS.items():
            if rel.key.startswith("zandbergen"):
                assert not rel.in_range(prop), (
                    f"{key} now claims to cover {prop:,.0f} kg; this test exists because it did not")
    # and the two lower stages ARE inside the steel relations' range, so the contrast is real
    assert si.RELATIONS["zandbergen_steel_S1"].in_range(PUBLISHED[1][0])


def test_the_relations_under_predict_scouts_small_stages():
    """The finding. Direction first, because a sign change would mean something quite different."""
    for stage_no in (3, 4):
        prop, inert, preds = _predictions(stage_no)
        for key, pred in preds.items():
            assert pred < inert, (
                f"{key} predicts {pred:,.0f} kg for Scout stage {stage_no}, at or above the published "
                f"{inert:,.0f} kg. Every relation under-predicted when this was written")


def test_the_out_of_sample_error_is_large_and_recorded():
    """Magnitude, so a refit that quietly fixed or worsened this has to come and change the number."""
    for key, rel in si.RELATIONS.items():
        pool = [s for s in si.OUT_OF_SAMPLE if rel.case in (s.case, "any")]
        if not pool:
            continue
        st = si.error_stats(key, pool)
        assert st["n"] == 2
        assert -0.75 < st["mpe"] < -0.30, (
            f"{key} out-of-sample bias is {st['mpe']:+.1%}; it was between -37% and -68% when this case "
            "was added, and a move outside -30%..-75% is a result worth looking at, not worth hiding")


def test_out_of_sample_is_kept_out_of_the_fitting_set():
    """DATASET defines what the published relations were fitted to and must not grow by accident."""
    assert len(si.DATASET) == 34, "DATASET is Zandbergen's fitting set; adding to it invalidates the refits"
    names = {s.name for s in si.DATASET}
    for s in si.OUT_OF_SAMPLE:
        assert s.name not in names, f"{s.name} is in both the fitting set and the out-of-sample set"


def test_the_books_casing_mer_lands_below_the_published_stage_inert():
    """A sanity check with a real edge to it.

    The book's k_SRM is a MOTOR-level number, so against a STAGE-level published inert - which also carries
    skirts, interstage, avionics and separation hardware - it must come out lower. If it ever came out
    higher, either the book coefficient is being applied at the wrong level or the published figure is not
    stage-level, and both would invalidate every solid comparison in the validation report.
    """
    for stage_no in (1, 2, 3, 4):
        prop, inert, _, _ = PUBLISHED[stage_no]
        method = "book_steel" if stage_no <= 2 else "book_composite"
        mass, _k, _src = casing_mass(prop, method)
        assert mass < inert, (
            f"stage {stage_no}: the book's motor-level casing MER gives {mass:,.0f} kg against a "
            f"stage-level published inert of {inert:,.0f} kg")
        assert mass > 0.3 * inert, (
            f"stage {stage_no}: casing {mass:,.0f} kg is under a third of the {inert:,.0f} kg stage inert, "
            "which would mean the build-up is carrying almost all of the mass")
