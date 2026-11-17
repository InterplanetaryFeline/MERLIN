"""Vehicle-data importer (R16): public source data -> annotated design YAML.

Purpose: grow the validation set without hand-typing nine hundred lines of YAML per vehicle. The
output is an ordinary design file in the same {v, u, d, s, t} form as everything in config/ and
validation/, so an imported vehicle is sized, reported and validated exactly like a hand-written one.

The rule the whole module is built around: a value either came from the source, in which case it is
tagged t = reference and carries the source string the sheet gave, or it did not, in which case it
keeps the base configuration's value and is tagged t = assumed and listed in the import report. The
importer never invents a number and never quietly accepts a default for something the source was
supposed to supply - a missing REQUIRED field raises, naming the vehicle and the field.

What public sources actually carry
----------------------------------
Enough to validate a design, because the tool PREDICTS the masses: payload to a stated orbit, stage
diameters, engine counts, thrust, Isp and propellants. Not enough to skip engineering judgement:
stage dry and propellant masses, tank arrangement, pressures, materials, skirt proportions and
engine envelopes are almost never published, and all of them stay at the base configuration's
assumed values. A typical import leaves far more fields assumed than referenced; the report says so
per vehicle, and `write_design` writes the count into the file's header comment.

On launchercalculator.com (named in the roadmap as a source): it is a calculator the user types
parameters INTO, not a published dataset - there is no data download, endpoint or API on the site,
and its repository is the calculator itself. Nothing to import. Wikipedia infoboxes are a real
source but a partly ambiguous one, which `parse_infobox` handles by refusing to guess - see there.

Formats read
------------
* CSV  - one row per vehicle, the column names below (`vehicle_sheet_columns()` prints them).
* JSON - the same fields, either flat like the CSV or with a "stages" list.
* Wikipedia infobox wikitext - a transcription aid, not an automatic import; see `parse_infobox`.
"""
from __future__ import annotations

import copy
import csv
import datetime
import json
import os
import re
from dataclasses import dataclass, field

import yaml

from .config_io import _Loader

from .paths import ROOT                                   # noqa: E402
DEFAULT_BASE = os.path.join(ROOT, "config", "default_design.yaml")
DEFAULT_SOLID_BASE = os.path.join(ROOT, "examples", "example_solid_smallsat.yaml")


class VehicleImportError(Exception):
    """Raised when a source sheet cannot be turned into a design without inventing something."""


# --------------------------------------------------------------------------------- field maps
# canonical sheet column -> (dotted path in the design, python type)
VEHICLE_FIELDS = {
    "payload_mass_kg": ("mission.payload_mass_kg", float),
    "orbit_type": ("mission.orbit.type", str),
    "perigee_altitude_km": ("mission.orbit.perigee_altitude_km", float),
    "apogee_altitude_km": ("mission.orbit.apogee_altitude_km", float),
    "inclination_deg": ("mission.orbit.inclination_deg", float),
    "site_latitude_deg": ("mission.launch_site.latitude_deg", float),
    "payload_envelope_diameter_m": ("mission.payload_envelope_diameter_m", float),
    "payload_envelope_length_m": ("mission.payload_envelope_length_m", float),
    "fairing_diameter_m": ("fairing.diameter_m", float),
    "fairing_material": ("fairing.material", str),
    "max_vehicle_length_m": ("constraints.max_vehicle_length_m", float),
}

