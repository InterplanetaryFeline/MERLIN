"""The launch site library: what it may fill, what it must not, and the inclination floor.

The floor is the part worth testing hardest. A site is a latitude, and a latitude forbids a band of
inclinations outright - sin b = cos i / cos lat has no solution below |lat|. The shipped default design sits
at 28.5 deg inclination from a 28.5 deg latitude, exactly on its own floor, so naming the real KSC pad
(28.6082 deg) pushes it 0.1082 deg under. That is not a hypothetical: it is what a user gets by picking the
first US site in the list, and if the tool did not notice, the only symptom would be an infeasibility on
pressing Size.
"""
import math
import os
import re

import pytest

from launch_vehicle import gui_meta, launch_sites as ls
from launch_vehicle.orbit import launch_azimuth_deg


# ------------------------------------------------------------------ the library itself
def test_the_library_loads_and_every_row_is_complete():
    rows = ls.load()
    assert len(rows) >= 25, f"only {len(rows)} sites: the library is meant to span several countries"
    for r in rows:
        assert r["name"] and r["region"] and r.get("source"), f"incomplete row: {r.get('name')!r}"
        assert -90.0 <= r["latitude_deg"] <= 90.0
        if r.get("longitude_deg") is not None:
            assert -180.0 <= r["longitude_deg"] <= 180.0


def test_every_site_name_is_unique():
    """Names are the key the design file references, so a duplicate would make one row unreachable."""
    names = [r["name"] for r in ls.load()]
    assert len(names) == len(set(names)), "duplicate site names: " + str(
        sorted({n for n in names if names.count(n) > 1}))


def test_the_region_is_the_continent_the_site_stands_on():
    """Grouped by continent since v1.1, at a user's request: Kourou is in South America although it is a
    European site, and the list is easier to search by where a site is than by who runs it."""
    rows = {r["name"]: r for r in ls.load()}
    assert {r["region"] for r in rows.values()} <= set(ls.CONTINENTS)
    for name, continent in (("Guiana Space Centre, Kourou", "South America"), ("Baikonur Cosmodrome", "Asia"),
                            ("Plesetsk Cosmodrome", "Europe"), ("Woomera Range Complex", "Oceania"),
                            ("Starbase, Boca Chica", "North America"), ("Alcantara Space Center", "South America")):
        assert rows[name]["region"] == continent, name
    for want in ("Andoya Space", "Esrange Space Center", "CPSP Ustka (suborbital)",
                 "SUAS Aerospace (proposed, south-west Ireland)"):
        assert want in rows, f"{want} was asked for by name and is missing"


def test_the_two_added_sites_say_what_their_coordinates_are():
    rows = {r["name"]: r for r in ls.load()}
    ustka = rows["CPSP Ustka (suborbital)"]
    assert ustka["orbital"] is False and ustka["country"] == "Poland"
    assert 54.4 < ustka["latitude_deg"] < 54.7 and 16.4 < ustka["longitude_deg"] < 17.0
    assert "SUBORBITAL ONLY" in ustka["source"] and "Wicko Morskie" in ustka["source"]
    suas = rows["SUAS Aerospace (proposed, south-west Ireland)"]
    assert suas["status"] == "proposed" and suas["country"] == "Ireland"
    assert "NO SITE CHOSEN" in suas["source"] and "STAND-IN" in suas["source"]
    hints = gui_meta.launch_site_map()
    assert "SUBORBITAL" in hints["CPSP Ustka (suborbital)"]["hint"]
    assert "PROPOSED" in hints["SUAS Aerospace (proposed, south-west Ireland)"]["hint"]
    assert "SUBORBITAL" not in hints["Andoya Space"]["hint"] and "PROPOSED" not in hints["Andoya Space"]["hint"]


def test_a_region_that_is_not_a_continent_is_refused():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "sites.yaml")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("sites:\n- {name: X, region: Asia-Pacific, latitude_deg: 10.0}\n")
        with pytest.raises(ls.LaunchSiteError):
            ls.load(p)


