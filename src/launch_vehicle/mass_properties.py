"""Hierarchical mass ledger, axial centre of mass and moments of inertia at flight events.

Coordinate convention: z upward from the first-stage nozzle exit plane (see geometry.py).
Locations are preliminary lumped-mass assumptions (stated per item in the ledger 'source' column):
  tank / casing / skirt / intertank / interstage structure : shell CM of its own surface of revolution
  engines: mid-length of the engine envelope; gimbals, thrust structure, feed system: mid aft skirt
  avionics, pressurant: mid forward skirt; wiring, other equipment: mid stage; separation hardware: top of stage
  mass-growth margin: centroid of the stage's other dry components
  liquid propellant: centroid of the liquid column filling each tank from the bottom (tank profile integration)
  solid propellant: centroid of the cast grain (annulus through the barrel, filled domes; book p.490 states the
    loaded SRM CM is at the centre of the propellant mass)
  strap-on boosters: own axis at radius rho from the vehicle centreline; the ring of n boosters is treated as
    axisymmetric (J_pitch gets m rho^2/2 per the ring average), as is done for a ring of engines.
Moments of inertia use the shapes of Tables 8.10/8.16/8.17 and the parallel-axis theorem (Eq. 8:37).
"""
from __future__ import annotations
import math
from dataclasses import dataclass
import numpy as np
from . import inertia as inr
from . import propulsion as prop


@dataclass
class MassItem:
    name: str
    stage: int            # 0 payload/PAF, -1 fairing, -2 boosters, j>=1 stage
    group: str
    mass_kg: float
    z_m: float
    source: str
    kind: str             # dry | prop_loaded | prop_resid | payload | paf | fairing | booster_dry | booster_prop
    J0_roll: float = 0.0      # about the item's own CM, roll axis [kg m^2]
    J0_pitch: float = 0.0     # about the item's own CM, transverse axis [kg m^2]
    ext_roll: float = 0.0     # m*rho^2 of off-axis sub-items (engine ring, booster ring) added to roll
    ext_pitch: float = 0.0    # m*rho^2/2 (ring average) added to pitch/yaw
    shape: str = "point"      # shape model used for J0 (documented in the ledger)


def _tank_z_internal_bottom(seg) -> float:
    g = seg.tank
    return seg.z0 + (0.0 if g.bulkhead == "upper_user" else g.t_wall)


def _frustum_zc(h, r_bot, r_top):
    """CM height above the base of a thin conical frustum shell (Table 8.10: h/3 (2r+R)/(r+R)); verified by book Example 4 (1.90 m)."""
    return h * (r_bot + 2 * r_top) / (3.0 * (r_bot + r_top)) if (r_bot + r_top) > 0 else h / 2


def _liquid_inertia(g, V, m):
    """Centroid and inertia of a liquid column of volume V holding mass m (zero volume is a valid input:
    a stage may carry no residual propellant at all)."""
    if V <= 0.0 or m <= 0.0:
        return 0.0, 0.0, 0.0
    zz, A = g.liquid_arrays(V)
    mm, zc, jr, jp = inr.solid_of_revolution(m / V, zz, A)
    return zc, jr, jp


def _grain_inertia(g, V_remaining, m):
    """Grain CM and inertia for a centre-perforated grain holding volume V_remaining (bore scaled to match)."""
    if V_remaining <= 0 or m <= 0:
        return 0.0, 0.0, 0.0
    from .solid_motor import grain_volume
    z = np.linspace(0.0, g.L_int, 4000)
    A_full = g.area_profile(z)
    hd, hc = g.h_dome, g.h_cyl
    in_barrel = (z >= hd) & (z <= hd + hc)
    # bore radius that leaves exactly V_remaining of grain (same geometry rule as the initial sizing)
    if g.bore_full_length:
        lo, hi = 0.0, 0.99 * g.R_int
        for _ in range(80):
            mid = 0.5 * (lo + hi)
            if grain_volume(g.R_int, hd, hc, mid, True) > V_remaining:
                lo = mid
            else:
                hi = mid
        r_bore = 0.5 * (lo + hi)
    else:
        V_free = max(g.V_int - V_remaining, 0.0)
        r_bore = min(math.sqrt(V_free / (math.pi * hc)) if hc > 0 else 0.0, 0.999 * g.R_int)
    A = np.maximum(A_full - math.pi * r_bore ** 2, 0.0) if g.bore_full_length else \
        np.where(in_barrel, np.maximum(A_full - math.pi * r_bore ** 2, 0.0), A_full)
    vol = float(np.trapezoid(A, z))
    _, zc, jr, jp = inr.solid_of_revolution(m / max(vol, 1e-12), z, A)
    return zc, jr, jp


