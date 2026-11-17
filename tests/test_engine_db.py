"""R2: the engine and motor database (method register M55, M56).

Two things matter about a database of real hardware: that every row carries a source and a confidence, and that
referencing a row *fills* a design without ever overriding what the designer wrote. The third group of tests
covers the power-cycle pressure bands, which are a plausibility flag and not a limit.
"""
import os
import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import engine_db as db
from launch_vehicle.config_io import load_design, load_yaml_annotated, build_spec

NUMERIC = ("thrust_vac_N", "thrust_sl_N", "isp_vac_s", "isp_sl_s", "chamber_pressure_Pa",
           "expansion_ratio", "mass_kg", "length_m", "exit_diameter_m", "of_ratio")


# ------------------------------------------------------------------ the data itself
def test_every_row_has_a_name_a_kind_a_source_and_a_confidence():
    rows = db.entries()
    assert len(rows) >= 8
    names = [r["name"] for r in rows]
    assert len(names) == len(set(names)), "duplicate engine names would make a lookup ambiguous"
    for r in rows:
        assert r["kind"] in ("liquid", "solid"), r["name"]
        assert r.get("source"), f"{r['name']} has no source"
        assert r.get("confidence") in ("published", "approximate"), r["name"]


def test_unknown_fields_are_null_and_never_invented():
    """A database row is allowed to be incomplete; it is not allowed to guess. Nulls stay null."""
    rows = {r["name"]: r for r in db.entries()}
    mv = rows["Merlin 1D Vacuum"]
    assert mv["mass_kg"] is None and mv["thrust_sl_N"] is None
    assert mv["isp_vac_s"] == 348.0


def test_numbers_are_physically_sane():
    for r in db.entries():
        for k in NUMERIC:
            v = r.get(k)
            assert v is None or v > 0, f"{r['name']}.{k} = {v}"
        if r.get("isp_sl_s") and r.get("isp_vac_s"):
            assert r["isp_sl_s"] < r["isp_vac_s"], f"{r['name']}: sea-level Isp must be below vacuum Isp"
        if r.get("thrust_sl_N") and r.get("thrust_vac_N"):
            assert r["thrust_sl_N"] < r["thrust_vac_N"], f"{r['name']}: sea-level thrust must be below vacuum"
        # A row must carry at least ONE specific impulse, and every one it carries must be physical. Requiring a
        # VACUUM figure of every row would be requiring the database to invent: book Table 4.11 (p.241) gives the
        # F-1 a sea-level Isp of 263 s and no vacuum value, so that row's isp_vac_s is genuinely empty and the
        # engine database reports it as unsupplied rather than filling it with a figure the source does not give.
        isps = [r.get("isp_vac_s"), r.get("isp_sl_s")]
        assert any(v is not None for v in isps), f"{r['name']}: no specific impulse at all"
        for v in isps:
            assert v is None or 150.0 < v < 500.0, f"{r['name']}: Isp {v} s is not physical"


def test_known_rows_match_their_cited_sources():
    """Spot checks against the figures each row cites, so a careless edit cannot drift the data."""
    rows = {r["name"]: r for r in db.entries()}
    m = rows["Merlin 1D"]
    assert (m["thrust_sl_N"], m["thrust_vac_N"]) == (845000.0, 981000.0)
    assert (m["isp_sl_s"], m["isp_vac_s"]) == (282.0, 311.0)
    assert m["chamber_pressure_Pa"] == 9.7e6 and m["mass_kg"] == 470.0
    rd = rows["RD-180"]
    assert (rd["thrust_sl_N"], rd["thrust_vac_N"]) == (3830000.0, 4150000.0)
    assert (rd["isp_sl_s"], rd["isp_vac_s"]) == (311.0, 338.0)
    assert rd["chamber_pressure_Pa"] == 26.7e6 and rd["expansion_ratio"] == 36.87
    assert rd["mass_kg"] == 5480.0 and rd["of_ratio"] == 2.72


def test_lookup_is_by_exact_name_and_a_miss_says_what_is_available():
    e = db.find("RL10B-2")
    assert e["cycle"] == "expander" and e["isp_vac_s"] > 460.0
    with pytest.raises(db.EngineDBError) as ex:
        db.find("Raptor 7")
    assert "Raptor 7" in str(ex.value)


