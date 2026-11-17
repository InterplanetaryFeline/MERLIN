"""Winds-aloft profiles: the launch site's own wind, read from a file instead of assumed.

The book's flight-load recipe (Sec. 9.1.6.3 step 4, p.573) says to "use the launch site's winds-aloft profile
to determine wind gust speed", and then prints one site's profile - the Atlantic Missile Range 95 % envelope of
Fig. 9.35. Hard-coding that fit means every vehicle is designed for Cape Canaveral, whatever pad it flies from.
This module lets a design name its own profile, from a CSV or an Excel sheet, while keeping the book's curve as
the default and as the yardstick everything else is drawn against.

Steady wind and gust speed are NOT the same input
-------------------------------------------------
This is the distinction that decides whether the feature helps or quietly halves your design load.

* The book's AMR curve is an **envelope**: a 95-percentile worst case that already contains the gust, and step 4
  feeds it straight in as v_w. A profile of `kind: gust_envelope` is used exactly that way.
* A balloon sounding, or a range reference atmosphere's mean profile, is a **steady** wind. The gust rides on
  top of it. A profile of `kind: steady` therefore requires an explicit `gust_increment_mps`, and the module
  REFUSES to run without one rather than picking a number - the book gives no increment for an arbitrary site,
  and inventing one here would be indistinguishable from the answer being right.

An ensemble, not a profile
--------------------------
One sounding is not a design wind. Real practice is to fly an ensemble of soundings and take the governing
load, not the governing wind, because the worst wind and the worst load are at different altitudes for
different vehicles. `load()` therefore accepts several files, and loads.standard_cases keeps the case that
governs and records which profile produced it.
"""
from __future__ import annotations

import glob
import math
import os
from dataclasses import dataclass, field


class WindError(ValueError):
    pass


# the book's own fit, kept as a built-in so the default behaviour is unchanged and comparable
BOOK_AMR_95 = "book_amr_95"
KINDS = ("gust_envelope", "steady")


def book_amr_95_mps(h_m: float) -> float:
    """Book Fig. 9.35 (p.572): SI curve fit to the Atlantic Missile Range 95 % wind profile envelope.

    h is height above the ground; the book writes the fit in km. Note the step at 20 km is the book's own:
    the fit falls to 24.384 m/s there rather than continuing the 14-20 km ramp down to 22.5 m/s.
    """
    hk = max(h_m, 0.0) / 1000.0
    if hk < 9.6:
        return 6.9288 * hk + 9.144
    if hk < 14.0:
        return 76.2
    if hk < 20.0:
        return 76.2 - 8.9474 * (hk - 14.0)
    return 24.384


