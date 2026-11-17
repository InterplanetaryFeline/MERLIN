"""Input validation (hard errors) and result checks (engineering warnings / infeasibility flags)."""
from __future__ import annotations
import math
import re
from dataclasses import dataclass


class InputError(ValueError):
    """Hard input error: the model cannot be assessed."""


@dataclass
class Issue:
    level: str        # ERROR | WARNING | INFO
    code: str
    message: str
    #: The input this is about, as a dotted path, where the check knows it. The GUI turns it into a "go to
    #: this field" button; `options` become one-click fixes. Both optional: a check that cannot name one
    #: input - a sum that does not add up, a combination that is wrong as a whole - leaves them empty
    #: rather than pointing somewhere misleading.
    field: str | None = None
    options: list | None = None

    def __str__(self):
        return f"[{self.level}] {self.code}: {self.message}"


TANK_METHODS = ("akin_propellant_mass", "akin_volume", "pressure_vessel", "mass_fraction", "user_mass")

#: Every casing-mass method validate_spec accepts: the book's four, plus the published stage-level
#: regressions of solid_inert (R18). Kept here rather than spelled out so a relation added to that
#: module becomes selectable without a second edit - and so the GUI dropdown and this check cannot drift.
from . import solid_inert as _solid_inert                    # noqa: E402
from . import solid_motor as sm                              # noqa: E402
CASING_METHODS = ("book_steel", "book_composite", "mass_fraction", "user_mass") + tuple(_solid_inert.RELATIONS)

#: Engine mass methods. `mer_calibrated` applies the R20 correction factor measured in engine_db.mer_check().
ENGINE_MASS_METHODS = ("mer", "mer_calibrated", "user")


def _db_hint(engine, field) -> str:
    """Say so when a value is missing because the engine-database row genuinely does not have it."""
    if getattr(engine, "db_entry", None):
        return (f" (the database entry '{engine.db_entry}' does not give {field}, and the tool does not invent "
                f"one)")
    return ""


def _cycle_band(cycle):
    try:
        from .engine_db import cycle_pressure_band_Pa
        return cycle_pressure_band_Pa(cycle)
    except Exception:                       # a missing or unreadable database must not break validation
        return None


def _num(v) -> str:
    """Format a database value for a message. Engine rows carry propellant NAMES as well as numbers."""
    try:
        return f"{float(v):,.4g}"
    except (TypeError, ValueError):
        return f"'{v}'"


#: Tank mass methods that actually read the tank material. The others are mass-estimating relationships in
#: the propellant mass or the tank volume, and the material they are paired with changes nothing.
MATERIAL_AWARE_TANK_METHODS = ("pressure_vessel",)


def _check_tank_material_is_used(spec, out: list, W) -> None:
    """Say so when a stage names a tank material that its own mass method ignores.

    Choosing stainless over aluminium and watching the lift-off mass move by 0.004 % looks like a broken
    tool. It is not: `akin_propellant_mass` and the other relationships are fitted to flown tanks and are
    functions of propellant mass or tank volume alone, so the material never enters. Only `pressure_vessel`
    sizes a wall from the material's allowable stress and density. Nothing here is wrong enough to refuse,
    but a user comparing materials needs to be told which of the two situations they are in.
    """
    guilty = []
    for st in spec.stages:
        tk = getattr(st, "tank", None)
        if st.is_solid or tk is None:
            continue
        mm = getattr(tk, "mass_method", None)
        methods = set(mm.values()) if isinstance(mm, dict) else ({mm} if mm else set())
        if methods and not (methods & set(MATERIAL_AWARE_TANK_METHODS)):
            guilty.append((st.index, getattr(getattr(tk, "material", None), "name", "?"),
                           ", ".join(sorted(methods))))
    if not guilty:
        return
    where = "; ".join(f"stage {i} ({mat}, {meth})" for i, mat, meth in guilty)
    # This warning already says exactly what to change, so it may as well change it. It is the one almost
    # every design carries, and "set the tank mass method to pressure_vessel on those stages" is six clicks
    # through a folded section for someone comparing materials - which is precisely the user this warning
    # exists for. One option per tank role per guilty stage, so the Checks tab can offer them as buttons.
    first = guilty[0][0]
    opts = []
    for i, _mat, _meth in guilty:
        for role in ("fuel", "oxidizer"):
            opts.append({"label": f"Size stage {i}'s {role} tank from the material",
                         "path": f"stages[{i - 1}].tank.mass_method_{role}", "value": "pressure_vessel",
                         "note": "the pressure-vessel method sizes the wall from this material's allowable "
                                 "stress and density, so the material choice then changes the mass"})
    W("MATUNUSED",
      f"the tank material is not used by the tank mass method on {where}. Those methods are relationships "
      f"fitted to flown tanks, in propellant mass or tank volume, so changing the material will not change "
      f"the mass. Set the tank mass method to 'pressure_vessel' on those stages to size the wall from this "
      f"material's allowable stress and density. The material is still used by the shell stress and "
      f"buckling study, which reads it directly.",
      field=f"stages[{first - 1}].tank.mass_method_fuel", options=opts[:6])