LIQUID_STAGE_FIELDS = {
    "diameter_m": ("diameter_m", float),
    "fuel": ("fuel", str),
    "oxidizer": ("oxidizer", str),
    "mixture_ratio_OF": ("mixture_ratio_OF", float),
    "n_engines": ("engine.n_engines", int),
    "engine_name": ("engine.name", str),
    "thrust_vac_per_engine_N": ("engine.thrust_vac_per_engine_N", float),
    "thrust_to_weight_ignition": ("engine.thrust_to_weight_ignition", float),
    "isp_vac_s": ("engine.isp_vac_s", float),
    "isp_sl_s": ("engine.isp_sl_s", float),
    "isp_effective_mode": ("engine.isp_effective_mode", str),
    "isp_effective_user_s": ("engine.isp_effective_user_s", float),
    "expansion_ratio": ("engine.expansion_ratio", float),
    "chamber_pressure_Pa": ("engine.chamber_pressure_Pa", float),
    "engine_length_m": ("engine.length_m", float),
    "engine_exit_diameter_m": ("engine.exit_diameter_m", float),
    "engine_mass_method": ("engine.mass_method", str),
    "engine_mass_per_engine_kg": ("engine.mass_user_per_engine_kg", float),
    "tank_material": ("tank.material", str),
    # Inert-mass assumptions. They are listed here because they DO NOT SCALE: the absolute ones in
    # kg are the single biggest reason an imported small vehicle comes out heavy (see SCALE_SENSITIVE).
    "structure_mass_factor": ("structure_mass_factor", float),
    "inert_mass_margin_fraction": ("inert_mass_margin_fraction", float),
    "residual_fraction": ("residual_fraction", float),
    "other_equipment_mass_kg": ("other_equipment_mass_kg", float),
    "separation_hardware_mass_kg": ("separation_hardware_mass_kg", float),
    "feed_system_mass_per_engine_kg": ("feed_system_mass_per_engine_kg", float),
}

SOLID_STAGE_FIELDS = {
    "diameter_m": ("diameter_m", float),
    "propellant": ("propellant", str),
    "motor_name": ("motor.name", str),
    "n_motors": ("motor.n_motors", int),
    "thrust_vac_total_N": ("motor.thrust_vac_total_N", float),
    "thrust_to_weight_ignition": ("motor.thrust_to_weight_ignition", float),
    "isp_vac_s": ("motor.isp_vac_s", float),
    "isp_sl_s": ("motor.isp_sl_s", float),
    "isp_effective_mode": ("motor.isp_effective_mode", str),
    "isp_effective_user_s": ("motor.isp_effective_user_s", float),
    "burn_time_s": ("motor.burn_time_s", float),
    "nozzle_length_m": ("motor.nozzle_length_m", float),
    "exit_diameter_m": ("motor.exit_diameter_m", float),
    "structure_mass_factor": ("structure_mass_factor", float),
    "inert_mass_margin_fraction": ("inert_mass_margin_fraction", float),
    "residual_fraction": ("residual_fraction", float),
    "other_equipment_mass_kg": ("other_equipment_mass_kg", float),
    "separation_hardware_mass_kg": ("separation_hardware_mass_kg", float),
}

# Leaves carrying an ABSOLUTE mass or a structure factor. Cloning a stage template from a base design
# of a different size class transfers these unchanged, and because they do not scale with the vehicle
# they dominate a small one: the default 10 t-class base contributes 100 kg of "other equipment",
# 60 kg of separation hardware and 25 kg per engine of feed system to every stage, which is noise on
# a Falcon 9 and roughly doubles the inert mass of an Electron-sized vehicle. Hence the warning in
# `build_design` and the columns above that let a sheet override them.
SCALE_SENSITIVE = ("other_equipment_mass_kg", "separation_hardware_mass_kg",
                   "feed_system_mass_per_engine_kg", "engine.mass_user_per_engine_kg",
                   "motor.igniter_mass_kg", "motor.tvc_mass_kg", "motor.casing_mass_kg",
                   "structure_mass_factor")
SCALE_WARN_RATIO = 3.0        # payload mass ratio beyond which the carried-over masses are flagged

# Without these the design is not a design, so their absence is an error rather than an assumption.
REQUIRED_VEHICLE = ("payload_mass_kg", "perigee_altitude_km")
REQUIRED_STAGE = ("diameter_m", "isp_vac_s")
# ...and a stage needs SOME way to know its thrust: an absolute figure or a thrust/weight ratio.
THRUST_FIELDS = ("thrust_vac_per_engine_N", "thrust_vac_total_N", "thrust_to_weight_ignition")


def vehicle_sheet_columns() -> list:
    """Every column `read_csv` understands, in the order a template sheet should carry them."""
    cols = ["key", "name", "description", "source", "n_stages"] + list(VEHICLE_FIELDS)
    for i in (1, 2, 3, 4):
        cols.append(f"stage{i}_type")
        cols += [f"stage{i}_{k}" for k in dict(LIQUID_STAGE_FIELDS, **SOLID_STAGE_FIELDS)]
    return cols


# ------------------------------------------------------------------------------- the record
@dataclass
class Value:
    """One imported number with the source it came from."""
    value: object
    source: str


