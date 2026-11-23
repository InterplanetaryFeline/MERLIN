"""Export a sized MERLIN vehicle to Kerbal Space Program 1.12.5 with Real Solar System.

WHAT THIS IS. Not a 3D model export: an engineering export. Each vehicle gets its OWN KSP parts, generated from
the sized design, so that the numbers KSP flies with are MERLIN's and not those of a stock part that happens to
look similar:

* every geometry segment (aft skirt, tanks, intertank, forward skirt, interstage) is one part, at MERLIN's
  station and diameter, carrying the dry mass of the ledger items that sit in it, with its centre of mass
  placed where those items put it (`CoMOffset`);
* every tank holds MERLIN's usable propellant (mission + start-up) as a propellant of its own, defined at
  MERLIN's density; residual and loading-margin propellant, which MERLIN keeps on board to burnout, is dry mass;
* every engine is one part with MERLIN's vacuum thrust, its vacuum Isp, and an Isp-versus-pressure curve that is
  exactly the straight line MERLIN's thrust model follows (T = mdot ve - Pa Ae), with explicit tangents so KSP
  does not smooth it; propellant ratios are MERLIN's mixture ratio converted to the volume ratio KSP uses;
* the interstage is the decoupler, the payload adapter is the base of a stock procedural fairing whose panel mass
  per area is set so the panels weigh MERLIN's fairing mass, and the payload is a mass part.

TARGET. KSP 1.12.5 with Real Solar System (so the planet is Earth-sized and MERLIN's delta-v budget applies) and
ModuleManager. Nothing else is required; FAR, if installed, computes drag from the parts' shapes. The parts use
stock meshes, scaled, so no new art is needed and nothing can be missing. See docs/KSP_EXPORT.md.

SOLID STAGES. A solid motor is its casing, holding the grain as a propellant of its own at the grain's density,
and a nozzle part that is the engine: constant mass flow over MERLIN's burn time (MERLIN's neutral-burn model),
no throttle and no shut-down, and the same straight-line Isp-versus-pressure curve as a liquid engine. MERLIN's
casing relation includes the nozzle, insulation and TVC, so the nozzle part carries no mass of its own rather
than an invented share of the casing.

NOT YET SUPPORTED (refused with a reason rather than exported wrong): strap-on boosters.
"""
from __future__ import annotations
import math
import os
import re
import zipfile
from dataclasses import dataclass, field

from .units import G0

#: stock meshes, with the native size of each so it can be scaled to MERLIN's
TANK_MESH = ("Squad/Parts/FuelTank/Size3Tanks/Size3MediumTank", 3.75, 3.868)        # model, diameter, height
ENGINE_MESH = ("Squad/Parts/Engine/liquidEngineMainsail_v2/liquidEngineMainsail_v2", 2.5, 2.478, 0.533)
FAIRING_BASE_MESH = ("Squad/Parts/Aero/fairings/fairingSize3", 3.75)
#: the stock launch clamp: its part name, and its surface-attach point in its own frame (launchClamp1.cfg,
#: node_attach = 0, 1.354437, 0.8069194); the clamp's +z axis points at the part it holds
CLAMP = ("launchClamp1", 1.354437, 0.8069194)
N_CLAMPS = 4
P0_PA = 101325.0                 # KSP's atmosphereCurve is in atmospheres; RSS sea level is 101.325 kPa
KSP_TARGET = "KSP 1.12.5 with Real Solar System and ModuleManager"


class KSPExportError(ValueError):
    pass


@dataclass
class KPart:
    """One generated KSP part and its place in the vehicle."""
    key: str                       # short id unique within the vehicle
    title: str
    kind: str                      # segment | engine | decoupler | fairing_base | payload
    stage: int
    z0: float                      # MERLIN station of the part's bottom and top [m]
    z1: float
    diameter: float
    dry_kg: float = 0.0
    cm_z: float = 0.0              # station of the part's dry centre of mass
    resources: dict = field(default_factory=dict)    # resource name -> units (litres)
    x: float = 0.0                 # lateral offset (engines in a cluster)
    y: float = 0.0
    items: list = field(default_factory=list)       # ledger items carried, for the report
    parent: str | None = None
    parent_node: str = "bottom"    # node of the PARENT this part hangs from
    own_node: str = "top"          # node of THIS part that attaches to the parent
    extra_nodes: dict = field(default_factory=dict)  # node name -> (x, y_local, z, dir_y)
    istg: int = -1
    engine: dict | None = None
    fairing: dict | None = None
    command: bool = False
    stock: str | None = None       # a stock part used as it is (launch clamps), not a generated one
    rot: tuple = (0.0, 0.0, 0.0, 1.0)
    srf: bool = False              # surface-attached to its parent rather than by a stack node

    @property
    def length(self):
        return self.z1 - self.z0

    @property
    def zc(self):
        return 0.5 * (self.z0 + self.z1)


def _tag(name: str) -> str:
    t = re.sub(r"[^A-Za-z0-9]+", "", name)[:24]
    return t or "Vehicle"


def _res_name(tag: str, prop: str) -> str:
    return f"MERLIN_{tag}_{re.sub(r'[^A-Za-z0-9]+', '', prop)}"