def _check_tank_method_inputs(spec, out: list, E) -> None:
    """A tank mass method whose own input is missing must not quietly size the tank at zero.

    `user_mass` and `mass_fraction` each need a number the user supplies. Both default to 0.0, so selecting
    one without filling it in produced a tank of no mass at all - a vehicle several percent light, with
    nothing said. The methods are selectable in the GUI, so this is reachable in two clicks.
    """
    for st in spec.stages:
        tk = getattr(st, "tank", None)
        if st.is_solid or tk is None:
            continue
        mm = getattr(tk, "mass_method", None) or {}
        for role, method in (mm.items() if isinstance(mm, dict) else ()):
            prop_name = st.fuel if role == "fuel" else st.oxidizer
            ps = (getattr(spec, "propellants", None) or {}).get(prop_name)
            here = f"stages[{st.index - 1}].tank.mass_method_{role}"
            ways = [{"label": f"Size stage {st.index}'s {role} tank by volume (Table 8.7)", "path": here,
                     "value": "akin_volume", "note": "the volume relation needs no coefficient for this propellant"},
                    {"label": f"Size stage {st.index}'s {role} tank as a pressure vessel", "path": here,
                     "value": "pressure_vessel",
                     "note": "the wall is sized from the tank pressure and the material's allowable stress"}]
            if method == "akin_propellant_mass" and ps is not None:
                if getattr(ps, "tank_mer_per_kg", None) is None:
                    E("TANKMER",
                      f"stage {st.index}: the propellant-mass tank relation (Table 8.6) has no coefficient for "
                      f"{prop_name}, so the {role} tank cannot be sized by it. The propellant library carries "
                      f"one for {', '.join(sorted(n for n, q in spec.propellants.items() if getattr(q, 'tank_mer_per_kg', None) is not None))} only.",
                      field=here, options=ways)
                elif getattr(ps, "tank_mer_ref_density", None):
                    dev = abs(ps.density_kg_m3 - ps.tank_mer_ref_density) / ps.tank_mer_ref_density
                    tol = ((getattr(spec, "mer", None) or {}).get("tank_mer_density_tolerance")
                           if isinstance(getattr(spec, "mer", None), dict) else None)
                    if tol is not None and dev > tol:
                        E("TANKMER",
                          f"stage {st.index}: the density of {prop_name} is {dev:.0%} away from the density the "
                          f"propellant-mass tank relation (Table 8.6) was fitted at, so it does not apply to the "
                          f"{role} tank.", field=here, options=ways)
            if method == "user_mass" and not (tk.user_mass_kg or {}).get(role):
                E("TANKUSER",
                  f"stage {st.index} sizes its {role} tank by 'user_mass' but no mass is given, which would "
                  f"make that tank weigh nothing. Type a mass in tank.user_mass_{role}_kg, or choose "
                  f"another tank mass method.", field=f"stages[{st.index - 1}].tank.user_mass_{role}_kg")
            if method == "mass_fraction" and not (tk.mass_fraction or {}).get(role):
                E("TANKFRAC",
                  f"stage {st.index} sizes its {role} tank by 'mass_fraction' but the fraction is zero, "
                  f"which would make that tank weigh nothing. Set tank.mass_fraction_{role}, or choose "
                  f"another tank mass method.", field=f"stages[{st.index - 1}].tank.mass_fraction_{role}")


def _check_launch_site(spec, out: list, W) -> None:
    """Record the named launch site in the report, and say what its latitude allows.

    The GUI enforces the inclination floor as the user picks a site, but a design run from the command line
    gets no such help, and the report is where a reader checks what the run assumed. So: one INFO line naming
    the site, its floor and the azimuth the mission actually needs - and a WARNING if the design's own latitude
    disagrees with the site it claims to fly from, which is a copy-paste mistake nothing else would catch.
    """
    note = getattr(spec, "launch_site_note", None)
    if not note:
        return
    from .launch_sites import inclination_check
    # the latitude IN FORCE, which is the design's own whenever it states one - never the library's, or the
    # line would quote a latitude the run did not use
    lat = spec.mission["site_latitude_deg"]
    chk = inclination_check(spec.mission["inclination_deg"], lat)
    where = f"{note['entry']}" + (f" ({note['country']})" if note.get("country") else "")
    out.append(Issue("INFO", "SITE",
                     f"launch site: {where}, flown at latitude {abs(lat):.4f} deg. "
                     + chk["note"].rstrip(". ") + ". Source: " + (note.get("source") or "launch site library")))
    mm = note.get("mismatch")
    if mm:
        W("SITELAT",
          f"the design flies from {note['entry']}, whose latitude is {mm['library']:.4f} deg, but states "
          f"{mm['design']:.4f} deg - a difference of {abs(mm['delta_deg']):.4f} deg. The design's own value "
          f"has been used, as it always is; check which of the two is the one you meant")


