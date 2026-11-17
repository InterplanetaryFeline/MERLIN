"""R1 performance curves (method register M54).

The headline check is self-consistency with the sizing loop: freeze the converged vehicle, ask what payload it
can take to its own design orbit, and the answer must be the payload it was sized for. Everything else - monotone
curves, unreachable orbits reported rather than extrapolated - follows from that.
"""
import math
import os
import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import performance as pf
from launch_vehicle.config_io import load_design
from launch_vehicle.convergence import size_vehicle

_C = {}


def ref():
    if "res" not in _C:
        _C["res"] = default_result()
        _C["fv"] = pf.freeze(_C["res"])
    return _C["res"], _C["fv"]


# ------------------------------------------------------------------ the frozen vehicle reproduces the model
def test_frozen_vehicle_reproduces_the_sized_delta_v_exactly():
    res, fv = ref()
    assert fv.delta_v(res.payload_mass_kg) == pytest.approx(res.dv_achieved_mps, rel=1e-9)
    for got, s in zip(fv.stage_delta_v(res.payload_mass_kg), res.stages):
        assert got == pytest.approx(s.dv_mps, rel=1e-9)


def test_frozen_vehicle_reproduces_the_sized_gross_mass():
    res, fv = ref()
    assert fv.glom(res.payload_mass_kg) == pytest.approx(res.glom_kg, rel=1e-9)


def test_payload_adapter_follows_the_payload_but_the_rest_of_the_hardware_does_not():
    res, fv = ref()
    assert fv.paf_kg(2 * res.payload_mass_kg) > fv.paf_kg(res.payload_mass_kg)
    # the structure is deliberately NOT re-sized: that is the whole point of a performance curve
    assert fv.m_dry_kg == [s.m_dry_kg for s in res.stages]
    assert fv.m_loaded_kg == [s.m_prop_loaded_kg for s in res.stages]


# ------------------------------------------------------------------ the capability root-find
def test_capability_at_the_design_orbit_returns_the_design_payload():
    """The one check that ties this module to the sizing loop. The two agree to a fraction of a per cent; they are
    not identical because the adapter follows the payload and the lift-off acceleration that feeds the loss
    regression moves with gross mass."""
    res, fv = ref()
    cap = pf.payload_capability_kg(res.spec, fv, {})
    assert cap == pytest.approx(res.payload_mass_kg, rel=2e-3)


def test_capability_falls_with_altitude_and_with_inclination():
    res, fv = ref()
    base = {"orbit_type": "LEO", "apogee_altitude_m": None, "eccentricity": None, "inclination_deg": 28.5}
    caps = [pf.payload_capability_kg(res.spec, fv, dict(base, perigee_altitude_m=h * 1e3))
            for h in (200.0, 400.0, 600.0, 800.0)]
    assert all(a > b for a, b in zip(caps, caps[1:])), caps
    incs = [pf.payload_capability_kg(res.spec, fv, dict(base, perigee_altitude_m=400e3, inclination_deg=i))
            for i in (28.5, 45.0, 70.0, 95.0)]
    assert all(a > b for a, b in zip(incs, incs[1:])), incs


def test_delta_v_achieved_falls_monotonically_with_payload():
    """The property the bisection relies on; if it ever fails the root-find is not safe."""
    res, fv = ref()
    dvs = [fv.delta_v(m) for m in (1000.0, 5000.0, 10000.0, 20000.0, 40000.0)]
    assert all(a > b for a, b in zip(dvs, dvs[1:])), dvs


def test_an_orbit_out_of_reach_raises_rather_than_returning_a_negative_payload():
    """Direct insertion into GEO from a 28.5 deg site needs roughly 14 km/s; this vehicle has 9.4."""
    res, fv = ref()
    with pytest.raises(pf.NoCapability):
        pf.payload_capability_kg(res.spec, fv, {"orbit_type": "GEO_DIRECT", "perigee_altitude_m": 185e3,
                                                "apogee_altitude_m": 35786e3, "eccentricity": None,
                                                "inclination_deg": 28.5})


def test_a_geometrically_impossible_orbit_is_an_orbit_error_not_a_capability_answer():
    """An inclination below the launch-site latitude is not 'too heavy', it is not flyable by direct ascent; the
    sweeps turn that into a note on the point rather than a number."""
    from launch_vehicle.orbit import OrbitError
    res, fv = ref()
    with pytest.raises((OrbitError, ValueError)):
        pf.payload_capability_kg(res.spec, fv, {"orbit_type": "LEO", "perigee_altitude_m": 400e3,
                                                "apogee_altitude_m": None, "eccentricity": None,
                                                "inclination_deg": 0.0})


# ------------------------------------------------------------------ the sweeps
def test_altitude_sweep_shape_and_design_point():
    res, fv = ref()
    va = pf.payload_vs_altitude(res.spec, fv)
    assert va["curves"] and all(c["points"] for c in va["curves"])
    assert va["design"]["payload_kg"] == res.payload_mass_kg
    for c in va["curves"]:
        got = [p["payload_kg"] for p in c["points"] if p["payload_kg"] is not None]
        assert all(a > b for a, b in zip(got, got[1:])), (c["inclination_deg"], got)
    assert all(p["altitude_km"] <= pf.MAX_SWEEP_ALTITUDE_KM for c in va["curves"] for p in c["points"])


def test_inclination_below_the_launch_site_latitude_is_reported_not_flown():
    res, fv = ref()
    lat = res.spec.mission["site_latitude_deg"]
    vi = pf.payload_vs_inclination(res.spec, fv, inclinations_deg=[lat - 10.0, lat + 10.0])
    low, high = vi["points"]
    assert low["payload_kg"] is None and "latitude" in low["note"]
    assert high["payload_kg"] is not None


def test_standard_curves_carries_its_own_self_check():
    res, _ = ref()
    cur = pf.standard_curves(res)
    assert set(cur) >= {"vs_altitude", "vs_inclination", "design_point_kg", "design_point_error_kg"}
    assert abs(cur["design_point_error_kg"]) < 0.005 * res.payload_mass_kg


def test_a_lighter_vehicle_lifts_less():
    """Sanity against a second design: the three-stage example and the default must order correctly on the same
    mission, because capability is hardware, not bookkeeping."""
    big = default_result()
    small = size_vehicle(load_design(os.path.join(ROOT, "examples", "example_solid_smallsat.yaml"), ASSUMP))
    cap_big = pf.payload_capability_kg(big.spec, pf.freeze(big), {})
    cap_small = pf.payload_capability_kg(small.spec, pf.freeze(small), {})
    assert cap_big > 20 * cap_small
    assert cap_small == pytest.approx(small.payload_mass_kg, rel=5e-3)


def test_boosted_vehicle_freezes_the_parallel_phase_contribution():
    res = size_vehicle(load_design(os.path.join(ROOT, "examples", "example_boosters.yaml"), ASSUMP))
    fv = pf.freeze(res)
    assert fv.booster_mass_kg > 0 and fv.booster_attach_stage == 1
    assert fv.delta_v(res.payload_mass_kg) == pytest.approx(res.dv_achieved_mps, rel=1e-9)
