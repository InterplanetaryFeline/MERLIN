"""CAD export (R15): layered DXF inboard profile and triangulated 3D meshes (STL / OBJ).

Coordinates follow geometry.py: z in metres measured UPWARD from the first-stage nozzle exit
plane, x and y lateral, origin on the vehicle centreline. In the DXF the profile is drawn in the
XY plane with DXF-y = vehicle z (vehicle vertical, nose up), matching the report drawings.

Both formats are written directly from their published specifications, so the export adds no
third-party dependency:
  * DXF R12 ASCII (group-code pairs; AutoCAD release 12 reference). POLYLINE/VERTEX/SEQEND is
    used rather than LWPOLYLINE, and domes are polygonised, because R12 has neither LWPOLYLINE
    nor ELLIPSE - the result loads in every CAD package that reads DXF at all.
  * STL (binary and ASCII) and Wavefront OBJ, from meshes revolved out of the drawn outer mould
    line.
  * 3MF (3MF Core Specification, 3MF Consortium), which is an OPC zip of XML. It is the only
    dependency-free format here that records the UNIT its numbers are in and keeps the part
    names, so it is the one to prefer over STL.

STEP IS NOT WRITTEN BY THIS MODULE. A STEP B-rep needs a geometry kernel to produce and, more to
the point, to check, and an unverifiable solid model is worse than no solid model. The kernel
route lives in cad_kernel.py, which drives CadQuery/OpenCASCADE when the user has installed it
and cross-checks every solid it builds against exact_revolution_volume_m3() below; read that
module's docstring for what has and has not been verified there.

What this module delivers is verified: the mesh writers are checked against the exact volume of a
polygonal solid of revolution and for edge-manifoldness, the 3MF against the specification's
structure and an independent re-read of the archive, and the DXF against an independent
group-code parser (tests/test_cad_export.py). No check here is a substitute for opening the file
in a CAD application, which has not been done.
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field

from . import propulsion as prop

EPS = 1e-9
DEFAULT_FACETS = 64

# DXF layer table: (name, AutoCAD Color Index, linetype)
DXF_LAYERS = [
    ("LV_AXIS", 8, "CENTER"),            # centreline
    ("LV_OML", 7, "CONTINUOUS"),         # outer mould line (the one closed silhouette)
    ("LV_STATION", 9, "CONTINUOUS"),     # segment boundary stations
    ("LV_TANK", 5, "CONTINUOUS"),        # tank walls and domes
    ("LV_GRAIN", 30, "CONTINUOUS"),      # solid propellant grain and bore
    ("LV_ENGINE", 1, "CONTINUOUS"),      # engine / nozzle envelopes
    ("LV_BOOSTER", 3, "CONTINUOUS"),     # strap-on boosters
    ("LV_PAYLOAD", 4, "CONTINUOUS"),     # PAF and payload static envelope
    ("LV_TEXT", 7, "CONTINUOUS"),        # labels
    ("LV_DIM", 6, "CONTINUOUS"),         # overall dimensions
]

DOME_FACETS = 24                          # polygon segments per half-dome in the DXF


# --------------------------------------------------------------------------- outer mould line
def _append(pts: list, z: float, r: float) -> None:
    if pts and abs(pts[-1][0] - z) < EPS and abs(pts[-1][1] - r) < EPS:
        return                            # same station AND same radius: one point, not two
    pts.append((z, r))


def profile_from_segments(segments) -> list:
    """(z, r) outer mould line of a bottom-up segment list, base plane -> top.

    A diameter step between neighbouring segments is kept as two points at the same z, which
    revolves into a flat annular ring rather than a smeared cone.
    """
    pts: list = []
    for s in segments:
        _append(pts, s.z0, 0.5 * s.d_bot)
        _append(pts, s.z1, 0.5 * s.d_top)
    return pts


def core_profile(geom) -> list:
    """Outer mould line of the core airframe: stage-1 base plane up to the nose tip."""
    return profile_from_segments(geom.segments)


def booster_profile(geom) -> list:
    """Outer mould line of ONE strap-on booster (casing + nose cone), in vehicle z."""
    return profile_from_segments(geom.booster_segments) if geom.booster_segments else []


def nozzle_profile(z_exit: float, length_m: float, exit_diameter_m: float) -> list:
    """(z, r) silhouette of one nozzle, matching the 2-D schematic's bell (schematic_2d)."""
    d_th = 0.18 * exit_diameter_m
    return [(z_exit, 0.5 * exit_diameter_m),
            (z_exit + 0.62 * length_m, d_th),
            (z_exit + length_m, 0.9 * d_th)]


