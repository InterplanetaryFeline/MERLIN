"""Dimensioned, proportionally scaled 2D longitudinal schematics (Matplotlib).

Every dimension is read from the same VehicleGeometry / StageResult objects used by the calculation engine;
nothing is hard-coded here. Preliminary engineering representation - NOT a manufacturing drawing.

Drawing conventions
-------------------
* axial coordinate z upward from the first-stage nozzle exit plane; the view is a longitudinal cut
* dimensions follow normal engineering practice: thin witness (extension) lines projected from the feature,
  a dimension line with arrowheads between them, and a short value label - lengths on the left of the
  vehicle, outer diameters across the body, both in a small fixed-size font
* all numerical callouts (masses, Isp, burn times) live in the data panel on the right, never on top of the
  vehicle outline
"""
from __future__ import annotations
import math
import re
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.patches import Polygon, Rectangle, Arc, Ellipse, Patch
from . import propulsion as prop

COL = {"aft_skirt": "#d9dee5", "tank_fuel": "#f6d7a7", "tank_oxidizer": "#a9d3f0", "tank_grain": "#d8c3a5",
       "intertank": "#e6e6e6", "fwd_skirt": "#d9dee5", "interstage": "#cfd6df", "fwd_adapter": "#cfd6df",
       "paf": "#bbbbbb", "fairing_cyl": "#f2f2f2", "fairing_nose": "#f2f2f2", "booster_case": "#e3d3c0",
       "booster_nose": "#eeeeee", "engine": "#8c8c8c"}
DIM = "#1a3d7c"          # dimension colour
RED = "#aa3333"
GREEN = "#117733"
FS_DIM = 6.5             # dimension text size (points) - kept small so labels never cover the vehicle


def _clip(ax, ann):
    """Clip an annotation's arrow to the axes. Matplotlib does not do this by default, so an unclipped dimension
    line would run off the figure in a paged (multi-window) view."""
    ap = getattr(ann, "arrow_patch", None)
    if ap is not None:
        ap.set_clip_path(ax.patch)
        ap.set_clip_on(True)


def _poly(ax, pts, fc, ec="k", lw=0.8, z=2, **kw):
    ax.add_patch(Polygon(pts, closed=True, fc=fc, ec=ec, lw=lw, zorder=z, **kw))


# --------------------------------------------------------------------------------------- dimensions
def _dim_v(ax, x, z0, z1, label, body_x=None, tick=None, fs=FS_DIM, color=DIM, lw=0.6):
    """Vertical dimension at x between z0 and z1, with witness lines running out from the body."""
    tick = tick if tick is not None else abs(x) * 0.04 + 0.05
    if body_x is not None:
        for z in (z0, z1):
            ax.plot([body_x if x > 0 else -abs(body_x), x], [z, z], lw=0.4, color=color, zorder=6, alpha=0.8)
    a = ax.annotate("", xy=(x, z0), xytext=(x, z1),
                    arrowprops=dict(arrowstyle="<|-|>", mutation_scale=5, lw=lw, color=color, shrinkA=0, shrinkB=0),
                    zorder=7)
    _clip(ax, a)
    ax.text(x, 0.5 * (z0 + z1), label, rotation=90, ha="center", va="center", fontsize=fs, color=color,
            bbox=dict(fc="white", ec="none", pad=0.8), zorder=8)


def _dim_h(ax, z, x0, x1, label, tick, fs=FS_DIM, color=DIM, lw=0.7, label_above=True):
    """Horizontal (diameter) dimension at height z between x0 and x1, with short witness lines."""
    for x in (x0, x1):
        ax.plot([x, x], [z - tick, z + tick], lw=0.5, color=color, zorder=7)
    a = ax.annotate("", xy=(x0, z), xytext=(x1, z),
                    arrowprops=dict(arrowstyle="<|-|>", mutation_scale=5, lw=lw, color=color, shrinkA=0, shrinkB=0),
                    zorder=7)
    _clip(ax, a)
    ax.text(0.5 * (x0 + x1), z + (tick * 0.5 if label_above else -tick * 0.5), label, ha="center",
            va="bottom" if label_above else "top", fontsize=fs, color=color,
            bbox=dict(fc="white", ec="none", pad=0.6), zorder=9)


# --------------------------------------------------------------------------------------- components
def _draw_tank(ax, seg, fc, x0=0.0):
    g = seg.tank
    R = g.R_int + g.t_wall
    hd = g.h_dome + g.t_wall
    has_bot = g.bulkhead != "upper_user"
    has_top = g.bulkhead != "lower_owner"
    zb = seg.z0 + (hd if has_bot else 0.0)
    zt = seg.z1 - (hd if has_top else 0.0)
    ax.add_patch(Rectangle((x0 - R, zb), 2 * R, max(zt - zb, 0), fc=fc, ec="none", zorder=2))
    for xs in (x0 - R, x0 + R):
        ax.plot([xs, xs], [zb, zt], color="k", lw=0.8, zorder=3)
    if has_bot:
        ax.add_patch(Arc((x0, zb), 2 * R, 2 * hd, theta1=180, theta2=360, ec="k", lw=0.8, zorder=3))
        ax.add_patch(Ellipse((x0, zb), 2 * R, 2 * hd, fc=fc, ec="none", zorder=1))
    if has_top:
        ax.add_patch(Arc((x0, zt), 2 * R, 2 * hd, theta1=0, theta2=180, ec="k", lw=0.8, zorder=3))
        ax.add_patch(Ellipse((x0, zt), 2 * R, 2 * hd, fc=fc, ec="none", zorder=1))
    if g.bulkhead == "lower_owner":
        ax.add_patch(Arc((x0, seg.z1), 2 * R, 2 * g.h_dome, theta1=0, theta2=180, ec="k", lw=1.1, zorder=4))
    if getattr(g, "R_bore", 0.0) > 0:          # solid motor: show the cast grain and its central bore
        _draw_grain(ax, seg, x0)


