"""CAD export: DXF profile and STL/OBJ meshes (R15).

There is no CAD kernel and no DXF/STL library in this environment, so nothing here can claim the
files open correctly in a CAD application - that check has not been run and is stated as missing
in docs/VALIDATION_REPORT.md. What CAN be checked is checked, and the readers below are written
from the file-format specifications rather than from cad_export, so a writer bug cannot hide in a
shared helper:

  * the revolved mesh's volume against the exact closed form for a faceted solid of revolution,
    which only comes out right if the winding is outward everywhere and the surface closes;
  * edge-manifoldness (every edge shared by exactly two oppositely-wound triangles);
  * STL (binary and ASCII) and OBJ parsed back and compared triangle for triangle;
  * DXF parsed back into group-code pairs and checked for section structure, declared layers,
    entity balance (POLYLINE/SEQEND), and that the drawn silhouette matches the geometry.
"""
import math
import os
import struct


import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import cad_export as cad


# The suite's runner passes no fixtures, so one scratch directory stands in for pytest's tmp_path.
# Every test below writes a distinct filename into it.
from scratch import Scratch

TMP = Scratch("lv_cad_")


# Every reader below parses a file the writers emit with `{value:.6f}`, so a coordinate that survives the
# round trip is only ever accurate to half a unit in the sixth decimal - 5e-7 m, or half a micron, which is
# finer than any CAD tolerance a launch vehicle is built to. The old default of 1e-9 was therefore asserting
# something the file format cannot carry: it passed only while every profile coordinate happened to land on
# six decimals, and `test_dxf_silhouette_matches_the_geometry` failed on 13.320160296483188 being stored as
# "13.320160" - a 3.0e-7 rounding artifact, not a geometry error. Present in v0.26.0 and fixed in v0.28.0.
# Tighten this only by giving the writers more decimals, never by raising the number here.
DXF_PRECISION_M = 5e-7


def paths_equal(got, want, abs=DXF_PRECISION_M):
    """Elementwise point comparison, to the precision the exported file actually stores."""
    assert len(got) == len(want), f"{len(got)} points, expected {len(want)}"
    for (gx, gy), (wx, wy) in zip(got, want):
        assert gx == pytest.approx(wx, abs=abs) and gy == pytest.approx(wy, abs=abs)


# ------------------------------------------------------------------ independent format readers
def read_binary_stl(path):
    with open(path, "rb") as fh:
        blob = fh.read()
    n = struct.unpack_from("<I", blob, 80)[0]
    assert len(blob) == 84 + 50 * n, "binary STL length must be exactly 84 + 50 n"
    tris = []
    for i in range(n):
        f = struct.unpack_from("<12fH", blob, 84 + 50 * i)
        tris.append((f[3:6], f[6:9], f[9:12]))
    return tris, [struct.unpack_from("<12fH", blob, 84 + 50 * i)[0:3] for i in range(n)]


def read_ascii_stl(path):
    tris, cur = [], []
    with open(path) as fh:
        for raw in fh:
            w = raw.split()
            if not w:
                continue
            if w[0] == "vertex":
                cur.append(tuple(float(x) for x in w[1:4]))
            elif w[0] == "endloop":
                assert len(cur) == 3, "an STL outer loop holds exactly three vertices"
                tris.append(tuple(cur))
                cur = []
    return tris


def read_obj(path):
    verts, groups, cur = [], {}, None
    with open(path) as fh:
        for raw in fh:
            w = raw.split()
            if not w or w[0] == "#":
                continue
            if w[0] == "g":
                cur = w[1]
                groups[cur] = []
            elif w[0] == "v":
                verts.append(tuple(float(x) for x in w[1:4]))
            elif w[0] == "f":
                groups[cur].append(tuple(int(x.split("/")[0]) for x in w[1:4]))
    return verts, groups


def read_dxf(path):
    """DXF -> list of (code, value) pairs, exactly as the format is defined."""
    with open(path) as fh:
        lines = fh.read().split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    assert len(lines) % 2 == 0, "DXF is a stream of group-code/value PAIRS"
    return [(int(lines[i]), lines[i + 1]) for i in range(0, len(lines), 2)]


def dxf_entities(pairs):
    """Split the ENTITIES section into [(type, [(code, value), ...]), ...]."""
    start = pairs.index((2, "ENTITIES"))
    out, cur = [], None
    for code, val in pairs[start + 1:]:
        if code == 0:
            if val == "ENDSEC":
                break
            cur = (val, [])
            out.append(cur)
        elif cur is not None:
            cur[1].append((code, val))
    return out


# ------------------------------------------------------------------------------- the geometry
_C = {}


def result():
    if "r" not in _C:
        _C["r"] = default_result()
    return _C["r"]


def booster_result():
    if "b" not in _C:
        path = os.path.join(ROOT, "examples", "example_boosters.yaml")
        from launch_vehicle.config_io import load_design
        from launch_vehicle.convergence import size_vehicle
        _C["b"] = size_vehicle(load_design(path, ASSUMP))
    return _C["b"]


# ------------------------------------------------------------------------------ mesh geometry
def test_cylinder_volume_is_the_exact_faceted_value():
    """A revolved cylinder is a regular prism, whose volume is known in closed form.

    Volume = (n/2) R^2 sin(2 pi / n) L. Getting this exactly right (not just to the true pi R^2 L
    within a few percent) means the caps closed and every facet is wound outward.
    """
    R, L = 1.7, 4.3
    for facets in (3, 8, 64):
        m = cad.revolve([(0.0, R), (L, R)], facets=facets)
        exact = 0.5 * facets * R * R * math.sin(2 * math.pi / facets) * L
        assert cad.mesh_volume_m3(m) == pytest.approx(exact, rel=1e-12)
        assert cad.is_watertight(m)
        assert len(m) == 4 * facets                          # barrel (2n) + two n-triangle fans


