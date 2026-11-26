"""Single-file design report: one self-contained HTML document per sizing run.

The report is a *statement of the design as calculated*: every number it shows is either an input (with its units,
description, source and provenance) or an output of the Python model, and nothing in it is retyped by hand. It is
meant to be the thing that leaves the tool - handed to a reviewer, attached to a design review, or printed.

Self-contained means exactly that: images are embedded as base64 PNG, the stylesheet is inline, and there are no
external requests, so the file renders identically offline and years later. `to_pdf()` converts it with headless
Chromium or wkhtmltopdf when one of them is installed, and says so plainly when neither is.
"""
from __future__ import annotations
import base64
import datetime
import hashlib
import html
import os
import shutil
import subprocess
import tempfile
from . import __version__
from .method_register import REGISTER, FIELDS
from .units import G0

PROV_LABEL = {"user": "user", "reference": "reference", "assumed": "assumed", "calculated": "calculated"}

CSS = """
:root{--ink:#1b2430;--muted:#5d6b7a;--line:#d4dae1;--bg:#fff;--accent:#1f3864;
       --user:#dbeafe;--ref:#dcfce7;--asm:#fef3c7;--calc:#f1f5f9;--bad:#fee2e2;--warn:#fff7ed}
*{box-sizing:border-box}
body{margin:0;background:#eef1f4;color:var(--ink);
     font:13px/1.5 "Segoe UI",system-ui,-apple-system,Helvetica,Arial,sans-serif}
.page{max-width:1120px;margin:0 auto;background:var(--bg);padding:38px 46px 60px}
h1{font-size:25px;margin:0 0 4px;color:var(--accent);letter-spacing:-.2px}
h2{font-size:17px;margin:34px 0 10px;padding-bottom:5px;border-bottom:2px solid var(--accent);color:var(--accent)}
h3{font-size:14px;margin:20px 0 7px;color:#2c3e55}
h4{font-size:13px;margin:14px 0 5px;color:#2c3e55}
.sub{color:var(--muted);font-size:12px;margin:0 0 2px}
.meta{display:flex;flex-wrap:wrap;gap:6px 26px;font-size:11.5px;color:var(--muted);
      margin:14px 0 0;padding-top:12px;border-top:1px solid var(--line)}
table{border-collapse:collapse;width:100%;margin:8px 0 4px;font-size:12px}
th,td{border:1px solid var(--line);padding:4px 7px;text-align:left;vertical-align:top;
      overflow-wrap:anywhere}
table{table-layout:auto;max-width:100%}
th{background:var(--accent);color:#fff;font-weight:600;font-size:11.5px}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
td.n{white-space:nowrap}        /* values stay on one line; headers wrap, or a wide numeric table
                                   would force the whole page to be scaled down when printed */
th{white-space:normal;hyphens:auto}
tbody tr:nth-child(even) td{background:#fafbfc}
tr.sum td{font-weight:700;background:#eef2f7!important}
.small{font-size:11px;color:var(--muted)}
.kpi{margin:16px 0 4px;font-size:0}
.kpi div{display:inline-block;width:23%;margin:0 1% 9px 0;vertical-align:top;font-size:13px;
         border:1px solid var(--line);border-left:3px solid var(--accent);padding:8px 10px;background:#fbfcfd}
.kpi b{display:block;font-size:19px;font-weight:600;letter-spacing:-.3px}
.kpi span{font-size:10.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.banner{padding:10px 13px;border-radius:3px;margin:16px 0;font-size:12.5px;border:1px solid}
.ok{background:#f0fdf4;border-color:#86efac}
.no{background:var(--bad);border-color:#fca5a5}
.warn{background:var(--warn);border-color:#fdba74}
.banner ul{margin:7px 0 0;padding-left:19px}
.banner li{margin:2px 0}
.note{background:#f8fafc;border-color:var(--line);color:#34495e}
.note b{color:var(--ink)}
.p-user{background:var(--user)}.p-reference{background:var(--ref)}.p-assumed{background:var(--asm)}
.p-calculated{background:var(--calc)}
.lvl-ERROR{background:var(--bad)}.lvl-WARNING{background:var(--warn)}.lvl-INFO{background:var(--calc)}
.fig{margin:14px 0 6px;text-align:center}
.fig img{max-width:100%;max-height:1180px;height:auto;border:1px solid var(--line)}
.fig .cap{font-size:11px;color:var(--muted);margin-top:5px;text-align:left}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:10px 22px}
code,.mono{font-family:"Cascadia Mono",Consolas,"DejaVu Sans Mono",monospace;font-size:11.5px}
.toc{font-size:0;margin:12px 0 0}
.toc a{color:var(--accent);text-decoration:none;display:inline-block;
        width:48%;padding:2px 0;font-size:12.5px;vertical-align:top}
.toc a:hover{text-decoration:underline}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:11px;margin:6px 0 2px}
.legend i{display:inline-block;width:11px;height:11px;border:1px solid var(--line);margin-right:4px;
          vertical-align:-1px}
details{margin:6px 0}summary{cursor:pointer;font-weight:600;color:var(--accent);font-size:12.5px}
@media print{body{background:#fff}.page{max-width:none;padding:0 0 10mm}
  h2{page-break-after:avoid}table{page-break-inside:auto}tr{page-break-inside:avoid}
  .fig{page-break-inside:avoid;page-break-before:auto}
  .fig img{max-height:241mm;width:auto}
  th,td{font-size:10px;padding:2px 4px}
  .mono{word-break:break-all}details{display:block}details>summary{display:none}
  details[open]>*,details>*{display:revert}}
@page{size:A4;margin:14mm 12mm}
"""


# --------------------------------------------------------------------------- small helpers
def _e(x) -> str:
    return html.escape("" if x is None else str(x), quote=True)


def _f(x, nd=0, dash="-"):
    if x is None:
        return dash
    try:
        if nd == 0:
            return f"{x:,.0f}"
        return f"{x:,.{nd}f}"
    except (TypeError, ValueError):
        return _e(x)


def _tbl(headers, rows, cls="", numeric=()):
    """headers: raw HTML written by this module (never user data). rows: already-formatted cells, or
    (row_class, cells). Symbols are written as literal UTF-8 characters, not HTML entities, so that a header that
    passes through an escaper still reads as a symbol."""
    th = "".join(f'<th class="{"n" if i in numeric else ""}">{h}</th>' for i, h in enumerate(headers))
    out = [f'<table class="{cls}"><thead><tr>{th}</tr></thead><tbody>']
    for row in rows:
        rc, cells = row if isinstance(row, tuple) else ("", row)
        tds = "".join(f'<td class="{"n" if i in numeric else ""}">{c}</td>' for i, c in enumerate(cells))
        out.append(f'<tr class="{rc}">{tds}</tr>')
    out.append("</tbody></table>")
    return "".join(out)


def _img(path, caption):
    if not path or not os.path.exists(path):
        return f'<p class="small">[figure not available: {_e(os.path.basename(path or ""))}]</p>'
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return (f'<div class="fig"><img src="data:image/png;base64,{b64}" alt="{_e(caption)}">'
            f'<div class="cap">{caption}</div></div>')


def _file_digest(path):
    if not path or not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(65536), b""):
            h.update(blk)
    return h.hexdigest()[:16]


# --------------------------------------------------------------------------- sections
def _cover(res, design_path, assump_path, figures):
    spec = res.spec
    g = res.geometry
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    nsol = sum(1 for s in res.stages if s.is_solid)
    cfg = f"{len(res.stages)} stages"
    if nsol:
        cfg += f" ({nsol} solid, {len(res.stages) - nsol} liquid)"
    if res.boosters is not None:
        cfg += f" + {res.boosters.n_total} x {res.boosters.name}"
    banner = (f'<div class="banner ok"><b>Converged</b> in {res.iterations} iterations '
              f'(relative residual {res.residual:.2e}, tolerance {spec.convergence.tol:.0e}). '
              f'Achieved Δv {_f(res.dv_achieved_mps)} m/s against a requirement of '
              f'{_f(res.dv_required_mps)} m/s.</div>'
              if res.converged else
              f'<div class="banner no"><b>NOT CONVERGED</b> - {_e(res.status)}. '
              f'Every number below is from the last iteration and must not be used.</div>')
    kpi = [("GLOM", f"{_f(res.glom_kg)} kg", "gross lift-off mass"),
           ("Payload", f"{_f(res.payload_mass_kg)} kg", "to the injection orbit"),
           ("Δv required", f"{_f(res.dv_required_mps)} m/s", "incl. losses and margin"),
           ("Length", f"{g.total_length:.2f} m", "nozzle exit to fairing tip"),
           ("Max diameter", f"{g.max_diameter:.2f} m", "core / fairing"),
           ("Lift-off T/W", f"{res.liftoff_tw:.2f}", f"thrust {_f(res.liftoff_thrust_N / 1e3)} kN"),
           ("Payload fraction", f"{100 * res.payload_mass_kg / res.glom_kg:.2f} %", "of GLOM")]
    cards = "".join(f"<div><span>{k}</span><b>{v}</b><span>{s}</span></div>" for k, v, s in kpi)
    rows = [["Design", _e(spec.name)],
            ["Configuration", _e(cfg)],
            ["Mission", _e(spec.mission.get("orbit_type", "-")) + ", payload "
                        + f"{_f(res.payload_mass_kg)} kg"],
            ["Design file", f'<span class="mono">{_e(design_path)}</span>'
                            + (f' <span class="small">sha256:{_file_digest(design_path)}</span>' if design_path else "")],
            ["Assumptions file", f'<span class="mono">{_e(assump_path)}</span>'
                                 + (f' <span class="small">sha256:{_file_digest(assump_path)}</span>' if assump_path else "")],
            ["Tool version", f"MERLIN {_e(__version__)}"],
            ["Generated", _e(now)],
            ["Reference", "Edberg &amp; Costa, <i>Design of Rockets and Space Launch Vehicles</i>, 2nd ed., AIAA 2022 "
                          "(with the published 1st-edition errata applied; see docs/ERRATA_COMPLIANCE.md)"]]
    return (f"<h1>Launch vehicle conceptual design report</h1>"
            f'<p class="sub">{_e(spec.name)} — {_e(cfg)}</p>'
            f'<div class="kpi">{cards}</div>{banner}'
            + _tbl(["Item", "Value"], rows))


def _drivers(res, extras):
    """The numbers that actually size this vehicle, gathered from whichever studies were run.

    Each row is a quantity that, if it moved, would change the hardware: the station the structure is sized
    at, the condition that sets the wall thickness, the peak the trajectory has to survive. Only studies that
    were actually run contribute, so a quick run shows a short table rather than a padded one.
    """
    rows = []

    def add(driver, value, where, section):
        rows.append([_e(driver), _e(value), _e(where), f'<a href="#{section[0]}">&sect;{_e(section[1])}</a>'])

    ld = extras.get("loads") or {}
    cases = [c for k, c in ld.items() if hasattr(c, "stations") and c.stations]
    if cases:
        worst = max(cases, key=lambda c: max(abs(st.moment_Nm) for st in c.stations))
        wst = max(worst.stations, key=lambda st: abs(st.moment_Nm))
        add("Governing bending moment", f"{wst.moment_Nm / 1e3:,.0f} kN\u00b7m",
            f"z = {wst.z_m:.1f} m, {worst.name}", ("loads", "loads"))
        axial = max(cases, key=lambda c: max(st.axial_below_N for st in c.stations))
        ast = max(axial.stations, key=lambda st: st.axial_below_N)
        add("Peak axial compression", f"{ast.axial_below_N / 1e3:,.0f} kN",
            f"z = {ast.z_m:.1f} m, {axial.name}", ("loads", "loads"))

    sc = extras.get("structure") or {}
    shells = sc.get("shells") or []
    if shells:
        thick = max(shells, key=lambda sh: sh.t_required_m)
        add("Thickest shell required", f"{1e3 * thick.t_required_m:.2f} mm",
            f"{thick.name}, sized by {thick.governing_driver}", ("struct", "structure"))
        if sc.get("mass_ratio"):
            add("Monocoque vs MER shell mass", f"{sc['mass_ratio']:.2f} \u00d7",
                f"{_f(sc.get('mass_sized_kg'))} kg sized against {_f(sc.get('mass_model_kg'))} kg modelled",
                ("struct", "structure"))

    tr = extras.get("trajectory")
    if tr is not None and getattr(tr, "converged", False) and getattr(tr, "q_Pa", None):
        import math
        qmax = max(tr.q_Pa)
        add("Maximum dynamic pressure", f"{qmax / 1e3:.1f} kPa",
            f"t = {tr.t_s[tr.q_Pa.index(qmax)]:.0f} s, h = {tr.h_m[tr.q_Pa.index(qmax)] / 1e3:.1f} km",
            ("traj", "trajectory"))
        if getattr(tr, "accel_g", None):
            gmax = max(tr.accel_g)
            # The sizing loop's own figure is vacuum thrust over burnout mass; the trajectory's is what the
            # vehicle actually pulls, thrust less drag at the real altitude. Naming both here stops the front
            # page appearing to contradict a burnout-acceleration warning a few lines below it.
            sized = max((s.accel_max_g for s in res.stages), default=0.0)
            add("Peak axial acceleration", f"{gmax:.2f} g flown",
                f"t = {tr.t_s[tr.accel_g.index(gmax)]:.0f} s; sizing loop quotes {sized:.2f} g at burnout "
                f"on vacuum thrust", ("traj", "trajectory"))

    ctl = extras.get("control")
    if ctl is not None and getattr(ctl, "points", None):
        w = ctl.worst("controllability")          # smallest control margin along the atmospheric ascent
        if w is not None:
            add("Worst control authority", f"M_\u03b4/M_A = {w.controllability:.2f}",
                f"t = {w.t_s:.0f} s, trim {w.trim_deg:.2f}\u00b0 of {ctl.delta_max_deg:.1f}\u00b0 available",
                ("aero", "stability and control"))

    pe = extras.get("payload_env")
    if pe is not None and getattr(pe, "rows", None):
        add("Payload design load factors", f"{pe.design_axial_g:.1f} g axial, {pe.design_lateral_g:.1f} g lateral",
            f"{pe.governing_axial_event}", ("penv", "payload environment"))

    if not rows:
        return ('<p class="small">No driver study was run. Add <span class="mono">--all-studies</span> to see '
                'what sizes this vehicle; the sizing loop alone reports masses, not drivers.</p>')
    return _tbl(["What governs", "Value", "Where", "Detail"], rows)


