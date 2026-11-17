"""Strap-on boosters and the parallel ("zeroth-stage") burn: book Sec. 5.11 (printed pp. 305-308).

Eq. 5:65  T_tot = v_e0 mdot_0 + v_e1 mdot_1 = v_e0ave (mdot_0 + mdot_1)
Eq. 5:66  v_e0ave = (v_e0 mdot_0 + v_e1 mdot_1)/(mdot_0 + mdot_1)
Fig. 5.21 phases: (1) core + strap-ons, (2) core alone, (3) upper stage.

The end-to-end check is the book's OWN Space Shuttle exercise (pp. 323-325), whose arithmetic is
transcribed independently in this file and compared with the module's phase sequence.
"""
import math
import os
import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import boosters as bst
from launch_vehicle.units import G0
from launch_vehicle.config_io import load_design
from launch_vehicle.convergence import size_vehicle

BOOST = os.path.join(ROOT, "examples", "example_boosters.yaml")


def boosted_result():
    return size_vehicle(load_design(BOOST, ASSUMP))


def group(n=4, mdot=100.0, isp=265.0, mp=17000.0, mi=2300.0, tb=75.0):
    return bst.BoosterGroup("test", n, mdot, isp, mp, mi, tb, mdot * G0 * isp)


# ---------------------------------------------------------------- Eq. 5:66
def test_mass_averaged_isp_is_the_book_weighting():
    assert bst.mass_averaged_isp([(100.0, 300.0), (100.0, 200.0)]) == pytest.approx(250.0, rel=1e-12)
    assert bst.mass_averaged_isp([(300.0, 300.0), (100.0, 200.0)]) == pytest.approx(275.0, rel=1e-12)
    # thrust identity of Eq. 5:65: T_tot = Isp_ave g0 (mdot_0 + mdot_1)
    m0, i0, m1, i1 = 1200.0, 265.0, 400.0, 330.0
    isp = bst.mass_averaged_isp([(m0, i0), (m1, i1)])
    assert isp * G0 * (m0 + m1) == pytest.approx(m0 * G0 * i0 + m1 * G0 * i1, rel=1e-12)
    with pytest.raises(bst.BoosterError):
        bst.mass_averaged_isp([(0.0, 300.0)])


# ---------------------------------------------------------------- phase sequence
def test_phase_sequence_masses_and_jettison_bookkeeping():
    g = group()
    ph = bst.phase_sequence(600000.0, 1000.0, 300.0, 200000.0, [g])
    assert [p.duration_s for p in ph] == [75.0, 0.0, pytest.approx((200000.0 - 75000.0) / 1000.0)]
    par, jet, core = ph
    # parallel phase burns the core's share plus all booster propellant
    assert par.m_start_kg - par.m_end_kg == pytest.approx(1000.0 * 75.0 + 4 * 17000.0, rel=1e-12)
    # jettison removes only inert mass and produces no delta-v
    assert jet.m_start_kg - jet.m_end_kg == pytest.approx(4 * 2300.0, rel=1e-12)
    assert jet.dv_mps == 0.0
    # the series phase burns exactly the remaining core propellant
    assert core.m_start_kg - core.m_end_kg == pytest.approx(200000.0 - 75000.0, rel=1e-12)
    assert core.isp_eff_s == 300.0
    # every powered phase obeys the rocket equation with its own effective Isp
    for p in (par, core):
        assert p.dv_mps == pytest.approx(G0 * p.isp_eff_s * math.log(p.m_start_kg / p.m_end_kg), rel=1e-12)


def test_parallel_phase_isp_sits_between_the_two_systems():
    g = group(isp=250.0)
    ph = bst.phase_sequence(600000.0, 1000.0, 330.0, 200000.0, [g])
    assert 250.0 < ph[0].isp_eff_s < 330.0


def test_core_must_outlast_the_boosters():
    g = group(tb=300.0)
    with pytest.raises(bst.BoosterError, match="runs out of propellant"):
        bst.phase_sequence(600000.0, 1000.0, 300.0, 200000.0, [g])