@dataclass
class VehicleRecord:
    key: str                                   # file stem, e.g. "h2a_202"
    name: str = ""                             # meta.name
    description: str = ""
    source: str = ""                           # default provenance for every field of this vehicle
    fields: dict = field(default_factory=dict)        # canonical name -> Value
    stages: list = field(default_factory=list)        # list of {"type": "liquid"|"solid", ...: Value}
    ambiguous: dict = field(default_factory=dict)     # field -> the competing candidates found

    @property
    def n_stages(self) -> int:
        return len(self.stages)


@dataclass
class ImportReport:
    """What the import took from the source and what it did not - the honest half of the output."""
    key: str
    name: str
    referenced: list = field(default_factory=list)    # (path, value, source) - came from the source
    assumed: list = field(default_factory=list)       # (path, value) - base file's ESTIMATES, t=assumed
    inherited: list = field(default_factory=list)     # (path, value) - base file's book-sourced values
    ambiguous: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)      # things the user has to look at before trusting it
    path: str = ""

    @property
    def n_referenced(self) -> int:
        return len(self.referenced)

    @property
    def n_assumed(self) -> int:
        return len(self.assumed)

    def summary(self) -> str:
        return (f"{self.key}: {self.n_referenced} leaves from the source, {self.n_assumed} left as "
                f"estimates, {len(self.inherited)} inherited from the book-sourced base configuration")

    def as_text(self) -> str:
        out = [f"Import report - {self.name} ({self.key})", "=" * 78, self.summary(), "",
               "FROM THE SOURCE (t = reference)"]
        out += [f"  {p:52s} {v!r:>16}   {s}" for p, v, s in self.referenced] or ["  (none)"]
        out += ["", "LEFT AS ESTIMATES (t = assumed; the source gave nothing, so these are the "
                    "tool's own assumptions and the first place to look when a result surprises you)"]
        out += [f"  {p:52s} {v!r:>16}" for p, v in self.assumed] or ["  (none)"]
        out += ["", f"INHERITED FROM THE BASE CONFIGURATION ({len(self.inherited)} leaves: book "
                    f"references and run options, unchanged by the import)"]
        if self.warnings:
            out += ["", "WARNINGS"] + [f"  ! {w}" for w in self.warnings]
        if self.ambiguous:
            out += ["", "AMBIGUOUS IN THE SOURCE - not imported, decide and enter by hand"]
            out += [f"  {k:28s} candidates: {c}" for k, c in sorted(self.ambiguous.items())]
        return "\n".join(out)


# ------------------------------------------------------------------------------- CSV / JSON
def _num(text, cast):
    """Parse one sheet cell, returning None for an empty one. Thousands separators are tolerated."""
    if text is None:
        return None
    s = str(text).strip().replace(",", "") if cast in (float, int) else str(text).strip()
    if s == "" or s.lower() in ("-", "n/a", "na", "none", "null"):
        return None
    try:
        return cast(float(s)) if cast is int else cast(s)
    except ValueError as e:
        raise VehicleImportError(f"cannot read {text!r} as {cast.__name__}") from e


