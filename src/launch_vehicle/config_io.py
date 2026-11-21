"""Strict, annotated configuration loader.

Every input leaf in a YAML design file must be a mapping with the keys
    v : value        u : units        d : description        s : source / justification
    t : provenance, one of  user | reference | assumed
Any bare scalar input raises ConfigError, so no input can be undocumented. The loader records every leaf in an
'inputs register' (path, value, units, description, source, provenance) used by the Excel input sheets.
"""
from __future__ import annotations
import copy
import re
import yaml
from pathlib import Path
from .models import (PropellantSpec, TankMaterial, TankSpec, EngineSpec, StageSpec, FairingSpec,
                     ConvergenceSettings, VehicleSpec, MotorSpec, BoosterSpec, SolidPropellantSpec)

class _Loader(yaml.SafeLoader):
    """SafeLoader that also reads 7.0e6 / 1e-4 style floats (PyYAML's YAML-1.1 rule needs a signed exponent)."""


_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(r"^[-+]?(?:[0-9][0-9_]*)(?:\.[0-9_]*)?(?:[eE][-+]?[0-9]+)$|^[-+]?(?:[0-9][0-9_]*)\.[0-9_]*$"),
    list("-+0123456789."))

PROVENANCE = ("user", "reference", "assumed")
REQUIRED = ("v", "u", "d", "s", "t")


class ConfigError(ValueError):
    """A problem with the configuration.

    `field` carries the dotted path of the input at fault when there is exactly one, so a user interface can
    take the person straight to it instead of making them hunt for the field the message names.
    """

    def __init__(self, message, field: str | None = None):
        super().__init__(message)
        self.field = field


def _unwrap(node, path, reg):
    if isinstance(node, dict) and "v" in node:
        missing = [k for k in REQUIRED if k not in node]
        if missing:
            raise ConfigError(f"input '{path}' is missing documentation keys {missing}")
        if node["t"] not in PROVENANCE:
            raise ConfigError(f"input '{path}': provenance 't' must be one of {PROVENANCE}, got {node['t']!r}")
        if not str(node["s"]).strip():
            raise ConfigError(f"input '{path}': empty source/justification")
        reg.append(dict(path=path, value=node["v"], units=node["u"], description=node["d"],
                        source=node["s"], provenance=node["t"]))
        return node["v"]
    if isinstance(node, dict):
        return {k: _unwrap(v, f"{path}.{k}" if path else k, reg) for k, v in node.items()}
    if isinstance(node, list):
        return [_unwrap(v, f"{path}[{i}]", reg) for i, v in enumerate(node)]
    raise ConfigError(f"input '{path}' = {node!r} is an undocumented bare value; use {{v:, u:, d:, s:, t:}}")


def load_yaml_annotated(path, reg=None, extra=None):
    """Read and unwrap an annotated file. `extra` is merged in before unwrapping: library entries from the
    personal library and from a design's own `library:` block (see user_library), so they are checked and
    registered exactly like shipped ones."""
    reg = [] if reg is None else reg
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.load(f, Loader=_Loader)
    meta = raw.pop("meta", {})
    # A design's `library:` block is not an input of the vehicle but entries for the library it is sized
    # against; it is handed back through meta for load_design to merge into the assumptions
    if "library" in raw:
        meta = dict(meta or {})
        meta["_library"] = raw.pop("library")
    if extra:
        from .user_library import merge as _merge
        _merge(raw, extra)
    # A `trade_study:` block is a study DECLARATION, not an input to the vehicle: plain YAML by design,
    # read by `studies.run_trade_study` and by the GUI's trade endpoint, never by the sizing loop. It was
    # not excluded here, so a file carrying one could be opened in the GUI and then refused on Size with
    # "trade_study.name is an undocumented bare value" - an error about a field that is not a field.
    raw.pop("trade_study", None)
    return _unwrap(raw, "", reg), meta, reg


#: Optional inputs a design file may leave out altogether, which the GUI still offers a field for. Setting
#: one creates it; any other unknown path is still refused, so a mistyped name cannot pass as a new input.
CREATABLE_LEAVES = {("engine", "cstar_mps"): dict(u="m/s", d="Delivered characteristic velocity c*, read only when "
                                                             "the engine dimensions come from the book relations")}


def creatable_leaf(keys) -> bool:
    return tuple(keys[-2:]) in CREATABLE_LEAVES


