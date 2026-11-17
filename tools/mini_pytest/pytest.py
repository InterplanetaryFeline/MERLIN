"""Minimal stand-in for the subset of pytest used by this test-suite (approx, raises).
Only used when the real pytest cannot be installed (offline sandbox). With real pytest installed, ignore this."""
import math


class approx:
    """Real pytest's tolerance rules, which are NOT "always take the looser of the two".

    From pytest's own documentation, and the three cases matter here:

      * neither given  -> rel 1e-6 and abs 1e-12, whichever is looser;
      * `abs` only     -> **the absolute tolerance alone**; the default relative one does not apply;
      * both given     -> passes if EITHER is met.

    This shim used to apply `max(abs, 1e-6 * |expected|)` in every case, so `approx(x, abs=...)` was always at
    least as loose as a part-per-million relative check. The suite calls that form 151 times, so on any
    quantity much larger than the stated absolute tolerance the assertion was quietly weaker than it reads -
    `approx(13.32016, abs=1e-9)` was really a 1.3e-5 check. One test was passing only because of it
    (`test_dxf_silhouette_matches_the_geometry`, fixed in v0.28.0 by comparing at the precision the exporters
    actually write). A test suite that is green under the offline runner and red under real pytest is worse
    than no suite, so the shim now agrees with real pytest and the whole suite passes under both.
    """
    _unset = object()

    def __init__(self, expected, rel=None, abs=None):
        self.expected = expected
        self.rel, self.abs = rel, abs

    def _tolerance(self):
        # Real pytest: `abs` alone suppresses the relative check entirely; otherwise the tolerance is the
        # looser of the relative one (`rel`, default 1e-6, times |expected|) and the absolute one (`abs`,
        # default 1e-12). The 1e-12 floor still applies when only `rel` is given, and it is what lets
        # `approx(tiny, rel=1e-12)` pass - dropping it made test_cad_export's faceted-volume convergence test
        # fail under this shim while passing under real pytest, which is exactly the divergence to avoid.
        if self.rel is None and self.abs is not None:
            return self.abs
        relative = (1e-6 if self.rel is None else self.rel) * math.fabs(self.expected)
        return max(relative, 1e-12 if self.abs is None else self.abs)

    def __eq__(self, actual):
        return math.fabs(actual - self.expected) <= self._tolerance()

    def __repr__(self):
        return f"approx({self.expected}, rel={self.rel}, abs={self.abs}, tol={self._tolerance():g})"


class _Raises:
    """Context manager with the same surface the suite uses: `.value` holds the caught exception afterwards."""

    def __init__(self, exc, match=None):
        self.exc, self.match, self.value = exc, match, None

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if et is None:
            raise AssertionError(f"DID NOT RAISE {self.exc}")
        if not issubclass(et, self.exc):
            return False
        if self.match and self.match.lower() not in str(ev).lower():
            raise AssertionError(f"exception text {str(ev)!r} does not contain {self.match!r}")
        self.value = ev
        return True


def raises(exc, match=None):
    return _Raises(exc, match)


def fixture(*a, **kw):
    """Not supported: this shim has no fixture machinery. Tests here use plain helper functions instead, so a
    fixture decorator in a test file is a mistake worth failing loudly on rather than silently mis-running."""
    raise NotImplementedError("tools/mini_pytest has no fixture support - use a module-level helper function "
                              "(see tests/test_report.py) so the suite runs with and without real pytest")


class Skipped(Exception):
    """Raised by `skip()`. `tools/run_tests.py` counts it as a skip, not a failure.

    Without this the shim had `mark.skip` but no top-level `skip()`, so the two calls in test_loads.py - both
    of which skip a comparison when two recorded trajectory points coincide, a legitimate outcome rather than
    a defect - raised AttributeError offline and were reported as FAILURES. tests/test_python_compatibility.py
    now walks the suite's AST for every `pytest.X` the tests actually reach for and asserts the shim has it.
    """


def skip(reason: str = "", **kw):
    raise Skipped(reason)


def fail(reason: str = "", **kw):
    raise AssertionError(reason)


class mark:
    @staticmethod
    def skip(*a, **kw):
        def deco(fn):
            fn.__mini_skip__ = True
            return fn
        return deco

    @staticmethod
    def parametrize(argnames, argvalues, **kw):
        """`@pytest.mark.parametrize`, collapsed into one test.

        `tools/run_tests.py` calls each `test_*` with no arguments, so instead of expanding into N tests the
        way real pytest does, this returns a single no-argument wrapper that runs every case and re-raises the
        first failure with the case prepended to the message. The suite therefore runs to completion under
        both runners; the only thing lost offline is per-case reporting and the fact that one failing case
        stops the remaining ones. Under real pytest the decorator behaves normally, because real pytest's own
        implementation is used - this file is only imported when pytest is missing.
        """
        names = [argnames] if isinstance(argnames, str) and "," not in argnames else (
            [s.strip() for s in argnames.split(",")] if isinstance(argnames, str) else list(argnames))

        def deco(fn):
            if getattr(fn, "__mini_parametrized__", False):
                raise NotImplementedError(
                    f"{fn.__name__}: this shim does not stack parametrize decorators; run it under real "
                    "pytest, or write the second dimension as a loop inside the test")
            def wrapper():
                for case in argvalues:
                    vals = list(case) if len(names) > 1 else [case]
                    try:
                        fn(**dict(zip(names, vals)))
                    except Exception as ex:
                        ident = ", ".join(f"{n}={v!r}" for n, v in zip(names, vals))
                        raise type(ex)(f"[{ident}] {ex}").with_traceback(ex.__traceback__) from None
            wrapper.__name__ = fn.__name__
            wrapper.__doc__ = fn.__doc__
            wrapper.__mini_parametrized__ = True
            return wrapper
        return deco
