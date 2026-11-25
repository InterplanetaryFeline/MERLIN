"""Result charts that are not drawings: performance curves, uncertainty distributions, staging optima.

Kept apart from schematic_2d, which draws the vehicle. Everything here plots numbers the engine produced; no
value is computed in this module.
"""
from __future__ import annotations
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ACC = "#1f3864"
GREEN = "#117733"
RED = "#aa3333"


def _save(fig, png, pdf, rect=None):
    fig.tight_layout(**({"rect": rect} if rect else {}))
    if png:
        fig.savefig(png, dpi=150)
    if pdf:
        fig.savefig(pdf)
    plt.close(fig)


def draw_performance(curves: dict, path_png=None, path_pdf=None, title=""):
    """Payload vs altitude (one curve per inclination) and payload vs inclination, side by side (book Sec. 3.8)."""
    va, vi = curves.get("vs_altitude"), curves.get("vs_inclination")
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12.5, 5.6), gridspec_kw=dict(width_ratios=[1.45, 1]))
    cmap = plt.get_cmap("viridis")
    if va:
        cs = va["curves"]
        for k, c in enumerate(cs):
            pts = [p for p in c["points"] if p["payload_kg"] is not None]
            if not pts:
                continue
            a1.plot([p["altitude_km"] for p in pts], [p["payload_kg"] for p in pts], "o-", ms=3.5, lw=1.4,
                    color=cmap(k / max(len(cs) - 1, 1) * 0.85), label=f"i = {c['inclination_deg']:.1f}°")
        d = va["design"]
        a1.plot([d["altitude_km"]], [d["payload_kg"]], marker="*", ms=15, color=RED, zorder=5, ls="none",
                label=f"design point ({d['payload_kg']:,.0f} kg)")
        a1.set_xlabel("circular orbit altitude [km]")
        a1.set_ylabel("payload delivered [kg]")
        a1.set_title(f"Payload vs altitude ({va['orbit_type']}, circular)", fontsize=10)
        a1.grid(alpha=0.3)
        a1.legend(fontsize=8)
        a1.set_ylim(bottom=0)
    if vi:
        pts = [p for p in vi["points"] if p["payload_kg"] is not None]
        xs = [p["inclination_deg"] for p in vi["points"]]
        a2.plot([p["inclination_deg"] for p in pts], [p["payload_kg"] for p in pts], "o-", ms=4, lw=1.6, color=ACC)
        a2.plot([vi["design"]["inclination_deg"]], [vi["design"]["payload_kg"]], marker="*", ms=15, color=RED,
                ls="none", zorder=5)
        # the curve runs along the top of the axes, so the callout goes in the empty lower half on a leader
        a2.annotate(f"design point\n{vi['design']['inclination_deg']:.1f}°, "
                    f"{vi['design']['payload_kg']:,.0f} kg",
                    xy=(vi["design"]["inclination_deg"], vi["design"]["payload_kg"]),
                    xytext=(0.33, 0.22), textcoords="axes fraction", fontsize=7.5, color=RED, ha="center",
                    arrowprops=dict(arrowstyle="-", color=RED, lw=0.7, shrinkB=9))
        lat = vi.get("site_latitude_deg")
        if lat is not None and xs and min(xs) < lat:
            # the band a direct ascent cannot reach from this site: shown, not silently cropped
            a2.axvspan(min(xs), lat, color="0.92", zorder=0)
            a2.axvline(lat, color=RED, ls="--", lw=0.9, zorder=1)
            # inside the band and rotated, so it cannot collide with the curve at any payload level
            a2.text(0.5 * (min(xs) + lat), 0.5, f"below the site latitude:\nno direct ascent",
                    transform=a2.get_xaxis_transform(), fontsize=7, color="#8a6d3b", rotation=90,
                    va="center", ha="center")
            a2.set_xlim(min(xs), max(xs))
        a2.set_xlabel("orbital inclination [deg]")
        a2.set_ylabel("payload delivered [kg]")
        a2.set_title(f"Payload vs inclination at {vi['altitude_km']:.0f} km", fontsize=10)
        a2.grid(alpha=0.3)
        a2.set_ylim(bottom=0)
    if title:
        fig.suptitle(title, fontsize=11)
        fig.subplots_adjust(top=0.86)
    _save(fig, path_png, path_pdf)
    return fig