def _record_from_mapping(row: dict, key_hint: str = "") -> VehicleRecord:
    row = {k.strip(): v for k, v in row.items() if k and k.strip()}
    rec = VehicleRecord(key=str(row.get("key") or key_hint or "").strip(),
                        name=str(row.get("name") or "").strip(),
                        description=str(row.get("description") or "").strip(),
                        source=str(row.get("source") or "").strip())
    if not rec.key:
        raise VehicleImportError("every row needs a 'key' (it becomes the YAML file name)")
    if not rec.source:
        raise VehicleImportError(f"{rec.key}: a 'source' column is required - an imported figure with no "
                           f"provenance is exactly what this tool refuses to produce")
    known = set(VEHICLE_FIELDS) | {"key", "name", "description", "source", "n_stages"}
    for col, val in row.items():
        if col.startswith("stage") or not str(val or "").strip():
            continue
        bare = col[:-7] if col.endswith("_source") else col
        if bare not in known:
            raise VehicleImportError(
                f"{rec.key}: column {col!r} is filled in but not understood, and a filled-in column "
                f"must never be silently dropped. Run write_template_csv for the column list.")
    for col, (_path, cast) in VEHICLE_FIELDS.items():
        v = _num(row.get(col), cast)
        if v is not None:
            rec.fields[col] = Value(v, str(row.get(f"{col}_source") or rec.source))

    declared = _num(row.get("n_stages"), int)
    for i in range(1, 9):
        stype = str(row.get(f"stage{i}_type") or "").strip().lower()
        prefix = f"stage{i}_"
        present = {k: v for k, v in row.items() if k.startswith(prefix) and str(v or "").strip()}
        if not present and not stype:
            continue
        if stype not in ("liquid", "solid"):
            raise VehicleImportError(f"{rec.key}: stage {i} needs stage{i}_type = liquid or solid "
                               f"(got {stype!r})")
        table = SOLID_STAGE_FIELDS if stype == "solid" else LIQUID_STAGE_FIELDS
        for col in present:
            bare = col[len(prefix):]
            if bare in ("type",) or bare.endswith("_source") and bare[:-7] in table:
                continue
            if bare not in table:
                raise VehicleImportError(
                    f"{rec.key}: stage {i} is {stype}, which has no field {bare!r} "
                    f"(did you mean a {'liquid' if stype == 'solid' else 'solid'} stage?). "
                    f"Known {stype} fields: {', '.join(sorted(table))}")
        st = {"type": stype}
        for col, (_path, cast) in table.items():
            v = _num(row.get(prefix + col), cast)
            if v is not None:
                st[col] = Value(v, str(row.get(f"{prefix}{col}_source") or rec.source))
        rec.stages.append(st)
    if declared is not None and declared != rec.n_stages:
        raise VehicleImportError(f"{rec.key}: n_stages says {declared} but {rec.n_stages} stage column "
                           f"groups were filled in")
    if not rec.stages:
        raise VehicleImportError(f"{rec.key}: no stage columns filled in")
    return rec


def read_csv(path) -> list:
    """Read a vehicle sheet. One row per vehicle; `vehicle_sheet_columns()` lists the columns."""
    try:
        # utf-8-sig also accepts the byte-order mark Excel puts on its "CSV UTF-8" format
        with open(path, newline="", encoding="utf-8-sig") as fh:
            rows = [r for r in csv.DictReader(fh)
                    if any(str(v or "").strip() for v in r.values())
                    and not str(r.get("key") or "").lstrip().startswith("#")]
    except UnicodeDecodeError as e:
        raise VehicleImportError(f"{path}: not UTF-8 text. Save the sheet as 'CSV UTF-8'; guessing the "
                                 f"encoding could silently garble a source citation ({e})") from e
    if not rows:
        raise VehicleImportError(f"{path}: no data rows")
    return [_record_from_mapping(r) for r in rows]


def read_json(path) -> list:
    """Read the same fields from JSON: a list of objects, or one object keyed by vehicle key.

    A stage may be given either as flat `stage1_*` keys or inside a "stages" list, which is the
    friendlier shape for anything generating the file programmatically.
    """
    with open(path, encoding="utf-8") as fh:
        blob = json.load(fh)
    items = []
    if isinstance(blob, dict):
        items = [dict(v, key=v.get("key", k)) for k, v in blob.items()] if \
            all(isinstance(v, dict) for v in blob.values()) else [blob]
    elif isinstance(blob, list):
        items = list(blob)
    else:
        raise VehicleImportError(f"{path}: expected a list of vehicles or an object keyed by vehicle")
    out = []
    for it in items:
        it = dict(it)
        for i, st in enumerate(it.pop("stages", []) or [], start=1):
            for k, v in st.items():
                it[f"stage{i}_{k}"] = v
        out.append(_record_from_mapping(it))
    return out


def read_any(path) -> list:
    ext = os.path.splitext(str(path))[1].lower()
    if ext == ".csv":
        return read_csv(path)
    if ext in (".json", ".jsn"):
        return read_json(path)
    raise VehicleImportError(f"{path}: expected a .csv or .json vehicle sheet")


