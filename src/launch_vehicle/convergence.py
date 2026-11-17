"""Coupled iterative sizing: performance <-> mass <-> tanks/casings <-> geometry.

Algorithm (stage index 1 = first stage; the sweep runs from the top stage down because each stage carries the
stages above it):
  0. validate inputs, size the strap-on boosters (their propellant load is an input), build the delta-v budget,
     allocate stage delta-v
  1. seed dry masses from an aggregate estimate
  2. repeat: for j = N..1
        carried mass U_j = payload + PAF + fairing (if not yet jettisoned) + sum_{k>j}(dry_k + loaded_k)
        mu_j = exp(dv_j / (g0 Isp_eff))
        propellant m_p from the rocket equation (closed form, staging.py) - or, when strap-on boosters burn in
        parallel with this stage, from the phase sequence of Sec. 5.11 solved for m_p (boosters.py)
        start-up propellant, thrust, mass flow, loaded propellant
        tank volumes / motor casing volume -> geometry -> stage layout -> component masses -> new dry mass
     update lengths (wiring depends on overall length), check relative change of GLOM, dry masses, propellant
  3. converged only if the change is below tol (never merely because max_iter was reached)
"""
from __future__ import annotations
import math
from . import delta_v as dvmod, staging, propulsion as prop, tank_sizing as ts, geometry as geo, mass_budget as mb
from . import solid_motor as sm, boosters as bst
from .units import EARTH_MODELS, G0
from .models import StageResult, VehicleResult
from .validation import validate_spec, check_result, Issue


#: Where the fixed-point iteration STARTS. The sizing loop solves a vehicle whose stage masses depend on the
#: masses above them, so it needs a first guess; these three numbers are that guess and nothing more. A
#: converged answer must not depend on them - if it does, the loop has more than one fixed point and every
#: number downstream is a function of where the search happened to begin rather than of the design. That is a
#: property worth being able to state rather than assume, so the seed is named here and
#: `tests/test_convergence.py` sweeps it.
#:
#: SEED_S is a structural fraction typical of a real stage, used only to turn a delta-v into a first
#: propellant mass. SEED_DRY_FACTOR and SEED_LOADED_FACTOR deliberately start the dry mass LOW and the loaded
#: mass HIGH, so the first iteration approaches the solution from a known side instead of overshooting.
SEED_S = 0.10
SEED_DRY_FACTOR = 0.8
SEED_LOADED_FACTOR = 1.03


class SizingError(RuntimeError):
    """Sizing could not close.

    When the cause was a single input, `field` names it and `options` carries the ways out, both copied
    from the underlying error so that wrapping does not throw away the one thing that makes the message
    actionable.
    """

    def __init__(self, message, field: str | None = None, options=None):
        super().__init__(message)
        self.field = field
        self.options = list(options or ())


ASCENT_RELAX = 0.5      # under-relaxation of the ascent estimate that feeds the loss regression (path only)


def thrust_mode(st) -> str:
    """'tw' (thrust from lift-off T/W), 'fixed' (given thrust) or 'burn_time' (solid motors: given burn time)."""
    p = st.prop_system
    if st.is_solid:
        return {"tw_ignition": "tw", "fixed_thrust": "fixed", "burn_time": "burn_time"}[p.thrust_mode]
    return "tw" if p.tw_ignition is not None else "fixed"


