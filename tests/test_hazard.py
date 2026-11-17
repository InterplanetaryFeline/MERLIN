"""Assembling the drop zones into map areas and files.

The behaviour worth pinning is what happens WITHOUT a launch-site longitude. A latitude alone fixes the
physics - the rotation credit, the azimuth relation, the whole descent - but not the meridian, so the distances
are knowable and the coordinates are not. The tool must then give the distances and say plainly why there is no
map, rather than either refusing the whole calculation or quietly defaulting to Greenwich and drawing an
impact point in the Gulf of Guinea.

The rest is export fidelity: a KML that does not parse is worse than no KML, and a hazard area whose caveat
has been stripped off is worse still, because the file outlives the conversation that produced it.
"""
import json
import types
import xml.etree.ElementTree as ET

from launch_vehicle import debris as dbr, hazard as hz

KML_NS = {"k": "http://www.opengis.net/kml/2.2"}


def _fake_design():
    spec = types.SimpleNamespace(name="Test LV", fairing=types.SimpleNamespace(diameter_m=3.0),
                                 stages=[types.SimpleNamespace(diameter_m=4.0),
                                         types.SimpleNamespace(diameter_m=3.0)],
                                 launch_site_note={"entry": "Kennedy Space Center LC-39A"})
    res = types.SimpleNamespace(spec=spec,
                                stages=[types.SimpleNamespace(index=1), types.SimpleNamespace(index=2)],
                                geometry=types.SimpleNamespace(max_diameter=4.0))
    traj = types.SimpleNamespace(downrange_m=1600e3, events=[
        dict(t_s=158.0, name="stage 1 jettison", mass_kg=7e4, h_m=80e3, v_mps=2900.0, gamma_deg=29.0,
             x_m=100e3, dropped_kg=20000.0),
        dict(t_s=161.0, name="fairing jettison", mass_kg=7e4, h_m=85e3, v_mps=2890.0, gamma_deg=28.5,
             x_m=108e3, dropped_kg=700.0),
        dict(t_s=540.0, name="stage 2 jettison", mass_kg=1e4, h_m=400e3, v_mps=7350.0, gamma_deg=0.0,
             x_m=1600e3, dropped_kg=4000.0),
    ])
    return res, traj


def _areas(lon=-80.604):
    res, traj = _fake_design()
    return hz.areas(res, traj, 28.5, lon, 90.0, dt=2.0)


# ------------------------------------------------------------------ with coordinates
def test_the_areas_carry_a_point_and_a_closed_ring_per_item_that_comes_down():
    a = _areas()
    assert len(a["features"]) == 2, "two items come down; the third is in orbit"
    for f in a["features"]:
        assert f["point"] is not None and f["ring"] is not None
        assert f["ring"][0] == f["ring"][-1], "the ring must be closed"
        assert -90 <= f["point"][0] <= 90 and -180 < f["point"][1] <= 180


def test_an_eastward_launch_from_florida_lands_east_of_the_pad_in_the_atlantic():
    a = _areas()
    for f in a["features"]:
        assert f["point"][1] > -80.604, f"{f['name']} landed west of the pad at {f['point'][1]}"
        assert f["point"][1] < -50.0, f"{f['name']} overshot the Atlantic at {f['point'][1]}"


def test_the_ground_track_starts_at_the_pad():
    a = _areas()
    assert a["ground_track"] and abs(a["ground_track"][0][0] - 28.5) < 1e-9


def test_every_area_description_says_what_it_is_not():
    """The caveat travels with the geometry, because the file is read long after this run."""
    a = _areas()
    for f in a["features"]:
        d = f["description"]
        assert "ASSUMPTION" in d, "the width must be labelled an assumption wherever it is shown"
        assert "NOT A RANGE-SAFETY PRODUCT" in d
        assert "breakup" in d


def test_the_notes_name_the_dispersion_that_produced_the_interval():
    a = _areas()
    txt = " ".join(a["notes"])
    assert "separation-speed" in txt and "Coriolis" in txt
    assert "not a predicted cross-range" in txt