def _draw_grain(ax, seg, x0=0.0):
    """Hatched propellant grain with a central combustion bore (core burner, book Fig. 4.10 right)."""
    g = seg.tank
    R, rb, hd = g.R_int, g.R_bore, g.h_dome
    z0 = seg.z0 + g.t_wall
    zc0, zc1 = (z0, z0 + g.L_int) if g.bore_full_length else (z0 + hd, z0 + hd + g.h_cyl)
    for sgn in (-1, 1):
        ax.add_patch(Rectangle((x0 + sgn * rb if sgn > 0 else x0 - R, zc0), R - rb, zc1 - zc0,
                               fc="none", ec="#6b5436", lw=0.5, hatch="///", zorder=3.5))
    ax.add_patch(Rectangle((x0 - rb, zc0), 2 * rb, zc1 - zc0, fc="white", ec="#6b5436", lw=0.5, zorder=3.6))
    ax.text(x0, 0.5 * (zc0 + zc1), "bore", rotation=90, ha="center", va="center", fontsize=5.5,
            color="#6b5436", zorder=3.7)


def _draw_engines(ax, res, sr, x0=0.0, z_exit=None):
    """Engine/nozzle silhouettes using the envelope actually used for the layout."""
    env = sr.envelope
    if env is None:
        return
    z_exit = res.geometry.engine_exit_z[sr.index] if z_exit is None else z_exit
    z_top = z_exit + env.length_m
    n = env.n
    rc = prop.engine_ring_radius(n, env.exit_diameter_m)
    xs = [0.0] if n == 1 else sorted(rc * math.cos(2 * math.pi * k / n + math.pi / n) for k in range(n))
    d_th = 0.18 * env.exit_diameter_m
    for k, x in enumerate(xs):
        x += x0
        pts = [(x - env.exit_diameter_m / 2, z_exit), (x + env.exit_diameter_m / 2, z_exit),
               (x + d_th, z_exit + 0.62 * env.length_m), (x + 0.9 * d_th, z_top), (x - 0.9 * d_th, z_top),
               (x - d_th, z_exit + 0.62 * env.length_m)]
        _poly(ax, pts, COL["engine"] if k % 2 == 0 else "#a8a8a8", z=2.6)


def _draw_segments(ax, segs, x0=0.0):
    for s in segs:
        if s.kind in ("tank", "booster_case"):
            fc = COL["tank_" + s.tank.role] if s.kind == "tank" else COL["booster_case"]
            _draw_tank(ax, s, fc, x0)
        elif s.kind in ("fairing_nose", "booster_nose"):
            _poly(ax, [(x0 - s.d_bot / 2, s.z0), (x0 + s.d_bot / 2, s.z0), (x0, s.z1)], COL[s.kind])
        else:
            _poly(ax, [(x0 - s.d_bot / 2, s.z0), (x0 + s.d_bot / 2, s.z0), (x0 + s.d_top / 2, s.z1),
                       (x0 - s.d_top / 2, s.z1)], COL.get(s.kind, "#dddddd"))


def _draw_boosters(ax, res):
    """Two strap-on silhouettes (left and right of the core) with their nozzles."""
    geom, br = res.geometry, res.boosters
    if br is None or not geom.booster_segments:
        return
    b = res.spec.boosters
    for sgn in (-1, 1):
        x0 = sgn * geom.booster_x_m
        _draw_segments(ax, geom.booster_segments, x0)
        z_exit = b.base_z_offset_m
        d, L = b.exit_diameter_m, b.nozzle_length_m
        _poly(ax, [(x0 - d / 2, z_exit), (x0 + d / 2, z_exit), (x0 + 0.18 * d, z_exit + L), (x0 - 0.18 * d, z_exit + L)],
              COL["engine"], z=2.6)


# --------------------------------------------------------------------------------------- panels
def _stage_table_lines(res):
    spec = res.spec
    out = ["STAGE SUMMARY", "stage  type    D[m]   L[m]  prop[kg]   dry[kg]      s   Isp[s] burn[s]  dv[m/s]"]
    for sr in res.stages:
        st = spec.stages[sr.index - 1]
        out.append(f"{sr.index:^5d}  {sr.stage_type:6s} {st.diameter_m:5.2f} {sr.length_m:6.2f} "
                   f"{sr.m_prop_loaded_kg:9,.0f} {sr.m_dry_kg:9,.0f} {sr.structural_factor_s:6.3f} "
                   f"{sr.isp_eff_s:6.1f} {sr.burn_time_s:7.0f} {sr.dv_mps:8,.0f}")
    br = res.boosters
    if br is not None:
        out.append(f"{'0':^5s}  {br.kind:6s} {br.diameter_m:5.2f} {br.length_m:6.2f} "
                   f"{br.m_prop_each_kg:9,.0f} {br.m_inert_each_kg:9,.0f} {br.structural_factor_s:6.3f} "
                   f"{br.isp_eff_s:6.1f} {br.burn_time_s:7.0f}    (each of {br.n_total})")
    return out


