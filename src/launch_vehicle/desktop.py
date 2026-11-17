"""MERLIN as a desktop app: the same GUI in its own window, with no browser and no Python to install.

    python -m launch_vehicle.desktop        # from source, needs `pip install pywebview`
    MERLIN.exe                              # the packaged app; see tools/build_app.py

It runs the GUI's local server on a free loopback port and shows it in a native window through pywebview, which
uses Microsoft Edge WebView2 on Windows. Nothing is reachable from outside this machine. Closing the window
stops the server.
"""
from __future__ import annotations
import ctypes
import os
import socket
import sys
import threading
import time
import urllib.request

from . import __version__
from .paths import ROOT


def free_port(host: str = "127.0.0.1") -> int:
    """A port nothing is listening on, so two copies of the app can run at once."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def redirect_missing_streams(log_path: str):
    """A windowed app has no console: sys.stdout and sys.stderr are None, and printing to None fails.

    Anything the engine prints goes to a log file instead, which is also where a crash can be read afterwards.
    Returns the opened file, or None when both streams already exist.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return None
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    log = open(log_path, "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = log
    if sys.stderr is None:
        sys.stderr = log
    return log


def wait_until_serving(url: str, timeout_s: float = 30.0) -> bool:
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except OSError:
            time.sleep(0.1)
    return False


def _message_box(text: str) -> None:
    if os.name == "nt":
        ctypes.windll.user32.MessageBoxW(None, text, "MERLIN", 0x10)
    else:
        print(text, file=sys.stderr)


def main() -> int:
    workdir = os.path.join(ROOT, "outputs", "gui")
    redirect_missing_streams(os.path.join(workdir, "merlin.log"))
    print(f"--- MERLIN {__version__} starting {time.strftime('%Y-%m-%d %H:%M:%S')}, data folder {ROOT}")

    try:
        import webview                                             # noqa: PLC0415 - optional dependency
    except ImportError:
        _message_box("The desktop window needs pywebview: pip install pywebview\n"
                     "Or use the browser version: python tools/gui.py")
        return 1

    from .webgui import serve                                       # noqa: PLC0415 - after the streams exist

    port = free_port()
    url = f"http://127.0.0.1:{port}/"
    threading.Thread(target=serve, kwargs=dict(port=port, open_browser=False, workdir=workdir),
                     daemon=True).start()
    if not wait_until_serving(url):
        _message_box(f"The MERLIN engine did not start. Details are in:\n{os.path.join(workdir, 'merlin.log')}")
        return 1

    webview.settings["ALLOW_DOWNLOADS"] = True                      # reports, workbooks and CAD files
    webview.create_window(f"MERLIN {__version__}", url, width=1400, height=900, min_size=(900, 600))
    try:
        webview.start(gui="edgechromium" if os.name == "nt" else None)
    except Exception as ex:                                         # noqa: BLE001 - shown, not hidden
        print(f"window failed: {type(ex).__name__}: {ex}")
        _message_box("MERLIN could not open its window. It needs Microsoft Edge WebView2, which is part of "
                     "Windows 11 and most Windows 10 systems; it can be installed from Microsoft's WebView2 "
                     f"page.\n\nDetails: {ex}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