# =========================================================================== MERLIN -> parts
def build_parts(res, tag: str) -> tuple[list, dict]:
    """The vehicle as a list of KPart, top part first, and the propellant definitions it needs."""
    spec = res.spec
    if res.boosters is not None:
        raise KSPExportError("strap-on boosters are not exported yet: the KSP export covers stages "
                             "stacked one on another, liquid or solid")
    segs = [s for s in res.geometry.segments if s.stage >= 1]
    fair = [s for s in res.geometry.segments if s.stage == 0]
    ledger = list(res.ledger)
    resources = {}
    parts = []

    # ---- one part per geometry segment
    by_stage = {}
    for s in segs:
        role = (s.tank.role if s.kind == "tank" and s.tank is not None else "")
        p = KPart(key=f"s{s.stage}_{s.kind}" + (f"_{role}" if role else ""), title=s.name, kind="segment",
                  stage=s.stage, z0=s.z0, z1=s.z1,
                  diameter=max(s.d_bot, s.d_top))
        if s.kind == "interstage":
            p.kind = "decoupler"
        by_stage.setdefault(s.stage, []).append((s, p))
        parts.append(p)

    def home(stage, z):
        rows = by_stage.get(stage) or []
        for s, p in rows:
            if s.z0 - 1e-9 <= z < s.z1 - 1e-9:
                return p
        return min(rows, key=lambda sp: min(abs(z - sp[0].z0), abs(z - sp[0].z1)))[1] if rows else None

    # ---- engines: one part each, on MERLIN's cluster ring
    from .cad_export import engine_positions
    engine_parts = {}
    for st in res.stages:
        sp = spec.stages[st.index - 1]
        env = st.envelope
        n = int(env.n)
        aft = next(p for s, p in by_stage[st.index] if s.kind == "aft_skirt")
        z_exit = aft.z0 - env.length_m * (1.0 - env.embed_fraction)
        eng_items = [] if sp.is_solid else \
            [i for i in ledger if i.stage == st.index and i.name in ("Engines", "Engine gimbals")]
        m_each = sum(i.mass_kg for i in eng_items) / n
        cm = (sum(i.mass_kg * i.z_m for i in eng_items) / sum(i.mass_kg for i in eng_items)) if eng_items else z_exit
        eng = _engine_data(res, st, sp, n, tag)
        lst = []
        for k, (x, y) in enumerate(engine_positions(n, env.exit_diameter_m)):
            ename = (sp.motor.name if sp.is_solid else sp.engine.name) or ("Nozzle" if sp.is_solid else "Engine")
            e = KPart(key=f"s{st.index}_engine{k + 1}", title=f"{ename} (stage {st.index}, "
                      f"{k + 1} of {n})", kind="engine", stage=st.index, z0=z_exit, z1=z_exit + env.length_m,
                      diameter=env.exit_diameter_m, dry_kg=m_each, cm_z=cm, x=x, y=y, engine=eng,
                      parent=aft.key, parent_node=f"engine{k + 1}", own_node="top", items=eng_items)
            aft.extra_nodes[f"engine{k + 1}"] = (x, z_exit + env.length_m, y, -1.0)
            lst.append(e)
        engine_parts[st.index] = lst

    # ---- dry ledger items into the segment they sit in
    for i in ledger:
        if i.stage < 1 or i.kind != "dry" or i.name in ("Engines", "Engine gimbals"):
            continue
        p = home(i.stage, i.z_m)
        p.items.append(i)
    # residual + loading margin stays on board to burnout: dry mass of its tank
    for st in res.stages:
        sp = spec.stages[st.index - 1]
        if sp.is_solid:
            seg, casing = next(((s, p) for s, p in by_stage[st.index] if s.kind == "tank" and s.tank is not None
                                and s.tank.role == "grain"), (None, None))
            if casing is None:
                raise KSPExportError(f"stage {st.index} is solid but has no motor casing segment for its grain")
            prop = seg.tank.propellant
            resid = [i for i in ledger if i.stage == st.index and i.kind == "prop_resid"]
            casing.items.extend(resid)
            usable = st.m_prop_loaded_kg - sum(i.mass_kg for i in resid)
            rho = spec.solid_propellants[prop].density_kg_m3
            rn = _res_name(tag, prop)
            resources[rn] = dict(propellant=prop, density_kg_m3=rho, solid=True)
            casing.resources[rn] = casing.resources.get(rn, 0.0) + usable / rho * 1000.0
            continue
        for role, prop in (("fuel", sp.fuel), ("oxidizer", sp.oxidizer)):
            tank = next((p for s, p in by_stage[st.index] if s.kind == "tank" and s.tank is not None
                         and s.tank.role == role), None)
            if tank is None:
                raise KSPExportError(f"stage {st.index} has no {role} tank segment to put its propellant in")
            resid = next((i for i in ledger if i.stage == st.index and i.kind == "prop_resid"
                          and f"({role})" in i.name), None)
            loaded = st.prop_masses[role]
            r_kg = resid.mass_kg if resid is not None else 0.0
            if resid is not None:
                tank.items.append(resid)
            usable = loaded - r_kg
            rho = spec.propellants[prop].density_kg_m3
            rn = _res_name(tag, prop)
            resources[rn] = dict(propellant=prop, density_kg_m3=rho)
            tank.resources[rn] = tank.resources.get(rn, 0.0) + usable / rho * 1000.0      # litres
    for p in parts:
        m = sum(i.mass_kg for i in p.items)
        p.dry_kg = m
        p.cm_z = (sum(i.mass_kg * i.z_m for i in p.items) / m) if m > 0 else p.zc

    # ---- payload adapter = fairing base, payload above it
    top = max((p for p in parts if p.kind in ("segment", "decoupler")), key=lambda p: p.z1)
    paf = next((i for i in ledger if i.group == "Payload" and "adapter" in i.name.lower()), None)
    pay = next((i for i in ledger if i.group == "Payload" and i.name == "Payload"), None)
    fair_items = [i for i in ledger if i.group == "Fairing"]
    base_h = 0.2
    base = KPart(key="fairing_base", title="Payload adapter and fairing base", kind="fairing_base", stage=0,
                 z0=top.z1, z1=top.z1 + base_h, diameter=spec.fairing.diameter_m,
                 dry_kg=paf.mass_kg if paf else 0.0, cm_z=paf.z_m if paf else top.z1 + base_h / 2,
                 items=[paf] if paf else [], parent=top.key, parent_node="top", own_node="bottom")
    if fair:
        z_tip = max(s.z1 for s in fair)
        prof = []
        for s in sorted(fair, key=lambda s: s.z0):
            prof.append((s.z0 - base.z1, s.d_bot / 2))
        prof.append((z_tip - base.z1, max(fair[-1].d_top / 2, 0.05)))
        area = 0.0
        for (h0, r0), (h1, r1) in zip(prof, prof[1:]):
            area += math.pi * (r0 + r1) * math.hypot(h1 - h0, r1 - r0)
        m_f = sum(i.mass_kg for i in fair_items)
        base.fairing = dict(xsections=prof, area_m2=area, mass_kg=m_f, unit_area_mass_t=(m_f / 1000.0) / area)
    env_d = spec.fairing.envelope_diameter_m
    env_l = spec.fairing.envelope_length_m
    payload = KPart(key="payload", title="Payload", kind="payload", stage=0, z0=base.z1, z1=base.z1 + env_l,
                    diameter=env_d, dry_kg=pay.mass_kg if pay else res.payload_mass_kg,
                    cm_z=pay.z_m if pay else base.z1 + env_l / 2, items=[pay] if pay else [],
                    parent=base.key, parent_node="top", own_node="bottom")

    # ---- the tree. KSP keeps control in the part tree that holds the root, so the root is the top stage's
    # forward skirt, which carries the guidance; everything else hangs from it.
    stack = sorted((p for p in parts if p.kind in ("segment", "decoupler")), key=lambda p: -p.z0)
    root = next(p for p in stack if p.stage == len(res.stages) and p.title.lower().startswith("forward skirt"))
    root.command = True
    # above the root: fairing base, payload. Below the root: every segment down to the first stage's aft skirt.
    i0 = stack.index(root)
    for upper, lower in zip(stack[i0:], stack[i0 + 1:]):
        lower.parent, lower.parent_node, lower.own_node = upper.key, "bottom", "top"
    # and anything of the top stage above its forward skirt (a forward adapter cone) hangs upward from it
    for j in range(i0 - 1, -1, -1):
        stack[j].parent, stack[j].parent_node, stack[j].own_node = stack[j + 1].key, "top", "bottom"
    ordered = [root, base, payload] + [p for p in stack if p is not root] + \
        [e for st in sorted(engine_parts) for e in engine_parts[st]]

    # ---- staging. KSP fires the highest stage number first.
    n_st = len(res.stages)
    k = 0
    stage_of = {}
    for st in range(1, n_st + 1):                # ignition of stage st, then separation above it
        stage_of[("ignite", st)] = None
    seq = []
    for st in range(1, n_st + 1):
        seq.append(("ignite", st))
        if st < n_st:
            seq.append(("separate", st))
    top_number = len(seq) - 1
    for j, ev in enumerate(seq):
        stage_of[ev] = top_number - j
    for st, lst in engine_parts.items():
        for e in lst:
            e.istg = stage_of[("ignite", st)]
    for p in parts:
        if p.kind == "decoupler":
            p.istg = stage_of[("separate", p.stage)]
    # the fairing goes at the start of the stage MERLIN jettisons it at
    jst = min(max(int(spec.fairing.jettison_stage), 2), n_st)
    base.istg = stage_of[("ignite", jst)] if base.fairing else -1

    # ---- launch clamps. NOT IN MERLIN: they hold the vehicle up on the pad and stay there at lift-off. Without
    # them a vehicle standing on one nozzle (Scout G-1) toppled and broke up before ignition.
    aft1 = next(p for p in parts if p.key == "s1_aft_skirt")
    name, up, inward = CLAMP
    r = aft1.diameter / 2.0
    for k in range(N_CLAMPS):
        th = 2.0 * math.pi * k / N_CLAMPS + math.pi / N_CLAMPS
        phi = math.atan2(-math.cos(th), -math.sin(th))      # turns the clamp's +z towards the vehicle's axis
        z = aft1.zc - up
        ordered.append(KPart(key=f"clamp{k + 1}", title="Launch clamp (stock, not in MERLIN)", kind="clamp",
                             stage=1, z0=z, z1=z, diameter=0.0, x=(r + inward) * math.cos(th),
                             y=(r + inward) * math.sin(th), parent=aft1.key, own_node="srfAttach",
                             istg=stage_of[("ignite", 1)], stock=name,
                             rot=(0.0, math.sin(phi / 2.0), 0.0, math.cos(phi / 2.0)), srf=True))
    return ordered, resources