def test_cone_volume_and_apex_sliver_free():
    """A nose cone: one apex vertex, n triangles to it, and the exact pyramid volume."""
    R, L, n = 1.1, 3.0, 32
    m = cad.revolve([(0.0, R), (L, 0.0)], facets=n)
    exact = 0.5 * n * R * R * math.sin(2 * math.pi / n) * L / 3.0
    assert cad.mesh_volume_m3(m) == pytest.approx(exact, rel=1e-12)
    assert cad.is_watertight(m)
    assert len(m) == 2 * n                                   # n sides + n base-fan triangles
    assert sum(1 for v in m.vertices if abs(v[0]) < 1e-12 and abs(v[1]) < 1e-12) == 2  # apex + cap centre


def test_frustum_and_step_volumes_match_the_closed_form():
    """A profile with a taper AND a diameter step (two points at one z) must still close."""
    prof = [(0.0, 1.0), (2.0, 1.0), (3.5, 0.6), (3.5, 0.3), (5.0, 0.3), (5.6, 0.0)]
    n = 48
    m = cad.revolve(prof, facets=n)
    assert cad.is_watertight(m)
    assert cad.mesh_volume_m3(m) == pytest.approx(cad.faceted_revolution_volume_m3(prof, n), rel=1e-12)


def test_faceted_volume_converges_to_the_body_of_revolution():
    """Sanity on the closed form itself: refine the facets and it must approach pi R^2 L.

    The inscribed n-gon is short of the circle by 1 - (n / 2 pi) sin(2 pi / n), i.e. (2 pi / n)^2 / 6
    to leading order, so at the default 64 facets the mesh under-reports volume by about 0.16 % -
    worth knowing before anyone takes a mass off the exported solid.
    """
    R, L = 2.0, 5.0
    true = math.pi * R * R * L
    prev = 0.0
    for n in (8, 32, 256):
        v = cad.faceted_revolution_volume_m3([(0.0, R), (L, R)], n)
        assert prev < v < true                               # inscribed: always short, always closer
        exact_deficit = 1.0 - n / (2 * math.pi) * math.sin(2 * math.pi / n)
        assert 1.0 - v / true == pytest.approx(exact_deficit, rel=1e-12)
        if n >= 32:                                          # the (2 pi / n)^2 / 6 form is asymptotic
            assert exact_deficit == pytest.approx((2 * math.pi / n) ** 2 / 6.0, rel=0.01)
        prev = v
    assert 1.0 - cad.faceted_revolution_volume_m3([(0.0, R), (L, R)],
                                                  cad.DEFAULT_FACETS) / true < 0.002


def test_offset_mesh_keeps_its_volume_and_moves_its_axis():
    prof = [(0.0, 0.8), (3.0, 0.8)]
    m0 = cad.revolve(prof, 32)
    m1 = cad.revolve(prof, 32, offset=(4.0, -1.5))
    assert cad.mesh_volume_m3(m1) == pytest.approx(cad.mesh_volume_m3(m0), rel=1e-12)
    cx = sum(v[0] for v in m1.vertices) / len(m1.vertices)
    cy = sum(v[1] for v in m1.vertices) / len(m1.vertices)
    assert cx == pytest.approx(4.0, abs=1e-9) and cy == pytest.approx(-1.5, abs=1e-9)


def test_revolve_rejects_nonsense():
    with pytest.raises(ValueError):
        cad.revolve([(0.0, 1.0), (1.0, 1.0)], facets=2)
    with pytest.raises(ValueError):
        cad.revolve([(0.0, 1.0), (1.0, -0.5)], facets=8)
    assert len(cad.revolve([(0.0, 1.0)], 8)) == 0             # a single station is not a solid


def test_non_manifold_edges_finds_a_hole():
    """The closure check has to be able to fail, so delete a face and confirm it reports it."""
    m = cad.revolve([(0.0, 1.0), (2.0, 1.0)], facets=16)
    assert cad.is_watertight(m)
    m.faces.pop()
    bad = cad.non_manifold_edges(m)
    assert len(bad) == 3 and not cad.is_watertight(m)


# ---------------------------------------------------------------------- profile out of the vehicle
def test_core_profile_spans_the_vehicle_monotonically():
    geom = result().geometry
    prof = cad.core_profile(geom)
    zs = [z for z, _ in prof]
    assert zs == sorted(zs), "the outer mould line must march upward, never back on itself"
    assert prof[0][0] == pytest.approx(geom.stage_base_z[1])
    assert prof[-1][0] == pytest.approx(geom.total_length)
    assert prof[-1][1] == pytest.approx(0.0), "the profile must end on the nose tip"
    assert max(r for _, r in prof) == pytest.approx(0.5 * geom.max_diameter)


def test_profile_keeps_diameter_steps_as_steps():
    """Where two segments meet at different diameters the profile holds two points at one z."""
    prof = cad.profile_from_segments(
        [type("S", (), {"z0": 0.0, "z1": 1.0, "d_bot": 2.0, "d_top": 2.0})(),
         type("S", (), {"z0": 1.0, "z1": 2.0, "d_bot": 1.0, "d_top": 1.0})()])
    assert prof == [(0.0, 1.0), (1.0, 1.0), (1.0, 0.5), (2.0, 0.5)]