@dataclass
class WindProfile:
    """Horizontal wind speed against altitude, with the units and meaning of the numbers declared."""
    name: str
    altitudes_m: list
    speeds_mps: list
    kind: str = "gust_envelope"
    directions_deg: list = field(default_factory=list)
    gust_increment_mps: float = 0.0
    source: str = ""
    path: str = ""

    def __post_init__(self):
        if self.kind not in KINDS:
            raise WindError(f"wind profile '{self.name}': kind must be one of {KINDS}, got {self.kind!r}")
        if len(self.altitudes_m) != len(self.speeds_mps):
            raise WindError(f"wind profile '{self.name}': {len(self.altitudes_m)} altitudes but "
                            f"{len(self.speeds_mps)} speeds")
        if len(self.altitudes_m) < 2:
            raise WindError(f"wind profile '{self.name}': needs at least two altitudes to interpolate")
        pairs = sorted(zip(self.altitudes_m, self.speeds_mps,
                           self.directions_deg or [None] * len(self.altitudes_m)))
        self.altitudes_m = [a for a, _s, _d in pairs]
        self.speeds_mps = [s for _a, s, _d in pairs]
        self.directions_deg = [d for _a, _s, d in pairs] if self.directions_deg else []
        if any(b - a <= 0 for a, b in zip(self.altitudes_m, self.altitudes_m[1:])):
            raise WindError(f"wind profile '{self.name}': duplicate altitude in the data")
        if any(s < 0 for s in self.speeds_mps):
            raise WindError(f"wind profile '{self.name}': negative wind speed")
        if self.kind == "steady" and self.gust_increment_mps <= 0.0:
            raise WindError(
                f"wind profile '{self.name}' is declared as a STEADY wind, so the book's recipe needs a gust "
                f"speed on top of it, and the book gives no gust increment for an arbitrary site. State "
                f"wind.gust_increment_mps in the design, or declare the profile as 'gust_envelope' if the data "
                f"already is a worst-case envelope.")

    # ------------------------------------------------------------------ evaluation
    def steady_at(self, h_m: float) -> float:
        """Interpolated profile speed, held flat outside the data rather than extrapolated."""
        h = max(h_m, 0.0)
        a, s = self.altitudes_m, self.speeds_mps
        if h <= a[0]:
            return s[0]
        if h >= a[-1]:
            return s[-1]
        for lo in range(len(a) - 1):
            if a[lo] <= h <= a[lo + 1]:
                f = (h - a[lo]) / (a[lo + 1] - a[lo])
                return s[lo] + f * (s[lo + 1] - s[lo])
        return s[-1]

    def gust_at(self, h_m: float) -> float:
        """The speed the book's step 4 wants: the envelope itself, or steady plus the stated increment."""
        return self.steady_at(h_m) + (self.gust_increment_mps if self.kind == "steady" else 0.0)

    @property
    def top_m(self) -> float:
        return self.altitudes_m[-1]

    @property
    def peak_mps(self) -> float:
        return max(self.gust_at(h) for h in self.altitudes_m)

    @property
    def peak_altitude_m(self) -> float:
        return max(self.altitudes_m, key=self.gust_at)

    def covers(self, h_m: float) -> bool:
        return self.altitudes_m[0] <= h_m <= self.altitudes_m[-1]


class _BookProfile(WindProfile):
    """The book's fit, wrapped so it presents the same interface as a file-read profile.

    Sampled rather than reimplemented: the curve is a piecewise fit with a deliberate step at 20 km, and
    sampling it at the breakpoints keeps the step exactly where the book puts it.
    """

    def __init__(self):
        a = [0.0, 9599.0, 9600.0, 13999.0, 14000.0, 19999.0, 20000.0, 30000.0]
        super().__init__(name=BOOK_AMR_95, altitudes_m=a, speeds_mps=[book_amr_95_mps(h) for h in a],
                         kind="gust_envelope",
                         source="Book Fig. 9.35 (p.572): SI fit to the Atlantic Missile Range 95 % wind "
                                "profile envelope. An ENVELOPE, so it is used directly as the gust speed.")

    def steady_at(self, h_m: float) -> float:
        return book_amr_95_mps(h_m)


def book_profile() -> WindProfile:
    return _BookProfile()


# ------------------------------------------------------------------------------- reading files
#: accepted column headings -> (canonical field, multiplier onto the SI unit)
_ALT_COLUMNS = {"altitude_m": 1.0, "alt_m": 1.0, "height_m": 1.0, "h_m": 1.0, "z_m": 1.0,
                "altitude_km": 1e3, "alt_km": 1e3, "height_km": 1e3, "h_km": 1e3,
                "altitude_ft": 0.3048, "height_ft": 0.3048}
_SPEED_COLUMNS = {"speed_mps": 1.0, "wind_speed_mps": 1.0, "wind_mps": 1.0, "v_mps": 1.0, "speed_m_s": 1.0,
                  "speed_kt": 0.514444, "wind_speed_kt": 0.514444, "speed_knots": 0.514444,
                  "speed_kmh": 1 / 3.6, "wind_speed_kmh": 1 / 3.6, "speed_mph": 0.44704}
_DIR_COLUMNS = ("direction_deg", "dir_deg", "wind_direction_deg", "heading_deg")


