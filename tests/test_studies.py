"""Declared trade studies and multi-design comparison (roadmap R17 and R14).

Neither is a method out of the book, so there is nothing published to check against. What there is to test is
that the driver does what it says: every declared case is run, failures stay visible, an unknown parameter path
is refused, and the outputs are the sizing loop's own rather than anything recomputed here.
"""
import math
import os
import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import studies as S

DESIGN = "config/default_design.yaml"
ASSUMP = "config/engineering_assumptions.yaml"
_C = {}


def small_grid():
    if "g" not in _C:
        _C["g"] = S.run_trade_study(dict(trade_study=dict(
            name="t", design=DESIGN, assumptions=ASSUMP, mode="grid",
            sweep=[dict(path="stages.0.diameter_m", values=[3.8, 4.0]),
                   dict(path="stages.0.mixture_ratio_OF", values=[2.4, 2.6])])))
    return _C["g"]


# ====================================================================== case generation
def test_a_grid_runs_every_combination():
    st = small_grid()
    assert len(st["cases"]) == 4
    seen = {(c.parameters["stages.0.diameter_m"], c.parameters["stages.0.mixture_ratio_OF"])
            for c in st["cases"]}
    assert seen == {(3.8, 2.4), (3.8, 2.6), (4.0, 2.4), (4.0, 2.6)}


def test_one_at_a_time_runs_the_baseline_plus_each_value_alone():
    ov = S._cases_from_sweep([dict(path="a.b", values=[1, 2]), dict(path="c.d", values=[9])],
                             "one_at_a_time")
    assert len(ov) == 4, "baseline + 2 + 1"
    assert ov[0][0] == {}, "the first case is the untouched baseline"
    assert all(len(o) == 1 for o, _p in ov[1:]), "every other case moves exactly one parameter"


def test_an_unknown_mode_is_refused():
    with pytest.raises(ValueError, match="unknown trade-study mode"):
        S._cases_from_sweep([dict(path="a", values=[1])], "shotgun")


def test_a_sweep_entry_without_values_is_refused():
    for bad in (dict(path="stages.0.diameter_m"), dict(path="stages.0.diameter_m", values=[]),
                dict(values=[1, 2])):
        with pytest.raises(ValueError):
            S.run_trade_study(dict(trade_study=dict(design=DESIGN, assumptions=ASSUMP, sweep=[bad])))


def test_a_study_without_a_base_design_is_refused():
    with pytest.raises(ValueError, match="must name a base design"):
        S.run_trade_study(dict(trade_study=dict(sweep=[])))


def test_an_unknown_parameter_path_fails_the_case_rather_than_the_run():
    """deep_set refuses an unknown key; the driver must record that as a failed case and carry on, so a typo
    in one line of a sweep does not throw away the other nine results."""
    st = S.run_trade_study(dict(trade_study=dict(
        design=DESIGN, assumptions=ASSUMP,
        sweep=[dict(path="stages.0.no_such_parameter", values=[1.0, 2.0])])))
    assert len(st["cases"]) == 2
    assert all(not c.ok for c in st["cases"])
    assert all("unknown parameter path" in c.error for c in st["cases"])


# ====================================================================== results
def test_the_outputs_are_the_sizing_loops_own():
    st = small_grid()
    for c in st["cases"]:
        if not c.ok:
            continue
        assert c.outputs["glom_kg"] == pytest.approx(c.result.glom_kg, rel=1e-12)
        assert c.outputs["length_m"] == pytest.approx(c.result.geometry.total_length, rel=1e-12)
        assert c.outputs["payload_fraction"] == pytest.approx(
            c.result.payload_mass_kg / c.result.glom_kg, rel=1e-12)


def test_the_swept_parameter_actually_moved_the_vehicle():
    """A sweep that changed nothing would be the worst possible silent failure."""
    st = small_grid()
    lengths = {round(c.outputs["length_m"], 4) for c in st["cases"] if c.ok}
    assert len(lengths) > 1


def test_failed_cases_stay_in_the_table():
    """A 3.6 m stage 1 cannot fit its engines, so it raises ENGFIT. The row must survive into the results."""
    st = S.run_trade_study(dict(trade_study=dict(
        design=DESIGN, assumptions=ASSUMP,
        sweep=[dict(path="stages.0.diameter_m", values=[3.6, 4.0])])))
    assert len(st["cases"]) == 2
    bad = [c for c in st["cases"] if not c.ok]
    assert len(bad) == 1 and bad[0].parameters["stages.0.diameter_m"] == 3.6
    assert "ENGFIT" in bad[0].worst_issue
    header, rows = S.to_rows(st)
    assert len(rows) == 2, "both rows are tabulated"
    assert any("ENGFIT" in str(r[-1]) for r in rows)
    assert any("kept in the table rather than dropped" in n for n in st["notes"])


def test_the_notes_name_the_lightest_and_heaviest_and_caveat_the_spread():
    st = small_grid()
    joined = " ".join(st["notes"])
    assert "Lightest" in joined and "Heaviest" in joined
    assert "uncertainty in the mass relationships" in joined, "a 0.4 % spread needs that caveat"


# ====================================================================== tabulation and output
def test_the_table_has_a_column_per_swept_parameter_then_the_outputs():
    st = small_grid()
    header, rows = S.to_rows(st, ["glom_kg", "length_m"])
    assert header[0] == "Case"
    assert header[1:3] == ["diameter_m", "mixture_ratio_OF"]
    assert header[3:5] == ["GLOM [kg]", "Length [m]"]
    assert header[-1] == "Status"
    assert all(len(r) == len(header) for r in rows)