def _engine_data(res, st, sp, n, tag):
    """Per-engine thrust, Isp curve and propellant ratios, from MERLIN's sized stage and flown burn."""
    from .trajectory import ascent_vehicle_from_result
    veh = ascent_vehicle_from_result(res)
    burn = next(b for b in veh.burns if b.name == f"stage {st.index}")
    f_vac_each = burn.thrust_vac_N / n
    isp_vac = burn.isp_vac_s
    mdot_each = burn.mdot_kgs / n
    ae_each = burn.exit_area_m2 / n
    # MERLIN's thrust model, T = mdot ve - Pa Ae at constant mdot, is Isp(Pa) = Isp_vac - Pa Ae / (mdot g0):
    # a straight line in pressure. Its value at one atmosphere is the curve's second key.
    isp_1atm = isp_vac - P0_PA * ae_each / (mdot_each * G0)
    if sp.is_solid:
        grain = next(s.tank.propellant for s in res.geometry.segments
                     if s.stage == st.index and s.kind == "tank" and s.tank is not None and s.tank.role == "grain")
        return dict(thrust_vac_kN=f_vac_each / 1000.0, isp_vac_s=isp_vac, isp_1atm_s=isp_1atm,
                    isp_sl_input_s=sp.motor.isp_sl_s, mdot_kgs=mdot_each, exit_area_m2=ae_each,
                    solid=True, grain=grain, grain_res=_res_name(tag, grain), burn_time_s=burn.duration_s,
                    gimbal_deg=5.0)
    rho_f = res.spec.propellants[sp.fuel].density_kg_m3
    rho_o = res.spec.propellants[sp.oxidizer].density_kg_m3
    of = sp.of_ratio
    # KSP's propellant ratios are by volume (units). Per kg of fuel, of kg of oxidiser.
    v_f, v_o = 1.0 / rho_f, of / rho_o
    return dict(thrust_vac_kN=f_vac_each / 1000.0, isp_vac_s=isp_vac, isp_1atm_s=isp_1atm,
                isp_sl_input_s=sp.engine.isp_sl_s, mdot_kgs=mdot_each, exit_area_m2=ae_each,
                fuel=sp.fuel, oxidizer=sp.oxidizer, of_ratio=of,
                fuel_res=_res_name(tag, sp.fuel), ox_res=_res_name(tag, sp.oxidizer),
                ratio_fuel=v_f / (v_f + v_o), ratio_ox=v_o / (v_f + v_o), gimbal_deg=5.0)


