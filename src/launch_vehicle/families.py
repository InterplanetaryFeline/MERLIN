"""Launch vehicle families: one core, several strap-on counts, a published figure for each.

Real launchers are sold as families. Delta II's 7320, 7420 and 7920 fly the same first stage and the same
second stage and differ only in how many GEM-40s are bolted to them; Ariane 62 and 64 share the LLPM core and
the Vinci upper stage. That shape matters to this tool for two reasons:

  * It is the architecture trade of `architecture.py` as it occurs in the wild, so a family folder is the
    natural place to keep the variants a user wants to compare.
  * It is the one configuration where the tool's hardest limitation is CHECKABLE against data. A sizer that
    gives every stage its own share of the delta-v must under-predict the smaller members of a shared-core
    family, because their real core is sized for the largest member's mission (docs/ACCURACY.md 6b.3). With
    the published figure for each variant stored beside the designs, that is a measurement the tool makes on
    itself rather than a claim in a document.

**A variant is a base design plus overrides, not a copy of it.** Writing each variant as a standalone YAML
would duplicate three hundred lines three times and let the "shared" core drift apart silently - the family
property would be an aspiration rather than a fact. Here the variants literally load the same base file, so
sharing the core is structural: change the base and every variant changes with it. The overrides are the
dotted paths `config_io.deep_set` already understands, which is also exactly what the GUI passes when it
opens a design with unsaved edits, so a variant needs no new machinery to be openable.

**Where families live.** Any search directory may hold a `families/` directory, and each subdirectory of that
with a `family.yaml` in it is a family. Users add their own by making a folder and writing the manifest; there
is nothing to register.

A manifest, in full:

    family:
      name: Delta II 7000 series            # what to call it
      note: ...                             # what the variants share, in one line
      base: ../../delta2_7920.yaml          # relative to the manifest; the design every variant starts from
      reference: "7920"                     # the variant whose hardware an architecture trade pins
      variants:
        "7320":
          label: Delta II 7320 (3 x GEM-40)
          overrides:
            boosters.n_total: 3
            boosters.n_ground_lit: 3
            mission.payload_mass_kg: 2800.0
          published:                        # annotated like any other sourced input: {v,u,d,s,t}
            glom_kg: {v: 152000.0, u: kg, d: Published lift-off mass, s: ..., t: reference}

`name`, `label`, `base`, `reference` and the override paths are structure rather than engineering inputs, so
they are plain YAML, the way `meta:` and `trade_study:` are. Everything under `published:` is a measured
quantity the tool will be scored against, so it carries the same five documentation keys every sourced input
in this project carries, and `t` must be `reference` - a published figure that is really an assumption is how
a validation set quietly starts grading itself against its own guesses.
"""
from __future__ import annotations
import os

import yaml

from .config_io import PROVENANCE, REQUIRED, _Loader, deep_set, load_design

MANIFEST = "family.yaml"
FAMILIES_DIR = "families"


class FamilyError(ValueError):
    """A family manifest does not describe a family that can be built."""


class Variant:
    """One member of a family: the base design, plus what makes it this member."""

    def __init__(self, key, label, overrides, published, family):
        self.key, self.label, self.overrides, self.published = key, label, overrides, published
        self.family = family

    @property
    def base_path(self):
        return self.family.base_path

    @property
    def is_reference(self):
        return self.key == self.family.reference

    def spec(self, assumptions, extra_overrides=None):
        """The variant as a VehicleSpec. `extra_overrides` wins, so a study can vary a variant further."""
        ov = dict(self.overrides)
        ov.update(extra_overrides or {})
        return load_design(self.base_path, assumptions, ov)

    def published_kg(self, key):
        node = self.published.get(key)
        return None if node is None else float(node["v"])

    def published_source(self, key):
        node = self.published.get(key)
        return "" if node is None else str(node["s"])

    def __repr__(self):
        return f"Variant({self.key!r}, {self.label!r})"