def build_ledger(res) -> list:
    spec, geom = res.spec, res.geometry
    items = []

    def add(name, stage, group, m, z, src, kind, shape="point", J=(0.0, 0.0), ext=(0.0, 0.0)):
        items.append(MassItem(name, stage, group, m, z, src, kind, J[0], J[1], ext[0], ext[1], shape))

    for sr in res.stages:
        st = spec.stages[sr.index - 1]
        segs = geom.stage_segments(sr.index)
        by = {}
        for sg in segs:
            by.setdefault(sg.kind, []).append(sg)
        z_base, z_top = geom.stage_base_z[sr.index], geom.stage_top_z[sr.index]
        aft, fwd = by["aft_skirt"][0], by["fwd_skirt"][0]
        R = st.diameter_m / 2
        env = sr.envelope
        eng_z = geom.engine_exit_z[sr.index] + (env.length_m if env else 0.0) / 2.0
        n_e = 1 if st.is_solid else st.engine.n_engines
        rho_e = prop.engine_ring_radius(n_e, env.exit_diameter_m if env else 0.0)
        ring_ext = lambda m: (m * rho_e ** 2, m * rho_e ** 2 / 2) if n_e > 1 else (0.0, 0.0)
        tank_by_role = {x.tank.role: x for x in by.get("tank", [])}
        if st.structure_mode == "aggregate_s":
            L = z_top - z_base
            add("Aggregate dry mass (smeared over stage)", sr.index, "Aggregate", sr.m_dry_kg, 0.5 * (z_base + z_top),
                "Eq. 5:90a aggregate inert mass minus residual/margin; smeared as thin cylinder", "dry", "thin cylinder (smeared)", inr.cyl_shell(sr.m_dry_kg, R, L))
        else:
            tmp = []
            for name, m in sr.components.items():
                if name == "Mass growth margin":
                    continue
                J, ext, shape, grp = (0.0, 0.0), (0.0, 0.0), "point (on axis)", "Systems"
                if name == "Engines":
                    z, src, grp, ext, shape = eng_z, "Table 8.9 MER; mid-length of engine envelope", "Propulsion", ring_ext(m), "point masses on engine ring (Table 8.15: point mass)"
                elif name == "Engine gimbals":
                    z, src, grp, ext, shape = aft.z_mid, "MER; aft skirt mid", "Propulsion", ring_ext(m), "point masses on engine ring"
                elif name == "Thrust structure":
                    z, src, grp = aft.z_mid, "MER; aft skirt mid", "Propulsion"
                    J, shape = inr.cyl_shell(m, 0.5 * R, 0.5 * st.diameter_m), "thin cylinder r=R/2, h=D/2 (assumed)"
                elif name == "Feed system":
                    z, src, grp = aft.z_mid, "assumption; aft skirt mid", "Propulsion"
                elif name.startswith("Motor casing"):
                    sg = tank_by_role["grain"]
                    g = sg.tank
                    zo, jr, jp = inr.shell_of_revolution(m, *inr.tank_outline(g.D_ext / 2, g.h_dome + g.t_wall, g.h_cyl))
                    z, src, grp = sg.z0 + zo, "Eq. 8:18 casing MER (includes insulation, nozzle, thrust structure, TVC); shell CM from outline integration", "Propulsion"
                    J, shape = (jr, jp), "thin shell of revolution (numerical)"
                elif name.startswith("Tank structure") or name.startswith("Tank insulation"):
                    role = name.split("(")[1].rstrip(")")
                    sg = tank_by_role[role]
                    g = sg.tank
                    zo, jr, jp = inr.shell_of_revolution(m, *inr.tank_outline(g.D_ext / 2, g.h_dome + g.t_wall, g.h_cyl))
                    z, src, grp = sg.z0 + zo if g.bulkhead == "none" else sg.z_mid, "tank method per tank spec; shell CM from outline integration", "Tanks"
                    J, shape = (jr, jp), "thin shell of revolution (numerical)"
                elif name in ("Aft skirt", "Intertank", "Forward skirt"):
                    sg = {"Aft skirt": aft, "Intertank": by.get("intertank", [None])[0], "Forward skirt": fwd}[name]
                    z, src, grp = sg.z_mid, "13.3 kg/m^2 x area (Table 8.8); thin cylinder (Table 8.10)", "Structure"
                    J, shape = inr.cyl_shell(m, R, sg.length), "thin cylinder (Table 8.10)"
                elif name in ("Interstage", "Forward adapter cone"):
                    sg = by["interstage" if name == "Interstage" else "fwd_adapter"][0]
                    z = sg.z0 + _frustum_zc(sg.length, sg.d_bot / 2, sg.d_top / 2)
                    src, grp = "13.3 kg/m^2 x frustum area (Table 8.8); CM per Table 8.10", "Structure"
                    J, shape = inr.frustum_shell(m, sg.d_top / 2, sg.d_bot / 2, sg.length), "thin frustum (Table 8.10)"
                elif name == "Avionics":
                    z, src, J, shape = fwd.z_mid, "MER/assumption; forward skirt mid", inr.ring(m, R), "thin ring (Table 8.15/8.16)"
                elif name == "Wiring":
                    z, src, J, shape = 0.5 * (z_base + z_top), "1.43 kg/m; mid-stage (Table 8.15: 1/2 l)", inr.thin_bar(m, z_top - z_base), "thin bar along stage (Table 8.17)"
                elif name == "Pressurant system":
                    z, src = fwd.z_mid, "assumption; forward skirt mid"
                elif name.startswith("TVC") or name.startswith("Igniter"):
                    z, src, grp = aft.z_mid, "assumption; aft end of the motor", "Propulsion"
                elif name == "Separation hardware":
                    z, src, J, shape, grp = z_top, "assumption; top of stage", inr.ring(m, R), "thin ring", "Structure"
                else:
                    z, src = 0.5 * (z_base + z_top), "assumption; mid-stage"
                tmp.append(MassItem(name, sr.index, grp, m, z, src, "dry", J[0], J[1], ext[0], ext[1], shape))
            items.extend(tmp)
            mtot = sum(i.mass_kg for i in tmp)
            zc = sum(i.mass_kg * i.z_m for i in tmp) / mtot
            f = sr.components["Mass growth margin"] / mtot
            # margin = scaled copy of the stage's components: same CM, inertia f x (sum of components about the margin CM)
            Jr = f * sum(i.J0_roll + i.ext_roll for i in tmp)
            Jp = f * sum(i.J0_pitch + i.ext_pitch + i.mass_kg * (i.z_m - zc) ** 2 for i in tmp)
            add("Mass growth margin", sr.index, "Margin", sr.components["Mass growth margin"], zc,
                "single margin; distributed like the stage's other dry components", "dry", "scaled copy of stage components", (Jr, Jp))
        # ---- propellant -------------------------------------------------------------------
        if st.is_solid:
            sg = tank_by_role["grain"]
            g = sg.tank
            zb = sg.z0 + g.t_wall
            zl, jr, jp = _grain_inertia(g, g.V_prop, sr.m_prop_loaded_kg)
            add(f"Solid propellant grain ({g.propellant})", sr.index, "Propellant", sr.m_prop_loaded_kg, zb + zl,
                "cast grain centroid (book p.490: loaded SRM CM at the centre of the propellant mass)", "prop_loaded",
                "centre-perforated grain, solid of revolution (numerical)", (jr, jp))
            m_r = sr.m_residual_kg + sr.m_margin_prop_kg
            if m_r > 0:
                add("Residual propellant (slivers/slag)", sr.index, "Propellant", m_r, sg.z0 + g.h_dome,
                    "assumption: residual slivers near the aft end at burnout", "prop_resid", "point (assumed)")
        else:
            frac = {"oxidizer": st.of_ratio / (1 + st.of_ratio), "fuel": 1 / (1 + st.of_ratio)}
            for role, seg in tank_by_role.items():
                g = seg.tank
                zb = _tank_z_internal_bottom(seg)
                ps = spec.propellants[g.propellant]
                zl, jr, jp = _liquid_inertia(g, g.V_liquid, g.m_liquid_loaded)
                add(f"Propellant loaded ({role}, {g.propellant})", sr.index, "Propellant", g.m_liquid_loaded, zb + zl,
                    "liquid column centroid, full load", "prop_loaded", "liquid solid of revolution (numerical)", (jr, jp))
                m_r = (sr.m_residual_kg + sr.m_margin_prop_kg) * frac[role]
                zr, jr, jp = _liquid_inertia(g, m_r / ps.density_kg_m3, m_r)
                add(f"Residual + margin propellant ({role})", sr.index, "Propellant", m_r, zb + zr,
                    "liquid at tank bottom at burnout", "prop_resid", "liquid solid of revolution (numerical)", (jr, jp))

    # ---- strap-on boosters ----------------------------------------------------------------
    br = res.boosters
    if br is not None:
        n, rho = br.n_total, geom.booster_x_m
        case_seg = [s for s in geom.booster_segments if s.kind == "booster_case"][0]
        nose_seg = [s for s in geom.booster_segments if s.kind == "booster_nose"]
        g = br.case
        ext = lambda m: (m * rho ** 2, m * rho ** 2 / 2)
        for name, m_each in br.components.items():
            m = n * m_each
            if name == "Nose cone" and nose_seg:
                s = nose_seg[0]
                z = s.z0 + s.length / 3.0
                J = inr.cone_shell(m, s.d_bot / 2, s.length)
                shape, src = "thin cone (Table 8.10)", "13.3 kg/m^2 x cone area; CM at h/3"
            elif name.startswith("Casing"):
                zo, jr, jp = inr.shell_of_revolution(m, *inr.tank_outline(g.D_ext / 2, g.h_dome + g.t_wall, g.h_cyl))
                z, J = case_seg.z0 + zo, (jr, jp)
                shape, src = "thin shell of revolution (numerical)", "casing/inert mass per booster inert method"
            else:
                z, J = case_seg.z_mid, (0.0, 0.0)
                shape, src = "point (assumed)", "assumption: at the casing mid-length"
            add(f"Boosters: {name} ({n} x {m_each:,.0f} kg)", -2, "Boosters", m, z, src, "booster_dry", shape, J, ext(m))
        m_p = n * br.m_prop_each_kg
        if br.kind == "solid":
            zl, jr, jp = _grain_inertia(g, g.V_prop, m_p)
            shape = "centre-perforated grain (numerical)"
        else:
            zl, jr, jp = _liquid_inertia(g, g.V_prop, m_p)
            shape = "equivalent bulk-density column (numerical)"
        add(f"Boosters: propellant ({n} x {br.m_prop_each_kg:,.0f} kg)", -2, "Boosters", m_p,
            case_seg.z0 + g.t_wall + zl, "propellant centroid inside the booster casing", "booster_prop", shape,
            (jr, jp), ext(m_p))
    # ---- payload, adapter, fairing ---------------------------------------------------------
    Dt = spec.stages[-1].diameter_m
    f_ = spec.fairing
    add("Payload", 0, "Payload", res.payload_mass_kg, 0.5 * (geom.payload_z0 + geom.payload_z1), "envelope mid-length; uniform solid cylinder assumed",
        "payload", "solid cylinder (Table 8.17), uniform density assumed", inr.solid_cyl(res.payload_mass_kg, f_.envelope_diameter_m / 2, f_.envelope_length_m))
    add("Payload adapter (PAF)", 0, "Payload", res.paf_mass_kg, 0.5 * (geom.paf_z0 + geom.paf_z1), "PAF mid-length", "paf", "thin cylinder (assumed)",
        inr.cyl_shell(res.paf_mass_kg, Dt / 2, geom.paf_z1 - geom.paf_z0))
    from .geometry import segment_area
    fs = [x for x in geom.segments if x.kind.startswith("fairing")]
    A = [segment_area(x) for x in fs]
    for x, a in zip(fs, A):
        m = res.fairing_mass_kg * a / sum(A)
        if x.kind == "fairing_cyl":
            add("Payload fairing (cylinder)", -1, "Fairing", m, x.z_mid, "area-weighted share; thin cylinder (Table 8.10)", "fairing", "thin cylinder (Table 8.10)", inr.cyl_shell(m, x.d_bot / 2, x.length))
        else:
            add("Payload fairing (nose cone)", -1, "Fairing", m, x.z0 + x.length / 3.0, "area-weighted share; thin cone, CM at h/3 (Table 8.10)", "fairing", "thin cone (Table 8.10)", inr.cone_shell(m, x.d_bot / 2, x.length))
    return items


