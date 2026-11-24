"""What the GUI needs to show an input as something a person can answer, rather than a YAML path.

Three things, for every one of the ~250 annotated inputs:

* a **label** - "Vacuum specific impulse", not `stages.0.engine.isp_vac_s`;
* the **choices**, where the field has a fixed set. Typing `RP-1` by hand risks a typo, or worse a propellant
  the tool has no density for; a list cannot be mistyped. The lists are not duplicated here - the propellant,
  combination, engine and material ones are read live from the libraries themselves, so a propellant added to
  the assumptions file appears in the GUI without anyone editing this module, and the code-level ones cite the
  line that enforces them;
* a **place**: a section, and a topic within it.

Paths are normalised before matching, so `stages.0.engine.isp_vac_s` and `stages.3.engine.isp_vac_s` both look
up `stages.*.engine.isp_vac_s`. Lookup falls back to the leaf key, then to a prettifier, so a field added to
the YAML without being listed here still gets a readable label rather than breaking the page.
"""
from __future__ import annotations

import os
import re

# --------------------------------------------------------------------------- choices fixed in code
#: path -> [(value, label)]. Every list here is enforced somewhere in the model; the comment says where, so a
#: list that drifts from its validator is a visible mistake rather than a silent one.
def _casing_choices():
    """Solid casing/inert methods, drawn from solid_inert so the GUI and the validator cannot drift.

    The book's four come first because they are the defaults; the published stage-level regressions follow,
    each labelled with the mass it predicts so nobody picks one expecting a casing mass (R18).
    """
    from . import solid_inert
    out = [("book_steel", "Book relation, steel case (motor only)"),
           ("book_composite", "Book relation, composite case (motor only)"),
           ("mass_fraction", "Fraction of propellant (motor only)"),
           ("user_mass", "Mass I give (motor only)")]
    for key, rel in solid_inert.RELATIONS.items():
        scope = "whole stage" if rel.predicts == "stage" else "motor only"
        out.append((key, f"{rel.label} ({scope})"))
    return out


STATIC_CHOICES: dict = {
    # validation.validate_spec
    "mission.orbit.type": [("LEO", "Low Earth orbit"), ("SSO", "Sun-synchronous"),
                           ("GTO", "Geostationary transfer"), ("GEO_VIA_GTO", "Geostationary, via GTO"),
                           ("GEO_DIRECT", "Geostationary, direct"), ("CUSTOM", "Custom (use the fields below)")],
    "mission.losses.model": [("book_penalty", "Book regression (Eq. 3:36-3:38)"),
                             ("book_k1k2", "Book k1/k2 form"), ("book_simple", "Book simple form"),
                             ("simulated", "From this vehicle's own simulated flight (slower)"),
                             ("user", "My own loss estimates")],
    "vehicle.dv_allocation_mode": [("fractions", "Split by fraction of total"),
                                   ("fixed", "Fixed delta-v per stage")],
    "vehicle.optimise_objective": [("glom", "Lightest vehicle (lift-off mass)"),
                                   ("cost", "Lowest development cost"),
                                   ("payload", "Most payload at the same lift-off mass")],
    "vehicle.payload_adapter_method": [("auto", "Automatic (MER, or fraction for small payloads)"),
                                       ("mer", "Mass relationship (Table 8.8)"),
                                       ("fraction", "Fraction of payload (0.15)")],
    "fairing.material": [("metal", "Metal"), ("composite", "Composite")],
    "stages.*.stage_type": [("liquid", "Liquid"), ("solid", "Solid motor")],
    "stages.*.structure_mode": [("bottom_up", "Build up from components"),
                                ("aggregate_s", "Single structural factor")],
    "stages.*.engine.isp_effective_mode": [("vacuum", "Vacuum Isp"),
                                           ("weighted", "Weighted sea-level/vacuum (Eq. 4:18)"),
                                           ("user", "My own effective Isp")],
    "stages.*.motor.isp_effective_mode": [("vacuum", "Vacuum Isp"),
                                          ("weighted", "Weighted sea-level/vacuum (Eq. 4:18)"),
                                          ("user", "My own effective Isp")],
    "stages.*.engine.geometry_method": [("user", "Dimensions I give"), ("book_mer", "From the book relations")],
    "stages.*.motor.nozzle_geometry_method": [("user", "Dimensions I give"),
                                              ("book_mer", "From the book relations")],
    "stages.*.engine.mass_method": [("mer", "Book mass relationship"),
                                    ("mer_calibrated", "Book relationship x the measured correction"),
                                    ("user", "Mass I give")],
    "stages.*.engine.gimbal_method": [("mer", "Mass relationship"), ("user", "Mass I give"),
                                      ("none", "No separate gimbal mass")],
    "stages.*.tank.arrangement": [("separate", "Separate tanks"), ("common_bulkhead", "Common bulkhead")],
    "stages.*.motor.thrust_mode": [("tw_ignition", "From thrust/weight at ignition"),
                                   ("fixed_thrust", "Fixed thrust"), ("burn_time", "From burn time")],
    "stages.*.motor.casing_mass_method": _casing_choices(),
    "boosters.kind": [("solid", "Solid"), ("liquid", "Liquid")],
    "boosters.type": [("solid", "Solid"), ("liquid", "Liquid")],      # the key the design file uses
    "boosters.inert_mass_method": _casing_choices(),
    "boosters.isp_mode": [("vacuum", "Vacuum Isp"), ("weighted", "Weighted sea-level/vacuum")],
    "boosters.isp_effective_mode": [("vacuum", "Vacuum Isp"), ("weighted", "Weighted sea-level/vacuum (Eq. 4:18)")],
    "mission.wind.kind": [("gust_envelope", "Gust envelope (already contains the gust)"),
                          ("steady", "Steady wind (needs a gust increment)")],
    # the two trajectory-model choices, whose options the design file's own description lists
    "mission.atmosphere_model": [("book_exponential", "Book exponential (Eqs. 6:50/6:53)"),
                                 ("us76", "US 1976 standard atmosphere")],
    "mission.ascent_profile": [("auto", "Automatic (straight in up to 200 km, otherwise raise the orbit)"),
                               ("direct", "Straight in, one burn"),
                               ("parking", "Low first, then a second burn")],
    "mission.aerodynamics.drag_model": [("geometry", "From this vehicle's geometry (varies with Mach)"),
                                        ("book_titan2", "Book Titan II curve (varies with Mach, Fig. 6.13)"),
                                        ("table", "Your own table of Cd against Mach"),
                                        ("constant", "One fixed Cd at every Mach (hand checks only)")],
    "mission.aerodynamics.nose_shape": [("cone", "Cone"), ("ogive", "Tangent ogive")],
}
#: tank mass methods come from validation.TANK_METHODS so the two cannot drift apart
_TANK_METHOD_LABELS = {"akin_propellant_mass": "Akin, by propellant mass (Table 8.6)",
                       "akin_volume": "Akin, by volume (Table 8.7)",
                       "pressure_vessel": "Pressure vessel (membrane theory)",
                       "mass_fraction": "Fraction of propellant mass",
                       "user_mass": "Mass I give"}