# =========================================================================== part configs
def _f(x, nd=6):
    return f"{x:.{nd}f}".rstrip("0").rstrip(".") if isinstance(x, float) else str(x)


def _node(name, x, y, z, dy, size):
    return f"\tnode_stack_{name} = {_f(x)}, {_f(y)}, {_f(z)}, 0.0, {_f(dy)}, 0.0, {size}\n"


#: the lowest Isp the KSP curve is allowed to reach [s]
ISP_FLOOR_S = 1.0


def isp_keys(e: dict) -> list:
    """The atmosphereCurve keys (pressure in atm, Isp, in-tangent, out-tangent): MERLIN's straight line from vacuum
    to one atmosphere. A vacuum engine's line can go below zero before one atmosphere (a large nozzle at sea level);
    a negative Isp would be negative thrust in KSP, so there the line stops at ISP_FLOOR_S and stays flat."""
    vac, atm = e["isp_vac_s"], e["isp_1atm_s"]
    slope = atm - vac
    if atm >= ISP_FLOOR_S:
        return [(0, vac, slope, slope), (1, atm, slope, slope)]
    p_floor = (vac - ISP_FLOOR_S) / (vac - atm)
    return [(0, vac, slope, slope), (p_floor, ISP_FLOOR_S, slope, 0.0), (1, ISP_FLOOR_S, 0.0, 0.0)]


