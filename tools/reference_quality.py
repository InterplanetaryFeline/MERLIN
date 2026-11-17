"""How much of each check case is actually sourced, on the inputs that decide its answer?

WHY THIS EXISTS. A validation table that says "Zhuque-2 -31.7 %" invites the reader to conclude the mass
model is 31.7 % light on that vehicle. For Zhuque-2 that conclusion is wrong, and the design file says so
in its own source fields: its stage-1 Isp carries `s: "ASSUMED (TQ-12 Isp not found)"`, its engine is named
"Generic LOX/RP-1 booster engine - Representative placeholder, not a real engine datasheet", and its
chamber pressure and expansion ratio are assumed too. The error is measuring an assumption, not the model.

That matters because Isp is the highest-leverage input a case has. Measured on Zhuque-2, dropping the three
assumed Isp values by a plausible 15 s - from 300/330 and 355 s to Merlin-class 285/315 and 340 s - moves
its GLOM error from -31.5 % to -19.0 %, and by 20 s to -14.0 %. Those alternatives are not adopted: picking
an Isp because it reduces the error is tuning an input to match a vehicle, which this project does not do.
The point is only that an error this sensitive to an unsourced number is not evidence about the model.

WHAT IT REPORTS. Per case, how many annotated leaves are `reference`, `user` and `assumed`, and then
separately whether any CRITICAL input - the ones the sizing answer turns on - is assumed rather than
sourced. A case with an assumed critical input is marked REFERENCE-WEAK, which is a statement about the
input data, not about the vehicle or the tool.

A sea-level Isp assumed from a published vacuum figure is a much smaller sin than an Isp assumed from
nothing, so the two are counted but the report prints the source text and lets a reader judge.
"""
import argparse
import glob
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Inputs the sized answer turns on. Isp sets the mass ratio, thrust sets the T/W and the burn time, and a
#: published propellant load pins the stage outright. An assumed value in any of these propagates straight
#: into GLOM through the fixed point.
CRITICAL = ("isp_sl_s", "isp_vac_s", "thrust_vac_per_engine_N", "thrust_sl_total_N",
            "thrust_vac_total_N", "prop_mass_each_kg", "prop_mass_kg")


def annotated_leaves(obj, path=""):
    """Yield (path, value, provenance, source) for every {v,u,d,s,t} leaf in a design document."""
    if isinstance(obj, dict):
        if "t" in obj and "v" in obj and not isinstance(obj.get("v"), dict):
            yield path, obj.get("v"), obj.get("t"), obj.get("s")
            return
        for k, v in obj.items():
            yield from annotated_leaves(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from annotated_leaves(v, f"{path}[{i}]")


def audit(path):
    doc = yaml.safe_load(open(path, encoding="utf-8"))
    counts = {"reference": 0, "user": 0, "assumed": 0, "calculated": 0, "other": 0}
    weak = []
    for p, value, prov, src in annotated_leaves(doc):
        counts[prov if prov in counts else "other"] += 1
        if prov == "assumed" and value is not None and p.split(".")[-1] in CRITICAL:
            weak.append((p, value, (src or "").strip()))
    return counts, weak


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", default=os.path.join(ROOT, "validation"))
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)

    rows = []
    for f in sorted(glob.glob(os.path.join(a.dir, "*.yaml"))):
        name = os.path.basename(f)[:-5]
        if name.startswith("combo_"):
            continue
        counts, weak = audit(f)
        rows.append((name, counts, weak))

    rows.sort(key=lambda r: (-len(r[2]), r[0]))
    print(f"{'case':16s}{'ref':>6s}{'user':>6s}{'assumed':>9s}{'sourced':>9s}  critical inputs assumed")
    print("-" * 78)
    for name, c, weak in rows:
        tot = c["reference"] + c["user"] + c["assumed"] + c["calculated"]
        frac = 100.0 * c["reference"] / tot if tot else 0.0
        mark = f"{len(weak)}" if weak else "-"
        print(f"{name:16s}{c['reference']:>6d}{c['user']:>6d}{c['assumed']:>9d}{frac:>8.0f}%  {mark}")

    weakest = [r for r in rows if r[2]]
    if weakest and not a.quiet:
        print()
        print("REFERENCE-WEAK CASES - the error of these does not measure the model, it measures the")
        print("assumption. Read their GLOM error with that in mind, and do NOT adjust these values to")
        print("reduce an error: that is tuning an input to match a vehicle.")
        for name, _c, weak in weakest:
            print(f"\n  {name}")
            for p, v, src in weak:
                short = p.replace("stages[", "s").replace("].engine.", ".").replace("].motor.", ".")
                print(f"    {short:28s} = {v}")
                if src:
                    print(f"      {src[:104]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
