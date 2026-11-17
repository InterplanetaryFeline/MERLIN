"""Recalculate a generated workbook with LibreOffice and check every built-in cross-check cell.

The workbook contains live Excel formulas that recompute the Python engine's results independently
(rocket equation, mass closure, tank/casing volume, centre of mass, inertia, phase delta-v). openpyxl
only writes the formulas - it does not evaluate them - so this tool runs LibreOffice headless to
recalculate the file and then asserts that every "should be 0" cell really is zero.

Usage:  python tools/verify_workbook.py <workbook.xlsx> [more.xlsx ...]
Exit code 0 = all cross-checks passed.
"""
from __future__ import annotations
import os
import re
import shutil
import subprocess
import sys
import tempfile
from openpyxl import load_workbook

# header text (row 4 of a table) -> absolute tolerance for every data cell below it
COL_CHECKS = {
    "dv - allocated": 1e-3,
    "Mass closure:": 1e-3,
    "Volume check": 1e-4,
    "Difference (should be 0)": 1e-3,
}
# row-label text in column A -> tolerance for the numeric cells on that row
ROW_CHECKS = {
    "difference (should be 0)": 1e-3,
    "closure error": 1e-3,
    "difference (should be ~0)": 1e-2,
}


def recalc(path: str, outdir: str) -> str:
    """Convert the workbook with LibreOffice (which recalculates on load) and return the new path."""
    cmd = ["soffice", "--headless", "--norestore", "--convert-to", "xlsx:Calc MS Excel 2007 XML",
           "--outdir", outdir, path]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    out = os.path.join(outdir, os.path.basename(path))
    if not os.path.exists(out):
        raise RuntimeError(f"LibreOffice did not produce {out}: {r.stdout}{r.stderr}")
    return out


def check_workbook(path: str, verbose: bool = True) -> list:
    """Return a list of failure strings (empty = everything passed)."""
    fails, checked = [], 0
    per_sheet = {}
    with tempfile.TemporaryDirectory() as td:
        wb = load_workbook(recalc(path, td), data_only=True)
        for ws in wb.worksheets:
            # --- column checks: find header cells, then test the cells underneath
            for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 200)):
                for cell in row:
                    if not isinstance(cell.value, str):
                        continue
                    for key, tol in COL_CHECKS.items():
                        if cell.value.startswith(key):
                            col = cell.column
                            for r in range(cell.row + 1, ws.max_row + 1):
                                v = ws.cell(row=r, column=col).value
                                if v is None or isinstance(v, str):
                                    continue
                                checked += 1
                                per_sheet[ws.title] = per_sheet.get(ws.title, 0) + 1
                                if abs(v) > tol:
                                    fails.append(f"{os.path.basename(path)} [{ws.title}] {cell.value[:48]!r} "
                                                 f"row {r}: {v:.6g} (tol {tol})")
            # --- row checks: a label in column A with numbers on the same row
            for r in range(1, ws.max_row + 1):
                lab = next((ws.cell(row=r, column=c).value for c in (1, 2, 3)
                            if isinstance(ws.cell(row=r, column=c).value, str)), None)
                lab_col = next((c for c in (1, 2, 3) if isinstance(ws.cell(row=r, column=c).value, str)), 1)
                if not isinstance(lab, str):
                    continue
                for key, tol in ROW_CHECKS.items():
                    if key in lab.lower():
                        for c in range(lab_col + 1, min(ws.max_column, lab_col + 10) + 1):
                            v = ws.cell(row=r, column=c).value
                            if isinstance(v, (int, float)):
                                checked += 1
                                per_sheet[ws.title] = per_sheet.get(ws.title, 0) + 1
                                if abs(v) > tol:
                                    fails.append(f"{os.path.basename(path)} [{ws.title}] {lab[:48]!r} "
                                                 f"row {r} col {c}: {v:.6g} (tol {tol})")
    if verbose:
        detail = ", ".join(f"{k}:{v}" for k, v in sorted(per_sheet.items()))
        print(f"{os.path.basename(path)}: {checked} cross-check cells recalculated, {len(fails)} failed  [{detail}]")
    return fails


def main(argv):
    if not shutil.which("soffice"):
        print("LibreOffice (soffice) is not installed: cannot recalculate the workbook formulas.")
        return 2
    paths = argv[1:]
    if not paths:
        print(__doc__)
        return 2
    allf = []
    for p in paths:
        try:
            allf += check_workbook(p)
        except Exception as ex:                      # noqa: BLE001 - report, do not hide
            allf.append(f"{p}: verification failed to run: {ex}")
    print()
    if allf:
        print(f"FAILED cross-checks ({len(allf)}):")
        for f in allf:
            print("  -", f)
        return 1
    print("All workbook cross-check formulas evaluate to zero within tolerance.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
