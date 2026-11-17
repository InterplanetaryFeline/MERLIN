"""The desktop app's own plumbing: where it keeps its data, and how it starts without a console.

The window itself needs pywebview and a display, so it is checked by building and running the app
(tools/build_app.py), not here. No fixtures, so the offline runner can run this file too.
"""
from __future__ import annotations
import io
import os
import socket
import sys
import tempfile

from launch_vehicle import desktop, paths, webgui

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_from_source_the_data_folder_is_the_project_folder():
    assert os.path.samefile(paths.project_root(frozen=False), ROOT)
    assert os.path.samefile(webgui.ROOT, ROOT), "a module still works out its own root"


def test_the_packaged_app_keeps_its_data_beside_the_exe():
    exe = os.path.join(tempfile.gettempdir(), "MERLIN", "MERLIN.exe")
    assert paths.project_root(frozen=True, executable=exe, environ={}) == os.path.dirname(exe)


def test_merlin_home_points_the_app_at_another_data_folder():
    home = os.path.join(tempfile.gettempdir(), "elsewhere")
    assert paths.project_root(frozen=True, executable="x.exe", environ={"MERLIN_HOME": home}) == home


def test_no_module_works_out_its_own_root_any_more():
    """Seven modules once did this independently. In the packaged app that path points inside the runtime."""
    old = "os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))"
    pkg = os.path.join(ROOT, "src", "launch_vehicle")
    offenders = []
    for name in sorted(os.listdir(pkg)):
        if name.endswith(".py") and name != "paths.py":
            with open(os.path.join(pkg, name), encoding="utf-8") as fh:
                if old in fh.read():
                    offenders.append(name)
    assert not offenders, "use launch_vehicle.paths.ROOT instead: " + ", ".join(offenders)


def test_the_port_it_picks_is_free():
    port = desktop.free_port()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", port))


def test_a_windowed_app_with_no_console_logs_to_a_file_instead_of_failing():
    saved = sys.stdout, sys.stderr
    with tempfile.TemporaryDirectory() as tmp:
        log_path = os.path.join(tmp, "logs", "merlin.log")
        try:
            sys.stdout = sys.stderr = None
            log = desktop.redirect_missing_streams(log_path)
            print("engine message")
            print("engine warning", file=sys.stderr)
            log.close()
        finally:
            sys.stdout, sys.stderr = saved
        with open(log_path, encoding="utf-8") as fh:
            text = fh.read()
    assert "engine message" in text and "engine warning" in text


def test_streams_that_exist_are_left_alone():
    saved = sys.stdout, sys.stderr
    try:
        sys.stdout = sys.stderr = io.StringIO()
        assert desktop.redirect_missing_streams(os.path.join(tempfile.gettempdir(), "unused.log")) is None
    finally:
        sys.stdout, sys.stderr = saved