#: the tank order list is a sequence, not a single choice, but its members are fixed
TANK_ROLES = ("fuel", "oxidizer")


def _tank_method_choices():
    from .validation import TANK_METHODS
    return [(m, _TANK_METHOD_LABELS.get(m, m)) for m in TANK_METHODS]


# --------------------------------------------------------------------------- choices from the libraries
def library_choices(assump: dict | None = None, engine_db_path: str | None = None) -> dict:
    """Choice lists that come from data rather than from code, read live so they cannot go stale.

    A propellant added to engineering_assumptions.yaml, or an engine added to the database, shows up in the
    GUI immediately. Anything unreadable is skipped rather than raising: a broken engine database should cost
    you the engine dropdown, not the whole page.
    """
    out: dict = {}
    if assump:
        props = sorted((assump.get("propellants") or {}))
        combos = sorted((assump.get("propellant_combinations") or {}))
        solids = sorted((assump.get("solid_propellants") or {}))
        mats = sorted((assump.get("tank_materials") or {}))
        if props:
            # Split the library by the role each propellant declares, so the fuel box never offers LOX
            # and the oxidiser box never offers kerosene. A propellant with no role tag is offered in both
            # rather than becoming unreachable - an untagged entry is a gap in the library, not a reason to
            # hide it from the user.
            raw = assump.get("propellants") or {}

            def _role(name):
                try:
                    return ((raw.get(name) or {}).get("role") or {}).get("v")
                except AttributeError:
                    return None
            fuels = [x for x in props if _role(x) in (None, "fuel")]
            oxes = [x for x in props if _role(x) in (None, "oxidizer")]
            mine = _custom("propellants")
            lab = lambda x: f"{x} (my library)" if x in mine else x                     # noqa: E731
            for p in ("stages.*.fuel", "boosters.fuel"):
                out[p] = [(x, lab(x)) for x in fuels]
            for p in ("stages.*.oxidizer", "boosters.oxidizer"):
                out[p] = [(x, lab(x)) for x in oxes]
        if combos:
            mine_c = _custom("propellant_combinations")
            out["stages.*.propellant_combination"] = [(x, f"{x} (my library)" if x in mine_c else x) for x in combos]
        # Which tank sits at the bottom. There are exactly two answers, so it is a choice, not a field to
        # type a list into. It keeps its meaning under a common bulkhead: the order still decides which
        # tank is aft, and the book's own S-II example (p.633) shows that moving the heavier tank forward
        # doubled the pre-launch wind running load, from 140.4 to 290.5 kN/m.
        out["stages.*.tank.order_bottom_to_top"] = [
            ("fuel,oxidizer", "Fuel at the bottom, oxidiser above"),
            ("oxidizer,fuel", "Oxidiser at the bottom, fuel above"),
        ]
        if solids:
            mine_s = _custom("solid_propellants")
            sl = [(x, f"{x} (my library)" if x in mine_s else x) for x in solids]
            out["stages.*.propellant"] = sl
            out["boosters.propellant"] = list(sl)
        if mats:
            # Label each key with the material's own name, so the list reads "SS-301-FH - Stainless steel
            # 301, full hard (AMS 5519)" rather than making the user know what a key stands for.
            lib = assump.get("tank_materials") or {}
            def _label(key):
                nm = (lib.get(key) or {}).get("name")
                nm = nm.get("v") if isinstance(nm, dict) else nm
                return f"{key} - {nm}" if nm and nm != key else key
            mine_m = _custom("tank_materials")
            out["stages.*.tank.material"] = [(x, _label(x) + (" (my library)" if x in mine_m else "")) for x in mats]
    # The launch site library lives in its own file, so it is read whether or not assumptions were passed.
    # A broken library costs the dropdown, not the page: choices() already returns [] on any read failure.
    try:
        from .launch_sites import choices as _site_choices
        sites = _site_choices()
        if sites:
            out["mission.launch_site.site"] = sites
    except Exception:
        pass
    try:
        from . import engine_db
        rows = engine_db.entries(engine_db_path)
        liquid = sorted(e["name"] for e in rows if e.get("kind", "liquid") != "solid")
        solid = sorted(e["name"] for e in rows if e.get("kind") == "solid")
        if liquid:
            out["stages.*.engine.from_database"] = [(x, x) for x in liquid]
        if solid:
            out["stages.*.motor.from_database"] = [(x, x) for x in solid]
            out["boosters.from_database"] = [(x, x) for x in solid]
        cycles = sorted(engine_db.cycles(engine_db_path))
        if cycles:
            out["stages.*.engine.cycle"] = [(c, c.replace("_", " ")) for c in cycles]
    except Exception:                      # a broken database costs the dropdown, not the page
        pass
    for key in ("stages.*.tank.mass_method_fuel", "stages.*.tank.mass_method_oxidizer"):
        out[key] = _tank_method_choices()
    return out


def _custom(section: str) -> set:
    try:
        from .user_library import custom_names
        return custom_names().get(section, set())
    except Exception:                                                  # noqa: BLE001
        return set()


def combination_map(assump: dict | None = None) -> dict:
    """{combination name: {fuel, oxidizer, of_ratio}} for the GUI to apply when a combination is picked.

    Picking "LOX/RP-1" and leaving the fuel box on LH2 is not a design, it is a contradiction - the sizing
    loop resolves the combination and then warns about the disagreement. Better to not create it: the page
    sets the fuel, the oxidiser and the mixture ratio when the combination changes, and shows them as
    ordinary overrides the user can then change on purpose.
    """
    out: dict = {}
    raw = (assump or {}).get("propellant_combinations") or {}
    for name, c in raw.items():
        if not isinstance(c, dict):
            continue

        def _v(key):
            d = c.get(key)
            return d.get("v") if isinstance(d, dict) else d

        of = _v("of_ratio_flight")
        if of is None:
            of = _v("of_ratio_optimum")
        out[name] = {"fuel": _v("fuel"), "oxidizer": _v("oxidizer"), "of_ratio": of}
    return out


