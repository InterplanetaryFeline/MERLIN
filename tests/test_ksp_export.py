"""Kerbal Space Program export (ksp_export).

KSP itself cannot run in the suite, so what is checked is what the files say, read back with parsers written
here from KSP's config syntax rather than with the exporter's own helpers. That the files load and fly in the
game was checked once by hand, through kRPC (tools/ksp_verify.py), and is written down in docs/KSP_EXPORT.md
with the measurements; it is not re-checked here.
"""
import atexit
import os
import pathlib
import re
import shutil
import tempfile
import types
import zipfile

import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import ksp_export as kx
from launch_vehicle.units import G0

TMP = pathlib.Path(tempfile.mkdtemp(prefix="lv_ksp_"))
atexit.register(shutil.rmtree, TMP, True)
_C = {}


def _ex():
    """One sized default vehicle and its export, shared by the tests (the suite's runner has no fixtures)."""
    if "ex" not in _C:
        _C["res"] = default_result()
        _C["ex"] = kx.export(_C["res"], str(TMP / "out"))
    return _C["res"], _C["ex"]


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _blocks(text, name):
    """Top-level `name { ... }` blocks of a KSP config, as raw text, by brace counting."""
    out, i = [], 0
    pat = re.compile(r"^%s\s*\n\{" % re.escape(name), re.M)
    for m in pat.finditer(text):
        depth, j = 0, m.end() - 1
        while True:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        out.append(text[m.end():j])
    return out


def _value(block, key):
    m = re.search(r"^\t%s = (.*)$" % re.escape(key), block, re.M)
    return m.group(1).strip() if m else None


# ------------------------------------------------------------------ the export carries MERLIN's numbers
def test_the_export_weighs_what_merlin_sized():
    res, ex = _ex()
    c = ex["check"]
    assert c["export_glom_kg"] == pytest.approx(res.glom_kg, rel=1e-9)


def test_every_stage_keeps_its_dry_mass_propellant_thrust_isp_and_mixture_ratio():
    _, ex = _ex()
    for w in ex["check"]["rows"]:
        assert w["export_dry_kg"] == pytest.approx(w["merlin_dry_kg"], rel=1e-9)
        assert w["export_usable_kg"] == pytest.approx(w["merlin_usable_kg"], rel=1e-9)
        assert w["export_thrust_vac_kN"] == pytest.approx(w["merlin_thrust_vac_kN"], rel=1e-9)
        assert w["export_isp_vac_s"] == pytest.approx(w["merlin_isp_vac_s"], rel=1e-9)
        assert w["export_of"] == pytest.approx(w["merlin_of"], rel=1e-9)


def test_part_masses_in_the_config_add_up_to_the_lift_off_mass():
    """Read back from parts.cfg and resources.cfg alone: part dry masses [t] plus resource units x density
    [t per unit], plus the fairing panels, are MERLIN's lift-off mass."""
    res, ex = _ex()
    dens = {_value(b, "name"): float(_value(b, "density"))
            for b in _blocks(_read(ex["files"]["resources"]), "RESOURCE_DEFINITION")}
    total_t = 0.0
    for b in _blocks(_read(ex["files"]["parts"]), "PART"):
        total_t += float(_value(b, "mass"))
        for r in re.finditer(r"\tRESOURCE\n\t\{\n\t\tname = (\S+)\n\t\tamount = (\S+)", b):
            if r.group(1) in dens:
                total_t += float(r.group(2)) * dens[r.group(1)]
    total_t += ex["check"]["fairing_kg"] / 1000.0
    assert total_t * 1000.0 == pytest.approx(res.glom_kg, rel=1e-6)


def test_propellant_densities_are_merlins_in_tonnes_per_litre():
    res, ex = _ex()
    for rn, r in ex["resources"].items():
        assert r["density_kg_m3"] == res.spec.propellants[r["propellant"]].density_kg_m3
    for b in _blocks(_read(ex["files"]["resources"]), "RESOURCE_DEFINITION"):
        rn = _value(b, "name")
        assert float(_value(b, "density")) == pytest.approx(ex["resources"][rn]["density_kg_m3"] / 1e6, rel=1e-6)