def test_an_item_that_stays_in_orbit_is_reported_and_given_no_area():
    a = _areas()
    assert not any("stage 2" in f["name"] for f in a["features"])
    assert any("stays in orbit" in n for n in a["notes"])


def test_a_not_localisable_item_gets_a_row_and_a_note_but_no_polygon():
    """A near-orbital release has a real nominal impact and no meaningful area; it must not get a box."""
    res, traj = _fake_design()
    traj.events.append(dict(t_s=400.0, name="stage 1 jettison", mass_kg=5e3, h_m=250e3, v_mps=7250.0,
                            gamma_deg=0.5, x_m=1200e3, dropped_kg=1500.0))
    a = hz.areas(res, traj, 5.2, -52.8, 0.0, dt=2.0)
    marg = [i for i in a["impacts"] if i.fate == "marginal"]
    assert marg, [i.fate for i in a["impacts"]]
    assert not any(f["name"] == marg[0].name and f["ring"] for f in a["features"])
    assert any("no area is drawn" in n for n in a["notes"])
    row = next(r for r in hz.table_rows(a) if r["fate"] == "marginal")
    assert row["downrange_km"] > 0 and row["window_km"] is None


# ------------------------------------------------------------------ without a longitude
def test_without_a_longitude_the_distances_survive_and_the_coordinates_do_not():
    a = _areas(lon=None)
    assert a["ground_track"] is None
    assert len(a["features"]) == 2, "the physics does not need a meridian, so the items are still resolved"
    for f in a["features"]:
        assert f["point"] is None and f["ring"] is None
        assert f["downrange_m"] > 0.0, "the downrange distance is knowable without a longitude"
    assert "no launch-site longitude" in a["notes"][0]


def test_exports_refuse_politely_without_a_longitude():
    a = _areas(lon=None)
    for fn in (hz.to_geojson, hz.to_kml):
        try:
            fn(a)
        except hz.HazardError as ex:
            assert "longitude" in str(ex)
        else:
            raise AssertionError(f"{fn.__name__} should refuse without a longitude")


def test_the_rows_degrade_without_a_longitude_rather_than_breaking():
    a = _areas(lon=None)
    rows = hz.table_rows(a)
    assert len(rows) == 3
    assert all(r["lat"] is None for r in rows)
    assert next(r for r in rows if "stage 1" in r["item"])["downrange_km"] > 0


# ------------------------------------------------------------------ exports
def test_the_geojson_is_a_valid_feature_collection_with_lon_lat_order():
    a = _areas()
    g = hz.to_geojson(a)
    assert g["type"] == "FeatureCollection"
    json.dumps(g)                                   # must be serialisable
    kinds = [f["properties"]["kind"] for f in g["features"]]
    assert "launch_site" in kinds and "ground_track" in kinds
    assert kinds.count("hazard_area") == 2 and kinds.count("nominal_impact") == 2
    site = next(f for f in g["features"] if f["properties"]["kind"] == "launch_site")
    lon, lat = site["geometry"]["coordinates"]
    assert abs(lon + 80.604) < 1e-9 and abs(lat - 28.5) < 1e-9, "GeoJSON is longitude first"


def test_the_geojson_polygons_are_closed_rings_in_a_single_outer_ring():
    g = hz.to_geojson(_areas())
    for f in g["features"]:
        if f["properties"]["kind"] != "hazard_area":
            continue
        rings = f["geometry"]["coordinates"]
        assert len(rings) == 1
        assert rings[0][0] == rings[0][-1]


def test_the_kml_parses_and_names_every_placemark():
    k = hz.to_kml(_areas())
    root = ET.fromstring(k)
    names = [p.find("k:name", KML_NS).text for p in root.iter(f"{{{KML_NS['k']}}}Placemark")]
    assert "Kennedy Space Center LC-39A" in names
    assert any("ground track" in n for n in names)
    assert sum("hazard area" in n for n in names) == 2
    assert sum("nominal impact" in n for n in names) == 2


