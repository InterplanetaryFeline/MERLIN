"""Mass properties: centre of mass at events and ledger consistency."""
import pytest
from helpers import default_result
from launch_vehicle import mass_properties as mp


def test_two_body_hand_calculation():
    # Basis: (10 kg at z=0, 30 kg at z=4) -> z_cm = (0 + 120)/40 = 3.0 m
    items = [mp.MassItem("a", 1, "g", 10.0, 0.0, "", "dry"), mp.MassItem("b", 1, "g", 30.0, 4.0, "", "dry")]
    m, z = mp.cm_of(items)
    assert m == 40.0 and z == pytest.approx(3.0, rel=1e-14)


def test_liftoff_cm_matches_independent_recomputation():
    r = default_result()
    N = len(r.stages)
    items = [i for i in r.ledger if (i.kind in ("payload", "paf")) or (i.kind == "dry") or (i.kind == "prop_loaded") or (i.kind == "fairing")]
    m = sum(i.mass_kg for i in items)
    z = sum(i.mass_kg * i.z_m for i in items) / m
    ev = r.mass_properties["events"][0]
    assert ev["mass_kg"] == pytest.approx(r.glom_kg, rel=1e-9)         # liftoff mass = GLOM
    assert m == pytest.approx(r.glom_kg, rel=1e-9)
    assert ev["z_cm_m"] == pytest.approx(z, rel=1e-9)
    assert 0.0 < ev["z_cm_m"] < r.geometry.total_length


def test_cm_moves_forward_as_propellant_burns():
    r = default_result()
    ev = r.mass_properties["events"]
    assert ev[1]["z_cm_m"] > ev[0]["z_cm_m"]                              # stage-1 burnout CM is higher than liftoff CM
    assert ev[0]["mass_kg"] > ev[1]["mass_kg"] > ev[2]["mass_kg"] > ev[3]["mass_kg"] > ev[4]["mass_kg"]


def test_event_masses_follow_mass_chain():
    r = default_result()
    s1, s2 = r.stages
    ev = {e["event"].split("(")[0].strip(): e for e in r.mass_properties["events"]}
    assert ev["Stage 1 burnout"]["mass_kg"] == pytest.approx(s1.m_burnout_kg + 0.0, rel=1e-9)
    assert ev["Stage 2 burnout"]["mass_kg"] == pytest.approx(s2.m_burnout_kg, rel=1e-9)
    assert r.mass_properties["events"][-1]["mass_kg"] == pytest.approx(r.payload_mass_kg + r.paf_mass_kg, rel=1e-12)


def test_propellant_centroids_inside_tanks():
    r = default_result()
    for sr in r.stages:
        segs = {s.tank.role: s for s in r.geometry.stage_segments(sr.index) if s.kind == "tank"}
        for i in r.ledger:
            if i.stage == sr.index and i.kind == "prop_loaded":
                role = "oxidizer" if "oxidizer" in i.name else "fuel"
                assert segs[role].z0 < i.z_m < segs[role].z1


def test_aggregate_mode_flags_smeared_mass():
    from helpers import book_tsto_overrides
    r = default_result(book_tsto_overrides())
    assert any("smeared" in w for w in r.mass_properties["warnings"])