def test_the_isp_curve_is_merlins_straight_line_with_explicit_tangents():
    """T = mdot ve - Pa Ae at constant mdot is Isp(Pa) = Isp_vac - Pa Ae / (mdot g0). KSP interpolates the
    curve as a Hermite spline; with both tangents equal to the chord's slope the spline IS the line."""
    _, ex = _ex()
    engines = [p for p in ex["parts"] if p.kind == "engine"]
    assert engines
    text = _read(ex["files"]["parts"])
    for p in engines:
        e = p.engine
        assert e["isp_1atm_s"] == pytest.approx(
            e["isp_vac_s"] - kx.P0_PA * e["exit_area_m2"] / (e["mdot_kgs"] * G0), rel=1e-12)
        block = next(b for b in _blocks(text, "PART") if _value(b, "name") == f"MERLIN_{ex['tag']}_{p.key}")
        keys = [list(map(float, k.split())) for k in re.findall(r"key = ([-\d. ]+)\n", block)]
        assert len(keys) == 2, "the default vehicle's engines all stay above the Isp floor"
        (p0, i0, a0, b0), (p1, i1, a1, b1) = keys
        slope = (i1 - i0) / (p1 - p0)
        assert a0 == b0 == a1 == b1 == pytest.approx(slope, abs=1e-3)
        assert i0 == pytest.approx(e["isp_vac_s"], abs=1e-3)


def test_volume_ratios_give_back_the_mass_mixture_ratio():
    res, ex = _ex()
    for p in ex["parts"]:
        if p.kind != "engine":
            continue
        e = p.engine
        rf = res.spec.propellants[e["fuel"]].density_kg_m3
        ro = res.spec.propellants[e["oxidizer"]].density_kg_m3
        assert e["ratio_fuel"] + e["ratio_ox"] == pytest.approx(1.0, abs=1e-12)
        assert (e["ratio_ox"] * ro) / (e["ratio_fuel"] * rf) == pytest.approx(e["of_ratio"], rel=1e-12)


# ------------------------------------------------------------------ the craft file
def test_craft_part_names_survive_ksps_first_underscore_split():
    """KSP reads 'part = name_id' by cutting at the FIRST underscore and stores part names with '_' as '.'.
    Written with underscores, every part loaded as 'MERLIN' and the game reported them all missing."""
    _, ex = _ex()
    names = {_value(b, "name").replace("_", ".") for b in _blocks(_read(ex["files"]["parts"]), "PART")}
    craft = _read(ex["files"]["craft"])
    refs = re.findall(r"^\tpart = (\S+)$", craft, re.M)
    assert len(refs) == len(ex["parts"])
    stock = {p.stock for p in ex["parts"] if p.stock}
    for ref in refs:
        assert ref.split("_", 1)[0] in names | stock, ref


def test_every_link_and_attachment_points_at_a_part_in_the_craft():
    _, ex = _ex()
    craft = _read(ex["files"]["craft"])
    ids = set(re.findall(r"^\tpart = (\S+)$", craft, re.M))
    links = re.findall(r"^\tlink = (\S+)$", craft, re.M)
    assert set(links) <= ids
    assert len(links) == len(ids) - 1, "a tree has one fewer link than parts"
    atts = re.findall(r"^\tattN = \w+,([^_\s]+_\d+)_", craft, re.M)
    srfs = re.findall(r"^\tsrfN = srfAttach,(\S+)$", craft, re.M)
    n_srf = sum(1 for p in ex["parts"] if p.srf)
    assert len(srfs) == n_srf, "a surface-attached part names its parent once, on itself"
    assert len(atts) == 2 * (len(links) - n_srf), "each stack link is recorded from both ends"
    for att in atts + srfs:
        assert att in ids


def test_four_launch_clamps_hold_the_first_stage_and_let_go_at_ignition():
    """Not in MERLIN, and not counted in its mass: stock clamps on the first stage's aft skirt, released with
    stage 1 ignition. Without them Scout G-1, standing on one nozzle, toppled on the pad."""
    import math
    for res, ex in (_ex(), _solid()):
        clamps = [p for p in ex["parts"] if p.kind == "clamp"]
        assert len(clamps) == kx.N_CLAMPS
        ign1 = next(p.istg for p in ex["parts"] if p.kind == "engine" and p.stage == 1)
        aft = next(p for p in ex["parts"] if p.key == "s1_aft_skirt")
        for c in clamps:
            assert c.stock == kx.CLAMP[0] and c.srf and c.parent == aft.key and c.istg == ign1
            assert c.dry_kg == 0.0 and not c.resources
            assert math.hypot(c.x, c.y) == pytest.approx(aft.diameter / 2 + kx.CLAMP[2])
            # the clamp's +z, turned by its rotation about the vertical, points at the vehicle's axis
            phi = 2.0 * math.atan2(c.rot[1], c.rot[3])
            r = math.hypot(c.x, c.y)
            assert math.sin(phi) == pytest.approx(-c.x / r, abs=1e-9)
            assert math.cos(phi) == pytest.approx(-c.y / r, abs=1e-9)
        assert ex["check"]["export_glom_kg"] == pytest.approx(res.glom_kg, rel=1e-9)
        assert f"name = MERLIN_{ex['tag']}_clamp" not in _read(ex["files"]["parts"]), "stock parts get no cfg"