def test_duplicate_stations_are_collapsed():
    """Neighbouring segments share a station at the same radius: that is one point, not two.

    The shared station itself is kept (it is a real station, and the DXF draws a line there); what
    must not happen is two coincident points, which would revolve into zero-area triangles.
    """
    prof = cad.profile_from_segments(
        [type("S", (), {"z0": 0.0, "z1": 1.0, "d_bot": 2.0, "d_top": 2.0})(),
         type("S", (), {"z0": 1.0, "z1": 2.0, "d_bot": 2.0, "d_top": 2.0})()])
    assert prof == [(0.0, 1.0), (1.0, 1.0), (2.0, 1.0)]
    assert len(set(prof)) == len(prof)


def test_engine_positions_sit_on_the_touching_pitch_circle():
    """One engine on the axis; several on the circle where their exit planes just touch."""
    assert cad.engine_positions(1, 2.0) == [(0.0, 0.0)]
    pos = cad.engine_positions(4, 1.0)
    rc = 1.0 / (2.0 * math.sin(math.pi / 4))
    assert all(math.hypot(x, y) == pytest.approx(rc) for x, y in pos)
    d = math.hypot(pos[0][0] - pos[1][0], pos[0][1] - pos[1][1])
    assert d == pytest.approx(1.0), "adjacent nozzles of a just-touching cluster are one exit diameter apart"


def test_booster_positions_are_evenly_spread():
    pos = cad.booster_positions(4, 3.0)
    assert len(pos) == 4
    assert all(math.hypot(x, y) == pytest.approx(3.0) for x, y in pos)
    angles = sorted(math.atan2(y, x) % (2 * math.pi) for x, y in pos)
    gaps = [b - a for a, b in zip(angles, angles[1:])]
    assert all(g == pytest.approx(math.pi / 2) for g in gaps)
    assert cad.booster_positions(0, 3.0) == []


# ------------------------------------------------------------------------ vehicle mesh assembly
def test_vehicle_meshes_are_all_closed_and_named():
    res = result()
    meshes = cad.vehicle_meshes(res, facets=24)
    assert len(meshes) >= 2
    assert meshes[0].name == "core_airframe"
    for m in meshes:
        assert cad.is_watertight(m), f"{m.name} is not closed"
        assert cad.mesh_volume_m3(m) > 0.0, f"{m.name} is wound inside-out"
    n_eng = sum(sr.envelope.n for sr in res.stages if sr.envelope is not None)
    assert sum(1 for m in meshes if "nozzle" in m.name) == n_eng


def test_airframe_volume_matches_its_own_profile():
    res = result()
    m = cad.vehicle_meshes(res, facets=32, engines=False, boosters=False)[0]
    expect = cad.faceted_revolution_volume_m3(cad.core_profile(res.geometry), 32)
    assert cad.mesh_volume_m3(m) == pytest.approx(expect, rel=1e-10)


def test_airframe_volume_is_bounded_by_its_bounding_cylinder():
    """An independent bound: the hull cannot hold more than the cylinder that contains it."""
    res = result()
    geom = res.geometry
    m = cad.vehicle_meshes(res, facets=64, engines=False, boosters=False)[0]
    v = cad.mesh_volume_m3(m)
    cyl = math.pi * (0.5 * geom.max_diameter) ** 2 * (geom.total_length - geom.stage_base_z[1])
    assert 0.3 * cyl < v < cyl


def test_boosters_appear_once_per_unit():
    res = booster_result()
    b = res.spec.boosters
    assert b is not None and b.n_total >= 2
    meshes = cad.vehicle_meshes(res, facets=16)
    names = [m.name for m in meshes]
    assert sum(1 for n in names if n.startswith("booster") and "nozzle" not in n) == b.n_total
    assert sum(1 for n in names if n.startswith("booster") and "nozzle" in n) == b.n_total
    for m in meshes:
        assert cad.is_watertight(m), f"{m.name} is not closed"


def test_engines_and_boosters_can_be_left_out():
    res = booster_result()
    assert len(cad.vehicle_meshes(res, 12, engines=False, boosters=False)) == 1


# ---------------------------------------------------------------------------- STL  /  OBJ files
def test_binary_stl_round_trips():
    meshes = cad.vehicle_meshes(result(), facets=16)
    p = cad.write_stl(meshes, TMP / "v.stl", binary=True)
    tris, normals = read_binary_stl(p)
    expect = [t for m in meshes for t in m.triangles()]
    assert len(tris) == len(expect)
    for got, want in zip(tris[:200], expect[:200]):
        for gv, wv in zip(got, want):
            for g, w in zip(gv, wv):
                assert g == pytest.approx(w, abs=1e-5)       # STL floats are single precision
    for n in normals[:200]:
        assert math.sqrt(sum(c * c for c in n)) == pytest.approx(1.0, abs=1e-5)


def test_ascii_stl_matches_the_binary_one():
    meshes = cad.vehicle_meshes(result(), facets=12)
    a = read_ascii_stl(cad.write_stl(meshes, TMP / "a.stl", binary=False))
    b, _ = read_binary_stl(cad.write_stl(meshes, TMP / "b.stl", binary=True))
    assert len(a) == len(b)
    for ta, tb in zip(a[:150], b[:150]):
        for va, vb in zip(ta, tb):
            for ca, cb in zip(va, vb):
                assert ca == pytest.approx(cb, abs=1e-5)


