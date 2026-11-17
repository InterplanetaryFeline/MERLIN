"""Files must come out the same on every platform.

Text mode with no arguments means CRLF and the ANSI code page on Windows. That once made the KML writer declare
UTF-8 in its header while writing cp1252, and it stayed invisible while the suite only ran on Linux.

No fixtures here: tools/run_tests.py calls every test with no arguments, and both runners must stay green.
"""
from __future__ import annotations
import ast
import os
import tempfile
from types import SimpleNamespace

import pytest

from launch_vehicle import cad_export, hazard, vehicle_import

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _python_files():
    for top in ("src/launch_vehicle", "tools"):
        for name in sorted(os.listdir(os.path.join(ROOT, top))):
            if name.endswith(".py"):
                yield os.path.join(top, name)


def _text_opens_without_encoding(source: str):
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open"):
            continue
        keywords = {k.arg: k.value for k in node.keywords}
        mode = node.args[1] if len(node.args) > 1 else keywords.get("mode")
        if isinstance(mode, ast.Constant) and "b" in str(mode.value):
            continue
        if "encoding" not in keywords:
            yield node.lineno


def test_every_text_mode_open_names_its_encoding():
    bad = []
    for rel in _python_files():
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            bad += [f"{rel}:{line}" for line in _text_opens_without_encoding(fh.read())]
    assert not bad, "text-mode open() with no encoding, so it depends on the platform: " + ", ".join(bad)


def test_the_scan_recognises_what_it_is_looking_for():
    assert list(_text_opens_without_encoding('open(p, "w")')) == [1]
    assert not list(_text_opens_without_encoding('open(p, "rb")'))
    assert not list(_text_opens_without_encoding('open(p, encoding="utf-8")'))


def test_an_exported_mesh_has_unix_line_endings_and_survives_a_non_ascii_name():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "v.obj")
        mesh = SimpleNamespace(name="stopień", vertices=[(0.0, 0.0, 0.0)], faces=[])
        cad_export.write_obj([mesh], path)
        with open(path, "rb") as fh:
            body = fh.read()
    assert b"\r\n" not in body
    assert "stopień" in body.decode("utf-8")


def test_kml_really_is_the_utf8_its_header_declares():
    text = '<?xml version="1.0" encoding="UTF-8"?>\n<kml>zrzut łącznika</kml>\n'
    original = hazard.to_kml
    hazard.to_kml = lambda a: text
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "z.kml")
            hazard.write_kml({}, path)
            with open(path, "rb") as fh:
                body = fh.read()
    finally:
        hazard.to_kml = original
    assert body == text.encode("utf-8")


def test_a_csv_that_is_not_utf8_is_refused_rather_than_garbled():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "sheet.csv")
        with open(path, "wb") as fh:
            fh.write("key,source\nx,caf\xe9\n".encode("latin-1"))
        with pytest.raises(vehicle_import.VehicleImportError):
            vehicle_import.read_csv(path)
