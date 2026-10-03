"""Profil lokalny („konto bez konta”): plik u uzytkownika, serwer tylko waliduje i niczego nie zapisuje."""
import copy
import json

import pytest

from engine import localprofile as lp
from tests.conftest import P


def good(**kw):
    d = {"format": lp.FORMAT, "version": 1, "name": "Test", "groups": ["senior"], "on": [], "off": [], "ui": {}, "places": []}
    d.update(kw)
    return d


def post(client, doc):
    return client.post("/api/profile/validate", content=json.dumps(doc), headers={"content-type": "application/json"})


# ---------- walidacja (bez HTTP) ----------
def test_all_shipped_examples_are_valid():
    for name, ex in lp.EXAMPLES.items():
        r = lp.validate(copy.deepcopy(ex))
        assert r["ok"], (name, r["errors"])


def test_valid_file_yields_api_parameters():
    r = lp.validate(good(groups=["wozek_inwalidzki"], on=["changing", "toilet"], off=["kerb"]))
    assert r["ok"] and r["query"]["profiles"] == "wozek_inwalidzki"
    assert "need:changing" in r["query"]["prefs"] and "relax:kerb" in r["query"]["prefs"]
    assert "need:toilet" not in r["query"]["prefs"]          # toaleta jest juz w grupie: nie dublujemy
    assert {"toilet", "changing"} <= set(r["aktywne"]) and "kerb" not in r["aktywne"]


def test_empty_selection_means_unrestricted_pedestrian():
    r = lp.validate(good(groups=[]))
    assert r["ok"] and r["query"] == {"profiles": "", "prefs": ""} and r["etykieta"] == "Pieszy (bez ograniczeń)"


def test_only_custom_items_without_group():
    r = lp.validate(good(groups=[], on=["lit", "bench:400"]))
    assert r["ok"] and r["query"]["profiles"] == "" and r["query"]["prefs"] == "lit,bench:400"


def test_wrong_format_or_version_is_rejected():
    assert not lp.validate({"format": "cos-innego", "version": 1})["ok"]
    assert not lp.validate({"format": lp.FORMAT})["ok"]
    assert not lp.validate({"format": lp.FORMAT, "version": "1"})["ok"]
    assert not lp.validate({"format": lp.FORMAT, "version": True})["ok"]
    assert not lp.validate([1, 2, 3])["ok"]
    assert not lp.validate("tekst")["ok"]


def test_newer_version_loads_known_fields_with_warning():
    r = lp.validate(good(version=7, przyszlosc={"x": 1}))
    assert r["ok"] and any("nowszej wersji" in w for w in r["warnings"]) and any("przyszlosc" in w for w in r["warnings"])


def test_unknown_group_item_and_token_are_reported():
    r = lp.validate(good(groups=["kosmita"]))
    assert not r["ok"] and "kosmita" in r["errors"][0]
    r = lp.validate(good(on=["nieistnieje"]))
    assert not r["ok"] and "nieistnieje" in " ".join(r["errors"])
    r = lp.validate(good(on=["incline:99"]))
    assert not r["ok"]


def test_cannot_add_item_that_only_exists_as_group_requirement():
    r = lp.validate(good(groups=[], on=["handrail"]))
    assert not r["ok"] and "handrail" in " ".join(r["errors"])


def test_off_without_group_is_ignored_with_warning():
    r = lp.validate(good(groups=[], off=["stairs"]))
    assert r["ok"] and any("żadnej grupy" in w for w in r["warnings"])


def test_ui_defaults_and_clamping():
    r = lp.validate(good(ui={"font_scale": 5, "max_steps": 1, "mode": "skupienie", "contrast": "wysoki", "reduce_motion": True}))
    ui = r["profile"]["ui"]
    assert r["ok"] and ui["font_scale"] == 2.0 and ui["max_steps"] == 3 and ui["mode"] == "skupienie" and ui["reduce_motion"] is True
    assert sum("poza zakresem" in w for w in r["warnings"]) == 2
    d = lp.validate(good())["profile"]["ui"]
    assert d["mode"] == "standard" and d["font_scale"] == 1.0 and d["max_steps"] == 7 and d["voice_replies"] is False


def test_ui_wrong_types_are_errors():
    for ui in ({"mode": "kosmiczny"}, {"contrast": "x"}, {"reduce_motion": "tak"}, {"font_scale": "duży"}, {"max_steps": True}, "tekst"):
        assert not lp.validate(good(ui=ui))["ok"], ui


def test_unknown_ui_setting_is_skipped_not_fatal():
    r = lp.validate(good(ui={"hologram": 1}))
    assert r["ok"] and "hologram" not in r["profile"]["ui"] and any("hologram" in w for w in r["warnings"])