def test_the_kml_carries_the_caveats_in_the_document_and_on_each_area():
    root = ET.fromstring(hz.to_kml(_areas()))
    doc_desc = root.find(f".//{{{KML_NS['k']}}}Document/{{{KML_NS['k']}}}description").text
    assert "Coriolis" in doc_desc
    areas = [p for p in root.iter(f"{{{KML_NS['k']}}}Placemark")
             if "hazard area" in p.find("k:name", KML_NS).text]
    for p in areas:
        assert "NOT A RANGE-SAFETY PRODUCT" in p.find("k:description", KML_NS).text


def test_the_kml_coordinates_are_lon_lat_altitude_triples():
    root = ET.fromstring(hz.to_kml(_areas()))
    for c in root.iter(f"{{{KML_NS['k']}}}coordinates"):
        for tok in c.text.split():
            parts = tok.split(",")
            assert len(parts) == 3, f"KML wants lon,lat,alt - got {tok!r}"
            assert -180.0 <= float(parts[0]) <= 180.0 and -90.0 <= float(parts[1]) <= 90.0


def test_write_kml_and_geojson_land_on_disk(tmp_path=None):
    import os
    import tempfile
    a = _areas()
    d = tmp_path or tempfile.mkdtemp()
    p1 = hz.write_kml(a, os.path.join(d, "z.kml"))
    p2 = hz.write_geojson(a, os.path.join(d, "z.geojson"))
    assert os.path.getsize(p1) > 500 and os.path.getsize(p2) > 500
    ET.parse(p1)
    with open(p2) as fh:
        json.load(fh)


# ------------------------------------------------------------------ the payload and the azimuth choice
def test_the_payload_is_json_serialisable_and_keeps_the_dataclasses_out():
    p = hz.to_payload(_areas())
    json.dumps(p)
    assert p["rows"] and p["features"] and p["orbital"]
    assert p["orbital"][0]["name"] == "stage 2 jettison"
    assert isinstance(p["ground_track"][0], list)


def test_a_single_azimuth_is_offered_once_when_the_inclination_equals_the_latitude():
    """Both solutions coincide there; offering two identical choices would imply the pick mattered."""
    opts = hz.azimuth_options(28.5, 28.5)
    assert len(opts) == 1 and "only direct azimuth" in opts[0]["label"]
    assert abs(opts[0]["azimuth_deg"] - 90.0) < 1e-6


def test_two_azimuths_are_offered_for_a_higher_inclination():
    opts = hz.azimuth_options(51.6, 28.5)
    assert len(opts) == 2
    assert abs(opts[0]["azimuth_deg"] - opts[1]["azimuth_deg"]) > 1.0


def test_no_azimuth_is_offered_below_the_latitude_floor():
    assert hz.azimuth_options(10.0, 28.5) == []


def test_a_retrograde_azimuth_is_reported_in_the_normal_range():
    opts = hz.azimuth_options(97.4, 34.7)
    assert opts and all(0.0 <= o["azimuth_deg"] < 360.0 for o in opts), opts


# ------------------------------------------------------------------ the dispersion reaches the output
def test_a_wider_speed_assumption_makes_a_longer_box():
    res, traj = _fake_design()
    tight = hz.areas(res, traj, 28.5, -80.604, 90.0, dispersion=dbr.Dispersion(sep_speed_frac=0.01), dt=2.0)
    loose = hz.areas(res, traj, 28.5, -80.604, 90.0, dispersion=dbr.Dispersion(sep_speed_frac=0.06), dt=2.0)
    t = tight["features"][0]
    l = loose["features"][0]
    assert (l["far_m"] - l["near_m"]) > 3 * (t["far_m"] - t["near_m"]), (
        "the along-track extent is driven by the separation-speed assumption, so it must respond to it")


def test_the_stated_dispersion_is_recorded_in_the_output():
    res, traj = _fake_design()
    a = hz.areas(res, traj, 28.5, -80.604, 90.0,
                 dispersion=dbr.Dispersion(sep_speed_frac=0.02, sep_gamma_deg=0.5), dt=2.0)
    assert a["dispersion"]["sep_speed_frac"] == 0.02 and a["dispersion"]["sep_gamma_deg"] == 0.5
