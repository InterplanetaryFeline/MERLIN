"""Assemble the drop zones into something that can be put on a map, and write them out.

`debris.py` produces, for each jettisoned item, an interval of downrange distance. This module turns those
distances into coordinates and closed areas, and exports them as GeoJSON and KML so they open in a browser map,
Google Earth or QGIS rather than only in this tool.

The chain is deliberately short and each link is a separate module, because each has a different failure mode:

    trajectory   separation state           (a 3-DoF integration of the ascent)
    debris       -> downrange interval      (a ballistic descent plus declared dispersions)
    geodesy      -> coordinates             (walk the arc along the launch azimuth, on a sphere)
    hazard       -> areas, files            (this module: assemble, label, export)

A HAZARD AREA HERE IS A RECTANGLE ALONG A GREAT CIRCLE. Its length is the along-track dispersion interval
`debris` computed; its width is an assumed half-width, because a pitch-plane trajectory has no cross-range state
at all. The width is therefore not a prediction, and `debris.half_width_m` deliberately floors it at the size of
the Coriolis cross-range the model is known to be missing. Every exported area carries that statement in its
own description field, so the caveat travels with the file instead of living only in this docstring - a KML
opened in Google Earth six months from now should still say what it is.

TWO AZIMUTHS. A given inclination is reachable on a northerly or a southerly azimuth, and which one a real range
uses is a range-safety question this tool does not model. Both are offered; the caller picks, and the picked one
is recorded in the output.
"""
from __future__ import annotations
import json
import math
import xml.etree.ElementTree as ET

from . import debris as dbr
from . import geodesy
from . import launch_sites as ls

TRACK_POINTS = 64


class HazardError(RuntimeError):
    """The hazard areas could not be assembled."""


def areas(res, traj, latitude_deg: float, longitude_deg: float | None, azimuth_deg: float,
          dispersion: "dbr.Dispersion | None" = None, dt: float = 0.5,
          atmosphere: str = "book_exponential") -> dict:
    """Impact points and hazard areas for one flight.

    `longitude_deg` may be None: the distances and the dispersion intervals do not need it, so they are still
    computed and returned, and only the coordinates are left out. That is the honest behaviour for a design that
    names no launch site - a latitude alone fixes the physics but not the meridian.

    Returns a dict with `site`, `azimuth_deg`, `half_width_m`, `impacts` (the `debris.Impact` list), `features`
    (one entry per item that comes down, with its point and ring when a longitude is known) and `notes`.
    """
    disp = dispersion or dbr.Dispersion()
    impacts = dbr.resolve(res, traj, latitude_deg, azimuth_deg, dispersion=disp, dt=dt, atmosphere=atmosphere)
    half = dbr.half_width_m(impacts, disp)
    mappable = longitude_deg is not None

    feats = []
    for imp in impacts:
        if imp.fate != "impact":
            continue
        f = {
            "name": imp.name,
            "downrange_m": imp.downrange_m,
            "near_m": imp.downrange_min_m,
            "far_m": imp.downrange_max_m,
            "half_width_m": half,
            "mass_kg": imp.mass_kg,
            "fall_time_s": imp.fall_time_s,
            "impact_v_mps": imp.impact_v_mps,
            "point": None,
            "ring": None,
            "sphere_error_m": geodesy.position_error_m(imp.downrange_m),
            "description": _describe(imp, half),
        }
        if mappable:
            f["point"] = geodesy.destination(latitude_deg, longitude_deg, azimuth_deg, imp.downrange_m)
            f["ring"] = geodesy.corridor_polygon(latitude_deg, longitude_deg, azimuth_deg,
                                                 imp.downrange_min_m, imp.downrange_max_m, half)
        feats.append(f)

    out = {
        "vehicle": res.spec.name,
        "site": {"latitude_deg": latitude_deg, "longitude_deg": longitude_deg,
                 "name": (getattr(res.spec, "launch_site_note", None) or {}).get("entry")
                 if isinstance(getattr(res.spec, "launch_site_note", None), dict) else None},
        "azimuth_deg": azimuth_deg,
        "half_width_m": half,
        "dispersion": {"sep_speed_frac": disp.sep_speed_frac, "sep_gamma_deg": disp.sep_gamma_deg,
                       "cd": list(disp.cd), "cross_half_width_m": disp.cross_half_width_m},
        "impacts": impacts,
        "features": feats,
        "ground_track": (geodesy.track(latitude_deg, longitude_deg, azimuth_deg,
                                       max([f["far_m"] for f in feats], default=traj.downrange_m),
                                       n=TRACK_POINTS) if mappable else None),
        "notes": _notes(impacts, half, disp, mappable),
    }
    return out