def test_exactly_one_part_commands_the_vehicle_and_it_is_the_root():
    _, ex = _ex()
    cmd = [p for p in ex["parts"] if p.command]
    assert len(cmd) == 1 and cmd[0].parent is None
    assert ex["parts"][0] is cmd[0], "KSP takes the first part of a craft as its root"
    assert "ModuleCommand" in _read(ex["files"]["parts"])


def test_staging_fires_stage_one_first_then_separates_then_lights_stage_two():
    """KSP fires the highest istg first."""
    _, ex = _ex()
    eng = {p.stage: p.istg for p in ex["parts"] if p.kind == "engine"}
    dec = [p.istg for p in ex["parts"] if p.kind == "decoupler"]
    assert len(dec) == 1
    assert eng[1] > dec[0] > eng[2]
    fb = next(p for p in ex["parts"] if p.kind == "fairing_base")
    assert fb.istg == eng[2], "MERLIN drops the fairing at stage 2 ignition for this vehicle"


def test_the_zip_holds_the_readme_parts_resources_and_craft():
    _, ex = _ex()
    with zipfile.ZipFile(ex["files"]["zip"]) as z:
        names = set(n.replace("\\", "/") for n in z.namelist())
    tag = ex["tag"]
    assert names == {"README_KSP.txt", f"GameData/MERLIN_Export/{tag}/parts.cfg",
                     f"GameData/MERLIN_Export/{tag}/resources.cfg", f"Ships/VAB/{tag}_MERLIN.craft"}


def test_generated_files_are_lf_and_utf8():
    _, ex = _ex()
    for k in ("parts", "resources", "craft", "readme"):
        with open(ex["files"][k], "rb") as fh:
            raw = fh.read()
        assert b"\r\n" not in raw
        raw.decode("utf-8")


# ------------------------------------------------------------------ what is refused, and installing
def test_boosters_are_refused_with_a_reason():
    boost = types.SimpleNamespace(spec=types.SimpleNamespace(stages=[types.SimpleNamespace(is_solid=False)]),
                                  boosters=object())
    with pytest.raises(kx.KSPExportError, match="booster"):
        kx.build_parts(boost, "X")


# ------------------------------------------------------------------ solid stages
def _solid():
    """Scout G-1: four solid stages, the top one with a forward adapter cone above its forward skirt."""
    if "solid" not in _C:
        from launch_vehicle.config_io import load_design
        from launch_vehicle.convergence import size_vehicle
        res = size_vehicle(load_design(os.path.join(ROOT, "validation", "scout_g1.yaml"), ASSUMP), keep_history=False)
        _C["solid"] = (res, kx.export(res, str(TMP / "scout")))
    return _C["solid"]


def test_a_solid_vehicle_keeps_every_stages_mass_grain_thrust_isp_and_burn_time():
    res, ex = _solid()
    c = ex["check"]
    assert c["export_glom_kg"] == pytest.approx(res.glom_kg, rel=1e-9)
    assert len(c["rows"]) == 4 and all(w["solid"] for w in c["rows"])
    for w in c["rows"]:
        for q in ("dry_kg", "usable_kg", "thrust_vac_kN", "isp_vac_s", "burn_s"):
            assert w["export_" + q] == pytest.approx(w["merlin_" + q], rel=1e-9), (w["stage"], q)
        assert w["merlin_of"] is None and w["export_of"] is None and w["propellant"]


def test_a_solid_motor_cannot_be_throttled_or_shut_down_and_burns_its_own_grain():
    _, ex = _solid()
    text = _read(ex["files"]["parts"])
    grains = {rn for rn, r in ex["resources"].items() if r.get("solid")}
    assert grains
    for p in ex["parts"]:
        if p.kind != "engine":
            continue
        block = next(b for b in _blocks(text, "PART") if _value(b, "name") == f"MERLIN_{ex['tag']}_{p.key}")
        for line in ("throttleLocked = True", "allowShutdown = False", "EngineType = SolidBooster"):
            assert line in block, (p.key, line)
        props = re.findall(r"PROPELLANT\n\t\t\{\n\t\t\tname = (\S+)", block)
        assert len(props) == 1 and props[0] in grains
        assert p.dry_kg == 0.0, "MERLIN's casing relation includes the nozzle, so the nozzle part weighs nothing"


