"""Every source file must parse on the OLDEST Python this project claims to support.

This file exists because of a bug that reached a user. `main.py` contained

    print(f"  {'all parts matched' if ok else 'AT LEAST ONE PART FAILED - no solid '
          'would be exported'}")

an f-string whose EXPRESSION spans two source lines. That is PEP 701 syntax, accepted only from Python 3.12.
The project declares `requires-python = ">=3.10"`, and the container the whole 725-test suite runs in is
3.13 - so every test passed, the file was shipped, and it would not even parse for anyone on 3.10 or 3.11.
A syntax error is not caught by any amount of behavioural testing: the module never loads.

Two checks, and between them they cover both directions:

  * On Python 3.12 and newer, the tokeniser reports f-strings as FSTRING_START/MIDDLE/END, which makes the
    two PEP 701-only constructs detectable: a non-triple-quoted f-string whose start and end are on
    different lines, and a nested string reusing the f-string's own quote character. That is a FORWARD
    compatibility check - a new interpreter proving the code still suits an old one.
  * On any version, every file is compiled. On 3.10 or 3.11 that is what catches the problem directly,
    because the file simply will not compile there.

So the suite is meaningful whichever interpreter runs it, and the check that matters is the one the running
interpreter is actually able to make.
"""
import io
import os
import pytest
import pathlib
import re
import sys
import tokenize

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent

#: directories whose .py files ship to users or run as part of the tool
SOURCE_DIRS = ("src", "tools", "tests")


def declared_minimum():
    """The lowest Python pyproject.toml claims to support, as a (major, minor) tuple.

    Parsed with a regex rather than tomllib, because tomllib itself is 3.11+ and this file has to run on
    the oldest version it is checking for.
    """
    text = (ROOT_DIR / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'requires-python\s*=\s*"[^0-9]*(\d+)\.(\d+)', text)
    assert m, "pyproject.toml does not declare requires-python"
    return int(m.group(1)), int(m.group(2))


def python_files():
    for d in SOURCE_DIRS:
        for p in sorted((ROOT_DIR / d).rglob("*.py")):
            if "__pycache__" not in p.parts:
                yield p


def pep701_offenders(src: str):
    """f-strings in `src` that only parse on Python 3.12+. Empty list on older interpreters."""
    if sys.version_info < (3, 12):
        return []                                    # the tokeniser here cannot see inside an f-string
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, SyntaxError) as e:
        return [(0, f"could not tokenise: {e}")]

    out, depth, start = [], 0, None
    for t in toks:
        name = tokenize.tok_name[t.type]
        if name == "FSTRING_START":
            depth += 1
            if depth == 1:
                start = t
        elif name == "FSTRING_END":
            if depth == 1 and start is not None:
                quote = start.string.lstrip("fFrRbB")
                if not quote.startswith(('"""', "'''")) and t.end[0] != start.start[0]:
                    out.append((start.start[0],
                                "the expression inside this f-string spans more than one line, which is "
                                "PEP 701 syntax and parses only on Python 3.12+. Compute the value on its "
                                "own line and interpolate the name instead"))
            depth = max(0, depth - 1)
            if depth == 0:
                start = None
        elif depth >= 1:
            # NOTE the shape here: these are separate `if`s, not an elif chain off the STRING case. The
            # first version of this check WAS an elif after it, so a nested STRING token was consumed by
            # the quote test and never reached the backslash test - which is precisely the token the
            # backslash bug lives in, and the detector reported the offending line as clean.
            if name == "STRING" and start is not None:
                q = start.string.lstrip("fFrRbB")[0]
                s = t.string.lstrip("fFrRbBuU")
                if s[:1] == q and not s.startswith(q * 3):
                    out.append((t.start[0],
                                f"this nested string reuses the f-string's own {q!r} quote, which is "
                                "PEP 701 syntax and parses only on Python 3.12+. Use the other quote "
                                "character"))
            if name == "COMMENT":
                out.append((t.start[0],
                            "a comment inside an f-string expression is PEP 701 syntax and parses only "
                            "on Python 3.12+"))
            # The THIRD PEP 701 relaxation, and the one that shipped a second syntax error to a user:
            #     f'{"\\u2026" if len(m) > 260 else ""}'
            # A backslash is fine in the literal TEXT of an f-string - that is FSTRING_MIDDLE, excluded
            # here - but before 3.12 it may not appear anywhere in the EXPRESSION. Bind the value to a
            # name on its own line and interpolate the name.
            if name != "FSTRING_MIDDLE" and "\\" in t.string:
                out.append((t.start[0],
                            f"this {name.lower()} puts a backslash inside an f-string EXPRESSION, which "
                            f"is PEP 701 syntax and parses only on Python 3.12+ - before that it is "
                            f"'SyntaxError: f-string expression part cannot include a backslash'. Bind "
                            f"it to a name first and interpolate the name"))
    return out


