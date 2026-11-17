"""Real engines and motors, and what a power cycle implies (roadmap R2).

A design that names an engine - `engine.from_database: "RD-180"` - stops being a rubber engine: thrust, Isp,
chamber pressure, area ratio, mass and envelope come from published figures instead of a scaling law. The rules
are deliberately conservative:

* the database only ever FILLS fields the design left out; anything the design states wins, always;
* a field the source does not give stays empty, and the tool says which ones it could not supply - nothing is
  invented to make a row look complete;
* every filled field enters the input register with `provenance: reference` and the row's own source string, so
  the report shows where each number came from and a reader can go and check it;
* these are public figures, not book data. The database file says so at the top, and so does the report.

Cycles are the other half of R2: naming a cycle does not change any number, it adds a check. A chamber pressure
far outside the band that cycle actually flies at is a modelling mistake worth a warning, not a silent result.
"""
from __future__ import annotations
import os
import yaml

from .paths import ROOT                                   # noqa: E402
DEFAULT_PATH = os.path.join(ROOT, "config", "engine_database.yaml")

# design-file key -> database key. Only these are ever filled in.
ENGINE_FIELDS = {
    "thrust_vac_per_engine_N": "thrust_vac_N",
    "isp_vac_s": "isp_vac_s",
    "isp_sl_s": "isp_sl_s",
    "chamber_pressure_Pa": "chamber_pressure_Pa",
    "expansion_ratio": "expansion_ratio",
    "mass_user_per_engine_kg": "mass_kg",
    "length_m": "length_m",
    "exit_diameter_m": "exit_diameter_m",
    "cycle": "cycle",
    "name": "name",
}
UNITS = {"thrust_vac_per_engine_N": "N", "thrust_vac_total_N": "N", "isp_vac_s": "s", "isp_sl_s": "s",
         "chamber_pressure_Pa": "Pa", "expansion_ratio": "-", "mass_user_per_engine_kg": "kg", "length_m": "m",
         "exit_diameter_m": "m", "cycle": "-", "name": "-", "burn_time_s": "s", "casing_mass_fraction": "-",
         "prop_mass_each_kg": "kg", "inert_mass_fraction": "-", "diameter_m": "m",
         "fuel": "-", "oxidizer": "-", "mixture_ratio_OF": "-"}
#: stage-level fields an engine row can also supply. A real engine comes with its propellants and the mixture
#: ratio it runs at; leaving the design's generic defaults in place beside a named engine is how a vehicle ends
#: up nominally flying an RD-180 at someone else's O/F.
STAGE_FIELDS = {
    "fuel": "fuel",
    "oxidizer": "oxidizer",
    "mixture_ratio_OF": "of_ratio",
}
MOTOR_FIELDS = {
    "thrust_vac_total_N": "thrust_vac_N",
    "isp_vac_s": "isp_vac_s",
    "burn_time_s": "burn_time_s",
    "casing_mass_fraction": "casing_k",
    "name": "name",
}


class EngineDBError(ValueError):
    pass


_CACHE = {}


def load_db(path: str | None = None) -> dict:
    path = path or DEFAULT_PATH
    if path not in _CACHE:
        if not os.path.exists(path):
            raise EngineDBError(f"engine database not found: {path}")
        with open(path, encoding="utf-8") as f:
            db = yaml.safe_load(f) or {}
        for key in ("engines", "motors"):
            db.setdefault(key, [])
        db.setdefault("cycles", {})
        names = [e["name"] for e in db["engines"]] + [m["name"] for m in db["motors"]]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise EngineDBError(f"duplicate names in the engine database: {sorted(dupes)}")
        _CACHE[path] = db
    return _CACHE[path]


def entries(path: str | None = None) -> list:
    db = load_db(path)
    return [dict(e, kind=e.get("kind", "liquid")) for e in db["engines"]] + \
           [dict(m, kind="solid") for m in db["motors"]]