def _summary(res, extras, figures):
    """The front page: what this vehicle is, what drives it, and what the tool is unhappy about.

    Everything after this is the working behind it. The three things a reader needs before deciding whether to
    read on are the mission, the drivers, and the warnings - and until this existed all three were scattered
    across twenty sections.
    """
    spec = res.spec
    m = spec.mission
    extras = extras or {}
    orbit = m.get("orbit_type", "-")
    h_km = m.get("perigee_altitude_m", 0.0) / 1e3
    inc = m.get("inclination_deg")
    mission = (f"{_f(res.payload_mass_kg)} kg to a {h_km:,.0f} km {_e(orbit)} orbit"
               + (f" at {inc:.1f}\u00b0" if inc is not None else "")
               + f", from {m.get('site_latitude_deg', 0.0):.1f}\u00b0 latitude.")

    iss = sorted(res.issues, key=lambda i: {"ERROR": 0, "WARNING": 1, "INFO": 2}.get(i.level, 3))
    errs = [i for i in iss if i.level == "ERROR"]
    warns = [i for i in iss if i.level == "WARNING"]
    if errs:
        cls, head = "no", f"{len(errs)} error(s) and {len(warns)} warning(s)"
    elif warns:
        cls, head = "warn", f"No errors, {len(warns)} warning(s)"
    else:
        cls, head = "ok", "No errors or warnings"
    # The ellipsis is bound to a name rather than written inside the f-string expression: a backslash in the
    # EXPRESSION part of an f-string is PEP 701 syntax and a SyntaxError before Python 3.12, which this
    # project still supports. The literal text part of an f-string may contain one, which is why the em dash
    # below is fine where the ellipsis was not.
    ell = "\u2026"
    items = "".join(f'<li><span class="mono">{_e(i.code)}</span> \u2014 {_e(i.message[:260])}'
                    f'{ell if len(i.message) > 260 else ""}</li>' for i in (errs + warns)[:8])
    more = (f'<p class="small">{len(errs) + len(warns) - 8} further item(s) in '
            f'<a href="#chk">the checks section</a>.</p>' if len(errs) + len(warns) > 8 else "")
    flags = (f'<div class="banner {cls}"><b>{head}.</b>'
             + (f"<ul>{items}</ul>{more}" if items else
                " Nothing in the model flagged this design as outside the range its methods were fitted for.")
             + "</div>")

    return ("<h2>Summary</h2>"
            f'<p><b>Mission.</b> {mission}</p>'
            f'<p><b>Vehicle.</b> {_f(res.glom_kg)} kg lift-off mass, {res.geometry.total_length:.1f} m long, '
            f'{res.geometry.max_diameter:.2f} m diameter, '
            f'{100 * res.payload_mass_kg / res.glom_kg:.2f} % payload fraction. '
            f'\u0394v required {_f(res.dv_required_mps)} m/s.</p>'
            "<h3>What governs this design</h3>"
            + _drivers(res, extras)
            + "<h3>What the checks say</h3>" + flags
            + '<p class="small">Everything below this point is the working: the sections are ordered as the '
              'design proceeds, from the mission requirement through to the register of every method used. '
              'Read the limitations note next if you have not used this tool before.</p>')


def _trajectory_limit_bullet(res, extras):
    """What the limitations section should say about the ascent, given what was actually run.

    A static "no trajectory simulation" disclaimer sitting above a section that integrates one is worse than no
    disclaimer: it tells the reader the report does not know what is in it. There are three honest states.
    """
    tr = (extras or {}).get("trajectory")
    if tr is None:
        return ("<li><b>No trajectory was flown.</b> Ascent losses here are a published regression fit or user "
                "estimates; the achievability of the orbit is not demonstrated, and no steering or lofting "
                "profile exists. Run the tool with <code>--trajectory</code> to integrate one and compute the "
                "losses instead.</li>")
    if not tr.converged:
        return (f"<li><b>A trajectory was integrated but the ascent did not close.</b> {_e(tr.status)} The "
                f"losses in section 6 therefore describe a flight that did not reach orbit, and the sizing "
                f"still rests on the regression estimate. The achievability of the orbit is <b>not</b> "
                f"demonstrated.</li>")
    margin = tr.margin_mps
    short = ("" if margin >= 0 else
             f" It finished {abs(margin):,.0f} m/s short of the speed the orbit needs, so on this flight the "
             f"vehicle does <b>not</b> reach the orbit.")
    return (f"<li><b>A trajectory was flown, and that is what section 6 reports.</b> Gravity, drag, propulsion "
            f"and steering losses there are integrals along an actual ascent (book Eq. 6:58), not estimates. "
            f"Two caveats remain. The vehicle was still <b>sized</b> with the loss estimate of section 1 unless "
            f"the loss model says otherwise - the trajectory is a check after the fact. And it is 3-DoF: no wind, "
            f"no lift, no attitude dynamics; the pitch kick is searched and the steering above the atmosphere is "
            f"the book's linear tangent law, which is close to the best a vehicle can do but is not an optimised "
            f"guidance design.{short}</li>")


def _loads_limit_bullet(res, extras):
    """What the limitations section should say about structure, given whether the loads were computed."""
    cases = (extras or {}).get("loads")
    if not cases:
        return ("<li><b>No structural analysis.</b> Tank and structure masses come from statistical MERs (or "
                "thin-wall membrane theory when that option is selected). Buckling, axial and bending loads, "
                "slosh, acoustics and proof testing are not sized. Nothing here is a stress report. Run the "
                "tool with <code>--loads</code> to compute the ground wind and max-q load distributions.</li>")
    worst = max((c for c in cases.values() if hasattr(c, "stations")),
                key=lambda c: abs(c.max_moment_Nm), default=None)
    where = f" The largest bending moment found is {abs(worst.max_moment_Nm)/1e3:,.0f} kN m, in the "\
            f"{_e(worst.name.lower())} case." if worst else ""
    if not (extras or {}).get("structure"):
        return ("<li><b>Loads, but not stresses.</b> The load cases were computed and are reported, so the "
                "vehicle is no longer unexamined structurally: axial force, shear and bending moment are known "
                f"along its length.{where} What is still missing is everything that turns a load into a "
                "structure: shell stresses, buckling allowables, the relief that tank pressurisation gives, "
                "joints and local cut-outs, and therefore any margin of safety. Structural masses still come "
                "from statistical MERs and were <b>not</b> re-sized to carry these loads. Run the tool with "
                "<code>--structure</code> for the stress and buckling analysis.</li>")
    sx = extras["structure"]
    ratio = (f" Sized as monocoque the shells come to {sx['mass_ratio']:.2f} times what the mass relationships "
             f"carry for them, which is the structural efficiency this analysis cannot model."
             if sx.get("mass_ratio") else "")
    return ("<li><b>Stresses and thicknesses, but not a structure.</b> Loads, stresses, buckling allowables and "
            f"the wall thickness each shell needs are all computed and reported.{where}{ratio} What is still "
            "missing: the structural masses in the mass statement are <b>still</b> the statistical relationships "
            "and were never re-sized to the thicknesses found here, so the vehicle in this report is not the "
            "vehicle that was analysed. Only monocoque shells are sized - no rings, stringers, sandwich or "
            "isogrid, which is what real vehicles use and is why the sized masses come out heavy. Domes, "
            "joints, cut-outs, thermal stress, fatigue, slosh, acoustics and proof testing are not covered at "
            "all, and the combined stress state is not evaluated.</li>")


def _limits(res, extras=None):
    body = """
<p>This report is a <b>conceptual sizing</b> result produced by mass-estimating relationships and closed-form
geometry. It is not a design qualification and does not demonstrate that the vehicle can fly. In particular:</p>
<ul>
__TRAJ_BULLET__
__LOADS_BULLET__
<li><b>No stability, control, thermal, GNC, separation or aerodynamic analysis.</b> Moments of inertia are
    reported, but no control authority or margin is assessed.</li>
<li><b>MER scatter.</b> Mass-estimating relationships are fits to historical vehicles; individual components can
    deviate by tens of per cent. Validation against twelve real vehicles gives a median GLOM error of about 17 %
    (see docs/VALIDATION_REPORT.md). Treat every mass here as having that kind of uncertainty.</li>
<li><b>Engines and motors are rubber.</b> Unless a real engine's mass and dimensions were entered, the engine is a
    scaled MER and its envelope is a layout estimate.</li>
</ul>
<p>Every input used is listed in full, with its source and provenance, in the <b>Input register</b> section; every
calculation is listed in the <b>Engineering method register</b> with the book page it comes from or an explicit
mark that it is supplementary.</p>"""
    body = body.replace("__TRAJ_BULLET__", _trajectory_limit_bullet(res, extras))
    body = body.replace("__LOADS_BULLET__", _loads_limit_bullet(res, extras))
    return '<div class="banner note">' + body + "</div>"


def _requirement(res):
    b = res.budget
    rows = []
    for ln in b.lines:
        cls = "" if ln.in_total else "small"
        rows.append((cls, [_e(ln.name) + ("" if ln.in_total else " <i>(informational)</i>"),
                           _f(ln.value_mps, 1), _e(ln.category),
                           "yes" if ln.in_total else "no", _e(ln.source)]))
    rows.append(("sum", ["<b>Δv required</b>", f"<b>{_f(b.total_mps, 1)}</b>", "total", "", ""]))
    out = ["<h2 id=req># Mission requirement and Δv budget</h2>"]
    m = res.spec.mission
    hp = (m.get("perigee_altitude_m") or 0.0) / 1e3
    ha = m.get("apogee_altitude_m")
    orbit = (f"{_e(m.get('orbit_type'))}: {hp:,.0f} km"
             + (f" x {ha / 1e3:,.0f} km" if ha else " circular")
             + f", i = {_f(m.get('inclination_deg'), 2)} deg")
    lm = m.get("loss_model")
    loss_src = {"book_penalty": "Eqs. 3:35-3:38 regression (lumped)",
                "book_k1k2": "Eqs. 3:33-3:34 (K1 + K2 Ta)",
                "book_simple": "Eq. 3:32 (simple three-term fit)",
                "simulated": "the losses of this vehicle's own simulated flight (SUPPLEMENTARY)",
                "user": "explicit user estimates"}.get(lm, "-")
    info = [["Injection orbit", orbit],
            ["Launch site", f"latitude {_f(m.get('site_latitude_deg'), 2)} deg, "
                            f"altitude {_f(m.get('site_altitude_m'), 0)} m"],
            ["Launch azimuth", f"{_f(m.get('launch_azimuth_deg'), 2)} deg"
                               if m.get("launch_azimuth_deg") is not None else "computed from the inclination"],
            ["Earth rotation credited", "yes" if m.get("include_earth_rotation") else "no"],
            ["Loss model", f"{_e(lm)} — {loss_src}"],
            ["Design margin", f"{100 * (m.get('design_margin_fraction') or 0.0):.1f} %"],
            ["Air launch", _e(m.get("air_launch")) if m.get("air_launch") else "no (ground launch)"],
            ["Δv override", f"{_f(m.get('dv_override_mps'), 1)} m/s (requirement forced by the user)"
                                  if m.get("dv_override_mps") else "none"],
            ["Δv allocation", _e(res.spec.dv_mode) + " → " +
             ", ".join(f"stage {i+1}: {_f(d, 1)} m/s" for i, d in enumerate(res.allocation))]]
    out.append(_tbl(["Requirement", "Value"], info))
    out.append("<h3>Δv budget, line by line</h3>")
    out.append(_tbl(["Budget line", "m/s", "Category", "In total", "Source"], rows, numeric=(1,)))
    if getattr(b, "notes", None):
        out.append('<p class="small">' + "<br>".join(_e(n) for n in b.notes) + "</p>")
    return "".join(out)


def _config(res):
    rows = []
    for s in res.stages:
        p = s.index
        st = res.spec.stages[p - 1]
        prop = (f"{_e(st.propellant)} (solid)" if s.is_solid
                else f"{_e(st.oxidizer)}/{_e(st.fuel)}, O/F {st.of_ratio:.2f}")
        ps = st.prop_system
        eng = (f"{_e(ps.name)}" if s.is_solid else f"{ps.n_engines} x {_e(ps.name)}")
        rows.append([f"{s.index}", _e(s.name), _e(s.stage_type), prop, eng,
                     f"{st.diameter_m:.2f}", f"{s.length_m:.2f}", _f(s.isp_eff_s, 1),
                     _f(s.dv_mps, 0), _f(s.m_prop_loaded_kg), _f(s.m_dry_kg), f"{s.structural_factor_s:.4f}"])
    out = ["<h2 id=cfg># Vehicle configuration</h2>",
           _tbl(["Stage", "Name", "Type", "Propellant", "Propulsion", "D [m]", "L [m]", "Isp_eff [s]",
                 "Δv [m/s]", "Propellant [kg]", "Dry [kg]", "s = ms/(ms+mp)"], rows,
                numeric=(5, 6, 7, 8, 9, 10, 11))]
    f = res.spec.fairing
    frows = [["Payload", f"{_f(res.payload_mass_kg)} kg in a {f.envelope_diameter_m:.2f} m x "
                         f"{f.envelope_length_m:.2f} m envelope"],
             ["Payload adapter (PAF)", f"{_f(res.paf_mass_kg, 1)} kg "
                                       f"(method: {_e(res.spec.paf_method)})"],
             ["Fairing", f"{_f(res.fairing_mass_kg, 1)} kg, {f.diameter_m:.2f} m diameter, {_e(f.material)}, "
                         f"jettisoned at the start of stage {f.jettison_stage}"]]
    out.append(_tbl(["Upper assembly", "Value"], frows))
    if res.boosters is not None:
        b = res.boosters
        brows = [["Boosters", f"{b.n_total} x {_e(b.name)} ({_e(b.kind)}), {b.n_ground_lit} ground-lit"],
                 ["Attached to", f"stage {b.attach_stage}"],
                 ["Each", f"{_f(b.m_prop_each_kg)} kg propellant + {_f(b.m_inert_each_kg)} kg inert "
                          f"= {_f(b.m_loaded_each_kg)} kg loaded, s = {b.structural_factor_s:.4f}"],
                 ["Total booster mass", f"{_f(b.m_total_kg)} kg"],
                 ["Thrust each", f"{_f(b.thrust_vac_each_N / 1e3, 1)} kN vacuum" +
                  (f", {_f(b.thrust_sl_each_N / 1e3, 1)} kN sea level" if b.thrust_sl_each_N else "")],
                 ["Burn time", f"{b.burn_time_s:.1f} s"],
                 ["Geometry", f"{b.diameter_m:.2f} m x {b.length_m:.2f} m, offset {b.x_offset_m:.2f} m from the axis"]]
        out.append("<h3>Strap-on boosters (parallel burn, book Sec. 5.11)</h3>")
        out.append(_tbl(["Item", "Value"], brows))
    return "".join(out)


def _drawings(res, figures):
    """The drawing pages. A launch vehicle is 10-20 times longer than it is wide, so a single full-height column
    uses a fifth of a portrait page; the report therefore prefers the paged variants (`*_page_png`), which split
    the same to-scale drawing over as many z-windows as it takes to fill the page."""
    def pick(*keys):
        for k in keys:
            if figures.get(k) and os.path.exists(figures[k]):
                return figures[k]
        return figures.get(keys[-1])

    paged = bool(figures.get("vehicle_page_png"))
    note = (" The vehicle is drawn as one continuous view at the largest scale that fits the page height, with "
            "the dimensions on the left and the stage data beside the stage it describes." if paged else "")
    plates = [(pick("vehicle_page_png", "vehicle_png"),
               "Vehicle general arrangement, to scale." + note +
               " Interior outlines are the sized tank or motor-case geometry, not a structural layout.")]
    # The isometric view is deliberately NOT placed here. It is produced by --cad, next to the DXF and the
    # meshes, where it belongs as a check on that export; in the report it showed the same outer mould line the
    # general arrangement above already shows, to scale and dimensioned, and at less use.
    plates.append((pick("mass_distribution_png"),
                   "Centre-of-mass travel through the flight events, from the mass ledger in section 6. The "
                   "CM moves nearly the length of the vehicle between lift-off and insertion, which is what "
                   "the static margin in section 8 has to be read against."))
    for s in res.stages:
        p = pick(f"stage{s.index}_page_png", f"stage{s.index}_png")
        if p and os.path.exists(p):
            kind = "solid motor" if s.is_solid else "tankage and engines"
            label = f"Stage {s.index}" if s.name.strip().lower() in (f"stage {s.index}", f"stage{s.index}") \
                else f"Stage {s.index} ({_e(s.name)})"
            plates.append((p, f"{label} \u2014 {kind}, to scale. Tank and motor numbers are tabulated in "
                              f"section 7."))
    out = ["<h2 id=drw># Drawings</h2>"]
    out += [_img(p, f"<b>Figure {i}.</b> {cap}") for i, (p, cap) in enumerate(plates, start=1)]
    out.append(_cad_note())
    return "".join(out)


