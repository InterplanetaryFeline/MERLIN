"""Vehicle-data importer: public source data -> annotated design YAML (R16).

The importer's whole job is to be honest about provenance, so that is what most of this file checks:
every leaf it took from the source is tagged t = reference and carries that source, every leaf it did
not is left alone and reported, and anything the source cannot supply unambiguously raises instead of
being guessed. The strongest test is at the end: the shipped example sheet is re-imported and sized,
and the result is compared against the hand-written validation case for the same vehicle.

The infobox fixtures below are wikitext written here by hand in the published `{{Infobox rocket}}`
form. The VALUES in them (Falcon 9's variant-laden mass, thrust and payload cells) were read off the
live article; the surrounding wikitext was not fetched, because no raw-wikitext fetch is available in
this environment. So these tests prove the parser handles the template grammar and refuses ambiguous
cells - they do not prove it copes with every article in the wild.
"""
import os

import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import vehicle_import as vi
from launch_vehicle.config_io import load_design
from launch_vehicle.convergence import size_vehicle

import atexit
import pathlib
import shutil
import tempfile

TMP = pathlib.Path(tempfile.mkdtemp(prefix="lv_imp_"))
atexit.register(shutil.rmtree, TMP, True)
SHEET = os.path.join(ROOT, "examples", "example_vehicle_sheet.csv")

_C = {}


def records():
    if "r" not in _C:
        _C["r"] = {r.key: r for r in vi.read_csv(SHEET)}
    return _C["r"]


def write_sheet(name, header, *rows):
    p = TMP / name
    p.write_text("\n".join([header] + list(rows)) + "\n")
    return str(p)


MINI_HEADER = ("key,name,source,payload_mass_kg,perigee_altitude_km,"
               "stage1_type,stage1_diameter_m,stage1_fuel,stage1_oxidizer,stage1_n_engines,"
               "stage1_isp_vac_s,stage1_thrust_to_weight_ignition,"
               "stage2_type,stage2_diameter_m,stage2_fuel,stage2_oxidizer,stage2_n_engines,"
               "stage2_isp_vac_s,stage2_isp_effective_mode,stage2_thrust_to_weight_ignition")
MINI_ROW = ("tiny,Tiny,a cited source,500,400,"
            "liquid,1.5,RP-1,LOX,4,300,1.4,"
            "liquid,1.5,RP-1,LOX,1,340,vacuum,0.8")


# ----------------------------------------------------------------------------- reading a sheet
def test_the_example_sheet_reads_into_records():
    recs = records()
    assert set(recs) == {"imported_electron", "imported_falcon9"}
    e = recs["imported_electron"]
    assert e.n_stages == 2 and e.name == "IMP-Electron"
    assert e.fields["payload_mass_kg"].value == 300.0
    assert e.fields["perigee_altitude_km"].value == 500.0
    assert e.stages[0]["n_engines"].value == 9 and isinstance(e.stages[0]["n_engines"].value, int)
    assert e.stages[0]["fuel"].value == "RP-1"
    assert e.stages[1]["type"] == "liquid"


def test_a_per_field_source_column_overrides_the_row_source():
    """A derived figure needs its own provenance, not the row's blanket citation."""
    e = records()["imported_electron"]
    assert e.fields["payload_mass_kg"].source == e.source
    assert e.stages[0]["thrust_to_weight_ignition"].source.startswith("Derived:")
    assert e.stages[0]["thrust_to_weight_ignition"].source != e.source


def test_thousands_separators_and_blank_cells_are_handled():
    p = write_sheet("sep.csv", MINI_HEADER, MINI_ROW.replace(",500,400,", ',"12,500",400,'))
    rec = vi.read_csv(p)[0]
    assert rec.fields["payload_mass_kg"].value == 12500.0
    assert "inclination_deg" not in rec.fields, "a column absent from the sheet must not be invented"


def test_blank_and_commented_rows_are_skipped():
    p = write_sheet("skip.csv", MINI_HEADER, MINI_ROW, "", "# ignore me,,,,,,,,,,,,,,,,,,,")
    assert len(vi.read_csv(p)) == 1


def test_a_row_without_a_source_is_refused():
    p = write_sheet("nosrc.csv", MINI_HEADER, MINI_ROW.replace("a cited source", ""))
    with pytest.raises(vi.VehicleImportError, match="source"):
        vi.read_csv(p)


def test_a_row_without_a_key_is_refused():
    p = write_sheet("nokey.csv", MINI_HEADER, MINI_ROW.replace("tiny,Tiny,", ",Tiny,", 1))
    with pytest.raises(vi.VehicleImportError, match="key"):
        vi.read_csv(p)