def _info_panel(axt, res):
    spec, geom = res.spec, res.geometry
    m = spec.mission
    lift = res.mass_properties["events"][0]
    L = geom.total_length
    lines = [f"{spec.name}", "=" * 78, "",
             f"MISSION   payload {res.payload_mass_kg:,.0f} kg -> {m['orbit_type']} "
             f"{m['perigee_altitude_m']/1e3:,.0f} km, i = {res.budget.info.get('inclination_deg', m['inclination_deg']):.2f} deg",
             f"          delta-v required {res.dv_required_mps:,.0f} m/s   (achieved {res.dv_achieved_mps:,.0f} m/s)",
             f"          status: {res.status} after {res.iterations} iterations",
             "",
             f"MASS      GLOM {res.glom_kg:,.0f} kg | payload fraction {100*res.payload_mass_kg/res.glom_kg:.2f} % "
             f"| lift-off T/W {res.liftoff_tw:.2f}",
             f"          dry (all stages) {sum(s.m_dry_kg for s in res.stages):,.0f} kg | "
             f"propellant {sum(s.m_prop_loaded_kg for s in res.stages):,.0f} kg",
             f"          fairing {res.fairing_mass_kg:,.0f} kg | PAF {res.paf_mass_kg:,.0f} kg",
             f"GEOMETRY  overall length {L:.2f} m | max diameter {geom.max_diameter:.2f} m | L/D {L/geom.max_diameter:.1f}"
             + (f" | span over boosters {geom.max_span_m:.2f} m" if res.boosters else ""),
             f"MASS PROP CM at lift-off z = {lift['z_cm_m']:.2f} m ({100*lift['z_cm_over_L']:.0f} % of length) | "
             f"J_roll {lift['J_roll']:.3g} | J_pitch {lift['J_pitch']:.3g} kg m^2",
             ""]
    lines += _stage_table_lines(res)
    br = res.boosters
    if br is not None:
        lines += ["", f"STRAP-ON BOOSTERS: {br.n_total} x {br.name} ({br.n_ground_lit} ground-lit), "
                      f"total {br.m_total_kg:,.0f} kg",
                  "  phase                                          t[s]  Isp[s]     m_start     m_end   dv[m/s]"]
        for p in res.stages[br.attach_stage - 1].phases:
            lines.append(f"  {p.name[:44]:44s} {p.duration_s:5.0f} {p.isp_eff_s:7.1f} {p.m_start_kg:11,.0f} "
                         f"{p.m_end_kg:9,.0f} {p.dv_mps:9,.0f}")
    solid = [s for s in res.stages if s.is_solid]
    if solid:
        lines += ["", "SOLID MOTORS      grain[m3]  casing[m3]  web[m]  bore R[m]  burn rate[mm/s]  k_casing"]
        for s in solid:
            i = s.motor_info
            lines.append(f"  stage {s.index:<2d}        {i['grain_volume_m3']:9.3f} {i['casing_volume_m3']:11.3f} "
                         f"{i['web_m']:7.3f} {i['bore_radius_m']:10.3f} {i['implied_burn_rate_mm_s']:16.1f} "
                         f"{i['casing_k']:9.4f}")
    errs = [i for i in res.issues if i.level == "ERROR"]
    warns = [i for i in res.issues if i.level == "WARNING"]
    lines += ["", f"CHECKS    {len(errs)} error(s), {len(warns)} warning(s)"]
    for i in (errs + warns)[:7]:
        msg = i.message if len(i.message) <= 70 else i.message[:67] + "..."
        lines.append(f"  [{i.level[0]}] {i.code}: {msg}")
    axt.text(0.0, 1.0, "\n".join(lines), fontsize=6.6, family="monospace", va="top", ha="left",
             transform=axt.transAxes, linespacing=1.45)
    axt.axis("off")