def test_stl_volume_survives_the_write():
    """The real question for a mesh file: does the solid still enclose the same volume?"""
    m = cad.vehicle_meshes(result(), facets=24, engines=False, boosters=False)[0]
    tris, _ = read_binary_stl(cad.write_stl(m, TMP / "s.stl"))
    v = sum(a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
            + a[2] * (b[0] * c[1] - b[1] * c[0]) for a, b, c in tris) / 6.0
    assert v == pytest.approx(cad.mesh_volume_m3(m), rel=1e-4)


def test_obj_keeps_the_part_names_and_indices():
    meshes = cad.vehicle_meshes(result(), facets=16)
    verts, groups = read_obj(cad.write_obj(meshes, TMP / "v.obj"))
    assert list(groups) == [m.name for m in meshes], "OBJ carries the part names that STL cannot"
    assert len(verts) == sum(len(m.vertices) for m in meshes)
    assert sum(len(f) for f in groups.values()) == sum(len(m) for m in meshes)
    for faces in groups.values():                            # 1-based, inside range, no zeros
        for f in faces:
            assert all(1 <= i <= len(verts) for i in f)
    first = groups[meshes[0].name][0]
    for got, want in zip([verts[i - 1] for i in first],
                         [meshes[0].vertices[i] for i in meshes[0].faces[0]]):
        for g, w in zip(got, want):
            assert g == pytest.approx(w, abs=1e-6)


def test_obj_groups_are_separately_closed():
    """Re-derive closure from the written file alone, per group, with the OBJ indices."""
    meshes = cad.vehicle_meshes(result(), facets=12)
    _verts, groups = read_obj(cad.write_obj(meshes, TMP / "v.obj"))
    for name, faces in groups.items():
        edges = {}
        for i, j, k in faces:
            for a, b in ((i, j), (j, k), (k, i)):
                edges[(a, b)] = edges.get((a, b), 0) + 1
        assert all(edges.get((b, a)) == 1 and n == 1 for (a, b), n in edges.items()), \
            f"group {name} is not a closed shell in the written OBJ"


# --------------------------------------------------------------------------------- DXF file
def test_dxf_has_the_sections_a_reader_needs():
    pairs = read_dxf(cad.write_dxf(result(), TMP / "p.dxf"))
    assert pairs[0] == (0, "SECTION") and pairs[-1] == (0, "EOF")
    assert (2, "HEADER") in pairs and (2, "TABLES") in pairs and (2, "ENTITIES") in pairs
    assert (1, "AC1009") in pairs, "declared as DXF R12"
    assert pairs.count((0, "SECTION")) == pairs.count((0, "ENDSEC")) == 3
    assert (70, "6") in pairs, "$INSUNITS = 6 (metres)"


def test_dxf_declares_every_layer_it_draws_on():
    pairs = read_dxf(cad.write_dxf(booster_result(), TMP / "p.dxf"))
    tables = pairs[:pairs.index((2, "ENTITIES"))]
    declared = {v for c, v in tables if c == 2} & {n for n, _, _ in cad.DXF_LAYERS}
    used = {v for _t, body in dxf_entities(pairs) for c, v in body if c == 8}
    assert used, "the drawing puts nothing on any layer"
    assert used <= declared, f"drawn on undeclared layers: {sorted(used - declared)}"
    assert {"LV_OML", "LV_TANK", "LV_ENGINE", "LV_BOOSTER", "LV_PAYLOAD"} <= used


def test_dxf_polylines_are_balanced():
    """Every POLYLINE needs its VERTEX run terminated by SEQEND or the file is unreadable."""
    ents = dxf_entities(read_dxf(cad.write_dxf(result(), TMP / "p.dxf")))
    kinds = [t for t, _ in ents]
    assert kinds.count("POLYLINE") == kinds.count("SEQEND") > 0
    depth = 0
    for t in kinds:
        if t == "POLYLINE":
            assert depth == 0, "a POLYLINE opened inside another"
            depth = 1
        elif t == "SEQEND":
            depth = 0
        elif t == "VERTEX":
            assert depth == 1, "a VERTEX outside any POLYLINE"
        else:
            assert depth == 0, f"{t} appeared inside a POLYLINE"
    assert depth == 0


def test_dxf_silhouette_matches_the_geometry():
    """The LV_OML polyline must be the outer mould line, mirrored, and nothing else."""
    res = result()
    geom = res.geometry
    ents = dxf_entities(read_dxf(cad.write_dxf(res, TMP / "p.dxf")))
    oml, grab = [], False
    for t, body in ents:
        layer = dict(body).get(8)
        if t == "POLYLINE":
            grab = layer == "LV_OML" and (70, "1") in body
        elif t == "VERTEX" and grab:
            d = dict(body)
            oml.append((float(d[10]), float(d[20])))
        elif t == "SEQEND":
            grab = False
    prof = cad.core_profile(geom)
    assert len(oml) == 2 * len(prof), "silhouette = profile up one side and back down the other"
    assert max(y for _x, y in oml) == pytest.approx(geom.total_length)
    assert max(x for x, _y in oml) == pytest.approx(0.5 * geom.max_diameter)
    assert min(x for x, _y in oml) == pytest.approx(-0.5 * geom.max_diameter)
    paths_equal(oml[:len(prof)], [(r, z) for z, r in prof])