def _cad_note():
    """What the CAD export gives and what it costs, so nobody takes a mesh for a solid model."""
    from . import cad_export, cad_kernel
    deficit = 100.0 * (1.0 - cad_export.faceted_volume_ratio(cad_export.DEFAULT_FACETS))
    st = cad_kernel.status()
    exact = (f"Exact solids are available here through cadquery {st['version']}: STEP with a named "
             f"part tree, and BREP. Each solid is checked against its closed-form volume before it "
             f"is written."
             if st["available"] else
             "Exact solids (STEP) are not available in this installation: it has no geometry "
             "kernel. <code>pip install cadquery</code> adds them; the four formats above need "
             "nothing.")
    return ('<div class="banner note"><b>CAD export.</b> <code>--cad</code> writes this outer '
            "mould line as a layered DXF inboard profile and as faceted meshes in STL, OBJ and "
            "3MF. Prefer 3MF over STL: it records the unit its coordinates are in and keeps the "
            f"part names, both of which STL discards. A faceted mesh encloses {deficit:.3f}% less "
            f"volume than the true body of revolution at the default {cad_export.DEFAULT_FACETS} "
            "facets, and cannot be sectioned or measured as a solid. " + exact +
            " No export has been opened in a commercial CAD application by the authors of this "
            "tool; the formats are written from their published specifications and read back by "
            "independent parsers in the test suite.</div>")


def _reliability(res):
    """Engine-cluster reliability and the engine-out case (R24, book Sec. 15.2.6).

    Placed in the propulsion section because that is where n_engines is decided, and the number of engines is
    the input this analysis prices. Nothing here feeds back into sizing.
    """
    from . import reliability as rl
    try:
        a = rl.analyse(res)
    except Exception as ex:                                  # noqa: BLE001
        return f'<p class="small">Engine reliability not computed: {_e(type(ex).__name__)}.</p>'
    if not a["stages"]:
        return ""
    rows = []
    for s in a["stages"]:
        tw_out = "\u2014" if s["tw_one_out"] is None else _f(s["tw_one_out"], 2)
        verdict = ("no redundancy (single engine)" if s["n_engines"] < 2 else
                   ("can lose one" if s["can_lose_an_engine"] else "CANNOT lose one"))
        rows.append([f"{s['stage']}", f"{s['n_engines']}", _f(s["tw_nominal"], 2), tw_out, verdict,
                     _f(100 * s["all_must_work"], 3) + " %",
                     ("\u2014" if s["one_out_tolerant"] is None
                      else _f(100 * s["one_out_tolerant"], 3) + " %"),
                     _f(100 * s["r_cluster"], 3) + " %"])
    out = ['<h3 class="sect">Engine-out and cluster reliability</h3>',
           f'<p class="small">Per-engine reliability {a["r_engine"]:.5f} \u2014 {_e(a["source"])}. '
           f'The cluster figure is the book\'s Sec. 15.2.6 binomial, R_s = \u03a3 C(n,j) R^j (1\u2212R)^(n\u2212j).</p>',
           _tbl(["Stage", "Engines", "T/W nominal", "T/W one out", "Engine-out", "All must work",
                 "One-out tolerant", "Credited"], rows, numeric=(1, 2, 3, 5, 6, 7))]
    if a["propulsion_reliability"] is not None:
        out.append(f'<p class="small">Propulsion reliability over all liquid stages, as credited: '
                   f'<b>{100 * a["propulsion_reliability"]:.3f} %</b>.</p>')
    out.append('<div class="banner note"><b>What this is worth.</b> ' + _e(a["independence_caveat"])
               + ' More engines is not automatically more reliable: the book\'s own pair of examples has a '
                 '7-of-9 cluster (99.164 %) coming out WORSE than a 3-of-5 one (99.88 %) at the same '
                 'per-engine reliability, because engines added faster than tolerated failures add failure '
                 'opportunities. Redundancy is only credited above where the stage can still fly with an '
                 'engine shut down.</div>')
    return "".join(out)


def _propellants(res):
    """Propellants, mixture ratio and bulk density per stage, beside what the chemistry can actually give."""
    from . import propellant_db as pdb
    spec = res.spec
    combos = getattr(spec, "propellant_combinations", {}) or {}
    rows, refs, any_ref = [], [], False
    for s in res.stages:
        st = spec.stages[s.index - 1]
        if s.is_solid:
            rows.append([f"{s.index}", _e(getattr(st, "propellant", "-") or "-"), "-", "-", "-",
                         _f(s.isp_eff_s, 1)])
            continue
        c = pdb.find_by_pair(st.oxidizer, st.fuel, combos)
        rho = pdb.bulk_density_kg_m3(c, spec.propellants, st.of_ratio) if c else None
        rows.append([f"{s.index}", f"{_e(st.oxidizer)} / {_e(st.fuel)}", f"{st.of_ratio:.3f}",
                     _f(rho, 1) if rho else "-",
                     _f(rho * s.isp_eff_s / 1e3, 1) if rho else "-", _f(s.isp_eff_s, 1)])
        if c is not None:
            any_ref = True
            refs.append([f"{s.index}", _e(c.name),
                         _f(c.of_ratio_optimum, 2) if c.of_ratio_optimum else "-",
                         _f(c.of_ratio_flight, 2) if c.of_ratio_flight else "-",
                         f"{st.of_ratio:.2f}",
                         _f(c.isp_ref_s, 1) if c.isp_ref_s else "-",
                         _f(c.cstar_ref_mps, 0) if c.cstar_ref_mps else "-",
                         _f(c.Tc_ref_K, 0) if c.Tc_ref_K else "-"])
    out = ["<h3>Propellants, mixture ratio and bulk density</h3>",
           _tbl(["Stage", "Oxidizer / fuel", "O/F", "bulk ρ [kg/m³]", "density impulse [kN·s/m³]",
                 "Isp effective [s]"], rows, numeric=(2, 3, 4, 5)),
           '<p class="small">Bulk density is (1+r)/(r/ρ_ox + 1/ρ_fuel) from the same densities the tanks are '
           'sized with, so it cannot disagree with the geometry. Density impulse ρ·Isp is the figure of merit '
           'for tank volume rather than mass: hydrogen wins on Isp and loses here.</p>']
    if any_ref:
        out += ["<h3>What the chemistry allows (book Table 4.10, p.240)</h3>",
                _tbl(["Stage", "Combination", "O/F at peak Isp", "O/F flown", "O/F used",
                      "Isp ref [s]", "c* ref [m/s]", "Tc ref [K]"], refs, numeric=tuple(range(2, 8))),
                '<p class="small"><b>The reference Isp is not a vacuum Isp and is not a target.</b> Book '
                'Table 4.10 is computed at a chamber pressure of 1,000 psia expanded optimally to sea-level '
                'ambient, so a vacuum nozzle of large area ratio legitimately beats it - the RD-180 delivers '
                '338 s against the 300 s tabulated for LOX/RP-1. It bounds what the combustion can give at '
                'that condition, and the two mixture ratios are kept apart because engines do not run at peak '
                'Isp: the Isp peak for LOX/LH2 is near O/F 4.0 and the J-2 flew at 5.50. Rows whose '
                'combination is not in the book (the peroxide pairs) carry figures from the papers cited in '
                'the input register instead, at their own conditions.</p>']
    notes = getattr(spec, "propellant_combination_notes", []) or []
    if notes:
        items = []
        for n in notes:
            filled = ", ".join(n["filled"]) if n["filled"] else "nothing (the stage stated it all)"
            items.append(f"<li>{_e(n['context'])}: named <b>{_e(n['entry'])}</b>, which supplied "
                         f"{_e(filled)}. Source: {_e(n['source'] or 'library entry')}</li>")
        out.append("<p class=\"small\">Resolved from the propellant-combination library:</p><ul class=\"small\">"
                   + "".join(items) + "</ul>")
    return "".join(out)


def _performance(res):
    rows = []
    for s in res.stages:
        rows.append([f"{s.index}", _f(s.thrust_vac_N / 1e3, 1),
                     _f(s.thrust_sl_N / 1e3, 1) if s.thrust_sl_N else "-",
                     _e(s.thrust_ref_condition), _f(s.mdot_kgs, 1), f"{s.burn_time_s:.1f}",
                     f"{s.tw_ignition:.2f}", f"{s.tw_burnout:.2f}", f"{s.accel_max_g:.2f}",
                     f"{s.mass_ratio:.4f}", _f(s.dv_check_mps, 1)])
    out = ["<h2 id=perf># Propulsion and performance</h2>",
           _tbl(["Stage", "T_vac [kN]", "T_SL [kN]", "Reference condition", "mdot [kg/s]", "t_burn [s]",
                 "T/W ignition", "T/W burnout", "a_max [g]", "mass ratio μ", "Δv recomputed [m/s]"],
                rows, numeric=(1, 2, 4, 5, 6, 7, 8, 9, 10)),
           '<p class="small">The last column recomputes Δv from the sized burn-start and burnout masses with '
           'the rocket equation; it must match the allocated Δv in section 2 to solver tolerance.</p>']
    out.append(_propellants(res))
    out.append(_reliability(res))
    if any(s.is_solid for s in res.stages):
        mr = []
        for s in res.stages:
            if s.is_solid and s.motor_info:
                mi = s.motor_info
                mr.append([f"{s.index}", _e(s.name), _f(mi.get("casing_k"), 4),
                           _f(mi.get("casing_mass_kg"), 1),
                           _f(mi.get("grain_volume_m3"), 2), _f(mi.get("casing_volume_m3"), 2),
                           _f(mi.get("volume_factor"), 2), _f(mi.get("web_m"), 3),
                           _f(mi.get("bore_radius_m"), 3), _f(mi.get("implied_burn_rate_mm_s"), 2)])
        if mr:
            out.append("<h3>Solid motor grain and casing (book Eqs. 8:17-8:24)</h3>")
            out.append(_tbl(["Stage", "Motor", "k = m_case/m_p", "Casing [kg]", "V_grain [m³]",
                             "V_casing [m³]", "V_case/V_grain", "web [m]", "bore radius [m]",
                             "implied burn rate [mm/s]"], mr, numeric=tuple(range(2, 10))))
            out.append('<p class="small">The casing mass includes internal insulation, the nozzle, the thrust '
                       'structure and TVC (book p.490 and 1st-ed. errata p.436), so no separate engine, thrust '
                       'structure or gimbal mass is added to a solid stage. The implied burn rate is web/t_burn, '
                       'reported for the designer to check against a real propellant; no internal-ballistics '
                       'solution is run.</p>')
    if res.boosters is not None:
        sr = res.stages[res.boosters.attach_stage - 1]
        pr = [[_e(p.name), f"{p.duration_s:.1f}", _f(p.mdot_total_kgs, 1), _f(p.isp_eff_s, 1),
               _f(p.thrust_eff_N / 1e3, 1), _f(p.m_start_kg), _f(p.m_end_kg), _f(p.dv_mps, 1)]
              for p in sr.phases]
        out.append("<h3>Parallel-burn phases (Eqs. 5:65-5:66, Fig. 5.21)</h3>")
        out.append(_tbl(["Phase", "duration [s]", "mdot total [kg/s]", "Isp mass-averaged [s]", "Thrust [kN]",
                         "m start [kg]", "m end [kg]", "Δv [m/s]"], pr, numeric=(1, 2, 3, 4, 5, 6, 7)))
        out.append('<p class="small">Each phase uses the mass-averaged exhaust speed of everything burning in it '
                   '(Eq. 5:66). Booster jettison removes inert mass and produces no Δv.</p>')
    return "".join(out)


def _capability(res, extras, figures):
    """R1: what the vehicle delivers where, as opposed to what it was sized for (book Sec. 3.8)."""
    cur = (extras or {}).get("performance")
    if not cur:
        return ""
    out = ["<h2 id=cap># Payload capability</h2>",
           '<div class="banner note">The sections above size a vehicle <b>for one mission</b>. This one freezes '
           'that vehicle - every stage keeps its dry mass, propellant load, mass flow, burn time and Isp - and '
           'asks what payload it delivers to other orbits. Only the payload and its adapter change, so the '
           'curves are the vehicle\u2019s performance, not a family of re-optimised designs. The design point is '
           'marked and lies on the curve by construction, which is also the check that this section and the '
           'sizing agree.</div>',
           _img(figures.get("performance_png"),
                "<b>Figure P.</b> Payload against circular-orbit altitude for several inclinations, and against "
                "inclination at the design altitude (book Sec. 3.8, Figs. 3.27-3.29). The star is the design "
                "point.")]
    va = cur.get("vs_altitude")
    if va:
        alts = [p["altitude_km"] for p in va["curves"][0]["points"]]
        head = ["Inclination"] + [f"{a:,.0f} km" for a in alts]
        rows = []
        for c in va["curves"]:
            rows.append([f"{c['inclination_deg']:.1f}\u00b0"] +
                        [("-" if p["payload_kg"] is None else _f(p["payload_kg"])) for p in c["points"]])
        out.append("<h3>Payload [kg] to a circular orbit</h3>")
        out.append(_tbl(head, rows, numeric=tuple(range(1, len(head)))))
    vi = cur.get("vs_inclination")
    if vi:
        rows = [[f"{p['inclination_deg']:.1f}\u00b0",
                 "-" if p["payload_kg"] is None else _f(p["payload_kg"]),
                 _e(p.get("note") or "")] for p in vi["points"]]
        out.append(f"<h3>Payload against inclination at {vi['altitude_km']:,.0f} km</h3>")
        out.append(_tbl(["Inclination", "Payload [kg]", "Note"], rows, numeric=(1,)))
    out.append('<p class="small">An inclination below the launch-site latitude is reported as unreachable rather '
               'than flown: the dog-leg or plane change that would reach it is not modelled. The sweep stops at '
               '1,000 km because the book\u2019s ascent-loss regressions are fitted to low Earth orbit and '
               'extrapolate badly above it.</p>')
    return "".join(out)


def _orbit_rows(tr):
    """The orbit-reached check, as rows of the ascent table (trajectory.insertion_orbit)."""
    ins = getattr(tr, "insertion", None)
    if not ins:
        return []
    if not ins.get("checked"):
        return [["Orbit reached?", _e(ins.get("headline") or "not checked")]]
    word = {"reached": "Yes", "short": "Short of the target", "suborbital": "No"}.get(ins["verdict"], "")
    rows = [["Orbit reached?", f"<b>{word}.</b> {_e(ins['headline'])}"],
            ["End of flight, inertial", f"{_f(ins['inertial_speed_mps'])} m/s at a flight path angle of "
                                  f"{ins['inertial_gamma_deg']:+.2f} deg"]]
    if ins.get("eccentricity") is not None:
        rows.append(["Orbit at the end", f"{ins['perigee_alt_m']/1e3:,.0f} x {ins['apogee_alt_m']/1e3:,.0f} km, "
                                         f"eccentricity {ins['eccentricity']:.4f}; asked for "
                                         f"{ins['target_perigee_alt_m']/1e3:,.0f} x "
                                         f"{ins['target_apogee_alt_m']/1e3:,.0f} km. Counted as reached within "
                                         f"{ins['tolerance_perigee_m']/1e3:,.0f} km at perigee and "
                                         f"{ins['tolerance_apogee_m']/1e3:,.0f} km at apogee (an assumed "
                                         f"reporting tolerance, not an injection accuracy)"])
    for n in ins.get("notes") or []:
        rows.append(["", _e(n)])
    return rows


