"""Klik w mape: wspolrzedne -> budynek -> adres, udogodnienia, bariery, brak danych."""
import pytest

from engine.buildings import Buildings
from engine.geocode import Geocoder
from tests.conftest import P, _fact, make_client


def square(lon, lat, d=0.0001):
    return [[[lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d], [lon - d, lat + d], [lon - d, lat - d]]]


def bfeat(fid, lon, lat, **props):
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": square(lon, lat)},
            "properties": {"feature_id": fid, **props}}


SZPITAL = (19.9417, 50.0613)         # node/szpital w conftest lezy w srodku tego obrysu (w POI jako way, tu jako ten sam id)
BUILDINGS = Buildings({"features": [
    bfeat("node/szpital", *SZPITAL, building="hospital", name="Szpital Miejski", **{"addr:street": "Szewska", "addr:housenumber": "7"}),
    bfeat("way/900", 19.9450, 50.0600, building="yes", **{"addr:street": "Krótka", "addr:housenumber": "3"}),
    bfeat("way/901", 19.9460, 50.0600, building="yes"),            # budynek bez adresu i bez danych
    bfeat("way/902", 19.9470, 50.0600, building="yes"),            # adres tylko jako osobny punkt adresowy w obrysie
]})
GEO = Geocoder({"entries": [
    {"id": "node/a1", "type": "adres", "street": "Długa", "number": "12", "lon": 19.9470, "lat": 50.0600},
    {"id": "node/a2", "type": "adres", "street": "Daleka", "number": "1", "lon": 19.9460, "lat": 50.06045},     # ok. 50 m od budynku 901
    {"id": "ulica/Krótka", "type": "ulica", "street": "Krótka", "number": None, "lon": 19.9450, "lat": 50.0600},
]})
FACTS = [_fact("way/900", "wheelchair", "no"), _fact("way/900", "step_count", "3"), _fact("way/900", "elevator", "yes"),
         _fact("way/900", "toilets:wheelchair", "limited"), _fact("way/900", "door:width", "0.8")]


@pytest.fixture()
def c(net):
    return make_client(net, geocoder=GEO, buildings=BUILDINGS, extra_facts=FACTS)


