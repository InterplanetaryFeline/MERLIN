"""Changing how many stages a vehicle has.

The number of stages was never an input. It was implied by the length of the `stages:` list in the YAML, so
the GUI rendered fields for whatever stages the file happened to contain and offered no way to add or remove
one: a new design was a two-stage vehicle because `config/default_design.yaml` has two stages, and a user who
wanted three had to edit YAML by hand. Staging is the first decision in conceptual design, so this is a real
gap rather than a missing convenience.

Like switching a stage between liquid and solid, this cannot be an override. Adding a stage adds a whole
annotated sub-document, and three things elsewhere in the design are counted in stages and have to move with
it:

  * `vehicle.dv_fractions` carries one entry per stage, and validation rejects any other length (DVFRAC).
  * `fairing.jettison_at_stage_start` must land between 2 and N+1 inclusive.
  * `mission.last_ascent_stage`, where it is set at all, names a stage that has to exist.

WHERE A NEW STAGE COMES FROM is the same answer as in `stage_type`: grafted from a shipped design, not from a
template written here. The donor block is real, already loads, already sizes, and carries its own units,
descriptions, sources and provenance tags, so an added stage is annotated exactly as if the user had started
from that example - and there is no second set of numbers in this module to drift out of step with the book.
The donor is chosen to match the type of the stage the new one sits on top of, because a vehicle whose upper
stage is solid is more likely to want another solid than a sudden liquid.

One leaf is carried over from the stage below rather than taken from the donor: `diameter_m`. A stacked
vehicle usually shares a cross-section, the donor's 3.05 m would otherwise land on a 1.9 m vehicle, and the
diameter is unambiguously the user's own decision about their own vehicle, so its annotation travels intact.
Everything else keeps the donor's provenance, which is the honest attribution: the user did not choose those
numbers, the shipped example did.

A STAGE IS ADDED ON TOP and removed from the top. For a new design, where every field is blank anyway, the
position does not matter; for an existing one, "make it three stages" conventionally means putting another
stage above the ones already there, and silently re-plumbing a vehicle's first stage would be a surprise.
"""
from __future__ import annotations
import copy
import os

from .stage_type import DONORS, StageTypeError, current_type, donor_stage, _leaf, _load_annotated  # noqa: F401

from .paths import ROOT                                   # noqa: E402

#: One stage is a legitimate vehicle (a sounding rocket, an SSTO study). The upper bound is not a modelling
#: limit - the sizing loop and the trajectory integrate any number - but a conceptual-design guard: past six
#: stages the staging optimum is flat, the per-stage inert masses dominate, and a user who really wants more
#: can write the YAML. It also keeps a slip of the keyboard from grafting four hundred stages.
MIN_STAGES = 1
MAX_STAGES = 6

#: leaves taken from the stage below instead of from the donor, with the reason in the module docstring
CARRIED_FROM_BELOW = ("diameter_m",)


def upper_donor(to: str, donor_path: str | None = None) -> dict:
    """The donor design's UPPERMOST stage of type `to`, which is the right template for a stage added on top.

    `stage_type.donor_stage` takes the FIRST matching stage, which is correct for its job - converting a
    stage in place, where the first liquid stage of the shipped design is as good a liquid block as any. It
    is the wrong choice here. A stage added on top is an upper stage, and the shipped design's first stage is
    a core: it carries a sea-level-optimised nozzle, a low expansion ratio and a first-stage thrust-to-weight.
    Grafting that as a new upper stage would put a sea-level bell above the atmosphere and quietly cost the
    design several hundred m/s. The last matching stage is the one already built to fly up there.
    """
    path = donor_path or DONORS[to]
    doc = _load_annotated(path)
    stages = doc.get("stages") or []
    for sd in reversed(stages):
        if current_type(sd) == to:
            return copy.deepcopy(sd)
    # no stage of that type in the donor: fall back to stage_type's own pick, which raises if there is none
    return donor_stage(to, donor_path)


class StageCountError(ValueError):
    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.field = field


def current_count(doc: dict) -> int:
    """How many stages this annotated design has."""
    stages = doc.get("stages")
    return len(stages) if isinstance(stages, list) else 0


def _val(leaf):
    """The value of an annotated leaf, read the way config_io reads it."""
    return leaf.get("v") if isinstance(leaf, dict) else leaf