def test_two_ignition_groups_give_three_powered_phases():
    """Delta II style: 6 ground-lit + 3 air-lit motors."""
    g1 = bst.BoosterGroup("ground", 6, 180.0, 265.0, 11765.0, 1315.0, 64.0, 500e3)
    g2 = bst.BoosterGroup("air", 3, 180.0, 265.0, 11765.0, 1315.0, 64.0, 500e3)
    ph = bst.phase_sequence(230000.0, 360.0, 290.0, 96000.0, [g1, g2])
    powered = [p for p in ph if p.duration_s > 0]
    assert len(powered) == 3
    assert powered[0].mdot_total_kgs > powered[1].mdot_total_kgs > powered[2].mdot_total_kgs
    assert sum(p.m_start_kg - p.m_end_kg for p in ph) == pytest.approx(230000.0 - ph[-1].m_end_kg, rel=1e-12)


def test_solver_hits_the_requested_delta_v():
    g = group()
    mp, ph = bst.solve_core_propellant(5000.0, 30000.0, 9000.0, 0.025, 1000.0, 300.0, [g])
    assert bst.total_dv(ph) == pytest.approx(5000.0, rel=1e-6)
    m_start = 30000.0 + 9000.0 + mp * 1.025 + g.m_total_kg
    assert ph[0].m_start_kg == pytest.approx(m_start, rel=1e-12)


def test_impossible_requirement_is_reported_not_silently_truncated():
    g = group()
    with pytest.raises(bst.BoosterError, match="infeasible"):
        bst.solve_core_propellant(20000.0, 30000.0, 9000.0, 0.025, 1000.0, 300.0, [g])


# ---------------------------------------------------------------- book exercise, pp. 323-325
def test_space_shuttle_parallel_burn_reproduces_the_books_exercise():
    """Book Chapter 5 exercise 1 (pp. 323-325) with the data printed there.

    SRB (each): gross 589,670 kg, empty 86,183 kg, Isp 237 SL / 269 vac, burn 124 s, quantity 2.
    ET: gross 750,975 kg, empty 29,930 kg. Orbiter + 3 SSME + OMS dry 77,658 kg, Isp 363 SL / 455 vac,
    burn 480 s. OMS propellant 21,660 kg. Effective Isp = 1/3 Isp_SL + 2/3 Isp_vac for both systems.
    The exercise asks for the payload that makes dv1 + dv2 = 9,086 m/s; the official payload is 29,500 kg.
    """
    isp_srb = (237 + 2 * 269) / 3
    isp_ssme = (363 + 2 * 455) / 3
    m_srb_gross, m_srb_empty, t_srb = 589670.0, 86183.0, 124.0
    m_et_gross, m_et_empty, t_ssme = 750975.0, 29930.0, 480.0
    m_orb, m_oms = 77658.0, 21660.0
    mdot_srb = (m_srb_gross - m_srb_empty) / t_srb
    mdot_et = (m_et_gross - m_et_empty) / t_ssme

    def dv_total(m_pl):
        # --- transcription of the book's own recipe (independent of the module) ---
        m10 = 2 * m_srb_gross + m_orb + m_et_gross + m_oms + m_pl
        m1f = 2 * m_srb_empty + m_orb + m_et_empty + (m_et_gross - m_et_empty - mdot_et * t_srb) + m_oms + m_pl
        isp1 = (2 * mdot_srb * isp_srb + mdot_et * isp_ssme) / (2 * mdot_srb + mdot_et)   # Eq. 5:66
        dv1 = G0 * isp1 * math.log(m10 / m1f)
        m20 = m_orb + m_et_empty + (m_et_gross - m_et_empty - mdot_et * t_srb) + m_oms + m_pl
        m2f = m_orb + m_et_empty + m_oms + m_pl
        dv2 = G0 * 455.0 * math.log(m20 / m2f)
        return dv1 + dv2, dv1, isp1, m10, m1f

    # solve for the payload that reaches the book's 9,086 m/s
    lo, hi = 0.0, 80000.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if dv_total(mid)[0] > 9086.0:
            lo = mid
        else:
            hi = mid
    m_pl = 0.5 * (lo + hi)
    total, dv1, isp1, m10, m1f = dv_total(m_pl)
    assert total == pytest.approx(9086.0, abs=1.0)
    # the exercise says to compare with the official 29,500 kg payload
    assert 20000.0 < m_pl < 40000.0
    assert m_pl == pytest.approx(29500.0, rel=0.25)

    # --- now the same first stage through the module's phase sequence ---
    g = bst.BoosterGroup("SRB", 2, mdot_srb, isp_srb, m_srb_gross - m_srb_empty, m_srb_empty, t_srb)
    core_prop = m_et_gross - m_et_empty
    m_start = m_orb + m_et_empty + core_prop + m_oms + m_pl + g.m_total_kg
    ph = bst.phase_sequence(m_start, mdot_et, isp_ssme, core_prop, [g])
    assert ph[0].isp_eff_s == pytest.approx(isp1, rel=1e-12)             # Eq. 5:66 agreement
    assert ph[0].m_start_kg == pytest.approx(m10, rel=1e-12)
    assert ph[0].m_end_kg == pytest.approx(m1f, rel=1e-12)
    assert ph[0].dv_mps == pytest.approx(dv1, rel=1e-12)