def part_cfg(p: KPart, tag: str) -> str:
    """The PART config of one generated part."""
    L, D = p.length, p.diameter
    size = 3 if D >= 3.0 else 2 if D >= 1.875 else 1
    pid = f"MERLIN_{tag}_{p.key}"
    out = ["PART\n{\n", f"\tname = {pid}\n", "\tmodule = Part\n", "\tauthor = MERLIN export\n"]
    if p.kind == "engine":
        e = p.engine
        model, nd, nh, ntop = ENGINE_MESH
        sx, sy = D / nd, L / nh
        out.append(f"\tMODEL\n\t{{\n\t\tmodel = {model}\n\t\tscale = {_f(sx)}, {_f(sy)}, {_f(sx)}\n"
                   f"\t\tposition = 0, {_f(L / 2 - ntop * sy)}, 0\n\t}}\n")
    elif p.kind == "fairing_base":
        model, nd = FAIRING_BASE_MESH
        s = D / nd
        out.append(f"\tMODEL\n\t{{\n\t\tmodel = {model}\n\t\tscale = {_f(s)}, {_f(s)}, {_f(s)}\n"
                   f"\t\trotation = 0.0,180,0.0\n\t}}\n")
    else:
        model, nd, nh = TANK_MESH
        out.append(f"\tMODEL\n\t{{\n\t\tmodel = {model}\n\t\tscale = {_f(D / nd)}, {_f(L / nh)}, {_f(D / nd)}\n\t}}\n")
    out.append("\trescaleFactor = 1\n")
    out.append(_node("top", 0, L / 2, 0, 1.0, size))
    out.append(_node("bottom", 0, -L / 2, 0, -1.0, size))
    for name, (x, z_station, y, dy) in p.extra_nodes.items():
        out.append(_node(name, x, z_station - p.zc, y, dy, 1))
    cost = 0
    out += ["\tTechRequired = start\n", "\tentryCost = 0\n", f"\tcost = {cost}\n",
            "\tcategory = none\n" if p.kind != "engine" else "\tcategory = Engine\n", "\tsubcategory = 0\n",
            f"\ttitle = {p.title} [MERLIN {tag}]\n", "\tmanufacturer = MERLIN export\n",
            f"\tdescription = Generated by MERLIN from the sized design. Dry mass {p.dry_kg:,.1f} kg.\n",
            "\tattachRules = 1,0,1,1,0\n", f"\tmass = {_f(p.dry_kg / 1000.0, 7)}\n",
            "\tdragModelType = default\n\tmaximum_drag = 0.2\n\tminimum_drag = 0.2\n\tangularDrag = 2\n",
            "\tcrashTolerance = 12\n\tbreakingForce = 2000\n\tbreakingTorque = 2000\n\tmaxTemp = 2400\n",
            f"\tCoMOffset = 0, {_f(p.cm_z - p.zc)}, 0\n", f"\tbulkheadProfiles = size{size}\n",
            "\ttags = merlin\n"]
    if p.kind == "decoupler":
        out.append("\tfuelCrossFeed = False\n\tstageOffset = 1\n\tchildStageOffset = 1\n")
        out.append("\tMODULE\n\t{\n\t\tname = ModuleDecouple\n\t\tejectionForce = 250\n\t\tisOmniDecoupler = false\n"
                   "\t\texplosiveNodeID = top\n\t}\n")
    else:
        out.append("\tfuelCrossFeed = True\n")
    if p.command:
        out.append("\tvesselType = Probe\n")
        out.append("\tMODULE\n\t{\n\t\tname = ModuleCommand\n\t\tminimumCrew = 0\n\t\tRESOURCE\n\t\t{\n"
                   "\t\t\tname = ElectricCharge\n\t\t\trate = 0.02\n\t\t}\n\t\thasHibernation = False\n\t}\n")
        out.append("\tMODULE\n\t{\n\t\tname = ModuleSAS\n\t\tSASServiceLevel = 3\n\t}\n")
        # NOT IN MERLIN: a small reaction wheel, so the vehicle can hold attitude when no engine is firing
        out.append("\tMODULE\n\t{\n\t\tname = ModuleReactionWheel\n\t\tPitchTorque = 20\n\t\tYawTorque = 20\n"
                   "\t\tRollTorque = 20\n\t\tRESOURCE\n\t\t{\n\t\t\tname = ElectricCharge\n\t\t\trate = 0.1\n\t\t}\n\t}\n")
        out.append("\tRESOURCE\n\t{\n\t\tname = ElectricCharge\n\t\tamount = 5000\n\t\tmaxAmount = 5000\n\t}\n")
    if p.kind == "engine":
        e = p.engine
        out += ["\tsound_rocket_hard = running\n", "\tsound_vent_medium = engage\n",
                "\tfx_exhaustFlame_yellow_medium = 0.0, -1.0, 0.0, 0.0, 1.0, 0.0, running\n",
                "\tfx_smokeTrail_light = 0.0, -1.5, 0.0, 0.0, 1.0, 0.0, running\n"]
        out.append("\tMODULE\n\t{\n\t\tname = ModulePartVariants\n\t\tbaseVariant = Bare\n\t\tVARIANT\n\t\t{\n"
                   "\t\t\tname = Bare\n\t\t\tGAMEOBJECTS\n\t\t\t{\n\t\t\t\tUpperCowl = false\n\t\t\t\tUpperCowlFoil = false\n"
                   "\t\t\t\tLowerCowl = false\n\t\t\t\tLowerCowlFoil = false\n\t\t\t\tTruss = true\n\t\t\t\tEngine = true\n"
                   "\t\t\t\tfairing = false\n\t\t\t\tfairingSmall = false\n\t\t\t}\n\t\t}\n\t}\n")
        if e.get("solid"):
            # a solid: no throttle, no shut-down, constant mass flow (KSP's fuel flow is maxThrust / (Isp_vac g0)
            # whatever the pressure, exactly MERLIN's constant-mdot neutral burn)
            head = ("\t\tthrottleLocked = True\n\t\tallowShutdown = False\n\t\tallowRestart = False\n"
                    "\t\tEngineType = SolidBooster\n"
                    f"\t\tPROPELLANT\n\t\t{{\n\t\t\tname = {e['grain_res']}\n\t\t\tratio = 1\n"
                    "\t\t\tDrawGauge = True\n\t\t}\n")
        else:
            head = ("\t\tEngineType = LiquidFuel\n"
                    f"\t\tPROPELLANT\n\t\t{{\n\t\t\tname = {e['fuel_res']}\n\t\t\tratio = {_f(e['ratio_fuel'], 8)}\n"
                    "\t\t\tDrawGauge = True\n\t\t}\n"
                    f"\t\tPROPELLANT\n\t\t{{\n\t\t\tname = {e['ox_res']}\n\t\t\tratio = {_f(e['ratio_ox'], 8)}\n\t\t}}\n")
        out.append("\tMODULE\n\t{\n\t\tname = ModuleEngines\n\t\tthrustVectorTransformName = thrustTransform\n"
                   "\t\texhaustDamage = True\n\t\tignitionThreshold = 0.1\n\t\tminThrust = 0\n"
                   f"\t\tmaxThrust = {_f(e['thrust_vac_kN'], 4)}\n\t\theatProduction = 100\n" + head +
                   "\t\tatmosphereCurve\n\t\t{\n"
                   # explicit tangents, so the curve is MERLIN's straight line and not a smoothed spline
                   + "".join(f"\t\t\tkey = {_f(float(pp), 6)} {_f(float(ii), 4)} {_f(float(a), 4)} {_f(float(b), 4)}\n"
                             for pp, ii, a, b in isp_keys(e)) +
                   "\t\t}\n\t}\n")
        out.append(f"\tMODULE\n\t{{\n\t\tname = ModuleGimbal\n\t\tgimbalTransformName = gimbal\n"
                   f"\t\tgimbalRange = {_f(e['gimbal_deg'])}\n\t}}\n")
    if p.kind == "fairing_base" and p.fairing:
        out.append("\tstageOffset = 1\n\tchildStageOffset = 1\n")
        out.append("\tMODULE\n\t{\n\t\tname = ModuleProceduralFairing\n\t\tnSides = 36\n\t\tnArcs = 6\n"
                   "\t\tnCollidersPerXSection = 12\n\t\tTextureURL = Squad/Parts/Aero/fairings/fairings_diff\n"
                   "\t\tCapTextureURL = Squad/Parts/Aero/fairings/fairingsCap\n"
                   "\t\tTextureNormalURL = Squad/Parts/Aero/fairings/fairings_normals\n"
                   "\t\tBaseModelTransformName = Mesh\n\t\tpanelGrouping = 3\n\t\tpivot = 0,0,0\n\t\taxis = 0,1,0\n"
                   f"\t\tbaseRadius = {_f(D / 2)}\n\t\tmaxRadius = {_f(max(D, 6.0))}\n\t\tcapRadius = 0.05\n"
                   "\t\tsnapThreshold = 0.25\n\t\txSectionHeightMin = 0.1\n\t\txSectionHeightMax = 20\n"
                   "\t\tminHeightRadiusRatio = 0.0\n\t\tnoseTip = 0.5\n"
                   # panel mass = area x UnitAreaMass: set so the panels weigh what MERLIN's fairing weighs
                   f"\t\tUnitAreaMass = {_f(p.fairing['unit_area_mass_t'], 8)}\n\t\tUnitAreaCost = 0\n\t}}\n")
    for rn, units in p.resources.items():
        out.append(f"\tRESOURCE\n\t{{\n\t\tname = {rn}\n\t\tamount = {_f(units, 3)}\n\t\tmaxAmount = {_f(units, 3)}\n\t}}\n")
    out.append("}\n")
    return "".join(out)


