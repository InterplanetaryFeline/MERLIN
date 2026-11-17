"""Invalid-input handling and engineering warnings."""
import pytest
from helpers import default_spec, default_result, custom_spec, DESIGN, ASSUMP
from launch_vehicle.config_io import ConfigError, load_yaml_annotated, load_design
from launch_vehicle.validation import InputError, validate_spec
from launch_vehicle.convergence import size_vehicle, SizingError
from launch_vehicle.orbit import OrbitError


def test_negative_payload_rejected():
    with pytest.raises(InputError, match="payload"):
        size_vehicle(default_spec({"mission.payload_mass_kg": -5.0}))


def test_unknown_propellant_rejected():
    with pytest.raises(InputError, match="propellant"):
        size_vehicle(default_spec({"stages.0.fuel": "unobtanium"}))


def test_thrust_must_be_specified_exactly_once():
    with pytest.raises(InputError, match="exactly one"):
        size_vehicle(default_spec({"stages.0.engine.thrust_vac_per_engine_N": 7.0e5}))
    with pytest.raises(InputError, match="exactly one"):
        size_vehicle(default_spec({"stages.1.engine.thrust_to_weight_ignition": None}))


def test_sea_level_isp_above_vacuum_rejected():
    with pytest.raises(InputError, match="sea-level"):
        size_vehicle(default_spec({"stages.0.engine.isp_sl_s": 320.0}))


def test_undocumented_bare_value_rejected(tmp_path=None):
    import os, tempfile
    d = tempfile.mkdtemp()
    p = os.path.join(d, "bad.yaml")
    open(p, "w").write("mission:\n  payload_mass_kg: 1000\n")
    with pytest.raises(ConfigError, match="undocumented"):
        load_yaml_annotated(p)


def test_missing_documentation_keys_rejected():
    import os, tempfile
    d = tempfile.mkdtemp()
    p = os.path.join(d, "bad.yaml")
    open(p, "w").write("mission:\n  payload_mass_kg: {v: 1000, u: kg}\n")
    with pytest.raises(ConfigError, match="missing documentation"):
        load_yaml_annotated(p)


def test_missing_required_input_rejected_no_silent_default():
    def mod(design, assump):
        del design["stages"][0]["residual_fraction"]
    with pytest.raises(ConfigError, match="residual_fraction"):
        custom_spec(mod)


def test_unknown_override_path_rejected():
    with pytest.raises(ConfigError):
        default_spec({"stages.0.engine.no_such_key": 1.0})


def test_inclination_below_latitude_rejected():
    with pytest.raises(OrbitError, match="direct ascent"):
        size_vehicle(default_spec({"mission.orbit.inclination_deg": 20.0}))


def test_fairing_wider_than_upper_stage_adds_an_adapter_cone():
    """v0.3: a fairing wider than the upper stage is allowed (book Fig. 8.15) and gets a conical adapter;
    a fairing NARROWER than the stage is still rejected, and the envelope must still fit."""
    r = size_vehicle(default_spec({"fairing.diameter_m": 3.5}))
    cones = [s for s in r.geometry.segments if s.kind == "fwd_adapter"]
    assert len(cones) == 1
    assert cones[0].d_bot == pytest.approx(3.0) and cones[0].d_top == pytest.approx(3.5)
    assert "Forward adapter cone" in r.stages[-1].components
    assert any(i.code == "FAIRDIA" and i.level == "WARNING" for i in r.issues)
    with pytest.raises(InputError, match="narrower than the uppermost stage"):
        size_vehicle(default_spec({"fairing.diameter_m": 2.5}))
    with pytest.raises(InputError, match="envelope"):
        size_vehicle(default_spec({"mission.payload_envelope_diameter_m": 3.0}))


def test_density_incompatible_with_table_8_6_mer_rejected():
    # refused before sizing since v1.1 (it used to surface part-way through the loop, with no field to go to)
    with pytest.raises(InputError, match="away from the density") as e:
        size_vehicle(default_spec({"assumptions.propellants.RP-1.density_kg_m3": 600.0}))
    assert e.value.field == "stages[0].tank.mass_method_fuel" and e.value.options


