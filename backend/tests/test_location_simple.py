"""Lokalizacja urzadzenia („gdzie jestem”), asystent glosowy (dopytywanie, najblizsze, ustawienia) i tryb prosty (kroki dla babci/ADHD)."""
import pytest

from tests.conftest import P, make_client
from engine.geocode import Geocoder
from engine.simple import simple_route, spoken_summary


def E(t, s, n, lon, lat):
    return {"id": f"{t}/{s}{n}", "type": t, "street": s, "number": n, "lon": lon, "lat": lat}


# ---------- Geocoder.reverse ----------
def test_reverse_prefers_close_address_over_street():
    g = Geocoder({"entries": [E("adres", "Floriańska", "12", 19.9400, 50.0630), E("ulica", "Szewska", None, 19.9400, 50.0630)]})
    r = g.reverse(19.94001, 50.06301)
    assert r["type"] == "adres" and r["number"] == "12" and r["distance_m"] < 5


def test_reverse_falls_back_to_street_when_no_address_near():
    g = Geocoder({"entries": [E("adres", "Floriańska", "12", 19.9400, 50.0630), E("ulica", "Szewska", None, 19.9420, 50.0630)]})
    r = g.reverse(19.9420, 50.0631)       # adres jest o ok. 140 m dalej (> 60 m), ulica ok. 11 m
    assert r["type"] == "ulica" and r["street"] == "Szewska"


def test_reverse_returns_none_when_nothing_is_close():
    g = Geocoder({"entries": [E("adres", "Floriańska", "12", 19.9400, 50.0630)]})
    assert g.reverse(19.9500, 50.0700) is None
    assert Geocoder(None).reverse(19.94, 50.06) is None


# ---------- /api/whereami ----------
@pytest.fixture()
def geo_client(net):
    g = Geocoder({"entries": [E("adres", "Szewska", "7", P[3][0], P[3][1]), E("ulica", "Szewska", None, P[3][0], P[3][1])]})
    return make_client(net, geocoder=g)


def test_whereami_names_address_nearby_places_and_is_speakable(geo_client):
    r = geo_client.get("/api/whereami", params=dict(lon=P[3][0], lat=P[3][1] + 0.00005)).json()
    assert r["inside_area"] and r["address"]["number"] == "7"
    assert "Szewska 7" in r["spoken"] and r["spoken"] == r["text"]
    assert any(n["name"] == "Kawiarnia" for n in r["nearby"])
    assert all(n["distance_m"] <= 80 for n in r["nearby"])
    assert [n["distance_m"] for n in r["nearby"]] == sorted(n["distance_m"] for n in r["nearby"])


def test_whereami_without_geocoder_says_so_instead_of_inventing_an_address(client):
    r = client.get("/api/whereami", params=dict(lon=P[3][0], lat=P[3][1])).json()
    assert r["address"] is None and "Nie znamy adresu" in r["spoken"]


def test_whereami_warns_about_poor_gps_accuracy(client):
    bad = client.get("/api/whereami", params=dict(lon=P[3][0], lat=P[3][1], accuracy_m=120)).json()
    good = client.get("/api/whereami", params=dict(lon=P[3][0], lat=P[3][1], accuracy_m=8)).json()
    assert "niedokładna" in bad["spoken"] and "120" in bad["spoken"]
    assert "niedokładna" not in good["spoken"]


def test_whereami_outside_area_gives_clear_message(client):
    r = client.get("/api/whereami", params=dict(lon=21.0, lat=52.2)).json()
    assert r["inside_area"] is False and r["address"] is None and r["nearby"] == []
    assert "poza obszarem" in r["spoken"]


def test_whereami_validates_parameters(client):
    assert client.get("/api/whereami", params=dict(lon="x", lat=50.0)).status_code == 422
    assert client.get("/api/whereami", params=dict(lon=P[3][0], lat=P[3][1], accuracy_m=-1)).status_code == 422


def test_whereami_does_not_store_position(client, tmp_path):
    """Pozycja z GPS nie moze trafiac do zadnego pliku ani do odpowiedzi innego zapytania."""
    client.get("/api/whereami", params=dict(lon=P[3][0], lat=P[3][1]))
    meta = client.get("/api/meta").text
    assert str(P[3][0]) not in meta


# ---------- asystent glosowy ----------
def voice(client, text):
    r = client.get("/api/voice/command", params={"q": text})
    assert r.status_code == 200
    return r.json()


def test_voice_ambiguous_place_asks_which_one(client):
    r = voice(client, "trasa z Rynek do Szpital Miejski")
    assert r["intent"] == "clarify"
    cl = r["clarify"]
    assert cl["slot"] == "from" and len(cl["choices"]) >= 2
    assert [c["n"] for c in cl["choices"]] == list(range(1, len(cl["choices"]) + 1))
    assert "numer" in r["reply"].lower()
    assert all({"lon", "lat", "label", "id"} <= set(c) for c in cl["choices"])
    # drugi koniec trasy jest juz rozpoznany, front dopisze pierwszy po wyborze
    assert "to_lon" in r["call"]["params"] and "from_lon" not in r["call"]["params"]


