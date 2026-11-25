"""Local web GUI for the sizing tool - stdlib only, no CDN, no framework, works offline.

Why a GUI at all: a design has a few hundred inputs, each with units, a description, a source and a provenance
class, and the interesting work is changing a handful of them and seeing what moves. On the command line that is a
YAML edit and a re-run; here it is a click, and the baseline stays on screen next to the new result.

What it is NOT: a second calculation engine. Every number the browser shows came out of the same Python model the
CLI runs, serialised to JSON. The YAML files remain the source of truth - the GUI sends *overrides* on top of a
file and tells you exactly which ones are active, and 'Save as YAML' writes them back out so a run is reproducible
from the command line.

Run it with:   python tools/gui.py            (then open the printed http://127.0.0.1:8000)
"""
from __future__ import annotations
import base64
import io
import json
import os
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from .config_io import load_design, load_yaml_annotated, ConfigError
from .convergence import size_vehicle, SizingError
from .validation import InputError
from . import __version__

from .paths import ROOT                                   # noqa: E402
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gui_static")
DEFAULT_ASSUMPTIONS = os.path.join(ROOT, "config", "engineering_assumptions.yaml")
#: where a design can be loaded from. "designs" is where the GUI SAVES, and is listed first so a person's own
#: work is at the top of the list rather than below two dozen shipped files.
SEARCH_DIRS = ("designs", "config", "examples", "validation")
SAVE_DIR = os.path.join(ROOT, "designs")
#: YAML files that live in the searched directories but are LIBRARIES, not designs. They would otherwise be
#: offered in the Open dialog and fail to load as a vehicle. One line per new library file.
NOT_DESIGNS = ("engineering_assumptions", "engine_database", "launch_sites", "my_library")
GROUP_LABELS = {"designs": "My designs", "config": "Starting points", "examples": "Examples",
                "validation": "Check cases (real vehicles)"}

#: The analyses, grouped so the dialog reads as three short lists instead of eleven loose checkboxes.
STUDY_GROUPS = {
    "trajectory": "How it flies", "ascent_optimum": "How it flies", "stability": "How it flies",
    "loads": "What the flight does to it", "structure": "What the flight does to it",
    "payload_env": "What the flight does to it",
    "performance": "What it is worth", "staging": "What it is worth", "cost": "What it is worth",
    "uncertainty": "What it is worth", "ballistics": "What it is worth",
}
STUDY_GROUP_ORDER = ["How it flies", "What the flight does to it", "What it is worth"]


def _combination_map():
    """The propellant-combination lookup the page uses to follow a pick through to fuel and oxidiser."""
    try:
        import yaml
        from .config_io import _Loader
        from . import gui_meta
        from .config_io import assumptions_doc
        # with your own combinations, so picking one carries its fuel, oxidiser and mixture ratio too
        return gui_meta.combination_map(assumptions_doc(DEFAULT_ASSUMPTIONS))
    except Exception:                                        # noqa: BLE001
        return {}


def _engine_map():
    """What picking each real engine or motor writes into the design, for the page to apply at the dropdown."""
    try:
        from . import gui_meta
        return gui_meta.engine_map()
    except Exception:                                        # noqa: BLE001
        return {}


def _infer_field(code, message):
    from .validation import infer_field
    return infer_field(code, message)


def _launch_site_map():
    """The launch-site lookup the page uses to follow a pick through to latitude and the inclination floor."""
    try:
        from . import gui_meta
        return gui_meta.launch_site_map()
    except Exception:                                        # noqa: BLE001
        return {}


#: CAD formats that need no third-party library, so they are always on offer. The exact-solid
#: formats come from cad_kernel.KERNEL_FORMATS and appear only when that kernel is installed.
CAD_FORMATS = {
    "dxf": "Inboard profile, layered, 2-D",
    "stl": "Faceted mesh, no units in the file",
    "obj": "Faceted mesh with part names",
    "3mf": "Faceted mesh with units and part names",
}

#: the optional analyses, in the order they are offered. `needs` names a study that must run first.
# The key on the left is the browser's vocabulary and also the key the RESULT comes back under, which is not
# always the key the engine takes to ask for the work - see ENGINE_STUDY_KEY below.
STUDIES = [
    ("trajectory", "Ascent trajectory", None),
    ("loads", "Ground and flight loads", "trajectory"),
    ("structure", "Shell stress and buckling", "loads"),
    # stability is computed from a converged trajectory rather than on its own, so asking for it alone used to
    # run nothing at all and show no tab: the dependency is declared here so ticking it brings the trajectory
    ("stability", "Aerodynamics, stability and control", "trajectory"),
    ("payload_env", "Payload environment", "trajectory"),
    ("ascent_optimum", "Pitch-programme optimisation", None),
    ("ballistics", "Solid motor internal ballistics", None),
    ("performance", "Payload capability curves", None),
    ("cost", "Cost", None),
    ("uncertainty", "Uncertainty (Monte Carlo)", None),
    ("staging", "Staging optimum", None),
]


# The engine's own name for a study, where it differs from the key the result arrives under. The ascent
# optimisation is asked for as "optimise_ascent" and comes back as "ascent_optimum"; sending the result key
# to main._studies matched nothing, so the checkbox ran silently and produced no tab.
ENGINE_STUDY_KEY = {"ascent_optimum": "optimise_ascent"}