#: stage index out of a register path, so a `stages[*]` pattern can be expanded over the real stages
_STAGE_IX = re.compile(r"^stages\[(\d+)\]\.")

#: What a NEW design asks the user for: the design brief, and nothing else.
#:
#: This list is a judgement about how a person starts a vehicle, so it is written down rather than derived.
#: The obvious derivation - "every leaf tagged `provenance: user`" - was tried and is wrong: it picks up
#: `engine.throttle_min_fraction` (1.0, meaning no throttling) and `launch_site.altitude_m` (0.0, sea level),
#: which are defaults that mean something and would come up blank for no reason, and blanking the first makes
#: the design unsizable. What belongs here is what a person has actually decided before they open the tool:
#: what they are launching, to where, from where, and how big a rocket it is going to be. Everything else is
#: the method's business and keeps the value and the provenance it ships with - a new design is a blank brief,
#: not a blank method.
#:
#: `stages[*]` expands over however many stages the design has. Each entry says why it is asked for; the
#: `blank` flag is False for a field that is a pick from a list, because an empty dropdown helps nobody -
#: those are flagged for attention with their default still in place.
NEW_DESIGN_FIELDS: tuple[tuple[str, bool, str], ...] = (
    ("mission.payload_mass_kg", True, "what the vehicle has to lift"),
    ("mission.payload_envelope_diameter_m", True, "how wide the payload is, which drives the fairing"),
    ("mission.payload_envelope_length_m", True, "how long the payload is"),
    ("mission.orbit.type", False, "the kind of orbit; the rest of the orbit block follows from it"),
    ("mission.orbit.perigee_altitude_km", True, "the altitude the payload is injected at"),
    ("mission.orbit.inclination_deg", True, "the inclination asked for; a site cannot go below its latitude"),
    ("mission.launch_site.site", False, "where it flies from; picking one fills the latitude"),
    ("mission.launch_site.latitude_deg", True, "the latitude, if no site from the library fits"),
    ("fairing.diameter_m", True, "the vehicle's outer diameter at the top"),
    ("vehicle.dv_fractions", True, "how the delta-v is split between the stages: the staging decision"),
    ("stages[*].name", False, "what to call the stage"),
    ("stages[*].diameter_m", True, "the stage's diameter"),
    ("stages[*].propellant_combination", False, "what it burns; picking one fills fuel, oxidiser and O/F"),
    ("stages[*].engine.n_engines", True, "how many engines"),
    ("stages[*].engine.isp_vac_s", True, "vacuum specific impulse, or name an engine from the database"),
)


def new_design_plan(items: list) -> dict:
    """Which leaves a new design blanks, and which it merely flags, for the design actually loaded.

    `items` is the described input register, so `stages[*]` is expanded against the stages that exist and a
    pattern naming a leaf this design does not have is dropped rather than reported as missing.
    """
    have = {it["path"] for it in items}
    stage_ix = sorted({int(m.group(1)) for m in
                       (_STAGE_IX.match(p) for p in have) if m})
    blank, flag, unknown = [], [], []
    for pattern, do_blank, why in NEW_DESIGN_FIELDS:
        paths = ([pattern.replace("stages[*]", f"stages[{i}]") for i in stage_ix]
                 if "stages[*]" in pattern else [pattern])
        for p in paths:
            if p not in have:
                unknown.append(p)
                continue
            (blank if do_blank else flag).append({"path": p, "why": why})
    return {"blank": blank, "flag": flag, "missing": unknown}


def launch_site_map() -> dict:
    """{site name: {latitude, min inclination, and the hint text}} for the GUI to apply when a site is picked.

    Latitude is the only design leaf a site may write. The rest is advice the page shows beside the field:
    above all the inclination FLOOR, because the default design sits at 28.5 deg inclination from a 28.5 deg
    latitude and picking the real KSC pad (28.6082 deg) puts the mission 0.1 deg below its own floor. The
    page lifts the inclination to the floor and says it did, rather than letting the user press Size and get
    an infeasibility they did not cause on purpose.
    """
    try:
        from .launch_sites import cascade_map
        raw = cascade_map()
    except Exception:
        return {}
    out: dict = {}
    for name, d in raw.items():
        lat = d["mission.launch_site.latitude_deg"]
        lon = d.get("_longitude_deg")
        floor = d["_min_inclination_deg"]
        where = f"{abs(lat):.4f} deg {'N' if lat >= 0 else 'S'}"
        if lon is not None:
            where += f", {abs(lon):.4f} deg {'E' if lon >= 0 else 'W'}"
        caveat = ""
        if not d.get("_orbital", True):
            caveat += (" This is a SUBORBITAL range: nothing has been launched to orbit from it, so an orbital "
                       "design placed here is a hypothetical.")
        if d.get("_status") == "proposed":
            caveat += (" This site is PROPOSED and not yet chosen: the coordinate is a stand-in, and the library "
                       "row says what it stands in for.")
        out[name] = {
            "leaves": {"mission.launch_site.latitude_deg": lat},
            "min_inclination_deg": floor,
            "country": d.get("_country") or "",
            "hint": (f"{where}. A direct ascent from here cannot reach an inclination below "
                     f"{floor:.2f} deg; range-safety azimuth limits are not modelled.{caveat}"),
            "source": d.get("_source") or "",
        }
    return out


def choices_for(path: str, lib: dict | None = None):
    """The choice list for one input path, or None if it is a free value."""
    n = normalise(path)
    if lib and n in lib:
        return lib[n]
    return STATIC_CHOICES.get(n)


# --------------------------------------------------------------------------- labels
def normalise(path: str) -> str:
    """Collapse the stage index so one entry covers every stage.

    The input register writes an indexed path as `stages[0].engine.isp_vac_s`, while override paths and the
    design dictionary use `stages.0.engine.isp_vac_s`. Both normalise to `stages.*.engine.isp_vac_s`, so this
    module does not care which spelling it is handed - and neither does the caller.
    """
    t = re.sub(r"\[(\d+)\]", r".\1", str(path))
    return re.sub(r"\.\d+(?=\.|$)", ".*", t)


