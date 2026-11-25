"""The optional CadQuery/OpenCASCADE route (cad_kernel).

READ THIS BEFORE TRUSTING ANY OF IT. CadQuery is not installed in this environment and cannot be
- the container has no DNS, so pip cannot reach PyPI - which means NOT ONE TEST HERE HAS TOUCHED A
REAL OPENCASCADE KERNEL. A recording stub stands in for it. What that stub can and cannot prove:

  CAN   - that the geometry our code hands the kernel describes the intended body: the stub
          computes each revolved volume from the points and axis it is actually given, by Pappus'
          theorem on the polygon (V = 2 pi Q_rho), which is a different calculation from the
          frustum sum in cad_export. Pass the wrong axis, drop the lateral offset or mangle the
          meridian and the two disagree.
  CAN   - that the volume cross-check REJECTS a bad solid rather than exporting it. That is the
          test that earns the module its keep, because it is the guard that stands in for the
          kernel testing we cannot do here (test_a_wrong_axis_is_caught_and_nothing_is_written).
  CAN   - that the export adapter copes with each documented CadQuery API spelling, and that an
          exporter which writes an empty file is treated as a failure.
  CANNOT - that OpenCASCADE accepts these calls at all, or that the workplane convention the stub
          encodes (which is the one CadQuery's documentation describes) is the one it implements.
          Only running it on a real install can show that; cad_kernel.verify_solids() is what does
          it there, and until someone has run it the exact-solid formats remain unproven.
"""
import math
import os
import sys


import pytest
from helpers import *                                        # noqa: F401,F403
from launch_vehicle import cad_export as ce
from launch_vehicle import cad_kernel as ck

from scratch import Scratch

TMP = Scratch("lv_kernel_")

BOOST = os.path.join(ROOT, "examples", "example_boosters.yaml")


def booster_result():
    """A vehicle with strap-ons, so the offset parts are exercised (boosters are not an override)."""
    from launch_vehicle.config_io import load_design
    from launch_vehicle.convergence import size_vehicle
    return size_vehicle(load_design(BOOST, ASSUMP))


# =========================================================================== the recording stub
def _pappus_volume(points, ax0, ax1):
    """Volume of the body swept by a closed planar polygon revolved about the given axis.

    Independent of cad_export: Pappus' theorem in the (rho, zeta) coordinates of the axis the
    caller actually passed, V = 2 pi Q_rho with Q_rho = (1/6) sum (r_i + r_i+1) cross_i. Because
    rho is measured from THAT axis, a wrong axis or a missing offset changes the answer.
    """
    dx, dy, dz = ax1[0] - ax0[0], ax1[1] - ax0[1], ax1[2] - ax0[2]
    n = math.sqrt(dx * dx + dy * dy + dz * dz)
    if n == 0:
        raise ValueError("degenerate revolution axis")
    dx, dy, dz = dx / n, dy / n, dz / n
    pr = []
    for px, py, pz in points:
        vx, vy, vz = px - ax0[0], py - ax0[1], pz - ax0[2]
        zeta = vx * dx + vy * dy + vz * dz
        ox, oy, oz = vx - zeta * dx, vy - zeta * dy, vz - zeta * dz
        pr.append((math.sqrt(ox * ox + oy * oy + oz * oz), zeta))
    q = 0.0
    for (r0, z0), (r1, z1) in zip(pr, pr[1:] + pr[:1]):
        q += (r0 + r1) * (r0 * z1 - r1 * z0)
    return abs(2.0 * math.pi * q / 6.0), pr


class _BB:
    def __init__(self, box):
        (self.xmin, self.xmax, self.ymin, self.ymax, self.zmin, self.zmax) = box


class _Shape:
    """Stands in for an OCC solid: knows only its volume and bounding box."""

    def __init__(self, volume, box, label="solid"):
        self._v, self._b, self.label = volume, box, label
        self.brep_written = None

    def Volume(self):
        return self._v

    def BoundingBox(self):
        return _BB(self._b)

    def translate(self, v):
        x, y, z = (v.x, v.y, v.z) if hasattr(v, "x") else v
        b = self._b
        return _Shape(self._v, (b[0] + x, b[1] + x, b[2] + y, b[3] + y, b[4] + z, b[5] + z),
                      self.label)

    def exportBrep(self, path):
        with open(path, "w") as fh:
            fh.write("DBRep_DrawableShape\n")
        self.brep_written = path
        return True