def assumptions_doc(assumptions_path, design_path=None) -> dict:
    """The annotated assumptions document as a design sees it: shipped, plus the personal library, plus the
    design's own `library:` block. For the GUI's choice lists, which must offer exactly what the sizing reads."""
    from .user_library import extra_entries, merge
    with open(assumptions_path, encoding="utf-8") as fh:
        doc = yaml.load(fh, Loader=_Loader) or {}
    block = None
    if design_path:
        with open(design_path, encoding="utf-8") as fh:
            block = (yaml.load(fh, Loader=_Loader) or {}).get("library")
    return merge(doc, extra_entries(block))


def deep_set(d: dict, dotted: str, value):
    """Set e.g. 'stages.0.engine.isp_vac_s' on a nested dict/list structure (used by sensitivity studies).

    Both index spellings are accepted. The input register writes `stages[0].engine.isp_vac_s`, while the
    sensitivity and trade drivers write `stages.0.engine.isp_vac_s`; anything holding a path from the register
    - the GUI above all - would otherwise fail on every per-stage value with a bare KeyError.
    """
    cur = d
    keys = re.sub(r"\[(\d+)\]", r".\1", str(dotted)).split(".")
    for k in keys[:-1]:
        cur = cur[int(k)] if isinstance(cur, list) else cur[k]
    last = keys[-1]
    if isinstance(cur, list):
        cur[int(last)] = value
    else:
        if last not in cur and not creatable_leaf(keys):
            raise ConfigError(f"unknown parameter path '{dotted}'")
        cur[last] = value


def _need(d: dict, key: str, ctx: str):
    """A required input: it must be present AND filled in.

    The emptiness check matters as much as the presence one. A half-filled design - exactly what the GUI's
    New button produces, on purpose - carries `v: null` on the fields the user has still to supply, and
    without this the null travelled on into the arithmetic and surfaced as
    `TypeError: unsupported operand type(s) for *: 'NoneType' and 'float'`, which names neither the field nor
    the remedy. Fields that are genuinely optional are read with `.get()` and never come through here, so a
    null arriving at this function always means "required, and still empty".
    """
    if key not in d:
        raise ConfigError(f"missing required input '{ctx}.{key}'")
    v = d[key]
    if v is None:
        raise ConfigError(f"'{ctx}.{key}' is empty and has to be filled in", field=f"{ctx}.{key}")
    return v


def _build_solid_stage(i: int, sd: dict, ctx: str) -> StageSpec:
    """Serial solid stage: a motor casing replaces the tanks and the engine (book Sec. 8.5)."""
    mo = _need(sd, "motor", ctx)
    mc = ctx + ".motor"
    motor = MotorSpec(
        name=_need(mo, "name", mc), n_motors=int(mo.get("n_motors", 1)),
        thrust_mode=_need(mo, "thrust_mode", mc), thrust_vac_total_N=mo.get("thrust_vac_total_N"),
        tw_ignition=mo.get("thrust_to_weight_ignition"), burn_time_s=mo.get("burn_time_s"),
        isp_vac_s=_need(mo, "isp_vac_s", mc), isp_sl_s=mo.get("isp_sl_s"),
        isp_mode=_need(mo, "isp_effective_mode", mc), isp_weight_sl=mo.get("isp_sl_weight", 1.0 / 3.0),
        isp_user_s=mo.get("isp_effective_user_s"), expansion_ratio=_need(mo, "expansion_ratio", mc),
        chamber_pressure_Pa=_need(mo, "chamber_pressure_Pa", mc), cstar_mps=_need(mo, "cstar_mps", mc),
        nozzle_geometry_method=_need(mo, "nozzle_geometry_method", mc), exit_diameter_m=mo.get("exit_diameter_m"),
        nozzle_length_m=mo.get("nozzle_length_m"), embed_fraction=_need(mo, "embed_fraction", mc),
        casing_mass_method=_need(mo, "casing_mass_method", mc), casing_mass_fraction=mo.get("casing_mass_fraction"),
        casing_mass_kg=mo.get("casing_mass_kg"), casing_volume_factor=_need(mo, "casing_volume_factor", mc),
        dome_AR=_need(mo, "dome_aspect_ratio", mc), wall_t_assumed_m=_need(mo, "wall_thickness_assumed_m", mc),
        tvc_mass_kg=mo.get("tvc_mass_kg", 0.0), igniter_mass_kg=mo.get("igniter_mass_kg", 0.0),
        cycle="solid", db_entry=mo.get("from_database"))
    lay = _need(sd, "layout", ctx)
    return StageSpec(
        index=i + 1, name=_need(sd, "name", ctx), fuel="", oxidizer="", of_ratio=1.0,
        residual_fraction=_need(sd, "residual_fraction", ctx),
        loading_margin_fraction=_need(sd, "loading_margin_fraction", ctx),
        startup_time_s=sd.get("startup_time_s", 0.0), diameter_m=_need(sd, "diameter_m", ctx),
        structure_mode=_need(sd, "structure_mode", ctx), structural_factor_s=sd.get("structural_factor_s"),
        tank=None, engine=None,
        aft_skirt_over_D=_need(lay, "aft_skirt_over_D", ctx + ".layout"), intertank_over_D=0.0,
        fwd_skirt_over_D=_need(lay, "fwd_skirt_over_D", ctx + ".layout"),
        interstage_min_length_m=_need(lay, "interstage_min_length_m", ctx + ".layout"),
        interstage_clearance_m=_need(lay, "interstage_clearance_m", ctx + ".layout"),
        interstage_half_angle_deg=_need(lay, "interstage_half_angle_deg", ctx + ".layout"),
        feed_mass_per_engine_kg=0.0, pressurant_fraction=0.0,
        separation_hw_kg=_need(sd, "separation_hardware_mass_kg", ctx),
        other_mass_kg=_need(sd, "other_equipment_mass_kg", ctx),
        inert_margin_fraction=_need(sd, "inert_mass_margin_fraction", ctx),
        structure_mass_factor=_need(sd, "structure_mass_factor", ctx), max_length_m=sd.get("max_length_m"),
        avionics_kg_override=sd.get("avionics_mass_override_kg"), stage_type="solid",
        propellant=_need(sd, "propellant", ctx), motor=motor)