def partial_core_prop_items(res, stage_index: int, consumed_kg: float) -> list:
    """Propellant items of one stage after `consumed_kg` has been burned (used at the strap-on burnout events).

    Liquid: each tank drains in mixture-ratio proportion and the remaining column is re-integrated.
    Solid: the grain bore is enlarged so that the remaining grain volume matches.
    """
    spec, geom = res.spec, res.geometry
    sr = res.stages[stage_index - 1]
    st = spec.stages[stage_index - 1]
    segs = {s.tank.role: s for s in geom.stage_segments(stage_index) if s.kind == "tank"}
    out = []
    if st.is_solid:
        sg = segs["grain"]
        g = sg.tank
        m_left = max(sr.m_prop_loaded_kg - consumed_kg, 0.0)
        V_left = m_left / (g.m_liquid_loaded / g.V_prop) if g.V_prop > 0 else 0.0
        zl, jr, jp = _grain_inertia(g, V_left, m_left)
        out.append(MassItem(f"Solid propellant grain remaining ({g.propellant})", stage_index, "Propellant", m_left,
                            sg.z0 + g.t_wall + zl, "grain remaining at this instant (bore scaled to the remaining volume)",
                            "prop_partial", jr, jp, 0.0, 0.0, "centre-perforated grain (numerical)"))
        return out
    frac = {"oxidizer": st.of_ratio / (1 + st.of_ratio), "fuel": 1 / (1 + st.of_ratio)}
    for role, sg in segs.items():
        g = sg.tank
        ps = spec.propellants[g.propellant]
        m_left = max(g.m_liquid_loaded - consumed_kg * frac[role], 0.0)
        V_left = m_left / ps.density_kg_m3
        zl, jr, jp = _liquid_inertia(g, max(V_left, 1e-9), max(m_left, 1e-9))
        out.append(MassItem(f"Propellant remaining ({role}, {g.propellant})", stage_index, "Propellant", m_left,
                            _tank_z_internal_bottom(sg) + zl, "liquid column at this instant", "prop_partial",
                            jr, jp, 0.0, 0.0, "liquid solid of revolution (numerical)"))
    return out