def find(name: str, path: str | None = None) -> dict:
    for e in entries(path):
        if e["name"].lower() == str(name).lower():
            return e
    avail = ", ".join(sorted(e["name"] for e in entries(path)))
    raise EngineDBError(f"no engine or motor '{name}' in the database. Available: {avail}")


def cycles(path: str | None = None) -> dict:
    return load_db(path)["cycles"]


def cycle_pressure_band_Pa(cycle: str, path: str | None = None):
    c = cycles(path).get(cycle)
    if not c or not c.get("chamber_pressure_bar"):
        return None
    lo, hi = c["chamber_pressure_bar"]
    return lo * 1e5, hi * 1e5


# --------------------------------------------------------------------------- expansion into a design
#: performance fields where silently keeping the design file's own number instead of the database row is worth
#: telling the designer about - these are what make the engine the engine
WATCHED = ("isp_vac_s", "isp_sl_s", "thrust_vac_per_engine_N", "thrust_vac_total_N", "expansion_ratio",
           "chamber_pressure_Pa", "prop_mass_each_kg", "burn_time_s", "mixture_ratio_OF")


def _fill(target: dict, mapping: dict, entry: dict, reg: list, ctx: str) -> tuple:
    """Fill the fields of `target` that are absent or null, recording each one in the input register.

    Fields the design already specifies are never touched - a database row is a default, not an override - but a
    performance field the design overrode with a *different* value is reported back, because a design that names
    a real engine and then flies it at another Isp is almost always a template left half-edited.
    """
    filled, missing, overridden, skipped = [], [], [], []
    # a stage sizes its thrust EITHER by an absolute value OR by a thrust-to-weight ratio, never both; filling the
    # absolute figure into a stage that is sized by T/W would make the design self-contradictory, so it is skipped
    # and reported instead
    sized_by_tw = (target.get("thrust_to_weight_ignition") is not None
                   or target.get("thrust_mode") in ("tw_ignition", "burn_time"))
    for design_key, db_key in mapping.items():
        if design_key == "name" and target.get("name"):
            continue
        if sized_by_tw and design_key in ("thrust_vac_per_engine_N", "thrust_vac_total_N"):
            if entry.get(db_key) is not None:
                skipped.append(dict(field=design_key, database=entry[db_key],
                                    why="the stage is sized by thrust-to-weight, not by absolute thrust"))
            continue
        val = entry.get(db_key)
        if target.get(design_key) is not None:
            if (design_key in WATCHED and val is not None
                    and abs(float(target[design_key]) - float(val)) > 1e-6 * max(1.0, abs(float(val)))):
                overridden.append(dict(field=design_key, design=target[design_key], database=val))
            continue                       # the design file wins, always
        if val is None:
            if db_key not in ("length_m", "exit_diameter_m", "name"):
                missing.append(db_key)
            continue
        target[design_key] = val
        filled.append(design_key)
        reg.append(dict(path=f"{ctx}.{design_key}", value=val, units=UNITS.get(design_key, "-"),
                        description=f"filled from the engine database entry '{entry['name']}'",
                        source=f"engine database ({entry.get('confidence', 'unknown')} confidence): "
                               f"{entry.get('source', 'no source given')}",
                        provenance="reference"))
    return filled, missing, overridden, skipped


def _propellant_mismatches(sd: dict, entry: dict) -> list:
    """A design that names an engine and then declares a different propellant is almost certainly a mistake.

    Nothing is changed - the design always wins - but an RD-180 stage declared as LOX/LH2 is reported, because
    the resulting vehicle would be sized on one propellant's density and another's performance.
    """
    out = []
    for key in ("fuel", "oxidizer"):
        have, want = sd.get(key), entry.get(key)
        if have and want and str(have).strip().lower() != str(want).strip().lower():
            out.append(dict(field=key, design=have, database=want))
    return out