def engine_positions(n: int, exit_diameter_m: float) -> list:
    """(x, y) of each engine axis on its pitch circle (one engine sits on the centreline)."""
    if n <= 1:
        return [(0.0, 0.0)]
    rc = prop.engine_ring_radius(n, exit_diameter_m)
    return [(rc * math.cos(2 * math.pi * k / n + math.pi / n),
             rc * math.sin(2 * math.pi * k / n + math.pi / n)) for k in range(n)]


def booster_positions(n: int, radius_m: float) -> list:
    """(x, y) of each strap-on axis, spread evenly around the core."""
    if n <= 0:
        return []
    if n == 1:
        return [(radius_m, 0.0)]
    return [(radius_m * math.cos(2 * math.pi * k / n), radius_m * math.sin(2 * math.pi * k / n))
            for k in range(n)]


# --------------------------------------------------------------------------------------- mesh
@dataclass
class Mesh:
    name: str = "solid"
    vertices: list = field(default_factory=list)      # (x, y, z)
    faces: list = field(default_factory=list)         # (i, j, k) into vertices, outward CCW

    def triangles(self):
        for i, j, k in self.faces:
            yield self.vertices[i], self.vertices[j], self.vertices[k]

    def __len__(self) -> int:
        return len(self.faces)


def revolve(profile: list, facets: int = DEFAULT_FACETS, offset=(0.0, 0.0), name: str = "solid") -> Mesh:
    """Revolve a (z, r) profile about the z axis into a closed, outward-wound triangle mesh.

    A profile point with r = 0 becomes a single apex vertex (no degenerate sliver triangles);
    an open end with r > 0 is closed with a flat cap, so the result is always watertight.
    """
    if facets < 3:
        raise ValueError(f"facets must be >= 3, got {facets}")
    clean: list = []
    for z, r in profile:
        if r < -EPS:
            raise ValueError(f"negative radius {r} at z = {z}")
        _append(clean, z, max(r, 0.0))
    if len(clean) < 2:
        return Mesh(name=name)
    ox, oy = offset
    m = Mesh(name=name)
    cos = [math.cos(2 * math.pi * k / facets) for k in range(facets)]
    sin = [math.sin(2 * math.pi * k / facets) for k in range(facets)]

    rings: list = []                      # per profile point: list of vertex indices (1 if apex)
    for z, r in clean:
        if r <= EPS:
            rings.append([len(m.vertices)])
            m.vertices.append((ox, oy, z))
        else:
            base = len(m.vertices)
            rings.append([base + k for k in range(facets)])
            m.vertices.extend((ox + r * cos[k], oy + r * sin[k], z) for k in range(facets))

    for lo, hi in zip(rings, rings[1:]):
        if len(lo) == 1 and len(hi) == 1:
            continue                      # two apexes in a row: zero-radius gap, nothing to draw
        for k in range(facets):
            k1 = (k + 1) % facets
            if len(lo) == 1:                                  # apex below, ring above
                m.faces.append((lo[0], hi[k1], hi[k]))
            elif len(hi) == 1:                                # ring below, apex above
                m.faces.append((lo[k], lo[k1], hi[0]))
            else:
                a, b, c, d = lo[k], lo[k1], hi[k1], hi[k]
                m.faces.extend([(a, b, c), (a, c, d)])

    # flat caps on open ends (normal -z at the bottom, +z at the top)
    if len(rings[0]) > 1:
        c0 = len(m.vertices)
        m.vertices.append((ox, oy, clean[0][0]))
        ring = rings[0]
        m.faces.extend((c0, ring[(k + 1) % facets], ring[k]) for k in range(facets))
    if len(rings[-1]) > 1:
        c1 = len(m.vertices)
        m.vertices.append((ox, oy, clean[-1][0]))
        ring = rings[-1]
        m.faces.extend((c1, ring[k], ring[(k + 1) % facets]) for k in range(facets))
    return m