#: leaf key -> label. Covers the inputs a person actually sets; anything missing falls back to the prettifier.
LEAF_LABELS: dict = {
    # --- the libraries. Left to the automatic rule these come out as "Density kg", "Tank mer per" and
    # --- "Of ratio optimum", which is how a reader ends up unsure what the number even is.
    "unpressurized_kg_m2": "Unpressurised structure, per square metre",
    "composite_fairing_kg_m2": "Composite fairing, per square metre",
    "wiring_kg_per_m": "Wiring, per metre of vehicle",
    "tank_vol_mer_kg_m3": "Tank mass per cubic metre (metallic)",
    "tank_vol_mer_lh2_kg_m3": "Tank mass per cubic metre (liquid hydrogen)",
    "role": "Used as",
    "density_kg_m3": "Density",
    "rho_kg_m3": "Density",
    "boiling_K": "Normal boiling point",
    "insulation_kg_m2": "Tank insulation, per square metre",
    "tank_mer_per_kg": "Tank mass per kg of this propellant",
    "tank_mer_ref_density": "Density the tank relation is valid at",
    "of_ratio_optimum": "O/F for peak Isp (shifting equilibrium)",
    "of_ratio_optimum_frozen": "O/F for peak Isp (frozen flow)",
    "of_ratio_flight": "O/F as actually flown",
    "isp_ref_s": "Reference Isp (shifting equilibrium)",
    "isp_ref_frozen_s": "Reference Isp (frozen flow)",
    "cstar_ref_mps": "Characteristic velocity c*",
    "c_star_mps": "Characteristic velocity c*",
    "Tc_ref_K": "Chamber temperature",
    "mw_ref_kg_kmol": "Exhaust molecular weight",
    "bulk_sg": "Bulk specific gravity of the mixture",
    "isp_note": "Note on the Isp figures",
    "burn_rate_exponent": "Burn-rate pressure exponent n",
    "alpha_per_K": "Thermal expansion coefficient",
    "sigma_allow_Pa": "Allowable stress",
    "joint_efficiency": "Weld joint efficiency",
    "corrosion_allowance_m": "Corrosion allowance",
    "t_min_m": "Minimum tank wall thickness",
    "t_min_structural_m": "Minimum structural gauge",
    "E_Pa": "Young's modulus",
    "poisson": "Poisson's ratio",

    # mission
    "payload_mass_kg": "Payload mass", "payload_adapter_mass_kg": "Payload adapter mass",
    "payload_envelope_diameter_m": "Payload envelope diameter",
    "payload_envelope_length_m": "Payload envelope length",
    "delta_v_override_mps": "Total delta-v required (override)",
    "report_apogee_maneuver": "Report the apogee manoeuvre separately",
    "perigee_altitude_km": "Perigee altitude", "apogee_altitude_km": "Apogee altitude",
    "eccentricity": "Eccentricity", "inclination_deg": "Inclination",
    "site": "Launch site", "latitude_deg": "Launch site latitude", "altitude_m": "Launch site altitude",
    "azimuth_deg": "Launch azimuth", "include_earth_rotation": "Include Earth's rotation",
    "staging_delay_s": "Coast between stages", "gravity_mps": "Gravity loss (my own estimate)", "drag_mps": "Drag loss (my own estimate)",
    "steering_mps": "Steering loss (my own estimate)", "other_allowance_mps": "Extra delta-v allowance",
    "design_margin_fraction": "Delta-v margin (fraction of the total)", "model": "Ascent loss method",
    "pad_height_m": "Pad height above ground", "profile": "Wind profile",
    "atmosphere_model": "Atmosphere model", "vertical_rise_s": "Vertical rise before the pitch kick",
    "ascent_profile": "Way to orbit", "parking_altitude_m": "Altitude of the first insertion",
    "last_ascent_stage": "Last stage flown in the ascent (blank = all)", "drag_model": "Drag model",
    "constant_cd": "Fixed drag coefficient",
    "mach_table": "Mach numbers of your drag table", "cd_table": "Cd at each of those Mach numbers",
    "surface_roughness_m": "Surface roughness (geometry drag)", "nose_shape": "Nose shape (geometry drag)",
    "nose_bluntness": "Nose tip bluntness (geometry drag)",
    "gust_increment_mps": "Gust increment", "kind": "Kind",
    "max_dynamic_pressure_Pa": "Maximum dynamic pressure allowed",
    "max_q_alpha_Pa_deg": "Maximum q-alpha allowed", "cost_year": "Cost reference year",
    "cna_overrides": "Normal-force slope overrides",
    # vehicle, fairing
    "paf_length_over_D": "Payload adapter height / diameter", "payload_adapter_method": "Payload adapter mass method",
    "dv_allocation_mode": "Delta-v split method", "dv_fractions": "Delta-v share per stage",
    "optimise_dv_split": "Optimise the delta-v split when sizing",
    "optimise_objective": "Optimise the split towards",
    "dv_fixed_mps": "Delta-v per stage (fixed values)", "diameter_m": "Diameter",
    "nose_length_over_D": "Nose length / diameter", "axial_clearance_m": "Axial clearance",
    "radial_clearance_m": "Radial clearance", "material": "Material",
    "jettison_at_stage_start": "Jettison at the start of stage", "mass_override_kg": "Override the mass",
    # constraints
    "max_vehicle_length_m": "Maximum vehicle length", "min_tw_liftoff": "Minimum lift-off thrust/weight",
    "max_accel_g": "Maximum axial acceleration", "min_tw_upper": "Minimum upper-stage thrust/weight",
    # stage
    "name": "Name", "fuel": "Fuel", "oxidizer": "Oxidizer", "propellant": "Propellant",
    "propellant_combination": "Propellant combination", "mixture_ratio_OF": "Mixture ratio (oxidiser/fuel)",
    "residual_fraction": "Residual propellant (unburned fraction)", "loading_margin_fraction": "Propellant loading margin (fraction)",
    "startup_time_s": "Engine start-up time", "structure_mode": "Dry mass estimated by",
    "structural_factor_s": "Structural factor s = inert / (inert + propellant)", "stage_type": "Stage type",
    "feed_system_mass_per_engine_kg": "Feed system mass per engine",
    "pressurant_mass_fraction_of_propellant": "Pressurant system mass (fraction of propellant)",
    "separation_hardware_mass_kg": "Separation hardware mass",
    "other_equipment_mass_kg": "Other equipment mass",
    "structure_mass_factor": "Structure mass multiplier (1 = metallic)", "inert_mass_margin_fraction": "Dry-mass growth margin (fraction)",
    # layout
    "aft_skirt_over_D": "Aft skirt length / diameter", "intertank_over_D": "Intertank length / diameter",
    "fwd_skirt_over_D": "Forward skirt length / diameter", "interstage_min_length_m": "Minimum interstage length",
    "interstage_clearance_m": "Interstage clearance", "interstage_half_angle_deg": "Transition half-angle",
    # tank
    "arrangement": "Tank arrangement", "order_bottom_to_top": "Tank order, bottom to top",
    "dome_aspect_ratio": "Dome aspect ratio", "ullage_fuel": "Ullage, fuel tank",
    "ullage_oxidizer": "Ullage, oxidiser tank", "mass_method_fuel": "Fuel tank mass method",
    "mass_method_oxidizer": "Oxidiser tank mass method", "wall_thickness_assumed_m": "Assumed wall thickness",
    "pressure_fuel_Pa": "Fuel tank pressure", "pressure_oxidizer_Pa": "Oxidiser tank pressure",
    "mass_fraction_fuel": "Fuel tank mass per kg of fuel", "mass_fraction_oxidizer": "Oxidiser tank mass per kg of oxidiser",
    "load_temperature_K": "Loading temperature", "insulated_fuel": "Insulate the fuel tank",
    "insulated_oxidizer": "Insulate the oxidiser tank",
    # engine / motor
    "from_database": "Pick a real engine (fills the fields below)", "n_engines": "Number of engines", "n_motors": "Number of motors",
    "thrust_to_weight_ignition": "Thrust-to-weight at ignition (sets the thrust)",
    "thrust_vac_per_engine_N": "Vacuum thrust per engine", "thrust_vac_total_N": "Total vacuum thrust",
    "isp_vac_s": "Vacuum specific impulse", "isp_sl_s": "Sea-level specific impulse",
    "isp_effective_mode": "Isp used for sizing", "isp_sl_weight": "Sea-level share in the weighted Isp",
    "isp_effective_user_s": "Effective Isp (my own figure)", "expansion_ratio": "Nozzle area ratio",
    "chamber_pressure_Pa": "Chamber pressure", "length_m": "Length", "exit_diameter_m": "Nozzle exit diameter",
    "embed_fraction": "Fraction of the engine inside the aft skirt", "mass_method": "Engine mass method",
    "mass_user_per_engine_kg": "Engine mass, each (my own figure)", "gimbal_method": "Gimbal mass method",
    "gimbal_user_per_engine_kg": "Gimbal mass, each (my own figure)", "throttle_min_fraction": "Minimum throttle (1 = no throttling)",
    "geometry_method": "Engine dimensions from", "cstar_mps": "Characteristic velocity c* (delivered)",
    "cycle": "Power cycle", "burn_time_s": "Burn time", "thrust_mode": "How to set thrust",
    "nozzle_length_m": "Nozzle length", "nozzle_geometry_method": "Nozzle geometry method",
    "casing_mass_method": "Casing mass method", "casing_mass_fraction": "Casing mass fraction",
    "casing_mass_kg": "Casing mass", "casing_volume_factor": "Casing volume factor",
    "igniter_mass_kg": "Igniter mass", "tvc_mass_kg": "Thrust-vector-control mass",
    # boosters
    "n_total": "Number of boosters", "n_ground_lit": "Number lit on the ground",
    "attach_stage": "Attached to stage", "prop_mass_each_kg": "Propellant mass each",
    "inert_mass_method": "Inert mass method", "inert_mass_fraction": "Inert mass fraction",
    "inert_mass_each_kg": "Inert mass each", "inert_margin_fraction": "Dry-mass growth margin (fraction)",
    "base_z_offset_m": "Base height above the core's nozzles", "radial_gap_m": "Radial gap to the core",
    "attach_hw_mass_each_kg": "Attachment hardware mass each", "dome_AR": "Dome aspect ratio",
    "wall_t_assumed_m": "Assumed wall thickness", "of_ratio": "Mixture ratio (oxidiser/fuel)",
    "isp_mode": "Isp used for sizing", "isp_weight_sl": "Sea-level share in the weighted Isp",
    # --- added at v1.1 after a first-time-user audit: names that did not say what the number was
    "ascent_time_override_s": "Ascent time for the loss estimate (override)",
    "avionics_mass_override_kg": "Avionics mass (override)",
    "user_mass_fuel_kg": "Fuel tank mass (my own figure)",
    "user_mass_oxidizer_kg": "Oxidiser tank mass (my own figure)",
    "attach_hardware_mass_each_kg": "Attachment hardware mass, each",
    "propellant_mass_each_kg": "Propellant mass, each",
    "yield_min_Pa": "Minimum yield strength",
    "safety_factor": "Safety factor",
    "earth_model": "Earth constants",
    "engine_a": "Engine mass relation: coefficient a", "engine_b": "Engine mass relation: coefficient b",
    "engine_c": "Engine mass relation: constant c, per engine",
    "engine_calibration_factor": "Engine mass correction factor",
    "gimbal_k": "Gimbal mass relation: coefficient k", "gimbal_exp": "Gimbal mass relation: exponent n",
    "thrust_structure_k": "Thrust structure mass per newton of thrust",
    "paf_a": "Payload adapter relation: slope a", "paf_b": "Payload adapter relation: constant b",
    "paf_small_payload_fraction": "Payload adapter mass / payload, small payloads",
    "paf_fraction_payload_threshold_kg": "Payload below which the adapter is a fraction",
    "avionics_small_kg": "Avionics mass, small launcher", "avionics_large_kg": "Avionics mass, large launcher",
    "avionics_payload_threshold_kg": "Payload separating small and large launchers",
    "avionics_upper_share": "Share of the avionics in the top stage",
    "tank_mer_density_tolerance": "Allowed density mismatch for the tank relation",
    "shrink_load_temperature_K": "Ambient temperature for cryogenic shrinkage",
    "tol": "Convergence tolerance", "max_iter": "Maximum iterations",
    "relax": "Under-relaxation factor (1 = none)",
}