def expand_design(design: dict, reg: list, path: str | None = None) -> list:
    """Resolve every `from_database` reference in a loaded design. Returns one note per resolved reference.

    Called by config_io after the YAML is unwrapped and before the spec is built, so the filled values go through
    exactly the same validation as hand-written ones.
    """
    notes = []
    for i, sd in enumerate(design.get("stages") or []):
        for block, mapping in (("engine", ENGINE_FIELDS), ("motor", MOTOR_FIELDS)):
            blk = sd.get(block)
            if not isinstance(blk, dict) or not blk.get("from_database"):
                continue
            entry = find(blk["from_database"], path)
            ctx = f"stages.{i}.{block}"
            want_solid = block == "motor"
            if (entry["kind"] == "solid") != want_solid:
                raise EngineDBError(f"{ctx}: '{entry['name']}' is a {entry['kind']} entry, "
                                    f"but it is referenced as a {'solid motor' if want_solid else 'liquid engine'}")
            filled, missing, overridden, skipped = _fill(blk, mapping, entry, reg, ctx)
            if block == "engine":
                # the propellants and mixture ratio live on the STAGE, not inside the engine block
                sfilled, _sm, soverridden, _sk = _fill(sd, STAGE_FIELDS, entry, reg, f"stages.{i}")
                filled += sfilled
                overridden += soverridden
                overridden += _propellant_mismatches(sd, entry)
            if block == "motor" and "casing_mass_fraction" in filled:
                blk.setdefault("casing_mass_method", "mass_fraction")
            notes.append(dict(context=ctx, entry=entry["name"], filled=filled, missing=missing,
                              overridden=overridden, skipped=skipped,
                              confidence=entry.get("confidence"), source=entry.get("source", "")))
    b = design.get("boosters")
    if isinstance(b, dict) and b.get("from_database"):
        entry = find(b["from_database"], path)
        if entry["kind"] != "solid":
            raise EngineDBError(f"boosters: '{entry['name']}' is not a solid-motor entry")
        mapping = {"isp_vac_s": "isp_vac_s", "burn_time_s": "burn_time_s",
                   "prop_mass_each_kg": "propellant_mass_kg", "inert_mass_fraction": "casing_k",
                   "diameter_m": "diameter_m", "name": "name"}
        filled, missing, overridden, skipped = _fill(b, mapping, entry, reg, "boosters")
        if "inert_mass_fraction" in filled:
            b.setdefault("inert_mass_method", "mass_fraction")
        notes.append(dict(context="boosters", entry=entry["name"], filled=filled, missing=missing,
                          overridden=overridden, skipped=skipped,
                          confidence=entry.get("confidence"), source=entry.get("source", "")))
    return notes


