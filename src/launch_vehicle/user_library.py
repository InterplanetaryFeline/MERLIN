"""Your own propellants and tank materials, kept beside your designs and merged into every one.

The shipped property library is `config/engineering_assumptions.yaml`. It is reference material: a person who
needs a propellant or an alloy it does not carry should not have to edit that file, which an app update would
overwrite and which every design on the machine reads. So additions live in a library of their own,
`designs/my_library.yaml`, beside the designs they are for, and are merged into the shipped library each time
a design is loaded. They then appear in the fuel, oxidiser and material dropdowns like any other entry.

THE RULES, which are the same as everywhere else in the tool.

* Every leaf is annotated `{v, u, d, s, t}`. The source and provenance are the person's, and are required: an
  entry with no source is refused, because a number nobody can trace is the thing this tool exists to avoid.
* A field the form leaves blank either stays unknown (boiling point: not cryogenic; Table 8.6 coefficient: none,
  so that propellant's tanks must be sized by volume or as pressure vessels) or takes a stated default, which is
  then tagged `assumed` with the reason in its source.
* A custom entry may not take the name of a shipped one. Changing a shipped value is what the GUI's library
  fields are for, and two entries with one name would make it impossible to tell which was used.
* A saved design carries a copy of every custom entry it uses, in a `library:` block, so it opens on another
  machine that has never seen your library. The design's copy wins over the library's: a design describes the
  vehicle as it was sized, and editing your library later must not quietly change a vehicle already saved.
  The same block carries any shipped entry whose values you changed in the GUI, for the same reason.
"""
from __future__ import annotations
import copy
import os
import re

import yaml

from .paths import ROOT

USER_LIBRARY_PATH = os.path.join(ROOT, "designs", "my_library.yaml")

#: the two kinds of entry a person can add, and the library section each one lives in
SECTIONS = {"propellant": "propellants", "material": "tank_materials", "solid": "solid_propellants",
            "combination": "propellant_combinations"}

#: entry names become YAML keys and dotted input paths, so a dot or a bracket would break both
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _\-+()/,]{0,47}$")