# --------------------------------------------------------------------------------- the checks
def test_the_declared_minimum_is_what_we_think_it_is():
    major, minor = declared_minimum()
    assert major == 3 and minor <= 11, (
        f"pyproject.toml declares Python {major}.{minor}. If the minimum were really raised to 3.12 this "
        "test would be pointless, so raising it is a deliberate decision to make here as well")


def test_no_source_file_uses_f_string_syntax_newer_than_the_declared_minimum():
    """The exact bug that shipped: a 3.12-only f-string in a project declaring 3.10."""
    major, minor = declared_minimum()
    if (major, minor) >= (3, 12):
        return
    if sys.version_info < (3, 12):
        return                                       # the compile check below is what catches it here
    bad = []
    for p in python_files():
        for line, why in pep701_offenders(p.read_text(encoding="utf-8")):
            bad.append(f"{p.relative_to(ROOT_DIR)}:{line}  {why}")
    assert not bad, (
        f"{len(bad)} f-string(s) need Python 3.12+ but this project supports {major}.{minor}:\n  "
        + "\n  ".join(bad))


def test_every_shipped_file_compiles():
    """A syntax error anywhere is invisible to behavioural tests, because the module never loads."""
    import py_compile
    import tempfile

    bad = []
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.pyc")
        for p in python_files():
            try:
                py_compile.compile(str(p), cfile=out, doraise=True)
            except py_compile.PyCompileError as e:
                bad.append(f"{p.relative_to(ROOT_DIR)}: {e.msg.strip()}")
    assert not bad, "files that do not compile:\n  " + "\n  ".join(bad)


def test_the_detector_actually_detects_the_bug_that_shipped():
    """A guard nobody has seen fail is not a guard. This is the real line, verbatim."""
    if sys.version_info < (3, 12):
        return
    shipped = (
        'print(f"  {\'all parts matched\' if rep[\'all_ok\'] else \'AT LEAST ONE PART FAILED - no solid \'\n'
        '      \'would be exported\'}")\n')
    found = pep701_offenders(shipped)
    assert found, "the detector does not catch the exact f-string that broke for a user"
    assert "3.12" in found[0][1]

    # and the same-quote form, the other half of PEP 701
    nested = 'x = f"{d["key"]}"\n'
    assert pep701_offenders(nested), "the nested-same-quote form is not caught"


def test_the_detector_does_not_cry_wolf():
    """Ordinary f-strings, including multi-line TRIPLE-quoted ones, must pass."""
    if sys.version_info < (3, 12):
        return
    fine = [
        'a = f"{x:>10.2f} and {y!r}"',                       # format spec and conversion
        '''b = f"{d['key']}"''',                               # nested string, other quote: fine everywhere
        'c = f"""spanning\nlines {z} is fine"""',             # triple-quoted f-strings may span lines
        'd = ("implicit "\n     f"concatenation {w}")',       # concatenation across lines is not PEP 701
        'e = f"{a}{b}{c}"',
    ]
    for src in fine:
        assert not pep701_offenders(src + "\n"), f"false positive on: {src!r}"


# --------------------------------------------------------------------------------- the third relaxation
def test_a_backslash_in_an_f_string_expression_is_caught():
    """The construct that shipped a SECOND syntax error to a user, after this file already existed.

        items = "".join(f'<li>{_e(i.code)}{"\\u2026" if len(i.message) > 260 else ""}</li>' ...)

    The detector was here, the compile check was here, and neither caught it: the compile check ran on 3.13
    where the line is legal, and the detector only looked for the other two PEP 701 forms. Worse, the first
    attempt at this check was written as an `elif` after the nested-quote test, so the STRING token carrying
    the backslash was consumed before it could be examined and the offending line was reported clean. Both
    the construct and that shape of mistake are pinned here.
    """
    if sys.version_info < (3, 12):
        return
    offenders = pep701_offenders('''x = f'{"\\u2026" if n > 260 else ""}'\n''')
    assert offenders, "a backslash inside an f-string expression is not caught"
    assert "backslash" in offenders[0][1]

    # the same restriction, without a nested string
    assert pep701_offenders('''y = f'{"a\\nb".upper()}'\n''')

    # and the legal neighbour it must not be confused with: a backslash in the TEXT part is fine everywhere
    assert not pep701_offenders('z = f"a \\u2026 b {y}"\n'), "a backslash in the literal text is legal"
    assert not pep701_offenders('w = f"{a}" + "\\n"\n'), "a backslash outside the f-string is legal"