def _set_val(block: dict, key: str, value):
    """Write `value` into an annotated leaf, leaving its units and description alone if it already exists."""
    cur = block.get(key)
    if isinstance(cur, dict) and "v" in cur:
        cur["v"] = value
    else:
        block[key] = _leaf(value)


def _rebalance_dv(doc: dict, old_n: int, new_n: int) -> str | None:
    """Give `vehicle.dv_fractions` one entry per stage, keeping the existing stages' split in proportion.

    Adding a stage: the new one takes an equal share, 1/N, and the stages that were already there keep their
    RATIOS to each other, scaled down to fill what is left. That preserves the staging decision the user
    made - a 44/56 split stays a 44/56 split between those two stages - instead of resetting it to equal.
    Removing a stage: its share is dropped and the rest renormalise the same way.

    The result is tagged `assumed`, because whatever the user chose it was not this, and the source line says
    what happened so the provenance column does not claim the split is theirs.
    """
    vh = doc.get("vehicle")
    if not isinstance(vh, dict):
        return None
    leaf = vh.get("dv_fractions")
    fr = _val(leaf)
    if not isinstance(fr, list) or not fr:
        return None
    try:
        fr = [float(x) for x in fr]
    except (TypeError, ValueError):
        return None

    if new_n > old_n:
        for _ in range(new_n - len(fr)):
            share = 1.0 / (len(fr) + 1)
            fr = [f * (1.0 - share) for f in fr] + [share]
        how = f"the added stage{'s' if new_n - old_n > 1 else ''} given an equal share"
    else:
        fr = fr[:new_n]
        how = "the removed stage's share spread over the rest"

    # A design whose fractions were already the wrong length - hand-edited, or written by an older version -
    # must not come out of here still wrong, so the length is made exact before it is normalised rather than
    # trusted to the arithmetic above. Validation rejects any other length (DVFRAC), and a count change is
    # the wrong moment to hand the user an error about a field they did not touch.
    fr = fr[:new_n]
    while len(fr) < new_n:
        fr.append(1.0 / new_n)

    total = sum(fr)
    if total <= 0:
        fr = [1.0 / new_n] * new_n
    else:
        fr = [f / total for f in fr]
    fr = [round(f, 6) for f in fr]
    # rounding six places over up to six stages can leave the sum a hair off 1.0; put the remainder on the
    # largest stage, where it is relatively smallest
    drift = 1.0 - sum(fr)
    if abs(drift) > 1e-12:
        k = max(range(len(fr)), key=lambda i: fr[i])
        fr[k] = round(fr[k] + drift, 12)

    if isinstance(leaf, dict):
        leaf["v"] = fr
        leaf["s"] = (f"Set when the stage count changed from {old_n} to {new_n}: {how}, "
                     "existing stages kept in proportion. Set it to whatever the staging should be")
        leaf["t"] = "assumed"
    else:
        vh["dv_fractions"] = _leaf(fr, "-", "Share of the total delta-v each stage provides",
                                   f"Set when the stage count changed from {old_n} to {new_n}", "assumed")
    return "vehicle.dv_fractions set to " + ", ".join(f"{100 * f:.1f} %" for f in fr) + f" ({how})"


def _clamp_indices(doc: dict, new_n: int) -> list:
    """Pull any stage-numbered field back inside the new stage count. Returns one note per field moved.

    One of these is not an index but is caused by the same change. The fairing sits on the UPPERMOST stage,
    and removing stages changes which stage that is: drop a 1.9 m upper stage off a 3.05 m core and the
    fairing is suddenly narrower than the stage under it, which validation rejects outright (FAIRDIA) because
    a reducing transition is not modelled. That is a consequence of the count change, so it is fixed here and
    declared, rather than left to surface as an error the user did not cause.
    """
    notes = []

    stages = doc.get("stages") or []
    fairing = doc.get("fairing")
    if isinstance(fairing, dict) and stages:
        top_d = _val((stages[-1] or {}).get("diameter_m"))
        fair_d = _val(fairing.get("diameter_m"))
        if isinstance(top_d, (int, float)) and isinstance(fair_d, (int, float)) and fair_d < top_d - 1e-9:
            _set_val(fairing, "diameter_m", float(top_d))
            notes.append(f"fairing widened from {fair_d:.2f} m to {top_d:.2f} m to match the new top stage, "
                         "which a fairing may not be narrower than")

    if isinstance(fairing, dict):
        leaf = fairing.get("jettison_at_stage_start")
        j = _val(leaf)
        if isinstance(j, (int, float)):
            # validation accepts 2 .. N+1, where N+1 means "not jettisoned during the staged ascent"
            lo, hi = 2, new_n + 1
            want = min(max(int(j), lo), hi)
            if want != int(j):
                _set_val(fairing, "jettison_at_stage_start", want)
                notes.append(f"fairing jettison moved from the start of stage {int(j)} to stage {want}, "
                             f"which is as late as a {new_n}-stage vehicle allows")

    mission = doc.get("mission")
    if isinstance(mission, dict):
        leaf = mission.get("last_ascent_stage")
        v = _val(leaf)
        if isinstance(v, (int, float)) and int(v) > new_n:
            _set_val(mission, "last_ascent_stage", new_n)
            notes.append(f"last ascent stage moved from {int(v)} to {new_n}, the new top stage")
    return notes