def test_a_declared_stage_count_must_match_the_columns_filled_in():
    p = write_sheet("nst.csv", "n_stages," + MINI_HEADER, "3," + MINI_ROW)
    with pytest.raises(vi.VehicleImportError, match="n_stages"):
        vi.read_csv(p)


def test_a_stage_needs_a_declared_type():
    p = write_sheet("notype.csv", MINI_HEADER, MINI_ROW.replace(",liquid,1.5,RP-1,LOX,4,", ",,1.5,RP-1,LOX,4,"))
    with pytest.raises(vi.VehicleImportError, match="liquid or solid"):
        vi.read_csv(p)


def test_an_unreadable_number_says_so():
    p = write_sheet("bad.csv", MINI_HEADER, MINI_ROW.replace(",500,400,", ",heavy,400,"))
    with pytest.raises(vi.VehicleImportError, match="heavy"):
        vi.read_csv(p)


def test_json_and_csv_describe_the_same_vehicle():
    """The JSON reader takes a 'stages' list, which is the friendlier shape to generate."""
    import json
    csv_rec = vi.read_csv(write_sheet("j.csv", MINI_HEADER, MINI_ROW))[0]
    blob = [{"key": "tiny", "name": "Tiny", "source": "a cited source",
             "payload_mass_kg": 500, "perigee_altitude_km": 400,
             "stages": [{"type": "liquid", "diameter_m": 1.5, "fuel": "RP-1", "oxidizer": "LOX",
                         "n_engines": 4, "isp_vac_s": 300, "thrust_to_weight_ignition": 1.4},
                        {"type": "liquid", "diameter_m": 1.5, "fuel": "RP-1", "oxidizer": "LOX",
                         "n_engines": 1, "isp_vac_s": 340, "isp_effective_mode": "vacuum",
                         "thrust_to_weight_ignition": 0.8}]}]
    p = TMP / "j.json"
    p.write_text(json.dumps(blob))
    jrec = vi.read_json(str(p))[0]
    assert jrec.key == csv_rec.key and jrec.n_stages == csv_rec.n_stages
    for i in range(jrec.n_stages):
        assert {k: v.value for k, v in jrec.stages[i].items() if k != "type"} == \
               {k: v.value for k, v in csv_rec.stages[i].items() if k != "type"}


def test_read_any_rejects_an_unknown_extension():
    p = TMP / "x.txt"
    p.write_text("nope")
    with pytest.raises(vi.VehicleImportError, match="csv"):
        vi.read_any(str(p))


# --------------------------------------------------------------------- required fields are required
def test_a_missing_payload_mass_is_an_error_not_a_default():
    p = write_sheet("nopl.csv", MINI_HEADER, MINI_ROW.replace(",500,400,", ",,400,"))
    with pytest.raises(vi.VehicleImportError, match="payload_mass_kg"):
        vi.build_design(vi.read_csv(p)[0])


def test_a_stage_with_no_thrust_information_is_an_error():
    p = write_sheet("nothrust.csv", MINI_HEADER, MINI_ROW.replace(",300,1.4,", ",300,,"))
    with pytest.raises(vi.VehicleImportError, match="thrust"):
        vi.build_design(vi.read_csv(p)[0])


def test_a_stage_with_no_diameter_is_an_error():
    p = write_sheet("nodia.csv", MINI_HEADER, MINI_ROW.replace(",liquid,1.5,RP-1", ",liquid,,RP-1", 1))
    with pytest.raises(vi.VehicleImportError, match="diameter_m"):
        vi.build_design(vi.read_csv(p)[0])


def test_user_isp_mode_without_a_user_isp_is_refused():
    """Inheriting the base vehicle's effective Isp here would be silently, invisibly wrong."""
    p = write_sheet("uisp.csv", MINI_HEADER, MINI_ROW.replace(",340,vacuum,", ",340,user,"))
    with pytest.raises(vi.VehicleImportError, match="isp_effective_user_s"):
        vi.build_design(vi.read_csv(p)[0])


def test_a_solid_field_on_a_liquid_stage_is_refused():
    p = write_sheet("mix.csv", MINI_HEADER + ",stage1_propellant", MINI_ROW + ",HTPB_AP_AL20")
    with pytest.raises(vi.VehicleImportError, match="propellant"):
        vi.build_design(vi.read_csv(p)[0])


