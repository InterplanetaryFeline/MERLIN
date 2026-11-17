"""Stage layout and vehicle geometry (single source of truth for the drawing, mass ledger and spreadsheet).

Axial coordinate z: metres, measured UPWARD from the nozzle exit plane of the first-stage engines (z = 0).
Stage base (mounting plane) of stage 1 therefore sits at z = engine protrusion of stage 1.
Thin-shell surface areas follow book Table 8.10 (p. 497): cylinder 2 pi R h, cone pi R sqrt(R^2+h^2),
frustum pi (r+R) sqrt((R-r)^2 + h^2).
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from .tank_sizing import InfeasibleGeometry


@dataclass
class Segment:
    kind: str              # aft_skirt | tank | intertank | fwd_skirt | interstage | paf | fairing_cyl | fairing_nose
    name: str
    length: float
    d_bot: float
    d_top: float
    stage: int
    tank: object = None
    z0: float = 0.0
    z1: float = 0.0

    @property
    def z_mid(self) -> float:
        return 0.5 * (self.z0 + self.z1)


def cylinder_area(D: float, L: float) -> float:
    return math.pi * D * L


def cone_area(R: float, h: float) -> float:
    return math.pi * R * math.sqrt(R * R + h * h)


def frustum_area(Rb: float, Rt: float, L: float) -> float:
    return math.pi * (Rb + Rt) * math.sqrt((Rb - Rt) ** 2 + L * L)


def segment_area(seg: Segment) -> float:
    if seg.kind == "fairing_nose":
        return cone_area(seg.d_bot / 2, seg.length)
    return frustum_area(seg.d_bot / 2, seg.d_top / 2, seg.length)


def engine_protrusion(stage, env=None) -> float:
    """Axial length by which the engine/nozzle sticks out below the stage's mounting plane."""
    if env is not None:
        return env.protrusion_m
    e = stage.engine
    return e.length_m * (1.0 - e.embed_fraction)


def build_layout(stage, tanks: list, next_stage=None, env=None, next_env=None, fairing_diameter_m=None) -> list:
    """Local (stage) segment list, bottom -> top. Lengths only; z filled in by assemble().

    A solid stage carries a single motor casing instead of tanks and has no intertank (book p.486).
    """
    D = stage.diameter_m
    segs = []
    emb = (env.length_m * env.embed_fraction) if env is not None else stage.engine.length_m * stage.engine.embed_fraction
    segs.append(Segment("aft_skirt", f"Aft skirt / engine section {stage.index}", max(stage.aft_skirt_over_D * D, emb),
                        D, D, stage.index))
    if stage.is_solid:
        g = tanks[0]
        segs.append(Segment("tank", f"Motor casing {stage.index}", g.L_ext, g.D_ext, g.D_ext, stage.index, tank=g))
    else:
        for k, t in enumerate(tanks):
            if k == 1 and stage.tank.arrangement == "separate":
                segs.append(Segment("intertank", f"Intertank {stage.index}", stage.intertank_over_D * D, D, D, stage.index))
            segs.append(Segment("tank", f"{t.role.capitalize()} tank {stage.index}", t.L_ext, t.D_ext, t.D_ext, stage.index, tank=t))
    segs.append(Segment("fwd_skirt", f"Forward skirt {stage.index}", stage.fwd_skirt_over_D * D, D, D, stage.index))
    if next_stage is not None:
        Dn = next_stage.diameter_m
        taper = abs(D - Dn) / 2.0 / math.tan(math.radians(stage.interstage_half_angle_deg)) if abs(D - Dn) > 1e-12 else 0.0
        L = max(stage.interstage_min_length_m, engine_protrusion(next_stage, next_env) + stage.interstage_clearance_m, taper)
        segs.append(Segment("interstage", f"Interstage {stage.index}-{stage.index+1}", L, D, Dn, stage.index))
    elif fairing_diameter_m is not None and fairing_diameter_m > D + 1e-12:
        # upper step narrower than the payload fairing (book Fig. 8.15, p.490): conical transition skirt
        taper = (fairing_diameter_m - D) / 2.0 / math.tan(math.radians(stage.interstage_half_angle_deg))
        segs.append(Segment("fwd_adapter", f"Forward adapter cone {stage.index}-fairing", taper, D, fairing_diameter_m,
                            stage.index))
    return segs