# ------------------------------------------------------------------ the cycles
def test_every_cycle_has_a_pressure_band_and_a_source():
    cy = db.cycles()
    assert {"pressure_fed", "gas_generator", "staged_combustion", "expander"} <= set(cy)
    for name, c in cy.items():
        lo, hi = c["chamber_pressure_bar"]
        assert 0 < lo < hi, name
        assert c.get("source"), name


def test_cycle_bands_order_as_the_physics_does():
    """Pressure-fed cannot beat a pump, and staged combustion runs hotter and harder than a gas generator."""
    cy = db.cycles()
    pf_hi = cy["pressure_fed"]["chamber_pressure_bar"][1]
    gg_hi = cy["gas_generator"]["chamber_pressure_bar"][1]
    sc_hi = cy["staged_combustion"]["chamber_pressure_bar"][1]
    assert pf_hi < gg_hi < sc_hi


def test_every_database_engine_sits_inside_its_own_cycle_band():
    for r in db.entries():
        if r["kind"] != "liquid" or not r.get("chamber_pressure_Pa") or not r.get("cycle"):
            continue
        lo, hi = db.cycle_pressure_band_Pa(r["cycle"])
        assert lo <= r["chamber_pressure_Pa"] <= hi, \
            f"{r['name']}: {r['chamber_pressure_Pa']/1e5:.0f} bar outside the {r['cycle']} band"


# ------------------------------------------------------------------ using a row in a design
def _design_with_engine(name, extra=None):
    """Mirror load_design: unwrap the YAML, expand the database references, then build the spec."""
    design, meta, reg = load_yaml_annotated(DESIGN)
    # load_yaml_annotated returns the design already unwrapped to plain values, with the {v,u,d,s,t} metadata
    # moved into the register, so the database reference is set as a plain name here
    design["stages"][1]["engine"]["from_database"] = name
    for k, v in (extra or {}).items():
        design["stages"][1]["engine"][k] = v
    assump, _, reg = load_yaml_annotated(ASSUMP, reg)
    notes = db.expand_design(design, reg)
    spec = build_spec(design, assump, reg, name="db-test")
    spec.engine_db_notes = notes
    return spec, notes


def test_a_database_row_fills_only_what_the_design_left_out():
    """The contract: a row is a default, never an override. The default design already states an Isp and an area
    ratio, so those stay; the engine mass and the cycle, which it does not state, are filled."""
    spec, notes = _design_with_engine("RL10B-2")
    note = [n for n in notes if n["context"] == "stages.1.engine"][0]
    assert "mass_user_per_engine_kg" in note["filled"] and "cycle" in note["filled"]
    assert spec.stages[1].engine.mass_user_kg == db.find("RL10B-2")["mass_kg"]
    assert spec.stages[1].engine.cycle == "expander"
    assert spec.stages[1].engine.db_entry == "RL10B-2"


def test_a_row_that_disagrees_with_the_design_is_reported_not_silently_ignored():
    """A design that names a real engine and then flies it at another Isp is a half-edited template; the tool
    keeps the designer's number (the contract) and says so loudly."""
    from launch_vehicle.validation import validate_spec
    spec, notes = _design_with_engine("RL10B-2")
    overridden = {o["field"] for n in notes for o in n["overridden"]}
    assert {"isp_vac_s", "expansion_ratio"} <= overridden
    codes = {i.code for i in validate_spec(spec)}
    assert "ENGDBOVR" in codes


def test_absolute_thrust_is_not_filled_into_a_stage_sized_by_thrust_to_weight():
    """Filling both would make the design self-contradictory, so the row's thrust is skipped and reported."""
    from launch_vehicle.validation import validate_spec
    spec, notes = _design_with_engine("RL10B-2")
    skipped = {s["field"] for n in notes for s in n["skipped"]}
    assert "thrust_vac_per_engine_N" in skipped
    assert spec.stages[1].engine.thrust_vac_per_engine_N is None
    assert "ENGDBSKIP" in {i.code for i in validate_spec(spec)}


