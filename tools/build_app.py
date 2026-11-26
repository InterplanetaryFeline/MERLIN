"""Build MERLIN as a Windows desktop app: a folder with MERLIN.exe that needs no Python and no browser.

    python -m venv .venv-build
    .venv-build\\Scripts\\activate
    pip install -r requirements.txt pywebview pyinstaller
    python tools/build_app.py                  # -> dist/MERLIN/MERLIN.exe
    python tools/build_app.py --zip            # also dist/MERLIN-<version>-windows.zip, for a GitHub Release

Build in a clean virtual environment: PyInstaller bundles whatever the building Python can import, so a
crowded environment makes a crowded app.

The result is one folder. MERLIN.exe and its runtime sit beside the data folders the GUI reads and writes
(config, examples, validation, designs, outputs), so that folder is the whole installation: copy it anywhere
writable and run MERLIN.exe. It needs Microsoft Edge WebView2, which is part of Windows 11.
"""
from __future__ import annotations
import importlib.metadata as md
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
APP = os.path.join(DIST, "MERLIN")

#: data the app reads and writes, copied beside MERLIN.exe rather than hidden in its runtime
DATA_DIRS = ["config", "examples", "validation"]
DATA_FILES = ["LICENSE", "README.md", "CITATION.cff", "docs", "outputs/README.txt",
              "outputs/engineering_method_register.xlsx", "outputs/engineering_method_register.csv",
              "designs/README.txt"]

#: modules the app never needs. tkinter and the Qt bindings are only matplotlib's interactive backends;
#: MERLIN draws with Agg. The CAD kernel is optional and very large.
EXCLUDE = ["tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6", "cadquery", "OCP", "pytest", "IPython"]

#: compiled libraries the engine cannot run without; PyInstaller puts each in a folder of its own
REQUIRED_IN_BUNDLE = ["numpy", "scipy", "matplotlib", "openpyxl", "yaml", "webview"]

#: packages whose licences require their notices to travel with a binary copy
BUNDLED = ["numpy", "scipy", "matplotlib", "openpyxl", "PyYAML", "pywebview", "pythonnet", "clr_loader",
           "pillow", "contourpy", "cycler", "fonttools", "kiwisolver", "packaging", "pyparsing",
           "python-dateutil", "six", "et_xmlfile", "proxy_tools", "bottle", "cffi", "pycparser",
           "typing_extensions", "pyinstaller"]


def third_party_licences(dest: str) -> list:
    os.makedirs(dest, exist_ok=True)
    missing = []
    for name in BUNDLED:
        try:
            dist = md.distribution(name)
        except md.PackageNotFoundError:
            continue
        files = [f for f in (dist.files or []) if any(k in f.name.upper() for k in ("LICENSE", "LICENCE", "COPYING", "NOTICE"))]
        if not files:
            # some packages ship no licence file, only a licence named in their metadata: record that instead
            meta = dist.metadata
            stated = meta.get("License-Expression") or meta.get("License") or ""
            if not stated.strip():
                missing.append(name)
                continue
            with open(os.path.join(dest, f"{meta['Name']}-{dist.version}-LICENSE-from-metadata.txt"), "w",
                      encoding="utf-8", newline="\n") as fh:
                fh.write(f"{meta['Name']} {dist.version}\nAuthor: {meta.get('Author') or meta.get('Author-email') or 'not stated'}\n"
                         f"Home page: {meta.get('Home-page') or 'not stated'}\n\nLicence as stated in the package "
                         f"metadata (the package ships no licence file):\n{stated}\n")
            continue
        for f in files:
            src = f.locate()
            if os.path.isfile(src):
                shutil.copyfile(src, os.path.join(dest, f"{dist.metadata['Name']}-{dist.version}-{f.name}"))
    return missing


#: .NET refuses to load a library that carries Windows' downloaded-from-the-internet mark, and Explorer puts that mark on
#: every file it extracts from a downloaded zip. This is .NET's own setting for an application that trusts its libraries.
EXE_CONFIG = """<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <runtime>
    <loadFromRemoteSources enabled="true"/>
  </runtime>
</configuration>
"""


def write_exe_config(app_dir: str) -> str:
    out = os.path.join(app_dir, "MERLIN.exe.config")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(EXE_CONFIG)
    return out