def test_the_grain_sits_in_the_motor_casing_at_the_grains_density():
    res, ex = _solid()
    for p in ex["parts"]:
        if p.resources:
            assert p.key.endswith("_tank_grain")
            for rn in p.resources:
                assert ex["resources"][rn]["density_kg_m3"] == \
                    res.spec.solid_propellants[ex["resources"][rn]["propellant"]].density_kg_m3


def test_a_part_above_the_command_part_still_hangs_from_the_tree():
    """Scout's top stage has an adapter cone above its forward skirt (the root); it once had no parent."""
    _, ex = _solid()
    assert [p.key for p in ex["parts"] if p.parent is None] == [ex["parts"][0].key]
    cone = next(p for p in ex["parts"] if p.key == "s4_fwd_adapter")
    assert cone.parent == ex["parts"][0].key and cone.own_node == "bottom" and cone.parent_node == "top"


def test_four_solid_stages_fire_and_separate_in_order():
    _, ex = _solid()
    ign = {p.stage: p.istg for p in ex["parts"] if p.kind == "engine"}
    sep = {p.stage: p.istg for p in ex["parts"] if p.kind == "decoupler"}
    order = [ign[1], sep[1], ign[2], sep[2], ign[3], sep[3], ign[4]]
    assert order == sorted(order, reverse=True) and len(set(order)) == 7


def test_a_vacuum_engines_isp_never_goes_negative_at_sea_level():
    """MERLIN's straight line can cross zero before one atmosphere for a large-nozzle vacuum engine; the curve
    stops at ISP_FLOOR_S there instead of giving KSP a negative Isp."""
    e = dict(isp_vac_s=315.5, isp_1atm_s=-2246.5)
    keys = kx.isp_keys(e)
    assert len(keys) == 3
    (p0, i0, a0, b0), (pf, i_f, af, bf), (p1, i1, a1, b1) = keys
    assert i0 == 315.5 and i_f == i1 == kx.ISP_FLOOR_S and p1 == 1
    assert (i_f - i0) / (pf - p0) == pytest.approx(a0) and a0 == b0 == af
    assert bf == a1 == b1 == 0.0
    assert kx.isp_keys(dict(isp_vac_s=300.0, isp_1atm_s=270.0)) == [(0, 300.0, -30.0, -30.0), (1, 270.0, -30.0, -30.0)]


def _fake_ksp(name, mods=("ModuleManager.4.2.3.dll", "RealSolarSystem")):
    root = TMP / name
    (root / "GameData").mkdir(parents=True)
    for m in mods:
        (root / "GameData" / m).mkdir()
    for s in ("career1", "training"):
        (root / "saves" / s).mkdir(parents=True)
        (root / "saves" / s / "persistent.sfs").write_text("GAME\n{\n}\n", encoding="utf-8")
    (root / "saves" / "empty").mkdir()
    (root / "GameData" / "SomeoneElsesMod").mkdir()
    return root


def test_status_lists_real_saves_and_warns_when_rss_is_missing():
    st = kx.ksp_status(str(_fake_ksp("k1", mods=("ModuleManager.4.2.3.dll",))))
    assert st["found"] and st["saves"] == ["career1"]
    assert st["mods"]["ModuleManager"] and not st["mods"]["Real Solar System"]
    assert any("Real Solar System" in p for p in st["problems"])
    assert not kx.ksp_status(str(TMP / "nowhere"))["found"]


def test_install_writes_only_merlins_folder_and_the_one_craft():
    _, ex = _ex()
    root = _fake_ksp("k2")
    before = {p for p in root.rglob("*")}
    done = kx.install(ex, str(root), "career1")
    new = {p for p in root.rglob("*")} - before
    gd = root / "GameData" / "MERLIN_Export" / ex["tag"]
    craft = root / "saves" / "career1" / "Ships" / "VAB" / f"{ex['tag']}_MERLIN.craft"
    assert pathlib.Path(done["craft"]) == craft and craft.is_file()
    assert (gd / "parts.cfg").read_bytes() == pathlib.Path(ex["files"]["parts"]).read_bytes()
    for p in new:
        assert (gd in p.parents or p == gd or gd.parent == p
                or root / "saves" / "career1" / "Ships" in [p, *p.parents]), p
    with pytest.raises(kx.KSPExportError, match="no save"):
        kx.install(ex, str(root), "not_a_save")
    with pytest.raises(kx.KSPExportError, match="not a Kerbal"):
        kx.install(ex, str(TMP / "nowhere"), None)