def test_voice_exact_name_is_not_ambiguous(client):
    r = voice(client, "trasa z Rynku Głównego do Szpitala Miejskiego dla wózka")
    assert r["intent"] == "route" and "clarify" not in r
    p = r["call"]["params"]
    assert p["profiles"] == "wozek_inwalidzki" and {"from_lon", "from_lat", "to_lon", "to_lat"} <= set(p)
    assert r["resolved"] == {"from": "Rynek Główny", "to": "Szpital Miejski"}


def test_voice_unknown_place_is_reported_not_guessed(client):
    r = voice(client, "trasa z Rynku Głównego do Zzzzzzz")
    assert r["intent"] == "not_found" and "zzzzzzz" in r["reply"].lower()


def test_voice_route_from_gps_marks_that_gps_is_needed(client):
    r = voice(client, "jak dojść do Szpital Miejski")
    assert r["intent"] == "route" and r["call"]["needs_gps"] == "from"
    assert "from_lon" not in r["call"]["params"] and "to_lon" in r["call"]["params"]


def test_voice_nearest_toilet_needs_position_and_is_a_valid_api_call(client):
    r = voice(client, "gdzie jest najbliższa toaleta")
    assert r["intent"] == "nearest" and r["call"]["endpoint"] == "/api/nearest" and r["call"]["needs_gps"] == "lon,lat"
    q = {**r["call"]["params"], "lon": P[1][0], "lat": P[1][1]}
    assert client.get("/api/nearest", params=q).status_code == 200      # to, co zwrocil asystent, front moze wywolac wprost


def test_voice_how_to_get_to_pharmacy_means_nearest_plus_route(client):
    r = voice(client, "jak dojść do apteki")
    assert r["intent"] == "nearest" and r["kind"] == "apteka" and r["route_to_first"] is True


def test_voice_where_am_i_and_transit_nearby(client):
    assert voice(client, "gdzie jestem")["call"]["endpoint"] == "/api/whereami"
    t = voice(client, "jakie są przystanki w pobliżu")
    assert t["intent"] == "transit_nearby" and t["call"]["endpoint"] == "/api/transit/nearby"


def test_voice_set_profile_does_not_call_api(client):
    r = voice(client, "jestem niewidomy")
    assert r["intent"] == "set_profile" and r["set"]["profiles"] == "niewidomy_slabowidzacy" and "call" not in r
    r = voice(client, "bez schodów")
    assert r["intent"] == "set_profile" and r["set"]["prefs"] == "nostairs"


def test_voice_choice_and_unknown_phrases(client):
    r = voice(client, "numer 2")
    assert r["intent"] == "choose" and r["index"] == 2
    r = voice(client, "bla bla bla")
    assert r["intent"] == "help" and "toaleta" in r["reply"]


def test_voice_input_is_validated(client):
    assert client.get("/api/voice/command", params={"q": ""}).status_code == 422
    assert client.get("/api/voice/command", params={"q": "a" * 201}).status_code == 422


# ---------- /api/nearest: zdanie do przeczytania ----------
def test_nearest_has_spoken_sentence_with_distance_and_status(client):
    r = client.get("/api/nearest", params=dict(lon=P[1][0], lat=P[1][1], kind="apteka")).json()
    assert r["results"] and r["spoken"].startswith("Najbliżej: Apteka Pod Lipami")
    assert "metrów chodnikami" in r["spoken"] and "Dostępność: prawdopodobna" in r["spoken"]


def test_nearest_says_when_nothing_found(client):
    r = client.get("/api/nearest", params=dict(lon=P[1][0], lat=P[1][1], kind="apteka", max_m=100)).json()
    assert r["results"] == [] and "nie oznacza" in r["spoken"]


def test_nearest_unknown_availability_is_never_called_accessible(client):
    r = client.get("/api/nearest", params=dict(lon=P[1][0], lat=P[1][1], kind="toaleta")).json()
    assert r["results"][0]["wheelchair"]["status"] == "brak" and "brak danych" in r["spoken"]


# ---------- tryb prosty ----------
def step(length, kind="chodnik", name="Ul", status=0, notes=None, start=0.0):
    return {"length_m": length, "kind": kind, "name": name, "status": status, "notes": notes or [], "start_m": start}


def straight(n=2, step_deg=0.0006):
    return [(19.94 + i * step_deg, 50.06) for i in range(n)]


def test_simple_route_ends_with_arrival_and_numbers_steps():
    s = simple_route([step(100)], straight(), 100, 2)
    assert [x["n"] for x in s["steps"]] == [1, 2]
    assert s["steps"][-1]["text"] == "Jesteś u celu." and s["steps"][-1]["kind"] == "cel"
    assert s["steps"][0]["text"].startswith("Idź") and "metrów" in s["steps"][0]["text"]