def version() -> str:
    import re
    with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as fh:
        return re.search(r'^version\s*=\s*"([^"]+)"', fh.read(), re.M).group(1)


def make_zip(app_dir: str, out: str) -> str:
    """Pack the app so that unzipping gives one folder, MERLIN, with MERLIN.exe at its top."""
    import zipfile
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for base, _dirs, files in os.walk(app_dir):
            for f in files:
                full = os.path.join(base, f)
                z.write(full, os.path.join("MERLIN", os.path.relpath(full, app_dir)))
    with zipfile.ZipFile(out) as z:                       # read it back: a corrupt archive is worse than none
        bad = z.testzip()
        if bad or not {"MERLIN/MERLIN.exe", "MERLIN/MERLIN.exe.config"} <= set(z.namelist()):
            raise RuntimeError(f"the archive {out} is not usable (bad member: {bad})")
    return out


def main(argv=None) -> int:
    global DIST, APP
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dist", default=DIST, help="folder to build into; the app lands in <dist>/MERLIN")
    ap.add_argument("--zip", action="store_true",
                    help="also pack the app as <dist>/MERLIN-<version>-windows.zip, unpacking to MERLIN/MERLIN.exe")
    a = ap.parse_args(argv)
    DIST, APP = os.path.abspath(a.dist), os.path.join(os.path.abspath(a.dist), "MERLIN")
    for mod in ("PyInstaller", "webview"):
        try:
            __import__(mod)
        except ImportError:
            print(f"missing {mod}: pip install pyinstaller pywebview")
            return 1

    # the rocket in the wizard's hat (tools/make_icon.py draws it): the exe's icon, which Windows also puts on the
    # window's title bar and the taskbar
    icon = os.path.join(ROOT, "src", "launch_vehicle", "gui_static", "merlin.ico")
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", "MERLIN",
           "--icon", icon,
           "--distpath", DIST, "--workpath", os.path.join(ROOT, "build"), "--specpath", os.path.join(ROOT, "build"),
           "--paths", os.path.join(ROOT, "src"),
           "--collect-submodules", "launch_vehicle",
           "--add-data", f"{os.path.join(ROOT, 'src', 'launch_vehicle', 'gui_static')}{os.pathsep}launch_vehicle/gui_static"]
    for m in EXCLUDE:
        cmd += ["--exclude-module", m]
    cmd.append(os.path.join(ROOT, "tools", "merlin_app.py"))
    print(" ".join(cmd))
    if subprocess.call(cmd):
        return 1

    # PyInstaller reports success even when its import scan missed the engine's libraries; the first build did
    # exactly that and produced a 28 MB app that would have failed on its first calculation
    # compiled packages get a folder in _internal; pure-Python ones live only in the PYZ archive, whose table of
    # contents PyInstaller leaves in the work folder
    with open(os.path.join(ROOT, "build", "MERLIN", "PYZ-00.toc"), encoding="utf-8") as fh:
        toc = fh.read()
    engine = [f"launch_vehicle.{f[:-3]}" for f in os.listdir(os.path.join(ROOT, "src", "launch_vehicle"))
              if f.endswith(".py") and f != "__init__.py"]
    absent = [m for m in REQUIRED_IN_BUNDLE + engine
              if not os.path.isdir(os.path.join(APP, "_internal", m)) and f"'{m}'" not in toc]
    if absent:
        print("BUILD IS NOT USABLE: these libraries are not in the bundle: " + ", ".join(absent))
        return 1

    write_exe_config(APP)
    for d in DATA_DIRS:
        shutil.copytree(os.path.join(ROOT, d), os.path.join(APP, d), dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__"))
    for f in DATA_FILES:
        src, dst = os.path.join(ROOT, f), os.path.join(APP, f)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copyfile(src, dst)
    missing = third_party_licences(os.path.join(APP, "third_party_licenses"))
    if missing:
        print("WARNING: no licence file found for: " + ", ".join(missing) + ". Add their notices by hand.")

    size = sum(os.path.getsize(os.path.join(b, f)) for b, _, fs in os.walk(APP) for f in fs)
    print(f"\nbuilt {os.path.join(APP, 'MERLIN.exe')}  ({size / 1e6:.0f} MB in the folder)")
    if a.zip:
        out = make_zip(APP, os.path.join(DIST, f"MERLIN-{version()}-windows.zip"))
        print(f"packed {out}  ({os.path.getsize(out) / 1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