def resources_cfg(resources: dict) -> str:
    out = []
    for rn, r in resources.items():
        out.append("RESOURCE_DEFINITION\n{\n"
                   f"\tname = {rn}\n\tdisplayName = {r['propellant']} (MERLIN)\n\tabbreviation = {r['propellant']}\n"
                   f"\tdensity = {_f(r['density_kg_m3'] / 1.0e6, 9)}\n"     # tonnes per litre
                   "\tunitCost = 0\n\tflowMode = STACK_PRIORITY_SEARCH\n\ttransfer = PUMP\n\tisTweakable = true\n"
                   "\tisVisible = true\n\tvolume = 1\n}\n")
    return "".join(out)


# =========================================================================== the craft file
def _v3(x, y, z):
    return f"{_f(x)},{_f(y)},{_f(z)}"


def craft_text(parts: list, tag: str, ship: str, description: str, y_offset: float) -> str:
    """A .craft that assembles the generated parts. Positions are MERLIN stations, lifted by y_offset."""
    # KSP stores a part's name with every underscore turned into a dot (liquidEngineMainsail_v2 is
    # liquidEngineMainsail.v2 in a craft), and reads a craft's "part = name_id" by cutting at the FIRST
    # underscore. Written with underscores, every part loaded as "MERLIN" and none was found.
    ids = {p.key: (p.stock if p.stock else f"MERLIN_{tag}_{p.key}".replace("_", ".")) + f"_{4200000000 - i}"
           for i, p in enumerate(parts)}
    by = {p.key: p for p in parts}
    children = {p.key: [] for p in parts}
    for p in parts:
        if p.parent:
            children[p.parent].append(p.key)
    flying = [p for p in parts if not p.stock]
    zmin = min(p.z0 for p in flying)
    zmax = max(p.z1 for p in flying)
    dmax = max(p.diameter for p in flying)
    head = [f"ship = {ship}\n", "version = 1.12.5\n", f"description = {description}\n", "type = VAB\n",
            f"size = {_f(dmax)},{_f(zmax - zmin)},{_f(dmax)}\n", "steamPublishedFileId = 0\n",
            "persistentId = 1234567890\n", "rot = 0,0,0,0\n", "missionFlag = Squad/Flags/default\n",
            "vesselType = Probe\n", "OverrideDefault = False,False,False,False\n",
            "OverrideActionControl = 0,0,0,0\n", "OverrideAxisControl = 0,0,0,0\n",
            "OverrideGroupNames = ,,,\n"]

    def node_pos(p, node):
        """This part's node, local position and direction."""
        if node == "top":
            return (0.0, p.length / 2, 0.0), (0, 1, 0)
        if node == "bottom":
            return (0.0, -p.length / 2, 0.0), (0, -1, 0)
        x, z_station, y, dy = p.extra_nodes[node]
        return (x, z_station - p.zc, y), (0, int(dy), 0)

    def att(name, other, pos, d):
        a = f"{_f(pos[0])}|{_f(pos[1])}|{_f(pos[2])}"
        b = f"{d[0]}|{d[1]}|{d[2]}"
        return f"\tattN = {name},{other}_{a}_{b}_{a}_{b}\n"

    body = []
    for i, p in enumerate(parts):
        wx, wy, wz = p.x, p.zc + y_offset, p.y
        q = ",".join(_f(float(c)) for c in p.rot)
        lines = ["PART\n{\n", f"\tpart = {ids[p.key]}\n", "\tpartName = Part\n",
                 f"\tpersistentId = {3000000000 + i}\n", f"\tpos = {_v3(wx, wy, wz)}\n", "\tattPos = 0,0,0\n",
                 f"\tattPos0 = {_v3(wx, wy, wz)}\n", f"\trot = {q}\n", "\tattRot = 0,0,0,1\n",
                 f"\tattRot0 = {q}\n", "\tmir = 1,1,1\n", "\tsymMethod = Radial\n", "\tautostrutMode = Off\n",
                 "\trigidAttachment = False\n", f"\tistg = {p.istg}\n", "\tresPri = 0\n", "\tdstg = 0\n",
                 f"\tsidx = {0 if p.istg >= 0 else -1}\n", f"\tsqor = {p.istg if p.istg >= 0 else -1}\n",
                 "\tsepI = -1\n", f"\tattm = {1 if p.srf else 0}\n", "\tsameVesselCollision = False\n", "\tmodCost = 0\n",
                 "\tmodMass = 0\n", "\tmodSize = 0,0,0\n"]
        for c in children[p.key]:
            lines.append(f"\tlink = {ids[c]}\n")
        # this part's own nodes: where its parent and each child attach
        if p.parent and p.srf:
            lines.append(f"\tsrfN = srfAttach,{ids[p.parent]}\n")
        elif p.parent:
            pos, d = node_pos(p, p.own_node)
            lines.append(att(p.own_node, ids[p.parent], pos, d))
        for c in children[p.key]:
            cp = by[c]
            if cp.srf:                       # a surface-attached child is recorded on the child only
                continue
            pos, d = node_pos(p, cp.parent_node)
            lines.append(att(cp.parent_node, ids[c], pos, d))
        lines += ["\tEVENTS\n\t{\n\t}\n", "\tACTIONS\n\t{\n\t}\n", "\tPARTDATA\n\t{\n\t}\n"]
        if p.kind == "fairing_base" and p.fairing:
            xs = "".join(f"\t\tXSECTION\n\t\t{{\n\t\t\th = {_f(h)}\n\t\t\tr = {_f(r)}\n\t\t}}\n"
                         for h, r in p.fairing["xsections"])
            lines.append("\tMODULE\n\t{\n\t\tname = ModuleProceduralFairing\n\t\tisEnabled = True\n"
                         "\t\tinterstageCraftID = 0\n\t\tnArcs = 6\n\t\tejectionForce = 100\n"
                         "\t\tuseClamshell = False\n\t\tisCapped = False\n\t\tstagingEnabled = True\n"
                         "\t\tfsm = st_idle\n\t\tEVENTS\n\t\t{\n\t\t}\n\t\tACTIONS\n\t\t{\n\t\t}\n" + xs + "\t}\n")
        for rn, units in p.resources.items():
            lines.append(f"\tRESOURCE\n\t{{\n\t\tname = {rn}\n\t\tamount = {_f(units, 3)}\n"
                         f"\t\tmaxAmount = {_f(units, 3)}\n\t\tflowState = True\n\t\tisTweakable = True\n"
                         "\t\thideFlow = False\n\t\tisVisible = True\n\t\tflowMode = Both\n\t}\n")
        if p.command:
            lines.append("\tRESOURCE\n\t{\n\t\tname = ElectricCharge\n\t\tamount = 5000\n\t\tmaxAmount = 5000\n"
                         "\t\tflowState = True\n\t\tisTweakable = True\n\t\thideFlow = False\n"
                         "\t\tisVisible = True\n\t\tflowMode = Both\n\t}\n")
        lines.append("}\n")
        body.append("".join(lines))
    return "".join(head) + "".join(body)