def booster_segments(spec, case, env_exit_d: float, nozzle_len: float) -> list:
    """Local segments of ONE strap-on booster, bottom -> top: nozzle gap, casing, nose cone.

    z is measured from the booster's own nozzle exit plane; assemble() shifts them by base_z_offset_m.
    """
    b = spec.boosters
    D = case.D_ext
    L_nose = b.nose_length_over_D * D
    return [Segment("booster_case", f"{b.name} casing", case.L_ext, D, D, 0, tank=case, z0=nozzle_len, z1=nozzle_len + case.L_ext),
            Segment("booster_nose", f"{b.name} nose cone", L_nose, D, 0.0, 0,
                    z0=nozzle_len + case.L_ext, z1=nozzle_len + case.L_ext + L_nose)]


def fairing_segments(spec, paf_length: float) -> list:
    f = spec.fairing
    L_cyl = paf_length + f.envelope_length_m + f.axial_clearance_m
    L_nose = f.nose_length_over_D * f.diameter_m
    n = len(spec.stages)
    return [Segment("fairing_cyl", "Fairing cylinder", L_cyl, f.diameter_m, f.diameter_m, 0),
            Segment("fairing_nose", "Fairing nose cone", L_nose, f.diameter_m, 0.0, 0)]


@dataclass
class VehicleGeometry:
    segments: list = field(default_factory=list)       # all segments with global z
    stage_base_z: dict = field(default_factory=dict)
    stage_top_z: dict = field(default_factory=dict)
    engine_exit_z: dict = field(default_factory=dict)
    paf_z0: float = 0.0
    paf_z1: float = 0.0
    payload_z0: float = 0.0
    payload_z1: float = 0.0
    total_length: float = 0.0
    fairing_base_z: float = 0.0
    max_diameter: float = 0.0
    booster_segments: list = field(default_factory=list)   # segments of ONE booster, in vehicle z
    booster_x_m: float = 0.0                               # lateral offset of the booster axis
    max_span_m: float = 0.0                                # widest lateral extent incl. boosters

    def stage_segments(self, idx: int) -> list:
        return [s for s in self.segments if s.stage == idx]


def assemble(spec, stage_layouts: dict, paf_length: float, envs: dict | None = None,
             booster_case=None) -> VehicleGeometry:
    """Stack the stage layouts bottom-up, then PAF, payload envelope and fairing; fill global z."""
    envs = envs or {}
    g = VehicleGeometry()
    z = engine_protrusion(spec.stages[0], envs.get(1))
    g.engine_exit_z[1] = 0.0
    for st in spec.stages:
        g.stage_base_z[st.index] = z
        if st.index > 1:
            g.engine_exit_z[st.index] = z - engine_protrusion(st, envs.get(st.index))
        for seg in stage_layouts[st.index]:
            seg.z0, seg.z1 = z, z + seg.length
            z = seg.z1
            g.segments.append(seg)
        g.stage_top_z[st.index] = z
    g.fairing_base_z = z
    g.paf_z0, g.paf_z1 = z, z + paf_length
    g.payload_z0 = g.paf_z1
    g.payload_z1 = g.payload_z0 + spec.fairing.envelope_length_m
    for seg in fairing_segments(spec, paf_length):
        seg.z0, seg.z1 = z, z + seg.length
        z = seg.z1
        g.segments.append(seg)
    g.total_length = z
    g.max_diameter = max(s.d_bot for s in g.segments)
    g.max_span_m = g.max_diameter
    if booster_case is not None and spec.boosters:
        b = spec.boosters
        segs = booster_segments(spec, booster_case, b.exit_diameter_m, b.nozzle_length_m)
        for s in segs:
            s.z0 += b.base_z_offset_m
            s.z1 += b.base_z_offset_m
        g.booster_segments = segs
        g.booster_x_m = 0.5 * spec.stages[b.attach_stage - 1].diameter_m + b.radial_gap_m + 0.5 * booster_case.D_ext
        g.max_span_m = max(g.max_diameter, 2 * (g.booster_x_m + 0.5 * booster_case.D_ext))
        g.total_length = max(g.total_length, max(s.z1 for s in segs))
    return g


def check_fairing_fit(spec) -> None:
    f = spec.fairing
    if f.envelope_diameter_m + 2 * f.radial_clearance_m > f.diameter_m + 1e-12:
        raise InfeasibleGeometry(
            f"payload envelope {f.envelope_diameter_m} m + 2x{f.radial_clearance_m} m clearance does not fit the "
            f"{f.diameter_m} m fairing")