def validate_spec(spec) -> list:
    """Raise InputError on invalid/missing inputs; return list of WARNING issues."""
    errs, warns = [], []
    def E(c, m, field=None, options=None): errs.append(Issue("ERROR", c, m, field or infer_field(c, m), options))
    def W(c, m, field=None, options=None): warns.append(Issue("WARNING", c, m, field or infer_field(c, m), options))
    N = len(spec.stages)
    if N < 1:
        E("NSTAGE", "at least one stage is required")
    if spec.payload_mass_kg <= 0:
        E("PAYLOAD", "payload mass must be positive", field="mission.payload_mass_kg")
    if spec.mission["orbit_type"] not in ("LEO", "SSO", "GTO", "GEO_VIA_GTO", "GEO_DIRECT", "CUSTOM"):
        E("ORBIT", f"unsupported orbit type {spec.mission['orbit_type']}")
    if spec.mission["site_altitude_m"]:
        W("SITEALT", "launch-site altitude is recorded but not used by the v1 performance model")
    _check_launch_site(spec, warns, W)
    _check_tank_material_is_used(spec, warns, W)
    _check_tank_method_inputs(spec, errs, E)
    if spec.dv_mode not in ("fractions", "fixed"):
        E("DVMODE", "dv_allocation_mode must be 'fractions' or 'fixed'")
    f = spec.fairing
    if not 2 <= f.jettison_stage <= N + 1:
        E("FAIRJET", "fairing jettison stage must be 2..N (jettisoned at start of that stage's burn) or N+1 (carried to burnout, conservative)", field="fairing.jettison_at_stage_start", options=[{"label": f"Jettison at the start of stage {min(max(int(f.jettison_stage), 2), N + 1)}", "path": "fairing.jettison_at_stage_start", "value": min(max(int(f.jettison_stage), 2), N + 1), "note": f"the nearest legal stage for a {N}-stage vehicle"}])
    if N and f.diameter_m < spec.stages[-1].diameter_m - 1e-9:
        E("FAIRDIA", "the fairing is narrower than the uppermost stage: a reducing transition is not modelled",
          field="fairing.diameter_m",
          options=[{"label": f"Widen the fairing to {spec.stages[-1].diameter_m:.2f} m",
                    "path": "fairing.diameter_m", "value": round(spec.stages[-1].diameter_m, 3),
                    "note": "matches the stage it sits on, which is the narrowest a fairing may be. A wider "
                            "fairing is fine too - the model adds a conical forward adapter for it"},
                   {"label": f"Or narrow the upper stage to {f.diameter_m:.2f} m",
                    "path": f"stages[{N - 1}].diameter_m", "value": round(f.diameter_m, 3),
                    "note": "the other way to close the step. Changing the upper stage's diameter also "
                            "changes its tanks, so expect the mass to move"}])
    if N and f.diameter_m > spec.stages[-1].diameter_m + 1e-9:
        W("FAIRDIA", f"fairing diameter {f.diameter_m:.2f} m exceeds the upper stage ({spec.stages[-1].diameter_m:.2f} m): "
                     f"a conical forward adapter is added to the upper stage (book Fig. 8.15, p.490)")
    if f.envelope_diameter_m + 2 * f.radial_clearance_m > f.diameter_m:
        need = f.envelope_diameter_m + 2 * f.radial_clearance_m
        fits = f.diameter_m - 2 * f.radial_clearance_m
        opts = [{"label": f"Widen the fairing to {need:.2f} m",
                 "path": "fairing.diameter_m", "value": round(need + 5e-3, 3),
                 "note": f"the envelope is {f.envelope_diameter_m:.2f} m and needs "
                         f"{f.radial_clearance_m:.2f} m of clearance each side"}]
        if fits > 0:
            opts.append({"label": f"Or shrink the payload envelope to {fits:.2f} m",
                         "path": "mission.payload_envelope_diameter_m", "value": round(fits - 5e-3, 3),
                         "note": "the largest envelope this fairing can take at the current clearance"})
        opts.append({"label": "Or reduce the radial clearance", "path": "fairing.radial_clearance_m",
                     "note": "the gap between the payload and the fairing wall. It exists for a reason - "
                             "dynamic deflection and acoustic blankets - so shrink it knowingly"})
        E("FAIRFIT", f"payload envelope plus radial clearance ({need:.2f} m) does not fit inside the "
                     f"{f.diameter_m:.2f} m fairing", field="fairing.diameter_m", options=opts)
    if spec.paf_method not in ("mer", "fraction", "auto"):
        E("PAFMETH", "vehicle.payload_adapter_method must be mer, fraction or auto")
    if spec.mission.get("loss_model") not in ("book_penalty", "book_k1k2", "book_simple", "user"):
        E("LOSSMODEL", f"unknown loss model '{spec.mission.get('loss_model')}' "
                       "(book_penalty | book_k1k2 | book_simple | user)")
    if spec.mission.get("ascent_time_override_s"):
        W("ASCTIME", f"ascent time for the loss regression overridden to {spec.mission['ascent_time_override_s']:.0f} s "
                     "instead of the sum of the sized burn times (use only when a stage burns after a long coast)")
    al = spec.mission.get("air_launch")
    if al:
        if spec.mission.get("loss_model") != "user":
            E("AIRLAUNCH", "air-launched vehicles must use loss_model 'user': the book's loss regression "
                           "(Eq. 3:37) was fitted to ground launches")
        for k in ("release_speed_mps", "release_altitude_m"):
            if al.get(k) is None: E("AIRLAUNCH", f"mission.air_launch needs {k}")
        W("AIRLAUNCH", "air launch: only the horizontal component of the release speed is credited; the altitude "
                       "and flight-path-angle benefits must be reflected in the user loss estimates")
    for st in spec.stages:
        p = f"stage {st.index}"
        if st.stage_type not in ("liquid", "solid"):
            E("STAGETYPE", f"{p}: stage_type must be 'liquid' or 'solid'")
        if st.diameter_m <= 0: E("DIAM", f"{p}: diameter must be positive")
        if not (0 <= st.residual_fraction < 0.5): E("RESID", f"{p}: residual fraction out of range")
        if not (0 <= st.loading_margin_fraction < 0.5): E("LMARG", f"{p}: loading margin out of range")
        if st.is_solid:
            warns.extend(_check_solid_stage(st, spec, E, W))
            continue
        e = st.engine
        if st.of_ratio <= 0: E("OF", f"{p}: mixture ratio must be positive")
        for pn in (st.fuel, st.oxidizer):
            if pn not in spec.propellants: E("PROP", f"{p}: propellant '{pn}' not in the property library")
        if (e.thrust_vac_per_engine_N is None) == (e.tw_ignition is None):
            E("THRUST", f"{p}: specify exactly one of thrust_vac_per_engine_N or thrust_to_weight_ignition")
        if e.geometry_method not in ("user", "book_mer"): E("ENGGEO", f"{p}: unknown engine geometry_method")
        if e.geometry_method == "book_mer" and not e.cstar_mps:
            ix = st.index - 1
            opts = []
            combo = next((c for c in (getattr(spec, "propellant_combinations", None) or {}).values()
                          if getattr(c, "fuel", None) == st.fuel and getattr(c, "oxidizer", None) == st.oxidizer
                          and getattr(c, "cstar_ref_mps", None)), None)
            if combo is not None:
                opts.append({"label": f"Use the library's c* for {st.oxidizer}/{st.fuel}: {combo.cstar_ref_mps:,.0f} m/s",
                             "path": f"stages[{ix}].engine.cstar_mps", "value": float(combo.cstar_ref_mps),
                             "note": "the propellant combination table's reference value, which is theoretical "
                                     "rather than a delivered one; replace it with the engine's own if you have it"})
            opts.append({"label": "Give the engine length and exit diameter myself instead",
                         "path": f"stages[{ix}].engine.geometry_method", "value": "user",
                         "note": "the dimensions are then read from the two fields under this choice"})
            E("ENGGEO", f"{p}: sizing the engine from the book relations needs a characteristic velocity c* "
                        f"(engine.cstar_mps, Table 8.12), and this stage has none",
              field=f"stages[{ix}].engine.cstar_mps", options=opts)
        if e.isp_vac_s <= 0: E("ISP", f"{p}: vacuum Isp must be positive")
        if e.isp_sl_s is not None and e.isp_sl_s > e.isp_vac_s:
            why, where = "", "isp_vac_s"
            if getattr(e, "db_entry", None):
                try:
                    from . import engine_db as _db
                    row = _db.find(e.db_entry)
                except Exception:                                    # noqa: BLE001
                    row = {}
                if row.get("isp_vac_s") is None and row.get("isp_sl_s") is not None:
                    why = (f". The database entry '{e.db_entry}' gives a sea-level figure and no vacuum one, so "
                           f"the vacuum Isp here is still the design's own from before the engine was picked: "
                           f"type the engine's vacuum Isp")
                elif row.get("isp_sl_s") is None and row.get("isp_vac_s") is not None:
                    why, where = (f". The database entry '{e.db_entry}' gives a vacuum figure and no sea-level "
                                  f"one, so the sea-level Isp here is still the design's own: type the engine's, "
                                  f"or size the stage on vacuum Isp"), "isp_sl_s"
            E("ISP", f"{p}: sea-level Isp {e.isp_sl_s:.0f} s exceeds vacuum Isp {e.isp_vac_s:.0f} s{why}",
              field=f"stages[{st.index - 1}].engine.{where}")
        if e.isp_mode == "weighted" and e.isp_sl_s is None: E("ISP", f"{p}: weighted Isp needs isp_sl_s")
        if e.isp_mode == "user" and not e.isp_user_s: E("ISP", f"{p}: user effective Isp missing")
        if e.isp_mode not in ("vacuum", "weighted", "user"): E("ISP", f"{p}: unknown isp_effective_mode")
        if e.isp_mode == "vacuum" and st.index == 1 and e.isp_sl_s is not None:
            W("ISPVAC", f"{p}: vacuum Isp is used for the whole burn of a stage that lifts off in the atmosphere - optimistic")
        if e.n_engines < 1: E("NENG", f"{p}: n_engines must be >= 1")
        if e.mass_method == "user" and e.mass_user_kg is None: E("ENGMASS", f"{p}: user engine mass missing")
        if e.mass_method not in ENGINE_MASS_METHODS:
            E("ENGMASS", f"{p}: unknown engine mass_method '{e.mass_method}'; expected one of "
                         f"{', '.join(ENGINE_MASS_METHODS)}")
        if e.mass_method == "mer_calibrated":
            W("ENGCAL", f"{p}: the engine mass relation is being scaled by a factor measured against 16 real "
                        f"engines (R20). It removes the book relation's median 24 % under-prediction for an "
                        f"ordinary engine, but over-predicts an exceptionally light one such as the Merlin 1D")
        if e.mass_method in ("mer", "mer_calibrated") and not (e.expansion_ratio and e.expansion_ratio > 1):
            E("EPS", f"{p}: expansion ratio must exceed 1" + _db_hint(e, "expansion_ratio"))
        if e.gimbal_method == "mer" and not e.chamber_pressure_Pa:
            E("GIMB", f"{p}: the gimbal MER (Table 8.9) needs a chamber pressure" + _db_hint(e, "chamber_pressure_Pa")
                      + "; give one in the design file or set gimbal_method to 'none'")
        if e.cycle and e.chamber_pressure_Pa:
            band = _cycle_band(e.cycle)
            if band and not (band[0] <= e.chamber_pressure_Pa <= band[1]):
                W("CYCLEPC", f"{p}: chamber pressure {e.chamber_pressure_Pa/1e5:.0f} bar is outside the "
                             f"{band[0]/1e5:.0f}-{band[1]/1e5:.0f} bar band that {e.cycle.replace('_', ' ')} "
                             f"engines normally fly at - check the cycle or the pressure")
        if e.db_entry:
            W("ENGDB", f"{p}: engine data filled from the database entry '{e.db_entry}'. These are public "
                       f"figures, not book data, and not verified beyond the cited source")
        if st.structure_mode not in ("bottom_up", "aggregate_s"): E("STRUCT", f"{p}: unknown structure_mode")
        if st.structure_mode == "aggregate_s" and not (st.structural_factor_s and 0 < st.structural_factor_s < 1):
            E("STRUCT", f"{p}: aggregate_s mode needs 0 < structural_factor_s < 1")
        if st.tank.arrangement not in ("separate", "common_bulkhead"): E("TANKARR", f"{p}: unknown tank arrangement")

        if st.tank.dome_AR < 1: E("DOME", f"{p}: dome aspect ratio must be >= 1")
        for role in ("fuel", "oxidizer"):
            m = st.tank.mass_method[role]
            if m not in TANK_METHODS: E("TANKM", f"{p}: unknown tank mass method {m}")
            if m == "pressure_vessel" and st.tank.pressure_Pa[role] <= 0: E("TANKP", f"{p}: pressure_vessel needs tank pressure for {role}")
            if m == "mass_fraction" and st.tank.mass_fraction[role] <= 0: E("TANKF", f"{p}: mass_fraction method needs a fraction")
        if e.exit_diameter_m <= 0 or e.length_m <= 0: E("ENGDIM", f"{p}: engine length/exit diameter must be positive")
        if not (0 <= e.embed_fraction <= 1): E("EMBED", f"{p}: embed fraction must be in [0,1]")
        if st.structure_mode == "aggregate_s":
            W("AGG", f"{p}: aggregate_s mode: component masses are NOT computed; inert mass is smeared in the mass properties")
    if spec.dv_mode == "fractions" and (not spec.dv_fractions or len(spec.dv_fractions) != N):
        E("DVFRAC", "dv_fractions must have one entry per stage", field="vehicle.dv_fractions")
    if spec.dv_mode == "fixed" and (not spec.dv_fixed or len(spec.dv_fixed) != N):
        E("DVFIX", "dv_fixed_mps must have one entry per stage", field="vehicle.dv_fixed_mps")
    if getattr(spec, "optimise_dv", False):
        # Caught here rather than at the optimiser, because a design that asks for an objective the tool
        # cannot compute should say so when it is checked, not after a search has already run.
        if spec.optimise_objective not in ("glom", "cost", "payload"):
            E("OPTOBJ", f"vehicle.optimise_objective must be glom, cost or payload, "
                        f"not {spec.optimise_objective!r}")
        if N < 2:
            W("OPTONE", "optimise_dv_split is on, but a single-stage vehicle has no allocation to optimise")
        if spec.dv_mode != "fractions":
            W("OPTMODE", "optimise_dv_split only applies to the 'fractions' allocation mode; with fixed "
                         "per-stage delta-v the split is already decided and will be used as written")
    # a design that names a real engine and then keeps a different Isp, thrust or propellant is nearly always a
    # template that
    # was only half-edited; the database never overrides the design file, so this has to be said out loud
    for note in getattr(spec, "engine_db_notes", []) or []:
        for ov in note.get("overridden") or []:
            W("ENGDBOVR", f"{note['context']}: '{note['entry']}' gives {ov['field']} = {_num(ov['database'])}, but "
                          f"the design keeps its own {_num(ov['design'])}. The database never overrides a value "
                          f"you wrote - delete the line to use the real engine's figure")
        for sk in note.get("skipped") or []:
            W("ENGDBSKIP", f"{note['context']}: '{note['entry']}' gives {sk['field']} = {_num(sk['database'])}, "
                           f"not applied because {sk['why']}")
        if note.get("missing"):
            W("ENGDBMISS", f"{note['context']}: the entry '{note['entry']}' does not supply "
                           f"{', '.join(note['missing'])}; those keep whatever the design file says")
    # the same rule for a named propellant combination: it fills what is absent and never overrides, so a stage
    # that names LOX/RP-1 and then declares LH2 has to be told about rather than quietly sized on the mixture
    for note in getattr(spec, "propellant_combination_notes", []) or []:
        for mm in note.get("mismatched") or []:
            W("COMBOMM", f"{note['context']}: combination '{note['entry']}' is {mm['combination']} for "
                         f"{mm['field']}, but the stage declares '{mm['design']}'. The stage wins, so this "
                         f"vehicle is sized on one propellant's density and another's mixture ratio")
        if note.get("missing"):
            W("COMBOMISS", f"{note['context']}: combination '{note['entry']}' supplies no "
                           f"{', '.join(note['missing'])}; those keep whatever the design file says")
    if spec.boosters:
        _check_boosters(spec, E, W)
    if errs:
        # Carry the first error that knows which input it is about, so the GUI can offer a jump and any
        # one-click fixes. Validation used to raise a bare sentence, which meant this whole class of error -
        # the fairing too narrow, the envelope that does not fit, a split that is not a partition - pointed
        # nowhere, while the geometry and sizing errors had pointed at their field for several versions.
        named = next((e for e in errs if e.field), None)
        ex = InputError("; ".join(str(e) for e in errs))
        ex.field = named.field if named else None
        # every way out the errors offer, not only the first error's: a stage whose fuel AND oxidiser tank both
        # need another method must get a button for each, or fixing one just produces the same refusal again
        ways, seen = [], set()
        for e in errs:
            for o in (e.options or []):
                key = (o.get("path"), repr(o.get("value")), o.get("label"))
                if key not in seen:
                    seen.add(key)
                    ways.append(o)
        ex.options = ways[:8] or None
        ex.issues = list(errs)
        raise ex
    return warns