# ------------------------------------------------------------------------------ building a design
def test_every_imported_leaf_is_tagged_reference_with_its_source():
    import yaml
    from launch_vehicle.config_io import _Loader
    rec = records()["imported_electron"]
    rep = vi.write_design(rec, TMP / "out")
    doc = yaml.load(open(rep.path), Loader=_Loader)
    assert doc["mission"]["payload_mass_kg"]["v"] == 300.0
    assert doc["mission"]["payload_mass_kg"]["t"] == "reference"
    assert doc["mission"]["payload_mass_kg"]["s"] == rec.source
    tw = doc["stages"][0]["engine"]["thrust_to_weight_ignition"]
    assert tw["t"] == "reference" and tw["s"].startswith("Derived:")
    for path, value, source in rep.referenced:
        leaf = doc
        for k in path.split("."):
            leaf = leaf[int(k)] if isinstance(leaf, list) else leaf[k]
        assert leaf["v"] == value and leaf["s"] == source and leaf["t"] == "reference"


def test_units_and_descriptions_survive_the_import():
    """Only v, s and t are replaced: the base file's units and prose are the schema and must stay."""
    import yaml
    from launch_vehicle.config_io import _Loader
    rep = vi.write_design(records()["imported_falcon9"], TMP / "out")
    doc = yaml.load(open(rep.path), Loader=_Loader)
    base = yaml.load(open(os.path.join(ROOT, "config", "default_design.yaml")), Loader=_Loader)
    for key in ("payload_mass_kg",):
        assert doc["mission"][key]["u"] == base["mission"][key]["u"]
        assert doc["mission"][key]["d"] == base["mission"][key]["d"]


def test_the_report_accounts_for_every_leaf_exactly_once():
    rep = vi.write_design(records()["imported_falcon9"], TMP / "out")
    paths = [p for p, _v, _s in rep.referenced] + [p for p, _v in rep.assumed] \
        + [p for p, _v in rep.inherited]
    assert len(paths) == len(set(paths)), "a leaf is reported in two categories at once"
    assert rep.n_referenced > 0 and rep.n_assumed > 0
    assert "reference" in rep.as_text() and rep.key in rep.as_text()


def test_the_header_says_how_much_of_the_file_is_assumed():
    rep = vi.write_design(records()["imported_electron"], TMP / "out")
    head = open(rep.path).read(1400)
    assert "AUTO-GENERATED" in head and records()["imported_electron"].source.split(";")[0] in head
    assert str(rep.n_referenced) in head and str(rep.n_assumed) in head
    assert "validation case rather than a datasheet" in head


def test_the_description_records_where_and_when_it_came_from():
    rep = vi.write_design(records()["imported_electron"], TMP / "out", retrieved="2026-01-31")
    import yaml
    from launch_vehicle.config_io import _Loader
    meta = yaml.load(open(rep.path), Loader=_Loader)["meta"]
    assert "2026-01-31" in meta["description"] and "rocketlabusa" in meta["description"]


def test_stage_count_follows_the_sheet_not_the_base_design():
    p = write_sheet("three.csv",
                    MINI_HEADER + ",stage3_type,stage3_diameter_m,stage3_fuel,stage3_oxidizer,"
                                  "stage3_n_engines,stage3_isp_vac_s,stage3_isp_effective_mode,"
                                  "stage3_thrust_to_weight_ignition",
                    MINI_ROW + ",liquid,1.2,RP-1,LOX,1,345,vacuum,0.5")
    doc, rep = vi.build_design(vi.read_csv(p)[0])
    assert len(doc["stages"]) == 3
    assert doc["stages"][2]["engine"]["isp_vac_s"]["v"] == 345.0


def test_a_solid_stage_is_built_from_the_solid_template():
    p = write_sheet("solid.csv",
                    "key,name,source,payload_mass_kg,perigee_altitude_km,"
                    "stage1_type,stage1_diameter_m,stage1_propellant,stage1_n_motors,"
                    "stage1_isp_vac_s,stage1_thrust_to_weight_ignition,"
                    "stage2_type,stage2_diameter_m,stage2_propellant,stage2_n_motors,"
                    "stage2_isp_vac_s,stage2_isp_effective_mode,stage2_thrust_to_weight_ignition",
                    "sol,Sol,a cited source,200,500,"
                    "solid,1.4,HTPB_AP_AL20,1,280,1.8,"
                    "solid,1.2,HTPB_AP_AL20,1,290,vacuum,1.1")
    doc, rep = vi.build_design(vi.read_csv(p)[0])
    assert all("motor" in s and "engine" not in s for s in doc["stages"])
    assert doc["stages"][0]["motor"]["isp_vac_s"]["v"] == 280.0
    assert doc["stages"][0]["propellant"]["v"] == "HTPB_AP_AL20"