def _norm(s) -> str:
    return str(s or "").strip().lower().replace(" ", "_").replace("/", "_").replace("-", "_")


def _pick(headers: list, table: dict, what: str):
    for i, h in enumerate(headers):
        if _norm(h) in table:
            return i, table[_norm(h)]
    raise WindError(f"no {what} column found. Headers were {headers}; accepted names are "
                    f"{', '.join(sorted(table))}")


def _rows_to_profile(headers, rows, name, kind, gust_increment_mps, source, path) -> WindProfile:
    ia, fa = _pick(headers, _ALT_COLUMNS, "altitude")
    iv, fv = _pick(headers, _SPEED_COLUMNS, "wind speed")
    idir = next((i for i, h in enumerate(headers) if _norm(h) in _DIR_COLUMNS), None)
    alts, spd, dirs = [], [], []
    for n, r in enumerate(rows, start=2):
        if all(str(c).strip() == "" for c in r if c is not None):
            continue
        try:
            alts.append(float(str(r[ia]).replace(",", "")) * fa)
            spd.append(float(str(r[iv]).replace(",", "")) * fv)
        except (TypeError, ValueError, IndexError) as e:
            raise WindError(f"{path or name}: row {n} is not numeric: {r}") from e
        if idir is not None and idir < len(r) and str(r[idir]).strip() != "":
            dirs.append(float(str(r[idir]).replace(",", "")))
    if not alts:
        raise WindError(f"{path or name}: no data rows")
    if dirs and len(dirs) != len(alts):
        dirs = []                                  # a partly filled direction column is no direction column
    return WindProfile(name=name, altitudes_m=alts, speeds_mps=spd, kind=kind, directions_deg=dirs,
                       gust_increment_mps=gust_increment_mps, source=source, path=str(path or ""))


#: metadata a file may declare about itself, in `# key: value` comment lines above the header row
_META_KEYS = ("kind", "gust_increment_mps", "source")


def _read_meta(lines) -> dict:
    """Pull `# kind: steady` style declarations out of a file's comment header.

    A file that knows what it is should be able to say so. Without this the kind comes only from the design's
    wind block, which is one setting for the whole ensemble - so a steady sounding listed beside an envelope
    would be read as an envelope, and its gust would be counted once instead of twice. That is precisely the
    mistake this module exists to prevent, so the file's own declaration wins over the block's default.
    """
    meta = {}
    for raw in lines:
        t = str(raw).strip().strip('"').strip()
        if not t.startswith("#"):
            break
        body = t.lstrip("#").strip()
        if ":" not in body:
            continue
        k, _, v = body.partition(":")
        k = _norm(k)
        if k in _META_KEYS:
            meta[k] = v.strip()
    return meta


def read_csv(path, kind="gust_envelope", gust_increment_mps=0.0, source="", name=None) -> WindProfile:
    """Read a two- or three-column wind profile. Units come from the column NAME, never assumed.

    `# kind:` and `# gust_increment_mps:` comment lines in the file override the arguments, so a sounding
    cannot be mistaken for a gust envelope just because it was listed beside one.
    """
    import csv
    with open(path, newline="", encoding="utf-8-sig") as fh:
        raw_lines = fh.read().splitlines()
    meta = _read_meta(raw_lines)
    import io
    rows = [r for r in csv.reader(io.StringIO("\n".join(raw_lines)))
            if r and not str(r[0]).lstrip().strip('"').lstrip().startswith("#")]
    if len(rows) < 2:
        raise WindError(f"{path}: expected a header row and at least two data rows")
    if meta.get("kind"):
        if meta["kind"] not in KINDS:
            raise WindError(f"{path}: declares kind '{meta['kind']}'; expected one of {', '.join(KINDS)}")
        kind = meta["kind"]
    if meta.get("gust_increment_mps"):
        try:
            gust_increment_mps = float(meta["gust_increment_mps"])
        except ValueError as e:
            raise WindError(f"{path}: gust_increment_mps '{meta['gust_increment_mps']}' is not a number") from e
    return _rows_to_profile(rows[0], rows[1:], name or os.path.splitext(os.path.basename(str(path)))[0],
                            kind, gust_increment_mps,
                            meta.get("source") or source or f"read from {os.path.basename(str(path))}",
                            path)