def test_name_is_sanitised_and_truncated():
    r = lp.validate(good(name="<script>alert(1)</script>" + "a" * 100))
    assert r["ok"] and "<" not in r["profile"]["name"] and ">" not in r["profile"]["name"] and len(r["profile"]["name"]) <= 40


def test_places_are_validated_and_rounded():
    r = lp.validate(good(places=[{"label": "Dom", "lon": 19.9400004, "lat": 50.0610004}]), inside=lambda lo, la: True)
    assert r["ok"] and r["profile"]["places"] == [{"label": "Dom", "lon": 19.94, "lat": 50.061, "inside_area": True}]
    for bad in ({"label": "X", "lon": 200, "lat": 50}, {"label": "X", "lon": "19", "lat": 50}, {"lon": 19.9, "lat": 50.0}, "dom", {"label": "X", "lon": True, "lat": 1}):
        assert not lp.validate(good(places=[bad]))["ok"], bad


def test_too_many_places_are_trimmed_with_warning():
    many = [{"label": f"M{i}", "lon": 19.9, "lat": 50.0} for i in range(30)]
    r = lp.validate(good(places=many))
    assert r["ok"] and len(r["profile"]["places"]) == 20 and any("Za dużo" in w for w in r["warnings"])


def test_oversized_document_is_rejected():
    r = lp.validate(good(name="x" * 30_000))
    assert not r["ok"] and "za duży" in r["errors"][0]


def test_health_data_warning_present_only_when_requirements_given():
    assert any("dane o zdrowiu" in w for w in lp.validate(good(groups=["senior"]))["warnings"])
    assert not any("dane o zdrowiu" in w for w in lp.validate(good(groups=[]))["warnings"])


def test_validation_does_not_mutate_input():
    d = good(groups=["senior"], on=["toilet"])
    before = copy.deepcopy(d)
    lp.validate(d)
    assert d == before


# ---------- API ----------
def test_schema_endpoint_describes_format_and_privacy(client):
    r = client.get("/api/profile/schema").json()
    assert r["format"] == lp.FORMAT and set(r["tryby_interfejsu"]) == {"standard", "prosty", "skupienie"}
    assert r["przyklady"]["babcia"]["ui"]["mode"] == "prosty"
    assert any("nie przechowuje" in x for x in r["prywatnosc"])
    assert "properties" in r["json_schema"]


def test_validate_endpoint_roundtrip_and_query_is_usable(client, q):
    r = post(client, good(groups=["wozek_inwalidzki"], on=["toilet"])).json()
    assert r["ok"]
    # to, co zwrocil serwer, da sie od razu wstawic do zapytania o trase
    routes = client.get("/api/routes", params={**q, **r["query"]})
    assert routes.status_code == 200


def test_validate_endpoint_reports_errors_with_200(client):
    r = post(client, good(groups=["kosmita"]))
    assert r.status_code == 200 and r.json()["ok"] is False and r.json()["errors"]


def test_validate_endpoint_bad_json_and_too_large(client):
    assert client.post("/api/profile/validate", content="to nie json").status_code == 422
    assert client.post("/api/profile/validate", content=b"\xff\xfe").status_code == 422
    assert client.post("/api/profile/validate", content="x" * 50_000).status_code == 413


def test_validate_marks_places_inside_area(client):
    r = post(client, good(places=[{"label": "Rynek", "lon": P[3][0], "lat": P[3][1]}, {"label": "Warszawa", "lon": 21.0, "lat": 52.2}])).json()
    inside = {p["label"]: p["inside_area"] for p in r["profile"]["places"]}
    assert inside == {"Rynek": True, "Warszawa": False}


def test_server_keeps_no_trace_of_the_profile(client):
    """Konto lokalne: ani nazwa, ani wspolrzedne z pliku nie moga pojawic sie w zadnej pozniejszej odpowiedzi serwera."""
    post(client, good(name="SekretnaNazwa", places=[{"label": "DomTajny", "lon": 19.94123, "lat": 50.06123}]))
    for path in ("/api/meta", "/api/profile/schema", "/api/catalog"):
        txt = client.get(path).text
        assert "SekretnaNazwa" not in txt and "DomTajny" not in txt and "19.94123" not in txt


# ---------- parametr simple_steps ----------
def test_simple_steps_parameter_limits_steps(client, q):
    r = client.get("/api/routes", params={**q, "simple_steps": 3}).json()
    for route in r["routes"]:
        assert route["properties"]["simple"]["max_steps"] == 3
    assert client.get("/api/routes", params={**q, "simple_steps": 2}).status_code == 422
    assert client.get("/api/routes", params={**q, "simple_steps": 10}).status_code == 422