def mesh_volume_m3(mesh: Mesh) -> float:
    """Enclosed volume by the divergence theorem: V = 1/6 sum v0 . (v1 x v2).

    Positive only when the winding is consistently outward, so this doubles as an orientation
    check. For a closed solid of revolution the answer is the volume of the FACETED solid, which
    is smaller than the true body of revolution by the usual polygon-inscription deficit.
    """
    total = 0.0
    for (ax, ay, az), (bx, by, bz), (cx, cy, cz) in mesh.triangles():
        total += (ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx))
    return total / 6.0


def mesh_area_m2(mesh: Mesh) -> float:
    total = 0.0
    for (ax, ay, az), (bx, by, bz), (cx, cy, cz) in mesh.triangles():
        ux, uy, uz = bx - ax, by - ay, bz - az
        vx, vy, vz = cx - ax, cy - ay, cz - az
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        total += 0.5 * math.sqrt(nx * nx + ny * ny + nz * nz)
    return total


def non_manifold_edges(mesh: Mesh) -> list:
    """Edges not shared by exactly two oppositely-wound triangles (empty list = watertight)."""
    seen: dict = {}
    for i, j, k in mesh.faces:
        for a, b in ((i, j), (j, k), (k, i)):
            seen[(a, b)] = seen.get((a, b), 0) + 1
    # Walk the UNDIRECTED edges. Keying off the directed ones that happen to ascend would miss a
    # hole whose one surviving half-edge runs the other way, which is exactly the case to catch.
    bad = set()
    for a, b in seen:
        lo, hi = (a, b) if a < b else (b, a)
        if seen.get((lo, hi), 0) != 1 or seen.get((hi, lo), 0) != 1:
            bad.add((lo, hi))
    return sorted(bad)


def is_watertight(mesh: Mesh) -> bool:
    return not non_manifold_edges(mesh)


def faceted_revolution_volume_m3(profile: list, facets: int) -> float:
    """Closed-form volume of the FACETED solid of revolution, for checking revolve().

    Each profile step is a frustum of a regular `facets`-gon. A polygonal frustum of inscribed
    radii r0, r1 and height h has volume (facets/6) sin(2 pi / facets) h (r0^2 + r0 r1 + r1^2),
    the prismatoid rule applied to the polygon area A(r) = (facets/2) r^2 sin(2 pi / facets).
    """
    clean: list = []
    for z, r in profile:
        _append(clean, z, max(r, 0.0))
    k = facets / 6.0 * math.sin(2 * math.pi / facets)
    return sum(k * abs(z1 - z0) * (r0 * r0 + r0 * r1 + r1 * r1)
               for (z0, r0), (z1, r1) in zip(clean, clean[1:]))


def exact_revolution_volume_m3(profile: list) -> float:
    """Closed-form volume of the TRUE body of revolution of a piecewise-linear (z, r) profile.

    Each step is a right circular frustum, V = (pi/3) h (r0^2 + r0 r1 + r1^2). This is the
    reference a geometry kernel has to reproduce: cad_kernel.verify_solids() compares what
    OpenCASCADE reports for each solid against this number, which is why the function lives here
    in the dependency-free module rather than beside the kernel that it audits.
    """
    clean: list = []
    for z, r in profile:
        _append(clean, z, max(r, 0.0))
    return sum(math.pi / 3.0 * abs(z1 - z0) * (r0 * r0 + r0 * r1 + r1 * r1)
               for (z0, r0), (z1, r1) in zip(clean, clean[1:]))


def faceted_volume_ratio(facets: int) -> float:
    """faceted_revolution_volume_m3 / exact_revolution_volume_m3, which is profile-independent.

    The ratio is n sin(2 pi / n) / (2 pi) - the inscribed-polygon area deficit, identical for
    every frustum in the profile and so for the whole body. At the default 64 facets a mesh
    export understates the enclosed volume by 0.161%; that is the price of a faceted format and
    the reason the kernel route exists.
    """
    if facets < 3:
        raise ValueError(f"facets must be >= 3, got {facets}")
    return facets * math.sin(2 * math.pi / facets) / (2 * math.pi)


