"""Typed data structures for the vehicle model (inputs and results). SI units everywhere."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PropellantSpec:
    name: str
    density_kg_m3: float
    boiling_K: Optional[float]            # None for storables / room-temperature liquids
    insulation_kg_m2: float
    tank_mer_per_kg: Optional[float]      # Table 8.6 style coefficient (tank mass / propellant mass)
    tank_mer_ref_density: Optional[float]
    source: str = ""


@dataclass
class TankMaterial:
    name: str
    rho_kg_m3: float
    alpha_per_K: float
    sigma_allow_Pa: float
    joint_efficiency: float
    safety_factor: float
    corrosion_allowance_m: float
    t_min_m: float
    # Chapter 10 stress analysis only; defaulted so a design file written before v0.8 still loads
    E_Pa: float = 69.0e9              # book Example 2, p.637 (aluminium)
    poisson: float = 0.31             # book Sec. 10.3.1.1, p.638
    t_min_structural_m: float = 0.0005  # book Table 10.2, p.634


@dataclass
class TankSpec:
    arrangement: str                      # 'separate' | 'common_bulkhead'
    order_bottom_to_top: list             # e.g. ['oxidizer', 'fuel']
    dome_AR: float
    ullage_fraction: dict                 # {'fuel':..,'oxidizer':..}
    mass_method: dict                     # {'fuel':..,'oxidizer':..}: akin_propellant_mass|akin_volume|pressure_vessel|mass_fraction|user_mass
    pressure_Pa: dict                     # operating (MEOP-ish) pressure per role, for pressure_vessel
    wall_t_assumed_m: dict                # thickness used for geometry when method != pressure_vessel
    mass_fraction: dict                   # for mass_fraction method (tank mass / propellant mass)
    user_mass_kg: dict
    material: TankMaterial
    load_temperature_K: float
    insulated: dict                       # {'fuel': bool, 'oxidizer': bool}
    diameter_m: Optional[float] = None    # tank external diameter if smaller than the stage (upper stages with
    #                                       tanks inside a wider skirt); None = equal to the stage diameter


@dataclass
class EngineSpec:
    name: str
    n_engines: int
    thrust_vac_per_engine_N: Optional[float]   # fixed-thrust mode
    tw_ignition: Optional[float]               # rubber-engine mode (thrust set by T/W at ignition)
    isp_vac_s: float
    isp_sl_s: Optional[float]
    isp_mode: str                              # vacuum | weighted | user
    isp_weight_sl: float
    isp_user_s: Optional[float]
    expansion_ratio: float
    chamber_pressure_Pa: float
    length_m: float
    exit_diameter_m: float
    embed_fraction: float                      # fraction of length inside the aft skirt (rest protrudes)
    mass_method: str                           # mer | user
    mass_user_kg: Optional[float]
    gimbal_method: str                         # mer | user | none
    gimbal_user_kg: Optional[float]
    throttle_min: float = 1.0                  # informational only in v1
    geometry_method: str = "user"              # user | book_mer (Eqs. 8:28-8:33)
    cstar_mps: Optional[float] = None          # delivered c*, needed by book_mer (Table 8.12)
    cycle: Optional[str] = None                # power cycle (engine database); informational + a Pc sanity check
    db_entry: Optional[str] = None             # engine-database row this stage was filled from, if any


@dataclass
class SolidPropellantSpec:
    name: str
    density_kg_m3: float
    isp_note: str = ""
    source: str = ""
    # internal ballistics only; defaulted so a propellant library written before v0.8 still loads
    c_star_mps: float = 0.0           # book Table 4.7
    burn_rate_exponent: float = 0.0   # de Saint Robert's n; 0 means "not given, do not run the solution"


@dataclass
class MotorSpec:
    """Solid rocket motor (SRM). The casing mass includes insulation, nozzle, thrust structure and TVC (book p.490)."""
    name: str
    n_motors: int                              # must be 1 for a serial solid stage
    thrust_mode: str                           # tw_ignition | fixed_thrust | burn_time
    thrust_vac_total_N: Optional[float]
    tw_ignition: Optional[float]
    burn_time_s: Optional[float]
    isp_vac_s: float
    isp_sl_s: Optional[float]
    isp_mode: str
    isp_weight_sl: float
    isp_user_s: Optional[float]
    expansion_ratio: float
    chamber_pressure_Pa: float
    cstar_mps: float                           # delivered c* used by Eq. 8:28
    nozzle_geometry_method: str                # book_mer | user
    exit_diameter_m: Optional[float]
    nozzle_length_m: Optional[float]
    embed_fraction: float                      # submerged fraction of the nozzle inside the aft dome/skirt
    casing_mass_method: str                    # book_steel | book_composite | mass_fraction | user_mass
    casing_mass_fraction: Optional[float]
    casing_mass_kg: Optional[float]
    casing_volume_factor: float                # Eq. 8:24 (1.12)
    dome_AR: float                             # 1.0 = hemispherical (book recommendation for SRMs)
    wall_t_assumed_m: float
    tvc_mass_kg: float = 0.0                   # only if the user wants it separate from the casing MER
    igniter_mass_kg: float = 0.0
    cycle: Optional[str] = None                # 'solid'; kept for symmetry with EngineSpec
    db_entry: Optional[str] = None             # name of the engine-database row this motor was filled from


@dataclass
class BoosterSpec:
    """Strap-on boosters ('zeroth stage'), burning in parallel with the stage they are attached to."""
    name: str
    n_total: int
    n_ground_lit: int                          # the remainder ignite when the ground-lit group burns out
    kind: str                                  # solid | liquid
    attach_stage: int
    propellant: Optional[str]                  # solid propellant name
    fuel: Optional[str]
    oxidizer: Optional[str]
    of_ratio: Optional[float]
    isp_vac_s: float
    isp_sl_s: Optional[float]
    isp_mode: str
    isp_weight_sl: float
    prop_mass_each_kg: float                   # mission propellant per booster
    burn_time_s: float
    residual_fraction: float
    inert_mass_method: str                     # book_steel | book_composite | mass_fraction | user_mass
    inert_mass_fraction: Optional[float]
    inert_mass_each_kg: Optional[float]
    inert_margin_fraction: float
    diameter_m: float
    dome_AR: float
    nose_length_over_D: float
    base_z_offset_m: float                     # nozzle exit plane above the core stage-1 nozzle exit plane
    radial_gap_m: float
    exit_diameter_m: float
    nozzle_length_m: float
    attach_hw_mass_each_kg: float = 0.0
    casing_volume_factor: float = 1.12
    wall_t_assumed_m: float = 0.0


@dataclass
class StageSpec:
    index: int                                 # 1 = first stage
    name: str
    fuel: str
    oxidizer: str
    of_ratio: float                            # O/F = m_ox / m_fuel (book's f = 1/OF)
    residual_fraction: float
    loading_margin_fraction: float
    startup_time_s: float
    diameter_m: float
    structure_mode: str                        # bottom_up | aggregate_s
    structural_factor_s: Optional[float]       # book s = ms/(ms+mp), used by aggregate_s
    tank: TankSpec
    engine: EngineSpec
    aft_skirt_over_D: float
    intertank_over_D: float
    fwd_skirt_over_D: float
    interstage_min_length_m: float
    interstage_clearance_m: float
    interstage_half_angle_deg: float
    feed_mass_per_engine_kg: float
    pressurant_fraction: float
    separation_hw_kg: float
    other_mass_kg: float
    inert_margin_fraction: float
    structure_mass_factor: float = 1.0       # multiplies tank + unpressurised structure MERs (book p.498: ~0.8 for composites)
    max_length_m: Optional[float] = None
    avionics_kg_override: Optional[float] = None
    stage_type: str = "liquid"               # liquid | solid
    propellant: Optional[str] = None         # solid propellant name (solid stages)
    motor: Optional[MotorSpec] = None        # solid stages

    @property
    def is_solid(self) -> bool:
        return self.stage_type == "solid"

    @property
    def prop_system(self):
        """The propulsion spec of this stage, whichever type it is (EngineSpec or MotorSpec)."""
        return self.motor if self.is_solid else self.engine


@dataclass
class FairingSpec:
    diameter_m: float
    nose_length_over_D: float
    axial_clearance_m: float
    radial_clearance_m: float
    envelope_diameter_m: float
    envelope_length_m: float
    material: str                              # metal | composite
    jettison_stage: int                        # jettisoned at the START of this stage's burn
    mass_override_kg: Optional[float] = None


@dataclass
class ConvergenceSettings:
    tol: float
    max_iter: int
    relax: float


@dataclass
class VehicleSpec:
    name: str
    mission: dict
    payload_mass_kg: float
    paf_mass_override_kg: Optional[float]
    paf_length_over_D: float
    fairing: FairingSpec
    stages: list
    dv_mode: str
    dv_fractions: Optional[list]
    dv_fixed: Optional[list]
    earth_model: str
    mer: dict                                  # all MER coefficients (engineering_assumptions)
    propellants: dict                          # name -> PropellantSpec
    convergence: ConvergenceSettings
    constraints: dict
    inputs_register: list = field(default_factory=list)
    paf_method: str = "mer"                    # mer | fraction | auto (errata p.443: 0.15 m_PL for small payloads)
    #: When true the delta-v allocation is REPLACED by the optimum before the vehicle is sized, so the
    #: design that is reported and the design that was optimised are the same vehicle. Off by default: the
    #: split is a decision the user makes, and a tool that silently re-made it would be reporting someone
    #: else's design. See `optimization.apply_optimum`.
    optimise_dv: bool = False
    optimise_objective: str = "glom"           # glom | cost | payload
    solid_propellants: dict = field(default_factory=dict)   # name -> SolidPropellantSpec
    boosters: Optional[BoosterSpec] = None
    engine_db_notes: list = field(default_factory=list)     # one entry per resolved engine-database reference
    propellant_combination_notes: list = field(default_factory=list)   # one per resolved combination reference
    propellant_combinations: dict = field(default_factory=dict)        # name -> Combination (reference data)
    mer_scatter: dict = field(default_factory=dict)         # relative 1-sigma per MER group (uncertainty.py)

    def boosters_on(self, stage_index: int):
        return self.boosters if (self.boosters and self.boosters.attach_stage == stage_index) else None


# ------------------------------------------------------------------ results
@dataclass
class StageResult:
    index: int
    name: str
    dv_mps: float
    isp_eff_s: float
    mass_ratio: float
    m_carried_kg: float                 # everything above the stage at its ignition (incl. fairing if not yet jettisoned)
    m_prop_mission_kg: float            # consumed in the delta-v producing burn
    m_startup_kg: float                 # consumed in startup, no delta-v credit
    m_residual_kg: float
    m_margin_prop_kg: float
    m_prop_loaded_kg: float
    m_dry_kg: float
    m_inert_burnout_kg: float           # dry + residual + loading margin (book 'structure' mass convention)
    m_ignition_kg: float                # stack mass at ignition incl. startup propellant
    m_burn_start_kg: float              # mass at start of delta-v burn (startup consumed)
    m_burnout_kg: float                 # mass at end of burn, before separation
    m_after_sep_kg: float
    structural_factor_s: float          # book convention, from final masses
    dv_check_mps: float                 # recomputed from m_burn_start / m_burnout
    thrust_ref_N: float
    thrust_ref_condition: str
    thrust_vac_N: float
    thrust_sl_N: Optional[float]
    mdot_kgs: float
    burn_time_s: float
    tw_ignition: float
    tw_burnout: float
    accel_max_g: float
    engine_mass_each_kg: float
    prop_masses: dict                   # {'oxidizer': {...}, 'fuel': {...}} loaded masses by role
    components: dict = field(default_factory=dict)   # name -> mass (bottom-up)
    tanks: list = field(default_factory=list)        # TankGeometry list
    layout: list = field(default_factory=list)       # Segment list (local)
    length_m: float = 0.0
    warnings: list = field(default_factory=list)
    stage_type: str = "liquid"
    phases: list = field(default_factory=list)       # parallel-burn phases (boosters attached), else empty
    motor_info: dict = field(default_factory=dict)   # solid stages: web, bore, implied burn rate, casing k
    nozzle_dims: object = None                       # EngineDimensions when computed from the book MERs
    envelope: object = None                          # PropEnvelope actually used for layout and drawing

    @property
    def is_solid(self) -> bool:
        return self.stage_type == "solid"


@dataclass
class BoosterResult:
    name: str
    n_total: int
    n_ground_lit: int
    kind: str
    attach_stage: int
    isp_eff_s: float
    m_prop_each_kg: float
    m_inert_each_kg: float
    m_loaded_each_kg: float
    m_total_kg: float
    thrust_vac_each_N: float
    thrust_sl_each_N: Optional[float]
    mdot_each_kgs: float
    burn_time_s: float
    diameter_m: float
    length_m: float
    case: object = None
    components: dict = field(default_factory=dict)
    z0: float = 0.0
    z1: float = 0.0
    x_offset_m: float = 0.0
    structural_factor_s: float = 0.0
    warnings: list = field(default_factory=list)


@dataclass
class VehicleResult:
    spec: VehicleSpec
    budget: object
    stages: list
    payload_mass_kg: float
    paf_mass_kg: float
    fairing_mass_kg: float
    glom_kg: float
    dv_required_mps: float
    dv_achieved_mps: float
    converged: bool
    status: str
    iterations: int
    residual: float
    history: list
    geometry: object = None
    ledger: list = field(default_factory=list)
    mass_properties: dict = field(default_factory=dict)
    issues: list = field(default_factory=list)
    allocation: list = field(default_factory=list)
    boosters: object = None                          # BoosterResult or None
    liftoff_thrust_N: float = 0.0
    liftoff_tw: float = 0.0