def _revolved_shape(points, ax0, ax1, label="solid"):
    """Build a stub shape from real geometry: Pappus volume, and the bbox the sweep implies."""
    vol, pr = _pappus_volume(points, ax0, ax1)
    if abs(ax1[0] - ax0[0]) > 1e-12 or abs(ax1[1] - ax0[1]) > 1e-12:
        raise ValueError(f"the stub only revolves about a z-parallel axis, got {ax0}->{ax1}")
    rmax = max(r for r, _z in pr)
    zlo = min(z for _r, z in pr) + ax0[2]
    zhi = max(z for _r, z in pr) + ax0[2]
    return _Shape(vol, (ax0[0] - rmax, ax0[0] + rmax, ax0[1] - rmax, ax0[1] + rmax, zlo, zhi),
                  label)


class _Vector:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        if hasattr(x, "__len__"):
            x, y, z = (list(x) + [0.0, 0.0])[:3]
        elif hasattr(x, "x"):
            x, y, z = x.x, x.y, x.z
        self.x, self.y, self.z = float(x), float(y), float(z)

    def toTuple(self):
        return (self.x, self.y, self.z)


def _xyz(p):
    return (p.x, p.y, p.z) if hasattr(p, "x") else tuple(list(p) + [0.0, 0.0])[:3]


class _Wire:
    def __init__(self, points):
        self.points = [_xyz(p) for p in points]

    @classmethod
    def makePolygon(cls, points, *a, **k):
        return cls(points)


class _Solid:
    @staticmethod
    def revolve(outerWire, innerWires, angleDegrees, axisStart, axisEnd):
        assert angleDegrees == pytest.approx(360.0), "a solid of revolution needs a full turn"
        assert not innerWires, "the profiles here have no inner loops"
        RECORD.append(("Solid.revolve", list(outerWire.points), _xyz(axisStart), _xyz(axisEnd)))
        return _revolved_shape(outerWire.points, _xyz(axisStart), _xyz(axisEnd))


# local (u, v, w) -> global, for the workplane names this module uses. "XZ" has xDir (1,0,0) and
# normal (0,-1,0), which is the convention CadQuery's documentation describes.
_PLANES = {"XZ": lambda u, v, w: (u, -w, v),
           "XY": lambda u, v, w: (u, v, w)}


class _Workplane:
    def __init__(self, plane="XY"):
        if plane not in _PLANES:
            raise ValueError(f"the stub knows only {sorted(_PLANES)}, got {plane!r}")
        self.plane, self.pending, self.shape, self.closed = plane, [], None, False

    def _to_world(self, p):
        u, v, w = (list(p) + [0.0, 0.0])[:3]
        return _PLANES[self.plane](float(u), float(v), float(w))

    def polyline(self, pts, *a, **k):
        self.pending = [self._to_world(p) for p in pts]
        RECORD.append(("polyline", self.plane, [tuple(p) for p in pts]))
        return self

    def close(self):
        self.closed = True
        return self

    def revolve(self, angleDegrees=360.0, axisStart=None, axisEnd=None, *a, **k):
        assert self.closed, "revolve() on an open wire would not make a solid"
        a0 = self._to_world(_xyz(axisStart) if axisStart is not None else (0, 0, 0))
        a1 = self._to_world(_xyz(axisEnd) if axisEnd is not None else (0, 1, 0))
        RECORD.append(("Workplane.revolve", list(self.pending), a0, a1))
        self.shape = _revolved_shape(self.pending, a0, a1)
        return self

    def translate(self, v):
        RECORD.append(("translate", _xyz(v)))
        self.shape = self.shape.translate(_Vector(*_xyz(v)))
        return self

    def val(self):
        return self.shape