def _build_boosters(bd: dict) -> BoosterSpec:
    c = "boosters"
    n = int(_need(bd, "n_total", c))
    return BoosterSpec(
        name=_need(bd, "name", c), n_total=n, n_ground_lit=int(bd.get("n_ground_lit", n)),
        kind=_need(bd, "type", c), attach_stage=int(bd.get("attach_stage", 1)),
        propellant=bd.get("propellant"), fuel=bd.get("fuel"), oxidizer=bd.get("oxidizer"),
        of_ratio=bd.get("mixture_ratio_OF"), isp_vac_s=_need(bd, "isp_vac_s", c), isp_sl_s=bd.get("isp_sl_s"),
        isp_mode=_need(bd, "isp_effective_mode", c), isp_weight_sl=bd.get("isp_sl_weight", 1.0 / 3.0),
        prop_mass_each_kg=_need(bd, "propellant_mass_each_kg", c), burn_time_s=_need(bd, "burn_time_s", c),
        residual_fraction=bd.get("residual_fraction", 0.0),
        inert_mass_method=_need(bd, "inert_mass_method", c), inert_mass_fraction=bd.get("inert_mass_fraction"),
        inert_mass_each_kg=bd.get("inert_mass_each_kg"), inert_margin_fraction=bd.get("inert_mass_margin_fraction", 0.0),
        diameter_m=_need(bd, "diameter_m", c), dome_AR=bd.get("dome_aspect_ratio", 1.0),
        nose_length_over_D=bd.get("nose_length_over_D", 1.5), base_z_offset_m=bd.get("base_z_offset_m", 0.0),
        radial_gap_m=bd.get("radial_gap_m", 0.2), exit_diameter_m=_need(bd, "exit_diameter_m", c),
        nozzle_length_m=_need(bd, "nozzle_length_m", c), attach_hw_mass_each_kg=bd.get("attach_hardware_mass_each_kg", 0.0),
        casing_volume_factor=bd.get("casing_volume_factor", 1.12), wall_t_assumed_m=bd.get("wall_thickness_assumed_m", 0.0))