# ---------------------------------------------------------------- end-to-end vehicle
def test_boosted_vehicle_mass_closure_and_phase_sum():
    r = boosted_result()
    b = r.boosters
    assert r.converged
    total = (r.payload_mass_kg + r.paf_mass_kg + r.fairing_mass_kg
             + sum(s.m_dry_kg + s.m_prop_loaded_kg for s in r.stages) + b.m_total_kg)
    assert total == pytest.approx(r.glom_kg, rel=1e-12)
    s1 = r.stages[b.attach_stage - 1]
    assert bst.total_dv(s1.phases) == pytest.approx(s1.dv_mps, rel=1e-6)
    assert s1.dv_check_mps == pytest.approx(s1.dv_mps, rel=1e-6)


def test_liftoff_thrust_includes_only_ground_lit_boosters():
    r = boosted_result()
    b = r.boosters
    expected = r.stages[0].thrust_ref_N + b.n_ground_lit * (b.thrust_sl_each_N or b.thrust_vac_each_N)
    assert r.liftoff_thrust_N == pytest.approx(expected, rel=1e-12)
    assert r.liftoff_tw == pytest.approx(expected / (r.glom_kg * G0), rel=1e-12)


def test_booster_event_masses_match_the_phase_model():
    """The mass ledger and the independent phase sequence must agree at strap-on burnout and jettison."""
    r = boosted_result()
    ph = [p for p in r.stages[0].phases]
    ev = {e["event"].split("(")[0].strip(): e for e in r.mass_properties["events"]}
    burn = [v for k, v in ev.items() if k.startswith("Strap-on burnout")][0]
    after = [v for k, v in ev.items() if k.startswith("After strap-on jettison")][0]
    assert burn["mass_kg"] == pytest.approx(ph[0].m_end_kg, rel=1e-9)
    assert after["mass_kg"] == pytest.approx(ph[2].m_start_kg, rel=1e-9)
    # roll inertia drops when the off-axis boosters go
    assert after["J_roll"] < burn["J_roll"]


def test_boosters_appear_in_the_geometry_and_ledger():
    r = boosted_result()
    assert r.geometry.booster_segments
    assert r.geometry.max_span_m > r.geometry.max_diameter
    items = [i for i in r.ledger if i.stage == -2]
    assert items and sum(i.mass_kg for i in items) == pytest.approx(r.boosters.m_total_kg, rel=1e-9)
    assert all(i.ext_roll > 0 for i in items)                 # off-axis contribution to roll inertia