#: a few fields need their section's context to be unambiguous
PATH_LABELS: dict = {
    "fairing.diameter_m": "Fairing diameter",
    "mission.orbit.type": "Orbit type",
    "stages.*.diameter_m": "Stage diameter",
    "stages.*.engine.name": "Engine name",
    "stages.*.motor.name": "Motor name",
    "boosters.name": "Booster name",
    "boosters.diameter_m": "Booster diameter",
    "boosters.exit_diameter_m": "Booster nozzle exit diameter",
    "boosters.nozzle_length_m": "Booster nozzle length",
    "boosters.burn_time_s": "Booster burn time",
    "boosters.residual_fraction": "Booster residual propellant",
    "mission.wind.profile": "Winds-aloft profile (wind speed against altitude, for the air loads)",
    # --- added at v1.1: a bare "Diameter", "Length" or "Material" does not say of what
    "mission.wind.kind": "What the wind profile represents",
    "fairing.nose_length_over_D": "Fairing nose length / diameter",
    "fairing.axial_clearance_m": "Payload clearance, axial",
    "fairing.radial_clearance_m": "Payload clearance, radial",
    "fairing.material": "Fairing material",
    "fairing.jettison_at_stage_start": "Fairing jettisoned at ignition of stage",
    "fairing.mass_override_kg": "Fairing mass (override)",
    "stages.*.max_length_m": "Maximum stage length",
    "stages.*.tank.diameter_m": "Tank diameter (blank = stage diameter)",
    "stages.*.tank.material": "Tank material",
    "stages.*.engine.length_m": "Engine length (chamber + nozzle)",
    "stages.*.motor.embed_fraction": "Fraction of the nozzle submerged in the case",
    "stages.*.motor.thrust_to_weight_ignition": "Thrust-to-weight at ignition",
    "boosters.max_length_m": "Maximum booster length",
    "boosters.type": "Booster type",
    "boosters.nose_length_over_D": "Booster nose length / diameter",
}