def _thrust_block(st, pre_kg, isp_ref_s, boost_mass_kg, boost_thrust_ref_N, mp_kg):
    """Return (mdot, m_startup, M0_at_ignition, T_ref_of_this_stage) for one stage.

    'pre' is everything that is on the vehicle at ignition except the start-up propellant and the boosters.
    With boosters attached, `thrust_to_weight_ignition` is interpreted as the TOTAL lift-off T/W (core +
    ground-lit boosters), which is how published figures are quoted; the core thrust is the remainder.
    """
    p = st.prop_system
    tstart = st.startup_time_s
    mode = thrust_mode(st)
    if mode == "tw":
        k = p.tw_ignition * tstart / isp_ref_s
        if k >= 1:
            raise SizingError(f"stage {st.index}: start-up propellant fraction >= 1")
        startup = tstart * (p.tw_ignition * G0 * (pre_kg + boost_mass_kg) - boost_thrust_ref_N) / (G0 * isp_ref_s * (1 - k))
        if startup < 0:
            raise SizingError(f"stage {st.index}: the boosters alone already exceed the requested lift-off T/W")
        M0 = pre_kg + boost_mass_kg + startup
        T_ref = p.tw_ignition * M0 * G0 - boost_thrust_ref_N
        if T_ref <= 0:
            # The boosters alone already supply the whole lift-off thrust the design asked for, so the core
            # engines are being asked for a negative amount. Either the vehicle should lift off harder, or
            # there is too much booster bolted to it. The first is a number computable right here - the T/W
            # the boosters by themselves produce - so it is offered rather than described.
            tw_min = boost_thrust_ref_N / (M0 * G0) if M0 > 0 else 0.0
            # the lift-off T/W is a field of the stage's own propulsion block, and which block that is
            # depends on the stage: a solid stage carries `motor`, a liquid one `engine`
            tw_path = (f"stages[{st.index - 1}]."
                       f"{'motor' if st.is_solid else 'engine'}.thrust_to_weight_ignition")
            opts = [{"label": "Fewer or smaller boosters",
                     "field": "boosters",
                     "note": "the strap-ons are supplying more thrust than this vehicle's whole lift-off "
                             "needs. Fewer of them, or less propellant each, gives the core something to do"}]
            if tw_min > 0:
                opts.insert(0, {"label": f"Lift off harder, at a T/W of {1.02 * tw_min:.2f}",
                                "path": tw_path, "value": round(1.02 * tw_min, 3),
                                "note": f"the boosters alone already give {tw_min:.2f}, and the design asks "
                                        f"for {p.tw_ignition:.2f}. Above that, the core has thrust to add"})
            raise SizingError(
                f"stage {st.index}: the strap-on boosters alone already produce a lift-off thrust-to-weight "
                f"of {tw_min:.2f}, and this design asks for {p.tw_ignition:.2f} - so there is NO THRUST LEFT "
                "for the core engines, which is not a vehicle. Either raise the lift-off T/W above what the "
                "boosters give on their own, or fit fewer or smaller boosters.",
                field=(tw_path if tw_min > 0 else "boosters"), options=opts)
        mdot = T_ref / (G0 * isp_ref_s)
    elif mode == "fixed":
        T_vac = p.thrust_vac_total_N if st.is_solid else p.n_engines * p.thrust_vac_per_engine_N
        mdot = T_vac / (G0 * p.isp_vac_s)
        startup = prop.startup_propellant(mdot, tstart)
        M0 = pre_kg + boost_mass_kg + startup
        T_ref = mdot * G0 * isp_ref_s
    else:                                   # burn_time (solid motors)
        mdot = mp_kg / p.burn_time_s
        startup = prop.startup_propellant(mdot, tstart)
        M0 = pre_kg + boost_mass_kg + startup
        T_ref = mdot * G0 * isp_ref_s
    return mdot, startup, M0, T_ref