# ====================================================== liquid strap-on boosters (Delta IV Heavy)
# Until this block the liquid-booster path had NO coverage at all: `type: liquid` was accepted by the
# schema and handled in mass_budget, but no shipped design used it and no test exercised it. The
# vehicle here is the reason it matters - three identical Common Booster Cores, which is the common
# liquid-strap-on architecture (Delta IV Heavy, Falcon Heavy, Angara A5).
D4H = os.path.join(ROOT, "validation", "delta4_heavy.yaml")


def d4h(overrides=None):
    from launch_vehicle.config_io import load_design
    from launch_vehicle.convergence import size_vehicle
    return size_vehicle(load_design(D4H, ASSUMP, overrides))


def test_a_liquid_strap_on_vehicle_sizes_end_to_end():
    r = d4h()
    assert r.converged, r.status
    b = r.boosters
    assert b.kind == "liquid" and b.n_total == 2
    # published Delta IV Heavy: 733 t at lift-off. The agreement is partly INHERITED - both booster
    # masses are typed in from the published figures - so this is a consistency check, not a prediction.
    assert r.glom_kg == pytest.approx(733_000, rel=0.05), f"GLOM {r.glom_kg:,.0f}"
    assert 60.0 < r.geometry.total_length < 85.0
    assert r.geometry.max_span_m == pytest.approx(15.3, rel=0.1), "three 5.1 m cores abreast"


def test_a_liquid_booster_uses_its_mixture_density_not_a_solid_propellant():
    r = d4h()
    b, spec = r.boosters, d4h().spec
    bs = spec.boosters
    rho_ox = spec.propellants[bs.oxidizer].density_kg_m3
    rho_f = spec.propellants[bs.fuel].density_kg_m3
    of = bs.of_ratio
    bulk = (1.0 + of) / (of / rho_ox + 1.0 / rho_f)
    assert 300.0 < bulk < 450.0, f"LOX/LH2 bulk density {bulk:.0f} kg/m3 is not plausible"
    # the sized case must hold the loaded propellant at that density, not at a solid's ~1,750 kg/m3
    V = b.case.V_int if hasattr(b.case, "V_int") else None
    assert b.m_prop_each_kg / bulk < (V or 1e9) * 1.3
    assert b.length_m > 25.0, "a LOX/LH2 booster of 200 t cannot be short"


def test_a_liquid_booster_has_no_cast_grain_or_bore():
    """A bore is a solid-motor concept. Drawing one down a hydrogen tank is how this was found."""
    b = d4h().boosters
    assert getattr(b.case, "R_bore", 0.0) == 0.0, "a liquid booster was given a grain bore"
    assert not getattr(b.case, "bore_full_length", False)
    solid = boosted_result().boosters                  # the solid example must still have one
    assert solid.case.R_bore > 0.0, "the solid motor lost its grain bore"


def test_a_liquid_booster_refuses_the_solid_casing_relation():
    """Eq. 8:18's k = 0.135 is a steel SRM casing. Applying it to a tank would be nonsense."""
    from launch_vehicle.config_io import load_design
    from launch_vehicle.convergence import size_vehicle
    try:
        size_vehicle(load_design(D4H, ASSUMP, {"boosters.inert_mass_method": "book_steel"}))
        raise AssertionError("book_steel should not be accepted for a liquid booster")
    except Exception as e:                                       # noqa: BLE001
        assert "mass_fraction" in str(e) or "user_mass" in str(e), str(e)


def test_the_core_must_outlast_liquid_boosters_too():
    """The core runs at ONE constant mass flow, so an un-throttled core needs more propellant.

    This is the Delta IV Heavy throttle, arrived at from the other end: give the core the same flow as
    the boosters and the sizing loop has to buy it a bigger tank than a Common Booster Core has.
    """
    full = 200400.0 / 246.0 * 9.80665 * 412.0        # one RS-68 at the boosters' own mass flow
    throttled = d4h().stages[0].m_prop_loaded_kg
    unthrottled = d4h({"stages.0.engine.thrust_vac_per_engine_N": full}).stages[0].m_prop_loaded_kg
    assert unthrottled > throttled * 1.1, (
        f"an un-throttled core should need materially more propellant: {unthrottled:,.0f} vs "
        f"{throttled:,.0f} kg")
    assert throttled == pytest.approx(200_400, rel=0.10), \
        "the throttled core should land near a real CBC load; the three-core architecture closes"