# ------------------------------------------------------------------- Wikipedia infobox wikitext
# Float-equality slack only. Metric/imperial twins are removed STRUCTURALLY rather than by tolerance
# (see infobox_number): no tolerance can separate "3.7 m (12 ft)", which is one figure 1.2% apart from
# itself, from "FT: 69.8 m; v1.1: 68.4 m", which is two vehicles 2.0% apart.
TWIN_TOLERANCE = 1e-9
_UNITS_TO_SI = {                       # multiplier onto the SI unit of that quantity
    "m": 1.0, "ft": 0.3048, "km": 1000.0, "cm": 0.01,
    "kg": 1.0, "lb": 0.45359237, "t": 1000.0, "tonne": 1000.0, "ton": 1000.0, "lbs": 0.45359237,
    "n": 1.0, "kn": 1e3, "mn": 1e6, "lbf": 4.4482216152605, "kgf": 9.80665,
    "s": 1.0, "sec": 1.0, "seconds": 1.0,
}


def _strip_markup(s: str) -> str:
    s = re.sub(r"<ref[^>]*?/>", " ", s)
    s = re.sub(r"<ref.*?</ref>", " ", s, flags=re.S)
    s = re.sub(r"<!--.*?-->", " ", s, flags=re.S)
    s = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]|]*)\]\]", r"\1", s)        # [[target|text]] -> text
    s = re.sub(r"</?\w+[^>]*>", " ", s)
    return s


def _convert_templates(s: str) -> str:
    """Reduce {{convert|549000|kg|lb}} to '549000 kg' so one regex can find numbers afterwards."""
    def one(m):
        parts = [p.strip() for p in m.group(1).split("|")]
        parts = [p for p in parts if "=" not in p]
        if len(parts) >= 2:
            return f" {parts[0]} {parts[1]} "
        return " " + " ".join(parts) + " "
    return re.sub(r"\{\{\s*(?:convert|cvt)\s*\|(.*?)\}\}", one, s, flags=re.I | re.S)


def parse_infobox_fields(wikitext: str) -> dict:
    """Split `{{Infobox ...}}` wikitext into {parameter: raw value}, templates and refs removed."""
    i = wikitext.find("{{")
    if i < 0:
        raise VehicleImportError("no template found in the text given")
    depth, j = 0, i
    while j < len(wikitext):
        if wikitext.startswith("{{", j):
            depth += 1
            j += 2
        elif wikitext.startswith("}}", j):
            depth -= 1
            j += 2
            if depth == 0:
                break
        else:
            j += 1
    body = wikitext[i + 2:j - 2]
    # split on pipes that are not inside a nested template or link
    parts, depth, buf = [], 0, []
    k = 0
    while k < len(body):
        if body.startswith(("{{", "[["), k):
            depth += 1
            buf.append(body[k:k + 2])
            k += 2
        elif body.startswith(("}}", "]]"), k):
            depth -= 1
            buf.append(body[k:k + 2])
            k += 2
        elif body[k] == "|" and depth == 0:
            parts.append("".join(buf))
            buf = []
            k += 1
        else:
            buf.append(body[k])
            k += 1
    parts.append("".join(buf))
    out = {}
    for p in parts[1:]:                                   # parts[0] is the template name
        if "=" not in p:
            continue
        key, _, val = p.partition("=")
        out[key.strip().lower()] = _strip_markup(_convert_templates(val)).strip()
    return out