# ------------------------------------------------------------------------------ mesh assembly
def vehicle_meshes(res, facets: int = DEFAULT_FACETS, engines: bool = True,
                   boosters: bool = True) -> list:
    """Every closed mesh making up the vehicle: airframe, each nozzle, each strap-on.

    The pieces are kept separate (each individually watertight) rather than booleaned together:
    a union needs a CAD kernel, and the parts overlap where nozzles sit inside the aft skirt.
    """
    geom = res.geometry
    out = [revolve(core_profile(geom), facets, name="core_airframe")]
    if engines:
        for sr in res.stages:
            env = sr.envelope
            if env is None:
                continue
            z_exit = geom.engine_exit_z[sr.index]
            prof = nozzle_profile(z_exit, env.length_m, env.exit_diameter_m)
            for n, (x, y) in enumerate(engine_positions(env.n, env.exit_diameter_m), start=1):
                out.append(revolve(prof, facets, offset=(x, y), name=f"stage{sr.index}_nozzle{n}"))
    if boosters and geom.booster_segments and res.spec.boosters is not None:
        b = res.spec.boosters
        bp = booster_profile(geom)
        noz = nozzle_profile(b.base_z_offset_m, b.nozzle_length_m, b.exit_diameter_m)
        for n, (x, y) in enumerate(booster_positions(b.n_total, geom.booster_x_m), start=1):
            out.append(revolve(bp, facets, offset=(x, y), name=f"booster{n}"))
            out.append(revolve(noz, facets, offset=(x, y), name=f"booster{n}_nozzle"))
    return out


