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


def _build_app():
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_app", os.path.join(ROOT, "tools", "build_app.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_app_lets_dotnet_load_its_own_downloaded_libraries():
    """v1.3.0 from a zip extracted with Explorer: every library was marked as downloaded and the window never opened."""
    import xml.etree.ElementTree as ET
    with tempfile.TemporaryDirectory() as tmp:
        path = _build_app().write_exe_config(tmp)
        assert os.path.basename(path) == "MERLIN.exe.config"
        assert ET.parse(path).find("runtime/loadFromRemoteSources").get("enabled") == "true"


def test_a_zip_without_that_setting_is_refused():
    b = _build_app()
    with tempfile.TemporaryDirectory() as tmp:
        app = os.path.join(tmp, "MERLIN")
        os.makedirs(app)
        with open(os.path.join(app, "MERLIN.exe"), "wb") as fh:
            fh.write(b"x")
        try:
            b.make_zip(app, os.path.join(tmp, "a.zip"))
            refused = False
        except RuntimeError:
            refused = True
        assert refused
        b.write_exe_config(app)
        assert os.path.exists(b.make_zip(app, os.path.join(tmp, "b.zip")))


def test_the_window_error_names_the_cause_it_has():
    blocked = RuntimeError("Failed to resolve Python.Runtime.Loader.Initialize from C:/x/Python.Runtime.dll")
    for installed in (True, False):
        t = desktop.window_error_text(blocked, installed, "m.log")
        assert "Unblock" in t and "WebView2" not in t and str(blocked) in t
    assert "WebView2" in desktop.window_error_text(RuntimeError("x"), False, "m.log")
    other = desktop.window_error_text(RuntimeError("something else"), True, "m.log")
    assert "WebView2" not in other and "Unblock" not in other and "something else" in other and "m.log" in other


def test_looking_for_webview2_never_raises():
    assert desktop.webview2_installed() in (True, False, None)


def test_the_app_has_its_own_icon():
    """A rocket in a wizard's hat, for an app called MERLIN, instead of Windows' default."""
    from PIL import Image
    static = os.path.join(ROOT, "src", "launch_vehicle", "gui_static")
    ico = Image.open(os.path.join(static, "merlin.ico"))
    assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= set(ico.info.get("sizes", set()))
    assert Image.open(os.path.join(static, "favicon.png")).size == (64, 64)
    src = open(os.path.join(ROOT, "tools", "build_app.py"), encoding="utf-8").read()
    assert '"--icon", icon' in src and "merlin.ico" in src
    page = open(os.path.join(static, "index.html"), encoding="utf-8").read()
    assert '<link rel="icon" type="image/png" href="/favicon.png">' in page