def _name_stage(stage: dict, number: int):
    """Label the stage by its position, so the user is not looking at two stages both called 'Stage 1'."""
    leaf = stage.get("name")
    if isinstance(leaf, dict):
        leaf["v"] = f"Stage {number}"
        leaf.setdefault("u", "-")
        leaf.setdefault("d", "Stage label")
        leaf["s"] = "Set when the stage count changed"
        leaf["t"] = "user"
    else:
        stage["name"] = _leaf(f"Stage {number}", "-", "Stage label", "Set when the stage count changed",
                              "user")


def set_count(doc: dict, n: int, donor_path: str | None = None) -> dict:
    """Make the annotated design `doc` have `n` stages, in place. Returns a note describing every change.

    The note is what the GUI shows the user: how many stages were added or removed, where the new blocks came
    from, and every count-dependent field that had to move with them. Nothing here is silent.
    """
    try:
        n = int(n)
    except (TypeError, ValueError):
        raise StageCountError(f"the number of stages must be a whole number, not {n!r}", "stage_count")
    if not MIN_STAGES <= n <= MAX_STAGES:
        raise StageCountError(
            f"the number of stages must be between {MIN_STAGES} and {MAX_STAGES}; {n} is outside what this "
            "tool sizes", "stage_count")

    stages = doc.get("stages")
    if not isinstance(stages, list) or not stages:
        raise StageCountError("this design has no stages to count", "stage_count")
    old_n = len(stages)
    if n == old_n:
        return {"was": old_n, "now": n, "changed": False, "added": 0, "removed": 0,
                "donor": None, "side_effects": [], "note": f"this design already has {n} stage(s)"}

    added, removed, donor_rel = 0, 0, None
    if n > old_n:
        # the new stage sits on top of the current top stage, and matches its type
        to = current_type(stages[-1])
        donor = upper_donor(to, donor_path)
        donor_rel = os.path.relpath(donor_path or DONORS[to], ROOT).replace(os.sep, "/")
        while len(stages) < n:
            below = stages[-1]
            fresh = copy.deepcopy(donor)
            for key in CARRIED_FROM_BELOW:
                if key in below:
                    fresh[key] = copy.deepcopy(below[key])
            _name_stage(fresh, len(stages) + 1)
            stages.append(fresh)
            added += 1
    else:
        while len(stages) > n:
            stages.pop()
            removed += 1

    side = []
    dv_note = _rebalance_dv(doc, old_n, n)
    if dv_note:
        side.append(dv_note)
    side.extend(_clamp_indices(doc, n))

    if added:
        what = (f"{added} stage(s) added on top, grafted from the uppermost stage of the shipped "
                f"{current_type(stages[-1])} example ({donor_rel})")
        # Forewarn rather than surprise. An added stage takes the cross-section of the stage below it, and a
        # stage carrying a fraction of the delta-v may not have enough propellant to fill a tank that wide -
        # the end caps alone can exceed the volume needed. That conflict is real and the sizing error offers
        # the narrower diameter as a one-click fix, but it should not arrive unannounced.
        side.append("a stage added on top starts with the cross-section of the stage below it, which can be "
                    "wider than its propellant load needs; if sizing says so, the error offers the narrower "
                    "tank diameter to apply")
    else:
        what = f"{removed} stage(s) removed from the top"
    return {"was": old_n, "now": n, "changed": True, "added": added, "removed": removed,
            "donor": donor_rel, "side_effects": side,
            "note": f"{old_n} -> {n} stages: {what}." + ("" if not side else " " + " ".join(
                s[0].upper() + s[1:] + "." for s in side))}