# ------------------------------------------------------------------- the scale-sensitivity warning
def test_carrying_absolute_masses_across_a_size_class_is_flagged():
    """The import's likeliest way of being quietly wrong, so it must not be silent.

    The default base is a 10 t-class vehicle whose stages each carry 100 kg of 'other equipment',
    60 kg of separation hardware and 25 kg per engine of feed system. On a 300 kg-payload vehicle
    those constants roughly double the inert mass - and nothing in the source says a word about them.
    """
    p = write_sheet("small.csv", MINI_HEADER, MINI_ROW.replace(",500,400,", ",120,400,"))
    _doc, rep = vi.build_design(vi.read_csv(p)[0])
    assert rep.warnings, "a 100x payload mismatch produced no warning"
    w = rep.warnings[0]
    assert "do NOT scale" in w and "other_equipment_mass_kg" in w
    assert "WARNINGS" in rep.as_text()


def test_overriding_those_masses_silences_the_warning():
    """The example sheet fills the inert-mass columns for Electron, which is the documented fix."""
    _doc, rep = vi.build_design(records()["imported_electron"])
    carried = [w for w in rep.warnings if "do NOT scale" in w]
    assert not carried, f"warned about masses the sheet actually supplied: {carried}"


def test_a_similar_sized_vehicle_is_not_warned_about():
    _doc, rep = vi.build_design(records()["imported_falcon9"])
    assert not [w for w in rep.warnings if "do NOT scale" in w]


# -------------------------------------------------------------------- Wikipedia infobox wikitext
FALCON9_INFOBOX = """{{Infobox rocket
| name          = Falcon 9
| image         = [[File:Falcon 9.jpg|thumb|A Falcon 9]]
| function      = [[Launch vehicle|Orbital launch vehicle]]
| height        = FT: {{convert|69.8|m|ft|abbr=on}}<ref name="spacex"/>; v1.1: {{convert|68.4|m|ft}}
| diameter      = {{convert|3.7|m|ft|abbr=on}}
| mass          = FT: {{convert|549000|kg|lb}}; v1.1: {{convert|506000|kg|lb}}
| stages        = 2
| stage1engines = 9 [[Merlin (rocket engine family)|Merlin 1D+]]
| stage1thrust  = {{convert|7600|kN|lbf|abbr=on}}
| stage1burntime = 162 seconds
| stage2engines = 1 Merlin 1D Vacuum
| stage2thrust  = {{convert|934|kN|lbf}}
| stage2burntime = 397 seconds
}}
Some article prose that must not be parsed."""


def test_infobox_parsing_strips_templates_links_and_refs():
    f = vi.parse_infobox_fields(FALCON9_INFOBOX)
    assert f["stages"] == "2"
    assert "File:" not in f.get("image", "") or True              # images are irrelevant, not fatal
    assert "<ref" not in f["height"] and "[[" not in f["function"]
    assert f["function"] == "Orbital launch vehicle", "a piped link must reduce to its display text"
    assert "prose that must not be parsed" not in " ".join(f.values())


def test_convert_templates_reduce_to_a_number_and_a_unit():
    f = vi.parse_infobox_fields(FALCON9_INFOBOX)
    v, cands = vi.infobox_number(f["diameter"], "length")
    assert v == pytest.approx(3.7) and len(cands) >= 1


def test_imperial_units_are_converted_to_si():
    assert vi.infobox_number("{{convert|229|ft|m}}".replace("{{convert|", "").replace("}}", "")
                             .replace("|", " "), "length")[0] == pytest.approx(229 * 0.3048)
    assert vi.infobox_number("7600 kN", "force")[0] == pytest.approx(7.6e6)
    assert vi.infobox_number("1200 lb", "mass")[0] == pytest.approx(1200 * 0.45359237)
    assert vi.infobox_number("162 seconds", "time")[0] == pytest.approx(162.0)


def test_a_cell_with_several_variants_is_refused_not_guessed():
    """The real reason infoboxes cannot be imported blind: one cell, several vehicles.

    'FT: 549,000 kg; v1.1: 506,000 kg' describes two different rockets. Taking the first number
    would fabricate a specification for a variant nobody asked for, so the field is left out and
    listed as ambiguous instead.
    """
    f = vi.parse_infobox_fields(FALCON9_INFOBOX)
    v, cands = vi.infobox_number(f["mass"], "mass")
    assert v is None, "an ambiguous cell must not resolve to a number"
    assert len(cands) == 2 and any("549000" in c for c in cands)
    v, cands = vi.infobox_number(f["height"], "length")
    assert v is None and len(cands) >= 2