def test_a_comment_inside_an_f_string_expression_is_caught():
    if sys.version_info < (3, 12):
        return
    assert pep701_offenders('x = f"{y # a comment\n}"\n')


# --------------------------------------------------------------------------------- the real interpreter
def older_interpreter():
    """An interpreter on PATH at least as old as the declared minimum, if there is one.

    The forward-compatibility detector above is a model of another interpreter's rules. This finds the real
    thing. It is opportunistic by design: absent on most machines, and then these tests simply do not run.
    """
    import shutil
    major, minor = declared_minimum()
    for m in range(minor, sys.version_info.minor):
        exe = shutil.which(f"python{major}.{m}")
        if exe:
            return exe, (major, m)
    return None, None


def test_every_shipped_file_compiles_on_the_oldest_interpreter_available():
    """Compile everything with a real old interpreter when the machine has one.

    This is the check that would have caught both shipped syntax errors outright, with no modelling of
    anyone's grammar. It needs no network and no install - only that some older python happens to be on
    PATH - so it costs nothing on the machines that cannot run it.
    """
    import json
    import subprocess
    exe, ver = older_interpreter()
    if not exe:
        return                                       # nothing older installed: the detector is the guard
    files = [str(p) for p in python_files()]
    prog = (
        "import json,sys,tempfile,py_compile,os\n"
        "bad=[]\n"
        "tmp=tempfile.mkdtemp()\n"
        "for i,p in enumerate(json.load(sys.stdin)):\n"
        "    try: py_compile.compile(p, doraise=True, cfile=os.path.join(tmp,str(i)+'.pyc'))\n"
        "    except py_compile.PyCompileError as e: bad.append(p+': '+str(e).strip().splitlines()[-1])\n"
        "print(json.dumps(bad))\n"
    )
    r = subprocess.run([exe, "-c", prog], input=json.dumps(files), capture_output=True, text=True,
                       timeout=300)
    assert r.returncode == 0, f"could not run {exe}: {r.stderr[:400]}"
    bad = json.loads(r.stdout.strip().splitlines()[-1])
    assert not bad, (
        f"{len(bad)} file(s) do not compile on Python {ver[0]}.{ver[1]}, which this project claims to "
        f"support:\n  " + "\n  ".join(bad))


def test_the_detector_agrees_with_that_older_interpreter():
    """Check the model against the real grammar, on the forms that distinguish them.

    A detector that is merely self-consistent proves nothing. Each snippet below is both run through the
    detector and handed to the older interpreter, and the two verdicts have to match - which is how the
    legal look-alikes (a backslash in the text part, a nested string in the other quote, a triple-quoted
    f-string spanning lines) are shown not to be false positives.
    """
    import os
    import subprocess
    import tempfile
    exe, ver = older_interpreter()
    if not exe or sys.version_info < (3, 12):
        return
    cases = [
        '''x = f'{"\\u2026" if n else ""}' ''',             # backslash in expression
        '''x = f'{"a\\nb".upper()}' ''',                    # backslash in expression, no nested quote
        '''x = f"a \\u2026 b {y}"''',                       # backslash in TEXT: legal
        '''x = f"{d["k"]}"''',                              # nested same quote
        '''x = f"{d['k']}"''',                              # nested other quote: legal
        '''x = f"{'a'\n 'b'}"''',                           # multi-line expression
        '''x = f"""{\n  y\n}"""''',                         # triple-quoted, multi-line: legal
        '''x = f"{y # c\n}"''',                             # comment in expression
        '''x = f"{a}-{b!r:>8}"''',                          # plain: legal
        '''x = f"{f'{y}'}"''',                              # nested f-string, other quote: legal
        '''x = f"{a}" + "\\n"''',                           # backslash outside: legal
    ]
    tmp = tempfile.mkdtemp()
    src_path, out_path = os.path.join(tmp, "c.py"), os.path.join(tmp, "o.pyc")
    disagreed = []
    for src in cases:
        with open(src_path, "w", encoding="utf-8") as fh:
            fh.write(src + "\n")
        r = subprocess.run(
            [exe, "-c", f"import py_compile;py_compile.compile({src_path!r},doraise=True,cfile={out_path!r})"],
            capture_output=True, text=True, timeout=60)
        if bool(pep701_offenders(src + "\n")) != (r.returncode != 0):
            disagreed.append(f"{src!r}: detector said "
                             f"{'offending' if pep701_offenders(src + chr(10)) else 'clean'}, "
                             f"Python {ver[0]}.{ver[1]} said "
                             f"{'offending' if r.returncode else 'clean'}")
    assert not disagreed, ("the forward-compatibility detector disagrees with the real interpreter:\n  "
                           + "\n  ".join(disagreed))