class Family:
    """A manifest, read and checked."""

    def __init__(self, path, name, note, base, reference, variants_raw):
        self.path = path                                  # the manifest file
        self.dir = os.path.dirname(path)
        self.name = name
        self.note = note
        self.base = base                                  # as written, relative to the manifest
        self.base_path = os.path.normpath(os.path.join(self.dir, base))
        self.reference = reference
        self.variants = [Variant(k, v.get("label") or k, v.get("overrides") or {},
                                 v.get("published") or {}, self) for k, v in variants_raw.items()]

    @property
    def slug(self):
        return os.path.basename(self.dir)

    def variant(self, key):
        for v in self.variants:
            if v.key == key:
                return v
        raise FamilyError(f"family '{self.name}' has no variant {key!r}; it has "
                          f"{', '.join(repr(v.key) for v in self.variants)}")

    @property
    def reference_variant(self):
        return self.variant(self.reference)

    def __repr__(self):
        return f"Family({self.name!r}, {len(self.variants)} variants)"


def _check_published(block, where):
    """A published figure is a sourced input, so it carries the same five keys every sourced input does."""
    out = {}
    for key, node in (block or {}).items():
        if not isinstance(node, dict) or "v" not in node:
            raise FamilyError(f"{where}: published '{key}' must be annotated {{v, u, d, s, t}}, not a bare "
                              f"value - a figure the tool is scored against has to say where it came from")
        missing = [k for k in REQUIRED if k not in node]
        if missing:
            raise FamilyError(f"{where}: published '{key}' is missing documentation keys {missing}")
        if node["t"] not in PROVENANCE:
            raise FamilyError(f"{where}: published '{key}' provenance 't' must be one of {PROVENANCE}, "
                              f"got {node['t']!r}")
        if node["t"] != "reference":
            raise FamilyError(f"{where}: published '{key}' is marked '{node['t']}', but a figure the tool is "
                              f"MEASURED against must be 'reference'. An assumed figure makes the validation "
                              f"set grade itself against its own guess")
        if not str(node["s"]).strip():
            raise FamilyError(f"{where}: published '{key}' has an empty source")
        out[key] = node
    return out


def load_manifest(path) -> Family:
    """Read and check one `family.yaml`."""
    with open(path, encoding="utf-8") as fh:
        doc = yaml.load(fh, Loader=_Loader) or {}
    fam = doc.get("family")
    if not isinstance(fam, dict):
        raise FamilyError(f"{path}: no 'family:' block")
    for key in ("name", "base", "variants"):
        if not fam.get(key):
            raise FamilyError(f"{path}: family is missing '{key}'")
    variants = fam["variants"]
    if not isinstance(variants, dict) or len(variants) < 2:
        raise FamilyError(f"{path}: a family needs at least two variants, as a mapping of key -> variant; "
                          f"one vehicle on its own is a design, not a family")
    base_path = os.path.normpath(os.path.join(os.path.dirname(path), fam["base"]))
    if not os.path.isfile(base_path):
        raise FamilyError(f"{path}: base design '{fam['base']}' does not exist (looked in {base_path})")
    ref = fam.get("reference")
    if ref is not None and ref not in variants:
        raise FamilyError(f"{path}: reference {ref!r} is not one of the variants "
                          f"({', '.join(map(repr, variants))})")
    clean = {}
    for key, v in variants.items():
        if not isinstance(v, dict):
            raise FamilyError(f"{path}: variant {key!r} must be a mapping")
        ov = v.get("overrides") or {}
        if not isinstance(ov, dict):
            raise FamilyError(f"{path}: variant {key!r}: 'overrides' must be a mapping of dotted path -> value")
        clean[str(key)] = dict(label=v.get("label"), overrides=ov,
                               published=_check_published(v.get("published"), f"{path}: variant {key!r}"))
    return Family(path, fam["name"], fam.get("note") or "", fam["base"], ref, clean)


def discover(root, search_dirs=("designs", "examples", "validation")) -> list:
    """Every family under `<root>/<dir>/families/*/family.yaml`, sorted by name."""
    out = []
    for d in search_dirs:
        base = os.path.join(root, d, FAMILIES_DIR)
        if not os.path.isdir(base):
            continue
        for sub in sorted(os.listdir(base)):
            manifest = os.path.join(base, sub, MANIFEST)
            if os.path.isfile(manifest):
                out.append(load_manifest(manifest))
    return sorted(out, key=lambda f: f.name)