def test_the_library_carries_no_altitude_and_no_invented_azimuth_limits():
    """Both are deliberate absences, and a later edit that quietly adds a guessed one should fail here.

    Altitude is not in the sources used, and site altitude is recorded-but-unused in the performance model,
    so a zero would be an invention that silently overwrote whatever the design said. Azimuth corridors are
    real but per-pad, per-vehicle and per-year, and none were available, so the tool models the physical
    floor only and says so.
    """
    for r in ls.load():
        assert "altitude_m" not in r, f"{r['name']} has an altitude: the sources used do not give one"
        for k in ("azimuth_min_deg", "azimuth_max_deg", "min_inclination_deg", "max_inclination_deg"):
            assert k not in r, (f"{r['name']} carries {k}, which no source in the library supplies. The "
                               "inclination floor is COMPUTED from latitude; range-safety limits are not "
                               "modelled and must not be invented")


def test_southern_sites_are_stored_with_a_negative_latitude():
    """Mahia and Woomera are the only hemisphere check in the library, and the floor takes |lat|."""
    for name in ("Mahia LC-1", "Woomera Range Complex"):
        r = ls.find(name)
        assert r["latitude_deg"] < 0, f"{name} should be in the southern hemisphere"
        assert ls.min_direct_inclination_deg(r["latitude_deg"]) > 0


# ------------------------------------------------------------------ the floor, against orbit.py
def test_the_floor_is_exactly_the_latitude_magnitude():
    for lat in (0.0, 5.2374, 28.6082, -39.2604, 69.2943):
        assert ls.min_direct_inclination_deg(lat) == abs(lat)


def test_the_floor_agrees_with_the_azimuth_relation_that_actually_flies_the_mission():
    """The floor is only meaningful if it matches where orbit.launch_azimuth_deg gives up.

    Checked from both sides at every site: one hundredth of a degree above the floor must resolve to an
    azimuth, and one hundredth below must be refused. If these two ever disagreed, the GUI would clear a
    mission the sizing loop then rejected, or block one it would have flown.
    """
    for r in ls.load():
        lat = r["latitude_deg"]
        floor = ls.min_direct_inclination_deg(lat)
        launch_azimuth_deg(floor + 0.01, lat)                     # must not raise
        try:
            launch_azimuth_deg(floor - 0.01, lat)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{r['name']}: {floor - 0.01:.4f} deg is below the floor {floor:.4f} but "
                                 "orbit.launch_azimuth_deg accepted it")


def test_a_retrograde_ascent_is_reported_as_a_real_azimuth_not_a_negative_one():
    """A sun-synchronous launch from Vandenberg. The raw relation gives -9.0 deg; nobody writes that down.

    cos i is negative for a retrograde orbit, so asin returns a negative angle. orbit.launch_azimuth_deg keeps
    the sign because it feeds sin and cos, where it makes no difference. What is shown to a person must be a
    compass bearing: 351.0 deg north-westerly, or 189.0 deg south-westerly, which is the one Vandenberg flies.
    """
    az = ls.direct_ascent_azimuths_deg(97.4, 34.7720)
    assert az is not None
    for b in az:
        assert 0.0 <= b < 360.0, f"azimuth {b} is not a compass bearing"
    assert abs(az[0] - 350.98) < 0.05 and abs(az[1] - 189.02) < 0.05, az
    chk = ls.inclination_check(97.4, 34.7720)
    assert not re.search(r"azimuth\s+-", chk["note"]), (
        f"a negative azimuth reached the user: {chk['note']}")
    assert "351.0" in chk["note"] and "189.0" in chk["note"]


def test_every_site_reports_compass_bearings_for_a_polar_and_a_prograde_orbit():
    for r in ls.load():
        lat = r["latitude_deg"]
        for inc in (ls.min_direct_inclination_deg(lat) + 0.5, 98.0):
            az = ls.direct_ascent_azimuths_deg(inc, lat)
            if az is None:
                continue
            for b in az:
                assert 0.0 <= b < 360.0, f"{r['name']} at i={inc}: azimuth {b} is out of range"