#: One dict per form field: key, label, the units the file stores and the form shows, the factor from the
#: form's value to the file's, whether it is required, the default for a blank (tagged `assumed`, with why),
#: the range the form accepts, and the description written into the entry.
SCHEMA = {
    "propellant": [
        dict(key="role", label="Fuel or oxidiser", units="-", choices=["fuel", "oxidizer"], required=True,
             d="Whether this propellant is offered as a fuel or as an oxidiser. The GUI uses it to keep the two "
               "dropdowns apart"),
        dict(key="density_kg_m3", label="Density (as loaded)", units="kg/m^3", shown="kg/m^3", factor=1.0,
             required=True, range=(10.0, 3000.0),
             d="Liquid density at the loading condition, for tank sizing. This is the property that matters most: "
               "it sets the tank volume"),
        dict(key="boiling_K", label="Normal boiling point (blank = not cryogenic)", units="K", shown="K",
             factor=1.0, required=False, range=(1.0, 400.0),
             d="Normal boiling temperature. Given, the tank shrinks when it is filled cold and is sized larger to "
               "make up for it; blank means a storable propellant and no shrinkage"),
        dict(key="insulation_kg_m2", label="Tank insulation mass per square metre", units="kg/m^2",
             shown="kg/m^2", factor=1.0, required=False, default=0.0, range=(0.0, 20.0),
             default_why="no insulation (storable propellant)",
             d="External tank insulation areal mass; 0 for a storable propellant"),
        dict(key="tank_mer_per_kg", label="Tank mass per kg of propellant (Table 8.6 style, optional)",
             units="kg/kg", shown="kg/kg", factor=1.0, required=False, range=(0.0005, 0.5),
             d="Tank mass divided by propellant mass, for the 'Akin, by propellant mass' tank method. Blank means "
               "there is none, so this propellant's tanks must be sized by volume or as pressure vessels"),
    ],
    "material": [
        dict(key="name", label="Full name", units="-", text=True, required=True,
             d="Material label shown beside the key in the dropdown"),
        dict(key="rho_kg_m3", label="Density", units="kg/m^3", shown="kg/m^3", factor=1.0, required=True,
             range=(500.0, 25000.0), d="Density. Sets the wall mass of a pressure-vessel tank and of a shell"),
        dict(key="yield_min_Pa", label="Published minimum yield strength", units="Pa", shown="MPa", factor=1.0e6,
             required=True, range=(10.0, 3000.0),
             d="Published minimum 0.2 % yield (or proof) strength, recorded so the allowable can be traced to it"),
        dict(key="sigma_allow_Pa", label="Allowable membrane stress (blank = 0.633 x yield)", units="Pa",
             shown="MPa", factor=1.0e6, required=False, range=(5.0, 3000.0),
             d="Allowable membrane stress at operating temperature, before the safety factor. Blank takes 0.633 x "
               "the minimum yield, the basis every shipped material uses, so a trade compares like with like"),
        dict(key="joint_efficiency", label="Weld joint efficiency", units="-", shown="-", factor=1.0,
             required=False, default=0.9, range=(0.3, 1.0), default_why="the value the shipped aluminium uses",
             d="Weld joint efficiency, dividing the allowable in the wall-thickness relation"),
        dict(key="safety_factor", label="Safety factor on pressure", units="-", shown="-", factor=1.0,
             required=False, default=1.4, range=(1.0, 5.0), default_why="the value every shipped material uses",
             d="Factor applied to pressure for sizing"),
        dict(key="corrosion_allowance_m", label="Corrosion / chem-mill allowance", units="m", shown="mm",
             factor=1.0e-3, required=False, default=0.0, range=(0.0, 5.0), default_why="none",
             d="Allowance added to the computed wall thickness"),
        dict(key="t_min_m", label="Minimum practical tank gauge", units="m", shown="mm", factor=1.0e-3,
             required=True, range=(0.05, 50.0), d="Thinnest wall the tank can be made with"),
        dict(key="E_Pa", label="Young's modulus", units="Pa", shown="GPa", factor=1.0e9, required=True,
             range=(1.0, 500.0), d="Young's modulus, for the buckling allowables of the shell stress analysis"),
        dict(key="poisson", label="Poisson's ratio", units="-", shown="-", factor=1.0, required=False,
             default=0.3, range=(0.05, 0.5), default_why="typical of metals",
             d="Poisson's ratio, used only by the flared-skirt buckling criterion"),
        dict(key="alpha_per_K", label="Thermal expansion coefficient", units="1/K", shown="um/(m K)",
             factor=1.0e-6, required=True, range=(0.01, 100.0),
             d="Coefficient of thermal expansion. Sets how much a tank shrinks when filled with a cryogen"),
        dict(key="t_min_structural_m", label="Minimum structural gauge (shell analysis)", units="m", shown="mm",
             factor=1.0e-3, required=False, default=0.5, range=(0.05, 50.0),
             default_why="the value the shipped aluminium uses",
             d="Minimum gauge for a load-carrying skin in the shell stress analysis"),
    ],
    "solid": [
        dict(key="density_kg_m3", label="Density of the cast propellant", units="kg/m^3", shown="kg/m^3",
             factor=1.0, required=True, range=(800.0, 2500.0),
             d="Density of the cured grain. Sets the motor case volume, so with the case relation it sets the "
               "motor's size and inert mass"),
        dict(key="c_star_mps", label="Characteristic velocity c* (optional)", units="m/s", shown="m/s",
             factor=1.0, required=False, range=(500.0, 2500.0),
             d="Characteristic exhaust speed. Read only by the internal ballistics analysis, which needs it and "
               "the burn-rate exponent together; blank leaves that analysis unavailable for this propellant"),
        dict(key="burn_rate_exponent", label="Burn-rate pressure exponent n (optional)", units="-", shown="-",
             factor=1.0, required=False, range=(0.05, 0.95),
             d="Pressure exponent n in de Saint Robert's law r = a Pc^n. Read only by the internal ballistics "
               "analysis; it must be below 1 for a stable burn"),
        dict(key="isp_note", label="Note on its performance (optional)", units="-", text=True, required=False,
             d="Free text: the Isp and c* the source quotes and at what condition. Isp itself is an input of the "
               "motor, not of the propellant"),
    ],
    "combination": [
        dict(key="oxidizer", label="Oxidiser", units="-", choices_from="oxidizer", required=True,
             d="Oxidiser key into the propellant library"),
        dict(key="fuel", label="Fuel", units="-", choices_from="fuel", required=True,
             d="Fuel key into the propellant library"),
        dict(key="of_ratio_flight", label="Mixture ratio O/F as flown", units="-", shown="-", factor=1.0,
             required=True, range=(0.05, 30.0),
             d="Oxidiser-to-fuel mass ratio the engines run at. Picking this combination writes it into the stage's "
               "mixture ratio, which with the two densities sets how the tank volume is split"),
        dict(key="of_ratio_optimum", label="O/F for peak Isp (optional)", units="-", shown="-", factor=1.0,
             required=False, range=(0.05, 30.0), d="O/F at maximum Isp, for reference"),
        dict(key="isp_ref_s", label="Reference Isp (optional)", units="s", shown="s", factor=1.0, required=False,
             range=(50.0, 600.0),
             d="Theoretical Isp at the source's reference condition. For reference only: the engine's own Isp is "
               "what sizes the stage"),
        dict(key="cstar_ref_mps", label="Characteristic velocity c* (optional)", units="m/s", shown="m/s",
             factor=1.0, required=False, range=(500.0, 3500.0),
             d="Theoretical characteristic velocity. Offered as the value to use when an engine is sized from the "
               "book relations and has no c* of its own"),
        dict(key="Tc_ref_K", label="Chamber temperature (optional)", units="K", shown="K", factor=1.0,
             required=False, range=(500.0, 5000.0), d="Theoretical chamber temperature, for reference"),
        dict(key="mw_ref_kg_kmol", label="Exhaust molecular mass (optional)", units="kg/kmol", shown="kg/kmol",
             factor=1.0, required=False, range=(1.0, 60.0), d="Exhaust molecular mass, for reference"),
    ],
}
PROVENANCES = ("user", "reference", "assumed")


