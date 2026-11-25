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


#: Microsoft's registry keys for the WebView2 Evergreen runtime
_WEBVIEW2 = r"Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"


def webview2_installed() -> bool | None:
    """Whether the WebView2 runtime is registered on this machine; None off Windows, where it is not asked."""
    if os.name != "nt":
        return None
    import winreg                                                   # noqa: PLC0415 - Windows only
    for hive, key in ((winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\WOW6432Node\\" + _WEBVIEW2),
                      (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\" + _WEBVIEW2),
                      (winreg.HKEY_CURRENT_USER, "Software\\" + _WEBVIEW2)):
        try:
            with winreg.OpenKey(hive, key) as k:
                if str(winreg.QueryValueEx(k, "pv")[0]) not in ("", "0.0.0.0"):
                    return True
        except OSError:
            continue
    return False


def window_error_text(ex: BaseException, webview2: bool | None, log_path: str) -> str:
    """What to tell the user when the window does not open: the likely cause, and the real error under it."""
    if "Python.Runtime" in str(ex):
        why = ("Windows is blocking part of MERLIN, usually because the files are marked as downloaded from the internet.\n\n"
               "Delete this folder, right-click the zip you downloaded, choose Properties, tick Unblock, and extract it again. "
               "If Unblock is not offered, your organisation may be blocking it: ask your IT department.")
    elif webview2 is False:
        why = ("It needs the Microsoft Edge WebView2 Runtime, which was not found on this computer. It can be installed from "
               "Microsoft's WebView2 page.")
    else:
        why = "The cause is not one MERLIN recognises."
    return f"MERLIN could not open its window.\n\n{why}\n\nDetails: {ex}\nLog: {log_path}"


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
        _message_box(window_error_text(ex, webview2_installed(), os.path.join(workdir, "merlin.log")))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