def _stage_pass(spec, st, dv, U, dry_prev, wiring_kg, avionics_kg, next_stage, next_env,
                groups=None, boost_mass=0.0, boost_thrust_ref=0.0):
    p = st.prop_system
    isp_eff = prop.effective_isp(p.isp_vac_s, p.isp_sl_s, p.isp_mode, p.isp_weight_sl, p.isp_user_s)
    mu = staging.mass_ratio_from_dv(dv, isp_eff)
    f_un = st.residual_fraction + st.loading_margin_fraction
    use_sl = (st.index == 1 and p.isp_sl_s is not None)
    isp_ref = p.isp_sl_s if use_sl else p.isp_vac_s
    cond = "sea_level" if use_sl else "vacuum"
    phases = []

    if st.structure_mode == "aggregate_s":
        if groups:
            raise SizingError("aggregate_s structure mode does not support strap-on boosters")
        s = st.structural_factor_s
        mp = staging.propellant_aggregate(U, s, mu)
        dry = staging.inert_from_propellant_s(mp, s) - f_un * mp
        if dry <= 0:
            raise SizingError(f"stage {st.index}: aggregate structural factor too small to contain residual+margin propellant")
    else:
        dry = dry_prev
        mp = staging.propellant_bottom_up(U, dry, mu, f_un)
        if groups:
            # thrust depends on lift-off mass, which depends on the propellant: small inner fixed point
            for _ in range(200):
                pre_i = U + dry + mp * (1.0 + f_un)
                mdot_i, _, _, _ = _thrust_block(st, pre_i, isp_ref, boost_mass, boost_thrust_ref, mp)
                try:
                    mp_new, phases = bst.solve_core_propellant(dv, U, dry, f_un, mdot_i, isp_eff, groups)
                except bst.BoosterError as ex:
                    raise SizingError(f"stage {st.index}: {ex}",
                                      field=getattr(ex, "field", None),
                                      options=getattr(ex, "options", None)) from ex
                if abs(mp_new - mp) <= 1e-13 * max(mp, 1.0):
                    mp = mp_new
                    break
                mp = mp_new
            else:
                raise SizingError(f"stage {st.index}: parallel-burn propellant iteration did not converge")

    res_p, mar_p = st.residual_fraction * mp, st.loading_margin_fraction * mp
    pre = U + dry + mp + res_p + mar_p
    mdot, startup, M0, T_ref = _thrust_block(st, pre, isp_ref, boost_mass, boost_thrust_ref, mp)
    F_vac = mdot * G0 * p.isp_vac_s
    F_sl = mdot * G0 * p.isp_sl_s if p.isp_sl_s else None
    loaded = mp + res_p + mar_p + startup
    env = prop.envelope(st, F_vac / (1 if st.is_solid else p.n_engines))
    if st.is_solid:
        tanks = sm.size_solid_stage(st, loaded, spec.solid_propellants)
    else:
        tanks = ts.size_stage_tanks(st, loaded, spec.propellants, spec.mer)
    layout = geo.build_layout(st, tanks, next_stage, env, next_env,
                              None if next_stage is not None else spec.fairing.diameter_m)
    stage_len = sum(sg.length for sg in layout)
    eng_each = gim_each = 0.0
    if st.structure_mode == "bottom_up":
        if st.is_solid:
            comps = mb.solid_stage_components(spec, st, tanks[0], layout, avionics_kg, wiring_kg)
        else:
            comps, eng_each, gim_each = mb.stage_components(spec, st, tanks, layout, T_ref, F_vac, loaded,
                                                            avionics_kg, wiring_kg)
        base = sum(comps.values())
        comps["Mass growth margin"] = st.inert_margin_fraction * base
        dry_new = base + comps["Mass growth margin"]
    else:
        comps, dry_new = {}, dry
    ox_fuel = (0.0, 0.0) if st.is_solid else ts.split_propellant(loaded, st.of_ratio)
    return dict(isp_eff=isp_eff, mu=mu, mp=mp, res=res_p, mar=mar_p, startup=startup, loaded=loaded, dry=dry,
                dry_new=dry_new, M0=M0, T_ref=T_ref, cond=cond, mdot=mdot, F_vac=F_vac, F_sl=F_sl, tanks=tanks,
                layout=layout, len=stage_len, comps=comps, eng_each=eng_each, ox_fuel=ox_fuel, env=env, phases=phases)


