"""Budynki i ich cechy (winda, rampa, toaleta), toalety jako udogodnienie, windy w poblizu."""
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from tests.conftest import P


def attrs(card):
    return {a["attribute"]: a for a in card["attributes"]}


def test_building_is_a_place_with_building_features(client):
    c = client.get("/api/places/node/szpital").json()
    assert c["place"]["category"] == "building"
    a = attrs(c)
    assert a["elevator"]["value"] == "yes" and a["elevator"]["group"] == "w_srodku"
    assert a["ramp:wheelchair"]["status"] == "potwierdzone" and a["ramp:wheelchair"]["group"] == "wejscie"
    assert a["toilets"]["status"] == "brak"                       # brak tagu = brak danych, nie „nie ma toalety”
    assert "Wejście" in c["grupy"].values()


def test_summary_missing_list_is_short(client):
    text = client.get("/api/places/node/42").json()["summary"]["text"]
    assert "innych" in text and text.count(",") <= 4 and "oraz" in text


def test_toilet_card_has_fee_and_hours_slots(client):
    a = attrs(client.get("/api/places/node/t1").json())
    assert {"fee", "opening_hours", "toilets:wheelchair"} <= set(a)
    assert a["fee"]["status"] == "brak"


def test_elevator_and_toilet_nearby_are_labelled_straight_line(client):
    c = client.get("/api/places/node/42").json()
    kinds = {x["kind"] for x in c["w_poblizu"]}
    assert {"winda", "toaleta"} <= kinds
    lift = next(x for x in c["w_poblizu"] if x["kind"] == "winda")
    assert lift["line_of_sight"] is True and lift["distance_m"] < 60 and lift["wheelchair"]["status"] == "potwierdzone"


def test_nearest_elevator_and_building_kinds(client):
    for kind in ("winda", "budynek"):
        r = client.get("/api/nearest", params=dict(lon=P[3][0], lat=P[3][1], kind=kind, max_m=2000))
        assert r.status_code == 200 and r.json()["results"], kind


def test_user_can_report_building_attributes(client):
    r = client.post("/api/reports", json={"feature_id": "node/szpital", "attribute": "elevator", "value": "no", "comment": "Winda nieczynna"})
    assert r.status_code == 201
    a = attrs(client.get("/api/places/node/szpital").json())["elevator"]
    assert a["status"] == "sprzeczne"                                # OSM: tak, zgloszenie: nie


def test_drop_noise_buildings_keeps_named_and_tagged():
    from pipeline.facts import drop_noise_buildings
    cfg = {"osm": {"fact_attributes": ["wheelchair", "elevator"]}}
    g = gpd.GeoDataFrame({"building": ["yes", "yes", "yes", None], "name": [None, "Urząd", None, None],
                          "elevator": [None, None, "yes", None], "amenity": [None, None, None, "cafe"]},
                         geometry=[Point(i, i) for i in range(4)])
    out = drop_noise_buildings(g, cfg)
    assert list(out.index) == [1, 2, 3]                              # anonimowy budynek (0) odpada


def test_embed_shows_nearby_features_and_no_script(client):
    r = client.get("/embed/place/node/42")
    assert r.status_code == 200 and "W pobliżu" in r.text and "<script" not in r.text