def test_dxf_extents_contain_everything_drawn():
    """A reader zooms to $EXTMIN/$EXTMAX, so nothing drawn may fall outside them."""
    pairs = read_dxf(cad.write_dxf(booster_result(), TMP / "p.dxf"))
    hdr = pairs[:pairs.index((2, "TABLES"))]
    i0, i1 = hdr.index((9, "$EXTMIN")), hdr.index((9, "$EXTMAX"))
    xmin, ymin = float(hdr[i0 + 1][1]), float(hdr[i0 + 2][1])
    xmax, ymax = float(hdr[i1 + 1][1]), float(hdr[i1 + 2][1])
    assert xmin < xmax and ymin < ymax
    pts = []
    for _t, body in dxf_entities(pairs):
        d = dict(body)
        for cx, cy in ((10, 20), (11, 21)):
            if cx in d and cy in d:
                pts.append((float(d[cx]), float(d[cy])))
    assert pts
    assert all(xmin <= x <= xmax and ymin <= y <= ymax for x, y in pts), \
        "geometry drawn outside the declared extents"


def test_dxf_labels_can_be_switched_off():
    with_labels = read_dxf(cad.write_dxf(result(), TMP / "a.dxf", labels=True))
    without = read_dxf(cad.write_dxf(result(), TMP / "b.dxf", labels=False))
    n_with = sum(1 for t, _ in dxf_entities(with_labels) if t == "TEXT")
    n_without = sum(1 for t, _ in dxf_entities(without) if t == "TEXT")
    assert n_without < n_with
    assert n_without >= 2, "the overall dimensions stay even with labels off"


def test_dxf_names_the_vehicle_and_warns_it_is_not_a_drawing():
    pairs = read_dxf(cad.write_dxf(result(), TMP / "p.dxf"))
    texts = " ".join(v for c, v in pairs if c == 1)
    assert result().spec.name in texts
    assert "Not a manufacturing drawing" in texts


# ----------------------------------------------------------------------------------- bundle
def test_export_all_writes_the_four_dependency_free_files():
    paths = cad.export_all(result(), TMP / "cad", facets=16)
    assert set(paths) == {"dxf", "stl", "obj", "3mf"}
    for fmt, p in paths.items():
        assert os.path.exists(p) and os.path.getsize(p) > 0, f"{fmt} not written"
    assert "step" not in paths, \
        "no kernel is installed here, so STEP must not appear (cad_kernel decides, not this module)"
    assert "kernel_error" not in paths, "an absent kernel is not an error"


def test_mesh_summary_reports_closure_honestly():
    meshes = cad.vehicle_meshes(result(), facets=16)
    s = cad.mesh_summary(meshes)
    assert s["parts"] == len(meshes) == s["watertight_parts"]
    assert s["triangles"] == sum(len(m) for m in meshes) > 0
    assert s["airframe_volume_m3"] > 0 and s["airframe_area_m2"] > 0
    broken = cad.vehicle_meshes(result(), facets=16)
    broken[0].faces.pop()
    assert cad.mesh_summary(broken)["watertight_parts"] == len(meshes) - 1


# ------------------------------------------------------------- orthographic projection (isometric view)
def _signed_area(poly):
    """Shoelace area of one projected triangle (positive = counter-clockwise on screen)."""
    (x0, y0), (x1, y1), (x2, y2) = poly
    return 0.5 * ((x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0))


def test_view_basis_is_orthonormal():
    import numpy as np
    from launch_vehicle import schematic_2d as s2
    for elev, azim in ((0.0, 0.0), (18.0, -58.0), (-35.0, 140.0)):
        r, u, v = s2._view_basis(elev, azim)
        for a in (r, u, v):
            assert np.linalg.norm(a) == pytest.approx(1.0, abs=1e-12)
        for a, b in ((r, u), (u, v), (v, r)):
            assert float(a @ b) == pytest.approx(0.0, abs=1e-12)


def test_side_on_projection_maps_z_to_screen_height():
    """At zero elevation the vertical screen axis IS the vehicle axis, so heights are readable."""
    from launch_vehicle import schematic_2d as s2
    m = cad.revolve([(0.0, 1.0), (7.0, 1.0)], facets=16)
    polys, _n, _p = s2.project_meshes([m], elev_deg=0.0, azim_deg=0.0)
    ys = polys[..., 1]
    assert ys.min() == pytest.approx(0.0, abs=1e-9)
    assert ys.max() == pytest.approx(7.0, abs=1e-9)
    assert abs(polys[..., 0]).max() == pytest.approx(1.0, abs=1e-9)   # a vertex sits on the silhouette


def test_culling_keeps_only_front_faces_and_sorts_them_back_to_front():
    import numpy as np
    from launch_vehicle import schematic_2d as s2
    m = cad.revolve([(0.0, 1.2), (5.0, 1.2)], facets=32)
    polys, normals, _p = s2.project_meshes([m], 18.0, -58.0, cull=True)
    _r, _u, view = s2._view_basis(18.0, -58.0)
    assert 0 < len(polys) < len(m.faces), "culling must drop the back faces and keep the front ones"
    assert float((normals @ view).min()) > 0.0, "a back face survived the cull"
    assert all(_signed_area(p) >= -1e-12 for p in polys), \
        "a front face must project counter-clockwise; a negative one means the cull sign is wrong"
    allp, _n2, _p2 = s2.project_meshes([m], 18.0, -58.0, cull=False)
    assert len(allp) == len(m.faces)