# ----------------------------------------------------------------------------- STL  /  OBJ
def _facet_normal(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    n = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (0.0, 0.0, 0.0) if n < EPS else (nx / n, ny / n, nz / n)


def write_stl(meshes, path, binary: bool = True, name: str = "launch_vehicle") -> str:
    """Write all meshes to one STL file. STL has no part structure, so they share one solid."""
    meshes = [meshes] if isinstance(meshes, Mesh) else list(meshes)
    tris = [t for m in meshes for t in m.triangles()]
    if binary:
        buf = bytearray()
        buf += name.encode("ascii", "replace")[:80].ljust(80, b"\0")
        buf += struct.pack("<I", len(tris))
        for a, b, c in tris:
            buf += struct.pack("<12fH", *_facet_normal(a, b, c), *a, *b, *c, 0)
        with open(path, "wb") as fh:
            fh.write(buf)
    else:
        lines = [f"solid {name}"]
        for a, b, c in tris:
            nx, ny, nz = _facet_normal(a, b, c)
            lines.append(f"  facet normal {nx:.6e} {ny:.6e} {nz:.6e}")
            lines.append("    outer loop")
            lines.extend(f"      vertex {v[0]:.6e} {v[1]:.6e} {v[2]:.6e}" for v in (a, b, c))
            lines.append("    endloop")
            lines.append("  endfacet")
        lines.append(f"endsolid {name}")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
    return str(path)


def write_obj(meshes, path, name: str = "launch_vehicle") -> str:
    """Wavefront OBJ, one group per mesh (OBJ keeps the part names that STL cannot)."""
    meshes = [meshes] if isinstance(meshes, Mesh) else list(meshes)
    lines = [f"# {name} - outer mould line, metres, +z along the vehicle axis (nose up)",
             "# generated by launch_vehicle.cad_export"]
    base = 1                                           # OBJ vertex indices are 1-based
    for m in meshes:
        lines.append(f"g {m.name}")
        lines.extend(f"v {x:.6f} {y:.6f} {z:.6f}" for x, y, z in m.vertices)
        lines.extend(f"f {i + base} {j + base} {k + base}" for i, j, k in m.faces)
        base += len(m.vertices)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    return str(path)


# --------------------------------------------------------------------------------------- 3MF
# Strings fixed by the specifications, not chosen here:
#   3MF Core Specification (3MF Consortium), Appendix C - content type, StartPart relationship
#   and core namespace. Section 3.4 - the six permitted unit values, default millimeter.
#   Section 4.1 - mesh is vertices then triangles, zero-based indices, counter-clockwise
#   (outward-normal) winding, and a consumer must not emit an object no <item> references.
# The two OPC strings come from ECMA-376 Part 2 (Open Packaging Conventions) and were confirmed
# against the content-types stream of a package this project itself writes (the openpyxl
# workbook), rather than quoted from memory.
MODEL_CONTENT_TYPE = "application/vnd.ms-package.3dmanufacturing-3dmodel+xml"
RELS_CONTENT_TYPE = "application/vnd.openxmlformats-package.relationships+xml"
OPC_RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OPC_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
THREEMF_START_PART = "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"
THREEMF_CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
MODEL_PART = "3D/3dmodel.model"

# multiply a length in metres by this to express it in the named 3MF unit
THREEMF_UNITS = {"micron": 1e6, "millimeter": 1e3, "centimeter": 1e2,
                 "inch": 1.0 / 0.0254, "foot": 1.0 / 0.3048, "meter": 1.0}


def _xml_escape(text) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _num(v: float) -> str:
    """Shortest round-trip-safe decimal: XML attributes, so no exponent sloppiness."""
    s = f"{v:.9g}"
    return "0" if s in ("-0", "-0.0") else s


def write_3mf(meshes, path, unit: str = "meter", name: str = "launch_vehicle") -> str:
    """Write all meshes to one 3MF archive, one named <object> per part.

    3MF is preferred over STL for the same mesh because it carries two things STL cannot: the
    UNIT its coordinates are in, and the part names. The default is `meter`, which means the
    numbers are written exactly as the tool holds them with no conversion step to get wrong; a
    consumer that honours the attribute - which is the whole point of the format - scales them
    itself. Pass unit="millimeter" for a consumer that does not.

    The mesh winding this module produces is already outward counter-clockwise with zero-based
    indices, which is what the specification requires, so nothing is reordered on the way out.

    Coordinates are written to 9 significant figures: a tenth of a micron on a 70 m vehicle, and
    finer than the float32 that binary STL can hold at all.
    """
    import datetime
    import zipfile

    if unit not in THREEMF_UNITS:
        raise ValueError(f"unknown 3MF unit {unit!r}; the specification permits "
                         f"{sorted(THREEMF_UNITS)}")
    meshes = [meshes] if isinstance(meshes, Mesh) else list(meshes)
    scale = THREEMF_UNITS[unit]

    objects, items = [], []
    for n, m in enumerate(meshes, start=1):
        if len(m.vertices) < 3 or len(m.faces) < 4:
            continue                      # spec 4.1: a solid model object needs a closed mesh
        oid = len(objects) + 1
        verts = "".join(f'<vertex x="{_num(x * scale)}" y="{_num(y * scale)}" '
                        f'z="{_num(z * scale)}"/>' for x, y, z in m.vertices)
        tris = "".join(f'<triangle v1="{i}" v2="{j}" v3="{k}"/>' for i, j, k in m.faces)
        objects.append(f'<object id="{oid}" type="model" name="{_xml_escape(m.name)}">'
                       f"<mesh><vertices>{verts}</vertices>"
                       f"<triangles>{tris}</triangles></mesh></object>")
        items.append(f'<item objectid="{oid}"/>')
    if not objects:
        raise ValueError("nothing to write: no mesh had a closed triangle set")

    stamp = datetime.date.today().isoformat()
    model = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<model unit="{unit}" xml:lang="en-US" xmlns="{THREEMF_CORE_NS}">'
        f'<metadata name="Title">{_xml_escape(name)}</metadata>'
        '<metadata name="Application">launch_vehicle.cad_export</metadata>'
        f'<metadata name="CreationDate">{stamp}</metadata>'
        '<metadata name="Description">Outer mould line, +z along the vehicle axis (nose up), '
        'origin on the centreline at the first-stage nozzle exit plane.</metadata>'
        f"<resources>{''.join(objects)}</resources>"
        f"<build>{''.join(items)}</build></model>")
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<Types xmlns="{OPC_TYPES_NS}">'
        f'<Default Extension="rels" ContentType="{RELS_CONTENT_TYPE}"/>'
        f'<Default Extension="model" ContentType="{MODEL_CONTENT_TYPE}"/></Types>')
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<Relationships xmlns="{OPC_RELS_NS}">'
        f'<Relationship Id="rel0" Target="/{MODEL_PART}" Type="{THREEMF_START_PART}"/>'
        "</Relationships>")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        # content types first: OPC readers are entitled to expect it before the parts it types
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr(MODEL_PART, model)
    return str(path)


