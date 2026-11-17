"""Giving a design strap-on boosters, or taking them away.

The model has supported strap-ons for a long time: Ariane 5 ECA, Atlas V 551, Delta II 7920, Delta IV Heavy,
H-IIA 202 and Soyuz-2.1b are all check cases, and the GUI renders all 32 booster fields properly - *if the
design already has a `boosters:` block*. If it does not, there was no way in. The browser can only edit what
the file contains, so a user starting from the shipped default could not add boosters at all, and a user who
opened Ariane 5 could not take them off. That is the same gap the stage count had, and it is fixed the same
way: by transforming the annotated document and handing back a draft.

This one is simpler than the stage count in the way that matters. The `boosters:` block is **self-contained** -
nothing outside it refers to the boosters, and `attach_stage` is pinned to 1 by validation (BOOSTSTAGE) in
this version - so adding or removing it moves nothing else in the design. There is no delta-v split to
rebalance and no index to clamp.

WHERE A BLOCK COMES FROM, which is the part worth being careful about: a shipped design, as always, never a
template written here. Both donors are chosen to be the most modest strap-on of their kind in the set, so
that grafting onto an arbitrary core has the best chance of sizing rather than immediately refusing:

  * solid  - `examples/example_boosters.yaml`, a generic GEM-class motor, 17 t of propellant at 1.2 m.
  * liquid - `validation/soyuz2_1b.yaml`, 39 t at 2.68 m. Delta IV Heavy was the obvious liquid candidate
    and is the wrong one: its Common Booster Cores carry 200 t each at 5.1 m, and grafted onto a core any
    smaller than Delta IV's own they drive the first stage out of propellant before the boosters are done.
    Measured, not assumed - that graft is the one combination of the four tried that would not size.

The donor's numbers arrive with the donor's own provenance, which is the honest attribution: the user did not
choose a Soyuz booster's propellant load, Soyuz's published figures did, and the note says exactly that. What
survives a change of kind is the pair the user plainly owns - how many boosters there are, and how many light
on the ground.
"""
from __future__ import annotations
import copy
import os

import yaml

from .paths import ROOT                                   # noqa: E402

KINDS = ("solid", "liquid")

#: where each kind's donor block is read from, and why that one - see the module docstring
DONORS = {
    "solid": os.path.join(ROOT, "examples", "example_boosters.yaml"),
    "liquid": os.path.join(ROOT, "validation", "soyuz2_1b.yaml"),
}

#: leaves taken from the block being replaced rather than from the donor, when there was one. How many
#: boosters a vehicle has, and how many light on the pad, are the user's architecture decision; the rest of
#: the block describes a particular motor or core and belongs to whichever design it was copied from.
CARRIED_ON_SWITCH = ("n_total", "n_ground_lit")


class StrapOnError(ValueError):
    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.field = field


def _load_annotated(path: str) -> dict:
    from .config_io import _Loader
    with open(path, encoding="utf-8") as fh:
        return yaml.load(fh, Loader=_Loader)


def _val(leaf):
    """The value of an annotated leaf, read the way config_io reads it."""
    return leaf.get("v") if isinstance(leaf, dict) else leaf


def current_kind(doc: dict) -> str | None:
    """`solid`, `liquid`, or None when this design has no strap-ons."""
    b = doc.get("boosters")
    if not isinstance(b, dict) or not b:
        return None
    kind = _val(b.get("type"))
    return kind if kind in KINDS else "solid"


def donor_block(kind: str, donor_path: str | None = None) -> dict:
    """The `boosters:` block of the donor design for `kind`, as an annotated block."""
    if kind not in KINDS:
        raise StrapOnError(f"booster type must be one of {KINDS}, not {kind!r}", "boosters.type")
    path = donor_path or DONORS[kind]
    doc = _load_annotated(path)
    block = doc.get("boosters")
    if not isinstance(block, dict) or not block:
        raise StrapOnError(f"donor design {path} has no boosters block", "boosters.type")
    return copy.deepcopy(block)


def _core_diameter(doc: dict):
    stages = doc.get("stages") or []
    return _val(stages[0].get("diameter_m")) if stages else None


def set_boosters(doc: dict, kind: str | None, donor_path: str | None = None) -> dict:
    """Give the annotated design `doc` strap-ons of type `kind`, or none when `kind` is falsy. In place.

    Returns a note listing what changed, where the block came from and anything the user should look at
    before pressing Size - the same contract as the stage-count and liquid/solid controls.
    """
    if kind in ("", None, "none"):
        kind = None
    elif kind not in KINDS:
        raise StrapOnError(
            f"strap-on boosters must be 'solid' or 'liquid', or none at all; {kind!r} is neither",
            "boosters.type")

    was = current_kind(doc)
    if was == kind:
        label = "no strap-on boosters" if kind is None else f"{kind} strap-on boosters"
        return {"was": was, "now": kind, "changed": False, "donor": None, "warnings": [],
                "note": f"this design already has {label}"}

    if kind is None:
        doc.pop("boosters", None)
        return {"was": was, "now": None, "changed": True, "donor": None, "warnings": [],
                "note": (f"the {was} strap-on boosters have been removed. Nothing else in the design refers "
                         "to them, so the core stages and the delta-v split are untouched - but the vehicle "
                         "now has to lift itself off the pad on the core alone, so expect it to grow")}

    donor = donor_block(kind, donor_path)
    old = doc.get("boosters") if isinstance(doc.get("boosters"), dict) else {}
    carried = []
    for key in CARRIED_ON_SWITCH:
        if key in old and key in donor:
            donor[key] = copy.deepcopy(old[key])
            carried.append(key)
    # how many light on the ground cannot exceed how many there are, and the two came from different places
    n_tot, n_gnd = _val(donor.get("n_total")), _val(donor.get("n_ground_lit"))
    if isinstance(n_tot, (int, float)) and isinstance(n_gnd, (int, float)) and n_gnd > n_tot:
        if isinstance(donor.get("n_ground_lit"), dict):
            donor["n_ground_lit"]["v"] = int(n_tot)
        carried.append("n_ground_lit (reduced to the number of boosters)")
    doc["boosters"] = donor

    donor_rel = os.path.relpath(donor_path or DONORS[kind], ROOT).replace(os.sep, "/")
    warnings = []
    core_d, boost_d = _core_diameter(doc), _val(donor.get("diameter_m"))
    if isinstance(core_d, (int, float)) and isinstance(boost_d, (int, float)) and boost_d > core_d:
        warnings.append(
            f"each booster is {boost_d:.2f} m across against a {core_d:.2f} m core stage. That is a real "
            "configuration - Delta IV Heavy's strap-ons are full-size cores - but check the booster "
            "diameter and propellant load are what you meant before reading the result")
    m_each = _val(donor.get("propellant_mass_each_kg"))
    if isinstance(m_each, (int, float)) and isinstance(n_tot, (int, float)):
        warnings.append(
            f"the block carries the donor's own numbers: {int(n_tot)} boosters of {m_each:,.0f} kg of "
            "propellant each. They are a starting point with the donor's provenance, not a fit to this "
            "vehicle - set the count, the propellant load and the diameter to your own")

    what = "added" if was is None else f"changed from {was} to {kind}"
    return {"was": was, "now": kind, "changed": True, "donor": donor_rel,
            "carried": carried, "warnings": warnings,
            "note": (f"{kind} strap-on boosters {what}, grafted from {donor_rel}"
                     + (f"; your {', '.join(carried)} kept" if carried else "")
                     + ". " + " ".join(w[0].upper() + w[1:] + "." for w in warnings))}