def _unlink(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _blank_required(overrides) -> list:
    """The paths the user has left empty, in the order the form shows them."""
    return [k for k, v in (overrides or {}).items() if v is None]


def _pretty(path: str) -> str:
    """A dotted input path as something to say in a sentence."""
    return "'" + str(path).replace("_", " ").replace(".", " > ") + "'"


def _json_safe(obj):
    """Replace NaN and +/-Infinity with null, recursively, so the browser can parse what we send.

    Python's json.dumps writes bare `NaN` and `Infinity`, which are NOT JSON: JSON.parse rejects the whole
    document. One such value therefore does not spoil one field, it loses the entire response - which is how
    eight of the shipped designs (Saturn V, Falcon 9, Titan II, Vega C among them) came to fail in the GUI
    with "is not valid JSON" while sizing perfectly well from Python.

    The values themselves are legitimate results, not mistakes. `control.trim_deflection_deg` returns NaN when
    a stage has no gimbal authority about the arm in question, and infinity when no deflection balances the
    aerodynamic moment. Both mean "there is no number here", which in JSON is null; the summary carries a note
    saying which of the two it was, since null alone cannot tell them apart.
    """
    if isinstance(obj, float):
        return None if (obj != obj or obj in (float("inf"), float("-inf"))) else obj
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def _expand_studies(want) -> set:
    """Add whatever a requested study depends on, so a person can tick 'structure' and get what it needs."""
    want = set(want or ())
    for _ in range(4):
        for key, _label, needs in STUDIES:
            if key in want and needs:
                want.add(needs)
    return want


def _engine_studies(want) -> set:
    """Translate the browser's study keys into the names main._studies gates on."""
    return {ENGINE_STUDY_KEY.get(k, k) for k in want}
_LOCK = threading.Lock()                      # one sizing run at a time; the model is not re-entrant-safe
_STATE = {}                                   # run token -> {"res":..., "figs":{...}, "design":..., "assump":...}


# --------------------------------------------------------------------------- helpers
def _safe_design_path(path):
    """Resolve a design path, refusing anything outside the project tree (this server binds to localhost, but a
    path check costs nothing and keeps a stray '../../etc/passwd' from being read)."""
    p = os.path.abspath(os.path.join(ROOT, path)) if not os.path.isabs(path) else os.path.abspath(path)
    if not p.startswith(ROOT + os.sep) or not p.endswith((".yaml", ".yml")):
        raise ConfigError(f"refusing to read '{path}': design files must be .yaml inside the project directory")
    if not os.path.exists(p):
        raise ConfigError(f"no such design file: {path}")
    return p


def list_designs():
    """Every design the GUI can open, grouped so the check cases are findable as check cases."""
    out = []
    for d in SEARCH_DIRS:
        full = os.path.join(ROOT, d)
        if not os.path.isdir(full):
            continue
        for f in sorted(os.listdir(full)):
            if not f.endswith((".yaml", ".yml")) or f.startswith(NOT_DESIGNS):
                continue
            rel = os.path.join(d, f).replace(os.sep, "/")
            name, desc = os.path.splitext(f)[0], ""
            # A file is a DESIGN only if it describes a mission. Trade-study declarations and other library
            # files live in the same directories and used to be offered here, then failed on Open with a
            # message about undocumented bare values, which says nothing about why the file was listed at
            # all. This reads the RAW document, because a file that is not a design is also under no
            # obligation to carry the annotation every design input needs - testing it with the annotated
            # reader would throw, and the file would stay in the list.
            try:
                import yaml as _y
                from .config_io import _Loader as _L
                with open(os.path.join(full, f), encoding="utf-8") as fh:
                    probe = _y.load(fh, Loader=_L)
                if not isinstance(probe, dict) or "mission" not in probe:
                    continue
            except Exception:                                    # noqa: BLE001
                continue                                         # unreadable: not something to offer either
            try:
                _, meta, _ = load_yaml_annotated(os.path.join(full, f))
                name = meta.get("name") or name
                desc = meta.get("description") or ""
            except Exception:                                    # noqa: BLE001
                pass
            out.append({"path": rel, "group": d, "group_label": GROUP_LABELS.get(d, d),
                        "name": name, "description": desc, "file": f})
    return out


def _group_of(path):
    if path.startswith("mission."):
        return "Mission"
    if path.startswith(("vehicle.", "fairing.")):
        return "Vehicle, payload, fairing"
    if path.startswith("boosters."):
        return "Boosters"
    if path.startswith("stages."):
        try:
            return f"Stage {int(path.split('.')[1]) + 1}"
        except (IndexError, ValueError):
            return "Stages"
    if path.startswith("constraints."):
        return "Constraints"
    return "Assumptions and MER coefficients"


def design_inputs(design_path, assump_path, describe: bool = False):
    """The annotated input register of a design.

    With describe=True each row also carries the things a person needs to answer it rather than decode it: a
    human label, the list of valid choices where the field has one, and the section and topic it belongs in.
    """
    spec = load_design(design_path, assump_path)
    items = []
    for r in spec.inputs_register:
        v = r["value"]
        items.append({"path": r["path"], "value": v, "units": r["units"], "description": r["description"],
                      "source": r["source"], "provenance": r["provenance"], "group": _group_of(r["path"]),
                      "type": ("list" if isinstance(v, list) else
                               "bool" if isinstance(v, bool) else
                               "number" if isinstance(v, (int, float)) else
                               "null" if v is None else "text"),
                      # Is this the user's to supply? `provenance: user` says the number is a requirement
                      # rather than the method's, and a requirement that the FILE itself leaves null is
                      # optional by construction - every one of those says "null = ..." in its description
                      # (no apogee for a circular orbit, no adapter mass means use the MER). So a required
                      # field is a user field the file fills in, and that is the set a new design asks for
                      # and the set the page can then chase. Nothing new to annotate, and it cannot go stale.
                      "required": r["provenance"] == "user" and v is not None})
    # Every stage gets a type row even when its file does not spell one out, because `stage_type` defaults to
    # liquid in config_io and that default IS an effective input - and because without the row there is no
    # control to switch the stage with. It is inserted next to the stage's other top-level values so it reads
    # where the user expects it, and tagged `assumed` since the file did not say.
    declared = {it["path"] for it in items}
    for s in spec.stages:
        # Stage.index is 1-based (it is what the reports call "Stage 1"); register paths are 0-based.
        ix = s.index - 1
        path = f"stages[{ix}].stage_type"
        if path in declared:
            continue
        row = {"path": path, "value": s.stage_type, "units": "-", "description": "liquid | solid",
               "source": "Not stated in the design file; liquid is the default",
               "provenance": "assumed", "group": _group_of(path), "type": "text", "required": False}
        at = max((i for i, it in enumerate(items) if it["path"].startswith(f"stages[{ix}].")), default=-1)
        items.insert(at + 1, row) if at >= 0 else items.append(row)
    # The characteristic velocity is read only when the engine is sized from the book relations, and no
    # shipped design states it. Without a row for it, choosing that method produced an error naming an input
    # the page had no field for.
    declared = {it["path"] for it in items}
    # The way to orbit of the simulated ascent: newer than most design files, so it gets a row whether or not the
    # file has one, next to the other trajectory settings.
    for key, val, units in (("parking_altitude_m", None, "m"), ("ascent_profile", "auto", "-")):
        path = f"mission.{key}"
        if path in declared:
            continue
        meta = _creatable_meta(["mission", key])
        row = {"path": path, "value": val, "units": units, "description": meta["d"],
               "source": "Not stated in the design file; " + ("automatic" if val else "185 km") + " is the default",
               "provenance": "assumed", "group": _group_of(path), "type": "text" if val else "null", "required": False}
        at = max((i for i, it in enumerate(items) if it["path"] in ("mission.vertical_rise_s", "mission.atmosphere_model")),
                 default=max((i for i, it in enumerate(items) if it["path"].startswith("mission.")), default=-1))
        items.insert(at + 1, row) if at >= 0 else items.append(row)
    for s in spec.stages:
        ix = s.index - 1
        path = f"stages[{ix}].engine.cstar_mps"
        if s.is_solid or path in declared or f"stages[{ix}].engine.geometry_method" not in declared:
            continue
        row = {"path": path, "value": getattr(s.engine, "cstar_mps", None), "units": "m/s",
               "description": "Delivered characteristic velocity c*. Read only when the engine dimensions come "
                              "from the book relations (Table 8.12), which size the throat from it",
               "source": "Not stated in the design file", "provenance": "user", "group": _group_of(path),
               "type": "null", "required": False}
        at = next(i for i, it in enumerate(items) if it["path"] == f"stages[{ix}].engine.geometry_method")
        items.insert(at + 1, row)

    out = {"name": spec.name, "n_stages": len(spec.stages), "items": items}
    if describe:
        import yaml as _yaml
        from .config_io import _Loader
        from . import gui_meta
        try:
            from .config_io import assumptions_doc
            assump = assumptions_doc(assump_path, design_path)      # with your own entries, so they are offered
        except Exception:
            assump = None
        out["items"] = gui_meta.describe_inputs(items, assump)
        out["open_sections"] = gui_meta.open_sections_for(out["items"])
        # which fields a New design clears and which it only flags, for the stages this design has
        out["new_design"] = gui_meta.new_design_plan(out["items"])
        out["writable"] = is_writable_design(design_path)
        # The stage count is not a leaf in the file - it is the length of the `stages:` list - so the page
        # cannot read it off an input row. It is reported here, with its bounds, so the control that changes
        # it and the module that enforces them cannot disagree.
        from . import stage_count as _sc
        out["stage_count"] = {"n": len(spec.stages), "min": _sc.MIN_STAGES, "max": _sc.MAX_STAGES}
        # Whether the design HAS strap-ons is the presence of a block, not a field, so the page cannot read
        # it off an input row either. How many there are stays an ordinary editable field.
        from . import strap_ons as _so
        import yaml as _y
        from .config_io import _Loader as _L
        try:
            with open(design_path, encoding="utf-8") as _fh:
                out["boosters"] = {"kind": _so.current_kind(_y.load(_fh, Loader=_L)),
                                   "kinds": list(_so.KINDS)}
        except Exception:
            out["boosters"] = {"kind": None, "kinds": list(_so.KINDS)}
        try:
            _d, meta, _r = load_yaml_annotated(design_path)
            out["meta"] = {"name": meta.get("name", ""), "description": meta.get("description", "")}
        except Exception:
            out["meta"] = {"name": spec.name, "description": ""}
    return out


def _stage_json(s):
    return {"index": s.index, "name": s.name, "type": s.stage_type, "dv_mps": s.dv_mps, "isp_eff_s": s.isp_eff_s,
            "mass_ratio": s.mass_ratio, "m_prop_loaded_kg": s.m_prop_loaded_kg, "m_dry_kg": s.m_dry_kg,
            "m_ignition_kg": s.m_ignition_kg, "m_burnout_kg": s.m_burnout_kg, "s": s.structural_factor_s,
            "burn_time_s": s.burn_time_s, "tw_ignition": s.tw_ignition, "tw_burnout": s.tw_burnout,
            "accel_max_g": s.accel_max_g, "length_m": s.length_m, "thrust_vac_N": s.thrust_vac_N,
            "thrust_sl_N": s.thrust_sl_N, "mdot_kgs": s.mdot_kgs, "dv_check_mps": s.dv_check_mps,
            "components": {k: v for k, v in sorted((s.components or {}).items(), key=lambda kv: -kv[1])},
            "motor_info": s.motor_info or {}, "warnings": list(s.warnings or [])}


def result_json(res, token):
    g = res.geometry
    return {
        "token": token,
        "name": res.spec.name,
        "converged": res.converged, "status": res.status, "iterations": res.iterations, "residual": res.residual,
        "glom_kg": res.glom_kg, "payload_kg": res.payload_mass_kg, "paf_kg": res.paf_mass_kg,
        "fairing_kg": res.fairing_mass_kg, "dv_required_mps": res.dv_required_mps,
        "dv_achieved_mps": res.dv_achieved_mps, "length_m": g.total_length, "max_diameter_m": g.max_diameter,
        "max_span_m": g.max_span_m, "liftoff_thrust_N": res.liftoff_thrust_N, "liftoff_tw": res.liftoff_tw,
        "payload_fraction": res.payload_mass_kg / res.glom_kg if res.glom_kg else 0.0,
        "allocation": list(res.allocation),
        "budget": [{"name": l.name, "value_mps": l.value_mps, "category": l.category,
                    "in_total": l.in_total, "source": l.source} for l in res.budget.lines],
        "budget_total": res.budget.total_mps,
        "stages": [_stage_json(s) for s in res.stages],
        "boosters": (None if res.boosters is None else {
            "name": res.boosters.name, "n_total": res.boosters.n_total, "kind": res.boosters.kind,
            "m_prop_each_kg": res.boosters.m_prop_each_kg, "m_inert_each_kg": res.boosters.m_inert_each_kg,
            "m_total_kg": res.boosters.m_total_kg, "burn_time_s": res.boosters.burn_time_s,
            "s": res.boosters.structural_factor_s,
            "phases": [{"name": p.name, "duration_s": p.duration_s, "isp_eff_s": p.isp_eff_s,
                        "thrust_N": p.thrust_eff_N, "dv_mps": p.dv_mps, "m_start_kg": p.m_start_kg,
                        "m_end_kg": p.m_end_kg}
                       for p in res.stages[res.boosters.attach_stage - 1].phases]}),
        # `field`/`options` ride along so the Checks tab can offer the same "go to this input" jump and
        # one-click fixes a hard refusal does. A warning that names its field is as actionable as an error.
        "issues": [{"level": i.level, "code": i.code, "message": i.message,
                    "field": getattr(i, "field", None) or _infer_field(i.code, i.message),
                    "options": getattr(i, "options", None) or None} for i in res.issues],
        "ledger": [{"stage": i.stage, "group": i.group, "name": i.name, "mass_kg": i.mass_kg, "z_m": i.z_m,
                    "kind": i.kind, "shape": i.shape, "source": i.source} for i in res.ledger],
        "events": [{k: e[k] for k in ("event", "mass_kg", "z_cm_m", "z_cm_over_L", "J_roll", "J_pitch")}
                   for e in (res.mass_properties or {}).get("events", [])],
        "segments": [{"stage": s.stage, "kind": s.kind, "name": s.name, "z0": s.z0, "z1": s.z1,
                      "length": s.length, "d_bot": s.d_bot, "d_top": s.d_top} for s in g.segments],
    }


def _figures(res, outdir):
    """Draw the drawings every run has. The study charts are added by _run_studies."""
    import matplotlib
    matplotlib.use("Agg")
    from . import schematic_2d
    os.makedirs(outdir, exist_ok=True)
    figs = {}
    figs["vehicle_png"] = os.path.join(outdir, "vehicle_schematic.png")
    schematic_2d.draw_vehicle(res, figs["vehicle_png"], None)
    figs["mass_distribution_png"] = os.path.join(outdir, "mass_distribution.png")
    schematic_2d.draw_mass_distribution(res, figs["mass_distribution_png"], None)
    for s in res.stages:
        k = f"stage{s.index}_png"
        figs[k] = os.path.join(outdir, f"stage{s.index}_schematic.png")
        schematic_2d.draw_stage(res, s.index, figs[k], None)
    return figs


def _run_studies(design_path, assump_path, spec, res, outdir, figs, want, n_mc=200, applied_opt=None):
    """Run the optional analyses the browser asked for, reusing the CLI's own code path.

    The GUI must not grow a second way of computing anything, so this calls main._studies - the same function
    `--all-studies` uses - and inherits its behaviour, including that one study failing never stops the rest.
    """
    if not want:
        return {}
    from .main import _studies
    return _studies(design_path, assump_path, spec, res, outdir, figs,
                    _engine_studies(_expand_studies(want)), n_mc, False, applied_opt=applied_opt)


def _study_payload(study, workdir) -> dict:
    """A trade study or comparison as JSON, with its CSV and HTML written beside the run.

    `studies.to_rows` already decides the columns and their order for the CLI and the report, so the browser
    is handed the same table rather than a second opinion about what matters.
    """
    from . import studies as _st
    header, rows = _st.to_rows(study)
    token = os.urandom(6).hex()
    outdir = os.path.join(workdir, "studies", token)
    os.makedirs(outdir, exist_ok=True)
    stem = _re.sub(r"[^A-Za-z0-9_.-]+", "_", study.get("name") or study.get("kind") or "study").strip("_")
    csv_path = _st.write_csv(study, os.path.join(outdir, f"{stem}.csv"))
    html_path = _st.write_html(study, os.path.join(outdir, f"{stem}.html"))
    return {
        "kind": study.get("kind"), "name": study.get("name"), "token": token,
        "header": header,
        # NaN is not JSON, and a failed case legitimately has no numbers: it becomes null and the page
        # shows a dash rather than the string "NaN"
        "rows": [[None if isinstance(x, float) and x != x else x for x in r] for r in rows],
        "notes": study.get("notes") or [],
        "n_cases": len(study.get("cases") or []),
        "n_ok": sum(1 for c in (study.get("cases") or []) if c.ok),
        "csv": os.path.basename(csv_path), "html": os.path.basename(html_path),
    }


def trade_study_files() -> list:
    """Every YAML in the project carrying a `trade_study:` block, for the browser to choose from."""
    import yaml as _yaml
    from .config_io import _Loader
    out = []
    for d in ("examples", "designs", "config"):
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            if not name.endswith((".yaml", ".yml")):
                continue
            p = os.path.join(base, name)
            try:
                with open(p, encoding="utf-8") as fh:
                    doc = _yaml.load(fh, Loader=_Loader)
            except Exception:                                    # noqa: BLE001
                continue
            blk = (doc or {}).get("trade_study")
            if isinstance(blk, dict):
                out.append({"path": _rel(p),
                            "name": blk.get("name") or name,
                            "n_sweeps": len(blk.get("sweep") or [])})
    return out


def _trim_note(trim_deg) -> str:
    """Why the trim deflection is not a number, when it is not. Null on the wire cannot say which case it was."""
    if trim_deg != trim_deg:
        return ("no gimbal authority about this arm, so no steady deflection can be computed - check the "
                "stage's gimballed fraction and the gimbal station")
    if trim_deg in (float("inf"), float("-inf")):
        return "no gimbal deflection balances the aerodynamic moment at the worst point"
    return ""


def _study_summary(extras):
    """One line per study for the browser, so the UI can show what ran without shipping the whole object."""
    out = {}
    tr = extras.get("trajectory")
    if tr is not None:
        # `status` says WHY, and a trajectory that did not converge needs it: without it the tab showed a
        # vehicle flying up and crashing - burnout altitude -0.22 km, max-q 4,833 kPa - as though those were
        # results, with "Converged: false" as one unremarkable table row among four.
        # `attempted` is a separate question from `converged`: an ascent that was not tried carries no figures.
        att = bool(getattr(tr, "attempted", True))
        out["trajectory"] = {"converged": bool(getattr(tr, "converged", False)),
                             "attempted": att,
                             "status": getattr(tr, "status", None),
                             "max_q_kPa": ((max(tr.q_Pa) / 1e3) if getattr(tr, "q_Pa", None) else None)
                                          if att else None,
                             "burnout_h_km": (getattr(tr, "burnout_h_m", 0.0) / 1e3) if att else None,
                             "burnout_v_mps": getattr(tr, "burnout_v_mps", 0.0) if att else None,
                             "gravity_loss_mps": getattr(tr, "gravity_loss_mps", 0.0) if att else None,
                             "drag_loss_mps": getattr(tr, "drag_loss_mps", 0.0) if att else None,
                             "propulsion_loss_mps": getattr(tr, "propulsion_loss_mps", 0.0) if att else None,
                             "steering_loss_mps": getattr(tr, "steering_loss_mps", 0.0) if att else None}
        if att and getattr(tr, "profile", ""):
            out["trajectory"]["profile_why"] = tr.profile_why
            if tr.converged:
                out["trajectory"].update(
                    margin_mps=tr.margin_mps, propellant_left_kg=tr.propellant_left_kg,
                    second_burn_dv_mps=tr.second_burn_dv_mps or None,
                    equivalent_loss_mps=tr.equivalent_loss_mps, budget_loss_mps=tr.budget_loss_mps or None)
            why = () if tr.converged else tuple(n for n in tr.notes if n.startswith(("the flight shown", "why it did not")))
            if why:
                out["trajectory"]["diagnosis"] = list(why)
            out["trajectory"]["notes"] = [n for n in tr.notes if n not in why and not n.startswith(("drag ", "reference area", "atmosphere", "way to orbit"))]
        ins = getattr(tr, "insertion", None)
        if ins:
            # a dict and a list: the generic quantity table skips both and the tab draws them itself
            out["trajectory"]["orbit"] = ins
        if att and getattr(tr, "t_s", None):
            from . import trajectory as _tj
            out["trajectory"]["timeline"] = _tj.timeline(tr)
        dt = getattr(tr, "drag_table", None)
        if att and dt:
            # a list, so the generic quantity table skips it and the Trajectory tab draws it as its own table
            out["trajectory"]["peak_cd"] = dt["peak_cd"]
            out["trajectory"]["drag_rows"] = dt["rows"]
            out["trajectory"]["drag_shape"] = [f"{b['count']} x {b['name']}: {b['length_m']:.1f} m long, "
                                               f"{b['diameter_m']:.2f} m diameter" for b in dt["bodies"]]
    ld = extras.get("loads")
    if ld:
        cases = [c for k, c in ld.items() if hasattr(c, "stations") and c.stations]
        if cases:
            w = max(cases, key=lambda c: abs(c.max_moment_Nm))
            st = max(w.stations, key=lambda s: abs(s.moment_Nm))
            out["loads"] = {"governing": w.name, "moment_kNm": w.max_moment_Nm / 1e3, "z_m": st.z_m,
                            "profiles": ld.get("wind_profiles_considered") or []}
    sc = extras.get("structure")
    if sc and sc.get("shells"):
        t = max(sc["shells"], key=lambda sh: sh.t_required_m)
        out["structure"] = {"thickest_mm": 1e3 * t.t_required_m, "shell": t.name,
                            "driver": t.governing_driver, "mass_ratio": sc.get("mass_ratio")}
    pe = extras.get("payload_env")
    if pe is not None and getattr(pe, "rows", None):
        out["payload_env"] = {"axial_g": pe.design_axial_g, "lateral_g": pe.design_lateral_g,
                              "event": pe.governing_axial_event}
    co = extras.get("cost")
    if co is not None:
        from . import cost as _cost
        out["cost"] = _cost.as_json(co)
    ctl = extras.get("control")
    if ctl is not None and getattr(ctl, "points", None):
        w = ctl.worst("controllability")
        out["control"] = {"controllability": w.controllability, "t_s": w.t_s, "trim_deg": w.trim_deg,
                          "trim_note": _trim_note(w.trim_deg)}
    unc = extras.get("uncertainty")
    if unc:
        out["uncertainty"] = {k: unc.get(k) for k in ("p05_glom_kg", "p50_glom_kg", "p95_glom_kg", "n")
                              if k in unc}
    ao = extras.get("ascent_optimum")
    if ao:
        best = ao.get("best") or {}
        out["ascent_optimum"] = {k: v for k, v in dict(
            speed_gain_mps=ao.get("speed_gain_mps"), payload_gain_kg=ao.get("payload_gain_kg"),
            handover_km=best["handover_h_m"] / 1e3 if best.get("handover_h_m") else None,
            vertical_rise_s=best.get("vertical_rise_s"), stopped_by=(ao.get("binding") or {}).get("detail"),
            binding=ao.get("binding")).items() if v is not None}
    return out


def run_sizing(design_path, assump_path, overrides, workdir, token, studies=(), n_mc=200):
    """Size a design with overrides, run whichever analyses were asked for, and remember it all under `token`."""
    with _LOCK:
        outdir = os.path.join(workdir, token)
        spec = load_design(design_path, assump_path, overrides or None)
        # If the design asks to be optimised, the allocation is replaced BEFORE sizing, so everything
        # downstream - mass, geometry, loads, drawing, cost - describes the split that is reported.
        from .optimization import apply_optimum
        spec, opt_note = apply_optimum(spec)
        res = size_vehicle(spec)
        figs = _figures(res, outdir)
        extras = _run_studies(design_path, assump_path, spec, res, outdir, figs, studies, n_mc,
                              applied_opt=(opt_note or {}).get("result"))
        _STATE[token] = {"res": res, "figs": figs, "design": design_path, "assump": assump_path,
                         "overrides": dict(overrides or {}), "dir": outdir, "extras": extras}
        # keep the last few runs only, so a long session does not grow without bound
        for old in list(_STATE)[:-6]:
            _STATE.pop(old, None)
        out = result_json(res, token)
        out["studies"] = sorted(extras)
        out["study_summary"] = _study_summary(extras)
        # An analysis can legitimately produce nothing - internal ballistics on an all-liquid vehicle, for
        # instance. The CLI says so on the console; without this the GUI just showed no tab, which is
        # indistinguishable from the request having been ignored.
        out["studies_empty"] = sorted(k for k in _expand_studies(studies) if k not in extras)
        out["figures"] = sorted(k for k, v in figs.items() if v and os.path.exists(v))
        # the page needs the applied split so the panel can show the numbers the result was actually
        # computed from, rather than the ones the user typed and the optimiser then replaced
        if opt_note:
            out["optimised"] = {k: v for k, v in opt_note.items() if k != "result"}
        return out


def apply_overrides(raw: dict, overrides: dict | None, what: str = "save", sources: dict | None = None) -> dict:
    """Write the GUI's overrides into an ANNOTATED design document, in place.

    Annotated, not unwrapped, so every value keeps its units, description, source and provenance. An
    overridden leaf is re-tagged `t: user` and its source records that a person set it in the GUI - the
    alternative, inheriting the old source, would attribute a hand-entered number to the book.
    """
    from . import user_library as _ul
    for dotted, value in (overrides or {}).items():
        node = raw
        # the register spells stage paths stages[0]...; accept that as well as stages.0...
        keys = _re.sub(r"\[(\d+)\]", r".\1", str(dotted)).split(".")
        if keys[0] in _ul.ASSUMPTION_BLOCKS:
            # A changed LIBRARY value is not the design's to hold in place, but the design must keep it, or the
            # saved file would size a different vehicle. It goes into the design's `library:` block as a copy of
            # the leaf with the new value, which load_design merges over the shipped entry.
            _library_override(raw, keys, value, (sources or {}).get(dotted), what, dotted)
            continue
        try:
            _creatable_parent(raw, keys)
            for k in keys[:-1]:
                node = node[int(k)] if isinstance(node, list) else node[k]
            if isinstance(node, dict) and keys[-1] not in node and _creatable_leaf(keys):
                # an optional input the file leaves out and the page still offers: written as a full leaf
                meta = _creatable_meta(keys)
                node[keys[-1]] = {"v": None, "u": meta["u"], "d": meta["d"], "s": "", "t": "user"}
            leaf = node[int(keys[-1])] if isinstance(node, list) else node[keys[-1]]
        except (KeyError, IndexError, ValueError, TypeError) as e:
            raise ConfigError(f"cannot {what}: unknown parameter path '{dotted}'") from e
        if isinstance(leaf, dict) and "v" in leaf:
            leaf["v"] = value
            # Not every value the page carries was typed by a person. The delta-v split can be chosen by the
            # optimiser, and saving that as `t: user, s: "Set in the GUI"` would put a numerical search's
            # answer in the file under the user's name - in a tool whose whole register rests on provenance
            # being accurate. Where the page says where a value came from, that is what gets written.
            src = (sources or {}).get(dotted)
            if isinstance(src, dict) and src.get("s"):
                leaf["s"] = str(src["s"])
                leaf["t"] = str(src.get("t") or "assumed")
            else:
                leaf["t"] = "user"
                leaf["s"] = "Set in the GUI"
        else:
            node[keys[-1]] = value
    return raw


from .config_io import (creatable_leaf as _creatable_leaf, creatable_meta as _creatable_meta,   # noqa: E402
                        creatable_parent as _creatable_parent)


def _library_override(raw, keys, value, src, what, dotted):
    from .config_io import assumptions_doc, _Loader                    # noqa: F401
    import tempfile
    import yaml as _yaml
    # the leaf as the design currently sees it, so its units and description travel with the new value
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as fh:
        _yaml.safe_dump({"library": raw.get("library") or {}}, fh)
        tmp = fh.name
    try:
        doc = assumptions_doc(DEFAULT_ASSUMPTIONS, tmp)
    finally:
        _unlink(tmp)
    node = doc
    try:
        for k in keys:
            node = node[k]
    except (KeyError, TypeError) as e:
        raise ConfigError(f"cannot {what}: unknown parameter path '{dotted}'") from e
    if not (isinstance(node, dict) and "v" in node):
        raise ConfigError(f"cannot {what}: '{dotted}' is not a single value")
    leaf = dict(node)
    leaf["v"] = value
    if isinstance(src, dict) and src.get("s"):
        leaf["s"], leaf["t"] = str(src["s"]), str(src.get("t") or "assumed")
    else:
        leaf["s"], leaf["t"] = "Set in the GUI", "user"
    tgt = raw.setdefault("library", {})
    for k in keys[:-1]:
        tgt = tgt.setdefault(k, {})
    tgt[keys[-1]] = leaf


class DesignExists(ConfigError):
    """A Save-as would land on a file that is already there. The page offers to replace it."""

    def __init__(self, path):
        super().__init__(f"'{path}' already exists")
        self.path = path


#: Where a structural edit parks its result until the user names it. A stage changing from liquid to solid is
#: not an override - it adds and removes keys - so it has to be written out and reloaded. It goes here rather
#: than into designs/ so that an abandoned experiment never shows up in the user's own list, and the leading
#: dot keeps it out of the flat listing that builds the Open dialog.
DRAFT_DIR = os.path.join(SAVE_DIR, ".drafts")
#: how many drafts to keep before the oldest are swept, so a long session does not accumulate them forever
DRAFT_KEEP = 20


def is_draft(path) -> bool:
    try:
        return os.path.abspath(path).startswith(os.path.abspath(DRAFT_DIR) + os.sep)
    except TypeError:
        return False


def is_writable_design(path) -> bool:
    """May plain Save overwrite this file in place?

    Only files the user saved themselves, which is everything under designs/. The shipped starting points,
    examples and check cases are reference material: a design opened from one of those is saved as a NEW file
    in designs/ instead, so pressing Save can never quietly rewrite config/default_design.yaml or a validation
    case that other runs are compared against.

    A draft is not writable either. A draft has no name the user chose, so Save on one has to ask for one -
    otherwise the result of converting a stage would be filed under a hidden scratch name and lost.
    """
    try:
        p = os.path.abspath(path)
    except TypeError:
        return False
    if is_draft(p):
        return False
    return p.startswith(os.path.abspath(SAVE_DIR) + os.sep) and p.endswith((".yaml", ".yml"))


def write_draft(doc: dict, stem: str, header: str = "") -> str:
    """Write an annotated design document to the draft directory and prove it loads. Returns its rel path."""
    import yaml as _yaml
    os.makedirs(DRAFT_DIR, exist_ok=True)
    safe = _safe_name(stem) or "draft"
    path = os.path.join(DRAFT_DIR, f"{safe}-{int(time.time() * 1000) % 1_000_000_000}.yaml")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# Working draft written by the launch_vehicle GUI. Save it to keep it.\n")
        if header:
            fh.write("".join(f"# {line}\n" for line in header.splitlines()))
        _yaml.safe_dump(doc, fh, sort_keys=False, width=220, allow_unicode=True)
    try:
        load_design(path, DEFAULT_ASSUMPTIONS)               # never hand back a draft that will not load
    except Exception:
        os.unlink(path)
        raise
    _sweep_drafts()
    return _rel(path)


def _sweep_drafts():
    try:
        files = [os.path.join(DRAFT_DIR, f) for f in os.listdir(DRAFT_DIR) if f.endswith(".yaml")]
    except OSError:
        return
    for p in sorted(files, key=os.path.getmtime)[:-DRAFT_KEEP]:
        try:
            os.unlink(p)
        except OSError:
            pass


def save_design(base_path, overrides, name, description="", filename=None, target=None, replace=False,
                override_sources=None):
    """Write the current configuration out as a complete, annotated design file of its own.

    The overrides are applied to the ANNOTATED document, not the unwrapped one, so the saved file keeps every
    value's units, description, source and provenance. An overridden leaf is re-tagged `t: user` and its source
    records that a person set it in the GUI - the alternative, inheriting the old source, would attribute a
    hand-entered number to the book.

    Three ways in, and they are the three things the buttons mean:

    * `target` names a file under designs/ to rewrite in place. That is plain Save on a design already bound
      to a file of its own: same path, no dialog, no second copy.
    * no target, and the name is free: a new file in designs/. That is the first Save, and Save as.
    * no target, and the name is taken: refused with DesignExists, so the page can ask before replacing
      someone's earlier work. `replace=True` is that answer.

    `base_path` is always the document the values are read from, which on a plain Save is the bound file
    itself - so Save is a genuine round trip and not a re-derivation from whatever the design began life as.
    """
    import yaml as _yaml
    from .config_io import _Loader
    if target is not None:
        path = _safe_design_path(target)
        if not is_writable_design(path):
            raise ConfigError(
                f"'{os.path.relpath(path, ROOT)}' is a shipped file, not one of your designs, so Save will "
                "not overwrite it. Use Save as to keep your version under its own name in designs/.")
        stem = os.path.splitext(os.path.basename(path))[0]
    else:
        stem = _safe_name(filename or name)
        if not stem:
            raise ConfigError("give the configuration a name before saving")
        path = os.path.join(SAVE_DIR, stem + ".yaml")
        if os.path.exists(path) and not replace:
            raise DesignExists(_rel(path))
    with open(base_path, encoding="utf-8") as fh:
        raw = _yaml.load(fh, Loader=_Loader)
    apply_overrides(raw, overrides, sources=override_sources)
    # a design that uses an entry of your own carries a copy of it, so it opens on a machine without your library
    from .user_library import embed_used as _embed
    _embed(raw)
    raw["meta"] = {"name": name or stem,
                   "description": description or f"Saved from the GUI, based on "
                                                 f"{os.path.relpath(base_path, ROOT)}"}
    os.makedirs(SAVE_DIR, exist_ok=True)
    # Write to a temporary file beside the target, prove it loads, and only then move it into place. The
    # previous order - write, then validate - left a broken file on disk whenever validation failed, so a
    # part-filled new design both reported an error AND created the file it was complaining about.
    tmp = path + ".part"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(f"# Saved from the launch_vehicle GUI.\n"
                     f"# Based on {os.path.relpath(base_path, ROOT)}; "
                     f"{len(overrides or {})} value(s) changed and re-tagged t: user.\n")
            _yaml.safe_dump(raw, fh, sort_keys=False, width=220, allow_unicode=True)
        load_design(tmp, DEFAULT_ASSUMPTIONS)            # prove it loads before anything is kept
    except ConfigError as ex:
        _unlink(tmp)
        blanks = _blank_required(overrides)
        if blanks:
            raise ConfigError(
                f"Not saved: {len(blanks)} field(s) are still empty, and a design file that cannot be loaded "
                f"would be worse than none. Fill in {_pretty(blanks[0])}"
                + (f" and {len(blanks) - 1} other(s)" if len(blanks) > 1 else "") + ", then save again.",
                field=blanks[0]) from ex
        raise
    except Exception:
        _unlink(tmp)
        raise
    os.replace(tmp, path)
    rel = _rel(path)
    return {"path": rel, "name": name or stem, "n_overrides": len(overrides or {}),
            # the page binds to this and shows it, so plain Save knows where to write next time
            "bound": True, "writable": is_writable_design(path)}


import re as _re

_SAFE = _re.compile(r"[^A-Za-z0-9_.-]+")


def _rel(path) -> str:
    """A path as the page shows it: relative to the project, with forward slashes. On Windows a folder on another
    drive has no relative path at all (os.path.relpath raises), which the GitHub build machine hit with the
    project on D: and temporary files on C:; such a path is shown in full instead of failing the save."""
    try:
        return os.path.relpath(path, ROOT).replace(os.sep, "/")
    except ValueError:
        return os.path.abspath(path).replace(os.sep, "/")


def _safe_name(name: str) -> str:
    """A file name from a person's title: no separators, no traversal, no surprises."""
    stem = _SAFE.sub("_", str(name or "").strip()).strip("._-")
    return stem[:80]


# --------------------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = f"MERLIN/{__version__}"
    workdir = os.path.join(ROOT, "outputs", "gui")

    def log_message(self, fmt, *args):            # keep the console readable; errors are reported in the UI
        pass

    # ---- plumbing
    def _send(self, code, body, ctype="application/json", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(_json_safe(body)).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _err(self, ex, code=400):
        known = isinstance(ex, (ConfigError, InputError, SizingError))
        # An error that knows which input caused it, and how to fix it, should say so: the page turns `field`
        # into a jump and each option into a button, instead of leaving the user to read a sentence and work
        # out which of a few hundred inputs it means.
        self._send(code, {"error": f"{ex}" if known else f"{type(ex).__name__}: {ex}",
                          "field": getattr(ex, "field", None) or _infer_field(None, str(ex)),
                          "options": getattr(ex, "options", None) or None,
                          "trace": traceback.format_exc() if not known else None})

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _state(self, q):
        t = (q.get("token") or [""])[0]
        if t not in _STATE:
            raise ConfigError("no such run - size the design first")
        return _STATE[t]

    # ---- routes
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path in ("/", "/index.html"):
                with open(os.path.join(STATIC, "index.html"), "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            if u.path == "/api/designs":
                return self._send(200, {"designs": list_designs(), "version": __version__,
                                        "assumptions": os.path.relpath(DEFAULT_ASSUMPTIONS, ROOT),
                                        "groups": [{"key": k, "label": GROUP_LABELS.get(k, k)}
                                                   for k in SEARCH_DIRS],
                                        "studies": [{"key": k, "label": lab, "needs": n,
                                                     "group": STUDY_GROUPS.get(k, "Other")}
                                                    for k, lab, n in STUDIES],
                                        "study_groups": STUDY_GROUP_ORDER,
                                        "combinations": _combination_map(),
                                        "engines": _engine_map(),
                                        "trade_studies": trade_study_files(),
                                        "launch_sites": _launch_site_map()})
            if u.path == "/api/library":
                from . import user_library as _ul
                return self._send(200, {"schema": _ul.schema_for_gui(), "library": _ul.listing(),
                                        "file": _rel(_ul.USER_LIBRARY_PATH)})
            if u.path == "/api/design":
                p = _safe_design_path((q.get("path") or ["config/default_design.yaml"])[0])
                return self._send(200, design_inputs(p, DEFAULT_ASSUMPTIONS, describe=True))
            if u.path == "/api/cad":
                st = self._state(q)
                fmt = (q.get("fmt") or ["dxf"])[0].lower()
                from . import cad_export, cad_kernel
                if fmt not in CAD_FORMATS and fmt not in cad_kernel.KERNEL_FORMATS:
                    return self._send(400, {"error": f"unknown CAD format '{fmt}'"})
                if fmt not in CAD_FORMATS and not cad_kernel.available():
                    return self._send(409, {"error": f"{fmt.upper()} needs a geometry kernel: "
                                                     + cad_kernel.status()["reason"]})
                paths = cad_export.export_all(st["res"], os.path.join(st["dir"], "cad"),
                                              kernel=False)
                if fmt not in CAD_FORMATS:
                    paths.update(cad_kernel.export_solids(st["res"], os.path.join(st["dir"], "cad"),
                                                          formats=(fmt,)))
                with open(paths[fmt], "rb") as f:
                    body = f.read()
                return self._send(200, body, "application/octet-stream",
                                  {"Content-Disposition": f'attachment; filename="vehicle.{fmt}"'})
            if u.path == "/api/model_checks":
                # Everything v0.15-v0.16 measured about the model itself, in one place: how reliable this
                # vehicle's engine clusters are (R24), how well the engine-mass relation does against real
                # engines (R20) and how the solid-stage relations do against flown stages (R18). The first
                # depends on the sized vehicle; the other two are properties of the libraries.
                st = self._state(q)
                from . import engine_db, reliability as rl, solid_inert as si
                out = {}
                try:
                    out["reliability"] = rl.analyse(st["res"])
                except Exception as ex:                      # noqa: BLE001
                    out["reliability_error"] = f"{type(ex).__name__}: {ex}"
                try:
                    mc = engine_db.mer_check()
                    out["engine_mer"] = {k: mc[k] for k in
                                         ("n", "mean", "median", "sd", "mean_abs", "n_light", "verdict",
                                          "calibration_factor", "calibrated", "source", "rows", "excluded")
                                         if k in mc}
                except Exception as ex:                      # noqa: BLE001
                    out["engine_mer_error"] = f"{type(ex).__name__}: {ex}"
                try:
                    out["solid_relations"] = si.summary_rows()
                    out["solid_dataset_n"] = len(si.DATASET)
                except Exception as ex:                      # noqa: BLE001
                    out["solid_error"] = f"{type(ex).__name__}: {ex}"
                return self._send(200, out)
            if u.path == "/api/cad_formats":
                from . import cad_export, cad_kernel
                st = cad_kernel.status()
                out = [{"fmt": f, "label": lab, "exact": False, "available": True}
                       for f, lab in CAD_FORMATS.items()]
                out += [{"fmt": f, "label": lab, "exact": True, "available": st["available"]}
                        for f, lab in cad_kernel.KERNEL_FORMATS.items()]
                return self._send(200, {
                    "formats": out, "kernel": st,
                    "facet_deficit": 1.0 - cad_export.faceted_volume_ratio(
                        cad_export.DEFAULT_FACETS)})
            if u.path == "/api/design_yaml":
                st = self._state(q)
                import yaml as _yaml
                from .config_io import _Loader
                with open(st["design"], encoding="utf-8") as f:
                    raw = _yaml.load(f, Loader=_Loader)
                return self._send(200, _yaml.safe_dump(raw, sort_keys=False, width=220, allow_unicode=True),
                                  "text/yaml; charset=utf-8",
                                  {"Content-Disposition": 'attachment; filename="design.yaml"'})
            if u.path == "/api/figure":
                st = self._state(q)
                key = (q.get("key") or ["vehicle_png"])[0]
                path = st["figs"].get(key)
                if not path or not os.path.exists(path):
                    return self._send(404, {"error": f"no figure '{key}' for this run"})
                with open(path, "rb") as f:
                    return self._send(200, f.read(), "image/png")
            if u.path == "/api/report":
                st = self._state(q)
                from . import report as report_mod
                htm = report_mod.build_html(st["res"], st["figs"],
                                            os.path.relpath(st["design"], ROOT), os.path.relpath(st["assump"], ROOT),
                                            extras=st.get("extras") or {})
                dl = (q.get("download") or ["0"])[0] == "1"
                extra = {"Content-Disposition": 'attachment; filename="design_report.html"'} if dl else None
                return self._send(200, htm, "text/html; charset=utf-8", extra)
            if u.path == "/api/workbook":
                st = self._state(q)
                from . import reporting
                ex = st.get("extras") or {}
                p = os.path.join(st["dir"], "launch_vehicle_sizing_workbook.xlsx")
                reporting.write_workbook(st["res"], p, st["figs"], design_path=st["design"],
                                         loads=ex.get("loads"), ascent_opt=ex.get("ascent_optimum"),
                                         structure=ex.get("structure"))
                with open(p, "rb") as f:
                    return self._send(200, f.read(),
                                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                      {"Content-Disposition": 'attachment; filename="launch_vehicle_sizing_workbook.xlsx"'})
            if u.path == "/api/yaml":
                st = self._state(q)
                return self._send(200, _overrides_yaml(st), "text/yaml; charset=utf-8",
                                  {"Content-Disposition": 'attachment; filename="gui_overrides.yaml"'})
            return self._send(404, {"error": "not found"})
        except Exception as ex:                              # noqa: BLE001 - the UI shows whatever went wrong
            return self._err(ex)

    def do_POST(self):
        u = urlparse(self.path)
        try:
            b = self._body()
            if u.path == "/api/size":
                p = _safe_design_path(b.get("path") or "config/default_design.yaml")
                token = b.get("token") or os.urandom(6).hex()
                return self._send(200, run_sizing(p, DEFAULT_ASSUMPTIONS, b.get("overrides") or {},
                                                  self.workdir, token, b.get("studies") or (),
                                                  int(b.get("mc_samples") or 200)))
            if u.path == "/api/library":
                # add, change or remove an entry of the personal library (user_library)
                from . import user_library as _ul
                act = b.get("action") or "add"
                try:
                    if act == "remove":
                        done = _ul.remove(b.get("kind"), b.get("name"))
                        return self._send(200, {"removed": done, "library": _ul.listing(),
                                                "combinations": _combination_map(), "schema": _ul.schema_for_gui()})
                    _ul.add(b.get("kind"), b.get("name"), b.get("values") or {}, b.get("source"),
                            b.get("provenance") or "user", replace=bool(b.get("replace")))
                except _ul.LibraryError as ex:
                    return self._send(400, {"error": str(ex), "field": ex.field})
                return self._send(200, {"added": b.get("name"), "kind": b.get("kind"), "library": _ul.listing(),
                                        "combinations": _combination_map(), "schema": _ul.schema_for_gui()})
            if u.path == "/api/cost":
                # the Cost tab's settings change the estimate, not the vehicle, so nothing is sized again
                st = self._state({"token": [b.get("token") or ""]})
                from . import cost as _cost
                try:
                    year = int(float(b.get("year") or 2010))
                    if not 1960 <= year <= 2100:
                        raise _cost.CostInputError("the cost year must be between 1960 and 2100", "year")
                    est = _cost.estimate(st["res"], year=year, inputs=b.get("inputs") or {})
                except (ValueError, OverflowError) as ex:
                    return self._send(400, {"error": str(ex), "cost_field": getattr(ex, "field", None)})
                st["extras"]["cost"] = est
                return self._send(200, _cost.as_json(est))
            if u.path == "/api/save":
                base = _safe_design_path(b.get("path") or "config/default_design.yaml")
                try:
                    return self._send(200, save_design(base, b.get("overrides") or {}, b.get("name") or "",
                                                       b.get("description") or "", b.get("filename"),
                                                       target=b.get("target"), replace=bool(b.get("replace")),
                                                       override_sources=b.get("override_sources") or None))
                except DesignExists as ex:
                    # 409, and flagged, so the page can offer to replace instead of just reporting a failure
                    return self._send(409, {"error": str(ex), "exists": True, "path": ex.path})
            if u.path == "/api/stage_type":
                # Changing a stage from liquid to solid adds and removes keys, so it cannot be an override:
                # the document is transformed and parked as a draft, which the page then loads.
                import yaml as _yaml
                from .config_io import _Loader
                from . import stage_type as _st
                base = _safe_design_path(b.get("path") or "config/default_design.yaml")
                idx, to = int(b.get("index", 0)), str(b.get("to") or "")
                with open(base, encoding="utf-8") as fh:
                    doc = _yaml.load(fh, Loader=_Loader)
                # A design being filled in has deliberate blanks - that is what New leaves behind - and a
                # document with a blank required field does not load, so a draft carrying them could not be
                # proved good. The blanks are therefore left OUT of the draft and handed back for the page to
                # re-apply as overrides once it has loaded, which keeps both promises: the draft on disk
                # always loads, and the user's half-finished brief survives changing a stage's type.
                ov = b.get("overrides") or {}
                blanks = {k: v for k, v in ov.items() if v is None}
                apply_overrides(doc, {k: v for k, v in ov.items() if v is not None},
                                what="change the stage type")
                note = _st.convert_stage(doc, idx, to)
                if not note["changed"]:
                    return self._send(200, {"path": b.get("path"), "note": note, "draft": False,
                                            "keep_overrides": blanks})
                stem = (doc.get("meta", {}) or {}).get("name") or "design"
                rel = write_draft(doc, f"{stem}-stage{idx + 1}-{to}", note["note"])
                return self._send(200, {"path": rel, "note": note, "draft": True,
                                        "keep_overrides": blanks})
            if u.path == "/api/stage_count":
                # How many stages the vehicle has was never an input: it was the length of the `stages:` list
                # in the file, so the browser could only ever edit the stages it was handed. Adding one adds a
                # whole annotated sub-document and moves three count-dependent fields with it, so like the
                # liquid/solid switch it is a document transformation parked as a draft, not an override.
                import yaml as _yaml
                from .config_io import _Loader
                from . import stage_count as _sc
                base = _safe_design_path(b.get("path") or "config/default_design.yaml")
                with open(base, encoding="utf-8") as fh:
                    doc = _yaml.load(fh, Loader=_Loader)
                # Same contract as /api/stage_type: a half-filled brief's blanks cannot go into a draft,
                # because a document with a blank required field does not load and the draft could not be
                # proved good. They are handed back for the page to re-apply once it has loaded.
                ov = b.get("overrides") or {}
                blanks = {k: v for k, v in ov.items() if v is None}
                apply_overrides(doc, {k: v for k, v in ov.items() if v is not None},
                                what="change the number of stages")
                try:
                    note = _sc.set_count(doc, b.get("count"))
                except _sc.StageCountError as ex:
                    return self._send(400, {"error": ex.message, "field": ex.field})
                if not note["changed"]:
                    return self._send(200, {"path": b.get("path"), "note": note, "draft": False,
                                            "keep_overrides": blanks})
                stem = (doc.get("meta", {}) or {}).get("name") or "design"
                rel = write_draft(doc, f"{stem}-{note['now']}stage", note["note"])
                return self._send(200, {"path": rel, "note": note, "draft": True,
                                        "keep_overrides": blanks})
            if u.path == "/api/boosters":
                # Strap-ons were editable only on a design that already declared them: the model has
                # supported them since Ariane 5 and Delta IV Heavy became check cases, but the browser can
                # only edit what the file contains. Adding the block is a document transformation, so it
                # takes the same draft route as the stage count and the liquid/solid switch.
                import yaml as _yaml
                from .config_io import _Loader
                from . import strap_ons as _so
                base = _safe_design_path(b.get("path") or "config/default_design.yaml")
                with open(base, encoding="utf-8") as fh:
                    doc = _yaml.load(fh, Loader=_Loader)
                ov = b.get("overrides") or {}
                blanks = {k: v for k, v in ov.items() if v is None}
                apply_overrides(doc, {k: v for k, v in ov.items() if v is not None},
                                what="change the strap-on boosters")
                try:
                    note = _so.set_boosters(doc, b.get("kind"))
                except _so.StrapOnError as ex:
                    return self._send(400, {"error": ex.message, "field": ex.field})
                if not note["changed"]:
                    return self._send(200, {"path": b.get("path"), "note": note, "draft": False,
                                            "keep_overrides": blanks})
                stem = (doc.get("meta", {}) or {}).get("name") or "design"
                tag = note["now"] or "no"
                rel = write_draft(doc, f"{stem}-{tag}-boosters", note["note"])
                return self._send(200, {"path": rel, "note": note, "draft": True,
                                        "keep_overrides": blanks})
            if u.path == "/api/sensitivity":
                # The one-at-a-time studies and the configuration comparison. They run in the CLI by
                # default and reach the workbook, but had no way in from the browser at all - so the
                # question "what is this design most sensitive to" could only be asked on a terminal.
                from . import sensitivity as _sens
                p = _safe_design_path(b.get("path") or "config/default_design.yaml")
                with _LOCK:
                    spec = load_design(p, DEFAULT_ASSUMPTIONS, b.get("overrides") or None)
                    base = size_vehicle(spec)
                    rows = _sens.standard_studies(p, DEFAULT_ASSUMPTIONS, base)
                    comp = _sens.configuration_comparison(p, DEFAULT_ASSUMPTIONS, base)
                return self._send(200, {"baseline_glom_kg": base.glom_kg,
                                        "studies": rows, "configurations": comp})
            if u.path == "/api/families":
                # Launch vehicle families (R37). A family is a folder with a family.yaml in it; the browser
                # could open one design at a time but had no way to see the variants as a family, which is
                # the one configuration where the shared-core limitation is measurable against data.
                from . import families as _fam
                want = b.get("name")
                try:
                    if not want:
                        found = _fam.discover(ROOT)
                        return self._send(200, {"families": [
                            {"slug": f.slug, "name": f.name, "note": " ".join(f.note.split()),
                             "reference": f.reference,
                             "base": os.path.relpath(f.base_path, ROOT).replace(os.sep, "/"),
                             "variants": [
                                 {"key": v.key, "label": v.label, "is_reference": v.is_reference,
                                  "overrides": v.overrides,
                                  "n_boosters": v.overrides.get("boosters.n_total"),
                                  "published_payload_kg": v.published_kg("payload_kg"),
                                  "published_glom_kg": v.published_kg("glom_kg"),
                                  "published_source": v.published_source("glom_kg")}
                                 for v in f.variants]} for f in found]})
                    f = _fam.find(ROOT, want)
                except _fam.FamilyError as ex:
                    return self._send(400, {"error": str(ex)})
                with _LOCK:
                    sized = _fam.size_family(f, DEFAULT_ASSUMPTIONS)
                    pinned = _fam.pinned_family(f, DEFAULT_ASSUMPTIONS) if b.get("pinned") else []
                return self._send(200, {
                    "slug": f.slug, "name": f.name, "note": " ".join(f.note.split()),
                    "reference": f.reference,
                    "base": os.path.relpath(f.base_path, ROOT).replace(os.sep, "/"),
                    # each variant is openable with no new machinery: it IS the base design plus overrides,
                    # which is exactly what /api/design and /api/size already take
                    "sized": [{"key": r["key"], "label": r["label"], "is_reference": r["is_reference"],
                               "glom_kg": None if r["result"] is None else r["result"].glom_kg,
                               "length_m": None if r["result"] is None else r["result"].geometry.total_length,
                               "liftoff_tw": None if r["result"] is None else r["result"].liftoff_tw,
                               "published_glom_kg": r["published_glom_kg"],
                               "glom_err": r["glom_err"], "error": r["error"],
                               "overrides": r["variant"].overrides} for r in sized],
                    "pinned": [{"key": r["key"], "label": r["label"], "is_reference": r["is_reference"],
                                "n_boosters": r["n_boosters"], "payload_kg": r["payload_kg"],
                                "glom_kg": r["glom_kg"], "liftoff_tw": r["liftoff_tw"],
                                "published_payload_kg": r["published_payload_kg"],
                                "payload_err": r["payload_err"], "flyable": r["flyable"],
                                "reason": r["reason"]} for r in pinned],
                    "caveat": "The two tables err in OPPOSITE directions from the same cause: a real family "
                              "shares one core, sized for its largest member, and this tool never carries a "
                              "core oversized for the mission being flown. Sizing each variant on its own "
                              "gives each a minimal core, so the small variants come out too light; pinning "
                              "the reference core pins one still lighter than the real shared core, so the "
                              "small variants get too much payload. docs/ACCURACY.md 6b.3 and 6b.5."})
            if u.path == "/api/architecture":
                # Pin the stages, change the strap-on count (method M102). The GUI could compare whole
                # designs but not one design's own architecture variants, which is the trade a launcher
                # family is actually built on - one core, several booster counts.
                from . import architecture as _arch
                p = _safe_design_path(b.get("path") or "config/default_design.yaml")
                counts = b.get("counts")
                if counts is not None:
                    try:
                        counts = sorted({int(c) for c in counts})
                    except (TypeError, ValueError):
                        return self._send(400, {"error": "counts must be whole numbers",
                                                "field": "boosters.n_total"})
                    if not counts or counts[0] < 0:
                        return self._send(400, {"error": "give one or more booster counts, none negative",
                                                "field": "boosters.n_total"})
                with _LOCK:
                    spec = load_design(p, DEFAULT_ASSUMPTIONS, b.get("overrides") or None)
                    if b.get("size_core"):
                        rows = []
                        for n in (counts or [spec.boosters.n_total if spec.boosters else 1]):
                            try:
                                r = _arch.core_for_boosters(spec, n, b.get("ground_lit"))
                                rows.append({"n_boosters": n, "flyable": True, "glom_kg": r.glom_kg,
                                             "core_prop_kg": r.stages[0].m_prop_loaded_kg,
                                             "payload_kg": r.payload_mass_kg,
                                             "liftoff_tw": r.liftoff_tw,
                                             "is_reference": bool(spec.boosters
                                                                  and n == spec.boosters.n_total)})
                            except (SizingError, InputError, ValueError,
                                    _arch.ArchitectureError) as ex:
                                rows.append({"n_boosters": n, "flyable": False, "reason": str(ex)})
                        return self._send(200, {"mode": "size_core", "payload_kg": spec.payload_mass_kg,
                                                "rows": rows})
                    base = size_vehicle(spec)
                    try:
                        pv = _arch.pin(base)
                    except _arch.ArchitectureError as ex:
                        return self._send(400, {"error": str(ex), "field": "boosters.n_total"})
                    out = _arch.booster_count_sweep(pv, counts=counts)
                rows = [{"n_boosters": r.n_boosters, "n_ground_lit": r.n_ground_lit, "flyable": r.flyable,
                         "payload_kg": r.payload_kg, "glom_kg": r.glom_kg, "liftoff_tw": r.liftoff_tw,
                         "dv_achieved_mps": r.dv_achieved_mps, "dv_required_mps": r.dv_required_mps,
                         "dv_limited_payload_kg": r.dv_limited_payload_kg,
                         "is_reference": r.is_reference, "reason": r.reason} for r in out]
                return self._send(200, {
                    "mode": "pinned", "booster_label": pv.booster_label,
                    "reference": {"n_boosters": pv.reference_n_boosters,
                                  "n_ground_lit": pv.reference_n_ground_lit,
                                  "payload_kg": base.payload_mass_kg, "glom_kg": base.glom_kg},
                    "rows": rows,
                    # the GUI must not present this as a capability curve without the measured bias
                    "caveat": "The stages are NOT re-sized: this is what this core lifts in another booster "
                              "architecture, not the vehicle a designer would draw for it. Measured against "
                              "the two launcher families that publish a figure for several counts of one core, "
                              "pinning over-predicts the smaller variants by 19-52 % (docs/ACCURACY.md 6b.5). "
                              "One booster either side of the design's own count is the useful range."})
            if u.path == "/api/trade":
                # A declared sweep, run through the same studies module the `trade` subcommand uses.
                import yaml as _yaml
                from .config_io import _Loader
                from . import studies as _st
                p = _safe_design_path(b.get("path") or "")
                with open(p, encoding="utf-8") as fh:
                    decl = _yaml.load(fh, Loader=_Loader)
                if not (decl or {}).get("trade_study"):
                    return self._send(400, {"error": f"{os.path.relpath(p, ROOT)} has no 'trade_study:' block, "
                                                     f"so there is no sweep to run"})
                with _LOCK:
                    study = _st.run_trade_study(decl, root=ROOT)
                return self._send(200, _study_payload(study, self.workdir))
            if u.path == "/api/compare":
                from . import studies as _st
                paths = [_safe_design_path(x) for x in (b.get("paths") or [])]
                if len(paths) < 2:
                    return self._send(400, {"error": "pick at least two designs to compare"})
                with _LOCK:
                    study = _st.compare_designs(paths, DEFAULT_ASSUMPTIONS)
                return self._send(200, _study_payload(study, self.workdir))
            if u.path == "/api/report_pdf":
                # The report is already written as HTML for the run; this converts that same file, so the
                # PDF can never disagree with what the Report tab is showing.
                from . import report as _rep
                st = self._state({"token": [b.get("token", "")]})
                # The Report tab builds its HTML in memory and never writes it, so build the SAME document
                # here and convert that file. Converting anything else would risk a PDF that disagrees with
                # what the tab is showing.
                os.makedirs(st["dir"], exist_ok=True)
                html = os.path.join(st["dir"], "design_report.html")
                with open(html, "w", encoding="utf-8") as fh:
                    fh.write(_rep.build_html(st["res"], st["figs"], os.path.relpath(st["design"], ROOT),
                                             os.path.relpath(st["assump"], ROOT),
                                             extras=st.get("extras") or {}))
                pdf, note = _rep.to_pdf(html, os.path.join(st["dir"], "design_report.pdf"))
                if not pdf:
                    return self._send(400, {"error": note or (
                        "no PDF converter found on this machine. The report converts with Chrome or "
                        "wkhtmltopdf; without either, the HTML report is the deliverable - open it in any "
                        "browser and print it, using the A4 print stylesheet it carries.")})
                with open(pdf, "rb") as fh:
                    return self._send(200, fh.read(), "application/pdf",
                                      {"Content-Disposition": 'attachment; filename="design_report.pdf"'})
            if u.path == "/api/hazard":
                # Where the jettisoned hardware lands. The design has to be sized and flown first, because the
                # separation states come out of the trajectory - there is no shortcut from the YAML to a map.
                from . import hazard as _hz, debris as _dbr, trajectory as _tj
                p = _safe_design_path(b.get("path") or "config/default_design.yaml")
                with _LOCK:
                    spec = load_design(p, DEFAULT_ASSUMPTIONS, b.get("overrides") or None)
                    lat = spec.mission["site_latitude_deg"]
                    lon = spec.mission.get("site_longitude_deg")
                    if b.get("longitude_deg") is not None:
                        lon = float(b["longitude_deg"])
                    opts = _hz.azimuth_options(spec.mission["inclination_deg"], lat)
                    if not opts:
                        return self._send(200, {
                            "error": (f"inclination {spec.mission['inclination_deg']:.2f} deg is not reachable "
                                      f"from latitude {lat:.2f} deg by a direct ascent, so there is no launch "
                                      f"azimuth and no ground track to draw"),
                            "azimuth_options": []})
                    az = float(b["azimuth_deg"]) if b.get("azimuth_deg") is not None else opts[0]["azimuth_deg"]
                    disp = _dbr.Dispersion(
                        sep_speed_frac=float(b.get("sep_speed_frac", _dbr.Dispersion.sep_speed_frac)),
                        sep_gamma_deg=float(b.get("sep_gamma_deg", _dbr.Dispersion.sep_gamma_deg)),
                        cross_half_width_m=(None if b.get("cross_half_width_m") in (None, "")
                                            else float(b["cross_half_width_m"])))
                    res = size_vehicle(spec)
                    from . import aerodynamics as _aero
                    traj = _tj.fly_design(res, drag=_aero.model_from_config(
                        spec.mission.get("aerodynamics"), root=os.path.dirname(p)), **_tj.flight_options(spec))
                    if not traj.converged:
                        # An ascent that did not close has no trustworthy separation states, and inventing drop
                        # zones from it would be the worst kind of plausible output.
                        return self._send(200, {
                            "error": "the ascent trajectory did not converge, so the separation states it would "
                                     "give are not trustworthy and no impact points are reported",
                            "trajectory_status": traj.status, "azimuth_options": opts})
                    a = _hz.areas(res, traj, lat, lon, az, dispersion=disp)
                payload = _hz.to_payload(a)
                payload["azimuth_options"] = opts
                payload["trajectory"] = {"downrange_m": traj.downrange_m, "burnout_h_m": traj.burnout_h_m,
                                         "burnout_v_mps": traj.burnout_v_mps}
                return self._send(200, payload)
            if u.path == "/api/hazard_export":
                from . import hazard as _hz, debris as _dbr, trajectory as _tj
                p = _safe_design_path(b.get("path") or "config/default_design.yaml")
                fmt = (b.get("format") or "kml").lower()
                if fmt not in ("kml", "geojson"):
                    return self._send(400, {"error": "format must be kml or geojson"})
                with _LOCK:
                    spec = load_design(p, DEFAULT_ASSUMPTIONS, b.get("overrides") or None)
                    lat = spec.mission["site_latitude_deg"]
                    lon = spec.mission.get("site_longitude_deg")
                    if b.get("longitude_deg") is not None:
                        lon = float(b["longitude_deg"])
                    if lon is None:
                        return self._send(400, {"error": "no launch-site longitude, so there is nothing to "
                                                         "place on a map: pick a site from the library or type "
                                                         "a longitude"})
                    opts = _hz.azimuth_options(spec.mission["inclination_deg"], lat)
                    az = float(b["azimuth_deg"]) if b.get("azimuth_deg") is not None else (
                        opts[0]["azimuth_deg"] if opts else 90.0)
                    disp = _dbr.Dispersion(
                        sep_speed_frac=float(b.get("sep_speed_frac", _dbr.Dispersion.sep_speed_frac)),
                        sep_gamma_deg=float(b.get("sep_gamma_deg", _dbr.Dispersion.sep_gamma_deg)),
                        cross_half_width_m=(None if b.get("cross_half_width_m") in (None, "")
                                            else float(b["cross_half_width_m"])))
                    res = size_vehicle(spec)
                    from . import aerodynamics as _aero
                    traj = _tj.fly_design(res, drag=_aero.model_from_config(
                        spec.mission.get("aerodynamics"), root=os.path.dirname(p)), **_tj.flight_options(spec))
                    if not traj.converged:
                        return self._send(400, {"error": "the ascent did not converge, so there are no drop "
                                                         "zones to export", "trajectory_status": traj.status})
                    a = _hz.areas(res, traj, lat, lon, az, dispersion=disp)
                stem = _re.sub(r"[^A-Za-z0-9_.-]+", "_", (res.spec.name or "design")).strip("_") or "design"
                os.makedirs(self.workdir, exist_ok=True)
                name = f"{stem}_hazard_areas.{'kml' if fmt == 'kml' else 'geojson'}"
                out = os.path.join(self.workdir, name)
                if fmt == "kml":
                    _hz.write_kml(a, out)
                else:
                    _hz.write_geojson(a, out)
                # The file is left in the work directory as well as returned, so a GUI session and a
                # command-line run leave the same artefacts behind in the same place.
                with open(out, "rb") as fh:
                    mime = ("application/vnd.google-earth.kml+xml" if fmt == "kml" else "application/geo+json")
                    return self._send(200, fh.read(), mime,
                                      {"Content-Disposition": f'attachment; filename="{name}"'})
            if u.path == "/api/optimize":
                p = _safe_design_path(b.get("path") or "config/default_design.yaml")
                with _LOCK:
                    from .optimization import optimize_dv_split
                    spec = load_design(p, DEFAULT_ASSUMPTIONS, b.get("overrides") or None)
                    obj = b.get("objective") or getattr(spec, "optimise_objective", "glom") or "glom"
                    out = optimize_dv_split(spec, objective=obj)
                if not out.get("success"):
                    # This used to come back 200 with a 1e12 "optimum", which the page then wrote into the
                    # user's design as the best split and reported as about a trillion kilograms lighter.
                    # A search that found nothing is a failure and has to arrive as one.
                    return self._send(400, {"error": out.get("note", "no feasible allocation was found"),
                                            "field": "vehicle.dv_fractions"})
                return self._send(200, out)
            return self._send(404, {"error": "not found"})
        except Exception as ex:                              # noqa: BLE001
            return self._err(ex)


def _overrides_yaml(st):
    """The active overrides as a YAML fragment, so a GUI session can be reproduced from the command line."""
    lines = ["# Overrides set in the GUI, on top of:",
             f"#   design:      {os.path.relpath(st['design'], ROOT)}",
             f"#   assumptions: {os.path.relpath(st['assump'], ROOT)}",
             "# Apply them with load_design(design, assumptions, overrides) or paste the values into the design file.",
             "overrides:"]
    if not st["overrides"]:
        lines.append("  {}   # none - the run used the design file as it is")
    for k, v in sorted(st["overrides"].items()):
        lines.append(f"  {k}: {json.dumps(v)}")
    return "\n".join(lines) + "\n"


def serve(port=8000, host="127.0.0.1", open_browser=True, workdir=None):
    Handler.workdir = workdir or Handler.workdir
    os.makedirs(Handler.workdir, exist_ok=True)
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}/"
    print(f"MERLIN {__version__} GUI on {url}")
    print(f"  project:   {ROOT}")
    print(f"  work dir:  {Handler.workdir}")
    print("  Ctrl-C to stop. The YAML files stay the source of truth; the GUI sends overrides on top of them.")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