def _describe(imp, half_m: float) -> str:
    """The sentence that travels with an exported area. Written to be read by someone who did not run the tool."""
    return (f"{imp.name}: {imp.mass_kg:.0f} kg separating at {imp.h_jettison_m/1e3:.0f} km and "
            f"{imp.v_jettison_mps:.0f} m/s, falling for {imp.fall_time_s:.0f} s to impact at "
            f"{imp.impact_v_mps:.0f} m/s. Nominal impact {imp.downrange_m/1e3:.0f} km downrange; this area "
            f"spans {imp.downrange_min_m/1e3:.0f} to {imp.downrange_max_m/1e3:.0f} km along track and "
            f"{half_m/1e3:.0f} km either side of it. The along-track extent is a computed dispersion; the width "
            f"is an ASSUMPTION, since the trajectory model has no cross-range state. CONCEPTUAL DESIGN "
            f"ESTIMATE, NOT A RANGE-SAFETY PRODUCT: no breakup, wind, Coriolis or casualty-probability "
            f"analysis is included.")


def _notes(impacts, half_m, disp, mappable) -> list:
    n = []
    if not mappable:
        n.append("no launch-site longitude, so distances are given but no coordinates: name a site from the "
                 "library, or type mission.launch_site.longitude_deg, to place these on a map")
    n.append(f"corridor half-width {half_m/1e3:.0f} km. This is not a predicted cross-range: a pitch-plane "
             f"trajectory has none. It is the larger of the stated half-width and the Coriolis cross-range the "
             f"descent model omits.")
    n.append(f"along-track dispersion from an assumed {100*disp.sep_speed_frac:.0f} % separation-speed and "
             f"{disp.sep_gamma_deg:.1f} deg flight-path-angle uncertainty, plus a Cd bracket of "
             f"{disp.cd[0]} to {disp.cd[-1]}. The speed assumption dominates; see debris.py.")
    marginal = [i for i in impacts if i.fate == "marginal"]
    if marginal:
        n.append("no area is drawn for: " + "; ".join(
            f"{i.name} (nominal impact {i.downrange_m/1e3:.0f} km, but the dispersion is not localisable)"
            for i in marginal) + " - see the row notes")
    orbital = [i for i in impacts if i.fate == "in_orbit"]
    if orbital:
        n.append("not every jettisoned item comes down: " +
                 "; ".join(f"{i.name} stays in orbit (perigee "
                           f"{'n/a' if i.perigee_altitude_m is None else format(i.perigee_altitude_m/1e3, '.0f')} km)"
                           for i in orbital))
    failed = [i for i in impacts if i.fate == "failed"]
    if failed:
        n.append("descent failed for: " + ", ".join(i.name for i in failed))
    lever = max([i.km_per_percent_speed for i in impacts if i.fate == "impact"], default=0.0)
    if lever:
        n.append(f"sensitivity: 1 % of separation-speed error moves an impact point up to {lever/1e3:.0f} km, so "
                 f"these zones are only as good as the vehicle's performance prediction")
    return n


