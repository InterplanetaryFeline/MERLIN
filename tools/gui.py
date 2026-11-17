"""Start the local sizing GUI.

    python tools/gui.py                 # http://127.0.0.1:8000, opens a browser
    python tools/gui.py --port 8080 --no-browser

Stdlib only; nothing is sent anywhere. The server binds to the loopback interface by default.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from launch_vehicle.webgui import serve                      # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Local GUI for the launch-vehicle sizing tool")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1",
                    help="bind address; keep the default unless you know you want it reachable from elsewhere")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--workdir", default=os.path.join(ROOT, "outputs", "gui"))
    a = ap.parse_args()
    serve(port=a.port, host=a.host, open_browser=not a.no_browser, workdir=a.workdir)