# ------------------------------------------------------------------ the offline runner must not be laxer
def _mini():
    """Load tools/mini_pytest/pytest.py by path, not by import: under real pytest the name `pytest` is
    already taken by the real thing, which is the whole point of the comparison."""
    import importlib.util
    p = os.path.join(ROOT_DIR, "tools", "mini_pytest", "pytest.py")
    spec = importlib.util.spec_from_file_location("_mini_pytest_under_test", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Each case is (expected, kwargs, actual). They cover the three tolerance regimes and the two edge cases that
# actually bit: `abs` alone must SUPPRESS the default relative check (real pytest's documented behaviour, and
# the shim used to take the looser of the two, quietly weakening the 151 `approx(..., abs=)` assertions in this
# suite), and `rel` alone must KEEP the 1e-12 absolute floor (without it, approx(tiny, rel=1e-12) fails here
# and passes under real pytest). A suite that is green under one runner and red under the other is worse than
# no suite, so this test compares the two implementations directly rather than restating either's rules.
_APPROX_CASES = [
    (1000.0, {}, 1000.0005), (1000.0, {}, 1000.5),
    (13.320160296483188, {"abs": 1e-9}, 13.32016),     # the DXF round-trip that exposed this
    (13.320160296483188, {"abs": 5e-7}, 13.32016),
    (1000.0, {"rel": 1e-3}, 1000.5), (0.0, {"rel": 1e-6, "abs": 1e-3}, 5e-4),
    (1e-15, {"rel": 1e-12}, 2e-15),                    # needs the absolute floor
    (0.0, {"rel": 1e-6}, 1e-13), (0.0, {}, 1e-13), (0.0, {}, 1e-11),
    (2.0, {"abs": 1e-9}, 2.0), (-5.0, {"rel": 1e-6}, -5.000001),
    (1e9, {"abs": 1.0}, 1e9 + 0.5), (1e9, {"rel": 1e-9}, 1e9 + 0.5),
]


def test_the_mini_pytest_shim_agrees_with_real_pytest_on_approx():
    mini = _mini()
    if getattr(pytest, "__file__", "") and "mini_pytest" in pytest.__file__:
        # the offline runner is itself the shim, so there is nothing to compare against; assert the two
        # regimes that actually bit instead, so this is never a test that passes by having nothing to do
        assert not (mini.approx(13.320160296483188, abs=1e-9) == 13.32016), \
            "`abs` alone must suppress the default relative check"
        assert mini.approx(1e-15, rel=1e-12) == 2e-15, "`rel` alone must keep the 1e-12 absolute floor"
        return
    for expected, kw, actual in _APPROX_CASES:
        assert (mini.approx(expected, **kw) == actual) is (pytest.approx(expected, **kw) == actual), \
            f"shim and real pytest disagree on approx({expected!r}, **{kw!r}) == {actual!r}"


def test_the_shim_supports_the_pytest_surface_the_suite_actually_uses():
    """Every pytest attribute the test files reach for must exist in the shim, or the offline runner cannot
    run the suite at all - `mark.parametrize` was missing until v0.28.0 and stopped it dead on the first file
    that used it."""
    import ast
    mini = _mini()
    used = set()
    for name in os.listdir(os.path.join(ROOT_DIR, "tests")):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        with open(os.path.join(ROOT_DIR, "tests", name), encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=name)
        # walk the AST rather than grepping the text: a path or a sentence that mentions
        # "tools/mini_pytest/pytest.py" is not an attribute access, and a regex cannot tell the difference
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            parts, cur = [], node
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name) and cur.id == "pytest":
                used.add(".".join(reversed(parts)))
    assert used, "no pytest usage found; this test would pass vacuously"
    assert "approx" in used and "raises" in used, "the scan missed the two most-used attributes"
    for dotted in sorted(used):
        obj = mini
        for part in dotted.split("."):
            assert hasattr(obj, part), f"tools/mini_pytest lacks pytest.{dotted}"
            obj = getattr(obj, part)


def test_the_shim_names_the_failing_case_of_a_parametrized_test():
    mini = _mini()

    @mini.mark.parametrize("value", [1, 99])
    def inner(value):
        assert value != 99, "boom"

    with pytest.raises(AssertionError, match=r"value=99"):
        inner()