class _Compound:
    @staticmethod
    def makeCompound(shapes):
        shapes = list(shapes)
        vol = sum(s.Volume() for s in shapes)
        boxes = [s.BoundingBox() for s in shapes]
        box = (min(b.xmin for b in boxes), max(b.xmax for b in boxes),
               min(b.ymin for b in boxes), max(b.ymax for b in boxes),
               min(b.zmin for b in boxes), max(b.zmax for b in boxes))
        s = _Shape(vol, box, "compound")
        RECORD.append(("makeCompound", len(shapes)))
        return s


class _Color:
    def __init__(self, *rgba):
        self.rgba = rgba


class _Assembly:
    """Records what went into the tree, and writes a file for whichever API the module calls."""
    allow_export = True
    allow_save = False

    def __init__(self, obj=None, loc=None, name=None, color=None, metadata=None):
        self.name, self.children = name, []

    def add(self, obj, name=None, loc=None, color=None, metadata=None):
        self.children.append((name, obj, color))
        return self

    def _write(self, path, how):
        with open(path, "w") as fh:
            fh.write(f"ISO-10303-21; /* stub {how} {len(self.children)} parts */ END-ISO-10303-21;")
        RECORD.append((how, path, [c[0] for c in self.children]))

    def export(self, path, exportType=None, **kw):
        if not type(self).allow_export:
            raise AttributeError("this CadQuery version has no Assembly.export")
        self._write(path, "assembly.export")

    def save(self, path, exportType=None, **kw):
        if not type(self).allow_save:
            raise AttributeError("this CadQuery version has no Assembly.save")
        self._write(path, "assembly.save")


class _ExportTypes:
    STEP, STL, AMF, VRML, THREEMF, GLTF = "STEP", "STL", "AMF", "VRML", "3MF", "GLTF"


class _Exporters:
    ExportTypes = _ExportTypes
    fail = False

    @staticmethod
    def export(obj, path, exportType=None, tolerance=None, **kw):
        if _Exporters.fail:
            raise RuntimeError("exporters.export refused")
        with open(path, "w") as fh:
            fh.write(f"stub {exportType} tolerance={tolerance}")
        RECORD.append(("exporters.export", path, exportType, tolerance))


RECORD: list = []


class _FakeCq:
    __version__ = "2.stub"
    Vector, Wire, Solid, Workplane, Compound, Color, Assembly = (
        _Vector, _Wire, _Solid, _Workplane, _Compound, _Color, _Assembly)
    exporters = _Exporters


def install_stub():
    """Put the stub where `import cadquery` will find it, and clear the call record."""
    RECORD.clear()
    _Assembly.allow_export, _Assembly.allow_save, _Exporters.fail = True, False, False
    sys.modules["cadquery"] = _FakeCq
    return _FakeCq


def remove_stub():
    sys.modules.pop("cadquery", None)


# ==================================================================== availability, honestly
def test_the_kernel_really_is_absent_here():
    """The premise of this whole file: no CadQuery in this environment, so no real-kernel proof."""
    remove_stub()
    assert ck.available() is False
    st = ck.status()
    assert st["available"] is False and st["version"] is None
    assert "pip install cadquery" in st["install"]
    assert "not importable" in st["reason"]


def test_nothing_in_the_tool_breaks_without_it():
    remove_stub()
    res = default_result()
    paths = ce.export_all(res, TMP / "nokernel", stem="v")
    assert set(paths) == {"dxf", "stl", "obj", "3mf"}, paths
    assert "step" not in paths and "kernel_error" not in paths
    for p in paths.values():
        assert os.path.getsize(p) > 0


def test_asking_for_solids_without_a_kernel_says_so_clearly():
    remove_stub()
    with pytest.raises(ck.KernelUnavailable) as e:
        ck.export_solids(default_result(), TMP / "never")
    assert "pip install cadquery" in str(e.value)
    assert not os.path.exists(TMP / "never" / "vehicle.step")


def test_the_summary_states_the_mesh_deficit_the_kernel_route_exists_to_remove():
    remove_stub()
    s = ck.summary()
    assert s["available"] is False
    # 1 - n sin(2 pi / n) / (2 pi) at 64 facets = 0.160561%, the whole reason the kernel route
    # is worth having: a mesh export of this vehicle is a sixth of a percent light on volume
    assert s["mesh_volume_deficit_at_64_facets"] == pytest.approx(1.60561e-3, rel=1e-4)