_SCATTER_NAMES = {"paf": "payload adapter mass", "isp_delivered": "delivered Isp",
                  "unpressurized_structure": "unpressurised structure mass", "engine_mass": "engine mass",
                  "thrust_structure": "thrust structure mass", "tank_mass": "tank mass",
                  "solid_casing": "solid motor casing mass", "avionics": "avionics mass",
                  "wiring": "wiring mass", "residual_propellant": "residual propellant"}
#: the folds of "Modelling assumptions" are named from the YAML block, and "Mer" is not a word
_ASSUMPTION_TOPICS = {"mer": "Mass-estimating relations", "mer_scatter": "Scatter of the relations (Monte Carlo)",
                      "convergence": "Sizing loop convergence", "earth_model": "Earth constants"}

_UNIT_SUFFIX = re.compile(r"_(kg|m|s|n|pa|deg|k|km|mps|m2|m3|kgs|g|usd|wyr)$", re.I)


def label_for(path: str) -> str:
    """A human label for an input path. Never fails: an unlisted field still gets something readable."""
    n = normalise(path)
    if n in PATH_LABELS:
        return PATH_LABELS[n]
    leaf = n.rsplit(".", 1)[-1]
    if n.startswith("mer_scatter."):
        # every row of this block is the same kind of number, and "Engine mass 0.37" does not say which
        return "Scatter, 1 sigma: " + _SCATTER_NAMES.get(leaf, leaf.replace("_", " "))
    if leaf in LEAF_LABELS:
        return LEAF_LABELS[leaf]
    pretty = _UNIT_SUFFIX.sub("", leaf).replace("_", " ").strip()
    return (pretty[:1].upper() + pretty[1:]) if pretty else leaf


# --------------------------------------------------------------------------- units a designer reads
#: The design file is SI throughout and stays so. These are the units the PAGE shows and accepts for a field,
#: as (unit shown, SI value of one of them): a chamber pressure is read in bar and a thrust in kN, and
#: nobody should have to count the zeros of 7093000 Pa. The page divides on the way out and multiplies on the
#: way back, so overrides, saved files and the engine never see anything but SI.
_DISPLAY_BY_LEAF = {
    "chamber_pressure_Pa": ("bar", 1.0e5), "pressure_fuel_Pa": ("bar", 1.0e5),
    "pressure_oxidizer_Pa": ("bar", 1.0e5),
    "max_dynamic_pressure_Pa": ("kPa", 1.0e3), "max_q_alpha_Pa_deg": ("kPa deg", 1.0e3),
    "sigma_allow_Pa": ("MPa", 1.0e6), "yield_min_Pa": ("MPa", 1.0e6), "E_Pa": ("GPa", 1.0e9),
    "thrust_vac_per_engine_N": ("kN", 1.0e3), "thrust_vac_total_N": ("kN", 1.0e3),
    "wall_thickness_assumed_m": ("mm", 1.0e-3), "wall_t_assumed_m": ("mm", 1.0e-3),
    "t_min_m": ("mm", 1.0e-3), "t_min_structural_m": ("mm", 1.0e-3),
    "corrosion_allowance_m": ("mm", 1.0e-3), "surface_roughness_m": ("mm", 1.0e-3),
}


def display_unit(path: str):
    """(unit shown, SI value of one of that unit) for an input path, or None to show it in its own SI unit."""
    return _DISPLAY_BY_LEAF.get(normalise(path).rsplit(".", 1)[-1])


# --------------------------------------------------------------------------- where an input belongs
#: Library blocks whose second path element is the name of the thing being described. Each one becomes its
#: own section, and each entry inside it its own fold, so "LOX/RP-1" and its mixture ratios stay together.
_LIBRARY_SECTIONS = (
    ("propellant_combinations", "Propellant combinations"),
    ("propellants", "Propellant library"),
    ("solid_propellants", "Solid propellant library"),
    ("tank_materials", "Material library"),
)

#: within a stage, which topic a sub-path belongs to
_STAGE_TOPICS = (("engine.", "Engine"), ("motor.", "Motor"), ("tank.", "Tankage"), ("layout.", "Layout"))
#: the topic holding the one control that decides what the rest of the stage even means. It is its own
#: topic, and `order_for_display` lifts it to the top of the stage, because liquid-or-solid governs which
#: of the other topics apply at all: a solid stage has a motor and no tanks, a liquid one the reverse.
#: Buried nineteen rows down inside "Propellants and size" it read as a detail, which it is not.
_SHAPE_TOPIC = "What kind of stage"
_MISSION_TOPICS = (("orbit.", "Orbit"), ("launch_site.", "Launch site"), ("losses.", "Ascent losses"),
                   ("wind.", "Winds aloft"), ("aerodynamics.", "Trajectory model"))
