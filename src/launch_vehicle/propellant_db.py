"""Propellant combinations: mixture ratio, bulk density, and what the chemistry can actually give.

A stage may name a combination instead of spelling out its propellants:

    propellant_combination: {v: "LOX/RP-1", u: '-', d: "...", s: "...", t: user}

which fills `fuel`, `oxidizer` and `mixture_ratio_OF` where the stage does not state them. The rules are the
engine database's rules, for the same reason: the library only ever FILLS what the design left out, anything
the design states wins, every filled value enters the input register with the library entry's own source, and
a stage that names a combination and then declares a different propellant is reported rather than silently
accepted - that is nearly always a template left half-edited.

Two mixture ratios, deliberately kept apart
-------------------------------------------
`of_ratio_optimum` maximises Isp. `of_ratio_flight` is what engines of that combination actually run, each one
named in the library's source string. They are not the same number and the gap can be large: for LOX/LH2 the
Isp peak is near O/F 4.0 (book Table 4.10, p.240) while the J-2 flew at 5.50 (Table 4.12, p.242), because
hydrogen engines run fuel-rich to hold turbine and chamber temperatures down. `of_ratio_flight` is what gets
filled into a stage; a design that wants the thermochemical optimum must ask for it.

Bulk density
------------
`bulk_density_kg_m3` is computed from the component densities and the mixture ratio, never read from the
library. The book prints a specific gravity for each Table 4.10 row, and the computed value is checked against
it (tests/test_propellant_combinations.py) - which is how the Aerozine-50 density misprint in Table 4.6 shows
up independently: Table 4.10's own printed 1.21 is unreachable from Table 4.6's 1,450 kg/m^3.
"""
from __future__ import annotations

from dataclasses import dataclass


class PropellantDBError(ValueError):
    pass


@dataclass
class Combination:
    """One oxidiser/fuel pair with its mixture ratios and reference thermochemistry."""
    name: str
    oxidizer: str
    fuel: str
    of_ratio_flight: float | None = None
    of_ratio_optimum: float | None = None
    of_ratio_optimum_frozen: float | None = None
    isp_ref_s: float | None = None
    isp_ref_frozen_s: float | None = None
    cstar_ref_mps: float | None = None
    Tc_ref_K: float | None = None
    mw_ref_kg_kmol: float | None = None
    bulk_sg_book: float | None = None
    source: str = ""

    @property
    def of_ratio(self) -> float | None:
        """The ratio a stage gets: what engines run, falling back to the thermochemical optimum."""
        return self.of_ratio_flight if self.of_ratio_flight is not None else self.of_ratio_optimum


_FIELDS = ("of_ratio_flight", "of_ratio_optimum", "of_ratio_optimum_frozen", "isp_ref_s",
           "isp_ref_frozen_s", "cstar_ref_mps", "Tc_ref_K", "mw_ref_kg_kmol")


def _v(block: dict, key: str):
    leaf = block.get(key)
    return leaf.get("v") if isinstance(leaf, dict) else leaf


#: the leaf whose source string best describes where a combination's mixture ratio came from, in order
_SOURCE_KEYS = ("of_ratio_flight", "of_ratio_optimum", "oxidizer")


def _source_for(name: str, blk: dict, reg) -> str:
    """Find the entry's source, whether the assumptions came in wrapped or already unwrapped.

    Read straight from the YAML the sources sit on the leaves as `s`. Loaded through
    config_io.load_yaml_annotated they have been moved into the input register instead, so look there too -
    otherwise a filled value would be recorded with no provenance, which is the one thing this tool must not do.
    """
    for key in _SOURCE_KEYS:
        leaf = blk.get(key)
        if isinstance(leaf, dict) and leaf.get("s"):
            return leaf["s"]
    for key in _SOURCE_KEYS:
        want = f"propellant_combinations.{name}.{key}"
        for row in reg or []:
            if row.get("path") == want and row.get("source"):
                return row["source"]
    return ""


def load(assump: dict, reg=None) -> dict:
    """Build {name: Combination} from an assumptions dict, wrapped or unwrapped. Absent block = none."""
    out = {}
    for name, blk in (assump.get("propellant_combinations") or {}).items():
        ox, fu = _v(blk, "oxidizer"), _v(blk, "fuel")
        if not ox or not fu:
            raise PropellantDBError(f"propellant combination '{name}' must name an oxidizer and a fuel")
        kw = {f: _v(blk, f) for f in _FIELDS}
        out[name] = Combination(name=name, oxidizer=ox, fuel=fu, bulk_sg_book=_v(blk, "bulk_sg"),
                                source=_source_for(name, blk, reg), **kw)
    return out