def read_excel(path, kind="gust_envelope", gust_increment_mps=0.0, source="", name=None,
               sheet=None) -> WindProfile:
    """Read the same columns from the first sheet (or a named one) of an .xlsx workbook."""
    try:
        from openpyxl import load_workbook
    except ImportError as e:                                   # pragma: no cover - openpyxl ships with the tool
        raise WindError("reading .xlsx needs openpyxl; export the sheet as CSV instead") from e
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet] if sheet else wb[wb.sheetnames[0]]
    rows = [list(r) for r in ws.iter_rows(values_only=True) if any(c is not None for c in r)]
    wb.close()
    if len(rows) < 2:
        raise WindError(f"{path}: expected a header row and at least two data rows")
    return _rows_to_profile(rows[0], rows[1:], name or os.path.splitext(os.path.basename(str(path)))[0],
                            kind, gust_increment_mps, source or f"read from {os.path.basename(str(path))}",
                            path)


def read_any(path, **kw) -> WindProfile:
    ext = os.path.splitext(str(path))[1].lower()
    if ext == ".csv":
        return read_csv(path, **kw)
    if ext in (".xlsx", ".xlsm"):
        return read_excel(path, **kw)
    raise WindError(f"{path}: wind profiles are read from .csv or .xlsx")


def load(spec_or_block, root: str = ".") -> list:
    """Resolve a design's `wind:` block into a list of profiles. Always returns at least one.

    `profile` may be the built-in name, one file path, a glob matching several, or a list of any of those.
    Several profiles are an ENSEMBLE: every one is flown and the governing load is kept (see
    loads.standard_cases), because the worst wind and the worst load are not at the same altitude.
    """
    block = spec_or_block or {}
    ref = block.get("profile") or BOOK_AMR_95
    kind = str(block.get("kind") or "gust_envelope")
    gust = float(block.get("gust_increment_mps") or 0.0)
    refs = ref if isinstance(ref, (list, tuple)) else [ref]
    out = []
    for r in refs:
        r = str(r).strip()
        if not r or r.lower() in (BOOK_AMR_95, "book", "default"):
            out.append(book_profile())
            continue
        p = r if os.path.isabs(r) else os.path.join(root, r)
        matches = sorted(glob.glob(p)) if any(c in p for c in "*?[") else [p]
        if not matches:
            raise WindError(f"wind profile '{r}' matched no file (looked under {root})")
        for m in matches:
            if not os.path.exists(m):
                raise WindError(f"wind profile file not found: {m}")
            out.append(read_any(m, kind=kind, gust_increment_mps=gust))
    if not out:
        out.append(book_profile())
    return out


def summarise(profiles: list) -> str:
    bits = []
    for p in profiles:
        bits.append(f"{p.name} ({p.kind}, peak {p.peak_mps:.1f} m/s at "
                    f"{p.peak_altitude_m / 1e3:.1f} km, data to {p.top_m / 1e3:.1f} km)")
    return "; ".join(bits)


def write_template_csv(path, profile: WindProfile | None = None) -> str:
    """Write a profile out in the format `read_csv` accepts, so the book's curve can be used as a starting point."""
    import csv
    p = profile or book_profile()
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["# wind profile for launch_vehicle. altitude_m is height above the ground;"])
        w.writerow([f"# speed_mps is a {p.kind}. Source: {p.source}"])
        w.writerow(["altitude_m", "speed_mps"])
        for h, v in zip(p.altitudes_m, p.speeds_mps):
            w.writerow([f"{h:.1f}", f"{v:.3f}"])
    return str(path)