def draw_uncertainty(mc: dict, path_png=None, path_pdf=None, title=""):
    """Monte-Carlo over the MER scatter: the GLOM distribution and what drives it."""
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12.5, 5.2), gridspec_kw=dict(width_ratios=[1.2, 1]))
    g = mc["glom_kg"]
    a1.hist(g, bins=min(40, max(8, len(g) // 12)), color="#9fb6d4", edgecolor="#44618f")
    for q, lab, c in ((mc["p05"], "5 %", "0.35"), (mc["p50"], "median", ACC), (mc["p95"], "95 %", "0.35")):
        a1.axvline(q, color=c, lw=1.4, ls="--")
        a1.text(q, a1.get_ylim()[1] * 0.97, f" {lab}\n {q:,.0f}", fontsize=7.5, va="top", color=c)
    a1.axvline(mc["nominal_glom_kg"], color=RED, lw=1.8)
    a1.text(mc["nominal_glom_kg"], a1.get_ylim()[1] * 0.55, " nominal", fontsize=8, color=RED)
    a1.set_xlabel("gross lift-off mass [kg]")
    a1.set_ylabel(f"samples (n = {len(g)})")
    a1.set_title("GLOM under MER scatter", fontsize=10)
    a1.grid(alpha=0.25, axis="y")
    sens = mc.get("sensitivity") or []
    if sens:
        names = [s["parameter"] for s in sens][::-1]
        vals = [100 * s["d_glom_per_sigma"] for s in sens][::-1]
        a2.barh(names, vals, color=["#c0504d" if v > 0 else "#4f81bd" for v in vals])
        a2.set_xlabel("change in GLOM per 1 sigma of the coefficient [%]")
        a2.set_title("What the spread is made of", fontsize=10)
        a2.grid(alpha=0.25, axis="x")
        a2.tick_params(labelsize=8)
    if title:
        fig.suptitle(title, fontsize=11)
        fig.subplots_adjust(top=0.86)
    _save(fig, path_png, path_pdf)
    return fig


def draw_staging_optimum(opt: dict, path_png=None, path_pdf=None, title=""):
    """GLOM against the first-stage delta-v share, with the numerical and analytical optima marked."""
    sw = opt.get("sweep") or []
    if not sw:
        return None
    fig, ax = plt.subplots(figsize=(8.6, 5.0))
    ax.plot([100 * p["f1"] for p in sw], [p["glom_kg"] for p in sw], "-", lw=1.6, color=ACC, label="GLOM")
    if opt.get("fractions"):
        ax.axvline(100 * opt["fractions"][0], color=GREEN, lw=1.6,
                   label=f"numerical optimum {100*opt['fractions'][0]:.1f} %")
    if opt.get("analytical_fractions"):
        ax.axvline(100 * opt["analytical_fractions"][0], color=RED, ls="--", lw=1.6,
                   label=f"analytical optimum {100*opt['analytical_fractions'][0]:.1f} %")
    ax.set_xlabel("share of the delta-v budget given to stage 1 [%]")
    ax.set_ylabel("gross lift-off mass [kg]")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=9)
    ax.set_title(title or "Staging optimum", fontsize=10)
    _save(fig, path_png, path_pdf)
    return fig


def draw_trajectory(tr, path_png=None, path_pdf=None, title=""):
    """The ascent: what the vehicle did, and what it cost.

    Four panels, because four things decide whether a trajectory is any good: the altitude and speed histories,
    the flight path angle and dynamic pressure (the book's own checklist on p.379), the ground track, and the
    loss budget that the whole integration exists to produce. The histories and the track stop at the first cutoff: a
    coast and a second burn take the better part of an hour and would squash the ascent into the axis. What happens
    after it is said in the line under the title.
    """
    fig, axes = plt.subplots(2, 2, figsize=(12.6, 8.2))
    (a1, a2), (a3, a4) = axes
    n = max(2, sum(1 for x in tr.t_s if x <= tr.burnout_t_s + 1e-6))
    t = tr.t_s[:n]
    end = "first cutoff" if tr.converged else "end of the flight shown"

    a1.plot(t, [h / 1e3 for h in tr.h_m[:n]], color=ACC, lw=1.7, label="altitude")
    a1.set_xlabel("time [s]"); a1.set_ylabel("altitude [km]", color=ACC)
    a1.tick_params(axis="y", labelcolor=ACC); a1.grid(alpha=0.3)
    b1 = a1.twinx()
    b1.plot(t, [v / 1e3 for v in tr.v_mps[:n]], color=RED, lw=1.7, label="speed")
    b1.set_ylabel("speed [km/s]", color=RED); b1.tick_params(axis="y", labelcolor=RED)
    a1.set_title("Altitude and speed" + (" to the first cutoff" if n < len(tr.t_s) - 2 else ""), fontsize=10)

    a2.plot(t, tr.gamma_deg[:n], color=GREEN, lw=1.7)
    a2.set_xlabel("time [s]"); a2.set_ylabel("flight path angle [deg]", color=GREEN)
    a2.tick_params(axis="y", labelcolor=GREEN); a2.grid(alpha=0.3); a2.axhline(0, color="0.7", lw=0.8)
    b2 = a2.twinx()
    b2.plot(t, [q / 1e3 for q in tr.q_Pa[:n]], color="#8a6d1f", lw=1.5)
    b2.set_ylabel("dynamic pressure [kPa]", color="#8a6d1f"); b2.tick_params(axis="y", labelcolor="#8a6d1f")
    b2.plot([tr.max_q_t_s], [tr.max_q_Pa / 1e3], marker="o", ms=6, color="#8a6d1f")
    b2.annotate(f"max-q {tr.max_q_Pa/1e3:.0f} kPa, {tr.max_q_t_s:.0f} s, M {tr.max_q_mach:.1f}",
                (tr.max_q_t_s, tr.max_q_Pa / 1e3), textcoords="offset points", xytext=(10, -14), fontsize=7.5,
                color="#8a6d1f")
    a2.set_title("Flight path angle and dynamic pressure", fontsize=10)

    xs_km = [x / 1e3 for x in tr.x_m[:n]]
    hs_km = [h / 1e3 for h in tr.h_m[:n]]
    a3.plot(xs_km, hs_km, color=ACC, lw=1.7)
    _label_events(a3, tr, xs_km, hs_km)
    a3.set_xlabel("downrange [km]"); a3.set_ylabel("altitude [km]"); a3.grid(alpha=0.3)
    a3.set_title(f"Ground track - {tr.downrange_m/1e3:,.0f} km downrange at the {end}", fontsize=10)

    names = ["gravity", "drag", "propulsion\n(back pressure)", "steering"]
    vals = [tr.gravity_loss_mps, tr.drag_loss_mps, tr.propulsion_loss_mps, tr.steering_loss_mps]
    bars = a4.barh(names[::-1], vals[::-1], color=["#9fb6d4", "#c0a0a0", "#a8c3a8", "#d4c79f"][::-1],
                   edgecolor="#44618f")
    for b, v in zip(bars, vals[::-1]):
        a4.text(v, b.get_y() + b.get_height() / 2, f" {v:,.0f}", va="center", fontsize=8.5)
    a4.set_xlabel("delta-v lost [m/s]")
    a4.set_title(f"Losses to the {end}: {tr.total_loss_mps:,.0f} m/s of a {tr.ideal_dv_mps:,.0f} m/s vacuum ideal",
                 fontsize=10)
    a4.grid(alpha=0.25, axis="x")
    a4.set_xlim(right=1.14 * max(max(vals), 1.0))

    fig.suptitle(title or f"{tr.vehicle_name} - ascent trajectory", fontsize=11.5, y=0.985)
    failed = ("" if tr.converged else "the ascent does not close; closest attempt: " if tr.closest_attempt
              else "the ascent does not close: ")
    fig.text(0.5, 0.946, f"{failed}{end} {tr.burnout_v_mps:,.0f} m/s at {tr.burnout_h_m/1e3:.0f} km, "
                         f"gamma {tr.burnout_gamma_deg:+.1f} deg, t = {tr.burnout_t_s:.0f} s"
                         + (f"; second burn of {tr.second_burn_dv_mps:,.0f} m/s ends at "
                            f"{tr.final_state['t_s'] / 60.0:,.0f} min" if tr.second_burn_dv_mps else "")
                         + (f"; {tr.margin_mps:+,.0f} m/s of margin at the end" if tr.converged and tr.profile else ""),
             ha="center", fontsize=8, color="0.3")
    fig.subplots_adjust(top=0.885)
    _save(fig, path_png, path_pdf)
    return fig


def _label_events(ax, tr, xs_km, hs_km):
    """Mark the flight events on the ground track without the labels fighting each other.

    Two things go wrong if the events are annotated naively. Several of them happen at nearly the same place -
    a stage burns out, is jettisoned, and the fairing goes a couple of seconds later - so their labels land on
    top of one another; and the last one sits exactly on the axis frame, where half the text is outside the
    plot. So events closer together than a few per cent of the plot are merged into one marker with a combined
    label, the labels alternate above and below the track, and a label near the right-hand edge is written to
    the left of its marker. Room is then left around the data so nothing is clipped.
    """
    wanted = [e for e in tr.events
              if any(w in e["name"] for w in ("burnout", "cutoff", "kick", "fairing"))
              and e["t_s"] <= tr.burnout_t_s + 1e-6]
    if not wanted or not xs_km:
        return
    span_x = max(max(xs_km) - min(xs_km), 1e-6)
    span_y = max(max(hs_km) - min(hs_km), 1e-6)

    groups = []                                   # merge events that share a point on this plot
    for e in wanted:
        x, y = _at(tr, e["t_s"], tr.x_m) / 1e3, _at(tr, e["t_s"], tr.h_m) / 1e3
        label = e["name"].replace(" jettison", " jett.").replace("pitch kick", "kick")
        for g in groups:
            if abs(g["x"] - x) < 0.04 * span_x and abs(g["y"] - y) < 0.04 * span_y:
                g["labels"].append(label)
                break
        else:
            groups.append(dict(x=x, y=y, labels=[label]))

    ax.margins(x=0.16, y=0.16)                    # headroom so no label is written onto the frame
    for i, g in enumerate(groups):
        ax.plot([g["x"]], [g["y"]], marker="o", ms=4.5, color=RED, zorder=5)
        right = g["x"] > min(xs_km) + 0.62 * span_x
        up = i % 2 == 0
        ax.annotate(" + ".join(g["labels"]), (g["x"], g["y"]), textcoords="offset points",
                    xytext=(-7 if right else 7, 7 if up else -11),
                    ha="right" if right else "left", va="bottom" if up else "top",
                    fontsize=6.6, color="0.25",
                    bbox=dict(fc="white", ec="none", alpha=0.75, pad=0.8))


def _at(tr, t_s, series):
    """The value of a recorded series at a given time (nearest sample) - for marking events on a plot."""
    if not tr.t_s:
        return 0.0
    i = min(range(len(tr.t_s)), key=lambda k: abs(tr.t_s[k] - t_s))
    return series[i]


def _strip_half_width(res):
    """Half the width of vehicle to show: its widest point, boosters included, with a little air."""
    return 1.1 * 0.5 * max(res.geometry.max_span_m, res.geometry.max_diameter)


def vehicle_strip(ax, res, z_lo=None, z_hi=None):
    """Draw the inboard profile upright on `ax`, to scale, sharing the caller's z axis.

    Used beside the loads and structure diagrams so a curve can be read against the hardware that carries it,
    which is how the book presents its own load distributions (Fig. 9.26 plots shear and moment against
    elevation, with the vehicle's stations named). Reuses the schematic module's segment drawing, so the strip
    is the same picture as the general arrangement rather than a second, possibly disagreeing, outline.
    """
    from . import schematic_2d as s2
    geom = res.geometry
    s2._draw_segments(ax, geom.segments, 0.0)
    for sr in res.stages:
        if sr.envelope is not None:
            s2._draw_engines(ax, res, sr, 0.0)
    if geom.booster_segments and res.spec.boosters is not None:
        s2._draw_boosters(ax, res)
    half = _strip_half_width(res)
    ax.set_xlim(-half, half)
    ax.set_ylim(z_lo if z_lo is not None else -0.01 * geom.total_length,
                z_hi if z_hi is not None else 1.01 * geom.total_length)
    ax.set_xticks([])
    ax.set_ylabel("z from the stage-1 nozzle exit plane [m]", fontsize=9)
    ax.tick_params(labelsize=8)
    for side in ("top", "right", "bottom"):
        ax.spines[side].set_visible(False)
    return ax


def _stage_joints(res):
    """z of the joints worth drawing across a load diagram: stage tops and the fairing base."""
    geom = res.geometry
    out = [(geom.stage_top_z[k], f"stage {k}/{k + 1}") for k in sorted(geom.stage_top_z)[:-1]]
    out.append((geom.fairing_base_z, "fairing base"))
    return [(z, lab) for z, lab in out if 0.0 < z < geom.total_length]


def draw_loads(cases: dict, path_png=None, path_pdf=None, title="", res=None):
    """Axial force, shear and bending moment along the vehicle, with the vehicle drawn beside them.

    Plotted against z upward from the first-stage nozzle exit plane - the same axis as the drawings, the mass
    ledger, the stability plot and the CAD export. The book's own load figures use elevation from the base too
    (Fig. 9.26); an earlier version of this chart used distance from the nose, which put the one diagram you
    most want to read against the vehicle on the opposite convention to the vehicle.

    Pass `res` to get the inboard profile in the left-hand column. Without it the three panels are drawn alone,
    which is all the data needs but much harder to interpret.
    """
    cs = [(k, c) for k, c in cases.items() if hasattr(c, "stations") and c.stations]
    if not cs:
        return None
    colours = {"ground_wind": ACC, "liftoff": "#6a7fb5", "max_q": RED, "max_q_alpha": GREEN,
               "max_axial": "#b07d1a"}
    n_panels = 3
    if res is not None:
        # The strip is given the width the vehicle needs at the height of the panels, so that one metre across is
        # one metre up. At a fixed width a slender vehicle was drawn several times too fat. It always keeps
        # room for the joint names to the right of the vehicle, where they are written.
        w_in, h_in, left, right, top, bottom = 12.6, 10.5, 0.075, 0.985, 0.945, 0.105
        gap_in = 0.2
        z_span = 1.02 * res.geometry.total_length
        m_per_in = z_span / (h_in * (top - bottom))
        strip_in = min(max(2.0 * _strip_half_width(res) / m_per_in + 0.8, 1.6), 5.0)
        panel_in = (w_in * (right - left) - strip_in - n_panels * gap_in) / n_panels
        fig, axs = plt.subplots(1, n_panels + 1, figsize=(w_in, h_in), sharey=True,
                                gridspec_kw=dict(width_ratios=[strip_in] + [panel_in] * n_panels,
                                                 wspace=gap_in / ((strip_in + n_panels * panel_in) / (n_panels + 1))))
        vehicle_strip(axs[0], res)
        axs[0].set_xlim(-_strip_half_width(res), -_strip_half_width(res) + strip_in * m_per_in)
        axes = list(axs[1:])
    else:
        fig, axs = plt.subplots(1, n_panels, figsize=(11.0, 8.0), sharey=True,
                                gridspec_kw=dict(wspace=0.12))
        axes = list(axs)
        axes[0].set_ylabel("z from the stage-1 nozzle exit plane [m]", fontsize=9)

    for key, case in cs:
        col = colours.get(key, "#666666")
        # a staircase: at each station the value just below the cut, then the value just above it
        zs, ax_, sh_ = [], [], []
        for st in case.stations:
            zs += [st.z_m, st.z_m]
            ax_ += [st.axial_below_N / 1e3, st.axial_above_N / 1e3]
            sh_ += [st.shear_below_N / 1e3, st.shear_above_N / 1e3]
        axes[0].plot(ax_, zs, "-", lw=1.5, color=col, label=case.name)
        axes[1].plot(sh_, zs, "-", lw=1.5, color=col, label=case.name)
        axes[2].plot([st.moment_Nm / 1e3 for st in case.stations], [st.z_m for st in case.stations],
                     "-", lw=1.5, color=col, label=case.name)

    joints = _stage_joints(res) if res is not None else []
    for ax, lab in zip(axes, ("axial force [kN], compression positive", "shear force [kN]",
                              "bending moment [kN\u00b7m]")):
        ax.set_xlabel(lab, fontsize=9)
        ax.grid(alpha=0.3)
        ax.axvline(0.0, color="#999999", lw=0.8)
        ax.tick_params(labelsize=8)
        for z, _name in joints:
            ax.axhline(z, color="#b0b6bd", ls="--", lw=0.8, zorder=0)

    # name the joints on the vehicle strip, where they belong to the hardware rather than to a curve
    if res is not None:
        for z, name in joints:
            axs[0].annotate(name, xy=(1.0, z), xycoords=("axes fraction", "data"), fontsize=6.8,
                            color="#6b7480", ha="right", va="bottom", xytext=(-1, 1),
                            textcoords="offset points")

    # the station that sizes the structure, marked where a reader looks for it
    worst = max(cs, key=lambda kc: max(abs(st.moment_Nm) for st in kc[1].stations))
    wst = max(worst[1].stations, key=lambda st: abs(st.moment_Nm))
    axes[2].plot([wst.moment_Nm / 1e3], [wst.z_m], "o", ms=7, mfc="none", mec="#111111", mew=1.3, zorder=6)
    import textwrap
    name = "\n".join(textwrap.wrap(worst[1].name, 30)[:2])
    axes[2].annotate(f"governing bending moment\n{wst.moment_Nm / 1e3:,.0f} kN\u00b7m at z = {wst.z_m:.1f} m\n"
                     f"{name}",
                     xy=(wst.moment_Nm / 1e3, wst.z_m), xytext=(0.97, 0.56), textcoords="axes fraction",
                     fontsize=7.5, color="#111111", ha="right", va="top",
                     arrowprops=dict(arrowstyle="-", color="#777777", lw=0.7, shrinkB=8),
                     bbox=dict(fc="white", ec="#cccccc", lw=0.5, boxstyle="round,pad=0.35", alpha=0.95))

    # one shared legend under the panels: inside any one of them it covers the data it labels
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=min(3, len(labels)), fontsize=8,
               frameon=False, bbox_to_anchor=(0.5, 0.004))
    fig.suptitle(title or "Ground and flight loads", fontsize=11, y=0.977)
    # Placed by hand rather than by tight_layout: the vehicle strip shares its y axis with the panels but
    # carries no x axis of its own, which tight_layout cannot size and warns about. Explicit margins also
    # keep the strip the same width whatever the longest tick label in the panels turns out to be.
    if res is not None:
        fig.subplots_adjust(left=left, right=right, top=top, bottom=bottom)
    else:
        fig.subplots_adjust(left=0.075, right=0.985, top=0.945, bottom=0.115)
    if path_png:
        fig.savefig(path_png, dpi=150)
    if path_pdf:
        fig.savefig(path_pdf)
    plt.close(fig)
    return fig


def draw_stability(cp: dict, path_png=None, path_pdf=None, title="", control=None):
    """Centre of pressure against centre of mass through the atmospheric ascent, and the static margin.

    Plotted against z upward from the first-stage nozzle exit plane - the same axis as the drawings, the mass
    ledger, the loads diagram and the CAD export - so the nose sits at the top without inverting anything.
    """
    rows = cp.get("rows") or []
    if not rows:
        return None
    t = [r["t_s"] for r in rows]
    n = 3 if (control and control.points) else 2
    fig, axes = plt.subplots(n, 1, figsize=(8.6, 3.3 * n), sharex=True)
    axes[0].plot(t, [r["z_cp_m"] for r in rows], "-", lw=1.6, color=RED, label="centre of pressure")
    axes[0].plot(t, [r["z_cm_m"] for r in rows], "-", lw=1.6, color=ACC, label="centre of mass")
    axes[0].fill_between(t, [r["z_cp_m"] for r in rows], [r["z_cm_m"] for r in rows],
                         color="#aa3333", alpha=0.10)
    axes[0].set_ylabel("z from the stage-1 nozzle exit plane [m]", fontsize=9)
    axes[0].legend(fontsize=8)
    axes[0].grid(alpha=0.3)
    sm = [r["static_margin_cal"] for r in rows]
    axes[1].plot(t, sm, "-", lw=1.6, color=GREEN)
    axes[1].axhline(0.0, color="#999999", lw=1.0)
    axes[1].set_ylabel("static margin [calibers]", fontsize=9)
    axes[1].grid(alpha=0.3)
    if n == 2:
        axes[1].set_xlabel("time from lift-off [s]")
    if max(sm) < 0:
        axes[1].annotate("below zero: statically unstable,\nflown entirely on thrust vector control",
                         xy=(0.02, 0.08), xycoords="axes fraction", fontsize=8, color="#555555")
    if n == 3:
        pts = control.points
        ct = [p.t_s for p in pts]
        ax = axes[2]
        ax.plot(ct, [min(p.controllability, 50) for p in pts], "-", lw=1.6, color=ACC,
                label="controllability M$_\\delta$/M$_A$ (capped at 50)")
        ax.axhline(2.0, color=ACC, ls="--", lw=1.0)
        ax.set_ylabel("controllability ratio", fontsize=9, color=ACC)
        ax.set_yscale("log")
        axr = ax.twinx()
        axr.plot(ct, [p.trim_deg for p in pts], "-", lw=1.6, color=RED, label="trim deflection")
        axr.axhline(2.0, color=RED, ls=":", lw=1.0)
        axr.set_ylabel("steady-state gimbal angle [deg]  (dotted = 2 deg rule)", fontsize=9, color=RED)
        ax.set_xlabel("time from lift-off [s]")
        ax.grid(alpha=0.3, which="both")
        ax.legend(fontsize=8, loc="upper left")
    axes[0].set_title(title or "Static stability through the atmospheric ascent", fontsize=10)
    _save(fig, path_png, path_pdf)
    return fig


def draw_ascent_optimum(opt: dict, path_png=None, path_pdf=None, title=""):
    """The book's Fig. 6.26 trade as numbers: what steering over earlier costs and buys.

    Top: the loss budget against the altitude at which the vehicle stops flying a pure gravity turn. Bottom:
    the two things that stop it going further, with their limits drawn.
    """
    sw = opt.get("sweep") or []
    if not sw:
        return None
    x = [p["handover_h_m"] / 1e3 for p in sw]
    fig, axes = plt.subplots(2, 1, figsize=(8.6, 7.2), sharex=True)
    # gravity and the total are hundreds of m/s; steering and drag are tens. On one linear axis the small
    # ones vanish and on a log axis the large ones do, and the whole point of the figure is that they move
    # against each other - so they get an axis each.
    axL = axes[0]
    axR = axL.twinx()
    for key, lab, col in (("gravity_loss_mps", "gravity loss", ACC), ("total_loss_mps", "total losses", "#222222")):
        axL.plot(x, [p[key] for p in sw], "-o", ms=3, lw=1.6, color=col, label=lab)
    for key, lab, col in (("steering_loss_mps", "steering loss", RED), ("drag_loss_mps", "drag loss", GREEN)):
        axR.plot(x, [p[key] for p in sw], "--s", ms=3, lw=1.4, color=col, label=lab)
    axL.set_ylabel("gravity and total loss [m/s]", fontsize=9)
    axR.set_ylabel("steering and drag loss [m/s]  (dashed)", fontsize=9)
    h1, l1 = axL.get_legend_handles_labels()
    h2, l2 = axR.get_legend_handles_labels()
    axL.legend(h1 + h2, l1 + l2, fontsize=8, ncol=2, loc="center right")
    axL.grid(alpha=0.3)
    lim = opt.get("limits") or {}
    ax2 = axes[1]
    ax2.plot(x, [p["max_q_Pa"] / 1e3 for p in sw], "-o", ms=3, lw=1.5, color=ACC, label="max-q [kPa]")
    if lim.get("max_q_Pa"):
        ax2.axhline(lim["max_q_Pa"] / 1e3, color=ACC, ls="--", lw=1.0, label="max-q limit")
    ax3 = ax2.twinx()
    ax3.plot(x, [p["max_q_alpha_Pa_deg"] / 1e3 for p in sw], "-s", ms=3, lw=1.5, color=RED,
             label="max q$\\alpha$ [kPa deg]")
    if lim.get("max_q_alpha_Pa_deg"):
        ax3.axhline(lim["max_q_alpha_Pa_deg"] / 1e3, color=RED, ls="--", lw=1.0)
    ax2.set_ylabel("dynamic pressure [kPa]", fontsize=9, color=ACC)
    ax3.set_ylabel("q$\\alpha$ [kPa deg]  (dashed = limit)", fontsize=9, color=RED)
    ax2.set_xlabel("altitude at which the gravity turn hands over to linear tangent steering [km]")
    ax2.grid(alpha=0.3)
    best = opt.get("best")
    if best:
        for ax in (axes[0], ax2):
            ax.axvline(best["handover_h_m"] / 1e3, color="#b07d1a", lw=1.4)
        axes[0].annotate("optimum", xy=(best["handover_h_m"] / 1e3, 0.9), xycoords=("data", "axes fraction"),
                         fontsize=8, color="#b07d1a", ha="left")
    axes[0].set_title(title or "Ascent pitch-programme trade", fontsize=10)
    _save(fig, path_png, path_pdf)
    return fig


def draw_structure(out: dict, geom, path_png=None, path_pdf=None, title=""):
    """Required wall thickness along the vehicle, and the mass that implies against the mass model's."""
    shells = out.get("shells") or []
    if not shells:
        return None
    by_name = {s.name: s for s in geom.segments}
    fig, axes = plt.subplots(2, 1, figsize=(8.6, 7.6))
    cols = {"buckling": RED, "hoop": ACC, "axial": GREEN, "minimum gauge": "#999999"}
    seen = set()
    ax = axes[0]
    for s in shells:
        seg = by_name.get(s.name)
        if seg is None:
            continue
        x0, x1 = seg.z0, seg.z1
        c = cols.get(s.governing_driver, "#666666")
        lab = s.governing_driver if s.governing_driver not in seen else None
        seen.add(s.governing_driver)
        ax.fill_between([x0, x1], [0, 0], [s.t_required_m * 1e3] * 2, color=c, alpha=0.55, label=lab,
                        linewidth=0.6, edgecolor="white")
        ax.plot([x0, x1], [s.t_installed_m * 1e3] * 2, "--", lw=1.2, color="#222222")
    ax.axhline(out["material"].t_min_m * 1e3, color="#999999", lw=1.0, ls=":")
    ax.annotate("minimum gauge", xy=(0.01, out["material"].t_min_m * 1e3), xycoords=("axes fraction", "data"),
                fontsize=7, color="#666666", va="bottom")
    ax.plot([], [], "--", lw=1.2, color="#222222", label="thickness assumed in the design")
    ax.set_xlabel("z from the stage-1 nozzle exit plane [m]")
    ax.set_ylabel("wall thickness [mm]", fontsize=9)
    ax.legend(fontsize=8, ncol=3)
    ax.grid(alpha=0.3)
    ax.set_title(title or "Required shell thickness and what it weighs", fontsize=10)

    ax2 = axes[1]
    paired = [s for s in shells if s.mass_model_kg > 0]
    idx = range(len(paired))
    ax2.bar([i - 0.2 for i in idx], [s.mass_sized_kg for s in paired], width=0.4, color=RED,
            label="sized monocoque (Chapter 10)")
    ax2.bar([i + 0.2 for i in idx], [s.mass_model_kg for s in paired], width=0.4, color=ACC,
            label="mass relationship (Chapter 8)")
    ax2.set_xticks(list(idx))
    ax2.set_xticklabels([s.name for s in paired], rotation=35, ha="right", fontsize=7)
    ax2.set_ylabel("shell mass [kg]", fontsize=9)
    ax2.legend(fontsize=8)
    ax2.grid(alpha=0.3, axis="y")
    _save(fig, path_png, path_pdf)
    return fig


def draw_internal_ballistics(profiles: list, path_png=None, path_pdf=None, title=""):
    """Thrust and chamber pressure through the burn, against the constant values the stage was sized on."""
    live = [p for p in profiles if p.get("ok")]
    if not live:
        return None
    fig, axes = plt.subplots(2, 1, figsize=(8.6, 6.8), sharex=False)
    for p in live:
        t = [pt["t_s"] for pt in p["points"]]
        lab = f"stage {p['stage']}" if p.get("stage") else p.get("grain", "")
        axes[0].plot(t, [pt["thrust_N"] / 1e3 for pt in p["points"]], "-", lw=1.6, label=lab)
        axes[0].plot([0, p["burn_time_s"]], [p["design_thrust_N"] / 1e3] * 2, "--", lw=1.1, color="#666666")
        axes[1].plot(t, [pt["pc_Pa"] / 1e6 for pt in p["points"]], "-", lw=1.6, label=lab)
        axes[1].plot([0, p["burn_time_s"]], [p["pc_design_Pa"] / 1e6] * 2, "--", lw=1.1, color="#666666")
    axes[0].plot([], [], "--", lw=1.1, color="#666666", label="constant value the sizing assumed")
    axes[0].set_ylabel("thrust [kN]", fontsize=9)
    axes[1].set_ylabel("chamber pressure [MPa]", fontsize=9)
    axes[1].set_xlabel("time from ignition [s]")
    for ax in axes:
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    axes[0].set_title(title or "Solid motor internal ballistics", fontsize=10)
    _save(fig, path_png, path_pdf)
    return fig


def draw_study(study: dict, path_png=None, path_pdf=None, title="", y="glom_kg", x=None):
    """A trade study or comparison as a chart: the swept parameter against an output, or a bar per design."""
    ok = [c for c in study.get("cases", []) if c.ok]
    if not ok:
        return None
    lab = {"glom_kg": "GLOM [kg]", "length_m": "length [m]", "payload_fraction": "payload fraction [-]",
           "dv_achieved_mps": "delta-v achieved [m/s]", "dry_mass_kg": "dry mass [kg]"}.get(y, y)
    fig, ax = plt.subplots(figsize=(8.6, 5.0))
    params = []
    for c in ok:
        for k in c.parameters:
            if k not in params and k != "baseline":
                params.append(k)
    if study.get("kind") == "trade_study" and params:
        xk = x or params[0]
        series = params[1] if len(params) > 1 else None
        groups = {}
        for c in ok:
            groups.setdefault(c.parameters.get(series) if series else None, []).append(c)
        palette = [ACC, RED, GREEN, "#b07d1a", "#6a7fb5", "#7733aa"]
        for i, (key, cs) in enumerate(sorted(groups.items(), key=lambda kv: (kv[0] is None, kv[0]))):
            cs = sorted(cs, key=lambda c: c.parameters.get(xk, 0))
            ax.plot([c.parameters.get(xk) for c in cs], [c.outputs[y] for c in cs], "-o", ms=4, lw=1.6,
                    color=palette[i % len(palette)],
                    label=(f"{series.split('.')[-1]} = {key}" if series else None))
        ax.set_xlabel(xk.split(".")[-1])
        if series:
            ax.legend(fontsize=8)
    else:
        ax.bar(range(len(ok)), [c.outputs[y] for c in ok], color=ACC)
        ax.set_xticks(range(len(ok)))
        ax.set_xticklabels([c.label for c in ok], rotation=30, ha="right", fontsize=8)
    failed = [c for c in study.get("cases", []) if not c.ok]
    if failed:
        ax.annotate(f"{len(failed)} case(s) did not converge or violated a constraint and are not plotted",
                    xy=(0.01, 0.02), xycoords="axes fraction", fontsize=8, color="#aa3333")
    ax.set_ylabel(lab, fontsize=9)
    ax.grid(alpha=0.3)
    ax.set_title(title or study.get("name", "Study"), fontsize=10)
    _save(fig, path_png, path_pdf)
    return fig


def draw_wind_profiles(profiles, path_png=None, path_pdf=None, title="", traj=None):
    """The winds-aloft profiles the flight load cases were built from, against the book's own envelope.

    Drawn with altitude on the vertical axis, the way a sounding is read. The book's AMR 95 % curve is always
    shown, in grey, even when the design flies its own data: it is the yardstick every number in Chapter 9 was
    calibrated against, and a site profile that sits far outside it is worth seeing rather than discovering
    later in a bending moment.
    """
    from . import wind as wind_mod
    profiles = list(profiles or [])
    if not profiles:
        return None
    fig, ax = plt.subplots(figsize=(6.4, 7.2))
    book = wind_mod.book_profile()
    hs = [h * 100.0 for h in range(0, 301)]
    ax.plot([book.gust_at(h) for h in hs], [h / 1e3 for h in hs], "-", lw=1.4, color="#9aa4b1",
            label=f"{book.name} (book Fig. 9.35)", zorder=2)
    cmap = plt.get_cmap("viridis")
    for k, p in enumerate(profiles):
        if p.name == book.name:
            continue
        col = cmap(k / max(len(profiles) - 1, 1) * 0.8)
        ax.plot([p.gust_at(h) for h in hs], [h / 1e3 for h in hs], "-", lw=1.7, color=col, zorder=3,
                label=f"{p.name} ({p.kind})")
        if p.kind == "steady":                      # show what the gust increment adds, as a dotted twin
            ax.plot([p.steady_at(h) for h in hs], [h / 1e3 for h in hs], ":", lw=1.1, color=col, zorder=3)
        ax.plot([p.peak_mps], [p.peak_altitude_m / 1e3], "o", ms=5, color=col, zorder=4)
        ax.axhspan(p.top_m / 1e3, max(hs) / 1e3, color="0.95", zorder=0)
    tops = [p.top_m for p in profiles if p.name != book.name]
    if tops and min(tops) < max(hs):
        ax.text(0.98, min(tops) / 1e3, " data ends; held flat above", transform=ax.get_yaxis_transform(),
                fontsize=7, color="#8a6d3b", va="bottom", ha="right")
    if traj is not None and getattr(traj, "h_m", None):
        ax.axhline(max(traj.h_m) / 1e3, color=GREEN, ls="-.", lw=0.8, zorder=1)
    ax.set_xlabel("horizontal gust speed used by the load case [m/s]")
    ax.set_ylabel("altitude above the ground [km]")
    ax.set_ylim(0, max(hs) / 1e3)
    ax.set_xlim(left=0)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="upper right")
    ax.set_title(title or "Winds aloft", fontsize=10)
    _save(fig, path_png, path_pdf)
    return fig