def test_the_two_azimuths_both_reach_the_asked_for_inclination():
    """A direct ascent has a northerly and a southerly solution; both are real and must round-trip.

    cos i = sin(b) cos(lat) is the inverse of the relation, so recovering i from each azimuth is the
    strongest available check that the pair is not merely plausible.
    """
    lat = 45.9552                                                  # Baikonur
    for inc in (51.6, 64.9, 80.0):
        az = ls.direct_ascent_azimuths_deg(inc, lat)
        assert az is not None
        for b in az:
            back = math.degrees(math.acos(math.sin(math.radians(b)) * math.cos(math.radians(lat))))
            assert abs(back - inc) < 1e-9, f"azimuth {b} from {lat} gives {back}, not {inc}"
        assert abs((az[0] + az[1]) - 180.0) < 1e-9, "the two solutions must be supplements"


def test_an_inclination_below_the_floor_has_no_azimuth_and_is_reported_infeasible():
    chk = ls.inclination_check(28.5, 28.6082)                      # the real trap: default design at KSC
    assert chk["feasible"] is False
    assert chk["azimuths_deg"] is None
    assert "28.61" in chk["note"] and "plane change" in chk["note"]


def test_a_reachable_inclination_is_reported_feasible_with_both_azimuths():
    chk = ls.inclination_check(51.6, 45.9552)
    assert chk["feasible"] is True
    assert len(chk["azimuths_deg"]) == 2
    assert "range-safety" in chk["note"], "the note must say what is NOT modelled"


def test_an_equatorial_site_can_reach_anything():
    chk = ls.inclination_check(0.0, 0.0)
    assert chk["feasible"] and chk["floor_deg"] == 0.0


# ------------------------------------------------------------------ resolving a design
def _design(site, lat):
    return {"mission": {"launch_site": {"site": site, "latitude_deg": lat}}}


def test_a_named_site_fills_a_null_latitude_and_registers_where_it_came_from():
    reg = []
    d = _design("Baikonur Cosmodrome", None)
    note = ls.expand_design(d, reg)
    assert d["mission"]["launch_site"]["latitude_deg"] == 45.9552
    # Longitude is filled on the same terms as latitude, because the impact-point map needs a meridian to
    # walk a downrange distance from. It used to be withheld, when nothing consumed it.
    assert note["filled"] == ["latitude_deg", "longitude_deg"], note["filled"]
    assert note["mismatch"] is None
    byp = {r["path"]: r for r in reg}
    assert set(byp) == {"mission.launch_site.latitude_deg", "mission.launch_site.longitude_deg"}, byp
    for r in reg:
        assert r["units"] == "deg" and r["provenance"] == "reference"
        assert "Baikonur" in r["source"] or "List of rocket launch sites" in r["source"]


def test_a_stated_latitude_always_wins_and_the_disagreement_is_reported():
    """The library fills gaps; it never overrules the user. A wrong site is a note, not a silent rewrite."""
    reg = []
    d = _design("Baikonur Cosmodrome", 28.5)
    note = ls.expand_design(d, reg)
    assert d["mission"]["launch_site"]["latitude_deg"] == 28.5, "the user's latitude was overwritten"
    assert note["mismatch"]["design"] == 28.5 and note["mismatch"]["library"] == 45.9552
    # The stated latitude is left alone; the longitude this design never stated is still filled, and that is
    # the only thing registered.
    assert [r["path"] for r in reg] == ["mission.launch_site.longitude_deg"], reg
    assert note["filled"] == ["longitude_deg"]


def test_a_stated_longitude_is_not_overwritten_either():
    """Same contract as latitude, so a user who types a specific pad's meridian keeps it."""
    reg = []
    d = {"mission": {"launch_site": {"site": "Baikonur Cosmodrome", "latitude_deg": None,
                                     "longitude_deg": 60.0}}}
    note = ls.expand_design(d, reg)
    assert d["mission"]["launch_site"]["longitude_deg"] == 60.0, "the user's longitude was overwritten"
    assert note["filled"] == ["latitude_deg"]
    assert [r["path"] for r in reg] == ["mission.launch_site.latitude_deg"]