def test_a_field_the_row_does_not_have_is_reported_as_missing():
    from launch_vehicle.validation import validate_spec
    spec, notes = _design_with_engine("RL10B-2")
    assert "isp_sl_s" in [m for n in notes for m in n["missing"]]
    assert "ENGDBMISS" in {i.code for i in validate_spec(spec)}


def test_an_explicit_value_beats_the_database_row():
    """A database entry is a default, never an override: the designer's own number must win."""
    spec, _ = _design_with_engine("RL10B-2", {"isp_vac_s": 300.0})
    assert spec.stages[1].engine.isp_vac_s == 300.0


def test_a_filled_field_is_recorded_in_the_input_register_with_the_row_as_its_source():
    spec, _ = _design_with_engine("RL10B-2")
    filled = [r for r in spec.inputs_register
              if r["path"].startswith("stages.1.engine.") and "engine database" in (r["source"] or "")]
    assert filled, "fields taken from the database must say so in the input register"
    assert all(r["provenance"] == "reference" for r in filled)
    assert any("RL10" in (r["source"] or "") for r in filled)


def test_an_unknown_engine_name_in_a_design_is_refused_with_a_clear_message():
    with pytest.raises((db.EngineDBError, ValueError)) as ex:
        _design_with_engine("No Such Engine 9000")
    assert "No Such Engine 9000" in str(ex.value)


def test_a_liquid_row_referenced_as_a_solid_motor_is_refused():
    design, meta, reg = load_yaml_annotated(DESIGN)
    design["stages"][1]["motor"] = {"from_database": "RD-180"}
    with pytest.raises(db.EngineDBError) as ex:
        db.expand_design(design, reg)
    assert "liquid" in str(ex.value)


def test_a_vehicle_using_a_real_engine_still_sizes_and_the_row_moves_the_answer():
    """Take the design's own Isp out of the way so the row's value is the one flown, and check it lands."""
    from launch_vehicle.convergence import size_vehicle
    spec, _ = _design_with_engine("RL10B-2", {"isp_vac_s": None, "isp_effective_mode": "vacuum"})
    res = size_vehicle(spec)
    assert res.converged
    assert res.stages[1].isp_eff_s == pytest.approx(db.find("RL10B-2")["isp_vac_s"], rel=1e-9)


# ---------------------------------------------------- R20: measuring the engine-mass MER, not trusting it
def test_the_engine_mass_mer_is_measured_against_every_engine_that_publishes_a_mass():
    """The book's Table 8.9 relation, run against real hardware instead of assumed to be right."""
    from launch_vehicle import engine_db
    d = engine_db.mer_check()
    assert d["n"] >= 10, f"only {d['n']} engines carry both a mass and the MER's inputs"
    for r in d["rows"]:
        assert r["published_kg"] > 0 and r["mer_kg"] > 0
        assert r["thrust_source"] in ("published",) or "derived" in r["thrust_source"]
    # the relation is not biased so much as imprecise: a small mean, a large spread
    assert abs(d["mean"]) < 0.20, f"mean error {100*d['mean']:+.0f}% would be a bias worth correcting"
    assert d["mean_abs"] > 0.25, "if the MER were this good on real engines, nothing here would be needed"


def test_the_relation_is_biased_low_not_merely_scattered():
    """R20's outcome once the sample grew from 10 engines to 16: a systematic offset, not noise.

    At 10 engines the mean was -7 % and the verdict was SCATTERED. Adding the six engines the new check
    cases needed turned it into a bias: 14 of 16 come out light with a median of -24 %. That is the kind of
    finding a small sample hides, which is why the sample is asserted here too.
    """
    from launch_vehicle import engine_db
    d = engine_db.mer_check()
    assert d["n"] >= 16, f"only {d['n']} engines; the bias is not visible on a smaller sample"
    assert "BIASED LOW" in d["verdict"], d["verdict"]
    assert d["median"] < -0.15, f"median error {100*d['median']:+.0f}%"
    assert d["n_light"] >= 0.75 * d["n"], "a bias means most engines err the same way"
    assert abs(d["trend_large_minus_small"]) < d["sd"], "the offset is not a size effect"