def find(root, key, search_dirs=("designs", "examples", "validation")) -> Family:
    """One family by slug or by name, case-insensitively."""
    fams = discover(root, search_dirs)
    k = str(key).strip().lower()
    for f in fams:
        if f.slug.lower() == k or f.name.lower() == k:
            return f
    raise FamilyError(f"no family {key!r}; found {', '.join(f.slug for f in fams) or 'none'}")


# --------------------------------------------------------------------------- the measurement
def size_family(family: Family, assumptions, optimise: bool = True) -> list:
    """Size every variant on its own and score it against its published figures.

    `optimise` re-optimises each variant's delta-v split before sizing, which is the basis
    `docs/ACCURACY.md` §2 and `tools/attribute_error.py` report on, so the numbers are comparable with the
    rest of the validation set.

    Each row carries the variant, the result (or the error that stopped it), and the GLOM error against the
    published lift-off mass. Sizing every member separately is the point: a shared-core family is where that
    assumption is wrong in a way the published figures can see.
    """
    from . import optimization
    from .convergence import SizingError, size_vehicle
    rows = []
    for v in family.variants:
        row = dict(variant=v, key=v.key, label=v.label, is_reference=v.is_reference,
                   published_glom_kg=v.published_kg("glom_kg"),
                   published_payload_kg=v.published_kg("payload_kg"),
                   result=None, glom_err=None, error="")
        try:
            spec = v.spec(assumptions)
            if optimise:
                opt = optimization.optimize_dv_split(spec)
                spec = v.spec(assumptions, {"vehicle.dv_fractions": opt["fractions"]})
            row["result"] = res = size_vehicle(spec, keep_history=False)
            if row["published_glom_kg"]:
                row["glom_err"] = res.glom_kg / row["published_glom_kg"] - 1.0
        except (SizingError, FamilyError, ValueError) as ex:
            row["error"] = str(ex)
        rows.append(row)
    return rows


def pinned_family(family: Family, assumptions, orbit=None) -> list:
    """Pin the reference variant's hardware and ask it for every other variant's architecture.

    This is `architecture.payload_for_architecture` applied along a family, and it is the measurement
    docs/ACCURACY.md 6b.5 reports: the published payload of each variant against what the reference
    variant's core delivers with that variant's booster count. It needs the variants to differ by
    `boosters.n_total`, which is what makes them a family in the first place.
    """
    from . import architecture as arch
    from .convergence import SizingError, size_vehicle
    ref = family.reference_variant
    base = size_vehicle(ref.spec(assumptions), keep_history=False)
    pv = arch.pin(base)
    rows = []
    for v in family.variants:
        n = v.overrides.get("boosters.n_total")
        row = dict(variant=v, key=v.key, label=v.label, is_reference=v.is_reference, n_boosters=n,
                   published_payload_kg=v.published_kg("payload_kg"), payload_kg=None, glom_kg=None,
                   liftoff_tw=None, payload_err=None, flyable=True, reason="")
        if n is None:
            row.update(flyable=False, reason=f"variant {v.key!r} does not override 'boosters.n_total', so "
                                             f"there is no booster count to pin the reference core against")
            rows.append(row)
            continue
        try:
            out = arch.payload_for_architecture(pv, n_total=int(n),
                                                n_ground_lit=v.overrides.get("boosters.n_ground_lit"),
                                                orbit=orbit)
        except (arch.ArchitectureError, SizingError, ValueError) as ex:
            row.update(flyable=False, reason=str(ex))
            rows.append(row)
            continue
        row.update(flyable=out.flyable, reason=out.reason, payload_kg=out.payload_kg,
                   glom_kg=out.glom_kg, liftoff_tw=out.liftoff_tw)
        if out.payload_kg is not None and row["published_payload_kg"]:
            row["payload_err"] = out.payload_kg / row["published_payload_kg"] - 1.0
        rows.append(row)
    return rows