def test_status_reports_a_present_kernel():
    install_stub()
    try:
        st = ck.status()
        assert st["available"] is True and st["version"] == "2.stub"
        assert "step" in st["formats"] and "brep" in st["formats"]
        assert "3mf" not in st["formats"], \
            "the kernel must not duplicate a format cad_export already writes: two routes on one name means one of them is unreachable"
    finally:
        remove_stub()


# ======================================================== the geometry handed to the kernel
def test_both_routes_reproduce_the_closed_form_volume():
    """The stub integrates what it is given; cad_export sums frusta. They must agree."""
    cq = install_stub()
    try:
        prof = [(0.0, 1.5), (10.0, 1.5), (12.0, 0.9), (14.0, 0.0)]
        part = ck.Part("test", prof)
        want = ce.exact_revolution_volume_m3(prof)
        assert want > 0
        for name, fn in ck.ROUTES:
            got = ck._measure(fn(cq, part))[0]
            assert got == pytest.approx(want, rel=1e-9), f"route {name}: {got} vs {want}"
    finally:
        remove_stub()


def test_an_offset_part_is_revolved_about_its_own_axis_not_the_centreline():
    """The nozzle and booster offsets are where a solid-of-revolution export usually goes wrong."""
    cq = install_stub()
    try:
        prof = [(0.0, 0.4), (2.0, 0.4)]
        want = ce.exact_revolution_volume_m3(prof)
        for name, fn in ck.ROUTES:
            part = ck.Part("off", prof, offset=(3.0, -1.0))
            obj = fn(cq, part)
            vol, box = ck._measure(obj)
            assert vol == pytest.approx(want, rel=1e-9), f"{name} changed the volume"
            assert box[0] == pytest.approx(2.6) and box[1] == pytest.approx(3.4), f"{name} x"
            assert box[2] == pytest.approx(-1.4) and box[3] == pytest.approx(-0.6), f"{name} y"
            assert ck._check(part, obj)["ok"], f"{name} failed its own check"
    finally:
        remove_stub()


def test_the_closed_meridian_returns_down_the_axis_without_duplicating_a_point():
    prof = [(0.0, 1.0), (5.0, 1.0)]                   # both ends open: two return points
    loop = ck._closed_loop(prof, 0.0, 0.0)
    assert loop == [(1.0, 0.0, 0.0), (1.0, 0.0, 5.0), (0.0, 0.0, 5.0), (0.0, 0.0, 0.0)]
    nose = [(0.0, 1.0), (5.0, 0.0)]                   # apex at the top: one return point only
    assert ck._closed_loop(nose, 0.0, 0.0) == [(1.0, 0.0, 0.0), (0.0, 0.0, 5.0), (0.0, 0.0, 0.0)]
    assert len(set(ck._closed_loop(nose, 0.0, 0.0))) == 3, "a repeated vertex makes the wire bad"


def test_the_part_list_matches_the_mesh_export_part_for_part():
    """Same names in the STEP tree and the OBJ groups, or the two exports cannot be compared."""
    res = booster_result()
    mesh_names = [m.name for m in ce.vehicle_meshes(res)]
    assert [p.name for p in ck.parts_for(res)] == mesh_names
    assert "core_airframe" in mesh_names and any("booster" in n for n in mesh_names)


def test_part_geometry_properties_come_from_the_profile_alone():
    p = ck.Part("x", [(1.0, 2.0), (4.0, 2.0)], offset=(1.0, 0.0))
    assert p.exact_volume_m3 == pytest.approx(math.pi * 4.0 * 3.0)
    # the suite's approx shim compares scalars only, so the box goes elementwise
    for got, want in zip(p.bbox_m, (-1.0, 3.0, -2.0, 2.0, 1.0, 4.0)):
        assert got == pytest.approx(want)