def test_projected_front_faces_cover_the_silhouette_exactly():
    """For a closed solid the visible faces tile the silhouette, so their areas must sum to it.

    Side on, a cylinder's silhouette is a rectangle: the projected width of the facet polygon times
    the height. Hitting that exactly is a strong check on culling, winding and the projection together.
    """
    from launch_vehicle import schematic_2d as s2
    R, L, n = 1.4, 6.0, 24
    m = cad.revolve([(0.0, R), (L, R)], facets=n)
    polys, _no, _pa = s2.project_meshes([m], elev_deg=0.0, azim_deg=0.0)
    area = sum(_signed_area(p) for p in polys)
    width = polys[..., 0].max() - polys[..., 0].min()
    assert area == pytest.approx(width * L, rel=1e-9)
    assert width == pytest.approx(2 * R * math.cos(math.pi / n) if n % 2 else 2 * R, rel=1e-9)


def _contains(poly, pt) -> bool:
    (x0, y0), (x1, y1), (x2, y2) = poly
    px, py = pt
    d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    if abs(d) < 1e-15:
        return False
    a = ((y1 - y2) * (px - x2) + (x2 - x1) * (py - y2)) / d
    b = ((y2 - y0) * (px - x2) + (x0 - x2) * (py - y2)) / d
    return a >= 0 and b >= 0 and a + b <= 1


def test_painter_ordering_puts_the_nearer_surface_on_top():
    """Whatever covers a screen point last must be the nearest thing covering it.

    Checked where a strap-on overlaps the core, which is the one place in this drawing where
    getting the order backwards would be obvious - the booster would vanish into the stage.
    """
    import numpy as np
    from launch_vehicle import schematic_2d as s2
    res = booster_result()
    meshes = cad.vehicle_meshes(res, facets=24)
    elev, azim = 18.0, -58.0
    polys, _n, parts = s2.project_meshes(meshes, elev, azim)
    right, up, view = s2._view_basis(elev, azim)

    boosters = [i for i, m in enumerate(meshes) if m.name.startswith("booster")
                and "nozzle" not in m.name]
    near = max(boosters, key=lambda i: np.asarray(meshes[i].vertices).mean(axis=0) @ view)
    c3 = np.asarray(meshes[near].vertices).mean(axis=0)
    pt = (float(c3 @ right), float(c3 @ up))

    hits = [k for k, p in enumerate(polys) if _contains(p, pt)]
    assert len(hits) >= 2, "the probe point should land where the booster covers the core"
    assert len(set(int(parts[k]) for k in hits)) >= 2, \
        "the probe point must be where two parts overlap, or the test proves nothing"
    assert int(parts[hits[-1]]) == near, "the core was painted over the booster in front of it"


def test_isometric_figure_is_produced():
    from launch_vehicle import schematic_2d as s2
    p = TMP / "iso.png"
    s2.draw_isometric(result(), str(p), facets=16)
    assert p.exists() and p.stat().st_size > 10_000


# =============================================================================== 3MF (OPC zip)
# The reader below is written from the 3MF Core Specification and ECMA-376 Part 2, not from
# cad_export, so a bug shared between writer and reader cannot hide. The two OPC strings it
# checks were confirmed against the content-types stream of a package this project itself
# produces (the openpyxl workbook), rather than quoted from memory.
# write_3mf formats coordinates to 9 significant figures, so a round trip differs from the mesh
# by decimal truncation and nothing else. The bound is a half-unit in the ninth significant
# digit, 0.5e-8 relative per coordinate; volume is cubic in the coordinates, so three times that.
# Both are bounds, not fitted numbers - the measured error on this vehicle is 2e-9 - and
# test_3mf_vertices_round_trip_to_the_precision_the_writer_claims pins them to that cause.
THREEMF_COORD_TOL = 5e-9
THREEMF_VOLUME_TOL = 3 * THREEMF_COORD_TOL

CORE_NS = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
RELS_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
TYPES_NS = "{http://schemas.openxmlformats.org/package/2006/content-types}"


def read_3mf(path):
    """Parse a 3MF archive back into plain Python, independently of the writer."""
    import xml.etree.ElementTree as ET
    import zipfile

    with zipfile.ZipFile(path) as z:
        members = z.namelist()
        bad = z.testzip()
        assert bad is None, f"corrupt archive member {bad}"
        types = ET.fromstring(z.read("[Content_Types].xml"))
        rels = ET.fromstring(z.read("_rels/.rels"))
        model = ET.fromstring(z.read("3D/3dmodel.model"))

    objects = []
    for o in model.find(CORE_NS + "resources").findall(CORE_NS + "object"):
        mesh = o.find(CORE_NS + "mesh")
        objects.append({
            "id": o.get("id"), "name": o.get("name"), "type": o.get("type"),
            "vertices": [(float(v.get("x")), float(v.get("y")), float(v.get("z")))
                         for v in mesh.find(CORE_NS + "vertices")],
            "triangles": [(int(t.get("v1")), int(t.get("v2")), int(t.get("v3")))
                          for t in mesh.find(CORE_NS + "triangles")],
        })
    return {
        "members": members,
        "unit": model.get("unit"),
        "root": model.tag,
        "objects": objects,
        "items": [i.get("objectid") for i in model.find(CORE_NS + "build").findall(CORE_NS + "item")],
        "defaults": {d.get("Extension"): d.get("ContentType")
                     for d in types.findall(TYPES_NS + "Default")},
        "rels": [(r.get("Target"), r.get("Type")) for r in rels.findall(RELS_NS + "Relationship")],
        "metadata": {m.get("name"): m.text for m in model.findall(CORE_NS + "metadata")},
    }