def test_a_latitude_within_the_pad_spread_of_a_big_range_is_not_flagged():
    """Pads inside one cosmodrome are kilometres apart, so a small difference is not a mistake."""
    note = ls.expand_design(_design("Baikonur Cosmodrome", 45.9552 + 0.5 * ls.LATITUDE_TOLERANCE_DEG), [])
    assert note["mismatch"] is None


def test_no_site_named_means_the_library_does_nothing_at_all():
    for blank in (None, ""):
        reg = []
        d = _design(blank, 12.34)
        assert ls.expand_design(d, reg) is None
        assert d["mission"]["launch_site"]["latitude_deg"] == 12.34
        assert reg == []


def test_an_annotated_leaf_is_read_the_same_as_a_bare_value():
    """Designs on disk carry {v,u,d,s,t} dicts; the GUI applies overrides to that same annotated document."""
    reg = []
    d = {"mission": {"launch_site": {"site": {"v": "Guiana Space Centre, Kourou", "u": "-"},
                                     "latitude_deg": {"v": None, "u": "deg"}}}}
    note = ls.expand_design(d, reg)
    assert note["entry"] == "Guiana Space Centre, Kourou"
    assert d["mission"]["launch_site"]["latitude_deg"] == 5.2374


def test_an_unknown_site_names_the_alternatives_instead_of_failing_blankly():
    try:
        ls.expand_design(_design("Cape Kennedy", None), [])
    except ls.LaunchSiteError as e:
        assert "Cape Canaveral Space Force Station" in str(e), "the error should list what IS available"
    else:
        raise AssertionError("an unknown site should raise")


# ------------------------------------------------------------------ what the GUI gets
def test_the_dropdown_offers_custom_first_then_every_site_grouped_by_region():
    ch = ls.choices()
    assert ch[0][0] == ls.CUSTOM and "Custom" in ch[0][1] and ch[0][2] is None
    assert len(ch) == len(ls.load()) + 1
    labels = [c[1] for c in ch[1:]]
    for lab in labels:
        assert "deg" in lab, f"the label should carry the latitude: {lab!r}"
    # continents must appear in contiguous runs, in the declared order, or the grouping is not grouping
    regions = [c[2] for c in ch[1:]]
    assert len(set(regions)) == len({r["region"] for r in ls.load()})
    assert regions == sorted(regions, key=ls.CONTINENTS.index)
    for cont in set(regions):
        names = [c[0].lower() for c in ch[1:] if c[2] == cont]
        assert names == sorted(names), f"{cont} is not in alphabetical order"
    described = next(i for i in gui_meta.describe_inputs([{"path": "mission.launch_site.site", "value": None,
                                                           "units": "-", "description": "", "source": "",
                                                           "provenance": "user"}], {}))
    assert described["choices"][0] == {"value": "", "label": ch[0][1]}
    assert all(c.get("group") in ls.CONTINENTS for c in described["choices"][1:])
    seen, runs = set(), 0
    prev = None
    for r in regions:
        if r != prev:
            runs += 1
            assert r not in seen, f"region {r!r} appears in more than one run"
            seen.add(r)
            prev = r
    assert runs == len(seen)


def test_the_cascade_map_writes_latitude_and_nothing_else():
    """The one leaf the library has authority over. Longitude and altitude must stay out of the design."""
    m = gui_meta.launch_site_map()
    assert len(m) == len(ls.load())
    for name, d in m.items():
        assert list(d["leaves"]) == ["mission.launch_site.latitude_deg"], (
            f"{name} would write {list(d['leaves'])}: only latitude may cascade")


def test_the_cascade_hint_states_the_floor_and_the_limit_of_the_model():
    d = gui_meta.launch_site_map()["Kennedy Space Center LC-39A"]
    assert d["min_inclination_deg"] == 28.6082
    assert "28.61" in d["hint"], "the hint must tell the user the floor before they press Size"
    assert "range-safety" in d["hint"], "the hint must say azimuth corridors are not modelled"
    assert d["source"], "every site carries its source through to the GUI"


