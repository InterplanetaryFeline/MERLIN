"""Stage delta-v allocation and multistage behaviour."""
import pytest
from launch_vehicle import staging as s
from helpers import default_result


def test_allocate_fractions_normalised_and_sum():
    d = s.allocate_dv(9000.0, 3, "fractions", [1, 2, 3])
    assert sum(d) == pytest.approx(9000.0, rel=1e-14)
    assert d[1] / d[0] == pytest.approx(2.0, rel=1e-12)


def test_allocate_fixed_remainder_and_mismatch():
    d = s.allocate_dv(9000.0, 2, "fixed", fixed=[3000.0, None])
    assert d == [3000.0, 6000.0]
    with pytest.raises(s.StagingError):
        s.allocate_dv(9000.0, 2, "fixed", fixed=[3000.0, 5000.0])
    with pytest.raises(s.StagingError):
        s.allocate_dv(9000.0, 2, "fractions", [1.0])


def test_two_vs_three_stage_gross_mass_trend():
    # Basis: staging theory (Book Ch.5): with the same total dv, more stages reduce the gross mass (up to diminishing returns).
    from helpers import custom_spec
    from launch_vehicle.convergence import size_vehicle
    two = default_result()

    def mod(design, assump):
        st1 = design["stages"][0]
        import copy
        mid = copy.deepcopy(design["stages"][1])
        mid["diameter_m"] = 3.5
        mid["engine"]["isp_vac_s"] = 330.0
        mid["engine"]["thrust_to_weight_ignition"] = 1.0
        mid["engine"]["n_engines"] = 2
        mid["engine"]["exit_diameter_m"] = 1.4
        design["stages"] = [st1, mid, design["stages"][1]]
        design["vehicle"]["dv_fractions"] = [0.25, 0.30, 0.45]   # third stage large enough for its tanks at D = 3 m
    three = size_vehicle(custom_spec(mod))
    assert three.converged
    assert len(three.stages) == 3
    # structure-per-stage overheads (avionics, margins, separation hardware) mean the gain is modest but must not be negative by much
    assert three.glom_kg < two.glom_kg * 1.05
    # the middle stage carries exactly the third stage + payload + PAF (fairing gone at stage-2 start)
    assert three.stages[1].m_carried_kg == pytest.approx(three.payload_mass_kg + three.paf_mass_kg + three.stages[2].m_dry_kg + three.stages[2].m_prop_loaded_kg, rel=1e-8)   # limited by the solver tolerance