# =========================================================================== the check, and the export
def _isp_vac(sp):
    return sp.motor.isp_vac_s if sp.is_solid else sp.engine.isp_vac_s


def summary(res, parts: list, resources: dict) -> dict:
    """MERLIN against what the generated files contain, stage by stage. Pure arithmetic on the export."""
    spec = res.spec
    dens = {rn: r["density_kg_m3"] for rn, r in resources.items()}

    def mass(p):
        return p.dry_kg + sum(u / 1000.0 * dens[rn] for rn, u in p.resources.items())
    fair_kg = parts and next((p.fairing["mass_kg"] for p in parts if p.fairing), 0.0)
    total = sum(mass(p) for p in parts) + (fair_kg or 0.0)
    cm = (sum(mass(p) * (p.cm_z if not p.resources else
                         (p.dry_kg * p.cm_z + (mass(p) - p.dry_kg) * p.zc) / mass(p)) for p in parts)
          + (fair_kg or 0.0) * 0.0) / max(total - (fair_kg or 0.0), 1e-9)
    rows = []
    for st in res.stages:
        mine = [p for p in parts if p.stage == st.index]
        dry = sum(p.dry_kg for p in mine)
        prop = sum(mass(p) - p.dry_kg for p in mine)
        eng = next(p.engine for p in mine if p.kind == "engine")
        n = sum(1 for p in mine if p.kind == "engine")
        usable_merlin = st.m_prop_mission_kg + st.m_startup_kg
        rows.append(dict(stage=st.index,
                         merlin_dry_kg=st.m_dry_kg + st.m_residual_kg + st.m_margin_prop_kg, export_dry_kg=dry,
                         merlin_usable_kg=usable_merlin, export_usable_kg=prop,
                         merlin_thrust_vac_kN=st.thrust_vac_N / 1000.0, export_thrust_vac_kN=eng["thrust_vac_kN"] * n,
                         merlin_isp_vac_s=_isp_vac(spec.stages[st.index - 1]), export_isp_vac_s=eng["isp_vac_s"],
                         merlin_isp_sl_s=eng["isp_sl_input_s"], export_isp_1atm_s=eng["isp_1atm_s"],
                         merlin_of=None if eng.get("solid") else spec.stages[st.index - 1].of_ratio,
                         export_of=None if eng.get("solid") else
                         (eng["ratio_ox"] * dens[eng["ox_res"]]) / (eng["ratio_fuel"] * dens[eng["fuel_res"]]),
                         solid=bool(eng.get("solid")), propellant=eng.get("grain"),
                         # MERLIN burns the start-up propellant at ignition with no delta-v; KSP burns it in flight
                         merlin_burn_s=st.burn_time_s + st.m_startup_kg / (eng["mdot_kgs"] * n),
                         export_burn_s=prop / (eng["mdot_kgs"] * n),
                         n_engines=n))
    return dict(merlin_glom_kg=res.glom_kg, export_glom_kg=total, rows=rows, n_parts=len(parts),
                fairing_kg=fair_kg or 0.0)


def readme_text(name: str, tag: str, res) -> str:
    lines = [
        f"{name} - exported from MERLIN for Kerbal Space Program",
        "",
        f"Needs: {KSP_TARGET}. Ferram Aerospace Research is optional.",
        "",
        "To install, unzip into the Kerbal Space Program folder (the one that holds GameData):",
        f"  GameData/MERLIN_Export/{tag}/   the vehicle's own parts and propellants",
        f"  Ships/VAB/{tag}_MERLIN.craft    the vehicle; it shows in the VAB's load dialog under Stock",
        "    vessels. To have it under a save's own craft instead, move it to saves/<save>/Ships/VAB/.",
        "",
        "Staging: space ignites stage 1; after burnout, space separates; space again ignites the next",
        "stage and jettisons the fairing at the stage MERLIN jettisons it.",
        "",
        f"Lift-off mass {res.glom_kg:,.0f} kg, payload {res.payload_mass_kg:,.0f} kg. Every part's mass, every",
        "tank's propellant and every engine's thrust and Isp are MERLIN's. Not from MERLIN: a 20 kNm reaction",
        "wheel and 5000 units of ElectricCharge in the top stage's forward skirt, and a 5 degree engine gimbal,",
        "so the vehicle can be steered at all.",
    ]
    return "\n".join(lines) + "\n"