#: mission fields that describe how the ascent is flown rather than what the mission is
_TRAJECTORY_KEYS = ("atmosphere_model", "vertical_rise_s", "ascent_profile", "parking_altitude_m", "last_ascent_stage",
                    "max_dynamic_pressure_Pa", "max_q_alpha_Pa_deg")
_STAGE_MASS_KEYS = ("feed_system_mass_per_engine_kg", "pressurant_mass_fraction_of_propellant",
                    "separation_hardware_mass_kg", "other_equipment_mass_kg", "structure_mass_factor",
                    "inert_mass_margin_fraction", "structure_mode", "structural_factor_s",
                    "avionics_mass_override_kg")


def place(path: str) -> tuple:
    """(section, topic) for an input path. The section is the big heading, the topic the fold inside it."""
    n = normalise(path)
    # work on the dotted spelling throughout, so stages[0]. and stages.0. route identically
    p = re.sub(r"\[(\d+)\]", r".\1", str(path))
    if p.startswith("mission."):
        rest = p[len("mission."):]
        for pre, topic in _MISSION_TOPICS:
            if rest.startswith(pre):
                return "Mission", topic
        if rest in _TRAJECTORY_KEYS:
            return "Mission", "Trajectory model"
        if rest == "pad_height_m":
            return "Mission", "Winds aloft"          # it raises the vehicle into the ground-wind profile
        if rest == "cost_year" or rest.startswith("cost."):
            return "Mission", "Cost"                 # shown on the Cost tab, not in the input list
        return "Mission", "Payload and orbit"
    if p.startswith("fairing."):
        return "Payload fairing", "Fairing"
    if p.startswith("vehicle."):
        return "Vehicle", "Staging and adapter"
    if p.startswith("constraints."):
        return "Limits to respect", "Limits"
    if p.startswith("boosters."):
        return "Strap-on boosters", "Boosters"
    if p.startswith("stages."):
        try:
            idx = int(p.split(".")[1]) + 1
        except (IndexError, ValueError):
            return "Stages", "Stage"
        rest = p.split(".", 2)[2] if len(p.split(".", 2)) > 2 else ""
        if rest == "stage_type":
            return f"Stage {idx}", _SHAPE_TOPIC
        for pre, topic in _STAGE_TOPICS:
            if rest.startswith(pre):
                return f"Stage {idx}", topic
        if rest in _STAGE_MASS_KEYS:
            return f"Stage {idx}", "Mass estimating"
        if rest == "max_length_m":
            return f"Stage {idx}", "Layout"
        return f"Stage {idx}", "Propellants and size"
    # Library blocks are keyed by the thing they describe, so each entry gets its OWN fold. Flattened into
    # one topic they are unusable: the propellant library alone is 75 rows with "Density" appearing fifteen
    # times, and the combinations 132 rows with no way to tell which O/F belongs to which pair. A user who
    # scrolls to the first "Density" and reads its description sees LOX's, and reasonably concludes the tank
    # is always sized for LOX - which it is not.
    for prefix, section in _LIBRARY_SECTIONS:
        if p.startswith(prefix + "."):
            rest = p[len(prefix) + 1:]
            name = rest.split(".", 1)[0] if "." in rest else rest
            return section, name or section
    block = n.split(".", 1)[0]
    return "Modelling assumptions", _ASSUMPTION_TOPICS.get(block, block.replace("_", " ").title())


#: sections shown expanded when the page first loads; the rest start folded.
#: NOTE: this names Stage 1 and Stage 2 only because it was written when every design had two stages. Use
#: `open_sections_for`, which adds whatever stages the design actually has - a hardcoded pair left a
#: three-stage design opening with its third stage folded away, and a stage added with the stage-count
#: control arriving collapsed, with the fields the user was just told to fill hidden behind a disclosure.
OPEN_SECTIONS = ("Mission", "Stage 1", "Stage 2", "Payload fairing", "Limits to respect")


def open_sections_for(items: list) -> list:
    """The sections to show expanded for THIS design: the fixed set, plus every stage it has.

    The stages are the design. A vehicle with six of them should not open with four of them hidden.
    """
    out = list(OPEN_SECTIONS)
    for it in items:
        sec = it.get("section") or ""
        if sec.startswith("Stage ") and sec not in out:
            out.append(sec)
    return out


def describe_inputs(items: list, assump: dict | None = None) -> list:
    """Attach label, choices, section and topic to each register row, in place-friendly form."""
    lib = library_choices(assump)
    out = []
    have = {it["path"] for it in items}
    controllers = set()
    for it in items:
        section, topic = place(it["path"])
        ch = choices_for(it["path"], lib)
        row = dict(it)
        row.update(label=label_for(it["path"]), section=section, topic=topic,
                   # a choice may carry a third element, the heading it is listed under (the launch sites'
                   # continent); the page draws those as groups in the dropdown
                   choices=[dict({"value": c[0], "label": c[1]}, **({"group": c[2]} if len(c) > 2 and c[2] else {}))
                            for c in ch] if ch else None)
        du = None if ch else display_unit(it["path"])
        if du:
            row.update(display_units=du[0], display_factor=du[1])
        sw = shown_when(it["path"], have)
        if sw:
            row["shown_when"] = sw
            controllers.add(sw["path"])
        out.append(row)
    for row in out:
        if row["path"] in controllers:
            row["controls"] = True                 # a choice other inputs hang on is never folded away
    return order_for_display(out)


def order_for_display(rows: list) -> list:
    """Put the shape-deciding control at the top of its stage, leaving everything else as it was.

    The GUI groups by section and then by topic in the order the rows arrive, so a row's position in this
    list is its position on the page. `stage_type` arrives from the register wherever the YAML happens to
    list it - row 19 of Stage 1 on the check cases, below the whole "Mass estimating" topic. It decides
    whether the stage has an engine and tanks or a motor and a casing, so it goes first; the sort is stable,
    so nothing else moves relative to anything else.
    """
    order = {}
    for i, r in enumerate(rows):
        sec = r.get("section") or ""
        if sec not in order:
            order[sec] = i
    def key(pair):
        i, r = pair
        sec = r.get("section") or ""
        return (order[sec], 0 if r.get("topic") == _SHAPE_TOPIC else 1, i)
    rows = [r for _, r in sorted(enumerate(rows), key=key)]
    # Within a fold: the pick that fills other fields leads, and an input that is read only under one setting
    # of a choice sits directly beneath that choice. Folds keep the order they first appear in.
    folds, seq = {}, []
    for r in rows:
        k = (r.get("section"), r.get("topic"))
        if k not in folds:
            folds[k] = []
            seq.append(k)
        folds[k].append(r)
    out = []
    for k in seq:
        fold = folds[k]
        lead = [r for r in fold if r["path"].rsplit(".", 1)[-1] in _LEAD_LEAVES]
        rest = [r for r in fold if r not in lead]
        deps = [r for r in rest if r.get("shown_when") and any(x["path"] == r["shown_when"]["path"] for x in rest)]
        rest = [r for r in rest if r not in deps]
        placed = []
        for r in rest:
            placed.append(r)
            placed.extend(d for d in deps if d["shown_when"]["path"] == r["path"])
        out.extend(lead + placed)
    return out


