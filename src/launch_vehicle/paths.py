"""Where MERLIN's data lives: `config/`, `examples/`, `validation/`, `designs/` and `outputs/`.

Run from source, that is the project folder, two levels above this package. Run as the packaged desktop app,
the package is inside the app's `_internal/` folder, so a path counted from this file would point there. The app
keeps its data next to `MERLIN.exe` instead, where the user can see it and the GUI can save designs.
"""
from __future__ import annotations
import os
import sys


def project_root(frozen: bool | None = None, executable: str | None = None, environ=None) -> str:
    """The folder the data directories hang off.

    `MERLIN_HOME` overrides it in a packaged app, to point the app at another data folder. The arguments exist so
    tests can ask what a packaged app would do without being one.
    """
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    environ = os.environ if environ is None else environ
    if frozen:
        home = environ.get("MERLIN_HOME")
        return os.path.abspath(home) if home else os.path.dirname(os.path.abspath(executable or sys.executable))
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


ROOT = project_root()