# ----------------------------------------------------------------------------------- DXF R12
class _Dxf:
    """Group-code pair accumulator for DXF R12 ASCII."""

    def __init__(self):
        self.out: list = []

    def p(self, code, value) -> None:
        self.out.append(str(code))
        self.out.append(f"{value:.6f}" if isinstance(value, float) else str(value))

    def line(self, layer, x1, y1, x2, y2) -> None:
        self.p(0, "LINE"), self.p(8, layer)
        self.p(10, float(x1)), self.p(20, float(y1)), self.p(30, 0.0)
        self.p(11, float(x2)), self.p(21, float(y2)), self.p(31, 0.0)

    def polyline(self, layer, pts, closed=False) -> None:
        if len(pts) < 2:
            return
        self.p(0, "POLYLINE"), self.p(8, layer), self.p(66, 1), self.p(70, 1 if closed else 0)
        self.p(10, 0.0), self.p(20, 0.0), self.p(30, 0.0)
        for x, y in pts:
            self.p(0, "VERTEX"), self.p(8, layer)
            self.p(10, float(x)), self.p(20, float(y)), self.p(30, 0.0)
        self.p(0, "SEQEND"), self.p(8, layer)

    def text(self, layer, x, y, height, s, align_right=False) -> None:
        self.p(0, "TEXT"), self.p(8, layer)
        self.p(10, float(x)), self.p(20, float(y)), self.p(30, 0.0)
        self.p(40, float(height)), self.p(1, str(s).replace("\n", " "))
        if align_right:
            self.p(72, 2)                                 # horizontal justification: right
            self.p(11, float(x)), self.p(21, float(y)), self.p(31, 0.0)

    def render(self, extmin, extmax) -> str:
        head = _Dxf()
        head.p(0, "SECTION"), head.p(2, "HEADER")
        head.p(9, "$ACADVER"), head.p(1, "AC1009")
        head.p(9, "$INSUNITS"), head.p(70, 6)             # 6 = metres
        head.p(9, "$EXTMIN"), head.p(10, extmin[0]), head.p(20, extmin[1]), head.p(30, 0.0)
        head.p(9, "$EXTMAX"), head.p(10, extmax[0]), head.p(20, extmax[1]), head.p(30, 0.0)
        head.p(0, "ENDSEC")

        tab = _Dxf()
        tab.p(0, "SECTION"), tab.p(2, "TABLES")
        tab.p(0, "TABLE"), tab.p(2, "LTYPE"), tab.p(70, 2)
        tab.p(0, "LTYPE"), tab.p(2, "CONTINUOUS"), tab.p(70, 0), tab.p(3, "Solid line")
        tab.p(72, 65), tab.p(73, 0), tab.p(40, 0.0)
        tab.p(0, "LTYPE"), tab.p(2, "CENTER"), tab.p(70, 0), tab.p(3, "Centre ____ _ ____ _ ____")
        tab.p(72, 65), tab.p(73, 4), tab.p(40, 2.0)
        for dash in (1.25, -0.25, 0.25, -0.25):
            tab.p(49, dash)
        tab.p(0, "ENDTAB")
        tab.p(0, "TABLE"), tab.p(2, "LAYER"), tab.p(70, len(DXF_LAYERS))
        for nm, colour, lt in DXF_LAYERS:
            tab.p(0, "LAYER"), tab.p(2, nm), tab.p(70, 0), tab.p(62, colour), tab.p(6, lt)
        tab.p(0, "ENDTAB"), tab.p(0, "ENDSEC")

        ent = ["0", "SECTION", "2", "ENTITIES"] + self.out + ["0", "ENDSEC", "0", "EOF"]
        return "\n".join(head.out + tab.out + ent) + "\n"


def _dome_arc(x0: float, z_apex: float, R: float, h: float, upward: bool) -> list:
    """Polygonised half-ellipse dome (R12 has no ELLIPSE entity), apex-centred at (x0, z_apex)."""
    pts = []
    for k in range(DOME_FACETS + 1):
        th = math.pi * k / DOME_FACETS
        pts.append((x0 - R * math.cos(th), z_apex + (h if upward else -h) * math.sin(th)))
    return pts