def _trajectory(res, extras, figures):
    """R5: the ascent actually flown, and the losses that come out of it rather than out of a regression."""
    tr = (extras or {}).get("trajectory")
    if not tr:
        return ""
    out = ["<h2 id=traj># Ascent trajectory</h2>",
           '<div class="banner note">Everywhere else in this report the ascent losses come from a published '
           'regression fitted to historical launches. Here the vehicle is <b>flown</b>: the book\u2019s Table 6.1 '
           'equations of motion are integrated through an atmosphere, with the drag coefficient a function of '
           'Mach number, and the gravity, drag, propulsion and steering losses are the Eq. 6:58 integrals along '
           'that trajectory. The vehicle rises vertically, is given one pitch kick, and flies the book\u2019s '
           'gravity turn (Sec. 6.4.7) out of the atmosphere; there it changes to linear tangent steering '
           '(Eq. 6:59), solved to arrive level at the insertion altitude, and cuts its engine off when it has the '
           'speed. Up to about 200 km it goes straight in; above that it coasts up and burns again (pp.372-373). '
           'The kick is the one that leaves the most speed in hand. This is a 3-DoF point-mass model in the plane '
           'of the orbit, on a turning spherical Earth: no lift, no wind, no attitude dynamics. Speeds below are '
           'relative to the turning Earth unless they say inertial.</div>']
    if not tr.converged:
        out.append(f'<div class="banner no"><b>The ascent did not close.</b> {_e(tr.status)}.'
                   + (" The figures below are the closest attempt found, not this vehicle's flight." if tr.closest_attempt
                      else "") + "</div>")
    rows = [["Outcome", _e(tr.status)],
            ["Way to orbit", _e(tr.profile_why)],
            ["Pitch kick", f"{tr.kick_deg:.3f} deg after a {tr.vertical_rise_s:.0f} s vertical rise"],
            ["First cutoff" if tr.converged else "End of the flight shown", f"{_f(tr.burnout_v_mps)} m/s at {tr.burnout_h_m/1e3:,.1f} km, flight path angle "
                             f"{tr.burnout_gamma_deg:+.2f} deg, {tr.burnout_t_s:,.0f} s after lift-off"],
            *([["Second burn", f"{_f(tr.second_burn_dv_mps)} m/s, ending {tr.final_state['t_s']:,.0f} s after lift-off"]]
              if tr.second_burn_dv_mps else []),
            *([["Speed in hand at the end", f"<b>{tr.margin_mps:+,.0f} m/s</b>"
                + (f", {_f(tr.propellant_left_kg)} kg of propellant left in the last stage"
                   if tr.propellant_left_kg > 0 else "")]] if tr.converged else []),
            *_orbit_rows(tr),
            ["Downrange at the first cutoff" if tr.converged else "Downrange at the end", f"{tr.downrange_m/1e3:,.0f} km"],
            ["Max dynamic pressure", f"{tr.max_q_Pa/1e3:,.1f} kPa at {tr.max_q_t_s:,.0f} s, "
                                     f"{tr.max_q_h_m/1e3:.1f} km, Mach {tr.max_q_mach:.2f}"],
            ["Peak axial acceleration", f"{tr.max_accel_g:.2f} g"],
            ["Largest thrust-to-velocity angle", f"{tr.max_alpha_deg:.1f} deg (zero during the gravity turn)"]]
    out.append(_tbl(["Ascent", "Value"], rows))
    out.append(_img(figures.get("trajectory_png"),
                    "<b>Figure T.</b> The ascent: altitude and speed, flight path angle and dynamic pressure "
                    "(the book's own checklist on p.379), the ground track with its events, and the loss budget "
                    "the integration produced."))
    out.append(f"<h3>Loss budget to the {'first cutoff' if tr.converged else 'end of the flight shown'}, computed rather than fitted (book Eq. 6:58)</h3>")
    tot = tr.total_loss_mps or 1.0
    lrows = [["Gravity loss", _f(tr.gravity_loss_mps, 1), f"{100*tr.gravity_loss_mps/tot:.1f}",
              "&int; g sin&gamma; dt - the cost of climbing"],
             ["Drag loss", _f(tr.drag_loss_mps, 1), f"{100*tr.drag_loss_mps/tot:.1f}",
              "&int; D/m dt, with Cd(M) from the drag model below"],
             ["Propulsion loss", _f(tr.propulsion_loss_mps, 1), f"{100*tr.propulsion_loss_mps/tot:.1f}",
              "&int; Ae P&infin;/m dt - thrust the ambient pressure takes back (Eq. 6:52)"],
             ["Steering loss", _f(tr.steering_loss_mps, 1), f"{100*tr.steering_loss_mps/tot:.1f}",
              "&int; T(1 &minus; cos&alpha; cos&psi;)/m dt - steering above the atmosphere, and the yaw &psi; that "
              "removes the launch site's speed across the orbit plane"]]
    lrows.append(("sum", ["<b>Total losses</b>", f"<b>{_f(tr.total_loss_mps, 1)}</b>", "100.0", ""]))
    lrows.append(("small", ["Vacuum ideal &Delta;v (rocket equation)", _f(tr.ideal_dv_mps, 1), "",
                            "&int; T_vac/m dt over the powered phases"]))
    lrows.append(("small", ["Closure: ideal &minus; losses &minus; speed gained",
                            f"{tr.closure_residual_mps:+.2e}", "",
                            "the identity of Eq. 6:58; it is the check that this budget is one integration "
                            "decomposed, not four separate estimates"]))
    out.append(_tbl(["Loss", "m/s", "% of losses", "What it is"], lrows, numeric=(1, 2)))
    reg = res.budget.subtotal("loss")
    eq = tr.equivalent_loss_mps
    if reg and eq is not None:
        out.append(f'<p class="small">For comparison, section 1 put the lumped ascent losses at <b>{_f(reg)} m/s</b>. '
                   f'On the same footing - what the budget adds to the orbital speed, less the speed left in hand - this '
                   f'flight cost <b>{_f(eq)} m/s</b>, a difference of {eq - reg:+,.0f} m/s. That figure includes the '
                   f'coast and any second burn, which the table above does not, and leaves out the back pressure the '
                   f'sizing already takes off the first stage’s Isp. The book quotes an RMS error of about 260 m/s '
                   f'for its loss regression.</p>')
    dt = getattr(tr, "drag_table", None)
    if dt:
        out.append("<h3>Drag coefficient, built up from this vehicle's geometry (SUPPLEMENTARY)</h3>")
        shape = "; ".join(f"{b['count']} &times; {_e(b['name'])}, {b['length_m']:.1f} m long, "
                          f"{b['diameter_m']:.2f} m diameter, {b['wetted_area_m2']:,.0f} m&sup2; wetted"
                          for b in dt["bodies"])
        out.append(f'<p class="small">The book gives no method for estimating drag from a shape and points to '
                   f'Missile DATCOM (p.358), so this is a standard preliminary build-up and not a book method: '
                   f'skin friction, pressure drag on the nose and on every flare, boattail and base drag, summed '
                   f'on the reference area of {dt["reference_area_m2"]:.2f} m&sup2;. Lift-off shape: {shape}. '
                   f'Surface roughness {1e6*dt["roughness_m"]:.0f} &micro;m. Each Mach number is evaluated at the '
                   f'altitude this ascent reached it. The shape changes in flight as strap-ons and spent stages '
                   f'leave, and the integration follows it; the table shows the lift-off shape only.</p>')
        drows = [[f"{d['mach']:.1f}", f"{d['altitude_m']/1e3:.1f}", f"{d['friction']:.3f}",
                  f"{d['forebody']:.3f}", f"{d['boattail']:.3f}", f"{d['base']:.3f}",
                  f"<b>{d['total']:.3f}</b>", f"{d['total_power_off']:.3f}", f"{d['book_titan2']:.3f}"]
                 for d in dt["rows"]]
        out.append(_tbl(["Mach", "Altitude [km]", "Skin friction", "Nose and flares", "Boattail", "Base",
                         "Cd, engines on", "Cd, engines off", "Book Titan II curve (Fig. 6.13)"], drows,
                        numeric=(0, 1, 2, 3, 4, 5, 6, 7, 8)))
        out.append('<p class="small"><b>What this leaves out:</b> protuberances and fins, interference between '
                   'the core and its strap-ons, plume effects beyond filling the nozzle exit area, and '
                   'non-circular sections. <code>docs/DRAG.md</code> measures the build-up against published '
                   'wind-tunnel curves. The last column is the single curve every design used to be flown '
                   'on.</p>')
    from .trajectory import timeline as _timeline
    ev = [[f"{e['t_s']:,.1f}", _e(e["name"]), f"{e['h_m']/1e3:.1f}", f"{e['x_m']/1e3:,.0f}", _f(e["v_mps"]),
           "&ndash;" if e["mach"] is None else f"{e['mach']:.2f}", f"{e['gamma_deg']:+.1f}",
           f"{e['q_Pa']/1e3:.1f}", _f(e["mass_kg"])]
          for e in _timeline(tr)]
    out.append("<h3>Event timeline</h3>")
    out.append('<p class="small">Ignitions, the pitch kick, burnouts and jettisons are logged by the integration '
               'as they happen; Mach 1, maximum dynamic pressure and peak axial acceleration (thrust less drag, '
               'over mass) are read from the recorded history. Speed is relative to the launch site. No Mach '
               'number is given above 100 km.</p>')
    out.append(_tbl(["t [s]", "Event", "Altitude [km]", "Downrange [km]", "Speed [m/s]", "Mach", "&gamma; [deg]",
                     "q [kPa]", "Mass [kg]"], ev, numeric=(0, 2, 3, 4, 5, 6, 7, 8)))
    if tr.notes:
        out.append('<p class="small">' + "<br>".join(_e(n) for n in tr.notes) + "</p>")
    return "".join(out)


def _ascent_optimum(res, extras, figures):
    """R5b: the pitch programme optimised, and what the result is worth in payload."""
    opt = (extras or {}).get("ascent_optimum")
    if not opt:
        return ""
    out = ["<h2 id=aopt># Ascent pitch-programme optimisation</h2>",
           '<div class="banner note">Section 6.7 of the book poses this problem and declines to solve it: '
           '"The mathematics behind the theory of optimization is relatively complicated and will not be '
           'presented here" (p.383). What it does supply is the trade, in Sec. 6.10 - climbing vertically '
           'costs gravity loss, so get horizontal early; but a shallow climb costs drag, air loads and '
           'heating, so do not level off too soon. That trade is what is searched here. The objective and the '
           'constraints are the book\u2019s; the search itself is a pattern search of this tool\u2019s own and '
           'is marked supplementary in the method register.</div>']
    if not opt.get("ok"):
        out.append('<div class="banner no"><b>No pitch programme met the limits.</b> '
                   + _e(" ".join(opt.get("notes") or [])) + "</div>")
        return "".join(out)
    b, o = opt["baseline"], opt["best"]
    rows = []
    for lab, c in (("Baseline (the programme flown in the trajectory section)", b), ("Optimised", o)):
        rows.append([lab, f"{c['handover_h_m']/1e3:.1f}", f"{c['max_alpha_deg']:.1f}",
                     f"{c['vertical_rise_s']:.1f}", f"{c['kick_deg']:.3f}", f"{c['margin_mps']:+,.0f}",
                     _f(c["total_loss_mps"]), f"{c['max_q_Pa']/1e3:.1f}",
                     f"{c['max_q_alpha_Pa_deg']/1e3:,.0f}", f"{c['max_accel_g']:.2f}"])
    out.append(_tbl(["Programme", "Hand-over [km]", "Largest &alpha; [deg]", "Vertical rise [s]", "Kick [deg]",
                     "Speed in hand [m/s]", "Total losses [m/s]", "max-q [kPa]", "max q&alpha; [kPa deg]",
                     "max axial [g]"], rows, numeric=tuple(range(1, 10))))
    lim = opt.get("limits") or {}
    lrows = [["Dynamic pressure", f"{lim['max_q_Pa']/1e3:,.1f} kPa" if lim.get("max_q_Pa") else "not set",
              f"reached {o['max_q_Pa']/1e3:,.1f} kPa"],
             ["q&alpha;", f"{lim['max_q_alpha_Pa_deg']/1e3:,.0f} kPa deg" if lim.get("max_q_alpha_Pa_deg")
              else "not set", f"reached {o['max_q_alpha_Pa_deg']/1e3:,.0f} kPa deg"],
             ["Axial acceleration", f"{lim['max_axial_g']:.2f} g" if lim.get("max_axial_g") else "not set",
              f"reached {o['max_accel_g']:.2f} g"],
             ["Burnout flight path angle", f"within {lim.get('max_gamma_burnout_deg', 10):.0f} deg of horizontal",
              f"reached {o['burnout_gamma_deg']:+.2f} deg"]]
    out.append("<h3>What stopped it</h3>")
    out.append(_tbl(["Limit", "Set to", "At the optimum"], lrows))
    bind = opt.get("binding") or {}
    if bind.get("detail"):
        out.append(f'<p>At the optimum: <b>{_e(bind["detail"])}</b>. The limits above are '
                   f'inputs, not findings - the dynamic pressure and q&alpha; defaults are what the book\u2019s '
                   f'own generic vehicle reached in Fig. 9.36, not certified limits for this design, and they '
                   f'are the numbers that decide the answer. Change them and the optimum moves.</p>')
    out.append(_img(figures.get("ascent_opt_png"),
                    "<b>Figure O.</b> The trade of book Fig. 6.26, as numbers: steering over earlier buys "
                    "gravity loss with steering and drag loss, and the limits are what stops it."))
    pb, po = opt.get("payload_baseline") or {}, opt.get("payload_optimum") or {}
    if pb.get("ok") and po.get("ok"):
        out.append("<h3>What it is worth</h3>")
        prows = [["Baseline programme", _f(pb["payload_kg"]), f"{pb['surplus_speed_mps']:+,.0f}"],
                 ["Optimised programme", _f(po["payload_kg"]), f"{po['surplus_speed_mps']:+,.0f}"],
                 ("sum", ["<b>Gain</b>", f"<b>{opt['payload_gain_kg']:+,.0f} kg</b>",
                          f"<b>{opt['speed_gain_mps']:+,.0f} m/s</b>"])]
        out.append(_tbl(["Programme", "Payload to the design orbit [kg]", "Speed in hand [m/s]"],
                        prows, numeric=(1, 2)))
        out.append(f'<p class="small">Both payloads come from flying the vehicle heavier until no speed '
                   f'is left over, with every other thing about the vehicle frozen. So this is what better steering is worth on the vehicle <b>as built</b>, '
                   f'not what a vehicle designed around the better profile would be.</p>')
    out.append(f'<p class="small">{opt["evaluations"]} trajectories were flown in the search. '
               + "<br>".join(_e(n) for n in opt.get("notes") or []) + "</p>")
    return "".join(out)