def parsed_volume(obj):
    """Enclosed volume of a parsed 3MF object, by the divergence theorem, written fresh here."""
    v, total = obj["vertices"], 0.0
    for i, j, k in obj["triangles"]:
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = v[i], v[j], v[k]
        total += (ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx))
    return total / 6.0


def test_3mf_package_has_the_structure_the_specification_requires():
    p = TMP / "struct.3mf"
    cad.write_3mf(cad.vehicle_meshes(result(), facets=12), p, name="Struct test")
    got = read_3mf(p)

    assert got["members"][0] == "[Content_Types].xml", \
        "OPC readers are entitled to find the content types before the parts they type"
    assert set(got["members"]) == {"[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model"}
    assert got["defaults"]["model"] == "application/vnd.ms-package.3dmanufacturing-3dmodel+xml"
    assert got["defaults"]["rels"] == "application/vnd.openxmlformats-package.relationships+xml"
    assert got["rels"] == [("/3D/3dmodel.model",
                            "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel")]
    assert got["root"] == CORE_NS + "model", "wrong core namespace: no consumer would open it"
    assert got["metadata"]["Title"] == "Struct test"


def test_3mf_keeps_the_part_names_that_stl_throws_away():
    res = result()
    meshes = cad.vehicle_meshes(res, facets=12)
    p = TMP / "names.3mf"
    cad.write_3mf(meshes, p)
    got = read_3mf(p)

    assert [o["name"] for o in got["objects"]] == [m.name for m in meshes]
    assert all(o["type"] == "model" for o in got["objects"])
    # spec 4.1: a consumer must not output an object no <item> references
    assert sorted(got["items"], key=int) == sorted((o["id"] for o in got["objects"]), key=int)
    assert len(set(got["items"])) == len(got["items"]), "an object was built twice"


def test_3mf_triangle_indices_are_zero_based_and_in_range():
    p = TMP / "idx.3mf"
    cad.write_3mf(cad.revolve([(0.0, 1.0), (4.0, 1.0)], facets=8, name="can"), p)
    obj = read_3mf(p)["objects"][0]
    n = len(obj["vertices"])
    assert min(min(t) for t in obj["triangles"]) == 0, "indices must start at zero"
    assert max(max(t) for t in obj["triangles"]) == n - 1
    for t in obj["triangles"]:
        assert len(set(t)) == 3, f"degenerate triangle {t}"


def test_3mf_winding_is_outward_and_consistent_across_every_shared_edge():
    """Spec 4.1: two triangles sharing an edge must declare the shared vertices in opposite order."""
    p = TMP / "wind.3mf"
    cad.write_3mf(cad.revolve([(0.0, 1.2), (3.0, 1.2), (5.0, 0.0)], facets=16, name="nose"), p)
    obj = read_3mf(p)["objects"][0]

    directed = {}
    for t in obj["triangles"]:
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            directed[(a, b)] = directed.get((a, b), 0) + 1
    for (a, b), count in directed.items():
        assert count == 1, f"edge {a}->{b} declared {count} times in the same direction"
        assert directed.get((b, a)) == 1, f"edge {a}->{b} has no opposite, so the mesh is open"
    assert parsed_volume(obj) > 0, "a negative volume means the normals point inward"


def test_3mf_default_unit_is_metres_written_without_conversion():
    """The tool holds metres; writing them unconverted removes a whole class of unit error."""
    prof = [(0.0, 1.5), (10.0, 1.5), (14.0, 0.0)]
    mesh = cad.revolve(prof, facets=32, name="core")
    p = TMP / "unit_m.3mf"
    cad.write_3mf(mesh, p)
    got = read_3mf(p)

    assert got["unit"] == "meter"
    assert max(abs(z) for _x, _y, z in got["objects"][0]["vertices"]) == pytest.approx(14.0)
    assert parsed_volume(got["objects"][0]) == pytest.approx(
        cad.faceted_revolution_volume_m3(prof, 32), rel=1e-9)


def test_3mf_can_be_written_in_any_unit_the_specification_allows():
    prof = [(0.0, 1.5), (10.0, 1.5)]
    mesh = cad.revolve(prof, facets=16, name="can")
    base = cad.faceted_revolution_volume_m3(prof, 16)
    for unit, per_metre in cad.THREEMF_UNITS.items():
        p = TMP / f"unit_{unit}.3mf"
        cad.write_3mf(mesh, p, unit=unit)
        got = read_3mf(p)
        assert got["unit"] == unit
        # volume scales with the cube of the length unit, exactly
        assert parsed_volume(got["objects"][0]) == pytest.approx(base * per_metre ** 3, rel=1e-6)
    assert sorted(cad.THREEMF_UNITS) == ["centimeter", "foot", "inch", "meter", "micron",
                                         "millimeter"], "the spec permits exactly these six"


def test_3mf_refuses_a_unit_the_specification_does_not_define():
    with pytest.raises(ValueError) as e:
        cad.write_3mf(cad.revolve([(0.0, 1.0), (1.0, 1.0)], facets=8), TMP / "bad.3mf",
                      unit="furlong")
    assert "furlong" in str(e.value)