def _dxf_tank(d: _Dxf, seg, x0: float) -> None:
    g = seg.tank
    R, hd = g.R_int + g.t_wall, g.h_dome + g.t_wall
    has_bot = g.bulkhead != "upper_user"
    has_top = g.bulkhead != "lower_owner"
    zb = seg.z0 + (hd if has_bot else 0.0)
    zt = seg.z1 - (hd if has_top else 0.0)
    for xs in (x0 - R, x0 + R):
        d.line("LV_TANK", xs, zb, xs, zt)
    if has_bot:
        d.polyline("LV_TANK", _dome_arc(x0, zb, R, hd, upward=False))
    if has_top:
        d.polyline("LV_TANK", _dome_arc(x0, zt, R, hd, upward=True))
    if g.bulkhead == "lower_owner":
        d.polyline("LV_TANK", _dome_arc(x0, seg.z1, R, g.h_dome, upward=True))
    if getattr(g, "R_bore", 0.0) > 0:                 # cast solid grain with a central bore
        z0 = seg.z0 + g.t_wall
        zc0, zc1 = ((z0, z0 + g.L_int) if g.bore_full_length
                    else (z0 + g.h_dome, z0 + g.h_dome + g.h_cyl))
        for sgn in (-1, 1):
            d.polyline("LV_GRAIN", [(x0 + sgn * g.R_bore, zc0), (x0 + sgn * g.R_int, zc0),
                                    (x0 + sgn * g.R_int, zc1), (x0 + sgn * g.R_bore, zc1)],
                       closed=True)


def _dxf_nozzles(d: _Dxf, res, layer="LV_ENGINE") -> None:
    for sr in res.stages:
        env = sr.envelope
        if env is None:
            continue
        prof = nozzle_profile(res.geometry.engine_exit_z[sr.index], env.length_m, env.exit_diameter_m)
        for x, _y in engine_positions(env.n, env.exit_diameter_m):
            pts = [(x + r, z) for z, r in prof] + [(x - r, z) for z, r in reversed(prof)]
            d.polyline(layer, pts, closed=True)


def write_dxf(res, path, labels: bool = True) -> str:
    """Layered DXF R12 of the inboard profile. Returns the path written."""
    geom, spec = res.geometry, res.spec
    L, Dmax = geom.total_length, geom.max_diameter
    h = max(L / 110.0, 1e-3)                           # text height
    d = _Dxf()

    d.line("LV_AXIS", 0.0, -0.03 * L, 0.0, 1.03 * L)

    prof = core_profile(geom)
    silhouette = [(r, z) for z, r in prof] + [(-r, z) for z, r in reversed(prof)]
    d.polyline("LV_OML", silhouette, closed=True)

    for s in geom.segments:
        d.line("LV_STATION", -0.5 * s.d_bot, s.z0, 0.5 * s.d_bot, s.z0)
        if s.kind == "tank" and s.tank is not None:
            _dxf_tank(d, s, 0.0)
        if labels:
            d.text("LV_TEXT", 0.52 * max(s.d_bot, s.d_top), s.z_mid - 0.4 * h, h, s.name)
    top = geom.segments[-1]
    d.line("LV_STATION", -0.5 * top.d_top, top.z1, 0.5 * top.d_top, top.z1)

    _dxf_nozzles(d, res)

    Dt = spec.stages[-1].diameter_m
    d.polyline("LV_PAYLOAD", [(-0.35 * Dt, geom.paf_z0), (0.35 * Dt, geom.paf_z0),
                              (0.35 * Dt, geom.paf_z1), (-0.35 * Dt, geom.paf_z1)], closed=True)
    ew = spec.fairing.envelope_diameter_m
    d.polyline("LV_PAYLOAD", [(-0.5 * ew, geom.payload_z0), (0.5 * ew, geom.payload_z0),
                              (0.5 * ew, geom.payload_z1), (-0.5 * ew, geom.payload_z1)], closed=True)
    if labels:
        d.text("LV_PAYLOAD", 0.0, geom.payload_z1 + 0.5 * h, h,
               f"payload envelope {ew:.2f} m x {geom.payload_z1 - geom.payload_z0:.2f} m")

    span = geom.max_span_m
    if geom.booster_segments and spec.boosters is not None:
        b = spec.boosters
        bprof = booster_profile(geom)
        noz = nozzle_profile(b.base_z_offset_m, b.nozzle_length_m, b.exit_diameter_m)
        for sgn in (-1, 1):                            # profile view shows the two in-plane units
            x0 = sgn * geom.booster_x_m
            pts = [(x0 + r, z) for z, r in bprof] + [(x0 - r, z) for z, r in reversed(bprof)]
            d.polyline("LV_BOOSTER", pts, closed=True)
            pts = [(x0 + r, z) for z, r in noz] + [(x0 - r, z) for z, r in reversed(noz)]
            d.polyline("LV_BOOSTER", pts, closed=True)
        if labels:
            d.text("LV_BOOSTER", 0.0, -2.6 * h, h,
                   f"{b.n_total} x {b.name} shown at +/-{geom.booster_x_m:.2f} m "
                   f"(2 of {b.n_total} in this view plane)")

    xd = 0.5 * span + 6 * h
    d.line("LV_DIM", xd, 0.0, xd, L)
    d.text("LV_DIM", xd + 0.5 * h, 0.5 * L, h, f"overall length {L:.3f} m")
    d.line("LV_DIM", -0.5 * Dmax, -1.2 * h, 0.5 * Dmax, -1.2 * h)
    d.text("LV_DIM", 0.0, -2.4 * h if not geom.booster_segments else -4.0 * h, h,
           f"max body diameter {Dmax:.3f} m, max span {span:.3f} m")
    if labels:
        d.text("LV_TEXT", -0.5 * span, L + 3 * h, 1.4 * h, f"{spec.name} - inboard profile")
        d.text("LV_TEXT", -0.5 * span, L + 1.2 * h, 0.85 * h,
               "Preliminary conceptual layout, metres, z from the stage-1 nozzle exit plane. "
               "Not a manufacturing drawing.")

    pad = 10 * h
    xs = [0.5 * span + pad, -0.5 * span - pad, xd + pad]
    extmin = (min(xs), -6 * h)
    extmax = (max(xs), L + 6 * h)
    text = d.render(extmin, extmax)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return str(path)