# ------------------------------------------------------------------ R20: is the engine mass MER any good?
def mer_check(coeffs: dict | None = None) -> dict:
    """Measure book Table 8.9 row 1 against every database engine that publishes a dry mass.

    The MER is m = F_vac (a + b sqrt(eps)) + c, so it needs a VACUUM thrust and an expansion ratio. Several
    rows publish only a sea-level thrust; where the row also gives both specific impulses, the vacuum thrust
    follows from the same mass flow (F_vac/F_sl = Isp_vac/Isp_sl) and the row is marked `derived`. Rows that
    cannot supply the inputs are listed in `excluded` with the reason rather than dropped silently.

    The answer this returns is a measurement, not a correction. Whether it justifies refitting the relation
    depends on whether the residual is structured or merely scattered, which is what `verdict` reports.
    """
    import math as _math
    import statistics as _st
    from . import propulsion as _prop

    c = coeffs or {"a": 7.81e-4, "b": 3.37e-5, "c": 59.0}
    rows, excluded = [], []
    for e in entries():
        if e.get("kind", "liquid") == "solid":
            continue
        name, m_pub, eps = e.get("name"), e.get("mass_kg"), e.get("expansion_ratio")
        if not m_pub:
            excluded.append({"engine": name, "why": "no published dry mass"})
            continue
        if not eps:
            excluded.append({"engine": name, "why": "no expansion ratio, which the MER needs"})
            continue
        f_vac, how = e.get("thrust_vac_N"), "published"
        if not f_vac:
            f_sl, iv, isl = e.get("thrust_sl_N"), e.get("isp_vac_s"), e.get("isp_sl_s")
            if f_sl and iv and isl:
                f_vac, how = f_sl * iv / isl, "derived from sea-level thrust and the two Isp values"
            else:
                excluded.append({"engine": name,
                                 "why": "only a sea-level thrust, and not both Isp values to scale it"})
                continue
        pred = _prop.engine_mass_mer(f_vac, eps, c)
        rows.append({"engine": name, "thrust_vac_N": f_vac, "thrust_source": how,
                     "expansion_ratio": eps, "published_kg": m_pub, "mer_kg": pred,
                     "error": (pred - m_pub) / m_pub})

    rows.sort(key=lambda r: -r["thrust_vac_N"])
    errs = [r["error"] for r in rows]
    out = {"rows": rows, "excluded": excluded, "n": len(rows), "coeffs": c,
           "source": "Book Table 8.9 row 1, p.495"}
    if errs:
        out.update(mean=_st.mean(errs), median=_st.median(errs),
                   mean_abs=_st.mean(abs(x) for x in errs),
                   sd=(_st.pstdev(errs) if len(errs) > 1 else 0.0),
                   worst=max(rows, key=lambda r: abs(r["error"])))
        # A refit is only worth doing if the error depends on something - here, on engine size. If the
        # scatter swamps any trend, a new coefficient fitted to this sample would just move the noise.
        big = [r["error"] for r in rows if r["thrust_vac_N"] > 5e5]
        small = [r["error"] for r in rows if r["thrust_vac_N"] <= 5e5]
        trend = (_st.mean(big) - _st.mean(small)) if (big and small) else None
        out["trend_large_minus_small"] = trend
        out["n_light"] = sum(1 for e in errs if e < 0)

        # A single multiplicative correction, fitted in LOG space so a 5 t engine does not outvote a 150 kg
        # one. It is reported, not applied: `mer_calibrated` is an opt-in engine mass method.
        logs = [_math.log(r["published_kg"] / r["mer_kg"]) for r in rows]
        k = _math.exp(_st.mean(logs))
        out["calibration_factor"] = k
        ce = [(k * r["mer_kg"] - r["published_kg"]) / r["published_kg"] for r in rows]
        out["calibrated"] = {"mean": _st.mean(ce), "median": _st.median(ce),
                             "sd": _st.pstdev(ce) if len(ce) > 1 else 0.0}

        size_structured = trend is not None and abs(trend) > out["sd"]
        biased = abs(out["median"]) > 0.15 and out["n_light"] >= 0.75 * out["n"]
        if biased:
            out["verdict"] = (
                f"BIASED LOW: {out['n_light']} of {out['n']} engines come out light and the median error is "
                f"{100 * out['median']:+.0f}%, which is a systematic offset rather than scatter. A single "
                f"factor of {k:.2f} removes it for the TYPICAL engine (median "
                f"{100 * out['calibrated']['median']:+.0f}%) but makes the two exceptional ones worse, because "
                "no scale factor can fix a distribution with strong outliers on one side. It is therefore "
                "offered as the opt-in method 'mer_calibrated' and the book's coefficients remain the "
                "default.")
        elif size_structured:
            out["verdict"] = ("STRUCTURED: the error depends on engine size by more than its own scatter, so "
                              "a refit would capture something real")
        else:
            out["verdict"] = (
                "SCATTERED: the spread between engines is larger than any size trend, so refitting this "
                "relation on this sample would fit noise. The book's coefficients are kept and the scatter "
                "is reported instead - which is what the uncertainty study already does with it.")
    return out
