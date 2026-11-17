"""Excel engineering workbook (openpyxl), CSV exports and the method register.

The Python model is the authoritative calculation engine. The workbook REPORTS its outputs; a handful of cells are
live Excel formulas (totals, mass ratio, delta-v recomputation, volumes, closure checks) so a reviewer can audit the
numbers independently. Editing the workbook does NOT re-run the model: the YAML configuration is the source of truth.
"""
from __future__ import annotations
import csv
import datetime
import os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.drawing.image import Image as XLImage
from . import __version__
from .method_register import REGISTER, FIELDS

FONT = "Arial"
HDR = PatternFill("solid", fgColor="1F3864")
F_USER = PatternFill("solid", fgColor="DDEBF7")
F_REF = PatternFill("solid", fgColor="E2EFDA")
F_ASM = PatternFill("solid", fgColor="FFF2CC")
F_CALC = PatternFill("solid", fgColor="F2F2F2")
PROV_FILL = {"user": F_USER, "reference": F_REF, "assumed": F_ASM}
thin = Side(style="thin", color="BFBFBF")
BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)


def _hdr(ws, row, headers, col0=1):
    for j, h in enumerate(headers):
        c = ws.cell(row=row, column=col0 + j, value=h)
        c.font = Font(name=FONT, bold=True, color="FFFFFF", size=10)
        c.fill = HDR
        c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        c.border = BORDER


def _title(ws, text, sub=None):
    ws["A1"] = text
    ws["A1"].font = Font(name=FONT, bold=True, size=14, color="1F3864")
    if sub:
        ws["A2"] = sub
        ws["A2"].font = Font(name=FONT, italic=True, size=9, color="595959")