def test_csv_and_html_are_written_and_readable(tmp_path="/tmp/claude-0/-home-claude/400c4472-2da2-506c-8942-6c3a7b33c072/scratchpad/st"):
    os.makedirs(tmp_path, exist_ok=True)
    st = small_grid()
    csvp = S.write_csv(st, os.path.join(tmp_path, "t.csv"))
    body = open(csvp, encoding="utf-8").read()
    assert body.count("\n") >= 5, "a header and four cases"
    assert "GLOM [kg]" in body
    htmlp = S.write_html(st, os.path.join(tmp_path, "t.html"))
    page = open(htmlp, encoding="utf-8").read()
    assert "<table" in page and "Lightest" in page
    assert "tens of per cent" in page, "the page must carry the uncertainty caveat"


# ====================================================================== R14: comparison
def test_comparing_designs_runs_each_as_declared():
    st = S.compare_designs([DESIGN, "examples/example_3stage_leo.yaml"], ASSUMP)
    assert st["kind"] == "comparison"
    assert len(st["cases"]) == 2
    assert [c.label for c in st["cases"]] == ["default_design", "example_3stage_leo"]
    assert all(c.ok for c in st["cases"])
    assert st["cases"][0].outputs["glom_kg"] != st["cases"][1].outputs["glom_kg"]


def test_the_comparison_caveats_payload_fraction_across_different_missions():
    """Comparing payload fraction between vehicles doing different missions is the easiest way to draw a wrong
    conclusion from this table, so the notes have to say so."""
    st = S.compare_designs([DESIGN, "examples/example_3stage_leo.yaml"], ASSUMP)
    joined = " ".join(st["notes"])
    assert "same mission" in joined
    assert "their missions may differ" in joined


def test_warnings_are_surfaced_in_the_comparison():
    st = S.compare_designs([DESIGN], ASSUMP)
    assert st["cases"][0].worst_issue.startswith("WARNING")
    assert "read each design's own report" in " ".join(st["notes"]).lower()


def test_a_missing_design_file_fails_its_own_row_only():
    st = S.compare_designs([DESIGN, "examples/no_such_design.yaml"], ASSUMP)
    assert st["cases"][0].ok
    assert not st["cases"][1].ok and st["cases"][1].error


def test_table_cells_are_readable_at_every_magnitude():
    """A lift-off mass is the number a comparison is read for, so it must not render in exponent form.

    '{:,.4g}' silently drops the thousands separator once %g switches to an exponent, turning 92,975 kg into
    '9.298e+04'. The formatter picks by magnitude instead.
    """
    from launch_vehicle.studies import _cell
    assert _cell(92975.4) == "92,975"
    assert _cell(410003.0) == "410,003"
    assert _cell(9378.3) == "9,378"
    assert _cell(34.264) == "34.26"
    assert _cell(1.35) == "1.35"
    assert _cell(0.021511) == "0.02151"
    assert _cell(-1234.5) == "-1,234"
    assert "e+" not in _cell(1.2345e7)


def test_the_written_comparison_page_shows_masses_in_full():
    import os
    import re
    import tempfile
    from launch_vehicle import studies as S
    base = os.path.join(ROOT, "config", "default_design.yaml")
    study = S.compare_designs([base, base], os.path.join(ROOT, "config", "engineering_assumptions.yaml"),
                              labels=["a", "b"])
    with tempfile.TemporaryDirectory() as d:
        page = S.write_html(study, os.path.join(d, "c.html"), None)
        text = open(page).read()
    assert re.search(r"\d{3},\d{3}", text), "the lift-off mass is not written with thousands separators"
    assert not re.search(r"\d\.\d+e\+0\d", text), "a value rendered in exponent form"


def test_a_design_can_carry_its_own_sweep_declaration_and_still_size():
    """A `trade_study:` block is a study DECLARATION in plain YAML, not an input to the vehicle. The design
    loader used to walk it like any input and refuse the file with "trade_study.name is an undocumented bare
    value" - an error about a field that is not a field - so a sweep could not live in the design it sweeps.
    """
    import os
    import tempfile
    import yaml
    from launch_vehicle.config_io import _Loader, load_design
    from launch_vehicle.convergence import size_vehicle

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "config", "default_design.yaml"), encoding="utf-8") as fh:
        doc = yaml.load(fh, Loader=_Loader)
    with open(os.path.join(root, "examples", "example_trade_study.yaml"), encoding="utf-8") as fh:
        doc["trade_study"] = yaml.load(fh, Loader=_Loader)["trade_study"]

    fh = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8")
    yaml.safe_dump(doc, fh, sort_keys=False)
    fh.close()
    try:
        result = size_vehicle(load_design(fh.name, os.path.join(root, "config",
                                                                "engineering_assumptions.yaml")))
        assert result.glom_kg > 0
    finally:
        os.unlink(fh.name)


def test_a_study_only_file_is_not_offered_as_a_design():
    """`examples/example_trade_study.yaml` has no vehicle in it at all - it names the design it sweeps. It
    must not appear in the Open dialog, or a user would open it and press Size on nothing."""
    from launch_vehicle import webgui
    paths = {d["path"] for d in webgui.list_designs()}
    assert "examples/example_trade_study.yaml" not in paths
    assert any(f["path"] == "examples/example_trade_study.yaml" for f in webgui.trade_study_files()), \
        "it should still be offered as a sweep"
