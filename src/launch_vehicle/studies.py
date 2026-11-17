"""Declared trade studies and multi-design comparison (roadmap R17 and R14).

Neither of these is a method out of the book: they are ways of running the methods that already exist over more
than one vehicle at a time, so that a question like "what does stage-1 diameter cost me" is answered by a table
rather than by editing a YAML file nine times.

A trade study is declared in YAML and names the base design, the parameters to sweep and how to combine them:

    trade_study:
      name: Stage 1 diameter and mixture ratio
      design: config/default_design.yaml
      assumptions: config/engineering_assumptions.yaml
      mode: grid                       # grid (every combination) | one_at_a_time (one parameter off base)
      sweep:
        - path: stages.0.diameter_m
          values: [3.6, 3.8, 4.0, 4.2]
        - path: stages.0.mixture_ratio_OF
          values: [2.3, 2.5, 2.7]

Paths are the same dotted paths the sensitivity studies already use, applied to the unwrapped design
dictionary, so an unknown one is refused rather than silently ignored.

A comparison takes a list of design files instead and runs each as it stands.

Both produce the same shape of result - one row per vehicle, with the outputs that matter for a trade and the
warnings each one raised - because the point of both is the same: put the vehicles side by side and let the
differences show. A case that fails to converge or violates a constraint stays in the table as a failed row;
dropping it would make a sweep look better than it is.
"""
from __future__ import annotations

import itertools
import os
from dataclasses import dataclass, field

from .config_io import load_design
from .convergence import size_vehicle, SizingError
from .validation import InputError


@dataclass
class CaseResult:
    label: str
    parameters: dict = field(default_factory=dict)
    ok: bool = False
    error: str = ""
    outputs: dict = field(default_factory=dict)
    issues: list = field(default_factory=list)
    result: object = None             # the VehicleResult, when it converged

    @property
    def worst_issue(self) -> str:
        for level in ("ERROR", "WARNING"):
            hit = [i for i in self.issues if i.level == level]
            if hit:
                return f"{level}: {hit[0].code}"
        return ""


# The columns a trade study answers with. Everything here is already computed by the sizing loop, so a sweep
# costs one sizing run per case and nothing else.
def outputs_of(res) -> dict:
    return dict(
        glom_kg=res.glom_kg,
        dry_mass_kg=sum(s.m_dry_kg for s in res.stages),
        propellant_kg=sum(s.m_prop_loaded_kg for s in res.stages),
        payload_kg=res.payload_mass_kg,
        payload_fraction=(res.payload_mass_kg / res.glom_kg) if res.glom_kg else float("nan"),
        length_m=res.geometry.total_length if res.geometry else float("nan"),
        max_diameter_m=res.geometry.max_diameter if res.geometry else float("nan"),
        dv_required_mps=res.dv_required_mps,
        dv_achieved_mps=res.dv_achieved_mps,
        liftoff_tw=res.liftoff_tw,
        iterations=res.iterations,
    )


OUTPUT_LABELS = {
    "glom_kg": "GLOM [kg]", "dry_mass_kg": "Dry mass [kg]", "propellant_kg": "Propellant [kg]",
    "payload_kg": "Payload [kg]", "payload_fraction": "Payload fraction [-]", "length_m": "Length [m]",
    "max_diameter_m": "Max diameter [m]", "dv_required_mps": "Delta-v required [m/s]",
    "dv_achieved_mps": "Delta-v achieved [m/s]", "liftoff_tw": "Lift-off T/W [-]", "iterations": "Iterations",
}


def _run_one(design: str, assumptions: str, overrides: dict | None, label: str,
             parameters: dict | None = None) -> CaseResult:
    case = CaseResult(label=label, parameters=dict(parameters or {}))
    try:
        spec = load_design(design, assumptions, overrides=overrides or None)
        res = size_vehicle(spec)
        case.result = res
        case.issues = list(res.issues)
        case.outputs = outputs_of(res)
        case.ok = res.converged and not any(i.level == "ERROR" for i in res.issues)
        if not res.converged:
            case.error = f"did not converge after {res.iterations} iterations"
    except (InputError, SizingError, ValueError, KeyError, OSError) as ex:
        # one unreadable file or one bad parameter must cost its own row and nothing else:
        # a sweep that aborts on case three throws away the two that worked
        case.error = f"{type(ex).__name__}: {ex}"
    return case