# ================================================== the guard that stands in for kernel testing
def test_a_wrong_axis_is_caught_and_nothing_is_written():
    """The test this module exists for.

    A construction that revolves about the wrong axis produces a solid that looks perfectly
    healthy - closed, non-empty, exportable - and is wrong. The volume cross-check has to reject
    it, and export_solids() must leave no file behind when it does.
    """
    cq = install_stub()

    def wrong(cq_, part):
        prof = ck._clean(part.profile)
        x, y = part.offset
        pts = [cq_.Vector(*p) for p in ck._closed_loop(prof, x, y)]
        wire = cq_.Wire.makePolygon(pts + [pts[0]])
        # revolve about the centreline instead of the part's own axis: the classic offset bug
        return cq_.Solid.revolve(wire, [], 360.0, cq_.Vector(0, 0, 0), cq_.Vector(0, 0, 1))

    real = ck.ROUTES
    ck.ROUTES = (("wrong", wrong),)
    out = TMP / "rejected"
    try:
        part = ck.Part("offset_nozzle", [(0.0, 0.4), (2.0, 0.4)], offset=(3.0, 0.0))
        verdict = ck._check(part, wrong(cq, part))
        assert verdict["ok"] is False
        assert "volume" in verdict["why"]
        with pytest.raises(ck.KernelCheckFailed) as e:
            ck.export_solids(booster_result(), out)
        assert "nothing was written" in str(e.value)
        assert not list(out.glob("*.step")) if out.exists() else True
    finally:
        ck.ROUTES = real
        remove_stub()


def test_a_route_that_raises_is_recorded_not_swallowed():
    cq = install_stub()
    real = ck.ROUTES
    ck.ROUTES = (("boom", lambda c, p: (_ for _ in ()).throw(RuntimeError("kernel said no"))),)
    try:
        with pytest.raises(ck.KernelCheckFailed) as e:
            ck.build(default_result())
        assert "boom: raised RuntimeError: kernel said no" in str(e.value)
    finally:
        ck.ROUTES = real
        remove_stub()


def test_a_kernel_that_will_not_report_a_volume_is_not_trusted():
    install_stub()
    try:
        part = ck.Part("x", [(0.0, 1.0), (2.0, 1.0)])
        mute = _Shape(None, (0, 0, 0, 0, 0, 0))
        mute.Volume = lambda: (_ for _ in ()).throw(RuntimeError("no"))
        v = ck._check(part, mute)
        assert v["ok"] is False and "would not report a volume" in v["why"]
    finally:
        remove_stub()


def test_verify_solids_reports_every_part_and_the_route_used():
    install_stub()
    try:
        rep = ck.verify_solids(default_result())
        assert rep["all_ok"] is True
        assert rep["kernel"]["available"] is True
        assert len(rep["parts"]) == len(ck.parts_for(default_result()))
        for row in rep["parts"]:
            assert row["ok"] is True
            assert row["route"] in dict(ck.ROUTES)
            assert row["volume_rel_error"] < ck.VOLUME_TOL
            assert row["kernel_volume_m3"] == pytest.approx(row["exact_volume_m3"], rel=1e-9)
    finally:
        remove_stub()


# ============================================================================ the export calls
def test_step_is_written_from_the_assembly_so_the_part_names_survive():
    install_stub()
    out = TMP / "step"
    try:
        paths = ck.export_solids(default_result(), out, stem="v", formats=("step",))
        assert paths["step"].endswith("v.step") and os.path.getsize(paths["step"]) > 0
        wrote = [r for r in RECORD if r[0] == "assembly.export"]
        assert wrote, "STEP did not go through the assembly, so it has no part tree"
        names = wrote[0][2]
        assert "core_airframe" in names and len(names) == len(ck.parts_for(default_result()))
    finally:
        remove_stub()


def test_the_adapter_falls_back_when_this_version_lacks_export():
    """CadQuery moved assemblies from .save() to .export(); a user may have either."""
    install_stub()
    _Assembly.allow_export, _Assembly.allow_save = False, True
    try:
        ck.export_solids(default_result(), TMP / "oldapi", stem="v", formats=("step",))
        assert any(r[0] == "assembly.save" for r in RECORD), "the older spelling was never tried"
    finally:
        remove_stub()