def test_the_site_dropdown_is_offered_to_the_page():
    """Without this the leaf would render as a free-text box and the library would be unreachable."""
    assert gui_meta.choices_for("mission.launch_site.site", gui_meta.library_choices({}))


# ------------------------------------------------------------------ what the report says
def _validated(overrides):
    """Load the default design with overrides applied to the ANNOTATED document, and validate it."""
    import os
    import tempfile
    import yaml
    from launch_vehicle.config_io import _Loader, load_design
    from launch_vehicle.validation import validate_spec
    from launch_vehicle.webgui import DEFAULT_ASSUMPTIONS, apply_overrides
    with open("config/default_design.yaml", encoding="utf-8") as fh:
        doc = yaml.load(fh, Loader=_Loader)
    apply_overrides(doc, overrides)
    fd, path = tempfile.mkstemp(suffix=".yaml", dir="designs")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(doc, fh, sort_keys=False)
        return validate_spec(load_design(path, DEFAULT_ASSUMPTIONS))
    finally:
        os.unlink(path)


def test_a_named_site_is_recorded_in_the_report_with_its_source_and_its_azimuth():
    """A command-line run gets none of the GUI's help, so the report is where the site has to be stated."""
    iss = _validated({"mission.launch_site.site": "Guiana Space Centre, Kourou",
                      "mission.launch_site.latitude_deg": None,
                      "mission.orbit.inclination_deg": 6.0})
    site = [i for i in iss if i.code == "SITE"]
    assert len(site) == 1, "a named site should produce exactly one INFO line"
    m = site[0].message
    assert site[0].level == "INFO"
    assert "Kourou" in m and "5.2374" in m
    assert "azimuth" in m, "the report should say which azimuth the mission needs"
    assert "range-safety" in m, "and that corridors are not modelled"
    assert "Source:" in m


def test_the_report_quotes_the_latitude_the_run_actually_used():
    """Not the library's, when the design states its own - or the line would cite a number nothing used."""
    iss = _validated({"mission.launch_site.site": "Baikonur Cosmodrome"})     # design keeps its own 28.5
    m = [i for i in iss if i.code == "SITE"][0].message
    assert "28.5000" in m and "flown at latitude" in m
    assert "45.9552 deg." not in m.split("Source:")[0], (
        "the heading quotes the library's latitude while the run used the design's")


def test_a_latitude_that_disagrees_with_the_named_site_is_warned_about():
    iss = _validated({"mission.launch_site.site": "Baikonur Cosmodrome"})
    w = [i for i in iss if i.code == "SITELAT"]
    assert len(w) == 1 and w[0].level == "WARNING"
    assert "45.9552" in w[0].message and "28.5000" in w[0].message
    assert "design's own value has been used" in w[0].message


def test_a_latitude_that_agrees_raises_no_warning():
    iss = _validated({"mission.launch_site.site": "Xichang Satellite Launch Center",
                      "mission.launch_site.latitude_deg": 28.2465,
                      "mission.orbit.inclination_deg": 30.0})
    assert not [i for i in iss if i.code == "SITELAT"]
    assert [i for i in iss if i.code == "SITE"]


def test_naming_no_site_adds_nothing_to_the_report():
    """An existing design must read exactly as it did before the library existed."""
    iss = _validated({})
    assert not [i for i in iss if i.code in ("SITE", "SITELAT")]


def test_the_default_design_names_no_site_so_nothing_changes_for_an_existing_user():
    import yaml
    from launch_vehicle.config_io import _Loader
    with open("config/default_design.yaml", encoding="utf-8") as fh:
        doc = yaml.load(fh, Loader=_Loader)
    site = doc["mission"]["launch_site"]["site"]
    assert site["v"] is None, "the shipped default must stay on Custom"
    assert doc["mission"]["launch_site"]["latitude_deg"]["v"] == 28.5
