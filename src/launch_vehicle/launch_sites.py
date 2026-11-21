"""Real launch sites, so a design can say WHERE it flies from instead of carrying a bare latitude.

Latitude is not a free parameter. It sets the Earth-rotation credit (orbit.site_rotation_speed) and the
azimuth needed for a given inclination (orbit.launch_azimuth_deg, sin b = cos i / cos lat), and those two
together decide a few hundred m/s of the budget. Typing 28.5 and forgetting what site that was is how a
design ends up claiming a Kourou rotation credit from a Plesetsk latitude.

So: name the site, and the latitude follows from the library. The rules match the engine database's.

* The library only ever FILLS latitude. A design that names a site and states its own latitude keeps its own
  and is told the two disagree - the user's number always wins, it is never silently replaced.
* Choosing a site leaves longitude and altitude alone. Longitude is carried in the library for reference and
  is used by nothing here, because ground tracks and launch windows are not modelled. Altitude is not in the
  library at all rather than being guessed at zero.
* `site: null` is the Custom option: the latitude in the design file is used as given and nothing is checked
  against a library row.

THE INCLINATION FLOOR, which is the one piece of real engineering this module adds.

A direct ascent from latitude phi cannot reach an inclination below |phi|, because sin b = cos i / cos phi
needs cos i <= cos phi. That floor is PHYSICS and is computed here from the latitude. orbit.py already
refuses to fly below it rather than modelling a dog-leg, and performance.py reports such a sweep point as
infeasible; this module is what lets the GUI say so BEFORE the run, and nudge the inclination up to the floor
when the user picks a high-latitude site.

What this module does NOT know is range safety. Every real site also has azimuth corridors fixed by what the
vehicle may overfly, which cut the band further and vary per pad, per vehicle and per year. None of that is
in the library and none of it has been invented: the floor is a NECESSARY condition for a direct ascent, not
a sufficient one. A site cleared here may still be unable to fly the azimuth in practice.
"""
from __future__ import annotations
import math
import os
import yaml

from .paths import ROOT                                   # noqa: E402
DEFAULT_PATH = os.path.join(ROOT, "config", "launch_sites.yaml")

#: how far the design's own latitude may sit from the named site's before the tool complains, in degrees.
#: 0.05 deg is about 5.5 km - finer than the pad-to-pad spread inside a large range, so a user who typed the
#: coordinate of a different pad at the same cosmodrome is not nagged, while a genuinely wrong site is caught.
LATITUDE_TOLERANCE_DEG = 0.05

#: the Custom choice: use the latitude in the design file and check nothing.
CUSTOM = ""

_CACHE: dict[str, list[dict]] = {}


class LaunchSiteError(ValueError):
    pass