class LibraryError(ValueError):
    """An entry that cannot be added. `field` names the form field at fault, where there is one."""

    def __init__(self, message, field=None):
        super().__init__(message)
        self.field = field


# --------------------------------------------------------------------------- the file
def load(path: str | None = None) -> dict:
    """The personal library as an annotated document: {section: {name: {key: {v,u,d,s,t}}}}. Empty if absent."""
    p = path or USER_LIBRARY_PATH
    if not os.path.exists(p):
        return {}
    from .config_io import _Loader
    with open(p, encoding="utf-8") as fh:
        doc = yaml.load(fh, Loader=_Loader) or {}
    return {sec: dict(doc.get(sec) or {}) for sec in SECTIONS.values() if doc.get(sec)}


def _write(doc: dict, path: str | None = None) -> None:
    p = path or USER_LIBRARY_PATH
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# Your own propellants and tank materials, added from the MERLIN GUI (Library button).\n"
                 "# Merged into config/engineering_assumptions.yaml whenever a design is loaded. Every leaf is\n"
                 "# annotated {v, u, d, s, t} like the shipped library. A saved design carries a copy of each\n"
                 "# entry it uses, so it still opens on a machine without this file.\n")
        yaml.safe_dump({k: v for k, v in doc.items() if v}, fh, sort_keys=False, width=200, allow_unicode=True)
    os.replace(tmp, p)


def shipped_names(assump_path: str, section: str) -> set:
    from .config_io import _Loader
    with open(assump_path, encoding="utf-8") as fh:
        doc = yaml.load(fh, Loader=_Loader) or {}
    return set((doc.get(section) or {}).keys())


def custom_names(path: str | None = None) -> dict:
    """{section: set of names} in the personal library."""
    return {sec: set(v) for sec, v in load(path).items()}


