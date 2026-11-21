"""The facts the project states about itself must agree with each other."""
from __future__ import annotations
import csv
import os
import re

from launch_vehicle.method_register import REGISTER

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8", newline="") as fh:
        return fh.read()


def _version():
    return re.search(r'^version\s*=\s*"([^"]+)"', _read("pyproject.toml"), re.M).group(1)


def test_the_version_is_the_same_in_every_place_that_states_it():
    pkg = re.search(r'^__version__\s*=\s*"([^"]+)"', _read("src", "launch_vehicle", "__init__.py"), re.M).group(1)
    readme = re.search(r"\(v([0-9][^)]*)\)", _read("README.md").split("\n")[0]).group(1)
    cff = re.search(r"^version:\s*(\S+)", _read("CITATION.cff"), re.M).group(1)
    assert _version() == pkg == readme == cff, (
        f"version disagreement: pyproject {_version()}, package {pkg}, README {readme}, CITATION {cff}")


def test_the_changelog_covers_the_current_version():
    assert f"v{_version()}" in _read("docs", "CHANGELOG.md"), (
        f"the changelog has no entry for v{_version()}")


def test_the_licence_names_its_owner_and_keeps_its_credit_clause():
    text = _read("LICENSE")
    assert "<" not in text.split("Permission is hereby")[0], "a placeholder is left in the copyright line"
    assert "Permission is hereby granted" in text and 'must credit "MERLIN by ' in text
    assert "NOT a range-safety product" in text, "the safety disclaimer must stay in the licence"


def test_nothing_still_carries_a_placeholder_owner():
    for name in ("LICENSE", "CITATION.cff", "README.md"):
        assert "<COPYRIGHT HOLDER>" not in _read(name), f"{name} still has the placeholder"


def test_the_method_register_covers_every_method():
    """The docs and the LICENSE point at this file, and it is generated, so it can fall behind the code."""
    with open(os.path.join(ROOT, "outputs", "engineering_method_register.csv"), encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    assert len(rows) - 1 == len(REGISTER), "regenerate the register: it no longer matches method_register.py"


def test_the_release_page_is_made_from_this_versions_changelog_section():
    """The GitHub Release text is that version's section of docs/CHANGELOG.md (tools/release_notes.py). A version
    with no section would fail the release workflow after the tests had passed, so it fails here first."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("release_notes", os.path.join(ROOT, "tools", "release_notes.py"))
    rn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rn)
    import launch_vehicle
    with open(os.path.join(ROOT, "docs", "CHANGELOG.md"), encoding="utf-8") as fh:
        text = fh.read()
    body = rn.notes(launch_vehicle.__version__, text)
    assert f"MERLIN-{launch_vehicle.__version__}-windows.zip" in body
    assert len(rn.section(launch_vehicle.__version__, text)) > 200
    assert "What changed in v" not in body, "the next version's section leaked into this one"
    with open(os.path.join(ROOT, ".github", "workflows", "release.yml"), encoding="utf-8") as fh:
        wf = fh.read()
    assert "tools/release_notes.py" in wf and "--notes-file release_notes.md" in wf