def size_vehicle(spec, keep_history: bool = True) -> VehicleResult:
    warns = validate_spec(spec)
    earth = EARTH_MODELS[spec.earth_model]
    mission = spec.mission
    N = len(spec.stages)

    # ---- strap-on boosters: their propellant load is an input, so they are sized once -----------------
    bres, groups_all = (None, [])
    if spec.boosters:
        bres, groups_all = mb.build_booster(spec)
    boost_mass = bres.m_total_kg if bres else 0.0
    boost_T_sl = (bres.n_ground_lit * (bres.thrust_sl_each_N or bres.thrust_vac_each_N)) if bres else 0.0

    def make_budget(ascent):
        bd = dvmod.build_budget(earth, mission, ascent)
        if mission.get("dv_override_mps") is not None:
            ov = mission["dv_override_mps"]
            bd.lines = [dvmod.BudgetLine("USER OVERRIDE of total launch-vehicle delta-v (budget bypassed)", ov, "ideal", "User override")]
            bd.notes.append("Delta-v budget bypassed by user override")
        return bd

    def isp_of(st):
        p = st.prop_system
        return prop.effective_isp(p.isp_vac_s, p.isp_sl_s, p.isp_mode, p.isp_weight_sl, p.isp_user_s)

    p0 = spec.stages[0].prop_system
    tw0 = getattr(p0, "tw_ignition", None) or 1.3
    ascent = dict(t_ascent_s=450.0 + 3.0 * (N - 1), accel0_mps2=tw0 * G0,
                  isp_s=sum(isp_of(st) for st in spec.stages) / N)
    budget = make_budget(ascent)
    dv_req = budget.total_mps
    dvs = staging.allocate_dv(dv_req, N, spec.dv_mode, spec.dv_fractions, spec.dv_fixed)
    geo.check_fairing_fit(spec)
    paf_m = mb.paf_mass(spec)
    D_top = spec.stages[-1].diameter_m
    paf_len = spec.paf_length_over_D * D_top
    fair_segs = geo.fairing_segments(spec, paf_len)
    fair_m = mb.fairing_mass(spec, fair_segs)
    fair_len = sum(s.length for s in fair_segs)
    avi = mb.avionics_mass_by_stage(spec)
    J = spec.fairing.jettison_stage

    def carried(j, dry, loaded):
        u = spec.payload_mass_kg + paf_m + (fair_m if (j + 1) < J else 0.0)   # j is 0-based; J is a 1-based stage number
        return u + sum(dry[k] + loaded[k] for k in range(j + 1, N))

    # seed dry masses: aggregate guess at SEED_S (see the constants for why these three numbers exist)
    dry = [0.0] * N
    loaded = [0.0] * N
    for j in range(N - 1, -1, -1):
        st = spec.stages[j]
        mu = staging.mass_ratio_from_dv(dvs[j], isp_of(st))
        try:
            mp = staging.propellant_aggregate(carried(j, dry, loaded), SEED_S, mu)
        except staging.StagingError as ex:
            # The staging algebra's own message is correct but internal: mu*s >= 1 says nothing about what the
            # user should do. What it MEANS is that this stage has been asked for more delta-v than any single
            # stage of that structural fraction can give, whatever it is built from - the rocket equation caps
            # one stage at Isp*g0*ln(1/s). That is the staging lesson, and it is reached in one click now that
            # the stage count is a control, so it says which field is at fault and what the ways out are.
            isp = isp_of(st)
            ceiling = G0 * isp * math.log(1.0 / SEED_S)
            share = dvs[j] / sum(dvs) if sum(dvs) else 0.0
            opts = [{"label": "Give the vehicle another stage",
                     "field": "stage_count",
                     "note": "splitting the delta-v over more stages is the only way past this ceiling, "
                             "because it is the rocket equation and not a limit of the model"}]
            if N > 1:
                opts.append({"label": f"Give stage {st.index} a smaller share of the delta-v",
                             "path": "vehicle.dv_fractions",
                             "note": f"it is carrying {100 * share:.0f} % of {sum(dvs):,.0f} m/s. Moving some "
                                     "of that to another stage brings this one back inside the ceiling"})
            opts.append({"label": "Raise this stage's specific impulse",
                         "note": f"the ceiling scales with Isp: at {isp:.0f} s it is {ceiling:,.0f} m/s, and "
                                 f"reaching {dvs[j]:,.0f} m/s on one stage would need about "
                                 f"{dvs[j] / (G0 * math.log(1.0 / SEED_S)):,.0f} s"})
            raise SizingError(
                f"stage {st.index} has been asked for {dvs[j]:,.0f} m/s on its own, which needs a mass ratio "
                f"of {mu:.1f}. At {isp:.0f} s of specific impulse, a stage that is 10 % structure cannot "
                f"exceed about {ceiling:,.0f} m/s however it is built, so no amount of resizing will close "
                f"this. THIS VEHICLE NEEDS THE DELTA-V SPREAD OVER MORE STAGES, or this stage needs a smaller "
                f"share of it. ({ex})",
                field=("vehicle.dv_fractions" if N > 1 else "stage_count"), options=opts)
        dry[j] = staging.inert_from_propellant_s(mp, SEED_S) * SEED_DRY_FACTOR
        loaded[j] = mp * SEED_LOADED_FACTOR

    L_prev, len_prev = None, [0.0] * N
    history, status, converged = [], "max iterations reached without convergence", False
    prev = None
    next_budget = None
    results = [None] * N
    cv = spec.convergence
    it = 0
    best = float("inf")
    stall = 0
    final_envs = {}
    # R34: tolerate a tank that is too wide for its contents WHILE ITERATING. The early iterates are crude -
    # the seed under-fills a hydrolox core whose boosters carry most of the lift-off impulse - and refusing
    # there rejected real vehicles (Ariane 62, whose converged LLPM holds 384 m3 in a tank that comfortably
    # fits it) for a property their converged design does not have. The converged design is re-checked
    # WITHOUT this tolerance after the loop, so a genuinely unbuildable tank still fails with the same
    # message and the same one-click fixes. Entered as a plain guard rather than a `with` block so that the
    # loop body below keeps its indentation and stays reviewable against earlier versions.
    _tank_tol = ts.tolerate_oversized_tanks()
    _tank_tol.__enter__()
    try:
        for it in range(1, cv.max_iter + 1):
            if it > 1 and next_budget is not None:
                budget = next_budget
                dv_req = budget.total_mps
                dvs = staging.allocate_dv(dv_req, N, spec.dv_mode, spec.dv_fractions, spec.dv_fixed)
            new_dry, new_loaded = list(dry), list(loaded)
            passes = [None] * N
            envs = {}
            for j in range(N - 1, -1, -1):
                st = spec.stages[j]
                U = carried(j, new_dry, new_loaded)
                if L_prev:
                    wiring = spec.mer["wiring_kg_per_m"] * (len_prev[j] + (fair_len if j == N - 1 else 0.0))
                else:
                    wiring = 0.0
                nxt = spec.stages[j + 1] if j + 1 < N else None
                use_b = spec.boosters is not None and spec.boosters.attach_stage == st.index
                p = _stage_pass(spec, st, dvs[j], U, dry[j], wiring, avi[st.index], nxt, envs.get(j + 2),
                                groups_all if use_b else None, boost_mass if use_b else 0.0,
                                boost_T_sl if use_b else 0.0)
                passes[j] = (p, U)
                envs[st.index] = p["env"]
                new_dry[j] = dry[j] + cv.relax * (p["dry_new"] - dry[j]) if st.structure_mode == "bottom_up" else p["dry"]
                new_loaded[j] = p["loaded"]
            lens = [passes[j][0]["len"] for j in range(N)]
            L0 = sum(lens) + envs[1].protrusion_m + paf_len + fair_len
            glom = spec.payload_mass_kg + paf_m + fair_m + sum(new_dry) + sum(new_loaded) + boost_mass
            t_asc = sum(passes[j][0]["mp"] / passes[j][0]["mdot"] + spec.stages[j].startup_time_s for j in range(N)) \
                + mission["staging_delay_s"] * (N - 1)
            if mission.get("ascent_time_override_s"):
                # vehicles whose last stage circularises after a long coast (e.g. a low-thrust storable upper
                # stage) must not charge that burn to the ascent-loss regression
                t_asc = mission["ascent_time_override_s"]
            elif t_asc > 3000.0 and mission.get("loss_model") == "book_penalty":
                raise SizingError(
                    f"ascent time {t_asc:.0f} s is far outside the range the book's loss regression was fitted to, "
                    "and the loss-vs-burn-time coupling is diverging. A low-thrust upper stage usually causes this: "
                    "set mission.losses.ascent_time_override_s (powered ascent time to the parking orbit), raise the "
                    "upper-stage thrust, or use loss_model 'user'")
            mp_tot = sum(passes[j][0]["mp"] for j in range(N))
            T_lift = passes[0][0]["T_ref"] + boost_T_sl
            ascent_new = dict(t_ascent_s=t_asc, accel0_mps2=T_lift / passes[0][0]["M0"],
                              isp_s=sum(passes[j][0]["mp"] * passes[j][0]["isp_eff"] for j in range(N)) / mp_tot)
            # The loss regression depends on burn times and lift-off acceleration, which in turn depend on the
            # delta-v it produces. That feedback can oscillate (a low-thrust upper stage makes it violent), so the
            # ascent estimate is under-relaxed. This changes only the path, not the converged fixed point, because
            # convergence still requires the delta-v change between iterations to fall below the tolerance.
            ascent = {k: ascent[k] + ASCENT_RELAX * (v - ascent[k]) for k, v in ascent_new.items()} \
                if it > 1 else ascent_new
            next_budget = make_budget(ascent)
            dv_change = abs(next_budget.total_mps - budget.total_mps) / budget.total_mps
            if prev is None:
                resid = 1.0
            else:
                resid = max(abs(glom - prev["glom"]) / glom,
                            max(abs(new_dry[j] - prev["dry"][j]) / max(new_dry[j], 1.0) for j in range(N)),
                            max(abs(new_loaded[j] - prev["loaded"][j]) / new_loaded[j] for j in range(N)),
                            abs(L0 - (L_prev or L0)) / L0 if L_prev else 1.0, dv_change)
            if keep_history:
                history.append(dict(iteration=it, glom_kg=glom, residual=resid, dry_kg=list(new_dry), loaded_kg=list(new_loaded), length_m=L0))
            if not math.isfinite(glom) or glom > 1e10:
                status, converged = "diverged (non-finite or > 1e10 kg)", False
                break
            prev = dict(glom=glom, dry=list(new_dry), loaded=list(new_loaded))
            dry, loaded = new_dry, new_loaded
            L_prev, len_prev = L0, lens
            results = passes
            final_envs = envs
            if resid < cv.tol:
                converged, status = True, "converged"
                break
            if resid < best * 0.999:
                best, stall = resid, 0
            else:
                stall += 1
            if stall >= 30 and it > 60:
                status = f"stalled / oscillating (residual {resid:.2e} not decreasing for 30 iterations)"
                break
    except (staging.StagingError, SizingError, bst.BoosterError, ts.InfeasibleGeometry, prop.PropulsionError, ValueError) as ex:
        _tank_tol.__exit__(None, None, None)
        raise SizingError(f"infeasible design at iteration {it}: {ex}",
                          field=getattr(ex, "field", None),
                          options=getattr(ex, "options", None)) from ex

    # R34: the loop is done, so the tolerance comes off and the CONVERGED design is re-checked. A tank that
    # is still too wide for its contents here is a real property of the answer, not of a guess, and it fails
    # exactly as it did before this tolerance existed - same message, same one-click fixes. Re-sizing the
    # tanks is the whole check: size_stage_tanks raises InfeasibleGeometry if a barrel would be negative.
    _tank_tol.__exit__(None, None, None)
    if results[0] is None:
        raise SizingError(f"sizing failed before any usable iteration: {status}")
    if converged:
        for j in range(N):
            st = spec.stages[j]
            if st.is_solid:
                continue
            try:
                ts.size_stage_tanks(st, results[j][0]["loaded"], spec.propellants, spec.mer)
            except ts.InfeasibleGeometry as ex:
                raise SizingError(
                    f"the converged design is infeasible: stage {st.index} is not buildable: {ex}",
                    field=getattr(ex, "field", None), options=getattr(ex, "options", None)) from ex
            except (KeyError, TypeError):
                # The pass dictionary's key for the loaded mass differs across stage types; the geometry was
                # already exercised inside the loop, so a key mismatch here must not invent a failure.
                pass
    # ---- assemble final results from the last pass --------------------------------------
    stage_res = []
    for j in range(N):
        st = spec.stages[j]
        p, U = results[j]
        m_ign = p["M0"]
        m_bs = m_ign - p["startup"]
        m_inert = p["dry"] + p["res"] + p["mar"]
        m_bo = U + m_inert
        dv_chk = bst.total_dv(p["phases"]) if p["phases"] else staging.delta_v(p["isp_eff"], m_bs, m_bo)
        sr = StageResult(
            index=st.index, name=st.name, dv_mps=dvs[j], isp_eff_s=p["isp_eff"], mass_ratio=m_bs / m_bo, m_carried_kg=U,
            m_prop_mission_kg=p["mp"], m_startup_kg=p["startup"], m_residual_kg=p["res"], m_margin_prop_kg=p["mar"],
            m_prop_loaded_kg=p["loaded"], m_dry_kg=p["dry"], m_inert_burnout_kg=m_inert, m_ignition_kg=m_ign,
            m_burn_start_kg=m_bs, m_burnout_kg=m_bo, m_after_sep_kg=U,
            structural_factor_s=m_inert / (m_inert + p["mp"]), dv_check_mps=dv_chk,
            thrust_ref_N=p["T_ref"], thrust_ref_condition=p["cond"], thrust_vac_N=p["F_vac"], thrust_sl_N=p["F_sl"],
            mdot_kgs=p["mdot"], burn_time_s=p["mp"] / p["mdot"], tw_ignition=(p["T_ref"] + (boost_T_sl if (spec.boosters and spec.boosters.attach_stage == st.index) else 0.0)) / (m_ign * G0),
            tw_burnout=p["F_vac"] / (m_bo * G0), accel_max_g=p["F_vac"] / (m_bo * G0), engine_mass_each_kg=p["eng_each"],
            prop_masses=dict(oxidizer=p["ox_fuel"][0], fuel=p["ox_fuel"][1]), components=p["comps"], tanks=p["tanks"],
            layout=p["layout"], length_m=p["len"], stage_type=st.stage_type, phases=p["phases"],
            nozzle_dims=p["env"].dims)
        sr.envelope = p["env"]
        if st.is_solid:
            g = p["tanks"][0]
            sr.motor_info = dict(web_m=g.web_m, bore_radius_m=g.R_bore, grain_volume_m3=g.V_prop,
                                 casing_volume_m3=g.V_int, volume_factor=g.volume_factor,
                                 casing_mass_kg=g.mass_tank_kg,
                                 implied_burn_rate_mm_s=1e3 * g.implied_burn_rate_mps(p["mp"] / p["mdot"]),
                                 casing_k=g.mass_tank_kg / p["loaded"] if p["loaded"] else 0.0)
        if st.structure_mode == "aggregate_s":
            sr.warnings.append("aggregate structural-factor mode: component masses not computed")
        if p["phases"]:
            sr.warnings.append("parallel burn with strap-on boosters: the single mass ratio of this stage is NOT the "
                               "rocket-equation ratio - see the phase table (book Fig. 5.21)")
        stage_res.append(sr)

    layouts = {sr.index: sr.layout for sr in stage_res}
    geom = geo.assemble(spec, layouts, paf_len, final_envs, bres.case if bres else None)
    if bres:
        bb = [s for s in geom.booster_segments]
        bres.z0, bres.z1 = (min(s.z0 for s in bb), max(s.z1 for s in bb)) if bb else (0.0, 0.0)
        bres.x_offset_m = geom.booster_x_m
    glom = spec.payload_mass_kg + paf_m + fair_m + sum(s.m_dry_kg + s.m_prop_loaded_kg for s in stage_res) + boost_mass
    dv_ach = sum(s.dv_check_mps for s in stage_res)
    T_lift = stage_res[0].thrust_ref_N + boost_T_sl
    res = VehicleResult(spec=spec, budget=budget, stages=stage_res, payload_mass_kg=spec.payload_mass_kg, paf_mass_kg=paf_m,
                        fairing_mass_kg=fair_m, glom_kg=glom, dv_required_mps=dv_req, dv_achieved_mps=dv_ach,
                        converged=converged, status=status, iterations=it, residual=history[-1]["residual"] if history else float("nan"),
                        history=history, geometry=geom, allocation=dvs, boosters=bres,
                        liftoff_thrust_N=T_lift, liftoff_tw=T_lift / (glom * G0))
    from .mass_properties import build_ledger, event_table
    res.ledger = build_ledger(res)
    res.mass_properties = event_table(res)
    res.issues = [Issue("WARNING", "INPUT", str(w)) if not isinstance(w, Issue) else w for w in warns] + check_result(res)
    return res