def test_the_correction_factor_helps_the_typical_engine_and_hurts_the_outliers():
    """Why mer_calibrated is opt-in rather than the default: it is a trade, not a free improvement."""
    from launch_vehicle import engine_db
    d = engine_db.mer_check()
    k = d["calibration_factor"]
    assert 1.1 < k < 1.4, f"factor {k:.3f}"
    assert abs(d["calibrated"]["median"]) < abs(d["median"]), "the typical engine must get better"
    assert d["calibrated"]["sd"] > d["sd"], (
        "and the spread must get worse - a single factor cannot fix one-sided outliers, which is the whole "
        "reason this is not applied by default")
    rows = {r["engine"]: r for r in d["rows"]}
    merlin = rows["Merlin 1D"]
    assert (k * merlin["mer_kg"] - merlin["published_kg"]) / merlin["published_kg"] > merlin["error"], \
        "the Merlin 1D is already over-predicted; scaling up makes it worse"


def test_the_calibrated_method_is_selectable_and_actually_changes_the_vehicle():
    from launch_vehicle.config_io import load_design
    from launch_vehicle.convergence import size_vehicle
    from launch_vehicle.validation import ENGINE_MASS_METHODS
    assert set(ENGINE_MASS_METHODS) == {"mer", "mer_calibrated", "user"}
    book = size_vehicle(load_design(DESIGN, ASSUMP))
    cal = size_vehicle(load_design(DESIGN, ASSUMP, {"stages.0.engine.mass_method": "mer_calibrated",
                                                    "stages.1.engine.mass_method": "mer_calibrated"}))
    assert cal.glom_kg > book.glom_kg, "a heavier engine must give a heavier vehicle"
    assert cal.stages[0].components["Engines"] > book.stages[0].components["Engines"]
    assert any(i.code == "ENGCAL" for i in cal.issues), "the user must be told the relation was scaled"


def test_the_gui_offers_the_calibrated_engine_method():
    import yaml
    from launch_vehicle import gui_meta as M
    from launch_vehicle.config_io import _Loader
    from launch_vehicle.validation import ENGINE_MASS_METHODS
    with open(ASSUMP, encoding="utf-8") as fh:
        a = yaml.load(fh, Loader=_Loader)
    offered = {v for v, _ in M.choices_for("stages.0.engine.mass_method", M.library_choices(a))}
    assert offered == set(ENGINE_MASS_METHODS), f"GUI and validator disagree: {offered}"


def test_the_measured_scatter_is_what_the_uncertainty_study_uses():
    """The 1-sigma in the assumptions file must be the measured number, not an independent guess."""
    import yaml
    from launch_vehicle import engine_db
    from launch_vehicle.config_io import _Loader
    with open(ASSUMP, encoding="utf-8") as fh:
        a = yaml.load(fh, Loader=_Loader)
    declared = a["mer_scatter"]["engine_mass"]
    assert declared["t"] == "reference", "a measured figure is not an assumption"
    d = engine_db.mer_check()
    assert declared["v"] == pytest.approx(d["sd"], abs=0.06), (
        f"the file says {declared['v']}, the measurement says {d['sd']:.2f}")


def test_the_two_outliers_are_the_engines_the_book_itself_explains():
    """The RS-68 is heavy for its thrust and the Merlin 1D is light; both are in the book's own text."""
    from launch_vehicle import engine_db
    rows = {r["engine"]: r for r in engine_db.mer_check()["rows"]}
    assert rows["RS-68"]["error"] < -0.4, "the ablative nozzle makes the RS-68 much heavier than the MER"
    assert rows["Merlin 1D"]["error"] > 0.5, "the Merlin 1D is lighter than any relation would guess"


def test_engines_without_the_inputs_are_listed_rather_than_dropped():
    from launch_vehicle import engine_db
    d = engine_db.mer_check()
    assert d["excluded"], "every engine cannot have a published mass"
    for x in d["excluded"]:
        assert x["engine"] and x["why"], x
    names = {r["engine"] for r in d["rows"]} | {x["engine"] for x in d["excluded"]}
    liquid = {e["name"] for e in engine_db.entries() if e.get("kind", "liquid") != "solid"}
    assert names == liquid, "every liquid engine must be either measured or explained"
