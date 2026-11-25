"""Lift-off mass errors of the 24 validation vehicles, sized with the book's loss method and with simulated losses (M109).

Prints the Markdown table of docs/ASCENT.md section 5:  python tools/measure_simulated_losses.py [processes]
"""
import os
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import validate_ascent as V                                                      # noqa: E402
from launch_vehicle.config_io import load_design                                 # noqa: E402
from launch_vehicle.convergence import size_vehicle                              # noqa: E402
from launch_vehicle.optimization import optimize_dv_split                        # noqa: E402

COLUMNS = ("own", "simulated", "own_opt", "simulated_opt")


def reason(ex) -> str:
    s = str(ex)
    if "ascent of this vehicle does not close" in s or "both sizes and flies" in s:
        return "no split sizes and flies" if "both sizes" in s else "ascent does not close"
    if "do not settle" in s:
        return "losses run away"
    if "not buildable" in s:
        return "tank not buildable"
    if "runs out of propellant" in s:
        return "core too small for its strap-ons"
    return s[:60]


def measure(key):
    ref = V.reference_tables()[0][key]
    path, glom = os.path.join(ROOT, "validation", key + ".yaml"), ref["glom"][0]
    row = dict(key=key, title=ref["title"], why=[])
    for col, ov in (("own", {}), ("simulated", {"mission.losses.model": "simulated"})):
        row[col] = row[col + "_opt"] = None
        try:
            r = size_vehicle(load_design(path, V.ASSUMP, ov), keep_history=False)
            row[col], row[col + "_loss"] = r.glom_kg / glom - 1.0, r.budget.subtotal("loss")
        except Exception as ex:                              # noqa: BLE001 - a refusal is a result here
            row["why"].append("own split: " + reason(ex))
        try:
            s = load_design(path, V.ASSUMP, ov)
            q = optimize_dv_split(s)
            s.dv_mode, s.dv_fractions, s.dv_fixed = "fractions", q["fractions"], None
            r = size_vehicle(s, keep_history=False)
            row[col + "_opt"] = r.glom_kg / glom - 1.0
            row[col + "_split"] = " / ".join(f"{100 * x:.0f}" for x in q["fractions"])
        except Exception as ex:                              # noqa: BLE001
            row["why"].append("optimised: " + reason(ex))
    print(key, {c: row[c] for c in COLUMNS}, row["why"], file=sys.stderr, flush=True)
    return row


def main():
    keys = sorted(V.reference_tables()[0])
    with ProcessPoolExecutor(int(sys.argv[1]) if len(sys.argv) > 1 else 4) as pool:
        rows = list(pool.map(measure, keys))

    def pct(v):
        return "-" if v is None else f"{100 * v:+.1f} %"
    print("| Vehicle | Design's loss method, own split | Simulated, own split | Design's method, optimised split | "
          "Simulated, optimised split | Optimised split: method / simulated [%] | Refused because |")
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['title']} | " + " | ".join(pct(r[c]) for c in COLUMNS)
              + f" | {r.get('own_split', '-')}; {r.get('simulated_split', '-')} | {'; '.join(r['why'])} |")
    for a, b, what in (("own", "simulated", "own split"), ("own_opt", "simulated_opt", "optimised split")):
        both = [r for r in rows if r[a] is not None and r[b] is not None]
        ea, eb = [abs(r[a]) for r in both], [abs(r[b]) for r in both]
        print(f"\n{what}: {len(both)} vehicles size both ways. Mean absolute error {100*statistics.mean(ea):.1f} % with the "
              f"design's method, {100*statistics.mean(eb):.1f} % simulated; median {100*statistics.median(ea):.1f} % and "
              f"{100*statistics.median(eb):.1f} %; mean signed {100*statistics.mean(r[a] for r in both):+.1f} % and "
              f"{100*statistics.mean(r[b] for r in both):+.1f} %.")


if __name__ == "__main__":
    main()