# --------------------------------------------------------------------------- adding and removing
def build_entry(kind: str, values: dict, source: str, provenance: str, known: dict | None = None) -> dict:
    """Validate the form's values and turn them into an annotated library entry. Raises LibraryError.

    `known` is {"fuel": names, "oxidizer": names} of the liquids a combination may name; without it a
    combination's fuel and oxidiser are not checked against the library."""
    if kind not in SCHEMA:
        raise LibraryError(f"unknown kind of entry {kind!r}; expected one of {', '.join(SCHEMA)}")
    source = str(source or "").strip()
    if not source:
        raise LibraryError("say where these numbers come from: a datasheet, a paper, a handbook, or 'my own "
                           "estimate'. An entry with no source is refused, as every input in this tool is.",
                           field="source")
    if provenance not in PROVENANCES:
        raise LibraryError(f"provenance must be one of {', '.join(PROVENANCES)}", field="provenance")
    out = {}
    for f in SCHEMA[kind]:
        raw = (values or {}).get(f["key"])
        blank = raw is None or (isinstance(raw, str) and not raw.strip())
        if f.get("choices"):
            if blank or raw not in f["choices"]:
                raise LibraryError(f"{f['label']}: choose one of {', '.join(f['choices'])}", field=f["key"])
            out[f["key"]] = dict(v=raw, u=f["units"], d=f["d"], s=source, t=provenance)
            continue
        if f.get("choices_from"):
            role = f["choices_from"]
            if blank:
                raise LibraryError(f"{f['label']} is required", field=f["key"])
            if known is not None and raw not in known.get(role, ()):
                raise LibraryError(f"{f['label']}: '{raw}' is not a{'n' if role == 'oxidizer' else ''} "
                                   f"{'oxidiser' if role == 'oxidizer' else 'fuel'} in the library", field=f["key"])
            out[f["key"]] = dict(v=raw, u="-", d=f["d"], s=source, t=provenance)
            continue
        if f.get("text"):
            if blank and f["required"]:
                raise LibraryError(f"{f['label']} is required", field=f["key"])
            out[f["key"]] = dict(v="" if blank else str(raw).strip(), u="-", d=f["d"], s=source, t=provenance)
            continue
        if blank:
            if f["required"]:
                raise LibraryError(f"{f['label']} is required", field=f["key"])
            if f.get("default") is not None:
                out[f["key"]] = dict(v=f["default"] * f["factor"], u=f["units"], d=f["d"],
                                     s=f"Default of the add-entry form: {f['default_why']}", t="assumed")
            else:
                out[f["key"]] = dict(v=None, u=f["units"], d=f["d"], s="Left blank in the add-entry form",
                                     t=provenance)
            continue
        try:
            x = float(raw)
        except (TypeError, ValueError):
            raise LibraryError(f"{f['label']}: {raw!r} is not a number", field=f["key"]) from None
        lo, hi = f.get("range", (None, None))
        if lo is not None and not lo <= x <= hi:
            raise LibraryError(f"{f['label']} of {x:g} {f['shown']} is outside the range this form accepts, "
                               f"{lo:g} to {hi:g} {f['shown']}. Check the units.", field=f["key"])
        out[f["key"]] = dict(v=x * f["factor"], u=f["units"], d=f["d"], s=source, t=provenance)
    # the relations between fields, where one alone cannot be judged
    if kind == "propellant":
        k = out["tank_mer_per_kg"]["v"]
        out["tank_mer_ref_density"] = dict(
            v=out["density_kg_m3"]["v"] if k is not None else None, u="kg/m^3",
            d="Density at which the tank relation is valid; taken as this propellant's own density",
            s=source if k is not None else "No tank relation given", t=provenance)
    if kind == "solid":
        out["source"] = dict(v=source, u="-", d="Provenance", s=source, t=provenance)
        if (out["c_star_mps"]["v"] is None) != (out["burn_rate_exponent"]["v"] is None):
            raise LibraryError("give c* and the burn-rate exponent together, or neither: the internal ballistics "
                               "needs both, and nothing else reads them",
                               field="c_star_mps" if out["c_star_mps"]["v"] is None else "burn_rate_exponent")
    if kind == "combination" and out["oxidizer"]["v"] == out["fuel"]["v"]:
        raise LibraryError("the fuel and the oxidiser must be different propellants", field="fuel")
    if kind == "material":
        y = out["yield_min_Pa"]["v"]
        if out["sigma_allow_Pa"]["v"] is None:
            out["sigma_allow_Pa"] = dict(v=0.633 * y, u="Pa", d=out["sigma_allow_Pa"]["d"],
                                         s="0.633 x the minimum yield given, the basis of every shipped material "
                                           "(config/engineering_assumptions.yaml, tank_materials)", t="assumed")
        elif out["sigma_allow_Pa"]["v"] > y:
            raise LibraryError("the allowable stress cannot exceed the minimum yield strength", field="sigma_allow_Pa")
    return out