def test_methane_without_table_mer_requires_other_method():
    def mod(design, assump):
        design["stages"][1]["fuel"] = "LCH4"
    with pytest.raises(InputError, match="Table 8.6") as e:
        size_vehicle(custom_spec(mod))
    assert e.value.field == "stages[1].tank.mass_method_fuel"
    assert {o["value"] for o in e.value.options} == {"akin_volume", "pressure_vessel"}


def test_engine_cluster_that_does_not_fit_is_flagged_infeasible():
    r = default_result({"stages.0.diameter_m": 3.4})
    assert any(i.code == "ENGFIT" and i.level == "ERROR" for i in r.issues)


def test_low_liftoff_tw_is_flagged():
    r = default_result({"stages.0.engine.thrust_to_weight_ignition": 1.05})
    assert any(i.code == "TWLIFT" and i.level == "ERROR" for i in r.issues)


def test_vacuum_isp_on_atmospheric_stage_gets_warning():
    r = default_result({"stages.0.engine.isp_effective_mode": "vacuum"})
    assert any(i.code == "ISPVAC" and i.level == "WARNING" and "optimistic" in i.message for i in r.issues)


def test_fidelity_disclaimer_always_present():
    r = default_result()
    assert any(i.code == "FIDELITY" and "NOT demonstrated" in i.message for i in r.issues)


def test_every_default_input_is_documented_in_register():
    spec = default_spec()
    assert len(spec.inputs_register) > 150
    for row in spec.inputs_register:
        assert row["provenance"] in ("user", "reference", "assumed")
        assert str(row["source"]).strip() and str(row["units"]).strip() and str(row["description"]).strip()


def test_validation_errors_name_the_field_they_are_about():
    """Validation used to raise a bare sentence, so this whole class of error - the fairing too narrow, the
    envelope that does not fit, a jettison stage out of range - pointed nowhere, while the geometry and
    sizing errors had named their field for several versions. The GUI turns `field` into a jump and each
    `option` into a button, so an error without one leaves the user to find the input themselves."""
    import os
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(root, "src"))
    from launch_vehicle.config_io import load_design
    from launch_vehicle.convergence import size_vehicle
    from launch_vehicle.validation import InputError
    assump = os.path.join(root, "config", "engineering_assumptions.yaml")
    design = os.path.join(root, "config", "default_design.yaml")

    cases = [({"fairing.diameter_m": 2.0}, "fairing.diameter_m"),
             ({"mission.payload_envelope_diameter_m": 5.0}, "fairing.diameter_m"),
             ({"fairing.jettison_at_stage_start": 9}, "fairing.jettison_at_stage_start"),
             ({"mission.payload_mass_kg": -5.0}, "mission.payload_mass_kg")]
    for overrides, want_field in cases:
        try:
            size_vehicle(load_design(design, assump, overrides))
        except InputError as ex:
            assert getattr(ex, "field", None) == want_field, (
                f"{overrides} -> field {getattr(ex, 'field', None)!r}, expected {want_field!r}")
        else:
            raise AssertionError(f"{overrides} was accepted")


def test_the_fixes_those_errors_offer_actually_resolve_them():
    """An offered fix that does not work is worse than none, because it looks like progress."""
    import os
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(root, "src"))
    from launch_vehicle.config_io import load_design
    from launch_vehicle.convergence import size_vehicle, SizingError
    from launch_vehicle.validation import InputError
    from launch_vehicle.tank_sizing import InfeasibleGeometry
    assump = os.path.join(root, "config", "engineering_assumptions.yaml")
    design = os.path.join(root, "config", "default_design.yaml")

    for start in ({"fairing.diameter_m": 2.0},
                  {"mission.payload_envelope_diameter_m": 5.0},
                  {"fairing.jettison_at_stage_start": 9}):
        overrides, clicks = dict(start), []
        for _ in range(6):
            try:
                assert size_vehicle(load_design(design, assump, overrides)).glom_kg > 0
                break
            except (InputError, SizingError, InfeasibleGeometry) as ex:
                usable = [o for o in (getattr(ex, "options", None) or [])
                          if o.get("path") and o.get("value") is not None]
                assert usable, f"{start}: refused with no applicable fix after {clicks}: {str(ex)[:120]}"
                overrides[usable[0]["path"]] = usable[0]["value"]
                clicks.append(usable[0]["path"])
        else:
            raise AssertionError(f"{start}: the offered fixes never settled, clicked {clicks}")
        assert len(clicks) <= 2, f"{start} took {len(clicks)} clicks: {clicks}"