def _check_solid_stage(st, spec, E, W) -> list:
    """Input checks specific to a serial solid stage (book Sec. 8.5)."""
    p = f"stage {st.index} (solid)"
    out = []
    mo = st.motor
    if mo is None:
        E("MOTOR", f"{p}: a solid stage needs a 'motor' block")
        return out
    if st.propellant not in spec.solid_propellants:
        E("SOLIDPROP", f"{p}: solid propellant '{st.propellant}' is not in the solid-propellant library")
    if mo.n_motors != 1:
        E("NMOTOR", f"{p}: a serial solid stage must have exactly one casing (use strap-on boosters for clusters)")
    if mo.thrust_mode not in ("tw_ignition", "fixed_thrust", "burn_time"):
        E("SOLIDTHRUST", f"{p}: thrust_mode must be tw_ignition, fixed_thrust or burn_time")
    given = {"tw_ignition": mo.tw_ignition, "fixed_thrust": mo.thrust_vac_total_N, "burn_time": mo.burn_time_s}
    if mo.thrust_mode in given and not given[mo.thrust_mode]:
        E("SOLIDTHRUST", f"{p}: thrust_mode '{mo.thrust_mode}' needs the matching input to be set")
    if mo.casing_mass_method not in CASING_METHODS:
        E("CASING", f"{p}: unknown casing_mass_method '{mo.casing_mass_method}'; expected one of "
                    f"{', '.join(CASING_METHODS)}")
    elif sm.is_stage_level(mo.casing_mass_method):
        rel = _solid_inert.get(mo.casing_mass_method)
        W("CASESTAGE", f"{p}: '{mo.casing_mass_method}' predicts the WHOLE STAGE inert mass, so skirts, "
                       f"interstage, avionics and wiring are NOT added separately - they are inside it. "
                       f"Published scatter {100 * rel.scatter:.0f}%")
        if not rel.in_range(st.m_prop_loaded_kg if hasattr(st, "m_prop_loaded_kg") else 0.0):
            pass                                  # the propellant load is not known at validation time
        if getattr(st, "inert_margin_fraction", 0.0) > 1e-9:
            W("CASEMARGIN", f"{p}: a {100 * st.inert_margin_fraction:.0f}% mass growth margin sits on top of a "
                            f"relation fitted to stages that have already flown; consider setting "
                            f"inert_mass_margin_fraction to 0 with a published relation")
    # Naming a real motor and then not using its mass is the quietest way to get a wrong answer here, and
    # it happens by default: the engine database fills casing_mass_fraction from the motor's own published
    # inert/propellant ratio, but a stage that already states a book_* method keeps that method, and the
    # real figure sits in the file doing nothing. On a Star 31 that is 148 kg of book motor against 98 kg
    # of real motor - 51% heavy on a stage whose whole point was to be real hardware.
    if getattr(mo, "db_entry", None) and mo.casing_mass_fraction and mo.casing_mass_method.startswith("book_"):
        from .solid_motor import K_SRM
        k_book = K_SRM["steel"] if mo.casing_mass_method == "book_steel" else K_SRM["composite"]
        W("CASEDB", f"{p}: the motor is '{mo.db_entry}', whose published inert/propellant ratio is "
                    f"{mo.casing_mass_fraction:.4f}, but casing_mass_method is '{mo.casing_mass_method}', "
                    f"which uses k = {k_book:.4f} instead - "
                    f"{abs(k_book / mo.casing_mass_fraction - 1) * 100:.0f}% "
                    f"{'heavier' if k_book > mo.casing_mass_fraction else 'lighter'} than the real motor. "
                    f"Set casing_mass_method to 'mass_fraction' to use the hardware's own mass, or clear "
                    f"from_database if a generic motor was meant")
    # Say which of the two worlds this stage is in, because a trade between a real motor and a notional one
    # is only readable if each stage declares which it is.
    if getattr(mo, "db_entry", None) and mo.casing_mass_method == "mass_fraction":
        out.append(Issue("INFO", "CASEDB",
                         f"{p}: real motor '{mo.db_entry}', using its own published inert/propellant ratio "
                         f"{mo.casing_mass_fraction:.4f} rather than a generic relation"))
    elif mo.casing_mass_method.startswith("book_") and not getattr(mo, "db_entry", None):
        out.append(Issue("INFO", "CASEGEN",
                         f"{p}: notional motor sized by {mo.casing_mass_method} (book Eq. 8:18). Measured "
                         f"against 55 real motors this constant runs about 26-51% high above 200 kg of "
                         f"propellant and about 36% low below 100 kg; 'star_motor' is the size-dependent "
                         f"alternative for an upper-stage-class motor"))
    if mo.casing_volume_factor < 1.0:
        E("CASEVOL", f"{p}: casing_volume_factor must be >= 1 (book Eq. 8:24 uses 1.12)")
    if mo.dome_AR < 1.0:
        E("DOME", f"{p}: dome aspect ratio must be >= 1")
    if mo.dome_AR > 1.0 + 1e-9:
        W("DOME", f"{p}: the book recommends hemispherical domes (AR = 1) for solid motors because of the high internal pressure")
    if mo.isp_vac_s <= 0:
        E("ISP", f"{p}: vacuum Isp must be positive")
    if mo.isp_mode == "weighted" and mo.isp_sl_s is None:
        E("ISP", f"{p}: weighted Isp needs isp_sl_s")
    if mo.nozzle_geometry_method not in ("user", "book_mer"):
        E("NOZGEO", f"{p}: unknown nozzle_geometry_method")
    if mo.nozzle_geometry_method == "book_mer" and not mo.cstar_mps:
        E("NOZGEO", f"{p}: nozzle geometry 'book_mer' needs cstar_mps")
    if mo.nozzle_geometry_method == "user" and (not mo.nozzle_length_m or not mo.exit_diameter_m):
        E("NOZGEO", f"{p}: nozzle geometry 'user' needs nozzle_length_m and exit_diameter_m")
    if st.startup_time_s:
        W("SOLIDSTART", f"{p}: the book assumes instantaneous SRM ignition (no start-up propellant); "
                        f"startup_time_s = {st.startup_time_s} s is being charged anyway")
    if st.residual_fraction > 0:
        W("SOLIDRESID", f"{p}: the book's SRM sizing assumes no residual propellant; {st.residual_fraction:.1%} "
                        "is being carried as slivers/slag (more conservative)")
    return out