def _present(item, k, phase, J, N, boost_stage=0) -> bool:
    """Is this ledger item on the vehicle at event (stage k, phase)?

    phase: 'ignition' (stage k full), 'burnout' (stage k empty, not yet separated),
           'boost_burnout' (strap-ons empty, still attached), 'after_boost' (strap-ons jettisoned).
    """
    if item.kind in ("payload", "paf"):
        return True
    if item.kind == "fairing":
        return (k < J) if k <= N else (J > N)
    if item.kind == "booster_dry":
        return k == boost_stage and phase in ("ignition", "boost_burnout")
    if item.kind == "booster_prop":
        return k == boost_stage and phase == "ignition"
    j = item.stage
    if item.kind == "dry":
        return j > k or (j == k and phase in ("ignition", "burnout", "boost_burnout", "after_boost"))
    if item.kind == "prop_loaded":
        return j > k or (j == k and phase == "ignition")
    if item.kind == "prop_resid":
        return j == k and phase == "burnout"
    return False


def cm_of(items) -> tuple:
    m = sum(i.mass_kg for i in items)
    return m, (sum(i.mass_kg * i.z_m for i in items) / m if m > 0 else float("nan"))


def inertia_of(items, z_cm=None) -> dict:
    """Assembly moments of inertia about the assembly CM (parallel-axis theorem, book Eq. 8:37 and procedure p.526).
    J_roll  = sum(J0_roll + m rho^2) ; J_pitch = J_yaw = sum(J0_pitch + m L^2 + (m rho^2/2 for off-axis rings))."""
    m, zc = cm_of(items)
    zc = zc if z_cm is None else z_cm
    jr = sum(i.J0_roll + i.ext_roll for i in items)
    jp = sum(i.J0_pitch + i.ext_pitch + i.mass_kg * (i.z_m - zc) ** 2 for i in items)
    # book-style value (Table 8.22): propellant treated as point masses (J0 = 0), axial offsets only
    jp_book = sum((0.0 if "prop" in i.kind else i.J0_pitch) + i.mass_kg * (i.z_m - zc) ** 2 for i in items)
    return dict(J_roll=jr, J_pitch=jp, J_yaw=jp, J_pitch_book_form=jp_book)