def test_simple_route_merges_plain_straight_segments_and_never_exceeds_limit():
    steps = [step(50, name=f"U{i}", start=i * 50.0) for i in range(12)]
    coords = straight(13)
    s = simple_route(steps, coords, 600, 8, max_steps=5)
    assert len(s["steps"]) <= 5 + 1                         # kroki + „Jesteś u celu”
    assert sum(x["distance_m"] for x in s["steps"]) >= 550  # nic nie zginelo przy laczeniu (z zaokragleniem)


def test_simple_route_detects_turn_direction_from_geometry():
    # na wschod 100 m, potem na poludnie (w prawo) 100 m
    east = (19.94, 50.06), (19.94 + 100 / (111_320 * 0.6428), 50.06)
    turn_right = list(east) + [(east[1][0], 50.06 - 100 / 110_540)]
    s = simple_route([step(100, name="A"), step(100, name="B", start=100.0)], turn_right, 200, 3)
    assert s["steps"][1]["turn"] == "prawo" and s["steps"][1]["text"].startswith("Skręć w prawo")
    turn_left = list(east) + [(east[1][0], 50.06 + 100 / 110_540)]
    s = simple_route([step(100, name="A"), step(100, name="B", start=100.0)], turn_left, 200, 3)
    assert s["steps"][1]["turn"] == "lewo" and s["steps"][1]["text"].startswith("Skręć w lewo")


def test_simple_route_warnings_are_separate_fields_not_only_colour():
    steps = [step(80), step(40, status=2, notes=["schody"], start=80.0), step(40, status=1, notes=["wysoki krawężnik"], start=120.0)]
    s = simple_route(steps, straight(4), 160, 3)
    warned = [x for x in s["steps"] if x["warning"]]
    assert len(warned) == 2
    assert warned[0]["warning_text"].startswith("Przeszkoda: schody")
    assert warned[1]["warning_text"].startswith("Uwaga: wysoki krawężnik")
    assert all(x["warning_text"] is None for x in s["steps"] if not x["warning"])


def test_simple_route_stairs_and_crossings_have_plain_wording():
    s = simple_route([step(10, kind="przejscie"), step(20, kind="schody", start=10.0)], straight(3), 30, 1)
    assert s["steps"][0]["text"] == "Przejdź przez jezdnię po przejściu dla pieszych."
    assert s["steps"][1]["text"].startswith("Schody")


def test_simple_route_summary_counts_attention_and_unknowns():
    s = simple_route([step(100)], straight(), 100, 2, {"blokada": 1, "ostrzezenie": 1, "brak_danych": 3})
    assert "2 miejsca wymagające uwagi" in s["summary"] and "W 3 miejscach nie mamy danych" in s["summary"]
    s = simple_route([step(100)], straight(), 100, 2, {})
    assert "uwagi" not in s["summary"] and "nie mamy danych" not in s["summary"]


def test_simple_route_survives_missing_geometry():
    s = simple_route([step(100), step(50, name="B", start=100.0)], [], 150, 2)
    assert s["steps"][-1]["text"] == "Jesteś u celu." and all(x["turn"] in ("start", None, "koniec") for x in s["steps"])


def test_spoken_summary_without_hazards_does_not_promise_safety():
    t = spoken_summary({"length_m": 480, "time_min": 7, "hazards": []})
    assert "480" in t and "nie gwarantuje" in t


def test_spoken_summary_lists_nearest_hazards_with_distance_and_truncates():
    hz = [{"severity": "blokada", "at_m": 40 + 100 * i, "spoken": f"Schody numer {i}."} for i in range(5)]
    hz.append({"severity": "brak_danych", "at_m": 10, "spoken": "Nie wiemy."})
    t = spoken_summary({"length_m": 600, "time_min": 9, "hazards": hz}, limit=3)
    assert "Uwaga na 5 miejsc" in t and "po 40 metrach schody numer 0." in t and "Oraz 2 kolejnych" in t
    assert "Nie wiemy" not in t        # brak danych nie jest czytany jako zagrozenie


def test_routes_endpoint_returns_simple_steps_and_spoken_summary(client, q):
    r = client.get("/api/routes", params={**q, "profiles": "wozek_inwalidzki"}).json()
    for route in r["routes"]:
        pr = route["properties"]
        assert pr["spoken_summary"] and pr["simple"]["steps"][-1]["kind"] == "cel"
        assert 2 <= len(pr["simple"]["steps"]) <= pr["simple"]["max_steps"] + 1
        assert pr["simple"]["summary"].startswith("Trasa ma około")
        assert all(len(x["text"]) <= 120 for x in pr["simple"]["steps"])       # jedno zdanie na krok
    # wozek: trasa z kostka ma ostrzezenie w krokach prostych
    rec = next(x for x in r["routes"] if x["properties"]["recommended"])
    assert any(s["warning"] for s in rec["properties"]["simple"]["steps"])


def test_simple_steps_for_shortcut_mention_stairs(client, q):
    r = client.get("/api/routes", params={**q, "profiles": ""}).json()
    texts = " ".join(s["text"] for s in r["routes"][0]["properties"]["simple"]["steps"])
    assert "Schody" in texts