def infobox_number(raw: str, quantity: str):
    """Extract ONE SI number from an infobox value, or report that the value is ambiguous.

    Returns (value, candidates). `value` is None whenever the field does not reduce to a single
    number, and `candidates` then lists what was found. This is the whole point of the function:
    real infobox cells read like "FT: 549,000 kg; v1.1: 506,000 kg; v1.0: 333,000 kg" or
    "22,800 kg when expended, 17,500 kg when landing on drone ship", and an importer that silently
    took the first number would be fabricating a specification for a vehicle variant nobody chose.
    """
    if not raw:
        return None, []
    # A restatement in the other unit system lives either inside the {{convert}} template, whose
    # target unit _convert_templates has already dropped, or in parentheses right after the figure.
    # Stripping parenthesised spans leaves only figures the article states in their own right.
    raw = re.sub(r"\([^()]*\)", " ", raw)
    si_units = {"length": ("m", "ft", "km", "cm"), "mass": ("kg", "lb", "lbs", "t", "tonne", "ton"),
                "force": ("n", "kn", "mn", "lbf", "kgf"), "time": ("s", "sec", "seconds"),
                "number": ()}[quantity]
    cands = []
    if quantity == "number":
        for m in re.finditer(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])", raw):
            cands.append((float(m.group(1)), m.group(0)))
    else:
        pat = r"(\d[\d,]*(?:\.\d+)?)\s*(" + "|".join(si_units) + r")\b"
        for m in re.finditer(pat, raw, re.I):
            unit = m.group(2).lower()
            cands.append((float(m.group(1).replace(",", "")) * _UNITS_TO_SI[unit], m.group(0)))
    if not cands:
        return None, []
    texts = [t for _v, t in cands]
    vals = sorted(v for v, _ in cands)
    # After the structural strip above, two surviving numbers are two figures the article really
    # does state separately - Falcon 9's "FT: 69.8 m; v1.1: 68.4 m" is two vehicles - so anything
    # but a single value is refused. The known blind spot is the reverse case: an article that
    # restates a figure WITHOUT a convert template or parentheses reads as ambiguous and is skipped,
    # which costs a field rather than inventing one.
    if vals[-1] - vals[0] <= TWIN_TOLERANCE * abs(vals[-1]):
        si = {"length": "m", "mass": "kg", "force": "n", "time": "s", "number": ""}[quantity]
        for v, t in cands:
            if re.search(rf"\d\s*{si}\b", t, re.I):
                return v, texts
        return vals[len(vals) // 2], texts
    return None, texts


# Infobox parameter -> (canonical sheet field, quantity). Stage parameters carry a {} for the index.
INFOBOX_VEHICLE_MAP = {
    "diameter": ("fairing_diameter_m", "length"),
}
INFOBOX_STAGE_MAP = {
    "stage{}engines": ("n_engines", "number"),
    "stage{}thrust": ("thrust_vac_per_engine_N", "force"),
    "stage{}burntime": ("burn_time_s", "time"),
    "stage{}diameter": ("diameter_m", "length"),
}


def parse_infobox(wikitext: str, key: str, source: str, name: str = "") -> VehicleRecord:
    """Turn `{{Infobox rocket}}` wikitext into a partial record, refusing every ambiguous field.

    This is a TRANSCRIPTION AID and nothing more. Infoboxes routinely give several variants of a
    vehicle in one cell, combine the engine count and engine name in one "stage1engines" row, and
    omit stage dry and propellant masses entirely; fields that do not reduce to a single number are
    left out and listed in `record.ambiguous` for a person to resolve. Expect to finish the sheet by
    hand - the value here is that the unambiguous fields are transcribed without typing errors.
    """
    fields = parse_infobox_fields(wikitext)
    rec = VehicleRecord(key=key, name=name or fields.get("name", key), source=source)
    for param, (canon, quantity) in INFOBOX_VEHICLE_MAP.items():
        if param in fields:
            v, cands = infobox_number(fields[param], quantity)
            if v is None and cands:
                rec.ambiguous[canon] = cands
            elif v is not None:
                rec.fields[canon] = Value(v, source)
    n = 0
    for i in range(1, 9):
        got = {}
        for pattern, (canon, quantity) in INFOBOX_STAGE_MAP.items():
            param = pattern.format(i)
            if param not in fields:
                continue
            v, cands = infobox_number(fields[param], quantity)
            if v is None and cands:
                rec.ambiguous[f"stage{i}_{canon}"] = cands
            elif v is not None:
                got[canon] = Value(v, source)
        if not got and f"stage{i}engines" not in fields:
            continue
        n = i
        rec.stages.append(dict(got, type="liquid"))
    if not n:
        raise VehicleImportError(f"{key}: no stage parameters found in the infobox")
    return rec


# ---------------------------------------------------------------------------- YAML emission
def _set(doc: dict, path: str, value, source: str, t: str = "reference") -> None:
    """Replace a leaf's v/s/t in place, keeping the base file's units and description."""
    keys = path.split(".")
    cur = doc
    for k in keys[:-1]:
        cur = cur[int(k)] if isinstance(cur, list) else cur[k]
    leaf = cur.get(keys[-1])
    if not isinstance(leaf, dict) or "v" not in leaf:
        raise VehicleImportError(f"the base configuration has no annotated leaf at {path!r}")
    leaf["v"] = value
    leaf["s"] = source
    leaf["t"] = t


def _paths_of(doc, prefix="") -> list:
    """Every annotated leaf path in a design document, for reporting what was left assumed."""
    out = []
    if isinstance(doc, dict):
        if "v" in doc and "t" in doc and not isinstance(doc.get("v"), dict):
            return [prefix]
        for k, v in doc.items():
            out += _paths_of(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(doc, list):
        for i, v in enumerate(doc):
            out += _paths_of(v, f"{prefix}.{i}")
    return out


def _load_base(path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.load(fh, Loader=_Loader)


def build_design(rec: VehicleRecord, base_path=DEFAULT_BASE, solid_base_path=DEFAULT_SOLID_BASE,
                 retrieved=None):
    """Turn a record into an annotated design document plus its import report.

    Stage blocks are cloned from real, already-validated configuration files rather than written out
    here, so an imported stage carries exactly the assumed fields (layout proportions, tank methods,
    margins) that a hand-written one does - and the report names every one of them.
    """
    base = _load_base(base_path)
    doc = copy.deepcopy(base)
    rep = ImportReport(key=rec.key, name=rec.name or rec.key, ambiguous=dict(rec.ambiguous))

    missing = [f for f in REQUIRED_VEHICLE if f not in rec.fields]
    if missing:
        raise VehicleImportError(f"{rec.key}: required field(s) {', '.join(missing)} missing - these have "
                           f"no sensible default and will not be guessed")

    liquid_tpl = copy.deepcopy(base["stages"][0])
    solid_tpl = None
    if any(s["type"] == "solid" for s in rec.stages):
        sb = _load_base(solid_base_path)
        solid_tpl = next((copy.deepcopy(s) for s in sb["stages"] if "motor" in s), None)
        if solid_tpl is None:
            raise VehicleImportError(f"{solid_base_path} has no solid stage to use as a template")

    stages = []
    for i, st in enumerate(rec.stages, start=1):
        tpl = copy.deepcopy(solid_tpl if st["type"] == "solid" else liquid_tpl)
        table = SOLID_STAGE_FIELDS if st["type"] == "solid" else LIQUID_STAGE_FIELDS
        given = [k for k in st if k != "type"]
        for f in REQUIRED_STAGE:
            if f not in given:
                raise VehicleImportError(f"{rec.key}: stage {i} is missing {f}")
        if not any(f in given for f in THRUST_FIELDS):
            raise VehicleImportError(f"{rec.key}: stage {i} gives no thrust - one of "
                                     f"{', '.join(THRUST_FIELDS)} is needed")
        if st.get("isp_effective_mode") is not None and \
                str(st["isp_effective_mode"].value) == "user" and "isp_effective_user_s" not in given:
            raise VehicleImportError(
                f"{rec.key}: stage {i} asks for isp_effective_mode = user but gives no "
                f"isp_effective_user_s. Inheriting another vehicle's effective Isp here would be "
                f"silently wrong, so give the value or choose mode 'vacuum' or 'weighted'.")
        for col in given:
            if col not in table:
                raise VehicleImportError(f"{rec.key}: stage {i} ({st['type']}) has no field {col!r}; "
                                   f"known fields are {', '.join(sorted(table))}")
            path, _cast = table[col]
            _set(tpl, path, st[col].value, st[col].source)
            rep.referenced.append((f"stages.{i - 1}.{path}", st[col].value, st[col].source))
        _set(tpl, "name", f"{rec.name or rec.key} stage {i}", "label", "user")
        # a stage given an absolute thrust must not also be driven by the base file's T/W, and vice versa
        if st["type"] == "liquid":
            if "thrust_vac_per_engine_N" in given and "thrust_to_weight_ignition" not in given:
                _set(tpl, "engine.thrust_to_weight_ignition", None,
                     "fixed-thrust mode: the published thrust is used directly", "user")
            elif "thrust_to_weight_ignition" in given and "thrust_vac_per_engine_N" not in given:
                _set(tpl, "engine.thrust_vac_per_engine_N", None,
                     "rubber-engine mode: thrust follows the published T/W", "user")
        stages.append(tpl)
    doc["stages"] = stages

    for col, val in rec.fields.items():
        path, _cast = VEHICLE_FIELDS[col]
        _set(doc, path, val.value, val.source)
        rep.referenced.append((path, val.value, val.source))

    when = retrieved or datetime.date.today().isoformat()
    doc["meta"] = {
        "name": rec.name or rec.key,
        "description": (rec.description or f"Imported vehicle {rec.key}")
        + f" | imported from: {rec.source} | retrieved {when}",
    }

    referenced = {p for p, _v, _s in rep.referenced}
    _warn_on_scale(doc, base, rec, rep, referenced, base_path)
    for p in _paths_of(doc):
        if p in referenced or p.startswith("meta"):
            continue
        leaf = doc
        for k in p.split("."):
            leaf = leaf[int(k)] if isinstance(leaf, list) else leaf[k]
        if leaf.get("t") == "assumed":
            rep.assumed.append((p, leaf.get("v")))
        else:                                   # a book reference or a run option from the base file
            rep.inherited.append((p, leaf.get("v")))
    return doc, rep


def _warn_on_scale(doc, base, rec, rep, referenced, base_path) -> None:
    """Flag absolute-mass assumptions carried from a base design of a very different size.

    A stage template cloned from another vehicle brings its kg constants with it. Those are a
    rounding error on a vehicle of the same class and a dominant term on one ten times smaller, so
    whenever the payload masses differ by more than SCALE_WARN_RATIO the report names every such
    leaf the sheet did not override. This is the import's most likely way of being quietly wrong.
    """
    want = rec.fields.get("payload_mass_kg")
    try:
        have = float(base["mission"]["payload_mass_kg"]["v"])
    except (KeyError, TypeError, ValueError):
        return
    if want is None or not have or not want.value:
        return
    ratio = max(float(want.value) / have, have / float(want.value))
    if ratio < SCALE_WARN_RATIO:
        return
    carried = []
    for i in range(len(doc["stages"])):
        for f in SCALE_SENSITIVE:
            path = f"stages.{i}.{f}"
            if path in referenced:
                continue
            leaf = doc["stages"][i]
            try:
                for k in f.split("."):
                    leaf = leaf[k]
            except (KeyError, TypeError):
                continue
            if isinstance(leaf, dict) and leaf.get("v") not in (None, 0, 0.0):
                carried.append(f"{path} = {leaf['v']}")
    if carried:
        rep.warnings.append(
            f"payload mass {want.value:,.0f} kg is {ratio:.0f}x away from the base configuration's "
            f"{have:,.0f} kg ({os.path.basename(str(base_path))}), and these absolute mass "
            f"assumptions were carried over unchanged and do NOT scale: "
            + "; ".join(carried) +
            ". Set the matching sheet columns, or import against a base design of a similar class.")


HEADER = ("# AUTO-GENERATED by launch_vehicle.vehicle_import (R16) - regenerate rather than hand-edit.\n"
          "# Source: {source}\n"
          "# {n_ref} leaves came from that source (t = reference); {n_ass} are the tool's own\n"
          "# estimates (t = assumed); the rest are book references carried over from the base\n"
          "# configuration. The source supplied nothing about stage dry or propellant masses,\n"
          "# structure, tankage or engine envelopes - the tool predicts those, which is exactly what\n"
          "# makes this file a validation case rather than a datasheet.\n")


def write_design(rec: VehicleRecord, out_dir, base_path=DEFAULT_BASE,
                 solid_base_path=DEFAULT_SOLID_BASE, retrieved=None):
    """Write `<out_dir>/<key>.yaml` and return the ImportReport, with .path set."""
    doc, rep = build_design(rec, base_path, solid_base_path, retrieved)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(str(out_dir), f"{rec.key}.yaml")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(HEADER.format(source=rec.source, n_ref=rep.n_referenced, n_ass=rep.n_assumed))
        yaml.safe_dump(doc, fh, sort_keys=False, width=220)
    rep.path = path
    return rep


def import_sheet(sheet_path, out_dir, base_path=DEFAULT_BASE, solid_base_path=DEFAULT_SOLID_BASE,
                 retrieved=None) -> list:
    """Read a sheet and write one annotated design per row. Returns the reports."""
    return [write_design(rec, out_dir, base_path, solid_base_path, retrieved)
            for rec in read_any(sheet_path)]


def write_template_csv(path) -> str:
    """Write an empty sheet with every understood column, as a starting point for a new source."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(vehicle_sheet_columns())
    return str(path)