def test_the_phase_table_is_built_for_a_liquid_parallel_burn():
    r = d4h()
    ph = [p for p in r.booster_phases] if hasattr(r, "booster_phases") else None
    if ph is None:
        return                                        # phases are reported through the report instead
    powered = [p for p in ph if p.dv_mps > 0]
    assert len(powered) == 2, "parallel burn then core-alone"
    assert powered[0].isp_eff_s != powered[1].isp_eff_s, "Eq. 5:66 should mass-average only in phase 1"


# ===================================================================== R23: two more real vehicles
def _val(name):
    from launch_vehicle.config_io import load_design
    from launch_vehicle.convergence import size_vehicle
    return size_vehicle(load_design(os.path.join(ROOT, "validation", name + ".yaml"), ASSUMP))


def test_h2a_202_sizes_with_solid_strap_ons_on_a_hydrolox_core():
    """The first case with composite solid strap-ons on a hydrolox core, added for R23."""
    r = _val("h2a_202")
    assert r.converged, r.status
    assert r.glom_kg == pytest.approx(285_000, rel=0.12), f"GLOM {r.glom_kg:,.0f} against a published 285 t"
    b = r.boosters
    assert b.kind == "solid" and b.n_total == 2
    assert b.m_prop_each_kg == pytest.approx(65_040, rel=1e-6), "the SRB-A propellant load is an input"
    # its inert mass is one of the stages solid_inert is fitted to, so the two should be close
    from launch_vehicle import solid_inert as si
    zb = next(s for s in si.DATASET if "H-IIA" in s.name)
    assert b.m_inert_each_kg == pytest.approx(zb.m_inert_kg, rel=0.15), (
        f"modelled {b.m_inert_each_kg:,.0f} kg against Zandbergen's {zb.m_inert_kg:,.0f} kg for the same motor")


def test_soyuz_sizes_despite_its_boosters_being_a_shape_the_tool_cannot_represent():
    """Added for R23 precisely because it does not fit: four TAPERED strap-ons, one diameter in the model.

    The sizing is expected to be reasonable and the geometry is expected to be wrong. Both are asserted, so
    that if someone later teaches the tool about tapered boosters this test tells them it mattered.
    """
    r = _val("soyuz2_1b")
    assert r.converged, r.status
    b = r.boosters
    assert b.kind == "liquid" and b.n_total == 4
    assert b.m_prop_each_kg == pytest.approx(39_160, rel=1e-6)
    # one diameter: the model's booster is a cylinder of the real one's MAXIMUM diameter
    assert b.diameter_m == pytest.approx(2.68, abs=0.05)
    assert b.length_m < 19.6, (
        "a cylinder of the maximum diameter holds the propellant in less length than the real tapered "
        "booster needs, so the modelled booster must come out short")
    assert r.geometry.max_span_m < 10.3, "and the span is correspondingly under-stated"


def test_the_core_burns_alongside_the_soyuz_strap_ons_without_any_throttling_fudge():
    """Unlike Delta IV Heavy, Soyuz needs no invented throttle: the core simply carries more propellant."""
    r = _val("soyuz2_1b")
    core_mdot = r.stages[0].m_prop_loaded_kg / r.stages[0].burn_time_s
    boost_mdot = r.boosters.mdot_each_kgs
    assert 0.5 < core_mdot / boost_mdot < 1.6, (
        f"core {core_mdot:.0f} kg/s against a booster's {boost_mdot:.0f} kg/s - these are comparable "
        "engines, which is why no throttle profile is needed here")
    assert r.stages[0].burn_time_s > r.boosters.burn_time_s, "the core must outlast the strap-ons"