def event_table(res) -> dict:
    N = len(res.stages)
    J = res.spec.fairing.jettison_stage
    L = res.geometry.total_length
    br = res.boosters
    bstage = br.attach_stage if br else 0
    rows = []

    def add(label, k, phase, note="", extra=None):
        its = [i for i in res.ledger if _present(i, k, phase, J, N, bstage)] + list(extra or [])
        m, z = cm_of(its)
        rows.append(dict(event=label, mass_kg=m, z_cm_m=z, z_cm_over_L=z / L, n_items=len(its), note=note, **inertia_of(its)))

    add("Liftoff (stage 1 ignition, full load)", 1, "ignition")
    for k in range(1, N + 1):
        if k > 1:
            add(f"Stage {k} ignition (after stage {k-1} separation{', fairing jettisoned' if k == J else ''})", k, "ignition")
        if br and k == bstage:
            sr_b = res.stages[k - 1]
            burned = sr_b.m_startup_kg + sr_b.mdot_kgs * br.burn_time_s
            part = partial_core_prop_items(res, k, burned)
            add(f"Strap-on burnout ({br.n_total} x {br.name} empty, still attached)", k, "boost_burnout",
                f"core has burned {burned:,.0f} kg (start-up + parallel phase)", part)
            add(f"After strap-on jettison (-{br.n_total * br.m_inert_each_kg:,.0f} kg)", k, "after_boost",
                "start of the series portion of the burn (book Fig. 5.21)", part)
        add(f"Stage {k} burnout (before separation)", k, "burnout")
    add("Orbit insertion (payload + adapter" + (" + fairing)" if J > N else ")"), N + 1, "ignition")
    stage_rows = []
    for sr in res.stages:
        its = [i for i in res.ledger if i.stage == sr.index and i.kind in ("dry", "prop_loaded")]
        m, z = cm_of(its)
        stage_rows.append(dict(stage=sr.index, mass_kg=m, z_cm_m=z, **inertia_of(its)))
    if br:
        its = [i for i in res.ledger if i.stage == -2]
        m, z = cm_of(its)
        stage_rows.append(dict(stage=0, mass_kg=m, z_cm_m=z, **inertia_of(its)))
    for r_ in rows:
        r_["roll_to_pitch_ratio"] = r_["J_roll"] / r_["J_pitch"]
    notes = [f"Stage {s.index}: dry mass smeared (aggregate mode) - CM and inertia are indicative only" for s in res.stages
             if res.spec.stages[s.index - 1].structure_mode == "aggregate_s"]
    notes.append("Component locations/shapes are preliminary lumped assumptions (see ledger 'shape' column). Inertias use the book's "
                 "parallel-axis method; thrust structure, feed system, payload and PAF shapes are assumptions; products of inertia "
                 "are zero by the axisymmetry assumption.")
    if br:
        notes.append(f"{br.n_total} strap-on boosters are treated as an axisymmetric ring at radius {res.geometry.booster_x_m:.2f} m "
                     "(J_pitch gets m rho^2/2 per booster); for n = 2 the real pitch and yaw inertias differ from this average.")
    return dict(events=rows, stages=stage_rows, warnings=notes)