# --------------------------------------------------------------------------- exports
def to_geojson(a: dict) -> dict:
    """GeoJSON FeatureCollection: the pad, the ground track, and one polygon plus one point per item."""
    if a["site"]["longitude_deg"] is None:
        raise HazardError("cannot write GeoJSON without a launch-site longitude")
    lat, lon = a["site"]["latitude_deg"], a["site"]["longitude_deg"]
    feats = [{"type": "Feature",
              "properties": {"name": a["site"]["name"] or "launch site", "kind": "launch_site"},
              "geometry": {"type": "Point", "coordinates": [lon, lat]}}]
    if a["ground_track"]:
        feats.append({"type": "Feature",
                      "properties": {"name": f"ground track, azimuth {a['azimuth_deg']:.1f} deg",
                                     "kind": "ground_track"},
                      "geometry": {"type": "LineString",
                                   "coordinates": [[p[1], p[0]] for p in a["ground_track"]]}})
    for f in a["features"]:
        if f["ring"]:
            feats.append({"type": "Feature",
                          "properties": {"name": f"{f['name']} hazard area", "kind": "hazard_area",
                                         "description": f["description"]},
                          "geometry": {"type": "Polygon",
                                       "coordinates": [[[p[1], p[0]] for p in f["ring"]]]}})
        if f["point"]:
            feats.append({"type": "Feature",
                          "properties": {"name": f"{f['name']} nominal impact", "kind": "nominal_impact",
                                         "description": f["description"]},
                          "geometry": {"type": "Point",
                                       "coordinates": [f["point"][1], f["point"][0]]}})
    return {"type": "FeatureCollection",
            "properties": {"vehicle": a["vehicle"], "notes": a["notes"]},
            "features": feats}


def write_geojson(a: dict, path: str) -> str:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(to_geojson(a), fh, indent=1)
    return path


def to_kml(a: dict) -> str:
    """KML, so the areas open in Google Earth with their caveats attached to each placemark."""
    if a["site"]["longitude_deg"] is None:
        raise HazardError("cannot write KML without a launch-site longitude")
    kml = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
    doc = ET.SubElement(kml, "Document")
    ET.SubElement(doc, "name").text = f"{a['vehicle']} - jettison hazard areas"
    ET.SubElement(doc, "description").text = "\n".join(a["notes"])

    for sid, color, width in (("area", "4d0000ff", 1), ("track", "ff00ffff", 2)):
        st = ET.SubElement(doc, "Style", id=sid)
        ls_ = ET.SubElement(st, "LineStyle")
        ET.SubElement(ls_, "color").text = "ff0000ff" if sid == "area" else color
        ET.SubElement(ls_, "width").text = str(width)
        if sid == "area":
            ET.SubElement(ET.SubElement(st, "PolyStyle"), "color").text = color

    site = ET.SubElement(doc, "Placemark")
    ET.SubElement(site, "name").text = a["site"]["name"] or "launch site"
    ET.SubElement(ET.SubElement(site, "Point"), "coordinates").text = \
        f"{a['site']['longitude_deg']:.6f},{a['site']['latitude_deg']:.6f},0"

    if a["ground_track"]:
        pm = ET.SubElement(doc, "Placemark")
        ET.SubElement(pm, "name").text = f"ground track, azimuth {a['azimuth_deg']:.1f} deg"
        ET.SubElement(pm, "styleUrl").text = "#track"
        ET.SubElement(ET.SubElement(pm, "LineString"), "coordinates").text = \
            " ".join(f"{p[1]:.6f},{p[0]:.6f},0" for p in a["ground_track"])

    for f in a["features"]:
        if f["ring"]:
            pm = ET.SubElement(doc, "Placemark")
            ET.SubElement(pm, "name").text = f"{f['name']} hazard area"
            ET.SubElement(pm, "description").text = f["description"]
            ET.SubElement(pm, "styleUrl").text = "#area"
            poly = ET.SubElement(pm, "Polygon")
            ring = ET.SubElement(ET.SubElement(ET.SubElement(poly, "outerBoundaryIs"), "LinearRing"),
                                 "coordinates")
            ring.text = " ".join(f"{p[1]:.6f},{p[0]:.6f},0" for p in f["ring"])
        if f["point"]:
            pm = ET.SubElement(doc, "Placemark")
            ET.SubElement(pm, "name").text = f"{f['name']} nominal impact"
            ET.SubElement(pm, "description").text = f["description"]
            ET.SubElement(ET.SubElement(pm, "Point"), "coordinates").text = \
                f"{f['point'][1]:.6f},{f['point'][0]:.6f},0"

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(kml, encoding="unicode")