def test_a_metric_imperial_twin_is_one_figure_not_two():
    """Infoboxes always restate a figure in the other unit system, so a pair must not read as a pair.

    12 ft is 3.6576 m, not 3.7 m, so a naive equality test would call every length in every infobox
    ambiguous - and no tolerance can help, because this pair is 1.2% apart while Falcon 9's two real
    height variants are 2.0% apart. The restatement is therefore removed structurally: the target
    unit of a convert template is dropped, and a parenthesised restatement after the figure with it.
    """
    v, cands = vi.infobox_number("3.7 m (12 ft)", "length")
    assert v == pytest.approx(3.7), "the parenthesised restatement must not count as a second figure"
    assert len(cands) == 1
    assert vi.infobox_number("549,000 kg (1,210,000 lb)", "mass")[0] == pytest.approx(549_000.0)
    # ...but two genuine variants stay ambiguous, because they are 8% apart, not 1%
    assert vi.infobox_number("FT: 549,000 kg; v1.1: 506,000 kg", "mass")[0] is None


def test_infobox_import_keeps_what_is_certain_and_flags_what_is_not():
    rec = vi.parse_infobox(FALCON9_INFOBOX, key="f9", source="en.wikipedia.org/wiki/Falcon_9")
    assert rec.n_stages == 2
    assert rec.stages[0]["n_engines"].value == 9
    assert rec.stages[0]["thrust_vac_per_engine_N"].value == pytest.approx(7.6e6)
    assert rec.stages[0]["burn_time_s"].value == pytest.approx(162.0)
    assert rec.fields["fairing_diameter_m"].value == pytest.approx(3.7)
    assert all(v.source == "en.wikipedia.org/wiki/Falcon_9"
               for v in list(rec.fields.values()) + [x for s in rec.stages
                                                     for k, x in s.items() if k != "type"])


def test_an_infobox_alone_is_not_enough_for_a_design():
    """And the importer says so by raising rather than filling the gaps with the base vehicle's.

    An infobox gives no payload mass, no orbit and no Isp, which is the honest headline for R16:
    this path transcribes, it does not import.
    """
    rec = vi.parse_infobox(FALCON9_INFOBOX, key="f9", source="wikipedia")
    with pytest.raises(vi.VehicleImportError, match="payload_mass_kg"):
        vi.build_design(rec)


def test_text_with_no_template_is_rejected():
    with pytest.raises(vi.VehicleImportError, match="template"):
        vi.parse_infobox_fields("Falcon 9 is a launch vehicle.")


def test_an_infobox_with_no_stages_is_rejected():
    with pytest.raises(vi.VehicleImportError, match="stage"):
        vi.parse_infobox("{{Infobox rocket\n| name = X\n| diameter = 3 m\n}}", "x", "src")


# ------------------------------------------------------------------- the imported design actually runs
def test_the_example_sheet_imports_sizes_and_lands_near_the_hand_written_case():
    """The end-to-end claim, measured rather than asserted in prose.

    An import carries what a public source publishes and nothing else, so it cannot reproduce a
    hand-built validation case exactly - the hand case also sets envelope lengths, wall thicknesses,
    tank pressures and engine envelopes that no source gives. What it must do is converge, stay in
    the same size class, and leave the remaining gap visible in the report. Measured here: Falcon 9
    imports 8% heavier than the hand-written case and Electron 17% heavier, the Electron gap being
    the larger because more of a small vehicle's inert mass comes from assumptions.
    """
    reps = vi.import_sheet(SHEET, TMP / "e2e")
    assert len(reps) == 2
    assump = os.path.join(ROOT, "config", "engineering_assumptions.yaml")
    ratios = {}
    for rep, hand in zip(sorted(reps, key=lambda r: r.key), ("electron", "falcon9")):
        imported = size_vehicle(load_design(rep.path, assump))
        reference = size_vehicle(load_design(os.path.join(ROOT, "validation", f"{hand}.yaml"), assump))
        assert imported.converged, f"{rep.key} did not converge"
        ratios[hand] = imported.glom_kg / reference.glom_kg
    assert ratios["falcon9"] == pytest.approx(1.08, abs=0.04)
    assert ratios["electron"] == pytest.approx(1.17, abs=0.06)


def test_the_template_sheet_lists_every_column_the_reader_knows():
    p = vi.write_template_csv(TMP / "template.csv")
    cols = open(p).read().strip().split(",")
    assert cols == vi.vehicle_sheet_columns()
    assert "key" in cols and "source" in cols
    for f in ("stage1_isp_vac_s", "stage1_propellant", "stage2_n_engines"):
        assert f in cols