def load(path: str | None = None) -> list[dict]:
    """Every row in the library, in file order. Cached per path: the file does not change mid-run."""
    p = path or DEFAULT_PATH
    if p not in _CACHE:
        if not os.path.exists(p):
            raise LaunchSiteError(f"launch site library not found: {p}")
        with open(p, "r", encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
        rows = doc.get("sites") or []
        if not rows:
            raise LaunchSiteError(f"launch site library {p} has no 'sites' list")
        for r in rows:
            for k in ("name", "latitude_deg", "region"):
                if r.get(k) in (None, ""):
                    raise LaunchSiteError(f"launch site row {r.get('name', '?')!r} is missing {k!r}")
            if r["region"] not in CONTINENTS:
                raise LaunchSiteError(f"launch site {r['name']!r} has region {r['region']!r}; the region is the "
                                      f"continent, one of {', '.join(CONTINENTS)}")
            if not -90.0 <= float(r["latitude_deg"]) <= 90.0:
                raise LaunchSiteError(
                    f"launch site {r['name']!r} has latitude {r['latitude_deg']}, outside [-90, 90]")
        _CACHE[p] = rows
    return _CACHE[p]


def find(name: str, path: str | None = None) -> dict:
    """The row named `name`. Raises with the available names listed, so a typo is self-correcting."""
    rows = load(path)
    for r in rows:
        if r["name"] == name:
            return r
    raise LaunchSiteError(
        f"launch site {name!r} is not in the library. Available: " + ", ".join(r["name"] for r in rows))


def min_direct_inclination_deg(latitude_deg: float) -> float:
    """The lowest inclination a direct ascent from this latitude can reach: |latitude|.

    From sin b = cos i / cos phi, which has a solution only while cos i <= cos phi, i.e. |i| >= |phi|.
    A plane change can go lower and is not modelled anywhere in this tool.
    """
    return abs(float(latitude_deg))


def direct_ascent_azimuths_deg(inclination_deg: float, latitude_deg: float) -> tuple[float, float] | None:
    """The two azimuths that reach `inclination_deg` from `latitude_deg`, or None if none do.

    Returned as (northerly, southerly) measured clockwise from north, both in [0, 360). Both are flyable in
    principle and reach the same inclination; which one a real site may use is a range-safety question this
    tool does not model.

    The normalisation matters for a RETROGRADE orbit. `asin` returns a negative angle whenever cos i < 0, so
    a sun-synchronous ascent from Vandenberg comes out of the raw relation as -9.0 deg, which is not an
    azimuth anyone writes down - it is 351.0 deg. orbit.launch_azimuth_deg keeps the signed value on purpose,
    because it feeds sin and cos where the two are identical; this function is what gets shown to a person, so
    here it is wrapped.
    """
    c = math.cos(math.radians(inclination_deg)) / math.cos(math.radians(latitude_deg))
    if abs(c) > 1.0:
        return None
    b = math.degrees(math.asin(c))
    return b % 360.0, (180.0 - b) % 360.0


def inclination_check(inclination_deg: float, latitude_deg: float) -> dict:
    """Is this inclination reachable from this latitude by a direct ascent?

    Returns {feasible, floor_deg, azimuths_deg, note}. The note is written to be shown to a user as-is.
    """
    floor = min_direct_inclination_deg(latitude_deg)
    az = direct_ascent_azimuths_deg(inclination_deg, latitude_deg)
    if az is None:
        return {"feasible": False, "floor_deg": floor, "azimuths_deg": None,
                "note": (f"inclination {inclination_deg:.2f} deg is below the launch-site latitude "
                         f"{abs(latitude_deg):.2f} deg, so no direct ascent reaches it. The lowest reachable "
                         f"inclination from here is {floor:.2f} deg; going lower needs a plane change, which "
                         "this tool does not model.")}
    return {"feasible": True, "floor_deg": floor, "azimuths_deg": az,
            "note": (f"reachable from latitude {abs(latitude_deg):.2f} deg on azimuth {az[0]:.1f} deg "
                     f"or {az[1]:.1f} deg (range-safety corridors are not modelled)")}


def cascade_map(path: str | None = None) -> dict[str, dict]:
    """site name -> the leaves choosing it should fill, for the GUI's cascade.

    Latitude and longitude. Both are published pad coordinates that the library has authority over, so both are
    pushed. Longitude used to be withheld because nothing consumed it; the impact-point map does - a downrange
    distance cannot be placed on a map without a starting meridian - so it is now a design leaf like latitude.
    Altitude is still not pushed: it is not in the library at all, and inventing one would be worse than a gap.
    """
    out: dict[str, dict] = {}
    for r in load(path):
        lat = float(r["latitude_deg"])
        lon = None if r.get("longitude_deg") is None else float(r["longitude_deg"])
        out[r["name"]] = {
            "mission.launch_site.latitude_deg": lat,
            **({"mission.launch_site.longitude_deg": lon} if lon is not None else {}),
            # not a design leaf: hints the GUI shows beside the field
            "_min_inclination_deg": min_direct_inclination_deg(lat),
            "_longitude_deg": (None if r.get("longitude_deg") is None else float(r["longitude_deg"])),
            "_country": r.get("country") or r.get("region"),
            "_source": r.get("source") or "",
            "_orbital": r.get("orbital", True) is not False,
            "_status": r.get("status") or "",
        }
    return out


#: the order the continents are listed in; a continent the library does not use is simply absent
CONTINENTS = ("North America", "South America", "Europe", "Africa", "Asia", "Oceania")


def choices(path: str | None = None) -> list[tuple]:
    """(value, label, group) triples for the GUI dropdown: Custom first, then every site under its continent.

    The group is the continent, which the page draws as a heading in the list; within a continent the sites
    are in alphabetical order, so a user looking for Esrange does not have to know how the file is ordered.
    The label carries the country and the latitude, because latitude is the only thing the choice actually
    changes and a user picking between Andoya at 69.3 and Esrange at 67.9 deg should not have to pick blind.
    """
    try:
        rows = load(path)
    except LaunchSiteError:
        return []
    out: list[tuple] = [(CUSTOM, "Custom - type a latitude below", None)]
    order = {c: i for i, c in enumerate(CONTINENTS)}
    for r in sorted(rows, key=lambda r: (order.get(r["region"], len(order)), r["region"], r["name"].lower())):
        lat = float(r["latitude_deg"])
        hemi = "N" if lat >= 0 else "S"
        country = r.get("country") or r["region"]
        out.append((r["name"], f"{r['name']} - {country} ({abs(lat):.2f} deg {hemi})", r["region"]))
    return out


def expand_design(design: dict, reg: list, path: str | None = None) -> dict | None:
    """Resolve `mission.launch_site.site` into coordinates. Returns a note, or None if no site is named.

    Called from config_io before the mission block is read, so a design may leave `latitude_deg` null and let
    the site supply it, and so a filled latitude goes through exactly the same validation as a typed one.

    A design that states BOTH keeps its own latitude - the user's number always wins - and the returned note
    carries the disagreement so the report and the GUI can show it.
    """
    m = design.get("mission") or {}
    site_block = m.get("launch_site") or {}
    ref = site_block.get("site")
    ref = ref.get("v") if isinstance(ref, dict) else ref
    if not ref:
        return None
    row = find(ref, path)
    lat = float(row["latitude_deg"])
    have = site_block.get("latitude_deg")
    have = have.get("v") if isinstance(have, dict) else have

    filled, mismatch = [], None
    if have is None:
        site_block["latitude_deg"] = lat
        filled.append("latitude_deg")
        reg.append(dict(path="mission.launch_site.latitude_deg", value=lat, units="deg",
                        description=f"filled from launch site library entry '{row['name']}'",
                        source=f"launch site library: {row.get('source') or row['name']}",
                        provenance="reference"))
    elif abs(float(have) - lat) > LATITUDE_TOLERANCE_DEG:
        mismatch = dict(field="latitude_deg", design=float(have), library=lat,
                        delta_deg=float(have) - lat)

    # Longitude, on exactly the same terms as latitude: filled when the design leaves it out, never overwritten
    # when the design states it. It is consumed only by the impact-point map, so a library row without a
    # longitude is not an error - it just means that design cannot be mapped until a longitude is typed in.
    lon = None if row.get("longitude_deg") is None else float(row["longitude_deg"])
    have_lon = site_block.get("longitude_deg")
    have_lon = have_lon.get("v") if isinstance(have_lon, dict) else have_lon
    if lon is not None and have_lon is None:
        site_block["longitude_deg"] = lon
        filled.append("longitude_deg")
        reg.append(dict(path="mission.launch_site.longitude_deg", value=lon, units="deg",
                        description=f"filled from launch site library entry '{row['name']}'",
                        source=f"launch site library: {row.get('source') or row['name']}",
                        provenance="reference"))
    elif lon is not None and abs(float(have_lon) - lon) > LATITUDE_TOLERANCE_DEG and mismatch is None:
        mismatch = dict(field="longitude_deg", design=float(have_lon), library=lon,
                        delta_deg=float(have_lon) - lon)

    return dict(entry=row["name"], region=row.get("region"), country=row.get("country"),
                latitude_deg=lat, longitude_deg=lon,
                min_inclination_deg=min_direct_inclination_deg(lat),
                filled=filled, mismatch=mismatch, source=row.get("source") or "")


def table_rows(path: str | None = None) -> list[dict]:
    """The whole library as report/GUI rows, with the computed inclination floor alongside."""
    rows = []
    for r in load(path):
        lat = float(r["latitude_deg"])
        rows.append({
            "name": r["name"],
            "region": r["region"],
            "country": r.get("country") or r["region"],
            "latitude_deg": lat,
            "longitude_deg": r.get("longitude_deg"),
            "min_inclination_deg": min_direct_inclination_deg(lat),
            "source": r.get("source") or "",
        })
    return rows