# =========================================================================== R17: the trade-study driver
def _cases_from_sweep(sweep: list, mode: str) -> list:
    """(overrides, parameters) for every case the sweep declares."""
    if not sweep:
        return [({}, {})]
    if mode == "grid":
        combos = itertools.product(*[[(s["path"], v) for v in s["values"]] for s in sweep])
        return [({p: v for p, v in c}, {p: v for p, v in c}) for c in combos]
    if mode == "one_at_a_time":
        out = [({}, {"baseline": True})]
        for s in sweep:
            for v in s["values"]:
                out.append(({s["path"]: v}, {s["path"]: v}))
        return out
    raise ValueError(f"unknown trade-study mode '{mode}': use 'grid' or 'one_at_a_time'")


def run_trade_study(declaration: dict, root: str = "") -> dict:
    """Run a declared trade study. `declaration` is the parsed `trade_study:` block."""
    d = declaration.get("trade_study", declaration)
    design = _resolve(d.get("design") or d.get("base"), root)
    assumptions = _resolve(d.get("assumptions") or "config/engineering_assumptions.yaml", root)
    mode = d.get("mode", "grid")
    sweep = d.get("sweep") or []
    for s in sweep:
        if "path" not in s or "values" not in s:
            raise ValueError("every sweep entry needs a 'path' and a list of 'values'")
        if not s["values"]:
            raise ValueError(f"sweep over '{s['path']}' has no values")
    cases = _cases_from_sweep(sweep, mode)
    rows = []
    for i, (ov, params) in enumerate(cases, 1):
        label = ", ".join(f"{k.split('.')[-1]} = {v}" for k, v in params.items()) or "baseline"
        rows.append(_run_one(design, assumptions, ov, label, params))
    return dict(kind="trade_study", name=d.get("name", "Trade study"), design=design,
                assumptions=assumptions, mode=mode, sweep=sweep, cases=rows,
                notes=_study_notes(rows, mode, sweep))


def _resolve(path: str, root: str) -> str:
    if not path:
        raise ValueError("a trade study must name a base design")
    return path if os.path.isabs(path) or not root else os.path.join(root, path)


def _study_notes(rows: list, mode: str, sweep: list) -> list:
    ok = [r for r in rows if r.ok]
    n = [f"{len(rows)} case(s) run in '{mode}' mode over "
         f"{len(sweep)} parameter(s); {len(ok)} converged cleanly."]
    failed = [r for r in rows if not r.ok]
    if failed:
        n.append(f"{len(failed)} case(s) did not: " +
                 "; ".join(f"{r.label} ({r.error or r.worst_issue})" for r in failed[:4]) +
                 ("..." if len(failed) > 4 else "") +
                 ". They are kept in the table rather than dropped, because a sweep that silently discards "
                 "its failures looks better than it is.")
    if ok:
        best = min(ok, key=lambda r: r.outputs["glom_kg"])
        worst = max(ok, key=lambda r: r.outputs["glom_kg"])
        spread = worst.outputs["glom_kg"] / best.outputs["glom_kg"] - 1.0
        n.append(f"Lightest: {best.label} at {best.outputs['glom_kg']:,.0f} kg. Heaviest: {worst.label} at "
                 f"{worst.outputs['glom_kg']:,.0f} kg, {100*spread:.1f} % more. Whether that spread is worth "
                 f"anything depends on how much of it survives the uncertainty in the mass relationships - "
                 f"the Monte-Carlo study puts that at tens of per cent on GLOM.")
    return n


# =========================================================================== R14: multi-design comparison
def compare_designs(design_paths: list, assumptions: str, labels: list | None = None) -> dict:
    """Size several designs as they stand and put them side by side."""
    labels = labels or [os.path.splitext(os.path.basename(p))[0] for p in design_paths]
    rows = [_run_one(p, assumptions, None, lab) for p, lab in zip(design_paths, labels)]
    return dict(kind="comparison", name="Design comparison", designs=list(design_paths), cases=rows,
                notes=_comparison_notes(rows))


def _comparison_notes(rows: list) -> list:
    ok = [r for r in rows if r.ok]
    n = [f"{len(rows)} design(s) compared; {len(ok)} converged cleanly."]
    if len(ok) > 1:
        by_frac = sorted(ok, key=lambda r: -r.outputs["payload_fraction"])
        n.append(f"Best payload fraction: {by_frac[0].label} at "
                 f"{100*by_frac[0].outputs['payload_fraction']:.2f} %, against "
                 f"{100*by_frac[-1].outputs['payload_fraction']:.2f} % for {by_frac[-1].label}. Payload "
                 f"fraction is the right comparison only between vehicles doing the same mission; these are "
                 f"compared as they are declared, and their missions may differ.")
    warned = [r for r in rows if r.worst_issue]
    if warned:
        n.append("Designs raising warnings or errors: " +
                 "; ".join(f"{r.label} ({r.worst_issue})" for r in warned) +
                 ". A comparison table flattens those into one line each; read each design's own report "
                 "before drawing a conclusion from a row.")
    return n


