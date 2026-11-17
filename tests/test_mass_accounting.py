"""Mass accounting, stage separation and conservation of mass across burns."""
import pytest
from helpers import default_result, custom_spec
from launch_vehicle.convergence import size_vehicle
from launch_vehicle.units import G0


def test_single_stage_mass_accounting():
    def mod(design, assump):
        design["stages"] = design["stages"][:1]
        design["vehicle"]["dv_fractions"] = [1.0]
        design["fairing"]["diameter_m"] = design["stages"][0]["diameter_m"]
        design["fairing"]["jettison_at_stage_start"] = 2          # N+1: carried to burnout (conservative)
        design["mission"]["delta_v_override_mps"] = 5000.0
        design["mission"]["payload_envelope_diameter_m"] = 3.0
        design["stages"][0]["engine"]["thrust_to_weight_ignition"] = 1.3
    r = size_vehicle(custom_spec(mod))
    s = r.stages[0]
    assert r.converged
    # GLOM = payload + PAF + fairing + dry + loaded propellant
    assert r.glom_kg == pytest.approx(r.payload_mass_kg + r.paf_mass_kg + r.fairing_mass_kg + s.m_dry_kg + s.m_prop_loaded_kg, rel=1e-12)
    # burnout = payload+PAF+fairing + dry + residual + margin
    assert s.m_burnout_kg == pytest.approx(r.payload_mass_kg + r.paf_mass_kg + r.fairing_mass_kg + s.m_dry_kg + s.m_residual_kg + s.m_margin_prop_kg, rel=1e-12)
    # rocket equation reproduces the allocated dv (Isp_eff = 290 s weighted)
    assert s.dv_check_mps == pytest.approx(5000.0, rel=1e-9)


def test_multistage_mass_accounting_closes():
    r = default_result()
    total = r.payload_mass_kg + r.paf_mass_kg + r.fairing_mass_kg + sum(s.m_dry_kg + s.m_prop_loaded_kg for s in r.stages)
    assert r.glom_kg == pytest.approx(total, rel=1e-12)
    assert r.stages[0].m_ignition_kg + 0.0 == pytest.approx(r.glom_kg, rel=1e-9)          # stage-1 ignition mass is the GLOM


def test_conservation_of_mass_across_burns_and_separation():
    r = default_result()
    s1, s2 = r.stages
    for s in r.stages:
        # ignition - start-up - mission propellant = burnout (before separation)
        assert s.m_ignition_kg - s.m_startup_kg - s.m_prop_mission_kg == pytest.approx(s.m_burnout_kg, rel=1e-9)
        # loaded propellant partition
        assert s.m_prop_loaded_kg == pytest.approx(s.m_prop_mission_kg + s.m_startup_kg + s.m_residual_kg + s.m_margin_prop_kg, rel=1e-12)
        # separation removes exactly dry + residual + margin
        assert s.m_burnout_kg - s.m_after_sep_kg == pytest.approx(s.m_dry_kg + s.m_residual_kg + s.m_margin_prop_kg, rel=1e-9)
    # fairing jettisoned at the start of stage 2: stage-2 ignition mass = what stage 1 leaves behind minus the fairing
    assert s1.m_after_sep_kg - r.fairing_mass_kg == pytest.approx(s2.m_ignition_kg, rel=1e-9)


def test_discarded_hardware_excluded_from_next_stage():
    r = default_result()
    s2 = r.stages[1]
    # Stage 2 carries only payload + PAF (stage-1 hardware and fairing are gone)
    assert s2.m_carried_kg == pytest.approx(r.payload_mass_kg + r.paf_mass_kg, rel=1e-12)
    # Stage 1 carries stage 2 entire + payload + PAF + fairing.
    # The carried mass is formed from the upper stage's masses of the SAME sweep while the reported stage-2 dry
    # mass is the value that sweep started from, so the identity holds to the solver's convergence tolerance
    # (1e-9 relative), not to machine precision.
    s1 = r.stages[0]
    assert s1.m_carried_kg == pytest.approx(r.payload_mass_kg + r.paf_mass_kg + r.fairing_mass_kg + s2.m_dry_kg + s2.m_prop_loaded_kg, rel=1e-8)


def test_fairing_carried_to_burnout_changes_upper_stage():
    base = default_result()
    kept = default_result({"fairing.jettison_at_stage_start": 3})        # N+1: never jettisoned during burns
    assert kept.stages[1].m_carried_kg == pytest.approx(base.stages[1].m_carried_kg + base.fairing_mass_kg, rel=1e-9)
    assert kept.glom_kg > base.glom_kg


def test_residual_and_loading_margin_not_consumed():
    r = default_result()
    s = r.stages[0]
    assert s.m_residual_kg == pytest.approx(0.02 * s.m_prop_mission_kg, rel=1e-12)
    assert s.m_margin_prop_kg == pytest.approx(0.005 * s.m_prop_mission_kg, rel=1e-12)
    assert s.m_inert_burnout_kg == pytest.approx(s.m_dry_kg + s.m_residual_kg + s.m_margin_prop_kg, rel=1e-12)


def test_dry_mass_components_sum_to_stage_dry_mass_no_double_count():
    r = default_result()
    for s in r.stages:
        assert sum(s.components.values()) == pytest.approx(s.m_dry_kg, rel=1e-6)
        base = sum(v for k, v in s.components.items() if k != "Mass growth margin")
        assert s.components["Mass growth margin"] == pytest.approx(0.10 * base, rel=1e-9)
    # ledger carries the same dry mass exactly once
    for s in r.stages:
        ledger_dry = sum(i.mass_kg for i in r.ledger if i.stage == s.index and i.kind == "dry")
        assert ledger_dry == pytest.approx(s.m_dry_kg, rel=1e-6)


def test_delta_v_summation():
    r = default_result()
    assert sum(s.dv_mps for s in r.stages) == pytest.approx(r.dv_required_mps, rel=1e-12)
    assert sum(s.dv_check_mps for s in r.stages) == pytest.approx(r.dv_required_mps, rel=1e-8)
    assert r.dv_achieved_mps == pytest.approx(r.dv_required_mps, abs=1e-5)


def test_burn_time_and_mass_flow_consistency():
    r = default_result()
    for s in r.stages:
        assert s.burn_time_s * s.mdot_kgs == pytest.approx(s.m_prop_mission_kg, rel=1e-12)
        # T = mdot g0 Isp for the reference condition
        spec_st = r.spec.stages[s.index - 1]
        isp_ref = spec_st.engine.isp_sl_s if s.thrust_ref_condition == "sea_level" else spec_st.engine.isp_vac_s
        assert s.thrust_ref_N == pytest.approx(s.mdot_kgs * G0 * isp_ref, rel=1e-12)
        assert s.tw_ignition == pytest.approx(s.thrust_ref_N / (s.m_ignition_kg * G0), rel=1e-12)
    assert r.stages[0].tw_ignition == pytest.approx(1.3, rel=1e-9)         # requested T/W0 honoured
    assert r.stages[1].tw_ignition == pytest.approx(0.7, rel=1e-9)
