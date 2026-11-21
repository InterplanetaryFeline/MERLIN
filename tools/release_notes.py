"""Write the GitHub Release text for one version, from that version's section of docs/CHANGELOG.md.

    python tools/release_notes.py 1.2.0 > notes.md

The changelog is the one place the changes are described, so the release page is made from it rather than
written twice. The download instructions go first, because the page is where people come to get the app.
"""
from __future__ import annotations
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADING = re.compile(r"^\*\*What changed in v(\d+\.\d+\.\d+)\b.*\*\*\s*$")


def section(version: str, text: str) -> str:
    """The body of the changelog section for `version`, without its heading. Raises if there is none."""
    lines = text.replace("\r\n", "\n").split("\n")
    start = None
    for i, ln in enumerate(lines):
        m = HEADING.match(ln)
        if m and start is None and m.group(1) == version:
            start = i
        elif m and start is not None:
            return "\n".join(lines[start + 1:i]).strip() + "\n"
    if start is None:
        raise SystemExit(f"docs/CHANGELOG.md has no section for v{version}: add one before releasing")
    return "\n".join(lines[start + 1:]).strip() + "\n"


def title(version: str, text: str) -> str:
    for ln in text.replace("\r\n", "\n").split("\n"):
        m = HEADING.match(ln)
        if m and m.group(1) == version:
            t = ln.strip().strip("*")
            return t.split(" - ", 1)[1].strip() if " - " in t else ""
    return ""


def notes(version: str, text: str) -> str:
    sub = title(version, text)
    head = (f"## MERLIN {version}" + (f": {sub}" if sub else "") + "\n\n"
            f"**Windows app:** download `MERLIN-{version}-windows.zip` below, unzip it and run `MERLIN/MERLIN.exe`. "
            f"No Python and no browser are needed. The two \"Source code\" archives do not contain the app.\n\n"
            f"### What changed\n\n")
    return head + section(version, text)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python tools/release_notes.py <version, e.g. 1.2.0>")
    v = sys.argv[1].lstrip("v")
    with open(os.path.join(ROOT, "docs", "CHANGELOG.md"), encoding="utf-8") as fh:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(notes(v, fh.read()))