def test_the_assembly_formats_carry_the_tessellation_tolerance():
    install_stub()
    try:
        paths = ck.export_solids(default_result(), TMP / "gltf", stem="v",
                                 formats=("gltf",), tolerance=2.5e-4)
        assert set(paths) == {"gltf"}
        calls = [r for r in RECORD if r[0] in ("exporters.export", "assembly.export")]
        assert calls, "glTF did not reach an exporter"
        tol = [c for c in calls if c[0] == "exporters.export" and c[3] == pytest.approx(2.5e-4)]
        assert tol or any(c[0] == "assembly.export" for c in calls), \
            "neither the assembly route nor the tolerance-bearing route was used"
    finally:
        remove_stub()


def test_the_kernel_offers_only_what_cad_export_cannot_write():
    """No format may be claimed by both routes: /api/cad resolves one name to one writer."""
    from launch_vehicle.webgui import CAD_FORMATS
    overlap = set(ck.KERNEL_FORMATS) & set(CAD_FORMATS)
    assert not overlap, f"{overlap} would be written by two routes, and only one would be reachable"
    assert set(ck.KERNEL_FORMATS) == {"step", "brep", "gltf"}
    assert "iges" not in ck.KERNEL_FORMATS, "not in CadQuery's documented export list"


def test_brep_prefers_the_native_shape_writer():
    install_stub()
    try:
        paths = ck.export_solids(default_result(), TMP / "brep", stem="v", formats=("brep",))
        assert os.path.getsize(paths["brep"]) > 0
        with open(paths["brep"]) as fh:
            assert "DBRep" in fh.read()
    finally:
        remove_stub()


def test_an_exporter_that_writes_nothing_is_a_failure_not_a_success():
    """A zero-byte STEP reported as written is the worst outcome available."""
    install_stub()
    out = TMP / "empty"
    os.makedirs(out, exist_ok=True)
    _Assembly.allow_export = True
    real = _Assembly._write
    _Assembly._write = lambda self, path, how: open(path, "w").close()
    try:
        with pytest.raises(ck.KernelCheckFailed) as e:
            ck.export_solids(default_result(), out, stem="v", formats=("step",))
        assert "is empty" in str(e.value)
    finally:
        _Assembly._write = real
        remove_stub()


def test_an_unknown_format_is_refused_before_any_work_is_done():
    install_stub()
    try:
        with pytest.raises(ValueError) as e:
            ck.export_solids(default_result(), TMP / "bad", formats=("step", "iges"))
        assert "iges" in str(e.value)
        # IGES is deliberately absent: CadQuery's documented export list does not include it
        assert "iges" not in ck.KERNEL_FORMATS
    finally:
        remove_stub()


def test_export_all_adds_the_kernel_formats_when_the_kernel_is_there():
    install_stub()
    try:
        paths = ce.export_all(default_result(), TMP / "both", stem="v")
        assert {"dxf", "stl", "obj", "3mf"} <= set(paths)
        assert "step" in paths, "the kernel was available but STEP was not written"
        assert "kernel_error" not in paths
    finally:
        remove_stub()


def test_a_kernel_failure_does_not_cost_the_mesh_exports():
    install_stub()
    real = ck.export_solids
    ck.export_solids = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("OCC fell over"))
    try:
        paths = ce.export_all(default_result(), TMP / "degrade", stem="v")
        assert {"dxf", "stl", "obj", "3mf"} <= set(paths)
        assert paths["kernel_error"] == "RuntimeError: OCC fell over"
        for k, p in paths.items():
            if k != "kernel_error":
                assert os.path.getsize(p) > 0
    finally:
        ck.export_solids = real
        remove_stub()


def test_parts_carry_the_drawing_colours_into_the_tree():
    cq = install_stub()
    try:
        assert ck._colour_for(cq, "core_airframe").rgba == ck.PART_COLOURS["core_airframe"]
        assert ck._colour_for(cq, "stage1_nozzle2").rgba == ck.PART_COLOURS["nozzle"]
        assert ck._colour_for(cq, "booster3_nozzle").rgba == ck.PART_COLOURS["nozzle"]
        assert ck._colour_for(cq, "something_else") is None
    finally:
        remove_stub()
