"""Exact-solid CAD export through an OPTIONAL geometry kernel (CadQuery / OpenCASCADE).

WHAT THIS MODULE IS
The dependency-free exporters in cad_export.py write faceted meshes (STL, OBJ, 3MF) and a 2-D
profile (DXF). A faceted mesh is not a solid model: it understates the enclosed volume by
faceted_volume_ratio(n) - 0.161% at the default 64 facets - and a downstream user cannot take a
section, measure a radius or mate a part to it. What a structures or GSE engineer actually wants
is STEP: exact cylinders and cones with a part tree. That needs a geometry kernel, so this module
drives CadQuery when the user has chosen to install it, and does nothing at all when they have
not. Nothing else in the tool imports it eagerly; nothing fails without it.

WHAT HAS BEEN VERIFIED, AND WHAT HAS NOT
CadQuery could not be installed in the environment this module was written in - that container has
no DNS at all, so pip cannot reach PyPI - and so NO CALL IN THIS MODULE HAS EVER REACHED A REAL
OPENCASCADE KERNEL. What is tested (tests/test_cad_kernel.py) is the call contract against a
recording stub: that the right geometry, in the right units, in the right order, reaches the API
that the CadQuery documentation describes. That is not the same as proof that OCC accepts it.

Rather than ship that uncertainty to the user, the module checks itself on their machine:

  * Every solid is cross-checked against exact_revolution_volume_m3() - a closed-form frustum sum
    computed in cad_export.py with no kernel involved - and against the profile's bounding box,
    BEFORE anything is written. A solid that disagrees by more than VOLUME_TOL is never exported;
    export_solids() raises instead. So the failure mode of a wrong API convention is a loud,
    specific error, not a plausible-looking STEP file with the wrong geometry in it.
  * Two documented construction routes are attempted in order (see _build_solid). This is not
    guesswork between APIs: each candidate is accepted only if it reproduces the independent
    closed-form volume, and if neither does, both diagnostics are reported.

Run `python -m launch_vehicle.main cad --verify-kernel` on a machine with CadQuery installed to
see that cross-check printed per part. Until that has been done on a real kernel, treat the
exact-solid formats as unproven - the mesh formats are the ones with checks behind them.

INSTALLING IT
    pip install cadquery          (brings in cadquery-ocp, a large OpenCASCADE binary wheel)
CadQuery's own pages disagree about supported Python versions: the README says "Only Python 3.9
through 3.12 are currently supported" for pip installs, while the installation page says "Python
versions 3.9 and newer are supported" with a warning that a very new Python may be broken because
the dependencies lag. Both were read on 2026-10-17. CadQuery is Apache-2.0, so it carries no
licence consequence for this tool; it stays optional because of its size, not its licence.

Coordinates are those of cad_export/geometry: metres, z upward from the first-stage nozzle exit
plane, origin on the centreline.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import cad_export as ce

# A solid of revolution of a piecewise-linear profile is exactly a stack of frusta, so the kernel
# and the closed form should agree to rounding. The tolerance is loose enough for OCC's own
# tessellation-free volume integration, tight enough that a wrong axis or a dropped segment fails.
VOLUME_TOL = 1e-6                        # relative
BBOX_TOL_M = 1e-6                        # absolute, metres

# Named parts get the colours of their DXF layers, so the STEP tree reads like the drawing.
PART_COLOURS = {
    "core_airframe": (0.78, 0.78, 0.80, 1.0),      # light grey, LV_OML
    "nozzle": (0.80, 0.18, 0.12, 1.0),             # red, LV_ENGINE
    "booster": (0.20, 0.62, 0.26, 1.0),            # green, LV_BOOSTER
}

# Formats this module offers, deliberately only the ones cad_export CANNOT write.
#
# CadQuery can also export STL, 3MF, AMF and VRML, and offering those here was the first draft -
# but it would have been duplication dressed up as choice. Our meridians are piecewise linear, so
# the only curvature in the body is circumferential, and `--cad-facets` already controls that
# exactly; a kernel tessellation of the same shape is not a better mesh, just a mesh produced by
# more machinery. Worse, two routes writing "3mf" collide on one name and one of them becomes
# unreachable. So the kernel is asked only for what it alone can do: exact B-rep, and the
# assembly-tree formats.
#
# IGES is NOT offered either: CadQuery's import/export documentation does not list it, and an
# export route nobody has read about is not one to advertise.
KERNEL_FORMATS = {
    "step": "exact B-rep solids with a named part tree - the one to send to a CAD package",
    "brep": "OpenCASCADE native, lossless, for another OCC-based tool",
    "gltf": "assembly with the part tree, for web and real-time viewers",
}
ASSEMBLY_ONLY = {"gltf"}                 # CadQuery documents these on assemblies only
TESSELLATED = {"gltf"}                   # the only one here with a tessellation tolerance
DEFAULT_FORMATS = ("step",)
DEFAULT_TOLERANCE_M = 1e-3               # kernel tessellation tolerance for the mesh formats


class KernelUnavailable(RuntimeError):
    """CadQuery is not importable, so the exact-solid formats cannot be written."""


class KernelCheckFailed(RuntimeError):
    """A kernel solid did not reproduce the closed-form volume, so it was not exported."""


# ----------------------------------------------------------------------------- availability
def _import():
    try:
        import cadquery as cq                       # noqa: PLC0415
    except Exception as e:                           # noqa: BLE001
        raise KernelUnavailable(
            f"cadquery is not importable ({type(e).__name__}: {e}). Install it with "
            "'pip install cadquery'; the mesh and DXF exports do not need it.") from e
    return cq


def available() -> bool:
    """True when the exact-solid formats can be attempted. Never raises."""
    try:
        _import()
    except KernelUnavailable:
        return False
    return True


def status() -> dict:
    """What to show a user who wants to know why STEP is or is not on offer."""
    try:
        cq = _import()
    except KernelUnavailable as e:
        return {"available": False, "version": None, "reason": str(e),
                "formats": [], "install": "pip install cadquery"}
    return {"available": True,
            "version": getattr(cq, "__version__", "unknown"),
            "reason": "cadquery imported",
            "formats": sorted(KERNEL_FORMATS),
            "install": None}


# -------------------------------------------------------------------------------- geometry
def _clean(profile) -> list:
    """The same point cleanup revolve() does, so both routes revolve identical geometry."""
    out: list = []
    for z, r in profile:
        if r < -ce.EPS:
            raise ValueError(f"negative radius {r} at z = {z}")
        ce._append(out, z, max(r, 0.0))
    return out


def _closed_loop(profile: list, x: float, y: float) -> list:
    """The meridian section as a closed 3-D loop in the plane y = const containing the axis.

    Up the outer mould line, then straight back down the axis. Points with r = 0 already sit on
    the axis, so adding a return point there would duplicate a vertex and make the wire invalid.
    """
    pts = [(x + r, y, z) for z, r in profile]
    z_top, r_top = profile[-1][0], profile[-1][1]
    z_bot, r_bot = profile[0][0], profile[0][1]
    if r_top > ce.EPS:
        pts.append((x, y, z_top))
    if r_bot > ce.EPS:
        pts.append((x, y, z_bot))
    return pts


@dataclass
class Part:
    """One solid of revolution: the profile it came from, where its axis is, and what to call it."""
    name: str
    profile: list
    offset: tuple = (0.0, 0.0)
    solid: object = None
    route: str = ""
    checks: dict = field(default_factory=dict)

    @property
    def exact_volume_m3(self) -> float:
        return ce.exact_revolution_volume_m3(self.profile)

    @property
    def bbox_m(self) -> tuple:
        """(xmin, xmax, ymin, ymax, zmin, zmax) implied by the profile and the offset."""
        x, y = self.offset
        rs = [r for _z, r in self.profile]
        zs = [z for z, _r in self.profile]
        rmax = max(rs)
        return (x - rmax, x + rmax, y - rmax, y + rmax, min(zs), max(zs))


def _route_workplane(cq, part: Part):
    """Documented high-level idiom: draw the meridian on a workplane, revolve, translate.

    The profile is drawn on the XZ workplane as (radius, z) and revolved a full turn about the
    workplane's vertical axis, which is the global z axis; the lateral offset is applied after,
    because the revolution has to be about the part's own axis.
    """
    prof = _clean(part.profile)
    # the same closed meridian the primitive route uses, dropped to the workplane's (u, v) with
    # u = radius and v = z, so both routes provably revolve the same points
    loop = [(x, z) for (x, _y, z) in _closed_loop(prof, 0.0, 0.0)]
    wp = (cq.Workplane("XZ").polyline(loop).close()
          .revolve(360.0, (0.0, 0.0, 0.0), (0.0, 1.0, 0.0)))
    x, y = part.offset
    if abs(x) > ce.EPS or abs(y) > ce.EPS:
        wp = wp.translate((x, y, 0.0))
    return wp


def _route_primitive(cq, part: Part):
    """Low-level route: an explicit global-coordinate wire revolved about an explicit axis.

    Every coordinate here is global, and the axis is given as two points on it, so this route
    depends on no workplane convention at all. The axis is placed at the part's own (x, y), which
    bakes the lateral offset into the revolution and needs no translate step.
    """
    prof = _clean(part.profile)
    x, y = part.offset
    pts = [cq.Vector(*p) for p in _closed_loop(prof, x, y)]
    wire = cq.Wire.makePolygon(pts + [pts[0]])
    return cq.Solid.revolve(wire, [], 360.0, cq.Vector(x, y, 0.0), cq.Vector(x, y, 1.0))


ROUTES = (("workplane", _route_workplane), ("primitive", _route_primitive))


def _shape(obj):
    """The underlying Shape, whether a Workplane or a Solid came back."""
    val = getattr(obj, "val", None)
    return val() if callable(val) else obj


def _measure(obj) -> tuple:
    """(volume_m3, bbox) from the kernel, or (None, None) if it will not say."""
    shp = _shape(obj)
    try:
        vol = float(shp.Volume())
    except Exception:                                # noqa: BLE001
        return (None, None)
    try:
        bb = shp.BoundingBox()
        box = (bb.xmin, bb.xmax, bb.ymin, bb.ymax, bb.zmin, bb.zmax)
    except Exception:                                # noqa: BLE001
        box = None
    return (vol, box)


def _check(part: Part, obj) -> dict:
    """Cross-check one kernel solid against the closed form. Returns a verdict dict."""
    want = part.exact_volume_m3
    vol, box = _measure(obj)
    out = {"part": part.name, "exact_volume_m3": want, "kernel_volume_m3": vol,
           "volume_rel_error": None, "bbox_max_error_m": None, "ok": False,
           "why": ""}
    if vol is None:
        out["why"] = "the kernel would not report a volume"
        return out
    if want <= 0.0:
        out["why"] = "the profile encloses no volume"
        return out
    out["volume_rel_error"] = abs(vol - want) / want
    if out["volume_rel_error"] > VOLUME_TOL:
        out["why"] = (f"volume {vol:.6g} m^3 against the closed-form {want:.6g} m^3 "
                      f"({out['volume_rel_error']:.3%} out)")
        return out
    if box is not None:
        want_box = part.bbox_m
        out["bbox_max_error_m"] = max(abs(a - b) for a, b in zip(box, want_box))
        if out["bbox_max_error_m"] > BBOX_TOL_M:
            out["why"] = (f"bounding box out by {out['bbox_max_error_m']:.3g} m "
                          f"(kernel {box}, profile {want_box})")
            return out
    out["ok"] = True
    out["why"] = "matches the closed-form volume and bounding box"
    return out


def _build_solid(cq, part: Part) -> Part:
    """Build one solid, accepting only a construction that reproduces the closed-form volume."""
    attempts = []
    for route, fn in ROUTES:
        try:
            obj = fn(cq, part)
        except Exception as e:                       # noqa: BLE001
            attempts.append(f"{route}: raised {type(e).__name__}: {e}")
            continue
        verdict = _check(part, obj)
        if verdict["ok"]:
            part.solid, part.route, part.checks = obj, route, verdict
            return part
        attempts.append(f"{route}: {verdict['why']}")
    raise KernelCheckFailed(
        f"no construction reproduced the geometry of {part.name!r}; "
        f"nothing was written. Attempts: " + " | ".join(attempts))


# ------------------------------------------------------------------------------ the vehicle
def parts_for(res, engines: bool = True, boosters: bool = True) -> list:
    """The part list, named and positioned exactly as cad_export.vehicle_meshes() names them.

    Kept deliberately parallel to that function: the same names in the STEP tree and in the OBJ
    groups mean a user can compare the two exports part by part.
    """
    geom = res.geometry
    out = [Part("core_airframe", ce.core_profile(geom))]
    if engines:
        for sr in res.stages:
            env = sr.envelope
            if env is None:
                continue
            z_exit = geom.engine_exit_z[sr.index]
            prof = ce.nozzle_profile(z_exit, env.length_m, env.exit_diameter_m)
            for n, (x, y) in enumerate(ce.engine_positions(env.n, env.exit_diameter_m), start=1):
                out.append(Part(f"stage{sr.index}_nozzle{n}", prof, (x, y)))
    if boosters and geom.booster_segments and res.spec.boosters is not None:
        b = res.spec.boosters
        bp = ce.booster_profile(geom)
        noz = ce.nozzle_profile(b.base_z_offset_m, b.nozzle_length_m, b.exit_diameter_m)
        for n, (x, y) in enumerate(ce.booster_positions(b.n_total, geom.booster_x_m), start=1):
            out.append(Part(f"booster{n}", bp, (x, y)))
            out.append(Part(f"booster{n}_nozzle", noz, (x, y)))
    return [p for p in out if len(_clean(p.profile)) >= 2]


def build(res, engines: bool = True, boosters: bool = True) -> list:
    """Build and verify every part. Raises KernelCheckFailed before writing anything."""
    cq = _import()
    return [_build_solid(cq, p) for p in parts_for(res, engines, boosters)]


def _colour_for(cq, name: str):
    for key, rgba in PART_COLOURS.items():
        if key in name:
            try:
                return cq.Color(*rgba)
            except Exception:                        # noqa: BLE001
                return None
    return None


def assembly(cq, parts: list, name: str = "launch_vehicle"):
    """A named, coloured assembly, so STEP carries the part tree the mesh formats cannot."""
    assy = cq.Assembly(name=name)
    for p in parts:
        colour = _colour_for(cq, p.name)
        try:
            assy.add(p.solid, name=p.name, color=colour)
        except TypeError:
            assy.add(p.solid, name=p.name)           # older signature without color=
    return assy


def compound(cq, parts: list):
    """All solids as one shape, for the formats CadQuery documents on shapes rather than assemblies."""
    shapes = [_shape(p.solid) for p in parts]
    maker = getattr(getattr(cq, "Compound", None), "makeCompound", None)
    if callable(maker):
        return maker(shapes)
    return cq.Compound(shapes)                       # newer constructor-style spelling


# --------------------------------------------------------------------------------- writing
def _try(calls) -> tuple:
    """Run (label, thunk) candidates until one does not raise; return (label, errors)."""
    errors = []
    for label, thunk in calls:
        try:
            thunk()
        except Exception as e:                       # noqa: BLE001
            errors.append(f"{label}: {type(e).__name__}: {e}")
            continue
        return label, errors
    return None, errors


def _write(cq, obj, path: str, kind: str, tolerance: float | None = None) -> str:
    """Write one file, tolerating the API change between CadQuery versions.

    CadQuery moved from the free function cq.exporters.export(obj, path, type) to the instance
    method obj.export(path, type), and assemblies from .save() to .export(). Which of those a user
    has depends on their version, so each documented spelling is tried in turn and the first that
    does not raise wins. The file is confirmed non-empty afterwards: an exporter that silently
    writes nothing must not be reported as a success.
    """
    import os

    enum = getattr(getattr(cq, "exporters", None), "ExportTypes", None)
    etype = getattr(enum, kind.upper(), None) if enum is not None else None
    kw = {}
    if tolerance is not None and kind in TESSELLATED:
        kw["tolerance"] = tolerance

    calls = []
    meth = getattr(obj, "export", None)
    if callable(meth):
        calls.append(("obj.export(path, type)", lambda: meth(path, etype or kind.upper(), **kw)))
        calls.append(("obj.export(path)", lambda: meth(path)))
    save = getattr(obj, "save", None)
    if callable(save):
        calls.append(("obj.save(path, type)", lambda: save(path, etype or kind.upper())))
        calls.append(("obj.save(path)", lambda: save(path)))
    free = getattr(getattr(cq, "exporters", None), "export", None)
    if callable(free):
        calls.append(("exporters.export(obj, path, type)",
                      lambda: free(obj, path, etype or kind.upper(), **kw)))
        calls.append(("exporters.export(obj, path)", lambda: free(obj, path)))
    if kind == "brep":
        shp = _shape(obj)
        brep = getattr(shp, "exportBrep", None)
        if callable(brep):
            calls.insert(0, ("Shape.exportBrep(path)", lambda: brep(path)))

    label, errors = _try(calls)
    if label is None:
        raise KernelCheckFailed(f"no documented CadQuery call wrote {kind.upper()} to {path}. "
                                "Tried: " + " | ".join(errors))
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        raise KernelCheckFailed(f"{label} reported success but {path} is empty")
    return str(path)


def export_solids(res, out_dir, stem: str = "vehicle", formats=DEFAULT_FORMATS,
                  tolerance: float = DEFAULT_TOLERANCE_M, name: str | None = None) -> dict:
    """Build, verify and write the exact-solid formats; return {format: path}.

    Verification happens first, for every part. Nothing is written unless every solid reproduces
    its closed-form volume, so a partial or wrong-geometry export cannot reach the user's disk.
    """
    import os

    cq = _import()
    bad = [f for f in formats if f not in KERNEL_FORMATS]
    if bad:
        raise ValueError(f"unknown kernel format(s) {bad}; this module writes "
                         f"{sorted(KERNEL_FORMATS)}")
    os.makedirs(out_dir, exist_ok=True)
    parts = build(res)                               # raises before anything is written
    assy = assembly(cq, parts, name=name or res.spec.name)
    comp = compound(cq, parts)

    paths = {}
    for fmt in formats:
        target = os.path.join(out_dir, f"{stem}.{fmt}")
        obj = assy if (fmt in ASSEMBLY_ONLY or fmt == "step") else comp
        paths[fmt] = _write(cq, obj, target, fmt, tolerance=tolerance)
    return paths


def verify_solids(res) -> dict:
    """Build every part and report the cross-check without writing anything.

    This is the honest answer to "does the kernel route work?". It is what
    `main.py cad --verify-kernel` prints, and it is the check that has never been run against a
    real OpenCASCADE kernel by the author of this module.
    """
    cq = _import()
    rows, ok = [], True
    for p in parts_for(res):
        try:
            built = _build_solid(cq, p)
        except KernelCheckFailed as e:
            rows.append({"part": p.name, "ok": False, "why": str(e),
                         "exact_volume_m3": p.exact_volume_m3, "kernel_volume_m3": None,
                         "volume_rel_error": None, "bbox_max_error_m": None, "route": None})
            ok = False
            continue
        row = dict(built.checks)
        row["route"] = built.route
        rows.append(row)
    return {"kernel": status(), "all_ok": ok and bool(rows), "parts": rows,
            "volume_tolerance": VOLUME_TOL, "bbox_tolerance_m": BBOX_TOL_M}


def summary(res=None) -> dict:
    """One dict for the report, the CLI and the GUI to show the same thing about the kernel."""
    st = status()
    out = {"available": st["available"], "version": st["version"], "reason": st["reason"],
           "formats": st["formats"], "install": st["install"],
           "mesh_volume_deficit_at_64_facets": 1.0 - ce.faceted_volume_ratio(ce.DEFAULT_FACETS)}
    if res is not None and st["available"]:
        try:
            out["verification"] = verify_solids(res)
        except Exception as e:                       # noqa: BLE001
            out["verification"] = {"all_ok": False, "error": f"{type(e).__name__}: {e}"}
    return out
