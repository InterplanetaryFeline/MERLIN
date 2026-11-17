"""Switching a stage between liquid and solid.

This is the one GUI edit that cannot be an override. Every other control changes a leaf's VALUE; a liquid
stage and a solid stage are different documents. A liquid stage carries `fuel`, `oxidizer`, `mixture_ratio_OF`
and the `engine` and `tank` blocks; a solid stage carries `propellant` and a `motor` block instead, and three
of the shared leaves take different values for a good reason - a cast grain has no residual, no loading margin
and no start-up transient (book p.489), where a liquid stage has all three. So the switch adds and removes
keys, which means transforming the annotated document and reloading it.

WHERE THE NEW BLOCK COMES FROM, which is the part worth being careful about.

Not from a template written here. The blocks are lifted from the shipped designs - the liquid one from
config/default_design.yaml, the solid one from examples/example_solid_smallsat.yaml - because those blocks are
real, already load, already size, and already carry their own units, descriptions, sources and provenance
tags. A hand-written template in this module would be a second set of numbers to keep in step with the book,
and the first thing to go stale. Grafting from a shipped file means a converted stage is annotated exactly as
if the user had started from that example.

What survives the switch is everything that is not about the propulsion: the stage's name, its diameter, its
structure mode, its separation hardware, its margins and its layout ratios. Those are the user's decisions and
they are kept, with their own provenance, so converting a stage does not quietly reset the geometry.
"""
from __future__ import annotations
import copy
import os

import yaml

from .paths import ROOT                                   # noqa: E402

#: where each type's donor block is read from. Both are shipped, both are covered by the test suite already.
DONORS = {
    "liquid": os.path.join(ROOT, "config", "default_design.yaml"),
    "solid": os.path.join(ROOT, "examples", "example_solid_smallsat.yaml"),
}

#: keys that belong to a liquid stage and must go when it becomes solid
LIQUID_KEYS = ("fuel", "oxidizer", "mixture_ratio_OF", "propellant_combination", "engine", "tank",
               "feed_system_mass_per_engine_kg", "pressurant_mass_fraction_of_propellant")
#: keys that belong to a solid stage and must go when it becomes liquid
SOLID_KEYS = ("propellant", "motor")
#: shared keys whose VALUE is type-dependent, so they are taken from the donor rather than carried over.
#: A cast grain burns to completion and lights instantly; a liquid stage does neither (book p.489).
TYPE_DEPENDENT_KEYS = ("residual_fraction", "loading_margin_fraction", "startup_time_s")
#: blocks that exist for both types but whose CONTENTS differ. `layout` is the one: a liquid stage needs
#: `intertank_over_D` for the gap between its two tanks, and a solid stage has no such gap and no such key.
#: These are merged - the donor supplies what is missing, the user keeps every ratio they had set - because
#: replacing the block outright would throw away skirt and interstage choices that survive the switch fine.
MERGED_BLOCKS = ("layout",)

TYPES = ("liquid", "solid")


class StageTypeError(ValueError):
    pass


def _load_annotated(path: str) -> dict:
    from .config_io import _Loader
    with open(path, encoding="utf-8") as fh:
        return yaml.load(fh, Loader=_Loader)


def _leaf(v, units="-", desc="", source="", tag="user"):
    return {"v": v, "u": units, "d": desc, "s": source, "t": tag}


def current_type(stage: dict) -> str:
    """What this stage is now, read the way config_io reads it."""
    st = stage.get("stage_type")
    st = st.get("v") if isinstance(st, dict) else st
    if st in TYPES:
        return st
    # no stage_type key at all: a liquid stage, which is what every design that predates the key is
    return "solid" if ("motor" in stage or "propellant" in stage) else "liquid"


def donor_stage(to: str, donor_path: str | None = None) -> dict:
    """The first stage of the donor design for type `to`, as an annotated block."""
    if to not in TYPES:
        raise StageTypeError(f"stage type must be one of {TYPES}, not {to!r}")
    path = donor_path or DONORS[to]
    doc = _load_annotated(path)
    stages = doc.get("stages") or []
    if not stages:
        raise StageTypeError(f"donor design {path} has no stages")
    for sd in stages:
        if current_type(sd) == to:
            return copy.deepcopy(sd)
    raise StageTypeError(f"donor design {path} has no {to} stage to copy from")


def convert_stage(doc: dict, index: int, to: str, donor_path: str | None = None) -> dict:
    """Convert stage `index` of the annotated design `doc` to type `to`, in place. Returns a note.

    The note lists exactly what was removed, what was added and what was carried over, so the GUI can tell
    the user what just happened to their stage instead of silently rewriting it.
    """
    if to not in TYPES:
        raise StageTypeError(f"stage type must be one of {TYPES}, not {to!r}")
    stages = doc.get("stages")
    if not isinstance(stages, list) or not 0 <= index < len(stages):
        raise StageTypeError(f"this design has no stage {index}")
    stage = stages[index]
    was = current_type(stage)
    if was == to:
        return {"index": index, "was": was, "now": to, "changed": False,
                "removed": [], "added": [], "kept": sorted(k for k in stage if k != "stage_type"),
                "note": f"stage {index + 1} is already {to}"}

    donor = donor_stage(to, donor_path)
    drop = SOLID_KEYS if to == "liquid" else LIQUID_KEYS
    take = LIQUID_KEYS if to == "liquid" else SOLID_KEYS

    removed = [k for k in drop if k in stage]
    for k in removed:
        del stage[k]

    added = []
    for k in list(take) + list(TYPE_DEPENDENT_KEYS):
        if k in donor:
            stage[k] = copy.deepcopy(donor[k])
            added.append(k)
    # fill in only the sub-keys the new type needs and this stage does not have yet
    filled_in = []
    for block in MERGED_BLOCKS:
        src = donor.get(block)
        if not isinstance(src, dict):
            continue
        dst = stage.get(block)
        if not isinstance(dst, dict):
            stage[block] = copy.deepcopy(src)
            added.append(block)
            continue
        for k, v in src.items():
            if k not in dst:
                dst[k] = copy.deepcopy(v)
                filled_in.append(f"{block}.{k}")
    # the stage's own name survives, so the user still recognises it; only the type label is rewritten
    stage["stage_type"] = _leaf(to, "-", "liquid | solid", "Set in the GUI", "user")

    kept = sorted(k for k in stage if k not in added and k != "stage_type")
    return {"index": index, "was": was, "now": to, "changed": True,
            "removed": removed, "added": sorted(added), "filled_in": sorted(filled_in), "kept": kept,
            "donor": os.path.relpath(donor_path or DONORS[to], ROOT).replace(os.sep, "/"),
            "note": (f"stage {index + 1} converted from {was} to {to}: "
                     f"{len(removed)} block(s) removed, {len(added)} added from the shipped "
                     f"{to} example, {len(kept)} of your own settings kept")}