# =========================================================================== shared output
def to_rows(study: dict, outputs: list | None = None) -> tuple:
    """(header, rows) ready for a table, with the parameter columns first."""
    keys = outputs or ["glom_kg", "dry_mass_kg", "payload_kg", "payload_fraction", "length_m",
                       "dv_required_mps", "dv_achieved_mps", "liftoff_tw"]
    param_keys = []
    for c in study["cases"]:
        for k in c.parameters:
            if k not in param_keys and k != "baseline":
                param_keys.append(k)
    header = ["Case"] + [k.split(".")[-1] for k in param_keys] + [OUTPUT_LABELS.get(k, k) for k in keys] \
        + ["Status"]
    rows = []
    for c in study["cases"]:
        r = [c.label] + [c.parameters.get(k, "") for k in param_keys]
        r += [c.outputs.get(k, float("nan")) if c.ok or c.outputs else float("nan") for k in keys]
        r.append("ok" if c.ok else (c.error or c.worst_issue or "failed"))
        rows.append(r)
    return header, rows


def write_csv(study: dict, path: str, outputs: list | None = None) -> str:
    import csv
    header, rows = to_rows(study, outputs)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(["" if isinstance(x, float) and x != x else x for x in r])
    return path


def _cell(x: float) -> str:
    """Format a table value by magnitude.

    A plain '{:,.4g}' turns a 92,975 kg lift-off mass into '9.298e+04', because the comma grouping does not
    apply once %g switches to exponent form - unreadable for exactly the quantity a comparison is read for.
    Masses and velocities get thousands separators and no decimals; fractions keep four significant figures.
    """
    ax = abs(x)
    if ax >= 1000:
        return f"{x:,.0f}"
    if ax >= 1:
        return f"{x:,.4g}"
    return f"{x:.4g}"


# =========================================================================== a standalone page for either
def write_html(study: dict, path: str, figure: str | None = None, outputs: list | None = None) -> str:
    """A small self-contained page for a trade study or a comparison, in the design report's styling."""
    from . import __version__
    from .report import CSS, _e, _tbl
    import base64
    import datetime

    header, rows = to_rows(study, outputs)
    body = [f"<h1>{_e(study.get('name', 'Study'))}</h1>",
            f'<p class="small">{_e(study.get("kind", ""))} &mdash; '
            f'{len(study["cases"])} case(s), MERLIN {_e(__version__)}, '
            f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}</p>']
    if study.get("kind") == "trade_study":
        body.append(_tbl(["Setting", "Value"], [
            ["Base design", _e(study["design"])], ["Assumptions", _e(study["assumptions"])],
            ["Mode", _e(study["mode"])],
            ["Swept", "<br>".join(f"{_e(s['path'])}: {_e(str(s['values']))}" for s in study["sweep"])]]))
    else:
        body.append(_tbl(["Designs compared"], [[_e(d)] for d in study.get("designs", [])]))
    if figure and os.path.exists(figure):
        with open(figure, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        body.append(f'<div class="fig"><img src="data:image/png;base64,{b64}"></div>')
    disp = []
    for r in rows:
        disp.append([_cell(x) if isinstance(x, float) and x == x
                     else ("" if isinstance(x, float) else _e(str(x))) for x in r])
    body.append(_tbl(header, disp, numeric=tuple(range(1, len(header) - 1))))
    body.append('<p class="small">' + "<br>".join(_e(n) for n in study.get("notes", [])) + "</p>")
    body.append('<div class="banner note">Every row here is a full sizing run with the same relationships, '
                'assumptions and warnings as a single-design report, and carries the same uncertainty: the '
                'mass-estimating relationships are fits to historical vehicles, and the Monte-Carlo study puts '
                'the spread on GLOM at tens of per cent. A trade whose spread is smaller than that is telling '
                'you about the model, not about the vehicles. Read each design\'s own report before acting on '
                'a row.</div>')
    html = ("<!DOCTYPE html><html lang=en><head><meta charset=utf-8>"
            f"<title>{_e(study.get('name', 'Study'))}</title>"
            '<meta name=viewport content="width=device-width,initial-scale=1">'
            f"<style>{CSS}</style></head><body><div class=page>{''.join(body)}</div></body></html>")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
