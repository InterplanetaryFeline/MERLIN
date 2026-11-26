"""Every error and warning takes the user to the input that fixes it.

A message that only says what is wrong leaves the user to find which of a few hundred inputs it means. The
owner's rule: every error points at the field to change. These tests make a new check that forgets its field
fail here rather than in front of a user.
"""
import ast
import glob
import os

import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import validation as V, orbit as O, delta_v as DV


def _calls(path, names):
    src = open(os.path.join(ROOT, path), encoding="utf-8").read()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Call):
            f = n.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if name in names:
                yield n, src


def test_every_input_check_names_its_field():
    missing = []
    for n, src in _calls("src/launch_vehicle/validation.py", {"E", "W"}):
        if not (n.args and isinstance(n.args[0], ast.Constant)):
            continue
        code = n.args[0].value
        named = any(k.arg == "field" for k in n.keywords) or len(n.args) >= 3
        if not named and code not in V._CODE_FIELD:
            missing.append(f"{code} (line {n.lineno})")
    assert not missing, "checks that name no input: " + ", ".join(missing)


def test_every_orbit_and_loss_model_error_names_its_field():
    for path in ("src/launch_vehicle/orbit.py", "src/launch_vehicle/delta_v.py"):
        for n, _src in _calls(path, {"OrbitError"}):
            if isinstance(n.func, ast.Name) and n.func.id == "OrbitError" and not n.args:
                continue
            assert any(k.arg == "field" for k in n.keywords), f"{path} line {n.lineno}: OrbitError without a field"
        src = open(os.path.join(ROOT, path), encoding="utf-8").read()
        assert "raise ValueError(" not in src, f"{path} raises a bare ValueError, which can name no field"


@pytest.mark.parametrize("name", ["electron", "vega", "falcon9", "saturn5", "pegasus_xl"])
def test_every_warning_after_sizing_names_its_field(name):
    res = size_vehicle(load_design(os.path.join(ROOT, "validation", f"{name}.yaml"), ASSUMP))
    loose = [f"{i.code}: {i.message[:60]}" for i in res.issues
             if i.level != "INFO" and not i.field and i.code not in V.NO_FIELD and i.code != "INPUT"]
    assert not loose, loose


@pytest.mark.parametrize("ov, field, fix", [
    ({"mission.orbit.type": "GEO_DIRECT"}, "mission.orbit.apogee_altitude_km", 35786.0),
    ({"mission.orbit.type": "GEO_DIRECT", "mission.orbit.apogee_altitude_km": 400.0}, "mission.orbit.apogee_altitude_km", 35786.0),
    ({"mission.orbit.type": "CUSTOM", "mission.orbit.apogee_altitude_km": 300.0}, "mission.orbit.apogee_altitude_km", None),
    ({"mission.orbit.inclination_deg": 10.0}, "mission.orbit.inclination_deg", 39.3),
])
def test_an_impossible_orbit_names_the_field_and_offers_the_fix(ov, field, fix):
    """A geostationary orbit at a 400 km apogee came back as a sentence with no field."""
    from launch_vehicle.convergence import SizingError
    with pytest.raises((O.OrbitError, SizingError)) as got:
        size_vehicle(load_design(os.path.join(ROOT, "validation", "electron.yaml"), ASSUMP, ov))
    ex = got.value
    assert ex.field == field
    assert ex.options and ex.options[0]["path"] == field
    assert ex.options[0]["value"] == (pytest.approx(fix) if fix is not None else None)


def test_the_apogee_manoeuvre_option_is_gone():
    """It added a GTO-to-GEO line nobody on a LEO mission needs, as one of the first things asked."""
    for p in glob.glob(os.path.join(ROOT, "validation", "*.yaml")) + glob.glob(os.path.join(ROOT, "examples", "*.yaml")) \
            + [os.path.join(ROOT, "config", "default_design.yaml")]:
        assert "report_apogee_maneuver" not in open(p, encoding="utf-8").read(), p
    for p in glob.glob(os.path.join(ROOT, "src", "launch_vehicle", "*.py")):
        assert "report_apogee_maneuver" not in open(p, encoding="utf-8").read(), p


def test_changing_the_orbit_type_sets_the_altitudes_that_follow_from_it():
    page = open(os.path.join(ROOT, "src", "launch_vehicle", "gui_static", "index.html"), encoding="utf-8").read()
    assert "function applyOrbitCascade(" in page and "applyOrbitCascade(it, raw" in page
    body = page.split("function applyOrbitCascade(")[1].split("\nfunction ")[0]
    assert 'set("apogee_altitude_km", 35786' in body and 'set("apogee_altitude_km", null' in body
