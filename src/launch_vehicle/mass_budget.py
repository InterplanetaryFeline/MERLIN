"""Bottom-up component masses via statistical mass-estimating relationships (MERs).

Each component has exactly one source of truth here. In 'aggregate_s' structure mode none of these are used
(the aggregate inert mass replaces them) so nothing is counted twice. MER sources (printed page numbers):
Table 8.8 (p.495) structures/avionics/wiring/PAF; Table 8.9 (p.495) engines & gimbals; Table 8.6/8.7 tanks (pp.494-495).
MERs are statistical fits and are meaningful to ~3 significant digits at best (book p.493).
"""
from __future__ import annotations
from . import propulsion as prop
from .geometry import segment_area, cone_area, cylinder_area


def avionics_mass_by_stage(spec) -> dict:
    m = spec.mer
    N = len(spec.stages)
    total = m["avionics_large_kg"] if spec.payload_mass_kg > m["avionics_payload_threshold_kg"] else m["avionics_small_kg"]
    out = {}
    for st in spec.stages:
        if st.avionics_kg_override is not None:
            out[st.index] = st.avionics_kg_override
        elif N == 1:
            out[st.index] = total
        elif st.index == N:
            out[st.index] = m["avionics_upper_share"] * total
        else:
            out[st.index] = (1.0 - m["avionics_upper_share"]) * total / (N - 1)
    return out


def paf_mass(spec) -> float:
    """Payload attach fitting / launch vehicle adapter.

    'mer'      : Table 8.8 item 4, m = 0.0755 m_PL + 50 kg.
    'fraction' : m = k m_PL (k = 0.15). The 1st-edition errata (p.443) adds to Table 8.8 item 3:
                 "Use m_PAF = 0.15 m_PL for smaller payloads", because the +50 kg constant of the MER does not
                 scale down (it is 33 % of a 150 kg payload). Table 8.8 item 5 of the 2nd edition uses the same
                 0.15 m_PL for payload mounts below 20 kg.
    'auto'     : the fraction form below the small-launcher payload threshold, the MER above it.
    """
    if spec.paf_mass_override_kg is not None:
        return spec.paf_mass_override_kg
    m, pl = spec.mer, spec.payload_mass_kg
    method = spec.paf_method
    mer_val = m["paf_a"] * pl + m["paf_b"]
    frac_val = m["paf_small_payload_fraction"] * pl
    if method == "mer":
        return mer_val
    if method == "fraction":
        return frac_val
    if method == "auto":
        return frac_val if pl < m["paf_fraction_payload_threshold_kg"] else mer_val
    raise ValueError(f"unknown payload-adapter method '{method}' (use mer, fraction or auto)")


def fairing_mass(spec, fairing_segs: list) -> float:
    f = spec.fairing
    if f.mass_override_kg is not None:
        return f.mass_override_kg
    k = spec.mer["composite_fairing_kg_m2"] if f.material == "composite" else spec.mer["unpressurized_kg_m2"]
    return k * sum(segment_area(s) for s in fairing_segs)


def solid_stage_components(spec, stage, case, layout, avionics_kg, wiring_kg) -> dict:
    """Bottom-up components of a SERIAL SOLID stage (book Sec. 8.5, p.490).

    The casing MER (Eq. 8:18) already contains the internal insulation, the nozzle, the thrust structure and the
    TVC, so no engine, thrust-structure, gimbal, feed-system or pressurant mass may be added here. Forward and aft
    skirts and the interstage are ordinary unpressurised structure (Table 8.8 line 1).
    """
    m = spec.mer
    sf = stage.structure_mass_factor
    if getattr(case, "stage_level_inert", False):
        # A published stage-level relation already contains the skirts, interstage, avionics and wiring.
        # Adding the bottom-up components on top would count them twice, so the build-up stops here. The
        # structure_mass_factor still applies: it is the user's composite credit, not part of the relation.
        return {f"Solid stage inert ({case.mass_method})": sf * case.mass_tank_kg}
    c = {"Motor casing (incl. insulation, nozzle, thrust structure, TVC)": sf * case.mass_tank_kg}
    k = m["unpressurized_kg_m2"] * sf
    names = {"aft_skirt": "Aft skirt", "fwd_skirt": "Forward skirt", "interstage": "Interstage",
             "fwd_adapter": "Forward adapter cone"}
    for seg in layout:
        if seg.kind in names:
            c[names[seg.kind]] = k * segment_area(seg)
    c["Avionics"] = avionics_kg
    c["Wiring"] = wiring_kg
    if stage.motor.tvc_mass_kg:
        c["TVC actuators (user, outside the casing MER)"] = stage.motor.tvc_mass_kg
    if stage.motor.igniter_mass_kg:
        c["Igniter (user, outside the casing MER)"] = stage.motor.igniter_mass_kg
    if stage.separation_hw_kg:
        c["Separation hardware"] = stage.separation_hw_kg
    if stage.other_mass_kg:
        c["Other equipment"] = stage.other_mass_kg
    return c