# ----------------------------------------------------------------------------------- bundle
def export_all(res, out_dir, facets: int = DEFAULT_FACETS, stem: str = "vehicle",
               binary_stl: bool = True, kernel: bool = True, unit_3mf: str = "meter") -> dict:
    """Write every CAD file this tool can; return {format: path} actually written.

    The four dependency-free formats are always written. The exact-solid formats are added only
    when the optional geometry kernel is installed, and a kernel failure is reported through the
    "kernel_error" key rather than being allowed to lose the meshes that did write.
    """
    import os
    os.makedirs(out_dir, exist_ok=True)
    meshes = vehicle_meshes(res, facets)
    paths = {
        "dxf": write_dxf(res, os.path.join(out_dir, f"{stem}_profile.dxf")),
        "stl": write_stl(meshes, os.path.join(out_dir, f"{stem}.stl"), binary=binary_stl,
                         name=res.spec.name[:60]),
        "obj": write_obj(meshes, os.path.join(out_dir, f"{stem}.obj"), name=res.spec.name),
        "3mf": write_3mf(meshes, os.path.join(out_dir, f"{stem}.3mf"), unit=unit_3mf,
                         name=res.spec.name),
    }
    if kernel:
        from . import cad_kernel
        if cad_kernel.available():
            try:
                paths.update(cad_kernel.export_solids(res, out_dir, stem=stem))
            except Exception as e:                       # noqa: BLE001
                paths["kernel_error"] = f"{type(e).__name__}: {e}"
    return paths


def mesh_summary(meshes) -> dict:
    """Counts and closure status, for the report and for the CLI to print honestly."""
    meshes = [meshes] if isinstance(meshes, Mesh) else list(meshes)
    return {
        "parts": len(meshes),
        "triangles": sum(len(m) for m in meshes),
        "vertices": sum(len(m.vertices) for m in meshes),
        "watertight_parts": sum(1 for m in meshes if is_watertight(m)),
        "airframe_volume_m3": mesh_volume_m3(meshes[0]) if meshes else 0.0,
        "airframe_area_m2": mesh_area_m2(meshes[0]) if meshes else 0.0,
    }