def build_spec(design: dict, assump: dict, reg: list | None = None, name: str = "design") -> VehicleSpec:
    """Convert unwrapped dicts into typed specs (no defaults are invented here).

    Library references are resolved here rather than in load_design so that EVERY route into a spec gets them -
    the GUI, the trade-study driver and the tests build specs without going through load_design, and a design
    whose propellants resolve on one route and not another is a trap.
    """
    reg = [] if reg is None else reg
    from .engine_db import expand_design as _expand_engines
    from .propellant_db import expand_design as _expand_combinations
    # The engine database runs first: an engine row's own mixture ratio is the more specific statement, so it
    # is already in place by the time the combination library looks for gaps to fill.
    _engine_notes = _expand_engines(design, reg)
    _combo_notes = _expand_combinations(design, assump, reg)
    # A named launch site fills the latitude, so this has to run before the mission block is read below.
    from .launch_sites import expand_design as _expand_site
    _site_note = _expand_site(design, reg)
    m = _need(design, "mission", "")
    orb = _need(m, "orbit", "mission")
    site = _need(m, "launch_site", "mission")
    loss = _need(m, "losses", "mission")
    mission = dict(
        orbit_type=_need(orb, "type", "mission.orbit"),
        perigee_altitude_m=_need(orb, "perigee_altitude_km", "mission.orbit") * 1e3,
        apogee_altitude_m=None if orb.get("apogee_altitude_km") is None else orb["apogee_altitude_km"] * 1e3,
        eccentricity=orb.get("eccentricity"),
        inclination_deg=_need(orb, "inclination_deg", "mission.orbit"),
        site_latitude_deg=_need(site, "latitude_deg", "mission.launch_site"),
        # Optional, and only the impact-point map reads it: a design written before the map existed simply has
        # no longitude, and that is handled where it is consumed rather than demanded here.
        site_longitude_deg=site.get("longitude_deg"),
        site_altitude_m=site.get("altitude_m"),
        launch_azimuth_deg=site.get("azimuth_deg"),
        include_earth_rotation=_need(site, "include_earth_rotation", "mission.launch_site"),
        loss_model=_need(loss, "model", "mission.losses"),
        gravity_loss_mps=loss.get("gravity_mps"),
        drag_loss_mps=loss.get("drag_mps"),
        steering_loss_mps=loss.get("steering_mps"),
        other_allowance_mps=_need(loss, "other_allowance_mps", "mission.losses"),
        staging_delay_s=_need(loss, "staging_delay_s", "mission.losses"),
        ascent_time_override_s=loss.get("ascent_time_override_s"),
        design_margin_fraction=_need(loss, "design_margin_fraction", "mission.losses"),
        report_apogee_maneuver=m.get("report_apogee_maneuver", False),
        dv_override_mps=m.get("delta_v_override_mps"),
        air_launch=m.get("air_launch"),
        # the 3-DoF ascent trajectory study reads these; all optional, all defaulted
        aerodynamics=m.get("aerodynamics"),
        atmosphere_model=m.get("atmosphere_model"),
        vertical_rise_s=m.get("vertical_rise_s"),
        last_ascent_stage=m.get("last_ascent_stage"),
        # the Chapter 9 load cases read this; optional, defaults to a vehicle standing on the ground
        pad_height_m=m.get("pad_height_m"), wind=m.get("wind"),
        # Chapter 17 cost model
        cost_year=m.get("cost_year"),
    )
    f = _need(design, "fairing", "")
    fairing = FairingSpec(
        diameter_m=_need(f, "diameter_m", "fairing"), nose_length_over_D=_need(f, "nose_length_over_D", "fairing"),
        axial_clearance_m=_need(f, "axial_clearance_m", "fairing"),
        radial_clearance_m=_need(f, "radial_clearance_m", "fairing"),
        envelope_diameter_m=_need(m, "payload_envelope_diameter_m", "mission"),
        envelope_length_m=_need(m, "payload_envelope_length_m", "mission"),
        material=_need(f, "material", "fairing"), jettison_stage=int(_need(f, "jettison_at_stage_start", "fairing")),
        mass_override_kg=f.get("mass_override_kg"))

    props = {}
    for pname, p in _need(assump, "propellants", "assumptions").items():
        props[pname] = PropellantSpec(pname, p["density_kg_m3"], p.get("boiling_K"), p["insulation_kg_m2"],
                                      p.get("tank_mer_per_kg"), p.get("tank_mer_ref_density"))
    mats = _need(assump, "tank_materials", "assumptions")

    solid_props = {}
    for pname, p in (assump.get("solid_propellants") or {}).items():
        solid_props[pname] = SolidPropellantSpec(pname, p["density_kg_m3"], p.get("isp_note", ""),
                                                 p.get("source", ""), c_star_mps=p.get("c_star_mps", 0.0),
                                                 burn_rate_exponent=p.get("burn_rate_exponent", 0.0))

    stages = []
    for i, sd in enumerate(_need(design, "stages", "")):
        ctx = f"stages[{i}]"
        if sd.get("stage_type", "liquid") == "solid":
            stages.append(_build_solid_stage(i, sd, ctx))
            continue
        tk = _need(sd, "tank", ctx)
        mat = mats[_need(tk, "material", ctx + ".tank")]
        tank = TankSpec(
            arrangement=_need(tk, "arrangement", ctx + ".tank"), order_bottom_to_top=_need(tk, "order_bottom_to_top", ctx + ".tank"),
            dome_AR=_need(tk, "dome_aspect_ratio", ctx + ".tank"),
            ullage_fraction=dict(fuel=_need(tk, "ullage_fuel", ctx + ".tank"), oxidizer=_need(tk, "ullage_oxidizer", ctx + ".tank")),
            mass_method=dict(fuel=_need(tk, "mass_method_fuel", ctx + ".tank"), oxidizer=_need(tk, "mass_method_oxidizer", ctx + ".tank")),
            pressure_Pa=dict(fuel=tk.get("pressure_fuel_Pa", 0.0), oxidizer=tk.get("pressure_oxidizer_Pa", 0.0)),
            wall_t_assumed_m=dict(fuel=_need(tk, "wall_thickness_assumed_m", ctx + ".tank"), oxidizer=_need(tk, "wall_thickness_assumed_m", ctx + ".tank")),
            mass_fraction=dict(fuel=tk.get("mass_fraction_fuel", 0.0), oxidizer=tk.get("mass_fraction_oxidizer", 0.0)),
            user_mass_kg=dict(fuel=tk.get("user_mass_fuel_kg", 0.0), oxidizer=tk.get("user_mass_oxidizer_kg", 0.0)),
            material=TankMaterial(mat["name"], mat["rho_kg_m3"], mat["alpha_per_K"], mat["sigma_allow_Pa"],
                                  mat["joint_efficiency"], mat["safety_factor"], mat["corrosion_allowance_m"],
                                  mat["t_min_m"], E_Pa=mat.get("E_Pa", 69.0e9),
                                  poisson=mat.get("poisson", 0.31),
                                  t_min_structural_m=mat.get("t_min_structural_m", 0.0005)),
            load_temperature_K=_need(tk, "load_temperature_K", ctx + ".tank"),
            insulated=dict(fuel=_need(tk, "insulated_fuel", ctx + ".tank"), oxidizer=_need(tk, "insulated_oxidizer", ctx + ".tank")),
            diameter_m=tk.get("diameter_m"))
        e = _need(sd, "engine", ctx)
        eng = EngineSpec(
            name=_need(e, "name", ctx + ".engine"), n_engines=int(_need(e, "n_engines", ctx + ".engine")),
            thrust_vac_per_engine_N=e.get("thrust_vac_per_engine_N"), tw_ignition=e.get("thrust_to_weight_ignition"),
            isp_vac_s=_need(e, "isp_vac_s", ctx + ".engine"), isp_sl_s=e.get("isp_sl_s"),
            isp_mode=_need(e, "isp_effective_mode", ctx + ".engine"), isp_weight_sl=e.get("isp_sl_weight", 1.0 / 3.0),
            isp_user_s=e.get("isp_effective_user_s"), expansion_ratio=_need(e, "expansion_ratio", ctx + ".engine"),
            # Optional: real engine rows do not all publish a chamber pressure (RL10C-1 is one), and a design
            # that neither sizes the engine from the book MER nor gimbals it by MER never needs the number.
            # The two places that DO need it say so by name rather than failing on a None here.
            chamber_pressure_Pa=e.get("chamber_pressure_Pa"), length_m=_need(e, "length_m", ctx + ".engine"),
            exit_diameter_m=_need(e, "exit_diameter_m", ctx + ".engine"), embed_fraction=_need(e, "embed_fraction", ctx + ".engine"),
            mass_method=_need(e, "mass_method", ctx + ".engine"), mass_user_kg=e.get("mass_user_per_engine_kg"),
            gimbal_method=_need(e, "gimbal_method", ctx + ".engine"), gimbal_user_kg=e.get("gimbal_user_per_engine_kg"),
            throttle_min=e.get("throttle_min_fraction", 1.0),
            geometry_method=e.get("geometry_method", "user"), cstar_mps=e.get("cstar_mps"),
            cycle=e.get("cycle"), db_entry=e.get("from_database"))
        lay = _need(sd, "layout", ctx)
        stages.append(StageSpec(
            index=i + 1, name=_need(sd, "name", ctx), fuel=_need(sd, "fuel", ctx), oxidizer=_need(sd, "oxidizer", ctx),
            of_ratio=_need(sd, "mixture_ratio_OF", ctx), residual_fraction=_need(sd, "residual_fraction", ctx),
            loading_margin_fraction=_need(sd, "loading_margin_fraction", ctx), startup_time_s=_need(sd, "startup_time_s", ctx),
            diameter_m=_need(sd, "diameter_m", ctx), structure_mode=_need(sd, "structure_mode", ctx),
            structural_factor_s=sd.get("structural_factor_s"), tank=tank, engine=eng,
            aft_skirt_over_D=_need(lay, "aft_skirt_over_D", ctx + ".layout"), intertank_over_D=_need(lay, "intertank_over_D", ctx + ".layout"),
            fwd_skirt_over_D=_need(lay, "fwd_skirt_over_D", ctx + ".layout"),
            interstage_min_length_m=_need(lay, "interstage_min_length_m", ctx + ".layout"),
            interstage_clearance_m=_need(lay, "interstage_clearance_m", ctx + ".layout"),
            interstage_half_angle_deg=_need(lay, "interstage_half_angle_deg", ctx + ".layout"),
            feed_mass_per_engine_kg=_need(sd, "feed_system_mass_per_engine_kg", ctx),
            pressurant_fraction=_need(sd, "pressurant_mass_fraction_of_propellant", ctx),
            separation_hw_kg=_need(sd, "separation_hardware_mass_kg", ctx), other_mass_kg=_need(sd, "other_equipment_mass_kg", ctx),
            inert_margin_fraction=_need(sd, "inert_mass_margin_fraction", ctx), structure_mass_factor=_need(sd, "structure_mass_factor", ctx), max_length_m=sd.get("max_length_m"),
            avionics_kg_override=sd.get("avionics_mass_override_kg")))

    vh = _need(design, "vehicle", "")
    cv = _need(assump, "convergence", "assumptions")
    spec = VehicleSpec(
        name=name, mission=mission, payload_mass_kg=_need(m, "payload_mass_kg", "mission"),
        paf_mass_override_kg=m.get("payload_adapter_mass_kg"), paf_length_over_D=_need(vh, "paf_length_over_D", "vehicle"),
        paf_method=vh.get("payload_adapter_method", "mer"),
        fairing=fairing, stages=stages, dv_mode=_need(vh, "dv_allocation_mode", "vehicle"),
        dv_fractions=vh.get("dv_fractions"), dv_fixed=vh.get("dv_fixed_mps"),
        optimise_dv=bool(vh.get("optimise_dv_split", False)),
        optimise_objective=str(vh.get("optimise_objective") or "glom"),
        earth_model=_need(assump, "earth_model", "assumptions"), mer=_need(assump, "mer", "assumptions"),
        propellants=props, convergence=ConvergenceSettings(cv["tol"], int(cv["max_iter"]), cv["relax"]),
        constraints=design.get("constraints", {}), inputs_register=reg or [],
        mer_scatter=assump.get("mer_scatter", {}),
        solid_propellants=solid_props,
        boosters=_build_boosters(design["boosters"]) if design.get("boosters") else None)
    spec.engine_db_notes = _engine_notes
    spec.propellant_combination_notes = _combo_notes
    spec.launch_site_note = _site_note
    from .propellant_db import load as _load_combinations
    spec.propellant_combinations = _load_combinations(assump, reg)
    return spec