def write_kml(a: dict, path: str) -> str:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(to_kml(a))
    return path


def table_rows(a: dict) -> list:
    """The drop zones as report/GUI rows."""
    rows = []
    for i in a["impacts"]:
        if i.fate == "marginal":
            # the nominal impact is real and worth showing; the window is not, which is the whole point
            rows.append({"item": i.name, "fate": i.fate, "downrange_km": i.downrange_m / 1e3,
                         "window_km": None, "lat": None, "lon": None,
                         "fall_time_s": i.fall_time_s, "impact_v_mps": i.impact_v_mps,
                         "note": i.notes[0] if i.notes else ""})
            continue
        if i.fate != "impact":
            rows.append({"item": i.name, "fate": i.fate, "downrange_km": None, "window_km": None,
                         "lat": None, "lon": None, "fall_time_s": None, "impact_v_mps": None,
                         "note": i.notes[0] if i.notes else ""})
            continue
        f = next((x for x in a["features"] if x["name"] == i.name), None)
        pt = (f or {}).get("point")
        rows.append({"item": i.name, "fate": i.fate,
                     "downrange_km": i.downrange_m / 1e3,
                     "window_km": (i.downrange_max_m - i.downrange_min_m) / 1e3,
                     "lat": None if pt is None else pt[0], "lon": None if pt is None else pt[1],
                     "fall_time_s": i.fall_time_s, "impact_v_mps": i.impact_v_mps,
                     "note": f"state {i.state_spread_m/1e3:.0f} km, drag {i.drag_spread_m/1e3:.0f} km"})
    return rows


def to_payload(a: dict) -> dict:
    """The areas as plain JSON types, for the GUI and for writing to disk.

    `areas()` holds `debris.Impact` dataclasses, which are the right thing for Python callers and the wrong
    thing for a socket, so the conversion lives here rather than in the server.
    """
    return {
        "vehicle": a["vehicle"],
        "site": a["site"],
        "azimuth_deg": a["azimuth_deg"],
        "half_width_m": a["half_width_m"],
        "dispersion": a["dispersion"],
        "ground_track": [[p[0], p[1]] for p in (a["ground_track"] or [])] or None,
        "notes": a["notes"],
        "rows": table_rows(a),
        "features": [{"name": f["name"], "description": f["description"],
                      "downrange_m": f["downrange_m"], "near_m": f["near_m"], "far_m": f["far_m"],
                      "half_width_m": f["half_width_m"], "mass_kg": f["mass_kg"],
                      "fall_time_s": f["fall_time_s"], "impact_v_mps": f["impact_v_mps"],
                      "sphere_error_m": f["sphere_error_m"],
                      "point": None if f["point"] is None else [f["point"][0], f["point"][1]],
                      "ring": None if f["ring"] is None else [[p[0], p[1]] for p in f["ring"]]}
                     for f in a["features"]],
        "orbital": [{"name": i.name,
                     "perigee_altitude_m": i.perigee_altitude_m,
                     "apogee_altitude_m": i.apogee_altitude_m,
                     "v_inertial_mps": i.v_inertial_mps,
                     "note": i.notes[0] if i.notes else ""}
                    for i in a["impacts"] if i.fate == "in_orbit"],
    }


def azimuth_options(inclination_deg: float, latitude_deg: float) -> list:
    """The azimuths a direct ascent could use, for the caller to choose between.

    The northerly and southerly solutions coincide when the target inclination equals the site latitude: that
    is the one case where the ascent plane is tangent to the latitude circle, so there is a single azimuth, not
    two identical choices. Offering it twice would invite a user to think the pick mattered.
    """
    az = ls.direct_ascent_azimuths_deg(inclination_deg, latitude_deg)
    if az is None:
        return []
    if abs(az[0] - az[1]) < 0.05:
        return [{"azimuth_deg": az[0],
                 "label": f"{az[0]:.1f} deg - the only direct azimuth, the target inclination equalling the "
                          f"site latitude"}]
    return [{"azimuth_deg": az[0], "label": f"northerly {az[0]:.1f} deg"},
            {"azimuth_deg": az[1], "label": f"southerly {az[1]:.1f} deg"}]