# --------------------------------------------------------------------------------------- main views
def _vehicle_on_ax(ax, res, scale=1.0, overall=True, xlim=None, callouts=False):
    """Draw the complete vehicle (hardware, dimensions, brackets, separation planes, CM) onto one axes.

    `scale` multiplies the text sizes: a paged view shows a shorter z-range in the same physical height, so the
    vehicle is drawn larger and the labels should grow with it. Everything is clipped to the axes, which is what
    lets the paged view show a z-window without redrawing anything.
    """
    spec, geom = res.spec, res.geometry
    L, D = geom.total_length, geom.max_diameter
    xh = max(D / 2, geom.max_span_m / 2)
    fs = FS_DIM * scale

    _draw_boosters(ax, res)
    _draw_segments(ax, geom.segments)
    for sr in res.stages:
        _draw_engines(ax, res, sr)

    # payload adapter and envelope
    Dt = spec.fairing.diameter_m
    ax.add_patch(Rectangle((-Dt / 2 + 0.15 * Dt, geom.paf_z0), Dt - 0.3 * Dt, geom.paf_z1 - geom.paf_z0,
                           fc=COL["paf"], ec="k", lw=0.6, zorder=3))
    ew = spec.fairing.envelope_diameter_m
    ax.add_patch(Rectangle((-ew / 2, geom.payload_z0), ew, geom.payload_z1 - geom.payload_z0, fc="none",
                           ec=RED, ls="--", lw=1.0, zorder=5))

    # ---- length dimensions (left) ----------------------------------------------------------
    x_len = -1.45 * xh
    for sr in res.stages:
        z0, z1 = geom.stage_base_z[sr.index], geom.stage_top_z[sr.index]
        _dim_v(ax, x_len, z0, z1, f"stage {sr.index}  {sr.length_m:.2f} m", fs=fs,
               body_x=-spec.stages[sr.index - 1].diameter_m / 2)
    zf = geom.fairing_base_z
    _dim_v(ax, x_len, zf, L, f"fairing + PAF  {L - zf:.2f} m", body_x=-Dt / 2, fs=fs)
    if overall:            # spans the whole vehicle, so it is meaningless inside a single z-window
        _dim_v(ax, -2.05 * xh, 0.0, L, f"OVERALL  {L:.2f} m", body_x=x_len, fs=7.5 * scale, lw=0.9)

    # ---- outer-diameter dimensions (across the body) ----------------------------------------
    tick = 0.012 * L
    for sr in res.stages:
        st = spec.stages[sr.index - 1]
        tanks = [x for x in geom.stage_segments(sr.index) if x.kind == "tank"]
        seg = max(tanks, key=lambda s: s.length) if tanks else geom.stage_segments(sr.index)[0]
        # on a solid stage the grain bore label sits at mid-height, so the diameter is dimensioned lower down
        z_dim = seg.z0 + (0.15 if sr.is_solid else 0.30) * seg.length
        _dim_h(ax, z_dim, -st.diameter_m / 2, st.diameter_m / 2, f"Ø {st.diameter_m:.2f} m", tick, fs=fs)
    cyl = [x for x in geom.segments if x.kind == "fairing_cyl"]
    if cyl:
        _dim_h(ax, cyl[0].z0 + 0.8 * cyl[0].length, -Dt / 2, Dt / 2, f"Ø {Dt:.2f} m", tick, fs=fs)
    br = res.boosters
    if br is not None:
        xb = geom.booster_x_m
        _dim_h(ax, br.z0 + 0.25 * (br.z1 - br.z0), xb - br.diameter_m / 2, xb + br.diameter_m / 2,
               f"Ø {br.diameter_m:.2f} m", tick, fs=fs)
        _dim_h(ax, -0.022 * L, -xb - br.diameter_m / 2, xb + br.diameter_m / 2,
               f"span {geom.max_span_m:.2f} m", tick, label_above=False, fs=fs)
        ax.text(-xb, br.z1 + 0.014 * L, f"{br.n_total} x strap-on", ha="center", va="bottom",
                fontsize=fs, color=DIM, bbox=dict(fc="white", ec="none", pad=0.6))

    # ---- stage brackets (right) -------------------------------------------------------------
    x_br = 1.25 * xh
    for sr in res.stages:
        st = spec.stages[sr.index - 1]
        z0, z1 = geom.stage_base_z[sr.index], geom.stage_top_z[sr.index]
        ax.plot([x_br, x_br], [z0, z1], lw=0.8, color="0.35", zorder=6)
        for z in (z0, z1):
            ax.plot([st.diameter_m / 2, x_br], [z, z], lw=0.4, color="0.6", zorder=6)
        label = f"STAGE {sr.index} ({'solid' if sr.is_solid else 'liquid'})"
        ax.text(x_br + 0.04 * xh, 0.5 * (z0 + z1), label, rotation=90, ha="left", va="center", fontsize=7 * scale,
                color="0.2")
    ax.plot([x_br, x_br], [zf, L], lw=0.8, color="0.35", zorder=6)
    ax.text(x_br + 0.04 * xh, 0.5 * (zf + L), "FAIRING", rotation=90, ha="left", va="center", fontsize=7 * scale,
            color="0.2")

    # ---- separation planes and centre of mass ------------------------------------------------
    for sr in res.stages[:-1]:
        z = geom.stage_top_z[sr.index]
        d = spec.stages[sr.index - 1].diameter_m
        ax.plot([-0.8 * d, 0.8 * d], [z, z], color=RED, ls="-.", lw=0.8, zorder=8)
        ax.text(0.82 * d, z, f"sep {sr.index}/{sr.index+1}", color=RED, fontsize=5.5 * scale, va="center", ha="left",
                zorder=8)
    lift = res.mass_properties["events"][0]
    zcm = lift["z_cm_m"]
    ax.plot([-0.6 * D, 0.6 * D], [zcm, zcm], color=GREEN, lw=1.2, zorder=9)
    ax.plot([0], [zcm], marker="o", ms=4, color=GREEN, zorder=9)
    if scale > 1.2:        # a larger label would run past the drawing edge, so it sits above the CM line
        ax.text(0.0, zcm + 0.004 * L, f"CM {zcm:.2f} m", color=GREEN, fontsize=fs, va="bottom", ha="center",
                zorder=9, bbox=dict(fc="white", ec="none", pad=0.8))
    else:
        ax.text(0.62 * D, zcm, f"CM {zcm:.1f} m", color=GREEN, fontsize=fs, va="center", ha="left", zorder=9)

    # ---- stage callouts, placed beside the stage they describe -------------------------------
    if callouts:
        x_call = 1.72 * xh
        for sr in res.stages:
            st = spec.stages[sr.index - 1]
            z0, z1 = geom.stage_base_z[sr.index], geom.stage_top_z[sr.index]
            kind = st.propellant if sr.is_solid else f"{st.oxidizer}/{st.fuel}  O/F {st.of_ratio:.2f}"
            txt = (f"STAGE {sr.index} - {sr.stage_type}\n{kind}\n"
                   f"Ø {st.diameter_m:.2f} m x {sr.length_m:.2f} m\n"
                   f"propellant {sr.m_prop_loaded_kg:,.0f} kg\n"
                   f"dry {sr.m_dry_kg:,.0f} kg\n"
                   f"s = {sr.structural_factor_s:.4f}\n"
                   f"Isp_eff {sr.isp_eff_s:.1f} s\n"
                   f"burn {sr.burn_time_s:.0f} s\n"
                   f"dv {sr.dv_mps:,.0f} m/s\n"
                   f"T/W at ignition {sr.tw_ignition:.2f}")
            ax.text(x_call, 0.5 * (z0 + z1), txt, fontsize=5.3 * scale, va="center", ha="left", zorder=10,
                    linespacing=1.3, bbox=dict(fc="white", ec="0.75", lw=0.5, pad=0.35))
        br = res.boosters
        if br is not None:
            ax.text(x_call, 0.5 * (br.z0 + br.z1),
                    f"{br.n_total} x {br.name}\n"
                    f"Ø {br.diameter_m:.2f} m x {br.length_m:.2f} m\n"
                    f"propellant {br.m_prop_each_kg:,.0f} kg ea\n"
                    f"inert {br.m_inert_each_kg:,.0f} kg ea\n"
                    f"s = {br.structural_factor_s:.4f}\n"
                    f"burn {br.burn_time_s:.0f} s\n"
                    f"total {br.m_total_kg:,.0f} kg",
                    fontsize=5.3 * scale, va="center", ha="left", zorder=10, linespacing=1.35,
                    bbox=dict(fc="white", ec="0.75", lw=0.5, pad=0.35))

    ax.set_aspect("equal")
    ax.set_xlim(*(xlim if xlim else (-2.35 * xh, 2.05 * xh)))
    ax.axhline(0, color="0.6", lw=0.5, ls=":")
    for t in ax.texts:                       # keep every label inside its own z-window in the paged view
        t.set_clip_on(True)


def _drawing_key(res):
    handles = [Patch(fc=COL["tank_fuel"], ec="k", label="fuel tank"), Patch(fc=COL["tank_oxidizer"], ec="k", label="oxidiser tank"),
               Patch(fc=COL["tank_grain"], ec="k", label="solid motor casing"), Patch(fc=COL["aft_skirt"], ec="k", label="skirts / intertank"),
               Patch(fc=COL["interstage"], ec="k", label="interstage / adapter"), Patch(fc=COL["engine"], ec="k", label="engines / nozzles"),
               Patch(fc="none", ec=RED, ls="--", label="payload envelope")]
    if res.boosters is not None:
        handles.append(Patch(fc=COL["booster_case"], ec="k", label="strap-on booster"))
    return handles


FOOTER = ("Preliminary engineering representation - not a manufacturing drawing. Dimensions are external unless "
          "stated. Values come from the same model that produced the workbook.")