def _check_boosters(spec, E, W) -> None:
    b = spec.boosters
    if b.attach_stage != 1:
        E("BOOSTSTAGE", "strap-on boosters must be attached to stage 1 in this version", field="boosters.attach_stage", options=[{"label": "Attach them to stage 1", "path": "boosters.attach_stage", "value": 1, "note": "the only stage this version models strap-ons on"}])
    if b.kind not in ("solid", "liquid"):
        E("BOOSTKIND", "booster type must be 'solid' or 'liquid'", field="boosters.type")
    if b.n_total < 1:
        E("BOOSTN", "n_total must be >= 1")
    if not 0 <= b.n_ground_lit <= b.n_total:
        E("BOOSTN", "n_ground_lit must be between 0 and n_total")
    if b.n_ground_lit == 0:
        E("BOOSTN", "at least one booster group must be ground-lit (air-lit-only sets are not modelled)")
    if b.n_ground_lit < b.n_total:
        W("BOOSTAIR", f"{b.n_total - b.n_ground_lit} air-lit boosters are assumed to ignite exactly when the "
                      "ground-lit group burns out")
    if b.kind == "solid" and b.propellant not in spec.solid_propellants:
        E("BOOSTPROP", f"booster propellant '{b.propellant}' is not in the solid-propellant library")
    if b.kind == "liquid":
        if not (b.fuel in spec.propellants and b.oxidizer in spec.propellants and b.of_ratio):
            E("BOOSTPROP", "a liquid booster needs fuel, oxidizer and mixture_ratio_OF from the propellant library")
        if b.inert_mass_method not in ("mass_fraction", "user_mass"):
            E("BOOSTINERT", "a liquid booster needs inert_mass_method 'mass_fraction' or 'user_mass'")
    if b.prop_mass_each_kg <= 0 or b.burn_time_s <= 0:
        E("BOOSTMASS", "booster propellant mass and burn time must be positive")
    if b.inert_mass_method == "user_mass" and b.inert_mass_each_kg is None:
        E("BOOSTINERT", "inert_mass_method 'user_mass' needs inert_mass_each_kg")
    if b.diameter_m <= 0:
        E("BOOSTDIA", "booster diameter must be positive")
    if spec.stages[0].is_solid and spec.stages[0].motor.thrust_mode == "burn_time":
        W("BOOSTCORE", "core stage uses a fixed burn time: check that it still outlasts the strap-ons")