def at(c, lon, lat, **kw):
    r = c.get("/api/at", params={"lon": lon, "lat": lat, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_click_inside_building_returns_address_from_building_tags(c):
    r = at(c, SZPITAL[0] + 0.00003, SZPITAL[1] - 0.00003)
    assert r["found"] == "budynek" and r["building"]["name"] == "Szpital Miejski"
    assert r["address"]["label"] == "Szewska 7" and r["address"]["approximate"] is False
    assert "znacznik adresowy" in r["address"]["source"]
    assert r["building"]["footprint"]["type"] == "Polygon" and r["building"]["click_distance_m"] == 0


def test_building_from_poi_lists_amenities_with_sources(c):
    r = at(c, *SZPITAL)
    labels = {x["attribute"]: x for x in r["udogodnienia"]}
    assert {"elevator", "ramp:wheelchair"} <= set(labels)
    assert labels["elevator"]["source"] == "OpenStreetMap" and labels["elevator"]["status"] == "potwierdzone"
    assert r["bariery"] == []
    assert any(x["attribute"] == "wheelchair" for x in r["brak_danych"])      # brak wheelchair to brak danych, nie „dostępne”
    assert "wheelchair" not in labels


def test_building_not_in_poi_still_gets_facts_barriers_and_address(c):
    r = at(c, 19.9450, 50.0600)
    assert r["found"] == "budynek" and r["place"]["id"] == "way/900" and r["address"]["label"] == "Krótka 3"
    bar = {x["attribute"]: x for x in r["bariery"]}
    assert {"wheelchair", "step_count", "toilets:wheelchair"} <= set(bar)
    assert bar["step_count"]["value_text"] == "3 stopnie"
    assert [x["attribute"] for x in r["udogodnienia"]] == ["elevator"]
    assert any(x["attribute"] == "door:width" for x in r["informacje"])        # szerokosc drzwi to informacja, nie udogodnienie
    assert "Bariery:" in r["spoken"] and "Udogodnienia: winda" in r["spoken"]


def test_building_without_any_data_says_so_and_never_claims_access(c):
    r = at(c, 19.9460, 50.0600)
    assert r["found"] == "budynek" and r["udogodnienia"] == [] and r["bariery"] == []
    assert len(r["brak_danych"]) >= 3
    assert "Nie mamy danych o udogodnieniach ani barierach" in r["spoken"]
    assert r["summary"]["level"] == "brak"


def test_address_point_inside_footprint_is_used(c):
    r = at(c, 19.9470, 50.0600)
    assert r["address"]["label"] == "Długa 12" and r["address"]["approximate"] is False and "punkt adresowy" in r["address"]["source"]


def test_nearest_address_is_marked_approximate(c):
    r = at(c, 19.9460, 50.0600)
    assert r["address"]["approximate"] is True and r["address"]["distance_m"] > 0
    assert "Najbliższy adres" in r["spoken"]


def test_click_just_outside_building_snaps_within_limit(c):
    near = at(c, 19.9450 + 0.0001 + 0.00005, 50.0600)           # ok. 3,5 m od krawedzi
    assert near["found"] == "budynek" and near["building"]["id"] == "way/900" and 0 < near["building"]["click_distance_m"] <= 10
    far = at(c, 19.9450 + 0.0001 + 0.0005, 50.0600)             # ok. 36 m od krawedzi
    assert far["found"] != "budynek"


def test_click_on_empty_place_returns_address_but_no_claims(c):
    r = at(c, 19.9500, 50.0620)
    assert r["found"] == "nic" and r["udogodnienia"] == [] and r["bariery"] == []
    assert "nie ma budynku" in r["spoken"]


def test_click_on_poi_without_footprint_uses_nearest_object(c):
    r = at(c, P[5][0] + 0.00001, P[5][1])
    assert r["found"] == "obiekt" and r["place"]["id"] == "node/43"
    assert r["summary"]["level"] == "zadeklarowane"


def test_click_outside_area_is_friendly(c):
    r = at(c, 21.0, 52.2)
    assert r["inside_area"] is False and "poza obszarem" in r["spoken"]


def test_requirements_add_fit_checklist(c):
    r = at(c, 19.9450, 50.0600, prefs="nostairs")
    assert r["fit"]["verdict"] == "nie_pasuje"
    assert at(c, 19.9450, 50.0600)["fit"] is None


def test_contradicting_sources_are_listed_separately(net):
    from tests.test_at import FACTS as base
    client = make_client(net, geocoder=GEO, buildings=BUILDINGS,
                         extra_facts=base + [_fact("way/901", "elevator", "yes"), _fact("way/901", "elevator", "no", status="niezweryfikowane")])
    r = at(client, 19.9460, 50.0600)
    assert [x["attribute"] for x in r["sprzeczne"]] == ["elevator"] and len(r["sprzeczne"][0]["versions"]) == 2
    assert all(x["attribute"] != "elevator" for x in r["udogodnienia"] + r["bariery"])


def test_osm_links_and_survey_freshness_present(c):
    r = at(c, 19.9450, 50.0600)
    assert r["osm_edit_url"].endswith("way=900") and r["osm_note_url"] and "nalot" in r


def test_works_without_footprints_and_geocoder(client):
    r = client.get("/api/at", params=dict(lon=P[3][0], lat=P[3][1])).json()
    assert r["found"] in ("obiekt", "nic") and r["address"] is None


def test_invalid_input_rejected(client):
    assert client.get("/api/at", params=dict(lon="x", lat=50.0)).status_code == 422
    assert client.get("/api/at", params=dict(lon=19.94, lat=50.06, snap_m=99)).status_code == 422
    assert client.get("/api/at", params=dict(lon=19.94, lat=50.06, profiles="kosmita")).status_code == 422


def test_building_footprints_helper_filters_non_polygons():
    import geopandas as gpd
    from shapely.geometry import Point, Polygon
    from pipeline.common import load_config
    from pipeline.facts import building_footprints
    g = gpd.GeoDataFrame({"building": ["yes", "yes"], "name": [None, "X"], "elevator": ["yes", None]},
                         geometry=[Polygon(square(19.94, 50.06)[0]), Point(19.94, 50.06)],
                         index=__import__("pandas").MultiIndex.from_tuples([("way", 1), ("node", 2)]))
    fc = building_footprints(g, load_config())
    assert len(fc["features"]) == 1
    p = fc["features"][0]["properties"]
    assert p["feature_id"] == "way/1" and p["elevator"] == "yes" and "name" not in p