def build_booster(spec):
    """Size one strap-on booster and return (BoosterResult, BoosterGroup list ordered by ignition).

    Solid boosters use the book's SRM relations (Eqs. 8:18/8:23/8:24). Liquid boosters are sized geometrically
    from the propellant volumes (an equivalent bulk density) and need a user inert mass or mass fraction, because
    the book gives no MER for a complete liquid booster.
    """
    from . import solid_motor as sm, propulsion as prop
    from .boosters import BoosterGroup
    from .geometry import cone_area
    from .tank_sizing import InfeasibleGeometry
    from .units import G0
    b = spec.boosters
    m_mission = b.prop_mass_each_kg
    m_res = b.residual_fraction * m_mission
    m_loaded = m_mission + m_res
    if b.kind == "solid":
        ps = spec.solid_propellants[b.propellant]
        rho, vf = ps.density_kg_m3, b.casing_volume_factor
        pname = b.propellant
    else:
        po, pf = spec.propellants[b.oxidizer], spec.propellants[b.fuel]
        m_ox = m_loaded * b.of_ratio / (1.0 + b.of_ratio)
        vol = m_ox / po.density_kg_m3 + (m_loaded - m_ox) / pf.density_kg_m3
        rho, vf = m_loaded / vol, b.casing_volume_factor
        pname = f"{b.oxidizer}/{b.fuel}"
    try:
        case = sm.size_motor_case(b.diameter_m, m_loaded, rho, b.dome_AR, b.wall_t_assumed_m, vf, pname)
    except InfeasibleGeometry as ex:
        # The casing sizer names its way out as a bare leaf - `diameter_m` - because it knows the geometry
        # and not what owns it. `solid_motor.size_solid_stage` completes those into `stages[N].…` for a
        # serial stage; nothing completed them for a BOOSTER, so the GUI was handed a path that resolves to
        # nothing and the one-click fix failed with "unknown parameter path 'diameter_m'". Only reachable
        # since boosters could be fitted from the browser, which is how it was found.
        for opt in getattr(ex, "options", ()):
            if opt.get("path") and not opt["path"].startswith("boosters."):
                opt["path"] = f"boosters.{opt['path']}"
        ex.field = next((o["path"] for o in getattr(ex, "options", ()) if o.get("path")), None)
        ex.args = (f"strap-on booster '{b.name}': " + str(ex),)
        raise
    if b.kind != "solid":
        # size_motor_case is reused for a liquid booster only to get a cylinder-plus-domes envelope that
        # holds the propellant. Its central BORE is a cast-grain concept - the free volume a core burner
        # needs for its flame front - and a liquid booster has no grain to bore. Leaving it set made every
        # consumer of the geometry believe there was one: the schematic drew a hatched grain with a bore
        # down the middle of a hydrogen tank, and the DXF put it on the LV_GRAIN layer. Clearing it here
        # rather than special-casing each drawing keeps the one wrong number from spreading.
        case.R_bore = 0.0
        case.bore_full_length = False
    if b.kind == "solid":
        m_case, k_eff, src = sm.casing_mass(m_loaded, b.inert_mass_method, b.inert_mass_fraction, b.inert_mass_each_kg)
    else:
        if b.inert_mass_method not in ("mass_fraction", "user_mass"):
            raise ValueError("a liquid strap-on booster needs inert_mass_method 'mass_fraction' or 'user_mass'"
                             " - the published relations in solid_inert are fitted to SOLID stages and say "
                             "nothing about a liquid booster")
        m_case, k_eff, src = sm.casing_mass(m_loaded, b.inert_mass_method, b.inert_mass_fraction, b.inert_mass_each_kg)
    case.mass_tank_kg = m_case
    case.stage_level_inert = sm.is_stage_level(b.inert_mass_method)
    # the nose cone exists geometrically whichever way its MASS is accounted for, and the booster's overall
    # length below needs it, so it is computed before the branch rather than inside one arm of it
    L_nose = b.nose_length_over_D * case.D_ext
    if case.stage_level_inert:
        # Same rule as a serial solid stage: a published relation fitted to flown stages already contains
        # the nose cone and the attach hardware, so adding them again would count them twice. Most of the
        # real strap-ons in those fits ARE boosters - Ariane's EAP, the Shuttle SRB, the H-IIA SRB-A - so
        # the relation applies here at least as well as it does to a serial stage.
        comps = {f"Booster inert ({b.inert_mass_method})": m_case}
        m_inert = m_case + m_res
    else:
        comps = {"Casing / dry structure": m_case}
        if L_nose > 0:
            comps["Nose cone"] = spec.mer["unpressurized_kg_m2"] * cone_area(case.D_ext / 2, L_nose)
        if b.attach_hw_mass_each_kg:
            comps["Attach / separation hardware"] = b.attach_hw_mass_each_kg
        base = sum(comps.values())
        if b.inert_margin_fraction:
            comps["Mass growth margin"] = b.inert_margin_fraction * base
        m_inert = sum(comps.values()) + m_res
    mdot = m_mission / b.burn_time_s
    isp_eff = prop.effective_isp(b.isp_vac_s, b.isp_sl_s, b.isp_mode, b.isp_weight_sl, None)
    F_vac = mdot * G0 * b.isp_vac_s
    F_sl = mdot * G0 * b.isp_sl_s if b.isp_sl_s else None
    length = b.nozzle_length_m + case.L_ext + L_nose
    from .models import BoosterResult
    res = BoosterResult(
        name=b.name, n_total=b.n_total, n_ground_lit=b.n_ground_lit, kind=b.kind, attach_stage=b.attach_stage,
        isp_eff_s=isp_eff, m_prop_each_kg=m_mission, m_inert_each_kg=m_inert, m_loaded_each_kg=m_mission + m_inert,
        m_total_kg=b.n_total * (m_mission + m_inert), thrust_vac_each_N=F_vac, thrust_sl_each_N=F_sl,
        mdot_each_kgs=mdot, burn_time_s=b.burn_time_s, diameter_m=case.D_ext, length_m=length, case=case,
        components=comps, structural_factor_s=m_inert / (m_inert + m_mission))
    res.warnings.append(f"casing/inert mass: {src}")
    if b.kind == "liquid":
        res.warnings.append("liquid booster: casing geometry uses an equivalent bulk density; no separate tanks are modelled")
    groups = []
    n_air = b.n_total - b.n_ground_lit
    ref_sl = F_sl if F_sl else F_vac
    if b.n_ground_lit > 0:
        groups.append(BoosterGroup(f"{b.name} (ground-lit)", b.n_ground_lit, mdot, isp_eff, m_mission, m_inert,
                                   b.burn_time_s, ref_sl))
    if n_air > 0:
        groups.append(BoosterGroup(f"{b.name} (air-lit)", n_air, mdot, isp_eff, m_mission, m_inert, b.burn_time_s, F_vac))
    return res, groups


