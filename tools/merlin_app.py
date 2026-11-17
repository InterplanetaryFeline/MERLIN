"""Entry point PyInstaller builds MERLIN.exe from.

It has to be a script with absolute imports: `launch_vehicle/desktop.py` uses package-relative imports, and
PyInstaller cannot follow those from a module it runs as a script, so a build started there bundled none of the
engine's libraries.
"""
import sys

from launch_vehicle.desktop import main

if __name__ == "__main__":
    sys.exit(main())