def _widths(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def write_table(ws, r0, cols, rows, fill=None):
    """cols: list of (header, key, number_format, formula_template|None). Formula templates use {key} -> cell ref in same row.
    Returns (first_data_row, last_data_row, {key: column_letter})."""
    letters = {k: get_column_letter(i + 1) for i, (_, k, _, _) in enumerate(cols) if k}
    _hdr(ws, r0, [c[0] for c in cols])
    for i, row in enumerate(rows):
        r = r0 + 1 + i
        for j, (h, k, fmt, ftpl) in enumerate(cols):
            c = ws.cell(row=r, column=j + 1)
            if ftpl:
                c.value = ftpl.format(**{kk: f"{ll}{r}" for kk, ll in letters.items()}, r=r)
                c.fill = F_CALC
            else:
                c.value = row.get(k)
                if fill:
                    c.fill = fill
            c.font = Font(name=FONT, size=10)
            c.border = BORDER
            if fmt:
                c.number_format = fmt
    return r0 + 1, r0 + len(rows), letters


# ---------------------------------------------------------------------------------------------------------
def write_register(path_xlsx=None, wb=None, path_csv=None):
    own = wb is None
    wb = wb or Workbook()
    ws = wb.active if own else wb.create_sheet("Engineering_References")
    ws.title = "Engineering_References"
    _title(ws, "Engineering method register", "Book = Edberg & Costa, Design of Rockets and Space Launch Vehicles, 2nd ed. (AIAA 2022). "
           "Page numbers are PRINTED page numbers verified in the supplied PDF. 'SUPPLEMENTARY' rows are not claimed to be in the book.")
    _hdr(ws, 4, FIELDS)
    for i, row in enumerate(REGISTER):
        for j, v in enumerate(row):
            c = ws.cell(row=5 + i, column=j + 1, value=v)
            c.font = Font(name=FONT, size=9)
            c.alignment = Alignment(wrap_text=True, vertical="top")
            c.border = BORDER
        if "SUPPLEMENTARY" in row[6]:
            ws.cell(row=5 + i, column=7).fill = F_ASM
        else:
            ws.cell(row=5 + i, column=7).fill = F_REF
    _widths(ws, [6, 26, 44, 24, 18, 38, 20, 34, 34, 30, 34])
    ws.freeze_panes = "C5"
    ws.auto_filter.ref = f"A4:{get_column_letter(len(FIELDS))}{4 + len(REGISTER)}"
    r = 6 + len(REGISTER)
    ws.cell(row=r, column=1, value="Global modelling limitations").font = Font(name=FONT, bold=True)
    for k, t in enumerate([
        "Preliminary conceptual-design fidelity: delta-v losses are user estimates; no trajectory simulation, aerodynamic loads, stability/control, thermal, or structural qualification.",
        "Expendable vehicles only: serial liquid and/or solid stages plus at most one set of strap-on boosters (ground-lit, optionally with a second air-lit group). "
        "Propellant crossfeed, recovery hardware, air-breathing stages and multiple booster sets are NOT implemented.",
        "MERs are statistical fits (~3 significant digits at best) and inherit the conservatism/age of their source data.",
        "Constant-thrust, constant-Isp burn per stage; throttling and thrust tail-off are not modelled."]):
        ws.cell(row=r + 1 + k, column=1, value=f"- {t}").font = Font(name=FONT, size=9)
    if path_csv:
        with open(path_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(FIELDS)
            w.writerows(REGISTER)
    if own and path_xlsx:
        wb.save(path_xlsx)
    return wb


def _inputs_sheet(wb, name, title, reg, prefixes):
    ws = wb.create_sheet(name)
    _title(ws, title, "Colour code: blue = user-defined, green = reference-based, amber = assumed. Source of truth: the YAML configuration (this sheet is a report).")
    rows = [dict(path=r["path"], value=(", ".join(map(str, r["value"])) if isinstance(r["value"], list) else r["value"]), units=r["units"],
                 description=r["description"], source=r["source"], provenance=r["provenance"], status="validated")
            for r in reg if any(r["path"].startswith(p) for p in prefixes)]
    cols = [("Input name (config path)", "path", None, None), ("Value", "value", "General", None), ("Units", "units", None, None),
            ("Description", "description", None, None), ("Source / justification", "source", None, None),
            ("Provenance", "provenance", None, None), ("Validation", "status", None, None)]
    f, l, _ = write_table(ws, 4, cols, rows)
    for r in range(f, l + 1):
        ws.cell(row=r, column=6).fill = PROV_FILL.get(ws.cell(row=r, column=6).value, F_CALC)
        for c in range(1, 8):
            ws.cell(row=r, column=c).alignment = Alignment(wrap_text=True, vertical="top")
    _widths(ws, [44, 18, 10, 56, 56, 12, 12])
    ws.freeze_panes = "B5"
    ws.auto_filter.ref = f"A4:G{max(l, 5)}"
    return ws


def write_workbook(res, path, figures: dict | None = None, sens_rows=None, comp_rows=None, opt=None, design_path="", loads=None, ascent_opt=None, structure=None):
    figures = figures or {}
    wb = Workbook()
    spec, geom = res.spec, res.geometry
    # ---------------- README
    ws = wb.active
    ws.title = "README"
    _title(ws, "MERLIN - Engineering Workbook", f"Design: {spec.name} | generated {datetime.datetime.now():%Y-%m-%d %H:%M} | software v{__version__}")
    lines = ["PURPOSE: report inputs, intermediate calculations and results of the Python sizing engine (authoritative). Editing this file does NOT re-run the model.",
             f"SOURCE OF TRUTH: configuration file {design_path or '(see config/)'} - edit it and rerun: python -m launch_vehicle.main run --design <file>",
             "SHEETS: Mission_Inputs, Vehicle_Inputs, Stage_Inputs, DeltaV_Budget, Stage_Sizing, Parallel_Burn (only with strap-ons), Mass_Breakdown, Tank_Sizing, Geometry, Mass_Properties, Results_Dashboard, Sensitivity, Engineering_References.",
             "COLOUR CODE: blue = user input, green = reference-based, amber = assumed, grey = live Excel formula (audit cross-check of the Python value).",
             "MODEL LIMITATIONS: preliminary fidelity; no trajectory simulation, loads, stability, thermal or structural qualification. Expendable vehicles with serial liquid and/or "
             "solid stages and one set of strap-on boosters; no crossfeed, no recovery hardware, no throttling profile.",
             "THE TOOL DOES NOT PROVE THAT A GIVEN ORBIT IS ACHIEVABLE; a closed mass budget means only that the stated assumptions are self-consistent.",
             "CONVENTIONS: SI units; z measured upward from the stage-1 nozzle exit plane; O/F = m_ox/m_fuel; structural factor s = m_inert/(m_inert + m_prop) (Book Eq. 5:5a).",
             "Book = Edberg & Costa, Design of Rockets and Space Launch Vehicles, 2nd ed.; page numbers are printed page numbers verified in the supplied PDF."]
    for i, t in enumerate(lines):
        c = ws.cell(row=4 + i, column=1, value=t)
        c.font = Font(name=FONT, size=10)
        c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.column_dimensions["A"].width = 150

    reg = spec.inputs_register
    _inputs_sheet(wb, "Mission_Inputs", "Mission inputs", reg, ["mission"])
    _inputs_sheet(wb, "Vehicle_Inputs", "Vehicle, fairing, constraints and global assumptions", reg, ["vehicle", "fairing", "constraints", "earth_model", "mer", "convergence", "propellants", "tank_materials"])
    _inputs_sheet(wb, "Stage_Inputs", "Stage inputs (normalised: one row per input)", reg, ["stages"])

    # ---------------- DeltaV_Budget
    ws = wb.create_sheet("DeltaV_Budget")
    _title(ws, "Mission delta-v budget", "Sign convention: positive = adds to launch-vehicle requirement; Earth-rotation benefit is negative. Margin applied once to the subtotal.")
    b = res.budget
    rows = [dict(name=l.name, cat=l.category, val=l.value_mps, src=l.source, inc="yes" if l.in_total else "no (informational)") for l in b.lines]
    cols = [("Line item", "name", None, None), ("Category", "cat", None, None), ("Value [m/s]", "val", "#,##0.0", None),
            ("Included in total", "inc", None, None), ("Source / justification", "src", None, None)]
    f, l, _ = write_table(ws, 4, cols, rows)
    r = l + 2
    ws.cell(row=r, column=1, value="TOTAL launch-vehicle delta-v requirement [m/s] (Excel SUM of included lines)").font = Font(name=FONT, bold=True)
    ws.cell(row=r, column=3, value=f'=SUMIF(D{f}:D{l},"yes",C{f}:C{l})').number_format = "#,##0.0"
    ws.cell(row=r + 1, column=1, value="TOTAL from Python engine [m/s]")
    ws.cell(row=r + 1, column=3, value=res.dv_required_mps).number_format = "#,##0.0"
    ws.cell(row=r + 2, column=1, value="Difference (should be 0)")
    ws.cell(row=r + 2, column=3, value=f"=C{r}-C{r+1}").number_format = "0.000"
    el = b.info["orbit"]
    info = [("Orbit type", b.info["orbit_type"]), ("Earth model", b.info["earth_model"]), ("Inclination [deg]", b.info["inclination_deg"]),
            ("Launch azimuth [deg]", b.info["azimuth_deg"]), ("Azimuth source", b.info["azimuth_source"]), ("Perigee altitude [km]", el.perigee_alt_m / 1e3),
            ("Apogee altitude [km]", el.apogee_alt_m / 1e3), ("Eccentricity [-]", el.e), ("Perigee speed [m/s]", el.v_perigee_ms), ("Apogee speed [m/s]", el.v_apogee_ms),
            ("Period [s]", el.period_s), ("Specific orbital energy [J/kg]", el.specific_energy_J_kg), ("Launch-site rotation speed used [m/s]", b.info["v_site_mps"]),
            ("Velocity needed relative to site [m/s]", b.info["v_needed_mps"]), ("Frame / gravity model", "Earth-centred inertial speeds; spherical Earth; point-mass gravity; no J2 in ascent")]
    r += 4
    ws.cell(row=r - 1, column=1, value="Orbit parameters").font = Font(name=FONT, bold=True)
    for i, (k, v) in enumerate(info):
        ws.cell(row=r + i, column=1, value=k).font = Font(name=FONT, size=10)
        c = ws.cell(row=r + i, column=3, value=v)
        c.font = Font(name=FONT, size=10)
        if isinstance(v, float):
            c.number_format = "#,##0.000"
    for n in b.notes:
        r += len(info) + 1
        ws.cell(row=r, column=1, value="Note: " + n)
    _widths(ws, [62, 12, 16, 18, 80])
    ws.freeze_panes = "A5"

    # ---------------- Stage_Sizing
    ws = wb.create_sheet("Stage_Sizing")
    _title(ws, "Stage sizing", "Grey cells are live Excel formulas recomputing Python values (rocket equation, mass ratio, burn time). Masses in kg.")
    rows = []
    b_total = res.boosters.m_total_kg if res.boosters else 0.0
    b_stage = res.boosters.attach_stage if res.boosters else 0
    for s in res.stages:
        rows.append(dict(i=s.index, name=s.name, type=s.stage_type, dv=s.dv_mps, isp=s.isp_eff_s, m_carried=s.m_carried_kg, m_dry=s.m_dry_kg, m_res=s.m_residual_kg, m_mar=s.m_margin_prop_kg,
                         m_p=s.m_prop_mission_kg, m_st=s.m_startup_kg, m_load=s.m_prop_loaded_kg, m_ign=s.m_ignition_kg, m_bs=s.m_burn_start_kg, m_bo=s.m_burnout_kg,
                         s_fac=s.structural_factor_s, mu_py=s.mass_ratio, dv_py=s.dv_check_mps, F=s.thrust_ref_N, cond=s.thrust_ref_condition, Fvac=s.thrust_vac_N,
                         mdot=s.mdot_kgs, tb_py=s.burn_time_s, tw0=s.tw_ignition, twb=s.tw_burnout,
                         par=1 if s.index == b_stage else 0, m_drop=b_total if s.index == b_stage else 0.0))
    cols = [("Stage", "i", "0", None), ("Name", "name", None, None), ("Type", "type", None, None),
            ("Parallel burn with strap-ons (1/0)", "par", "0", None),
            ("Strap-on mass dropped during this stage [kg]", "m_drop", "#,##0.0", None),
            ("Allocated dv [m/s]", "dv", "#,##0.0", None), ("Isp effective [s]", "isp", "0.0", None),
            ("Carried mass above stage (incl. payload) [kg]", "m_carried", "#,##0.0", None), ("Dry mass [kg]", "m_dry", "#,##0.0", None),
            ("Residual propellant [kg]", "m_res", "#,##0.0", None), ("Loading margin (unburned) [kg]", "m_mar", "#,##0.0", None),
            ("Mission propellant consumed [kg]", "m_p", "#,##0.0", None), ("Start-up propellant [kg]", "m_st", "#,##0.0", None),
            ("Loaded propellant [kg]", "m_load", "#,##0.0", None), ("Ignition mass [kg]", "m_ign", "#,##0.0", None),
            ("Mass at start of dv burn [kg]", "m_bs", "#,##0.0", None), ("Burnout mass before separation [kg]", "m_bo", "#,##0.0", None),
            ("Structural factor s (Book Eq.5:5a)", "s_fac", "0.0000", None), ("Mass ratio (Python)", "mu_py", "0.0000", None),
            ("Mass ratio (Excel = start / burnout)", None, "0.0000", "={m_bs}/{m_bo}"),
            ("dv recomputed in Excel [m/s] (single-Isp rocket equation)", None, "#,##0.00",
             '=IF({par}=1,"see Parallel_Burn",{isp}*9.80665*LN({m_bs}/{m_bo}))'),
            ("dv - allocated [m/s] (should be 0)", None, "0.0000",
             '=IF({par}=1,"n/a: parallel burn",({isp}*9.80665*LN({m_bs}/{m_bo}))-{dv})'),
            ("Mass closure: ignition - startup - mission prop - strap-ons dropped - burnout [kg] (0)", None, "0.000000",
             "={m_ign}-{m_st}-{m_p}-{m_drop}-{m_bo}"),
            ("Reference thrust [N]", "F", "#,##0", None), ("Thrust condition", "cond", None, None), ("Vacuum thrust [N]", "Fvac", "#,##0", None),
            ("Mass flow [kg/s]", "mdot", "#,##0.00", None), ("Burn time Python [s]", "tb_py", "0.0", None), ("Burn time Excel = m_p/mdot [s]", None, "0.0", "={m_p}/{mdot}"),
            ("T/W at ignition (ref. thrust)", "tw0", "0.000", None), ("T/W at burnout (vac. thrust)", "twb", "0.000", None)]
    f, l, L = write_table(ws, 4, cols, rows)
    ws.row_dimensions[4].height = 60
    _widths(ws, [7, 12, 9, 10] + [16] * (len(cols) - 4))
    ws.freeze_panes = "C5"
    ws.auto_filter.ref = f"A4:{get_column_letter(len(cols))}{l}"
    r = l + 2
    dvc = L["dv"]
    ws.cell(row=r, column=1, value="Sum of allocated stage dv [m/s] (Excel)").font = Font(name=FONT, bold=True)
    ws.cell(row=r, column=5, value=f"=SUM({dvc}{f}:{dvc}{l})").number_format = "#,##0.0"
    ws.cell(row=r + 1, column=1, value="Mission requirement [m/s]")
    ws.cell(row=r + 1, column=5, value=res.dv_required_mps).number_format = "#,##0.0"
    ws.cell(row=r + 2, column=1, value="Margin (sum - requirement)")
    ws.cell(row=r + 2, column=5, value=f"=E{r}-E{r+1}").number_format = "0.000"
    for key in ("dv - allocated [m/s] (should be 0)", "Mass closure: ignition - startup - mission prop - strap-ons dropped - burnout [kg] (0)"):
        cl = get_column_letter([i for i, c in enumerate(cols, 1) if c[0] == key][0])
        ws.conditional_formatting.add(f"{cl}{f}:{cl}{l}", FormulaRule(
            formula=[f"AND(ISNUMBER({cl}{f}),ABS({cl}{f})>0.001)"], fill=PatternFill("solid", bgColor="F8CBAD")))

    # ---------------- Mass_Breakdown
    ws = wb.create_sheet("Mass_Breakdown")
    _title(ws, "Mass breakdown", "One source of truth per component. Margin is a single explicit line per stage.")
    rows = [dict(item="Payload", m=res.payload_mass_kg), dict(item="Payload adapter (PAF)", m=res.paf_mass_kg), dict(item="Fairing", m=res.fairing_mass_kg)]
    for s in res.stages:
        rows.append(dict(item=f"Stage {s.index} dry mass", m=s.m_dry_kg))
        rows.append(dict(item=f"Stage {s.index} loaded propellant", m=s.m_prop_loaded_kg))
    if res.boosters is not None:
        b = res.boosters
        rows.append(dict(item=f"Strap-on boosters: inert ({b.n_total} x {b.m_inert_each_kg:,.0f} kg)", m=b.n_total * b.m_inert_each_kg))
        rows.append(dict(item=f"Strap-on boosters: propellant ({b.n_total} x {b.m_prop_each_kg:,.0f} kg)", m=b.n_total * b.m_prop_each_kg))
    cols = [("Vehicle-level item", "item", None, None), ("Mass [kg]", "m", "#,##0.0", None)]
    f, l, _ = write_table(ws, 4, cols, rows)
    ws.cell(row=l + 1, column=1, value="Gross liftoff mass (Excel SUM)").font = Font(name=FONT, bold=True)
    ws.cell(row=l + 1, column=2, value=f"=SUM(B{f}:B{l})").number_format = "#,##0.0"
    ws.cell(row=l + 2, column=1, value="Gross liftoff mass (Python)")
    ws.cell(row=l + 2, column=2, value=res.glom_kg).number_format = "#,##0.0"
    ws.cell(row=l + 3, column=1, value="Closure error [kg] (should be ~0)")
    ws.cell(row=l + 3, column=2, value=f"=B{l+1}-B{l+2}").number_format = "0.000000"
    ws.conditional_formatting.add(f"B{l+3}", CellIsRule(operator="notBetween", formula=["-0.001", "0.001"], fill=PatternFill("solid", bgColor="F8CBAD")))
    glom_cell = f"$B${l+1}"
    for i in range(f, l + 1):
        ws.cell(row=i, column=3, value=f"=B{i}/{glom_cell}").number_format = "0.00%"
        ws.cell(row=i, column=3).fill = F_CALC
    ws.cell(row=4, column=3, value="Fraction of GLOM")
    _hdr(ws, 4, ["Vehicle-level item", "Mass [kg]", "Fraction of GLOM"])
    r0 = l + 6
    ws.cell(row=r0 - 1, column=1, value="Subsystem ledger (hierarchical: stage > group > component)").font = Font(name=FONT, bold=True)
    from .mass_properties import _present
    Nn, Jj = len(res.stages), spec.fairing.jettison_stage
    bst = res.boosters.attach_stage if res.boosters else 0
    rows = [dict(stage=i.stage, group=i.group, item=i.name, m=i.mass_kg, z=i.z_m, src=i.source, kind=i.kind, shape=i.shape, J0r=i.J0_roll, J0p=i.J0_pitch,
                 er=i.ext_roll, ep=i.ext_pitch, lift=1 if _present(i, 1, "ignition", Jj, Nn, bst) else 0) for i in res.ledger]
    cols = [("Stage (0 payload, -1 fairing, -2 boosters)", "stage", "0", None), ("Group", "group", None, None), ("Component", "item", None, None), ("Mass [kg]", "m", "#,##0.00", None),
            ("Axial CM location z [m]", "z", "0.000", None), ("Kind", "kind", None, None), ("Source of estimate / location", "src", None, None),
            ("Inertia shape model", "shape", None, None), ("J0 roll about own CM [kg m2]", "J0r", "#,##0.0", None), ("J0 pitch about own CM [kg m2]", "J0p", "#,##0.0", None),
            ("Off-axis ring add-on, roll [kg m2]", "er", "#,##0.0", None), ("Off-axis ring add-on, pitch [kg m2]", "ep", "#,##0.0", None), ("Present at liftoff (1/0)", "lift", "0", None)]
    f2, l2, _ = write_table(ws, r0, cols, rows)
    ws.auto_filter.ref = f"A{r0}:M{l2}"
    # live Excel cross-check of the liftoff centre of mass and pitch/roll inertia (parallel-axis theorem, Book Eq. 8:37)
    ws.cell(row=l2 + 1, column=3, value="Liftoff mass (Excel) [kg]").font = Font(name=FONT, bold=True)
    ws.cell(row=l2 + 1, column=4, value=f"=SUMPRODUCT(M{f2}:M{l2},D{f2}:D{l2})").number_format = "#,##0.0"
    ws.cell(row=l2 + 2, column=3, value="Liftoff CM z (Excel) [m]").font = Font(name=FONT, bold=True)
    ws.cell(row=l2 + 2, column=4, value=f"=SUMPRODUCT(M{f2}:M{l2},D{f2}:D{l2},E{f2}:E{l2})/D{l2+1}").number_format = "0.000"
    ws.cell(row=l2 + 3, column=3, value="Liftoff J_pitch about CM (Excel) [kg m2]").font = Font(name=FONT, bold=True)
    ws.cell(row=l2 + 3, column=4, value=f"=SUMPRODUCT(M{f2}:M{l2},J{f2}:J{l2}+L{f2}:L{l2}+D{f2}:D{l2}*(E{f2}:E{l2}-D{l2+2})^2)").number_format = "#,##0"
    ws.cell(row=l2 + 4, column=3, value="Liftoff J_pitch (Python) [kg m2]").font = Font(name=FONT)
    ws.cell(row=l2 + 4, column=4, value=res.mass_properties["events"][0]["J_pitch"]).number_format = "#,##0"
    ws.cell(row=l2 + 5, column=3, value="Difference (should be ~0)").font = Font(name=FONT)
    ws.cell(row=l2 + 5, column=4, value=f"=D{l2+3}-D{l2+4}").number_format = "0.000"
    ws.cell(row=l2 + 6, column=3, value="Liftoff J_roll (Excel) [kg m2]").font = Font(name=FONT, bold=True)
    ws.cell(row=l2 + 6, column=4, value=f"=SUMPRODUCT(M{f2}:M{l2},I{f2}:I{l2}+K{f2}:K{l2})").number_format = "#,##0"
    for k in range(1, 7):
        ws.cell(row=l2 + k, column=4).fill = F_CALC
    l2 = l2 + 6
    r3 = l2 + 2
    ws.cell(row=r3 - 1, column=1, value="Stage dry-mass components (bottom-up) [kg]").font = Font(name=FONT, bold=True)
    names = sorted({k for s in res.stages for k in s.components})
    if names:
        rows = [dict(c=n, **{f"s{s.index}": s.components.get(n, 0.0) for s in res.stages}) for n in names]
        cols = [("Component", "c", None, None)] + [(f"Stage {s.index} [kg]", f"s{s.index}", "#,##0.0", None) for s in res.stages]
        f3, l3, _ = write_table(ws, r3, cols, rows)
        ws.cell(row=l3 + 1, column=1, value="Stage dry mass (Excel SUM)").font = Font(name=FONT, bold=True)
        for j in range(len(res.stages)):
            col = get_column_letter(2 + j)
            ws.cell(row=l3 + 1, column=2 + j, value=f"=SUM({col}{f3}:{col}{l3})").number_format = "#,##0.0"
            ws.cell(row=l3 + 2, column=2 + j, value=res.stages[j].m_dry_kg).number_format = "#,##0.0"
        ws.cell(row=l3 + 2, column=1, value="Stage dry mass (Python)")
    _widths(ws, [44, 18, 40, 16, 22, 14, 60, 34, 16, 16, 16, 16, 12])
    ws.freeze_panes = "A5"

    # ---------------- Tank_Sizing
    ws = wb.create_sheet("Tank_Sizing")
    _title(ws, "Tank sizing", "Internal dimensions = inside the pressure shell; external = + wall. Grey = Excel recomputation (liquid volume, required volume, geometric volume check).")
    rows = []
    for s in res.stages:
        st = spec.stages[s.index - 1]
        for t in s.tanks:
            if st.is_solid:
                ps_rho = spec.solid_propellants[t.propellant].density_kg_m3
                ull = shrink = 0.0
                vf = t.volume_factor
                extra = dict(bore=t.R_bore, web=t.web_m, Vp=t.V_prop)
            else:
                ps = spec.propellants[t.propellant]
                ps_rho = ps.density_kg_m3
                ull = st.tank.ullage_fraction[t.role]
                shrink = 0.0 if ps.boiling_K is None else 3 * st.tank.material.alpha_per_K * abs(st.tank.load_temperature_K - ps.boiling_K)
                vf = 1.0
                extra = dict(bore=None, web=None, Vp=t.V_liquid)
            rows.append(dict(stage=s.index, role=t.role, prop=t.propellant, m=t.m_liquid_loaded, rho=ps_rho, ull=ull, shr=shrink, vf=vf,
                             V_py=t.V_int, R=t.R_int, AR=t.AR, hc=t.h_cyl, hd=t.h_dome, tw=t.t_wall, Lint=t.L_int, Lext=t.L_ext, Dext=t.D_ext, A=t.area_ext,
                             mt=t.mass_tank_kg, mi=t.mass_insulation_kg, meth=t.mass_method, arr=t.bulkhead, **extra))
    br = res.boosters
    if br is not None:
        t = br.case
        rho = (spec.solid_propellants[t.propellant].density_kg_m3 if br.kind == "solid"
               else br.m_loaded_each_kg / t.V_prop if t.V_prop else 0.0)
        rows.append(dict(stage=0, role="booster", prop=t.propellant, m=t.m_liquid_loaded, rho=rho, ull=0.0, shr=0.0, vf=t.volume_factor,
                         V_py=t.V_int, R=t.R_int, AR=t.AR, hc=t.h_cyl, hd=t.h_dome, tw=t.t_wall, Lint=t.L_int, Lext=t.L_ext, Dext=t.D_ext,
                         A=t.area_ext, mt=t.mass_tank_kg, mi=0.0, meth=spec.boosters.inert_mass_method, arr=t.bulkhead,
                         bore=t.R_bore, web=t.web_m, Vp=t.V_prop))
    cols = [("Stage (0 = strap-on)", "stage", "0", None), ("Tank / casing", "role", None, None), ("Propellant", "prop", None, None), ("Loaded propellant mass [kg]", "m", "#,##0.0", None),
            ("Density [kg/m3]", "rho", "#,##0.0", None), ("Ullage fraction", "ull", "0.0000", None), ("Shrink fraction (3 alpha dT)", "shr", "0.0000", None),
            ("Volume factor (solids: Eq. 8:24 = 1.12)", "vf", "0.000", None),
            ("Propellant volume Excel = m/rho [m3]", None, "#,##0.000", "={m}/{rho}"), ("Ullage volume [m3]", None, "#,##0.000", "=({m}/{rho})*{ull}"),
            ("Required internal volume Excel [m3]", None, "#,##0.000", "=({m}/{rho})*(1+{ull}+{shr})*{vf}"), ("Required internal volume Python [m3]", "V_py", "#,##0.000", None),
            ("Internal radius [m]", "R", "0.0000", None), ("Dome aspect ratio R/h", "AR", "0.0000", None), ("Barrel length [m]", "hc", "0.0000", None),
            ("Dome height (internal) [m]", "hd", "0.0000", None), ("Wall thickness used [m]", "tw", "0.0000", None),
            ("Geometric volume Excel: pi R2 h + 2 (2 pi R3/(3 AR)) [m3] (bulkhead upper tank: barrel only)", None, "#,##0.000", "=IF({arr}=\"upper_user\",PI()*{R}^2*{hc},PI()*{R}^2*{hc}+2*(2*PI()*{R}^3/(3*{AR})))"),
            ("Volume check (geometric - required) [m3]", None, "0.000000", "=({R}*0+IF({arr}=\"upper_user\",PI()*{R}^2*{hc},PI()*{R}^2*{hc}+2*(2*PI()*{R}^3/(3*{AR}))))-{V_py}"),
            ("Internal length [m]", "Lint", "0.000", None), ("External length [m]", "Lext", "0.000", None), ("External diameter [m]", "Dext", "0.0000", None),
            ("Outer area [m2]", "A", "#,##0.00", None), ("Tank / casing structure mass [kg]", "mt", "#,##0.0", None), ("Insulation mass [kg]", "mi", "#,##0.0", None),
            ("Mass method", "meth", None, None), ("Bulkhead role", "arr", None, None),
            ("Propellant volume [m3] (grain for solids)", "Vp", "#,##0.000", None), ("Grain bore radius [m] (solids)", "bore", "0.0000", None),
            ("Web thickness [m] (solids)", "web", "0.0000", None)]
    f, l, _ = write_table(ws, 4, cols, rows)
    ws.row_dimensions[4].height = 75
    _widths(ws, [7, 11, 11] + [15] * 27)
    ws.freeze_panes = "D5"
    ws.auto_filter.ref = f"A4:{get_column_letter(len(cols))}{l}"
    chk = get_column_letter([i for i, c in enumerate(cols, 1) if c[0].startswith("Volume check")][0])
    ws.conditional_formatting.add(f"{chk}{f}:{chk}{l}", CellIsRule(operator="notBetween", formula=["-0.0001", "0.0001"], fill=PatternFill("solid", bgColor="F8CBAD")))
    ws.cell(row=l + 2, column=1, value="Tank-mass notes: Table 8.6/8.7 MERs and pressure-vessel estimates are preliminary; the pressure-vessel option is membrane-only (no buckling/axial/bending). "
                                       "Solid motors: casing volume = 1.12 x grain volume (Eq. 8:24); the casing mass MER (Eq. 8:18) already includes insulation, nozzle, thrust structure and TVC.").font = Font(name=FONT, size=9, italic=True)

    # ---------------- Geometry
    ws = wb.create_sheet("Geometry")
    _title(ws, "Vehicle geometry (single source for the 2D drawing)", "z measured upward from the stage-1 nozzle exit plane [m]. Segment length in Excel = z_top - z_bottom.")
    rows = [dict(stage=s.stage, kind=s.kind, name=s.name, z0=s.z0, z1=s.z1, L=s.length, db=s.d_bot, dt=s.d_top)
            for s in list(geom.segments) + list(geom.booster_segments)]
    cols = [("Stage (0 = fairing)", "stage", "0", None), ("Kind", "kind", None, None), ("Component", "name", None, None), ("z bottom [m]", "z0", "0.000", None),
            ("z top [m]", "z1", "0.000", None), ("Length Excel = z_top - z_bottom [m]", None, "0.000", "={z1}-{z0}"), ("Length Python [m]", "L", "0.000", None),
            ("Diameter bottom [m]", "db", "0.000", None), ("Diameter top [m]", "dt", "0.000", None)]
    f, l, _ = write_table(ws, 4, cols, rows)
    r = l + 2
    dims = [("Overall vehicle length [m]", geom.total_length), ("Maximum diameter [m]", geom.max_diameter), ("Length / diameter [-]", geom.total_length / geom.max_diameter),
            ("Fairing length incl. nose [m]", sum(s.length for s in geom.segments if s.kind.startswith("fairing"))), ("Fairing diameter [m]", spec.fairing.diameter_m),
            ("PAF z range [m]", f"{geom.paf_z0:.3f} - {geom.paf_z1:.3f}"), ("Payload envelope z range [m]", f"{geom.payload_z0:.3f} - {geom.payload_z1:.3f}")]
    for s in res.stages:
        dims.append((f"Stage {s.index} length [m] / L/D", f"{s.length_m:.3f} / {s.length_m / spec.stages[s.index-1].diameter_m:.2f}"))
        dims.append((f"Stage {s.index} engine exit plane z [m]", geom.engine_exit_z[s.index]))
        if s.envelope is not None:
            dims.append((f"Stage {s.index} nozzle/engine envelope: n x L x D_exit [m]",
                         f"{s.envelope.n} x {s.envelope.length_m:.3f} x {s.envelope.exit_diameter_m:.3f} ({s.envelope.source})"))
    if res.boosters is not None:
        dims += [("Strap-on span over boosters [m]", geom.max_span_m), ("Strap-on axis offset [m]", geom.booster_x_m),
                 ("Strap-on z range [m]", f"{res.boosters.z0:.3f} - {res.boosters.z1:.3f}")]
    ws.cell(row=r - 1, column=1, value="Key dimensions").font = Font(name=FONT, bold=True)
    for i, (k, v) in enumerate(dims):
        ws.cell(row=r + i, column=1, value=k).font = Font(name=FONT, size=10)
        c = ws.cell(row=r + i, column=4, value=v)
        if isinstance(v, float):
            c.number_format = "0.000"
    _widths(ws, [30, 14, 38, 16, 14, 24, 16, 16, 16])
    ws.freeze_panes = "A5"
    ws.auto_filter.ref = f"A4:I{l}"
    ws.cell(row=r + len(dims) + 1, column=1, value="Hyperlinks to generated drawings (relative paths):").font = Font(name=FONT, bold=True)
    for i, (k, v) in enumerate(figures.items()):
        c = ws.cell(row=r + len(dims) + 2 + i, column=1, value=k)
        c.hyperlink = os.path.relpath(v, os.path.dirname(path)) if os.path.isabs(v) else v
        c.font = Font(name=FONT, color="0563C1", underline="single")

    # ---------------- Mass_Properties
    ws = wb.create_sheet("Mass_Properties")
    _title(ws, "Mass properties", "z measured upward from stage-1 nozzle exit plane. Lumped-mass locations are stated per item in Mass_Breakdown.")
    rows = [dict(e=e["event"], m=e["mass_kg"], z=e["z_cm_m"], f=e["z_cm_over_L"], n=e["n_items"], jr=e["J_roll"], jp=e["J_pitch"], jb=e["J_pitch_book_form"], rt=e["roll_to_pitch_ratio"])
            for e in res.mass_properties["events"]]
    cols = [("Flight event", "e", None, None), ("Vehicle mass [kg]", "m", "#,##0.0", None), ("CM z [m]", "z", "0.000", None), ("CM z / overall length", "f", "0.0000", None), ("Ledger items", "n", "0", None),
            ("J_roll [kg m2]", "jr", "#,##0", None), ("J_pitch = J_yaw about CM [kg m2] (full: liquid self-inertia included)", "jp", "#,##0", None),
            ("J_pitch, book-style (propellant as point masses) [kg m2]", "jb", "#,##0", None), ("J_roll / J_pitch", "rt", "0.0000", None)]
    f, l, _ = write_table(ws, 4, cols, rows)
    r = l + 2
    ws.cell(row=r, column=1, value="Stage hardware + full propellant, taken alone").font = Font(name=FONT, bold=True)
    rows = [dict(s=x["stage"], m=x["mass_kg"], z=x["z_cm_m"], jr=x["J_roll"], jp=x["J_pitch"]) for x in res.mass_properties["stages"]]
    write_table(ws, r + 1, [("Stage", "s", "0", None), ("Mass [kg]", "m", "#,##0.0", None), ("CM z [m]", "z", "0.000", None), ("J_roll [kg m2]", "jr", "#,##0", None), ("J_pitch about own CM [kg m2]", "jp", "#,##0", None)], rows)
    r = r + 4 + len(rows)
    ws.cell(row=r, column=1, value="Data-completeness warnings").font = Font(name=FONT, bold=True)
    for i, w in enumerate(res.mass_properties["warnings"]):
        ws.cell(row=r + 1 + i, column=1, value=w).font = Font(name=FONT, size=10, color="C00000")
    _widths(ws, [70, 18, 14, 18, 14, 16, 30, 30, 14])
    ws.row_dimensions[4].height = 60
    ws.freeze_panes = "A5"

    # ---------------- Sensitivity
    ws = wb.create_sheet("Sensitivity")
    _title(ws, "Sensitivity studies and configuration comparison", "One-at-a-time changes about the base case; all cases share the base mission requirement (delta-v losses varied only where stated).")
    allrows = (sens_rows or []) + (comp_rows or [])
    n = len(res.stages)
    cols = [("Study", "study", None, None), ("Case", "case", None, None), ("Parameter value", "value", "General", None), ("GLOM [kg]", "glom_kg", "#,##0", None),
            ("dGLOM vs base [%]", "delta_glom_pct", "+0.00;-0.00;0.00", None), ("Total loaded propellant [kg]", "prop_total_kg", "#,##0", None),
            ("Total dry mass [kg]", "dry_total_kg", "#,##0", None), ("Payload fraction", "payload_fraction", "0.0000", None), ("Propellant fraction", "prop_fraction", "0.000", None),
            ("Overall length [m]", "length_m", "0.00", None), ("dv requirement [m/s]", "dv_req_mps", "#,##0", None), ("dv margin [m/s]", "dv_margin_mps", "0.000", None)]
    for j in range(1, n + 1):
        cols += [(f"Stage {j} dry [kg]", f"dry_s{j}_kg", "#,##0", None), (f"Stage {j} length [m]", f"len_s{j}_m", "0.00", None)]
    cols += [("Converged", "converged", None, None), ("Feasible", "feasible", None, None), ("Status", "status", None, None)]
    if allrows:
        f, l, _ = write_table(ws, 4, cols, allrows)
        ws.conditional_formatting.add(f"{get_column_letter(len(cols)-2)}{f}:{get_column_letter(len(cols)-1)}{l}", CellIsRule(operator="equal", formula=["FALSE"], fill=PatternFill("solid", bgColor="F8CBAD")))
        ws.auto_filter.ref = f"A4:{get_column_letter(len(cols))}{l}"
    ws.row_dimensions[4].height = 45
    _widths(ws, [44, 44, 14] + [14] * (len(cols) - 3))
    ws.freeze_panes = "C5"
    if opt:
        r = (l if allrows else 4) + 3
        ws.cell(row=r, column=1, value="Optimisation (separate mode): GLOM-minimising stage dv allocation").font = Font(name=FONT, bold=True)
        for i, (k, v) in enumerate([("Optimal dv fractions", ", ".join(f"{x:.4f}" for x in opt["fractions"])), ("GLOM at optimum [kg]", opt["glom_kg"]),
                                    ("GLOM at baseline allocation [kg]", opt["baseline_glom_kg"]), ("Function evaluations", opt["evaluations"]), ("Note", opt["note"])]):
            ws.cell(row=r + 1 + i, column=1, value=k)
            ws.cell(row=r + 1 + i, column=2, value=v)

    # ---------------- Results_Dashboard
    ws = wb.create_sheet("Results_Dashboard", 1)
    _title(ws, f"Results dashboard - {spec.name}", "Software demonstration of a self-consistent preliminary sizing; NOT proof that the mission is achievable.")
    kp = [("Convergence status", res.status), ("Iterations", res.iterations), ("Final residual (relative)", res.residual), ("Gross liftoff mass [kg]", res.glom_kg),
          ("Payload mass [kg]", res.payload_mass_kg), ("Payload adapter [kg]", res.paf_mass_kg), ("Fairing [kg]", res.fairing_mass_kg),
          ("Total loaded propellant [kg]", sum(s.m_prop_loaded_kg for s in res.stages)), ("Total stage dry mass [kg]", sum(s.m_dry_kg for s in res.stages)),
          ("Payload fraction of GLOM", res.payload_mass_kg / res.glom_kg), ("Mission delta-v requirement [m/s]", res.dv_required_mps),
          ("Sum of stage delta-v [m/s]", res.dv_achieved_mps), ("Overall length [m]", geom.total_length), ("Maximum diameter [m]", geom.max_diameter),
          ("Liftoff thrust incl. strap-ons [N]", res.liftoff_thrust_N), ("Liftoff T/W", res.liftoff_tw),
          ("Liftoff CM z [m]", res.mass_properties["events"][0]["z_cm_m"])]
    if res.boosters is not None:
        b = res.boosters
        kp += [(f"Strap-on boosters ({b.kind})", f"{b.n_total} x {b.name} ({b.n_ground_lit} ground-lit)"),
               ("Strap-on total mass [kg]", b.m_total_kg), ("Strap-on burn time [s]", b.burn_time_s)]
    if any(s.is_solid for s in res.stages):
        kp += [("Solid stages", ", ".join(str(s.index) for s in res.stages if s.is_solid)),
               ("Implied burn rates [mm/s]", ", ".join(f"{s.motor_info['implied_burn_rate_mm_s']:.1f}" for s in res.stages if s.is_solid))]
    _hdr(ws, 4, ["Key result", "Value"])
    for i, (k, v) in enumerate(kp):
        ws.cell(row=5 + i, column=1, value=k).font = Font(name=FONT, size=10)
        c = ws.cell(row=5 + i, column=2, value=v)
        c.font = Font(name=FONT, size=10, bold=(k == "Convergence status"))
        if isinstance(v, float):
            c.number_format = "#,##0.000" if abs(v) < 100 else "#,##0.0"
        if k == "Convergence status":
            c.fill = PatternFill("solid", fgColor="C6EFCE" if res.converged else "F8CBAD")
    r = 5 + len(kp) + 1
    ws.cell(row=r, column=1, value="Stage mass distribution").font = Font(name=FONT, bold=True)
    rows = [dict(s=f"Stage {s.index}", dry=s.m_dry_kg, prop=s.m_prop_loaded_kg, L=s.length_m, D=spec.stages[s.index - 1].diameter_m) for s in res.stages]
    f, l, _ = write_table(ws, r + 1, [("Stage", "s", None, None), ("Dry [kg]", "dry", "#,##0", None), ("Propellant [kg]", "prop", "#,##0", None),
                                      ("Length [m]", "L", "0.00", None), ("Diameter [m]", "D", "0.00", None)], rows)
    ch = BarChart()
    ch.type, ch.grouping, ch.overlap = "col", "stacked", 100
    ch.title, ch.y_axis.title = "Stage mass distribution [kg]", "kg"
    ch.add_data(Reference(ws, min_col=2, max_col=3, min_row=r + 1, max_row=l), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=1, min_row=f, max_row=l))
    ch.height, ch.width = 7, 12
    ws.add_chart(ch, "D4")
    r = l + 2
    ws.cell(row=r, column=1, value="Convergence history").font = Font(name=FONT, bold=True)
    hrows = [dict(it=h["iteration"], g=h["glom_kg"], res=h["residual"]) for h in res.history]
    f2, l2, _ = write_table(ws, r + 1, [("Iteration", "it", "0", None), ("GLOM [kg]", "g", "#,##0.00", None), ("Relative residual", "res", "0.0E+00", None)], hrows)
    lc = LineChart()
    lc.title, lc.y_axis.title, lc.x_axis.title = "GLOM vs iteration", "kg", "iteration"
    lc.add_data(Reference(ws, min_col=2, min_row=r + 1, max_row=l2), titles_from_data=True)
    lc.set_categories(Reference(ws, min_col=1, min_row=f2, max_row=l2))
    lc.height, lc.width = 7, 12
    ws.add_chart(lc, "D20")
    r = l2 + 2
    ws.cell(row=r, column=1, value="Validation issues, warnings and key assumptions").font = Font(name=FONT, bold=True)
    for i, it in enumerate(res.issues):
        c = ws.cell(row=r + 1 + i, column=1, value=f"[{it.level}] {it.code}: {it.message}")
        c.font = Font(name=FONT, size=9, color={"ERROR": "C00000", "WARNING": "9C5700", "INFO": "595959"}[it.level])
        c.alignment = Alignment(wrap_text=True, vertical="top")
    r = r + len(res.issues) + 2
    for i, t in enumerate(["Loss terms (gravity/drag/steering) are user estimates, not simulated.", "Effective Isp per stage is an explicit assumption (see Stage_Inputs).",
                           "Mass margins: one per stage (inert_mass_margin_fraction) + one delta-v margin; no double counting.", "Residual & loading-margin propellant stay on board at burnout."]):
        ws.cell(row=r + i, column=1, value="- " + t).font = Font(name=FONT, size=9)
    if "vehicle_png" in figures and os.path.exists(figures["vehicle_png"]):
        img = XLImage(figures["vehicle_png"])
        k = 760 / img.height
        img.height, img.width = 760, int(img.width * k)
        ws.add_image(img, "J4")
    _widths(ws, [74, 22, 18, 14, 14])
    ws.conditional_formatting.add(f"A{r - len(res.issues) - 2}:A{r}", FormulaRule(formula=[f'LEFT(A{r - len(res.issues) - 2},7)="[ERROR]"'], font=Font(color="C00000", bold=True)))

    # ---------------- Parallel_Burn (only when strap-on boosters are present)
    if res.boosters is not None:
        b, bs = res.boosters, spec.boosters
        ws = wb.create_sheet("Parallel_Burn")
        _title(ws, "Strap-on boosters and the parallel ('zeroth-stage') burn",
               "Book Sec. 5.11: total thrust Eq. 5:65, mass-averaged exhaust speed Eq. 5:66, phase structure Fig. 5.21. "
               "Grey cells recompute the phase delta-v in Excel from the masses and the mass-averaged Isp.")
        info = [("Booster name", b.name), ("Type", b.kind), ("Number of boosters", b.n_total), ("Ground-lit at lift-off", b.n_ground_lit),
                ("Air-lit (ignite at ground-lit burnout)", b.n_total - b.n_ground_lit), ("Attached to stage", b.attach_stage),
                ("Propellant", bs.propellant or f"{bs.oxidizer}/{bs.fuel}"), ("Mission propellant per booster [kg]", b.m_prop_each_kg),
                ("Inert mass per booster [kg]", b.m_inert_each_kg), ("Loaded mass per booster [kg]", b.m_loaded_each_kg),
                ("Total strap-on mass [kg]", b.m_total_kg), ("Structural factor s of one booster", b.structural_factor_s),
                ("Burn time [s]", b.burn_time_s), ("Mass flow per booster [kg/s]", b.mdot_each_kgs),
                ("Vacuum thrust per booster [N]", b.thrust_vac_each_N), ("Sea-level thrust per booster [N]", b.thrust_sl_each_N),
                ("Effective Isp per booster [s]", b.isp_eff_s), ("Booster diameter [m]", b.diameter_m), ("Booster length [m]", b.length_m),
                ("Lateral offset of booster axis [m]", b.x_offset_m), ("Vehicle lift-off thrust incl. strap-ons [N]", res.liftoff_thrust_N),
                ("Vehicle lift-off T/W", res.liftoff_tw)]
        _hdr(ws, 4, ["Booster property", "Value"])
        for i, (k, v) in enumerate(info):
            ws.cell(row=5 + i, column=1, value=k).font = Font(name=FONT, size=10)
            c = ws.cell(row=5 + i, column=2, value=v)
            c.font = Font(name=FONT, size=10)
            if isinstance(v, float):
                c.number_format = "#,##0.000" if abs(v) < 100 else "#,##0.0"
        r = 5 + len(info) + 2
        ws.cell(row=r - 1, column=1, value=f"Phase sequence of stage {b.attach_stage} (Fig. 5.21)").font = Font(name=FONT, bold=True)
        prows = [dict(n=p.name, t=p.duration_s, mdot=p.mdot_total_kgs, isp=p.isp_eff_s, F=p.thrust_eff_N, m0=p.m_start_kg,
                      m1=p.m_end_kg, dv=p.dv_mps, note=p.note) for p in res.stages[b.attach_stage - 1].phases]
        pcols = [("Phase", "n", None, None), ("Duration [s]", "t", "0.0", None), ("Total mass flow [kg/s]", "mdot", "#,##0.00", None),
                 ("Mass-averaged Isp [s] (Eq. 5:66)", "isp", "0.00", None), ("Effective thrust [N]", "F", "#,##0", None),
                 ("Mass at start [kg]", "m0", "#,##0.0", None), ("Mass at end [kg]", "m1", "#,##0.0", None),
                 ("delta-v Python [m/s]", "dv", "#,##0.00", None),
                 ("delta-v Excel = g0 Isp ln(m0/m1) [m/s]", None, "#,##0.00", "=IF({t}=0,0,{isp}*9.80665*LN({m0}/{m1}))"),
                 ("Difference (should be 0)", None, "0.000000", "=IF({t}=0,0,{isp}*9.80665*LN({m0}/{m1}))-{dv}"),
                 ("Propellant used in phase [kg]", None, "#,##0.0", "={mdot}*{t}"), ("Note", "note", None, None)]
        pf, pl, _ = write_table(ws, r, pcols, prows)
        ws.cell(row=pl + 1, column=1, value="Sum of phase delta-v [m/s] (Excel)").font = Font(name=FONT, bold=True)
        ws.cell(row=pl + 1, column=8, value=f"=SUM(H{pf}:H{pl})").number_format = "#,##0.00"
        ws.cell(row=pl + 2, column=1, value=f"Delta-v allocated to stage {b.attach_stage} [m/s]")
        ws.cell(row=pl + 2, column=8, value=res.stages[b.attach_stage - 1].dv_mps).number_format = "#,##0.00"
        ws.cell(row=pl + 3, column=1, value="Difference (should be 0)")
        ws.cell(row=pl + 3, column=8, value=f"=H{pl+1}-H{pl+2}").number_format = "0.000000"
        r2 = pl + 5
        ws.cell(row=r2 - 1, column=1, value="Booster mass build-up (per booster) [kg]").font = Font(name=FONT, bold=True)
        write_table(ws, r2, [("Item", "c", None, None), ("Mass [kg]", "m", "#,##0.0", None)],
                    [dict(c=k, m=v) for k, v in b.components.items()] + [dict(c="Residual propellant", m=b.m_inert_each_kg - sum(b.components.values()))])
        ws.row_dimensions[r].height = 45
        _widths(ws, [52, 20, 18, 18, 18, 18, 18, 18, 20, 18, 18, 46])
        for wmsg in b.warnings:
            ws.cell(row=r2 + len(b.components) + 4, column=1, value="Note: " + wmsg).font = Font(name=FONT, size=9, italic=True)

    # ---------------- Loads (only when the load cases were computed)
    if loads:
        ws = wb.create_sheet("Loads")
        _title(ws, "Ground and flight loads (book Chapter 9)",
               "z = upward from the stage-1 nozzle exit plane, the axis the drawings and the loads diagram use; station = the book's own coordinate, distance from the nose. Axial positive in compression. "
               "Values are those just below the station cut, so a load applied at a station is included.")
        r = 4
        for key, case in loads.items():
            if not hasattr(case, "stations"):
                continue
            ws.cell(row=r, column=1, value=case.name).font = Font(name=FONT, bold=True, size=11, color="1F3864")
            st = "; ".join(f"{k} = {v:,.4g}" if isinstance(v, (int, float)) else f"{k} = {v}"
                           for k, v in case.state.items())
            c = ws.cell(row=r + 1, column=1, value=st)
            c.font = Font(name=FONT, size=8, italic=True, color="595959")
            rows = [dict(z=s.z_m, stn=s.station_m, at=s.label, a=s.axial_below_N / 1e3, v=s.shear_below_N / 1e3,
                         m=s.moment_Nm / 1e3) for s in case.stations]
            cols = [("z [m]", "z", "0.000", None), ("Station [m]", "stn", "0.000", None), ("At", "at", None, None),
                    ("Axial [kN]", "a", "#,##0.0", None), ("Shear [kN]", "v", "#,##0.0", None),
                    ("Bending moment [kN m]", "m", "#,##0.0", None)]
            _f, last, _ = write_table(ws, r + 2, cols, rows)
            r = last + 2
            for k, v in case.closure.items():
                ws.cell(row=r, column=1, value=f"closure: {k}").font = Font(name=FONT, size=9, italic=True)
                ws.cell(row=r, column=4, value=v).number_format = "#,##0.000"
                r += 1
            for n in case.notes:
                ws.cell(row=r, column=1, value=n).font = Font(name=FONT, size=8, color="595959")
                r += 1
            r += 2
        _widths(ws, [14, 14, 50, 18, 18, 24])

    # ---------------- Ascent_Optimum (only when the pitch programme was optimised)
    if ascent_opt and ascent_opt.get("ok"):
        ws = wb.create_sheet("Ascent_Optimum")
        _title(ws, "Ascent pitch-programme optimisation (book Sec. 6.7)",
               "Objective: burnout speed. The pitch kick is solved by shooting inside every evaluation, so every "
               "row below reaches the target altitude. The optimum sits on a constraint, not at a stationary point.")
        cols = [("Hand-over altitude [km]", "h", "0.0", None), ("alpha allowed [deg]", "a", "0.00", None),
                ("Vertical rise [s]", "vr", "0.0", None), ("Kick [deg]", "k", "0.0000", None),
                ("Burnout speed [m/s]", "v", "#,##0.0", None), ("Total losses [m/s]", "L", "#,##0", None),
                ("Gravity [m/s]", "lg", "#,##0", None), ("Drag [m/s]", "ld", "#,##0", None),
                ("Steering [m/s]", "ls", "#,##0", None), ("max-q [kPa]", "q", "0.0", None),
                ("max q.alpha [kPa deg]", "qa", "#,##0", None), ("max axial [g]", "g", "0.00", None)]

        def row(c):
            return dict(h=c["handover_h_m"] / 1e3, a=c["max_alpha_deg"], vr=c["vertical_rise_s"],
                        k=c["kick_deg"], v=c["burnout_v_mps"], L=c["total_loss_mps"],
                        lg=c["gravity_loss_mps"], ld=c["drag_loss_mps"], ls=c["steering_loss_mps"],
                        q=c["max_q_Pa"] / 1e3, qa=c["max_q_alpha_Pa_deg"] / 1e3, g=c["max_accel_g"])

        ws.cell(row=4, column=1, value="Baseline and optimum").font = Font(name=FONT, bold=True)
        _f, last, _ = write_table(ws, 5, cols, [row(ascent_opt["baseline"]), row(ascent_opt["best"])])
        r = last + 2
        ws.cell(row=r, column=1, value="Trade sweep: the book's Fig. 6.26, as numbers").font = Font(name=FONT, bold=True)
        _f, last, _ = write_table(ws, r + 1, cols, [row(c) for c in ascent_opt.get("sweep", [])])
        r = last + 2
        lim = ascent_opt.get("limits") or {}
        for k, v in (("max-q limit [Pa]", lim.get("max_q_Pa")), ("q.alpha limit [Pa deg]", lim.get("max_q_alpha_Pa_deg")),
                     ("axial acceleration limit [g]", lim.get("max_axial_g")),
                     ("burnout flight path angle window [deg]", lim.get("max_gamma_burnout_deg")),
                     ("binding constraint", (ascent_opt.get("binding") or {}).get("detail")),
                     ("burnout speed gain [m/s]", ascent_opt.get("speed_gain_mps")),
                     ("payload gain [kg]", ascent_opt.get("payload_gain_kg")),
                     ("trajectories flown in the search", ascent_opt.get("evaluations"))):
            ws.cell(row=r, column=1, value=k).font = Font(name=FONT, size=10)
            ws.cell(row=r, column=4, value=v)
            r += 1
        for n in ascent_opt.get("notes", []):
            ws.cell(row=r, column=1, value=n).font = Font(name=FONT, size=8, color="595959")
            r += 1
        _widths(ws, [26, 18, 16, 14, 18, 16, 14, 12, 14, 14, 20, 14])

    # ---------------- Structure (only when the stress analysis was run)
    if structure and structure.get("shells"):
        ws = wb.create_sheet("Structure")
        mat = structure["material"]
        _title(ws, "Shell stress, buckling and required thickness (book Chapter 10)",
               f"{mat.name}: E = {mat.E_Pa/1e9:,.0f} GPa, sigma_allow = {mat.sigma_allow_Pa/1e6:,.0f} MPa, "
               f"rho = {mat.rho_kg_m3:,.0f} kg/m3, minimum gauge {mat.t_min_m*1e3:.2f} mm, FS = "
               f"{structure['factor_of_safety']:.2f}. Required thickness = max(axial, hoop, buckling, min gauge) "
               f"over every load case. Nothing here is fed back into the vehicle's masses.")
        rows = []
        for sh in structure["shells"]:
            for c in sh.cases:
                rows.append(dict(n=sh.name, k=sh.kind, case=c.case, R=sh.R_m, L=sh.L_m,
                                 P=c.P_N / 1e3, M=c.M_Nm / 1e3, V=c.V_N / 1e3, p=c.p_Pa / 1e3,
                                 ph=c.p_hydro_Pa / 1e3, ta=c.t_axial_m * 1e3, th=c.t_hoop_m * 1e3,
                                 tb=c.t_buckling_m * 1e3, tr=c.t_required_m * 1e3, d=c.driver,
                                 sv=c.sigma_vert_Pa / 1e6, sh_=c.sigma_hoop_Pa / 1e6,
                                 ms=c.margin_strength, mb=c.margin_buckling))
        cols = [("Shell", "n", None, None), ("Kind", "k", None, None), ("Load case", "case", None, None),
                ("R [m]", "R", "0.000", None), ("L [m]", "L", "0.000", None),
                ("Axial P [kN]", "P", "#,##0", None), ("Moment M [kN m]", "M", "#,##0", None),
                ("Shear V [kN]", "V", "#,##0", None), ("Ullage p [kPa]", "p", "#,##0", None),
                ("Hydrostatic [kPa]", "ph", "#,##0", None), ("t axial [mm]", "ta", "0.000", None),
                ("t hoop [mm]", "th", "0.000", None), ("t buckling [mm]", "tb", "0.000", None),
                ("t required [mm]", "tr", "0.000", None), ("Driven by", "d", None, None),
                ("sigma vert [MPa]", "sv", "#,##0.0", None), ("sigma hoop [MPa]", "sh_", "#,##0.0", None),
                ("MoS strength", "ms", "0.00", None), ("MoS buckling", "mb", "0.00", None)]
        _f, last, _ = write_table(ws, 4, cols, rows)
        r = last + 2
        ws.cell(row=r, column=1, value="Per shell: the worst case, and what it weighs").font = Font(name=FONT, bold=True)
        srows = [dict(n=sh.name, tr=sh.t_required_m * 1e3, d=sh.governing_driver, case=sh.governing_case,
                      gauge="yes" if sh.min_gauge_applied else "", a=sh.surface_area_m2,
                      ms=sh.mass_sized_kg, mm=sh.mass_model_kg) for sh in structure["shells"]]
        scols = [("Shell", "n", None, None), ("t required [mm]", "tr", "0.000", None),
                 ("Driven by", "d", None, None), ("Governing case", "case", None, None),
                 ("At minimum gauge", "gauge", None, None), ("Surface area [m2]", "a", "0.00", None),
                 ("Sized mass [kg]", "ms", "#,##0", None), ("Model mass [kg]", "mm", "#,##0", None)]
        _f, last, _ = write_table(ws, r + 1, scols, srows)
        r = last + 2
        for k, v in (("Sized monocoque total [kg]", structure.get("mass_sized_kg")),
                     ("Mass-relationship total for the same shells [kg]", structure.get("mass_model_kg")),
                     ("Ratio", structure.get("mass_ratio"))):
            ws.cell(row=r, column=1, value=k).font = Font(name=FONT, size=10)
            ws.cell(row=r, column=4, value=v)
            r += 1
        for n in structure.get("notes", []):
            ws.cell(row=r, column=1, value=n).font = Font(name=FONT, size=8, color="595959")
            r += 1
        _widths(ws, [30, 12, 26, 10, 10, 14, 16, 13, 14, 16, 13, 13, 15, 15, 14, 16, 16, 13, 13])

    write_register(wb=wb)
    order = ["README", "Mission_Inputs", "Vehicle_Inputs", "Stage_Inputs", "DeltaV_Budget", "Stage_Sizing", "Mass_Breakdown", "Tank_Sizing", "Geometry",
             "Mass_Properties", "Results_Dashboard", "Sensitivity", "Engineering_References"]
    if loads:
        order.insert(order.index("Results_Dashboard"), "Loads")
    if ascent_opt and ascent_opt.get("ok"):
        order.insert(order.index("Results_Dashboard"), "Ascent_Optimum")
    if structure and structure.get("shells"):
        order.insert(order.index("Results_Dashboard"), "Structure")
    if res.boosters is not None:
        order.insert(order.index("Mass_Breakdown"), "Parallel_Burn")
    wb._sheets = [wb[n] for n in order]
    wb.save(path)
    return path


# ---------------------------------------------------------------------------------------------------------
def export_csv(res, outdir):
    os.makedirs(outdir, exist_ok=True)
    paths = {}
    def w(name, header, rows):
        p = os.path.join(outdir, name)
        with open(p, "w", newline="", encoding="utf-8") as f:
            wr = csv.writer(f)
            wr.writerow(header)
            wr.writerows(rows)
        paths[name] = p
    g = res.geometry
    w("geometry_dimensions.csv", ["stage", "kind", "component", "z_bottom_m", "z_top_m", "length_m", "d_bottom_m", "d_top_m"],
      [[s.stage, s.kind, s.name, f"{s.z0:.4f}", f"{s.z1:.4f}", f"{s.length:.4f}", f"{s.d_bot:.4f}", f"{s.d_top:.4f}"] for s in g.segments])
    w("component_positions.csv", ["stage", "group", "component", "mass_kg", "z_cm_m", "kind", "source"],
      [[i.stage, i.group, i.name, f"{i.mass_kg:.4f}", f"{i.z_m:.4f}", i.kind, i.source] for i in res.ledger])
    w("stage_summary.csv", ["stage", "type", "dv_mps", "isp_eff_s", "m_ignition_kg", "m_burnout_kg", "m_dry_kg", "m_prop_loaded_kg", "mass_ratio", "s", "burn_time_s", "tw_ignition", "length_m"],
      [[s.index, s.stage_type, f"{s.dv_mps:.3f}", f"{s.isp_eff_s:.3f}", f"{s.m_ignition_kg:.3f}", f"{s.m_burnout_kg:.3f}", f"{s.m_dry_kg:.3f}", f"{s.m_prop_loaded_kg:.3f}",
        f"{s.mass_ratio:.5f}", f"{s.structural_factor_s:.5f}", f"{s.burn_time_s:.2f}", f"{s.tw_ignition:.4f}", f"{s.length_m:.4f}"] for s in res.stages])
    if res.boosters is not None:
        b = res.boosters
        sr = res.stages[b.attach_stage - 1]
        w("parallel_burn_phases.csv", ["phase", "duration_s", "mdot_total_kgs", "isp_eff_s", "thrust_N", "m_start_kg", "m_end_kg", "dv_mps"],
          [[p.name, f"{p.duration_s:.3f}", f"{p.mdot_total_kgs:.4f}", f"{p.isp_eff_s:.4f}", f"{p.thrust_eff_N:.1f}",
            f"{p.m_start_kg:.3f}", f"{p.m_end_kg:.3f}", f"{p.dv_mps:.4f}"] for p in sr.phases])
    return paths