def test_3mf_and_stl_describe_the_same_triangles():
    """Two formats, one mesh: if they disagree, one of the writers is editing the geometry."""
    meshes = cad.vehicle_meshes(result(), facets=12)
    cad.write_3mf(meshes, TMP / "same.3mf")
    cad.write_stl(meshes, TMP / "same.stl", binary=True)
    got = read_3mf(TMP / "same.3mf")

    assert sum(len(o["triangles"]) for o in got["objects"]) == sum(len(m) for m in meshes)
    with open(TMP / "same.stl", "rb") as fh:
        fh.seek(80)
        n_stl = struct.unpack("<I", fh.read(4))[0]
    assert n_stl == sum(len(o["triangles"]) for o in got["objects"])
    assert sum(parsed_volume(o) for o in got["objects"]) == pytest.approx(
        sum(cad.mesh_volume_m3(m) for m in meshes), rel=THREEMF_VOLUME_TOL)


def test_3mf_vertices_round_trip_to_the_precision_the_writer_claims():
    """The only thing between the mesh and the file is decimal truncation.

    The writer formats to 9 significant figures - 0.1 micron on a 70 m vehicle, and better than
    the float32 that binary STL stores - so the parsed coordinates must match the mesh exactly at
    that precision, and the volume discrepancy must be truncation rather than a lost or reordered
    triangle. This is the check that pins THREEMF_VOLUME_TOL to a cause instead of a fudge.
    """
    meshes = cad.vehicle_meshes(result(), facets=12)
    cad.write_3mf(meshes, TMP / "prec.3mf")
    got = read_3mf(TMP / "prec.3mf")

    assert len(got["objects"]) == len(meshes)
    for obj, mesh in zip(got["objects"], meshes):
        assert obj["triangles"] == [tuple(f) for f in mesh.faces], f"{mesh.name}: faces changed"
        assert len(obj["vertices"]) == len(mesh.vertices)
        for parsed, original in zip(obj["vertices"], mesh.vertices):
            for g, w in zip(parsed, original):
                assert g == pytest.approx(w, rel=THREEMF_COORD_TOL, abs=1e-12), \
                    f"{mesh.name}: {g} vs {w}"


def test_3mf_refuses_to_write_an_empty_model():
    with pytest.raises(ValueError) as e:
        cad.write_3mf([cad.Mesh(name="nothing")], TMP / "empty.3mf")
    assert "no mesh" in str(e.value)


def test_3mf_skips_a_degenerate_part_rather_than_writing_an_invalid_object():
    meshes = [cad.Mesh(name="sliver"), cad.revolve([(0.0, 1.0), (2.0, 1.0)], facets=8, name="real")]
    cad.write_3mf(meshes, TMP / "skip.3mf")
    got = read_3mf(TMP / "skip.3mf")
    assert [o["name"] for o in got["objects"]] == ["real"]
    assert got["items"] == ["1"], "ids must stay contiguous after a part is dropped"


def test_export_all_writes_the_3mf_alongside_the_other_three():
    paths = cad.export_all(result(), TMP / "bundle", facets=12, stem="veh")
    assert {"dxf", "stl", "obj", "3mf"} <= set(paths)
    assert paths["3mf"].endswith("veh.3mf")
    got = read_3mf(paths["3mf"])
    assert got["objects"] and got["unit"] == "meter"


# ------------------------------------------------- exact vs faceted, the kernel route's premise
def test_the_faceted_deficit_is_the_inscribed_polygon_ratio_for_any_profile():
    """faceted / exact = n sin(2 pi / n) / (2 pi), independent of the profile. The claim the
    optional kernel route rests on, so it is checked rather than asserted in a docstring."""
    profiles = [[(0.0, 1.0), (5.0, 1.0)],
                [(0.0, 2.0), (3.0, 1.0), (4.0, 0.0)],
                cad.core_profile(result().geometry)]
    for prof in profiles:
        exact = cad.exact_revolution_volume_m3(prof)
        assert exact > 0
        for n in (8, 16, 64, 256):
            ratio = cad.faceted_revolution_volume_m3(prof, n) / exact
            assert ratio == pytest.approx(cad.faceted_volume_ratio(n), rel=1e-12)
            assert ratio < 1.0, "an inscribed polygon cannot enclose more than the circle"


def test_the_exact_volume_is_the_frustum_formula_on_shapes_with_known_answers():
    """Checked against solids whose volume is known in closed form without any frustum sum."""
    import math as _m
    cyl = cad.exact_revolution_volume_m3([(0.0, 2.0), (5.0, 2.0)])
    assert cyl == pytest.approx(_m.pi * 4.0 * 5.0, rel=1e-12)
    cone = cad.exact_revolution_volume_m3([(0.0, 3.0), (7.0, 0.0)])
    assert cone == pytest.approx(_m.pi * 9.0 * 7.0 / 3.0, rel=1e-12)
    # a cone on a cylinder, summed independently
    stack = cad.exact_revolution_volume_m3([(0.0, 2.0), (5.0, 2.0), (8.0, 0.0)])
    assert stack == pytest.approx(cyl + _m.pi * 4.0 * 3.0 / 3.0, rel=1e-12)
    assert cad.exact_revolution_volume_m3([(0.0, 0.0), (5.0, 0.0)]) == pytest.approx(0.0)


def test_mesh_volume_approaches_the_exact_volume_as_the_facet_count_rises():
    prof = cad.core_profile(result().geometry)
    exact = cad.exact_revolution_volume_m3(prof)
    errors = [abs(cad.mesh_volume_m3(cad.revolve(prof, n)) - exact) / exact for n in (8, 32, 128)]
    assert errors[0] > errors[1] > errors[2], f"not converging: {errors}"
    assert errors[2] < 1e-3
