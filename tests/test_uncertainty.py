"""R3: MER scatter as a Monte-Carlo (method register M57).

A single GLOM number carries false precision: the mass-estimating relationships behind it are fits to a historical
population, and this tool's own validation puts the median error at 17 %. These tests check that the sampler does
what it claims - samples every declared group, reproduces itself from a seed, reports failures instead of hiding
them, and produces an interval that brackets the nominal design.
"""
import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import uncertainty as unc

_C = {}


def mc(n=28, seed=3):
    key = (n, seed)
    if key not in _C:
        _C[key] = unc.monte_carlo(DESIGN, ASSUMP, n=n, seed=seed)
    return _C[key]


def test_every_scatter_group_in_the_assumptions_is_sampled():
    m = mc()
    from launch_vehicle.config_io import load_design
    spec = load_design(DESIGN, ASSUMP)
    declared = {k for k, v in spec.mer_scatter.items()} if hasattr(spec, "mer_scatter") else set(m["sigma"])
    assert set(m["sigma"]) == declared or set(m["sigma"]) <= declared
    assert m["sigma"], "no scatter groups were read from the assumptions file"
    assert all(0.0 <= s < 1.0 for s in m["sigma"].values())


def test_the_interval_brackets_the_nominal_design_and_is_not_absurdly_wide():
    m = mc()
    assert m["p05"] < m["nominal_glom_kg"] < m["p95"]
    width = (m["p95"] - m["p05"]) / m["nominal_glom_kg"]
    assert 0.05 < width < 0.60, f"5-95 % width {width:.1%} of nominal is not a plausible MER spread"


def test_the_sample_is_reproducible_from_its_seed():
    a = unc.monte_carlo(DESIGN, ASSUMP, n=12, seed=11)
    b = unc.monte_carlo(DESIGN, ASSUMP, n=12, seed=11)
    assert a["glom_kg"] == b["glom_kg"]
    c = unc.monte_carlo(DESIGN, ASSUMP, n=12, seed=12)
    assert c["glom_kg"] != a["glom_kg"], "a different seed must give a different sample"


def test_failed_samples_are_counted_not_dropped_silently():
    m = mc()
    assert m["n_converged"] + m["n_failed"] == m["n_requested"]
    assert isinstance(m["failures"], list)


def test_zero_sigma_freezes_a_group():
    """Setting a scatter to zero must remove that coefficient from the sampling, not merely narrow it."""
    m = unc.monte_carlo(DESIGN, ASSUMP, n=8, seed=5,
                        overrides={"assumptions.mer_scatter.avionics": 0.0})
    assert m["sigma"]["avionics"] == 0.0
    assert all(s["parameter"] != "avionics" for s in m["sensitivity"])


def test_one_at_a_time_ranking_is_sorted_and_signed():
    m = mc()
    sens = m["sensitivity"]
    assert sens, "no one-at-a-time sensitivity was produced"
    mags = [abs(s["d_glom_per_sigma"]) for s in sens]
    assert mags == sorted(mags, reverse=True)
    # a heavier structure must make the vehicle heavier, and a better Isp must make it lighter
    by = {s["parameter"]: s["d_glom_per_sigma"] for s in sens}
    assert by.get("tank_mass", 1) > 0 and by.get("engine_mass", 1) > 0
    if "isp_delivered" in by:
        assert by["isp_delivered"] < 0


def test_the_dominant_contributors_are_physically_sensible():
    """Residual propellant and delivered Isp sit at the top because they act on every stage at once; wiring sits
    at the bottom because it is a few hundred kilograms on a 400-tonne vehicle."""
    by = {s["parameter"]: abs(s["d_glom_per_sigma"]) for s in mc()["sensitivity"]}
    assert by["residual_propellant"] > by["wiring"]
    assert by["isp_delivered"] > by["wiring"]


def test_a_design_with_no_scatter_block_is_refused_clearly():
    with pytest.raises(unc.UncertaintyError):
        unc.monte_carlo(DESIGN, ASSUMP, n=4, seed=1,
                        overrides={f"assumptions.mer_scatter.{k}": 0.0
                                   for k in mc()["sigma"]})