def check_result(res) -> list:
    """Post-sizing consistency checks and engineering warnings/infeasibility flags."""
    spec = res.spec
    iss = []
    c = spec.constraints
    N = len(res.stages)
    # mass closure
    sum_stage = sum(s.m_dry_kg + s.m_prop_loaded_kg for s in res.stages)
    glom_chk = sum_stage + res.payload_mass_kg + res.paf_mass_kg + res.fairing_mass_kg \
        + (res.boosters.m_total_kg if res.boosters else 0.0)
    if abs(glom_chk - res.glom_kg) > 1e-6 * res.glom_kg:
        iss.append(Issue("ERROR", "MASSCLOSE", f"mass accounting does not close: {glom_chk:.3f} vs {res.glom_kg:.3f} kg"))
    # delta-v
    if abs(res.dv_achieved_mps - res.dv_required_mps) > 0.01 and res.converged:
        iss.append(Issue("ERROR", "DVSUM", f"sum of stage delta-v {res.dv_achieved_mps:.2f} != requirement {res.dv_required_mps:.2f} m/s"))
    for s in res.stages:
        st = spec.stages[s.index - 1]
        if s.index == 1 and s.tw_ignition < c.get("min_tw_liftoff", 1.0):
            iss.append(Issue("ERROR", "TWLIFT", f"liftoff T/W {s.tw_ignition:.2f} below minimum {c.get('min_tw_liftoff')}"))
        if s.index > 1 and s.tw_ignition < c.get("min_tw_upper", 0.0):
            iss.append(Issue("WARNING", "TWUP", f"stage {s.index} ignition T/W {s.tw_ignition:.2f} is low: long burn, high gravity loss risk"))
        if s.accel_max_g > c.get("max_accel_g", 1e9):
            iss.append(Issue("WARNING", "ACCEL", f"stage {s.index} burnout acceleration {s.accel_max_g:.1f} g exceeds limit {c.get('max_accel_g')} g (throttling not modelled)"))
        env = s.envelope
        from .propulsion import cluster_fits
        # an upper-stage nozzle sits inside the interstage, so it may be wider than its own stage but not wider
        # than the stage below it
        d_allow = st.diameter_m if s.index == 1 else max(st.diameter_m, spec.stages[s.index - 2].diameter_m)
        if env and not cluster_fits(env.n, env.exit_diameter_m, d_allow):
            iss.append(Issue("ERROR", "ENGFIT", f"stage {s.index}: {env.n} engine(s) of exit diameter "
                                                f"{env.exit_diameter_m:.2f} m do not fit a single ring in {d_allow:.2f} m "
                                                f"({'stage diameter' if s.index == 1 else 'interstage diameter'})"))
        elif env and s.index > 1 and env.exit_diameter_m > st.diameter_m:
            iss.append(Issue("INFO", "ENGFIT", f"stage {s.index}: the nozzle exit ({env.exit_diameter_m:.2f} m) is wider than "
                                               f"the stage ({st.diameter_m:.2f} m) and is housed inside the interstage"))
        if s.is_solid and s.motor_info:
            r = s.motor_info["implied_burn_rate_mm_s"]
            if not 1.0 <= r <= 40.0:
                iss.append(Issue("WARNING", "BURNRATE", f"stage {s.index}: implied average burn rate {r:.1f} mm/s is outside the "
                                                        "usual 1-40 mm/s range for composite propellants (Eq. 4:32/4:33): "
                                                        "check the burn time, grain geometry or diameter"))
            if s.motor_info["bore_radius_m"] > 0.6 * 0.5 * st.diameter_m:
                iss.append(Issue("WARNING", "GRAINBORE", f"stage {s.index}: the grain bore is more than 60 % of the casing radius; "
                                                         "the web is thin and the single-bore grain model is marginal"))
        if st.max_length_m and s.length_m > st.max_length_m:
            iss.append(Issue("ERROR", "STAGELEN", f"stage {s.index} length {s.length_m:.2f} m exceeds limit {st.max_length_m} m"))
        if s.structural_factor_s > 0.25:
            iss.append(Issue("WARNING", "SFACT", f"stage {s.index}: structural factor {s.structural_factor_s:.3f} is high versus book Tables 5.1/5.2 range"))
        if s.structural_factor_s < 0.04:
            iss.append(Issue("WARNING", "SFACT", f"stage {s.index}: structural factor {s.structural_factor_s:.3f} is optimistic (below ~0.04)"))
        if s.burn_time_s > 1200:
            iss.append(Issue("WARNING", "BURN", f"stage {s.index}: burn time {s.burn_time_s:.0f} s unusually long"))
        for t in s.tanks:
            if abs(t.volume_check()) > 1e-6 * t.V_int:
                iss.append(Issue("ERROR", "TANKVOL", f"stage {s.index} {t.role} tank volume check failed"))
        iss.extend(Issue("WARNING", "STAGE", w) for w in s.warnings)
    g = res.geometry
    if g is not None and c.get("max_vehicle_length_m") and g.total_length > c["max_vehicle_length_m"]:
        iss.append(Issue("ERROR", "VEHLEN", f"vehicle length {g.total_length:.1f} m exceeds limit {c['max_vehicle_length_m']} m"))
    if res.boosters is not None:
        b, br = spec.boosters, res.boosters
        if br.m_inert_each_kg <= 0:
            iss.append(Issue("ERROR", "BOOSTINERT", "booster inert mass is not positive"))
        s1 = res.stages[b.attach_stage - 1]
        if s1.burn_time_s <= br.burn_time_s:
            iss.append(Issue("ERROR", "BOOSTBURN", f"the core stage burn time {s1.burn_time_s:.0f} s does not exceed the "
                                                   f"strap-on burn time {br.burn_time_s:.0f} s"))
        iss.append(Issue("INFO", "BOOSTPHASE", f"parallel burn: {br.n_total} x {br.name}, "
                                               f"{len([p for p in s1.phases if p.duration_s > 0])} powered phases, "
                                               f"mass-averaged Isp per phase (Eq. 5:66)"))
    for sr in res.stages:
        st = res.spec.stages[sr.index - 1]
        tk = getattr(st, "tank", None)
        if getattr(sr, "is_solid", False) or tk is None or tk.arrangement != "common_bulkhead":
            continue
        first = tk.order_bottom_to_top[0] if tk.order_bottom_to_top else "?"
        iss.append(Issue("INFO", "TANKORDER",
                         f"stage {sr.index}: a common bulkhead does not make the tank order irrelevant. It "
                         f"still decides which tank is aft - here the {first} tank - and therefore the mass "
                         f"distribution, the load panels and the centre-of-mass travel; it additionally "
                         f"decides which tank owns the shared dome. The book's own S-II example (p.633) "
                         f"moved the heavier tank forward and the pre-launch wind running load went from "
                         f"140.4 to 290.5 kN/m"))
    if g is not None:
        ld = g.total_length / g.max_diameter
        if ld > 25:
            iss.append(Issue("WARNING", "SLENDER", f"overall length/diameter {ld:.1f} is very slender - bending/control margins not assessed"))
    # payload-ratio sanity check (1st-ed. errata p.296 NOTE): "assignments in the past have claimed payload
    # ratios as high as 14%, in reality lucky to get 4%", usually caused by not carrying the whole loaded upper
    # step as the lower step's payload. This tool does carry it (tested), so a high ratio points at optimistic
    # structural factors, Isp values or loss estimates.
    pf = res.payload_mass_kg / res.glom_kg
    if pf > 0.06:
        iss.append(Issue("WARNING", "PAYFRAC", f"payload fraction {pf:.1%} of GLOM is high: real expendable launchers "
                                               "reach about 2-4 % (book errata p.296). Check the structural factors, "
                                               "Isp values and loss estimates before trusting it"))
    if spec.paf_method == "mer" and res.paf_mass_kg > 0.20 * res.payload_mass_kg:
        iss.append(Issue("WARNING", "PAFSMALL", f"the payload adapter is {res.paf_mass_kg/res.payload_mass_kg:.0%} of the "
                                                "payload mass: the Table 8.8 MER does not scale down well. The errata "
                                                "(p.443) recommends 0.15 m_PL for small payloads "
                                                "(vehicle.payload_adapter_method: fraction or auto)"))
    if not res.converged:
        iss.append(Issue("ERROR", "CONV", f"sizing did not converge: {res.status}"))
    iss.append(Issue("INFO", "FIDELITY", "Preliminary model. The sizing loop uses mass-estimating "
                     "relationships and a regression for the ascent losses, and that is the vehicle every mass "
                     "and dimension in this report describes. The optional studies - trajectory, loads, "
                     "structure, control, ascent optimisation, internal ballistics - are ANALYSES OF that "
                     "vehicle, run afterwards and reported separately. None of them feeds back into it: "
                     "structure is never re-sized to carry the loads it is shown to need, the vehicle is never "
                     "re-sized around a better ascent, and no casing is re-sized for the chamber pressure its "
                     "grain would reach. Without a trajectory, the achievability of the orbit is NOT "
                     "demonstrated; with one, it is demonstrated for the profile flown and no other."))
    return iss


