"""Command-line interface.

  python -m launch_vehicle.main run --design config/default_design.yaml --out outputs
  python -m launch_vehicle.main optimize --design ...
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from .config_io import load_design
from .convergence import size_vehicle, SizingError
from .validation import InputError
from . import schematic_2d, reporting, sensitivity, optimization, report as report_mod
from . import charts, performance, uncertainty, trajectory as trajectory_mod, aerodynamics
from . import loads as loads_mod, ascent_opt as ascent_opt_mod, structure as structure_mod
from . import control as control_mod, solid_motor, engine_geometry
from . import cost as cost_mod, payload_env as payload_env_mod, studies as studies_mod
from . import cad_export, vehicle_import, wind as wind_mod


def _studies(design, assump, spec, res, outdir, figs, want, n_mc, verbose, applied_opt=None):
    """The optional studies that add their own report sections: R1 performance curves, R3 uncertainty, R4 the
    staging optimum. Each one is independent; a failure in one is reported and never stops the run."""
    # Every study writes a chart into outdir. run() creates it, but the GUI, the tests and the trade driver
    # all call this directly, and a missing directory turned into a per-study "skipped" that looked like the
    # study itself had failed.
    os.makedirs(outdir, exist_ok=True)
    extras = {}
    if "performance" in want:
        if verbose:
            print("  performance curves ...", flush=True)
        try:
            cur = performance.standard_curves(res)
            figs["performance_png"] = os.path.join(outdir, "performance_curves.png")
            charts.draw_performance(cur, figs["performance_png"], None,
                                    title=f"{spec.name} - payload capability")
            extras["performance"] = cur
            if verbose and cur.get("design_point_error_kg") is not None:
                print(f"    design-point self-check: {cur['design_point_kg']:,.0f} kg "
                      f"({cur['design_point_error_kg']:+,.0f} kg vs the design payload)")
        except Exception as ex:                                  # noqa: BLE001 - a study must not kill the run
            print(f"    performance curves skipped: {type(ex).__name__}: {ex}", file=sys.stderr)
    if "staging" in want:
        if verbose:
            print("  staging optimum ...", flush=True)
        try:
            ana = optimization.analytical_optimum_from_result(res)
            # If the split was already optimised and APPLIED before sizing, reuse that result. Re-running
            # the search here would start from the optimum it had just found, report ~0 % improvement and
            # quote the optimised split as its own baseline - losing the before-and-after that is the whole
            # point of the section, and paying for a second search to do it.
            num = applied_opt if applied_opt else optimization.optimize_dv_split(spec)
            st = {"analytical": ana, "numerical": num, "sweep": optimization.staging_sweep(spec),
                  # flat keys so charts.draw_staging_optimum can mark both optima on the sweep
                  "fractions": num["fractions"], "analytical_fractions": ana["fractions"],
                  "analytical_glom_kg": optimization.glom_for_fractions(spec, ana["fractions"])}
            extras["staging"] = st
            if st["sweep"]:
                figs["staging_png"] = os.path.join(outdir, "staging_optimum.png")
                charts.draw_staging_optimum(st, figs["staging_png"], None,
                                            title=f"{spec.name} - staging optimum")
        except Exception as ex:                                  # noqa: BLE001
            print(f"    staging optimum skipped: {type(ex).__name__}: {ex}", file=sys.stderr)
    if "trajectory" in want:
        if verbose:
            print("  ascent trajectory ...", flush=True)
        try:
            drag = aerodynamics.model_from_config(spec.mission.get("aerodynamics"), root=os.path.dirname(design))
            tr = trajectory_mod.fly_design(res, drag=drag,
                                           atmosphere=(spec.mission.get("atmosphere_model")
                                                       or "book_exponential"),
                                           vertical_rise_s=float(spec.mission.get("vertical_rise_s") or 10.0),
                                           last_ascent_stage=spec.mission.get("last_ascent_stage"))
            extras["trajectory"] = tr
            if tr.attempted:
                figs["trajectory_png"] = os.path.join(outdir, "trajectory.png")
                charts.draw_trajectory(tr, figs["trajectory_png"], None,
                                       title=f"{spec.name} - ascent trajectory",
                                       required_v_mps=res.budget.info.get("v_needed_mps"))
            elif verbose:
                # No chart at all, rather than four empty axes that read as a vehicle which never moved
                print(f"    ascent not attempted: {tr.status.split('.')[0]}", flush=True)
            if tr.converged:
                try:
                    cp = aerodynamics.cp_over_trajectory(
                        res, tr, (spec.mission.get("aerodynamics") or {}).get("cna_overrides"), every=2)
                    if cp.get("rows"):
                        extras["stability"] = cp
                        figs["stability_png"] = os.path.join(outdir, "stability.png")
                        charts.draw_stability(cp, figs["stability_png"], None,
                                              title=f"{spec.name} - static stability")
                        ctl = control_mod.assess(res, tr, cp["rows"])
                        extras["control"] = ctl
                        charts.draw_stability(cp, figs["stability_png"], None,
                                              title=f"{spec.name} - static stability", control=ctl)
                        if verbose:
                            w = min(cp["rows"], key=lambda r: r["static_margin_cal"])
                            print(f"    centre of pressure at station {cp['rows'][0]['station_cp_m']:.1f} m; "
                                  f"static margin {w['static_margin_cal']:+.2f} calibers at worst")
                            bad = [c for c in ctl.checks if not c["passed"]]
                            print("    control checks: " + (f"{len(ctl.checks)-len(bad)}/{len(ctl.checks)} pass"
                                  + ("" if not bad else "; FAILED: " + ", ".join(c["rule"] for c in bad))))
                except Exception as ex:                          # noqa: BLE001
                    print(f"    centre-of-pressure build-up skipped: {type(ex).__name__}: {ex}",
                          file=sys.stderr)
            if verbose:
                if tr.converged:
                    print(f"    burnout {tr.burnout_v_mps:,.0f} m/s at {tr.burnout_h_m/1e3:.0f} km "
                          f"(needed {res.budget.info.get('v_needed_mps', 0):,.0f} m/s); losses "
                          f"gravity {tr.gravity_loss_mps:,.0f}, drag {tr.drag_loss_mps:,.0f}, "
                          f"propulsion {tr.propulsion_loss_mps:,.0f}, steering {tr.steering_loss_mps:,.0f} m/s")
                else:
                    print(f"    the ascent did not close: {tr.status}")
        except Exception as ex:                                  # noqa: BLE001
            print(f"    trajectory skipped: {type(ex).__name__}: {ex}", file=sys.stderr)
    if "optimise_ascent" in want:
        if verbose:
            print("  ascent pitch-programme optimisation ...", flush=True)
        try:
            drag = aerodynamics.model_from_config(spec.mission.get("aerodynamics"), root=os.path.dirname(design))
            opt = ascent_opt_mod.optimise_and_price(
                res, drag=drag, atmosphere=(spec.mission.get("atmosphere_model") or "book_exponential"),
                limits=ascent_opt_mod.limits_from_spec(spec),
                vertical_rise_s=float(spec.mission.get("vertical_rise_s") or 10.0),
                last_ascent_stage=spec.mission.get("last_ascent_stage"))
            extras["ascent_optimum"] = opt
            if opt.get("sweep"):
                figs["ascent_opt_png"] = os.path.join(outdir, "ascent_optimum.png")
                charts.draw_ascent_optimum(opt, figs["ascent_opt_png"], None,
                                           title=f"{spec.name} - ascent pitch-programme trade")
            if verbose:
                if opt.get("ok"):
                    print(f"    {opt['speed_gain_mps']:+,.0f} m/s of burnout speed"
                          + (f", {opt['payload_gain_kg']:+,.0f} kg of payload"
                             if opt.get("payload_gain_kg") is not None else "")
                          + f"; stopped by: {opt.get('binding', {}).get('name', '?')}")
                else:
                    print("    no pitch programme in the search box met the limits")
        except Exception as ex:                                  # noqa: BLE001
            print(f"    ascent optimisation skipped: {type(ex).__name__}: {ex}", file=sys.stderr)
    if "loads" in want:
        if verbose:
            print("  ground and flight loads ...", flush=True)
        try:
            # the site's own winds aloft when the design names a file, the book's AMR envelope otherwise;
            # several profiles are an ensemble and the governing load is kept (see wind.py)
            profiles = wind_mod.load(spec.mission.get("wind"), root=os.path.dirname(design) or ".")
            cases = loads_mod.standard_cases(
                res, extras.get("trajectory"),
                pad_height_m=float(spec.mission.get("pad_height_m") or 0.0),
                cna_overrides=(spec.mission.get("aerodynamics") or {}).get("cna_overrides"),
                wind_profiles=profiles)
            extras["loads"] = cases
            extras["wind_profiles"] = profiles
            if verbose:
                print(f"    winds aloft: {wind_mod.summarise(profiles)}", flush=True)
            figs["wind_png"] = os.path.join(outdir, "wind_profiles.png")
            charts.draw_wind_profiles(profiles, figs["wind_png"], None,
                                      title=f"{spec.name} - winds aloft used for the flight load cases")
            figs["loads_png"] = os.path.join(outdir, "loads.png")
            charts.draw_loads(cases, figs["loads_png"], None, title=f"{spec.name} - ground and flight loads", res=res)
            if verbose:
                for key, c in cases.items():
                    if hasattr(c, "stations"):
                        print(f"    {c.name}: axial {c.max_axial_N/1e3:,.0f} kN, shear "
                              f"{c.max_shear_N/1e3:,.0f} kN, bending {c.max_moment_Nm/1e3:,.0f} kN m")
        except Exception as ex:                                  # noqa: BLE001
            print(f"    loads skipped: {type(ex).__name__}: {ex}", file=sys.stderr)
    if "ballistics" in want:
        if verbose:
            print("  solid motor internal ballistics ...", flush=True)
        try:
            profs = []
            for s in res.stages:
                stx = spec.stages[s.index - 1]
                if not stx.is_solid or stx.motor is None:
                    continue
                segs = [x for x in res.geometry.stage_segments(s.index) if x.kind == "tank"]
                if not segs or segs[0].tank is None:
                    continue
                case = segs[0].tank
                ps = spec.solid_propellants.get(case.propellant)
                if ps is None or not ps.c_star_mps or not ps.burn_rate_exponent:
                    continue
                At = engine_geometry.throat_area(s.thrust_vac_N / max(stx.motor.n_motors, 1), ps.c_star_mps,
                                                 stx.motor.chamber_pressure_Pa, stx.motor.isp_vac_s)
                pr = solid_motor.burn_profile(case, ps.density_kg_m3, ps.c_star_mps, ps.burn_rate_exponent,
                                              At, stx.motor.chamber_pressure_Pa, stx.motor.isp_vac_s)
                pr["stage"] = s.index
                pr["design_thrust_N"] = s.thrust_vac_N
                pr["design_burn_time_s"] = s.burn_time_s
                pr["propellant"] = case.propellant
                profs.append(pr)
            if profs:
                extras["ballistics"] = profs
                figs["ballistics_png"] = os.path.join(outdir, "internal_ballistics.png")
                charts.draw_internal_ballistics(profs, figs["ballistics_png"], None,
                                                title=f"{spec.name} - solid motor internal ballistics")
                if verbose:
                    for pr in profs:
                        if pr.get("ok"):
                            print(f"    stage {pr['stage']}: thrust {pr['thrust_initial_N']/1e3:,.0f} -> "
                                  f"{pr['thrust_final_N']/1e3:,.0f} kN over {pr['burn_time_s']:.0f} s, "
                                  f"peak Pc {pr['pc_max_Pa']/1e6:.1f} MPa against a design "
                                  f"{pr['pc_design_Pa']/1e6:.1f} MPa")
            elif verbose:
                print("    no solid stage with ballistic data on this vehicle")
        except Exception as ex:                                  # noqa: BLE001
            print(f"    internal ballistics skipped: {type(ex).__name__}: {ex}", file=sys.stderr)
    if "structure" in want and extras.get("loads"):
        if verbose:
            print("  shell stress and buckling ...", flush=True)
        try:
            sout = structure_mod.analyse(res, extras["loads"])
            extras["structure"] = sout
            figs["structure_png"] = os.path.join(outdir, "structure.png")
            charts.draw_structure(sout, res.geometry, figs["structure_png"], None,
                                  title=f"{spec.name} - shell sizing")
            if verbose:
                drv = {}
                for sh in sout["shells"]:
                    drv[sh.governing_driver] = drv.get(sh.governing_driver, 0) + 1
                print("    " + ", ".join(f"{v} sized by {k}" for k, v in sorted(drv.items())))
                if sout.get("mass_ratio"):
                    print(f"    monocoque shells {sout['mass_sized_kg']:,.0f} kg vs "
                          f"{sout['mass_model_kg']:,.0f} kg from the mass relationships "
                          f"(x{sout['mass_ratio']:.2f})")
        except Exception as ex:                                  # noqa: BLE001
            print(f"    structural analysis skipped: {type(ex).__name__}: {ex}", file=sys.stderr)
    if "payload_env" in want:
        try:
            env = payload_env_mod.build(res, extras.get("trajectory"), extras.get("loads"))
            if env.rows:
                extras["payload_env"] = env
                if verbose:
                    print(f"  payload environment: {env.design_axial_g:.1f} g axial "
                          f"({env.governing_axial_event}), {env.design_lateral_g:.1f} g lateral")
        except Exception as ex:                                  # noqa: BLE001
            print(f"    payload environment skipped: {type(ex).__name__}: {ex}", file=sys.stderr)
    if "cost" in want:
        try:
            cst = cost_mod.estimate(res, year=int(spec.mission.get("cost_year") or 2010))
            extras["cost"] = cst
            if verbose:
                print(f"  cost: {cst.development_wyr:,.0f} work-years development "
                      f"(${cst.development_usd/1e9:,.1f} B, {cst.year} dollars); "
                      f"${cst.per_flight_central_usd/1e6:,.0f} M per flight by the rule of thumb")
        except Exception as ex:                                  # noqa: BLE001
            print(f"    cost estimate skipped: {type(ex).__name__}: {ex}", file=sys.stderr)
    if "uncertainty" in want:
        if verbose:
            print(f"  uncertainty: {n_mc} Monte-Carlo samples ...", flush=True)
        try:
            mc = uncertainty.monte_carlo(design, assump, n=n_mc)
            extras["uncertainty"] = mc
            figs["uncertainty_png"] = os.path.join(outdir, "uncertainty.png")
            charts.draw_uncertainty(mc, figs["uncertainty_png"], None,
                                    title=f"{spec.name} - GLOM under MER scatter")
            if verbose:
                print(f"    GLOM {mc['p05']:,.0f} / {mc['p50']:,.0f} / {mc['p95']:,.0f} kg "
                      f"(5 / 50 / 95 %), {mc['n_converged']}/{mc['n_requested']} samples converged")
        except Exception as ex:                                  # noqa: BLE001
            print(f"    uncertainty study skipped: {type(ex).__name__}: {ex}", file=sys.stderr)
    return extras


def _print_kernel_check(cad_kernel, res) -> bool:
    """Print the exact-solid cross-check, part by part. Returns True when every part passed.

    This is the check the author of cad_kernel.py could never run: no CadQuery was installable in
    the environment it was written in. On a machine that has it, this is the evidence that the
    STEP geometry is right - each solid's volume as OpenCASCADE computes it against the
    closed-form frustum sum, which involves no kernel at all.
    """
    st = cad_kernel.status()
    if not st["available"]:
        print(f"Kernel:   not available - {st['reason']}")
        print(f"          install with: {st['install']}")
        return False
    rep = cad_kernel.verify_solids(res)
    print(f"Kernel:   cadquery {st['version']}; tolerance {rep['volume_tolerance']:.0e} on volume, "
          f"{rep['bbox_tolerance_m']:.0e} m on the bounding box")
    print(f"  {'part':<22}{'closed form m^3':>17}{'kernel m^3':>15}{'rel err':>11}  "
          f"{'route':<10}result")
    for row in rep["parts"]:
        kv = "-" if row["kernel_volume_m3"] is None else f"{row['kernel_volume_m3']:.6f}"
        err = "-" if row["volume_rel_error"] is None else f"{row['volume_rel_error']:.2e}"
        print(f"  {row['part']:<22}{row['exact_volume_m3']:>17.6f}{kv:>15}{err:>11}  "
              f"{str(row['route'] or '-'):<10}{'ok' if row['ok'] else 'FAILED'}")
        if not row["ok"]:
            print(f"      {row['why']}")
    # Kept as a plain conditional rather than folded into the f-string: an f-string whose EXPRESSION spans
    # two source lines is PEP 701 syntax and only parses on Python 3.12+, while this project supports 3.10.
    verdict = ("all parts matched" if rep["all_ok"]
               else "AT LEAST ONE PART FAILED - no solid would be exported")
    print(f"  {verdict}")
    return rep["all_ok"]


def run(design, assump, outdir, with_sens=True, with_opt=False, verbose=True, with_report=True, pdf=False,
        studies=(), n_mc=200, cad=False, cad_facets=cad_export.DEFAULT_FACETS,
        cad_formats=None, verify_kernel=False):
    os.makedirs(outdir, exist_ok=True)
    spec = load_design(design, assump)
    # `vehicle.optimise_dv_split` replaces the allocation before sizing, so the report describes one vehicle
    spec, opt_note = optimization.apply_optimum(spec)
    if opt_note:
        print(("  " + opt_note["why"]) if opt_note.get("applied")
              else f"  optimisation requested but not applied: {opt_note['why']}")
    res = size_vehicle(spec)
    figs = {}
    figs["vehicle_png"] = os.path.join(outdir, "vehicle_schematic.png")
    figs["vehicle_pdf"] = os.path.join(outdir, "vehicle_schematic.pdf")
    schematic_2d.draw_vehicle(res, figs["vehicle_png"], figs["vehicle_pdf"])
    for s in res.stages:
        figs[f"stage{s.index}_png"] = os.path.join(outdir, f"stage{s.index}_schematic.png")
        figs[f"stage{s.index}_pdf"] = os.path.join(outdir, f"stage{s.index}_schematic.pdf")
        schematic_2d.draw_stage(res, s.index, figs[f"stage{s.index}_png"], figs[f"stage{s.index}_pdf"])
    if with_report:                      # page-shaped variants: one drawing per printed page, filling it
        figs["vehicle_page_png"] = os.path.join(outdir, "vehicle_schematic_page.png")
        schematic_2d.draw_vehicle_page(res, figs["vehicle_page_png"], None)
        for s in res.stages:
            figs[f"stage{s.index}_page_png"] = os.path.join(outdir, f"stage{s.index}_schematic_page.png")
            schematic_2d.draw_stage_page(res, s.index, figs[f"stage{s.index}_page_png"], None)
    figs["mass_distribution_png"] = os.path.join(outdir, "mass_distribution.png")
    figs["mass_distribution_pdf"] = os.path.join(outdir, "mass_distribution.pdf")
    schematic_2d.draw_mass_distribution(res, figs["mass_distribution_png"], figs["mass_distribution_pdf"])
    cad_paths = {}
    if cad or verify_kernel:
        from . import cad_kernel
    if verify_kernel:
        _print_kernel_check(cad_kernel, res)
    if cad:
        cad_dir = os.path.join(outdir, "cad")
        cad_paths = cad_export.export_all(res, cad_dir, facets=cad_facets, kernel=False)
        if cad_kernel.available():
            fmts = tuple(cad_formats) if cad_formats else cad_kernel.DEFAULT_FORMATS
            try:
                cad_paths.update(cad_kernel.export_solids(res, cad_dir, formats=fmts))
            except Exception as ex:                              # noqa: BLE001
                cad_paths["kernel_error"] = f"{type(ex).__name__}: {ex}"
        elif cad_formats:
            cad_paths["kernel_error"] = cad_kernel.status()["reason"]
        figs["isometric_png"] = os.path.join(outdir, "isometric_view.png")
        schematic_2d.draw_isometric(res, figs["isometric_png"], None, facets=min(cad_facets, 48))
    csvs = reporting.export_csv(res, outdir)
    reporting.write_register(path_xlsx=os.path.join(outdir, "engineering_method_register.xlsx"), path_csv=os.path.join(outdir, "engineering_method_register.csv"))
    sens = comp = opt = None
    if with_sens:
        sens = sensitivity.standard_studies(design, assump, res)
        comp = sensitivity.configuration_comparison(design, assump, res)
    if with_opt:
        opt = optimization.optimize_dv_split(spec)
    extras = _studies(design, assump, spec, res, outdir, figs, set(studies), n_mc, verbose,
                      applied_opt=(opt_note or {}).get("result")) if studies else {}
    wb_path = os.path.join(outdir, "launch_vehicle_sizing_workbook.xlsx")
    reporting.write_workbook(res, wb_path, figs, sens, comp, opt, design_path=design, loads=extras.get("loads"), ascent_opt=extras.get("ascent_optimum"), structure=extras.get("structure"))
    rep = {}
    if with_report:
        rep = report_mod.write_report(res, os.path.join(outdir, "design_report.html"), figs,
                                      design_path=design, assump_path=assump, pdf=pdf, extras=extras)
    summary = dict(design=spec.name, status=res.status, converged=res.converged, iterations=res.iterations, residual=res.residual, glom_kg=res.glom_kg,
                   dv_required_mps=res.dv_required_mps, dv_achieved_mps=res.dv_achieved_mps, length_m=res.geometry.total_length,
                   stages=[dict(index=s.index, dry_kg=s.m_dry_kg, propellant_loaded_kg=s.m_prop_loaded_kg, s=s.structural_factor_s, burn_s=s.burn_time_s,
                                tw0=s.tw_ignition, length_m=s.length_m) for s in res.stages],
                   issues=[str(i) for i in res.issues],
                   studies=sorted(extras),
                   outputs=dict(workbook=wb_path, **{("cad_" + k): v for k, v in cad_paths.items()}, **{("report_" + k): v for k, v in rep.items()}, **figs, **csvs))
    with open(os.path.join(outdir, "run_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    if verbose:
        print(f"{spec.name}: {res.status} in {res.iterations} iterations (residual {res.residual:.2e})")
        print(f"GLOM {res.glom_kg:,.0f} kg | payload {res.payload_mass_kg:,.0f} kg | dv {res.dv_required_mps:,.0f} m/s | length {res.geometry.total_length:.2f} m")
        for i in res.issues:
            print("  ", i)
        print("Workbook:", wb_path)
        if cad_paths:
            from . import cad_kernel
            summ = cad_export.mesh_summary(cad_export.vehicle_meshes(res, cad_facets))
            mesh_fmts = [k for k in ("dxf", "stl", "obj", "3mf") if k in cad_paths]
            solid_fmts = [k for k in cad_paths if k not in mesh_fmts and k != "kernel_error"]
            print(f"CAD:      {', '.join(cad_paths[k] for k in mesh_fmts)}")
            print(f"          {summ['parts']} parts, {summ['triangles']:,} triangles, "
                  f"{summ['watertight_parts']}/{summ['parts']} closed shells; "
                  f"faceted volume is {100 * (1 - cad_export.faceted_volume_ratio(cad_facets)):.3f}% "
                  f"light at {cad_facets} facets.")
            if solid_fmts:
                st = cad_kernel.status()
                print(f"          exact solids via cadquery {st['version']}: "
                      f"{', '.join(cad_paths[k] for k in solid_fmts)}")
                print("          each solid was checked against its closed-form volume before "
                      "writing (--verify-kernel prints the check).")
            else:
                print("          exact solids (STEP): not written - "
                      f"{cad_kernel.status()['reason'].split('.')[0]}.")
                print("          'pip install cadquery' adds STEP and BREP; the files above need "
                      "nothing.")
            if cad_paths.get("kernel_error"):
                print(f"          kernel route FAILED, mesh files above are unaffected: "
                      f"{cad_paths['kernel_error']}", file=sys.stderr)
        if rep.get("html"):
            print("Report:  ", rep["html"] + (f" (+ {rep['pdf']})" if rep.get("pdf") else ""))
        if rep.get("pdf_note"):
            print("   PDF not produced:", rep["pdf_note"])
    return res, summary


def main(argv=None):
    ap = argparse.ArgumentParser(prog="launch_vehicle")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "optimize"):
        p = sub.add_parser(name)
        p.add_argument("--design", default="config/default_design.yaml")
        p.add_argument("--assumptions", default="config/engineering_assumptions.yaml")
        p.add_argument("--out", default="outputs")
        p.add_argument("--no-sensitivity", action="store_true")
        p.add_argument("--with-optimization", action="store_true")
        p.add_argument("--no-report", action="store_true", help="skip the single-file design report")
        p.add_argument("--pdf", action="store_true", help="also convert the report to PDF (needs Chrome, Edge or wkhtmltopdf)")
        p.add_argument("--performance", action="store_true",
                       help="payload capability curves vs altitude and inclination")
        p.add_argument("--uncertainty", action="store_true",
                       help="Monte-Carlo over the MER scatter: GLOM as a distribution")
        p.add_argument("--staging", action="store_true",
                       help="analytical vs numerical optimum delta-v split")
        p.add_argument("--trajectory", action="store_true",
                       help="3-DoF ascent trajectory: computed gravity, drag, propulsion and steering losses")
        p.add_argument("--optimise-ascent", action="store_true", dest="optimise_ascent",
                       help="search the pitch programme for maximum payload, within the dynamic pressure, "
                            "q-alpha and axial acceleration limits in the design's constraints block")
        p.add_argument("--cost", action="store_true",
                       help="TRANSCOST-style development effort and cost, and cost per flight")
        p.add_argument("--payload-env", action="store_true", dest="payload_env",
                       help="quasi-static load factors for the payload user's guide (implies --trajectory)")
        p.add_argument("--ballistics", action="store_true",
                       help="solid motor internal ballistics: the thrust and chamber pressure the grain "
                            "actually delivers, against the constant values the sizing assumed")
        p.add_argument("--structure", action="store_true",
                       help="shell stress, buckling and required wall thickness from the load cases "
                            "(implies --loads)")
        p.add_argument("--loads", action="store_true",
                       help="ground wind and max-q flight loads: axial, shear and bending along the vehicle "
                            "(implies --trajectory for the flight cases)")
        p.add_argument("--all-studies", action="store_true", help="all of the above")
        p.add_argument("--mc-samples", type=int, default=200, help="Monte-Carlo sample count (default 200)")
        p.add_argument("--cad", action="store_true",
                       help="export the layout for CAD: a layered DXF inboard profile and the outer "
                            "mould line as STL, OBJ and 3MF meshes, plus an isometric view; adds "
                            "exact STEP solids when cadquery is installed (roadmap R15)")
        p.add_argument("--cad-facets", type=int, default=cad_export.DEFAULT_FACETS, dest="cad_facets",
                       help=f"sides per revolution in the exported meshes "
                            f"(default {cad_export.DEFAULT_FACETS}; more is smoother and larger)")
        p.add_argument("--cad-formats", dest="cad_formats",
                       help="comma-separated exact-solid formats to write, which needs cadquery "
                            "installed: step, brep, 3mf, amf, vrml, gltf (default step,3mf). "
                            "Faceted DXF/STL/OBJ/3MF are always written and need nothing")
        p.add_argument("--verify-kernel", action="store_true", dest="verify_kernel",
                       help="print the exact-solid cross-check (each solid's kernel volume against "
                            "the closed-form value) and write nothing; use it to confirm the STEP "
                            "route on a machine that has cadquery")
    ip = sub.add_parser("import-vehicles",
                        help="turn a public-source data sheet into annotated design YAML (roadmap R16)")
    ip.add_argument("--sheet", help="a .csv or .json vehicle sheet; omit with --template to write a blank one")
    ip.add_argument("--out", default="outputs/imported", help="directory to write the design files into")
    ip.add_argument("--base", default="config/default_design.yaml",
                    help="design whose assumed values an imported vehicle inherits - pick one of a "
                         "SIMILAR SIZE CLASS, since absolute mass assumptions do not scale")
    ip.add_argument("--solid-base", default="examples/example_solid_smallsat.yaml", dest="solid_base",
                    help="design to take the solid-stage template from")
    ip.add_argument("--template", metavar="PATH",
                    help="write a blank sheet with every understood column to PATH and stop")
    ip.add_argument("--report", action="store_true",
                    help="print the full per-vehicle import report, not just the summary line")
    tp = sub.add_parser("trade", help="run a trade study declared in YAML (roadmap R17)")
    tp.add_argument("--study", required=True, help="a YAML file with a trade_study: block")
    tp.add_argument("--out", default="outputs/trade")
    cp = sub.add_parser("compare", help="size several designs and put them side by side (roadmap R14)")
    cp.add_argument("--designs", nargs="+", required=True, help="two or more design YAML files")
    cp.add_argument("--assumptions", default="config/engineering_assumptions.yaml")
    cp.add_argument("--out", default="outputs/compare")
    fp = sub.add_parser("family",
                        help="launch vehicle families: one core, several strap-on counts (R37)")
    fp.add_argument("--name", default=None,
                    help="family slug or name; omit to list every family found")
    fp.add_argument("--assumptions", default="config/engineering_assumptions.yaml")
    fp.add_argument("--pinned", action="store_true",
                    help="also pin the reference variant's core and ask it for each variant's architecture")
    xp = sub.add_parser("architecture",
                        help="pin a design's stages and change the strap-on count: what does it lift? (R35)")
    xp.add_argument("--design", required=True, help="the design whose stages and booster unit are pinned")
    xp.add_argument("--assumptions", default="config/engineering_assumptions.yaml")
    xp.add_argument("--boosters", nargs="+", type=int, default=None, metavar="N",
                    help="booster counts to try; default 0 to twice the design's own count")
    xp.add_argument("--ground-lit", type=int, default=None,
                    help="how many of them are lit on the ground; default follows the design's own split")
    xp.add_argument("--size-core", action="store_true",
                    help="the other direction: re-size the core for each count instead of pinning it")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "run":
            want = {k for k in ("performance", "uncertainty", "staging", "trajectory", "loads",
                                "optimise_ascent", "structure", "ballistics", "cost", "payload_env")
                    if getattr(a, k) or a.all_studies}
            if "payload_env" in want:
                want.add("trajectory")        # the load factors come from the flown ascent
            if "structure" in want:
                want.add("loads")             # the stress analysis is driven by the load cases
            if "loads" in want:
                want.add("trajectory")        # the flight load cases need a flown trajectory
            run(a.design, a.assumptions, a.out, not a.no_sensitivity, a.with_optimization,
                with_report=not a.no_report, pdf=a.pdf, studies=want, n_mc=a.mc_samples,
                cad=a.cad or a.all_studies, cad_facets=a.cad_facets,
                cad_formats=[s.strip() for s in a.cad_formats.split(",") if s.strip()]
                if a.cad_formats else None,
                verify_kernel=a.verify_kernel)
        elif a.cmd == "import-vehicles":
            if a.template:
                print("Blank sheet written:", vehicle_import.write_template_csv(a.template))
                return 0
            if not a.sheet:
                print("ERROR: give --sheet PATH, or --template PATH to write a blank one",
                      file=sys.stderr)
                return 2
            reps = vehicle_import.import_sheet(a.sheet, a.out, a.base, a.solid_base)
            for rep in reps:
                print(f"{rep.path}\n   {rep.summary()}")
                for w in rep.warnings:
                    print(f"   WARNING: {w}")
                for k, cands in sorted(rep.ambiguous.items()):
                    print(f"   AMBIGUOUS, left out: {k} (candidates: {', '.join(cands)})")
                if a.report:
                    print("\n" + rep.as_text() + "\n")
            n_ass = sum(r.n_assumed for r in reps)
            print(f"\n{len(reps)} design(s) written. {n_ass} leaves across them are the tool's own "
                  f"estimates, not source data - run with --report to see which.")
        elif a.cmd in ("trade", "compare"):
            os.makedirs(a.out, exist_ok=True)
            if a.cmd == "trade":
                import yaml
                with open(a.study, encoding="utf-8") as f:
                    decl = yaml.safe_load(f)
                study = studies_mod.run_trade_study(decl, root=os.getcwd())
                outputs = (decl.get("trade_study") or decl).get("outputs")
            else:
                study = studies_mod.compare_designs(a.designs, a.assumptions)
                outputs = None
            png = os.path.join(a.out, f"{a.cmd}.png")
            charts.draw_study(study, png, None, title=study["name"])
            csvp = studies_mod.write_csv(study, os.path.join(a.out, f"{a.cmd}.csv"), outputs)
            htmlp = studies_mod.write_html(study, os.path.join(a.out, f"{a.cmd}.html"), png, outputs)
            ok = sum(1 for c in study["cases"] if c.ok)
            print(f"{study['name']}: {ok}/{len(study['cases'])} case(s) converged cleanly")
            for n in study["notes"]:
                print("   " + n)
            print(f"Table:  {csvp}")
            print(f"Report: {htmlp}")
        elif a.cmd == "family":
            from . import families as fam
            root = os.getcwd()
            if not a.name:
                found = fam.discover(root)
                if not found:
                    print("No families found. A family is a folder with a family.yaml in it, under "
                          "designs/families/, examples/families/ or validation/families/ - see "
                          "docs/USER_MANUAL.md 7.17c for the manifest format.")
                    return 0
                print(f"{len(found)} family/families:")
                for f in found:
                    ref = f" (reference: {f.reference})" if f.reference else ""
                    print(f"\n  {f.slug}: {f.name}{ref}")
                    for v in f.variants:
                        n = v.overrides.get("boosters.n_total")
                        pub = v.published_kg("payload_kg")
                        print(f"      {v.key:<6} {v.label}"
                              + (f"   {n} booster(s)" if n is not None else "")
                              + (f", {pub:,.0f} kg published" if pub else ""))
                return 0
            f = fam.find(root, a.name)
            print(f"{f.name}  -  {len(f.variants)} variants, base {os.path.relpath(f.base_path, root)}")
            if f.note:
                print("  " + " ".join(f.note.split()))
            print("\nEach variant sized on its OWN, delta-v split re-optimised:")
            print("  {:<34}{:>12}{:>12}{:>9}".format("variant", "tool GLOM", "published", "err"))
            for r in fam.size_family(f, a.assumptions):
                if r["error"]:
                    print("  {:<34} {}".format(r["label"], r["error"][:60])); continue
                err = "{:>+8.1f}%".format(100 * r["glom_err"]) if r["glom_err"] is not None else "       - "
                print("  {:<34}{:>12,.0f}{:>12,.0f}{}{}".format(
                    r["label"], r["result"].glom_kg, r["published_glom_kg"] or 0, err,
                    "  <- reference" if r["is_reference"] else ""))
            if a.pinned:
                print(f"\nReference variant ({f.reference}) PINNED, booster count changed (method M102):")
                print("  {:<34}{:>12}{:>12}{:>9}".format("variant", "pinned PL", "published", "err"))
                for r in fam.pinned_family(f, a.assumptions):
                    if not r["flyable"] or r["payload_kg"] is None:
                        print("  {:<34} {}".format(r["label"], r["reason"][:60])); continue
                    err = ("{:>+8.1f}%".format(100 * r["payload_err"])
                           if r["payload_err"] is not None else "       - ")
                    print("  {:<34}{:>12,.0f}{:>12,.0f}{}{}".format(
                        r["label"], r["payload_kg"], r["published_payload_kg"] or 0, err,
                        "  <- reference" if r["is_reference"] else ""))
            print("\nThe two tables err in OPPOSITE directions and both come from the same cause: a real family\n"
                  "shares ONE core, sized for its largest member, and this tool never carries a core that is\n"
                  "oversized for the mission being flown. Sizing each variant on its own gives every one its own\n"
                  "minimal core, so the small variants come out too light; pinning the reference core still\n"
                  "pins a core lighter than the real shared one, so the small variants get too much payload.\n"
                  "See docs/ACCURACY.md 6b.3 and 6b.5.")
        elif a.cmd == "architecture":
            from . import architecture as arch
            spec = load_design(a.design, a.assumptions)
            if a.size_core:
                counts = a.boosters or [spec.boosters.n_total]
                print(f"{spec.name}: core RE-SIZED for each booster count, payload held at "
                      f"{spec.payload_mass_kg:,.0f} kg")
                print(f"{'n':>4} {'GLOM kg':>14} {'core prop kg':>14} {'stages':>8}  note")
                for n in counts:
                    try:
                        r = arch.core_for_boosters(spec, n, a.ground_lit)
                        print(f"{n:>4} {r.glom_kg:>14,.0f} {r.stages[0].m_prop_loaded_kg:>14,.0f} "
                              f"{len(r.stages):>8}  {'as designed' if n == spec.boosters.n_total else ''}")
                    except (SizingError, ValueError, arch.ArchitectureError) as ex:
                        print(f"{n:>4} {'n/a':>14}  {ex}")
                return 0
            res = size_vehicle(spec, keep_history=False)
            pv = arch.pin(res)
            print(f"{spec.name}: stages and the {pv.booster_label} unit PINNED at the design's values, "
                  f"booster count varied")
            print(f"   as designed: {pv.reference_n_boosters} booster(s), "
                  f"{res.payload_mass_kg:,.0f} kg payload, {res.glom_kg:,.0f} kg GLOM")
            print(f"\n{'n':>4} {'payload kg':>12} {'GLOM kg':>13} {'T/W':>6} {'vs design':>11}  note")
            for out in arch.booster_count_sweep(pv, counts=a.boosters):
                if out.flyable:
                    d = out.payload_kg - res.payload_mass_kg
                    print(f"{out.n_boosters:>4} {out.payload_kg:>12,.0f} {out.glom_kg:>13,.0f} "
                          f"{out.liftoff_tw:>6.2f} {d:>+11,.0f}  "
                          f"{'as designed' if out.is_reference else ''}")
                else:
                    print(f"{out.n_boosters:>4} {'n/a':>12}  {out.reason}")
            print("\nThe stages are NOT re-sized: this is what THIS core lifts in another booster "
                  "architecture, not the\nvehicle a designer would draw for it. Measured against the two "
                  "launcher families that publish a figure\nfor several counts of the same core, pinning "
                  "over-predicts the smaller variants by 19-52 %: see\ndocs/ACCURACY.md 6b.5. Use --size-core "
                  "for the other direction, where the core is re-sized each time.")
        else:
            spec = load_design(a.design, a.assumptions)
            print(json.dumps(optimization.optimize_dv_split(spec), indent=2))
    except (InputError, SizingError, ValueError) as ex:
        print(f"ERROR: {ex}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