def find(name: str, combos: dict) -> Combination:
    for key, c in combos.items():
        if key.lower() == str(name).lower():
            return c
    raise PropellantDBError(f"no propellant combination '{name}'. Available: {', '.join(sorted(combos))}")


def find_by_pair(oxidizer: str, fuel: str, combos: dict):
    """The library entry for an oxidiser/fuel pair, however the stage happened to specify it.

    A stage that spells out LOX and RP-1 by hand gets the same reference thermochemistry as one that names the
    combination; the data describes the chemistry, not the way the YAML was written.
    """
    ox, fu = str(oxidizer).lower(), str(fuel).lower()
    for c in combos.values():
        if c.oxidizer.lower() == ox and c.fuel.lower() == fu:
            return c
    return None


def bulk_density_kg_m3(comb: Combination, propellants: dict, of_ratio: float | None = None):
    """Density of the loaded propellant as a whole: (1+r) / (r/rho_ox + 1/rho_fuel).

    This is the volume-weighted density that actually sets tank size, and it is COMPUTED rather than read, so
    it cannot disagree with the densities the tanks are sized from. Returns None if either propellant is
    missing from the library or the mixture ratio is unknown.
    """
    r = of_ratio if of_ratio is not None else comb.of_ratio
    ox, fu = propellants.get(comb.oxidizer), propellants.get(comb.fuel)
    if r is None or ox is None or fu is None:
        return None
    rho_ox = getattr(ox, "density_kg_m3", None) or (ox.get("density_kg_m3") if isinstance(ox, dict) else None)
    rho_fu = getattr(fu, "density_kg_m3", None) or (fu.get("density_kg_m3") if isinstance(fu, dict) else None)
    if not rho_ox or not rho_fu or r <= 0:
        return None
    return (1.0 + r) / (r / rho_ox + 1.0 / rho_fu)


def density_impulse_s_kg_m3(comb: Combination, propellants: dict, isp_s: float | None = None):
    """Density impulse rho_bulk x Isp: the figure of merit that decides tank volume, not just mass."""
    rho = bulk_density_kg_m3(comb, propellants)
    isp = isp_s if isp_s is not None else comb.isp_ref_s
    return None if (rho is None or isp is None) else rho * isp


# ------------------------------------------------------------------------- expansion into a design
FILLED_FIELDS = ("fuel", "oxidizer", "mixture_ratio_OF")


def expand_design(design: dict, assump: dict, reg: list) -> list:
    """Resolve every `propellant_combination` reference in a loaded design. Returns one note each.

    Called from config_io after the YAML is unwrapped and before the spec is built, so filled values go through
    exactly the same validation as hand-written ones.
    """
    combos = load(assump, reg)
    notes = []
    for i, sd in enumerate(design.get("stages") or []):
        ref = sd.get("propellant_combination")
        ref = ref.get("v") if isinstance(ref, dict) else ref
        if not ref:
            continue
        if sd.get("stage_type", "liquid") == "solid":
            raise PropellantDBError(f"stages.{i}: a solid stage has no oxidiser/fuel pair, so it cannot name "
                                    f"a propellant combination ('{ref}')")
        c = find(ref, combos)
        filled, mismatched, missing = [], [], []
        for key, val, what in (("fuel", c.fuel, "fuel"), ("oxidizer", c.oxidizer, "oxidizer"),
                               ("mixture_ratio_OF", c.of_ratio, "mixture ratio")):
            if sd.get(key) is not None:
                have = sd[key]
                if key != "mixture_ratio_OF" and val is not None and str(have).lower() != str(val).lower():
                    mismatched.append(dict(field=key, design=have, combination=val))
                continue
            if val is None:
                missing.append(key)
                continue
            sd[key] = val
            filled.append(key)
            reg.append(dict(path=f"stages.{i}.{key}", value=val,
                            units="-" if key != "mixture_ratio_OF" else "-",
                            description=f"filled from propellant combination '{c.name}' ({what})",
                            source=f"propellant combination library: {c.source}" if c.source else
                                   f"propellant combination library entry '{c.name}'",
                            provenance="reference"))
        notes.append(dict(context=f"stages.{i}", entry=c.name, filled=filled, mismatched=mismatched,
                          missing=missing, of_ratio=c.of_ratio, of_ratio_optimum=c.of_ratio_optimum,
                          source=c.source))
    return notes