def _aerodynamics(res, extras, figures):
    """R5c: the normal-force build-up and where it acts."""
    cp = (extras or {}).get("stability")
    if not cp or not cp.get("rows"):
        return ""
    from .aerodynamics import normal_force_buildup
    rows = cp["rows"]
    tr = (extras or {}).get("trajectory")
    mach_q = tr.max_q_mach if tr else rows[len(rows) // 2]["mach"]
    bu = normal_force_buildup(res.geometry, mach_q, cp.get("sref_m2"))
    at_q = min(rows, key=lambda r: abs(r["mach"] - mach_q))
    D = cp["diameter_m"]
    ctl = (extras or {}).get("control")
    out = ["<h2 id=aero># Aerodynamics, static stability and control authority</h2>",
           '<div class="banner note">Drag decides how much speed the ascent costs; the <b>normal</b> force '
           'decides whether the vehicle can be flown at all. It is built up panel by panel over the outer mold '
           'line: a cylinder carries none to first order (book p.577), so only the changes of diameter matter, '
           'and each one acts at the centroid of its own area change. Summing them gives the vehicle\u2019s '
           'normal-force slope and the point it acts through, the centre of pressure. This section locates '
           'that point and compares it with the centre of mass; it does <b>not</b> assess control authority, '
           'which needs the gimbal rates, actuator limits and attitude dynamics this tool does not model.</div>']
    prows = []
    for pa in bu.panels:
        prows.append([_e(pa.panel.name), f"{pa.panel.d_aft:.2f} / {pa.panel.d_fwd:.2f}",
                      f"{pa.ref_area_m2:.2f}", f"{pa.cna_per_rad:.3f}", f"{pa.cna_on_sref:+.3f}",
                      f"{res.geometry.total_length - pa.z_cp_m:.2f}",
                      "stabilising" if pa.stabilising else "destabilising if ahead of the CM"])
    out.append(f"<h3>Panel build-up at Mach {mach_q:.2f} (max-q)</h3>")
    out.append(_tbl(["Panel", "Diameter aft / fwd [m]", "Own A<sub>ref</sub> [m&sup2;]",
                     "C<sub>N&alpha;</sub> [1/rad]", "On S<sub>ref</sub> [1/rad]", "Acts at station [m]",
                     "Sign"], prows, numeric=(2, 3, 4, 5)))
    srows = [["Vehicle normal-force slope C<sub>N&alpha;</sub>", f"{bu.cna_total_per_rad:.3f} /rad",
              f"on S<sub>ref</sub> = {bu.sref_m2:.2f} m&sup2; (the largest cross-section, book p.358)"],
             ["Centre of pressure", f"z = {bu.z_cp_m:.2f} m (station {bu.station_cp_m:.2f} m)",
              "the normal-force-weighted centroid of the panels above"],
             ["Centre of mass at max-q", f"z = {at_q['z_cm_m']:.2f} m (station {at_q['station_cm_m']:.2f} m)",
              "from the mass ledger, drained to the mass the trajectory had at that instant"],
             ["Static margin at max-q", f"{at_q['static_margin_cal']:+.2f} calibers",
              f"(CM &minus; CP) / {D:.2f} m; negative means the CP is ahead of the CM"],
             ["Pitching-moment slope C<sub>m&alpha;</sub>", f"{at_q['cma_per_rad']:+.3f} /rad",
              "positive = a disturbance grows (book p.357). Defined even where the CP is not"]]
    out.append(_tbl(["Quantity", "Value", "What it is"], srows))
    verdict = ("<b>statically unstable</b>" if not at_q["stable"] else "<b>statically stable</b>")
    out.append(f'<p>At max-q this vehicle is {verdict}. For a launch vehicle without fins that is the '
               f'expected result, not a defect: "Most space launchers have no fins and are unstable, so some '
               f'sort of stabilizing system is required to keep the vehicle from diverging from its '
               f'trajectory" (book p.357). What it means in practice is that the engines must keep gimbaling '
               f'to hold attitude; the loads section computes how hard they have to push at max-q, and how '
               f'quickly an uncontrolled disturbance would diverge is a control question this tool does not '
               f'answer.</p>')
    out.append(_img(figures.get("stability_png"),
                    "<b>Figure S.</b> Centre of pressure and centre of mass through the atmospheric ascent, "
                    "and the static margin between them. The CP is fixed by the shape; the CM moves aft as "
                    "the first stage drains, which is why the margin improves through the flight."))
    if cp.get("notes"):
        out.append('<p class="small">' + "<br>".join(_e(n) for n in cp["notes"]) + "</p>")
    if ctl and ctl.checks:
        out.append("<h3>Can it be controlled?</h3>")
        out.append('<p>A statically unstable vehicle is flown by its engines, so the question is whether they '
                   'are strong enough and fast enough. Section 12.3.6 gives three numerical rules of thumb for '
                   'that, and Table 12.4 a way of budgeting the gimbal travel. All four are evaluated at the '
                   'worst instant of the atmospheric ascent, not on average.</p>')
        crows = []
        for c in ctl.checks:
            verdict = ("<b style='color:#117733'>pass</b>" if c["passed"]
                       else "<b style='color:#aa3333'>FAIL</b>")
            crows.append([_e(c["rule"]), _e(c["limit"]), _e(c["value"]), _e(c["at"]), verdict,
                          _e(c["source"])])
        out.append(_tbl(["Check", "Limit", "Worst value", "Where", "Verdict", "Source"], crows))
        b = ctl.budget
        brows = [[_e(k), f"{v:.2f}"] for k, v in b["terms"].items()]
        brows.append(("sum", ["<b>Root-sum-squared</b>", f"<b>{b['rss_deg']:.2f}</b>"]))
        brows.append(("small", ["If every contributor peaked at once", f"{b['worst_case_total_deg']:.2f}"]))
        out.append("<h4>Gimbal deflection budget [deg], after book Table 12.4</h4>")
        out.append(_tbl(["Contributor", "Deflection [deg]"], brows, numeric=(1,)))
        out.append('<p class="small">Only the first line is this vehicle\u2019s own: the rest are the '
                   'book\u2019s Table 12.4 figures for one NASA study of a solid Saturn-class family, used '
                   'here as stand-ins. They are not requirements for this design. Note also that the totals '
                   'printed in that table are about 13 % above the root-sum-square of its own rows, while its '
                   'arithmetic totals match them exactly; the definition the book gives in words is the one '
                   'used here.</p>')
        out.append('<p class="small">' + "<br>".join(_e(n) for n in ctl.notes) + "</p>")
    out.append('<p class="small"><b>What this build-up leaves out.</b> Cylindrical sections are taken to '
               'carry no normal force, which is the book\u2019s own first-order assumption (p.577) but omits '
               'the viscous crossflow a real body develops at angle of attack. That crossflow acts over the '
               'whole body, most of which is behind the nose, so leaving it out puts the centre of pressure '
               '<b>further forward than it really is</b> and the static margin is pessimistic by an amount '
               'this tool cannot quantify. The slender-body slope used by default is also independent of Mach '
               'number, so the CP above does not move with speed; the book\u2019s supersonic charts '
               '(Figs. 9.38\u20139.39) do vary, and chart reads can be supplied per panel through '
               '<code>aerodynamics.cna_overrides</code>. Fins, strap-on boosters and protuberances are not '
               'modelled at all.</p>')
    return "".join(out)


def _loads(res, extras, figures):
    """R8: what the structure has to carry, on the pad and at max-q (book Chapter 9)."""
    cases = (extras or {}).get("loads")
    if not cases:
        return ""
    ordered = [(k, c) for k, c in cases.items() if hasattr(c, "stations")]
    ground = cases.get("ground_wind")
    flight = [(k, c) for k, c in ordered if c.condition == "flight"]
    out = ["<h2 id=loads># Ground and flight loads</h2>",
           '<div class="banner note">The two conditions the book works in full (p.557) are the vehicle clamped to '
           'the pad in a ground wind, fully loaded and <b>unpressurised</b>, and the vehicle in flight at max-q '
           'flying at the angle of attack a horizontal gust forces on it. Lift-off, max-q&alpha; and the instant '
           'of greatest axial acceleration are listed among its load cases but not worked, and are added here. '
           'Each is marched from '
           'the nose down (Eqs. 9:13&ndash;9:19): axial force is the running total of apparent weights above '
           'the station, shear and bending moment the running totals of the lateral air loads and, in flight, '
           'of the d’Alembert inertia relief at every mass. These are global beam loads on the outer shell '
           'and nothing more: no local pressure distribution, no shell stresses, no margins of safety, and no '
           'relief from tank pressurisation, which the book defers to Chapter 10.</div>']

    srows = []
    for key, c in ordered:
        s = c.state
        if c.condition == "ground_wind":
            cond = (f"wind {s['wind_effective_at_top_mps']:.0f} m/s effective at the nose "
                    f"({s['q_at_top_Pa']/1e3:.2f} kPa), n<sub>x</sub> = {s['n_x']:.2f}")
        else:
            cond = (f"t = {s['t_s']:,.0f} s, {s['h_m']/1e3:.1f} km, Mach {s['mach']:.2f}, "
                    f"q = {s['q_Pa']/1e3:.1f} kPa, &alpha; = {s['alpha_deg']:.1f} deg, "
                    f"n<sub>x</sub> = {s['n_x']:.2f}, n<sub>z</sub> = {s['n_z']:.3f}")
        va, sa_ = c.peak("axial_below_N"), c.peak("shear_below_N")
        mo = c.peak("moment_Nm")
        srows.append([_e(c.name), cond, f"{va[0]/1e3:,.0f}", f"{sa_[0]/1e3:,.0f}", f"{mo[0]/1e3:,.0f}",
                      f"{mo[1].z_m:.1f}"])
    out.append(_tbl(["Condition", "State", "Peak axial [kN]", "Peak shear [kN]", "Peak moment [kN m]",
                     "at z [m]"], srows, numeric=(2, 3, 4, 5)))

    considered = cases.get("wind_profiles_considered") or []
    fl = [c for _k, c in flight]
    if considered and fl:
        used = {c.state.get("wind_profile") for c in fl}
        kinds = {c.state.get("wind_profile_kind") for c in fl}
        many = (f" chosen from {len(considered)} profile(s) flown as an ensemble "
                f"({', '.join(_e(n) for n in considered)})" if len(considered) > 1 else "")
        out.append(f'<p class="small"><b>Winds aloft.</b> The flight cases above were produced by '
                   f'<b>{", ".join(_e(n) for n in sorted(n for n in used if n))}</b>'
                   f'{many}. Profile kind: {", ".join(_e(k) for k in sorted(k for k in kinds if k))} '
                   f'(a <i>gust_envelope</i> already contains the gust and is used as the book\'s step 4 '
                   f'asks; a <i>steady</i> profile is a mean wind and carries its gust increment separately). '
                   f'The site\'s own profile replaces the book\'s Atlantic Missile Range 95 % envelope only '
                   f'when the design names one \u2014 see the mission block\'s <span class="mono">wind</span> '
                   f'entry in the input register.</p>')
        if figures.get("wind_png") and os.path.exists(figures["wind_png"]):
            out.append(_img(figures["wind_png"],
                            "<b>Winds aloft used for the flight load cases.</b> Every profile flown, against "
                            "the book's AMR 95 % envelope."))

    gov = cases.get("governing_flight_case")
    if gov and len(flight) > 1:
        out.append(f'<p class="small">The book says plainly that which of max-q and max-q&alpha; governs '
                   f'cannot be known before a trajectory exists (p.572), so both are flown and compared, and '
                   f'the instant of greatest axial acceleration with them. Here <b>{_e(gov)}</b> produces the '
                   f'largest bending moment in flight, <b>{_e(cases.get("governing_axial_case", ""))}</b> the '
                   f'largest axial load, and <b>{_e(cases.get("governing_bending_case", ""))}</b> the largest '
                   f'bending moment of any condition.</p>')
    if ground and flight:
        gm = abs(ground.max_moment_Nm)
        fm = max(abs(c.max_moment_Nm) for _, c in flight)
        if gm > 0 and fm > 0:
            worse = "the ground wind" if gm > fm else "flight"
            out.append(f'<p class="small">Bending is {max(gm, fm)/min(gm, fm):.1f} times larger on '
                       f'{worse}: {gm/1e3:,.0f} kN m at the hold-down plane against {fm/1e3:,.0f} kN m in '
                       f'flight. The same ordering appears in the book’s own Saturn V numbers '
                       f'(67,860 against about 22,000 kN m), because inertia relief has no counterpart on '
                       f'the pad, where the vehicle is a cantilever.</p>')

    out.append(_img(figures.get("loads_png"),
                    "<b>Figure L.</b> Axial force, shear and bending moment against station, for every load "
                    "case. The axial curve closes on the thrust at the gimbal plane and the flight bending "
                    "moment is zero at both ends, as it must be for a free-free beam (p.606)."))

    for key, c in ordered:
        out.append(f"<h3>{_e(c.name)}</h3>")
        rows = []
        for st in c.stations:
            if not any(abs(getattr(st, a)) > 1e-6 for a in
                       ("axial_below_N", "shear_below_N", "moment_Nm")):
                continue
            rows.append([f"{st.z_m:.2f}", f"{st.station_m:.2f}", _e(st.label[:46]),
                         f"{st.axial_below_N/1e3:,.0f}", f"{st.shear_below_N/1e3:,.1f}",
                         f"{st.moment_Nm/1e3:,.0f}"])
        out.append(_tbl(["z [m]", "Station [m]", "At", "Axial [kN]", "Shear [kN]", "Moment [kN m]"],
                        rows, numeric=(0, 1, 3, 4, 5)))
        cl = c.closure
        if c.condition == "flight":
            chk = (f"axial residual at the gimbal plane {cl['axial_residual_N']:+,.1f} N, shear residual "
                   f"{cl['shear_residual_N']:+,.1f} N, bending moment {cl['moment_at_tip_Nm']:+,.1f} N m at "
                   f"the nose and {cl['moment_at_base_Nm']:+,.1f} N m at the base - the vehicle is a "
                   f"free-free beam in flight, so both ends must come out at zero (p.606)")
        else:
            chk = (f"axial at the base minus the vehicle weight {cl['axial_residual_N']:+,.1f} N, shear at the "
                   f"base minus the total wind force {cl['shear_residual_N']:+,.1f} N")
        out.append(f'<p class="small"><b>Closure.</b> {chk}.</p>')
        out.append('<p class="small">' + "<br>".join(_e(n) for n in c.notes) + "</p>")
    return "".join(out)


def _structure(res, extras, figures):
    """R7: what the loads do to the shells, and how thick they have to be (book Chapter 10)."""
    out_s = (extras or {}).get("structure")
    if not out_s:
        return ""
    mat = out_s["material"]
    fs = out_s["factor_of_safety"]
    out = ["<h2 id=struct># Shell stress, buckling and required thickness</h2>",
           f'<div class="banner note">The previous section produced loads; this turns them into stresses and '
           f'into the wall thickness each shell needs to survive them, at a factor of safety of {fs:.2f}. Four '
           f'requirements are evaluated for every shell against every load case: axial strength (Eq. 10.43), '
           f'hoop strength from pressure and the head of accelerating liquid (Eq. 10.44), elastic stability '
           f'(Eqs. 10.45\u201310.46, solved numerically as the book says they must be), and the minimum gauge '
           f'below which there is nothing to buy (Table 10.2). The thickness reported is the largest of those, '
           f'over every case. <b>Nothing here is fed back into the vehicle</b> \u2014 the structural masses in '
           f'the mass statement still come from the Chapter 8 relationships.</div>']
    rows = [["Material", _e(m.name), f"E = {m.E_Pa/1e9:,.0f} GPa, &sigma;<sub>allow</sub> = "
             f"{m.sigma_allow_Pa/1e6:,.0f} MPa, &rho; = {m.rho_kg_m3:,.0f} kg/m&sup3;, &mu; = {m.poisson:.2f}"]
            for m in (out_s.get("materials") or [mat])]
    rows += [
            ["Minimum gauge", f"{mat.t_min_m*1e3:.2f} mm", "book Table 10.2, aluminium skin"],
            ["Factor of safety", f"{fs:.2f}", "the value the book uses throughout Chapter 10"],
            ["Load cases applied", f"{len(out_s['cases'])}", _e(", ".join(out_s["cases"]))]]
    out.append(_tbl(["Setting", "Value", "Note"], rows))

    srows = []
    for sh in out_s["shells"]:
        c = max(sh.cases, key=lambda c: c.t_required_m) if sh.cases else None
        srows.append([_e(sh.name), f"{sh.R_m:.2f}", f"{sh.L_m:.2f}", f"{sh.t_installed_m*1e3:.2f}",
                      f"{c.t_axial_m*1e3:.2f}" if c else "", f"{c.t_hoop_m*1e3:.2f}" if c else "",
                      f"{c.t_buckling_m*1e3:.2f}" if c else "",
                      f"<b>{sh.t_required_m*1e3:.2f}</b>", _e(sh.governing_driver),
                      _e(sh.governing_case[:26]), f"{sh.mass_sized_kg:,.0f}",
                      f"{sh.mass_model_kg:,.0f}" if sh.mass_model_kg else "&ndash;"])
    out.append("<h3>Required thickness, shell by shell</h3>")
    out.append(_tbl(["Shell", "R [m]", "L [m]", "t assumed [mm]", "t axial [mm]", "t hoop [mm]",
                     "t buckling [mm]", "t required [mm]", "Driven by", "Governing case",
                     "Sized mass [kg]", "Model mass [kg]"], srows, numeric=tuple(range(1, 8)) + (10, 11)))

    if out_s.get("mass_model_kg"):
        out.append(f'<p>Summed over the shells the mass model also carries: <b>{out_s["mass_sized_kg"]:,.0f} kg</b> '
                   f'sized as monocoque against <b>{out_s["mass_model_kg"]:,.0f} kg</b> from the Chapter 8 '
                   f'relationships, a factor of <b>{out_s["mass_ratio"]:.2f}</b>. Neither number is wrong. The '
                   f'relationships are fitted to vehicles that are not monocoque, and the difference is the mass '
                   f'that rings, stringers, waffle and isogrid buy back \u2014 the structural efficiency this '
                   f'analysis cannot model, because Chapter 10 describes those concepts (Sec. 10.3.3) without '
                   f'giving allowables for any of them.</p>')
    out.append(_img(figures.get("structure_png"),
                    "<b>Figure St.</b> Required wall thickness along the vehicle, coloured by what drives it, "
                    "against the thickness the design assumed; and the sized shell masses beside the mass "
                    "model's."))
    out.append('<p class="small">' + "<br>".join(_e(n) for n in out_s.get("notes", [])) + "</p>")
    out.append('<p class="small"><b>What is not sized.</b> Monocoque shells only: no rings, stringers, '
               'sandwich, isogrid or orthogrid, because the book gives no allowables or mass-per-area laws for '
               'them. No domes or bulkheads, no joints, welds, cut-outs or local reinforcement, no thermal '
               'stress, no fatigue or fracture, no acoustic or vibration environment, and no combined '
               'stress state \u2014 the book sets that last one aside too ("the calculation of the overall state '
               'of stress is beyond the scope of this book", p.649). Shear is computed and reported but sizes '
               'nothing, following Example 1b, where it needs a twentieth of minimum gauge.</p>')
    return "".join(out)


def _ballistics(res, extras, figures):
    """R6: what the grain actually delivers, against the constant thrust the sizing assumed."""
    profs = [p for p in ((extras or {}).get("ballistics") or []) if p.get("ok")]
    if not profs:
        return ""
    out = ["<h2 id=ball># Solid motor internal ballistics</h2>",
           '<div class="banner note">Every solid stage above was sized on one thrust held for the whole burn. '
           'A grain does not deliver that: mass flow follows the burning area as the grain regresses '
           '(Eq. 4:33) and the burn rate follows the chamber pressure (Eq. 4:32), so the profile is whatever '
           'the grain shape makes it. Three book relations close the loop \u2014 those two and '
           'c* = P<sub>c</sub>A<sub>t</sub>/&#7745; from Table 4.4 \u2014 giving '
           'P<sub>c</sub> = [&rho; a c* A<sub>b</sub>/A<sub>t</sub>]<sup>1/(1&minus;n)</sup>, whose exponent is '
           'the book\u2019s own stability argument: below n = 1 a disturbance settles, above it does not.</div>']
    rows = []
    for p in profs:
        rows.append([f"{p['stage']}", _e(p.get("propellant", "")), f"{p['n']:.2f}",
                     f"{p.get('Kn_start', p['Kn_min']):,.0f} &rarr; {p['Kn_max']:,.0f}",
                     f"{p['design_thrust_N']/1e3:,.0f}",
                     f"{p['thrust_initial_N']/1e3:,.0f} &rarr; {p['thrust_max_N']/1e3:,.0f}",
                     f"{p['thrust_mean_action_N']/1e3:,.0f}",
                     f"{p['pc_design_Pa']/1e6:.1f}", f"{p['pc_max_Pa']/1e6:.1f}",
                     f"{p['design_burn_time_s']:,.0f}", f"{p['action_time_s']:,.1f}",
                     f"{100 * p['tail_fraction']:.0f} %"])
    out.append(_tbl(["Stage", "Propellant", "n", "K<sub>n</sub> = A<sub>b</sub>/A<sub>t</sub>",
                     "Thrust assumed [kN]", "Thrust, start &rarr; peak [kN]", "Mean over the action time [kN]",
                     "P<sub>c</sub> design [MPa]", "P<sub>c</sub> peak [MPa]",
                     "Burn assumed [s]", "Action time [s]", "Burned in the tail"], rows,
                    numeric=(0, 2, 4, 6, 7, 8, 9, 10, 11)))
    for p in ((extras or {}).get("ballistics") or []):
        if not p.get("ok"):
            out.append(f'<p class="small">Stage {p.get("stage")} is not shown: {_e(p.get("reason", ""))}.</p>')
    worst = max(profs, key=lambda p: p["pc_max_Pa"] / max(p["pc_design_Pa"], 1.0))
    ratio = worst["thrust_max_N"] / max(worst["thrust_initial_N"], 1.0)
    out.append(f'<p><b>The simplest grain cannot deliver the thrust the sizing assumed.</b> A plain '
               f'cylindrical bore is <i>progressive</i>: its burning surface grows as it regresses, so thrust '
               f'climbs through the burn \u2014 by a factor of {ratio:.1f} on stage {worst["stage"]}, taking '
               f'chamber pressure to {worst["pc_max_Pa"]/1e6:.1f} MPa against a design of '
               f'{worst["pc_design_Pa"]/1e6:.1f} MPa, which the casing was not sized for. The book says this '
               f'plainly: a cylindrical cutout "will produce thrust levels that increase with time" (p.233), '
               f'and a cog or double-cylinder grain is what buys a constant one. This report does not design '
               f'that grain \u2014 Fig. 4.12 draws those shapes but never dimensions them.</p>')
    out.append(_img(figures.get("ballistics_png"),
                    "<b>Figure B.</b> Thrust and chamber pressure through each solid motor's burn, against "
                    "the constant values the stage was sized on."))
    out.append('<p class="small"><b>How this is anchored.</b> The pressure exponent n comes from the '
               'propellant library (the book gives the typical range 0.4&ndash;0.7 but no value for any '
               'propellant), c* from Table 4.7, and the throat area from Eq. 8:28. The burning-rate '
               'coefficient a is <b>not</b> assumed: it is solved for so that each motor reaches its own '
               'design chamber pressure at its burning area averaged over the propellant, which makes these curves a statement about '
               'the grain shape rather than about a propellant this tool has no measured data for. The whole '
               'grain burns: the bore widens and its ends burn into the domes, so the total impulse is the '
               'sized one. After the bore reaches the case wall only the dome ends are left, burning on a '
               'shrinking surface at a falling pressure; the action time ends where thrust falls below '
               f'{100 * profs[0].get("action_fraction", 0.1):.0f} % of its peak, a common convention and an '
               'assumption here, and the share burned after web burnout is the tail.</p>')
    out.append('<p class="small"><b>What is not modelled.</b> Only the two grain shapes the book describes '
               'completely: the end burner and the hollow cylinder. The star, cog and finocyl grains of '
               'Fig. 4.12 are drawn but never dimensioned, so their burning-area laws are not in this book and '
               'are not invented here. Also absent: erosive burning (described on p.231 without an equation), '
               'ignition and tail-off transients, the factor-of-two burn-rate variation with grain temperature '
               'the book reports on p.233, and any re-sizing of the casing for the peak pressure found above.'
               '</p>')
    return "".join(out)


def _payload_env(res, extras, figures):
    """R13: the quasi-static load factors a payload customer would be given (book Chapter 11)."""
    env = (extras or {}).get("payload_env")
    if not env or not env.rows:
        return ""
    from .payload_env import ARIANE5_QSL, ATLAS5_QSL, TYPICAL_AXIAL_G, TYPICAL_LATERAL_G
    out = ["<h2 id=penv># Payload environment</h2>",
           '<div class="banner note">What the spacecraft customer is handed. Section 11.4 describes a payload '
           'planner\u2019s guide and what it must contain to let a payload be designed: a table of design load '
           'factors by flight event, axial and lateral, each the worst combination of steady and dynamic '
           'acceleration. The steady half below is computed from this vehicle\u2019s own flight; the dynamic '
           'half is <b>not</b> \u2014 it needs a coupled-loads analysis of the vehicle and spacecraft together '
           '\u2014 and is filled from the two real guides the book prints, marked as such.</div>']
    rows = []
    for r in env.rows:
        rows.append([_e(r.event), f"{r.t_s:,.0f}", f"{r.axial_static_g:.2f}", f"&plusmn;{r.axial_dynamic_g:.2f}",
                     f"<b>{r.axial_total_g:.2f}</b>", f"{r.lateral_static_g:.2f}",
                     f"&plusmn;{r.lateral_dynamic_g:.2f}", f"<b>{r.lateral_total_g:.2f}</b>"])
    out.append(_tbl(["Flight event", "t [s]", "Axial steady [g]", "Axial dynamic [g]", "Axial total [g]",
                     "Lateral steady [g]", "Lateral dynamic [g]", "Lateral total [g]"], rows,
                    numeric=tuple(range(1, 8))))
    out.append(f'<p><b>Design load factors: {env.design_axial_g:.1f} g axial</b> '
               f'({_e(env.governing_axial_event)}) and <b>{env.design_lateral_g:.1f} g lateral</b> '
               f'({_e(env.governing_lateral_event)}). The book\u2019s expectation for a preliminary design is '
               f'{TYPICAL_AXIAL_G[0]:.0f}&ndash;{TYPICAL_AXIAL_G[1]:.0f} g axial and '
               f'{TYPICAL_LATERAL_G[0]:.1f}&ndash;{TYPICAL_LATERAL_G[1]:.0f} g lateral (p.691); this vehicle is '
               f'{"inside" if env.within_typical.get("axial") else "<b>outside</b>"} that range axially and '
               f'{"inside" if env.within_typical.get("lateral") else "<b>outside</b>"} it laterally.</p>')
    out.append("<h3>The two real guides the book prints, for comparison</h3>")
    a5 = [[_e(ev), f"{st:+.2f}", f"&plusmn;{dy:.2f}", f"&plusmn;{lat:.2f}"] for ev, st, dy, lat in ARIANE5_QSL]
    out.append("<h4>Ariane 5 (book Table 11.3, ESA) &mdash; negative is compression</h4>")
    out.append(_tbl(["Event", "Longitudinal static [g]", "Longitudinal dynamic [g]",
                     "Lateral static + dynamic [g]"], a5, numeric=(1, 2, 3)))
    av = [[_e(ev), f"{ax:+.2f}", f"&plusmn;{dy:.2f}", f"&plusmn;{lat:.2f}"] for ev, ax, dy, lat in ATLAS5_QSL]
    out.append("<h4>Atlas V (book Table 11.4, ULA)</h4>")
    out.append(_tbl(["Flight condition", "Axial [g]", "Axial dynamic [g]", "Lateral [g]"], av,
                    numeric=(1, 2, 3)))
    out.append('<p class="small">' + "<br>".join(env.notes) + "</p>")
    f = env.flight or {}
    if f:
        from .payload_env import ARIANE6_REFERENCE
        out.append("<h3>What the ascent does to the payload over time</h3>")
        rows = [["Maximum dynamic pressure", f"{_f(f['max_q_kPa'], 1)} kPa at t = {_f(f['max_q_t_s'])} s"],
                ["Highest steady axial load factor", f"{f['max_axial_g']:.2f} g at t = {_f(f['max_axial_t_s'])} s"],
                ["Fastest fall of outside pressure", f"{f['max_dpdt_kPa_s']:.2f} kPa/s at t = {_f(f['max_dpdt_t_s'])} s, "
                 f"{_f(f['max_dpdt_h_m'] / 1e3, 1)} km"]]
        if "jettison_t_s" in f:
            rows += [["Fairing jettison", f"t = {_f(f['jettison_t_s'])} s, {_f(f['jettison_h_m'] / 1e3, 1)} km"],
                     ["Free-molecular flux at and after jettison",
                      f"{_f(f['jettison_fmh_W_m2'])} W/m&sup2; at jettison, at most {_f(f['jettison_fmh_after_W_m2'])} after"]]
        rows.append(["Flux below the limit from", f"t = {_f(f['fmh_ok_from_t_s'])} s, {_f(f['fmh_ok_from_h_m'] / 1e3, 1)} km"
                     if f.get("fmh_ok_from_t_s") else "not within the flight shown"])
        out.append(_tbl(["", "Value"], rows))
        out.append(_img(figures.get("payload_env_png"), "<b>Payload environment in flight.</b> Steady axial load "
                        "factor; free-molecular heat flux 1/2&rho;v&sup3; against the 1,135 W/m&sup2; jettison criterion; "
                        "fall of outside pressure against the 2.5 and 4.0 kPa/s limits under the fairing. Limits from "
                        "Arianespace, Ariane 6 User&rsquo;s Manual, Issue 2 Rev. 0 (Feb. 2021), sec. 3.3.3.2 and 3.2.8.2."))
        out.append('<p class="small">The flux uses the flight&rsquo;s own atmosphere model. The book&rsquo;s exponential '
                   'model keeps one scale height all the way up, and the real atmosphere thins more slowly above about '
                   '90 km, so the altitude where the flux falls under the limit is probably later than a real '
                   'launcher&rsquo;s. The pressure is the outside air&rsquo;s; the pressure under the fairing lags it '
                   'through the vents, so its fall is an upper bound on what the venting must manage.'
                   + ("" if f.get("jettison_ok", True) else " <b>Here the fairing comes off before the flux has fallen "
                      "to the limit.</b> When it comes off is an input: the stage at whose start it is jettisoned.")
                   + "</p>")
        out.append("<h3>Not computed: what a real guide also specifies</h3>")
        out.append('<p class="small">Ariane 6&rsquo;s published figures, as a reference for what a payload is designed '
                   'to, not a result for this vehicle (Arianespace, Ariane 6 User&rsquo;s Manual, Issue 2 Revision 0, '
                   'February 2021).</p>')
        out.append(_tbl(["Environment", "Ariane 6 figure", "Where", "Why it is not computed"],
                        [[_e(x) for x in r] for r in ARIANE6_REFERENCE]))
    return "".join(out)


def _cost(res, extras, figures):
    """R11: development, production and per-flight cost, in work-years first (book Chapter 17, Koelle TRANSCOST 7.2)."""
    c = (extras or {}).get("cost")
    if not c:
        return ""
    m = 1e6

    def money(w):
        return f"${c.usd(w)/m:,.0f} M"
    out = ["<h2 id=cost># Cost</h2>",
           '<div class="banner note">TRANSCOST estimates effort in <b>work-years</b>, which do not change with '
           'inflation or currency, and dollars are work-years times the price of one. The development CERs are the '
           'book\u2019s (Figs. 17.12&ndash;17.16); the factor values, production, learning and operations come from '
           'Koelle, <i>Handbook of Cost Engineering</i>, TRANSCOST 7.2 (2007).</div>']
    out.append("<h3>Development</h3>")
    lo, hi = (c.development_wyr * (1 + k * 0.2) for k in (-1, 1))
    out.append(_tbl(["Quantity", "Work-years", f"Dollars ({c.year})"], [
        ["<b>Development</b>", f"<b>{_f(c.development_wyr)}</b>", f"<b>{money(c.development_wyr)}</b>"],
        ["Range, &plusmn;20 % (book p.998)", f"{_f(lo)} &ndash; {_f(hi)}", f"{money(lo)} &ndash; {money(hi)}"],
        [f"Average team over {c.development_years:.1f} years ({_e(c.development_years_from)})",
         f"{_f(c.average_team)} people", ""]]))
    rows = []
    for x in c.elements:
        rows.append([_e(x["element"]) + (f' <span class="small">({_e(x["note"])})</span>' if x["note"] else ""),
                     x["code"], _e(x["basis"]), _f(x["mass_kg"]), _f(x["wyr_cer"]), f"{x['f1']:.2f}",
                     f"{x['f2']:.2f}" if x["f2"] is not None else "&ndash;", f"{x['f3']:.2f}", f"{x['f8']:.2f}",
                     "<b>already developed</b>" if x["existing"] else f"<b>{_f(x['wyr'])}</b>", _e(x["figure"])])
    out.append(_tbl(["Element", "Code", "Mass basis", "Mass [kg]", "CER [work-years]", "f1", "f2", "f3", "f8",
                     "Effort [work-years]", "Source"], rows, numeric=(3, 4, 9)))
    out.append(f'<p class="small">Total = sum of the efforts &times; f0 = 1.04<sup>{c.n_stages}</sup> = {c.f0:.3f}. '
               f'One work-year is ${c.work_year_usd:,.0f} in {c.year}: {_e(c.work_year_source)}.</p>')
    out.append("<h3>Cost per flight</h3>")
    flights = int(c.inputs["total_flights"])
    out.append(_tbl(["Part", "Work-years", f"Dollars ({c.year})"], [
        [f"Vehicle production, averaged over {flights} vehicles", _f(c.production_wyr), money(c.production_wyr)],
        ["Ground operations", _f(c.ground_wyr), money(c.ground_wyr)],
        ["Launch and mission operations", f"{c.mission_wyr:.1f}", money(c.mission_wyr)],
        ["Indirect (11.5 %; Koelle gives 8 to 15 %)", _f(c.indirect_wyr), money(c.indirect_wyr)],
        ["<b>Cost per flight</b>", f"<b>{_f(c.flight_wyr)}</b>", f"<b>{money(c.flight_wyr)}</b>"],
        [f"With development spread over {flights} flights", _f(c.flight_wyr_with_development),
         money(c.flight_wyr_with_development)]]))
    out.append(_tbl(["Production element", "Units per vehicle", "Mass [kg]", "First unit [work-years]", "Learning p",
                     "f4", "Per vehicle [work-years]", "Source"],
                    [[_e(p["element"]), p["n"], _f(p["mass_kg"]), f"{p['first_unit_wyr']:,.1f}", f"{p['p']:.3f}",
                      f"{p['f4']:.2f}", f"{p['wyr']:,.1f}", _e(p["source"])] for p in c.production],
                    numeric=(1, 2, 3, 4, 5, 6)))
    rows = [["This estimate", _f(c.flight_wyr), money(c.flight_wyr)]]
    if c.trend_wyr is not None:
        rows.append(["Trend of real vehicles (fit of book Table 17.5; scatter +100 %/&minus;50 %, p.1009)",
                     f"{_f(c.trend_wyr)} ({_f(c.trend_band_wyr[0])} &ndash; {_f(c.trend_band_wyr[1])})",
                     money(c.trend_wyr)])
    rows.append(["Rule of thumb, $5,000 per pound (book p.995); the same page gives $2,000 to $120,000", "",
                 f"${c.rule_usd/m:,.0f} M (${c.rule_band_usd[0]/m:,.0f} &ndash; {c.rule_band_usd[1]/m:,.0f} M)"])
    out.append("<h3>Cross-checks</h3>")
    out.append(_tbl(["Basis", "Work-years per flight", "Dollars"], rows))
    if c.comparables:
        crows = []
        for x in c.comparables:
            w = x["wyr_per_flight"]
            lo_, hi_ = x["price_low"] / m, x["price_high"] / m
            crows.append([_e(x["name"]), _f(x["leo_kg"]),
                          "&ndash;" if not w else _f(w[0]) if w[0] == w[1] else f"{_f(w[0])}&ndash;{_f(w[1])}",
                          (f"{lo_:,.0f}" if lo_ == hi_ else f"{lo_:,.0f}&ndash;{hi_:,.0f}") + f" M {x['currency']}"])
        out.append("<h3>Real vehicles of comparable payload (book Table 17.5, ca. 2013)</h3>")
        out.append(_tbl(["Vehicle", "LEO payload [kg]", "Work-years per flight", "Price per flight"], crows,
                        numeric=(1,)))
    out.append('<p class="small">' + "<br>".join(_e(n) for n in c.notes) + "</p>")
    return "".join(out)


def _uncertainty(res, extras, figures):
    """R3: the band around the point estimate."""
    mc = (extras or {}).get("uncertainty")
    if not mc:
        return ""
    lo, hi = mc["p05"], mc["p95"]
    nom = mc["nominal_glom_kg"]
    out = ["<h2 id=unc># Uncertainty</h2>",
           '<div class="banner note">Every mass above is a point estimate from relationships fitted to a '
           f'historical population. Re-sizing the vehicle {mc["n_requested"]:,} times with each MER coefficient '
           'drawn from its assumed scatter gives the band below. <b>Read the band, not the kilogram.</b></div>',
           _img(figures.get("uncertainty_png"),
                "<b>Figure U.</b> Gross lift-off mass under MER scatter, and the one-at-a-time sensitivity that "
                "says which coefficient the answer depends on.")]
    rows = [["Nominal GLOM (the number in section 5)", _f(nom), "-"],
            ["Median of the samples", _f(mc["p50"]), f"{100 * (mc['p50'] / nom - 1):+.1f} %"],
            ["5th percentile", _f(lo), f"{100 * (lo / nom - 1):+.1f} %"],
            ["95th percentile", _f(hi), f"{100 * (hi / nom - 1):+.1f} %"],
            ["Standard deviation", _f(mc["sd_glom_kg"]), f"{100 * mc['sd_glom_kg'] / nom:.1f} %"],
            ["Samples converged", f"{mc['n_converged']:,} of {mc['n_requested']:,}",
             f"{mc['n_failed']:,} failed"]]
    out.append(_tbl(["Quantity", "GLOM [kg]", "Relative to nominal"], rows, numeric=(1, 2)))
    out.append(f'<p><b>Quote this design as {nom:,.0f} kg with a 90 % interval of '
               f'{lo:,.0f} to {hi:,.0f} kg</b> ({100 * (lo / nom - 1):+.0f} % / {100 * (hi / nom - 1):+.0f} %), '
               f'and remember that the interval covers MER scatter only - not a trajectory, loads or a '
               f'structural concept.</p>')
    sens = mc.get("sensitivity") or []
    if sens:
        rows = [[_e(s["parameter"].replace("_", " ")), f"{100 * s['sigma']:.0f} %",
                 f"{100 * s['d_glom_per_sigma']:+.2f} %"] for s in sens]
        out.append("<h3>What the spread is made of</h3>")
        out.append(_tbl(["MER group", "Assumed 1&sigma;".replace("&sigma;", "\u03c3"),
                         "Change in GLOM per +1\u03c3"], rows, numeric=(1, 2)))
    sig = mc.get("sigma") or {}
    out.append('<p class="small">The sigmas are <b>assumptions</b>, listed in '
               '<span class="mono">config/engineering_assumptions.yaml \u2192 mer_scatter</span> and in the input '
               'register: '
               + ", ".join(f"{k.replace('_', ' ')} {100 * v:.0f} %" for k, v in sorted(sig.items()))
               + ". Nobody has published a covariance for the book\u2019s mass-estimating relationships; these are "
                 "engineering judgement anchored on this tool\u2019s own validation, where the median error "
                 "against twelve real vehicles is 17 %. Correlations between groups are not modelled, which makes "
                 "the band, if anything, optimistic.</p>")
    return "".join(out)


def _staging(res, extras, figures):
    """R4: the analytical optimum next to the numerical one."""
    st = (extras or {}).get("staging")
    if not st:
        return ""
    ana = st.get("analytical")
    num = st.get("numerical")
    out = ["<h2 id=stg># Staging optimum</h2>",
           '<div class="banner note">The book solves the optimum split of the \u0394v budget between steps in '
           'closed form with a Lagrange multiplier (Eqs. 5:30-5:33, pp.287-288), on the assumption that each '
           'step\u2019s structural ratio and exhaust speed are fixed. In this tool they are not - a stage\u2019s '
           'structural factor falls out of a mass build-up that depends on its own size - so the two answers '
           'differ, and the difference is a measure of how much that assumption costs.</div>']
    rows = []
    cur = [d / res.dv_required_mps for d in res.allocation]
    rows.append(["This design, as allocated"] + [f"{100 * f:.1f} %" for f in cur] + [_f(res.glom_kg)])
    if ana:
        rows.append(["Analytical optimum (Eqs. 5:32-5:33)"] + [f"{100 * f:.1f} %" for f in ana["fractions"]]
                    + [_f(st.get("analytical_glom_kg")) if st.get("analytical_glom_kg") else "-"])
    if num:
        rows.append(["Numerical optimum (full re-size per evaluation)"]
                    + [f"{100 * f:.1f} %" for f in num["fractions"]] + [_f(num.get("glom_kg"))])
    head = ["Split"] + [f"stage {i + 1}" for i in range(len(res.stages))] + ["GLOM [kg]"]
    out.append(_tbl(head, rows, numeric=tuple(range(1, len(head)))))
    if ana:
        mrows = [[f"{i + 1}", _f(ana["c_eff_mps"][i], 1), f"{ana['sigma'][i]:.4f}",
                  f"{ana['mass_ratios'][i]:.4f}", _f(ana["dv_mps"][i], 1)]
                 for i in range(len(ana["mass_ratios"]))]
        out.append("<h3>Analytical solution</h3>")
        out.append(_tbl(["Step", "c_eff [m/s]", "\u03c3 (converged)", "\u03bc optimum", "\u0394v [m/s]"],
                        mrows, numeric=(1, 2, 3, 4)))
        out.append(f'<p class="small">Lagrange multiplier \u03bb = {ana["lagrange_lambda"]:.6g} s/m '
                   f'(the book prints L = \u2212\u03bb = {ana["lagrange_L"]:.6g}). '
                   f'With equal exhaust speeds and equal structural ratios this reduces to the book\u2019s '
                   f'restricted-staging result, \u0394v/N per step (p.289).</p>')
    if figures.get("staging_png"):
        out.append(_img(figures["staging_png"],
                        "<b>Figure S.</b> Gross lift-off mass against the share of the budget given to stage 1, "
                        "with both optima marked. A flat curve means the split hardly matters; a sharp one means "
                        "it does."))
    return "".join(out)


def _masses(res):
    out = ["<h2 id=mass># Mass statement</h2>"]
    rows = []
    for s in res.stages:
        rows.append([f"{s.index}", _f(s.m_carried_kg), _f(s.m_prop_mission_kg), _f(s.m_startup_kg, 1),
                     _f(s.m_residual_kg, 1), _f(s.m_margin_prop_kg, 1), _f(s.m_prop_loaded_kg),
                     _f(s.m_dry_kg), _f(s.m_inert_burnout_kg), _f(s.m_ignition_kg), _f(s.m_burnout_kg)])
    rows.append(("sum", ["<b>Stack</b>", "", _f(sum(s.m_prop_mission_kg for s in res.stages)),
                         _f(sum(s.m_startup_kg for s in res.stages), 1),
                         _f(sum(s.m_residual_kg for s in res.stages), 1),
                         _f(sum(s.m_margin_prop_kg for s in res.stages), 1),
                         _f(sum(s.m_prop_loaded_kg for s in res.stages)),
                         _f(sum(s.m_dry_kg for s in res.stages)), "",
                         f"<b>{_f(res.glom_kg)}</b>", ""]))
    out.append(_tbl(["Stage", "Carried above [kg]", "Mission prop. [kg]", "Start-up [kg]", "Residual [kg]",
                     "Loading margin [kg]", "Loaded prop. [kg]", "Dry [kg]", "Inert at burnout [kg]",
                     "Ignition [kg]", "Burnout [kg]"], rows, numeric=tuple(range(1, 11))))
    out.append('<p class="small">"Carried above" is everything above the stage at its ignition — payload, '
               'adapter, the fairing while it is still attached, and every upper stage fully loaded. '
               '"Inert at burnout" is dry + residual + loading margin, the mass the structural factor s uses.</p>')
    out.append("<h3>GLOM build-up</h3>")
    br = [["Payload", _f(res.payload_mass_kg)], ["Payload adapter", _f(res.paf_mass_kg, 1)],
          ["Fairing", _f(res.fairing_mass_kg, 1)]]
    for s in res.stages:
        br.append([f"Stage {s.index} dry", _f(s.m_dry_kg)])
        br.append([f"Stage {s.index} propellant loaded", _f(s.m_prop_loaded_kg)])
    if res.boosters is not None:
        br.append([f"Boosters ({res.boosters.n_total} x {_e(res.boosters.name)})", _f(res.boosters.m_total_kg)])
    tot = (res.payload_mass_kg + res.paf_mass_kg + res.fairing_mass_kg
           + sum(s.m_dry_kg + s.m_prop_loaded_kg for s in res.stages)
           + (res.boosters.m_total_kg if res.boosters is not None else 0.0))
    br.append(("sum", ["<b>GLOM</b>", f"<b>{_f(tot)}</b>"]))
    br.append(("small", ["Closure against the sized GLOM", f"{tot - res.glom_kg:+.3f} kg"]))
    out.append(_tbl(["Item", "Mass [kg]"], br, numeric=(1,)))
    out.append("<h3>Dry-mass breakdown by component</h3>")
    for s in res.stages:
        if not s.components:
            continue
        items = sorted(s.components.items(), key=lambda kv: -kv[1])
        tot_c = sum(v for _, v in items)
        cr = [[_e(k), _f(v, 1), f"{100 * v / tot_c:.1f}" if tot_c else "-"] for k, v in items]
        cr.append(("sum", ["<b>Stage dry mass</b>", f"<b>{_f(tot_c, 1)}</b>", "100.0"]))
        label = "" if s.name.strip().lower() == f"stage {s.index}" else f" — {_e(s.name)}"
        out.append(f"<h4>Stage {s.index}{label}</h4>")
        out.append(_tbl(["Component", "Mass [kg]", "% of dry"], cr, numeric=(1, 2)))
    return "".join(out)


def _ledger(res):
    out = ["<h2 id=ledger># Mass ledger and mass properties</h2>",
           '<p class="small">Every mass in the vehicle, where it sits on the axis, which shape it was given for '
           'inertia, and the rule it came from. This table is the input to the centre-of-mass and inertia '
           'calculation and to Figure 2.</p>']
    # 0, -1 and -2 are the ledger's numbers for the payload, the fairing and the strap-ons; "upper" used to
    # stand for both of the last two, which put the boosters at the top of the vehicle
    where = {0: "payload", -1: "fairing", -2: "boosters"}
    from .mass_properties import at_liftoff, liftoff_total
    rows = [[_e(i.stage) if i.stage >= 1 else where.get(i.stage, "-"), _e(i.group),
             _e(i.name) + ("" if at_liftoff(res, i) else " <i>(at burnout; inside the loaded propellant)</i>"),
             _f(i.mass_kg, 1), f"{i.z_m:.3f}", _e(i.kind), _e(i.shape), _e(i.source)] for i in res.ledger]
    rows.append(("sum", ["", "", "<b>Total at lift-off</b>", f"<b>{_f(liftoff_total(res))}</b>",
                         "", "", "", ""]))
    out.append("<details open><summary>Full mass ledger (%d items)</summary>" % len(res.ledger))
    out.append(_tbl(["Stage", "Group", "Component", "Mass [kg]", "z_cm [m]", "Kind", "Inertia shape",
                     "Source / assumption"], rows, numeric=(3, 4)))
    out.append("</details>")
    mp = res.mass_properties or {}
    ev = mp.get("events") or []
    if ev:
        er = [[_e(e["event"]), _f(e["mass_kg"]), f"{e['z_cm_m']:.3f}", f"{e['z_cm_over_L']:.3f}",
               _f(e["J_roll"]), _f(e["J_pitch"]), f"{e['roll_to_pitch_ratio']:.4f}", _e(e.get("note") or "")]
              for e in ev]
        out.append("<h3>Centre of mass and inertia through the flight events</h3>")
        out.append(_tbl(["Event", "Mass [kg]", "z_cm [m]", "z_cm/L", "J_roll [kg m²]", "J_pitch [kg m²]",
                         "J_roll/J_pitch", "Note"], er, numeric=(1, 2, 3, 4, 5, 6)))
    if mp.get("warnings"):
        out.append('<p class="small">' + "<br>".join(_e(w) for w in mp["warnings"]) + "</p>")
    return "".join(out)


def _geometry(res):
    g = res.geometry
    out = ["<h2 id=geo># Geometry</h2>"]
    rows = [[_e(s.stage) if s.stage else "-", _e(s.kind), _e(s.name), f"{s.z0:.3f}", f"{s.z1:.3f}",
             f"{s.length:.3f}", f"{s.d_bot:.3f}", f"{s.d_top:.3f}"] for s in g.segments]
    out.append("<details open><summary>Segment table (%d segments, bottom to top)</summary>" % len(g.segments))
    out.append(_tbl(["Stage", "Kind", "Component", "z bottom [m]", "z top [m]", "Length [m]",
                     "D bottom [m]", "D top [m]"], rows, numeric=tuple(range(3, 8))))
    out.append("</details>")
    tr = []
    for s in res.stages:
        for t in (s.tanks or []):
            tr.append([f"{s.index}", _e(t.role), _e(t.propellant), _f(t.V_int, 3), _f(t.V_liquid, 3),
                       _f(2 * t.R_int, 3), _f(t.AR, 3), _f(t.h_cyl, 3), _f(t.h_dome, 3), _f(t.L_ext, 3),
                       _f(t.area_ext, 2), _f(t.mass_tank_kg, 1), _f(t.mass_insulation_kg, 1),
                       _e(t.mass_method), _e(t.bulkhead)])
    if tr:
        out.append("<h3>Tank / motor-case geometry (book Eqs. 8:13-8:16, Table 8.2; solids Eqs. 8:23-8:24)</h3>")
        out.append(_tbl(["Stage", "Role", "Propellant", "V internal [m³]", "V liquid [m³]", "D internal [m]",
                         "Dome AR", "Barrel L [m]", "Dome h [m]", "External L [m]", "External area [m²]",
                         "Tank mass [kg]", "Insulation [kg]", "Mass method", "Bulkhead"], tr,
                        numeric=tuple(range(3, 13))))
        notes = [f"Stage {s.index} {t.role}: {n}" for s in res.stages for t in (s.tanks or []) for n in (t.notes or [])]
        if notes:
            out.append('<p class="small">' + "<br>".join(_e(n) for n in notes) + "</p>")
    tot = [["Overall length", f"{g.total_length:.3f} m"],
           ["Maximum diameter", f"{g.max_diameter:.3f} m"],
           ["Maximum span (incl. boosters)", f"{g.max_span_m:.3f} m"],
           ["Length / diameter", f"{g.total_length / g.max_diameter:.2f}"],
           ["Payload envelope", f"z = {g.payload_z0:.3f} to {g.payload_z1:.3f} m"]]
    out.append(_tbl(["Overall", "Value"], tot))
    return "".join(out)


def _inputs(res):
    reg = res.spec.inputs_register or []
    groups = [("Mission and orbit", ("mission.",)),
              ("Vehicle, payload and fairing", ("vehicle.", "fairing.", "payload")),
              ("Stages, propulsion and tanks", ("stages.", "boosters.")),
              ("Engineering assumptions and MER coefficients", ("assumptions.", "mer.", "propellants.",
                                                                "solid_propellants.", "constraints.",
                                                                "convergence.", "earth"))]
    used = set()
    out = ["<h2 id=inputs># Input register</h2>",
           '<p class="small">Every input the model read, with its units, what it means, where the value came from, '
           'and how it is classified. Nothing else was used; nothing here was tuned to make a result match a real '
           'vehicle.</p>',
           '<div class="legend">'
           '<span><i class="p-user"></i>user — a requirement or a choice the designer made</span>'
           '<span><i class="p-reference"></i>reference — taken from the book or a cited source</span>'
           '<span><i class="p-assumed"></i>assumed — a placeholder that should be replaced by real data</span>'
           "</div>"]
    counts = {}
    for r in reg:
        counts[r["provenance"]] = counts.get(r["provenance"], 0) + 1
    out.append('<p class="small">' + ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
               + f", {len(reg)} inputs in total.</p>")
    for title, prefixes in groups:
        rows = []
        for i, r in enumerate(reg):
            if i in used or not any(r["path"].startswith(p) for p in prefixes):
                continue
            used.add(i)
            v = r["value"]
            v = ", ".join(map(str, v)) if isinstance(v, list) else v
            rows.append((f"p-{PROV_LABEL.get(r['provenance'], 'calculated')}",
                         [f'<span class="mono">{_e(r["path"])}</span>', _e(v), _e(r["units"]),
                          _e(r["description"]), _e(r["source"]), _e(r["provenance"])]))
        if rows:
            out.append(f"<details><summary>{_e(title)} ({len(rows)} inputs)</summary>")
            out.append(_tbl(["Input (config path)", "Value", "Units", "Description", "Source / justification",
                             "Provenance"], rows, numeric=(1,)))
            out.append("</details>")
    rest = [(i, r) for i, r in enumerate(reg) if i not in used]
    if rest:
        rows = [(f"p-{PROV_LABEL.get(r['provenance'], 'calculated')}",
                 [f'<span class="mono">{_e(r["path"])}</span>',
                  _e(", ".join(map(str, r["value"])) if isinstance(r["value"], list) else r["value"]),
                  _e(r["units"]), _e(r["description"]), _e(r["source"]), _e(r["provenance"])])
                for _, r in rest]
        out.append(f"<details><summary>Other inputs ({len(rows)})</summary>")
        out.append(_tbl(["Input (config path)", "Value", "Units", "Description", "Source / justification",
                         "Provenance"], rows, numeric=(1,)))
        out.append("</details>")
    return "".join(out)


def _issues(res):
    out = ["<h2 id=chk># Checks and warnings</h2>"]
    order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
    iss = sorted(res.issues, key=lambda i: order.get(i.level, 3))
    if not iss:
        out.append('<p class="small">No checks reported anything.</p>')
        return "".join(out)
    rows = [(f"lvl-{i.level}", [_e(i.level), f'<span class="mono">{_e(i.code)}</span>', _e(i.message)])
            for i in iss]
    out.append(_tbl(["Level", "Code", "Message"], rows))
    nerr = sum(1 for i in iss if i.level == "ERROR")
    nwarn = sum(1 for i in iss if i.level == "WARNING")
    out.append(f'<p class="small">{nerr} errors, {nwarn} warnings. Warnings are not failures: they mark places '
               f'where the model is being used near or outside the range its methods were fitted for.</p>')
    for s in res.stages:
        if s.warnings:
            out.append(f'<p class="small"><b>Stage {s.index}:</b> ' + "<br>".join(_e(w) for w in s.warnings) + "</p>")
    return "".join(out)


def _methods(res):
    out = ["<h2 id=meth># Engineering method register</h2>",
           '<p class="small">Every calculation in the tool, its formulation, the verified book page it comes from '
           '(printed page numbers; "SUPPLEMENTARY" means it is <b>not</b> claimed to be in the book), its '
           'assumptions and limits, where it is implemented, and how it is verified.</p>',
           "<details><summary>Method register (%d methods)</summary>" % len(REGISTER),
           _tbl(FIELDS, [[_e(c) for c in row] for row in REGISTER]), "</details>"]
    return "".join(out)


def _toc(sections):
    links = "".join(f'<a href="#{sid}">{i}. {_e(title)}</a>' for i, (sid, title) in enumerate(sections, 1))
    return f"<h2>Contents</h2><div class=toc>{links}</div>"


def _number_sections(body: str, sections: list) -> str:
    """Give every section its number, from the one list the contents is also built from.

    Section headings are written as `<h2 id=xxx># Title</h2>`; the number is filled in here. Keeping the
    numbers in exactly one place means adding or removing a section cannot leave the document numbered in two
    different ways, which is the mistake this replaces.
    """
    for i, (sid, _title) in enumerate(sections, 1):
        body = body.replace(f"<h2 id={sid}># ", f"<h2 id={sid}>{i}. ", 1)
    left = [s for s in body.split("<h2 id=")[1:] if s.lstrip().split(">", 1)[-1].startswith("# ")]
    if left:
        raise AssertionError(f"{len(left)} report section(s) are not listed in the contents and stayed unnumbered")
    return body


# --------------------------------------------------------------------------- public API
def build_html(res, figures: dict | None = None, design_path: str = "", assump_path: str = "",
               extras: dict | None = None) -> str:
    """Return the complete report as one self-contained HTML string.

    `extras` carries the optional studies: {"performance": ..., "uncertainty": ..., "staging": ...}. Each one adds
    its own section when present and is silently absent otherwise, so a quick run and a full run produce the same
    document structure minus the parts that were not computed.
    """
    figures = figures or {}
    extras = extras or {}
    sections = [("req", "Mission requirement and delta-v budget"), ("cfg", "Vehicle configuration"),
                ("drw", "Drawings"), ("perf", "Propulsion and performance")]
    if extras.get("performance"):
        sections.append(("cap", "Payload capability"))
    if extras.get("trajectory"):
        sections.append(("traj", "Ascent trajectory"))
    if extras.get("ascent_optimum"):
        sections.append(("aopt", "Ascent pitch-programme optimisation"))
    if extras.get("stability"):
        sections.append(("aero", "Aerodynamic build-up and centre of pressure"))
    if extras.get("loads"):
        sections.append(("loads", "Ground and flight loads"))
    if extras.get("structure"):
        sections.append(("struct", "Shell stress, buckling and required thickness"))
    if any(p.get("ok") for p in (extras.get("ballistics") or [])):
        sections.append(("ball", "Solid motor internal ballistics"))
    if extras.get("payload_env") and extras["payload_env"].rows:
        sections.append(("penv", "Payload environment"))
    if extras.get("cost"):
        sections.append(("cost", "Cost"))
    sections += [("mass", "Mass statement"), ("ledger", "Mass ledger and mass properties"),
                 ("geo", "Geometry")]
    if extras.get("uncertainty"):
        sections.append(("unc", "Uncertainty"))
    if extras.get("staging"):
        sections.append(("stg", "Staging optimum"))
    sections += [("inputs", "Input register"), ("chk", "Checks and warnings"),
                 ("meth", "Engineering method register")]
    body = "".join([_cover(res, design_path, assump_path, figures),
                    _summary(res, extras, figures), _limits(res, extras), _toc(sections),
                    _requirement(res), _config(res), _drawings(res, figures), _performance(res),
                    _capability(res, extras, figures), _trajectory(res, extras, figures),
                    _ascent_optimum(res, extras, figures), _aerodynamics(res, extras, figures),
                    _loads(res, extras, figures), _structure(res, extras, figures),
                    _ballistics(res, extras, figures), _payload_env(res, extras, figures),
                    _cost(res, extras, figures),
                    _masses(res), _ledger(res), _geometry(res),
                    _uncertainty(res, extras, figures), _staging(res, extras, figures),
                    _inputs(res), _issues(res), _methods(res)])
    body = _number_sections(body, sections)
    foot = (f'<div class="meta"><span>MERLIN {_e(__version__)}</span>'
            f'<span>{_e(res.spec.name)}</span>'
            f'<span>generated {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}</span>'
            f'<span>g0 = {G0} m/s2</span>'
            f'<span>Conceptual sizing only \u2014 not a design qualification</span></div>')
    return ("<!DOCTYPE html><html lang=en><head><meta charset=utf-8>"
            f"<title>{_e(res.spec.name)} - design report</title>"
            '<meta name=viewport content="width=device-width,initial-scale=1">'
            f"<style>{CSS}</style></head><body><div class=page>{body}{foot}</div></body></html>")


def write_report(res, path, figures: dict | None = None, design_path: str = "", assump_path: str = "",
                 pdf: bool = False, extras: dict | None = None) -> dict:
    """Write the HTML report to `path`. With pdf=True also try to convert it. Returns the paths written."""
    htm = build_html(res, figures, design_path, assump_path, extras)
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(htm)
    out = {"html": path}
    if pdf:
        p, note = to_pdf(path)
        if p:
            out["pdf"] = p
        else:
            out["pdf_note"] = note
    return out


def to_pdf(html_path, pdf_path=None):
    """Convert a written HTML report to PDF with whatever converter is installed.

    Returns (pdf_path, None) on success or (None, explanation) when no converter is available. The HTML is always
    the primary artefact: any browser prints it to PDF with the report's own A4 print stylesheet.
    """
    pdf_path = pdf_path or os.path.splitext(html_path)[0] + ".pdf"
    import glob
    cands = ["chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome"]
    cands += sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"), reverse=True)
    cands += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              # Edge is Chromium and ships with Windows, so this makes PDF work on any Windows machine
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]
    chrome = next((c for c in cands if (shutil.which(c) if os.sep not in c else os.path.exists(c))), None)
    if chrome:
        with tempfile.TemporaryDirectory() as tmp:
            cmd = [chrome, "--headless", "--disable-gpu", "--no-sandbox", f"--user-data-dir={tmp}",
                   "--no-pdf-header-footer", f"--print-to-pdf={pdf_path}",
                   "file://" + os.path.abspath(html_path)]
            try:
                subprocess.run(cmd, check=True, capture_output=True, timeout=300)
                if os.path.exists(pdf_path):
                    return pdf_path, None
            except (subprocess.SubprocessError, OSError) as ex:
                last = f"headless Chromium failed: {ex}"
            else:
                last = "headless Chromium produced no file"
    else:
        last = "no Chromium/Chrome found"
    if shutil.which("wkhtmltopdf"):
        try:
            subprocess.run(["wkhtmltopdf", "--enable-local-file-access", "-q", os.path.abspath(html_path),
                            pdf_path], check=True, capture_output=True, timeout=300)
            if os.path.exists(pdf_path):
                return pdf_path, None
        except (subprocess.SubprocessError, OSError) as ex:
            last += f"; wkhtmltopdf failed: {ex}"
    return None, (f"{last}. The HTML report is complete and self-contained - open it in any browser and print to "
                  f"PDF (the report carries its own A4 print stylesheet).")
