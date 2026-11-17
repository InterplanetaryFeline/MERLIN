import copy, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESIGN = os.path.join(ROOT, "config", "default_design.yaml")
ASSUMP = os.path.join(ROOT, "config", "engineering_assumptions.yaml")
from launch_vehicle.config_io import load_design, load_yaml_annotated, build_spec
from launch_vehicle.convergence import size_vehicle


def default_spec(overrides=None):
    return load_design(DESIGN, ASSUMP, overrides)


def default_result(overrides=None):
    return size_vehicle(default_spec(overrides))


def custom_spec(modify):
    """Load the raw (unwrapped) design dicts, let `modify(design, assump)` edit them, and build the spec."""
    design, meta, reg = load_yaml_annotated(DESIGN)
    assump, _, reg = load_yaml_annotated(ASSUMP, reg)
    modify(design, assump)
    return build_spec(design, assump, reg, name="test")


def book_tsto_overrides():
    """Edberg & Costa Example 1 (p.480): Isp 291/340 s, dv 3757/4842 m/s, s 0.08/0.10, 10 t payload; no PAF/fairing/start-up."""
    o = {"mission.delta_v_override_mps": 8599.0, "mission.payload_adapter_mass_kg": 0.0, "fairing.mass_override_kg": 0.0,
         "vehicle.dv_allocation_mode": "fixed", "vehicle.dv_fixed_mps": [3757.0, 4842.0],
         "stages.0.engine.isp_effective_mode": "user", "stages.0.engine.isp_effective_user_s": 291.0,
         "stages.0.structure_mode": "aggregate_s", "stages.0.structural_factor_s": 0.08,
         "stages.1.structure_mode": "aggregate_s", "stages.1.structural_factor_s": 0.10,
         "stages.0.startup_time_s": 0.0, "stages.1.startup_time_s": 0.0}
    return o