def add(kind: str, name: str, values: dict, source: str, provenance: str = "user", replace: bool = False,
        assump_path: str | None = None, path: str | None = None) -> dict:
    """Add (or, with replace, change) one entry in the personal library. Returns the entry written."""
    name = str(name or "").strip()
    if not NAME_RE.match(name):
        raise LibraryError("the name must start with a letter or digit and use only letters, digits, spaces and "
                           "- _ + ( ) / , (no dots or brackets, which would break the input paths), at most "
                           "48 characters", field="entry_name")
    sec = SECTIONS.get(kind)
    if sec is None:
        raise LibraryError(f"unknown kind of entry {kind!r}")
    if name in shipped_names(assump_path or os.path.join(ROOT, "config", "engineering_assumptions.yaml"), sec):
        raise LibraryError(f"'{name}' is already in the shipped library. Choose another name, or change the "
                           f"shipped entry's values in its own fields in the input panel.", field="entry_name")
    doc = load(path)
    if name in doc.get(sec, {}) and not replace:
        raise LibraryError(f"you already have an entry called '{name}'", field="entry_name")
    entry = build_entry(kind, values, source, provenance,
                        known=liquids(assump_path, path) if kind == "combination" else None)
    doc.setdefault(sec, {})[name] = entry
    _write(doc, path)
    return entry


def remove(kind: str, name: str, path: str | None = None) -> bool:
    sec = SECTIONS.get(kind)
    doc = load(path)
    if not sec or name not in doc.get(sec, {}):
        return False
    del doc[sec][name]
    _write(doc, path)
    return True


def listing(path: str | None = None) -> dict:
    """{kind: [{name, values (in the form's units), source, provenance}]} for the GUI."""
    # (the solid propellant's `source` leaf is the entry's provenance record, not a form field)
    doc = load(path)
    out = {}
    for kind, sec in SECTIONS.items():
        rows = []
        for name, entry in (doc.get(sec) or {}).items():
            vals = {}
            for f in SCHEMA[kind]:
                leaf = entry.get(f["key"]) or {}
                v = leaf.get("v") if isinstance(leaf, dict) else leaf
                if isinstance(v, (int, float)) and not isinstance(v, bool) and f.get("factor"):
                    v = v / f["factor"]
                vals[f["key"]] = v
            first = next((x for x in entry.values() if isinstance(x, dict) and x.get("t") != "assumed"), {})
            rows.append(dict(name=name, values=vals, source=first.get("s", ""), provenance=first.get("t", "user")))
        out[kind] = rows
    return out


def liquids(assump_path: str | None = None, path: str | None = None) -> dict:
    """{"fuel": names, "oxidizer": names} of the liquid propellants, shipped and your own, that a combination may name."""
    from .config_io import _Loader
    p = assump_path or os.path.join(ROOT, "config", "engineering_assumptions.yaml")
    with open(p, encoding="utf-8") as fh:
        doc = yaml.load(fh, Loader=_Loader) or {}
    props = dict(doc.get("propellants") or {})
    props.update(load(path).get("propellants") or {})
    out = {"fuel": [], "oxidizer": []}
    for name, e in props.items():
        role = (e.get("role") or {}).get("v") if isinstance(e.get("role"), dict) else e.get("role")
        for r in (("fuel", "oxidizer") if role is None else (role,)):
            if r in out:
                out[r].append(name)
    return {k: sorted(v) for k, v in out.items()}