def draw_vehicle(res, path_png=None, path_pdf=None):
    """Screen/workbook view: the vehicle in one column with the data panel beside it."""
    geom = res.geometry
    L, D = geom.total_length, geom.max_diameter
    xh = max(D / 2, geom.max_span_m / 2)
    # the drawing is to scale, so its axes box must have the vehicle's own aspect ratio; the width left over
    # goes to the data panel instead of being wasted as white space around a pencil-shaped vehicle
    x_span, z_span = 4.4 * xh, 1.07 * L
    fig_h = 15.0
    draw_w = min(max((fig_h - 1.8) * x_span / z_span, 3.0), 8.0)
    panel_w = 5.9
    fig = plt.figure(figsize=(draw_w + panel_w, fig_h))
    gs = GridSpec(1, 2, width_ratios=[draw_w, panel_w], wspace=0.03, figure=fig)
    ax = fig.add_subplot(gs[0, 0])
    axt = fig.add_subplot(gs[0, 1])
    _vehicle_on_ax(ax, res)
    ax.set_ylim(-0.035 * L, 1.035 * L)
    ax.set_xlabel("lateral position [m]", fontsize=8)
    ax.set_ylabel("axial coordinate z [m] (up from the stage-1 nozzle exit plane)", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.set_title("longitudinal schematic - to scale", fontsize=9.5)
    _info_panel(axt, res)
    axt.legend(handles=_drawing_key(res), loc="lower left", bbox_to_anchor=(0.0, 0.0), fontsize=6.6, ncol=2,
               framealpha=0.95, title="drawing key", title_fontsize=6.6)
    fig.text(0.008, 0.006, FOOTER, fontsize=6.5)
    _save(fig, path_png, path_pdf)
    return fig


def _n_columns(x_span, z_span, page_aspect, max_cols=4):
    """How many side-by-side z-windows make a drawing of this shape fill a page of the given aspect.

    A launch vehicle is 10-20 times longer than it is wide, so one full-height column uses a fifth of a portrait
    page and the vehicle ends up tiny. Splitting the z-range over N columns multiplies the drawn scale by N while
    keeping the drawing strictly to scale: with N columns the figure's aspect is N^2 x_span / z_span, so the N
    that fills the page is sqrt(page_aspect z_span / x_span).
    """
    if z_span <= 0 or x_span <= 0:
        return 1
    # drawn scale on a page of width `page_aspect` and height 1: the smaller of what width and height allow
    def drawn_scale(k):
        return min(page_aspect / (k * x_span), k / z_span)
    return max(range(1, max_cols + 1), key=drawn_scale)


def _break_marks(ax, z, side, xh):
    """The conventional break symbol: a wavy line across the drawing where the view is cut."""
    x = np.linspace(-2.3 * xh, 2.0 * xh, 160)
    amp = 0.004 * (ax.get_ylim()[1] - ax.get_ylim()[0])
    ax.plot(x, z + amp * np.sin(x / (0.09 * xh)), color="0.45", lw=0.8, zorder=12, clip_on=True)
    ax.text(2.0 * xh, z, "  break" if side == "top" else "  break", fontsize=5.5, color="0.45",
            va="bottom" if side == "top" else "top", ha="right", zorder=12, clip_on=True)


def draw_vehicle_page(res, path_png=None, path_pdf=None, page_aspect=0.80, fig_height_in=12.6, max_columns=1):
    """Report view: the whole vehicle as ONE continuous drawing, filling the page height, strictly to scale.

    A launch vehicle is 10-20 times longer than it is wide, so a single column that fills a portrait page leaves
    most of the page width unused. That spare width costs nothing - with the height binding, the drawn scale is
    set by the z-range alone, so the vehicle is exactly as large either way - and it is given to the dimension
    lines on the left and the stage callouts on the right rather than to white space.

    `max_columns` > 1 re-enables the older behaviour of splitting the z-range over several side-by-side windows,
    which draws the vehicle larger at the cost of cutting it into pieces. One continuous vehicle is the default
    because a drawing of a rocket should look like a rocket.
    """
    geom = res.geometry
    L, D = geom.total_length, geom.max_diameter
    xh = max(D / 2, geom.max_span_m / 2)
    n = _n_columns(4.4 * xh, 1.07 * L, page_aspect, max_cols=max(1, int(max_columns)))
    z_lo, z_hi = (-0.055 if res.boosters is not None else -0.035) * L, 1.035 * L
    z_col = (z_hi - z_lo) / n
    overlap = 0.02 * z_col if n > 1 else 0.0
    z_win = z_col + 2 * overlap

    # the lateral window: dimensions on the left, brackets and callouts on the right. Widening it does not shrink
    # the vehicle (the page height sets the scale), so it is sized to hold the annotations comfortably.
    x_lo, x_hi_min = -2.15 * xh, (4.6 if n == 1 else 2.05) * xh
    # one continuous column is sized to the annotations only: stretching it towards the page aspect would leave
    # the vehicle as a sliver against a wall of white, and would not draw it any larger
    x_span = (x_hi_min - x_lo) if n == 1 else \
        min(max(x_hi_min - x_lo, page_aspect * z_win / n), 3.0 * (x_hi_min - x_lo))
    x_hi = x_lo + x_span
    callouts = x_hi > 2.6 * xh

    scale = min(2.0, 0.55 + 0.52 * n) if n > 1 else 0.92
    # the axes keeps an equal aspect, so whichever of width or height is scarcer sets its size. The allowance
    # below is what the title block, the x label and the tick labels take; leaving it too small makes the axes
    # width-limited and strands white space above and below the vehicle
    col_h = fig_height_in - (1.6 if n > 1 else 2.45)
    col_w = col_h * x_span / z_win
    fig = plt.figure(figsize=(n * col_w + 1.1, fig_height_in))
    gs = GridSpec(1, n, wspace=0.14, figure=fig)
    for k in range(n):
        ax = fig.add_subplot(gs[0, k])
        _vehicle_on_ax(ax, res, scale=scale, overall=(n == 1), xlim=(x_lo, x_hi), callouts=callouts)
        z0 = z_lo + k * z_col - (overlap if k else 0.0)
        z1 = z_lo + (k + 1) * z_col + (overlap if k < n - 1 else 0.0)
        ax.set_ylim(z0, z1)
        if n > 1:
            if k:
                _break_marks(ax, z0 + overlap, "bottom", xh)
            if k < n - 1:
                _break_marks(ax, z1 - overlap, "top", xh)
            ax.set_title(f"z = {max(z0, 0.0):.1f} - {min(z1, L):.1f} m", fontsize=8.5)
        ax.tick_params(labelsize=7)
        ax.set_xlabel("lateral [m]", fontsize=7.5)
        ax.set_ylabel("axial coordinate z [m] (up from the stage-1 nozzle exit plane)" if k == 0 else "",
                      fontsize=8)
    sub = f"overall length {L:.2f} m, max diameter {D:.2f} m"
    if n > 1:
        # a wide figure: the legend fits across the bottom and the title on one line
        fig.legend(handles=_drawing_key(res), loc="lower center", bbox_to_anchor=(0.5, 0.004), fontsize=7,
                   ncol=4, framealpha=0.95)
        fig.suptitle(f"{res.spec.name} - longitudinal schematic, to scale", fontsize=11, y=0.985)
        fig.text(0.5, 0.962, sub + f" - drawn as {n} z-windows side by side, reading left to right",
                 ha="center", fontsize=8, color="0.3")
        _save(fig, path_png, path_pdf, rect=(0, 0.062, 1, 0.952))
    else:
        # one continuous column is a tall, narrow figure: the title wraps, and the legend goes inside the axes,
        # into the empty corner beside the nose, rather than stealing height from the drawing
        ax.legend(handles=_drawing_key(res), loc="upper right", fontsize=5.4, ncol=1, framealpha=0.95,
                  borderpad=0.4, labelspacing=0.3, handlelength=1.4, handletextpad=0.5,
                  title="drawing key", title_fontsize=5.6)
        fig.text(0.5, 0.988, f"{res.spec.name}", ha="center", va="top", fontsize=9.5)
        fig.text(0.5, 0.967, "longitudinal schematic, one continuous view, to scale",
                 ha="center", va="top", fontsize=7.2, color="0.3")
        fig.text(0.5, 0.951, sub, ha="center", va="top", fontsize=7.2, color="0.3")
        _save(fig, path_png, path_pdf, rect=(0, 0.012, 1, 0.941), tight=True, keep_open=True)
    return fig


def _seg_label(name, idx):
    """Segment names carry the stage number ('Forward skirt 1', 'Interstage 1-2'); drop it for a dimension label."""
    return re.sub(rf"\s+{idx}(-\d+)?$", "", name)


def _stage_on_ax(ax, res, idx, scale=1.0, overall=True, callouts=True, xlim=None):
    """Draw one stage (hardware, per-segment dimensions, tank callouts) onto a single axes."""
    spec, geom = res.spec, res.geometry
    st, sr = spec.stages[idx - 1], res.stages[idx - 1]
    segs = geom.stage_segments(idx)
    zb = geom.engine_exit_z[idx]
    zt = geom.stage_top_z[idx]
    Lh = zt - zb
    D = st.diameter_m
    _draw_segments(ax, segs)
    _draw_engines(ax, res, sr)
    x_len = -1.5 * D / 2
    short = 0.055 * max(Lh, 1e-9)        # labels of short neighbouring segments would print on top of each other
    stagger = 0
    for s in segs:
        lab = f"{_seg_label(s.name, idx)}  {s.length:.2f} m"
        stagger = (stagger + 1) % 2 if s.length < short else 0
        _dim_v(ax, x_len - stagger * 0.42 * D, s.z0, s.z1, lab, body_x=-s.d_bot / 2, fs=FS_DIM * scale)
    if overall:
        _dim_v(ax, -2.15 * D / 2, zb, zt, f"stage incl. nozzle  {Lh:.2f} m", body_x=x_len, fs=7.5 * scale, lw=0.9)
    _dim_h(ax, zt + 0.02 * Lh, -D / 2, D / 2, f"Ø {D:.2f} m", 0.02 * Lh, fs=FS_DIM * scale)
    for s in (segs if callouts else []):
        if s.kind != "tank":
            continue
        g = s.tank
        if getattr(g, "R_bore", 0.0) > 0:
            txt = (f"{g.propellant}\ngrain {g.V_prop:.2f} m3 | {g.m_liquid_loaded:,.0f} kg\n"
                   f"casing {g.V_int:.2f} m3 (x{g.volume_factor:.2f})\nweb {g.web_m:.3f} m, bore R {g.R_bore:.3f} m")
        else:
            txt = (f"{g.propellant}\nV_int {g.V_int:.2f} m3 | {g.m_liquid_loaded:,.0f} kg\n"
                   f"barrel {g.h_cyl:.2f} m, dome h {g.h_dome:.2f} m\nD_int {2*g.R_int:.3f} / D_ext {g.D_ext:.3f} m")
        ax.text(D * 0.62, s.z_mid, txt, ha="left", va="center", fontsize=6.5 * scale, zorder=9,
                bbox=dict(fc="white", ec="0.7", lw=0.5, pad=0.3))
    env = sr.envelope
    if env is not None and callouts:
        ax.text(D * 0.62, zb + 0.4 * env.length_m,
                f"{env.n} x nozzle/engine\nexit Ø {env.exit_diameter_m:.2f} m, L {env.length_m:.2f} m\n({env.source})",
                fontsize=6.5 * scale, va="center", ha="left", bbox=dict(fc="white", ec="0.7", lw=0.5, pad=0.3))
    kind = "SOLID MOTOR" if sr.is_solid else f"{st.oxidizer}/{st.fuel}, O/F {st.of_ratio:.2f}"
    info = (f"Stage {idx} ({sr.stage_type}): {kind}\n"
            f"ignition {sr.m_ignition_kg:,.0f} kg | burnout {sr.m_burnout_kg:,.0f} kg | dry {sr.m_dry_kg:,.0f} kg | "
            f"loaded propellant {sr.m_prop_loaded_kg:,.0f} kg\n"
            f"s = {sr.structural_factor_s:.4f} | dv {sr.dv_mps:,.0f} m/s | Isp_eff {sr.isp_eff_s:.1f} s | "
            f"burn {sr.burn_time_s:.0f} s | T/W at ignition {sr.tw_ignition:.2f}")
    ax.set_aspect("equal")
    ax.set_xlim(*(xlim if xlim else (-2.6 * D / 2, 3.4 * D / 2)))
    for t in ax.texts:
        t.set_clip_on(True)
    return info


def draw_stage(res, idx, path_png=None, path_pdf=None):
    """Screen/workbook view: one stage in a single column."""
    geom = res.geometry
    zb, zt = geom.engine_exit_z[idx], geom.stage_top_z[idx]
    Lh = zt - zb
    fig, ax = plt.subplots(figsize=(10, max(6, 1.05 * Lh + 2.5)))
    info = _stage_on_ax(ax, res, idx)
    ax.set_title(info, fontsize=8.5, loc="left")
    ax.set_ylim(zb - 0.05 * Lh, zt + 0.08 * Lh)
    ax.set_xlabel("lateral position [m]", fontsize=8)
    ax.set_ylabel("axial coordinate z [m] (vehicle coordinates)", fontsize=8)
    ax.tick_params(labelsize=7)
    _save(fig, path_png, path_pdf)
    return fig


def draw_stage_page(res, idx, path_png=None, path_pdf=None, page_aspect=0.80, fig_height_in=12.0,
                    max_columns=1):
    """Report view of one stage: one continuous drawing filling the page height, strictly to scale.

    As with the vehicle, `max_columns` > 1 re-enables splitting the stage over side-by-side z-windows, which draws
    it larger but cuts it into pieces."""
    geom = res.geometry
    D = res.spec.stages[idx - 1].diameter_m
    zb, zt = geom.engine_exit_z[idx], geom.stage_top_z[idx]
    Lh = zt - zb
    # the per-tank callout boxes are dropped here (the report prints the same numbers as a table), so the
    # lateral window only has to hold the drawing and its dimensions - which is what lets the stage be drawn big
    x_lo, x_span = -1.35 * D, 2.2 * D
    n = _n_columns(x_span, 1.13 * Lh, page_aspect, max_cols=max(1, int(max_columns)))
    z_lo, z_hi = zb - 0.05 * Lh, zt + 0.08 * Lh
    z_col = (z_hi - z_lo) / n
    overlap = 0.02 * z_col if n > 1 else 0.0
    z_win = z_col + 2 * overlap
    scale = min(1.9, 0.6 + 0.5 * n) if n > 1 else 0.95
    col_h = fig_height_in - (1.5 if n > 1 else 2.45)
    col_w = col_h * x_span / z_win
    fig = plt.figure(figsize=(n * col_w + 1.1, fig_height_in))
    gs = GridSpec(1, n, wspace=0.14, figure=fig)
    info = ""
    for k in range(n):
        ax = fig.add_subplot(gs[0, k])
        info = _stage_on_ax(ax, res, idx, scale=scale, overall=(n == 1), callouts=False,
                            xlim=(x_lo, x_lo + x_span))
        z0 = z_lo + k * z_col - (overlap if k else 0.0)
        z1 = z_lo + (k + 1) * z_col + (overlap if k < n - 1 else 0.0)
        ax.set_ylim(z0, z1)
        if n > 1:
            if k:
                _break_marks(ax, z0 + overlap, "bottom", D)
            if k < n - 1:
                _break_marks(ax, z1 - overlap, "top", D)
            ax.set_title(f"z = {z0:.1f} - {z1:.1f} m", fontsize=8.5)
        ax.tick_params(labelsize=7)
        ax.set_xlabel("lateral [m]", fontsize=7.5)
        ax.set_ylabel("axial coordinate z [m] (vehicle coordinates)" if k == 0 else "", fontsize=8)
    if n > 1:
        fig.suptitle(info, fontsize=8.5, y=0.992, va="top")
        _save(fig, path_png, path_pdf, rect=(0, 0.01, 1, 0.925))
    else:
        # a single continuous column is narrow, so the header is re-wrapped to the figure width instead of
        # running off both edges
        import textwrap
        fig_w_in = fig.get_size_inches()[0]
        width = max(28, int(fig_w_in / 0.049))          # characters that fit at this font size
        head, *rest = info.split("\n")
        lines = [head] + [w for part in rest for w in textwrap.wrap(part, width) or [""]]
        fig.text(0.5, 0.992, lines[0], ha="center", va="top", fontsize=8.2)
        for i, ln in enumerate(lines[1:]):
            fig.text(0.5, 0.973 - 0.0145 * i, ln, ha="center", va="top", fontsize=6.6, color="0.3")
        _save(fig, path_png, path_pdf, rect=(0, 0.01, 1, 0.985 - 0.0145 * len(lines)), tight=True,
              keep_open=True)
    return fig


def draw_mass_distribution(res, path_png=None, path_pdf=None):
    """Centre of mass against vehicle mass, through the flight events.

    This used to carry a second panel scattering every ledger component's mass against its axial station. It was
    dropped: a cloud of forty dots on a log axis says little that the mass ledger table does not say better and
    exactly, and the one thing it was there to show - where the vehicle's mass sits and how it moves - is what
    this panel shows directly. The component data is still in the report, as the mass ledger, and in
    component_positions.csv.
    """
    N = len(res.stages)
    ev = res.mass_properties["events"]
    fig, ax = plt.subplots(figsize=(8.2, 5.4))
    ax.plot([e["mass_kg"] for e in ev], [e["z_cm_m"] for e in ev], "o-", color=GREEN, zorder=3)
    for e in ev:
        ax.annotate(e["event"].split("(")[0].strip()[:26], (e["mass_kg"], e["z_cm_m"]), fontsize=7,
                    xytext=(5, 4), textcoords="offset points")
    # the stage boundaries, so the CM travel can be read against the vehicle rather than in the abstract
    for k in range(1, N):
        z = res.geometry.stage_top_z[k]
        ax.axhline(z, color=RED, ls="-.", lw=0.8, zorder=1)
        # axis-fraction x so the label sits at the left edge whatever the data limits turn out to be
        ax.text(0.012, z, f"top of stage {k}", transform=ax.get_yaxis_transform(), fontsize=6.5,
                color=RED, va="bottom", ha="left")
    ax.set_xscale("log")
    ax.set_xlabel("vehicle mass [kg] (log scale)")
    ax.set_ylabel("centre of mass, z [m] from the stage-1 nozzle exit plane")
    ax.set_title("Centre of mass through the flight events")
    ax.grid(alpha=0.3)
    ax.margins(x=0.12, y=0.10)
    _save(fig, path_png, path_pdf)
    return fig


def _save(fig, png, pdf, rect=(0, 0.012, 1, 1), tight=False, keep_open=False):
    """Write the figure. `tight` crops the surrounding white margin, which matters for the page-shaped drawings:
    the report scales them to the page height, so every millimetre of white border is a millimetre the vehicle
    does not get."""
    import warnings
    with warnings.catch_warnings():           # the data panel holds a legend outside its axes
        warnings.simplefilter("ignore", UserWarning)
        fig.tight_layout(rect=rect)
    kw = dict(bbox_inches="tight", pad_inches=0.03) if tight else {}
    if png:
        fig.savefig(png, dpi=150, **kw)
    if pdf:
        fig.savefig(pdf, **kw)
    if not keep_open:
        plt.close(fig)


# ------------------------------------------------------------------------------ isometric view
ISO_COL = {"core_airframe": "#c7d2de", "nozzle": "#8c8c8c", "booster": "#dcc9b2"}


def _iso_part_colour(name: str) -> str:
    if "nozzle" in name:
        return ISO_COL["nozzle"]
    if name.startswith("booster"):
        return ISO_COL["booster"]
    return ISO_COL["core_airframe"]


def _view_basis(elev_deg: float, azim_deg: float):
    """Orthographic camera basis: (right, up, towards-viewer) unit vectors for an elev/azim view."""
    e, a = math.radians(elev_deg), math.radians(azim_deg)
    view = np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
    right = np.array([-math.sin(a), math.cos(a), 0.0])
    up = np.array([-math.sin(e) * math.cos(a), -math.sin(e) * math.sin(a), math.cos(e)])
    return right, up, view


def project_meshes(meshes, elev_deg: float, azim_deg: float, cull: bool = True):
    """Orthographic projection of triangle meshes to 2-D, far-to-near (painter's algorithm).

    Returns (polygons, normals, part_index) with the triangles already ordered for drawing. Matplotlib's
    own 3-D axes are not used: they fit the whole data CUBE in the frame, and for a body fifteen times
    longer than it is wide most of that cube is empty air, so the vehicle ends up small and the framing
    cannot be controlled. Projecting here makes the framing exact.

    Back faces are dropped first (they are never visible on a closed shell, which every exported part is
    - see cad_export.is_watertight), then the survivors are sorted by depth. Painter's algorithm is
    correct for convex parts and for separated parts like strap-ons; it can mis-order two interpenetrating
    surfaces, which is a drawing artefact only - the exported mesh is unaffected.
    """
    right, up, view = _view_basis(elev_deg, azim_deg)
    polys, normals, parts, depths = [], [], [], []
    for pi, m in enumerate(meshes):
        if not m.faces:
            continue
        verts = np.asarray(m.vertices, dtype=float)
        tris = verts[np.asarray(m.faces, dtype=int)]                        # (n, 3, 3)
        n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
        ln = np.linalg.norm(n, axis=1)
        n = n / np.where(ln[:, None] < 1e-15, 1.0, ln[:, None])
        keep = (n @ view) > 0.0 if cull else np.ones(len(tris), dtype=bool)
        tris, n = tris[keep], n[keep]
        if not len(tris):
            continue
        polys.append(np.stack([tris @ right, tris @ up], axis=-1))          # (n, 3, 2)
        normals.append(n)
        parts.append(np.full(len(tris), pi))
        depths.append(tris.mean(axis=1) @ view)                             # centroid depth
    if not polys:
        return np.empty((0, 3, 2)), np.empty((0, 3)), np.empty(0, dtype=int)
    polys, normals = np.concatenate(polys), np.concatenate(normals)
    parts, depths = np.concatenate(parts), np.concatenate(depths)
    order = np.argsort(depths)                                              # farthest drawn first
    return polys[order], normals[order], parts[order]


def draw_isometric(res, path_png=None, path_pdf=None, facets: int = 48, elev: float = 18.0,
                   azim: float = -58.0, shade: bool = True):
    """Isometric view of the exported 3-D outer mould line (R15).

    This renders exactly the meshes cad_export writes to STL and OBJ, so the picture is a check on the
    export rather than a drawing of its own: if the view looks wrong, the exported solid is wrong.
    Faceting is visible by design - the surfaces of revolution really are polygonal, and
    cad_export.faceted_revolution_volume_m3 says how much volume that costs.
    """
    from matplotlib.collections import PolyCollection
    from . import cad_export as cad

    meshes = cad.vehicle_meshes(res, facets=facets)
    polys, normals, parts = project_meshes(meshes, elev, azim)

    fig = plt.figure(figsize=(4.9, 9.2))
    ax = fig.add_axes([0.02, 0.055, 0.96, 0.86])
    ax.set_aspect("equal")
    ax.set_axis_off()

    # Key light fixed to the camera (over the viewer's left shoulder), so the shading reads the same
    # whatever elev/azim the caller asks for. A light fixed in world axes goes flat at some headings.
    _right, _up, _view = _view_basis(elev, azim)
    light = _view - 0.85 * _right + 0.45 * _up
    light /= np.linalg.norm(light)
    base = np.array([matplotlib.colors.to_rgb(_iso_part_colour(meshes[i].name)) for i in parts])
    if shade:
        lam = 0.38 + 0.72 * np.clip(normals @ light, 0.0, 1.0) ** 0.8       # ambient + diffuse
        base = np.clip(base * lam[:, None], 0.0, 1.0)
    ax.add_collection(PolyCollection(polys, facecolors=base, edgecolors="none", linewidths=0.0))

    xs, ys = polys[..., 0], polys[..., 1]
    mx = 0.04 * (ys.max() - ys.min())
    ax.set_xlim(xs.min() - mx, xs.max() + mx)
    ax.set_ylim(ys.min() - mx, ys.max() + mx)

    geom = res.geometry
    s = cad.mesh_summary(meshes)
    fig.text(0.5, 0.985, f"{res.spec.name} \u2014 outer mould line, isometric view",
             ha="center", va="top", fontsize=10)
    fig.text(0.5, 0.957, f"{s['parts']} parts, {s['triangles']:,} triangles, {facets} facets per "
                         f"revolution; {s['watertight_parts']}/{s['parts']} closed shells",
             ha="center", va="top", fontsize=7.5, color="#555555")
    dims = (f"overall length   {geom.total_length:,.2f} m\n"
            f"max body dia.    {geom.max_diameter:,.2f} m\n"
            f"max span         {geom.max_span_m:,.2f} m\n"
            f"enclosed volume  {s['airframe_volume_m3']:,.1f} m\u00b3\n"
            f"wetted area      {s['airframe_area_m2']:,.1f} m\u00b2")
    fig.text(0.035, 0.90, dims, ha="left", va="top", fontsize=7, family="monospace", color="#333333",
             bbox=dict(fc="white", ec="#cccccc", lw=0.5, boxstyle="round,pad=0.4"))
    fig.text(0.035, 0.058, f"orthographic view, elevation {elev:.0f}\u00b0, azimuth {azim:.0f}\u00b0; "
                           f"z upward from the stage-1 nozzle exit plane",
             ha="left", va="bottom", fontsize=6.5, color="#555555")
    fig.text(0.5, 0.012, FOOTER, ha="center", fontsize=5.6, color="#555555", wrap=True)
    # Saved without tight_layout: the axes are placed by hand above, and tight_layout would move them.
    if path_png:
        fig.savefig(path_png, dpi=150)
    if path_pdf:
        fig.savefig(path_pdf)
    plt.close(fig)
    return fig