# --------------------------------------------------------------------------- inputs that depend on a choice
#: dependent input -> (the choice beside it that decides whether it is read, the values for which it is,
#: whether it must then be filled). Every pair is a sibling pair: same block of the design file. Each rule was
#: checked against the code that reads the input - an input hidden here is one the chosen method never looks
#: at, so showing it invited the user to set a number that changes nothing.
SHOWN_WHEN: dict = {
    "stages.*.engine.cstar_mps": ("geometry_method", ("book_mer",), True),
    "stages.*.engine.length_m": ("geometry_method", ("user",), True),
    "stages.*.engine.exit_diameter_m": ("geometry_method", ("user",), True),
    "stages.*.engine.isp_sl_weight": ("isp_effective_mode", ("weighted",), False),
    "stages.*.engine.isp_effective_user_s": ("isp_effective_mode", ("user",), True),
    "stages.*.engine.mass_user_per_engine_kg": ("mass_method", ("user",), True),
    "stages.*.engine.gimbal_user_per_engine_kg": ("gimbal_method", ("user",), True),
    "stages.*.motor.nozzle_length_m": ("nozzle_geometry_method", ("user",), True),
    "stages.*.motor.exit_diameter_m": ("nozzle_geometry_method", ("user",), True),
    "stages.*.motor.isp_sl_weight": ("isp_effective_mode", ("weighted",), False),
    "stages.*.motor.isp_effective_user_s": ("isp_effective_mode", ("user",), True),
    "stages.*.motor.casing_mass_fraction": ("casing_mass_method", ("mass_fraction",), True),
    "stages.*.motor.casing_mass_kg": ("casing_mass_method", ("user_mass",), True),
    "stages.*.motor.thrust_to_weight_ignition": ("thrust_mode", ("tw_ignition",), True),
    "stages.*.motor.thrust_vac_total_N": ("thrust_mode", ("fixed_thrust",), True),
    "stages.*.motor.burn_time_s": ("thrust_mode", ("burn_time",), True),
    "stages.*.structural_factor_s": ("structure_mode", ("aggregate_s",), True),
    "stages.*.tank.user_mass_fuel_kg": ("mass_method_fuel", ("user_mass",), True),
    "stages.*.tank.user_mass_oxidizer_kg": ("mass_method_oxidizer", ("user_mass",), True),
    "stages.*.tank.mass_fraction_fuel": ("mass_method_fuel", ("mass_fraction",), True),
    "stages.*.tank.mass_fraction_oxidizer": ("mass_method_oxidizer", ("mass_fraction",), True),
    "mission.losses.gravity_mps": ("model", ("user",), True),
    "mission.losses.drag_mps": ("model", ("user",), True),
    "mission.losses.steering_mps": ("model", ("user",), True),
    "mission.wind.gust_increment_mps": ("kind", ("steady",), True),
    "vehicle.dv_fixed_mps": ("dv_allocation_mode", ("fixed",), True),
    "vehicle.optimise_objective": ("optimise_dv_split", (True,), False),
    "boosters.inert_mass_fraction": ("inert_mass_method", ("mass_fraction",), True),
    "boosters.inert_mass_each_kg": ("inert_mass_method", ("user_mass",), True),
    "boosters.isp_sl_weight": ("isp_effective_mode", ("weighted",), False),
    "boosters.fuel": ("type", ("liquid",), True),
    "boosters.oxidizer": ("type", ("liquid",), True),
    "boosters.mixture_ratio_OF": ("type", ("liquid",), True),
    "boosters.propellant": ("type", ("solid",), True),
}
#: inputs that lead their fold, because picking one fills in others
_LEAD_LEAVES = ("from_database", "propellant_combination")


def shown_when(path: str, have: set):
    """{path, values, required} for an input that is read only under one setting of a choice beside it, or
    None. `have` is the set of paths this design has: a rule whose controlling choice is absent is dropped,
    because hiding an input behind a control the page cannot show would lose it altogether."""
    rule = SHOWN_WHEN.get(normalise(path))
    if not rule:
        return None
    ctrl = str(path).rsplit(".", 1)[0] + "." + rule[0]
    if ctrl not in have:
        return None
    return {"path": ctrl, "values": list(rule[1]), "required": bool(rule[2])}


def engine_map(path: str | None = None) -> dict:
    """What naming each real engine or motor writes into the design, keyed by its name, for the page.

    The mappings are engine_db's own (ENGINE_FIELDS, STAGE_FIELDS, MOTOR_FIELDS), so the page fills exactly
    the fields the loader would. A value the source does not give is None, and the page says so instead of
    writing anything."""
    from . import engine_db
    out = {}
    try:
        rows = engine_db.entries(path)
    except Exception:                                                # noqa: BLE001 - no database, no map
        return out
    booster = {"isp_vac_s": "isp_vac_s", "burn_time_s": "burn_time_s",
               "propellant_mass_each_kg": "propellant_mass_kg", "prop_mass_each_kg": "propellant_mass_kg",
               "inert_mass_fraction": "casing_k", "diameter_m": "diameter_m", "name": "name"}
    for e in rows:
        solid = e.get("kind") == "solid"
        item = {"kind": e.get("kind", "liquid"), "confidence": e.get("confidence") or "unknown",
                "source": e.get("source") or "no source given"}
        if solid:
            item["motor"] = {k: e.get(v) for k, v in engine_db.MOTOR_FIELDS.items()}
            item["booster"] = {k: e.get(v) for k, v in booster.items()}
        else:
            item["engine"] = {k: e.get(v) for k, v in engine_db.ENGINE_FIELDS.items()}
            item["stage"] = {k: e.get(v) for k, v in engine_db.STAGE_FIELDS.items()}
        out[e["name"]] = item
    return out