def export(res, out_dir: str, ksp_dir: str | None = None) -> dict:
    """Write the KSP export of a sized vehicle into out_dir (GameData/ and Ships/VAB/, plus a zip), and into a KSP
    install too when ksp_dir is given. Returns the paths and the check."""
    spec = res.spec
    tag = _tag(spec.name)
    parts, resources = build_parts(res, tag)
    ship = f"{spec.name} (MERLIN)"
    desc = (f"Exported from MERLIN: lift-off mass {res.glom_kg:,.0f} kg, payload {res.payload_mass_kg:,.0f} kg. "
            f"Needs {KSP_TARGET}.")
    lowest = min(p.z0 for p in parts if not p.stock)
    craft = craft_text(parts, tag, ship, desc, y_offset=2.0 - lowest)
    gd = os.path.join(out_dir, "GameData", "MERLIN_Export", tag)
    os.makedirs(gd, exist_ok=True)
    os.makedirs(os.path.join(out_dir, "Ships", "VAB"), exist_ok=True)
    files = {}
    with open(os.path.join(gd, "parts.cfg"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"// Generated by MERLIN for {spec.name}. Do not edit: export again instead.\n")
        fh.write("".join(part_cfg(p, tag) for p in parts if not p.stock))
    files["parts"] = os.path.join(gd, "parts.cfg")
    with open(os.path.join(gd, "resources.cfg"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(resources_cfg(resources))
    files["resources"] = os.path.join(gd, "resources.cfg")
    craft_path = os.path.join(out_dir, "Ships", "VAB", f"{tag}_MERLIN.craft")
    with open(craft_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(craft)
    files["craft"] = craft_path
    readme = os.path.join(out_dir, "README_KSP.txt")
    with open(readme, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(readme_text(spec.name, tag, res))
    files["readme"] = readme
    zp = os.path.join(out_dir, f"{tag}_KSP.zip")
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for k in ("readme", "parts", "resources", "craft"):
            z.write(files[k], os.path.relpath(files[k], out_dir))
    files["zip"] = zp
    check = summary(res, parts, resources)
    return dict(tag=tag, ship=ship, files=files, check=check, parts=parts, resources=resources)


# =========================================================================== finding and installing into KSP
#: where Steam and the KSP store put the game on Windows; other Steam libraries are read from libraryfolders.vdf
_STEAM_ROOTS = (r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam")
_SAVE_SKIP = {"scenarios", "training", "missions"}


def _is_ksp(path: str) -> bool:
    return bool(path) and os.path.isdir(os.path.join(path, "GameData")) and os.path.isdir(os.path.join(path, "saves"))


def find_ksp(extra: tuple = ()) -> str | None:
    """The KSP install folder, or None. Looks at the given folders, then every Steam library on this machine."""
    cands = list(extra)
    for root in _STEAM_ROOTS:
        cands.append(os.path.join(root, "steamapps", "common", "Kerbal Space Program"))
        vdf = os.path.join(root, "steamapps", "libraryfolders.vdf")
        try:
            with open(vdf, encoding="utf-8", errors="replace") as fh:
                for m in re.finditer(r'"path"\s+"([^"]+)"', fh.read()):
                    lib = m.group(1).replace("\\\\", "\\")
                    cands.append(os.path.join(lib, "steamapps", "common", "Kerbal Space Program"))
        except OSError:
            pass
    for c in cands:
        if _is_ksp(c):
            return os.path.normpath(c)
    return None


def ksp_status(ksp_dir: str | None) -> dict:
    """What the install has that the export needs, and the saves a craft can go into."""
    if not _is_ksp(ksp_dir or ""):
        return dict(found=False, path=ksp_dir, saves=[], mods={}, problems=[
            "No Kerbal Space Program folder found. Give its path (the folder that holds GameData and saves)."])
    gd = os.path.join(ksp_dir, "GameData")
    names = os.listdir(gd)
    mods = {"ModuleManager": any(n.lower().startswith("modulemanager") and n.lower().endswith(".dll") for n in names),
            "Real Solar System": "RealSolarSystem" in names,
            "Kopernicus": "Kopernicus" in names,
            "Ferram Aerospace Research": "FerramAerospaceResearch" in names}
    saves = sorted(n for n in os.listdir(os.path.join(ksp_dir, "saves"))
                   if n not in _SAVE_SKIP and os.path.isfile(os.path.join(ksp_dir, "saves", n, "persistent.sfs")))
    problems = []
    if not mods["ModuleManager"]:
        problems.append("ModuleManager is not installed: the generated parts load without it, but install it "
                        "anyway, Real Solar System needs it.")
    if not mods["Real Solar System"]:
        problems.append("Real Solar System is not installed. The vehicle will load, but on stock Kerbin (a tenth "
                        "of Earth's size) it is hugely overpowered and MERLIN's numbers do not apply.")
    return dict(found=True, path=ksp_dir, saves=saves, mods=mods, problems=problems)


def install(exported: dict, ksp_dir: str, save: str | None) -> dict:
    """Copy an export into a KSP install: the parts into GameData/MERLIN_Export/<tag>/, the craft into
    saves/<save>/Ships/VAB/ (or the install's own Ships/VAB/ when no save is given). Only MERLIN's own folder and
    the one craft file are written; nothing else in the install is touched."""
    import shutil
    if not _is_ksp(ksp_dir):
        raise KSPExportError(f"'{ksp_dir}' is not a Kerbal Space Program folder (it has no GameData and saves)")
    tag = exported["tag"]
    dst_gd = os.path.join(ksp_dir, "GameData", "MERLIN_Export", tag)
    os.makedirs(dst_gd, exist_ok=True)
    for k in ("parts", "resources"):
        shutil.copyfile(exported["files"][k], os.path.join(dst_gd, os.path.basename(exported["files"][k])))
    if save:
        if save not in ksp_status(ksp_dir)["saves"]:
            raise KSPExportError(f"there is no save called '{save}' in {ksp_dir}")
        vab = os.path.join(ksp_dir, "saves", save, "Ships", "VAB")
    else:
        vab = os.path.join(ksp_dir, "Ships", "VAB")
    os.makedirs(vab, exist_ok=True)
    craft = os.path.join(vab, os.path.basename(exported["files"]["craft"]))
    shutil.copyfile(exported["files"]["craft"], craft)
    return dict(gamedata=dst_gd, craft=craft, save=save)