def load_design(design_path, assumptions_path, overrides: dict | None = None) -> VehicleSpec:
    """Load, optionally override (dotted paths on the *unwrapped* design dict), and build a VehicleSpec."""
    from . import user_library as _ul
    reg = []
    design, meta, reg = load_yaml_annotated(design_path, reg)
    assump, _, reg = load_yaml_annotated(assumptions_path, reg,
                                         extra=_ul.extra_entries((meta or {}).get("_library")))
    if overrides:
        for k, v in overrides.items():
            # The GUI writes a library value under its own path (propellants.LOX.density_kg_m3), with no
            # "assumptions." prefix. Sent to the design dict, it failed with a KeyError, so no library value
            # could be changed from the GUI at all. A path whose first segment is an assumptions block goes there.
            if k.startswith("assumptions."):
                deep_set(assump, k[len("assumptions."):], v)
            elif re.split(r"[.\[]", k, maxsplit=1)[0] in _ul.ASSUMPTION_BLOCKS:
                deep_set(assump, k, v)
            else:
                deep_set(design, k, v)
    # real engines and motors, if the design names any: fills only what the design left out, and records every
    # filled value in the input register with the database row's own source (see engine_db)
    # the engine database and the propellant-combination library are resolved inside build_spec
    return build_spec(design, assump, reg, name=meta.get("name", Path(design_path).stem))
