"""Convergence detection, divergence/infeasibility detection."""
import pytest
from helpers import default_result, default_spec
from launch_vehicle.convergence import size_vehicle, SizingError


def test_converges_with_tolerance_and_reports_iterations():
    r = default_result()
    assert r.converged and r.status == "converged"
    assert r.residual < 1e-9 and 3 < r.iterations < 60
    hist = [h["residual"] for h in r.history]
    assert hist[-1] < hist[2]                                    # residual decreases overall


def test_iteration_limit_is_not_reported_as_converged():
    r = default_result({"assumptions.convergence.max_iter": 3})
    assert not r.converged
    assert "max iterations" in r.status
    assert any(i.code == "CONV" and i.level == "ERROR" for i in r.issues)


def test_under_relaxation_reaches_same_fixed_point():
    a = default_result()
    b = default_result({"assumptions.convergence.relax": 0.5})
    assert b.converged and b.iterations > a.iterations
    assert b.glom_kg == pytest.approx(a.glom_kg, rel=1e-6)


def test_impossible_requirement_detected_as_infeasible():
    # dv = 40 km/s with Isp ~300 s: residual-propellant fraction makes the stage unsizeable -> must raise, not return garbage
    with pytest.raises(SizingError, match="infeasible"):
        size_vehicle(default_spec({"mission.delta_v_override_mps": 40000.0}))


def test_aggregate_structure_too_heavy_is_infeasible():
    from helpers import book_tsto_overrides
    o = book_tsto_overrides()
    o["stages.1.structural_factor_s"] = 0.30                    # mu2 = 4.27 -> mu*s = 1.28 >= 1
    with pytest.raises(SizingError, match="infeasible"):
        size_vehicle(default_spec(o))


def test_result_is_deterministic():
    assert default_result().glom_kg == default_result().glom_kg


def test_example_configurations_run_end_to_end():
    import os
    from helpers import ROOT, ASSUMP
    from launch_vehicle.config_io import load_design
    for f in ("example_design.yaml", "example_3stage_leo.yaml"):
        r = size_vehicle(load_design(os.path.join(ROOT, "examples", f), ASSUMP))
        assert r.converged
        assert not any(i.level == "ERROR" for i in r.issues)
        assert sum(s.dv_check_mps for s in r.stages) == pytest.approx(r.dv_required_mps, abs=1e-5)