def stage_components(spec, stage, tanks, layout, T_ref_total_N, F_vac_total_N, m_prop_loaded, avionics_kg,
                     wiring_kg) -> tuple:
    """Return (components dict name->mass, engine_mass_each, gimbal_each) for a bottom-up stage."""
    m = spec.mer
    e = stage.engine
    n = e.n_engines
    T_each_ref = T_ref_total_N / n
    if e.mass_method in ("mer", "mer_calibrated"):
        eng_each = prop.engine_mass_mer(T_each_ref, e.expansion_ratio,
                                        dict(a=m["engine_a"], b=m["engine_b"], c=m["engine_c"]))
        if e.mass_method == "mer_calibrated":
            # R20: measured against every database engine that publishes a dry mass, the book's relation is
            # biased LOW - 14 of 16 come out light, median -24 %. This factor removes that for the typical
            # engine and makes the two exceptional ones (Merlin 1D, RD-253) worse. Opt-in, never the default.
            eng_each *= m["engine_calibration_factor"]
    else:
        eng_each = e.mass_user_kg
    if e.gimbal_method == "mer":
        gim_each = prop.gimbal_mass_mer(T_each_ref, e.chamber_pressure_Pa, m["gimbal_k"], m["gimbal_exp"])
    elif e.gimbal_method == "user":
        gim_each = e.gimbal_user_kg
    else:
        gim_each = 0.0
    c = {}
    c["Engines"] = n * eng_each
    c["Engine gimbals"] = n * gim_each
    c["Thrust structure"] = prop.thrust_structure_mass(T_ref_total_N, m["thrust_structure_k"])
    sf = stage.structure_mass_factor
    for t in tanks:
        c[f"Tank structure ({t.role})"] = sf * t.mass_tank_kg
        if t.mass_insulation_kg:
            c[f"Tank insulation ({t.role})"] = t.mass_insulation_kg
    k = m["unpressurized_kg_m2"] * sf
    names = {"aft_skirt": "Aft skirt", "intertank": "Intertank", "fwd_skirt": "Forward skirt",
             "interstage": "Interstage", "fwd_adapter": "Forward adapter cone"}
    for seg in layout:
        if seg.kind in names:
            c[names[seg.kind]] = k * segment_area(seg)
    c["Avionics"] = avionics_kg
    c["Wiring"] = wiring_kg
    c["Feed system"] = stage.feed_mass_per_engine_kg * n
    c["Pressurant system"] = stage.pressurant_fraction * m_prop_loaded
    if stage.separation_hw_kg:
        c["Separation hardware"] = stage.separation_hw_kg
    if stage.other_mass_kg:
        c["Other equipment"] = stage.other_mass_kg
    return c, eng_each, gim_each