# --------------------------------------------------------------------------- which input a message is about
#: check code -> the input to send the user to. "{s}" is the stage as the page spells it (stages[0]); a pair
#: is (liquid stage, solid stage). A check that names its own field keeps it; this is for the many that
#: raise a sentence and nothing else, which the page could then only print.
_CODE_FIELD = {
    "ORBIT": "mission.orbit.type", "SITEALT": "mission.launch_site.altitude_m",
    "SITELAT": "mission.launch_site.latitude_deg", "DVMODE": "vehicle.dv_allocation_mode",
    "PAFMETH": "vehicle.payload_adapter_method", "LOSSMODEL": "mission.losses.model",
    "ASCTIME": "mission.losses.ascent_time_override_s", "AIRLAUNCH": "mission.losses.model",
    "OPTOBJ": "vehicle.optimise_objective", "OPTONE": "vehicle.optimise_dv_split",
    "OPTMODE": "vehicle.optimise_dv_split", "ACCEL": "constraints.max_accel_g",
    "STAGETYPE": "{s}.stage_type", "DIAM": "{s}.diameter_m", "RESID": "{s}.residual_fraction",
    "LMARG": "{s}.loading_margin_fraction", "OF": "{s}.mixture_ratio_OF", "PROP": "{s}.fuel",
    "THRUST": "{s}.engine.thrust_to_weight_ignition", "ENGGEO": "{s}.engine.geometry_method",
    "ISP": ("{s}.engine.isp_vac_s", "{s}.motor.isp_vac_s"), "ISPVAC": "{s}.engine.isp_effective_mode",
    "ENGMASS": "{s}.engine.mass_method", "ENGCAL": "{s}.engine.mass_method",
    "EPS": "{s}.engine.expansion_ratio", "GIMB": "{s}.engine.chamber_pressure_Pa",
    "CYCLEPC": "{s}.engine.chamber_pressure_Pa", "ENGDB": "{s}.engine.from_database",
    "ENGDBOVR": ("{s}.engine.from_database", "{s}.motor.from_database"),
    "ENGDBSKIP": ("{s}.engine.from_database", "{s}.motor.from_database"),
    "ENGDBMISS": ("{s}.engine.from_database", "{s}.motor.from_database"),
    "COMBOMM": "{s}.propellant_combination", "COMBOMISS": "{s}.propellant_combination",
    "STRUCT": "{s}.structural_factor_s", "AGG": "{s}.structure_mode",
    "SOLIDPROP": "{s}.propellant", "SOLIDTHRUST": "{s}.motor.thrust_mode",
    "CASING": "{s}.motor.casing_mass_method", "CASESTAGE": "{s}.motor.casing_mass_method",
    "CASEDB": "{s}.motor.casing_mass_method", "CASEMARGIN": "{s}.inert_mass_margin_fraction",
    "CASEVOL": "{s}.motor.casing_volume_factor", "DOME": "{s}.motor.dome_aspect_ratio",
    "NOZGEO": "{s}.motor.nozzle_geometry_method", "SOLIDSTART": "{s}.startup_time_s",
    "SOLIDRESID": "{s}.residual_fraction",
    "BOOSTN": "boosters.n_total", "BOOSTAIR": "boosters.n_ground_lit", "BOOSTPROP": "boosters.propellant",
    "BOOSTINERT": "boosters.inert_mass_method", "BOOSTMASS": "boosters.propellant_mass_each_kg",
    "BOOSTDIA": "boosters.diameter_m",
}
#: for errors raised outside validation as a bare sentence: a key or phrase in the text -> the input
_TEXT_FIELD = (
    ("cstar_mps", "{s}.engine.cstar_mps"), ("geometry_method", "{s}.engine.geometry_method"),
    ("chamber pressure", "{s}.engine.chamber_pressure_Pa"), ("expansion ratio", "{s}.engine.expansion_ratio"),
    ("structural_factor_s", "{s}.structural_factor_s"), ("casing_mass_fraction", "{s}.motor.casing_mass_fraction"),
    ("casing_mass_kg", "{s}.motor.casing_mass_kg"), ("ascent_time_override_s", "mission.losses.ascent_time_override_s"),
    ("gust_increment_mps", "mission.wind.gust_increment_mps"),
)
_STAGE_ONE_BASED = re.compile(r"\bstage (\d+)")
_STAGE_ZERO_BASED = re.compile(r"\bstages[.\[](\d+)")


def infer_field(code, message: str):
    """The input a check or an error is about, as the page's path, or None when it is about no single one."""
    msg = str(message or "")
    tmpl = _CODE_FIELD.get(code) if code else None
    if tmpl is None:
        low = msg.lower()
        tmpl = next((t for key, t in _TEXT_FIELD if key in low), None)
    if tmpl is None:
        return None
    if isinstance(tmpl, tuple):
        tmpl = tmpl[1] if ("(solid)" in msg or ".motor" in msg) else tmpl[0]
    if "{s}" not in tmpl:
        return tmpl
    z = _STAGE_ZERO_BASED.search(msg)
    o = _STAGE_ONE_BASED.search(msg)
    if z:
        i = int(z.group(1))
    elif o:
        i = int(o.group(1)) - 1
    else:
        return None
    return tmpl.replace("{s}", f"stages[{i}]") if i >= 0 else None
