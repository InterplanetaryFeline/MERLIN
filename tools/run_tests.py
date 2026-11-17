"""Tiny test runner.

    python tools/run_tests.py                             # the whole suite
    python tools/run_tests.py tests/test_stage_count.py   # just these files
    python tools/run_tests.py test_stage_count            # the name is enough
    python tools/run_tests.py -k stage_count              # only tests whose name matches

It used to take no arguments and silently run everything whatever you passed it, which wastes forty minutes
when you meant to re-check one file - and worse, makes you think you checked one file when you checked the
tree as it was when the run started. Arguments now select, and an argument that matches nothing is an error
rather than a full run.

Prefers real pytest when available: if `import pytest` works from site-packages, defers to it with the same
arguments."""
import importlib.util, os, sys, time, traceback, glob
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(root, "src"), os.path.join(root, "tests"), os.path.join(root, "tools", "mini_pytest")]

args = sys.argv[1:]
pattern = None
if "-k" in args:
    i = args.index("-k")
    if i + 1 >= len(args):
        print("-k needs a pattern"); sys.exit(2)
    pattern = args[i + 1]
    args = args[:i] + args[i + 2:]

try:
    import pytest as _p
    if not hasattr(_p, "approx") or "mini_pytest" not in getattr(_p, "__file__", ""):
        os.chdir(root)
        cmd = [sys.executable, "-m", "pytest", "-v"] + (["-k", pattern] if pattern else []) + (args or ["tests"])
        sys.exit(__import__("subprocess").call(cmd))
except ImportError:
    pass
os.chdir(root)

# Reaching here means the shim is what `import pytest` resolves to (real pytest exits above, delegating to
# itself). Its `skip()` raises this; a test that skips itself is reported as a skip, not a failure.
try:
    from pytest import Skipped as _Skipped
except ImportError:                                   # no pytest of any kind: nothing can raise it
    class _Skipped(Exception):
        pass

everything = sorted(glob.glob(os.path.join(root, "tests", "test_*.py")))
if args:
    paths, unknown = [], []
    for a in args:
        stem = os.path.basename(a)
        if stem.endswith(".py"):
            stem = stem[:-3]
        hits = [p for p in everything if os.path.basename(p)[:-3] == stem]
        if hits:
            paths.extend(hits)
        else:
            unknown.append(a)
    if unknown:
        print("no such test file: " + ", ".join(unknown))
        print("available: " + ", ".join(os.path.basename(p)[:-3] for p in everything))
        sys.exit(2)
    paths = sorted(set(paths))
else:
    paths = everything

passed = failed = skipped = 0
fails = []
t0 = time.time()
for path in paths:
    spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    for name in sorted(n for n in dir(mod) if n.startswith("test_")):
        fn = getattr(mod, name)
        if not callable(fn): continue
        if pattern and pattern not in name:
            skipped += 1; continue
        try:
            fn(); passed += 1; print(f"PASS  {os.path.basename(path)}::{name}")
        except _Skipped as ex:
            # a test that skips itself is not a test that failed: the suite's two uses are legitimate
            # outcomes of the recorded trajectory, not defects
            skipped += 1; print(f"SKIP  {os.path.basename(path)}::{name}  ({ex})")
        except Exception:
            failed += 1; fails.append((path, name)); print(f"FAIL  {os.path.basename(path)}::{name}"); traceback.print_exc()
what = f"{len(paths)} file{'' if len(paths) == 1 else 's'}"
extra = f", {skipped} not matching -k {pattern}" if pattern else ""
print(f"\n{passed} passed, {failed} failed in {time.time()-t0:.1f}s  ({what}{extra}; "
      "runner: mini_pytest shim; real pytest not available)")
if failed:
    print("failed: " + ", ".join(f"{os.path.basename(p)[:-3]}::{n}" for p, n in fails))
sys.exit(1 if failed else 0)