def schema_for_gui(assump_path: str | None = None) -> dict:
    """The form fields for the page, with a combination's fuel and oxidiser lists filled from the library."""
    liq = liquids(assump_path)
    out = {}
    for kind, fields in SCHEMA.items():
        rows = []
        for f in fields:
            g = {k: f[k] for k in ("key", "label", "shown", "required", "default", "range", "choices", "text", "d")
                 if k in f}
            if f.get("choices_from"):
                g["choices"] = liq[f["choices_from"]]
            rows.append(g)
        out[kind] = rows
    return out


# --------------------------------------------------------------------------- merging into a design
#: the top-level blocks of the assumptions file; a design's `library:` block may carry a changed copy of any
ASSUMPTION_BLOCKS = ("earth_model", "mer", "propellants", "propellant_combinations", "solid_propellants",
                     "tank_materials", "convergence", "mer_scatter")


def extra_entries(design_block: dict | None, path: str | None = None) -> dict:
    """The entries to merge into the shipped library for one design: the personal library, overlaid by the
    copies the design itself carries (its `library:` block), which win."""
    out = {}
    for sec, entries in load(path).items():
        out.setdefault(sec, {}).update(copy.deepcopy(entries))
    for sec, entries in (design_block or {}).items():
        if sec in ASSUMPTION_BLOCKS and isinstance(entries, dict):
            out.setdefault(sec, {}).update(copy.deepcopy(entries))
    return out


def merge(assump_raw: dict, extra: dict) -> dict:
    """Merge extra entries into an annotated assumptions document, in place. A design's copy of a shipped entry
    replaces it entry by entry, field by field: only the fields the copy states are changed."""
    for sec, entries in (extra or {}).items():
        target = assump_raw.setdefault(sec, {})
        for name, entry in entries.items():
            if name in target and isinstance(target[name], dict):
                merged = copy.deepcopy(target[name])
                merged.update(entry)
                target[name] = merged
            else:
                target[name] = entry
    return assump_raw


def used_names(design_raw: dict) -> dict:
    """{section: names} of the library entries an annotated design refers to."""
    def v(node):
        return node.get("v") if isinstance(node, dict) else node
    props, mats, solids, combos = set(), set(), set(), set()
    for sd in design_raw.get("stages") or []:
        for k in ("fuel", "oxidizer"):
            if v(sd.get(k)):
                props.add(v(sd.get(k)))
        if v(sd.get("propellant")):
            solids.add(v(sd.get("propellant")))
        if v(sd.get("propellant_combination")):
            combos.add(v(sd.get("propellant_combination")))
        tk = sd.get("tank") or {}
        if v(tk.get("material")):
            mats.add(v(tk.get("material")))
    b = design_raw.get("boosters") or {}
    for k in ("fuel", "oxidizer"):
        if v(b.get(k)):
            props.add(v(b.get(k)))
    if v(b.get("propellant")):
        solids.add(v(b.get("propellant")))
    return {"propellants": props, "tank_materials": mats, "solid_propellants": solids,
            "propellant_combinations": combos}


def embed_used(design_raw: dict, path: str | None = None) -> list:
    """Copy every personal-library entry the design uses into its `library:` block. Returns the names copied."""
    lib = load(path)
    used = used_names(design_raw)
    # a combination of your own names its fuel and oxidiser, which the design then needs as well
    for c in list(used["propellant_combinations"]):
        entry = (lib.get("propellant_combinations") or {}).get(c) or {}
        for k in ("fuel", "oxidizer"):
            leaf = entry.get(k)
            if isinstance(leaf, dict) and leaf.get("v"):
                used["propellants"].add(leaf["v"])
    copied = []
    for sec, names in used.items():
        for name in sorted(names):
            if name in (lib.get(sec) or {}):
                design_raw.setdefault("library", {}).setdefault(sec, {})[name] = copy.deepcopy(lib[sec][name])
                copied.append(name)
    return copied
